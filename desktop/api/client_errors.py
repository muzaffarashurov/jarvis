"""Typed error hierarchy for the Desktop UI's REST API client.

Every failure ``JarvisApiClient`` (``jarvis_api_client.py``) can raise
is one of these types, so callers (ViewModels) can branch on a small,
closed set of categories instead of catching bare ``requests``
exceptions or raw ``Exception``. Mirrors EP-043's own server-side
error-hierarchy pattern (``src/core/api/api_error.py``) on the client
side of the same boundary.

Categories match EP044_DESIGN.md, Section 18 ("Error Handling"):
Network error, Timeout, HTTP error, API validation error, API internal
error, Malformed response, Unexpected client error. Command failure
(``success: False`` with HTTP 200) is *not* an error in this
hierarchy -- it is a normal, successfully-routed
``CommandResponse`` (see ``desktop/models/dto.py``) and is handled by
the caller as a result, not an exception (EP044_DESIGN.md Section 18).
"""

from __future__ import annotations

__all__ = [
    "ApiClientError",
    "ApiHttpError",
    "ApiNetworkError",
    "ApiTimeoutError",
    "MalformedResponseError",
]


class ApiClientError(Exception):
    """Base class for every error the Desktop API client can raise.

    Never carries a raw Python traceback or internal implementation
    detail intended for direct display -- callers are responsible for
    presenting ``str(error)`` (or a category-specific user-facing
    message) rather than exposing the underlying exception chain to
    the user, matching EP044_DESIGN.md Section 18 ("Raw Python
    exceptions are never shown to the user directly").
    """


class ApiNetworkError(ApiClientError):
    """The server could not be reached at all.

    Covers connection refused, DNS failure, and similar
    transport-level failures where no HTTP response was ever received
    (EP044_DESIGN.md Section 18, "Network error").
    """


class ApiTimeoutError(ApiClientError):
    """The request exceeded the configured timeout with no response.

    (EP044_DESIGN.md Section 18, "Timeout".)
    """


class ApiHttpError(ApiClientError):
    """The server returned a non-2xx HTTP status.

    Covers EP-043's documented error statuses: 400 (validation), 404
    (not found), 405 (method not allowed), 415 (unsupported media
    type), and 500 (internal error) -- see EP044_DESIGN.md Section 13.

    Attributes:
        status_code: The HTTP status code returned by the server.
        error_code: The machine-readable error code from the server's
            ``{"error": {"code": ..., "message": ...}}`` body
            (``src/core/api/dto.py``'s ``ErrorPayload``), if the body
            was well-formed. ``None`` if the error body itself could
            not be parsed.
    """

    def __init__(self, status_code: int, message: str, error_code: str | None = None) -> None:
        """Initialize the HTTP error.

        Args:
            status_code: The HTTP status code returned by the server.
            message: A human-readable message safe to display to the
                user (the server's own ``ErrorPayload.message``, which
                EP-043 already guarantees never contains a stack
                trace -- see ``src/core/api/api_error.py``).
            error_code: The server's machine-readable error code, if
                available.
        """
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class MalformedResponseError(ApiClientError):
    """The server returned HTTP 200 but the body was not valid or expected.

    Covers both "not valid JSON" and "valid JSON but missing/invalid
    expected fields" (EP044_DESIGN.md Section 18, "Malformed
    response").
    """
