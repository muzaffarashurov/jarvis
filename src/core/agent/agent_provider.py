"""AgentProvider domain model for EP-028 Agent Framework.

Defines the abstraction every agent implementation must satisfy so the
rest of Jarvis never needs to know which concrete agent is currently
active, matching the pattern already used by the Semantic Search
Provider Framework (`src/core/semantic/semantic_provider.py`) and the
Context Compression Provider Framework
(`src/core/context_compression/compression_provider.py`).

EP-028's task brief lists eight *future* orchestration components --
Planner, Reasoning Engine, Reflection Engine, Workflow Engine, Task
Scheduler, Tool Executor, Conversation Engine (already exists from
EP-016, but not integrated here), Multi-Agent Coordinator -- and is
explicit that "Create interfaces only. Do NOT implement future
components." This module resolves that exactly the way EP-026 and
EP-027 resolved the analogous conflict: it implements exactly one
concrete, built-in agent -- `DefaultAgentProvider`, registered under
the stable name "jarvis" (matching 'agent.default_agent' in
config/config.yaml) -- so the subsystem is actually usable today
(lifecycle management + subsystem registry + request
acknowledgment), while implementing none of the eight named *future*
components. Every `execute()` call is accepted and acknowledged, never
planned, reasoned about, or dispatched to a real task -- see
`AgentExecutionResult.dispatched`, which is always False here.

This module performs no AI reasoning, no planning, no task execution,
no tool calling, and no prompt construction: it only tracks lifecycle
state and a name -> availability-check subsystem registry, exactly
like `DefaultCompressionProvider` only deduplicates and limits
`ContextChunk` instances it is handed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import OrderedDict
from threading import Lock
from typing import Callable

from loguru import logger

from src.core.agent.agent_result import AgentCancelResult, AgentExecutionResult, SubsystemInfo
from src.core.agent.agent_state import AgentState

__all__ = [
    "AgentFrameworkError",
    "AgentConfigurationError",
    "AgentProviderError",
    "AgentNotInitializedError",
    "SubsystemAlreadyRegisteredError",
    "SubsystemNotFoundError",
    "AgentRequestNotFoundError",
    "AgentProvider",
    "DefaultAgentProvider",
]

#: Maximum number of completed request ids `DefaultAgentProvider` keeps
#: (for `cancel()`'s "already completed" diagnostic) before evicting the
#: oldest -- bounds memory for a long-running process; not a
#: persistence guarantee.
_MAX_TRACKED_REQUESTS: int = 1000


class AgentFrameworkError(Exception):
    """Common root for every exception raised by the Agent Framework (EP-028).

    Downstream packages (e.g. a future Workflow Engine) can catch this
    single type to handle "anything agent-framework-related" without
    needing to know about every specific failure mode (provider-level,
    engine-level, manager-level, or configuration-level).
    """


class AgentConfigurationError(AgentFrameworkError):
    """Raised when 'agent.*' configuration itself is invalid.

    This is distinct from a provider-level lifecycle error: it means
    the configuration value itself is malformed (wrong type, empty, or
    references an agent/mode that does not exist) -- restarting with
    corrected configuration is required to resolve it.
    """


class AgentProviderError(AgentFrameworkError):
    """Base class for errors raised while using an agent provider."""


class AgentNotInitializedError(AgentProviderError):
    """Raised when `execute()` is called before `initialize()` (or after `shutdown()`)."""


class SubsystemAlreadyRegisteredError(AgentProviderError):
    """Raised when `register_subsystem()` is called with an already-registered name."""


class SubsystemNotFoundError(AgentProviderError):
    """Raised when an operation references a subsystem name that is not registered."""


class AgentRequestNotFoundError(AgentProviderError):
    """Raised when `cancel()` is called with a request id this agent never issued."""


class AgentProvider(ABC):
    """Structural contract every agent implementation must satisfy.

    An agent maintains its own lifecycle (`initialize()`/`shutdown()`/
    `reset()`/`status()`), a name -> availability-check subsystem
    registry (`register_subsystem()`/`unregister_subsystem()`/
    `list_subsystems()`), and accepts requests (`execute()`/
    `cancel()`) -- it never performs planning, reasoning, tool
    execution, or prompt construction, and never accesses a registered
    subsystem beyond calling the single status-check callable supplied
    for it at registration time.
    """

    @abstractmethod
    def agent_name(self) -> str:
        """Return this agent's stable identifier (e.g. "jarvis")."""
        raise NotImplementedError

    @abstractmethod
    def initialize(self) -> None:
        """Transition this agent into `AgentState.READY`.

        Idempotent: calling `initialize()` while already READY or
        RUNNING has no effect. Calling it after `shutdown()` is
        explicitly supported (re-initialization).
        """
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> None:
        """Transition this agent into `AgentState.SHUTDOWN`.

        Idempotent: calling `shutdown()` while already SHUTDOWN has no
        effect. After this call, `execute()` is rejected until
        `initialize()` is called again.
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        """Clear transient request-tracking state and recover from `AgentState.ERROR`.

        Never initializes an UNINITIALIZED agent and never resurrects
        a SHUTDOWN agent -- those lifecycle boundaries are only
        crossed by `initialize()`.
        """
        raise NotImplementedError

    @abstractmethod
    def status(self) -> AgentState:
        """Return this agent's current `AgentState`."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, request: str, metadata: dict | None = None) -> AgentExecutionResult:
        """Accept and acknowledge a request.

        Args:
            request: The request text. Never parsed, planned, or acted
                on -- this EP performs no reasoning.
            metadata: Optional caller-supplied metadata, carried
                through unchanged (never inspected).

        Returns:
            The resulting AgentExecutionResult.

        Raises:
            AgentNotInitializedError: If this agent is not currently
                READY (i.e. UNINITIALIZED or SHUTDOWN).
        """
        raise NotImplementedError

    @abstractmethod
    def cancel(self, request_id: str) -> AgentCancelResult:
        """Attempt to cancel a previously accepted request.

        Args:
            request_id: A request id previously returned by
                `execute()`.

        Returns:
            The resulting AgentCancelResult.

        Raises:
            AgentRequestNotFoundError: If `request_id` was never
                issued by this agent.
        """
        raise NotImplementedError

    @abstractmethod
    def register_subsystem(
        self, name: str, status_check: Callable[[], bool] | None = None
    ) -> None:
        """Register a subsystem this agent coordinates.

        Args:
            name: The subsystem's name (e.g. "knowledge", "semantic").
            status_check: An optional zero-argument callable returning
                whether the subsystem currently reports itself
                enabled, read only through the subsystem's own public
                API (e.g. `lambda: some_service.status().enabled`).
                When None, the subsystem is a "declared present"
                registration with no live binding, and is always
                reported available.

        Raises:
            SubsystemAlreadyRegisteredError: If `name` is already registered.
        """
        raise NotImplementedError

    @abstractmethod
    def unregister_subsystem(self, name: str) -> None:
        """Remove a previously registered subsystem.

        Args:
            name: The subsystem's registered name.

        Raises:
            SubsystemNotFoundError: If `name` is not registered.
        """
        raise NotImplementedError

    @abstractmethod
    def list_subsystems(self) -> list[SubsystemInfo]:
        """Return every registered subsystem's diagnostic snapshot, ordered by name."""
        raise NotImplementedError


