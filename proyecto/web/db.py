"""Persistencia en SQLite. Cada entrevista es un documento JSON más columnas indexables para el panel."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).parent / "datos" / "orientador.db"))
_lock = threading.Lock()

COLUMNAS = [
    "pais", "departamento", "municipio", "colonia", "zona", "nivel_economico", "carrera_top",
    "carrera_elegida", "alerta_bienestar", "estado", "nombre", "correo", "cita_estado", "correo_estado",
    "modo", "dictamen", "idioma",
]


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, _conn() as c:
        cols = ", ".join(f"{k} TEXT" for k in COLUMNAS)
        c.execute(f"CREATE TABLE IF NOT EXISTS entrevistas (id TEXT PRIMARY KEY, creada TEXT, actualizada TEXT, {cols}, doc TEXT)")
        # Migración: columnas nuevas en bases existentes
        existentes = {r[1] for r in c.execute("PRAGMA table_info(entrevistas)")}
        for k in COLUMNAS:
            if k not in existentes:
                c.execute(f"ALTER TABLE entrevistas ADD COLUMN {k} TEXT")
        c.execute("CREATE TABLE IF NOT EXISTS geocache (q TEXT PRIMARY KEY, doc TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS videos (carrera TEXT PRIMARY KEY, doc TEXT, creado TEXT)")


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _columnas(doc: dict) -> dict:
    u = doc.get("ubicacion") or {}
    r = doc.get("respuestas") or {}
    res = doc.get("resultado") or {}
    top = (res.get("carreras") or [{}])[0].get("id") if res.get("carreras") else None
    caso = doc.get("caso") or {}
    if doc.get("modo") == "permanencia":
        top = caso.get("carrera_id") or caso.get("carrera_nombre")
    return {
        "pais": u.get("pais"), "departamento": u.get("departamento"), "municipio": u.get("municipio"),
        "colonia": u.get("colonia"), "zona": u.get("zona"),
        "nivel_economico": (r.get("economia") or {}).get("nivel"),
        "carrera_top": top, "carrera_elegida": doc.get("carrera_elegida"),
        "alerta_bienestar": "si" if ((r.get("extra") or {}).get("alerta_bienestar") or caso.get("alerta_bienestar")) else "no",
        "estado": doc.get("estado"), "nombre": (doc.get("estudiante") or {}).get("nombre"),
        "correo": (doc.get("estudiante") or {}).get("correo"),
        "cita_estado": (doc.get("cita") or {}).get("estado"),
        "correo_estado": (doc.get("correo_psicologo") or {}).get("estado"),
        "modo": doc.get("modo") or "eleccion",
        "dictamen": (doc.get("dictamen") or {}).get("decision"),
        "idioma": doc.get("idioma") or "es",
    }


def crear(id: str) -> dict:
    doc = {"id": id, "creada": ahora(), "estado": "en_curso", "respuestas": {}, "ubicacion": None, "resultado": None,
           "enfoque": None, "calificaciones": {}, "carrera_elegida": None, "estudiante": {}, "ui": {}, "version": 0}
    guardar(doc)
    return doc


def guardar(doc: dict) -> dict:
    doc["actualizada"] = ahora()
    doc["version"] = int(doc.get("version", 0)) + 1
    cols = _columnas(doc)
    with _lock, _conn() as c:
        keys = ", ".join(COLUMNAS)
        qs = ", ".join("?" for _ in COLUMNAS)
        upd = ", ".join(f"{k}=excluded.{k}" for k in COLUMNAS)
        c.execute(
            f"INSERT INTO entrevistas (id, creada, actualizada, {keys}, doc) VALUES (?, ?, ?, {qs}, ?) "
            f"ON CONFLICT(id) DO UPDATE SET actualizada=excluded.actualizada, {upd}, doc=excluded.doc",
            [doc["id"], doc["creada"], doc["actualizada"], *[cols[k] for k in COLUMNAS], json.dumps(doc, ensure_ascii=False)],
        )
    return doc


def obtener(id: str) -> dict | None:
    with _lock, _conn() as c:
        row = c.execute("SELECT doc FROM entrevistas WHERE id=?", [id]).fetchone()
    return json.loads(row["doc"]) if row else None


def listar(filtros: dict, limite: int = 500) -> list[dict]:
    where, args = [], []
    for k in ("departamento", "nivel_economico", "zona", "alerta_bienestar", "estado", "carrera_top", "carrera_elegida", "pais", "modo", "dictamen"):
        v = filtros.get(k)
        if v:
            where.append(f"{k} = ?")
            args.append(v)
    q = filtros.get("q")
    if q:
        where.append("(nombre LIKE ? OR municipio LIKE ? OR colonia LIKE ? OR correo LIKE ?)")
        args += [f"%{q}%"] * 4
    sql = "SELECT id, creada, actualizada, " + ", ".join(COLUMNAS) + " FROM entrevistas"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY creada DESC LIMIT ?"
    args.append(limite)
    with _lock, _conn() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def valores_distintos(col: str) -> list[str]:
    assert col in COLUMNAS
    with _lock, _conn() as c:
        return [r[0] for r in c.execute(f"SELECT DISTINCT {col} FROM entrevistas WHERE {col} IS NOT NULL ORDER BY 1")]


def geocache_get(q: str):
    with _lock, _conn() as c:
        row = c.execute("SELECT doc FROM geocache WHERE q=?", [q.lower()]).fetchone()
    return json.loads(row["doc"]) if row else None


def geocache_set(q: str, doc):
    with _lock, _conn() as c:
        c.execute("INSERT OR REPLACE INTO geocache (q, doc) VALUES (?, ?)", [q.lower(), json.dumps(doc)])


def video_get(carrera: str):
    with _lock, _conn() as c:
        row = c.execute("SELECT doc FROM videos WHERE carrera=?", [carrera]).fetchone()
    return json.loads(row["doc"]) if row else None


def video_set(carrera: str, doc):
    with _lock, _conn() as c:
        c.execute("INSERT OR REPLACE INTO videos (carrera, doc, creado) VALUES (?, ?, ?)", [carrera, json.dumps(doc), ahora()])
