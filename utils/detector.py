"""
detector.py -- Detecta o tipo de conteudo enviado pelo usuario
"""

import re
from enum import Enum


class ContentType(str, Enum):
    URL = "url"
    PDF = "pdf"
    TEXT = "text"
    UNSUPPORTED = "unsupported"


# Regex para detectar URLs (http:// ou https://)
URL_PATTERN = re.compile(
    r"https?://"
    r"(?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}"
    r"(?:/[^\s]*)?"
)

# Tipos de mensagem do WhatsApp nao suportados
TIPOS_BLOQUEADOS = {
    "image", "audio", "video", "sticker",
    "reaction", "location", "contacts"
}


def detectar_tipo(message: dict) -> ContentType:
    """
    Recebe o objeto de mensagem do WhatsApp e retorna o tipo de conteudo.
    """
    msg_type = message.get("type", "")

    # Documento PDF enviado diretamente
    if msg_type == "document":
        doc = message.get("document", {})
        mime = doc.get("mime_type", "")
        if mime == "application/pdf":
            return ContentType.PDF
        return ContentType.UNSUPPORTED

    # Mensagem de texto: verificar se contem URL
    if msg_type == "text":
        body = message.get("text", {}).get("body", "")
        if URL_PATTERN.search(body):
            return ContentType.URL
        return ContentType.TEXT

    # Imagem, audio, video, sticker, reacao, localizacao
    blocked = msg_type in TIPOS_BLOQUEADOS
    if blocked:
        return ContentType.UNSUPPORTED

    return ContentType.UNSUPPORTED


def extrair_url(body: str) -> str | None:
    """Extrai a primeira URL encontrada no corpo da mensagem."""
    match = URL_PATTERN.search(body)
    return match.group(0) if match else None
