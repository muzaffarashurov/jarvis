"""Built-in embedding providers for EP-021 Embedding Engine.

Public API:
    LocalHashEmbeddingProvider -- fully offline, deterministic local
        provider (no network access, no third-party dependency).
    CloudEmbeddingProvider -- configuration-driven placeholder for a
        future real cloud embedding integration, matching EP-014's
        ConfigDrivenProvider precedent.
"""

from __future__ import annotations

from src.core.embedding.providers.cloud_provider import CloudEmbeddingProvider
from src.core.embedding.providers.local_provider import LocalHashEmbeddingProvider

__all__ = [
    "CloudEmbeddingProvider",
    "LocalHashEmbeddingProvider",
]
