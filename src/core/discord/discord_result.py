"""DiscordResult domain model for EP-041 Discord Integration.

Pure data describing the outcome of one Discord REST API call -- no
HTTP call happens in this module, matching the pattern already used by
`GitHubResult` (`src/core/github/github_result.py`, EP-039): a small,
dependency-free data type owned by Core, with the one real invocation
(`requests.get(...)`) living exclusively in `DiscordService`
(`src/services/discord_service.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["DiscordResult"]


@dataclass(frozen=True)
class DiscordResult:
    """The outcome of one successful Discord REST API call.

    Attributes:
        operation: The DiscordService method that produced this result
            (e.g. "get_guild"), for logging/debugging -- not the full
            request URL.
        status_code: The raw HTTP status code (always 2xx -- a non-2xx
            response is translated into a DiscordError subclass instead
            of a DiscordResult; see `src.core.discord.discord_error`).
        data: The parsed JSON response body, exactly as Discord
            returned it. No further structure/typing is imposed.
    """

    operation: str
    status_code: int
    data: Any
