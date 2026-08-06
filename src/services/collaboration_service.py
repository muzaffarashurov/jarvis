"""Business logic for EP-032 Multi-Agent Collaboration CLI integration.

CollaborationService is a thin, CLI-facing wrapper around
CollaborationEngine and CollaborationManager. It owns no distribution
logic or agent-catalog logic itself -- provider selection stays inside
CollaborationManager, the live agent catalog stays inside EP-028's
AgentManager, and dispatch orchestration stays inside
CollaborationEngine/CollaborationProvider; this service only forwards
calls to them and adapts the results to dataclasses/CommandResult for
CollaborationModule, matching every other Service in this project (see
src/services/tool_service.py's ToolService -> ToolEngine pattern):

    CollaborationModule -> CollaborationService -> CollaborationEngine -> CollaborationManager

It implements no business logic belonging to any other module and
never imports from src.core.ai, src.core.planning, or
src.core.plan_execution (Multi-Agent Collaboration must not plan,
decompose, or walk a Plan).
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.collaboration.collaboration_engine import (
    CollaborationEngine,
    CollaborationEngineError,
)
from src.core.collaboration.collaboration_manager import (
    CollaborationManager,
    CollaborationProviderNotFoundError,
)
from src.core.collaboration.collaboration_provider import CollaborationProviderError
from src.core.collaboration.collaboration_result import CollaborationResult
from src.core.command_router import CommandResult


@dataclass(frozen=True)
class CollaborationStatus:
    """Result of `collaborate status`.

    Attributes:
        enabled: Whether the Multi-Agent Collaboration subsystem is
            currently enabled.
        current_provider: The currently selected provider's name, or
            None if no provider is selected.
        registered_provider_count: Number of providers registered with
            the CollaborationManager.
        registered_agent_count: Number of agents currently registered
            with the Agent Framework (EP-028).
    """

    enabled: bool
    current_provider: str | None
    registered_provider_count: int
    registered_agent_count: int


@dataclass(frozen=True)
class CollaborationProviderInfo:
    """One row of `collaborate providers` output.

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
    """Result of `collaborate use <provider>`.

    Attributes:
        success: Whether the provider was successfully selected.
        provider: The requested provider name.
        message: Human-readable outcome summary.
    """

    success: bool
    provider: str
    message: str


@dataclass(frozen=True)
class CollaborationOutcome:
    """Result of `collaborate run "<request>"`.

    Attributes:
        success: Whether collaboration completed without an
            infrastructure-level error (this is independent of
            whether every agent itself succeeded -- see
            `CollaborationResult.success` for that).
        request: The request text that was distributed.
        result: The resulting CollaborationResult, or None on
            infrastructure failure.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    request: str
    result: CollaborationResult | None
    error: str


class CollaborationService:
    """Coordinates CollaborationEngine/CollaborationManager as a CLI-friendly API.

    Depends only on CollaborationEngine and CollaborationManager
    (EP-032). Implements no distribution logic of its own -- every call
    is forwarded unchanged; this class only adapts return values to
    dataclasses/CommandResult for CollaborationModule.
    """

    def __init__(self, manager: CollaborationManager, engine: CollaborationEngine) -> None:
        """Initialize the CollaborationService.

        Args:
            manager: The CollaborationManager this service reports on
                and selects providers through.
            engine: The CollaborationEngine this service requests
                collaboration through.
        """
        self._manager = manager
        self._engine = engine

    def status(self) -> CollaborationStatus:
        """Return the Multi-Agent Collaboration subsystem's overall status."""
        return CollaborationStatus(
            enabled=self._manager.is_enabled(),
            current_provider=self._manager.current_provider_name(),
            registered_provider_count=len(self._manager.list_providers()),
            registered_agent_count=len(self._engine.list_agents()),
        )

    def list_providers(self) -> list[CollaborationProviderInfo]:
        """List every registered collaboration provider and its diagnostic flags."""
        current_name = self._manager.current_provider_name()
        return [
            CollaborationProviderInfo(
                name=provider.provider_name(),
                available=provider.is_available(),
                is_current=provider.provider_name() == current_name,
            )
            for provider in self._manager.list_providers()
        ]

    def list_agents(self) -> list[str]:
        """List every agent currently registered with the Agent Framework (EP-028)."""
        return self._engine.list_agents()

    def use_provider(self, name: str) -> ProviderSelectionResult:
        """Select a collaboration provider as the currently active provider.

        Args:
            name: The registered provider name to activate.

        Returns:
            A ProviderSelectionResult reflecting whether `name` was
            selected.
        """
        try:
            self._manager.set_current(name)
        except CollaborationProviderNotFoundError as exc:
            return ProviderSelectionResult(success=False, provider=name, message=str(exc))

        return ProviderSelectionResult(
            success=True, provider=name, message=f"Collaboration provider set to '{name}'."
        )

    def disable(self) -> CommandResult:
        """Disable the Multi-Agent Collaboration subsystem."""
        self._manager.disable()
        return CommandResult(success=True, message="Multi-Agent Collaboration subsystem disabled.")

    def run(self, request: str) -> CollaborationOutcome:
        """Distribute `request` across every currently registered agent.

        Args:
            request: The request text to distribute.

        Returns:
            A CollaborationOutcome describing the outcome.
        """
        try:
            result = self._engine.collaborate(request)
        except (CollaborationEngineError, CollaborationProviderError) as exc:
            logger.error(f"Multi-Agent Collaboration run failed: {exc}")
            return CollaborationOutcome(success=False, request=request, result=None, error=str(exc))

        return CollaborationOutcome(success=True, request=request, result=result, error="")
