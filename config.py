"""
config.py â VariÃ¡veis de ambiente e configuraÃ§Ãµes globais
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

    # Limites do plano Free (por nÃºmero de telefone por dia)
    FREE_URL_LIMIT_PER_DAY: int = 5
    FREE_PDF_LIMIT_PER_DAY: int = 2

    # Monitoramento de erros
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")

    # Taxa de cÃ¢mbio USD â BRL (fixada ou atualizada via env)
    USD_TO_BRL: float = float(os.getenv("USD_TO_BRL", "5.70"))

    # Redis (para rate limiter persistente entre deploys)
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    DASHBOARD_TOKEN: str = os.getenv("DASHBOARD_TOKEN", "poda_dash_2024")


settings = Settings()
