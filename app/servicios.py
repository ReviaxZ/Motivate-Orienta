"""
Gestor de servicios de Motivate (sin Docker).

Arranca como procesos nativos lo que antes eran contenedores:
  - web         FastAPI/uvicorn en el puerto 7878 (pagina principal, panel, API)
  - orientador  agente de voz Lucia / Fabiola (orientacion) en LiveKit
  - fabiola     agente de voz Fabiola (cobros) en LiveKit
  - ngrok       tunel publico opcional hacia el puerto 7878

Cada servicio escribe su salida en ~/.local/share/motivate/logs/<servicio>.log
y su PID en ~/.local/share/motivate/run/<servicio>.pid, asi la ventana Tk y el
modo --headless (systemd) ven los mismos procesos.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

VERSION = "1.0.0"

APP_DIR = Path(__file__).resolve().parent.parent          # /opt/motivate
PROYECTO = APP_DIR / "proyecto"                            # codigo original del proyecto
ASSETS = APP_DIR / "assets"

XDG_CONFIG = Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config"))
XDG_DATA = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
CONFIG_FILE = Path(os.getenv("MOTIVATE_CONFIG", XDG_CONFIG / "motivate" / "motivate.env"))
DATA_DIR = Path(os.getenv("MOTIVATE_DATA", XDG_DATA / "motivate"))
LOG_DIR = DATA_DIR / "logs"
RUN_DIR = DATA_DIR / "run"
DB_FILE = DATA_DIR / "datos" / "orientador.db"
HEADLESS_PID = RUN_DIR / "headless.pid"

LOG_MAX_BYTES = 5 * 1024 * 1024

# Claves minimas para que cada servicio funcione
REQUERIDAS = {
    "web": ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "INTERNAL_TOKEN", "PANEL_PASSWORD"],
    "orientador": ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "SONIOX_API_KEY",
                   "FISH_AUDIO_API_KEY", "CEREBRAS_API_KEY", "INTERNAL_TOKEN"],
    "fabiola": ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "SONIOX_API_KEY",
                "FISH_AUDIO_API_KEY", "CEREBRAS_API_KEY"],
    "ngrok": ["NGROK_AUTHTOKEN"],
}


# ----------------------------------------------------------------- configuracion
def _leer_env(path: Path) -> dict[str, str]:
    """Lee un archivo KEY=VALUE (acepta comillas y comentarios)."""
    datos: dict[str, str] = {}
    if not path.exists():
        return datos
    for linea in path.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        if linea.startswith("export "):
            linea = linea[7:]
        k, v = linea.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        elif " #" in v:
            v = v.split(" #", 1)[0].rstrip()
        datos[k] = v
    return datos


def asegurar_config() -> Path:
    """Crea la configuracion del usuario la primera vez (desde la copia incluida)."""
    if not CONFIG_FILE.exists():
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        for origen in (APP_DIR / "config" / "motivate.env", APP_DIR / "config" / "motivate.env.example"):
            if origen.exists():
                shutil.copyfile(origen, CONFIG_FILE)
                break
        else:
            CONFIG_FILE.write_text("MOTIVATE_PORT=7878\n", encoding="utf-8")
        os.chmod(CONFIG_FILE, 0o600)
    return CONFIG_FILE


def cargar_config() -> dict[str, str]:
    asegurar_config()
    return _leer_env(CONFIG_FILE)


def puerto(cfg: dict[str, str] | None = None) -> int:
    cfg = cfg if cfg is not None else cargar_config()
    try:
        return int(cfg.get("MOTIVATE_PORT", "7878"))
    except ValueError:
        return 7878


def faltantes(nombre: str, cfg: dict[str, str]) -> list[str]:
    return [k for k in REQUERIDAS.get(nombre, []) if not cfg.get(k, "").strip()]


# ----------------------------------------------------------------- utilidades
def ips_locales() -> list[str]:
    ips: list[str] = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=2).stdout.split()
        ips += [ip for ip in out if ":" not in ip and ip not in ips]
    except Exception:
        pass
    return [ip for ip in ips if not ip.startswith("127.")] or ["127.0.0.1"]


def puerto_ocupado(p: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", p)) == 0


def http_ok(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def url_ngrok() -> str:
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1.5) as r:
            for t in json.loads(r.read().decode()).get("tunnels", []):
                if t.get("public_url", "").startswith("https://"):
                    return t["public_url"]
    except Exception:
        pass
    return ""


def _pid_vivo(pid: int) -> bool:
    try:
        estado = Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0]
        return estado not in ("Z", "X")
    except (OSError, IndexError):
        return False


def _cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return ""


def headless_activo() -> int:
    """PID del modo --headless (systemd) si esta corriendo."""
    try:
        pid = int(HEADLESS_PID.read_text().strip())
        if pid != os.getpid() and _pid_vivo(pid) and "--headless" in _cmdline(pid):
            return pid
    except (OSError, ValueError):
        pass
    return 0


# ----------------------------------------------------------------- servicios
@dataclass
class Servicio:
    nombre: str
    titulo: str
    descripcion: str
    cwd: Path
    args: list[str]
    marca: str                      # texto que identifica el proceso en /proc/<pid>/cmdline
    proc: subprocess.Popen | None = None
    pid: int = 0
    inicio: float = 0.0
    deseado: bool = False           # el usuario lo quiere encendido (para el reinicio automatico)
    reinicios: list[float] = field(default_factory=list)
    ultimo_error: str = ""

    @property
    def log(self) -> Path:
        return LOG_DIR / f"{self.nombre}.log"

    @property
    def pidfile(self) -> Path:
        return RUN_DIR / f"{self.nombre}.pid"


class Gestor:
    def __init__(self) -> None:
        for d in (LOG_DIR, RUN_DIR, DB_FILE.parent):
            d.mkdir(parents=True, exist_ok=True)
        self.cfg = cargar_config()
        py = sys.executable
        web = PROYECTO / "web"
        self.servicios: dict[str, Servicio] = {
            "web": Servicio("web", "Web principal", "Pagina de Lucia, panel y API (FastAPI)",
                            web, [py, str(web / "server.py")], str(web / "server.py")),
            "orientador": Servicio("orientador", "Orientadoras Lucia y Fabiola",
                                   "Voz: Soniox + Cerebras + Fish Audio",
                                   PROYECTO / "orientador",
                                   [py, str(PROYECTO / "orientador" / "agent.py"), "start"],
                                   str(PROYECTO / "orientador" / "agent.py")),
            "fabiola": Servicio("fabiola", "Agente Fabiola (cobros)", "Agente de voz en /fabiola/",
                                PROYECTO, [py, str(PROYECTO / "agent.py"), "start"], str(PROYECTO / "agent.py")),
            "ngrok": Servicio("ngrok", "Tunel ngrok", "URL publica https (opcional)",
                              DATA_DIR, ["ngrok", "http", "7878", "--log", "stdout"], "ngrok http"),
        }
        self._adoptar()

    # ------------------------------------------------------------ estado
    def recargar_config(self) -> None:
        self.cfg = cargar_config()

    @property
    def puerto(self) -> int:
        return puerto(self.cfg)

    def habilitados(self) -> list[str]:
        lista = self.cfg.get("MOTIVATE_SERVICIOS", "web,orientador,fabiola")
        nombres = [n.strip() for n in lista.split(",") if n.strip() in self.servicios]
        if self.cfg.get("NGROK_ENABLED", "0").strip().lower() in ("1", "true", "si", "yes") and "ngrok" not in nombres:
            nombres.append("ngrok")
        return nombres

    def ngrok_disponible(self) -> bool:
        return shutil.which("ngrok") is not None

    def _adoptar(self) -> None:
        """Recupera procesos que siguen vivos de una sesion anterior (pidfile)."""
        for s in self.servicios.values():
            try:
                pid = int(s.pidfile.read_text().strip())
            except (OSError, ValueError):
                continue
            if _pid_vivo(pid) and s.marca in _cmdline(pid):
                s.pid = pid
                s.inicio = s.pidfile.stat().st_mtime
                s.deseado = True
            else:
                s.pidfile.unlink(missing_ok=True)

    def vivo(self, nombre: str) -> bool:
        s = self.servicios[nombre]
        if s.proc is not None:
            if s.proc.poll() is None:
                return True
            s.ultimo_error = f"termino con codigo {s.proc.returncode}"
            s.proc = None
            s.pid = 0
            s.pidfile.unlink(missing_ok=True)
            return False
        if s.pid and _pid_vivo(s.pid) and s.marca in _cmdline(s.pid):
            return True
        if s.pid:
            s.pid = 0
            s.pidfile.unlink(missing_ok=True)
        return False

    def estado(self, nombre: str) -> tuple[str, str]:
        """(codigo, texto). codigo: off | arrancando | ok | error | externo"""
        s = self.servicios[nombre]
        if not self.vivo(nombre):
            if nombre == "web" and puerto_ocupado(self.puerto):
                return "externo", f"Puerto {self.puerto} ocupado por otro proceso"
            if s.ultimo_error and s.deseado:
                return "error", f"Detenido: {s.ultimo_error}"
            return "off", "Detenido"
        if nombre == "web":
            # Conexion TCP (no HTTP) para no llenar el registro de accesos cada 2 segundos
            if puerto_ocupado(self.puerto):
                return "ok", f"Activo en el puerto {self.puerto}"
            return "arrancando", "Iniciando..."
        if nombre == "ngrok":
            u = url_ngrok()
            return ("ok", u) if u else ("arrancando", "Conectando...")
        cola = self.leer_cola(nombre, 40000)
        if "registered worker" in cola.lower():
            return "ok", "Conectado a LiveKit"
        reciente = cola[-4000:].lower()
        if time.time() - s.inicio > 20 and ('"level": "error"' in reciente or "traceback" in reciente
                                            or "failed to connect" in reciente):
            return "error", "Sin conexion a LiveKit (ver registros)"
        return "arrancando", "Conectando a LiveKit..."

    def uptime(self, nombre: str) -> str:
        s = self.servicios[nombre]
        if not self.vivo(nombre) or not s.inicio:
            return ""
        seg = int(time.time() - s.inicio)
        h, r = divmod(seg, 3600)
        m, sg = divmod(r, 60)
        return f"{h}h {m:02d}m" if h else f"{m}m {sg:02d}s"

    # ------------------------------------------------------------ entorno
    def _entorno(self, nombre: str) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self.cfg)
        p = str(self.puerto)
        env["PYTHONUNBUFFERED"] = "1"
        env["PORT"] = p
        if nombre == "web":
            env["DB_PATH"] = str(DB_FILE)
            env.setdefault("AGENT_NAME", "fabiola")
        elif nombre == "orientador":
            env["DATA_DIR"] = str(PROYECTO / "web" / "data")
            env["WEB_INTERNAL_URL"] = f"http://127.0.0.1:{p}"
            env["AGENT_HTTP_PORT"] = self.cfg.get("ORIENTADOR_HTTP_PORT", "8082")
        elif nombre == "fabiola":
            env["AGENT_HTTP_PORT"] = self.cfg.get("FABIOLA_HTTP_PORT", "8081")
        return env

    # ------------------------------------------------------------ control
    def iniciar(self, nombre: str) -> str:
        s = self.servicios[nombre]
        s.deseado = True
        if self.vivo(nombre):
            return f"{s.titulo} ya esta activo"
        self.recargar_config()
        falta = faltantes(nombre, self.cfg)
        if falta:
            s.ultimo_error = "faltan " + ", ".join(falta)
            return f"{s.titulo}: faltan en la configuracion {', '.join(falta)}"
        if nombre == "web" and puerto_ocupado(self.puerto):
            s.ultimo_error = f"puerto {self.puerto} ocupado"
            return f"El puerto {self.puerto} ya esta en uso por otro proceso"
        args = list(s.args)
        if nombre == "ngrok":
            if not self.ngrok_disponible():
                s.ultimo_error = "ngrok no esta instalado"
                return "ngrok no esta instalado (ver README_ROCKY.md)"
            args = ["ngrok", "http", str(self.puerto), "--log", "stdout"]
        if s.log.exists() and s.log.stat().st_size > LOG_MAX_BYTES:
            s.log.replace(s.log.with_suffix(".log.1"))
        f = open(s.log, "ab", buffering=0)
        f.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} inicio de {s.titulo} =====\n".encode())
        try:
            s.proc = subprocess.Popen(args, cwd=s.cwd, env=self._entorno(nombre), stdout=f,
                                      stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        except OSError as e:
            s.ultimo_error = str(e)
            return f"No se pudo iniciar {s.titulo}: {e}"
        finally:
            f.close()
        s.pid = s.proc.pid
        s.inicio = time.time()
        s.ultimo_error = ""
        s.pidfile.write_text(str(s.pid))
        return f"{s.titulo} iniciado (PID {s.pid})"

    def detener(self, nombre: str, espera: float = 10.0) -> str:
        s = self.servicios[nombre]
        s.deseado = False
        if not self.vivo(nombre):
            return f"{s.titulo} ya estaba detenido"
        pid = s.pid
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        limite = time.time() + espera
        while time.time() < limite and self.vivo(nombre):
            time.sleep(0.2)
        if self.vivo(nombre):
            try:
                os.killpg(pid, signal.SIGKILL)
            except OSError:
                pass
            time.sleep(0.3)
            self.vivo(nombre)
        s.proc = None
        s.pid = 0
        s.inicio = 0
        s.ultimo_error = ""
        s.pidfile.unlink(missing_ok=True)
        with open(s.log, "ab") as f:
            f.write(f"===== {time.strftime('%Y-%m-%d %H:%M:%S')} detenido =====\n".encode())
        return f"{s.titulo} detenido"

    def reiniciar(self, nombre: str) -> str:
        self.detener(nombre)
        return self.iniciar(nombre)

    def iniciar_todo(self) -> list[str]:
        orden = ["web", "orientador", "fabiola", "ngrok"]
        return [self.iniciar(n) for n in orden if n in self.habilitados()]

    def detener_todo(self) -> list[str]:
        return [self.detener(n) for n in ["ngrok", "fabiola", "orientador", "web"] if self.vivo(n)]

    def vigilar(self) -> list[str]:
        """Reinicio automatico: vuelve a levantar lo que se cayo (max 5 veces en 5 minutos)."""
        msgs = []
        ahora = time.time()
        for n, s in self.servicios.items():
            if not s.deseado or self.vivo(n):
                continue
            if s.ultimo_error.startswith("faltan") or "ocupado" in s.ultimo_error or "instalado" in s.ultimo_error:
                continue
            s.reinicios = [t for t in s.reinicios if ahora - t < 300]
            if len(s.reinicios) >= 5:
                continue
            espera = 2 ** len(s.reinicios)
            if s.reinicios and ahora - s.reinicios[-1] < espera:
                continue
            s.reinicios.append(ahora)
            msgs.append(f"Reinicio automatico: {self.iniciar(n)}")
        return msgs

    # ------------------------------------------------------------ registros
    def leer_cola(self, nombre: str, max_bytes: int = 200_000) -> str:
        p = self.servicios[nombre].log
        if not p.exists():
            return ""
        with open(p, "rb") as f:
            f.seek(0, 2)
            tam = f.tell()
            f.seek(max(0, tam - max_bytes))
            return f.read().decode("utf-8", errors="replace")


# ----------------------------------------------------------------- sesiones (SQLite)
COLUMNAS_SESION = ["id", "creada", "actualizada", "modo", "nombre", "correo", "pais", "departamento", "municipio",
                   "zona", "nivel_economico", "carrera_top", "carrera_elegida", "dictamen", "alerta_bienestar",
                   "estado", "cita_estado", "correo_estado", "idioma"]


def sesiones(limite: int = 2000) -> list[dict]:
    if not DB_FILE.exists():
        return []
    con = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        existentes = {r[1] for r in con.execute("PRAGMA table_info(entrevistas)")}
        cols = [c for c in COLUMNAS_SESION if c in existentes] + (["doc"] if "doc" in existentes else [])
        filas = con.execute(f"SELECT {', '.join(cols)} FROM entrevistas ORDER BY creada DESC LIMIT ?", (limite,))
        return [dict(r) for r in filas]
    except sqlite3.Error:
        return []
    finally:
        con.close()


def exportar_csv(destino: Path) -> int:
    import csv
    filas = sesiones(100000)
    with open(destino, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNAS_SESION, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    return len(filas)


def exportar_json(destino: Path) -> int:
    filas = sesiones(100000)
    salida = []
    for r in filas:
        r = dict(r)
        try:
            r["doc"] = json.loads(r.get("doc") or "{}")
        except ValueError:
            pass
        salida.append(r)
    destino.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(salida)


def respaldar_db(destino: Path) -> None:
    if not DB_FILE.exists():
        raise FileNotFoundError("Todavia no hay base de datos")
    origen = sqlite3.connect(DB_FILE)
    copia = sqlite3.connect(destino)
    with copia:
        origen.backup(copia)
    origen.close()
    copia.close()


def importar_db(origen: Path) -> Path | None:
    """Reemplaza la base (por ejemplo la del volumen Docker). Respalda la actual antes."""
    con = sqlite3.connect(f"file:{origen}?mode=ro", uri=True)
    try:
        con.execute("SELECT count(*) FROM entrevistas").fetchone()
    finally:
        con.close()
    respaldo = None
    if DB_FILE.exists():
        respaldo = DB_FILE.with_name(f"orientador-respaldo-{time.strftime('%Y%m%d-%H%M%S')}.db")
        respaldar_db(respaldo)
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origen, DB_FILE)
    return respaldo


# ----------------------------------------------------------------- modo headless
def headless() -> int:
    g = Gestor()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    HEADLESS_PID.write_text(str(os.getpid()))
    corriendo = True

    def _salir(*_):
        nonlocal corriendo
        corriendo = False

    signal.signal(signal.SIGTERM, _salir)
    signal.signal(signal.SIGINT, _salir)
    for m in g.iniciar_todo():
        print(m, flush=True)
    print(f"Motivate {VERSION}: web en http://{ips_locales()[0]}:{g.puerto}/", flush=True)
    try:
        while corriendo:
            for m in g.vigilar():
                print(m, flush=True)
            time.sleep(2)
    finally:
        for m in g.detener_todo():
            print(m, flush=True)
        HEADLESS_PID.unlink(missing_ok=True)
    return 0
