"""Scheduler: EP-011 central automatic job execution service.

Architecture (per EP-011's task brief):

    SchedulerService -> Scheduler -> JobRegistry -> ExecutionEngine

The Scheduler contains no business logic. It only decides *when* a job
should run (calculate_next_run) and *that* it should run (run_job),
which always delegates the actual execution to the shared, unmodified
ExecutionEngine (see AI_GENERATION_STANDARD.md's Existing Code
Policy). A Job's `command` is a raw target string handed to
ExecutionEngine.run() unchanged -- exactly the same contract every
other existing caller (InvoiceService, FastResponseService,
WorkflowService) already uses. The Scheduler knows nothing about
Telegram, Voice, AI, Browser, CALYPSO, Invoice, or Fast Response
Board implementations, per EP-011's Important Design Rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock

from loguru import logger

from src.core.execution.engine import ExecutionEngine
from src.core.scheduler.job import Job, JobStatus, Schedule, ScheduleType
from src.core.scheduler.job_registry import JobRegistry


class SchedulerError(Exception):
    """Raised for invalid scheduler operations.

    Covers EP-011's Error Handling cases: unknown job, duplicate job,
    and invalid schedule. ("Scheduler stopped" is reported by
    SchedulerService, the layer that owns configuration; "Execution
    failed" is reported via Job.status / ExecutionResult rather than
    raised, matching WorkflowService.run_workflow's convention.)
    """


@dataclass(frozen=True)
class SchedulerDiagnostics:
    """Low-level diagnostic facts about the Scheduler's own dependencies.

    Used by SchedulerService.doctor() to report on the Registry,
    ExecutionEngine, Job State, and Next Run checks required by
    `scheduler doctor`, without SchedulerService reaching past its
    direct dependency (the Scheduler) into JobRegistry or
    ExecutionEngine directly.

    Attributes:
        registry_available: Whether the JobRegistry dependency is present.
        execution_engine_available: Whether the ExecutionEngine
            dependency is present.
        jobs_registered: Number of jobs currently in the registry.
        job_state_valid: Whether every registered job reports a
            structurally valid JobStatus.
        next_run_calculable: Whether `calculate_next_run` succeeds
            (without raising SchedulerError) for every registered job.
    """

    registry_available: bool
    execution_engine_available: bool
    jobs_registered: int
    job_state_valid: bool
    next_run_calculable: bool


class Scheduler:
    """Central service responsible for executing jobs automatically.

    Responsibilities (per EP-011's task brief): register_job,
    remove_job, start_job, stop_job, run_job, list_jobs,
    calculate_next_run. `tick()` is the automatic-execution entry
    point driven by SchedulerService's background loop
    ('scheduler.tick_interval' in config/config.yaml).
    """

    def __init__(self, registry: JobRegistry, execution_engine: ExecutionEngine) -> None:
        """Initialize the Scheduler.

        Args:
            registry: Storage for all known Job objects.
            execution_engine: Shared engine used to execute job commands.
        """
        self._registry = registry
        self._execution_engine = execution_engine
        self._lock = Lock()

    # ---------- Public API ----------

    def register_job(self, job: Job) -> None:
        """Register a new job with the scheduler.

        Args:
            job: The Job to register.

        Raises:
            SchedulerError: If a job with the same id is already registered.
        """
        try:
            self._registry.register(job)
        except ValueError as exc:
            raise SchedulerError(str(exc)) from exc
        logger.info(f"Job registered: '{job.id}'.")

    def remove_job(self, job_id: str) -> None:
        """Remove a registered job.

        Args:
            job_id: The id of the job to remove.

        Raises:
            SchedulerError: If no job with that id is registered.
        """
        try:
            self._registry.unregister(job_id)
        except KeyError as exc:
            raise SchedulerError(f"Unknown job: '{job_id}'.") from exc
        logger.info(f"Job removed: '{job_id}'.")

    def start_job(self, job_id: str) -> Job:
        """Enable scheduled execution for a job.

        Args:
            job_id: The id of the job to enable.

        Returns:
            The updated Job.

        Raises:
            SchedulerError: If the job is unknown, or its schedule is invalid.
        """
        job = self._require_job(job_id)
        next_run = self.calculate_next_run(job)
        with self._lock:
            job.enabled = True
            if job.status == JobStatus.DISABLED:
                job.status = JobStatus.IDLE
            job.next_run = next_run
        logger.info(f"Job started: '{job_id}'.")
        return job

    def stop_job(self, job_id: str) -> Job:
        """Disable scheduled execution for a job.

        Args:
            job_id: The id of the job to disable.

        Returns:
            The updated Job.

        Raises:
            SchedulerError: If the job is unknown.
        """
        job = self._require_job(job_id)
        with self._lock:
            job.enabled = False
            job.next_run = None
            job.status = JobStatus.DISABLED
        logger.info(f"Job stopped: '{job_id}'.")
        return job

    def run_job(self, job_id: str) -> Job:
        """Execute a job immediately via the ExecutionEngine.

        Args:
            job_id: The id of the job to run.

        Returns:
            The updated Job, reflecting the execution outcome.

        Raises:
            SchedulerError: If the job is unknown.
        """
        job = self._require_job(job_id)
        result = self._execution_engine.run(job.command)

        with self._lock:
            job.last_run = datetime.now(timezone.utc)
            job.status = JobStatus.SUCCESS if result.success else JobStatus.FAILED

            if result.success:
                logger.info(f"Job executed: '{job_id}'.")
            else:
                logger.error(f"Job failed: '{job_id}' -> {result.message}")

            if job.enabled:
                try:
                    job.next_run = self.calculate_next_run(job)
                except SchedulerError as exc:
                    logger.error(f"Invalid schedule for job '{job_id}': {exc}")
                    job.next_run = None

        return job

    def list_jobs(self) -> list[Job]:
        """Return all registered jobs."""
        return self._registry.list()

    def get_job(self, job_id: str) -> Job | None:
        """Return the job registered under `job_id`, or None."""
        return self._registry.get(job_id)

    def calculate_next_run(self, job: Job) -> datetime | None:
        """Compute a job's next scheduled run time based on its Schedule.

        Args:
            job: The Job to evaluate.

        Returns:
            The next UTC run time, or None if the job has no further
            automatic runs (manual schedule, or a "once" schedule
            that has already run).

        Raises:
            SchedulerError: If the job's Schedule is missing fields
                required by its type.
        """
        schedule = job.schedule

        if schedule.type == ScheduleType.MANUAL:
            return None

        if schedule.type == ScheduleType.ONCE:
            return self._next_once(job, schedule)

        if schedule.type == ScheduleType.INTERVAL:
            return self._next_interval(job, schedule)

        if schedule.type == ScheduleType.DAILY:
            return self._next_daily(job, schedule)

        if schedule.type == ScheduleType.WEEKLY:
            return self._next_weekly(job, schedule)

        if schedule.type == ScheduleType.CRON:
            # TODO:
            # Cron scheduling is prepared as an interface only (per
            # EP-011's task brief: "cron (prepare interface only, TODO
            # implementation)"). No cron expression parser exists
            # anywhere in this project, so next_run cannot be computed
            # here without inventing one.
            return None

        raise SchedulerError(f"Invalid schedule for job '{job.id}': unknown type '{schedule.type}'.")

    def tick(self) -> list[Job]:
        """Execute every enabled job whose next_run has arrived.

        Called periodically by SchedulerService's background loop
        (driven by 'scheduler.tick_interval') to provide automatic
        execution.

        Returns:
            The jobs that were executed on this tick.
        """
        now = datetime.now(timezone.utc)
        due = [
            job
            for job in self._registry.list()
            if job.enabled and job.next_run is not None and job.next_run <= now
        ]

        executed: list[Job] = []
        for job in due:
            try:
                executed.append(self.run_job(job.id))
            except SchedulerError as exc:
                logger.error(f"Scheduled execution skipped: {exc}")
        return executed

    def diagnostics(self) -> SchedulerDiagnostics:
        """Return diagnostic facts used by `scheduler doctor`."""
        jobs = self._registry.list()
        return SchedulerDiagnostics(
            registry_available=self._registry is not None,
            execution_engine_available=self._execution_engine is not None,
            jobs_registered=len(jobs),
            job_state_valid=self._check_job_state(jobs),
            next_run_calculable=self._check_next_run(jobs),
        )

    # ---------- Internal helpers ----------

    @staticmethod
    def _check_job_state(jobs: list[Job]) -> bool:
        """Return whether every job reports a structurally valid JobStatus.

        Args:
            jobs: The jobs to check.

        Returns:
            True if every job's `status` is a JobStatus member.
        """
        return all(isinstance(job.status, JobStatus) for job in jobs)

    def _check_next_run(self, jobs: list[Job]) -> bool:
        """Return whether `calculate_next_run` succeeds for every job.

        Args:
            jobs: The jobs to check.

        Returns:
            True if `calculate_next_run` does not raise SchedulerError
            for any registered job.
        """
        for job in jobs:
            try:
                self.calculate_next_run(job)
            except SchedulerError:
                return False
        return True

    def _require_job(self, job_id: str) -> Job:
        """Return the job for `job_id`, or raise SchedulerError if unknown."""
        job = self._registry.get(job_id)
        if job is None:
            raise SchedulerError(f"Unknown job: '{job_id}'.")
        return job

    @staticmethod
    def _next_once(job: Job, schedule: Schedule) -> datetime | None:
        """Return the "once" schedule's run time, or None once it has run."""
        if job.last_run is not None:
            return None
        if schedule.run_at is None:
            raise SchedulerError(f"Invalid schedule for job '{job.id}': 'once' requires run_at.")
        return schedule.run_at

    @staticmethod
    def _next_interval(job: Job, schedule: Schedule) -> datetime:
        """Return the next run time for an "interval" schedule."""
        if not schedule.interval_seconds or schedule.interval_seconds <= 0:
            raise SchedulerError(
                f"Invalid schedule for job '{job.id}': 'interval' requires interval_seconds > 0."
            )
        base = job.last_run or datetime.now(timezone.utc)
        return base + timedelta(seconds=schedule.interval_seconds)

    @classmethod
    def _next_daily(cls, job: Job, schedule: Schedule) -> datetime:
        """Return the next run time for a "daily" schedule."""
        hour, minute = cls._parse_time_of_day(job, schedule)
        now = datetime.now(timezone.utc)
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    @classmethod
    def _next_weekly(cls, job: Job, schedule: Schedule) -> datetime:
        """Return the next run time for a "weekly" schedule."""
        if schedule.day_of_week is None or not (0 <= schedule.day_of_week <= 6):
            raise SchedulerError(
                f"Invalid schedule for job '{job.id}': 'weekly' requires day_of_week (0-6)."
            )
        hour, minute = cls._parse_time_of_day(job, schedule)
        now = datetime.now(timezone.utc)
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        days_ahead = (schedule.day_of_week - candidate.weekday()) % 7
        candidate += timedelta(days=days_ahead)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate

    @staticmethod
    def _parse_time_of_day(job: Job, schedule: Schedule) -> tuple[int, int]:
        """Parse a Schedule's "HH:MM" time_of_day field.

        Raises:
            SchedulerError: If time_of_day is missing or malformed.
        """
        if schedule.time_of_day is None:
            raise SchedulerError(f"Invalid schedule for job '{job.id}': missing time_of_day.")
        try:
            hour_str, minute_str = schedule.time_of_day.split(":")
            hour, minute = int(hour_str), int(minute_str)
        except ValueError as exc:
            raise SchedulerError(
                f"Invalid schedule for job '{job.id}': bad time_of_day '{schedule.time_of_day}'."
            ) from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise SchedulerError(
                f"Invalid schedule for job '{job.id}': bad time_of_day '{schedule.time_of_day}'."
            )
        return hour, minute
