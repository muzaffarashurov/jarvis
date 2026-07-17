"""Executor that opens files and folders with the OS default application."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from loguru import logger

from src.core.execution.executor import Executor
from src.core.execution.models import ExecutionRequest, ExecutionResult, TargetType

_NON_FILE_SUFFIXES: frozenset[str] = frozenset({".exe", ".py"})


class FileExecutor(Executor):
    """Opens folders, documents, and images with the OS default handler.

    This is the catch-all executor for filesystem paths that are not
    themselves executables (.exe) or Python scripts (.py); those are
    instead handled by ProcessExecutor / PythonExecutor.
    """

    def supports(self, raw_target: str) -> bool:
        """Return True if the target is an existing path not handled by a
        more specific executor.

        Args:
            raw_target: The raw target string.

        Returns:
            True if the path exists and is not a .exe or .py file.
        """
        path = Path(raw_target.strip().strip('"'))
        if not path.exists():
            return False
        return path.suffix.lower() not in _NON_FILE_SUFFIXES

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Open the target with the operating system's default application.

        Args:
            request: The execution request whose raw_target is a path to
                a folder, document, or image.

        Returns:
            An ExecutionResult describing whether the target was opened.
        """
        path = Path(request.raw_target.strip().strip('"'))
        if not path.exists():
            return ExecutionResult(
                success=False, message="Target not found.", target_type=TargetType.FILE
            )

        try:
            self._open_with_default_application(path)
        except Exception as exc:  # noqa: BLE001 - never crash the engine
            logger.error(f"Failed to open '{path}': {exc}")
            return ExecutionResult(
                success=False, message="Cannot launch process.", target_type=TargetType.FILE
            )

        logger.info(f"File opened: {path}")
        return ExecutionResult(success=True, message="File opened.", target_type=TargetType.FILE)

    @staticmethod
    def _open_with_default_application(path: Path) -> None:
        """Open `path` with the current OS's default application.

        Args:
            path: The filesystem path to open.

        Raises:
            OSError: If the underlying OS call fails.
        """
        system = platform.system()
        if system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
