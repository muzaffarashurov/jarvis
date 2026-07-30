"""Business logic for EP-021 Embedding Engine CLI integration.

EmbeddingService is a thin, CLI-facing wrapper around EmbeddingEngine
and EmbeddingManager. It owns no embedding logic itself -- provider
selection, configuration loading and lifecycle stay inside
EmbeddingManager exactly as implemented for EP-021, and batching,
vector validation and error handling stay inside EmbeddingEngine; this
service only forwards calls to them and adapts the results to
dataclasses/CommandResult for EmbeddingModule, matching every other
Service in this project (see src/services/index_service.py's
IndexService -> ProjectIndexer pattern):

    EmbeddingModule -> EmbeddingService -> EmbeddingEngine -> EmbeddingManager

It implements no business logic belonging to any other module and
never imports from src.core.retrieval or src.core.ai (the Embedding
Engine must not perform retrieval, RAG, or chat completion).
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.command_router import CommandResult
from src.core.embedding.engine import EmbeddingEngine, EmbeddingEngineError
from src.core.embedding.manager import EmbeddingManager, EmbeddingProviderNotFoundError
from src.core.embedding.provider import EmbeddingProviderError


@dataclass(frozen=True)
class EmbeddingStatus:
    """Result of `embedding status`.

    Attributes:
        enabled: Whether the Embedding subsystem is currently enabled.
        current_provider: The currently selected provider's name, or
            None if no provider is selected.
        registered_provider_count: Number of providers registered with
            the EmbeddingManager.
        dimension: The current provider's embedding dimension, or None
            if no provider is currently selected.
    """

    enabled: bool
    current_provider: str | None
    registered_provider_count: int
    dimension: int | None


@dataclass(frozen=True)
class EmbeddingProviderInfo:
    """One row of `embedding providers` output.

    Attributes:
        name: The provider's registered name.
        model: The provider's configured model identifier.
        dimension: The provider's embedding dimension.
        available: Whether the provider is enabled and fully configured.
        is_current: Whether this is the currently selected provider.
    """

    name: str
    model: str
    dimension: int
    available: bool
    is_current: bool


@dataclass(frozen=True)
class ProviderSelectionResult:
    """Result of `embedding use <provider>`.

    Attributes:
        success: Whether the provider was successfully selected.
        provider: The requested provider name.
        message: Human-readable outcome summary.
    """

    success: bool
    provider: str
    message: str


@dataclass(frozen=True)
class EmbedResult:
    """Result of `embedding embed "<text>"`.

    Attributes:
        success: Whether an embedding vector was produced.
        provider: The provider name used, or "" on failure before a
            provider could be resolved.
        model: The provider's model identifier, or "" on failure.
        dimension: The vector's length, or 0 on failure.
        vector: The embedding vector, or an empty list on failure.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    provider: str
    model: str
    dimension: int
    vector: list[float]
    error: str


class EmbeddingService:
    """Coordinates EmbeddingEngine/EmbeddingManager and exposes them as a CLI-friendly API.

    Depends only on EmbeddingEngine and EmbeddingManager (EP-021).
    Implements no embedding logic of its own -- every call is
    forwarded unchanged; this class only adapts return values to
    dataclasses/CommandResult for EmbeddingModule.
    """

    def __init__(self, manager: EmbeddingManager, engine: EmbeddingEngine) -> None:
        """Initialize the EmbeddingService.

        Args:
            manager: The EmbeddingManager this service reports on and
                selects providers through.
            engine: The EmbeddingEngine this service requests
                embeddings through.
        """
        self._manager = manager
        self._engine = engine

    def status(self) -> EmbeddingStatus:
        """Return the Embedding subsystem's overall status."""
        current = self._manager.get_current()
        return EmbeddingStatus(
            enabled=self._manager.is_enabled(),
            current_provider=self._manager.current_provider_name(),
            registered_provider_count=len(self._manager.list_providers()),
            dimension=current.dimension() if current is not None else None,
        )

    def list_providers(self) -> list[EmbeddingProviderInfo]:
        """List every registered embedding provider and its diagnostic flags."""
        current_name = self._manager.current_provider_name()
        return [
            EmbeddingProviderInfo(
                name=provider.provider_name(),
                model=provider.model_name(),
                dimension=provider.dimension(),
                available=provider.is_available(),
                is_current=provider.provider_name() == current_name,
            )
            for provider in self._manager.list_providers()
        ]

    def use_provider(self, name: str) -> ProviderSelectionResult:
        """Select an embedding provider as the currently active provider.

        Args:
            name: The registered provider name to activate.

        Returns:
            A ProviderSelectionResult reflecting whether `name` was
            selected.
        """
        try:
            self._manager.set_current(name)
        except EmbeddingProviderNotFoundError as exc:
            return ProviderSelectionResult(success=False, provider=name, message=str(exc))

        return ProviderSelectionResult(
            success=True, provider=name, message=f"Embedding provider set to '{name}'."
        )

    def disable(self) -> CommandResult:
        """Disable the Embedding subsystem."""
        self._manager.disable()
        return CommandResult(success=True, message="Embedding subsystem disabled.")

    def embed(self, text: str) -> EmbedResult:
        """Request a single embedding vector for `text` from the active provider.

        Args:
            text: The text to embed.

        Returns:
            An EmbedResult describing the outcome.
        """
        try:
            vector = self._engine.embed_text(text)
        except (EmbeddingEngineError, EmbeddingProviderError) as exc:
            logger.error(f"Embedding request failed: {exc}")
            return EmbedResult(
                success=False, provider="", model="", dimension=0, vector=[], error=str(exc)
            )

        provider_name = self._manager.current_provider_name() or ""
        current = self._manager.get_current()
        model = current.model_name() if current is not None else ""
        return EmbedResult(
            success=True,
            provider=provider_name,
            model=model,
            dimension=len(vector),
            vector=vector,
            error="",
        )

    def dimension(self) -> tuple[bool, int, str]:
        """Return the currently active provider's embedding dimension.

        Returns:
            `(True, dimension, "")` on success; `(False, 0, error_message)`
            if no provider is currently selected.
        """
        try:
            return True, self._engine.dimension(), ""
        except EmbeddingEngineError as exc:
            return False, 0, str(exc)
