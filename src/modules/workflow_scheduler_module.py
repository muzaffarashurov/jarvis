"""Workflow Scheduler module: CLI command surface for EP-034 Workflow Scheduler.

Exposes the "autoflow" command namespace (list, status, run, start,
stop, info, help) as thin CommandModule handlers, following the same
pattern as SchedulerModule/WorkflowEngineModule. All orchestration
logic lives in WorkflowSchedulerService; this module only formats
CommandResult objects for the shell.

NOTE: the CLI namespace is deliberately "autoflow", not "scheduler" or
"schedule" -- see src/core/workflow_scheduler/__init__.py's
naming-collision note ("scheduler" belongs to EP-011's active
SchedulerModule; "schedule" was avoided as a too-similar near-miss).

No "register" command is exposed via CLI, matching EP-011's
SchedulerModule and EP-033's WorkflowEngineModule precedent -- entries
are registered only through the public
`WorkflowSchedulerService.register()` API (e.g. at Bootstrap).
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.workflow_scheduler.scheduled_workflow import ScheduledWorkflow
from src.services.workflow_scheduler_service import WorkflowSchedulerService, WorkflowSchedulerStatus

HELP_TEXT: str = (
    "Available commands\n\n"
    "autoflow list\n"
    "autoflow status\n"
    "autoflow run <id>\n"
    "autoflow start <id>\n"
    "autoflow stop <id>\n"
    "autoflow info <id>\n"
    "autoflow help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class WorkflowSchedulerModule:
    """Built-in "autoflow" command namespace for Workflow Scheduler."""

    def __init__(self, workflow_scheduler_service: WorkflowSchedulerService) -> None:
        """Initialize the WorkflowSchedulerModule.

        Args:
            workflow_scheduler_service: The service used to list,
                inspect, run, start, and stop scheduled workflows.
        """
        self._service = workflow_scheduler_service
        self._actions: dict[str, ActionHandler] = {
            "list": self._list,
            "status": self._status,
            "run": self._run,
            "start": self._start,
            "stop": self._stop,
            "info": self._info,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "autoflow"."""
        return "autoflow"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute an "autoflow" action.

        Args:
            action: The requested action (e.g. "list").
            arguments: Additional arguments (e.g. a scheduled workflow id).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "autoflow help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available autoflow commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _list(self, arguments: list[str]) -> CommandResult:
        """List all registered scheduled workflows."""
        entries: list[ScheduledWorkflow] = self._service.list_entries()
        if not entries:
            return CommandResult(success=True, message="Scheduled Workflows\n\n(none registered)")

        lines = ["Scheduled Workflows"]
        for entry in entries:
            state = "enabled" if entry.enabled else "disabled"
            lines.append(
                f"{entry.id} : {entry.name} -> {entry.workflow_id} "
                f"({state}, {entry.schedule.type.value})"
            )
        return CommandResult(success=True, message="\n\n".join(lines))

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the workflow scheduler's overall status."""
        status: WorkflowSchedulerStatus = self._service.status()
        lines = [
            "Workflow Scheduler Status",
            f"Running : {'YES' if status.running else 'NO'}",
            f"Scheduled workflows registered : {status.entries_registered}",
            f"Scheduled workflows enabled : {status.entries_enabled}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    def _run(self, arguments: list[str]) -> CommandResult:
        """Run a scheduled workflow's referenced workflow immediately."""
        entry_id = self._require_entry_id(arguments)
        if entry_id is None:
            return CommandResult(success=False, message="Usage: autoflow run <id>")
        return self._service.run(entry_id)

    def _start(self, arguments: list[str]) -> CommandResult:
        """Enable scheduled execution for an entry."""
        entry_id = self._require_entry_id(arguments)
        if entry_id is None:
            return CommandResult(success=False, message="Usage: autoflow start <id>")
        return self._service.start(entry_id)

    def _stop(self, arguments: list[str]) -> CommandResult:
        """Disable scheduled execution for an entry."""
        entry_id = self._require_entry_id(arguments)
        if entry_id is None:
            return CommandResult(success=False, message="Usage: autoflow stop <id>")
        return self._service.stop(entry_id)

    def _info(self, arguments: list[str]) -> CommandResult:
        """Display name, status, schedule, last/next run, and description."""
        entry_id = self._require_entry_id(arguments)
        if entry_id is None:
            return CommandResult(success=False, message="Usage: autoflow info <id>")

        entry = self._service.get_entry(entry_id)
        if entry is None:
            return CommandResult(success=False, message=f"Scheduled workflow not found: {entry_id}")

        pairs = (
            ("Name", entry.name),
            ("Workflow", entry.workflow_id),
            ("Status", entry.status.value),
            ("Schedule", entry.schedule.type.value),
            ("Last Run", entry.last_run.isoformat() if entry.last_run else "never"),
            ("Next Run", entry.next_run.isoformat() if entry.next_run else "not scheduled"),
            ("Description", entry.description),
        )
        message = "\n\n".join(f"{label}\n\n{value}" for label, value in pairs)
        return CommandResult(success=True, message=message)

    @staticmethod
    def _require_entry_id(arguments: list[str]) -> str | None:
        """Return the scheduled workflow id from arguments, or None if missing."""
        if not arguments:
            return None
        return arguments[0]
