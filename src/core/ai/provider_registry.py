"""Catalog registry for EP-014 AI Provider Manager.

ProviderRegistry stores the catalog of AIProvider instances known to
Jarvis (Claude, OpenAI, Ollama, LM Studio, ...). It performs no
provider construction (see ProviderFactory) and no current-provider
selection (see ProviderManager), matching this project's One
Responsibility Per Component rule and the pattern already used for the
Process Catalog (see src/core/processes/process_registry.py).
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.ai.provider import AIProvider


class ProviderRegistryError(Exception):
    """Raised for invalid catalog operations (e.g. duplicate provider name)."""


class ProviderNotFoundError(Exception):
    """Raised when an operation references a provider name not in the catalog."""


class ProviderRegistry:
    """Thread-safe catalog of AI providers known to the Provider Manager.

    Responsibilities:
        - Register a provider in the catalog.
        - Remove a provider from the catalog.
        - Return a single registered provider, raising if unknown.
        - Find a single registered provider without raising.
        - List all registered providers.
        - Report whether a given provider name is currently registered.
    """

    def __init__(self) -> None:
        """Initialize an empty ProviderRegistry."""
        self._providers: dict[str, AIProvider] = {}
        self._lock = Lock()

    def register(self, provider: AIProvider) -> None:
        """Register a provider in the catalog.

        Args:
            provider: The AIProvider to add, keyed by `provider.name()`.

        Raises:
            ProviderRegistryError: If a provider with the same name is
                already registered.
        """
        name = provider.name()
        with self._lock:
            if name in self._providers:
                raise ProviderRegistryError(f"Provider already registered: '{name}'.")
            self._providers[name] = provider
        logger.info(f"AI provider registered: '{name}'.")

    def remove(self, name: str) -> None:
        """Remove a provider from the catalog, if present.

        Args:
            name: The name of the provider to remove.
        """
        with self._lock:
            removed = self._providers.pop(name, None)
        if removed is not None:
            logger.info(f"AI provider removed: '{name}'.")

    def get(self, name: str) -> AIProvider:
        """Return a single registered provider.

        Args:
            name: The provider's registered name.

        Returns:
            The matching AIProvider.

        Raises:
            ProviderNotFoundError: If `name` is not registered.
        """
        provider = self.find(name)
        if provider is None:
            raise ProviderNotFoundError(f"Unknown AI provider: '{name}'.")
        return provider

    def find(self, name: str) -> AIProvider | None:
        """Return the catalog entry for a provider name, if registered.

        Args:
            name: The provider's registered name.

        Returns:
            The AIProvider, or None if not registered.
        """
        with self._lock:
            return self._providers.get(name)

    def list(self) -> list[AIProvider]:
        """Return every registered provider, ordered by name.

        Returns:
            A list of AIProvider entries sorted by `name()`.
        """
        with self._lock:
            return sorted(self._providers.values(), key=lambda provider: provider.name())

    def is_registered(self, name: str) -> bool:
        """Return whether a provider name is currently registered.

        Args:
            name: The name to check.

        Returns:
            True if a provider with this name exists in the catalog.
        """
        with self._lock:
            return name in self._providers
