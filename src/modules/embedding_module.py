"""Embedding module: CLI command surface for EP-021 Embedding Engine.

Exposes the "embedding" command namespace (status, providers, use,
embed, dimension, help) as thin CommandModule handlers, following the
same pattern as AIModule/IndexModule. All orchestration logic lives in
EmbeddingService; this module only formats CommandResult objects for
the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.embedding_service import (
    EmbeddingProviderInfo,
    EmbeddingService,
    EmbeddingStatus,
    EmbedResult,
    ProviderSelectionResult,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "embedding help\n"
    "embedding status\n"
    "embedding providers\n"
    "embedding use <provider>\n"
    'embedding embed "<text>"\n'
    "embedding dimension"
)

ActionHandler = Callable[[list[str]], CommandResult]


class EmbeddingModule:
    """Built-in "embedding" command namespace for the Embedding Engine."""

    def __init__(self, embedding_service: EmbeddingService) -> None:
        """Initialize the EmbeddingModule.

        Args:
            embedding_service: The service used to inspect and control
                the Embedding subsystem and its registered providers.
        """
        self._service = embedding_service
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "status": self._status,
            "providers": self._providers,
            "use": self._use,
            "embed": self._embed,
            "dimension": self._dimension,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "embedding"."""
        return "embedding"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute an "embedding" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a provider name).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "embedding help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available embedding commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the Embedding subsystem's overall status."""
        status: EmbeddingStatus = self._service.status()
        lines = [
            "Embedding Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Current provider : {status.current_provider or 'none'}",
            f"Registered providers : {status.registered_provider_count}",
            f"Dimension : {status.dimension if status.dimension is not None else 'n/a'}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _providers(self, arguments: list[str]) -> CommandResult:
        """List every registered embedding provider and its diagnostic flags."""
        providers: list[EmbeddingProviderInfo] = self._service.list_providers()
        if not providers:
            return CommandResult(success=True, message="No embedding providers registered.")

        header = f"{'Provider':<10}{'Model':<24}{'Dimension':<11}{'Available':<11}{'Current':<8}"
        lines = ["Embedding Providers", "", header]
        for provider in providers:
            lines.append(
                f"{provider.name:<10}"
                f"{provider.model:<24}"
                f"{provider.dimension:<11}"
                f"{self._mark(provider.available):<11}"
                f"{self._mark(provider.is_current):<8}"
            )
        return CommandResult(success=True, message="\n".join(lines))

    def _use(self, arguments: list[str]) -> CommandResult:
        """Select an embedding provider as the currently active provider.

        Args:
            arguments: `[provider_name]`.

        Returns:
            A CommandResult reflecting whether the provider was selected.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: embedding use <provider>")

        result: ProviderSelectionResult = self._service.use_provider(arguments[0].lower())
        return CommandResult(success=result.success, message=result.message)

    def _embed(self, arguments: list[str]) -> CommandResult:
        """Request a single embedding vector for the given text.

        Args:
            arguments: The text words (joined with spaces).

        Returns:
            A CommandResult with the embedding vector's summary, or a
            user-friendly error message.
        """
        if not arguments:
            return CommandResult(success=False, message='Usage: embedding embed "<text>"')

        text = " ".join(arguments)
        result: EmbedResult = self._service.embed(text)
        if not result.success:
            return CommandResult(success=False, message=result.error)

        lines = [
            f"Provider : {result.provider}",
            f"Model : {result.model}",
            f"Dimension : {result.dimension}",
            f"Vector (first 5) : {result.vector[:5]}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _dimension(self, arguments: list[str]) -> CommandResult:
        """Display the currently active provider's embedding dimension."""
        success, dimension, error = self._service.dimension()
        if not success:
            return CommandResult(success=False, message=error)
        return CommandResult(success=True, message=f"Dimension: {dimension}")

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "YES" or "NO"."""
        return "YES" if value else "NO"
