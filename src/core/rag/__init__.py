"""EP-022 Provider-Independent RAG (Retrieval-Augmented Generation) Engine.

Combines the Project Index Engine (EP-019, `src.core.indexing`), the
Semantic Retrieval Engine (EP-020, `src.core.retrieval`) and the
Embedding Engine (EP-021, `src.core.embedding`) into a single, reusable
context-generation pipeline: given a user query, obtain its embedding
(EP-021), retrieve and rank relevant chunks (EP-020), assemble the
highest-ranked chunks into context (read directly from EP-019's
ProjectIndex), and return a structured `RagResult`.

This package must NOT call any LLM, any AI provider, or perform chat
completion of any kind -- no import of `src.core.ai.*` anywhere here.
It performs no semantic (embedding-based) search of its own, persists
no embeddings, and uses no vector database: relevance ranking is
delegated entirely to EP-020's existing, deterministic RankingEngine.

Public API:
    RagEngine -- the provider-independent query -> RagResult pipeline.
    RagEngineError / EmptyQueryError / EmbeddingUnavailableError --
        RagEngine's own exception types.
    RagManager -- owns the RAG Engine's lifecycle: the current
        ProjectIndex/RetrievalEngine pairing, the selected embedding
        provider, and the enabled/disabled state of the RAG subsystem.
    RagManagerError / RagConfigurationError / RagDisabledError /
        IndexNotBuiltError -- RagManager's own exception types.
    RagProviderInfo -- a read-only snapshot of the embedding provider
        currently backing the RAG Engine.
    RagProviderError / NoEmbeddingProviderError -- raised when no
        embedding provider is currently selected.
    RagContextItem -- one retrieved chunk assembled into a RagResult's
        context.
    RagResult -- one complete, structured RAG pipeline result.
"""

from __future__ import annotations

from src.core.rag.rag_engine import (
    EmbeddingUnavailableError,
    EmptyQueryError,
    RagEngine,
    RagEngineError,
)
from src.core.rag.rag_manager import (
    IndexNotBuiltError,
    RagConfigurationError,
    RagDisabledError,
    RagManager,
    RagManagerError,
)
from src.core.rag.rag_provider import (
    NoEmbeddingProviderError,
    RagProviderError,
    RagProviderInfo,
)
from src.core.rag.rag_result import RagContextItem, RagResult

__all__ = [
    "RagEngine",
    "RagEngineError",
    "EmptyQueryError",
    "EmbeddingUnavailableError",
    "RagManager",
    "RagManagerError",
    "RagConfigurationError",
    "RagDisabledError",
    "IndexNotBuiltError",
    "RagProviderInfo",
    "RagProviderError",
    "NoEmbeddingProviderError",
    "RagContextItem",
    "RagResult",
]
