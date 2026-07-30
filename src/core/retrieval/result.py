"""RetrievalResult domain model for the EP-020 Semantic Retrieval Engine.

Represents one ranked search result: a scored reference into a
`DocumentChunk` (EP-019), never the chunk itself -- `RetrievalEngine`
must never return raw chunks directly (see its module docstring).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.indexing import DocumentChunk

__all__ = ["RetrievalResult"]

PREVIEW_MAX_CHARACTERS = 200


@dataclass(frozen=True)
class RetrievalResult:
    """One ranked search result.

    Attributes:
        document_id: Identifier of the owning `IndexedDocument`.
        chunk_id: Identifier of the matched `DocumentChunk`.
        score: This result's ranking score (see `ranking.py`); higher
            is more relevant. Never negative.
        relative_path: The owning document's repository-relative path.
        heading: The matched chunk's nearest preceding heading, or ""
            if it falls outside any heading.
        preview: A short, human-readable excerpt of the matched
            chunk's text (see `from_chunk`) -- never the full chunk
            text.
    """

    document_id: str
    chunk_id: str
    score: float
    relative_path: str
    heading: str
    preview: str

    @classmethod
    def from_chunk(cls, chunk: DocumentChunk, score: float) -> RetrievalResult:
        """Build a RetrievalResult from a matched chunk and its score.

        Args:
            chunk: The matched DocumentChunk (EP-019, read-only; never
                mutated here).
            score: This result's ranking score.

        Returns:
            A RetrievalResult exposing only `chunk`'s identifying
            fields and a short preview of its text -- never the full
            chunk text and never the chunk object itself.
        """
        return cls(
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            score=score,
            relative_path=chunk.relative_path,
            heading=chunk.heading,
            preview=cls._build_preview(chunk.text()),
        )

    @staticmethod
    def _build_preview(text: str) -> str:
        """Return a short, single-line excerpt of `text`.

        Args:
            text: The full chunk text to summarize.

        Returns:
            `text` unchanged if it is at most `PREVIEW_MAX_CHARACTERS`
            long; otherwise the first `PREVIEW_MAX_CHARACTERS`
            characters (trimmed of trailing whitespace) followed by
            "...".
        """
        collapsed = " ".join(text.split())
        if len(collapsed) <= PREVIEW_MAX_CHARACTERS:
            return collapsed
        return collapsed[:PREVIEW_MAX_CHARACTERS].rstrip() + "..."
