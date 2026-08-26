"""Real engineering tests for EP-050 STEP 2 - Computer Use.

Single combined test suite (NAME = "EP050"), following the same
precedent EP-043/EP-045/EP-046/EP-047/EP-048/EP-049 already
established: this sidesteps the pre-existing `TestRegistry`
NAME-collision technical debt (docs/BACKLOG.md) entirely rather than
triggering it.

Fully deterministic: no real mouse, keyboard, screen, PyAutoGUI
import, or Windows GUI session is required or exercised anywhere in
this file. Every `DesktopModule` scenario is exercised through
`_FakeComputerUseBackend` (below) -- a plain class implementing
`ComputerUseBackend`'s full protocol, following
`tests/EP046/test_voice.py`'s own `_FakeSpeechToTextEngine`/
`_FakeAudioCapture` precedent exactly (EP050_DESIGN.md Section 25).
`WindowsComputerUseBackend`/`pyautogui` are never imported by this
file -- that real, PyAutoGUI-backed class is exercised only by the
separate, unregistered `tests/EP050/test_desktop_windows_integration.py`
(EP050_DESIGN.md Section 25's three-tier automated/integration/manual
split).

Covers:
    - `ComputerUseBackend` protocol conformance (the fake satisfies
      the same structural interface the real backend does).
    - `DesktopModule` argument-shape validation (wrong argument
      count, non-integer coordinates, unrecognized key/button names)
      -- rejected before any backend call.
    - The `desktop.enabled` safety gate (EP050_DESIGN.md Section 16/
      20/32.8): every action is rejected, with zero backend calls,
      while disabled; every action reaches the backend once enabled.
    - Coordinate bounds validation against `screen_size()`
      (EP050_DESIGN.md Section 17).
    - Every one of the 13 `desktop` actions succeeding via the fake
      backend, with the exact arguments the module is expected to
      pass through.
    - Backend-raised `ComputerUseBackendError` translated into a
      failed `CommandResult`, never propagated raw (EP050_DESIGN.md
      Section 21) -- exercised for a representative action and
      explicitly including a simulated "timed out" backend failure,
      demonstrating the error model's generality even though EP-050
      defines no distinct timeout state of its own (synchronous,
      single-call actions only, EP050_DESIGN.md Section 20/21).
    - Sensitive-content logging hygiene (EP050_DESIGN.md Section 19):
      clipboard/typed-text content is never written to the log,
      only its length.
    - `CommandRouter` string-dispatch ("desktop <action> ...")
      produces results identical to direct `DesktopModule.execute()`
      calls, mirroring `tests/EP046/test_voice.py`'s own
      `_test_voice_module_listen_matches_direct_dispatch` precedent.
    - `Bootstrap` wiring: 'desktop.enabled' defaults to false when
      entirely absent from config; the 'desktop' namespace is
      registered with `CommandRouter` regardless of the flag's value
      (EP050_DESIGN.md Section 16's per-dispatch gate design, unlike
      `VoiceModule`'s registration-time gate) but every action
      reports the disabled message until the flag is set to true.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.command_router import CommandRouter
from src.skills.desktop.backend import (
    ComputerUseBackend,
    ComputerUseBackendError,
    CursorPosition,
    Screenshot,
    ScreenSize,
)
from src.skills.desktop.skill import DesktopModule
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry
from tests.EP045.test_web_dashboard import (
    _MINIMAL_BOOTSTRAP_CONFIG_YAML,
    _ChdirGuard,
    _api_section,
)
from tests.EP046.test_voice import _config_with


@dataclass
class _RecordedCall:
    """One recorded `ComputerUseBackend` method invocation."""

    method: str
    args: tuple
    kwargs: dict


class _FakeComputerUseBackend:
    """Deterministic, test-only `ComputerUseBackend` (EP050_DESIGN.md Section 25).

    Records every call it receives (`self.calls`) so tests can assert
    exactly what `DesktopModule` passed through, without touching any
    real mouse, keyboard, screen, or clipboard. `raise_on` (a set of
    method names) makes the fake raise `ComputerUseBackendError` for
    specific methods, to exercise `DesktopModule`'s failure-
    translation path deterministically.
    """

    def __init__(
        self,
        screen_size: tuple[int, int] = (1920, 1080),
        cursor: tuple[int, int] = (100, 100),
        clipboard_text: str = "",
        active_window: str = "Notepad",
        focus_result: bool = True,
        raise_on: frozenset[str] = frozenset(),
        raise_message: str = "simulated backend failure",
    ) -> None:
        self.calls: list[_RecordedCall] = []
        self._screen_size = ScreenSize(*screen_size)
        self._cursor = CursorPosition(*cursor)
        self._clipboard = clipboard_text
        self._active_window = active_window
        self._focus_result = focus_result
        self._raise_on = raise_on
        self._raise_message = raise_message

    def _record(self, method: str, *args, **kwargs) -> None:
        self.calls.append(_RecordedCall(method=method, args=args, kwargs=kwargs))
        if method in self._raise_on:
            raise ComputerUseBackendError(self._raise_message)

    def move_mouse(self, x: int, y: int) -> None:
        self._record("move_mouse", x, y)

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        self._record("click", x, y, button=button, double=double)

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None:
        self._record("scroll", amount, x=x, y=y)

    def type_text(self, text: str) -> None:
        self._record("type_text", text)

    def press_key(self, key: str) -> None:
        self._record("press_key", key)

    def read_clipboard(self) -> str:
        self._record("read_clipboard")
        return self._clipboard

    def write_clipboard(self, text: str) -> None:
        self._record("write_clipboard", text)
        self._clipboard = text

    def screenshot(self) -> Screenshot:
        self._record("screenshot")
        return Screenshot(width=2, height=2, format="png", data=b"\x89PNGfakeimagebytes")

    def cursor_position(self) -> CursorPosition:
        self._record("cursor_position")
        return self._cursor

    def screen_size(self) -> ScreenSize:
        self._record("screen_size")
        return self._screen_size

    def active_window_title(self) -> str:
        self._record("active_window_title")
        return self._active_window

    def focus_window(self, title: str) -> bool:
        self._record("focus_window", title)
        return self._focus_result


class _CapturingSink:
    """A minimal loguru sink that records every formatted log message.

    Used only by the logging-hygiene tests below to assert that
    sensitive content (clipboard text, typed text) never appears in
    a log line -- not to test loguru itself.
    """

    def __init__(self) -> None:
        self.messages: list[str] = []

    def write(self, message) -> None:
        self.messages.append(str(message))


def _write_desktop_bootstrap_config(directory: Path, desktop_section: str) -> None:
    """Write a minimal bootstrap config.yaml (EP-045's fixture) plus a 'desktop:' block."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base_yaml = _MINIMAL_BOOTSTRAP_CONFIG_YAML.format(
        api_section=_api_section(enabled=False, web_dashboard_dir=None)
    )
    (config_dir / "config.yaml").write_text(base_yaml + "\n" + desktop_section, encoding="utf-8")


