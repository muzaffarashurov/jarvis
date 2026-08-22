"""Real engineering tests for EP-044 STEP 2 - Desktop UI.

Single combined test suite (NAME = "EP044"), following the precedent
EP-043 established (`tests/EP043/test_rest_api.py`) of using one
suite rather than a Service/Module pair for a transport-layer EP that
introduces no Service/Module pair of its own -- EP-044's
`JarvisApiClient`/`MainWindowViewModel`/`MainWindow` are UI/transport
components, not a Core->Service->Module business subsystem, so a
single suite both accurately reflects that and sidesteps the
pre-existing `TestRegistry` NAME-collision technical debt documented
in `docs/BACKLOG.md` (not otherwise touched by this EP -- see
EP044_DESIGN.md, no-goal on unrelated technical debt).

Covers three layers, matching `desktop/`'s MVVM boundaries
(EP044_DESIGN.md Section 11) and the STEP 2 governing instructions'
required coverage (Section 20):

1. `JarvisApiClient` against a scripted local HTTP server: health/
   status/command success, business-level command failure (still
   HTTP 200), HTTP 400/404/405/415/500, connection refused, timeout,
   malformed JSON, and an unexpected response structure (missing
   fields).
2. Client-side DTOs (`desktop/models/dto.py`): serialization and
   deserialization, including invalid data.
3. `MainWindowViewModel`: initial state, connecting, successful
   request, failed request, network/transport error, command result,
   and state transitions -- exercised with a fake API client (no real
   HTTP), matching EP044_DESIGN.md's requirement that ViewModels be
   "testable independently of the GUI where possible" (Section 11).
4. One end-to-end integration check: `JarvisApiClient` against a real
   `RestApiServer`/`ApiRouter`/`CommandRouter` (the same components
   `tests/EP043/test_rest_api.py` already exercises), confirming the
   Desktop UI's client actually understands EP-043's real, as-shipped
   contract -- not only a hand-scripted approximation of it.

Qt is configured for headless (`offscreen`) operation before any
PySide6 import, per the STEP 2 governing instructions, Section 22
("configure the test environment in the least invasive way
possible") -- no CI-specific tooling or physical display is required.
"""

from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (
    QApplication,
)

from desktop.api.client_errors import (
    ApiHttpError,
    ApiNetworkError,
    ApiTimeoutError,
    MalformedResponseError,
)
from desktop.api.jarvis_api_client import JarvisApiClient
from desktop.models.dto import (
    CommandRequest,
    CommandResponse,
    HealthResponse,
)
from desktop.state.connection_state import CommandState, ConnectionState
from desktop.viewmodels.main_window_viewmodel import MainWindowViewModel
from src.core.api.api_router import ApiRouter
from src.core.api.rest_api_server import RestApiServer
from src.core.command_router import (
    CommandModule,
    CommandResult,
    CommandRouter,
)
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

# ---------- scripted fake Jarvis API server (unit-level tests) ----------


