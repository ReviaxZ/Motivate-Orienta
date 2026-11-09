"""Genera web/data/test_carreras.json: test de 6 preguntas por carrera (2 básicas, 2 intermedias, 2 avanzadas).

Cada pregunta se escribe con la respuesta correcta en primer lugar; el script baraja las opciones
de forma determinista para que la correcta no quede siempre en la misma letra.
"""
import hashlib
import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "web" / "data"


def q(p, correcta, *otras):
    return (p, [correcta, *otras])


BANCO = {
    "sistemas": [
        [q("¿Qué es un algoritmo?", "Una secuencia finita de pasos para resolver un problema", "Un tipo de computadora", "Un lenguaje de programación", "Un virus informático"),
         q("¿Qué estructura repite un bloque de instrucciones mientras se cumpla una condición?", "Un ciclo while", "Una variable", "Un comentario", "Una constante")],
        [q("¿Qué estructura de datos funciona con el principio último en entrar, primero en salir?", "Pila", "Cola", "Árbol", "Grafo"),
         q("En una base de datos relacional, ¿qué es una clave primaria?", "Un campo que identifica de forma única cada registro", "La contraseña de la base de datos", "Siempre el primer campo de la tabla", "Una copia de seguridad")],
        [q("¿Cuál es la complejidad de la búsqueda binaria en un arreglo ordenado?", "Logarítmica, O de log n", "Lineal, O de n", "Cuadrática, O de n al cuadrado", "Constante, O de 1"),
         q("En el modelo OSI, ¿en qué capa opera el protocolo IP?", "Red", "Transporte", "Enlace de datos", "Aplicación")],
    ],
    "informatica_administrativa": [
        [q("¿Qué programa se usa típicamente para hacer hojas de cálculo?", "Microsoft Excel", "Paint", "Bloc de notas", "Un reproductor de video"),
         q("¿Qué es un sistema de información en una empresa?", "Personas, datos y procesos que apoyan la toma de decisiones", "Solo las computadoras de la empresa", "El sitio web de la empresa", "El departamento de ventas")],
        [q("¿Qué instrucción SQL se usa para consultar datos?", "SELECT", "DELETE", "DROP", "GRANT"),
         q("¿Qué es un ERP?", "Un sistema que integra los procesos de toda la empresa", "Un antivirus", "Un tipo de red inalámbrica", "Un lenguaje de programación")],
        [q("¿Qué notación se usa para modelar procesos de negocio?", "BPMN", "HTML", "TCP", "JPEG"),
         q("En auditoría informática, ¿qué busca principalmente un control interno?", "Reducir riesgos y asegurar la integridad de la información", "Aumentar la velocidad del internet", "Diseñar logotipos", "Vender más productos")],
    ],
    "medicina": [
        [q("¿Qué órgano bombea la sangre por todo el cuerpo?", "El corazón", "El hígado", "El pulmón", "El riñón"),
         q("¿Cuál es la unidad básica de la vida?", "La célula", "El átomo", "El tejido", "El órgano")],
        [q("¿Qué células de la sangre transportan oxígeno?", "Los glóbulos rojos", "Los glóbulos blancos", "Las plaquetas", "Los linfocitos"),
         q("¿Qué hormona del páncreas regula el azúcar en la sangre?", "La insulina", "La adrenalina", "La tiroxina", "El cortisol")],
        [q("¿Cuál es la frecuencia cardíaca normal en reposo de un adulto?", "Entre sesenta y cien latidos por minuto", "Entre veinte y cuarenta", "Entre ciento veinte y ciento sesenta", "Más de ciento ochenta"),
         q("¿Qué tipo de microorganismo causa el dengue?", "Un virus", "Una bacteria", "Un hongo", "Un protozoario")],
    ],
    "enfermeria": [
        [q("¿Cuál es una de las medidas más importantes para prevenir infecciones en el hospital?", "El lavado de manos", "Usar perfume", "Cambiar de turno", "Hablar en voz baja"),
         q("¿Cuáles son los signos vitales?", "Temperatura, pulso, respiración y presión arterial", "Peso, talla y edad", "Color de ojos y cabello", "Solo glucosa y colesterol")],
        [q("¿Qué vía de administración pone el medicamento directamente en la vena?", "Intravenosa", "Intramuscular", "Oral", "Subcutánea"),
         q("¿Cuál es la temperatura corporal normal aproximada de un adulto?", "Entre treinta y seis y treinta y siete grados y medio", "Entre treinta y tres y treinta y cuatro grados", "Entre treinta y ocho y treinta y nueve grados", "Más de cuarenta grados")],
        [q("¿Qué escala valora el nivel de conciencia de un paciente?", "La escala de Glasgow", "La escala de Richter", "La escala de Likert", "La escala de Mohs"),
         q("Un paciente con presión baja y mareo, ¿en qué posición suele ayudar colocarlo?", "Acostado con las piernas elevadas", "Sentado inclinado hacia adelante", "De pie caminando", "Boca abajo")],
    ],
    "odontologia": [
        [q("¿Cuántos dientes tiene un adulto con la dentición completa?", "Treinta y dos", "Veinte", "Veinticuatro", "Cuarenta"),
         q("¿Cuál es la capa más dura y externa del diente?", "El esmalte", "La pulpa", "El cemento", "La encía")],
        [q("¿Qué causa principalmente la caries dental?", "Bacterias que producen ácidos a partir de azúcares", "El agua fría", "Cepillarse demasiado", "La falta de sueño"),
         q("¿Cuántos dientes tiene la dentición de leche?", "Veinte", "Treinta y dos", "Dieciséis", "Veintiocho")],
        [q("¿Qué especialidad trata la pulpa y los conductos del diente?", "Endodoncia", "Ortodoncia", "Periodoncia", "Prostodoncia"),
         q("¿Qué especialidad trata las encías y los tejidos de soporte del diente?", "Periodoncia", "Endodoncia", "Odontopediatría", "Ortodoncia")],
    ],
    "nutricion": [
        [q("¿Cuáles son los tres macronutrientes?", "Carbohidratos, proteínas y grasas", "Vitaminas, minerales y agua", "Hierro, calcio y zinc", "Fibra, sal y azúcar"),
         q("¿Qué nutriente es la principal fuente de energía rápida?", "Los carbohidratos", "Las vitaminas", "Los minerales", "El agua")],
        [q("¿Cuántas kilocalorías aporta un gramo de grasa?", "Nueve", "Cuatro", "Siete", "Dos"),
         q("¿Qué vitamina produce la piel con la luz del sol?", "La vitamina D", "La vitamina C", "La vitamina B12", "La vitamina K")],
        [q("¿Cómo se calcula el índice de masa corporal?", "Peso en kilogramos entre la estatura en metros al cuadrado", "Estatura entre peso", "Peso por edad", "Cintura entre cadera"),
         q("La falta de hierro en la dieta puede causar principalmente:", "Anemia", "Escorbuto", "Raquitismo", "Bocio")],
    ],
    "quimica_farmacia": [
        [q("¿Cuál es la fórmula química del agua?", "H dos O", "C O dos", "Na Cl", "O dos"),
         q("¿Qué es un fármaco?", "Una sustancia que produce un efecto terapéutico en el organismo", "Un tipo de célula", "Un instrumento de laboratorio", "Una enfermedad")],
        [q("¿Qué estudia la farmacocinética?", "La absorción, distribución, metabolismo y excreción del fármaco", "Cómo se venden los medicamentos", "El sabor de los medicamentos", "La fabricación de envases"),
         q("¿Cuál es el pH de una solución neutra?", "Siete", "Cero", "Catorce", "Uno")],
        [q("¿En qué órgano se metabolizan principalmente la mayoría de los fármacos?", "El hígado", "El corazón", "El pulmón", "El bazo"),
         q("¿Qué es un medicamento genérico?", "Uno con el mismo principio activo que el original, sin marca comercial", "Uno sin principio activo", "Uno solo para animales", "Uno ilegal")],
    ],
    "microbiologia": [
        [q("¿Qué instrumento se usa para observar bacterias?", "El microscopio", "El telescopio", "El termómetro", "El estetoscopio"),
         q("¿Qué son las bacterias?", "Organismos unicelulares procariotas", "Virus grandes", "Células del cuerpo humano", "Hongos multicelulares")],
        [q("¿Qué tinción clasifica a las bacterias en positivas y negativas?", "La tinción de Gram", "La tinción de Wright", "La tinción de Papanicolaou", "La hematoxilina"),
         q("¿Qué medicamento elimina bacterias pero no sirve contra virus?", "El antibiótico", "El antiviral", "El antihistamínico", "El analgésico")],
        [q("¿Cuál es la diferencia principal entre un virus y una bacteria?", "El virus necesita una célula huésped para reproducirse", "El virus es más grande", "La bacteria no tiene material genético", "No hay diferencia"),
         q("¿Qué técnica amplifica fragmentos de ADN para diagnóstico?", "PCR", "ELISA", "Electroforesis de proteínas", "Cultivo en agar")],
    ],
    "psicologia": [
        [q("¿Qué estudia la psicología?", "El comportamiento y los procesos mentales", "Solo las enfermedades del cerebro", "Las rocas y minerales", "La historia antigua"),
         q("¿Quién es considerado el padre del psicoanálisis?", "Sigmund Freud", "Isaac Newton", "Charles Darwin", "Jean Piaget")],
        [q("Según Piaget, ¿cuál es la primera etapa del desarrollo cognitivo?", "Sensoriomotora", "Operaciones formales", "Preoperacional", "Operaciones concretas"),
         q("¿Qué es el condicionamiento clásico?", "Aprender a asociar un estímulo neutro con otro que provoca una respuesta", "Aprender leyendo libros", "Un tipo de terapia de grupo", "Una prueba de inteligencia")],
        [q("¿Qué manual se usa internacionalmente para clasificar trastornos mentales?", "El DSM", "El IPC", "La norma ISO", "Las NIIF"),
         q("En la pirámide de Maslow, ¿qué necesidad está en la cima?", "La autorrealización", "Las fisiológicas", "La seguridad", "La afiliación")],
    ],
    "trabajo_social": [
        [q("¿Cuál es el objetivo principal del trabajo social?", "Promover el bienestar y los derechos de personas y comunidades", "Vender productos", "Construir edificios", "Diagnosticar enfermedades"),
         q("¿Qué es un estudio socioeconómico?", "Un análisis de las condiciones sociales y económicas de una familia", "Un examen médico", "Un estudio de mercado", "Una auditoría contable")],
        [q("¿Qué es la intervención comunitaria?", "Trabajar con la comunidad para resolver sus problemas de forma participativa", "Sancionar a la comunidad", "Mudar a la comunidad", "Vender servicios"),
         q("¿Qué documento reconoce internacionalmente los derechos de la niñez?", "La Convención sobre los Derechos del Niño", "El Código de Comercio", "La Carta de la OTAN", "Un tratado de libre comercio")],
        [q("¿Qué técnica permite conocer la dinámica familiar en el hogar?", "La visita domiciliaria", "La auditoría", "La radiografía", "El balance general"),
         q("¿Qué herramienta representa gráficamente las relaciones familiares de varias generaciones?", "El genograma", "El organigrama", "El histograma", "El cronograma")],
    ],
    "derecho": [
        [q("¿Cuál es la ley suprema de un país?", "La Constitución", "Un reglamento municipal", "Un contrato privado", "Una sentencia"),
         q("¿Qué es un contrato?", "Un acuerdo de voluntades que crea obligaciones", "Una multa", "Una ley del Congreso", "Un juicio")],
        [q("¿Qué poder del Estado juzga y aplica las leyes en casos concretos?", "El Poder Judicial", "El Poder Legislativo", "El Poder Ejecutivo", "La municipalidad"),
         q("¿Qué principio dice que toda persona es inocente hasta que se demuestre lo contrario?", "La presunción de inocencia", "La cosa juzgada", "La irretroactividad", "La legítima defensa")],
        [q("¿Qué recurso protege a una persona detenida ilegalmente?", "El habeas corpus", "La pensión alimenticia", "El divorcio", "La hipoteca"),
         q("¿Qué es la prescripción en derecho?", "La pérdida o adquisición de un derecho por el paso del tiempo", "Una receta médica", "Un tipo de impuesto", "La firma de un contrato")],
    ],
    "periodismo": [
        [q("¿Cuáles son las preguntas básicas de una noticia?", "Qué, quién, cuándo, dónde, cómo y por qué", "Solo cuándo y dónde", "Cuánto cuesta", "Ninguna"),
         q("¿Qué es una fuente periodística?", "Una persona o documento que aporta información", "Un tipo de letra", "Una cámara de video", "El título de la noticia")],
        [q("¿Qué estructura ordena la información de lo más a lo menos importante?", "La pirámide invertida", "La línea de tiempo", "El cuento", "La entrevista"),
         q("¿Qué género periodístico expresa la opinión del medio?", "El editorial", "La noticia", "La crónica", "El reportaje")],
        [q("¿Qué es la verificación de datos?", "Comprobar la veracidad de datos y declaraciones antes de publicar", "Revisar la ortografía", "Contar las palabras", "Medir la audiencia"),
         q("¿Qué principio protege la identidad de quien da información confidencial?", "El secreto profesional", "La libertad de prensa", "El derecho de réplica", "La censura previa")],
    ],
    "pedagogia": [
        [q("¿Qué estudia la pedagogía?", "La educación y los procesos de enseñanza y aprendizaje", "Las plantas", "Las enfermedades", "Los mercados"),
         q("¿Qué es un plan de clase?", "La planificación de objetivos, actividades y evaluación de una clase", "La lista de estudiantes", "El horario del colegio", "El reglamento escolar")],
        [q("¿Qué evaluación se hace durante el proceso para mejorar el aprendizaje?", "La evaluación formativa", "La evaluación sumativa", "El examen final", "El examen de admisión"),
         q("¿Qué autor propuso la zona de desarrollo próximo?", "Lev Vygotsky", "Jean Piaget", "Sigmund Freud", "Isaac Newton")],
        [q("¿Qué propone la taxonomía de Bloom?", "Niveles de pensamiento para formular objetivos de aprendizaje", "Clasificar plantas", "Medir la inteligencia", "Ordenar libros"),
         q("Según Ausubel, ¿qué es el aprendizaje significativo?", "Relacionar la nueva información con lo que el estudiante ya sabe", "Memorizar sin entender", "Aprender con castigos", "Copiar del pizarrón")],
    ],
    "lenguas": [
        [q("¿Cuál es el pasado del verbo en inglés go?", "Went", "Goed", "Gone", "Going"),
         q("¿Cómo se dice biblioteca en inglés?", "Library", "Bookstore", "Librery", "Study")],
        [q("¿Qué tiempo verbal es I have lived here for five years?", "Presente perfecto", "Pasado simple", "Futuro simple", "Presente continuo"),
         q("¿Qué palabra en francés significa gracias?", "Merci", "Bonjour", "S'il vous plaît", "Au revoir")],
        [q("¿Qué es un falso amigo en traducción?", "Una palabra parecida en dos idiomas pero con distinto significado", "Un sinónimo exacto", "Un error de pronunciación", "Una palabra prestada"),
         q("¿Qué rama de la lingüística estudia los sonidos del habla?", "La fonética", "La sintaxis", "La semántica", "La pragmática")],
    ],
    "educacion_fisica": [
        [q("¿Cuántos jugadores tiene en la cancha un equipo de fútbol?", "Once", "Nueve", "Siete", "Cinco"),
         q("¿Qué se recomienda hacer antes de una actividad física intensa?", "Un calentamiento", "Comer mucho", "Dormir", "Nada")],
        [q("¿Qué capacidad física permite mantener un esfuerzo por largo tiempo?", "La resistencia", "La flexibilidad", "La velocidad", "El equilibrio"),
         q("¿Qué sistema del cuerpo produce el movimiento junto con los huesos?", "El sistema muscular", "El sistema digestivo", "El sistema endocrino", "El sistema urinario")],
        [q("¿Cómo se estima comúnmente la frecuencia cardíaca máxima?", "Doscientos veinte menos la edad", "Cien más la edad", "La edad por dos", "Ciento ochenta menos el peso"),
         q("¿Qué principio dice que la carga de entrenamiento debe aumentar poco a poco?", "La sobrecarga progresiva", "La inercia", "El principio de Pascal", "La igualdad")],
    ],
    "administracion": [
        [q("¿Cuáles son las funciones del proceso administrativo?", "Planear, organizar, dirigir y controlar", "Comprar, vender y cobrar", "Contratar y despedir", "Producir y almacenar"),
         q("¿Qué es la misión de una empresa?", "Su razón de ser y propósito", "Su edificio principal", "Su lista de precios", "Su número de empleados")],
        [q("¿Qué herramienta analiza fortalezas, oportunidades, debilidades y amenazas?", "El análisis FODA", "El balance general", "El diagrama de Gantt", "El flujo de caja"),
         q("¿Qué es un organigrama?", "La representación gráfica de la estructura de una organización", "Un estado financiero", "Un plan de ventas", "Un contrato laboral")],
        [q("¿Qué indica el punto de equilibrio?", "El nivel de ventas donde ingresos y costos son iguales", "La máxima utilidad posible", "El número ideal de empleados", "El precio de la competencia"),
         q("¿Qué es el retorno sobre la inversión?", "La ganancia obtenida en relación con lo invertido", "El total de ventas", "Los impuestos pagados", "El capital inicial")],
    ],
    "contaduria": [
        [q("¿Cuál es la ecuación contable básica?", "Activo igual a pasivo más capital", "Ingresos igual a gastos", "Activo igual a capital menos pasivo", "Pasivo igual a activo más capital"),
         q("¿Qué es un activo?", "Un recurso controlado por la empresa del que espera beneficios", "Una deuda con proveedores", "Un gasto del mes", "Un impuesto")],
        [q("¿Qué estado financiero muestra ingresos, costos y utilidad de un período?", "El estado de resultados", "El balance general", "El inventario", "El libro de actas"),
         q("En partida doble, ¿qué significa que todo cargo tiene un abono?", "Que cada operación afecta al menos dos cuentas por el mismo valor", "Que se cobra dos veces", "Que hay dos contadores", "Que se paga doble impuesto")],
        [q("¿Qué son las NIIF?", "Normas Internacionales de Información Financiera", "Normas de inventario industrial", "Un impuesto nacional", "Un banco internacional"),
         q("¿Qué es la depreciación?", "Distribuir el costo de un activo fijo durante su vida útil", "Un aumento de precio", "Un préstamo bancario", "Una pérdida por robo")],
    ],
    "economia": [
        [q("¿Qué estudia la economía?", "Cómo se usan recursos escasos para satisfacer necesidades", "Solo el dinero de los bancos", "Las estrellas", "Los idiomas"),
         q("¿Qué es la inflación?", "El aumento generalizado de los precios", "La baja de los salarios", "El aumento del empleo", "La compra de dólares")],
        [q("Según la ley de la demanda, si el precio de un bien sube, ¿qué pasa con la cantidad demandada?", "Disminuye", "Aumenta", "No cambia", "Se duplica"),
         q("¿Qué mide el producto interno bruto?", "El valor de los bienes y servicios finales producidos en un país en un período", "La deuda del gobierno", "La población", "Solo las exportaciones")],
        [q("¿Qué es la elasticidad precio de la demanda?", "Qué tanto cambia la cantidad demandada ante un cambio de precio", "El precio máximo de un bien", "La cantidad producida", "El costo de transporte"),
         q("¿Qué política aplica el banco central al subir la tasa de interés para frenar la inflación?", "Política monetaria contractiva", "Política fiscal expansiva", "Política comercial", "Política laboral")],
    ],
    "mercadotecnia": [
        [q("¿Cuáles son las cuatro P del marketing?", "Producto, precio, plaza y promoción", "Personas, procesos, planta y papel", "Publicidad, prensa, política y poder", "Precio, pago, préstamo y plazo"),
         q("¿Qué es un mercado meta?", "El grupo de clientes al que se dirige un producto", "El edificio de un mercado", "La competencia", "El precio más bajo")],
        [q("¿Qué es la segmentación de mercado?", "Dividir el mercado en grupos con características similares", "Bajar los precios", "Abrir más tiendas", "Contratar vendedores"),
         q("¿Qué es el posicionamiento?", "El lugar que ocupa una marca en la mente del consumidor", "La ubicación de la tienda", "El orden en la estantería", "El ranking de ventas")],
        [q("En marketing digital, ¿qué significa SEO?", "Optimización para motores de búsqueda", "Servicio de envío ordinario", "Sistema de ventas en línea", "Software de edición"),
         q("¿Qué mide la tasa de conversión?", "El porcentaje de visitantes que realiza la acción deseada", "El número de seguidores", "El precio promedio", "El costo del anuncio")],
    ],
    "comercio_internacional": [
        [q("¿Qué es exportar?", "Vender bienes o servicios a otro país", "Comprar productos de otro país", "Vender dentro del país", "Prestar dinero"),
         q("¿Qué es un arancel?", "Un impuesto al comercio exterior", "Un tipo de contenedor", "Un banco internacional", "Una moneda")],
        [q("¿Qué son los Incoterms?", "Reglas que definen responsabilidades entre comprador y vendedor internacionales", "Monedas extranjeras", "Tipos de barcos", "Impuestos locales"),
         q("¿Qué tratado de libre comercio incluye a Estados Unidos, Centroamérica y República Dominicana?", "El CAFTA DR", "El TLCAN", "El MERCOSUR", "La Unión Europea")],
        [q("¿Qué significa el Incoterm FOB?", "Libre a bordo: el vendedor entrega la mercancía cargada en el buque", "El comprador recoge en fábrica", "El vendedor paga todo hasta el destino", "Mercancía sin seguro"),
         q("¿Qué es la balanza comercial?", "La diferencia entre exportaciones e importaciones", "El presupuesto del gobierno", "La deuda externa", "El tipo de cambio")],
    ],
    "turismo": [
        [q("¿Qué es el turismo?", "Viajes temporales fuera del lugar habitual por ocio, negocios u otros motivos", "Mudarse para siempre", "Trabajar en una fábrica", "Estudiar en casa"),
         q("¿Qué destino de Honduras es famoso por su arrecife y el buceo?", "Roatán", "Tegucigalpa", "Choluteca", "Gracias")],
        [q("¿Qué es el ecoturismo?", "Turismo responsable en áreas naturales que conserva y beneficia a la comunidad", "Turismo en centros comerciales", "Viajes de negocios", "Cruceros de lujo"),
         q("¿Qué sitio arqueológico maya de Honduras es Patrimonio de la Humanidad?", "Copán Ruinas", "Tikal", "Chichén Itzá", "Machu Picchu")],
        [q("¿Qué indica la tasa de ocupación hotelera?", "El porcentaje de habitaciones ocupadas en un período", "El número de empleados", "El precio por noche", "Las estrellas del hotel"),
         q("¿Qué es la capacidad de carga turística?", "El máximo de visitantes que un lugar soporta sin deteriorarse", "El peso de equipaje permitido", "El número de buses", "El presupuesto de promoción")],
    ],
    "diseno_grafico": [
        [q("¿Cuáles son los colores primarios de la luz en el modelo RGB?", "Rojo, verde y azul", "Rojo, amarillo y azul", "Cian, magenta y amarillo", "Blanco, negro y gris"),
         q("¿Qué es un logotipo?", "La representación gráfica de una marca", "Un tipo de papel", "Una cámara", "Un programa de oficina")],
        [q("¿Qué modelo de color se usa para impresión?", "CMYK", "RGB", "HSL", "Escala de grises únicamente"),
         q("¿Qué ventaja tiene una imagen vectorial sobre un mapa de bits?", "Se puede ampliar sin perder calidad", "Pesa siempre más", "Solo es en blanco y negro", "No tiene ninguna")],
        [q("¿Qué es el kerning en tipografía?", "El ajuste del espacio entre pares de letras", "El tamaño de la letra", "El color del texto", "El tipo de papel"),
         q("¿Qué ley de la Gestalt dice que percibimos como grupo los elementos cercanos?", "La ley de proximidad", "La ley de gravedad", "La ley de Ohm", "La ley de la oferta")],
    ],
    "arquitectura": [
        [q("¿Qué es un plano arquitectónico?", "Una representación gráfica a escala de una construcción", "Una foto del edificio", "Un contrato de obra", "Un tipo de ladrillo"),
         q("En un plano a escala uno a cien, ¿cuánto representa un centímetro?", "Un metro", "Un centímetro", "Diez metros", "Un kilómetro")],
        [q("¿Qué elemento transmite las cargas del edificio al suelo?", "La cimentación", "La ventana", "El cielo falso", "La pintura"),
         q("¿Qué software se usa comúnmente para dibujo arquitectónico?", "AutoCAD", "Excel", "PowerPoint", "Un reproductor de música")],
        [q("¿Qué es la arquitectura bioclimática?", "Diseñar aprovechando el clima para lograr confort con menos energía", "Usar solo aire acondicionado", "Construir sin ventanas", "Pintar de verde los edificios"),
         q("¿Qué metodología modela un edificio con la información de todos sus elementos?", "BIM", "CPM", "PERT", "FODA")],
    ],
    "ing_civil": [
        [q("¿Qué material resulta de mezclar cemento, arena, grava y agua?", "El concreto", "El acero", "La madera", "El vidrio"),
         q("¿Qué instrumento de topografía mide ángulos y distancias?", "La estación total", "El microscopio", "El termómetro", "El osciloscopio")],
        [q("¿Por qué se coloca acero de refuerzo en el concreto?", "Porque el concreto resiste poco a la tensión", "Para que pese menos", "Para que seque más rápido", "Por estética"),
         q("¿Qué estudia la mecánica de suelos?", "El comportamiento del suelo ante las cargas", "El clima", "Los minerales preciosos", "El tráfico")],
        [q("¿Qué es el momento flector en una viga?", "El efecto de las cargas que tiende a doblarla", "Solo su peso propio", "Su longitud", "Su color"),
         q("¿Cómo cambia la presión de un fluido en reposo con la profundidad?", "Aumenta con la profundidad", "Disminuye con la profundidad", "Es igual en todo punto", "No existe presión en reposo")],
    ],
    "ing_industrial": [
        [q("¿Qué busca principalmente la ingeniería industrial?", "Mejorar procesos para hacerlos más eficientes", "Diseñar ropa", "Curar enfermedades", "Escribir leyes"),
         q("¿Qué es la productividad?", "La relación entre lo producido y los recursos usados", "El número de empleados", "El precio del producto", "El tamaño de la fábrica")],
        [q("¿Qué metodología busca eliminar desperdicios en la producción?", "Lean manufacturing", "La contabilidad de costos", "El marketing digital", "El derecho laboral"),
         q("¿Qué herramienta muestra las tareas de un proyecto en el tiempo?", "El diagrama de Gantt", "El diagrama de Venn", "El árbol genealógico", "El mapa conceptual")],
        [q("¿Qué método optimiza recursos sujetos a restricciones lineales?", "La programación lineal", "La derivación", "La estadística descriptiva", "La trigonometría"),
         q("¿Qué busca Six Sigma?", "Reducir la variación y los defectos en los procesos", "Aumentar el inventario", "Contratar más personal", "Bajar los salarios")],
    ],
    "ing_electrica": [
        [q("¿Cuál es la unidad de la resistencia eléctrica?", "El ohmio", "El voltio", "El amperio", "El vatio"),
         q("Según la ley de Ohm, el voltaje es igual a:", "La corriente por la resistencia", "La corriente más la resistencia", "La resistencia entre la corriente", "La potencia por el tiempo")],
        [q("¿Qué tipo de corriente llega a las casas?", "Corriente alterna", "Corriente continua", "Corriente estática", "Corriente magnética"),
         q("¿Qué componente almacena energía en un campo eléctrico?", "El capacitor", "El fusible", "El interruptor", "El cable")],
        [q("¿Qué hace un transformador?", "Cambia el nivel de voltaje en corriente alterna", "Genera electricidad del sol", "Almacena energía en baterías", "Mide la corriente"),
         q("En resistencias conectadas en serie, la resistencia total es:", "La suma de todas", "El promedio", "La menor de ellas", "Cero")],
    ],
    "ing_mecanica": [
        [q("¿Cuál es la unidad de fuerza en el Sistema Internacional?", "El newton", "El julio", "El pascal", "El vatio"),
         q("Según la segunda ley de Newton, la fuerza es igual a:", "La masa por la aceleración", "La masa por la velocidad", "El peso entre la gravedad", "La energía por el tiempo")],
        [q("¿Qué estudia la termodinámica?", "La energía, el calor y el trabajo", "Los circuitos electrónicos", "Los seres vivos", "Las leyes del país"),
         q("¿Qué hace un motor de combustión interna?", "Convierte la energía química del combustible en trabajo mecánico", "Convierte luz en sonido", "Almacena electricidad", "Enfría el aire")],
        [q("¿Qué es la fatiga de materiales?", "La falla por cargas repetidas aunque sean menores al límite de resistencia", "El cansancio del operario", "La oxidación por lluvia", "El desgaste de la pintura"),
         q("¿Qué ciclo termodinámico describe el motor de gasolina ideal?", "El ciclo Otto", "El ciclo de Krebs", "El ciclo del agua", "El ciclo de Deming")],
    ],
    "agronomia": [
        [q("¿Qué proceso realizan las plantas para producir su alimento con la luz solar?", "La fotosíntesis", "La digestión", "La fermentación", "La evaporación"),
         q("¿Cuáles son los tres nutrientes principales de un fertilizante NPK?", "Nitrógeno, fósforo y potasio", "Neón, plata y kriptón", "Níquel, plomo y potasio", "Nitrógeno, plata y calcio")],
        [q("¿Qué es la rotación de cultivos?", "Alternar distintos cultivos en un terreno para mantener su fertilidad", "Girar las plantas al sol", "Cosechar dos veces al día", "Regar en círculos"),
         q("¿Qué mide el pH del suelo?", "Su acidez o alcalinidad", "Su humedad", "Su temperatura", "Su color")],
        [q("¿Qué es el manejo integrado de plagas?", "Combinar métodos biológicos, culturales y químicos con menor impacto", "Usar solo químicos", "Quemar el cultivo", "No hacer nada"),
         q("¿Qué tipo de riego aplica el agua gota a gota cerca de la raíz?", "Riego por goteo", "Riego por inundación", "Riego por aspersión", "Riego por gravedad")],
    ],
    "forestal": [
        [q("¿Qué es un bosque?", "Un ecosistema dominado por árboles", "Un parque urbano", "Un cultivo de maíz", "Un desierto"),
         q("¿Qué gas absorben los árboles y ayuda a reducir el cambio climático?", "El dióxido de carbono", "El oxígeno", "El nitrógeno", "El helio")],
        [q("¿Qué plaga ha afectado gravemente a los pinares de Honduras?", "El gorgojo descortezador del pino", "La broca del café", "La roya", "El picudo del algodón"),
         q("¿Qué es la silvicultura?", "El manejo y cultivo de los bosques", "El estudio de los suelos", "La pesca", "La minería")],
        [q("¿Qué es el diámetro a la altura del pecho?", "El diámetro del tronco medido a un metro treinta del suelo", "La altura total del árbol", "La edad del árbol", "El ancho de la copa"),
         q("¿Qué es una cuenca hidrográfica?", "Un territorio cuyas aguas drenan a un mismo río o lago", "Un tanque de agua", "Un tipo de árbol", "Una represa")],
    ],
    "veterinaria": [
        [q("¿Cuál de estos animales es un rumiante?", "La vaca", "El perro", "El gato", "El caballo"),
         q("¿Para qué sirve vacunar a los animales?", "Para prevenir enfermedades", "Para que crezcan más rápido", "Para cambiar su color", "Para que coman menos")],
        [q("¿Cuántos compartimentos tiene el estómago de un bovino?", "Cuatro", "Uno", "Dos", "Seis"),
         q("¿Qué es una zoonosis?", "Una enfermedad que se transmite entre animales y humanos", "Un zoológico", "Un tipo de alimento", "Una raza de perro")],
        [q("¿Qué enfermedad viral mortal se transmite por la mordida de animales infectados?", "La rabia", "La tuberculosis", "La brucelosis", "La leptospirosis"),
         q("¿Qué es el período de retiro de un medicamento veterinario?", "El tiempo que debe pasar antes de consumir leche o carne del animal tratado", "El tiempo de fabricación", "La fecha de compra", "Las vacaciones del veterinario")],
    ],
    "agroindustrial": [
        [q("¿Qué es la agroindustria?", "Transformar productos del campo en productos con valor agregado", "Sembrar a mano", "Vender tierras", "Criar mascotas"),
         q("¿Qué proceso calienta la leche para eliminar microorganismos?", "La pasteurización", "La fermentación", "La congelación", "La destilación")],
        [q("¿Qué son las Buenas Prácticas de Manufactura?", "Normas para producir alimentos seguros e higiénicos", "Técnicas de venta", "Recetas de cocina", "Normas de tránsito"),
         q("¿Qué microorganismo se usa para fermentar el pan?", "La levadura", "Un virus", "La bacteria del tifus", "El moho negro")],
        [q("¿Qué es el sistema HACCP?", "Un análisis de peligros y puntos críticos de control para la inocuidad", "Un impuesto", "Una máquina empacadora", "Un tipo de envase"),
         q("¿Qué indica la actividad de agua de un alimento?", "El agua disponible para el crecimiento de microorganismos", "El contenido de sal", "El color", "El precio")],
    ],
    "biologia": [
        [q("¿Qué molécula contiene la información genética?", "El ADN", "La glucosa", "El agua", "El almidón"),
         q("¿Qué organelo produce la energía de la célula?", "La mitocondria", "El núcleo", "La pared celular", "El ribosoma")],
        [q("¿Quién propuso la evolución por selección natural?", "Charles Darwin", "Gregor Mendel", "Louis Pasteur", "Albert Einstein"),
         q("En un ecosistema, ¿qué organismos producen su propio alimento?", "Los productores", "Los consumidores", "Los descomponedores", "Los depredadores")],
        [q("Si se cruzan dos plantas heterocigotas Aa, ¿qué proporción de la descendencia será aa?", "Un cuarto", "La mitad", "Tres cuartos", "Ninguna"),
         q("¿Qué proceso forma células sexuales con la mitad de los cromosomas?", "La meiosis", "La mitosis", "La fotosíntesis", "La ósmosis")],
    ],
}

NIVELES = ["basico", "intermedio", "avanzado"]


def barajar(p, opciones):
    semilla = int(hashlib.md5(p.encode()).hexdigest()[:8], 16)
    idx = list(range(len(opciones)))
    random.Random(semilla).shuffle(idx)
    return [opciones[i] for i in idx], idx.index(0)


salida = {}
for carrera, niveles in BANCO.items():
    assert len(niveles) == 3, carrera
    preguntas = []
    for nivel, lista in zip(NIVELES, niveles):
        assert len(lista) == 2, (carrera, nivel)
        for p, opciones in lista:
            assert len(opciones) == 4, (carrera, p)
            ops, correcta = barajar(p, opciones)
            preguntas.append({"nivel": nivel, "pregunta": p, "opciones": ops, "correcta": correcta})
    salida[carrera] = preguntas

carreras = {c["id"] for c in json.loads((OUT / "carreras.json").read_text(encoding="utf-8"))}
assert set(salida) == carreras, carreras ^ set(salida)
(OUT / "test_carreras.json").write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
from collections import Counter
print(len(salida), "carreras,", sum(len(v) for v in salida.values()), "preguntas; letras correctas:",
      Counter("ABCD"[x["correcta"]] for v in salida.values() for x in v))
