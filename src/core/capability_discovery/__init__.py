"""EP-069.5 Capability Discovery Engine.

Given a plain-text task description and a `CapabilityRegistry`
(EP-069.4, `src/core/capability/`), finds the registered, `enabled`
capabilities that fit it and ranks them by fit, trust, and an
optional externally supplied cost signal -- the single decision point
Planning/Agents can use instead of hard-coding "which tool for which
task," replacing the fixed keyword tables both currently rely on
(`src/core/planning/planning_provider.py`,
`src/core/agent/agent_provider.py`). See `docs/architecture/designs/
EP069_5_DESIGN.md` for the full architecture and Owner Decisions
(OD1-OD6).

This package is a pure, read-only discovery/ranking layer. It does
NOT: execute a capability (no `CapabilityBackend.invoke()` call is
ever made); mutate `CapabilityRegistry` or any `Capability`; enforce
any security/permission policy; perform any capability lifecycle
action; use semantic/LLM-based matching (Owner Decision OD4); or
introduce any new `Capability` field, including a cost field (Owner
Decision OD3). It is not wired into `src/bootstrap.py`, `config/
config.yaml`, or any CLI surface, and is not integrated with Planning
Engine, Agent Framework, or Tool Engine (Owner Decision OD2) -- all of
that remains deferred to a future Engineering Package. The production
`CapabilityRegistry` population gap identified during this EP's
STEP 1 (nothing registers real capabilities today) is likewise
deliberately not solved here.

`CapabilityMatch`/`CapabilityDiscoveryResult` (`capability_discovery_
result.py`) are the plain, read-only outcome data types.
`CapabilityDiscoveryProvider`/`DefaultCapabilityDiscoveryProvider`
(`capability_discovery_provider.py`) are the structural contract and
its one concrete, deterministic, non-AI implementation, alongside this
package's own `CapabilityDiscoveryError` hierarchy.
`CapabilityDiscoveryEngine` (`capability_discovery_engine.py`) is the
provider-independent orchestration layer -- there is no Manager in
this Engineering Package (Owner Decision OD2); the engine is
constructed directly with the provider it will use.

Public API:
    CapabilityMatch -- A single ranked candidate.
    CapabilityDiscoveryResult -- The outcome of one discover() call.
    CapabilityDiscoveryError -- Common root for every exception raised by this package.
    CapabilityDiscoveryProviderError -- Invalid discover() input (max_results, cost_hints).
    CapabilityDiscoveryProvider -- Structural contract every discovery strategy implements.
    DefaultCapabilityDiscoveryProvider -- Deterministic, non-AI default strategy.
    CapabilityDiscoveryEngine -- Provider-independent orchestration.
"""

from __future__ import annotations

from src.core.capability_discovery.capability_discovery_engine import (
    CapabilityDiscoveryEngine,
)
from src.core.capability_discovery.capability_discovery_provider import (
    CapabilityDiscoveryError,
    CapabilityDiscoveryProvider,
    CapabilityDiscoveryProviderError,
    DefaultCapabilityDiscoveryProvider,
)
from src.core.capability_discovery.capability_discovery_result import (
    CapabilityDiscoveryResult,
    CapabilityMatch,
)

__all__ = [
    "CapabilityMatch",
    "CapabilityDiscoveryResult",
    "CapabilityDiscoveryError",
    "CapabilityDiscoveryProviderError",
    "CapabilityDiscoveryProvider",
    "DefaultCapabilityDiscoveryProvider",
    "CapabilityDiscoveryEngine",
]
