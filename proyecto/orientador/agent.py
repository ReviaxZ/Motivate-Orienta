"""
Agente de voz "Lucía" – orientadora vocacional para estudiantes de colegio.

Misma base que Fabiola: LiveKit + Soniox (STT) + Cerebras (LLM) + Fish Audio (TTS).
El agente conduce la entrevista y guarda cada respuesta en el servidor web (motor de
recomendación + base de datos). Después de cada cambio avisa a la página con un RPC
para que se actualice la ficha, las carreras, el mapa, el video y el temario.

Cuidados de voz:
- Todo lo que genera el LLM pasa por `limpieza.Limpiador` antes de ir a voz y a la
  transcripción: solo llega al estudiante texto natural, nunca JSON, nombres de
  herramientas ni resultados internos.
- Candado de turno: el agente habla UNA vez por turno. En cuanto el texto del LLM
  termina con una pregunta (o termina sin más herramientas pendientes), el turno se
  cierra y cualquier otra generación queda muda hasta que el estudiante hable o
  toque algo en la pantalla (calificar, responder, saltar...).
- Una pregunta casi idéntica a la última que ya hizo se descarta de la voz, salvo que
  el estudiante pida que la repita.
- Botón "Saltar pregunta": la página marca la pregunta como omitida y el agente
  dice la siguiente, una sola vez.
- Se ignoran muletillas ("eh", "mmm") y el eco de la propia voz de Lucía.
"""

import asyncio
import json
import logging
import os
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Annotated, AsyncIterable, Literal, Optional

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

from livekit import rtc  # noqa: E402
from livekit.agents import (  # noqa: E402
    Agent, AgentSession, JobContext, RunContext, StopResponse, WorkerOptions, cli, function_tool, llm,
)
from livekit.plugins import cerebras, fishaudio, soniox  # noqa: E402

from limpieza import Limpiador, hablable  # noqa: E402

log = logging.getLogger("orientador")

WEB_URL = os.getenv("WEB_INTERNAL_URL", "http://web:7878").rstrip("/")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "")
PERSONA = os.getenv("ORIENTADOR_PERSONA", "Lucía")
VOICE_ID = os.getenv("ORIENTADOR_VOICE_ID", "ccb010adf2bd46248c8643f9cfdeddc3")

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).parent / "data"))
VOCAB = json.loads((DATA_DIR / "vocabulario.json").read_text(encoding="utf-8"))
Interes = Literal[tuple(VOCAB["intereses"])]  # type: ignore[valid-type]
Materia = Literal[tuple(VOCAB["materias"])]  # type: ignore[valid-type]
Rasgo = Literal[tuple(VOCAB["rasgos"])]  # type: ignore[valid-type]
Ambiente = Literal[tuple(VOCAB["ambientes"])]  # type: ignore[valid-type]
CARRERA_IDS = [c["id"] for c in json.loads((DATA_DIR / "carreras.json").read_text(encoding="utf-8"))]
IDIOMAS = json.loads((DATA_DIR / "idiomas.json").read_text(encoding="utf-8"))
CarreraId = Literal[tuple(CARRERA_IDS)]  # type: ignore[valid-type]
MOTIVOS = json.loads((DATA_DIR / "motivos.json").read_text(encoding="utf-8"))
Motivo = Literal[tuple(MOTIVOS)]  # type: ignore[valid-type]
FABIOLA = os.getenv("FABIOLA_PERSONA", "Fabiola")
FABIOLA_VOICE_ID = os.getenv("FABIOLA_VOICE_ID", VOICE_ID)

TEXTOS = json.loads((DATA_DIR / "preguntas.json").read_text(encoding="utf-8"))
PREGUNTAS = {k: v["es"] for k, v in TEXTOS["eleccion"].items()}
PREGUNTAS_EN = {k: v["en"] for k, v in TEXTOS["eleccion"].items()}
PREGUNTAS_CASO = {k: v["es"] for k, v in TEXTOS["caso"].items()}
PREGUNTAS_CASO_EN = {k: v["en"] for k, v in TEXTOS["caso"].items()}

SALUDO = (f"Hola estimado, soy {PERSONA}, tu orientadora vocacional. Vamos a platicar un ratito para descubrir "
          f"qué carreras van contigo. Para empezar... {PREGUNTAS['disfruta']}")

