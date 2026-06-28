"""
whatsapp.py — Webhook da Meta WhatsApp Cloud API
Recebe todas as mensagens, detecta o tipo e roteia para o handler correto.
"""

import logging
import asyncio

from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse

from utils.detector import detectar_tipo, extrair_url, ContentType
from utils.formatter import formatar_nao_suportado
from services.whatsapp_api import enviar_texto, marcar_como_lida
from routes import url_handler, pdf_handler, token_handler

logger = logging.getLogger("poda.whatsapp")

router = APIRouter()

# Mensagem de boas-vindas (enviada na primeira interação ou quando o usuário envia "oi", "ola", etc.)
SAUDACOES = {"oi", "olá", "ola", "hello", "hi", "hey", "oie", "bom dia", "boa tarde", "boa noite"}

MENSAGEM_BOAS_VINDAS = (
    "🌱 *Olá! Eu sou o Poda.*\n\n"
    "Converto qualquer conteúdo em texto limpo e eficiente para usar no ChatGPT, Claude ou Gemini.\n\n"
    "O que você pode me enviar:\n\n"
    "🔗 *Link* — qualquer URL de página web\n"
    "   → Receba o conteúdo em Markdown limpo (menos 80% de tokens)\n\n"
    "📄 *PDF* — qualquer arquivo PDF\n"
    "   → Receba o documento estruturado em Markdown\n\n"
    "📝 *Texto* — qualquer texto\n"
    "   → Veja a contagem de tokens e o custo por modelo de IA\n\n"
    "_Mande qualquer um desses agora e eu processo na hora._"
)


@router.post("/webhook")
async def webhook_receber(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint principal: recebe todos os eventos do WhatsApp.
    Responde 200 imediatamente e processa em background.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON"})

    # Processar em background para responder < 1s à Meta
    background_tasks.add_task(_processar_evento, body)

    return JSONResponse(status_code=200, content={"status": "ok"})


async def _processar_evento(body: dict) -> None:
    """Processa o evento do webhook de forma assíncrona."""
    try:
        entry = body.get("entry", [])
        if not entry:
            return

        for item in entry:
            changes = item.get("changes", [])
            for change in changes:
                value = change.get("value", {})
                mensagens = value.get("messages", [])

                for msg in mensagens:
                    numero = msg.get("from")
                    message_id = msg.get("id")

                    if not numero:
                        continue

                    # Marcar como lida (feedback visual para o usuário)
                    await marcar_como_lida(numero, message_id)

                    await _rotear_mensagem(numero, msg)

    except Exception as e:
        logger.error(f"Erro ao processar evento do webhook: {e}", exc_info=True)


async def _rotear_mensagem(numero: str, message: dict) -> None:
    """Detecta o tipo de conteúdo e roteia para o handler correto."""
    msg_type = message.get("type", "")

    # Saudação → mensagem de boas-vindas
    if msg_type == "text":
        body_text = message.get("text", {}).get("body", "").strip().lower()
        if body_text in SAUDACOES or len(body_text) <= 3:
            await enviar_texto(numero, MENSAGEM_BOAS_VINDAS)
            return

    tipo = detectar_tipo(message)
    logger.info(f"Mensagem de {numero}: tipo={tipo}")

    if tipo == ContentType.URL:
        body_text = message.get("text", {}).get("body", "")
        url = extrair_url(body_text)
        if url:
            await enviar_texto(numero, "⏳ _Processando o link..._")
            await url_handler.processar_url(numero, url)

    elif tipo == ContentType.PDF:
        media_id = message.get("document", {}).get("id")
        if media_id:
            await enviar_texto(numero, "⏳ _Convertendo o PDF..._")
            await pdf_handler.processar_pdf(numero, media_id)

    elif tipo == ContentType.TEXT:
        body_text = message.get("text", {}).get("body", "")
        if body_text.strip():
            await token_handler.processar_texto(numero, body_text)
        else:
            await enviar_texto(numero, formatar_nao_suportado())

    else:
        await enviar_texto(numero, formatar_nao_suportado())
