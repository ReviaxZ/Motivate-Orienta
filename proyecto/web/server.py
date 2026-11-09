"""
Servidor web (puerto 7878, se expone con ngrok).

- /              Lucía, orientadora vocacional por voz (página principal).
- /fabiola/      Página de Fabiola (agente de cobros).
- /panel/        Panel del psicólogo con filtros (usuario y contraseña).
- /api/...       Tokens de LiveKit y API del orientador.
- /internal/...  API que usa el agente orientador desde la red de Docker.
"""

import logging
import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from livekit import api  # noqa: E402

import db  # noqa: E402
import orientador_api  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
AGENT_NAME = os.getenv("AGENT_NAME", "fabiola")
ROOM_PREFIX = os.getenv("ROOM_PREFIX", "fabiola-web")

STATIC_DIR = Path(__file__).parent / "static"

db.init()
app = FastAPI(title="Motivate Web", docs_url=None, redoc_url=None)
app.include_router(orientador_api.publico)
app.include_router(orientador_api.interno)
app.include_router(orientador_api.panel)


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ----------------------------- Fabiola -----------------------------
@app.post("/api/token")
def create_token():
    if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        raise HTTPException(500, "Faltan LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET")
    room_name = f"{ROOM_PREFIX}-{secrets.token_hex(4)}"
    identity = f"cliente-{secrets.token_hex(3)}"
    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name("Cliente web")
        .with_ttl(timedelta(minutes=30))
        .with_grants(api.VideoGrants(room_join=True, room=room_name, can_publish=True, can_subscribe=True, can_publish_data=True))
        .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name=AGENT_NAME)]))
        .to_jwt()
    )
    return {"serverUrl": LIVEKIT_URL, "token": token, "room": room_name, "identity": identity}


# ----------------------------- Páginas -----------------------------
@app.get("/")
def index():
    # Página principal: Lucía, la orientadora vocacional
    return FileResponse(STATIC_DIR / "orientador" / "index.html")


@app.get("/orientador")
@app.get("/orientador/")
def orientador_alias():
    return RedirectResponse("/")


@app.get("/fabiola")
def fabiola_redirect():
    return RedirectResponse("/fabiola/")


@app.get("/fabiola/")
def fabiola_page():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/panel")
def panel_redirect():
    return RedirectResponse("/panel/")


@app.get("/panel/", dependencies=[Depends(orientador_api._auth_panel)])
def panel_page():
    return FileResponse(STATIC_DIR / "panel" / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7878")), proxy_headers=True, forwarded_allow_ips="*")
