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

# TTL da chave de estado pendente (10 minutos)
PENDING_CPF_TTL = 600

SAUDACOES = {"oi", "olá", "ola", "hello", "hi", "hey", "oie", "bom dia", "boa tarde", "boa noite"}
COMANDOS = {"/status", "/ajuda", "/help", "/planos", "/plano", "/starter", "/pro", "/equipe", "/assinar"}

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
    " /assinar starter — plano Starter (R$9/mês)\n"
    " /assinar pro — plano Pro (R$19/mês)\n"
    " /assinar equipe — plano Equipe (R$79/mês)\n\n"
    "_Mande qualquer um desses agora e eu processo na hora._\n\n"
    "https://poda.digital"
)

MENSAGEM_PLANOS = (
    "🌱 *Planos do Poda*\n\n"
    "🆓 *Free — R$0/mês*\n"
    " • 5 URLs por dia\n"
    " • 2 PDFs por dia\n"
    " • Contador de tokens ilimitado\n\n"
    "🌿 *Starter — R$9/mês*\n"
    " • 15 URLs por dia\n"
    " • 8 PDFs por dia\n"
    " • Menos que R$0,30 por dia\n\n"
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
    " /assinar starter\n"
    " /assinar pro\n"
    " /assinar equipe"
)

NOMES_PLANO = {
    "free": "Free 🆓",
    "starter": "Starter 🌿",
    "pro": "Pro ⚡",
    "equipe": "Equipe 👥",
}

PRECOS_PLANO_TXT = {
    "starter": "R$9/mês",
    "pro": "R$19/mês",
    "equipe": "R$79/mês",
}


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
            await metrics.registrar_mensagem_recebida(numero, "saudacao")
            await enviar_texto(numero, MENSAGEM_BOAS_VINDAS)
            return

        # Comandos especiais — têm prioridade sobre estado pendente
        primeiro_token = body_lower.split()[0] if body_lower else ""
        if primeiro_token in COMANDOS:
            await metrics.registrar_mensagem_recebida(numero, "comando")
            # Se o usuário manda /assinar novamente, limpa estado pendente
            if primeiro_token == "/assinar":
                await _limpar_pendente(numero)
            await _processar_comando(numero, primeiro_token, body_lower)
            return

        # Verificar se há estado pendente (aguardando CPF/CNPJ)
        pending = await _get_pendente(numero)
        if pending:
            await _processar_cpf_pendente(numero, body_text, pending)
            return

        # Comando desconhecido começando com "/" → orientar em vez de analisar como texto
        if body_lower.startswith("/"):
            await metrics.registrar_mensagem_recebida(numero, "comando")
            await enviar_texto(
                numero,
                "🤔 *Não reconheci esse comando.*\n\n"
                "Comandos disponíveis:\n"
                " /status — seu uso de hoje\n"
                " /planos — conhecer os planos\n"
                " /assinar starter — plano Starter (R$9/mês)\n"
                " /assinar pro — plano Pro (R$19/mês)\n"
                " /assinar equipe — plano Equipe (R$79/mês)\n"
                " /ajuda — tudo que eu faço",
            )
            return

        tipo = detectar_tipo(message)
        logger.info(f"Mensagem de {numero}: tipo={tipo}")

        if tipo == ContentType.URL:
            await metrics.registrar_mensagem_recebida(numero, "url")
            url = extrair_url(body_text)
            if url:
                if not await rate_limiter.pode_processar_url(numero):
                    await enviar_texto(numero, await _msg_limite("url", numero))
                    return
                await rate_limiter.registrar_url(numero)
                await enviar_texto(numero, "⏳ _Processando o link..._")
                await url_handler.processar_url(numero, url)
                await _avisar_quase_limite(numero, "url")
                await _avisar_renovacao(numero)

        elif tipo == ContentType.PDF:
            await metrics.registrar_mensagem_recebida(numero, "pdf")
            media_id = message.get("document", {}).get("id")
            if media_id:
                if not await rate_limiter.pode_processar_pdf(numero):
                    await enviar_texto(numero, await _msg_limite("pdf", numero))
                    return
                await rate_limiter.registrar_pdf(numero)
                await enviar_texto(numero, "⏳ _Convertendo o PDF..._")
                await pdf_handler.processar_pdf(numero, media_id)
                await _avisar_quase_limite(numero, "pdf")
                await _avisar_renovacao(numero)

        elif tipo == ContentType.TEXT:
            if body_text.strip():
                await metrics.registrar_mensagem_recebida(numero, "texto")
                await token_handler.processar_texto(numero, body_text)
        else:
            await metrics.registrar_mensagem_recebida(numero, "invalido")
            await enviar_texto(numero, formatar_nao_suportado())

    else:
        tipo = detectar_tipo(message)
        if tipo == ContentType.PDF:
            await metrics.registrar_mensagem_recebida(numero, "pdf")
            media_id = message.get("document", {}).get("id")
            if media_id:
                if not await rate_limiter.pode_processar_pdf(numero):
                    await enviar_texto(numero, await _msg_limite("pdf", numero))
                    return
                await rate_limiter.registrar_pdf(numero)
                await enviar_texto(numero, "⏳ _Convertendo o PDF..._")
                await pdf_handler.processar_pdf(numero, media_id)
                await _avisar_quase_limite(numero, "pdf")
                await _avisar_renovacao(numero)
        elif tipo == ContentType.UNSUPPORTED:
            raw_type = message.get("type", "")
            resposta = formatar_nao_suportado(raw_type)
            await metrics.registrar_mensagem_recebida(numero, "invalido")
            if resposta:
                await enviar_texto(numero, resposta)
        else:
            await enviar_texto(numero, formatar_nao_suportado())



