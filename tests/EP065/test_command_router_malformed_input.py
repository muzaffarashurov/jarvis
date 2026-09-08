"""EP-065 test suite: CommandRouter Malformed-Input Dispatch Safety.

Covers, per `EP065_DESIGN.md` Sections 11/14:
    1. `CommandRouter.dispatch()`'s containment of the `ValueError`
       `_tokenize()` raises for malformed (unbalanced) quoting.
    2. The new failure path's message/logging content -- distinct
       wording, and no raw command text in either the returned
       `CommandResult.message` or the log line (Owner Decision D4).
    3. Regression: `_tokenize()` itself is unchanged and still raises
       `ValueError` directly; well-formed quoting, Windows-path
       backslash handling, and the two pre-existing `dispatch()`
       failure paths ("Unknown module: ...", "Internal error while
       executing ...") are all byte-for-byte unchanged.
    4. `InteractiveShell.run()` survives a malformed line with no
       production change to `src/core/shell.py`.
    5. `TelegramService`'s polling loop survives a malformed message
       with no production change to any Telegram file.
    6. REST (`ApiRouter.dispatch_command()`) remains unaffected, by
       construction, with no production change to any REST file.

Self-contained per this repository's own per-EP test convention (no
import from `tests/EP002/` or any other EP test package) -- local
builder/fixture classes below are independent, EP-065-owned copies of
the kind of real objects `tests/EP002/test_shell.py` already uses for
`CommandRouter`, following `tests/EP061/test_scheduler_shutdown.py`'s
own "self-contained, no cross-EP import" precedent.
"""

from __future__ import annotations

import time
from unittest.mock import patch

from src.core.api.api_router import ApiRouter
from src.core.command_router import CommandResult, CommandRouter
from src.core.config import Config
from src.core.shell import InteractiveShell
from src.core.telegram.telegram_client import TelegramMessage
from src.core.telegram.telegram_router import TelegramRouter
from src.services.telegram_service import TelegramService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

# ================= Shared local fixtures =================


