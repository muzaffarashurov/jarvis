"""Project manifest parsing and repository detection.

This is the single place `PROJECT_MANIFEST.md` is ever parsed and the
single place a project's repository root is ever detected -- see
`AI_GENERATION_STANDARD.md`'s "Single Source of Truth" rule. Every
`PROJECT_MANIFEST`-driven subsystem depends on this module instead of
re-implementing (or importing from) any other subsystem's private
internals.

Current consumers:
    - The EP-018 Context Engine (`src/core/ai/context_loader.py`),
      which layers priority ordering, a character budget, and section
      rendering on top of what this module resolves.
    - The EP-019 Project Index Engine (`src/core/indexing/`), which
      layers chunking and persistent storage on top of the same
      resolved manifest and document set.

This module has no dependency on Config, on any AI provider, or on
either of the subsystems above -- only the manifest file format and
the filesystem. Each consumer owns its own `ManifestLoader` /
`DocumentCache` *instance*: caching is per-consumer, never shared
global state, so two independent subsystems can never see (or
invalidate) each other's cache.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any

from loguru import logger

__all__ = [
    "DEFAULT_IGNORE_DIRECTORIES",
    "DEFAULT_MAX_DOCUMENT_BYTES",
    "DEFAULT_PRIORITY",
    "DOCUMENTS_HEADING",
    "MANIFEST_FILENAME",
    "TEXT_EXTENSIONS",
    "DocumentCache",
    "ManifestDocument",
    "ManifestLoader",
    "ProjectManifest",
    "expand_document_entries",
    "find_manifest_path",
    "parse_manifest",
    "relative_path",
]

# The single project-specific file name this module ever hardcodes.
MANIFEST_FILENAME = "PROJECT_MANIFEST.md"
_MAX_SEARCH_DEPTH = 32

# The manifest heading listing every project document a consumer may
# load: a list of file paths and/or directory references (path ending
# in '/'). This is the sole source of "project documents" -- no form
# of automatic/keyword/semantic document discovery beyond what the
# manifest explicitly declares is ever performed here.
DOCUMENTS_HEADING = "Context Documents"

DEFAULT_PRIORITY = "medium"
_PRIORITY_WEIGHTS = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# Safety net on top of the manifest's own ignore rules: never read a
# binary/asset file, never descend into well-known noise directories.
TEXT_EXTENSIONS = frozenset(
    {".md", ".txt", ".rst", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".json", ".xml", ".csv"}
)
DEFAULT_IGNORE_DIRECTORIES = frozenset({".git", ".venv", "__pycache__", "node_modules", "dist", "build"})
DEFAULT_MAX_DOCUMENT_BYTES = 512_000


@dataclass(frozen=True)
class ManifestDocument:
    """One document-category entry: a repository-relative path or directory reference."""

    path: str
    priority: str = DEFAULT_PRIORITY


@dataclass(frozen=True)
class ProjectManifest:
    """The parsed contents of one project's `PROJECT_MANIFEST.md`."""

    repository_root: Path
    project_name: str
    version: str
    project_type: str
    description: str
    documents: tuple[ManifestDocument, ...]
    sections: frozenset[str]
    configuration_files: tuple[str, ...]
    active_process_hint: str
    ignore_directories: frozenset[str]
    ignore_paths: tuple[str, ...]
    ignore_file_patterns: tuple[str, ...]


def priority_weight(priority: str) -> int:
    """Map a document priority label to a sort weight (lower sorts first)."""
    return _PRIORITY_WEIGHTS.get(priority.lower(), _PRIORITY_WEIGHTS[DEFAULT_PRIORITY])


def find_manifest_path(filename: str = MANIFEST_FILENAME) -> Path | None:
    """Locate a manifest file by walking upward from likely starting points.

    Repository root is never hardcoded or assumed -- it is always the
    directory the manifest is actually found in. The current working
    directory is authoritative (the common case: a process launched
    from within the target project); the directory this module itself
    lives in is only a deterministic fallback for when the caller's
    cwd is outside the project entirely, tried in a fixed order so two
    candidate manifests are never raced.

    Args:
        filename: The manifest file name to look for.

    Returns:
        The manifest's path, or None if none was found.
    """
    cwd = Path.cwd().resolve()
    module_dir = Path(__file__).resolve().parent
    starting_points = [cwd] if module_dir == cwd else [cwd, module_dir]

    for start in starting_points:
        current = start
        for _ in range(_MAX_SEARCH_DEPTH):
            candidate = current / filename
            if candidate.is_file():
                return candidate
            if current.parent == current:
                break
            current = current.parent
    return None


