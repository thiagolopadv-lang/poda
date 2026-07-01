"""
services/pagamento.py — Integração PIX via Mercado Pago

Cria cobranças PIX e verifica status de pagamentos.
Fallback estático (chave PIX) quando MERCADOPAGO_ACCESS_TOKEN não está configurado.
"""

import logging
from typing import Optional

from config import settings

logger = logging.getLogger("poda.pagamento")

# Descrições dos planos
PLANOS = {
    "pro": {
        "nome": "Pro",
        "preco": settings.PLANO_PRO_PRECO,
        "descricao": f"Poda Pro — {settings.PLANO_DIAS} dias",
        "emoji": "⚡",
    },
    "equipe": {
        "nome": "Equipe",
        "preco": settings.PLANO_EQUIPE_PRECO,
        "descricao": f"Poda Equipe — {settings.PLANO_DIAS} dias",
        "emoji": "👥",
    },
}


def _sdk():
    """Retorna instância do SDK do Mercado Pago. None se não configurado."""
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        return None
    try:
        import mercadopago
        return mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
    except ImportError:
        logger.error("Pacote 'mercadopago' não instalado. Execute: pip install mercadopago")
        return None
    except Exception as e:
        logger.error(f"Erro ao inicializar SDK Mercado Pago: {e}")
        return None


async def criar_cobranca_pix(telefone: str, plano: str) -> dict:
    """
    Cria uma cobrança PIX no Mercado Pago.

    Retorna dict com:
        - sucesso: bool
        - tipo: "mercadopago" | "estatico"
        - pix_copia_cola: str (código PIX)
        - pix_qr_base64: str | None (imagem base64 do QR)
        - payment_id: str | None
        - valor: float
        - erro: str | None
    """
    if plano not in PLANOS:
        return {"sucesso": False, "erro": f"Plano inválido: {plano}"}

    info = PLANOS[plano]
    sdk = _sdk()

    # --- Mercado Pago ---
    if sdk:
        try:
            payment_data = {
                "transaction_amount": info["preco"],
                "description": info["descricao"],
                "payment_method_id": "pix",
                "payer": {
                    "email": f"poda_{telefone}@poda.bot",
                    "first_name": "Cliente",
                    "last_name": "Poda",
                    "identification": {
                        "type": "CPF",
                        "number": "00000000000",  # CPF genérico; usuário paga pelo QR/código
                    },
                },
                "metadata": {
                    "telefone": telefone,
                    "plano": plano,
                },
                "notification_url": f"{settings.BASE_URL}/api/pagamento/webhook"
                if settings.BASE_URL else None,
            }

            # Remove None values
            if not payment_data["notification_url"]:
                del payment_data["notification_url"]

            result = sdk.payment().create(payment_data)
            resp = result.get("response", {})

            if resp.get("status") in ("pending", "approved"):
                pix_info = resp.get("point_of_interaction", {}).get("transaction_data", {})
                return {
                    "sucesso": True,
                    "tipo": "mercadopago",
                    "pix_copia_cola": pix_info.get("qr_code", ""),
                    "pix_qr_base64": pix_info.get("qr_code_base64"),
                    "payment_id": str(resp.get("id", "")),
                    "valor": info["preco"],
                    "erro": None,
                }
            else:
                erro = resp.get("message", "Erro desconhecido no Mercado Pago")
                logger.error(f"Mercado Pago retornou erro: {erro}")
        except Exception as e:
            logger.error(f"Exceção ao criar cobrança Mercado Pago: {e}")

    # --- Fallback: chave PIX estática ---
    if settings.PIX_CHAVE:
        logger.info(f"Usando chave PIX estática para {telefone} plano {plano}")
        return {
            "sucesso": True,
            "tipo": "estatico",
            "pix_copia_cola": settings.PIX_CHAVE,
            "pix_qr_base64": None,
            "payment_id": None,
            "valor": info["preco"],
            "erro": None,
        }

    return {
        "sucesso": False,
        "erro": "Pagamento PIX não configurado. Configure MERCADOPAGO_ACCESS_TOKEN ou PIX_CHAVE.",
    }


async def verificar_pagamento(payment_id: str) -> Optional[dict]:
    """
    Verifica status de um pagamento no Mercado Pago.
    Retorna dict com status e metadata, ou None em caso de erro.
    """
    sdk = _sdk()
    if not sdk:
        return None
    try:
        result = sdk.payment().get(int(payment_id))
        resp = result.get("response", {})
        return {
            "status": resp.get("status"),
            "telefone": resp.get("metadata", {}).get("telefone"),
            "plano": resp.get("metadata", {}).get("plano"),
            "payment_id": payment_id,
        }
    except Exception as e:
        logger.error(f"Erro ao verificar pagamento {payment_id}: {e}")
        return None
