---
description: Verify SEBI disclaimer coverage on signal-bearing surfaces
argument-hint: [<path>]
---

# /check-sebi — verify SEBI disclaimer coverage

Verify that every signal-bearing surface in the repo (or under `$1` if
given) carries the SEBI disclaimer.

The canonical disclaimer text:

```
⚠️ MarketPulse India is not a SEBI-registered investment advisor.
Output is for educational/informational purposes only and is not
investment advice. Markets carry risk; consult a registered advisor
before making decisions.
```

Steps:

1. Grep the repo (or `$1`) for likely signal surfaces:
   - Files under `backend/routers/` returning JSON containing keys like
     `signal`, `recommendation`, `target_price`, `verdict`.
   - LangGraph nodes that produce user-facing text (`agents/nodes/*.py`).
   - Frontend components rendering signal data.
   - MCP tool docstrings that mark themselves as signal-bearing.
2. For each surface, confirm the disclaimer is included either:
   - Inline in the response payload (preferred for API/MCP), or
   - Wrapped by a shared helper (`backend/disclaimer.py` /
     `frontend/lib/disclaimer.ts`) that's clearly applied.
3. Report a table of: surface → disclaimer present (yes/no) → location.
4. If any surface is missing the disclaimer, stop and ask the user before
   patching — there may be deliberate reasons (e.g., a raw-data endpoint
   that intentionally returns no commentary).

Constraints:

- Do not silently rewrite signal text — disclaimer fixes are visible
  changes and should land in their own commit.
- Match the disclaimer exactly. Truncated / paraphrased versions don't count.
