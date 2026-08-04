"""Business logic for EP-029 Planning Engine CLI integration.

PlanningService is a thin, CLI-facing wrapper around PlanningEngine and
PlanningManager. It owns no decomposition logic itself -- provider
selection and default limits stay inside PlanningManager, and
request-to-plan orchestration stays inside PlanningEngine/
PlanningProvider; this service only forwards calls to them and adapts
the results to dataclasses/CommandResult for PlanningModule, matching
every other Service in this project (see
src/services/context_compression_service.py's CompressionService ->
CompressionEngine pattern):

    PlanningModule -> PlanningService -> PlanningEngine -> PlanningManager

It implements no business logic belonging to any other module and
never imports from src.core.rag, src.core.ai, or any Reasoning/
Reflection/Execution/Tool-Executor module (the Planning Engine must
not reason, execute, or call an AI provider).
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.command_router import CommandResult
from src.core.planning.planning_engine import PlanningEngine, PlanningEngineError
from src.core.planning.planning_manager import PlanningManager, PlanningProviderNotFoundError
from src.core.planning.planning_provider import PlanningConfigurationError, PlanningProviderError
from src.core.planning.planning_result import Plan


@dataclass(frozen=True)
class PlanningStatus:
    """Result of `planning status`.

    Attributes:
        enabled: Whether the Planning Engine subsystem is currently
            enabled.
        current_provider: The currently selected provider's name, or
            None if no provider is selected.
        registered_provider_count: Number of providers registered with
            the PlanningManager.
        max_steps: The current default maximum number of steps a plan
            may contain.
    """

    enabled: bool
    current_provider: str | None
    registered_provider_count: int
    max_steps: int


@dataclass(frozen=True)
class PlanningProviderInfo:
    """One row of `planning providers` output.

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
    """Result of `planning use <provider>`.

    Attributes:
        success: Whether the provider was successfully selected.
        provider: The requested provider name.
        message: Human-readable outcome summary.
    """

    success: bool
    provider: str
    message: str


@dataclass(frozen=True)
class PlanOutcome:
    """Result of `planning plan "<request>"`.

    Attributes:
        success: Whether planning completed successfully.
        request: The request text that was planned.
        plan: The resulting Plan, or None on failure.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    request: str
    plan: Plan | None
    error: str


@dataclass(frozen=True)
class PlanningLimits:
    """Result of `planning limits`.

    Attributes:
        max_steps: The current default maximum number of steps a plan
            may contain.
    """

    max_steps: int


class PlanningService:
    """Coordinates PlanningEngine/PlanningManager and exposes them as a CLI-friendly API.

    Depends only on PlanningEngine and PlanningManager (EP-029).
    Implements no planning logic of its own -- every call is forwarded
    unchanged; this class only adapts return values to
    dataclasses/CommandResult for PlanningModule.
    """

    def __init__(self, manager: PlanningManager, engine: PlanningEngine) -> None:
        """Initialize the PlanningService.

        Args:
            manager: The PlanningManager this service reports on and
                selects providers through.
            engine: The PlanningEngine this service requests planning
                through.
        """
        self._manager = manager
        self._engine = engine

    def status(self) -> PlanningStatus:
        """Return the Planning Engine subsystem's overall status."""
        return PlanningStatus(
            enabled=self._manager.is_enabled(),
            current_provider=self._manager.current_provider_name(),
            registered_provider_count=len(self._manager.list_providers()),
            max_steps=self._manager.max_steps(),
        )

    def list_providers(self) -> list[PlanningProviderInfo]:
        """List every registered planning provider and its diagnostic flags."""
        current_name = self._manager.current_provider_name()
        return [
            PlanningProviderInfo(
                name=provider.provider_name(),
                available=provider.is_available(),
                is_current=provider.provider_name() == current_name,
            )
            for provider in self._manager.list_providers()
        ]

    def use_provider(self, name: str) -> ProviderSelectionResult:
        """Select a planning provider as the currently active provider.

        Args:
            name: The registered provider name to activate.

        Returns:
            A ProviderSelectionResult reflecting whether `name` was
            selected.
        """
        try:
            self._manager.set_current(name)
        except PlanningProviderNotFoundError as exc:
            return ProviderSelectionResult(success=False, provider=name, message=str(exc))

        return ProviderSelectionResult(
            success=True, provider=name, message=f"Planning provider set to '{name}'."
        )

    def disable(self) -> CommandResult:
        """Disable the Planning Engine subsystem."""
        self._manager.disable()
        return CommandResult(success=True, message="Planning Engine subsystem disabled.")

    def plan(self, request: str) -> PlanOutcome:
        """Decompose `request` into an ordered Plan using the currently active provider.

        Args:
            request: The request text to decompose.

        Returns:
            A PlanOutcome describing the outcome.
        """
        try:
            result = self._engine.plan(request)
        except (PlanningEngineError, PlanningProviderError) as exc:
            logger.error(f"Planning Engine plan failed: {exc}")
            return PlanOutcome(success=False, request=request, plan=None, error=str(exc))

        return PlanOutcome(success=True, request=request, plan=result, error="")

    def limits(self) -> PlanningLimits:
        """Return the current default planning limits."""
        return PlanningLimits(max_steps=self._manager.max_steps())

    def set_max_steps(self, value: int) -> CommandResult:
        """Set the default maximum number of steps a plan may contain.

        Args:
            value: The new default maximum, a positive integer.

        Returns:
            A CommandResult reflecting whether the limit was updated.
        """
        try:
            self._manager.set_max_steps(value)
        except PlanningConfigurationError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Max steps set to {value}.")
