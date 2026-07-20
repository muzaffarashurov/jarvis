"""Business logic that coordinates the Scheduler (EP-011 Task Scheduler).

SchedulerService implements no domain logic of its own and never calls
Telegram/Voice/AI/Browser/CALYPSO/Invoice/FastResponse modules
directly. Per EP-011's architecture, it depends only on:

    SchedulerService -> Scheduler -> JobRegistry -> ExecutionEngine

In addition to the thin CLI-facing wrappers (register/unregister/
start/stop/run/status/doctor), SchedulerService owns the background
tick loop that makes job execution automatic, driven by
'scheduler.tick_interval' and started automatically at construction
when 'scheduler.enabled' and 'scheduler.auto_start' are true (see
config/config.yaml). The loop only ever calls Scheduler.tick(); it
never calls any business-logic module directly.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.scheduler.job import Job, JobStatus
from src.core.scheduler.scheduler import Scheduler, SchedulerError


@dataclass(frozen=True)
class SchedulerStatus:
    """Result of `scheduler status`."""

    running: bool
    jobs_registered: int
    jobs_enabled: int


@dataclass(frozen=True)
class SchedulerDoctorReport:
    """Result of `scheduler doctor`.

    Attributes:
        scheduler_available: Whether the Scheduler dependency is present.
        registry_available: Whether the Scheduler's JobRegistry is present.
        execution_engine_available: Whether the Scheduler's ExecutionEngine
            is present.
        configuration_loaded: Whether 'scheduler.enabled' resolves to a
            boolean in configuration.
        job_state_valid: Whether every registered job reports a
            structurally valid JobStatus.
        next_run_calculable: Whether the next run time can be computed
            for every registered job.
    """

    scheduler_available: bool
    registry_available: bool
    execution_engine_available: bool
    configuration_loaded: bool
    job_state_valid: bool
    next_run_calculable: bool

    @property
    def is_ready(self) -> bool:
        """Return True only if every diagnostic check passed."""
        return (
            self.scheduler_available
            and self.registry_available
            and self.execution_engine_available
            and self.configuration_loaded
            and self.job_state_valid
            and self.next_run_calculable
        )


class SchedulerService:
    """Coordinates the Scheduler and owns its automatic tick loop.

    Depends only on Scheduler (job execution) and Config (its own
    'scheduler.*' settings), matching EP-011's architecture:
    SchedulerModule -> SchedulerService -> Scheduler -> JobRegistry ->
    ExecutionEngine. Implements no business logic of its own.
    """

    def __init__(self, config: Config, scheduler: Scheduler) -> None:
        """Initialize the SchedulerService.

        Args:
            config: Loaded application configuration, used to resolve
                'scheduler.enabled', 'scheduler.auto_start', and
                'scheduler.tick_interval'.
            scheduler: The Scheduler used to register, run, and track jobs.
        """
        self._config = config
        self._scheduler = scheduler
        self._tick_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()

        if bool(self._config.get("scheduler.enabled", True)) and bool(
            self._config.get("scheduler.auto_start", True)
        ):
            self._start_tick_loop()

    # ---------- Public API ----------

    def register(self, job: Job) -> CommandResult:
        """Register a new job."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            self._scheduler.register_job(job)
        except SchedulerError as exc:
            logger.error(f"Job registration failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Job '{job.id}' registered.")

    def unregister(self, job_id: str) -> CommandResult:
        """Remove a registered job."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            self._scheduler.remove_job(job_id)
        except SchedulerError as exc:
            logger.error(f"Job removal failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Job '{job_id}' removed.")

    def start(self, job_id: str) -> CommandResult:
        """Enable scheduled execution for a job."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        job = self._scheduler.get_job(job_id)
        if job is None:
            message = f"Unknown job: '{job_id}'."
            logger.error(f"Job start failed: {message}")
            return CommandResult(success=False, message=message)

        if job.enabled:
            return CommandResult(success=True, message="Job already started.")

        try:
            self._scheduler.start_job(job_id)
        except SchedulerError as exc:
            logger.error(f"Job start failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Job '{job_id}' started.")

    def stop(self, job_id: str) -> CommandResult:
        """Disable scheduled execution for a job."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        job = self._scheduler.get_job(job_id)
        if job is None:
            message = f"Unknown job: '{job_id}'."
            logger.error(f"Job stop failed: {message}")
            return CommandResult(success=False, message=message)

        if not job.enabled:
            return CommandResult(success=True, message="Job already stopped.")

        try:
            self._scheduler.stop_job(job_id)
        except SchedulerError as exc:
            logger.error(f"Job stop failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Job '{job_id}' stopped.")

    def run(self, job_id: str) -> CommandResult:
        """Run a job immediately."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            job = self._scheduler.run_job(job_id)
        except SchedulerError as exc:
            logger.error(f"Job execution failed: {exc}")
            return CommandResult(success=False, message=str(exc))

        if job.status == JobStatus.FAILED:
            return CommandResult(success=False, message=f"Job '{job_id}' failed to execute.")
        return CommandResult(success=True, message=f"Job '{job_id}' executed.")

    def list_jobs(self) -> list[Job]:
        """Return all registered jobs."""
        return self._scheduler.list_jobs()

    def get_job(self, job_id: str) -> Job | None:
        """Return the job registered under `job_id`, or None."""
        return self._scheduler.get_job(job_id)

    def status(self) -> SchedulerStatus:
        """Return the `scheduler status` snapshot."""
        jobs = self._scheduler.list_jobs()
        return SchedulerStatus(
            running=self._is_tick_loop_running(),
            jobs_registered=len(jobs),
            jobs_enabled=sum(1 for job in jobs if job.enabled),
        )

    def doctor(self) -> SchedulerDoctorReport:
        """Run the `scheduler doctor` diagnostic checks."""
        diagnostics = self._scheduler.diagnostics()
        return SchedulerDoctorReport(
            scheduler_available=self._scheduler is not None,
            registry_available=diagnostics.registry_available,
            execution_engine_available=diagnostics.execution_engine_available,
            configuration_loaded=isinstance(self._config.get("scheduler.enabled"), bool),
            job_state_valid=diagnostics.job_state_valid,
            next_run_calculable=diagnostics.next_run_calculable,
        )

    # ---------- Internal helpers ----------

    def _ensure_enabled(self) -> CommandResult | None:
        """Return a "Scheduler stopped" failure if scheduling is disabled.

        Returns:
            A failing CommandResult if 'scheduler.enabled' is False,
            otherwise None (meaning the caller may proceed).
        """
        if bool(self._config.get("scheduler.enabled", True)):
            return None
        logger.error("Scheduler operation rejected: Scheduler stopped.")
        return CommandResult(success=False, message="Scheduler stopped.")

    def _start_tick_loop(self) -> None:
        """Start the background thread that calls Scheduler.tick() periodically."""
        with self._lifecycle_lock:
            if self._tick_thread is not None:
                return
            self._stop_event.clear()
            self._tick_thread = threading.Thread(
                target=self._tick_loop, name="scheduler-tick", daemon=True
            )
            self._tick_thread.start()
        logger.info("Scheduler started.")

    def _tick_loop(self) -> None:
        """Repeatedly call Scheduler.tick() every 'scheduler.tick_interval' seconds."""
        interval = float(self._config.get("scheduler.tick_interval", 1))
        while not self._stop_event.wait(interval):
            try:
                self._scheduler.tick()
            except Exception as exc:  # noqa: BLE001 - the tick loop must never die silently
                logger.error(f"Scheduler tick failed: {exc}")
        logger.info("Scheduler stopped.")

    def _is_tick_loop_running(self) -> bool:
        """Return whether the background tick thread is alive."""
        with self._lifecycle_lock:
            return self._tick_thread is not None and self._tick_thread.is_alive()
