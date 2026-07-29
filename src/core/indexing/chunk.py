"""DocumentChunk domain model for the EP-019 Project Index Engine.

Represents one immutable, indexed slice of a document, produced by
`ChunkBuilder` (see `src/core/indexing/chunk_builder.py`). DocumentChunk
carries no knowledge of any AI provider, prompting, or retrieval
strategy -- it is pure indexed data, consumed later by Retrieval
(out of scope here).
"""

from __future__ import annotations

from typing import Any

__all__ = ["DocumentChunk"]


class DocumentChunk:
    """One immutable indexed chunk of a document.

    Attributes:
        chunk_id: Unique identifier for this chunk.
        document_id: Identifier of the `IndexedDocument` this chunk
            belongs to.
        relative_path: The owning document's repository-relative path.
        heading: The nearest preceding heading text, or "" if the
            chunk falls outside any heading.
        start_line: 1-based line number where this chunk begins.
        end_line: 1-based line number where this chunk ends.
        character_count: Number of characters in this chunk's text.

    Chunk objects are immutable after construction -- no field can be
    reassigned, and `metadata()` returns a defensive copy so callers
    can never mutate internal state.
    """

    __slots__ = (
        "_chunk_id",
        "_document_id",
        "_end_line",
        "_heading",
        "_metadata",
        "_relative_path",
        "_start_line",
        "_text",
    )

    def __init__(
        self,
        chunk_id: str,
        document_id: str,
        relative_path: str,
        heading: str,
        text: str,
        start_line: int,
        end_line: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize an immutable DocumentChunk.

        Args:
            chunk_id: Unique identifier for this chunk.
            document_id: Identifier of the owning IndexedDocument.
            relative_path: The owning document's repository-relative path.
            heading: The nearest preceding heading text, or "".
            text: The chunk's text content.
            start_line: 1-based line number where this chunk begins.
            end_line: 1-based line number where this chunk ends.
            metadata: Arbitrary extra data. Copied defensively so the
                caller's dict can never mutate this chunk afterward.

        Raises:
            ValueError: If `text` is empty -- chunks must never be
                empty (see `ChunkBuilder`).
        """
        if not text:
            raise ValueError("DocumentChunk text must not be empty.")
        self._chunk_id = chunk_id
        self._document_id = document_id
        self._relative_path = relative_path
        self._heading = heading
        self._text = text
        self._start_line = start_line
        self._end_line = end_line
        self._metadata = dict(metadata) if metadata else {}

    @property
    def chunk_id(self) -> str:
        """Return this chunk's unique identifier."""
        return self._chunk_id

    @property
    def document_id(self) -> str:
        """Return the identifier of the document this chunk belongs to."""
        return self._document_id

    @property
    def relative_path(self) -> str:
        """Return the owning document's repository-relative path."""
        return self._relative_path

    @property
    def heading(self) -> str:
        """Return the nearest preceding heading text, or "" if none."""
        return self._heading

    @property
    def start_line(self) -> int:
        """Return the 1-based line number where this chunk begins."""
        return self._start_line

    @property
    def end_line(self) -> int:
        """Return the 1-based line number where this chunk ends."""
        return self._end_line

    @property
    def character_count(self) -> int:
        """Return the number of characters in this chunk's text."""
        return len(self._text)

    def text(self) -> str:
        """Return this chunk's text content."""
        return self._text

    def metadata(self) -> dict[str, Any]:
        """Return a defensive copy of this chunk's metadata."""
        return dict(self._metadata)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this chunk."""
        return {
            "chunk_id": self._chunk_id,
            "document_id": self._document_id,
            "relative_path": self._relative_path,
            "heading": self._heading,
            "text": self._text,
            "start_line": self._start_line,
            "end_line": self._end_line,
            "character_count": self.character_count,
            "metadata": dict(self._metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocumentChunk:
        """Reconstruct a DocumentChunk from `to_dict()`'s output."""
        return cls(
            chunk_id=data["chunk_id"],
            document_id=data["document_id"],
            relative_path=data["relative_path"],
            heading=data.get("heading", ""),
            text=data["text"],
            start_line=data["start_line"],
            end_line=data["end_line"],
            metadata=data.get("metadata") or {},
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, DocumentChunk):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        return (
            f"DocumentChunk(chunk_id={self._chunk_id!r}, "
            f"relative_path={self._relative_path!r}, "
            f"start_line={self._start_line}, end_line={self._end_line})"
        )
