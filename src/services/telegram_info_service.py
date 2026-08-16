"""Business logic that wires EP-040 Telegram Info into the application.

TelegramInfoService is a thin, config-driven wrapper around a single
Telegram Bot API operation, `get_chat`, as its entire public API. It
owns the one place `Bot.get_chat(...)` is ever called in this
subsystem -- exactly matching the "one component owns the one real
invocation" discipline `GitHubService` (EP-039) established for
`requests.get(...)`.

Architectural independence from EP-012: this service constructs its
own, independent `telegram.Bot` instance -- it never imports or
instantiates `TelegramClient` (`src/core/telegram/telegram_client.py`),
never calls `fetch_updates()`/`get_updates()`, and never touches any
update offset/cursor. `src/core/telegram/`,
`src/services/telegram_service.py`, and `src/modules/telegram_module.py`
(EP-012) are not imported anywhere in this file. The only thing shared
with EP-012 is the `telegram.token` configuration value, read
read-only -- never duplicated into a second key, never written back.

Like GitHubService, TelegramInfoService owns no thread, queue, or
other persistent resource beyond the one Bot connection it constructs
once at `__init__` (mirroring `TelegramClient.connect()`'s own
one-time `initialize()` pattern): `get_chat()` is a single,
synchronous (internally async-bridged), blocking call that has fully
returned (or raised) before the method returns.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from loguru import logger
from telegram import Bot
from telegram.error import (
    BadRequest,
    Forbidden,
    InvalidToken,
    NetworkError,
    RetryAfter,
    TelegramError,
    TimedOut,
)

from src.core.config import Config
from src.core.telegram_info.telegram_info_error import (
    TelegramInfoAPIError,
    TelegramInfoAuthenticationError,
    TelegramInfoNetworkError,
    TelegramInfoNotFoundError,
    TelegramInfoRateLimitError,
    TelegramInfoTimeoutError,
)
from src.core.telegram_info.telegram_info_result import TelegramInfoResult

_DEFAULT_TIMEOUT_SECONDS = 10.0


class TelegramInfoServiceError(Exception):
    """Raised for a missing/blank 'telegram.token', or invalid
    'telegram_info.*' configuration.

    Can only ever be raised from `TelegramInfoService.__init__`,
    before any Bot API call is attempted -- never from a running
    `get_chat()` call, which instead raises `TelegramInfoError`
    subclasses (see `src.core.telegram_info.telegram_info_error`).
    Mirrors `GitHubServiceError`/`GitServiceError`'s split from their
    respective error hierarchies.
    """


class TelegramInfoService:
    """Config-driven, read-only wrapper around a single Telegram Bot API call."""

    def __init__(self, config: Config, bot: "Bot | None" = None) -> None:
        """Initialize the TelegramInfoService.

        Args:
            config: Loaded application configuration, used to resolve
                'telegram_info.timeout_seconds' and, read-only, the
                existing 'telegram.token' value (EP-012's key -- never
                duplicated into a new one).
            bot: Optional pre-built `telegram.Bot`-like object used
                for every call, in place of constructing a real `Bot`.
                Must expose a `get_chat(chat_id)` coroutine method.
                Defaults to None, in which case a real, independent
                `telegram.Bot(token=...)` is constructed and
                initialized here; tests supply a small duck-typed stub
                instead, so no real Telegram API call is ever made by
                this project's own test suite.

        Raises:
            TelegramInfoServiceError: If 'telegram.token' is
                missing/blank, if 'telegram_info.timeout_seconds' is
                configured but is not a positive number, or if
                constructing/initializing a real Bot fails.
        """
        self._config = config
        self._timeout_seconds = self._resolve_timeout_seconds()

        if bot is not None:
            self._bot = bot
            self._owns_loop = False
            self._loop = None
            self._loop_lock = None
        else:
            token = self._resolve_token()
            self._loop = asyncio.new_event_loop()
            self._loop_lock = threading.Lock()
            self._owns_loop = True
            try:
                real_bot = Bot(token=token)
                self._call(real_bot.initialize())
            except TelegramError as exc:
                raise TelegramInfoServiceError(
                    f"Failed to initialize the Telegram Bot connection: {exc}"
                ) from exc
            self._bot = real_bot

        logger.info(f"Telegram Info Service initialized (timeout: {self._timeout_seconds}s).")

    # ---------- Public API ----------

    def get_chat(self, chat_id: int | str) -> TelegramInfoResult:
        """Return metadata for a single, already-known chat.

        Args:
            chat_id: The numeric chat id, or an `@username` string,
                exactly as the Telegram Bot API accepts for `get_chat`.

        Returns:
            A TelegramInfoResult whose `data` is the chat's fields,
            exactly as `telegram.Chat.to_dict()` returns them.

        Raises:
            TelegramInfoAuthenticationError: If the token is rejected,
                or the bot has no access to the chat.
            TelegramInfoNotFoundError: If the chat does not exist or
                is not resolvable.
            TelegramInfoRateLimitError: If Telegram's rate limit was
                exceeded.
            TelegramInfoTimeoutError: If the call exceeds
                'telegram_info.timeout_seconds'.
            TelegramInfoNetworkError: If a connection-level failure
                occurs.
            TelegramInfoAPIError: If Telegram returns any other error.
        """
        try:
            chat = self._call(
                self._bot.get_chat(
                    chat_id,
                    read_timeout=self._timeout_seconds,
                    connect_timeout=self._timeout_seconds,
                )
            )
        except TimedOut as exc:
            logger.error(f"Telegram get_chat timed out for chat_id={chat_id!r}.")
            raise TelegramInfoTimeoutError(
                f"Telegram request timed out after {self._timeout_seconds}s."
            ) from exc
        except BadRequest as exc:
            raise TelegramInfoNotFoundError(
                f"Telegram chat not found or not resolvable: {chat_id!r}."
            ) from exc
        except (InvalidToken, Forbidden) as exc:
            raise TelegramInfoAuthenticationError(
                "Telegram rejected the configured token, or the bot has no access to this chat."
            ) from exc
        except RetryAfter as exc:
            raise TelegramInfoRateLimitError("Telegram API rate limit exceeded.") from exc
        except NetworkError as exc:
            logger.error(f"Telegram get_chat network failure (chat_id={chat_id!r}): {exc}")
            raise TelegramInfoNetworkError("Could not reach the Telegram API.") from exc
        except TelegramError as exc:
            logger.error(f"Telegram get_chat failed (chat_id={chat_id!r}): {exc}")
            raise TelegramInfoAPIError(str(exc)) from exc

        data = chat.to_dict() if hasattr(chat, "to_dict") else chat
        return TelegramInfoResult(chat_id=chat_id, data=data)

    # ---------- Internal helpers ----------

    def _call(self, coroutine: Any) -> Any:
        """Run a Bot API coroutine to completion, bridging async to sync.

        If this service owns its own event loop (the real-Bot
        construction path), the call is bridged through it under a
        lock, mirroring `TelegramClient._run()`'s own pattern
        (reimplemented independently here, not imported from EP-012).
        If a test-injected `bot` stub was supplied instead, the
        coroutine is awaited via `asyncio.run()` on a fresh loop for
        that single call, since a test stub owns no persistent loop
        of its own.

        Args:
            coroutine: The awaitable returned by a `Bot` call.

        Returns:
            The coroutine's result.
        """
        if self._owns_loop:
            with self._loop_lock:
                return self._loop.run_until_complete(coroutine)
        return asyncio.run(coroutine)

    def _resolve_token(self) -> str:
        """Resolve and validate the existing 'telegram.token' value.

        Returns:
            The non-blank token value.

        Raises:
            TelegramInfoServiceError: If 'telegram.token' is
                missing/blank.
        """
        token = self._config.get("telegram.token", "")
        if not token or not str(token).strip():
            raise TelegramInfoServiceError(
                "'telegram.token' is not configured. EP-040 reuses EP-012's "
                "existing token; no separate telegram_info token exists."
            )
        return str(token)

    def _resolve_timeout_seconds(self) -> float:
        """Resolve and validate 'telegram_info.timeout_seconds'.

        Returns:
            The configured timeout in seconds (default
            `_DEFAULT_TIMEOUT_SECONDS`).

        Raises:
            TelegramInfoServiceError: If the configured value is not a
                positive number.
        """
        value = self._config.get("telegram_info.timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise TelegramInfoServiceError(
                f"Invalid value for 'telegram_info.timeout_seconds': expected a positive number, got {value!r}."
            )
        return float(value)
