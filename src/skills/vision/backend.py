"""VisionBackend: the EP-053 Vision Integration image-interpretation abstraction.

This is the *only* interface `VisionModule` (`skill.py`) depends on. It
defines the smallest useful contract EP-053 v1 needs -- local,
read-only image interpretation (`image_info`, `extract_text`;
EP053_DESIGN.md Section 8/9, Owner Decisions D1/D2) -- and nothing
else. It deliberately exposes no screen/page capture, general file
management, object detection, video, or AI-provider-based
description capability (EP053_DESIGN.md Section 4/8.3/9, Owner
Decision D1); those are either permanently out of scope or a
well-defined, explicitly-deferred follow-up (Section 19).

Path safety (allow-list resolution, EP053_DESIGN.md Section 11.2/13,
Owner Decision D4) is enforced entirely at the `VisionModule`
boundary, *before* any `VisionBackend` method is called -- every
`Path` this interface receives is already resolved to its absolute,
canonical form and has already passed the allow-list check.
`VisionBackend` implementations perform the raw image-interpretation
operation only; they are not responsible for, and must not
re-implement, the path-safety model. Resource limits
(`vision.max_file_size_mb`/`vision.max_dimension`, Owner Decision D5)
ARE this interface's responsibility -- unlike path safety, they
depend on the image's own content (file size, decoded dimensions),
which only a `VisionBackend` implementation can observe.

Two implementations exist:
    - `LocalVisionBackend` (`local_backend.py`): the real
      implementation, built on Pillow (image decoding) and
      `pytesseract` (OCR, wrapping an external Tesseract binary;
      EP053_DESIGN.md Section 10, Owner Decisions D1/D2).
    - `_FakeVisionBackend` (`tests/EP053/test_vision.py`): a
      deterministic, test-only stand-in, following the same
      fake-class testing convention `_FakeComputerUseBackend`/
      `_FakeBrowserBackend`/`_FakeFileBackend` already established
      (EP053_DESIGN.md Section 16/20, Owner Decision D10).

This module contains no image-decoding or OCR logic itself -- it is a
pure interface, mirroring `ComputerUseBackend`'s/`BrowserBackend`'s/
`FileBackend`'s role for their own EPs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "ImageInfo",
    "OcrResult",
    "VisionBackendError",
    "VisionBackend",
]


@dataclass(frozen=True)
class ImageInfo:
    """Metadata describing a single image file, no content interpretation.

    Returned by `VisionBackend.image_info()`. A plain, frozen
    dataclass with no behavior -- mirroring `ScreenSize`/
    `CursorPosition`/`Screenshot`/`FileEntry`'s established precedent
    (EP053_DESIGN.md Section 8.2/14).

    Attributes:
        width: Image width, in pixels.
        height: Image height, in pixels.
        format: The image's on-disk format, as Pillow reports it
            (e.g. "PNG", "JPEG").
        mode: The image's Pillow color mode (e.g. "RGB", "L", "RGBA").
        size_bytes: The file's size on disk, in bytes.
    """

    width: int
    height: int
    format: str
    mode: str
    size_bytes: int


@dataclass(frozen=True)
class OcrResult:
    """The result of extracting text from an image via OCR.

    Returned by `VisionBackend.extract_text()`. A plain, frozen
    dataclass with no behavior.

    Attributes:
        text: The extracted text. An empty string is a normal,
            observable outcome ("no text found"), never an error
            (EP053_DESIGN.md Section 14 -- mirrors
            `active_window_title()`'s own "empty is not a failure"
            precedent).
        confidence: A backend-reported confidence score, or None if
            the backend does not provide one. `LocalVisionBackend`
            (v1) always returns None -- `pytesseract`'s own simple
            `image_to_string()` call does not expose a confidence
            score (EP053_DESIGN.md Section 8.2, declared here for
            shape only).
        language: The language code actually used for recognition
            (e.g. "eng"), reflecting either the caller's request or
            the backend's own default.
    """

    text: str
    confidence: float | None
    language: str


class VisionBackendError(Exception):
    """Raised when a VisionBackend operation cannot be completed.

    `VisionModule` catches this (and only this) exception type from
    every backend call and translates it into a failed `CommandResult`
    (EP053_DESIGN.md Section 15) -- it is never allowed to propagate
    through `CommandRouter.dispatch()` uncaught. Implementations must
    never let a raw `OSError`/`PIL.UnidentifiedImageError`/
    `pytesseract.TesseractNotFoundError` escape -- every failure is
    translated into `VisionBackendError` with a clear, non-leaking
    message.
    """


@runtime_checkable
class VisionBackend(Protocol):
    """The image-interpretation contract every Vision backend must implement.

    Every method performs exactly one, synchronous, read-only
    interpretation of an already-resolved, already-path-safety-checked
    `Path` and returns immediately -- there is no multi-step
    operation, no queued/batched action, and no mutation of the image
    or the filesystem of any kind (EP053_DESIGN.md Section 9/11.1 --
    v1 is entirely read-only).

    Implementations must raise `VisionBackendError` (only) for any
    failure -- never a bare/unrelated exception type -- so
    `VisionModule` has one, single exception type to catch.
    """

    def image_info(self, path) -> ImageInfo:
        """Return metadata describing the image at `path`.

        Never depends on the OCR engine being available (EP053_DESIGN.md
        Owner Decision D8 -- split availability) -- only on the image
        being decodable by Pillow.

        Args:
            path: An already-resolved, already-path-safety-checked
                image file path.

        Returns:
            The image's `ImageInfo`.

        Raises:
            VisionBackendError: If `path` does not exist, is not a
                regular file, is not a decodable image, or exceeds
                the configured resource limits
                (`vision.max_file_size_mb`/`vision.max_dimension`,
                Owner Decision D5).
        """
        ...

    def extract_text(self, path, language: str | None = None) -> OcrResult:
        """Extract any printed/typed text visible in the image at `path`.

        Args:
            path: An already-resolved, already-path-safety-checked
                image file path.
            language: An optional Tesseract language code (e.g.
                "eng", "rus", "uzb"). None uses the backend's own
                default.

        Returns:
            The extracted `OcrResult`. `text` may be empty -- this is
            a normal outcome, not a failure.

        Raises:
            VisionBackendError: If `path` does not exist, is not a
                regular file, is not a decodable image, exceeds the
                configured resource limits, or the OCR engine itself
                is unavailable (e.g. the external Tesseract binary is
                not installed, Owner Decision D8) or fails.
        """
        ...
