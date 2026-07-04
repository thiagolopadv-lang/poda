"""
pdf_handler.py - Processa PDFs enviados pelo usuario
Fluxo: verificar limite -> baixa PDF -> PyMuPDF4LLM -> Marker -> LlamaParse -> erro
"""

import logging
import tiktoken

from services.pdf_parser import pdf_para_markdown
from services.rate_limiter import rate_limiter
from services.whatsapp_api import baixar_midia, enviar_texto, enviar_arquivo_texto
from utils.formatter import formatar_resultado_pdf, formatar_erro, formatar_limite_atingido
from config import settings

logger = logging.getLogger("poda.pdf_handler")

MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


async def processar_pdf(numero: str, media_id: str) -> None:
    """
    Orquestra o download e conversao do PDF para Markdown.
    """
    log_ctx = {"numero": numero, "media_id": media_id}

    # --- Verificar limite diario (plano free) ---
    if not await rate_limiter.pode_processar_pdf(numero):
        logger.info("Limite diario de PDFs atingido.", extra=log_ctx)
        plano = await rate_limiter.get_plano(numero)
        limite_real = rate_limiter._limite_pdf(plano) or settings.FREE_PDF_LIMIT_PER_DAY
        await enviar_texto(
            numero,
            formatar_limite_atingido(
                tipo="conversoes de PDF",
                limite=limite_real,
            ),
        )
        return

    # --- Baixar PDF da Meta API ---
    try:
        pdf_bytes = await baixar_midia(media_id)
        logger.info("PDF baixado com sucesso.", extra={**log_ctx, "tamanho_bytes": len(pdf_bytes)})
    except Exception as e:
        logger.error("Erro ao baixar PDF.", extra={**log_ctx, "erro": str(e)})
        await enviar_texto(numero, formatar_erro("Nao consegui baixar o arquivo. Tente reenviar o PDF."))
        return

    # Verificar tamanho
    tamanho_mb = len(pdf_bytes) / 1024 / 1024
    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        logger.warning("PDF acima do limite de tamanho.", extra={**log_ctx, "tamanho_mb": tamanho_mb})
        await enviar_texto(
            numero,
            formatar_erro(
                f"O PDF e muito grande ({tamanho_mb:.1f} MB). "
                "O limite e 50 MB. Tente dividir o documento."
            ),
        )
        return

    # --- Converter para Markdown ---
    try:
        markdown, num_paginas, tokens_brutos = await pdf_para_markdown(pdf_bytes)
        logger.info("PDF convertido com sucesso.", extra={**log_ctx, "paginas": num_paginas})
    except Exception as e:
        logger.error("Erro ao converter PDF.", extra={**log_ctx, "erro": str(e)})
        await enviar_texto(
            numero,
            formatar_erro(
                "Nao consegui processar este PDF. "
                "Pode ser um arquivo corrompido, protegido por senha ou com formato incomum."
            ),
        )
        return

    # --- Registrar uso (so apos processamento bem-sucedido) ---
    await rate_limiter.registrar_pdf(numero)
    pdfs_restantes = await rate_limiter.pdfs_restantes(numero)

    # --- Calcular tokens do output ---
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = len(enc.encode(markdown))

    logger.info(
        "PDF processado e pronto para envio.",
        extra={
            **log_ctx,
            "paginas": num_paginas,
            "tokens_saida": tokens,
            "pdfs_restantes": pdfs_restantes,
        },
    )

    # --- Formatar e enviar ---
    cabecalho, conteudo_separado = formatar_resultado_pdf(
        markdown=markdown,
        num_paginas=num_paginas,
        tokens=tokens,
        tokens_brutos=tokens_brutos,
        pdfs_restantes=pdfs_restantes,
        limite_diario=settings.FREE_PDF_LIMIT_PER_DAY,
    )

    if conteudo_separado is None:
        await enviar_texto(numero, cabecalho)
    else:
        await enviar_texto(numero, cabecalho)
        await enviar_arquivo_texto(numero, conteudo_separado, "resultado.md")
