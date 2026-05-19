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


@lru_cache(maxsize=1)
def _build_llm_strong() -> ChatOpenAI:
    return ChatOpenAI(model=_STRONG_MODEL, temperature=0)


@lru_cache(maxsize=1)
def _build_llm_fast() -> ChatOpenAI:
    return ChatOpenAI(model=_FAST_MODEL, temperature=0)


@lru_cache(maxsize=1)
def _build_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(model=_EMBEDDING_MODEL)


# Public, ready-to-use clients. Cached so callers share one instance.
llm_strong: ChatOpenAI = _build_llm_strong()
llm_fast: ChatOpenAI = _build_llm_fast()
embeddings: OpenAIEmbeddings = _build_embeddings()


__all__ = ["embeddings", "llm_fast", "llm_strong"]
