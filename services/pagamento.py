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
    token = settings.ASAAS_ACCESS_TOKEN
    if token and not token.startswith("$"):
        token = "$" + token
    return {
        "access_token": token,
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


async def _get_ou_criar_cliente(
    telefone: str, client: httpx.AsyncClient, cpf_cnpj: str = ""
) -> str:
    """Busca ou cria cliente no Asaas pelo telefone. Atualiza CPF/CNPJ se necessário."""
    fone = "".join(c for c in telefone if c.isdigit())

    resp = await client.get(
        f"{ASAAS_BASE_URL}/customers",
        headers=_headers(),
        params={"mobilePhone": fone},
    )
    data = resp.json()
    if data.get("data"):
        customer = data["data"][0]
        customer_id = customer["id"]
        logger.info(f"Cliente Asaas encontrado: {customer_id}")

        # Atualizar CPF/CNPJ se o cliente existente não tiver
        if cpf_cnpj and not customer.get("cpfCnpj"):
            await client.put(
                f"{ASAAS_BASE_URL}/customers/{customer_id}",
                headers=_headers(),
                json={"cpfCnpj": cpf_cnpj},
            )
            logger.info(f"CPF/CNPJ atualizado no cliente {customer_id}")

        return customer_id

    # Criar novo cliente com CPF/CNPJ
    payload: dict = {
        "name": f"WhatsApp {fone}",
        "mobilePhone": fone,
        "notificationDisabled": True,
    }
    if cpf_cnpj:
        payload["cpfCnpj"] = cpf_cnpj

    resp = await client.post(
        f"{ASAAS_BASE_URL}/customers",
        headers=_headers(),
        json=payload,
    )
    cliente = _assert_ok(resp, "criar_cliente")
    logger.info(f"Cliente Asaas criado: {cliente['id']}")
    return cliente["id"]


async def criar_cobranca_pix(
    telefone: str, plano: str, cpf_cnpj: str = ""
) -> dict:
    """
    Cria cobrança PIX no Asaas.
    Retorna: {payment_id, pix_copia_cola, qr_code_image, preco, expira_em}
    """
    precos = {
        "starter": settings.PLANO_STARTER_PRECO,
        "pro": settings.PLANO_PRO_PRECO,
        "equipe": settings.PLANO_EQUIPE_PRECO,
    }
    valor = precos.get(plano.lower(), settings.PLANO_PRO_PRECO)
    vencimento = (date.today() + timedelta(days=1)).isoformat()

    async with httpx.AsyncClient(timeout=30) as client:
        customer_id = await _get_ou_criar_cliente(telefone, client, cpf_cnpj)

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
        return resp.json().get("status", "UNKNOWN")
