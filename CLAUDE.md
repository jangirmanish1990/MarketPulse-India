# MarketPulse India — Project Constitution

> This is the **single source of truth** for how Claude Code (and humans) should
> work inside this repo. Read this top-to-bottom before changing anything.

---

## 1. What we are building

**MarketPulse India** is an autonomous NSE/BSE stock intelligence agent. It
ingests live and historical Indian equity market data, runs a multi-node
LangGraph agent over it, produces signals + commentary, and serves them over
an API + UI. It is **not** a broker, **not** registered with SEBI, and
**every signal-bearing surface must carry the SEBI disclaimer**.

Primary surfaces:
- **Backend** — async FastAPI app (`backend/`)
- **Agents** — LangGraph nodes orchestrating LLM reasoning (`agents/`)
- **MCP servers** — tool servers Claude/agents call into (`mcp_servers/`)
- **Frontend** — Next.js dashboard (`frontend/`)
- **Infra** — AWS (Lambda + RDS + ECS) via Terraform (`infra/`, `lambdas/`)

---

## 2. Non-negotiable rules

These are hard constraints. Violating any of them is a bug, not a stylistic
choice.

1. **LLM provider is OpenAI, not Anthropic.**
   - `gpt-4o` for strong reasoning, `gpt-4o-mini` for fast/cheap calls,
     `text-embedding-3-small` for embeddings.
   - **All** LLM clients must be imported from `agents/llm.py`. Never
     instantiate `ChatOpenAI` / `OpenAIEmbeddings` anywhere else.

2. **All datetimes are IST (`Asia/Kolkata`).**
   - Never use naive `datetime.now()`. Use `datetime.now(ZoneInfo("Asia/Kolkata"))`.
   - Store timezone-aware timestamps in the DB (`TIMESTAMPTZ`).
   - Display values in IST in the UI; do not localize on the frontend.

3. **Async everywhere in the backend.**
   - All FastAPI route handlers are `async def`.
   - Use `asyncpg` / `SQLAlchemy 2.0 async` for DB, `httpx.AsyncClient` for HTTP.
   - No `requests`, no sync DB drivers, no blocking I/O in request paths.

4. **Python 3.12 + Pydantic v2.**
   - `.python-version` is pinned to `3.12`.
   - Use `model_config = ConfigDict(...)`, not the v1 `class Config`.
   - Use `Annotated[...]` + `Field(...)` for validation.

5. **SEBI disclaimer is mandatory on signal output.**
   - Any API response, UI panel, or report that contains a buy/sell/hold
     signal, price target, or directional commentary **must** include:
     ```
     ⚠️ MarketPulse India is not a SEBI-registered investment advisor.
     Output is for educational/informational purposes only and is not
     investment advice. Markets carry risk; consult a registered advisor
     before making decisions.
     ```
   - Use `/check-sebi` slash command before shipping any new signal surface.

6. **No secrets in the repo.** Use `.env` (gitignored) locally and AWS
   Secrets Manager / Parameter Store in deployed environments. `.env.example`
   shows the shape, never real values.

---

## 3. Repository layout

```
backend/         FastAPI app, REST endpoints, websocket gateway
agents/          LangGraph state machine + reusable LLM helpers
agents/nodes/    One file per graph node (ingest, analyze, signal, …)
mcp_servers/     MCP servers exposed to Claude / agents
frontend/        Next.js 14 app (App Router)
infra/           Terraform modules for AWS
lambdas/         Standalone Lambda handlers (cron jobs, webhooks)
tests/           Pytest suite
tests/evals/     LLM evals (signal quality, disclaimer presence, …)
tests/e2e/       Playwright + API end-to-end tests
scripts/         One-off scripts: seeding, backfills, data fetches
docs/            Architecture notes, runbooks, decision records
```

Empty folders carry a `.gitkeep` until they have real content.

---

## 4. Tooling contract

| Concern        | Tool                          | Notes                               |
| -------------- | ----------------------------- | ----------------------------------- |
| Formatter      | `ruff format`                 | Run via `make lint` / pre-commit    |
| Linter         | `ruff check --fix`            | Config in `pyproject.toml`          |
| Types          | `mypy --strict`               | Strict mode is non-negotiable       |
| Tests          | `pytest -q`                   | Async tests use `pytest-asyncio`    |
| Migrations     | `alembic`                     | All schema changes go through it    |
| Package mgmt   | `uv` (preferred) or `pip`     | `uv sync` reads `pyproject.toml`    |
| Frontend       | `pnpm` (Node 20)              | Strict TS, no `any` without comment |
| Container      | `docker compose`              | Local dev: API + Redis + Postgres   |

Make targets (`make dev`, `make test`, `make lint`, `make migrate`,
`make deploy`) are the canonical entry points. CI runs the same commands.

---

## 5. LangGraph agent shape

The agent lives in `agents/` and exposes a single compiled graph. Conventions:

- Each node is a `async def` in `agents/nodes/<name>.py` taking
  `state: AgentState` and returning a partial state dict.
- Node files have **no** top-level LLM instantiation — import from
  `agents.llm`.
- Shared state is a Pydantic v2 model in `agents/state.py`.
- Side effects (DB writes, MCP tool calls) go through dependency-injected
  clients on the state, not module-level globals.

---

## 6. Definition of done

A change is "done" when:

1. `make lint` passes (ruff format + check, mypy strict).
2. `make test` passes (unit + relevant evals).
3. If it touches signal output: `/check-sebi` confirms disclaimer presence.
4. If it changes the DB: a new Alembic migration is included.
5. If it changes the agent: at least one eval in `tests/evals/` exercises it.
6. PR description names the affected surfaces (backend / agents / MCP / UI).

---

## 7. Slash commands (this repo)

These live in `.claude/commands/` and are tuned for MarketPulse work:

- `/scaffold-node` — create a new LangGraph node skeleton
- `/scaffold-mcp` — create a new MCP server skeleton
- `/add-mcp-tool` — add a tool to an existing MCP server
- `/run-evals` — run LLM eval suite against current agent
- `/backtest` — replay a signal strategy over historical data
- `/check-sebi` — verify SEBI disclaimer coverage on signal surfaces
- `/db-migrate` — generate + apply an Alembic migration
- `/seed-corpus` — populate dev DB with seed instruments + sample bars
- `/deploy-aws` — package and deploy to AWS (lambdas + ECS service)

Each command file documents its own arguments and preconditions.

---

## 8. What Claude should NOT do automatically

- **Do not push** to `main` or open PRs without being asked.
- **Do not run migrations** against any non-local DB without being asked.
- **Do not call `/deploy-aws`** without explicit confirmation.
- **Do not add Anthropic SDK** as a runtime dep — OpenAI only here.
- **Do not invent signals or price targets** for examples; use `EXAMPLE-ONLY`
  placeholders so eval suites don't confuse them with real output.
