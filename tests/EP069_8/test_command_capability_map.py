"""EP-069.8 test suite: CommandCapabilityMap.

Self-contained test suite (`NAME = "EP069_8"`) under `tests/EP069_8/`,
following the established per-EP test-package convention (e.g.
`tests/EP070/test_capability_policy_engine.py`, `tests/EP069_7/
test_capability_lifecycle_registry.py`). Does not import
`src.bootstrap` -- `CommandCapabilityMap` (`src/core/
capability_governance/command_capability_map.py`) has no dependency
on it.

Covers `docs/architecture/designs/EP069.8_STEP1_1_RESOLUTION.md`'s
Category A requirements: registration, resolution, normalization,
duplicate rejection, invalid-identifier handling, intentional
capability sharing across commands, and startup validation against a
`CapabilityRegistry`.
"""

from __future__ import annotations

from src.core.capability import Capability, CapabilityRegistry, CapabilitySourceKind
from src.core.capability_governance.command_capability_map import (
    CommandCapabilityMap,
    CommandCapabilityMapError,
    CommandCapabilityMapValidationError,
)
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


def _make_capability(capability_id: str) -> Capability:
    """Build a test `Capability` via EP-069.4's own, unmodified `Capability.create()`."""
    return Capability.create(
        id=capability_id,
        name="Test Capability",
        description="A capability used for EP-069.8 testing.",
        source_kind=CapabilitySourceKind.INTERNAL,
    )


