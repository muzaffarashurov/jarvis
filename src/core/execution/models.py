"""Data models shared across the execution engine and its executors."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TargetType(Enum):
    """Categories of targets the ExecutionEngine can dispatch to executors."""

    PROCESS = auto()
    PYTHON_SCRIPT = auto()
    FILE = auto()
    URL = auto()


@dataclass(frozen=True)
class ExecutionRequest:
    """A normalized request to execute a single target.

    Attributes:
        raw_target: The original target string supplied by the caller,
            already stripped of surrounding whitespace (e.g. "notepad",
            "https://openai.com", "D:\\Scripts\\hello.py").
    """

    raw_target: str


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of executing a single ExecutionRequest.

    Attributes:
        success: Whether the target was launched or opened successfully.
        message: Human-readable outcome description shown to the user.
        process_id: Jarvis-assigned tracking ID, if a process was started.
        target_type: The TargetType the engine resolved the target to.
    """

    success: bool
    message: str
    process_id: int | None = None
    target_type: TargetType | None = None
