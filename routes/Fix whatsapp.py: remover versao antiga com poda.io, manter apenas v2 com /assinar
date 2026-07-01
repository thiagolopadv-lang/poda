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
from services import metrics
from routes import url_handler, pdf_handler, token_handler

logger = logging.getLogger("poda.whatsapp")

router = APIRouter()

# Saudações → mensagem de boas-vindas
SAUDACOES = {"oi", "olá", "ola", "hello", "hi", "hey", "oie", "bom dia", "boa tarde", "boa noite"}

# Comandos especiais
COMANDOS = {"/status", "/ajuda", "/help", "/planos", "/plano", "/pro", "/assinar"}

MENSAGEM_BOAS_VINDAS = (
    "🌱 *Olá! Eu sou o Poda.*\n\n"
    "Converto qualquer conteúdo em texto limpo e eficiente para usar no ChatGPT, Claude ou Gemini.\n\n"
    "O que você pode me enviar:\n\n"
    "🔗 *Link* — qualquer URL de página web\n"
    " → Receba o conteúdo em Markdown limpo (menos 80% de tokens)\n\n"
    "📄 *PDF* — qualquer arquivo PDF\n"
    " → Receba o documento estruturado em Markdown\n\n"
    "📝 *Texto* — qualquer texto\n"
    " → Veja a contagem de tokens e o custo por modelo de IA\n\n"
    "💡 *Comandos úteis:*\n"
    " /status — ver seu uso de hoje\n"
    " /planos — conhecer os planos\n"
    " /assinar pro — assinar plano Pro (R$19/mês)\n"
    " /assinar equipe — assinar plano Equipe (R$79/mês)\n\n"
    "_Mande qualquer um desses agora e eu processo na hora._"
)

