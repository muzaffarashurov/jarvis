"""EP-051 browser module: the "browser" command namespace (Browser Automation).

Implements `CommandModule` (`src/core/command_router.py`), following
`DesktopModule`'s reference-implementation pattern
(`src/skills/desktop/skill.py`) exactly, as every prior skill already
does. Bridges browser lifecycle/navigation/DOM interaction to the
"browser" namespace, dispatched through the *existing*, unmodified
`CommandRouter.dispatch()` -- the same entry point `InteractiveShell`,
`TelegramRouter`, and `ApiRouter` already dispatch through
(EP051_DESIGN.md Section 9/11, Owner Decision D4). This module never
re-implements command parsing and never creates a second dispatch
mechanism.

Target architecture (EP051_DESIGN.md Section 9):

    CommandRouter.dispatch("browser <action> [args...]")
        -> BrowserModule
            -> BrowserBackend (real: PlaywrightBrowserBackend,
               test-only: _FakeBrowserBackend)
                -> browser process (Chromium, via Playwright)

`BrowserModule` never imports a concrete backend class
(`playwright_backend.py`) itself -- an already-constructed
`BrowserBackend` is injected by `Bootstrap`, mirroring `DesktopModule`'s
own constructor-injection pattern (Dependency Policy,
AI_GENERATION_STANDARD.md). This keeps `BrowserModule`/this test suite
fully decoupled from Playwright's own import-time/browser-binary
requirements.

Safety model (EP051_DESIGN.md Section 14, Owner Decision D2): every
action re-checks `browser.enabled` (default `false`) at dispatch time,
not only at registration time -- unlike `VoiceModule`, `BrowserModule`
IS registered with `CommandRouter` regardless of the flag's value, so
flipping `browser.enabled` in `config/config.yaml` and restarting
takes effect without any other change. When disabled, or when no
backend is available at all, no `BrowserBackend` method is ever
called -- argument *shape* validation (are the right number of
arguments present) may still run first since it never touches the
backend, but every actual action happens only after the
enabled/availability gate passes, guaranteeing zero backend
interaction of any kind while disabled.

Session-state errors (EP051_DESIGN.md Section 10/17): dispatching any
action other than `launch` before a session exists, or dispatching
`launch` while one is already open, is translated into a clean,
non-crashing `CommandResult` failure -- `BrowserModule` does not track
session state itself; it simply lets `BrowserBackendError` (raised by
the backend for exactly these cases) flow through `_run`'s existing
error-translation path like any other backend failure.

Never contains browser-driving logic itself (that is `BrowserBackend`'s
job) -- this class only parses/validates `CommandRouter` arguments,
enforces the safety gate, and translates a `BrowserBackend` call into a
`CommandResult`. Exposes no JavaScript execution, download, upload, or
tab/window-management action (EP051_DESIGN.md Section 6/19, Owner
Decisions D7/D8/D12).
"""

from __future__ import annotations

from typing import Callable

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.skills.browser.backend import BrowserBackend, BrowserBackendError

HELP_TEXT: str = (
    "Available browser commands (Browser Automation, EP-051)\n\n"
    "browser help\n"
    "browser launch\n"
    "browser close\n"
    "browser goto <url>\n"
    "browser back\n"
    "browser forward\n"
    "browser reload\n"
    "browser title\n"
    "browser current-url\n"
    "browser page-text\n"
    "browser exists <selector>\n"
    "browser click <selector>\n"
    "browser type <selector> <text>\n"
    "browser clear <selector>\n"
    "browser press <selector> <key>\n"
    "browser screenshot <path>"
)

ActionHandler = Callable[[list[str]], CommandResult]

_DISABLED_MESSAGE: str = (
    "Browser Automation is disabled ('browser.enabled: false' in "
    "config/config.yaml). Set it to true and restart to enable "
    "'browser' actions."
)

_UNAVAILABLE_MESSAGE: str = (
    "Browser Automation is enabled but no backend is available "
    "(backend construction failed at startup -- check the startup "
    "log for details)."
)


