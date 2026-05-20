"""Pydantic v2 structured-output models for NSE/BSE announcement parsing."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class QuarterlyResultsParsed(BaseModel):
    """Extracted from NSE quarterly results announcement."""

    revenue_cr: float = Field(description="Total revenue/sales in Indian Crores (₹ Cr)")
    pat_cr: float = Field(description="Profit After Tax in Indian Crores (₹ Cr)")
    eps: float = Field(description="Earnings Per Share in ₹")
    ebitda_cr: Optional[float] = Field(None, description="EBITDA in ₹ Cr if mentioned")
    operating_margin_pct: Optional[float] = Field(None, description="Operating margin %")
    yoy_revenue_growth_pct: float = Field(description="Year-on-Year revenue growth %")
    qoq_revenue_growth_pct: float = Field(description="Quarter-on-Quarter revenue growth %")
    yoy_pat_growth_pct: float = Field(description="Year-on-Year PAT growth %")
    quarter: str = Field(description="Quarter label e.g. Q2FY25, Q3FY24")
    beat_or_miss: Literal["beat", "in-line", "miss"] = Field(
        description="Did results beat, meet, or miss street estimates?"
    )
    guidance_next_quarter: Optional[str] = Field(
        None, description="Management guidance for next quarter if mentioned"
    )
    key_highlights: list[str] = Field(
        default_factory=list,
        description="3-5 key highlights from the announcement",
    )


class BoardMeetingParsed(BaseModel):
    """Extracted from NSE board meeting outcome announcement."""

    dividend_per_share_inr: Optional[float] = Field(
        None, description="Dividend per share in ₹"
    )
    dividend_type: Optional[Literal["interim", "final", "special"]] = Field(None)
    record_date: Optional[str] = Field(
        None, description="Record date for dividend in DD-MMM-YYYY"
    )
    buyback_price_inr: Optional[float] = Field(
        None, description="Buyback price per share in ₹"
    )
    buyback_total_cr: Optional[float] = Field(
        None, description="Total buyback size in ₹ Cr"
    )
    stock_split_ratio: Optional[str] = Field(
        None, description="Split ratio e.g. 1:5"
    )
    bonus_ratio: Optional[str] = Field(
        None, description="Bonus share ratio e.g. 1:1"
    )
    other_decisions: list[str] = Field(
        default_factory=list,
        description="Other significant board decisions",
    )
    sentiment: Literal["very_positive", "positive", "neutral", "negative"] = Field(
        description="Overall sentiment of board decisions"
    )


class InsiderTradeParsed(BaseModel):
    """Extracted from NSE insider trading disclosure."""

    trader_name: str = Field(description="Name of the insider/promoter")
    designation: str = Field(description="Role: MD, CEO, Director, Promoter etc.")
    trade_type: Literal["buy", "sell"] = Field(description="Whether insider bought or sold")
    quantity: int = Field(description="Number of shares traded")
    avg_price_inr: float = Field(description="Average price per share in ₹")
    value_cr: float = Field(description="Total transaction value in ₹ Cr")
    holding_pct_before: Optional[float] = Field(
        None, description="Holding % before trade"
    )
    holding_pct_after: Optional[float] = Field(
        None, description="Holding % after trade"
    )
    trade_date: Optional[str] = Field(None, description="Date of trade")
    sentiment: Literal["bullish", "bearish", "neutral"] = Field(
        description="Buy = bullish, Sell = bearish usually"
    )


class SHPParsed(BaseModel):
    """Extracted from shareholding pattern announcement."""

    quarter: str = Field(description="Quarter e.g. Q2FY25")
    promoter_pct: float = Field(description="Promoter holding %")
    fii_pct: float = Field(description="Foreign Institutional Investor holding %")
    dii_pct: float = Field(description="Domestic Institutional Investor holding %")
    retail_pct: float = Field(description="Retail/public holding %")
    promoter_pledged_pct: Optional[float] = Field(
        None, description="% of promoter shares pledged"
    )
    promoter_change: Optional[float] = Field(
        None, description="Change in promoter holding vs last quarter (+ or -)"
    )
    fii_change: Optional[float] = Field(
        None, description="Change in FII holding vs last quarter"
    )
    pledging_risk: Literal["high", "medium", "low", "none"] = Field(
        description="high if pledged > 20%, medium if 10-20%, low if < 10%, none if 0"
    )
