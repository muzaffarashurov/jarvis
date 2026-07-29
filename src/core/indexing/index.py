"""ProjectIndex domain model for the EP-019 Project Index Engine.

Represents the indexed repository as a whole: manifest-derived project
identity, every indexed document, and every chunk. Provides only
read operations -- no AI logic, no retrieval.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.core.indexing.chunk import DocumentChunk
from src.core.indexing.document import IndexedDocument

__all__ = ["ProjectIndex"]

INDEX_FORMAT_VERSION = "1.0"


class ProjectIndex:
    """The indexed repository: project identity, documents, and chunks.

    Immutable and read-only: nothing here mutates an existing index in
    place -- `ProjectIndexer.build()`/`rebuild()` produce a fresh
    instance each time.
    """

    def __init__(
        self,
        repository_root: str,
        project_name: str,
        version: str,
        project_type: str,
        description: str,
        documents: tuple[IndexedDocument, ...] = (),
        metadata: dict[str, Any] | None = None,
        created_at: datetime | None = None,
        index_format_version: str = INDEX_FORMAT_VERSION,
    ) -> None:
        """Initialize an immutable ProjectIndex.

        Args:
            repository_root: The indexed repository's root directory.
            project_name: The manifest's declared project name.
            version: The manifest's declared project version.
            project_type: The manifest's declared project type.
            description: The manifest's declared project description.
            documents: Every document that participated in indexing.
            metadata: Arbitrary extra data. Copied defensively.
            created_at: When this index was built. Defaults to now
                (UTC).
            index_format_version: Version of this index's own
                structure (distinct from `version`, the *project's*
                version) -- lets future storage backends detect and
                migrate an older on-disk format.
        """
        self._repository_root = repository_root
        self._project_name = project_name
        self._version = version
        self._project_type = project_type
        self._description = description
        self._documents = tuple(documents)
        self._documents_by_id = {document.document_id: document for document in self._documents}
        self._chunks_by_id: dict[str, DocumentChunk] = {}
        for document in self._documents:
            for chunk in document.chunks():
                self._chunks_by_id[chunk.chunk_id] = chunk
        self._metadata = dict(metadata) if metadata else {}
        self._created_at = created_at if created_at is not None else datetime.now(UTC)
        self._index_format_version = index_format_version

    @property
    def repository_root(self) -> str:
        """Return the indexed repository's root directory."""
        return self._repository_root

    @property
    def project_name(self) -> str:
        """Return the manifest's declared project name."""
        return self._project_name

    @property
    def version(self) -> str:
        """Return the manifest's declared project version."""
        return self._version

    @property
    def project_type(self) -> str:
        """Return the manifest's declared project type."""
        return self._project_type

    @property
    def description(self) -> str:
        """Return the manifest's declared project description."""
        return self._description

    @property
    def created_at(self) -> datetime:
        """Return when this index was built."""
        return self._created_at

    @property
    def index_format_version(self) -> str:
        """Return this index's own structure version."""
        return self._index_format_version

    def documents(self) -> tuple[IndexedDocument, ...]:
        """Return every indexed document, in indexing order."""
        return self._documents

    def chunks(self) -> tuple[DocumentChunk, ...]:
        """Return every chunk from every document, in indexing order."""
        return tuple(self._chunks_by_id.values())

    def document(self, document_id: str) -> IndexedDocument | None:
        """Return the document with `document_id`, or None if not found."""
        return self._documents_by_id.get(document_id)

    def chunk(self, chunk_id: str) -> DocumentChunk | None:
        """Return the chunk with `chunk_id`, or None if not found."""
        return self._chunks_by_id.get(chunk_id)

    def metadata(self) -> dict[str, Any]:
        """Return a defensive copy of this index's metadata."""
        return dict(self._metadata)

    def statistics(self) -> dict[str, Any]:
        """Return summary statistics for this index.

        Returns:
            A dict with `document_count`, `chunk_count`,
            `total_characters` (summed across every chunk), and
            `average_chunk_size` (0 if there are no chunks).
        """
        chunk_count = len(self._chunks_by_id)
        total_characters = sum(chunk.character_count for chunk in self._chunks_by_id.values())
        return {
            "document_count": len(self._documents),
            "chunk_count": chunk_count,
            "total_characters": total_characters,
            "average_chunk_size": (total_characters / chunk_count) if chunk_count else 0,
        }

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this index."""
        return {
            "repository_root": self._repository_root,
            "project_name": self._project_name,
            "version": self._version,
            "project_type": self._project_type,
            "description": self._description,
            "documents": [document.to_dict() for document in self._documents],
            "metadata": dict(self._metadata),
            "created_at": self._created_at.isoformat(),
            "index_format_version": self._index_format_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectIndex:
        """Reconstruct a ProjectIndex from `to_dict()`'s output."""
        created_at_raw = data.get("created_at")
        created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else None
        return cls(
            repository_root=data["repository_root"],
            project_name=data.get("project_name", ""),
            version=data.get("version", ""),
            project_type=data.get("project_type", ""),
            description=data.get("description", ""),
            documents=tuple(IndexedDocument.from_dict(item) for item in data.get("documents", [])),
            metadata=data.get("metadata") or {},
            created_at=created_at,
            index_format_version=data.get("index_format_version", INDEX_FORMAT_VERSION),
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProjectIndex):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        return (
            f"ProjectIndex(project_name={self._project_name!r}, "
            f"documents={len(self._documents)}, chunks={len(self._chunks_by_id)})"
        )
