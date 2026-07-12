"""
routes/pagamento.py — Webhook e status de pagamento Asaas
"""
import logging
from fastapi import APIRouter, Request, HTTPException
from services.pagamento import criar_cobranca_pix, verificar_pagamento
from services.rate_limiter import rate_limiter
from services.whatsapp_api import enviar_texto
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pagamento", tags=["pagamento"])

NOMES_PLANO = {
    "starter": "Starter 🌿",
    "pro": "Pro ⚡",
    "equipe": "Equipe 👥",
}

LIMITES_PLANO = {
    "starter": "15 URLs/dia · 8 PDFs/dia",
    "pro": "50 URLs/dia · 20 PDFs/dia",
    "equipe": "Uso ilimitado · até 5 usuários",
}


@router.post("/webhook")
async def webhook_asaas(request: Request):
    """
    Recebe eventos do Asaas.
    Autenticação: token Bearer no header Authorization ou query param ?token=
    Formato: {"event": "PAYMENT_RECEIVED", "payment": {"externalReference": "phone|plan", ...}}
    """
    # — Validação de segurança —
    secret = settings.WEBHOOK_ASAAS_TOKEN
    if secret:
        auth_header = request.headers.get("Authorization", "")
        token_query = request.query_params.get("token", "")
        token_recebido = auth_header.replace("Bearer ", "").strip() or token_query
        if token_recebido != secret:
            logger.warning(f"Webhook Asaas rejeitado: token inválido")
            raise HTTPException(status_code=401, detail="Token inválido")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido")

    event = payload.get("event", "")
    payment = payload.get("payment", {})

    logger.info(f"Asaas webhook: event={event}, payment_id={payment.get('id')}")

    if event == "PAYMENT_RECEIVED":
        external_ref = payment.get("externalReference", "")
        parts = external_ref.split("|")
        if len(parts) == 2:
            telefone, plano = parts
            plano = plano.lower().strip()

            if plano not in NOMES_PLANO:
                logger.warning(f"Plano desconhecido no webhook: {plano}")
                return {"status": "ok"}

            # Idempotência: webhook pode ser reenviado pelo Asaas.
            # Sem isso, cada reenvio somaria +30 dias ao plano.
            payment_id = payment.get("id", "")
            if payment_id:
                try:
                    chave_dedup = f"poda:pagamento_processado:{payment_id}"
                    if await rate_limiter.redis.get(chave_dedup):
                        logger.info(f"Pagamento {payment_id} já processado — ignorando.")
                        return {"status": "ok"}
                    await rate_limiter.redis.setex(chave_dedup, 90 * 86400, "1")
                except Exception as e:
                    logger.warning(f"Dedup indisponível para {payment_id}: {e}")

            await rate_limiter.set_plano(telefone, plano)
            try:
                from services.metricas_comerciais import registrar_pagamento_confirmado
                await registrar_pagamento_confirmado(telefone, plano)
            except Exception as e:
                logger.warning(f"Erro ao registrar funil de pagamento: {e}")
            logger.info(f"Plano {plano} ativado para {telefone}")

            # Notificar o usuário via WhatsApp
            nome_plano = NOMES_PLANO.get(plano, plano.title())
            limites = LIMITES_PLANO.get(plano, "")
            mensagem = (
                f"✅ *Pagamento confirmado!*\n\n"
                f"Seu plano *{nome_plano}* está ativo agora.\n\n"
                f"📊 Seus novos limites:\n"
                f"   {limites}\n\n"
                f"⏳ Validade: {settings.PLANO_DIAS} dias\n"
                f"_Use /status a qualquer momento para acompanhar._\n\n"
                f"Pode mandar a primeira URL ou PDF! 🌿"
            )
            try:
                await enviar_texto(telefone, mensagem)
                logger.info(f"Notificação enviada para {telefone}")
            except Exception as e:
                logger.error(f"Erro ao notificar {telefone}: {e}")
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
