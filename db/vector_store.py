"""pgvector vector store for MarketPulse India financial documents.

Uses langchain-postgres PGVector backed by PostgreSQL with the pgvector
extension. Embeddings are sourced from agents.llm (text-embedding-3-small)
per the project rule that all LLM/embedding clients live in agents/llm.py.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.documents import Document
from langchain_postgres import PGVector

from agents.llm import embeddings

COLLECTION_NAME = "marketpulse_india_docs"


def _pg_conn_str() -> str:
    """Build a psycopg3-compatible URL for langchain-postgres.

    Prefers DATABASE_URL so cloud URLs (.env) take precedence over stale
    shell values of DATABASE_SYNC_URL.

    Translations applied:
      +asyncpg  → +psycopg   (dialect swap)
      ?ssl=require → ?sslmode=require  (asyncpg param → libpq/psycopg3 param)
    """
    url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_SYNC_URL", "")
    url = url.replace("+asyncpg", "+psycopg")
    # asyncpg uses ?ssl=require; psycopg3/libpq uses ?sslmode=require
    url = url.replace("?ssl=require", "?sslmode=require")
    url = url.replace("&ssl=require", "&sslmode=require")
    return url


def get_vector_store() -> PGVector:
    """Return a configured PGVector store.

    Creates the pgvector extension and collection tables on first run.
    Requires the pgvector extension to be available in the database.
    """
    return PGVector(
        embeddings=embeddings,
        collection_name=COLLECTION_NAME,
        connection=_pg_conn_str(),
        use_jsonb=True,
    )


def add_documents(docs: list[dict[str, Any]]) -> None:
    """Embed and store a list of document dicts into pgvector.

    Each dict must have:
        content  — text to embed
        metadata — dict with keys: nse_symbol, announcement_type, quarter,
                   company_name, sector, date_ist, source
    """
    vs = get_vector_store()
    lc_docs = [Document(page_content=d["content"], metadata=d["metadata"]) for d in docs]
    vs.add_documents(lc_docs)


def search_similar(
    query: str,
    *,
    nse_symbol: str | None = None,
    announcement_type: str | None = None,
    k: int = 10,
) -> list[dict[str, Any]]:
    """Similarity search with optional metadata filters.

    When nse_symbol is provided, searches company-specific docs (k=6) first,
    then appends a general peer search (k=4) for broader context.
    Results are deduplicated by the first 100 chars of content.
    """
    vs = get_vector_store()
    all_results: list[tuple[Document, float]] = []

    if nse_symbol:
        company_filter: dict[str, Any] = {"nse_symbol": nse_symbol}
        if announcement_type:
            company_filter["announcement_type"] = announcement_type

        company_results: list[tuple[Document, float]] = vs.similarity_search_with_score(
            query, k=6, filter=company_filter
        )
        all_results.extend(company_results)

        # Peer/general context docs
        peer_results: list[tuple[Document, float]] = vs.similarity_search_with_score(query, k=4)
        all_results.extend(peer_results)
    else:
        all_results = vs.similarity_search_with_score(query, k=k)

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for doc, score in all_results:
        key = doc.page_content[:100]
        if key not in seen:
            seen.add(key)
            deduped.append(
                {
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                    "score": float(score),
                }
            )

    return deduped


def search_by_sector(sector: str, k: int = 4) -> list[dict[str, Any]]:
    """Search for documents from the same sector (peer company context)."""
    vs = get_vector_store()
    results: list[tuple[Document, float]] = vs.similarity_search_with_score(
        sector, k=k, filter={"sector": sector}
    )
    return [
        {
            "content": doc.page_content,
            "metadata": doc.metadata,
            "score": float(score),
        }
        for doc, score in results
    ]


__all__ = [
    "COLLECTION_NAME",
    "add_documents",
    "get_vector_store",
    "search_by_sector",
    "search_similar",
]
