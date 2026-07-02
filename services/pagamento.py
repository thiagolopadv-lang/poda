"""
services/pagamento.py — Integração PIX via Asaas
"""
import httpx
from datetime import date, timedelta
from config import settings

ASAAS_BASE_URL = "https://api.asaas.com/v3"


def _headers() -> dict:
    return {
        "access_token": settings.ASAAS_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }


async def _get_ou_criar_cliente(telefone: str) -> str:
    """Busca ou cria cliente no Asaas pelo telefone."""
    async with httpx.AsyncClient(timeout=20) as client:
        # Buscar cliente existente
        resp = await client.get(
            f"{ASAAS_BASE_URL}/customers",
            headers=_headers(),
            params={"mobilePhone": telefone},
        )
        data = resp.json()
        if data.get("data"):
            return data["data"][0]["id"]

        # Criar novo cliente
        resp = await client.post(
            f"{ASAAS_BASE_URL}/customers",
            headers=_headers(),
            json={
                "name": f"Cliente {telefone}",
                "mobilePhone": telefone,
            },
        )
        return resp.json()["id"]


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

    customer_id = await _get_ou_criar_cliente(telefone)

    async with httpx.AsyncClient(timeout=20) as client:
        vencimento = (date.today() + timedelta(days=1)).isoformat()

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
        payment = resp.json()
        payment_id = payment["id"]

        # Buscar QR code PIX
        qr_resp = await client.get(
            f"{ASAAS_BASE_URL}/payments/{payment_id}/pixQrCode",
            headers=_headers(),
        )
        qr_data = qr_resp.json()

        return {
            "payment_id": payment_id,
            "qr_code": qr_data.get("payload", ""),
            "qr_code_image": qr_data.get("encodedImage", ""),
            "valor": valor,
            "expira_em": vencimento,
        }


async def verificar_pagamento(payment_id: str) -> str:
    """Verifica status de pagamento no Asaas. Retorna 'RECEIVED', 'PENDING', etc."""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{ASAAS_BASE_URL}/payments/{payment_id}",
            headers=_headers(),
        )
        data = resp.json()
        return data.get("status", "UNKNOWN")