async def _msg_limite(tipo: str, numero: str) -> str:
    """Mensagem de limite diário atingido, com CTA de upgrade escalonado por plano."""
    plano = await rate_limiter.get_plano(numero)
    recurso = "URLs" if tipo == "url" else "PDFs"
    msg = (
        f"⚠️ *Limite diário de {recurso} atingido.*\n"
        "_Renova automaticamente à meia-noite (horário de Brasília)._"
    )
    if plano == "free":
        prox = "15 URLs + 8 PDFs" if tipo == "url" else "8 PDFs + 15 URLs"
        msg += (
            f"\n\n👉 Continue agora mesmo com o Starter (R$9/mês — {prox}/dia):\n"
            "*/assinar starter*\n\n"
            "Ou vá direto ao Pro (R$19/mês — 50 URLs + 20 PDFs/dia):\n"
            "*/assinar pro*"
        )
    elif plano == "starter":
        msg += (
            "\n\n👉 Precisa de mais? O Pro libera 50 URLs + 20 PDFs/dia:\n"
            "*/assinar pro*"
        )
    elif plano == "pro":
        msg += (
            "\n\n👉 O plano Equipe tem uso ilimitado:\n"
            "*/assinar equipe*"
        )
    return msg


async def _avisar_quase_limite(numero: str, tipo: str) -> None:
    """
    Avisa o usuário free quando resta apenas 1 uso do dia.
    Converter ANTES do bloqueio funciona melhor que bloquear de surpresa.
    """
    try:
        plano = await rate_limiter.get_plano(numero)
        if plano != "free":
            return
        if tipo == "url":
            restantes = await rate_limiter.urls_restantes(numero)
            recurso = "URL grátis restante"
        else:
            restantes = await rate_limiter.pdfs_restantes(numero)
            recurso = "PDF grátis restante"
        if restantes == 1:
            await enviar_texto(
                numero,
                f"ℹ️ _Você tem só 1 {recurso} hoje._\n\n"
                "🌿 O Starter (R$9/mês) libera 15 URLs + 8 PDFs por dia:\n"
                "*/assinar starter*",
            )
    except Exception as e:
        logger.warning(f"Erro em _avisar_quase_limite para {numero}: {e}")


