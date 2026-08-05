"""Tool module: CLI command surface for EP-031 Tool Engine.

Exposes the "tool" command namespace (help, status, providers, list,
use, run) as thin CommandModule handlers, following the same pattern
as PlanExecutionModule/PlanningModule/AgentModule. All orchestration
logic lives in ToolService; this module only formats CommandResult
objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.tool_service import (
    ProviderSelectionResult,
    RunOutcome,
    ToolEngineStatus,
    ToolInfo,
    ToolProviderInfo,
    ToolService,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "(Invokes real subsystem actions -- see 'tool list' for the catalog.)\n\n"
    "tool help\n"
    "tool status\n"
    "tool providers\n"
    "tool list\n"
    "tool use <provider>\n"
    "tool run <tool_id>"
)

ActionHandler = Callable[[list[str]], CommandResult]


class ToolModule:
    """Built-in "tool" command namespace for Tool Engine."""

    def __init__(self, tool_service: ToolService) -> None:
        """Initialize the ToolModule.

        Args:
            tool_service: The service used to inspect and control the
                Tool Engine subsystem, its registered providers, and
                its tool catalog.
        """
        self._service = tool_service
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "status": self._status,
            "providers": self._providers,
            "list": self._list,
            "use": self._use,
            "run": self._run,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "tool"."""
        return "tool"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "tool" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a provider or tool id).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "tool help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available tool commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the Tool Engine subsystem's overall status."""
        status: ToolEngineStatus = self._service.status()
        lines = [
            "Tool Engine Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Current provider : {status.current_provider or 'none'}",
            f"Registered providers : {status.registered_provider_count}",
            f"Registered tools : {status.registered_tool_count}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _providers(self, arguments: list[str]) -> CommandResult:
        """List every registered tool provider and its diagnostic flags."""
        providers: list[ToolProviderInfo] = self._service.list_providers()
        if not providers:
            return CommandResult(success=True, message="No tool providers registered.")

        header = f"{'Provider':<16}{'Available':<11}{'Current':<8}"
        lines = ["Tool Providers", "", header]
        for provider in providers:
            lines.append(
                f"{provider.name:<16}"
                f"{self._mark(provider.available):<11}"
                f"{self._mark(provider.is_current):<8}"
            )
        return CommandResult(success=True, message="\n".join(lines))

    def _list(self, arguments: list[str]) -> CommandResult:
        """List every registered tool in the catalog."""
        tools: list[ToolInfo] = self._service.list_tools()
        if not tools:
            return CommandResult(success=True, message="No tools registered.")

        header = f"{'Tool':<24}{'Subsystem':<18}{'Action':<24}{'Enabled':<8}"
        lines = ["Tool Catalog", "", header]
        for tool in tools:
            lines.append(
                f"{tool.id:<24}"
                f"{(tool.subsystem or 'none'):<18}"
                f"{tool.action:<24}"
                f"{self._mark(tool.enabled):<8}"
            )
        return CommandResult(success=True, message="\n".join(lines))

    def _use(self, arguments: list[str]) -> CommandResult:
        """Select a tool provider as the currently active provider.

        Args:
            arguments: `[provider_name]`.

        Returns:
            A CommandResult reflecting whether the provider was selected.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: tool use <provider>")

        result: ProviderSelectionResult = self._service.use_provider(arguments[0].lower())
        return CommandResult(success=result.success, message=result.message)

    def _run(self, arguments: list[str]) -> CommandResult:
        """Invoke a single registered tool by id.

        Args:
            arguments: `[tool_id]`.

        Returns:
            A CommandResult listing the invocation outcome, or a
            user-friendly error message.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: tool run <tool_id>")

        outcome: RunOutcome = self._service.run(arguments[0])
        if not outcome.success or outcome.result is None:
            return CommandResult(success=False, message=outcome.error)

        result = outcome.result
        lines = [
            "Tool Invocation Result",
            "",
            f"Tool : {result.tool_id}",
            f"Status : {result.status.value}",
            f"Message : {result.message}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "YES" or "NO"."""
        return "YES" if value else "NO"
