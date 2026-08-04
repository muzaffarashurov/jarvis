"""EP-029 Planning Engine.

A provider-independent engine that turns a request into an ordered
`Plan`: delegates the actual decomposition to the currently selected
`PlanningProvider` (via `PlanningManager`), then -- if an EP-028
`AgentEngine` was supplied -- reconciles each step's `available` flag
against that agent's live subsystem registry (public
`list_subsystems()` method only). This is Planning Engine's entire
responsibility -- it must NOT call an AI provider, build a prompt,
execute a step, retrieve or rank context, or reason beyond the fixed
keyword rules already applied by the active `PlanningProvider` (see
`src/core/planning/__init__.py`).

Depends only on public APIs:
    - `PlanningManager` (this package) -- current provider and default
      `max_steps`.
    - `AgentEngine` (EP-028, optional) -- `list_subsystems()`, used
      solely to refine an already-built `Plan`'s per-step availability.
      `SubsystemInfo` (EP-028) is read only through its public fields
      (`name`, `available`).

No AI provider, no prompt engine, no execution engine, no reflection,
no tool executor, and no private attribute of any of the above is ever
accessed (only their public methods/fields).
"""

from __future__ import annotations

from src.core.agent.agent_engine import AgentEngine, AgentEngineError
from src.core.agent.agent_provider import AgentProviderError
from src.core.planning.planning_manager import PlanningManager
from src.core.planning.planning_provider import PlanningError
from src.core.planning.planning_result import Plan, PlanStep

__all__ = [
    "PlanningEngine",
    "PlanningEngineError",
    "NoPlanningProviderSelectedError",
    "EmptyPlanningRequestError",
]


class PlanningEngineError(PlanningError):
    """Base class for errors raised by the PlanningEngine itself.

    Inherits from `PlanningError`
    (src/core/planning/planning_provider.py) so callers can catch
    every Planning-Engine-related failure -- provider, engine, or
    manager -- with a single exception type.
    """


class NoPlanningProviderSelectedError(PlanningEngineError):
    """Raised when planning is requested but no provider is currently selected."""


class EmptyPlanningRequestError(PlanningEngineError):
    """Raised when `plan()` is called with an empty/whitespace-only request."""


class PlanningEngine:
    """Provider-independent request -> Plan pipeline.

    Pipeline for `plan()`:

        request -> PlanningProvider.plan() -> Plan (every step available=True)
                -> (if an AgentEngine was supplied) reconcile each
                   step's `available` flag against
                   AgentEngine.list_subsystems() -> final Plan

    Never selects, constructs, or configures providers itself --
    provider selection and lifecycle are exclusively
    `PlanningManager`'s concern. Never applies keyword rules or any
    other decomposition logic itself -- that stays inside the active
    `PlanningProvider`.
    """

    def __init__(self, manager: PlanningManager, agent_engine: AgentEngine | None = None) -> None:
        """Initialize the PlanningEngine.

        Args:
            manager: The PlanningManager used to resolve the currently
                active provider and the default `max_steps` limit.
                Never mutated by this engine.
            agent_engine: The AgentEngine (EP-028) used only to
                reconcile a built plan's per-step subsystem
                availability against a live subsystem registry, via
                its public `list_subsystems()` method. Optional: if
                None, every step's `available` flag from the active
                `PlanningProvider` is left unchanged (always True,
                except for the fallback step's `subsystem=None`, which
                is also always True).
        """
        self._manager = manager
        self._agent_engine = agent_engine

    def plan(self, request: str) -> Plan:
        """Decompose `request` into an ordered `Plan`.

        Args:
            request: The request text to decompose.

        Returns:
            The resulting Plan, with per-step availability reconciled
            against a live subsystem registry if this engine was
            constructed with an `AgentEngine`.

        Raises:
            EmptyPlanningRequestError: If `request` is empty or
                whitespace-only.
            NoPlanningProviderSelectedError: If no planning provider is
                currently selected (or the subsystem is disabled).
            PlanningProviderError: If the active provider itself fails
                to plan (e.g. an invalid configured limit).
        """
        if not request or not request.strip():
            raise EmptyPlanningRequestError("Planning Engine request must not be empty.")

        provider = self._require_current_provider()
        built_plan = provider.plan(request, max_steps=self._manager.max_steps())

        if self._agent_engine is None:
            return built_plan

        return self._reconcile_availability(built_plan)

    # ---------- Internal helpers ----------

    def _reconcile_availability(self, built_plan: Plan) -> Plan:
        """Refine `built_plan`'s per-step `available` flag against the live subsystem registry.

        Args:
            built_plan: The plan produced by the active
                `PlanningProvider`, with every step's `available`
                currently True.

        Returns:
            A new Plan with the same request/step_count/truncated
            values, but with each step's `available` flag set to:
            True when `subsystem` is None; the matching
            `SubsystemInfo.available` when the step's subsystem is
            registered with the current agent; False when the step's
            subsystem is not registered with the current agent.

        Raises:
            PlanningEngineError: If listing subsystems from the
                AgentEngine itself fails.
        """
        try:
            subsystems = self._agent_engine.list_subsystems()
        except (AgentEngineError, AgentProviderError) as exc:
            raise PlanningEngineError(
                f"Planning Engine could not read the Agent Framework's subsystem registry: {exc}"
            ) from exc

        availability_by_name = {info.name: info.available for info in subsystems}

        reconciled_steps = [
            PlanStep(
                order=step.order,
                subsystem=step.subsystem,
                action=step.action,
                description=step.description,
                available=(
                    True if step.subsystem is None else availability_by_name.get(step.subsystem, False)
                ),
            )
            for step in built_plan.steps
        ]

        return Plan(
            request=built_plan.request,
            steps=reconciled_steps,
            step_count=built_plan.step_count,
            truncated=built_plan.truncated,
        )

    def _require_current_provider(self):
        """Return the currently selected provider, or raise if none is selected.

        Returns:
            The active PlanningProvider.

        Raises:
            NoPlanningProviderSelectedError: If no planning provider is
                currently selected (or the subsystem is disabled).
        """
        provider = self._manager.get_current()
        if provider is None:
            raise NoPlanningProviderSelectedError(
                "No planning provider is currently selected. Use 'planning use <provider>'."
            )
        return provider
