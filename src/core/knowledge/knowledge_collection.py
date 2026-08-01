"""Thread-safe, collection-organized storage engine for EP-024 Knowledge Base.

`KnowledgeCollection` only stores and retrieves `KnowledgeRecord`
objects grouped into named collections; it performs no CLI formatting,
no configuration resolution, and no file I/O of its own. It mirrors
the storage-only role of `MemoryStore`
(see `src/core/memory/memory_store.py`), adopting the same
lock-per-instance thread-safety pattern, since knowledge records may be
written and read concurrently by the CLI and, in the future, other
in-process consumers.

This module implements no reasoning, no embeddings, no retrieval and
no persistence -- it is a plain, in-process structured store organized
by collection instead of namespace.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any

from loguru import logger

from src.core.knowledge.knowledge_record import KnowledgeRecord, utc_now


class KnowledgeCollectionError(Exception):
    """Raised for invalid Knowledge Base collection operations."""


@dataclass(frozen=True)
class CollectionStats:
    """Statistics snapshot for a single collection.

    Attributes:
        name: The collection's name.
        record_count: Number of records currently stored in it.
    """

    name: str
    record_count: int


class KnowledgeCollection:
    """Thread-safe, collection-organized store of KnowledgeRecord objects.

    Responsibilities:
        - Store, retrieve, update, and delete KnowledgeRecord objects,
          keyed by (collection, key).
        - Group records by named collection.
        - Expose per-collection and overall statistics.

    `KnowledgeCollection` performs no reasoning and knows nothing about
    embeddings, retrieval, RAG, or memory providers.
    """

    def __init__(self) -> None:
        """Initialize an empty KnowledgeCollection store."""
        self._collections: dict[str, dict[str, KnowledgeRecord]] = {}
        self._lock = RLock()

    def store(self, record: KnowledgeRecord) -> None:
        """Store (or overwrite) a record under its collection and key.

        Args:
            record: The KnowledgeRecord to store.
        """
        with self._lock:
            bucket = self._collections.setdefault(record.collection, {})
            bucket[record.key] = record
        logger.debug(f"Knowledge record stored: '{record.collection}:{record.key}'")

    def load(self, collection: str, key: str) -> KnowledgeRecord | None:
        """Retrieve a single record.

        Args:
            collection: The collection to look in.
            key: The key to look up.

        Returns:
            The stored KnowledgeRecord, or None if absent.
        """
        with self._lock:
            bucket = self._collections.get(collection)
            if bucket is None:
                return None
            return bucket.get(key)

    def update(
        self,
        collection: str,
        key: str,
        content: Any,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeRecord | None:
        """Update an existing record's content (and optionally metadata).

        Args:
            collection: The collection the record belongs to.
            key: The record's key.
            content: The new content to store.
            metadata: If given, replaces the record's metadata.
                Otherwise the existing metadata is preserved.

        Returns:
            The updated KnowledgeRecord, or None if no record exists
            under (collection, key). Use `store` to create one.
        """
        with self._lock:
            bucket = self._collections.get(collection)
            if bucket is None or key not in bucket:
                return None
            existing = bucket[key]
            updated = KnowledgeRecord(
                key=existing.key,
                content=content,
                collection=existing.collection,
                metadata=metadata if metadata is not None else existing.metadata,
                created_at=existing.created_at,
                updated_at=utc_now(),
            )
            bucket[key] = updated
        logger.info(f"Knowledge record updated: '{collection}:{key}'")
        return updated

    def delete(self, collection: str, key: str) -> bool:
        """Delete a single record.

        Args:
            collection: The collection to delete from.
            key: The key to delete.

        Returns:
            True if a record was removed, False if it did not exist.
        """
        with self._lock:
            bucket = self._collections.get(collection)
            if bucket is None or key not in bucket:
                return False
            del bucket[key]
        logger.info(f"Knowledge record deleted: '{collection}:{key}'")
        return True

    def clear(self, collection: str | None = None) -> int:
        """Remove all records in a collection, or every collection.

        Args:
            collection: The collection to clear. If None, every
                collection is cleared.

        Returns:
            The number of records removed.
        """
        with self._lock:
            if collection is None:
                count = sum(len(bucket) for bucket in self._collections.values())
                self._collections.clear()
            else:
                bucket = self._collections.pop(collection, {})
                count = len(bucket)
        scope = "all collections" if collection is None else f"collection '{collection}'"
        logger.info(f"Knowledge cleared: {count} record(s) ({scope})")
        return count

    def list(self, collection: str | None = None) -> list[KnowledgeRecord]:
        """List records.

        Args:
            collection: If given, only records in this collection are
                returned. If None, records from every collection are
                returned.

        Returns:
            Records sorted by (collection, key).
        """
        with self._lock:
            if collection is None:
                records = [
                    record for bucket in self._collections.values() for record in bucket.values()
                ]
            else:
                records = list(self._collections.get(collection, {}).values())
        return sorted(records, key=lambda record: (record.collection, record.key))

    def collections(self) -> list[str]:
        """Return every collection that currently has at least one record.

        Returns:
            A sorted list of collection names.
        """
        with self._lock:
            return sorted(name for name, bucket in self._collections.items() if bucket)

    def count(self, collection: str | None = None) -> int:
        """Count records.

        Args:
            collection: If given, count only within this collection.
                If None, count records across every collection.

        Returns:
            The number of stored records.
        """
        with self._lock:
            if collection is None:
                return sum(len(bucket) for bucket in self._collections.values())
            return len(self._collections.get(collection, {}))

    def stats(self, collection: str | None = None) -> list[CollectionStats]:
        """Return per-collection statistics.

        Args:
            collection: If given, return statistics for just this
                collection (an empty list if it has no records). If
                None, return statistics for every non-empty collection.

        Returns:
            A list of CollectionStats, sorted by collection name.
        """
        with self._lock:
            if collection is None:
                names = sorted(name for name, bucket in self._collections.items() if bucket)
                return [
                    CollectionStats(name=name, record_count=len(self._collections[name]))
                    for name in names
                ]
            bucket = self._collections.get(collection)
            if not bucket:
                return []
            return [CollectionStats(name=collection, record_count=len(bucket))]
