"""Business logic for EP-031 Tool Engine CLI integration.

ToolService is a thin, CLI-facing wrapper around ToolEngine and
ToolManager. It owns no invocation logic or catalog logic itself --
provider selection and the tool catalog stay inside ToolManager, and
lookup/dispatch orchestration stays inside ToolEngine/ToolProvider;
this service only forwards calls to them and adapts the results to
dataclasses/CommandResult for ToolModule, matching every other Service
in this project (see src/services/plan_execution_service.py's
PlanExecutionService -> PlanExecutionEngine pattern):

    ToolModule -> ToolService -> ToolEngine -> ToolManager

It implements no business logic belonging to any other module and
never imports from src.core.ai, src.core.planning, or
src.core.plan_execution (the EP-030 bridge, `ToolExecutionProvider`,
lives in src.core.tool itself -- see
src/core/tool/tool_execution_provider.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.command_router import CommandResult
from src.core.tool.tool_engine import (
    NoToolProviderSelectedError,
    ToolEngine,
    ToolEngineError,
    ToolNotRegisteredError,
)
from src.core.tool.tool_manager import ToolManager, ToolProviderNotFoundError
from src.core.tool.tool_result import ToolResult


@dataclass(frozen=True)
class ToolEngineStatus:
    """Result of `tool status`.

    Attributes:
        enabled: Whether the Tool Engine subsystem is currently
            enabled.
        current_provider: The currently selected provider's name, or
            None if no provider is selected.
        registered_provider_count: Number of providers registered with
            the ToolManager.
        registered_tool_count: Number of tools registered in the
            catalog.
    """

    enabled: bool
    current_provider: str | None
    registered_provider_count: int
    registered_tool_count: int


@dataclass(frozen=True)
class ToolProviderInfo:
    """One row of `tool providers` output.

    Attributes:
        name: The provider's registered name.
        available: Whether the provider is enabled and fully configured.
        is_current: Whether this is the currently selected provider.
    """

    name: str
    available: bool
    is_current: bool


@dataclass(frozen=True)
class ToolInfo:
    """One row of `tool list` output.

    Attributes:
        id: The tool's registered id.
        name: The tool's human-readable display name.
        description: The tool's short description.
        subsystem: The subsystem this tool wraps, or None.
        action: The action identifier this tool satisfies.
        enabled: Whether this tool currently participates in invocation.
    """

    id: str
    name: str
    description: str
    subsystem: str | None
    action: str
    enabled: bool


@dataclass(frozen=True)
class ProviderSelectionResult:
    """Result of `tool use <provider>`.

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
    """Result of `tool run <tool_id>`.

    Attributes:
        success: Whether the invocation completed without an
            infrastructure-level error (this is independent of
            whether the tool itself reported success -- see
            `ToolResult.status` for that).
        tool_id: The tool id that was requested.
        result: The resulting ToolResult, or None on infrastructure
            failure.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    tool_id: str
    result: ToolResult | None
    error: str


class ToolService:
    """Coordinates ToolEngine/ToolManager and exposes them as a CLI-friendly API.

    Depends only on ToolEngine and ToolManager (EP-031). Implements no
    lookup or invocation logic of its own -- every call is forwarded
    unchanged; this class only adapts return values to
    dataclasses/CommandResult for ToolModule.
    """

    def __init__(self, manager: ToolManager, engine: ToolEngine) -> None:
        """Initialize the ToolService.

        Args:
            manager: The ToolManager this service reports on and
                selects providers through.
            engine: The ToolEngine this service requests invocation
                through.
        """
        self._manager = manager
        self._engine = engine

    def status(self) -> ToolEngineStatus:
        """Return the Tool Engine subsystem's overall status."""
        return ToolEngineStatus(
            enabled=self._manager.is_enabled(),
            current_provider=self._manager.current_provider_name(),
            registered_provider_count=len(self._manager.list_providers()),
            registered_tool_count=len(self._engine.list_tools()),
        )

    def list_providers(self) -> list[ToolProviderInfo]:
        """List every registered tool provider and its diagnostic flags."""
        current_name = self._manager.current_provider_name()
        return [
            ToolProviderInfo(
                name=provider.provider_name(),
                available=provider.is_available(),
                is_current=provider.provider_name() == current_name,
            )
            for provider in self._manager.list_providers()
        ]

    def list_tools(self) -> list[ToolInfo]:
        """List every registered tool in the catalog."""
        return [
            ToolInfo(
                id=tool.id,
                name=tool.name,
                description=tool.description,
                subsystem=tool.subsystem,
                action=tool.action,
                enabled=tool.enabled,
            )
            for tool in self._engine.list_tools()
        ]

    def use_provider(self, name: str) -> ProviderSelectionResult:
        """Select a tool provider as the currently active provider.

        Args:
            name: The registered provider name to activate.

        Returns:
            A ProviderSelectionResult reflecting whether `name` was
            selected.
        """
        try:
            self._manager.set_current(name)
        except ToolProviderNotFoundError as exc:
            return ProviderSelectionResult(success=False, provider=name, message=str(exc))

        return ProviderSelectionResult(
            success=True, provider=name, message=f"Tool provider set to '{name}'."
        )

    def disable(self) -> CommandResult:
        """Disable the Tool Engine subsystem."""
        self._manager.disable()
        return CommandResult(success=True, message="Tool Engine subsystem disabled.")

    def run(self, tool_id: str) -> RunOutcome:
        """Invoke the tool registered under `tool_id`.

        Args:
            tool_id: The id of the tool to invoke.

        Returns:
            A RunOutcome describing the outcome.
        """
        try:
            result = self._engine.invoke(tool_id)
        except (ToolNotRegisteredError, NoToolProviderSelectedError, ToolEngineError) as exc:
            logger.error(f"Tool Engine run failed: {exc}")
            return RunOutcome(success=False, tool_id=tool_id, result=None, error=str(exc))

        return RunOutcome(success=True, tool_id=tool_id, result=result, error="")
