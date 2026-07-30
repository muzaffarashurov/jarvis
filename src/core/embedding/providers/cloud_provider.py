"""Cloud embedding provider placeholder for EP-021 Embedding Engine.

CloudEmbeddingProvider mirrors EP-014's `ConfigDrivenProvider`
precedent (see src/core/ai/provider_factory.py): its
status/availability/health are derived entirely from
'embedding.providers.cloud' configuration, with no network request of
any kind performed by this Engineering Package. Per
AI_GENERATION_STANDARD.md's Unknown API Policy ("If a required method
does not exist, DO NOT invent it"), this provider does not invent a
concrete cloud embedding API integration; a real cloud provider (e.g.
OpenAI, Cohere) can replace or extend it in a future Engineering
Package without changing `EmbeddingProvider`, `EmbeddingEngine`,
`EmbeddingManager`, or `EmbeddingService`.
"""

from __future__ import annotations

from typing import Any

from src.core.embedding.provider import (
    EmbeddingProvider,
    EmbeddingProviderConfigurationError,
    EmbeddingProviderHealth,
    EmbeddingProviderStatus,
    EmbeddingProviderUnavailableError,
)


class CloudEmbeddingProvider(EmbeddingProvider):
    """A cloud EmbeddingProvider whose state is derived entirely from configuration.

    Placeholder implementation: it never calls a cloud embedding API
    and never performs a network request. A concrete cloud
    integration replaces this class in a future Engineering Package.
    """

    def __init__(self, enabled: bool, api_key: str, model: str, dimension: int) -> None:
        """Initialize the CloudEmbeddingProvider.

        Args:
            enabled: Value of 'embedding.providers.cloud.enabled'.
            api_key: Value of 'embedding.providers.cloud.api_key',
                used only to determine whether the provider is
                configured -- never returned or logged.
            model: Value of 'embedding.providers.cloud.model'.
            dimension: Value of 'embedding.providers.cloud.dimension'.
                The fixed length of every vector this provider would
                produce.

        Raises:
            ValueError: If `dimension` is not a positive integer.
        """
        if dimension <= 0:
            raise ValueError("Cloud embedding provider dimension must be positive.")
        self._enabled = enabled
        self._configured = bool(api_key.strip())
        self._model = model
        self._dimension = dimension

    def provider_name(self) -> str:
        """Return this provider's stable identifier: "cloud"."""
        return "cloud"

    def model_name(self) -> str:
        """Return this provider's configured model identifier."""
        return self._model

    def dimension(self) -> int:
        """Return the fixed vector length this provider would produce."""
        return self._dimension

    def embed(self, text: str) -> list[float]:
        """Raise, since this Engineering Package performs no cloud network access.

        Args:
            text: The text that would be embedded.

        Raises:
            EmbeddingProviderConfigurationError: If this provider is
                disabled or missing 'api_key'.
            EmbeddingProviderUnavailableError: If this provider is
                enabled and configured, since real cloud communication
                is not implemented by this Engineering Package.
        """
        self._require_configured()
        raise EmbeddingProviderUnavailableError(
            "Cloud embedding provider is configured but does not perform network "
            "requests in this Engineering Package (EP-021)."
        )

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Raise, since this Engineering Package performs no cloud network access.

        Args:
            texts: The texts that would be embedded.

        Raises:
            EmbeddingProviderConfigurationError: If this provider is
                disabled or missing 'api_key'.
            EmbeddingProviderUnavailableError: If this provider is
                enabled and configured, since real cloud communication
                is not implemented by this Engineering Package.
        """
        self._require_configured()
        raise EmbeddingProviderUnavailableError(
            "Cloud embedding provider is configured but does not perform network "
            "requests in this Engineering Package (EP-021)."
        )

    def status(self) -> EmbeddingProviderStatus:
        """Return this provider's current EmbeddingProviderStatus."""
        if not self._enabled:
            return EmbeddingProviderStatus.DISABLED
        if not self._configured:
            return EmbeddingProviderStatus.NOT_CONFIGURED
        return EmbeddingProviderStatus.AVAILABLE

    def configuration(self) -> dict[str, Any]:
        """Return a non-secret snapshot of this provider's configuration."""
        return {"enabled": self._enabled, "configured": self._configured, "model": self._model}

    def health(self) -> EmbeddingProviderHealth:
        """Return a configuration-derived readiness check (no network access)."""
        if not self._enabled:
            return EmbeddingProviderHealth(
                available=False, message="Cloud embedding provider is disabled."
            )
        if not self._configured:
            return EmbeddingProviderHealth(
                available=False, message="Cloud embedding provider is missing 'api_key'."
            )
        return EmbeddingProviderHealth(
            available=True, message="Cloud embedding provider is configured."
        )

    def _require_configured(self) -> None:
        """Raise EmbeddingProviderConfigurationError if disabled or unconfigured."""
        if not self._enabled:
            raise EmbeddingProviderConfigurationError(
                "Cloud embedding provider is disabled ('embedding.providers.cloud.enabled')."
            )
        if not self._configured:
            raise EmbeddingProviderConfigurationError(
                "Cloud embedding provider is missing 'embedding.providers.cloud.api_key'."
            )
