"""Domain model for EP-069.7 Capability Lifecycle Management.

Defines the plain, read-only data types `CapabilityLifecycleRegistry`
(`capability_lifecycle_registry.py`) uses to represent a capability's
lifecycle status and its ordered, append-only event history:
`CapabilityLifecycleStatus` (the current status), `CapabilityLifecycleEventType`
(what kind of transition an event records),
`CapabilityLifecycleEvent` (a single, immutable audit-trail entry),
and `CapabilityLifecycleRecord` (a read-only snapshot of one
capability's full lifecycle state).

**This package tracks lifecycle status/history independently of
`Capability` itself.** `Capability` (EP-069.4,
`src/core/capability/capability.py`) is `frozen=True` and is never
mutated here or anywhere in this package -- only its `id` and
`version` fields are ever read. This package also has **zero
dependency on `CapabilityRegistry`** (EP-069.4's own catalog) -- it
never registers, unregisters, queries, or otherwise touches the live
capability catalog. See `docs/architecture/designs/EP069_7_DESIGN.md`
for the full architecture, scope boundary, and Owner Decisions
(OD1-OD7).

No wall-clock timestamp exists anywhere in this module (Owner Decision
OD5) -- event ordering is by a monotonic `sequence: int` only, kept
deterministic and independent of system time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "CapabilityLifecycleStatus",
    "CapabilityLifecycleEventType",
    "CapabilityLifecycleEvent",
    "CapabilityLifecycleRecord",
]


class CapabilityLifecycleStatus(str, Enum):
    """The current lifecycle status of a tracked capability.

    `REVOKED` is strictly terminal (Owner Decision OD6) -- once a
    capability reaches `REVOKED`, no further transition of any kind is
    permitted; see `CapabilityLifecycleRegistry`.
    """

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    REVOKED = "REVOKED"


class CapabilityLifecycleEventType(str, Enum):
    """The kind of lifecycle transition a single `CapabilityLifecycleEvent` records.

    Names exactly the five responsibilities `docs/BACKLOG.md`'s own
    EP-069.7 bullet lists: registration, versioning (via `UPDATED`),
    enable/disable, and revocation.
    """

    REGISTERED = "REGISTERED"
    UPDATED = "UPDATED"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    REVOKED = "REVOKED"


@dataclass(frozen=True)
class CapabilityLifecycleEvent:
    """A single, immutable audit-trail entry.

    Attributes:
        sequence: A monotonically increasing integer, unique across
            the entire owning `CapabilityLifecycleRegistry` instance
            (not just per capability id) -- the sole ordering key.
            Never derived from wall-clock time (Owner Decision OD5).
        capability_id: The id of the capability this event concerns.
        event_type: What kind of transition this event records.
        version: The capability's version as of this event.
            Unchanged from the immediately preceding event for
            `ENABLED`/`DISABLED`/`REVOKED` events, which never alter
            version.
        reason: An optional, human-readable explanation. Populated for
            `DISABLED`/`REVOKED` events; blank (`""`) for the other
            three event types.
    """

    sequence: int
    capability_id: str
    event_type: CapabilityLifecycleEventType
    version: str
    reason: str = ""


@dataclass(frozen=True)
class CapabilityLifecycleRecord:
    """A read-only snapshot of one capability's full lifecycle state.

    Returned by `CapabilityLifecycleRegistry`'s mutating methods and
    by `history()`'s underlying lookup -- a fresh snapshot each time,
    never a live reference into the registry's own internal state
    (mirroring `CapabilityRegistry.list()`'s own "returns a new list
    each call" convention, so a caller cannot corrupt registry state
    by mutating what it receives).

    Attributes:
        capability_id: The id of the capability this record describes.
        status: The capability's current lifecycle status.
        current_version: The capability's most recently recorded
            version (from the latest `REGISTERED` or `UPDATED` event).
        history: Every event recorded for this capability, ordered by
            `sequence` (oldest first). Always non-empty once
            `register()` has succeeded.
    """

    capability_id: str
    status: CapabilityLifecycleStatus
    current_version: str
    history: list[CapabilityLifecycleEvent] = field(default_factory=list)
