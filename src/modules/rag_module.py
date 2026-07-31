"""RAG module: CLI command surface for EP-022 RAG Engine.

Exposes the "rag" command namespace (help, status, query, context,
provider, use) as thin CommandModule handlers, following the same
pattern as EmbeddingModule/IndexModule. All orchestration logic lives
in RagService; this module only formats CommandResult objects for the
shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.rag_service import (
    RagContextOutcome,
    RagProviderOutcome,
    RagProviderSelectionResult,
    RagQueryOutcome,
    RagService,
    RagStatus,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "rag help\n"
    "rag status\n"
    'rag query "<text>"\n'
    'rag context "<text>"\n'
    "rag provider\n"
    "rag use <provider>"
)

ActionHandler = Callable[[list[str]], CommandResult]


class RagModule:
    """Built-in "rag" command namespace for the RAG Engine."""

    def __init__(self, rag_service: RagService) -> None:
        """Initialize the RagModule.

        Args:
            rag_service: The service used to inspect and drive the RAG
                subsystem (index status, query, context assembly, and
                embedding provider selection).
        """
        self._service = rag_service
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "status": self._status,
            "query": self._query,
            "context": self._context,
            "provider": self._provider,
            "use": self._use,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "rag"."""
        return "rag"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "rag" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. the query text).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "rag help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available rag commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the RAG subsystem's overall status."""
        status: RagStatus = self._service.status()
        lines = [
            "RAG Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Index built : {self._mark(status.index_built)}",
            f"Documents : {status.document_count}",
            f"Chunks : {status.chunk_count}",
            f"Current provider : {status.current_provider or 'none'}",
            f"Provider available : {self._mark(status.provider_available)}",
            f"Top K : {status.top_k}",
            f"Max context characters : {status.max_context_characters}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _query(self, arguments: list[str]) -> CommandResult:
        """Run the full RAG pipeline for the given text and summarize the result.

        Args:
            arguments: The query text words (joined with spaces).

        Returns:
            A CommandResult with the query's structured outcome
            summary, or a user-friendly error message.
        """
        if not arguments:
            return CommandResult(success=False, message='Usage: rag query "<text>"')

        text = " ".join(arguments)
        outcome: RagQueryOutcome = self._service.query(text)
        if not outcome.success:
            return CommandResult(success=False, message=outcome.error)

        result = outcome.result
        lines = [
            f"Query : {result.query}",
            f"Provider : {result.provider}",
            f"Model : {result.model}",
            f"Embedding dimension : {result.embedding_dimension}",
            f"Items : {len(result.items)}",
            f"Truncated : {self._mark(result.truncated)}",
        ]
        if result.items:
            lines.append("")
            lines.append("Top matches:")
            for item in result.items:
                heading_part = f" — {item.heading}" if item.heading else ""
                lines.append(f"  [{item.score:.2f}] {item.relative_path}{heading_part}")
        else:
            lines.append("")
            lines.append("No matching context found.")
        return CommandResult(success=True, message="\n".join(lines))

    def _context(self, arguments: list[str]) -> CommandResult:
        """Run the full RAG pipeline for the given text and return only the assembled context.

        Args:
            arguments: The query text words (joined with spaces).

        Returns:
            A CommandResult with the assembled context text, or a
            user-friendly error message.
        """
        if not arguments:
            return CommandResult(success=False, message='Usage: rag context "<text>"')

        text = " ".join(arguments)
        outcome: RagContextOutcome = self._service.context(text)
        if not outcome.success:
            return CommandResult(success=False, message=outcome.error)
        if not outcome.context:
            return CommandResult(success=True, message="No matching context found.")
        return CommandResult(success=True, message=outcome.context)

    def _provider(self, arguments: list[str]) -> CommandResult:
        """Display the embedding provider currently backing the RAG Engine."""
        outcome: RagProviderOutcome = self._service.provider()
        if not outcome.success:
            return CommandResult(success=False, message=outcome.error)

        info = outcome.info
        lines = [
            "RAG Embedding Provider",
            f"Name : {info.name}",
            f"Model : {info.model}",
            f"Dimension : {info.dimension}",
            f"Available : {self._mark(info.available)}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _use(self, arguments: list[str]) -> CommandResult:
        """Select an embedding provider for future RAG queries.

        Args:
            arguments: `[provider_name]`.

        Returns:
            A CommandResult reflecting whether the provider was selected.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: rag use <provider>")

        result: RagProviderSelectionResult = self._service.use_provider(arguments[0].lower())
        return CommandResult(success=result.success, message=result.message)

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "YES" or "NO"."""
        return "YES" if value else "NO"
