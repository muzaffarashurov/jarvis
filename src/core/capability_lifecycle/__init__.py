"""EP-069.7 Capability Lifecycle Management.

Tracks a capability's lifecycle status (`ACTIVE`/`DISABLED`/`REVOKED`)
and an ordered, append-only audit trail of the events that produced
it (registration, update, enable, disable, revocation) --
independently of `Capability` (EP-069.4, `src/core/capability/`)
itself, which is immutable and never mutated by this package, and
independently of `CapabilityRegistry`, which this package has zero
dependency on. See `docs/architecture/designs/EP069_7_DESIGN.md` for
the full architecture, scope boundary, and Owner Decisions (OD1-OD7).

**Architectural boundary.** This package is a standalone lifecycle
state/history abstraction. It does NOT: import, reference, wrap, or
call `CapabilityRegistry` in any way (no `register()`/`unregister()`/
`get()`/`find()`/`list()`/`is_registered()` call anywhere); mutate the
live capability catalog when a capability is disabled or revoked here;
mutate any `Capability` instance; perform discovery or ranking
(EP-069.5); perform security/risk assessment (EP-069.6); enforce any
policy or make any approval/rejection decision (a future EP-070's
named, exclusive responsibility); persist anything to a file,
database, or cache; or depend on wall-clock time for event ordering
(ordering is by a monotonic `sequence: int` counter only, Owner
Decision OD5). It is not wired into `src/bootstrap.py`,
`config/config.yaml`, or any CLI surface, and introduces no
Provider/Engine/Manager/ABC framework (Owner Decision OD4) -- this
domain has exactly one correct set of transition rules, not a
pluggable strategy.

`CapabilityLifecycleStatus`/`CapabilityLifecycleEventType`/
`CapabilityLifecycleEvent`/`CapabilityLifecycleRecord`
(`capability_lifecycle_result.py`) are the plain, read-only data
types. `CapabilityLifecycleRegistry`
(`capability_lifecycle_registry.py`) is the single, concrete,
thread-safe, in-memory tracker, alongside this package's own
`CapabilityLifecycleError` hierarchy.

Public API:
    CapabilityLifecycleStatus -- ACTIVE/DISABLED/REVOKED; REVOKED is strictly terminal.
    CapabilityLifecycleEventType -- REGISTERED/UPDATED/ENABLED/DISABLED/REVOKED.
    CapabilityLifecycleEvent -- A single, immutable audit-trail entry.
    CapabilityLifecycleRecord -- A read-only snapshot of one capability's lifecycle state.
    CapabilityLifecycleError -- Common root for every exception raised by this package.
    CapabilityLifecycleNotFoundError -- An operation referenced an untracked capability id.
    CapabilityLifecycleConflictError -- An invalid lifecycle transition (duplicate register, or any mutation after REVOKED).
    CapabilityLifecycleValidationError -- revoke() called with a blank reason.
    CapabilityLifecycleRegistry -- The single, concrete, thread-safe lifecycle tracker.
"""

from __future__ import annotations

from src.core.capability_lifecycle.capability_lifecycle_registry import (
    CapabilityLifecycleConflictError,
    CapabilityLifecycleError,
    CapabilityLifecycleNotFoundError,
    CapabilityLifecycleRegistry,
    CapabilityLifecycleValidationError,
)
from src.core.capability_lifecycle.capability_lifecycle_result import (
    CapabilityLifecycleEvent,
    CapabilityLifecycleEventType,
    CapabilityLifecycleRecord,
    CapabilityLifecycleStatus,
)

__all__ = [
    "CapabilityLifecycleStatus",
    "CapabilityLifecycleEventType",
    "CapabilityLifecycleEvent",
    "CapabilityLifecycleRecord",
    "CapabilityLifecycleError",
    "CapabilityLifecycleNotFoundError",
    "CapabilityLifecycleConflictError",
    "CapabilityLifecycleValidationError",
    "CapabilityLifecycleRegistry",
]
