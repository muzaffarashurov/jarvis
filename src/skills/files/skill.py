"""EP-052 files module: the "file" command namespace (File Automation).

Implements `CommandModule` (`src/core/command_router.py`), following
`DesktopModule`/`BrowserModule`'s reference-implementation pattern
exactly (Owner Decision D9). Bridges controlled local filesystem
automation (list/exists/stat/read/write/copy/move/mkdir/delete) to the
"file" namespace, dispatched through the *existing*, unmodified
`CommandRouter.dispatch()` -- no new dispatch mechanism, and Tool
Engine is untouched.

Target architecture (EP052_DESIGN.md Section 8/9):

    CommandRouter.dispatch("file <action> [args...]")
        -> FileModule
            -> FileBackend (real: LocalFileBackend,
               test-only: _FakeFileBackend)
                -> Local filesystem

`FileModule` never imports a concrete backend class
(`local_backend.py`) itself -- an already-constructed `FileBackend` is
injected by `Bootstrap`, mirroring `DesktopModule`/`BrowserModule`'s
own constructor-injection pattern.

EP-052 v1 is a **controlled filesystem automation capability, not a
read-only filesystem viewer** (Owner Decision D2): both read-only
observation (`list`, `exists`, `stat`, `read`) and controlled mutation
(`write`, `copy`, `move`, `mkdir`, `delete`) ship together, subject to
the layered security model below.

Safety model (EP052_DESIGN.md Section 11/13/20, Owner Decisions
D2-D5):

    1. `file.enabled` (default `false`) -- the master gate for the
       entire namespace, re-checked on every dispatched action, not
       only at registration time (mirrors `desktop.enabled`/
       `browser.enabled` exactly). `FileModule` IS registered with
       `CommandRouter` regardless of this flag's value.
    2. Path safety -- every path argument is resolved to its
       absolute, canonical form (`Path.resolve()`, which follows
       symlinks/junctions) and must be equal to, or a descendant of,
       at least one configured `file.allowed_roots` entry, and must
       NOT be equal to, or a descendant of, any configured
       `file.denied_paths` entry (Owner Decision D4). An empty
       `allowed_roots` list means no path is ever permitted (Owner
       Decision D5) -- `file.enabled: true` alone is inert.
    3. `file.allow_destructive` (default `false`) -- a second,
       independent gate specifically for `move`, `delete`, and
       overwriting an existing file via `write`/`copy` (Owner
       Decision D3). `write`/`copy` against a *new* path, and
       `mkdir`, never require this flag.

Argument-shape validation (right number of arguments, `--overwrite`
flag parsing) may run before the `file.enabled` gate, since it never
touches the backend -- but no path is ever resolved/safety-checked
and no `FileBackend` method is ever called until every applicable
gate has passed, guaranteeing zero backend interaction while disabled
(mirrors `DesktopModule`'s identical discipline).

Never performs shell/subprocess/arbitrary code execution of any kind
(EP052_DESIGN.md Section 4/18 -- a path is always treated as data,
never as a command string) and never reads a `file read` result back
into `CommandRouter.dispatch()` or any AI/Agent decision point itself
(EP052_DESIGN.md Section 18's trust-boundary rule -- file content is
untrusted data the moment it is returned to a caller).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.skills.files.backend import FileBackend, FileBackendError, FileEntry

HELP_TEXT: str = (
    "Available file commands (File Automation, EP-052)\n\n"
    "file help\n"
    "file list <dir>\n"
    "file exists <path>\n"
    "file stat <path>\n"
    "file read <path>\n"
    "file write [--overwrite] <path> <text...>\n"
    "file copy [--overwrite] <src> <dst>\n"
    "file move <src> <dst>\n"
    "file mkdir <path>\n"
    "file delete <path>\n\n"
    "Every path must resolve inside a configured 'file.allowed_roots' "
    "entry. 'move', 'delete', and overwriting 'write'/'copy' also "
    "require 'file.allow_destructive: true'. 'delete' does not "
    "recursively remove non-empty directories."
)

ActionHandler = Callable[[list[str]], CommandResult]

_DISABLED_MESSAGE: str = (
    "File Automation is disabled ('file.enabled: false' in "
    "config/config.yaml). Set it to true and restart to enable "
    "'file' actions."
)

_UNAVAILABLE_MESSAGE: str = (
    "File Automation is enabled but no backend is available (backend "
    "construction failed at startup -- check the startup log for "
    "details)."
)

_DESTRUCTIVE_DISABLED_MESSAGE: str = (
    "This action is destructive (move/delete/overwrite) and "
    "'file.allow_destructive: false' in config/config.yaml. Set it to "
    "true and restart to allow it."
)

_NO_ALLOWED_ROOTS_MESSAGE_SUFFIX: str = (
    " -- add at least one entry to 'file.allowed_roots' in "
    "config/config.yaml and restart."
)

_OVERWRITE_FLAG: str = "--overwrite"


class FileModule:
    """The "file" command namespace (EP-052, File Automation).

    Responsibilities:
        - `file list <dir>`: list a directory's immediate children.
        - `file exists <path>`: report whether a path exists.
        - `file stat <path>`: report metadata (size, mtime, type).
        - `file read <path>`: return a text file's UTF-8 content.
        - `file write [--overwrite] <path> <text...>`: create a new
          file, or update an existing one if `--overwrite` is given
          and `file.allow_destructive` is true.
        - `file copy [--overwrite] <src> <dst>`: copy a file to a new
          destination, or replace an existing destination if
          `--overwrite` is given and `file.allow_destructive` is true.
        - `file move <src> <dst>`: move/rename a file or directory.
          Always destructive (requires `file.allow_destructive`);
          never overwrites an existing destination in v1.
        - `file mkdir <path>`: create a single new, empty directory.
          Does not create missing parent directories.
        - `file delete <path>`: delete a file, or an already-empty
          directory. Always destructive. Never recursively deletes a
          non-empty directory (Owner Decision D8).

    Never launches a process/application (that remains EP-003's job)
    and never performs shell/code execution of any kind.
    """

    def __init__(self, config: Config, backend: FileBackend | None) -> None:
        """Initialize the FileModule.

        Args:
            config: The application Config. Read at dispatch time for
                'file.enabled', 'file.allow_destructive',
                'file.allowed_roots', and 'file.denied_paths' -- read
                fresh on every call, not cached, so a config
                reload/restart is the only way to change them
                (matching every other subsystem's flag-reading
                convention).
            backend: The already-constructed `FileBackend` used to
                perform every action. May be None if 'file.enabled' is
                false at startup or backend construction failed --
                every action reports a clear, non-crashing failure
                (`_UNAVAILABLE_MESSAGE`) in that case, never a crash.
        """
        self._config = config
        self._backend = backend
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "list": self._list,
            "exists": self._exists,
            "stat": self._stat,
            "read": self._read,
            "write": self._write,
            "copy": self._copy,
            "move": self._move,
            "mkdir": self._mkdir,
            "delete": self._delete,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace.

        Returns:
            The literal string "file".
        """
        return "file"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "file" action.

        Args:
            action: The requested action (e.g. "read"). May be empty
                if the user entered only "file".
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
                'Type "file help" for available commands.'
            )
            return CommandResult(success=False, message=message)

        return handler(arguments)

    # ---------- Safety gates (EP052_DESIGN.md Section 11/13/20) ----------

    def _is_enabled(self) -> bool:
        """Return whether 'file.enabled' is currently true."""
        return bool(self._config.get("file.enabled", False))

    def _is_destructive_allowed(self) -> bool:
        """Return whether 'file.allow_destructive' is currently true."""
        return bool(self._config.get("file.allow_destructive", False))

    def _allowed_roots(self) -> list:
        """Return the configured, resolved allow-list of permitted roots.

        Read fresh from config on every call. Entries that cannot be
        resolved (e.g. malformed) are skipped rather than crashing the
        whole gate. An empty result means no path is ever permitted
        (Owner Decision D5).
        """
        raw = self._config.get("file.allowed_roots", []) or []
        roots = []
        for entry in raw:
            try:
                roots.append(Path(str(entry)).resolve())
            except (OSError, RuntimeError, ValueError):
                logger.warning(f"file: could not resolve allowed_roots entry '{entry}', skipping.")
        return roots

    def _denied_paths(self) -> list:
        """Return the configured, resolved deny-list (Owner Decision D4)."""
        raw = self._config.get("file.denied_paths", []) or []
        denied = []
        for entry in raw:
            try:
                denied.append(Path(str(entry)).resolve())
            except (OSError, RuntimeError, ValueError):
                logger.warning(f"file: could not resolve denied_paths entry '{entry}', skipping.")
        return denied

    def _gate(self) -> CommandResult | None:
        """Return a failure CommandResult if no action may execute, else None.

        Called by every action handler *after* argument-shape
        validation and *before* any path resolution or `FileBackend`
        call -- guarantees zero backend interaction while disabled or
        unavailable.
        """
        if not self._is_enabled():
            logger.info("file: action rejected, 'file.enabled' is false.")
            return CommandResult(success=False, message=_DISABLED_MESSAGE)
        if self._backend is None:
            logger.warning("file: action rejected, no backend available.")
            return CommandResult(success=False, message=_UNAVAILABLE_MESSAGE)
        return None

    def _destructive_gate(self) -> CommandResult | None:
        """Return a failure CommandResult if destructive actions are disallowed, else None."""
        if not self._is_destructive_allowed():
            logger.info("file: destructive action rejected, 'file.allow_destructive' is false.")
            return CommandResult(success=False, message=_DESTRUCTIVE_DISABLED_MESSAGE)
        return None

    def _resolve_within_allowed(self, raw_path: str):
        """Resolve `raw_path` and check it against the allow/deny-root model.

        Args:
            raw_path: The path argument exactly as supplied by the
                caller.

        Returns:
            A `(resolved_path, None)` tuple on success, or
            `(None, failure_CommandResult)` if the path is invalid or
            refused (EP052_DESIGN.md Section 13 -- resolve to an
            absolute, canonical path *before* any allow/deny-root
            comparison, never compared as a raw string).
        """

        try:
            resolved = Path(raw_path).resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            return None, CommandResult(success=False, message=f"file: invalid path '{raw_path}': {exc}")

        allowed_roots = self._allowed_roots()
        is_allowed = any(
            resolved == root or root in resolved.parents for root in allowed_roots
        )
        if not is_allowed:
            message = f"file: '{raw_path}' is outside the allowed workspace"
            if not allowed_roots:
                message += _NO_ALLOWED_ROOTS_MESSAGE_SUFFIX
            else:
                message += " (file.allowed_roots)."
            logger.info(f"file: path rejected (not in allowed_roots): '{resolved}'.")
            return None, CommandResult(success=False, message=message)

        for denied in self._denied_paths():
            if resolved == denied or denied in resolved.parents:
                logger.info(f"file: path rejected (in denied_paths): '{resolved}'.")
                return None, CommandResult(
                    success=False,
                    message=f"file: '{raw_path}' is inside a denied path (file.denied_paths).",
                )

        return resolved, None

    # ---------- Action handlers ----------

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available file commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _list(self, arguments: list[str]) -> CommandResult:
        """List a directory's immediate children.

        Args:
            arguments: [dir] -- the directory to list.
        """
        if len(arguments) != 1:
            return _usage_error("file list <dir>")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        resolved, path_failure = self._resolve_within_allowed(arguments[0])
        if path_failure is not None:
            return path_failure

        try:
            entries = self._backend.list(resolved)
        except FileBackendError as exc:
            logger.error(f"file list failed: {exc}")
            return CommandResult(success=False, message=f"file list failed: {exc}")

        logger.info(f"file list: '{resolved}' ({len(entries)} entries).")
        if not entries:
            return CommandResult(success=True, message=f"'{resolved}' is empty.")
        lines = [_format_entry(entry) for entry in entries]
        return CommandResult(success=True, message="\n".join(lines))

    def _exists(self, arguments: list[str]) -> CommandResult:
        """Report whether a path exists.

        Args:
            arguments: [path].
        """
        if len(arguments) != 1:
            return _usage_error("file exists <path>")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        resolved, path_failure = self._resolve_within_allowed(arguments[0])
        if path_failure is not None:
            return path_failure

        try:
            found = self._backend.exists(resolved)
        except FileBackendError as exc:
            logger.error(f"file exists failed: {exc}")
            return CommandResult(success=False, message=f"file exists failed: {exc}")

        logger.info(f"file exists: '{resolved}' -> {found}.")
        return CommandResult(success=True, message="true" if found else "false")

    def _stat(self, arguments: list[str]) -> CommandResult:
        """Report metadata (size, modified time, type) for a path.

        Args:
            arguments: [path].
        """
        if len(arguments) != 1:
            return _usage_error("file stat <path>")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        resolved, path_failure = self._resolve_within_allowed(arguments[0])
        if path_failure is not None:
            return path_failure

        try:
            entry = self._backend.stat(resolved)
        except FileBackendError as exc:
            logger.error(f"file stat failed: {exc}")
            return CommandResult(success=False, message=f"file stat failed: {exc}")

        logger.info(f"file stat: '{resolved}'.")
        kind = "directory" if entry.is_dir else "file"
        message = f"{entry.path}: {kind}, {entry.size} bytes, modified {entry.modified}"
        return CommandResult(success=True, message=message)

    def _read(self, arguments: list[str]) -> CommandResult:
        """Return a text file's UTF-8 content.

        Args:
            arguments: [path].
        """
        if len(arguments) != 1:
            return _usage_error("file read <path>")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        resolved, path_failure = self._resolve_within_allowed(arguments[0])
        if path_failure is not None:
            return path_failure

        try:
            content = self._backend.read(resolved)
        except FileBackendError as exc:
            logger.error(f"file read failed: {exc}")
            return CommandResult(success=False, message=f"file read failed: {exc}")

        logger.info(f"file read: '{resolved}' ({len(content)} chars).")
        return CommandResult(success=True, message=content)

    def _write(self, arguments: list[str]) -> CommandResult:
        """Create a new file, or update an existing one (Owner Decision D7).

        Args:
            arguments: [--overwrite] <path> <text...> -- `--overwrite`
                is only required, and only checked against
                `file.allow_destructive`, when `path` already exists.
        """
        overwrite_requested, args = _pop_overwrite_flag(arguments)
        if len(args) < 2:
            return _usage_error("file write [--overwrite] <path> <text...>")
        raw_path = args[0]
        text = " ".join(args[1:])

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        resolved, path_failure = self._resolve_within_allowed(raw_path)
        if path_failure is not None:
            return path_failure

        try:
            already_exists = self._backend.exists(resolved)
        except FileBackendError as exc:
            logger.error(f"file write failed: {exc}")
            return CommandResult(success=False, message=f"file write failed: {exc}")

        if already_exists:
            if not overwrite_requested:
                return CommandResult(
                    success=False,
                    message=(
                        f"file write: '{resolved}' already exists. Use "
                        f"'file write --overwrite {raw_path} ...' to update it."
                    ),
                )
            destructive_failure = self._destructive_gate()
            if destructive_failure is not None:
                return destructive_failure

        try:
            self._backend.write(resolved, text)
        except FileBackendError as exc:
            logger.error(f"file write failed: {exc}")
            return CommandResult(success=False, message=f"file write failed: {exc}")

        verb = "updated" if already_exists else "created"
        logger.info(f"file write: {verb} '{resolved}' ({len(text)} chars).")
        return CommandResult(success=True, message=f"file write: {verb} '{resolved}'.")

    def _copy(self, arguments: list[str]) -> CommandResult:
        """Copy a file to a new destination, or replace an existing one.

        Args:
            arguments: [--overwrite] <src> <dst>.
        """
        overwrite_requested, args = _pop_overwrite_flag(arguments)
        if len(args) != 2:
            return _usage_error("file copy [--overwrite] <src> <dst>")
        raw_src, raw_dst = args

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        src_resolved, src_failure = self._resolve_within_allowed(raw_src)
        if src_failure is not None:
            return src_failure
        dst_resolved, dst_failure = self._resolve_within_allowed(raw_dst)
        if dst_failure is not None:
            return dst_failure

        try:
            src_exists = self._backend.exists(src_resolved)
        except FileBackendError as exc:
            logger.error(f"file copy failed: {exc}")
            return CommandResult(success=False, message=f"file copy failed: {exc}")
        if not src_exists:
            return CommandResult(success=False, message=f"file copy: source '{src_resolved}' does not exist.")

        try:
            dst_exists = self._backend.exists(dst_resolved)
        except FileBackendError as exc:
            logger.error(f"file copy failed: {exc}")
            return CommandResult(success=False, message=f"file copy failed: {exc}")

        if dst_exists:
            if not overwrite_requested:
                return CommandResult(
                    success=False,
                    message=(
                        f"file copy: destination '{dst_resolved}' already exists. "
                        f"Use 'file copy --overwrite {raw_src} {raw_dst}' to replace it."
                    ),
                )
            destructive_failure = self._destructive_gate()
            if destructive_failure is not None:
                return destructive_failure

        try:
            self._backend.copy(src_resolved, dst_resolved)
        except FileBackendError as exc:
            logger.error(f"file copy failed: {exc}")
            return CommandResult(success=False, message=f"file copy failed: {exc}")

        logger.info(f"file copy: '{src_resolved}' -> '{dst_resolved}'.")
        return CommandResult(success=True, message=f"file copy: '{src_resolved}' copied to '{dst_resolved}'.")

    def _move(self, arguments: list[str]) -> CommandResult:
        """Move/rename a file or directory. Always destructive.

        Args:
            arguments: [src, dst].
        """
        if len(arguments) != 2:
            return _usage_error("file move <src> <dst>")
        raw_src, raw_dst = arguments

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        destructive_failure = self._destructive_gate()
        if destructive_failure is not None:
            return destructive_failure

        src_resolved, src_failure = self._resolve_within_allowed(raw_src)
        if src_failure is not None:
            return src_failure
        dst_resolved, dst_failure = self._resolve_within_allowed(raw_dst)
        if dst_failure is not None:
            return dst_failure

        try:
            src_exists = self._backend.exists(src_resolved)
        except FileBackendError as exc:
            logger.error(f"file move failed: {exc}")
            return CommandResult(success=False, message=f"file move failed: {exc}")
        if not src_exists:
            return CommandResult(success=False, message=f"file move: source '{src_resolved}' does not exist.")

        try:
            dst_exists = self._backend.exists(dst_resolved)
        except FileBackendError as exc:
            logger.error(f"file move failed: {exc}")
            return CommandResult(success=False, message=f"file move failed: {exc}")
        if dst_exists:
            return CommandResult(
                success=False,
                message=f"file move: destination '{dst_resolved}' already exists; move does not overwrite in v1.",
            )

        try:
            self._backend.move(src_resolved, dst_resolved)
        except FileBackendError as exc:
            logger.error(f"file move failed: {exc}")
            return CommandResult(success=False, message=f"file move failed: {exc}")

        logger.info(f"file move: '{src_resolved}' -> '{dst_resolved}'.")
        return CommandResult(success=True, message=f"file move: '{src_resolved}' moved to '{dst_resolved}'.")

    def _mkdir(self, arguments: list[str]) -> CommandResult:
        """Create a single new, empty directory. Not destructive.

        Args:
            arguments: [path].
        """
        if len(arguments) != 1:
            return _usage_error("file mkdir <path>")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        resolved, path_failure = self._resolve_within_allowed(arguments[0])
        if path_failure is not None:
            return path_failure

        try:
            self._backend.mkdir(resolved)
        except FileBackendError as exc:
            logger.error(f"file mkdir failed: {exc}")
            return CommandResult(success=False, message=f"file mkdir failed: {exc}")

        logger.info(f"file mkdir: created '{resolved}'.")
        return CommandResult(success=True, message=f"file mkdir: created '{resolved}'.")

    def _delete(self, arguments: list[str]) -> CommandResult:
        """Delete a file, or an already-empty directory. Always destructive.

        Args:
            arguments: [path].
        """
        if len(arguments) != 1:
            return _usage_error("file delete <path>")

        gate_failure = self._gate()
        if gate_failure is not None:
            return gate_failure

        destructive_failure = self._destructive_gate()
        if destructive_failure is not None:
            return destructive_failure

        resolved, path_failure = self._resolve_within_allowed(arguments[0])
        if path_failure is not None:
            return path_failure

        try:
            self._backend.delete(resolved)
        except FileBackendError as exc:
            logger.error(f"file delete failed: {exc}")
            return CommandResult(success=False, message=f"file delete failed: {exc}")

        logger.info(f"file delete: removed '{resolved}'.")
        return CommandResult(success=True, message=f"file delete: removed '{resolved}'.")


def _usage_error(usage: str) -> CommandResult:
    """Return a standard, non-crashing usage-error CommandResult."""
    return CommandResult(success=False, message=f"Invalid arguments. Usage: {usage}")


def _pop_overwrite_flag(arguments: list[str]) -> tuple[bool, list[str]]:
    """Strip a leading '--overwrite' flag from `arguments`, if present.

    Returns:
        (overwrite_requested, remaining_arguments).
    """
    if arguments and arguments[0] == _OVERWRITE_FLAG:
        return True, arguments[1:]
    return False, list(arguments)


def _format_entry(entry: FileEntry) -> str:
    """Format one `FileEntry` as a single, human-readable listing line."""
    kind = "d" if entry.is_dir else "f"
    return f"{kind}  {entry.size:>10}  {entry.name}"
