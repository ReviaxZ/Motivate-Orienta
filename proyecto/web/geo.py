"""Geocodificación de la ubicación del estudiante (Nominatim / OpenStreetMap) con respaldo local."""

from __future__ import annotations

import logging
import os

import httpx

import db
from motor import GEO, norm

log = logging.getLogger("geo")

PAISES = {
    "honduras": "hn", "guatemala": "gt", "el salvador": "sv", "nicaragua": "ni", "costa rica": "cr",
    "panama": "pa", "mexico": "mx", "belice": "bz", "estados unidos": "us", "espana": "es",
}
NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
USER_AGENT = os.getenv("NOMINATIM_USER_AGENT", "MotivateOrientadorVocacional/1.0")


def _nominatim(q: str, pais: str | None) -> dict | None:
    cached = db.geocache_get(q)
    if cached is not None:
        return cached or None
    params = {"q": q, "format": "jsonv2", "limit": 1, "accept-language": "es"}
    cc = PAISES.get(norm(pais)) if pais else None
    if cc:
        params["countrycodes"] = cc
    try:
        r = httpx.get(NOMINATIM_URL, params=params, headers={"User-Agent": USER_AGENT}, timeout=6)
        r.raise_for_status()
        data = r.json()
        res = {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"]), "display": data[0].get("display_name")} if data else {}
    except Exception as e:  # sin red o servicio caído
        log.warning("Nominatim falló para %r: %s", q, e)
        return None
    db.geocache_set(q, res)
    return res or None


def _depto_local(pais: str | None, depto: str | None) -> tuple[float, float] | None:
    info = GEO.get("Honduras") if norm(pais) in ("honduras", "") else None
    if not info or not depto:
        return None
    for nombre, (lat, lng) in info["departamentos"].items():
        if norm(nombre) == norm(depto) or norm(depto) in norm(nombre):
            return lat, lng
    return None


def geocodificar(pais: str | None, departamento: str | None, municipio: str | None, colonia: str | None) -> dict:
    partes = [p for p in (colonia, municipio, departamento, pais) if p]
    intentos = []
    if colonia and municipio:
        intentos.append(("colonia", ", ".join(p for p in (colonia, municipio, departamento, pais) if p)))
    if municipio:
        intentos.append(("municipio", ", ".join(p for p in (municipio, departamento, pais) if p)))
    if departamento:
        intentos.append(("departamento", ", ".join(p for p in (departamento, pais) if p)))
    for precision, q in intentos:
        r = _nominatim(q, pais)
        if r:
            return {"lat": r["lat"], "lng": r["lng"], "precision": precision, "fuente": "OpenStreetMap", "display": r.get("display")}
    d = _depto_local(pais, departamento)
    if d:
        return {"lat": d[0], "lng": d[1], "precision": "departamento", "fuente": "cabecera departamental (aprox.)", "display": None}
    if norm(pais) in ("honduras", ""):
        c = GEO["Honduras"]["centro"]
        return {"lat": c[0], "lng": c[1], "precision": "pais", "fuente": "centro del país (aprox.)", "display": None}
    return {"lat": None, "lng": None, "precision": "desconocida", "fuente": None, "display": ", ".join(partes)}
