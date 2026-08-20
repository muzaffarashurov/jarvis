"""EP-042 Email Integration -- read-only inspection of a standard,
provider-independent IMAP mailbox.

Exposes four read-only operations (`list_folders`, `list_messages`,
`get_message`, `search_messages`) against a standard IMAP server, using
the Python standard library (`imaplib` + `email`) only -- no
third-party dependency, no provider-specific API (Gmail API, Microsoft
Graph, Outlook API), no OAuth. No send, reply, forward, delete, move,
or flag/mark (read/unread) operation is implemented -- this package
can only ever read from the configured mailbox.

This package (`src/core/email/`) holds only pure, dependency-free data
types -- `EmailFolder`, `EmailAttachment`, `EmailMessageSummary`,
`EmailMessage`, `EmailResult`, and the `EmailError` hierarchy. All
IMAP protocol/network logic lives exclusively in `EmailService`
(`src/services/email_service.py`), matching the "one component owns
the one real invocation point" discipline `DiscordService` (EP-041)
and `GitHubService` (EP-039) already established for their respective
protocols.

This subsystem has no dependency on any other Engineering Package --
it depends only on `Config` and, at call time, the process environment
(via the two configured environment-variable names -- see
`src/services/email_service.py`).

`EmailService` is deliberately stateless between calls: each operation
opens one short-lived IMAP connection, performs its one unit of work,
and always closes the connection before returning -- no persistent
connection, background thread, or polling exists anywhere in this
subsystem.

Public API:
    EmailFolder -- One IMAP mailbox/folder entry.
    EmailAttachment -- Attachment metadata only (never content).
    EmailMessageSummary -- Envelope-only row used by list/search results.
    EmailMessage -- A fully normalized message, returned by get_message.
    EmailResult -- The outcome of one successful EmailService call.
    EmailError -- Base class for every exception an operation call can raise.
    EmailAuthenticationError -- Missing/blank credentials, or the IMAP
        server rejected the configured credentials.
    EmailConnectionError -- A connection-level failure occurred.
    EmailTimeoutError -- The call exceeded 'email.timeout_seconds'.
    EmailTLSError -- A TLS/certificate negotiation failure occurred.
    EmailMailboxError -- The requested folder does not exist, or SELECT failed.
    EmailMessageNotFoundError -- The requested UID does not exist in the folder.
    EmailSearchError -- The IMAP server rejected the search criteria.
    EmailProtocolError -- Any other IMAP protocol failure, or an
        unparseable server response.
"""

from __future__ import annotations

from src.core.email.email_error import (
    EmailAuthenticationError,
    EmailConnectionError,
    EmailError,
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

__all__ = [
    "EmailFolder",
    "EmailAttachment",
    "EmailMessageSummary",
    "EmailMessage",
    "EmailResult",
    "EmailError",
    "EmailAuthenticationError",
    "EmailConnectionError",
    "EmailTimeoutError",
    "EmailTLSError",
    "EmailMailboxError",
    "EmailMessageNotFoundError",
    "EmailSearchError",
    "EmailProtocolError",
]
