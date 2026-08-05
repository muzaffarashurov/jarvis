"""ToolExecutionProvider: the EP-030-anticipated Tool-Engine-backed provider.

This is the bridge -- and the *only* file in this project that
imports from both `src.core.tool` and `src.core.plan_execution` --
that satisfies the extension point EP-030 explicitly left open for a
future Tool Engine:

    - `src/core/plan_execution/plan_execution_provider.py`: "A future
      Tool Engine (a later Phase-4 Engineering Package) is the
      natural place for a step-dispatch strategy that actually
      invokes a real subsystem action."
    - `src/core/plan_execution/plan_execution_manager.py`: "New
      provider types (e.g. a future Tool-Engine-backed provider) can
      be added at runtime via `register_provider()` without modifying
      this class."

`ToolExecutionProvider` implements EP-030's `PlanExecutionProvider`
ABC. It performs no dispatch-order logic, no failure-policy logic, and
no plan walking itself (all of that remains `PlanExecutionEngine`'s
responsibility, unchanged) -- it only translates a single, already-
available `PlanStep` into a `ToolEngine.invoke_for_step()` call, and
maps the resulting `ToolResult` back into EP-030's `StepResult`/
`StepStatus` vocabulary.

Registering an instance of this class with `PlanExecutionManager` (via
its existing, public `register_provider()`) is the only way this
bridge becomes reachable -- see `src/bootstrap.py`'s EP-031 wiring
block. `src/core/plan_execution/` itself is never modified.
"""

from __future__ import annotations

from src.core.plan_execution.plan_execution_provider import PlanExecutionProvider
from src.core.plan_execution.plan_execution_result import StepResult, StepStatus
from src.core.planning.planning_result import PlanStep
from src.core.tool.tool_engine import NoToolProviderSelectedError, ToolEngine
from src.core.tool.tool_result import ToolStatus

__all__ = ["ToolExecutionProvider"]


class ToolExecutionProvider(PlanExecutionProvider):
    """Plan-execution provider backed by EP-031's Tool Engine.

    Registered by `src/bootstrap.py` with `PlanExecutionManager` under
    the name "tool_engine" (matching `ToolEngine`'s own provider name,
    for operator clarity when running `execution providers`). NOT
    selected as the default plan-execution provider automatically --
    `plan_execution.default_provider` in config/config.yaml remains
    "plan_execution" unless an operator explicitly runs
    `execution use tool_engine`, preserving EP-030's exact default
    behavior (backward compatibility).
    """

    _NAME: str = "tool_engine"

    def __init__(self, tool_engine: ToolEngine) -> None:
        """Initialize the ToolExecutionProvider.

        Args:
            tool_engine: The ToolEngine (EP-031) used to resolve and
                invoke a real tool for a given `PlanStep`.
        """
        self._tool_engine = tool_engine

    def provider_name(self) -> str:
        """Return this provider's stable identifier: "tool_engine"."""
        return self._NAME

    def is_available(self) -> bool:
        """Return whether Tool Engine currently has a provider selected.

        Returns:
            True if `ToolEngine`'s own provider is available for
            invocation (mirrors `ToolManager.is_enabled()` plus a
            current-provider selection); False otherwise.
        """
        try:
            # A cheap, side-effect-free probe: listing tools never
            # invokes anything and never raises.
            self._tool_engine.list_tools()
        except Exception:  # noqa: BLE001 - is_available() must never raise
            return False
        return True

    def execute_step(self, step: PlanStep) -> StepResult:
        """Dispatch a single, already-available `PlanStep` to a real tool invocation.

        Args:
            step: The step to dispatch (always supplied with
                `available=True` by `PlanExecutionEngine`).

        Returns:
            A StepResult with `status=COMPLETED` if a matching tool
            was found and invoked successfully, `status=FAILED`
            otherwise (no matching tool registered, or the tool's
            handler failed) -- never `SKIPPED`; skipping remains
            `PlanExecutionEngine`'s decision, made before this
            provider is ever called.
        """
        try:
            tool_result = self._tool_engine.invoke_for_step(step.subsystem, step.action)
        except NoToolProviderSelectedError as exc:
            return StepResult(step=step, status=StepStatus.FAILED, message=str(exc))

        status = (
            StepStatus.COMPLETED if tool_result.status == ToolStatus.COMPLETED else StepStatus.FAILED
        )
        return StepResult(step=step, status=status, message=tool_result.message)
