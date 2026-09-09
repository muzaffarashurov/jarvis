"""EP-067 test suite: TelegramService poll loop exception containment.

Covers, per `EP067_DESIGN.md` Section 13:
    A. Normal polling still occurs when nothing fails.
    B. An unexpected (non-TelegramClientError) exception from
       `_poll_once()` does not escape the `"telegram-poll"` thread --
       including exceptions raised from inside the message-routing
       path, not only from `fetch_updates()` itself.
    C. The loop survives one failure and performs a later successful
       poll (proves continuation, not merely that the exception was
       logged).
    D. Repeated unexpected failures do not terminate the loop.
    E. The failure is actually recorded via the real logging pipeline,
       using the new, distinct message.
    F. No application data (message text, chat id) is leaked into the
       log by the new handler beyond what `str(exc)` itself carries.
    G. The pre-existing `TelegramClientError` handling inside
       `_poll_once()` is unchanged and not replaced by the new guard.
    H. `stop()` still terminates the loop cleanly after a survived
       exception.
    I. The loop does not busy-loop after a failure -- consecutive poll
       attempts remain spaced by roughly `polling_interval`.

Self-contained per this repository's own per-EP test convention (no
import from `tests/EP061/`, `tests/EP062/`, `tests/EP063/`,
`tests/EP064/`, `tests/EP065/`, or `tests/EP066/`) -- the local fixtures
below are deliberately near-identical in *shape* to (but independent,
freshly-authored copies of) the kind of fake `TelegramClient` and
`_RecordingModule` `tests/EP065/test_command_router_malformed_input.py`
already uses for the same real objects.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from loguru import logger

from src.core.command_router import CommandResult, CommandRouter
from src.core.config import Config
from src.core.telegram.telegram_client import TelegramClientError, TelegramMessage
from src.core.telegram.telegram_router import TelegramRouter
from src.services.telegram_service import TelegramService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

# ================= Local fixtures (independent of other tests/EP0XX/) =================


class _RecordingModule:
    """Minimal, real `CommandModule` implementation -- records every call.

    Independent, EP-067-owned copy of the kind of stub
    `tests/EP065/test_command_router_malformed_input.py`'s own
    `_RecordingModule` already uses.
    """

    def __init__(self, name: str = "stub") -> None:
        self._name = name
        self.calls: list[tuple[str, list[str]]] = []

    @property
    def name(self) -> str:
        return self._name

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        self.calls.append((action, arguments))
        return CommandResult(success=True, message=f"executed:{action}")


class _FakeTelegramClient:
    """Deterministic, test-only Telegram client -- no network, no real Bot API.

    Duck-typed to exactly the surface `TelegramService` calls
    (`connect`, `disconnect`, `is_connected`, `fetch_updates`,
    `send_message`). `fetch_updates()` consumes one queued "step" per
    call: a step is either a `list[TelegramMessage]` to return, or a
    `BaseException` *instance* to raise -- allowing a single test to
    script a mix of successful batches, `TelegramClientError` failures,
    and arbitrary unexpected exceptions across successive poll cycles.
    Once the queue is exhausted, an empty list is returned (normal idle
    polling), never an exception, so a test's later assertions are not
    accidentally disturbed by trailing poll cycles.
    """

    def __init__(self, steps: list) -> None:
        self._steps = list(steps)
        self._connected = False
        self.sent_messages: list[tuple[int, str]] = []
        self.fetch_call_count = 0
        self.fetch_call_times: list[float] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def fetch_updates(self, timeout: int = 0) -> list[TelegramMessage]:
        self.fetch_call_count += 1
        self.fetch_call_times.append(time.monotonic())
        if self._steps:
            step = self._steps.pop(0)
        else:
            step = []
        if isinstance(step, BaseException):
            raise step
        return step

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))


class _RaisingRouter:
    """A duck-typed stand-in for `TelegramRouter` whose `route()` always raises.

    Used only to prove `_poll_loop()`'s new guard contains *any*
    exception escaping `_poll_once()` -- not merely ones raised by
    `TelegramClient.fetch_updates()` -- without modifying the real
    `TelegramRouter`/`CommandRouter` in any way (Owner Decision D2/D8:
    this EP does not touch either file; this fixture simply satisfies
    `TelegramService`'s duck-typed dependency on an object with a
    `.route(chat_id, text)` method).
    """

    def __init__(self, exc_factory) -> None:
        self._exc_factory = exc_factory
        self.call_count = 0

    def route(self, chat_id: int, text: str) -> CommandResult:
        self.call_count += 1
        raise self._exc_factory()


def _build_telegram_config(tmp_path: Path, polling_interval: float = 0.03) -> Config:
    """Build a real, minimal Config enabling Telegram with fast polling."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        "telegram:\n"
        "  enabled: true\n"
        "  auto_start: false\n"
        f"  polling_interval: {polling_interval}\n"
        "  token: fake-token-not-used-by-fake-client\n"
        "  allowed_chat_ids: [1]\n",
        encoding="utf-8",
    )
    return Config(config_dir / "config.yaml").load()


