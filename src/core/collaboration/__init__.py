"""EP-032 Multi-Agent Collaboration.

Implements the Multi-Agent Coordinator explicitly deferred, by name, in
the docstrings of EP-028 (`src/core/agent/__init__.py`), EP-029
(`src/core/planning/__init__.py`), and EP-030
(`src/core/plan_execution/__init__.py`): coordinating collaboration
across multiple already-registered `AgentProvider` instances (EP-028's
`AgentManager` catalog). This is distinct from EP-028's own subsystem
registry (`AgentProvider.register_subsystem()`), which coordinates
*subsystems* a single agent is aware of; this package coordinates
*agents* themselves -- a different axis entirely.

This package must NOT call an AI provider, build a prompt, plan a
request, decompose it into steps, walk a Plan, or invoke a real
subsystem action -- those remain, respectively, the Conversation/Prompt
Engine's, EP-029 Planning Engine's, EP-030 Plan Execution Engine's, and
EP-031 Tool Engine's jobs. It performs no AI reasoning, no negotiation,
and no inter-agent messaging: it only distributes an already-formed
request to every currently registered agent (deterministic broadcast)
and collects each agent's own `AgentExecutionResult` into a uniform
outcome.

It may use only the public APIs of completed Engineering Packages --
specifically EP-028's Agent Framework, through
`AgentManager.list_providers()` and each `AgentProvider`'s own public
`agent_name()`/`status()`/`execute()` methods only -- never any
subsystem's internals, and never a private attribute of `AgentManager`
or any `AgentProvider`.

SCOPE NOTE: this Engineering Package coordinates whole requests across
agents (broadcast), not individual EP-029 `PlanStep`s across agents.
Distributing a single `Plan`'s steps across multiple agents would
require widening `PlanStep`'s schema with an agent assignment -- an
EP-029/EP-030 architecture change explicitly out of scope here, per
this project's Unknown API Policy ("never invent APIs... leave a
TODO"). Only one real agent ("jarvis", EP-028's
`DefaultAgentProvider`) is registered in this project today; this
package's value is architectural (a working, tested multi-agent
coordination pipeline) until a second `AgentProvider` implementation
exists.

`AgentOutcomeStatus` / `AgentOutcome` / `CollaborationResult`
(`collaboration_result.py`) are the plain data types shared by the
rest of this package. `CollaborationProvider`
(`collaboration_provider.py`) is the structural contract every
multi-agent distribution strategy must implement;
`DefaultCollaborationProvider` is the built-in, deterministic broadcast
provider, registered under the name "collaboration"
(matching 'collaboration.default_provider' in config/config.yaml).
`CollaborationManager` (`collaboration_manager.py`) owns provider
registration and active-provider selection, mirroring EP-029 through
EP-031's *Manager classes -- it owns no reference to `AgentManager` or
its catalog. `CollaborationEngine` (`collaboration_engine.py`) is the
provider-independent pipeline that reads the live agent catalog from
EP-028's `AgentManager` (public `list_providers()` only) and dispatches
to the active `CollaborationProvider`.

Public API:
    AgentOutcomeStatus -- Outcome of dispatching a request to a single agent.
    AgentOutcome -- The outcome of attempting to dispatch to a single agent.
    CollaborationResult -- The outcome of a single collaborate() call.
    CollaborationProvider -- Structural contract every distribution
        strategy must implement.
    DefaultCollaborationProvider -- The built-in, deterministic broadcast provider.
    CollaborationError -- Base class for every Multi-Agent Collaboration exception.
    CollaborationConfigurationError -- Invalid 'collaboration.*' configuration.
    CollaborationProviderError -- Base class for provider-level errors.
    CollaborationManager -- Owns provider selection and configuration loading.
    CollaborationProviderRegistryError -- Duplicate provider registration.
    CollaborationProviderNotFoundError -- Unknown provider name.
    CollaborationEngine -- The request -> multi-agent-dispatch pipeline.
    CollaborationEngineError -- Base class for engine-level errors.
    NoCollaborationProviderSelectedError -- No provider is currently selected.
    EmptyCollaborationRequestError -- Empty/whitespace-only request submitted.
    NoAgentsAvailableError -- No agent is registered with the Agent Framework at all.
"""

from __future__ import annotations

from src.core.collaboration.collaboration_engine import (
    CollaborationEngine,
    CollaborationEngineError,
    EmptyCollaborationRequestError,
    NoAgentsAvailableError,
    NoCollaborationProviderSelectedError,
)
from src.core.collaboration.collaboration_manager import (
    CollaborationManager,
    CollaborationProviderNotFoundError,
    CollaborationProviderRegistryError,
)
from src.core.collaboration.collaboration_provider import (
    CollaborationConfigurationError,
    CollaborationError,
    CollaborationProvider,
    CollaborationProviderError,
    DefaultCollaborationProvider,
)
from src.core.collaboration.collaboration_result import (
    AgentOutcome,
    AgentOutcomeStatus,
    CollaborationResult,
)

__all__ = [
    "AgentOutcomeStatus",
    "AgentOutcome",
    "CollaborationResult",
    "CollaborationProvider",
    "DefaultCollaborationProvider",
    "CollaborationError",
    "CollaborationConfigurationError",
    "CollaborationProviderError",
    "CollaborationManager",
    "CollaborationProviderRegistryError",
    "CollaborationProviderNotFoundError",
    "CollaborationEngine",
    "CollaborationEngineError",
    "NoCollaborationProviderSelectedError",
    "EmptyCollaborationRequestError",
    "NoAgentsAvailableError",
]
