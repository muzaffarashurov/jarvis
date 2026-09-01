"""Context compression module: CLI command surface for EP-027 Context Compression.

Exposes the "compression" command namespace (help, status, providers,
use, analyze, compress, query, limits) as thin CommandModule handlers,
following the same pattern as SemanticModule/EmbeddingModule. All
orchestration logic lives in CompressionService; this module only
formats CommandResult objects for the shell.

EP-057 Memory Optimization (Owner Decision D1/D4, "Candidate A") adds
the "query" action, forwarding to CompressionService.query() --
already-built, already-tested Context Compression/Semantic Search
infrastructure (EP-027/EP-026), previously exposed only to EP-027's
own test suite. Every other action is unchanged.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.context_compression_service import (
    AnalyzeOutcome,
    CompressionLimits,
    CompressionProviderInfo,
    CompressionService,
    CompressionStatus,
    CompressOutcome,
    ProviderSelectionResult,
    QueryOutcome,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "compression help\n"
    "compression status\n"
    "compression providers\n"
    "compression use <provider>\n"
    'compression analyze "<text>"\n'
    'compression compress "<text>"\n'
    'compression query "<text>"\n'
    "compression limits"
)

ActionHandler = Callable[[list[str]], CommandResult]


class ContextCompressionModule:
    """Built-in "compression" command namespace for Context Compression."""

    def __init__(self, compression_service: CompressionService) -> None:
        """Initialize the ContextCompressionModule.

        Args:
            compression_service: The service used to inspect and
                control the Context Compression subsystem and its
                registered providers.
        """
        self._service = compression_service
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "status": self._status,
            "providers": self._providers,
            "use": self._use,
            "analyze": self._analyze,
            "compress": self._compress,
            "query": self._query,
            "limits": self._limits,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "compression"."""
        return "compression"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "compression" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a provider name).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "compression help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available compression commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the Context Compression subsystem's overall status."""
        status: CompressionStatus = self._service.status()
        lines = [
            "Context Compression Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Current provider : {status.current_provider or 'none'}",
            f"Registered providers : {status.registered_provider_count}",
            f"Max context characters : {status.max_context_characters}",
            f"Max chunks : {status.max_chunks}",
            f"Deduplicate : {self._mark(status.deduplicate)}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _providers(self, arguments: list[str]) -> CommandResult:
        """List every registered compression provider and its diagnostic flags."""
        providers: list[CompressionProviderInfo] = self._service.list_providers()
        if not providers:
            return CommandResult(success=True, message="No compression providers registered.")

        header = f"{'Provider':<14}{'Available':<11}{'Current':<8}"
        lines = ["Compression Providers", "", header]
        for provider in providers:
            lines.append(
                f"{provider.name:<14}"
                f"{self._mark(provider.available):<11}"
                f"{self._mark(provider.is_current):<8}"
            )
        return CommandResult(success=True, message="\n".join(lines))

    def _use(self, arguments: list[str]) -> CommandResult:
        """Select a compression provider as the currently active provider.

        Args:
            arguments: `[provider_name]`.

        Returns:
            A CommandResult reflecting whether the provider was selected.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: compression use <provider>")

        result: ProviderSelectionResult = self._service.use_provider(arguments[0].lower())
        return CommandResult(success=result.success, message=result.message)

    def _analyze(self, arguments: list[str]) -> CommandResult:
        """Analyze the given text's size/token/chunk footprint, without compressing it.

        Args:
            arguments: The text words (joined with spaces).

        Returns:
            A CommandResult listing the analysis, or a user-friendly
            error message.
        """
        if not arguments:
            return CommandResult(success=False, message='Usage: compression analyze "<text>"')

        text = " ".join(arguments)
        outcome: AnalyzeOutcome = self._service.analyze(text)
        if not outcome.success:
            return CommandResult(success=False, message=outcome.error)

        lines = [
            "Context Compression Analysis",
            f"Characters : {outcome.character_count}",
            f"Estimated tokens : {outcome.estimated_tokens}",
            f"Chunks : {outcome.chunk_count}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _compress(self, arguments: list[str]) -> CommandResult:
        """Compress the given text using the currently active provider and limits.

        Args:
            arguments: The text words (joined with spaces).

        Returns:
            A CommandResult listing the compression outcome, or a
            user-friendly error message.
        """
        if not arguments:
            return CommandResult(success=False, message='Usage: compression compress "<text>"')

        text = " ".join(arguments)
        outcome: CompressOutcome = self._service.compress(text)
        if not outcome.success or outcome.result is None:
            return CommandResult(success=False, message=outcome.error)

        result = outcome.result
        lines = [
            "Context Compression Result",
            "",
            f"Original chunks : {result.original_chunk_count}",
            f"Compressed chunks : {result.chunk_count}",
            f"Original characters : {result.original_character_count}",
            f"Compressed characters : {result.character_count}",
            f"Estimated tokens : {result.estimated_tokens}",
            f"Deduplicated : {result.deduplicated_chunk_count}",
            f"Truncated : {self._mark(result.truncated)}",
            "",
            result.joined_text(),
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _query(self, arguments: list[str]) -> CommandResult:
        """Search memory for the given query and compress the results (EP-057).

        Args:
            arguments: The query words (joined with spaces).

        Returns:
            A CommandResult listing the query/compression outcome, or
            a user-friendly error message.
        """
        if not arguments:
            return CommandResult(success=False, message='Usage: compression query "<text>"')

        query = " ".join(arguments)
        outcome: QueryOutcome = self._service.query(query)
        if not outcome.success or outcome.result is None:
            return CommandResult(success=False, message=outcome.error)

        result = outcome.result
        lines = [
            "Context Compression Query Result",
            "",
            f"Original chunks : {result.original_chunk_count}",
            f"Compressed chunks : {result.chunk_count}",
            f"Original characters : {result.original_character_count}",
            f"Compressed characters : {result.character_count}",
            f"Estimated tokens : {result.estimated_tokens}",
            f"Deduplicated : {result.deduplicated_chunk_count}",
            f"Truncated : {self._mark(result.truncated)}",
            "",
            result.joined_text(),
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _limits(self, arguments: list[str]) -> CommandResult:
        """Display the current default compression limits."""
        limits: CompressionLimits = self._service.limits()
        lines = [
            "Context Compression Limits",
            f"Max context characters : {limits.max_context_characters}",
            f"Max chunks : {limits.max_chunks}",
            f"Deduplicate : {self._mark(limits.deduplicate)}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "YES" or "NO"."""
        return "YES" if value else "NO"
