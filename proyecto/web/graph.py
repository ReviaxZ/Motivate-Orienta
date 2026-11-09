"""
Microsoft Graph: reuniones de Teams y correo al psicólogo.

Dos formas de autenticarse (se usa la primera que esté configurada):
  1. Aplicación (recomendado para producción): GRAPH_TENANT_ID, GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET
     y GRAPH_USER (buzón organizador). Permisos de aplicación: Calendars.ReadWrite y Mail.Send.
  2. Token delegado temporal (pruebas): GRAPH_ACCESS_TOKEN, por ejemplo copiado de Graph Explorer.
     Debe incluir los permisos Calendars.ReadWrite y Mail.Send. Caduca en horas.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

log = logging.getLogger("graph")

GRAPH = "https://graph.microsoft.com/v1.0"
TZ = ZoneInfo(os.getenv("ZONA_HORARIA", "America/Tegucigalpa"))
TZ_WINDOWS = os.getenv("ZONA_HORARIA_WINDOWS", "Central America Standard Time")

PSICOLOGO_EMAIL = os.getenv("PSICOLOGO_EMAIL", "")
PSICOLOGO_NOMBRE = os.getenv("PSICOLOGO_NOMBRE", "Psicología / Orientación")
CITA_MIN = int(os.getenv("CITA_DURACION_MIN", "30"))
CITA_HORA_INICIO = int(os.getenv("CITA_HORA_INICIO", "8"))
CITA_HORA_FIN = int(os.getenv("CITA_HORA_FIN", "16"))
CITA_DIAS = int(os.getenv("CITA_DIAS_HABILES", "5"))

_app_token: dict = {}


def _decode(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def _modo() -> str | None:
    if os.getenv("GRAPH_TENANT_ID") and os.getenv("GRAPH_CLIENT_ID") and os.getenv("GRAPH_CLIENT_SECRET") and os.getenv("GRAPH_USER"):
        return "aplicacion"
    if os.getenv("GRAPH_ACCESS_TOKEN"):
        return "delegado"
    return None


def _token() -> str:
    modo = _modo()
    if modo == "delegado":
        return os.environ["GRAPH_ACCESS_TOKEN"].strip()
    if modo == "aplicacion":
        if _app_token.get("exp", 0) > time.time() + 120:
            return _app_token["tok"]
        r = httpx.post(
            f"https://login.microsoftonline.com/{os.environ['GRAPH_TENANT_ID']}/oauth2/v2.0/token",
            data={"client_id": os.environ["GRAPH_CLIENT_ID"], "client_secret": os.environ["GRAPH_CLIENT_SECRET"],
                  "scope": "https://graph.microsoft.com/.default", "grant_type": "client_credentials"},
            timeout=15,
        )
        r.raise_for_status()
        d = r.json()
        _app_token.update(tok=d["access_token"], exp=time.time() + int(d.get("expires_in", 3600)))
        return _app_token["tok"]
    raise RuntimeError("Graph no está configurado")


def _base() -> str:
    return f"{GRAPH}/users/{os.environ['GRAPH_USER']}" if _modo() == "aplicacion" else f"{GRAPH}/me"


def estado() -> dict:
    modo = _modo()
    info = {"modo": modo, "psicologo": PSICOLOGO_EMAIL or None, "calendario": False, "correo": False,
            "expira": None, "cuenta": None, "faltan": [], "mensaje": ""}
    if not modo:
        info["mensaje"] = "Graph sin configurar: las citas y correos quedan pendientes en el panel."
        return info
    if modo == "aplicacion":
        try:
            claims = _decode(_token())
        except Exception as e:
            info["mensaje"] = f"No se pudo obtener token de aplicación: {e}"
            return info
        permisos = set(claims.get("roles", []))
        info["cuenta"] = os.getenv("GRAPH_USER")
    else:
        claims = _decode(_token())
        permisos = set((claims.get("scp") or "").split())
        info["cuenta"] = claims.get("upn") or claims.get("unique_name")
        if claims.get("exp"):
            info["expira"] = datetime.fromtimestamp(claims["exp"], TZ).isoformat(timespec="minutes")
            if claims["exp"] < time.time():
                info["mensaje"] = "El token de Graph ya caducó: genera uno nuevo."
    info["calendario"] = bool(permisos & {"Calendars.ReadWrite", "Calendars.ReadWrite.Shared"})
    info["correo"] = bool(permisos & {"Mail.Send", "Mail.Send.Shared"})
    if not info["calendario"]:
        info["faltan"].append("Calendars.ReadWrite")
    if not info["correo"]:
        info["faltan"].append("Mail.Send")
    if not PSICOLOGO_EMAIL:
        info["faltan"].append("PSICOLOGO_EMAIL (variable de entorno)")
    if info["faltan"] and not info["mensaje"]:
        info["mensaje"] = "Faltan: " + ", ".join(info["faltan"])
    return info


def _req(method: str, path: str, **kw) -> httpx.Response:
    headers = kw.pop("headers", {})
    headers["Authorization"] = f"Bearer {_token()}"
    r = httpx.request(method, f"{_base()}{path}", headers=headers, timeout=20, **kw)
    if r.status_code >= 400:
        try:
            err = r.json().get("error", {})
            msg = f"{err.get('code')}: {err.get('message')}"
        except Exception:
            msg = r.text[:300]
        raise RuntimeError(f"Graph {r.status_code} – {msg}")
    return r


# ---------------------------------------------------------------------------
# Horarios
# ---------------------------------------------------------------------------

def horarios_disponibles(max_slots: int = 12) -> list[dict]:
    ahora = datetime.now(TZ)
    inicio_min = ahora + timedelta(hours=2)
    slots, dia, dias = [], ahora.date(), 0
    for _ in range(CITA_DIAS * 3):
        if dias >= CITA_DIAS:
            break
        if dia.weekday() < 5:
            t = datetime(dia.year, dia.month, dia.day, CITA_HORA_INICIO, tzinfo=TZ)
            fin_dia = datetime(dia.year, dia.month, dia.day, CITA_HORA_FIN, tzinfo=TZ)
            del_dia = []
            while t + timedelta(minutes=CITA_MIN) <= fin_dia:
                if t >= inicio_min:
                    del_dia.append(t)
                t += timedelta(minutes=CITA_MIN)
            if del_dia:
                slots += del_dia
                dias += 1
        dia += timedelta(days=1)
    if not slots:
        return []
    ocupados = []
    st = estado()
    if st["calendario"]:
        try:
            r = _req("GET", "/calendarView", params={
                "startDateTime": slots[0].isoformat(), "endDateTime": (slots[-1] + timedelta(minutes=CITA_MIN)).isoformat(),
                "$select": "start,end,showAs", "$top": "200"}, headers={"Prefer": f'outlook.timezone="{TZ_WINDOWS}"'})
            for ev in r.json().get("value", []):
                if ev.get("showAs") == "free":
                    continue
                a = datetime.fromisoformat(ev["start"]["dateTime"][:19]).replace(tzinfo=TZ)
                b = datetime.fromisoformat(ev["end"]["dateTime"][:19]).replace(tzinfo=TZ)
                ocupados.append((a, b))
        except Exception as e:
            log.warning("No se pudo leer el calendario: %s", e)
    libres = []
    for s in slots:
        e = s + timedelta(minutes=CITA_MIN)
        if any(a < e and s < b for a, b in ocupados):
            continue
        libres.append(s)
    # Repartir: hasta 3 horarios por día (mañana, mediodía, tarde) para dar variedad
    por_dia: dict = {}
    for s in libres:
        por_dia.setdefault(s.date(), []).append(s)
    out = []
    for k in sorted(por_dia):
        lst = por_dia[k]
        if len(lst) <= 3:
            out += lst
        else:
            out += [lst[0], lst[len(lst) // 2], lst[-1]]
    dias_es = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    return [{"inicio": s.isoformat(timespec="minutes"),
             "etiqueta": f"{dias_es[s.weekday()].capitalize()} {s.day} de {meses[s.month - 1]}, {s.strftime('%I:%M %p').lstrip('0').lower()}"}
            for s in out[:max_slots]]


# ---------------------------------------------------------------------------
# Acciones
# ---------------------------------------------------------------------------

def crear_reunion(inicio_iso: str, nombre: str, correo_estudiante: str | None, sesion_id: str) -> dict:
    st = estado()
    if not st["calendario"] or not PSICOLOGO_EMAIL:
        raise RuntimeError(st["mensaje"] or "Graph sin permiso de calendario")
    inicio = datetime.fromisoformat(inicio_iso).astimezone(TZ)
    fin = inicio + timedelta(minutes=CITA_MIN)
    asistentes = [{"emailAddress": {"address": PSICOLOGO_EMAIL, "name": PSICOLOGO_NOMBRE}, "type": "required"}]
    if correo_estudiante:
        asistentes.append({"emailAddress": {"address": correo_estudiante, "name": nombre or "Estudiante"}, "type": "required"})
    cuerpo = (f"<p>Reunión de orientación vocacional con <b>{nombre or 'estudiante'}</b>.</p>"
              f"<p>El contexto de la entrevista se envió por correo al equipo de psicología (referencia {sesion_id}).</p>")
    ev = _req("POST", "/events", json={
        "subject": f"Orientación vocacional – {nombre or 'Estudiante'}",
        "body": {"contentType": "HTML", "content": cuerpo},
        "start": {"dateTime": inicio.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": TZ_WINDOWS},
        "end": {"dateTime": fin.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": TZ_WINDOWS},
        "attendees": asistentes,
        "isOnlineMeeting": True,
        "onlineMeetingProvider": "teamsForBusiness",
        "allowNewTimeProposals": True,
    }).json()
    join = (ev.get("onlineMeeting") or {}).get("joinUrl")
    if not join:
        time.sleep(2)
        ev2 = _req("GET", f"/events/{ev['id']}", params={"$select": "onlineMeeting,webLink"}).json()
        join = (ev2.get("onlineMeeting") or {}).get("joinUrl")
    return {"evento_id": ev.get("id"), "enlace": join, "web": ev.get("webLink"),
            "inicio": inicio.isoformat(timespec="minutes"), "fin": fin.isoformat(timespec="minutes")}


def enviar_correo(para: str, asunto: str, html: str, importancia: str = "normal") -> None:
    st = estado()
    if not st["correo"]:
        raise RuntimeError(st["mensaje"] or "Graph sin permiso Mail.Send")
    _req("POST", "/sendMail", json={
        "message": {"subject": asunto, "importance": importancia, "body": {"contentType": "HTML", "content": html},
                    "toRecipients": [{"emailAddress": {"address": para}}]},
        "saveToSentItems": True,
    })
