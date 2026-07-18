"""Workflow module: CLI command surface for EP-007 Workflow Engine.

Exposes the "workflow" command namespace (list, info, run, validate,
stop, doctor, help) as thin CommandModule handlers, following the same
pattern as SystemModule/InvoiceModule/FastResponseModule. All
orchestration logic lives in WorkflowService; this module only formats
CommandResult objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.workflows.workflow import Workflow
from src.services.workflow_service import (
    WorkflowDoctorReport,
    WorkflowService,
    WorkflowValidation,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "workflow list\n"
    "workflow info <workflow>\n"
    "workflow run <workflow>\n"
    "workflow validate <workflow>\n"
    "workflow stop <workflow>\n"
    "workflow doctor\n"
    "workflow help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class WorkflowModule:
    """Built-in "workflow" command namespace for the Workflow Engine."""

    def __init__(self, workflow_service: WorkflowService) -> None:
        """Initialize the WorkflowModule.

        Args:
            workflow_service: The service used to list, inspect, run,
                validate, and stop workflows.
        """
        self._service = workflow_service
        self._actions: dict[str, ActionHandler] = {
            "list": self._list,
            "info": self._info,
            "run": self._run,
            "validate": self._validate,
            "stop": self._stop,
            "doctor": self._doctor,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "workflow"."""
        return "workflow"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "workflow" action.

        Args:
            action: The requested action (e.g. "list").
            arguments: Additional arguments (e.g. a workflow id).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "workflow help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available workflow commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _list(self, arguments: list[str]) -> CommandResult:
        """List all registered workflows."""
        workflows: list[Workflow] = self._service.list_workflows()
        if not workflows:
            return CommandResult(success=True, message="Workflows\n\n(none registered)")

        lines = ["Workflows"]
        for workflow in workflows:
            state = "enabled" if workflow.enabled else "disabled"
            lines.append(
                f"{workflow.id} : {workflow.name} ({state}, {len(workflow.steps)} step(s))"
            )
        return CommandResult(success=True, message="\n\n".join(lines))

    def _info(self, arguments: list[str]) -> CommandResult:
        """Display name, description, step count, and status for a workflow."""
        workflow_id = self._require_workflow_id(arguments)
        if workflow_id is None:
            return CommandResult(success=False, message="Usage: workflow info <workflow>")

        workflow = self._service.get_workflow(workflow_id)
        if workflow is None:
            return CommandResult(success=False, message=f"Workflow not found: {workflow_id}")

        pairs = (
            ("Name", workflow.name),
            ("Description", workflow.description),
            ("Number of steps", str(len(workflow.steps))),
            ("Status", "ENABLED" if workflow.enabled else "DISABLED"),
        )
        message = "\n\n".join(f"{label}\n\n{value}" for label, value in pairs)
        return CommandResult(success=True, message=message)

    def _run(self, arguments: list[str]) -> CommandResult:
        """Execute a workflow."""
        workflow_id = self._require_workflow_id(arguments)
        if workflow_id is None:
            return CommandResult(success=False, message="Usage: workflow run <workflow>")
        return self._service.run_workflow(workflow_id)

    def _stop(self, arguments: list[str]) -> CommandResult:
        """Stop a workflow (workflows execute synchronously; see WorkflowService)."""
        workflow_id = self._require_workflow_id(arguments)
        if workflow_id is None:
            return CommandResult(success=False, message="Usage: workflow stop <workflow>")
        return self._service.stop_workflow(workflow_id)

    def _validate(self, arguments: list[str]) -> CommandResult:
        """Validate a workflow's existence and step structure."""
        workflow_id = self._require_workflow_id(arguments)
        if workflow_id is None:
            return CommandResult(success=False, message="Usage: workflow validate <workflow>")

        result: WorkflowValidation = self._service.validate_workflow(workflow_id)
        if not result.workflow_found:
            return CommandResult(success=False, message=f"Workflow not found: {workflow_id}")

        lines = [f"Workflow Validation: {workflow_id}"]
        for step in result.steps:
            mark = "OK" if step.is_structurally_valid else "FAIL"
            lines.append(f"{step.step_name} : {mark}")
        lines.append("Targets available : NOT VERIFIED (see WorkflowService TODO)")
        lines.append(f"Result : {'READY' if result.is_ready else 'FAILED'}")
        return CommandResult(success=result.is_ready, message="\n\n".join(lines))

    def _doctor(self, arguments: list[str]) -> CommandResult:
        """Run full workflow-engine diagnostics."""
        report: WorkflowDoctorReport = self._service.run_doctor()
        lines = [
            "Workflow Engine Doctor",
            f"Workflow registry : {self._mark(report.registry_available)}",
            f"ExecutionEngine : {self._mark(report.execution_engine_available)}",
            f"Registered workflows : {report.workflows_registered}",
            f"Configuration : {self._mark(report.configuration_loaded)}",
            f"Result : {'READY' if report.is_ready else 'FAILED'}",
        ]
        return CommandResult(success=report.is_ready, message="\n\n".join(lines))

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "OK" or "FAIL"."""
        return "OK" if value else "FAIL"

    @staticmethod
    def _require_workflow_id(arguments: list[str]) -> str | None:
        """Return the workflow id from arguments, or None if missing."""
        if not arguments:
            return None
        return arguments[0]
