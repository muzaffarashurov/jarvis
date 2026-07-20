"""Memory module: CLI command surface for EP-013 Memory & Context Manager.

Exposes the "memory" command namespace (status, doctor, get, set,
delete, clear, list, export, import, help) as thin CommandModule
handlers, following the same pattern as SchedulerModule/WorkflowModule.
All storage and business logic lives in MemoryStore/MemoryService;
this module only parses CLI arguments and formats CommandResult
objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.memory.context import MemoryEntry
from src.services.memory_service import MemoryDoctorReport, MemoryService, MemoryStatus

HELP_TEXT: str = (
    "Available commands\n\n"
    "memory status\n"
    "memory doctor\n"
    "memory get <key>\n"
    "memory set <key> <value>\n"
    "memory delete <key>\n"
    "memory clear\n"
    "memory list\n"
    "memory export [path]\n"
    "memory import [path]\n"
    "memory help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class MemoryModule:
    """Built-in "memory" command namespace for the Memory & Context Manager."""

    def __init__(self, memory_service: MemoryService) -> None:
        """Initialize the MemoryModule.

        Args:
            memory_service: The service used to read, write, and
                inspect runtime memory.
        """
        self._service = memory_service
        self._actions: dict[str, ActionHandler] = {
            "status": self._status,
            "doctor": self._doctor,
            "get": self._get,
            "set": self._set,
            "delete": self._delete,
            "clear": self._clear,
            "list": self._list,
            "export": self._export,
            "import": self._import,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "memory"."""
        return "memory"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "memory" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a key and value).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "memory help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available memory commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the memory store's overall status."""
        status: MemoryStatus = self._service.status()
        lines = [
            "Memory Status",
            f"Total entries : {status.total_entries}",
            f"Namespaces : {status.namespace_count}",
            f"Persistent entries : {status.persistent_entries}",
            f"Session entries : {status.session_entries}",
            f"Enabled : {self._mark(status.enabled)}",
            f"Persistent : {self._mark(status.persistent)}",
            f"Storage File : {status.storage_file}",
            f"Auto Save : {self._mark(status.auto_save)}",
            f"Interval : {status.auto_save_interval}s",
            f"Max Entries : {status.max_entries}",
            f"TTL : {status.default_ttl if status.default_ttl is not None else 'none'}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    def _doctor(self, arguments: list[str]) -> CommandResult:
        """Run full memory diagnostics."""
        report: MemoryDoctorReport = self._service.doctor()
        lines = [
            "Memory Doctor",
            f"Store : {self._mark(report.store_available)}",
            f"Configuration : {self._mark(report.configuration_loaded)}",
            f"Export Path : {self._mark(report.export_path_writable)}",
            f"Entries : {self._mark(report.entries_valid)}",
            f"Storage File : {self._mark(report.storage_file_valid)}",
            f"Permissions : {self._mark(report.permissions_valid)}",
            f"Auto Save : {self._mark(report.auto_save_valid)}",
            f"Persistence : {self._mark(report.persistence_valid)}",
            f"TTL : {self._mark(report.ttl_valid)}",
            f"Result : {'READY' if report.is_ready else 'FAILED'}",
        ]
        return CommandResult(success=report.is_ready, message="\n\n".join(lines))

    def _get(self, arguments: list[str]) -> CommandResult:
        """Retrieve a single value by key."""
        if not arguments:
            return CommandResult(success=False, message="Usage: memory get <key>")

        key = arguments[0]
        entry = self._service.get(key)
        if entry is None:
            return CommandResult(success=False, message=f"Key not found: '{key}'")
        return CommandResult(success=True, message=str(entry.value))

    def _set(self, arguments: list[str]) -> CommandResult:
        """Store a value under a key."""
        if len(arguments) < 2:
            return CommandResult(success=False, message="Usage: memory set <key> <value>")

        key = arguments[0]
        value = " ".join(arguments[1:])
        return self._service.set(key, value)

    def _delete(self, arguments: list[str]) -> CommandResult:
        """Delete a single key."""
        if not arguments:
            return CommandResult(success=False, message="Usage: memory delete <key>")

        return self._service.delete(arguments[0])

    def _clear(self, arguments: list[str]) -> CommandResult:
        """Clear every stored entry."""
        return self._service.clear()

    def _list(self, arguments: list[str]) -> CommandResult:
        """List all stored entries."""
        entries: list[MemoryEntry] = self._service.list_entries()
        if not entries:
            return CommandResult(success=True, message="Memory\n\n(empty)")

        lines = ["Memory"]
        for entry in entries:
            scope = "persistent" if entry.persistent else "session"
            lines.append(f"{entry.namespace}:{entry.key} = {entry.value} ({scope})")
        return CommandResult(success=True, message="\n\n".join(lines))

    def _export(self, arguments: list[str]) -> CommandResult:
        """Export persistent memory to a JSON file."""
        path = arguments[0] if arguments else None
        return self._service.export(path)

    def _import(self, arguments: list[str]) -> CommandResult:
        """Import memory from a JSON file."""
        path = arguments[0] if arguments else None
        return self._service.import_(path)

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "OK" or "FAIL"."""
        return "OK" if value else "FAIL"
