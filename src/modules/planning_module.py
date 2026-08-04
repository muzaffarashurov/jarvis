"""Planning module: CLI command surface for EP-029 Planning Engine.

Exposes the "planning" command namespace (help, status, providers,
use, plan, limits) as thin CommandModule handlers, following the same
pattern as ContextCompressionModule/AgentModule. All orchestration
logic lives in PlanningService; this module only formats CommandResult
objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.planning_service import (
    PlanningLimits,
    PlanningProviderInfo,
    PlanningService,
    PlanningStatus,
    PlanOutcome,
    ProviderSelectionResult,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "planning help\n"
    "planning status\n"
    "planning providers\n"
    "planning use <provider>\n"
    'planning plan "<request>"\n'
    "planning limits"
)

ActionHandler = Callable[[list[str]], CommandResult]


class PlanningModule:
    """Built-in "planning" command namespace for Planning Engine."""

    def __init__(self, planning_service: PlanningService) -> None:
        """Initialize the PlanningModule.

        Args:
            planning_service: The service used to inspect and control
                the Planning Engine subsystem and its registered
                providers.
        """
        self._service = planning_service
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "status": self._status,
            "providers": self._providers,
            "use": self._use,
            "plan": self._plan,
            "limits": self._limits,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "planning"."""
        return "planning"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "planning" action.

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
            message = f'Unknown command: {command}\nType "planning help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available planning commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the Planning Engine subsystem's overall status."""
        status: PlanningStatus = self._service.status()
        lines = [
            "Planning Engine Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Current provider : {status.current_provider or 'none'}",
            f"Registered providers : {status.registered_provider_count}",
            f"Max steps : {status.max_steps}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _providers(self, arguments: list[str]) -> CommandResult:
        """List every registered planning provider and its diagnostic flags."""
        providers: list[PlanningProviderInfo] = self._service.list_providers()
        if not providers:
            return CommandResult(success=True, message="No planning providers registered.")

        header = f"{'Provider':<14}{'Available':<11}{'Current':<8}"
        lines = ["Planning Providers", "", header]
        for provider in providers:
            lines.append(
                f"{provider.name:<14}"
                f"{self._mark(provider.available):<11}"
                f"{self._mark(provider.is_current):<8}"
            )
        return CommandResult(success=True, message="\n".join(lines))

    def _use(self, arguments: list[str]) -> CommandResult:
        """Select a planning provider as the currently active provider.

        Args:
            arguments: `[provider_name]`.

        Returns:
            A CommandResult reflecting whether the provider was selected.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: planning use <provider>")

        result: ProviderSelectionResult = self._service.use_provider(arguments[0].lower())
        return CommandResult(success=result.success, message=result.message)

    def _plan(self, arguments: list[str]) -> CommandResult:
        """Decompose the given request text into an ordered Plan.

        Args:
            arguments: The request words (joined with spaces).

        Returns:
            A CommandResult listing the plan, or a user-friendly error
            message.
        """
        if not arguments:
            return CommandResult(success=False, message='Usage: planning plan "<request>"')

        request = " ".join(arguments)
        outcome: PlanOutcome = self._service.plan(request)
        if not outcome.success or outcome.plan is None:
            return CommandResult(success=False, message=outcome.error)

        plan = outcome.plan
        lines = [
            "Plan",
            "",
            f"Request : {plan.request}",
            f"Steps : {plan.step_count}",
            f"Truncated : {self._mark(plan.truncated)}",
            "",
            plan.summary(),
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _limits(self, arguments: list[str]) -> CommandResult:
        """Display the current default planning limits."""
        limits: PlanningLimits = self._service.limits()
        lines = [
            "Planning Engine Limits",
            f"Max steps : {limits.max_steps}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "YES" or "NO"."""
        return "YES" if value else "NO"
