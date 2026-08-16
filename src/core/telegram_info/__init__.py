"""EP-040 Telegram Info -- read-only chat/channel metadata lookup.

Exposes exactly one read-only operation, `get_chat(chat_id)`, against
the Telegram Bot API, using the project's existing `python-telegram-bot`
dependency directly -- no new dependency. No message reading, message
history, chat discovery/listing, or any write/mutating Telegram
operation is implemented -- this package can only ever look up a
single, already-known chat's metadata.

This package (`src/core/telegram_info/`) holds only pure,
dependency-free data types -- `TelegramInfoResult` and the
`TelegramInfoError` hierarchy. The one real `Bot.get_chat(...)`
invocation point lives exclusively in `TelegramInfoService`
(`src/services/telegram_info_service.py`), matching the "one
component owns the one real invocation" discipline `GitHubService`
(EP-039) already established for `requests.get(...)`.

EP-040 is architecturally independent of EP-012 "Telegram Gateway"
(`src/core/telegram/`, `src/services/telegram_service.py`,
`src/modules/telegram_module.py`): it constructs its own,
independent `telegram.Bot` instance rather than reusing
`TelegramClient`, and never calls `fetch_updates()`/`get_updates()`
or shares any update offset/cursor with EP-012's background polling
thread. EP-012's files are not imported, modified, or referenced by
this package. The only thing shared with EP-012 is the
`telegram.token` configuration value, read read-only.

Public API:
    TelegramInfoResult -- The outcome of one successful get_chat call.
    TelegramInfoError -- Base class for every exception a call can raise.
    TelegramInfoAuthenticationError -- Invalid token, or no access to the chat.
    TelegramInfoNotFoundError -- The chat_id does not exist or is not resolvable.
    TelegramInfoRateLimitError -- Telegram's rate limit was exceeded.
    TelegramInfoTimeoutError -- The call exceeded 'telegram_info.timeout_seconds'.
    TelegramInfoNetworkError -- A connection-level failure occurred.
    TelegramInfoAPIError -- Any other Telegram API error.
"""

from __future__ import annotations

from src.core.telegram_info.telegram_info_error import (
    TelegramInfoAPIError,
    TelegramInfoAuthenticationError,
    TelegramInfoError,
    TelegramInfoNetworkError,
    TelegramInfoNotFoundError,
    TelegramInfoRateLimitError,
    TelegramInfoTimeoutError,
)
from src.core.telegram_info.telegram_info_result import TelegramInfoResult

__all__ = [
    "TelegramInfoResult",
    "TelegramInfoError",
    "TelegramInfoAuthenticationError",
    "TelegramInfoNotFoundError",
    "TelegramInfoRateLimitError",
    "TelegramInfoTimeoutError",
    "TelegramInfoNetworkError",
    "TelegramInfoAPIError",
]
