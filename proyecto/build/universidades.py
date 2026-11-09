"""Genera web/data/universidades.json, oportunidades.json y geografia.json.

Coordenadas de sedes: aproximadas al centro de la ciudad (suficiente para distancia y mapa).
Fuentes principales: Oferta educativa UNAH 2024 (estadistica.unah.edu.hn), notas de prensa
de admisiones 2026 (PHUMA), requisitos UNACIFOR, oferta publicada de universidades privadas.
"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "web" / "data"

CIUDADES = {
    "Tegucigalpa": ("Francisco Morazán", 14.0846, -87.1607),
    "San Pedro Sula": ("Cortés", 15.5040, -88.0250),
    "Santa Rosa de Copán": ("Copán", 14.7667, -88.7792),
    "Comayagua": ("Comayagua", 14.4514, -87.6375),
    "Choluteca": ("Choluteca", 13.3007, -87.1908),
    "Juticalpa": ("Olancho", 14.6667, -86.2192),
    "La Ceiba": ("Atlántida", 15.7597, -86.7822),
    "Olanchito": ("Yoro", 15.4810, -86.5745),
    "Danlí": ("El Paraíso", 14.0300, -86.5800),
    "Tela": ("Atlántida", 15.7744, -87.4597),
    "Puerto Cortés": ("Cortés", 15.8456, -87.9406),
    "Choloma": ("Cortés", 15.6144, -87.9530),
    "Gracias": ("Lempira", 14.5886, -88.5819),
    "Roatán": ("Islas de la Bahía", 16.3168, -86.5390),
    "Ocotepeque": ("Ocotepeque", 14.4333, -89.1833),
    "Marcala": ("La Paz", 14.1500, -88.0333),
    "Catacamas": ("Olancho", 14.8481, -85.8946),
    "Siguatepeque": ("Comayagua", 14.5980, -87.8300),
    "Valle del Yeguare (Zamorano)": ("Francisco Morazán", 14.0110, -87.0030),
    "El Progreso": ("Yoro", 15.4000, -87.8000),
    "La Esperanza": ("Intibucá", 14.3110, -88.1770),
    "Nacaome": ("Valle", 13.5300, -87.4900),
    "Santa Bárbara": ("Santa Bárbara", 14.9192, -88.2361),
}


def sede(id, nombre, ciudad, carreras, modalidad="presencial"):
    depto, lat, lng = CIUDADES[ciudad]
    return {"id": id, "nombre": nombre, "ciudad": ciudad, "departamento": depto, "lat": lat, "lng": lng,
            "carreras": carreras, "modalidad": modalidad}


ADMISION_UNAH = {
    "resumen": "Ingreso con la PHUMA (Prueba Hondureña Universitaria de Medición Académica). La UNAH abre varios procesos de admisión al año.",
    "pasos": [
        "Haz la prueba vocacional en línea en el portal de admisiones (es obligatoria antes de inscribirte).",
        "Inscríbete a la PHUMA en la plataforma digital de la UNAH dentro de las fechas del proceso.",
        "Paga la prueba (en el proceso de 2026 costó 500 lempiras, pago único) en banco o en línea.",
        "Sube tus documentos: identificación, fotografía tipo pasaporte y un correo electrónico activo.",
        "Recibe tu credencial digital por correo y presenta la prueba en la sede asignada.",
        "Consulta tus resultados en el portal de admisiones y elige tu carrera y centro.",
    ],
    "url": "https://admisiones.unah.edu.hn",
}

UNIVERSIDADES = [
    {
        "id": "unah", "nombre": "Universidad Nacional Autónoma de Honduras", "siglas": "UNAH",
        "tipo": "publica", "costo": "publica",
        "costo_texto": "Pública: matrícula de muy bajo costo.",
        "web": "https://www.unah.edu.hn",
        "admision": ADMISION_UNAH,
        "becas": ["unah_mi_bienestar", "sedesol_becas"],
        "sedes": [
            sede("unah_cu", "Ciudad Universitaria", "Tegucigalpa",
                 ["pedagogia", "arquitectura", "educacion_fisica", "lenguas", "psicologia", "periodismo", "trabajo_social",
                  "biologia", "microbiologia", "economia", "administracion", "contaduria", "informatica_administrativa",
                  "comercio_internacional", "mercadotecnia", "derecho", "medicina", "enfermeria", "nutricion",
                  "quimica_farmacia", "ing_civil", "ing_electrica", "ing_mecanica", "ing_industrial", "sistemas",
                  "odontologia"]),
            sede("unah_vs", "UNAH Campus Cortés (Valle de Sula)", "San Pedro Sula",
                 ["pedagogia", "psicologia", "periodismo", "biologia", "economia", "contaduria", "administracion",
                  "informatica_administrativa", "derecho", "medicina", "enfermeria", "ing_civil", "ing_electrica",
                  "ing_mecanica", "ing_industrial", "sistemas", "odontologia"]),
            sede("unah_curoc", "CUROC – Centro Universitario Regional de Occidente", "Santa Rosa de Copán",
                 ["administracion", "comercio_internacional", "sistemas", "agroindustrial"]),
            sede("unah_curc", "CURC – Centro Universitario Regional del Centro", "Comayagua",
                 ["periodismo", "administracion", "comercio_internacional", "agroindustrial"]),
            sede("unah_curlp", "CURLP – Centro Universitario Regional del Litoral Pacífico", "Choluteca",
                 ["comercio_internacional", "sistemas", "agroindustrial"]),
            sede("unah_curno", "CURNO – Centro Universitario Regional Nor-Oriental", "Juticalpa",
                 ["administracion", "comercio_internacional", "enfermeria", "agroindustrial"]),
            sede("unah_curla", "CURLA – Centro Universitario Regional del Litoral Atlántico", "La Ceiba",
                 ["administracion", "enfermeria", "agronomia", "forestal", "economia", "turismo"]),
            sede("unah_tec_aguan", "UNAH Tec Aguán", "Olanchito", ["agroindustrial"]),
            sede("unah_tec_danli", "UNAH Tec Danlí", "Danlí", ["informatica_administrativa", "enfermeria", "agroindustrial"]),
            sede("unah_tc_pcortes", "Telecentro Puerto Cortés", "Puerto Cortés", ["pedagogia"], "telecentro"),
            sede("unah_tc_choloma", "Telecentro Choloma", "Choloma", ["pedagogia"], "telecentro"),
            sede("unah_tc_gracias", "Telecentro Gracias", "Gracias", ["pedagogia"], "telecentro"),
            sede("unah_tc_roatan", "Telecentro Roatán", "Roatán", ["turismo"], "telecentro"),
            sede("unah_tc_ocotepeque", "Telecentro Ocotepeque", "Ocotepeque", ["pedagogia"], "telecentro"),
        ],
    },
    {
        "id": "upnfm", "nombre": "Universidad Pedagógica Nacional Francisco Morazán", "siglas": "UPNFM",
        "tipo": "publica", "costo": "publica",
        "costo_texto": "Pública: forma docentes (profesorados) a bajo costo.",
        "web": "https://www.upnfm.edu.hn",
        "admision": {
            "resumen": "Examen de admisión propio con inscripción en línea.",
            "pasos": [
                "Inscríbete en línea en la convocatoria de admisión.",
                "Paga el derecho a examen.",
                "Completa el Cuestionario de Propósito General (perfil vocacional).",
                "Genera tu carné de aspirante (obligatorio para el examen).",
                "Presenta el examen y consulta resultados en los canales oficiales.",
            ],
            "url": "https://www.upnfm.edu.hn",
            "contacto": "admision.consultas@upnfm.edu.hn",
        },
        "becas": ["sedesol_becas"],
        "sedes": [
            sede("upnfm_tgu", "Campus Central", "Tegucigalpa", ["pedagogia", "lenguas", "educacion_fisica"]),
            sede("upnfm_sps", "Centro Universitario San Pedro Sula", "San Pedro Sula", ["pedagogia", "lenguas", "educacion_fisica"]),
            sede("upnfm_ceiba", "Centro Universitario Regional La Ceiba", "La Ceiba", ["pedagogia"]),
            sede("upnfm_srosa", "Centro Universitario Regional Santa Rosa de Copán", "Santa Rosa de Copán", ["pedagogia"]),
            sede("upnfm_gracias", "Centro Regional Universitario Gracias", "Gracias", ["pedagogia"]),
            sede("upnfm_esperanza", "Centro Regional Universitario La Esperanza", "La Esperanza", ["pedagogia"]),
            sede("upnfm_choluteca", "Centro Regional Universitario Choluteca", "Choluteca", ["pedagogia"]),
            sede("upnfm_nacaome", "Centro Regional Universitario Nacaome", "Nacaome", ["pedagogia"]),
            sede("upnfm_juticalpa", "Centro Regional Universitario Juticalpa", "Juticalpa", ["pedagogia"]),
            sede("upnfm_sbarbara", "Centro Regional Universitario Santa Bárbara", "Santa Bárbara", ["pedagogia"]),
            sede("upnfm_danli", "Centro Regional Universitario Danlí", "Danlí", ["pedagogia"]),
        ],
    },
    {
        "id": "unag", "nombre": "Universidad Nacional de Agricultura", "siglas": "UNAG",
        "tipo": "publica", "costo": "publica",
        "costo_texto": "Pública, especializada en ciencias agrarias. Pregunta por internado y apoyos.",
        "web": "https://unag.edu.hn",
        "admision": {
            "resumen": "Proceso de admisión anual con prueba propia (en 2026 aplicaron más de 1,400 aspirantes).",
            "pasos": [
                "Revisa la convocatoria de admisión en el portal de la UNAG.",
                "Inscríbete y presenta los documentos que pidan.",
                "Presenta la prueba de admisión y consulta resultados.",
                "Pregunta por el internado y las ayudas para estudiantes de zonas rurales.",
            ],
            "url": "https://unag.edu.hn",
        },
        "becas": ["sedesol_becas"],
        "sedes": [sede("unag_catacamas", "Campus Catacamas", "Catacamas", ["agronomia", "veterinaria", "agroindustrial"])],
    },
    {
        "id": "unacifor", "nombre": "Universidad Nacional de Ciencias Forestales", "siglas": "UNACIFOR",
        "tipo": "publica", "costo": "publica",
        "costo_texto": "Pública, con comité de becas que evalúa la situación socioeconómica.",
        "web": "https://unacifor.edu.hn",
        "admision": {
            "resumen": "Ingreso con la PAA y expediente. Ingenierías piden 900 puntos y técnicos 700.",
            "pasos": [
                "Presenta la Prueba de Aptitud Académica (PAA).",
                "Llena la solicitud de admisión con foto y tres cartas de referencia (una de un docente).",
                "Reúne notas de los últimos tres años, título o constancia de graduación y certificado médico.",
                "Envía los documentos a admisiones@unacifor.edu.hn y docencia@unacifor.edu.hn.",
                "Solicita evaluación del comité de becas (considera PAA, situación socioeconómica y notas).",
            ],
            "url": "https://unacifor.edu.hn",
            "contacto": "Tel. 2720-2300 ext. 114",
        },
        "becas": ["unacifor_becas", "sedesol_becas"],
        "sedes": [sede("unacifor_sigua", "Campus Siguatepeque", "Siguatepeque", ["forestal", "turismo"])],
    },
    {
        "id": "zamorano", "nombre": "Universidad Zamorano (Escuela Agrícola Panamericana)", "siglas": "Zamorano",
        "tipo": "privada", "costo": "beca",
        "costo_texto": "Privada de alto costo, pero con becas para jóvenes hondureños (convenio SEDESOL 2026).",
        "web": "https://www.zamorano.edu",
        "admision": {
            "resumen": "Admisión con solicitud, examen y entrevista; solicita ayuda financiera al aplicar.",
            "pasos": ["Aplica en el sitio de admisiones de Zamorano.", "Solicita ayuda financiera o beca en el mismo proceso.",
                      "Pregunta por las becas del convenio con SEDESOL para hondureños."],
            "url": "https://www.zamorano.edu",
        },
        "becas": ["zamorano_sedesol"],
        "sedes": [sede("zamorano_campus", "Campus Valle del Yeguare", "Valle del Yeguare (Zamorano)", ["agronomia", "agroindustrial"])],
    },
    {
        "id": "ceutec", "nombre": "Centro Universitario Tecnológico", "siglas": "CEUTEC",
        "tipo": "privada", "costo": "accesible",
        "costo_texto": "Privada de costo accesible, horarios pensados para quien trabaja.",
        "web": "http://www.ceutec.unitec.edu",
        "admision": {"resumen": "Inscripción directa en el campus o en línea.", "pasos": ["Solicita información de admisión en el sitio de CEUTEC.", "Pregunta por descuentos y financiamiento."], "url": "http://www.ceutec.unitec.edu"},
        "becas": [],
        "sedes": [
            sede("ceutec_tgu", "CEUTEC Tegucigalpa", "Tegucigalpa",
                 ["economia", "contaduria", "periodismo", "enfermeria", "diseno_grafico", "turismo", "psicologia",
                  "mercadotecnia", "derecho", "administracion", "informatica_administrativa"]),
            sede("ceutec_sps", "CEUTEC San Pedro Sula", "San Pedro Sula",
                 ["contaduria", "enfermeria", "diseno_grafico", "psicologia", "mercadotecnia", "derecho", "administracion",
                  "informatica_administrativa"]),
            sede("ceutec_ceiba", "CEUTEC La Ceiba", "La Ceiba", ["contaduria", "administracion", "mercadotecnia", "derecho"]),
        ],
    },
    {
        "id": "uth", "nombre": "Universidad Tecnológica de Honduras", "siglas": "UTH",
        "tipo": "privada", "costo": "accesible",
        "costo_texto": "Privada de costo medio, con varios campus en el país.",
        "web": "https://www.uth.hn",
        "admision": {"resumen": "Inscripción directa en el campus.", "pasos": ["Solicita información de admisión en el sitio de UTH.", "Pregunta por becas internas y descuentos."], "url": "https://www.uth.hn"},
        "becas": [],
        "sedes": [
            sede("uth_sps", "UTH San Pedro Sula", "San Pedro Sula",
                 ["sistemas", "ing_industrial", "ing_electrica", "derecho", "psicologia", "mercadotecnia", "contaduria",
                  "administracion", "comercio_internacional", "informatica_administrativa", "turismo", "diseno_grafico"]),
            sede("uth_tgu", "UTH Tegucigalpa", "Tegucigalpa",
                 ["sistemas", "derecho", "psicologia", "mercadotecnia", "contaduria", "administracion", "informatica_administrativa"]),
            sede("uth_ceiba", "UTH La Ceiba", "La Ceiba", ["sistemas", "derecho", "contaduria", "administracion", "turismo"]),
            sede("uth_progreso", "UTH El Progreso", "El Progreso", ["sistemas", "derecho", "contaduria", "administracion"]),
            sede("uth_choloma", "UTH Choloma", "Choloma", ["sistemas", "ing_industrial", "administracion", "contaduria"]),
            sede("uth_pcortes", "UTH Puerto Cortés", "Puerto Cortés", ["administracion", "comercio_internacional", "contaduria"]),
        ],
    },
    {
        "id": "unitec", "nombre": "Universidad Tecnológica Centroamericana", "siglas": "UNITEC",
        "tipo": "privada", "costo": "alto",
        "costo_texto": "Privada de costo alto.",
        "web": "https://www.unitec.edu",
        "admision": {"resumen": "Solicitud de admisión y prueba propia.", "pasos": ["Aplica en el sitio de UNITEC.", "Pregunta por becas de excelencia y financiamiento."], "url": "https://www.unitec.edu"},
        "becas": [],
        "sedes": [
            sede("unitec_tgu", "UNITEC Tegucigalpa", "Tegucigalpa",
                 ["sistemas", "ing_civil", "ing_industrial", "ing_electrica", "medicina", "odontologia", "nutricion",
                  "psicologia", "arquitectura", "diseno_grafico", "derecho", "mercadotecnia", "economia", "turismo"]),
            sede("unitec_sps", "UNITEC San Pedro Sula", "San Pedro Sula",
                 ["sistemas", "ing_civil", "ing_industrial", "medicina", "psicologia", "arquitectura", "diseno_grafico",
                  "derecho", "mercadotecnia"]),
        ],
    },
    {
        "id": "usap", "nombre": "Universidad de San Pedro Sula", "siglas": "USAP",
        "tipo": "privada", "costo": "alto",
        "costo_texto": "Privada de costo alto.",
        "web": "https://www.usap.edu",
        "admision": {"resumen": "Solicitud de admisión directa.", "pasos": ["Aplica en el sitio de USAP."], "url": "https://www.usap.edu"},
        "becas": [],
        "sedes": [sede("usap_sps", "USAP San Pedro Sula", "San Pedro Sula",
                       ["diseno_grafico", "derecho", "sistemas", "informatica_administrativa", "ing_industrial", "periodismo",
                        "administracion", "arquitectura", "agronomia", "mercadotecnia", "turismo"])],
    },
    {
        "id": "unicah", "nombre": "Universidad Católica de Honduras", "siglas": "UNICAH",
        "tipo": "privada", "costo": "alto",
        "costo_texto": "Privada de costo medio a alto, con campus en varias ciudades.",
        "web": "https://www.unicah.edu",
        "admision": {"resumen": "Solicitud de admisión y prueba propia.", "pasos": ["Aplica en el sitio de UNICAH y pregunta por becas."], "url": "https://www.unicah.edu"},
        "becas": [],
        "sedes": [
            sede("unicah_tgu", "UNICAH Tegucigalpa", "Tegucigalpa",
                 ["medicina", "odontologia", "psicologia", "derecho", "arquitectura", "ing_civil", "ing_industrial", "sistemas",
                  "administracion", "enfermeria", "nutricion", "mercadotecnia", "periodismo"]),
            sede("unicah_sps", "UNICAH San Pedro Sula", "San Pedro Sula",
                 ["medicina", "odontologia", "psicologia", "derecho", "sistemas", "administracion"]),
        ],
    },
]

# Oportunidades: becas, educación a distancia, opciones gratuitas virtuales y preparación
OPORTUNIDADES = [
    {"id": "sedesol_becas", "tipo": "beca", "nombre": "Programa Nacional de Becas de SEDESOL",
     "resumen": "Apoyo de 4,000 lempiras al mes para universitarios de grado. En 2026 se ofrecieron más de 8,000 becas en los 18 departamentos.",
     "requisitos": ["Estar matriculado en una carrera universitaria", "Índice académico superior al 80%",
                    "Tener entre 17 y 40 años, ser hondureño y vivir en Honduras", "No recibir otra beca del gobierno",
                    "Cuenta de ahorro personal en lempiras"],
     "como_aplicar": ["Espera la convocatoria (la de 2026 abrió el 11 de junio).",
                      "Prepara DNI o partida de nacimiento, título o certificado, constancia de matrícula, historial y un recibo de servicio público.",
                      "Llena el formulario en línea y adjunta los documentos."],
     "url": "https://sedesol.gob.hn/becas/", "carreras": "todas", "requiere_internet": True},
    {"id": "unah_mi_bienestar", "tipo": "beca", "nombre": "Becas y ayudas Mi Bienestar UNAH (VOAE)",
     "resumen": "Becas académicas y ayudas económicas para estudiantes de la UNAH con buen rendimiento y necesidad económica; también apoyos de alimentación, materiales y transporte.",
     "requisitos": ["Ser estudiante matriculado de la UNAH", "Buen rendimiento académico", "Necesidad económica comprobable"],
     "como_aplicar": ["Entra al sistema DIPP con tu número de cuenta.", "Busca Mi Bienestar y elige Solicitud de beca.",
                      "Elige beca académica, ayuda económica o ambas y envía el formulario."],
     "url": "https://voae.unah.edu.hn", "carreras": "unah", "requiere_internet": True},
    {"id": "unacifor_becas", "tipo": "beca", "nombre": "Becas UNACIFOR",
     "resumen": "El comité de becas evalúa PAA, situación socioeconómica, notas del colegio y cartas de referencia.",
     "requisitos": ["Ser admitido en UNACIFOR"], "como_aplicar": ["Solicítala junto con tu expediente de admisión."],
     "url": "https://unacifor.edu.hn", "carreras": ["forestal", "turismo"], "requiere_internet": False},
    {"id": "zamorano_sedesol", "tipo": "beca", "nombre": "Becas Zamorano – SEDESOL",
     "resumen": "Convenio 2026 de más de 60 millones de lempiras que beneficia a 177 jóvenes hondureños en carreras agro de Zamorano.",
     "requisitos": ["Ser admitido en Zamorano", "Compromiso de retribuir al país al graduarte"],
     "como_aplicar": ["Aplica a Zamorano y solicita ayuda financiera.", "Pregunta en admisiones por los cupos del convenio con SEDESOL."],
     "url": "https://www.zamorano.edu", "carreras": ["agronomia", "agroindustrial", "forestal", "administracion"], "requiere_internet": True},
    {"id": "earth", "tipo": "beca", "nombre": "Universidad EARTH (Costa Rica)",
     "resumen": "Universidad agrícola internacional que ofrece becas según necesidad económica a jóvenes de Latinoamérica, incluidos de zonas rurales. Verifica la convocatoria vigente.",
     "requisitos": ["Graduado de secundaria", "Interés en agro y ambiente"],
     "como_aplicar": ["Revisa la convocatoria de admisión y becas en su sitio.", "Prepara notas, cartas y entrevista."],
     "url": "https://www.earth.ac.cr", "carreras": ["agronomia", "forestal", "biologia", "agroindustrial"], "requiere_internet": True},
    {"id": "unah_distancia", "tipo": "distancia", "nombre": "UNAH a distancia (CRAED / SUED) y telecentros",
     "resumen": "La UNAH ofrece Pedagogía y Administración de Empresas Agropecuarias a distancia, y telecentros en Gracias, Ocotepeque, Roatán, Choloma, Puerto Cortés y Marcala.",
     "requisitos": ["Aprobar la PHUMA"], "como_aplicar": ["Elige la modalidad a distancia al seleccionar carrera en admisiones UNAH."],
     "url": "https://admisiones.unah.edu.hn", "carreras": ["pedagogia", "administracion", "agronomia"], "requiere_internet": True, "gratuita": True},
    {"id": "upnfm_distancia", "tipo": "distancia", "nombre": "UPNFM – Educación a distancia",
     "resumen": "Profesorados en modalidad a distancia con tutorías en distintos departamentos.",
     "requisitos": ["Aprobar el examen de admisión de la UPNFM"], "como_aplicar": ["Consulta en admisiones de la UPNFM la sede de distancia más cercana."],
     "url": "https://www.upnfm.edu.hn", "carreras": ["pedagogia", "lenguas", "educacion_fisica"], "requiere_internet": True, "gratuita": True},
    {"id": "infop", "tipo": "gratis", "nombre": "INFOP – Cursos técnicos gratuitos",
     "resumen": "Cursos gratuitos presenciales y virtuales (inglés, computación, redes, electricidad, alimentos, atención al cliente y más) para mayores de 16 años.",
     "requisitos": ["Mayor de 16 años", "Inscripción en la oficina regional o en línea"],
     "como_aplicar": ["Llama o visita la oficina del INFOP de tu departamento.", "Pregunta por cursos virtuales si vives lejos."],
     "url": "https://www.infop.hn", "carreras": "todas", "requiere_internet": False, "gratuita": True},
    {"id": "carlos_slim", "tipo": "gratis", "nombre": "Capacítate para el empleo (Fundación Carlos Slim)",
     "resumen": "Cursos en línea gratuitos y con constancia, en español, de cientos de oficios y áreas técnicas.",
     "requisitos": ["Internet (funciona en celular)"], "como_aplicar": ["Crea tu cuenta gratuita y elige una ruta de tu carrera."],
     "url": "https://capacitateparaelempleo.org", "carreras": "todas", "requiere_internet": True, "gratuita": True},
    {"id": "khan", "tipo": "preparacion", "nombre": "Khan Academy en español",
     "resumen": "Gratis: repasa matemáticas, lectura y ciencias para la PHUMA y exámenes de admisión.",
     "requisitos": ["Internet o descarga de videos"], "como_aplicar": ["Entra a es.khanacademy.org y sigue el curso de matemáticas de tu nivel."],
     "url": "https://es.khanacademy.org", "carreras": "todas", "requiere_internet": True, "gratuita": True},
    {"id": "uopeople", "tipo": "distancia", "nombre": "University of the People (en inglés)",
     "resumen": "Universidad en línea acreditada en EE. UU. sin colegiatura; cobra tarifas de solicitud y de evaluación por curso, y tiene becas que pueden cubrirlas. Clases en inglés.",
     "requisitos": ["Inglés intermedio", "Internet y computadora"], "como_aplicar": ["Aplica en línea y solicita beca para las tarifas."],
     "url": "https://www.uopeople.edu", "carreras": ["sistemas", "administracion", "pedagogia", "nutricion"], "requiere_internet": True, "gratuita": False},
]

# Cabeceras departamentales de Honduras (respaldo si no hay geocodificación)
GEOGRAFIA = {
    "Honduras": {
        "centro": [14.75, -86.75],
        "departamentos": {
            "Atlántida": [15.7597, -86.7822], "Choluteca": [13.3007, -87.1908], "Colón": [15.9167, -85.9535],
            "Comayagua": [14.4514, -87.6375], "Copán": [14.7667, -88.7792], "Cortés": [15.5040, -88.0250],
            "El Paraíso": [14.0300, -86.5800], "Francisco Morazán": [14.0846, -87.1607], "Gracias a Dios": [15.2667, -83.7667],
            "Intibucá": [14.3167, -88.1667], "Islas de la Bahía": [16.3168, -86.5390], "La Paz": [14.3200, -87.6800],
            "Lempira": [14.5886, -88.5819], "Ocotepeque": [14.4333, -89.1833], "Olancho": [14.6667, -86.2192],
            "Santa Bárbara": [14.9192, -88.2361], "Valle": [13.5333, -87.4833], "Yoro": [15.1333, -87.1333],
        },
    }
}

# ---------------------------------------------------------------------------
# Enlaces al plan de estudios por universidad y carrera, y contactos verificados
# UNAH: páginas de la Feria Vocacional (plan de estudios PDF + correos de coordinación por centro)
# Privadas, UPNFM, UNACIFOR y Zamorano: fichas de universidades.hn (plan por ciclos + "Pedir información")
# o PDF oficiales de la propia universidad.
# ---------------------------------------------------------------------------
FV = "https://feriavocacional.unah.edu.hn/carreras/"
UHN = "https://universidades.hn/universidades/"
PLANES = {
    "unah": {c: FV + slug for c, slug in {
        "sistemas": "ingenieria-en-sistemas-computacionales", "informatica_administrativa": "informatica-administrativa",
        "medicina": "medicina", "enfermeria": "enfermeria", "odontologia": "odontologia", "nutricion": "nutricion",
        "quimica_farmacia": "quimica-y-farmacia", "microbiologia": "microbiologia", "psicologia": "psicologia",
        "trabajo_social": "trabajo-social", "derecho": "derecho", "periodismo": "periodismo", "pedagogia": "pedagogia",
        "lenguas": "lenguas-extranjeras", "educacion_fisica": "educacion-fisica",
        "administracion": "administracion-y-generacion-de-empresas", "contaduria": "contaduria-publica-y-finanzas",
        "economia": "economia", "mercadotecnia": "mercadotecnia", "comercio_internacional": "comercio-internacional",
        "turismo": "ecoturismo", "arquitectura": "arquitectura", "ing_civil": "ingenieria-civil",
        "ing_industrial": "ingenieria-industrial", "ing_electrica": "ingenieria-electrica-industrial",
        "ing_mecanica": "ingenieria-mecanica-industrial", "agronomia": "ingenieria-agronomica",
        "forestal": "ingenieria-forestal", "agroindustrial": "ingenieria-agroindustrial", "biologia": "biologia",
    }.items()},
    "upnfm": {
        "pedagogia": UHN + "universidad-pedagogica-nacional-francisco-morazan/educacion",
        "lenguas": UHN + "universidad-pedagogica-nacional-francisco-morazan/ensenanza-del-ingles",
        "educacion_fisica": UHN + "universidad-pedagogica-nacional-francisco-morazan/educacion-fisica",
    },
    "unag": {
        "agronomia": "https://www.unag.edu.hn/documents/planes-de-estudio/plan-de-ingenieria-agronomica.pdf",
        "veterinaria": "https://www.unag.edu.hn/documents/planes-de-estudio/plan-de-medicina-veterinaria.pdf",
        "agroindustrial": "https://portal.unag.edu.hn/wp-content/uploads/2021/10/Plan-de-Tecnologia-Alimentaria.pdf",
    },
    "unacifor": {
        "forestal": "https://unacifor.edu.hn/wp-content/uploads/2022/04/3.-TRIFOLIO-OFICIAL-INGENIERIA-EN-CIENCIAS-FORESTALES.pdf",
        "turismo": UHN + "universidad-nacional-de-ciencias-forestales-de-honduras/turismo-sostenible",
    },
    "zamorano": {
        "agronomia": "https://zamorano.edu/wp-content/uploads/2026/03/brochure-Agronomica.pdf",
        "agroindustrial": "https://zamorano.edu/wp-content/uploads/2026/03/Brochure-Agroindustria-Alimentaria.pdf",
    },
    "unitec": {c: UHN + "universidad-tecnologica-centroamericana-unitec/" + slug for c, slug in {
        "sistemas": "ingenieria-en-sistemas-computacionales", "ing_civil": "ingenieria-civil",
        "ing_industrial": "ingenieria-industrial-y-de-sistemas", "ing_electrica": "ingenieria-de-energia",
        "medicina": "medicina-y-cirugia", "odontologia": "cirugia-dental", "nutricion": "nutricion",
        "psicologia": "psicologia", "arquitectura": "arquitectura", "diseno_grafico": "diseno-grafico",
        "derecho": "derecho", "mercadotecnia": "mercadotecnia-y-negocios-internacionales",
        "economia": "finanzas-y-economia", "turismo": "administracion-de-la-hospitalidad-y-el-turismo",
    }.items()},
    "uth": {c: UHN + "universidad-tecnologica-de-honduras/" + slug for c, slug in {
        "sistemas": "ingenieria-en-computacion", "ing_industrial": "ingenieria-en-produccion-industrial",
        "ing_electrica": "ingenieria-en-electronica", "derecho": "derecho", "psicologia": "psicologia",
        "mercadotecnia": "marketing", "contaduria": "contaduria-financiera", "administracion": "emprendimiento-gerencial",
        "comercio_internacional": "comercio-y-negocios-internacionales",
        "informatica_administrativa": "informatica-administrativa", "turismo": "turismo", "diseno_grafico": "diseno-grafico",
    }.items()},
    "usap": {c: UHN + "universidad-de-san-pedro-sula/" + slug for c, slug in {
        "diseno_grafico": "diseno-grafico", "derecho": "derecho", "sistemas": "ingenieria-en-tecnologias-computacionales",
        "informatica_administrativa": "informatica-administrativa", "ing_industrial": "ingenieria-industrial",
        "periodismo": "ciencias-de-la-comunicacion-y-publicidad", "administracion": "administracion-de-empresas",
        "arquitectura": "arquitectura", "agronomia": "ingenieria-agronomica-administrativa",
        "mercadotecnia": "mercadotecnia", "turismo": "administracion-turistica",
    }.items()},
    "unicah": {c: UHN + "universidad-catolica-de-honduras-unicah/" + slug for c, slug in {
        "medicina": "medicina-y-cirugia", "odontologia": "cirugia-dental", "psicologia": "psicologia",
        "derecho": "derecho", "arquitectura": "arquitectura", "ing_civil": "ingenieria-civil",
        "ing_industrial": "ingenieria-industrial", "sistemas": "ingenieria-en-ciencias-de-la-computacion",
        "administracion": "administracion-de-empresas", "enfermeria": "enfermeria", "nutricion": "nutricion",
        "mercadotecnia": "mercadotecnia", "periodismo": "ciencias-de-la-comunicacion",
    }.items()},
}
# Excepciones por sede (centros regionales UNAH con otra versión de la carrera)
PLANES_SEDE = {
    "unah_curla": {"economia": FV + "economia-agricola"},
    "unah_curoc": {"comercio_internacional": FV + "comercio-internacional-con-orientacion-en-agroindustria"},
    "unah_curc": {"comercio_internacional": FV + "comercio-internacional-con-orientacion-en-agroindustria"},
    "unah_curlp": {"comercio_internacional": FV + "comercio-internacional-con-orientacion-en-agroindustria"},
    "unah_curno": {"comercio_internacional": FV + "comercio-internacional-con-orientacion-en-agroindustria"},
}
CONTACTOS = {
    "unah": {"correo": "info@unah.edu.hn", "url": "https://www.unah.edu.hn/oferta-academica"},
    "upnfm": {"correo": "admision.consultas@upnfm.edu.hn", "url": "https://universidades.hn/universidades/universidad-pedagogica-nacional-francisco-morazan"},
    "unag": {"url": "https://universidades.hn/universidades/universidad-nacional-de-agricultura"},
    "unacifor": {"telefono": "2720-2300 ext. 114", "correo": "admisiones@unacifor.edu.hn", "url": "https://unacifor.edu.hn"},
    "zamorano": {"telefono": "2776-6140", "url": "https://www.zamorano.edu"},
    "ceutec": {"url": "http://www.ceutec.unitec.edu"},
    "uth": {"url": "https://universidades.hn/universidades/universidad-tecnologica-de-honduras"},
    "unitec": {"telefono": "2268-1000", "url": "https://www.unitec.edu/estudios/programas-de-grado/"},
    "usap": {"url": "https://universidades.hn/universidades/universidad-de-san-pedro-sula"},
    "unicah": {"url": "https://universidades.hn/universidades/universidad-catolica-de-honduras-unicah"},
}
TELEFONO_SEDE = {"unitec_sps": "2564-5600", "unitec_tgu": "2268-1000", "unah_cu": "2216-3000"}

for u in UNIVERSIDADES:
    u["contacto"] = CONTACTOS.get(u["id"], {"url": u["web"]})
    for s_ in u["sedes"]:
        s_["planes"] = {c: (PLANES_SEDE.get(s_["id"], {}).get(c) or PLANES.get(u["id"], {}).get(c)) for c in s_["carreras"]}
        s_["planes"] = {k: v for k, v in s_["planes"].items() if v}
        if s_["id"] in TELEFONO_SEDE:
            s_["telefono"] = TELEFONO_SEDE[s_["id"]]

(OUT / "universidades.json").write_text(json.dumps(UNIVERSIDADES, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "oportunidades.json").write_text(json.dumps(OPORTUNIDADES, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "geografia.json").write_text(json.dumps(GEOGRAFIA, ensure_ascii=False, indent=2), encoding="utf-8")

# Validación: todas las carreras referidas existen
carreras = {c["id"] for c in json.loads((OUT / "carreras.json").read_text(encoding="utf-8"))}
for u in UNIVERSIDADES:
    for s in u["sedes"]:
        for c in s["carreras"]:
            assert c in carreras, (u["id"], s["id"], c)
for o in OPORTUNIDADES:
    if isinstance(o["carreras"], list):
        for c in o["carreras"]:
            assert c in carreras, (o["id"], c)
sin_sede = carreras - {c for u in UNIVERSIDADES for s in u["sedes"] for c in s["carreras"]}
print("universidades:", len(UNIVERSIDADES), "sedes:", sum(len(u["sedes"]) for u in UNIVERSIDADES), "carreras sin sede:", sin_sede)
