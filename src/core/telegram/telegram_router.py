"""Telegram router: bridges Telegram messages to the existing CommandRouter.

TelegramRouter performs no business logic and no command parsing of
its own: every authorized message's raw text is handed unchanged to
CommandRouter.dispatch(), exactly the same entry point the interactive
shell already uses (see src/core/shell.py). Its only own responsibility
is EP-012's security requirement -- reject messages from chat ids
outside 'telegram.allowed_chat_ids'.
"""

from __future__ import annotations

from loguru import logger

from src.core.command_router import CommandResult, CommandRouter

__all__ = ["TelegramRouter"]


class TelegramRouter:
    """Routes incoming Telegram messages to the existing CommandRouter.

    Responsibilities:
        - Reject messages from chat ids outside the configured
          allow-list ('telegram.allowed_chat_ids').
        - Hand authorized message text to CommandRouter.dispatch()
          unchanged.

    Never executes business logic itself and never duplicates
    CommandRouter's parsing/dispatch logic.
    """

    def __init__(self, command_router: CommandRouter, allowed_chat_ids: list[int]) -> None:
        """Initialize the TelegramRouter.

        Args:
            command_router: The existing, shared CommandRouter every
                other interface (the interactive shell) also dispatches
                through.
            allowed_chat_ids: Telegram chat ids permitted to issue
                commands.
        """
        self._command_router = command_router
        self._allowed_chat_ids = set(allowed_chat_ids)

    @property
    def command_router_available(self) -> bool:
        """Return whether this router holds a CommandRouter dependency."""
        return self._command_router is not None

    def is_authorized(self, chat_id: int) -> bool:
        """Return whether `chat_id` is permitted to issue commands.

        Args:
            chat_id: The Telegram chat id to check.

        Returns:
            True if `chat_id` is in 'telegram.allowed_chat_ids'.
        """
        return chat_id in self._allowed_chat_ids

    def route(self, chat_id: int, text: str) -> CommandResult:
        """Route one incoming Telegram message to the CommandRouter.

        Args:
            chat_id: The originating chat's Telegram id.
            text: The raw message text (e.g. "scheduler status").

        Returns:
            The CommandResult from CommandRouter.dispatch(), or an
            unauthorized failure result if `chat_id` is not allowed.
        """
        if not self.is_authorized(chat_id):
            logger.warning(f"Telegram authentication failure: unauthorized chat_id={chat_id}")
            return CommandResult(success=False, message="Unauthorized.")

        logger.info(f"Telegram incoming command: chat_id={chat_id}")
        result = self._command_router.dispatch(text)
        logger.info(f"Telegram outgoing message: chat_id={chat_id}")
        return result
