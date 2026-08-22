"""Client-side DTOs mirroring the EP-043 REST API's external contract.

These dataclasses mirror ``src/core/api/dto.py`` on the server side
(``CommandRequest``, ``CommandResponse``, ``HealthResponse``,
``ErrorPayload``) but are intentionally a separate, independent
definition: the Desktop UI is an external HTTP client and must not
import server-side code (EP044_DESIGN.md, Section 5). Keeping the
contract in two independently-maintained places, one per side of the
HTTP boundary, is the same pattern any external REST client uses --
the alternative (importing ``src.core.api.dto`` from ``desktop/``)
would require the Desktop UI to import ``src.core`` package internals,
which EP044_DESIGN.md Section 5 explicitly forbids.

See EP044_DESIGN.md, Section 13 ("REST API Integration") for the
verified contract these DTOs implement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "CommandRequest",
    "CommandResponse",
    "HealthResponse",
]


@dataclass(frozen=True)
class CommandRequest:
    """Outbound body for ``POST /api/v1/commands``.

    Attributes:
        module: The target command namespace (e.g. "system"). Required,
            non-empty.
        action: The action within that namespace. May be empty.
        arguments: Additional positional arguments, in order.
    """

    module: str
    action: str = ""
    arguments: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable request body.

        Returns:
            A dict matching EP-043's documented request schema
            (EP044_DESIGN.md Section 13):
            ``{"module": ..., "action": ..., "arguments": [...]}``.
        """
        return {
            "module": self.module,
            "action": self.action,
            "arguments": list(self.arguments),
        }


@dataclass(frozen=True)
class CommandResponse:
    """Deserialized body of a successfully routed EP-043 response.

    Used for both ``GET /api/v1/status`` and ``POST /api/v1/commands``,
    which share the same ``{"success": bool, "message": str}`` shape
    (EP044_DESIGN.md Section 13).

    Attributes:
        success: Whether the underlying command succeeded. Note this
            is carried in the JSON body, not the HTTP status -- EP-043
            returns HTTP 200 even when ``success`` is False (a
            "routed but the command itself failed" case). Callers must
            branch on this field, not the HTTP status code, to know
            whether the command succeeded.
        message: Human-readable result or failure message.
    """

    success: bool
    message: str

    @staticmethod
    def from_dict(data: dict[str, Any]) -> CommandResponse:
        """Build a CommandResponse from a decoded JSON response body.

        Args:
            data: The decoded JSON response body.

        Returns:
            The parsed CommandResponse.

        Raises:
            ValueError: If ``data`` does not contain the expected
                fields with the expected types. Callers translate this
                into a client-side ``MalformedResponseError`` (see
                ``desktop/api/client_errors.py``).
        """
        success = data.get("success")
        message = data.get("message")

        if not isinstance(success, bool):
            raise ValueError("'success' is required and must be a boolean.")  # noqa: TRY004 - uniform ValueError lets callers catch one exception type
        if not isinstance(message, str):
            raise ValueError("'message' is required and must be a string.")  # noqa: TRY004 - uniform ValueError lets callers catch one exception type

        return CommandResponse(success=success, message=message)


@dataclass(frozen=True)
class HealthResponse:
    """Deserialized body of ``GET /health``.

    Attributes:
        status: Expected to be ``"ok"`` for a healthy server
            (EP044_DESIGN.md Section 13).
    """

    status: str

    @staticmethod
    def from_dict(data: dict[str, Any]) -> HealthResponse:
        """Build a HealthResponse from a decoded JSON response body.

        Args:
            data: The decoded JSON response body.

        Returns:
            The parsed HealthResponse.

        Raises:
            ValueError: If ``data`` does not contain a ``status``
                string field.
        """
        status = data.get("status")

        if not isinstance(status, str):
            raise ValueError("'status' is required and must be a string.")  # noqa: TRY004 - uniform ValueError lets callers catch one exception type

        return HealthResponse(status=status)
