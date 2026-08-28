"""FileBackend: the EP-052 File Automation filesystem abstraction.

This is the *only* interface `FileModule` (`skill.py`) depends on. It
defines the smallest useful contract EP-052 v1 needs -- the ten
approved actions (`list`, `exists`, `stat`, `read`, `write`, `copy`,
`move`, `mkdir`, `delete`, `help`; EP052_DESIGN.md Section 9, Owner
Decision D2) -- and nothing else. It deliberately exposes no shell/
process execution, browser automation, OCR/vision, cloud storage, or
archive-handling capability (EP052_DESIGN.md Section 4); those are
either permanently out of scope or another EP's territory.

Path safety (allow-list/deny-list resolution, EP052_DESIGN.md Section
13) is enforced entirely at the `FileModule` boundary, *before* any
`FileBackend` method is called -- every `Path` this interface receives
is already resolved to its absolute, canonical form and has already
passed the allow/deny-root check. `FileBackend` implementations
perform the raw filesystem operation only; they are not responsible
for, and must not re-implement, the safety model.

Two implementations exist:
    - `LocalFileBackend` (`local_backend.py`): the real, standard-
      library-only implementation (EP052_DESIGN.md Section 10, Owner
      Decision D1).
    - `_FakeFileBackend` (`tests/EP052/test_file.py`): a deterministic,
      test-only stand-in, following the same fake-class testing
      convention `_FakeComputerUseBackend`/`_FakeBrowserBackend`
      already established (EP052_DESIGN.md Section 16).

This module contains no filesystem-facing logic itself -- it is a
pure interface, mirroring `ComputerUseBackend`'s/`BrowserBackend`'s
role for their own EPs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "FileEntry",
    "FileBackendError",
    "FileBackend",
]


@dataclass(frozen=True)
class FileEntry:
    """Metadata describing a single filesystem entry.

    Returned by `FileBackend.list()` (one per directory child) and
    `FileBackend.stat()` (describing the queried path itself). A
    plain, frozen dataclass with no behavior -- mirroring
    `ScreenSize`/`CursorPosition`/`Screenshot`'s established
    precedent (EP052_DESIGN.md Section 14).
    """

    name: str
    path: str
    is_dir: bool
    is_file: bool
    size: int
    modified: float


class FileBackendError(Exception):
    """Raised when a FileBackend operation cannot be completed.

    `FileModule` catches this (and only this) exception type from
    every backend call and translates it into a failed `CommandResult`
    (EP052_DESIGN.md Section 15) -- it is never allowed to propagate
    through `CommandRouter.dispatch()` uncaught. Implementations must
    never let a raw `OSError`/`PermissionError`/`FileNotFoundError`
    escape -- every failure is translated into `FileBackendError`
    with a clear, non-leaking message.
    """


@runtime_checkable
class FileBackend(Protocol):
    """The filesystem contract every File Automation backend must implement.

    Every method performs exactly one, synchronous filesystem
    operation on an already-resolved, already-safety-checked `Path`
    and returns immediately -- there is no multi-step operation, no
    queued/batched action, and no recursive directory deletion in v1
    (EP052_DESIGN.md Section 9/13, Owner Decision D8: `delete` is
    restricted to single files and already-empty directories).

    Implementations must raise `FileBackendError` (only) for any
    failure -- never a bare/unrelated exception type -- so
    `FileModule` has one, single exception type to catch.
    """

    def list(self, path) -> list[FileEntry]:
        """Return the immediate children of the directory at `path`.

        Args:
            path: An already-resolved, already-safety-checked
                directory path.

        Returns:
            One `FileEntry` per direct child, in a stable order.

        Raises:
            FileBackendError: If `path` does not exist, is not a
                directory, or cannot be listed (e.g. permission
                error).
        """
        ...

    def exists(self, path) -> bool:
        """Return whether `path` currently exists (file or directory)."""
        ...

    def stat(self, path) -> FileEntry:
        """Return metadata describing `path` itself.

        Raises:
            FileBackendError: If `path` does not exist or cannot be
                inspected.
        """
        ...

    def read(self, path) -> str:
        """Return the UTF-8 text content of the file at `path`.

        Binary content is out of scope for v1 (EP052_DESIGN.md Owner
        Decision D6) -- non-UTF-8 content is a `FileBackendError`,
        not a silent, lossy decode.

        Raises:
            FileBackendError: If `path` does not exist, is not a
                regular file, is not valid UTF-8, or cannot be read.
        """
        ...

    def write(self, path, content: str) -> None:
        """Write `content` to `path` as UTF-8 text, unconditionally.

        Whether this is a CREATE or an UPDATE, and whether an
        existing file may be overwritten at all, is decided by
        `FileModule` *before* this method is ever called (Owner
        Decision D7) -- by the time `write()` runs, the caller has
        already confirmed the operation is permitted.

        Raises:
            FileBackendError: If `path` is a directory, or the write
                otherwise fails.
        """
        ...

    def copy(self, src, dst) -> None:
        """Copy the file at `src` to `dst`, unconditionally.

        Whether `dst` may already exist (overwrite) is decided by
        `FileModule` before this method is ever called (Owner
        Decision D7), mirroring `write()`.

        Raises:
            FileBackendError: If `src` does not exist or is not a
                regular file, or the copy otherwise fails.
        """
        ...

    def move(self, src, dst) -> None:
        """Move/rename the file or directory at `src` to `dst`.

        Args:
            src: An already-resolved, already-safety-checked source
                path that `FileModule` has already confirmed exists.
            dst: An already-resolved, already-safety-checked
                destination path that `FileModule` has already
                confirmed does not exist (v1 does not overwrite on
                move).

        Raises:
            FileBackendError: If `src` does not exist, or the move
                otherwise fails.
        """
        ...

    def mkdir(self, path) -> None:
        """Create a single new, empty directory at `path`.

        Does not create missing parent directories (v1 does not
        silently create arbitrary parent trees) and does not succeed
        if `path` already exists.

        Raises:
            FileBackendError: If the parent directory does not exist,
                `path` already exists, or creation otherwise fails.
        """
        ...

    def delete(self, path) -> None:
        """Delete the file, or already-empty directory, at `path`.

        Recursive deletion of a non-empty directory is out of scope
        for v1 (Owner Decision D8) -- this must fail cleanly, never
        fall back to a recursive delete.

        Raises:
            FileBackendError: If `path` does not exist, is a
                non-empty directory, or deletion otherwise fails.
        """
        ...
