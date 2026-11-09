"""
Motor de recomendación vocacional.

Puntaje final = Afinidad x factor económico, ajustado por la calificación del video.

- Afinidad (0-100): cruce de las etiquetas que el agente extrae de cada respuesta
  (intereses, clase favorita, rasgos, ambiente) contra el perfil ponderado de cada carrera.
- Viabilidad (0-1): ¿puede estudiarla de verdad? Depende de su nivel económico
  (qué tipo de universidad puede costear), la distancia a la sede más cercana que
  ofrece la carrera, si puede mudarse o necesita trabajar, y si hay opción a distancia
  con o sin internet.
- La situación económica es determinante: con nivel "baja" la viabilidad pesa el 50 %
  del puntaje; con "media" el 30 %; con "alta" el 10 %.
"""

from __future__ import annotations

import json
import math
import os
import unicodedata
from pathlib import Path

DATA = Path(__file__).parent / "data"

UMBRAL_ALEJADO_KM = float(os.getenv("UMBRAL_ALEJADO_KM", "60"))
UMBRAL_RURAL_KM = float(os.getenv("UMBRAL_RURAL_KM", "30"))

PESO_DIMENSION = {"intereses": 0.35, "materias": 0.25, "rasgos": 0.20, "ambientes": 0.20}
PESO_ECONOMICO = {"baja": 0.5, "media": 0.3, "alta": 0.1}
COSTOS_ACCESIBLES = {
    "baja": {"publica", "beca"},
    "media": {"publica", "beca", "accesible"},
    "alta": {"publica", "beca", "accesible", "alto"},
}
BASE_COSTO = {
    "publica": {"baja": 1.0, "media": 1.0, "alta": 1.0},
    "beca": {"baja": 0.55, "media": 0.65, "alta": 0.9},
    "accesible": {"baja": 0.3, "media": 0.8, "alta": 1.0},
    "alto": {"baja": 0.1, "media": 0.35, "alta": 1.0},
}
ETIQUETA_COSTO = {
    "publica": "Pública / muy bajo costo",
    "beca": "Privada con becas",
    "accesible": "Privada accesible",
    "alto": "Privada",
}


def _load(nombre):
    return json.loads((DATA / nombre).read_text(encoding="utf-8"))


VOCAB = _load("vocabulario.json")
CARRERAS = _load("carreras.json")
CARRERAS_POR_ID = {c["id"]: c for c in CARRERAS}
UNIVERSIDADES = _load("universidades.json")
OPORTUNIDADES = _load("oportunidades.json")
OPORT_POR_ID = {o["id"]: o for o in OPORTUNIDADES}
GEO = _load("geografia.json")

PREGUNTA_DIMENSION = {"disfruta": "intereses", "clase": "materias", "descripcion": "rasgos", "ambiente": "ambientes"}
VOCAB_DIMENSION = {"intereses": "intereses", "materias": "materias", "rasgos": "rasgos", "ambientes": "ambientes"}


def norm(s: str | None) -> str:
    s = (s or "").strip().lower()
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")


def limpiar_etiquetas(dimension: str, etiquetas) -> list[str]:
    validas = VOCAB[VOCAB_DIMENSION[dimension]]
    out = []
    for e in etiquetas or []:
        e = norm(str(e)).replace(" ", "_")
        if e in validas and e not in out:
            out.append(e)
    return out


def etiqueta_legible(dimension: str, tag: str) -> str:
    return VOCAB[VOCAB_DIMENSION[dimension]].get(tag, tag)


def haversine_km(a_lat, a_lng, b_lat, b_lng) -> float:
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# ---------------------------------------------------------------------------
# Afinidad
# ---------------------------------------------------------------------------

def perfil_estudiante(respuestas: dict) -> dict[str, list[str]]:
    perfil = {}
    for pregunta, dim in PREGUNTA_DIMENSION.items():
        r = respuestas.get(pregunta) or {}
        tags = limpiar_etiquetas(dim, r.get("etiquetas"))
        if tags:
            perfil[dim] = tags
    return perfil


