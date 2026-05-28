# Changelog

All notable changes to MarketPulse India are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.0.0] — 2026-05-28

### Added — Week 1–2 (Agent Pipeline)

- 9-node LangGraph CRAG pipeline: `fetch_market_data` → `parse_announcement` →
  `concall_analyzer` → `fetch_india_context` + `promoter_intelligence` (parallel)
  → `retrieve_rag_context` → `grade_documents` → `generate_analysis` → `score_signal`
- 5 custom MCP servers: NSE (with cookie rotation), BSE, yfinance-India, Screener.in,
  Indian News (ET / Moneycontrol / Mint)
- pgvector hybrid RAG (dense cosine + sparse BM25) with HyDE query expansion
- CRAG grader with automatic web fallback when relevance score < 0.65
- `AgentState` Pydantic v2 model — full type safety across all nodes
- IST-aware datetime handling throughout (`Asia/Kolkata`, no DST)
- ₹ Crore number parser — normalises lakh / crore / thousand-crore notation

### Added — Week 3 (Backend + Evals)

- FastAPI async backend — 7 routers: auth, analyze, signals, sector, market,
  stocks, watchlist, webhook
- JWT authentication (`OAuth2PasswordBearer`, HS256, 24-hour expiry)
- WebSocket streaming gateway — live 9-node pipeline trace to frontend
- LangSmith eval suite — 5 evaluators, all passing on FY25 dataset (12 symbols):
  `parser_accuracy` 1.00 · `signal_accuracy` 0.92 · `faithfulness` 0.85 ·
  `india_risk_relevance` 1.00 · `sebi_compliance` 1.00
- FY25 backtest engine — 83.3% accuracy (40/48 signals), +6.88% alpha vs Nifty50
- CloudWatch dashboard (6 widgets) + SQS dead-letter queue
- Alembic migrations for Neon PostgreSQL (8-table schema, `TIMESTAMPTZ` throughout)
- `scripts/run_evals.py` — 3-mode runner: LangSmith live / local / Day-14 baseline

### Added — Week 4 (React Dashboard)

- React 19 + Vite + Tailwind CSS — saffron `#FF9500` brand theme, dark `#04080F` base
- Live Nifty50 / Sensex / BankNifty / NiftyIT ticker bar with WebSocket updates
- `AgentTrace` — real-time 9-node pipeline visualizer with per-node timing
- `IndianSignalCard` — ₹ price targets, confidence meter, SEBI disclaimer
- `ResultsCalendar` — result dates colour-coded by sector
- `AnnouncementFeed` — real-time NSE/BSE announcement stream
- `SectorView` — peer comparison table with composite rankings
- `SignalHistoryTable` — sortable, filterable, CSV export
- JWT login flow + protected routes
- PWA manifest + service worker (cache-first static, 5-min cache for `/api/signals`)

### Added — Week 5 (Advanced Features)

- `concall_analyzer` node — `management_tone` detection, `tone_vs_numbers`
  cross-check; cautious tone applies −0.08 confidence penalty
- `promoter_intelligence` node — pledging risk (>20% = −10% confidence),
  FII 5-day net flow classification (+7% / −5% confidence adjustments)
- Parallel sector analysis — LangGraph `Send` API 5-way fan-out; composite
  ranking: 0.4 × upside + 0.4 × confidence + 0.2 × direction
- Multi-channel alert dispatcher — WhatsApp (Meta Cloud API), Telegram Bot API,
  AWS SNS Transactional SMS; `AlertPayload` frozen Pydantic model
- Morning digest Lambda + pre-result alert Lambda with EventBridge schedules
- Locust load test — 9.3 RPS, 0% failure rate at 20 concurrent users

### Added — Week 6 (Deployment & Security)

- Multi-stage production `Dockerfile` — `python:3.12-slim`, `TZ=Asia/Kolkata`,
  non-root `appuser`, health check, 2-worker Uvicorn
- AWS CDK stacks (5 total):
  - `MarketPulseEcsStack` — VPC, ECR, ECS Fargate (0.5 vCPU / 1 GB), ALB,
    CPU auto-scaling 1–3 tasks
  - `MarketPulseFrontendStack` — S3 + CloudFront OAC, `PriceClass_200` (Mumbai edge),
    SPA error routing
  - `MarketPulseWafStack` — WAFv2 CloudFront WebACL: `CommonRuleSet`,
    `KnownBadInputsRuleSet`, IP rate-limit 2 000 req/5 min
  - `MarketPulseObservabilityStack` — CloudWatch dashboard, alarms, SQS DLQ
  - `MarketPulsePollingStack` — NSE poller Lambda, DynamoDB, SNS topic
- GitHub Actions CI/CD:
  - `ci.yml` — lint (ruff) + types (mypy strict) + tests on every push/PR
  - `deploy.yml` — test → ECR build/push → ECS rolling deploy with Alembic migration gate
  - `deploy-frontend.yml` — Vite build → S3 sync (immutable hashes + no-cache entry
    points) → CloudFront invalidation
  - `test.yml` — PR gate: tests + eval gate (non-blocking)
- AWS Secrets Manager integration — `load_production_secrets()` overlays Pydantic
  `Settings` at startup when `APP_ENV=production`
- Neon RLS — `signals` (read-all), `watchlist_items` + `alert_preferences`
  (owner-only, `app.current_user_id` session variable); `marketpulse_app` role
  with `BYPASSRLS`
- Bandit 1.9.4 scan — **0 HIGH, 0 MEDIUM** issues across 57 files
- SEBI compliance audit — all 5 surfaces pass: alert templates (3/3),
  frontend components, API schema (5 routers), DB signal rows
- `scripts/smoke_test.py` — 6-check end-to-end validator (health → auth →
  analysis → WebSocket trace → DB → sector analysis)
- `docs/ARCHITECTURE.md` — 364-line deep-dive with India-specific design rationale
- `docs/API.md` — full API reference with curl examples and realistic responses
- `README.md` — badges, mermaid pipeline diagram, backtest results, quick start
