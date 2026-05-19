---
description: Scaffold a new LangGraph agent node under agents/nodes/<name>.py
argument-hint: <node_name> [<short_description>]
---

# /scaffold-node — create a new LangGraph node

Create a new node file at `agents/nodes/$1.py` with:

1. An `async def $1(state: AgentState) -> dict` signature.
2. A short module docstring summarising what the node does ($2 if given).
3. An import of `llm_strong` / `llm_fast` from `agents.llm` (commented if not
   used yet) — never instantiate `ChatOpenAI` here.
4. A typed return value that updates a single, named slot on `AgentState`.

Then:

- Register the node in `agents/graph.py` (add edge wiring, even if just from
  `START` for now).
- Create a stub test in `tests/test_node_$1.py` using `pytest-asyncio`,
  asserting the node returns the expected key.
- Add a stub eval in `tests/evals/eval_$1.py` if the node produces
  user-facing or signal-bearing output.

Constraints:

- IST timestamps only (`datetime.now(ZoneInfo("Asia/Kolkata"))`).
- If the node emits signal-bearing text, append the SEBI disclaimer and run
  `/check-sebi` after the change.
- Do not add new top-level dependencies without updating `pyproject.toml`.

Verify with `make lint` and `pytest -q tests/test_node_$1.py` before
reporting done.
