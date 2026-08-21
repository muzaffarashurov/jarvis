"""RestApiServer: the EP-043 REST API's HTTP transport component.

RestApiServer is a thin HTTP adapter, architecturally analogous to
``InteractiveShell`` (the CLI transport) and ``TelegramRouter`` (the
Telegram transport): it performs no business logic of its own. Every
request is translated into a call against ``ApiRouter``, which
dispatches through the same shared ``CommandRouter`` every other
transport already uses, so REST API behaviour can never diverge from
the CLI's.

Uses only the Python standard library (``http.server``) -- no new
third-party dependency. This mirrors the project's existing
stdlib-first precedent for a new integration EP (EP-042's EmailService
uses only ``imaplib``/``email``, no third-party IMAP client) and, per
EP043_STEP1_REPORT.md's ambiguity #6 ("framework/library"), is the
safest resolution available without a documented framework decision:
it adds zero dependency-selection risk and requires no change to
``requirements.txt``.

Endpoints (all under a fixed, minimal route table -- see ``_ROUTES``):

    GET  /health              -- liveness check, no CommandRouter call.
    GET  /api/v1/status       -- equivalent to the CLI's "system status".
    POST /api/v1/commands     -- generic command dispatch: any
                                  module/action/arguments the CLI
                                  itself could run.

Every route returns HTTP 200 for a well-formed, successfully *routed*
request -- including when the underlying command itself reports
``success=False`` (e.g. "unknown module", or a business-level
failure). The distinction between "the API call worked" and "the
command it ran succeeded" is carried in the JSON body's ``success``
field, not the HTTP status. Only REST-transport-level problems
(malformed JSON, missing required fields, an unknown path, or an
unsupported HTTP method) produce a non-2xx status. This is a
deliberate simplification, made because no design document specifies
a business-result-to-HTTP-status mapping, and because attempting one
would require per-module business knowledge inside a REST controller
-- exactly what EP-043 must avoid (see EP043_STEP2_REPORT.md, "Error
Handling", for the full rationale).

Content-Type Handling (STEP 3): ``POST /api/v1/commands`` accepts a
missing ``Content-Type`` header leniently (the body is still parsed as
JSON), but rejects a *present* ``Content-Type`` that is not
``application/json`` (parameters like ``; charset=utf-8`` are ignored)
with ``415 Unsupported Media Type``. This is deliberately simple --
no content negotiation, no support for alternate media types -- while
still catching the unambiguous case of a client explicitly declaring
an incompatible payload (see EP043_STEP3_REPORT.md, "Content-Type
Handling").
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from loguru import logger

from src.core.api.api_error import (
    ApiError,
    ApiInternalError,
    ApiMethodNotAllowedError,
    ApiNotFoundError,
    ApiUnsupportedMediaTypeError,
    ApiValidationError,
)
from src.core.api.api_router import ApiRouter
from src.core.api.dto import (
    CommandRequest,
    CommandResponse,
    ErrorPayload,
    HealthResponse,
)

__all__ = ["RestApiServer", "RestApiServerError"]

# Fixed route table: path -> set of supported HTTP methods. Centralizing
# this here lets the request handler distinguish "no such resource"
# (404) from "resource exists, wrong method" (405) without duplicating
# the path list in every do_<METHOD> handler.
_ROUTES: dict[str, set[str]] = {
    "/health": {"GET"},
    "/api/v1/status": {"GET"},
    "/api/v1/commands": {"POST"},
}


class RestApiServerError(Exception):
    """Raised when the REST API server cannot be started (e.g. the
    configured host/port could not be bound)."""


class _ApiRequestHandler(BaseHTTPRequestHandler):
    """Stdlib HTTP request handler for the EP-043 REST API.

    ``api_router`` is bound onto a dynamically created subclass by
    ``RestApiServer.start()`` (``http.server`` instantiates one
    handler object per request, with no constructor hook for extra
    dependencies, so the standard technique is a per-server subclass
    carrying the dependency as a class attribute).
    """

    api_router: ApiRouter  # bound by RestApiServer.start()

    def log_message(self, format: str, *args: Any) -> None:
        """Redirect stdlib's default stderr access log into loguru."""
        logger.debug("REST API: " + (format % args))

    # ---------- response helpers ----------

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, error: ApiError) -> None:
        self._send_json(error.status_code, ErrorPayload(error.code, str(error)).to_dict())

    def _check_content_type(self) -> None:
        """Enforce the API's Content-Type policy for a JSON request body.

        Policy (see module docstring, "Content-Type Handling"): a
        present-but-incompatible ``Content-Type`` is rejected with 415;
        an absent ``Content-Type`` is treated leniently and still
        parsed as JSON. This keeps the policy simple (no content
        negotiation) while still catching the unambiguous case of a
        client explicitly declaring a non-JSON payload.
        """
        content_type = self.headers.get("Content-Type")
        if content_type is None:
            return
        # Strip parameters, e.g. "application/json; charset=utf-8".
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            raise ApiUnsupportedMediaTypeError(
                f"Unsupported Content-Type: {content_type!r}. Expected 'application/json'."
            )

    def _read_json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError as exc:
            raise ApiValidationError("Invalid Content-Length header.") from exc

        if length == 0:
            return {}

        raw = self.rfile.read(length)
        if not raw.strip():
            return {}

        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiValidationError(f"Request body is not valid JSON: {exc}") from exc

        if not isinstance(data, dict):
            raise ApiValidationError("Request body must be a JSON object.")
        return data

    def _check_route(self, method: str) -> None:
        allowed_methods = _ROUTES.get(self.path)
        if allowed_methods is None:
            raise ApiNotFoundError(f"No such resource: {self.path}")
        if method not in allowed_methods:
            raise ApiMethodNotAllowedError(f"Method not allowed: {method} {self.path}")

    # ---------- routing ----------

    def _dispatch(self, method: str) -> None:
        try:
            self._check_route(method)

            if self.path == "/health":
                self._send_json(200, HealthResponse().to_dict())
                return

            if self.path == "/api/v1/status":
                result = self.api_router.dispatch_command("system", "status", [])
                self._send_json(200, CommandResponse.from_command_result(result).to_dict())
                return

            if self.path == "/api/v1/commands":
                self._check_content_type()
                body = self._read_json_body()
                try:
                    command_request = CommandRequest.from_dict(body)
                except ValueError as exc:
                    raise ApiValidationError(str(exc)) from exc
                result = self.api_router.dispatch_command(
                    command_request.module, command_request.action, command_request.arguments
                )
                self._send_json(200, CommandResponse.from_command_result(result).to_dict())
                return

        except ApiError as exc:
            self._send_error(exc)
        except Exception as exc:  # noqa: BLE001 - never leak a stack trace to the client
            logger.error(f"Unhandled REST API error on {method} {self.path}: {exc}")
            self._send_error(ApiInternalError("Internal server error."))

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PUT(self) -> None:
        self._dispatch("PUT")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")


