"""
pdf_handler.py — Processa PDFs enviados pelo usuário
Fluxo: baixa PDF → PyMuPDF4LLM → Marker → LlamaParse → erro
"""

import logging
import time
import tiktoken

from services import metricas_comerciais
from services.pdf_parser import pdf_para_markdown, PDFEscaneadoError
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

    inicio = time.monotonic()

    # Verificar tamanho
    if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
        await metricas_comerciais.registrar_erro("pdf", "too_large")
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
    except PDFEscaneadoError:
        logger.info("PDF escaneado detectado — sem OCR disponível.")
        await enviar_texto(
            numero,
            "📄 *Este PDF é uma imagem digitalizada (escaneado).*\n\n"
            "Ele não tem texto selecionável — é o caso comum de matrículas de imóvel, "
            "certidões e documentos digitalizados em cartório.\n\n"
            "Por enquanto não faço leitura de imagem (OCR). O que funciona:\n"
            "• PDFs gerados digitalmente (sites, sistemas, Word)\n"
            "• Documentos onde dá para *selecionar o texto* no leitor de PDF\n\n"
            "💡 _Dica: se o documento veio de um sistema online, baixe a versão "
            "digital em vez da digitalizada._",
        )
        return
    except Exception as e:
        logger.error(f"Erro ao converter PDF: {e}")
        await metricas_comerciais.registrar_erro("pdf", "parse_fail")
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
    from services.rate_limiter import rate_limiter
    plano = await rate_limiter.get_plano(numero)

    cabecalho, conteudo_separado = formatar_resultado_pdf(
        markdown=markdown,
        num_paginas=num_paginas,
        tokens=tokens,
        plano=plano,
    )

    if conteudo_separado is None:
        await enviar_texto(numero, cabecalho)
    else:
        await enviar_texto(numero, cabecalho)
        await enviar_arquivo_texto(numero, conteudo_separado, "documento.md")

    await metricas_comerciais.registrar_latencia(
        "pdf", int((time.monotonic() - inicio) * 1000)
    )
