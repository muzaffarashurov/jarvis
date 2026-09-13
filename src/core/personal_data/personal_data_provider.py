"""Storage-provider abstraction for EP-092 Personal Data Collection Framework.

Defines the unified store/store_if_new/exists/query/stats contract
every personal-data storage backend must implement
(`PersonalDataProvider`), plus its sole approved concrete
implementation:

    JsonlPersonalDataProvider
        Persists `PersonalDataPoint` records as append-only JSONL --
        one file per category under 'personal_data.storage_root'
        (default "data/database/personal_data") -- delegating all raw
        file reads/writes to `PersonalDataPersistence`
        (`personal_data_persistence.py`). This is the Owner-approved
        Option B persistence backend (EP-092 STEP 1 design §21):
        Knowledge Base (EP-024) was evaluated and rejected, because
        `KnowledgeCollection` is an in-memory, overwrite-per-key store
        and personal data is unbounded, append-only time-series data
        that must preserve every individual observation. This module
        has zero import dependency on `src/core/knowledge/` or
        `src/services/knowledge_service.py`.

`PersonalDataProvider` remains the abstraction boundary regardless: a
second implementation could be added later without touching
`PersonalDataManager` or anything above it, but none is planned.

This module performs no reasoning, ranking, similarity search, or
embeddings, and must never import Embedding, Retrieval, RAG, Semantic
Search, Context Compression, Reflection, Planner, Agent Framework,
Browser Automation, Vector Database, or any future EP.
"""

from __future__ import annotations

import json
import threading
from abc import ABC, abstractmethod
from datetime import datetime

from loguru import logger

from src.core.config import Config
from src.core.personal_data.personal_data_persistence import (
    PersonalDataPersistence,
    PersonalDataPersistenceError,
)
from src.core.personal_data.personal_data_record import PersonalDataPoint

DedupKey = tuple[str, str, datetime]


class PersonalDataProviderError(Exception):
    """Raised for invalid Personal Data Collection provider operations (EP-092)."""


class PersonalDataProvider(ABC):
    """Unified storage contract used exclusively by `PersonalDataManager`.

    `PersonalDataManager` never performs file I/O directly and never
    knows about JSONL or file paths -- it only calls this abstract
    contract.
    """

    @abstractmethod
    def store(self, point: PersonalDataPoint) -> None:
        """Persist `point`.

        Callers (`PersonalDataManager`) are responsible for the
        consent (`personal_data.enabled_categories`) and dedup
        (`exists()`) checks before calling `store()` -- this method
        unconditionally persists `point` and updates the dedup index.

        This method alone is NOT safe against concurrent duplicate
        writes: a caller that calls `exists()` then `store()` as two
        separate steps is exposed to a check-then-act race between
        concurrent callers (EP-092 STEP 3 audit finding
        EP092-AUDIT-002). Callers that need a dedup guarantee under
        concurrent collection must use `store_if_new()` instead, which
        performs the check and the store atomically.

        Raises:
            PersonalDataProviderError: If `point` cannot be persisted.
        """
        raise NotImplementedError

    @abstractmethod
    def store_if_new(self, point: PersonalDataPoint) -> bool:
        """Atomically check-and-store `point` if its dedup key is not already present.

        This is the concurrency-safe combination of `exists()` and
        `store()`: implementations must guarantee that the existence
        check and the store are atomic with respect to other
        concurrent calls to `store_if_new()` (and to `store()`/
        `exists()`) on the same provider instance. `PersonalDataManager
        .collect_from()` uses this method, not a separate `exists()`
        + `store()` sequence, specifically to close that race
        (EP-092 STEP 3 audit finding EP092-AUDIT-002).

        Args:
            point: The point to store if not already present.

        Returns:
            True if `point` was newly stored, False if a point with
            the same dedup key (`source_id`, `category`, `timestamp`)
            already existed -- a no-op, not an error.

        Raises:
            PersonalDataProviderError: If persisting `point` fails.
                On failure, the dedup index must NOT be updated -- a
                failed write must never be treated as if the point
                were stored.
        """
        raise NotImplementedError

    @abstractmethod
    def exists(self, source_id: str, category: str, timestamp: datetime) -> bool:
        """Return whether a point with this dedup key has already been stored.

        The dedup key is exactly `(source_id, category, timestamp)` --
        never a point's `collected_at` (see `personal_data_record.py`).
        """
        raise NotImplementedError

    @abstractmethod
    def query(
        self, category: str, start: datetime | None = None, end: datetime | None = None
    ) -> list[PersonalDataPoint]:
        """Return persisted points for `category`, optionally bounded by time.

        Args:
            category: The category to query.
            start: If given, only points with `timestamp >= start`.
            end: If given, only points with `timestamp <= end`.

        Returns:
            Matching points, sorted by `timestamp`. Empty if
            `category` has never been collected.
        """
        raise NotImplementedError

    @abstractmethod
    def stats(self) -> dict[str, int]:
        """Return aggregate storage statistics.

        Returns:
            A dictionary with at least `"category_count"` (number of
            categories with at least one stored point) and
            `"point_count"` (total points across every category).
        """
        raise NotImplementedError


