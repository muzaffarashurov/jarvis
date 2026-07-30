"""EP-021 Provider-Independent Embedding Engine.

Transforms text into embedding vectors only. This package must NOT
perform retrieval (that is EP-020's `src.core.retrieval`), must NOT
perform RAG, and must NOT perform chat completion (that is EP-014's
`src.core.ai`). It has no dependency on either of those packages.

Public API:
    EmbeddingProvider -- structural contract every embedding provider
        (local, cloud, or any future provider) must implement.
    EmbeddingProviderStatus -- lifecycle status a provider reports.
    EmbeddingProviderHealth -- configuration-derived readiness result.
    EmbeddingProviderError -- base class for provider-level errors.
    EmbeddingProviderConfigurationError -- disabled/unconfigured provider.
    EmbeddingProviderUnavailableError -- provider cannot currently serve requests.
    EmbeddingEngine -- batches, validates and requests embeddings from
        the currently selected provider.
    EmbeddingEngineError -- base class for engine-level errors.
    NoProviderSelectedError -- no provider is currently selected.
    EmbeddingValidationError -- a provider returned a malformed vector.
    EmbeddingManager -- owns provider selection, configuration loading,
        and provider lifecycle.
    EmbeddingProviderRegistryError -- duplicate provider registration.
    EmbeddingProviderNotFoundError -- unknown provider name.
"""

from __future__ import annotations

from src.core.embedding.engine import (
    EmbeddingEngine,
    EmbeddingEngineError,
    EmbeddingValidationError,
    NoProviderSelectedError,
)
from src.core.embedding.manager import (
    EmbeddingManager,
    EmbeddingProviderNotFoundError,
    EmbeddingProviderRegistryError,
)
from src.core.embedding.provider import (
    EmbeddingProvider,
    EmbeddingProviderConfigurationError,
    EmbeddingProviderError,
    EmbeddingProviderHealth,
    EmbeddingProviderStatus,
    EmbeddingProviderUnavailableError,
)

__all__ = [
    "EmbeddingProvider",
    "EmbeddingProviderStatus",
    "EmbeddingProviderHealth",
    "EmbeddingProviderError",
    "EmbeddingProviderConfigurationError",
    "EmbeddingProviderUnavailableError",
    "EmbeddingEngine",
    "EmbeddingEngineError",
    "NoProviderSelectedError",
    "EmbeddingValidationError",
    "EmbeddingManager",
    "EmbeddingProviderRegistryError",
    "EmbeddingProviderNotFoundError",
]