INSTRUCCIONES = f"""Eres {PERSONA}, orientadora vocacional virtual. Hablas por voz con estudiantes de colegio (secundaria), sobre todo de Honduras. Tu meta: conocer al estudiante con una entrevista corta y cálida y ayudarle a descubrir carreras que le encajen y que de verdad pueda estudiar según su situación económica y el lugar donde vive.

LO QUE ESCRIBES SE CONVIERTE EN VOZ. Escribe únicamente las palabras que le dirías al estudiante:
- Solo texto plano en español. Nada de JSON, llaves, corchetes, paréntesis, asteriscos, listas, emojis ni comillas.
- Nunca escribas nombres de herramientas, identificadores, etiquetas internas ni el contenido de los resultados de las herramientas. Esos resultados son notas privadas para ti.
- Números en palabras: "ochenta y dos", "unos cuarenta kilómetros", "quinientos lempiras".
- Nunca leas direcciones web, correos ni listas largas. Di "te lo dejé en la pantalla".
- Frases cortas, tono cálido y respetuoso, tutea.
- Nunca escribas fórmulas, ecuaciones, símbolos matemáticos ni caracteres especiales (=, +, /, %, ^, $, barras, llaves). Si necesitas una expresión, dila con palabras: "dos más dos es cuatro", "veinte por ciento".

TURNOS, MUY IMPORTANTE:
- Haz UNA sola pregunta por turno y termina tu turno inmediatamente después de preguntar. Luego espera en silencio la respuesta del estudiante.
- Nunca repitas una pregunta que ya hiciste. Solo repítela, con otras palabras, si el estudiante dice que no entendió o pide que la repitas.
- Cuando el estudiante responda, llama primero a la herramienta de guardar que corresponda, sin escribir nada antes. Con el resultado, di una validación breve de una frase y la siguiente pregunta que te indique el resultado. Si el resultado no indica pregunta, no agregues nada.
- Si la respuesta es muy corta o no se entiende, pide un ejemplo una sola vez.

CONFIRMACIONES, MUY IMPORTANTE (cada paso se confirma antes de pasar al siguiente):
- Las respuestas de selección se confirman: la situación económica y la ubicación. Cuando el estudiante responda una de ellas, llama a la herramienta sin escribir nada antes. El sistema le dirá en voz alta lo que entendió y le preguntará si es correcto. Tú no digas nada más en ese turno.
- Cuando el estudiante conteste a la confirmación: si dice que sí, llama a confirmar con si verdadero. Si dice que no, llama a confirmar con si falso. Si dice que no y en la misma frase da el dato correcto, llama otra vez a la herramienta de guardar con el dato corregido.
- Nunca avances a la siguiente pregunta sin que el estudiante haya confirmado la anterior.
- Las preguntas siguientes y las confirmaciones las dice el sistema con el texto exacto: no las repitas ni las leas tú. Si el resultado de una herramienta no te indica decir nada, no digas nada.

Orden de la entrevista (el saludo y la primera pregunta ya se dijeron):
1. Qué disfruta hacer en su día → guardar_intereses.
2. Clase que más disfruta → guardar_clase_favorita.
3. Cómo se describiría a sí mismo → guardar_descripcion.
4. En qué ambiente le gustaría trabajar → guardar_ambiente.
5. Situación económica actual, con tacto. Si no lo mencionó, pregunta también si tiene internet y computadora o celular en casa → guardar_situacion_economica.
6. País, departamento, municipio y colonia, barrio o aldea. No pidas dirección exacta → guardar_ubicacion.
7. Algo más sobre su situación actual → guardar_comentario_extra.
8. Con las siete respuestas el sistema calcula las carreras y las muestra en pantalla; el resultado de la herramienta te las da. Explica solo la primera: su nombre, una razón conectada con lo que dijo y dónde podría estudiarla. Dile que en la pantalla hay un video de esa carrera y que lo califique con las estrellas. Si hay plan directo, cuéntale que tiene opciones gratis, a distancia y becas en la pantalla. Luego espera.
9. Cuando llegue la calificación del video: con cuatro o cinco estrellas pregunta si quiere quedarse con esa carrera o ver otra; con tres o menos propone la siguiente carrera y llama a mostrar_carrera.
10. Si pide otra carrera, llama a mostrar_carrera. Cuando decida, llama a elegir_carrera y menciona dos o tres materias del primer año.
11. Ofrece una reunión por Teams con el psicólogo del colegio. Si acepta, llama a ofrecer_cita_psicologo y pídele que llene sus datos y elija un horario en la pantalla. Espera el aviso del resultado.
12. Para cerrar llama a finalizar_entrevista con un resumen para el psicólogo y despídete con una frase de ánimo. Si el estudiante quiere irse antes, también llama a finalizar_entrevista.

Cuidado especial:
- Si el estudiante menciona que quiere hacerse daño, violencia, abuso, que no está seguro en casa o algo grave: responde con calma y empatía, sin pedir detalles. Dile que no está solo, que hable hoy con un adulto de confianza o con el psicólogo del colegio, y que en una emergencia en Honduras puede llamar al nueve uno uno. Guarda alerta_bienestar en verdadero y ofrece la reunión con el psicólogo. No diagnostiques.
- Nunca descartes una carrera solo por dinero: muestra el camino con universidades públicas, becas o estudio a distancia.
- No inventes universidades, becas, fechas ni costos.
- Si pregunta algo fuera de la orientación, responde breve y vuelve a la pregunta pendiente."""

SALUDO_EN = (f"Hi there, I'm {PERSONA}, your career guidance counselor. Let's chat for a little while to discover "
             "which careers suit you. To start... what do you enjoy doing most in your day?")


SALUDO_FABIOLA = (f"Hola, soy {FABIOLA}, orientadora universitaria. Te voy a acompañar a pensar si te conviene seguir en tu carrera. "
                  "Para empezar... ¿qué carrera estudias, en qué universidad y en qué año vas?")
SALUDO_FABIOLA_EN = (f"Hi, I'm {FABIOLA}, a university guidance counselor. I'll help you think through whether to stay in your degree. "
                     "To start... what are you studying, at which university, and what year are you in?")

INSTRUCCIONES_FABIOLA = f"""Eres {FABIOLA}, orientadora universitaria virtual. Hablas por voz con estudiantes que ya están en una carrera universitaria y dudan si seguir o dejarla. Tu meta: entender su caso, aplicarle un test corto de su carrera en tres etapas (básica, intermedia y avanzada), preguntarle cómo se sintió en cada etapa y darle un dictamen orientativo de si es recomendable mantenerse en la carrera.

LO QUE ESCRIBES SE CONVIERTE EN VOZ. Escribe únicamente las palabras que le dirías al estudiante:
- Solo texto plano. Nada de JSON, llaves, corchetes, paréntesis, asteriscos, listas, emojis ni comillas.
- Nunca escribas nombres de herramientas, identificadores ni el contenido literal de los resultados de las herramientas: son notas privadas.
- Números en palabras. Nunca leas direcciones web ni correos: di "te lo dejé en la pantalla".
- Frases cortas, tono cálido, sin juzgar. Tutea.
- Nunca escribas fórmulas, ecuaciones, símbolos matemáticos ni caracteres especiales (=, +, /, %, ^, $, barras, llaves). Si necesitas una expresión, dila con palabras: "dos más dos es cuatro", "veinte por ciento".

TURNOS:
- Una sola pregunta por turno; después de preguntar, termina tu turno y espera la respuesta. No repitas preguntas salvo que no te hayan entendido.
- Cuando el estudiante responda, llama primero a la herramienta correspondiente sin escribir nada antes y luego sigue lo que te indique el resultado.

CONFIRMACIONES, MUY IMPORTANTE (cada paso se confirma antes de pasar al siguiente):
- Las respuestas de selección se confirman: los datos de su caso (carrera, universidad y año; motivos; qué tanto le gusta), cada respuesta del test y cómo se sintió en cada etapa. Cuando el estudiante responda una de ellas, llama a la herramienta sin escribir nada antes. El sistema le dirá en voz alta lo que entendió y le preguntará si es correcto. Tú no digas nada más en ese turno.
- Cuando el estudiante conteste a la confirmación: si dice que sí, llama a confirmar con si verdadero. Si dice que no, llama a confirmar con si falso. Si dice que no y en la misma frase da el dato correcto, llama otra vez a la herramienta de guardar con el dato corregido.
- Nunca avances a la siguiente pregunta sin que el estudiante haya confirmado la anterior.
- Las preguntas siguientes y las confirmaciones las dice el sistema con el texto exacto: no las repitas ni las leas tú. Si el resultado de una herramienta no te indica decir nada, no digas nada.

FLUJO (el saludo y la primera pregunta ya se dijeron):
1. Caso: carrera, universidad y año; qué le hace dudar; del uno al cinco qué tanto le gusta su carrera hoy. Después de cada respuesta llama a guardar_caso solo con lo que respondió. Si su carrera coincide con una del catálogo, envía su identificador; si no, usa otra.
2. Cuando el caso esté confirmado, el sistema presenta el test y lee cada pregunta con sus opciones. Tú no las leas.
3. Si la carrera no está en el catálogo, el resultado te pedirá crear el test: llama a crear_test_personalizado con seis preguntas correctas y claras de su carrera, dos básicas, dos intermedias y dos avanzadas, cada una con cuatro opciones. Las preguntas y opciones deben poder leerse en voz alta: sin fórmulas, símbolos ni ecuaciones.
4. Cuando diga una letra, llama a responder_pregunta con esa letra. El sistema le pide confirmar; con su sí llama a confirmar. El sistema le dice si acertó y lee la siguiente.
5. Al terminar cada etapa el sistema pregunta cómo se sintió del uno al cinco. Cuando responda, llama a guardar_sentimiento y luego a confirmar cuando diga que sí.
6. Al final el resultado traerá el dictamen. Explica el puntaje del test, el dictamen y una o dos recomendaciones, recordando que es orientativo y que la decisión es suya. Pregúntale cómo se siente con el resultado.
7. Ofrece una reunión por Teams con el psicólogo. Si acepta, llama a ofrecer_cita_psicologo. Para cerrar llama a finalizar_entrevista con un resumen para el psicólogo y despídete con ánimo.
8. Si el dictamen sugiere explorar otra carrera, menciona que en la barra lateral puede hablar con Lucía para descubrir carreras.

Cuidado especial:
- Si menciona que quiere hacerse daño, violencia, abuso o algo grave: responde con calma y empatía, sin pedir detalles; dile que no está solo, que busque hoy a alguien de confianza o al psicólogo, y que en una emergencia en Honduras puede llamar al nueve uno uno. Llama a guardar_caso con alerta_bienestar verdadero y ofrece la reunión con el psicólogo. No diagnostiques. En este caso sí puedes hablar aunque haya una confirmación pendiente.
- No inventes datos de universidades, becas ni costos."""


