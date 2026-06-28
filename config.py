"""
config.py — Variáveis de ambiente e configurações globais
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # WhatsApp / Meta
    WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "poda_verify_secret")
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_API_VERSION: str = "v19.0"

    # Jina Reader
    JINA_API_KEY: str = os.getenv("JINA_API_KEY", "")

    # Firecrawl (fallback)
    FIRECRAWL_API_KEY: str = os.getenv("FIRECRAWL_API_KEY", "")

    # LlamaParse (fallback premium para PDFs complexos)
    LLAMA_CLOUD_API_KEY: str = os.getenv("LLAMA_CLOUD_API_KEY", "")

    # Limites do plano Free (por número de telefone por dia)
    FREE_URL_LIMIT_PER_DAY: int = 5
    FREE_PDF_LIMIT_PER_DAY: int = 2

    # Taxa de câmbio USD → BRL (fixada ou atualizada via BACEN)
    USD_TO_BRL: float = float(os.getenv("USD_TO_BRL", "5.70"))

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
