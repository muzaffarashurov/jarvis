"""EP-020 Semantic Retrieval Engine.

A deterministic, read-only retrieval layer over the `ProjectIndex`
produced by EP-019 (`src.core.indexing`). Finds and ranks the most
relevant documents and chunks using plain keyword matching -- no AI,
no embeddings, no vector database. Intended as the foundation of a
later RAG pipeline; this package performs retrieval only (no CLI
integration -- see EP-020's task brief).

Public API:
    RetrievalEngine -- searches a ProjectIndex, returns ranked results.
    RankingEngine   -- deterministic keyword-based chunk scoring.
    Query           -- a normalized search request.
    RetrievalResult -- one ranked search result.
"""

from __future__ import annotations

from src.core.retrieval.query import Query
from src.core.retrieval.ranking import RankingEngine
from src.core.retrieval.result import RetrievalResult
from src.core.retrieval.retrieval_engine import RetrievalEngine

__all__ = [
    "Query",
    "RankingEngine",
    "RetrievalEngine",
    "RetrievalResult",
]
