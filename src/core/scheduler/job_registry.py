"""In-memory registry of Job objects.

JobRegistry only stores and retrieves Job objects; it performs no
scheduling or execution logic. Mirrors WorkflowRegistry's storage-only
role for WorkflowService (see src/core/workflows/workflow_registry.py)
and adopts ProcessRegistry's thread-safety pattern (see
src/core/execution/process_registry.py), since Job objects are
mutated in place both by the CLI thread and by the Scheduler's
background tick loop.
"""

from __future__ import annotations

from threading import Lock

from src.core.scheduler.job import Job


class JobRegistry:
    """Thread-safe, in-memory store of registered Job objects, keyed by id."""

    def __init__(self) -> None:
        """Initialize an empty JobRegistry."""
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()

    def register(self, job: Job) -> None:
        """Register a job.

        Args:
            job: The Job to register.

        Raises:
            ValueError: If a job with the same id is already registered.
        """
        with self._lock:
            if job.id in self._jobs:
                raise ValueError(f"Job already registered: {job.id}")
            self._jobs[job.id] = job

    def unregister(self, job_id: str) -> None:
        """Remove a registered job.

        Args:
            job_id: The id of the job to remove.

        Raises:
            KeyError: If no job with that id is registered.
        """
        with self._lock:
            del self._jobs[job_id]

    def get(self, job_id: str) -> Job | None:
        """Return the job registered under `job_id`.

        Args:
            job_id: The id to look up.

        Returns:
            The registered Job, or None if no such id is registered.
        """
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        """Return all registered jobs.

        Returns:
            A list of every currently registered Job.
        """
        with self._lock:
            return list(self._jobs.values())
