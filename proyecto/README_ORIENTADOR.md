# Orienta: orientación vocacional por voz (Lucía y Fabiola)

Lucía es un agente de voz que entrevista a estudiantes de colegio. Con sus respuestas, su situación económica y el lugar donde viven, les recomienda carreras con universidades cercanas, video, temario, becas y un plan directo. Al terminar agenda una reunión de Teams y envía el contexto al psicólogo.

Usa la misma infraestructura que Fabiola: LiveKit Cloud, Soniox, Cerebras, Fish Audio, Docker Compose y la web del puerto 7878 expuesta con ngrok.

## Cómo levantarlo

```
docker compose up -d --build
ngrok http 7878
```

| URL | Para quién |
|---|---|
| `https://<tu-ngrok>/` | Estudiantes: Lucía, la orientadora (página principal). `/#<id-de-sesión>` abre los resultados de una sesión |
| `https://<tu-ngrok>/panel/` | Psicólogo: todas las sesiones de Lucía y Fabiola (usuario `panel`, contraseña `PANEL_PASSWORD` en `orientador.env`) |
| `https://<tu-ngrok>/fabiola/` | Fabiola (agente de cobros) |

La configuración del orientador vive en **`orientador.env`** (Graph, correo del psicólogo, contraseña del panel, YouTube).

## Arquitectura

```
Navegador ──WebRTC──► LiveKit Cloud ◄──── orientador (agente Lucía, Docker)
    │                                          │ HTTP interno (X-Internal-Token)
    └──HTTP /api/orientador──► web:7878 ◄──────┘
                                 ├─ motor.py   recomendación (afinidad × viabilidad)
                                 ├─ geo.py     país/depto/municipio/colonia → coordenadas (OpenStreetMap)
                                 ├─ graph.py   Teams + correo (Microsoft Graph)
                                 └─ db.py      SQLite (volumen orientador-datos)
```

- El agente nunca calcula nada por su cuenta. Cada respuesta se guarda en la web con etiquetas de un vocabulario fijo (`web/data/vocabulario.json`). Así el resultado es reproducible y auditable.
- Cada vez que cambian los datos, el agente avisa a la página con un RPC (`ui.actualizar`) y la página se refresca.
- La página manda al agente la calificación del video, la carrera que tocó y el resultado de la cita (RPC `orientador.evento`). Lucía reacciona en voz.

## Flujo de la entrevista

1. Saludo: "Hola estimado… ¿qué es lo que más disfrutas hacer en tu día?" → `intereses`
2. ¿Cuál es la clase que más disfrutas? → `materias`
3. ¿Cómo te describirías a ti mismo? → `rasgos`
4. ¿En qué ambiente te gustaría trabajar? (oficina, campo…) → `ambientes`
5. ¿Cuál es tu situación económica actual? → nivel `baja / media / alta`, necesita trabajar, internet, computadora
6. País, departamento, municipio y colonia → se guardan y se geocodifican. Se marca la zona como urbana o rural.
7. ¿Algo más que te gustaría contar? → comentario, alerta de bienestar y si puede mudarse
8. Recomendación. Se muestran en pantalla:
   - las 3 carreras con su puntaje;
   - el video y las estrellas para calificarlo;
   - el temario por año;
   - un mapa con las universidades que ofrecen la carrera;
   - el plan directo, si aplica;
   - otras opciones, cada una con su universidad gratuita más cercana.
9. Calificación del video. Con 4 o 5 estrellas se ofrece elegir la carrera. Con 3 o menos se propone la siguiente.
10. Elección de carrera, con el temario del primer año.
11. Cita por Teams con el psicólogo. El estudiante escribe su nombre y correo y elige un horario.
12. Cierre. Se envía al psicólogo el correo con el contexto completo. Si el estudiante cuelga antes, se envía igual, marcado como "incompleta".

## Cómo se determinan los datos

**Afinidad (0–100).** Cada carrera tiene un perfil ponderado de 1 a 3 en cuatro dimensiones: intereses (35 %), materias (25 %), rasgos (20 %) y ambiente (20 %). Las etiquetas del estudiante se cruzan con ese perfil.

**Viabilidad (0–1).** Mide qué tan posible es estudiar la carrera:
- Considera la mejor sede que ofrece la carrera.
- El costo pesa según el nivel económico. Una pública vale 1. Una privada cara vale 0.1 si el nivel es bajo.
- La distancia descuenta a partir de 30 km en línea recta. Si puede mudarse, el descuento se limita.
- Si necesita trabajar y la sede está lejos, se penaliza.
- La opción a distancia cuenta más si tiene internet.

