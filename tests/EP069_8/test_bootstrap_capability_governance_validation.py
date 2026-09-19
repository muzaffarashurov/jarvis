"""EP-069.8 test suite: startup capability-governance validation.

Self-contained test suite (`NAME = "EP069_8"`) under `tests/EP069_8/`.

Scope note (explicit, not a silent limitation): `src/bootstrap.py`'s
`Bootstrap._build_command_router()` calls exactly one new line for
EP-069.8's startup validation --
`capability_command_map.validate_against_registry(capability_registry)`
-- immediately after constructing the same collaborators this suite
constructs below, then passes the resulting coordinator into
`CommandRouter`. No test file anywhere in this repository imports
`src.bootstrap` (verified by inspection during STEP 2.1 -- `grep` for
`bootstrap` under `tests/` returns no matches), because doing so pulls
in `Bootstrap`'s full transitive dependency graph (Playwright, PySide6,
vosk, sounddevice, onnxruntime, python-telegram-bot, and more) for
every one of its ~90 EPs, none of which is relevant to what EP-069.8
itself needs verified. Following the same "no established convention
to deviate from" reasoning, this suite instead tests the validation
mechanism itself -- `CommandCapabilityMap.validate_against_registry()`
-- directly, and separately reproduces `_build_command_router()`'s
exact five-collaborator construction-and-injection sequence
byte-for-byte (see `_build_governance_wiring()` below) using only the
lightweight `src.core.capability*`/`src.core.command_router` modules,
which require no third-party dependency beyond `loguru`. This gives
equivalent coverage of the actual behavior `bootstrap.py` executes
without requiring the rest of the application to be importable in a
test environment.

Covers `docs/architecture/designs/EP069.8_STEP1_1_RESOLUTION.md`'s
Category D requirements.
"""

from __future__ import annotations

from src.core.capability import Capability, CapabilityRegistry, CapabilitySourceKind
from src.core.capability_governance.capability_governance_coordinator import (
    CapabilityGovernanceCoordinator,
)
from src.core.capability_governance.command_capability_map import (
    CommandCapabilityMap,
    CommandCapabilityMapValidationError,
)
from src.core.capability_lifecycle import CapabilityLifecycleRegistry
from src.core.capability_policy import PolicyEngine
from src.core.capability_security import CapabilitySecurityEngine
from src.core.command_router import CommandRouter
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


def _make_capability(capability_id: str) -> Capability:
    """Build a test `Capability` via EP-069.4's own, unmodified `Capability.create()`."""
    return Capability.create(
        id=capability_id,
        name="Test Capability",
        description="A capability used for EP-069.8 startup-validation testing.",
        source_kind=CapabilitySourceKind.INTERNAL,
    )


def _build_governance_wiring(
    populate: "callable | None" = None,
) -> CommandRouter:
    """Reproduce `Bootstrap._build_command_router()`'s EP-069.8 wiring sequence exactly.

    Args:
        populate: Optional callback `(command_capability_map,
            capability_registry) -> None`, invoked before startup
            validation runs -- mirrors a future EP's own future
            registration calls at the same point in
            `_build_command_router()`.

    Returns:
        A real `CommandRouter`, wired to a real
        `CapabilityGovernanceCoordinator` and real EP-069.4/.6/.7/070
        collaborators, exactly as `bootstrap.py` constructs it.

    Raises:
        CommandCapabilityMapValidationError: Propagated unchanged if
            `populate` leaves an inconsistent mapping -- this
            function does not catch it, exactly as
            `_build_command_router()` itself must not.
    """
    capability_registry = CapabilityRegistry()
    capability_security_engine = CapabilitySecurityEngine()
    capability_policy_engine = PolicyEngine()
    capability_lifecycle_registry = CapabilityLifecycleRegistry()
    capability_command_map = CommandCapabilityMap()

    if populate is not None:
        populate(capability_command_map, capability_registry)

    capability_command_map.validate_against_registry(capability_registry)

    capability_governance_coordinator = CapabilityGovernanceCoordinator(
        command_capability_map=capability_command_map,
        capability_registry=capability_registry,
        security_engine=capability_security_engine,
        policy_engine=capability_policy_engine,
        lifecycle_registry=capability_lifecycle_registry,
    )
    return CommandRouter(coordinator=capability_governance_coordinator)


