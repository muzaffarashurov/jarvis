"""Semantic module: CLI command surface for EP-026 Semantic Search.

Exposes the "semantic" command namespace (help, status, providers,
use, search, threshold) as thin CommandModule handlers, following the
same pattern as EmbeddingModule/KnowledgeModule. All orchestration
logic lives in SemanticService; this module only formats CommandResult
objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.semantic_service import (
    ProviderSelectionResult,
    SemanticProviderInfo,
    SemanticSearchOutcome,
    SemanticService,
    SemanticStatus,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "semantic help\n"
    "semantic status\n"
    "semantic providers\n"
    "semantic use <provider>\n"
    'semantic search "<query>"\n'
    "semantic threshold"
)

ActionHandler = Callable[[list[str]], CommandResult]


class SemanticModule:
    """Built-in "semantic" command namespace for Semantic Search."""

    def __init__(self, semantic_service: SemanticService) -> None:
        """Initialize the SemanticModule.

        Args:
            semantic_service: The service used to inspect and control
                the Semantic Search subsystem and its registered
                providers.
        """
        self._service = semantic_service
        self._actions: dict[str, ActionHandler] = {
            "help": self._help,
            "status": self._status,
            "providers": self._providers,
            "use": self._use,
            "search": self._search,
            "threshold": self._threshold,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "semantic"."""
        return "semantic"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "semantic" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a provider name).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "semantic help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available semantic commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the Semantic Search subsystem's overall status."""
        status: SemanticStatus = self._service.status()
        lines = [
            "Semantic Search Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Current provider : {status.current_provider or 'none'}",
            f"Registered providers : {status.registered_provider_count}",
            f"Top K : {status.top_k}",
            f"Similarity threshold : {status.similarity_threshold}",
        ]
        if status.embedding_provider_warning:
            lines.append(f"Warning : {status.embedding_provider_warning}")
        return CommandResult(success=True, message="\n".join(lines))

    def _providers(self, arguments: list[str]) -> CommandResult:
        """List every registered semantic provider and its diagnostic flags."""
        providers: list[SemanticProviderInfo] = self._service.list_providers()
        if not providers:
            return CommandResult(success=True, message="No semantic providers registered.")

        header = f"{'Provider':<12}{'Available':<11}{'Current':<8}"
        lines = ["Semantic Providers", "", header]
        for provider in providers:
            lines.append(
                f"{provider.name:<12}"
                f"{self._mark(provider.available):<11}"
                f"{self._mark(provider.is_current):<8}"
            )
        return CommandResult(success=True, message="\n".join(lines))

    def _use(self, arguments: list[str]) -> CommandResult:
        """Select a semantic provider as the currently active provider.

        Args:
            arguments: `[provider_name]`.

        Returns:
            A CommandResult reflecting whether the provider was selected.
        """
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: semantic use <provider>")

        result: ProviderSelectionResult = self._service.use_provider(arguments[0].lower())
        return CommandResult(success=result.success, message=result.message)

    def _search(self, arguments: list[str]) -> CommandResult:
        """Perform a semantic similarity search for the given query.

        Args:
            arguments: The query words (joined with spaces).

        Returns:
            A CommandResult listing the ranked matches, or a
            user-friendly error message.
        """
        if not arguments:
            return CommandResult(success=False, message='Usage: semantic search "<query>"')

        query = " ".join(arguments)
        outcome: SemanticSearchOutcome = self._service.search(query)
        if not outcome.success:
            return CommandResult(success=False, message=outcome.error)

        if not outcome.results:
            return CommandResult(success=True, message=f'No matches found for "{query}".')

        lines = [f'Semantic Search Results for "{query}"', ""]
        for index, result in enumerate(outcome.results, start=1):
            lines.append(
                f"{index}. [{result.source}] {result.identifier} "
                f"(score: {result.score:.4f})"
            )
            lines.append(f"   {result.text[:120]}")
        return CommandResult(success=True, message="\n".join(lines))

    def _threshold(self, arguments: list[str]) -> CommandResult:
        """Display the current default similarity threshold."""
        return CommandResult(
            success=True, message=f"Similarity threshold: {self._service.threshold()}"
        )

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "YES" or "NO"."""
        return "YES" if value else "NO"
