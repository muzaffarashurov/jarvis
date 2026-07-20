"""Disk-backed persistence lifecycle for EP-013.2 Memory Configuration & Persistence.

MemoryPersistence owns the optional startup load and periodic
auto-save behavior for the Memory subsystem's 'memory.storage_file',
built only on `MemoryStore.export_snapshot()` / `import_snapshot()`.
It performs no CLI formatting and returns no `CommandResult` -- that
translation is MemoryService's job, exactly as MemoryStore itself
stays storage-only. This split exists solely to keep both files
under AI_GENERATION_STANDARD.md's file-size limit; it introduces no
new architecture, only a second layer of the same
Store/Service-style separation EP-013 already uses.

Mirrors the SchedulerService -> Scheduler background-loop pattern
('scheduler.tick_interval' / '_tick_loop' / SchedulerDiagnostics).
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from src.core.config import Config
from src.core.memory.memory_store import MemoryStore

DEFAULT_STORAGE_FILE: str = "data/database/memory.json"


@dataclass(frozen=True)
class PersistenceDiagnostics:
    """Persistence-related facts consumed by `MemoryService.doctor()`.

    Attributes:
        storage_file_valid: Whether 'memory.storage_file' resolves to
            a non-empty path.
        permissions_valid: Whether the storage file's parent directory
            exists or can be created (write permissions).
        auto_save_valid: Whether the auto-save loop's running state
            matches configuration.
        persistence_valid: Whether the storage file, if present,
            contains a valid JSON snapshot.
    """

    storage_file_valid: bool
    permissions_valid: bool
    auto_save_valid: bool
    persistence_valid: bool


class MemoryPersistence:
    """Owns startup load and periodic auto-save for a MemoryStore.

    Reads only its own settings from Config ('memory.persistent',
    'memory.storage_file', 'memory.auto_save',
    'memory.auto_save_interval') and depends only on MemoryStore.
    """

    def __init__(self, config: Config, store: MemoryStore) -> None:
        """Initialize the persistence lifecycle (does not start it).

        Args:
            config: Loaded application configuration, used to resolve
                'memory.persistent', 'memory.storage_file',
                'memory.auto_save', and 'memory.auto_save_interval'.
            store: The MemoryStore to load into / save from.
        """
        self._config = config
        self._store = store
        self._save_lock = threading.Lock()
        self._save_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ---------- Public API ----------

    def start(self) -> None:
        """Load the storage file and start auto-save, per configuration.

        No-op if 'memory.persistent' is False. Intended to be called
        once, by MemoryService, after 'memory.enabled' has already
        been confirmed True.
        """
        if not self.is_persistent():
            return
        self.load()
        if self.is_auto_save():
            self._start_auto_save_loop()

    def is_persistent(self) -> bool:
        """Return whether disk-backed persistence is on ('memory.persistent')."""
        return bool(self._config.get("memory.persistent", False))

    def is_auto_save(self) -> bool:
        """Return whether periodic auto-save is on ('memory.auto_save')."""
        return bool(self._config.get("memory.auto_save", True))

    def auto_save_interval(self) -> float:
        """Resolve the auto-save interval in seconds ('memory.auto_save_interval')."""
        return float(self._config.get("memory.auto_save_interval", 60))

    def storage_path(self) -> Path:
        """Resolve the configured persistence file ('memory.storage_file')."""
        configured = self._config.get("memory.storage_file", DEFAULT_STORAGE_FILE)
        return Path(str(configured))

    def load(self) -> None:
        """Load entries from the storage file into the MemoryStore, if present.

        A missing or invalid storage file is logged and skipped rather
        than raised, since a first run has no prior storage file yet.
        """
        path = self.storage_path()
        if not path.exists():
            return

        try:
            with path.open("r", encoding="utf-8") as file:
                raw = json.load(file)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error(f"Memory storage load failed: {exc}")
            return

        if not isinstance(raw, list):
            logger.error(f"Memory storage load failed: '{path}' must contain a JSON array.")
            return

        try:
            count = self._store.import_snapshot(raw)
        except (KeyError, TypeError, ValueError) as exc:
            logger.error(f"Memory storage load failed: invalid entry data ({exc}).")
            return

        logger.info(f"Memory storage loaded: {count} entries from '{path}'.")

    def save(self) -> tuple[bool, str]:
        """Write every persistent entry to the storage file.

        Callable directly for an explicit save (e.g. when
        'memory.auto_save' is False), and used internally by the
        auto-save loop when it is True.

        Returns:
            A (success, message) pair describing the outcome.
        """
        target = self.storage_path()
        snapshot = self._store.export_snapshot()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8") as file:
                json.dump(snapshot, file, indent=2)
        except OSError as exc:
            logger.error(f"Memory storage save failed: {exc}")
            return False, f"Memory storage save failed: {exc}"
        return True, f"Saved {len(snapshot)} entries to '{target}'."

    def is_running(self) -> bool:
        """Return whether the background auto-save thread is alive."""
        with self._save_lock:
            return self._save_thread is not None and self._save_thread.is_alive()

    def diagnostics(self, enabled: bool) -> PersistenceDiagnostics:
        """Return the persistence-related checks for `memory doctor`.

        Args:
            enabled: The Memory subsystem's own 'memory.enabled' state
                (owned by MemoryService), needed so a deliberately
                disabled subsystem isn't reported as a stopped
                auto-save failure.
        """
        return PersistenceDiagnostics(
            storage_file_valid=bool(str(self.storage_path())),
            permissions_valid=self._path_writable(self.storage_path()),
            auto_save_valid=self._validate_auto_save(enabled),
            persistence_valid=self._validate_persistence(),
        )

    # ---------- Internal helpers ----------

    def _start_auto_save_loop(self) -> None:
        """Start the background thread that calls `save()` periodically."""
        with self._save_lock:
            if self._save_thread is not None:
                return
            self._stop_event.clear()
            self._save_thread = threading.Thread(
                target=self._auto_save_loop, name="memory-auto-save", daemon=True
            )
            self._save_thread.start()
        logger.info("Memory auto-save started.")

    def _auto_save_loop(self) -> None:
        """Repeatedly call `save()` every 'memory.auto_save_interval' seconds."""
        interval = self.auto_save_interval()
        while not self._stop_event.wait(interval):
            success, message = self.save()
            if not success:
                logger.error(f"Memory auto-save failed: {message}")
        logger.info("Memory auto-save stopped.")

    def _validate_auto_save(self, enabled: bool) -> bool:
        """Return whether the auto-save loop's running state matches configuration."""
        if not (enabled and self.is_persistent() and self.is_auto_save()):
            return True
        return self.is_running()

    def _validate_persistence(self) -> bool:
        """Return whether persistence to the storage file actually works.

        Validates that any existing storage-file content is a readable
        JSON snapshot, and separately performs a real, non-destructive
        write-then-read round trip beside the storage file to confirm
        entries can genuinely be serialized, written to disk,
        deserialized, and read back -- rather than only checking that
        a file happens to already contain valid JSON.
        """
        if not self.is_persistent():
            return True

        path = self.storage_path()
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as file:
                    raw = json.load(file)
            except (OSError, json.JSONDecodeError):
                return False
            if not isinstance(raw, list):
                return False

        return self._round_trip_check(path)

    @staticmethod
    def _round_trip_check(path: Path) -> bool:
        """Write, read back, and remove a small probe file beside `path`.

        Args:
            path: The configured storage file; the probe file is
                created in the same directory and never overwrites it.

        Returns:
            True if the probe payload could be serialized, written,
            read back, deserialized, and matched exactly.
        """
        probe_path = path.with_name(f".{path.name}.doctor_probe")
        probe_payload = [{"doctor_probe": True}]
        try:
            probe_path.parent.mkdir(parents=True, exist_ok=True)
            with probe_path.open("w", encoding="utf-8") as file:
                json.dump(probe_payload, file)
            with probe_path.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
        except (OSError, json.JSONDecodeError):
            return False
        finally:
            try:
                probe_path.unlink(missing_ok=True)
            except OSError:
                pass
        return loaded == probe_payload

    @staticmethod
    def _path_writable(path: Path) -> bool:
        """Return whether `path`'s parent directory exists or can be created."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        return True
