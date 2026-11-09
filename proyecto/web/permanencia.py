"""
Motor de "¿Sigo en mi carrera?" (Fabiola).

1. Caso: carrera, universidad, año que cursa, motivos de duda y satisfacción (1-5).
2. Test de 6 preguntas en 3 etapas (básico, intermedio, avanzado), 2 por etapa.
   Puntos por acierto: básico 1, intermedio 2, avanzado 3 (máximo 12 → 0-100).
3. Después de cada etapa: cómo se sintió (1-5 y comentario).
4. Dictamen orientativo:
   - Conocimiento relativo = puntaje del test / puntaje esperado según el año (1.º: 40, 2.º: 55, 3.º o más: 70), tope 1.
   - Bienestar = promedio de cómo se sintió en las etapas (1-5 → 0-1).
   - Satisfacción con la carrera (1-5 → 0-1).
   - Señal vocacional: si los motivos indican que la carrera no le gusta, no era lo esperado o le interesa otra.
   Índice de permanencia = 35 % bienestar + 25 % satisfacción + 25 % conocimiento + 15 % señal vocacional.
"""

from __future__ import annotations

import json
from pathlib import Path

from motor import CARRERAS_POR_ID, OPORT_POR_ID

DATA = Path(__file__).parent / "data"
BANCO = json.loads((DATA / "test_carreras.json").read_text(encoding="utf-8"))
NIVELES = ["basico", "intermedio", "avanzado"]
NOMBRE_NIVEL = {"basico": "Básico", "intermedio": "Intermedio", "avanzado": "Avanzado"}
PUNTOS = {"basico": 1, "intermedio": 2, "avanzado": 3}
LETRAS = "ABCD"

MOTIVOS = json.loads((DATA / "motivos.json").read_text(encoding="utf-8"))
VOCACIONALES = {"no_me_gusta", "no_era_lo_esperado", "otra_carrera_interes"}


def crear_test(carrera_id: str | None, personalizadas: list[dict] | None = None) -> dict:
    if personalizadas:
        preguntas = []
        for p in personalizadas:
            ops = [str(o) for o in p["opciones"]][:4]
            if len(ops) != 4 or p.get("nivel") not in NIVELES:
                continue
            preguntas.append({"nivel": p["nivel"], "pregunta": str(p["pregunta"]), "opciones": ops,
                              "correcta": max(0, min(3, int(p["correcta"])))})
        preguntas.sort(key=lambda x: NIVELES.index(x["nivel"]))
        fuente = "personalizado"
    else:
        preguntas = [dict(x) for x in BANCO[carrera_id]]
        fuente = "banco"
    for i, p in enumerate(preguntas, 1):
        p["numero"] = i
    return {"carrera_id": carrera_id, "fuente": fuente, "preguntas": preguntas, "respuestas": {}, "sentimientos": {}}


def pregunta_publica(p: dict) -> dict:
    """Pregunta sin la respuesta correcta (para la pantalla y la voz)."""
    return {"numero": p["numero"], "nivel": p["nivel"], "pregunta": p["pregunta"], "opciones": p["opciones"]}


def siguiente_paso(test: dict) -> dict:
    """Qué toca: una pregunta, preguntar cómo se sintió en una etapa, o el dictamen."""
    for nivel in NIVELES:
        del_nivel = [p for p in test["preguntas"] if p["nivel"] == nivel]
        pend = [p for p in del_nivel if str(p["numero"]) not in test["respuestas"]]
        if pend:
            return {"tipo": "pregunta", "pregunta": pregunta_publica(pend[0])}
        if del_nivel and nivel not in test["sentimientos"]:
            return {"tipo": "sentimiento", "nivel": nivel}
    return {"tipo": "dictamen"}


def responder(test: dict, numero: int, opcion: str) -> dict:
    p = next((x for x in test["preguntas"] if x["numero"] == numero), None)
    if not p:
        raise ValueError("Pregunta no existe")
    if str(numero) in test["respuestas"]:
        r = test["respuestas"][str(numero)]
        return {"ya_respondida": True, **r}
    letra = opcion.strip().upper()[:1]
    if letra not in LETRAS:
        raise ValueError("Opción inválida")
    idx = LETRAS.index(letra)
    correcta = idx == p["correcta"]
    r = {"numero": numero, "opcion": letra, "correcta": correcta,
         "letra_correcta": LETRAS[p["correcta"]], "texto_correcta": p["opciones"][p["correcta"]]}
    test["respuestas"][str(numero)] = r
    return {"ya_respondida": False, **r}


def omitir(test: dict, numero: int) -> dict:
    """El estudiante saltó la pregunta: cuenta como no acertada."""
    p = next((x for x in test["preguntas"] if x["numero"] == numero), None)
    if not p:
        raise ValueError("Pregunta no existe")
    if str(numero) in test["respuestas"]:
        return {"ya_respondida": True, **test["respuestas"][str(numero)]}
    r = {"numero": numero, "opcion": None, "correcta": False, "omitida": True,
         "letra_correcta": LETRAS[p["correcta"]], "texto_correcta": p["opciones"][p["correcta"]]}
    test["respuestas"][str(numero)] = r
    return {"ya_respondida": False, **r}


