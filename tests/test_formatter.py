"""
test_formatter.py — Testes para utils/formatter.py
"""

import pytest
from utils.formatter import formatar_resultado_url, formatar_resultado_pdf, MAX_WHATSAPP_CHARS


MARKDOWN_CURTO = "# Titulo\n\nConteudo curto do artigo."
MARKDOWN_LONGO = "# Titulo\n\n" + ("Paragrafo de conteudo. " * 300)


class TestFormatarResultadoUrl:
    def test_retorna_tupla(self):
        resultado = formatar_resultado_url(
            markdown=MARKDOWN_CURTO,
            tokens_antes=1000,
            tokens_depois=100,
            custo_economizado_brl=0.05,
            plano="free",
            urls_restantes=4,
            limite_diario=5,
        )
        assert isinstance(resultado, tuple)
        assert len(resultado) == 2

    def test_conteudo_curto_segundo_elemento_none(self):
        cabecalho, conteudo = formatar_resultado_url(
            markdown=MARKDOWN_CURTO,
            tokens_antes=500,
            tokens_depois=50,
            custo_economizado_brl=0.02,
            plano="free",
            urls_restantes=4,
            limite_diario=5,
        )
        assert cabecalho is not None
        assert conteudo is None

    def test_conteudo_longo_segundo_elemento_preenchido(self):
        cabecalho, conteudo = formatar_resultado_url(
            markdown=MARKDOWN_LONGO,
            tokens_antes=5000,
            tokens_depois=500,
            custo_economizado_brl=0.50,
            plano="free",
            urls_restantes=4,
            limite_diario=5,
        )
        assert cabecalho is not None
        assert conteudo is not None
        assert len(conteudo) > 0

    def test_cabecalho_contem_tokens(self):
        cabecalho, _ = formatar_resultado_url(
            markdown=MARKDOWN_CURTO,
            tokens_antes=1000,
            tokens_depois=100,
            custo_economizado_brl=0.05,
            plano="free",
            urls_restantes=3,
            limite_diario=5,
        )
        assert "1.000" in cabecalho or "1000" in cabecalho or "token" in cabecalho.lower()

    def test_limite_atingido_mensagem_presente(self):
        cabecalho, _ = formatar_resultado_url(
            markdown=MARKDOWN_CURTO,
            tokens_antes=100,
            tokens_depois=10,
            custo_economizado_brl=0.01,
            plano="free",
            urls_restantes=0,
            limite_diario=5,
        )
        assert cabecalho is not None


class TestFormatarResultadoPdf:
    def test_retorna_tupla(self):
        resultado = formatar_resultado_pdf(
            markdown=MARKDOWN_CURTO,
            num_paginas=3,
            tokens=200,
            tokens_brutos=500,
            pdfs_restantes=2,
            limite_diario=3,
        )
        assert isinstance(resultado, tuple)
        assert len(resultado) == 2

    def test_conteudo_curto_segundo_elemento_none(self):
        cabecalho, conteudo = formatar_resultado_pdf(
            markdown=MARKDOWN_CURTO,
            num_paginas=1,
            tokens=100,
            tokens_brutos=200,
            pdfs_restantes=2,
            limite_diario=3,
        )
        assert conteudo is None

    def test_conteudo_longo_segundo_elemento_preenchido(self):
        cabecalho, conteudo = formatar_resultado_pdf(
            markdown=MARKDOWN_LONGO,
            num_paginas=10,
            tokens=5000,
            tokens_brutos=8000,
            pdfs_restantes=2,
            limite_diario=3,
        )
        assert conteudo is not None
        assert len(conteudo) > 0

    def test_cabecalho_contem_paginas(self):
        cabecalho, _ = formatar_resultado_pdf(
            markdown=MARKDOWN_CURTO,
            num_paginas=5,
            tokens=300,
            tokens_brutos=600,
            pdfs_restantes=2,
            limite_diario=3,
        )
        assert "5" in cabecalho


class TestMaxWhatsappChars:
    def test_constante_definida(self):
        assert MAX_WHATSAPP_CHARS == 4_000

    def test_markdown_curto_abaixo_do_limite(self):
        assert len(MARKDOWN_CURTO) < MAX_WHATSAPP_CHARS

    def test_markdown_longo_acima_do_limite(self):
        assert len(MARKDOWN_LONGO) > MAX_WHATSAPP_CHARS
