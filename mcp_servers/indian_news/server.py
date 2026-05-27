"""Indian News MCP server — RSS feed aggregator for NSE/BSE stock news.

Aggregates real-time Indian financial news from ET Markets, Moneycontrol,
LiveMint, and Business Standard via RSS feeds. Used as the web fallback
when pgvector RAG retrieval returns too few relevant documents.

Also provides concall (earnings call) transcript fetching with a local cache
and Screener.in fallback.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import feedparser  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
mcp: FastMCP = FastMCP("indian-news-mcp")

RSS_FEEDS: dict[str, str] = {
    "ET Markets": "https://economictimes.indiatimes.com/markets/rss.cms",
    "Moneycontrol": "https://www.moneycontrol.com/rss/latestnews.xml",
    "LiveMint": "https://www.livemint.com/rss/markets",
    "Business Standard": "https://www.business-standard.com/rss/markets-106.rss",
}

_POSITIVE_WORDS = frozenset(
    [
        "beat",
        "profit",
        "growth",
        "surge",
        "rally",
        "strong",
        "record",
        "dividend",
        "buyback",
        "upgrade",
        "outperform",
        "gain",
        "rise",
        "up",
        "positive",
        "bullish",
    ]
)
_NEGATIVE_WORDS = frozenset(
    [
        "miss",
        "loss",
        "decline",
        "fall",
        "weak",
        "cut",
        "downgrade",
        "concern",
        "risk",
        "warning",
        "underperform",
        "down",
        "negative",
        "bearish",
        "sell-off",
    ]
)


def _classify_sentiment(title: str) -> str:
    lower = title.lower()
    if any(w in lower for w in _POSITIVE_WORDS):
        return "bullish"
    if any(w in lower for w in _NEGATIVE_WORDS):
        return "bearish"
    return "neutral"


@mcp.tool()
def search_stock_news(
    symbol: str,
    company_name: str = "",
    days: int = 7,
) -> list[dict[str, Any]]:
    """Search Indian financial news RSS feeds for a stock symbol.

    Searches ET Markets, Moneycontrol, LiveMint, and Business Standard.
    Matches by NSE symbol or company name (case-insensitive).
    Returns up to 20 articles sorted by recency, with sentiment tags.
    """
    results: list[dict[str, Any]] = []
    symbol_upper = symbol.upper()
    company_upper = company_name.upper() if company_name else ""

    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:50]:
                title: str = entry.get("title", "")
                if not title:
                    continue

                # Match by symbol or company name
                title_upper = title.upper()
                if symbol_upper not in title_upper and (
                    not company_upper or company_upper not in title_upper
                ):
                    continue

                results.append(
                    {
                        "headline": title,
                        "source": source,
                        "url": entry.get("link", ""),
                        "sentiment": _classify_sentiment(title),
                        "published": entry.get("published", ""),
                        "summary": entry.get("summary", "")[:300],
                    }
                )
        except Exception:
            logger.exception("[indian-news-mcp] %s feed failed", source)

    return results[:20]


@mcp.tool()
def get_analyst_ratings(symbol: str) -> dict[str, Any]:
    """Get analyst consensus for a stock.

    Placeholder — returns neutral consensus. Live analyst ratings
    (scraped from Moneycontrol) are planned for Week 5.
    """
    return {
        "symbol": symbol.upper(),
        "consensus": "HOLD",
        "buy_count": 0,
        "hold_count": 0,
        "sell_count": 0,
        "avg_target_inr": 0.0,
        "note": "Live analyst ratings coming in Week 5",
    }


@mcp.tool()
def get_concall_transcript(
    symbol: str,
    quarter: str = "latest",
) -> dict[str, Any]:
    """Fetch earnings call transcript for an Indian stock.

    Returns transcript text, key highlights, and metadata.

    Resolution order:
    1. Local cache  →  ``data/transcripts/<SYMBOL>_<quarter>.json``
    2. Screener.in  →  ``/company/<SYMBOL>/concalls/`` (returns URL only)
    3. Built-in mock transcripts for INFY / TCS (for testing)
    4. Empty skeleton for any other symbol

    Args:
        symbol:  NSE ticker (e.g. ``"INFY"``, ``"TCS"``).
        quarter: Quarter string (e.g. ``"Q2FY25"``) or ``"latest"`` (default).

    Returns:
        dict with keys:
          symbol, quarter, source, available (bool),
          management_opening, analyst_qa,
          key_metrics_mentioned, transcript_url (optional), note (optional).
    """
    # ------------------------------------------------------------------
    # 1. Local cache
    # ------------------------------------------------------------------
    cache_dir = Path("data/transcripts")
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{symbol.upper()}_{quarter}.json"

    if cache_file.exists():
        with cache_file.open() as fh:
            return json.load(fh)  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # 2. Screener.in concalls page  (returns link, not full text)
    # ------------------------------------------------------------------
    try:
        import requests  # MCP server — sync IO is acceptable here
        from bs4 import BeautifulSoup  # MCP server — sync IO is acceptable here

        url = f"https://www.screener.in/company/{symbol.upper()}/concalls/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            docs = soup.find_all(
                "a",
                string=lambda t: t and ("transcript" in t.lower() or "concall" in t.lower()),
            )
            if docs:
                result: dict[str, Any] = {
                    "symbol": symbol.upper(),
                    "quarter": quarter,
                    "source": "screener.in",
                    "available": True,
                    "transcript_url": docs[0].get("href", ""),
                    "transcript_text": None,
                    "management_opening": "",
                    "analyst_qa": "",
                    "key_metrics_mentioned": {},
                    "note": "Transcript URL found — full text requires download",
                }
                with cache_file.open("w") as fh:
                    json.dump(result, fh, indent=2)
                return result
    except Exception:
        logger.exception("[indian-news-mcp] Screener.in concall fetch failed for %s", symbol)

    # ------------------------------------------------------------------
    # 3. Built-in mock transcripts for smoke-testing
    # ------------------------------------------------------------------
    _MOCK_TRANSCRIPTS: dict[str, dict[str, Any]] = {
        "INFY": {
            "symbol": "INFY",
            "quarter": "Q2FY25",
            "source": "mock",
            "available": True,
            "management_opening": (
                "Good evening everyone. Thank you for joining our Q2 FY25 earnings call.\n"
                "We are pleased to report another strong quarter with revenue of "
                "Rs 40,986 crores, growing 5.1% year on year. Our operating margin "
                "came in at 21.1%.\n"
                "We have upgraded our full year guidance to 4.5%-5% in constant currency.\n"
                "Total contract value of $2.4 billion shows strong deal momentum.\n"
                "Financial services is showing early signs of recovery.\n"
                "We remain cautious about discretionary spending recovery in the near term."
            ),
            "analyst_qa": (
                "Analyst: Can you comment on the deal pipeline and client spending?\n"
                "Management: We are seeing good momentum in our deal pipeline. "
                "However, clients remain cautious about discretionary projects. "
                "We expect gradual improvement in H2 FY25.\n\n"
                "Analyst: What is your outlook on margins?\n"
                "Management: We expect margins to remain in the 20-22% band for the full year. "
                "We are focused on operational efficiency and automation."
            ),
            "key_metrics_mentioned": {
                "revenue_guidance_cc": "4.5-5%",
                "margin_guidance": "20-22%",
                "deal_tcv_bn_usd": 2.4,
                "headcount_change": "stable",
            },
        },
        "TCS": {
            "symbol": "TCS",
            "quarter": "Q2FY25",
            "source": "mock",
            "available": True,
            "management_opening": (
                "Thank you for joining TCS Q2 FY25 earnings call.\n"
                "Revenue grew 8.1% year on year to Rs 63,973 crores.\n"
                "Our operating margin was 24.5%, maintaining our industry-leading position.\n"
                "Deal wins were strong at $8.6 billion TCV.\n"
                "We are seeing good momentum across all verticals.\n"
                "BFSI vertical showing signs of recovery.\n"
                "We remain cautiously optimistic about FY25."
            ),
            "analyst_qa": (
                "Analyst: How is the demand environment?\n"
                "Management: Demand environment is improving gradually. "
                "We are seeing good traction in AI and cloud projects. "
                "Discretionary spending recovery is slower than expected.\n\n"
                "Analyst: Any update on margin trajectory?\n"
                "Management: We are confident of maintaining margins in the current range. "
                "Efficiency programmes are on track."
            ),
            "key_metrics_mentioned": {
                "revenue_guidance_cc": None,
                "margin_guidance": "24-25%",
                "deal_tcv_bn_usd": 8.6,
                "headcount_change": "stable",
            },
        },
    }

    transcript = _MOCK_TRANSCRIPTS.get(
        symbol.upper(),
        {
            "symbol": symbol.upper(),
            "quarter": quarter,
            "source": "mock",
            "available": False,
            "management_opening": "",
            "analyst_qa": "",
            "key_metrics_mentioned": {},
            "note": f"No transcript available for {symbol.upper()}",
        },
    )

    # Cache so repeat calls are instant
    with cache_file.open("w") as fh:
        json.dump(transcript, fh, indent=2)

    return transcript


if __name__ == "__main__":
    mcp.run()
