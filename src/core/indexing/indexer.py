"""ProjectIndexer for the EP-019 Project Index Engine.

ProjectIndexer builds and maintains a `ProjectIndex`: it reads
`PROJECT_MANIFEST.md` (via the shared, subsystem-independent
`src/core/project_manifest.py`), discovers and loads the manifest's
declared Context Documents, splits each into chunks (via
`ChunkBuilder`), and assembles the result into an immutable
`ProjectIndex`.

Responsible only for building the index. This package performs no
retrieval and no AI prompting, and has no dependency on any AI
provider or on any other AI-facing subsystem in this codebase -- see
`src/core/project_manifest.py`'s module docstring for the one
dependency this and the EP-018 Context Engine both share.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from threading import RLock

from loguru import logger

from src.core.indexing.chunk_builder import ChunkBuilder
from src.core.indexing.document import IndexedDocument
from src.core.indexing.index import ProjectIndex
from src.core.indexing.storage import IndexStorage, MemoryIndexStorage
from src.core.project_manifest import (
    MANIFEST_FILENAME,
    DocumentCache,
    ManifestLoader,
    ProjectManifest,
    expand_document_entries,
)

__all__ = ["ProjectIndexer"]


class ProjectIndexer:
    """Builds and maintains a `ProjectIndex` from a project's `PROJECT_MANIFEST.md`.

    Responsibilities: read the manifest, discover its declared Context
    Documents, load their content, split each into chunks, and build a
    `ProjectIndex`. Nothing else -- caching policy (when to rebuild)
    is explicitly out of scope for this EP; only the primitives
    (`build`/`rebuild`/`load`/`save`/`clear`) are exposed.

    Owns its own `ManifestLoader` and `DocumentCache` instances -- each
    is, independently, an instance of the one shared parsing/detection
    implementation in `src/core/project_manifest.py`, so this and any
    other manifest-driven subsystem can never see or invalidate each
    other's cache.

    Thread-safe via its own re-entrant lock.
    """

    def __init__(
        self,
        storage: IndexStorage | None = None,
        chunk_builder: ChunkBuilder | None = None,
        manifest_filename: str = MANIFEST_FILENAME,
    ) -> None:
        """Initialize an empty ProjectIndexer.

        Args:
            storage: Where `save()`/`load()` persist/restore the
                index. Defaults to an in-memory `MemoryIndexStorage`;
                inject a `JsonIndexStorage` (or a future SQLite/Vector
                DB backend) for on-disk persistence.
            chunk_builder: Splits document text into chunks. Defaults
                to `ChunkBuilder()`'s own defaults (1000 characters,
                100 character overlap).
            manifest_filename: The manifest file name to look for.
                Overridable for testing; every real caller should use
                the default.
        """
        self._storage: IndexStorage = storage if storage is not None else MemoryIndexStorage()
        self._chunk_builder = chunk_builder if chunk_builder is not None else ChunkBuilder()
        self._manifest_loader = ManifestLoader(manifest_filename)
        self._document_cache = DocumentCache()
        self._lock = RLock()
        self._index: ProjectIndex | None = None

    def build(self) -> ProjectIndex:
        """Build a fresh `ProjectIndex` from the current manifest and documents.

        Reuses cached manifest/document content while the underlying
        files are unchanged on disk -- see `rebuild()` to force a full
        reread first.

        Returns:
            The newly built index (also becomes `index()`'s current
            value).

        Raises:
            ValueError: If no `PROJECT_MANIFEST.md` could be found.
        """
        logger.info("Index build started.")
        with self._lock:
            manifest = self._manifest_loader.get()
            if manifest is None:
                raise ValueError(
                    "No PROJECT_MANIFEST.md found; ProjectIndexer cannot build an index without one."
                )

            documents: list[IndexedDocument] = []
            for relative_path, _entry in expand_document_entries(manifest):
                document = self._index_document(manifest, relative_path)
                if document is not None:
                    documents.append(document)

            index = ProjectIndex(
                repository_root=str(manifest.repository_root),
                project_name=manifest.project_name,
                version=manifest.version,
                project_type=manifest.project_type,
                description=manifest.description,
                documents=tuple(documents),
            )
            self._index = index

        chunk_count = sum(len(document.chunks()) for document in documents)
        logger.info(f"Index completed: {len(documents)} document(s), {chunk_count} chunk(s).")
        return index

    def rebuild(self) -> ProjectIndex:
        """Force a full rebuild, ignoring cached manifest/document content.

        Returns:
            The newly built index.

        Raises:
            ValueError: If no `PROJECT_MANIFEST.md` could be found.
        """
        with self._lock:
            self._manifest_loader.refresh()
            self._document_cache.clear()
        return self.build()

    def clear(self) -> None:
        """Discard the current in-memory index and its manifest/document caches.

        Does not touch persisted storage -- see `IndexStorage.clear()`
        for that.
        """
        with self._lock:
            self._index = None
            self._manifest_loader.refresh()
            self._document_cache.clear()
        logger.info("Index cleared.")

    def save(self) -> None:
        """Persist the current index via the injected `IndexStorage`.

        Raises:
            ValueError: If no index has been built or loaded yet.
        """
        with self._lock:
            index = self._index
        if index is None:
            raise ValueError("No index to save -- call build() or load() first.")
        self._storage.save(index)

    def load(self) -> ProjectIndex | None:
        """Load a previously saved index via the injected `IndexStorage`.

        Returns:
            The loaded index (also becomes `index()`'s current value),
            or None if nothing has been saved yet.
        """
        index = self._storage.load()
        with self._lock:
            self._index = index
        return index

    def index(self) -> ProjectIndex | None:
        """Return the current index (from the last `build()`/`rebuild()`/`load()`), or None."""
        with self._lock:
            return self._index

    # ---------- Internal ----------

    def _index_document(self, manifest: ProjectManifest, relative_path: str) -> IndexedDocument | None:
        """Load, chunk, and wrap one document; None if it cannot be read."""
        full_path = manifest.repository_root / relative_path
        if not full_path.is_file():
            logger.warning(f"Indexed document not found: '{relative_path}'.")
            return None

        try:
            content, _was_cached = self._document_cache.read(full_path)
            stat = full_path.stat()
        except OSError as exc:
            logger.warning(f"Unable to read indexed document '{relative_path}': {exc}")
            return None

        document_id = _document_id(relative_path)
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        title = _derive_title(content, relative_path)
        chunks = self._chunk_builder.build(document_id, relative_path, content)

        logger.info(f"Document indexed: '{relative_path}' ({len(chunks)} chunk(s)).")
        return IndexedDocument(
            document_id=document_id,
            relative_path=relative_path,
            absolute_path=str(full_path),
            title=title,
            size=stat.st_size,
            last_modified=stat.st_mtime,
            checksum=checksum,
            chunks=chunks,
        )


def _document_id(relative_path: str) -> str:
    """Derive a stable, deterministic document id from its relative path."""
    return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]


def _derive_title(content: str, relative_path: str) -> str:
    """Derive a human-readable title: the first Markdown heading, or the file's stem."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading_text = stripped.lstrip("#").strip()
            if heading_text:
                return heading_text
            break
    return Path(relative_path).stem
