"""EP-030 Plan Execution Engine.

A provider-independent engine that turns an EP-029 `Plan` into actual
work -- or, more precisely, into *dispatched* work: walks a plan's
steps in order, skips any step already reported unavailable (see
`PlanStep.available`), dispatches every other step to the currently
selected `PlanExecutionProvider`, and halts the remaining plan (each
remaining step reported `SKIPPED`) after a step fails, if
'plan_execution.stop_on_failure' is enabled. This is Plan Execution
Engine's entire responsibility -- it must NOT call an AI provider,
build a prompt, invoke a real subsystem action (that remains a future
Tool Engine's responsibility), or re-plan (see
`src/core/plan_execution/__init__.py`).

Depends only on public APIs:
    - `PlanExecutionManager` (this package) -- current provider and
      the default `stop_on_failure` policy.
    - `PlanningEngine` (EP-029, optional) -- `plan()`, used solely by
      `execute_request()` to let a caller plan-and-execute a request in
      one call. `Plan`/`PlanStep` (EP-029) are read only through their
      public fields.

No AI provider, no prompt engine, no Tool Engine, no reflection, and
no private attribute of any of the above is ever accessed (only their
public methods/fields).
"""

from __future__ import annotations

from src.core.plan_execution.plan_execution_manager import PlanExecutionManager
from src.core.plan_execution.plan_execution_provider import PlanExecutionError
from src.core.plan_execution.plan_execution_result import PlanExecutionResult, StepResult, StepStatus
from src.core.planning.planning_engine import PlanningEngine, PlanningEngineError
from src.core.planning.planning_provider import PlanningProviderError
from src.core.planning.planning_result import Plan

__all__ = [
    "PlanExecutionEngine",
    "PlanExecutionEngineError",
    "NoPlanExecutionProviderSelectedError",
    "EmptyPlanError",
    "PlanningEngineUnavailableError",
]


class PlanExecutionEngineError(PlanExecutionError):
    """Base class for errors raised by the PlanExecutionEngine itself.

    Inherits from `PlanExecutionError`
    (src/core/plan_execution/plan_execution_provider.py) so callers
    can catch every Plan-Execution-related failure -- provider,
    engine, or manager -- with a single exception type.
    """


class NoPlanExecutionProviderSelectedError(PlanExecutionEngineError):
    """Raised when execution is requested but no provider is currently selected."""


class EmptyPlanError(PlanExecutionEngineError):
    """Raised when `execute_plan()` is called with a plan that has no steps."""


class PlanningEngineUnavailableError(PlanExecutionEngineError):
    """Raised when `execute_request()` is called without a PlanningEngine configured."""


