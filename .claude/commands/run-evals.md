---
description: Run the LLM eval suite against the current agent
argument-hint: [<eval_name_glob>]
---

# /run-evals — run the LLM eval suite

Run the eval suite under `tests/evals/`. With no argument, run everything.
With `$1`, pass it as a `-k` filter.

Steps:

1. Ensure `OPENAI_API_KEY` is set (read from `.env` for local dev).
2. Run: `pytest -q tests/evals/ -k "$1"` (or no `-k` if empty).
3. If any eval fails, print a one-line summary per failed eval (name +
   what was expected vs. observed) and stop — do **not** auto-fix.
4. Report total pass/fail counts and approximate token spend if the eval
   harness reports it.

Constraints:

- Evals use `gpt-4o-mini` by default to keep cost manageable. Only escalate
  to `gpt-4o` in evals that explicitly need stronger reasoning, and call
  this out in the eval file's docstring.
- Never commit cached eval outputs that contain real signal recommendations
  — use `EXAMPLE-ONLY` placeholders.
- Disclaimer-presence evals (`tests/evals/eval_disclaimer*.py`) are
  required to pass before any signal-surface PR merges.
