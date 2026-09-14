"""Real engineering tests for EP-069.7 STEP 2 - Capability Lifecycle Management.

Self-contained test suite (`NAME = "EP069_7"`) under `tests/EP069_7/`,
following the established convention of a package per sub-EP. Does
not import `src.bootstrap` or `src.core.capability.capability_registry`
-- `EP069_7_DESIGN.md` Owner Decisions OD1/OD7 explicitly exclude both
from this EP's scope.

Covers every behavioral area required by the approved STEP 1 design
and the STEP 2 implementation prompt (items A-R):
    A. data model construction
    B. initial registration
    C. status()
    D. is_tracked()
    E. update()
    F. disable()
    G. enable()
    H. revoke()
    I. history()
    J. deterministic sequence ordering
    K. duplicate/invalid registration
    L. invalid state transitions (folded into N, the REVOKED terminal
       tests, since no other "invalid transition" exists per the
       approved design)
    M. untracked capability operations
    N. REVOKED terminal behavior (each prohibited operation tested
       individually)
    O. history immutability / defensive exposure
    P. Capability immutability
    Q. lifecycle independence from CapabilityRegistry
    R. repeated/no-op operations
"""

from __future__ import annotations

import inspect
import re

from src.core.capability import Capability, CapabilitySourceKind
from src.core.capability_lifecycle import (
    CapabilityLifecycleConflictError,
    CapabilityLifecycleError,
    CapabilityLifecycleEvent,
    CapabilityLifecycleEventType,
    CapabilityLifecycleNotFoundError,
    CapabilityLifecycleRecord,
    CapabilityLifecycleRegistry,
    CapabilityLifecycleStatus,
    CapabilityLifecycleValidationError,
)
from src.core.capability_lifecycle import capability_lifecycle_registry as _registry_module
from src.core.capability_lifecycle import capability_lifecycle_result as _result_module
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

_IMPORT_LINE_PATTERN = re.compile(r"^(?:from|import)\s+\S.*$", re.MULTILINE)


def _make_capability(id: str, version: str = "1.0.0") -> Capability:
    """Build a test `Capability` via EP-069.4's own, unmodified `Capability.create()`."""
    return Capability.create(
        id=id,
        name="Test Capability",
        description="A capability used for EP-069.7 testing.",
        source_kind=CapabilitySourceKind.INTERNAL,
        version=version,
    )


