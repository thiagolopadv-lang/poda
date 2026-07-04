"""
routes/pagamento.py — Webhook e status de pagamento Asaas
"""
import hmac as _hmac
import logging
from fastapi import APIRouter, Request, HTTPException
from services.pagamento import criar_cobranca_pix, verificar_pagamento
from services.rate_limiter import rate_limiter
from services.whatsapp_api import enviar_texto
from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pagamento", tags=["pagamento"])

from config import settings as _settings

NOMES_PLANO = {
    "pro": "Pro ⚡",
    "equipe": "Equipe 👥",
}

def _limites_plano() -> dict:
    return {
        "pro": f"{_settings.PRO_URL_LIMIT_PER_DAY} URLs/dia · {_settings.PRO_PDF_LIMIT_PER_DAY} PDFs/dia",
        "equipe": "Uso ilimitado · até 5 usuários",
    }

LIMITES_PLANO = _limites_plano()


@router.post("/webhook")
async def webhook_asaas(request: Request):
    """
    Recebe eventos do Asaas.
    Autenticação: token Bearer no header Authorization ou query param ?token=
    Formato: {"event": "PAYMENT_RECEIVED", "payment": {"externalReference": "phone|plan", ...}}
    """
    # — Validação de segurança (CRÍTICA-1 fix) —
    secret = settings.WEBHOOK_ASAAS_TOKEN
    # Fail-secure: bloquear SEMPRE se token não configurado (nunca pular validação)
    if not secret:
        logger.error(
            "WEBHOOK_ASAAS_TOKEN nao configurado — requisicao bloqueada por seguranca. "
            "Configure a variavel de ambiente no Railway IMEDIATAMENTE."
        )
        raise HTTPException(status_code=503, detail="Servico temporariamente indisponivel")
    # Aceitar token apenas via header Authorization (nunca via query param — evita log de token)
    auth_header = request.headers.get("Authorization", "")
    token_recebido = auth_header.replace("Bearer ", "").strip()
    # Comparacao em tempo constante — evita timing attack
    if not _hmac.compare_digest(token_recebido, secret):
        logger.warning("Webhook Asaas rejeitado: token invalido")
        raise HTTPException(status_code=401, detail="Token invalido")

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
            # CRÍTICA-1 fix: validar plano antes de ativar — evita ativacao de planos arbitrarios
            if plano not in ("pro", "equipe"):
                logger.warning("Webhook Asaas: plano invalido recebido: %r — ignorado.", plano)
                return {"status": "ignored"}
            await rate_limiter.set_plano(telefone, plano)
            logger.info("Plano ativado: sufixo=%s", telefone[-4:] if len(telefone) > 4 else "****")

            # Notificar o usuário via WhatsApp
            nome_plano = NOMES_PLANO.get(plano, plano.title())
            limites = LIMITES_PLANO.get(plano, "")
            mensagem = (
                f"✅ *Pagamento confirmado!*\n\n"
                f"Seu plano *{nome_plano}* está ativo agora.\n\n"
                f"📊 Seus novos limites:\n"
                f"   {limites}\n\n"
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
async def status_pagamento(payment_id: str, request: Request):
    """
    Consulta status de um pagamento no Asaas.
    Requer o mesmo token Bearer do webhook Asaas para evitar enumeracao.
    """
    # CRITICA-1 fix: mesma logica fail-secure do webhook
    secret = settings.WEBHOOK_ASAAS_TOKEN
    if not secret:
        raise HTTPException(status_code=503, detail="Servico temporariamente indisponivel")
    auth_header = request.headers.get("Authorization", "")
    token_recebido = auth_header.replace("Bearer ", "").strip()
    if not _hmac.compare_digest(token_recebido, secret):
        raise HTTPException(status_code=401, detail="Token invalido")
    status = await verificar_pagamento(payment_id)
    return {"payment_id": payment_id, "status": status}


# POST /criar foi REMOVIDO por seguranca (OWASP A01 - Broken Access Control).
# A criacao de cobracas PIX e acionada exclusivamente pelo fluxo interno
# do webhook WhatsApp (routes/whatsapp.py -> _processar_comando -> /assinar).
