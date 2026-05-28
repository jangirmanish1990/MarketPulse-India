# MarketPulse India — FY25 Backtest Report

> **Generated:** 2026-05-28 10:54 IST  
> **Universe:** 12 stocks × 4 quarters = 48 signals (FY2024-25)  
> **Data:** Mock prices for educational/testing purposes.
  In production, prices are fetched from Yahoo Finance.

## Summary

| Metric | Value |
|---|---|
| Total signals | 48 |
| Correct signals | 40 |
| Overall accuracy | **83.3%** |
| Average alpha (BUY signals) | **+6.88% vs Nifty50** |
| Best sector | Consumer, Energy, FMCG, NBFC (100.0%) |
| Worst sector | Conglomerate (50.0%) |

## Accuracy Definition

| Signal | Correct if … |
|---|---|
| **BUY**  | `stock_return_30d > nifty_return_30d` — beat the market |
| **SELL** | `stock_return_30d < nifty_return_30d` — lagged the market |
| **HOLD** | `|stock_return_30d − nifty_return_30d| < 3 %` — in-line with market |

Where `alpha = stock_return_30d − nifty_return_30d`.

## Signal-by-Signal Results

| Symbol | Quarter | Signal | Conf | Stock Ret | Nifty Ret | Alpha | Correct | Sector |
|--------|---------|--------|------|-----------|-----------|-------|---------|--------|
| TCS | Q1FY25 | 🟢 BUY | 82% | +7.01% | +2.48% | **+4.53%** | ✅ | IT |
| TCS | Q2FY25 | 🟢 BUY | 79% | +4.07% | +0.80% | **+3.26%** | ✅ | IT |
| TCS | Q3FY25 | 🟡 HOLD | 61% | -2.56% | -1.68% | **-0.88%** | ✅ | IT |
| TCS | Q4FY25 | 🟢 BUY | 85% | +9.18% | +4.98% | **+4.21%** | ✅ | IT |
| INFY | Q1FY25 | 🟢 BUY | 78% | +9.88% | +2.48% | **+7.40%** | ✅ | IT |
| INFY | Q2FY25 | 🟡 HOLD | 58% | -1.66% | +0.80% | **-2.46%** | ✅ | IT |
| INFY | Q3FY25 | 🟢 BUY | 81% | +14.29% | -1.68% | **+15.97%** | ✅ | IT |
| INFY | Q4FY25 | 🟢 BUY | 76% | +10.86% | +4.98% | **+5.88%** | ✅ | IT |
| HDFCBANK | Q1FY25 | 🟢 BUY | 74% | +5.56% | +2.48% | **+3.08%** | ✅ | Banking |
| HDFCBANK | Q2FY25 | 🟡 HOLD | 55% | -1.79% | +0.80% | **-2.59%** | ✅ | Banking |
| HDFCBANK | Q3FY25 | 🟡 HOLD | 62% | +3.14% | -1.68% | **+4.83%** | ❌ | Banking |
| HDFCBANK | Q4FY25 | 🟢 BUY | 77% | +11.69% | +4.98% | **+6.71%** | ✅ | Banking |
| RELIANCE | Q1FY25 | 🟡 HOLD | 59% | +1.73% | +2.48% | **-0.75%** | ✅ | Energy |
| RELIANCE | Q2FY25 | 🟢 BUY | 71% | +9.71% | +0.80% | **+8.91%** | ✅ | Energy |
| RELIANCE | Q3FY25 | 🟡 HOLD | 63% | -1.71% | -1.68% | **-0.03%** | ✅ | Energy |
| RELIANCE | Q4FY25 | 🟢 BUY | 80% | +12.45% | +4.98% | **+7.48%** | ✅ | Energy |
| WIPRO | Q1FY25 | 🟡 HOLD | 57% | +2.50% | +2.48% | **+0.02%** | ✅ | IT |
| WIPRO | Q2FY25 | 🟡 HOLD | 54% | -2.35% | +0.80% | **-3.16%** | ❌ | IT |
| WIPRO | Q3FY25 | 🔴 SELL | 68% | -6.67% | -1.68% | **-4.99%** | ✅ | IT |
| WIPRO | Q4FY25 | 🟡 HOLD | 60% | +5.13% | +4.98% | **+0.16%** | ✅ | IT |
| BAJFINANCE | Q1FY25 | 🟢 BUY | 83% | +9.12% | +2.48% | **+6.64%** | ✅ | NBFC |
| BAJFINANCE | Q2FY25 | 🟢 BUY | 79% | +8.17% | +0.80% | **+7.37%** | ✅ | NBFC |
| BAJFINANCE | Q3FY25 | 🟡 HOLD | 64% | -1.87% | -1.68% | **-0.19%** | ✅ | NBFC |
| BAJFINANCE | Q4FY25 | 🟢 BUY | 81% | +11.25% | +4.98% | **+6.27%** | ✅ | NBFC |
| TITAN | Q1FY25 | 🟢 BUY | 76% | +6.52% | +2.48% | **+4.04%** | ✅ | Consumer |
| TITAN | Q2FY25 | 🟢 BUY | 72% | +5.56% | +0.80% | **+4.75%** | ✅ | Consumer |
| TITAN | Q3FY25 | 🟡 HOLD | 58% | -1.69% | -1.68% | **-0.01%** | ✅ | Consumer |
| TITAN | Q4FY25 | 🟢 BUY | 77% | +10.06% | +4.98% | **+5.08%** | ✅ | Consumer |
| NESTLEIND | Q1FY25 | 🟡 HOLD | 61% | +1.21% | +2.48% | **-1.27%** | ✅ | FMCG |
| NESTLEIND | Q2FY25 | 🟡 HOLD | 56% | -2.09% | +0.80% | **-2.90%** | ✅ | FMCG |
| NESTLEIND | Q3FY25 | 🔴 SELL | 69% | -4.39% | -1.68% | **-2.71%** | ✅ | FMCG |
| NESTLEIND | Q4FY25 | 🟡 HOLD | 62% | +2.79% | +4.98% | **-2.19%** | ✅ | FMCG |
| AXISBANK | Q1FY25 | 🟢 BUY | 75% | +9.32% | +2.48% | **+6.84%** | ✅ | Banking |
| AXISBANK | Q2FY25 | 🟢 BUY | 71% | +6.45% | +0.80% | **+5.65%** | ✅ | Banking |
| AXISBANK | Q3FY25 | 🟡 HOLD | 59% | +2.75% | -1.68% | **+4.43%** | ❌ | Banking |
| AXISBANK | Q4FY25 | 🟢 BUY | 78% | +15.69% | +4.98% | **+10.71%** | ✅ | Banking |
| SBIN | Q1FY25 | 🟢 BUY | 80% | +10.98% | +2.48% | **+8.50%** | ✅ | Banking |
| SBIN | Q2FY25 | 🟢 BUY | 74% | +8.05% | +0.80% | **+7.24%** | ✅ | Banking |
| SBIN | Q3FY25 | 🟡 HOLD | 60% | +3.85% | -1.68% | **+5.53%** | ❌ | Banking |
| SBIN | Q4FY25 | 🟢 BUY | 82% | +16.67% | +4.98% | **+11.69%** | ✅ | Banking |
| KOTAKBANK | Q1FY25 | 🟡 HOLD | 57% | -1.65% | +2.48% | **-4.13%** | ❌ | Banking |
| KOTAKBANK | Q2FY25 | 🟢 BUY | 70% | +8.05% | +0.80% | **+7.24%** | ✅ | Banking |
| KOTAKBANK | Q3FY25 | 🟡 HOLD | 63% | +2.38% | -1.68% | **+4.06%** | ❌ | Banking |
| KOTAKBANK | Q4FY25 | 🟢 BUY | 75% | +10.13% | +4.98% | **+5.15%** | ✅ | Banking |
| ADANIENT | Q1FY25 | 🟡 HOLD | 55% | -2.83% | +2.48% | **-5.31%** | ❌ | Conglomerate |
| ADANIENT | Q2FY25 | 🔴 SELL | 71% | -8.72% | +0.80% | **-9.53%** | ✅ | Conglomerate |
| ADANIENT | Q3FY25 | 🟡 HOLD | 58% | +2.76% | -1.68% | **+4.44%** | ❌ | Conglomerate |
| ADANIENT | Q4FY25 | 🟢 BUY | 73% | +12.50% | +4.98% | **+7.52%** | ✅ | Conglomerate |

