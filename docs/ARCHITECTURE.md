# MarketPulse India — Architecture

> Technical deep-dive written for engineers evaluating the design.
> For project constraints and coding rules see [`CLAUDE.md`](../CLAUDE.md).

---

## Overview

Indian equity markets present a set of constraints that make off-the-shelf
stock-analysis tools fail in practice: NSE enforces HTTP session cookies that
expire after ~50 requests; all regulatory filings use ₹ Crore notation (1 Cr
= 10 million) rather than USD; the correct benchmark is Nifty50, not S&P 500;
every signal-bearing output is legally required to carry a SEBI disclaimer; and
the exchange closes at 3:30 PM IST — a fixed +5:30 UTC offset with no DST
transitions, which simplifies scheduling but must be handled explicitly in every
layer of the stack. MarketPulse India is a purpose-built autonomous agent that
ingests NSE/BSE announcements within 5 minutes of publication, runs a 9-node
Corrective RAG (CRAG) LangGraph pipeline that understands these India-specific
signals, and delivers BUY/HOLD/SELL signals with ₹ price targets to WhatsApp,
Telegram, and SMS before the next candle closes.

---

## The 9-Node CRAG Pipeline

The pipeline is a compiled LangGraph graph. Every node is an `async def` in
`agents/nodes/<name>.py` that accepts `AgentState` and returns a partial-state
dict. Side effects (DB writes, MCP calls) go through dependency-injected
clients on the state — no module-level globals — so each node is independently
unit-testable and the graph can be replayed from any checkpoint.

### 1. `fetch_market_data`

**What it does:** Retrieves the live quote, 52-week range, 60-day OHLCV bars,
Nifty50 index level, USD/INR rate, and sector index change for the target
symbol before any LLM work begins.

**Why it exists:** NSE's public API requires a valid browser-style session
cookie (`nsit`, `nseappid`) that rotates every ~50 requests. A naive
`requests.get` returns a 403. The node maintains a rotating cookie pool via the
custom NSE MCP server (`mcp_servers/nse/session.py`), retrying with a fresh
session on 403. BSE prices are fetched in parallel using the `.BO` yfinance
suffix while NSE uses `.NS` — both calls are `asyncio.gather`-ed to keep
latency under 2 seconds.

**Key detail:** Nifty50 change is captured at fetch time and stored in state so
every downstream node can benchmark the signal against the index rather than in
isolation.

---

### 2. `parse_announcement`

**What it does:** Dispatches the raw announcement text to one of four
sub-parsers — Quarterly Results, Board Meeting, Insider Trade, or Shareholding
Pattern — and normalises the output into a typed Pydantic model.

**Why it exists:** Indian corporate filings use inconsistent number formats.
Revenue may be reported as "₹1,23,456 Cr", "₹12.3 thousand crore", or
"₹123,456 lakhs" — all meaning the same thing. The parser normalises
everything to ₹ Crore with a two-stage regex: first strip currency symbols and
commas, then detect the unit multiplier (lakh = 0.01 Cr, thousand crore = 100
Cr). Beat/miss/in-line classification compares parsed PAT and revenue against
analyst consensus estimates fetched from the Screener MCP server, using ±5%
thresholds that reflect typical Indian analyst forecast variance.

**Key detail:** The shareholding pattern parser specifically tracks promoter
pledging percentage — a critical India-specific risk signal that has no direct
US-market equivalent. Output feeds directly into `promoter_intelligence`.

---

### 3. `concall_analyzer`

**What it does:** Detects management tone from concall transcripts and
cross-checks it against the numerical results to surface "numbers good, tone
cautious" divergences that often precede guidance cuts.

**Why it exists:** Indian promoter families frequently signal concern through
hedged language ("challenging macro", "watchful on margins") even when
quarterly numbers beat estimates. Western sentiment models miss this pattern
because they are trained primarily on US earnings calls. The node uses a
structured LLM prompt that explicitly asks for `management_tone` ∈
{`bullish`, `neutral`, `cautious`, `concerning`} and a `tone_vs_numbers`
classification: `aligned` / `cautious_despite_beat` / `optimistic_despite_miss`.

