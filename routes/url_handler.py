"""
url_handler.py - Processa URLs enviadas pelo usuario
Fluxo: verificar limite -> Jina Reader -> fallback Firecrawl -> erro
"""

import logging
import tiktoken

from services import jina, firecrawl
from services.rate_limiter import rate_limiter
from services.whatsapp_api import enviar_texto, enviar_arquivo_texto
from utils.formatter import (
    formatar_resultado_url,
    formatar_erro,
    formatar_limite_atingido,
)
from config import settings

logger = logging.getLogger("poda.url_handler")


async def processar_url(numero: str, url: str) -> None:
    """
    Orquestra a conversao de URL para Markdown e envia o resultado ao usuario.
    """
    log_ctx = {"numero": numero, "url": url}

    # --- Verificar limite diario (plano free) ---
    if not await rate_limiter.pode_processar_url(numero):
        logger.info("Limite diario de URLs atingido.", extra=log_ctx)
        plano = await rate_limiter.get_plano(numero)
        limite_real = rate_limiter._limite_url(plano) or settings.FREE_URL_LIMIT_PER_DAY
        await enviar_texto(
            numero,
            formatar_limite_atingido(
                tipo="conversoes de URL",
                limite=limite_real,
            ),
        )
        return

    markdown = None

    # --- Tentativa 1: Jina Reader ---
    try:
        markdown = await jina.url_para_markdown(url)
        if markdown:
            logger.info("Jina Reader bem-sucedido.", extra=log_ctx)
    except Exception as e:
        logger.warning("Jina Reader falhou.", extra={**log_ctx, "erro": str(e)})

    # --- Tentativa 2: Firecrawl ---
    if not markdown:
        try:
            markdown = await firecrawl.url_para_markdown(url)
            if markdown:
                logger.info("Firecrawl bem-sucedido.", extra=log_ctx)
        except Exception as e:
            logger.warning("Firecrawl falhou.", extra={**log_ctx, "erro": str(e)})

    # --- Falha total ---
    if not markdown:
        logger.error("Todas as tentativas de conversao falharam.", extra=log_ctx)
        await enviar_texto(
            numero,
            formatar_erro(
                "Esta pagina pode estar protegida por login, "
                "carregar conteudo via JavaScript sem fallback disponivel, "
                "ou estar temporariamente indisponivel."
            ),
        )
        return

    # --- Registrar uso (so apos processamento bem-sucedido) ---
    await rate_limiter.registrar_url(numero)
    urls_restantes = await rate_limiter.urls_restantes(numero)

    # --- Calcular metricas de compressao ---
    enc = tiktoken.get_encoding("cl100k_base")
    tokens_depois = len(enc.encode(markdown))
    tokens_antes = tokens_depois * 5
    tokens_economizados = tokens_antes - tokens_depois
    custo_economizado_usd = (tokens_economizados / 1_000_000) * 2.50
    custo_economizado_brl = custo_economizado_usd * settings.USD_TO_BRL

    logger.info(
        "URL convertida com sucesso.",
        extra={
            **log_ctx,
            "tokens_entrada": tokens_antes,
            "tokens_saida": tokens_depois,
            "urls_restantes": urls_restantes,
        },
    )

    # --- Formatar e enviar ---
    cabecalho, conteudo_separado = formatar_resultado_url(
        markdown=markdown,
        tokens_antes=tokens_antes,
        tokens_depois=tokens_depois,
        custo_economizado_brl=custo_economizado_brl,
        urls_restantes=urls_restantes,
        limite_diario=settings.FREE_URL_LIMIT_PER_DAY,
    )

    if conteudo_separado is None:
        await enviar_texto(numero, cabecalho)
    else:
        await enviar_texto(numero, cabecalho)
        await enviar_arquivo_texto(numero, conteudo_separado, "resultado.md")
