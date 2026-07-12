"""
metricas_comerciais.py — Rastreamento de funil de conversão, latência e erros
Módulo complementar ao services/metrics.py com inteligência comercial.
"""
import json
import time
from datetime import date, datetime
from typing import Optional
from zoneinfo import ZoneInfo

from services.rate_limiter import rate_limiter

BRASILIA = ZoneInfo("America/Sao_Paulo")


# ── Helpers internos ──────────────────────────────────────────────────────────

def _hoje() -> str:
    # Data de Brasília — consistente com os contadores do rate_limiter
    return datetime.now(BRASILIA).date().isoformat()


async def _incr(key: str, ex: int = 86400 * 30) -> None:
    try:
        await rate_limiter.redis.incr(key)
        await rate_limiter.redis.expire(key, ex)
    except Exception:
        pass


# ── Funil de Conversão ────────────────────────────────────────────────────────

async def registrar_limite_atingido(phone: str, modalidade: str = "url") -> None:
    """Etapa 1 — usuário atingiu limite de uso (gatilho comercial)."""
    try:
        hoje = _hoje()
        await _incr(f"poda:funnel:limit_hit:{hoje}")
        await _incr(f"poda:funnel:limit_hit:{modalidade}:{hoje}")
        # Marca o usuário como tendo atingido limite hoje (sem duplicar contagem)
        flag_key = f"poda:funnel:limit_flag:{phone}:{hoje}"
        if not await rate_limiter.redis.exists(flag_key):
            await rate_limiter.redis.set(flag_key, 1, ex=86400)
    except Exception:
        pass


async def registrar_intent_upgrade(phone: str) -> None:
    """Etapa 2 — usuário demonstrou interesse em upgrade (/planos ou similar)."""
    try:
        ts = int(time.time())
        await rate_limiter.redis.set(
            f"poda:funnel:intent:{phone}", ts, ex=3600 * 48
        )
        await _incr(f"poda:funnel:intent_total:{_hoje()}")
    except Exception:
        pass


async def registrar_cpf_informado(phone: str) -> None:
    """Etapa 3 — usuário informou CPF (intenção forte de compra)."""
    try:
        ts = int(time.time())
        await rate_limiter.redis.set(
            f"poda:funnel:cpf:{phone}", ts, ex=3600 * 2
        )
        await _incr(f"poda:funnel:cpf_total:{_hoje()}")
    except Exception:
        pass


async def registrar_pix_gerado(phone: str, plano: str, valor: float) -> None:
    """Etapa 4 — PIX gerado (início do 'abandono de carrinho' se não pagar)."""
    try:
        ts = int(time.time())
        data = json.dumps({"plano": plano, "valor": valor, "ts": ts})
        await rate_limiter.redis.set(
            f"poda:funnel:pix:{phone}", data, ex=3600 * 2
        )
        await _incr(f"poda:funnel:pix_total:{_hoje()}")
    except Exception:
        pass


async def registrar_pagamento_confirmado(phone: str, plano: str) -> None:
    """Etapa 5 — pagamento confirmado pelo webhook Asaas."""
    try:
        await _incr(f"poda:funnel:paid_total:{_hoje()}")
        # Remove o PIX pendente (não conta mais como abandono)
        await rate_limiter.redis.delete(f"poda:funnel:pix:{phone}")
    except Exception:
        pass


# ── Churn ─────────────────────────────────────────────────────────────────────

async def registrar_churn(phone: str, plano_anterior: str) -> None:
    """Registra cancelamento (downgrade para free ou expiração de plano)."""
    try:
        hoje = _hoje()
        data = json.dumps({"plano": plano_anterior, "data": hoje})
        await rate_limiter.redis.set(
            f"poda:churn:{phone}", data, ex=86400 * 90
        )
        await _incr(f"poda:churn:total:{hoje}")
    except Exception:
        pass


# ── Latência ──────────────────────────────────────────────────────────────────

async def registrar_latencia(modalidade: str, ms: int) -> None:
    """Registra latência em sorted set rotativo (últimas 500 amostras por modalidade)."""
    try:
        key = f"poda:latencia:{modalidade}"
        ts = int(time.time() * 1000)
        await rate_limiter.redis.zadd(key, {f"{ts}": float(ms)})
        await rate_limiter.redis.zremrangebyrank(key, 0, -501)
        await rate_limiter.redis.expire(key, 86400 * 7)
    except Exception:
        pass


# ── Erros ─────────────────────────────────────────────────────────────────────

async def registrar_erro(modalidade: str, tipo: str) -> None:
    """Registra ocorrência de erro por modalidade e tipo."""
    try:
        hoje = _hoje()
        await _incr(f"poda:erros:{modalidade}:{tipo}:{hoje}")
        await _incr(f"poda:erros:total:{hoje}")
    except Exception:
        pass


