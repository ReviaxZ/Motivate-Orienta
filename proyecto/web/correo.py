"""Correo HTML con el contexto de la entrevista para el psicólogo."""

from __future__ import annotations

import html
import os
from datetime import datetime

from motor import CARRERAS_POR_ID, VOCAB, VOCAB_DIMENSION, PREGUNTA_DIMENSION

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

PREGUNTAS = [
    ("disfruta", "¿Qué es lo que más disfrutas hacer en tu día?"),
    ("clase", "¿Cuál es la clase que más disfrutas?"),
    ("descripcion", "¿Cómo te describirías a ti mismo?"),
    ("ambiente", "¿En qué ambiente te gustaría trabajar?"),
    ("economia", "¿Cuál es tu situación económica actual?"),
    ("extra", "¿Algo más que te gustaría contar sobre tu situación actual?"),
]


def e(x) -> str:
    return html.escape(str(x)) if x not in (None, "") else "—"


def _tags(pregunta: str, r: dict) -> str:
    dim = PREGUNTA_DIMENSION.get(pregunta)
    if not dim or not r.get("etiquetas"):
        return ""
    labels = [VOCAB[VOCAB_DIMENSION[dim]].get(t, t) for t in r["etiquetas"]]
    return "<br><span style='color:#555;font-size:12px'>Etiquetas: " + e(", ".join(labels)) + "</span>"


def asunto(doc: dict) -> str:
    nombre = (doc.get("estudiante") or {}).get("nombre") or "Estudiante"
    alerta = (doc.get("respuestas", {}).get("extra") or {}).get("alerta_bienestar") or (doc.get("caso") or {}).get("alerta_bienestar")
    if doc.get("modo") == "permanencia":
        inc = " (entrevista incompleta)" if doc.get("estado") == "incompleta" else ""
        return f"{'[ATENCIÓN PRIORITARIA] ' if alerta else ''}¿Sigo en mi carrera? – {nombre}{inc}"
    pref = "[ATENCIÓN PRIORITARIA] " if alerta else ""
    inc = " (entrevista incompleta)" if doc.get("estado") == "incompleta" else ""
    return f"{pref}Orientación vocacional – {nombre}{inc}"


