"""CollaborationProvider domain model for EP-032 Multi-Agent Collaboration.

Defines the abstraction every multi-agent distribution strategy must
implement so the rest of Jarvis never needs to know which distribution
strategy is currently active, matching the pattern already used by the
Planning Engine (`src/core/planning/planning_provider.py`), the Plan
Execution Engine (`src/core/plan_execution/plan_execution_provider.py`),
and the Tool Engine (`src/core/tool/tool_provider.py`).

EP-028's task brief listed "Multi-Agent Coordinator" as an explicitly
*future* orchestration component -- named verbatim, and deferred again,
in the docstrings of EP-028 (`src/core/agent/__init__.py`), EP-029
(`src/core/planning/__init__.py`), and EP-030
(`src/core/plan_execution/__init__.py`). This module is where that
deferred component is finally implemented: exactly one concrete,
built-in strategy -- `DefaultCollaborationProvider`, registered under
the stable name "collaboration" (matching
'collaboration.default_provider' in config/config.yaml) -- broadcasts
the same request to every currently registered `AgentProvider` (EP-028)
and collects each agent's own `AgentExecutionResult` into a uniform
`AgentOutcome`.

This module performs no AI reasoning, no negotiation, no voting, and
no inter-agent messaging: it only iterates EP-028's already-registered
agent catalog (supplied by `CollaborationEngine`, itself reached only
through `AgentManager.list_providers()`) and calls each agent's own
public `status()`/`execute()` methods -- never a private attribute of
any `AgentProvider`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from loguru import logger

from src.core.agent.agent_provider import AgentFrameworkError, AgentProvider
from src.core.agent.agent_state import AgentState
from src.core.collaboration.collaboration_result import (
    AgentOutcome,
    AgentOutcomeStatus,
    CollaborationResult,
)

__all__ = [
    "CollaborationError",
    "CollaborationConfigurationError",
    "CollaborationProviderError",
    "CollaborationProvider",
    "DefaultCollaborationProvider",
]


class CollaborationError(Exception):
    """Common root for every exception raised by Multi-Agent Collaboration (EP-032).

    Downstream packages can catch this single type to handle "anything
    collaboration-related" without needing to know about every
    specific failure mode (provider-level, engine-level,
    manager-level, or configuration-level).
    """


class CollaborationConfigurationError(CollaborationError):
    """Raised when 'collaboration.*' configuration itself is invalid.

    This is distinct from a provider-level error: it means the
    configuration value itself is malformed (wrong type, empty, or
    references a provider that does not exist) -- restarting with
    corrected configuration is required to resolve it.
    """


class CollaborationProviderError(CollaborationError):
    """Base class for errors raised while using a collaboration provider."""


class CollaborationProvider(ABC):
    """Structural contract every multi-agent distribution strategy must implement.

    A provider distributes a single request across an already-resolved
    list of `AgentProvider` instances -- it never decides which agents
    to consider (that stays inside `CollaborationEngine`, via
    `AgentManager.list_providers()`), and never performs AI reasoning,
    negotiation, or voting. `is_available()` must never perform network
    requests or expensive work, matching `ToolProvider`'s convention.
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return this provider's stable identifier (e.g. "collaboration")."""
        raise NotImplementedError

    @abstractmethod
    def collaborate(
        self, request: str, metadata: dict | None, agents: list[AgentProvider]
    ) -> CollaborationResult:
        """Distribute `request` across `agents` and collect their outcomes.

        Args:
            request: The request text to distribute. Never parsed,
                planned, or reasoned about -- forwarded unchanged to
                each agent's own `execute()`.
            metadata: Optional caller-supplied metadata, forwarded
                unchanged to each agent's own `execute()`.
            agents: The already-resolved list of agents to consider --
                callers only ever pass the live catalog reported by
                `AgentManager.list_providers()`; deciding *which*
                agents exist is never this method's concern.

        Returns:
            The resulting CollaborationResult, with one `AgentOutcome`
            per entry in `agents`.
        """
        raise NotImplementedError

    # ---------- Lifecycle / diagnostics extension point ----------

    def is_available(self) -> bool:
        """Return whether this provider is currently able to collaborate.

        Base implementation always returns True. Providers with an
        enabled/configured distinction should override this method.
        """
        return True


