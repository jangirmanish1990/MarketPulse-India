"""Structured logging configuration for MarketPulse India.

Call setup_logging() once at application startup (in the FastAPI lifespan).
Everywhere else, use get_logger(__name__) to obtain a structlog bound logger.

Processors inject IST timestamp and service metadata so every log line is
self-contained for log aggregators (CloudWatch, Loki, Datadog).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from structlog.types import EventDict, WrappedLogger

IST = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------------------
# Custom processors
# ---------------------------------------------------------------------------


def add_ist_timestamp(logger: WrappedLogger, method: str, event_dict: EventDict) -> EventDict:
    event_dict["timestamp_ist"] = datetime.now(IST).isoformat()
    return event_dict


def add_service_info(logger: WrappedLogger, method: str, event_dict: EventDict) -> EventDict:
    event_dict["service"] = "marketpulse-india"
    event_dict["version"] = "0.1.0"
    return event_dict


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def setup_logging(log_level: str = "INFO") -> None:
    """Configure structlog for the entire application.

    Development: coloured console output.
    Production: switch to JSONRenderer by setting LOG_FORMAT=json.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Keep stdlib logging quiet but funnelled into structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        add_ist_timestamp,
        add_service_info,
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_logger(name: str = __name__) -> Any:
    """Return a structlog bound logger.  Use as a module-level constant:

    log = get_logger(__name__)
    """
    return structlog.get_logger(name)