MENSAGEM_PLANOS = (
    "🌱 *Planos do Poda*\n\n"
    "🆓 *Free — R$0/mês*\n"
    " • 5 URLs por dia\n"
    " • 2 PDFs por dia\n"
    " • Contador de tokens ilimitado\n\n"
    "⚡ *Pro — R$19/mês*\n"
    " • 50 URLs por dia\n"
    " • 20 PDFs por dia\n"
    " • Sem branding nas respostas\n"
    " • Fallback Firecrawl ativado\n\n"
    "👥 *Equipe — R$79/mês*\n"
    " • Uso ilimitado\n"
    " • Até 5 usuários\n"
    " • Webhook/API disponível\n\n"
    "💳 *Pagar via PIX (ativação imediata):*\n"
    " /assinar pro\n"
    " /assinar equipe"
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
            await _processar_comando(numero, primeiro_token, body_lower)
            return

        tipo = detectar_tipo(message)
        logger.info(f"Mensagem de {numero}: tipo={tipo}")

        if tipo == ContentType.URL:
            await metrics.registrar_mensagem_recebida(numero, "url")
            body_text = message.get("text", {}).get("body", "")
            url = extrair_url(body_text)
            if url:
                await enviar_texto(numero, "⏳ _Processando o link..._")
                await url_handler.processar_url(numero, url)

        elif tipo == ContentType.PDF:
            await metrics.registrar_mensagem_recebida(numero, "pdf")
            media_id = message.get("document", {}).get("id")
            if media_id:
                await enviar_texto(numero, "⏳ _Convertendo o PDF..._")
                await pdf_handler.processar_pdf(numero, media_id)

        elif tipo == ContentType.TEXT:
            body_text = message.get("text", {}).get("body", "")
            if body_text.strip():
                await token_handler.processar_texto(numero, body_text)
        else:
            await metrics.registrar_mensagem_recebida(numero, "invalido")
            await enviar_texto(numero, formatar_nao_suportado())

    else:
        tipo = detectar_tipo(message)
        if tipo == ContentType.UNSUPPORTED:
            raw_type = message.get("type", "")
            resposta = formatar_nao_suportado(raw_type)
            await metrics.registrar_mensagem_recebida(numero, "invalido")
            if resposta:  # Reações retornam string vazia — não responder
                await enviar_texto(numero, resposta)
        else:
            await enviar_texto(numero, formatar_nao_suportado())


async def _processar_comando(numero: str, comando: str, texto_completo: str = "") -> None:
    """Processa comandos especiais do bot."""
    if comando == "/status":
        status = await rate_limiter.status_usuario(numero)
        plano = status.get("plano", "free")
        nomes_plano = {"free": "Free 🆓", "pro": "Pro ⚡", "equipe": "Equipe 👥"}
        nome_plano = nomes_plano.get(plano, plano.capitalize())

        urls_limite = status.get("urls_limite") or "∞"
        pdfs_limite = status.get("pdfs_limite") or "∞"
        urls_restantes = status.get("urls_restantes") or "∞"
        pdfs_restantes = status.get("pdfs_restantes") or "∞"

        mensagem = (
            f"📊 *Seu uso hoje ({status['data']})*\n\n"
            f"🏷️ Plano: *{nome_plano}*\n\n"
            f"🔗 URLs: {status['urls_usadas']}/{urls_limite} usadas"
            f" — {urls_restantes} restantes\n"
            f"📄 PDFs: {status['pdfs_usados']}/{pdfs_limite} usados"
            f" — {pdfs_restantes} restantes\n"
            f"📝 Contador de tokens: ∞ (ilimitado)\n\n"
        )
        atingiu_limite = (
            status.get("urls_restantes") == 0 or status.get("pdfs_restantes") == 0
        )
        if plano == "free" and atingiu_limite:
            mensagem += (
                "⚠️ _Algum limite foi atingido hoje._\n"
                "Limite reseta à meia-noite (horário de Brasília).\n\n"
                "👉 Assine via PIX: */assinar pro*"
            )
        else:
            mensagem += "_Contador de tokens é sempre gratuito e ilimitado._"
        await enviar_texto(numero, mensagem)

    elif comando in {"/ajuda", "/help"}:
        await enviar_texto(numero, MENSAGEM_BOAS_VINDAS)

    elif comando in {"/planos", "/plano", "/pro"}:
        await enviar_texto(numero, MENSAGEM_PLANOS)

    elif comando == "/assinar":
        tokens = texto_completo.split()
        plano = tokens[1] if len(tokens) > 1 else ""
        await _processar_assinatura(numero, plano)


async def _processar_assinatura(numero: str, plano: str) -> None:
    """Gera cobrança PIX e envia o código para o usuário."""
    plano = plano.lower().strip()

    if plano not in ("pro", "equipe"):
        await enviar_texto(
            numero,
            "💳 *Assinar o Poda via PIX*\n\n"
            "Escolha seu plano:\n\n"
            "⚡ */assinar pro* — R$19/mês\n"
            " • 50 URLs + 20 PDFs por dia\n\n"
            "👥 */assinar equipe* — R$79/mês\n"
            " • Uso ilimitado\n\n"
            "_Pagamento via PIX. Ativação instantânea após confirmação._",
        )
        return

    await enviar_texto(numero, "⏳ _Gerando cobrança PIX..._")

    try:
        from services.pagamento import criar_cobranca_pix

        resultado = await criar_cobranca_pix(numero, plano)
    except Exception as e:
        logger.error(f"Erro ao criar cobrança PIX para {numero}: {e}", exc_info=True)
        await enviar_texto(
            numero,
            "❌ Erro ao gerar cobrança. Tente novamente em instantes.",
        )
        return

    if not resultado or not resultado.get("pix_copia_cola"):
        await enviar_texto(
            numero,
            "❌ Não foi possível gerar o PIX agora. Tente novamente.",
        )
        return

    nome_plano = "Pro ⚡" if plano == "pro" else "Equipe 👥"
    preco = resultado.get("preco", 0)
    pix = resultado.get("pix_copia_cola", "")
    payment_id = resultado.get("payment_id", "")

    mensagem = (
        f"💳 *PIX — Plano {nome_plano}*\n\n"
        f"Valor: *R${float(preco):.2f}*\n"
        f"Validade: 30 minutos\n\n"
        f"Copie o código PIX abaixo e pague no seu banco:\n\n"
        f"```\n{pix}\n```\n\n"
        f"✅ Após o pagamento, seu plano é ativado automaticamente.\n"
        f"_ID: {payment_id}_"
    )
    await enviar_texto(numero, mensagem)
