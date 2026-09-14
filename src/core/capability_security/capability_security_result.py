"""Domain model for EP-069.6 External Capability Security & Supply-Chain Trust
(advisory assessment slice).

Defines the plain, read-only outcome data types shared by
`CapabilitySecurityProvider` (the actual assessment algorithm) and
`CapabilitySecurityEngine` (thin orchestration): `SecurityRiskLevel`
(a coarse-grained risk classification), `SecurityFinding` (a single,
specific concern), and `CapabilitySecurityAssessment` (the outcome of
assessing one `Capability`). This module owns no assessment logic and
no registry access -- it mirrors the role of `src/core/
capability_discovery/capability_discovery_result.py` relative to
`CapabilityDiscoveryProvider`/`CapabilityDiscoveryEngine`.

**Advisory only.** `CapabilitySecurityAssessment` carries no
`approved`/`rejected`/`allowed` field of any kind -- this package makes
no binding decision. A future EP-070 (Policy, Permissions & Human
Approval Engine, not yet implemented in this repository) or any other
future policy consumer is expected to read this shape and make its own
decision. See `docs/architecture/designs/EP069_6_DESIGN.md` Owner
Decision OD2.

This package performs no dependency/package scanning, no sandboxing,
no execution, and no credential handling -- see
`docs/architecture/designs/EP069_6_DESIGN.md` for the full
architecture, scope boundary, and Owner Decisions (OD1-OD6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.core.capability.capability import Capability

__all__ = [
    "SecurityRiskLevel",
    "SecurityFinding",
    "CapabilitySecurityAssessment",
]


class SecurityRiskLevel(str, Enum):
    """A coarse-grained, advisory risk classification.

    Deliberately three levels, no `CRITICAL` tier and no numeric
    score -- mirroring `CapabilityTrustLevel`'s own rationale
    (EP-069.4, `EP069_4_DESIGN.md` Owner Decision D6): a finer-grained
    or numeric scale implies a scoring algorithm sophistication this
    advisory slice does not attempt, and would prejudge a future, more
    complete EP-069.6 phase's own design.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


# Ordinal ordering used only to compute `overall_risk_level` as the
# maximum across a set of findings -- not exposed as a public ranking
# API, and never used to make or imply a binding decision.
_RISK_RANK: dict[SecurityRiskLevel, int] = {
    SecurityRiskLevel.LOW: 0,
    SecurityRiskLevel.MEDIUM: 1,
    SecurityRiskLevel.HIGH: 2,
}


@dataclass(frozen=True)
class SecurityFinding:
    """A single, specific concern raised while assessing one `Capability`.

    Attributes:
        category: A short, stable identifier for the kind of concern
            (e.g. `"missing_provenance"`, `"trust_source_mismatch"`,
            `"high_risk_permission"`).
        message: A human-readable explanation of the concern.
        risk_level: This finding's own contribution to the overall
            assessment.
    """

    category: str
    message: str
    risk_level: SecurityRiskLevel


@dataclass(frozen=True)
class CapabilitySecurityAssessment:
    """The advisory outcome of assessing one `Capability`.

    Carries no `approved`/`rejected`/`allowed` field of any kind
    (Owner Decision OD2) -- this is a risk classification and a list
    of findings only, never a binding decision.

    Attributes:
        capability_id: The id of the `Capability` that was assessed.
        overall_risk_level: The highest `risk_level` among `findings`,
            or `SecurityRiskLevel.LOW` when `findings` is empty.
        findings: Every concern raised during assessment. May be
            empty -- a capability with no triggered finding is a
            normal, valid outcome, not an error.
    """

    capability_id: str
    overall_risk_level: SecurityRiskLevel
    findings: list[SecurityFinding] = field(default_factory=list)

    @staticmethod
    def from_findings(capability: Capability, findings: list[SecurityFinding]) -> "CapabilitySecurityAssessment":
        """Build an assessment from a capability and its triggered findings.

        Args:
            capability: The `Capability` that was assessed.
            findings: Every `SecurityFinding` triggered for it, in any
                order.

        Returns:
            A `CapabilitySecurityAssessment` whose `overall_risk_level`
            is the maximum `risk_level` across `findings`, or `LOW`
            when `findings` is empty.
        """
        if findings:
            overall_risk_level = max(findings, key=lambda finding: _RISK_RANK[finding.risk_level]).risk_level
        else:
            overall_risk_level = SecurityRiskLevel.LOW

        return CapabilitySecurityAssessment(
            capability_id=capability.id,
            overall_risk_level=overall_risk_level,
            findings=list(findings),
        )
