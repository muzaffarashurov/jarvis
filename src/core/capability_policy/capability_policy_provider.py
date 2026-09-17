"""Capability Policy Provider framework for EP-070.

Defines the structural contract every policy-decision strategy
implements (`PolicyProvider`), this package's own exception hierarchy,
and the one concrete, deterministic, built-in strategy
(`DefaultPolicyProvider`) -- directly mirroring the Provider framework
pattern already established by `src/core/capability_discovery/
capability_discovery_provider.py` and `src/core/capability_security/
capability_security_provider.py`.

`DefaultPolicyProvider` implements exactly the six-row rule table
approved as Owner Decision OD4 in
`docs/architecture/designs/EP070_DESIGN.md` -- unchanged, unreordered,
with no additional row and no additional condition. It performs no
I/O, no network access, no filesystem access, no randomness, and no
wall-clock-time dependency; its decisions derive exclusively from the
three arguments passed to `evaluate()`.

**Mandatory semantic clarification (Owner-issued): `OBSERVE` is a
restrictive policy decision, not execution authorization.** Rows 1 and
2 of the table below (`REVOKED`/`DISABLED` lifecycle status) both
produce `OBSERVE` -- this does not mean the capability is executable;
it means the opposite. This module performs no enforcement of this or
any other decision.

This package has **zero dependency** on `CapabilityRegistry`,
`CapabilityDiscoveryEngine`, `CapabilitySecurityEngine`, or
`CapabilityLifecycleRegistry` -- the caller supplies
`security_assessment`/`lifecycle_status` directly; this module never
fetches them itself.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.capability.capability import Capability, CapabilitySourceKind
from src.core.capability_lifecycle.capability_lifecycle_result import (
    CapabilityLifecycleStatus,
)
from src.core.capability_policy.capability_policy_result import (
    PolicyDecision,
    PolicyLevel,
)
from src.core.capability_security.capability_security_result import (
    CapabilitySecurityAssessment,
    SecurityRiskLevel,
)

__all__ = [
    "CapabilityPolicyError",
    "CapabilityPolicyProviderError",
    "PolicyProvider",
    "DefaultPolicyProvider",
]


class CapabilityPolicyError(Exception):
    """Common root for every exception raised by the Capability Policy package (EP-070).

    Downstream packages can catch this single type to handle "anything
    capability-policy-related" without needing to know about every
    specific failure mode, mirroring `CapabilityError`'s (EP-069.4),
    `CapabilityDiscoveryError`'s (EP-069.5), `CapabilitySecurityError`'s
    (EP-069.6), and `CapabilityLifecycleError`'s (EP-069.7) identical
    role.
    """


class CapabilityPolicyProviderError(CapabilityPolicyError):
    """Raised when a `PolicyProvider` is called with invalid input.

    Covers only a `None` `capability` argument -- this package's
    contract has no numeric/count parameter analogous to
    `CapabilityDiscoveryProvider.discover()`'s `max_results`.
    """


class PolicyProvider(ABC):
    """Structural contract every capability policy-decision strategy implements.

    A provider evaluates one already-identified `Capability` plus
    optional, already-produced EP-069.6/EP-069.7 outputs -- it never
    queries `CapabilityRegistry`, calls `CapabilitySecurityEngine` or
    `CapabilityDiscoveryEngine`, or queries
    `CapabilityLifecycleRegistry` itself. A provider never mutates any
    argument, performs no I/O, and produces no enforcement action of
    any kind -- only a `PolicyDecision`.
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return this provider's stable, human-readable name.

        Must be cheap and side-effect free -- no network or expensive
        work.
        """
        raise NotImplementedError

    @abstractmethod
    def evaluate(
        self,
        capability: Capability,
        security_assessment: CapabilitySecurityAssessment | None = None,
        lifecycle_status: CapabilityLifecycleStatus | None = None,
    ) -> PolicyDecision:
        """Compute a policy decision for one capability.

        Args:
            capability: The capability to evaluate. Never mutated.
            security_assessment: The capability's already-produced
                EP-069.6 assessment, if one was run. This method never
                calls `CapabilitySecurityEngine.assess()` itself.
            lifecycle_status: The capability's already-queried
                EP-069.7 lifecycle status, if it is tracked. This
                method never calls
                `CapabilityLifecycleRegistry.status()` itself.

        Returns:
            The resulting `PolicyDecision` -- a decision only, never an
            enforcement action.

        Raises:
            CapabilityPolicyProviderError: If `capability` is `None`.
        """
        raise NotImplementedError

    # ---------- Lifecycle / diagnostics extension point ----------

    def is_available(self) -> bool:
        """Return whether this provider is currently able to compute a decision.

        Base implementation always returns True. Providers with an
        enabled/configured distinction should override this method.
        """
        return True


class DefaultPolicyProvider(PolicyProvider):
    """Deterministic, non-AI capability policy-decision strategy.

    Implements Owner Decision OD4's approved rule table exactly, in
    this exact order, evaluated top-to-bottom with the first matching
    rule winning:

    1. ``lifecycle_status is REVOKED`` -> ``OBSERVE``
    2. ``lifecycle_status is DISABLED`` -> ``OBSERVE``
    3. ``security_assessment.overall_risk_level is HIGH`` -> ``REQUIRE_APPROVAL``
    4. ``security_assessment.overall_risk_level is MEDIUM`` -> ``PREPARE``
    5. ``capability.source_kind is not INTERNAL and security_assessment is None`` -> ``ANALYZE``
    6. otherwise -> ``EXECUTE``

    Rows 1 and 2 both produce ``OBSERVE`` -- a **restrictive** result,
    not execution authorization (this module's own docstring; Owner
    Decision OD4/OD5's mandatory clarification). A `REVOKED` or
    `DISABLED` capability reaching this provider is never, as a result
    of this decision, treated as executable.
    """

    def provider_name(self) -> str:
        return "default"

    def evaluate(
        self,
        capability: Capability,
        security_assessment: CapabilitySecurityAssessment | None = None,
        lifecycle_status: CapabilityLifecycleStatus | None = None,
    ) -> PolicyDecision:
        if capability is None:
            raise CapabilityPolicyProviderError("'capability' must not be None.")

        # Rule 1: lifecycle REVOKED -> OBSERVE (restrictive, not executable).
        if lifecycle_status == CapabilityLifecycleStatus.REVOKED:
            return PolicyDecision(
                capability_id=capability.id,
                level=PolicyLevel.OBSERVE,
                reasons=(
                    "lifecycle_status is REVOKED: OBSERVE is a restrictive "
                    "decision, not execution authorization.",
                ),
            )

        # Rule 2: lifecycle DISABLED -> OBSERVE (restrictive, not executable).
        if lifecycle_status == CapabilityLifecycleStatus.DISABLED:
            return PolicyDecision(
                capability_id=capability.id,
                level=PolicyLevel.OBSERVE,
                reasons=(
                    "lifecycle_status is DISABLED: OBSERVE is a restrictive "
                    "decision, not execution authorization.",
                ),
            )

        # Rule 3: security assessment HIGH risk -> REQUIRE_APPROVAL.
        if (
            security_assessment is not None
            and security_assessment.overall_risk_level == SecurityRiskLevel.HIGH
        ):
            return PolicyDecision(
                capability_id=capability.id,
                level=PolicyLevel.REQUIRE_APPROVAL,
                reasons=("security_assessment.overall_risk_level is HIGH.",),
            )

        # Rule 4: security assessment MEDIUM risk -> PREPARE.
        if (
            security_assessment is not None
            and security_assessment.overall_risk_level == SecurityRiskLevel.MEDIUM
        ):
            return PolicyDecision(
                capability_id=capability.id,
                level=PolicyLevel.PREPARE,
                reasons=("security_assessment.overall_risk_level is MEDIUM.",),
            )

        # Rule 5: non-INTERNAL capability with no assessment -> ANALYZE.
        if capability.source_kind != CapabilitySourceKind.INTERNAL and security_assessment is None:
            return PolicyDecision(
                capability_id=capability.id,
                level=PolicyLevel.ANALYZE,
                reasons=(
                    "capability.source_kind is not INTERNAL and no "
                    "security_assessment was supplied.",
                ),
            )

        # Rule 6: otherwise -> EXECUTE.
        return PolicyDecision(
            capability_id=capability.id,
            level=PolicyLevel.EXECUTE,
            reasons=("No restrictive rule matched.",),
        )
