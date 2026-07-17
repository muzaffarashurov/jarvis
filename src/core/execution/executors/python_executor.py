"""Executor that runs Python scripts using the current interpreter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from loguru import logger

from src.core.execution.executor import Executor
from src.core.execution.models import ExecutionRequest, ExecutionResult, TargetType
from src.core.execution.process_registry import ProcessRegistry


class PythonExecutor(Executor):
    """Executes Python scripts and tracks them as Jarvis-managed processes."""

    def __init__(self, registry: ProcessRegistry) -> None:
        """Initialize the PythonExecutor.

        Args:
            registry: The registry used to track launched script processes.
        """
        self._registry = registry

    def supports(self, raw_target: str) -> bool:
        """Return True if the target is a path to a .py file.

        Args:
            raw_target: The raw target string.

        Returns:
            True if the target's file suffix is ".py".
        """
        return Path(raw_target.strip().strip('"')).suffix.lower() == ".py"

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute the target Python script with the current interpreter.

        Args:
            request: The execution request whose raw_target is a .py path.

        Returns:
            An ExecutionResult indicating whether the script was launched.
        """
        path = Path(request.raw_target.strip().strip('"'))
        if not path.exists():
            return ExecutionResult(
                success=False, message="Target not found.", target_type=TargetType.PYTHON_SCRIPT
            )

        try:
            handle = subprocess.Popen([sys.executable, str(path)])
        except OSError as exc:
            logger.error(f"Cannot launch script '{path}': {exc}")
            return ExecutionResult(
                success=False,
                message="Cannot launch process.",
                target_type=TargetType.PYTHON_SCRIPT,
            )

        process_id = self._registry.register(name=path.name, handle=handle)
        logger.info(f"Python script started: {path.name} (id={process_id}, pid={handle.pid})")

        return ExecutionResult(
            success=True,
            message="Python script executed.",
            process_id=process_id,
            target_type=TargetType.PYTHON_SCRIPT,
        )
