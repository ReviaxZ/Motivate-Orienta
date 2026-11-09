#!/usr/bin/env python3
"""
Motivate - app de escritorio Tcl/Tk para Rocky Linux.

  motivate                 abre la ventana (Tk)
  motivate --headless      arranca los servicios sin ventana (para systemd)
  motivate --status        muestra el estado en la terminal
  motivate --stop          detiene todos los servicios
  motivate --export-csv F  exporta las sesiones a CSV
"""

from __future__ import annotations

import argparse
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import servicios as S  # noqa: E402

# ----------------------------------------------------------------- paleta (misma que la web)
BG = "#f5f3ee"
SURFACE = "#ffffff"
SURFACE2 = "#faf9f6"
INK = "#17202b"
MUTED = "#5e6a77"
LINE = "#e5e1d7"
PRIMARY = "#3346c4"
PRIMARY_DARK = "#26359e"
HEADER = "#1f2b8f"
HEADER_SOFT = "#c9cff7"
ACCENT = "#f2a516"
GOOD = "#1b9b67"
WARN = "#c7811a"
DANGER = "#d23f3f"
INFO = "#2a7bd6"
OFF = "#b8bfc8"
TERM_BG = "#11151b"
TERM_FG = "#dde3ea"

COLOR_ESTADO = {"ok": GOOD, "arrancando": WARN, "error": DANGER, "off": OFF, "externo": INFO}
ORDEN = ["web", "orientador", "fabiola", "ngrok"]


def corto(p) -> str:
    s, h = str(p), str(Path.home())
    return "~" + s[len(h):] if s.startswith(h + "/") else s