class _RecordingModule:
    """Minimal, real `CommandModule` implementation -- records every call.

    Independent, EP-065-owned copy of the kind of stub
    `tests/EP002/test_shell.py`'s own `_StubModule` already uses.
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


class _RaisingModule:
    """A `CommandModule` whose `execute()` always raises.

    Used to prove `module.execute()`'s existing exception-handling
    path (the "Internal error while executing ..." branch) is
    completely unaffected by this EP's new, separate branch.
    """

    def __init__(self, name: str = "boom") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        raise RuntimeError("simulated module defect")


class _ExitOnCommandModule:
    """A `CommandModule` whose `execute()` always requests shell exit.

    Used only by the `InteractiveShell` test below, to give
    `shell.run()` a normal, non-crashing way to end its loop after
    the malformed line has already been processed once.
    """

    def __init__(self, name: str = "system") -> None:
        self._name = name
        self.calls: list[tuple[str, list[str]]] = []

    @property
    def name(self) -> str:
        return self._name

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        self.calls.append((action, arguments))
        return CommandResult(success=True, message="", should_exit=True)


class _FakeTelegramClient:
    """Deterministic, test-only Telegram client -- no network, no real Bot API.

    Duck-typed to exactly the surface `TelegramService` calls
    (`connect`, `disconnect`, `is_connected`, `fetch_updates`,
    `send_message`), following `tests/EP051/test_browser.py`'s own
    `_FakeBrowserBackend` precedent (`EP065_DESIGN.md` Section 11).
    `fetch_updates()` returns one queued batch of `TelegramMessage`
    objects per call, then an empty list once the queue is exhausted,
    so a test can feed a malformed message followed by a well-formed
    one across two separate poll cycles.
    """

    def __init__(self, batches: list[list[TelegramMessage]]) -> None:
        self._batches = list(batches)
        self._connected = False
        self.sent_messages: list[tuple[int, str]] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def fetch_updates(self, timeout: int = 0) -> list[TelegramMessage]:
        if self._batches:
            return self._batches.pop(0)
        return []

    def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))


def _build_telegram_config(tmp_path, polling_interval: float = 0.05) -> Config:
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


@TestRegistry.register
class CommandRouterMalformedInputTest(BaseTest):
    """EP-065 regression suite (`NAME = "EP065"`)."""

    NAME = "EP065"

    def run(self):
        # ---------- CommandRouter-level: containment ----------
        self._test_tokenize_still_raises_valueerror_directly()
        self._test_dispatch_never_raises_for_unbalanced_double_quote()
        self._test_dispatch_never_raises_for_unbalanced_single_quote()
        self._test_dispatch_never_raises_for_bare_quote_character()
        self._test_dispatch_never_raises_for_multiple_non_pairing_quotes()

        # ---------- CommandRouter-level: message/logging semantics ----------
        self._test_malformed_input_result_message_names_syntax_error()
        self._test_malformed_input_does_not_log_raw_command_text()
        self._test_malformed_input_never_calls_module_execute()
        self._test_malformed_input_result_should_exit_is_false()
        self._test_repeated_malformed_input_is_idempotent()

        # ---------- CommandRouter-level: regressions ----------
        self._test_well_formed_quoted_input_still_works()
        self._test_windows_path_backslash_handling_still_works()
        self._test_unknown_module_path_unchanged()
        self._test_internal_error_path_unchanged_and_still_echoes_raw_input()

        # ---------- InteractiveShell: survival ----------
        self._test_shell_survives_malformed_line_and_continues()

        # ---------- TelegramService: survival ----------
        self._test_telegram_poll_loop_survives_malformed_message()

        # ---------- REST: unchanged / unaffected ----------
        self._test_rest_dispatch_command_immune_to_malformed_quoting()

        return self.result

    # ================= CommandRouter-level: containment =================

    def _test_tokenize_still_raises_valueerror_directly(self) -> None:
        """`_tokenize()` itself is unchanged: it still raises `ValueError`
        directly for malformed quoting. Containment happens only at
        `dispatch()`'s call site (Owner Decision D1/D2)."""
        try:
            CommandRouter._tokenize('bad "quote')  # noqa: SLF001
        except ValueError as exc:
            self.assert_true(
                "No closing quotation" in str(exc),
                f"unexpected _tokenize() ValueError text: {exc!r}",
            )
        else:
            self.assert_true(
                False, "_tokenize() should still raise ValueError for malformed quoting"
            )

    def _test_dispatch_never_raises_for_unbalanced_double_quote(self) -> None:
        router = CommandRouter()
        try:
            result = router.dispatch('system status "oops')
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"dispatch() raised: {exc!r}")
            return
        self.assert_true(isinstance(result, CommandResult))
        self.assert_false(result.success)

    def _test_dispatch_never_raises_for_unbalanced_single_quote(self) -> None:
        router = CommandRouter()
        try:
            result = router.dispatch("system status 'oops")
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"dispatch() raised: {exc!r}")
            return
        self.assert_false(result.success)

    def _test_dispatch_never_raises_for_bare_quote_character(self) -> None:
        router = CommandRouter()
        for bare in ('"', "'"):
            try:
                result = router.dispatch(bare)
            except Exception as exc:  # noqa: BLE001
                self.assert_true(False, f"dispatch({bare!r}) raised: {exc!r}")
                continue
            self.assert_false(result.success)

    def _test_dispatch_never_raises_for_multiple_non_pairing_quotes(self) -> None:
        router = CommandRouter()
        try:
            result = router.dispatch('a "b" "c')
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"dispatch() raised: {exc!r}")
            return
        self.assert_false(result.success)

    # ================= CommandRouter-level: message/logging semantics =================

    def _test_malformed_input_result_message_names_syntax_error(self) -> None:
        router = CommandRouter()
        result = router.dispatch('system status "oops')
        self.assert_true(result.message.startswith("Invalid command syntax:"))
        self.assert_true("No closing quotation" in result.message)
        self.assert_false("Unknown module" in result.message)
        self.assert_false("Internal error" in result.message)
        # Owner Decision D4 (revised): the raw command text itself must
        # never appear in the returned message.
        self.assert_false("oops" in result.message)

    def _test_malformed_input_does_not_log_raw_command_text(self) -> None:
        from loguru import logger

        captured: list[str] = []
        handler_id = logger.add(lambda record: captured.append(str(record)), level="ERROR")
        try:
            router = CommandRouter()
            router.dispatch('login "sk-super-secret-marker')
        finally:
            logger.remove(handler_id)

        joined = "\n".join(captured)
        self.assert_true(
            "No closing quotation" in joined,
            "expected the parser's own exception reason to appear in the log",
        )
        self.assert_false(
            "sk-super-secret-marker" in joined,
            "raw command text must never appear in the new log message",
        )

    def _test_malformed_input_never_calls_module_execute(self) -> None:
        router = CommandRouter()
        module = _RecordingModule("system")
        router.register(module)
        router.dispatch('system "oops')
        self.assert_equal(len(module.calls), 0)

    def _test_malformed_input_result_should_exit_is_false(self) -> None:
        router = CommandRouter()
        result = router.dispatch('system "oops')
        self.assert_false(result.should_exit)

    def _test_repeated_malformed_input_is_idempotent(self) -> None:
        router = CommandRouter()
        module = _RecordingModule("stub")
        router.register(module)
        before_names = list(router.module_names)

        results = [router.dispatch('stub "oops') for _ in range(3)]
        self.assert_equal(results[0].success, results[1].success)
        self.assert_equal(results[0].message, results[1].message)
        self.assert_equal(results[1].message, results[2].message)
        self.assert_equal(len(module.calls), 0)
        self.assert_equal(list(router.module_names), before_names)

    # ================= CommandRouter-level: regressions =================

    def _test_well_formed_quoted_input_still_works(self) -> None:
        router = CommandRouter()
        module = _RecordingModule("stub")
        router.register(module)
        result = router.dispatch('stub ping "hello world"')
        self.assert_true(result.success)
        self.assert_equal(module.calls, [("ping", ["hello world"])])

    def _test_windows_path_backslash_handling_still_works(self) -> None:
        router = CommandRouter()
        module = _RecordingModule("stub")
        router.register(module)
        result = router.dispatch(r"stub open C:\Temp\file.txt")
        self.assert_true(result.success)
        self.assert_equal(module.calls, [("open", [r"C:\Temp\file.txt"])])

    def _test_unknown_module_path_unchanged(self) -> None:
        router = CommandRouter()
        result = router.dispatch("nosuchmodule help")
        self.assert_false(result.success)
        self.assert_equal(
            result.message,
            "Unknown module: nosuchmodule\n"
            'Type "system help" for available commands.',
        )

    def _test_internal_error_path_unchanged_and_still_echoes_raw_input(self) -> None:
        router = CommandRouter()
        router.register(_RaisingModule("boom"))
        raw = "boom detonate"
        result = router.dispatch(raw)
        self.assert_false(result.success)
        self.assert_equal(
            result.message, f"Internal error while executing '{raw}'."
        )

    # ================= InteractiveShell: survival =================

    def _test_shell_survives_malformed_line_and_continues(self) -> None:
        router = CommandRouter()
        exit_module = _ExitOnCommandModule("system")
        router.register(exit_module)
        shell = InteractiveShell(router=router)

        with patch("builtins.input", side_effect=['system status "oops', "system exit"]):
            try:
                shell.run()
            except Exception as exc:  # noqa: BLE001
                self.assert_true(False, f"InteractiveShell.run() raised: {exc!r}")
                return

        self.assert_true(True, "InteractiveShell.run() returned normally")
        self.assert_equal(
            len(exit_module.calls),
            1,
            "the second, valid line should have reached the module exactly once, "
            "proving the loop genuinely continued past the malformed first line",
        )

    # ================= TelegramService: survival =================

    def _test_telegram_poll_loop_survives_malformed_message(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            config = _build_telegram_config(Path(tmp))
            router = CommandRouter()
            router.register(_RecordingModule("stub"))
            telegram_router = TelegramRouter(command_router=router, allowed_chat_ids=[1])

            fake_client = _FakeTelegramClient(
                batches=[
                    [TelegramMessage(chat_id=1, text='stub "oops', update_id=1)],
                    [TelegramMessage(chat_id=1, text="stub ping", update_id=2)],
                ]
            )
            service = TelegramService(config=config, client=fake_client, router=telegram_router)
            start_result = service.start()
            self.assert_true(start_result.success, f"start() failed: {start_result.message}")

            try:
                # Allow several poll cycles (interval=0.05s) to consume
                # both queued batches.
                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline and len(fake_client.sent_messages) < 2:
                    time.sleep(0.05)

                self.assert_true(
                    service.status().running,
                    "telegram-poll thread must survive a malformed message",
                )
                self.assert_equal(
                    len(fake_client.sent_messages),
                    2,
                    "both the malformed and the well-formed message should have "
                    "produced a reply",
                )
                if len(fake_client.sent_messages) >= 2:
                    first_chat_id, first_reply = fake_client.sent_messages[0]
                    second_chat_id, second_reply = fake_client.sent_messages[1]
                    self.assert_equal(first_chat_id, 1)
                    self.assert_true(first_reply.startswith("Invalid command syntax:"))
                    self.assert_false("oops" in first_reply)
                    self.assert_equal(second_chat_id, 1)
                    self.assert_equal(second_reply, "executed:ping")
            finally:
                service.stop()

    # ================= REST: unchanged / unaffected =================

    def _test_rest_dispatch_command_immune_to_malformed_quoting(self) -> None:
        router = CommandRouter()
        module = _RecordingModule("echo")
        router.register(module)
        api_router = ApiRouter(command_router=router)

        malformed_value = 'oops"unbalanced'
        try:
            result = api_router.dispatch_command("echo", "ping", [malformed_value])
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"ApiRouter.dispatch_command() raised: {exc!r}")
            return

        self.assert_true(result.success)
        self.assert_equal(len(module.calls), 1)
        self.assert_equal(module.calls[0], ("ping", [malformed_value]))
