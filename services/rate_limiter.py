"""
rate_limiter.py — Controle de limites diários por usuário (plano free)

Armazena contagens em memória com reset automático à meia-noite (Brasília).
Para MVP: suficiente. Reseta com cada reinicialização do servidor.
Para produção futura: substituir pelo Redis.
"""

import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo
from collections import defaultdict
from config import settings

logger = logging.getLogger("poda.rate_limiter")

BRASILIA = ZoneInfo("America/Sao_Paulo")


class RateLimiter:
    """
    Controla uso diário por número de telefone.
    Estrutura: {numero: {"data": date, "urls": int, "pdfs": int}}
    """

    def __init__(self):
        self._contadores: dict[str, dict] = defaultdict(
            lambda: {"data": None, "urls": 0, "pdfs": 0}
        )

    def _hoje(self) -> date:
        return datetime.now(BRASILIA).date()

    def _resetar_se_necessario(self, numero: str) -> None:
        """Reseta o contador se mudou o dia."""
        hoje = self._hoje()
        if self._contadores[numero]["data"] != hoje:
            self._contadores[numero] = {"data": hoje, "urls": 0, "pdfs": 0}

    # ------------------------------------------------------------------ #
    # URLs                                                                 #
    # ------------------------------------------------------------------ #

    def pode_processar_url(self, numero: str) -> bool:
        """Retorna True se o usuário ainda tem URLs disponíveis hoje."""
        self._resetar_se_necessario(numero)
        return self._contadores[numero]["urls"] < settings.FREE_URL_LIMIT_PER_DAY

    def registrar_url(self, numero: str) -> None:
        """Registra uma URL processada."""
        self._resetar_se_necessario(numero)
        self._contadores[numero]["urls"] += 1
        logger.debug(
            f"[rate_limiter] {numero}: {self._contadores[numero]['urls']}"
            f"/{settings.FREE_URL_LIMIT_PER_DAY} URLs hoje"
        )

    def urls_restantes(self, numero: str) -> int:
        self._resetar_se_necessario(numero)
        usadas = self._contadores[numero]["urls"]
        return max(0, settings.FREE_URL_LIMIT_PER_DAY - usadas)

    def urls_usadas(self, numero: str) -> int:
        self._resetar_se_necessario(numero)
        return self._contadores[numero]["urls"]

    # ------------------------------------------------------------------ #
    # PDFs                                                                 #
    # ------------------------------------------------------------------ #

    def pode_processar_pdf(self, numero: str) -> bool:
        """Retorna True se o usuário ainda tem PDFs disponíveis hoje."""
        self._resetar_se_necessario(numero)
        return self._contadores[numero]["pdfs"] < settings.FREE_PDF_LIMIT_PER_DAY

    def registrar_pdf(self, numero: str) -> None:
        """Registra um PDF processado."""
        self._resetar_se_necessario(numero)
        self._contadores[numero]["pdfs"] += 1
        logger.debug(
            f"[rate_limiter] {numero}: {self._contadores[numero]['pdfs']}"
            f"/{settings.FREE_PDF_LIMIT_PER_DAY} PDFs hoje"
        )

    def pdfs_restantes(self, numero: str) -> int:
        self._resetar_se_necessario(numero)
        usados = self._contadores[numero]["pdfs"]
        return max(0, settings.FREE_PDF_LIMIT_PER_DAY - usados)

    def pdfs_usados(self, numero: str) -> int:
        self._resetar_se_necessario(numero)
        return self._contadores[numero]["pdfs"]

    # ------------------------------------------------------------------ #
    # Status completo (para comando /status)                               #
    # ------------------------------------------------------------------ #

    def status_usuario(self, numero: str) -> dict:
        """Retorna o status completo do usuário para exibição."""
        self._resetar_se_necessario(numero)
        c = self._contadores[numero]
        return {
            "urls_usadas": c["urls"],
            "urls_limite": settings.FREE_URL_LIMIT_PER_DAY,
            "urls_restantes": max(0, settings.FREE_URL_LIMIT_PER_DAY - c["urls"]),
            "pdfs_usados": c["pdfs"],
            "pdfs_limite": settings.FREE_PDF_LIMIT_PER_DAY,
            "pdfs_restantes": max(0, settings.FREE_PDF_LIMIT_PER_DAY - c["pdfs"]),
            "data": c["data"].strftime("%d/%m/%Y") if c["data"] else self._hoje().strftime("%d/%m/%Y"),
        }


# Instância global — singleton compartilhado em toda a aplicação
rate_limiter = RateLimiter()
