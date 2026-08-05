"""Tool domain model for EP-031 Tool Engine.

Defines the static catalog entry (`Tool`) describing a single,
real, invocable action Tool Engine can dispatch. This module owns no
runtime execution -- it is pure data plus a bound handler callable,
matching the pattern already used for the Plugin catalog (see
`src/core/plugins/plugin.py`) and the Process Catalog (see
`src/core/processes/process.py`).

A `Tool`'s `handler` is a zero-argument callable, pre-bound (via
closure) to whichever already-built subsystem service it wraps --
Tool Engine itself never instantiates a subsystem service, matching
this project's Dependency Policy ("never instantiate large services
inside business logic"). Binding happens once, at composition-root
time (`src/bootstrap.py`), exactly like `Plugin.entry_point` factories
and `AgentEngine.register_subsystem(name, status_check=...)` closures
already do for EP-009 and EP-028 respectively.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

__all__ = ["Tool"]


@dataclass(frozen=True)
class Tool:
    """A single catalog entry describing a real, invocable action.

    Attributes:
        id: Unique, stable identifier for the tool (e.g.
            "memory_recall"). Used as the registry key.
        name: Human-readable display name.
        description: Short description shown by `tool list`.
        subsystem: The name of the completed Engineering Package this
            tool wraps (e.g. "memory", "knowledge"), matching the
            subsystem names EP-028's Agent Framework registers and
            EP-029's `PlanStep.subsystem` values. None only for a
            tool with no associated subsystem (e.g. an
            acknowledgment-only tool).
        action: The stable action identifier this tool satisfies
            (e.g. "retrieve_from_memory"), matching EP-029's
            `PlanStep.action` values. Combined with `subsystem`, this
            is how `ToolExecutionProvider` (the EP-030 bridge) looks
            up which tool to invoke for a given `PlanStep`.
        handler: Zero-argument callable that performs the real
            subsystem action and returns its result. Must not raise
            for expected conditions -- `DefaultToolProvider` catches
            any exception and translates it into a failed
            `ToolResult`, but a handler that raises routinely instead
            of returning an error value is a poor citizen of this
            contract.
        enabled: Whether this tool currently participates in
            `tool list` / invocation. A disabled tool is not removed
            from the catalog, matching `Plugin.enabled`.
    """

    id: str
    name: str
    description: str
    subsystem: str | None
    action: str
    handler: Callable[[], object]
    enabled: bool = True