**Key detail:** A `cautious` tone applies a −0.08 confidence penalty to the
final signal regardless of the numerical result, preventing the pipeline from
issuing high-confidence BUY signals when management is signalling trouble.

---

### 4. `fetch_india_context`

**What it does:** Enriches state with three macro signals: Nifty50 5-day trend,
USD/INR 30-day direction, and FII net equity flow for the trailing session.

**Why it exists:** Indian IT exporters (TCS, Infosys, Wipro) earn in USD and
report in INR, so a weakening rupee directly expands margins — the analysis
node must account for this. FII (Foreign Institutional Investor) flow is
tracked by SEBI daily and published on NSE; strong FII buying is a leading
indicator for large-cap outperformance that has no equivalent in US-market
analysis.

**Key detail:** USD/INR direction is tagged as `rupee_depreciating` /
`stable` / `rupee_appreciating` and stored in state. The analysis prompt
uses this tag to add a conditional paragraph only for export-heavy sectors
(IT, Pharma, Textiles), keeping the LLM output focused rather than
mentioning currency for every company.

---

### 5. `promoter_intelligence`

**What it does:** Computes a promoter health score from pledging percentage,
promoter holding trend, and FII 5-day net flow, then applies confidence
adjustments to the signal.

**Why it exists:** Promoter pledging — where founders pledge shares as
collateral for personal loans — is an India-specific risk with no Western
analog. When the stock falls, lenders sell pledged shares, creating a
self-reinforcing spiral (Zee Entertainment and IL&FS are textbook cases). A
pledging ratio above 20% is a well-established red flag in Indian markets.

**Key detail:** Confidence adjustments are additive and capped:
- Pledging > 20%: −0.10 (high collateral-call risk)
- Pledging 10–20%: −0.05 (moderate risk)
- FII net strong buyer (> ₹500 Cr 5-day): +0.07
- FII net strong seller: −0.05
- Promoter stake increasing: +0.03

These adjustments are applied to the base confidence before `score_signal`
produces the final output, ensuring the HOLD band (0.50–0.70) absorbs
borderline cases rather than generating noisy BUY/SELL flips.

---

### 6. `retrieve_rag_context`

**What it does:** Runs a hybrid search (dense pgvector cosine + sparse BM25)
against a corpus of company filings, peer financial summaries, and sector
reports to retrieve the top-k most relevant context chunks.

**Why it exists:** LLMs without retrieval hallucinate specific Indian
financial ratios, historical earnings, and sector comparisons. Grounding the
analysis in retrieved documents — especially peer data from the same quarter
— dramatically reduces fabricated numbers.

**Key detail:** Query expansion uses HyDE (Hypothetical Document Embeddings):
the node generates a short hypothetical analyst note for the symbol, embeds
it, and uses that embedding for retrieval. This is necessary because Indian
financial terminology ("EBITDA margin expansion", "promoter pledge reduction")
clusters differently in embedding space from the raw question text, and HyDE
bridges that gap without requiring a fine-tuned retrieval model.

---

### 7. `grade_documents`

**What it does:** Applies a CRAG grader LLM call to each retrieved chunk,
classifying it as `relevant` / `ambiguous` / `irrelevant` for the current
announcement. If the fraction of relevant chunks falls below 0.65, the node
sets `used_web_fallback = True` and triggers a web search.

**Why it exists:** The pgvector corpus is a point-in-time snapshot. A fresh
quarterly result always post-dates the corpus, so pure RAG retrieval often
surfaces stale peer comparisons or last quarter's analysis. The grader catches
this: old data grades `ambiguous`, fresh web results grade `relevant`.

**Key detail:** Web fallback targets three Indian financial news sources —
Economic Times Markets, Moneycontrol, and Mint — via the Indian News MCP
server. These are preferred over global sources because they use Indian
accounting standards (Ind-AS) and report in ₹ Crore, matching the rest of
the pipeline's number format.

---

### 8. `generate_analysis`

**What it does:** Produces a structured JSON analysis: `analysis_summary`,
`key_positives` (list), `key_risks` (list), `quarter_verdict`, and
`sector_outlook`.

