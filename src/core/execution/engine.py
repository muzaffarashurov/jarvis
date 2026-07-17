"""Execution engine: routes execution requests to the correct executor."""

from __future__ import annotations

from loguru import logger

from src.core.execution.executor import Executor
from src.core.execution.models import ExecutionRequest, ExecutionResult
from src.core.execution.process_registry import ProcessRegistry


class ExecutionEngine:
    """Chooses an executor, validates targets, and delegates execution.

    Responsibilities:
        - Own the list of registered Executors (dependency injection).
        - Choose the correct executor for a given raw target.
        - Delegate the actual launch/open operation to that executor.
        - Track processes via the shared ProcessRegistry.
        - Log every execution attempt, success, and failure.

    The engine never executes anything itself: all execution is always
    delegated to an Executor. Future executors are added purely by
    passing additional instances to the constructor; this class never
    needs to change (open/closed principle).
    """

    def __init__(self, executors: list[Executor], registry: ProcessRegistry) -> None:
        """Initialize the ExecutionEngine.

        Args:
            executors: Ordered list of executors. The first executor
                whose `supports()` returns True for a target handles it.
            registry: Shared registry of processes launched by Jarvis.
        """
        self._executors = executors
        self._registry = registry

    def run(self, raw_target: str) -> ExecutionResult:
        """Resolve and execute a raw target string.

        Args:
            raw_target: The raw target supplied by the caller (a program
                name, file path, or URL).

        Returns:
            An ExecutionResult describing the outcome.
        """
        target = raw_target.strip()
        if not target:
            return ExecutionResult(success=False, message="Target not found.")

        executor = self._select_executor(target)
        if executor is None:
            logger.info(f"Unsupported target: {target}")
            return ExecutionResult(success=False, message="Unsupported target.")

        request = ExecutionRequest(raw_target=target)
        try:
            result = executor.run(request)
        except Exception as exc:  # noqa: BLE001 - executors must never crash the engine
            logger.error(f"Execution error for '{target}': {exc}")
            return ExecutionResult(success=False, message="Cannot launch process.")

        if result.success:
            logger.info(f"Execution succeeded: {target}")
        else:
            logger.info(f"Execution failed: {target} -> {result.message}")

        return result

    def list_processes(self) -> list[tuple[int, str]]:
        """Return all Jarvis-tracked processes still running.

        Returns:
            A list of (process_id, name) tuples, ordered by process ID.
        """
        records = sorted(self._registry.list_running(), key=lambda r: r.process_id)
        return [(record.process_id, record.name) for record in records]

    def stop_process(self, process_id: int) -> ExecutionResult:
        """Terminate a Jarvis-tracked process by ID.

        Args:
            process_id: The Jarvis-assigned process ID to terminate.

        Returns:
            An ExecutionResult describing whether termination succeeded.
        """
        record = self._registry.get(process_id)
        if record is None:
            logger.info(f"Invalid process id: {process_id}")
            return ExecutionResult(success=False, message="Invalid process id.")

        try:
            record.handle.terminate()
            record.handle.wait(timeout=5)
        except Exception as exc:  # noqa: BLE001 - never crash on termination
            logger.error(f"Failed to terminate process {process_id}: {exc}")
            return ExecutionResult(success=False, message="Cannot launch process.")

        self._registry.remove(process_id)
        logger.info(f"Process terminated: id={process_id}, name={record.name}")
        return ExecutionResult(success=True, message="Process terminated.")

    def _select_executor(self, target: str) -> Executor | None:
        """Return the first executor that supports the given target.

        Args:
            target: The raw target string.

        Returns:
            The matching Executor, or None if no executor supports it.
        """
        for executor in self._executors:
            if executor.supports(target):
                return executor
        return None
