"""EP-050 desktop module: the "desktop" command namespace (Computer Use).

Implements `CommandModule` (`src/core/command_router.py`), following
`SystemModule`'s reference-implementation pattern
(`src/skills/system/skill.py`) exactly as every prior skill
(`voice`, `git`, `email`, ...) already does. Bridges raw OS input
(mouse/keyboard/clipboard/screen observation) to the "desktop"
namespace, dispatched through the *existing*, unmodified
`CommandRouter.dispatch()` -- the same entry point `InteractiveShell`,
`TelegramRouter`, and `ApiRouter` already dispatch through
(EP050_DESIGN.md Section 9/32.2). This module never re-implements
command parsing and never creates a second dispatch mechanism.

Target architecture (EP050_DESIGN.md Section 9):

    CommandRouter.dispatch("desktop <action> [args...]")
        -> DesktopModule
            -> ComputerUseBackend (real: WindowsComputerUseBackend,
               test-only: _FakeComputerUseBackend)
                -> OS

`DesktopModule` never imports a concrete backend class
(`windows_backend.py`) itself -- an already-constructed
`ComputerUseBackend` is injected by `Bootstrap`, mirroring
`VoiceModule`'s own constructor-injection pattern
(Dependency Policy, AI_GENERATION_STANDARD.md). This keeps
`DesktopModule`/this test suite fully decoupled from PyAutoGUI's own
import-time environment requirements (EP050_DESIGN.md Section 24 --
`pyautogui` itself needs a real display and is never imported by this
file).

Safety model (EP050_DESIGN.md Section 16/20, Owner Decision D2,
Section 32.8): every action re-checks `desktop.enabled` (default
`false`) at dispatch time, not only at registration time -- unlike
`VoiceModule`, `DesktopModule` IS registered with `CommandRouter`
regardless of the flag's value, so flipping `desktop.enabled` in
`config/config.yaml` and restarting takes effect without any other
change. When disabled, or when no backend is available at all, no
`ComputerUseBackend` method is ever called (VALIDATING -> GATE_CHECK
-> EXECUTING, EP050_DESIGN.md Section 20) -- argument *shape*
validation (are the right number of arguments present, do
coordinates parse as integers, is a key/button name recognized) may
still run first since it never touches the backend, but coordinate
*bounds* validation (which needs `backend.screen_size()`) and every
actual action happen only after the enabled/availability gate passes,
guaranteeing zero backend interaction of any kind while disabled.

Never contains OS-input logic itself (that is `ComputerUseBackend`'s
job) -- this class only parses/validates `CommandRouter` arguments,
enforces the safety gate, and translates a `ComputerUseBackend` call
into a `CommandResult`.
"""

from __future__ import annotations

from typing import Callable

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.skills.desktop.backend import (
    KNOWN_BUTTONS,
    KNOWN_KEYS,
    ComputerUseBackend,
    ComputerUseBackendError,
)

HELP_TEXT: str = (
    "Available desktop commands (Computer Use, EP-050)\n\n"
    "desktop help\n"
    "desktop move <x> <y>\n"
    "desktop click <x> <y> [left|right|middle] [double]\n"
    "desktop scroll <amount> [x] [y]\n"
    "desktop type <text>\n"
    "desktop key <key|key+key+...>\n"
    "desktop read-clipboard\n"
    "desktop write-clipboard <text>\n"
    "desktop screenshot <path>\n"
    "desktop cursor\n"
    "desktop screen-size\n"
    "desktop active-window\n"
    "desktop focus <window title>"
)

ActionHandler = Callable[[list[str]], CommandResult]

_DISABLED_MESSAGE: str = (
    "Computer Use is disabled ('desktop.enabled: false' in "
    "config/config.yaml). Set it to true and restart to enable "
    "'desktop' actions."
)

_UNAVAILABLE_MESSAGE: str = (
    "Computer Use is enabled but no backend is available (backend "
    "construction failed at startup -- check the startup log for "
    "details)."
)


