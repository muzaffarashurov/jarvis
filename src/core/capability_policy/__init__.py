"""EP-070 Policy, Permissions & Human Approval Engine (capability policy-decision slice).

Given a `Capability` (EP-069.4, `src/core/capability/`) plus optional,
already-produced `CapabilitySecurityAssessment` (EP-069.6) and
`CapabilityLifecycleStatus` (EP-069.7), computes a deterministic
`PolicyDecision` -- one of five graduated `PolicyLevel` values
(`OBSERVE`, `ANALYZE`, `PREPARE`, `EXECUTE`, `REQUIRE_APPROVAL`) named
by `docs/BACKLOG.md`'s EP-070 bullet. See `docs/architecture/designs/
EP070_DESIGN.md` for the full architecture and Owner Decisions
(OD1-OD9).

**This package computes decisions; it does not enforce them.** It does
NOT: execute a capability; block, pause, or otherwise enforce any
decision; provide a human-approval workflow or notification mechanism
(`REQUIRE_APPROVAL` is a computed label only); call
`CapabilityRegistry`, `CapabilityDiscoveryEngine`,
`CapabilitySecurityEngine`, or `CapabilityLifecycleRegistry` (the
caller supplies their outputs); mutate any input; persist any decision
(no audit trail, no database, no file); or read any configuration.
It is not wired into `src/bootstrap.py`, `config/config.yaml`, any CLI
surface, `ToolEngine`, or `ToolExecutionProvider`.

**Mandatory semantic clarification (Owner-issued):** `PolicyLevel.OBSERVE`
is a **restrictive** policy decision, never execution authorization.
A `REVOKED` or `DISABLED` capability's lifecycle status producing
`OBSERVE` does not mean that capability is executable -- it means the
opposite. This package performs no enforcement of this or any other
decision; any future integration/enforcement code that consumes a
`PolicyDecision` must honor this boundary.

`PolicyLevel`/`PolicyDecision` (`capability_policy_result.py`) are the
plain, read-only data types -- `PolicyLevel` is deliberately unordered
(Owner Decision OD6): no comparison operator, no numeric severity.
`PolicyProvider`/`DefaultPolicyProvider`
(`capability_policy_provider.py`) are the structural contract and its
one concrete, deterministic implementation of Owner Decision OD4's
six-row rule table, alongside this package's own `CapabilityPolicyError`
hierarchy. `PolicyEngine` (`capability_policy_engine.py`) is the
provider-independent orchestration layer -- there is no Manager in
this Engineering Package (Owner Decision OD2); the engine is
constructed directly with the provider it will use.

Public API:
    PolicyLevel -- One of five graduated policy levels; unordered.
    PolicyDecision -- The outcome of one evaluate() call.
    CapabilityPolicyError -- Common root for every exception raised by this package.
    CapabilityPolicyProviderError -- Invalid evaluate() input (a None capability).
    PolicyProvider -- Structural contract every policy-decision strategy implements.
    DefaultPolicyProvider -- Deterministic implementation of Owner Decision OD4's rule table.
    PolicyEngine -- Provider-independent orchestration.
"""

from __future__ import annotations

from src.core.capability_policy.capability_policy_engine import PolicyEngine
from src.core.capability_policy.capability_policy_provider import (
    CapabilityPolicyError,
    CapabilityPolicyProviderError,
    DefaultPolicyProvider,
    PolicyProvider,
)
from src.core.capability_policy.capability_policy_result import (
    PolicyDecision,
    PolicyLevel,
)

__all__ = [
    "PolicyLevel",
    "PolicyDecision",
    "CapabilityPolicyError",
    "CapabilityPolicyProviderError",
    "PolicyProvider",
    "DefaultPolicyProvider",
    "PolicyEngine",
]
