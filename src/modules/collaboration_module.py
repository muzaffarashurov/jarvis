"""Collaboration module: CLI command surface for EP-032 Multi-Agent Collaboration.

Exposes the "collaborate" command namespace (help, status, providers,
agents, use, run) as thin CommandModule handlers, following the same
pattern as ToolModule/PlanExecutionModule/PlanningModule/AgentModule.
All orchestration logic lives in CollaborationService; this module only
formats CommandResult objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.collaboration_service import (
    CollaborationOutcome,
    CollaborationProviderInfo,
    CollaborationStatus,
    ProviderSelectionResult,
    CollaborationService,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "(Distributes a request across every registered agent -- see "
    "'collaborate agents' for the roster.)\n\n"
    "collaborate help\n"
    "collaborate status\n"
    "collaborate providers\n"
    "collaborate agents\n"
    "collaborate use <provider>\n"
    'collaborate run "<request>"'
)

ActionHandler = Callable[[list[str]], CommandResult]


class CollaborationModule:
    """Built-in "collaborate" command namespace for Multi-Agent Collaboration."""

    def __init__(self, collaboration_service: CollaborationService) -> None:
        """Initialize the CollaborationModule.

        Args:
            collaboration_service: The service used to inspect and
                control the Multi-Agent Collaboration subsystem, its
                registered providers, and the live agent roster.
        """
        self._service = collaboration_service
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "status": self._status,
            "providers": self._providers,
            "agents": self._agents,
            "use": self._use,
            "run": self._run,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "collaborate"."""
        return "collaborate"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "collaborate" action.

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
            message = f'Unknown command: {command}\nType "collaborate help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available collaborate commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the Multi-Agent Collaboration subsystem's overall status."""
        status: CollaborationStatus = self._service.status()
        lines = [
            "Multi-Agent Collaboration Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Current provider : {status.current_provider or 'none'}",
            f"Registered providers : {status.registered_provider_count}",
            f"Registered agents : {status.registered_agent_count}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _providers(self, arguments: list[str]) -> CommandResult:
        """List every registered collaboration provider and its diagnostic flags."""
        providers: list[CollaborationProviderInfo] = self._service.list_providers()
        if not providers:
            return CommandResult(success=True, message="No collaboration providers registered.")

        header = f"{'Provider':<16}{'Available':<11}{'Current':<8}"
        lines = ["Collaboration Providers", "", header]
        for provider in providers:
            lines.append(
                f"{provider.name:<16}"
                f"{self._mark(provider.available):<11}"
                f"{self._mark(provider.is_current):<8}"
            )
        return CommandResult(success=True, message="\n".join(lines))

    def _agents(self, arguments: list[str]) -> CommandResult:
        """List every agent currently registered with the Agent Framework."""
        agents: list[str] = self._service.list_agents()
        if not agents:
            return CommandResult(success=True, message="No agents registered.")

        lines = ["Registered Agents", ""] + agents
        return CommandResult(success=True, message="\n".join(lines))

    def _use(self, arguments: list[str]) -> CommandResult:
        """Select a collaboration provider as the currently active provider.

        Args:
            arguments: `[provider_name]`.

        Returns:
            A CommandResult reflecting whether the provider was selected.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: collaborate use <provider>")

        result: ProviderSelectionResult = self._service.use_provider(arguments[0].lower())
        return CommandResult(success=result.success, message=result.message)

    def _run(self, arguments: list[str]) -> CommandResult:
        """Distribute the given request text across every registered agent.

        Args:
            arguments: The request words (joined with spaces).

        Returns:
            A CommandResult listing every agent's outcome, or a
            user-friendly error message.
        """
        if not arguments:
            return CommandResult(success=False, message='Usage: collaborate run "<request>"')

        request = " ".join(arguments)
        outcome: CollaborationOutcome = self._service.run(request)
        if not outcome.success or outcome.result is None:
            return CommandResult(success=False, message=outcome.error)

        result = outcome.result
        lines = [
            "Collaboration Result",
            "",
            f"Request : {result.request}",
            f"Participants : {result.participant_count}",
            f"Succeeded : {result.succeeded_count}",
            f"Failed : {result.failed_count}",
            f"Unavailable : {result.unavailable_count}",
            f"Success : {self._mark(result.success)}",
            "",
            result.summary(),
        ]
        return CommandResult(success=True, message="\n".join(lines))

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "YES" or "NO"."""
        return "YES" if value else "NO"
