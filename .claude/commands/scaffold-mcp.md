---
description: Scaffold a new MCP server under mcp_servers/<name>/
argument-hint: <server_name> [<short_description>]
---

# /scaffold-mcp — create a new MCP server skeleton

Create a new MCP server at `mcp_servers/$1/`:

```
mcp_servers/$1/
  __init__.py
  server.py        # entrypoint; instantiates Server() and registers tools
  tools.py         # one async function per tool, typed with Pydantic v2
  README.md        # what the server does, how to run it
```

`server.py` should:

- Use the `mcp` Python SDK (already in `pyproject.toml`).
- Register tools imported from `tools.py`.
- Run via `python -m mcp_servers.$1.server` (stdio transport for local dev).
- Read configuration from environment variables documented in `.env.example`
  (add new variables there if you introduce any).

After scaffolding:

1. Add an entry for the server to `.claude/.mcp.json`.
2. Add a smoke test in `tests/test_mcp_$1.py` that imports the server and
   asserts each registered tool is callable.
3. Update the root `README.md` MCP server table (if one exists).

Constraints:

- Async tools only — no blocking I/O.
- Tool input/output types are Pydantic v2 models.
- If a tool returns signal-bearing data, the disclaimer is the caller's
  responsibility; document this clearly in the tool docstring.

Verify with `make lint` before reporting done.
