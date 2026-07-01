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

    # Limites do plano Pro (por número de telefone por dia)
    PRO_URL_LIMIT_PER_DAY: int = 50
    PRO_PDF_LIMIT_PER_DAY: int = 20

    # Monitoramento de erros
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")

    # Taxa de câmbio USD → BRL (fixada ou atualizada via cron)
    USD_BRL: float = 5.0

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "")

    # Dashboard
    DASHBOARD_TOKEN: str = os.getenv("DASHBOARD_TOKEN", "poda_dash_2024")

    # ---------------------------------------------------------------
    # Pagamentos via Mercado Pago (PIX)
    # ---------------------------------------------------------------
    MERCADOPAGO_ACCESS_TOKEN: str = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")

    # Chave PIX para fallback (estática) — email, CPF, telefone ou aleatória
    PIX_CHAVE: str = os.getenv("PIX_CHAVE", "")
    PIX_BENEFICIARIO: str = os.getenv("PIX_BENEFICIARIO", "Poda")

    # Preços dos planos (em reais)
    PLANO_PRO_PRECO: float = 19.00
    PLANO_EQUIPE_PRECO: float = 79.00

    # Duração dos planos (em dias)
    PLANO_DIAS: int = 30

    # URL base do webhook (Railway)
    BASE_URL: str = os.getenv("BASE_URL", "")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