def regla_idioma(idioma: str) -> str:
    """Regla de idioma estricta: el agente habla SOLO en el idioma elegido."""
    if idioma == "es" or idioma not in IDIOMAS:
        return ""
    nombre = IDIOMAS[idioma]["nombre"]
    if idioma == "en":
        nombre = "inglés"
    extra = ("" if idioma == "en" else
             f" Usa frases cortas y vocabulario sencillo de {nombre}. Si no conoces una palabra técnica en {nombre}, "
             f"descríbela con palabras sencillas de {nombre}; no cambies a español.")
    return (f"\n\nIDIOMA OBLIGATORIO: Habla ÚNICAMENTE en {nombre} durante toda la conversación. No digas ni una sola frase en español "
            f"(ni para aclarar, ni para repetir), aunque el estudiante te hable en español y aunque las notas privadas, las preguntas "
            f"indicadas, los resultados de las herramientas y los nombres de carreras estén en español: tradúcelo todo a {nombre} antes de decirlo. "
            f"Solo los nombres propios de universidades y ciudades se dicen tal cual." + extra)


def instrucciones(idioma: str, modo: str = "eleccion") -> str:
    base = INSTRUCCIONES_FABIOLA if modo == "permanencia" else INSTRUCCIONES
    return base + regla_idioma(idioma)


NOTA = "[NOTA PRIVADA, no la leas ni la repitas] "
MULETILLAS = {"uh", "um", "umm", "hm", "eh", "ehh", "em", "emm", "mm", "mmm", "hmm", "ah", "ahh", "este", "esteee", "o sea", "pues", "bueno", "a ver", "eee"}
# El estudiante pide que repita: solo entonces se permite decir otra vez la misma pregunta
PIDE_REPETIR = re.compile(r"\b(repit|repet|otra vez|de nuevo|no (te )?entend|no (te )?escuch|no oi|que dijiste|como dijiste|cual era la pregunta|"
                          r"repeat|again|didn ?t (get|hear|understand)|say that|pardon)", re.I)
SIMILITUD_REPETIDA = float(os.getenv("SIMILITUD_PREGUNTA_REPETIDA", "0.9"))
# Respuestas cortas a "¿Es correcto?" que se resuelven sin pasar por el LLM
DICE_SI = re.compile(r"^(si|claro|correcto|exacto|exactamente|asi es|eso es|confirmo|confirmado|de acuerdo|ok|okay|dale|afirmativo|"
                     r"esta bien|ajam|yes|yeah|yep|correct|right|that s right|sure|i confirm)\b")
DICE_NO = re.compile(r"^(no|incorrecto|negativo|nope|wrong|para nada|nel)\b")


def respuesta_corta(texto: str) -> bool | None:
    """True si dijo que sí, False si dijo que no (sin más datos), None si no es una respuesta corta."""
    palabras = texto.split()
    if not palabras or len(palabras) > 6:
        return None
    if DICE_SI.match(texto) and not re.search(r"\b(no|pero|but|not)\b", texto):
        return True
    if DICE_NO.match(texto) and len(palabras) <= 3:
        return False
    return None


def _norm(s: str) -> str:
    s = "".join(ch for ch in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-zñ0-9 ]+", " ", s).strip()


def _parecida(a: str, b: str) -> bool:
    if not a or not b:
        return False
    return a == b or SequenceMatcher(None, a, b).ratio() >= SIMILITUD_REPETIDA


