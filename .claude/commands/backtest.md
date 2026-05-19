---
description: Backtest a signal strategy over historical NSE/BSE data
argument-hint: <strategy_name> <start_date YYYY-MM-DD> <end_date YYYY-MM-DD> [<universe>]
---

# /backtest — replay a strategy over historical data

Backtest the strategy named `$1` from `$2` to `$3` against the universe
`$4` (default: `NIFTY50`).

Steps:

1. Resolve the strategy implementation in `backend/strategies/$1.py` (or
   `agents/strategies/$1.py`). If it doesn't exist, stop and ask the user.
2. Load historical bars for the universe across the date range from the
   local DB (run `/seed-corpus` first if the DB is empty).
3. Run the strategy day-by-day, recording signals + simulated P&L.
4. Output a summary table to stdout:
   - Total trades, win rate, gross / net P&L
   - Max drawdown, Sharpe (assume 252 trading days, IST close)
   - Per-symbol breakdown (top 10 by P&L)
5. Write the full trade ledger to `scripts/output/backtest_$1_$2_$3.csv`.

Constraints:

- Dates are interpreted in IST close-of-day.
- Backtests are educational only — outputs are not investment advice, and
  any text rendered to a user-facing channel must carry the SEBI disclaimer.
- Do not write backtest results to the production DB; the local CSV is the
  output of record.
