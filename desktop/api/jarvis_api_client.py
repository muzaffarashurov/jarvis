"""JarvisApiClient: the Desktop UI's REST API client.

Thin HTTP transport layer against the EP-043 REST API's existing
contract (``GET /health``, ``GET /api/v1/status``,
``POST /api/v1/commands`` -- see EP044_DESIGN.md Section 13). Built on
``requests``, which is already a Jarvis project dependency used
elsewhere (``src/services/github_service.py``,
``src/services/discord_service.py``, and two AI provider modules) --
this client introduces no new dependency (EP044_DESIGN.md Section 14).

Architecturally analogous to ``desktop/models/dto.py``'s relationship
to ``src/core/api/dto.py``: this client talks to Jarvis exclusively
over HTTP and never imports ``src.core``, ``src.services``,
``src.modules``, or ``src.bootstrap`` (EP044_DESIGN.md Section 5).

Contains no UI logic and no business logic: it only performs HTTP
requests, serializes/deserializes JSON, and raises a typed error
(``desktop/api/client_errors.py``) on every failure category. Callers
(ViewModels) are responsible for deciding what a result or error means
to the user.

No automatic retries are implemented for ``POST /api/v1/commands``:
commands may have side effects, so a failed/timed-out request does not
necessarily mean the command was not executed server-side
(EP044_DESIGN.md Section 14, "Retries").
"""

from __future__ import annotations

import json

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

from desktop.api.client_errors import (
    ApiHttpError,
    ApiNetworkError,
    ApiTimeoutError,
    MalformedResponseError,
)
from desktop.models.dto import CommandRequest, CommandResponse, HealthResponse

__all__ = ["JarvisApiClient"]

# EP044_DESIGN.md, Section 27, Decision D3: "the exact duration is a
# UX tradeoff... marked RECOMMENDED - OWNER APPROVAL REQUIRED".
# STEP 2's governing instructions resolve this open question with an
# explicit conservative fallback: "If the design leaves the value
# unresolved, use a conservative explicit default of 10 seconds."
DEFAULT_TIMEOUT_SECONDS: float = 10.0


