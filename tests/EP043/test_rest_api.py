"""Real engineering tests for EP-043 STEP 2 - REST API.

Single combined test suite (NAME = "EP043") rather than a
Service/Module pair, deliberately avoiding the pre-existing
`TestRegistry` NAME-collision technical debt documented in
docs/BACKLOG.md and docs/architecture/audits/EP042_ARCHITECTURE_AUDIT.md
(only one of two same-NAME suites is reachable via the CLI `test
EP0NN` command). EP-043 introduces no Service/Module pair -- ApiRouter
and RestApiServer are transport-layer components, analogous to
TelegramRouter/InteractiveShell, not a Core->Service->Module business
subsystem -- so a single suite is both accurate and sufficient, and
sidesteps the collision entirely (matching tests/EP037/test_event_bus.py's
single-suite precedent for a similarly non-Service/Module EP).

Covers:

1. ApiRouter: dispatches (module, action, arguments) to a real
   CommandRouter unchanged, including arguments containing spaces
   (shell-quoting round-trip).
2. RestApiServer, bound to an OS-assigned ephemeral port
   (host="127.0.0.1", port=0) to avoid any port collision with other
   test runs: GET /health, GET /api/v1/status, POST /api/v1/commands
   (valid request, business-level failure still returns HTTP 200 with
   success=false in the body, malformed JSON, missing 'module'),
   unknown path (404), and wrong method on a known path (405).
3. Real Bootstrap wiring: 'api.enabled: true' starts a running
   RestApiServer; 'api.enabled: false' (and an entirely absent 'api'
   section) leaves it at None with nothing bound.
4. InteractiveShell continues to work independently of the REST API
   (same CommandRouter, unaffected by RestApiServer's presence).
5. `Bootstrap.shutdown()` cleanly stops a running RestApiServer and is
   safe to call when nothing was started.

No real Discord/GitHub/Telegram/Email network call is made -- every
'*.enabled' flag other than 'api' is left at its safe test default in
the config template below.
"""

from __future__ import annotations

import http.client
import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.api.api_router import ApiRouter
from src.core.api.rest_api_server import RestApiServer
from src.core.command_router import CommandRouter
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