**Puntaje.** `afinidad × (1 − w + w × viabilidad)`, donde `w` vale 0.5 si el nivel es bajo, 0.3 si es medio y 0.1 si es alto. Así la situación económica es un factor determinante. La calificación del video suma o resta 4 puntos por cada estrella sobre o bajo 3.

**Zona alejada.** La sede accesible más cercana está a más de 60 km, o el estudiante es de zona rural y está a más de 30 km, o vive fuera de Honduras. En ese caso, o si el nivel económico es bajo, se arma el **plan directo** en cuatro fases:
1. Ahora: preparación y documentos.
2. Admisión: pasos de la universidad objetivo.
3. Becas aplicables: SEDESOL, Mi Bienestar UNAH, UNACIFOR, Zamorano y SEDESOL, EARTH.
4. Opciones gratis o a distancia: UNAH CRAED y telecentros, UPNFM a distancia, INFOP, Fundación Carlos Slim, Khan Academy.

**Filtros del mapa.** Se activan solos según el nivel económico:
- Bajo: públicas, con beca y a distancia.
- Medio: lo anterior más las privadas accesibles.
- Alto: todas.

El estudiante puede activar o desactivar cada tipo.

## Fabiola: ¿sigo en mi carrera?

En la barra lateral izquierda se elige la orientadora:
- **Lucía**: para estudiantes de colegio que eligen carrera.
- **Fabiola**: para estudiantes universitarios que dudan si seguir o dejar su carrera.

Flujo de Fabiola:
1. **Caso:** qué carrera estudia, en qué universidad y en qué año; qué le hace dudar (motivos); del uno al cinco, qué tanto le gusta hoy.
2. **Test en tres etapas:** seis preguntas de opción múltiple de su carrera, dos básicas, dos intermedias y dos avanzadas (`web/data/test_carreras.json`, 192 preguntas para las 32 carreras).
   - Responde diciendo la letra o tocándola en pantalla.
   - Si la carrera no está en el catálogo, Fabiola crea seis preguntas propias.
3. **Cómo se sintió** al final de cada etapa, del uno al cinco, por voz o con las caritas.
4. **Dictamen orientativo:**
   - Índice de permanencia = 35 % bienestar + 25 % satisfacción + 25 % conocimiento + 15 % señal vocacional.
   - Conocimiento = puntaje del test frente a lo esperado para su año: 40 en primero, 55 en segundo, 70 desde tercero.
   - Resultados posibles: continuar, continuar con apoyo, continuar y reevaluar, o explorar un cambio de carrera.
   - Incluye recomendaciones (tutorías, becas, horarios, psicólogo) y un botón para pasar con Lucía.
5. Cita por Teams y correo al psicólogo con todo el contexto, igual que con Lucía.

La voz de Fabiola se puede cambiar con `FABIOLA_VOICE_ID` en el compose; por defecto usa la misma voz.

## Interfaz

- **Tarjetas de carrera:** al tocar una tarjeta (o una de "Otras opciones"), el video empieza solo. Mientras el video suena, el micrófono se pausa para que Lucía no "escuche" el video. Si Lucía empieza a hablar, el video se pausa. Al terminar el video, Lucía pide la calificación.
- **Plan de estudios y contacto:** cada universidad del mapa y de la carrera enfocada tiene su enlace directo al plan de estudios de esa carrera, o a la oferta académica, y su teléfono o correo cuando está verificado.
  - UNAH: página de la Feria Vocacional de cada carrera, con el PDF del plan y los correos de coordinación por centro.
  - UNITEC, UTH, USAP, UNICAH, UPNFM y UNACIFOR: ficha de universidades.hn con el plan por ciclos.
  - UNAG, UNACIFOR y Zamorano: PDF oficiales.
- **Nueva sesión:** el botón "+" del encabezado limpia todo y deja listo un registro nuevo.
- **Todas las sesiones:** el botón de lista abre el panel. Desde el panel, "Abrir vista del estudiante" muestra los resultados de cualquier sesión.
- **Idioma:** el selector "Idioma de Lucía" cambia los tres modelos.
  - El STT de Soniox usa como pista el idioma elegido.
  - El LLM recibe la regla de idioma.
  - El TTS de Fish Audio detecta el idioma del texto.
  - Se puede cambiar a mitad de la conversación.
  - Español e inglés funcionan completos.
  - La regla es estricta: la orientadora habla **solo** en el idioma elegido y traduce todo, incluidas las notas internas.
  - En inglés, además, un filtro descarta cualquier frase en español que se cuele.
  - Garífuna, miskito, náhuatl, maya yucateco y wayuunaiki son **experimentales**: ninguno de los tres proveedores los soporta oficialmente. La calidad depende del modelo, y el estudiante responde en español porque la transcripción no los reconoce.

