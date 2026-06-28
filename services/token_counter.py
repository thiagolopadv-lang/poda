"""
token_counter.py — Contagem de tokens e estimativa de custo
Usa tiktoken (local, $0) + tokencost (local, $0)
"""

import logging

logger = logging.getLogger("poda.token_counter")

# Modelos para exibição na resposta
MODELOS = [
    ("GPT-4o", "gpt-4o"),
    ("GPT-4o mini", "gpt-4o-mini"),
    ("Claude Sonnet", "claude-sonnet-4-6"),
    ("Claude Haiku", "claude-haiku-4-5-20251001"),
    ("Gemini 1.5 Pro", "gemini-1.5-pro"),
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
    from tokencost import calculate_prompt_cost

    # Contagem de tokens (cl100k_base cobre GPT-4, Claude e a maioria dos modelos)
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = len(enc.encode(texto))
    chars = len(texto)

    # Custo estimado por modelo (em USD)
    custos = {}
    for nome_display, nome_modelo in MODELOS:
        try:
            custo_usd = float(calculate_prompt_cost(texto, nome_modelo))
            custos[nome_display] = custo_usd
        except Exception as e:
            logger.warning(f"Não foi possível calcular custo para {nome_modelo}: {e}")
            custos[nome_display] = 0.0

    logger.info(f"Token counter: {tokens} tokens, {chars} chars")

    return {
        "tokens": tokens,
        "chars": chars,
        "custos": custos,
    }