class DesktopModule:
    """The "desktop" command namespace (EP-050, Computer Use).

    Responsibilities:
        - `desktop move/click/scroll`: raw mouse input.
        - `desktop type/key`: raw keyboard input.
        - `desktop read-clipboard`/`write-clipboard`: OS clipboard
          text access.
        - `desktop screenshot <path>`: capture the screen and save
          the raw, uninterpreted image bytes to the given path --
          EP-050 never inspects a screenshot's content
          (EP050_DESIGN.md Section 18); a path is required so
          delivering the captured bytes stays a single, explicit,
          caller-directed write, not automatic persistence
          (EP050_DESIGN.md Section 19).
        - `desktop cursor`/`screen-size`/`active-window`: basic,
          read-only screen/window observation.
        - `desktop focus <title>`: bring a window to the foreground
          by (sub-)title match -- the only window-management
          primitive in v1 (EP050_DESIGN.md Section 8.1, Owner
          Decision D6; full window management is deferred).

    Never launches a process/application/file/URL (that remains
    `src/core/execution/`'s job, EP-003 -- EP050_DESIGN.md Section
    14/15) and never performs shell/code execution of any kind
    (EP050_DESIGN.md Section 15 -- typed text is always sent
    literally, never interpreted).
    """

    def __init__(self, config: Config, backend: ComputerUseBackend | None) -> None:
        """Initialize the DesktopModule.

        Args:
            config: The application Config. Read at dispatch time for
                'desktop.enabled' (EP050_DESIGN.md Section 16/22) --
                read fresh on every call, not cached, so a config
                reload/restart is the only way to change it (matching
                every other subsystem's flag-reading convention).
            backend: The already-constructed `ComputerUseBackend`
                used to perform every action. May be None if
                'desktop.enabled' is false at startup or backend
                construction failed (EP050_DESIGN.md Section 10) --
                every action reports a clear, non-crashing failure
                (`_UNAVAILABLE_MESSAGE`) in that case, never a crash,
                mirroring `VoiceModule`'s own None-collaborator
                handling.
        """
        self._config = config
        self._backend = backend
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "move": self._move,
            "click": self._click,
            "scroll": self._scroll,
            "type": self._type,
            "key": self._key,
            "read-clipboard": self._read_clipboard,
            "write-clipboard": self._write_clipboard,
            "screenshot": self._screenshot,
            "cursor": self._cursor,
            "screen-size": self._screen_size,
            "active-window": self._active_window,
            "focus": self._focus,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace.

        Returns:
            The literal string "desktop".
        """
        return "desktop"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "desktop" action.

        Args:
            action: The requested action (e.g. "click"). May be empty
                if the user entered only "desktop".
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
                'Type "desktop help" for available commands.'
            )
            return CommandResult(success=False, message=message)

        return handler(arguments)

    # ---------- Safety gate (EP050_DESIGN.md Section 16/20) ----------

    def _is_enabled(self) -> bool:
        """Return whether 'desktop.enabled' is currently true.

        Read fresh from `self._config` on every call -- never cached
        -- so this is the single source of truth for the GATE_CHECK
        state (EP050_DESIGN.md Section 20).
        """
        return bool(self._config.get("desktop.enabled", False))

    def _gate(self) -> CommandResult | None:
        """Return a failure CommandResult if actions must not execute, else None.

        Called by every action handler *after* argument-shape
        validation and *before* any `ComputerUseBackend` call
        (including `backend.screen_size()` for bounds-checking) --
        guarantees zero backend interaction while disabled or
        unavailable (task requirement: "No partial execution may
        occur before the enabled check").
        """
        if not self._is_enabled():
            logger.info("desktop: action rejected, 'desktop.enabled' is false.")
            return CommandResult(success=False, message=_DISABLED_MESSAGE)
        if self._backend is None:
            logger.warning("desktop: action rejected, no backend available.")
            return CommandResult(success=False, message=_UNAVAILABLE_MESSAGE)
        return None

    # ---------- Action handlers ----------

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available desktop commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _move(self, arguments: list[str]) -> CommandResult:
        """Move the mouse to an absolute (x, y) screen position.

        Args:
            arguments: [x, y] -- both required integers.
        """
        if len(arguments) != 2:
            return _usage_error("desktop move <x> <y>")

        parsed = _parse_ints(arguments)
        if parsed is None:
            return _usage_error("desktop move <x> <y> (x/y must be integers)")
        x, y = parsed

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        bounds_failure = self._check_bounds(x, y)
        if bounds_failure is not None:
            return bounds_failure

        return self._run("move", lambda: self._backend.move_mouse(x, y))

    def _click(self, arguments: list[str]) -> CommandResult:
        """Move the mouse to (x, y) and click.

        Args:
            arguments: [x, y, button?, "double"?] -- x/y required
                integers; an optional third argument selects the
                button ("left"/"right"/"middle", default "left"); an
                optional fourth argument, the literal word "double",
                requests a double-click.
        """
        if len(arguments) < 2 or len(arguments) > 4:
            return _usage_error("desktop click <x> <y> [left|right|middle] [double]")

        parsed = _parse_ints(arguments[:2])
        if parsed is None:
            return _usage_error("desktop click <x> <y> (x/y must be integers)")
        x, y = parsed

        button = "left"
        double = False
        for extra in arguments[2:]:
            lowered = extra.lower()
            if lowered == "double":
                double = True
            elif lowered in KNOWN_BUTTONS:
                button = lowered
            else:
                return _usage_error(
                    f"desktop click: unrecognized argument '{extra}' "
                    f"(expected a button name {sorted(KNOWN_BUTTONS)} or 'double')"
                )

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        bounds_failure = self._check_bounds(x, y)
        if bounds_failure is not None:
            return bounds_failure

        return self._run("click", lambda: self._backend.click(x, y, button=button, double=double))

    def _scroll(self, arguments: list[str]) -> CommandResult:
        """Scroll at an optional (x, y), or the current cursor position.

        Args:
            arguments: [amount, x?, y?] -- amount is a required
                integer; x/y are optional integers (both must be
                given together, or neither).
        """
        if len(arguments) not in (1, 3):
            return _usage_error("desktop scroll <amount> [x] [y]")

        parsed = _parse_ints(arguments)
        if parsed is None:
            return _usage_error("desktop scroll <amount> [x] [y] (all values must be integers)")

        amount = parsed[0]
        x = parsed[1] if len(parsed) == 3 else None
        y = parsed[2] if len(parsed) == 3 else None

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        if x is not None and y is not None:
            bounds_failure = self._check_bounds(x, y)
            if bounds_failure is not None:
                return bounds_failure

        return self._run("scroll", lambda: self._backend.scroll(amount, x=x, y=y))

    def _type(self, arguments: list[str]) -> CommandResult:
        """Type text (arguments joined with a single space) literally.

        Matches the existing `" ".join(arguments)` convention already
        used elsewhere for free-text command arguments (e.g. `voice
        speak`, `src/skills/voice/skill.py`). The text is always sent
        literally to whatever currently has input focus -- never
        interpreted as a command (EP050_DESIGN.md Section 15).

        Args:
            arguments: The words to type.
        """
        if not arguments:
            return _usage_error("desktop type <text>")
        text = " ".join(arguments)

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        result = self._run("type", lambda: self._backend.type_text(text))
        # Never log the typed text itself (EP050_DESIGN.md Section 19)
        # -- only its length. `_run`'s own success log line already
        # omits arguments; this comment documents that guarantee
        # explicitly for the one action where it matters most.
        logger.info(f"desktop type: {len(text)} character(s) sent.")
        return result

    def _key(self, arguments: list[str]) -> CommandResult:
        """Press a single key or a '+'-joined hotkey combination.

        Args:
            arguments: [key] -- e.g. ["enter"] or ["ctrl+c"].
        """
        if len(arguments) != 1:
            return _usage_error("desktop key <key|key+key+...>")
        key = arguments[0]

        parts = key.lower().split("+")
        unknown = [part for part in parts if part not in KNOWN_KEYS]
        if unknown:
            return _usage_error(
                f"desktop key: unrecognized key name(s) {unknown} "
                f"(not in the known-keys allow-list)"
            )

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        return self._run("key", lambda: self._backend.press_key(key.lower()))

    def _read_clipboard(self, arguments: list[str]) -> CommandResult:
        """Return the current OS clipboard text contents."""
        if arguments:
            return _usage_error("desktop read-clipboard")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        try:
            text = self._backend.read_clipboard()
        except ComputerUseBackendError as exc:
            logger.error(f"desktop read-clipboard failed: {exc}")
            return CommandResult(success=False, message=f"desktop read-clipboard failed: {exc}")

        # Length only -- never the clipboard content itself
        # (EP050_DESIGN.md Section 19).
        logger.info(f"desktop read-clipboard: {len(text)} character(s) read.")
        return CommandResult(success=True, message=text)

    def _write_clipboard(self, arguments: list[str]) -> CommandResult:
        """Replace the OS clipboard text contents with the given text.

        Args:
            arguments: The words to write, joined with a single
                space (same convention as `_type`).
        """
        if not arguments:
            return _usage_error("desktop write-clipboard <text>")
        text = " ".join(arguments)

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        result = self._run("write-clipboard", lambda: self._backend.write_clipboard(text))
        # Length only -- never the clipboard content itself
        # (EP050_DESIGN.md Section 19).
        logger.info(f"desktop write-clipboard: {len(text)} character(s) written.")
        return result

    def _screenshot(self, arguments: list[str]) -> CommandResult:
        """Capture the screen and save the raw, uninterpreted bytes to a path.

        A path is required (EP050_DESIGN.md Section 19 -- a single,
        explicit, caller-directed write, never automatic persistence).
        EP-050 never inspects the captured bytes' content.

        Args:
            arguments: [path] -- the destination file path.
        """
        if len(arguments) != 1:
            return _usage_error("desktop screenshot <path>")
        path = arguments[0]

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        try:
            image = self._backend.screenshot()
        except ComputerUseBackendError as exc:
            logger.error(f"desktop screenshot failed: {exc}")
            return CommandResult(success=False, message=f"desktop screenshot failed: {exc}")

        try:
            with open(path, "wb") as file:
                file.write(image.data)
        except OSError as exc:
            logger.error(f"desktop screenshot: could not write '{path}': {exc}")
            return CommandResult(
                success=False,
                message=f"desktop screenshot: could not write '{path}': {exc}",
            )

        # Dimensions and byte size only -- never the image content
        # itself (EP050_DESIGN.md Section 19).
        logger.info(
            f"desktop screenshot: {image.width}x{image.height} "
            f"({len(image.data)} bytes) saved to '{path}'."
        )
        return CommandResult(
            success=True,
            message=f"Screenshot saved to '{path}' ({image.width}x{image.height}, {len(image.data)} bytes).",
        )

    def _cursor(self, arguments: list[str]) -> CommandResult:
        """Report the mouse cursor's current absolute screen position."""
        if arguments:
            return _usage_error("desktop cursor")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        try:
            position = self._backend.cursor_position()
        except ComputerUseBackendError as exc:
            logger.error(f"desktop cursor failed: {exc}")
            return CommandResult(success=False, message=f"desktop cursor failed: {exc}")

        logger.info(f"desktop cursor: ({position.x}, {position.y}).")
        return CommandResult(success=True, message=f"Cursor position: ({position.x}, {position.y})")

    def _screen_size(self, arguments: list[str]) -> CommandResult:
        """Report the primary screen's current dimensions."""
        if arguments:
            return _usage_error("desktop screen-size")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        try:
            size = self._backend.screen_size()
        except ComputerUseBackendError as exc:
            logger.error(f"desktop screen-size failed: {exc}")
            return CommandResult(success=False, message=f"desktop screen-size failed: {exc}")

        logger.info(f"desktop screen-size: {size.width}x{size.height}.")
        return CommandResult(success=True, message=f"Screen size: {size.width}x{size.height}")

    def _active_window(self, arguments: list[str]) -> CommandResult:
        """Report the currently focused/active window's title."""
        if arguments:
            return _usage_error("desktop active-window")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        try:
            title = self._backend.active_window_title()
        except ComputerUseBackendError as exc:
            logger.error(f"desktop active-window failed: {exc}")
            return CommandResult(success=False, message=f"desktop active-window failed: {exc}")

        logger.info(f"desktop active-window: '{title}'.")
        return CommandResult(success=True, message=f"Active window: '{title}'" if title else "No active window.")

    def _focus(self, arguments: list[str]) -> CommandResult:
        """Bring a window to the foreground by (sub-)title match.

        Args:
            arguments: The words making up the target window title,
                joined with a single space (same convention as
                `_type`) -- window titles routinely contain spaces.
        """
        if not arguments:
            return _usage_error("desktop focus <window title>")
        title = " ".join(arguments)

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        try:
            focused = self._backend.focus_window(title)
        except ComputerUseBackendError as exc:
            logger.error(f"desktop focus failed: {exc}")
            return CommandResult(success=False, message=f"desktop focus failed: {exc}")

        if not focused:
            logger.info(f"desktop focus: no window matching '{title}'.")
            return CommandResult(success=False, message=f"No window matching '{title}' was found.")

        logger.info(f"desktop focus: focused window matching '{title}'.")
        return CommandResult(success=True, message=f"Focused window matching '{title}'.")

    # ---------- Shared helpers ----------

    def _check_bounds(self, x: int, y: int) -> CommandResult | None:
        """Return a failure CommandResult if (x, y) is outside the screen, else None.

        Only called after `_gate()` has already confirmed a backend
        is available (EP050_DESIGN.md Section 17) -- this is the one
        place `screen_size()` is called purely for input validation,
        never before the safety gate has passed.
        """
        try:
            size = self._backend.screen_size()
        except ComputerUseBackendError as exc:
            logger.error(f"desktop: could not read screen size for bounds check: {exc}")
            return CommandResult(success=False, message=f"desktop: could not read screen size: {exc}")

        if not (0 <= x < size.width and 0 <= y < size.height):
            return CommandResult(
                success=False,
                message=(
                    f"desktop: ({x}, {y}) is out of screen bounds "
                    f"(screen is {size.width}x{size.height})."
                ),
            )
        return None

    def _run(self, action_name: str, call: Callable[[], None]) -> CommandResult:
        """Invoke a no-return backend call, translating any failure.

        Args:
            action_name: The action's name, for logging only.
            call: A zero-argument callable performing the actual
                `ComputerUseBackend` method call.

        Returns:
            `CommandResult(success=True, ...)` on success,
            `CommandResult(success=False, ...)` if the backend raised
            `ComputerUseBackendError` -- never lets any other
            exception type propagate uncaught (mirrors
            `CommandRouter.dispatch()`'s own top-level catch,
            EP050_DESIGN.md Section 21).
        """
        try:
            call()
        except ComputerUseBackendError as exc:
            logger.error(f"desktop {action_name} failed: {exc}")
            return CommandResult(success=False, message=f"desktop {action_name} failed: {exc}")

        logger.info(f"desktop {action_name}: succeeded.")
        return CommandResult(success=True, message=f"desktop {action_name}: done.")


def _usage_error(usage: str) -> CommandResult:
    """Return a standard, non-crashing usage-error CommandResult."""
    return CommandResult(success=False, message=f"Invalid arguments. Usage: {usage}")


def _parse_ints(values: list[str]) -> list[int] | None:
    """Parse every string in `values` as an int, or return None if any fails."""
    parsed: list[int] = []
    for value in values:
        try:
            parsed.append(int(value))
        except ValueError:
            return None
    return parsed
