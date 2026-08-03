"""EP-027 Context Compression Engine.

A provider-independent engine that shrinks already-assembled context
to fit within a configured character/chunk budget: splits raw text
into paragraph-sized chunks (or accepts pre-built chunks, e.g. one per
EP-026 `SemanticResult`), and delegates deduplication, ordering and
limit enforcement to the currently selected `CompressionProvider` (via
`CompressionManager`). This is Context Compression's entire
responsibility -- it must NOT generate answers, call an AI provider,
build prompts, retrieve or rank context, plan, or reason (see
`src/core/context_compression/__init__.py`).

Depends only on public APIs:
    - `CompressionManager` (this package) -- current provider and
      default limits.
    - `SemanticEngine` (EP-026, optional) -- `search()`, used solely by
      `compress_query()` to let a caller compress the results of a
      fresh semantic search in one call. `SemanticResult` (EP-026) is
      read only through its public fields (`text`, `source`,
      `identifier`, `score`, `metadata`).

No AI provider, no prompt engine, no RAG engine, no Planner, no
Reflection, no browser automation, no tool calling, no conversation
engine, no agent framework, and no private attribute of any of the
above is ever accessed (only their public methods/fields).
"""

from __future__ import annotations

import re

from src.core.context_compression.compression_manager import CompressionManager
from src.core.context_compression.compression_provider import (
    CompressionProviderError,
    ContextCompressionError,
)
from src.core.context_compression.compression_result import CompressionResult, ContextChunk
from src.core.semantic.semantic_engine import SemanticEngine, SemanticEngineError
from src.core.semantic.semantic_provider import SemanticProviderError
from src.core.semantic.semantic_result import SemanticResult

__all__ = [
    "CompressionEngine",
    "CompressionEngineError",
    "NoCompressionProviderSelectedError",
    "EmptyContextError",
    "SemanticSearchUnavailableError",
]

#: Splits raw text into paragraphs on one or more blank lines, matching
#: `DefaultCompressionProvider`'s own paragraph boundary.
_PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n")


class CompressionEngineError(ContextCompressionError):
    """Base class for errors raised by the CompressionEngine itself.

    Inherits from `ContextCompressionError`
    (src/core/context_compression/compression_provider.py) so callers
    can catch every context-compression-related failure -- provider,
    engine, or manager -- with a single exception type.
    """


class NoCompressionProviderSelectedError(CompressionEngineError):
    """Raised when compression is requested but no provider is currently selected."""


class EmptyContextError(CompressionEngineError):
    """Raised when compression is requested with no context (empty text or chunk list)."""


class SemanticSearchUnavailableError(CompressionEngineError):
    """Raised when `compress_query()` is called without a SemanticEngine configured."""


