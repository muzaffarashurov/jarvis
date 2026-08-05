"""Business logic for EP-030 Plan Execution Engine CLI integration.

PlanExecutionService is a thin, CLI-facing wrapper around
PlanExecutionEngine and PlanExecutionManager. It owns no dispatch logic
or failure-policy logic itself -- provider selection and the default
`stop_on_failure` policy stay inside PlanExecutionManager, and
plan-walking/dispatch orchestration stays inside
PlanExecutionEngine/PlanExecutionProvider; this service only forwards
calls to them and adapts the results to dataclasses/CommandResult for
PlanExecutionModule, matching every other Service in this project (see
src/services/planning_service.py's PlanningService -> PlanningEngine
pattern):

    PlanExecutionModule -> PlanExecutionService -> PlanExecutionEngine -> PlanExecutionManager

It implements no business logic belonging to any other module and
never imports from src.core.rag, src.core.ai, or src.core.execution
(the pre-existing, unrelated OS-level launcher from EP-003 -- see
src/core/plan_execution/__init__.py's naming-disambiguation note).
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.command_router import CommandResult
from src.core.plan_execution.plan_execution_engine import PlanExecutionEngine, PlanExecutionEngineError
from src.core.plan_execution.plan_execution_manager import (
    PlanExecutionManager,
    PlanExecutionProviderNotFoundError,
)
from src.core.plan_execution.plan_execution_provider import (
    PlanExecutionConfigurationError,
    PlanExecutionProviderError,
)
from src.core.plan_execution.plan_execution_result import PlanExecutionResult


@dataclass(frozen=True)
class PlanExecutionStatus:
    """Result of `execution status`.

    Attributes:
        enabled: Whether the Plan Execution Engine subsystem is
            currently enabled.
        current_provider: The currently selected provider's name, or
            None if no provider is selected.
        registered_provider_count: Number of providers registered with
            the PlanExecutionManager.
        stop_on_failure: Whether execution halts the remaining plan
            after a step fails.
    """

    enabled: bool
    current_provider: str | None
    registered_provider_count: int
    stop_on_failure: bool


@dataclass(frozen=True)
class PlanExecutionProviderInfo:
    """One row of `execution providers` output.

    Attributes:
        name: The provider's registered name.
        available: Whether the provider is enabled and fully configured.
        is_current: Whether this is the currently selected provider.
    """

    name: str
    available: bool
    is_current: bool


@dataclass(frozen=True)
class ProviderSelectionResult:
    """Result of `execution use <provider>`.

    Attributes:
        success: Whether the provider was successfully selected.
        provider: The requested provider name.
        message: Human-readable outcome summary.
    """

    success: bool
    provider: str
    message: str


@dataclass(frozen=True)
class RunOutcome:
    """Result of `execution run "<request>"`.

    Attributes:
        success: Whether planning and execution both completed without
            an infrastructure-level error (this is independent of
            whether individual steps succeeded -- see
            `PlanExecutionResult.success` for that).
        request: The request text that was planned and executed.
        result: The resulting PlanExecutionResult, or None on failure.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    request: str
    result: PlanExecutionResult | None
    error: str


class PlanExecutionService:
    """Coordinates PlanExecutionEngine/PlanExecutionManager and exposes them as a CLI-friendly API.

    Depends only on PlanExecutionEngine and PlanExecutionManager
    (EP-030). Implements no dispatch or failure-policy logic of its
    own -- every call is forwarded unchanged; this class only adapts
    return values to dataclasses/CommandResult for
    PlanExecutionModule.
    """

    def __init__(self, manager: PlanExecutionManager, engine: PlanExecutionEngine) -> None:
        """Initialize the PlanExecutionService.

        Args:
            manager: The PlanExecutionManager this service reports on
                and selects providers through.
            engine: The PlanExecutionEngine this service requests
                execution through.
        """
        self._manager = manager
        self._engine = engine

    def status(self) -> PlanExecutionStatus:
        """Return the Plan Execution Engine subsystem's overall status."""
        return PlanExecutionStatus(
            enabled=self._manager.is_enabled(),
            current_provider=self._manager.current_provider_name(),
            registered_provider_count=len(self._manager.list_providers()),
            stop_on_failure=self._manager.stop_on_failure(),
        )

    def list_providers(self) -> list[PlanExecutionProviderInfo]:
        """List every registered plan-execution provider and its diagnostic flags."""
        current_name = self._manager.current_provider_name()
        return [
            PlanExecutionProviderInfo(
                name=provider.provider_name(),
                available=provider.is_available(),
                is_current=provider.provider_name() == current_name,
            )
            for provider in self._manager.list_providers()
        ]

    def use_provider(self, name: str) -> ProviderSelectionResult:
        """Select a plan-execution provider as the currently active provider.

        Args:
            name: The registered provider name to activate.

        Returns:
            A ProviderSelectionResult reflecting whether `name` was
            selected.
        """
        try:
            self._manager.set_current(name)
        except PlanExecutionProviderNotFoundError as exc:
            return ProviderSelectionResult(success=False, provider=name, message=str(exc))

        return ProviderSelectionResult(
            success=True, provider=name, message=f"Plan-execution provider set to '{name}'."
        )

    def disable(self) -> CommandResult:
        """Disable the Plan Execution Engine subsystem."""
        self._manager.disable()
        return CommandResult(success=True, message="Plan Execution Engine subsystem disabled.")

    def run(self, request: str) -> RunOutcome:
        """Plan `request` (via EP-029) and execute the resulting plan.

        Args:
            request: The request text to plan and execute.

        Returns:
            A RunOutcome describing the outcome.
        """
        try:
            result = self._engine.execute_request(request)
        except (PlanExecutionEngineError, PlanExecutionProviderError) as exc:
            logger.error(f"Plan Execution Engine run failed: {exc}")
            return RunOutcome(success=False, request=request, result=None, error=str(exc))

        return RunOutcome(success=True, request=request, result=result, error="")

    def set_stop_on_failure(self, value: bool) -> CommandResult:
        """Set whether execution halts the remaining plan after a step fails.

        Args:
            value: The new default.

        Returns:
            A CommandResult reflecting whether the policy was updated.
        """
        try:
            self._manager.set_stop_on_failure(value)
        except PlanExecutionConfigurationError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"stop_on_failure set to {value}.")
