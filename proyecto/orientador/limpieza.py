"""
Filtro de lo que se convierte en voz.

El LLM a veces mezcla en su respuesta cosas que no son para el estudiante: JSON de
argumentos, nombres de herramientas, tokens del formato interno de gpt-oss
(<|channel|>, to=functions...), o lee en voz alta el resultado de una herramienta.
Este filtro trabaja en streaming, oración por oración, y solo deja pasar texto
natural dirigido al estudiante.
"""

from __future__ import annotations

import re

# Tokens del formato "harmony" de gpt-oss y restos de canales internos
_HARMONY = re.compile(r"<\|[^|>]{0,40}\|>|\b(?:assistant|analysis|commentary|final)\b(?=\s*(?:<\||to=|$))", re.I)

# Si una oración contiene algo de esto, es interna y se descarta completa
_INTERNO = re.compile(
    r"(functions\.|to=\w|<\||\|>|\bjson\b|guardar_|recomendar_carreras|mostrar_carrera|elegir_carrera|"
    r"ofrecer_cita|finalizar_entrevista|\bherramienta|\binterno\b|\bguardado\b|falta preguntar|"
    r"siguiente pregunta|\bid\s+\w+_|instrucci[oó]n|aviso de la pantalla|\btool\b|\bpayload\b|nota privada)",
    re.I,
)

_SNAKE = re.compile(r"\b(?:functions\.)?[A-Za-z]+(?:_[A-Za-z]+)+\b")

_ABRE = "{[("
_CIERRA = "}])"
_FIN = ".?!\n"


_ES = {"que", "de", "la", "el", "los", "las", "y", "en", "por", "para", "con", "una", "un", "es", "tu", "te", "muy", "mas",
       "pero", "como", "esta", "estas", "del", "al", "se", "lo", "mi", "si", "tus", "gracias", "hola", "carrera", "puedes"}
_EN = {"the", "and", "you", "is", "to", "of", "what", "your", "a", "in", "for", "with", "are", "it", "do", "that", "this",
       "i", "my", "can", "be", "how", "would", "thanks", "hi"}


# Palabras inequívocamente inglesas (sin "a", "i" ni otras que también existen en español)
_EN_FUERTE = {"the", "and", "you", "your", "is", "are", "to", "of", "what", "for", "with", "it", "do", "does", "that", "this",
              "my", "can", "be", "how", "would", "will", "we", "need", "should", "user", "they", "have", "has", "then", "now",
              "so", "let", "call", "ask", "answer", "question", "next", "must", "just", "about", "which", "say", "respond",
              "reply", "tool", "function", "student", "their", "our", "it's", "i'm", "we'll", "let's", "don't", "in", "on", "from"}

# Razonamiento interno / meta-instrucciones del modelo (no van dirigidas al estudiante)
_META = re.compile(
    r"(\bthe user\b|\buser (said|says|answered|asked|wants|responded|replied|mentioned)|\bthe student (said|says|answered|wants|mentioned)|"
    r"\b(we|i) (need|should|must|have) to\b|\blet me (call|check|save|use|record|store)\b|\b(call|calling|use|using) the (tool|function)|"
    r"\btool call|\bfunction call|\bthe (tool|function|system|developer|assistant|instructions?|note|prompt)\b|\binstructions? (say|says)\b|"
    r"\baccording to the\b|\bas instructed\b|\brespond (in|with|only)\b|\bnow (we|i) (ask|call|need|should|must)\b|\bnext (question|step) is\b|"
    r"\bel usuario\b|\bla usuaria\b|\bel estudiante (dijo|respondi[oó]|quiere|mencion[oó]|ha dicho)\b|"
    r"\b(debemos|necesitamos|tenemos que|debo|necesito) (llamar|preguntar|responder|guardar|usar)\b|seg[uú]n las instrucciones|"
    r"\bahora (llamo|llamamos|debo|preguntamos|pregunto a)\b|\bla siguiente pregunta es\b|\bvoy a llamar\b|\bel sistema\b)",
    re.I,
)


