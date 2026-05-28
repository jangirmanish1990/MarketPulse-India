"""Application-level settings and shared constants for MarketPulse India."""

from __future__ import annotations

import json
import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

SEBI_DISCLAIMER = (
    "⚠️ MarketPulse India is not a SEBI-registered investment advisor. "
    "Output is for educational/informational purposes only and is not "
    "investment advice. Markets carry risk; consult a registered advisor "
    "before making decisions."
)


def get_market_status() -> str:
    """Return NSE market status based on current IST time."""
    now = datetime.now(IST)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return "CLOSED"
    t = now.time()
    if time(9, 0) <= t < time(9, 15):
        return "PRE_OPEN"
    if time(9, 15) <= t <= time(15, 30):
        return "OPEN"
    if time(15, 30) < t <= time(16, 0):
        return "POST_CLOSE"
    return "CLOSED"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "MarketPulse India"
    version: str = "0.1.0"
    debug: bool = False
    app_env: str = "local"  # local | dev | staging | production

    # Database
    database_url: str = ""
    redis_url: str = "redis://localhost:6379"

    # OpenAI
    openai_api_key: str = ""

    # LangSmith
    langchain_api_key: str = ""
    langchain_tracing_v2: bool = True
    langchain_project: str = "marketpulse-india"

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # AWS
    aws_region: str = "ap-south-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # Secrets Manager — set to the secret name/ARN in production ECS task def
    aws_secrets_name: str = ""

    # Rate limiting
    rate_limit_analyses_per_day: int = 100

    # Webhook
    webhook_secret: str = "marketpulse-webhook-secret-2026"


# ---------------------------------------------------------------------------
# AWS Secrets Manager loader
# ---------------------------------------------------------------------------

def _fetch_secret_json(secret_name: str, region: str) -> dict[str, str]:
    """Fetch and parse a JSON secret from AWS Secrets Manager.

    Returns an empty dict on any error so the caller can decide whether to
    abort or fall back to env-var defaults.
    """
    try:
        import boto3  # type: ignore[import-untyped]

        client = boto3.client("secretsmanager", region_name=region)
        resp = client.get_secret_value(SecretId=secret_name)
        raw = resp.get("SecretString", "{}")
        return dict(json.loads(raw))
    except Exception as exc:
        logger.warning("Secrets Manager fetch failed (%s): %s", secret_name, exc)
        return {}


def load_production_secrets(s: Settings) -> None:
    """Overlay Settings fields with values from AWS Secrets Manager.

    Called once from the FastAPI lifespan when ``app_env == 'production'``
    and ``aws_secrets_name`` is set.  Mutates *s* in-place — intentionally
    not thread-safe (call before the server starts accepting requests).

    Secret JSON shape (all keys optional — only present keys are applied):
    {
        "DATABASE_URL":       "postgresql+asyncpg://...",
        "OPENAI_API_KEY":     "sk-...",
        "JWT_SECRET_KEY":     "...",
        "WEBHOOK_SECRET":     "...",
        "LANGCHAIN_API_KEY":  "..."
    }
    """
    if s.app_env != "production" or not s.aws_secrets_name:
        return

    logger.info("Loading secrets from AWS Secrets Manager: %s", s.aws_secrets_name)
    secret = _fetch_secret_json(s.aws_secrets_name, s.aws_region)

    _MAP: dict[str, str] = {
        "DATABASE_URL":      "database_url",
        "OPENAI_API_KEY":    "openai_api_key",
        "JWT_SECRET_KEY":    "jwt_secret_key",
        "WEBHOOK_SECRET":    "webhook_secret",
        "LANGCHAIN_API_KEY": "langchain_api_key",
    }
    applied = 0
    for secret_key, attr in _MAP.items():
        val = secret.get(secret_key)
        if val:
            object.__setattr__(s, attr, val)
            applied += 1

    logger.info("Applied %d secret(s) from Secrets Manager", applied)


settings = Settings()
limiter = Limiter(key_func=get_remote_address)

__all__ = [
    "IST",
    "SEBI_DISCLAIMER",
    "Settings",
    "get_market_status",
    "limiter",
    "load_production_secrets",
    "settings",
]
