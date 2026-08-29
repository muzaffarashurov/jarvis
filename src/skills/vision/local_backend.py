"""LocalVisionBackend: the real, local-only EP-053 VisionBackend.

Built on Pillow (image decoding, `image_info`/`extract_text` both
need it) and `pytesseract` (OCR, `extract_text` only -- wraps an
external Tesseract binary; EP053_DESIGN.md Section 10, Owner
Decisions D1/D2). No AI-provider/network path exists in this class
(Owner Decision D1 -- v1 is local-only; no image byte or path ever
leaves the machine).

Genuinely cross-platform by design, with no `platform.system()`/
`sys.platform` branching anywhere in this file (EP053_DESIGN.md
Section 17): Pillow and `pytesseract` already handle Windows/macOS/
Linux differences internally, mirroring `LocalFileBackend`'s own
`pathlib`/`shutil`-based cross-platform precedent (EP052_DESIGN.md
Owner Decision D10).

This class assumes every `Path` it receives has *already* been
resolved to its absolute, canonical form and has *already* passed
`VisionModule`'s allow-list safety check (EP053_DESIGN.md Section 13)
-- `LocalVisionBackend` performs no path *safety* checking of its own.
It DOES perform its own resource-limit checks (file size, decoded
pixel dimensions -- EP053_DESIGN.md Section 20, Owner Decision D5),
since only the backend can observe an image's own decoded content;
`VisionModule` never queries these limits itself.

Split availability (EP053_DESIGN.md Section 18/20, Owner Decision
D8): this class ALWAYS constructs successfully -- Pillow needs no
external binary or display, exactly like `LocalFileBackend`'s own
"no construction-time dependency" precedent (EP052_DESIGN.md Section
21). `image_info()` never touches Tesseract and is therefore always
available once `vision.enabled` is true. `extract_text()` calls the
external Tesseract binary via `pytesseract` lazily, on each call --
if that binary is missing from `PATH`, the failure surfaces as a
`VisionBackendError` from that specific call only, never at
construction time and never affecting `image_info()`.
"""

from __future__ import annotations

from pathlib import Path

import pytesseract
from PIL import Image, UnidentifiedImageError

from src.core.config import Config
from src.skills.vision.backend import ImageInfo, OcrResult, VisionBackendError

_DEFAULT_MAX_FILE_SIZE_MB: int = 25
_DEFAULT_MAX_DIMENSION: int = 8000


class LocalVisionBackend:
    """The sole real `VisionBackend` implementation (EP-053 v1).

    Local-only (Owner Decision D1): image metadata (`image_info`) and
    OCR text extraction (`extract_text`) only -- no AI-provider-based
    semantic description exists in v1. No shell/subprocess execution
    of its own -- `pytesseract` invokes the Tesseract binary
    internally as that library's own, already-widely-audited
    implementation detail; `LocalVisionBackend` never constructs or
    executes a shell command itself (EP053_DESIGN.md Section 11.4).
    """

    def __init__(self, config: Config) -> None:
        """Initialize the LocalVisionBackend.

        Args:
            config: The application Config, read once for
                'vision.max_file_size_mb'/'vision.max_dimension'
                (Owner Decision D5) -- mirrors
                `WindowsComputerUseBackend`'s own
                'desktop.screenshot.max_dimension' precedent
                (EP050_DESIGN.md): a resource-usage bound, not a
                security control, so reading it once at construction
                (rather than fresh on every call, unlike the
                'vision.enabled'/'vision.allowed_roots' safety gates
                `VisionModule` itself owns) is consistent with this
                project's existing convention for this class of
                setting.
        """
        max_file_size_mb = config.get("vision.max_file_size_mb", _DEFAULT_MAX_FILE_SIZE_MB)
        self._max_file_size_bytes: int = int(max_file_size_mb) * 1024 * 1024
        self._max_dimension: int = int(config.get("vision.max_dimension", _DEFAULT_MAX_DIMENSION))

    def image_info(self, path: Path) -> ImageInfo:
        """See `VisionBackend.image_info`."""
        image = self._open_and_validate(path)
        try:
            size_bytes = path.stat().st_size
        except OSError as exc:
            raise VisionBackendError(f"could not stat '{path}': {exc}") from exc
        return ImageInfo(
            width=image.width,
            height=image.height,
            format=image.format or "",
            mode=image.mode,
            size_bytes=size_bytes,
        )

    def extract_text(self, path: Path, language: str | None = None) -> OcrResult:
        """See `VisionBackend.extract_text`."""
        image = self._open_and_validate(path)

        kwargs: dict[str, str] = {}
        if language:
            kwargs["lang"] = language

        try:
            raw_text = pytesseract.image_to_string(image, **kwargs)
        except pytesseract.TesseractNotFoundError as exc:
            raise VisionBackendError(
                "the external Tesseract OCR binary is not installed, or is "
                "not on PATH -- 'vision ocr' requires it in addition to the "
                "Python 'pytesseract'/'Pillow' packages (EP053_DESIGN.md "
                "Owner Decisions D2/D7/D8)."
            ) from exc
        except pytesseract.TesseractError as exc:
            raise VisionBackendError(f"OCR failed for '{path}': {exc}") from exc

        return OcrResult(text=raw_text.strip(), confidence=None, language=language or "eng")

    # ---------- Shared image-opening / resource-limit logic ----------

    def _open_and_validate(self, path: Path) -> Image.Image:
        """Open and fully decode the image at `path`, enforcing resource limits.

        Args:
            path: An already-resolved, already-path-safety-checked
                image file path.

        Returns:
            The fully-loaded Pillow `Image`.

        Raises:
            VisionBackendError: If `path` does not exist, is not a
                regular file, exceeds
                'vision.max_file_size_mb'/'vision.max_dimension'
                (Owner Decision D5), or is not a decodable image.
        """
        if not path.exists():
            raise VisionBackendError(f"'{path}' does not exist.")
        if not path.is_file():
            raise VisionBackendError(f"'{path}' is not a regular file.")

        try:
            size_bytes = path.stat().st_size
        except OSError as exc:
            raise VisionBackendError(f"could not stat '{path}': {exc}") from exc

        if size_bytes > self._max_file_size_bytes:
            raise VisionBackendError(
                f"'{path}' is {size_bytes} bytes, exceeding the configured "
                f"'vision.max_file_size_mb' limit ({self._max_file_size_bytes // (1024 * 1024)} MB)."
            )

        try:
            image = Image.open(path)
            image.load()  # Force full decode now, so any error surfaces here.
        except UnidentifiedImageError as exc:
            raise VisionBackendError(f"'{path}' is not a recognizable image: {exc}") from exc
        except Image.DecompressionBombError as exc:
            raise VisionBackendError(
                f"'{path}' exceeds Pillow's own decompression-bomb safety limit: {exc}"
            ) from exc
        except OSError as exc:
            raise VisionBackendError(f"could not open '{path}' as an image: {exc}") from exc

        if max(image.width, image.height) > self._max_dimension:
            raise VisionBackendError(
                f"'{path}' is {image.width}x{image.height}, exceeding the "
                f"configured 'vision.max_dimension' limit ({self._max_dimension})."
            )

        return image
