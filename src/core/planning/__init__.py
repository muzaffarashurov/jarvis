"""EP-029 Planning Engine.

Decomposes a request into an ordered `Plan` of steps referencing
already-implemented Engineering Packages by name -- using only
deterministic, fixed keyword rules, and never AI reasoning, an AI
provider call, prompt construction, or task execution. This package
must NOT implement a Reasoning Engine, Reflection Engine, Workflow
Engine, Task Scheduler, Tool Executor, Conversation Engine
integration, Multi-Agent Coordinator, or any future EP's
functionality -- a `Plan` is a proposed sequence of steps only; turning
it into actual work is out of scope here and left to a future
Execution Engine (EP-030). It may use only the public APIs of
completed Engineering Packages -- specifically EP-028's Agent
Framework, through `AgentEngine.list_subsystems()` only, to refine a
plan's per-step availability -- never any subsystem's internals.

`PlanStep` / `Plan` (`planning_result.py`) are the plain data types
shared by the rest of this package. `PlanningProvider`
(`planning_provider.py`) is the structural contract every planning
strategy must implement; `DefaultPlanningProvider` is the built-in,
deterministic keyword-rule provider, registered under the name
"planning". `PlanningManager` (`planning_manager.py`) owns provider
registration, active-provider selection, and the default `max_steps`
limit, mirroring EP-026/EP-027/EP-028's *Manager classes.
`PlanningEngine` (`planning_engine.py`) is the provider-independent
pipeline that builds a `Plan` via the active `PlanningProvider` and
optionally reconciles it against EP-028's Agent Framework.

Public API:
    PlanStep -- A single, ordered step of a Plan.
    Plan -- The outcome of a single PlanningEngine.plan() call.
    PlanningProvider -- Structural contract every planning strategy must implement.
    DefaultPlanningProvider -- The built-in, deterministic keyword-rule provider.
    PlanningProviderStatus -- Lifecycle status a provider reports.
    PlanningProviderHealth -- Configuration-derived readiness result.
    PlanningError -- Base class for every Planning Engine exception.
    PlanningConfigurationError -- Invalid 'planning.*' configuration.
    PlanningProviderError -- Base class for provider-level errors.
    PlanningProviderConfigurationError -- Disabled/unconfigured provider.
    PlanningProviderUnavailableError -- Provider cannot currently serve requests.
    PlanningManager -- Owns provider selection, configuration loading,
        and provider lifecycle.
    PlanningProviderRegistryError -- Duplicate provider registration.
    PlanningProviderNotFoundError -- Unknown provider name.
    PlanningEngine -- The request -> Plan pipeline.
    PlanningEngineError -- Base class for engine-level errors.
    NoPlanningProviderSelectedError -- No provider is currently selected.
    EmptyPlanningRequestError -- Empty/whitespace-only request submitted.
"""

from __future__ import annotations

from src.core.planning.planning_engine import (
    EmptyPlanningRequestError,
    NoPlanningProviderSelectedError,
    PlanningEngine,
    PlanningEngineError,
)
from src.core.planning.planning_manager import (
    PlanningManager,
    PlanningProviderNotFoundError,
    PlanningProviderRegistryError,
)
from src.core.planning.planning_provider import (
    DefaultPlanningProvider,
    PlanningConfigurationError,
    PlanningError,
    PlanningProvider,
    PlanningProviderConfigurationError,
    PlanningProviderError,
    PlanningProviderHealth,
    PlanningProviderStatus,
    PlanningProviderUnavailableError,
)
from src.core.planning.planning_result import Plan, PlanStep

__all__ = [
    "PlanStep",
    "Plan",
    "PlanningProvider",
    "DefaultPlanningProvider",
    "PlanningProviderStatus",
    "PlanningProviderHealth",
    "PlanningError",
    "PlanningConfigurationError",
    "PlanningProviderError",
    "PlanningProviderConfigurationError",
    "PlanningProviderUnavailableError",
    "PlanningManager",
    "PlanningProviderRegistryError",
    "PlanningProviderNotFoundError",
    "PlanningEngine",
    "PlanningEngineError",
    "NoPlanningProviderSelectedError",
    "EmptyPlanningRequestError",
]