class AgenteBase(Agent):
    """Lo común a Lucía y Fabiola: voz limpia, candado de turno, anti-eco, idioma, API interna, saltar, cita y cierre."""

    def __init__(self, ctx: JobContext, http: httpx.AsyncClient, idioma: str, modo: str, saludo: str) -> None:
        super().__init__(instructions=instrucciones(idioma, modo))
        self.idioma = idioma
        self.modo = modo
        self.ctx = ctx
        self.http = http
        self.sid = ctx.room.name
        self.finalizada = False
        self._paso = Limpiador()       # texto del paso actual del LLM
        self._ultimo_dicho = saludo    # para detectar eco
        # Candado de turno: el agente solo puede hablar con el turno abierto
        self._turno = 0
        self._abierto = False          # el saludo se dice con say(); luego se espera al estudiante
        self._extra = False            # permiso para UNA generación más (p. ej. explicar los resultados)
        self._hablo_turno = 0          # generaciones con voz en el turno
        self._pregunto_turno = False
        self._pidio_repetir = False
        self._ultima_pregunta = _norm(saludo.split("...")[-1]) if "?" in saludo else ""
        self._confirmacion: dict | None = None   # lo que el sistema le pidió confirmar al estudiante

    def en_idioma(self, texto: str) -> str:
        """Agrega el recordatorio de idioma a una nota/instrucción interna."""
        if self.idioma == "es":
            return texto
        nombre = "inglés" if self.idioma == "en" else IDIOMAS[self.idioma]["nombre"]
        return texto + f" Responde únicamente en {nombre}, sin nada de español."

    async def cambiar_idioma(self, nuevo: str) -> None:
        self.idioma = nuevo
        await self.update_instructions(instrucciones(nuevo, self.modo))

    # ---------------------------------------------------------------- candado de turno
    def abrir_turno(self, repetir: bool = False) -> None:
        """El estudiante habló o hizo algo en la pantalla: el agente puede responder una vez."""
        self._turno += 1
        self._abierto = True
        self._extra = False
        self._hablo_turno = 0
        self._pregunto_turno = False
        self._pidio_repetir = repetir

    def cerrar_turno(self) -> None:
        self._abierto = False
        self._extra = False

    def permitir_una_mas(self) -> None:
        """Una herramienta trae algo que sí hay que decir (los resultados): se permite una generación más."""
        self._extra = True

    def _filtro_voz(self, oracion: str) -> str:
        """Descarta preguntas repetidas: la misma pregunta no se dice dos veces seguidas."""
        if "?" not in oracion:
            return oracion
        n = _norm(oracion)
        if not self._pidio_repetir and _parecida(n, self._ultima_pregunta):
            self._paso.descartadas.append("[repetida] " + oracion)
            return ""
        self._pregunto_turno = True
        self._ultima_pregunta = n
        return oracion

    async def decir(self, texto: str) -> None:
        """Dice un texto fijo (sin LLM) y deja el turno cerrado esperando al estudiante."""
        self.cerrar_turno()
        self._ultimo_dicho = texto
        if "?" in texto:
            self._ultima_pregunta = _norm(re.split(r"(?<=[.!])\s+", texto.split("?")[0])[-1] + "?")
        self.session.say(texto, allow_interruptions=False)

    async def callar(self) -> None:
        """Corta lo que esté diciendo o generando (para responder a un toque en la pantalla)."""
        try:
            await self.session.interrupt(force=True)
        except Exception as e:
            log.debug("interrupt: %s", e)
        try:
            self.session.clear_user_turn()
        except Exception:
            pass

    # ---------------------------------------------------------------- voz limpia
    async def tts_node(self, text, model_settings):
        """Último filtro antes de Fish Audio: fórmulas y símbolos se dicen con palabras o se quitan."""
        idioma = self.idioma

        async def limpio():
            async for t in text:
                h = hablable(t, idioma)
                if h:
                    yield h + " "

        async for frame in Agent.default.tts_node(self, limpio(), model_settings):
            yield frame

    async def llm_node(self, chat_ctx: llm.ChatContext, tools: list, model_settings):
        """Pasa la salida del LLM por el filtro y respeta el candado de turno."""
        if not self._abierto and not self._extra:
            log.info("Generación bloqueada: el turno ya terminó; se espera al estudiante")
            return
        extra = self._extra and not self._abierto
        if extra:
            self._extra = False
            self._pregunto_turno = False
        turno = self._turno
        limp = Limpiador(self.idioma, filtro=self._filtro_voz)
        self._paso = limp
        dicho, herramientas = [], False
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            if isinstance(chunk, str):
                t = limp.feed(chunk)
                if t:
                    dicho.append(t)
                    yield t
                continue
            if isinstance(chunk, llm.ChatChunk) and chunk.delta:
                if chunk.delta.tool_calls:
                    herramientas = True
                if chunk.delta.content:
                    t = limp.feed(chunk.delta.content)
                    if t:
                        dicho.append(t)
                    chunk = chunk.model_copy(update={"delta": chunk.delta.model_copy(update={"content": t or None})})
                    if not t and not chunk.delta.tool_calls:
                        continue
            elif isinstance(chunk, llm.FunctionToolCall):
                herramientas = True
            yield chunk
        resto = limp.flush()
        if resto:
            dicho.append(resto)
            yield resto
        if limp.descartadas:
            log.info("Texto descartado de la voz: %s", limp.descartadas)
        if dicho:
            self._ultimo_dicho = "".join(dicho)
        if turno != self._turno:
            return                      # mientras tanto se abrió otro turno (p. ej. tocó Saltar)
        if dicho:
            self._hablo_turno += 1
        # Fin del texto del LLM: si ya preguntó, si habló sin herramientas pendientes,
        # o si ya habló dos veces en este turno, el turno se cierra.
        if extra or self._pregunto_turno or (dicho and not herramientas) or self._hablo_turno >= 2:
            if self._abierto:
                log.info("Turno cerrado: %s", "ya preguntó" if self._pregunto_turno else "terminó de hablar")
            self.cerrar_turno()

    def _ya_pregunto(self) -> bool:
        return "?" in self._paso.visto or self._pregunto_turno

    # ---------------------------------------------------------------- ignorar muletillas y eco
    async def on_user_turn_completed(self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage) -> None:
        texto = _norm(new_message.text_content or "")
        if not texto or len(texto) < 2 or texto in MULETILLAS:
            log.info("Turno ignorado (vacío o muletilla): %r", new_message.text_content)
            raise StopResponse()
        palabras = texto.split()
        propias = set(_norm(self._ultimo_dicho).split())
        if len(palabras) >= 4 and sum(p in propias for p in palabras) / len(palabras) >= 0.8:
            log.info("Turno ignorado (eco de la voz del agente): %r", new_message.text_content)
            raise StopResponse()
        self.abrir_turno(repetir=bool(PIDE_REPETIR.search(texto)) or texto in {"que", "como", "what", "perdon", "sorry"})
        # Confirmación pendiente y el estudiante dijo un sí o un no corto: se resuelve sin el LLM
        if self._confirmacion:
            si = respuesta_corta(texto)
            if si is not None:
                data = await self._api("confirmar", {"si": si})
                if data.get("ok"):
                    log.info("Confirmación por voz: %s", "sí" if si else "no")
                    nota = await self.hablar_servidor(data)
                    if nota:      # el LLM debe hablar (resultados, dictamen, traducción): se le pasa la nota en este turno
                        turn_ctx.add_message(role="system", content=nota)
                        return
                    chat = self.chat_ctx.copy()
                    chat.add_message(role="user", content=new_message.text_content or "")
                    await self.update_chat_ctx(chat)
                    raise StopResponse()

    # ---------------------------------------------------------------- lo que dice el sistema
    async def hablar_servidor(self, data: dict) -> str | None:
        """Dice el texto exacto que arma el servidor (pregunta, confirmación, siguiente paso).
        Devuelve una nota para el LLM cuando debe hablar él (explicar resultados, traducir, crear el test)."""
        if not data.get("ok", True):
            self._confirmacion = None
            return self.en_idioma(NOTA + f"No se pudo registrar ({data.get('error', '')[:120]}). Pide con amabilidad que lo repita. Termina tu turno.")
        self._confirmacion = data.get("por_confirmar")
        voz = data.get("voz_en") if self.idioma == "en" else data.get("voz") if self.idioma == "es" else None
        exp = data.get("explicar")
        if exp:
            self.permitir_una_mas()
            pre = f"Empieza diciendo: {data['voz']} " if data.get("voz") else ""
            if exp == "recomendacion":
                return self.en_idioma(NOTA + pre + "Ya se calcularon las carreras y están en pantalla:\n" + data.get("recomendacion", "") +
                                      "\nAhora explica solo la primera carrera según el paso ocho y pide que califique el video. "
                                      "No hagas ninguna otra pregunta de la entrevista.")
            if exp == "dictamen":
                return self.en_idioma(NOTA + pre + "Test terminado. Explica el resultado según el paso seis: " + data.get("dictamen", ""))
            if exp == "crear_test":
                return self.en_idioma(NOTA + "El caso está confirmado y la carrera no está en el catálogo: llama ahora a crear_test_personalizado "
                                      "con seis preguntas de su carrera, dos por nivel, sin decir nada antes.")
        if voz:
            await self.decir(voz)
            return None
        if data.get("voz"):          # otro idioma: el LLM lo traduce, completo y sin agregar nada
            self.permitir_una_mas()
            return self.en_idioma(NOTA + "Di exactamente esto, traducido al idioma de la conversación, completo y sin agregar nada; "
                                  "luego termina tu turno: " + data["voz"])
        return None

    async def hablar_evento(self, data: dict, nota_chat: str | None = None) -> None:
        """Algo pasó en la pantalla (tocó una opción, confirmó, saltó): se corta lo que dice y habla una vez."""
        await self.callar()
        if nota_chat:
            chat = self.chat_ctx.copy()
            chat.add_message(role="system", content=nota_chat)
            await self.update_chat_ctx(chat)
        self.abrir_turno()
        nota = await self.hablar_servidor(data)
        if nota:
            self.session.generate_reply(instructions=nota)
        else:
            self.cerrar_turno()

    async def saltar(self, ev: dict) -> None:
        """El estudiante tocó "Saltar pregunta": se dice la siguiente una sola vez."""
        data = ev.get("data") or {}
        saltada = data.get("saltada") or {}
        nota = f"{NOTA}El estudiante tocó Saltar en la pregunta «{saltada.get('texto', '')}». Quedó omitida: no la vuelvas a hacer ni la guardes."
        if saltada.get("tipo") == "test":
            nota += f" No llames a responder_pregunta para la pregunta {saltada.get('numero')}."
        await self.hablar_evento(data, nota)

    @function_tool()
    async def confirmar(
        self, context: RunContext,
        si: Annotated[bool, Field(description="Verdadero si el estudiante confirmó que es correcto; falso si dijo que no")],
    ) -> str | None:
        """Registra la respuesta del estudiante a la confirmación que le hizo el sistema (¿Es correcto? / ¿Confirmas tu respuesta?)."""
        return await self.hablar_servidor(await self._api("confirmar", {"si": si}))

    # ---------------------------------------------------------------- helpers
    async def _api(self, path: str, payload: dict | None = None) -> dict:
        try:
            r = await self.http.post(f"{WEB_URL}/internal/sesiones/{self.sid}/{path}", json=payload or {},
                                     headers={"X-Internal-Token": INTERNAL_TOKEN}, timeout=20)
            if r.status_code >= 400:
                try:
                    detalle = r.json().get("detail")
                except Exception:
                    detalle = r.text[:200]
                log.warning("API %s → %s: %s", path, r.status_code, detalle)
                return {"ok": False, "error": str(detalle)}
            data = r.json()
        except Exception as e:
            log.exception("Error llamando a %s", path)
            return {"ok": False, "error": str(e)}
        asyncio.create_task(notificar_ui(self.ctx, {"evento": path}))
        return data

    def _tras_guardar(self, data: dict, extra: str = "") -> str | None:
        """Qué hacer después de guardar. None = no generar otra respuesta (ya preguntó)."""
        if data.get("recomendacion"):
            self.permitir_una_mas()      # los resultados sí se explican aunque ya haya hablado
            return self.en_idioma(NOTA + "Ya se calcularon las carreras y están en pantalla:\n" + data["recomendacion"] +
                                  "\nAhora explica solo la primera carrera según el paso ocho y pide que califique el video. "
                                  "No hagas ninguna otra pregunta de la entrevista.")
        if self._ya_pregunto():
            return None
        if not data.get("ok", True):
            return NOTA + "No se pudo guardar. Sigue con la conversación sin mencionarlo."
        faltan = data.get("faltan") or []
        if not faltan:
            return NOTA + "Todo guardado. No agregues nada."
        pregunta = PREGUNTAS_EN[faltan[0]] if self.idioma == "en" else PREGUNTAS[faltan[0]]
        return self.en_idioma(NOTA + extra + "Guardado. Di una validación breve de una frase y luego haz exactamente esta pregunta "
                              f"(traducida al idioma de la conversación si no es español), y termina tu turno: {pregunta}")

    @function_tool()
    async def ofrecer_cita_psicologo(self, context: RunContext) -> str | None:
        """Muestra en pantalla el formulario para agendar una reunión de Teams con el psicólogo."""
        data = await self._api("agenda")
        if self._ya_pregunto():
            return None
        if data.get("teams_disponible"):
            return NOTA + "Formulario visible. Pídele que escriba su nombre, su correo si tiene, y elija un horario en pantalla. Luego espera."
        return NOTA + ("Formulario visible; la solicitud quedará registrada y el equipo de psicología lo contactará. "
                       "Pídele que llene sus datos en pantalla y espera.")

    @function_tool()
    async def finalizar_entrevista(
        self, context: RunContext,
        resumen: Annotated[str, Field(description="Resumen para el psicólogo: intereses, fortalezas, situación, carreras exploradas, dudas y ánimo del estudiante")],
        sugerencias: Annotated[Optional[str], Field(description="Sugerencias de seguimiento para el psicólogo")] = None,
    ) -> str | None:
        """Cierra la entrevista y envía el contexto por correo al psicólogo."""
        await self._api("finalizar", {"resumen": resumen, "sugerencias": sugerencias})
        self.finalizada = True
        if self._paso.visto.strip():
            return None
        return NOTA + "Despídete con una frase breve de ánimo."


