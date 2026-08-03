"""Agent lifecycle state for EP-028 Agent Framework.

Defines the single enum every `AgentProvider` implementation reports
through `status()` and transitions through via
`initialize()`/`shutdown()`/`reset()`/`execute()`. This module owns no
behavior -- it mirrors the role of
`src/core/context_compression/compression_provider.py`'s
`CompressionProviderStatus` relative to `CompressionProvider`, just
for agent lifecycle instead of provider configuration readiness.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["AgentState"]


class AgentState(str, Enum):
    """An agent's current position in its lifecycle.

    Transitions (enforced by `DefaultAgentProvider`, never by this
    enum itself):

        UNINITIALIZED --initialize()--> READY
        READY --execute()--> RUNNING --(execute() completes)--> READY
        READY/RUNNING/ERROR --reset()--> READY
        UNINITIALIZED/SHUTDOWN --reset()--> unchanged (reset does not
            initialize or resurrect a shut-down agent)
        (any state) --shutdown()--> SHUTDOWN
        SHUTDOWN --initialize()--> READY (re-initialization is allowed)

    Attributes:
        UNINITIALIZED: The agent has been constructed but
            `initialize()` has not yet been called (or configuration
            resolved 'agent.startup_mode' to "idle"). `execute()` is
            rejected in this state.
        READY: The agent is initialized and idle, able to accept a
            new `execute()` call.
        RUNNING: The agent is currently processing one `execute()`
            call. Since no Planner/Reasoning Engine/Task Scheduler
            exists yet, this state is held only for the duration of a
            single synchronous acknowledgment -- there is no
            long-running task to observe or cancel.
        SHUTDOWN: The agent has been explicitly shut down via
            `shutdown()`. `execute()` is rejected until `initialize()`
            is called again.
        ERROR: The agent encountered an unrecoverable condition during
            `execute()` and requires `reset()` before further use.
            `DefaultAgentProvider` (this EP's only implementation)
            never enters this state on its own, since it performs no
            reasoning that could fail -- it exists for future
            `AgentProvider` implementations (e.g. a Planner-backed
            agent) to report into.
    """

    UNINITIALIZED = "UNINITIALIZED"
    READY = "READY"
    RUNNING = "RUNNING"
    SHUTDOWN = "SHUTDOWN"
    ERROR = "ERROR"
