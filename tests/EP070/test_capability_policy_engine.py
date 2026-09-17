"""Real engineering tests for EP-070 STEP 2 - Policy, Permissions & Human
Approval Engine (capability policy-decision slice).

Self-contained test suite (`NAME = "EP070"`) under `tests/EP070/`,
following the established convention of a package per EP. Does not
import `src.bootstrap`, `src.core.capability.capability_registry`,
`src.core.capability_discovery`, or
`src.core.capability_security.capability_security_engine` --
`EP070_DESIGN.md` Owner Decisions OD1/OD3/OD7 explicitly exclude all
of these from this EP's scope.

Covers all 30 behavioral requirements from the STEP 2 implementation
prompt, including the mandatory semantic verification that `OBSERVE`
is a restrictive result, never execution authorization.
"""

from __future__ import annotations

import inspect
import re

from src.core.capability import Capability, CapabilitySourceKind
from src.core.capability_lifecycle import CapabilityLifecycleStatus
from src.core.capability_policy import (
    CapabilityPolicyError,
    CapabilityPolicyProviderError,
    DefaultPolicyProvider,
    PolicyDecision,
    PolicyEngine,
    PolicyLevel,
    PolicyProvider,
)
from src.core.capability_policy import capability_policy_engine as _engine_module
from src.core.capability_policy import capability_policy_provider as _provider_module
from src.core.capability_policy import capability_policy_result as _result_module
from src.core.capability_security import CapabilitySecurityAssessment, SecurityRiskLevel
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

_IMPORT_LINE_PATTERN = re.compile(r"^(?:from|import)\s+\S.*$", re.MULTILINE)


def _make_capability(id: str, source_kind: CapabilitySourceKind = CapabilitySourceKind.INTERNAL) -> Capability:
    """Build a test `Capability` via EP-069.4's own, unmodified `Capability.create()`."""
    return Capability.create(
        id=id,
        name="Test Capability",
        description="A capability used for EP-070 testing.",
        source_kind=source_kind,
    )


def _make_assessment(risk_level: SecurityRiskLevel) -> CapabilitySecurityAssessment:
    """Build a test `CapabilitySecurityAssessment` via EP-069.6's own, unmodified type."""
    return CapabilitySecurityAssessment(capability_id="unused", overall_risk_level=risk_level, findings=[])


class _RecordingFakeProvider(PolicyProvider):
    """Minimal, deterministic, test-only `PolicyProvider`.

    Records exactly what it was called with, so tests can assert the
    Engine delegates correctly without duplicating rule logic.
    """

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def provider_name(self) -> str:
        return "recording_fake"

    def evaluate(
        self,
        capability: Capability,
        security_assessment: CapabilitySecurityAssessment | None = None,
        lifecycle_status: CapabilityLifecycleStatus | None = None,
    ) -> PolicyDecision:
        self.calls.append((capability, security_assessment, lifecycle_status))
        return PolicyDecision(capability_id=capability.id, level=PolicyLevel.EXECUTE, reasons=("fake",))