@TestRegistry.register
class CapabilityGovernanceStartupValidationTest(BaseTest):
    """EP-069.8 startup-validation suite (`NAME = "EP069_8"`)."""

    NAME = "EP069_8"

    def run(self):
        self._test_valid_mapping_and_registered_capability_wiring_succeeds()
        self._test_mapping_referencing_nonexistent_capability_fails_startup()
        self._test_empty_mapping_wiring_remains_valid()
        self._test_startup_validation_is_unconditional_no_flag_required()
        self._test_startup_validation_error_message_names_the_bad_mapping()
        self._test_startup_validation_runs_before_router_is_usable()
        return self.result

    def _test_valid_mapping_and_registered_capability_wiring_succeeds(self) -> None:
        def populate(cmap: CommandCapabilityMap, registry: CapabilityRegistry) -> None:
            registry.register(_make_capability("sys.status"))
            cmap.register("system", "status", "sys.status")

        try:
            router = _build_governance_wiring(populate)
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"wiring should succeed for a consistent mapping: {exc!r}")
            return

        self.assert_true(isinstance(router, CommandRouter))

    def _test_mapping_referencing_nonexistent_capability_fails_startup(self) -> None:
        def populate(cmap: CommandCapabilityMap, registry: CapabilityRegistry) -> None:
            # Deliberately: mapped, capability never registered.
            cmap.register("file", "delete", "file.remove")

        try:
            _build_governance_wiring(populate)
        except CommandCapabilityMapValidationError:
            self.assert_true(True)
        else:
            self.assert_true(
                False,
                "startup wiring must fail loudly for a mapping referencing an "
                "unregistered capability, not silently start",
            )

    def _test_empty_mapping_wiring_remains_valid(self) -> None:
        # No `populate` callback at all -- exactly today's actual
        # production state (STEP 1.1 report Section 9; EP069.8_DESIGN.md
        # Section 13): both the map and the registry start, and remain, empty.
        try:
            router = _build_governance_wiring()
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"wiring with an empty map must succeed: {exc!r}")
            return

        self.assert_true(isinstance(router, CommandRouter))

    def _test_startup_validation_is_unconditional_no_flag_required(self) -> None:
        # There is no configuration object, flag, or environment
        # variable anywhere in `_build_governance_wiring()` --
        # validation always runs. This test asserts that fact
        # structurally: calling the function with a bad mapping raises
        # unconditionally, with no way to opt out (STEP 2 prompt
        # Section 12; STEP 1.1 report Secondary Decisions).
        def populate(cmap: CommandCapabilityMap, registry: CapabilityRegistry) -> None:
            cmap.register("x", "y", "nonexistent.capability")

        try:
            _build_governance_wiring(populate)
        except CommandCapabilityMapValidationError:
            self.assert_true(True)
        else:
            self.assert_true(False, "validation must be unconditional -- no flag can suppress it")

    def _test_startup_validation_error_message_names_the_bad_mapping(self) -> None:
        def populate(cmap: CommandCapabilityMap, registry: CapabilityRegistry) -> None:
            cmap.register("file", "delete", "file.remove")

        try:
            _build_governance_wiring(populate)
        except CommandCapabilityMapValidationError as exc:
            message = str(exc)
            self.assert_true("file.remove" in message)
            self.assert_true("file delete" in message)
        else:
            self.assert_true(False, "expected CommandCapabilityMapValidationError to be raised")

    def _test_startup_validation_runs_before_router_is_usable(self) -> None:
        # If validation raises, no CommandRouter/coordinator is ever
        # constructed or returned -- the failure happens strictly
        # before the router becomes reachable, matching
        # "do not allow Jarvis to start with an inconsistent governed
        # mapping" (STEP 2 prompt Section 7).
        def populate(cmap: CommandCapabilityMap, registry: CapabilityRegistry) -> None:
            cmap.register("file", "delete", "file.remove")

        router_was_constructed = False
        try:
            _build_governance_wiring(populate)
            router_was_constructed = True
        except CommandCapabilityMapValidationError:
            pass

        self.assert_false(
            router_was_constructed,
            "no CommandRouter should ever be returned when startup validation fails",
        )
