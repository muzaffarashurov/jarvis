"""Provider construction for EP-014 AI Provider Manager.

ProviderFactory is the single place that knows how to turn
'providers.*' configuration entries (see config/config.yaml) into
AIProvider instances. Per EP-014 ("Actual provider implementations
will be added in future EPs"), it does not integrate with any real AI
API: every provider it builds is a `ConfigDrivenProvider`, whose
status/availability/health are derived entirely from
'providers.<name>' configuration values, with no network request of
any kind.
"""

from __future__ import annotations

from typing import Any

from src.core.ai.provider import AIProvider, ProviderHealth, ProviderStatus
from src.core.config import Config

# Provider names Jarvis's configuration currently recognizes (see
# 'providers.*' in config/config.yaml). Gemini, DeepSeek and
# OpenRouter are named as future providers in EP-014's task brief but
# have no 'providers.*' configuration section yet, so they are not
# built here -- adding their configuration section is left to the EP
# that implements them, per the Configuration Policy.
KNOWN_PROVIDER_NAMES: tuple[str, ...] = ("claude", "openai", "ollama", "lmstudio")

# Configuration key each known provider uses to describe how it is
# reached: API-key-based providers vs. endpoint-based local providers.
_CREDENTIAL_KEYS: dict[str, str] = {
    "claude": "api_key",
    "openai": "api_key",
    "ollama": "endpoint",
    "lmstudio": "endpoint",
}


class ConfigDrivenProvider(AIProvider):
    """An AIProvider whose state is derived entirely from configuration.

    Placeholder implementation for EP-014's Provider Management layer:
    it never calls an AI API, never performs a network request, and
    never implements chat or streaming. Concrete provider integrations
    replace this class in future EPs (see EP-014's task brief).
    """

    def __init__(
        self, name: str, enabled: bool, credential_key: str, credential_value: str
    ) -> None:
        """Initialize the ConfigDrivenProvider.

        Args:
            name: The provider's stable identifier (e.g. "ollama").
            enabled: Value of 'providers.<name>.enabled'.
            credential_key: Which configuration key this provider is
                configured through ("api_key" or "endpoint").
            credential_value: The raw configured value for
                `credential_key`, used only to determine whether the
                provider is configured -- never returned or logged.
        """
        self._name = name
        self._enabled = enabled
        self._credential_key = credential_key
        self._configured = bool(credential_value.strip())

    def name(self) -> str:
        """Return this provider's stable identifier."""
        return self._name

    def status(self) -> ProviderStatus:
        """Return this provider's current ProviderStatus."""
        if not self._enabled:
            return ProviderStatus.DISABLED
        if not self._configured:
            return ProviderStatus.NOT_CONFIGURED
        return ProviderStatus.AVAILABLE

    def is_available(self) -> bool:
        """Return whether this provider is enabled and fully configured."""
        return self._enabled and self._configured

    def configuration(self) -> dict[str, Any]:
        """Return a non-secret snapshot of this provider's configuration."""
        return {
            "enabled": self._enabled,
            "configured": self._configured,
            "credential_key": self._credential_key,
        }

    def health(self) -> ProviderHealth:
        """Return a configuration-derived readiness check (no network access)."""
        if not self._enabled:
            return ProviderHealth(available=False, message=f"Provider '{self._name}' is disabled.")
        if not self._configured:
            return ProviderHealth(
                available=False,
                message=f"Provider '{self._name}' is missing '{self._credential_key}'.",
            )
        return ProviderHealth(available=True, message=f"Provider '{self._name}' is configured.")


class ProviderFactory:
    """Builds AIProvider instances from 'providers.*' configuration."""

    def __init__(self, config: Config) -> None:
        """Initialize the ProviderFactory.

        Args:
            config: Loaded application configuration.
        """
        self._config = config

    def build_all(self) -> list[AIProvider]:
        """Build every known provider from 'providers.*' configuration.

        Returns:
            One ConfigDrivenProvider per name in KNOWN_PROVIDER_NAMES.
        """
        return [self.build(name) for name in KNOWN_PROVIDER_NAMES]

    def build(self, name: str) -> AIProvider:
        """Build a single provider from its 'providers.<name>' section.

        Args:
            name: The provider name to build (must be one of
                KNOWN_PROVIDER_NAMES).

        Returns:
            A ConfigDrivenProvider reflecting `name`'s current
            configuration.

        Raises:
            ValueError: If `name` is not a known provider name.
        """
        if name not in _CREDENTIAL_KEYS:
            raise ValueError(f"Unknown AI provider name: '{name}'.")

        credential_key = _CREDENTIAL_KEYS[name]
        enabled = bool(self._config.get(f"providers.{name}.enabled", False))
        credential_value = self._config.get(f"providers.{name}.{credential_key}", "")
        if not isinstance(credential_value, str):
            credential_value = ""

        return ConfigDrivenProvider(
            name=name,
            enabled=enabled,
            credential_key=credential_key,
            credential_value=credential_value,
        )
