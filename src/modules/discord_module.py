"""Discord module: CLI command surface for EP-041 Discord Integration.

Exposes the "discord" command namespace (guild, channels, channel,
member, message, help) as thin CommandModule handlers, following the
same pattern as GitHubModule (EP-039). All Discord-API logic lives in
DiscordService; this module only parses/validates CLI arguments, calls
DiscordService's existing public methods unchanged, and formats
CommandResult objects for the shell -- it never calls `requests`
itself and never reads DISCORD_TOKEN.

Catches `DiscordError` (the common base of every exception a running
operation call can raise) to format
`CommandResult(success=False, message=str(exc))`, never letting a raw
exception reach the shell, matching every other module's pattern.
`DiscordServiceError` is not caught here because it can only ever be
raised during Bootstrap construction of DiscordService, never from a
running CLI call -- if construction fails, Bootstrap never registers
this module at all (see src/bootstrap.py).

No "send", "edit", "delete", "create", "ban", "kick", "webhook",
"role", "react", or "invite" command exists -- this subsystem is
read-only by design, matching the EP-041 design's explicit scope.
DISCORD_TOKEN never flows through this module at all (it is read
directly from the environment inside DiscordService), so there is no
code path here that could leak it into a CommandResult message.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.discord.discord_error import DiscordError
from src.services.discord_service import DiscordService

HELP_TEXT: str = (
    "Available commands\n\n"
    "discord guild <guild_id>\n"
    "discord channels <guild_id>\n"
    "discord channel <channel_id>\n"
    "discord member <guild_id> <user_id>\n"
    "discord message <channel_id> <message_id>\n"
    "discord help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class DiscordModule:
    """Built-in "discord" command namespace for EP-041 Discord Integration."""

    def __init__(self, discord_service: DiscordService) -> None:
        """Initialize the DiscordModule.

        Args:
            discord_service: The service used to run read-only
                Discord operations against the Discord REST API.
        """
        self._service = discord_service
        self._actions: dict[str, ActionHandler] = {
            "guild": self._guild,
            "channels": self._channels,
            "channel": self._channel,
            "member": self._member,
            "message": self._message,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "discord"."""
        return "discord"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "discord" action.

        Args:
            action: The requested action (e.g. "guild").
            arguments: Additional arguments (e.g. a guild_id).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "discord help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available discord commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _guild(self, arguments: list[str]) -> CommandResult:
        """Handle "discord guild <guild_id>"."""
        if not arguments:
            return CommandResult(success=False, message="discord guild requires a guild_id.")
        try:
            result = self._service.get_guild(arguments[0])
        except DiscordError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=str(result.data))

    def _channels(self, arguments: list[str]) -> CommandResult:
        """Handle "discord channels <guild_id>"."""
        if not arguments:
            return CommandResult(success=False, message="discord channels requires a guild_id.")
        try:
            result = self._service.list_guild_channels(arguments[0])
        except DiscordError as exc:
            return CommandResult(success=False, message=str(exc))
        message = str(result.data) if result.data else "No channels."
        return CommandResult(success=True, message=message)

    def _channel(self, arguments: list[str]) -> CommandResult:
        """Handle "discord channel <channel_id>"."""
        if not arguments:
            return CommandResult(success=False, message="discord channel requires a channel_id.")
        try:
            result = self._service.get_channel(arguments[0])
        except DiscordError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=str(result.data))

    def _member(self, arguments: list[str]) -> CommandResult:
        """Handle "discord member <guild_id> <user_id>"."""
        if len(arguments) < 2:
            return CommandResult(
                success=False, message="discord member requires <guild_id> <user_id>."
            )
        try:
            result = self._service.get_guild_member(arguments[0], arguments[1])
        except DiscordError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=str(result.data))

    def _message(self, arguments: list[str]) -> CommandResult:
        """Handle "discord message <channel_id> <message_id>"."""
        if len(arguments) < 2:
            return CommandResult(
                success=False, message="discord message requires <channel_id> <message_id>."
            )
        try:
            result = self._service.get_message(arguments[0], arguments[1])
        except DiscordError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=str(result.data))
