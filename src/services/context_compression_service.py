"""Business logic for EP-027 Context Compression CLI integration.

CompressionService is a thin, CLI-facing wrapper around
CompressionEngine and CompressionManager. It owns no compression logic
itself -- provider selection and default limits stay inside
CompressionManager exactly as implemented for EP-027, and chunk
splitting, deduplication, ordering and limit enforcement stay inside
CompressionEngine / CompressionProvider; this service only forwards
calls to them and adapts the results to dataclasses/CommandResult for
ContextCompressionModule, matching every other Service in this project
(see src/services/semantic_service.py's SemanticService -> SemanticEngine
pattern):

    ContextCompressionModule -> CompressionService -> CompressionEngine -> CompressionManager

It implements no business logic belonging to any other module and
never imports from src.core.rag or src.core.ai (Context Compression
must not generate answers, call an AI provider, build prompts, or
reason).

EP-057 Memory Optimization (Owner Decision D1, "Candidate A") adds
`query()`, a thin forward to CompressionEngine.compress_query() --
already-built, already-tested (EP-027), previously reachable only
from EP-027's own test suite. `query()` introduces no new compression
or semantic-search logic of its own: it composes the same
already-existing engine call `compress()` composes for
`compress_text()`, adapted to `compress_query()`'s own signature and
exception surface. Per Owner Decision D2, `top_k`/`threshold` are not
exposed as CLI arguments in v1 -- callers rely on 'semantic.top_k' /
'semantic.similarity_threshold''s already-configured defaults, so
`query()` takes no such parameters.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.command_router import CommandResult
from src.core.context_compression.compression_engine import CompressionEngine, CompressionEngineError
from src.core.context_compression.compression_manager import (
    CompressionManager,
    CompressionProviderNotFoundError,
)
from src.core.context_compression.compression_provider import (
    CompressionConfigurationError,
    CompressionProviderError,
)
from src.core.context_compression.compression_result import CompressionResult


@dataclass(frozen=True)
class CompressionStatus:
    """Result of `compression status`.

    Attributes:
        enabled: Whether the Context Compression subsystem is
            currently enabled.
        current_provider: The currently selected provider's name, or
            None if no provider is selected.
        registered_provider_count: Number of providers registered with
            the CompressionManager.
        max_context_characters: The current default maximum total
            character count for compressed context.
        max_chunks: The current default maximum number of chunks a
            compressed result may contain.
        deduplicate: Whether deduplication is applied by default.
    """

    enabled: bool
    current_provider: str | None
    registered_provider_count: int
    max_context_characters: int
    max_chunks: int
    deduplicate: bool


@dataclass(frozen=True)
class CompressionProviderInfo:
    """One row of `compression providers` output.

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
    """Result of `compression use <provider>`.

    Attributes:
        success: Whether the provider was successfully selected.
        provider: The requested provider name.
        message: Human-readable outcome summary.
    """

    success: bool
    provider: str
    message: str


@dataclass(frozen=True)
class AnalyzeOutcome:
    """Result of `compression analyze "<text>"`.

    Attributes:
        success: Whether the analysis completed successfully.
        text: The text that was analyzed.
        character_count: The text's raw character count.
        estimated_tokens: The active provider's estimated token count
            for the text, uncompressed.
        chunk_count: The number of paragraph chunks `text` would split
            into.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    text: str
    character_count: int
    estimated_tokens: int
    chunk_count: int
    error: str


@dataclass(frozen=True)
class CompressOutcome:
    """Result of `compression compress "<text>"`.

    Attributes:
        success: Whether the compression completed successfully.
        text: The text that was requested to be compressed.
        result: The resulting CompressionResult, or None on failure.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    text: str
    result: CompressionResult | None
    error: str