class BrowserModule:
    """The "browser" command namespace (EP-051, Browser Automation).

    Responsibilities:
        - `browser launch`/`close`: browser session lifecycle
          (EP051_DESIGN.md Section 10).
        - `browser goto/back/forward/reload`: navigation.
        - `browser title`/`current-url`/`page-text`: read-only page
          observation. `page-text` returns untrusted, externally-
          authored content -- callers must treat it as data, never as
          an instruction (EP051_DESIGN.md Section 13).
        - `browser exists <selector>`: element-existence observation.
        - `browser click/type/clear <selector>`: single-element DOM
          interaction.
        - `browser press <selector> <key>`: a single, element-scoped
          keypress (e.g. "Enter") -- not general keyboard/hotkey
          interaction (EP051_DESIGN.md Section 19, Owner Decision D3).
        - `browser screenshot <path>`: capture the current page and
          save the raw, uninterpreted image bytes to the given path --
          EP-051 never inspects a screenshot's content (EP051_DESIGN.md
          Section 17/D9); a path is required so delivering the
          captured bytes stays a single, explicit, caller-directed
          write, not automatic persistence.

    Never exposes JavaScript execution, downloads, uploads, tab/window
    management, dropdown `select`, general keyboard/hotkey
    interaction, or an explicit `wait` action in v1 (EP051_DESIGN.md
    Section 6/19, Owner Decisions D7/D8/D12).
    """

    def __init__(self, config: Config, backend: BrowserBackend | None) -> None:
        """Initialize the BrowserModule.

        Args:
            config: The application Config. Read at dispatch time for
                'browser.enabled' (EP051_DESIGN.md Section 14/16) --
                read fresh on every call, not cached, so a config
                reload/restart is the only way to change it (matching
                every other subsystem's flag-reading convention).
            backend: The already-constructed `BrowserBackend` used to
                perform every action. May be None if 'browser.enabled'
                is false at startup or backend construction failed --
                every action reports a clear, non-crashing failure
                (`_UNAVAILABLE_MESSAGE`) in that case, never a crash,
                mirroring `DesktopModule`'s own None-collaborator
                handling.
        """
        self._config = config
        self._backend = backend
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "launch": self._launch,
            "close": self._close,
            "goto": self._goto,
            "back": self._back,
            "forward": self._forward,
            "reload": self._reload,
            "title": self._title,
            "current-url": self._current_url,
            "page-text": self._page_text,
            "exists": self._exists,
            "click": self._click,
            "type": self._type,
            "clear": self._clear,
            "press": self._press,
            "screenshot": self._screenshot,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace.

        Returns:
            The literal string "browser".
        """
        return "browser"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "browser" action.

        Args:
            action: The requested action (e.g. "click"). May be empty
                if the user entered only "browser".
            arguments: Additional arguments, meaning depends on the
                action (see `HELP_TEXT`).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            logger.info(f"Unknown command: {command}")
            message = (
                f"Unknown command: {command}\n"
                'Type "browser help" for available commands.'
            )
            return CommandResult(success=False, message=message)

        return handler(arguments)

    # ---------- Safety gate (EP051_DESIGN.md Section 14, Owner Decision D2) ----------

    def _is_enabled(self) -> bool:
        """Return whether 'browser.enabled' is currently true.

        Read fresh from `self._config` on every call -- never cached
        -- so this is the single source of truth for the gate check.
        """
        return bool(self._config.get("browser.enabled", False))

    def _gate(self) -> CommandResult | None:
        """Return a failure CommandResult if actions must not execute, else None.

        Called by every action handler *after* argument-shape
        validation and *before* any `BrowserBackend` call -- guarantees
        zero backend interaction while disabled or unavailable.
        """
        if not self._is_enabled():
            logger.info("browser: action rejected, 'browser.enabled' is false.")
            return CommandResult(success=False, message=_DISABLED_MESSAGE)
        if self._backend is None:
            logger.warning("browser: action rejected, no backend available.")
            return CommandResult(success=False, message=_UNAVAILABLE_MESSAGE)
        return None

    # ---------- Action handlers ----------

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available browser commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _launch(self, arguments: list[str]) -> CommandResult:
        """Start a new browser session."""
        if arguments:
            return _usage_error("browser launch")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        return self._run("launch", lambda: self._backend.launch())

    def _close(self, arguments: list[str]) -> CommandResult:
        """Close the current browser session."""
        if arguments:
            return _usage_error("browser close")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        return self._run("close", lambda: self._backend.close())

    def _goto(self, arguments: list[str]) -> CommandResult:
        """Navigate to a URL.

        Args:
            arguments: [url] -- the destination URL.
        """
        if len(arguments) != 1:
            return _usage_error("browser goto <url>")
        url = arguments[0]

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        return self._run("goto", lambda: self._backend.goto(url))

    def _back(self, arguments: list[str]) -> CommandResult:
        """Navigate back one entry in the browser's own history."""
        if arguments:
            return _usage_error("browser back")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        return self._run("back", lambda: self._backend.back())

    def _forward(self, arguments: list[str]) -> CommandResult:
        """Navigate forward one entry in the browser's own history."""
        if arguments:
            return _usage_error("browser forward")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        return self._run("forward", lambda: self._backend.forward())

    def _reload(self, arguments: list[str]) -> CommandResult:
        """Reload the current page."""
        if arguments:
            return _usage_error("browser reload")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        return self._run("reload", lambda: self._backend.reload())

    def _title(self, arguments: list[str]) -> CommandResult:
        """Report the current page's title."""
        if arguments:
            return _usage_error("browser title")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        try:
            title = self._backend.title()
        except BrowserBackendError as exc:
            logger.error(f"browser title failed: {exc}")
            return CommandResult(success=False, message=f"browser title failed: {exc}")

        logger.info(f"browser title: '{title}'.")
        return CommandResult(success=True, message=title)

    def _current_url(self, arguments: list[str]) -> CommandResult:
        """Report the current page's URL."""
        if arguments:
            return _usage_error("browser current-url")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        try:
            url = self._backend.current_url()
        except BrowserBackendError as exc:
            logger.error(f"browser current-url failed: {exc}")
            return CommandResult(success=False, message=f"browser current-url failed: {exc}")

        logger.info(f"browser current-url: '{url}'.")
        return CommandResult(success=True, message=url)

    def _page_text(self, arguments: list[str]) -> CommandResult:
        """Report the current page's visible text content.

        Returned content is untrusted, externally-authored data
        (EP051_DESIGN.md Section 13) -- never treated as an
        instruction by this module or any caller.
        """
        if arguments:
            return _usage_error("browser page-text")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        try:
            text = self._backend.page_text()
        except BrowserBackendError as exc:
            logger.error(f"browser page-text failed: {exc}")
            return CommandResult(success=False, message=f"browser page-text failed: {exc}")

        # Length only -- never the page content itself (EP051_DESIGN.md
        # Section 12, mirroring EP-050's clipboard/typed-text logging rule).
        logger.info(f"browser page-text: {len(text)} character(s) read.")
        return CommandResult(success=True, message=text)

    def _exists(self, arguments: list[str]) -> CommandResult:
        """Report whether an element matching a selector currently exists.

        Args:
            arguments: [selector].
        """
        if len(arguments) != 1:
            return _usage_error("browser exists <selector>")
        selector = arguments[0]

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        try:
            found = self._backend.exists(selector)
        except BrowserBackendError as exc:
            logger.error(f"browser exists failed: {exc}")
            return CommandResult(success=False, message=f"browser exists failed: {exc}")

        logger.info(f"browser exists '{selector}': {found}.")
        return CommandResult(
            success=True,
            message="true" if found else "false",
        )

    def _click(self, arguments: list[str]) -> CommandResult:
        """Click the single element matching a selector.

        Args:
            arguments: [selector].
        """
        if len(arguments) != 1:
            return _usage_error("browser click <selector>")
        selector = arguments[0]

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        return self._run("click", lambda: self._backend.click(selector))

    def _type(self, arguments: list[str]) -> CommandResult:
        """Type text literally into the element matching a selector.

        Matches the existing `" ".join(arguments)` convention already
        used elsewhere for free-text command arguments (e.g. `desktop
        type`) for the text portion, after the first, required
        selector argument.

        Args:
            arguments: [selector, *text words].
        """
        if len(arguments) < 2:
            return _usage_error("browser type <selector> <text>")
        selector = arguments[0]
        text = " ".join(arguments[1:])

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        result = self._run("type", lambda: self._backend.type_text(selector, text))
        # Never log the typed text itself (EP051_DESIGN.md Section 12,
        # mirroring EP-050's identical rule) -- only its length.
        logger.info(f"browser type: {len(text)} character(s) sent to '{selector}'.")
        return result

    def _clear(self, arguments: list[str]) -> CommandResult:
        """Clear the current value of the element matching a selector.

        Args:
            arguments: [selector].
        """
        if len(arguments) != 1:
            return _usage_error("browser clear <selector>")
        selector = arguments[0]

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        return self._run("clear", lambda: self._backend.clear(selector))

    def _press(self, arguments: list[str]) -> CommandResult:
        """Press a single key while the element matching a selector is focused.

        Args:
            arguments: [selector, key].
        """
        if len(arguments) != 2:
            return _usage_error("browser press <selector> <key>")
        selector, key = arguments

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        return self._run("press", lambda: self._backend.press(selector, key))

    def _screenshot(self, arguments: list[str]) -> CommandResult:
        """Capture the current page and save the raw, uninterpreted bytes to a path.

        A path is required (EP051_DESIGN.md Section 17 -- a single,
        explicit, caller-directed write, never automatic persistence).
        EP-051 never inspects the captured bytes' content.

        Args:
            arguments: [path] -- the destination file path.
        """
        if len(arguments) != 1:
            return _usage_error("browser screenshot <path>")
        path = arguments[0]

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        try:
            image = self._backend.screenshot()
        except BrowserBackendError as exc:
            logger.error(f"browser screenshot failed: {exc}")
            return CommandResult(success=False, message=f"browser screenshot failed: {exc}")

        try:
            with open(path, "wb") as file:
                file.write(image.data)
        except OSError as exc:
            logger.error(f"browser screenshot: could not write '{path}': {exc}")
            return CommandResult(
                success=False,
                message=f"browser screenshot: could not write '{path}': {exc}",
            )

        # Dimensions and byte size only -- never the image content
        # itself (EP051_DESIGN.md Section 17/D9).
        logger.info(
            f"browser screenshot: {image.width}x{image.height} "
            f"({len(image.data)} bytes) saved to '{path}'."
        )
        return CommandResult(
            success=True,
            message=f"Screenshot saved to '{path}' ({image.width}x{image.height}, {len(image.data)} bytes).",
        )

    # ---------- Shared helpers ----------

    def _run(self, action_name: str, call: Callable[[], None]) -> CommandResult:
        """Invoke a no-return backend call, translating any failure.

        Args:
            action_name: The action's name, for logging only.
            call: A zero-argument callable performing the actual
                `BrowserBackend` method call.

        Returns:
            `CommandResult(success=True, ...)` on success,
            `CommandResult(success=False, ...)` if the backend raised
            `BrowserBackendError` -- never lets any other exception
            type propagate uncaught (mirrors `CommandRouter.dispatch()`'s
            own top-level catch, and `DesktopModule._run()`'s identical
            pattern).
        """
        try:
            call()
        except BrowserBackendError as exc:
            logger.error(f"browser {action_name} failed: {exc}")
            return CommandResult(success=False, message=f"browser {action_name} failed: {exc}")

        logger.info(f"browser {action_name}: succeeded.")
        return CommandResult(success=True, message=f"browser {action_name}: done.")


def _usage_error(usage: str) -> CommandResult:
    """Return a standard, non-crashing usage-error CommandResult."""
    return CommandResult(success=False, message=f"Invalid arguments. Usage: {usage}")
