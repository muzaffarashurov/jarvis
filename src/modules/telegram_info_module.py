"""Telegram Info module: CLI command surface for EP-040.

Exposes the "telegram-info" command namespace (chat, help) as thin
CommandModule handlers, following the same pattern as GitHubModule
(EP-039). All Telegram Bot API logic lives in TelegramInfoService;
this module only parses/validates CLI arguments, calls
TelegramInfoService's existing public method unchanged, and formats
CommandResult objects for the shell -- it never imports `telegram`
itself and never reads `telegram.token`.

Catches `TelegramInfoError` (the common base of every exception a
running `get_chat()` call can raise) to format
`CommandResult(success=False, message=str(exc))`, never letting a raw
exception reach the shell, matching every other module's pattern.
`TelegramInfoServiceError` is not caught here because it can only ever
be raised during Bootstrap construction of TelegramInfoService, never
from a running CLI call -- if construction fails, Bootstrap never
registers this module at all (see src/bootstrap.py).

No "messages", "history", "chats"/list, "send", or any other
read-beyond-scope or write/mutating command exists -- this subsystem
exposes exactly one operation, matching the EP-040 design's explicit
scope. This module never imports or references EP-012's
`TelegramClient`/`TelegramService`/`TelegramModule`/`TelegramRouter`.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.telegram_info.telegram_info_error import TelegramInfoError
from src.services.telegram_info_service import TelegramInfoService

HELP_TEXT: str = (
    "Available commands\n\n"
    "telegram-info chat <chat_id>\n"
    "telegram-info help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class TelegramInfoModule:
    """Built-in "telegram-info" command namespace for EP-040."""

    def __init__(self, telegram_info_service: TelegramInfoService) -> None:
        """Initialize the TelegramInfoModule.

        Args:
            telegram_info_service: The service used to look up chat
                metadata via the Telegram Bot API.
        """
        self._service = telegram_info_service
        self._actions: dict[str, ActionHandler] = {
            "chat": self._chat,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "telegram-info"."""
        return "telegram-info"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "telegram-info" action.

        Args:
            action: The requested action (e.g. "chat").
            arguments: Additional arguments (e.g. a chat_id).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "telegram-info help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available telegram-info commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _chat(self, arguments: list[str]) -> CommandResult:
        """Handle "telegram-info chat <chat_id>"."""
        if not arguments:
            return CommandResult(success=False, message="telegram-info chat requires a chat_id.")

        raw = arguments[0]
        chat_id: int | str = raw
        if raw.lstrip("-").isdigit():
            chat_id = int(raw)

        try:
            result = self._service.get_chat(chat_id)
        except TelegramInfoError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=str(result.data))
