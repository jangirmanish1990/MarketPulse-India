---
description: Seed the local DB with sample instruments and historical bars
argument-hint: [<universe: NIFTY50|NIFTY100|SENSEX|all>] [<days>]
---

# /seed-corpus — seed the local DB with sample data

Populate the **local** dev database with sample instruments and historical
OHLCV bars so agents, evals, and backtests have something to chew on.

Defaults: universe = `NIFTY50`, days = `365`.

Steps:

1. Confirm the local DB is up (`docker compose up -d db`) and migrations
   are current (`make migrate`).
2. Run `python scripts/seed_corpus.py --universe $1 --days $2` (defaults
   apply if arguments are empty).
3. The script should:
   - Insert instrument rows for the chosen universe (NSE/BSE symbol,
     ISIN, sector).
   - Fetch or generate daily OHLCV bars in IST.
   - Idempotently upsert — running the command twice should not duplicate
     rows.
4. Print a summary: instruments inserted, bars inserted, date range
   covered (in IST).

Constraints:

- **Local DB only.** Refuse to run against any database whose URL is not
  `localhost`/`127.0.0.1`.
- Generated/synthetic bars must be clearly tagged in the DB (`source =
  'synthetic'`) so they never leak into evals or backtests claiming to
  reflect real market data.
- Do not commit seed CSVs over 5MB; keep them under `scripts/data/` only
  if they fit that budget.
