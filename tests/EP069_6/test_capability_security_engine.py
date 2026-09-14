"""Real engineering tests for EP-069.6 STEP 2 - Capability Security & Supply-Chain
Trust (advisory assessment slice).

Self-contained test suite (`NAME = "EP069_6"`) under `tests/EP069_6/`,
following `tests/EP069_5/test_capability_discovery_engine.py`'s own
precedent of a package per sub-EP. Does not import `src.bootstrap` --
`EP069_6_DESIGN.md` Owner Decision OD4 explicitly excludes bootstrap/
CLI/config wiring from this EP's scope.

Covers every behavioral area required by the approved STEP 1 design's
Section 18 (Testing Strategy):
    1. core behavior (LOW-risk baseline, both INTERNAL and non-INTERNAL)
    2. validation / error handling (assess(None))
    3. each finding category independently
    4. multi-finding aggregation (overall_risk_level = max)
    5. INTERNAL-capability exemption from all three checks
    6. deterministic, repeated-call behavior
    7. integration boundaries (no forbidden imports, no mutation)
    8. public API / import behavior
    9. error hierarchy (CapabilitySecurityError root)
"""

from __future__ import annotations

import inspect
import re

from src.core.capability import Capability, CapabilitySourceKind, CapabilityTrustLevel
from src.core.capability_security import (
    CapabilitySecurityAssessment,
    CapabilitySecurityEngine,
    CapabilitySecurityError,
    CapabilitySecurityProvider,
    CapabilitySecurityProviderError,
    DefaultCapabilitySecurityProvider,
    SecurityRiskLevel,
)
from src.core.capability_security import capability_security_engine as _engine_module
from src.core.capability_security import capability_security_provider as _provider_module
from src.core.capability_security import capability_security_result as _result_module
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

_IMPORT_LINE_PATTERN = re.compile(r"^(?:from|import)\s+\S.*$", re.MULTILINE)


def _make_capability(
    id: str,
    source_kind: CapabilitySourceKind = CapabilitySourceKind.INTERNAL,
    source: str = "",
    trust_level: CapabilityTrustLevel = CapabilityTrustLevel.UNVERIFIED,
    required_permissions: tuple[str, ...] = (),
) -> Capability:
    """Build a test `Capability` via EP-069.4's own, unmodified `Capability.create()`."""
    return Capability.create(
        id=id,
        name="Test Capability",
        description="A capability used for EP-069.6 testing.",
        source_kind=source_kind,
        source=source,
        trust_level=trust_level,
        required_permissions=required_permissions,
    )


