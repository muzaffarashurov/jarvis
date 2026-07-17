"""
Jarvis Interactive Shell

Core API v1.0

This class is intentionally lightweight.

Responsibilities:
- Read user input
- Delegate commands to CommandRouter
- Display CommandResult
- Handle graceful shutdown

Business logic MUST NOT be implemented here.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from src.core.command_router import CommandRouter, CommandResult


class InteractiveShell:
    """Interactive command-line shell."""

    PROMPT = "jarvis> "

    def __init__(self, router: CommandRouter) -> None:
        self._router = router

    def run(self) -> None:
        """Main shell loop."""

        logger.info("Interactive shell started.")

        while True:
            try:
                raw = input(self.PROMPT)

                result = self._router.dispatch(raw)

                self._display_result(result)

                if result.should_exit:
                    logger.info("Interactive shell stopped.")
                    break

            except KeyboardInterrupt:
                print("\nUse 'system exit' to quit.")
                continue

            except EOFError:
                print("\nGoodbye.")
                break

    @staticmethod
    def _display_result(result: Optional[CommandResult]) -> None:
        """Display command execution result."""

        if result is None:
            return

        if result.message:
            print(result.message)