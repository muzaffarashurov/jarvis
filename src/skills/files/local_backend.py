"""LocalFileBackend: the real, standard-library-only EP-052 FileBackend.

Built entirely on `pathlib`/`shutil` (EP052_DESIGN.md Section 10,
Owner Decision D1) -- no new third-party dependency. Genuinely
cross-platform by design, with no `platform.system()`/`sys.platform`
branching anywhere in this file (EP052_DESIGN.md Section 17, Owner
Decision D10): `pathlib.Path` and `shutil` already handle Windows/
macOS/Linux differences internally.

This class assumes every `Path` it receives has *already* been
resolved to its absolute, canonical form and has *already* passed
`FileModule`'s allow-list/deny-list safety check (EP052_DESIGN.md
Section 13) -- `LocalFileBackend` performs no path-safety checking of
its own. It performs the raw filesystem operation only, translating
every failure into a single `FileBackendError` (EP052_DESIGN.md
Section 15) -- never letting a raw `OSError`/`PermissionError`/
`FileNotFoundError`/`UnicodeDecodeError` propagate out.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from src.skills.files.backend import FileBackendError, FileEntry


class LocalFileBackend:
    """The sole real `FileBackend` implementation (EP-052 v1).

    Text-only (UTF-8) for `read`/`write` (Owner Decision D6); no
    binary read/write in v1. No recursive directory deletion (Owner
    Decision D8) -- `delete` is restricted to single files and
    already-empty directories. No shell/subprocess execution of any
    kind -- every operation is a direct `pathlib`/`shutil` call on a
    path treated purely as data, never as a command string
    (EP052_DESIGN.md Section 18).
    """

    def list(self, path: Path) -> list[FileEntry]:
        """See `FileBackend.list`."""
        if not path.exists():
            raise FileBackendError(f"'{path}' does not exist.")
        if not path.is_dir():
            raise FileBackendError(f"'{path}' is not a directory.")
        try:
            children = sorted(path.iterdir(), key=lambda child: child.name)
            entries: list[FileEntry] = []
            for child in children:
                entries.append(_entry_for(child))
            return entries
        except OSError as exc:
            raise FileBackendError(f"could not list '{path}': {exc}") from exc

    def exists(self, path: Path) -> bool:
        """See `FileBackend.exists`."""
        return path.exists()

    def stat(self, path: Path) -> FileEntry:
        """See `FileBackend.stat`."""
        if not path.exists():
            raise FileBackendError(f"'{path}' does not exist.")
        try:
            return _entry_for(path)
        except OSError as exc:
            raise FileBackendError(f"could not stat '{path}': {exc}") from exc

    def read(self, path: Path) -> str:
        """See `FileBackend.read`."""
        if not path.exists():
            raise FileBackendError(f"'{path}' does not exist.")
        if not path.is_file():
            raise FileBackendError(f"'{path}' is not a regular file.")
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise FileBackendError(f"'{path}' is not valid UTF-8 text: {exc}") from exc
        except OSError as exc:
            raise FileBackendError(f"could not read '{path}': {exc}") from exc

    def write(self, path: Path, content: str) -> None:
        """See `FileBackend.write`."""
        if path.exists() and path.is_dir():
            raise FileBackendError(f"'{path}' is a directory; cannot write a file there.")
        try:
            path.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise FileBackendError(f"could not write '{path}': {exc}") from exc

    def copy(self, src: Path, dst: Path) -> None:
        """See `FileBackend.copy`."""
        if not src.exists():
            raise FileBackendError(f"source '{src}' does not exist.")
        if not src.is_file():
            raise FileBackendError(f"source '{src}' is not a regular file.")
        if dst.exists() and dst.is_dir():
            raise FileBackendError(f"destination '{dst}' is a directory; cannot copy a file there.")
        try:
            shutil.copy2(str(src), str(dst))
        except OSError as exc:
            raise FileBackendError(f"could not copy '{src}' to '{dst}': {exc}") from exc

    def move(self, src: Path, dst: Path) -> None:
        """See `FileBackend.move`."""
        if not src.exists():
            raise FileBackendError(f"source '{src}' does not exist.")
        if dst.exists():
            raise FileBackendError(f"destination '{dst}' already exists.")
        try:
            shutil.move(str(src), str(dst))
        except OSError as exc:
            raise FileBackendError(f"could not move '{src}' to '{dst}': {exc}") from exc

    def mkdir(self, path: Path) -> None:
        """See `FileBackend.mkdir`."""
        if path.exists():
            raise FileBackendError(f"'{path}' already exists.")
        try:
            path.mkdir(parents=False, exist_ok=False)
        except OSError as exc:
            raise FileBackendError(f"could not create directory '{path}': {exc}") from exc

    def delete(self, path: Path) -> None:
        """See `FileBackend.delete`."""
        if not path.exists():
            raise FileBackendError(f"'{path}' does not exist.")
        try:
            if path.is_dir():
                if any(path.iterdir()):
                    raise FileBackendError(
                        f"'{path}' is a non-empty directory; recursive delete "
                        f"is not supported in v1 (Owner Decision D8)."
                    )
                path.rmdir()
            else:
                path.unlink()
        except OSError as exc:
            raise FileBackendError(f"could not delete '{path}': {exc}") from exc


def _entry_for(path: Path) -> FileEntry:
    """Build a `FileEntry` describing an existing path."""
    st = path.stat()
    return FileEntry(
        name=path.name,
        path=str(path),
        is_dir=path.is_dir(),
        is_file=path.is_file(),
        size=st.st_size,
        modified=st.st_mtime,
    )
