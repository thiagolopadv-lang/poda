"""
formatter.py -- Formata respostas para o WhatsApp

Limites do WhatsApp:
- Mensagem de texto: 4.096 caracteres
- Arquivo: ate 100 MB
"""

from config import settings

MAX_WHATSAPP_CHARS = 4_000  # Margem de seguranca abaixo de 4.096
FOOTER_FREE = "\n\n--\n[Poda] poda.io"


def formatar_resultado_url(
    markdown: str,
    tokens_antes: int,
    tokens_depois: int,
    custo_economizado_brl: float,
    plano: str = "free",
    urls_restantes: int | None = None,
    limite_diario: int | None = None,
) -> tuple[str, str | None]:
    """
    Retorna (mensagem_cabecalho, conteudo_markdown_ou_None).
    Se o markdown couber na mensagem, retorna junto.
    Caso contrario, retorna o cabecalho e o markdown separado (para envio como arquivo).
    """
    economia_pct = round((1 - tokens_depois / tokens_antes) * 100, 1) if tokens_antes else 0

    cabecalho = (
        "OK *Pagina convertida com sucesso*\n\n"
        "*Compressao realizada:*\n"
        f"   Antes:  ~{tokens_antes:,} tokens (HTML bruto)\n"
        f"   Depois:  {tokens_depois:,} tokens (Markdown limpo)\n"
        f"   Economia: *{economia_pct}%*\n\n"
        f"   Em GPT-4o isso equivale a ~R${custo_economizado_brl:.2f} economizados\n"
        "   nesta unica requisicao.\n"
    )

    # Mostrar limite restante no plano free (gatilho de upgrade sutil)
    if plano == "free" and urls_restantes is not None and limite_diario is not None:
        if urls_restantes == 0:
            cabecalho += (
                f"\nATENCAO: Voce usou todas as {limite_diario} URLs gratuitas de hoje.\n"
                "Limite reseta a meia-noite. Plano Pro: poda.io/pro\n"
            )
        elif urls_restantes <= 1:
            cabecalho += f"\nRestam {urls_restantes} conversao de URL hoje (plano free).\n"

    if plano == "free":
        cabecalho += FOOTER_FREE

    conteudo_completo = cabecalho + "\n\n" + markdown

    if len(conteudo_completo) <= MAX_WHATSAPP_CHARS:
        return conteudo_completo, None

    # Markdown grande: enviar cabecalho + arquivo separado
    return cabecalho, markdown


def formatar_resultado_pdf(
    markdown: str,
    num_paginas: int,
    tokens: int,
    tokens_brutos: int = 0,
    plano: str = "free",
    pdfs_restantes: int | None = None,
    limite_diario: int | None = None,
) -> tuple[str, str | None]:
    """Formata resultado da conversao PDF -> Markdown."""
    # Linha de economia (so mostra se tokens_brutos > tokens)
    if tokens_brutos > tokens > 0:
        tokens_economizados = tokens_brutos - tokens
        economia_pct = round((tokens_economizados / tokens_brutos) * 100, 1)
        linha_economia = (
            f"   Tokens originais: ~{tokens_brutos:,}\n"
            f"   Tokens no output: {tokens:,}\n"
            f"   Economia: *{tokens_economizados:,} tokens ({economia_pct}%)*\n"
        )
    else:
        linha_economia = f"   Tokens no output: {tokens:,}\n"

    cabecalho = (
        "OK *PDF convertido com sucesso*\n\n"
        "*Detalhes:*\n"
        f"   Paginas processadas: {num_paginas}\n"
        f"{linha_economia}\n"
        "O conteudo foi estruturado em Markdown, pronto para colar no seu LLM.\n"
    )

    # Mostrar limite restante no plano free
    if plano == "free" and pdfs_restantes is not None and limite_diario is not None:
        if pdfs_restantes == 0:
            cabecalho += (
                f"\nATENCAO: Voce usou os {limite_diario} PDFs gratuitos de hoje.\n"
                "Limite reseta a meia-noite. Plano Pro: poda.io/pro\n"
            )
        elif pdfs_restantes <= 1:
            cabecalho += f"\nResta {pdfs_restantes} conversao de PDF hoje (plano free).\n"

    if plano == "free":
        cabecalho += FOOTER_FREE

    conteudo_completo = cabecalho + "\n\n" + markdown

    if len(conteudo_completo) <= MAX_WHATSAPP_CHARS:
        return conteudo_completo, None

    return cabecalho, markdown


