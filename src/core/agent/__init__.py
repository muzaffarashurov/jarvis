"""EP-028 Agent Framework.

The central orchestration layer coordinating already-implemented
Engineering Packages: maintains agent lifecycle
(initialize/shutdown/reset/status), a subsystem registry
(register_subsystem/unregister_subsystem/list_subsystems), and accepts
requests (execute/cancel) -- entirely without planning, reasoning,
task decomposition, tool execution, or prompt construction. This
package must NOT call an AI provider, an LLM, or implement a Planner,
Reasoning Engine, Reflection Engine, Workflow Engine, Task Scheduler,
Tool Executor, Conversation Engine integration, or Multi-Agent
Coordinator -- those are explicitly future Engineering Packages
(EP-029 onward). It may use only the public APIs of completed
Engineering Packages (EP-021 Embedding Engine, EP-022 RAG Engine,
EP-023 Memory Manager, EP-024 Knowledge Base, EP-025 Long-Term Memory,
EP-026 Semantic Search, EP-027 Context Compression), reached only
through a single status-check callable per subsystem -- never their
internals.

`AgentState` (`agent_state.py`) is the lifecycle enum every
`AgentProvider` reports through and transitions via.
`SubsystemInfo` / `AgentExecutionResult` / `AgentCancelResult`
(`agent_result.py`) are the plain data types shared by the rest of
this package. `AgentProvider` (`agent_provider.py`) is the structural
contract every agent implementation must satisfy; `DefaultAgentProvider`
is the built-in agent, registered under the name "jarvis" --
lifecycle + subsystem registry + synchronous request acknowledgment
only. `AgentManager` (`agent_manager.py`) owns agent registration,
active-agent selection, and the resolved 'agent.startup_mode',
mirroring EP-026/EP-027's *Manager classes. `AgentEngine`
(`agent_engine.py`) is the provider-independent pipeline that forwards
every lifecycle/subsystem-registry/request call to the currently
selected `AgentProvider`.

Public API:
    AgentState -- Lifecycle enum every AgentProvider reports through.
    SubsystemInfo -- A single registered subsystem's diagnostic snapshot.
    AgentExecutionResult -- The outcome of a single execute() call.
    AgentCancelResult -- The outcome of a single cancel() call.
    AgentProvider -- Structural contract every agent implementation must satisfy.
    DefaultAgentProvider -- The built-in "jarvis" agent.
    AgentFrameworkError -- Base class for every Agent Framework exception.
    AgentConfigurationError -- Invalid 'agent.*' configuration.
    AgentProviderError -- Base class for agent-level errors.
    AgentNotInitializedError -- execute() called while not READY.
    SubsystemAlreadyRegisteredError -- Duplicate subsystem registration.
    SubsystemNotFoundError -- Unknown subsystem name.
    AgentRequestNotFoundError -- cancel() used with an unknown request id.
    AgentManager -- Owns agent registration, selection, and startup mode.
    AgentProviderRegistryError -- Duplicate agent registration.
    AgentProviderNotFoundError -- Unknown agent name.
    AgentEngine -- The request/lifecycle -> current-agent forwarding pipeline.
    AgentEngineError -- Base class for engine-level errors.
    NoAgentSelectedError -- No agent is currently selected.
    EmptyRequestError -- Empty/whitespace-only request submitted.
"""

from __future__ import annotations

from src.core.agent.agent_engine import (
    AgentEngine,
    AgentEngineError,
    EmptyRequestError,
    NoAgentSelectedError,
)
from src.core.agent.agent_manager import (
    AgentManager,
    AgentProviderNotFoundError,
    AgentProviderRegistryError,
)
from src.core.agent.agent_provider import (
    AgentConfigurationError,
    AgentFrameworkError,
    AgentNotInitializedError,
    AgentProvider,
    AgentProviderError,
    AgentRequestNotFoundError,
    DefaultAgentProvider,
    SubsystemAlreadyRegisteredError,
    SubsystemNotFoundError,
)
from src.core.agent.agent_result import AgentCancelResult, AgentExecutionResult, SubsystemInfo
from src.core.agent.agent_state import AgentState

__all__ = [
    "AgentState",
    "SubsystemInfo",
    "AgentExecutionResult",
    "AgentCancelResult",
    "AgentProvider",
    "DefaultAgentProvider",
    "AgentFrameworkError",
    "AgentConfigurationError",
    "AgentProviderError",
    "AgentNotInitializedError",
    "SubsystemAlreadyRegisteredError",
    "SubsystemNotFoundError",
    "AgentRequestNotFoundError",
    "AgentManager",
    "AgentProviderRegistryError",
    "AgentProviderNotFoundError",
    "AgentEngine",
    "AgentEngineError",
    "NoAgentSelectedError",
    "EmptyRequestError",
]