## Datos editables

Todos están en `web/data/`. Regenera los JSON con `python build/vocab_carreras.py` y `python build/universidades.py`, o edita los JSON directamente.

| Archivo | Contenido |
|---|---|
| `carreras.json` | 32 carreras: perfil, temario de referencia, campo laboral, rutas cortas, `video.youtube_id` |
| `universidades.json` | 10 universidades y 33 sedes con coordenadas aproximadas por ciudad, carreras por sede, costo y admisión |
| `oportunidades.json` | Becas, educación a distancia y opciones gratuitas, con requisitos y cómo aplicar |
| `geografia.json` | Cabeceras departamentales, de respaldo si no hay geocodificación |

**Videos.** Cada carrera trae 3 videos de YouTube en `video.youtube_ids`. La página usa el reproductor de YouTube: si un video no se puede reproducir, pasa al siguiente. Con `YOUTUBE_API_KEY` se agregan candidatos de una búsqueda segura. Si ninguno funciona, queda el botón a la búsqueda de YouTube.

**Voz limpia.** A Fish Audio solo llega la respuesta para el estudiante:
- Cerebras se llama con `reasoning_format: hidden`, así el razonamiento interno de gpt-oss (en inglés) no viene en la respuesta. Se cambia con `REASONING_FORMAT` en el compose (`default` lo desactiva).
- Todo lo que genera el LLM pasa por `orientador/limpieza.py` antes de ir a voz y a la transcripción. Se descartan el JSON de argumentos, los nombres de herramientas, los tokens internos de gpt-oss y las notas de los resultados.
- También se descartan las frases de razonamiento o de instrucciones ("we need to…", "the user said…", "el usuario dijo…", "según las instrucciones…") y, si la conversación no es en inglés, cualquier frase en inglés.
- En el log del orientador cada frase descartada aparece con su motivo: `[meta]`, `[en]`, `[es]` o `[repetida]`.

**Turnos (candado).** La orientadora habla una sola vez por turno:
- En cuanto el texto del LLM termina con una pregunta, o termina sin herramientas pendientes, el turno se cierra. Cualquier otra generación queda muda hasta que el estudiante hable o toque algo en la pantalla (calificar, responder, saltar, agendar).
- Si el modelo intenta decir otra vez casi la misma pregunta que ya hizo, esa frase se descarta de la voz. Solo se repite si el estudiante lo pide ("repítemela", "no te entendí").
- Los resultados de Lucía y el dictamen de Fabiola sí se explican aunque ya haya hablado en ese turno.
- No hay generación anticipada y no se interrumpe al agente: el audio que entra mientras habla se descarta.
- Las muletillas ("eh", "mmm") y el eco de su propia voz se ignoran.

**Confirmaciones paso a paso.** Las respuestas de selección no se guardan hasta que el estudiante las confirma, y no se pasa a la siguiente pregunta sin esa confirmación:
- **Fabiola:** carrera, universidad y año; motivos; qué tanto le gusta; cada respuesta del test; cómo se sintió en cada etapa.
- **Lucía:** situación económica y ubicación. Las preguntas abiertas (qué disfruta, clase, cómo se describe, ambiente, algo más) se guardan directo.
- La orientadora dice lo que entendió y pregunta "¿Es correcto?" (en el test, "Elegiste la opción B: … ¿Confirmas tu respuesta?").
  - Si el estudiante dice que **sí**, se guarda y sigue.
  - Si dice que **no**, vuelve a hacer la pregunta.
  - Si corrige en la misma frase ("no, es tercer año"), se propone el dato corregido.
- Un "sí" o "no" corto se resuelve directo, sin pasar por el LLM, así que no hay demora ni variación.
- En pantalla aparecen los botones **Sí, es correcto** y **Corregir**. En el test, tocar una opción o una carita la marca y pide confirmar.
- Las preguntas del test, la confirmación, el resultado ("¡Correcto!" / "La respuesta correcta es la C…") y la siguiente pregunta los arma el servidor y se dicen con el texto exacto en español e inglés. En los demás idiomas el LLM los traduce.

