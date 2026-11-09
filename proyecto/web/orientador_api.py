"""Rutas del orientador vocacional: API pública (navegador), interna (agente) y panel."""

from __future__ import annotations

import csv
import json
import io
import logging
import os
import re
import secrets
import threading
import time
from urllib.parse import quote_plus
from datetime import datetime, timedelta
from typing import Literal, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from livekit import api
from pydantic import BaseModel, Field

import correo
import db
import geo
import graph
import mailer
import motor
import permanencia as perm

log = logging.getLogger("orientador")

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
ORIENTADOR_AGENT = os.getenv("ORIENTADOR_AGENT_NAME", "orientador")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "")
PANEL_USER = os.getenv("PANEL_USER", "panel")
PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
LIMITE_SESIONES_HORA = int(os.getenv("LIMITE_SESIONES_POR_IP_HORA", "12"))

publico = APIRouter(prefix="/api/orientador")
interno = APIRouter(prefix="/internal")
panel = APIRouter(prefix="/panel/api")
_basic = HTTPBasic()
_rate: dict[str, list[float]] = {}
_rate_lock = threading.Lock()

ID_RE = re.compile(r"^orienta-[0-9a-f]{24}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _doc(id: str) -> dict:
    if not ID_RE.match(id):
        raise HTTPException(404, "Sesión no encontrada")
    d = db.obtener(id)
    if not d:
        raise HTTPException(404, "Sesión no encontrada")
    return d


def _auto_recomendar(d: dict) -> str | None:
    """Cuando ya están las 7 respuestas, calcula la recomendación sin esperar al agente."""
    if d.get("resultado") or _faltan(d):
        return None
    d["resultado"] = motor.recomendar(d)
    if d["resultado"]["carreras"]:
        d["enfoque"] = d["resultado"]["carreras"][0]["id"]
    return motor.resumen_para_voz(d["resultado"])


def _recalcular(d: dict) -> None:
    if d.get("resultado"):
        enfoque = d.get("enfoque")
        d["resultado"] = motor.recomendar(d)
        ids = [c["id"] for c in d["resultado"]["carreras"] + d["resultado"]["extras"]]
        if enfoque not in ids:
            d["enfoque"] = ids[0] if ids else None


def vista_publica(d: dict) -> dict:
    v = {k: d.get(k) for k in ("modo", "id", "estado", "respuestas", "ubicacion", "resultado", "enfoque", "calificaciones",
                               "carrera_elegida", "ui", "cita", "version", "estudiante", "idioma", "creada")}
    v["respuestas"] = {k: {kk: vv for kk, vv in (r or {}).items() if kk != "alerta_bienestar"} for k, r in (d.get("respuestas") or {}).items()}
    v["correo_estado"] = (d.get("correo_psicologo") or {}).get("estado")
    v["modo"] = d.get("modo") or "eleccion"
    if v["modo"] == "permanencia":
        caso = dict(d.get("caso") or {})
        caso.pop("alerta_bienestar", None)
        v["caso"] = caso or None
        t = d.get("test")
        if t:
            v["test"] = {"carrera_id": t.get("carrera_id"), "respuestas": t["respuestas"], "sentimientos": t["sentimientos"],
                         "preguntas": [perm.pregunta_publica(p) for p in t["preguntas"]], "paso": perm.siguiente_paso(t)}
        else:
            v["test"] = None
        v["dictamen"] = d.get("dictamen")
    v["pendiente"] = _pendiente(d)
    pc = d.get("por_confirmar")
    v["por_confirmar"] = ({"tipo": pc["tipo"], "texto": pc["texto"], "numero": pc["datos"].get("numero"), "opcion": pc["datos"].get("opcion"),
                           "nivel": pc["datos"].get("nivel"), "valor": pc["datos"].get("valor")} if pc else None)
    return v


# ---------------------------------------------------------------------------
# Público (navegador)
# ---------------------------------------------------------------------------

def _ip(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (req.client.host if req.client else "?")


IDIOMAS = json.loads((motor.DATA / "idiomas.json").read_text(encoding="utf-8"))
TEXTOS = json.loads((motor.DATA / "preguntas.json").read_text(encoding="utf-8"))


def _txt(grupo: str, clave: str, idioma: str = "es") -> str:
    t = TEXTOS[grupo][clave]
    return t.get(idioma) or t["es"]


class NuevaSesion(BaseModel):
    idioma: str = "es"
    modo: Literal["eleccion", "permanencia"] = "eleccion"


class Idioma(BaseModel):
    idioma: str


@publico.post("/token")
def crear_sesion(req: Request, body: Optional[NuevaSesion] = None):
    idioma = (body.idioma if body else "es")
    modo = (body.modo if body else "eleccion")
    if idioma not in IDIOMAS:
        idioma = "es"
    if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        raise HTTPException(500, "Faltan credenciales de LiveKit")
    ip, ahora = _ip(req), time.time()
    with _rate_lock:
        hist = [t for t in _rate.get(ip, []) if ahora - t < 3600]
        if len(hist) >= LIMITE_SESIONES_HORA:
            raise HTTPException(429, "Demasiadas sesiones desde esta conexión. Intenta más tarde.")
        hist.append(ahora)
        _rate[ip] = hist
    sid = f"orienta-{secrets.token_hex(12)}"
    d = db.crear(sid)
    d["idioma"] = idioma
    d["modo"] = modo
    db.guardar(d)
    identity = f"estudiante-{secrets.token_hex(3)}"
    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity).with_name("Estudiante").with_ttl(timedelta(minutes=60))
        .with_metadata(json.dumps({"idioma": idioma, "modo": modo}))
        .with_grants(api.VideoGrants(room_join=True, room=sid, can_publish=True, can_subscribe=True, can_publish_data=True))
        .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=ORIENTADOR_AGENT)]))
        .to_jwt()
    )
    return {"serverUrl": LIVEKIT_URL, "token": token, "sesion": sid, "identity": identity, "idioma": idioma, "modo": modo}


@publico.post("/sesiones/{sid}/idioma")
def cambiar_idioma(sid: str, body: Idioma):
    if body.idioma not in IDIOMAS:
        raise HTTPException(400, "Idioma no disponible")
    d = _doc(sid)
    d["idioma"] = body.idioma
    db.guardar(d)
    return vista_publica(d)


@publico.get("/catalogo")
def catalogo():
    return {"vocabulario": motor.VOCAB, "oportunidades": motor.OPORT_POR_ID, "costos": motor.ETIQUETA_COSTO, "idiomas": IDIOMAS, "motivos": perm.MOTIVOS}


@publico.get("/sesiones/{sid}")
def ver_sesion(sid: str):
    return vista_publica(_doc(sid))


