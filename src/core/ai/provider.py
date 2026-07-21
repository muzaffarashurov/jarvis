"""AI provider domain model for EP-014 AI Provider Manager.

Defines the abstraction every AI provider (Claude, OpenAI, Ollama, LM
Studio, Gemini, DeepSeek, OpenRouter, ...) must implement so the rest
of Jarvis never needs to know which provider is currently active. This
module owns no network access, no chat/completion logic, and no
provider-specific implementation: it is the structural contract only,
matching the pattern already used for the Plugin SDK (see
src/core/plugins/plugin.py) and the Process Catalog (see
src/core/processes/process.py).

Per EP-014's "IMPORTANT" section, this abstraction never performs
network requests, calls any AI API, or implements chat/streaming;
concrete provider integrations (Claude, OpenAI, Ollama, ...) are left
to future EPs.
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


class AIProvider(ABC):
    """Structural contract every AI provider must implement.

    Implementations must never perform network requests, call an AI
    API, or implement chat/streaming (EP-014); they only describe
    their own identity, configuration, and configuration-derived
    readiness, so ProviderManager and the rest of Jarvis can treat any
    provider interchangeably without knowing which one is active.
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
