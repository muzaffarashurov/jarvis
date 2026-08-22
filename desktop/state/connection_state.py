"""Application state enums for the Desktop UI.

Two small, independent enums rather than one combined state machine,
since connection health and the outcome of the last submitted command
are orthogonal concerns -- a command can fail (``success: False``)
while the connection itself stays healthy (EP044_DESIGN.md
Section 16). Held on ``MainWindowViewModel`` and exposed to Views via
Qt signals.
"""

from __future__ import annotations

from enum import Enum, auto

__all__ = ["CommandState", "ConnectionState"]


class ConnectionState(Enum):
    """Health/reachability of the configured Jarvis REST API.

    EP044_DESIGN.md, Section 16.
    """

    DISCONNECTED = auto()
    """No successful health check has been made yet, or the last one failed."""

    CONNECTING = auto()
    """A health check is currently in flight."""

    CONNECTED = auto()
    """The last health check succeeded."""

    API_UNAVAILABLE = auto()
    """The last health check failed (network error, timeout, or HTTP error)."""


class CommandState(Enum):
    """Outcome of the most recently submitted command or status request.

    EP044_DESIGN.md, Section 16.
    """

    IDLE = auto()
    """No command has been submitted yet."""

    REQUEST_IN_PROGRESS = auto()
    """A command request is currently in flight."""

    SUCCEEDED = auto()
    """The request was routed and the underlying command reported success."""

    FAILED = auto()
    """The request was routed but the underlying command reported failure
    (``success: False``, HTTP 200) -- not a transport error."""

    ERROR = auto()
    """A transport-level error occurred (network error, timeout, HTTP
    error, or malformed response) -- see ``desktop/api/client_errors.py``."""