def html_permanencia(doc: dict) -> str:
    import permanencia as perm
    caso = doc.get("caso") or {}
    t = doc.get("test") or {}
    dic = doc.get("dictamen") or {}
    est = doc.get("estudiante") or {}
    cita = doc.get("cita") or {}
    alerta = ""
    if caso.get("alerta_bienestar"):
        alerta = ("<div style='background:#fde8e8;border-left:4px solid #c62828;padding:10px;margin:12px 0'>"
                  "<b>Alerta de bienestar:</b> el estudiante mencionó algo que requiere atención prioritaria.</div>")
    motivos = ", ".join(perm.MOTIVOS.get(m, m) for m in caso.get("motivos") or []) or "—"
    filas = ""
    for p in t.get("preguntas", []):
        r = (t.get("respuestas") or {}).get(str(p["numero"]))
        res = ("—" if not r else "Omitida" if r.get("omitida") else
               (f"✔ {r['opcion']}" if r["correcta"] else f"✘ {r['opcion']} (correcta {r['letra_correcta']})"))
        filas += (f"<tr><td style='padding:6px;border-bottom:1px solid #eee'>{e(perm.NOMBRE_NIVEL[p['nivel']])}</td>"
                  f"<td style='padding:6px;border-bottom:1px solid #eee'>{e(p['pregunta'])}</td>"
                  f"<td style='padding:6px;border-bottom:1px solid #eee'>{e(res)}</td></tr>")
    sent = "".join(f"<li>{e(perm.NOMBRE_NIVEL[n])}: {(str(v.get('valor')) + '/5') if v.get('valor') else 'omitida'} – {e(v.get('texto'))}</li>"
                   for n, v in (t.get("sentimientos") or {}).items())
    recs = "".join(f"<li>{e(r['texto'])}</li>" for r in dic.get("recomendaciones", []))
    comp = dic.get("componentes") or {}
    cita_html = ""
    if cita.get("estado") == "agendada":
        cita_html = f"<p><b>Reunión Teams:</b> {e(cita.get('inicio'))} – <a href='{e(cita.get('enlace'))}'>Unirse</a></p>"
    elif cita.get("estado"):
        cita_html = f"<p><b>Cita solicitada:</b> {e(cita.get('inicio'))} (estado: {e(cita.get('estado'))}; agendar manualmente)</p>"
    panel = f"<p><a href='{PUBLIC_BASE_URL}/panel/#{e(doc['id'])}'>Ver en el panel</a></p>" if PUBLIC_BASE_URL else ""
    return f"""
<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1b1b1b;max-width:720px">
  <h2 style="margin:0 0 4px">¿Sigo en mi carrera? – contexto para psicología</h2>
  <p style="color:#555;margin:0 0 12px">Entrevista {e(doc['id'])} con Fabiola · estado: {e(doc.get('estado'))} · idioma: {e(doc.get('idioma') or 'es')}</p>
  {alerta}
  <p><b>Estudiante:</b> {e(est.get('nombre'))} · <b>Correo:</b> {e(est.get('correo'))}</p>
  <p><b>Carrera:</b> {e(perm.nombre_carrera(caso))} · <b>Universidad:</b> {e(caso.get('universidad'))} · <b>Año:</b> {e(caso.get('anio'))}</p>
  <p><b>Motivos de duda:</b> {e(motivos)} · <b>Satisfacción con la carrera:</b> {e(str(caso['satisfaccion']) + '/5' if caso.get('satisfaccion') else 'omitida')}</p>
  <p><b>Lo que contó:</b> {e(caso.get('texto'))}</p>
  <h3>Dictamen orientativo</h3>
  <p style="font-size:16px"><b>{e(dic.get('titulo'))}</b> · índice {e(dic.get('indice'))}/100 · test {e(dic.get('puntaje_test'))}/100 (esperado para su año: {e(dic.get('esperado_por_anio'))})</p>
  <p>Bienestar {e(comp.get('bienestar'))} · Satisfacción {e(comp.get('satisfaccion'))} · Conocimiento {e(comp.get('conocimiento'))} · Señal vocacional {e(comp.get('vocacional'))}</p>
  <p>{e(dic.get('texto'))}</p>
  <h3>Cómo se sintió en cada etapa</h3><ul>{sent or '<li>—</li>'}</ul>
  <h3>Test</h3><table style="border-collapse:collapse;width:100%">{filas}</table>
  <h3>Recomendaciones dadas</h3><ul>{recs or '<li>—</li>'}</ul>
  {cita_html}
  <h3>Resumen de Fabiola</h3><p>{e(doc.get('resumen_agente'))}</p>
  <p><b>Sugerencias para el seguimiento:</b> {e(doc.get('sugerencias_agente'))}</p>
  {panel}
  <p style="color:#888;font-size:12px">Generado automáticamente. El dictamen es orientativo; la conversación con el estudiante es lo que cuenta.</p>
</div>"""


