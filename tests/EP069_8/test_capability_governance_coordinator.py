"""EP-069.8 test suite: CapabilityGovernanceCoordinator.

Self-contained test suite (`NAME = "EP069_8"`) under `tests/EP069_8/`.
Uses the real, unmodified EP-069.4/EP-069.6/EP-069.7/EP-070 collaborators
wherever a real one can deterministically produce the scenario under
test (mirroring `tests/EP070/test_capability_policy_engine.py`'s own
"real engineering tests" precedent), and small, local, duck-typed
fakes only where a real collaborator cannot be made to raise or to
return a specific shape on demand (mirroring `tests/EP065/
test_command_router_malformed_input.py`'s own `_RecordingModule`/
`_RaisingModule` local-fixture precedent).

Covers `docs/architecture/designs/EP069.8_STEP1_1_RESOLUTION.md`'s
Category B requirements.
"""

from __future__ import annotations

from src.core.capability import Capability, CapabilityRegistry, CapabilitySourceKind
from src.core.capability_governance.capability_governance_coordinator import (
    CapabilityGovernanceCoordinator,
    GovernanceOutcome,
)
from src.core.capability_governance.command_capability_map import CommandCapabilityMap
from src.core.capability_lifecycle import CapabilityLifecycleRegistry
from src.core.capability_policy import PolicyEngine, PolicyLevel
from src.core.capability_security import CapabilitySecurityEngine
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


def _make_capability(
    capability_id: str,
    source_kind: CapabilitySourceKind = CapabilitySourceKind.INTERNAL,
    source: str = "",
    required_permissions: tuple[str, ...] = (),
) -> Capability:
    """Build a test `Capability` via EP-069.4's own, unmodified `Capability.create()`."""
    return Capability.create(
        id=capability_id,
        name="Test Capability",
        description="A capability used for EP-069.8 coordinator testing.",
        source_kind=source_kind,
        source=source,
        required_permissions=required_permissions,
    )


def _build_coordinator(
    *,
    command_capability_map: CommandCapabilityMap | None = None,
    capability_registry: CapabilityRegistry | None = None,
    security_engine=None,
    policy_engine=None,
    lifecycle_registry=None,
) -> tuple[CapabilityGovernanceCoordinator, CommandCapabilityMap, CapabilityRegistry, CapabilityLifecycleRegistry]:
    """Build a coordinator with real collaborators, any of which may be overridden.

    Returns the coordinator plus the (possibly newly built) map,
    registry, and lifecycle registry, so callers can populate them
    before dispatching without reaching into the coordinator's own
    private attributes.
    """
    cmap = command_capability_map if command_capability_map is not None else CommandCapabilityMap()
    registry = capability_registry if capability_registry is not None else CapabilityRegistry()
    lifecycle = lifecycle_registry if lifecycle_registry is not None else CapabilityLifecycleRegistry()
    coordinator = CapabilityGovernanceCoordinator(
        command_capability_map=cmap,
        capability_registry=registry,
        security_engine=security_engine if security_engine is not None else CapabilitySecurityEngine(),
        policy_engine=policy_engine if policy_engine is not None else PolicyEngine(),
        lifecycle_registry=lifecycle,
    )
    return coordinator, cmap, registry, lifecycle


class _RecordingSecurityEngine:
    """Duck-typed fake `CapabilitySecurityEngine` -- records whether `assess()` was ever called."""

    def __init__(self) -> None:
        self.call_count = 0

    def assess(self, capability):
        self.call_count += 1
        return CapabilitySecurityEngine().assess(capability)


class _RecordingPolicyEngine:
    """Duck-typed fake `PolicyEngine` -- records whether `evaluate()` was ever called."""

    def __init__(self) -> None:
        self.call_count = 0

    def evaluate(self, capability, security_assessment=None, lifecycle_status=None):
        self.call_count += 1
        return PolicyEngine().evaluate(capability, security_assessment, lifecycle_status)


class _NoneAssessmentSecurityEngine:
    """Duck-typed fake -- always returns `None` from `assess()`.

    Used only to exercise `DefaultPolicyProvider`'s rule 5 (`ANALYZE`)
    through the real coordinator/PolicyEngine: the coordinator's real
    `CapabilitySecurityEngine` collaborator always returns a real
    `CapabilitySecurityAssessment`, so rule 5's `security_assessment
    is None` condition is otherwise unreachable end-to-end. This fake
    proves the coordinator forwards whatever its `security_engine`
    collaborator returns -- including `None` -- faithfully to
    `PolicyEngine.evaluate()`, without special-casing it.
    """

    def assess(self, capability):
        return None


