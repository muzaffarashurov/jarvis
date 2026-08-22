"""Real engineering tests for EP-045 STEP 2 - Web Dashboard.

Single combined test suite (NAME = "EP045"), following the same
precedent EP-043 (tests/EP043/test_rest_api.py) and EP-037
(tests/EP037/test_event_bus.py) already established for a
non-Service/Module transport-layer EP: this sidesteps the
pre-existing `TestRegistry` NAME-collision technical debt
(docs/BACKLOG.md) entirely rather than triggering it.

EP-045 introduces exactly one server-side change -- optional,
same-origin static-file serving in `RestApiServer`, added only
because a browser-based dashboard cannot use CORS-free cross-origin
requests, and no separate process can bind the same host:port
(see docs/architecture/designs/EP045_DESIGN.md, Section 21 "Option A",
and the EP-045 STEP 2 report's "Why this change is required" section).
This suite verifies:

1. `RestApiServer`'s three EP-043 API routes are completely unaffected
   by the new capability, whether or not a `static_dir` is configured
   (regression safety -- this suite does not re-run EP-043's own
   `tests/EP043/test_rest_api.py`, which remains untouched and is the
   authoritative regression check for that contract).
2. Static file serving itself: `/`, an explicit file, correct
   Content-Type inference, a 404 for a missing file, and a refused
   (still-404, not 500) path-traversal attempt.
3. The "disabled by default" behavior: with no `static_dir`
   configured, every non-API path still returns exactly the same 404
   it did before EP-045 existed.
4. Bootstrap wiring: `api.web_dashboard_dir` pointing at a real
   directory serves it; an absent config key, an empty value, and a
   non-existent directory all degrade safely to "not served" rather
   than crashing `Bootstrap.initialize()`.
"""

from __future__ import annotations

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


_MINIMAL_BOOTSTRAP_CONFIG_YAML = (
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


def _write_bootstrap_config(directory: Path, api_section: str) -> None:
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _MINIMAL_BOOTSTRAP_CONFIG_YAML.format(api_section=api_section),
        encoding="utf-8",
    )


def _api_section(*, enabled: bool, web_dashboard_dir: str | None) -> str:
    lines = ["api:", "  enabled: " + ("true" if enabled else "false"), '  host: "127.0.0.1"', "  port: 0"]
    if web_dashboard_dir is not None:
        lines.append(f'  web_dashboard_dir: "{web_dashboard_dir}"')
    return "\n".join(lines) + "\n"


