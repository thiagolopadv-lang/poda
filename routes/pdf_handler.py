"""
pdf_handler.py — Processa PDFs enviados pelo usuário
Fluxo: baixa PDF → PyMuPDF4LLM → Marker → LlamaParse → erro
"""

import logging
import tiktoken

from services.pdf_parser import pdf_para_markdown
from services.whatsapp_api import baixar_midia, enviar_texto, enviar_arquivo_texto
from utils.formatter import formatar_resultado_pdf, formatar_erro

logger = logging.getLogger("poda.pdf_handler")

MAX_PDF_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


async def processar_pdf(numero: str, media_id: str) -> None:
    """
    Orquestra o download e conversão do PDF para Markdown.
    """
    # --- Baixar PDF da Meta API ---
    try:
        pdf_bytes = await baixar_midia(media_id)
    except Exception as e:
        logger.error(f"Erro ao baixar PDF (media_id={media_id}): {e}")
        await enviar_texto(numero, formatar_erro("Não consegui baixar o arquivo. Tente reenviar o PDF."))
        return

    # Verificar tamanho
    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        await enviar_texto(
            numero,
            formatar_erro(
                f"O PDF é muito grande ({len(pdf_bytes) / 1024 / 1024:.1f} MB). "
                "O limite é 50 MB. Tente dividir o documento."
            ),
        )
        return

    # --- Converter para Markdown ---
    try:
        markdown, num_paginas = await pdf_para_markdown(pdf_bytes)
    except Exception as e:
        logger.error(f"Erro ao converter PDF: {e}")
        await enviar_texto(
            numero,
            formatar_erro(
                "Não consegui processar este PDF. "
                "Pode ser um arquivo corrompido, protegido por senha ou com formato incomum."
            ),
        )
        return

    # --- Calcular tokens do output ---
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = len(enc.encode(markdown))

    # --- Formatar e enviar ---
    cabecalho, conteudo_separado = formatar_resultado_pdf(
        markdown=markdown,
        num_paginas=num_paginas,
        tokens=tokens,
    )

    if conteudo_separado is None:
        await enviar_texto(numero, cabecalho)
    else:
        await enviar_texto(numero, cabecalho)
        await enviar_arquivo_texto(numero, conteudo_separado, "documento.md")
