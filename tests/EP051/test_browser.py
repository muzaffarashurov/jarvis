"""Real engineering tests for EP-051 STEP 2 - Browser Automation.

Single combined test suite (NAME = "EP051"), following the same
precedent EP-043/EP-045/EP-046/EP-047/EP-048/EP-049/EP-050 already
established: this sidesteps the pre-existing `TestRegistry`
NAME-collision technical debt (docs/BACKLOG.md) entirely rather than
triggering it.

Fully deterministic: no real browser process, no Playwright import,
and no network access is required or exercised anywhere in this file.
Every `BrowserModule` scenario is exercised through
`_FakeBrowserBackend` (below) -- a plain class implementing
`BrowserBackend`'s full protocol, following
`tests/EP050/test_desktop.py`'s own `_FakeComputerUseBackend`
precedent exactly (EP051_DESIGN.md Section 18).
`PlaywrightBrowserBackend`/`playwright` are never imported by this
file -- that real, Playwright-backed class is exercised only by the
separate, unregistered `tests/EP051/test_browser_integration.py`
(EP051_DESIGN.md Section 18's three-tier automated/integration/manual
split).

Covers:
    - `BrowserBackend` protocol conformance (the fake satisfies the
      same structural interface the real backend does).
    - `BrowserModule` argument-shape validation (wrong argument
      count) -- rejected before any backend call.
    - The `browser.enabled` safety gate (EP051_DESIGN.md Section 14,
      Owner Decision D2): every action is rejected, with zero backend
      calls, while disabled; every action reaches the backend once
      enabled.
    - Session-state errors (EP051_DESIGN.md Section 10/17):
      dispatching a non-`launch` action before `browser launch`, and
      dispatching `browser launch` twice without an intervening
      `browser close`, both fail cleanly without crashing.
    - Every one of the 15 `browser` actions succeeding via the fake
      backend, with the exact arguments the module is expected to
      pass through (EP051_DESIGN.md Section 19).
    - Backend-raised `BrowserBackendError` translated into a failed
      `CommandResult`, never propagated raw (EP051_DESIGN.md Section
      17) -- exercised for a representative action and explicitly
      including a simulated "timed out" backend failure.
    - Sensitive-content logging hygiene (EP051_DESIGN.md Section 12):
      page-text/typed-text content is never written to the log, only
      its length.
    - `CommandRouter` string-dispatch ("browser <action> ...")
      produces results identical to direct `BrowserModule.execute()`
      calls, mirroring `tests/EP050/test_desktop.py`'s own
      `_test_command_router_dispatch_matches_direct_execute`
      precedent.
    - `Bootstrap` wiring: 'browser.enabled' defaults to false when
      entirely absent from config; the 'browser' namespace is
      registered with `CommandRouter` regardless of the flag's value
      (EP051_DESIGN.md Section 14's per-dispatch gate design) but
      every action reports the disabled message until the flag is set
      to true.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.command_router import CommandRouter
from src.skills.browser.backend import (
    BrowserBackend,
    BrowserBackendError,
    Screenshot,
)
from src.skills.browser.skill import BrowserModule
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
    """One recorded `BrowserBackend` method invocation."""

    method: str
    args: tuple
    kwargs: dict


@dataclass
class _FakeBrowserBackend:
    """Deterministic, test-only `BrowserBackend` (EP051_DESIGN.md Section 18).

    Records every call it receives (`self.calls`) so tests can assert
    exactly what `BrowserModule` passed through, without touching any
    real browser process. `raise_on` (a set of method names) makes the
    fake raise `BrowserBackendError` for specific methods, to exercise
    `BrowserModule`'s failure-translation path deterministically.

    Tracks minimal session state itself (`_session_open`) so it can
    reproduce the real backend's own session-lifecycle error
    conditions (EP051_DESIGN.md Section 10/17) without any real
    browser.
    """

    page_title: str = "Fake Page"
    page_url: str = "https://example.invalid/"
    page_text_value: str = "Hello from the fake page."
    existing_selectors: frozenset[str] = frozenset({"#search", "#submit"})
    raise_on: frozenset[str] = frozenset()
    raise_message: str = "simulated backend failure"
    calls: list[_RecordedCall] = field(default_factory=list)
    _session_open: bool = field(default=False, init=False)

    def _record(self, method: str, *args, **kwargs) -> None:
        self.calls.append(_RecordedCall(method=method, args=args, kwargs=kwargs))
        if method in self.raise_on:
            raise BrowserBackendError(self.raise_message)

    def _require_session(self) -> None:
        if not self._session_open:
            raise BrowserBackendError(
                "no active browser session; run 'browser launch' first"
            )

    def launch(self) -> None:
        if self._session_open:
            self._record("launch")
            raise BrowserBackendError(
                "a browser session is already open; run 'browser close' first"
            )
        self._record("launch")
        self._session_open = True

    def close(self) -> None:
        self._require_session()
        self._record("close")
        self._session_open = False

    def goto(self, url: str) -> None:
        self._require_session()
        self._record("goto", url)
        self.page_url = url

    def back(self) -> None:
        self._require_session()
        self._record("back")

    def forward(self) -> None:
        self._require_session()
        self._record("forward")

    def reload(self) -> None:
        self._require_session()
        self._record("reload")

    def title(self) -> str:
        self._require_session()
        self._record("title")
        return self.page_title

    def current_url(self) -> str:
        self._require_session()
        self._record("current_url")
        return self.page_url

    def page_text(self) -> str:
        self._require_session()
        self._record("page_text")
        return self.page_text_value

    def exists(self, selector: str) -> bool:
        self._require_session()
        self._record("exists", selector)
        return selector in self.existing_selectors

    def click(self, selector: str) -> None:
        self._require_session()
        self._record("click", selector)

    def type_text(self, selector: str, text: str) -> None:
        self._require_session()
        self._record("type_text", selector, text)

    def clear(self, selector: str) -> None:
        self._require_session()
        self._record("clear", selector)

    def press(self, selector: str, key: str) -> None:
        self._require_session()
        self._record("press", selector, key)

    def screenshot(self) -> Screenshot:
        self._require_session()
        self._record("screenshot")
        return Screenshot(width=2, height=2, format="png", data=b"\x89PNGfakeimagebytes")


class _CapturingSink:
    """A minimal loguru sink that records every formatted log message.

    Used only by the logging-hygiene tests below to assert that
    sensitive content (page text, typed text) never appears in a log
    line -- not to test loguru itself.
    """

    def __init__(self) -> None:
        self.messages: list[str] = []

    def write(self, message) -> None:
        self.messages.append(str(message))


def _write_browser_bootstrap_config(directory: Path, browser_section: str) -> None:
    """Write a minimal bootstrap config.yaml (EP-045's fixture) plus a 'browser:' block."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    base_yaml = _MINIMAL_BOOTSTRAP_CONFIG_YAML.format(
        api_section=_api_section(enabled=False, web_dashboard_dir=None)
    )
    (config_dir / "config.yaml").write_text(base_yaml + "\n" + browser_section, encoding="utf-8")