@TestRegistry.register
class DesktopTest(BaseTest):
    NAME = "EP050"

    def run(self):
        self._test_fake_backend_satisfies_protocol()

        self._test_move_rejects_wrong_argument_count()
        self._test_move_rejects_non_integer_coordinates()
        self._test_click_rejects_unknown_button()
        self._test_key_rejects_unknown_key_name()
        self._test_scroll_rejects_wrong_argument_count()

        self._test_disabled_rejects_every_action_with_zero_backend_calls()
        self._test_disabled_rejects_before_argument_bounds_check_but_after_shape_check()
        self._test_no_backend_available_rejects_with_zero_backend_calls()

        self._test_move_out_of_bounds_rejected_without_executing()
        self._test_click_out_of_bounds_rejected_without_executing()

        self._test_move_succeeds_and_calls_backend_with_expected_args()
        self._test_click_succeeds_with_default_button()
        self._test_click_succeeds_with_right_button_and_double()
        self._test_scroll_succeeds_with_and_without_position()
        self._test_type_succeeds_and_calls_backend_with_joined_text()
        self._test_key_succeeds_with_single_key()
        self._test_key_succeeds_with_hotkey_combination()
        self._test_read_clipboard_succeeds_and_returns_text()
        self._test_write_clipboard_succeeds_and_calls_backend_with_joined_text()
        self._test_screenshot_succeeds_and_writes_file()
        self._test_screenshot_rejects_wrong_argument_count()
        self._test_cursor_succeeds()
        self._test_screen_size_succeeds()
        self._test_active_window_succeeds()
        self._test_active_window_reports_no_active_window()
        self._test_focus_succeeds()
        self._test_focus_reports_no_match()
        self._test_help_lists_commands()
        self._test_unknown_action_returns_failure()

        self._test_backend_failure_translated_to_failed_result()
        self._test_backend_timeout_like_failure_translated_to_failed_result()
        self._test_screenshot_backend_failure_translated_to_failed_result()

        self._test_results_are_deterministic_across_repeated_calls()

        self._test_typed_text_never_logged()
        self._test_clipboard_content_never_logged()

        self._test_command_router_dispatch_matches_direct_execute()
        self._test_command_router_unaffected_by_other_modules()

        self._test_bootstrap_config_defaults_desktop_disabled()
        self._test_bootstrap_registers_desktop_namespace_even_when_disabled()
        self._test_bootstrap_desktop_actions_report_disabled_message()
        self._test_bootstrap_other_modules_unaffected_when_desktop_absent()

        return self.result

    # ---------- ComputerUseBackend protocol conformance ----------

    def _test_fake_backend_satisfies_protocol(self) -> None:
        fake = _FakeComputerUseBackend()
        self.assert_true(
            isinstance(fake, ComputerUseBackend),
            "_FakeComputerUseBackend must structurally satisfy the ComputerUseBackend protocol",
        )

    # ---------- Argument-shape validation (no backend call) ----------

    def _test_move_rejects_wrong_argument_count(self) -> None:
        fake = _FakeComputerUseBackend()
        module = DesktopModule(config=_config_with({"desktop": {"enabled": True}}), backend=fake)
        result = module.execute("move", ["100"])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0, "no backend call for a shape-invalid request")

    def _test_move_rejects_non_integer_coordinates(self) -> None:
        fake = _FakeComputerUseBackend()
        module = DesktopModule(config=_config_with({"desktop": {"enabled": True}}), backend=fake)
        result = module.execute("move", ["abc", "100"])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0)

    def _test_click_rejects_unknown_button(self) -> None:
        fake = _FakeComputerUseBackend()
        module = DesktopModule(config=_config_with({"desktop": {"enabled": True}}), backend=fake)
        result = module.execute("click", ["10", "10", "nonexistent-button"])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0)

    def _test_key_rejects_unknown_key_name(self) -> None:
        fake = _FakeComputerUseBackend()
        module = DesktopModule(config=_config_with({"desktop": {"enabled": True}}), backend=fake)
        result = module.execute("key", ["totallynotarealkey"])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0)

    def _test_scroll_rejects_wrong_argument_count(self) -> None:
        fake = _FakeComputerUseBackend()
        module = DesktopModule(config=_config_with({"desktop": {"enabled": True}}), backend=fake)
        result = module.execute("scroll", ["10", "20"])  # 2 args -- must be 1 or 3
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0)

    # ---------- Safety gate (EP050_DESIGN.md Section 16/20/32.8) ----------

    def _test_disabled_rejects_every_action_with_zero_backend_calls(self) -> None:
        fake = _FakeComputerUseBackend()
        module = DesktopModule(config=_config_with({"desktop": {"enabled": False}}), backend=fake)

        scenarios: list[tuple[str, list[str]]] = [
            ("move", ["10", "10"]),
            ("click", ["10", "10"]),
            ("scroll", ["1"]),
            ("type", ["hello"]),
            ("key", ["enter"]),
            ("read-clipboard", []),
            ("write-clipboard", ["hello"]),
            ("cursor", []),
            ("screen-size", []),
            ("active-window", []),
            ("focus", ["Notepad"]),
        ]
        for action, args in scenarios:
            result = module.execute(action, args)
            self.assert_false(result.success, f"'{action}' must be rejected while disabled")
            self.assert_true(
                "disabled" in result.message.lower(),
                f"'{action}' failure message must explain Computer Use is disabled",
            )
        self.assert_equal(
            len(fake.calls), 0, "no backend method may be called while 'desktop.enabled' is false"
        )

    def _test_disabled_rejects_before_argument_bounds_check_but_after_shape_check(self) -> None:
        # A shape-invalid request must fail on shape grounds even
        # while disabled (no backend call either way) -- a
        # shape-*valid* request while disabled must fail on the
        # disabled gate specifically (not attempt a bounds check,
        # which would itself require a backend call).
        fake = _FakeComputerUseBackend()
        module = DesktopModule(config=_config_with({"desktop": {"enabled": False}}), backend=fake)

        shape_invalid = module.execute("move", ["not-a-number", "10"])
        self.assert_false(shape_invalid.success)

        shape_valid = module.execute("move", ["10", "10"])
        self.assert_false(shape_valid.success)
        self.assert_true("disabled" in shape_valid.message.lower())
        self.assert_equal(len(fake.calls), 0, "screen_size() must never be called while disabled")

    def _test_no_backend_available_rejects_with_zero_backend_calls(self) -> None:
        module = DesktopModule(config=_config_with({"desktop": {"enabled": True}}), backend=None)
        result = module.execute("move", ["10", "10"])
        self.assert_false(result.success)
        self.assert_true("no backend" in result.message.lower() or "unavailable" in result.message.lower())

    # ---------- Bounds validation (EP050_DESIGN.md Section 17) ----------

    def _test_move_out_of_bounds_rejected_without_executing(self) -> None:
        fake = _FakeComputerUseBackend(screen_size=(1920, 1080))
        module = DesktopModule(config=_config_with({"desktop": {"enabled": True}}), backend=fake)
        result = module.execute("move", ["5000", "5000"])
        self.assert_false(result.success)
        self.assert_true("bounds" in result.message.lower())
        move_calls = [call for call in fake.calls if call.method == "move_mouse"]
        self.assert_equal(len(move_calls), 0, "move_mouse must never be called for out-of-bounds input")

    def _test_click_out_of_bounds_rejected_without_executing(self) -> None:
        fake = _FakeComputerUseBackend(screen_size=(1920, 1080))
        module = DesktopModule(config=_config_with({"desktop": {"enabled": True}}), backend=fake)
        result = module.execute("click", ["-1", "10"])
        self.assert_false(result.success)
        click_calls = [call for call in fake.calls if call.method == "click"]
        self.assert_equal(len(click_calls), 0)

    # ---------- Successful actions (enabled, in-bounds) ----------

    def _enabled_module(self, fake: _FakeComputerUseBackend) -> DesktopModule:
        return DesktopModule(config=_config_with({"desktop": {"enabled": True}}), backend=fake)

    def _test_move_succeeds_and_calls_backend_with_expected_args(self) -> None:
        fake = _FakeComputerUseBackend(screen_size=(1920, 1080))
        module = self._enabled_module(fake)
        result = module.execute("move", ["500", "300"])
        self.assert_true(result.success)
        move_calls = [call for call in fake.calls if call.method == "move_mouse"]
        self.assert_equal(len(move_calls), 1)
        self.assert_equal(move_calls[0].args, (500, 300))

    def _test_click_succeeds_with_default_button(self) -> None:
        fake = _FakeComputerUseBackend(screen_size=(1920, 1080))
        module = self._enabled_module(fake)
        result = module.execute("click", ["500", "300"])
        self.assert_true(result.success)
        click_calls = [call for call in fake.calls if call.method == "click"]
        self.assert_equal(len(click_calls), 1)
        self.assert_equal(click_calls[0].args, (500, 300))
        self.assert_equal(click_calls[0].kwargs, {"button": "left", "double": False})

    def _test_click_succeeds_with_right_button_and_double(self) -> None:
        fake = _FakeComputerUseBackend(screen_size=(1920, 1080))
        module = self._enabled_module(fake)
        result = module.execute("click", ["500", "300", "right", "double"])
        self.assert_true(result.success)
        click_calls = [call for call in fake.calls if call.method == "click"]
        self.assert_equal(click_calls[0].kwargs, {"button": "right", "double": True})

    def _test_scroll_succeeds_with_and_without_position(self) -> None:
        fake = _FakeComputerUseBackend(screen_size=(1920, 1080))
        module = self._enabled_module(fake)

        result_no_pos = module.execute("scroll", ["5"])
        self.assert_true(result_no_pos.success)

        result_with_pos = module.execute("scroll", ["-5", "100", "200"])
        self.assert_true(result_with_pos.success)

        scroll_calls = [call for call in fake.calls if call.method == "scroll"]
        self.assert_equal(len(scroll_calls), 2)
        self.assert_equal(scroll_calls[0].args, (5,))
        self.assert_equal(scroll_calls[0].kwargs, {"x": None, "y": None})
        self.assert_equal(scroll_calls[1].args, (-5,))
        self.assert_equal(scroll_calls[1].kwargs, {"x": 100, "y": 200})

    def _test_type_succeeds_and_calls_backend_with_joined_text(self) -> None:
        fake = _FakeComputerUseBackend()
        module = self._enabled_module(fake)
        result = module.execute("type", ["hello", "there"])
        self.assert_true(result.success)
        type_calls = [call for call in fake.calls if call.method == "type_text"]
        self.assert_equal(type_calls[0].args, ("hello there",))

    def _test_key_succeeds_with_single_key(self) -> None:
        fake = _FakeComputerUseBackend()
        module = self._enabled_module(fake)
        result = module.execute("key", ["enter"])
        self.assert_true(result.success)
        key_calls = [call for call in fake.calls if call.method == "press_key"]
        self.assert_equal(key_calls[0].args, ("enter",))

    def _test_key_succeeds_with_hotkey_combination(self) -> None:
        fake = _FakeComputerUseBackend()
        module = self._enabled_module(fake)
        result = module.execute("key", ["ctrl+c"])
        self.assert_true(result.success)
        key_calls = [call for call in fake.calls if call.method == "press_key"]
        self.assert_equal(key_calls[0].args, ("ctrl+c",))

    def _test_read_clipboard_succeeds_and_returns_text(self) -> None:
        fake = _FakeComputerUseBackend(clipboard_text="secret-value")
        module = self._enabled_module(fake)
        result = module.execute("read-clipboard", [])
        self.assert_true(result.success)
        self.assert_equal(result.message, "secret-value")

    def _test_write_clipboard_succeeds_and_calls_backend_with_joined_text(self) -> None:
        fake = _FakeComputerUseBackend()
        module = self._enabled_module(fake)
        result = module.execute("write-clipboard", ["new", "value"])
        self.assert_true(result.success)
        write_calls = [call for call in fake.calls if call.method == "write_clipboard"]
        self.assert_equal(write_calls[0].args, ("new value",))

    def _test_screenshot_succeeds_and_writes_file(self) -> None:
        fake = _FakeComputerUseBackend()
        module = self._enabled_module(fake)
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir) / "shot.png")
            result = module.execute("screenshot", [path])
            self.assert_true(result.success)
            self.assert_true(Path(path).exists())
            self.assert_equal(Path(path).read_bytes(), b"\x89PNGfakeimagebytes")

    def _test_screenshot_rejects_wrong_argument_count(self) -> None:
        fake = _FakeComputerUseBackend()
        module = self._enabled_module(fake)
        result = module.execute("screenshot", [])
        self.assert_false(result.success)
        screenshot_calls = [call for call in fake.calls if call.method == "screenshot"]
        self.assert_equal(len(screenshot_calls), 0)

    def _test_cursor_succeeds(self) -> None:
        fake = _FakeComputerUseBackend(cursor=(42, 84))
        module = self._enabled_module(fake)
        result = module.execute("cursor", [])
        self.assert_true(result.success)
        self.assert_true("42" in result.message and "84" in result.message)

    def _test_screen_size_succeeds(self) -> None:
        fake = _FakeComputerUseBackend(screen_size=(1280, 720))
        module = self._enabled_module(fake)
        result = module.execute("screen-size", [])
        self.assert_true(result.success)
        self.assert_true("1280" in result.message and "720" in result.message)

    def _test_active_window_succeeds(self) -> None:
        fake = _FakeComputerUseBackend(active_window="My Editor")
        module = self._enabled_module(fake)
        result = module.execute("active-window", [])
        self.assert_true(result.success)
        self.assert_true("My Editor" in result.message)

    def _test_active_window_reports_no_active_window(self) -> None:
        fake = _FakeComputerUseBackend(active_window="")
        module = self._enabled_module(fake)
        result = module.execute("active-window", [])
        self.assert_true(result.success)
        self.assert_true("no active window" in result.message.lower())

    def _test_focus_succeeds(self) -> None:
        fake = _FakeComputerUseBackend(focus_result=True)
        module = self._enabled_module(fake)
        result = module.execute("focus", ["My", "Editor"])
        self.assert_true(result.success)
        focus_calls = [call for call in fake.calls if call.method == "focus_window"]
        self.assert_equal(focus_calls[0].args, ("My Editor",))

    def _test_focus_reports_no_match(self) -> None:
        fake = _FakeComputerUseBackend(focus_result=False)
        module = self._enabled_module(fake)
        result = module.execute("focus", ["Nonexistent"])
        self.assert_false(result.success)
        self.assert_true("no window" in result.message.lower())

    def _test_help_lists_commands(self) -> None:
        fake = _FakeComputerUseBackend()
        module = DesktopModule(config=_config_with({"desktop": {"enabled": False}}), backend=fake)
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("desktop move" in result.message)
        self.assert_true("desktop click" in result.message)

    def _test_unknown_action_returns_failure(self) -> None:
        fake = _FakeComputerUseBackend()
        module = self._enabled_module(fake)
        result = module.execute("not-a-real-action", [])
        self.assert_false(result.success)

    # ---------- Backend failure translation (EP050_DESIGN.md Section 21) ----------

    def _test_backend_failure_translated_to_failed_result(self) -> None:
        fake = _FakeComputerUseBackend(screen_size=(1920, 1080), raise_on=frozenset({"move_mouse"}))
        module = self._enabled_module(fake)
        result = module.execute("move", ["10", "10"])
        self.assert_false(result.success)
        self.assert_true("simulated backend failure" in result.message)

    def _test_backend_timeout_like_failure_translated_to_failed_result(self) -> None:
        # EP-050 defines no distinct TIMEOUT state (EP050_DESIGN.md
        # Section 21 -- synchronous, single-call actions only); a
        # backend that raises ComputerUseBackendError for any reason,
        # including a simulated hang/timeout, is handled identically
        # to any other backend failure.
        fake = _FakeComputerUseBackend(
            raise_on=frozenset({"read_clipboard"}), raise_message="operation timed out"
        )
        module = self._enabled_module(fake)
        result = module.execute("read-clipboard", [])
        self.assert_false(result.success)
        self.assert_true("timed out" in result.message.lower())

    def _test_screenshot_backend_failure_translated_to_failed_result(self) -> None:
        fake = _FakeComputerUseBackend(raise_on=frozenset({"screenshot"}))
        module = self._enabled_module(fake)
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir) / "shot.png")
            result = module.execute("screenshot", [path])
            self.assert_false(result.success)
            self.assert_false(Path(path).exists(), "no file must be written when capture itself fails")

    # ---------- Determinism ----------

    def _test_results_are_deterministic_across_repeated_calls(self) -> None:
        fake = _FakeComputerUseBackend(cursor=(7, 9))
        module = self._enabled_module(fake)
        first = module.execute("cursor", [])
        second = module.execute("cursor", [])
        self.assert_equal(first.success, second.success)
        self.assert_equal(first.message, second.message)

    # ---------- Logging hygiene (EP050_DESIGN.md Section 19) ----------

    def _test_typed_text_never_logged(self) -> None:
        from loguru import logger

        sink = _CapturingSink()
        handler_id = logger.add(sink, format="{message}")
        try:
            fake = _FakeComputerUseBackend()
            module = self._enabled_module(fake)
            secret_text = "MySuperSecretPassword123"
            module.execute("type", [secret_text])
        finally:
            logger.remove(handler_id)

        joined_log = "\n".join(sink.messages)
        self.assert_false(
            "MySuperSecretPassword123" in joined_log,
            "typed text content must never appear in a log line",
        )

    def _test_clipboard_content_never_logged(self) -> None:
        from loguru import logger

        sink = _CapturingSink()
        handler_id = logger.add(sink, format="{message}")
        try:
            fake = _FakeComputerUseBackend(clipboard_text="TopSecretClipboardValue")
            module = self._enabled_module(fake)
            module.execute("read-clipboard", [])
            module.execute("write-clipboard", ["AnotherSecretValue"])
        finally:
            logger.remove(handler_id)

        joined_log = "\n".join(sink.messages)
        self.assert_false("TopSecretClipboardValue" in joined_log)
        self.assert_false("AnotherSecretValue" in joined_log)

    # ---------- CommandRouter integration ----------

    def _test_command_router_dispatch_matches_direct_execute(self) -> None:
        fake = _FakeComputerUseBackend(screen_size=(1920, 1080))
        module = self._enabled_module(fake)
        router = CommandRouter()
        router.register(module)

        direct = module.execute("move", ["10", "20"])
        dispatched = router.dispatch("desktop move 10 20")

        self.assert_equal(direct.success, dispatched.success)
        # Two separate move_mouse calls are expected (one per
        # invocation above) -- both with the same arguments.
        move_calls = [call for call in fake.calls if call.method == "move_mouse"]
        self.assert_equal(len(move_calls), 2)
        self.assert_equal(move_calls[0].args, move_calls[1].args)

    def _test_command_router_unaffected_by_other_modules(self) -> None:
        fake = _FakeComputerUseBackend()
        module = self._enabled_module(fake)
        router = CommandRouter()
        router.register(module)

        result = router.dispatch("unknownmodule somecommand")
        self.assert_false(result.success)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_config_defaults_desktop_disabled(self) -> None:
        config = _config_with({})
        self.assert_false(
            bool(config.get("desktop.enabled", False)),
            "'desktop.enabled' must default to false when entirely absent from config",
        )

    def _test_bootstrap_registers_desktop_namespace_even_when_disabled(self) -> None:
        # Unlike VoiceModule (registered only when at least one of
        # its own flags is true), DesktopModule is always registered
        # -- EP050_DESIGN.md Section 20's per-dispatch GATE_CHECK
        # means the safety gate lives inside each action handler, not
        # at registration time (see skill.py's module docstring).
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_desktop_bootstrap_config(directory, desktop_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(
                        "desktop" in bootstrap._command_router.module_names,
                        "'desktop' namespace must be registered even when 'desktop.enabled' is absent/false",
                    )
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_desktop_actions_report_disabled_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_desktop_bootstrap_config(directory, desktop_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap._command_router.dispatch("desktop cursor")
                    self.assert_false(result.success)
                    self.assert_true("disabled" in result.message.lower())
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_other_modules_unaffected_when_desktop_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_desktop_bootstrap_config(directory, desktop_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    other = bootstrap._command_router.dispatch("system version")
                    self.assert_true(other.success, "Other modules must be unaffected by EP-050 wiring")
                finally:
                    bootstrap.shutdown()