def _http_get_raw(base_url: str, path: str):
    """GET and return (status, headers, body_bytes) without assuming a JSON body."""
    request = urllib.request.Request(base_url + path, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def _http_get_json(base_url: str, path: str) -> tuple[int, dict]:
    status, _headers, body = _http_get_raw(base_url, path)
    return status, json.loads(body.decode("utf-8"))


class _EchoModule:
    """Minimal CommandModule stub used only by this test suite."""

    @property
    def name(self) -> str:
        return "echo"

    def execute(self, action, arguments):
        from src.core.command_router import CommandResult

        if action != "say":
            return CommandResult(success=False, message=f"Unknown command: echo {action}")
        return CommandResult(success=True, message=" ".join(arguments))


@TestRegistry.register
class WebDashboardTest(BaseTest):
    NAME = "EP045"

    def run(self):
        self._test_static_dir_none_preserves_ep043_404_behavior()
        self._test_serves_index_html_at_root()
        self._test_serves_named_static_file_with_content_type()
        self._test_missing_static_file_returns_404()
        self._test_path_traversal_attempt_returns_404_not_500()
        self._test_existing_api_routes_unaffected_when_static_dir_configured()
        self._test_wrong_method_on_static_path_falls_through_to_get_only()

        self._test_bootstrap_serves_dashboard_when_configured()
        self._test_bootstrap_skips_dashboard_when_key_absent()
        self._test_bootstrap_skips_dashboard_when_value_empty()
        self._test_bootstrap_skips_dashboard_when_directory_missing()

        return self.result

    # ---------- static file serving ----------

    def _start_server(self, static_dir: Path | None = None) -> tuple[RestApiServer, str]:
        router = CommandRouter()
        router.register(_EchoModule())
        api_router = ApiRouter(command_router=router)
        server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0, static_dir=static_dir)
        server.start()
        return server, f"http://127.0.0.1:{server.port}"

    def _make_static_dir(self, tmp: str) -> Path:
        static_dir = Path(tmp) / "web_public"
        static_dir.mkdir(parents=True, exist_ok=True)
        (static_dir / "index.html").write_text("<html><body>Jarvis Dashboard</body></html>", encoding="utf-8")
        (static_dir / "app.js").write_text("console.log('ep045');", encoding="utf-8")
        (static_dir / "styles.css").write_text("body { margin: 0; }", encoding="utf-8")
        return static_dir

    def _test_static_dir_none_preserves_ep043_404_behavior(self) -> None:
        server, base_url = self._start_server(static_dir=None)
        try:
            status, payload = _http_get_json(base_url, "/")
            self.assert_equal(status, 404)
            self.assert_equal(payload.get("error", {}).get("code"), "not_found")

            status, payload = _http_get_json(base_url, "/anything-else.html")
            self.assert_equal(status, 404)
        finally:
            server.stop()

    def _test_serves_index_html_at_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            static_dir = self._make_static_dir(tmp)
            server, base_url = self._start_server(static_dir=static_dir)
            try:
                status, headers, body = _http_get_raw(base_url, "/")
                self.assert_equal(status, 200)
                self.assert_true("text/html" in headers.get("Content-Type", ""))
                self.assert_true(b"Jarvis Dashboard" in body)
            finally:
                server.stop()

    def _test_serves_named_static_file_with_content_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            static_dir = self._make_static_dir(tmp)
            server, base_url = self._start_server(static_dir=static_dir)
            try:
                status, headers, body = _http_get_raw(base_url, "/app.js")
                self.assert_equal(status, 200)
                self.assert_true(
                    "javascript" in headers.get("Content-Type", "")
                    or "ecmascript" in headers.get("Content-Type", "")
                )
                self.assert_true(b"ep045" in body)

                status, headers, body = _http_get_raw(base_url, "/styles.css")
                self.assert_equal(status, 200)
                self.assert_true("css" in headers.get("Content-Type", ""))
            finally:
                server.stop()

    def _test_missing_static_file_returns_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            static_dir = self._make_static_dir(tmp)
            server, base_url = self._start_server(static_dir=static_dir)
            try:
                status, payload = _http_get_json(base_url, "/does-not-exist.png")
                self.assert_equal(status, 404)
                self.assert_equal(payload.get("error", {}).get("code"), "not_found")
            finally:
                server.stop()

    def _test_path_traversal_attempt_returns_404_not_500(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            static_dir = self._make_static_dir(tmp)
            # A sibling file outside static_dir that a traversal attempt
            # might try to reach.
            (Path(tmp) / "secret.txt").write_text("do not serve me", encoding="utf-8")
            server, base_url = self._start_server(static_dir=static_dir)
            try:
                status, payload = _http_get_json(base_url, "/../secret.txt")
                self.assert_equal(status, 404)
                self.assert_equal(payload.get("error", {}).get("code"), "not_found")
            finally:
                server.stop()

    def _test_existing_api_routes_unaffected_when_static_dir_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            static_dir = self._make_static_dir(tmp)
            server, base_url = self._start_server(static_dir=static_dir)
            try:
                status, payload = _http_get_json(base_url, "/health")
                self.assert_equal(status, 200)
                self.assert_equal(payload.get("status"), "ok")

                status, payload = _http_get_json(base_url, "/api/v1/status")
                self.assert_equal(status, 200)
                self.assert_true("success" in payload)

                request = urllib.request.Request(
                    base_url + "/api/v1/commands",
                    data=json.dumps({"module": "echo", "action": "say", "arguments": ["hi"]}).encode("utf-8"),
                    method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    status = response.status
                    payload = json.loads(response.read().decode("utf-8"))
                self.assert_equal(status, 200)
                self.assert_true(payload.get("success"))
                self.assert_equal(payload.get("message"), "hi")
            finally:
                server.stop()

    def _test_wrong_method_on_static_path_falls_through_to_get_only(self) -> None:
        # POST to a static-file-shaped path (not one of the 3 fixed
        # API routes) is never treated as a static-file request (only
        # GET is) -- it falls straight through to the existing 404,
        # matching EP-043's original "no such resource" behavior.
        with tempfile.TemporaryDirectory() as tmp:
            static_dir = self._make_static_dir(tmp)
            server, base_url = self._start_server(static_dir=static_dir)
            try:
                request = urllib.request.Request(base_url + "/index.html", method="POST", data=b"{}")
                try:
                    urllib.request.urlopen(request, timeout=5)
                    self.assert_true(False, "Expected an HTTPError for POST /index.html")
                except urllib.error.HTTPError as exc:
                    self.assert_equal(exc.code, 404)
            finally:
                server.stop()

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_serves_dashboard_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            static_dir = directory / "web" / "public"
            static_dir.mkdir(parents=True, exist_ok=True)
            (static_dir / "index.html").write_text("<html>ok</html>", encoding="utf-8")

            _write_bootstrap_config(
                directory, _api_section(enabled=True, web_dashboard_dir="web/public")
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.rest_api_server is not None)
                    self.assert_true(bootstrap.rest_api_server.is_running)
                    self.assert_true(bootstrap.rest_api_server.static_dir is not None)

                    status, _headers, body = _http_get_raw(
                        f"http://127.0.0.1:{bootstrap.rest_api_server.port}", "/"
                    )
                    self.assert_equal(status, 200)
                    self.assert_true(b"ok" in body)

                    # The 3 API routes remain reachable alongside static serving.
                    status, payload = _http_get_json(
                        f"http://127.0.0.1:{bootstrap.rest_api_server.port}", "/health"
                    )
                    self.assert_equal(status, 200)
                    self.assert_equal(payload.get("status"), "ok")
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_skips_dashboard_when_key_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_bootstrap_config(directory, _api_section(enabled=True, web_dashboard_dir=None))
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.rest_api_server is not None)
                    self.assert_true(bootstrap.rest_api_server.static_dir is None)

                    status, payload = _http_get_json(
                        f"http://127.0.0.1:{bootstrap.rest_api_server.port}", "/"
                    )
                    self.assert_equal(status, 404)
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_skips_dashboard_when_value_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_bootstrap_config(directory, _api_section(enabled=True, web_dashboard_dir=""))
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.rest_api_server is not None)
                    self.assert_true(bootstrap.rest_api_server.static_dir is None)
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_skips_dashboard_when_directory_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_bootstrap_config(
                directory, _api_section(enabled=True, web_dashboard_dir="web/does-not-exist")
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.rest_api_server is not None)
                    self.assert_true(bootstrap.rest_api_server.static_dir is None)

                    status, payload = _http_get_json(
                        f"http://127.0.0.1:{bootstrap.rest_api_server.port}", "/"
                    )
                    self.assert_equal(status, 404)
                finally:
                    bootstrap.shutdown()
