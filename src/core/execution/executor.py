"""Abstract executor interface shared by all execution backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.core.execution.models import ExecutionRequest, ExecutionResult


class Executor(ABC):
    """Common interface every execution backend must implement.

    Responsibilities:
        - Decide whether a given target belongs to this executor
          (`supports`).
        - Perform the actual launch/open operation (`run`).

    New executors are added purely by implementing this interface and
    registering an instance with the ExecutionEngine; no existing code
    needs to change to support them (open/closed principle).
    """

    @abstractmethod
    def supports(self, raw_target: str) -> bool:
        """Return whether this executor can handle the given target.

        Args:
            raw_target: The raw, stripped target string supplied by the
                user (e.g. a program name, file path, or URL).

        Returns:
            True if this executor should handle the target.
        """
        raise NotImplementedError

    @abstractmethod
    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute the given request.

        Args:
            request: The normalized execution request.

        Returns:
            An ExecutionResult describing the outcome. Implementations
            must catch their own exceptions and translate them into a
            failed ExecutionResult rather than raising.
        """
        raise NotImplementedError
