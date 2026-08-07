"""WorkflowRunProvider domain model for EP-033 Workflow Engine.

Defines the abstraction every workflow-step dispatch strategy must
implement so the rest of Jarvis never needs to know which dispatch
strategy is currently active, matching the pattern already used by the
Planning Engine (`src/core/planning/planning_provider.py`), the Plan
Execution Engine (`src/core/plan_execution/plan_execution_provider.py`),
the Tool Engine (`src/core/tool/tool_provider.py`), and Multi-Agent
Collaboration (`src/core/collaboration/collaboration_provider.py`).

Implements exactly one concrete, built-in provider --
`DefaultWorkflowRunProvider`, registered under the stable name
"workflow_engine" (matching 'workflow_engine.default_provider' in
config/config.yaml) -- which dispatches a single
`WorkflowRequestStep`'s request through a caller-supplied `executor`
callable (bound by `WorkflowEngine` to EP-030's
`PlanExecutionEngine.execute_request()`, never imported directly here)
and translates the resulting `PlanExecutionResult` into a
`WorkflowStepOutcome`.

This module performs no AI reasoning and no direct real-subsystem
invocation of its own: it only calls the `executor` callable it is
given and reports what came back. It never queries `PlanExecutionEngine`
or `PlanningEngine` directly, and never decides whether a step *should*
run (ordering and the stop-on-failure policy stay inside `WorkflowEngine`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from loguru import logger

from src.core.plan_execution.plan_execution_result import PlanExecutionResult
from src.core.workflow_engine.workflow_definition import WorkflowRequestStep
from src.core.workflow_engine.workflow_run_result import WorkflowStepOutcome, WorkflowStepOutcomeStatus

__all__ = [
    "WorkflowEngineError",
    "WorkflowEngineConfigurationError",
    "WorkflowRunProviderError",
    "WorkflowRunProvider",
    "DefaultWorkflowRunProvider",
]


class WorkflowEngineError(Exception):
    """Common root for every exception raised by Workflow Engine (EP-033).

    Downstream callers can catch this single type to handle "anything
    workflow-engine-related" without needing to know about every
    specific failure mode (provider-level, engine-level,
    manager-level, registry-level, or configuration-level).
    """


class WorkflowEngineConfigurationError(WorkflowEngineError):
    """Raised when 'workflow_engine.*' configuration itself is invalid.

    This is distinct from a provider-level error: it means the
    configuration value itself is malformed (wrong type, empty, or
    references a provider that does not exist) -- restarting with
    corrected configuration is required to resolve it.
    """


class WorkflowRunProviderError(WorkflowEngineError):
    """Base class for errors raised while using a workflow-run provider."""


class WorkflowRunProvider(ABC):
    """Structural contract every workflow-step dispatch strategy must implement.

    A provider dispatches a single `WorkflowRequestStep` -- it never
    decides whether a step *should* run (ordering and the
    'workflow_engine.stop_on_failure' policy stay inside
    `WorkflowEngine`), never performs AI reasoning, and never imports
    or holds a reference to `PlanExecutionEngine`/`PlanningEngine`
    itself -- the caller-supplied `executor` callable is its only
    route to running a step's request. `is_available()` must never
    perform network requests or expensive work, matching
    `CollaborationProvider`'s convention.
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return this provider's stable identifier (e.g. "workflow_engine")."""
        raise NotImplementedError

    @abstractmethod
    def run_step(
        self, step: WorkflowRequestStep, executor: Callable[[str], PlanExecutionResult]
    ) -> WorkflowStepOutcome:
        """Dispatch a single `WorkflowRequestStep` through `executor`.

        Args:
            step: The step to dispatch. Callers only ever pass a step
                that has not been skipped -- skip decisions belong to
                `WorkflowEngine`, never to this method.
            executor: A callable that plans and executes a single
                request, returning its `PlanExecutionResult` (bound by
                `WorkflowEngine` to
                `PlanExecutionEngine.execute_request()`). May raise;
                implementations must catch and translate any exception
                into a FAILED outcome rather than letting it propagate.

        Returns:
            The resulting WorkflowStepOutcome (`status` is always
            `COMPLETED` or `FAILED` -- never `SKIPPED`; skipping is
            decided by `WorkflowEngine`, before a provider is ever
            called).
        """
        raise NotImplementedError

    # ---------- Lifecycle / diagnostics extension point ----------

    def is_available(self) -> bool:
        """Return whether this provider is currently able to dispatch steps.

        Base implementation always returns True. Providers with an
        enabled/configured distinction should override this method.
        """
        return True


class DefaultWorkflowRunProvider(WorkflowRunProvider):
    """Built-in workflow-run provider: calls `executor`, translates the result.

    Registered by `WorkflowEngineManager` under the name
    "workflow_engine" (see 'workflow_engine.default_provider' in
    config/config.yaml). Performs a deterministic, honest translation
    -- no AI reasoning, no network access, no direct subsystem
    invocation:

        - Calls `executor(step.request)`.
        - If it raises, the step is reported FAILED (the exception is
          never allowed to propagate -- its message is preserved in
          `WorkflowStepOutcome.message` and it is logged).
        - Otherwise, the step is reported COMPLETED if the resulting
          `PlanExecutionResult.success` is True, FAILED otherwise --
          the underlying `PlanExecutionResult` is always attached to
          the outcome either way.
    """

    _NAME: str = "workflow_engine"

    def provider_name(self) -> str:
        """Return this provider's stable identifier: "workflow_engine"."""
        return self._NAME

    def run_step(
        self, step: WorkflowRequestStep, executor: Callable[[str], PlanExecutionResult]
    ) -> WorkflowStepOutcome:
        """Dispatch `step` via `executor`, translating the outcome.

        Args:
            step: The step to dispatch.
            executor: Callable that plans and executes a single
                request, returning its PlanExecutionResult.

        Returns:
            The resulting WorkflowStepOutcome -- never raises.
        """
        try:
            result = executor(step.request)
        except Exception as exc:  # noqa: BLE001 - translated, never swallowed
            logger.warning(f"Workflow step '{step.name}' raised during execution: {exc}")
            return WorkflowStepOutcome(
                step_name=step.name,
                status=WorkflowStepOutcomeStatus.FAILED,
                message=f"Step '{step.name}' failed: {exc}",
                plan_execution_result=None,
            )

        status = (
            WorkflowStepOutcomeStatus.COMPLETED
            if result.success
            else WorkflowStepOutcomeStatus.FAILED
        )
        outcome_label = "succeeded" if result.success else "failed"
        message = (
            f"Plan execution {outcome_label} "
            f"({result.completed_count} completed, {result.failed_count} failed, "
            f"{result.skipped_count} skipped)."
        )
        return WorkflowStepOutcome(
            step_name=step.name,
            status=status,
            message=message,
            plan_execution_result=result,
        )
