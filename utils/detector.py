"""
detector.py — Detecta o tipo de conteúdo enviado pelo usuário
"""

import re
from enum import Enum


class ContentType(str, Enum):
    URL = "url"
    PDF = "pdf"
    TEXT = "text"


# Regex para detectar URLs (http:// ou https://)
URL_PATTERN = re.compile(
    r"https?://"
    r"(?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}"
    r"(?:/[^\s]*)?"
)


def detectar_tipo(message: dict) -> ContentType:
    """
    Recebe o objeto de mensagem do WhatsApp e retorna o tipo de conteúdo.

    Estrutura do objeto message da Meta API:
    {
      "type": "text" | "document" | "image" | ...,
      "text": {"body": "..."},
      "document": {"mime_type": "application/pdf", "id": "..."}
    }
    """
    msg_type = message.get("type", "")

    # Documento PDF enviado diretamente
    if msg_type == "document":
        doc = message.get("document", {})
        mime = doc.get("mime_type", "")
        if mime == "application/pdf":
            return ContentType.PDF
        # Outros documentos: tratar como texto (não suportado)
        return ContentType.TEXT

    # Mensagem de texto: verificar se contém URL
    if msg_type == "text":
        body = message.get("text", {}).get("body", "")
        if URL_PATTERN.search(body):
            return ContentType.URL
        return ContentType.TEXT

    # Tipo não suportado (imagem, áudio, vídeo, etc.)
    return ContentType.TEXT


def extrair_url(body: str) -> str | None:
    """Extrai a primeira URL encontrada no corpo da mensagem."""
    match = URL_PATTERN.search(body)
    return match.group(0) if match else None


def extrair_urls(body: str) -> list[str]:
    """Extrai todas as URLs encontradas no corpo da mensagem."""
    return URL_PATTERN.findall(body)