**Sin símbolos en la voz.** Fish Audio no recibe símbolos ni fórmulas:
- Las expresiones simples se dicen con palabras: "F igual a m por a", "x al cuadrado", "veinte por ciento", "tres entre cuatro".
- Las complejas (LaTeX, sumatorias, integrales) se cambian por "la fórmula que ves en la pantalla".
- Los enlaces, correos, emoticonos y caracteres especiales se quitan.
- La transcripción en pantalla conserva el texto original.

**Saltar pregunta.** La ficha muestra la pregunta actual con un botón **Saltar pregunta**. En el test de Fabiola también hay "Saltar esta pregunta" y, al preguntar cómo se sintió, "Prefiero no responder".
- La pregunta queda como **omitida**: en la entrevista no suma etiquetas; si se omite la situación económica se asume nivel medio; si se omite la ubicación no se usa la distancia; en el test cuenta como no acertada; un sentimiento omitido no entra en el bienestar.
- La orientadora dice "Está bien, pasemos a la siguiente" y hace la siguiente pregunta una sola vez (en español e inglés con el texto exacto, sin pasar por el LLM).
- La carrera en Fabiola no se puede saltar porque con ella se arma el test.
- Las omitidas se ven en la ficha, en el panel y en el correo al psicólogo.
- Los textos de las preguntas están en `web/data/preguntas.json` (los usan el agente y la web).

**Resultados automáticos.** Al completar las 7 respuestas, el servidor calcula las carreras sin esperar al agente. Si faltara alguna, el botón "Ver mis resultados" en la ficha permite calcularlas con las respuestas que ya hay.

## Correos (Resend)

Todos los correos van a `CORREOS_DESTINO` (en `orientador.env`, se pueden poner varios separados por comas):
- **Contexto de la entrevista** al terminar (o al colgar antes, marcado "incompleta").
- **Solicitud de reunión**, en cuanto el estudiante elige un horario. Si Teams no pudo crear la reunión, el correo dice que hay que confirmarla a mano.
- **Alerta de bienestar**, inmediata y con prioridad alta, la primera vez que el estudiante menciona algo grave.

Configuración en `orientador.env` (se usa la primera opción que esté completa):
1. **Gmail por SMTP**: permite enviar a cualquier dirección. `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER` (la cuenta de Gmail) y `SMTP_PASSWORD` con una **contraseña de aplicación** de Google (la contraseña normal no funciona). Se crea en myaccount.google.com/apppasswords y requiere la verificación en dos pasos activa.
2. **Resend**: `RESEND_API_KEY` y `RESEND_FROM`. Con el remitente de prueba `onboarding@resend.dev` **solo puede enviar al correo dueño de la cuenta de Resend**. Para enviar a otras direcciones, verifica un dominio en Resend y pon por ejemplo `Orienta <orienta@tudominio.com>`.
3. **Microsoft Graph** (Mail.Send).

En el panel, el botón **Enviar correo de prueba** confirma que llegan. Los correos que fallen quedan pendientes y se reenvían con "Reintentar cita y correo". Sin `RESEND_API_KEY` se usa Microsoft Graph (Mail.Send), como antes.

## Microsoft Graph (reuniones de Teams)

- **Pruebas:** en Graph Explorer, "Modify permissions", da consentimiento a **Calendars.ReadWrite** y **Mail.Send**, copia el token nuevo a `GRAPH_ACCESS_TOKEN` y ejecuta `docker compose up -d web`. El token caduca en unas horas.
- **Producción:** registra una aplicación en Entra ID con permisos de aplicación Calendars.ReadWrite y Mail.Send (requiere consentimiento de un administrador). Llena `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` y `GRAPH_USER` (el buzón organizador).
- Sin permisos, las citas y los correos quedan **pendientes** en el panel. El botón "Reintentar" los envía cuando el token ya es válido.
- La invitación de Teams lleva un texto genérico. El contexto sensible (situación económica, alerta de bienestar) va **solo** en el correo al psicólogo.

## Privacidad y cuidado

- La página avisa antes de empezar que las respuestas se guardan y se comparten con psicología.
- No se pide dirección exacta.
- Si el estudiante menciona riesgo, Lucía responde con empatía, menciona el 911 y marca **alerta de bienestar**. El correo sale como prioridad alta con "[ATENCIÓN PRIORITARIA]".
- Se limita a 12 sesiones por IP cada hora (`LIMITE_SESIONES_POR_IP_HORA`) para cuidar los créditos de las APIs cuando la URL de ngrok es pública.