def afinidad(perfil: dict[str, list[str]], carrera: dict) -> tuple[float, list[str]]:
    total, peso_total, razones = 0.0, 0.0, []
    for dim, peso in PESO_DIMENSION.items():
        tags = perfil.get(dim)
        if not tags:
            continue
        pesos = carrera["perfil"].get(dim, {})
        suma = sum(pesos.get(t, 0) for t in tags)
        denom = 3 * max(1, min(len(tags), 3))
        s = min(1.0, suma / denom)
        total += peso * s
        peso_total += peso
        fuertes = sorted((t for t in tags if pesos.get(t, 0) >= 2), key=lambda t: -pesos[t])
        if fuertes:
            t = fuertes[0]
            label = etiqueta_legible(dim, t)
            label = (label.split(",")[0] if dim in ("rasgos", "materias") else label).lower()
            razones.append({
                "intereses": f"Disfrutas: {label}",
                "materias": f"Tu clase favorita ({label}) es base de la carrera",
                "rasgos": f"Te describes como {label}",
                "ambientes": f"Quieres trabajar en: {label}",
            }[dim])
    if peso_total == 0:
        return 0.0, []
    return round(100 * total / peso_total, 1), razones


# ---------------------------------------------------------------------------
# Viabilidad y opciones de estudio
# ---------------------------------------------------------------------------

def factor_distancia(d: float | None, puede_mudarse: bool | None) -> float:
    if d is None:
        f = 0.6
    elif d <= 30:
        f = 1.0
    elif d <= 100:
        f = 1.0 - (d - 30) / 70 * 0.45
    elif d <= 250:
        f = 0.55 - (d - 100) / 150 * 0.25
    else:
        f = 0.25
    if puede_mudarse:
        f = max(f, 0.6)
    return f


def sedes_de_carrera(carrera_id: str, ubic: dict | None, nivel: str) -> list[dict]:
    lat = (ubic or {}).get("lat")
    lng = (ubic or {}).get("lng")
    accesibles = COSTOS_ACCESIBLES.get(nivel, COSTOS_ACCESIBLES["media"])
    out = []
    for u in UNIVERSIDADES:
        for s in u["sedes"]:
            if carrera_id not in s["carreras"]:
                continue
            d = round(haversine_km(lat, lng, s["lat"], s["lng"])) if lat is not None and lng is not None else None
            out.append({
                "universidad_id": u["id"], "universidad": u["nombre"], "siglas": u["siglas"],
                "sede_id": s["id"], "sede": s["nombre"], "ciudad": s["ciudad"], "departamento": s["departamento"],
                "lat": s["lat"], "lng": s["lng"], "modalidad": s["modalidad"],
                "costo": u["costo"], "costo_texto": ETIQUETA_COSTO[u["costo"]], "costo_detalle": u["costo_texto"],
                "accesible": u["costo"] in accesibles, "distancia_km": d, "web": u["web"],
                "plan_url": (s.get("planes") or {}).get(carrera_id),
                "telefono": s.get("telefono") or (u.get("contacto") or {}).get("telefono"),
                "correo": (u.get("contacto") or {}).get("correo"),
                "contacto_url": (u.get("contacto") or {}).get("url") or u["web"],
            })
    out.sort(key=lambda x: (not x["accesible"], x["distancia_km"] if x["distancia_km"] is not None else 9999))
    return out


def oportunidades_de_carrera(carrera_id: str, tipos=("distancia", "beca", "gratis")) -> list[dict]:
    out = []
    for o in OPORTUNIDADES:
        if o["tipo"] not in tipos:
            continue
        cs = o["carreras"]
        if cs == "todas" or (isinstance(cs, list) and carrera_id in cs):
            out.append(o)
        elif cs == "unah" and any(carrera_id in s["carreras"] for u in UNIVERSIDADES if u["id"] == "unah" for s in u["sedes"]):
            out.append(o)
    return out


def viabilidad(carrera_id: str, ubic: dict | None, eco: dict) -> tuple[float, dict | None, str]:
    nivel = eco.get("nivel") or "media"
    mudarse = eco.get("puede_mudarse")
    trabajar = eco.get("necesita_trabajar")
    internet = eco.get("internet")
    mejor, mejor_sede, via = 0.0, None, ""
    for s in sedes_de_carrera(carrera_id, ubic, nivel):
        f = BASE_COSTO[s["costo"]][nivel] * factor_distancia(s["distancia_km"], mudarse)
        if trabajar and (s["distancia_km"] or 0) > 40 and not mudarse:
            f *= 0.85
        if f > mejor:
            mejor, mejor_sede, via = f, s, "presencial"
    for o in oportunidades_de_carrera(carrera_id, tipos=("distancia",)):
        base = 0.7 if internet else (0.45 if internet is None else 0.3)
        if not o.get("gratuita", False):
            base *= 0.6
        if base > mejor:
            mejor, mejor_sede, via = base, None, f"distancia:{o['id']}"
    return round(mejor, 2), mejor_sede, via


