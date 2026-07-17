"""Tracks OS processes launched by Jarvis so they can be listed and stopped."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class ProcessRecord:
    """A single Jarvis-tracked process.

    Attributes:
        process_id: Jarvis-assigned sequential ID (distinct from the OS PID).
        name: Display name of the launched target (e.g. "notepad.exe").
        handle: The underlying subprocess.Popen handle.
    """

    process_id: int
    name: str
    handle: subprocess.Popen


class ProcessRegistry:
    """Thread-safe registry of processes started by the ExecutionEngine.

    Responsibilities:
        - Assign sequential, human-friendly IDs to launched processes.
        - Track processes started by Jarvis while they are running.
        - Report the list of processes still alive.
        - Remove records for processes that have exited or been stopped.
    """

    def __init__(self) -> None:
        """Initialize an empty ProcessRegistry."""
        self._records: dict[int, ProcessRecord] = {}
        self._next_id: int = 1
        self._lock = Lock()

    def register(self, name: str, handle: subprocess.Popen) -> int:
        """Register a newly launched process and assign it an ID.

        Args:
            name: Display name of the launched target.
            handle: The Popen handle of the launched process.

        Returns:
            The Jarvis-assigned sequential process ID.
        """
        with self._lock:
            process_id = self._next_id
            self._next_id += 1
            self._records[process_id] = ProcessRecord(process_id, name, handle)
            return process_id

    def list_running(self) -> list[ProcessRecord]:
        """Return all tracked processes that are still running.

        Prunes records for processes that have already exited as a
        side effect of this call.

        Returns:
            A list of ProcessRecord entries whose handle has not exited.
        """
        with self._lock:
            alive = {
                process_id: record
                for process_id, record in self._records.items()
                if record.handle.poll() is None
            }
            self._records = alive
            return list(alive.values())

    def get(self, process_id: int) -> ProcessRecord | None:
        """Return the record for a given process ID, if tracked and alive.

        Args:
            process_id: The Jarvis-assigned process ID.

        Returns:
            The ProcessRecord, or None if unknown or no longer running.
        """
        with self._lock:
            record = self._records.get(process_id)

        if record is None:
            return None

        if record.handle.poll() is not None:
            self.remove(process_id)
            return None

        return record

    def remove(self, process_id: int) -> None:
        """Remove a process record from the registry.

        Args:
            process_id: The Jarvis-assigned process ID to remove.
        """
        with self._lock:
            self._records.pop(process_id, None)
