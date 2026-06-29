"""
url_handler.py — Processa URLs enviadas pelo usuário
Fluxo: verificar limite → Jina Reader → fallback Firecrawl → erro
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
    Orquestra a conversão de URL para Markdown e envia o resultado ao usuário.
    """
    # --- Verificar limite diário (plano free) ---
    if not rate_limiter.pode_processar_url(numero):
        await enviar_texto(
            numero,
            formatar_limite_atingido(
                tipo="conversões de URL",
                limite=settings.FREE_URL_LIMIT_PER_DAY,
            ),
        )
        return

    markdown = None

    # --- Tentativa 1: Jina Reader ---
    try:
        markdown = await jina.url_para_markdown(url)
    except Exception as e:
        logger.warning(f"Jina Reader falhou para {url}: {e}")

    # --- Tentativa 2: Firecrawl ---
    if not markdown:
        try:
            markdown = await firecrawl.url_para_markdown(url)
        except Exception as e:
            logger.warning(f"Firecrawl falhou para {url}: {e}")

    # --- Falha total ---
    if not markdown:
        await enviar_texto(
            numero,
            formatar_erro(
                "Esta página pode estar protegida por login, "
                "carregar conteúdo via JavaScript sem fallback disponível, "
                "ou estar temporariamente indisponível."
            ),
        )
        return

    # --- Registrar uso (só após processamento bem-sucedido) ---
    rate_limiter.registrar_url(numero)
    urls_restantes = rate_limiter.urls_restantes(numero)

    # --- Calcular métricas de compressão ---
    enc = tiktoken.get_encoding("cl100k_base")
    tokens_depois = len(enc.encode(markdown))

    # Estimar tokens de HTML bruto: média de 5x o Markdown (heurística conservadora)
    tokens_antes = tokens_depois * 5

    # Custo economizado: tokens_antes - tokens_depois em GPT-4o (input: $2.50/1M tokens)
    tokens_economizados = tokens_antes - tokens_depois
    custo_economizado_usd = (tokens_economizados / 1_000_000) * 2.50
    custo_economizado_brl = custo_economizado_usd * settings.USD_TO_BRL

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
