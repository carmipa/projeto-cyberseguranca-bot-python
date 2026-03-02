"""
API para o painel Windows (CyberBot GRC).
Rode na VPS: uvicorn vps_api:app --host 0.0.0.0 --port 8000

Requer: pip install fastapi uvicorn httpx
"""
import json
import logging
import os

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vps_api")

app = FastAPI()

# Caminho do database.json - dentro do Docker usa /app/data (volume compartilhado)
_BASE = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.environ.get("VPS_API_DATA_DIR") or os.path.join(_BASE, "data")
NOME_ARQUIVO_JSON = os.path.join(_DATA_DIR, "database.json")
# Bot URL: no Docker use hostname do serviço; no host use 127.0.0.1
_BOT_HOST = os.environ.get("BOT_HOST", "127.0.0.1")
BOT_TRIGGER_URL = f"http://{_BOT_HOST}:8080/api/trigger_scan"
BOT_SYNC_URL = f"http://{_BOT_HOST}:8080/api/sync_from_discord"


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
            return JSONResponse(
                content={"error": "Arquivo JSON não encontrado", "sent_news": []},
                headers={"Cache-Control": "no-cache, no-store"},
            )
        with open(NOME_ARQUIVO_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(
            content=data,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    except Exception as e:
        logger.exception(str(e))
        return JSONResponse(
            content={"error": str(e), "sent_news": []},
            headers={"Cache-Control": "no-cache, no-store"},
        )


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


@app.post("/clean_test_items")
def clean_test_items():
    """
    Remove itens de teste (Test News CVE-9999, example.com) do database.json.
    Após limpar, chame /sync_from_discord para repopular com dados reais do Discord.
    Proteção: não remove se isso deixaria sent_news vazio (evita apagar dados reais).
    """
    test_patterns = ("test news", "teste", "cve-9999", "example.com")
    try:
        if not os.path.exists(NOME_ARQUIVO_JSON):
            return {"status": "error", "detail": "Arquivo não encontrado"}
        with open(NOME_ARQUIVO_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        sent = data.get("sent_news", [])
        original = len(sent)
        cleaned = [i for i in sent if isinstance(i, dict) and not any(
            p in (i.get("title", "") + i.get("link", "")).lower() for p in test_patterns
        )]
        removed = original - len(cleaned)
        # Proteção: não limpar se há poucos itens e nenhum é de teste (pode ser scan recente)
        if original < 5 and removed == 0:
            return {"status": "ok", "removed": 0, "remaining": original, "skipped": "poucos itens"}
        # Proteção: não esvaziar sent_news (evita apagar dados reais por falso positivo)
        # Exceto quando há poucos itens e todos são de teste - aí permite para poder sync depois
        if removed > 0 and len(cleaned) == 0 and original >= 10:
            logger.warning("clean_test_items: bloqueado - remoção deixaria sent_news vazio")
            return {"status": "ok", "removed": 0, "remaining": original, "skipped": "evitar esvaziar"}
        if removed > 0:
            data["sent_news"] = cleaned
            with open(NOME_ARQUIVO_JSON, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Removidos {removed} itens de teste. Restam {len(cleaned)}.")
        return {"status": "ok", "removed": removed, "remaining": len(cleaned)}
    except Exception as e:
        logger.exception(str(e))
        return {"status": "error", "detail": str(e)}


@app.get("/debug")
def debug():
    """Diagnóstico: caminho do JSON e quantidade de itens."""
    exists = os.path.exists(NOME_ARQUIVO_JSON)
    count = 0
    if exists:
        try:
            with open(NOME_ARQUIVO_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            count = len(data.get("sent_news", []))
        except Exception as e:
            return {"path": NOME_ARQUIVO_JSON, "exists": True, "error": str(e)}
    return {"path": NOME_ARQUIVO_JSON, "exists": exists, "sent_news_count": count}


@app.post("/debug_seed")
def debug_seed():
    """
    Adiciona 1 item de teste ao database.json para verificar se o painel exibe dados.
    Use: curl -X POST http://localhost:8000/debug_seed
    Depois clique em Sincronizar News no painel.
    """
    from datetime import datetime
    try:
        data = {"sent_news": [], "stats": {"total_processed": 0}}
        if os.path.exists(NOME_ARQUIVO_JSON):
            with open(NOME_ARQUIVO_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
        item = {
            "title": "[TESTE] Vulnerabilidade CVE-2024-1234 - Verificação do painel",
            "link": "https://nvd.nist.gov/vuln/detail/CVE-2024-1234",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "description": "Item de diagnóstico. Se você vê isso, o painel está funcionando."
        }
        data.setdefault("sent_news", []).append(item)
        data.setdefault("stats", {})["total_processed"] = data["stats"].get("total_processed", 0) + 1
        with open(NOME_ARQUIVO_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("debug_seed: 1 item de teste adicionado")
        return {"status": "ok", "added": 1, "total": len(data["sent_news"])}
    except Exception as e:
        logger.exception(str(e))
        return {"status": "error", "detail": str(e)}


@app.on_event("startup")
def startup_event():
    logger.info("vps_api iniciada na porta 8000. Rode o bot na porta 8080.")
