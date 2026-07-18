"""Catalog registry for EP-008 Process Catalog & Smart Orchestrator.

ProcessRegistry stores *catalog metadata* only: which processes exist,
their declared dependencies, restart policy, and timeouts. It owns no
runtime/liveness state -- that would duplicate what the underlying
services (InvoiceService, FastResponseService) and ExecutionEngine
already own, which the project's Single Source of Truth rule forbids.

Naming note: this is a distinct component from
`src.core.execution.process_registry.ProcessRegistry`, which tracks
raw OS-level subprocess handles launched by the ExecutionEngine. That
registry is untouched by EP-008. This registry tracks named, logical
processes (catalog entries) that ProcessService coordinates; it holds
no subprocess handles at all.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.processes.process import Process


class ProcessRegistryError(Exception):
    """Raised for invalid catalog operations (e.g. duplicate process id)."""


class ProcessRegistry:
    """Thread-safe catalog of processes known to the Process Catalog.

    Responsibilities:
        - Register a process in the catalog.
        - Remove a process from the catalog.
        - Find a single process by id.
        - List all registered processes.
        - Report whether a given process id is currently registered.
    """

    def __init__(self) -> None:
        """Initialize an empty ProcessRegistry."""
        self._processes: dict[str, Process] = {}
        self._lock = Lock()

    def register(self, process: Process) -> None:
        """Register a process in the catalog.

        Args:
            process: The Process to add.

        Raises:
            ProcessRegistryError: If a process with the same id is
                already registered.
        """
        with self._lock:
            if process.id in self._processes:
                raise ProcessRegistryError(f"Process already registered: '{process.id}'.")
            self._processes[process.id] = process
        logger.info(f"Process registered: '{process.id}'.")

    def remove(self, process_id: str) -> None:
        """Remove a process from the catalog, if present.

        Args:
            process_id: The id of the process to remove.
        """
        with self._lock:
            removed = self._processes.pop(process_id, None)
        if removed is not None:
            logger.info(f"Process removed: '{process_id}'.")

    def find(self, process_id: str) -> Process | None:
        """Return the catalog entry for a process id, if registered.

        Args:
            process_id: The id of the process to find.

        Returns:
            The Process, or None if not registered.
        """
        with self._lock:
            return self._processes.get(process_id)

    def list_all(self) -> list[Process]:
        """Return every registered process, ordered by id.

        Returns:
            A list of Process entries sorted by id.
        """
        with self._lock:
            return sorted(self._processes.values(), key=lambda process: process.id)

    def is_registered(self, process_id: str) -> bool:
        """Return whether a process id is currently registered.

        Args:
            process_id: The id to check.

        Returns:
            True if a process with this id exists in the catalog.
        """
        with self._lock:
            return process_id in self._processes