class DefaultCollaborationProvider(CollaborationProvider):
    """Built-in collaboration provider: deterministic broadcast dispatch only.

    Registered by `CollaborationManager` under the name "collaboration"
    (see 'collaboration.default_provider' in config/config.yaml).
    Performs a fixed, purely deterministic pipeline -- no AI reasoning,
    no network access, no negotiation between agents:

        1. Sort `agents` by `agent_name()` (deterministic ordering).
        2. For each agent currently in `AgentState.READY`, call its own
           `execute(request, metadata=metadata)` and translate the
           resulting `AgentExecutionResult` into an `AgentOutcome`
           (`SUCCEEDED` if `success=True`, else `FAILED`).
        3. For each agent NOT currently READY, report `UNAVAILABLE`
           without ever calling `execute()` on it (mirrors EP-030's
           "skip an unavailable step" policy).
        4. An `AgentFrameworkError` raised by a single agent's
           `execute()` call is caught and translated into `FAILED` for
           that agent only -- one misbehaving agent must never prevent
           every other agent's outcome from being reported (mirrors
           `DefaultAgentProvider.list_subsystems()`'s isolation of a
           single failing `status_check`).
    """

    _NAME: str = "collaboration"

    def provider_name(self) -> str:
        """Return this provider's stable identifier: "collaboration"."""
        return self._NAME

    def collaborate(
        self, request: str, metadata: dict | None, agents: list[AgentProvider]
    ) -> CollaborationResult:
        """Broadcast `request` to every READY agent in `agents`.

        Args:
            request: The request text to broadcast.
            metadata: Optional caller-supplied metadata, forwarded
                unchanged to each dispatched agent's `execute()`.
            agents: The already-resolved list of agents to consider.

        Returns:
            The resulting CollaborationResult.
        """
        outcomes: list[AgentOutcome] = []
        succeeded_count = 0
        failed_count = 0
        unavailable_count = 0

        for agent in sorted(agents, key=lambda candidate: candidate.agent_name()):
            outcome = self._dispatch_one(agent, request, metadata)
            outcomes.append(outcome)
            if outcome.status == AgentOutcomeStatus.SUCCEEDED:
                succeeded_count += 1
            elif outcome.status == AgentOutcomeStatus.FAILED:
                failed_count += 1
            else:
                unavailable_count += 1

        return CollaborationResult(
            request=request,
            outcomes=outcomes,
            participant_count=len(outcomes),
            succeeded_count=succeeded_count,
            failed_count=failed_count,
            unavailable_count=unavailable_count,
            success=succeeded_count > 0 and failed_count == 0,
        )

    @staticmethod
    def _dispatch_one(
        agent: AgentProvider, request: str, metadata: dict | None
    ) -> AgentOutcome:
        """Dispatch `request` to a single agent, translating its outcome.

        Args:
            agent: The agent to consider.
            request: The request text.
            metadata: Optional caller-supplied metadata.

        Returns:
            The resulting AgentOutcome -- never raises.
        """
        name = agent.agent_name()

        try:
            state = agent.status()
        except AgentFrameworkError as exc:
            logger.warning(f"Collaboration could not read agent '{name}' status: {exc}")
            return AgentOutcome(
                agent_name=name,
                status=AgentOutcomeStatus.UNAVAILABLE,
                message=f"Agent '{name}' status could not be determined: {exc}",
            )

        if state != AgentState.READY:
            return AgentOutcome(
                agent_name=name,
                status=AgentOutcomeStatus.UNAVAILABLE,
                message=f"Agent '{name}' is {state.value}; not currently READY.",
            )

        try:
            result = agent.execute(request, metadata=metadata)
        except AgentFrameworkError as exc:
            logger.warning(f"Agent '{name}' execute() raised during collaboration: {exc}")
            return AgentOutcome(
                agent_name=name,
                status=AgentOutcomeStatus.FAILED,
                message=f"Agent '{name}' failed: {exc}",
            )

        status = AgentOutcomeStatus.SUCCEEDED if result.success else AgentOutcomeStatus.FAILED
        return AgentOutcome(
            agent_name=name,
            status=status,
            message=result.message,
            request_id=result.request_id,
        )
