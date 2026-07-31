"""EP-022 RAG Engine.

A provider-independent Retrieval-Augmented Generation pipeline that
combines the Project Index Engine (EP-019), the Semantic Retrieval
Engine (EP-020) and the Embedding Engine (EP-021) into a single,
reusable context-generation pipeline for LLMs: given a user query, it

    1. obtains the query's embedding (EP-021, `EmbeddingEngine`),
    2. retrieves and ranks relevant chunks (EP-020, `RetrievalEngine`),
    3. assembles the highest-ranked chunks -- read directly from this
       engine's `ProjectIndex` (EP-019) -- into a single context block,

and returns a structured `RagResult`. This is the RAG Engine's entire
responsibility.

It must NEVER call an LLM, an AI provider, or perform chat completion
of any kind -- no import of `src.core.ai.*` anywhere in this package.
It performs no semantic (embedding-based) search of its own and stores
no embeddings: relevance ranking is delegated entirely to EP-020's
existing, deterministic `RankingEngine`. The query embedding obtained
in step 1 is surfaced on `RagResult` (its dimension only) as a
literal, forward-compatible pipeline step -- it is never used to
re-rank, filter, or otherwise influence which chunks step 2 or step 3
select.

Depends only on `ProjectIndex` (EP-019, read-only), `RetrievalEngine`
(EP-020) and `EmbeddingEngine` (EP-021) -- no `ProjectIndexer`, no
`IndexStorage`, no `EmbeddingManager`, no `RankingEngine` constructed
directly, no `AIProvider`, no `ContextLoader`, no `PromptBuilder`, no
`PromptManager`, no `ContextManager`. Lifecycle concerns (which
`ProjectIndex`/`RetrievalEngine` currently backs this engine, which
embedding provider is currently selected) belong exclusively to
`RagManager` (see `rag_manager.py`), matching EP-021's own
Engine/Manager split.
"""

from __future__ import annotations

from src.core.embedding.engine import EmbeddingEngine, EmbeddingEngineError
from src.core.embedding.provider import EmbeddingProviderError
from src.core.indexing import ProjectIndex
from src.core.rag.rag_result import RagContextItem, RagResult
from src.core.retrieval import RetrievalEngine, RetrievalResult

__all__ = [
    "RagEngine",
    "RagEngineError",
    "EmptyQueryError",
    "EmbeddingUnavailableError",
]

DEFAULT_TOP_K = 5
DEFAULT_MAX_CONTEXT_CHARACTERS = 4000


class RagEngineError(Exception):
    """Base class for errors raised by the RagEngine itself."""


class EmptyQueryError(RagEngineError):
    """Raised when `query()`/`context()` is given empty or whitespace-only text."""


class EmbeddingUnavailableError(RagEngineError):
    """Raised when the query-embedding step (EP-021) cannot be completed.

    Wraps the underlying `EmbeddingEngineError`/`EmbeddingProviderError`
    (e.g. no provider currently selected, or the provider itself
    failed) so every caller of `RagEngine` can catch a single,
    RAG-specific exception type without needing to import EP-021's own
    error hierarchy.
    """