def html_contexto(doc: dict) -> str:
    if doc.get("modo") == "permanencia":
        return html_permanencia(doc)
    r = doc.get("respuestas", {})
    u = doc.get("ubicacion") or {}
    eco = r.get("economia") or {}
    extra = r.get("extra") or {}
    res = doc.get("resultado") or {}
    est = doc.get("estudiante") or {}
    cita = doc.get("cita") or {}
    filas = []
    for k, preg in PREGUNTAS:
        resp = r.get(k) or {}
        filas.append(f"<tr><td style='padding:6px;border-bottom:1px solid #eee;vertical-align:top;width:38%'><b>{e(preg)}</b></td>"
                     f"<td style='padding:6px;border-bottom:1px solid #eee'>{e(resp.get('texto'))}{_tags(k, resp)}</td></tr>")
    alerta_html = ""
    if extra.get("alerta_bienestar"):
        alerta_html = ("<div style='background:#fde8e8;border-left:4px solid #c62828;padding:10px;margin:12px 0'>"
                       "<b>Alerta de bienestar:</b> el estudiante mencionó algo que requiere atención prioritaria. "
                       f"Comentario: {e(extra.get('texto'))}</div>")
    carreras = ""
    for c in res.get("carreras", []):
        s = c.get("sede_accesible_cercana") or c.get("sede_publica_cercana") or {}
        cal = (doc.get("calificaciones") or {}).get(c["id"])
        carreras += (f"<li><b>{e(c['nombre'])}</b> – puntaje {round(c['puntaje'])} (afinidad {round(c['afinidad'])}, viabilidad {c['viabilidad']})"
                     f"{' · video calificado ' + str(cal) + '/5' if cal else ''}<br><span style='color:#555'>"
                     f"{e('; '.join(c.get('razones', [])))}. Sede sugerida: {e(s.get('siglas'))} {e(s.get('ciudad'))}"
                     f"{' (' + str(s.get('distancia_km')) + ' km)' if s.get('distancia_km') is not None else ''}</span></li>")
    extras = ", ".join(e(x["nombre"]) for x in res.get("extras", []))
    elegida = CARRERAS_POR_ID.get(doc.get("carrera_elegida") or "", {}).get("nombre")
    cita_html = ""
    if cita.get("estado") == "agendada":
        cita_html = f"<p><b>Reunión Teams:</b> {e(cita.get('inicio'))} – <a href='{e(cita.get('enlace'))}'>Unirse</a></p>"
    elif cita.get("estado"):
        cita_html = f"<p><b>Cita solicitada:</b> {e(cita.get('inicio'))} (estado: {e(cita.get('estado'))}; agendar manualmente)</p>"
    panel = f"<p><a href='{PUBLIC_BASE_URL}/panel/#{e(doc['id'])}'>Ver en el panel</a></p>" if PUBLIC_BASE_URL else ""
    return f"""
<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1b1b1b;max-width:720px">
  <h2 style="margin:0 0 4px">Contexto de orientación vocacional</h2>
  <p style="color:#555;margin:0 0 12px">Entrevista {e(doc['id'])} · {e(doc.get('creada', '')[:16].replace('T', ' '))} UTC · estado: {e(doc.get('estado'))}</p>
  {alerta_html}
  <h3>Estudiante</h3>
  <p><b>Nombre:</b> {e(est.get('nombre'))} · <b>Correo:</b> {e(est.get('correo'))}</p>
  <p><b>Idioma de la entrevista:</b> {e(doc.get('idioma') or 'es')}</p>
  <p><b>Ubicación:</b> {e(u.get('colonia'))}, {e(u.get('municipio'))}, {e(u.get('departamento'))}, {e(u.get('pais'))} · zona {e(u.get('zona'))}</p>
  <p><b>Situación económica:</b> nivel {e(eco.get('nivel'))} · necesita trabajar: {e({True: 'sí', False: 'no'}.get(eco.get('necesita_trabajar')))}
     · internet: {e({True: 'sí', False: 'no'}.get(eco.get('internet')))} · computadora: {e({True: 'sí', False: 'no'}.get(eco.get('computadora')))}</p>
  <h3>Respuestas</h3>
  <table style="border-collapse:collapse;width:100%">{''.join(filas)}</table>
  <h3>Resultado</h3>
  <ol>{carreras or '<li>Sin recomendación generada</li>'}</ol>
  <p><b>Otras opciones mostradas:</b> {extras or '—'}</p>
  <p><b>Carrera elegida por el estudiante:</b> {e(elegida)}</p>
  <p><b>Zona alejada:</b> {'sí – ' + e(res.get('motivo_alejado')) if res.get('alejado') else 'no'}</p>
  {cita_html}
  <h3>Resumen de la orientadora virtual</h3>
  <p>{e(doc.get('resumen_agente'))}</p>
  <p><b>Sugerencias para el seguimiento:</b> {e(doc.get('sugerencias_agente'))}</p>
  {panel}
  <p style="color:#888;font-size:12px">Generado automáticamente. Las puntuaciones son orientativas; la conversación con el estudiante es lo que cuenta.</p>
</div>"""


