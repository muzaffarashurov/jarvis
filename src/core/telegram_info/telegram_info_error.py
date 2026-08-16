"""TelegramInfoError hierarchy for EP-040 Telegram Info integration.

A flat domain-exception hierarchy per subsystem, matching this
project's existing convention (`GitHubError` in EP-039, `GitError` in
EP-038). Mapped onto `python-telegram-bot`'s actual exception
hierarchy (`telegram.error.TelegramError` and its subclasses
`InvalidToken`, `Forbidden`, `NetworkError` -> `BadRequest`/`TimedOut`,
`RetryAfter`, and a handful of rarer subclasses), the same way
`GitHubError` was mapped onto `requests.exceptions`. Deliberately more
granular than EP-012's own `TelegramClient`, which catches only the
broad base `TelegramError` -- justified because the confirmed EP-040
architecture instruction is to follow the EP-038/039 precedent for
this new EP; EP-012 itself is untouched and not required to change.

`TelegramInfoServiceError` (raised only for a missing/blank
`telegram.token`, or invalid 'telegram_info.*' configuration, at
`TelegramInfoService.__init__` time) intentionally does NOT subclass
`TelegramInfoError`: it can never occur from a running `get_chat()`
call, only from Bootstrap construction, matching how
`GitHubServiceError`/`GitServiceError` are distinct from their
respective `GitHubError`/`GitError` hierarchies. It is defined in
`src/services/telegram_info_service.py`, not here, for the same
reason.
"""

from __future__ import annotations

__all__ = [
    "TelegramInfoError",
    "TelegramInfoAuthenticationError",
    "TelegramInfoNotFoundError",
    "TelegramInfoRateLimitError",
    "TelegramInfoTimeoutError",
    "TelegramInfoNetworkError",
    "TelegramInfoAPIError",
]


class TelegramInfoError(Exception):
    """Base class for every EP-040 Telegram Info exception raised by a call."""


class TelegramInfoAuthenticationError(TelegramInfoError):
    """telegram.token is invalid (InvalidToken), or the bot has no
    access to the requested chat (Forbidden)."""


class TelegramInfoNotFoundError(TelegramInfoError):
    """The chat_id does not exist or is not resolvable (BadRequest)."""


class TelegramInfoRateLimitError(TelegramInfoError):
    """Telegram's rate limit was exceeded (RetryAfter)."""


class TelegramInfoTimeoutError(TelegramInfoError):
    """The call exceeded 'telegram_info.timeout_seconds' (TimedOut)."""


class TelegramInfoNetworkError(TelegramInfoError):
    """A connection-level failure occurred (NetworkError, other than
    the more specific TimedOut/BadRequest cases above)."""


class TelegramInfoAPIError(TelegramInfoError):
    """Any other TelegramError subclass not covered above (ChatMigrated,
    Conflict, EndPointNotFound, PassportDecryptionError, ...)."""