def _make_scripted_handler(script: dict):
    """Build a BaseHTTPRequestHandler class serving canned responses.

    Args:
        script: Maps ``(method, path)`` to a response spec dict with
            optional keys ``status`` (int, default 200), ``body``
            (JSON-serializable, default ``{}``), ``raw_body`` (bytes,
            overrides ``body`` -- used to send deliberately malformed
            JSON), and ``delay`` (float seconds to sleep before
            responding -- used to simulate a slow server for timeout
            tests).
    """

    class _ScriptedHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Silence request logging; keeps test output clean.

        def _respond(self, method: str) -> None:
            spec = script.get((method, self.path))
            if spec is None:
                self.send_response(404)
                self.end_headers()
                return

            delay = spec.get("delay", 0.0)
            if delay:
                time.sleep(delay)

            status = spec.get("status", 200)
            body = spec.get("raw_body")
            if body is None:
                body = json.dumps(spec.get("body", {})).encode("utf-8")

            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                # The client (deliberately, in the timeout test) may have
                # already given up and closed its socket by the time a
                # delayed response is written. Not a test failure -- the
                # client-side timeout is what the timeout test asserts.
                #
                # BrokenPipeError, ConnectionAbortedError, and
                # ConnectionResetError are sibling subclasses of
                # ConnectionError (none is a subclass of another), each
                # representing the identical "peer already closed the
                # connection" condition surfaced differently depending on
                # platform and OS socket stack: POSIX/Linux typically
                # raises BrokenPipeError (EPIPE) here, while Windows raises
                # ConnectionAbortedError (WSAECONNABORTED / WinError 10053)
                # for the same scenario. ConnectionResetError (ECONNRESET)
                # is included as the third platform-dependent manifestation
                # of the same condition. This is a standard library
                # behavior difference present since Python 3.3 (PEP 3151),
                # not specific to any particular Python version.
                pass

        def do_GET(self) -> None:
            self._respond("GET")

        def do_POST(self) -> None:
            content_length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(content_length)
            self._respond("POST")

    return _ScriptedHandler


class _ScriptedServer:
    """A running scripted HTTP server on an OS-assigned ephemeral port."""

    def __init__(self, script: dict) -> None:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), _make_scripted_handler(script))
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        host, port = self._httpd.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def port(self) -> int:
        return self._httpd.server_address[1]

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)


# ---------- fake API client (ViewModel-level tests) ----------


class _FakeApiClient:
    """Duck-typed stand-in for JarvisApiClient -- no real HTTP calls.

    Each method is a configurable callable, injected per test, so
    MainWindowViewModel tests are deterministic and independent of
    both the network and JarvisApiClient's own implementation.
    """

    def __init__(self, check_health=None, get_status=None, execute_command=None) -> None:
        self._check_health = check_health
        self._get_status = get_status
        self._execute_command = execute_command

    def check_health(self):
        return self._check_health()

    def get_status(self):
        return self._get_status()

    def execute_command(self, request: CommandRequest):
        return self._execute_command(request)


# ---------- Qt event loop pumping helper ----------


