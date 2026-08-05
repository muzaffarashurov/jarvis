"""Domain model for EP-030 Plan Execution Engine.

Defines the plain data types shared by `PlanExecutionProvider` (the
actual step-dispatch strategy), `PlanExecutionEngine` (pipeline
orchestration: ordering, availability skipping, failure policy) and
`PlanExecutionService` (the CLI-facing layer): the outcome of a single
step (`StepStatus`, `StepResult`) and the outcome of executing a whole
EP-029 `Plan` (`PlanExecutionResult`). This module owns no dispatch
logic and no failure policy -- it mirrors the role of
`src/core/planning/planning_result.py` relative to
`PlanningProvider`/`PlanningEngine`.

NOTE ON NAMING: this package is named `plan_execution` (not
`execution`) specifically to avoid colliding with the pre-existing,
unrelated `src/core/execution/` package (EP-003's OS-level target
launcher -- `ExecutionEngine.run(raw_target)`, used by Invoice,
Process, Scheduler, Workflow, and Plugin subsystems). The two are
conceptually unrelated: EP-003's engine launches operating-system
processes/scripts/files/URLs; this package dispatches `PlanStep`
instances produced by EP-029's Planning Engine. See
`src/core/plan_execution/__init__.py` for the full disambiguation
note.

Plan Execution Engine performs no AI reasoning and no real tool
invocation (that remains a future Tool Engine's responsibility). This
module has no dependency on any LLM, AI provider, prompt, or
tool-execution component.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.core.planning.planning_result import Plan, PlanStep

__all__ = [
    "StepStatus",
    "StepResult",
    "PlanExecutionResult",
]


class StepStatus(str, Enum):
    """The outcome of dispatching a single `PlanStep`.

    Attributes:
        COMPLETED: The step was dispatched to a recognized action and
            the active `PlanExecutionProvider` reported success. No
            real tool invocation occurs in this Engineering Package --
            "completed" means "successfully dispatched", not "a real
            external effect was produced".
        FAILED: The step was dispatched but the active
            `PlanExecutionProvider` could not carry it out (e.g. its
            action is not one it recognizes).
        SKIPPED: The step was never dispatched to the provider at all
            -- either because it was reported unavailable (see
            `PlanStep.available`), or because a prior step failed and
            the configured failure policy ('plan_execution.stop_on_failure')
            halted the remaining plan.
    """

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class StepResult:
    """The outcome of attempting a single `PlanStep`.

    Attributes:
        step: The `PlanStep` this result corresponds to, unchanged.
        status: The step's outcome.
        message: Human-readable explanation of the outcome.
    """

    step: PlanStep
    status: StepStatus
    message: str


@dataclass(frozen=True)
class PlanExecutionResult:
    """The outcome of a single `PlanExecutionEngine.execute_plan()` call.

    Attributes:
        plan: The `Plan` (EP-029) this result corresponds to, unchanged.
        step_results: One `StepResult` per step in `plan.steps`, in the
            same order.
        completed_count: Number of steps with `StepStatus.COMPLETED`.
        failed_count: Number of steps with `StepStatus.FAILED`.
        skipped_count: Number of steps with `StepStatus.SKIPPED`.
        success: Whether every step reached `StepStatus.COMPLETED` or
            `StepStatus.SKIPPED` (i.e. `failed_count == 0`). A plan
            containing only unavailable steps (all SKIPPED) is still
            considered successful -- nothing was attempted and nothing
            failed.
    """

    plan: Plan
    step_results: list[StepResult] = field(default_factory=list)
    completed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    success: bool = True

    def summary(self) -> str:
        """Return a human-readable, multi-line summary of every step's outcome.

        Returns:
            One line per step, formatted as
            "<order>. [<subsystem or 'none'>] <action> - <status>:
            <message>", in order. Empty string if there are no step
            results (never the case for a `PlanExecutionResult`
            produced by `PlanExecutionEngine`, since `Plan.steps` is
            never empty).
        """
        lines = []
        for result in self.step_results:
            subsystem_label = result.step.subsystem if result.step.subsystem is not None else "none"
            lines.append(
                f"{result.step.order}. [{subsystem_label}] {result.step.action} - "
                f"{result.status.value}: {result.message}"
            )
        return "\n".join(lines)
