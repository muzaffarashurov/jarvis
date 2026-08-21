"""Error hierarchy for the EP-043 REST API.

Every error the REST API can return to a client is one of these
types. Each carries its own HTTP status code and a short machine
-readable ``code``, so ``RestApiServer`` never has to guess a status
code -- and a client never receives an uncontrolled stack trace as
the response body (see EP043_STEP2_REPORT.md, "Error Handling").

Flat hierarchy, matching the existing per-subsystem convention used by
EP-038..EP-042 (e.g. ``EmailError`` and its subclasses in
``src/core/email/email_error.py``).
"""

from __future__ import annotations

__all__ = [
    "ApiError",
    "ApiInternalError",
    "ApiMethodNotAllowedError",
    "ApiNotFoundError",
    "ApiUnsupportedMediaTypeError",
    "ApiValidationError",
]


class ApiError(Exception):
    """Base class for every REST API error.

    Attributes:
        status_code: The HTTP status code this error maps to.
        code: A short, stable, machine-readable error identifier
            included in the JSON error body (see ``dto.ErrorPayload``).
    """

    status_code: int = 500
    code: str = "internal_error"


class ApiValidationError(ApiError):
    """The request was malformed or failed input validation (400)."""

    status_code = 400
    code = "validation_error"


class ApiNotFoundError(ApiError):
    """No resource exists at the requested path (404)."""

    status_code = 404
    code = "not_found"


class ApiMethodNotAllowedError(ApiError):
    """The path exists but does not support the requested HTTP method (405)."""

    status_code = 405
    code = "method_not_allowed"


class ApiUnsupportedMediaTypeError(ApiError):
    """A request body was sent with a non-JSON ``Content-Type`` (415).

    Added in EP-043 STEP 3 as part of the API's Content-Type policy
    (see ``rest_api_server.py`` module docstring): only raised when a
    ``Content-Type`` header is present and explicitly incompatible
    with JSON. A missing ``Content-Type`` header is treated
    leniently, not rejected -- see EP043_STEP3_REPORT.md, "Content-Type
    Handling".
    """

    status_code = 415
    code = "unsupported_media_type"


class ApiInternalError(ApiError):
    """An unexpected, uncategorized server-side failure (500).

    Never constructed with the original exception's message -- callers
    must pass a generic, safe message so internal details are never
    leaked to a client (see EP043_STEP2_REPORT.md, "Error Handling").
    """

    status_code = 500
    code = "internal_error"
