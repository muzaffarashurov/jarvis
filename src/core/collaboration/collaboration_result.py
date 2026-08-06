"""Domain model for EP-032 Multi-Agent Collaboration.

Defines the plain data types shared by `CollaborationProvider` (the
actual per-agent dispatch strategy), `CollaborationEngine` (pipeline
orchestration) and `CollaborationService` (the CLI-facing layer): the
outcome of dispatching a request to a single registered agent
(`AgentOutcomeStatus`, `AgentOutcome`) and the outcome of a single
`collaborate()` call across every currently registered agent
(`CollaborationResult`). This module owns no dispatch logic itself --
it mirrors the role of `src/core/plan_execution/plan_execution_result.py`
relative to `PlanExecutionProvider`/`PlanExecutionEngine`, just for
per-agent outcomes instead of per-step outcomes.

Multi-Agent Collaboration performs no AI reasoning, no negotiation,
and no inter-agent messaging: it only distributes an already-formed
request to every currently registered `AgentProvider` (EP-028) and
collects each agent's own `AgentExecutionResult` (also EP-028) into a
uniform outcome list. This module has no dependency on any LLM, AI
provider, prompt, planner, or reflection component.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "AgentOutcomeStatus",
    "AgentOutcome",
    "CollaborationResult",
]


class AgentOutcomeStatus(str, Enum):
    """The outcome of dispatching a request to a single registered agent.

    Attributes:
        SUCCEEDED: The agent was READY and its own `execute()` call
            reported `success=True`.
        FAILED: The agent was READY but its own `execute()` call
            reported `success=False`, or raised an `AgentFrameworkError`
            that this package caught and translated (see
            `DefaultCollaborationProvider`).
        UNAVAILABLE: The agent was never dispatched to at all -- it
            was not currently in `AgentState.READY` (e.g.
            UNINITIALIZED, SHUTDOWN, or already RUNNING).
    """

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class AgentOutcome:
    """The outcome of attempting to dispatch a request to a single agent.

    Attributes:
        agent_name: The dispatched-to (or skipped) agent's stable
            identifier, as reported by its own `AgentProvider.agent_name()`.
        status: This agent's outcome.
        message: Human-readable explanation of the outcome.
        request_id: The request id returned by this agent's own
            `execute()` call, or None if the agent was never
            dispatched to (`status == UNAVAILABLE`).
    """

    agent_name: str
    status: AgentOutcomeStatus
    message: str
    request_id: str | None = None


@dataclass(frozen=True)
class CollaborationResult:
    """The outcome of a single `CollaborationEngine.collaborate()` call.

    Attributes:
        request: The request text that was distributed, unchanged.
        outcomes: One `AgentOutcome` per agent registered with the
            Agent Framework (EP-028) at the time of this call, ordered
            by agent name.
        participant_count: Number of agents considered (`len(outcomes)`).
        succeeded_count: Number of outcomes with
            `AgentOutcomeStatus.SUCCEEDED`.
        failed_count: Number of outcomes with `AgentOutcomeStatus.FAILED`.
        unavailable_count: Number of outcomes with
            `AgentOutcomeStatus.UNAVAILABLE`.
        success: Whether at least one agent succeeded and no agent
            failed (`succeeded_count > 0 and failed_count == 0`). A
            collaboration in which every agent was UNAVAILABLE (e.g.
            the default 'agent.startup_mode: idle' configuration, with
            no agent yet initialized) is honestly reported as
            unsuccessful -- nothing was actually accomplished.
    """

    request: str
    outcomes: list[AgentOutcome] = field(default_factory=list)
    participant_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    unavailable_count: int = 0
    success: bool = False

    def summary(self) -> str:
        """Return a human-readable, multi-line summary of every agent's outcome.

        Returns:
            One line per outcome, formatted as
            "<agent_name> - <status>: <message>", in order. Empty
            string if there are no outcomes (e.g. no agents were
            registered with the Agent Framework at all).
        """
        lines = []
        for outcome in self.outcomes:
            lines.append(f"{outcome.agent_name} - {outcome.status.value}: {outcome.message}")
        return "\n".join(lines)