class Orientadora(AgenteBase):
    """Lucía: orientación vocacional para estudiantes de colegio."""

    def __init__(self, ctx: JobContext, http: httpx.AsyncClient, idioma: str = "es") -> None:
        super().__init__(ctx, http, idioma, "eleccion", SALUDO_EN if idioma == "en" else SALUDO)

    # ---------------------------------------------------------------- herramientas
    @function_tool()
    async def guardar_intereses(
        self, context: RunContext,
        texto: Annotated[str, Field(description="Lo que dijo el estudiante, resumido con sus palabras")],
        intereses: Annotated[list[Interes], Field(description="Una a cuatro etiquetas que mejor representen lo que disfruta")],
    ) -> str | None:
        """Guarda la respuesta a qué es lo que más disfruta hacer en su día."""
        return self._tras_guardar(await self._api("respuesta", {"pregunta": "disfruta", "texto": texto, "etiquetas": intereses}))

    @function_tool()
    async def guardar_clase_favorita(
        self, context: RunContext,
        texto: Annotated[str, Field(description="Lo que dijo el estudiante")],
        materias: Annotated[list[Materia], Field(description="Una a tres materias que mencionó o que más se parecen")],
    ) -> str | None:
        """Guarda la clase que más disfruta en el colegio."""
        return self._tras_guardar(await self._api("respuesta", {"pregunta": "clase", "texto": texto, "etiquetas": materias}))

    @function_tool()
    async def guardar_descripcion(
        self, context: RunContext,
        texto: Annotated[str, Field(description="Cómo se describió, con sus palabras")],
        rasgos: Annotated[list[Rasgo], Field(description="Dos a cuatro rasgos que lo describen")],
    ) -> str | None:
        """Guarda cómo se describe a sí mismo."""
        return self._tras_guardar(await self._api("respuesta", {"pregunta": "descripcion", "texto": texto, "etiquetas": rasgos}))

    @function_tool()
    async def guardar_ambiente(
        self, context: RunContext,
        texto: Annotated[str, Field(description="Lo que dijo el estudiante")],
        ambientes: Annotated[list[Ambiente], Field(description="Uno a tres ambientes de trabajo preferidos")],
    ) -> str | None:
        """Guarda en qué ambiente le gustaría trabajar."""
        return self._tras_guardar(await self._api("respuesta", {"pregunta": "ambiente", "texto": texto, "etiquetas": ambientes}))

    @function_tool()
    async def guardar_situacion_economica(
        self, context: RunContext,
        texto: Annotated[str, Field(description="Lo que contó sobre su situación económica")],
        nivel: Annotated[Literal["baja", "media", "alta"], Field(description=(
            "baja: necesita opción gratuita, beca o trabajar mientras estudia; "
            "media: puede costear una pública y quizá una privada accesible; alta: puede pagar una privada"))],
        necesita_trabajar: Annotated[Optional[bool], Field(description="Si necesitará trabajar mientras estudia; null si no se sabe")] = None,
        internet: Annotated[Optional[bool], Field(description="Si tiene internet en casa; null si no se sabe")] = None,
        computadora: Annotated[Optional[bool], Field(description="Si tiene computadora; null si no se sabe")] = None,
    ) -> str | None:
        """Guarda la situación económica (el sistema le pide confirmarla). Es un factor determinante para la recomendación."""
        return await self.hablar_servidor(await self._api("proponer", {"tipo": "economia", "datos": {
            "texto": texto, "nivel": nivel, "necesita_trabajar": necesita_trabajar, "internet": internet, "computadora": computadora}}))

    @function_tool()
    async def guardar_ubicacion(
        self, context: RunContext,
        pais: Annotated[str, Field(description="País, por ejemplo Honduras")],
        departamento: Annotated[Optional[str], Field(description="Departamento o estado")] = None,
        municipio: Annotated[Optional[str], Field(description="Municipio o ciudad")] = None,
        colonia: Annotated[Optional[str], Field(description="Colonia, barrio, aldea o caserío")] = None,
        zona: Annotated[Literal["urbana", "rural", "no_sabe"], Field(description="rural si dijo aldea, caserío o que vive en el campo")] = "no_sabe",
    ) -> str | None:
        """Guarda país, departamento, municipio y colonia del estudiante (el sistema le pide confirmarlo)."""
        return await self.hablar_servidor(await self._api("proponer", {"tipo": "ubicacion", "datos": {
            "pais": pais, "departamento": departamento, "municipio": municipio, "colonia": colonia, "zona": zona}}))

    @function_tool()
    async def guardar_comentario_extra(
        self, context: RunContext,
        texto: Annotated[str, Field(description="Lo que contó; vacío si no quiso agregar nada")],
        alerta_bienestar: Annotated[bool, Field(description="Verdadero si mencionó riesgo, violencia, abuso, querer hacerse daño o algo que requiera atención prioritaria")] = False,
        puede_mudarse: Annotated[Optional[bool], Field(description="Si dijo que podría mudarse a otra ciudad para estudiar; null si no se sabe")] = None,
    ) -> str | None:
        """Guarda la respuesta a si hay algo más que quiera contar sobre su situación."""
        return self._tras_guardar(await self._api("respuesta", {"pregunta": "extra", "texto": texto or "Nada más",
                                                                "alerta_bienestar": alerta_bienestar, "puede_mudarse": puede_mudarse}))

    @function_tool()
    async def recomendar_carreras(self, context: RunContext) -> str:
        """Vuelve a calcular las carreras recomendadas y las muestra en pantalla."""
        data = await self._api("recomendar")
        if not data.get("ok"):
            return NOTA + "No se pudo calcular. Discúlpate brevemente."
        self.permitir_una_mas()
        return NOTA + data["texto"] + "\nExplica solo la primera carrera y pide que califique el video."

    @function_tool()
    async def mostrar_carrera(self, context: RunContext, carrera: Annotated[CarreraId, Field(description="Identificador de la carrera")]) -> str | None:
        """Muestra en pantalla el video, temario y universidades de una carrera."""
        data = await self._api("enfoque", {"carrera": carrera})
        if self._ya_pregunto():
            return None
        return NOTA + (data.get("texto") or "No se pudo mostrar la carrera.") + " Coméntala en dos frases y pregunta qué le parece."

    @function_tool()
    async def elegir_carrera(self, context: RunContext, carrera: Annotated[CarreraId, Field(description="Identificador de la carrera elegida")]) -> str | None:
        """Registra la carrera que el estudiante decidió explorar como su opción principal."""
        data = await self._api("elegir", {"carrera": carrera})
        if self._ya_pregunto():
            return None
        return NOTA + (data.get("texto") or "") + " Menciona dos o tres materias del primer año y luego ofrece la reunión con el psicólogo."


