"""Business logic that wires EP-041 Discord Integration into the application.

DiscordService is a thin, config-driven wrapper around the Discord
REST API (v10), exposing five read-only operations as its entire
public API. It owns the one place `requests.get(...)` is ever called
in this subsystem -- exactly matching the "one component owns the one
real invocation" discipline `GitHubService` (EP-039) established for
`requests.get(...)` against the GitHub REST API.

Authentication: `DISCORD_TOKEN` is read from `os.environ` at the start
of every operation call (never at `__init__`, never cached on `self`
beyond the duration of a single call, never logged). If unset or
blank, `DiscordAuthenticationError` is raised immediately, before any
HTTP call is attempted. The token is sent only as the `Authorization`
request header; it never appears in a log line, an exception message,
or a `DiscordResult` -- every error message in this module is built
from fixed text and/or the HTTP response, never from the token value.

No create, update, delete, moderation, webhook, role, reaction,
invite, or any other write/mutating Discord operation is implemented
or callable through this service. No Discord Gateway/WebSocket
connection is opened anywhere in this module -- every method is a
single, stateless HTTP GET request.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests
from loguru import logger

from src.core.config import Config
from src.core.discord.discord_error import (
    DiscordAPIError,
    DiscordAuthenticationError,
    DiscordNetworkError,
    DiscordNotFoundError,
    DiscordRateLimitError,
    DiscordTimeoutError,
)
from src.core.discord.discord_result import DiscordResult

_DEFAULT_API_BASE_URL = "https://discord.com/api/v10"
_DEFAULT_TIMEOUT_SECONDS = 30.0
_TOKEN_ENV_VAR = "DISCORD_TOKEN"


class DiscordServiceError(Exception):
    """Raised for invalid 'discord.*' configuration.

    Can only ever be raised from `DiscordService.__init__`, before any
    HTTP call is attempted -- never from a running `get_guild()`/
    `list_guild_channels()`/etc. call, which instead raise
    `DiscordError` subclasses (see `src.core.discord.discord_error`).
    Never raised for a missing/invalid `DISCORD_TOKEN` -- that is
    checked per-call instead (see module docstring) and raises
    `DiscordAuthenticationError`. This mirrors `GitHubServiceError`'s
    split from `GitHubError` in EP-039.
    """


class DiscordService:
    """Config-driven, read-only wrapper around the Discord REST API."""

    def __init__(self, config: Config, session: "requests.Session | None" = None) -> None:
        """Initialize the DiscordService.

        Args:
            config: Loaded application configuration, used to resolve
                'discord.api_base_url' and 'discord.timeout_seconds'.
                Never used to resolve DISCORD_TOKEN -- that is read
                directly from the process environment at call time.
            session: Optional `requests.Session`-like object used to
                perform every HTTP call. Must expose a `.get(url,
                headers=None, timeout=None)` method returning an
                object with `.status_code`, `.json()`, and `.headers`.
                Defaults to a real `requests.Session()` when omitted;
                tests supply a small duck-typed stub instead, so no
                real Discord API call is ever made by this project's
                own test suite.

        Raises:
            DiscordServiceError: If 'discord.api_base_url' is
                configured but empty/blank, or if
                'discord.timeout_seconds' is configured but is not a
                positive number.
        """
        self._config = config
        self._api_base_url = self._resolve_api_base_url()
        self._timeout_seconds = self._resolve_timeout_seconds()
        self._session = session if session is not None else requests.Session()
        logger.info(
            f"Discord Service initialized (api_base_url: {self._api_base_url}, "
            f"timeout: {self._timeout_seconds}s)."
        )

    # ---------- Public API ----------

    def get_guild(self, guild_id: str) -> DiscordResult:
        """Return metadata for a single guild (server).

        Args:
            guild_id: The Discord guild id.

        Returns:
            A DiscordResult whose `data` is the guild's JSON object,
            exactly as Discord returns it.

        Raises:
            DiscordAuthenticationError: If DISCORD_TOKEN is
                missing/blank, or Discord rejects it or denies access.
            DiscordNotFoundError: If the guild does not exist, or the
                bot cannot see it.
            DiscordRateLimitError: If Discord's rate limit was
                exceeded.
            DiscordTimeoutError: If the call exceeds
                'discord.timeout_seconds'.
            DiscordNetworkError: If a connection-level failure occurs.
            DiscordAPIError: If Discord returns any other non-2xx
                status, or an unparseable response body.
        """
        path = f"/guilds/{quote(str(guild_id))}"
        return self._get("get_guild", path)

    def list_guild_channels(self, guild_id: str) -> DiscordResult:
        """Return the list of channels belonging to a guild.

        Args:
            guild_id: The Discord guild id.

        Returns:
            A DiscordResult whose `data` is a list of channel JSON
            objects.

        Raises:
            DiscordAuthenticationError: If DISCORD_TOKEN is
                missing/blank, or Discord rejects it or denies access.
            DiscordNotFoundError: If the guild does not exist, or the
                bot cannot see it.
            DiscordRateLimitError: If Discord's rate limit was
                exceeded.
            DiscordTimeoutError: If the call exceeds
                'discord.timeout_seconds'.
            DiscordNetworkError: If a connection-level failure occurs.
            DiscordAPIError: If Discord returns any other non-2xx
                status, or an unparseable response body.
        """
        path = f"/guilds/{quote(str(guild_id))}/channels"
        return self._get("list_guild_channels", path)

    def get_channel(self, channel_id: str) -> DiscordResult:
        """Return metadata for a single channel.

        Args:
            channel_id: The Discord channel id.

        Returns:
            A DiscordResult whose `data` is the channel's JSON object.

        Raises:
            DiscordAuthenticationError: If DISCORD_TOKEN is
                missing/blank, or Discord rejects it or denies access.
            DiscordNotFoundError: If the channel does not exist, or
                the bot cannot see it.
            DiscordRateLimitError: If Discord's rate limit was
                exceeded.
            DiscordTimeoutError: If the call exceeds
                'discord.timeout_seconds'.
            DiscordNetworkError: If a connection-level failure occurs.
            DiscordAPIError: If Discord returns any other non-2xx
                status, or an unparseable response body.
        """
        path = f"/channels/{quote(str(channel_id))}"
        return self._get("get_channel", path)

    def get_guild_member(self, guild_id: str, user_id: str) -> DiscordResult:
        """Return a single guild member's info.

        Args:
            guild_id: The Discord guild id.
            user_id: The Discord user id.

        Returns:
            A DiscordResult whose `data` is the guild member's JSON
            object (nickname, roles, joined_at, ...).

        Raises:
            DiscordAuthenticationError: If DISCORD_TOKEN is
                missing/blank, or Discord rejects it or denies access.
            DiscordNotFoundError: If the member does not exist, or the
                bot cannot see it.
            DiscordRateLimitError: If Discord's rate limit was
                exceeded.
            DiscordTimeoutError: If the call exceeds
                'discord.timeout_seconds'.
            DiscordNetworkError: If a connection-level failure occurs.
            DiscordAPIError: If Discord returns any other non-2xx
                status, or an unparseable response body.
        """
        path = f"/guilds/{quote(str(guild_id))}/members/{quote(str(user_id))}"
        return self._get("get_guild_member", path)

    def get_message(self, channel_id: str, message_id: str) -> DiscordResult:
        """Return a single message's detail.

        Args:
            channel_id: The Discord channel id the message belongs to.
            message_id: The Discord message id.

        Returns:
            A DiscordResult whose `data` is the message's JSON object.

        Raises:
            DiscordAuthenticationError: If DISCORD_TOKEN is
                missing/blank, or Discord rejects it or denies access.
            DiscordNotFoundError: If the message does not exist, or
                the bot cannot see it.
            DiscordRateLimitError: If Discord's rate limit was
                exceeded.
            DiscordTimeoutError: If the call exceeds
                'discord.timeout_seconds'.
            DiscordNetworkError: If a connection-level failure occurs.
            DiscordAPIError: If Discord returns any other non-2xx
                status, or an unparseable response body.
        """
        path = f"/channels/{quote(str(channel_id))}/messages/{quote(str(message_id))}"
        return self._get("get_message", path)

    # ---------- Internal helpers ----------

    def _require_token(self) -> str:
        """Return DISCORD_TOKEN from the environment, or raise.

        Returns:
            The non-blank token value.

        Raises:
            DiscordAuthenticationError: If DISCORD_TOKEN is unset or
                blank.
        """
        token = os.environ.get(_TOKEN_ENV_VAR)
        if not token or not token.strip():
            raise DiscordAuthenticationError(
                f"{_TOKEN_ENV_VAR} environment variable is not set."
            )
        return token

    def _get(self, operation: str, path: str) -> DiscordResult:
        """Perform one authenticated GET call against the Discord API.

        The sole place `requests.get(...)` is ever called in this
        subsystem. DISCORD_TOKEN is resolved first (see
        `_require_token`), so a missing token never attempts an HTTP
        call at all.

        Args:
            operation: The public method name (e.g. "get_guild"),
                used for `DiscordResult.operation` and log messages
                only.
            path: The API path, beginning with "/", already safely
                constructed (guild_id/channel_id/user_id/message_id
                segments already URL-quoted by the caller).

        Returns:
            A DiscordResult describing a successful (2xx) response.

        Raises:
            DiscordAuthenticationError: If DISCORD_TOKEN is
                missing/blank, or the response is HTTP 401 or 403.
            DiscordNotFoundError: If the response is HTTP 404.
            DiscordRateLimitError: If the response is HTTP 429.
            DiscordTimeoutError: If the call exceeds
                `self._timeout_seconds`.
            DiscordNetworkError: If a connection-level failure occurs.
            DiscordAPIError: If the response is any other non-2xx
                status, or the response body is not valid JSON.
        """
        token = self._require_token()
        url = f"{self._api_base_url}{path}"
        headers = {"Authorization": f"Bot {token}"}

        try:
            response = self._session.get(url, headers=headers, timeout=self._timeout_seconds)
        except requests.exceptions.Timeout as exc:
            logger.error(f"Discord request timed out (operation='{operation}').")
            raise DiscordTimeoutError(
                f"Discord request timed out after {self._timeout_seconds}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error(f"Discord request network failure (operation='{operation}'): {exc}")
            raise DiscordNetworkError("Could not reach the Discord API.") from exc
        except requests.exceptions.RequestException as exc:
            logger.error(f"Discord request failed (operation='{operation}'): {exc}")
            raise DiscordNetworkError(str(exc)) from exc

        return self._parse_response(operation, response)

    def _parse_response(self, operation: str, response: Any) -> DiscordResult:
        """Translate a raw response object into a DiscordResult or error.

        Args:
            operation: The public method name, for `DiscordResult.operation`.
            response: The raw response object (a real
                `requests.Response`, or a test stub exposing the same
                `.status_code`/`.json()`/`.headers` shape).

        Returns:
            The parsed DiscordResult, on a 2xx status.

        Raises:
            DiscordAuthenticationError: On HTTP 401 or 403.
            DiscordNotFoundError: On HTTP 404.
            DiscordRateLimitError: On HTTP 429.
            DiscordAPIError: On any other non-2xx status, or an
                unparseable response body.
        """
        status_code = response.status_code

        if status_code in (401, 403):
            raise DiscordAuthenticationError(
                "Discord rejected the configured token or denied access to this resource."
            )

        if status_code == 404:
            raise DiscordNotFoundError(f"Discord resource not found (operation='{operation}').")

        if status_code == 429:
            raise DiscordRateLimitError("Discord API rate limit exceeded.")

        if status_code < 200 or status_code >= 300:
            raise DiscordAPIError(f"Discord request failed (HTTP {status_code}).")

        try:
            data = response.json()
        except ValueError as exc:
            raise DiscordAPIError("Discord returned an invalid (non-JSON) response body.") from exc

        return DiscordResult(operation=operation, status_code=status_code, data=data)

    def _resolve_api_base_url(self) -> str:
        """Resolve and validate 'discord.api_base_url'.

        Returns:
            The configured base URL (default `_DEFAULT_API_BASE_URL`),
            with any trailing slash stripped.

        Raises:
            DiscordServiceError: If the configured value is present
                but empty/blank.
        """
        value = self._config.get("discord.api_base_url", _DEFAULT_API_BASE_URL)
        if not isinstance(value, str) or not value.strip():
            raise DiscordServiceError(
                f"Invalid value for 'discord.api_base_url': expected a non-empty string, got {value!r}."
            )
        return value.rstrip("/")

    def _resolve_timeout_seconds(self) -> float:
        """Resolve and validate 'discord.timeout_seconds'.

        Returns:
            The configured timeout in seconds (default
            `_DEFAULT_TIMEOUT_SECONDS`).

        Raises:
            DiscordServiceError: If the configured value is not a
                positive number.
        """
        value = self._config.get("discord.timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise DiscordServiceError(
                f"Invalid value for 'discord.timeout_seconds': expected a positive number, got {value!r}."
            )
        return float(value)