class RestApiServer:
    """Owns the REST API's HTTP listener lifecycle.

    A ``ThreadingHTTPServer`` is bound and served from a dedicated
    daemon thread, so the REST API never turns ``InteractiveShell``
    (or the process's main thread) into a server loop -- the CLI and
    the REST API run fully independently, matching the Bootstrap
    architecture:

        bootstrap
         ├── Core
         ├── Services
         ├── Modules
         ├── InteractiveShell
         └── RestApiServer

    The thread is a daemon so an un-stopped server can never block
    process exit, but ``stop()`` should still be called for a clean
    shutdown (see ``Bootstrap.shutdown()``).
    """

    def __init__(self, api_router: ApiRouter, host: str = "127.0.0.1", port: int = 8080) -> None:
        """Initialize the RestApiServer without binding a socket yet.

        Args:
            api_router: The ApiRouter used to dispatch every incoming
                command request.
            host: The interface to bind to. Defaults to the loopback
                interface only -- see module docstring and
                EP043_STEP2_REPORT.md, "Security".
            port: The TCP port to bind to.
        """
        self._api_router = api_router
        self._host = host
        self._port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        """Return the configured bind host."""
        return self._host

    @property
    def port(self) -> int:
        """Return the actual bound port.

        Identical to the configured port unless the server was
        started with ``port=0`` (OS-assigned ephemeral port, used by
        this EP's own test suite to avoid port collisions), in which
        case this returns the port the OS actually assigned.
        """
        if self._httpd is not None:
            return self._httpd.server_address[1]
        return self._port

    @property
    def is_running(self) -> bool:
        """Return whether the HTTP listener is currently active."""
        return (
            self._httpd is not None
            and self._thread is not None
            and self._thread.is_alive()
        )

    def start(self) -> None:
        """Bind the configured host/port and start serving in a background thread.

        A no-op if already running.

        Raises:
            RestApiServerError: If the configured host/port could not
                be bound (e.g. the port is already in use).
        """
        if self.is_running:
            return

        # Each RestApiServer instance gets its own handler subclass so
        # `api_router` is bound per-server, not shared global state.
        handler_class = type(
            "_BoundApiRequestHandler",
            (_ApiRequestHandler,),
            {"api_router": self._api_router},
        )

        try:
            self._httpd = ThreadingHTTPServer((self._host, self._port), handler_class)
        except (OSError, TypeError, ValueError, OverflowError) as exc:
            # OSError: e.g. port already in use. TypeError/ValueError/
            # OverflowError: e.g. a malformed 'api.host'/'api.port'
            # configuration value (non-string host, non-int port, or a
            # port outside 0-65535) reaching socket.bind() -- added in
            # STEP 3 after auditing configuration robustness (see
            # EP043_STEP3_REPORT.md, "Configuration Hardening"). Both
            # cases must be recoverable, not crash Bootstrap.initialize().
            self._httpd = None
            raise RestApiServerError(
                f"Could not bind REST API server to {self._host!r}:{self._port!r}: {exc}"
            ) from exc

        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="jarvis-rest-api",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"REST API server started on http://{self._host}:{self.port}")

    def stop(self) -> None:
        """Stop serving and release the bound socket. Safe to call multiple times."""
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("REST API server stopped.")
