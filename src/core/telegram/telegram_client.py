"""Telegram client: thin wrapper around python-telegram-bot's `telegram.Bot`.

TelegramClient contains no business logic. It only:

    - connects to the Telegram Bot API (via the existing
      `python-telegram-bot` dependency already declared in
      requirements.txt -- never a hand-rolled HTTP client),
    - polls for incoming updates,
    - sends outgoing messages,
    - reconnects automatically on transient failures,
    - logs connection/disconnection/reconnect/error events.

It knows nothing about Command Router, CLI commands, or any Jarvis
business logic -- see TelegramRouter and TelegramService for those
responsibilities. `telegram.Bot`'s methods are coroutines (as of
python-telegram-bot 20+); this class owns a single private asyncio
event loop and exposes a plain synchronous interface over it, guarded
by a lock so it can be safely driven from more than one thread (the
background polling loop and the CLI's `telegram send`).
"""

from __future__ import annotations

import asyncio
import threading

from loguru import logger
from telegram import Bot, Update
from telegram.error import TelegramError

__all__ = ["TelegramClient", "TelegramClientError", "TelegramMessage"]


class TelegramClientError(Exception):
    """Raised when a Telegram Bot API operation fails.

    Covers EP-012's documented error cases: invalid token, connection
    timeout, and general Telegram-unavailable conditions surfaced by
    `python-telegram-bot`'s own `TelegramError` hierarchy.
    """


class TelegramMessage:
    """A single incoming Telegram text message, reduced to what routing needs.

    Attributes:
        chat_id: The originating chat's Telegram id.
        text: The message's text content.
        update_id: The Telegram update id this message was extracted
            from (used internally to advance polling).
    """

    __slots__ = ("chat_id", "text", "update_id")

    def __init__(self, chat_id: int, text: str, update_id: int) -> None:
        """Initialize a TelegramMessage.

        Args:
            chat_id: The originating chat's Telegram id.
            text: The message's text content.
            update_id: The Telegram update id this message came from.
        """
        self.chat_id = chat_id
        self.text = text
        self.update_id = update_id


class TelegramClient:
    """Thin synchronous wrapper around `telegram.Bot` (python-telegram-bot).

    Responsibilities (per EP-012's task brief):
        - connect to the Telegram Bot API and verify the token
        - receive updates (polling)
        - send messages
        - reconnect automatically on transient failures
        - log connection lifecycle events and errors

    Never logs the bot token. Never implements its own Bot API HTTP
    client -- every Telegram operation is delegated to `telegram.Bot`.
    """

    def __init__(self, token: str) -> None:
        """Initialize the TelegramClient.

        Args:
            token: The Telegram bot token used to authenticate with
                the Bot API.
        """
        self._token = token
        self._bot: Bot | None = None
        self._loop = asyncio.new_event_loop()
        self._loop_lock = threading.Lock()
        self._update_offset: int | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Return whether the client currently holds a live connection."""
        return self._connected

    def connect(self) -> None:
        """Create the underlying Bot and verify the token via `get_me()`.

        Raises:
            TelegramClientError: If the token is invalid or the
                Telegram Bot API cannot be reached.
        """
        try:
            bot = Bot(token=self._token)
            self._run(bot.initialize())
            self._run(bot.get_me())
        except TelegramError as exc:
            self._connected = False
            logger.error(f"Telegram connection failed: {exc}")
            raise TelegramClientError("Invalid token or connection failed.") from exc

        self._bot = bot
        self._connected = True
        logger.info("Telegram connected.")

    def disconnect(self) -> None:
        """Close the underlying Bot connection, if any."""
        if self._bot is not None:
            try:
                self._run(self._bot.shutdown())
            except TelegramError as exc:
                logger.error(f"Telegram disconnect error: {exc}")
        self._bot = None
        self._connected = False
        logger.info("Telegram disconnected.")

    def fetch_updates(self, timeout: int = 0) -> list[TelegramMessage]:
        """Poll for new updates via `Bot.get_updates()`.

        Automatically attempts one reconnect if polling fails.

        Args:
            timeout: Long-poll timeout (seconds) passed to
                `Bot.get_updates()`.

        Returns:
            The text messages contained in any new updates, in order.
            Empty if there are none or if reconnection was required.
        """
        if self._bot is None:
            raise TelegramClientError("Telegram client is not connected.")

        try:
            updates: tuple[Update, ...] = self._run(
                self._bot.get_updates(offset=self._update_offset, timeout=timeout)
            )
        except TelegramError as exc:
            logger.error(f"Telegram polling failed, reconnecting: {exc}")
            self._reconnect()
            return []

        messages: list[TelegramMessage] = []
        for update in updates:
            self._update_offset = update.update_id + 1
            message = update.effective_message
            if message is None or message.text is None or message.chat is None:
                continue
            messages.append(
                TelegramMessage(
                    chat_id=message.chat.id, text=message.text, update_id=update.update_id
                )
            )
        return messages

    def send_message(self, chat_id: int, text: str) -> None:
        """Send a text message to a Telegram chat.

        Args:
            chat_id: The destination chat's Telegram id.
            text: The message text to send.

        Raises:
            TelegramClientError: If the client is not connected or the
                message cannot be sent.
        """
        if self._bot is None:
            raise TelegramClientError("Telegram client is not connected.")

        try:
            self._run(self._bot.send_message(chat_id=chat_id, text=text))
        except TelegramError as exc:
            logger.error(f"Telegram outgoing message failed: {exc}")
            raise TelegramClientError(str(exc)) from exc

    def _reconnect(self) -> None:
        """Attempt a single automatic reconnect after a polling failure."""
        logger.info("Telegram reconnecting...")
        self._connected = False
        try:
            self.connect()
            logger.info("Telegram reconnected.")
        except TelegramClientError as exc:
            logger.error(f"Telegram reconnect failed: {exc}")

    def _run(self, coroutine):
        """Run a `telegram.Bot` coroutine to completion on the private loop.

        Guarded by a lock so this client can be safely called from
        both the background polling thread and the CLI thread.

        Args:
            coroutine: The awaitable returned by a `telegram.Bot` call.

        Returns:
            The coroutine's result.
        """
        with self._loop_lock:
            return self._loop.run_until_complete(coroutine)
