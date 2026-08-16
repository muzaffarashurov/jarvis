"""TelegramInfoResult domain model for EP-040 Telegram Info integration.

Pure data describing the outcome of one Telegram Bot API `get_chat`
call -- no Bot API call happens in this module, matching the pattern
already used by `GitHubResult` (`src/core/github/github_result.py`,
EP-039): a small, dependency-free data type owned by Core, with the
one real invocation (`Bot.get_chat(...)`) living exclusively in
`TelegramInfoService` (`src/services/telegram_info_service.py`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["TelegramInfoResult"]


@dataclass(frozen=True)
class TelegramInfoResult:
    """The outcome of one successful `get_chat` call.

    Attributes:
        chat_id: The chat id (or `@username`) that was looked up,
            exactly as the caller supplied it.
        data: The chat's data, exactly as `telegram.Chat.to_dict()`
            returns it -- a raw, neutral structure. No further domain
            modeling is imposed.
    """

    chat_id: int | str
    data: Any
