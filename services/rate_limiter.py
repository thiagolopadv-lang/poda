"""
rate_limiter.py — Controle de limites diários por usuário (plano free)

Usa Redis para persistência entre reinicializações do servidor.
Fallback automático para memória se REDIS_URL não estiver configurado.
"""

import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo
from collections import defaultdict

from config import settings

logger = logging.getLogger("poda.rate_limiter")

BRASILIA = ZoneInfo("America/Sao_Paulo")

_redis_client = None


def _get_redis():
    """Retorna o cliente Redis assíncrono (lazy init). None se não configurado."""
    global _redis_client
    if _redis_client is None and settings.REDIS_URL:
        try:
            import redis.asyncio as aioredis
            _redis_client = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=5,
            )
            logger.info("Redis conectado com sucesso.")
        except Exception as e:
            logger.warning(f"Não foi possível conectar ao Redis: {e}. Usando memória.")
    return _redis_client


def _segundos_ate_meia_noite() -> int:
    """Segundos restantes até meia-noite no horário de Brasília."""
    agora = datetime.now(BRASILIA)
    meia_noite = agora.replace(hour=23, minute=59, second=59, microsecond=0)
    diff = meia_noite - agora
    return max(60, int(diff.total_seconds()))


class RateLimiter:
    """
    Controla uso diário por número de telefone.

    Redis (produção): chaves com TTL expiram à meia-noite de Brasília.
      Chave: poda:{tipo}:{YYYY-MM-DD}:{numero}

    Memória (fallback): mesmo comportamento sem persistência entre deploys.
    """

    def __init__(self):
        self._memoria: dict[str, dict] = defaultdict(
            lambda: {"data": None, "urls": 0, "pdfs": 0}
        )

    def _hoje(self) -> date:
        return datetime.now(BRASILIA).date()

    def _chave(self, tipo: str, numero: str) -> str:
        return f"poda:{tipo}:{self._hoje().isoformat()}:{numero}"

    def _resetar_memoria(self, numero: str) -> None:
        hoje = self._hoje()
        if self._memoria[numero]["data"] != hoje:
            self._memoria[numero] = {"data": hoje, "urls": 0, "pdfs": 0}

    # ------------------------------------------------------------------ #
    # URLs                                                                 #
    # ------------------------------------------------------------------ #

    async def pode_processar_url(self, numero: str) -> bool:
        redis = _get_redis()
        if redis:
            try:
                count = await redis.get(self._chave("urls", numero))
                return (int(count) if count else 0) < settings.FREE_URL_LIMIT_PER_DAY
            except Exception as e:
                logger.warning(f"Redis erro em pode_processar_url: {e}. Fallback memória.")
        self._resetar_memoria(numero)
        return self._memoria[numero]["urls"] < settings.FREE_URL_LIMIT_PER_DAY

    async def registrar_url(self, numero: str) -> None:
        redis = _get_redis()
        if redis:
            try:
                chave = self._chave("urls", numero)
                pipe = redis.pipeline()
                pipe.incr(chave)
                pipe.expire(chave, _segundos_ate_meia_noite())
                await pipe.execute()
                logger.debug(f"[rate_limiter] {numero}: URL registrada no Redis")
                return
            except Exception as e:
                logger.warning(f"Redis erro em registrar_url: {e}. Fallback memória.")
        self._resetar_memoria(numero)
        self._memoria[numero]["urls"] += 1

    async def urls_restantes(self, numero: str) -> int:
        redis = _get_redis()
        if redis:
            try:
                count = await redis.get(self._chave("urls", numero))
                usadas = int(count) if count else 0
                return max(0, settings.FREE_URL_LIMIT_PER_DAY - usadas)
            except Exception as e:
                logger.warning(f"Redis erro em urls_restantes: {e}. Fallback memória.")
        self._resetar_memoria(numero)
        return max(0, settings.FREE_URL_LIMIT_PER_DAY - self._memoria[numero]["urls"])

    async def urls_usadas(self, numero: str) -> int:
        redis = _get_redis()
        if redis:
            try:
                count = await redis.get(self._chave("urls", numero))
                return int(count) if count else 0
            except Exception:
                pass
        self._resetar_memoria(numero)
        return self._memoria[numero]["urls"]

    # ------------------------------------------------------------------ #
    # PDFs                                                                 #
    # ------------------------------------------------------------------ #

    async def pode_processar_pdf(self, numero: str) -> bool:
        redis = _get_redis()
        if redis:
            try:
                count = await redis.get(self._chave("pdfs", numero))
                return (int(count) if count else 0) < settings.FREE_PDF_LIMIT_PER_DAY
            except Exception as e:
                logger.warning(f"Redis erro em pode_processar_pdf: {e}. Fallback memória.")
        self._resetar_memoria(numero)
        return self._memoria[numero]["pdfs"] < settings.FREE_PDF_LIMIT_PER_DAY

    async def registrar_pdf(self, numero: str) -> None:
        redis = _get_redis()
        if redis:
            try:
                chave = self._chave("pdfs", numero)
                pipe = redis.pipeline()
                pipe.incr(chave)
                pipe.expire(chave, _segundos_ate_meia_noite())
                await pipe.execute()
                logger.debug(f"[rate_limiter] {numero}: PDF registrado no Redis")
                return
            except Exception as e:
                logger.warning(f"Redis erro em registrar_pdf: {e}. Fallback memória.")
        self._resetar_memoria(numero)
        self._memoria[numero]["pdfs"] += 1

    async def pdfs_restantes(self, numero: str) -> int:
        redis = _get_redis()
        if redis:
            try:
                count = await redis.get(self._chave("pdfs", numero))
                usados = int(count) if count else 0
                return max(0, settings.FREE_PDF_LIMIT_PER_DAY - usados)
            except Exception as e:
                logger.warning(f"Redis erro em pdfs_restantes: {e}. Fallback memória.")
        self._resetar_memoria(numero)
        return max(0, settings.FREE_PDF_LIMIT_PER_DAY - self._memoria[numero]["pdfs"])

    async def pdfs_usados(self, numero: str) -> int:
        redis = _get_redis()
        if redis:
            try:
                count = await redis.get(self._chave("pdfs", numero))
                return int(count) if count else 0
            except Exception:
                pass
        self._resetar_memoria(numero)
        return self._memoria[numero]["pdfs"]

    # ------------------------------------------------------------------ #
    # Status completo (para comando /status)                               #
    # ------------------------------------------------------------------ #

    async def status_usuario(self, numero: str) -> dict:
        u_usadas = await self.urls_usadas(numero)
        p_usados = await self.pdfs_usados(numero)
        return {
            "urls_usadas": u_usadas,
            "urls_limite": settings.FREE_URL_LIMIT_PER_DAY,
            "urls_restantes": max(0, settings.FREE_URL_LIMIT_PER_DAY - u_usadas),
            "pdfs_usados": p_usados,
            "pdfs_limite": settings.FREE_PDF_LIMIT_PER_DAY,
            "pdfs_restantes": max(0, settings.FREE_PDF_LIMIT_PER_DAY - p_usados),
            "data": self._hoje().strftime("%d/%m/%Y"),
        }


# Instância global — singleton compartilhado em toda a aplicação
rate_limiter = RateLimiter()
