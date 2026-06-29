"""
pdf_parser.py — Pipeline de conversão PDF → Markdown em cascata
Ordem: PyMuPDF4LLM (nativo) → Marker (OCR) → LlamaParse (premium)
"""

import logging
import os
import tempfile

logger = logging.getLogger("poda.pdf_parser")


async def pdf_para_markdown(pdf_bytes: bytes) -> tuple[str, int, int]:
    """
    Converte bytes de um PDF em Markdown estruturado.
    Retorna (markdown, num_paginas, tokens_brutos).
    tokens_brutos = tokens do texto puro extraído antes da estruturação.
    Tenta cada ferramenta em cascata até obter resultado satisfatório.
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    try:
        # Extrai texto bruto para calcular economia de tokens
        tokens_brutos = _contar_tokens_brutos(tmp_path)

        # --- Tentativa 1: PyMuPDF4LLM (PDFs nativos com texto) ---
        resultado = await _tentar_pymupdf4llm(tmp_path)
        if resultado:
            markdown, num_paginas = resultado
            logger.info(f"PyMuPDF4LLM: sucesso — {num_paginas} páginas, {len(markdown)} chars")
            return markdown, num_paginas, tokens_brutos

        # --- Tentativa 2: Marker (PDFs escaneados / imagens) ---
        logger.info("PyMuPDF4LLM insuficiente. Tentando Marker (OCR)...")
        resultado = await _tentar_marker(tmp_path)
        if resultado:
            markdown, num_paginas = resultado
            logger.info(f"Marker: sucesso — {num_paginas} páginas, {len(markdown)} chars")
            return markdown, num_paginas, tokens_brutos

        # --- Tentativa 3: LlamaParse (fallback premium) ---
        logger.info("Marker insuficiente. Tentando LlamaParse...")
        resultado = await _tentar_llama_parse(tmp_path)
        if resultado:
            markdown, num_paginas = resultado
            logger.info(f"LlamaParse: sucesso — {num_paginas} páginas, {len(markdown)} chars")
            return markdown, num_paginas, tokens_brutos

        raise ValueError("Nenhuma ferramenta conseguiu processar o PDF.")

    finally:
        os.unlink(tmp_path)  # Sempre deleta o arquivo temporário


def _contar_tokens_brutos(caminho: str) -> int:
    """Extrai texto puro do PDF e conta tokens (antes da estruturação em Markdown)."""
    try:
        import pymupdf
        import tiktoken

        doc = pymupdf.open(caminho)
        texto_bruto = "\n".join(page.get_text() for page in doc)
        doc.close()

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(texto_bruto))
    except Exception as e:
        logger.warning(f"Não foi possível contar tokens brutos: {e}")
        return 0


async def _tentar_pymupdf4llm(caminho: str) -> tuple[str, int] | None:
    """Extração via PyMuPDF4LLM (PDFs com texto nativo)."""
    try:
        import pymupdf4llm
        import pymupdf

        doc = pymupdf.open(caminho)
        num_paginas = len(doc)
        doc.close()

        markdown = pymupdf4llm.to_markdown(caminho)

        # Heurística: se menos de 50 chars por página, provavelmente é escaneado
        if len(markdown.strip()) < (num_paginas * 50):
            logger.warning(f"PyMuPDF4LLM: conteúdo suspeito ({len(markdown)} chars para {num_paginas} páginas).")
            return None

        return markdown, num_paginas

    except ImportError:
        logger.error("pymupdf4llm não instalado. Execute: pip install pymupdf4llm")
        return None
    except Exception as e:
        logger.warning(f"PyMuPDF4LLM falhou: {e}")
        return None


async def _tentar_marker(caminho: str) -> tuple[str, int] | None:
    """OCR via Marker para PDFs escaneados."""
    try:
        from marker.convert import convert_single_pdf
        from marker.models import load_all_models

        # Carrega modelos (lento na primeira vez, ~5s; em produção cachear)
        models = load_all_models()
        full_text, metadata, _ = convert_single_pdf(caminho, models)

        num_paginas = metadata.get("pages", 1)

        if not full_text.strip():
            return None

        return full_text, num_paginas

    except ImportError:
        logger.warning("marker-pdf não instalado. Pulando fallback OCR.")
        return None
    except Exception as e:
        logger.warning(f"Marker falhou: {e}")
        return None


async def _tentar_llama_parse(caminho: str) -> tuple[str, int] | None:
    """Fallback premium via LlamaParse (para PDFs muito complexos)."""
    from config import settings

    if not settings.LLAMA_CLOUD_API_KEY:
        logger.warning("LlamaParse não configurado (sem API key). Pulando.")
        return None

    try:
        from llama_parse import LlamaParse

        parser = LlamaParse(
            api_key=settings.LLAMA_CLOUD_API_KEY,
            result_type="markdown",
            verbose=False,
        )

        documents = await parser.aload_data(caminho)
        if not documents:
            return None

        markdown = "\n\n".join(doc.text for doc in documents)
        num_paginas = len(documents)

        return markdown, num_paginas

    except ImportError:
        logger.warning("llama-parse não instalado. Pulando.")
        return None
    except Exception as e:
        logger.warning(f"LlamaParse falhou: {e}")
        return None
