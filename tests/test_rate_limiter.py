"""
test_rate_limiter.py — Testes para services/rate_limiter.py
Usa apenas o modo fallback em memoria (sem Redis).
"""

import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from services.rate_limiter import RateLimiter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def limiter():
    """RateLimiter isolado sem Redis."""
    with patch("services.rate_limiter.settings") as mock_settings:
        mock_settings.REDIS_URL = ""  # desativa Redis
        rl = RateLimiter()
    return rl


NUMERO = "5511999990000"


# ---------------------------------------------------------------------------
# URLs — modo memoria
# ---------------------------------------------------------------------------

class TestUrls:
    @pytest.mark.asyncio
    async def test_pode_processar_quando_zero_usadas(self, limiter):
        assert await limiter.pode_processar_url(NUMERO) is True

    @pytest.mark.asyncio
    async def test_registrar_incrementa_contador(self, limiter):
        await limiter.registrar_url(NUMERO)
        assert await limiter.urls_usadas(NUMERO) == 1

    @pytest.mark.asyncio
    async def test_restantes_diminui_apos_registro(self, limiter):
        antes = await limiter.urls_restantes(NUMERO)
        await limiter.registrar_url(NUMERO)
        depois = await limiter.urls_restantes(NUMERO)
        assert depois == antes - 1

    @pytest.mark.asyncio
    async def test_bloqueia_apos_limite(self, limiter):
        limite = (await limiter.status_usuario(NUMERO))["urls_limite"]
        for _ in range(limite):
            await limiter.registrar_url(NUMERO)
        assert await limiter.pode_processar_url(NUMERO) is False

    @pytest.mark.asyncio
    async def test_restantes_nunca_negativo(self, limiter):
        limite = (await limiter.status_usuario(NUMERO))["urls_limite"]
        for _ in range(limite + 5):
            await limiter.registrar_url(NUMERO)
        assert await limiter.urls_restantes(NUMERO) == 0


# ---------------------------------------------------------------------------
# PDFs — modo memoria
# ---------------------------------------------------------------------------

class TestPdfs:
    @pytest.mark.asyncio
    async def test_pode_processar_quando_zero_usados(self, limiter):
        assert await limiter.pode_processar_pdf(NUMERO) is True

    @pytest.mark.asyncio
    async def test_registrar_incrementa_contador(self, limiter):
        await limiter.registrar_pdf(NUMERO)
        assert await limiter.pdfs_usados(NUMERO) == 1

    @pytest.mark.asyncio
    async def test_bloqueia_apos_limite(self, limiter):
        limite = (await limiter.status_usuario(NUMERO))["pdfs_limite"]
        for _ in range(limite):
            await limiter.registrar_pdf(NUMERO)
        assert await limiter.pode_processar_pdf(NUMERO) is False


# ---------------------------------------------------------------------------
# status_usuario
# ---------------------------------------------------------------------------

class TestStatusUsuario:
    @pytest.mark.asyncio
    async def test_retorna_dict_com_campos_esperados(self, limiter):
        status = await limiter.status_usuario(NUMERO)
        assert "urls_usadas" in status
        assert "urls_restantes" in status
        assert "pdfs_usados" in status
        assert "pdfs_restantes" in status
        assert "urls_limite" in status
        assert "pdfs_limite" in status

    @pytest.mark.asyncio
    async def test_contadores_iniciam_zero(self, limiter):
        status = await limiter.status_usuario(NUMERO)
        assert status["urls_usadas"] == 0
        assert status["pdfs_usados"] == 0

    @pytest.mark.asyncio
    async def test_status_reflete_registros(self, limiter):
        await limiter.registrar_url(NUMERO)
        await limiter.registrar_pdf(NUMERO)
        status = await limiter.status_usuario(NUMERO)
        assert status["urls_usadas"] == 1
        assert status["pdfs_usados"] == 1


# ---------------------------------------------------------------------------
# Isolamento entre usuarios
# ---------------------------------------------------------------------------

class TestIsolamentoUsuarios:
    @pytest.mark.asyncio
    async def test_usuarios_distintos_nao_compartilham_contagem(self, limiter):
        numero_b = "5521888880000"
        await limiter.registrar_url(NUMERO)
        assert await limiter.urls_usadas(numero_b) == 0