## Sector Breakdown

| Sector | Signals | Correct | Accuracy |
|--------|---------|---------|----------|
| Consumer | 4 | 4 | 100.0% |
| Energy | 4 | 4 | 100.0% |
| FMCG | 4 | 4 | 100.0% |
| NBFC | 4 | 4 | 100.0% |
| IT | 12 | 11 | 91.7% |
| Banking | 16 | 11 | 68.8% |
| Conglomerate | 4 | 2 | 50.0% |

## Incorrect Signals

All 8 incorrect signals were HOLD calls where market divergence (Nifty Q3 FY25 drawdown) pushed alpha outside the ±3% band.

| Symbol | Quarter | Signal | Stock Ret | Nifty Ret | Alpha |
|--------|---------|--------|-----------|-----------|-------|
| HDFCBANK | Q3FY25 | HOLD | +3.14% | -1.68% | +4.83% |
| WIPRO | Q2FY25 | HOLD | -2.35% | +0.80% | -3.16% |
| AXISBANK | Q3FY25 | HOLD | +2.75% | -1.68% | +4.43% |
| SBIN | Q3FY25 | HOLD | +3.85% | -1.68% | +5.53% |
| KOTAKBANK | Q1FY25 | HOLD | -1.65% | +2.48% | -4.13% |
| KOTAKBANK | Q3FY25 | HOLD | +2.38% | -1.68% | +4.06% |
| ADANIENT | Q1FY25 | HOLD | -2.83% | +2.48% | -5.31% |
| ADANIENT | Q3FY25 | HOLD | +2.76% | -1.68% | +4.44% |

---

> ⚠️ **MarketPulse India is not a SEBI-registered investment advisor.**  
> This backtest uses mock price data for **educational and testing purposes only**.
> Past signal accuracy does not guarantee future performance.
> Markets carry risk; consult a registered advisor before making decisions.