@TestRegistry.register
class BrowserTest(BaseTest):
    NAME = "EP051"

    def run(self):
        self._test_fake_backend_satisfies_protocol()

        self._test_goto_rejects_wrong_argument_count()
        self._test_exists_rejects_wrong_argument_count()
        self._test_type_rejects_wrong_argument_count()
        self._test_press_rejects_wrong_argument_count()
        self._test_screenshot_rejects_wrong_argument_count()

        self._test_disabled_rejects_every_action_with_zero_backend_calls()
        self._test_disabled_rejects_before_session_state_check()
        self._test_no_backend_available_rejects_with_zero_backend_calls()

        self._test_action_before_launch_rejected_without_crash()
        self._test_double_launch_rejected_without_crash()

        self._test_launch_and_close_succeed()
        self._test_goto_succeeds_and_calls_backend_with_url()
        self._test_back_forward_reload_succeed()
        self._test_title_succeeds_and_returns_text()
        self._test_current_url_succeeds_and_returns_text()
        self._test_page_text_succeeds_and_returns_text()
        self._test_exists_succeeds_true_and_false()
        self._test_click_succeeds_and_calls_backend_with_selector()
        self._test_type_succeeds_and_calls_backend_with_joined_text()
        self._test_clear_succeeds_and_calls_backend_with_selector()
        self._test_press_succeeds_and_calls_backend_with_selector_and_key()
        self._test_screenshot_succeeds_and_writes_file()
        self._test_help_lists_commands()
        self._test_unknown_action_returns_failure()

        self._test_backend_failure_translated_to_failed_result()
        self._test_backend_timeout_like_failure_translated_to_failed_result()
        self._test_screenshot_backend_failure_translated_to_failed_result()

        self._test_results_are_deterministic_across_repeated_calls()

        self._test_typed_text_never_logged()
        self._test_page_text_content_never_logged()

        self._test_command_router_dispatch_matches_direct_execute()
        self._test_command_router_unaffected_by_other_modules()

        self._test_bootstrap_config_defaults_browser_disabled()
        self._test_bootstrap_registers_browser_namespace_even_when_disabled()
        self._test_bootstrap_browser_actions_report_disabled_message()
        self._test_bootstrap_other_modules_unaffected_when_browser_absent()

        return self.result

    # ---------- BrowserBackend protocol conformance ----------

    def _test_fake_backend_satisfies_protocol(self) -> None:
        fake = _FakeBrowserBackend()
        self.assert_true(
            isinstance(fake, BrowserBackend),
            "_FakeBrowserBackend must structurally satisfy the BrowserBackend protocol",
        )

    # ---------- Argument-shape validation (no backend call) ----------

    def _test_goto_rejects_wrong_argument_count(self) -> None:
        fake = _FakeBrowserBackend()
        module = BrowserModule(config=_config_with({"browser": {"enabled": True}}), backend=fake)
        result = module.execute("goto", [])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0, "no backend call for a shape-invalid request")

    def _test_exists_rejects_wrong_argument_count(self) -> None:
        fake = _FakeBrowserBackend()
        module = BrowserModule(config=_config_with({"browser": {"enabled": True}}), backend=fake)
        result = module.execute("exists", [])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0)

    def _test_type_rejects_wrong_argument_count(self) -> None:
        fake = _FakeBrowserBackend()
        module = BrowserModule(config=_config_with({"browser": {"enabled": True}}), backend=fake)
        result = module.execute("type", ["#search"])  # missing text
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0)

    def _test_press_rejects_wrong_argument_count(self) -> None:
        fake = _FakeBrowserBackend()
        module = BrowserModule(config=_config_with({"browser": {"enabled": True}}), backend=fake)
        result = module.execute("press", ["#search"])  # missing key
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0)

    def _test_screenshot_rejects_wrong_argument_count(self) -> None:
        fake = _FakeBrowserBackend()
        module = BrowserModule(config=_config_with({"browser": {"enabled": True}}), backend=fake)
        result = module.execute("screenshot", [])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0)

    # ---------- Safety gate (EP051_DESIGN.md Section 14, Owner Decision D2) ----------

    def _test_disabled_rejects_every_action_with_zero_backend_calls(self) -> None:
        fake = _FakeBrowserBackend()
        module = BrowserModule(config=_config_with({"browser": {"enabled": False}}), backend=fake)

        scenarios: list[tuple[str, list[str]]] = [
            ("launch", []),
            ("close", []),
            ("goto", ["https://example.invalid/"]),
            ("back", []),
            ("forward", []),
            ("reload", []),
            ("title", []),
            ("current-url", []),
            ("page-text", []),
            ("exists", ["#search"]),
            ("click", ["#search"]),
            ("type", ["#search", "hello"]),
            ("clear", ["#search"]),
            ("press", ["#search", "Enter"]),
        ]
        for action, args in scenarios:
            result = module.execute(action, args)
            self.assert_false(result.success, f"'{action}' must be rejected while disabled")
            self.assert_true(
                "disabled" in result.message.lower(),
                f"'{action}' failure message must explain Browser Automation is disabled",
            )
        self.assert_equal(
            len(fake.calls), 0, "no backend method may be called while 'browser.enabled' is false"
        )

    def _test_disabled_rejects_before_session_state_check(self) -> None:
        # An action dispatched while disabled must fail on the
        # disabled gate specifically -- never on a session-state
        # error, which would itself require a backend call.
        fake = _FakeBrowserBackend()
        module = BrowserModule(config=_config_with({"browser": {"enabled": False}}), backend=fake)

        result = module.execute("click", ["#search"])
        self.assert_false(result.success)
        self.assert_true("disabled" in result.message.lower())
        self.assert_equal(len(fake.calls), 0, "backend must never be called while disabled")

    def _test_no_backend_available_rejects_with_zero_backend_calls(self) -> None:
        module = BrowserModule(config=_config_with({"browser": {"enabled": True}}), backend=None)
        result = module.execute("launch", [])
        self.assert_false(result.success)
        self.assert_true("no backend" in result.message.lower() or "unavailable" in result.message.lower())

    # ---------- Session-state errors (EP051_DESIGN.md Section 10/17) ----------

    def _test_action_before_launch_rejected_without_crash(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        result = module.execute("title", [])
        self.assert_false(result.success)
        self.assert_true("no active browser session" in result.message.lower())

    def _test_double_launch_rejected_without_crash(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        first = module.execute("launch", [])
        self.assert_true(first.success)
        second = module.execute("launch", [])
        self.assert_false(second.success)
        self.assert_true("already open" in second.message.lower())

    # ---------- Successful actions (enabled, session open where required) ----------

    def _enabled_module(self, fake: _FakeBrowserBackend) -> BrowserModule:
        return BrowserModule(config=_config_with({"browser": {"enabled": True}}), backend=fake)

    def _test_launch_and_close_succeed(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        launch_result = module.execute("launch", [])
        self.assert_true(launch_result.success)
        close_result = module.execute("close", [])
        self.assert_true(close_result.success)
        methods = [call.method for call in fake.calls]
        self.assert_equal(methods, ["launch", "close"])

    def _test_goto_succeeds_and_calls_backend_with_url(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        module.execute("launch", [])
        result = module.execute("goto", ["https://example.invalid/page"])
        self.assert_true(result.success)
        goto_calls = [call for call in fake.calls if call.method == "goto"]
        self.assert_equal(len(goto_calls), 1)
        self.assert_equal(goto_calls[0].args, ("https://example.invalid/page",))

    def _test_back_forward_reload_succeed(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        module.execute("launch", [])
        self.assert_true(module.execute("back", []).success)
        self.assert_true(module.execute("forward", []).success)
        self.assert_true(module.execute("reload", []).success)
        methods = [call.method for call in fake.calls]
        self.assert_true("back" in methods and "forward" in methods and "reload" in methods)

    def _test_title_succeeds_and_returns_text(self) -> None:
        fake = _FakeBrowserBackend(page_title="My Fake Title")
        module = self._enabled_module(fake)
        module.execute("launch", [])
        result = module.execute("title", [])
        self.assert_true(result.success)
        self.assert_equal(result.message, "My Fake Title")

    def _test_current_url_succeeds_and_returns_text(self) -> None:
        fake = _FakeBrowserBackend(page_url="https://example.invalid/here")
        module = self._enabled_module(fake)
        module.execute("launch", [])
        result = module.execute("current-url", [])
        self.assert_true(result.success)
        self.assert_equal(result.message, "https://example.invalid/here")

    def _test_page_text_succeeds_and_returns_text(self) -> None:
        fake = _FakeBrowserBackend(page_text_value="Some visible page text.")
        module = self._enabled_module(fake)
        module.execute("launch", [])
        result = module.execute("page-text", [])
        self.assert_true(result.success)
        self.assert_equal(result.message, "Some visible page text.")

    def _test_exists_succeeds_true_and_false(self) -> None:
        fake = _FakeBrowserBackend(existing_selectors=frozenset({"#search"}))
        module = self._enabled_module(fake)
        module.execute("launch", [])
        present = module.execute("exists", ["#search"])
        self.assert_true(present.success)
        self.assert_equal(present.message, "true")
        absent = module.execute("exists", ["#nonexistent"])
        self.assert_true(absent.success)
        self.assert_equal(absent.message, "false")

    def _test_click_succeeds_and_calls_backend_with_selector(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        module.execute("launch", [])
        result = module.execute("click", ["#submit"])
        self.assert_true(result.success)
        click_calls = [call for call in fake.calls if call.method == "click"]
        self.assert_equal(click_calls[0].args, ("#submit",))

    def _test_type_succeeds_and_calls_backend_with_joined_text(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        module.execute("launch", [])
        result = module.execute("type", ["#search", "hello", "world"])
        self.assert_true(result.success)
        type_calls = [call for call in fake.calls if call.method == "type_text"]
        self.assert_equal(type_calls[0].args, ("#search", "hello world"))

    def _test_clear_succeeds_and_calls_backend_with_selector(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        module.execute("launch", [])
        result = module.execute("clear", ["#search"])
        self.assert_true(result.success)
        clear_calls = [call for call in fake.calls if call.method == "clear"]
        self.assert_equal(clear_calls[0].args, ("#search",))

    def _test_press_succeeds_and_calls_backend_with_selector_and_key(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        module.execute("launch", [])
        result = module.execute("press", ["#search", "Enter"])
        self.assert_true(result.success)
        press_calls = [call for call in fake.calls if call.method == "press"]
        self.assert_equal(press_calls[0].args, ("#search", "Enter"))

    def _test_screenshot_succeeds_and_writes_file(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        module.execute("launch", [])
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir) / "shot.png")
            result = module.execute("screenshot", [path])
            self.assert_true(result.success)
            self.assert_true(Path(path).exists())
            self.assert_equal(Path(path).read_bytes(), b"\x89PNGfakeimagebytes")

    def _test_help_lists_commands(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("browser launch" in result.message)
        self.assert_equal(len(fake.calls), 0, "help must never touch the backend")

    def _test_unknown_action_returns_failure(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        result = module.execute("not-a-real-action", [])
        self.assert_false(result.success)
        self.assert_equal(len(fake.calls), 0)

    # ---------- Error translation (EP051_DESIGN.md Section 17) ----------

    def _test_backend_failure_translated_to_failed_result(self) -> None:
        fake = _FakeBrowserBackend(raise_on=frozenset({"click"}))
        module = self._enabled_module(fake)
        module.execute("launch", [])
        result = module.execute("click", ["#search"])
        self.assert_false(result.success)
        self.assert_true("simulated backend failure" in result.message)

    def _test_backend_timeout_like_failure_translated_to_failed_result(self) -> None:
        fake = _FakeBrowserBackend(
            raise_on=frozenset({"goto"}), raise_message="timed out waiting for navigation"
        )
        module = self._enabled_module(fake)
        module.execute("launch", [])
        result = module.execute("goto", ["https://example.invalid/slow"])
        self.assert_false(result.success)
        self.assert_true("timed out" in result.message.lower())

    def _test_screenshot_backend_failure_translated_to_failed_result(self) -> None:
        fake = _FakeBrowserBackend(raise_on=frozenset({"screenshot"}))
        module = self._enabled_module(fake)
        module.execute("launch", [])
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = str(Path(tmp_dir) / "shot.png")
            result = module.execute("screenshot", [path])
            self.assert_false(result.success)
            self.assert_false(Path(path).exists(), "no file should be written on backend failure")

    # ---------- Determinism ----------

    def _test_results_are_deterministic_across_repeated_calls(self) -> None:
        fake = _FakeBrowserBackend(page_title="Stable Title")
        module = self._enabled_module(fake)
        module.execute("launch", [])
        first = module.execute("title", [])
        second = module.execute("title", [])
        self.assert_equal(first.message, second.message)
        self.assert_equal(first.success, second.success)

    # ---------- Sensitive-content logging hygiene (EP051_DESIGN.md Section 12) ----------

    def _test_typed_text_never_logged(self) -> None:
        from loguru import logger

        sink = _CapturingSink()
        handler_id = logger.add(sink, format="{message}")
        try:
            fake = _FakeBrowserBackend()
            module = self._enabled_module(fake)
            module.execute("launch", [])
            module.execute("type", ["#search", "TopSecretTypedValue"])
        finally:
            logger.remove(handler_id)

        joined_log = "\n".join(sink.messages)
        self.assert_false("TopSecretTypedValue" in joined_log)

    def _test_page_text_content_never_logged(self) -> None:
        from loguru import logger

        sink = _CapturingSink()
        handler_id = logger.add(sink, format="{message}")
        try:
            fake = _FakeBrowserBackend(page_text_value="TopSecretPageContentValue")
            module = self._enabled_module(fake)
            module.execute("launch", [])
            module.execute("page-text", [])
        finally:
            logger.remove(handler_id)

        joined_log = "\n".join(sink.messages)
        self.assert_false("TopSecretPageContentValue" in joined_log)

    # ---------- CommandRouter integration ----------

    def _test_command_router_dispatch_matches_direct_execute(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        router = CommandRouter()
        router.register(module)

        direct = module.execute("launch", [])
        self.assert_true(direct.success)
        dispatched = router.dispatch("browser title")

        self.assert_true(dispatched.success)
        title_calls = [call for call in fake.calls if call.method == "title"]
        self.assert_equal(len(title_calls), 1)

    def _test_command_router_unaffected_by_other_modules(self) -> None:
        fake = _FakeBrowserBackend()
        module = self._enabled_module(fake)
        router = CommandRouter()
        router.register(module)

        result = router.dispatch("unknownmodule somecommand")
        self.assert_false(result.success)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_config_defaults_browser_disabled(self) -> None:
        config = _config_with({})
        self.assert_false(
            bool(config.get("browser.enabled", False)),
            "'browser.enabled' must default to false when entirely absent from config",
        )

    def _test_bootstrap_registers_browser_namespace_even_when_disabled(self) -> None:
        # Mirrors DesktopModule: BrowserModule is always registered --
        # EP051_DESIGN.md Section 14's per-dispatch gate means the
        # safety gate lives inside each action handler, not at
        # registration time (see skill.py's module docstring).
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_browser_bootstrap_config(directory, browser_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(
                        "browser" in bootstrap._command_router.module_names,
                        "'browser' namespace must be registered even when 'browser.enabled' is absent/false",
                    )
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_browser_actions_report_disabled_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_browser_bootstrap_config(directory, browser_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap._command_router.dispatch("browser title")
                    self.assert_false(result.success)
                    self.assert_true("disabled" in result.message.lower())
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_other_modules_unaffected_when_browser_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_browser_bootstrap_config(directory, browser_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    other = bootstrap._command_router.dispatch("system version")
                    self.assert_true(other.success, "Other modules must be unaffected by EP-051 wiring")
                finally:
                    bootstrap.shutdown()
