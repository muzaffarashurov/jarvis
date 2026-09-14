"""Capability Security Provider framework for EP-069.6 (advisory assessment slice).

Defines the structural contract every capability security-assessment
strategy implements (`CapabilitySecurityProvider`), this package's own
exception hierarchy, and the one concrete, deterministic, built-in
strategy (`DefaultCapabilitySecurityProvider`) -- directly mirroring
the Provider framework pattern already established by
`src/core/capability_discovery/capability_discovery_provider.py`'s
`CapabilityDiscoveryProvider`/`DefaultCapabilityDiscoveryProvider`.

`DefaultCapabilitySecurityProvider` performs exactly three
deterministic checks against a `Capability`'s already-declared
metadata only -- no dependency/package scanning, no sandboxing, no
network access, no filesystem access, no external tool invocation, and
no AI/LLM reasoning. It never mutates the `Capability` it assesses and
never queries a `CapabilityRegistry` itself. See
`docs/architecture/designs/EP069_6_DESIGN.md` Sections 7 and 9 for the
full rationale and Non-Goals.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.capability.capability import Capability, CapabilitySourceKind, CapabilityTrustLevel
from src.core.capability_security.capability_security_result import (
    CapabilitySecurityAssessment,
    SecurityFinding,
    SecurityRiskLevel,
)

__all__ = [
    "CapabilitySecurityError",
    "CapabilitySecurityProviderError",
    "CapabilitySecurityProvider",
    "DefaultCapabilitySecurityProvider",
]

# Starter, case-insensitive substring list for the "high-risk
# permission tag" check (EP069_6_DESIGN.md Owner Decision OD5).
# `required_permissions` is a free-form tuple of strings (EP-069.4,
# `EP069_4_DESIGN.md` Owner Decision D5 -- no structured taxonomy), so
# this is a documented, adjustable heuristic, not an exhaustive or
# authoritative classification.
_HIGH_RISK_PERMISSION_SUBSTRINGS: tuple[str, ...] = (
    "credential",
    "secret",
    "network",
    "filesystem.write",
    "process",
    "shell",
)


class CapabilitySecurityError(Exception):
    """Common root for every exception raised by the Capability Security package (EP-069.6).

    Downstream packages can catch this single type to handle "anything
    capability-security-related" without needing to know about every
    specific failure mode, mirroring `CapabilityError`'s
    (EP-069.4) and `CapabilityDiscoveryError`'s (EP-069.5) identical
    role.
    """


class CapabilitySecurityProviderError(CapabilitySecurityError):
    """Raised when a `CapabilitySecurityProvider` is called with invalid input.

    Covers only a `None` `capability` argument -- this package's
    contract has no numeric/count parameter analogous to
    `CapabilityDiscoveryProvider.discover()`'s `max_results`.
    """


class CapabilitySecurityProvider(ABC):
    """Structural contract every capability security-assessment strategy implements.

    A provider assesses one already-fetched `Capability` -- it never
    queries a live `CapabilityRegistry` itself, mirroring
    `CapabilityDiscoveryProvider.discover()`'s own identical
    convention. A provider never mutates the `Capability` it assesses,
    never invokes it, never performs network or filesystem I/O beyond
    reading the in-memory object's own fields, and never performs
    AI/LLM inference.
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return this provider's stable, human-readable name.

        Must be cheap and side-effect free -- no network or expensive
        work.
        """
        raise NotImplementedError

    @abstractmethod
    def assess(self, capability: Capability) -> CapabilitySecurityAssessment:
        """Assess one `Capability`'s already-declared metadata.

        Args:
            capability: The capability to assess. Never mutated.

        Returns:
            The resulting `CapabilitySecurityAssessment` -- advisory
            only; never a binding approve/reject decision.

        Raises:
            CapabilitySecurityProviderError: If `capability` is `None`.
        """
        raise NotImplementedError

    # ---------- Lifecycle / diagnostics extension point ----------

    def is_available(self) -> bool:
        """Return whether this provider is currently able to perform assessment.

        Base implementation always returns True. Providers with an
        enabled/configured distinction should override this method.
        """
        return True


class DefaultCapabilitySecurityProvider(CapabilitySecurityProvider):
    """Deterministic, non-AI capability security-assessment strategy.

    Performs exactly three checks against a `Capability`'s already-
    declared fields, each independently producing zero or one
    `SecurityFinding`:

    1. **Missing provenance**: `source_kind != INTERNAL` and `source`
       is blank -> `MEDIUM` finding (`"missing_provenance"`).
    2. **Trust/source inconsistency**: `source_kind != INTERNAL` and
       `trust_level == TRUSTED_INTERNAL` -> `HIGH` finding
       (`"trust_source_mismatch"`) -- an externally sourced capability
       cannot legitimately claim the internal trust tier.
    3. **High-risk permission tag**: `source_kind != INTERNAL` and any
       tag in `required_permissions` case-insensitively contains one
       of a small, fixed, documented substring list -> `HIGH` finding
       (`"high_risk_permission"`, naming the matched tag).

    An `INTERNAL` capability never triggers checks 1 or 2 or 3,
    regardless of its other field values -- all three are gated on
    `source_kind != INTERNAL`. `overall_risk_level` is the maximum
    `risk_level` across every triggered finding, or `LOW` when none
    trigger.
    """

    def provider_name(self) -> str:
        return "default"

    def assess(self, capability: Capability) -> CapabilitySecurityAssessment:
        if capability is None:
            raise CapabilitySecurityProviderError("'capability' must not be None.")

        findings: list[SecurityFinding] = []

        is_external = capability.source_kind != CapabilitySourceKind.INTERNAL

        if is_external and not capability.source.strip():
            findings.append(
                SecurityFinding(
                    category="missing_provenance",
                    message=(
                        f"Capability '{capability.id}' is sourced externally "
                        f"({capability.source_kind.value}) but declares no 'source' provenance."
                    ),
                    risk_level=SecurityRiskLevel.MEDIUM,
                )
            )

        if is_external and capability.trust_level == CapabilityTrustLevel.TRUSTED_INTERNAL:
            findings.append(
                SecurityFinding(
                    category="trust_source_mismatch",
                    message=(
                        f"Capability '{capability.id}' is sourced externally "
                        f"({capability.source_kind.value}) but declares TRUSTED_INTERNAL trust."
                    ),
                    risk_level=SecurityRiskLevel.HIGH,
                )
            )

        if is_external:
            for tag in capability.required_permissions:
                lowered_tag = tag.lower()
                matched = next(
                    (
                        substring
                        for substring in _HIGH_RISK_PERMISSION_SUBSTRINGS
                        if substring in lowered_tag
                    ),
                    None,
                )
                if matched is not None:
                    findings.append(
                        SecurityFinding(
                            category="high_risk_permission",
                            message=(
                                f"Capability '{capability.id}' is sourced externally "
                                f"({capability.source_kind.value}) and declares a high-risk "
                                f"required permission tag: '{tag}'."
                            ),
                            risk_level=SecurityRiskLevel.HIGH,
                        )
                    )

        return CapabilitySecurityAssessment.from_findings(capability, findings)
