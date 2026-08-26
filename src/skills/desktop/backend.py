"""ComputerUseBackend: the EP-050 OS-input abstraction.

This is the *only* interface `DesktopModule` (`skill.py`) depends on.
It defines the smallest useful contract EP-050 v1 needs -- raw mouse,
keyboard, clipboard, and observation primitives (EP050_DESIGN.md
Section 8) -- and nothing else. It deliberately exposes no Browser,
File, OCR, Vision, or arbitrary OS/shell-execution capability
(EP050_DESIGN.md Sections 5, 20, 26); those remain EP-051/052/053's
scope, or are permanently out of scope (arbitrary execution).

Two implementations exist:
    - `WindowsComputerUseBackend` (`windows_backend.py`): the real,
      PyAutoGUI-based backend (EP050_DESIGN.md Section 24, Owner
      Decision D3).
    - `_FakeComputerUseBackend` (`tests/EP050/test_desktop.py`):
      a deterministic, test-only stand-in, following the same
      fake-class testing convention `tests/EP046/test_voice.py`
      already established (EP050_DESIGN.md Section 25).

This module contains no OS-facing logic itself -- it is a pure
interface, mirroring `ToolProvider`'s (`src/core/tool/
tool_provider.py`) role for Tool Engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "ScreenSize",
    "CursorPosition",
    "Screenshot",
    "ComputerUseBackendError",
    "ComputerUseBackend",
    "KNOWN_KEYS",
    "KNOWN_BUTTONS",
]


@dataclass(frozen=True)
class ScreenSize:
    """The primary screen's dimensions, in pixels."""

    width: int
    height: int


@dataclass(frozen=True)
class CursorPosition:
    """The mouse cursor's current position, in screen pixels."""

    x: int
    y: int


@dataclass(frozen=True)
class Screenshot:
    """A single, raw screen capture.

    `data` is opaque, undecoded image bytes (EP050_DESIGN.md Section
    18 -- EP-050 never interprets a screenshot's content). `width`/
    `height` describe the captured image itself, which may differ
    from the live `ScreenSize` if `desktop.screenshot.max_dimension`
    (EP050_DESIGN.md Section 22) caused the backend to scale it down.
    """

    width: int
    height: int
    format: str
    data: bytes


class ComputerUseBackendError(Exception):
    """Raised when a ComputerUseBackend operation cannot be completed.

    `DesktopModule` catches this (and only this) exception type from
    every backend call and translates it into a failed `CommandResult`
    (EP050_DESIGN.md Section 21) -- it is never allowed to propagate
    through `CommandRouter.dispatch()` uncaught.
    """


@runtime_checkable
class ComputerUseBackend(Protocol):
    """The OS-input contract every Computer Use backend must implement.

    Every method performs exactly one, synchronous, side-effecting or
    observation action and returns immediately -- there is no
    multi-step gesture, no queued/batched action, and no persistence
    of state between calls (EP050_DESIGN.md Section 8.2's "no
    drag-and-drop primitive in v1" scoping).

    Implementations must raise `ComputerUseBackendError` (only) for
    any failure -- never a bare/unrelated exception type -- so
    `DesktopModule` has one, single exception type to catch.
    """

    def move_mouse(self, x: int, y: int) -> None:
        """Move the mouse cursor to an absolute screen position."""
        ...

    def click(self, x: int, y: int, button: str = "left", double: bool = False) -> None:
        """Move the mouse to (x, y) and click.

        Args:
            x: Absolute screen x-coordinate.
            y: Absolute screen y-coordinate.
            button: One of `KNOWN_BUTTONS` ("left", "right", "middle").
            double: If True, perform a double-click instead of a
                single click.
        """
        ...

    def scroll(self, amount: int, x: int | None = None, y: int | None = None) -> None:
        """Scroll at (x, y) if given, otherwise at the current cursor position.

        Args:
            amount: Scroll amount and direction (backend-defined
                sign convention: positive scrolls up/away from the
                user, negative scrolls down/toward the user).
            x: Optional absolute x-coordinate to move to before
                scrolling.
            y: Optional absolute y-coordinate to move to before
                scrolling.
        """
        ...

    def type_text(self, text: str) -> None:
        """Type `text` literally into whatever currently has input focus.

        `text` is never interpreted as a command, expression, or
        script by any backend implementation (EP050_DESIGN.md Section
        15 -- an unconditional, hard rule for the whole module).
        """
        ...

    def press_key(self, key: str) -> None:
        """Press a single key, or a '+'-joined hotkey combination.

        Args:
            key: A single key name (e.g. "enter"), or multiple key
                names joined with '+' (e.g. "ctrl+c"). Every
                individual key name must already be a member of
                `KNOWN_KEYS` -- `DesktopModule` validates this before
                calling the backend (EP050_DESIGN.md Section 17), so
                a conforming backend may assume every name it
                receives here is already known-valid.
        """
        ...

    def read_clipboard(self) -> str:
        """Return the current text contents of the OS clipboard."""
        ...

    def write_clipboard(self, text: str) -> None:
        """Replace the OS clipboard's text contents with `text`."""
        ...

    def screenshot(self) -> Screenshot:
        """Capture the current screen and return it as raw, opaque bytes."""
        ...

    def cursor_position(self) -> CursorPosition:
        """Return the mouse cursor's current absolute screen position."""
        ...

    def screen_size(self) -> ScreenSize:
        """Return the primary screen's current dimensions, in pixels."""
        ...

    def active_window_title(self) -> str:
        """Return the title of the currently focused/active window.

        Returns an empty string if no window is currently focused, or
        if the active window's title cannot be determined -- never
        raises `ComputerUseBackendError` for this specific case, since
        "no active window" is a normal, observable state, not a
        failure.
        """
        ...

    def focus_window(self, title: str) -> bool:
        """Attempt to bring the window whose title matches `title` to the foreground.

        Args:
            title: The target window's title (or a substring match,
                backend-defined).

        Returns:
            True if a matching window was found and focused, False if
            no matching window exists. Raises
            `ComputerUseBackendError` only for a genuine OS-level
            failure, never merely because no window matched.
        """
        ...


# Deliberately small, explicit allow-lists (EP050_DESIGN.md Section
# 17) -- a key name or button not listed here is rejected by
# `DesktopModule` before any backend call is made, rather than being
# passed straight through to the OS. This is not exhaustive of every
# key a real keyboard has; it covers the keys a v1 Computer Use
# consumer actually needs. Extending it is a normal, low-risk future
# change -- it does not require an Owner Decision by itself.
KNOWN_KEYS: frozenset[str] = frozenset(
    {
        # Letters and digits.
        *"abcdefghijklmnopqrstuvwxyz",
        *"0123456789",
        # Whitespace / editing.
        "enter", "return", "tab", "space", "backspace", "delete", "esc", "escape",
        "insert",
        # Navigation.
        "up", "down", "left", "right", "home", "end", "pageup", "pagedown",
        # Modifiers (also valid as hotkey components, e.g. "ctrl+c").
        "ctrl", "alt", "shift", "win", "cmd", "command",
        # Function keys.
        *(f"f{n}" for n in range(1, 13)),
        # Punctuation commonly used in hotkeys.
        "-", "=", "[", "]", ";", "'", ",", ".", "/", "`", "\\",
    }
)

KNOWN_BUTTONS: frozenset[str] = frozenset({"left", "right", "middle"})
