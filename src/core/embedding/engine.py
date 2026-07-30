"""EP-021 Embedding Engine.

A provider-independent engine that transforms text into embedding
vectors: requests embeddings from the currently selected
EmbeddingProvider (via EmbeddingManager), batches multi-text requests,
validates every returned vector, and translates provider failures into
this module's own error types. This is the Embedding Engine's entire
responsibility -- it must NOT perform retrieval, NOT perform RAG, and
NOT perform chat completion (see src/core/embedding/__init__.py).

Depends only on EmbeddingManager and the EmbeddingProvider contract --
no ProjectIndex, no RetrievalEngine, no RankingEngine, no AIProvider,
no ContextLoader, no PromptBuilder, no PromptManager, no
ContextManager, matching EP-020's own dependency discipline
(src/core/retrieval/retrieval_engine.py).
"""

from __future__ import annotations

import math

from src.core.embedding.manager import EmbeddingManager
from src.core.embedding.provider import EmbeddingError, EmbeddingProvider, EmbeddingProviderError

__all__ = [
    "EmbeddingEngine",
    "EmbeddingEngineError",
    "NoProviderSelectedError",
    "EmbeddingValidationError",
]

DEFAULT_BATCH_SIZE = 16


class EmbeddingEngineError(EmbeddingError):
    """Base class for errors raised by the EmbeddingEngine itself.

    Inherits from `EmbeddingError` (src/core/embedding/provider.py) so
    callers can catch every embedding-related failure -- provider,
    engine, manager, or configuration -- with a single exception type.
    """


class NoProviderSelectedError(EmbeddingEngineError):
    """Raised when an embedding is requested but no provider is currently selected."""


class EmbeddingValidationError(EmbeddingEngineError):
    """Raised when a provider returns a vector that fails validation."""


class EmbeddingEngine:
    """Provider-independent text-to-vector engine.

    Never selects, constructs, or configures providers itself --
    provider selection and lifecycle are exclusively EmbeddingManager's
    concern (build/register/set_current/disable are never called from
    here). Never returns a provider's raw errors uncaught: every
    failure is either a validated result or one of this module's own
    EmbeddingEngineError subclasses.
    """

    def __init__(self, manager: EmbeddingManager, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        """Initialize the EmbeddingEngine.

        Args:
            manager: The EmbeddingManager used to resolve the currently
                active provider. Never mutated by this engine.
            batch_size: Maximum number of texts sent to a provider's
                `embed_many()` in a single call. Must be positive.

        Raises:
            ValueError: If `batch_size` is not a positive integer.
        """
        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        self._manager = manager
        self._batch_size = batch_size

    def embed_text(self, text: str) -> list[float]:
        """Request a single embedding vector for `text`.

        Args:
            text: The text to embed.

        Returns:
            A validated embedding vector of the active provider's
            `dimension()`.

        Raises:
            NoProviderSelectedError: If no embedding provider is
                currently selected (or the subsystem is disabled).
            EmbeddingValidationError: If the provider's returned vector
                fails validation.
            EmbeddingProviderError: If the provider itself fails to
                produce an embedding (e.g. disabled, not configured).
        """
        provider = self._require_current_provider()
        try:
            vector = provider.embed(text)
        except EmbeddingProviderError:
            raise
        self._validate_vector(vector, provider)
        return vector

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Request one embedding vector per entry in `texts`, batching requests.

        Args:
            texts: The texts to embed, in order.

        Returns:
            One validated embedding vector per entry in `texts`, in
            the same order. Empty list for an empty input.

        Raises:
            NoProviderSelectedError: If no embedding provider is
                currently selected (or the subsystem is disabled).
            EmbeddingValidationError: If any returned vector fails
                validation.
            EmbeddingProviderError: If the provider itself fails to
                produce embeddings (e.g. disabled, not configured).
        """
        if not texts:
            return []

        provider = self._require_current_provider()
        vectors: list[list[float]] = []
        for batch in self._batches(texts):
            batch_vectors = provider.embed_many(batch)
            self._validate_batch(batch, batch_vectors, provider)
            vectors.extend(batch_vectors)
        return vectors

    def dimension(self) -> int:
        """Return the currently active provider's embedding dimension.

        Returns:
            The active provider's `dimension()`.

        Raises:
            NoProviderSelectedError: If no embedding provider is
                currently selected (or the subsystem is disabled).
        """
        return self._require_current_provider().dimension()

    def _require_current_provider(self) -> EmbeddingProvider:
        """Return the currently selected provider, or raise if none is selected.

        Returns:
            The active EmbeddingProvider.

        Raises:
            NoProviderSelectedError: If no embedding provider is
                currently selected (or the subsystem is disabled).
        """
        provider = self._manager.get_current()
        if provider is None:
            raise NoProviderSelectedError(
                "No embedding provider is currently selected. Use 'embedding use <provider>'."
            )
        return provider

    def _batches(self, texts: list[str]) -> list[list[str]]:
        """Split `texts` into fixed-size batches of at most `self._batch_size`.

        Args:
            texts: The texts to split.

        Returns:
            `texts` split into consecutive batches, preserving order.
        """
        return [
            texts[start : start + self._batch_size]
            for start in range(0, len(texts), self._batch_size)
        ]

    def _validate_batch(
        self, batch: list[str], vectors: list[list[float]], provider: EmbeddingProvider
    ) -> None:
        """Validate that `vectors` is a well-formed, one-per-text response for `batch`.

        Args:
            batch: The texts that were sent to `provider.embed_many()`.
            vectors: The vectors `provider.embed_many()` returned.
            provider: The provider that produced `vectors`.

        Raises:
            EmbeddingValidationError: If `vectors` does not contain
                exactly one valid vector per entry in `batch`.
        """
        if len(vectors) != len(batch):
            raise EmbeddingValidationError(
                f"Provider '{provider.provider_name()}' returned {len(vectors)} vector(s) "
                f"for {len(batch)} text(s)."
            )
        for vector in vectors:
            self._validate_vector(vector, provider)

    def _validate_vector(self, vector: list[float], provider: EmbeddingProvider) -> None:
        """Validate a single embedding vector against `provider`'s declared dimension.

        Args:
            vector: The vector to validate.
            provider: The provider that produced `vector`.

        Raises:
            EmbeddingValidationError: If `vector` is not a list, its
                length does not match `provider.dimension()`, or any
                component is not a finite real number.
        """
        expected_dimension = provider.dimension()
        if not isinstance(vector, list):
            raise EmbeddingValidationError(
                f"Provider '{provider.provider_name()}' returned a non-list vector."
            )
        if len(vector) != expected_dimension:
            raise EmbeddingValidationError(
                f"Provider '{provider.provider_name()}' returned a vector of length "
                f"{len(vector)}, expected {expected_dimension}."
            )
        for component in vector:
            if not isinstance(component, (int, float)) or isinstance(component, bool):
                raise EmbeddingValidationError(
                    f"Provider '{provider.provider_name()}' returned a non-numeric "
                    "vector component."
                )
            if math.isnan(component) or math.isinf(component):
                raise EmbeddingValidationError(
                    f"Provider '{provider.provider_name()}' returned a non-finite "
                    "vector component."
                )