class PreguntaTest(BaseModel):
    nivel: Literal["basico", "intermedio", "avanzado"]
    pregunta: str = Field(description="Pregunta clara que se pueda leer en voz alta: sin fórmulas, símbolos ni ecuaciones")
    opciones: list[str] = Field(description="Exactamente cuatro opciones cortas, sin fórmulas ni símbolos")
    correcta: int = Field(description="Índice de la opción correcta, de 0 a 3")


class Fabiola(AgenteBase):
    """Fabiola: ¿sigo en mi carrera? Test por etapas, sentimientos y dictamen. Cada respuesta se confirma."""

    def __init__(self, ctx: JobContext, http: httpx.AsyncClient, idioma: str = "es") -> None:
        super().__init__(ctx, http, idioma, "permanencia", SALUDO_FABIOLA_EN if idioma == "en" else SALUDO_FABIOLA)

    @function_tool()
    async def guardar_caso(
        self, context: RunContext,
        carrera_nombre: Annotated[Optional[str], Field(description="Nombre de la carrera tal como lo dijo; null si no lo dijo en esta respuesta")] = None,
        carrera_id: Annotated[Optional[Literal[tuple(CARRERA_IDS) + ("otra",)]], Field(description="Carrera del catálogo que coincide; otra si no está; null si no se sabe")] = None,  # type: ignore[valid-type]
        universidad: Annotated[Optional[str], Field(description="Universidad; null si no la dijo")] = None,
        anio: Annotated[Optional[int], Field(description="Año que cursa, de uno a diez; null si no lo dijo")] = None,
        motivos: Annotated[list[Motivo], Field(description="Motivos de duda que mencionó en esta respuesta")] = [],
        satisfaccion: Annotated[Optional[int], Field(description="Del uno al cinco, qué tanto le gusta su carrera; null si no lo dijo")] = None,
        texto: Annotated[Optional[str], Field(description="Lo que contó, resumido con sus palabras")] = None,
        alerta_bienestar: Annotated[bool, Field(description="Verdadero si mencionó riesgo, violencia, abuso o querer hacerse daño")] = False,
    ) -> str | None:
        """Guarda lo que el estudiante acaba de responder sobre su caso. El sistema le pide confirmarlo."""
        data = await self._api("proponer", {"tipo": "caso", "datos": {
            "carrera_nombre": carrera_nombre, "carrera_id": None if carrera_id == "otra" else carrera_id,
            "universidad": universidad, "anio": anio, "motivos": motivos, "satisfaccion": satisfaccion,
            "texto": texto, "alerta_bienestar": alerta_bienestar}})
        if alerta_bienestar:
            # Primero la contención: el LLM responde con empatía; la confirmación queda en pantalla
            self._confirmacion = data.get("por_confirmar")
            self.permitir_una_mas()
            return self.en_idioma(NOTA + "Guardado con alerta de bienestar. Responde con calma y empatía según el cuidado especial y "
                                  "ofrece la reunión con el psicólogo. No hagas ninguna pregunta del test.")
        return await self.hablar_servidor(data)

    @function_tool()
    async def crear_test_personalizado(
        self, context: RunContext,
        preguntas: Annotated[list[PreguntaTest], Field(description="Seis preguntas: dos básicas, dos intermedias y dos avanzadas")],
    ) -> str | None:
        """Crea el test cuando la carrera del estudiante no está en el catálogo."""
        return await self.hablar_servidor(await self._api("test/iniciar", {"preguntas": [p.model_dump() for p in preguntas]}))

    @function_tool()
    async def responder_pregunta(
        self, context: RunContext,
        opcion: Annotated[Literal["A", "B", "C", "D"], Field(description="Letra de la opción que eligió")],
        numero: Annotated[Optional[int], Field(description="Número de la pregunta, si lo sabes")] = None,
    ) -> str | None:
        """Registra la opción que eligió en la pregunta actual del test. El sistema le pide confirmarla."""
        return await self.hablar_servidor(await self._api("proponer", {"tipo": "test", "datos": {"opcion": opcion, "numero": numero}}))

    @function_tool()
    async def guardar_sentimiento(
        self, context: RunContext,
        valor: Annotated[int, Field(description="Del uno (muy mal) al cinco (muy bien)")],
        texto: Annotated[str, Field(description="Lo que dijo sobre cómo se sintió")] = "",
    ) -> str | None:
        """Guarda cómo se sintió el estudiante en la etapa que acaba de terminar. El sistema le pide confirmarlo."""
        return await self.hablar_servidor(await self._api("proponer", {"tipo": "sentimiento", "datos": {
            "valor": max(1, min(5, int(valor))), "texto": texto}}))


