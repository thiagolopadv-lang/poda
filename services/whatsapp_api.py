"""
whatsapp_api.py — Cliente para a Meta WhatsApp Cloud API
Responsável por enviar mensagens, fazer upload de mídias e baixar arquivos.
"""

import logging
import httpx
from services import metrics

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
    await metrics.registrar_mensagem_enviada()
    return True


async def enviar_arquivo_texto(numero: str, conteudo: str, nome_arquivo: str = "resultado.md") -> bool:
    """
    Envia conteúdo como arquivo de documento via WhatsApp Cloud API.
    Fluxo:
      1. Upload de mídia em /media (multipart/form-data)
      2. Envio de mensagem do tipo "document" com o media_id retornado
    Fallback: se o upload falhar, envia como texto truncado.
    """
    url_base = f"{BASE_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}"
    headers_auth = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}

    conteudo_bytes = conteudo.encode("utf-8")

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # 1. Upload da mídia
        upload_response = await client.post(
            f"{url_base}/media",
            headers=headers_auth,
            data={"messaging_product": "whatsapp"},
            files={"file": (nome_arquivo, conteudo_bytes, "text/plain")},
        )

        if upload_response.status_code != 200:
            logger.error(
                f"Erro no upload de mídia: {upload_response.status_code} — {upload_response.text}"
            )
            # Fallback: enviar como texto truncado com aviso
            truncado = conteudo[:3_800]
            aviso = "\n\n_[Conteúdo truncado. Erro no envio do arquivo .md]_"
            return await enviar_texto(numero, truncado + aviso)

        media_id = upload_response.json()["id"]
        logger.info(f"Upload concluído: media_id={media_id}, arquivo={nome_arquivo}")

        # 2. Enviar mensagem com documento
        doc_response = await client.post(
            f"{url_base}/messages",
            headers={**headers_auth, "Content-Type": "application/json"},
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": numero,
                "type": "document",
                "document": {
                    "id": media_id,
                    "filename": nome_arquivo,
                    "caption": "Aqui está o conteúdo completo em Markdown. Abra e copie para o seu LLM.",
                },
            },
        )

        if doc_response.status_code != 200:
            logger.error(
                f"Erro ao enviar documento: {doc_response.status_code} — {doc_response.text}"
            )
            return False

    logger.info(f"Arquivo {nome_arquivo} enviado para {numero}")
    return True


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
    Fluxo: GET /media_id -> URL temporária -> GET URL -> bytes
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
