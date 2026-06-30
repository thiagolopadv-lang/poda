"""
test_detector.py — Testes para utils/detector.py
"""

import pytest
from utils.detector import detectar_tipo, extrair_url, ContentType


class TestDetectarTipoTexto:
    def _msg(self, texto: str) -> dict:
        return {"type": "text", "text": {"body": texto}}

    def test_url_http(self):
        assert detectar_tipo(self._msg("https://exemplo.com/artigo")) == ContentType.URL

    def test_url_em_frase(self):
        assert detectar_tipo(self._msg("Veja: https://g1.com/noticia")) == ContentType.URL

    def test_texto_simples(self):
        assert detectar_tipo(self._msg("Ola, tudo bem?")) == ContentType.TEXT

    def test_sem_url_com_ponto(self):
        assert detectar_tipo(self._msg("Dr. Silva esteve aqui.")) == ContentType.TEXT


class TestDetectarTipoPDF:
    def test_pdf_mime(self):
        msg = {"type": "document", "document": {"mime_type": "application/pdf", "id": "abc"}}
        assert detectar_tipo(msg) == ContentType.PDF

    def test_docx_nao_suportado(self):
        msg = {"type": "document", "document": {"mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "id": "x"}}
        assert detectar_tipo(msg) == ContentType.UNSUPPORTED


class TestDetectarTipoUnsupported:
    def test_imagem(self):
        assert detectar_tipo({"type": "image"}) == ContentType.UNSUPPORTED

    def test_audio(self):
        assert detectar_tipo({"type": "audio"}) == ContentType.UNSUPPORTED

    def test_video(self):
        assert detectar_tipo({"type": "video"}) == ContentType.UNSUPPORTED

    def test_sticker(self):
        assert detectar_tipo({"type": "sticker"}) == ContentType.UNSUPPORTED

    def test_reaction(self):
        assert detectar_tipo({"type": "reaction"}) == ContentType.UNSUPPORTED


class TestExtrairUrl:
    def _msg(self, texto: str) -> dict:
        return {"type": "text", "text": {"body": texto}}

    def test_extrai_url_simples(self):
        msg = self._msg("Veja: https://exemplo.com/pagina")
        assert extrair_url(msg) == "https://exemplo.com/pagina"

    def test_extrai_primeira_url(self):
        msg = self._msg("https://primeiro.com e https://segundo.com")
        assert extrair_url(msg) == "https://primeiro.com"

    def test_sem_url_retorna_none(self):
        msg = self._msg("texto sem link")
        assert extrair_url(msg) is None
