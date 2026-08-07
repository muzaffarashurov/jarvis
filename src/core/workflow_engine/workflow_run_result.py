"""Result model for EP-033 Workflow Engine.

Defines the plain data types shared by `WorkflowRunProvider` (the
per-step dispatch strategy), `WorkflowEngine` (pipeline orchestration:
ordering, failure policy) and `WorkflowEngineService` (the CLI-facing
layer): the outcome of a single step (`WorkflowStepOutcomeStatus`,
`WorkflowStepOutcome`) and the outcome of running a whole
`WorkflowDefinition` (`WorkflowRunResult`). This module owns no
dispatch logic and no failure policy -- it mirrors the role of
`src/core/plan_execution/plan_execution_result.py` relative to
`PlanExecutionProvider`/`PlanExecutionEngine`, one level up: each
`WorkflowStepOutcome` wraps the `PlanExecutionResult` (EP-030) that
running its step actually produced.

Workflow Engine performs no AI reasoning and no direct real-subsystem
invocation of its own (that happens transitively, inside EP-030's
`PlanExecutionEngine.execute_request()`, which this package only
calls). This module has no dependency on any LLM, AI provider, or
prompt component.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.core.plan_execution.plan_execution_result import PlanExecutionResult

__all__ = [
    "WorkflowStepOutcomeStatus",
    "WorkflowStepOutcome",
    "WorkflowRunResult",
]


class WorkflowStepOutcomeStatus(str, Enum):
    """The outcome of running a single `WorkflowRequestStep`.

    Attributes:
        COMPLETED: The step's request was planned and executed (via
            EP-030's `PlanExecutionEngine.execute_request()`) and the
            resulting `PlanExecutionResult.success` was True.
        FAILED: The step's request was planned and executed but the
            resulting `PlanExecutionResult.success` was False, or
            planning/execution itself raised an exception (caught and
            translated here -- see `DefaultWorkflowRunProvider`).
        SKIPPED: The step was never dispatched at all -- a prior step
            failed and the configured failure policy
            ('workflow_engine.stop_on_failure') halted the remaining
            workflow.
    """

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class WorkflowStepOutcome:
    """The outcome of attempting a single `WorkflowRequestStep`.

    Attributes:
        step_name: The `WorkflowRequestStep.name` this result
            corresponds to, unchanged.
        status: The step's outcome.
        message: Human-readable explanation of the outcome.
        plan_execution_result: The `PlanExecutionResult` (EP-030)
            produced by actually running this step's request, or None
            if the step was never dispatched (`status == SKIPPED`).
    """

    step_name: str
    status: WorkflowStepOutcomeStatus
    message: str
    plan_execution_result: PlanExecutionResult | None = None


@dataclass(frozen=True)
class WorkflowRunResult:
    """The outcome of a single `WorkflowEngine.run()` / `run_definition()` call.

    Attributes:
        definition_id: The `WorkflowDefinition.id` this result
            corresponds to, unchanged.
        definition_name: The `WorkflowDefinition.name` this result
            corresponds to, unchanged.
        step_outcomes: One `WorkflowStepOutcome` per step in
            `definition.steps`, in the same order.
        completed_count: Number of steps with
            `WorkflowStepOutcomeStatus.COMPLETED`.
        failed_count: Number of steps with
            `WorkflowStepOutcomeStatus.FAILED`.
        skipped_count: Number of steps with
            `WorkflowStepOutcomeStatus.SKIPPED`.
        success: Whether every step reached `COMPLETED` or `SKIPPED`
            (i.e. `failed_count == 0`).
    """

    definition_id: str
    definition_name: str
    step_outcomes: list[WorkflowStepOutcome] = field(default_factory=list)
    completed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    success: bool = True

    def summary(self) -> str:
        """Return a human-readable, multi-line summary of every step's outcome.

        Returns:
            One line per step outcome, formatted as
            "<step_name> - <status>: <message>", in order. Empty
            string if there are no step outcomes.
        """
        lines = []
        for outcome in self.step_outcomes:
            lines.append(f"{outcome.step_name} - {outcome.status.value}: {outcome.message}")
        return "\n".join(lines)
