"""Workflow domain model.

Workflow and WorkflowStep are plain, immutable data objects. They
contain no execution logic: WorkflowRegistry only stores them, and
WorkflowService is the only component that interprets and executes
them (via ExecutionEngine).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class WorkflowStep:
    """A single step within a Workflow.

    Attributes:
        name: Human-readable step name (e.g. "Invoice Automation").
        target: The step's target identifier (e.g. "Invoice Automation").
            See WorkflowService's module docstring for how (and how
            far) this is currently resolved via ExecutionEngine.
        action: The action to perform against the target (e.g. "start").
        parameters: Optional extra parameters for the step. Not yet
            consumed by WorkflowService; reserved for future steps.
    """

    name: str
    target: str
    action: str
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Workflow:
    """A named, ordered sequence of steps.

    Attributes:
        id: Unique workflow identifier (e.g. "start_work").
        name: Human-readable workflow name.
        description: Short description of what the workflow does.
        enabled: Whether the workflow may be executed.
        steps: Ordered steps that make up the workflow.
    """

    id: str
    name: str
    description: str
    enabled: bool
    steps: tuple[WorkflowStep, ...]