class JsonlPersonalDataProvider(PersonalDataProvider):
    """Persists `PersonalDataPoint` records as append-only JSONL, one file per category.

    Owns dedup-index bookkeeping and query filtering; delegates all
    raw file reads/writes to `PersonalDataPersistence`. This is the
    sole implementation of `PersonalDataProvider` for EP-092 (Owner
    Decision, STEP 1 design §21) -- a Knowledge-Base-backed
    alternative was evaluated and rejected, and is not implemented.

    Dedup-index rebuild on initialization: this provider does not
    persist its dedup index separately. On construction it discovers
    every category with an existing `.jsonl` file (via
    `PersonalDataPersistence.known_categories()`), reads each once,
    and rebuilds an in-memory index containing *only the dedup keys*
    (`set[DedupKey]` of `(source_id, category, timestamp)`), never
    full `PersonalDataPoint` objects. Each category is processed
    independently: a category whose on-disk file name fails
    `category_path()`'s validation (e.g. a legacy or externally-placed
    file predating the stricter validation added for
    EP092-AUDIT-001) is logged and skipped, without aborting
    construction or affecting any other, valid category
    (EP092-AUDIT-004) -- construction never bypasses that validation
    to read a skipped file, and a skipped category's keys are simply
    absent from the index, never silently treated as valid. After
    that one-time rebuild, `exists()` is an in-memory set lookup;
    `store()` appends to both the file (via `PersonalDataPersistence`)
    and the in-memory index. No database and no second cache of full
    history is introduced -- the index holds keys only. `query()`
    does not read the dedup index; it reads and filters the persisted
    `.jsonl` data directly, via `PersonalDataPersistence`, once per
    call.

    Concurrency: a single `threading.Lock` guards every read/write of
    `_dedup_index` together with its corresponding file write, so
    `store()`, `exists()`, and `store_if_new()` are each atomic with
    respect to one another on this instance (EP-092 STEP 3 audit
    finding EP092-AUDIT-002). `store_if_new()` holds the lock across
    both the existence check and the store, closing the check-then-act
    race a separate `exists()` + `store()` sequence is exposed to.
    `query()`/`stats()` read directly from disk and do not touch
    `_dedup_index`, so they are not guarded by this lock.
    """

    def __init__(self, config: Config, persistence: PersonalDataPersistence | None = None) -> None:
        """Initialize the provider and rebuild its dedup-key index from disk.

        Args:
            config: Loaded application configuration, forwarded to
                `PersonalDataPersistence` if `persistence` is not
                given.
            persistence: The `PersonalDataPersistence` instance to
                delegate raw file I/O to. If None, a default one is
                built from `config`.
        """
        self._persistence = persistence if persistence is not None else PersonalDataPersistence(config)
        self._lock = threading.Lock()
        self._dedup_index: set[DedupKey] = self._rebuild_dedup_index()

    def store(self, point: PersonalDataPoint) -> None:
        """Append `point` to its category's `.jsonl` file and update the dedup index.

        Unconditional: does not check `exists()` first. Callers that
        need a dedup guarantee under concurrent collection should use
        `store_if_new()` instead.

        Raises:
            PersonalDataProviderError: If the underlying file write
                fails, or if `point.category` is not a safe filesystem
                path component.
        """
        with self._lock:
            self._write_and_index_locked(point)

    def store_if_new(self, point: PersonalDataPoint) -> bool:
        """Atomically check-and-store `point` if its dedup key is not already present.

        Holds the same lock `store()`/`exists()` use across both the
        existence check and the store, so concurrent callers cannot
        both observe "not yet stored" and both write a duplicate (see
        the class docstring and EP092-AUDIT-002).

        Raises:
            PersonalDataProviderError: If the underlying file write
                fails, or if `point.category` is not a safe filesystem
                path component. On failure, the dedup index is not
                updated.
        """
        with self._lock:
            if point.dedup_key() in self._dedup_index:
                return False
            self._write_and_index_locked(point)
            return True

    def exists(self, source_id: str, category: str, timestamp: datetime) -> bool:
        """Return whether `(source_id, category, timestamp)` is already stored."""
        with self._lock:
            return (source_id, category, timestamp) in self._dedup_index

    def query(
        self, category: str, start: datetime | None = None, end: datetime | None = None
    ) -> list[PersonalDataPoint]:
        """Read and filter `category`'s persisted `.jsonl` data directly from disk.

        Raises:
            PersonalDataProviderError: If `category` is not a safe
                filesystem path component.
        """
        points: list[PersonalDataPoint] = []
        try:
            for line in self._persistence.read_lines(category):
                point = self._deserialize_line(line)
                if point is None:
                    continue
                if start is not None and point.timestamp < start:
                    continue
                if end is not None and point.timestamp > end:
                    continue
                points.append(point)
        except PersonalDataPersistenceError as exc:
            raise PersonalDataProviderError(str(exc)) from exc
        points.sort(key=lambda point: point.timestamp)
        return points

    def stats(self) -> dict[str, int]:
        """Return aggregate storage statistics across every persisted category."""
        categories = self._persistence.known_categories()
        total = sum(self._persistence.line_count(category) for category in categories)
        return {"category_count": len(categories), "point_count": total}

    # ---------- Internal helpers ----------

    def _write_and_index_locked(self, point: PersonalDataPoint) -> None:
        """Write `point` to disk and update the dedup index. Caller must hold `self._lock`.

        The dedup index is updated only after the write succeeds --
        on failure, nothing is added to the index (see
        EP092-AUDIT-002's "a failed write must not incorrectly mark a
        point as persisted" requirement).

        Raises:
            PersonalDataProviderError: If the underlying file write
                fails, or if `point.category` is not a safe filesystem
                path component.
        """
        try:
            self._persistence.append_line(point.category, json.dumps(point.to_dict()))
        except (OSError, PersonalDataPersistenceError) as exc:
            raise PersonalDataProviderError(
                f"Failed to persist personal data point '{point.id}': {exc}"
            ) from exc
        self._dedup_index.add(point.dedup_key())

    def _rebuild_dedup_index(self) -> set[DedupKey]:
        """Scan every persisted category once and rebuild the dedup-key index.

        Reads only the dedup-key fields (`source_id`, `category`,
        `timestamp`) out of each persisted line -- never retains full
        `PersonalDataPoint` objects (see the class docstring).

        Each category discovered by `known_categories()` is processed
        independently: if a category's file name fails
        `category_path()`'s validation (EP-092 STEP 3 audit finding
        EP092-AUDIT-004 -- e.g. a legacy or externally-placed file
        whose name predates the stricter allowlist introduced for
        EP092-AUDIT-001), that one category is logged and skipped,
        and every other, valid category is still rebuilt normally.
        Construction never bypasses `category_path()`'s validation to
        read a skipped file, and a skipped category is never treated
        as if it were valid -- its keys are simply absent from the
        index, exactly as if it had never been collected.
        """
        index: set[DedupKey] = set()
        for category in self._persistence.known_categories():
            try:
                for line in self._persistence.read_lines(category):
                    key = self._extract_dedup_key(line)
                    if key is not None:
                        index.add(key)
            except PersonalDataPersistenceError as exc:
                logger.error(
                    f"Personal data dedup-index rebuild: skipping invalid on-disk "
                    f"category '{category}' ({exc})."
                )
                continue
        return index

    @staticmethod
    def _extract_dedup_key(line: str) -> DedupKey | None:
        """Parse just the dedup-key fields out of a persisted JSONL line.

        Returns:
            The `(source_id, category, timestamp)` key, or None if
            `line` is malformed (logged and skipped rather than
            raised, so one corrupted line does not prevent startup).
        """
        try:
            data = json.loads(line)
            return (
                str(data["source_id"]),
                str(data["category"]),
                datetime.fromisoformat(data["timestamp"]),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.error(f"Personal data dedup-index rebuild: skipping malformed line ({exc}).")
            return None

    @staticmethod
    def _deserialize_line(line: str) -> PersonalDataPoint | None:
        """Parse a persisted JSONL line into a `PersonalDataPoint`.

        Returns:
            The reconstructed point, or None if `line` is malformed
            (logged and skipped rather than raised, so one corrupted
            line does not fail an entire `query()` call).
        """
        try:
            return PersonalDataPoint.from_dict(json.loads(line))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.error(f"Personal data query: skipping malformed line ({exc}).")
            return None
