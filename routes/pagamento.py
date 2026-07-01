"""
routes/pagamento.py — Webhook e endpoints de pagamento PIX (Mercado Pago)
"""

import logging
from fastapi import APIRouter, Request, HTTPException, Query
from services.pagamento import verificar_pagamento
from services.rate_limiter import rate_limiter
from config import settings

logger = logging.getLogger("poda.pagamento")
router = APIRouter()


@router.post("/api/pagamento/webhook")
async def webhook_pagamento(request: Request):
    """
    Webhook do Mercado Pago.
    Ativado quando um pagamento PIX é aprovado.
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido")

    tipo = data.get("type") or data.get("action", "")
    if tipo not in ("payment", "payment.updated"):
        return {"status": "ignorado", "tipo": tipo}

    payment_id = None
    if "data" in data and "id" in data["data"]:
        payment_id = str(data["data"]["id"])
    elif "id" in data:
        payment_id = str(data["id"])

    if not payment_id:
        logger.warning("Webhook sem payment_id: %s", data)
        return {"status": "sem_id"}

    resultado = await verificar_pagamento(payment_id)
    if not resultado:
        logger.info("Pagamento %s não encontrado ou não aprovado", payment_id)
        return {"status": "nao_aprovado", "payment_id": payment_id}

    status_pag = resultado.get("status", "")
    if status_pag != "approved":
        logger.info("Pagamento %s com status %s", payment_id, status_pag)
        return {"status": status_pag, "payment_id": payment_id}

    telefone = resultado.get("telefone", "")
    plano = resultado.get("plano", "")

    if not telefone or plano not in ("pro", "equipe"):
        logger.warning("Webhook com dados inválidos: telefone=%s plano=%s", telefone, plano)
        return {"status": "dados_invalidos"}

    await rate_limiter.set_plano(telefone, plano, dias=settings.PLANO_DIAS)
    logger.info("Plano %s ativado para %s via webhook", plano, telefone)

    try:
        from services.whatsapp_sender import enviar_texto
        emoji = "⚡" if plano == "pro" else "👥"
        nome_plano = "Pro" if plano == "pro" else "Equipe"
        mensagem = (
            f"{emoji} *Pagamento confirmado!*\n\n"
            f"Seu plano *{nome_plano}* foi ativado com sucesso por {settings.PLANO_DIAS} dias.\n\n"
            f"Aproveite seus novos limites! Digite */status* para conferir."
        )
        await enviar_texto(telefone, mensagem)
    except Exception as e:
        logger.warning("Erro ao enviar confirmação WhatsApp: %s", e)

    return {"status": "ok", "plano": plano, "telefone": telefone}


@router.get("/api/pagamento/status")
async def status_pagamento(
    numero: str = Query(..., description="Número WhatsApp"),
    token: str = Query(..., description="Token interno"),
):
    """
    Endpoint interno para consultar plano de um número.
    """
    if token != settings.WEBHOOK_TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido")

    info = await rate_limiter.status_usuario(numero)
    return info
