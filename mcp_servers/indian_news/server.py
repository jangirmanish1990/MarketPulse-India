"""Indian News MCP server — RSS feed aggregator for NSE/BSE stock news.

Aggregates real-time Indian financial news from ET Markets, Moneycontrol,
LiveMint, and Business Standard via RSS feeds. Used as the web fallback
when pgvector RAG retrieval returns too few relevant documents.
"""

from __future__ import annotations

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


if __name__ == "__main__":
    mcp.run()
