"""Conversation module: CLI command surface for EP-016 Conversation Engine.

Exposes the "conversation" command namespace (current, list, create,
use, rename, delete, clear, history, export, import, stats, help) as
thin CommandModule handlers, following the same pattern as
MemoryModule/AIModule. All conversation storage and lifecycle logic
lives in ConversationManager; this module only parses CLI arguments,
translates ConversationManager's exceptions into CommandResult, and
formats output for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.ai.conversation import Conversation
from src.core.ai.conversation_manager import (
    ConversationAlreadyExistsError,
    ConversationManager,
    ConversationManagerError,
    ConversationNotFoundError,
)
from src.core.command_router import CommandResult

HELP_TEXT: str = (
    "Available commands\n\n"
    "conversation current\n"
    "conversation list\n"
    "conversation create <name>\n"
    "conversation use <name>\n"
    "conversation rename <old> <new>\n"
    "conversation delete <name>\n"
    "conversation clear\n"
    "conversation history [name]\n"
    "conversation export [name] [path]\n"
    "conversation import [path]\n"
    "conversation stats [name]\n"
    "conversation help"
)

_DISABLED_MESSAGE: str = (
    "Conversation Engine disabled. Enable 'conversation.enabled' in config.yaml."
)

ActionHandler = Callable[[list[str]], CommandResult]


class ConversationModule:
    """Built-in "conversation" command namespace for the Conversation Engine."""

    def __init__(self, conversation_manager: ConversationManager) -> None:
        """Initialize the ConversationModule.

        Args:
            conversation_manager: The manager used to create, inspect,
                and persist chat sessions.
        """
        self._manager = conversation_manager
        self._actions: dict[str, ActionHandler] = {
            "current": self._current,
            "list": self._list,
            "create": self._create,
            "use": self._use,
            "rename": self._rename,
            "delete": self._delete,
            "clear": self._clear,
            "history": self._history,
            "export": self._export,
            "import": self._import,
            "stats": self._stats,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "conversation"."""
        return "conversation"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "conversation" action.

        Args:
            action: The requested action (e.g. "list").
            arguments: Additional arguments (e.g. a conversation name).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "conversation help" for available commands.'
            return CommandResult(success=False, message=message)

        if action != "help" and not self._manager.is_enabled():
            return CommandResult(success=False, message=_DISABLED_MESSAGE)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available conversation commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _current(self, arguments: list[str]) -> CommandResult:
        """Display the currently selected conversation."""
        conversation = self._manager.current()
        return CommandResult(
            success=True,
            message=f"Current conversation: '{conversation.title}' ({conversation.size()} messages)",
        )

    def _list(self, arguments: list[str]) -> CommandResult:
        """List every registered conversation."""
        conversations = self._manager.list()
        if not conversations:
            return CommandResult(success=True, message="Conversations\n\n(none)")

        lines = ["Conversations", ""]
        for conversation in conversations:
            lines.append(
                f"{conversation.title:<24} messages={conversation.size():<5} "
                f"updated={conversation.updated_at.isoformat()}"
            )
        return CommandResult(success=True, message="\n".join(lines))

    def _create(self, arguments: list[str]) -> CommandResult:
        """Create a new, empty conversation."""
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: conversation create <name>")

        try:
            conversation = self._manager.create(arguments[0])
        except ConversationManagerError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Conversation created: '{conversation.title}'.")

    def _use(self, arguments: list[str]) -> CommandResult:
        """Select a conversation as the currently active conversation."""
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: conversation use <name>")

        try:
            self._manager.set_current(arguments[0])
        except ConversationNotFoundError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Current conversation set to '{arguments[0]}'.")

    def _rename(self, arguments: list[str]) -> CommandResult:
        """Rename an existing conversation."""
        if len(arguments) != 2:
            return CommandResult(success=False, message="Usage: conversation rename <old> <new>")

        try:
            self._manager.rename(arguments[0], arguments[1])
        except (ConversationNotFoundError, ConversationAlreadyExistsError) as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(
            success=True, message=f"Conversation renamed: '{arguments[0]}' -> '{arguments[1]}'."
        )

    def _delete(self, arguments: list[str]) -> CommandResult:
        """Delete a conversation."""
        if len(arguments) != 1:
            return CommandResult(success=False, message="Usage: conversation delete <name>")

        removed = self._manager.delete(arguments[0])
        if not removed:
            return CommandResult(success=False, message=f"Unknown conversation: '{arguments[0]}'.")
        return CommandResult(success=True, message=f"Conversation deleted: '{arguments[0]}'.")

    def _clear(self, arguments: list[str]) -> CommandResult:
        """Clear every message from the current (or named) conversation."""
        name = arguments[0] if arguments else None
        try:
            count = self._manager.clear(name)
        except ConversationNotFoundError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Cleared {count} messages.")

    def _history(self, arguments: list[str]) -> CommandResult:
        """Display every message in the current (or named) conversation."""
        conversation = self._resolve(arguments)
        if conversation is None:
            return CommandResult(success=False, message=f"Unknown conversation: '{arguments[0]}'.")

        messages = conversation.messages()
        if not messages:
            return CommandResult(success=True, message=f"'{conversation.title}'\n\n(empty)")

        lines = [f"'{conversation.title}'", ""]
        for message in messages:
            lines.append(f"[{message.role.value}] {message.content}")
        return CommandResult(success=True, message="\n".join(lines))

    def _export(self, arguments: list[str]) -> CommandResult:
        """Export a conversation to a JSON file."""
        name = arguments[0] if len(arguments) >= 1 else None
        path = arguments[1] if len(arguments) >= 2 else None
        try:
            destination = self._manager.export(name=name, path=path)
        except ConversationNotFoundError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Exported to '{destination}'.")

    def _import(self, arguments: list[str]) -> CommandResult:
        """Import a conversation from a JSON file."""
        path = arguments[0] if arguments else None
        try:
            conversation = self._manager.import_(path)
        except (FileNotFoundError, ConversationManagerError) as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Imported conversation: '{conversation.title}'.")

    def _stats(self, arguments: list[str]) -> CommandResult:
        """Display statistics for the current (or named) conversation."""
        conversation = self._resolve(arguments)
        if conversation is None:
            return CommandResult(success=False, message=f"Unknown conversation: '{arguments[0]}'.")

        lines = [
            "Conversation Stats",
            f"Conversation ID : {conversation.conversation_id}",
            f"Message count : {conversation.size()}",
            f"Created : {conversation.created_at.isoformat()}",
            f"Updated : {conversation.updated_at.isoformat()}",
            f"Estimated tokens (approx.) : {self._estimate_tokens(conversation)}",
        ]
        return CommandResult(success=True, message="\n".join(lines))

    def _resolve(self, arguments: list[str]) -> Conversation | None:
        """Resolve `arguments[0]` to a Conversation, defaulting to the current one."""
        if arguments:
            return self._manager.get(arguments[0])
        return self._manager.current()

    @staticmethod
    def _estimate_tokens(conversation: Conversation) -> int:
        """Approximate the token count of every message (~4 characters per token)."""
        total_chars = sum(len(message.content) for message in conversation.messages())
        return max(total_chars // 4, 0)
