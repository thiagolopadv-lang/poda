"""
whatsapp.py — Webhook da Meta WhatsApp Cloud API
Recebe todas as mensagens, detecta o tipo e roteia para o handler correto.
"""

import logging

from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import JSONResponse

from utils.detector import detectar_tipo, extrair_url, ContentType
from utils.formatter import formatar_nao_suportado
from services.whatsapp_api import enviar_texto, marcar_como_lida
from services.rate_limiter import rate_limiter
from routes import url_handler, pdf_handler, token_handler

logger = logging.getLogger("poda.whatsapp")

router = APIRouter()

# Saudações → mensagem de boas-vindas
SAUDACOES = {"oi", "olá", "ola", "hello", "hi", "hey", "oie", "bom dia", "boa tarde", "boa noite"}

# Comandos especiais
COMANDOS = {"/status", "/ajuda", "/help", "/planos", "/plano", "/pro"}

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
    "💡 *Comandos úteis:*\n"
    "   /status — ver seu uso de hoje\n"
    "   /planos — conhecer os planos\n\n"
    "_Mande qualquer um desses agora e eu processo na hora._"
)

MENSAGEM_PLANOS = (
    "🌱 *Planos do Poda*\n\n"
    "🆓 *Free — R$0/mês*\n"
    "   • 5 URLs por dia\n"
    "   • 2 PDFs por dia\n"
    "   • Contador de tokens ilimitado\n\n"
    "⚡ *Pro — R$19/mês*\n"
    "   • 50 URLs por dia\n"
    "   • 20 PDFs por dia\n"
    "   • Sem branding nas respostas\n"
    "   • Fallback Firecrawl ativado\n\n"
    "👥 *Equipe — R$79/mês*\n"
    "   • Uso ilimitado\n"
    "   • Até 5 usuários\n"
    "   • Webhook/API disponível\n\n"
    "👉 Assinar: poda.io/pro"
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

    if msg_type == "text":
        body_text = message.get("text", {}).get("body", "").strip()
        body_lower = body_text.lower()

        # Saudação → boas-vindas
        if body_lower in SAUDACOES or len(body_lower) <= 3:
            await enviar_texto(numero, MENSAGEM_BOAS_VINDAS)
            return

        # Comandos especiais
        primeiro_token = body_lower.split()[0] if body_lower else ""
        if primeiro_token in COMANDOS:
            await _processar_comando(numero, primeiro_token)
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

    elif tipo == ContentType.UNSUPPORTED:
        raw_type = message.get("type", "")
        resposta = formatar_nao_suportado(raw_type)
        if resposta:  # Reações retornam string vazia — não responder
            await enviar_texto(numero, resposta)

    else:
        await enviar_texto(numero, formatar_nao_suportado())


async def _processar_comando(numero: str, comando: str) -> None:
    """Processa comandos especiais do bot."""
    if comando == "/status":
        status = rate_limiter.status_usuario(numero)
        mensagem = (
            f"📊 *Seu uso hoje ({status['data']})*\n\n"
            f"🔗 URLs: {status['urls_usadas']}/{status['urls_limite']} usadas"
            f" — {status['urls_restantes']} restantes\n"
            f"📄 PDFs: {status['pdfs_usados']}/{status['pdfs_limite']} usados"
            f" — {status['pdfs_restantes']} restantes\n"
            f"📝 Contador de tokens: ∞ (ilimitado)\n\n"
        )
        if status["urls_restantes"] == 0 or status["pdfs_restantes"] == 0:
            mensagem += (
                "⚠️ _Algum limite foi atingido hoje._\n"
                "Limite reseta à meia-noite (horário de Brasília).\n\n"
                "👉 Plano Pro (R$19/mês): poda.io/pro"
            )
        else:
            mensagem += "_Contador de tokens é sempre gratuito e ilimitado._"
        await enviar_texto(numero, mensagem)

    elif comando in {"/ajuda", "/help"}:
        await enviar_texto(numero, MENSAGEM_BOAS_VINDAS)

    elif comando in {"/planos", "/plano", "/pro"}:
        await enviar_texto(numero, MENSAGEM_PLANOS)
