"""Real engineering tests for EP-041 STEP 2 - DiscordService.

Builds a real DiscordService with a small, duck-typed stub `session`
object standing in for `requests.Session` -- no real Discord API call
is ever made anywhere in this suite. `DISCORD_TOKEN` is set/unset
directly via `os.environ` around each test that needs it, always
restored afterward, so this suite never depends on (or leaks into) the
real process environment beyond the duration of a single test.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import requests

from src.core.config import Config
from src.core.discord.discord_error import (
    DiscordAPIError,
    DiscordAuthenticationError,
    DiscordNetworkError,
    DiscordNotFoundError,
    DiscordRateLimitError,
    DiscordTimeoutError,
)
from src.services.discord_service import DiscordService, DiscordServiceError
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

_TOKEN_ENV_VAR = "DISCORD_TOKEN"
_FAKE_TOKEN = "fake-discord-token-for-tests-xyz123"


class _TokenGuard:
    """Context manager: set DISCORD_TOKEN for the duration of a `with`
    block (or unset it entirely if `value` is None), always restoring
    whatever was present before."""

    def __init__(self, value: str | None) -> None:
        self._value = value
        self._original: str | None = None
        self._was_set = False

    def __enter__(self) -> None:
        self._was_set = _TOKEN_ENV_VAR in os.environ
        self._original = os.environ.get(_TOKEN_ENV_VAR)
        if self._value is None:
            os.environ.pop(_TOKEN_ENV_VAR, None)
        else:
            os.environ[_TOKEN_ENV_VAR] = self._value

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._was_set:
            os.environ[_TOKEN_ENV_VAR] = self._original
        else:
            os.environ.pop(_TOKEN_ENV_VAR, None)


class _StubResponse:
    """A minimal duck-typed stand-in for `requests.Response`."""

    def __init__(self, status_code: int, json_data=None, invalid_json: bool = False):
        self.status_code = status_code
        self._json_data = json_data
        self._invalid_json = invalid_json

    def json(self):
        if self._invalid_json:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._json_data


class _StubSession:
    """A minimal duck-typed stand-in for `requests.Session`.

    Returns a scripted `_StubResponse` (or raises a scripted
    exception) on every `.get()` call, and records every call made so
    tests can assert a call did/did not happen and inspect its
    headers/timeout/url.
    """

    def __init__(self, response: _StubResponse | None = None, exception: Exception | None = None):
        self.response = response
        self.exception = exception
        self.calls: list[dict] = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        if self.exception is not None:
            raise self.exception
        return self.response


def _write_config(directory: Path, sections: str) -> Config:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(sections, encoding="utf-8")
    return Config(config_path).load()


def _default_config(tmp: str) -> Config:
    return _write_config(
        Path(tmp),
        "discord:\n  api_base_url: \"https://discord.com/api/v10\"\n  timeout_seconds: 30\n",
    )


@TestRegistry.register
class DiscordServiceTest(BaseTest):
    NAME = "EP041"

    def run(self):
        self._test_get_guild_success()
        self._test_list_guild_channels_success()
        self._test_get_channel_success()
        self._test_get_guild_member_success()
        self._test_get_message_success()

        self._test_missing_token_raises_and_never_calls_session()
        self._test_blank_token_raises()
        self._test_401_raises_authentication_error()
        self._test_403_raises_authentication_error()
        self._test_404_raises_not_found_error()
        self._test_429_raises_rate_limit_error()
        self._test_500_raises_api_error()
        self._test_timeout_raises_timeout_error()
        self._test_connection_error_raises_network_error()
        self._test_other_request_exception_raises_network_error()
        self._test_malformed_json_raises_api_error()

        self._test_construction_rejects_invalid_timeout()
        self._test_construction_rejects_empty_api_base_url()
        self._test_construction_defaults_applied()

        self._test_token_never_leaks_into_exception_messages()
        self._test_authorization_header_sent_correctly()
        self._test_path_segments_are_url_quoted()
        self._test_configured_base_url_and_timeout_used()

        return self.result

    # ---------- Successful operations ----------

    def _test_get_guild_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {"id": "1", "name": "My Server"}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.get_guild("1")
            self.assert_equal(result.status_code, 200)
            self.assert_equal(result.data["name"], "My Server")
            self.assert_equal(result.operation, "get_guild")

    def _test_list_guild_channels_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, [{"id": "10"}, {"id": "11"}]))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.list_guild_channels("1")
            self.assert_equal(len(result.data), 2)
            self.assert_equal(session.calls[0]["url"], "https://discord.com/api/v10/guilds/1/channels")

    def _test_get_channel_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {"id": "10", "name": "general"}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.get_channel("10")
            self.assert_equal(result.data["name"], "general")
            self.assert_true(session.calls[0]["url"].endswith("/channels/10"))

    def _test_get_guild_member_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {"nick": "Ada", "roles": []}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.get_guild_member("1", "999")
            self.assert_equal(result.data["nick"], "Ada")
            self.assert_true(session.calls[0]["url"].endswith("/guilds/1/members/999"))

    def _test_get_message_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {"id": "555", "content": "hi"}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                result = service.get_message("10", "555")
            self.assert_equal(result.data["content"], "hi")
            self.assert_true(session.calls[0]["url"].endswith("/channels/10/messages/555"))

    # ---------- Authentication ----------

    def _test_missing_token_raises_and_never_calls_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(None):
                try:
                    service.get_guild("1")
                    self.assert_true(False, "missing token should have raised")
                except DiscordAuthenticationError:
                    self.result.add_pass()
            self.assert_equal(len(session.calls), 0, "no HTTP call should be attempted without a token")

    def _test_blank_token_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard("   "):
                try:
                    service.get_guild("1")
                    self.assert_true(False, "blank token should have raised")
                except DiscordAuthenticationError:
                    self.result.add_pass()

    def _test_401_raises_authentication_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(401, {"message": "401: Unauthorized"}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.get_guild("1")
                    self.assert_true(False, "401 should raise DiscordAuthenticationError")
                except DiscordAuthenticationError:
                    self.result.add_pass()

    def _test_403_raises_authentication_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(403, {"message": "Missing Access"}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.get_channel("10")
                    self.assert_true(False, "403 should raise DiscordAuthenticationError")
                except DiscordAuthenticationError:
                    self.result.add_pass()

    # ---------- Not found / rate limit / generic errors ----------

    def _test_404_raises_not_found_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(404, {"message": "Unknown Guild"}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.get_guild("999999")
                    self.assert_true(False, "404 should raise DiscordNotFoundError")
                except DiscordNotFoundError:
                    self.result.add_pass()

    def _test_429_raises_rate_limit_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(429, {"retry_after": 1.5}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.get_guild("1")
                    self.assert_true(False, "429 should raise DiscordRateLimitError")
                except DiscordRateLimitError:
                    self.result.add_pass()

    def _test_500_raises_api_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(500, {}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.get_guild("1")
                    self.assert_true(False, "500 should raise DiscordAPIError")
                except DiscordAPIError:
                    self.result.add_pass()

    # ---------- Network / timeout ----------

    def _test_timeout_raises_timeout_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(exception=requests.exceptions.Timeout("timed out"))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.get_guild("1")
                    self.assert_true(False, "a Timeout exception should raise DiscordTimeoutError")
                except DiscordTimeoutError:
                    self.result.add_pass()

    def _test_connection_error_raises_network_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(exception=requests.exceptions.ConnectionError("refused"))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.get_guild("1")
                    self.assert_true(False, "a ConnectionError should raise DiscordNetworkError")
                except DiscordNetworkError:
                    self.result.add_pass()

    def _test_other_request_exception_raises_network_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(exception=requests.exceptions.RequestException("weird"))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.get_guild("1")
                    self.assert_true(False, "a generic RequestException should raise DiscordNetworkError")
                except DiscordNetworkError:
                    self.result.add_pass()

    def _test_malformed_json_raises_api_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, invalid_json=True))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                try:
                    service.get_guild("1")
                    self.assert_true(False, "malformed JSON should raise DiscordAPIError")
                except DiscordAPIError:
                    self.result.add_pass()

    # ---------- Construction / configuration ----------

    def _test_construction_rejects_invalid_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "discord:\n  timeout_seconds: -5\n")
            try:
                DiscordService(config=config, session=_StubSession())
                self.assert_true(False, "a negative timeout_seconds should have raised")
            except DiscordServiceError:
                self.result.add_pass()

            config2 = _write_config(Path(tmp) / "b", "discord:\n  timeout_seconds: \"nope\"\n")
            try:
                DiscordService(config=config2, session=_StubSession())
                self.assert_true(False, "a non-numeric timeout_seconds should have raised")
            except DiscordServiceError:
                self.result.add_pass()

    def _test_construction_rejects_empty_api_base_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "discord:\n  api_base_url: \"\"\n")
            try:
                DiscordService(config=config, session=_StubSession())
                self.assert_true(False, "an empty api_base_url should have raised")
            except DiscordServiceError:
                self.result.add_pass()

    def _test_construction_defaults_applied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "app:\n  name: \"x\"\n")
            session = _StubSession(response=_StubResponse(200, {"ok": True}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                service.get_guild("1")
            self.assert_equal(session.calls[0]["url"], "https://discord.com/api/v10/guilds/1")
            self.assert_equal(session.calls[0]["timeout"], 30.0)

    def _test_configured_base_url_and_timeout_used(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(
                Path(tmp),
                "discord:\n  api_base_url: \"https://discord.example.test/api/v10\"\n  timeout_seconds: 7\n",
            )
            session = _StubSession(response=_StubResponse(200, {}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                service.get_guild("1")
            self.assert_equal(session.calls[0]["url"], "https://discord.example.test/api/v10/guilds/1")
            self.assert_equal(session.calls[0]["timeout"], 7.0)

    # ---------- Security ----------

    def _test_token_never_leaks_into_exception_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)

            scenarios = [
                (_StubSession(response=_StubResponse(401, {})), DiscordAuthenticationError),
                (_StubSession(response=_StubResponse(403, {})), DiscordAuthenticationError),
                (_StubSession(response=_StubResponse(404, {})), DiscordNotFoundError),
                (_StubSession(response=_StubResponse(429, {})), DiscordRateLimitError),
                (_StubSession(response=_StubResponse(500, {})), DiscordAPIError),
                (_StubSession(exception=requests.exceptions.Timeout()), DiscordTimeoutError),
                (_StubSession(exception=requests.exceptions.ConnectionError()), DiscordNetworkError),
            ]
            for session, expected_exc in scenarios:
                service = DiscordService(config=config, session=session)
                with _TokenGuard(_FAKE_TOKEN):
                    try:
                        service.get_guild("1")
                        self.assert_true(False, f"expected {expected_exc.__name__}")
                    except expected_exc as exc:
                        self.assert_true(
                            _FAKE_TOKEN not in str(exc),
                            f"token leaked into {expected_exc.__name__} message",
                        )

            service = DiscordService(config=config, session=_StubSession(response=_StubResponse(200, {})))
            with _TokenGuard(None):
                try:
                    service.get_guild("1")
                    self.assert_true(False, "missing token should have raised")
                except DiscordAuthenticationError as exc:
                    self.assert_true(_FAKE_TOKEN not in str(exc))

    def _test_authorization_header_sent_correctly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                service.get_guild("1")
            self.assert_equal(session.calls[0]["headers"]["Authorization"], f"Bot {_FAKE_TOKEN}")

    def _test_path_segments_are_url_quoted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            session = _StubSession(response=_StubResponse(200, {}))
            service = DiscordService(config=config, session=session)
            with _TokenGuard(_FAKE_TOKEN):
                service.get_guild_member("guild id", "user/id")
            url = session.calls[0]["url"]
            self.assert_true("guild%20id" in url or "guild+id" in url)
            self.assert_true("user%2Fid" in url)