# ---------------------------------------------------------------------------
# Recomendación completa
# ---------------------------------------------------------------------------

def _detalle_carrera(c: dict, ubic: dict | None, eco: dict, af: float, razones: list, vi: float, puntaje: float) -> dict:
    nivel = eco.get("nivel") or "media"
    sedes = sedes_de_carrera(c["id"], ubic, nivel)
    publicas = [s for s in sedes if s["costo"] == "publica"]
    accesibles = [s for s in sedes if s["accesible"]]
    return {
        "id": c["id"], "nombre": c["nombre"], "area": c["area"], "descripcion": c["descripcion"],
        "duracion": c["duracion"], "afinidad": af, "viabilidad": round(vi * 100), "puntaje": puntaje,
        "razones": razones, "temario": c["temario"], "campo_laboral": c["campo_laboral"],
        "alternativas_cortas": c["alternativas_cortas"], "plan_oficial_url": c.get("plan_oficial_url"),
        "video": c["video"], "sedes": sedes,
        "sede_publica_cercana": publicas[0] if publicas else None,
        "sede_accesible_cercana": accesibles[0] if accesibles else None,
        "oportunidades": [o["id"] for o in oportunidades_de_carrera(c["id"])],
    }


def es_alejado(ubic: dict | None, eco: dict, detalle: dict) -> tuple[bool, str]:
    if not ubic or ubic.get("lat") is None:
        return False, ""
    if norm(ubic.get("pais")) not in ("honduras", ""):
        return True, "Nuestro catálogo de sedes cubre Honduras; te mostramos opciones a distancia y becas."
    s = detalle.get("sede_accesible_cercana")
    if not s:
        return True, "No hay una sede que puedas costear que ofrezca esta carrera; mira becas y opciones a distancia."
    d = s["distancia_km"] or 0
    if d > UMBRAL_ALEJADO_KM:
        return True, f"La sede accesible más cercana ({s['siglas']} {s['ciudad']}) está a unos {d} km en línea recta."
    if ubic.get("zona") == "rural" and d > UMBRAL_RURAL_KM:
        return True, f"Vives en zona rural y la sede accesible más cercana está a unos {d} km."
    return False, ""


def plan_directo(detalle: dict, eco: dict, ubic: dict | None) -> list[dict]:
    """Plan de acción por fases para estudiantes de zonas alejadas o con pocos recursos."""
    internet = eco.get("internet")
    fases = []
    sede = detalle.get("sede_publica_cercana") or detalle.get("sede_accesible_cercana")
    univ = next((u for u in UNIVERSIDADES if sede and u["id"] == sede["universidad_id"]), None)

    pasos_ahora = [
        {"texto": "Repasa matemáticas y lectura para la prueba de admisión con Khan Academy (gratis).", "url": OPORT_POR_ID["khan"]["url"]},
        {"texto": "Saca tu DNI o partida de nacimiento, fotos tipo pasaporte y crea un correo electrónico propio.", "url": None},
    ]
    if internet is False:
        pasos_ahora.append({"texto": "Ubica un centro con internet cercano (escuela, municipalidad, telecentro o ciber) para tus trámites en línea.", "url": None})
    fases.append({"fase": "Ahora, mientras terminas el colegio", "pasos": pasos_ahora})

    if univ:
        pasos = [{"texto": f"Meta: {detalle['nombre']} en {univ['siglas']} {sede['ciudad']} (a unos {sede['distancia_km']} km).", "url": univ["web"]}]
        pasos += [{"texto": p, "url": None} for p in univ["admision"]["pasos"]]
        pasos[-1]["url"] = univ["admision"]["url"]
        if (sede.get("distancia_km") or 0) > UMBRAL_ALEJADO_KM:
            pasos.append({"texto": "Pregunta en la universidad por residencias, internado o transporte para estudiantes de lejos.", "url": None})
        fases.append({"fase": "Cuando abra la admisión", "pasos": pasos})

    becas = [OPORT_POR_ID[b] for b in detalle["oportunidades"] if OPORT_POR_ID[b]["tipo"] == "beca"]
    if becas:
        fases.append({"fase": "Becas que puedes pedir", "pasos": [
            {"texto": f"{b['nombre']}: {b['resumen']} Cómo: {' '.join(b['como_aplicar'])}", "url": b["url"]} for b in becas]})

    dist = [OPORT_POR_ID[o] for o in detalle["oportunidades"] if OPORT_POR_ID[o]["tipo"] == "distancia"]
    gratis = [OPORT_POR_ID[o] for o in detalle["oportunidades"] if OPORT_POR_ID[o]["tipo"] == "gratis"]
    pasos_virtual = [{"texto": f"{o['nombre']}: {o['resumen']}", "url": o["url"]} for o in dist + gratis]
    pasos_virtual += [{"texto": f"Ruta corta: {a}", "url": None} for a in detalle["alternativas_cortas"]]
    fases.append({"fase": "Opciones gratis, virtuales o a distancia", "pasos": pasos_virtual})
    return fases