# ---------------------------------------------------------------- fórmulas y símbolos
# Fish Audio lee los símbolos tal cual ("igual", "asterisco", "barra"...). Las expresiones simples
# se dicen con palabras; las complejas (LaTeX, sumatorias, integrales) se cambian por un aviso.
_COMPLEJA = re.compile(r"\$[^$]*\$|\\[a-zA-Z]+(?:\{[^}]*\})*|[^\s,;:¿?¡!]*[∑∫∂∇∮√]\S*\s*\([^)]*\)|[^\s,;:¿?¡!]*[∑∫∂∇∮\\$][^\s,;:¿?¡!]*")
_AVISO = {"es": " la fórmula que ves en la pantalla ", "en": " the formula on the screen "}
_SUP = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉", "01234567890123456789")
_PALABRAS = {
    "es": {"=": "igual a", "+": "más", "−": "menos", "×": "por", "·": "por", "*": "por", "÷": "entre", "/": "entre",
           "±": "más o menos", "≤": "menor o igual que", "≥": "mayor o igual que", "≠": "distinto de", "≈": "aproximadamente",
           "<": "menor que", ">": "mayor que", "√": "raíz de", "π": "pi", "Δ": "delta", "∆": "delta", "∞": "infinito",
           "%": "por ciento", "°": "grados", "^2": "al cuadrado", "^3": "al cubo", "^": "a la", "→": ",", "&": "y"},
    "en": {"=": "equals", "+": "plus", "−": "minus", "×": "times", "·": "times", "*": "times", "÷": "divided by", "/": "over",
           "±": "plus or minus", "≤": "less than or equal to", "≥": "greater than or equal to", "≠": "not equal to", "≈": "approximately",
           "<": "less than", ">": "greater than", "√": "square root of", "π": "pi", "Δ": "delta", "∆": "delta", "∞": "infinity",
           "%": "percent", "°": "degrees", "^2": "squared", "^3": "cubed", "^": "to the", "→": ",", "&": "and"},
}
_OPERANDO = r"[\w)\]]"
# Caracteres que sí se pueden leer; todo lo demás se quita antes de ir a voz
_HABLABLE = re.compile(r"[^\w\s.,;:¿?¡!'\-áéíóúüñÁÉÍÓÚÜÑ]")


_CORTAS_COMUNES = {"es", "el", "la", "lo", "y", "o", "de", "que", "en", "a", "un", "se", "su", "al", "del", "con", "por", "the",
                   "is", "of", "and", "to", "an", "it", "in", "on", "for", "as", "es,", "son"}


def _complejas(s: str, aviso: str) -> str:
    """Cambia cada fórmula compleja (y los términos cortos que la siguen) por el aviso."""
    if not _COMPLEJA.search(s):
        return s
    s = _COMPLEJA.sub(" \x00 ", s)
    toks, out, tragando = s.split(), [], False
    for t in toks:
        if t == "\x00":
            if not tragando:
                previa = out[-1].lower().strip(".,;:") if out else ""
                if previa in ("fórmula", "formula", "ecuación", "ecuacion", "expresión", "expresion", "equation", "expression"):
                    out.append("que ves en la pantalla" if "the" not in aviso else "on the screen")
                else:
                    out.append(aviso.strip())
            tragando = True
            continue
        if tragando and len(t.strip(".,;:?!")) <= 3 and t.lower().strip(".,;:?!") not in _CORTAS_COMUNES and not re.search(r"[.,;:?!]$", t):
            continue
        tragando = False
        out.append(t)
    return " ".join(out)


def hablable(s: str, idioma: str = "es") -> str:
    """Convierte fórmulas y símbolos en algo que se pueda decir (o los quita)."""
    if not s:
        return s
    w = _PALABRAS.get(idioma)
    s = re.sub(r"https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.]+", " ", s)    # enlaces y correos: están en pantalla
    s = re.sub(r"(?<![\w])[:;]-?[()DPp](?!\w)", " ", s)                  # emoticonos :)
    s = re.sub(r"\b(y|and)/(o|or)\b", r"\1 \2", s)                         # y/o
    s = _complejas(s, _AVISO.get(idioma, " "))
    s = s.replace("²", "^2").replace("³", "^3").translate(_SUP)
    if w:
        s = re.sub(r"\^\s*2\b", f" {w['^2']}", s)
        s = re.sub(r"\^\s*3\b", f" {w['^3']}", s)
        s = re.sub(r"\^\s*(\w+)", lambda m: f" {w['^']} {m.group(1)}", s)
        s = re.sub(r"(\d)\s*%", lambda m: f"{m.group(1)} {w['%']}", s)
        s = re.sub(r"(\d)\s*°\s*C\b", lambda m: f"{m.group(1)} {w['°']} {'centígrados' if idioma == 'es' else 'Celsius'}", s)
        s = re.sub(r"(\d)\s*°\s*F\b", lambda m: f"{m.group(1)} {w['°']} Fahrenheit", s)
        s = re.sub(r"(\d)\s*°", lambda m: f"{m.group(1)} {w['°']}", s)
        # Operadores entre operandos: 2 + 3, x = 5, a/b, 3 × 4
        for op in ("=", "+", "×", "·", "*", "÷", "±", "≤", "≥", "≠", "≈", "<", ">"):
            s = re.sub(rf"(?<={_OPERANDO})\s*{re.escape(op)}\s*(?=[\w(√−-])", f" {w[op]} ", s)
        s = re.sub(r"\bkm\s*/\s*h\b", "kilómetros por hora" if idioma == "es" else "kilometers per hour", s)
        s = re.sub(r"\b(\w{1,3})\s*/\s*(\w{1,3})\b", lambda m: f"{m.group(1)} {w['/']} {m.group(2)}", s)
        s = re.sub(r"(?<=[\w)])\s+[−-]\s+(?=[\w(])", f" {w['−']} ", s)       # 5 - 3 (con espacios)
        s = re.sub(r"(?:(?<=\s)|^)[−-](?=\d)", f"{w['−']} ", s)               # -3
        s = s.replace("−", f" {w['−']} ")
        for sim in ("√", "π", "Δ", "∆", "∞", "→", "&"):
            s = s.replace(sim, f" {w[sim]} ")
    s = s.replace("/", " ")
    s = _HABLABLE.sub(" ", s).replace("_", " ")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s+([,.;:?!])", r"\1", s)
    s = re.sub(r"[:;,]+$", "", s.strip())
    return s.strip()


