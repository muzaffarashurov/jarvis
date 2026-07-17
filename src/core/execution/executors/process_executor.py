"""Executor that launches native/system executables as tracked processes."""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from loguru import logger

from src.core.execution.executor import Executor
from src.core.execution.models import ExecutionRequest, ExecutionResult, TargetType
from src.core.execution.process_registry import ProcessRegistry

_KNOWN_SYSTEM_COMMANDS: frozenset[str] = frozenset(
    {"notepad", "notepad.exe", "calc", "calc.exe", "python", "python.exe"}
)


class ProcessExecutor(Executor):
    """Launches executable programs and tracks them in a ProcessRegistry.

    Handles both bare system commands resolved via PATH (e.g. "notepad",
    "calc") and explicit paths to .exe files.
    """

    def __init__(self, registry: ProcessRegistry) -> None:
        """Initialize the ProcessExecutor.

        Args:
            registry: The registry used to track launched processes.
        """
        self._registry = registry

    def supports(self, raw_target: str) -> bool:
        """Return True for known system commands or explicit .exe paths.

        Args:
            raw_target: The raw target string.

        Returns:
            True if this executor should handle the target.
        """
        target = raw_target.strip().strip('"')
        if target.lower() in _KNOWN_SYSTEM_COMMANDS:
            return True
        return Path(target).suffix.lower() == ".exe"

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Launch the target as a new tracked process.

        Args:
            request: The execution request whose raw_target names a
                program to launch.

        Returns:
            An ExecutionResult with the Jarvis-assigned process ID on
            success.
        """
        target = request.raw_target.strip().strip('"')
        command = shlex.split(target, posix=False)

        try:
            handle = subprocess.Popen(command)
        except FileNotFoundError:
            logger.error(f"Target not found: {target}")
            return ExecutionResult(
                success=False, message="Target not found.", target_type=TargetType.PROCESS
            )
        except OSError as exc:
            logger.error(f"Cannot launch process '{target}': {exc}")
            return ExecutionResult(
                success=False, message="Cannot launch process.", target_type=TargetType.PROCESS
            )

        name = Path(command[0]).name
        process_id = self._registry.register(name=name, handle=handle)
        logger.info(f"Process started: {name} (id={process_id}, pid={handle.pid})")

        return ExecutionResult(
            success=True,
            message=f"Started process\nID: {process_id}",
            process_id=process_id,
            target_type=TargetType.PROCESS,
        )
