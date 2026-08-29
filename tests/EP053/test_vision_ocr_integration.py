"""EP-053 optional real-OCR integration check (real Pillow, real Tesseract binary).

**Deliberately NOT registered with `TestRegistry`.** This file is
never imported by `src/modules/test_module.py`, never runs as part of
`test EP053` or `test all`, and its behavior in an environment
without the external Tesseract system binary installed must never
affect the normal EP-053 automated suite
(`tests/EP053/test_vision.py`) in any way (EP053_DESIGN.md Section 16,
Owner Decision D10 -- mirrors `tests/EP051/
test_browser_integration.py`'s identical "optional integration" tier
and `tests/EP050/test_desktop_windows_integration.py`'s precedent
before it).

This module constructs a real `LocalVisionBackend`
(`src/skills/vision/local_backend.py`) and renders a small, real PNG
image containing rendered text using Pillow's own `ImageDraw`/
built-in bitmap font (no external font file, no network access, fully
hermetic) -- never a screenshot of the operator's real screen or any
externally-sourced image. It then runs real OCR against that image
via the real, external Tesseract binary.

Run manually, on a machine where the system Tesseract OCR binary has
already been installed (see `requirements.txt`'s EP-053 comment for
the one-time install step), with:

    python -m tests.EP053.test_vision_ocr_integration

This intentionally does not use `BaseTest`/`TestRegistry` -- it is not
part of the graded `Passed`/`Failed`/`Skipped` suite; it prints a
plain pass/fail summary for a human operator to read, matching
EP053_DESIGN.md Section 16's "optional integration" tier. If the
Tesseract binary is not installed, this script prints a disclosed
`SKIPPED` result and exits 0 -- never a failure of the normal EP-053
automated suite, which never imports this file.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from src.core.config import Config
from src.skills.vision.backend import VisionBackendError
from src.skills.vision.local_backend import LocalVisionBackend

_RENDERED_TEXT = "Jarvis Vision"


def _config_with_defaults() -> Config:
    config = Config(config_path=Path(__file__))  # never actually read from disk
    config._data = {
        "vision": {
            "max_file_size_mb": 25,
            "max_dimension": 8000,
        }
    }
    return config


def _make_text_image(path: Path) -> None:
    """Render `_RENDERED_TEXT` onto a plain white image using Pillow's built-in font."""
    image = Image.new("RGB", (320, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((10, 25), _RENDERED_TEXT, fill=(0, 0, 0))
    image.save(path, format="PNG")


def main() -> int:
    """Run a small set of real-OCR checks. Returns 0 on success (including a disclosed skip), 1 on failure."""
    print("EP-053 Vision Integration OCR check (real Pillow, real Tesseract binary)")
    print("This is NOT part of 'test EP053' -- run only where the system Tesseract OCR binary is installed.\n")

    backend = LocalVisionBackend(config=_config_with_defaults())
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        image_path = Path(tmp_dir) / "text.png"
        _make_text_image(image_path)

        try:
            info = backend.image_info(image_path)
            if (info.width, info.height, info.format) != (320, 80, "PNG"):
                failures.append(f"image_info: unexpected result {info!r}")
            else:
                print(f"image_info: OK ({info.width}x{info.height} {info.format})")
        except VisionBackendError as exc:
            failures.append(f"image_info: unexpected VisionBackendError: {exc}")

        try:
            result = backend.extract_text(image_path)
        except VisionBackendError as exc:
            if "tesseract" in str(exc).lower() and "not" in str(exc).lower():
                print(f"SKIPPED: system Tesseract OCR binary not available: {exc}")
                print(
                    "This is expected in any environment without the "
                    "external Tesseract binary installed -- not a "
                    "failure of the normal EP-053 automated suite, "
                    "which never imports this file."
                )
                return 0
            failures.append(f"extract_text: unexpected VisionBackendError: {exc}")
        else:
            recognized = result.text.strip()
            print(f"extract_text: OCR returned {recognized!r}")
            # Real OCR engines are not byte-exact; a reasonable substring
            # match is the right bar for an integration smoke check, not
            # an exact-equality assertion.
            if "jarvis" not in recognized.lower():
                failures.append(
                    f"extract_text: expected to recognize the word 'Jarvis' in {recognized!r}"
                )
            else:
                print("extract_text: OK (recognized expected text)")

    if failures:
        print("\nFAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nAll EP-053 OCR integration checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