def _build_real_router() -> tuple[TelegramRouter, _RecordingModule]:
    """Build a real `TelegramRouter` over a real `CommandRouter`, one stub module."""
    command_router = CommandRouter()
    module = _RecordingModule("stub")
    command_router.register(module)
    router = TelegramRouter(command_router=command_router, allowed_chat_ids=[1])
    return router, module


def _capture_logs() -> tuple[list[str], int]:
    """Attach a fresh loguru sink capturing formatted messages.

    Returns the list that will be appended to, and the sink id (to be
    removed with `logger.remove(sink_id)` when the caller is done).
    """
    lines: list[str] = []
    sink_id = logger.add(lambda message: lines.append(message.record["message"]), level="DEBUG")
    return lines, sink_id


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.01) -> bool:
    """Poll `predicate()` until it is truthy or `timeout` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@TestRegistry.register
class TelegramPollLoopResilienceTest(BaseTest):
    """EP-067 regression suite (`NAME = "EP067"`)."""

    NAME = "EP067"

    def run(self):
        self._test_normal_polling_still_occurs()
        self._test_unexpected_exception_from_fetch_does_not_escape_the_thread()
        self._test_unexpected_exception_from_routing_does_not_escape_the_thread()
        self._test_loop_recovers_and_polls_after_one_failure()
        self._test_repeated_unexpected_failures_do_not_kill_the_loop()
        self._test_unexpected_failure_is_logged_at_error_level()
        self._test_no_sensitive_data_leaks_into_the_new_log_message()
        self._test_existing_telegramclienterror_handling_is_unchanged()
        self._test_stop_still_terminates_cleanly_after_a_survived_exception()
        self._test_no_busy_loop_after_a_failure()
        return self.result

    # ---------- A. Normal polling ----------

    def _test_normal_polling_still_occurs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = _build_telegram_config(tmp_path)
            router, module = _build_real_router()
            fake_client = _FakeTelegramClient(
                steps=[
                    [TelegramMessage(chat_id=1, text="stub ping", update_id=1)],
                ]
            )
            service = TelegramService(config=config, client=fake_client, router=router)
            start_result = service.start()
            self.assert_true(start_result.success, f"start() failed: {start_result.message}")
            try:
                ok = _wait_until(lambda: len(module.calls) >= 1, timeout=5.0)
                self.assert_true(ok, "expected the queued message to be routed and executed")
                self.assert_true(
                    service._is_poll_loop_running(),  # noqa: SLF001 - test-only introspection
                    "expected the polling thread to remain alive during normal operation",
                )
            finally:
                service.stop()

    # ---------- B. Unexpected exception containment ----------

    def _test_unexpected_exception_from_fetch_does_not_escape_the_thread(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = _build_telegram_config(tmp_path)
            router, _module = _build_real_router()
            fake_client = _FakeTelegramClient(
                steps=[
                    RuntimeError("deliberate unexpected fetch failure"),
                ]
            )
            service = TelegramService(config=config, client=fake_client, router=router)
            start_result = service.start()
            self.assert_true(start_result.success, f"start() failed: {start_result.message}")
            try:
                ok = _wait_until(lambda: fake_client.fetch_call_count >= 1, timeout=5.0)
                self.assert_true(ok, "expected fetch_updates() to have been called")
                # Give the exception path a bounded moment to resolve, then
                # confirm the thread is still alive (not merely that the
                # call happened before a crash).
                still_alive = _wait_until(
                    lambda: service._is_poll_loop_running(),  # noqa: SLF001
                    timeout=2.0,
                )
                self.assert_true(
                    still_alive,
                    "the 'telegram-poll' thread must survive an unexpected "
                    "exception from fetch_updates()",
                )
            finally:
                service.stop()

    def _test_unexpected_exception_from_routing_does_not_escape_the_thread(self) -> None:
        """Proves containment is not narrowly scoped to fetch_updates() alone.

        Uses a duck-typed `_RaisingRouter` in place of the real
        `TelegramRouter` -- `TelegramService` depends on `router.route()`
        structurally, not on the concrete `TelegramRouter` class, so
        this exercises the same `_poll_loop()` guard against a
        different failure origin without modifying `TelegramRouter`
        itself in any way.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = _build_telegram_config(tmp_path)
            raising_router = _RaisingRouter(lambda: ValueError("deliberate routing failure"))
            fake_client = _FakeTelegramClient(
                steps=[
                    [TelegramMessage(chat_id=1, text="stub ping", update_id=1)],
                ]
            )
            service = TelegramService(config=config, client=fake_client, router=raising_router)
            start_result = service.start()
            self.assert_true(start_result.success, f"start() failed: {start_result.message}")
            try:
                ok = _wait_until(lambda: raising_router.call_count >= 1, timeout=5.0)
                self.assert_true(ok, "expected route() to have been called")
                still_alive = _wait_until(
                    lambda: service._is_poll_loop_running(),  # noqa: SLF001
                    timeout=2.0,
                )
                self.assert_true(
                    still_alive,
                    "the 'telegram-poll' thread must survive an unexpected "
                    "exception raised from route()",
                )
            finally:
                service.stop()

    # ---------- C. Recovery ----------

    def _test_loop_recovers_and_polls_after_one_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = _build_telegram_config(tmp_path)
            router, module = _build_real_router()
            fake_client = _FakeTelegramClient(
                steps=[
                    RuntimeError("deliberate unexpected failure #1"),
                    [TelegramMessage(chat_id=1, text="stub ping", update_id=1)],
                ]
            )
            service = TelegramService(config=config, client=fake_client, router=router)
            start_result = service.start()
            self.assert_true(start_result.success, f"start() failed: {start_result.message}")
            try:
                ok = _wait_until(lambda: len(module.calls) >= 1, timeout=5.0)
                self.assert_true(
                    ok,
                    "expected the second, successful poll cycle to actually "
                    "route and execute its queued message after the first "
                    "cycle's unexpected failure",
                )
                self.assert_true(fake_client.fetch_call_count >= 2)
            finally:
                service.stop()

    # ---------- D. Repeated failures ----------

    def _test_repeated_unexpected_failures_do_not_kill_the_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = _build_telegram_config(tmp_path)
            router, _module = _build_real_router()
            fake_client = _FakeTelegramClient(
                steps=[
                    RuntimeError("deliberate unexpected failure #1"),
                    RuntimeError("deliberate unexpected failure #2"),
                    RuntimeError("deliberate unexpected failure #3"),
                    RuntimeError("deliberate unexpected failure #4"),
                ]
            )
            service = TelegramService(config=config, client=fake_client, router=router)
            start_result = service.start()
            self.assert_true(start_result.success, f"start() failed: {start_result.message}")
            try:
                ok = _wait_until(lambda: fake_client.fetch_call_count >= 4, timeout=5.0)
                self.assert_true(ok, "expected all four failing polls to have been attempted")
                self.assert_true(
                    service._is_poll_loop_running(),  # noqa: SLF001
                    "the polling thread must survive repeated, consecutive "
                    "unexpected failures",
                )
            finally:
                service.stop()

    # ---------- E. Logging ----------

    def _test_unexpected_failure_is_logged_at_error_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = _build_telegram_config(tmp_path)
            router, _module = _build_real_router()
            fake_client = _FakeTelegramClient(
                steps=[
                    RuntimeError("deliberate unexpected failure for logging check"),
                ]
            )
            service = TelegramService(config=config, client=fake_client, router=router)
            lines, sink_id = _capture_logs()
            try:
                start_result = service.start()
                self.assert_true(start_result.success, f"start() failed: {start_result.message}")
                ok = _wait_until(
                    lambda: any(
                        "Telegram poll loop encountered an unexpected error" in line
                        for line in lines
                    ),
                    timeout=5.0,
                )
                self.assert_true(
                    ok, "expected the new, distinct ERROR log message to be emitted"
                )
                self.assert_true(
                    any(
                        "deliberate unexpected failure for logging check" in line
                        for line in lines
                    ),
                    "expected the exception reason (str(exc)) to appear in the log line",
                )
            finally:
                service.stop()
                logger.remove(sink_id)

    # ---------- F. No sensitive-data leakage ----------

    def _test_no_sensitive_data_leaks_into_the_new_log_message(self) -> None:
        """A distinctive marker embedded in a message payload, but *not* in
        the raised exception's own text, must never reach the log via the
        new handler -- only `str(exc)` may appear.
        """
        marker = "SENSITIVE-MARKER-9f3ac21e"

        class _MarkerCarryingRouter:
            """Raises an exception whose str() excludes the marker, even
            though the router "saw" a message containing it -- proving the
            new handler logs only str(exc), never the raw message/update.
            """

            def __init__(self) -> None:
                self.seen_texts: list[str] = []

            def route(self, chat_id: int, text: str) -> CommandResult:
                self.seen_texts.append(text)
                raise RuntimeError("deliberate unexpected routing failure")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = _build_telegram_config(tmp_path)
            marker_router = _MarkerCarryingRouter()
            fake_client = _FakeTelegramClient(
                steps=[
                    [TelegramMessage(chat_id=1, text=marker, update_id=1)],
                ]
            )
            service = TelegramService(config=config, client=fake_client, router=marker_router)
            lines, sink_id = _capture_logs()
            try:
                start_result = service.start()
                self.assert_true(start_result.success, f"start() failed: {start_result.message}")
                ok = _wait_until(lambda: len(marker_router.seen_texts) >= 1, timeout=5.0)
                self.assert_true(ok, "expected the marker message to have reached route()")
                _wait_until(
                    lambda: any(
                        "Telegram poll loop encountered an unexpected error" in line
                        for line in lines
                    ),
                    timeout=5.0,
                )
                self.assert_false(
                    any(marker in line for line in lines),
                    "the sensitive marker must never appear in any log line "
                    "produced by the new exception handler",
                )
            finally:
                service.stop()
                logger.remove(sink_id)

    # ---------- G. Existing TelegramClientError behavior unchanged ----------

    def _test_existing_telegramclienterror_handling_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = _build_telegram_config(tmp_path)
            router, _module = _build_real_router()
            fake_client = _FakeTelegramClient(
                steps=[
                    TelegramClientError("deliberate simulated Bot API failure"),
                    [],
                ]
            )
            service = TelegramService(config=config, client=fake_client, router=router)
            lines, sink_id = _capture_logs()
            try:
                start_result = service.start()
                self.assert_true(start_result.success, f"start() failed: {start_result.message}")
                ok = _wait_until(
                    lambda: any("Telegram polling failed:" in line for line in lines),
                    timeout=5.0,
                )
                self.assert_true(
                    ok,
                    "expected the pre-existing 'Telegram polling failed: ...' "
                    "message to still fire for a TelegramClientError, unchanged",
                )
                self.assert_false(
                    any(
                        "Telegram poll loop encountered an unexpected error" in line
                        for line in lines
                    ),
                    "the new broad handler must not also fire for a "
                    "TelegramClientError already handled inside _poll_once()",
                )
                self.assert_true(
                    service._is_poll_loop_running(),  # noqa: SLF001
                    "the loop must continue after a TelegramClientError, "
                    "exactly as it did before this EP",
                )
            finally:
                service.stop()
                logger.remove(sink_id)

    # ---------- H. Shutdown ----------

    def _test_stop_still_terminates_cleanly_after_a_survived_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = _build_telegram_config(tmp_path)
            router, _module = _build_real_router()
            fake_client = _FakeTelegramClient(
                steps=[
                    RuntimeError("deliberate unexpected failure before stop()"),
                ]
            )
            service = TelegramService(config=config, client=fake_client, router=router)
            start_result = service.start()
            self.assert_true(start_result.success, f"start() failed: {start_result.message}")

            ok = _wait_until(lambda: fake_client.fetch_call_count >= 1, timeout=5.0)
            self.assert_true(ok, "expected the failing poll to have been attempted")

            started_stop = time.monotonic()
            stop_result = service.stop()
            stop_duration = time.monotonic() - started_stop

            self.assert_true(stop_result.success, f"stop() failed: {stop_result.message}")
            self.assert_true(
                stop_duration < 5.5,
                f"stop() took too long after a survived exception: {stop_duration:.2f}s",
            )
            self.assert_false(
                service._is_poll_loop_running(),  # noqa: SLF001
                "expected the polling thread to have fully stopped",
            )

    # ---------- I. No busy loop ----------

    def _test_no_busy_loop_after_a_failure(self) -> None:
        polling_interval = 0.1
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config = _build_telegram_config(tmp_path, polling_interval=polling_interval)
            router, _module = _build_real_router()
            fake_client = _FakeTelegramClient(
                steps=[
                    RuntimeError("deliberate unexpected failure #1"),
                    RuntimeError("deliberate unexpected failure #2"),
                    RuntimeError("deliberate unexpected failure #3"),
                ]
            )
            service = TelegramService(config=config, client=fake_client, router=router)
            start_result = service.start()
            self.assert_true(start_result.success, f"start() failed: {start_result.message}")
            try:
                ok = _wait_until(lambda: fake_client.fetch_call_count >= 3, timeout=5.0)
                self.assert_true(ok, "expected three failing poll attempts")
                gaps = [
                    b - a
                    for a, b in zip(
                        fake_client.fetch_call_times, fake_client.fetch_call_times[1:]
                    )
                ]
                self.assert_true(
                    all(gap >= polling_interval * 0.5 for gap in gaps),
                    f"poll attempts after a failure were spaced too tightly "
                    f"(possible busy-loop): {gaps!r}",
                )
            finally:
                service.stop()
