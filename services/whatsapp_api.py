"""
whatsapp_api.py — Cliente para a Meta WhatsApp Cloud API
Responsável por enviar mensagens e baixar mídias.
"""

import logging
import httpx

from config import settings

logger = logging.getLogger("poda.whatsapp_api")

BASE_URL = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}"
TIMEOUT = 30


async def enviar_texto(numero: str, mensagem: str) -> bool:
    """Envia uma mensagem de texto para um número do WhatsApp."""
    url = f"{BASE_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "text",
        "text": {"body": mensagem, "preview_url": False},
    }
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            logger.error(f"Erro ao enviar mensagem: {response.status_code} — {response.text}")
            return False

    logger.info(f"Mensagem enviada para {numero}")
    return True


async def enviar_arquivo_texto(numero: str, conteudo: str, nome_arquivo: str = "resultado.md") -> bool:
    """
    Envia conteúdo como arquivo de documento.
    Nota: A Meta API requer upload prévio da mídia para obter o media_id.
    Esta função usa envio via URL (link direto) — para MVP, enviar como texto truncado.
    TODO: Implementar upload de mídia via /media endpoint para Sprint 2+
    """
    # Por ora, enviar como texto truncado com aviso
    truncado = conteudo[:3_800]
    aviso = "\n\n_[Conteúdo truncado. Em breve: envio como arquivo .md]_"
    return await enviar_texto(numero, truncado + aviso)


async def marcar_como_lida(numero: str, message_id: str) -> None:
    """Marca a mensagem como lida (double-check azul)."""
    url = f"{BASE_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json=payload, headers=headers)


async def baixar_midia(media_id: str) -> bytes:
    """
    Baixa uma mídia (PDF) da Meta API e retorna os bytes.
    Fluxo: GET /media_id → URL temporária → GET URL → bytes
    """
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # 1. Obter URL temporária da mídia
        meta_response = await client.get(
            f"{BASE_URL}/{media_id}",
            headers=headers,
        )
        meta_response.raise_for_status()
        media_url = meta_response.json()["url"]

        # 2. Baixar o arquivo da URL temporária
        file_response = await client.get(media_url, headers=headers)
        file_response.raise_for_status()

    logger.info(f"Mídia {media_id} baixada: {len(file_response.content)} bytes")
    return file_response.content
