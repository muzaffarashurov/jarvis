"""Business logic for integrating EP-019 Project Index Engine into Jarvis.

IndexService is a thin, CLI-facing wrapper around
`src.core.indexing.ProjectIndexer`. It owns no indexing logic itself
-- reading the manifest, discovering documents, chunking and building
a `ProjectIndex` all stay inside `ProjectIndexer` exactly as
implemented for EP-019; this service only forwards calls to it and
adapts the results to `CommandResult`/`IndexStatus` for `IndexModule`,
matching every other Service in this project (see
src/services/memory_service.py's MemoryService -> MemoryStore
pattern):

    IndexModule -> IndexService -> ProjectIndexer

It implements no business logic belonging to any other module and,
per EP-019's own architectural constraint, never imports from
src.core.ai.* (no AI provider, no ContextLoader, no PromptBuilder, no
PromptManager, no ContextManager).

Also holds the `IndexStorage` instance the composition root
(src/bootstrap.py) constructed `ProjectIndexer` with, so `index clear`
can remove persisted state and `index status` can report which
backend is active -- both using only `IndexStorage`'s existing public
API (save/load/clear/exists), never a method invented on
`ProjectIndexer` itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from src.core.command_router import CommandResult
from src.core.indexing import IndexStorage, ProjectIndex, ProjectIndexer


@dataclass(frozen=True)
class IndexStatus:
    """Result of `index status`.

    Attributes:
        project_name: The indexed project's declared name (empty if
            no index has been built yet).
        document_count: Number of indexed documents.
        chunk_count: Number of indexed chunks.
        storage_backend: The concrete `IndexStorage` backend in use
            (e.g. "JsonIndexStorage", "MemoryIndexStorage").
        index_version: The built index's own format version
            (`ProjectIndex.index_format_version`), empty if no index
            has been built yet.
        last_build_time: When the current index was built, or None if
            no index has been built yet.
        built: Whether an index currently exists in memory.
    """

    project_name: str
    document_count: int
    chunk_count: int
    storage_backend: str
    index_version: str
    last_build_time: datetime | None
    built: bool


class IndexService:
    """Coordinates ProjectIndexer and exposes it as a CLI-friendly API.

    Depends only on ProjectIndexer (EP-019) and the IndexStorage
    instance it was constructed with. Implements no indexing logic of
    its own -- every build/rebuild/clear call is forwarded to
    ProjectIndexer unchanged; this class only adapts return values to
    CommandResult/IndexStatus for IndexModule.
    """

    def __init__(self, indexer: ProjectIndexer, storage: IndexStorage) -> None:
        """Initialize the IndexService.

        Args:
            indexer: The ProjectIndexer instance this service wraps.
            storage: The same IndexStorage instance `indexer` was
                constructed with, used for `index clear` and to report
                the active backend in `index status`.
        """
        self._indexer = indexer
        self._storage = storage

    def build(self) -> CommandResult:
        """Build a fresh index from the current manifest and documents, then persist it."""
        try:
            index = self._indexer.build()
        except ValueError as exc:
            logger.error(f"Index build failed: {exc}")
            return CommandResult(success=False, message=str(exc))

        self._indexer.save()
        return CommandResult(success=True, message=self._summary("Index built", index))

    def rebuild(self) -> CommandResult:
        """Force a full rebuild, ignoring cached manifest/document content, then persist it."""
        try:
            index = self._indexer.rebuild()
        except ValueError as exc:
            logger.error(f"Index rebuild failed: {exc}")
            return CommandResult(success=False, message=str(exc))

        self._indexer.save()
        return CommandResult(success=True, message=self._summary("Index rebuilt", index))

    def clear(self) -> CommandResult:
        """Discard the current in-memory index and any persisted copy."""
        self._indexer.clear()
        self._storage.clear()
        return CommandResult(success=True, message="Index cleared.")

    def status(self) -> IndexStatus:
        """Return the `index status` snapshot for the current in-memory index."""
        index: ProjectIndex | None = self._indexer.index()
        backend_name = type(self._storage).__name__

        if index is None:
            return IndexStatus(
                project_name="",
                document_count=0,
                chunk_count=0,
                storage_backend=backend_name,
                index_version="",
                last_build_time=None,
                built=False,
            )

        stats = index.statistics()
        return IndexStatus(
            project_name=index.project_name,
            document_count=stats["document_count"],
            chunk_count=stats["chunk_count"],
            storage_backend=backend_name,
            index_version=index.index_format_version,
            last_build_time=index.created_at,
            built=True,
        )

    @staticmethod
    def _summary(prefix: str, index: ProjectIndex) -> str:
        """Format a one-line build/rebuild summary from a freshly built index."""
        stats = index.statistics()
        return (
            f"{prefix}: '{index.project_name}' "
            f"({stats['document_count']} document(s), {stats['chunk_count']} chunk(s))."
        )
