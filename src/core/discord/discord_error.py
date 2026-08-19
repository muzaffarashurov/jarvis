"""DiscordError hierarchy for EP-041 Discord Integration.

A flat domain-exception hierarchy per subsystem, matching this
project's existing convention (`GitHubError` in EP-039). Modeled
directly on `GitHubError`'s split -- both subsystems reuse `requests`
directly, unlike EP-040's library-specific exception mapping. Discord
does not overload HTTP 403 for rate-limiting the way GitHub does:
Discord uses 429 exclusively for rate limits, so 401 and 403 both map
to `DiscordAuthenticationError` (bad token vs. forbidden access
respectively), with no rate-limit-header disambiguation needed.

`DiscordServiceError` (raised only for invalid 'discord.*'
configuration, at `DiscordService.__init__` time) intentionally does
NOT subclass `DiscordError`: it can never occur from a running
operation call, only from Bootstrap construction, matching how
`GitHubServiceError` is distinct from `GitHubError` in EP-039.
`DiscordServiceError` is defined in `src/services/discord_service.py`,
not here, for the same reason.
"""

from __future__ import annotations

__all__ = [
    "DiscordError",
    "DiscordAuthenticationError",
    "DiscordNotFoundError",
    "DiscordRateLimitError",
    "DiscordTimeoutError",
    "DiscordNetworkError",
    "DiscordAPIError",
]


class DiscordError(Exception):
    """Base class for every Discord Integration exception raised by an operation call."""


class DiscordAuthenticationError(DiscordError):
    """DISCORD_TOKEN is missing/blank, or Discord rejected it/denied
    access (HTTP 401 or 403)."""


class DiscordNotFoundError(DiscordError):
    """The requested guild/channel/member/message does not exist, or
    the bot cannot see it (HTTP 404)."""


class DiscordRateLimitError(DiscordError):
    """Discord's rate limit was exceeded (HTTP 429)."""


class DiscordTimeoutError(DiscordError):
    """The request exceeded 'discord.timeout_seconds'."""


class DiscordNetworkError(DiscordError):
    """A connection-level failure occurred (DNS, TLS, refused, ...)."""


class DiscordAPIError(DiscordError):
    """Discord returned any other non-2xx status not covered above, or
    an unparseable (non-JSON) response body."""