# ---------------------------------------------------------------------------
# Avisos inmediatos: solicitud de cita y alerta de bienestar
# ---------------------------------------------------------------------------

def _quien(doc: dict) -> str:
    return "Fabiola (¿sigo en mi carrera?)" if doc.get("modo") == "permanencia" else "Lucía (orientación vocacional)"


def _panel(doc: dict) -> str:
    return f"<p><a href='{PUBLIC_BASE_URL}/panel/#{e(doc['id'])}'>Ver la sesión en el panel</a></p>" if PUBLIC_BASE_URL else ""


def asunto_cita(doc: dict) -> str:
    est = doc.get("estudiante") or {}
    cita = doc.get("cita") or {}
    tipo = "Reunión agendada" if cita.get("estado") == "agendada" else "Solicitud de reunión"
    return f"{tipo} – {est.get('nombre') or 'Estudiante'}"


def html_cita(doc: dict) -> str:
    est = doc.get("estudiante") or {}
    cita = doc.get("cita") or {}
    try:
        cuando = datetime.fromisoformat(cita.get("inicio")).strftime("%d/%m/%Y %I:%M %p")
    except Exception:
        cuando = cita.get("inicio")
    if cita.get("estado") == "agendada":
        estado = (f"<p><b>Estado:</b> agendada en Teams · <a href='{e(cita.get('enlace'))}'>Unirse</a></p>" if cita.get("enlace")
                  else "<p><b>Estado:</b> agendada en el calendario.</p>")
    else:
        estado = ("<p style='background:#fff6e0;border-left:4px solid #c7811a;padding:10px'><b>Pendiente de confirmar:</b> "
                  "no se pudo crear la reunión de Teams automáticamente. Contacta al estudiante para confirmar el horario.</p>")
    return f"""
<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1b1b1b;max-width:640px">
  <h2 style="margin:0 0 4px">{e(asunto_cita(doc))}</h2>
  <p style="color:#555;margin:0 0 12px">Sesión {e(doc['id'])} con {e(_quien(doc))}</p>
  <p><b>Estudiante:</b> {e(est.get('nombre'))}<br><b>Correo:</b> {e(est.get('correo'))}<br><b>Horario pedido:</b> {e(cuando)}</p>
  {estado}
  <p>El contexto completo de la entrevista llega en otro correo al terminar la conversación.</p>
  {_panel(doc)}
</div>"""


def asunto_alerta(doc: dict) -> str:
    return f"[ATENCIÓN PRIORITARIA] Alerta de bienestar – sesión {doc['id'][-6:]}"


def html_alerta(doc: dict, texto: str | None) -> str:
    est = doc.get("estudiante") or {}
    u = doc.get("ubicacion") or {}
    lugar = ", ".join(x for x in [u.get("municipio"), u.get("departamento")] if x) or "—"
    return f"""
<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#1b1b1b;max-width:640px">
  <div style="background:#fde8e8;border-left:4px solid #c62828;padding:12px;margin:0 0 12px">
    <b>Alerta de bienestar.</b> Durante la conversación con {e(_quien(doc))} el estudiante mencionó algo que requiere atención prioritaria.
  </div>
  <p><b>Sesión:</b> {e(doc['id'])} · {e(datetime.now().strftime('%d/%m/%Y %I:%M %p'))}</p>
  <p><b>Estudiante:</b> {e(est.get('nombre'))} · <b>Correo:</b> {e(est.get('correo'))} · <b>Ubicación:</b> {e(lugar)}</p>
  <p><b>Lo que contó (resumen de la orientadora):</b><br>{e(texto)}</p>
  <p>La orientadora le respondió con calma, le recomendó hablar hoy con un adulto de confianza o con psicología y mencionó el 911 en caso de emergencia.</p>
  {_panel(doc)}
</div>"""


def html_prueba() -> str:
    return ("<div style=\"font-family:Segoe UI,Arial,sans-serif;font-size:14px\"><h2>Correo de prueba de Orienta</h2>"
            f"<p>Si lees esto, los correos del orientador ya llegan a esta dirección. Enviado {e(datetime.now().strftime('%d/%m/%Y %I:%M %p'))}.</p></div>")