class PlanExecutionEngine:
    """Provider-independent plan -> dispatched-work pipeline.

    Pipeline for `execute_plan()`:

        Plan -> for each step, in order:
                    unavailable?      -> SKIPPED (never dispatched)
                    halted by policy? -> SKIPPED (never dispatched)
                    otherwise         -> PlanExecutionProvider.execute_step()
             -> PlanExecutionResult

    Pipeline for `execute_request()`:

        request -> PlanningEngine.plan() -> Plan -> execute_plan() -> PlanExecutionResult

    Never selects, constructs, or configures providers itself --
    provider selection and lifecycle are exclusively
    `PlanExecutionManager`'s concern. Never dispatches a step itself --
    that stays inside the active `PlanExecutionProvider`. Never
    decomposes a request into a plan itself -- that stays inside
    `PlanningEngine` (EP-029).
    """

    def __init__(
        self,
        manager: PlanExecutionManager,
        planning_engine: PlanningEngine | None = None,
    ) -> None:
        """Initialize the PlanExecutionEngine.

        Args:
            manager: The PlanExecutionManager used to resolve the
                currently active provider and the default
                `stop_on_failure` policy. Never mutated by this engine.
            planning_engine: The PlanningEngine (EP-029) used only by
                `execute_request()` to plan a request before executing
                it. Optional: if None, `execute_request()` raises
                `PlanningEngineUnavailableError` -- `execute_plan()`
                still functions normally either way.
        """
        self._manager = manager
        self._planning_engine = planning_engine

    def execute_plan(self, plan: Plan) -> PlanExecutionResult:
        """Dispatch every available step of `plan`, in `plan.steps` list order.

        Steps are processed in the order they appear in `plan.steps`
        -- this engine does not re-sort by `PlanStep.order`. EP-029's
        `PlanningEngine`/`PlanningProvider` guarantee `plan.steps` is
        already ordered consistently with each step's `order` field, so
        this is equivalent in practice; a custom `PlanningProvider`
        that violated that guarantee (a list out of sync with `order`)
        would have its steps dispatched in list order, not `order`
        order.

        Args:
            plan: The Plan (EP-029) to execute.

        Returns:
            The resulting PlanExecutionResult.

        Raises:
            EmptyPlanError: If `plan.steps` is empty.
            NoPlanExecutionProviderSelectedError: If no plan-execution
                provider is currently selected (or the subsystem is
                disabled).
        """
        if not plan.steps:
            raise EmptyPlanError("Plan Execution Engine requires a plan with at least one step.")

        provider = self._require_current_provider()
        stop_on_failure = self._manager.stop_on_failure()

        step_results: list[StepResult] = []
        halted = False

        for step in plan.steps:
            if halted:
                step_results.append(
                    StepResult(
                        step=step,
                        status=StepStatus.SKIPPED,
                        message="Execution halted after a prior step failed.",
                    )
                )
                continue

            if not step.available:
                step_results.append(
                    StepResult(
                        step=step,
                        status=StepStatus.SKIPPED,
                        message=(
                            f"Subsystem '{step.subsystem}' is not available."
                            if step.subsystem is not None
                            else "Step has no associated subsystem to check."
                        ),
                    )
                )
                continue

            result = provider.execute_step(step)
            step_results.append(result)
            if result.status == StepStatus.FAILED and stop_on_failure:
                halted = True

        completed_count = sum(1 for r in step_results if r.status == StepStatus.COMPLETED)
        failed_count = sum(1 for r in step_results if r.status == StepStatus.FAILED)
        skipped_count = sum(1 for r in step_results if r.status == StepStatus.SKIPPED)

        return PlanExecutionResult(
            plan=plan,
            step_results=step_results,
            completed_count=completed_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            success=(failed_count == 0),
        )

    def execute_request(self, request: str) -> PlanExecutionResult:
        """Plan `request` (via EP-029), then execute the resulting plan.

        Args:
            request: The request text, forwarded unchanged to
                `PlanningEngine.plan()`.

        Returns:
            The resulting PlanExecutionResult.

        Raises:
            PlanningEngineUnavailableError: If no PlanningEngine was
                configured for this PlanExecutionEngine.
            PlanExecutionEngineError: If planning `request` itself fails.
            EmptyPlanError: If `plan.steps` is empty (never the case
                for a plan produced by EP-029's `PlanningEngine`).
            NoPlanExecutionProviderSelectedError: If no plan-execution
                provider is currently selected (or the subsystem is
                disabled).
        """
        if self._planning_engine is None:
            raise PlanningEngineUnavailableError(
                "Plan Execution Engine was not configured with a PlanningEngine; "
                "use execute_plan() instead."
            )

        try:
            plan = self._planning_engine.plan(request)
        except (PlanningEngineError, PlanningProviderError) as exc:
            raise PlanExecutionEngineError(f"Plan Execution Engine planning failed: {exc}") from exc

        return self.execute_plan(plan)

    # ---------- Internal helpers ----------

    def _require_current_provider(self):
        """Return the currently selected provider, or raise if none is selected.

        Returns:
            The active PlanExecutionProvider.

        Raises:
            NoPlanExecutionProviderSelectedError: If no plan-execution
                provider is currently selected (or the subsystem is
                disabled).
        """
        provider = self._manager.get_current()
        if provider is None:
            raise NoPlanExecutionProviderSelectedError(
                "No plan-execution provider is currently selected. "
                "Use 'execution use <provider>'."
            )
        return provider
