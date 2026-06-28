"""
firecrawl.py — Fallback para páginas renderizadas com JavaScript
Usado quando o Jina Reader retorna conteúdo insuficiente.
https://www.firecrawl.dev/
"""

import logging
import httpx

from config import settings

logger = logging.getLogger("poda.firecrawl")

FIRECRAWL_API = "https://api.firecrawl.dev/v1/scrape"
TIMEOUT = 60  # segundos — Firecrawl é mais lento pois executa JS


async def url_para_markdown(url: str) -> str | None:
    """
    Converte uma URL em Markdown usando o Firecrawl.
    Retorna None se não houver API key configurada ou se falhar.
    """
    if not settings.FIRECRAWL_API_KEY:
        logger.warning("Firecrawl não configurado (sem API key). Pulando fallback.")
        return None

    payload = {
        "url": url,
        "formats": ["markdown"],
        "onlyMainContent": True,
    }

    headers = {
        "Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }

    logger.info(f"Firecrawl: processando {url}")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(FIRECRAWL_API, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

    markdown = data.get("data", {}).get("markdown", "")

    if not markdown.strip():
        logger.warning(f"Firecrawl retornou conteúdo vazio para {url}")
        return None

    logger.info(f"Firecrawl: sucesso — {len(markdown)} chars")
    return markdown
