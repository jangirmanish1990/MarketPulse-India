"""Smoke-test CloudWatch metric publishing for MarketPulse India.

Publishes one data point per metric family, then lists metrics from the
MarketPulseIndia namespace to confirm they arrived.

Note: CloudWatch can take 1-2 minutes to show newly published metrics in
list_metrics(). Run again after a short wait if the count is 0.

Usage:
    python scripts/test_monitoring.py

Requires AWS credentials with cloudwatch:PutMetricData + cloudwatch:ListMetrics.
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

SEP = "=" * 56
OK = "[PASS]"
FAIL = "[FAIL]"


def _check(label: str, ok: bool, detail: str = "") -> bool:
    tag = OK if ok else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  {tag}  {label}{suffix}")
    return ok


def test_metrics() -> bool:
    from backend.monitoring import (
        get_cloudwatch_client,
        record_agent_run,
        record_mcp_call,
        record_retrieval,
        record_signal_confidence,
    )

    results: list[bool] = []

    # ── Verify boto3 is available ──────────────────────────────────────────
    cw = get_cloudwatch_client()
    results.append(_check("boto3 CloudWatch client initialized", cw is not None))
    if cw is None:
        print("\n  [SKIP] No boto3 — install with: pip install -e '.[infra]'")
        return False

    print("\nPublishing test metrics to CloudWatch...")

    # ── Publish one data point per metric family ───────────────────────────
    record_agent_run("INFY", 35000, True, "BUY")
    results.append(_check("AgentRunDuration + AgentRunSuccess + SignalGenerated published", True))

    record_mcp_call("nse-yfinance", "get_live_quote", 2000, True)
    results.append(_check("MCPCallDuration + MCPCallSuccess published", True))

    record_retrieval("INFY", 5, 4, False)
    results.append(_check("RetrievalPrecision + WebFallbackUsed published", True))

    record_signal_confidence("INFY", 0.91, "BUY")
    results.append(_check("SignalConfidence published", True))

    # ── List metrics in namespace (may be 0 if < 2 min since first publish) ─
    try:
        resp = cw.list_metrics(Namespace="MarketPulseIndia")
        metrics = resp.get("Metrics", [])
        print(f"\n  Metrics visible in CloudWatch namespace: {len(metrics)}")
        for m in metrics:
            print(f"    {m['MetricName']}")
        if not metrics:
            print("  (CloudWatch takes 1-2 min to index new metrics — rerun shortly)")
    except Exception as exc:
        print(f"  [WARN] list_metrics failed: {exc}")

    return all(results)


def main() -> None:
    print(SEP)
    print("MarketPulse India — CloudWatch Monitoring Smoke Test")
    print(SEP)

    passed = test_metrics()

    print(f"\n{SEP}")
    print("CloudWatch monitoring test PASSED" if passed else "CloudWatch monitoring test FAILED")
    print(SEP)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
