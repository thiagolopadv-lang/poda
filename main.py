"""
PODA — Otimizador de Tokens via WhatsApp
main.py — Ponto de entrada da aplicação FastAPI
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from routes.whatsapp import router as whatsapp_router
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("poda")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🌱 Poda iniciando...")
    yield
    logger.info("Poda encerrando.")


app = FastAPI(
    title="Poda",
    description="Otimizador de Tokens via WhatsApp",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(whatsapp_router)


@app.get("/")
async def health():
    return {"status": "ok", "service": "poda"}


@app.get("/webhook")
async def webhook_verify(request: Request):
    """
    Verificação do webhook pela Meta.
    Meta envia: hub.mode, hub.verify_token, hub.challenge
    """
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verificado com sucesso pela Meta.")
        return PlainTextResponse(content=challenge)

    logger.warning("Falha na verificação do webhook. Token inválido.")
    return PlainTextResponse(content="Forbidden", status_code=403)
