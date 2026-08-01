"""Central Long-Term Memory Manager for EP-025.

`LongTermMemoryManager` is a pure orchestration layer over registered
`LongTermProvider` instances: registration, enable/disable,
active-provider switching, and delegation of the unified
store/get/update/archive/delete/clear/list/stats API to whichever
provider is currently active. It implements no persistence logic of
its own -- concrete storage stays inside each `LongTermProvider` (e.g.
`KnowledgeBackedLongTermProvider`, wrapping EP-024's `KnowledgeService`).

Mirrors the manager-over-registered-providers pattern already used by
`MemoryManager` (EP-023, `src/core/memory/memory_manager.py`) and
`KnowledgeManager` (EP-024, `src/core/knowledge/knowledge_manager.py`),
scoped down to EP-025's own responsibilities: persistent storage and
lifecycle management (active/archived) of long-lived memories.

Long-Term Memory performs no ranking, similarity search, embeddings, or
AI reasoning, and has no dependency on Semantic Search, Context
Compression, Reflection, Planner, Agent Framework, Browser Automation,
Vector Database, Embedding, Retrieval, RAG, or any future EP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from src.core.long_term_memory.long_term_provider import (
    LongTermProvider,
    LongTermProviderError,
    LongTermProviderStatus,
    LongTermStats,
)
from src.core.long_term_memory.long_term_record import LongTermRecord


@dataclass(frozen=True)
class LongTermManagerStatus:
    """Status snapshot returned by `LongTermMemoryManager.status()`.

    Attributes:
        active_provider: Name of the currently active provider, or
            None if no provider is registered/active.
        provider_count: Number of registered providers.
        providers: Per-provider status snapshots, sorted by name.
    """

    active_provider: str | None
    provider_count: int
    providers: list[LongTermProviderStatus]


class LongTermMemoryManager:
    """Orchestrates registered `LongTermProvider` instances.

    Responsibilities:
        - register / unregister providers
        - enable / disable providers
        - switch the active provider
        - expose the active provider and per-provider status
        - delegate the unified long-term-memory API to the active provider

    `LongTermMemoryManager` owns no storage state of its own; every
    memory lives inside whichever `LongTermProvider` is currently active.
    """

    def __init__(self, default_provider: str | None = None) -> None:
        """Initialize an empty `LongTermMemoryManager`.

        Args:
            default_provider: Name to activate automatically once a
                matching provider is registered (see `register`).
                Typically resolved from
                'long_term_memory.default_provider' by the caller
                (`LongTermMemoryService`). If None, the first enabled
                provider registered becomes active.
        """
        self._providers: dict[str, LongTermProvider] = {}
        self._enabled: dict[str, bool] = {}
        self._active: str | None = None
        self._default_provider = default_provider

    # ---------- Registration ----------

    def register(self, provider: LongTermProvider, enabled: bool = True) -> None:
        """Register a provider under its own `name`.

        Args:
            provider: The `LongTermProvider` instance to register.
            enabled: Whether the provider starts enabled.

        If no provider is currently active, this provider is enabled,
        and either no default was configured or this provider's name
        matches the configured default, it becomes active.
        """
        name = provider.name
        self._providers[name] = provider
        self._enabled[name] = enabled
        logger.info(f"Long-term memory provider registered: '{name}'")

        if (
            self._active is None
            and enabled
            and (self._default_provider is None or name == self._default_provider)
        ):
            self._active = name
            logger.info(f"Long-term memory provider activated: '{name}'")

    def unregister(self, name: str) -> bool:
        """Remove a registered provider.

        Returns:
            True if a provider was removed, False if `name` was unknown.
        """
        if name not in self._providers:
            return False
        del self._providers[name]
        del self._enabled[name]
        if self._active == name:
            self._active = None
        logger.info(f"Long-term memory provider unregistered: '{name}'")
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
        logger.info(f"Long-term memory provider enabled: '{name}'")
        return True

    def disable(self, name: str) -> bool:
        """Disable a registered provider.

        Disabling the currently active provider clears the active
        selection (the unified API then has no provider to delegate
        to until another one is activated).

        Returns:
            True if disabled, False if `name` is not registered.
        """
        if name not in self._providers:
            return False
        self._enabled[name] = False
        if self._active == name:
            self._active = None
        logger.info(f"Long-term memory provider disabled: '{name}'")
        return True

    def use(self, name: str) -> None:
        """Switch the active provider.

        Raises:
            LongTermProviderError: If `name` is not registered, or is
                currently disabled.
        """
        if name not in self._providers:
            raise LongTermProviderError(f"Unknown long-term memory provider: '{name}'")
        if not self._enabled.get(name, False):
            raise LongTermProviderError(f"Long-term memory provider is disabled: '{name}'")
        self._active = name
        logger.info(f"Long-term memory provider activated: '{name}'")

    def active_provider(self) -> LongTermProvider | None:
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

    def status(self) -> LongTermManagerStatus:
        """Return a status snapshot of every registered provider."""
        providers_status = [
            LongTermProviderStatus(
                name=name,
                enabled=self._enabled.get(name, False),
                active=(name == self._active),
            )
            for name in sorted(self._providers)
        ]
        return LongTermManagerStatus(
            active_provider=self._active,
            provider_count=len(self._providers),
            providers=providers_status,
        )

    # ---------- Unified long-term-memory API (delegates to the active provider) ----------

    def store(
        self, memory_id: str, content: Any, metadata: dict[str, Any] | None = None
    ) -> LongTermRecord:
        """Create (or overwrite) an active memory using the active provider.

        Raises:
            LongTermProviderError: If no provider is currently active.
        """
        return self._require_active().store(memory_id, content, metadata)

    def get(self, memory_id: str) -> LongTermRecord | None:
        """Retrieve a memory from the active provider.

        Raises:
            LongTermProviderError: If no provider is currently active.
        """
        return self._require_active().get(memory_id)

    def update(
        self,
        memory_id: str,
        content: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> LongTermRecord | None:
        """Update an existing memory using the active provider.

        Raises:
            LongTermProviderError: If no provider is currently active.
        """
        return self._require_active().update(memory_id, content, metadata)

    def archive(self, memory_id: str) -> LongTermRecord | None:
        """Archive an existing memory using the active provider.

        Raises:
            LongTermProviderError: If no provider is currently active.
        """
        return self._require_active().archive(memory_id)

    def delete(self, memory_id: str) -> bool:
        """Permanently delete a memory from the active provider.

        Raises:
            LongTermProviderError: If no provider is currently active.
        """
        return self._require_active().delete(memory_id)

    def clear(self) -> int:
        """Permanently delete every memory from the active provider.

        Raises:
            LongTermProviderError: If no provider is currently active.
        """
        return self._require_active().clear()

    def list(self, status: str | None = None) -> list[LongTermRecord]:
        """List memories from the active provider.

        Raises:
            LongTermProviderError: If no provider is currently active.
        """
        return self._require_active().list(status)

    def stats(self) -> LongTermStats:
        """Return aggregate statistics from the active provider.

        Raises:
            LongTermProviderError: If no provider is currently active.
        """
        return self._require_active().stats()

    def _require_active(self) -> LongTermProvider:
        """Return the active provider.

        Raises:
            LongTermProviderError: If no provider is currently active.
        """
        provider = self.active_provider()
        if provider is None:
            raise LongTermProviderError("No active long-term memory provider.")
        return provider
