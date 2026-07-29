"""EP-019 Project Index Engine.

A universal, manifest-driven subsystem that scans a repository once
and builds a searchable `ProjectIndex`. Performs indexing only -- no
retrieval, no AI prompting, and no dependency on any AI provider,
PromptBuilder, ContextLoader, or ContextManager.

Public API:
    ProjectIndexer  -- builds and maintains a ProjectIndex.
    ProjectIndex    -- the indexed repository (read-only).
    IndexedDocument -- one indexed document.
    DocumentChunk   -- one immutable indexed chunk.
    ChunkBuilder    -- splits document text into chunks.
    IndexStorage / MemoryIndexStorage / JsonIndexStorage -- persistence.
"""

from __future__ import annotations

from src.core.indexing.chunk import DocumentChunk
from src.core.indexing.chunk_builder import ChunkBuilder
from src.core.indexing.document import IndexedDocument
from src.core.indexing.index import ProjectIndex
from src.core.indexing.indexer import ProjectIndexer
from src.core.indexing.storage import IndexStorage, JsonIndexStorage, MemoryIndexStorage

__all__ = [
    "ChunkBuilder",
    "DocumentChunk",
    "IndexStorage",
    "IndexedDocument",
    "JsonIndexStorage",
    "MemoryIndexStorage",
    "ProjectIndex",
    "ProjectIndexer",
]
