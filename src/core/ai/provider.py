"""AI provider domain model for EP-014 AI Provider Manager.

Defines the abstraction every AI provider (Claude, OpenAI, Ollama, LM
Studio, Gemini, DeepSeek, OpenRouter, ...) must implement so the rest
of Jarvis never needs to know which provider is currently active. This
module owns no network access itself and no provider-specific
implementation: it is the structural contract only, matching the
pattern already used for the Plugin SDK (see src/core/plugins/plugin.py)
and the Process Catalog (see src/core/processes/process.py).

Per EP-014's "IMPORTANT" section, identity/status/configuration/health
never perform network requests. EP-015 (Claude Provider) additively
extends this contract with `ask()`, `ping()` and `list_models()` so a
provider that DOES implement real chat communication (e.g.
ClaudeProvider) can be used interchangeably through ProviderManager.
Their base implementations below are non-network no-ops so EP-014's
placeholder providers (ConfigDrivenProvider: openai, ollama, lmstudio)
remain valid AIProvider implementations without any changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ProviderStatus(str, Enum):
    """Lifecycle status a registered AI provider can report.

    Attributes:
        DISABLED: The provider is turned off in configuration
            ('providers.<name>.enabled' is False).
        NOT_CONFIGURED: The provider is enabled but is missing the
            configuration it needs to be usable (e.g. an API key or
            endpoint).
        AVAILABLE: The provider is enabled and fully configured.
    """

    DISABLED = "DISABLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    AVAILABLE = "AVAILABLE"


@dataclass(frozen=True)
class ProviderHealth:
    """Result of a provider's own `health()` check.

    This is a configuration-derived readiness check only -- per
    EP-014, no provider performs a network request to verify
    connectivity.

    Attributes:
        available: Whether the provider reports itself ready for use.
        message: Human-readable explanation of the health result.
    """

    available: bool
    message: str


@dataclass(frozen=True)
class ProviderResponse:
    """Result of a successful `AIProvider.ask()` call (EP-015).

    Attributes:
        text: The model's reply text.
        model: The model identifier that produced the reply.
        latency_ms: Wall-clock time the request took, in milliseconds.
    """

    text: str
    model: str
    latency_ms: float


@dataclass(frozen=True)
class PingResult:
    """Result of an `AIProvider.ping()` connectivity check (EP-015).

    Attributes:
        reachable: Whether the provider's API could be reached.
        latency_ms: Round-trip time for the check, in milliseconds.
        model: The model identifier used for the check.
        authenticated: Whether the configured credentials were
            accepted. Only meaningful when `reachable` is True.
        message: Human-readable detail, especially on failure.
    """

    reachable: bool
    latency_ms: float
    model: str
    authenticated: bool
    message: str


class ProviderError(Exception):
    """Base class for errors raised while talking to an AI provider (EP-015)."""


class ProviderConfigurationError(ProviderError):
    """Raised when a provider is disabled or missing required configuration."""


class ProviderAuthenticationError(ProviderError):
    """Raised when a provider rejects the configured credentials."""


class ProviderTimeoutError(ProviderError):
    """Raised when a provider request exceeds its configured timeout."""


class ProviderNetworkError(ProviderError):
    """Raised when a provider request fails due to a network problem."""


class ProviderRateLimitError(ProviderError):
    """Raised when a provider reports that a rate limit was exceeded."""


class ProviderUnavailableError(ProviderError):
    """Raised when a provider is unreachable or refuses to serve a request."""


class AIProvider(ABC):
    """Structural contract every AI provider must implement.

    Identity, configuration and health reporting (name/status/
    is_available/configuration/health) must never perform network
    requests (EP-014). `ask()`, `ping()` and `list_models()` are the
    EP-015 extension points for providers that DO implement real
    chat communication; their base implementations here are safe
    non-network no-ops so ProviderManager and the rest of Jarvis can
    treat any provider interchangeably without knowing which one is
    active.
    """

    @abstractmethod
    def name(self) -> str:
        """Return this provider's stable identifier (e.g. "ollama")."""
        raise NotImplementedError

    @abstractmethod
    def status(self) -> ProviderStatus:
        """Return this provider's current ProviderStatus."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether this provider is enabled and fully configured."""
        raise NotImplementedError

    @abstractmethod
    def configuration(self) -> dict[str, Any]:
        """Return a non-secret snapshot of this provider's configuration.

        Implementations must never include raw credentials (e.g. API
        keys) in the returned mapping, per this project's Logging
        Policy ("Never log secrets").
        """
        raise NotImplementedError

    @abstractmethod
    def health(self) -> ProviderHealth:
        """Return a configuration-derived readiness check.

        This is never a network connectivity check (EP-014 forbids
        network requests in this layer); it reflects whether this
        provider's own configuration looks usable.
        """
        raise NotImplementedError

    # ---------- EP-015: real communication extension points ----------

    def ask(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        """Send `prompt` to this provider and return its reply (EP-015).

        Base implementation always raises: this provider does not
        implement real chat communication. Providers that do (e.g.
        ClaudeProvider) must override this method.

        Args:
            prompt: The user prompt to send.
            max_tokens: Optional override for the reply's maximum
                token count. None uses the provider's configured
                default.

        Returns:
            The provider's reply.

        Raises:
            ProviderError: Always, unless overridden.
        """
        raise ProviderUnavailableError(
            f"Provider '{self.name()}' does not support chat requests."
        )

    def ping(self) -> PingResult:
        """Check whether this provider is reachable and authenticated (EP-015).

        Base implementation performs no network request and reports
        this provider as unreachable. Providers that implement real
        communication (e.g. ClaudeProvider) should override this
        method with an actual connectivity check.
        """
        return PingResult(
            reachable=False,
            latency_ms=0.0,
            model="",
            authenticated=False,
            message=f"Provider '{self.name()}' does not support ping.",
        )

    def list_models(self) -> list[str]:
        """Return the models available to this provider (EP-015).

        Never performs online discovery; models are read from this
        provider's own configuration. Base implementation returns an
        empty list.
        """
        return []
