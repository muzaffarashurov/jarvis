"""EP-028 Agent Framework Engine.

A provider-independent engine that forwards every lifecycle,
subsystem-registry, and request call to the currently selected
`AgentProvider` (via `AgentManager`) -- this is the Agent Framework's
entire responsibility: receive requests, maintain agent lifecycle,
coordinate already-implemented Engineering Packages through a
subsystem registry, expose agent status, expose registered subsystems,
and expose an orchestration pipeline that dispatches requests to a
future Planner. It must NOT plan, reason, execute tools, build
prompts, or make an AI provider call (see
`src/core/agent/__init__.py`).

Depends only on public APIs:
    - `AgentManager` (this package) -- current agent and resolved
      'agent.startup_mode'.

No AI provider, no Planner, no Reasoning Engine, no Reflection Engine,
no Workflow Engine, no Prompt Engine, no Conversation Engine, no
Browser Automation, no Tool Executor, and no private attribute of any
subsystem is ever accessed -- subsystems are reached only through the
single, caller-supplied `status_check` callable passed to
`register_subsystem()`.
"""

from __future__ import annotations

from src.core.agent.agent_manager import AgentManager
from src.core.agent.agent_provider import AgentFrameworkError, AgentProviderError
from src.core.agent.agent_result import AgentCancelResult, AgentExecutionResult, SubsystemInfo
from src.core.agent.agent_state import AgentState

__all__ = [
    "AgentEngine",
    "AgentEngineError",
    "NoAgentSelectedError",
    "EmptyRequestError",
]


class AgentEngineError(AgentFrameworkError):
    """Base class for errors raised by the AgentEngine itself.

    Inherits from `AgentFrameworkError`
    (src/core/agent/agent_provider.py) so callers can catch every
    Agent-Framework-related failure -- provider, engine, or manager --
    with a single exception type.
    """


class NoAgentSelectedError(AgentEngineError):
    """Raised when an agent call is made but no agent is currently selected."""


class EmptyRequestError(AgentEngineError):
    """Raised when `execute()` is called with an empty/whitespace-only request."""


class AgentEngine:
    """Provider-independent Agent Framework pipeline.

    Every public method forwards, unchanged, to whichever
    `AgentProvider` `AgentManager.get_current()` currently reports --
    this class implements no lifecycle logic, no subsystem registry,
    and no request handling itself. If 'agent.startup_mode' resolves
    to "auto", the currently selected agent is initialized once, here,
    at construction time.
    """

    def __init__(self, manager: AgentManager) -> None:
        """Initialize the AgentEngine.

        Args:
            manager: The AgentManager used to resolve the currently
                active agent and the resolved 'agent.startup_mode'.
                Never mutated by this engine, aside from the one-time
                `initialize()` call issued to its current agent when
                'agent.startup_mode' is "auto".
        """
        self._manager = manager
        if self._manager.startup_mode() == "auto":
            current = self._manager.get_current()
            if current is not None:
                current.initialize()

    def initialize(self) -> None:
        """Transition the current agent into `AgentState.READY`.

        Raises:
            NoAgentSelectedError: If no agent is currently selected
                (or the subsystem is disabled).
        """
        self._require_current_provider().initialize()

    def shutdown(self) -> None:
        """Transition the current agent into `AgentState.SHUTDOWN`.

        Raises:
            NoAgentSelectedError: If no agent is currently selected
                (or the subsystem is disabled).
        """
        self._require_current_provider().shutdown()

    def reset(self) -> None:
        """Clear the current agent's transient request-tracking state.

        Raises:
            NoAgentSelectedError: If no agent is currently selected
                (or the subsystem is disabled).
        """
        self._require_current_provider().reset()

    def status(self) -> AgentState:
        """Return the current agent's `AgentState`.

        Raises:
            NoAgentSelectedError: If no agent is currently selected
                (or the subsystem is disabled).
        """
        return self._require_current_provider().status()

    def execute(self, request: str, metadata: dict | None = None) -> AgentExecutionResult:
        """Accept and acknowledge `request` through the current agent.

        Args:
            request: The request text. Never parsed, planned, or acted
                on -- the Agent Framework performs no reasoning.
            metadata: Optional caller-supplied metadata, forwarded
                unchanged.

        Returns:
            The resulting AgentExecutionResult.

        Raises:
            EmptyRequestError: If `request` is empty or whitespace-only.
            NoAgentSelectedError: If no agent is currently selected
                (or the subsystem is disabled).
            AgentProviderError: If the current agent itself rejects the
                request (e.g. it is not currently READY).
        """
        if not request or not request.strip():
            raise EmptyRequestError("Agent Framework request must not be empty.")
        return self._require_current_provider().execute(request, metadata=metadata)

    def cancel(self, request_id: str) -> AgentCancelResult:
        """Attempt to cancel a previously accepted request through the current agent.

        Args:
            request_id: A request id previously returned by `execute()`.

        Returns:
            The resulting AgentCancelResult.

        Raises:
            NoAgentSelectedError: If no agent is currently selected
                (or the subsystem is disabled).
            AgentProviderError: If `request_id` is unknown to the
                current agent.
        """
        return self._require_current_provider().cancel(request_id)

    def register_subsystem(self, name: str, status_check=None) -> None:
        """Register a subsystem the current agent coordinates.

        Args:
            name: The subsystem's name.
            status_check: Optional zero-argument callable reporting
                whether the subsystem is currently enabled, read only
                through its own public API.

        Raises:
            NoAgentSelectedError: If no agent is currently selected
                (or the subsystem is disabled).
            AgentProviderError: If `name` is already registered.
        """
        self._require_current_provider().register_subsystem(name, status_check=status_check)

    def unregister_subsystem(self, name: str) -> None:
        """Remove a previously registered subsystem from the current agent.

        Args:
            name: The subsystem's registered name.

        Raises:
            NoAgentSelectedError: If no agent is currently selected
                (or the subsystem is disabled).
            AgentProviderError: If `name` is not registered.
        """
        self._require_current_provider().unregister_subsystem(name)

    def list_subsystems(self) -> list[SubsystemInfo]:
        """Return the current agent's registered subsystems, ordered by name.

        Raises:
            NoAgentSelectedError: If no agent is currently selected
                (or the subsystem is disabled).
        """
        return self._require_current_provider().list_subsystems()

    # ---------- Internal helpers ----------

    def _require_current_provider(self):
        """Return the currently selected agent, or raise if none is selected.

        Returns:
            The active AgentProvider.

        Raises:
            NoAgentSelectedError: If no agent is currently selected
                (or the subsystem is disabled).
        """
        provider = self._manager.get_current()
        if provider is None:
            raise NoAgentSelectedError(
                "No agent is currently selected. Check 'agent.enabled' and "
                "'agent.default_agent' configuration."
            )
        return provider
