"""Workflow Engine module: CLI command surface for EP-033 Workflow Engine.

Exposes the "flow" command namespace (help, status, list, info, use,
run) as thin CommandModule handlers, following the same pattern as
CollaborationModule/ToolModule/PlanExecutionModule/PlanningModule.
All orchestration logic lives in WorkflowEngineService; this module
only formats CommandResult objects for the shell.

NOTE: the CLI namespace is deliberately "flow", not "workflow" -- see
src/core/workflow_engine/__init__.py's naming-collision note (the
"workflow" token belongs to EP-007's dormant WorkflowModule).
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.workflow_engine.workflow_definition import WorkflowDefinition
from src.services.workflow_engine_service import (
    ProviderSelectionResult,
    WorkflowEngineService,
    WorkflowEngineStatus,
    WorkflowRunOutcome,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "(Runs a named, ordered sequence of requests through the Planning "
    "+ Plan Execution pipeline -- see 'flow list' for registered workflows.)\n\n"
    "flow help\n"
    "flow status\n"
    "flow list\n"
    "flow info <id>\n"
    "flow use <provider>\n"
    "flow run <id>"
)

ActionHandler = Callable[[list[str]], CommandResult]


class WorkflowEngineModule:
    """Built-in "flow" command namespace for Workflow Engine."""

    def __init__(self, workflow_engine_service: WorkflowEngineService) -> None:
        """Initialize the WorkflowEngineModule.

        Args:
            workflow_engine_service: The service used to inspect and
                control the Workflow Engine subsystem and its
                registered workflow definitions.
        """
        self._service = workflow_engine_service
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "status": self._status,
            "list": self._list,
            "info": self._info,
            "use": self._use,
            "run": self._run,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "flow"."""
        return "flow"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "flow" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a provider name or
                workflow definition id).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "flow help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available flow commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the Workflow Engine subsystem's overall status."""
        status: WorkflowEngineStatus = self._service.status()
        lines = [
            "Workflow Engine Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Current provider : {status.current_provider or 'none'}",
            f"Stop on failure : {self._mark(status.stop_on_failure)}",
            f"Registered providers : {status.registered_provider_count}",
            f"Registered workflows : {status.registered_definition_count}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _list(self, arguments: list[str]) -> CommandResult:
        """List every registered workflow definition."""
        definitions: list[WorkflowDefinition] = self._service.list_definitions()
        if not definitions:
            return CommandResult(success=True, message="No workflows registered.")

        header = f"{'ID':<24}{'Steps':<7}{'Enabled':<9}Name"
        lines = ["Registered Workflows", "", header]
        for definition in definitions:
            lines.append(
                f"{definition.id:<24}"
                f"{len(definition.steps):<7}"
                f"{self._mark(definition.enabled):<9}"
                f"{definition.name}"
            )
        return CommandResult(success=True, message="\n".join(lines))

    def _info(self, arguments: list[str]) -> CommandResult:
        """Display a single workflow definition's steps.

        Args:
            arguments: `[definition_id]`.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: flow info <id>")

        definition = self._service.get_definition(arguments[0])
        if definition is None:
            return CommandResult(success=False, message=f"Unknown workflow: '{arguments[0]}'.")

        lines = [
            f"Workflow: {definition.name} ({definition.id})",
            definition.description,
            f"Enabled : {self._mark(definition.enabled)}",
            "",
            "Steps:",
        ]
        for index, step in enumerate(definition.steps, start=1):
            lines.append(f"{index}. {step.name} - {step.request}")
        return CommandResult(success=True, message="\n".join(lines))

    def _use(self, arguments: list[str]) -> CommandResult:
        """Select a workflow-run provider as the currently active provider.

        Args:
            arguments: `[provider_name]`.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: flow use <provider>")

        result: ProviderSelectionResult = self._service.use_provider(arguments[0].lower())
        return CommandResult(success=result.success, message=result.message)

    def _run(self, arguments: list[str]) -> CommandResult:
        """Run an already-registered workflow definition by id.

        Args:
            arguments: `[definition_id]`.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: flow run <id>")

        outcome: WorkflowRunOutcome = self._service.run(arguments[0])
        if not outcome.success or outcome.result is None:
            return CommandResult(success=False, message=outcome.error)

        result = outcome.result
        lines = [
            "Workflow Run Result",
            "",
            f"Workflow : {result.definition_name} ({result.definition_id})",
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
