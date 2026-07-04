"""
PODA - Otimizador de Tokens via WhatsApp
main.py - Ponto de entrada da aplicacao FastAPI
v 2.0 - Pagamentos PIX adicionados
"""

import logging
import os
from contextlib import asynccontextmanager

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from routes.whatsapp import router as whatsapp_router
from routes.dashboard import router as dashboard_router
from routes.pagamento import router as pagamento_router
from config import settings

# ----------------------------------------------------------------------------
# Logging estruturado em JSON
# ----------------------------------------------------------------------------

def _configurar_logging() -> None:
    """Configura logging em formato JSON para facilitar analise no Railway/Sentry."""
    try:
        from pythonjsonlogger import jsonlogger  # type: ignore

        handler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"asctime": "timestamp", "levelname": "level"},
        )
        handler.setFormatter(formatter)

        root = logging.getLogger()
        root.handlers.clear()
        root.addHandler(handler)
        root.setLevel(logging.INFO)

    except ImportError:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s>",
        )

_configurar_logging()
logger = logging.getLogger("poda")

# ----------------------------------------------------------------------------
# Sentry
# ----------------------------------------------------------------------------

_sentry_dsn = os.getenv("SENTRY_DSN", "")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        integrations=[
            FastApiIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
    )
    logger.info("Sentry inicializado.", extra={"dsn_configurado": True})
else:
    logger.warning(
        "SENTRY_DSN nao configurado - monitoramento de erros desativado.",
        extra={"dsn_configurado": False},
    )

# ----------------------------------------------------------------------------
# Lifecycle
# ----------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Poda iniciando...", extra={"servico": "poda", "fase": "startup"})
    yield
    logger.info("Poda encerrando.", extra={"servico": "poda", "fase": "shutdown"})

# ----------------------------------------------------------------------------
# App
# ----------------------------------------------------------------------------

app = FastAPI(
    title="Poda",
    description="Otimizador de tokens via WhatsApp",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(whatsapp_router)
app.include_router(dashboard_router)
app.include_router(pagamento_router)

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0"}

@app.get("/")
async def webhook_verificacao(request: Request):
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verificado com sucesso pela Meta.", extra={"modo": mode})
        return PlainTextResponse(content=challenge)

    logger.warning("Falha na verificacao do webhook.", extra={"modo": mode})
    return PlainTextResponse(content="Forbidden", status_code=403)