def parece_ingles(s: str) -> bool:
    import unicodedata
    t = "".join(ch for ch in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(ch) != "Mn")
    palabras = re.findall(r"[a-zñ']+", t)
    en = sum(p in _EN_FUERTE for p in palabras)
    es = sum(p in _ES for p in palabras)
    return en >= 2 and en > es


def parece_espanol(s: str) -> bool:
    import unicodedata
    t = "".join(ch for ch in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(ch) != "Mn")
    palabras = re.findall(r"[a-zñ]+", t)
    es = sum(p in _ES for p in palabras)
    en = sum(p in _EN for p in palabras)
    marcas = bool(re.search(r"[ñ¿¡]|ción\b", s.lower()))
    return (marcas and es >= 1) or (es >= 2 and es > en)


class Limpiador:
    def __init__(self, idioma: str = "es", filtro=None) -> None:
        self.idioma = idioma
        self.filtro = filtro     # filtro extra por oración (p. ej. preguntas repetidas); devuelve "" para descartar
        self.prof = 0          # profundidad dentro de {} [] ()
        self.abre = ""         # tipo de paréntesis exterior abierto
        self.dentro = ""       # contenido dentro de paréntesis (se conserva si es una fórmula o una aclaración corta)
        self.punto = False     # punto después de un número: puede ser decimal (3.5), se decide con el siguiente carácter
        self.oracion = ""
        self.visto = ""          # todo lo escrito fuera de {} [] () (para saber si ya preguntó)
        self.descartadas: list[str] = []

    def _emitir(self) -> str:
        s = _HARMONY.sub(" ", self.oracion)
        self.oracion = ""
        # Nombres internos en formato snake_case (herramientas, etiquetas, ids): se quitan
        s = _SNAKE.sub(" ", s)
        s = re.sub(r"\s+", " ", s).strip()
        if not s or not re.search(r"[A-Za-zÁÉÍÓÚáéíóúÑñ]", s):
            return ""
        if _INTERNO.search(s):
            self.descartadas.append(s)
            return ""
        if _META.search(s):
            self.descartadas.append("[meta] " + s)
            return ""
        if self.idioma == "en" and parece_espanol(s):
            self.descartadas.append("[es] " + s)
            return ""
        if self.idioma != "en" and parece_ingles(s):
            self.descartadas.append("[en] " + s)
            return ""
        s = hablable(s, self.idioma)
        if s and self.filtro:
            s = self.filtro(s)
        return s + " " if s else ""

    def _agregar(self, ch: str, out: list) -> None:
        if self.punto:
            self.punto = False
            if not ch.isspace():        # punto interno: decimal (3.5), web o sigla (unah.edu.hn)
                self.oracion += ch
                self.visto += ch
                return
            out.append(self._emitir())
        self.visto += ch
        self.oracion += ch
        if ch == "." and self.oracion[-2:-1].isalnum():
            self.punto = True
        elif ch in _FIN:
            out.append(self._emitir())

    def feed(self, texto: str) -> str:
        out: list[str] = []
        for ch in texto:
            if ch in _ABRE:
                if self.prof == 0:
                    self.abre, self.dentro = ch, ""
                else:
                    self.dentro += ch
                self.prof += 1
                continue
            if ch in _CIERRA:
                self.prof = max(0, self.prof - 1)
                if self.prof == 0:
                    # Paréntesis con una fórmula o aclaración corta: se conserva; JSON y argumentos: se descartan
                    d = self.dentro.strip()
                    if self.abre == "(" and d and len(d) <= 60 and not re.search(r"[\"'{}\[\]:_]|=\s*\W", d):
                        for c in f" {d} ":
                            self._agregar(c, out)
                    self.dentro = ""
                else:
                    self.dentro += ch
                continue
            if self.prof > 0:
                self.dentro += ch
                continue
            self._agregar(ch, out)
        return "".join(out)

    def flush(self) -> str:
        self.prof = 0
        self.punto = False
        return self._emitir()


def limpiar(texto: str) -> str:
    l = Limpiador()
    return (l.feed(texto) + l.flush()).strip()
