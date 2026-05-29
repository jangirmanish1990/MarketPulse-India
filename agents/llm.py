"""Single source of truth for LLM clients used across MarketPulse India.

Rules:
    * Provider is OpenAI. Do not add Anthropic / other SDKs here.
    * Call get_llm_strong(), get_llm_fast(), or get_embeddings() — never
      instantiate ChatOpenAI / OpenAIEmbeddings elsewhere.
    * When OPENAI_API_KEY is absent, getters return MockLLM so the app starts
      and serves cached data.  Any live-analysis node that calls the mock
      raises RuntimeError with a clear demo-mode message; stream_runner
      catches it and broadcasts the error over the WebSocket.
    * Model names are env-overridable for evals / staging.
"""

from __future__ import annotations

import os
from functools import lru_cache

from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# ---------------------------------------------------------------------------
# Model identifiers
# ---------------------------------------------------------------------------
_STRONG_MODEL: str = os.getenv("LLM_STRONG_MODEL", "gpt-4o")
_FAST_MODEL: str = os.getenv("LLM_FAST_MODEL", "gpt-4o-mini")
_EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# Guard against .env copy-paste errors where a comment ends up as the org value.
# LangChain re-reads OPENAI_ORG_ID from os.environ at validator time.
_raw_org = os.environ.get("OPENAI_ORG_ID", "").strip()
if _raw_org and not _raw_org.startswith("org-"):
    os.environ.pop("OPENAI_ORG_ID", None)

_DEMO_MSG = (
    "OPENAI_API_KEY is not configured — app is running in demo mode. "
    "Set OPENAI_API_KEY to enable live analysis."
)


# ---------------------------------------------------------------------------
# Mock LLM — returned by all getters when no API key is present
# ---------------------------------------------------------------------------

class MockLLM:
    """Stub LLM for key-less / demo deployments.

    Lets FastAPI start and serve the health endpoint, signals history, and
    sector rankings from the DB.  Any call that actually invokes the LLM
    (analysis pipeline nodes) raises RuntimeError(_DEMO_MSG) so the error
    surfaces in the WebSocket stream and is displayed in the UI.
    """

    def with_structured_output(self, schema: type, **kwargs: object) -> RunnableLambda:  # type: ignore[type-arg]
        async def _raise(inp: object) -> None:
            raise RuntimeError(_DEMO_MSG)
        return RunnableLambda(_raise)  # type: ignore[arg-type]

    def invoke(self, messages: object, **kwargs: object) -> None:
        raise RuntimeError(_DEMO_MSG)

    async def ainvoke(self, messages: object, **kwargs: object) -> None:
        raise RuntimeError(_DEMO_MSG)


# ---------------------------------------------------------------------------
# Public lazy getters — import these, never the module-level instances
# ---------------------------------------------------------------------------

def _llm_kwargs(model: str) -> dict[str, object]:
    return {"model": model, "temperature": 0}


@lru_cache(maxsize=1)
def get_llm_strong() -> ChatOpenAI | MockLLM:
    """Return gpt-4o client, or MockLLM when OPENAI_API_KEY is not set."""
    if not os.getenv("OPENAI_API_KEY"):
        return MockLLM()
    return ChatOpenAI(**_llm_kwargs(_STRONG_MODEL))  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def get_llm_fast() -> ChatOpenAI | MockLLM:
    """Return gpt-4o-mini client, or MockLLM when OPENAI_API_KEY is not set."""
    if not os.getenv("OPENAI_API_KEY"):
        return MockLLM()
    return ChatOpenAI(**_llm_kwargs(_FAST_MODEL))  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings | MockLLM:
    """Return text-embedding-3-small client, or MockLLM when key is absent."""
    if not os.getenv("OPENAI_API_KEY"):
        return MockLLM()
    return OpenAIEmbeddings(model=_EMBEDDING_MODEL)


__all__ = ["MockLLM", "get_embeddings", "get_llm_fast", "get_llm_strong"]
