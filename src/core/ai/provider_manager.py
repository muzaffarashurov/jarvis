"""Provider selection for EP-014 AI Provider Manager.

ProviderManager is the single place that knows which AI provider is
currently active, keeping that choice entirely in memory so `ai use
<provider>` takes effect immediately -- no restart required, and no
write back to config/config.yaml (Config exposes no write path; see
src/core/config.py). Provider construction is delegated to
ProviderFactory and catalog storage to ProviderRegistry, so this class
owns current-provider/enabled-state selection only, per this project's
One Responsibility Per Component rule.

The rest of Jarvis is expected to depend only on ProviderManager (via
AIService), never on ProviderRegistry or a concrete AIProvider
directly, so the active provider can change without any other
component needing to know which one is active.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.ai.provider import AIProvider
from src.core.ai.provider_registry import ProviderRegistry


class ProviderManager:
    """Owns the currently active AI provider and the AI subsystem's enabled state.

    Responsibilities:
        - Register a provider with the underlying ProviderRegistry.
        - Return a single registered provider.
        - Select and report the currently active provider.
        - List every registered provider.
        - Disable the AI subsystem as a whole.
    """

    def __init__(
        self, registry: ProviderRegistry, enabled: bool, default_provider: str | None
    ) -> None:
        """Initialize the ProviderManager.

        Args:
            registry: Catalog of known AI providers.
            enabled: Initial value of 'ai.enabled' from configuration.
            default_provider: Initial value of 'ai.default_provider'
                from configuration. "none" (or None) means no provider
                is selected at startup.
        """
        self._registry = registry
        self._enabled = enabled
        self._current_name: str | None = (
            default_provider
            if default_provider and default_provider.lower() != "none"
            else None
        )
        self._lock = Lock()

    # ---------- Required API ----------

    def register_provider(self, provider: AIProvider) -> None:
        """Register a provider so it can later be selected by `set_current()`.

        Args:
            provider: The AIProvider to register.

        Raises:
            ProviderRegistryError: If a provider with the same name is
                already registered.
        """
        self._registry.register(provider)

    def get_provider(self, name: str) -> AIProvider:
        """Return a single registered provider by name.

        Args:
            name: The provider's registered name.

        Returns:
            The matching AIProvider.

        Raises:
            ProviderNotFoundError: If `name` is not registered.
        """
        return self._registry.get(name)

    def set_current(self, name: str) -> None:
        """Select the currently active provider.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            name: The registered provider name to activate.

        Raises:
            ProviderNotFoundError: If `name` is not registered.
        """
        self._registry.get(name)  # raises ProviderNotFoundError if unknown
        with self._lock:
            self._current_name = name
        logger.info(f"AI current provider set to '{name}'.")

    def get_current(self) -> AIProvider | None:
        """Return the currently active provider.

        Returns:
            The active AIProvider, or None if no provider is selected.
        """
        with self._lock:
            current_name = self._current_name
        if current_name is None:
            return None
        return self._registry.find(current_name)

    def list_providers(self) -> list[AIProvider]:
        """Return every registered provider."""
        return self._registry.list()

    # ---------- AI subsystem enable/disable ----------

    def is_enabled(self) -> bool:
        """Return whether the AI subsystem is currently enabled."""
        with self._lock:
            return self._enabled

    def disable(self) -> None:
        """Disable the AI subsystem and clear the current provider selection."""
        with self._lock:
            self._enabled = False
            self._current_name = None
        logger.info("AI subsystem disabled.")
