"""In-memory registry of ScheduledWorkflow objects, for EP-034 Workflow Scheduler.

ScheduledWorkflowRegistry only stores and retrieves ScheduledWorkflow
objects; it performs no scheduling or execution logic. Mirrors EP-011's
`JobRegistry`'s storage-only role and thread-safety pattern
(`src/core/scheduler/job_registry.py`) exactly, since ScheduledWorkflow
objects are mutated in place both by the CLI thread and by
WorkflowSchedulerService's background tick loop -- deliberately a new,
separate registry rather than reusing `JobRegistry` itself, since
`JobRegistry` is typed to `Job`, not `ScheduledWorkflow` (see
src/core/workflow_scheduler/__init__.py for the full naming-collision
note).
"""

from __future__ import annotations

from threading import Lock

from src.core.workflow_scheduler.scheduled_workflow import ScheduledWorkflow

__all__ = ["ScheduledWorkflowRegistry"]


class ScheduledWorkflowRegistry:
    """Thread-safe, in-memory store of registered ScheduledWorkflow objects, keyed by id."""

    def __init__(self) -> None:
        """Initialize an empty ScheduledWorkflowRegistry."""
        self._entries: dict[str, ScheduledWorkflow] = {}
        self._lock = Lock()

    def register(self, entry: ScheduledWorkflow) -> None:
        """Register a scheduled workflow.

        Args:
            entry: The ScheduledWorkflow to register.

        Raises:
            ValueError: If an entry with the same id is already registered.
        """
        with self._lock:
            if entry.id in self._entries:
                raise ValueError(f"Scheduled workflow already registered: {entry.id}")
            self._entries[entry.id] = entry

    def unregister(self, entry_id: str) -> None:
        """Remove a registered scheduled workflow.

        Args:
            entry_id: The id of the entry to remove.

        Raises:
            KeyError: If no entry with that id is registered.
        """
        with self._lock:
            del self._entries[entry_id]

    def get(self, entry_id: str) -> ScheduledWorkflow | None:
        """Return the entry registered under `entry_id`.

        Args:
            entry_id: The id to look up.

        Returns:
            The registered ScheduledWorkflow, or None if no such id is registered.
        """
        with self._lock:
            return self._entries.get(entry_id)

    def list(self) -> list[ScheduledWorkflow]:
        """Return all registered scheduled workflows.

        Returns:
            A list of every currently registered ScheduledWorkflow.
        """
        with self._lock:
            return list(self._entries.values())