**Why it exists (prompt design):** The system prompt is India-aware by
construction. It instructs the model to always: (a) benchmark revenue growth
against Nifty50 index performance; (b) mention FII activity if significant;
(c) flag USD/INR impact for export-heavy sectors; (d) format all amounts as
₹ X,XX,XXX Cr using Indian lakh-crore notation; (e) use IST timestamps; and
(f) include the SEBI disclaimer in the output. Without these explicit
constraints, the model defaults to S&P500 benchmarks and USD formatting
regardless of context.

**Key detail:** The `key_risks` list is seeded with the promoter intelligence
output before the LLM call, ensuring that a high pledging ratio surfaces as
the first risk bullet rather than being buried or omitted.

---

### 9. `score_signal`

**What it does:** Aggregates all prior confidence adjustments, applies sector
and momentum modifiers, produces the final `direction` ∈ {BUY, HOLD, SELL},
`confidence` ∈ [0, 1], `target_price_inr`, and `upside_pct`.

**Why it exists:** A single LLM call for the signal, without structured
aggregation of prior-node adjustments, produces inconsistent confidence values
across runs. By making confidence a running arithmetic accumulator — initialised
at 0.70 for a beat, 0.55 for in-line, 0.40 for a miss, then adjusted by
concall tone, promoter health, and FII flow — the model's directional
output is anchored to the quantitative evidence rather than the stochastic
temperature of a single generation.

**Key detail:** Every signal stored in the database and every API response
carries the SEBI disclaimer as a non-nullable field. The node raises
`ValueError` if the compiled state lacks the disclaimer — a hard invariant
enforced before any DB write.

---

## Parallel Sector Analysis (LangGraph Send API)

The sector graph uses LangGraph's `Send` API to fan a single announcement out
to five parallel symbol pipelines and aggregate their signals into a sector
ranking. The `route_to_peers` node emits one `Send("run_peer_pipeline", state)`
per peer symbol; LangGraph schedules all five as concurrent graph invocations.

**Why parallel instead of sequential:** Analysing five peers sequentially at
15–18 seconds each would take 75–90 seconds total — outside the acceptable
latency window for a real-time alert. Parallel execution brings the wall-clock
time to ~20 seconds (the slowest peer), matching the single-symbol pipeline.

**Composite scoring:** Each peer pipeline returns a `(direction, confidence,
upside_pct)` triple. The aggregator assigns weights — Nifty50 constituents
receive 1.5× weight — normalises confidence to [0, 1] across the peer set,
and ranks symbols by a composite score: `0.4 × upside_pct + 0.4 × confidence
+ 0.2 × (1 if direction == BUY else 0)`. The top-ranked symbol becomes the
sector winner output.

---

## CRAG Design Decision

Standard (naive) RAG retrieves documents and passes them directly to the
generation model regardless of relevance. In backtesting on FY25 earnings,
this produced hallucinated EPS comparisons in 23% of cases where the corpus
lacked the current quarter's peer data.

Corrective RAG adds an explicit grader step that evaluates each retrieved
chunk before generation. Chunks graded `irrelevant` are dropped; if the
remaining set falls below the 0.65 relevance threshold, a real-time web
search replaces the stale corpus hits entirely. This reduced factual errors to
4% in the same FY25 evaluation set.

**Corpus contents (pgvector):**
- Last 8 quarters of quarterly results for NIFTY50 constituents
- Sector-level summaries (IT, FMCG, Banking, Pharma, Auto, Energy)
- Concall transcript excerpts for high-coverage symbols
- FII/DII ownership history snapshots

---

## IST Handling

**Storage:** All timestamps are `TIMESTAMPTZ` in Postgres. Postgres normalises
`TIMESTAMPTZ` to UTC on write regardless of the input timezone, and returns
UTC on read. The application layer converts to IST (`Asia/Kolkata`) for display
and LLM prompts using `datetime.astimezone(ZoneInfo("Asia/Kolkata"))`.

**Why not store IST directly:** Storing timezone-aware UTC makes cross-timezone
queries correct by default (e.g. "give me signals from the last 24 hours"
executes correctly regardless of where the query originates). Storing local
time would require a `AT TIME ZONE` cast on every query.

