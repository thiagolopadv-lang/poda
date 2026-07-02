"""
rate_limiter.py — Controle de limites diários por usuário com suporte a planos

Usa Redis para persistência entre reinicializações do servidor.
Fallback automático para memória se REDIS_URL não estiver configurado.

Planos:
  free   — 5 URLs/dia, 2 PDFs/dia
  pro    — 50 URLs/dia, 20 PDFs/dia
  equipe — ilimitado
"""

import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo
from collections import defaultdict

from config import settings

logger = logging.getLogger("poda.rate_limiter")

BRASILIA = ZoneInfo("America/Sao_Paulo")

_redis_client = None

LIMITES_URL = {
    "free": settings.FREE_URL_LIMIT_PER_DAY,
    "pro": settings.PRO_URL_LIMIT_PER_DAY,
    "equipe": None,
}
LIMITES_PDF = {
    "free": settings.FREE_PDF_LIMIT_PER_DAY,
    "pro": settings.PRO_PDF_LIMIT_PER_DAY,
    "equipe": None,
}


def _get_redis():
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
            logger.warning(f"Nao foi possivel conectar ao Redis: {e}. Usando memoria.")
    return _redis_client


def _segundos_ate_meia_noite() -> int:
    agora = datetime.now(BRASILIA)
    meia_noite = agora.replace(hour=23, minute=59, second=59, microsecond=0)
    diff = meia_noite - agora
    return max(60, int(diff.total_seconds()))


