"""Business logic that coordinates registered Workflow objects.

WorkflowService implements no domain logic of its own (no invoice or
workbook knowledge) and never calls InvoiceModule/FastResponseModule
directly. Per EP-007's architecture, it depends only on:

    WorkflowService -> WorkflowRegistry (workflow data)
    WorkflowService -> ExecutionEngine (step execution)

KNOWN ARCHITECTURE GAP (please read before "fixing" this):
Default workflow steps describe domain actions such as
("Invoice Automation", "start") or ("Fast Response Board", "backup").
ExecutionEngine's real, existing public API -- run(raw_target),
list_processes(), stop_process(process_id) -- only launches raw
OS-level targets (files, URLs, known system commands, Python scripts).
It has no concept of "invoke the 'start' action of the module named
X". There is currently no existing, unmodified component that lets
WorkflowService say "run Invoice Automation's start action" without
either:

  (a) WorkflowService calling InvoiceModule/FastResponseModule
      directly -- forbidden by EP-007's brief ("WorkflowService must
      NOT directly call modules"), or
  (b) ExecutionEngine exposing a method to dispatch a named module
      action -- it does not, and EP-007 lists ExecutionEngine as
      DO-NOT-MODIFY.

Per AI_GENERATION_STANDARD.md's Unknown API Policy ("If a required
method does not exist, DO NOT invent it"), this gap is not papered
over. `run_workflow()` genuinely calls ExecutionEngine.run(step.target)
as instructed ("Use ExecutionEngine"), which -- for a domain-name
target like "Invoice Automation" -- honestly reports "Unsupported
target" rather than silently pretending to succeed.

# TODO:
# To make workflow steps actually invoke module actions, one of the
# following would need to happen (neither is done here, since it was
# not explicitly requested and both change existing wiring):
#   1. Inject the existing, unmodified CommandRouter into
#      WorkflowService and dispatch f"{step.target} {step.action}"
#      through it (CommandRouter is not on EP-007's DO-NOT-MODIFY
#      list -- only ExecutionEngine and Shell are).
#   2. Extend ExecutionEngine with a reviewed, explicit API for
#      invoking named module actions.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger  # module-level logger, matching every other Jarvis component

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.execution.engine import ExecutionEngine
from src.core.workflows.workflow import Workflow, WorkflowStep
from src.core.workflows.workflow_registry import WorkflowRegistry


@dataclass(frozen=True)
class StepValidation:
    """Structural validation outcome for a single workflow step."""

    step_name: str
    is_structurally_valid: bool
    reason: str | None


@dataclass(frozen=True)
class WorkflowValidation:
    """Result of `workflow validate <id>`.

    Attributes:
        workflow_found: Whether the workflow id is registered.
        steps: Per-step structural validation results.
        targets_verified: Always False. ExecutionEngine exposes no
            side-effect-free way to check whether a target is
            runnable (calling run() would actually launch it), so
            this is reported honestly as unverified instead of
            guessed -- see the module docstring's TODO.
    """

    workflow_found: bool
    steps: tuple[StepValidation, ...]
    targets_verified: bool

    @property
    def is_ready(self) -> bool:
        """Return True if the workflow exists and every step is structurally valid."""
        return self.workflow_found and all(step.is_structurally_valid for step in self.steps)


@dataclass(frozen=True)
class WorkflowDoctorReport:
    """Result of `workflow doctor`."""

    registry_available: bool
    execution_engine_available: bool
    workflows_registered: int
    configuration_loaded: bool

    @property
    def is_ready(self) -> bool:
        """Return True only if every diagnostic check passed."""
        return (
            self.registry_available
            and self.execution_engine_available
            and self.workflows_registered > 0
            and self.configuration_loaded
        )


class WorkflowService:
    """Coordinates execution of registered Workflow objects.

    Depends only on WorkflowRegistry (workflow data) and
    ExecutionEngine (step execution), matching EP-007's architecture:
    WorkflowModule -> WorkflowService -> WorkflowRegistry -> ExecutionEngine.
    Implements no business logic of its own.
    """

    def __init__(
        self, config: Config, registry: WorkflowRegistry, execution_engine: ExecutionEngine
    ) -> None:
        """Initialize the WorkflowService.

        Args:
            config: Loaded application configuration, used to resolve
                'workflows.enabled' / 'workflows.auto_register'.
            registry: Registry holding all known Workflow objects.
            execution_engine: Shared engine used to execute steps.
        """
        self._config = config
        self._registry = registry
        self._execution_engine = execution_engine

    # ---------- Public API ----------

    def list_workflows(self) -> list[Workflow]:
        """Return all registered workflows."""
        return self._registry.list()

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        """Return the workflow registered under `workflow_id`, or None."""
        return self._registry.get(workflow_id)

    def validate_workflow(self, workflow_id: str) -> WorkflowValidation:
        """Check that a workflow exists and every step is structurally valid.

        "Targets available" cannot be verified without side effects --
        see the module docstring's TODO -- so it is always reported as
        unverified rather than guessed.
        """
        workflow = self._registry.get(workflow_id)
        if workflow is None:
            return WorkflowValidation(workflow_found=False, steps=(), targets_verified=False)

        steps = tuple(self._validate_step(step) for step in workflow.steps)
        return WorkflowValidation(workflow_found=True, steps=steps, targets_verified=False)

    def run_workflow(self, workflow_id: str) -> CommandResult:
        """Execute a registered workflow step by step via ExecutionEngine.

        See the module docstring's TODO: steps whose target is a
        domain name (not a raw OS target) will genuinely fail here,
        since ExecutionEngine cannot dispatch named module actions.

        Returns:
            A CommandResult summarizing success or failure across all
            steps.
        """
        workflow = self._registry.get(workflow_id)
        if workflow is None:
            message = f"Workflow not found: {workflow_id}"
            logger.error(message)
            return CommandResult(success=False, message=message)

        if not workflow.enabled:
            message = f"Workflow is disabled: {workflow_id}"
            logger.error(f"Workflow failed: {message}")
            return CommandResult(success=False, message=message)

        logger.info(f"Workflow started: {workflow.id}")
        failures = self._run_steps(workflow)

        if failures:
            logger.error(f"Workflow failed: {workflow.id}")
            summary = "\n".join(failures)
            message = f"Workflow '{workflow.id}' failed on {len(failures)} step(s):\n\n{summary}"
            return CommandResult(success=False, message=message)

        logger.info(f"Workflow finished: {workflow.id}")
        return CommandResult(success=True, message=f"Workflow '{workflow.id}' completed.")

    def stop_workflow(self, workflow_id: str) -> CommandResult:
        """Report that a workflow is not running.

        Workflows execute synchronously to completion inside
        run_workflow(); there is no background/async execution model
        to stop, so this reports a friendly "not running" message
        (the same convention as InvoiceService.stop()) once the
        workflow is confirmed to exist.
        """
        workflow = self._registry.get(workflow_id)
        if workflow is None:
            message = f"Workflow not found: {workflow_id}"
            logger.error(message)
            return CommandResult(success=False, message=message)

        logger.info(f"Workflow stopped: {workflow.id}")
        return CommandResult(
            success=True,
            message=f"Workflow '{workflow.id}' is not running (workflows execute synchronously).",
        )

    def run_doctor(self) -> WorkflowDoctorReport:
        """Run the `workflow doctor` diagnostic checks."""
        return WorkflowDoctorReport(
            registry_available=self._registry is not None,
            execution_engine_available=self._execution_engine is not None,
            workflows_registered=len(self._registry.list()),
            configuration_loaded=isinstance(self._config.get("workflows.enabled"), bool),
        )

    # ---------- Internal helpers ----------

    @staticmethod
    def _validate_step(step: WorkflowStep) -> StepValidation:
        """Structurally validate a single WorkflowStep.

        Args:
            step: The WorkflowStep to validate.

        Returns:
            The step's StepValidation outcome.
        """
        is_valid = bool(step.name.strip()) and bool(step.target.strip()) and bool(
            step.action.strip()
        )
        reason = None if is_valid else "Step is missing a name, target, or action."
        return StepValidation(step_name=step.name, is_structurally_valid=is_valid, reason=reason)

    def _run_steps(self, workflow: Workflow) -> list[str]:
        """Execute every step of `workflow` via ExecutionEngine, collecting failures."""
        failures: list[str] = []
        for step in workflow.steps:
            result = self._execution_engine.run(step.target)
            if not result.success:
                failures.append(f"{step.name} ({step.action}): {result.message}")
        return failures
