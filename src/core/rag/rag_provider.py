"""RagProviderInfo domain model for the EP-022 RAG Engine.

A read-only view of the embedding provider (EP-021) currently backing
the RAG Engine's query-embedding step. This module defines no new
provider abstraction and performs no embedding itself -- provider
selection, configuration and lifecycle remain exclusively
`EmbeddingManager`'s concern (see `src/core/embedding/manager.py`).
This module only describes, for RAG-facing callers (`RagManager`,
`RagService`, `RagModule`), which embedding provider is currently in
use, so the "rag provider" / "rag use <provider>" CLI commands never
need to import `src.core.embedding.provider.EmbeddingProvider`
directly.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["RagProviderInfo", "RagProviderError", "NoEmbeddingProviderError"]


class RagProviderError(Exception):
    """Base class for every RAG-provider-related error."""


class NoEmbeddingProviderError(RagProviderError):
    """Raised when the RAG Engine needs an embedding provider but none is currently selected."""


@dataclass(frozen=True)
class RagProviderInfo:
    """A read-only snapshot of the embedding provider currently backing the RAG Engine.

    Attributes:
        name: The active embedding provider's registered name (e.g. "local").
        model: The active embedding provider's configured model identifier.
        dimension: The active embedding provider's fixed embedding dimension.
        available: Whether the provider is enabled and fully configured.
    """

    name: str
    model: str
    dimension: int
    available: bool
