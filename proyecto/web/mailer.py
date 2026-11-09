"""
Envío de correos del orientador.

Orden de preferencia:
1. SMTP (SMTP_HOST, SMTP_USER, SMTP_PASSWORD): por ejemplo Gmail con una contraseña de aplicación.
   Permite enviar a cualquier destinatario.
2. Resend (RESEND_API_KEY). Sin dominio verificado solo puede enviar al dueño de la cuenta.
3. Microsoft Graph (Mail.Send) hacia PSICOLOGO_EMAIL, como antes.

Todos los correos (contexto de la entrevista, solicitudes de cita y alertas de bienestar)
van a la(s) dirección(es) de CORREOS_DESTINO (separadas por comas).

Remitente: RESEND_FROM. Sin dominio verificado en Resend se usa onboarding@resend.dev,
que solo puede enviar al correo dueño de la cuenta de Resend.
"""

from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import httpx

import graph

log = logging.getLogger("orientador")

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM = os.getenv("RESEND_FROM", "").strip() or "Orienta <onboarding@resend.dev>"
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or 587)
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").replace(" ", "")   # las contraseñas de aplicación de Google vienen con espacios
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Orienta").strip()
DESTINOS = [c.strip() for c in os.getenv("CORREOS_DESTINO", "").split(",") if c.strip()]


def proveedor() -> str | None:
    if SMTP_HOST and SMTP_USER and SMTP_PASSWORD:
        return "smtp"
    if RESEND_API_KEY:
        return "resend"
    st = graph.estado()
    return "graph" if st["correo"] else None


def destinos() -> list[str]:
    if DESTINOS:
        return DESTINOS
    return [graph.PSICOLOGO_EMAIL] if graph.PSICOLOGO_EMAIL else []


def estado() -> dict:
    prov = proveedor()
    para = destinos()
    if prov == "smtp":
        msg = f"Correos por SMTP ({SMTP_USER}) → {', '.join(para)}" if para else "SMTP sin destino: configura CORREOS_DESTINO"
    elif prov == "resend":
        msg = f"Correos por Resend → {', '.join(para)}" if para else "Resend sin destino: configura CORREOS_DESTINO"
    elif prov == "graph":
        msg = f"Correos por Graph → {', '.join(para)}" if para else "Falta PSICOLOGO_EMAIL"
    else:
        msg = "Correo sin configurar: los correos quedan pendientes en el panel"
    return {"proveedor": prov, "destinos": para, "listo": bool(prov and para), "remitente": RESEND_FROM if prov == "resend" else None,
            "mensaje": msg}


def enviar(asunto: str, html: str, importancia: str = "normal") -> dict:
    """Envía un correo a los destinos configurados. Lanza RuntimeError si no se pudo."""
    para = destinos()
    if not para:
        raise RuntimeError("No hay destinatario: configura CORREOS_DESTINO")
    prov = proveedor()
    if prov == "smtp":
        return _enviar_smtp(para, asunto, html, importancia)
    if prov == "resend":
        cuerpo = {"from": RESEND_FROM, "to": para, "subject": asunto, "html": html}
        if importancia == "high":
            cuerpo["headers"] = {"X-Priority": "1", "Importance": "high"}
        try:
            r = httpx.post("https://api.resend.com/emails", json=cuerpo, timeout=20,
                           headers={"Authorization": f"Bearer {RESEND_API_KEY}"})
        except httpx.HTTPError as e:
            raise RuntimeError(f"Resend no respondió: {e}")
        if r.status_code >= 400:
            try:
                err = r.json()
                msg = f"{err.get('name') or err.get('statusCode')}: {err.get('message')}"
            except Exception:
                msg = r.text[:300]
            raise RuntimeError(f"Resend {r.status_code} – {msg}")
        return {"proveedor": "resend", "id": r.json().get("id"), "para": ", ".join(para)}
    if prov == "graph":
        for p in para:
            graph.enviar_correo(p, asunto, html, importancia)
        return {"proveedor": "graph", "para": ", ".join(para)}
    raise RuntimeError(estado()["mensaje"])


def _enviar_smtp(para: list[str], asunto: str, html: str, importancia: str) -> dict:
    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = formataddr((SMTP_FROM_NAME, SMTP_USER))
    msg["To"] = ", ".join(para)
    msg["Message-ID"] = make_msgid(domain=SMTP_USER.split("@")[-1])
    if importancia == "high":
        msg["X-Priority"] = "1"
        msg["Importance"] = "high"
    msg.set_content("Este correo tiene formato HTML. Ábrelo en un cliente que lo muestre.")
    msg.add_alternative(html, subtype="html")
    ctx = ssl.create_default_context()
    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=20) as s:
                s.login(SMTP_USER, SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
                s.starttls(context=ctx)
                s.login(SMTP_USER, SMTP_PASSWORD)
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise RuntimeError("SMTP rechazó el usuario o la contraseña. En Gmail usa una contraseña de aplicación "
                           f"(no la contraseña normal). Detalle: {e.smtp_code} {e.smtp_error.decode(errors='ignore')[:150]}")
    except (smtplib.SMTPException, OSError) as e:
        raise RuntimeError(f"SMTP falló: {e}")
    return {"proveedor": "smtp", "para": ", ".join(para)}
