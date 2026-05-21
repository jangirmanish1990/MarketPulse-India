"""Application-level settings and shared constants for MarketPulse India."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict
from slowapi import Limiter
from slowapi.util import get_remote_address

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

    # Rate limiting
    rate_limit_analyses_per_day: int = 100

    # Webhook
    webhook_secret: str = "marketpulse-webhook-secret-2026"


settings = Settings()
limiter = Limiter(key_func=get_remote_address)

__all__ = [
    "IST",
    "SEBI_DISCLAIMER",
    "Settings",
    "get_market_status",
    "limiter",
    "settings",
]
