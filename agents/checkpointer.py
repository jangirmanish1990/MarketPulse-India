"""LangGraph Postgres checkpointer wired to MarketPulse India's Neon DB.

Usage:
    from agents.checkpointer import get_checkpointer

    async with get_checkpointer() as checkpointer:
        graph = builder.compile(checkpointer=checkpointer)
        await graph.ainvoke(...)

Run the self-test from the project root:
    python -m agents.checkpointer
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TypedDict, cast

from dotenv import load_dotenv

load_dotenv()

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph


# ---------------------------------------------------------------------------
def _to_psycopg_url(url: str) -> str:
    """Convert a SQLAlchemy asyncpg URL to a plain psycopg URL.

    LangGraph's `AsyncPostgresSaver` uses psycopg v3 directly (not via
    SQLAlchemy), so we strip the `+asyncpg` / `+psycopg` driver suffix and
    normalize the SSL query parameter (asyncpg: `ssl=`, psycopg: `sslmode=`).
    """
    if url.startswith("postgresql+asyncpg://"):
        url = "postgresql://" + url[len("postgresql+asyncpg://") :]
    elif url.startswith("postgresql+psycopg://"):
        url = "postgresql://" + url[len("postgresql+psycopg://") :]

    url = url.replace("?ssl=require", "?sslmode=require")
    url = url.replace("&ssl=require", "&sslmode=require")
    return url


def _get_checkpoint_url() -> str:
    raw = os.getenv("DATABASE_URL")
    if not raw:
        raise RuntimeError(
            "DATABASE_URL is not set. The LangGraph checkpointer reuses the "
            "same Neon Postgres database as the API; set it in .env."
        )
    return _to_psycopg_url(raw)


@asynccontextmanager
async def get_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    """Yield an `AsyncPostgresSaver` bound to the project's Postgres.

    The checkpoint tables (`checkpoints`, `checkpoint_writes`, …) are
    created lazily on first call via `setup()` — safe to call repeatedly.
    """
    conn_string = _get_checkpoint_url()
    async with AsyncPostgresSaver.from_conn_string(conn_string) as saver:
        await saver.setup()
        yield saver


# ---------------------------------------------------------------------------
# Self-test: save + resume a tiny graph's state under thread_id='test-001'.
# ---------------------------------------------------------------------------
_MARKER_VALUE = "checkpoint-test-v1"


class _TinyState(TypedDict):
    marker: str


async def _set_marker(_state: _TinyState) -> dict[str, str]:
    return {"marker": _MARKER_VALUE}


def _build_tiny_graph() -> Any:
    builder = StateGraph(_TinyState)
    builder.add_node("set_marker", cast(Any, _set_marker))
    builder.add_edge(START, "set_marker")
    builder.add_edge("set_marker", END)
    return builder


async def test_checkpoint_save_resume() -> bool:
    """Build a tiny graph, persist state under thread_id='test-001',
    rebuild the graph against the same checkpointer, and confirm the
    state was preserved.

    Returns True on success and prints "Checkpoint test PASSED".
    """
    thread_id = "test-001"
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    async with get_checkpointer() as checkpointer:
        # ----- save -----
        graph = _build_tiny_graph().compile(checkpointer=checkpointer)
        await graph.ainvoke({"marker": ""}, config=config)

        # ----- resume: rebuild from scratch, load checkpoint -----
        graph2 = _build_tiny_graph().compile(checkpointer=checkpointer)
        snapshot = await graph2.aget_state(config)

        recovered = snapshot.values.get("marker") if snapshot else None
        if recovered != _MARKER_VALUE:
            print(f"Checkpoint test FAILED: expected marker={_MARKER_VALUE!r}, got {recovered!r}")
            return False

    print("Checkpoint test PASSED")
    return True


def _main() -> int:
    # psycopg v3 requires SelectorEventLoop on Windows (incompatible with ProactorEventLoop).
    if sys.platform == "win32":
        import selectors

        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        ok = loop.run_until_complete(test_checkpoint_save_resume())
        loop.close()
    else:
        ok = asyncio.run(test_checkpoint_save_resume())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_main())


__all__ = ["get_checkpointer", "test_checkpoint_save_resume"]
