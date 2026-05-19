# MarketPulse India

Autonomous NSE/BSE stock intelligence agent.

See [`CLAUDE.md`](./CLAUDE.md) for the full project constitution: rules,
tooling contract, and definition of done.

## Quick start

```bash
cp .env.example .env          # fill in OPENAI_API_KEY at minimum
make install                  # install python deps (uv or pip)
make dev                      # docker compose: api + db + redis
make migrate                  # apply alembic migrations
make seed                     # optional: seed NIFTY50 + 1y of bars
```

Then hit `http://localhost:8000/health`.

## Layout

| Path             | What lives here                                    |
| ---------------- | -------------------------------------------------- |
| `backend/`       | Async FastAPI app                                  |
| `agents/`        | LangGraph nodes + shared LLM clients               |
| `mcp_servers/`   | MCP servers exposed to Claude / agents             |
| `frontend/`      | Next.js dashboard                                  |
| `infra/`         | Terraform for AWS                                  |
| `lambdas/`       | Standalone AWS Lambda handlers                     |
| `tests/`         | Pytest suite (unit, evals, e2e)                    |
| `scripts/`       | Seeders, backfills, one-off tools                  |

## Compliance

MarketPulse India is **not** a SEBI-registered investment advisor. All
signal-bearing surfaces must carry the disclaimer documented in
`CLAUDE.md` §2.5 and verified by `/check-sebi`.
