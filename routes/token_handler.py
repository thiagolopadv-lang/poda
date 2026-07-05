"""
token_handler.py — Processa textos para análise de tokens e custo
"""

import logging

from services.token_counter import analisar_tokens
from services.whatsapp_api import enviar_texto
from utils.formatter import formatar_resultado_tokens, formatar_erro
from config import settings

logger = logging.getLogger("poda.token_handler")


async def processar_texto(numero: str, texto: str) -> None:
    """
    Analisa o texto e envia a contagem de tokens + estimativa de custo.
    """
    if len(texto.strip()) < 10:
        await enviar_texto(
            numero,
            formatar_erro("O texto enviado é muito curto para análise. Envie um texto mais longo."),
        )
        return

    try:
        resultado = analisar_tokens(texto)
    except Exception as e:
        logger.error(f"Erro ao contar tokens: {e}")
        await enviar_texto(
            numero,
            formatar_erro("Erro ao processar o texto. Tente novamente."),
        )
        return

    try:
        mensagem = formatar_resultado_tokens(
            tokens=resultado["tokens"],
            chars=resultado["chars"],
            custos=resultado["custos"],
            usd_to_brl=settings.USD_BRL,
        )
    except Exception as e:
        logger.error(f"Erro ao formatar resultado de tokens: {e}")
        tokens = resultado.get("tokens", 0)
        chars = resultado.get("chars", 0)
        mensagem = (
            f"*ANÁLISE DO TEXTO*\n\n"
            f"Tokens: *{tokens:,}*\n"
            f"Caracteres: {chars:,}\n\n"
            "_Estimativa de custo temporariamente indisponível._"
        )

    await enviar_texto(numero, mensagem)