@TestRegistry.register
class CapabilityPolicyEngineTest(BaseTest):
    NAME = "EP070"

    def run(self):
        # 1-2. PolicyLevel shape
        self._test_policy_level_has_exactly_five_values()
        self._test_policy_level_exposes_no_ordering()

        # 3. Each OD4 rule independently
        self._test_rule_1_revoked_yields_observe()
        self._test_rule_2_disabled_yields_observe()
        self._test_rule_3_high_yields_require_approval()
        self._test_rule_4_medium_yields_prepare()
        self._test_rule_5_external_no_assessment_yields_analyze()
        self._test_rule_6_otherwise_yields_execute()

        # 4-5. Precedence
        self._test_precedence_revoked_and_high_yields_observe()
        self._test_precedence_disabled_and_high_yields_observe()

        # 6-10. Security/lifecycle combinations
        self._test_internal_no_assessment_yields_execute()
        self._test_external_low_assessment_yields_execute()
        self._test_external_medium_yields_prepare()
        self._test_external_high_yields_require_approval()
        self._test_missing_assessment_external_yields_analyze()

        # 11-12. Optional inputs
        self._test_lifecycle_status_none_works()
        self._test_security_assessment_none_works()

        # 13. Invalid input
        self._test_evaluate_none_raises()

        # 14-16. Immutability / determinism
        self._test_policy_decision_is_immutable()
        self._test_reasons_are_deterministic()
        self._test_repeated_evaluation_produces_equal_decisions()

        # 17-19. No mutation of inputs
        self._test_capability_not_mutated()
        self._test_security_assessment_not_mutated()
        self._test_lifecycle_status_not_mutated()

        # 20-21. Engine delegation
        self._test_engine_delegates_to_configured_provider()
        self._test_engine_defaults_to_default_provider()

        # 22-26. Dependency boundaries
        self._test_no_forbidden_imports()

        # 27. No DENY level
        self._test_no_deny_level_exists()

        # 28-30. Mandatory OBSERVE semantics
        self._test_observe_is_documented_as_restrictive()
        self._test_revoked_observe_does_not_imply_executable()
        self._test_disabled_observe_does_not_imply_executable()

        # Error hierarchy
        self._test_provider_error_is_a_policy_error()

        return self.result

    # ---------- 1-2. PolicyLevel shape ----------

    def _test_policy_level_has_exactly_five_values(self) -> None:
        self.assert_equal(
            {member.value for member in PolicyLevel},
            {"OBSERVE", "ANALYZE", "PREPARE", "EXECUTE", "REQUIRE_APPROVAL"},
            "PolicyLevel must contain exactly the five approved values, no DENY, no sixth value.",
        )
        self.assert_equal(len(PolicyLevel), 5, "PolicyLevel must have exactly 5 members.")

    def _test_policy_level_exposes_no_ordering(self) -> None:
        for method_name in ("__lt__", "__le__", "__gt__", "__ge__"):
            self.assert_false(
                method_name in PolicyLevel.__dict__,
                f"PolicyLevel must not define {method_name} (Owner Decision OD6: unordered).",
            )
        raised = False
        try:
            PolicyLevel.OBSERVE < PolicyLevel.EXECUTE  # type: ignore[operator]
        except TypeError:
            raised = True
        self.assert_true(
            raised, "Comparing two PolicyLevel members with '<' must raise TypeError (no ordering contract)."
        )

    # ---------- 3. Each OD4 rule independently ----------

    def _test_rule_1_revoked_yields_observe(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            _make_capability("cap"), lifecycle_status=CapabilityLifecycleStatus.REVOKED
        )
        self.assert_equal(decision.level, PolicyLevel.OBSERVE, "Rule 1: REVOKED must yield OBSERVE.")

    def _test_rule_2_disabled_yields_observe(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            _make_capability("cap"), lifecycle_status=CapabilityLifecycleStatus.DISABLED
        )
        self.assert_equal(decision.level, PolicyLevel.OBSERVE, "Rule 2: DISABLED must yield OBSERVE.")

    def _test_rule_3_high_yields_require_approval(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            _make_capability("cap"), security_assessment=_make_assessment(SecurityRiskLevel.HIGH)
        )
        self.assert_equal(
            decision.level, PolicyLevel.REQUIRE_APPROVAL, "Rule 3: HIGH risk must yield REQUIRE_APPROVAL."
        )

    def _test_rule_4_medium_yields_prepare(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            _make_capability("cap"), security_assessment=_make_assessment(SecurityRiskLevel.MEDIUM)
        )
        self.assert_equal(decision.level, PolicyLevel.PREPARE, "Rule 4: MEDIUM risk must yield PREPARE.")

    def _test_rule_5_external_no_assessment_yields_analyze(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(_make_capability("cap", source_kind=CapabilitySourceKind.REST_API))
        self.assert_equal(
            decision.level,
            PolicyLevel.ANALYZE,
            "Rule 5: non-INTERNAL with no assessment must yield ANALYZE.",
        )

    def _test_rule_6_otherwise_yields_execute(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(_make_capability("cap", source_kind=CapabilitySourceKind.INTERNAL))
        self.assert_equal(decision.level, PolicyLevel.EXECUTE, "Rule 6: otherwise must yield EXECUTE.")

    # ---------- 4-5. Precedence ----------

    def _test_precedence_revoked_and_high_yields_observe(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            _make_capability("cap"),
            security_assessment=_make_assessment(SecurityRiskLevel.HIGH),
            lifecycle_status=CapabilityLifecycleStatus.REVOKED,
        )
        self.assert_equal(
            decision.level,
            PolicyLevel.OBSERVE,
            "REVOKED + HIGH must yield OBSERVE: lifecycle is checked before security risk.",
        )

    def _test_precedence_disabled_and_high_yields_observe(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            _make_capability("cap"),
            security_assessment=_make_assessment(SecurityRiskLevel.HIGH),
            lifecycle_status=CapabilityLifecycleStatus.DISABLED,
        )
        self.assert_equal(
            decision.level,
            PolicyLevel.OBSERVE,
            "DISABLED + HIGH must yield OBSERVE: lifecycle is checked before security risk.",
        )

    # ---------- 6-10. Security/lifecycle combinations ----------

    def _test_internal_no_assessment_yields_execute(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(_make_capability("cap", source_kind=CapabilitySourceKind.INTERNAL))
        self.assert_equal(decision.level, PolicyLevel.EXECUTE, "INTERNAL + no assessment must yield EXECUTE.")

    def _test_external_low_assessment_yields_execute(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            _make_capability("cap", source_kind=CapabilitySourceKind.LOCAL_CLI),
            security_assessment=_make_assessment(SecurityRiskLevel.LOW),
        )
        self.assert_equal(
            decision.level, PolicyLevel.EXECUTE, "External + LOW assessment must yield EXECUTE."
        )

    def _test_external_medium_yields_prepare(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            _make_capability("cap", source_kind=CapabilitySourceKind.LOCAL_CLI),
            security_assessment=_make_assessment(SecurityRiskLevel.MEDIUM),
        )
        self.assert_equal(decision.level, PolicyLevel.PREPARE, "External + MEDIUM must yield PREPARE.")

    def _test_external_high_yields_require_approval(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            _make_capability("cap", source_kind=CapabilitySourceKind.LOCAL_CLI),
            security_assessment=_make_assessment(SecurityRiskLevel.HIGH),
        )
        self.assert_equal(
            decision.level, PolicyLevel.REQUIRE_APPROVAL, "External + HIGH must yield REQUIRE_APPROVAL."
        )

    def _test_missing_assessment_external_yields_analyze(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(_make_capability("cap", source_kind=CapabilitySourceKind.BROWSER_SERVICE))
        self.assert_equal(
            decision.level, PolicyLevel.ANALYZE, "Missing assessment for an external capability must yield ANALYZE."
        )

    # ---------- 11-12. Optional inputs ----------

    def _test_lifecycle_status_none_works(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(_make_capability("cap"), lifecycle_status=None)
        self.assert_equal(decision.level, PolicyLevel.EXECUTE, "lifecycle_status=None must work and not raise.")

    def _test_security_assessment_none_works(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(_make_capability("cap"), security_assessment=None)
        self.assert_equal(decision.level, PolicyLevel.EXECUTE, "security_assessment=None must work and not raise.")

    # ---------- 13. Invalid input ----------

    def _test_evaluate_none_raises(self) -> None:
        engine = PolicyEngine()
        raised = False
        try:
            engine.evaluate(None)
        except CapabilityPolicyProviderError:
            raised = True
        self.assert_true(raised, "evaluate(None, ...) must raise CapabilityPolicyProviderError.")

    # ---------- 14-16. Immutability / determinism ----------

    def _test_policy_decision_is_immutable(self) -> None:
        decision = PolicyEngine().evaluate(_make_capability("cap"))
        raised = False
        try:
            decision.level = PolicyLevel.OBSERVE  # type: ignore[misc]
        except Exception:
            raised = True
        self.assert_true(raised, "PolicyDecision must be immutable (frozen dataclass).")

    def _test_reasons_are_deterministic(self) -> None:
        engine = PolicyEngine()
        capability = _make_capability("cap")
        first = engine.evaluate(capability, lifecycle_status=CapabilityLifecycleStatus.REVOKED)
        second = engine.evaluate(capability, lifecycle_status=CapabilityLifecycleStatus.REVOKED)
        self.assert_equal(first.reasons, second.reasons, "reasons must be identical across repeated identical calls.")
        self.assert_true(len(first.reasons) >= 1, "reasons must contain at least one entry.")

    def _test_repeated_evaluation_produces_equal_decisions(self) -> None:
        engine = PolicyEngine()
        capability = _make_capability("cap", source_kind=CapabilitySourceKind.LOCAL_CLI)
        assessment = _make_assessment(SecurityRiskLevel.MEDIUM)
        first = engine.evaluate(capability, security_assessment=assessment)
        second = engine.evaluate(capability, security_assessment=assessment)
        self.assert_equal(first, second, "Two identical evaluate() calls must produce equal PolicyDecision values.")

    # ---------- 17-19. No mutation of inputs ----------

    def _test_capability_not_mutated(self) -> None:
        capability = _make_capability("cap", source_kind=CapabilitySourceKind.LOCAL_CLI)
        PolicyEngine().evaluate(
            capability,
            security_assessment=_make_assessment(SecurityRiskLevel.HIGH),
            lifecycle_status=CapabilityLifecycleStatus.REVOKED,
        )
        self.assert_equal(capability.id, "cap", "Capability.id must be unchanged.")
        self.assert_true(capability.enabled, "Capability.enabled must be unchanged.")

    def _test_security_assessment_not_mutated(self) -> None:
        assessment = _make_assessment(SecurityRiskLevel.HIGH)
        PolicyEngine().evaluate(_make_capability("cap"), security_assessment=assessment)
        self.assert_equal(
            assessment.overall_risk_level, SecurityRiskLevel.HIGH, "CapabilitySecurityAssessment must be unchanged."
        )

    def _test_lifecycle_status_not_mutated(self) -> None:
        status = CapabilityLifecycleStatus.DISABLED
        PolicyEngine().evaluate(_make_capability("cap"), lifecycle_status=status)
        self.assert_equal(status, CapabilityLifecycleStatus.DISABLED, "CapabilityLifecycleStatus must be unchanged.")

    # ---------- 20-21. Engine delegation ----------

    def _test_engine_delegates_to_configured_provider(self) -> None:
        fake_provider = _RecordingFakeProvider()
        engine = PolicyEngine(provider=fake_provider)
        capability = _make_capability("cap")
        assessment = _make_assessment(SecurityRiskLevel.LOW)
        status = CapabilityLifecycleStatus.ACTIVE

        decision = engine.evaluate(capability, security_assessment=assessment, lifecycle_status=status)

        self.assert_equal(len(fake_provider.calls), 1, "The engine must delegate exactly once per evaluate() call.")
        recorded_capability, recorded_assessment, recorded_status = fake_provider.calls[0]
        self.assert_true(recorded_capability is capability, "The capability must be forwarded unchanged.")
        self.assert_true(recorded_assessment is assessment, "The assessment must be forwarded unchanged.")
        self.assert_equal(recorded_status, status, "The lifecycle status must be forwarded unchanged.")
        self.assert_equal(
            decision.level, PolicyLevel.EXECUTE, "The engine must return the provider's own result unchanged."
        )

    def _test_engine_defaults_to_default_provider(self) -> None:
        engine = PolicyEngine()
        self.assert_true(
            isinstance(engine._provider, DefaultPolicyProvider),
            "PolicyEngine must default to DefaultPolicyProvider when none is supplied.",
        )

    # ---------- 22-26. Dependency boundaries ----------

    def _test_no_forbidden_imports(self) -> None:
        forbidden_substrings = (
            "capability_registry",
            "capability_backend",
            "capability_discovery",
            "capability_security_engine",
            "capability_lifecycle_registry",
            "src.core.planning",
            "src.core.agent",
            "src.core.tool",
            "tool_execution_provider",
            "tool_engine",
            "src.bootstrap",
            "config",
        )
        for module in (_result_module, _provider_module, _engine_module):
            source = inspect.getsource(module)
            import_lines = " ".join(_IMPORT_LINE_PATTERN.findall(source)).lower()
            for forbidden in forbidden_substrings:
                self.assert_false(
                    forbidden in import_lines,
                    f"{module.__name__} must not import anything referencing '{forbidden}'.",
                )

    # ---------- 27. No DENY level ----------

    def _test_no_deny_level_exists(self) -> None:
        self.assert_false(
            hasattr(PolicyLevel, "DENY"), "PolicyLevel must not define a DENY member."
        )
        self.assert_false(
            "DENY" in {member.value for member in PolicyLevel}, "No PolicyLevel value may be 'DENY'."
        )

    # ---------- 28-30. Mandatory OBSERVE semantics ----------

    def _test_observe_is_documented_as_restrictive(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(_make_capability("cap"), lifecycle_status=CapabilityLifecycleStatus.REVOKED)
        self.assert_equal(decision.level, PolicyLevel.OBSERVE, "REVOKED must produce OBSERVE.")
        reasons_text = " ".join(decision.reasons).lower()
        self.assert_true(
            "restrictive" in reasons_text,
            "The OBSERVE decision's own reasons must describe it as restrictive, per the mandatory clarification.",
        )
        self.assert_true(
            "not execution authorization" in reasons_text,
            "The OBSERVE decision's own reasons must state it is not execution authorization.",
        )

    def _test_revoked_observe_does_not_imply_executable(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(_make_capability("cap"), lifecycle_status=CapabilityLifecycleStatus.REVOKED)
        self.assert_equal(decision.level, PolicyLevel.OBSERVE, "REVOKED must produce OBSERVE.")
        self.assert_false(
            decision.level == PolicyLevel.EXECUTE,
            "A REVOKED capability's OBSERVE decision must never equal EXECUTE -- OBSERVE does not imply executable permission.",
        )

    def _test_disabled_observe_does_not_imply_executable(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(_make_capability("cap"), lifecycle_status=CapabilityLifecycleStatus.DISABLED)
        self.assert_equal(decision.level, PolicyLevel.OBSERVE, "DISABLED must produce OBSERVE.")
        self.assert_false(
            decision.level == PolicyLevel.EXECUTE,
            "A DISABLED capability's OBSERVE decision must never equal EXECUTE -- OBSERVE does not imply executable permission.",
        )

    # ---------- Error hierarchy ----------

    def _test_provider_error_is_a_policy_error(self) -> None:
        caught_as_root = False
        try:
            raise CapabilityPolicyProviderError("example failure")
        except CapabilityPolicyError:
            caught_as_root = True
        self.assert_true(
            caught_as_root, "A raised CapabilityPolicyProviderError must be catchable as CapabilityPolicyError."
        )
