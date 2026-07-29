"""Index module: CLI command surface for EP-019 Project Index Engine.

Exposes the "index" command namespace (build, rebuild, clear, status,
help) as thin CommandModule handlers, following the same pattern as
MemoryModule/SchedulerModule (see src/modules/memory_module.py). All
indexing logic lives in ProjectIndexer (EP-019, untouched) and all
business logic lives in IndexService; this module only parses CLI
arguments and formats CommandResult objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.index_service import IndexService, IndexStatus

HELP_TEXT: str = (
    "Available commands\n\n"
    "index build\n"
    "index rebuild\n"
    "index clear\n"
    "index status\n"
    "index help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class IndexModule:
    """Built-in "index" command namespace for the Project Index Engine."""

    def __init__(self, index_service: IndexService) -> None:
        """Initialize the IndexModule.

        Args:
            index_service: The service used to build, rebuild, clear
                and inspect the project index.
        """
        self._service = index_service
        self._actions: dict[str, ActionHandler] = {
            "build": self._build,
            "rebuild": self._rebuild,
            "clear": self._clear,
            "status": self._status,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "index"."""
        return "index"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute an "index" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (unused by every current
                "index" action).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "index help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available index commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _build(self, arguments: list[str]) -> CommandResult:
        """Build a fresh index from the current manifest and documents."""
        return self._service.build()

    def _rebuild(self, arguments: list[str]) -> CommandResult:
        """Force a full rebuild, ignoring cached manifest/document content."""
        return self._service.rebuild()

    def _clear(self, arguments: list[str]) -> CommandResult:
        """Discard the current in-memory index and any persisted copy."""
        return self._service.clear()

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the project index's overall status."""
        status: IndexStatus = self._service.status()
        lines = [
            "Index Status",
            f"Project Name : {status.project_name or '(none)'}",
            f"Indexed Documents : {status.document_count}",
            f"Indexed Chunks : {status.chunk_count}",
            f"Storage Backend : {status.storage_backend}",
            f"Index Version : {status.index_version or '(none)'}",
            "Last Build Time : "
            + (status.last_build_time.isoformat() if status.last_build_time else "never"),
            f"Status : {'Ready' if status.built else 'Not Built'}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))
