"""ApiRouter: bridges REST API requests to the existing CommandRouter.

Mirrors ``src/core/telegram/telegram_router.py``'s role for Telegram:
performs no business logic and no command parsing of its own. Every
(module, action, arguments) triple is reassembled into a raw command
line and handed to ``CommandRouter.dispatch()`` -- the exact same
entry point ``InteractiveShell`` (``src/core/shell.py``) and
``TelegramRouter`` already dispatch through -- so the REST API can
never diverge in behaviour from the CLI, and no command logic is ever
duplicated for HTTP (see EP043_STEP1_REPORT.md, section 5/14 and
EP043_STEP2_REPORT.md, "Architecture").
"""

from __future__ import annotations

import shlex

from src.core.command_router import CommandResult, CommandRouter

__all__ = ["ApiRouter"]


class ApiRouter:
    """Routes REST API command requests to the existing CommandRouter.

    Responsibilities:
        - Reassemble a (module, action, arguments) triple into the
          same raw command-line syntax the interactive shell accepts.
        - Hand it to ``CommandRouter.dispatch()`` unchanged.

    Never executes business logic itself and never duplicates
    ``CommandRouter``'s parsing/dispatch logic.
    """

    def __init__(self, command_router: CommandRouter) -> None:
        """Initialize the ApiRouter.

        Args:
            command_router: The existing, shared CommandRouter every
                other interface (the interactive shell, Telegram)
                also dispatches through.
        """
        self._command_router = command_router

    @property
    def command_router_available(self) -> bool:
        """Return whether this router holds a CommandRouter dependency."""
        return self._command_router is not None

    def dispatch_command(self, module: str, action: str, arguments: list[str]) -> CommandResult:
        """Dispatch one REST API command request to the CommandRouter.

        Args:
            module: The target command namespace (e.g. "system").
            action: The action within that namespace. May be empty.
            arguments: Additional positional arguments, in order. Each
                is shell-quoted before being rejoined, so arguments
                containing spaces or special characters round-trip
                safely through ``CommandRouter.dispatch()``'s
                ``shlex.split()`` parsing.

        Returns:
            The CommandResult from ``CommandRouter.dispatch()``.
        """
        tokens = [module]
        if action:
            tokens.append(action)
        tokens.extend(arguments)
        raw_command = " ".join(shlex.quote(token) for token in tokens)
        return self._command_router.dispatch(raw_command)
