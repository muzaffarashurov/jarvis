"""Runtime module: CLI command surface for EP-059/EP-060 RuntimeService.

Exposes the "runtime" command namespace (status, help) as thin
CommandModule handlers, following the same pattern as
BackgroundWorkerModule/PlanningModule. All aggregation/coordination
logic lives in RuntimeService (unchanged); this module only formats
`RuntimeStatus` into a `CommandResult` for the shell.

Per EP-059 Owner Decision D5 and EP-060 Owner Decision D3, no mutating
action of any kind is exposed here (no "runtime restart"/"stop"/
"shutdown"/"reconfigure") -- `status`/`help` remain the only two
actions. EP-060 adds `RuntimeService.shutdown()`, but it is invoked
exclusively by `Bootstrap.shutdown()` at process exit, never through
this module -- see `EP060_DESIGN.md` Section 9.2/Owner Decision D3
("shutdown coordination remains internal-only... never dispatchable
via the Shell or... the still-unauthenticated REST API").

Since `RestApiServer`'s own `ApiRouter` (EP-043) already forwards any
`CommandRouter`-registered command unchanged, "runtime status" becomes
reachable over the REST API the moment this module is registered, with
zero REST-layer-specific code written for it (see `EP059_DESIGN.md`
Section 6.4). Because no mutating action exists in this module, this
remains true without introducing any new REST-reachable control
surface.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.runtime_service import RuntimeService, RuntimeStatus

HELP_TEXT: str = "Available commands\n\nruntime status\nruntime help"

ActionHandler = Callable[[list[str]], CommandResult]


class RuntimeModule:
    """Built-in "runtime" command namespace for EP-059 RuntimeService."""

    def __init__(self, runtime_service: RuntimeService) -> None:
        """Initialize the RuntimeModule.

        Args:
            runtime_service: The service used to produce a
                `RuntimeStatus` snapshot on demand.
        """
        self._service = runtime_service
        self._actions: dict[str, ActionHandler] = {
            "status": self._status,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "runtime"."""
        return "runtime"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "runtime" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments. Unused by every action
                this module exposes; extra arguments are silently
                ignored, matching this document's own "read-only,
                minimal surface" scope (no usage error is raised for
                trailing arguments, since neither "status" nor "help"
                accepts any).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "runtime help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available runtime commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display this Jarvis instance's aggregated runtime status."""
        status: RuntimeStatus = self._service.status()
        lines = [
            "Runtime Status",
            f"PID : {status.pid}",
            f"Uptime (seconds) : {status.uptime_seconds:.1f}",
            f"Shell : {'ACTIVE' if status.shell_active else 'INACTIVE'}",
            f"REST API : {'ACTIVE' if status.api_active else 'INACTIVE'}",
        ]
        if status.api_active:
            lines.append(f"REST API address : {status.api_host}:{status.api_port}")
        lines.append(
            f"Background Workers : "
            f"{'ACTIVE' if status.background_workers_active else 'INACTIVE'}"
        )
        if status.background_workers_active:
            lines.append(f"Background worker threads : {status.background_worker_count}")
            lines.append(f"Background tasks submitted : {status.background_worker_task_count}")
        lines.append(
            f"Scheduler : {'ACTIVE' if status.scheduler_active else 'INACTIVE'}"
        )
        if status.scheduler_active:
            lines.append(f"Scheduler jobs registered : {status.scheduler_jobs_registered}")
        return CommandResult(success=True, message="\n\n".join(lines))