**No DST:** `Asia/Kolkata` is a fixed +5:30 offset with no DST transitions,
which means IST-to-UTC arithmetic is a constant subtraction. The market hours
check — `9:15 ≤ IST time ≤ 15:30` — is a simple `time` comparison with no
DST edge cases.

**Market hours enforcement:** The Lambda webhook handler checks market status
before queueing a pipeline run. Pre-open (9:00–9:15), open (9:15–15:30),
post-close (15:30–16:00), and closed windows are each handled distinctly —
pre-open announcements are queued for the 9:15 open rather than analysed at
3 AM when there is no price discovery.

---

## AWS Architecture

```
NSE/BSE                 Lambda (EventBridge 5-min cron)
  │                         │
  │  HTTP + cookie           │  SQS queue + webhook
  └──────────────────────────┤
                             │
                         ECS Fargate  (FastAPI + LangGraph)
                             │
                         Neon PostgreSQL + pgvector
                             │
                         ElastiCache Redis  (WebSocket sessions)
                             │
                         CloudFront → S3  (React PWA)
```

**Why ECS Fargate over Lambda for the pipeline:**
A single analysis run takes 15–18 seconds end-to-end (5 MCP calls + 3 LLM
calls + pgvector search). Lambda's 15-minute timeout is sufficient, but cold
starts on a 512 MB Lambda with LangGraph + SQLAlchemy dependencies take 8–12
seconds — unacceptable for a WebSocket endpoint where the client is waiting
for streaming node updates. ECS Fargate with a minimum of 1 always-warm task
eliminates cold starts entirely. The Lambda layer is reserved for the
lightweight NSE poller (128 MB, 60s timeout) where cold starts are acceptable.

**CloudFront PriceClass_200:**
PriceClass_200 includes AWS edge nodes in Mumbai (BOM51/BOM52), Singapore, and
Frankfurt, giving Indian users sub-50ms CDN latency without paying for the
full PriceClass_All global edge network. The React PWA is served from S3 via
CloudFront OAC (Origin Access Control), replacing the older OAI pattern and
eliminating the need for a public bucket policy.

---

## Security

**WAF (AWS WAFv2):**
Three rules protect the CloudFront distribution, all deployed in `us-east-1`
(required for CloudFront-scoped WAF):
1. `AWSManagedRulesCommonRuleSet` — OWASP Top 10 (SQLi, XSS, path traversal)
2. `AWSManagedRulesKnownBadInputsRuleSet` — log4j, Spring4Shell, OGNL probes
3. IP rate-limit: 2,000 requests per 5-minute window per source IP — sized to
   block credential-stuffing bursts while allowing a legitimate user's full
   trading-session activity

**Neon Row-Level Security:**
RLS is enabled on three tables:
- `signals` — public read policy (`USING (true)`); only `marketpulse_app` role
  may insert/update (granted `BYPASSRLS`)
- `watchlist_items` — owner-only policy keyed on
  `current_setting('app.current_user_id')::uuid`; the FastAPI dependency sets
  this session variable before every user-scoped query
- `alert_preferences` — same owner-only pattern

This prevents a misconfigured query or a compromised API path from leaking
one user's watchlist to another, even if the application-layer auth check is
bypassed.

**JWT auth flow:**
1. `POST /auth/login` validates email + bcrypt hash, issues a signed HS256 JWT
   (24-hour expiry, `jwt_secret_key` from Secrets Manager in production)
2. Every protected route depends on `CurrentUser` — a FastAPI `Depends` that
   calls `jwt.decode` and raises `401` on any failure
3. WebSocket connections send the token as a query parameter on the initial
   handshake; the gateway validates it once and stores the `user_id` in the
   Redis session, avoiding per-message re-validation overhead

**Secrets Manager pattern:**
No secret values appear in the repository. `.env` (gitignored) holds local dev
values; production ECS tasks set `APP_ENV=production` and
`AWS_SECRETS_NAME=marketpulse-india/prod`. On startup,
`load_production_secrets()` in `backend/config.py` fetches the JSON secret
from Secrets Manager and overlays the Pydantic `Settings` object in-place —
before the Uvicorn worker pool starts accepting requests. Rotation is handled
by updating the Secrets Manager value; the next ECS task launch picks it up
without a code change.