def abrir(destino: str) -> None:
    """Abre una URL o carpeta con la aplicacion del escritorio."""
    if shutil.which("xdg-open"):
        subprocess.Popen(["xdg-open", destino], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    else:
        threading.Thread(target=webbrowser.open, args=(destino,), daemon=True).start()


# ================================================================= GUI
def gui() -> int:
    try:
        import tkinter as tk
        from tkinter import filedialog, font as tkfont, messagebox, ttk
    except ImportError:
        print("Falta Tkinter. En Rocky Linux: sudo dnf install python3.12-tkinter  (o python3.11-tkinter)")
        return 1

    class App:
        def __init__(self) -> None:
            self.root = tk.Tk(className="Motivate")
            self.root.title("Motivate - Orientacion vocacional por voz")
            self.root.geometry("1140x800")
            self.root.minsize(980, 700)
            self.root.configure(bg=BG)
            self._iconos()
            self._estilos()

            self.g = S.Gestor()
            self.jobs: queue.Queue = queue.Queue()
            self.ui: queue.Queue = queue.Queue()
            self.auto = tk.BooleanVar(value=True)
            self._auto_flag = True
            self.snap: dict = {}
            self.log_pos: dict[str, int] = {}

            self._header()
            self._barra_estado()
            self._cuerpo()

            threading.Thread(target=self._trabajador, daemon=True).start()
            self.root.after(150, self._procesar_ui)
            self.root.after(600, self._tail_logs)
            self.root.protocol("WM_DELETE_WINDOW", self._cerrar)

            if S.headless_activo():
                self._msg("Los servicios los administra el modo headless (systemd: motivate.service)")
            elif self.g.cfg.get("MOTIVATE_AUTOSTART", "1").strip() in ("1", "true", "si", "yes"):
                self._job(lambda: "; ".join(self.g.iniciar_todo()) or "Servicios listos")

        # ------------------------------------------------------------ apariencia
        def _iconos(self) -> None:
            self.img = {}
            try:
                for t in (256, 128, 64, 48, 32, 16):
                    p = S.ASSETS / f"motivate-{t}.png"
                    if p.exists():
                        self.img[t] = tk.PhotoImage(file=str(p))
                if self.img:
                    self.root.iconphoto(True, *[self.img[t] for t in sorted(self.img, reverse=True)])
            except tk.TclError:
                pass

        def _familia(self, opciones: list[str], defecto: str) -> str:
            disponibles = set(tkfont.families(self.root))
            return next((f for f in opciones if f in disponibles), defecto)

        def _estilos(self) -> None:
            sans = self._familia(["Red Hat Text", "Cantarell", "Noto Sans", "Inter", "DejaVu Sans",
                                  "Liberation Sans"], "TkDefaultFont")
            disp = self._familia(["Red Hat Display", "Cantarell", "Noto Sans", "DejaVu Sans"], sans)
            mono = self._familia(["Red Hat Mono", "JetBrains Mono", "Noto Sans Mono", "DejaVu Sans Mono",
                                  "Liberation Mono"], "TkFixedFont")
            self.f = {
                "base": (sans, 10), "small": (sans, 9), "bold": (sans, 10, "bold"),
                "title": (disp, 12, "bold"), "h1": (disp, 18, "bold"), "url": (disp, 14, "bold"),
                "mono": (mono, 10), "sub": (sans, 10),
            }
            st = ttk.Style(self.root)
            st.theme_use("clam")
            st.configure(".", background=BG, foreground=INK, font=self.f["base"], bordercolor=LINE,
                         focuscolor=PRIMARY, lightcolor=SURFACE, darkcolor=LINE, troughcolor=SURFACE2)
            st.configure("TFrame", background=BG)
            st.configure("Card.TFrame", background=SURFACE, relief="solid", borderwidth=1)
            st.configure("Plain.TFrame", background=SURFACE)
            st.configure("Header.TFrame", background=HEADER)
            st.configure("TLabel", background=BG, foreground=INK)
            st.configure("Muted.TLabel", background=BG, foreground=MUTED, font=self.f["small"])
            st.configure("Section.TLabel", background=BG, foreground=INK, font=self.f["title"])
            st.configure("Card.TLabel", background=SURFACE, foreground=INK)
            st.configure("CardTitle.TLabel", background=SURFACE, foreground=INK, font=self.f["title"])
            st.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED, font=self.f["small"])
            st.configure("CardStatus.TLabel", background=SURFACE, foreground=INK, font=self.f["bold"])
            st.configure("Link.TLabel", background=SURFACE, foreground=PRIMARY, font=self.f["bold"])
            st.configure("H.TLabel", background=HEADER, foreground="#ffffff", font=self.f["h1"])
            st.configure("HSub.TLabel", background=HEADER, foreground=HEADER_SOFT, font=self.f["sub"])
            st.configure("HUrl.TLabel", background=HEADER, foreground="#ffffff", font=self.f["url"])
            st.configure("Status.TLabel", background=SURFACE2, foreground=MUTED, font=self.f["small"],
                         padding=(12, 5))
            st.configure("TButton", background=SURFACE, foreground=INK, padding=(12, 6), relief="flat",
                         bordercolor=LINE, lightcolor=SURFACE, darkcolor=SURFACE)
            st.map("TButton", background=[("disabled", SURFACE2), ("active", "#eef0fb")],
                   foreground=[("disabled", OFF)], bordercolor=[("active", PRIMARY)])
            st.configure("Primary.TButton", background=PRIMARY, foreground="#ffffff", bordercolor=PRIMARY,
                         lightcolor=PRIMARY, darkcolor=PRIMARY, font=self.f["bold"])
            st.map("Primary.TButton", background=[("disabled", OFF), ("active", PRIMARY_DARK)],
                   bordercolor=[("active", PRIMARY_DARK)])
            st.configure("Header.TButton", background="#34419f", foreground="#ffffff", bordercolor="#4a57b8",
                         lightcolor="#34419f", darkcolor="#34419f", padding=(12, 6))
            st.map("Header.TButton", background=[("active", "#4251bd")], bordercolor=[("active", "#ffffff")])
            st.configure("Accent.TButton", background=ACCENT, foreground=INK, bordercolor=ACCENT,
                         lightcolor=ACCENT, darkcolor=ACCENT, font=self.f["bold"], padding=(14, 6))
            st.map("Accent.TButton", background=[("active", "#f5b942")])
            st.configure("Danger.TButton", foreground=DANGER)
            st.configure("Small.TButton", padding=(8, 3))
            st.configure("TCheckbutton", background=BG, foreground=INK)
            st.map("TCheckbutton", background=[("active", BG)])
            st.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(16, 8, 16, 0))
            st.configure("TNotebook.Tab", background=BG, foreground=MUTED, padding=(18, 9),
                         borderwidth=0, font=self.f["bold"])
            st.map("TNotebook.Tab", background=[("selected", SURFACE)], foreground=[("selected", PRIMARY)],
                   lightcolor=[("selected", SURFACE)], bordercolor=[("selected", LINE)])
            st.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=INK,
                         rowheight=28, bordercolor=LINE, borderwidth=1)
            st.map("Treeview", background=[("selected", "#e3e7fb")], foreground=[("selected", INK)])
            st.configure("Treeview.Heading", background=SURFACE2, foreground=MUTED, font=self.f["bold"],
                         relief="flat", padding=(8, 6))
            st.map("Treeview.Heading", background=[("active", "#eef0fb")])
            st.configure("TEntry", fieldbackground=SURFACE, padding=6)
            st.configure("TCombobox", fieldbackground=SURFACE, padding=4)
            st.configure("Vertical.TScrollbar", background=SURFACE2, troughcolor=BG, bordercolor=BG,
                         arrowcolor=MUTED)

        # ------------------------------------------------------------ cabecera
        def _header(self) -> None:
            h = ttk.Frame(self.root, style="Header.TFrame", padding=(20, 14))
            h.pack(fill="x")
            if 64 in self.img:
                tk.Label(h, image=self.img[64], bg=HEADER, bd=0).pack(side="left", padx=(0, 14))
            tit = ttk.Frame(h, style="Header.TFrame")
            tit.pack(side="left")
            ttk.Label(tit, text="Motivate", style="H.TLabel").pack(anchor="w")
            ttk.Label(tit, text="Lucia y Fabiola - orientacion vocacional por voz con IA",
                      style="HSub.TLabel").pack(anchor="w")

            der = ttk.Frame(h, style="Header.TFrame")
            der.pack(side="right")
            ttk.Label(der, text="WEB PRINCIPAL", style="HSub.TLabel").grid(row=0, column=0, columnspan=3, sticky="e")
            self.lbl_url = ttk.Label(der, text="", style="HUrl.TLabel")
            self.lbl_url.grid(row=1, column=0, sticky="e", padx=(0, 12))
            ttk.Button(der, text="Abrir", style="Accent.TButton",
                       command=lambda: abrir(self._url_local("/"))).grid(row=1, column=1, padx=(0, 6))
            ttk.Button(der, text="Copiar", style="Header.TButton",
                       command=self._copiar_url).grid(row=1, column=2)

        def _url_lan(self, ruta: str = "/") -> str:
            return f"http://{S.ips_locales()[0]}:{self.g.puerto}{ruta}"

        def _url_local(self, ruta: str = "/") -> str:
            return f"http://127.0.0.1:{self.g.puerto}{ruta}"

        def _copiar_url(self) -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.lbl_url.cget("text"))
            self._msg("URL copiada al portapapeles")

        # ------------------------------------------------------------ pestanas
        def _cuerpo(self) -> None:
            self.nb = ttk.Notebook(self.root)
            self.nb.pack(fill="both", expand=True, padx=0, pady=(6, 0))
            self._tab_servicios()
            self._tab_registros()
            self._tab_sesiones()
            self._tab_config()
            self._tab_acerca()

        def _tab_servicios(self) -> None:
            t = ttk.Frame(self.nb, padding=(20, 16))
            self.nb.add(t, text="Servicios")

            barra = ttk.Frame(t)
            barra.pack(fill="x", pady=(0, 12))
            ttk.Button(barra, text="Iniciar todo", style="Primary.TButton",
                       command=lambda: self._job(lambda: "; ".join(self.g.iniciar_todo()) or "Nada que iniciar")
                       ).pack(side="left")
            ttk.Button(barra, text="Detener todo", style="Danger.TButton",
                       command=lambda: self._job(lambda: "; ".join(self.g.detener_todo()) or "Todo detenido")
                       ).pack(side="left", padx=8)
            ttk.Button(barra, text="Reiniciar todo",
                       command=lambda: self._job(self._reiniciar_todo)).pack(side="left")
            ttk.Checkbutton(barra, text="Reinicio automatico si un servicio se cae", variable=self.auto,
                            command=self._toggle_auto).pack(side="right")

            self.banner = tk.Label(t, text="", bg="#fff4dc", fg="#7a4d00", anchor="w", padx=12, pady=8,
                                   font=self.f["base"])

            self.cards: dict[str, dict] = {}
            cont = ttk.Frame(t)
            cont.pack(fill="x")
            self.cont_cards = cont
            for n in ORDEN:
                s = self.g.servicios[n]
                c = ttk.Frame(cont, style="Card.TFrame", padding=(16, 9))
                c.pack(fill="x", pady=4)
                c.columnconfigure(1, weight=1)
                dot = tk.Canvas(c, width=14, height=14, bg=SURFACE, highlightthickness=0)
                dot.grid(row=0, column=0, rowspan=2, padx=(0, 14))
                oval = dot.create_oval(2, 2, 13, 13, fill=OFF, outline="")
                ttk.Label(c, text=s.titulo, style="CardTitle.TLabel").grid(row=0, column=1, sticky="w")
                ttk.Label(c, text=s.descripcion, style="CardMuted.TLabel").grid(row=1, column=1, sticky="w")
                est = ttk.Label(c, text="Detenido", style="CardStatus.TLabel", width=32, anchor="e")
                est.grid(row=0, column=2, sticky="e", padx=12)
                det = ttk.Label(c, text="", style="CardMuted.TLabel", width=32, anchor="e")
                det.grid(row=1, column=2, sticky="e", padx=12)
                bts = ttk.Frame(c, style="Plain.TFrame")
                bts.grid(row=0, column=3, rowspan=2)
                b1 = ttk.Button(bts, text="Iniciar", width=8, style="Small.TButton",
                                command=lambda n=n: self._job(lambda: self.g.iniciar(n)))
                b2 = ttk.Button(bts, text="Detener", width=8, style="Small.TButton",
                                command=lambda n=n: self._job(lambda: self.g.detener(n)))
                b3 = ttk.Button(bts, text="Reiniciar", width=8, style="Small.TButton",
                                command=lambda n=n: self._job(lambda: self.g.reiniciar(n)))
                b4 = ttk.Button(bts, text="Registros", width=8, style="Small.TButton", command=lambda n=n: self._ver_log(n))
                for i, b in enumerate((b1, b2, b3, b4)):
                    b.grid(row=0, column=i, padx=2)
                self.cards[n] = {"dot": dot, "oval": oval, "est": est, "det": det, "b": (b1, b2, b3)}

            acc = ttk.Frame(t)
            acc.pack(fill="x", pady=(12, 0))
            ttk.Label(acc, text="Accesos", style="Section.TLabel").pack(anchor="w", pady=(0, 6))
            caja = ttk.Frame(acc, style="Card.TFrame", padding=(16, 8))
            caja.pack(fill="x")
            caja.columnconfigure(1, weight=1)
            enlaces = [
                ("Pagina principal (Lucia)", "/", "Estudiantes de colegio: orientacion vocacional"),
                ("Panel del psicologo", "/panel/", "Usuario 'panel' y la PANEL_PASSWORD de la configuracion"),
                ("Fabiola (cobros)", "/fabiola/", "Agente de voz de cobros"),
                ("Estado del servidor", "/healthz", "Comprobacion rapida de salud"),
            ]
            for i, (txt, ruta, desc) in enumerate(enlaces):
                lk = ttk.Label(caja, text=txt, style="Link.TLabel", cursor="hand2")
                lk.grid(row=i, column=0, sticky="w", pady=3)
                lk.bind("<Button-1>", lambda e, r=ruta: abrir(self._url_local(r)))
                ttk.Label(caja, text=desc, style="CardMuted.TLabel").grid(row=i, column=1, sticky="w", padx=16)
                ttk.Button(caja, text="Copiar URL", style="Small.TButton",
                           command=lambda r=ruta: self._copiar(self._url_lan(r))).grid(row=i, column=2, sticky="e",
                                                                                       pady=1)
            self.lbl_red = ttk.Label(caja, text="", style="CardMuted.TLabel", justify="left")
            self.lbl_red.grid(row=len(enlaces), column=0, columnspan=3, sticky="w", pady=(8, 0))

        def _tab_registros(self) -> None:
            t = ttk.Frame(self.nb, padding=(20, 16))
            self.nb.add(t, text="Registros")
            barra = ttk.Frame(t)
            barra.pack(fill="x", pady=(0, 10))
            ttk.Label(barra, text="Servicio:").pack(side="left")
            self.log_sel = tk.StringVar(value="web")
            cb = ttk.Combobox(barra, textvariable=self.log_sel, values=ORDEN, state="readonly", width=14)
            cb.pack(side="left", padx=8)
            cb.bind("<<ComboboxSelected>>", lambda e: self._recargar_log())
            self.seguir = tk.BooleanVar(value=True)
            ttk.Checkbutton(barra, text="Seguir al final", variable=self.seguir).pack(side="left", padx=8)
            ttk.Button(barra, text="Abrir carpeta", command=lambda: abrir(str(S.LOG_DIR))).pack(side="right")
            ttk.Button(barra, text="Recargar", command=self._recargar_log).pack(side="right", padx=8)

            marco = ttk.Frame(t, style="Card.TFrame")
            marco.pack(fill="both", expand=True)
            self.txt_log = tk.Text(marco, bg=TERM_BG, fg=TERM_FG, insertbackground=TERM_FG, font=self.f["mono"],
                                   relief="flat", wrap="none", padx=12, pady=10, borderwidth=0,
                                   selectbackground="#2f3a4a")
            sb = ttk.Scrollbar(marco, orient="vertical", command=self.txt_log.yview)
            sbx = ttk.Scrollbar(marco, orient="horizontal", command=self.txt_log.xview)
            self.txt_log.configure(yscrollcommand=sb.set, xscrollcommand=sbx.set)
            sb.pack(side="right", fill="y")
            sbx.pack(side="bottom", fill="x")
            self.txt_log.pack(fill="both", expand=True)
            self.txt_log.tag_configure("err", foreground="#ff8a8a")
            self.txt_log.tag_configure("warn", foreground="#f5c26b")
            self.txt_log.tag_configure("sep", foreground="#8fa2ff", font=(self.f["mono"][0], 10, "bold"))
            self.txt_log.tag_configure("ok", foreground="#7fe0b0")
            self.txt_log.configure(state="disabled")
            self._recargar_log()

        def _tab_sesiones(self) -> None:
            t = ttk.Frame(self.nb, padding=(20, 16))
            self.nb.add(t, text="Sesiones y exportacion")
            barra = ttk.Frame(t)
            barra.pack(fill="x", pady=(0, 10))
            ttk.Button(barra, text="Actualizar", command=self._cargar_sesiones).pack(side="left")
            ttk.Button(barra, text="Exportar CSV", style="Primary.TButton",
                       command=lambda: self._exportar("csv")).pack(side="left", padx=(8, 0))
            ttk.Button(barra, text="Exportar JSON", command=lambda: self._exportar("json")).pack(side="left", padx=8)
            ttk.Button(barra, text="Respaldar base", command=self._respaldar).pack(side="left")
            ttk.Button(barra, text="Importar base (Docker)", command=self._importar).pack(side="left", padx=8)
            fila2 = ttk.Frame(t)
            fila2.pack(fill="x", pady=(0, 10))
            ttk.Label(fila2, text="Buscar:").pack(side="left")
            self.buscar = tk.StringVar()
            e = ttk.Entry(fila2, textvariable=self.buscar, width=34)
            e.pack(side="left", padx=8)
            e.bind("<KeyRelease>", lambda ev: self._pintar_sesiones())
            ttk.Label(fila2, text="Doble clic en una fila abre sus resultados en el navegador",
                      style="Muted.TLabel").pack(side="left", padx=8)
            ttk.Button(fila2, text="Abrir resultado", command=self._abrir_sesion).pack(side="right")

            marco = ttk.Frame(t)
            marco.pack(fill="both", expand=True)
            cols = [("creada", "Fecha", 140), ("modo", "Modo", 110), ("nombre", "Nombre", 160),
                    ("carrera", "Carrera / dictamen", 220), ("lugar", "Lugar", 190), ("nivel", "Nivel", 70),
                    ("alerta", "Alerta", 60), ("estado", "Estado", 100)]
            self.tv = ttk.Treeview(marco, columns=[c[0] for c in cols], show="headings", selectmode="browse")
            for k, txt, w in cols:
                self.tv.heading(k, text=txt)
                self.tv.column(k, width=w, anchor="w", stretch=k in ("carrera", "lugar", "nombre"))
            self.tv.tag_configure("alerta", foreground=DANGER)
            self.tv.tag_configure("par", background=SURFACE2)
            sb = ttk.Scrollbar(marco, orient="vertical", command=self.tv.yview)
            self.tv.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            self.tv.pack(fill="both", expand=True)
            self.tv.bind("<Double-1>", lambda e: self._abrir_sesion())
            self.lbl_ses = ttk.Label(t, text="", style="Muted.TLabel")
            self.lbl_ses.pack(anchor="w", pady=(8, 0))
            self.filas: list[dict] = []
            self._cargar_sesiones()

        def _tab_config(self) -> None:
            t = ttk.Frame(self.nb, padding=(20, 16))
            self.nb.add(t, text="Configuracion")
            barra = ttk.Frame(t)
            barra.pack(fill="x", pady=(0, 10))
            ttk.Button(barra, text="Guardar", style="Primary.TButton", command=self._guardar_cfg).pack(side="left")
            ttk.Button(barra, text="Guardar y reiniciar servicios",
                       command=lambda: self._guardar_cfg(reiniciar=True)).pack(side="left", padx=8)
            ttk.Button(barra, text="Descartar cambios", command=self._cargar_cfg).pack(side="left")
            ttk.Button(barra, text="Abrir carpeta", command=lambda: abrir(str(S.CONFIG_FILE.parent))
                       ).pack(side="right")
            ttk.Label(barra, text=corto(S.CONFIG_FILE), style="Muted.TLabel").pack(side="right", padx=10)

            cuerpo = ttk.Frame(t)
            cuerpo.pack(fill="both", expand=True)
            marco = ttk.Frame(cuerpo, style="Card.TFrame")
            marco.pack(side="left", fill="both", expand=True)
            self.txt_cfg = tk.Text(marco, bg=SURFACE, fg=INK, insertbackground=PRIMARY, font=self.f["mono"],
                                   relief="flat", wrap="none", padx=12, pady=10, undo=True, borderwidth=0)
            sb = ttk.Scrollbar(marco, orient="vertical", command=self.txt_cfg.yview)
            self.txt_cfg.configure(yscrollcommand=sb.set)
            sb.pack(side="right", fill="y")
            self.txt_cfg.pack(fill="both", expand=True)
            self.txt_cfg.tag_configure("com", foreground="#8a94a0")
            self.txt_cfg.tag_configure("key", foreground=PRIMARY)
            self.txt_cfg.tag_configure("sec", foreground=WARN)
            self.txt_cfg.bind("<KeyRelease>", lambda e: self._resaltar_cfg())

            lado = ttk.Frame(cuerpo, style="Card.TFrame", padding=(16, 14), width=280)
            lado.pack(side="right", fill="y", padx=(12, 0))
            lado.pack_propagate(False)
            ttk.Label(lado, text="Validacion", style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(lado, text="Claves necesarias por servicio", style="CardMuted.TLabel").pack(anchor="w",
                                                                                               pady=(0, 10))
            self.lbl_val = tk.Label(lado, text="", bg=SURFACE, fg=INK, justify="left", anchor="nw",
                                    font=self.f["base"], wraplength=245)
            self.lbl_val.pack(fill="both", expand=True, anchor="w")
            self._cargar_cfg()

        def _tab_acerca(self) -> None:
            t = ttk.Frame(self.nb, padding=(20, 16))
            self.nb.add(t, text="Acerca de")
            c = ttk.Frame(t, style="Card.TFrame", padding=(20, 16))
            c.pack(fill="x")
            if 128 in self.img:
                tk.Label(c, image=self.img[128], bg=SURFACE, bd=0).grid(row=0, column=0, rowspan=9,
                                                                        sticky="n", padx=(0, 20))
            filas = [
                ("Version", f"Motivate {S.VERSION}"),
                ("Python", f"{sys.version.split()[0]}  ({sys.executable})"),
                ("Aplicacion", str(S.APP_DIR)),
                ("Configuracion", corto(S.CONFIG_FILE)),
                ("Datos", corto(S.DATA_DIR)),
                ("Base de datos", corto(S.DB_FILE)),
                ("Registros", corto(S.LOG_DIR)),
                ("Servicio systemd", "sudo systemctl enable --now motivate   (arranque sin ventana)"),
                ("Firewall", f"sudo firewall-cmd --permanent --add-port={self.g.puerto}/tcp && "
                             "sudo firewall-cmd --reload"),
            ]
            for i, (k, v) in enumerate(filas):
                ttk.Label(c, text=k, style="CardMuted.TLabel").grid(row=i, column=1, sticky="w", pady=3)
                e = ttk.Label(c, text=v, style="Card.TLabel")
                e.grid(row=i, column=2, sticky="w", padx=16, pady=3)
            ttk.Label(t, text="Proyecto Motivate (Orienta): Lucia orienta a estudiantes de colegio y Fabiola "
                              "acompana a universitarios. Esta app reemplaza docker compose: corre la web y los "
                              "agentes como procesos nativos y expone la web principal en el puerto "
                              f"{self.g.puerto}.", style="Muted.TLabel", wraplength=900, justify="left"
                      ).pack(anchor="w", pady=(14, 0))

        def _barra_estado(self) -> None:
            b = ttk.Frame(self.root, style="Plain.TFrame")
            b.pack(fill="x", side="bottom")
            tk.Frame(b, height=1, bg=LINE).pack(fill="x")
            fila = ttk.Frame(b, style="Plain.TFrame")
            fila.pack(fill="x")
            self.lbl_msg = ttk.Label(fila, text="Listo", style="Status.TLabel")
            self.lbl_msg.pack(side="left")
            self.lbl_cuenta = ttk.Label(fila, text="", style="Status.TLabel")
            self.lbl_cuenta.pack(side="right")

        # ------------------------------------------------------------ hilo de trabajo
        def _job(self, fn) -> None:
            self.jobs.put(fn)

        def _toggle_auto(self) -> None:
            self._auto_flag = bool(self.auto.get())

        def _reiniciar_todo(self) -> str:
            activos = [n for n in ORDEN if self.g.vivo(n)] or self.g.habilitados()
            for n in reversed(activos):
                self.g.detener(n)
            return "; ".join(self.g.iniciar(n) for n in ORDEN if n in activos)

        def _foto(self) -> dict:
            snap = {"svc": {}, "headless": S.headless_activo(), "ips": S.ips_locales(), "puerto": self.g.puerto}
            for n in ORDEN:
                cod, txt = self.g.estado(n)
                s = self.g.servicios[n]
                snap["svc"][n] = (cod, txt, s.pid, self.g.uptime(n))
            snap["ngrok"] = snap["svc"]["ngrok"][1] if snap["svc"]["ngrok"][0] == "ok" else ""
            return snap

        def _trabajador(self) -> None:
            ultimo = 0.0
            while True:
                try:
                    fn = self.jobs.get(timeout=0.5)
                except queue.Empty:
                    fn = None
                if fn is not None:
                    self.ui.put(("msg", "Trabajando..."))
                    try:
                        r = fn()
                    except Exception as e:  # noqa: BLE001
                        r = f"Error: {e}"
                    self.ui.put(("msg", r))
                if fn is not None or time.time() - ultimo > 2:
                    if self._auto_flag and not S.headless_activo():
                        for m in self.g.vigilar():
                            self.ui.put(("msg", m))
                    try:
                        self.ui.put(("snap", self._foto()))
                    except Exception as e:  # noqa: BLE001
                        self.ui.put(("msg", f"Error leyendo estado: {e}"))
                    ultimo = time.time()

        def _procesar_ui(self) -> None:
            try:
                while True:
                    tipo, dato = self.ui.get_nowait()
                    if tipo == "msg":
                        self._msg(dato)
                    elif tipo == "snap":
                        self._pintar(dato)
            except queue.Empty:
                pass
            self.root.after(150, self._procesar_ui)

        def _msg(self, texto: str) -> None:
            self.lbl_msg.configure(text=texto[:180])

        def _copiar(self, texto: str) -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(texto)
            self._msg(f"Copiado: {texto}")

        def _pintar(self, snap: dict) -> None:
            self.snap = snap
            p = snap["puerto"]
            self.lbl_url.configure(text=f"http://{snap['ips'][0]}:{p}/")
            activos = 0
            for n, (cod, txt, pid, up) in snap["svc"].items():
                c = self.cards[n]
                c["dot"].itemconfigure(c["oval"], fill=COLOR_ESTADO.get(cod, OFF))
                c["est"].configure(text=txt if len(txt) < 46 else txt[:44] + "...",
                                   foreground=COLOR_ESTADO.get(cod, INK) if cod in ("error", "ok") else INK)
                c["det"].configure(text=f"PID {pid}  -  {up}" if pid else "")
                vivo = cod in ("ok", "arrancando") or (cod == "error" and pid)
                activos += 1 if vivo else 0
                b1, b2, b3 = c["b"]
                deshab = n == "ngrok" and not self.g.ngrok_disponible()
                b1.state(["disabled"] if (vivo or deshab) else ["!disabled"])
                b2.state(["!disabled"] if vivo else ["disabled"])
                b3.state(["disabled"] if deshab else ["!disabled"])
                if deshab:
                    c["est"].configure(text="ngrok no instalado (opcional)")
            red = "En la red:  " + "    ".join(f"http://{ip}:{p}/" for ip in snap["ips"])
            if snap.get("ngrok"):
                red += f"\nPublica (ngrok):  {snap['ngrok']}/"
            self.lbl_red.configure(text=red)
            total = len([n for n in ORDEN if n in self.g.habilitados()])
            self.lbl_cuenta.configure(text=f"{activos} de {total} servicios activos   |   puerto {p}")
            if snap["headless"]:
                self.banner.configure(text=f"Los servicios corren en modo headless (PID {snap['headless']}, "
                                           "motivate.service). Si los detiene aqui, el servicio los "
                                           "volvera a iniciar; use systemctl para detenerlo.")
                if not self.banner.winfo_ismapped():
                    self.banner.pack(fill="x", pady=(0, 10), before=self.cont_cards)
            elif self.banner.winfo_ismapped():
                self.banner.pack_forget()

        # ------------------------------------------------------------ registros
        def _ver_log(self, n: str) -> None:
            self.log_sel.set(n)
            self._recargar_log()
            self.nb.select(1)

        def _recargar_log(self) -> None:
            n = self.log_sel.get()
            txt = self.g.leer_cola(n, 400_000)
            self.log_pos[n] = self.g.servicios[n].log.stat().st_size if self.g.servicios[n].log.exists() else 0
            self.txt_log.configure(state="normal")
            self.txt_log.delete("1.0", "end")
            self._agregar_log(txt or f"(sin registros de {n} todavia)\n")
            self.txt_log.configure(state="disabled")
            self.txt_log.see("end")

        def _agregar_log(self, texto: str) -> None:
            for linea in texto.splitlines(keepends=True):
                lo = linea.lower()
                tag = ()
                if linea.startswith("====="):
                    tag = ("sep",)
                elif ("traceback" in lo or '"level": "error"' in lo or " error" in lo or "error:" in lo
                      or "exception" in lo):
                    tag = ("err",)
                elif "warn" in lo:
                    tag = ("warn",)
                elif "registered worker" in lo or "application startup complete" in lo or "uvicorn running" in lo:
                    tag = ("ok",)
                self.txt_log.insert("end", linea, tag)
            lineas = int(self.txt_log.index("end-1c").split(".")[0])
            if lineas > 6000:
                self.txt_log.delete("1.0", f"{lineas - 5000}.0")

        def _tail_logs(self) -> None:
            n = self.log_sel.get()
            p = self.g.servicios[n].log
            try:
                tam = p.stat().st_size if p.exists() else 0
                pos = self.log_pos.get(n, 0)
                if tam < pos:
                    self._recargar_log()
                elif tam > pos:
                    with open(p, "rb") as f:
                        f.seek(pos)
                        nuevo = f.read(tam - pos).decode("utf-8", errors="replace")
                    self.log_pos[n] = tam
                    self.txt_log.configure(state="normal")
                    self._agregar_log(nuevo)
                    self.txt_log.configure(state="disabled")
                    if self.seguir.get():
                        self.txt_log.see("end")
            except OSError:
                pass
            self.root.after(700, self._tail_logs)

        # ------------------------------------------------------------ sesiones
        def _cargar_sesiones(self) -> None:
            self.filas = S.sesiones()
            self._pintar_sesiones()

        def _pintar_sesiones(self) -> None:
            q = self.buscar.get().strip().lower()
            self.tv.delete(*self.tv.get_children())
            n = 0
            for r in self.filas:
                carrera = r.get("carrera_elegida") or r.get("carrera_top") or r.get("dictamen") or ""
                lugar = ", ".join(x for x in (r.get("municipio"), r.get("departamento")) if x)
                alerta = "SI" if str(r.get("alerta_bienestar") or "").lower() in ("1", "true", "si") else ""
                vals = ((r.get("creada") or "")[:16].replace("T", " "), r.get("modo") or "", r.get("nombre") or "",
                        carrera, lugar, r.get("nivel_economico") or "", alerta, r.get("estado") or "")
                if q and q not in " ".join(vals).lower() and q not in (r.get("id") or "").lower():
                    continue
                tags = ["alerta"] if alerta else []
                if n % 2:
                    tags.append("par")
                self.tv.insert("", "end", iid=r["id"], values=vals, tags=tags)
                n += 1
            base = "sin base de datos todavia" if not S.DB_FILE.exists() else corto(S.DB_FILE)
            self.lbl_ses.configure(text=f"{n} de {len(self.filas)} sesiones   |   {base}")

        def _abrir_sesion(self) -> None:
            sel = self.tv.selection()
            if not sel:
                self._msg("Seleccione una sesion")
                return
            abrir(self._url_local(f"/#{sel[0]}"))

        def _exportar(self, tipo: str) -> None:
            nombre = f"motivate-sesiones-{time.strftime('%Y%m%d-%H%M')}.{tipo}"
            dest = filedialog.asksaveasfilename(parent=self.root, initialfile=nombre, defaultextension=f".{tipo}",
                                                initialdir=str(Path.home()),
                                                filetypes=[(tipo.upper(), f"*.{tipo}"), ("Todos", "*")])
            if not dest:
                return
            try:
                cant = S.exportar_csv(Path(dest)) if tipo == "csv" else S.exportar_json(Path(dest))
                self._msg(f"Exportadas {cant} sesiones a {dest}")
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Exportar", str(e), parent=self.root)

        def _respaldar(self) -> None:
            dest = filedialog.asksaveasfilename(parent=self.root, defaultextension=".db",
                                                initialfile=f"orientador-{time.strftime('%Y%m%d-%H%M')}.db",
                                                initialdir=str(Path.home()))
            if not dest:
                return
            try:
                S.respaldar_db(Path(dest))
                self._msg(f"Respaldo guardado en {dest}")
            except Exception as e:  # noqa: BLE001
                messagebox.showerror("Respaldo", str(e), parent=self.root)

        def _importar(self) -> None:
            messagebox.showinfo(
                "Importar base", "Para traer las sesiones de Docker, primero copie la base del volumen:\n\n"
                "docker cp fabiola-web:/app/datos/orientador.db ~/orientador.db\n\n"
                "Luego elija ese archivo. La base actual se respalda antes de reemplazarla.", parent=self.root)
            src = filedialog.askopenfilename(parent=self.root, initialdir=str(Path.home()),
                                             filetypes=[("SQLite", "*.db *.sqlite"), ("Todos", "*")])
            if not src:
                return
            if not messagebox.askyesno("Importar base", "Se detendra la web, se reemplazara la base y se volvera "
                                       "a iniciar. Continuar?", parent=self.root):
                return

            def tarea():
                estaba = self.g.vivo("web")
                if estaba:
                    self.g.detener("web")
                resp = S.importar_db(Path(src))
                if estaba:
                    self.g.iniciar("web")
                self.root.after(0, self._cargar_sesiones)
                return "Base importada" + (f" (respaldo anterior: {resp.name})" if resp else "")
            self._job(tarea)

        # ------------------------------------------------------------ configuracion
        def _cargar_cfg(self) -> None:
            S.asegurar_config()
            self.txt_cfg.delete("1.0", "end")
            self.txt_cfg.insert("1.0", S.CONFIG_FILE.read_text(encoding="utf-8"))
            self.txt_cfg.edit_reset()
            self._resaltar_cfg()

        def _resaltar_cfg(self) -> None:
            w = self.txt_cfg
            for tg in ("com", "key", "sec"):
                w.tag_remove(tg, "1.0", "end")
            datos = {}
            for i, linea in enumerate(w.get("1.0", "end-1c").splitlines(), start=1):
                s = linea.lstrip()
                if s.startswith("# ---") or s.startswith("# ==="):
                    w.tag_add("sec", f"{i}.0", f"{i}.end")
                elif s.startswith("#"):
                    w.tag_add("com", f"{i}.0", f"{i}.end")
                elif "=" in s:
                    k = linea.split("=", 1)[0]
                    w.tag_add("key", f"{i}.0", f"{i}.{len(k)}")
                    datos[k.strip()] = linea.split("=", 1)[1].strip().strip("\"'")
            partes = []
            for n in ("web", "orientador", "fabiola", "ngrok"):
                falta = [k for k in S.REQUERIDAS[n] if not datos.get(k)]
                marca = "OK " if not falta else ("-- " if n == "ngrok" else "X  ")
                extra = ""
                if falta:
                    extra = "\n     opcional, sin token" if n == "ngrok" else f"\n     falta: {', '.join(falta)}"
                partes.append(f"{marca} {self.g.servicios[n].titulo}{extra}")
            try:
                p = int(datos.get("MOTIVATE_PORT", "7878"))
                partes.append(f"\nPuerto web: {p}")
            except ValueError:
                partes.append("\nPuerto web invalido")
            self.lbl_val.configure(text="\n".join(partes))

        def _guardar_cfg(self, reiniciar: bool = False) -> None:
            contenido = self.txt_cfg.get("1.0", "end-1c").rstrip() + "\n"
            if S.CONFIG_FILE.exists():
                shutil.copyfile(S.CONFIG_FILE, S.CONFIG_FILE.with_suffix(".env.bak"))
                os.chmod(S.CONFIG_FILE.with_suffix(".env.bak"), 0o600)
            S.CONFIG_FILE.write_text(contenido, encoding="utf-8")
            os.chmod(S.CONFIG_FILE, 0o600)
            self.g.recargar_config()
            self._msg("Configuracion guardada")
            if reiniciar:
                self._job(self._reiniciar_todo)

        # ------------------------------------------------------------ salida
        def _cerrar(self) -> None:
            vivos = [n for n in ORDEN if self.snap.get("svc", {}).get(n, ("off",))[0] in ("ok", "arrancando", "error")
                     and self.snap["svc"][n][2]]
            if vivos and not S.headless_activo():
                r = messagebox.askyesnocancel(
                    "Salir de Motivate",
                    "Hay servicios activos.\n\nSi: detenerlos y salir\nNo: dejarlos corriendo en segundo plano "
                    "(la web sigue en el puerto %d)\nCancelar: volver" % self.g.puerto, parent=self.root)
                if r is None:
                    return
                if r:
                    self._msg("Deteniendo servicios...")
                    self.root.update_idletasks()
                    self.g.detener_todo()
            self.root.destroy()

        def run(self) -> None:
            self.root.mainloop()

    App().run()
    return 0


# ================================================================= CLI
def main() -> int:
    ap = argparse.ArgumentParser(prog="motivate", description="Motivate - app Tk para Rocky Linux")
    ap.add_argument("--headless", action="store_true", help="iniciar servicios sin ventana (systemd)")
    ap.add_argument("--status", action="store_true", help="estado de los servicios")
    ap.add_argument("--start", action="store_true", help="iniciar los servicios en segundo plano y salir")
    ap.add_argument("--stop", action="store_true", help="detener todos los servicios")
    ap.add_argument("--export-csv", metavar="ARCHIVO", help="exportar sesiones a CSV")
    ap.add_argument("--version", action="version", version=f"Motivate {S.VERSION}")
    a = ap.parse_args()

    if a.headless:
        return S.headless()
    if a.export_csv:
        print(f"{S.exportar_csv(Path(a.export_csv))} sesiones exportadas a {a.export_csv}")
        return 0
    if a.status or a.start or a.stop:
        g = S.Gestor()
        if a.stop:
            for m in g.detener_todo():
                print(m)
        if a.start:
            for m in g.iniciar_todo():
                print(m)
            time.sleep(3)
        for n in ORDEN:
            cod, txt = g.estado(n)
            print(f"  {g.servicios[n].titulo:<28} {cod:<11} {txt}")
        print(f"\n  Web: http://{S.ips_locales()[0]}:{g.puerto}/")
        return 0
    return gui()


if __name__ == "__main__":
    sys.exit(main())
