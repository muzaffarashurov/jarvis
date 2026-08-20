"""Business logic that wires EP-042 Email Integration into the application.

EmailService is a thin, config-driven, read-only wrapper around a
standard IMAP server, using only the Python standard library
(`imaplib` + `email`) -- no third-party dependency, no provider-
specific API (Gmail API, Microsoft Graph, Outlook API), no OAuth.

Authentication: the IMAP username/password are read from
`os.environ` at the start of every operation call (never at
`__init__`, never cached on `self` beyond the duration of a single
call, never logged), using the two environment-variable *names*
configured via `email.imap_username_env_var`/
`email.imap_password_env_var` (see `_resolve_credentials_env_vars`).
If either is unset or blank, `EmailAuthenticationError` is raised
immediately, before any connection is opened. The credential values
are sent only inside the IMAP `LOGIN` command; they never appear in a
log line, an exception message, or an `EmailResult`.

Unlike `DiscordService`/`GitHubService` (a single stateless HTTP call
per operation), IMAP is inherently connection-oriented: a mailbox must
be selected before it can be searched or fetched from. This service
stays conceptually stateless the same way those do -- no connection is
ever stored on `self` -- by opening one short-lived connection per
public method call (connect -> login -> select -> operate -> close),
always closing it (even on failure) before the method returns. No
background thread, timer, event loop, or IDLE/polling connection
exists anywhere in this module.

No send, reply, forward, delete, move, or flag/mark (read/unread)
Email operation is implemented or callable through this service --
every mailbox `SELECT` this service performs is read-only
(`readonly=True`, i.e. IMAP `EXAMINE`), so this subsystem cannot even
have the side effect of marking a message \\Seen.
"""

from __future__ import annotations

import email as email_lib
import imaplib
import os
import re
import socket
import ssl
from email.header import decode_header
from email.message import Message
from typing import Callable, Protocol

from loguru import logger

from src.core.config import Config
from src.core.email.email_error import (
    EmailAuthenticationError,
    EmailConnectionError,
    EmailMailboxError,
    EmailMessageNotFoundError,
    EmailProtocolError,
    EmailSearchError,
    EmailTimeoutError,
    EmailTLSError,
)
from src.core.email.email_result import (
    EmailAttachment,
    EmailFolder,
    EmailMessage,
    EmailMessageSummary,
    EmailResult,
)

_DEFAULT_IMAP_PORT = 993
_DEFAULT_TLS_MODE = "ssl"
_VALID_TLS_MODES = ("ssl", "starttls")
_DEFAULT_USERNAME_ENV_VAR = "EMAIL_IMAP_USERNAME"
_DEFAULT_PASSWORD_ENV_VAR = "EMAIL_IMAP_PASSWORD"
_DEFAULT_MAILBOX = "INBOX"
_DEFAULT_MESSAGE_LIMIT = 50
_DEFAULT_TIMEOUT_SECONDS = 30.0

_LIST_LINE_RE = re.compile(r'^\((?P<attrs>[^)]*)\)\s+"?(?P<delim>[^"]*?)"?\s+(?P<name>.+)$')


class EmailServiceError(Exception):
    """Raised for invalid 'email.*' configuration.

    Can only ever be raised from `EmailService.__init__`, before any
    IMAP connection is attempted -- never from a running
    `list_folders()`/`list_messages()`/etc. call, which instead raise
    `EmailError` subclasses (see `src.core.email.email_error`). Never
    raised for missing/invalid credentials -- those are checked
    per-call instead (see module docstring) and raise
    `EmailAuthenticationError`. This mirrors `DiscordServiceError`'s
    split from `DiscordError` in EP-041.
    """


class _IMAPConnection(Protocol):
    """The small subset of `imaplib.IMAP4`/`IMAP4_SSL`'s interface this
    service actually uses. A real `imaplib.IMAP4_SSL`/`IMAP4` instance
    already satisfies this Protocol natively; tests supply a small
    duck-typed stub instead, so no real IMAP server is ever contacted
    by this project's own test suite."""

    def login(self, user: str, password: str) -> tuple: ...

    def select(self, mailbox: str, readonly: bool = False) -> tuple: ...

    def list(self) -> tuple: ...

    def uid(self, command: str, *args) -> tuple: ...

    def close(self) -> tuple: ...

    def logout(self) -> tuple: ...