class Enfoque(BaseModel):
    carrera: str


@publico.post("/sesiones/{sid}/enfoque")
def enfoque_publico(sid: str, body: Enfoque):
    d = _doc(sid)
    if body.carrera not in motor.CARRERAS_POR_ID:
        raise HTTPException(400, "Carrera desconocida")
    d["enfoque"] = body.carrera
    db.guardar(d)
    return vista_publica(d)


class Calificacion(BaseModel):
    carrera: str
    puntaje: int = Field(ge=1, le=5)


@publico.post("/sesiones/{sid}/calificacion")
def calificar(sid: str, body: Calificacion):
    d = _doc(sid)
    if body.carrera not in motor.CARRERAS_POR_ID:
        raise HTTPException(400, "Carrera desconocida")
    d.setdefault("calificaciones", {})[body.carrera] = body.puntaje
    _recalcular(d)
    d["enfoque"] = body.carrera
    db.guardar(d)
    return vista_publica(d)


class Gps(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


@publico.post("/sesiones/{sid}/gps")
def gps(sid: str, body: Gps):
    d = _doc(sid)
    u = d.get("ubicacion") or {}
    u.update(lat=body.lat, lng=body.lng, precision="gps", fuente="ubicación del dispositivo")
    d["ubicacion"] = u
    _recalcular(d)
    db.guardar(d)
    return vista_publica(d)


@publico.post("/sesiones/{sid}/recomendar")
def recomendar_publico(sid: str):
    d = _doc(sid)
    r = d.get("respuestas") or {}
    if len([k for k in ("disfruta", "clase", "descripcion", "ambiente", "economia") if k in r]) < 4 or not d.get("ubicacion"):
        raise HTTPException(400, "Aún faltan respuestas para calcular tus resultados")
    d["resultado"] = motor.recomendar(d)
    if d["resultado"]["carreras"]:
        d["enfoque"] = d["resultado"]["carreras"][0]["id"]
    db.guardar(d)
    return vista_publica(d)


@publico.get("/horarios")
def horarios():
    st = graph.estado()
    try:
        slots = graph.horarios_disponibles()
    except Exception as e:
        log.warning("horarios: %s", e)
        slots = []
    return {"horarios": slots, "teams": st["calendario"] and bool(st["psicologo"]), "duracion_min": graph.CITA_MIN}


class Cita(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)
    correo: Optional[str] = Field(default=None, max_length=120)
    inicio: str


@publico.post("/sesiones/{sid}/cita")
def agendar(sid: str, body: Cita, bg: BackgroundTasks):
    d = _doc(sid)
    correo_est = (body.correo or "").strip() or None
    if correo_est and not EMAIL_RE.match(correo_est):
        raise HTTPException(400, "Correo no válido")
    try:
        inicio = datetime.fromisoformat(body.inicio)
    except ValueError:
        raise HTTPException(400, "Horario no válido")
    d["estudiante"] = {"nombre": body.nombre.strip(), "correo": correo_est}
    try:
        r = graph.crear_reunion(inicio.isoformat(), body.nombre.strip(), correo_est, sid)
        d["cita"] = {"estado": "agendada", **r}
    except Exception as e:
        log.warning("No se pudo crear la reunión: %s", e)
        d["cita"] = {"estado": "pendiente", "inicio": inicio.isoformat(timespec="minutes"), "error": str(e)[:300]}
    d.setdefault("ui", {})["mostrar_agenda"] = True
    d["correo_cita"] = {"estado": "enviando"}
    db.guardar(d)
    bg.add_task(_enviar_cita, sid)
    return vista_publica(d)


@publico.get("/video/{carrera}")
def video(carrera: str):
    c = motor.CARRERAS_POR_ID.get(carrera)
    if not c:
        raise HTTPException(404, "Carrera desconocida")
    buscar = "https://www.youtube.com/results?search_query=" + quote_plus(c["video"]["busqueda"])
    ids = list(c["video"].get("youtube_ids") or [])
    cached = db.video_get(carrera)
    if cached:
        ids += [i for i in cached.get("ids", []) if i not in ids]
    elif YOUTUBE_API_KEY:
        try:
            r = httpx.get("https://www.googleapis.com/youtube/v3/search", timeout=8, params={
                "part": "snippet", "type": "video", "videoEmbeddable": "true", "safeSearch": "strict",
                "relevanceLanguage": "es", "regionCode": "HN", "maxResults": 5, "q": c["video"]["busqueda"], "key": YOUTUBE_API_KEY})
            r.raise_for_status()
            extra = [it["id"]["videoId"] for it in r.json().get("items", [])]
            db.video_set(carrera, {"ids": extra})
            ids += [i for i in extra if i not in ids]
        except Exception as e:
            log.warning("YouTube API: %s", e)
    return {"ids": ids, "buscar_url": buscar}


# ---------------------------------------------------------------------------
# Interno (agente LiveKit)
# ---------------------------------------------------------------------------

def _auth_interna(x_internal_token: str = Header(default="")):
    if not INTERNAL_TOKEN or not secrets.compare_digest(x_internal_token, INTERNAL_TOKEN):
        raise HTTPException(401, "No autorizado")


PREGUNTAS = ["disfruta", "clase", "descripcion", "ambiente", "economia", "ubicacion", "extra"]


def _faltan(d: dict) -> list[str]:
    r = d.get("respuestas") or {}
    return [p for p in PREGUNTAS if (p == "ubicacion" and not d.get("ubicacion")) or (p != "ubicacion" and p not in r)]


class Respuesta(BaseModel):
    pregunta: Literal["disfruta", "clase", "descripcion", "ambiente", "economia", "extra"]
    texto: str = Field(max_length=2000)
    etiquetas: list[str] = []
    nivel: Optional[Literal["baja", "media", "alta"]] = None
    necesita_trabajar: Optional[bool] = None
    internet: Optional[bool] = None
    computadora: Optional[bool] = None
    alerta_bienestar: Optional[bool] = None
    puede_mudarse: Optional[bool] = None


@interno.post("/sesiones/{sid}/respuesta", dependencies=[Depends(_auth_interna)])
def guardar_respuesta(sid: str, body: Respuesta, bg: BackgroundTasks):
    d = _doc(sid)
    reg, rec = _aplicar_respuesta(d, body)
    _avisar_alerta(d, body.texto, bg)
    db.guardar(d)
    return {"ok": True, "guardado": reg, "faltan": _faltan(d), "recomendacion": rec}


def _aplicar_respuesta(d: dict, body: "Respuesta") -> tuple[dict, str | None]:
    reg = {"texto": body.texto.strip()}
    dim = motor.PREGUNTA_DIMENSION.get(body.pregunta)
    if dim:
        reg["etiquetas"] = motor.limpiar_etiquetas(dim, body.etiquetas)
    if body.pregunta == "economia":
        reg.update(nivel=body.nivel or "media", necesita_trabajar=body.necesita_trabajar, internet=body.internet, computadora=body.computadora)
    if body.pregunta == "extra":
        reg.update(alerta_bienestar=bool(body.alerta_bienestar), puede_mudarse=body.puede_mudarse)
    d.setdefault("respuestas", {})[body.pregunta] = reg
    _recalcular(d)
    return reg, _auto_recomendar(d)


class Ubicacion(BaseModel):
    pais: str = "Honduras"
    departamento: Optional[str] = None
    municipio: Optional[str] = None
    colonia: Optional[str] = None
    zona: Literal["urbana", "rural", "no_sabe"] = "no_sabe"


@interno.post("/sesiones/{sid}/ubicacion", dependencies=[Depends(_auth_interna)])
def guardar_ubicacion(sid: str, body: Ubicacion):
    d = _doc(sid)
    g = geo.geocodificar(body.pais, body.departamento, body.municipio, body.colonia)
    d["ubicacion"] = {**body.model_dump(), **g}
    _recalcular(d)
    rec = _auto_recomendar(d)
    db.guardar(d)
    return {"ok": True, "precision": g["precision"], "encontrado": g.get("display"), "faltan": _faltan(d), "recomendacion": rec}


@interno.post("/sesiones/{sid}/recomendar", dependencies=[Depends(_auth_interna)])
def recomendar(sid: str):
    d = _doc(sid)
    d["resultado"] = motor.recomendar(d)
    if d["resultado"]["carreras"]:
        d["enfoque"] = d["resultado"]["carreras"][0]["id"]
    db.guardar(d)
    return {"ok": True, "texto": motor.resumen_para_voz(d["resultado"]), "faltan": _faltan(d)}


def _texto_carrera(d: dict, cid: str) -> str:
    todas = (d.get("resultado") or {}).get("carreras", []) + (d.get("resultado") or {}).get("extras", [])
    c = next((x for x in todas if x["id"] == cid), None)
    if not c:
        eco = (d.get("respuestas") or {}).get("economia") or {}
        base = motor.CARRERAS_POR_ID[cid]
        c = motor._detalle_carrera(base, d.get("ubicacion"), eco, 0, [], 0, 0)
    s = c.get("sede_accesible_cercana") or c.get("sede_publica_cercana")
    primero = ", ".join(c["temario"][0]["materias"][:3]) if c.get("temario") else ""
    donde = f"{s['siglas']} en {s['ciudad']} a unos {s['distancia_km']} kilómetros" if s and s.get("distancia_km") is not None else "ver opciones a distancia"
    return (f"{c['nombre']}: {c['descripcion']} Dura {c['duracion']}. Primer año: {primero}. "
            f"Campo laboral: {', '.join(c['campo_laboral'][:3])}. Sede sugerida: {donde}.")


@interno.post("/sesiones/{sid}/enfoque", dependencies=[Depends(_auth_interna)])
def enfoque_interno(sid: str, body: Enfoque):
    d = _doc(sid)
    if body.carrera not in motor.CARRERAS_POR_ID:
        raise HTTPException(400, f"Carrera desconocida. Opciones: {', '.join(motor.CARRERAS_POR_ID)}")
    d["enfoque"] = body.carrera
    db.guardar(d)
    return {"ok": True, "texto": _texto_carrera(d, body.carrera)}


@interno.post("/sesiones/{sid}/elegir", dependencies=[Depends(_auth_interna)])
def elegir(sid: str, body: Enfoque):
    d = _doc(sid)
    if body.carrera not in motor.CARRERAS_POR_ID:
        raise HTTPException(400, "Carrera desconocida")
    d["carrera_elegida"] = body.carrera
    d["enfoque"] = body.carrera
    db.guardar(d)
    return {"ok": True, "texto": _texto_carrera(d, body.carrera)}


@interno.post("/sesiones/{sid}/agenda", dependencies=[Depends(_auth_interna)])
def mostrar_agenda(sid: str):
    d = _doc(sid)
    d.setdefault("ui", {})["mostrar_agenda"] = True
    db.guardar(d)
    st = graph.estado()
    return {"ok": True, "teams_disponible": st["calendario"] and bool(st["psicologo"])}


_correo_lock = threading.Lock()


def _enviar(d: dict, campo: str, asunto: str, html: str, importancia: str = "normal") -> None:
    """Envía un correo (Resend o Graph) y guarda en el documento si salió o quedó pendiente."""
    try:
        r = mailer.enviar(asunto, html, importancia)
        res = {"estado": "enviado", "fecha": db.ahora(), **r}
    except Exception as e:
        log.warning("Correo %s pendiente: %s", campo, e)
        res = {"estado": "pendiente", "error": str(e)[:300], "fecha": db.ahora()}
    # Se relee el documento: mientras se enviaba pudieron llegar respuestas nuevas del agente
    with _correo_lock:
        actual = db.obtener(d["id"]) or d
        actual[campo] = res
        db.guardar(actual)


def _hay_alerta(d: dict) -> bool:
    return bool((d.get("respuestas", {}).get("extra") or {}).get("alerta_bienestar") or (d.get("caso") or {}).get("alerta_bienestar"))


def _enviar_contexto(sid: str) -> None:
    d = db.obtener(sid)
    if d:
        _enviar(d, "correo_psicologo", correo.asunto(d), correo.html_contexto(d), "high" if _hay_alerta(d) else "normal")


def _enviar_cita(sid: str) -> None:
    d = db.obtener(sid)
    if d and d.get("cita"):
        _enviar(d, "correo_cita", correo.asunto_cita(d), correo.html_cita(d))


def _enviar_alerta(sid: str, texto: str | None) -> None:
    d = db.obtener(sid)
    if d:
        _enviar(d, "correo_alerta", correo.asunto_alerta(d), correo.html_alerta(d, texto), "high")


def _avisar_alerta(d: dict, texto: str | None, bg: BackgroundTasks) -> None:
    """Primera vez que aparece una alerta de bienestar: aviso inmediato por correo (una sola vez)."""
    if _hay_alerta(d) and not d.get("correo_alerta"):
        d["correo_alerta"] = {"estado": "enviando"}
        bg.add_task(_enviar_alerta, d["id"], texto)


class Finalizar(BaseModel):
    resumen: str = Field(max_length=4000)
    sugerencias: Optional[str] = Field(default=None, max_length=2000)


@interno.post("/sesiones/{sid}/finalizar", dependencies=[Depends(_auth_interna)])
def finalizar(sid: str, body: Finalizar, bg: BackgroundTasks):
    d = _doc(sid)
    d["resumen_agente"] = body.resumen
    d["sugerencias_agente"] = body.sugerencias
    d["estado"] = "finalizada"
    db.guardar(d)
    bg.add_task(_enviar_contexto, sid)
    return {"ok": True}


@interno.post("/sesiones/{sid}/cerrar", dependencies=[Depends(_auth_interna)])
def cerrar(sid: str, bg: BackgroundTasks):
    d = _doc(sid)
    if d.get("estado") == "en_curso":
        d["estado"] = "incompleta" if (len(d.get("respuestas") or {}) >= 2 or d.get("caso")) else "abandonada"
        db.guardar(d)
        if d["estado"] == "incompleta":
            bg.add_task(_enviar_contexto, sid)
    return {"ok": True, "estado": d["estado"]}


# ---------------------------------------------------------------------------
# Fabiola: ¿sigo en mi carrera? (modo permanencia)
# ---------------------------------------------------------------------------

ETAPA = {"basico": "básica", "intermedio": "intermedia", "avanzado": "avanzada"}


def _avance(d: dict) -> dict:
    """Siguiente paso del test y texto guía para la voz."""
    t = d["test"]
    paso = perm.siguiente_paso(t)
    if paso["tipo"] == "pregunta":
        return {"paso": "pregunta", "numero": paso["pregunta"]["numero"], "texto": perm.texto_pregunta_voz(paso["pregunta"])}
    if paso["tipo"] == "sentimiento":
        return {"paso": "sentimiento", "nivel": paso["nivel"],
                "texto": f"Terminó la etapa {ETAPA[paso['nivel']]}. Pregúntale cómo se sintió en esta etapa, del uno al cinco y por qué."}
    if not d.get("dictamen"):
        d["dictamen"] = perm.dictamen(d.get("caso") or {}, t)
    dic = d["dictamen"]
    niveles = ", ".join(f"{perm.NOMBRE_NIVEL[n].lower()} {v['aciertos']} de {v['total']}" for n, v in dic["por_nivel"].items())
    return {"paso": "dictamen", "texto": (
        f"Test terminado. Puntaje del test {dic['puntaje_test']} de cien ({niveles}). Índice de permanencia {dic['indice']} de cien. "
        f"Dictamen: {dic['titulo']}. {dic['texto']} Recomendaciones en pantalla: " + " ".join(r["texto"] for r in dic["recomendaciones"][:3]))}


class Caso(BaseModel):
    carrera_nombre: Optional[str] = Field(default=None, max_length=120)
    carrera_id: Optional[str] = None
    universidad: Optional[str] = Field(default=None, max_length=120)
    anio: Optional[int] = Field(default=None, ge=1, le=10)
    motivos: list[str] = []
    satisfaccion: Optional[int] = Field(default=None, ge=1, le=5)
    texto: Optional[str] = Field(default=None, max_length=2000)
    alerta_bienestar: Optional[bool] = None


def _faltan_caso(caso: dict) -> list[str]:
    out = []
    omitidas = set(caso.get("omitidas") or [])
    if not caso.get("carrera_nombre") and not caso.get("carrera_id"):
        out.append("carrera")
    if not caso.get("motivos") and not caso.get("texto") and "motivos" not in omitidas:
        out.append("motivos")
    if not caso.get("satisfaccion") and "satisfaccion" not in omitidas:
        out.append("satisfaccion")
    return out


# ---------------------------------------------------------------------------
# Pregunta pendiente y botón "Saltar pregunta"
# ---------------------------------------------------------------------------

def _pendiente(d: dict) -> dict | None:
    """La pregunta que el estudiante tiene por contestar ahora (para mostrarla y poder saltarla)."""
    idioma = d.get("idioma") if d.get("idioma") in ("es", "en") else "es"
    if (d.get("modo") or "eleccion") == "eleccion":
        if d.get("resultado"):
            return None
        faltan = _faltan(d)
        if not faltan:
            return None
        k = faltan[0]
        return {"clave": k, "tipo": "entrevista", "texto": _txt("eleccion", k, idioma), "saltable": True}
    caso = d.get("caso") or {}
    t = d.get("test")
    if not t:
        faltan = _faltan_caso(caso)
        if not faltan:
            return None
        k = faltan[0]
        return {"clave": k, "tipo": "caso", "texto": _txt("caso", k, idioma), "saltable": k != "carrera",
                "motivo_no_saltable": "Tu carrera es necesaria para armar tu test." if k == "carrera" else None}
    paso = perm.siguiente_paso(t)
    if paso["tipo"] == "pregunta":
        q = paso["pregunta"]
        return {"clave": f"test:{q['numero']}", "tipo": "test", "numero": q["numero"], "nivel": q["nivel"],
                "texto": q["pregunta"], "saltable": True}
    if paso["tipo"] == "sentimiento":
        etapa = TEXTOS["etapa"][idioma][paso["nivel"]]
        return {"clave": f"sentimiento:{paso['nivel']}", "tipo": "sentimiento", "nivel": paso["nivel"],
                "texto": TEXTOS["sentimiento"][idioma].format(etapa=etapa), "saltable": True}
    return None


class Saltar(BaseModel):
    clave: Optional[str] = Field(default=None, max_length=40)


@publico.post("/sesiones/{sid}/saltar")
def saltar(sid: str, body: Optional[Saltar] = None):
    """Marca la pregunta pendiente como omitida y avanza a la siguiente."""
    d = _doc(sid)
    p = _pendiente(d)
    if not p:
        raise HTTPException(409, "No hay una pregunta pendiente para saltar")
    if body and body.clave and body.clave != p["clave"]:
        # La pregunta ya cambió (por ejemplo, respondió por voz): no se salta otra por error
        return {"ok": False, "motivo": "La pregunta ya cambió", "vista": vista_publica(d), "siguiente": p}
    if not p["saltable"]:
        raise HTTPException(400, p.get("motivo_no_saltable") or "Esta pregunta no se puede saltar")
    out: dict = {"ok": True, "saltada": p}
    d.pop("por_confirmar", None)
    k = p["clave"]
    if p["tipo"] == "entrevista":
        if k == "ubicacion":
            d["ubicacion"] = {"omitida": True, "pais": None, "departamento": None, "municipio": None, "colonia": None,
                              "zona": "no_sabe", "lat": None, "lng": None, "precision": "omitida"}
        else:
            reg: dict = {"texto": "(omitida)", "omitida": True}
            if motor.PREGUNTA_DIMENSION.get(k):
                reg["etiquetas"] = []
            if k == "economia":
                reg.update(nivel=None, necesita_trabajar=None, internet=None, computadora=None)
            if k == "extra":
                reg.update(alerta_bienestar=False, puede_mudarse=None)
            d.setdefault("respuestas", {})[k] = reg
        _recalcular(d)
        out["recomendacion"] = _auto_recomendar(d)
    elif p["tipo"] == "caso":
        caso = dict(d.get("caso") or {})
        caso["omitidas"] = sorted(set(caso.get("omitidas") or []) | {k})
        d["caso"] = caso
        if not _faltan_caso(caso) and not d.get("test"):
            if caso.get("carrera_id"):
                d["test"] = perm.crear_test(caso["carrera_id"])
            else:
                out["necesita_preguntas"] = True
    elif p["tipo"] == "test":
        out["resultado"] = perm.omitir(d["test"], p["numero"])
    elif p["tipo"] == "sentimiento":
        d["test"]["sentimientos"][p["nivel"]] = {"valor": None, "texto": "", "omitida": True}
    if d.get("test"):
        if d.get("dictamen"):
            d["dictamen"] = perm.dictamen(d.get("caso") or {}, d["test"])
        out["avance"] = _avance(d)
    pre = (TEXTOS["salto"]["es"] + " ", TEXTOS["salto"]["en"] + " ")
    out.update(_voz(d, pre[0], pre[1], rec=out.get("recomendacion"), intro_test=p["tipo"] == "caso" and bool(d.get("test"))))
    db.guardar(d)
    out["siguiente"] = _pendiente(d)
    out["vista"] = vista_publica(d)
    return out


@interno.post("/sesiones/{sid}/caso", dependencies=[Depends(_auth_interna)])
def guardar_caso(sid: str, body: Caso, bg: BackgroundTasks):
    """Guarda el caso de forma incremental: solo actualiza lo que viene con valor."""
    d = _doc(sid)
    caso = _aplicar_caso(d, body.model_dump())
    _avisar_alerta(d, body.texto, bg)
    db.guardar(d)
    return {"ok": True, "faltan": _faltan_caso(caso), "banco_disponible": bool(caso.get("carrera_id")),
            "test_iniciado": bool(d.get("test"))}


def _aplicar_caso(d: dict, nuevo: dict) -> dict:
    caso = dict(d.get("caso") or {})
    for k, v in nuevo.items():
        if k == "motivos":
            caso["motivos"] = sorted(set(caso.get("motivos") or []) | {m for m in v if m in perm.MOTIVOS})
        elif k == "texto" and v:
            caso["texto"] = ((caso.get("texto") or "") + " " + v).strip()
        elif k == "alerta_bienestar":
            caso["alerta_bienestar"] = bool(caso.get("alerta_bienestar") or v)
        elif v not in (None, ""):
            caso[k] = v
    if caso.get("carrera_id") not in motor.CARRERAS_POR_ID:
        caso["carrera_id"] = None
    if caso.get("carrera_id") and not caso.get("carrera_nombre"):
        caso["carrera_nombre"] = motor.CARRERAS_POR_ID[caso["carrera_id"]]["nombre"]
    d["caso"] = caso
    if d.get("dictamen") and d.get("test"):
        d["dictamen"] = perm.dictamen(caso, d["test"])
    return caso


class PreguntaPersonalizada(BaseModel):
    nivel: Literal["basico", "intermedio", "avanzado"]
    pregunta: str = Field(max_length=300)
    opciones: list[str]
    correcta: int = Field(ge=0, le=3)


class IniciarTest(BaseModel):
    preguntas: Optional[list[PreguntaPersonalizada]] = None


@interno.post("/sesiones/{sid}/test/iniciar", dependencies=[Depends(_auth_interna)])
def iniciar_test(sid: str, body: IniciarTest):
    d = _doc(sid)
    caso = d.get("caso") or {}
    if not d.get("test"):
        if caso.get("carrera_id"):
            d["test"] = perm.crear_test(caso["carrera_id"])
        elif body.preguntas:
            d["test"] = perm.crear_test(None, [p.model_dump() for p in body.preguntas])
            if len(d["test"]["preguntas"]) < 3:
                d["test"] = None
                raise HTTPException(400, "Se necesitan al menos tres preguntas válidas de cuatro opciones")
        else:
            return {"ok": False, "necesita_preguntas": True,
                    "texto": "La carrera no está en el banco: crea seis preguntas propias, dos por nivel, y vuelve a llamar."}
    av = _avance(d)
    out = {"ok": True, **av, **_voz(d, intro_test=True)}
    db.guardar(d)
    return out


class Respuesta_Test(BaseModel):
    numero: int = Field(ge=1, le=20)
    opcion: str = Field(min_length=1, max_length=2)


def _responder(d: dict, numero: int, opcion: str) -> dict:
    if not d.get("test"):
        raise HTTPException(400, "El test no ha iniciado")
    try:
        r = perm.responder(d["test"], numero, opcion)
    except ValueError as e:
        raise HTTPException(400, str(e))
    av = _avance(d)
    db.guardar(d)
    return {"ok": True, "resultado": r, **av}


@interno.post("/sesiones/{sid}/test/responder", dependencies=[Depends(_auth_interna)])
def responder_interno(sid: str, body: Respuesta_Test):
    return _responder(_doc(sid), body.numero, body.opcion)


@publico.post("/sesiones/{sid}/test/responder")
def responder_publico(sid: str, body: Respuesta_Test):
    d = _doc(sid)
    out = _responder(d, body.numero, body.opcion)
    return {"vista": vista_publica(d), **out}


class Sentimiento(BaseModel):
    nivel: Literal["basico", "intermedio", "avanzado"]
    valor: int = Field(ge=1, le=5)
    texto: str = Field(default="", max_length=1000)


def _sentimiento(d: dict, body: Sentimiento) -> dict:
    if not d.get("test"):
        raise HTTPException(400, "El test no ha iniciado")
    d["test"]["sentimientos"][body.nivel] = {"valor": body.valor, "texto": body.texto}
    if d.get("dictamen"):
        d["dictamen"] = perm.dictamen(d.get("caso") or {}, d["test"])
    av = _avance(d)
    db.guardar(d)
    return {"ok": True, **av}


@interno.post("/sesiones/{sid}/test/sentimiento", dependencies=[Depends(_auth_interna)])
def sentimiento_interno(sid: str, body: Sentimiento):
    return _sentimiento(_doc(sid), body)


@publico.post("/sesiones/{sid}/test/sentimiento")
def sentimiento_publico(sid: str, body: Sentimiento):
    d = _doc(sid)
    out = _sentimiento(d, body)
    return {"vista": vista_publica(d), **out}


# ---------------------------------------------------------------------------
# Panel (psicólogo / coordinación)
# ---------------------------------------------------------------------------

def _auth_panel(cred: HTTPBasicCredentials = Depends(_basic)):
    ok = PANEL_PASSWORD and secrets.compare_digest(cred.username, PANEL_USER) and secrets.compare_digest(cred.password, PANEL_PASSWORD)
    if not ok:
        raise HTTPException(401, "No autorizado", headers={"WWW-Authenticate": "Basic"})


@panel.get("/sesiones", dependencies=[Depends(_auth_panel)])
def panel_listar(departamento: str = "", nivel_economico: str = "", zona: str = "", alerta_bienestar: str = "",
                 estado: str = "", carrera_top: str = "", carrera_elegida: str = "", q: str = "", modo: str = "", dictamen: str = ""):
    filas = db.listar(dict(departamento=departamento, nivel_economico=nivel_economico, zona=zona,
                           alerta_bienestar=alerta_bienestar, estado=estado, carrera_top=carrera_top,
                           carrera_elegida=carrera_elegida, q=q, modo=modo, dictamen=dictamen))
    nombres = {k: v["nombre"] for k, v in motor.CARRERAS_POR_ID.items()}
    return {
        "filas": filas,
        "opciones": {"departamento": db.valores_distintos("departamento"), "carrera_top": db.valores_distintos("carrera_top"),
                     "carrera_elegida": db.valores_distintos("carrera_elegida")},
        "carreras": nombres,
        "graph": graph.estado(),
        "correo": mailer.estado(),
    }


@panel.get("/sesiones/{sid}", dependencies=[Depends(_auth_panel)])
def panel_detalle(sid: str):
    d = _doc(sid)
    return {"doc": d, "html": correo.html_contexto(d)}


@panel.post("/sesiones/{sid}/reintentar", dependencies=[Depends(_auth_panel)])
def panel_reintentar(sid: str):
    d = _doc(sid)
    cita = d.get("cita") or {}
    if cita.get("estado") == "pendiente":
        try:
            r = graph.crear_reunion(cita["inicio"], (d.get("estudiante") or {}).get("nombre") or "Estudiante",
                                    (d.get("estudiante") or {}).get("correo"), sid)
            d["cita"] = {"estado": "agendada", **r}
        except Exception as e:
            d["cita"]["error"] = str(e)[:300]
        db.guardar(d)
    if (d.get("correo_psicologo") or {}).get("estado") != "enviado" and d.get("estado") in ("finalizada", "incompleta"):
        _enviar_contexto(sid)
    d = db.obtener(sid)
    if d.get("cita") and (d.get("correo_cita") or {}).get("estado") != "enviado":
        _enviar_cita(sid)
    d = db.obtener(sid)
    if _hay_alerta(d) and (d.get("correo_alerta") or {}).get("estado") != "enviado":
        _enviar_alerta(sid, (d.get("respuestas", {}).get("extra") or {}).get("texto") or (d.get("caso") or {}).get("texto"))
    return {"doc": db.obtener(sid)}


@panel.post("/correo/prueba", dependencies=[Depends(_auth_panel)])
def panel_correo_prueba():
    try:
        r = mailer.enviar("Prueba de correo – Orienta", correo.html_prueba())
        return {"ok": True, **r}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300], "estado": mailer.estado()}


