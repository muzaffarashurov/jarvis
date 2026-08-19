"""EP-041 Discord Integration -- read-only inspection of Discord guilds,
channels, members, and messages.

Exposes five read-only operations (`get_guild`, `list_guild_channels`,
`get_channel`, `get_guild_member`, `get_message`) against the Discord
REST API (v10), using the project's existing `requests` dependency
directly -- no Discord SDK, no Gateway/WebSocket connection. No create,
update, delete, comment, moderation, webhook, role, reaction, invite,
or any other write/mutating operation is implemented -- this package
can only ever read from Discord.

This package (`src/core/discord/`) holds only pure, dependency-free
data types -- `DiscordResult` and the `DiscordError` hierarchy. The
one real `requests.get(...)` invocation point lives exclusively in
`DiscordService` (`src/services/discord_service.py`), matching the
"one component owns the one real invocation" discipline `GitHubService`
(EP-039) already established.

This subsystem has no dependency on any other Engineering Package --
it depends only on `Config` and, at call time, the process environment
(`DISCORD_TOKEN`).

`DiscordService` is deliberately stateless (no persistent connection,
no event loop, no background thread, no cursor/offset of any kind), so
a future Discord Gateway/WebSocket EP could coexist without sharing
state or creating hidden coupling with this one.

Public API:
    DiscordResult -- The outcome of one successful Discord REST API call.
    DiscordError -- Base class for every exception an operation call can raise.
    DiscordAuthenticationError -- Missing/invalid DISCORD_TOKEN, or a
        401/403 from the API.
    DiscordNotFoundError -- The requested resource does not exist (HTTP 404).
    DiscordRateLimitError -- Discord's rate limit was exceeded (HTTP 429).
    DiscordTimeoutError -- The request exceeded 'discord.timeout_seconds'.
    DiscordNetworkError -- A connection-level failure occurred.
    DiscordAPIError -- Any other non-2xx status, or an unparseable response body.
"""

from __future__ import annotations

from src.core.discord.discord_error import (
    DiscordAPIError,
    DiscordAuthenticationError,
    DiscordError,
    DiscordNetworkError,
    DiscordNotFoundError,
    DiscordRateLimitError,
    DiscordTimeoutError,
)
from src.core.discord.discord_result import DiscordResult

__all__ = [
    "DiscordResult",
    "DiscordError",
    "DiscordAuthenticationError",
    "DiscordNotFoundError",
    "DiscordRateLimitError",
    "DiscordTimeoutError",
    "DiscordNetworkError",
    "DiscordAPIError",
]
