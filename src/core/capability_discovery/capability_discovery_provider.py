"""Capability Discovery Provider framework for EP-069.5.

Defines the structural contract every capability-matching/ranking
strategy implements (`CapabilityDiscoveryProvider`), this package's
own exception hierarchy, and the one concrete, deterministic, built-in
strategy (`DefaultCapabilityDiscoveryProvider`) -- directly mirroring
the Provider framework pattern already established by every other
Core Level-1 subsystem in this repository (`src/core/planning/
planning_provider.py`'s `PlanningProvider`/`DefaultPlanningProvider`,
`src/core/tool/tool_provider.py`'s `ToolProvider`/
`DefaultToolProvider`, `src/core/context_compression/
compression_provider.py`'s `CompressionProvider`/
`DefaultCompressionProvider`).

`DefaultCapabilityDiscoveryProvider` performs no AI/LLM reasoning and
no semantic/embedding-based matching -- deterministic, case-
insensitive substring/token matching only, per
`docs/architecture/designs/EP069_5_DESIGN.md` Owner Decision OD4. A
semantic-matching provider is a natural, later, alternate
implementation of this same contract, not built here.

No provider defined in this module ever mutates a `Capability` or a
`CapabilityRegistry` (EP-069.4, `src/core/capability/`) -- every
provider here is a pure, read-only ranking function.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from src.core.capability.capability import Capability, CapabilityTrustLevel
from src.core.capability_discovery.capability_discovery_result import (
    CapabilityDiscoveryResult,
    CapabilityMatch,
)

__all__ = [
    "CapabilityDiscoveryError",
    "CapabilityDiscoveryProviderError",
    "CapabilityDiscoveryProvider",
    "DefaultCapabilityDiscoveryProvider",
]

_TOKEN_PATTERN = re.compile(r"\w+")

# Higher value ranks first. TRUSTED_INTERNAL > TRUSTED_CONFIGURED >
# UNVERIFIED, per `EP069_5_DESIGN.md` Section 9's documented sort
# order and Owner Decision OD6 (UNVERIFIED included, ranked lowest).
_TRUST_RANK: dict[CapabilityTrustLevel, int] = {
    CapabilityTrustLevel.TRUSTED_INTERNAL: 2,
    CapabilityTrustLevel.TRUSTED_CONFIGURED: 1,
    CapabilityTrustLevel.UNVERIFIED: 0,
}


class CapabilityDiscoveryError(Exception):
    """Common root for every exception raised by the Capability Discovery package (EP-069.5).

    Downstream packages can catch this single type to handle "anything
    capability-discovery-related" without needing to know about every
    specific failure mode, mirroring `CapabilityError`'s identical
    role in `src/core/capability/capability.py` (EP-069.4).
    """


class CapabilityDiscoveryProviderError(CapabilityDiscoveryError):
    """Raised when a `CapabilityDiscoveryProvider` is called with invalid input.

    Covers a non-positive `max_results` and a `cost_hints` key that
    does not correspond to any candidate's id -- both caller errors,
    surfaced loudly rather than silently ignored or auto-corrected.
    """


class CapabilityDiscoveryProvider(ABC):
    """Structural contract every capability discovery/ranking strategy implements.

    A provider matches and ranks an already-fetched list of candidate
    capabilities against one task description -- it never queries a
    live `CapabilityRegistry` itself (`CapabilityDiscoveryEngine` fetches
    and filters the registry, then hands the resulting list in),
    mirroring `PlanningProvider.plan()`'s own identical "never queries
    a live registry itself" convention. This keeps every provider
    trivially unit-testable with plain lists, with no registry
    construction required.

    A provider never executes a capability, never mutates a
    `Capability` or the `capabilities` list it is given, and never
    performs network I/O or AI/LLM inference.
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return this provider's stable, human-readable name.

        Must be cheap and side-effect free -- no network or expensive
        work.
        """
        raise NotImplementedError

    @abstractmethod
    def discover(
        self,
        task: str,
        capabilities: list[Capability],
        max_results: int,
        cost_hints: dict[str, float] | None = None,
    ) -> CapabilityDiscoveryResult:
        """Match and rank `capabilities` against `task`.

        Args:
            task: The plain-text task description to match candidates
                against. Never coupled to Planning Engine's `PlanStep`
                or any Agent Framework type (Owner Decision OD5).
            capabilities: The already-fetched, already-`enabled`-
                filtered candidate capabilities to consider. A
                provider never queries a `CapabilityRegistry` itself.
            max_results: Maximum number of matches the returned result
                may contain.

            cost_hints: Optional, externally supplied per-capability
                cost signal, keyed by `Capability.id` (Owner Decision
                OD3) -- used as an additional ranking/tie-break input.
                A capability with no entry is treated as cost `0.0`
                (cost-neutral). `Capability` itself carries no cost
                field; this parameter is the sole cost-ranking input.

        Returns:
            The resulting `CapabilityDiscoveryResult`, sorted best
            match first.

        Raises:
            CapabilityDiscoveryProviderError: If `max_results` is not
                a positive integer, or if `cost_hints` contains a key
                that does not match any entry in `capabilities`.
        """
        raise NotImplementedError

    # ---------- Lifecycle / diagnostics extension point ----------

    def is_available(self) -> bool:
        """Return whether this provider is currently able to perform discovery.

        Base implementation always returns True. Providers with an
        enabled/configured distinction should override this method.
        """
        return True


class DefaultCapabilityDiscoveryProvider(CapabilityDiscoveryProvider):
    """Deterministic, non-AI capability discovery/ranking strategy.

    Fit is scored by case-insensitive, token-oriented substring
    matching against each candidate's `name` and `description`; the
    stronger of the two per-field scores is the candidate's
    `fit_score`. A candidate with a `fit_score` of `0.0` against both
    fields is excluded from the result entirely -- unlike
    `DefaultPlanningProvider`, which always emits a fallback step,
    there is no meaningful "fallback capability" concept here, so an
    empty `matches` list is a normal, valid outcome (`EP069_5_DESIGN.md`
    Section 9).

    Surviving candidates are sorted by, in order: `fit_score`
    (descending), `trust_level` (descending --
    `TRUSTED_INTERNAL` > `TRUSTED_CONFIGURED` > `UNVERIFIED`, per
    Owner Decision OD6), `cost_hints` value (ascending, `0.0` when not
    supplied), then `id` (ascending) as the final, deterministic
    tie-break. No random or AI-influenced ordering.
    """

    def provider_name(self) -> str:
        return "default"

    def discover(
        self,
        task: str,
        capabilities: list[Capability],
        max_results: int,
        cost_hints: dict[str, float] | None = None,
    ) -> CapabilityDiscoveryResult:
        if max_results <= 0:
            raise CapabilityDiscoveryProviderError(
                "'max_results' must be a positive integer."
            )

        candidate_ids = {capability.id for capability in capabilities}
        if cost_hints:
            unknown_keys = set(cost_hints) - candidate_ids
            if unknown_keys:
                raise CapabilityDiscoveryProviderError(
                    "'cost_hints' contains a key that does not match any "
                    f"candidate capability id: {sorted(unknown_keys)}."
                )

        scored: list[tuple[Capability, float]] = []
        for capability in capabilities:
            fit_score = self._fit_score(task, capability)
            if fit_score > 0.0:
                scored.append((capability, fit_score))

        def sort_key(entry: tuple[Capability, float]) -> tuple[float, int, float, str]:
            capability, fit_score = entry
            trust_rank = _TRUST_RANK[capability.trust_level]
            cost = cost_hints.get(capability.id, 0.0) if cost_hints else 0.0
            return (-fit_score, -trust_rank, cost, capability.id)

        scored.sort(key=sort_key)

        truncated = len(scored) > max_results
        limited = scored[:max_results]

        matches = [
            CapabilityMatch(capability=capability, fit_score=fit_score, rank=rank)
            for rank, (capability, fit_score) in enumerate(limited, start=1)
        ]

        return CapabilityDiscoveryResult(
            task=task,
            matches=matches,
            match_count=len(matches),
            truncated=truncated,
        )

    @staticmethod
    def _fit_score(task: str, capability: Capability) -> float:
        """Score how strongly `task` matches one candidate's `name`/`description`.

        For each of `name` and `description`, computes the fraction of
        `task`'s distinct, lowercased word tokens that appear as a
        substring somewhere in that field's lowercased text, then
        returns the stronger (higher) of the two field scores.
        Deterministic and side-effect free; performs no AI/LLM call
        and no external lookup.

        Returns:
            A float in `[0.0, 1.0]`. `0.0` when `task` has no word
            tokens, or when no token appears in either field.
        """
        task_tokens = set(_TOKEN_PATTERN.findall(task.lower()))
        if not task_tokens:
            return 0.0

        def field_score(text: str) -> float:
            haystack = text.lower()
            hits = sum(1 for token in task_tokens if token in haystack)
            return hits / len(task_tokens)

        return max(field_score(capability.name), field_score(capability.description))
