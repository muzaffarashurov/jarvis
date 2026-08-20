"""EmailError hierarchy for EP-042 Email Integration.

A flat domain-exception hierarchy per subsystem, matching this
project's existing convention (`DiscordError` in EP-041, `GitHubError`
in EP-039). Because IMAP exposes more distinct failure modes than a
single REST API (a connection step, a separate TLS-negotiation step, a
separate mailbox-selection step, a separate search step), this
hierarchy has more members than `DiscordError`/`GitHubError`, but
remains a single flat level under one common base -- no further
sub-hierarchy exists.

`EmailServiceError` (raised only for invalid 'email.*' configuration,
at `EmailService.__init__` time) intentionally does NOT subclass
`EmailError`: it can never occur from a running operation call, only
from Bootstrap construction, matching how `DiscordServiceError` is
distinct from `DiscordError` in EP-041. `EmailServiceError` is defined
in `src/services/email_service.py`, not here, for the same reason.
"""

from __future__ import annotations

__all__ = [
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


class EmailError(Exception):
    """Base class for every Email Integration exception raised by an operation call."""


class EmailAuthenticationError(EmailError):
    """The configured username/password environment variable is
    missing/blank, or the IMAP server rejected the configured
    credentials."""


class EmailConnectionError(EmailError):
    """A connection-level failure occurred (DNS, refused, ...)."""


class EmailTimeoutError(EmailError):
    """The call exceeded 'email.timeout_seconds'."""


class EmailTLSError(EmailError):
    """A TLS/certificate negotiation failure occurred."""


class EmailMailboxError(EmailError):
    """The requested folder does not exist, or SELECT failed."""


class EmailMessageNotFoundError(EmailError):
    """The requested UID does not exist in the selected folder."""


class EmailSearchError(EmailError):
    """The IMAP server rejected the search criteria."""


class EmailProtocolError(EmailError):
    """Any other IMAP protocol failure, or an unparseable server response."""
