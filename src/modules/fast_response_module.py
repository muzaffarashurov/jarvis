"""Fast Response Board module: CLI command surface for EP-006.

Exposes the "frb" command namespace (status, open, backup, validate,
info, doctor, help) as thin CommandModule handlers, following the same
pattern as SystemModule and InvoiceModule. All business logic --
resolving configuration, checking the workbook, opening it, and
creating backups -- lives in FastResponseService; this module only
formats CommandResult objects for the shell.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from src.core.command_router import CommandResult
from src.services.fast_response_service import (
    DoctorReport,
    FastResponseService,
    ValidationResult,
    WorkbookInfo,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "frb status\n"
    "frb open\n"
    "frb backup\n"
    "frb validate\n"
    "frb info\n"
    "frb doctor\n"
    "frb help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class FastResponseModule:
    """Built-in "frb" command namespace for the Fast Response Board."""

    def __init__(self, fast_response_service: FastResponseService) -> None:
        """Initialize the FastResponseModule.

        Args:
            fast_response_service: The service used to resolve, check,
                open, and back up the Fast Response Board workbook.
        """
        self._service = fast_response_service
        self._actions: dict[str, ActionHandler] = {
            "status": self._status,
            "open": self._open,
            "backup": self._backup,
            "validate": self._validate,
            "info": self._info,
            "doctor": self._doctor,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "frb"."""
        return "frb"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute an "frb" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments; unused by current actions.

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "frb help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available frb commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Report workbook path, worksheet, existence, and readiness."""
        info = self._service.get_info()
        lines = [
            "Fast Response Board",
            f"Workbook : {info.workbook_path if info.workbook_path else '(not configured)'}",
            f"Worksheet : {info.worksheet if info.worksheet else '(not configured)'}",
            f"Exists : {'Yes' if info.exists else 'No'}",
            f"Last modified : {self._format_datetime(info.last_modified)}",
            f"Status : {'READY' if info.is_ready else 'ERROR'}",
        ]
        if info.error_message:
            lines.append(f"Reason : {info.error_message}")
        return CommandResult(success=True, message="\n\n".join(lines))

    def _open(self, arguments: list[str]) -> CommandResult:
        """Open the workbook with the operating system's default application."""
        return self._service.open_workbook()

    def _backup(self, arguments: list[str]) -> CommandResult:
        """Create a timestamped backup of the workbook."""
        return self._service.create_backup()

    def _validate(self, arguments: list[str]) -> CommandResult:
        """Run workbook/worksheet/backup-folder validation checks."""
        result: ValidationResult = self._service.validate()
        lines = [
            "Fast Response Board Validation",
            f"Workbook exists : {self._mark(result.workbook_exists)}",
            f"Worksheet exists : {self._mark(result.worksheet_exists)}",
            f"Workbook readable : {self._mark(result.workbook_readable)}",
            f"Backup folder exists : {self._mark(result.backup_folder_exists)}",
            f"Result : {'VALID' if result.is_valid else 'INVALID'}",
        ]
        return CommandResult(success=result.is_valid, message="\n\n".join(lines))

    def _info(self, arguments: list[str]) -> CommandResult:
        """Display workbook, worksheet, file size, last modified, and backup location."""
        info: WorkbookInfo = self._service.get_info()
        pairs = (
            ("Workbook", info.workbook_path.name if info.workbook_path else "(not configured)"),
            ("Worksheet", info.worksheet if info.worksheet else "(not configured)"),
            ("File size", self._format_size(info.size_bytes)),
            ("Last modified", self._format_datetime(info.last_modified)),
            (
                "Backup location",
                str(info.backup_folder) if info.backup_folder else "(not configured)",
            ),
        )
        message = "\n\n".join(f"{label}\n\n{value}" for label, value in pairs)
        return CommandResult(success=True, message=message)

    def _doctor(self, arguments: list[str]) -> CommandResult:
        """Run full diagnostics and report READY or FAILED."""
        report: DoctorReport = self._service.run_doctor()
        lines = [
            "Fast Response Board Doctor",
            f"Configuration loaded : {self._mark(report.configuration_loaded)}",
            f"Workbook exists : {self._mark(report.workbook_exists)}",
            f"Worksheet configured : {self._mark(report.worksheet_configured)}",
            f"Backup directory exists : {self._mark(report.backup_directory_exists)}",
            f"Permissions OK : {self._mark(report.permissions_ok)}",
            f"Result : {'READY' if report.is_ready else 'FAILED'}",
        ]
        return CommandResult(success=report.is_ready, message="\n\n".join(lines))

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "OK" or "FAIL"."""
        return "OK" if value else "FAIL"

    @staticmethod
    def _format_datetime(value: datetime | None) -> str:
        """Format a UTC datetime as a local-time string, or "-" if None."""
        if value is None:
            return "-"
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _format_size(size_bytes: int | None) -> str:
        """Format a byte count as a human-readable size, or "-" if None."""
        if size_bytes is None:
            return "-"
        size = float(size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
