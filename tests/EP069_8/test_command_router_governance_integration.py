"""EP-069.8 test suite: CommandRouter governance integration.

Self-contained test suite (`NAME = "EP069_8"`) under `tests/EP069_8/`.
Local `CommandModule` fixtures mirror `tests/EP065/
test_command_router_malformed_input.py`'s own `_RecordingModule`
precedent (an independent, EP-069.8-owned copy, per this repository's
established "self-contained, no cross-EP import" convention --
`tests/EP061/test_scheduler_shutdown.py`).

Covers `docs/architecture/designs/EP069.8_STEP1_1_RESOLUTION.md`'s
Category C requirements: backward compatibility (bare `CommandRouter()`
and a coordinator with an empty map both reproduce pre-EP-069.8
behavior exactly), governed allow/deny routing, and -- critically --
that a denied dispatch never reaches `module.execute()` (side-effect
prevention), verified by asserting on the module's own call log, not
only on the returned `CommandResult`.
"""

from __future__ import annotations

from src.core.capability import Capability, CapabilityRegistry, CapabilitySourceKind
from src.core.capability_governance.capability_governance_coordinator import (
    CapabilityGovernanceCoordinator,
)
from src.core.capability_governance.command_capability_map import CommandCapabilityMap
from src.core.capability_lifecycle import CapabilityLifecycleRegistry
from src.core.capability_policy import PolicyEngine
from src.core.capability_security import CapabilitySecurityEngine
from src.core.command_router import CommandResult, CommandRouter
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


class _RecordingModule:
    """Minimal, real `CommandModule` implementation -- records every call.

    Independent, EP-069.8-owned copy of the kind of stub
    `tests/EP065/test_command_router_malformed_input.py`'s own
    `_RecordingModule` already uses.
    """

    def __init__(self, name: str = "stub") -> None:
        self._name = name
        self.calls: list[tuple[str, list[str]]] = []

    @property
    def name(self) -> str:
        return self._name

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        self.calls.append((action, arguments))
        return CommandResult(success=True, message=f"executed:{action}")


def _make_capability(capability_id: str) -> Capability:
    """Build a test `Capability` via EP-069.4's own, unmodified `Capability.create()`."""
    return Capability.create(
        id=capability_id,
        name="Test Capability",
        description="A capability used for EP-069.8 CommandRouter-integration testing.",
        source_kind=CapabilitySourceKind.INTERNAL,
    )


def _build_governed_router(
    module: _RecordingModule,
) -> tuple[CommandRouter, CommandCapabilityMap, CapabilityRegistry, CapabilityLifecycleRegistry]:
    """Build a real CommandRouter wired to a real coordinator + real engines, with `module` registered."""
    cmap = CommandCapabilityMap()
    registry = CapabilityRegistry()
    lifecycle = CapabilityLifecycleRegistry()
    coordinator = CapabilityGovernanceCoordinator(
        command_capability_map=cmap,
        capability_registry=registry,
        security_engine=CapabilitySecurityEngine(),
        policy_engine=PolicyEngine(),
        lifecycle_registry=lifecycle,
    )
    router = CommandRouter(coordinator=coordinator)
    router.register(module)
    return router, cmap, registry, lifecycle