@TestRegistry.register
class CapabilityLifecycleRegistryTest(BaseTest):
    NAME = "EP069_7"

    def run(self):
        # A. Data model construction
        self._test_event_construction()
        self._test_record_construction()

        # B/C/D. Initial registration, status(), is_tracked()
        self._test_register_creates_active_status_and_event()
        self._test_status_on_untracked_raises()
        self._test_is_tracked_true_and_false()

        # E. update()
        self._test_update_changes_version_and_appends_event()

        # F. disable()
        self._test_disable_transitions_to_disabled()
        self._test_disable_again_appends_new_event()

        # G. enable()
        self._test_enable_transitions_disabled_to_active()
        self._test_enable_on_active_is_noop()

        # H. revoke()
        self._test_revoke_transitions_to_revoked_with_reason()
        self._test_revoke_blank_reason_raises()

        # I. history()
        self._test_history_ordered_and_matches_events()

        # J. Deterministic sequence ordering
        self._test_deterministic_sequence_ordering_full_lifecycle()

        # K. Duplicate/invalid registration
        self._test_duplicate_registration_raises()

        # M. Untracked capability operations
        self._test_update_untracked_raises()
        self._test_disable_untracked_raises()
        self._test_enable_untracked_raises()
        self._test_revoke_untracked_raises()
        self._test_history_untracked_raises()

        # N. REVOKED terminal behavior (each individually)
        self._test_revoked_then_enable_raises()
        self._test_revoked_then_disable_raises()
        self._test_revoked_then_update_raises()
        self._test_revoked_then_revoke_raises()

        # O. History immutability / defensive exposure
        self._test_history_returned_list_is_a_copy()

        # P. Capability immutability
        self._test_capability_object_never_mutated()

        # Q. Lifecycle independence from CapabilityRegistry
        self._test_no_capability_registry_dependency()

        # R. Repeated/no-op operations
        self._test_repeated_enable_calls_remain_noop()

        # Error hierarchy
        self._test_errors_are_lifecycle_errors()

        return self.result

    # ---------- A. Data model construction ----------

    def _test_event_construction(self) -> None:
        event = CapabilityLifecycleEvent(
            sequence=1,
            capability_id="cap",
            event_type=CapabilityLifecycleEventType.REGISTERED,
            version="1.0.0",
        )
        self.assert_equal(event.sequence, 1, "sequence must round-trip.")
        self.assert_equal(event.reason, "", "reason must default to an empty string.")

    def _test_record_construction(self) -> None:
        record = CapabilityLifecycleRecord(
            capability_id="cap",
            status=CapabilityLifecycleStatus.ACTIVE,
            current_version="1.0.0",
        )
        self.assert_equal(record.history, [], "history must default to an empty list.")

    # ---------- B/C/D. Initial registration, status(), is_tracked() ----------

    def _test_register_creates_active_status_and_event(self) -> None:
        registry = CapabilityLifecycleRegistry()
        capability = _make_capability("cap_a")

        event = registry.register(capability)

        self.assert_equal(
            event.event_type, CapabilityLifecycleEventType.REGISTERED, "register() must append a REGISTERED event."
        )
        self.assert_equal(registry.status("cap_a"), CapabilityLifecycleStatus.ACTIVE, "New registrations start ACTIVE.")

    def _test_status_on_untracked_raises(self) -> None:
        registry = CapabilityLifecycleRegistry()
        raised = False
        try:
            registry.status("unknown")
        except CapabilityLifecycleNotFoundError:
            raised = True
        self.assert_true(raised, "status() on an untracked id must raise CapabilityLifecycleNotFoundError.")

    def _test_is_tracked_true_and_false(self) -> None:
        registry = CapabilityLifecycleRegistry()
        self.assert_false(registry.is_tracked("cap_a"), "is_tracked() must be False before registration.")

        registry.register(_make_capability("cap_a"))

        self.assert_true(registry.is_tracked("cap_a"), "is_tracked() must be True after registration.")

    # ---------- E. update() ----------

    def _test_update_changes_version_and_appends_event(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a", version="1.0.0"))

        event = registry.update(_make_capability("cap_a", version="2.0.0"))

        self.assert_equal(event.event_type, CapabilityLifecycleEventType.UPDATED, "update() must append an UPDATED event.")
        self.assert_equal(event.version, "2.0.0", "The event must carry the new version.")
        self.assert_equal(len(registry.history("cap_a")), 2, "History must now have 2 events.")

    # ---------- F. disable() ----------

    def _test_disable_transitions_to_disabled(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))

        event = registry.disable("cap_a", reason="maintenance")

        self.assert_equal(event.event_type, CapabilityLifecycleEventType.DISABLED, "disable() must append a DISABLED event.")
        self.assert_equal(event.reason, "maintenance", "The reason must be carried on the event.")
        self.assert_equal(registry.status("cap_a"), CapabilityLifecycleStatus.DISABLED, "Status must become DISABLED.")

    def _test_disable_again_appends_new_event(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))
        registry.disable("cap_a", reason="first")

        registry.disable("cap_a", reason="second")

        self.assert_equal(
            len(registry.history("cap_a")), 3, "Disabling an already-DISABLED capability must append a new event."
        )

    # ---------- G. enable() ----------

    def _test_enable_transitions_disabled_to_active(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))
        registry.disable("cap_a")

        event = registry.enable("cap_a")

        self.assert_true(event is not None, "enable() from DISABLED must return a real event, not None.")
        self.assert_equal(event.event_type, CapabilityLifecycleEventType.ENABLED, "enable() must append an ENABLED event.")
        self.assert_equal(registry.status("cap_a"), CapabilityLifecycleStatus.ACTIVE, "Status must become ACTIVE.")

    def _test_enable_on_active_is_noop(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))

        result = registry.enable("cap_a")

        self.assert_true(result is None, "enable() on an already-ACTIVE capability must return None (no-op).")
        self.assert_equal(
            len(registry.history("cap_a")), 1, "enable() on ACTIVE must not append a new event."
        )

    # ---------- H. revoke() ----------

    def _test_revoke_transitions_to_revoked_with_reason(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))

        event = registry.revoke("cap_a", reason="compromised")

        self.assert_equal(event.event_type, CapabilityLifecycleEventType.REVOKED, "revoke() must append a REVOKED event.")
        self.assert_equal(event.reason, "compromised", "The reason must be carried on the event.")
        self.assert_equal(registry.status("cap_a"), CapabilityLifecycleStatus.REVOKED, "Status must become REVOKED.")

    def _test_revoke_blank_reason_raises(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))

        raised = False
        try:
            registry.revoke("cap_a", reason="   ")
        except CapabilityLifecycleValidationError:
            raised = True
        self.assert_true(raised, "revoke() with a blank reason must raise CapabilityLifecycleValidationError.")

    # ---------- I. history() ----------

    def _test_history_ordered_and_matches_events(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))
        registry.disable("cap_a")
        registry.enable("cap_a")

        history = registry.history("cap_a")

        self.assert_equal(
            [event.event_type for event in history],
            [
                CapabilityLifecycleEventType.REGISTERED,
                CapabilityLifecycleEventType.DISABLED,
                CapabilityLifecycleEventType.ENABLED,
            ],
            "history() must return events in the order they occurred.",
        )

    # ---------- J. Deterministic sequence ordering ----------

    def _test_deterministic_sequence_ordering_full_lifecycle(self) -> None:
        registry = CapabilityLifecycleRegistry()
        register_event = registry.register(_make_capability("cap_a", version="1.0.0"))
        update_event = registry.update(_make_capability("cap_a", version="2.0.0"))
        disable_event = registry.disable("cap_a")
        enable_event = registry.enable("cap_a")
        revoke_event = registry.revoke("cap_a", reason="done")

        sequences = [
            register_event.sequence,
            update_event.sequence,
            disable_event.sequence,
            enable_event.sequence,
            revoke_event.sequence,
        ]

        self.assert_equal(
            sequences,
            sorted(sequences),
            "Sequence numbers must be strictly increasing in the order operations occurred.",
        )
        self.assert_equal(
            len(set(sequences)), 5, "Every sequence number in one lifecycle must be unique."
        )
        self.assert_equal(
            [event.sequence for event in registry.history("cap_a")],
            sequences,
            "history() must be sorted by sequence, matching the order events actually occurred.",
        )

    # ---------- K. Duplicate/invalid registration ----------

    def _test_duplicate_registration_raises(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))

        raised = False
        try:
            registry.register(_make_capability("cap_a"))
        except CapabilityLifecycleConflictError:
            raised = True
        self.assert_true(raised, "Registering an already-tracked id must raise CapabilityLifecycleConflictError.")

    # ---------- M. Untracked capability operations ----------

    def _test_update_untracked_raises(self) -> None:
        registry = CapabilityLifecycleRegistry()
        raised = False
        try:
            registry.update(_make_capability("unknown"))
        except CapabilityLifecycleNotFoundError:
            raised = True
        self.assert_true(raised, "update() on an untracked id must raise CapabilityLifecycleNotFoundError.")

    def _test_disable_untracked_raises(self) -> None:
        registry = CapabilityLifecycleRegistry()
        raised = False
        try:
            registry.disable("unknown")
        except CapabilityLifecycleNotFoundError:
            raised = True
        self.assert_true(raised, "disable() on an untracked id must raise CapabilityLifecycleNotFoundError.")

    def _test_enable_untracked_raises(self) -> None:
        registry = CapabilityLifecycleRegistry()
        raised = False
        try:
            registry.enable("unknown")
        except CapabilityLifecycleNotFoundError:
            raised = True
        self.assert_true(raised, "enable() on an untracked id must raise CapabilityLifecycleNotFoundError.")

    def _test_revoke_untracked_raises(self) -> None:
        registry = CapabilityLifecycleRegistry()
        raised = False
        try:
            registry.revoke("unknown", reason="reason")
        except CapabilityLifecycleNotFoundError:
            raised = True
        self.assert_true(raised, "revoke() on an untracked id must raise CapabilityLifecycleNotFoundError.")

    def _test_history_untracked_raises(self) -> None:
        registry = CapabilityLifecycleRegistry()
        raised = False
        try:
            registry.history("unknown")
        except CapabilityLifecycleNotFoundError:
            raised = True
        self.assert_true(raised, "history() on an untracked id must raise CapabilityLifecycleNotFoundError.")

    # ---------- N. REVOKED terminal behavior (each individually) ----------

    def _test_revoked_then_enable_raises(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))
        registry.revoke("cap_a", reason="done")

        raised = False
        try:
            registry.enable("cap_a")
        except CapabilityLifecycleConflictError:
            raised = True
        self.assert_true(raised, "enable() on a REVOKED capability must raise CapabilityLifecycleConflictError.")
        self.assert_equal(
            registry.status("cap_a"), CapabilityLifecycleStatus.REVOKED, "Status must remain REVOKED after the failed enable()."
        )

    def _test_revoked_then_disable_raises(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))
        registry.revoke("cap_a", reason="done")

        raised = False
        try:
            registry.disable("cap_a")
        except CapabilityLifecycleConflictError:
            raised = True
        self.assert_true(raised, "disable() on a REVOKED capability must raise CapabilityLifecycleConflictError.")

    def _test_revoked_then_update_raises(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))
        registry.revoke("cap_a", reason="done")

        raised = False
        try:
            registry.update(_make_capability("cap_a", version="9.9.9"))
        except CapabilityLifecycleConflictError:
            raised = True
        self.assert_true(raised, "update() on a REVOKED capability must raise CapabilityLifecycleConflictError.")

    def _test_revoked_then_revoke_raises(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))
        registry.revoke("cap_a", reason="first revocation")

        raised = False
        try:
            registry.revoke("cap_a", reason="second revocation")
        except CapabilityLifecycleConflictError:
            raised = True
        self.assert_true(raised, "revoke() on an already-REVOKED capability must raise CapabilityLifecycleConflictError.")

    # ---------- O. History immutability / defensive exposure ----------

    def _test_history_returned_list_is_a_copy(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))

        first_call = registry.history("cap_a")
        first_call.append(
            CapabilityLifecycleEvent(
                sequence=999,
                capability_id="cap_a",
                event_type=CapabilityLifecycleEventType.REVOKED,
                version="1.0.0",
                reason="injected",
            )
        )
        second_call = registry.history("cap_a")

        self.assert_equal(
            len(second_call), 1, "Mutating a previously returned history list must not affect the registry's own state."
        )

    # ---------- P. Capability immutability ----------

    def _test_capability_object_never_mutated(self) -> None:
        capability = _make_capability("cap_a", version="1.0.0")
        registry = CapabilityLifecycleRegistry()

        registry.register(capability)
        registry.disable("cap_a")
        registry.enable("cap_a")
        registry.revoke("cap_a", reason="done")

        self.assert_equal(capability.id, "cap_a", "The original Capability's id must be unchanged.")
        self.assert_equal(capability.version, "1.0.0", "The original Capability's version must be unchanged.")
        self.assert_true(capability.enabled, "The original Capability's enabled flag must be unchanged.")

    # ---------- Q. Lifecycle independence from CapabilityRegistry ----------

    def _test_no_capability_registry_dependency(self) -> None:
        forbidden_substrings = (
            "capability_registry",
            "capability_backend",
            "capability_discovery",
            "capability_security",
            "src.core.planning",
            "src.core.agent",
            "src.bootstrap",
            "config",
        )
        for module in (_result_module, _registry_module):
            source = inspect.getsource(module)
            import_lines = " ".join(_IMPORT_LINE_PATTERN.findall(source)).lower()
            for forbidden in forbidden_substrings:
                self.assert_false(
                    forbidden in import_lines,
                    f"{module.__name__} must not import anything referencing '{forbidden}'.",
                )

        # A full lifecycle operates correctly with no CapabilityRegistry
        # instance ever constructed anywhere in this test.
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("standalone"))
        self.assert_true(
            registry.is_tracked("standalone"),
            "CapabilityLifecycleRegistry must operate correctly with zero CapabilityRegistry involvement.",
        )

    # ---------- R. Repeated/no-op operations ----------

    def _test_repeated_enable_calls_remain_noop(self) -> None:
        registry = CapabilityLifecycleRegistry()
        registry.register(_make_capability("cap_a"))

        first = registry.enable("cap_a")
        second = registry.enable("cap_a")
        third = registry.enable("cap_a")

        self.assert_equal(
            (first, second, third), (None, None, None), "Every repeated enable() call on an ACTIVE capability must be a no-op."
        )
        self.assert_equal(len(registry.history("cap_a")), 1, "No event must be appended by any of the repeated calls.")

    # ---------- Error hierarchy ----------

    def _test_errors_are_lifecycle_errors(self) -> None:
        for error_class in (
            CapabilityLifecycleNotFoundError,
            CapabilityLifecycleConflictError,
            CapabilityLifecycleValidationError,
        ):
            caught_as_root = False
            try:
                raise error_class("example failure")
            except CapabilityLifecycleError:
                caught_as_root = True
            self.assert_true(
                caught_as_root, f"{error_class.__name__} must be catchable as CapabilityLifecycleError."
            )
