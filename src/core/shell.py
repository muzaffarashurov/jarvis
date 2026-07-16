"""Interactive command-line shell for Jarvis."""

from __future__ import annotations

from loguru import logger

from src.core.command_router import CommandRouter

PROMPT: str = "jarvis> "


class InteractiveShell:
    """Reads user commands and dispatches them through the CommandRouter.

    Responsibilities:
        - Display the "jarvis>" prompt and read user input.
        - Validate input before dispatching (ignore blank lines).
        - Send commands to the CommandRouter and print the response.
        - Loop until an exit command, EOF, or keyboard interrupt occurs.
        - Perform a graceful shutdown in every termination scenario.
    """

    def __init__(self, router: CommandRouter) -> None:
        """Initialize the InteractiveShell.

        Args:
            router: The CommandRouter used to dispatch user commands.
        """
        self._router = router
        self._running = False

    def run(self) -> None:
        """Run the read-execute-print loop until the shell terminates.

        Handles KeyboardInterrupt (Ctrl+C) and EOF (Ctrl+D) as graceful
        shutdown triggers rather than crashes. Application termination
        is logged exactly once, regardless of how the loop exits.
        """
        self._running = True
        logger.info("Interactive shell started.")

        try:
            while self._running:
                self._step()
        except KeyboardInterrupt:
            print("\n\nGoodbye.")
        except EOFError:
            print("\n\nGoodbye.")
        finally:
            self._running = False
            logger.info("Application terminated")

    def _step(self) -> None:
        """Read, validate, execute, and print the result of one command."""
        raw_input = input(PROMPT)

        if not raw_input.strip():
            return

        result = self._router.dispatch(raw_input)

        if result.message:
            print()
            print(result.message)
            print()

        if result.should_exit:
            self._running = False