def relative_path(path: Path, repository_root: Path) -> str:
    """Return `path` relative to `repository_root`, forward-slashed; falls back to `path` itself."""
    try:
        return path.resolve().relative_to(repository_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def parse_manifest(text: str, manifest_path: Path) -> ProjectManifest:
    """Parse a `PROJECT_MANIFEST.md`'s content into a `ProjectManifest`.

    The format is itself project-independent: '#' headings are fixed,
    known categories; a heading's body is a list if any of its lines
    start with '- ' (each item optionally carrying indented 'key:
    value' attributes), otherwise a plain scalar paragraph. Only the
    *category names* below are ever hardcoded -- their content never is.

    Args:
        text: The manifest file's raw text content.
        manifest_path: Path the text was read from (used to resolve
            the repository root).

    Returns:
        The parsed manifest.
    """
    sections = _parse_sections(text)
    return ProjectManifest(
        repository_root=_resolve_repository_root(sections, manifest_path),
        project_name=_scalar(sections, "Project Name"),
        version=_scalar(sections, "Current Version"),
        project_type=_scalar(sections, "Project Type"),
        description=_scalar(sections, "Project Description"),
        documents=tuple(_documents_from(sections.get(DOCUMENTS_HEADING))),
        sections=_parse_context_sections(sections),
        configuration_files=_string_list(sections, "Configuration Files"),
        active_process_hint=_first_item(sections, "Active Processes"),
        ignore_directories=frozenset(_string_list(sections, "Ignore Directories")),
        ignore_paths=_string_list(sections, "Ignore Paths"),
        ignore_file_patterns=_string_list(sections, "Ignore Files"),
    )


def expand_document_entries(manifest: ProjectManifest) -> list[tuple[str, ManifestDocument]]:
    """Expand manifest document entries into ordered, deduplicated (relative_path, entry) pairs.

    A path ending in '/' (or an existing directory) is expanded into
    every text file beneath it, honoring ignore rules and the
    text/binary safety whitelist. Any other path is kept as a single
    candidate (existence is checked later by the caller).

    Args:
        manifest: The parsed manifest to expand documents from.

    Returns:
        Ordered, deduplicated (relative_path, ManifestDocument) pairs,
        in manifest declaration order.
    """
    ignore_directories = DEFAULT_IGNORE_DIRECTORIES | manifest.ignore_directories
    results: list[tuple[str, ManifestDocument]] = []
    seen: set[str] = set()
    for document in manifest.documents:
        for resolved_path in _expand_document(manifest, document, ignore_directories):
            rel = relative_path(resolved_path, manifest.repository_root)
            if rel in seen:
                continue
            seen.add(rel)
            results.append((rel, document))
    return results


class ManifestLoader:
    """Loads and caches a parsed `ProjectManifest`, reusing the cache while the file is unchanged on disk.

    Thread-safe via its own re-entrant lock. Each consumer
    (`ContextLoader`, `ProjectIndexer`, ...) owns an independent
    `ManifestLoader` instance -- caches are per-consumer, never shared
    across subsystems.
    """

    def __init__(self, filename: str = MANIFEST_FILENAME) -> None:
        """Initialize an empty ManifestLoader.

        Args:
            filename: The manifest file name to look for.
        """
        self._filename = filename
        self._lock = RLock()
        self._cache: tuple[Path, float, ProjectManifest] | None = None

    def get(self) -> ProjectManifest | None:
        """Return the parsed manifest, reusing the cache while the file is unchanged.

        Returns:
            The parsed manifest, or None if no manifest could be found
            or read.
        """
        manifest_path = find_manifest_path(self._filename)
        if manifest_path is None:
            logger.warning(f"'{self._filename}' not found; manifest-driven behavior is disabled.")
            return None

        try:
            mtime = manifest_path.stat().st_mtime
        except OSError as exc:
            logger.warning(f"Unable to inspect manifest '{manifest_path}': {exc}")
            return None

        with self._lock:
            cached = self._cache
        if cached is not None and cached[0] == manifest_path and cached[1] == mtime:
            return cached[2]

        try:
            text = manifest_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning(f"Unable to read manifest '{manifest_path}': {exc}")
            return None

        manifest = parse_manifest(text, manifest_path)
        with self._lock:
            self._cache = (manifest_path, mtime, manifest)
        logger.info(f"Manifest loaded: '{manifest_path}' (project '{manifest.project_name or 'unnamed'}').")
        return manifest

    def refresh(self) -> None:
        """Invalidate the cache so the next `get()` rereads the manifest from disk."""
        with self._lock:
            self._cache = None


class DocumentCache:
    """Caches document content read from disk, keyed by resolved path and mtime.

    Each consumer owns its own instance -- content caching is
    per-consumer, never shared global state.
    """

    def __init__(self, max_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES) -> None:
        """Initialize an empty DocumentCache.

        Args:
            max_bytes: Hard cap, in bytes, on how much of any single
                file is read into memory.
        """
        self._max_bytes = max_bytes
        self._lock = RLock()
        self._entries: dict[str, tuple[float, str]] = {}

    def read(self, path: Path) -> tuple[str, bool]:
        """Read one document, reusing the cache while its mtime is unchanged.

        Files larger than the configured cap are truncated at read
        time (logged, never raised) as a hard safety net.

        Args:
            path: The file to read.

        Returns:
            (content, was_served_from_cache).

        Raises:
            OSError: If the file cannot be stat'd or read.
        """
        key = str(path.resolve())
        stat = path.stat()
        mtime = stat.st_mtime

        with self._lock:
            cached_entry = self._entries.get(key)
        if cached_entry is not None and cached_entry[0] == mtime:
            return cached_entry[1], True

        if stat.st_size > self._max_bytes:
            logger.warning(f"Document '{path}' is {stat.st_size} bytes; capping the read at {self._max_bytes}.")

        with path.open("r", encoding="utf-8", errors="replace") as file:
            content = file.read(self._max_bytes)

        with self._lock:
            self._entries[key] = (mtime, content)
        return content, False

    def clear(self) -> None:
        """Remove every cached document, so the next `read()` rereads from disk."""
        with self._lock:
            self._entries.clear()


# ---------- Internal parsing helpers ----------


def _expand_document(
    manifest: ProjectManifest, document: ManifestDocument, ignore_directories: frozenset[str]
) -> list[Path]:
    """Expand one manifest document entry into concrete candidate file paths."""
    target = manifest.repository_root / document.path
    if not document.path.endswith("/") and not target.is_dir():
        return [target]
    if not target.is_dir():
        return []

    results: list[Path] = []
    for path in sorted(target.rglob("*")):
        if not path.is_file():
            continue
        if any(part in ignore_directories for part in path.relative_to(manifest.repository_root).parts):
            continue
        rel = relative_path(path, manifest.repository_root)
        if any(rel.startswith(prefix) for prefix in manifest.ignore_paths):
            continue
        if any(fnmatch.fnmatch(path.name, pattern) for pattern in manifest.ignore_file_patterns):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        results.append(path)
    return results


def _parse_sections(text: str) -> dict[str, list[Any]]:
    """Split a manifest's raw text into `heading -> parsed body` pairs."""
    raw_bodies: dict[str, list[str]] = {}
    current_heading: str | None = None
    for line in text.splitlines():
        if line.startswith("# ") and not line.startswith("## "):
            current_heading = line[2:].strip()
            raw_bodies.setdefault(current_heading, [])
            continue
        if current_heading is not None:
            raw_bodies[current_heading].append(line)
    return {heading: _parse_body(lines) for heading, lines in raw_bodies.items()}


def _parse_body(lines: list[str]) -> Any:
    """Parse one heading's body into a list (bullets, optionally with 'key: value' attributes) or a scalar string."""
    items: list[Any] = []
    scalar_lines: list[str] = []
    is_list = False
    current_item: dict[str, str] | str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("- "):
            is_list = True
            if current_item is not None:
                items.append(current_item)
            body = stripped[2:].strip()
            if ":" in body:
                key, _, value = body.partition(":")
                current_item = {key.strip(): value.strip()}
            else:
                current_item = body
            continue

        if is_list and isinstance(current_item, dict) and line.startswith((" ", "\t")) and ":" in stripped:
            key, _, value = stripped.partition(":")
            current_item[key.strip()] = value.strip()
            continue

        if not is_list:
            scalar_lines.append(stripped)

    if current_item is not None:
        items.append(current_item)
    return items if is_list else " ".join(scalar_lines).strip()


def _scalar(sections: dict[str, Any], heading: str) -> str:
    """Return heading `heading`'s scalar value, or "" if absent/list-shaped."""
    value = sections.get(heading, "")
    return value if isinstance(value, str) else ""


def _string_list(sections: dict[str, Any], heading: str) -> tuple[str, ...]:
    """Return heading `heading`'s list items as plain strings, or () if absent/scalar."""
    value = sections.get(heading, [])
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _first_item(sections: dict[str, Any], heading: str) -> str:
    """Return the first item of a list-shaped heading, or the scalar itself if not a list."""
    value = sections.get(heading, "")
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    return value


def _documents_from(raw_items: Any) -> list[ManifestDocument]:
    """Convert one document-category heading's parsed body into `ManifestDocument`s."""
    if not isinstance(raw_items, list):
        return []
    documents: list[ManifestDocument] = []
    for item in raw_items:
        if isinstance(item, dict):
            path = item.get("path", "").strip()
            priority = (item.get("priority") or DEFAULT_PRIORITY).strip().lower()
        else:
            path = str(item).strip()
            priority = DEFAULT_PRIORITY
        if path:
            documents.append(ManifestDocument(path=path, priority=priority or DEFAULT_PRIORITY))
    return documents


def _parse_context_sections(sections: dict[str, Any]) -> frozenset[str]:
    """Parse "Context Sections" into active, lowercased section names (empty if absent -- caller decides the default)."""
    return frozenset(name.lower() for name in _string_list(sections, "Context Sections"))


def _resolve_repository_root(sections: dict[str, Any], manifest_path: Path) -> Path:
    """Resolve the repository root: the manifest's own directory, or its explicit override."""
    default_root = manifest_path.parent
    override = _scalar(sections, "Repository Root")
    if not override:
        return default_root
    override_path = Path(override)
    if not override_path.is_absolute():
        override_path = default_root / override_path
    return override_path.resolve()
