"""Invoice module: CLI command surface for EP-005 Invoice Automation.

Exposes the "invoice" command namespace (status, start, stop, restart,
info, help) as thin CommandModule handlers, following the same pattern
as SystemModule (see src/skills/system/skill.py). All business logic —
resolving the script path, deciding process state, and talking to the
ExecutionEngine — lives in InvoiceService; this module only formats
CommandResult objects for the shell and never launches or stops
anything itself.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from loguru import logger

from src.core.command_router import CommandResult
from src.services.invoice_service import InvoiceInfo, InvoiceService, InvoiceStatus

HELP_TEXT: str = (
    "Available commands\n\n"
    "invoice status\n"
    "invoice start\n"
    "invoice stop\n"
    "invoice restart\n"
    "invoice info\n"
    "invoice help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class InvoiceModule:
    """Built-in "invoice" command namespace for Invoice Automation.

    Responsibilities:
        - Report invoice automation status (status).
        - Start the automation script (start).
        - Stop the running automation process (stop).
        - Restart the automation script (restart).
        - Display detailed process information (info).
        - Report available commands (help).
    """

    def __init__(self, invoice_service: InvoiceService) -> None:
        """Initialize the InvoiceModule.

        Args:
            invoice_service: The service used to resolve, launch, stop,
                and inspect the invoice automation process.
        """
        self._service = invoice_service
        self._actions: dict[str, ActionHandler] = {
            "status": self._status,
            "start": self._start,
            "stop": self._stop,
            "restart": self._restart,
            "info": self._info,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace.

        Returns:
            The literal string "invoice".
        """
        return "invoice"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute an "invoice" action.

        Args:
            action: The requested action (e.g. "status"). May be empty
                if the user entered only "invoice".
            arguments: Additional arguments; unused by current actions.

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            logger.info(f"Unknown command: {command}")
            message = (
                f"Unknown command: {command}\n"
                'Type "invoice help" for available commands.'
            )
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available invoice commands.

        Args:
            arguments: Unused.

        Returns:
            A CommandResult containing the help text.
        """
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Report the current invoice automation status.

        Args:
            arguments: Unused.

        Returns:
            A CommandResult with status, and PID/running time when the
            process is RUNNING.
        """
        info = self._service.info()
        lines = ["Invoice Automation", f"Status : {info.status.value}"]

        if info.status == InvoiceStatus.RUNNING and info.process_id is not None:
            lines.append(f"PID : {info.process_id}")
            if info.started_at is not None:
                lines.append(f"Running : {self._format_elapsed(info.started_at)}")

        return CommandResult(success=True, message="\n\n".join(lines))

    def _start(self, arguments: list[str]) -> CommandResult:
        """Start the invoice automation script.

        Args:
            arguments: Unused.

        Returns:
            The CommandResult from InvoiceService.start().
        """
        return self._service.start()

    def _stop(self, arguments: list[str]) -> CommandResult:
        """Stop the running invoice automation process.

        Args:
            arguments: Unused.

        Returns:
            The CommandResult from InvoiceService.stop().
        """
        return self._service.stop()

    def _restart(self, arguments: list[str]) -> CommandResult:
        """Restart the invoice automation script (stop, then start).

        Args:
            arguments: Unused.

        Returns:
            The CommandResult from InvoiceService.restart().
        """
        return self._service.restart()

    def _info(self, arguments: list[str]) -> CommandResult:
        """Display detailed invoice automation process information.

        Args:
            arguments: Unused.

        Returns:
            A CommandResult with script path, location, status, PID,
            and start time.
        """
        info: InvoiceInfo = self._service.info()

        script_name = info.script_path.name if info.script_path else "(not configured)"
        location = str(info.script_path.parent) if info.script_path else "(unknown)"
        pid = str(info.process_id) if info.process_id is not None else "-"
        started = (
            info.started_at.astimezone().strftime("%H:%M:%S")
            if info.started_at
            else "(not started)"
        )

        pairs = (
            ("Script", script_name),
            ("Location", location),
            ("Status", info.status.value),
            ("PID", pid),
            ("Started", started),
        )
        message = "\n\n".join(f"{label}\n\n{value}" for label, value in pairs)
        return CommandResult(success=True, message=message)

    @staticmethod
    def _format_elapsed(started_at: datetime) -> str:
        """Format the time elapsed since `started_at` as HH:MM:SS.

        Args:
            started_at: The timezone-aware (UTC) timestamp the tracked
                process was launched.

        Returns:
            The elapsed running time, formatted as "HH:MM:SS".
        """
        elapsed_seconds = max(int((datetime.now(timezone.utc) - started_at).total_seconds()), 0)
        hours, remainder = divmod(elapsed_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
