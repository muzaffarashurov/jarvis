"""PlaywrightBrowserBackend: the real, Playwright-based BrowserBackend.

Implements `BrowserBackend` (`backend.py`) against Playwright's
synchronous API -- the approved v1 technology (EP051_DESIGN.md
Section 8, Owner Decision D1): auto-waiting, a narrower error surface,
and no separate driver-binary management, at the cost of a genuinely
new dependency replacing the unused, unpinned `selenium` placeholder
(EP051_DESIGN.md Section 2/7).

This class knows nothing about `CommandRouter`, `CommandResult`, or
any other Jarvis-specific concept -- it is a pure browser-facing
adapter, mirroring `WindowsComputerUseBackend`'s isolation from
`DesktopModule` (EP051_DESIGN.md Section 9). No Playwright-specific
detail (its own exception types, its `Page`/`Browser`/`Playwright`
object shapes, etc.) leaks past this file -- every public method here
returns only `backend.py`'s own dataclasses or plain built-in types,
or raises only `BrowserBackendError`.

The `playwright` import itself is deferred to `__init__` (never at
module level), following `WindowsComputerUseBackend`'s exact
precedent (`src/skills/desktop/windows_backend.py`): this keeps the
module importable even in an environment where `playwright` is not
installed and no `BrowserModule`/`Bootstrap` code path ever
constructs this class (e.g. `browser.enabled: false`).

Genuinely cross-platform (EP051_DESIGN.md Section 21, Owner Decision
D11) -- unlike `WindowsComputerUseBackend`, this class carries no
Windows-only guard, since Playwright's own API is uniform across
platforms. Windows remains the v1 manual-verification target, but the
architecture itself does not require it.

Single browser session per instance, lazily created by `launch()`
(EP051_DESIGN.md Section 10, Owner Decision D5) -- no multi-session or
multi-tab addressing (Owner Decision D12). A second `launch()` call
while a session is already open raises `BrowserBackendError`; every
method other than `launch()` raises `BrowserBackendError` if no
session is currently open.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.core.config import Config
from src.skills.browser.backend import BrowserBackendError, Screenshot

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page, Playwright

DEFAULT_HEADLESS = False
DEFAULT_BROWSER_TYPE = "chromium"
DEFAULT_TIMEOUT_MS = 30000

_SUPPORTED_BROWSER_TYPES = frozenset({"chromium", "firefox", "webkit"})

__all__ = ["PlaywrightBrowserBackendError", "PlaywrightBrowserBackend"]


class PlaywrightBrowserBackendError(Exception):
    """Raised when PlaywrightBrowserBackend cannot be constructed.

    Reserved for construction-time failures only (the 'playwright'
    package is not importable, or 'browser.browser_type' names an
    unsupported engine). Never raised by any action method afterwards;
    those raise `BrowserBackendError` instead, matching
    `WindowsComputerUseBackendError`'s own construction-vs-runtime
    error split.
    """


class PlaywrightBrowserBackend:
    """The real `BrowserBackend` implementation, backed by Playwright.

    Constructed once by `Bootstrap` and injected into `BrowserModule`
    -- never constructs itself, never imported by `skill.py`
    (Dependency Policy, AI_GENERATION_STANDARD.md).
    """

    def __init__(self, config: Config) -> None:
        """Initialize the PlaywrightBrowserBackend.

        Does not launch a browser or start Playwright itself --
        construction only validates that 'playwright' is importable
        and that configuration is well-formed. The actual browser
        process is started lazily, by `launch()` (EP051_DESIGN.md
        Section 10).

        Args:
            config: The application Config, read once for
                'browser.headless', 'browser.browser_type', and
                'browser.default_timeout_ms' (EP051_DESIGN.md Section
                16).

        Raises:
            PlaywrightBrowserBackendError: If 'playwright' is not
                importable, or 'browser.browser_type' is not one of
                "chromium", "firefox", "webkit" -- `Bootstrap` catches
                this and continues with `browser.enabled` effectively
                unavailable, exactly as it already does for
                `WindowsComputerUseBackendError`.
        """
        try:
            import playwright.sync_api as _playwright_sync_api  # noqa: F401
        except Exception as exc:  # noqa: BLE001 -- normalize every import-time
            # failure (missing package, missing native dependency, etc.)
            # into one construction-time error, mirroring
            # WindowsComputerUseBackend's identical broad catch for the
            # same reason: the failure mode is a construction-time
            # environment problem, not a specific, enumerable exception
            # type.
            raise PlaywrightBrowserBackendError(
                "The 'playwright' package could not be imported. Ensure "
                "'playwright' is installed (see requirements.txt) and that "
                f"'playwright install' has been run at least once. ({exc})"
            ) from exc

        self._headless = bool(config.get("browser.headless", DEFAULT_HEADLESS))
        browser_type = str(config.get("browser.browser_type", DEFAULT_BROWSER_TYPE))
        if browser_type not in _SUPPORTED_BROWSER_TYPES:
            raise PlaywrightBrowserBackendError(
                f"Unsupported 'browser.browser_type': '{browser_type}' "
                f"(expected one of {sorted(_SUPPORTED_BROWSER_TYPES)})."
            )
        self._browser_type = browser_type
        self._timeout_ms = int(config.get("browser.default_timeout_ms", DEFAULT_TIMEOUT_MS))

        self._sync_playwright_context: Any = None
        self._playwright: "Playwright | None" = None
        self._browser: "Browser | None" = None
        self._page: "Page | None" = None

    # ---------- Session lifecycle (EP051_DESIGN.md Section 10) ----------

    def launch(self) -> None:
        if self._page is not None:
            raise BrowserBackendError(
                "a browser session is already open; run 'browser close' first"
            )

        from playwright.sync_api import Error as _PlaywrightError
        from playwright.sync_api import sync_playwright

        try:
            self._sync_playwright_context = sync_playwright()
            playwright = self._sync_playwright_context.start()
            browser_launcher = getattr(playwright, self._browser_type)
            browser = browser_launcher.launch(headless=self._headless)
            page = browser.new_page()
            page.set_default_timeout(self._timeout_ms)
        except _PlaywrightError as exc:
            self._reset_session_state()
            raise BrowserBackendError(f"browser launch: failed to start browser: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 -- a failed launch can raise
            # non-Playwright exception types too (e.g. no browser binaries
            # installed raises a plain Exception from Playwright's own
            # driver process, not `playwright.sync_api.Error`) -- every
            # failure here is normalized into one BrowserBackendError.
            self._reset_session_state()
            raise BrowserBackendError(f"browser launch: failed to start browser: {exc}") from exc

        self._playwright = playwright
        self._browser = browser
        self._page = page

    def close(self) -> None:
        page = self._require_session()
        from playwright.sync_api import Error as _PlaywrightError

        try:
            if self._browser is not None:
                self._browser.close()
            if self._sync_playwright_context is not None:
                self._sync_playwright_context.stop()
        except _PlaywrightError as exc:
            raise BrowserBackendError(f"browser close: {exc}") from exc
        finally:
            self._reset_session_state()

    # ---------- Navigation ----------

    def goto(self, url: str) -> None:
        page = self._require_session()
        self._call(page.goto, "goto", url)

    def back(self) -> None:
        page = self._require_session()
        self._call(page.go_back, "back")

    def forward(self) -> None:
        page = self._require_session()
        self._call(page.go_forward, "forward")

    def reload(self) -> None:
        page = self._require_session()
        self._call(page.reload, "reload")

    # ---------- Observation ----------

    def title(self) -> str:
        page = self._require_session()
        return self._call(page.title, "title")

    def current_url(self) -> str:
        page = self._require_session()
        return page.url

    def page_text(self) -> str:
        page = self._require_session()
        return self._call(page.inner_text, "page-text", "body")

    def exists(self, selector: str) -> bool:
        page = self._require_session()
        try:
            return page.locator(selector).count() > 0
        except Exception as exc:  # noqa: BLE001 -- invalid selector syntax
            raise BrowserBackendError(f"browser exists: invalid selector '{selector}': {exc}") from exc

    # ---------- DOM interaction ----------

    def click(self, selector: str) -> None:
        page = self._require_session()
        self._call(lambda: page.locator(selector).click(), "click")

    def type_text(self, selector: str, text: str) -> None:
        page = self._require_session()
        self._call(lambda: page.locator(selector).fill(text), "type")

    def clear(self, selector: str) -> None:
        page = self._require_session()
        self._call(lambda: page.locator(selector).fill(""), "clear")

    def press(self, selector: str, key: str) -> None:
        page = self._require_session()
        self._call(lambda: page.locator(selector).press(key), "press")

    def screenshot(self) -> Screenshot:
        page = self._require_session()
        data = self._call(page.screenshot, "screenshot")
        # Playwright's default screenshot format is PNG; dimensions
        # are read from the page's own viewport size (EP051_DESIGN.md
        # Section 17 -- never interpreted, only reported).
        viewport = page.viewport_size or {"width": 0, "height": 0}
        return Screenshot(
            width=int(viewport.get("width", 0)),
            height=int(viewport.get("height", 0)),
            format="png",
            data=data,
        )

    # ---------- Shared helpers ----------

    def _require_session(self) -> "Page":
        if self._page is None:
            raise BrowserBackendError(
                "no active browser session; run 'browser launch' first"
            )
        return self._page

    def _call(self, call, action_name: str, *args):
        from playwright.sync_api import Error as _PlaywrightError
        from playwright.sync_api import TimeoutError as _PlaywrightTimeoutError

        try:
            return call(*args)
        except _PlaywrightTimeoutError as exc:
            raise BrowserBackendError(f"browser {action_name}: timed out: {exc}") from exc
        except _PlaywrightError as exc:
            raise BrowserBackendError(f"browser {action_name}: {exc}") from exc

    def _reset_session_state(self) -> None:
        self._sync_playwright_context = None
        self._playwright = None
        self._browser = None
        self._page = None