async def _avisar_renovacao(numero: str) -> None:
    """
    Aviso proativo de expiração: se o plano pago expira em até 3 dias,
    envia no máximo 1 lembrete por dia (deduplicado via Redis).
    """
    try:
        plano = await rate_limiter.get_plano(numero)
        if plano == "free":
            return
        ttl = await rate_limiter.get_plano_expiracao(numero)
        if ttl <= 0 or ttl > 3 * 86400:
            return
        chave = f"poda:aviso_renovacao:{numero}"
        if await rate_limiter.redis.get(chave):
            return
        await rate_limiter.redis.setex(chave, 86400, "1")
        dias = max(1, (ttl + 86399) // 86400)
        plural = "dia" if dias == 1 else "dias"
        preco = PRECOS_PLANO_TXT.get(plano, "")
        await enviar_texto(
            numero,
            f"⏳ *Seu plano {NOMES_PLANO.get(plano, plano)} expira em {dias} {plural}.*\n\n"
            f"Renove agora e os dias restantes são somados ao novo período ({preco}):\n"
            f"*/assinar {plano}*",
        )
    except Exception as e:
        logger.warning(f"Erro em _avisar_renovacao para {numero}: {e}")


# ─── Helpers de estado pendente (Redis) ──────────────────────────────────────

async def _get_pendente(numero: str) -> str:
    """Retorna o plano pendente para o número, ou '' se não houver."""
    try:
        val = await rate_limiter.redis.get(f"pending_cpf:{numero}")
        return val if val else ""
    except Exception:
        return ""


async def _limpar_pendente(numero: str) -> None:
    """Remove o estado pendente do número."""
    try:
        await rate_limiter.redis.delete(f"pending_cpf:{numero}")
    except Exception:
        pass


# ─── Handlers de comando ──────────────────────────────────────────────────────

async def _processar_comando(numero: str, comando: str, texto_completo: str = "") -> None:
    """Processa comandos especiais do bot."""
    if comando == "/status":
        status = await rate_limiter.status_usuario(numero)
        plano = status.get("plano", "free")
        nome_plano = NOMES_PLANO.get(plano, plano.capitalize())

        urls_limite = status.get("urls_limite") or "∞"
        pdfs_limite = status.get("pdfs_limite") or "∞"
        urls_restantes = status.get("urls_restantes") or "∞"
        pdfs_restantes = status.get("pdfs_restantes") or "∞"

        mensagem = (
            f"📊 *Seu uso hoje ({status['data']})*\n\n"
            f"🏷️ Plano: *{nome_plano}*\n"
        )

        # Dias restantes do plano pago + CTA de renovação
        dias_restantes = status.get("dias_restantes", 0)
        if plano != "free":
            mensagem += f"⏳ Validade: *{dias_restantes} dia(s) restantes*\n"
            if dias_restantes <= 5:
                mensagem += (
                    f"   _Renove com /assinar {plano} — os dias restantes são somados._\n"
                )
        mensagem += "\n"

        mensagem += (
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
                "👉 Assine via PIX: */assinar starter* (R$9) ou */assinar pro* (R$19)"
            )
        else:
            mensagem += "_Contador de tokens é sempre gratuito e ilimitado._"
        await enviar_texto(numero, mensagem)

    elif comando in {"/ajuda", "/help"}:
        await enviar_texto(numero, MENSAGEM_BOAS_VINDAS)

    elif comando in {"/planos", "/plano"}:
        await enviar_texto(numero, MENSAGEM_PLANOS)

    elif comando in {"/starter", "/pro", "/equipe"}:
        # Atalho direto: /starter equivale a /assinar starter
        await _processar_assinatura(numero, comando[1:])

    elif comando == "/assinar":
        tokens = texto_completo.split()
        plano = tokens[1] if len(tokens) > 1 else ""
        await _processar_assinatura(numero, plano)


async def _processar_assinatura(numero: str, plano: str) -> None:
    """Inicia o fluxo de assinatura: valida plano e solicita CPF/CNPJ."""
    plano = plano.lower().strip()

    if plano not in ("starter", "pro", "equipe"):
        await enviar_texto(
            numero,
            "💳 *Assinar o Poda via PIX*\n\n"
            "Escolha seu plano:\n\n"
            "🌿 */assinar starter* — R$9/mês\n"
            " • 15 URLs + 8 PDFs por dia\n\n"
            "⚡ */assinar pro* — R$19/mês\n"
            " • 50 URLs + 20 PDFs por dia\n\n"
            "👥 */assinar equipe* — R$79/mês\n"
            " • Uso ilimitado\n\n"
            "_Pagamento via PIX. Ativação instantânea após confirmação._",
        )
        return

    # Salvar plano no Redis e pedir CPF/CNPJ
    try:
        await rate_limiter.redis.setex(f"pending_cpf:{numero}", PENDING_CPF_TTL, plano)
    except Exception as e:
        logger.error(f"Erro ao salvar estado pendente para {numero}: {e}")

    nome_plano = f"{NOMES_PLANO.get(plano, plano.title())} ({PRECOS_PLANO_TXT.get(plano, '')})"
    await enviar_texto(
        numero,
        f"💳 *Plano {nome_plano}*\n\n"
        "Para gerar o PIX, preciso do seu *CPF ou CNPJ*.\n\n"
        "_Digite apenas os números (sem pontos ou traços):_",
    )


async def _processar_cpf_pendente(numero: str, texto: str, plano: str) -> None:
    """Valida CPF/CNPJ recebido e gera a cobrança PIX."""
    cpf_cnpj = "".join(c for c in texto if c.isdigit())

    if len(cpf_cnpj) not in (11, 14):
        await enviar_texto(
            numero,
            "❌ CPF ou CNPJ inválido.\n\n"
            "Por favor, envie *apenas os números*:\n"
            " • CPF: 11 dígitos\n"
            " • CNPJ: 14 dígitos\n\n"
            "_Ou envie /assinar para recomeçar._",
        )
        return

    # Limpar estado pendente antes de processar
    await _limpar_pendente(numero)

    await enviar_texto(numero, "⏳ _Gerando cobrança PIX..._")

    try:
        from services.pagamento import criar_cobranca_pix
        resultado = await criar_cobranca_pix(numero, plano, cpf_cnpj)
    except Exception as e:
        logger.error(f"Erro ao criar cobrança PIX para {numero}: {e}", exc_info=True)
        await enviar_texto(
            numero,
            "❌ Erro ao gerar cobrança. Tente novamente: */assinar "
            + plano
            + "*",
        )
        return

    if not resultado or not resultado.get("pix_copia_cola"):
        await enviar_texto(
            numero,
            "❌ Não foi possível gerar o PIX agora. Tente: */assinar " + plano + "*",
        )
        return

    nome_plano = NOMES_PLANO.get(plano, plano.title())
    preco = resultado.get("preco", 0)
    pix = resultado.get("pix_copia_cola", "")
    payment_id = resultado.get("payment_id", "")

    mensagem = (
        f"💳 *PIX — Plano {nome_plano}*\n\n"
        f"Valor: *R${float(preco):.2f}*\n"
        f"Validade: 24 horas\n\n"
        f"Copie o código PIX abaixo e pague no seu banco:\n\n"
        f"```\n{pix}\n```\n\n"
        f"✅ Após o pagamento, seu plano é ativado automaticamente.\n"
        f"_ID: {payment_id}_"
    )
    await enviar_texto(numero, mensagem)
