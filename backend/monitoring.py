"""CloudWatch metrics publisher for MarketPulse India.

All functions are fire-and-forget: exceptions are caught and logged locally
so a CloudWatch outage never crashes the application.

boto3 is imported lazily so the module loads cleanly in dev environments
where the infra extra-deps aren't installed.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
NAMESPACE = "MarketPulseIndia"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Client (lazy + cached)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_cloudwatch_client() -> Any:
    """Return a cached boto3 CloudWatch client, or None if boto3 is absent."""
    try:
        import boto3

        return boto3.client(
            "cloudwatch",
            region_name=os.environ.get("AWS_REGION", "ap-south-1"),
        )
    except Exception:
        logger.debug("[monitoring] boto3 unavailable — CloudWatch metrics disabled")
        return None


# ---------------------------------------------------------------------------
# Core publisher
# ---------------------------------------------------------------------------


def publish_metric(
    metric_name: str,
    value: float,
    unit: str = "None",
    dimensions: dict[str, str] | None = None,
) -> None:
    """Publish a single metric data point to CloudWatch.

    Never raises — all errors are swallowed so callers can't be disrupted.
    """
    try:
        cw = get_cloudwatch_client()
        if cw is None:
            return

        metric_data: dict[str, Any] = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit,
            "Timestamp": datetime.now(IST),
        }
        if dimensions:
            metric_data["Dimensions"] = [
                {"Name": k, "Value": str(v)} for k, v in dimensions.items()
            ]

        cw.put_metric_data(Namespace=NAMESPACE, MetricData=[metric_data])
    except Exception as exc:
        logger.debug("[monitoring] CloudWatch publish failed for %s: %s", metric_name, exc)


# ---------------------------------------------------------------------------
# Domain helpers
# ---------------------------------------------------------------------------


def record_agent_run(
    symbol: str,
    duration_ms: int,
    success: bool,
    signal: str | None = None,
) -> None:
    """Record overall pipeline duration, success flag, and optional signal direction."""
    publish_metric(
        "AgentRunDuration",
        float(duration_ms),
        unit="Milliseconds",
        dimensions={"Symbol": symbol},
    )
    publish_metric(
        "AgentRunSuccess",
        1.0 if success else 0.0,
        unit="Count",
        dimensions={"Symbol": symbol},
    )
    if signal:
        publish_metric(
            "SignalGenerated",
            1.0,
            unit="Count",
            dimensions={"Direction": signal},
        )


def record_mcp_call(
    mcp_name: str,
    tool: str,
    duration_ms: int,
    success: bool,
) -> None:
    """Record an individual MCP tool call duration and outcome."""
    publish_metric(
        "MCPCallDuration",
        float(duration_ms),
        unit="Milliseconds",
        dimensions={"MCP": mcp_name, "Tool": tool},
    )
    publish_metric(
        "MCPCallSuccess",
        1.0 if success else 0.0,
        unit="Count",
        dimensions={"MCP": mcp_name},
    )


def record_retrieval(
    symbol: str,
    docs_retrieved: int,
    docs_relevant: int,
    used_fallback: bool,
) -> None:
    """Record RAG retrieval precision and web-fallback usage."""
    precision = docs_relevant / docs_retrieved if docs_retrieved > 0 else 0.0
    publish_metric(
        "RetrievalPrecision",
        precision,
        unit="None",
        dimensions={"Symbol": symbol},
    )
    publish_metric(
        "WebFallbackUsed",
        1.0 if used_fallback else 0.0,
        unit="Count",
    )


def record_signal_confidence(
    symbol: str,
    confidence: float,
    direction: str,
) -> None:
    """Record the final signal confidence score."""
    publish_metric(
        "SignalConfidence",
        confidence,
        unit="None",
        dimensions={"Symbol": symbol, "Direction": direction},
    )