@panel.get("/export.csv", dependencies=[Depends(_auth_panel)])
def panel_csv(departamento: str = "", nivel_economico: str = "", zona: str = "", alerta_bienestar: str = "", estado: str = "", q: str = ""):
    filas = db.listar(dict(departamento=departamento, nivel_economico=nivel_economico, zona=zona,
                           alerta_bienestar=alerta_bienestar, estado=estado, q=q), limite=100000)
    buf = io.StringIO()
    if filas:
        w = csv.DictWriter(buf, fieldnames=list(filas[0].keys()))
        w.writeheader()
        w.writerows(filas)
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=entrevistas.csv"})


@panel.get("/ping", dependencies=[Depends(_auth_panel)])
def panel_ping():
    return PlainTextResponse("ok")


# ---------------------------------------------------------------------------
# Confirmaciones: cada respuesta de selección se propone, el estudiante la confirma
# y solo entonces se guarda y se pasa a la siguiente pregunta.
# Además el servidor arma el texto exacto que la orientadora debe decir (voz).
# ---------------------------------------------------------------------------

NUM = {"es": ["cero", "uno", "dos", "tres", "cuatro", "cinco"], "en": ["zero", "one", "two", "three", "four", "five"]}
ORDINAL = {"es": ["", "primer", "segundo", "tercer", "cuarto", "quinto", "sexto", "séptimo", "octavo", "noveno", "décimo"],
           "en": ["", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"]}
NIVEL_VOZ = {"basico": "básico", "intermedio": "intermedio", "avanzado": "avanzado"}
CONFIRMA = {"es": "¿Es correcto?", "en": "Is that right?"}


def _leer_pregunta_test(t: dict, q: dict) -> str:
    """Pregunta del test con sus opciones, una por frase, para leerla con pausas."""
    total = len(t["preguntas"])
    ops = " ".join(f"Opción {L}: {str(o).strip().rstrip('.')}." for L, o in zip("ABCD", q["opciones"]))
    preg = q["pregunta"].strip()
    if not preg.endswith(("?", ".")):
        preg += "."
    return f"Pregunta {q['numero']} de {total}, nivel {NIVEL_VOZ[q['nivel']]}. {preg} {ops} ¿Cuál opción eliges?"


def _intro_test(t: dict) -> str:
    return (f"Ahora viene un test corto de {len(t['preguntas'])} preguntas en tres etapas: básica, intermedia y avanzada. "
            "Puedes responder diciendo la letra o tocándola en la pantalla. ")


def _voz(d: dict, pre_es: str = "", pre_en: str = "", rec: str | None = None, intro_test: bool = False) -> dict:
    """Qué debe decir la orientadora ahora. voz/voz_en: texto exacto (None = lo arma el LLM).
    explicar: el LLM debe explicar resultados (recomendacion, dictamen) o crear el test (crear_test)."""
    pc = d.get("por_confirmar")
    if pc:
        en = (pre_en + pc["texto_en"]) if pc.get("texto_en") else None
        return {"voz": (pre_es + pc["texto"]).strip(), "voz_en": en and en.strip(), "por_confirmar": pc, "explicar": None}
    out = {"voz": None, "voz_en": None, "por_confirmar": None, "explicar": None}
    if (d.get("modo") or "eleccion") == "eleccion":
        if rec:
            return {**out, "voz": pre_es.strip() or None, "voz_en": pre_en.strip() or None, "explicar": "recomendacion", "recomendacion": rec}
        p = _pendiente(d)
        if p:
            out.update(voz=pre_es + _txt("eleccion", p["clave"], "es"), voz_en=pre_en + _txt("eleccion", p["clave"], "en"))
        return out
    caso, t = d.get("caso") or {}, d.get("test")
    if not t:
        faltan = _faltan_caso(caso)
        if faltan:
            out.update(voz=pre_es + _txt("caso", faltan[0], "es"), voz_en=pre_en + _txt("caso", faltan[0], "en"))
        else:
            out.update(voz=pre_es.strip() or None, explicar="crear_test")
        return out
    paso = perm.siguiente_paso(t)
    intro = _intro_test(t) if intro_test else ""
    if paso["tipo"] == "pregunta":
        out.update(voz=pre_es + intro + _leer_pregunta_test(t, paso["pregunta"]))   # en: el LLM la traduce
    elif paso["tipo"] == "sentimiento":
        out.update(voz=pre_es + TEXTOS["sentimiento"]["es"].format(etapa=TEXTOS["etapa"]["es"][paso["nivel"]]),
                   voz_en=pre_en + TEXTOS["sentimiento"]["en"].format(etapa=TEXTOS["etapa"]["en"][paso["nivel"]]))
    else:
        av = _avance(d)
        out.update(voz=pre_es.strip() or None, explicar="dictamen", dictamen=av["texto"])
    return out


def _lista(items: list[str], y: str) -> str:
    items = [i for i in items if i]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" {y} " + items[-1] if items else ""


def _texto_confirmacion(d: dict, tipo: str, datos: dict) -> tuple[str, str | None]:
    """Frase de confirmación en español y en inglés (None si el LLM debe traducirla)."""
    if tipo == "test":
        q = next(p for p in d["test"]["preguntas"] if p["numero"] == datos["numero"])
        txt = str(q["opciones"]["ABCD".index(datos["opcion"])]).strip().rstrip(".")
        return f"Elegiste la opción {datos['opcion']}: {txt}. ¿Confirmas tu respuesta?", None
    if tipo == "sentimiento":
        v, n = datos["valor"], datos["nivel"]
        return (f"Te sentiste un {NUM['es'][v]} de cinco en la etapa {TEXTOS['etapa']['es'][n]}. {CONFIRMA['es']}",
                f"You felt a {NUM['en'][v]} out of five in the {TEXTOS['etapa']['en'][n]} stage. {CONFIRMA['en']}")
    if tipo == "economia":
        es = {"baja": "necesitarías una opción gratuita, con beca o de muy bajo costo", "media": "tu familia podría pagar una universidad pública",
              "alta": "tu familia podría pagar una universidad privada"}[datos.get("nivel") or "media"]
        en = {"baja": "you would need a free, scholarship or very low-cost option", "media": "your family could pay for a public university",
              "alta": "your family could pay for a private university"}[datos.get("nivel") or "media"]
        ex_es, ex_en = [], []
        if datos.get("necesita_trabajar"):
            ex_es.append("necesitarías trabajar mientras estudias"); ex_en.append("you would need to work while studying")
        if datos.get("internet") is False:
            ex_es.append("no tienes internet en casa"); ex_en.append("you don't have internet at home")
        if datos.get("computadora") is False:
            ex_es.append("no tienes computadora"); ex_en.append("you don't have a computer")
        return (f"Entonces, {_lista([es] + ex_es, 'y')}. {CONFIRMA['es']}", f"So, {_lista([en] + ex_en, 'and')}. {CONFIRMA['en']}")
    if tipo == "ubicacion":
        lugar = ", ".join(x for x in [datos.get("colonia"), datos.get("municipio"), datos.get("departamento"), datos.get("pais")] if x)
        rural_es = ", en zona rural" if datos.get("zona") == "rural" else ""
        rural_en = ", in a rural area" if datos.get("zona") == "rural" else ""
        return f"Entonces vives en {lugar}{rural_es}. {CONFIRMA['es']}", f"So you live in {lugar}{rural_en}. {CONFIRMA['en']}"
    if tipo == "caso":
        caso = {**(d.get("caso") or {}), **{k: v for k, v in datos.items() if v not in (None, "", [])}}
        es, en, traducible = [], [], True
        if any(datos.get(k) for k in ("carrera_nombre", "carrera_id", "universidad", "anio")):
            nombre = caso.get("carrera_nombre") or (motor.CARRERAS_POR_ID.get(caso.get("carrera_id") or "", {}).get("nombre"))
            f = f"estudias {nombre}" if nombre else "estudias"
            g = f"you study {nombre}" if nombre else "you study"
            if caso.get("universidad"):
                f += f" en {caso['universidad']}"; g += f" at {caso['universidad']}"
            if caso.get("anio") and 1 <= int(caso["anio"]) <= 10:
                f += f" y vas en {ORDINAL['es'][int(caso['anio'])]} año"; g += f" and you are in your {ORDINAL['en'][int(caso['anio'])]} year"
            es.append(f"Entonces {f}."); en.append(f"So {g}.")
        if datos.get("motivos"):
            ms = [perm.MOTIVOS.get(m, m).lower() for m in datos["motivos"]]
            es.append(f"Lo que te hace dudar es: {_lista(ms, 'y')}.")
            traducible = False
        if datos.get("satisfaccion"):
            v = int(datos["satisfaccion"])
            es.append(f"Le das un {NUM['es'][v]} de cinco a tu carrera."); en.append(f"You give your degree a {NUM['en'][v]} out of five.")
        es.append(CONFIRMA["es"]); en.append(CONFIRMA["en"])
        return " ".join(es), (" ".join(en) if traducible else None)
    raise ValueError(tipo)


def _clave_pregunta(tipo: str, datos: dict) -> tuple[str, str] | None:
    """Pregunta que se vuelve a hacer si el estudiante dice que no."""
    if tipo in ("economia", "ubicacion"):
        return ("eleccion", tipo)
    if tipo == "caso":
        if any(datos.get(k) for k in ("carrera_nombre", "carrera_id", "universidad", "anio")):
            return ("caso", "carrera")
        if datos.get("motivos"):
            return ("caso", "motivos")
        return ("caso", "satisfaccion")
    return None


class Propuesta(BaseModel):
    tipo: Literal["test", "sentimiento", "caso", "economia", "ubicacion"]
    datos: dict = {}


def _proponer(d: dict, body: Propuesta, bg: BackgroundTasks | None = None) -> dict:
    tipo, datos = body.tipo, dict(body.datos or {})
    if tipo == "test":
        t = d.get("test")
        paso = perm.siguiente_paso(t) if t else {"tipo": None}
        if paso["tipo"] != "pregunta":
            raise HTTPException(409, "No hay una pregunta del test pendiente")
        letra = str(datos.get("opcion") or "").strip().upper()[:1]
        if letra not in "ABCD" or not letra:
            raise HTTPException(400, "Opción inválida: A, B, C o D")
        datos = {"numero": paso["pregunta"]["numero"], "opcion": letra}      # siempre la pregunta actual
    elif tipo == "sentimiento":
        t = d.get("test")
        paso = perm.siguiente_paso(t) if t else {"tipo": None}
        if paso["tipo"] != "sentimiento":
            raise HTTPException(409, "No toca preguntar cómo se sintió")
        valor = int(datos.get("valor") or 0)
        if not 1 <= valor <= 5:
            raise HTTPException(400, "El valor va del uno al cinco")
        datos = {"nivel": paso["nivel"], "valor": valor, "texto": str(datos.get("texto") or "")[:1000]}
    elif tipo == "economia":
        datos.setdefault("texto", "")
        r = Respuesta(pregunta="economia", **{k: v for k, v in datos.items() if k in Respuesta.model_fields and k != "pregunta"})
        datos = r.model_dump()
    elif tipo == "ubicacion":
        u = Ubicacion(**{k: v for k, v in datos.items() if k in Ubicacion.model_fields})
        datos = u.model_dump()
    elif tipo == "caso":
        c = Caso(**{k: v for k, v in datos.items() if k in Caso.model_fields})
        datos = c.model_dump()
        # La alerta de bienestar y lo que contó se guardan de inmediato, sin esperar confirmación
        inmediato = {"texto": datos.pop("texto", None), "alerta_bienestar": datos.pop("alerta_bienestar", None)}
        if inmediato["texto"] or inmediato["alerta_bienestar"]:
            _aplicar_caso(d, inmediato)
            if bg:
                _avisar_alerta(d, inmediato["texto"], bg)
        datos = {k: v for k, v in datos.items() if v not in (None, "", [])}
        if not datos:      # no hay nada que confirmar
            db.guardar(d)
            return {"ok": True, "sin_confirmar": True, **_voz(d)}
    texto, texto_en = _texto_confirmacion(d, tipo, datos)
    d["por_confirmar"] = {"tipo": tipo, "datos": datos, "texto": texto, "texto_en": texto_en}
    db.guardar(d)
    return {"ok": True, **_voz(d)}


class Confirmacion(BaseModel):
    si: bool


def _confirmar(d: dict, si: bool, bg: BackgroundTasks | None = None) -> dict:
    pc = d.pop("por_confirmar", None)
    if not pc:
        raise HTTPException(409, "No hay nada pendiente de confirmar")
    tipo, datos = pc["tipo"], pc["datos"]
    if not si:
        if tipo == "test":
            out = _voz(d)   # se vuelve a la misma pregunta
            out.update(voz="De acuerdo. ¿Cuál opción eliges entonces? Puedes decir A, B, C o D.",
                       voz_en="Okay. Which option do you choose then? You can say A, B, C or D.")
        elif tipo == "sentimiento":
            out = _voz(d, "De acuerdo. ", "Okay. ")
        else:
            grupo, clave = _clave_pregunta(tipo, datos)
            out = {"voz": "De acuerdo, corrígeme por favor. " + _txt(grupo, clave, "es"),
                   "voz_en": "Okay, please correct me. " + _txt(grupo, clave, "en"), "por_confirmar": None, "explicar": None}
        db.guardar(d)
        return {"ok": True, "confirmado": False, **out}
    pre_es, pre_en, rec, intro, resultado = "Perfecto. ", "Great. ", None, False, None
    if tipo == "test":
        resultado = perm.responder(d["test"], datos["numero"], datos["opcion"])
        if resultado.get("correcta"):
            pre_es, pre_en = "¡Correcto! ", "Correct! "
        else:
            txt = str(resultado["texto_correcta"]).strip().rstrip(".")
            pre_es = f"No es la correcta. La respuesta correcta es la {resultado['letra_correcta']}: {txt}. "
            pre_en = f"That's not right. The correct answer is {resultado['letra_correcta']}: {txt}. "
    elif tipo == "sentimiento":
        d["test"]["sentimientos"][datos["nivel"]] = {"valor": datos["valor"], "texto": datos.get("texto", "")}
        pre_es, pre_en = "Gracias por contármelo. ", "Thanks for telling me. "
    elif tipo == "economia":
        _, rec = _aplicar_respuesta(d, Respuesta(**datos))
    elif tipo == "ubicacion":
        g = geo.geocodificar(datos.get("pais"), datos.get("departamento"), datos.get("municipio"), datos.get("colonia"))
        d["ubicacion"] = {**datos, **g}
        _recalcular(d)
        rec = _auto_recomendar(d)
    elif tipo == "caso":
        caso = _aplicar_caso(d, datos)
        if not _faltan_caso(caso) and not d.get("test") and caso.get("carrera_id"):
            d["test"] = perm.crear_test(caso["carrera_id"])
            intro = True
    if d.get("test") and d.get("dictamen"):
        d["dictamen"] = perm.dictamen(d.get("caso") or {}, d["test"])
    out = _voz(d, pre_es, pre_en, rec=rec, intro_test=intro)
    db.guardar(d)
    return {"ok": True, "confirmado": True, "tipo": tipo, "resultado": resultado, **out}


@interno.post("/sesiones/{sid}/proponer", dependencies=[Depends(_auth_interna)])
def proponer_interno(sid: str, body: Propuesta, bg: BackgroundTasks):
    return _proponer(_doc(sid), body, bg)


@interno.post("/sesiones/{sid}/confirmar", dependencies=[Depends(_auth_interna)])
def confirmar_interno(sid: str, body: Confirmacion, bg: BackgroundTasks):
    return _confirmar(_doc(sid), body.si, bg)


@publico.post("/sesiones/{sid}/proponer")
def proponer_publico(sid: str, body: Propuesta, bg: BackgroundTasks):
    if body.tipo not in ("test", "sentimiento"):
        raise HTTPException(400, "Desde la pantalla solo se eligen opciones del test o cómo te sentiste")
    d = _doc(sid)
    out = _proponer(d, body, bg)
    return {"vista": vista_publica(d), **out}


@publico.post("/sesiones/{sid}/confirmar")
def confirmar_publico(sid: str, body: Confirmacion, bg: BackgroundTasks):
    d = _doc(sid)
    out = _confirmar(d, body.si, bg)
    return {"vista": vista_publica(d), **out}
