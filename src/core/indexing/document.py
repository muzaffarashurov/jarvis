"""IndexedDocument domain model for the EP-019 Project Index Engine.

Represents one document that participated in indexing, plus its
ordered chunks. Carries no AI logic and no knowledge of any provider
-- pure indexed data (see `chunk.py`'s module docstring).
"""

from __future__ import annotations

from typing import Any

from src.core.indexing.chunk import DocumentChunk

__all__ = ["IndexedDocument"]


class IndexedDocument:
    """One indexed document: its identity, filesystem metadata, and ordered chunks.

    Attributes:
        document_id: Unique, stable identifier for this document.
        relative_path: Repository-relative path.
        absolute_path: Absolute filesystem path at index time.
        title: A human-readable title (the document's first heading,
            or its file name if it has none).
        size: File size in bytes at index time.
        last_modified: The file's modification time (Unix epoch
            seconds) at index time.
        checksum: SHA-256 hex digest of the document's indexed content,
            for detecting changes between rebuilds.

    Immutable after construction: `chunks()` and `metadata()` both
    return defensive copies/tuples so callers can never mutate
    internal state.
    """

    __slots__ = (
        "_absolute_path",
        "_checksum",
        "_chunks",
        "_document_id",
        "_last_modified",
        "_metadata",
        "_relative_path",
        "_size",
        "_title",
    )

    def __init__(
        self,
        document_id: str,
        relative_path: str,
        absolute_path: str,
        title: str,
        size: int,
        last_modified: float,
        checksum: str,
        chunks: tuple[DocumentChunk, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize an immutable IndexedDocument.

        Args:
            document_id: Unique, stable identifier for this document.
            relative_path: Repository-relative path.
            absolute_path: Absolute filesystem path at index time.
            title: A human-readable title for this document.
            size: File size in bytes at index time.
            last_modified: The file's modification time (Unix epoch
                seconds) at index time.
            checksum: SHA-256 hex digest of the document's indexed
                content.
            chunks: This document's ordered chunks.
            metadata: Arbitrary extra data. Copied defensively.
        """
        self._document_id = document_id
        self._relative_path = relative_path
        self._absolute_path = absolute_path
        self._title = title
        self._size = size
        self._last_modified = last_modified
        self._checksum = checksum
        self._chunks = tuple(chunks)
        self._metadata = dict(metadata) if metadata else {}

    @property
    def document_id(self) -> str:
        """Return this document's unique identifier."""
        return self._document_id

    @property
    def relative_path(self) -> str:
        """Return this document's repository-relative path."""
        return self._relative_path

    @property
    def absolute_path(self) -> str:
        """Return this document's absolute filesystem path at index time."""
        return self._absolute_path

    @property
    def title(self) -> str:
        """Return this document's human-readable title."""
        return self._title

    @property
    def size(self) -> int:
        """Return this document's file size in bytes at index time."""
        return self._size

    @property
    def last_modified(self) -> float:
        """Return this document's modification time (Unix epoch seconds) at index time."""
        return self._last_modified

    @property
    def checksum(self) -> str:
        """Return this document's SHA-256 content checksum."""
        return self._checksum

    def chunks(self) -> tuple[DocumentChunk, ...]:
        """Return this document's ordered chunks."""
        return self._chunks

    def metadata(self) -> dict[str, Any]:
        """Return a defensive copy of this document's metadata."""
        return dict(self._metadata)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this document."""
        return {
            "document_id": self._document_id,
            "relative_path": self._relative_path,
            "absolute_path": self._absolute_path,
            "title": self._title,
            "size": self._size,
            "last_modified": self._last_modified,
            "checksum": self._checksum,
            "chunks": [chunk.to_dict() for chunk in self._chunks],
            "metadata": dict(self._metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IndexedDocument:
        """Reconstruct an IndexedDocument from `to_dict()`'s output."""
        return cls(
            document_id=data["document_id"],
            relative_path=data["relative_path"],
            absolute_path=data["absolute_path"],
            title=data.get("title", ""),
            size=data["size"],
            last_modified=data["last_modified"],
            checksum=data["checksum"],
            chunks=tuple(DocumentChunk.from_dict(item) for item in data.get("chunks", [])),
            metadata=data.get("metadata") or {},
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IndexedDocument):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        return (
            f"IndexedDocument(document_id={self._document_id!r}, "
            f"relative_path={self._relative_path!r}, chunks={len(self._chunks)})"
        )
