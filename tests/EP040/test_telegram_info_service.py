"""Real engineering tests for EP-040 STEP 2 - TelegramInfoService.

Builds a real TelegramInfoService with a small, duck-typed stub `bot`
object standing in for `telegram.Bot` -- no real Telegram API call is
ever made anywhere in this suite, and no real bot token is required.
The stub exposes ONLY `get_chat` (an async method), structurally
proving no polling/update-related method is ever needed or called by
this subsystem.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

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
from src.services.telegram_info_service import TelegramInfoService, TelegramInfoServiceError
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

_FAKE_TOKEN = "fake-telegram-token-for-tests-xyz123"


class _StubChat:
    """A minimal duck-typed stand-in for `telegram.Chat`."""

    def __init__(self, data: dict):
        self._data = data

    def to_dict(self) -> dict:
        return self._data


class _StubBot:
    """A minimal duck-typed stand-in for `telegram.Bot`.

    Exposes ONLY `get_chat` -- no `get_updates`/`fetch_updates`/`initialize`
    method exists on this class at all, so any accidental attempt by
    TelegramInfoService to call a polling-related method would raise
    AttributeError, structurally proving no such call path exists.
    """

    def __init__(self, response_data: dict | None = None, exception: Exception | None = None):
        self.response_data = response_data
        self.exception = exception
        self.calls: list[dict] = []

    async def get_chat(self, chat_id, **kwargs):
        self.calls.append({"chat_id": chat_id, "kwargs": kwargs})
        if self.exception is not None:
            raise self.exception
        return _StubChat(self.response_data)


def _write_config(directory: Path, sections: str) -> Config:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(sections, encoding="utf-8")
    return Config(config_path).load()


def _default_config(tmp: str) -> Config:
    return _write_config(
        Path(tmp),
        f"telegram:\n  token: \"{_FAKE_TOKEN}\"\n\ntelegram_info:\n  timeout_seconds: 10\n",
    )


@TestRegistry.register
class TelegramInfoServiceTest(BaseTest):
    NAME = "EP040"

    def run(self):
        self._test_get_chat_success()
        self._test_correct_chat_id_passed_to_bot()
        self._test_result_mapping()

        self._test_invalid_token_raises_authentication_error()
        self._test_forbidden_raises_authentication_error()
        self._test_bad_request_raises_not_found_error()
        self._test_retry_after_raises_rate_limit_error()
        self._test_timed_out_raises_timeout_error()
        self._test_network_error_raises_network_error()
        self._test_generic_telegram_error_raises_api_error()

        self._test_missing_token_raises_service_error()
        self._test_blank_token_raises_service_error()

        self._test_construction_rejects_invalid_timeout()

        self._test_token_never_leaks_into_exception_messages()
        self._test_timeout_kwargs_passed_to_bot()
        self._test_no_polling_method_exists_on_service()

        return self.result

    # ---------- Successful operation ----------

    def _test_get_chat_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            bot = _StubBot(response_data={"id": 12345, "type": "private", "first_name": "Ada"})
            service = TelegramInfoService(config=config, bot=bot)
            result = service.get_chat(12345)
            self.assert_equal(result.chat_id, 12345)
            self.assert_equal(result.data["type"], "private")

    def _test_correct_chat_id_passed_to_bot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            bot = _StubBot(response_data={"id": 999})
            service = TelegramInfoService(config=config, bot=bot)
            service.get_chat("@somechannel")
            self.assert_equal(bot.calls[0]["chat_id"], "@somechannel")

    def _test_result_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            data = {"id": 42, "type": "channel", "title": "Test Channel", "description": "hi"}
            bot = _StubBot(response_data=data)
            service = TelegramInfoService(config=config, bot=bot)
            result = service.get_chat(42)
            self.assert_equal(result.data, data)

    # ---------- Error mappings ----------

    def _test_invalid_token_raises_authentication_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            bot = _StubBot(exception=InvalidToken("bad token"))
            service = TelegramInfoService(config=config, bot=bot)
            try:
                service.get_chat(1)
                self.assert_true(False, "InvalidToken should raise TelegramInfoAuthenticationError")
            except TelegramInfoAuthenticationError:
                self.result.add_pass()

    def _test_forbidden_raises_authentication_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            bot = _StubBot(exception=Forbidden("bot was blocked"))
            service = TelegramInfoService(config=config, bot=bot)
            try:
                service.get_chat(1)
                self.assert_true(False, "Forbidden should raise TelegramInfoAuthenticationError")
            except TelegramInfoAuthenticationError:
                self.result.add_pass()

    def _test_bad_request_raises_not_found_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            bot = _StubBot(exception=BadRequest("Chat not found"))
            service = TelegramInfoService(config=config, bot=bot)
            try:
                service.get_chat(999999)
                self.assert_true(False, "BadRequest should raise TelegramInfoNotFoundError")
            except TelegramInfoNotFoundError:
                self.result.add_pass()

    def _test_retry_after_raises_rate_limit_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            bot = _StubBot(exception=RetryAfter(30))
            service = TelegramInfoService(config=config, bot=bot)
            try:
                service.get_chat(1)
                self.assert_true(False, "RetryAfter should raise TelegramInfoRateLimitError")
            except TelegramInfoRateLimitError:
                self.result.add_pass()

    def _test_timed_out_raises_timeout_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            bot = _StubBot(exception=TimedOut())
            service = TelegramInfoService(config=config, bot=bot)
            try:
                service.get_chat(1)
                self.assert_true(False, "TimedOut should raise TelegramInfoTimeoutError")
            except TelegramInfoTimeoutError:
                self.result.add_pass()

    def _test_network_error_raises_network_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            bot = _StubBot(exception=NetworkError("connection refused"))
            service = TelegramInfoService(config=config, bot=bot)
            try:
                service.get_chat(1)
                self.assert_true(False, "NetworkError should raise TelegramInfoNetworkError")
            except TelegramInfoNetworkError:
                self.result.add_pass()

    def _test_generic_telegram_error_raises_api_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            bot = _StubBot(exception=TelegramError("something else went wrong"))
            service = TelegramInfoService(config=config, bot=bot)
            try:
                service.get_chat(1)
                self.assert_true(False, "a generic TelegramError should raise TelegramInfoAPIError")
            except TelegramInfoAPIError:
                self.result.add_pass()

    # ---------- Token / construction ----------

    def _test_missing_token_raises_service_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "app:\n  name: \"x\"\n")
            try:
                TelegramInfoService(config=config)
                self.assert_true(False, "missing telegram.token should have raised, with no network call")
            except TelegramInfoServiceError:
                self.result.add_pass()

    def _test_blank_token_raises_service_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "telegram:\n  token: \"   \"\n")
            try:
                TelegramInfoService(config=config)
                self.assert_true(False, "blank telegram.token should have raised, with no network call")
            except TelegramInfoServiceError:
                self.result.add_pass()

    def _test_construction_rejects_invalid_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(
                Path(tmp), f"telegram:\n  token: \"{_FAKE_TOKEN}\"\n\ntelegram_info:\n  timeout_seconds: -1\n"
            )
            bot = _StubBot(response_data={})
            try:
                TelegramInfoService(config=config, bot=bot)
                self.assert_true(False, "a negative timeout_seconds should have raised")
            except TelegramInfoServiceError:
                self.result.add_pass()

            config2 = _write_config(
                Path(tmp) / "b",
                f"telegram:\n  token: \"{_FAKE_TOKEN}\"\n\ntelegram_info:\n  timeout_seconds: \"nope\"\n",
            )
            try:
                TelegramInfoService(config=config2, bot=bot)
                self.assert_true(False, "a non-numeric timeout_seconds should have raised")
            except TelegramInfoServiceError:
                self.result.add_pass()

    # ---------- Security / structural checks ----------

    def _test_token_never_leaks_into_exception_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)  # config has _FAKE_TOKEN set, but bot is injected below

            scenarios = [
                (InvalidToken("bad"), TelegramInfoAuthenticationError),
                (Forbidden("no access"), TelegramInfoAuthenticationError),
                (BadRequest("not found"), TelegramInfoNotFoundError),
                (RetryAfter(5), TelegramInfoRateLimitError),
                (TimedOut(), TelegramInfoTimeoutError),
                (NetworkError("refused"), TelegramInfoNetworkError),
                (TelegramError("other"), TelegramInfoAPIError),
            ]
            for exc_to_raise, expected in scenarios:
                bot = _StubBot(exception=exc_to_raise)
                service = TelegramInfoService(config=config, bot=bot)
                try:
                    service.get_chat(1)
                    self.assert_true(False, f"expected {expected.__name__}")
                except expected as exc:
                    self.assert_true(
                        _FAKE_TOKEN not in str(exc), f"token leaked into {expected.__name__} message"
                    )

            # And the missing-token construction error itself must not echo
            # any token-shaped value either.
            empty_config = _write_config(Path(tmp) / "empty", "app:\n  name: \"x\"\n")
            try:
                TelegramInfoService(config=empty_config)
                self.assert_true(False, "missing token should have raised")
            except TelegramInfoServiceError as exc:
                self.assert_true(_FAKE_TOKEN not in str(exc))

    def _test_timeout_kwargs_passed_to_bot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _default_config(tmp)
            bot = _StubBot(response_data={"id": 1})
            service = TelegramInfoService(config=config, bot=bot)
            service.get_chat(1)
            kwargs = bot.calls[0]["kwargs"]
            self.assert_equal(kwargs.get("read_timeout"), 10.0)
            self.assert_equal(kwargs.get("connect_timeout"), 10.0)

    def _test_no_polling_method_exists_on_service(self) -> None:
        for forbidden_name in ("fetch_updates", "get_updates", "poll", "poll_loop", "start_polling"):
            self.assert_true(
                not hasattr(TelegramInfoService, forbidden_name),
                f"TelegramInfoService must not expose a '{forbidden_name}' method",
            )
