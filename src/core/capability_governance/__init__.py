"""EP-069.8 Capability Governance Integration (Wiring).

Wires the already-implemented, already-audited EP-069.4
(`CapabilityRegistry`), EP-069.6 (`CapabilitySecurityEngine`), EP-070
(`PolicyEngine`), and EP-069.7 (`CapabilityLifecycleRegistry`)
packages into one real enforcement chain, reached from
`CommandRouter.dispatch()` (`src/core/command_router.py`). None of
those four packages, nor EP-069.5 (`CapabilityDiscoveryEngine`, which
is deliberately not part of this chain -- see
`capability_governance_coordinator.py`'s own module docstring), is
modified by this package.

This package owns exactly two new responsibilities, and nothing else:
    1. `CommandCapabilityMap` -- the sole source of truth for the
       `(module_name, action) -> capability_id` relationship (see
       `docs/architecture/designs/EP069.8_STEP1_1_RESOLUTION.md`).
    2. `CapabilityGovernanceCoordinator` -- the single seam
       `CommandRouter` depends on, composing the four existing engines
       plus `CommandCapabilityMap` into one allow/deny decision per
       dispatch.

See `docs/architecture/designs/EP069.8_DESIGN.md` and
`docs/architecture/designs/EP069.8_STEP1_1_RESOLUTION.md` for the full
architecture.

Public API:
    CapabilityGovernanceError -- Common root for every exception raised by this package.
    CommandCapabilityMapError -- Invalid CommandCapabilityMap registration.
    CommandCapabilityMapValidationError -- A mapped capability id is not registered (startup validation).
    CommandCapabilityMap -- The (module_name, action) -> capability_id resolver.
    GovernanceOutcome -- The four possible high-level authorize_dispatch() outcomes.
    GovernanceDecision -- The outcome of one authorize_dispatch() call.
    CapabilityGovernanceCoordinator -- The orchestration seam CommandRouter depends on.
"""

from __future__ import annotations

from src.core.capability_governance.capability_governance_coordinator import (
    CapabilityGovernanceCoordinator,
    GovernanceDecision,
    GovernanceOutcome,
)
from src.core.capability_governance.command_capability_map import (
    CapabilityGovernanceError,
    CommandCapabilityMap,
    CommandCapabilityMapError,
    CommandCapabilityMapValidationError,
)

__all__ = [
    "CapabilityGovernanceError",
    "CommandCapabilityMapError",
    "CommandCapabilityMapValidationError",
    "CommandCapabilityMap",
    "GovernanceOutcome",
    "GovernanceDecision",
    "CapabilityGovernanceCoordinator",
]
