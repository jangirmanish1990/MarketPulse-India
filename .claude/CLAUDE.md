# Claude Code — MarketPulse India working notes

The full project constitution is in `../CLAUDE.md` at the repo root. This file
holds **Claude-Code-specific** working notes — things relevant to how the
agent should drive its tools in this repo.

## Quick rules recap

- LLM provider is **OpenAI** (`gpt-4o`, `gpt-4o-mini`,
  `text-embedding-3-small`). Anthropic SDK is **not** a runtime dependency.
- All LLM clients must be imported from `agents/llm.py`.
- All datetimes are IST (`Asia/Kolkata`); never use naive `datetime.now()`.
- Backend is fully async; use `httpx.AsyncClient` and async SQLAlchemy.
- Python 3.12 + Pydantic v2 (`model_config`, not class `Config`).
- Any signal-bearing surface must carry the SEBI disclaimer — run
  `/check-sebi` before shipping.

## Preferred entry points

- Use the `Makefile` targets (`make dev`, `make test`, `make lint`,
  `make migrate`) over remembering raw commands.
- Use the slash commands in `.claude/commands/` for repo-specific scaffolding
  rather than hand-rolling boilerplate.

## When you're scaffolding new code

- New LangGraph node → `/scaffold-node`
- New MCP server → `/scaffold-mcp`
- New tool on an existing MCP server → `/add-mcp-tool`
- New DB column / table → `/db-migrate`

## Things to be careful about

- Don't instantiate `ChatOpenAI` outside `agents/llm.py`. Import the
  pre-built `llm_strong`, `llm_fast`, or `embeddings`.
- Don't add sync DB drivers (`psycopg2`); use `asyncpg` + SQLAlchemy async.
- Don't commit `.env`. Update `.env.example` instead if you add a variable.
- Don't run `make deploy` without explicit user confirmation.
