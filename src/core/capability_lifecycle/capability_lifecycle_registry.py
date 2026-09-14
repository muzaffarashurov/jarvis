"""Capability Lifecycle Registry for EP-069.7.

`CapabilityLifecycleRegistry` is a single, concrete, thread-safe,
in-memory tracker of capability lifecycle status and history -- there
is no Provider/Engine/Manager/ABC framework here (Owner Decision OD4):
this domain has exactly one correct set of transition rules, not a
pluggable strategy to select between.

**Zero dependency on `CapabilityRegistry`** (Owner Decision OD1) --
this module never imports, references, or calls
`src.core.capability.capability_registry`. It operates purely on
`Capability` objects/ids handed to it by a caller. `disable()` and
`revoke()` never modify the live capability catalog in any way (Owner
Decision OD2) -- a future integration layer, not this package, is
responsible for reconciling lifecycle status here with catalog
membership in `CapabilityRegistry`.

`Capability` (EP-069.4) is `frozen=True` and is never mutated --  only
its `id` and `version` fields are ever read, in `register()`/
`update()` only.

No wall-clock timestamp exists anywhere in this module (Owner Decision
OD7) -- ordering is by a monotonic `sequence: int` counter only.
"""

from __future__ import annotations

from threading import Lock

from src.core.capability.capability import Capability
from src.core.capability_lifecycle.capability_lifecycle_result import (
    CapabilityLifecycleEvent,
    CapabilityLifecycleEventType,
    CapabilityLifecycleRecord,
    CapabilityLifecycleStatus,
)

__all__ = [
    "CapabilityLifecycleError",
    "CapabilityLifecycleNotFoundError",
    "CapabilityLifecycleConflictError",
    "CapabilityLifecycleValidationError",
    "CapabilityLifecycleRegistry",
]


class CapabilityLifecycleError(Exception):
    """Common root for every exception raised by the Capability Lifecycle package (EP-069.7).

    Downstream packages can catch this single type to handle "anything
    capability-lifecycle-related" without needing to know about every
    specific failure mode, mirroring `CapabilityError`'s (EP-069.4),
    `CapabilityDiscoveryError`'s (EP-069.5), and
    `CapabilitySecurityError`'s (EP-069.6) identical role.
    """


class CapabilityLifecycleNotFoundError(CapabilityLifecycleError):
    """Raised when an operation references a capability id that has never been `register()`-ed."""


class CapabilityLifecycleConflictError(CapabilityLifecycleError):
    """Raised for an invalid lifecycle transition.

    Covers a duplicate `register()` call, any mutating call on an
    already-`REVOKED` capability (`REVOKED` is strictly terminal --
    Owner Decision OD6), and a repeated `revoke()` call.
    """


class CapabilityLifecycleValidationError(CapabilityLifecycleError):
    """Raised when `revoke()` is called with a blank `reason`."""


class _MutableRecord:
    """Internal, mutable bookkeeping for one tracked capability.

    Never exposed outside this module -- `CapabilityLifecycleRegistry`
    always converts this into a fresh, immutable
    `CapabilityLifecycleRecord` before returning it to a caller, so a
    caller can never corrupt registry state by mutating what it
    receives.
    """

    __slots__ = ("capability_id", "status", "current_version", "history")

    def __init__(self, capability_id: str, current_version: str) -> None:
        self.capability_id = capability_id
        self.status = CapabilityLifecycleStatus.ACTIVE
        self.current_version = current_version
        self.history: list[CapabilityLifecycleEvent] = []

    def to_record(self) -> CapabilityLifecycleRecord:
        return CapabilityLifecycleRecord(
            capability_id=self.capability_id,
            status=self.status,
            current_version=self.current_version,
            history=list(self.history),
        )


