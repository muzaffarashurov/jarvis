"""EP-053 vision module: the "vision" command namespace (Vision Integration).

Implements `CommandModule` (`src/core/command_router.py`), following
`DesktopModule`/`BrowserModule`/`FileModule`'s reference-implementation
pattern exactly (Owner Decision D9). Bridges local, read-only image
interpretation (metadata + OCR) to the "vision" namespace, dispatched
through the *existing*, unmodified `CommandRouter.dispatch()` -- no
new dispatch mechanism, and Tool Engine is untouched.

Target architecture (EP053_DESIGN.md Section 8/9):

    CommandRouter.dispatch("vision <action> <path> [...]")
        -> VisionModule
            -> VisionBackend (real: LocalVisionBackend,
               test-only: _FakeVisionBackend)
                -> Pillow / pytesseract (local only)

`VisionModule` never imports a concrete backend class
(`local_backend.py`) itself -- an already-constructed `VisionBackend`
is injected by `Bootstrap`, mirroring `DesktopModule`/`BrowserModule`/
`FileModule`'s own constructor-injection pattern.

EP-053 v1 is local-only and entirely read-only (Owner Decision D1):
`vision info` (image metadata) and `vision ocr` (text extraction) are
the only two real actions. There is no `vision describe` (AI-provider-
based semantic description) in this v1 -- see EP053_DESIGN.md Section
19 for that explicitly-deferred follow-up, and Section 21's "DO NOT
MODIFY" list, which this module honors: no line of
`src/core/ai/provider.py` is touched by this file.

`VisionModule` has no constructor dependency on `ComputerUseBackend`,
`BrowserBackend`, or `FileBackend` (EP053_DESIGN.md Section 7/11.2,
Owner Decision D4) -- it never captures a screenshot itself and never
delegates path-safety checking to `FileModule`; its own
`vision.allowed_roots` allow-list is independently configured and
independently enforced, duplicating (not importing) the same
resolve-then-compare algorithm `FileModule` already established for
'file.allowed_roots', by explicit Owner Decision.

Safety model (EP053_DESIGN.md Section 11/13/20, Owner Decisions
D1/D4):

    1. `vision.enabled` (default `false`) -- the master gate for the
       entire namespace, re-checked on every dispatched action, not
       only at registration time (mirrors `desktop.enabled`/
       `browser.enabled`/`file.enabled` exactly). `VisionModule` IS
       registered with `CommandRouter` regardless of this flag's
       value.
    2. Path safety -- every path argument is resolved to its
       absolute, canonical form (`Path.resolve()`, which follows
       symlinks/junctions) and must be equal to, or a descendant of,
       at least one configured `vision.allowed_roots` entry. An empty
       `allowed_roots` list means no path is ever permitted (mirrors
       `file.allowed_roots`' own default-empty, default-deny
       precedent) -- `vision.enabled: true` alone is inert.

Resource limits (`vision.max_file_size_mb`/`vision.max_dimension`,
Owner Decision D5) are enforced inside `VisionBackend` implementations
themselves (Section 8.2 of the backend contract), not here -- only a
backend can observe an image's own decoded content.

Argument-shape validation (right number of arguments) may run before
the `vision.enabled` gate, since it never touches the backend -- but
no path is ever resolved/safety-checked and no `VisionBackend` method
is ever called until the gate has passed, guaranteeing zero backend
interaction while disabled (mirrors `FileModule`'s identical
discipline).

Never performs screen/page capture (that remains EP-050's/EP-051's
job), never manages files beyond reading the one path a caller
supplies (that remains EP-052's job), and never performs shell/
subprocess/arbitrary code execution of any kind (`pytesseract`'s own
internal Tesseract-process invocation is that library's own,
already-widely-audited implementation detail, not a second call site
`VisionModule` introduces).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.skills.vision.backend import ImageInfo, VisionBackend, VisionBackendError

HELP_TEXT: str = (
    "Available vision commands (Vision Integration, EP-053)\n\n"
    "vision help\n"
    "vision info <path>\n"
    "vision ocr <path> [language]\n\n"
    "Every path must resolve inside a configured 'vision.allowed_roots' "
    "entry. 'vision' v1 is local-only and read-only: it never captures a "
    "screenshot itself (see 'desktop screenshot'/'browser screenshot') and "
    "never sends image data to an AI provider or any other network "
    "destination."
)

ActionHandler = Callable[[list[str]], CommandResult]

_DISABLED_MESSAGE: str = (
    "Vision Integration is disabled ('vision.enabled: false' in "
    "config/config.yaml). Set it to true and restart to enable "
    "'vision' actions."
)

_UNAVAILABLE_MESSAGE: str = (
    "Vision Integration is enabled but no backend is available (backend "
    "construction failed at startup -- check the startup log for "
    "details)."
)

_NO_ALLOWED_ROOTS_MESSAGE_SUFFIX: str = (
    " -- add at least one entry to 'vision.allowed_roots' in "
    "config/config.yaml and restart."
)


class VisionModule:
    """The "vision" command namespace (EP-053, Vision Integration).

    Responsibilities:
        - `vision info <path>`: report an image's metadata (width,
          height, format, color mode, file size) -- no interpretation
          of the image's content.
        - `vision ocr <path> [language]`: extract any printed/typed
          text visible in the image via OCR.

    Never captures a screenshot/page (EP-050's/EP-051's job), never
    manages files beyond the single path a caller supplies (EP-052's
    job), and never sends image data to an AI provider or any other
    network destination in v1 (Owner Decision D1).
    """

    def __init__(self, config: Config, backend: VisionBackend | None) -> None:
        """Initialize the VisionModule.

        Args:
            config: The application Config. Read at dispatch time for
                'vision.enabled' and 'vision.allowed_roots' -- read
                fresh on every call, not cached, so a config
                reload/restart is the only way to change them
                (matching every other subsystem's flag-reading
                convention).
            backend: The already-constructed `VisionBackend` used to
                perform every action. May be None if 'vision.enabled'
                is false at startup -- every action reports a clear,
                non-crashing failure (`_UNAVAILABLE_MESSAGE`) in that
                case, never a crash.
        """
        self._config = config
        self._backend = backend
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "info": self._info,
            "ocr": self._ocr,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace.

        Returns:
            The literal string "vision".
        """
        return "vision"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "vision" action.

        Args:
            action: The requested action (e.g. "ocr"). May be empty
                if the user entered only "vision".
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
                'Type "vision help" for available commands.'
            )
            return CommandResult(success=False, message=message)

        return handler(arguments)

    # ---------- Safety gate (EP053_DESIGN.md Section 11/13/20) ----------

    def _is_enabled(self) -> bool:
        """Return whether 'vision.enabled' is currently true."""
        return bool(self._config.get("vision.enabled", False))

    def _allowed_roots(self) -> list[Path]:
        """Return the configured, resolved allow-list of permitted roots.

        Read fresh from config on every call. Entries that cannot be
        resolved (e.g. malformed) are skipped rather than crashing the
        whole gate. An empty result means no path is ever permitted
        (mirrors `FileModule._allowed_roots()`'s own precedent,
        Owner Decision D4 -- an independent copy, not a shared
        implementation).
        """
        raw = self._config.get("vision.allowed_roots", []) or []
        roots: list[Path] = []
        for entry in raw:
            try:
                roots.append(Path(str(entry)).resolve())
            except (OSError, RuntimeError, ValueError):
                logger.warning(f"vision: could not resolve allowed_roots entry '{entry}', skipping.")
        return roots

    def _gate(self) -> CommandResult | None:
        """Return a failure CommandResult if no action may execute, else None.

        Called by every action handler *after* argument-shape
        validation and *before* any path resolution or `VisionBackend`
        call -- guarantees zero backend interaction while disabled or
        unavailable.
        """
        if not self._is_enabled():
            logger.info("vision: action rejected, 'vision.enabled' is false.")
            return CommandResult(success=False, message=_DISABLED_MESSAGE)
        if self._backend is None:
            logger.warning("vision: action rejected, no backend available.")
            return CommandResult(success=False, message=_UNAVAILABLE_MESSAGE)
        return None

    def _resolve_within_allowed(self, raw_path: str) -> tuple[Path | None, CommandResult | None]:
        """Resolve `raw_path` and check it against the allow-root model.

        Args:
            raw_path: The path argument exactly as supplied by the
                caller.

        Returns:
            A `(resolved_path, None)` tuple on success, or
            `(None, failure_CommandResult)` if the path is invalid or
            refused (EP053_DESIGN.md Section 13 -- resolve to an
            absolute, canonical path *before* any allow-root
            comparison, never compared as a raw string).
        """
        try:
            resolved = Path(raw_path).resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            return None, CommandResult(success=False, message=f"vision: invalid path '{raw_path}': {exc}")

        allowed_roots = self._allowed_roots()
        is_allowed = any(
            resolved == root or root in resolved.parents for root in allowed_roots
        )
        if not is_allowed:
            message = f"vision: '{raw_path}' is outside the allowed workspace"
            if not allowed_roots:
                message += _NO_ALLOWED_ROOTS_MESSAGE_SUFFIX
            else:
                message += " (vision.allowed_roots)."
            logger.info(f"vision: path rejected (not in allowed_roots): '{resolved}'.")
            return None, CommandResult(success=False, message=message)

        return resolved, None

    # ---------- Action handlers ----------

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available vision commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _info(self, arguments: list[str]) -> CommandResult:
        """Report an image's metadata.

        Args:
            arguments: [path] -- the image file path.
        """
        if len(arguments) != 1:
            return _usage_error("vision info <path>")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        resolved, path_failure = self._resolve_within_allowed(arguments[0])
        if path_failure is not None:
            return path_failure

        try:
            info = self._backend.image_info(resolved)
        except VisionBackendError as exc:
            logger.error(f"vision info failed: {exc}")
            return CommandResult(success=False, message=f"vision info failed: {exc}")

        logger.info(f"vision info: '{resolved}' ({info.width}x{info.height} {info.format}).")
        return CommandResult(success=True, message=_format_info(resolved, info))

    def _ocr(self, arguments: list[str]) -> CommandResult:
        """Extract any printed/typed text visible in the image.

        Args:
            arguments: [path] or [path, language] -- the image file
                path, and an optional Tesseract language code (e.g.
                "eng", "rus", "uzb").
        """
        if len(arguments) not in (1, 2):
            return _usage_error("vision ocr <path> [language]")
        raw_path = arguments[0]
        language = arguments[1] if len(arguments) == 2 else None

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        resolved, path_failure = self._resolve_within_allowed(raw_path)
        if path_failure is not None:
            return path_failure

        try:
            result = self._backend.extract_text(resolved, language)
        except VisionBackendError as exc:
            logger.error(f"vision ocr failed: {exc}")
            return CommandResult(success=False, message=f"vision ocr failed: {exc}")

        logger.info(f"vision ocr: '{resolved}' ({len(result.text)} chars extracted).")
        if not result.text:
            return CommandResult(success=True, message=f"vision ocr: no text found in '{resolved}'.")
        return CommandResult(success=True, message=result.text)


def _usage_error(usage: str) -> CommandResult:
    """Return a standard, non-crashing usage-error CommandResult."""
    return CommandResult(success=False, message=f"Invalid arguments. Usage: {usage}")


def _format_info(path: Path, info: ImageInfo) -> str:
    """Format one `ImageInfo` as a single, human-readable summary line."""
    return (
        f"{path}: {info.width}x{info.height} {info.format} ({info.mode}), "
        f"{info.size_bytes:,} bytes"
    )
