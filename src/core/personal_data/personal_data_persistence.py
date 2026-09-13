"""Low-level JSONL file I/O for EP-092 Personal Data Collection Framework.

`PersonalDataPersistence` performs narrowly-scoped, append-only JSONL
file I/O only -- append one already-serialized line to the correct
`data/database/personal_data/<category>.jsonl` file, and iterate the
lines already stored in a category's file. It is scoped the same way
`src/core/memory/memory_persistence.py` is scoped to Memory's on-disk
snapshot mechanics: a second, narrow layer of the Store/Persistence
split, not a new architecture.

This class has no knowledge of `PersonalDataPoint`, dedup, or
category semantics beyond a category name mapping to one file. It is
used exclusively by `JsonlPersonalDataProvider`
(`personal_data_provider.py`) -- never called directly by
`PersonalDataManager`, `PersonalDataService`, or any
`PersonalDataSource`. It is not a second storage-provider
abstraction: it implements no `PersonalDataProvider` and exposes no
`store`/`query`/`exists`/`stats` surface.

Category names are validated here, at the single point every category
string is turned into a filesystem path (`category_path()`), per
EP-092 STEP 3 audit finding EP092-AUDIT-001: `category` originates
from `PersonalDataSource.category` -- untrusted input, per the STEP 1
design's §15 principle -- and must never be usable to escape
'personal_data.storage_root'. Validation uses an allowlist (only
letters, digits, `_`, `-`), which rejects path separators, `..`,
absolute paths, and any other traversal form by construction rather
than by enumerating forbidden patterns.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from loguru import logger

from src.core.config import Config

DEFAULT_STORAGE_ROOT: str = "data/database/personal_data"

# Allowlist: only plain identifier-like category names are accepted.
# Rejects path separators ('/', '\\'), '..', absolute paths, empty
# strings, and any other character that could influence path
# resolution -- by construction, not by enumerating forbidden forms.
_CATEGORY_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class PersonalDataPersistenceError(Exception):
    """Raised for invalid Personal Data Collection persistence operations (EP-092).

    Raised by `category_path()` (and therefore by `append_line()` /
    `read_lines()`, which both resolve their path through it) when
    `category` is not a safe filesystem path component -- see
    `_validate_category()`.
    """


def _validate_category(category: str) -> None:
    """Validate that `category` is safe to use as a filesystem path component.

    Args:
        category: The category name to validate.

    Raises:
        PersonalDataPersistenceError: If `category` is empty or
            contains anything other than letters, digits, `_`, or `-`
            -- this rejects path separators, `..` traversal, absolute
            paths, and any other traversal-capable input by
            construction (an allowlist, not a blocklist).
    """
    if not category or not _CATEGORY_PATTERN.fullmatch(category):
        raise PersonalDataPersistenceError(
            f"Invalid personal data category {category!r}: category names must contain only "
            "letters, digits, '_', and '-' (no path separators, '..', or absolute paths)."
        )


class PersonalDataPersistence:
    """Owns append/read access to `data/database/personal_data/<category>.jsonl` files.

    Reads only its own setting from Config ('personal_data.
    storage_root') and depends on nothing beyond the standard library.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the persistence layer (performs no I/O yet).

        Args:
            config: Loaded application configuration, used to resolve
                'personal_data.storage_root'.
        """
        self._config = config

    def storage_root(self) -> Path:
        """Resolve the configured storage root ('personal_data.storage_root')."""
        configured = self._config.get("personal_data.storage_root", DEFAULT_STORAGE_ROOT)
        return Path(str(configured))

    def category_path(self, category: str) -> Path:
        """Return the `.jsonl` file path for `category` (may not exist yet).

        Raises:
            PersonalDataPersistenceError: If `category` is not a safe
                filesystem path component (see `_validate_category()`).
                This is the single point every category string is
                turned into a path -- both `append_line()` and
                `read_lines()` resolve their path through this method,
                so both the write and read directions are protected.
        """
        _validate_category(category)
        return self.storage_root() / f"{category}.jsonl"

    def known_categories(self) -> list[str]:
        """Return every category with an existing `.jsonl` file, sorted.

        Returns:
            Category names derived from existing file stems. Empty if
            the storage root does not exist yet (nothing has been
            collected).
        """
        root = self.storage_root()
        if not root.exists():
            return []
        return sorted(path.stem for path in root.glob("*.jsonl") if path.is_file())

    def append_line(self, category: str, line: str) -> None:
        """Append one already-serialized line to `category`'s `.jsonl` file.

        Args:
            category: The category whose file the line belongs in.
                Validated by `category_path()` -- see
                `PersonalDataPersistenceError`.
            line: The already-serialized (e.g. `json.dumps(...)`)
                line to append. A trailing newline is added; `line`
                itself must not contain an embedded newline.

        Raises:
            PersonalDataPersistenceError: If `category` is not a safe
                filesystem path component.
            OSError: If the storage root cannot be created or the
                file cannot be written.
        """
        path = self.category_path(category)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(line)
            file.write("\n")

    def read_lines(self, category: str) -> Iterator[str]:
        """Iterate every persisted line for `category`, in file order.

        Args:
            category: The category to read. Validated by
                `category_path()` -- see `PersonalDataPersistenceError`.
                Because this method is a generator, that validation
                runs on the first iteration, not at call time.

        Yields:
            Each non-empty line in `category`'s `.jsonl` file, with
            the trailing newline stripped. Yields nothing if the file
            does not exist yet.

        Raises:
            PersonalDataPersistenceError: If `category` is not a safe
                filesystem path component (raised on first iteration).
            OSError: If the file exists but cannot be read.
        """
        path = self.category_path(category)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as file:
            for raw_line in file:
                stripped = raw_line.strip()
                if stripped:
                    yield stripped

    def line_count(self, category: str) -> int:
        """Return the number of persisted lines for `category`.

        A simple, best-effort count used by `stats()` -- reads the
        file once; never keeps a second cached count (Single Source
        Of Truth: the file itself).
        """
        try:
            return sum(1 for _ in self.read_lines(category))
        except (OSError, PersonalDataPersistenceError) as exc:
            logger.error(f"Personal data storage read failed for '{category}': {exc}")
            return 0
