"""Email domain models for EP-042 Email Integration.

Pure data describing IMAP mailboxes and normalized messages -- no
IMAP/network call happens in this module, matching the pattern already
used by `DiscordResult` (`src/core/discord/discord_result.py`,
EP-041): small, dependency-free data types owned by Core, with all
real IMAP invocations living exclusively in `EmailService`
(`src/services/email_service.py`).

Messages are normalized (never raw IMAP/RFC 822 structures) before
reaching Core, per EP-042's explicit "do not expose raw IMAP protocol
structures directly to the rest of Jarvis" requirement -- see
`EmailService`'s normalization logic for how these are built.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "EmailFolder",
    "EmailAttachment",
    "EmailMessageSummary",
    "EmailMessage",
    "EmailResult",
]


@dataclass(frozen=True)
class EmailFolder:
    """One IMAP mailbox/folder entry, from a `LIST` response.

    Attributes:
        name: The folder's full name (e.g. "INBOX", "INBOX.Archive").
        delimiter: The hierarchy delimiter the server reported for
            this folder (e.g. "."  or "/"), or "" if none was given.
        attributes: The folder's IMAP attribute flags (e.g.
            "\\HasNoChildren", "\\Noselect"), exactly as reported by
            the server, with no further interpretation.
    """

    name: str
    delimiter: str
    attributes: tuple[str, ...]


@dataclass(frozen=True)
class EmailAttachment:
    """Metadata for one attachment found on a message.

    Attachment *content* is never stored here or anywhere else in this
    subsystem -- only metadata, per EP-042's explicit scope.

    Attributes:
        filename: The attachment's declared filename, or None if the
            MIME part did not declare one.
        content_type: The attachment's declared MIME content type
            (e.g. "application/pdf").
        size_bytes: The size, in bytes, of the attachment's decoded
            payload as parsed from the message.
    """

    filename: str | None
    content_type: str
    size_bytes: int


@dataclass(frozen=True)
class EmailMessageSummary:
    """One envelope-only row, used by `list_messages`/`search_messages`.

    Deliberately headers-only (no body, no attachments) -- fetching a
    full message body for every row in a listing/search result is not
    performed, so listing or searching a large mailbox does not force
    downloading every matching message's full content.

    Attributes:
        uid: The message's IMAP UID within `folder` (stable across a
            session; not a message sequence number).
        subject: The decoded Subject header, or "" if absent.
        sender: The decoded From header, or "" if absent.
        date: The message's Date header as reported by the server, or
            None if absent/unparseable.
        folder: The folder this summary was read from.
    """

    uid: str
    subject: str
    sender: str
    date: str | None
    folder: str


@dataclass(frozen=True)
class EmailMessage:
    """One fully normalized message, returned only by `get_message`.

    Attributes:
        uid: The message's IMAP UID within `folder`.
        message_id: The message's Message-ID header, or None if absent.
        subject: The decoded Subject header, or "" if absent.
        sender: The decoded From header, or "" if absent.
        recipients: The decoded To header addresses, or an empty tuple.
        cc: The decoded Cc header addresses, or an empty tuple.
        date: The message's Date header as reported by the server, or
            None if absent/unparseable.
        body_text: The first text/plain part's decoded content, or
            None if the message has no text/plain part.
        body_html: The first text/html part's decoded content, or None
            if the message has no text/html part.
        folder: The folder this message was read from.
        attachments: Metadata for every attachment part found on the
            message. Never includes attachment content.
    """

    uid: str
    message_id: str | None
    subject: str
    sender: str
    recipients: tuple[str, ...]
    cc: tuple[str, ...]
    date: str | None
    body_text: str | None
    body_html: str | None
    folder: str
    attachments: tuple[EmailAttachment, ...]


@dataclass(frozen=True)
class EmailResult:
    """The outcome of one successful EmailService call.

    Attributes:
        operation: The EmailService method that produced this result
            (e.g. "list_messages"), for logging/debugging.
        data: The normalized result -- one of EmailFolder,
            EmailMessage, EmailMessageSummary, or a list of either,
            depending on `operation`. Never a raw IMAP/RFC 822
            structure.
    """

    operation: str
    data: Any