class RateLimiter:
    def __init__(self):
        self._memoria: dict[str, dict] = defaultdict(
            lambda: {"data": None, "urls": 0, "pdfs": 0}
        )

    @property
    def redis(self):
        return _get_redis()

    def _chave(self, tipo: str, numero: str) -> str:
        hoje = date.today().isoformat()
        return f"poda:{tipo}:{hoje}:{numero}"

    def _resetar_memoria(self, numero: str) -> None:
        hoje = date.today()
        if self._memoria[numero]["data"] != hoje:
            self._memoria[numero] = {"data": hoje, "urls": 0, "pdfs": 0}

    def _hoje(self):
        return datetime.now(BRASILIA).date()

    def _limite_url(self, plano: str):
        return LIMITES_URL.get(plano, settings.FREE_URL_LIMIT_PER_DAY)

    def _limite_pdf(self, plano: str):
        return LIMITES_PDF.get(plano, settings.FREE_PDF_LIMIT_PER_DAY)

    async def get_plano(self, numero: str) -> str:
        redis = _get_redis()
        if redis:
            try:
                plano = await redis.get(f"poda:plano:{numero}")
                return plano if plano in ("pro", "equipe") else "free"
            except Exception as e:
                logger.warning(f"Redis erro em get_plano: {e}")
        return "free"

    async def set_plano(self, numero: str, plano: str, dias: int = None) -> None:
        if dias is None:
            dias = settings.PLANO_DIAS
        redis = _get_redis()
        if redis:
            try:
                ttl = dias * 86400
                await redis.setex(f"poda:plano:{numero}", ttl, plano)
                logger.info(f"Plano {plano} ativado para {numero} por {dias} dias.")
            except Exception as e:
                logger.error(f"Redis erro em set_plano: {e}")

    async def get_plano_expiracao(self, numero: str) -> int:
        redis = _get_redis()
        if redis:
            try:
                return await redis.ttl(f"poda:plano:{numero}")
            except Exception:
                pass
        return -2

    async def pode_processar_url(self, numero: str) -> bool:
        plano = await self.get_plano(numero)
        limite = self._limite_url(plano)
        if limite is None:
            return True
        redis = _get_redis()
        if redis:
            try:
                count = await redis.get(self._chave("urls", numero))
                return (int(count) if count else 0) < limite
            except Exception as e:
                logger.warning(f"Redis erro em pode_processar_url: {e}. Fallback memoria.")
        self._resetar_memoria(numero)
        return self._memoria[numero]["urls"] < limite

    async def registrar_url(self, numero: str) -> None:
        redis = _get_redis()
        if redis:
            try:
                chave = self._chave("urls", numero)
                pipe = redis.pipeline()
                pipe.incr(chave)
                pipe.expire(chave, _segundos_ate_meia_noite())
                await pipe.execute()
                return
            except Exception as e:
                logger.warning(f"Redis erro em registrar_url: {e}. Fallback memoria.")
        self._resetar_memoria(numero)
        self._memoria[numero]["urls"] += 1

    async def urls_restantes(self, numero: str) -> int:
        plano = await self.get_plano(numero)
        limite = self._limite_url(plano)
        if limite is None:
            return 9999
        redis = _get_redis()
        if redis:
            try:
                count = await redis.get(self._chave("urls", numero))
                usadas = int(count) if count else 0
                return max(0, limite - usadas)
            except Exception as e:
                logger.warning(f"Redis erro em urls_restantes: {e}. Fallback memoria.")
        self._resetar_memoria(numero)
        return max(0, limite - self._memoria[numero]["urls"])

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

    async def pode_processar_pdf(self, numero: str) -> bool:
        plano = await self.get_plano(numero)
        limite = self._limite_pdf(plano)
        if limite is None:
            return True
        redis = _get_redis()
        if redis:
            try:
                count = await redis.get(self._chave("pdfs", numero))
                return (int(count) if count else 0) < limite
            except Exception as e:
                logger.warning(f"Redis erro em pode_processar_pdf: {e}. Fallback memoria.")
        self._resetar_memoria(numero)
        return self._memoria[numero]["pdfs"] < limite

    async def registrar_pdf(self, numero: str) -> None:
        redis = _get_redis()
        if redis:
            try:
                chave = self._chave("pdfs", numero)
                pipe = redis.pipeline()
                pipe.incr(chave)
                pipe.expire(chave, _segundos_ate_meia_noite())
                await pipe.execute()
                return
            except Exception as e:
                logger.warning(f"Redis erro em registrar_pdf: {e}. Fallback memoria.")
        self._resetar_memoria(numero)
        self._memoria[numero]["pdfs"] += 1

    async def pdfs_restantes(self, numero: str) -> int:
        plano = await self.get_plano(numero)
        limite = self._limite_pdf(plano)
        if limite is None:
            return 9999
        redis = _get_redis()
        if redis:
            try:
                count = await redis.get(self._chave("pdfs", numero))
                usadas = int(count) if count else 0
                return max(0, limite - usadas)
            except Exception as e:
                logger.warning(f"Redis erro em pdfs_restantes: {e}. Fallback memoria.")
        self._resetar_memoria(numero)
        return max(0, limite - self._memoria[numero]["pdfs"])

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

    async def status_usuario(self, numero: str) -> dict:
        plano = await self.get_plano(numero)
        limite_url = self._limite_url(plano)
        limite_pdf = self._limite_pdf(plano)
        u_usadas = await self.urls_usadas(numero)
        p_usados = await self.pdfs_usados(numero)
        ttl = await self.get_plano_expiracao(numero)
        dias_plano = max(0, ttl // 86400) if ttl > 0 else 0

        url_lim_txt = str(limite_url) if limite_url is not None else "inf"
        pdf_lim_txt = str(limite_pdf) if limite_pdf is not None else "inf"
        url_rest = max(0, limite_url - u_usadas) if limite_url is not None else None
        pdf_rest = max(0, limite_pdf - p_usados) if limite_pdf is not None else None

        return {
            "plano": plano,
            "dias_restantes": dias_plano,
            "urls_usadas": u_usadas,
            "urls_limite": limite_url,
            "urls_limite_txt": url_lim_txt,
            "urls_restantes": url_rest,
            "pdfs_usados": p_usados,
            "pdfs_limite": limite_pdf,
            "pdfs_limite_txt": pdf_lim_txt,
            "pdfs_restantes": pdf_rest,
            "data": self._hoje().strftime("%d/%m/%Y"),
        }


rate_limiter = RateLimiter()
