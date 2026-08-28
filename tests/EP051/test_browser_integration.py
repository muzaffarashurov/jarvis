"""EP-051 optional real-browser integration checks (real Playwright, real Chromium).

**Deliberately NOT registered with `TestRegistry`.** This file is
never imported by `src/modules/test_module.py`, never runs as part of
`test EP051` or `test all`, and its import (or run) failing in an
environment without downloaded browser binaries must never affect the
normal EP-051 automated suite (`tests/EP051/test_browser.py`) in any
way (EP051_DESIGN.md Section 18's three-tier automated / optional
integration / manual split; mirrors `tests/EP050/
test_desktop_windows_integration.py`'s identical precedent).

This module constructs a real `PlaywrightBrowserBackend`
(`src/skills/browser/playwright_backend.py`), which itself lazily
imports `playwright` only inside `__init__`/action methods -- so
simply importing *this* file is safe even without `playwright`
installed or browser binaries downloaded; only calling `main()` below
actually launches a real browser.

Exercises `PlaywrightBrowserBackend` against a local, static `file://`
fixture page (never a live third-party website) to keep the check
hermetic and avoid flakiness from external site changes
(EP051_DESIGN.md Section 18): launch a real Chromium instance,
navigate to the fixture, read its title/page-text, click a button,
type into a field, submit with Enter, and verify the resulting page
state, then capture a screenshot and close the session.

Run manually, on a machine where `playwright install chromium` has
already completed successfully, with:

    python -m tests.EP051.test_browser_integration

This intentionally does not use `BaseTest`/`TestRegistry` -- it is not
part of the graded `Passed`/`Failed`/`Skipped` suite; it prints a
plain pass/fail summary for a human operator to read, matching
EP051_DESIGN.md Section 18's "optional integration" tier.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from src.core.config import Config
from src.skills.browser.backend import BrowserBackendError
from src.skills.browser.playwright_backend import (
    PlaywrightBrowserBackend,
    PlaywrightBrowserBackendError,
)

_FIXTURE_HTML = """<!DOCTYPE html>
<html>
<head><title>EP-051 Fixture Page</title></head>
<body>
  <h1>EP-051 Integration Fixture</h1>
  <p id="greeting">Hello, integration test.</p>
  <input id="search" type="text" />
  <button id="submit" onclick="document.getElementById('result').innerText = 'clicked: ' + document.getElementById('search').value;">Submit</button>
  <p id="result"></p>
</body>
</html>
"""


def _config_with_defaults() -> Config:
    config = Config(config_path=Path(__file__))  # never actually read from disk
    config._data = {
        "browser": {
            "headless": True,  # Non-interactive for an automated manual run.
            "browser_type": "chromium",
            "default_timeout_ms": 10000,
        }
    }
    return config


def main() -> int:
    """Run a small set of real-browser checks. Returns 0 on success, 1 on failure."""
    print("EP-051 Browser Automation integration check (real Playwright, real Chromium)")
    print("This is NOT part of 'test EP051' -- run only where 'playwright install chromium' has completed.\n")

    try:
        backend = PlaywrightBrowserBackend(config=_config_with_defaults())
    except PlaywrightBrowserBackendError as exc:
        print(f"SKIPPED: could not construct PlaywrightBrowserBackend: {exc}")
        print(
            "This is expected in any environment without 'playwright' "
            "installed (e.g. this sandbox) -- not a failure of the "
            "normal EP-051 automated suite, which never imports this file."
        )
        return 0

    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        fixture_path = Path(tmp_dir) / "fixture.html"
        fixture_path.write_text(_FIXTURE_HTML, encoding="utf-8")
        fixture_url = fixture_path.as_uri()

        try:
            backend.launch()
            print("launch: OK")

            backend.goto(fixture_url)
            print(f"goto '{fixture_url}': OK")

            title = backend.title()
            if title != "EP-051 Fixture Page":
                failures.append(f"title: expected 'EP-051 Fixture Page', got {title!r}")
            else:
                print(f"title: OK ({title!r})")

            text = backend.page_text()
            if "Hello, integration test." not in text:
                failures.append(f"page_text: expected greeting not found in {text!r}")
            else:
                print("page_text: OK")

            if not backend.exists("#search"):
                failures.append("exists('#search'): expected True, got False")
            else:
                print("exists('#search'): OK")

            backend.type_text("#search", "integration-value")
            print("type_text: OK")

            backend.click("#submit")
            print("click: OK")

            result_text = backend.page_text()
            if "clicked: integration-value" not in result_text:
                failures.append(
                    f"post-click page_text: expected 'clicked: integration-value' in {result_text!r}"
                )
            else:
                print("post-click page_text: OK")

            screenshot = backend.screenshot()
            if not screenshot.data:
                failures.append("screenshot: expected non-empty image bytes")
            else:
                print(f"screenshot: OK ({screenshot.width}x{screenshot.height}, {len(screenshot.data)} bytes)")

            backend.close()
            print("close: OK")

        except BrowserBackendError as exc:
            failures.append(f"unexpected BrowserBackendError: {exc}")

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nAll EP-051 integration checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
