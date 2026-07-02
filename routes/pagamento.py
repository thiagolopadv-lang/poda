"""
routes/pagamento.py — Webhook e status de pagamento Asaas
"""
import logging
from fastapi import APIRouter, Request, HTTPException
from services.pagamento import criar_cobranca_pix, verificar_pagamento
from services.rate_limiter import rate_limiter
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pagamento", tags=["pagamento"])


@router.post("/webhook")
async def webhook_asaas(request: Request):
    """
    Recebe eventos do Asaas.
    Formato: {"event": "PAYMENT_RECEIVED", "payment": {"externalReference": "phone|plan", ...}}
    """
    # Validar token de autenticação do Asaas
    if settings.ASAAS_WEBHOOK_TOKEN:
        token = request.headers.get("access_token", "")
        if token != settings.ASAAS_WEBHOOK_TOKEN:
            logger.warning(f"Webhook Asaas rejeitado: token inválido")
            raise HTTPException(status_code=403, detail="Token inválido")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido")

    event = payload.get("event", "")
    payment = payload.get("payment", {})

    logger.info(f"Asaas webhook: event={event}, payment_id={payment.get('id')}")

    if event in ("PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"):
        external_ref = payment.get("externalReference", "")
        parts = external_ref.split("|")
        if len(parts) == 2:
            telefone, plano = parts
            await rate_limiter.set_plano(telefone, plano)
            logger.info(f"Plano {plano} ativado para {telefone}")
        else:
            logger.warning(f"externalReference inválido: {external_ref}")

    return {"status": "ok"}


@router.get("/status/{payment_id}")
async def status_pagamento(payment_id: str):
    """Consulta status de um pagamento no Asaas."""
    status = await verificar_pagamento(payment_id)
    return {"payment_id": payment_id, "status": status}


@router.post("/criar")
async def criar_pagamento(request: Request):
    """Cria cobrança PIX para um telefone e plano."""
    body = await request.json()
    telefone = body.get("telefone")
    plano = body.get("plano", "pro")

    if not telefone:
        raise HTTPException(status_code=400, detail="telefone obrigatório")

    cobranca = await criar_cobranca_pix(telefone, plano)
    return cobranca
