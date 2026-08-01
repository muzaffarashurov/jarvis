"""Knowledge module: CLI command surface for EP-024 Knowledge Base.

Exposes the "knowledge" command namespace (help, status, collections,
list, info, clear) as thin CommandModule handlers, following the same
pattern as MemoryModule/EmbeddingModule/RagModule/IndexModule. All
storage and business logic lives in KnowledgeManager/KnowledgeService;
this module only parses CLI arguments and formats CommandResult
objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.knowledge.knowledge_collection import CollectionStats
from src.core.knowledge.knowledge_record import DEFAULT_COLLECTION, KnowledgeRecord
from src.services.knowledge_service import KnowledgeService, KnowledgeStatus

HELP_TEXT: str = (
    "Available commands\n\n"
    "knowledge status\n"
    "knowledge collections\n"
    "knowledge list [collection]\n"
    "knowledge info <key> [collection]\n"
    "knowledge clear [collection]\n"
    "knowledge help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class KnowledgeModule:
    """Built-in "knowledge" command namespace for the Knowledge Base."""

    def __init__(self, knowledge_service: KnowledgeService) -> None:
        """Initialize the KnowledgeModule.

        Args:
            knowledge_service: The service used to read and inspect
                stored knowledge records and collections.
        """
        self._service = knowledge_service
        self._actions: dict[str, ActionHandler] = {
            "status": self._status,
            "collections": self._collections,
            "list": self._list,
            "info": self._info,
            "clear": self._clear,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "knowledge"."""
        return "knowledge"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "knowledge" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a key and collection).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "knowledge help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available knowledge commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the Knowledge Base's overall status."""
        status: KnowledgeStatus = self._service.status()
        lines = [
            "Knowledge Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Active Provider : {status.active_provider or 'none'}",
            f"Providers : {status.provider_count}",
            f"Total Records : {status.total_records}",
            f"Collections : {status.collection_count}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    def _collections(self, arguments: list[str]) -> CommandResult:
        """List every collection and its record count."""
        stats: list[CollectionStats] = self._service.collection_stats()
        if not stats:
            return CommandResult(success=True, message="Knowledge Collections\n\n(empty)")

        lines = ["Knowledge Collections"]
        for entry in stats:
            lines.append(f"{entry.name} ({entry.record_count} record(s))")
        return CommandResult(success=True, message="\n\n".join(lines))

    def _list(self, arguments: list[str]) -> CommandResult:
        """List stored records, optionally scoped to a single collection."""
        collection = arguments[0] if arguments else None
        records: list[KnowledgeRecord] = self._service.list_records(collection)
        if not records:
            return CommandResult(success=True, message="Knowledge\n\n(empty)")

        lines = ["Knowledge"]
        for record in records:
            lines.append(f"{record.collection}:{record.key}")
        return CommandResult(success=True, message="\n\n".join(lines))

    def _info(self, arguments: list[str]) -> CommandResult:
        """Show a single record's content and metadata."""
        if not arguments:
            return CommandResult(success=False, message="Usage: knowledge info <key> [collection]")

        key = arguments[0]
        collection = arguments[1] if len(arguments) > 1 else DEFAULT_COLLECTION
        record = self._service.load(key, collection)
        if record is None:
            return CommandResult(
                success=False, message=f"Record not found: '{key}' in collection '{collection}'."
            )

        lines = [
            "Knowledge Record",
            f"Key : {record.key}",
            f"Collection : {record.collection}",
            f"Content : {record.content}",
            f"Metadata : {record.metadata}",
            f"Created : {record.created_at.isoformat()}",
            f"Updated : {record.updated_at.isoformat()}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    def _clear(self, arguments: list[str]) -> CommandResult:
        """Clear a single collection, or every collection."""
        collection = arguments[0] if arguments else None
        return self._service.clear(collection)

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean status check as "OK" or "FAIL"."""
        return "OK" if value else "FAIL"
