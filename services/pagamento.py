"""
services/pagamento.py — Integração PIX via Asaas
"""
import logging
import httpx
from datetime import date, timedelta
from config import settings

logger = logging.getLogger(__name__)

ASAAS_BASE_URL = "https://api.asaas.com/v3"


def _headers() -> dict:
    return {
        "access_token": settings.ASAAS_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }


def _assert_ok(resp: httpx.Response, contexto: str) -> dict:
    """Lança exceção detalhada se a resposta Asaas indicar erro."""
    data = resp.json()
    if resp.status_code >= 400 or "errors" in data:
        erros = data.get("errors", [{"description": str(data)}])
        msgs = "; ".join(e.get("description", str(e)) for e in erros)
        raise ValueError(f"Asaas [{contexto}] HTTP {resp.status_code}: {msgs}")
    return data


async def _get_ou_criar_cliente(telefone: str, client: httpx.AsyncClient) -> str:
    """Busca ou cria cliente no Asaas pelo telefone."""
    # Normalizar telefone: apenas dígitos
    fone = "".join(c for c in telefone if c.isdigit())

    # Buscar cliente existente pelo telefone
    resp = await client.get(
        f"{ASAAS_BASE_URL}/customers",
        headers=_headers(),
        params={"mobilePhone": fone},
    )
    data = resp.json()
    if data.get("data"):
        logger.info(f"Cliente Asaas encontrado: {data['data'][0]['id']}")
        return data["data"][0]["id"]

    # Criar novo cliente (cpfCnpj opcional — Asaas aceita sem ele)
    resp = await client.post(
        f"{ASAAS_BASE_URL}/customers",
        headers=_headers(),
        json={
            "name": f"WhatsApp {fone}",
            "mobilePhone": fone,
            "notificationDisabled": True,
        },
    )
    cliente = _assert_ok(resp, "criar_cliente")
    logger.info(f"Cliente Asaas criado: {cliente['id']}")
    return cliente["id"]


async def criar_cobranca_pix(telefone: str, plano: str) -> dict:
    """
    Cria cobrança PIX no Asaas.
    Retorna: {payment_id, qr_code, qr_code_image, valor, expira_em}
    """
    precos = {
        "pro": settings.PLANO_PRO_PRECO,
        "equipe": settings.PLANO_EQUIPE_PRECO,
    }
    valor = precos.get(plano.lower(), settings.PLANO_PRO_PRECO)
    vencimento = (date.today() + timedelta(days=1)).isoformat()

    async with httpx.AsyncClient(timeout=30) as client:
        customer_id = await _get_ou_criar_cliente(telefone, client)

        # Criar cobrança PIX
        resp = await client.post(
            f"{ASAAS_BASE_URL}/payments",
            headers=_headers(),
            json={
                "customer": customer_id,
                "billingType": "PIX",
                "value": valor,
                "dueDate": vencimento,
                "description": f"Assinatura Poda — Plano {plano.title()}",
                "externalReference": f"{telefone}|{plano}",
            },
        )
        payment = _assert_ok(resp, "criar_cobranca")
        payment_id = payment["id"]
        logger.info(f"Cobrança Asaas criada: {payment_id}")

        # Buscar QR code PIX
        qr_resp = await client.get(
            f"{ASAAS_BASE_URL}/payments/{payment_id}/pixQrCode",
            headers=_headers(),
        )
        qr_data = _assert_ok(qr_resp, "pixQrCode")

        return {
            "payment_id": payment_id,
            "pix_copia_cola": qr_data.get("payload", ""),
            "qr_code_image": qr_data.get("encodedImage", ""),
            "preco": valor,
            "expira_em": vencimento,
        }


async def verificar_pagamento(payment_id: str) -> str:
    """Verifica status de pagamento no Asaas."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{ASAAS_BASE_URL}/payments/{payment_id}",
            headers=_headers(),
        )
        data = resp.json()
        return data.get("status", "UNKNOWN")