# ── Consultas agregadas ───────────────────────────────────────────────────────

async def obter_funil_hoje() -> dict:
    """Retorna dados do funil de conversão do dia atual."""
    hoje = _hoje()
    try:
        keys = [
            f"poda:funnel:limit_hit:{hoje}",
            f"poda:funnel:intent_total:{hoje}",
            f"poda:funnel:cpf_total:{hoje}",
            f"poda:funnel:pix_total:{hoje}",
            f"poda:funnel:paid_total:{hoje}",
        ]
        vals = await rate_limiter.redis.mget(*keys)
        limit_hit = int(vals[0] or 0)
        intent    = int(vals[1] or 0)
        cpf       = int(vals[2] or 0)
        pix       = int(vals[3] or 0)
        paid      = int(vals[4] or 0)
        abandono  = round((pix - paid) / pix * 100, 1) if pix > 0 else 0
        return {
            "limite_atingido":  limit_hit,
            "intent_upgrade":   intent,
            "cpf_informado":    cpf,
            "pix_gerado":       pix,
            "pago":             paid,
            "abandono_pct":     abandono,
        }
    except Exception:
        return {
            "limite_atingido": 0, "intent_upgrade": 0, "cpf_informado": 0,
            "pix_gerado": 0, "pago": 0, "abandono_pct": 0,
        }


async def obter_latencias() -> dict:
    """Retorna percentis P50 / P95 / P99 de latência por modalidade."""
    result = {}
    for mod in ("url", "pdf", "token"):
        try:
            key = f"poda:latencia:{mod}"
            entries = await rate_limiter.redis.zrange(key, 0, -1, withscores=True)
            if not entries:
                result[mod] = {"p50": None, "p95": None, "p99": None, "amostras": 0}
                continue
            scores = sorted(int(score) for _, score in entries)
            n = len(scores)

            def perc(p: int) -> int:
                return scores[min(int(n * p / 100), n - 1)]

            result[mod] = {
                "p50": perc(50),
                "p95": perc(95),
                "p99": perc(99),
                "amostras": n,
            }
        except Exception:
            result[mod] = {"p50": None, "p95": None, "p99": None, "amostras": 0}
    return result


async def obter_erros_hoje() -> dict:
    """Retorna contagem de erros do dia por modalidade e tipo."""
    hoje = _hoje()
    tipos_por_mod = {
        "url":   ["timeout", "parse_fail", "rate_limit"],
        "pdf":   ["too_large", "parse_fail", "timeout"],
        "token": ["overflow", "parse_fail"],
        "pix":   ["fail", "timeout"],
    }
    resultado: dict = {}
    total = 0
    try:
        for mod, tipos in tipos_por_mod.items():
            resultado[mod] = {}
            for tipo in tipos:
                val = await rate_limiter.redis.get(
                    f"poda:erros:{mod}:{tipo}:{hoje}"
                )
                n = int(val or 0)
                resultado[mod][tipo] = n
                total += n
    except Exception:
        pass
    resultado["total"] = total
    return resultado


async def calcular_mrr(
    assinantes_starter: int,
    assinantes_pro: int,
    assinantes_equipe: int,
    preco_starter: float = 9.0,
    preco_pro: float = 19.0,
    preco_equipe: float = 79.0,
) -> dict:
    """Calcula MRR e ARR a partir dos assinantes atuais (inclui Starter)."""
    mrr = (
        assinantes_starter * preco_starter
        + assinantes_pro * preco_pro
        + assinantes_equipe * preco_equipe
    )
    total_pagantes = assinantes_starter + assinantes_pro + assinantes_equipe
    return {
        "mrr":          round(mrr, 2),
        "arr":          round(mrr * 12, 2),
        "ticket_medio": round(mrr / total_pagantes, 2) if total_pagantes > 0 else 0.0,
        "total_pagantes": total_pagantes,
    }


async def reconciliar_assinantes() -> dict:
    """
    Conta assinantes por plano e remove dos sets quem já expirou
    (a chave poda:plano:{numero} some quando o TTL vence).
    Torna o painel autocorretivo e registra churn passivo.
    """
    contagem = {"starter": 0, "pro": 0, "equipe": 0}
    for plano in contagem:
        try:
            membros = await rate_limiter.redis.smembers(f"poda:assinantes:{plano}")
            for numero in membros or []:
                atual = await rate_limiter.redis.get(f"poda:plano:{numero}")
                if atual == plano:
                    contagem[plano] += 1
                else:
                    # Expirou ou mudou de plano — sai do set e conta churn se virou free
                    await rate_limiter.redis.srem(f"poda:assinantes:{plano}", numero)
                    if not atual:
                        await registrar_churn(numero, plano)
        except Exception:
            pass
    return contagem
