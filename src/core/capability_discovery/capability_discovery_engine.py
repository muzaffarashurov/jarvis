"""Capability Discovery Engine for EP-069.5.

`CapabilityDiscoveryEngine` orchestrates one `CapabilityDiscoveryProvider`
against a `CapabilityRegistry` (EP-069.4): it fetches the registry's
current, `enabled` capabilities and hands them to its configured
provider, returning the provider's result unchanged. It performs no
matching/ranking logic of its own (that is the provider's job) and no
provider selection logic (there is no Manager in this Engineering
Package -- Owner Decision OD2, `docs/architecture/designs/
EP069_5_DESIGN.md` Section 13 -- the engine is constructed directly
with the one provider it will use).

This engine never mutates `CapabilityRegistry` or any `Capability`,
never calls `CapabilityBackend.invoke()`, and is not wired into
`src/bootstrap.py`, `config/config.yaml`, or any CLI surface (Owner
Decision OD2). Registering it with Planning Engine or Agent Framework
remains deferred to a future Engineering Package (Section 22 of the
approved design).
"""

from __future__ import annotations

from src.core.capability.capability_registry import CapabilityRegistry
from src.core.capability_discovery.capability_discovery_provider import (
    CapabilityDiscoveryProvider,
    DefaultCapabilityDiscoveryProvider,
)
from src.core.capability_discovery.capability_discovery_result import (
    CapabilityDiscoveryResult,
)

__all__ = [
    "CapabilityDiscoveryEngine",
]


class CapabilityDiscoveryEngine:
    """Provider-independent orchestration for capability discovery.

    Never selects, constructs, or reconfigures a provider on its own
    behalf beyond the one supplied (or defaulted) at construction
    time, mirroring `ToolEngine`'s own documented boundary ("Never
    selects, constructs, or configures providers itself").
    """

    def __init__(self, provider: CapabilityDiscoveryProvider | None = None) -> None:
        """Initialize the engine with a discovery provider.

        Args:
            provider: The `CapabilityDiscoveryProvider` to delegate
                matching/ranking to. Defaults to a new
                `DefaultCapabilityDiscoveryProvider` instance when
                omitted.
        """
        self._provider = provider if provider is not None else DefaultCapabilityDiscoveryProvider()

    def discover(
        self,
        task: str,
        registry: CapabilityRegistry,
        max_results: int = 10,
        cost_hints: dict[str, float] | None = None,
    ) -> CapabilityDiscoveryResult:
        """Discover and rank the capabilities in `registry` that fit `task`.

        Args:
            task: The plain-text task description to match candidates
                against.
            registry: The `CapabilityRegistry` to read candidates
                from. Never mutated -- only its existing, public
                `list()` method is called.
            max_results: Maximum number of matches the returned result
                may contain. Defaults to `10`.
            cost_hints: Optional, externally supplied per-capability
                cost signal, keyed by `Capability.id` -- forwarded to
                the configured provider unchanged.

        Returns:
            The configured provider's `CapabilityDiscoveryResult`,
            returned unchanged.

        Raises:
            CapabilityDiscoveryProviderError: Propagated unchanged from
                the configured provider -- this method never swallows
                a provider exception, mirroring `ToolEngine.invoke()`'s
                own documented behavior.
        """
        enabled_capabilities = [
            capability for capability in registry.list() if capability.enabled
        ]
        return self._provider.discover(task, enabled_capabilities, max_results, cost_hints)