class RagEngine:
    """Provider-independent Retrieval-Augmented Generation pipeline.

    Combines a fixed `ProjectIndex` (EP-019), `RetrievalEngine`
    (EP-020) and `EmbeddingEngine` (EP-021) into one reusable
    `query()` -> `RagResult` pipeline. Never mutates any of its
    dependencies and never calls an LLM.
    """

    def __init__(
        self,
        index: ProjectIndex,
        retrieval_engine: RetrievalEngine,
        embedding_engine: EmbeddingEngine,
        top_k: int = DEFAULT_TOP_K,
        max_context_characters: int = DEFAULT_MAX_CONTEXT_CHARACTERS,
    ) -> None:
        """Initialize the RagEngine.

        Args:
            index: The ProjectIndex (EP-019) to read full chunk text
                from. Read-only: never mutated by this engine. Should
                be the same index `retrieval_engine` was built over
                (see `RagManager`, which guarantees this).
            retrieval_engine: The RetrievalEngine (EP-020) used to
                find and rank relevant chunks for a query.
            embedding_engine: The EmbeddingEngine (EP-021) used to
                obtain a query's embedding vector.
            top_k: Default maximum number of chunks to assemble into
                context, used when `query()`/`context()` are not given
                an explicit `top_k`. Must be positive.
            max_context_characters: Maximum total size (in characters)
                of the assembled context text. Must be positive.

        Raises:
            ValueError: If `top_k` or `max_context_characters` is not
                a positive integer.
        """
        if top_k <= 0:
            raise ValueError("top_k must be positive.")
        if max_context_characters <= 0:
            raise ValueError("max_context_characters must be positive.")
        self._index = index
        self._retrieval_engine = retrieval_engine
        self._embedding_engine = embedding_engine
        self._top_k = top_k
        self._max_context_characters = max_context_characters

    def query(self, text: str, top_k: int | None = None) -> RagResult:
        """Run the full RAG pipeline for `text` and return a structured result.

        Steps: obtain `text`'s embedding (EP-021), retrieve and rank
        relevant chunks (EP-020), then assemble the highest-ranked
        chunks -- read directly from this engine's `ProjectIndex`
        (EP-019) -- into a single context block.

        Args:
            text: The user's query text.
            top_k: Maximum number of chunks to assemble into context.
                Defaults to this engine's configured `top_k`.

        Returns:
            A RagResult describing the query's embedding dimension,
            the ranked context items used, and the assembled context
            text. `provider`/`model` are left as "" here -- `RagEngine`
            has no `EmbeddingManager` to resolve them from; `RagManager`
            fills them in (see `rag_manager.py`).

        Raises:
            EmptyQueryError: If `text` is empty or whitespace-only.
            ValueError: If `top_k` is given and is not positive.
            EmbeddingUnavailableError: If `text`'s embedding cannot be
                obtained (e.g. no embedding provider is currently
                selected, or the provider itself fails).
        """
        if not text or not text.strip():
            raise EmptyQueryError("Query text must not be empty.")

        resolved_top_k = self._top_k if top_k is None else top_k
        if resolved_top_k <= 0:
            raise ValueError("top_k must be positive.")

        embedding_vector = self._embed_query(text)
        retrieval_results = self._retrieval_engine.top_k(text, resolved_top_k)
        items, context, truncated = self._assemble_context(retrieval_results)

        return RagResult(
            query=text,
            provider="",
            model="",
            embedding_dimension=len(embedding_vector),
            items=tuple(items),
            context=context,
            truncated=truncated,
            statistics={
                "retrieved_count": len(retrieval_results),
                "assembled_count": len(items),
                "context_characters": len(context),
            },
        )

    def context(self, text: str, top_k: int | None = None) -> str:
        """Run the full RAG pipeline for `text` and return only the assembled context text.

        Equivalent to `query(text, top_k).context`.

        Args:
            text: The user's query text.
            top_k: Maximum number of chunks to assemble into context.

        Returns:
            The assembled context text; "" if nothing matched.

        Raises:
            EmptyQueryError: If `text` is empty or whitespace-only.
            ValueError: If `top_k` is given and is not positive.
            EmbeddingUnavailableError: If `text`'s embedding cannot be
                obtained.
        """
        return self.query(text, top_k=top_k).context

    def _embed_query(self, text: str) -> list[float]:
        """Obtain `text`'s embedding vector via EmbeddingEngine (EP-021).

        Args:
            text: The query text to embed.

        Returns:
            The validated embedding vector produced by EP-021.

        Raises:
            EmbeddingUnavailableError: If the embedding step fails for
                any reason (no provider selected, provider failure, or
                a vector-validation failure).
        """
        try:
            return self._embedding_engine.embed_text(text)
        except (EmbeddingEngineError, EmbeddingProviderError) as exc:
            raise EmbeddingUnavailableError(
                f"RAG Engine could not obtain a query embedding: {exc}"
            ) from exc

    def _assemble_context(
        self, retrieval_results: list[RetrievalResult]
    ) -> tuple[list[RagContextItem], str, bool]:
        """Assemble the highest-ranked chunks into a single context block.

        Reads each result's full chunk text directly from this
        engine's `ProjectIndex` -- EP-020's `RetrievalResult` never
        exposes more than a short preview (see
        `src/core/retrieval/result.py`).

        Stops adding further chunks once the assembled text would
        exceed `max_context_characters`, always including at least the
        first (highest-ranked) chunk that fits, and preserves
        `retrieval_results`' rank order throughout.

        Args:
            retrieval_results: Ranked results from RetrievalEngine,
                highest score first.

        Returns:
            A tuple of `(items, context, truncated)`:
                items: The RagContextItem for every chunk actually
                    assembled, in the same ranked order.
                context: `items`' formatted blocks, joined by a blank
                    line. "" if `items` is empty.
                truncated: Whether one or more lower-ranked candidates
                    from `retrieval_results` had to be dropped to
                    respect `max_context_characters`.
        """
        items: list[RagContextItem] = []
        blocks: list[str] = []
        total_characters = 0
        truncated = False

        for result in retrieval_results:
            chunk = self._index.chunk(result.chunk_id)
            if chunk is None:
                # The index changed since `result` was produced (e.g. a
                # rebuild happened between retrieval and assembly) --
                # skip the now-stale reference rather than crash the
                # whole pipeline.
                continue

            chunk_text = chunk.text()
            block = self._format_block(result, chunk_text)
            separator_characters = 2 if blocks else 0  # "\n\n" joiner
            projected_characters = total_characters + separator_characters + len(block)

            if blocks and projected_characters > self._max_context_characters:
                truncated = True
                break

            items.append(RagContextItem.from_retrieval_result(result, chunk_text))
            blocks.append(block)
            total_characters = projected_characters

        return items, "\n\n".join(blocks), truncated

    @staticmethod
    def _format_block(result: RetrievalResult, text: str) -> str:
        """Format one retrieved chunk as a labeled context block.

        Args:
            result: The chunk's ranked retrieval result.
            text: The chunk's full text.

        Returns:
            A two-line block: a `[relative_path — heading]` label (or
            just `[relative_path]` if the chunk has no heading),
            followed by the chunk's full text.
        """
        if result.heading:
            label = f"[{result.relative_path} — {result.heading}]"
        else:
            label = f"[{result.relative_path}]"
        return f"{label}\n{text}"
