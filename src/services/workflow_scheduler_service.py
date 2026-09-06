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

Per EP-063 (`EP063_DESIGN.md` Section 1) this class originally
exposed no public counterpart to `_start_tick_loop()` at all -- unlike
EP-011's `Scheduler`, which EP-061 already closed this same gap for.
EP-063 closes it here with one new, additive public method,
`shutdown()`, that stops the tick loop using the already-existing
`_stop_event`/`_tick_thread` mechanism. No other public method's
signature or behavior changes. Unlike `SchedulerService.shutdown()`
(whose join timeout is a fixed constant, since `Scheduler.tick()`
never blocks), this class's `shutdown()` resolves its default timeout
from 'workflow_scheduler.shutdown_timeout' configuration, mirroring
`BackgroundWorkerService.shutdown()`'s own
'background_workers.shutdown_timeout' -- because
`WorkflowSchedulerEngine.tick()` can itself block for as long as a
scheduled workflow's `WorkflowEngine.run()` call takes
(`EP063_DESIGN.md` Section 2.2, Owner Decision D3). `shutdown()` is
invoked exclusively by `RuntimeService.shutdown()` (EP-060/EP-063) --
it is never exposed as a `WorkflowSchedulerModule` CLI/REST action
(EP-063 Owner Decision D1); see `workflow_scheduler_module.py`.
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

_DEFAULT_SHUTDOWN_TIMEOUT = 10.0


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

        Raises:
            WorkflowSchedulerError: If 'workflow_scheduler.shutdown_timeout'
                is present but not a positive number (EP-063). Reuses
                this module's existing error type, rather than
                introducing a new one, so `Bootstrap`'s existing
                `except WorkflowSchedulerError` handling around this
                class's construction already covers it unchanged.
        """
        self._config = config
        self._engine = engine
        self._tick_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()
        self._shutdown_timeout = self._resolve_shutdown_timeout()

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

    def shutdown(self, wait: bool = True, timeout: float | None = None) -> bool:
        """Stop the background tick loop, if one is running.

        Safe to call regardless of whether the tick loop was ever
        started (e.g. 'workflow_scheduler.auto_start: false', or
        already stopped) -- reports success immediately since there is
        nothing to stop. Does not affect any registered entry's
        enabled/disabled state, and does not prevent `run(entry_id)`
        from being called manually afterward -- only the automatic
        tick loop is stopped.

        This is the EP-063 counterpart to `_start_tick_loop()`; unlike
        that method, this one is public, matching
        `SchedulerService.shutdown()`'s (EP-061) and
        `BackgroundWorkerService.shutdown()`'s (EP-036) naming/shape.
        It is invoked internally by `RuntimeService.shutdown()` and is
        not exposed as a `WorkflowSchedulerModule` CLI/REST action
        (EP-063 Owner Decision D1).

        Unlike `SchedulerService.shutdown()`, this method's default
        timeout is read from 'workflow_scheduler.shutdown_timeout'
        configuration, not a fixed constant -- because
        `WorkflowSchedulerEngine.tick()` can itself block for as long
        as a scheduled workflow's `WorkflowEngine.run()` call takes,
        unlike `Scheduler.tick()`'s non-blocking dispatch
        (`EP063_DESIGN.md` Section 2.2, Owner Decision D3). A tick
        genuinely in progress when this is called is not interrupted
        -- this method can only wait for it to finish naturally, up to
        `timeout`.

        Args:
            wait: If True (default), block until the tick thread has
                exited or `timeout` elapses. If False, signal the stop
                and return immediately without joining.
            timeout: Maximum seconds to wait when `wait` is True.
                Defaults to this service's resolved
                `_shutdown_timeout` (see `_resolve_shutdown_timeout`)
                when not given explicitly.

        Returns:
            True if the tick loop is confirmed not running after this
            call (including if it was never running to begin with);
            False if `wait=True` and the thread did not exit within
            `timeout` (e.g. a scheduled workflow run was still in
            progress).
        """
        with self._lifecycle_lock:
            thread = self._tick_thread
            if thread is None:
                return True
            self._stop_event.set()

        if not wait:
            return not thread.is_alive()

        resolved_timeout = timeout if timeout is not None else self._shutdown_timeout
        thread.join(timeout=resolved_timeout)
        stopped = not thread.is_alive()
        if stopped:
            with self._lifecycle_lock:
                if self._tick_thread is thread:
                    self._tick_thread = None
        return stopped

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

    def _resolve_shutdown_timeout(self) -> float:
        """Resolve and validate 'workflow_scheduler.shutdown_timeout'.

        Returns:
            The configured shutdown timeout in seconds (default
            `_DEFAULT_SHUTDOWN_TIMEOUT`).

        Raises:
            WorkflowSchedulerError: If the configured value is not a
                positive number.
        """
        value = self._config.get(
            "workflow_scheduler.shutdown_timeout", _DEFAULT_SHUTDOWN_TIMEOUT
        )
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise WorkflowSchedulerError(
                "Invalid value for 'workflow_scheduler.shutdown_timeout': expected a "
                f"positive number, got {value!r}."
            )
        return float(value)

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
