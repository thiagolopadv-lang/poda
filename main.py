"""
PODA - Otimizador de Tokens via WhatsApp
main.py - Ponto de entrada da aplicacao FastAPI
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

# Armazena ultimo dado de gravacao/transcricao recebido
last_recording_data: dict = {}

# Armazena ultimo SMS recebido
last_sms_data: dict = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Poda iniciando...")
    yield
    logger.info("Poda encerrando...")

app = FastAPI(
    title="Poda",
    description="Otimizador de Tokens via WhatsApp",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(whatsapp_router)

@app.get("/")
def root():
    return {"status": "ok", "service": "Poda"}

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/twiml-record")
@app.post("/twiml-record")
async def twiml_record(request: Request):
    """TwiML para gravar chamada de verificacao Meta"""
    from fastapi.responses import Response

    def build_twiml(base_url: str) -> str:
        transcribe_cb = f"{base_url}/twiml-record"
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Say language="pt-BR">Aguarde. Gravando o codigo de verificacao.</Say>'
            f'<Record maxLength="60" transcribe="true" transcribeCallback="{transcribe_cb}"/>'
            '</Response>'
        )

    if request.method == "POST":
        form_data = await request.form()
        data = dict(form_data)
        logger.info(f"TWILIO POST DATA keys: {list(data.keys())}")

        # Se tem TranscriptionText ou RecordingUrl: e o callback de transcricao
        if "TranscriptionText" in data or "RecordingUrl" in data:
            global last_recording_data
            last_recording_data = data
            logger.info(f"TRANSCRIPTION CAPTURED: {data.get('TranscriptionText', 'N/A')}")
            return Response(content="OK", media_type="text/plain")

        # Caso contrario: e o webhook de voz inicial do Twilio - retorna TwiML
        base_url = str(request.base_url).rstrip("/")
        logger.info("Voice webhook POST received - returning TwiML")
        return Response(content=build_twiml(base_url), media_type="application/xml")

    # GET: retorna TwiML para gravar a chamada
    base_url = str(request.base_url).rstrip("/")
    return Response(content=build_twiml(base_url), media_type="application/xml")

@app.get("/last-transcription")
def last_transcription():
    """Retorna os ultimos dados de gravacao/transcricao do Twilio"""
    return last_recording_data

@app.post("/sms")
async def sms_webhook(request: Request):
    """Webhook para capturar SMS recebidos pelo Twilio (codigo de verificacao Meta)"""
    from fastapi.responses import Response
    form_data = await request.form()
    data = dict(form_data)
    global last_sms_data
    last_sms_data = data
    body = data.get("Body", "")
    from_number = data.get("From", "")
    logger.info(f"SMS RECEBIDO de {from_number}: {body}")
    # Retorna TwiML vazio (sem resposta automatica)
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type="application/xml"
    )

@app.get("/last-sms")
def last_sms():
    """Retorna o ultimo SMS recebido pelo Twilio"""
    return last_sms_data