def formatar_resultado_tokens(
    tokens: int,
    chars: int,
    custos: dict,
    usd_to_brl: float = 5.70,
) -> str:
    """Formata a analise de tokens para o usuario."""

    def barra_contexto(tokens: int, tamanho: int) -> str:
        pct = tokens / tamanho
        filled = int(pct * 10)
        bar = "#" * filled + "." * (10 - filled)
        return f"{bar} {pct*100:.1f}%"

    linhas_custo = ""
    menor_custo = min(custos.values()) if custos else 0
    for modelo, custo_usd in custos.items():
        custo_brl = custo_usd * usd_to_brl
        tag = "  <- mais barato" if custo_usd == menor_custo else ""
        linhas_custo += f"  {modelo:<20} R${custo_brl:.4f}{tag}\n"

    mensagem = (
        "*ANALISE DO SEU TEXTO*\n\n"
        f"Tokens: *{tokens:,}*\n"
        f"Caracteres: {chars:,}\n\n"
        "*CUSTO ESTIMADO (input):*\n"
        f"{linhas_custo}\n"
        "*USO DO CONTEXTO:*\n"
        f"  128K  {barra_contexto(tokens, 128_000)}\n"
        f"  200K  {barra_contexto(tokens, 200_000)}\n\n"
        "Se este conteudo vier de uma pagina web ou PDF,\n"
        "envie o link ou arquivo para reduzir ate 80% dos tokens."
    )

    return mensagem


def formatar_erro(motivo: str) -> str:
    """Mensagem de erro padronizada."""
    return f"ERRO: Nao consegui processar isso.\n\n{motivo}\n\nTente novamente ou envie outro conteudo."


def formatar_limite_atingido(tipo: str, limite: int, link_upgrade: str = "poda.io/pro") -> str:
    """Mensagem quando o usuario atinge o limite do plano free."""
    return (
        "AVISO: *Limite diario atingido*\n\n"
        f"Voce usou suas {limite} {tipo} gratuitas de hoje.\n\n"
        "O limite reseta a meia-noite.\n\n"
        "Para uso ilimitado, conheca o Plano Pro:\n"
        f"poda.io/pro -> {link_upgrade}"
    )


def formatar_nao_suportado(tipo: str = "") -> str:
    """Mensagem para tipos de arquivo nao suportados."""
    dicas_por_tipo = {
        "image": "Imagens nao sao suportadas ainda. Se voce quer extrair texto de uma imagem, tente converter para PDF primeiro.",
        "audio": "Audios nao sao suportados. Se for um conteudo transcrito, cole o texto diretamente.",
        "video": "Videos nao sao suportados.",
        "sticker": "Stickers sao otimos, mas so processo texto, links e PDFs!",
        "reaction": "",
    }

    dica = dicas_por_tipo.get(tipo, "")

    base = (
        "*Nao reconheci esse tipo de conteudo.*\n\n"
        "Posso processar:\n"
        "- Link: qualquer URL de pagina web\n"
        "- PDF: envie o arquivo PDF diretamente\n"
        "- Texto: qualquer texto para contar tokens\n\n"
        "Envie um desses e eu processo na hora."
    )

    if dica:
        return f"{dica}\n\n{base}"

    # Reacoes: nao responder (evita loop)
    if tipo == "reaction":
        return ""

    return base
