"""Business logic that coordinates the Telegram Gateway (EP-012).

TelegramService implements no business logic of its own and never
executes CLI commands directly. Per EP-012's architecture, it depends
only on:

    TelegramModule -> TelegramService -> TelegramRouter -> CommandRouter
                                       -> TelegramClient -> Telegram Bot API

In addition to the thin CLI-facing wrappers (start/stop/status/doctor/
send_message), TelegramService owns the background polling loop that
makes message reception automatic, driven by
'telegram.polling_interval' and started automatically at construction
when 'telegram.enabled' and 'telegram.auto_start' are true (see
config/config.yaml). If 'telegram.token' is missing or blank, this
service starts with no TelegramClient at all and every action reports
"Telegram is not configured." -- the rest of the application starts
and runs normally regardless (see EP-012's Testing requirement).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.telegram.telegram_client import TelegramClient, TelegramClientError
from src.core.telegram.telegram_router import TelegramRouter

__all__ = ["TelegramDoctorReport", "TelegramService", "TelegramStatus"]


@dataclass(frozen=True)
class TelegramStatus:
    """Result of `telegram status`."""

    running: bool
    connected: bool
    allowed_chat_count: int


@dataclass(frozen=True)
class TelegramDoctorReport:
    """Result of `telegram doctor`.

    Attributes:
        configuration_loaded: Whether 'telegram.enabled' resolves to a
            boolean in configuration.
        token_configured: Whether 'telegram.token' is a non-blank string.
        connection_available: Whether the underlying TelegramClient is
            currently connected to the Telegram Bot API.
        router_available: Whether the TelegramRouter dependency is present.
        command_router_available: Whether TelegramRouter's own
            CommandRouter dependency is present.
    """

    configuration_loaded: bool
    token_configured: bool
    connection_available: bool
    router_available: bool
    command_router_available: bool

    @property
    def is_ready(self) -> bool:
        """Return True only if every diagnostic check passed."""
        return (
            self.configuration_loaded
            and self.token_configured
            and self.connection_available
            and self.router_available
            and self.command_router_available
        )


class TelegramService:
    """Coordinates the Telegram gateway and owns its automatic polling loop.

    Depends only on TelegramClient (Bot API access), TelegramRouter
    (dispatch to the existing CommandRouter), and Config (its own
    'telegram.*' settings), matching EP-012's architecture. Implements
    no business logic of its own.
    """

    def __init__(
        self, config: Config, client: TelegramClient | None, router: TelegramRouter
    ) -> None:
        """Initialize the TelegramService.

        Args:
            config: Loaded application configuration, used to resolve
                'telegram.enabled', 'telegram.auto_start', and
                'telegram.polling_interval'.
            client: The TelegramClient used to connect, poll, and send
                messages, or None if 'telegram.token' is not configured.
            router: The TelegramRouter used to authorize and dispatch
                incoming messages to the existing CommandRouter.
        """
        self._config = config
        self._client = client
        self._router = router
        self._poll_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lifecycle_lock = threading.Lock()

        if bool(self._config.get("telegram.enabled", False)) and bool(
            self._config.get("telegram.auto_start", False)
        ):
            start_result = self.start()
            if not start_result.success:
                logger.error(f"Telegram auto-start skipped: {start_result.message}")

    # ---------- Public API ----------

    def start(self) -> CommandResult:
        """Connect to the Telegram Bot API and start the polling loop."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        if self._client is None:
            message = "Telegram is not configured: missing 'telegram.token'."
            logger.error(f"Telegram start failed: {message}")
            return CommandResult(success=False, message=message)

        with self._lifecycle_lock:
            if self._poll_thread is not None:
                return CommandResult(success=True, message="Telegram already started.")

            try:
                self._client.connect()
            except TelegramClientError as exc:
                logger.error(f"Telegram start failed: {exc}")
                return CommandResult(success=False, message=str(exc))

            self._stop_event.clear()
            self._poll_thread = threading.Thread(
                target=self._poll_loop, name="telegram-poll", daemon=True
            )
            self._poll_thread.start()

        logger.info("Telegram started.")
        return CommandResult(success=True, message="Telegram started.")

    def stop(self) -> CommandResult:
        """Stop the polling loop and disconnect from the Telegram Bot API."""
        with self._lifecycle_lock:
            if self._poll_thread is None:
                return CommandResult(success=True, message="Telegram already stopped.")
            self._stop_event.set()
            thread = self._poll_thread
            self._poll_thread = None

        thread.join(timeout=5)
        if self._client is not None:
            self._client.disconnect()
        logger.info("Telegram stopped.")
        return CommandResult(success=True, message="Telegram stopped.")

    def status(self) -> TelegramStatus:
        """Return the `telegram status` snapshot."""
        allowed_chat_ids = self._config.get("telegram.allowed_chat_ids", [])
        allowed_chat_count = (
            len(allowed_chat_ids) if isinstance(allowed_chat_ids, list) else 0
        )
        return TelegramStatus(
            running=self._is_poll_loop_running(),
            connected=self._client is not None and self._client.is_connected,
            allowed_chat_count=allowed_chat_count,
        )

    def doctor(self) -> TelegramDoctorReport:
        """Run the `telegram doctor` diagnostic checks."""
        token = self._config.get("telegram.token")
        return TelegramDoctorReport(
            configuration_loaded=isinstance(self._config.get("telegram.enabled"), bool),
            token_configured=isinstance(token, str) and bool(token.strip()),
            connection_available=self._client is not None and self._client.is_connected,
            router_available=self._router is not None,
            command_router_available=(
                self._router is not None and self._router.command_router_available
            ),
        )

    def send_message(self, chat_id: int, text: str) -> CommandResult:
        """Send a message to a Telegram chat via the TelegramClient.

        Args:
            chat_id: The destination chat's Telegram id.
            text: The message text to send.

        Returns:
            A CommandResult describing whether the message was sent.
        """
        if self._client is None:
            return CommandResult(
                success=False, message="Telegram is not configured: missing 'telegram.token'."
            )

        try:
            self._client.send_message(chat_id, text)
        except TelegramClientError as exc:
            logger.error(f"Telegram send failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message="Message sent.")

    # ---------- Internal helpers ----------

    def _ensure_enabled(self) -> CommandResult | None:
        """Return a "Telegram disabled" failure if 'telegram.enabled' is False.

        Returns:
            A failing CommandResult if Telegram is disabled, otherwise
            None (meaning the caller may proceed).
        """
        if bool(self._config.get("telegram.enabled", False)):
            return None
        logger.error("Telegram operation rejected: Telegram disabled.")
        return CommandResult(success=False, message="Telegram disabled.")

    def _poll_loop(self) -> None:
        """Repeatedly poll for and route messages every 'telegram.polling_interval' seconds."""
        interval = float(self._config.get("telegram.polling_interval", 2))
        while not self._stop_event.wait(interval):
            self._poll_once()
        logger.info("Telegram polling stopped.")

    def _poll_once(self) -> None:
        """Fetch and route any new messages, replying with each command's result."""
        if self._client is None:
            return

        try:
            messages = self._client.fetch_updates()
        except TelegramClientError as exc:  # noqa: BLE001 - the poll loop must never die silently
            logger.error(f"Telegram polling failed: {exc}")
            return

        for message in messages:
            result = self._router.route(message.chat_id, message.text)
            try:
                self._client.send_message(message.chat_id, result.message)
            except TelegramClientError as exc:
                logger.error(f"Telegram outgoing message failed: {exc}")

    def _is_poll_loop_running(self) -> bool:
        """Return whether the background polling thread is alive."""
        with self._lifecycle_lock:
            return self._poll_thread is not None and self._poll_thread.is_alive()
