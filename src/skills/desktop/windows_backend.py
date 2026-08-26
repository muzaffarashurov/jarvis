"""WindowsComputerUseBackend: the real, PyAutoGUI-based ComputerUseBackend.

Implements `ComputerUseBackend` (`backend.py`) against PyAutoGUI --
the approved v1 technology (EP050_DESIGN.md Section 24, Owner
Decision D3): already declared in `requirements.txt` (unused until
now), and the only evaluated candidate covering every EP-050 v1
primitive (mouse, keyboard, screenshot, clipboard via its own
`pyperclip` dependency) in one library. Window-title observation uses
`pygetwindow`, PyAutoGUI's own bundled dependency -- no separate
top-level dependency is introduced (EP050_DESIGN.md Section 27).

This class knows nothing about `CommandRouter`, `CommandResult`, or
any other Jarvis-specific concept -- it is a pure OS-facing adapter,
mirroring `VoskSpeechToTextEngine`'s isolation from `VoiceModule`
(EP050_DESIGN.md Section 10). No PyAutoGUI-specific detail (its own
exception types, its `size()`/`position()` tuple return shapes, etc.)
leaks past this file -- every public method here returns only
`backend.py`'s own dataclasses, or raises only
`ComputerUseBackendError`.

Every dependency import is deferred to `__init__` (never at module
level), following `VoskSpeechToTextEngine`'s exact precedent
(`src/skills/voice/speech_to_text.py`) for the same reason: PyAutoGUI
itself requires a real display/windowing environment at *import*
time (it probes for one via its own `mouseinfo`/`pygetwindow`
dependencies) and would otherwise make this entire module
unimportable in a headless sandbox that never constructs this class
-- exactly the environment-availability situation EP-048's
`tflite-runtime` precedent already established a pattern for
(EP050_DESIGN.md Section 6.2/25).

v1 targets Windows only (EP050_DESIGN.md Section 9/24, Owner Decision
D5) -- this class is not verified on any other platform, even though
PyAutoGUI itself happens to support several.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from loguru import logger

from src.core.config import Config
from src.skills.desktop.backend import (
    ComputerUseBackendError,
    CursorPosition,
    Screenshot,
    ScreenSize,
)

if TYPE_CHECKING:
    import pyautogui
    import pygetwindow
    import pyperclip

DEFAULT_SCREENSHOT_MAX_DIMENSION = 4096

__all__ = ["WindowsComputerUseBackendError", "WindowsComputerUseBackend"]


class WindowsComputerUseBackendError(Exception):
    """Raised when WindowsComputerUseBackend cannot be constructed.

    Reserved for construction-time failures only (the 'pyautogui'
    package -- or one of its own dependencies -- is not importable,
    or no display/windowing environment is available). Never raised
    by any action method afterwards; those raise
    `ComputerUseBackendError` instead, matching
    `SpeechToTextEngineError`'s own construction-vs-runtime error
    split (`src/skills/voice/speech_to_text.py`).
    """


class WindowsComputerUseBackend:
    """The real `ComputerUseBackend` implementation, backed by PyAutoGUI.

    Constructed once by `Bootstrap` and injected into `DesktopModule`
    -- never constructs itself, never imported by `skill.py`
    (Dependency Policy, AI_GENERATION_STANDARD.md).
    """

    def __init__(self, config: Config) -> None:
        """Initialize the WindowsComputerUseBackend.

        Args:
            config: The application Config, read once for
                'desktop.screenshot.max_dimension'
                (EP050_DESIGN.md Section 22).

        Raises:
            WindowsComputerUseBackendError: If 'pyautogui' (or one of
                its own dependencies, e.g. 'pygetwindow',
                'pyperclip') is not importable, or if no real
                display/windowing environment is available to probe
                (e.g. a headless sandbox with no display) --
                `Bootstrap` catches this and continues with
                `desktop.enabled` effectively unavailable (see
                `_build_command_router`'s EP-050 wiring), exactly as
                every other hardware/dependency-backed subsystem
                already does for its own construction-time failures.
        """
        try:
            import pyautogui as _pyautogui
            import pygetwindow as _pygetwindow
            import pyperclip as _pyperclip
        except Exception as exc:  # noqa: BLE001 -- PyAutoGUI's own import-time
            # environment probing (display/windowing availability) can raise
            # a variety of exception types, not only ImportError (confirmed
            # during EP-050 STEP 2 verification: a headless sandbox with no
            # DISPLAY raises a KeyError from one of PyAutoGUI's own
            # dependencies at import time, not an ImportError) -- every
            # failure here is a construction-time environment problem, so
            # all of them are normalized into one WindowsComputerUseBackendError.
            raise WindowsComputerUseBackendError(
                "The 'pyautogui' package (or one of its own dependencies) "
                "could not be imported, or no display/windowing environment "
                "is available. Ensure 'pyautogui' is installed (see "
                "requirements.txt) and that this process has access to a "
                f"real Windows desktop session. ({exc})"
            ) from exc

        self._pyautogui = _pyautogui
        self._pygetwindow = _pygetwindow
        self._pyperclip = _pyperclip
        # PyAutoGUI's own fail-safe: moving the mouse to a screen corner
        # aborts the in-progress action. Left at its library default
        # (True) deliberately -- this is a real, if blunt, extra safety
        # mechanism and EP-050 has no reason to disable it.
        self._pyautogui.FAILSAFE = True

        self._max_screenshot_dimension = int(
            config.get(
                "desktop.screenshot.max_dimension",
                DEFAULT_SCREENSHOT_MAX_DIMENSION,
            )
        )

    def move_mouse(self, x: int, y: int) -> None:
        self._call(lambda: self._pyautogui.moveTo(x, y))

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        if double:
            self._call(lambda: self._pyautogui.doubleClick(x, y, button=button))
        else:
            self._call(lambda: self._pyautogui.click(x, y, button=button))

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None:
        def _do_scroll() -> None:
            if x is not None and y is not None:
                self._pyautogui.moveTo(x, y)
            self._pyautogui.scroll(amount)

        self._call(_do_scroll)

    def type_text(self, text: str) -> None:
        self._call(lambda: self._pyautogui.write(text, interval=0.0))

    def press_key(self, key: str) -> None:
        def _do_press() -> None:
            parts = key.split("+")
            if len(parts) > 1:
                self._pyautogui.hotkey(*parts)
            else:
                self._pyautogui.press(parts[0])

        self._call(_do_press)

    def read_clipboard(self) -> str:
        return self._call(lambda: self._pyperclip.paste())

    def write_clipboard(self, text: str) -> None:
        self._call(lambda: self._pyperclip.copy(text))

    def screenshot(self) -> Screenshot:
        def _do_screenshot() -> Screenshot:
            image = self._pyautogui.screenshot()
            width, height = image.size
            max_dim = self._max_screenshot_dimension
            if max_dim > 0 and max(width, height) > max_dim:
                scale = max_dim / max(width, height)
                new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
                image = image.resize(new_size)
                width, height = image.size
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return Screenshot(width=width, height=height, format="png", data=buffer.getvalue())

        return self._call(_do_screenshot)

    def cursor_position(self) -> CursorPosition:
        def _do_position() -> CursorPosition:
            point = self._pyautogui.position()
            return CursorPosition(x=int(point.x), y=int(point.y))

        return self._call(_do_position)

    def screen_size(self) -> ScreenSize:
        def _do_size() -> ScreenSize:
            size = self._pyautogui.size()
            return ScreenSize(width=int(size.width), height=int(size.height))

        return self._call(_do_size)

    def active_window_title(self) -> str:
        def _do_active_window() -> str:
            window = self._pygetwindow.getActiveWindow()
            return window.title if window is not None else ""

        # "No active window" is a normal observed state, not a
        # failure -- return "" rather than raising in that specific
        # case (backend.py's own contract).
        try:
            return _do_active_window()
        except ComputerUseBackendError:
            raise
        except Exception:  # noqa: BLE001
            return ""

    def focus_window(self, title: str) -> bool:
        def _do_focus() -> bool:
            matches = self._pygetwindow.getWindowsWithTitle(title)
            if not matches:
                return False
            matches[0].activate()
            return True

        return self._call(_do_focus)

    # ---------- Shared helper ----------

    def _call(self, action):
        """Run `action()`, normalizing any exception into ComputerUseBackendError.

        PyAutoGUI/pygetwindow/pyperclip each raise their own,
        library-specific exception types (e.g.
        `pyautogui.FailSafeException`) -- this is the single place
        that translates any of them into the one exception type
        `backend.py`'s `ComputerUseBackend` contract promises
        (EP050_DESIGN.md Section 21), so no PyAutoGUI-specific
        exception type ever reaches `DesktopModule`.
        """
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 -- see docstring
            logger.error(f"WindowsComputerUseBackend action failed: {exc}")
            raise ComputerUseBackendError(str(exc)) from exc
