"""Thread-safe in-memory storage engine for EP-013 Memory & Context Manager.

MemoryStore only stores and retrieves `MemoryEntry` objects; it performs
no CLI formatting, no configuration resolution, and no file I/O of its
own. It mirrors the storage-only role of `JobRegistry` and
`ProcessRegistry` (see `src/core/scheduler/job_registry.py` and
`src/core/processes/process_registry.py`), and adopts the same
lock-per-instance thread-safety pattern, since memory is written and
read concurrently by the CLI, Telegram, Scheduler, Workflow Engine and
Plugins.

Writing export snapshots to disk (or reading them back) is a
MemoryService concern; this module only (de)serializes entries to and
from plain, JSON-ready dictionaries.
"""

from __future__ import annotations

from threading import RLock
from typing import Any

from loguru import logger

from src.core.memory.context import MemoryEntry, utc_now


class MemoryStoreError(Exception):
    """Raised for invalid memory store operations."""


class MemoryStore:
    """Thread-safe, namespaced, in-memory store of MemoryEntry objects.

    Responsibilities:
        - Store, retrieve, and delete MemoryEntry objects, keyed by
          (namespace, key).
        - Group entries by namespace.
        - Lazily purge entries whose TTL has elapsed.
        - Serialize/deserialize persistent entries to/from plain dict
          snapshots for export/import.
    """

    def __init__(self) -> None:
        """Initialize an empty MemoryStore."""
        self._namespaces: dict[str, dict[str, MemoryEntry]] = {}
        self._lock = RLock()

    def set(self, entry: MemoryEntry) -> None:
        """Store (or overwrite) an entry under its namespace and key.

        Args:
            entry: The MemoryEntry to store.
        """
        with self._lock:
            bucket = self._namespaces.setdefault(entry.namespace, {})
            bucket[entry.key] = entry
        logger.debug(f"Memory set: '{entry.namespace}:{entry.key}'")

    def get(self, namespace: str, key: str) -> MemoryEntry | None:
        """Retrieve an entry, purging it first if its TTL has elapsed.

        Args:
            namespace: The namespace to look in.
            key: The key to look up.

        Returns:
            The stored MemoryEntry, or None if absent or expired.
        """
        with self._lock:
            bucket = self._namespaces.get(namespace)
            if bucket is None:
                return None
            entry = bucket.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del bucket[key]
                logger.debug(f"Memory expired: '{namespace}:{key}'")
                return None
            return entry

    def delete(self, namespace: str, key: str) -> bool:
        """Delete a single entry.

        Args:
            namespace: The namespace to delete from.
            key: The key to delete.

        Returns:
            True if an entry was removed, False if it did not exist.
        """
        with self._lock:
            bucket = self._namespaces.get(namespace)
            if bucket is None or key not in bucket:
                return False
            del bucket[key]
        logger.info(f"Memory deleted: '{namespace}:{key}'")
        return True

    def clear(self, namespace: str | None = None) -> int:
        """Remove all entries in a namespace, or every namespace.

        Args:
            namespace: The namespace to clear. If None, every
                namespace is cleared.

        Returns:
            The number of entries removed.
        """
        with self._lock:
            if namespace is None:
                count = sum(len(bucket) for bucket in self._namespaces.values())
                self._namespaces.clear()
            else:
                bucket = self._namespaces.pop(namespace, {})
                count = len(bucket)
        scope = "all namespaces" if namespace is None else f"namespace '{namespace}'"
        logger.info(f"Memory cleared: {count} entr{'y' if count == 1 else 'ies'} ({scope})")
        return count

    def list(self, namespace: str | None = None) -> list[MemoryEntry]:
        """List entries, purging any that have expired.

        Args:
            namespace: If given, only entries in this namespace are
                returned. If None, entries from every namespace are
                returned.

        Returns:
            Entries sorted by (namespace, key).
        """
        with self._lock:
            self._purge_expired()
            if namespace is None:
                entries = [entry for bucket in self._namespaces.values() for entry in bucket.values()]
            else:
                entries = list(self._namespaces.get(namespace, {}).values())
        return sorted(entries, key=lambda entry: (entry.namespace, entry.key))

    def namespaces(self) -> list[str]:
        """Return every namespace that currently has at least one entry.

        Returns:
            A sorted list of namespace names.
        """
        with self._lock:
            return sorted(name for name, bucket in self._namespaces.items() if bucket)

    def count(self, namespace: str | None = None) -> int:
        """Count entries.

        Args:
            namespace: If given, count only within this namespace.
                If None, count entries across every namespace.

        Returns:
            The number of stored entries.
        """
        with self._lock:
            if namespace is None:
                return sum(len(bucket) for bucket in self._namespaces.values())
            return len(self._namespaces.get(namespace, {}))

    def export_snapshot(self) -> list[dict[str, Any]]:
        """Serialize every persistent (non-session) entry for export.

        Session-only entries (`persistent=False`) are intentionally
        excluded, since they are scoped to the running process.

        Returns:
            A list of plain dictionaries (see `MemoryEntry.to_dict`),
            sorted by (namespace, key).
        """
        with self._lock:
            self._purge_expired()
            entries = [
                entry.to_dict()
                for bucket in self._namespaces.values()
                for entry in bucket.values()
                if entry.persistent
            ]
        return sorted(entries, key=lambda item: (item["namespace"], item["key"]))

    def import_snapshot(self, snapshot: list[dict[str, Any]]) -> int:
        """Load entries from a previously exported snapshot.

        Existing entries with the same (namespace, key) are overwritten.

        Args:
            snapshot: A list of plain dictionaries as produced by
                `export_snapshot` / `MemoryEntry.to_dict`.

        Returns:
            The number of entries imported.

        Raises:
            KeyError: If an entry dictionary is missing a required field.
            TypeError: If an entry field has an unexpected type.
            ValueError: If an entry's timestamp is not valid ISO-8601.
        """
        parsed = [MemoryEntry.from_dict(raw) for raw in snapshot]
        with self._lock:
            for entry in parsed:
                bucket = self._namespaces.setdefault(entry.namespace, {})
                bucket[entry.key] = entry
        logger.info(f"Memory imported: {len(parsed)} entries")
        return len(parsed)

    def _purge_expired(self) -> None:
        """Remove every entry whose TTL has elapsed.

        Caller must already hold `self._lock`.
        """
        now = utc_now()
        for bucket in self._namespaces.values():
            expired_keys = [key for key, entry in bucket.items() if entry.is_expired(now)]
            for key in expired_keys:
                del bucket[key]
