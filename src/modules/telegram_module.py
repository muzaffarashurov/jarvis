"""Telegram module: CLI command surface for EP-012 Telegram Gateway.

Exposes the "telegram" command namespace (start, stop, status, doctor,
send, help) as thin CommandModule handlers, following the same
pattern as SchedulerModule/WorkflowModule. All orchestration logic
lives in TelegramService; this module only formats CommandResult
objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.services.telegram_service import (
    TelegramDoctorReport,
    TelegramService,
    TelegramStatus,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "telegram start\n"
    "telegram stop\n"
    "telegram status\n"
    "telegram doctor\n"
    "telegram send <chat_id> <message>\n"
    "telegram help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class TelegramModule:
    """Built-in "telegram" command namespace for the Telegram Gateway."""

    def __init__(self, telegram_service: TelegramService) -> None:
        """Initialize the TelegramModule.

        Args:
            telegram_service: The service used to start, stop, inspect,
                and send messages through the Telegram Gateway.
        """
        self._service = telegram_service
        self._actions: dict[str, ActionHandler] = {
            "start": self._start,
            "stop": self._stop,
            "status": self._status,
            "doctor": self._doctor,
            "send": self._send,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "telegram"."""
        return "telegram"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "telegram" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a chat id and message).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "telegram help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available telegram commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _start(self, arguments: list[str]) -> CommandResult:
        """Connect to the Telegram Bot API and start receiving messages."""
        return self._service.start()

    def _stop(self, arguments: list[str]) -> CommandResult:
        """Stop receiving messages and disconnect from the Telegram Bot API."""
        return self._service.stop()

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the Telegram gateway's overall status."""
        status: TelegramStatus = self._service.status()
        lines = [
            "Telegram Status",
            f"Running : {'YES' if status.running else 'NO'}",
            f"Connected : {'YES' if status.connected else 'NO'}",
            f"Allowed chat ids : {status.allowed_chat_count}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    def _doctor(self, arguments: list[str]) -> CommandResult:
        """Run full Telegram gateway diagnostics."""
        report: TelegramDoctorReport = self._service.doctor()
        lines = [
            "Telegram Doctor",
            f"Configuration : {self._mark(report.configuration_loaded)}",
            f"Token : {self._mark(report.token_configured)}",
            f"Connection : {self._mark(report.connection_available)}",
            f"Router : {self._mark(report.router_available)}",
            f"Command Router : {self._mark(report.command_router_available)}",
            f"Result : {'READY' if report.is_ready else 'FAILED'}",
        ]
        return CommandResult(success=report.is_ready, message="\n\n".join(lines))

    def _send(self, arguments: list[str]) -> CommandResult:
        """Send a message to a Telegram chat.

        Args:
            arguments: `[chat_id, *message_words]`.

        Returns:
            A CommandResult reflecting whether the message was sent.
        """
        if len(arguments) < 2:
            return CommandResult(success=False, message="Usage: telegram send <chat_id> <message>")

        try:
            chat_id = int(arguments[0])
        except ValueError:
            return CommandResult(success=False, message="Invalid chat id.")

        text = " ".join(arguments[1:])
        return self._service.send_message(chat_id, text)

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "OK" or "FAIL"."""
        return "OK" if value else "FAIL"