ConnectionFactory = Callable[[str, int, str, float], _IMAPConnection]


def _default_connection_factory(host: str, port: int, tls_mode: str, timeout: float) -> _IMAPConnection:
    """Build a real `imaplib.IMAP4_SSL`/`IMAP4` connection.

    Args:
        host: The IMAP server hostname.
        port: The IMAP server port.
        tls_mode: "ssl" (implicit TLS, IMAPS) or "starttls" (plaintext
            connection upgraded via STARTTLS). No other value reaches
            this function -- `EmailService.__init__` already validated
            it.
        timeout: Connection/read timeout, in seconds.

    Returns:
        A connected (but not yet logged in) IMAP4/IMAP4_SSL instance.
    """
    if tls_mode == "ssl":
        context = ssl.create_default_context()
        return imaplib.IMAP4_SSL(host, port, ssl_context=context, timeout=timeout)

    context = ssl.create_default_context()
    connection = imaplib.IMAP4(host, port, timeout=timeout)
    connection.starttls(ssl_context=context)
    return connection


class EmailService:
    """Config-driven, read-only wrapper around a standard IMAP server."""

    def __init__(self, config: Config, connection_factory: ConnectionFactory | None = None) -> None:
        """Initialize the EmailService.

        Args:
            config: Loaded application configuration, used to resolve
                every 'email.*' setting. Never used to resolve
                credentials -- those are read directly from the
                process environment at call time.
            connection_factory: Optional callable
                `(host, port, tls_mode, timeout) -> connection`
                returning an object satisfying `_IMAPConnection`.
                Defaults to `_default_connection_factory` (a real
                `imaplib.IMAP4_SSL`/`IMAP4` connection); tests supply a
                duck-typed stub instead.

        Raises:
            EmailServiceError: If any 'email.*' configuration value is
                missing (when required) or invalid.
        """
        self._config = config
        self._imap_host = self._resolve_imap_host()
        self._imap_port = self._resolve_imap_port()
        self._tls_mode = self._resolve_tls_mode()
        self._username_env_var, self._password_env_var = self._resolve_credentials_env_vars()
        self._default_mailbox = self._resolve_default_mailbox()
        self._default_message_limit = self._resolve_default_message_limit()
        self._timeout_seconds = self._resolve_timeout_seconds()
        self._connection_factory = connection_factory or _default_connection_factory
        logger.info(
            f"Email Service initialized (imap_host: {self._imap_host}, "
            f"imap_port: {self._imap_port}, tls_mode: {self._tls_mode}, "
            f"timeout: {self._timeout_seconds}s)."
        )

    # ---------- Public API ----------

    def list_folders(self) -> EmailResult:
        """Return every mailbox/folder available on the server.

        Returns:
            An EmailResult whose `data` is a list of EmailFolder.

        Raises:
            EmailAuthenticationError: If credentials are missing/blank,
                or the server rejects them.
            EmailConnectionError: If a connection-level failure occurs.
            EmailTimeoutError: If the call exceeds 'email.timeout_seconds'.
            EmailTLSError: If a TLS/certificate negotiation failure occurs.
            EmailProtocolError: If the server response cannot be parsed.
        """
        with self._session() as connection:
            typ, data = connection.list()
            if typ != "OK":
                raise EmailProtocolError("IMAP server rejected the LIST command.")
            folders = [self._parse_folder_line(line) for line in data if line]
            return EmailResult(operation="list_folders", data=folders)

    def list_messages(self, folder: str | None = None, limit: int | None = None) -> EmailResult:
        """Return the most recent messages (envelope only) from a folder.

        Args:
            folder: The mailbox to list. Defaults to
                'email.default_mailbox' when omitted.
            limit: The maximum number of messages to return, most
                recent first. Defaults to
                'email.default_message_limit' when omitted.

        Returns:
            An EmailResult whose `data` is a list of
            EmailMessageSummary, newest first.

        Raises:
            EmailAuthenticationError: If credentials are missing/blank,
                or the server rejects them.
            EmailConnectionError: If a connection-level failure occurs.
            EmailTimeoutError: If the call exceeds 'email.timeout_seconds'.
            EmailTLSError: If a TLS/certificate negotiation failure occurs.
            EmailMailboxError: If the folder does not exist.
            EmailProtocolError: If the server response cannot be parsed.
        """
        resolved_folder = folder or self._default_mailbox
        resolved_limit = limit if limit is not None else self._default_message_limit

        with self._session() as connection:
            self._select(connection, resolved_folder)
            uids = self._search_uids(connection, "ALL")
            uids_to_fetch = uids[-resolved_limit:][::-1] if resolved_limit > 0 else []
            summaries = [
                self._fetch_summary(connection, uid, resolved_folder) for uid in uids_to_fetch
            ]
            return EmailResult(operation="list_messages", data=summaries)

    def get_message(self, folder: str, uid: str) -> EmailResult:
        """Return one fully normalized message.

        Args:
            folder: The mailbox the message belongs to.
            uid: The message's IMAP UID within `folder`.

        Returns:
            An EmailResult whose `data` is one EmailMessage.

        Raises:
            EmailAuthenticationError: If credentials are missing/blank,
                or the server rejects them.
            EmailConnectionError: If a connection-level failure occurs.
            EmailTimeoutError: If the call exceeds 'email.timeout_seconds'.
            EmailTLSError: If a TLS/certificate negotiation failure occurs.
            EmailMailboxError: If the folder does not exist.
            EmailMessageNotFoundError: If the UID does not exist in the folder.
            EmailProtocolError: If the server response cannot be parsed.
        """
        with self._session() as connection:
            self._select(connection, folder)
            raw = self._fetch_raw_message(connection, uid, "(RFC822)")
            message = email_lib.message_from_bytes(raw)
            normalized = self._normalize_message(message, uid=uid, folder=folder)
            return EmailResult(operation="get_message", data=normalized)

    def search_messages(self, folder: str, criteria: str) -> EmailResult:
        """Search a folder using a raw IMAP search-key expression.

        Args:
            folder: The mailbox to search.
            criteria: A raw IMAP search-key expression (e.g.
                'UNSEEN', 'SUBJECT "invoice"', 'SINCE 01-Jan-2026').
                Passed to the server as-is -- this service does not
                impose a query DSL on top of it.

        Returns:
            An EmailResult whose `data` is a list of
            EmailMessageSummary matching `criteria`.

        Raises:
            EmailAuthenticationError: If credentials are missing/blank,
                or the server rejects them.
            EmailConnectionError: If a connection-level failure occurs.
            EmailTimeoutError: If the call exceeds 'email.timeout_seconds'.
            EmailTLSError: If a TLS/certificate negotiation failure occurs.
            EmailMailboxError: If the folder does not exist.
            EmailSearchError: If the server rejects the search criteria.
            EmailProtocolError: If the server response cannot be parsed.
        """
        if not criteria or not criteria.strip():
            raise EmailSearchError("Search criteria must not be empty.")

        with self._session() as connection:
            self._select(connection, folder)
            uids = self._search_uids(connection, criteria)
            summaries = [self._fetch_summary(connection, uid, folder) for uid in reversed(uids)]
            return EmailResult(operation="search_messages", data=summaries)

    # ---------- Connection lifecycle ----------

    def _require_credentials(self) -> tuple[str, str]:
        """Return (username, password) from the environment, or raise.

        Returns:
            The non-blank (username, password) pair.

        Raises:
            EmailAuthenticationError: If either environment variable is
                unset or blank.
        """
        username = os.environ.get(self._username_env_var)
        password = os.environ.get(self._password_env_var)
        if not username or not username.strip():
            raise EmailAuthenticationError(
                f"{self._username_env_var} environment variable is not set."
            )
        if not password or not password.strip():
            raise EmailAuthenticationError(
                f"{self._password_env_var} environment variable is not set."
            )
        return username, password

    class _Session:
        """Context manager: open one IMAP connection, log in, and
        guarantee logout/close before the `with` block exits -- even
        when the block raises."""

        def __init__(self, service: "EmailService") -> None:
            self._service = service
            self._connection: _IMAPConnection | None = None

        def __enter__(self) -> _IMAPConnection:
            username, password = self._service._require_credentials()
            self._connection = self._service._connect(username, password)
            return self._connection

        def __exit__(self, exc_type, exc_value, traceback) -> bool:
            if self._connection is not None:
                try:
                    self._connection.logout()
                except Exception:  # nosec - best-effort cleanup only
                    pass
            return False

    def _session(self) -> "EmailService._Session":
        """Return a new one-shot IMAP session context manager."""
        return EmailService._Session(self)

    def _connect(self, username: str, password: str) -> _IMAPConnection:
        """Open one IMAP connection and authenticate.

        Args:
            username: The resolved IMAP username.
            password: The resolved IMAP password.

        Returns:
            A connected, logged-in IMAP connection.

        Raises:
            EmailAuthenticationError: If the server rejects the
                credentials.
            EmailConnectionError: If a connection-level failure occurs.
            EmailTimeoutError: If the connection attempt times out.
            EmailTLSError: If a TLS/certificate negotiation failure
                occurs.
        """
        try:
            connection = self._connection_factory(
                self._imap_host, self._imap_port, self._tls_mode, self._timeout_seconds
            )
        except socket.timeout as exc:
            raise EmailTimeoutError(
                f"Connecting to the IMAP server timed out after {self._timeout_seconds}s."
            ) from exc
        except ssl.SSLError as exc:
            raise EmailTLSError("TLS/certificate negotiation with the IMAP server failed.") from exc
        except (OSError, ConnectionError) as exc:
            raise EmailConnectionError("Could not reach the configured IMAP server.") from exc

        try:
            connection.login(username, password)
        except imaplib.IMAP4.error as exc:
            raise EmailAuthenticationError(
                "IMAP server rejected the configured credentials."
            ) from exc
        except socket.timeout as exc:
            raise EmailTimeoutError(
                f"IMAP login timed out after {self._timeout_seconds}s."
            ) from exc

        return connection

    def _select(self, connection: _IMAPConnection, folder: str) -> None:
        """Select `folder` read-only, or raise EmailMailboxError.

        Args:
            connection: An already-connected, logged-in connection.
            folder: The mailbox to select.

        Raises:
            EmailMailboxError: If the folder does not exist, or SELECT
                otherwise fails.
        """
        try:
            typ, _data = connection.select(folder, readonly=True)
        except imaplib.IMAP4.error as exc:
            raise EmailMailboxError(f"Could not select mailbox '{folder}'.") from exc
        if typ != "OK":
            raise EmailMailboxError(f"Mailbox '{folder}' does not exist or could not be selected.")

    def _search_uids(self, connection: _IMAPConnection, criteria: str) -> list[str]:
        """Run one `UID SEARCH` and return matching UIDs, ascending.

        Args:
            connection: An already-connected, folder-selected connection.
            criteria: A raw IMAP search-key expression.

        Returns:
            The matching UIDs, explicitly sorted ascending by their
            numeric value. RFC 3501 does not guarantee SEARCH results
            are returned in any particular order, so this method
            enforces ascending numeric order itself rather than
            trusting server-returned order -- both `list_messages`
            ("most recent first") and `search_messages` depend on a
            reliable ascending ordering to correctly identify the most
            recent messages.

        Raises:
            EmailSearchError: If the server rejects the criteria.
            EmailProtocolError: If the response cannot be parsed.
        """
        try:
            typ, data = connection.uid("search", None, criteria)
        except imaplib.IMAP4.error as exc:
            raise EmailSearchError(f"IMAP server rejected search criteria: {criteria!r}") from exc
        if typ != "OK":
            raise EmailSearchError(f"IMAP server rejected search criteria: {criteria!r}")
        if not data or not data[0]:
            return []
        uids = data[0].split()  # type: ignore[union-attr]
        try:
            uids.sort(key=lambda candidate: int(candidate))
        except (TypeError, ValueError) as exc:
            raise EmailProtocolError(
                f"IMAP server returned a non-numeric UID in SEARCH results: {data[0]!r}"
            ) from exc
        return uids

    def _fetch_summary(
        self, connection: _IMAPConnection, uid: "str | bytes", folder: str
    ) -> EmailMessageSummary:
        """Fetch header-only data for one UID and normalize it.

        Args:
            connection: An already-connected, folder-selected connection.
            uid: The message UID (str or bytes, as returned by search).
            folder: The folder the message belongs to.

        Returns:
            The normalized EmailMessageSummary.

        Raises:
            EmailMessageNotFoundError: If the UID does not exist.
            EmailProtocolError: If the response cannot be parsed.
        """
        raw = self._fetch_raw_message(connection, uid, "(BODY.PEEK[HEADER])")
        message = email_lib.message_from_bytes(raw)
        uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
        return EmailMessageSummary(
            uid=uid_str,
            subject=self._decode_header_value(message.get("Subject")),
            sender=self._decode_header_value(message.get("From")),
            date=message.get("Date"),
            folder=folder,
        )

    def _fetch_raw_message(
        self, connection: _IMAPConnection, uid: "str | bytes", fetch_spec: str
    ) -> bytes:
        """Run one `UID FETCH` and return the raw message bytes.

        Args:
            connection: An already-connected, folder-selected connection.
            uid: The message UID (str or bytes).
            fetch_spec: The IMAP FETCH data-item spec (e.g. "(RFC822)").

        Returns:
            The raw message bytes (or header bytes) returned by the
            server.

        Raises:
            EmailMessageNotFoundError: If the UID does not exist.
            EmailProtocolError: If the response cannot be parsed.
        """
        uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
        try:
            typ, data = connection.uid("fetch", uid_str, fetch_spec)
        except imaplib.IMAP4.error as exc:
            raise EmailProtocolError(f"IMAP FETCH failed for uid={uid_str!r}.") from exc
        if typ != "OK" or not data:
            raise EmailMessageNotFoundError(f"No message with uid={uid_str!r} in the selected folder.")

        for part in data:
            if isinstance(part, tuple) and len(part) >= 2 and part[1]:
                return part[1]

        raise EmailMessageNotFoundError(f"No message with uid={uid_str!r} in the selected folder.")

    # ---------- Normalization ----------

    def _normalize_message(self, message: Message, uid: str, folder: str) -> EmailMessage:
        """Normalize a parsed `email.message.Message` into EmailMessage.

        Multipart handling is deliberately minimal and predictable: the
        first text/plain part becomes `body_text`, the first text/html
        part becomes `body_html`, and every other part carrying a
        filename or an "attachment" disposition becomes one
        EmailAttachment (metadata only). A non-multipart message maps
        its single body directly to `body_text` or `body_html`
        depending on its declared Content-Type.

        Args:
            message: The parsed message.
            uid: The message's IMAP UID.
            folder: The folder the message was read from.

        Returns:
            The normalized EmailMessage.
        """
        body_text: str | None = None
        body_html: str | None = None
        attachments: list[EmailAttachment] = []

        if message.is_multipart():
            for part in message.walk():
                if part.is_multipart():
                    continue
                filename = part.get_filename()
                disposition = str(part.get("Content-Disposition") or "")
                content_type = part.get_content_type()

                if filename or "attachment" in disposition.lower():
                    payload = part.get_payload(decode=True) or b""
                    attachments.append(
                        EmailAttachment(
                            filename=self._decode_header_value(filename) if filename else None,
                            content_type=content_type,
                            size_bytes=len(payload),
                        )
                    )
                    continue

                if content_type == "text/plain" and body_text is None:
                    body_text = self._decode_part_text(part)
                elif content_type == "text/html" and body_html is None:
                    body_html = self._decode_part_text(part)
        else:
            content_type = message.get_content_type()
            if content_type == "text/html":
                body_html = self._decode_part_text(message)
            else:
                body_text = self._decode_part_text(message)

        return EmailMessage(
            uid=uid,
            message_id=message.get("Message-ID"),
            subject=self._decode_header_value(message.get("Subject")),
            sender=self._decode_header_value(message.get("From")),
            recipients=self._decode_address_list(message.get("To")),
            cc=self._decode_address_list(message.get("Cc")),
            date=message.get("Date"),
            body_text=body_text,
            body_html=body_html,
            folder=folder,
            attachments=tuple(attachments),
        )

    @staticmethod
    def _decode_header_value(value: str | None) -> str:
        """Decode an RFC 2047 encoded-word header into plain text.

        A malformed or unrecognized charset declared inside the header
        (e.g. a garbled encoded-word, or a nonstandard/misspelled
        charset name a sender's mail client emitted) must never crash
        the calling operation -- this falls back to a safe,
        best-effort UTF-8 decode instead of letting a bare
        `LookupError`/`UnicodeDecodeError` escape, per EP042's "safe
        normalization" requirement (STEP 1 prompt, MESSAGE
        NORMALIZATION section: "predictable and safe extraction
        strategy").

        Args:
            value: The raw header value, or None.

        Returns:
            The decoded text (best-effort), or "" if `value` is
            None/empty.
        """
        if not value:
            return ""
        try:
            parts = decode_header(value)
        except (LookupError, UnicodeDecodeError, ValueError):
            return value
        decoded = []
        for text, charset in parts:
            if isinstance(text, bytes):
                try:
                    decoded.append(text.decode(charset or "utf-8", errors="replace"))
                except (LookupError, UnicodeDecodeError, ValueError):
                    decoded.append(text.decode("utf-8", errors="replace"))
            else:
                decoded.append(text)
        return "".join(decoded)

    @staticmethod
    def _decode_address_list(value: str | None) -> tuple[str, ...]:
        """Split a To/Cc header into individual, RFC 2047-decoded address strings.

        Args:
            value: The raw header value, or None.

        Returns:
            A tuple of decoded address strings (not further
            parsed/validated), or an empty tuple if `value` is
            None/empty.
        """
        if not value:
            return ()
        decoded_value = EmailService._decode_header_value(value)
        return tuple(part.strip() for part in decoded_value.split(",") if part.strip())

    @staticmethod
    def _decode_part_text(part: Message) -> str:
        """Decode one text MIME part's payload into a string.

        Falls back to a best-effort UTF-8 decode if the part's
        declared charset is malformed/unrecognized, for the same
        "safe normalization" reason as `_decode_header_value`.

        Args:
            part: A non-multipart message/part.

        Returns:
            The decoded text, or "" if the part has no payload.
        """
        payload = part.get_payload(decode=True)
        if payload is None:
            return ""
        charset = part.get_content_charset() or "utf-8"
        try:
            return payload.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError, ValueError):
            return payload.decode("utf-8", errors="replace")

    @staticmethod
    def _parse_folder_line(line: "bytes | str") -> EmailFolder:
        """Parse one raw IMAP LIST response line into an EmailFolder.

        Args:
            line: One raw line from `LIST`'s response data (e.g.
                b'(\\HasNoChildren) "." "INBOX"').

        Returns:
            The parsed EmailFolder.

        Raises:
            EmailProtocolError: If the line cannot be parsed.
        """
        text = line.decode() if isinstance(line, bytes) else line
        match = _LIST_LINE_RE.match(text.strip())
        if not match:
            raise EmailProtocolError(f"Could not parse IMAP LIST response line: {text!r}")
        attrs = tuple(a.strip() for a in match.group("attrs").split() if a.strip())
        delimiter = match.group("delim")
        name = match.group("name").strip().strip('"')
        return EmailFolder(name=name, delimiter=delimiter, attributes=attrs)

    # ---------- Configuration resolution ----------

    def _resolve_imap_host(self) -> str:
        """Resolve and validate 'email.imap_host'.

        Returns:
            The configured host.

        Raises:
            EmailServiceError: If 'email.enabled' is true but
                'email.imap_host' is missing/blank.
        """
        value = self._config.get("email.imap_host", "")
        enabled = bool(self._config.get("email.enabled", False))
        if enabled and (not isinstance(value, str) or not value.strip()):
            raise EmailServiceError(
                "Invalid value for 'email.imap_host': expected a non-empty string when "
                f"'email.enabled' is true, got {value!r}."
            )
        return value

    def _resolve_imap_port(self) -> int:
        """Resolve and validate 'email.imap_port'.

        Returns:
            The configured port (default `_DEFAULT_IMAP_PORT`).

        Raises:
            EmailServiceError: If the configured value is not an
                integer in 1..65535.
        """
        value = self._config.get("email.imap_port", _DEFAULT_IMAP_PORT)
        if isinstance(value, bool) or not isinstance(value, int) or not (1 <= value <= 65535):
            raise EmailServiceError(
                f"Invalid value for 'email.imap_port': expected an integer in 1..65535, got {value!r}."
            )
        return value

    def _resolve_tls_mode(self) -> str:
        """Resolve and validate 'email.tls_mode'.

        Returns:
            The configured TLS mode (default `_DEFAULT_TLS_MODE`).

        Raises:
            EmailServiceError: If the configured value is not "ssl" or
                "starttls". Plaintext, unencrypted IMAP is not
                supported by this subsystem.
        """
        value = self._config.get("email.tls_mode", _DEFAULT_TLS_MODE)
        if value not in _VALID_TLS_MODES:
            raise EmailServiceError(
                f"Invalid value for 'email.tls_mode': expected one of {_VALID_TLS_MODES}, got {value!r}."
            )
        return value

    def _resolve_credentials_env_vars(self) -> tuple[str, str]:
        """Resolve and validate the two credential environment-variable names.

        Returns:
            (username_env_var, password_env_var), the environment
            variable *names* -- never the secret values themselves.

        Raises:
            EmailServiceError: If either configured name is not a
                non-empty string.
        """
        username_env_var = self._config.get("email.imap_username_env_var", _DEFAULT_USERNAME_ENV_VAR)
        password_env_var = self._config.get("email.imap_password_env_var", _DEFAULT_PASSWORD_ENV_VAR)
        if not isinstance(username_env_var, str) or not username_env_var.strip():
            raise EmailServiceError(
                "Invalid value for 'email.imap_username_env_var': expected a non-empty string, "
                f"got {username_env_var!r}."
            )
        if not isinstance(password_env_var, str) or not password_env_var.strip():
            raise EmailServiceError(
                "Invalid value for 'email.imap_password_env_var': expected a non-empty string, "
                f"got {password_env_var!r}."
            )
        return username_env_var, password_env_var

    def _resolve_default_mailbox(self) -> str:
        """Resolve and validate 'email.default_mailbox'.

        Returns:
            The configured default mailbox (default `_DEFAULT_MAILBOX`).

        Raises:
            EmailServiceError: If the configured value is not a
                non-empty string.
        """
        value = self._config.get("email.default_mailbox", _DEFAULT_MAILBOX)
        if not isinstance(value, str) or not value.strip():
            raise EmailServiceError(
                f"Invalid value for 'email.default_mailbox': expected a non-empty string, got {value!r}."
            )
        return value

    def _resolve_default_message_limit(self) -> int:
        """Resolve and validate 'email.default_message_limit'.

        Returns:
            The configured default limit (default `_DEFAULT_MESSAGE_LIMIT`).

        Raises:
            EmailServiceError: If the configured value is not a
                positive integer.
        """
        value = self._config.get("email.default_message_limit", _DEFAULT_MESSAGE_LIMIT)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise EmailServiceError(
                "Invalid value for 'email.default_message_limit': expected a positive integer, "
                f"got {value!r}."
            )
        return value

    def _resolve_timeout_seconds(self) -> float:
        """Resolve and validate 'email.timeout_seconds'.

        Returns:
            The configured timeout in seconds (default
            `_DEFAULT_TIMEOUT_SECONDS`).

        Raises:
            EmailServiceError: If the configured value is not a
                positive number.
        """
        value = self._config.get("email.timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise EmailServiceError(
                f"Invalid value for 'email.timeout_seconds': expected a positive number, got {value!r}."
            )
        return float(value)
