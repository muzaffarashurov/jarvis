"""EP-032 Multi-Agent Collaboration Engine.

A provider-independent engine that turns a request into a
`CollaborationResult`: reads the live agent catalog from EP-028's
`AgentManager` (public `list_providers()` only), and dispatches to the
currently selected `CollaborationProvider` (via `CollaborationManager`)
to distribute the request across every registered agent. This is
Multi-Agent Collaboration's entire responsibility -- it must NOT call
an AI provider, build a prompt, plan a request, walk a Plan, or decide
*how* a single agent handles a request (that remains each agent's own
`AgentProvider.execute()`); this engine only coordinates *which*
already-registered agents a request reaches (see
`src/core/collaboration/__init__.py`).

Depends only on public APIs:
    - `CollaborationManager` (this package) -- current provider.
    - `AgentManager` (EP-028) -- through `list_providers()` only.

No AI provider, no Planning Engine, no Plan Execution Engine, no Tool
Engine, and no private attribute of any subsystem is ever accessed
here.
"""

from __future__ import annotations

from src.core.agent.agent_manager import AgentManager
from src.core.collaboration.collaboration_manager import CollaborationManager
from src.core.collaboration.collaboration_provider import CollaborationError
from src.core.collaboration.collaboration_result import CollaborationResult

__all__ = [
    "CollaborationEngine",
    "CollaborationEngineError",
    "NoCollaborationProviderSelectedError",
    "EmptyCollaborationRequestError",
    "NoAgentsAvailableError",
]


class CollaborationEngineError(CollaborationError):
    """Base class for errors raised by the CollaborationEngine itself.

    Inherits from `CollaborationError`
    (src/core/collaboration/collaboration_provider.py) so callers can
    catch every Multi-Agent-Collaboration-related failure -- provider,
    engine, or manager -- with a single exception type.
    """


class NoCollaborationProviderSelectedError(CollaborationEngineError):
    """Raised when a collaboration is requested but no provider is currently selected."""


class EmptyCollaborationRequestError(CollaborationEngineError):
    """Raised when `collaborate()` is called with an empty/whitespace-only request."""


class NoAgentsAvailableError(CollaborationEngineError):
    """Raised when no agent is registered with the Agent Framework at all.

    Distinct from every registered agent being reported UNAVAILABLE
    (not currently READY) -- that is a normal, expected runtime
    condition (e.g. the default 'agent.startup_mode: idle') and is
    reported as a `CollaborationResult`, not raised. This error means
    there is nothing whatsoever for Multi-Agent Collaboration to
    coordinate.
    """


class CollaborationEngine:
    """Provider-independent request -> multi-agent-dispatch pipeline.

    Never selects, constructs, or configures collaboration providers
    itself -- provider selection and lifecycle are exclusively
    `CollaborationManager`'s concern. Never selects, constructs, or
    configures agents itself -- agent registration and lifecycle
    remain exclusively `AgentManager`'s concern (EP-028). Never invokes
    an agent itself -- that stays inside the active
    `CollaborationProvider`.
    """

    def __init__(self, manager: CollaborationManager, agent_manager: AgentManager) -> None:
        """Initialize the CollaborationEngine.

        Args:
            manager: The CollaborationManager used to resolve the
                currently active collaboration provider. Never mutated
                by this engine.
            agent_manager: The EP-028 AgentManager used to resolve the
                currently registered agent catalog, through its public
                `list_providers()` method only. Never mutated by this
                engine.
        """
        self._manager = manager
        self._agent_manager = agent_manager

    def list_agents(self) -> list[str]:
        """Return the stable names of every agent currently registered with the Agent Framework.

        Returns:
            A list of agent names, in `AgentManager.list_providers()`'s
            own (name-sorted) order.
        """
        return [agent.agent_name() for agent in self._agent_manager.list_providers()]

    def collaborate(self, request: str, metadata: dict | None = None) -> CollaborationResult:
        """Distribute `request` across every currently registered agent.

        Args:
            request: The request text. Never parsed, planned, or acted
                on by this engine -- forwarded unchanged to the active
                `CollaborationProvider`.
            metadata: Optional caller-supplied metadata, forwarded
                unchanged.

        Returns:
            The resulting CollaborationResult.

        Raises:
            EmptyCollaborationRequestError: If `request` is empty or
                whitespace-only.
            NoAgentsAvailableError: If no agent is registered with the
                Agent Framework at all.
            NoCollaborationProviderSelectedError: If no collaboration
                provider is currently selected (or the subsystem is
                disabled).
        """
        if not request or not request.strip():
            raise EmptyCollaborationRequestError(
                "Multi-Agent Collaboration request must not be empty."
            )

        agents = self._agent_manager.list_providers()
        if not agents:
            raise NoAgentsAvailableError(
                "No agent is registered with the Agent Framework. Check "
                "'agent.enabled' and 'agent.default_agent' configuration."
            )

        provider = self._require_current_provider()
        return provider.collaborate(request, metadata=metadata, agents=agents)

    # ---------- Internal helpers ----------

    def _require_current_provider(self):
        """Return the currently selected provider, or raise if none is selected.

        Returns:
            The active CollaborationProvider.

        Raises:
            NoCollaborationProviderSelectedError: If no collaboration
                provider is currently selected (or the subsystem is
                disabled).
        """
        provider = self._manager.get_current()
        if provider is None:
            raise NoCollaborationProviderSelectedError(
                "No collaboration provider is currently selected. Use "
                "'collaborate use <provider>'."
            )
        return provider
