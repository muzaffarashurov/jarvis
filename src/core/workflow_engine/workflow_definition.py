"""Domain model for EP-033 Workflow Engine.

`WorkflowRequestStep` and `WorkflowDefinition` are plain, immutable
data objects -- they contain no execution logic. `WorkflowDefinition`
storage is `WorkflowDefinitionRegistry`'s concern
(workflow_definition_registry.py); interpreting and running a
definition is exclusively `WorkflowEngine`'s concern
(workflow_engine.py).

NOTE ON NAMING: this package (`src/core/workflow_engine/`) is
deliberately named and namespaced apart from the pre-existing,
completed `src/core/workflows/` package (EP-007's `Workflow`,
`WorkflowStep`, `WorkflowRegistry`) -- see
`src/core/workflow_engine/__init__.py` for the full disambiguation
note. `WorkflowRequestStep` here is unrelated to EP-007's
`WorkflowStep`: it carries a single plain-text `request` meant for
EP-029's Planning Engine (via EP-030's `PlanExecutionEngine.execute_request()`),
not a raw `(target, action)` pair meant for EP-003's `ExecutionEngine`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowRequestStep:
    """A single step within a `WorkflowDefinition`.

    Attributes:
        name: Human-readable step name (e.g. "Recall preferences").
        request: The plain-text request forwarded, unchanged, to
            `PlanExecutionEngine.execute_request()` when this step
            runs -- the same kind of request EP-029's Planning Engine
            already understands.
    """

    name: str
    request: str


@dataclass(frozen=True)
class WorkflowDefinition:
    """A named, ordered sequence of `WorkflowRequestStep`s.

    Attributes:
        id: Unique workflow definition identifier (e.g. "morning_briefing").
        name: Human-readable workflow name.
        description: Short description of what the workflow does.
        enabled: Whether the workflow may be run.
        steps: Ordered steps that make up the workflow.
    """

    id: str
    name: str
    description: str
    enabled: bool
    steps: tuple[WorkflowRequestStep, ...]