@TestRegistry.register
class CapabilitySecurityEngineTest(BaseTest):
    NAME = "EP069_6"

    def run(self):
        # ---------- Public API / import behavior ----------
        self._test_public_api_exports()

        # ---------- Core behavior ----------
        self._test_internal_capability_yields_low_risk_no_findings()
        self._test_external_capability_with_provenance_yields_low_risk()

        # ---------- Validation / error handling ----------
        self._test_assess_none_raises()

        # ---------- Each finding category independently ----------
        self._test_missing_provenance_finding()
        self._test_trust_source_mismatch_finding()
        self._test_high_risk_permission_finding()

        # ---------- Multi-finding aggregation ----------
        self._test_multiple_findings_report_max_risk_and_all_findings()

        # ---------- INTERNAL exemption ----------
        self._test_internal_capability_exempt_from_all_checks()

        # ---------- Deterministic behavior ----------
        self._test_deterministic_repeated_assessment()

        # ---------- Integration boundaries ----------
        self._test_no_forbidden_imports()
        self._test_engine_does_not_mutate_capability()
        self._test_engine_defaults_to_default_provider()
        self._test_engine_delegates_to_custom_provider()

        # ---------- Error hierarchy ----------
        self._test_provider_error_is_a_security_error()

        return self.result

    # ---------- Public API / import behavior ----------

    def _test_public_api_exports(self) -> None:
        self.assert_true(
            issubclass(CapabilitySecurityProviderError, CapabilitySecurityError),
            "CapabilitySecurityProviderError must subclass CapabilitySecurityError.",
        )
        self.assert_true(
            issubclass(DefaultCapabilitySecurityProvider, CapabilitySecurityProvider),
            "DefaultCapabilitySecurityProvider must implement CapabilitySecurityProvider.",
        )
        engine = CapabilitySecurityEngine()
        self.assert_true(
            isinstance(engine, CapabilitySecurityEngine),
            "CapabilitySecurityEngine must be constructible with no arguments.",
        )

    # ---------- Core behavior ----------

    def _test_internal_capability_yields_low_risk_no_findings(self) -> None:
        capability = _make_capability("internal_tool", source_kind=CapabilitySourceKind.INTERNAL)
        engine = CapabilitySecurityEngine()

        assessment = engine.assess(capability)

        self.assert_equal(
            assessment.overall_risk_level,
            SecurityRiskLevel.LOW,
            "An INTERNAL capability with no risky fields must assess as LOW.",
        )
        self.assert_equal(assessment.findings, [], "No findings should be triggered.")
        self.assert_equal(
            assessment.capability_id, "internal_tool", "The assessment must carry the assessed capability's id."
        )

    def _test_external_capability_with_provenance_yields_low_risk(self) -> None:
        capability = _make_capability(
            "external_api",
            source_kind=CapabilitySourceKind.REST_API,
            source="https://example.com/api",
            trust_level=CapabilityTrustLevel.TRUSTED_CONFIGURED,
            required_permissions=("read_only",),
        )
        engine = CapabilitySecurityEngine()

        assessment = engine.assess(capability)

        self.assert_equal(
            assessment.overall_risk_level,
            SecurityRiskLevel.LOW,
            "A non-INTERNAL capability with provenance, consistent trust, and no risky "
            "permission tags must assess as LOW.",
        )

    # ---------- Validation / error handling ----------

    def _test_assess_none_raises(self) -> None:
        engine = CapabilitySecurityEngine()

        raised = False
        try:
            engine.assess(None)
        except CapabilitySecurityProviderError:
            raised = True
        self.assert_true(raised, "assess(None) must raise CapabilitySecurityProviderError.")

    # ---------- Each finding category independently ----------

    def _test_missing_provenance_finding(self) -> None:
        capability = _make_capability(
            "no_source", source_kind=CapabilitySourceKind.LOCAL_CLI, source=""
        )
        engine = CapabilitySecurityEngine()

        assessment = engine.assess(capability)

        self.assert_equal(len(assessment.findings), 1, "Exactly one finding must be triggered.")
        self.assert_equal(
            assessment.findings[0].category, "missing_provenance", "The finding category must be 'missing_provenance'."
        )
        self.assert_equal(
            assessment.findings[0].risk_level, SecurityRiskLevel.MEDIUM, "missing_provenance must be MEDIUM risk."
        )
        self.assert_equal(
            assessment.overall_risk_level, SecurityRiskLevel.MEDIUM, "overall_risk_level must reflect the finding."
        )

    def _test_trust_source_mismatch_finding(self) -> None:
        capability = _make_capability(
            "mismatched_trust",
            source_kind=CapabilitySourceKind.BROWSER_SERVICE,
            source="https://example.com",
            trust_level=CapabilityTrustLevel.TRUSTED_INTERNAL,
        )
        engine = CapabilitySecurityEngine()

        assessment = engine.assess(capability)

        self.assert_equal(len(assessment.findings), 1, "Exactly one finding must be triggered.")
        self.assert_equal(
            assessment.findings[0].category,
            "trust_source_mismatch",
            "The finding category must be 'trust_source_mismatch'.",
        )
        self.assert_equal(
            assessment.findings[0].risk_level, SecurityRiskLevel.HIGH, "trust_source_mismatch must be HIGH risk."
        )

    def _test_high_risk_permission_finding(self) -> None:
        capability = _make_capability(
            "risky_perms",
            source_kind=CapabilitySourceKind.LOCAL_CLI,
            source="https://github.com/example/project",
            required_permissions=("credential.read", "read_only"),
        )
        engine = CapabilitySecurityEngine()

        assessment = engine.assess(capability)

        self.assert_equal(len(assessment.findings), 1, "Exactly one finding must be triggered.")
        self.assert_equal(
            assessment.findings[0].category,
            "high_risk_permission",
            "The finding category must be 'high_risk_permission'.",
        )
        self.assert_true(
            "credential.read" in assessment.findings[0].message,
            "The finding message must name the matched high-risk permission tag.",
        )
        self.assert_equal(
            assessment.findings[0].risk_level, SecurityRiskLevel.HIGH, "high_risk_permission must be HIGH risk."
        )

    # ---------- Multi-finding aggregation ----------

    def _test_multiple_findings_report_max_risk_and_all_findings(self) -> None:
        capability = _make_capability(
            "many_findings",
            source_kind=CapabilitySourceKind.LOCAL_CLI,
            source="",
            trust_level=CapabilityTrustLevel.TRUSTED_INTERNAL,
            required_permissions=("shell.execute",),
        )
        engine = CapabilitySecurityEngine()

        assessment = engine.assess(capability)

        categories = {finding.category for finding in assessment.findings}
        self.assert_equal(
            categories,
            {"missing_provenance", "trust_source_mismatch", "high_risk_permission"},
            "All three independently-triggerable findings must be present.",
        )
        self.assert_equal(
            assessment.overall_risk_level,
            SecurityRiskLevel.HIGH,
            "overall_risk_level must be the maximum across all findings (HIGH, not MEDIUM).",
        )

    # ---------- INTERNAL exemption ----------

    def _test_internal_capability_exempt_from_all_checks(self) -> None:
        # Deliberately combines every individually-risky field value
        # with source_kind=INTERNAL, to prove all three checks are
        # gated on source_kind != INTERNAL, not merely coincidentally
        # non-triggering.
        capability = _make_capability(
            "internal_with_risky_fields",
            source_kind=CapabilitySourceKind.INTERNAL,
            source="",
            trust_level=CapabilityTrustLevel.TRUSTED_CONFIGURED,
            required_permissions=("credential.read", "shell.execute"),
        )
        engine = CapabilitySecurityEngine()

        assessment = engine.assess(capability)

        self.assert_equal(
            assessment.findings,
            [],
            "An INTERNAL capability must never trigger any finding, regardless of its other field values.",
        )
        self.assert_equal(assessment.overall_risk_level, SecurityRiskLevel.LOW, "Must assess as LOW.")

    # ---------- Deterministic behavior ----------

    def _test_deterministic_repeated_assessment(self) -> None:
        capability = _make_capability(
            "repeatable",
            source_kind=CapabilitySourceKind.REST_API,
            source="",
            required_permissions=("network.external",),
        )
        engine = CapabilitySecurityEngine()

        first = engine.assess(capability)
        second = engine.assess(capability)

        self.assert_equal(
            first, second, "Repeated assess() calls with identical input must produce an identical assessment."
        )

    # ---------- Integration boundaries ----------

    def _test_no_forbidden_imports(self) -> None:
        forbidden_substrings = (
            "capability_discovery",
            "capability_registry",
            "capability_backend",
            "src.core.planning",
            "src.core.agent",
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

    def _test_engine_does_not_mutate_capability(self) -> None:
        capability = _make_capability("immutable_check", source_kind=CapabilitySourceKind.INTERNAL)
        engine = CapabilitySecurityEngine()

        engine.assess(capability)

        self.assert_equal(capability.id, "immutable_check", "The capability's own fields must be unchanged.")
        self.assert_true(capability.enabled, "The capability's enabled flag must be unchanged.")

    def _test_engine_defaults_to_default_provider(self) -> None:
        engine = CapabilitySecurityEngine()
        self.assert_true(
            isinstance(engine._provider, DefaultCapabilitySecurityProvider),
            "CapabilitySecurityEngine must default to DefaultCapabilitySecurityProvider when none is supplied.",
        )

    def _test_engine_delegates_to_custom_provider(self) -> None:
        capability = _make_capability("delegated", source_kind=CapabilitySourceKind.INTERNAL)

        class _RecordingFakeProvider(CapabilitySecurityProvider):
            def __init__(self) -> None:
                self.calls: list[Capability] = []

            def provider_name(self) -> str:
                return "recording_fake"

            def assess(self, capability: Capability) -> CapabilitySecurityAssessment:
                self.calls.append(capability)
                return CapabilitySecurityAssessment.from_findings(capability, [])

        fake_provider = _RecordingFakeProvider()
        engine = CapabilitySecurityEngine(provider=fake_provider)

        engine.assess(capability)

        self.assert_equal(len(fake_provider.calls), 1, "The engine must delegate exactly once per assess() call.")
        self.assert_true(
            fake_provider.calls[0] is capability, "The engine must forward the exact capability instance unchanged."
        )

    # ---------- Error hierarchy ----------

    def _test_provider_error_is_a_security_error(self) -> None:
        caught_as_root = False
        try:
            raise CapabilitySecurityProviderError("example failure")
        except CapabilitySecurityError:
            caught_as_root = True
        self.assert_true(
            caught_as_root,
            "A raised CapabilitySecurityProviderError must be catchable as CapabilitySecurityError.",
        )