def puntajes(test: dict) -> dict:
    por_nivel, total, maximo = {}, 0, 0
    for nivel in NIVELES:
        ps = [p for p in test["preguntas"] if p["nivel"] == nivel]
        ok = sum(1 for p in ps if test["respuestas"].get(str(p["numero"]), {}).get("correcta"))
        por_nivel[nivel] = {"aciertos": ok, "total": len(ps), "porcentaje": round(100 * ok / len(ps)) if ps else 0}
        total += ok * PUNTOS[nivel]
        maximo += len(ps) * PUNTOS[nivel]
    return {"por_nivel": por_nivel, "puntaje": round(100 * total / maximo) if maximo else 0}


def dictamen(caso: dict, test: dict) -> dict:
    pts = puntajes(test)
    anio = int(caso.get("anio") or 1)
    esperado = 40 if anio <= 1 else (55 if anio == 2 else 70)
    conocimiento = min(1.0, pts["puntaje"] / esperado)
    sent = [v["valor"] for v in test["sentimientos"].values() if v.get("valor")]
    bienestar = ((sum(sent) / len(sent)) - 1) / 4 if sent else 0.5
    satisf = ((caso.get("satisfaccion") or 3) - 1) / 4
    motivos = set(caso.get("motivos") or [])
    vocacional = bool(motivos & VOCACIONALES)
    indice = round(100 * (0.35 * bienestar + 0.25 * satisf + 0.25 * conocimiento + 0.15 * (0 if vocacional else 1)))

    if indice >= 70:
        decision, titulo = "continuar", "Recomendable continuar en la carrera"
        texto = "Tus respuestas muestran que la carrera va contigo: te sientes bien en ella y tienes la base que se espera para tu avance."
    elif indice >= 50:
        if conocimiento < 0.6 and bienestar >= 0.5:
            decision, titulo = "continuar_apoyo", "Continuar con apoyo académico"
            texto = "Te sientes a gusto con la carrera; lo que más pesa es reforzar conocimientos. Con tutorías y un plan de estudio puedes avanzar."
        elif motivos & {"economico", "trabajo_horario", "familiar_personal"}:
            decision, titulo = "continuar_apoyo", "Continuar buscando apoyo para tu situación"
            texto = "Tus dudas vienen más de tu situación que de la carrera en sí. Vale la pena buscar becas, otro horario o modalidad antes de dejarla."
        else:
            decision, titulo = "reevaluar", "Continuar y reevaluar en un período"
            texto = "Hay señales mixtas. Te conviene seguir un período más con metas claras y volver a evaluar con el psicólogo."
    else:
        if vocacional or bienestar < 0.4:
            decision, titulo = "explorar_cambio", "Explorar un cambio de carrera"
            texto = "Tus respuestas indican que esta carrera no te está haciendo sentir bien o no es lo que buscas. Explora otras opciones antes de decidir."
        else:
            decision, titulo = "reevaluar", "Reevaluar con el psicólogo antes de decidir"
            texto = "Hay dificultades importantes, pero no necesariamente vocacionales. Habla con el psicólogo para definir el mejor paso."

    recs = []
    if "dificultad_academica" in motivos or conocimiento < 0.6:
        recs.append({"texto": "Pide tutorías o asesorías en tu facultad y forma un grupo de estudio.", "url": None})
        recs.append({"texto": "Repasa la base con cursos gratuitos de Khan Academy.", "url": OPORT_POR_ID["khan"]["url"]})
    if "economico" in motivos:
        recs.append({"texto": "Solicita una beca: " + OPORT_POR_ID["sedesol_becas"]["nombre"] + ".", "url": OPORT_POR_ID["sedesol_becas"]["url"]})
        recs.append({"texto": "Si estudias en la UNAH, pide la beca o ayuda Mi Bienestar.", "url": OPORT_POR_ID["unah_mi_bienestar"]["url"]})
    if "trabajo_horario" in motivos:
        recs.append({"texto": "Pregunta por secciones nocturnas, de fin de semana o modalidad a distancia en tu universidad.", "url": None})
    if vocacional or decision == "explorar_cambio":
        recs.append({"texto": "Haz la orientación con Lucía para descubrir carreras que vayan contigo (botón Lucía de la barra lateral).", "url": None})
    if "salud_bienestar" in motivos or caso.get("alerta_bienestar"):
        recs.append({"texto": "Agenda una reunión con el psicólogo; tu bienestar es lo primero.", "url": None})
    if "salida_laboral" in motivos:
        recs.append({"texto": "Conversa con graduados de tu carrera y revisa ofertas de empleo del área para conocer el campo laboral real.", "url": None})
    recs.append({"texto": "Este dictamen es orientativo: la decisión es tuya. Coméntalo con el psicólogo y con tu familia.", "url": None})

    return {
        "decision": decision, "titulo": titulo, "texto": texto, "indice": indice, "puntaje_test": pts["puntaje"],
        "por_nivel": pts["por_nivel"], "esperado_por_anio": esperado,
        "componentes": {"bienestar": round(bienestar * 100), "satisfaccion": round(satisf * 100),
                        "conocimiento": round(conocimiento * 100), "vocacional": 0 if vocacional else 100},
        "sentimientos": test["sentimientos"], "recomendaciones": recs,
    }


def texto_pregunta_voz(p: dict) -> str:
    ops = "; ".join(f"opción {LETRAS[i]}: {o}" for i, o in enumerate(p["opciones"]))
    return f"Pregunta {p['numero']}, nivel {NOMBRE_NIVEL[p['nivel']].lower()}: {p['pregunta']} {ops}."


def nombre_carrera(caso: dict) -> str:
    cid = caso.get("carrera_id")
    return caso.get("carrera_nombre") or (CARRERAS_POR_ID.get(cid, {}).get("nombre") if cid else "") or "tu carrera"