class CompressionEngine:
    """Provider-independent context-compression pipeline.

    Pipeline for `compress_text()`:

        text -> split into paragraph chunks -> CompressionProvider.compress()
             -> CompressionResult

    Pipeline for `compress_query()` (mirrors the task brief's diagram
    "Semantic Search results -> deduplicate -> preserve ordering ->
    enforce limits -> CompressionResult"):

        query -> SemanticEngine.search() -> one chunk per SemanticResult
              -> CompressionProvider.compress() -> CompressionResult

    Never selects, constructs, or configures providers itself --
    provider selection and lifecycle are exclusively
    `CompressionManager`'s concern. Never deduplicates, orders, or
    limits chunks itself -- all three stay inside the active
    `CompressionProvider`.
    """

    def __init__(
        self,
        manager: CompressionManager,
        semantic_engine: SemanticEngine | None = None,
    ) -> None:
        """Initialize the CompressionEngine.

        Args:
            manager: The CompressionManager used to resolve the
                currently active provider and the default
                `max_context_characters` / `max_chunks` /
                `deduplicate` limits. Never mutated by this engine.
            semantic_engine: The SemanticEngine (EP-026) used only by
                `compress_query()` to perform a semantic search whose
                results are then compressed. Optional: if None,
                `compress_query()` raises
                `SemanticSearchUnavailableError` -- `compress_text()`
                and `compress_chunks()` still function normally either
                way.
        """
        self._manager = manager
        self._semantic_engine = semantic_engine

    def compress_text(self, text: str) -> CompressionResult:
        """Compress raw text: split into paragraph chunks, then compress them.

        Args:
            text: The raw context text to compress.

        Returns:
            The resulting CompressionResult.

        Raises:
            EmptyContextError: If `text` is empty or whitespace-only.
            NoCompressionProviderSelectedError: If no compression
                provider is currently selected (or the subsystem is
                disabled).
            CompressionProviderError: If the active provider itself
                fails to compress (e.g. an invalid configured limit).
        """
        if not text or not text.strip():
            raise EmptyContextError("Context Compression input text must not be empty.")

        return self.compress_chunks(self._chunks_from_text(text))

    def compress_chunks(self, chunks: list[ContextChunk]) -> CompressionResult:
        """Compress an already-built, ordered sequence of chunks.

        Args:
            chunks: The chunks to compress, in their original order.

        Returns:
            The resulting CompressionResult.

        Raises:
            EmptyContextError: If `chunks` is empty.
            NoCompressionProviderSelectedError: If no compression
                provider is currently selected (or the subsystem is
                disabled).
            CompressionProviderError: If the active provider itself
                fails to compress (e.g. an invalid configured limit).
        """
        if not chunks:
            raise EmptyContextError("Context Compression input must contain at least one chunk.")

        provider = self._require_current_provider()
        try:
            return provider.compress(
                chunks,
                max_characters=self._manager.max_context_characters(),
                max_chunks=self._manager.max_chunks(),
                deduplicate=self._manager.deduplicate(),
            )
        except CompressionProviderError:
            raise

    def compress_semantic_results(self, results: list[SemanticResult]) -> CompressionResult:
        """Compress a list of EP-026 `SemanticResult` instances, one chunk each.

        Reads only `SemanticResult`'s public fields (`text`, `source`,
        `identifier`, `score`, `metadata`); never accesses Semantic
        Search internals.

        Args:
            results: The semantic search results to compress, in their
                already-ranked order (preserved through compression).

        Returns:
            The resulting CompressionResult.

        Raises:
            EmptyContextError: If `results` is empty.
            NoCompressionProviderSelectedError: If no compression
                provider is currently selected (or the subsystem is
                disabled).
            CompressionProviderError: If the active provider itself
                fails to compress (e.g. an invalid configured limit).
        """
        chunks = [
            ContextChunk(
                text=result.text,
                index=index,
                metadata={
                    **result.metadata,
                    "source": result.source,
                    "identifier": result.identifier,
                    "score": result.score,
                },
            )
            for index, result in enumerate(results)
        ]
        return self.compress_chunks(chunks)

    def compress_query(
        self,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> CompressionResult:
        """Run a semantic search, then compress its results.

        Args:
            query: The natural-language search query, forwarded
                unchanged to `SemanticEngine.search()`.
            top_k: Maximum number of semantic search results to
                request. Defaults to the SemanticEngine's own default
                when None.
            threshold: Minimum similarity score a semantic search
                result must reach. Defaults to the SemanticEngine's
                own default when None.

        Returns:
            The resulting CompressionResult.

        Raises:
            SemanticSearchUnavailableError: If no SemanticEngine was
                configured for this CompressionEngine.
            EmptyContextError: If the semantic search returns no results.
            NoCompressionProviderSelectedError: If no compression
                provider is currently selected (or the subsystem is
                disabled).
            CompressionEngineError: If the semantic search itself fails.
            CompressionProviderError: If the active provider itself
                fails to compress (e.g. an invalid configured limit).
        """
        if self._semantic_engine is None:
            raise SemanticSearchUnavailableError(
                "Context Compression was not configured with a SemanticEngine; "
                "use compress_text()/compress_chunks()/compress_semantic_results() instead."
            )

        try:
            results = self._semantic_engine.search(query, top_k=top_k, threshold=threshold)
        except (SemanticEngineError, SemanticProviderError) as exc:
            raise CompressionEngineError(f"Context Compression semantic search failed: {exc}") from exc

        if not results:
            raise EmptyContextError(f'Semantic search for "{query}" returned no results.')

        return self.compress_semantic_results(results)

    # ---------- Analysis (no truncation applied) ----------

    def estimate(self, text: str) -> tuple[int, int, int]:
        """Return `(character_count, estimated_tokens, chunk_count)` for `text`, uncompressed.

        Never deduplicates or truncates -- a pure, read-only estimate
        of `text` as given, using the currently active provider's
        `estimate_tokens()`.

        Args:
            text: The text to analyze.

        Returns:
            A tuple of `(character_count, estimated_tokens,
            chunk_count)`.

        Raises:
            EmptyContextError: If `text` is empty or whitespace-only.
            NoCompressionProviderSelectedError: If no compression
                provider is currently selected (or the subsystem is
                disabled).
        """
        if not text or not text.strip():
            raise EmptyContextError("Context Compression input text must not be empty.")

        provider = self._require_current_provider()
        chunks = self._chunks_from_text(text)
        character_count = len(text)
        estimated_tokens = provider.estimate_tokens(text)
        return character_count, estimated_tokens, len(chunks)

    # ---------- Internal helpers ----------

    def _require_current_provider(self):
        """Return the currently selected provider, or raise if none is selected.

        Returns:
            The active CompressionProvider.

        Raises:
            NoCompressionProviderSelectedError: If no compression
                provider is currently selected (or the subsystem is
                disabled).
        """
        provider = self._manager.get_current()
        if provider is None:
            raise NoCompressionProviderSelectedError(
                "No compression provider is currently selected. "
                "Use 'compression use <provider>'."
            )
        return provider

    @staticmethod
    def _chunks_from_text(text: str) -> list[ContextChunk]:
        """Split `text` into one `ContextChunk` per paragraph (blank-line-separated).

        Args:
            text: The raw text to split.

        Returns:
            One chunk per non-blank paragraph, in original order,
            each with empty metadata. If `text` has no blank-line
            separator, the whole text becomes a single chunk.
        """
        paragraphs = [
            paragraph.strip()
            for paragraph in _PARAGRAPH_SPLIT_PATTERN.split(text.strip())
            if paragraph.strip()
        ]
        return [ContextChunk(text=paragraph, index=i) for i, paragraph in enumerate(paragraphs)]
