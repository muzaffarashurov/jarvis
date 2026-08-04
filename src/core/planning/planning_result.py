"""Domain model for EP-029 Planning Engine.

Defines the plain data types shared by `PlanningProvider` (the actual
decomposition algorithm), `PlanningEngine` (pipeline orchestration,
including optional EP-028 Agent Framework subsystem-availability
enrichment) and `PlanningService` (the CLI-facing layer): a single
ordered step of a plan (`PlanStep`) and the outcome of planning a
whole request (`Plan`). This module owns no decomposition logic and no
subsystem lookup -- it mirrors the role of
`src/core/context_compression/compression_result.py` relative to
`CompressionProvider`/`CompressionEngine`, and
`src/core/agent/agent_result.py` relative to `AgentProvider`/
`AgentEngine`.

Planning Engine performs no AI reasoning and no task execution. This
module has no dependency on any LLM, AI provider, prompt, reflection,
or tool-execution component.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "PlanStep",
    "Plan",
]


@dataclass(frozen=True)
class PlanStep:
    """A single, ordered step of a `Plan`.

    Built by a `PlanningProvider` from the request text alone (with
    `available` always True at that point -- a provider is subsystem-
    agnostic and never queries a live registry itself), then optionally
    refined by `PlanningEngine` using EP-028's `AgentEngine.list_subsystems()`
    (public API only) to reflect whether the referenced subsystem is
    actually registered and reports itself enabled.

    Attributes:
        order: The step's 1-based position in the plan. Always
            reflects final ordering after any truncation.
        subsystem: The name of the completed Engineering Package this
            step would be carried out by (e.g. "knowledge", "semantic",
            "compression"), matching the subsystem names EP-028's
            Agent Framework registers. None only for the fallback
            "acknowledge_request" step produced when no subsystem
            keyword matched the request text.
        action: A short, stable action identifier for this step (e.g.
            "semantic_search", "compress_context"). Never a natural-
            language sentence -- see `description` for that.
        description: A human-readable explanation of what this step
            would do, suitable for CLI display.
        available: Whether the referenced subsystem is currently
            known to be available. True when `subsystem` is None (the
            fallback step needs no subsystem), or when no live
            `AgentEngine` was supplied to `PlanningEngine` (unknown,
            assumed available), or reflects that subsystem's own
            reported availability when a live `AgentEngine` was
            supplied and the subsystem is registered with it. False
            when a live `AgentEngine` was supplied but the subsystem
            is not registered with it, or is registered but reports
            itself unavailable.
    """

    order: int
    subsystem: str | None
    action: str
    description: str
    available: bool


@dataclass(frozen=True)
class Plan:
    """The outcome of a single `PlanningEngine.plan()` call.

    A plan never executes anything -- it is a proposed, ordered
    sequence of steps referencing subsystems by name only. Turning a
    `Plan` into actual work is explicitly out of scope for this
    Engineering Package (see `src/core/planning/__init__.py`) and is
    left to a future Execution Engine.

    Attributes:
        request: The original request text this plan was built for,
            unchanged.
        steps: The plan's steps, in execution order (a 1-based,
            contiguous `order` sequence). Never empty -- a request that
            matches no subsystem keyword still yields a single
            fallback step.
        step_count: Number of steps in `steps`.
        truncated: Whether one or more steps were dropped to satisfy
            the configured maximum step count.
    """

    request: str
    steps: list[PlanStep] = field(default_factory=list)
    step_count: int = 0
    truncated: bool = False

    def summary(self) -> str:
        """Return a human-readable, multi-line summary of every step.

        Returns:
            One line per step, formatted as
            "<order>. [<subsystem or 'none'>] <action> - <description>
            (available|unavailable)", in order. Empty string if there
            are no steps (never the case for a `Plan` produced by
            `PlanningEngine`).
        """
        lines = []
        for step in self.steps:
            subsystem_label = step.subsystem if step.subsystem is not None else "none"
            availability_label = "available" if step.available else "unavailable"
            lines.append(
                f"{step.order}. [{subsystem_label}] {step.action} - "
                f"{step.description} ({availability_label})"
            )
        return "\n".join(lines)