def recomendar(estado: dict, calificaciones: dict | None = None, top_n: int = 3, extras_n: int = 5) -> dict:
    respuestas = estado.get("respuestas", {})
    eco = dict(respuestas.get("economia") or {})
    extra = respuestas.get("extra") or {}
    if extra.get("puede_mudarse") is not None:
        eco["puede_mudarse"] = extra.get("puede_mudarse")
    ubic = estado.get("ubicacion")
    nivel = eco.get("nivel") or "media"
    w = PESO_ECONOMICO.get(nivel, 0.3)
    perfil = perfil_estudiante(respuestas)
    calificaciones = calificaciones or estado.get("calificaciones") or {}

    ranking = []
    for c in CARRERAS:
        af, razones = afinidad(perfil, c)
        vi, _, via = viabilidad(c["id"], ubic, eco)
        puntaje = af * (1 - w + w * vi)
        if c["id"] in calificaciones:
            puntaje += (int(calificaciones[c["id"]]) - 3) * 4
        ranking.append((round(max(0, min(100, puntaje)), 1), af, vi, razones, c))
    ranking.sort(key=lambda x: (-x[0], -x[1]))

    detalles = [_detalle_carrera(c, ubic, eco, af, rz, vi, p) for p, af, vi, rz, c in ranking[: top_n + extras_n]]
    principales, extras = detalles[:top_n], detalles[top_n:]
    top = principales[0] if principales else None
    alejado, motivo = es_alejado(ubic, eco, top) if top else (False, "")
    mostrar_plan = alejado or nivel == "baja"
    return {
        "perfil": perfil,
        "nivel_economico": nivel,
        "peso_economico": w,
        "carreras": principales,
        "extras": extras,
        "alejado": alejado,
        "motivo_alejado": motivo,
        "plan_directo": plan_directo(top, eco, ubic) if (top and mostrar_plan) else [],
        "filtros_sugeridos": sorted(COSTOS_ACCESIBLES.get(nivel, COSTOS_ACCESIBLES["media"]) | {"distancia"}),
    }


def resumen_para_voz(res: dict) -> str:
    """Texto breve (sin cifras con símbolos) para que el LLM lo convierta en voz."""
    if not res["carreras"]:
        return "No hay suficientes datos para recomendar."
    lineas = []
    for i, c in enumerate(res["carreras"], 1):
        s = c["sede_accesible_cercana"] or c["sede_publica_cercana"]
        donde = f"más cercana que puede costear: {s['siglas']} en {s['ciudad']}, a unos {s['distancia_km']} kilómetros" if s and s["distancia_km"] is not None else (
            f"opción: {s['siglas']} en {s['ciudad']}" if s else "sin sede accesible, hay opciones a distancia o becas")
        lineas.append(f"{i}. {c['nombre']} (id {c['id']}): puntaje {round(c['puntaje'])}, afinidad {round(c['afinidad'])}, "
                      f"viabilidad {c['viabilidad']}. Razones: {'; '.join(c['razones'][:2]) or 'perfil general'}. Sede {donde}.")
    extras = ", ".join(f"{e['nombre']} (id {e['id']})" for e in res["extras"])
    txt = "Carreras recomendadas:\n" + "\n".join(lineas) + f"\nOtras opciones en pantalla: {extras}."
    if res["alejado"]:
        txt += f"\nZONA ALEJADA: {res['motivo_alejado']} Hay un plan directo en pantalla con becas y opciones gratis o a distancia."
    elif res["plan_directo"]:
        txt += "\nPor su situación económica hay un plan directo en pantalla con becas y opciones gratuitas."
    return txt
