"""EP-020 Semantic Retrieval Engine.

A deterministic retrieval layer over the `ProjectIndex` produced by
EP-019: given a search query, finds and ranks the most relevant
documents and chunks. This is NOT an embedding engine and NOT a
vector database (per EP-020's task brief) -- scoring is plain,
deterministic keyword matching (see `ranking.py`).

Read-only with respect to EP-019: never mutates the `ProjectIndex`,
any `IndexedDocument`, or any `DocumentChunk` it is given, and never
calls back into `ProjectIndexer`/`IndexStorage` (build/rebuild/save/
load/clear are exclusively EP-019's concern). Never returns raw
`DocumentChunk` objects to callers -- only `RetrievalResult`.

Depends only on EP-019's public API (`src.core.indexing`) plus this
package's own `Query`/`RetrievalResult`/`RankingEngine` -- no AI
provider, no ContextLoader, no PromptBuilder, no PromptManager, no
ContextManager, matching EP-019's own dependency rule.
"""

from __future__ import annotations

from typing import Any

from src.core.indexing import ProjectIndex
from src.core.retrieval.query import Query
from src.core.retrieval.ranking import RankingEngine
from src.core.retrieval.result import RetrievalResult

__all__ = ["RetrievalEngine"]


class RetrievalEngine:
    """Deterministic, read-only retrieval over a single ProjectIndex.

    Never modifies `index` (or anything it contains) -- every public
    method only reads from it via EP-019's existing public API
    (`ProjectIndex.documents()` and `ProjectIndex.statistics()`).
    """

    def __init__(self, index: ProjectIndex, ranking_engine: RankingEngine | None = None) -> None:
        """Initialize the RetrievalEngine.

        Args:
            index: The ProjectIndex (EP-019) to search. Read-only:
                never mutated by this engine.
            ranking_engine: The scoring strategy to use. Defaults to a
                new `RankingEngine()`.
        """
        self._index = index
        self._ranking_engine = ranking_engine or RankingEngine()

    def search(self, query: str | Query) -> list[RetrievalResult]:
        """Search every chunk in the index and return ranked results.

        Equivalent to `search_chunks(query)` -- chunks are the atomic
        retrieval unit this engine ranks against.

        Args:
            query: Raw query text, or an already-built `Query`.

        Returns:
            Every chunk scoring above zero, ranked highest score
            first. Empty list for an empty or unmatched query.
        """
        return self.search_chunks(query)

    def search_chunks(self, query: str | Query) -> list[RetrievalResult]:
        """Search every chunk in the index and return ranked results.

        Args:
            query: Raw query text, or an already-built `Query`.

        Returns:
            Every chunk scoring above zero, ranked highest score
            first. Empty list for an empty or unmatched query.
        """
        resolved_query = self._resolve_query(query)
        if resolved_query.is_empty:
            return []

        results: list[RetrievalResult] = []
        for document in self._index.documents():
            for chunk in document.chunks():
                score = self._ranking_engine.score_chunk(resolved_query, chunk, document)
                if score > 0.0:
                    results.append(RetrievalResult.from_chunk(chunk, score))

        return self._sorted_results(results)

    def search_documents(self, query: str | Query) -> list[RetrievalResult]:
        """Search every document and return each one's single best-matching chunk.

        Args:
            query: Raw query text, or an already-built `Query`.

        Returns:
            At most one `RetrievalResult` per matching document (its
            highest-scoring chunk), ranked highest score first. Empty
            list for an empty or unmatched query.
        """
        resolved_query = self._resolve_query(query)
        if resolved_query.is_empty:
            return []

        best_per_document: dict[str, RetrievalResult] = {}
        for document in self._index.documents():
            best_score = 0.0
            best_chunk = None
            for chunk in document.chunks():
                score = self._ranking_engine.score_chunk(resolved_query, chunk, document)
                if score > best_score:
                    best_score = score
                    best_chunk = chunk
            if best_chunk is not None:
                best_per_document[document.document_id] = RetrievalResult.from_chunk(
                    best_chunk, best_score
                )

        return self._sorted_results(list(best_per_document.values()))

    def top_k(self, query: str | Query, k: int) -> list[RetrievalResult]:
        """Return the top `k` chunk results for `query`.

        Args:
            query: Raw query text, or an already-built `Query`.
            k: Maximum number of results to return. Non-positive
                values return an empty list.

        Returns:
            At most `k` results from `search_chunks(query)`, in the
            same highest-score-first order.
        """
        if k <= 0:
            return []
        return self.search_chunks(query)[:k]

    def statistics(self) -> dict[str, Any]:
        """Return summary statistics for the underlying index.

        Returns:
            `ProjectIndex.statistics()`'s own dict, unchanged --
            `document_count`, `chunk_count`, `total_characters`, and
            `average_chunk_size`.
        """
        return self._index.statistics()

    @staticmethod
    def _resolve_query(query: str | Query) -> Query:
        """Return `query` as a `Query`, building one from text if needed.

        Args:
            query: Raw query text, or an already-built `Query`.

        Returns:
            `query` unchanged if it is already a `Query`; otherwise
            `Query.from_text(query)`.
        """
        return query if isinstance(query, Query) else Query.from_text(query)

    @staticmethod
    def _sorted_results(results: list[RetrievalResult]) -> list[RetrievalResult]:
        """Sort `results` highest score first, breaking ties deterministically.

        Args:
            results: Unsorted results.

        Returns:
            `results` sorted by descending score, then ascending
            `relative_path`, then ascending `chunk_id`, so identical
            inputs always produce identical output order (EP-020's
            "deterministic output" requirement).
        """
        return sorted(
            results, key=lambda result: (-result.score, result.relative_path, result.chunk_id)
        )
