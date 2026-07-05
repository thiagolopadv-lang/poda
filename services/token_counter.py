"""
token_counter.py — Contagem de tokens e estimativa de custo
Usa tiktoken para contar tokens; preços hardcoded por modelo.
"""

import logging

logger = logging.getLogger("poda.token_counter")

# Preços de input em USD por 1 milhão de tokens (fonte: sites oficiais)
# Atualizar aqui quando os provedores mudarem os preços.
MODELOS = [
    ("GPT-4o",            "gpt-4o",                      2.50),
    ("GPT-4o mini",       "gpt-4o-mini",                 0.15),
    ("Claude Sonnet 4",   "claude-sonnet-4",             3.00),
    ("Claude Haiku 4.5",  "claude-haiku-4-5",            0.80),
    ("Gemini 1.5 Pro",    "gemini-1.5-pro",              1.25),
]


def analisar_tokens(texto: str) -> dict:
    """
    Analisa o texto e retorna contagem de tokens e custos estimados.

    Retorna:
    {
        "tokens": int,
        "chars": int,
        "custos": {"GPT-4o": float_usd, ...}
    }
    """
    import tiktoken

    # Contagem de tokens (cl100k_base cobre GPT-4, Claude e a maioria dos modelos)
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = len(enc.encode(texto))
    chars = len(texto)

    # Custo estimado por modelo (em USD)
    custos = {}
    for nome_display, _nome_api, preco_por_milhao in MODELOS:
        try:
            custo_usd = (tokens / 1_000_000) * preco_por_milhao
            custos[nome_display] = custo_usd
        except Exception as e:
            logger.warning(f"Erro ao calcular custo para {nome_display}: {e}")
            custos[nome_display] = 0.0

    logger.info(f"Token counter: {tokens} tokens, {chars} chars")

    return {
        "tokens": tokens,
        "chars": chars,
        "custos": custos,
    }