@dataclass(frozen=True)
class QueryOutcome:
    """Result of `compression query "<text>"` (EP-057).

    Attributes:
        success: Whether the query completed successfully.
        query: The natural-language query that was searched for.
        result: The resulting CompressionResult, or None on failure.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    query: str
    result: CompressionResult | None
    error: str


@dataclass(frozen=True)
class CompressionLimits:
    """Result of `compression limits`.

    Attributes:
        max_context_characters: The current default maximum total
            character count for compressed context.
        max_chunks: The current default maximum number of chunks a
            compressed result may contain.
        deduplicate: Whether deduplication is applied by default.
    """

    max_context_characters: int
    max_chunks: int
    deduplicate: bool


class CompressionService:
    """Coordinates CompressionEngine/CompressionManager and exposes them as a CLI-friendly API.

    Depends only on CompressionEngine and CompressionManager (EP-027).
    Implements no compression logic of its own -- every call is
    forwarded unchanged; this class only adapts return values to
    dataclasses/CommandResult for ContextCompressionModule.
    """

    def __init__(self, manager: CompressionManager, engine: CompressionEngine) -> None:
        """Initialize the CompressionService.

        Args:
            manager: The CompressionManager this service reports on
                and selects providers through.
            engine: The CompressionEngine this service requests
                analysis/compression through.
        """
        self._manager = manager
        self._engine = engine

    def status(self) -> CompressionStatus:
        """Return the Context Compression subsystem's overall status."""
        return CompressionStatus(
            enabled=self._manager.is_enabled(),
            current_provider=self._manager.current_provider_name(),
            registered_provider_count=len(self._manager.list_providers()),
            max_context_characters=self._manager.max_context_characters(),
            max_chunks=self._manager.max_chunks(),
            deduplicate=self._manager.deduplicate(),
        )

    def list_providers(self) -> list[CompressionProviderInfo]:
        """List every registered compression provider and its diagnostic flags."""
        current_name = self._manager.current_provider_name()
        return [
            CompressionProviderInfo(
                name=provider.provider_name(),
                available=provider.is_available(),
                is_current=provider.provider_name() == current_name,
            )
            for provider in self._manager.list_providers()
        ]

    def use_provider(self, name: str) -> ProviderSelectionResult:
        """Select a compression provider as the currently active provider.

        Args:
            name: The registered provider name to activate.

        Returns:
            A ProviderSelectionResult reflecting whether `name` was
            selected.
        """
        try:
            self._manager.set_current(name)
        except CompressionProviderNotFoundError as exc:
            return ProviderSelectionResult(success=False, provider=name, message=str(exc))

        return ProviderSelectionResult(
            success=True, provider=name, message=f"Compression provider set to '{name}'."
        )

    def disable(self) -> CommandResult:
        """Disable the Context Compression subsystem."""
        self._manager.disable()
        return CommandResult(success=True, message="Context Compression subsystem disabled.")

    def analyze(self, text: str) -> AnalyzeOutcome:
        """Analyze `text`'s size/token/chunk footprint, without compressing it.

        Args:
            text: The text to analyze.

        Returns:
            An AnalyzeOutcome describing the outcome.
        """
        try:
            character_count, estimated_tokens, chunk_count = self._engine.estimate(text)
        except CompressionEngineError as exc:
            logger.error(f"Context Compression analyze failed: {exc}")
            return AnalyzeOutcome(
                success=False,
                text=text,
                character_count=0,
                estimated_tokens=0,
                chunk_count=0,
                error=str(exc),
            )

        return AnalyzeOutcome(
            success=True,
            text=text,
            character_count=character_count,
            estimated_tokens=estimated_tokens,
            chunk_count=chunk_count,
            error="",
        )

    def compress(self, text: str) -> CompressOutcome:
        """Compress `text` using the currently active provider and default limits.

        Args:
            text: The text to compress.

        Returns:
            A CompressOutcome describing the outcome.
        """
        try:
            result = self._engine.compress_text(text)
        except (CompressionEngineError, CompressionProviderError) as exc:
            logger.error(f"Context Compression compress failed: {exc}")
            return CompressOutcome(success=False, text=text, result=None, error=str(exc))

        return CompressOutcome(success=True, text=text, result=result, error="")

    def query(self, query: str) -> QueryOutcome:
        """Run a semantic search for `query`, then compress its results (EP-057).

        Thin forward to the already-existing, already-tested
        `CompressionEngine.compress_query()` (EP-027) -- reuses
        'semantic.top_k' / 'semantic.similarity_threshold''s own,
        already-configured defaults (Owner Decision D2); no per-call
        override is exposed here.

        Args:
            query: The natural-language query to search for.

        Returns:
            A QueryOutcome describing the outcome.
        """
        try:
            result = self._engine.compress_query(query)
        except (CompressionEngineError, CompressionProviderError) as exc:
            logger.error(f"Context Compression query failed: {exc}")
            return QueryOutcome(success=False, query=query, result=None, error=str(exc))

        return QueryOutcome(success=True, query=query, result=result, error="")

    def limits(self) -> CompressionLimits:
        """Return the current default compression limits."""
        return CompressionLimits(
            max_context_characters=self._manager.max_context_characters(),
            max_chunks=self._manager.max_chunks(),
            deduplicate=self._manager.deduplicate(),
        )

    def set_max_context_characters(self, value: int) -> CommandResult:
        """Set the default maximum total character count for compressed context.

        Args:
            value: The new default maximum, a positive integer.

        Returns:
            A CommandResult reflecting whether the limit was updated.
        """
        try:
            self._manager.set_max_context_characters(value)
        except CompressionConfigurationError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Max context characters set to {value}.")

    def set_max_chunks(self, value: int) -> CommandResult:
        """Set the default maximum number of chunks a compressed result may contain.

        Args:
            value: The new default maximum, a positive integer.

        Returns:
            A CommandResult reflecting whether the limit was updated.
        """
        try:
            self._manager.set_max_chunks(value)
        except CompressionConfigurationError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Max chunks set to {value}.")
