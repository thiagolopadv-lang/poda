"""
url_handler.py — Processa URLs enviadas pelo usuário
Fluxo: Jina Reader → fallback Firecrawl → erro
"""

import logging
import tiktoken

from services import jina, firecrawl
from services.whatsapp_api import enviar_texto, enviar_arquivo_texto
from utils.formatter import (
    formatar_resultado_url,
    formatar_erro,
)
from config import settings

logger = logging.getLogger("poda.url_handler")


async def processar_url(numero: str, url: str) -> None:
    """
    Orquestra a conversão de URL para Markdown e envia o resultado ao usuário.
    """
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

    # --- Calcular métricas de compressão ---
    enc = tiktoken.get_encoding("cl100k_base")
    tokens_depois = len(enc.encode(markdown))

    # Estimar tokens de HTML bruto: média de 5x o Markdown (heurística conservadora)
    tokens_antes = tokens_depois * 5

    # Custo economizado: tokens_antes - tokens_depois em GPT-4o (input: $2.50/1M tokens)
    tokens_economizados = tokens_antes - tokens_depois
    custo_economizado_usd = (tokens_economizados / 1_000_000) * 2.50
    custo_economizado_brl = custo_economizado_usd * settings.USD_BRL

    # --- Formatar e enviar ---
    cabecalho, conteudo_separado = formatar_resultado_url(
        markdown=markdown,
        tokens_antes=tokens_antes,
        tokens_depois=tokens_depois,
        custo_economizado_brl=custo_economizado_brl,
    )

    if conteudo_separado is None:
        # Tudo cabe numa mensagem
        await enviar_texto(numero, cabecalho)
    else:
        # Cabeçalho primeiro, depois o conteúdo
        await enviar_texto(numero, cabecalho)
        await enviar_arquivo_texto(numero, conteudo_separado, "resultado.md")
