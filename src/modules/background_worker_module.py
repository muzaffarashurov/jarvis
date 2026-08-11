"""Background Worker module: CLI command surface for EP-036 Background Worker Pool.

Exposes the "worker" command namespace (status, submit, list, info,
stop, help) as thin CommandModule handlers, following the same
pattern as AutomationModule/WorkflowSchedulerModule. All orchestration
logic lives in BackgroundWorkerService (STEP 2, unchanged); this
module only formats CommandResult objects for the shell.

Unlike AutomationService/WorkflowSchedulerService -- whose public
methods already return CommandResult directly, since those services
were designed CLI-first -- BackgroundWorkerService (STEP 2) exposes a
plain Python API (returns values, raises domain exceptions) with no
CLI awareness of its own, by design: STEP 2 explicitly deferred any
CLI surface to this step (see BackgroundWorkerService's own module
docstring). STEP 3 does not go back and change that STEP 2 API --
instead, exactly as promised there, this module is a pure, additive
translation layer: it calls BackgroundWorkerService's existing public
methods unchanged and catches the specific domain exceptions they
already document raising (`BackgroundWorkerServiceError`,
`PoolShutDownError`) to format them as `CommandResult(success=False, ...)`
for the shell.

No "register" command is exposed via CLI, matching EP-034's
WorkflowSchedulerModule and EP-035's AutomationModule precedent --
there is no analogous concept to register here (a task is created
directly by "worker submit", not pre-registered then triggered).

"worker stop" shuts down the owned pool (delegates to
`BackgroundWorkerService.shutdown()`), mirroring EP-011's
ProcessModule "process stop" precedent for a CLI-triggered manual
shutdown of a running resource. It uses the service's already-resolved
'background_workers.shutdown_timeout' default (no way to pass a custom
timeout from the CLI -- not needed for STEP 3's scope).
"""

from __future__ import annotations

from typing import Callable

from src.core.background_workers.background_worker_pool import (
    BackgroundTask,
    PoolShutDownError,
)
from src.core.command_router import CommandResult
from src.services.background_worker_service import (
    BackgroundWorkerService,
    BackgroundWorkerServiceError,
    BackgroundWorkerStatus,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "worker status\n"
    "worker submit <workflow_id>\n"
    "worker list\n"
    "worker info <task_id>\n"
    "worker stop\n"
    "worker help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class BackgroundWorkerModule:
    """Built-in "worker" command namespace for the Background Worker Pool."""

    def __init__(self, background_worker_service: BackgroundWorkerService) -> None:
        """Initialize the BackgroundWorkerModule.

        Args:
            background_worker_service: The service used to submit,
                inspect, list, and shut down background tasks.
        """
        self._service = background_worker_service
        self._actions: dict[str, ActionHandler] = {
            "status": self._status,
            "submit": self._submit,
            "list": self._list,
            "info": self._info,
            "stop": self._stop,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "worker"."""
        return "worker"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "worker" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a task id).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "worker help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available worker commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the Background Worker Pool's overall status."""
        status: BackgroundWorkerStatus = self._service.status()
        lines = [
            "Background Worker Status",
            f"Enabled : {'YES' if status.enabled else 'NO'}",
            f"Running : {'YES' if status.running else 'NO'}",
            f"Worker threads : {status.worker_count}",
            f"Tasks submitted : {status.task_count}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    def _submit(self, arguments: list[str]) -> CommandResult:
        """Submit a workflow for background execution."""
        workflow_id = self._require_workflow_id(arguments)
        if workflow_id is None:
            return CommandResult(success=False, message="Usage: worker submit <workflow_id>")

        try:
            task_id = self._service.submit(workflow_id)
        except BackgroundWorkerServiceError as exc:
            return CommandResult(success=False, message=str(exc))
        except PoolShutDownError as exc:
            return CommandResult(success=False, message=str(exc))

        return CommandResult(success=True, message=f"Task submitted: {task_id}")

    def _list(self, arguments: list[str]) -> CommandResult:
        """List every task ever submitted to the live pool."""
        tasks: list[BackgroundTask] = self._service.list_tasks()
        if not tasks:
            return CommandResult(success=True, message="Background Tasks\n\n(none submitted)")

        lines = ["Background Tasks"]
        for task in tasks:
            lines.append(f"{task.id} : {task.workflow_id} ({task.status.value})")
        return CommandResult(success=True, message="\n\n".join(lines))

    def _info(self, arguments: list[str]) -> CommandResult:
        """Display a task's workflow id, status, and outcome."""
        task_id = self._require_task_id(arguments)
        if task_id is None:
            return CommandResult(success=False, message="Usage: worker info <task_id>")

        task = self._service.get_task(task_id)
        if task is None:
            return CommandResult(success=False, message=f"Background task not found: {task_id}")

        pairs = [
            ("Workflow", task.workflow_id),
            ("Status", task.status.value),
        ]
        if task.error:
            pairs.append(("Error", task.error))
        message = "\n\n".join(f"{label}\n\n{value}" for label, value in pairs)
        return CommandResult(success=True, message=message)

    def _stop(self, arguments: list[str]) -> CommandResult:
        """Shut down the Background Worker Pool."""
        stopped = self._service.shutdown()
        if stopped:
            return CommandResult(success=True, message="Background Worker Pool stopped.")
        return CommandResult(
            success=False,
            message="Background Worker Pool did not stop cleanly within its configured timeout.",
        )

    @staticmethod
    def _require_workflow_id(arguments: list[str]) -> str | None:
        """Return the workflow id from arguments, or None if missing."""
        if not arguments:
            return None
        return arguments[0]

    @staticmethod
    def _require_task_id(arguments: list[str]) -> str | None:
        """Return the task id from arguments, or None if missing."""
        if not arguments:
            return None
        return arguments[0]
