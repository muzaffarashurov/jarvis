"""Business logic that coordinates EP-034 Workflow Scheduler.

WorkflowSchedulerService implements no scheduling or execution logic
of its own; it depends only on `WorkflowSchedulerEngine`, matching
EP-034's architecture:

    WorkflowSchedulerModule -> WorkflowSchedulerService -> WorkflowSchedulerEngine -> ScheduledWorkflowRegistry -> WorkflowEngine

In addition to the thin CLI-facing wrappers (register/unregister/
start/stop/run_now/status), WorkflowSchedulerService owns the
background tick loop that makes scheduled workflow execution
automatic, driven by 'workflow_scheduler.tick_interval' and started
automatically at construction when 'workflow_scheduler.enabled' and
'workflow_scheduler.auto_start' are true (see config/config.yaml) --
mirroring EP-011's `SchedulerService` exactly, as its own, entirely
separate background thread (no shared state with EP-011's Scheduler).
The loop only ever calls `WorkflowSchedulerEngine.tick()`; it never
calls any business-logic module directly.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.scheduler.job import JobStatus
from src.core.workflow_scheduler.scheduled_workflow import ScheduledWorkflow
from src.core.workflow_scheduler.workflow_scheduler_engine import (
    WorkflowSchedulerEngine,
    WorkflowSchedulerError,
)


@dataclass(frozen=True)
class WorkflowSchedulerStatus:
    """Result of `autoflow status`."""

    running: bool
    entries_registered: int
    entries_enabled: int


class WorkflowSchedulerService:
    """Coordinates WorkflowSchedulerEngine and owns its automatic tick loop.

    Depends only on WorkflowSchedulerEngine (scheduled-workflow
    execution) and Config (its own 'workflow_scheduler.*' settings).
    Implements no business logic of its own.
    """

    def __init__(self, config: Config, engine: WorkflowSchedulerEngine) -> None:
        """Initialize the WorkflowSchedulerService.

        Args:
            config: Loaded application configuration, used to resolve
                'workflow_scheduler.enabled',
                'workflow_scheduler.auto_start', and
                'workflow_scheduler.tick_interval'.
            engine: The WorkflowSchedulerEngine used to register, run,
                and track scheduled workflows.
        """
        self._config = config
        self._engine = engine
        self._tick_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()

        if bool(self._config.get("workflow_scheduler.enabled", True)) and bool(
            self._config.get("workflow_scheduler.auto_start", False)
        ):
            self._start_tick_loop()

    # ---------- Public API ----------

    def register(self, entry: ScheduledWorkflow) -> CommandResult:
        """Register a new scheduled workflow."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            self._engine.register_entry(entry)
        except WorkflowSchedulerError as exc:
            logger.error(f"Scheduled workflow registration failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Scheduled workflow '{entry.id}' registered.")

    def unregister(self, entry_id: str) -> CommandResult:
        """Remove a registered scheduled workflow."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            self._engine.remove_entry(entry_id)
        except WorkflowSchedulerError as exc:
            logger.error(f"Scheduled workflow removal failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Scheduled workflow '{entry_id}' removed.")

    def start(self, entry_id: str) -> CommandResult:
        """Enable scheduled execution for an entry."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        entry = self._engine.get_entry(entry_id)
        if entry is None:
            message = f"Unknown scheduled workflow: '{entry_id}'."
            logger.error(f"Scheduled workflow start failed: {message}")
            return CommandResult(success=False, message=message)

        if entry.enabled:
            return CommandResult(success=True, message="Scheduled workflow already started.")

        try:
            self._engine.start_entry(entry_id)
        except WorkflowSchedulerError as exc:
            logger.error(f"Scheduled workflow start failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Scheduled workflow '{entry_id}' started.")

    def stop(self, entry_id: str) -> CommandResult:
        """Disable scheduled execution for an entry."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        entry = self._engine.get_entry(entry_id)
        if entry is None:
            message = f"Unknown scheduled workflow: '{entry_id}'."
            logger.error(f"Scheduled workflow stop failed: {message}")
            return CommandResult(success=False, message=message)

        if not entry.enabled:
            return CommandResult(success=True, message="Scheduled workflow already stopped.")

        try:
            self._engine.stop_entry(entry_id)
        except WorkflowSchedulerError as exc:
            logger.error(f"Scheduled workflow stop failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Scheduled workflow '{entry_id}' stopped.")

    def run(self, entry_id: str) -> CommandResult:
        """Run a scheduled workflow's referenced workflow immediately."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            entry = self._engine.run_now(entry_id)
        except WorkflowSchedulerError as exc:
            logger.error(f"Scheduled workflow execution failed: {exc}")
            return CommandResult(success=False, message=str(exc))

        if entry.status == JobStatus.FAILED:
            return CommandResult(
                success=False, message=f"Scheduled workflow '{entry_id}' failed to execute."
            )
        return CommandResult(success=True, message=f"Scheduled workflow '{entry_id}' executed.")

    def list_entries(self) -> list[ScheduledWorkflow]:
        """Return all registered scheduled workflows."""
        return self._engine.list_entries()

    def get_entry(self, entry_id: str) -> ScheduledWorkflow | None:
        """Return the scheduled workflow registered under `entry_id`, or None."""
        return self._engine.get_entry(entry_id)

    def status(self) -> WorkflowSchedulerStatus:
        """Return the `autoflow status` snapshot."""
        entries = self._engine.list_entries()
        return WorkflowSchedulerStatus(
            running=self._is_tick_loop_running(),
            entries_registered=len(entries),
            entries_enabled=sum(1 for entry in entries if entry.enabled),
        )

    # ---------- Internal helpers ----------

    def _ensure_enabled(self) -> CommandResult | None:
        """Return a "Workflow Scheduler stopped" failure if scheduling is disabled.

        Returns:
            A failing CommandResult if 'workflow_scheduler.enabled' is
            False, otherwise None (meaning the caller may proceed).
        """
        if bool(self._config.get("workflow_scheduler.enabled", True)):
            return None
        logger.error("Workflow Scheduler operation rejected: Workflow Scheduler stopped.")
        return CommandResult(success=False, message="Workflow Scheduler stopped.")

    def _start_tick_loop(self) -> None:
        """Start the background thread that calls WorkflowSchedulerEngine.tick() periodically."""
        with self._lifecycle_lock:
            if self._tick_thread is not None:
                return
            self._stop_event.clear()
            self._tick_thread = threading.Thread(
                target=self._tick_loop, name="workflow-scheduler-tick", daemon=True
            )
            self._tick_thread.start()
        logger.info("Workflow Scheduler started.")

    def _tick_loop(self) -> None:
        """Repeatedly call WorkflowSchedulerEngine.tick() every 'workflow_scheduler.tick_interval' seconds."""
        interval = float(self._config.get("workflow_scheduler.tick_interval", 5))
        while not self._stop_event.wait(interval):
            try:
                self._engine.tick()
            except Exception as exc:  # noqa: BLE001 - the tick loop must never die silently
                logger.error(f"Workflow Scheduler tick failed: {exc}")
        logger.info("Workflow Scheduler stopped.")

    def _is_tick_loop_running(self) -> bool:
        """Return whether the background tick thread is alive."""
        with self._lifecycle_lock:
            return self._tick_thread is not None and self._tick_thread.is_alive()
