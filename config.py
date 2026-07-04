"""
config.py â VariÃ¡veis de ambiente e configuraÃ§Ãµes globais
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # WhatsApp / Meta
    WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")  # OBRIGATÓRIO: defina no Railway
    WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_API_VERSION: str = "v19.0"
    WHATSAPP_APP_SECRET: str = os.getenv("WHATSAPP_APP_SECRET", "")  # segredo do App Meta — obrigatório para validação de assinatura

    # Jina Reader
    JINA_API_KEY: str = os.getenv("JINA_API_KEY", "")

    # Firecrawl (fallback)
    FIRECRAWL_API_KEY: str = os.getenv("FIRECRAWL_API_KEY", "")

    # LlamaParse (fallback premium para PDFs complexos)
    LLAMA_CLOUD_API_KEY: str = os.getenv("LLAMA_CLOUD_API_KEY", "")

    # Limites do plano Free (por nÃºmero de telefone por dia)
    FREE_URL_LIMIT_PER_DAY: int = 5
    FREE_PDF_LIMIT_PER_DAY: int = 2

    # Limites do plano Pro (por nÃºmero de telefone por dia)
    STARTER_URL_LIMIT_PER_DAY: int = 15
    PRO_URL_LIMIT_PER_DAY: int = 50
    STARTER_PDF_LIMIT_PER_DAY: int = 8
    PRO_PDF_LIMIT_PER_DAY: int = 20

    # Monitoramento de erros
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")

    # Taxa de cÃ¢mbio USD â BRL (fixada ou atualizada via cron)
    USD_BRL: float = 5.0

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    # CRÍTICA-2 / LGPD Art. 46: chave para criptografar CPF/CNPJ em repouso no Redis.
    # Gere com: python -c "import secrets; print(secrets.token_urlsafe(32))"
    # OBRIGATÓRIO — configure no Railway antes de subir em produção.
    REDIS_ENCRYPT_KEY: str = os.getenv("REDIS_ENCRYPT_KEY", "")

    # Dashboard
    # Credenciais de acesso ao painel (usuário + senha separados)
    # Configure no Railway: DASHBOARD_USER=admin  DASHBOARD_PASSWORD=sua_senha_segura
    DASHBOARD_USER: str = os.getenv("DASHBOARD_USER", "")
    DASHBOARD_PASSWORD: str = os.getenv("DASHBOARD_PASSWORD", "")
    # Mantido para compatibilidade — será ignorado se DASHBOARD_USER estiver configurado
    DASHBOARD_TOKEN: str = os.getenv("DASHBOARD_TOKEN", "")

    # ---------------------------------------------------------------
    # Pagamentos via Asaas (PIX)
    # ---------------------------------------------------------------
    ASAAS_ACCESS_TOKEN: str = os.getenv("ASAAS_ACCESS_TOKEN", "")

    # Token secreto para validar requisições do webhook Asaas
    WEBHOOK_ASAAS_TOKEN: str = os.getenv("WEBHOOK_ASAAS_TOKEN", "")

    # NOTA: ASAAS_WEBHOOK_TOKEN removido — duplicata de WEBHOOK_ASAAS_TOKEN

    # Chave PIX estÃ¡tica â email, CPF, telefone ou aleatÃ³ria
    PIX_CHAVE: str = os.getenv("PIX_CHAVE", "")
    PIX_BENEFICIARIO: str = os.getenv("PIX_BENEFICIARIO", "Poda")

    # PreÃ§os dos planos (em reais)
    PLANO_STARTER_PRECO: float = 9.00
    PLANO_PRO_PRECO: float = 19.00
    PLANO_EQUIPE_PRECO: float = 79.00

    # DuraÃ§Ã£o dos planos (em dias)
    PLANO_DIAS: int = 30

    # Número público do WhatsApp (exibido no frontend)
    WHATSAPP_PUBLIC_NUMBER: str = os.getenv("WHATSAPP_PUBLIC_NUMBER", "5511955020393")

    # URL base do webhook (Railway)
    BASE_URL: str = os.getenv("BASE_URL", "")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
