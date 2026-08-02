"""EP-026 Semantic Search Engine.

A provider-independent engine that performs meaning-based similarity
search over Knowledge Base (EP-024) and Long-Term Memory (EP-025)
records: generates a query vector via the Embedding Engine (EP-021),
embeds each candidate record's text representation, and delegates
scoring and ranking to the currently selected `SemanticProvider` (via
`SemanticManager`). This is Semantic Search's entire responsibility --
it must NOT generate answers, call an AI provider, build prompts,
compress context, or reason (see `src/core/semantic/__init__.py`).

Depends only on public APIs:
    - `EmbeddingManager` (EP-021) -- `get_current()`, read-only, used
      solely to detect the built-in, non-semantic "local" hash
      provider (see `_uses_placeholder_embedding_provider`).
    - `EmbeddingEngine` (EP-021) -- `embed_text()` / `embed_texts()`.
    - `KnowledgeService` (EP-024) -- `list_records()`.
    - `LongTermMemoryService` (EP-025) -- `list_memories()`.
    - `SemanticManager` (this package) -- current provider and defaults.

No `RagEngine`, no `Planner`, no `Reflection`, no AI provider, no
prompt engine, no browser automation, no tool calling, no conversation
engine, no agent framework, and no private attribute of any of the
above is ever accessed (only their public methods).

Placeholder-embedding-provider handling (independent audit finding
H1): EP-021 ships exactly one embedding provider that requires no
external service and is therefore active by default --
`LocalHashEmbeddingProvider`, registered under the stable name
"local". By its own documentation it "is not a semantic embedding
model": `_hash_component()` runs the *entire* input text through
SHA-256 as one atomic blob, so by SHA-256's avalanche property, any
two texts that are not byte-identical produce statistically
uncorrelated vectors -- confirmed empirically across eight
related-but-reworded sentence pairs, whose cosine similarities ranged
from -0.60 to +0.34 with no consistent bias toward "more related
means higher score" (e.g. "I like cats" vs. "I like dogs" scored
-0.126, more negative than one pair of genuinely unrelated sentences).
Only byte-identical text reliably scores near 1.0.

An earlier version of this fix relaxed the effective similarity
threshold toward 0.0 for this provider, reasoning that
near-duplicate-but-reworded text scored "low but positive" based on a
couple of anecdotal examples. Broader testing disproved that: since
the scores are genuine noise, relaxing the threshold does not
reliably surface related content -- it only admits a coin-flip ~50%
of *all* candidates, related or not, which is a worse outcome than
returning nothing, because it presents random matches as if they were
ranked, meaningful results. No threshold value fixes this: the
provider carries no exploitable signal for non-identical text, so this
module makes no attempt to choose one. Instead, it detects that
specific, well-known built-in provider by its public, stable
`provider_name()` ("local") and surfaces a clear, queryable warning
via `embedding_provider_warning()` (also surfaced through
`SemanticService.status()` and `semantic status`), so the person using
it understands why only exact/near-exact matches are meaningful and
how to get genuine semantic search (configure a real embedding
provider). The configured `similarity_threshold` is used exactly as
set, for every provider, always -- this module never adjusts it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from src.core.embedding.engine import EmbeddingEngine, EmbeddingEngineError
from src.core.embedding.manager import EmbeddingManager
from src.core.embedding.provider import EmbeddingProviderError
from src.core.semantic.semantic_manager import SemanticManager
from src.core.semantic.semantic_provider import SemanticError, SemanticProviderError
from src.core.semantic.semantic_result import (
    SOURCE_KNOWLEDGE,
    SOURCE_LONG_TERM_MEMORY,
    SemanticCandidate,
    SemanticResult,
)

if TYPE_CHECKING:
    # Deferred, type-checking-only imports: src/core must not depend on
    # src/services at runtime (see src/core/long_term_memory/long_term_provider.py
    # and src/core/plugins/plugin_context.py for the same established
    # pattern elsewhere in this project). These two types are used only
    # in type hints below -- never imported, instantiated, or accessed
    # for anything other than their already-public
    # `list_records()` / `list_memories()` methods, called via
    # ordinary duck typing at runtime.
    from src.services.knowledge_service import KnowledgeService
    from src.services.long_term_memory_service import LongTermMemoryService

__all__ = [
    "SemanticEngine",
    "SemanticEngineError",
    "NoSemanticProviderSelectedError",
    "EmptySemanticQueryError",
    "PLACEHOLDER_EMBEDDING_PROVIDER_NAME",
]

#: The stable `provider_name()` of EP-021's built-in, non-semantic
#: hash-based embedding provider (`LocalHashEmbeddingProvider`). Used
#: only to detect it and warn -- never to special-case
#: any other provider, and never assumed for any name other than this
#: exact, documented, public identifier.
PLACEHOLDER_EMBEDDING_PROVIDER_NAME: str = "local"


class SemanticEngineError(SemanticError):
    """Base class for errors raised by the SemanticEngine itself.

    Inherits from `SemanticError` (src/core/semantic/semantic_provider.py)
    so callers can catch every semantic-search-related failure --
    provider, engine, or manager -- with a single exception type.
    """


class NoSemanticProviderSelectedError(SemanticEngineError):
    """Raised when a search is requested but no semantic provider is currently selected."""


class EmptySemanticQueryError(SemanticEngineError):
    """Raised when a search is requested with an empty (or whitespace-only) query."""


class SemanticEngine:
    """Provider-independent semantic similarity search pipeline.

    Pipeline for `search()`:

        query -> EmbeddingEngine -> query vector
              -> Knowledge Base records (EP-024, optional)
              -> Long-Term Memory records (EP-025, optional)
              -> EmbeddingEngine -> candidate vectors
              -> SemanticProvider.search() -> similarity + ranking
              -> list[SemanticResult]

    Never selects, constructs, or configures providers itself --
    provider selection and lifecycle are exclusively
    `SemanticManager`'s concern. Never calculates similarity or
    ranking itself -- both stay inside the active `SemanticProvider`.
    """

    def __init__(
        self,
        manager: SemanticManager,
        embedding_engine: EmbeddingEngine,
        embedding_manager: EmbeddingManager | None = None,
        knowledge_service: "KnowledgeService | None" = None,
        long_term_memory_service: "LongTermMemoryService | None" = None,
    ) -> None:
        """Initialize the SemanticEngine.

        Args:
            manager: The SemanticManager used to resolve the currently
                active provider and the default `top_k` /
                `similarity_threshold`. Never mutated by this engine.
            embedding_engine: The EmbeddingEngine (EP-021) used to
                generate the query vector and every candidate vector.
            embedding_manager: The EmbeddingManager (EP-021) used only
                to read the active embedding provider's public
                `provider_name()`, to detect EP-021's built-in,
                non-semantic "local" hash provider and warn/adjust
                defaults accordingly (see module docstring). Optional:
                if None, placeholder detection is simply skipped (no
                warning is produced, defaults are never adjusted) --
                this engine still functions normally either way.
            knowledge_service: The KnowledgeService (EP-024) whose
                `list_records()` public method supplies Knowledge Base
                candidates, or None if the Knowledge Base subsystem is
                unavailable this run (candidates from it are then
                simply omitted, never an error).
            long_term_memory_service: The LongTermMemoryService
                (EP-025) whose `list_memories()` public method
                supplies Long-Term Memory candidates, or None if the
                Long-Term Memory subsystem is unavailable this run
                (candidates from it are then simply omitted, never an
                error).
        """
        self._manager = manager
        self._embedding_engine = embedding_engine
        self._embedding_manager = embedding_manager
        self._knowledge_service = knowledge_service
        self._long_term_memory_service = long_term_memory_service
        self._warned_placeholder_provider = False

    def search(
        self,
        query: str,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> list[SemanticResult]:
        """Perform a semantic similarity search over Knowledge Base and Long-Term Memory records.

        Args:
            query: The natural-language search query.
            top_k: Maximum number of results to return. Defaults to
                `manager.top_k()` when None.
            threshold: Minimum similarity score a result must reach.
                Defaults to `manager.similarity_threshold()` when
                None, applied unchanged for every provider (see module
                docstring for why this is never adjusted for the
                built-in "local" placeholder provider).

        Returns:
            The matching records as `SemanticResult` instances, most
            relevant first. Empty if no candidates exist, or if none
            score at or above the effective threshold.

        Raises:
            EmptySemanticQueryError: If `query` is empty or
                whitespace-only.
            NoSemanticProviderSelectedError: If no semantic provider is
                currently selected (or the subsystem is disabled).
            SemanticEngineError: If the Embedding Engine fails to
                produce a query or candidate vector (e.g. no embedding
                provider is currently selected).
            SemanticProviderError: If the active provider itself fails
                to perform the search (e.g. an invalid `top_k`).
        """
        if not query or not query.strip():
            raise EmptySemanticQueryError("Semantic search query must not be empty.")

        provider = self._require_current_provider()
        resolved_top_k = top_k if top_k is not None else self._manager.top_k()
        resolved_threshold = threshold if threshold is not None else self._default_threshold()

        query_vector = self._embed(query)

        candidates = self._build_candidates()
        if not candidates:
            return []

        try:
            return provider.search(query_vector, candidates, resolved_top_k, resolved_threshold)
        except SemanticProviderError:
            raise

    def _default_threshold(self) -> float:
        """Return the threshold to use when the caller did not pass one explicitly.

        Always `manager.similarity_threshold()`, unchanged -- see the
        module docstring for why no threshold value is adjusted for
        the placeholder provider. When the active embedding provider
        is EP-021's built-in, non-semantic "local" hash provider, also
        logs a one-time warning identical to
        `embedding_provider_warning()`'s message, so the limitation is
        visible even to callers who never inspect `semantic status`.

        Returns:
            The effective default similarity threshold for this search.
        """
        if self._uses_placeholder_embedding_provider() and not self._warned_placeholder_provider:
            logger.warning(self.embedding_provider_warning())
            self._warned_placeholder_provider = True
        return self._manager.similarity_threshold()

    def _uses_placeholder_embedding_provider(self) -> bool:
        """Return whether the active embedding provider is EP-021's non-semantic hash provider.

        Returns:
            True if an `EmbeddingManager` was supplied and its current
            provider's public `provider_name()` equals
            `PLACEHOLDER_EMBEDDING_PROVIDER_NAME` ("local"). False if
            no `EmbeddingManager` was supplied, no provider is
            currently selected, or the active provider is anything
            else (including a future, genuinely semantic local model
            that happens to be registered under a different name).
        """
        if self._embedding_manager is None:
            return False
        current = self._embedding_manager.get_current()
        if current is None:
            return False
        return current.provider_name() == PLACEHOLDER_EMBEDDING_PROVIDER_NAME

    def embedding_provider_warning(self) -> str | None:
        """Return a human-readable warning if the active embedding provider is non-semantic.

        Callable at any time (before or independent of any `search()`
        call) so `SemanticService`/`semantic status` can surface it
        proactively, not only after a search has already run.

        Returns:
            A warning message if `_uses_placeholder_embedding_provider()`
            is True, else None.
        """
        if not self._uses_placeholder_embedding_provider():
            return None
        return (
            "The active embedding provider is 'local' (EP-021's built-in "
            "SHA-256 hash provider): it hashes each text as a whole, so "
            "only byte-identical text scores highly (~1.0) -- any other "
            "text, related or not, scores as uncorrelated noise. Results "
            "beyond exact/near-exact matches are not meaningful. "
            "Configure a real embedding provider "
            "('embedding.default_provider') for genuine semantic search."
        )

    def _require_current_provider(self):
        """Return the currently selected provider, or raise if none is selected.

        Returns:
            The active SemanticProvider.

        Raises:
            NoSemanticProviderSelectedError: If no semantic provider is
                currently selected (or the subsystem is disabled).
        """
        provider = self._manager.get_current()
        if provider is None:
            raise NoSemanticProviderSelectedError(
                "No semantic provider is currently selected. Use 'semantic use <provider>'."
            )
        return provider

    def _embed(self, text: str) -> list[float]:
        """Request a single embedding vector for `text` from the Embedding Engine.

        Args:
            text: The text to embed.

        Returns:
            The embedding vector for `text`.

        Raises:
            SemanticEngineError: If the Embedding Engine cannot
                currently produce an embedding.
        """
        try:
            return self._embedding_engine.embed_text(text)
        except (EmbeddingEngineError, EmbeddingProviderError) as exc:
            raise SemanticEngineError(f"Semantic search embedding failed: {exc}") from exc

    def _build_candidates(self) -> list[SemanticCandidate]:
        """Gather and embed every searchable candidate from Knowledge Base and Long-Term Memory.

        EP-025's built-in `KnowledgeBackedLongTermProvider` persists
        Long-Term Memory records inside `KnowledgeService`'s own
        storage (`knowledge_service.list_records()` and
        `long_term_memory_service.list_memories()` can therefore both
        surface the very same physical record, under the same
        identifier, through two different subsystem facades). To avoid
        returning that record twice under two different `source`
        labels, an identifier reachable through Long-Term Memory takes
        precedence: the matching Knowledge Base entry is dropped, and
        only the `SOURCE_LONG_TERM_MEMORY`-labeled one is kept, since
        that is the more specific origin for it.

        Returns:
            One `SemanticCandidate` per distinct, non-empty record
            text, Long-Term Memory records first, followed by every
            Knowledge Base record not already covered by one.

        Raises:
            SemanticEngineError: If the Embedding Engine cannot
                currently produce candidate embeddings.
        """
        long_term_memory_sources = self._long_term_memory_candidates()
        long_term_memory_ids = {identifier for _s, identifier, _t, _m in long_term_memory_sources}

        knowledge_sources = [
            entry
            for entry in self._knowledge_candidates()
            if entry[1] not in long_term_memory_ids
        ]

        sources: list[tuple[str, str, str, dict]] = long_term_memory_sources + knowledge_sources

        if not sources:
            return []

        texts = [text for _source, _identifier, text, _metadata in sources]
        try:
            vectors = self._embedding_engine.embed_texts(texts)
        except (EmbeddingEngineError, EmbeddingProviderError) as exc:
            raise SemanticEngineError(f"Semantic search embedding failed: {exc}") from exc

        return [
            SemanticCandidate(
                source=source, identifier=identifier, text=text, vector=vector, metadata=metadata
            )
            for (source, identifier, text, metadata), vector in zip(sources, vectors)
        ]

    def _knowledge_candidates(self) -> list[tuple[str, str, str, dict]]:
        """Return `(source, identifier, text, metadata)` tuples for every Knowledge Base record.

        Returns:
            One tuple per Knowledge Base record with non-empty text,
            or an empty list if no `KnowledgeService` was supplied.
        """
        if self._knowledge_service is None:
            return []

        candidates: list[tuple[str, str, str, dict]] = []
        for record in self._knowledge_service.list_records():
            text = self._as_text(record.content)
            if text:
                candidates.append((SOURCE_KNOWLEDGE, record.key, text, dict(record.metadata)))
        return candidates

    def _long_term_memory_candidates(self) -> list[tuple[str, str, str, dict]]:
        """Return `(source, identifier, text, metadata)` tuples for every Long-Term Memory record.

        Returns:
            One tuple per Long-Term Memory record with non-empty text,
            or an empty list if no `LongTermMemoryService` was
            supplied.
        """
        if self._long_term_memory_service is None:
            return []

        candidates: list[tuple[str, str, str, dict]] = []
        for record in self._long_term_memory_service.list_memories():
            text = self._as_text(record.content)
            if text:
                candidates.append(
                    (SOURCE_LONG_TERM_MEMORY, record.id, text, dict(record.metadata))
                )
        return candidates

    @staticmethod
    def _as_text(content: object) -> str:
        """Return a searchable text representation of a record's `content`.

        Args:
            content: A record's `content` field, which may already be
                a string or any other JSON-serializable value.

        Returns:
            `content` unchanged if it is already a non-blank string,
            `str(content)` for any other non-None value, or an empty
            string for blank/None content (such records are excluded
            from the candidate set).
        """
        if content is None:
            return ""
        if isinstance(content, str):
            return content.strip()
        return str(content).strip()
