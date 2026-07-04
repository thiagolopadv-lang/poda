"""
formatter.py — Formata respostas para o WhatsApp

Limites do WhatsApp:
- Mensagem de texto: 4.096 caracteres
- Arquivo: até 100 MB
"""

from config import settings

MAX_WHATSAPP_CHARS = 4_000  # Margem de segurança abaixo de 4.096
FOOTER_FREE = "\n\n—\n🌱 _Enviado pelo Poda_ · poda.io"


def formatar_resultado_url(
    markdown: str,
    tokens_antes: int,
    tokens_depois: int,
    custo_economizado_brl: float,
    plano: str = "free",
) -> tuple[str, str | None]:
    """
    Retorna (mensagem_cabecalho, conteudo_markdown_ou_None).
    Se o markdown couber na mensagem, retorna junto.
    Caso contrário, retorna o cabeçalho e o markdown separado (para envio como arquivo).
    """
    economia_pct = round((1 - tokens_depois / tokens_antes) * 100, 1) if tokens_antes else 0

    cabecalho = (
        f"✅ *Página convertida com sucesso*\n\n"
        f"📊 *Compressão realizada:*\n"
        f"   Antes:  ~{tokens_antes:,} tokens (HTML bruto)\n"
        f"   Depois:  {tokens_depois:,} tokens (Markdown limpo)\n"
        f"   Economia: *{economia_pct}%*\n\n"
        f"   💰 Em GPT-4o isso equivale a ~R${custo_economizado_brl:.2f} economizados\n"
        f"   nesta única requisição.\n"
    )

    if plano == "free":
        cabecalho += FOOTER_FREE

    conteudo_completo = cabecalho + "\n\n" + markdown

    if len(conteudo_completo) <= MAX_WHATSAPP_CHARS:
        return conteudo_completo, None

    # Markdown grande: enviar cabeçalho + arquivo separado
    return cabecalho, markdown


def formatar_resultado_pdf(
    markdown: str,
    num_paginas: int,
    tokens: int,
    plano: str = "free",
) -> tuple[str, str | None]:
    """Formata resultado da conversão PDF → Markdown."""
    cabecalho = (
        f"✅ *PDF convertido com sucesso*\n\n"
        f"📄 *Detalhes:*\n"
        f"   Páginas processadas: {num_paginas}\n"
        f"   Tokens no output: {tokens:,}\n\n"
        f"_O conteúdo foi estruturado em Markdown, pronto para colar no seu LLM._\n"
    )

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
    """Formata a análise de tokens para o usuário."""

    def barra_contexto(tokens: int, tamanho: int) -> str:
        pct = tokens / tamanho
        filled = int(pct * 10)
        bar = "▓" * filled + "░" * (10 - filled)
        return f"{bar} {pct*100:.1f}%"

    linhas_custo = ""
    menor_custo = min(custos.values()) if custos else 0
    for modelo, custo_usd in custos.items():
        custo_brl = custo_usd * usd_to_brl
        tag = "  ← mais barato" if custo_usd == menor_custo else ""
        linhas_custo += f"  {modelo:<20} R${custo_brl:.4f}{tag}\n"

    mensagem = (
        f"📊 *ANÁLISE DO SEU TEXTO*\n\n"
        f"Tokens: *{tokens:,}*\n"
        f"Caracteres: {chars:,}\n\n"
        f"💰 *CUSTO ESTIMADO (input):*\n"
        f"{linhas_custo}\n"
        f"📏 *USO DO CONTEXTO:*\n"
        f"  128K  {barra_contexto(tokens, 128_000)}\n"
        f"  200K  {barra_contexto(tokens, 200_000)}\n\n"
        f"💡 _Se este conteúdo vier de uma página web ou PDF,_\n"
        f"_envie o link ou arquivo para reduzir até 80% dos tokens._"
    )

    return mensagem


def formatar_erro(motivo: str) -> str:
    """Mensagem de erro padronizada."""
    return f"❌ *Não consegui processar isso.*\n\n{motivo}\n\nTente novamente ou envie outro conteúdo."


def formatar_limite_atingido(tipo: str, limite: int, link_upgrade: str = "poda.io/pro") -> str:
    """Mensagem quando o usuário atinge o limite do plano free."""
    return (
        f"⚠️ *Limite diário atingido*\n\n"
        f"Você usou suas {limite} {tipo} gratuitas de hoje.\n\n"
        f"O limite reseta à meia-noite.\n\n"
        f"Para uso ilimitado, conheça o Plano Pro:\n"
        f"👉 {link_upgrade}"
    )


def formatar_nao_suportado() -> str:
    """Mensagem para tipos de arquivo não suportados."""
    return (
        "🤔 *Não reconheci esse tipo de conteúdo.*\n\n"
        "Posso processar:\n"
        "• 🔗 *URL* — qualquer link de página web\n"
        "• 📄 *PDF* — envie o arquivo diretamente\n"
        "• 📝 *Texto* — qualquer texto para contar tokens\n\n"
        "_Envie um desses e eu processo na hora._"
    )
