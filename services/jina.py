"""
jina.py — Cliente para o Jina Reader API
Converte qualquer URL em Markdown limpo.
https://jina.ai/reader/
"""

import logging
import httpx

from config import settings

logger = logging.getLogger("poda.jina")

JINA_BASE = "https://r.jina.ai"
TIMEOUT = 30  # segundos
MIN_CONTENT_LENGTH = 200  # chars — se menos que isso, fallback para Firecrawl


async def url_para_markdown(url: str) -> str | None:
    """
    Converte uma URL em Markdown usando o Jina Reader.
    Retorna None se o conteúdo for insuficiente (página com JS ou protegida).
    Lança exceção se houver erro de rede.
    """
    jina_url = f"{JINA_BASE}/{url}"
    headers = {}

    if settings.JINA_API_KEY:
        headers["Authorization"] = f"Bearer {settings.JINA_API_KEY}"
        headers["X-Return-Format"] = "markdown"

    logger.info(f"Jina Reader: processando {url}")

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        response = await client.get(jina_url, headers=headers)
        response.raise_for_status()
        content = response.text

    if len(content.strip()) < MIN_CONTENT_LENGTH:
        logger.warning(f"Jina retornou conteúdo insuficiente para {url} ({len(content)} chars). Tentando fallback.")
        return None

    logger.info(f"Jina Reader: sucesso — {len(content)} chars")
    return content
