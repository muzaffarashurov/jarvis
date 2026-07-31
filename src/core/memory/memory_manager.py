"""Central Memory Manager for EP-023.

`MemoryManager` is a pure orchestration layer over registered
`MemoryProvider` instances: registration, enable/disable, active-
provider switching, and delegation of the unified store/load/delete/
clear/exists/list API to whichever provider is currently active. It
implements no storage logic of its own -- concrete storage stays
inside each `MemoryProvider` (e.g. `MemoryStoreProvider`, wrapping the
existing EP-013 `MemoryStore`).

Mirrors the manager-over-registered-providers pattern already used by
`EmbeddingManager`/`RagManager` (see `src/core/embedding/manager.py`
and `src/core/rag/rag_manager.py`), scoped down to EP-023's own
responsibilities: registration, enablement and active-provider
switching only -- no indexing, retrieval, embeddings, or RAG.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from src.core.memory.memory_provider import MemoryProvider, MemoryProviderError, ProviderStatus


@dataclass(frozen=True)
class ManagerStatus:
    """Status snapshot returned by `MemoryManager.status()`.

    Attributes:
        active_provider: Name of the currently active provider, or
            None if no provider is registered/active.
        provider_count: Number of registered providers.
        providers: Per-provider status snapshots, sorted by name.
    """

    active_provider: str | None
    provider_count: int
    providers: list[ProviderStatus]


class MemoryManager:
    """Orchestrates registered `MemoryProvider` instances.

    Responsibilities:
        - register / unregister providers
        - enable / disable providers
        - switch the active provider
        - expose the active provider and per-provider status
        - delegate the unified memory API to the active provider

    `MemoryManager` owns no storage state of its own; every entry
    lives inside whichever `MemoryProvider` is currently active.
    """

    def __init__(self, default_provider: str | None = None) -> None:
        """Initialize an empty `MemoryManager`.

        Args:
            default_provider: Name to activate automatically once a
                matching provider is registered (see `register`).
                Typically resolved from 'memory.default_provider' by
                the caller (`MemoryService`). If None, the first
                enabled provider registered becomes active.
        """
        self._providers: dict[str, MemoryProvider] = {}
        self._enabled: dict[str, bool] = {}
        self._active: str | None = None
        self._default_provider = default_provider

    # ---------- Registration ----------

    def register(self, provider: MemoryProvider, enabled: bool = True) -> None:
        """Register a provider under its own `name`.

        Args:
            provider: The `MemoryProvider` instance to register.
            enabled: Whether the provider starts enabled.

        If no provider is currently active, this provider is enabled,
        and either no default was configured or this provider's name
        matches the configured default, it becomes active.
        """
        name = provider.name
        self._providers[name] = provider
        self._enabled[name] = enabled
        logger.info(f"Memory provider registered: '{name}'")

        if (
            self._active is None
            and enabled
            and (self._default_provider is None or name == self._default_provider)
        ):
            self._active = name
            logger.info(f"Memory provider activated: '{name}'")

    def unregister(self, name: str) -> bool:
        """Remove a registered provider.

        Args:
            name: The provider's registration name.

        Returns:
            True if a provider was removed, False if `name` was unknown.
        """
        if name not in self._providers:
            return False
        del self._providers[name]
        del self._enabled[name]
        if self._active == name:
            self._active = None
        logger.info(f"Memory provider unregistered: '{name}'")
        return True

    def providers(self) -> list[str]:
        """Return every registered provider name, sorted."""
        return sorted(self._providers)

    # ---------- Enable / disable / switch ----------

    def enable(self, name: str) -> bool:
        """Enable a registered provider.

        Returns:
            True if enabled, False if `name` is not registered.
        """
        if name not in self._providers:
            return False
        self._enabled[name] = True
        logger.info(f"Memory provider enabled: '{name}'")
        return True

    def disable(self, name: str) -> bool:
        """Disable a registered provider.

        Disabling the currently active provider clears the active
        selection (the unified memory API then has no provider to
        delegate to until another one is activated).

        Returns:
            True if disabled, False if `name` is not registered.
        """
        if name not in self._providers:
            return False
        self._enabled[name] = False
        if self._active == name:
            self._active = None
        logger.info(f"Memory provider disabled: '{name}'")
        return True

    def use(self, name: str) -> None:
        """Switch the active provider.

        Args:
            name: The provider to activate.

        Raises:
            MemoryProviderError: If `name` is not registered, or is
                currently disabled.
        """
        if name not in self._providers:
            raise MemoryProviderError(f"Unknown memory provider: '{name}'")
        if not self._enabled.get(name, False):
            raise MemoryProviderError(f"Memory provider is disabled: '{name}'")
        self._active = name
        logger.info(f"Memory provider activated: '{name}'")

    def active_provider(self) -> MemoryProvider | None:
        """Return the currently active provider instance, or None."""
        if self._active is None:
            return None
        return self._providers.get(self._active)

    def active_provider_name(self) -> str | None:
        """Return the currently active provider's name, or None."""
        return self._active

    def is_registered(self, name: str) -> bool:
        """Return whether a provider with `name` is registered."""
        return name in self._providers

    def is_enabled(self, name: str) -> bool:
        """Return whether a registered provider is currently enabled."""
        return self._enabled.get(name, False)

    def status(self) -> ManagerStatus:
        """Return a status snapshot of every registered provider."""
        providers_status = [
            ProviderStatus(
                name=name,
                enabled=self._enabled.get(name, False),
                active=(name == self._active),
            )
            for name in sorted(self._providers)
        ]
        return ManagerStatus(
            active_provider=self._active,
            provider_count=len(self._providers),
            providers=providers_status,
        )

    # ---------- Unified memory API (delegates to the active provider) ----------

    def store(self, key: str, value: Any, namespace: str = "default") -> None:
        """Store `value` under `key` using the active provider.

        Raises:
            MemoryProviderError: If no provider is currently active.
        """
        self._require_active().store(key, value, namespace)

    def load(self, key: str, namespace: str = "default") -> Any | None:
        """Load the value stored under `key` from the active provider.

        Raises:
            MemoryProviderError: If no provider is currently active.
        """
        return self._require_active().load(key, namespace)

    def delete(self, key: str, namespace: str = "default") -> bool:
        """Delete `key` from the active provider.

        Raises:
            MemoryProviderError: If no provider is currently active.
        """
        return self._require_active().delete(key, namespace)

    def clear(self, namespace: str | None = None) -> int:
        """Clear entries from the active provider.

        Raises:
            MemoryProviderError: If no provider is currently active.
        """
        return self._require_active().clear(namespace)

    def exists(self, key: str, namespace: str = "default") -> bool:
        """Return whether `key` exists in the active provider.

        Raises:
            MemoryProviderError: If no provider is currently active.
        """
        return self._require_active().exists(key, namespace)

    def list(self, namespace: str | None = None) -> list[str]:
        """List keys from the active provider.

        Raises:
            MemoryProviderError: If no provider is currently active.
        """
        return self._require_active().list(namespace)

    def _require_active(self) -> MemoryProvider:
        """Return the active provider.

        Raises:
            MemoryProviderError: If no provider is currently active.
        """
        provider = self.active_provider()
        if provider is None:
            raise MemoryProviderError("No active memory provider.")
        return provider
