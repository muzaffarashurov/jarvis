"""Central Knowledge Manager for EP-024 Knowledge Base.

`KnowledgeManager` is a pure orchestration layer over registered
`KnowledgeProvider` instances: registration, enable/disable, active-
provider switching, and delegation of the unified store/load/update/
delete/clear/list/collections/stats API to whichever provider is
currently active. It implements no storage logic of its own -- concrete
storage stays inside each `KnowledgeProvider` (e.g.
`KnowledgeCollectionProvider`, wrapping `KnowledgeCollection`).

Mirrors the manager-over-registered-providers pattern already used by
`MemoryManager` (see `src/core/memory/memory_manager.py`), scoped down
to EP-024's own responsibilities: structured knowledge records
organized into collections. Knowledge Base performs no reasoning and
has no dependency on Embedding, Retrieval, RAG, Long-Term Memory,
Semantic Search, Context Compression, Planner, Reflection, Agent
Framework, Browser Automation, Vector Database, or any future EP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from src.core.knowledge.knowledge_collection import CollectionStats
from src.core.knowledge.knowledge_provider import (
    DEFAULT_COLLECTION,
    KnowledgeProvider,
    KnowledgeProviderError,
    ProviderStatus,
)
from src.core.knowledge.knowledge_record import KnowledgeRecord


@dataclass(frozen=True)
class ManagerStatus:
    """Status snapshot returned by `KnowledgeManager.status()`.

    Attributes:
        active_provider: Name of the currently active provider, or
            None if no provider is registered/active.
        provider_count: Number of registered providers.
        providers: Per-provider status snapshots, sorted by name.
    """

    active_provider: str | None
    provider_count: int
    providers: list[ProviderStatus]


class KnowledgeManager:
    """Orchestrates registered `KnowledgeProvider` instances.

    Responsibilities:
        - register / unregister providers
        - enable / disable providers
        - switch the active provider
        - expose the active provider and per-provider status
        - delegate the unified knowledge API to the active provider

    `KnowledgeManager` owns no storage state of its own; every record
    lives inside whichever `KnowledgeProvider` is currently active.
    """

    def __init__(self, default_provider: str | None = None) -> None:
        """Initialize an empty `KnowledgeManager`.

        Args:
            default_provider: Name to activate automatically once a
                matching provider is registered (see `register`).
                Typically resolved from 'knowledge.default_provider'
                by the caller (`KnowledgeService`). If None, the first
                enabled provider registered becomes active.
        """
        self._providers: dict[str, KnowledgeProvider] = {}
        self._enabled: dict[str, bool] = {}
        self._active: str | None = None
        self._default_provider = default_provider

    # ---------- Registration ----------

    def register(self, provider: KnowledgeProvider, enabled: bool = True) -> None:
        """Register a provider under its own `name`.

        Args:
            provider: The `KnowledgeProvider` instance to register.
            enabled: Whether the provider starts enabled.

        If no provider is currently active, this provider is enabled,
        and either no default was configured or this provider's name
        matches the configured default, it becomes active.
        """
        name = provider.name
        self._providers[name] = provider
        self._enabled[name] = enabled
        logger.info(f"Knowledge provider registered: '{name}'")

        if (
            self._active is None
            and enabled
            and (self._default_provider is None or name == self._default_provider)
        ):
            self._active = name
            logger.info(f"Knowledge provider activated: '{name}'")

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
        logger.info(f"Knowledge provider unregistered: '{name}'")
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
        logger.info(f"Knowledge provider enabled: '{name}'")
        return True

    def disable(self, name: str) -> bool:
        """Disable a registered provider.

        Disabling the currently active provider clears the active
        selection (the unified knowledge API then has no provider to
        delegate to until another one is activated).

        Returns:
            True if disabled, False if `name` is not registered.
        """
        if name not in self._providers:
            return False
        self._enabled[name] = False
        if self._active == name:
            self._active = None
        logger.info(f"Knowledge provider disabled: '{name}'")
        return True

    def use(self, name: str) -> None:
        """Switch the active provider.

        Args:
            name: The provider to activate.

        Raises:
            KnowledgeProviderError: If `name` is not registered, or is
                currently disabled.
        """
        if name not in self._providers:
            raise KnowledgeProviderError(f"Unknown knowledge provider: '{name}'")
        if not self._enabled.get(name, False):
            raise KnowledgeProviderError(f"Knowledge provider is disabled: '{name}'")
        self._active = name
        logger.info(f"Knowledge provider activated: '{name}'")

    def active_provider(self) -> KnowledgeProvider | None:
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

    # ---------- Unified knowledge API (delegates to the active provider) ----------

    def store(
        self,
        key: str,
        content: Any,
        collection: str = DEFAULT_COLLECTION,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeRecord:
        """Create (or overwrite) a record using the active provider.

        Raises:
            KnowledgeProviderError: If no provider is currently active.
        """
        return self._require_active().store(key, content, collection, metadata)

    def load(self, key: str, collection: str = DEFAULT_COLLECTION) -> KnowledgeRecord | None:
        """Load a record from the active provider.

        Raises:
            KnowledgeProviderError: If no provider is currently active.
        """
        return self._require_active().load(key, collection)

    def update(
        self,
        key: str,
        content: Any,
        collection: str = DEFAULT_COLLECTION,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeRecord | None:
        """Update an existing record using the active provider.

        Raises:
            KnowledgeProviderError: If no provider is currently active.
        """
        return self._require_active().update(key, content, collection, metadata)

    def delete(self, key: str, collection: str = DEFAULT_COLLECTION) -> bool:
        """Delete a record from the active provider.

        Raises:
            KnowledgeProviderError: If no provider is currently active.
        """
        return self._require_active().delete(key, collection)

    def clear(self, collection: str | None = None) -> int:
        """Clear records from the active provider.

        Raises:
            KnowledgeProviderError: If no provider is currently active.
        """
        return self._require_active().clear(collection)

    def list(self, collection: str | None = None) -> list[KnowledgeRecord]:
        """List records from the active provider.

        Raises:
            KnowledgeProviderError: If no provider is currently active.
        """
        return self._require_active().list(collection)

    def collections(self) -> list[str]:
        """List collections known to the active provider.

        Raises:
            KnowledgeProviderError: If no provider is currently active.
        """
        return self._require_active().collections()

    def stats(self, collection: str | None = None) -> list[CollectionStats]:
        """Return collection statistics from the active provider.

        Raises:
            KnowledgeProviderError: If no provider is currently active.
        """
        return self._require_active().stats(collection)

    def _require_active(self) -> KnowledgeProvider:
        """Return the active provider.

        Raises:
            KnowledgeProviderError: If no provider is currently active.
        """
        provider = self.active_provider()
        if provider is None:
            raise KnowledgeProviderError("No active knowledge provider.")
        return provider
