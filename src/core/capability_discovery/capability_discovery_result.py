"""Domain model for EP-069.5 Capability Discovery Engine.

Defines the plain data types shared by `CapabilityDiscoveryProvider`
(the actual fit/trust/cost ranking algorithm) and
`CapabilityDiscoveryEngine` (pipeline orchestration: fetching and
filtering a `CapabilityRegistry`'s entries before ranking): a single
ranked candidate (`CapabilityMatch`) and the outcome of discovering
capabilities for a whole task (`CapabilityDiscoveryResult`). This
module owns no matching/ranking logic and no registry access -- it
mirrors the role of `src/core/planning/planning_result.py` relative to
`PlanningProvider`/`PlanningEngine`, and
`src/core/context_compression/compression_result.py` relative to
`CompressionProvider`/`CompressionEngine`.

Capability Discovery performs no capability execution, no registry
mutation, and no AI/LLM reasoning. This module has no dependency on
any LLM, AI provider, or capability-invocation component.

See `docs/architecture/designs/EP069_5_DESIGN.md` for the full
architecture and Owner Decisions (OD1-OD6) this package implements.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.capability.capability import Capability

__all__ = [
    "CapabilityMatch",
    "CapabilityDiscoveryResult",
]


@dataclass(frozen=True)
class CapabilityMatch:
    """A single ranked candidate returned by a `CapabilityDiscoveryProvider`.

    Attributes:
        capability: The matched `Capability`, unchanged and unmutated
            (EP-069.4, `src/core/capability/capability.py`).
        fit_score: How strongly `capability`'s `name`/`description`
            matched the task text, in the inclusive range `[0.0,
            1.0]`. Computed by the active provider; see
            `DefaultCapabilityDiscoveryProvider` for the default,
            deterministic scoring algorithm.
        rank: This match's 1-based position within the containing
            `CapabilityDiscoveryResult.matches`, after sorting and any
            `max_results` truncation. Always reflects final ordering.
    """

    capability: Capability
    fit_score: float
    rank: int


@dataclass(frozen=True)
class CapabilityDiscoveryResult:
    """The outcome of a single `CapabilityDiscoveryEngine.discover()` call.

    A result never executes anything -- it is a read-only, ranked list
    of candidates. Invoking one of them is explicitly out of scope for
    this Engineering Package (see `src/core/capability_discovery/
    __init__.py`) and is left to a future `CapabilityBackend`
    implementation and its caller.

    Attributes:
        task: The original task text this discovery was performed
            for, unchanged.
        matches: The discovered candidates, best fit first (per
            `DefaultCapabilityDiscoveryProvider`'s documented sort
            order), each with a contiguous, 1-based `rank`. May be
            empty -- a task that matches no registered, enabled
            capability yields an empty list, which is a normal, valid
            outcome, not an error.
        match_count: Number of entries in `matches`.
        truncated: Whether one or more otherwise-matching candidates
            were dropped to satisfy the configured `max_results`.
    """

    task: str
    matches: list[CapabilityMatch] = field(default_factory=list)
    match_count: int = 0
    truncated: bool = False