class _ChdirGuard:
    """Context manager: chdir into `directory`, always restoring the original cwd."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._original = Path.cwd()

    def __enter__(self) -> Path:
        os.chdir(self._directory)
        return self._directory

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        os.chdir(self._original)


_FULL_BOOTSTRAP_CONFIG_YAML = (
    "app:\n"
    "  name: \"JARVIS-TEST\"\n"
    "  tagline: \"Test\"\n"
    "  version: \"0.0.0-test\"\n\n"
    "logging:\n"
    "  level: \"INFO\"\n"
    "  retention_days: 1\n"
    "  console_enabled: false\n\n"
    "paths:\n"
    "  logs: \"logs\"\n"
    "  data_input: \"data/input\"\n"
    "  data_output: \"data/output\"\n"
    "  data_cache: \"data/cache\"\n"
    "  data_database: \"data/database\"\n"
    "  knowledge: \"knowledge\"\n"
    "  prompts: \"prompts\"\n\n"
    "memory:\n"
    "  enabled: true\n"
    "  persistent: false\n"
    "  auto_save: false\n"
    "  max_entries: 10000\n"
    "  default_ttl: null\n"
    "  default_provider: \"memory\"\n\n"
    "knowledge:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n\n"
    "long_term_memory:\n"
    "  enabled: true\n"
    "  default_provider: \"knowledge\"\n\n"
    "orchestrator:\n"
    "  skills_enabled: []\n\n"
    "invoice:\n"
    "  script: \"\"\n\n"
    "fast_response:\n"
    "  workbook: \"\"\n"
    "  worksheet: \"\"\n"
    "  backup_folder: \"\"\n\n"
    "workflows:\n"
    "  enabled: true\n"
    "  auto_register: true\n\n"
    "processes:\n"
    "  auto_start: false\n"
    "  dependency_check: true\n"
    "  health_check_interval: 60\n\n"
    "scheduler:\n"
    "  enabled: true\n"
    "  auto_start: false\n"
    "  tick_interval: 1\n\n"
    "plugins:\n"
    "  enabled: true\n"
    "  auto_load: false\n"
    "  auto_discovery: false\n"
    "  plugin_directory: \"plugins\"\n\n"
    "telegram:\n"
    "  enabled: false\n"
    "  auto_start: false\n"
    "  token: \"\"\n"
    "  allowed_chat_ids: []\n"
    "  polling_interval: 2\n\n"
    "ai:\n"
    "  enabled: true\n"
    "  default_provider: \"none\"\n"
    "  timeout: 120\n"
    "  retry_count: 2\n"
    "  max_context_messages: 20\n\n"
    "conversation:\n"
    "  enabled: true\n"
    "  auto_save: false\n"
    "  max_messages: 100\n"
    "  max_conversations: 100\n"
    "  storage_file: \"data/database/conversations.json\"\n"
    "  truncate_strategy: \"oldest\"\n\n"
    "prompt:\n"
    "  enabled: true\n"
    "  system_prompt: \"\"\n"
    "  append_datetime: false\n"
    "  append_provider_name: false\n"
    "  append_os_information: false\n"
    "  append_working_directory: false\n"
    "  include_working_directory: false\n"
    "  include_project_files: false\n"
    "  smart_selection: true\n\n"
    "indexing:\n"
    "  storage_backend: \"memory\"\n"
    "  storage_file: \"data/database/project_index.json\"\n\n"
    "providers:\n"
    "  claude:\n"
    "    enabled: false\n"
    "    api_key: \"\"\n"
    "  openai:\n"
    "    enabled: false\n"
    "    api_key: \"\"\n"
    "  gemini:\n"
    "    enabled: false\n"
    "    api_key: \"\"\n"
    "  ollama:\n"
    "    enabled: false\n"
    "    endpoint: \"\"\n"
    "  lmstudio:\n"
    "    enabled: false\n"
    "    endpoint: \"\"\n\n"
    "embedding:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n"
    "  batch_size: 16\n"
    "  providers:\n"
    "    local:\n"
    "      enabled: true\n"
    "      model: \"local-hash-v1\"\n"
    "      dimension: 16\n"
    "    cloud:\n"
    "      enabled: false\n"
    "      api_key: \"\"\n"
    "      model: \"text-embedding-cloud-v1\"\n"
    "      dimension: 1536\n\n"
    "rag:\n"
    "  enabled: true\n"
    "  top_k: 5\n"
    "  max_context_characters: 4000\n\n"
    "semantic:\n"
    "  enabled: true\n"
    "  default_provider: \"semantic\"\n"
    "  top_k: 5\n"
    "  similarity_threshold: 0.0\n\n"
    "context_compression:\n"
    "  enabled: true\n"
    "  default_provider: \"compression\"\n"
    "  max_context_characters: 12000\n"
    "  max_chunks: 20\n"
    "  deduplicate: true\n\n"
    "agent:\n"
    "  enabled: true\n"
    "  default_agent: \"jarvis\"\n"
    "  startup_mode: \"idle\"\n\n"
    "planning:\n"
    "  enabled: true\n"
    "  default_provider: \"planning\"\n"
    "  max_steps: 10\n\n"
    "plan_execution:\n"
    "  enabled: true\n"
    "  default_provider: \"plan_execution\"\n"
    "  stop_on_failure: true\n\n"
    "tool:\n"
    "  enabled: true\n"
    "  default_provider: \"tool_engine\"\n\n"
    "collaboration:\n"
    "  enabled: true\n"
    "  default_provider: \"collaboration\"\n\n"
    "workflow_engine:\n"
    "  enabled: true\n"
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: true\n\n"
    "workflow_scheduler:\n"
    "  enabled: true\n"
    "  auto_start: false\n"
    "  tick_interval: 5\n\n"
    "automation:\n"
    "  enabled: true\n\n"
    "git:\n"
    "  enabled: false\n\n"
    "github:\n"
    "  enabled: false\n\n"
    "telegram_info:\n"
    "  enabled: false\n\n"
    "discord:\n"
    "  enabled: false\n\n"
    "email:\n"
    "  enabled: false\n\n"
    "{api_section}"
)


def _write_full_bootstrap_config(directory: Path, api_section: str) -> None:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(api_section=api_section),
        encoding="utf-8",
    )


_API_ENABLED_SECTION = 'api:\n  enabled: true\n  host: "127.0.0.1"\n  port: 0\n'
_API_DISABLED_SECTION = "api:\n  enabled: false\n  host: \"127.0.0.1\"\n  port: 0\n"
_API_ABSENT_SECTION = ""  # no 'api' section at all -- must default safely


def _http_get(base_url: str, path: str) -> tuple[int, dict]:
    request = urllib.request.Request(base_url + path, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _http_post(base_url: str, path: str, body: bytes | None, content_type: str = "application/json") -> tuple[int, dict]:
    request = urllib.request.Request(
        base_url + path, data=body, method="POST", headers={"Content-Type": content_type}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _http_post_without_content_type(host: str, port: int, path: str, body: bytes) -> tuple[int, dict]:
    """POST with no Content-Type header at all.

    `urllib.request` always attaches a default Content-Type
    ("application/x-www-form-urlencoded") whenever a body is given, so
    it cannot be used to test genuine header absence. This helper
    talks HTTP/1.1 directly via `http.client` to omit the header
    entirely -- exercising the real leniency path documented in
    rest_api_server.py's "Content-Type Handling" section.
    """
    connection = http.client.HTTPConnection(host, port, timeout=5)
    try:
        connection.putrequest("POST", path, skip_accept_encoding=True)
        connection.putheader("Content-Length", str(len(body)))
        connection.endheaders()
        connection.send(body)
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


@TestRegistry.register
class RestApiTest(BaseTest):
    NAME = "EP043"

    def run(self):
        self._test_api_router_dispatches_to_command_router()
        self._test_api_router_quotes_arguments_with_spaces()

        self._test_health_endpoint()
        self._test_status_endpoint()
        self._test_commands_endpoint_valid_request()
        self._test_commands_endpoint_business_failure_still_200()
        self._test_commands_endpoint_malformed_json()
        self._test_commands_endpoint_missing_module()
        self._test_unknown_path_returns_404()
        self._test_wrong_method_returns_405()
        self._test_server_start_is_idempotent()
        self._test_server_stop_then_restart()

        # --- STEP 3: contract hardening ---
        self._test_commands_endpoint_wrong_content_type_returns_415()
        self._test_commands_endpoint_json_content_type_with_charset_ok()
        self._test_commands_endpoint_missing_content_type_is_lenient()
        self._test_commands_endpoint_empty_body_treated_as_empty_object()
        self._test_commands_endpoint_unexpected_fields_ignored()
        self._test_commands_endpoint_wrong_field_types_rejected()
        self._test_health_endpoint_does_not_touch_command_router()
        self._test_status_endpoint_uses_command_response_dto_only()
        self._test_repeated_start_stop_cycles_leave_no_leaks()
        self._test_invalid_port_type_does_not_crash_bootstrap()
        self._test_invalid_port_range_does_not_crash_bootstrap()
        self._test_external_client_contract_round_trip()

        self._test_bootstrap_starts_rest_api_when_enabled()
        self._test_bootstrap_skips_rest_api_when_disabled()
        self._test_bootstrap_skips_rest_api_when_config_absent()
        self._test_bootstrap_shutdown_stops_server()
        self._test_bootstrap_shutdown_safe_when_nothing_started()
        self._test_interactive_shell_unaffected_by_rest_api()

        return self.result

    # ---------- ApiRouter ----------

    def _test_api_router_dispatches_to_command_router(self) -> None:
        router = CommandRouter()
        router.register(_EchoModule())
        api_router = ApiRouter(command_router=router)

        result = api_router.dispatch_command("echo", "say", ["hello"])
        self.assert_true(result.success)
        self.assert_equal(result.message, "hello")

    def _test_api_router_quotes_arguments_with_spaces(self) -> None:
        router = CommandRouter()
        router.register(_EchoModule())
        api_router = ApiRouter(command_router=router)

        result = api_router.dispatch_command("echo", "say", ["hello world"])
        self.assert_true(result.success)
        self.assert_equal(result.message, "hello world")

    # ---------- RestApiServer over real HTTP ----------

    def _test_health_endpoint(self) -> None:
        server, base_url = self._start_test_server()
        try:
            status, payload = _http_get(base_url, "/health")
            self.assert_equal(status, 200)
            self.assert_equal(payload.get("status"), "ok")
        finally:
            server.stop()

    def _test_status_endpoint(self) -> None:
        server, base_url = self._start_test_server()
        try:
            status, payload = _http_get(base_url, "/api/v1/status")
            self.assert_equal(status, 200)
            self.assert_true("success" in payload)
            self.assert_true("message" in payload)
        finally:
            server.stop()

    def _test_commands_endpoint_valid_request(self) -> None:
        server, base_url = self._start_test_server()
        try:
            body = json.dumps({"module": "echo", "action": "say", "arguments": ["hi"]}).encode("utf-8")
            status, payload = _http_post(base_url, "/api/v1/commands", body)
            self.assert_equal(status, 200)
            self.assert_true(payload.get("success"))
            self.assert_equal(payload.get("message"), "hi")
        finally:
            server.stop()

    def _test_commands_endpoint_business_failure_still_200(self) -> None:
        server, base_url = self._start_test_server()
        try:
            body = json.dumps({"module": "nonexistent_module", "action": "x"}).encode("utf-8")
            status, payload = _http_post(base_url, "/api/v1/commands", body)
            # Transport-level success (the request was well-formed and
            # routed) is 200 even though the underlying command itself
            # failed -- see rest_api_server.py's module docstring.
            self.assert_equal(status, 200)
            self.assert_false(payload.get("success"))
        finally:
            server.stop()

    def _test_commands_endpoint_malformed_json(self) -> None:
        server, base_url = self._start_test_server()
        try:
            status, payload = _http_post(base_url, "/api/v1/commands", b"{not valid json")
            self.assert_equal(status, 400)
            self.assert_equal(payload.get("error", {}).get("code"), "validation_error")
        finally:
            server.stop()

    def _test_commands_endpoint_missing_module(self) -> None:
        server, base_url = self._start_test_server()
        try:
            body = json.dumps({"action": "say"}).encode("utf-8")
            status, payload = _http_post(base_url, "/api/v1/commands", body)
            self.assert_equal(status, 400)
            self.assert_equal(payload.get("error", {}).get("code"), "validation_error")
        finally:
            server.stop()

    def _test_unknown_path_returns_404(self) -> None:
        server, base_url = self._start_test_server()
        try:
            status, payload = _http_get(base_url, "/api/v1/does-not-exist")
            self.assert_equal(status, 404)
            self.assert_equal(payload.get("error", {}).get("code"), "not_found")
        finally:
            server.stop()

    def _test_wrong_method_returns_405(self) -> None:
        server, base_url = self._start_test_server()
        try:
            status, payload = _http_get(base_url, "/api/v1/commands")
            self.assert_equal(status, 405)
            self.assert_equal(payload.get("error", {}).get("code"), "method_not_allowed")
        finally:
            server.stop()

    # ---------- STEP 3: Content-Type policy ----------

    def _test_commands_endpoint_wrong_content_type_returns_415(self) -> None:
        server, base_url = self._start_test_server()
        try:
            body = json.dumps({"module": "echo", "action": "say", "arguments": ["hi"]}).encode("utf-8")
            status, payload = _http_post(base_url, "/api/v1/commands", body, content_type="text/plain")
            self.assert_equal(status, 415)
            self.assert_equal(payload.get("error", {}).get("code"), "unsupported_media_type")
        finally:
            server.stop()

    def _test_commands_endpoint_json_content_type_with_charset_ok(self) -> None:
        server, base_url = self._start_test_server()
        try:
            body = json.dumps({"module": "echo", "action": "say", "arguments": ["hi"]}).encode("utf-8")
            status, payload = _http_post(
                base_url, "/api/v1/commands", body, content_type="application/json; charset=utf-8"
            )
            self.assert_equal(status, 200)
            self.assert_true(payload.get("success"))
        finally:
            server.stop()

    def _test_commands_endpoint_missing_content_type_is_lenient(self) -> None:
        server, _base_url = self._start_test_server()
        try:
            body = json.dumps({"module": "echo", "action": "say", "arguments": ["hi"]}).encode("utf-8")
            status, payload = _http_post_without_content_type(
                "127.0.0.1", server.port, "/api/v1/commands", body
            )
            self.assert_equal(status, 200)
            self.assert_true(payload.get("success"))
        finally:
            server.stop()

    # ---------- STEP 3: request/response contract stability ----------

    def _test_commands_endpoint_empty_body_treated_as_empty_object(self) -> None:
        server, base_url = self._start_test_server()
        try:
            status, payload = _http_post(base_url, "/api/v1/commands", b"")
            # Empty body -> {} -> fails validation (module required), not
            # a JSON parse error or an internal error.
            self.assert_equal(status, 400)
            self.assert_equal(payload.get("error", {}).get("code"), "validation_error")
        finally:
            server.stop()

    def _test_commands_endpoint_unexpected_fields_ignored(self) -> None:
        server, base_url = self._start_test_server()
        try:
            body = json.dumps(
                {
                    "module": "echo",
                    "action": "say",
                    "arguments": ["hi"],
                    "unexpected_field": "some-future-client-field",
                }
            ).encode("utf-8")
            status, payload = _http_post(base_url, "/api/v1/commands", body)
            # Documented, deliberate leniency: unknown fields are
            # ignored rather than rejected, for forward compatibility
            # with future clients -- see EP043_STEP3_REPORT.md.
            self.assert_equal(status, 200)
            self.assert_true(payload.get("success"))
        finally:
            server.stop()

    def _test_commands_endpoint_wrong_field_types_rejected(self) -> None:
        server, base_url = self._start_test_server()
        try:
            body = json.dumps({"module": "echo", "action": "say", "arguments": "not-a-list"}).encode("utf-8")
            status, payload = _http_post(base_url, "/api/v1/commands", body)
            self.assert_equal(status, 400)
            self.assert_equal(payload.get("error", {}).get("code"), "validation_error")
        finally:
            server.stop()

    def _test_health_endpoint_does_not_touch_command_router(self) -> None:
        # A CommandRouter with nothing registered: if /health ever
        # started dispatching a command, this would surface as a
        # business failure in the response. It must not.
        router = CommandRouter()
        api_router = ApiRouter(command_router=router)
        server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)
        server.start()
        try:
            status, payload = _http_get(f"http://127.0.0.1:{server.port}", "/health")
            self.assert_equal(status, 200)
            self.assert_equal(payload, {"status": "ok"})
        finally:
            server.stop()

    def _test_status_endpoint_uses_command_response_dto_only(self) -> None:
        server, base_url = self._start_test_server()
        try:
            status, payload = _http_get(base_url, "/api/v1/status")
            self.assert_equal(status, 200)
            # Stable, minimal contract: exactly {success, message} --
            # no internal CommandResult/Python object fields leak
            # through (e.g. no 'should_exit', no class name, no
            # tracebacks).
            self.assert_equal(set(payload.keys()), {"success", "message"})
            self.assert_true(isinstance(payload["success"], bool))
            self.assert_true(isinstance(payload["message"], str))
        finally:
            server.stop()

    # ---------- STEP 3: lifecycle robustness ----------

    def _test_repeated_start_stop_cycles_leave_no_leaks(self) -> None:
        import threading

        router = CommandRouter()
        api_router = ApiRouter(command_router=router)
        server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)

        threads_before = {t.ident for t in threading.enumerate()}
        for _ in range(5):
            server.start()
            self.assert_true(server.is_running)
            status, _ = _http_get(f"http://127.0.0.1:{server.port}", "/health")
            self.assert_equal(status, 200)
            server.stop()
            self.assert_false(server.is_running)

        threads_after = {t.ident for t in threading.enumerate()}
        # No jarvis-rest-api threads should remain alive after the
        # final stop() -- every started thread must have been joined.
        leaked = [
            t
            for t in threading.enumerate()
            if t.name == "jarvis-rest-api" and t.ident in (threads_after - threads_before)
        ]
        self.assert_equal(leaked, [])

    def _test_invalid_port_type_does_not_crash_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory, 'api:\n  enabled: true\n  host: "127.0.0.1"\n  port: "not-a-port"\n'
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    # Must not raise: an invalid 'api.port' degrades to
                    # "REST API disabled", it must not crash startup.
                    bootstrap.initialize()
                    self.assert_true(bootstrap.rest_api_server is None)
                finally:
                    bootstrap.shutdown()

    def _test_invalid_port_range_does_not_crash_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory, 'api:\n  enabled: true\n  host: "127.0.0.1"\n  port: 99999\n'
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.rest_api_server is None)
                finally:
                    bootstrap.shutdown()

    # ---------- STEP 3: external client contract ----------

    def _test_external_client_contract_round_trip(self) -> None:
        """Behaves like a real external client: start, call, parse, assert, shut down.

        Exercises the full contract a future Web UI would depend on,
        without any Jarvis-internal knowledge -- only the documented
        JSON shapes from EP043_DESIGN.md.
        """
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, _API_ENABLED_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    server = bootstrap.rest_api_server
                    self.assert_true(server is not None and server.is_running)
                    base_url = f"http://127.0.0.1:{server.port}"

                    # 1. Liveness check, as a client would do before anything else.
                    status, health = _http_get(base_url, "/health")
                    self.assert_equal(status, 200)
                    self.assert_equal(health.get("status"), "ok")

                    # 2. Ask Jarvis for its status.
                    status, status_payload = _http_get(base_url, "/api/v1/status")
                    self.assert_equal(status, 200)
                    self.assert_true("success" in status_payload)

                    # 3. Issue a real command through the public contract only.
                    request_body = json.dumps(
                        {"module": "system", "action": "version", "arguments": []}
                    ).encode("utf-8")
                    status, command_payload = _http_post(base_url, "/api/v1/commands", request_body)
                    self.assert_equal(status, 200)
                    self.assert_true(command_payload.get("success"))
                    self.assert_true(isinstance(command_payload.get("message"), str))
                finally:
                    # 4. Clean shutdown, as a client-hosting process would perform.
                    bootstrap.shutdown()
                    self.assert_true(bootstrap.rest_api_server is None)

    def _test_server_start_is_idempotent(self) -> None:
        server, _ = self._start_test_server()
        try:
            port_before = server.port
            server.start()  # should be a no-op, not raise
            self.assert_true(server.is_running)
            self.assert_equal(server.port, port_before)
        finally:
            server.stop()

    def _test_server_stop_then_restart(self) -> None:
        server, _ = self._start_test_server()
        server.stop()
        self.assert_false(server.is_running)
        server.start()
        try:
            self.assert_true(server.is_running)
        finally:
            server.stop()

    def _start_test_server(self) -> tuple[RestApiServer, str]:
        router = CommandRouter()
        router.register(_EchoModule())
        api_router = ApiRouter(command_router=router)
        server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)
        server.start()
        return server, f"http://127.0.0.1:{server.port}"

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_starts_rest_api_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, _API_ENABLED_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.rest_api_server is not None)
                    self.assert_true(bootstrap.rest_api_server.is_running)

                    status, payload = _http_get(
                        f"http://127.0.0.1:{bootstrap.rest_api_server.port}", "/health"
                    )
                    self.assert_equal(status, 200)
                    self.assert_equal(payload.get("status"), "ok")
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_skips_rest_api_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, _API_DISABLED_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.rest_api_server is None)

    def _test_bootstrap_skips_rest_api_when_config_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, _API_ABSENT_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.rest_api_server is None)

    def _test_bootstrap_shutdown_stops_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, _API_ENABLED_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                server = bootstrap.rest_api_server
                self.assert_true(server is not None and server.is_running)
                bootstrap.shutdown()
                self.assert_false(server.is_running)
                self.assert_true(bootstrap.rest_api_server is None)

    def _test_bootstrap_shutdown_safe_when_nothing_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, _API_DISABLED_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                bootstrap.shutdown()  # must not raise
                self.assert_true(bootstrap.rest_api_server is None)

    def _test_interactive_shell_unaffected_by_rest_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, _API_ENABLED_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.shell is not None)
                    # InteractiveShell dispatches through the exact same
                    # CommandRouter the REST API uses -- prove the CLI
                    # path still works independently of the running
                    # RestApiServer.
                    result = bootstrap._command_router.dispatch("system version")
                    self.assert_true(result.success)
                finally:
                    bootstrap.shutdown()


class _EchoModule:
    """Minimal CommandModule stub used only by this test suite.

    Not a production module: returns its own arguments joined by a
    space, purely to give ApiRouter/RestApiServer tests a
    deterministic, dependency-free target to dispatch against.
    """

    @property
    def name(self) -> str:
        return "echo"

    def execute(self, action, arguments):
        from src.core.command_router import CommandResult

        if action != "say":
            return CommandResult(success=False, message=f"Unknown command: echo {action}")
        return CommandResult(success=True, message=" ".join(arguments))