class DefaultAgentProvider(AgentProvider):
    """Built-in agent: lifecycle + subsystem registry + request acknowledgment only.

    Registered by `AgentManager` under the name "jarvis" (see
    'agent.default_agent' in config/config.yaml). Implements no
    planning, reasoning, tool execution, or prompt construction:
    `execute()` always synchronously accepts and immediately
    acknowledges a request (`AgentExecutionResult.dispatched` is
    always False), and `cancel()` always reports nothing left to
    cancel for a known request id (there is nothing asynchronous to
    interrupt).
    """

    _NAME: str = "jarvis"

    def __init__(self) -> None:
        """Initialize the DefaultAgentProvider in `AgentState.UNINITIALIZED`."""
        self._lock = Lock()
        self._state: AgentState = AgentState.UNINITIALIZED
        self._subsystems: dict[str, Callable[[], bool] | None] = {}
        self._request_counter: int = 0
        self._completed_requests: "OrderedDict[str, None]" = OrderedDict()

    def agent_name(self) -> str:
        """Return this agent's stable identifier: "jarvis"."""
        return self._NAME

    def initialize(self) -> None:
        """Transition into `AgentState.READY` (idempotent; re-initialization after shutdown is allowed)."""
        with self._lock:
            if self._state in (AgentState.READY, AgentState.RUNNING):
                return
            self._state = AgentState.READY
        logger.info(f"Agent '{self._NAME}' initialized.")

    def shutdown(self) -> None:
        """Transition into `AgentState.SHUTDOWN` (idempotent)."""
        with self._lock:
            if self._state == AgentState.SHUTDOWN:
                return
            self._state = AgentState.SHUTDOWN
        logger.info(f"Agent '{self._NAME}' shut down.")

    def reset(self) -> None:
        """Clear request-tracking state; recover from ERROR/RUNNING back to READY.

        Never initializes an UNINITIALIZED agent and never resurrects
        a SHUTDOWN agent.
        """
        with self._lock:
            self._completed_requests.clear()
            self._request_counter = 0
            if self._state in (AgentState.RUNNING, AgentState.ERROR):
                self._state = AgentState.READY
        logger.info(f"Agent '{self._NAME}' reset.")

    def status(self) -> AgentState:
        """Return this agent's current AgentState."""
        with self._lock:
            return self._state

    def execute(self, request: str, metadata: dict | None = None) -> AgentExecutionResult:
        """Accept and synchronously acknowledge `request`; no planning or task execution occurs.

        Args:
            request: The request text. Never parsed, planned, or acted on.
            metadata: Optional caller-supplied metadata. Never inspected.

        Returns:
            An AgentExecutionResult with `dispatched=False` and
            `success=True`.

        Raises:
            AgentNotInitializedError: If this agent is not currently READY.
        """
        with self._lock:
            if self._state != AgentState.READY:
                raise AgentNotInitializedError(
                    f"Agent '{self._NAME}' is {self._state.value}; call initialize() first."
                )
            self._state = AgentState.RUNNING
            self._request_counter += 1
            request_id = f"req-{self._request_counter}"

        result = AgentExecutionResult(
            request_id=request_id,
            success=True,
            dispatched=False,
            state=AgentState.READY,
            message=(
                "Request accepted. No Planner/Reasoning Engine is registered yet "
                "(future EP); the Agent Framework performed no reasoning, planning, "
                "or task execution."
            ),
        )

        with self._lock:
            self._completed_requests[request_id] = None
            if len(self._completed_requests) > _MAX_TRACKED_REQUESTS:
                self._completed_requests.popitem(last=False)
            self._state = AgentState.READY

        return result

    def cancel(self, request_id: str) -> AgentCancelResult:
        """Report that `request_id` has nothing left to cancel (every request is synchronous).

        Args:
            request_id: A request id previously returned by `execute()`.

        Returns:
            An AgentCancelResult with `success=False`.

        Raises:
            AgentRequestNotFoundError: If `request_id` was never issued
                by this agent.
        """
        with self._lock:
            known = request_id in self._completed_requests
        if not known:
            raise AgentRequestNotFoundError(f"Unknown request id: '{request_id}'.")
        return AgentCancelResult(
            request_id=request_id,
            success=False,
            message="Request already completed synchronously; nothing to cancel.",
        )

    def register_subsystem(
        self, name: str, status_check: Callable[[], bool] | None = None
    ) -> None:
        """Register a subsystem this agent coordinates.

        Args:
            name: The subsystem's name.
            status_check: Optional zero-argument callable reporting
                whether the subsystem is currently enabled, read only
                through its own public API.

        Raises:
            SubsystemAlreadyRegisteredError: If `name` is already registered.
        """
        with self._lock:
            if name in self._subsystems:
                raise SubsystemAlreadyRegisteredError(f"Subsystem already registered: '{name}'.")
            self._subsystems[name] = status_check
        logger.info(f"Agent '{self._NAME}' subsystem registered: '{name}'.")

    def unregister_subsystem(self, name: str) -> None:
        """Remove a previously registered subsystem.

        Args:
            name: The subsystem's registered name.

        Raises:
            SubsystemNotFoundError: If `name` is not registered.
        """
        with self._lock:
            if name not in self._subsystems:
                raise SubsystemNotFoundError(f"Unknown subsystem: '{name}'.")
            del self._subsystems[name]
        logger.info(f"Agent '{self._NAME}' subsystem unregistered: '{name}'.")

    def list_subsystems(self) -> list[SubsystemInfo]:
        """Return every registered subsystem's diagnostic snapshot, ordered by name.

        A `status_check` that raises is treated as "unavailable"
        rather than propagating -- a single misbehaving subsystem must
        never break `agent subsystems` for every other subsystem.
        """
        with self._lock:
            items = list(self._subsystems.items())

        infos: list[SubsystemInfo] = []
        for name, status_check in sorted(items, key=lambda pair: pair[0]):
            available = True
            if status_check is not None:
                try:
                    available = bool(status_check())
                except Exception as exc:  # noqa: BLE001 - a subsystem's own check must not break listing
                    logger.warning(f"Subsystem '{name}' status check failed: {exc}")
                    available = False
            infos.append(SubsystemInfo(name=name, available=available))
        return infos
