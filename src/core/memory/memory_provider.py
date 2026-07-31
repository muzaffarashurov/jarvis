"""Provider abstraction for EP-023 Memory Manager.

Defines the unified `store`/`load`/`delete`/`clear`/`exists`/`list`
contract that every memory provider must implement, plus the
`MemoryStoreProvider` adapter around the existing (EP-013) MemoryStore.

This module implements no storage logic of its own. `MemoryProvider`
is a pure interface; `MemoryStoreProvider` only delegates to
`MemoryStore`/`MemoryEntry` (see `src/core/memory/memory_store.py` and
`src/core/memory/context.py`), reusing EP-013's storage instead of
duplicating it. Future providers (KnowledgeBaseProvider,
LongTermMemoryProvider, ExternalProvider, etc.) are out of scope for
EP-023 and are not implemented here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.core.memory.context import DEFAULT_NAMESPACE, MemoryEntry
from src.core.memory.memory_store import MemoryStore


class MemoryProviderError(Exception):
    """Raised for invalid memory provider operations (EP-023)."""


class MemoryProvider(ABC):
    """Unified interface implemented by every memory provider.

    `MemoryManager` (EP-023) orchestrates instances of this interface;
    it never implements storage itself. Every method mirrors the
    store/load/delete/clear/exists/list vocabulary requested by EP-023.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return this provider's unique registration name."""
        raise NotImplementedError

    @abstractmethod
    def store(self, key: str, value: Any, namespace: str = DEFAULT_NAMESPACE) -> None:
        """Store `value` under `key` within `namespace`."""
        raise NotImplementedError

    @abstractmethod
    def load(self, key: str, namespace: str = DEFAULT_NAMESPACE) -> Any | None:
        """Retrieve the value stored under `key`, or None if absent."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str, namespace: str = DEFAULT_NAMESPACE) -> bool:
        """Delete the entry stored under `key`. Returns True if removed."""
        raise NotImplementedError

    @abstractmethod
    def clear(self, namespace: str | None = None) -> int:
        """Remove every entry in `namespace` (or all namespaces if None)."""
        raise NotImplementedError

    @abstractmethod
    def exists(self, key: str, namespace: str = DEFAULT_NAMESPACE) -> bool:
        """Return whether `key` currently has a stored (non-expired) value."""
        raise NotImplementedError

    @abstractmethod
    def list(self, namespace: str | None = None) -> list[str]:
        """List keys currently stored (optionally scoped to `namespace`)."""
        raise NotImplementedError


@dataclass(frozen=True)
class ProviderStatus:
    """Status snapshot of a single provider registered with `MemoryManager`.

    Attributes:
        name: The provider's registration name.
        enabled: Whether the provider is currently enabled.
        active: Whether this is the currently active provider.
    """

    name: str
    enabled: bool
    active: bool


class MemoryStoreProvider(MemoryProvider):
    """Adapts the existing (EP-013) `MemoryStore` to the `MemoryProvider` interface.

    Delegates every operation to `MemoryStore`; this class owns no
    storage state of its own and introduces no new persistence
    behavior. It exists so `MemoryManager` has a working, config-driven
    default provider (`memory.default_provider`, typically "memory")
    without duplicating EP-013's storage logic.
    """

    def __init__(self, store: MemoryStore, name: str = "memory") -> None:
        """Initialize the adapter around an existing `MemoryStore`.

        Args:
            store: The EP-013 `MemoryStore` instance to delegate to.
            name: The registration name this provider is exposed under.
        """
        self._store = store
        self._name = name

    @property
    def name(self) -> str:
        """Return this provider's registration name (default: "memory")."""
        return self._name

    def store(self, key: str, value: Any, namespace: str = DEFAULT_NAMESPACE) -> None:
        """Store `value` under `key` by delegating to `MemoryStore.set`."""
        self._store.set(MemoryEntry(key=key, value=value, namespace=namespace))

    def load(self, key: str, namespace: str = DEFAULT_NAMESPACE) -> Any | None:
        """Retrieve the value under `key` by delegating to `MemoryStore.get`."""
        entry = self._store.get(namespace, key)
        return entry.value if entry is not None else None

    def delete(self, key: str, namespace: str = DEFAULT_NAMESPACE) -> bool:
        """Delete `key` by delegating to `MemoryStore.delete`."""
        return self._store.delete(namespace, key)

    def clear(self, namespace: str | None = None) -> int:
        """Clear entries by delegating to `MemoryStore.clear`."""
        return self._store.clear(namespace)

    def exists(self, key: str, namespace: str = DEFAULT_NAMESPACE) -> bool:
        """Return whether `key` exists by delegating to `MemoryStore.get`."""
        return self._store.get(namespace, key) is not None

    def list(self, namespace: str | None = None) -> list[str]:
        """List keys by delegating to `MemoryStore.list`."""
        return [entry.key for entry in self._store.list(namespace)]
