---
description: Add a new tool to an existing MCP server
argument-hint: <server_name> <tool_name> [<short_description>]
---

# /add-mcp-tool — add a tool to an existing MCP server

Add a tool named `$2` to the MCP server at `mcp_servers/$1/`.

Steps:

1. In `mcp_servers/$1/tools.py`:
   - Add an `async def $2(...)` function.
   - Inputs and outputs are Pydantic v2 models (define them in the same
     file or in a shared `schemas.py` if reused).
   - Docstring explains: what it does, expected inputs, sample output,
     and whether the result is signal-bearing (i.e., requires the caller
     to attach the SEBI disclaimer).
2. In `mcp_servers/$1/server.py`:
   - Import the new tool and register it with the MCP server.
3. In `tests/test_mcp_$1.py`:
   - Add a test that calls the tool with a typed input and asserts the
     output shape.
4. Update `mcp_servers/$1/README.md` with a one-line entry for the tool.

Constraints:

- The tool must be `async`. No blocking I/O.
- If the tool calls an LLM, import `llm_strong` / `llm_fast` from
  `agents.llm`. Do not instantiate new clients.
- If the tool calls external APIs, use `httpx.AsyncClient` with a timeout.

Verify with `make lint` and `pytest -q tests/test_mcp_$1.py` before
reporting done.