@TestRegistry.register
class CommandCapabilityMapTest(BaseTest):
    """EP-069.8 `CommandCapabilityMap` suite (`NAME = "EP069_8"`)."""

    NAME = "EP069_8"

    def run(self):
        self._test_register_and_resolve_valid_mapping()
        self._test_resolve_unknown_mapping_returns_none()
        self._test_resolve_never_raises_for_unmapped_pair()
        self._test_module_and_action_normalization()
        self._test_duplicate_mapping_registration_is_rejected()
        self._test_duplicate_registration_does_not_overwrite_existing_entry()
        self._test_blank_module_name_is_rejected()
        self._test_blank_capability_id_is_rejected()
        self._test_empty_action_is_a_valid_identifier()
        self._test_multiple_commands_may_share_one_capability()
        self._test_is_empty_reflects_registration_state()
        self._test_entries_returns_every_registered_mapping()
        self._test_validate_against_registry_passes_when_all_ids_exist()
        self._test_validate_against_registry_passes_for_empty_map()
        self._test_validate_against_registry_fails_for_missing_capability()
        self._test_validate_against_registry_does_not_mutate_the_map()
        return self.result

    # ================= Registration / resolution =================

    def _test_register_and_resolve_valid_mapping(self) -> None:
        cmap = CommandCapabilityMap()
        cmap.register("system", "status", "sys.status")
        self.assert_equal(cmap.resolve("system", "status"), "sys.status")

    def _test_resolve_unknown_mapping_returns_none(self) -> None:
        cmap = CommandCapabilityMap()
        cmap.register("system", "status", "sys.status")
        self.assert_equal(cmap.resolve("system", "restart"), None)
        self.assert_equal(cmap.resolve("nosuchmodule", "status"), None)

    def _test_resolve_never_raises_for_unmapped_pair(self) -> None:
        cmap = CommandCapabilityMap()
        try:
            result = cmap.resolve("anything", "whatever")
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"resolve() raised for an unmapped pair: {exc!r}")
            return
        self.assert_equal(result, None)

    def _test_module_and_action_normalization(self) -> None:
        cmap = CommandCapabilityMap()
        cmap.register("System", "Status", "sys.status")
        # Case-insensitive and whitespace-trimmed, mirroring
        # CommandRouter.dispatch()'s own module_name.lower()/
        # action.lower() normalization exactly.
        self.assert_equal(cmap.resolve("system", "status"), "sys.status")
        self.assert_equal(cmap.resolve("SYSTEM", "STATUS"), "sys.status")
        self.assert_equal(cmap.resolve("  system  ", "  status  "), "sys.status")

    def _test_duplicate_mapping_registration_is_rejected(self) -> None:
        cmap = CommandCapabilityMap()
        cmap.register("system", "status", "sys.status")
        try:
            cmap.register("system", "status", "sys.other")
        except CommandCapabilityMapError:
            self.assert_true(True)
        else:
            self.assert_true(False, "duplicate (module, action) registration should raise")

    def _test_duplicate_registration_does_not_overwrite_existing_entry(self) -> None:
        cmap = CommandCapabilityMap()
        cmap.register("system", "status", "sys.status")
        try:
            cmap.register("system", "status", "sys.other")
        except CommandCapabilityMapError:
            pass
        # The original mapping must survive the rejected overwrite attempt.
        self.assert_equal(cmap.resolve("system", "status"), "sys.status")

    def _test_blank_module_name_is_rejected(self) -> None:
        cmap = CommandCapabilityMap()
        for blank in ("", "   "):
            try:
                cmap.register(blank, "status", "sys.status")
            except CommandCapabilityMapError:
                self.assert_true(True)
            else:
                self.assert_true(False, f"blank module_name {blank!r} should raise")

    def _test_blank_capability_id_is_rejected(self) -> None:
        cmap = CommandCapabilityMap()
        for blank in ("", "   "):
            try:
                cmap.register("system", "status", blank)
            except CommandCapabilityMapError:
                self.assert_true(True)
            else:
                self.assert_true(False, f"blank capability_id {blank!r} should raise")

    def _test_empty_action_is_a_valid_identifier(self) -> None:
        # CommandRouter.dispatch() itself treats "" as a valid action
        # (a module invoked with no action) -- the map must accept it
        # too, deterministically.
        cmap = CommandCapabilityMap()
        try:
            cmap.register("system", "", "sys.default")
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"empty-string action should be a valid identifier: {exc!r}")
            return
        self.assert_equal(cmap.resolve("system", ""), "sys.default")

    # ================= Capability sharing / bulk read =================

    def _test_multiple_commands_may_share_one_capability(self) -> None:
        cmap = CommandCapabilityMap()
        cmap.register("file", "delete", "file.remove")
        cmap.register("file", "rm", "file.remove")
        self.assert_equal(cmap.resolve("file", "delete"), "file.remove")
        self.assert_equal(cmap.resolve("file", "rm"), "file.remove")

    def _test_is_empty_reflects_registration_state(self) -> None:
        cmap = CommandCapabilityMap()
        self.assert_true(cmap.is_empty())
        cmap.register("system", "status", "sys.status")
        self.assert_false(cmap.is_empty())

    def _test_entries_returns_every_registered_mapping(self) -> None:
        cmap = CommandCapabilityMap()
        cmap.register("system", "status", "sys.status")
        cmap.register("file", "delete", "file.remove")
        entries = cmap.entries()
        self.assert_equal(len(entries), 2)
        self.assert_true(("system", "status", "sys.status") in entries)
        self.assert_true(("file", "delete", "file.remove") in entries)

    # ================= Startup validation =================

    def _test_validate_against_registry_passes_when_all_ids_exist(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_make_capability("sys.status"))
        cmap = CommandCapabilityMap()
        cmap.register("system", "status", "sys.status")
        try:
            cmap.validate_against_registry(registry)
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"validation should pass when every id exists: {exc!r}")
            return
        self.assert_true(True)

    def _test_validate_against_registry_passes_for_empty_map(self) -> None:
        registry = CapabilityRegistry()
        cmap = CommandCapabilityMap()
        try:
            cmap.validate_against_registry(registry)
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"validation of an empty map must never raise: {exc!r}")
            return
        self.assert_true(True)

    def _test_validate_against_registry_fails_for_missing_capability(self) -> None:
        registry = CapabilityRegistry()  # deliberately empty
        cmap = CommandCapabilityMap()
        cmap.register("file", "delete", "file.remove")
        try:
            cmap.validate_against_registry(registry)
        except CommandCapabilityMapValidationError as exc:
            self.assert_true("file.remove" in str(exc))
        else:
            self.assert_true(False, "validation should raise for a mapping with no matching capability")

    def _test_validate_against_registry_does_not_mutate_the_map(self) -> None:
        registry = CapabilityRegistry()  # empty -> validation will fail
        cmap = CommandCapabilityMap()
        cmap.register("file", "delete", "file.remove")
        try:
            cmap.validate_against_registry(registry)
        except CommandCapabilityMapValidationError:
            pass
        # The (invalid) mapping must not be silently removed or
        # "repaired" -- STEP 1.1 report Section 4 explicitly forbids
        # silent repair.
        self.assert_equal(cmap.resolve("file", "delete"), "file.remove")
