"""Request/response DTOs for the EP-043 REST API.

These dataclasses define the REST API's external JSON contract. They
intentionally mirror only what a client sends or receives over HTTP --
never an internal domain/service object -- so the API's external
boundary stays independent of internal Jarvis implementation details
(see EP043_STEP1_REPORT.md, section 10 "API Boundary and DTOs").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.core.command_router import CommandResult

__all__ = [
    "CommandRequest",
    "CommandResponse",
    "ErrorPayload",
    "HealthResponse",
]


@dataclass(frozen=True)
class CommandRequest:
    """Deserialized, validated body of ``POST /api/v1/commands``.

    Attributes:
        module: The target command namespace (e.g. "system", "email").
        action: The action within that namespace. May be empty.
        arguments: Additional positional arguments, in order.
    """

    module: str
    action: str = ""
    arguments: list[str] = field(default_factory=list)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> CommandRequest:
        """Validate and build a CommandRequest from a decoded JSON body.

        Args:
            data: The decoded JSON request body.

        Returns:
            A validated CommandRequest.

        Raises:
            ValueError: If required fields are missing or of the wrong
                type. Callers translate this into an
                ``ApiValidationError`` (HTTP 400).
        """
        module = data.get("module")
        action = data.get("action", "")
        arguments = data.get("arguments", [])

        if not isinstance(module, str) or not module.strip():
            raise ValueError("'module' is required and must be a non-empty string.")
        if not isinstance(action, str):
            raise ValueError("'action' must be a string.")  # noqa: TRY004 - uniform ValueError lets callers catch one exception type
        if not isinstance(arguments, list) or not all(isinstance(a, str) for a in arguments):
            raise ValueError("'arguments' must be a list of strings.")

        return CommandRequest(module=module, action=action, arguments=list(arguments))


@dataclass(frozen=True)
class CommandResponse:
    """Serialized body returned by the status and commands endpoints.

    Mirrors ``CommandResult`` (``src/core/command_router.py``) exactly
    -- the same result type InteractiveShell already displays -- minus
    the CLI-only ``should_exit`` field, which has no meaning over a
    stateless HTTP request (see EP043_STEP2_REPORT.md, "Known
    Limitations").
    """

    success: bool
    message: str

    @staticmethod
    def from_command_result(result: CommandResult) -> CommandResponse:
        """Build a CommandResponse from an existing CommandResult.

        Args:
            result: The result returned by ``CommandRouter.dispatch()``.

        Returns:
            The equivalent CommandResponse.
        """
        return CommandResponse(success=result.success, message=result.message)

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable representation of this response."""
        return {"success": self.success, "message": self.message}


@dataclass(frozen=True)
class HealthResponse:
    """Serialized body returned by ``GET /health``."""

    status: str = "ok"

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable representation of this response."""
        return {"status": self.status}


@dataclass(frozen=True)
class ErrorPayload:
    """Serialized body returned for every non-2xx REST API response.

    Attributes:
        code: The machine-readable error code (see ``api_error.py``).
        message: A human-readable description of the failure. Never
            contains a stack trace or internal implementation detail.
    """

    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable representation of this response."""
        return {"error": {"code": self.code, "message": self.message}}
