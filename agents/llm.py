"""Single source of truth for LLM clients used across MarketPulse India.

Rules:
    * Provider is OpenAI. Do not add Anthropic / other SDKs here.
    * Import `llm_strong`, `llm_fast`, or `embeddings` from this module —
      never instantiate `ChatOpenAI` or `OpenAIEmbeddings` elsewhere.
    * Model names are env-overridable so evals / tests can swap them, but
      defaults are pinned in code so production behavior is deterministic.
"""

from __future__ import annotations

import os
from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

# ---------------------------------------------------------------------------
# Model identifiers — overridable for evals / staging via env, defaulted here
# so production behavior is deterministic without env config.
# ---------------------------------------------------------------------------
_STRONG_MODEL: str = os.getenv("LLM_STRONG_MODEL", "gpt-4o")
_FAST_MODEL: str = os.getenv("LLM_FAST_MODEL", "gpt-4o-mini")
_EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# Guard against .env copy-paste errors where a comment ends up as the org value.
# LangChain re-reads OPENAI_ORG_ID from os.environ at validator time, so the
# only reliable fix is to remove the var from the environment when it's invalid.
_raw_org = os.environ.get("OPENAI_ORG_ID", "").strip()
if _raw_org and not _raw_org.startswith("org-"):
    os.environ.pop("OPENAI_ORG_ID", None)
_ORG_ID: str | None = _raw_org if _raw_org.startswith("org-") else None


def _llm_kwargs(model: str) -> dict[str, object]:
    return {"model": model, "temperature": 0}


@lru_cache(maxsize=1)
def _build_llm_strong() -> ChatOpenAI:
    return ChatOpenAI(**_llm_kwargs(_STRONG_MODEL))  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def _build_llm_fast() -> ChatOpenAI:
    return ChatOpenAI(**_llm_kwargs(_FAST_MODEL))  # type: ignore[arg-type]


@lru_cache(maxsize=1)
def _build_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=_EMBEDDING_MODEL)


# Public, ready-to-use clients. Cached so callers share one instance.
llm_strong: ChatOpenAI = _build_llm_strong()
llm_fast: ChatOpenAI = _build_llm_fast()
embeddings: OpenAIEmbeddings = _build_embeddings()


__all__ = ["embeddings", "llm_fast", "llm_strong"]
