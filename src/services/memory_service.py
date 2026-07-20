"""Business logic for EP-013 Memory & Context Manager.

MemoryService is a core, LLM-independent service shared by the CLI,
Telegram Gateway, Scheduler, Workflow Engine and Plugins (via
PluginContext) to read and write runtime key/value context. Per
EP-013's architecture, it depends only on:

    MemoryService -> MemoryStore

It implements no business logic belonging to any other module and
never calls the Execution Engine, Workflow Engine, Scheduler,
Telegram, Plugin SDK, Invoice Automation, or Fast Response Board
directly.

EP-013.2 extends this service to read its own 'memory.*' section
from Config (enabled, persistent, storage_file, auto_save,
auto_save_interval, max_entries, default_ttl). The disk-backed load
/ auto-save lifecycle itself is delegated to MemoryPersistence (see
src/core/memory/memory_persistence.py) so this file stays within
AI_GENERATION_STANDARD.md's file-size limit; MemoryService still owns
every CLI-facing decision (whether the subsystem is enabled, TTL
defaults, max_entries enforcement, CommandResult formatting).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.memory.context import DEFAULT_NAMESPACE, MemoryEntry, utc_now
from src.core.memory.memory_persistence import MemoryPersistence
from src.core.memory.memory_store import MemoryStore

DEFAULT_EXPORT_FILE: str = "data/output/memory_export.json"


@dataclass(frozen=True)
class MemoryStatus:
    """Result of `memory status`.

    Attributes:
        total_entries: Total number of live (non-expired) entries.
        namespace_count: Number of namespaces with at least one entry.
        persistent_entries: Number of entries marked as persistent memory.
        session_entries: Number of entries scoped to this process only.
        enabled: Whether the Memory subsystem is enabled ('memory.enabled').
        persistent: Whether disk-backed persistence is on ('memory.persistent').
        storage_file: The configured persistence file ('memory.storage_file').
        auto_save: Whether periodic auto-save is on ('memory.auto_save').
        auto_save_interval: Seconds between auto-saves ('memory.auto_save_interval').
        max_entries: Maximum entries allowed ('memory.max_entries').
        default_ttl: Default TTL in seconds, or None for no expiration
            ('memory.default_ttl').
    """

    total_entries: int
    namespace_count: int
    persistent_entries: int
    session_entries: int
    enabled: bool
    persistent: bool
    storage_file: str
    auto_save: bool
    auto_save_interval: float
    max_entries: int
    default_ttl: float | None


@dataclass(frozen=True)
class MemoryDoctorReport:
    """Result of `memory doctor`.

    Attributes:
        store_available: Whether the MemoryStore dependency is present.
        configuration_loaded: Whether every 'memory.*' setting has a
            valid type and value.
        export_path_writable: Whether the configured export file's
            parent directory exists or can be created.
        entries_valid: Whether every stored entry has a non-empty key
            and namespace.
        storage_file_valid: Whether 'memory.storage_file' resolves to
            a non-empty path.
        permissions_valid: Whether the storage file's parent directory
            exists or can be created (write permissions).
        auto_save_valid: Whether the auto-save loop's running state
            matches configuration.
        persistence_valid: Whether the storage file, if present,
            contains a valid JSON snapshot.
        ttl_valid: Whether 'memory.default_ttl' is None or a positive
            number.
    """

    store_available: bool
    configuration_loaded: bool
    export_path_writable: bool
    entries_valid: bool
    storage_file_valid: bool
    permissions_valid: bool
    auto_save_valid: bool
    persistence_valid: bool
    ttl_valid: bool

    @property
    def is_ready(self) -> bool:
        """Return True only if every diagnostic check passed."""
        return (
            self.store_available
            and self.configuration_loaded
            and self.export_path_writable
            and self.entries_valid
            and self.storage_file_valid
            and self.permissions_valid
            and self.auto_save_valid
            and self.persistence_valid
            and self.ttl_valid
        )


class MemoryService:
    """Coordinates the MemoryStore and exposes it as a CLI-friendly API.

    Depends only on MemoryStore (storage) and Config (its own
    'memory.*' settings), matching EP-013's architecture: MemoryModule
    -> MemoryService -> MemoryStore, plus MemoryPersistence for the
    disk-backed load/auto-save lifecycle. Implements no domain logic
    belonging to any other Episode.

    EP-013.2: at construction, if 'memory.enabled' is False the
    subsystem does not start (no load, no auto-save) and every
    mutating operation is rejected. Otherwise MemoryPersistence.start()
    decides, from 'memory.persistent' / 'memory.auto_save', whether to
    load 'memory.storage_file' and run the auto-save loop.
    """

    def __init__(self, config: Config, store: MemoryStore) -> None:
        """Initialize the MemoryService and, per configuration, start persistence.

        Args:
            config: Loaded application configuration, used to resolve
                'memory.*' settings.
            store: The MemoryStore used to persist and retrieve entries.
        """
        self._config = config
        self._store = store
        self._persistence = MemoryPersistence(config=config, store=store)

        if self._is_enabled():
            self._persistence.start()

    # ---------- Public API ----------

    def set(
        self,
        key: str,
        value: Any,
        namespace: str = DEFAULT_NAMESPACE,
        persistent: bool | None = None,
        ttl_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CommandResult:
        """Store a value under `key` in `namespace`.

        Args:
            key: The key to store the value under.
            value: The value to store. Should be JSON-serializable if
                `persistent` is True.
            namespace: The namespace to store the value in.
            persistent: Whether this entry belongs in `export`
                (persistent memory) or stays session-only. Defaults to
                'memory.persistent' when not given, so entries created
                through the CLI (which never passes this argument)
                follow the subsystem's configured persistence mode
                instead of silently always being session-only.
            ttl_seconds: Optional time-to-live in seconds, after which
                the entry is treated as absent. Defaults to
                'memory.default_ttl' when not given.
            metadata: Optional caller-supplied metadata about the entry.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        if not key:
            return CommandResult(success=False, message="Key must not be empty.")

        if persistent is None:
            persistent = self._persistence.is_persistent()

        existing = self._store.get(namespace, key)
        if existing is None and self._store.count() >= self._max_entries():
            return CommandResult(
                success=False,
                message=f"Memory max_entries exceeded (max={self._max_entries()}).",
            )

        if ttl_seconds is None:
            ttl_seconds = self._default_ttl()

        expires_at = None
        if ttl_seconds is not None:
            if ttl_seconds <= 0:
                return CommandResult(
                    success=False, message="TTL must be a positive number of seconds."
                )
            expires_at = utc_now() + timedelta(seconds=ttl_seconds)

        entry = MemoryEntry(
            key=key,
            value=value,
            namespace=namespace,
            persistent=persistent,
            metadata=metadata or {},
            created_at=existing.created_at if existing is not None else utc_now(),
            updated_at=utc_now(),
            expires_at=expires_at,
        )
        self._store.set(entry)
        return CommandResult(
            success=True, message=f"Key '{key}' set in namespace '{namespace}'."
        )

    def get(self, key: str, namespace: str = DEFAULT_NAMESPACE) -> MemoryEntry | None:
        """Retrieve a stored entry.

        Args:
            key: The key to look up.
            namespace: The namespace to look in.

        Returns:
            The stored MemoryEntry, or None if absent or expired.
        """
        return self._store.get(namespace, key)

    def delete(self, key: str, namespace: str = DEFAULT_NAMESPACE) -> CommandResult:
        """Delete a single entry.

        Args:
            key: The key to delete.
            namespace: The namespace to delete from.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        removed = self._store.delete(namespace, key)
        if not removed:
            return CommandResult(
                success=False, message=f"Key not found: '{key}' in namespace '{namespace}'."
            )
        return CommandResult(success=True, message=f"Key '{key}' deleted.")

    def clear(self, namespace: str | None = None) -> CommandResult:
        """Clear all entries in a namespace, or every namespace.

        Args:
            namespace: The namespace to clear. If None, every
                namespace is cleared.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        count = self._store.clear(namespace)
        scope = "all namespaces" if namespace is None else f"namespace '{namespace}'"
        return CommandResult(success=True, message=f"Cleared {count} entries from {scope}.")

    def list_entries(self, namespace: str | None = None) -> list[MemoryEntry]:
        """List stored entries.

        Args:
            namespace: If given, only entries in this namespace are
                returned. If None, entries from every namespace are
                returned.

        Returns:
            The matching entries, sorted by (namespace, key).
        """
        return self._store.list(namespace)

    def status(self) -> MemoryStatus:
        """Return the `memory status` snapshot."""
        entries = self._store.list()
        persistent = sum(1 for entry in entries if entry.persistent)
        return MemoryStatus(
            total_entries=len(entries),
            namespace_count=len(self._store.namespaces()),
            persistent_entries=persistent,
            session_entries=len(entries) - persistent,
            enabled=self._is_enabled(),
            persistent=self._persistence.is_persistent(),
            storage_file=str(self._persistence.storage_path()),
            auto_save=self._persistence.is_auto_save(),
            auto_save_interval=self._persistence.auto_save_interval(),
            max_entries=self._max_entries(),
            default_ttl=self._default_ttl(),
        )

    def doctor(self) -> MemoryDoctorReport:
        """Run the `memory doctor` diagnostic checks."""
        entries_valid = all(
            bool(entry.key) and bool(entry.namespace) for entry in self._store.list()
        )
        persistence = self._persistence.diagnostics(enabled=self._is_enabled())

        return MemoryDoctorReport(
            store_available=self._store is not None,
            configuration_loaded=self._validate_configuration(),
            export_path_writable=self._path_writable(self._export_path()),
            entries_valid=entries_valid,
            storage_file_valid=persistence.storage_file_valid,
            permissions_valid=persistence.permissions_valid,
            auto_save_valid=persistence.auto_save_valid,
            persistence_valid=persistence.persistence_valid,
            ttl_valid=self._validate_ttl(),
        )

    def export(self, path: str | None = None) -> CommandResult:
        """Write every persistent entry to a JSON file.

        Args:
            path: Destination file path. Defaults to 'memory.export_file'.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        target = Path(path) if path else self._export_path()
        snapshot = self._store.export_snapshot()

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as file:
                json.dump(snapshot, file, indent=2)
        except OSError as exc:
            logger.error(f"Memory export failed: {exc}")
            return CommandResult(success=False, message=f"Memory export failed: {exc}")

        return CommandResult(
            success=True, message=f"Exported {len(snapshot)} entries to '{target}'."
        )

    def import_(self, path: str | None = None) -> CommandResult:
        """Load entries from a previously exported JSON file.

        Args:
            path: Source file path. Defaults to 'memory.export_file'.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        source = Path(path) if path else self._export_path()
        if not source.exists():
            return CommandResult(success=False, message=f"Import file not found: '{source}'.")

        try:
            with source.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error(f"Memory import failed: {exc}")
            return CommandResult(success=False, message=f"Memory import failed: {exc}")

        if not isinstance(raw, list):
            return CommandResult(
                success=False, message="Import file must contain a JSON array of entries."
            )

        try:
            count = self._store.import_snapshot(raw)
        except (KeyError, TypeError, ValueError) as exc:
            logger.error(f"Memory import failed: {exc}")
            return CommandResult(
                success=False, message=f"Memory import failed: invalid entry data ({exc})."
            )

        return CommandResult(success=True, message=f"Imported {count} entries from '{source}'.")

    def save(self) -> CommandResult:
        """Persist every persistent entry to 'memory.storage_file'.

        Used internally by MemoryPersistence's auto-save loop when
        'memory.auto_save' is True, and available for an explicit
        save when it is False.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled
        if not self._persistence.is_persistent():
            return CommandResult(
                success=False,
                message="Memory persistence disabled (memory.persistent=false); "
                "running in RAM-only mode.",
            )

        success, message = self._persistence.save()
        return CommandResult(success=success, message=message)

    # ---------- Internal helpers: configuration ----------

    def _is_enabled(self) -> bool:
        """Return whether the Memory subsystem is enabled ('memory.enabled')."""
        return bool(self._config.get("memory.enabled", True))

    def _max_entries(self) -> int:
        """Resolve the maximum number of entries allowed ('memory.max_entries')."""
        return int(self._config.get("memory.max_entries", 10000))

    def _default_ttl(self) -> float | None:
        """Resolve the default TTL in seconds, or None ('memory.default_ttl')."""
        value = self._config.get("memory.default_ttl", None)
        return float(value) if value is not None else None

    def _export_path(self) -> Path:
        """Resolve the configured export/import file path, defaulting under 'data/output'."""
        configured = self._config.get("memory.export_file", DEFAULT_EXPORT_FILE)
        return Path(str(configured))

    def _ensure_enabled(self) -> CommandResult | None:
        """Return a failing CommandResult if 'memory.enabled' is False.

        Returns:
            A failing CommandResult if the Memory subsystem is
            disabled, otherwise None (meaning the caller may proceed).
        """
        if self._is_enabled():
            return None
        logger.error("Memory operation rejected: Memory subsystem disabled.")
        return CommandResult(success=False, message="Memory subsystem disabled.")

    # ---------- Internal helpers: doctor validation ----------

    def _validate_configuration(self) -> bool:
        """Return whether every 'memory.*' setting has a valid type and value."""
        return (
            isinstance(self._config.get("memory.enabled", True), bool)
            and isinstance(self._config.get("memory.persistent", False), bool)
            and isinstance(self._config.get("memory.storage_file", ""), str)
            and isinstance(self._config.get("memory.auto_save", True), bool)
            and self._persistence.auto_save_interval() > 0
            and self._max_entries() > 0
            and self._validate_ttl()
        )

    def _validate_ttl(self) -> bool:
        """Return whether 'memory.default_ttl' is None or a positive number."""
        ttl = self._config.get("memory.default_ttl", None)
        if ttl is None:
            return True
        return isinstance(ttl, (int, float)) and not isinstance(ttl, bool) and ttl > 0

    @staticmethod
    def _path_writable(path: Path) -> bool:
        """Return whether `path`'s parent directory exists or can be created."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        return True
