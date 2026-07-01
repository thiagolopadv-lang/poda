"""
metrics.py â Coleta e leitura de mÃ©tricas do bot Poda

Registra no Redis contadores de mensagens, usuÃ¡rios, tipos e erros.
"""

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import settings

logger = logging.getLogger("poda.metrics")
BRASILIA = ZoneInfo("America/Sao_Paulo")
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None and settings.REDIS_URL:
        try:
            import redis.asyncio as aioredis
            _redis_client = aioredis.from_url(
                settings.REDIS_URL, decode_responses=True, socket_connect_timeout=5,
            )
        except Exception as e:
            logger.warning(f"Metrics: Redis indisponÃ­vel: {e}")
    return _redis_client


def _hoje() -> str:
    return datetime.now(BRASILIA).strftime("%Y-%m-%d")


def _agora_iso() -> str:
    return datetime.now(BRASILIA).isoformat(timespec="seconds")


async def registrar_mensagem_recebida(numero: str, tipo: str) -> None:
    """Tipos: url | pdf | texto | comando | saudacao | invalido"""
    r = _get_redis()
    if not r:
        return
    try:
        hoje = _hoje()
        pipe = r.pipeline()
        pipe.incr("poda:metrics:msgs_recebidas")
        pipe.incr(f"poda:metrics:tipos:{tipo}")
        pipe.incr(f"poda:metrics:msgs_dia:{hoje}")
        pipe.sadd(f"poda:metrics:usuarios:{hoje}", numero)
        pipe.expire(f"poda:metrics:usuarios:{hoje}", 60 * 60 * 24 * 30)
        pipe.expire(f"poda:metrics:msgs_dia:{hoje}", 60 * 60 * 24 * 30)
        pipe.set("poda:metrics:ultimo_evento", _agora_iso())
        pipe.setnx("poda:metrics:inicio", _agora_iso())
        await pipe.execute()
    except Exception as e:
        logger.warning(f"Metrics: erro ao registrar: {e}")


async def registrar_mensagem_enviada() -> None:
    r = _get_redis()
    if not r:
        return
    try:
        await r.incr("poda:metrics:msgs_enviadas")
    except Exception as e:
        logger.warning(f"Metrics: erro ao registrar envio: {e}")


async def registrar_erro() -> None:
    r = _get_redis()
    if not r:
        return
    try:
        await r.incr("poda:metrics:erros")
    except Exception as e:
        logger.warning(f"Metrics: erro ao registrar erro: {e}")


async def obter_metricas() -> dict:
    """Retorna todas as mÃ©tricas para o dashboard."""
    r = _get_redis()
    if not r:
        return {"redis_disponivel": False}
    try:
        hoje = _hoje()
        pipe = r.pipeline()
        pipe.get("poda:metrics:msgs_recebidas")
        pipe.get("poda:metrics:msgs_enviadas")
        pipe.get("poda:metrics:erros")
        pipe.get(f"poda:metrics:msgs_dia:{hoje}")
        pipe.scard(f"poda:metrics:usuarios:{hoje}")
        pipe.get("poda:metrics:ultimo_evento")
        pipe.get("poda:metrics:inicio")
        for tipo in ["url", "pdf", "texto", "comando", "saudacao", "invalido"]:
            pipe.get(f"poda:metrics:tipos:{tipo}")
        for i in range(7, 0, -1):
            dia = (datetime.now(BRASILIA) - timedelta(days=i)).strftime("%Y-%m-%d")
            pipe.scard(f"poda:metrics:usuarios:{dia}")
            pipe.get(f"poda:metrics:msgs_dia:{dia}")

        res = await pipe.execute()

        tipos = {
            "url": int(res[7] or 0), "pdf": int(res[8] or 0),
            "texto": int(res[9] or 0), "comando": int(res[10] or 0),
            "saudacao": int(res[11] or 0), "invalido": int(res[12] or 0),
        }

        historico = []
        for i in range(7, 0, -1):
            dia = (datetime.now(BRASILIA) - timedelta(days=i)).strftime("%Y-%m-%d")
            idx = 13 + (i - 1) * 2
            historico.append({
                "data": dia,
                "usuarios": int(res[idx] or 0),
                "mensagens": int(res[idx + 1] or 0),
            })

        uptime_str = None
        if res[6]:
            try:
                inicio_dt = datetime.fromisoformat(res[6])
                delta = datetime.now(BRASILIA) - inicio_dt
                uptime_str = f"{delta.days}d {delta.seconds // 3600}h {(delta.seconds % 3600) // 60}m"
            except Exception:
                pass

        info = await r.info("server")

        return {
            "redis_disponivel": True,
            "redis_versao": info.get("redis_version", "?"),
            "redis_memoria": info.get("used_memory_human", "?"),
            "msgs_recebidas": int(res[0] or 0),
            "msgs_enviadas": int(res[1] or 0),
            "erros": int(res[2] or 0),
            "msgs_hoje": int(res[3] or 0),
            "usuarios_hoje": int(res[4] or 0),
            "ultimo_evento": res[5],
            "uptime": uptime_str,
            "tipos": tipos,
            "historico_7_dias": historico,
            "data_hoje": hoje,
        }
    except Exception as e:
        logger.error(f"Metrics: erro ao obter mÃ©tricas: {e}", exc_info=True)
        return {"redis_disponivel": False, "erro": str(e)}
