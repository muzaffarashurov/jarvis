"""RagResult domain model for the EP-022 RAG Engine.

Represents one complete, structured RAG pipeline result: the original
query, the embedding provider used to embed it (EP-021), the ranked
context items retrieved (EP-020) and assembled from full chunk text
(EP-019), and the assembled context text itself. This is pure,
immutable data -- no chat completion, no LLM call, no prompt sent
anywhere, matching `rag_engine.py`'s module docstring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.retrieval import RetrievalResult

__all__ = ["RagContextItem", "RagResult"]


@dataclass(frozen=True)
class RagContextItem:
    """One retrieved chunk assembled into a RagResult's context.

    Unlike EP-020's `RetrievalResult` (which exposes only a short
    preview), `text` here is the chunk's full text -- read directly
    from EP-019's `ProjectIndex` by the RAG Engine, since context
    assembly requires the complete chunk, not a preview.

    Attributes:
        document_id: Identifier of the owning `IndexedDocument` (EP-019).
        chunk_id: Identifier of the retrieved `DocumentChunk` (EP-019).
        relative_path: The owning document's repository-relative path.
        heading: The chunk's nearest preceding heading, or "" if none.
        score: The chunk's retrieval score (EP-020's `RankingEngine`);
            higher is more relevant. Never negative.
        text: The chunk's full text, as assembled into
            `RagResult.context`.
    """

    document_id: str
    chunk_id: str
    relative_path: str
    heading: str
    score: float
    text: str

    @classmethod
    def from_retrieval_result(cls, result: RetrievalResult, text: str) -> RagContextItem:
        """Build a RagContextItem from an EP-020 RetrievalResult plus full chunk text.

        Args:
            result: The ranked retrieval result to adapt.
            text: The matched chunk's full text (read from EP-019's
                `ProjectIndex`, never from `result.preview`).

        Returns:
            A RagContextItem carrying `result`'s identifying fields
            and score, plus the given full `text`.
        """
        return cls(
            document_id=result.document_id,
            chunk_id=result.chunk_id,
            relative_path=result.relative_path,
            heading=result.heading,
            score=result.score,
            text=text,
        )


@dataclass(frozen=True)
class RagResult:
    """One complete RAG pipeline result for a single query.

    Attributes:
        query: The original, unmodified query text.
        provider: The embedding provider's registered name used to
            embed `query`. "" if not yet known to the caller that
            produced this result (see `rag_engine.py`'s module
            docstring: `RagEngine` itself never has an
            `EmbeddingManager` to resolve this from -- `RagManager`
            fills it in).
        model: The embedding provider's model identifier. "" under
            the same conditions as `provider`.
        embedding_dimension: Length of `query`'s embedding vector, as
            obtained from EP-021.
        items: The ranked context items assembled into `context`,
            highest score first. May be empty if nothing matched.
        context: The assembled context text, built from `items`,
            ready to be handed to a future prompt-building stage.
            Never sent to any LLM by this package. "" if `items` is
            empty.
        truncated: Whether one or more lower-ranked candidates had to
            be dropped from `items` to respect the assembling
            `RagEngine`'s configured `max_context_characters`.
        statistics: Read-only diagnostic counters: `retrieved_count`
            (results EP-020 returned before assembly),
            `assembled_count` (== `len(items)`), and
            `context_characters` (== `len(context)`).
    """

    query: str
    provider: str
    model: str
    embedding_dimension: int
    items: tuple[RagContextItem, ...]
    context: str
    truncated: bool
    statistics: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """Return True if no context items were assembled for this query."""
        return len(self.items) == 0
