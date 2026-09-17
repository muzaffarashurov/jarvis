"""Capability Policy Engine for EP-070.

`PolicyEngine` is thin, provider-independent orchestration: it
delegates directly to its configured `PolicyProvider` and returns the
result unchanged. It performs no policy rule logic of its own (that is
the provider's job, `capability_policy_provider.py`) and no provider
selection logic (there is no Manager in this Engineering Package --
Owner Decision OD2, `docs/architecture/designs/EP070_DESIGN.md` -- the
engine is constructed directly with the one provider it will use).

This engine never queries `CapabilityRegistry`, never calls
`CapabilityDiscoveryEngine` or `CapabilitySecurityEngine`, never
queries `CapabilityLifecycleRegistry`, and never mutates any input.
It is not wired into `src/bootstrap.py`, `config/config.yaml`, or any
CLI surface, and is not connected to `ToolEngine`/
`ToolExecutionProvider` or any execution path (Owner Decision OD7) --
it performs no enforcement of any kind. A `PolicyDecision` with
`level == PolicyLevel.OBSERVE` is a restrictive result, never
execution authorization.
"""

from __future__ import annotations

from src.core.capability.capability import Capability
from src.core.capability_lifecycle.capability_lifecycle_result import (
    CapabilityLifecycleStatus,
)
from src.core.capability_policy.capability_policy_provider import (
    DefaultPolicyProvider,
    PolicyProvider,
)
from src.core.capability_policy.capability_policy_result import PolicyDecision
from src.core.capability_security.capability_security_result import (
    CapabilitySecurityAssessment,
)

__all__ = [
    "PolicyEngine",
]


class PolicyEngine:
    """Provider-independent orchestration for capability policy decisions.

    Never selects, constructs, or reconfigures a provider on its own
    behalf beyond the one supplied (or defaulted) at construction
    time, mirroring `CapabilityDiscoveryEngine`'s/
    `CapabilitySecurityEngine`'s own documented boundary. Never
    duplicates `PolicyProvider`'s rule logic.
    """

    def __init__(self, provider: PolicyProvider | None = None) -> None:
        """Initialize the engine with a policy-decision provider.

        Args:
            provider: The `PolicyProvider` to delegate evaluation to.
                Defaults to a new `DefaultPolicyProvider` instance when
                omitted.
        """
        self._provider = provider if provider is not None else DefaultPolicyProvider()

    def evaluate(
        self,
        capability: Capability,
        security_assessment: CapabilitySecurityAssessment | None = None,
        lifecycle_status: CapabilityLifecycleStatus | None = None,
    ) -> PolicyDecision:
        """Compute a policy decision for one capability via the configured provider.

        Args:
            capability: The capability to evaluate. Never mutated.
            security_assessment: The capability's already-produced
                EP-069.6 assessment, if one was run. Forwarded
                unchanged; never fetched by this method.
            lifecycle_status: The capability's already-queried
                EP-069.7 lifecycle status, if it is tracked. Forwarded
                unchanged; never fetched by this method.

        Returns:
            The configured provider's `PolicyDecision`, returned
            unchanged. This is a decision only -- this method performs
            no enforcement of it.

        Raises:
            CapabilityPolicyProviderError: Propagated unchanged from
                the configured provider -- this method never swallows
                a provider exception, mirroring
                `CapabilityDiscoveryEngine.discover()`'s/
                `CapabilitySecurityEngine.assess()`'s own documented
                behavior.
        """
        return self._provider.evaluate(capability, security_assessment, lifecycle_status)
