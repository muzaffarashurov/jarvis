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
from src.core.execution.engine import ExecutionEngine
from src.core.orchestrator import Orchestrator
from src.utils.constants import APP_NAME, APP_VERSION

HELP_TEXT: str = (
    "Available commands\n\n"
    "system help\n"
    "system version\n"
    "system status\n"
    "system clear\n"
    "system exit\n"
    "system run <target>\n"
    "system processes\n"
    "system stop <id>"
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

    def __init__(self, orchestrator: Orchestrator, execution_engine: ExecutionEngine) -> None:
        """Initialize the SystemModule.

        Args:
            orchestrator: The running Orchestrator, used to report status
                information such as the number of loaded skills.
            execution_engine: The engine used to run, list, and stop
                external targets (programs, scripts, files, and URLs).
        """
        self._orchestrator = orchestrator
        self._execution_engine = execution_engine
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "version": self._version,
            "status": self._status,
            "clear": self._clear,
            "exit": self._exit,
            "run": self._run,
            "processes": self._processes,
            "stop": self._stop,
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

    def _run(self, arguments: list[str]) -> CommandResult:
        """Execute a target through the ExecutionEngine.

        Args:
            arguments: The target to run, e.g. ["notepad"] or
                ['"D:\\Scripts\\hello.py"']. Multiple tokens (in the rare
                case a quoted target was split) are rejoined with spaces.

        Returns:
            A CommandResult reflecting the ExecutionEngine's outcome.
        """
        if not arguments:
            return CommandResult(success=False, message="Target not found.")

        target = " ".join(arguments).strip().strip('"').strip("'")
        result = self._execution_engine.run(target)
        return CommandResult(success=result.success, message=result.message)

    def _processes(self, arguments: list[str]) -> CommandResult:
        """List processes started by Jarvis that are still running.

        Args:
            arguments: Unused.

        Returns:
            A CommandResult listing each tracked process's ID and name.
        """
        processes = self._execution_engine.list_processes()
        if not processes:
            return CommandResult(success=True, message="Running Processes\n\n(none)")

        rows = "\n".join(f"{process_id}    {name}" for process_id, name in processes)
        message = f"Running Processes\n\n{rows}"
        return CommandResult(success=True, message=message)

    def _stop(self, arguments: list[str]) -> CommandResult:
        """Terminate a Jarvis-tracked process by ID.

        Args:
            arguments: A single-element list containing the process ID.

        Returns:
            A CommandResult reflecting the ExecutionEngine's outcome.
        """
        if not arguments:
            return CommandResult(success=False, message="Invalid process id.")

        try:
            process_id = int(arguments[0])
        except ValueError:
            return CommandResult(success=False, message="Invalid process id.")

        result = self._execution_engine.stop_process(process_id)
        return CommandResult(success=result.success, message=result.message)
