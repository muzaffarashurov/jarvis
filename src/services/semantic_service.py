"""Business logic for EP-026 Semantic Search CLI integration.

SemanticService is a thin, CLI-facing wrapper around SemanticEngine
and SemanticManager. It owns no search logic itself -- provider
selection and default parameters stay inside SemanticManager exactly
as implemented for EP-026, and embedding, candidate gathering,
similarity calculation and ranking stay inside SemanticEngine /
SemanticProvider; this service only forwards calls to them and adapts
the results to dataclasses/CommandResult for SemanticModule, matching
every other Service in this project (see
src/services/embedding_service.py's EmbeddingService ->
EmbeddingEngine pattern):

    SemanticModule -> SemanticService -> SemanticEngine -> SemanticManager

It implements no business logic belonging to any other module and
never imports from src.core.rag or src.core.ai (Semantic Search must
not generate answers, call an AI provider, build prompts, or reason).
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.command_router import CommandResult
from src.core.semantic.semantic_engine import SemanticEngine, SemanticEngineError
from src.core.semantic.semantic_manager import SemanticManager, SemanticProviderNotFoundError
from src.core.semantic.semantic_provider import (
    SemanticConfigurationError,
    SemanticProviderError,
)
from src.core.semantic.semantic_result import SemanticResult


@dataclass(frozen=True)
class SemanticStatus:
    """Result of `semantic status`.

    Attributes:
        enabled: Whether the Semantic Search subsystem is currently
            enabled.
        current_provider: The currently selected provider's name, or
            None if no provider is selected.
        registered_provider_count: Number of providers registered with
            the SemanticManager.
        top_k: The current default maximum number of results per search.
        similarity_threshold: The current default minimum similarity
            score a result must reach.
        embedding_provider_warning: A human-readable warning if the
            active embedding provider is EP-021's non-semantic
            built-in "local" hash provider (see
            `SemanticEngine.embedding_provider_warning`), else None.
    """

    enabled: bool
    current_provider: str | None
    registered_provider_count: int
    top_k: int
    similarity_threshold: float
    embedding_provider_warning: str | None = None


@dataclass(frozen=True)
class SemanticProviderInfo:
    """One row of `semantic providers` output.

    Attributes:
        name: The provider's registered name.
        available: Whether the provider is enabled and fully configured.
        is_current: Whether this is the currently selected provider.
    """

    name: str
    available: bool
    is_current: bool


@dataclass(frozen=True)
class ProviderSelectionResult:
    """Result of `semantic use <provider>`.

    Attributes:
        success: Whether the provider was successfully selected.
        provider: The requested provider name.
        message: Human-readable outcome summary.
    """

    success: bool
    provider: str
    message: str


@dataclass(frozen=True)
class SemanticSearchOutcome:
    """Result of `semantic search "<query>"`.

    Attributes:
        success: Whether the search completed successfully.
        query: The search query that was requested.
        results: The matching records, most relevant first. Empty on
            failure or when nothing matched.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    query: str
    results: list[SemanticResult]
    error: str


class SemanticService:
    """Coordinates SemanticEngine/SemanticManager and exposes them as a CLI-friendly API.

    Depends only on SemanticEngine and SemanticManager (EP-026).
    Implements no semantic search logic of its own -- every call is
    forwarded unchanged; this class only adapts return values to
    dataclasses/CommandResult for SemanticModule.
    """

    def __init__(self, manager: SemanticManager, engine: SemanticEngine) -> None:
        """Initialize the SemanticService.

        Args:
            manager: The SemanticManager this service reports on and
                selects providers through.
            engine: The SemanticEngine this service requests searches
                through.
        """
        self._manager = manager
        self._engine = engine

    def status(self) -> SemanticStatus:
        """Return the Semantic Search subsystem's overall status."""
        return SemanticStatus(
            enabled=self._manager.is_enabled(),
            current_provider=self._manager.current_provider_name(),
            registered_provider_count=len(self._manager.list_providers()),
            top_k=self._manager.top_k(),
            similarity_threshold=self._manager.similarity_threshold(),
            embedding_provider_warning=self._engine.embedding_provider_warning(),
        )

    def list_providers(self) -> list[SemanticProviderInfo]:
        """List every registered semantic provider and its diagnostic flags."""
        current_name = self._manager.current_provider_name()
        return [
            SemanticProviderInfo(
                name=provider.provider_name(),
                available=provider.is_available(),
                is_current=provider.provider_name() == current_name,
            )
            for provider in self._manager.list_providers()
        ]

    def use_provider(self, name: str) -> ProviderSelectionResult:
        """Select a semantic provider as the currently active provider.

        Args:
            name: The registered provider name to activate.

        Returns:
            A ProviderSelectionResult reflecting whether `name` was
            selected.
        """
        try:
            self._manager.set_current(name)
        except SemanticProviderNotFoundError as exc:
            return ProviderSelectionResult(success=False, provider=name, message=str(exc))

        return ProviderSelectionResult(
            success=True, provider=name, message=f"Semantic provider set to '{name}'."
        )

    def disable(self) -> CommandResult:
        """Disable the Semantic Search subsystem."""
        self._manager.disable()
        return CommandResult(success=True, message="Semantic Search subsystem disabled.")

    def search(
        self, query: str, top_k: int | None = None, threshold: float | None = None
    ) -> SemanticSearchOutcome:
        """Perform a semantic similarity search.

        Args:
            query: The natural-language search query.
            top_k: Maximum number of results to return, or None to use
                the current default.
            threshold: Minimum similarity score a result must reach,
                or None to use the current default.

        Returns:
            A SemanticSearchOutcome describing the outcome.
        """
        try:
            results = self._engine.search(query, top_k=top_k, threshold=threshold)
        except (SemanticEngineError, SemanticProviderError) as exc:
            logger.error(f"Semantic search failed: {exc}")
            return SemanticSearchOutcome(success=False, query=query, results=[], error=str(exc))

        return SemanticSearchOutcome(success=True, query=query, results=results, error="")

    def threshold(self) -> float:
        """Return the current default similarity threshold."""
        return self._manager.similarity_threshold()

    def set_threshold(self, value: float) -> CommandResult:
        """Set the default similarity threshold.

        Args:
            value: The new default threshold, between 0.0 and 1.0.

        Returns:
            A CommandResult reflecting whether the threshold was
            updated.
        """
        try:
            self._manager.set_similarity_threshold(value)
        except SemanticConfigurationError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Similarity threshold set to {value}.")
