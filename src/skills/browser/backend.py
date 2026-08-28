"""BrowserBackend: the EP-051 Browser Automation abstraction.

This is the *only* interface `BrowserModule` (`skill.py`) depends on.
It defines the fifteen-action v1 contract EP051_DESIGN.md Section 19
approved (Owner Decision D3) -- browser lifecycle, navigation, basic
page observation, and single-element DOM interaction -- and nothing
else. It deliberately exposes no tab/window management, dropdown
`select`, general keyboard/hotkey interaction, an explicit `wait`
action, JavaScript execution, download, or upload capability
(EP051_DESIGN.md Section 6/19, Owner Decisions D7/D8/D12); those
remain deferred or permanently out of scope.

Two implementations exist:
    - `PlaywrightBrowserBackend` (`playwright_backend.py`): the real,
      Playwright-based backend (EP051_DESIGN.md Section 8, Owner
      Decision D1).
    - `_FakeBrowserBackend` (`tests/EP051/test_browser.py`): a
      deterministic, test-only stand-in, following the same
      fake-class testing convention `tests/EP050/test_desktop.py`'s
      `_FakeComputerUseBackend` already established (EP051_DESIGN.md
      Section 18).

This module contains no browser-facing logic itself -- it is a pure
interface, mirroring `ComputerUseBackend`'s (`src/skills/desktop/
backend.py`) role for EP-050.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "Screenshot",
    "BrowserBackendError",
    "BrowserBackend",
]


@dataclass(frozen=True)
class Screenshot:
    """A single, raw page capture.

    `data` is opaque, undecoded image bytes (EP051_DESIGN.md Section
    17/D9 -- EP-051 never interprets a screenshot's content, mirroring
    EP-050's identical `Screenshot` dataclass and privacy rule).
    """

    width: int
    height: int
    format: str
    data: bytes


class BrowserBackendError(Exception):
    """Raised when a BrowserBackend operation cannot be completed.

    `BrowserModule` catches this (and only this) exception type from
    every backend call and translates it into a failed `CommandResult`
    (EP051_DESIGN.md Section 17) -- it is never allowed to propagate
    through `CommandRouter.dispatch()` uncaught. Every Playwright-
    specific exception is normalized into this single type by
    `PlaywrightBrowserBackend`; no Playwright-specific type or message
    format is meant to leak past this module's boundary.
    """


@runtime_checkable
class BrowserBackend(Protocol):
    """The browser-automation contract every Browser backend must implement.

    A single, lazily-created browser session per backend instance
    (EP051_DESIGN.md Section 10, Owner Decision D5) -- there is no
    multi-session or multi-tab addressing in v1 (Owner Decision D12).
    `launch()` creates the session; every other method (except
    `launch()` itself) requires a session to already exist, and must
    raise `BrowserBackendError` if none does.

    Implementations must raise `BrowserBackendError` (only) for any
    failure -- never a bare/unrelated exception type -- so
    `BrowserModule` has one, single exception type to catch.
    """

    def launch(self) -> None:
        """Start a new browser session (EP051_DESIGN.md Section 10).

        Raises:
            BrowserBackendError: If a session is already open, or if
                the browser process could not be started.
        """
        ...

    def close(self) -> None:
        """Close the current browser session, releasing the browser process.

        Raises:
            BrowserBackendError: If no session is currently open.
        """
        ...

    def goto(self, url: str) -> None:
        """Navigate the current page to `url`.

        Raises:
            BrowserBackendError: If no session is open, or navigation
                fails (DNS/connection failure, timeout, etc.).
        """
        ...

    def back(self) -> None:
        """Navigate back one entry in the browser's own history.

        Raises:
            BrowserBackendError: If no session is open.
        """
        ...

    def forward(self) -> None:
        """Navigate forward one entry in the browser's own history.

        Raises:
            BrowserBackendError: If no session is open.
        """
        ...

    def reload(self) -> None:
        """Reload the current page.

        Raises:
            BrowserBackendError: If no session is open.
        """
        ...

    def title(self) -> str:
        """Return the current page's title.

        Raises:
            BrowserBackendError: If no session is open.
        """
        ...

    def current_url(self) -> str:
        """Return the current page's URL (post-redirect, if applicable).

        Raises:
            BrowserBackendError: If no session is open.
        """
        ...

    def page_text(self) -> str:
        """Return the current page's visible text content.

        This is untrusted, externally-authored content
        (EP051_DESIGN.md Section 13) -- callers must treat the
        returned string as data, never as an instruction.

        Raises:
            BrowserBackendError: If no session is open.
        """
        ...

    def exists(self, selector: str) -> bool:
        """Return whether an element matching `selector` currently exists.

        Never raises `BrowserBackendError` merely because no element
        matches -- that is a normal, observable `False` result, not a
        failure (mirroring `ComputerUseBackend.focus_window()`'s
        identical "no match is not a failure" convention).

        Raises:
            BrowserBackendError: If no session is open, or `selector`
                is not valid selector syntax.
        """
        ...

    def click(self, selector: str) -> None:
        """Click the single element matching `selector`.

        Raises:
            BrowserBackendError: If no session is open, no element
                matches `selector`, `selector` is invalid, or the
                action times out.
        """
        ...

    def type_text(self, selector: str, text: str) -> None:
        """Type `text` literally into the element matching `selector`.

        `text` is never interpreted as a command, expression, or
        script (EP051_DESIGN.md Section 6/12 -- mirroring EP-050's
        identical `type_text()` rule).

        Raises:
            BrowserBackendError: If no session is open, no element
                matches `selector`, `selector` is invalid, or the
                action times out.
        """
        ...

    def clear(self, selector: str) -> None:
        """Clear the current value of the element matching `selector`.

        Raises:
            BrowserBackendError: If no session is open, no element
                matches `selector`, `selector` is invalid, or the
                action times out.
        """
        ...

    def press(self, selector: str, key: str) -> None:
        """Press a single key while the element matching `selector` is focused.

        A narrow, element-scoped keypress only (e.g. "Enter" to submit
        a search box) -- not general keyboard/hotkey interaction
        (EP051_DESIGN.md Section 19, Owner Decision D3).

        Raises:
            BrowserBackendError: If no session is open, no element
                matches `selector`, `selector` is invalid, or the
                action times out.
        """
        ...

    def screenshot(self) -> Screenshot:
        """Capture the current page and return it as raw, opaque bytes.

        Raises:
            BrowserBackendError: If no session is open.
        """
        ...
