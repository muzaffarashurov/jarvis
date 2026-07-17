"""Executor that opens URLs using the operating system's default browser."""

from __future__ import annotations

import webbrowser

from loguru import logger

from src.core.execution.executor import Executor
from src.core.execution.models import ExecutionRequest, ExecutionResult, TargetType

_URL_SCHEMES: tuple[str, ...] = ("http://", "https://")


class UrlExecutor(Executor):
    """Opens web URLs using the system's default browser."""

    def supports(self, raw_target: str) -> bool:
        """Return True if the target looks like an http(s) URL.

        Args:
            raw_target: The raw target string.

        Returns:
            True if the target starts with "http://" or "https://".
        """
        return raw_target.strip().strip('"').lower().startswith(_URL_SCHEMES)

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """Open the target URL in the default browser.

        Args:
            request: The execution request whose raw_target is a URL.

        Returns:
            An ExecutionResult indicating whether the browser opened.
        """
        target = request.raw_target.strip().strip('"')

        try:
            opened = webbrowser.open(target)
        except Exception as exc:  # noqa: BLE001 - never crash the engine
            logger.error(f"Failed to open URL '{target}': {exc}")
            return ExecutionResult(
                success=False, message="Cannot launch process.", target_type=TargetType.URL
            )

        if not opened:
            logger.error(f"No browser available to open URL '{target}'.")
            return ExecutionResult(
                success=False, message="Cannot launch process.", target_type=TargetType.URL
            )

        logger.info(f"URL opened: {target}")
        return ExecutionResult(success=True, message="URL opened.", target_type=TargetType.URL)
