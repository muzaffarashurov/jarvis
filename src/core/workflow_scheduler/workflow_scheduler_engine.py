"""WorkflowSchedulerEngine: EP-034 automatic Workflow Engine run trigger.

Architecture (mirroring EP-011's task brief for `Scheduler`):

    WorkflowSchedulerService -> WorkflowSchedulerEngine -> ScheduledWorkflowRegistry -> WorkflowEngine

WorkflowSchedulerEngine contains no business logic of its own. It only
decides *when* a scheduled workflow should run (`calculate_next_run`)
and *that* it should run (`run_now`), which always delegates the
actual run to the shared, unmodified EP-033 `WorkflowEngine`, through
its public `run(workflow_id)` method only -- never `PlanningEngine` or
`PlanExecutionEngine` directly (mirrored from EP-033's own restraint
of never reaching past its immediately-prior EP). A `ScheduledWorkflow`'s
`workflow_id` is an opaque id handed to `WorkflowEngine.run()`
unchanged -- this engine never inspects or decomposes the referenced
`WorkflowDefinition` itself.

`calculate_next_run`'s date-math intentionally reimplements EP-011's
`Scheduler.calculate_next_run` rather than calling it: `Schedule`/
`ScheduleType` are reused unchanged (see scheduled_workflow.py), but
`Scheduler.calculate_next_run` is typed to and reads fields from `Job`
specifically -- duck-typing a `ScheduledWorkflow` into it would create
undocumented, fragile coupling to a completed EP's internal
assumptions with no formal contract keeping the two types
duck-type-compatible over time. This ~80-line switch is small,
self-contained, and independently tested; it is not a redesign of
EP-011, which remains completely untouched.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock

from loguru import logger

from src.core.scheduler.job import JobStatus, Schedule, ScheduleType
from src.core.workflow_engine.workflow_engine import WorkflowEngine
from src.core.workflow_engine.workflow_run_provider import WorkflowEngineError
from src.core.workflow_scheduler.scheduled_workflow import ScheduledWorkflow
from src.core.workflow_scheduler.scheduled_workflow_registry import ScheduledWorkflowRegistry

__all__ = ["WorkflowSchedulerEngine", "WorkflowSchedulerError"]


class WorkflowSchedulerError(Exception):
    """Raised for invalid workflow-scheduler operations.

    Covers the same cases as EP-011's `SchedulerError`: unknown entry,
    duplicate entry, and invalid schedule. ("Workflow Scheduler
    stopped" is reported by WorkflowSchedulerService, the layer that
    owns configuration; a failed run is reported via
    `ScheduledWorkflow.status` rather than raised, matching
    `Scheduler.run_job`'s convention.)
    """


class WorkflowSchedulerEngine:
    """Central engine responsible for running scheduled workflows automatically.

    Responsibilities (mirroring EP-011's `Scheduler`): register_entry,
    remove_entry, start_entry, stop_entry, run_now, list_entries,
    calculate_next_run. `tick()` is the automatic-execution entry
    point driven by WorkflowSchedulerService's background loop
    ('workflow_scheduler.tick_interval' in config/config.yaml).
    """

    def __init__(self, registry: ScheduledWorkflowRegistry, workflow_engine: WorkflowEngine) -> None:
        """Initialize the WorkflowSchedulerEngine.

        Args:
            registry: Storage for all known ScheduledWorkflow objects.
            workflow_engine: The EP-033 WorkflowEngine used to actually
                run a scheduled entry's referenced workflow definition,
                through its public `run()` method only.
        """
        self._registry = registry
        self._workflow_engine = workflow_engine
        self._lock = Lock()

    # ---------- Public API ----------

    def register_entry(self, entry: ScheduledWorkflow) -> None:
        """Register a new scheduled workflow.

        Args:
            entry: The ScheduledWorkflow to register.

        Raises:
            WorkflowSchedulerError: If an entry with the same id is
                already registered.
        """
        try:
            self._registry.register(entry)
        except ValueError as exc:
            raise WorkflowSchedulerError(str(exc)) from exc
        logger.info(f"Scheduled workflow registered: '{entry.id}'.")

    def remove_entry(self, entry_id: str) -> None:
        """Remove a registered scheduled workflow.

        Args:
            entry_id: The id of the entry to remove.

        Raises:
            WorkflowSchedulerError: If no entry with that id is registered.
        """
        try:
            self._registry.unregister(entry_id)
        except KeyError as exc:
            raise WorkflowSchedulerError(f"Unknown scheduled workflow: '{entry_id}'.") from exc
        logger.info(f"Scheduled workflow removed: '{entry_id}'.")

    def start_entry(self, entry_id: str) -> ScheduledWorkflow:
        """Enable scheduled execution for an entry.

        Args:
            entry_id: The id of the entry to enable.

        Returns:
            The updated ScheduledWorkflow.

        Raises:
            WorkflowSchedulerError: If the entry is unknown, or its
                schedule is invalid.
        """
        entry = self._require_entry(entry_id)
        next_run = self.calculate_next_run(entry)
        with self._lock:
            entry.enabled = True
            if entry.status == JobStatus.DISABLED:
                entry.status = JobStatus.IDLE
            entry.next_run = next_run
        logger.info(f"Scheduled workflow started: '{entry_id}'.")
        return entry

    def stop_entry(self, entry_id: str) -> ScheduledWorkflow:
        """Disable scheduled execution for an entry.

        Args:
            entry_id: The id of the entry to disable.

        Returns:
            The updated ScheduledWorkflow.

        Raises:
            WorkflowSchedulerError: If the entry is unknown.
        """
        entry = self._require_entry(entry_id)
        with self._lock:
            entry.enabled = False
            entry.next_run = None
            entry.status = JobStatus.DISABLED
        logger.info(f"Scheduled workflow stopped: '{entry_id}'.")
        return entry

    def run_now(self, entry_id: str) -> ScheduledWorkflow:
        """Run a scheduled entry's referenced workflow immediately.

        Args:
            entry_id: The id of the entry to run.

        Returns:
            The updated ScheduledWorkflow, reflecting the run's outcome.

        Raises:
            WorkflowSchedulerError: If the entry is unknown.
        """
        entry = self._require_entry(entry_id)

        try:
            result = self._workflow_engine.run(entry.workflow_id)
            success = result.success
            message = result.summary()
        except WorkflowEngineError as exc:
            success = False
            message = str(exc)

        with self._lock:
            entry.last_run = datetime.now(timezone.utc)
            entry.status = JobStatus.SUCCESS if success else JobStatus.FAILED

            if success:
                logger.info(f"Scheduled workflow executed: '{entry_id}'.")
            else:
                logger.error(f"Scheduled workflow failed: '{entry_id}' -> {message}")

            if entry.enabled:
                try:
                    entry.next_run = self.calculate_next_run(entry)
                except WorkflowSchedulerError as exc:
                    logger.error(f"Invalid schedule for scheduled workflow '{entry_id}': {exc}")
                    entry.next_run = None

        return entry

    def list_entries(self) -> list[ScheduledWorkflow]:
        """Return all registered scheduled workflows."""
        return self._registry.list()

    def get_entry(self, entry_id: str) -> ScheduledWorkflow | None:
        """Return the entry registered under `entry_id`, or None."""
        return self._registry.get(entry_id)

    def calculate_next_run(self, entry: ScheduledWorkflow) -> datetime | None:
        """Compute an entry's next scheduled run time based on its Schedule.

        Args:
            entry: The ScheduledWorkflow to evaluate.

        Returns:
            The next UTC run time, or None if the entry has no further
            automatic runs (manual schedule, or a "once" schedule that
            has already run).

        Raises:
            WorkflowSchedulerError: If the entry's Schedule is missing
                fields required by its type.
        """
        schedule = entry.schedule

        if schedule.type == ScheduleType.MANUAL:
            return None

        if schedule.type == ScheduleType.ONCE:
            return self._next_once(entry, schedule)

        if schedule.type == ScheduleType.INTERVAL:
            return self._next_interval(entry, schedule)

        if schedule.type == ScheduleType.DAILY:
            return self._next_daily(entry, schedule)

        if schedule.type == ScheduleType.WEEKLY:
            return self._next_weekly(entry, schedule)

        if schedule.type == ScheduleType.CRON:
            # TODO:
            # Cron scheduling remains an interface only, exactly as in
            # EP-011's Scheduler.calculate_next_run -- no cron
            # expression parser exists anywhere in this project.
            return None

        raise WorkflowSchedulerError(
            f"Invalid schedule for scheduled workflow '{entry.id}': unknown type '{schedule.type}'."
        )

    def tick(self) -> list[ScheduledWorkflow]:
        """Run every enabled entry whose next_run has arrived.

        Called periodically by WorkflowSchedulerService's background
        loop (driven by 'workflow_scheduler.tick_interval') to provide
        automatic execution.

        Returns:
            The entries that were run on this tick.
        """
        now = datetime.now(timezone.utc)
        due = [
            entry
            for entry in self._registry.list()
            if entry.enabled and entry.next_run is not None and entry.next_run <= now
        ]

        executed: list[ScheduledWorkflow] = []
        for entry in due:
            try:
                executed.append(self.run_now(entry.id))
            except WorkflowSchedulerError as exc:
                logger.error(f"Scheduled workflow run skipped: {exc}")
        return executed

    # ---------- Internal helpers ----------

    def _require_entry(self, entry_id: str) -> ScheduledWorkflow:
        """Return the entry for `entry_id`, or raise WorkflowSchedulerError if unknown."""
        entry = self._registry.get(entry_id)
        if entry is None:
            raise WorkflowSchedulerError(f"Unknown scheduled workflow: '{entry_id}'.")
        return entry

    @staticmethod
    def _next_once(entry: ScheduledWorkflow, schedule: Schedule) -> datetime | None:
        """Return the "once" schedule's run time, or None once it has run."""
        if entry.last_run is not None:
            return None
        if schedule.run_at is None:
            raise WorkflowSchedulerError(
                f"Invalid schedule for scheduled workflow '{entry.id}': 'once' requires run_at."
            )
        return schedule.run_at

    @staticmethod
    def _next_interval(entry: ScheduledWorkflow, schedule: Schedule) -> datetime:
        """Return the next run time for an "interval" schedule."""
        if not schedule.interval_seconds or schedule.interval_seconds <= 0:
            raise WorkflowSchedulerError(
                f"Invalid schedule for scheduled workflow '{entry.id}': "
                "'interval' requires interval_seconds > 0."
            )
        base = entry.last_run or datetime.now(timezone.utc)
        return base + timedelta(seconds=schedule.interval_seconds)

    @classmethod
    def _next_daily(cls, entry: ScheduledWorkflow, schedule: Schedule) -> datetime:
        """Return the next run time for a "daily" schedule."""
        hour, minute = cls._parse_time_of_day(entry, schedule)
        now = datetime.now(timezone.utc)
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    @classmethod
    def _next_weekly(cls, entry: ScheduledWorkflow, schedule: Schedule) -> datetime:
        """Return the next run time for a "weekly" schedule."""
        if schedule.day_of_week is None or not (0 <= schedule.day_of_week <= 6):
            raise WorkflowSchedulerError(
                f"Invalid schedule for scheduled workflow '{entry.id}': "
                "'weekly' requires day_of_week (0-6)."
            )
        hour, minute = cls._parse_time_of_day(entry, schedule)
        now = datetime.now(timezone.utc)
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        days_ahead = (schedule.day_of_week - candidate.weekday()) % 7
        candidate += timedelta(days=days_ahead)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate

    @staticmethod
    def _parse_time_of_day(entry: ScheduledWorkflow, schedule: Schedule) -> tuple[int, int]:
        """Parse a Schedule's "HH:MM" time_of_day field.

        Raises:
            WorkflowSchedulerError: If time_of_day is missing or malformed.
        """
        if schedule.time_of_day is None:
            raise WorkflowSchedulerError(
                f"Invalid schedule for scheduled workflow '{entry.id}': missing time_of_day."
            )
        try:
            hour_str, minute_str = schedule.time_of_day.split(":")
            hour, minute = int(hour_str), int(minute_str)
        except ValueError as exc:
            raise WorkflowSchedulerError(
                f"Invalid schedule for scheduled workflow '{entry.id}': "
                f"bad time_of_day '{schedule.time_of_day}'."
            ) from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise WorkflowSchedulerError(
                f"Invalid schedule for scheduled workflow '{entry.id}': "
                f"bad time_of_day '{schedule.time_of_day}'."
            )
        return hour, minute