def _pump_until(app: QApplication, predicate, timeout_seconds: float = 5.0) -> bool:
    """Process Qt events until ``predicate()`` is True or timeout expires.

    Needed because ApiWorker delivers its result via a queued signal
    connection, which requires the Qt event loop to run at least once
    to be dispatched -- these tests never call ``app.exec()``, so
    events must be pumped manually.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


# ---------- minimal echo module for the real-server integration check ----------


class _EchoModule(CommandModule):
    NAME = "echo"

    @property
    def name(self) -> str:
        return self.NAME

    def execute(self, command: str, args: list[str]) -> CommandResult:
        return CommandResult(success=True, message=" ".join(args))


@TestRegistry.register
class DesktopUiTest(BaseTest):
    NAME = "EP044"

    def run(self):
        self._app = QApplication.instance() or QApplication([])

        # --- API client: success paths ---
        self._test_check_health_success()
        self._test_get_status_success()
        self._test_execute_command_success()
        self._test_execute_command_business_failure_is_not_an_exception()

        # --- API client: transport-level HTTP errors ---
        self._test_execute_command_http_400()
        self._test_execute_command_http_404()
        self._test_execute_command_http_405()
        self._test_execute_command_http_415()
        self._test_execute_command_http_500()

        # --- API client: network-level failures ---
        self._test_connection_refused()
        self._test_timeout()
        self._test_malformed_json_response()
        self._test_unexpected_response_structure()

        # --- DTOs ---
        self._test_command_request_to_dict()
        self._test_command_response_from_dict_valid()
        self._test_command_response_from_dict_invalid_missing_field()
        self._test_command_response_from_dict_invalid_wrong_type()
        self._test_health_response_from_dict_valid()
        self._test_health_response_from_dict_invalid()

        # --- ViewModel ---
        self._test_viewmodel_initial_state()
        self._test_viewmodel_check_health_transitions_through_connecting()
        self._test_viewmodel_check_health_success()
        self._test_viewmodel_check_health_failure()
        self._test_viewmodel_execute_command_success()
        self._test_viewmodel_execute_command_business_failure()
        self._test_viewmodel_execute_command_transport_error()

        # --- Real EP-043 server integration ---
        self._test_real_server_health_and_status()
        self._test_real_server_command_round_trip()

        return self.result

    # ---------- API client: success paths ----------

    def _test_check_health_success(self) -> None:
        server = _ScriptedServer({("GET", "/health"): {"body": {"status": "ok"}}})
        try:
            client = JarvisApiClient(server.base_url)
            result = client.check_health()
            self.assert_equal(result.status, "ok")
        finally:
            server.stop()

    def _test_get_status_success(self) -> None:
        server = _ScriptedServer(
            {("GET", "/api/v1/status"): {"body": {"success": True, "message": "running"}}}
        )
        try:
            client = JarvisApiClient(server.base_url)
            result = client.get_status()
            self.assert_true(result.success)
            self.assert_equal(result.message, "running")
        finally:
            server.stop()

    def _test_execute_command_success(self) -> None:
        server = _ScriptedServer(
            {("POST", "/api/v1/commands"): {"body": {"success": True, "message": "hi"}}}
        )
        try:
            client = JarvisApiClient(server.base_url)
            result = client.execute_command(CommandRequest(module="echo", action="say", arguments=["hi"]))
            self.assert_true(result.success)
            self.assert_equal(result.message, "hi")
        finally:
            server.stop()

    def _test_execute_command_business_failure_is_not_an_exception(self) -> None:
        server = _ScriptedServer(
            {("POST", "/api/v1/commands"): {"body": {"success": False, "message": "Unknown module"}}}
        )
        try:
            client = JarvisApiClient(server.base_url)
            result = client.execute_command(CommandRequest(module="does_not_exist"))
            self.assert_false(result.success)
            self.assert_equal(result.message, "Unknown module")
        finally:
            server.stop()

    # ---------- API client: transport-level HTTP errors ----------

    def _test_execute_command_http_400(self) -> None:
        self._assert_http_error_raised(400, "validation_error")

    def _test_execute_command_http_404(self) -> None:
        self._assert_http_error_raised(404, "not_found")

    def _test_execute_command_http_405(self) -> None:
        self._assert_http_error_raised(405, "method_not_allowed")

    def _test_execute_command_http_415(self) -> None:
        self._assert_http_error_raised(415, "unsupported_media_type")

    def _test_execute_command_http_500(self) -> None:
        self._assert_http_error_raised(500, "internal_error")

    def _assert_http_error_raised(self, status: int, error_code: str) -> None:
        server = _ScriptedServer(
            {
                ("POST", "/api/v1/commands"): {
                    "status": status,
                    "body": {"error": {"code": error_code, "message": f"error {status}"}},
                }
            }
        )
        try:
            client = JarvisApiClient(server.base_url)
            try:
                client.execute_command(CommandRequest(module="x"))
                self.assert_true(False, f"Expected ApiHttpError for status {status}")
            except ApiHttpError as exc:
                self.assert_equal(exc.status_code, status)
                self.assert_equal(exc.error_code, error_code)
        finally:
            server.stop()

    # ---------- API client: network-level failures ----------

    def _test_connection_refused(self) -> None:
        # Start a server to obtain a genuinely free ephemeral port, then
        # stop it -- nothing listens on that port afterward, so the
        # connection attempt is refused deterministically.
        server = _ScriptedServer({})
        base_url = server.base_url
        server.stop()

        client = JarvisApiClient(base_url)
        try:
            client.check_health()
            self.assert_true(False, "Expected ApiNetworkError")
        except ApiNetworkError:
            self.result.add_pass()

    def _test_timeout(self) -> None:
        server = _ScriptedServer({("GET", "/health"): {"body": {"status": "ok"}, "delay": 0.3}})
        try:
            client = JarvisApiClient(server.base_url, timeout_seconds=0.05)
            try:
                client.check_health()
                self.assert_true(False, "Expected ApiTimeoutError")
            except ApiTimeoutError:
                self.result.add_pass()
        finally:
            server.stop()

    def _test_malformed_json_response(self) -> None:
        server = _ScriptedServer({("GET", "/health"): {"raw_body": b"{not valid json"}})
        try:
            client = JarvisApiClient(server.base_url)
            try:
                client.check_health()
                self.assert_true(False, "Expected MalformedResponseError")
            except MalformedResponseError:
                self.result.add_pass()
        finally:
            server.stop()

    def _test_unexpected_response_structure(self) -> None:
        server = _ScriptedServer({("GET", "/health"): {"body": {"unexpected": "shape"}}})
        try:
            client = JarvisApiClient(server.base_url)
            try:
                client.check_health()
                self.assert_true(False, "Expected MalformedResponseError")
            except MalformedResponseError:
                self.result.add_pass()
        finally:
            server.stop()

    # ---------- DTOs ----------

    def _test_command_request_to_dict(self) -> None:
        request = CommandRequest(module="system", action="status", arguments=["a", "b"])
        self.assert_equal(
            request.to_dict(),
            {"module": "system", "action": "status", "arguments": ["a", "b"]},
        )

    def _test_command_response_from_dict_valid(self) -> None:
        response = CommandResponse.from_dict({"success": True, "message": "ok"})
        self.assert_true(response.success)
        self.assert_equal(response.message, "ok")

    def _test_command_response_from_dict_invalid_missing_field(self) -> None:
        try:
            CommandResponse.from_dict({"success": True})
            self.assert_true(False, "Expected ValueError for missing 'message'")
        except ValueError:
            self.result.add_pass()

    def _test_command_response_from_dict_invalid_wrong_type(self) -> None:
        try:
            CommandResponse.from_dict({"success": "yes", "message": "ok"})
            self.assert_true(False, "Expected ValueError for non-bool 'success'")
        except ValueError:
            self.result.add_pass()

    def _test_health_response_from_dict_valid(self) -> None:
        response = HealthResponse.from_dict({"status": "ok"})
        self.assert_equal(response.status, "ok")

    def _test_health_response_from_dict_invalid(self) -> None:
        try:
            HealthResponse.from_dict({})
            self.assert_true(False, "Expected ValueError for missing 'status'")
        except ValueError:
            self.result.add_pass()

    # ---------- ViewModel ----------

    def _test_viewmodel_initial_state(self) -> None:
        view_model = MainWindowViewModel(_FakeApiClient())
        self.assert_equal(view_model.connection_state, ConnectionState.DISCONNECTED)
        self.assert_equal(view_model.command_state, CommandState.IDLE)

    def _test_viewmodel_check_health_transitions_through_connecting(self) -> None:
        client = _FakeApiClient(check_health=lambda: HealthResponse(status="ok"))
        view_model = MainWindowViewModel(client)

        view_model.check_health()
        # Immediately after calling, before the worker thread has had a
        # chance to run, state must already be CONNECTING.
        self.assert_equal(view_model.connection_state, ConnectionState.CONNECTING)

        completed = _pump_until(
            self._app, lambda: view_model.connection_state != ConnectionState.CONNECTING
        )
        self.assert_true(completed, "Timed out waiting for check_health() to complete")

    def _test_viewmodel_check_health_success(self) -> None:
        client = _FakeApiClient(check_health=lambda: HealthResponse(status="ok"))
        view_model = MainWindowViewModel(client)

        received: list[HealthResponse] = []
        view_model.health_result.connect(received.append)

        view_model.check_health()
        completed = _pump_until(self._app, lambda: len(received) == 1)

        self.assert_true(completed, "Timed out waiting for health_result signal")
        self.assert_equal(view_model.connection_state, ConnectionState.CONNECTED)
        self.assert_equal(received[0].status, "ok")

    def _test_viewmodel_check_health_failure(self) -> None:
        def raise_network_error():
            raise ApiNetworkError("unreachable")

        client = _FakeApiClient(check_health=raise_network_error)
        view_model = MainWindowViewModel(client)

        errors: list[Exception] = []
        view_model.error_occurred.connect(errors.append)

        view_model.check_health()
        completed = _pump_until(self._app, lambda: len(errors) == 1)

        self.assert_true(completed, "Timed out waiting for error_occurred signal")
        self.assert_equal(view_model.connection_state, ConnectionState.API_UNAVAILABLE)
        self.assert_true(isinstance(errors[0], ApiNetworkError))

    def _test_viewmodel_execute_command_success(self) -> None:
        client = _FakeApiClient(execute_command=lambda req: CommandResponse(success=True, message="done"))
        view_model = MainWindowViewModel(client)

        received: list[CommandResponse] = []
        view_model.command_result.connect(received.append)

        view_model.execute_command("system", "status", [])
        self.assert_equal(view_model.command_state, CommandState.REQUEST_IN_PROGRESS)

        completed = _pump_until(self._app, lambda: len(received) == 1)
        self.assert_true(completed, "Timed out waiting for command_result signal")
        self.assert_equal(view_model.command_state, CommandState.SUCCEEDED)
        self.assert_equal(received[0].message, "done")

    def _test_viewmodel_execute_command_business_failure(self) -> None:
        client = _FakeApiClient(
            execute_command=lambda req: CommandResponse(success=False, message="unknown module")
        )
        view_model = MainWindowViewModel(client)

        received: list[CommandResponse] = []
        view_model.command_result.connect(received.append)

        view_model.execute_command("bogus", "", [])
        completed = _pump_until(self._app, lambda: len(received) == 1)

        self.assert_true(completed, "Timed out waiting for command_result signal")
        self.assert_equal(view_model.command_state, CommandState.FAILED)
        self.assert_false(received[0].success)

    def _test_viewmodel_execute_command_transport_error(self) -> None:
        def raise_timeout():
            raise ApiTimeoutError("timed out")

        client = _FakeApiClient(execute_command=lambda req: raise_timeout())
        view_model = MainWindowViewModel(client)

        errors: list[Exception] = []
        view_model.error_occurred.connect(errors.append)

        view_model.execute_command("system", "status", [])
        completed = _pump_until(self._app, lambda: len(errors) == 1)

        self.assert_true(completed, "Timed out waiting for error_occurred signal")
        self.assert_equal(view_model.command_state, CommandState.ERROR)
        self.assert_true(isinstance(errors[0], ApiTimeoutError))

    # ---------- Real EP-043 server integration ----------

    def _start_real_server(self) -> tuple[RestApiServer, str]:
        router = CommandRouter()
        router.register(_EchoModule())
        api_router = ApiRouter(command_router=router)
        server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)
        server.start()
        return server, f"http://127.0.0.1:{server.port}"

    def _test_real_server_health_and_status(self) -> None:
        server, base_url = self._start_real_server()
        try:
            client = JarvisApiClient(base_url)
            health = client.check_health()
            self.assert_equal(health.status, "ok")

            status = client.get_status()
            self.assert_true(isinstance(status, CommandResponse))
        finally:
            server.stop()

    def _test_real_server_command_round_trip(self) -> None:
        server, base_url = self._start_real_server()
        try:
            client = JarvisApiClient(base_url)
            result = client.execute_command(CommandRequest(module="echo", action="say", arguments=["hello desktop"]))
            self.assert_true(result.success)
            self.assert_equal(result.message, "hello desktop")
        finally:
            server.stop()
