"""EP-033 Workflow Engine pipeline.

A provider-independent engine that turns a `WorkflowDefinition` into a
`WorkflowRunResult`: walks each `WorkflowRequestStep` in order,
dispatches it through the currently selected `WorkflowRunProvider`
(via `WorkflowEngineManager`), and halts the remaining workflow
(reporting SKIPPED) after a failure if
'workflow_engine.stop_on_failure' is enabled -- exactly mirroring
EP-030's `PlanExecutionEngine.execute_plan()` ordering/halting policy,
one level up.

This is Workflow Engine's entire responsibility -- it must NOT call an
AI provider, build a prompt, plan a request itself, or invoke a real
subsystem action directly (that remains, respectively, the
Conversation/Prompt Engine's, EP-029 Planning Engine's, and EP-031
Tool Engine's jobs, all reached transitively -- never directly -- only
through EP-030's `PlanExecutionEngine.execute_request()`).

Depends only on public APIs:
    - `WorkflowEngineManager` (this package) -- current provider,
      failure policy, workflow definition catalog.
    - `PlanExecutionEngine` (EP-030) -- through `execute_request()`
      only.

No AI provider, no Planning Engine, no Tool Engine, no Agent
Framework, no Multi-Agent Collaboration, and no private attribute of
any subsystem is ever accessed here.
"""

from __future__ import annotations

from src.core.plan_execution.plan_execution_engine import PlanExecutionEngine
from src.core.workflow_engine.workflow_definition import WorkflowDefinition
from src.core.workflow_engine.workflow_engine_manager import WorkflowEngineManager
from src.core.workflow_engine.workflow_run_provider import WorkflowEngineError
from src.core.workflow_engine.workflow_run_result import (
    WorkflowRunResult,
    WorkflowStepOutcome,
    WorkflowStepOutcomeStatus,
)

__all__ = [
    "WorkflowEngine",
    "WorkflowRunError",
    "NoWorkflowRunProviderSelectedError",
    "EmptyWorkflowDefinitionError",
    "DisabledWorkflowDefinitionError",
]


class WorkflowRunError(WorkflowEngineError):
    """Base class for errors raised by the WorkflowEngine itself.

    Inherits from `WorkflowEngineError`
    (src/core/workflow_engine/workflow_run_provider.py) so callers can
    catch every Workflow-Engine-related failure -- provider, engine,
    manager, or registry -- with a single exception type.
    """


class NoWorkflowRunProviderSelectedError(WorkflowRunError):
    """Raised when a run is requested but no workflow-run provider is currently selected."""


class EmptyWorkflowDefinitionError(WorkflowRunError):
    """Raised when a `WorkflowDefinition` with no steps is run."""


class DisabledWorkflowDefinitionError(WorkflowRunError):
    """Raised when a `WorkflowDefinition` with `enabled=False` is run."""


class WorkflowEngine:
    """Provider-independent workflow-definition -> multi-step-run pipeline.

    Never selects, constructs, or configures workflow-run providers
    itself -- provider selection and lifecycle are exclusively
    `WorkflowEngineManager`'s concern. Never selects, constructs, or
    configures the Plan Execution Engine itself -- that remains
    exclusively Bootstrap's concern (EP-030). Never dispatches a step
    itself -- that stays inside the active `WorkflowRunProvider`.
    """

    def __init__(self, manager: WorkflowEngineManager, plan_execution_engine: PlanExecutionEngine) -> None:
        """Initialize the WorkflowEngine.

        Args:
            manager: The WorkflowEngineManager used to resolve the
                currently active workflow-run provider, the
                stop-on-failure policy, and the workflow definition
                catalog. Never mutated by this engine.
            plan_execution_engine: The EP-030 PlanExecutionEngine used
                to actually plan and execute each step's request,
                through its public `execute_request()` method only.
                Never mutated by this engine.
        """
        self._manager = manager
        self._plan_execution_engine = plan_execution_engine

    def list_definitions(self) -> list[WorkflowDefinition]:
        """Return every workflow definition currently registered with this engine's manager."""
        return self._manager.registry.list()

    def run(self, definition_id: str) -> WorkflowRunResult:
        """Run an already-registered workflow definition by id.

        Args:
            definition_id: The id of the WorkflowDefinition to run.

        Returns:
            The resulting WorkflowRunResult.

        Raises:
            WorkflowDefinitionNotFoundError: If `definition_id` is not
                registered with this engine's manager.
            EmptyWorkflowDefinitionError: If the definition has no steps.
            DisabledWorkflowDefinitionError: If the definition is disabled.
            NoWorkflowRunProviderSelectedError: If no workflow-run
                provider is currently selected (or the subsystem is
                disabled).
        """
        definition = self._manager.registry.get(definition_id)
        return self.run_definition(definition)

    def run_definition(self, definition: WorkflowDefinition) -> WorkflowRunResult:
        """Run an already-built workflow definition, whether or not it is registered.

        Args:
            definition: The WorkflowDefinition to run.

        Returns:
            The resulting WorkflowRunResult.

        Raises:
            EmptyWorkflowDefinitionError: If `definition` has no steps.
            DisabledWorkflowDefinitionError: If `definition.enabled` is False.
            NoWorkflowRunProviderSelectedError: If no workflow-run
                provider is currently selected (or the subsystem is
                disabled).
        """
        if not definition.steps:
            raise EmptyWorkflowDefinitionError(
                f"Workflow definition '{definition.id}' has no steps."
            )
        if not definition.enabled:
            raise DisabledWorkflowDefinitionError(
                f"Workflow definition '{definition.id}' is disabled."
            )

        provider = self._require_current_provider()
        stop_on_failure = self._manager.stop_on_failure()

        step_outcomes: list[WorkflowStepOutcome] = []
        halted = False
        for step in definition.steps:
            if halted:
                step_outcomes.append(
                    WorkflowStepOutcome(
                        step_name=step.name,
                        status=WorkflowStepOutcomeStatus.SKIPPED,
                        message="Workflow halted after a prior step failed.",
                    )
                )
                continue

            outcome = provider.run_step(step, self._plan_execution_engine.execute_request)
            step_outcomes.append(outcome)
            if outcome.status == WorkflowStepOutcomeStatus.FAILED and stop_on_failure:
                halted = True

        completed_count = sum(
            1 for outcome in step_outcomes if outcome.status == WorkflowStepOutcomeStatus.COMPLETED
        )
        failed_count = sum(
            1 for outcome in step_outcomes if outcome.status == WorkflowStepOutcomeStatus.FAILED
        )
        skipped_count = sum(
            1 for outcome in step_outcomes if outcome.status == WorkflowStepOutcomeStatus.SKIPPED
        )

        return WorkflowRunResult(
            definition_id=definition.id,
            definition_name=definition.name,
            step_outcomes=step_outcomes,
            completed_count=completed_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            success=failed_count == 0,
        )

    # ---------- Internal helpers ----------

    def _require_current_provider(self):
        """Return the currently selected provider, or raise if none is selected.

        Returns:
            The active WorkflowRunProvider.

        Raises:
            NoWorkflowRunProviderSelectedError: If no workflow-run
                provider is currently selected (or the subsystem is
                disabled).
        """
        provider = self._manager.get_current()
        if provider is None:
            raise NoWorkflowRunProviderSelectedError(
                "No workflow-run provider is currently selected. Use 'flow use <provider>'."
            )
        return provider