def cerebras_llm(kwargs: dict) -> cerebras.LLM:
    """LLM de Cerebras sin razonamiento en la respuesta: con reasoning_format=hidden el modelo
    no devuelve su análisis interno (en inglés), así que nunca puede llegar a la voz."""
    m = cerebras.LLM(**kwargs)
    fmt = os.getenv("REASONING_FORMAT", "hidden").strip()
    if fmt and fmt != "default":
        m._opts.extra_body = {"reasoning_format": fmt}
    return m


async def notificar_ui(ctx: JobContext, payload: dict) -> None:
    """Avisa a la página (RPC) que hay datos nuevos para que se actualice."""
    for p in list(ctx.room.remote_participants.values()):
        if p.kind == rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
            continue
        try:
            await ctx.room.local_participant.perform_rpc(
                destination_identity=p.identity, method="ui.actualizar", payload=json.dumps(payload), response_timeout=5)
        except Exception as e:
            log.debug("RPC ui.actualizar falló: %s", e)


async def entrypoint(ctx: JobContext):
    await ctx.connect()
    http = httpx.AsyncClient()

    # El idioma elegido en la página llega en la metadata del participante
    estudiante = await ctx.wait_for_participant()
    try:
        meta = json.loads(estudiante.metadata or "{}")
    except json.JSONDecodeError:
        meta = {}
    idioma = meta.get("idioma", "es")
    modo = "permanencia" if meta.get("modo") == "permanencia" else "eleccion"
    if idioma not in IDIOMAS:
        idioma = "es"
    log.info("Sesión %s en idioma %s, modo %s", ctx.room.name, idioma, modo)

    llm_kwargs = {"model": os.getenv("CEREBRAS_MODEL", "gpt-oss-120b"), "parallel_tool_calls": False, "temperature": 0.4}
    if "gpt-oss" in llm_kwargs["model"]:
        llm_kwargs["reasoning_effort"] = os.getenv("REASONING_EFFORT", "low")

    session = AgentSession(
        stt=soniox.STT(params=soniox.STTOptions(model="stt-rt-v4", language_hints=IDIOMAS[idioma]["stt"])),
        llm=cerebras_llm(llm_kwargs),
        tts=fishaudio.TTS(model="s2.1-pro", voice_id=FABIOLA_VOICE_ID if modo == "permanencia" else VOICE_ID,
                          api_key=os.getenv("FISH_AUDIO_API_KEY") or os.getenv("FISH_API_KEY")),
        turn_handling={
            "endpointing": {"min_delay": float(os.getenv("MIN_ENDPOINTING_DELAY", "0.8"))},
            # No se interrumpe al agente y se descarta el audio que entra mientras habla
            "interruption": {"enabled": False, "discard_audio_if_uninterruptible": True},
            # Sin generación anticipada: solo se responde a turnos confirmados
            "preemptive_generation": {"enabled": False},
        },
        max_tool_steps=3,
    )
    agente = Fabiola(ctx, http, idioma) if modo == "permanencia" else Orientadora(ctx, http, idioma)

    # Eventos que manda la página: calificación del video, carrera tocada, cita agendada
    @ctx.room.local_participant.register_rpc_method("orientador.evento")
    async def on_evento(data: rtc.RpcInvocationData) -> str:
        try:
            ev = json.loads(data.payload or "{}")
        except json.JSONDecodeError:
            return "json invalido"
        tipo = ev.get("tipo")
        if tipo == "calificacion":
            instr = (f"{NOTA}El estudiante calificó en pantalla el video de {ev.get('nombre')} con {ev.get('puntaje')} de cinco estrellas. "
                     "Reacciona en una o dos frases según el paso nueve y termina tu turno.")
        elif tipo == "enfoque":
            # Cambio silencioso: el estudiante está viendo el video; no hablar encima de él
            nota = (f"{NOTA}El estudiante abrió en pantalla la carrera {ev.get('nombre')} (identificador {ev.get('carrera')}) "
                    "y está viendo su video. No digas nada hasta que hable o califique.")
            ctx_chat = agente.chat_ctx.copy()
            ctx_chat.add_message(role="system", content=nota)
            await agente.update_chat_ctx(ctx_chat)
            return "ok"
        elif tipo == "video_fin":
            instr = (f"{NOTA}El estudiante terminó de ver el video de {ev.get('nombre')}. Pregúntale en una frase qué le pareció "
                     "y pídele que lo califique con las estrellas. Termina tu turno.")
        elif tipo == "idioma":
            nuevo = ev.get("idioma")
            if nuevo not in IDIOMAS or nuevo == agente.idioma:
                return "ignorado"
            await agente.cambiar_idioma(nuevo)
            instr = (f"{NOTA}El estudiante cambió el idioma a {IDIOMAS[nuevo]['nombre']}. Desde ahora sigue la regla de idioma. "
                     "Avísale en una frase corta en el nuevo idioma y repite la última pregunta pendiente que le hiciste. Termina tu turno.")
        elif tipo in ("propuesta", "confirmacion"):
            # Tocó una opción o una carita (propuesta) o el botón Confirmar/Corregir (confirmacion)
            await agente.hablar_evento(ev.get("data") or {})
            return "ok"
        elif tipo == "saltar":
            await agente.saltar(ev)
            return "ok"
        elif tipo == "cita":
            if ev.get("estado") == "agendada":
                instr = (f"{NOTA}La reunión de Teams quedó agendada para {ev.get('etiqueta')}. Confírmalo, dile que el enlace "
                         "está en pantalla y en su correo si lo escribió, y luego cierra la entrevista.")
            else:
                instr = (f"{NOTA}La solicitud de reunión quedó registrada pero no se creó en Teams automáticamente. "
                         "Dile que el equipo de psicología lo contactará para confirmar y luego cierra la entrevista.")
        else:
            return "ignorado"
        # Un toque en la pantalla abre un turno nuevo: se corta lo que estuviera diciendo y responde una vez
        await agente.callar()
        agente.abrir_turno(repetir=tipo == "idioma")
        session.generate_reply(instructions=agente.en_idioma(instr))
        return "ok"

    async def al_cerrar():
        if not agente.finalizada:
            try:
                await http.post(f"{WEB_URL}/internal/sesiones/{ctx.room.name}/cerrar",
                                headers={"X-Internal-Token": INTERNAL_TOKEN}, timeout=10)
            except Exception:
                log.warning("No se pudo marcar la sesión como cerrada")
        await http.aclose()

    ctx.add_shutdown_callback(al_cerrar)

    await session.start(agent=agente, room=ctx.room)
    fab = modo == "permanencia"
    if idioma in ("es", "en"):
        session.say(agente._ultimo_dicho)   # saludo fijo en español o inglés
    else:
        quien, rol, primera = ((FABIOLA, "orientadora universitaria", PREGUNTAS_CASO["carrera"]) if fab else
                               (PERSONA, "orientadora vocacional", PREGUNTAS["disfruta"]))
        agente.abrir_turno()
        session.generate_reply(instructions=agente.en_idioma(
            f"{NOTA}Saluda al estudiante siguiendo la regla de idioma: preséntate como {quien}, su {rol}, y haz esta primera "
            f"pregunta traducida: {primera} Termina tu turno."))


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name=os.getenv("ORIENTADOR_AGENT_NAME", "orientador"),
                              port=int(os.getenv("AGENT_HTTP_PORT", "8081"))))
