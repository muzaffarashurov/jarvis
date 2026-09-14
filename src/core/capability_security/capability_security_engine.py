"""Capability Security Engine for EP-069.6 (advisory assessment slice).

`CapabilitySecurityEngine` is thin, provider-independent orchestration:
it delegates directly to its configured `CapabilitySecurityProvider`
and returns the result unchanged. It performs no assessment logic of
its own (that is the provider's job) and no provider selection logic
(there is no Manager in this Engineering Package -- Owner Decision
OD4, `docs/architecture/designs/EP069_6_DESIGN.md` -- the engine is
constructed directly with the one provider it will use).

This engine never queries or mutates a `CapabilityRegistry`, never
mutates a `Capability`, never calls `CapabilityBackend.invoke()`, and
is not wired into `src/bootstrap.py`, `config/config.yaml`, or any CLI
surface (Owner Decision OD4). Integrating this engine with a future
EP-070 policy gate remains deferred to a future Engineering Package.
"""

from __future__ import annotations

from src.core.capability.capability import Capability
from src.core.capability_security.capability_security_provider import (
    CapabilitySecurityProvider,
    DefaultCapabilitySecurityProvider,
)
from src.core.capability_security.capability_security_result import (
    CapabilitySecurityAssessment,
)

__all__ = [
    "CapabilitySecurityEngine",
]


class CapabilitySecurityEngine:
    """Provider-independent orchestration for capability security assessment.

    Never selects, constructs, or reconfigures a provider on its own
    behalf beyond the one supplied (or defaulted) at construction
    time, mirroring `CapabilityDiscoveryEngine`'s own documented
    boundary.
    """

    def __init__(self, provider: CapabilitySecurityProvider | None = None) -> None:
        """Initialize the engine with a security-assessment provider.

        Args:
            provider: The `CapabilitySecurityProvider` to delegate
                assessment to. Defaults to a new
                `DefaultCapabilitySecurityProvider` instance when
                omitted.
        """
        self._provider = provider if provider is not None else DefaultCapabilitySecurityProvider()

    def assess(self, capability: Capability) -> CapabilitySecurityAssessment:
        """Assess one `Capability` via the configured provider.

        Args:
            capability: The capability to assess. Never mutated.
                Callers wanting to assess every registered capability
                iterate a `CapabilityRegistry.list()` themselves and
                call this method per entry -- this engine does not
                query or mutate a registry itself.

        Returns:
            The configured provider's `CapabilitySecurityAssessment`,
            returned unchanged.

        Raises:
            CapabilitySecurityProviderError: Propagated unchanged from
                the configured provider -- this method never swallows
                a provider exception, mirroring
                `CapabilityDiscoveryEngine.discover()`'s own documented
                behavior.
        """
        return self._provider.assess(capability)