class _RaisingSecurityEngine:
    """Duck-typed fake `CapabilitySecurityEngine` whose `assess()` always raises."""

    def assess(self, capability):
        raise RuntimeError("simulated security engine failure")


class _RaisingPolicyEngine:
    """Duck-typed fake `PolicyEngine` whose `evaluate()` always raises."""

    def evaluate(self, capability, security_assessment=None, lifecycle_status=None):
        raise RuntimeError("simulated policy engine failure")


class _RaisingLifecycleRegistry:
    """Duck-typed fake `CapabilityLifecycleRegistry` whose `is_tracked()` always raises."""

    def is_tracked(self, capability_id):
        raise RuntimeError("simulated lifecycle registry failure")

    def status(self, capability_id):  # pragma: no cover - not reached if is_tracked() raises first
        raise RuntimeError("simulated lifecycle registry failure")


@TestRegistry.register
class CapabilityGovernanceCoordinatorTest(BaseTest):
    """EP-069.8 `CapabilityGovernanceCoordinator` suite (`NAME = "EP069_8"`)."""

    NAME = "EP069_8"

    def run(self):
        self._test_unmapped_command_is_ungoverned()
        self._test_unmapped_command_does_not_invoke_security()
        self._test_unmapped_command_does_not_invoke_policy()
        self._test_mapped_internal_capability_execute_is_allowed()
        self._test_medium_risk_prepare_is_denied()
        self._test_none_assessment_analyze_is_denied()
        self._test_high_risk_permission_require_approval_is_denied()
        self._test_lifecycle_disabled_is_denied()
        self._test_lifecycle_revoked_is_denied()
        self._test_high_risk_trust_mismatch_prevents_execution()
        self._test_missing_capability_fails_closed()
        self._test_security_engine_exception_fails_closed()
        self._test_policy_engine_exception_fails_closed()
        self._test_lifecycle_engine_exception_fails_closed()
        self._test_allowed_decision_has_sufficient_diagnostics()
        self._test_denied_decision_has_sufficient_diagnostics()
        self._test_authorize_dispatch_never_raises()
        return self.result

    # ================= Ungoverned path =================

    def _test_unmapped_command_is_ungoverned(self) -> None:
        coordinator, _cmap, _registry, _lifecycle = _build_coordinator()
        decision = coordinator.authorize_dispatch("system", "status")
        self.assert_equal(decision.outcome, GovernanceOutcome.UNGOVERNED)
        self.assert_true(decision.may_execute)
        self.assert_equal(decision.capability_id, None)

    def _test_unmapped_command_does_not_invoke_security(self) -> None:
        recording_security = _RecordingSecurityEngine()
        coordinator, _cmap, _registry, _lifecycle = _build_coordinator(security_engine=recording_security)
        coordinator.authorize_dispatch("system", "status")
        self.assert_equal(recording_security.call_count, 0)

    def _test_unmapped_command_does_not_invoke_policy(self) -> None:
        recording_policy = _RecordingPolicyEngine()
        coordinator, _cmap, _registry, _lifecycle = _build_coordinator(policy_engine=recording_policy)
        coordinator.authorize_dispatch("system", "status")
        self.assert_equal(recording_policy.call_count, 0)

    # ================= EXECUTE / ALLOWED =================

    def _test_mapped_internal_capability_execute_is_allowed(self) -> None:
        coordinator, cmap, registry, lifecycle_registry = _build_coordinator()
        registry.register(_make_capability("sys.status"))
        cmap.register("system", "status", "sys.status")

        decision = coordinator.authorize_dispatch("system", "status")

        self.assert_equal(decision.outcome, GovernanceOutcome.ALLOWED)
        self.assert_true(decision.may_execute)
        self.assert_equal(decision.capability_id, "sys.status")
        self.assert_not_none(decision.policy_decision)
        self.assert_equal(decision.policy_decision.level, PolicyLevel.EXECUTE)

    # ================= Non-EXECUTE policy levels -> DENY =================

    def _test_medium_risk_prepare_is_denied(self) -> None:
        # DefaultCapabilitySecurityProvider: non-INTERNAL + blank source
        # -> MEDIUM ("missing_provenance") -> DefaultPolicyProvider rule 4 -> PREPARE.
        coordinator, cmap, registry, lifecycle_registry = _build_coordinator()
        registry.register(
            _make_capability("ext.prepare", source_kind=CapabilitySourceKind.REST_API, source="")
        )
        cmap.register("ext", "prepare", "ext.prepare")

        decision = coordinator.authorize_dispatch("ext", "prepare")

        self.assert_equal(decision.outcome, GovernanceOutcome.DENIED)
        self.assert_false(decision.may_execute)
        self.assert_equal(decision.policy_decision.level, PolicyLevel.PREPARE)

    def _test_none_assessment_analyze_is_denied(self) -> None:
        # DefaultPolicyProvider rule 5: non-INTERNAL + security_assessment
        # is None -> ANALYZE. See _NoneAssessmentSecurityEngine's own
        # docstring for why a fake is required to reach this rule.
        coordinator, cmap, registry, lifecycle_registry = _build_coordinator(
            security_engine=_NoneAssessmentSecurityEngine()
        )
        registry.register(_make_capability("ext.analyze", source_kind=CapabilitySourceKind.LOCAL_CLI))
        cmap.register("ext", "analyze", "ext.analyze")

        decision = coordinator.authorize_dispatch("ext", "analyze")

        self.assert_equal(decision.outcome, GovernanceOutcome.DENIED)
        self.assert_false(decision.may_execute)
        self.assert_equal(decision.policy_decision.level, PolicyLevel.ANALYZE)

    def _test_high_risk_permission_require_approval_is_denied(self) -> None:
        # DefaultCapabilitySecurityProvider: non-INTERNAL + a required
        # permission tag containing "network" -> HIGH
        # ("high_risk_permission") -> DefaultPolicyProvider rule 3 -> REQUIRE_APPROVAL.
        coordinator, cmap, registry, lifecycle_registry = _build_coordinator()
        registry.register(
            _make_capability(
                "ext.approval",
                source_kind=CapabilitySourceKind.REST_API,
                source="https://example.invalid/api",
                required_permissions=("network.external",),
            )
        )
        cmap.register("ext", "approve_me", "ext.approval")

        decision = coordinator.authorize_dispatch("ext", "approve_me")

        self.assert_equal(decision.outcome, GovernanceOutcome.DENIED)
        self.assert_false(decision.may_execute)
        self.assert_equal(decision.policy_decision.level, PolicyLevel.REQUIRE_APPROVAL)

    def _test_high_risk_trust_mismatch_prevents_execution(self) -> None:
        # A second, independent HIGH-risk trigger (trust/source
        # mismatch rather than a permission tag), confirming HIGH risk
        # generally prevents execution, not just this one finding category.
        from src.core.capability import CapabilityTrustLevel

        coordinator, cmap, registry, lifecycle_registry = _build_coordinator()
        capability = Capability.create(
            id="ext.mismatch",
            name="Mismatched Capability",
            description="External capability incorrectly claiming internal trust.",
            source_kind=CapabilitySourceKind.REST_API,
            source="https://example.invalid/api",
            trust_level=CapabilityTrustLevel.TRUSTED_INTERNAL,
        )
        registry.register(capability)
        cmap.register("ext", "mismatch", "ext.mismatch")

        decision = coordinator.authorize_dispatch("ext", "mismatch")

        self.assert_equal(decision.outcome, GovernanceOutcome.DENIED)
        self.assert_false(decision.may_execute)
        self.assert_equal(decision.policy_decision.level, PolicyLevel.REQUIRE_APPROVAL)

    def _test_lifecycle_disabled_is_denied(self) -> None:
        coordinator, cmap, registry, lifecycle_registry = _build_coordinator()
        capability = _make_capability("sys.disabled")
        registry.register(capability)
        cmap.register("system", "disabled_action", "sys.disabled")

        lifecycle_registry.register(capability)
        lifecycle_registry.disable("sys.disabled", reason="EP-069.8 test")

        decision = coordinator.authorize_dispatch("system", "disabled_action")

        self.assert_equal(decision.outcome, GovernanceOutcome.DENIED)
        self.assert_false(decision.may_execute)
        self.assert_equal(decision.policy_decision.level, PolicyLevel.OBSERVE)

    def _test_lifecycle_revoked_is_denied(self) -> None:
        coordinator, cmap, registry, lifecycle_registry = _build_coordinator()
        capability = _make_capability("sys.revoked")
        registry.register(capability)
        cmap.register("system", "revoked_action", "sys.revoked")

        lifecycle_registry.register(capability)
        lifecycle_registry.revoke("sys.revoked", reason="EP-069.8 test")

        decision = coordinator.authorize_dispatch("system", "revoked_action")

        self.assert_equal(decision.outcome, GovernanceOutcome.DENIED)
        self.assert_false(decision.may_execute)
        self.assert_equal(decision.policy_decision.level, PolicyLevel.OBSERVE)

    # ================= Fail closed =================

    def _test_missing_capability_fails_closed(self) -> None:
        coordinator, cmap, _registry, _lifecycle = _build_coordinator()  # registry stays empty
        cmap.register("file", "delete", "file.remove")

        decision = coordinator.authorize_dispatch("file", "delete")

        self.assert_equal(decision.outcome, GovernanceOutcome.ERROR)
        self.assert_false(decision.may_execute)
        self.assert_equal(decision.capability_id, "file.remove")
        self.assert_true("not registered" in decision.reason)

    def _test_security_engine_exception_fails_closed(self) -> None:
        coordinator, cmap, registry, _lifecycle = _build_coordinator(security_engine=_RaisingSecurityEngine())
        registry.register(_make_capability("sys.boom"))
        cmap.register("system", "boom", "sys.boom")

        decision = coordinator.authorize_dispatch("system", "boom")

        self.assert_equal(decision.outcome, GovernanceOutcome.ERROR)
        self.assert_false(decision.may_execute)

    def _test_policy_engine_exception_fails_closed(self) -> None:
        coordinator, cmap, registry, _lifecycle = _build_coordinator(policy_engine=_RaisingPolicyEngine())
        registry.register(_make_capability("sys.boom2"))
        cmap.register("system", "boom2", "sys.boom2")

        decision = coordinator.authorize_dispatch("system", "boom2")

        self.assert_equal(decision.outcome, GovernanceOutcome.ERROR)
        self.assert_false(decision.may_execute)

    def _test_lifecycle_engine_exception_fails_closed(self) -> None:
        coordinator, cmap, registry, _lifecycle = _build_coordinator(lifecycle_registry=_RaisingLifecycleRegistry())
        registry.register(_make_capability("sys.boom3"))
        cmap.register("system", "boom3", "sys.boom3")

        decision = coordinator.authorize_dispatch("system", "boom3")

        self.assert_equal(decision.outcome, GovernanceOutcome.ERROR)
        self.assert_false(decision.may_execute)

    def _test_authorize_dispatch_never_raises(self) -> None:
        # Every fake-collaborator scenario above must have returned a
        # GovernanceDecision, never propagated an exception out of
        # authorize_dispatch() itself. This test exercises the same
        # "everything raises" combination once more, directly asserting
        # no exception escapes.
        coordinator, cmap, registry, _lifecycle = _build_coordinator(
            security_engine=_RaisingSecurityEngine(),
            policy_engine=_RaisingPolicyEngine(),
            lifecycle_registry=_RaisingLifecycleRegistry(),
        )
        registry.register(_make_capability("sys.boom4"))
        cmap.register("system", "boom4", "sys.boom4")

        try:
            decision = coordinator.authorize_dispatch("system", "boom4")
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"authorize_dispatch() must never raise: {exc!r}")
            return
        self.assert_equal(decision.outcome, GovernanceOutcome.ERROR)

    # ================= Diagnostics =================

    def _test_allowed_decision_has_sufficient_diagnostics(self) -> None:
        coordinator, cmap, registry, lifecycle_registry = _build_coordinator()
        registry.register(_make_capability("sys.diag"))
        cmap.register("system", "diag", "sys.diag")

        decision = coordinator.authorize_dispatch("system", "diag")

        self.assert_equal(decision.capability_id, "sys.diag")
        self.assert_not_none(decision.policy_decision)
        self.assert_equal(decision.policy_decision.capability_id, "sys.diag")
        self.assert_true(len(decision.policy_decision.reasons) > 0)

    def _test_denied_decision_has_sufficient_diagnostics(self) -> None:
        coordinator, cmap, registry, lifecycle_registry = _build_coordinator()
        capability = _make_capability("sys.diag2")
        registry.register(capability)
        cmap.register("system", "diag2", "sys.diag2")

        lifecycle_registry.register(capability)
        lifecycle_registry.revoke("sys.diag2", reason="diagnostics test")

        decision = coordinator.authorize_dispatch("system", "diag2")

        self.assert_equal(decision.capability_id, "sys.diag2")
        self.assert_not_none(decision.policy_decision)
        self.assert_true("policy level" in decision.reason)
        self.assert_true(len(decision.policy_decision.reasons) > 0)
