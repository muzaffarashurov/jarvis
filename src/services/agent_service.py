"""Business logic for EP-028 Agent Framework CLI integration.

AgentService is a thin, CLI-facing wrapper around AgentEngine and
AgentManager. It owns no lifecycle logic or subsystem-registry logic
itself -- agent selection and startup mode stay inside AgentManager,
and lifecycle/request/subsystem-registry forwarding stays inside
AgentEngine/AgentProvider; this service only forwards calls to them
and adapts the results to dataclasses/CommandResult for AgentModule,
matching every other Service in this project (see
src/services/context_compression_service.py's CompressionService ->
CompressionEngine pattern):

    AgentModule -> AgentService -> AgentEngine -> AgentManager

It implements no business logic belonging to any other module and
never imports from src.core.rag, src.core.ai, or any Planner/
Reasoning/Reflection/Workflow/Tool-Executor module (the Agent
Framework must not plan, reason, execute tools, or call an AI
provider).
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.agent.agent_engine import AgentEngine, AgentEngineError
from src.core.agent.agent_manager import AgentManager
from src.core.agent.agent_provider import AgentProviderError
from src.core.agent.agent_state import AgentState
from src.core.command_router import CommandResult


@dataclass(frozen=True)
class AgentStatus:
    """Result of `agent status`.

    Attributes:
        enabled: Whether the Agent Framework subsystem is currently
            enabled.
        current_agent: The currently selected agent's name, or None if
            no agent is selected.
        state: The current agent's `AgentState`, or None if no agent
            is selected.
        registered_agent_count: Number of agents registered with the
            AgentManager.
        startup_mode: The resolved 'agent.startup_mode' ("idle" or
            "auto"), or "" if the subsystem is disabled.
        subsystem_count: Number of subsystems registered with the
            current agent, or 0 if no agent is selected.
    """

    enabled: bool
    current_agent: str | None
    state: AgentState | None
    registered_agent_count: int
    startup_mode: str
    subsystem_count: int


@dataclass(frozen=True)
class SubsystemOutcome:
    """Result of `agent register <name>` / `agent unregister <name>`.

    Attributes:
        success: Whether the operation completed successfully.
        name: The subsystem name that was requested.
        message: Human-readable outcome summary.
    """

    success: bool
    name: str
    message: str


class AgentService:
    """Coordinates AgentEngine/AgentManager and exposes them as a CLI-friendly API.

    Depends only on AgentEngine and AgentManager (EP-028). Implements
    no orchestration logic of its own -- every call is forwarded
    unchanged; this class only adapts return values to
    dataclasses/CommandResult for AgentModule.
    """

    def __init__(self, manager: AgentManager, engine: AgentEngine) -> None:
        """Initialize the AgentService.

        Args:
            manager: The AgentManager this service reports on.
            engine: The AgentEngine this service forwards
                lifecycle/subsystem-registry/request calls through.
        """
        self._manager = manager
        self._engine = engine

    def status(self) -> AgentStatus:
        """Return the Agent Framework subsystem's overall status."""
        state: AgentState | None = None
        subsystem_count = 0
        if self._manager.get_current() is not None:
            state = self._engine.status()
            subsystem_count = len(self._engine.list_subsystems())

        return AgentStatus(
            enabled=self._manager.is_enabled(),
            current_agent=self._manager.current_provider_name(),
            state=state,
            registered_agent_count=len(self._manager.list_providers()),
            startup_mode=self._manager.startup_mode() if self._manager.is_enabled() else "",
            subsystem_count=subsystem_count,
        )

    def list_subsystems(self):
        """List every subsystem registered with the current agent.

        Returns:
            A list of `SubsystemInfo` (see
            src/core/agent/agent_result.py), or an empty list if no
            agent is currently selected.
        """
        if self._manager.get_current() is None:
            return []
        return self._engine.list_subsystems()

    def register_subsystem(self, name: str) -> SubsystemOutcome:
        """Register a subsystem, by name only, with the current agent.

        No live status-check callable is bound for a CLI-registered
        subsystem -- it is a "declared present" registration, always
        reported available. Subsystems backed by a real, bootstrap-wired
        service (e.g. "knowledge", "semantic") are registered with a
        live status check during Bootstrap wiring instead; see
        src/bootstrap.py's EP-028 wiring.

        Args:
            name: The subsystem name to register.

        Returns:
            A SubsystemOutcome reflecting whether `name` was registered.
        """
        try:
            self._engine.register_subsystem(name)
        except (AgentEngineError, AgentProviderError) as exc:
            return SubsystemOutcome(success=False, name=name, message=str(exc))
        return SubsystemOutcome(success=True, name=name, message=f"Subsystem registered: '{name}'.")

    def unregister_subsystem(self, name: str) -> SubsystemOutcome:
        """Remove a subsystem from the current agent's registry.

        Args:
            name: The subsystem name to remove.

        Returns:
            A SubsystemOutcome reflecting whether `name` was removed.
        """
        try:
            self._engine.unregister_subsystem(name)
        except (AgentEngineError, AgentProviderError) as exc:
            return SubsystemOutcome(success=False, name=name, message=str(exc))
        return SubsystemOutcome(success=True, name=name, message=f"Subsystem unregistered: '{name}'.")

    def initialize(self) -> CommandResult:
        """Initialize the current agent."""
        try:
            self._engine.initialize()
        except (AgentEngineError, AgentProviderError) as exc:
            logger.error(f"Agent Framework initialize failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message="Agent initialized.")

    def shutdown(self) -> CommandResult:
        """Shut down the current agent."""
        try:
            self._engine.shutdown()
        except (AgentEngineError, AgentProviderError) as exc:
            logger.error(f"Agent Framework shutdown failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message="Agent shut down.")

    def reset(self) -> CommandResult:
        """Reset the current agent's transient request-tracking state."""
        try:
            self._engine.reset()
        except (AgentEngineError, AgentProviderError) as exc:
            logger.error(f"Agent Framework reset failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message="Agent reset.")

    def disable(self) -> CommandResult:
        """Disable the Agent Framework subsystem."""
        self._manager.disable()
        return CommandResult(success=True, message="Agent Framework subsystem disabled.")

    def execute(self, request: str, metadata: dict | None = None):
        """Forward a request to the current agent for acknowledgment.

        Not exposed as a CLI command in this EP (see
        src/modules/agent_module.py) -- available for future
        programmatic callers (e.g. a future Planner) that already hold
        an AgentService reference.

        Args:
            request: The request text. Never parsed, planned, or acted on.
            metadata: Optional caller-supplied metadata, forwarded unchanged.

        Returns:
            The resulting `AgentExecutionResult` (see
            src/core/agent/agent_result.py).

        Raises:
            EmptyRequestError: If `request` is empty or whitespace-only.
            NoAgentSelectedError: If no agent is currently selected.
            AgentProviderError: If the current agent rejects the request.
        """
        return self._engine.execute(request, metadata=metadata)

    def cancel(self, request_id: str):
        """Forward a cancellation attempt to the current agent.

        Not exposed as a CLI command in this EP; see `execute()`.

        Args:
            request_id: A request id previously returned by `execute()`.

        Returns:
            The resulting `AgentCancelResult` (see
            src/core/agent/agent_result.py).

        Raises:
            NoAgentSelectedError: If no agent is currently selected.
            AgentProviderError: If `request_id` is unknown.
        """
        return self._engine.cancel(request_id)
