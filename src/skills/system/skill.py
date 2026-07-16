"""System module: built-in Jarvis shell commands.

Provides the "system" command namespace (help, version, status, clear,
exit). This module also serves as the reference implementation of the
CommandModule interface that future modules (invoice, telegram, excel,
presentation, browser, voice, github, ...) must follow.
"""

from __future__ import annotations

import os
import platform
from typing import Callable

from loguru import logger

from src.core.command_router import CommandResult
from src.core.orchestrator import Orchestrator
from src.utils.constants import APP_NAME, APP_VERSION

HELP_TEXT: str = (
    "Available commands\n\n"
    "system help\n"
    "system version\n"
    "system status\n"
    "system clear\n"
    "system exit"
)

ActionHandler = Callable[[list[str]], CommandResult]


class SystemModule:
    """Built-in "system" command namespace.

    Responsibilities:
        - Report available commands (help).
        - Report application version (version).
        - Report runtime status (status).
        - Clear the terminal screen (clear).
        - Request graceful shell termination (exit).
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        """Initialize the SystemModule.

        Args:
            orchestrator: The running Orchestrator, used to report status
                information such as the number of loaded skills.
        """
        self._orchestrator = orchestrator
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "version": self._version,
            "status": self._status,
            "clear": self._clear,
            "exit": self._exit,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace.

        Returns:
            The literal string "system".
        """
        return "system"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "system" action.

        Args:
            action: The requested action (e.g. "status"). May be empty
                if the user entered only "system".
            arguments: Additional arguments; unused by current actions.

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            logger.info(f"Unknown command: {command}")
            message = (
                f"Unknown command: {command}\n"
                'Type "system help" for available commands.'
            )
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available system commands.

        Args:
            arguments: Unused.

        Returns:
            A CommandResult containing the help text.
        """
        return CommandResult(success=True, message=HELP_TEXT)

    def _version(self, arguments: list[str]) -> CommandResult:
        """Return the application name and version.

        Args:
            arguments: Unused.

        Returns:
            A CommandResult containing version information.
        """
        message = f"{APP_NAME}\n\nVersion: {APP_VERSION}"
        return CommandResult(success=True, message=message)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Return the current system status.

        Args:
            arguments: Unused.

        Returns:
            A CommandResult containing configuration, logger, core and
            skill status.
        """
        skill_count = len(self._orchestrator.skills)
        core_state = "Running" if self._orchestrator.is_running else "Stopped"
        message = (
            "System Status\n\n"
            "Configuration : OK\n\n"
            "Logger : OK\n\n"
            f"Core : {core_state}\n\n"
            f"Skills : {skill_count} Loaded"
        )
        return CommandResult(success=True, message=message)

    def _clear(self, arguments: list[str]) -> CommandResult:
        """Clear the terminal screen on both Windows and Linux/macOS.

        Args:
            arguments: Unused.

        Returns:
            A CommandResult with no message, since the screen clear is
            performed directly as a side effect.
        """
        os.system("cls" if platform.system() == "Windows" else "clear")
        return CommandResult(success=True, message="")

    def _exit(self, arguments: list[str]) -> CommandResult:
        """Request graceful termination of the interactive shell.

        Args:
            arguments: Unused.

        Returns:
            A CommandResult signaling the shell to stop after printing
            a farewell message.
        """
        return CommandResult(success=True, message="Goodbye.", should_exit=True)