class CapabilityLifecycleRegistry:
    """Thread-safe, in-memory tracker of capability lifecycle status and history.

    Holds an id-keyed dict of internal, mutable bookkeeping records
    plus a single, shared, monotonically increasing sequence counter.
    Every public method returns a fresh, immutable
    `CapabilityLifecycleRecord`/`CapabilityLifecycleEvent` snapshot --
    never a live reference into this registry's own internal state.

    State is in-memory only; nothing is persisted to a file, database,
    or cache, and all state is lost on process restart, exactly like
    `CapabilityRegistry`'s own catalog (EP-069.4) -- which this class
    has no dependency on or awareness of.
    """

    def __init__(self) -> None:
        """Initialize an empty CapabilityLifecycleRegistry."""
        self._records: dict[str, _MutableRecord] = {}
        self._next_sequence = 1
        self._lock = Lock()

    def register(self, capability: Capability) -> CapabilityLifecycleEvent:
        """Begin tracking a capability's lifecycle.

        Args:
            capability: The capability to begin tracking. Only its
                `id` and `version` fields are read; the object itself
                is never mutated.

        Returns:
            The `REGISTERED` event this call appended.

        Raises:
            CapabilityLifecycleConflictError: If `capability.id` is
                already tracked.
        """
        with self._lock:
            if capability.id in self._records:
                raise CapabilityLifecycleConflictError(
                    f"Capability already tracked: '{capability.id}'."
                )
            record = _MutableRecord(capability_id=capability.id, current_version=capability.version)
            event = self._append_event_locked(
                record, CapabilityLifecycleEventType.REGISTERED, capability.version
            )
            self._records[capability.id] = record
            return event

    def update(self, capability: Capability) -> CapabilityLifecycleEvent:
        """Record an update to an already-tracked capability's version.

        Args:
            capability: The capability's new state. Only its `id` and
                `version` fields are read.

        Returns:
            The `UPDATED` event this call appended.

        Raises:
            CapabilityLifecycleNotFoundError: If `capability.id` is
                not tracked.
            CapabilityLifecycleConflictError: If the tracked
                capability's status is `REVOKED`.
        """
        with self._lock:
            record = self._get_locked(capability.id)
            self._reject_if_revoked_locked(record)
            record.current_version = capability.version
            return self._append_event_locked(
                record, CapabilityLifecycleEventType.UPDATED, capability.version
            )

    def disable(self, capability_id: str, reason: str = "") -> CapabilityLifecycleEvent:
        """Transition a tracked capability to `DISABLED`.

        Calling this on an already-`DISABLED` capability is a
        harmless, valid operation that still appends a new `DISABLED`
        event (an operator may disable again with a different
        `reason`).

        Args:
            capability_id: The id of the capability to disable.
            reason: An optional, human-readable explanation.

        Returns:
            The `DISABLED` event this call appended.

        Raises:
            CapabilityLifecycleNotFoundError: If `capability_id` is
                not tracked.
            CapabilityLifecycleConflictError: If the tracked
                capability's status is `REVOKED`.
        """
        with self._lock:
            record = self._get_locked(capability_id)
            self._reject_if_revoked_locked(record)
            record.status = CapabilityLifecycleStatus.DISABLED
            return self._append_event_locked(
                record, CapabilityLifecycleEventType.DISABLED, record.current_version, reason=reason
            )

    def enable(self, capability_id: str) -> CapabilityLifecycleEvent | None:
        """Transition a tracked capability to `ACTIVE`.

        Calling this on an already-`ACTIVE` capability is a no-op that
        does **not** append a duplicate event -- this avoids polluting
        the audit trail with a meaningless repeat of an already-true
        fact.

        Args:
            capability_id: The id of the capability to enable.

        Returns:
            The `ENABLED` event this call appended, or `None` if the
            capability was already `ACTIVE` (no-op).

        Raises:
            CapabilityLifecycleNotFoundError: If `capability_id` is
                not tracked.
            CapabilityLifecycleConflictError: If the tracked
                capability's status is `REVOKED`.
        """
        with self._lock:
            record = self._get_locked(capability_id)
            self._reject_if_revoked_locked(record)
            if record.status == CapabilityLifecycleStatus.ACTIVE:
                return None
            record.status = CapabilityLifecycleStatus.ACTIVE
            return self._append_event_locked(
                record, CapabilityLifecycleEventType.ENABLED, record.current_version
            )

    def revoke(self, capability_id: str, reason: str) -> CapabilityLifecycleEvent:
        """Transition a tracked capability to `REVOKED` (terminal).

        Args:
            capability_id: The id of the capability to revoke.
            reason: A required, human-readable explanation.

        Returns:
            The `REVOKED` event this call appended.

        Raises:
            CapabilityLifecycleNotFoundError: If `capability_id` is
                not tracked.
            CapabilityLifecycleValidationError: If `reason` is blank.
            CapabilityLifecycleConflictError: If the tracked
                capability's status is already `REVOKED`.
        """
        if not reason.strip():
            raise CapabilityLifecycleValidationError("'reason' is required to revoke a capability.")

        with self._lock:
            record = self._get_locked(capability_id)
            self._reject_if_revoked_locked(record)
            record.status = CapabilityLifecycleStatus.REVOKED
            return self._append_event_locked(
                record, CapabilityLifecycleEventType.REVOKED, record.current_version, reason=reason
            )

    def status(self, capability_id: str) -> CapabilityLifecycleStatus:
        """Return a tracked capability's current lifecycle status.

        Args:
            capability_id: The id of the capability to look up.

        Returns:
            The capability's current `CapabilityLifecycleStatus`.

        Raises:
            CapabilityLifecycleNotFoundError: If `capability_id` is
                not tracked.
        """
        with self._lock:
            return self._get_locked(capability_id).status

    def history(self, capability_id: str) -> list[CapabilityLifecycleEvent]:
        """Return a tracked capability's full event history.

        Args:
            capability_id: The id of the capability to look up.

        Returns:
            A fresh list of every event recorded for this capability,
            ordered by `sequence` (oldest first). Mutating the
            returned list has no effect on this registry's own
            internal state.

        Raises:
            CapabilityLifecycleNotFoundError: If `capability_id` is
                not tracked.
        """
        with self._lock:
            return list(self._get_locked(capability_id).history)

    def is_tracked(self, capability_id: str) -> bool:
        """Return whether a capability id is currently tracked.

        Args:
            capability_id: The id to check.

        Returns:
            True if `capability_id` has been `register()`-ed. Never
            raises.
        """
        with self._lock:
            return capability_id in self._records

    # ---------- Internal helpers (caller must already hold self._lock) ----------

    def _get_locked(self, capability_id: str) -> _MutableRecord:
        record = self._records.get(capability_id)
        if record is None:
            raise CapabilityLifecycleNotFoundError(f"Capability not tracked: '{capability_id}'.")
        return record

    def _reject_if_revoked_locked(self, record: _MutableRecord) -> None:
        if record.status == CapabilityLifecycleStatus.REVOKED:
            raise CapabilityLifecycleConflictError(
                f"Capability already revoked and cannot be further modified: '{record.capability_id}'."
            )

    def _append_event_locked(
        self,
        record: _MutableRecord,
        event_type: CapabilityLifecycleEventType,
        version: str,
        reason: str = "",
    ) -> CapabilityLifecycleEvent:
        event = CapabilityLifecycleEvent(
            sequence=self._next_sequence,
            capability_id=record.capability_id,
            event_type=event_type,
            version=version,
            reason=reason,
        )
        self._next_sequence += 1
        record.history.append(event)
        return event
