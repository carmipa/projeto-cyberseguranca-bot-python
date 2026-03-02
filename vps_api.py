"""
API para o painel Windows (CyberBot GRC).
Rode na VPS junto com o bot: uvicorn vps_api:app --host 0.0.0.0 --port 8000

Requer: pip install fastapi uvicorn httpx
"""
import json
import logging
import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from utils.storage import p

# Configura logger simples
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vps_api")

app = FastAPI()

NOME_ARQUIVO_JSON = p("database.json")  # data/database.json
BOT_TRIGGER_URL = "http://127.0.0.1:8080/api/trigger_scan"
BOT_SYNC_URL = "http://127.0.0.1:8080/api/sync_from_discord"


@app.middleware("http")
async def log_requests(request: Request, call_next):
    client_ip = request.client.host if request.client else "?"
    logger.info(f"{client_ip} {request.method} {request.url.path}")
    try:
        return await call_next(request)
    except Exception as e:
        logger.exception(str(e))
        raise


@app.get("/data")
def get_security_data():
    """Retorna dados do database.json para o painel Windows."""
    try:
        if not os.path.exists(NOME_ARQUIVO_JSON):
            return {"error": "Arquivo JSON não encontrado", "sent_news": []}
        with open(NOME_ARQUIVO_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        logger.exception(str(e))
        return {"error": str(e), "sent_news": []}


@app.post("/sync_from_discord")
def sync_from_discord():
    """Sincroniza notícias do Discord para database.json."""
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(BOT_SYNC_URL)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "ok":
                return {"status": "ok", "added": data.get("added", 0)}
            return {"status": "error", "detail": data.get("detail", "Erro")}
        return {"status": "error", "detail": f"Bot retornou {resp.status_code}"}
    except httpx.ConnectError:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "Bot não está rodando na porta 8080."},
        )
    except Exception as e:
        logger.exception(str(e))
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})


@app.post("/trigger_scan")
def trigger_scan():
    """Dispara varredura manual no bot."""
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(BOT_TRIGGER_URL)
        if resp.status_code == 200:
            data = resp.json()
            return {"status": "accepted", "detail": data.get("detail", "Solicitação enviada.")}
        return {"status": "accepted", "detail": f"Bot respondeu {resp.status_code}"}
    except httpx.ConnectError:
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "Bot não está rodando na porta 8080."},
        )
    except Exception as e:
        logger.exception(str(e))
        return JSONResponse(status_code=500, content={"status": "error", "detail": str(e)})


@app.on_event("startup")
def startup_event():
    logger.info("vps_api iniciada na porta 8000. Rode o bot na porta 8080.")
