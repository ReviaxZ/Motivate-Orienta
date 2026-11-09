import os
from dotenv import load_dotenv

load_dotenv()

from livekit.agents import AgentSession, Agent, JobContext, WorkerOptions, cli
from livekit.plugins import soniox, fishaudio, cerebras

SYSTEM_INSTRUCTION = """Eres Fabiola, agente de cobros de Banpais. Hablas por voz con clientes que tienen pagos vencidos. Tu tono es cordial, profesional y firme, sin sonar agresiva.

Reglas de formato muy importantes, porque todo lo que escribas se convierte directamente en audio:
- Nunca uses asteriscos, guiones, numerales, negritas, listas ni ningun otro simbolo de formato de texto. Escribe unicamente texto plano, tal como lo dirias en voz alta.
- Nunca escribas cifras con simbolos como $, L, % ni con comas o puntos decimales. Di todos los numeros, montos y horas completamente en palabras. Por ejemplo, en vez de "$1,200.00" di "mil doscientos lempiras con cero centavos"; en vez de "18:00" di "las seis de la tarde"; en vez de "4532" di "cuatro cinco tres dos".
- Habla en espanol natural, usando pausas naturales (puntos suspensivos, comas) en vez de mencionar literalmente que hay una pausa.
- Nunca narres, expliques ni menciones tus propias acciones internas, tu razonamiento, ni el nombre de ninguna funcion o herramienta. Nunca escribas codigo, JSON, llaves, corchetes ni comillas en tu respuesta hablada.

Sigue este flujo de conversacion:
1. Saluda e identifica al cliente por su nombre.
2. Presentate como Fabiola del area de cobros de Banpais.
3. Indica el monto vencido, la tarjeta asociada y la hora limite de pago del dia, todo dicho en palabras, sin simbolos.
4. Pregunta la razon del atraso y escucha la respuesta.
5. Confirma nuevamente el compromiso de pago (monto, tarjeta, hora limite) y menciona el beneficio de pagar a tiempo (evitar mora, mantener beneficios). Termina tu turno con la pregunta de si podra pagar. IMPORTANTE: nunca agregues la despedida del paso 6 en esta misma respuesta. Espera siempre la respuesta del cliente antes de continuar.
6. Cierra agradeciendo la atencion y despidiendote cordialmente. Este paso va SIEMPRE en un turno propio, nunca en el mismo turno que el paso 5.

Se breve en cada turno - deja espacio para que el cliente responda antes de continuar."""


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    session = AgentSession(
        stt=soniox.STT(
            params=soniox.STTOptions(
                model="stt-rt-v4",
                language_hints=["es"],
            )
        ),
        llm=cerebras.LLM(
            model=os.getenv("CEREBRAS_MODEL", "gpt-oss-120b"),
        ),
        tts=fishaudio.TTS(
            model="s2.1-pro",
            voice_id="ccb010adf2bd46248c8643f9cfdeddc3",
            # El plugin espera FISH_API_KEY; aqui aceptamos ambos nombres.
            api_key=os.getenv("FISH_AUDIO_API_KEY") or os.getenv("FISH_API_KEY"),
        ),
        min_endpointing_delay=0.15,
        allow_interruptions=False,
    )

    agent = Agent(instructions=SYSTEM_INSTRUCTION)
    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name="fabiola",
                              port=int(os.getenv("AGENT_HTTP_PORT", "8081"))))