class JarvisApiClient:
    """REST client for the EP-043 Jarvis REST API.

    Responsibilities:
        - Perform ``GET /health``, ``GET /api/v1/status``, and
          ``POST /api/v1/commands`` HTTP requests.
        - Serialize request bodies and deserialize response bodies
          into the DTOs in ``desktop/models/dto.py``.
        - Translate every failure into one of the typed errors in
          ``desktop/api/client_errors.py``.

    Never executes JARVIS business logic itself and never duplicates
    ``ApiRouter``/``CommandRouter``'s dispatch logic -- it only sends
    HTTP requests to the endpoints EP-043 already exposes.
    """

    def __init__(self, base_url: str, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        """Initialize the API client.

        Args:
            base_url: The Jarvis REST API's base URL, e.g.
                ``"http://127.0.0.1:8080"``. No trailing slash is
                required; one is stripped if present. Injected from
                Desktop-owned configuration
                (``desktop/config/desktop_config.py``) -- never
                hardcoded (EP044_DESIGN.md Section 14).
            timeout_seconds: The timeout applied to every request.
                Centralized here rather than hard-coded per call site
                (EP-044 STEP 2 governing instructions, Section 9).
        """
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @property
    def base_url(self) -> str:
        """Return the configured base URL."""
        return self._base_url

    @property
    def timeout_seconds(self) -> float:
        """Return the configured request timeout, in seconds."""
        return self._timeout_seconds

    def reconfigure(self, base_url: str, timeout_seconds: float | None = None) -> None:
        """Update the client's target base URL and, optionally, timeout.

        Used when the user applies new connection settings from the
        Desktop UI (EP044_DESIGN.md Section 15, "connection
        configuration") without needing to discard and recreate the
        client (and, with it, any ViewModel holding a reference to it).

        Args:
            base_url: The new Jarvis REST API base URL.
            timeout_seconds: The new request timeout, in seconds. Left
                unchanged if omitted.
        """
        self._base_url = base_url.rstrip("/")
        if timeout_seconds is not None:
            self._timeout_seconds = timeout_seconds

    def check_health(self) -> HealthResponse:
        """Call ``GET /health``.

        Returns:
            The parsed HealthResponse.

        Raises:
            ApiNetworkError: The server could not be reached.
            ApiTimeoutError: The request timed out.
            ApiHttpError: The server returned a non-2xx status.
            MalformedResponseError: The response body was not valid
                JSON or was missing expected fields.
        """
        data = self._request("GET", "/health")
        try:
            return HealthResponse.from_dict(data)
        except ValueError as exc:
            raise MalformedResponseError(str(exc)) from exc

    def get_status(self) -> CommandResponse:
        """Call ``GET /api/v1/status``.

        Returns:
            The parsed CommandResponse (equivalent to the CLI's
            ``system status``).

        Raises:
            ApiNetworkError: The server could not be reached.
            ApiTimeoutError: The request timed out.
            ApiHttpError: The server returned a non-2xx status.
            MalformedResponseError: The response body was not valid
                JSON or was missing expected fields.
        """
        data = self._request("GET", "/api/v1/status")
        try:
            return CommandResponse.from_dict(data)
        except ValueError as exc:
            raise MalformedResponseError(str(exc)) from exc

    def execute_command(self, request: CommandRequest) -> CommandResponse:
        """Call ``POST /api/v1/commands``.

        Args:
            request: The command to execute.

        Returns:
            The parsed CommandResponse. Note ``response.success`` may
            be ``False`` -- this is a normal, successfully-routed
            result (the underlying command failed), not an exception;
            see ``desktop/models/dto.py``'s ``CommandResponse``
            docstring and EP044_DESIGN.md Section 13.

        Raises:
            ApiNetworkError: The server could not be reached.
            ApiTimeoutError: The request timed out.
            ApiHttpError: The server returned a non-2xx status (a
                transport-level problem, e.g. malformed request,
                unknown path, or wrong Content-Type -- not the same as
                the command itself failing).
            MalformedResponseError: The response body was not valid
                JSON or was missing expected fields.
        """
        data = self._request(
            "POST",
            "/api/v1/commands",
            json_body=request.to_dict(),
        )
        try:
            return CommandResponse.from_dict(data)
        except ValueError as exc:
            raise MalformedResponseError(str(exc)) from exc

    def _request(
        self,
        method: str,
        path: str,
        json_body: dict | None = None,
    ) -> dict:
        """Perform one HTTP request and return the decoded JSON body.

        Centralizes request execution, timeout application, and
        translation of every failure mode into a typed
        ``ApiClientError`` subclass, so ``check_health``,
        ``get_status``, and ``execute_command`` never handle
        ``requests`` exceptions directly.

        Args:
            method: The HTTP method ("GET" or "POST").
            path: The request path, e.g. "/health".
            json_body: The JSON-serializable request body, for POST
                requests. Sent with an explicit
                ``Content-Type: application/json`` header (EP-043
                accepts a missing header leniently, but an explicit,
                correct header avoids relying on that leniency -- see
                EP044_DESIGN.md Section 13).

        Returns:
            The decoded JSON response body.

        Raises:
            ApiNetworkError: The server could not be reached.
            ApiTimeoutError: The request timed out.
            ApiHttpError: The server returned a non-2xx status.
            MalformedResponseError: The response body (on an
                otherwise-successful request) was not valid JSON.
        """
        url = f"{self._base_url}{path}"
        headers = {"Content-Type": "application/json"} if json_body is not None else None

        try:
            response = requests.request(
                method,
                url,
                json=json_body,
                headers=headers,
                timeout=self._timeout_seconds,
            )
        except RequestsTimeout as exc:
            raise ApiTimeoutError(
                f"Request to {url} timed out after {self._timeout_seconds} seconds."
            ) from exc
        except RequestsConnectionError as exc:
            raise ApiNetworkError(f"Could not reach Jarvis at {url}.") from exc

        if response.status_code >= 400:
            error_code, message = self._parse_error_body(response)
            raise ApiHttpError(response.status_code, message, error_code)

        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise MalformedResponseError(
                f"Jarvis returned a non-JSON response from {url}."
            ) from exc

    @staticmethod
    def _parse_error_body(response: requests.Response) -> tuple[str | None, str]:
        """Extract a safe error code/message pair from an error response.

        Matches EP-043's documented error body shape,
        ``{"error": {"code": ..., "message": ...}}``
        (``src/core/api/dto.py``'s ``ErrorPayload``). Falls back to a
        generic message if the body does not match -- never surfaces a
        raw parsing exception to the caller.

        Args:
            response: The HTTP response with a non-2xx status.

        Returns:
            A ``(error_code, message)`` tuple. ``error_code`` is
            ``None`` if the body could not be parsed as the expected
            shape.
        """
        try:
            body = response.json()
            error = body.get("error", {})
            code = error.get("code")
            message = error.get("message")
            if isinstance(code, str) and isinstance(message, str):
                return code, message
        except (json.JSONDecodeError, AttributeError):
            pass

        return None, f"Jarvis returned HTTP {response.status_code}."
