# LinkedIn Launch Post — MarketPulse India

> Copy-paste ready. Placeholder links marked with `[LINK]`.
> Recommended image: a screenshot of the React dashboard showing a live BUY signal with the saffron theme.

---

**30 days. 1 autonomous agent. Every NSE/BSE announcement analyzed in under 20 seconds.**

I just finished building MarketPulse India — an end-to-end autonomous stock intelligence system for Indian equity markets. Here's what I built, why it was hard, and what I learned.

---

**The problem**

Every trading day, NSE and BSE publish hundreds of corporate announcements — quarterly results, board meeting outcomes, insider trades, shareholding changes. A retail investor who sees "INFY Q2 FY25: Revenue ₹40,986 Cr" in their inbox has no fast way to contextualize it. Is that a beat or a miss? How does it compare to TCS and Wipro this quarter? What are FII flows doing? Is the promoter pledging shares? Is Nifty50 up or down?

By the time you've answered those questions manually, the market has already priced in the news.

---

**What I built**

MarketPulse India is a 9-node LangGraph CRAG (Corrective RAG) pipeline that ingests every announcement within 5 minutes of publication, runs multi-source analysis, and delivers a BUY/HOLD/SELL signal with an ₹ price target over WhatsApp, Telegram, or SMS — before the next candle closes.

The architecture:

🔷 **AWS Lambda** polls NSE/BSE on a 5-minute EventBridge schedule and forwards announcements to the FastAPI backend via webhook

🔷 **9-node LangGraph pipeline** (15–18 seconds end-to-end):
- `fetch_market_data` → `parse_announcement` → `concall_analyzer`
- `fetch_india_context` + `promoter_intelligence` (parallel)
- `retrieve_rag_context` → `grade_documents`
- → web fallback if CRAG grade < 0.65
- `generate_analysis` → `score_signal`

🔷 **5 custom MCP servers** for Indian data: NSE, BSE, yfinance-India, Screener.in, and an Indian financial news aggregator

🔷 **Parallel sector analysis** using LangGraph's Send API — 5 peer pipelines run concurrently, then aggregate into a sector winner + ranked table

🔷 **83.3% backtest accuracy** on 48 FY25 signals across 12 NIFTY50 symbols, with +6.88% average alpha on BUY signals vs Nifty50

🔷 **LangSmith eval suite** — 5 evaluators (parser accuracy, signal accuracy, faithfulness, India risk relevance, SEBI compliance) running on every push to main

---

**The India-specific engineering challenges**

This is where it got genuinely interesting. Indian markets have constraints that break every off-the-shelf tool:

**1. NSE cookie rotation**
NSE's public API doesn't require a developer key — but it does require a valid browser session cookie that expires after ~50 requests. Every tool that tries to scrape NSE without handling this gets a silent 403. I built a rotating cookie pool in the NSE MCP server that refreshes sessions on failure and keeps a warm pool of 3 valid sessions at all times.

**2. ₹ Crore number parsing**
Indian financial reporting uses a lakh-crore system that has no direct mapping to Western notation. "₹40,986 Cr", "₹40.9 thousand crore", and "₹4,09,860 million" are all the same number. I wrote a two-stage normaliser: first strip currency symbols and commas, then detect the unit multiplier. Getting this wrong means your signal confidence calculations are off by a factor of 10.

**3. IST timezone with no DST**
`Asia/Kolkata` is +5:30 UTC — fixed, no daylight saving. This sounds simple until you're building a system that enforces market hours (9:15 AM–3:30 PM IST), stores all timestamps in UTC-normalised TIMESTAMPTZ, and needs to correctly gate pre-open announcements so they queue for the open rather than triggering an analysis at 3 AM.

**4. SEBI disclaimer — legally non-negotiable**
Every signal-bearing API response, every WebSocket message, every WhatsApp alert, every frontend component that shows a direction carries the full SEBI disclaimer. I built a `/check-sebi` script that audits every surface and a LangSmith evaluator (`sebi_compliance`, threshold 1.0) that gates deployments. It's treated as a first-class engineering constraint, not an afterthought.

**5. Promoter pledging as a confidence signal**
This is the one that has no Western equivalent. In India, promoter families often pledge their equity stake as collateral for personal loans. When the stock falls, lenders force-sell the pledged shares, creating a spiral. Pledge ratio > 20% is a well-established red flag. The `promoter_intelligence` node applies a −10% confidence penalty for high pledging, surfacing this risk in every signal even when quarterly numbers look clean.

---

**Tech stack**

LangGraph · LangChain · FastAPI · React · Tailwind CSS · Recharts ·
AWS ECS Fargate · CloudFront (PriceClass_200, Mumbai edge) ·
WAFv2 · AWS Lambda · Neon PostgreSQL · pgvector ·
LangSmith · Redis · JWT · GitHub Actions ·
Built entirely with **Claude Code** (agentic AI coding)

---

**The 30-day journey**

- **Week 1–2:** LangGraph pipeline, MCP servers, pgvector RAG — the core agent
- **Week 3:** FastAPI backend, LangSmith evals, backtesting engine — 83.3% accuracy validated
- **Week 4:** React dashboard, WebSocket streaming, WhatsApp/Telegram/SMS alerts
- **Week 5:** Concall analyzer, promoter intelligence, parallel sector analysis, load testing (9.3 RPS, 0% failures at 20 concurrent users)
- **Week 6:** AWS CDK deployment (ECS + CloudFront + WAF), GitHub Actions CI/CD, PWA, security hardening, documentation

---

**What's next**

Options flow analysis (F&O data from NSE). SEBI filing PDF parsing via document AI. Multi-timeframe signals (intraday vs positional). A mobile-first PWA that's already installable today.

---

**Links**

🔗 GitHub: [LINK — github.com/your-username/marketpulse-india]  
📊 LangSmith eval dashboard: [LINK — smith.langchain.com/...] *(eval results available on request)*  
🎯 Live demo: [LINK — available on request]

---

If you're building in the Indian fintech or LLM agent space, I'd love to connect. Happy to talk architecture, LangGraph patterns, or the specific quirks of Indian market data infrastructure.

---

\#LangGraph #LangChain #FastAPI #AWS #IndianStockMarket #NSE #BSE #AIEngineering #Claude #GenerativeAI #PortfolioProject #Python #React #BuildInPublic
