"""Email module: CLI command surface for EP-042 Email Integration.

Exposes the "email" command namespace (folders, list, message, search,
help) as thin CommandModule handlers, following the same pattern as
DiscordModule (EP-041). All IMAP protocol logic lives in EmailService;
this module only parses/validates CLI arguments, calls EmailService's
existing public methods unchanged, and formats CommandResult objects
for the shell -- it never calls `imaplib` itself and never reads any
email credential or environment variable.

Catches `EmailError` (the common base of every exception a running
operation call can raise) to format
`CommandResult(success=False, message=str(exc))`, never letting a raw
exception (or a credential, since it never handles one) reach the
shell, matching every other module's pattern. `EmailServiceError` is
not caught here because it can only ever be raised during Bootstrap
construction of EmailService, never from a running CLI call -- if
construction fails, Bootstrap never registers this module at all (see
src/bootstrap.py).

No "send", "reply", "forward", "delete", "move", or "flag" command
exists -- this subsystem is read-only by design, matching the EP-042
design's explicit scope.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.email.email_error import EmailError
from src.services.email_service import EmailService

HELP_TEXT: str = (
    "Available commands\n\n"
    "email folders\n"
    "email list [folder] [limit]\n"
    "email message <folder> <uid>\n"
    "email search <folder> <criteria...>\n"
    "email help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class EmailModule:
    """Built-in "email" command namespace for EP-042 Email Integration."""

    def __init__(self, email_service: EmailService) -> None:
        """Initialize the EmailModule.

        Args:
            email_service: The service used to run read-only Email
                operations against the configured IMAP server.
        """
        self._service = email_service
        self._actions: dict[str, ActionHandler] = {
            "folders": self._folders,
            "list": self._list,
            "message": self._message,
            "search": self._search,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "email"."""
        return "email"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute an "email" action.

        Args:
            action: The requested action (e.g. "folders").
            arguments: Additional arguments (e.g. a folder name).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "email help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available email commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _folders(self, arguments: list[str]) -> CommandResult:
        """Handle "email folders"."""
        try:
            result = self._service.list_folders()
        except EmailError as exc:
            return CommandResult(success=False, message=str(exc))
        message = str(result.data) if result.data else "No folders."
        return CommandResult(success=True, message=message)

    def _list(self, arguments: list[str]) -> CommandResult:
        """Handle "email list [folder] [limit]"."""
        folder = arguments[0] if len(arguments) >= 1 else None
        limit: int | None = None
        if len(arguments) >= 2:
            try:
                limit = int(arguments[1])
            except ValueError:
                return CommandResult(success=False, message="email list: limit must be an integer.")

        try:
            result = self._service.list_messages(folder=folder, limit=limit)
        except EmailError as exc:
            return CommandResult(success=False, message=str(exc))
        message = str(result.data) if result.data else "No messages."
        return CommandResult(success=True, message=message)

    def _message(self, arguments: list[str]) -> CommandResult:
        """Handle "email message <folder> <uid>"."""
        if len(arguments) < 2:
            return CommandResult(
                success=False, message="email message requires <folder> <uid>."
            )
        try:
            result = self._service.get_message(arguments[0], arguments[1])
        except EmailError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=str(result.data))

    def _search(self, arguments: list[str]) -> CommandResult:
        """Handle "email search <folder> <criteria...>"."""
        if len(arguments) < 2:
            return CommandResult(
                success=False, message="email search requires <folder> <criteria...>."
            )
        folder = arguments[0]
        criteria = " ".join(arguments[1:])
        try:
            result = self._service.search_messages(folder, criteria)
        except EmailError as exc:
            return CommandResult(success=False, message=str(exc))
        message = str(result.data) if result.data else "No matching messages."
        return CommandResult(success=True, message=message)
