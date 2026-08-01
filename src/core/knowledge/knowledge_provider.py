"""Provider abstraction for EP-024 Knowledge Base.

Defines the unified store/load/update/delete/clear/list/collections/
stats contract that every knowledge provider must implement, plus the
`KnowledgeCollectionProvider` adapter around `KnowledgeCollection`.

This module implements no storage logic of its own. `KnowledgeProvider`
is a pure interface; `KnowledgeCollectionProvider` only delegates to
`KnowledgeCollection`/`KnowledgeRecord` (see
`src/core/knowledge/knowledge_collection.py` and
`src/core/knowledge/knowledge_record.py`), reusing that storage engine
instead of duplicating it. Future providers (e.g. an external or
file-backed knowledge provider) are out of scope for EP-024 and are
not implemented here.

Knowledge Base performs no reasoning and must never import Embedding,
Retrieval, RAG, Long-Term Memory, Semantic Search, Context Compression,
Planner, Reflection, Agent Framework, Browser Automation, Vector
Database, or any future EP.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from src.core.knowledge.knowledge_collection import CollectionStats, KnowledgeCollection
from src.core.knowledge.knowledge_record import DEFAULT_COLLECTION, KnowledgeRecord


class KnowledgeProviderError(Exception):
    """Raised for invalid Knowledge Base provider operations (EP-024)."""


class KnowledgeProvider(ABC):
    """Unified interface implemented by every knowledge provider.

    `KnowledgeManager` (EP-024) orchestrates instances of this
    interface; it never implements storage itself. Every method
    mirrors the store/load/update/delete/clear/list/collections/stats
    vocabulary requested by EP-024.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return this provider's unique registration name."""
        raise NotImplementedError

    @abstractmethod
    def store(
        self,
        key: str,
        content: Any,
        collection: str = DEFAULT_COLLECTION,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeRecord:
        """Create (or overwrite) a record under `key` within `collection`."""
        raise NotImplementedError

    @abstractmethod
    def load(self, key: str, collection: str = DEFAULT_COLLECTION) -> KnowledgeRecord | None:
        """Retrieve the record stored under `key`, or None if absent."""
        raise NotImplementedError

    @abstractmethod
    def update(
        self,
        key: str,
        content: Any,
        collection: str = DEFAULT_COLLECTION,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeRecord | None:
        """Update an existing record's content. Returns None if it does not exist."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str, collection: str = DEFAULT_COLLECTION) -> bool:
        """Delete the record stored under `key`. Returns True if removed."""
        raise NotImplementedError

    @abstractmethod
    def clear(self, collection: str | None = None) -> int:
        """Remove every record in `collection` (or all collections if None)."""
        raise NotImplementedError

    @abstractmethod
    def list(self, collection: str | None = None) -> list[KnowledgeRecord]:
        """List records currently stored (optionally scoped to `collection`)."""
        raise NotImplementedError

    @abstractmethod
    def collections(self) -> list[str]:
        """List every collection that currently has at least one record."""
        raise NotImplementedError

    @abstractmethod
    def stats(self, collection: str | None = None) -> list[CollectionStats]:
        """Return per-collection statistics (optionally scoped to `collection`)."""
        raise NotImplementedError


@dataclass(frozen=True)
class ProviderStatus:
    """Status snapshot of a single provider registered with `KnowledgeManager`.

    Attributes:
        name: The provider's registration name.
        enabled: Whether the provider is currently enabled.
        active: Whether this is the currently active provider.
    """

    name: str
    enabled: bool
    active: bool


class KnowledgeCollectionProvider(KnowledgeProvider):
    """Adapts a `KnowledgeCollection` store to the `KnowledgeProvider` interface.

    Delegates every operation to `KnowledgeCollection`; this class owns
    no storage state of its own and introduces no new persistence
    behavior. It exists so `KnowledgeManager` has a working,
    config-driven default provider (`knowledge.default_provider`,
    typically "local") without duplicating the storage engine's logic.
    """

    def __init__(self, store: KnowledgeCollection, name: str = "local") -> None:
        """Initialize the adapter around a `KnowledgeCollection` store.

        Args:
            store: The KnowledgeCollection instance to delegate to.
            name: The registration name this provider is exposed under.
        """
        self._store = store
        self._name = name

    @property
    def name(self) -> str:
        """Return this provider's registration name (default: "local")."""
        return self._name

    def store(
        self,
        key: str,
        content: Any,
        collection: str = DEFAULT_COLLECTION,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeRecord:
        """Create (or overwrite) a record, preserving `created_at` on overwrite."""
        existing = self._store.load(collection, key)
        record = KnowledgeRecord(
            key=key, content=content, collection=collection, metadata=metadata or {}
        )
        if existing is not None:
            record.created_at = existing.created_at
        self._store.store(record)
        return record

    def load(self, key: str, collection: str = DEFAULT_COLLECTION) -> KnowledgeRecord | None:
        """Retrieve a record by delegating to `KnowledgeCollection.load`."""
        return self._store.load(collection, key)

    def update(
        self,
        key: str,
        content: Any,
        collection: str = DEFAULT_COLLECTION,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeRecord | None:
        """Update a record by delegating to `KnowledgeCollection.update`."""
        return self._store.update(collection, key, content, metadata)

    def delete(self, key: str, collection: str = DEFAULT_COLLECTION) -> bool:
        """Delete a record by delegating to `KnowledgeCollection.delete`."""
        return self._store.delete(collection, key)

    def clear(self, collection: str | None = None) -> int:
        """Clear records by delegating to `KnowledgeCollection.clear`."""
        return self._store.clear(collection)

    def list(self, collection: str | None = None) -> list[KnowledgeRecord]:
        """List records by delegating to `KnowledgeCollection.list`."""
        return self._store.list(collection)

    def collections(self) -> list[str]:
        """List collections by delegating to `KnowledgeCollection.collections`."""
        return self._store.collections()

    def stats(self, collection: str | None = None) -> list[CollectionStats]:
        """Return statistics by delegating to `KnowledgeCollection.stats`."""
        return self._store.stats(collection)