@TestRegistry.register
class CommandRouterGovernanceIntegrationTest(BaseTest):
    """EP-069.8 `CommandRouter` integration suite (`NAME = "EP069_8"`)."""

    NAME = "EP069_8"

    def run(self):
        self._test_bare_router_behaves_exactly_as_before()
        self._test_router_with_coordinator_and_empty_map_behaves_exactly_as_before()
        self._test_unmapped_command_executes()
        self._test_mapped_execute_command_executes()
        self._test_mapped_denied_command_does_not_execute()
        self._test_mapped_missing_capability_does_not_execute()
        self._test_governance_internal_error_does_not_execute()
        self._test_unknown_module_remains_handled_exactly_as_before()
        self._test_allowed_execution_arguments_reach_module_unchanged()
        self._test_denied_execution_prevents_all_module_side_effects()
        self._test_denial_message_does_not_leak_arguments()
        return self.result

    # ================= Backward compatibility =================

    def _test_bare_router_behaves_exactly_as_before(self) -> None:
        module = _RecordingModule("stub")
        router = CommandRouter()  # no coordinator argument at all
        router.register(module)

        result = router.dispatch("stub ping hello")

        self.assert_true(result.success)
        self.assert_equal(result.message, "executed:ping")
        self.assert_equal(module.calls, [("ping", ["hello"])])

    def _test_router_with_coordinator_and_empty_map_behaves_exactly_as_before(self) -> None:
        module = _RecordingModule("stub")
        router, _cmap, _registry, _lifecycle = _build_governed_router(module)  # map is empty

        result = router.dispatch("stub ping hello")

        self.assert_true(result.success)
        self.assert_equal(result.message, "executed:ping")
        self.assert_equal(module.calls, [("ping", ["hello"])])

    # ================= Ungoverned / governed routing =================

    def _test_unmapped_command_executes(self) -> None:
        module = _RecordingModule("stub")
        router, cmap, registry, _lifecycle = _build_governed_router(module)
        # A mapping exists, but for a *different* action -- "ping" itself
        # remains unmapped and therefore ungoverned.
        registry.register(_make_capability("stub.other"))
        cmap.register("stub", "other_action", "stub.other")

        result = router.dispatch("stub ping hello")

        self.assert_true(result.success)
        self.assert_equal(module.calls, [("ping", ["hello"])])

    def _test_mapped_execute_command_executes(self) -> None:
        module = _RecordingModule("stub")
        router, cmap, registry, _lifecycle = _build_governed_router(module)
        registry.register(_make_capability("stub.ping"))
        cmap.register("stub", "ping", "stub.ping")

        result = router.dispatch("stub ping hello")

        self.assert_true(result.success)
        self.assert_equal(result.message, "executed:ping")
        self.assert_equal(module.calls, [("ping", ["hello"])])

    def _test_mapped_denied_command_does_not_execute(self) -> None:
        module = _RecordingModule("stub")
        router, cmap, registry, lifecycle = _build_governed_router(module)
        capability = _make_capability("stub.ping")
        registry.register(capability)
        cmap.register("stub", "ping", "stub.ping")
        lifecycle.register(capability)
        lifecycle.revoke("stub.ping", reason="EP-069.8 integration test")

        result = router.dispatch("stub ping hello")

        self.assert_false(result.success)
        self.assert_true("denied" in result.message.lower())
        self.assert_equal(module.calls, [])

    def _test_mapped_missing_capability_does_not_execute(self) -> None:
        module = _RecordingModule("stub")
        router, cmap, _registry, _lifecycle = _build_governed_router(module)
        # Deliberately: mapped, but the referenced capability is never
        # registered -- simulates a drifted map (STEP 1.1 report,
        # Drift Analysis), which must fail closed, not silently
        # execute as if ungoverned.
        cmap.register("stub", "ping", "stub.nonexistent")

        result = router.dispatch("stub ping hello")

        self.assert_false(result.success)
        self.assert_equal(module.calls, [])

    def _test_governance_internal_error_does_not_execute(self) -> None:
        class _RaisingSecurityEngine:
            def assess(self, capability):
                raise RuntimeError("simulated security engine failure")

        module = _RecordingModule("stub")
        cmap = CommandCapabilityMap()
        registry = CapabilityRegistry()
        registry.register(_make_capability("stub.ping"))
        cmap.register("stub", "ping", "stub.ping")
        coordinator = CapabilityGovernanceCoordinator(
            command_capability_map=cmap,
            capability_registry=registry,
            security_engine=_RaisingSecurityEngine(),
            policy_engine=PolicyEngine(),
            lifecycle_registry=CapabilityLifecycleRegistry(),
        )
        router = CommandRouter(coordinator=coordinator)
        router.register(module)

        try:
            result = router.dispatch("stub ping hello")
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"dispatch() must never raise for a governance error: {exc!r}")
            return

        self.assert_false(result.success)
        self.assert_equal(module.calls, [])

    # ================= Unchanged pre-existing paths =================

    def _test_unknown_module_remains_handled_exactly_as_before(self) -> None:
        module = _RecordingModule("stub")
        router, _cmap, _registry, _lifecycle = _build_governed_router(module)

        result = router.dispatch("nosuchmodule help")

        self.assert_false(result.success)
        self.assert_equal(
            result.message,
            "Unknown module: nosuchmodule\n"
            'Type "system help" for available commands.',
        )
        self.assert_equal(module.calls, [])

    # ================= Argument/side-effect integrity =================

    def _test_allowed_execution_arguments_reach_module_unchanged(self) -> None:
        module = _RecordingModule("stub")
        router, cmap, registry, _lifecycle = _build_governed_router(module)
        registry.register(_make_capability("stub.open"))
        cmap.register("stub", "open", "stub.open")

        result = router.dispatch(r"stub open C:\Temp\file.txt --flag value")

        self.assert_true(result.success)
        self.assert_equal(
            module.calls,
            [("open", [r"C:\Temp\file.txt", "--flag", "value"])],
        )

    def _test_denied_execution_prevents_all_module_side_effects(self) -> None:
        # The important test: assert on module.execute() call count,
        # not only on the returned CommandResult, proving no side
        # effect occurred -- not just that the reply says "denied".
        module = _RecordingModule("stub")
        router, cmap, registry, lifecycle = _build_governed_router(module)
        capability = _make_capability("stub.danger")
        registry.register(capability)
        cmap.register("stub", "danger", "stub.danger")
        lifecycle.register(capability)
        lifecycle.disable("stub.danger", reason="EP-069.8 integration test")

        for _ in range(3):
            router.dispatch("stub danger irreversible_argument")

        self.assert_equal(
            len(module.calls),
            0,
            "module.execute() must never be called for a denied, governed command, "
            "no matter how many times dispatch() is retried",
        )

    def _test_denial_message_does_not_leak_arguments(self) -> None:
        module = _RecordingModule("stub")
        router, cmap, registry, lifecycle = _build_governed_router(module)
        capability = _make_capability("stub.secret")
        registry.register(capability)
        cmap.register("stub", "secret", "stub.secret")
        lifecycle.register(capability)
        lifecycle.revoke("stub.secret", reason="EP-069.8 integration test")

        result = router.dispatch("stub secret sk-super-secret-marker")

        self.assert_false(result.success)
        self.assert_false("sk-super-secret-marker" in result.message)
