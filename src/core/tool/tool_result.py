"""Domain model for EP-031 Tool Engine.

Defines the plain data types shared by `ToolProvider` (the actual
invocation strategy), `ToolEngine` (pipeline orchestration) and
`ToolService` (the CLI-facing layer): the outcome of a single tool
invocation (`ToolStatus`, `ToolResult`). This module owns no
invocation logic itself -- it mirrors the role of
`src/core/plan_execution/plan_execution_result.py` relative to
`PlanExecutionProvider`/`PlanExecutionEngine`.

Tool Engine performs no AI reasoning, no planning, and no plan
walking. This module has no dependency on any LLM, AI provider,
prompt, or planning component.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "ToolStatus",
    "ToolResult",
]


class ToolStatus(str, Enum):
    """The outcome of invoking a single `Tool`.

    Attributes:
        COMPLETED: The tool's handler was called and returned
            normally -- a real subsystem action was actually
            performed (unlike EP-030's `StepStatus.COMPLETED`, which
            only means "successfully dispatched").
        FAILED: The tool's handler raised an exception, or no tool
            was registered for the requested id/action.
    """

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ToolResult:
    """The outcome of a single `ToolEngine.invoke()` (or `invoke_for_step()`) call.

    Attributes:
        tool_id: The id of the `Tool` that was invoked, or the
            requested id/action pair if no matching tool was found.
        status: The invocation's outcome.
        message: Human-readable explanation of the outcome.
        data: The tool handler's return value, forwarded unchanged.
            None on failure, or when the handler itself returns None.
    """

    tool_id: str
    status: ToolStatus
    message: str
    data: object | None = None
