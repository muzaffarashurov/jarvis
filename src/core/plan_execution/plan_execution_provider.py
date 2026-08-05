"""PlanExecutionProvider domain model for EP-030 Plan Execution Engine.

Defines the abstraction every step-dispatch strategy must implement so
the rest of Jarvis never needs to know which dispatch strategy is
currently active, matching the pattern already used by the Semantic
Search Provider Framework (`src/core/semantic/semantic_provider.py`),
the Context Compression Provider Framework
(`src/core/context_compression/compression_provider.py`), the Agent
Framework (`src/core/agent/agent_provider.py`), and the Planning
Engine (`src/core/planning/planning_provider.py`).

A future Tool Engine (a later Phase-4 Engineering Package) is the
natural place for a step-dispatch strategy that actually invokes a
real subsystem action -- implementing that here would be out-of-scope
feature creep for EP-030 (it must not perform real tool invocation).
This module resolves the analogous conflict the same way EP-026
through EP-029 did: it implements exactly one concrete, built-in
provider -- `DefaultPlanExecutionProvider`, registered under the
stable name "plan_execution" (matching
'plan_execution.default_provider' in config/config.yaml) -- so the
subsystem is actually usable today, while performing no real tool
invocation.

This module performs no AI reasoning and no real subsystem
invocation: it only recognizes whether a `PlanStep.action` is one of
the fixed set of actions EP-029's `DefaultPlanningProvider` is known
to produce, and reports success or failure accordingly. It never
queries a live subsystem registry itself (that is
`PlanExecutionEngine`'s and its caller's concern, already reflected in
`PlanStep.available` before this provider is ever invoked).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.planning.planning_result import PlanStep
from src.core.plan_execution.plan_execution_result import StepResult, StepStatus

__all__ = [
    "PlanExecutionError",
    "PlanExecutionConfigurationError",
    "PlanExecutionProviderError",
    "PlanExecutionProvider",
    "DefaultPlanExecutionProvider",
]

#: The fixed set of `PlanStep.action` values `DefaultPlanExecutionProvider`
#: recognizes -- exactly the actions EP-029's `DefaultPlanningProvider`
#: keyword-rule table is known to produce (see
#: `src/core/planning/planning_provider.py`'s `_KEYWORD_RULES` and
#: `_FALLBACK_ACTION`). A step whose action is not in this set (e.g.
#: produced by a future, custom `PlanningProvider`) is a genuine,
#: reachable failure -- this provider has nothing registered to carry
#: it out.
_RECOGNIZED_ACTIONS: frozenset[str] = frozenset(
    {
        "retrieve_from_memory",
        "query_knowledge_base",
        "query_long_term_memory",
        "generate_embedding",
        "retrieve_context",
        "semantic_search",
        "compress_context",
        "coordinate_subsystems",
        "acknowledge_request",
    }
)


class PlanExecutionError(Exception):
    """Common root for every exception raised by Plan Execution Engine (EP-030).

    Downstream packages (e.g. a future Tool Engine) can catch this
    single type to handle "anything plan-execution-related" without
    needing to know about every specific failure mode (provider-level,
    engine-level, manager-level, or configuration-level).
    """


class PlanExecutionConfigurationError(PlanExecutionError):
    """Raised when 'plan_execution.*' configuration itself is invalid.

    This is distinct from a provider-level error: it means the
    configuration value itself is malformed (wrong type, empty, or
    references a provider that does not exist) -- restarting with
    corrected configuration is required to resolve it.
    """


class PlanExecutionProviderError(PlanExecutionError):
    """Base class for errors raised while using a plan-execution provider."""


class PlanExecutionProvider(ABC):
    """Structural contract every step-dispatch strategy must implement.

    A provider dispatches a single, already-available `PlanStep` (see
    `PlanExecutionEngine.execute_plan()`, which never calls this for a
    step whose `available` flag is False, or after a prior failure has
    halted the plan) -- it never decides whether a step *should* run
    (that stays inside `PlanExecutionEngine`), never performs AI
    reasoning, and never invokes a real subsystem action.
    `is_available()` must never perform network requests or expensive
    work, matching `CompressionProvider`'s convention.
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return this provider's stable identifier (e.g. "plan_execution")."""
        raise NotImplementedError

    @abstractmethod
    def execute_step(self, step: PlanStep) -> StepResult:
        """Dispatch a single, already-available `PlanStep`.

        Args:
            step: The step to dispatch. Callers only ever pass a step
                with `available=True` -- availability is decided by
                `PlanExecutionEngine`, never by this method.

        Returns:
            The resulting StepResult (`status` is always `COMPLETED`
            or `FAILED` -- never `SKIPPED`; skipping is decided by
            `PlanExecutionEngine`, before a provider is ever called).
        """
        raise NotImplementedError

    # ---------- Lifecycle / diagnostics extension point ----------

    def is_available(self) -> bool:
        """Return whether this provider is currently able to dispatch steps.

        Base implementation always returns True. Providers with an
        enabled/configured distinction should override this method.
        """
        return True


class DefaultPlanExecutionProvider(PlanExecutionProvider):
    """Built-in plan-execution provider: recognized-action dispatch only.

    Registered by `PlanExecutionManager` under the name
    "plan_execution" (see 'plan_execution.default_provider' in
    config/config.yaml). Performs a deterministic, honest check -- no
    AI reasoning, no network access, and no real subsystem invocation:

        - If `step.action` is one of the actions EP-029's
          `DefaultPlanningProvider` is known to produce, the step is
          reported COMPLETED: it was successfully dispatched, but no
          Tool Engine exists yet to actually carry it out (a future
          Engineering Package).
        - Otherwise, the step is reported FAILED: this provider has no
          executor registered for an action it does not recognize.
    """

    _NAME: str = "plan_execution"

    def provider_name(self) -> str:
        """Return this provider's stable identifier: "plan_execution"."""
        return self._NAME

    def execute_step(self, step: PlanStep) -> StepResult:
        """Dispatch `step` if its action is recognized; otherwise report failure.

        Args:
            step: The step to dispatch (always supplied with
                `available=True` by `PlanExecutionEngine`).

        Returns:
            A StepResult with `status=COMPLETED` if `step.action` is
            recognized, `status=FAILED` otherwise.
        """
        if step.action in _RECOGNIZED_ACTIONS:
            return StepResult(
                step=step,
                status=StepStatus.COMPLETED,
                message=(
                    f"Step '{step.action}' dispatched. No Tool Engine is registered yet "
                    "(future EP); Plan Execution Engine performed no real tool invocation."
                ),
            )

        return StepResult(
            step=step,
            status=StepStatus.FAILED,
            message=f"No executor registered for action '{step.action}'.",
        )

