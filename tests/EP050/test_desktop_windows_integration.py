"""EP-050 optional Windows integration checks (real PyAutoGUI, real OS).

**Deliberately NOT registered with `TestRegistry`.** This file is
never imported by `src/modules/test_module.py`, never runs as part
of `test EP050` or `test all`, and its import (or run) failing in a
headless/non-Windows environment must never affect the normal EP-050
automated suite (`tests/EP050/test_desktop.py`) in any way
(EP050_DESIGN.md Section 25's three-tier automated / optional
integration / manual split; task requirement: "must not cause the
normal EP-050 test suite to fail on environments without a real
Windows desktop").

This module constructs a real `WindowsComputerUseBackend`
(`src/skills/desktop/windows_backend.py`), which itself lazily
imports `pyautogui` only inside `__init__` -- so simply importing
*this* file is safe even without a display; only calling `main()`
below actually touches PyAutoGUI.

Run manually, on the real target Windows workstation, with:

    python -m tests.EP050.test_desktop_windows_integration

This intentionally does not use `BaseTest`/`TestRegistry` -- it is
not part of the graded `Passed`/`Failed`/`Skipped` suite; it prints a
plain pass/fail summary for a human operator to read, matching
EP050_DESIGN.md Section 25's "manual verification" tier as closely as
an automatable check can, while still being scripted rather than
purely by-eye where that's possible (mouse position round-trip,
screenshot dimensions).
"""

from __future__ import annotations

import sys

from src.core.config import Config
from src.skills.desktop.windows_backend import (
    WindowsComputerUseBackend,
    WindowsComputerUseBackendError,
)


def _config_with_defaults() -> Config:
    config = Config(config_path=__file__)  # never actually read from disk
    config._data = {"desktop": {"screenshot": {"max_dimension": 4096}}}
    return config


def main() -> int:
    """Run a small set of real-hardware checks. Returns 0 on success, 1 on failure."""
    print("EP-050 Windows integration check (real PyAutoGUI, real OS)")
    print("This is NOT part of 'test EP050' -- run only on a real Windows workstation.\n")

    try:
        backend = WindowsComputerUseBackend(config=_config_with_defaults())
    except WindowsComputerUseBackendError as exc:
        print(f"SKIPPED: could not construct WindowsComputerUseBackend: {exc}")
        print(
            "This is expected in any environment without a real "
            "display/windowing session (e.g. this sandbox, a headless "
            "CI runner). Run this script on the real target Windows "
            "workstation to actually exercise it."
        )
        return 0

    failures: list[str] = []

    try:
        size = backend.screen_size()
        print(f"screen_size(): {size.width}x{size.height}")
        if size.width <= 0 or size.height <= 0:
            failures.append("screen_size() reported non-positive dimensions")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"screen_size() raised: {exc}")

    try:
        original = backend.cursor_position()
        target_x = max(0, min(size.width - 1, original.x))
        target_y = max(0, min(size.height - 1, original.y))
        backend.move_mouse(target_x, target_y)
        moved = backend.cursor_position()
        print(f"cursor round-trip: moved to ({target_x}, {target_y}), read back ({moved.x}, {moved.y})")
        if (moved.x, moved.y) != (target_x, target_y):
            failures.append("cursor position after move_mouse() did not match the requested position")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"mouse move/read round-trip raised: {exc}")

    try:
        image = backend.screenshot()
        print(f"screenshot(): {image.width}x{image.height}, {len(image.data)} bytes, format={image.format}")
        if image.width <= 0 or image.height <= 0 or not image.data:
            failures.append("screenshot() reported empty/non-positive dimensions or no data")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"screenshot() raised: {exc}")

    try:
        original_clipboard = backend.read_clipboard()
        probe_value = "EP050-integration-check-probe"
        backend.write_clipboard(probe_value)
        round_tripped = backend.read_clipboard()
        print(f"clipboard round-trip: wrote probe value, read back {'matched' if round_tripped == probe_value else 'MISMATCH'}")
        if round_tripped != probe_value:
            failures.append("clipboard read-back did not match the value just written")
        backend.write_clipboard(original_clipboard)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"clipboard round-trip raised: {exc}")

    try:
        title = backend.active_window_title()
        print(f"active_window_title(): '{title}'")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"active_window_title() raised: {exc}")

    print()
    if failures:
        print(f"FAILED ({len(failures)} issue(s)):")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("PASSED: all real-hardware checks succeeded.")
    print(
        "Remaining manual verification (EP050_DESIGN.md Section 25): "
        "visually confirm a real 'desktop click'/'desktop type' against "
        "a visible application window, and confirm 'desktop.enabled: "
        "false' genuinely blocks all actions on this machine."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
