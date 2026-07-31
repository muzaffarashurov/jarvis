"""Business logic for EP-022 RAG Engine CLI integration.

RagService is a thin, CLI-facing wrapper around `RagManager`. It owns
no RAG logic itself -- index/retrieval-engine lifecycle, embedding
provider selection, and the query/context pipeline all stay inside
`RagManager`/`RagEngine` exactly as implemented for EP-022; this
service only forwards calls to them and adapts the results to
dataclasses/`CommandResult` for `RagModule`, matching every other
Service in this project (see `src/services/embedding_service.py`'s
`EmbeddingService` -> `EmbeddingEngine`/`EmbeddingManager` pattern):

    RagModule -> RagService -> RagManager -> RagEngine

It implements no business logic belonging to any other module and
never imports from `src.core.ai` (the RAG Engine must not perform chat
completion -- see `src/core/rag/rag_engine.py`'s module docstring).
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.embedding.manager import EmbeddingProviderNotFoundError
from src.core.rag.rag_engine import RagEngineError
from src.core.rag.rag_manager import RagManager, RagManagerError
from src.core.rag.rag_provider import NoEmbeddingProviderError, RagProviderInfo
from src.core.rag.rag_result import RagResult


@dataclass(frozen=True)
class RagStatus:
    """Result of `rag status`.

    Attributes:
        enabled: Whether the RAG subsystem is currently enabled.
        index_built: Whether a ProjectIndex (EP-019) currently exists.
        document_count: Number of indexed documents (0 if no index).
        chunk_count: Number of indexed chunks (0 if no index).
        current_provider: The currently selected embedding provider's
            name, or None if no provider is selected.
        provider_available: Whether the current embedding provider is
            enabled and fully configured.
        top_k: The RAG Engine's configured default number of chunks
            assembled into context.
        max_context_characters: The RAG Engine's configured maximum
            assembled context size, in characters.
    """

    enabled: bool
    index_built: bool
    document_count: int
    chunk_count: int
    current_provider: str | None
    provider_available: bool
    top_k: int
    max_context_characters: int


@dataclass(frozen=True)
class RagQueryOutcome:
    """Result of `rag query "<text>"`.

    Attributes:
        success: Whether the RAG pipeline completed successfully.
        result: The structured RagResult, or None on failure.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    result: RagResult | None
    error: str


@dataclass(frozen=True)
class RagContextOutcome:
    """Result of `rag context "<text>"`.

    Attributes:
        success: Whether the RAG pipeline completed successfully.
        context: The assembled context text, or "" on failure or if
            nothing matched.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    context: str
    error: str


@dataclass(frozen=True)
class RagProviderOutcome:
    """Result of `rag provider`.

    Attributes:
        success: Whether an embedding provider is currently selected.
        info: A RagProviderInfo snapshot, or None on failure.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    info: RagProviderInfo | None
    error: str


@dataclass(frozen=True)
class RagProviderSelectionResult:
    """Result of `rag use <provider>`.

    Attributes:
        success: Whether the embedding provider was successfully selected.
        provider: The requested provider name.
        message: Human-readable outcome summary.
    """

    success: bool
    provider: str
    message: str


class RagService:
    """Coordinates RagManager and exposes it as a CLI-friendly API.

    Depends only on RagManager (EP-022). Implements no RAG logic of
    its own -- every call is forwarded unchanged; this class only
    adapts return values (and RagManager's exceptions) to
    dataclasses/`CommandResult` for `RagModule`.
    """

    def __init__(self, manager: RagManager) -> None:
        """Initialize the RagService.

        Args:
            manager: The RagManager this service reports on and
                drives the RAG pipeline through.
        """
        self._manager = manager

    def status(self) -> RagStatus:
        """Return the RAG subsystem's overall status."""
        index = self._manager.current_index()
        if index is not None:
            stats = index.statistics()
            document_count = int(stats.get("document_count", 0))
            chunk_count = int(stats.get("chunk_count", 0))
        else:
            document_count = 0
            chunk_count = 0

        try:
            provider = self._manager.provider_info()
            current_provider = provider.name
            provider_available = provider.available
        except NoEmbeddingProviderError:
            current_provider = None
            provider_available = False

        return RagStatus(
            enabled=self._manager.is_enabled(),
            index_built=index is not None,
            document_count=document_count,
            chunk_count=chunk_count,
            current_provider=current_provider,
            provider_available=provider_available,
            top_k=self._manager.top_k,
            max_context_characters=self._manager.max_context_characters,
        )

    def query(self, text: str, top_k: int | None = None) -> RagQueryOutcome:
        """Run the full RAG pipeline for `text` and return a structured outcome.

        Args:
            text: The user's query text.
            top_k: Maximum number of chunks to assemble into context.

        Returns:
            A RagQueryOutcome describing the outcome.
        """
        try:
            result = self._manager.query(text, top_k=top_k)
        except (RagManagerError, RagEngineError, NoEmbeddingProviderError, ValueError) as exc:
            logger.error(f"RAG query failed: {exc}")
            return RagQueryOutcome(success=False, result=None, error=str(exc))

        return RagQueryOutcome(success=True, result=result, error="")

    def context(self, text: str, top_k: int | None = None) -> RagContextOutcome:
        """Run the full RAG pipeline for `text` and return only the assembled context text.

        Args:
            text: The user's query text.
            top_k: Maximum number of chunks to assemble into context.

        Returns:
            A RagContextOutcome describing the outcome.
        """
        outcome = self.query(text, top_k=top_k)
        if not outcome.success:
            return RagContextOutcome(success=False, context="", error=outcome.error)
        return RagContextOutcome(success=True, context=outcome.result.context, error="")

    def provider(self) -> RagProviderOutcome:
        """Return a snapshot of the embedding provider currently backing RAG."""
        try:
            info = self._manager.provider_info()
        except NoEmbeddingProviderError as exc:
            return RagProviderOutcome(success=False, info=None, error=str(exc))
        return RagProviderOutcome(success=True, info=info, error="")

    def use_provider(self, name: str) -> RagProviderSelectionResult:
        """Select the embedding provider used for future RAG queries.

        Args:
            name: The registered embedding provider name to activate.

        Returns:
            A RagProviderSelectionResult reflecting whether `name` was
            selected.
        """
        try:
            self._manager.use_provider(name)
        except EmbeddingProviderNotFoundError as exc:
            return RagProviderSelectionResult(success=False, provider=name, message=str(exc))

        return RagProviderSelectionResult(
            success=True, provider=name, message=f"RAG embedding provider set to '{name}'."
        )

    def disable(self) -> RagStatus:
        """Disable the RAG subsystem and return its resulting status."""
        self._manager.disable()
        return self.status()
