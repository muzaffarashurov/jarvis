"""Deterministic scoring for the EP-020 Semantic Retrieval Engine.

RankingEngine scores a single `DocumentChunk` (EP-019) against a
`Query` using plain keyword matching only -- no AI, no embeddings, no
vector math, no external model of any kind. See
`retrieval_engine.py`'s module docstring for how these scores are
used to rank search results.
"""

from __future__ import annotations

from src.core.indexing import DocumentChunk, IndexedDocument
from src.core.retrieval.query import Query

__all__ = ["RankingEngine"]

KEYWORD_OVERLAP_WEIGHT = 1.0
TITLE_BONUS = 5.0
HEADING_BONUS = 3.0
EXACT_PHRASE_BONUS = 10.0


class RankingEngine:
    """Deterministic, keyword-based scoring for chunk/document search.

    Implements no matching or ranking logic beyond plain (lowercased)
    keyword overlap plus three fixed bonuses (title, heading, exact
    phrase) -- no AI, no embeddings, no semantic similarity of any
    kind (EP-020's task brief: "This is NOT an embedding engine").
    Identical inputs always produce the identical score.
    """

    def score_chunk(self, query: Query, chunk: DocumentChunk, document: IndexedDocument) -> float:
        """Score how well `chunk` (belonging to `document`) matches `query`.

        Args:
            query: The (already normalized) search request.
            chunk: The candidate chunk. Never mutated.
            document: The `IndexedDocument` `chunk` belongs to (used
                only for the title bonus). Never mutated.

        Returns:
            A non-negative score; 0.0 means no match at all. Higher
            is more relevant.

            - `query.exact_phrase` (the caller quoted the query):
              scored only if `query.normalized` occurs verbatim,
              contiguously, inside the chunk's text -- otherwise 0.0.
            - Otherwise: keyword-overlap score, plus a title bonus if
              any query term appears in the document's title, plus a
              heading bonus if any query term appears in the chunk's
              heading, plus an exact-phrase bonus if the full
              (multi-word) normalized query happens to occur
              contiguously in the chunk's text anyway.
        """
        if query.is_empty:
            return 0.0

        chunk_text = chunk.text().lower()
        phrase_found = bool(query.normalized) and query.normalized in chunk_text

        if query.exact_phrase:
            if not phrase_found:
                return 0.0
            return self._composite_score(query, chunk, document, chunk_text, phrase_matched=True)

        return self._composite_score(query, chunk, document, chunk_text, phrase_matched=phrase_found)

    def _composite_score(
        self,
        query: Query,
        chunk: DocumentChunk,
        document: IndexedDocument,
        chunk_text: str,
        phrase_matched: bool,
    ) -> float:
        """Combine keyword overlap with the title/heading/exact-phrase bonuses.

        Args:
            query: The search request.
            chunk: The candidate chunk.
            document: The chunk's owning document.
            chunk_text: `chunk.text()`, already lowercased.
            phrase_matched: Whether the exact-phrase bonus applies.

        Returns:
            The combined, non-negative score.
        """
        heading_text = chunk.heading.lower()
        title_text = document.title.lower()

        score = KEYWORD_OVERLAP_WEIGHT * self._keyword_overlap(query.terms, chunk_text)

        if any(term in title_text for term in query.terms):
            score += TITLE_BONUS

        if heading_text and any(term in heading_text for term in query.terms):
            score += HEADING_BONUS

        if phrase_matched:
            score += EXACT_PHRASE_BONUS

        return score

    @staticmethod
    def _keyword_overlap(terms: tuple[str, ...], text: str) -> int:
        """Count how many query terms appear in `text`.

        Args:
            terms: The query's normalized, whitespace-split terms.
            text: Lowercased text to search within.

        Returns:
            The number of `terms` entries that occur as a substring of
            `text` (each entry in `terms` counted at most once, even
            if it appears in `text` multiple times).
        """
        return sum(1 for term in terms if term and term in text)
