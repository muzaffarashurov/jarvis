"""EmbeddingProvider domain model for EP-021 Embedding Engine.

Defines the abstraction every embedding provider (local, cloud, or any
future provider) must implement so the rest of Jarvis never needs to
know which embedding provider is currently active. This module owns
no network access and no provider-specific implementation: it is the
structural contract only, matching the pattern already used for the
AI Provider Framework (see src/core/ai/provider.py) and the Plugin SDK
(see src/core/plugins/plugin.py).

The Embedding Engine transforms text into embedding vectors only. It
must never perform retrieval, RAG, or chat completion (see this
package's __init__.py).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = [
    "EmbeddingProvider",
    "EmbeddingProviderStatus",
    "EmbeddingProviderHealth",
    "EmbeddingError",
    "EmbeddingConfigurationError",
    "EmbeddingProviderError",
    "EmbeddingProviderConfigurationError",
    "EmbeddingProviderUnavailableError",
]


class EmbeddingProviderStatus(str, Enum):
    """Lifecycle status a registered embedding provider can report.

    Attributes:
        DISABLED: The provider is turned off in configuration
            ('embedding.providers.<name>.enabled' is False).
        NOT_CONFIGURED: The provider is enabled but is missing the
            configuration it needs to be usable (e.g. an API key).
        AVAILABLE: The provider is enabled and fully configured.
    """

    DISABLED = "DISABLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    AVAILABLE = "AVAILABLE"


@dataclass(frozen=True)
class EmbeddingProviderHealth:
    """Result of a provider's own `health()` check.

    This is a configuration-derived readiness check only -- no
    provider performs a network request to verify connectivity as
    part of `health()`.

    Attributes:
        available: Whether the provider reports itself ready for use.
        message: Human-readable explanation of the health result.
    """

    available: bool
    message: str


class EmbeddingError(Exception):
    """Common root for every exception raised by the Embedding Engine (EP-021).

    Downstream packages (e.g. a future RAG Engine or Memory Manager)
    can catch this single type to handle "anything embedding-related"
    without needing to know about every specific failure mode
    (provider-level, engine-level, manager-level, or configuration-level).

    All other embedding exceptions -- `EmbeddingProviderError`,
    `EmbeddingConfigurationError`, and (see engine.py/manager.py)
    `EmbeddingEngineError`, `EmbeddingProviderRegistryError`,
    `EmbeddingProviderNotFoundError` -- inherit from this class. This
    is a backward-compatible change: every previously existing
    exception class keeps its name and its existing subclass
    relationships; only a shared ancestor was added above them.
    """


class EmbeddingConfigurationError(EmbeddingError):
    """Raised when 'embedding.*' configuration itself is invalid.

    This is distinct from `EmbeddingProviderConfigurationError`, which
    is a *runtime* condition (a provider is currently disabled or
    missing credentials, and may become available later without
    restarting). `EmbeddingConfigurationError` means the configuration
    value itself is malformed (wrong type, empty, or references a
    provider that does not exist) -- restarting with corrected
    configuration is required to resolve it. Raised instead of
    silently substituting a default value, per this project's
    Configuration Policy.
    """


class EmbeddingProviderError(EmbeddingError):
    """Base class for errors raised while using an embedding provider."""


class EmbeddingProviderConfigurationError(EmbeddingProviderError):
    """Raised when a provider is disabled or missing required configuration."""


class EmbeddingProviderUnavailableError(EmbeddingProviderError):
    """Raised when a provider cannot currently serve embedding requests."""


class EmbeddingProvider(ABC):
    """Structural contract every embedding provider must implement.

    Identity, configuration and health reporting
    (status/is_available/configuration/health) must never perform
    network requests, matching EP-014's AIProvider convention. This
    class is intentionally independent of `AIProvider`: an embedding
    provider never sends chat prompts and never completes
    conversations, so it must not be confused with (or made to
    implement) the chat-completion provider contract.
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return this provider's stable identifier (e.g. "local")."""
        raise NotImplementedError

    @abstractmethod
    def model_name(self) -> str:
        """Return the identifier of the embedding model this provider uses."""
        raise NotImplementedError

    @abstractmethod
    def dimension(self) -> int:
        """Return the fixed length of every vector this provider produces."""
        raise NotImplementedError

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Transform `text` into a single embedding vector.

        Args:
            text: The text to embed.

        Returns:
            A vector of length `dimension()`.

        Raises:
            EmbeddingProviderError: If this provider cannot currently
                produce an embedding (e.g. disabled, not configured,
                or otherwise unavailable).
        """
        raise NotImplementedError

    @abstractmethod
    def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Transform `texts` into one embedding vector per entry.

        Args:
            texts: The texts to embed, in order.

        Returns:
            One vector of length `dimension()` per entry in `texts`,
            in the same order.

        Raises:
            EmbeddingProviderError: If this provider cannot currently
                produce embeddings (e.g. disabled, not configured, or
                otherwise unavailable).
        """
        raise NotImplementedError

    # ---------- Lifecycle / diagnostics extension points ----------

    def status(self) -> EmbeddingProviderStatus:
        """Return this provider's current EmbeddingProviderStatus.

        Base implementation always reports AVAILABLE. Providers with
        an enabled/configured distinction (e.g. a cloud provider
        requiring an API key) should override this method.
        """
        return EmbeddingProviderStatus.AVAILABLE

    def is_available(self) -> bool:
        """Return whether this provider is enabled and fully configured."""
        return self.status() == EmbeddingProviderStatus.AVAILABLE

    def configuration(self) -> dict[str, Any]:
        """Return a non-secret snapshot of this provider's configuration.

        Implementations must never include raw credentials (e.g. API
        keys) in the returned mapping, per this project's Logging
        Policy ("Never log secrets").
        """
        return {}

    def health(self) -> EmbeddingProviderHealth:
        """Return a configuration-derived readiness check (no network access)."""
        if self.is_available():
            return EmbeddingProviderHealth(
                available=True, message=f"Provider '{self.provider_name()}' is configured."
            )
        return EmbeddingProviderHealth(
            available=False,
            message=f"Provider '{self.provider_name()}' is not available.",
        )
