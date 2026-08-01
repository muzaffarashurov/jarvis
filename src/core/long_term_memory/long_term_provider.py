"""Provider abstraction for EP-025 Long-Term Memory.

Defines the unified store/get/update/archive/delete/clear/list/stats
contract that every long-term-memory provider must implement
(`LongTermProvider`), plus two adapters:

    KnowledgeBackedLongTermProvider
        Persists LongTermRecord objects as KnowledgeRecords inside a
        dedicated collection, communicating with EP-024's Knowledge
        Base exclusively through `KnowledgeService`'s public API
        (store/load/update/delete/list_records/collection_stats) --
        never touching `KnowledgeCollection` or `KnowledgeManager`
        directly. This is Long-Term Memory's persistence backend: it
        introduces no third storage engine, reusing EP-024's instead.

    LongTermMemoryProvider
        Adapts a `LongTermMemoryManager` (or any object exposing the
        same store/get/delete/clear/list methods) to EP-023's
        `MemoryProvider` interface, so it can be registered with the
        Memory Manager through `MemoryService.register_provider` --
        again, only through a public API, never MemoryManager's
        internals. This is how EP-025 "extends EP-023 Memory Manager"
        per its brief: MemoryManager needs no code change to gain a
        "long_term" provider.

This module implements no reasoning, ranking, similarity search, or
embeddings, and must never import Embedding, Retrieval, RAG, Semantic
Search, Context Compression, Reflection, Planner, Agent Framework,
Browser Automation, Vector Database, or any future EP.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from src.core.long_term_memory.long_term_record import (
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    LongTermRecord,
    utc_now,
)
from src.core.memory.memory_provider import MemoryProvider

if TYPE_CHECKING:
    from src.core.long_term_memory.long_term_manager import LongTermMemoryManager
    from src.services.knowledge_service import KnowledgeService

DEFAULT_COLLECTION: str = "long_term_memory"
_METADATA_STATUS_KEY: str = "_ltm_status"
_METADATA_ARCHIVED_AT_KEY: str = "_ltm_archived_at"


class LongTermProviderError(Exception):
    """Raised for invalid Long-Term Memory provider operations (EP-025)."""


@dataclass(frozen=True)
class LongTermProviderStatus:
    """Status snapshot of a single provider registered with `LongTermMemoryManager`.

    Attributes:
        name: The provider's registration name.
        enabled: Whether the provider is currently enabled.
        active: Whether this is the currently active provider.
    """

    name: str
    enabled: bool
    active: bool


@dataclass(frozen=True)
class LongTermStats:
    """Aggregate statistics for the Long-Term Memory subsystem.

    Attributes:
        total: Total number of records (active + archived).
        active: Number of records with status STATUS_ACTIVE.
        archived: Number of records with status STATUS_ARCHIVED.
    """

    total: int
    active: int
    archived: int


class LongTermProvider(ABC):
    """Unified interface implemented by every long-term-memory provider.

    `LongTermMemoryManager` (EP-025) orchestrates instances of this
    interface; it never implements persistence itself. Long-Term
    Memory is a flat, ID-addressed store: there is no namespace or
    collection concept at this level (that detail, if any, belongs to
    the concrete provider's own persistence backend).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return this provider's unique registration name."""
        raise NotImplementedError

    @abstractmethod
    def store(
        self, memory_id: str, content: Any, metadata: dict[str, Any] | None = None
    ) -> LongTermRecord:
        """Create (or overwrite) an active memory under `memory_id`."""
        raise NotImplementedError

    @abstractmethod
    def get(self, memory_id: str) -> LongTermRecord | None:
        """Retrieve the memory stored under `memory_id`, or None if absent."""
        raise NotImplementedError

    @abstractmethod
    def update(
        self,
        memory_id: str,
        content: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> LongTermRecord | None:
        """Update an existing memory's content and/or metadata.

        Returns None if no memory exists under `memory_id`.
        """
        raise NotImplementedError

    @abstractmethod
    def archive(self, memory_id: str) -> LongTermRecord | None:
        """Mark an existing memory as archived (a lifecycle transition, not a delete).

        Returns None if no memory exists under `memory_id`.
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        """Permanently delete the memory stored under `memory_id`."""
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> int:
        """Permanently delete every memory. Returns the number removed."""
        raise NotImplementedError

    @abstractmethod
    def list(self, status: str | None = None) -> list[LongTermRecord]:
        """List memories, optionally filtered to STATUS_ACTIVE or STATUS_ARCHIVED."""
        raise NotImplementedError

    @abstractmethod
    def stats(self) -> LongTermStats:
        """Return aggregate active/archived/total statistics."""
        raise NotImplementedError


class KnowledgeBackedLongTermProvider(LongTermProvider):
    """Persists long-term memories via EP-024's Knowledge Base.

    Every operation is expressed in terms of `KnowledgeService`'s
    public API (`store`/`load`/`update`/`delete`/`list_records`) inside
    a single dedicated collection (default "long_term_memory").
    Lifecycle metadata (status, archived_at) rides inside the
    KnowledgeRecord's own `metadata` dict, under reserved keys, so this
    provider introduces no second storage engine: Knowledge Base's
    `KnowledgeCollection` remains the single source of truth for the
    underlying bytes.
    """

    def __init__(
        self,
        knowledge_service: "KnowledgeService",
        collection: str = DEFAULT_COLLECTION,
        name: str = "knowledge",
    ) -> None:
        """Initialize the adapter around a `KnowledgeService` instance.

        Args:
            knowledge_service: The EP-024 KnowledgeService to persist
                memories through. Only its public methods are used.
            collection: The Knowledge Base collection long-term
                memories are stored in.
            name: The registration name this provider is exposed under.
        """
        self._knowledge_service = knowledge_service
        self._collection = collection
        self._name = name

    @property
    def name(self) -> str:
        """Return this provider's registration name (default: "knowledge")."""
        return self._name

    def store(
        self, memory_id: str, content: Any, metadata: dict[str, Any] | None = None
    ) -> LongTermRecord:
        """Create (or overwrite) an active memory via `KnowledgeService.store`.

        Raises:
            LongTermProviderError: If the underlying Knowledge Base
                store operation fails (e.g. the Knowledge subsystem is
                disabled).
        """
        packed = self._pack_metadata(metadata or {}, status=STATUS_ACTIVE, archived_at=None)
        result = self._knowledge_service.store(memory_id, content, self._collection, packed)
        if not result.success:
            raise LongTermProviderError(result.message)
        return self._require_record(memory_id)

    def get(self, memory_id: str) -> LongTermRecord | None:
        """Retrieve a memory via `KnowledgeService.load`."""
        record = self._knowledge_service.load(memory_id, self._collection)
        return self._to_long_term_record(record) if record is not None else None

    def update(
        self,
        memory_id: str,
        content: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> LongTermRecord | None:
        """Update a memory's content and/or metadata via `KnowledgeService.update`.

        Preserves the existing lifecycle status/archived_at -- archiving
        is only ever done through `archive`.
        """
        existing = self._knowledge_service.load(memory_id, self._collection)
        if existing is None:
            return None

        new_content = content if content is not None else existing.content
        user_metadata = (
            metadata if metadata is not None else self._unpack_user_metadata(existing.metadata)
        )
        status, archived_at = self._unpack_lifecycle(existing.metadata)
        packed = self._pack_metadata(user_metadata, status=status, archived_at=archived_at)

        result = self._knowledge_service.update(memory_id, new_content, self._collection, packed)
        if not result.success:
            return None
        return self._require_record(memory_id)

    def archive(self, memory_id: str) -> LongTermRecord | None:
        """Transition a memory to STATUS_ARCHIVED via `KnowledgeService.update`."""
        existing = self._knowledge_service.load(memory_id, self._collection)
        if existing is None:
            return None

        user_metadata = self._unpack_user_metadata(existing.metadata)
        packed = self._pack_metadata(user_metadata, status=STATUS_ARCHIVED, archived_at=utc_now())
        result = self._knowledge_service.update(
            memory_id, existing.content, self._collection, packed
        )
        if not result.success:
            return None
        return self._require_record(memory_id)

    def delete(self, memory_id: str) -> bool:
        """Permanently delete a memory via `KnowledgeService.delete`."""
        result = self._knowledge_service.delete(memory_id, self._collection)
        return result.success

    def clear(self) -> int:
        """Permanently delete every memory via `KnowledgeService.clear`."""
        count = len(self._knowledge_service.list_records(self._collection))
        result = self._knowledge_service.clear(self._collection)
        if not result.success:
            return 0
        return count

    def list(self, status: str | None = None) -> list[LongTermRecord]:
        """List memories via `KnowledgeService.list_records`, optionally filtered by status."""
        records = [
            self._to_long_term_record(record)
            for record in self._knowledge_service.list_records(self._collection)
        ]
        if status is not None:
            records = [record for record in records if record.status == status]
        return sorted(records, key=lambda record: record.id)

    def stats(self) -> LongTermStats:
        """Return aggregate active/archived/total statistics."""
        records = self.list()
        active = sum(1 for record in records if record.status == STATUS_ACTIVE)
        archived = sum(1 for record in records if record.status == STATUS_ARCHIVED)
        return LongTermStats(total=len(records), active=active, archived=archived)

    # ---------- Internal helpers ----------

    def _require_record(self, memory_id: str) -> LongTermRecord:
        record = self._knowledge_service.load(memory_id, self._collection)
        if record is None:
            raise LongTermProviderError(
                f"Long-term memory '{memory_id}' was written but could not be re-read."
            )
        return self._to_long_term_record(record)

    @staticmethod
    def _pack_metadata(
        user_metadata: dict[str, Any], status: str, archived_at: Any = None
    ) -> dict[str, Any]:
        """Merge caller-facing metadata with reserved lifecycle keys."""
        packed = dict(user_metadata)
        packed[_METADATA_STATUS_KEY] = status
        packed[_METADATA_ARCHIVED_AT_KEY] = (
            archived_at.isoformat() if hasattr(archived_at, "isoformat") else archived_at
        )
        return packed

    @staticmethod
    def _unpack_user_metadata(packed_metadata: dict[str, Any]) -> dict[str, Any]:
        """Strip reserved lifecycle keys, returning only caller-facing metadata."""
        return {
            key: value
            for key, value in packed_metadata.items()
            if key not in (_METADATA_STATUS_KEY, _METADATA_ARCHIVED_AT_KEY)
        }

    @staticmethod
    def _unpack_lifecycle(packed_metadata: dict[str, Any]) -> tuple[str, Any]:
        """Extract (status, archived_at) from a KnowledgeRecord's packed metadata."""
        status = packed_metadata.get(_METADATA_STATUS_KEY, STATUS_ACTIVE)
        archived_at = packed_metadata.get(_METADATA_ARCHIVED_AT_KEY)
        return status, archived_at

    def _to_long_term_record(self, knowledge_record: Any) -> LongTermRecord:
        """Convert a KnowledgeRecord (with packed lifecycle metadata) to a LongTermRecord."""
        status, archived_at = self._unpack_lifecycle(knowledge_record.metadata)
        return LongTermRecord(
            id=knowledge_record.key,
            content=knowledge_record.content,
            metadata=self._unpack_user_metadata(knowledge_record.metadata),
            status=status,
            created_at=knowledge_record.created_at,
            updated_at=knowledge_record.updated_at,
            archived_at=self._parse_archived_at(archived_at),
        )

    @staticmethod
    def _parse_archived_at(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, str):
            return datetime.fromisoformat(value)
        return value


class LongTermMemoryProvider(MemoryProvider):
    """Adapts EP-025's Long-Term Memory to EP-023's `MemoryProvider` interface.

    Registering an instance of this class with `MemoryManager` (via
    `MemoryService.register_provider`) is how EP-025 "extends EP-023
    Memory Manager" per its brief -- MemoryManager gains a "long_term"
    provider without any change to its own code. Long-Term Memory is a
    flat, ID-addressed store: `namespace` is accepted for interface
    compatibility only and does not partition storage.
    """

    def __init__(self, manager: "LongTermMemoryManager", name: str = "long_term") -> None:
        """Initialize the adapter around a `LongTermMemoryManager`.

        Args:
            manager: The LongTermMemoryManager whose unified API
                (store/get/delete/clear/list) this adapter delegates
                to. Delegating to the manager (rather than a single
                provider snapshot) means this adapter always reflects
                whichever LongTermProvider is currently active.
            name: The registration name this provider is exposed under.
        """
        self._manager = manager
        self._name = name

    @property
    def name(self) -> str:
        """Return this provider's registration name (default: "long_term")."""
        return self._name

    def store(self, key: str, value: Any, namespace: str = "default") -> None:
        """Store `value` as a long-term memory under `key` (namespace is ignored)."""
        self._manager.store(key, value)

    def load(self, key: str, namespace: str = "default") -> Any | None:
        """Return the content of the long-term memory stored under `key`, or None."""
        record = self._manager.get(key)
        return record.content if record is not None else None

    def delete(self, key: str, namespace: str = "default") -> bool:
        """Permanently delete the long-term memory stored under `key`."""
        return self._manager.delete(key)

    def clear(self, namespace: str | None = None) -> int:
        """Permanently delete every long-term memory (namespace is ignored)."""
        return self._manager.clear()

    def exists(self, key: str, namespace: str = "default") -> bool:
        """Return whether a long-term memory is stored under `key`."""
        return self._manager.get(key) is not None

    def list(self, namespace: str | None = None) -> list[str]:
        """List every long-term memory's id (namespace is ignored)."""
        return [record.id for record in self._manager.list()]
