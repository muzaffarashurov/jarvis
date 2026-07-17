"""Business logic for orchestrating the external Invoice Automation script.

InvoiceService never touches operating-system processes directly. Every
launch, stop, and liveness check is delegated to the shared
ExecutionEngine, exactly as required for EP-005 ("InvoiceService must
never directly manipulate processes"). This module only decides *what*
to run and *how* to interpret the engine's answers; it owns no
subprocess or ProcessRegistry reference at all.

start()/stop()/restart() return the project's existing CommandResult
type (src.core.command_router.CommandResult) instead of an ad-hoc
tuple, so every layer of Jarvis shares one outcome type rather than
each service inventing its own.

Single Source of Truth: whether the tracked process is currently alive
is never cached here — it is asked of ExecutionEngine.list_processes()
on every call. The only thing this service stores locally is:

  - `_process_id`: the identifier ExecutionEngine.run() handed back for
    *this* launch. ExecutionEngine tracks many unrelated processes
    (e.g. ones started via "system run"); nothing in the existing
    architecture labels a tracked process as "the invoice one", so this
    reference is unavoidable bookkeeping, not a duplicate of process
    state ExecutionEngine already owns.
  - `_started_at`: the local timestamp of this service's own launch
    action, stored as a timezone-aware UTC datetime (not naive local
    time) so it stays valid if this value is ever persisted or read by
    a future History/Scheduler/Analytics component. No existing
    component tracks process start times, so this is not a duplicate
    of anything.
  - `_last_start_failed`: whether the most recent start() attempt was
    rejected by ExecutionEngine. This is InvoiceService's own concern;
    no other component tracks "did the last invoice launch attempt
    fail".

ExecutionEngine does not expose OS-level exit codes or a reason a
process is no longer tracked (see TODO in `status()` below), so this
service deliberately does not guess whether a process that disappeared
from list_processes() crashed or exited cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from loguru import logger  # module-level logger, matching every other Jarvis component

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.execution.engine import ExecutionEngine


class InvoiceStatus(str, Enum):
    """Lifecycle states of the invoice automation process."""

    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class InvoiceConfigurationError(Exception):
    """Raised when 'invoice.script' is missing or invalid in config.yaml."""


@dataclass(frozen=True)
class InvoiceInfo:
    """Snapshot of the invoice automation process for display purposes.

    Attributes:
        script_path: Resolved path to the automation script, or None if
            'invoice.script' is not configured (or misconfigured).
        status: The current InvoiceStatus.
        process_id: The Jarvis-assigned tracking ID returned by
            ExecutionEngine, or None if nothing has been launched.
        started_at: When the currently tracked process was launched
            (timezone-aware, UTC), or None if nothing is currently
            tracked.
    """

    script_path: Path | None
    status: InvoiceStatus
    process_id: int | None
    started_at: datetime | None


class InvoiceService:
    """Orchestrates the existing external Invoice Automation script.

    Responsibilities:
        - Resolve and validate the script path from configuration.
        - Start / stop / restart the script exclusively through the
          shared ExecutionEngine.
        - Track the minimal Jarvis-side bookkeeping (which process id
          belongs to the invoice launch, when it was launched, and
          whether the last launch attempt failed) that no other
          existing component owns.

    Running/alive state itself is never cached: every status() call
    re-asks ExecutionEngine.list_processes() rather than trusting a
    locally stored flag, per the project's Single Source of Truth rule.

    The automation script itself is never modified or replaced: Jarvis
    only launches, tracks, and stops the existing external program.
    """

    def __init__(self, config: Config, execution_engine: ExecutionEngine) -> None:
        """Initialize the InvoiceService.

        Args:
            config: Loaded application configuration, used to resolve
                'invoice.script'.
            execution_engine: The shared engine used to launch, stop,
                and list Jarvis-tracked processes.
        """
        self._config = config
        self._execution_engine = execution_engine
        self._process_id: int | None = None
        self._started_at: datetime | None = None
        self._last_start_failed: bool = False

    # ---------- Public API ----------

    def get_script_path(self) -> Path:
        """Resolve the configured invoice automation script path.

        Returns:
            The configured script path (not guaranteed to exist on disk;
            callers that need to launch it must check separately).

        Raises:
            InvoiceConfigurationError: If 'invoice.script' is missing,
                blank, or not configured as a string.
        """
        raw_path = self._config.get("invoice.script")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise InvoiceConfigurationError(
                "Missing or invalid 'invoice.script' entry in config/config.yaml."
            )
        return Path(raw_path.strip())

    def status(self) -> InvoiceStatus:
        """Return the current lifecycle status of the invoice automation.

        Returns:
            RUNNING if a launched process id is still tracked as alive
            by ExecutionEngine; FAILED if the most recent start()
            attempt was rejected by ExecutionEngine; UNKNOWN if
            configuration cannot be resolved; STOPPED otherwise
            (including a previously tracked process that is no longer
            alive -- see the TODO below).
        """
        try:
            self.get_script_path()
        except InvoiceConfigurationError:
            return InvoiceStatus.UNKNOWN

        if self._process_id is not None:
            if self._is_tracked_process_alive():
                return InvoiceStatus.RUNNING

            # TODO:
            # ExecutionEngine does not expose OS-level exit codes or a
            # reason a tracked process is no longer running, so we
            # cannot tell a clean exit from a crash here. Once such a
            # method exists, use it to distinguish STOPPED from FAILED
            # for a process that ended without an explicit stop() call.
            logger.info("Invoice automation process is no longer tracked as running.")
            self._process_id = None
            self._started_at = None
            return InvoiceStatus.STOPPED

        return InvoiceStatus.FAILED if self._last_start_failed else InvoiceStatus.STOPPED

    def start(self) -> CommandResult:
        """Start the invoice automation script through the ExecutionEngine.

        Returns:
            A CommandResult with a friendly, user-facing message
            describing the outcome.
        """
        if self.status() == InvoiceStatus.RUNNING:
            return CommandResult(success=False, message="Invoice automation is already running.")

        try:
            script_path = self.get_script_path()
        except InvoiceConfigurationError as exc:
            logger.error(f"Invoice automation failed: {exc}")
            self._last_start_failed = True
            return CommandResult(success=False, message=str(exc))

        if not script_path.is_file():
            message = f"Invoice automation script not found: {script_path}"
            logger.error(f"Invoice automation failed: {message}")
            self._last_start_failed = True
            return CommandResult(success=False, message=message)

        result = self._execution_engine.run(str(script_path))
        if not result.success or result.process_id is None:
            self._last_start_failed = True
            logger.error(f"Invoice automation failed: {result.message}")
            return CommandResult(
                success=False, message=f"Could not start invoice automation: {result.message}"
            )

        self._process_id = result.process_id
        self._started_at = datetime.now(timezone.utc)
        self._last_start_failed = False
        logger.info(f"Invoice automation started (id={self._process_id}).")
        return CommandResult(success=True, message="Invoice automation started.")

    def stop(self) -> CommandResult:
        """Stop the running invoice automation process, if any.

        Returns:
            A CommandResult. Stopping when nothing is running is not
            treated as an error: it returns a friendly message with
            success=True, as required by EP-005.
        """
        if self._process_id is None or not self._is_tracked_process_alive():
            self._process_id = None
            self._started_at = None
            return CommandResult(success=True, message="Invoice automation is not running.")

        result = self._execution_engine.stop_process(self._process_id)
        if not result.success:
            logger.error(f"Invoice automation failed to stop: {result.message}")
            return CommandResult(
                success=False, message=f"Could not stop invoice automation: {result.message}"
            )

        logger.info(f"Invoice automation stopped (id={self._process_id}).")
        self._process_id = None
        self._started_at = None
        self._last_start_failed = False
        return CommandResult(success=True, message="Invoice automation stopped.")

    def restart(self) -> CommandResult:
        """Stop, then start, the invoice automation script.

        Returns:
            A CommandResult describing the outcome. If the stop step
            fails, start is not attempted.
        """
        stop_result = self.stop()
        if not stop_result.success:
            return stop_result

        start_result = self.start()
        if not start_result.success:
            return start_result

        logger.info("Invoice automation restarted.")
        return CommandResult(success=True, message="Invoice automation restarted.")

    def info(self) -> InvoiceInfo:
        """Return a full snapshot of the invoice automation process.

        Returns:
            An InvoiceInfo describing script path, status, process id,
            and start time, suitable for the 'invoice info' command.
        """
        try:
            script_path = self.get_script_path()
        except InvoiceConfigurationError:
            script_path = None

        return InvoiceInfo(
            script_path=script_path,
            status=self.status(),
            process_id=self._process_id,
            started_at=self._started_at,
        )

    # ---------- Internal helpers ----------

    def _is_tracked_process_alive(self) -> bool:
        """Return whether our tracked process id is still reported as running.

        Returns:
            True if `self._process_id` is present among the processes
            ExecutionEngine currently reports as alive.
        """
        if self._process_id is None:
            return False
        running_ids = {process_id for process_id, _ in self._execution_engine.list_processes()}
        return self._process_id in running_ids
