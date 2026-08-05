"""Plan execution module: CLI command surface for EP-030 Plan Execution Engine.

Exposes the "execution" command namespace (help, status, providers,
use, run) as thin CommandModule handlers, following the same pattern
as PlanningModule/AgentModule. All orchestration logic lives in
PlanExecutionService; this module only formats CommandResult objects
for the shell.

NOTE: "execution" here refers exclusively to dispatching an EP-029
Plan's steps -- it is unrelated to the pre-existing OS-level target
launcher from EP-003 (`src/core/execution/`, wrapped by the `process`,
`invoice`, `frb`, `scheduler`, and `workflow` CLI namespaces). See
src/core/plan_execution/__init__.py for the full disambiguation note.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.plan_execution_service import (
    PlanExecutionProviderInfo,
    PlanExecutionService,
    PlanExecutionStatus,
    ProviderSelectionResult,
    RunOutcome,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "(Dispatches EP-029 Plan steps -- unrelated to OS process launching.)\n\n"
    "execution help\n"
    "execution status\n"
    "execution providers\n"
    "execution use <provider>\n"
    'execution run "<request>"'
)

ActionHandler = Callable[[list[str]], CommandResult]


class PlanExecutionModule:
    """Built-in "execution" command namespace for the Plan Execution Engine."""

    def __init__(self, plan_execution_service: PlanExecutionService) -> None:
        """Initialize the PlanExecutionModule.

        Args:
            plan_execution_service: The service used to inspect and
                control the Plan Execution Engine subsystem and its
                registered providers.
        """
        self._service = plan_execution_service
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "status": self._status,
            "providers": self._providers,
            "use": self._use,
            "run": self._run,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "execution"."""
        return "execution"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute an "execution" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a provider name or
                request text).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "execution help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available plan-execution commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the Plan Execution Engine subsystem's overall status."""
        status: PlanExecutionStatus = self._service.status()
        lines = [
            "Plan Execution Engine Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Current provider : {status.current_provider or 'none'}",
            f"Registered providers : {status.registered_provider_count}",
            f"Stop on failure : {self._mark(status.stop_on_failure)}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _providers(self, arguments: list[str]) -> CommandResult:
        """List every registered plan-execution provider and its diagnostic flags."""
        providers: list[PlanExecutionProviderInfo] = self._service.list_providers()
        if not providers:
            return CommandResult(success=True, message="No plan-execution providers registered.")

        header = f"{'Provider':<16}{'Available':<11}{'Current':<8}"
        lines = ["Plan Execution Providers", "", header]
        for provider in providers:
            lines.append(
                f"{provider.name:<16}"
                f"{self._mark(provider.available):<11}"
                f"{self._mark(provider.is_current):<8}"
            )
        return CommandResult(success=True, message="\n".join(lines))

    def _use(self, arguments: list[str]) -> CommandResult:
        """Select a plan-execution provider as the currently active provider.

        Args:
            arguments: `[provider_name]`.

        Returns:
            A CommandResult reflecting whether the provider was selected.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: execution use <provider>")

        result: ProviderSelectionResult = self._service.use_provider(arguments[0].lower())
        return CommandResult(success=result.success, message=result.message)

    def _run(self, arguments: list[str]) -> CommandResult:
        """Plan the given request text and execute the resulting plan.

        Args:
            arguments: The request words (joined with spaces).

        Returns:
            A CommandResult listing the execution outcome, or a
            user-friendly error message.
        """
        if not arguments:
            return CommandResult(success=False, message='Usage: execution run "<request>"')

        request = " ".join(arguments)
        outcome: RunOutcome = self._service.run(request)
        if not outcome.success or outcome.result is None:
            return CommandResult(success=False, message=outcome.error)

        result = outcome.result
        lines = [
            "Plan Execution Result",
            "",
            f"Request : {result.plan.request}",
            f"Completed : {result.completed_count}",
            f"Failed : {result.failed_count}",
            f"Skipped : {result.skipped_count}",
            f"Success : {self._mark(result.success)}",
            "",
            result.summary(),
        ]
        return CommandResult(success=True, message="\n".join(lines))

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "YES" or "NO"."""
        return "YES" if value else "NO"
