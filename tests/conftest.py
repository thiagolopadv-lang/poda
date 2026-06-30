"""
conftest.py — Fixtures compartilhadas para toda a suite de testes.
"""

import pytest
from unittest.mock import patch


@pytest.fixture(autouse=False)
def sem_redis():
    """Garante que o RateLimiter use memoria (sem Redis) durante os testes."""
    with patch("services.rate_limiter.settings") as mock_settings:
        mock_settings.REDIS_URL = ""
        yield mock_settings
