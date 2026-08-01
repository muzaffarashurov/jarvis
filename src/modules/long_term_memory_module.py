"""Long-term memory module: CLI command surface for EP-025 Long-Term Memory.

Exposes the "ltm" command namespace (help, status, list, info, archive,
clear, statistics) as thin CommandModule handlers, following the same
pattern as MemoryModule/KnowledgeModule/EmbeddingModule/RagModule/
IndexModule. All storage and business logic lives in
LongTermMemoryManager/LongTermMemoryService; this module only parses
CLI arguments and formats CommandResult objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.long_term_memory.long_term_provider import LongTermStats
from src.core.long_term_memory.long_term_record import LongTermRecord
from src.services.long_term_memory_service import LongTermMemoryService, LongTermMemoryStatus

HELP_TEXT: str = (
    "Available commands\n\n"
    "ltm status\n"
    "ltm list [status]\n"
    "ltm info <id>\n"
    "ltm archive <id>\n"
    "ltm clear\n"
    "ltm statistics\n"
    "ltm help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class LongTermMemoryModule:
    """Built-in "ltm" command namespace for Long-Term Memory."""

    def __init__(self, long_term_memory_service: LongTermMemoryService) -> None:
        """Initialize the LongTermMemoryModule.

        Args:
            long_term_memory_service: The service used to inspect and
                manage stored long-term memories.
        """
        self._service = long_term_memory_service
        self._actions: dict[str, ActionHandler] = {
            "status": self._status,
            "list": self._list,
            "info": self._info,
            "archive": self._archive,
            "clear": self._clear,
            "statistics": self._statistics,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "ltm"."""
        return "ltm"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute an "ltm" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a memory id).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "ltm help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available ltm commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display Long-Term Memory's overall status."""
        status: LongTermMemoryStatus = self._service.status()
        lines = [
            "Long-Term Memory Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Active Provider : {status.active_provider or 'none'}",
            f"Providers : {status.provider_count}",
            f"Total Memories : {status.total}",
            f"Active : {status.active}",
            f"Archived : {status.archived}",
            f"Memory Manager Integration : {self._mark(status.memory_manager_integrated)}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    def _list(self, arguments: list[str]) -> CommandResult:
        """List stored memories, optionally filtered by status ("active"/"archived")."""
        status_filter = arguments[0] if arguments else None
        records: list[LongTermRecord] = self._service.list_memories(status_filter)
        if not records:
            return CommandResult(success=True, message="Long-Term Memory\n\n(empty)")

        lines = ["Long-Term Memory"]
        for record in records:
            lines.append(f"{record.id} ({record.status})")
        return CommandResult(success=True, message="\n\n".join(lines))

    def _info(self, arguments: list[str]) -> CommandResult:
        """Show a single memory's content, metadata and lifecycle status."""
        if not arguments:
            return CommandResult(success=False, message="Usage: ltm info <id>")

        memory_id = arguments[0]
        record = self._service.get(memory_id)
        if record is None:
            return CommandResult(success=False, message=f"Memory not found: '{memory_id}'.")

        lines = [
            "Long-Term Memory Record",
            f"ID : {record.id}",
            f"Status : {record.status}",
            f"Content : {record.content}",
            f"Metadata : {record.metadata}",
            f"Created : {record.created_at.isoformat()}",
            f"Updated : {record.updated_at.isoformat()}",
            f"Archived : {record.archived_at.isoformat() if record.archived_at else 'never'}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    def _archive(self, arguments: list[str]) -> CommandResult:
        """Archive a single memory by id."""
        if not arguments:
            return CommandResult(success=False, message="Usage: ltm archive <id>")
        return self._service.archive(arguments[0])

    def _clear(self, arguments: list[str]) -> CommandResult:
        """Permanently delete every long-term memory."""
        return self._service.clear()

    def _statistics(self, arguments: list[str]) -> CommandResult:
        """Show aggregate active/archived/total statistics."""
        stats: LongTermStats = self._service.stats()
        lines = [
            "Long-Term Memory Statistics",
            f"Total : {stats.total}",
            f"Active : {stats.active}",
            f"Archived : {stats.archived}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean status check as "OK" or "FAIL"."""
        return "OK" if value else "FAIL"
