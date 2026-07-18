"""Process module: CLI command surface for EP-008 Process Catalog & Smart Orchestrator.

Exposes the "process" command namespace (list, info, start, stop,
restart, status, doctor, help) as thin CommandModule handlers,
following the same pattern as InvoiceModule and FastResponseModule.
All coordination logic lives in ProcessService; this module only
formats CommandResult objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.processes.process import Process, ProcessHealth
from src.services.process_service import DoctorReport, ProcessService, UnknownProcessError

HELP_TEXT: str = (
    "Available commands\n\n"
    "process list\n"
    "process info <name>\n"
    "process start <name>\n"
    "process stop <name>\n"
    "process restart <name>\n"
    "process status\n"
    "process doctor\n"
    "process help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class ProcessModule:
    """Built-in "process" command namespace for the Process Catalog.

    Responsibilities:
        - List all registered processes (list).
        - Display details for a single process (info).
        - Start / stop / restart a process (start, stop, restart).
        - Report all currently running processes (status).
        - Run catalog readiness diagnostics (doctor).
        - Report available commands (help).
    """

    def __init__(self, process_service: ProcessService) -> None:
        """Initialize the ProcessModule.

        Args:
            process_service: The service used to coordinate registered processes.
        """
        self._service = process_service
        self._actions: dict[str, ActionHandler] = {
            "list": self._list,
            "info": self._info,
            "start": self._start,
            "stop": self._stop,
            "restart": self._restart,
            "status": self._status,
            "doctor": self._doctor,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "process"."""
        return "process"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "process" action.

        Args:
            action: The requested action (e.g. "list").
            arguments: Additional arguments (e.g. the process name).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "process help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available process commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _list(self, arguments: list[str]) -> CommandResult:
        """List every registered process with its id and enabled state."""
        processes = self._service.list_processes()
        if not processes:
            return CommandResult(success=True, message="No processes registered.")

        lines = ["Registered Processes"]
        for process in processes:
            lines.append(f"{process.id} ({process.name}) - {self._enabled_label(process)}")
        return CommandResult(success=True, message="\n\n".join(lines))

    def _info(self, arguments: list[str]) -> CommandResult:
        """Display description, dependencies, status, restart policy, and health."""
        name = self._require_name(arguments)
        if name is None:
            return CommandResult(success=False, message="Usage: process info <name>")

        try:
            process = self._service.get_process(name)
            health = self._service.health(name)
        except UnknownProcessError as exc:
            return CommandResult(success=False, message=str(exc))

        dependencies = ", ".join(process.dependencies) if process.dependencies else "(none)"
        pairs = (
            ("Name", process.name),
            ("Description", process.description),
            ("Dependencies", dependencies),
            ("Status", health.value),
            ("Restart policy", process.restart_policy.value),
            ("Health check", "enabled" if process.health_check else "disabled"),
        )
        message = "\n\n".join(f"{label}\n\n{value}" for label, value in pairs)
        return CommandResult(success=True, message=message)

    def _start(self, arguments: list[str]) -> CommandResult:
        """Start a process by name, resolving dependencies first."""
        name = self._require_name(arguments)
        if name is None:
            return CommandResult(success=False, message="Usage: process start <name>")
        return self._service.start(name)

    def _stop(self, arguments: list[str]) -> CommandResult:
        """Stop a process by name."""
        name = self._require_name(arguments)
        if name is None:
            return CommandResult(success=False, message="Usage: process stop <name>")

        try:
            return self._service.stop(name)
        except UnknownProcessError as exc:
            return CommandResult(success=False, message=str(exc))

    def _restart(self, arguments: list[str]) -> CommandResult:
        """Restart a process by name."""
        name = self._require_name(arguments)
        if name is None:
            return CommandResult(success=False, message="Usage: process restart <name>")

        try:
            return self._service.restart(name)
        except UnknownProcessError as exc:
            return CommandResult(success=False, message=str(exc))

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display all processes currently reporting RUNNING or READY."""
        running: list[tuple[Process, ProcessHealth]] = []
        for process in self._service.list_processes():
            health = self._service.health(process.id)
            if health in (ProcessHealth.RUNNING, ProcessHealth.READY):
                running.append((process, health))

        if not running:
            return CommandResult(success=True, message="No processes currently running.")

        lines = ["Running Processes"]
        for process, health in running:
            lines.append(f"{process.id} ({process.name}) - {health.value}")
        return CommandResult(success=True, message="\n\n".join(lines))

    def _doctor(self, arguments: list[str]) -> CommandResult:
        """Run registry, dependency, engine, workflow, and configuration checks."""
        report: DoctorReport = self._service.run_doctor()
        lines = [
            "Process Catalog Doctor",
            f"Registry : {self._mark(report.registry_ok)}",
            f"Dependencies : {self._mark(report.dependencies_ok)}",
            f"Execution Engine : {self._mark(report.execution_engine_ok)}",
            f"Workflow Engine : {self._mark(report.workflow_engine_ok)}",
            f"Configuration : {self._mark(report.configuration_ok)}",
            f"Result : {'READY' if report.is_ready else 'FAILED'}",
        ]
        return CommandResult(success=report.is_ready, message="\n\n".join(lines))

    @staticmethod
    def _require_name(arguments: list[str]) -> str | None:
        """Return the first argument as a process name, or None if missing."""
        return arguments[0] if arguments else None

    @staticmethod
    def _enabled_label(process: Process) -> str:
        """Return "enabled" or "disabled" for a process's `enabled` flag."""
        return "enabled" if process.enabled else "disabled"

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "OK" or "FAIL"."""
        return "OK" if value else "FAIL"
