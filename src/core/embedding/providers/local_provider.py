"""Local embedding provider for EP-021 Embedding Engine.

LocalHashEmbeddingProvider is a fully offline embedding provider: it
performs no network access and requires no third-party dependency,
matching this project's Existing Dependencies Policy ("Never
introduce a new third-party dependency unless explicitly requested").
Vectors are derived deterministically from the input text using only
the standard library (`hashlib`), so identical input always produces
the identical output vector -- useful as a default, always-available
"local" provider and as a stable fixture for automated tests.

This is not a semantic embedding model. It exists to demonstrate and
exercise the provider-independent Embedding Engine architecture with a
real, working, dependency-free local provider; a genuine local model
integration (e.g. sentence-transformers) can replace it later as its
own Engineering Package without changing `EmbeddingProvider`,
`EmbeddingEngine`, `EmbeddingManager`, or `EmbeddingService`.
"""

from __future__ import annotations

import hashlib
from typing import Any

from src.core.embedding.provider import (
    EmbeddingProvider,
    EmbeddingProviderConfigurationError,
    EmbeddingProviderHealth,
    EmbeddingProviderStatus,
)

_UINT64_MAX = (2**64) - 1


class LocalHashEmbeddingProvider(EmbeddingProvider):
    """Deterministic, offline embedding provider backed by SHA-256 hashing."""

    def __init__(self, enabled: bool, model: str, dimension: int) -> None:
        """Initialize the LocalHashEmbeddingProvider.

        Args:
            enabled: Value of 'embedding.providers.local.enabled'.
            model: Value of 'embedding.providers.local.model'; purely
                a label, since this provider uses no real model.
            dimension: Value of 'embedding.providers.local.dimension'.
                The fixed length of every vector this provider
                produces.

        Raises:
            ValueError: If `dimension` is not a positive integer.
        """
        if dimension <= 0:
            raise ValueError("Local embedding provider dimension must be positive.")
        self._enabled = enabled
        self._model = model
        self._dimension = dimension

    def provider_name(self) -> str:
        """Return this provider's stable identifier: "local"."""
        return "local"

    def model_name(self) -> str:
        """Return this provider's configured model label."""
        return self._model

    def dimension(self) -> int:
        """Return the fixed vector length this provider produces."""
        return self._dimension

    def embed(self, text: str) -> list[float]:
        """Deterministically transform `text` into a single embedding vector.

        Args:
            text: The text to embed.

        Returns:
            A vector of length `dimension()`, with values in [-1.0, 1.0].

        Raises:
            EmbeddingProviderConfigurationError: If this provider is disabled.
        """
        if not self._enabled:
            raise EmbeddingProviderConfigurationError(
                "Local embedding provider is disabled ('embedding.providers.local.enabled')."
            )
        return [self._hash_component(text, index) for index in range(self._dimension)]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Deterministically transform `texts` into one embedding vector each.

        Args:
            texts: The texts to embed, in order.

        Returns:
            One vector of length `dimension()` per entry in `texts`.

        Raises:
            EmbeddingProviderConfigurationError: If this provider is disabled.
        """
        return [self.embed(text) for text in texts]

    def status(self) -> EmbeddingProviderStatus:
        """Return DISABLED if this provider is turned off, else AVAILABLE.

        This provider requires no credentials, so it is never
        NOT_CONFIGURED.
        """
        if not self._enabled:
            return EmbeddingProviderStatus.DISABLED
        return EmbeddingProviderStatus.AVAILABLE

    def configuration(self) -> dict[str, Any]:
        """Return a non-secret snapshot of this provider's configuration."""
        return {"enabled": self._enabled, "model": self._model, "dimension": self._dimension}

    def health(self) -> EmbeddingProviderHealth:
        """Return a configuration-derived readiness check (no network access)."""
        if not self._enabled:
            return EmbeddingProviderHealth(
                available=False, message="Local embedding provider is disabled."
            )
        return EmbeddingProviderHealth(
            available=True, message="Local embedding provider is configured."
        )

    @staticmethod
    def _hash_component(text: str, index: int) -> float:
        """Derive one deterministic vector component from `text` and `index`.

        Args:
            text: The full input text.
            index: The vector component's position, mixed into the
                hash input so every component of the same text's
                vector differs.

        Returns:
            A float in [-1.0, 1.0], deterministic for a given
            `(text, index)` pair.
        """
        digest = hashlib.sha256(f"{text}:{index}".encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], byteorder="big", signed=False)
        return (value / _UINT64_MAX) * 2.0 - 1.0
