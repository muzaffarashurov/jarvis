"""IndexStorage for the EP-019 Project Index Engine.

Defines the storage interface every backend implements, so
`ProjectIndexer` never depends on a concrete storage technology.
Ships with two backends now (in-memory, JSON-on-disk); future EPs may
add SQLite or a Vector DB backend behind the same interface without
touching `ProjectIndexer`.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path
from threading import RLock

from loguru import logger

from src.core.indexing.index import ProjectIndex

__all__ = ["IndexStorage", "JsonIndexStorage", "MemoryIndexStorage"]


class IndexStorage(ABC):
    """Storage interface for one `ProjectIndex`.

    Every backend persists (or holds) exactly one "current" index per
    instance -- callers needing multiple named indexes construct one
    storage instance per index (e.g. one `JsonIndexStorage` per output
    path).
    """

    @abstractmethod
    def save(self, index: ProjectIndex) -> None:
        """Persist `index`, replacing whatever was previously stored.

        Args:
            index: The index to persist.
        """
        raise NotImplementedError

    @abstractmethod
    def load(self) -> ProjectIndex | None:
        """Return the most recently saved index.

        Returns:
            The stored index, or None if nothing has been saved yet.
        """
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        """Remove whatever index is currently stored, if any."""
        raise NotImplementedError

    @abstractmethod
    def exists(self) -> bool:
        """Return whether an index is currently stored."""
        raise NotImplementedError


class MemoryIndexStorage(IndexStorage):
    """Holds one `ProjectIndex` in process memory. No persistence across restarts.

    Thread-safe via its own re-entrant lock.
    """

    def __init__(self) -> None:
        """Initialize an empty MemoryIndexStorage."""
        self._lock = RLock()
        self._index: ProjectIndex | None = None

    def save(self, index: ProjectIndex) -> None:
        with self._lock:
            self._index = index
        logger.info("Index saved (memory storage).")

    def load(self) -> ProjectIndex | None:
        with self._lock:
            index = self._index
        if index is not None:
            logger.info("Index loaded (memory storage).")
        return index

    def clear(self) -> None:
        with self._lock:
            self._index = None

    def exists(self) -> bool:
        with self._lock:
            return self._index is not None


class JsonIndexStorage(IndexStorage):
    """Persists one `ProjectIndex` as a single JSON file on disk.

    Thread-safe via its own re-entrant lock.
    """

    def __init__(self, path: Path) -> None:
        """Initialize a JsonIndexStorage.

        Args:
            path: File path the index is read from / written to. Its
                parent directory is created on first `save()` if
                missing.
        """
        self._path = path
        self._lock = RLock()

    @property
    def path(self) -> Path:
        """Return the file path this storage reads from / writes to."""
        return self._path

    def save(self, index: ProjectIndex) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(index.to_dict(), ensure_ascii=False, indent=2)
            self._path.write_text(payload, encoding="utf-8")
        logger.info(f"Index saved: '{self._path}'.")

    def load(self) -> ProjectIndex | None:
        with self._lock:
            if not self._path.is_file():
                return None
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(f"Unable to load index '{self._path}': {exc}")
                return None
        index = ProjectIndex.from_dict(data)
        logger.info(f"Index loaded: '{self._path}'.")
        return index

    def clear(self) -> None:
        with self._lock:
            if self._path.is_file():
                self._path.unlink()

    def exists(self) -> bool:
        with self._lock:
            return self._path.is_file()
