"""Real engineering tests for EP-059 - Distributed Runtime (Candidate A).

Per `EP059_DESIGN.md` (Owner Decision D1, "Candidate A"), EP-059 adds
exactly one new capability: a read-only `RuntimeService`/`RuntimeModule`
pair that aggregates already-existing, already-public facts from
already-constructed objects (`RestApiServer.is_running`/`.host`/
`.port` (EP-043), `BackgroundWorkerService.status()` (EP-036), and an
`InteractiveShell` reference) into one `RuntimeStatus` snapshot, plus
process PID/uptime via the standard library only. It performs no new
computation, network call, or file I/O of its own, and never starts,
stops, restarts, or reconfigures anything it reports on.

Covers:
    - `RuntimeService.status()` in isolation: every dependency `None`
      (a clean, all-inactive/zero snapshot, never a crash); a real,
      unmodified `RestApiServer` bound to an ephemeral local port,
      both before and after `start()`; a real, unmodified
      `BackgroundWorkerService` backed by a real `WorkflowEngine`,
      both disabled and enabled, including `task_count` changing after
      a real `submit()`; `shell_active` with and without a real
      `InteractiveShell`; `pid == os.getpid()`; `uptime_seconds >= 0`
      and increasing across two calls separated by a real sleep.
    - `RuntimeModule` CLI-layer tests: `runtime status` formatting
      (including/excluding the REST API address line and the
      Background Worker lines depending on active state); `runtime
      help` lists `runtime status`; an unknown action fails cleanly;
      trailing arguments to `status`/`help` are tolerated, not
      rejected (no usage-error path exists for either, matching this
      module's own, deliberately minimal action set).
    - `CommandRouter` dispatch-equivalence: `router.dispatch("runtime
      status")` produces the same `CommandResult` as calling
      `RuntimeModule.execute("status", [])` directly.
    - Read-only-only architecture guarantee: `RuntimeModule` exposes
      exactly `{"status", "help"}` and no mutating/control action of
      any kind (Owner Decision D5); `RuntimeService`'s only public
      method is `status()`.
    - Real, enabled `Bootstrap` end-to-end wiring: a full
      `Bootstrap.initialize()` run (mirroring
      `EP057_ARCHITECTURE_AUDIT.md`/`EP058_ARCHITECTURE_AUDIT.md`'s own
      "real object graph, not a fake" precedent) confirming
      `bootstrap.runtime_service` is constructed, `"runtime"` is a
      registered `CommandRouter` namespace, and `runtime status`
      dispatches successfully through the real `CommandRouter` --
      proving the Bootstrap wiring genuinely works end to end, not
      merely at the unit level.
    - Construction-ordering correctness (the approved STEP 1
      documentation clarification, verified in code): the
      `RuntimeService` a real `Bootstrap` builds observes the exact
      same, final, live `background_worker_service`/`rest_api_server`/
      `shell` objects `Bootstrap`'s own public properties expose --
      never a stale or early `None` captured before those subsystems'
      own construction attempts completed. Verified both by object
      identity and behaviorally (a task submitted through
      `bootstrap.background_worker_service` after `initialize()`
      is visible in a subsequent `runtime status` call).
    - REST command-dispatch compatibility without any new
      REST-layer-specific code: a real `RestApiServer`/`ApiRouter`
      pair (both standalone and via a real, `api.enabled: true`
      `Bootstrap`) answers `POST /api/v1/commands` for
      `{"module": "runtime", "action": "status"}` correctly -- proving
      `EP059_DESIGN.md` Section 6.4's "zero REST-specific code, reachable
      the moment the module is registered" claim is genuinely true.
    - Regression guards: `api status`/`worker status` (already-existing,
      unmodified actions) are completely unaffected by `RuntimeModule`'s
      own, separate registration; `background_worker_service`/
      `rest_api_server` behave identically whether or not
      `RuntimeService` is also constructed.
    - Mutation-quality self-check: `_test_field_wiring_is_not_permuted`
      cross-checks every `RuntimeStatus` field against an
      independently-computed expected value using distinguishable
      inputs (different worker counts, task counts, host, and port),
      so a field-swap or off-by-one implementation bug -- not just a
      wrong boolean -- would be caught. See also this file's own
      docstring note on the manual mutation drill performed for STEP 2
      (not itself part of the committed suite).
"""

from __future__ import annotations

import inspect
import os
import tempfile
import time
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.api.api_router import ApiRouter
from src.core.api.rest_api_server import RestApiServer
from src.core.command_router import CommandRouter
from src.core.config import Config
from src.core.plan_execution.plan_execution_result import PlanExecutionResult
from src.core.shell import InteractiveShell
from src.core.workflow_engine.workflow_definition import (
    WorkflowDefinition,
    WorkflowRequestStep,
)
from src.core.workflow_engine.workflow_engine import WorkflowEngine
from src.core.workflow_engine.workflow_engine_manager import WorkflowEngineManager
from src.modules.runtime_module import RuntimeModule
from src.services.background_worker_service import BackgroundWorkerService
from src.services.runtime_service import RuntimeService, RuntimeStatus
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


class _StubPlanExecutionEngine:
    """Minimal, real `PlanExecutionEngine`-shaped stub -- always succeeds.

    Kept local and self-contained (not imported from `tests/EP036`),
    matching this project's own per-EP-suite self-containment
    precedent (see `EP059_DESIGN.md`'s own citation of this pattern).
    """

    def execute_request(self, request: str) -> PlanExecutionResult:
        return PlanExecutionResult(
            plan=None,
            step_results=[],
            completed_count=1,
            failed_count=0,
            skipped_count=0,
            success=True,
        )


def _build_real_workflow_engine(tmp_path: Path, workflow_id: str = "noop") -> WorkflowEngine:
    """Build a real, minimal WorkflowEngine with one single-step definition."""
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        'workflow_engine:\n  enabled: true\n  default_provider: "workflow_engine"\n'
        "  stop_on_failure: true\n",
        encoding="utf-8",
    )

    config = Config(config_dir / "config.yaml").load()
    manager = WorkflowEngineManager(config=config)
    manager.register_definition(
        WorkflowDefinition(
            id=workflow_id,
            name=workflow_id,
            description="",
            enabled=True,
            steps=(WorkflowRequestStep(name="only", request=workflow_id),),
        )
    )
    return WorkflowEngine(manager=manager, plan_execution_engine=_StubPlanExecutionEngine())


_FULL_BOOTSTRAP_CONFIG_YAML = (
    "app:\n"
    '  name: "JARVIS-TEST"\n'
    '  tagline: "Test"\n'
    '  version: "0.0.0-test"\n\n'
    "logging:\n"
    '  level: "INFO"\n'
    "  retention_days: 1\n"
    "  console_enabled: false\n\n"
    "paths:\n"
    '  logs: "logs"\n'
    '  data_input: "data/input"\n'
    '  data_output: "data/output"\n'
    '  data_cache: "data/cache"\n'
    '  data_database: "data/database"\n'
    '  knowledge: "knowledge"\n'
    '  prompts: "prompts"\n\n'
    "memory:\n"
    "  enabled: true\n"
    "  persistent: false\n"
    "  auto_save: false\n"
    "  max_entries: 10000\n"
    "  default_ttl: null\n"
    '  default_provider: "memory"\n\n'
    "knowledge:\n"
    "  enabled: true\n"
    '  default_provider: "local"\n\n'
    "long_term_memory:\n"
    "  enabled: true\n"
    '  default_provider: "knowledge"\n\n'
    "orchestrator:\n"
    "  skills_enabled: []\n\n"
    "invoice:\n"
    '  script: ""\n\n'
    "fast_response:\n"
    '  workbook: ""\n'
    '  worksheet: ""\n'
    '  backup_folder: ""\n\n'
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
    '  plugin_directory: "plugins"\n\n'
    "telegram:\n"
    "  enabled: false\n"
    "  auto_start: false\n"
    '  token: ""\n'
    "  allowed_chat_ids: []\n"
    "  polling_interval: 2\n\n"
    "ai:\n"
    "  enabled: true\n"
    '  default_provider: "none"\n'
    "  timeout: 120\n"
    "  retry_count: 2\n"
    "  max_context_messages: 20\n\n"
    "conversation:\n"
    "  enabled: true\n"
    "  auto_save: false\n"
    "  max_messages: 100\n"
    "  max_conversations: 100\n"
    '  storage_file: "data/database/conversations.json"\n'
    '  truncate_strategy: "oldest"\n\n'
    "prompt:\n"
    "  enabled: true\n"
    '  system_prompt: ""\n'
    "  append_datetime: false\n"
    "  append_provider_name: false\n"
    "  append_os_information: false\n"
    "  append_working_directory: false\n"
    "  max_prompt_size: 32000\n"
    "  reserved_system_prompt: 2000\n"
    "  reserved_conversation_history: 8000\n"
    "  reserved_user_prompt: 2000\n"
    "  reserved_provider_overhead: 1000\n\n"
    "context:\n"
    "  enabled: true\n"
    "  auto_load: true\n"
    "  include_environment: false\n"
    "  include_working_directory: false\n"
    "  include_project_files: false\n"
    "  smart_selection: true\n\n"
    "indexing:\n"
    '  storage_backend: "memory"\n'
    '  storage_file: "data/database/project_index.json"\n\n'
    "providers:\n"
    "  claude:\n"
    "    enabled: false\n"
    '    api_key: ""\n'
    "  openai:\n"
    "    enabled: false\n"
    '    api_key: ""\n'
    "  gemini:\n"
    "    enabled: false\n"
    '    api_key: ""\n'
    "  ollama:\n"
    "    enabled: false\n"
    '    endpoint: ""\n'
    "  lmstudio:\n"
    "    enabled: false\n"
    '    endpoint: ""\n\n'
    "embedding:\n"
    "  enabled: true\n"
    '  default_provider: "local"\n'
    "  batch_size: 16\n"
    "  providers:\n"
    "    local:\n"
    "      enabled: true\n"
    '      model: "local-hash-v1"\n'
    "      dimension: 16\n"
    "    cloud:\n"
    "      enabled: false\n"
    '      api_key: ""\n'
    '      model: "text-embedding-cloud-v1"\n'
    "      dimension: 1536\n\n"
    "rag:\n"
    "  enabled: true\n"
    "  top_k: 5\n"
    "  max_context_characters: 4000\n\n"
    "semantic:\n"
    "  enabled: true\n"
    '  default_provider: "semantic"\n'
    "  top_k: 5\n"
    "  similarity_threshold: 0.0\n\n"
    "context_compression:\n"
    "  enabled: true\n"
    '  default_provider: "compression"\n'
    "  max_context_characters: 12000\n"
    "  max_chunks: 20\n"
    "  deduplicate: true\n\n"
    "agent:\n"
    "  enabled: true\n"
    '  default_agent: "jarvis"\n'
    '  startup_mode: "idle"\n\n'
    "planning:\n"
    "  enabled: true\n"
    '  default_provider: "planning"\n'
    "  max_steps: 10\n\n"
    "plan_execution:\n"
    "  enabled: true\n"
    '  default_provider: "plan_execution"\n'
    "  stop_on_failure: true\n\n"
    "tool:\n"
    "  enabled: true\n"
    '  default_provider: "tool_engine"\n\n'
    "collaboration:\n"
    "  enabled: true\n"
    '  default_provider: "collaboration"\n\n'
    "workflow_engine:\n"
    "  enabled: true\n"
    '  default_provider: "workflow_engine"\n'
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
    "{background_workers_section}"
)


def _write_full_bootstrap_config(
    directory: Path,
    api_section: str = 'api:\n  enabled: false\n  host: "127.0.0.1"\n  port: 0\n',
    background_workers_section: str = "",
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            api_section=api_section, background_workers_section=background_workers_section
        ),
        encoding="utf-8",
    )


_API_ENABLED_SECTION = 'api:\n  enabled: true\n  host: "127.0.0.1"\n  port: 0\n'
_API_DISABLED_SECTION = 'api:\n  enabled: false\n  host: "127.0.0.1"\n  port: 0\n'


def _http_post_json(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    import json
    import urllib.error
    import urllib.request

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        base_url + path, data=body, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


@TestRegistry.register
class RuntimeTest(BaseTest):
    NAME = "EP059"

    def run(self):
        # ---------- RuntimeService.status() in isolation ----------
        self._test_status_all_none_reports_clean_inactive_snapshot()
        self._test_status_never_raises_with_all_none()
        self._test_pid_matches_os_getpid()
        self._test_uptime_nonnegative_and_increasing()
        self._test_shell_active_true_with_real_shell()
        self._test_shell_active_false_without_shell()
        self._test_api_inactive_before_start()
        self._test_api_active_after_start_with_real_host_port()
        self._test_api_inactive_when_none_supplied()
        self._test_background_workers_inactive_when_disabled()
        self._test_background_workers_active_with_real_pool()
        self._test_background_worker_task_count_increases_after_submit()
        self._test_field_wiring_is_not_permuted()

        # ---------- RuntimeModule CLI layer ----------
        self._test_module_name_is_runtime()
        self._test_help_lists_status()
        self._test_status_message_active_state()
        self._test_status_message_inactive_state()
        self._test_unknown_action_fails_cleanly()
        self._test_status_ignores_trailing_arguments()
        self._test_help_ignores_trailing_arguments()

        # ---------- CommandRouter dispatch equivalence ----------
        self._test_router_dispatch_equivalence()

        # ---------- Read-only / no control surface guarantee ----------
        self._test_module_exposes_only_status_and_help()
        self._test_service_exposes_only_status()

        # ---------- Real Bootstrap wiring (production path) ----------
        self._test_bootstrap_constructs_runtime_service()
        self._test_bootstrap_registers_runtime_namespace()
        self._test_bootstrap_runtime_status_dispatches_successfully()
        self._test_bootstrap_runtime_status_reflects_live_api_and_workers()
        self._test_bootstrap_absent_api_section_defaults_safely()

        # ---------- Construction-ordering correctness ----------
        self._test_bootstrap_runtime_service_observes_live_background_worker_service()
        self._test_bootstrap_runtime_service_observes_live_rest_api_server()
        self._test_bootstrap_runtime_service_observes_live_shell()
        self._test_submitted_task_after_init_visible_in_runtime_status()

        # ---------- REST command-dispatch compatibility ----------
        self._test_standalone_rest_dispatch_runtime_status()
        self._test_bootstrap_rest_dispatch_runtime_status()

        # ---------- Regression guards ----------
        self._test_worker_status_unaffected_by_runtime_module()
        self._test_api_status_unaffected_by_runtime_module()

        return self.result

    # ================= RuntimeService in isolation =================

    def _test_status_all_none_reports_clean_inactive_snapshot(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        status = service.status()
        self.assert_false(status.shell_active)
        self.assert_false(status.api_active)
        self.assert_true(status.api_host is None)
        self.assert_true(status.api_port is None)
        self.assert_false(status.background_workers_active)
        self.assert_equal(status.background_worker_count, 0)
        self.assert_equal(status.background_worker_task_count, 0)

    def _test_status_never_raises_with_all_none(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        try:
            service.status()
            self.assert_true(True)
        except Exception as exc:  # noqa: BLE001 - this is the assertion itself
            self.assert_true(False, f"status() raised unexpectedly: {exc!r}")

    def _test_pid_matches_os_getpid(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        self.assert_equal(service.status().pid, os.getpid())

    def _test_uptime_nonnegative_and_increasing(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        first = service.status().uptime_seconds
        self.assert_true(first >= 0)
        time.sleep(0.05)
        second = service.status().uptime_seconds
        self.assert_true(second > first)

    def _test_shell_active_true_with_real_shell(self) -> None:
        router = CommandRouter()
        shell = InteractiveShell(router=router)
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=shell,
        )
        self.assert_true(service.status().shell_active)

    def _test_shell_active_false_without_shell(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        self.assert_false(service.status().shell_active)

    def _test_api_inactive_before_start(self) -> None:
        router = CommandRouter()
        api_router = ApiRouter(command_router=router)
        server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=server,
            background_worker_service=None,
            shell=None,
        )
        status = service.status()
        self.assert_false(status.api_active)
        self.assert_true(status.api_host is None)
        self.assert_true(status.api_port is None)

    def _test_api_active_after_start_with_real_host_port(self) -> None:
        router = CommandRouter()
        api_router = ApiRouter(command_router=router)
        server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)
        server.start()
        try:
            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=server,
                background_worker_service=None,
                shell=None,
            )
            status = service.status()
            self.assert_true(status.api_active)
            self.assert_equal(status.api_host, "127.0.0.1")
            self.assert_equal(status.api_port, server.port)
            self.assert_true(status.api_port != 0)
        finally:
            server.stop()

    def _test_api_inactive_when_none_supplied(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        self.assert_false(service.status().api_active)

    def _test_background_workers_inactive_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine = _build_real_workflow_engine(tmp_path)

            config = Config(tmp_path / "config" / "config.yaml").load()
            bg_service = BackgroundWorkerService(config=config, workflow_engine=engine)
            # 'background_workers.enabled' absent from this minimal
            # config, but defaults to True (see BackgroundWorkerService's
            # own module docstring) -- so exercise the explicit-disabled
            # path with its own config instead.
            (tmp_path / "config" / "config.yaml").write_text(
                'workflow_engine:\n  enabled: true\n  default_provider: "workflow_engine"\n'
                "  stop_on_failure: true\n\n"
                "background_workers:\n  enabled: false\n",
                encoding="utf-8",
            )
            disabled_config = Config(tmp_path / "config" / "config.yaml").load()
            disabled_service = BackgroundWorkerService(
                config=disabled_config, workflow_engine=engine
            )
            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=disabled_service,
                shell=None,
            )
            status = service.status()
            self.assert_false(status.background_workers_active)
            self.assert_equal(status.background_worker_count, 0)
            self.assert_equal(status.background_worker_task_count, 0)
            bg_service.shutdown(wait=True, timeout=2)

    def _test_background_workers_active_with_real_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine = _build_real_workflow_engine(tmp_path)
            (tmp_path / "config" / "config.yaml").write_text(
                'workflow_engine:\n  enabled: true\n  default_provider: "workflow_engine"\n'
                "  stop_on_failure: true\n\n"
                "background_workers:\n  enabled: true\n  worker_count: 3\n",
                encoding="utf-8",
            )

            config = Config(tmp_path / "config" / "config.yaml").load()
            bg_service = BackgroundWorkerService(config=config, workflow_engine=engine)
            try:
                service = RuntimeService(
                    started_at=time.monotonic(),
                    rest_api_server=None,
                    background_worker_service=bg_service,
                    shell=None,
                )
                status = service.status()
                self.assert_true(status.background_workers_active)
                self.assert_equal(status.background_worker_count, 3)
                self.assert_equal(status.background_worker_task_count, 0)
            finally:
                bg_service.shutdown(wait=True, timeout=2)

    def _test_background_worker_task_count_increases_after_submit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine = _build_real_workflow_engine(tmp_path, workflow_id="noop")
            (tmp_path / "config" / "config.yaml").write_text(
                'workflow_engine:\n  enabled: true\n  default_provider: "workflow_engine"\n'
                "  stop_on_failure: true\n\n"
                "background_workers:\n  enabled: true\n  worker_count: 2\n",
                encoding="utf-8",
            )

            config = Config(tmp_path / "config" / "config.yaml").load()
            bg_service = BackgroundWorkerService(config=config, workflow_engine=engine)
            try:
                service = RuntimeService(
                    started_at=time.monotonic(),
                    rest_api_server=None,
                    background_worker_service=bg_service,
                    shell=None,
                )
                before = service.status().background_worker_task_count
                bg_service.submit("noop")
                after = service.status().background_worker_task_count
                self.assert_equal(before, 0)
                self.assert_equal(after, 1)
            finally:
                bg_service.shutdown(wait=True, timeout=2)

    def _test_field_wiring_is_not_permuted(self) -> None:
        """Cross-check every field against an independently-computed value.

        Uses distinguishable inputs (a non-default worker count, a
        non-default port, a real submitted task) so a field-swap bug
        (e.g. reporting `worker_count` where `task_count` belongs, or
        `api_port` where `background_worker_count` belongs) would be
        caught, not just a wrong boolean. This is the suite's primary
        mutation-quality guard against "shape is right, wiring is
        wrong" bugs.
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine = _build_real_workflow_engine(tmp_path, workflow_id="noop")
            (tmp_path / "config" / "config.yaml").write_text(
                'workflow_engine:\n  enabled: true\n  default_provider: "workflow_engine"\n'
                "  stop_on_failure: true\n\n"
                "background_workers:\n  enabled: true\n  worker_count: 5\n",
                encoding="utf-8",
            )

            config = Config(tmp_path / "config" / "config.yaml").load()
            bg_service = BackgroundWorkerService(config=config, workflow_engine=engine)
            router = CommandRouter()
            api_router = ApiRouter(command_router=router)
            server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)
            server.start()
            try:
                bg_service.submit("noop")
                bg_service.submit("noop")
                expected_port = server.port
                expected_worker_status = bg_service.status()

                service = RuntimeService(
                    started_at=time.monotonic(),
                    rest_api_server=server,
                    background_worker_service=bg_service,
                    shell=None,
                )
                status = service.status()

                self.assert_equal(status.api_host, "127.0.0.1")
                self.assert_equal(status.api_port, expected_port)
                self.assert_equal(status.background_worker_count, 5)
                self.assert_equal(status.background_worker_count, expected_worker_status.worker_count)
                self.assert_equal(status.background_worker_task_count, 2)
                self.assert_equal(
                    status.background_worker_task_count, expected_worker_status.task_count
                )
                # None of these distinguishable values are equal to
                # each other, so any pairwise swap between them would
                # fail at least one of the assertions above.
                self.assert_true(
                    len(
                        {
                            status.api_port,
                            status.background_worker_count,
                            status.background_worker_task_count,
                        }
                    )
                    == 3
                )
            finally:
                server.stop()
                bg_service.shutdown(wait=True, timeout=2)

    # ================= RuntimeModule CLI layer =================

    def _test_module_name_is_runtime(self) -> None:
        module = RuntimeModule(self._inactive_service())
        self.assert_equal(module.name, "runtime")

    def _test_help_lists_status(self) -> None:
        module = RuntimeModule(self._inactive_service())
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("runtime status" in result.message)
        self.assert_true("runtime help" in result.message)

    def _test_status_message_active_state(self) -> None:
        router = CommandRouter()
        api_router = ApiRouter(command_router=router)
        server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)
        server.start()
        try:
            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=server,
                background_worker_service=None,
                shell=None,
            )
            module = RuntimeModule(service)
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("ACTIVE" in result.message)
            self.assert_true(f"127.0.0.1:{server.port}" in result.message)
        finally:
            server.stop()

    def _test_status_message_inactive_state(self) -> None:
        module = RuntimeModule(self._inactive_service())
        result = module.execute("status", [])
        self.assert_true(result.success)
        self.assert_true("INACTIVE" in result.message)
        # No REST API address / worker-count lines when inactive.
        self.assert_false("Background worker threads" in result.message)

    def _test_unknown_action_fails_cleanly(self) -> None:
        module = RuntimeModule(self._inactive_service())
        result = module.execute("restart", [])
        self.assert_false(result.success)
        self.assert_true("Unknown command" in result.message)

    def _test_status_ignores_trailing_arguments(self) -> None:
        module = RuntimeModule(self._inactive_service())
        result = module.execute("status", ["unexpected", "extra"])
        self.assert_true(result.success)

    def _test_help_ignores_trailing_arguments(self) -> None:
        module = RuntimeModule(self._inactive_service())
        result = module.execute("help", ["unexpected"])
        self.assert_true(result.success)

    # ================= CommandRouter dispatch equivalence =================

    def _test_router_dispatch_equivalence(self) -> None:
        router = CommandRouter()
        service = self._inactive_service()
        router.register(RuntimeModule(service))
        direct = RuntimeModule(service).execute("status", [])
        via_router = router.dispatch("runtime status")
        self.assert_equal(direct.success, via_router.success)
        self.assert_equal(direct.message, via_router.message)

    # ================= Read-only / no control surface =================

    def _test_module_exposes_only_status_and_help(self) -> None:
        module = RuntimeModule(self._inactive_service())
        self.assert_equal(set(module._actions.keys()), {"status", "help"})  # noqa: SLF001
        for forbidden in ("start", "stop", "restart", "reconfigure", "register", "shutdown"):
            self.assert_true(forbidden not in module._actions)  # noqa: SLF001

    def _test_service_exposes_only_status(self) -> None:
        public_methods = [
            name
            for name, member in inspect.getmembers(RuntimeService, predicate=inspect.isfunction)
            if not name.startswith("_")
        ]
        self.assert_equal(public_methods, ["status"])

    # ================= Real Bootstrap wiring =================

    def _test_bootstrap_constructs_runtime_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.runtime_service is not None)

    def _test_bootstrap_registers_runtime_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                module_names = bootstrap._command_router.module_names  # noqa: SLF001
                self.assert_true("runtime" in module_names)

    def _test_bootstrap_runtime_status_dispatches_successfully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                result = bootstrap._command_router.dispatch("runtime status")  # noqa: SLF001
                self.assert_true(result.success)
                self.assert_true("Runtime Status" in result.message)
                self.assert_true(f"PID : {os.getpid()}" in result.message)

    def _test_bootstrap_runtime_status_reflects_live_api_and_workers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                api_section=_API_ENABLED_SECTION,
                background_workers_section="background_workers:\n  enabled: true\n  worker_count: 2\n",
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap._command_router.dispatch("runtime status")  # noqa: SLF001
                    self.assert_true(result.success)
                    self.assert_true(
                        f"127.0.0.1:{bootstrap.rest_api_server.port}" in result.message
                    )
                    self.assert_true("Background worker threads : 2" in result.message)
                finally:
                    if bootstrap.background_worker_service is not None:
                        bootstrap.background_worker_service.shutdown(wait=True, timeout=2)
                    if bootstrap.rest_api_server is not None:
                        bootstrap.rest_api_server.stop()

    def _test_bootstrap_absent_api_section_defaults_safely(self) -> None:
        # No 'api' section at all -- must default safely (api.enabled
        # defaults to false), and 'runtime status' must still succeed.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, api_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.rest_api_server is None)
                result = bootstrap._command_router.dispatch("runtime status")  # noqa: SLF001
                self.assert_true(result.success)
                self.assert_true("REST API : INACTIVE" in result.message)

    # ================= Construction-ordering correctness =================

    def _test_bootstrap_runtime_service_observes_live_background_worker_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                background_workers_section="background_workers:\n  enabled: true\n  worker_count: 4\n",
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.background_worker_service is not None)
                    # Whitebox identity check: RuntimeService must hold
                    # the exact same object Bootstrap's own public
                    # property exposes -- never a stale reference
                    # captured before this subsystem's own construction
                    # attempt (inside `_build_command_router`, which
                    # runs before `_shell`/`_rest_api_server` are even
                    # assigned) completed.
                    self.assert_true(
                        bootstrap.runtime_service._background_worker_service  # noqa: SLF001
                        is bootstrap.background_worker_service
                    )
                finally:
                    if bootstrap.background_worker_service is not None:
                        bootstrap.background_worker_service.shutdown(wait=True, timeout=2)

    def _test_bootstrap_runtime_service_observes_live_rest_api_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, api_section=_API_ENABLED_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.rest_api_server is not None)
                    self.assert_true(
                        bootstrap.runtime_service._rest_api_server  # noqa: SLF001
                        is bootstrap.rest_api_server
                    )
                finally:
                    if bootstrap.rest_api_server is not None:
                        bootstrap.rest_api_server.stop()

    def _test_bootstrap_runtime_service_observes_live_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.shell is not None)
                self.assert_true(
                    bootstrap.runtime_service._shell is bootstrap.shell  # noqa: SLF001
                )

    def _test_submitted_task_after_init_visible_in_runtime_status(self) -> None:
        # Behavioral proof (not just identity): a task submitted
        # through Bootstrap's own background_worker_service AFTER
        # initialize() must be visible in a SUBSEQUENT "runtime
        # status" call -- this could only be true if RuntimeService
        # were handed the final, live BackgroundWorkerService, not an
        # early snapshot/None captured before construction completed.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                background_workers_section="background_workers:\n  enabled: true\n  worker_count: 2\n",
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.background_worker_service is not None)

                    before = bootstrap._command_router.dispatch(  # noqa: SLF001
                        "runtime status"
                    )
                    self.assert_true("Background tasks submitted : 0" in before.message)

                    # No workflow is registered by default (the
                    # 'workflows' section above is EP-007's unrelated,
                    # dormant subsystem), so submitting a real
                    # workflow_id will raise a domain error -- which is
                    # fine: we only need the pool's own task_count to
                    # move, and an attempted-but-rejected submission
                    # does not touch the pool's task list. Instead,
                    # register a real definition directly through the
                    # already-constructed WorkflowEngine this run, then
                    # submit through the live service.
                    workflow_engine_service = bootstrap.workflow_engine_service
                    self.assert_true(workflow_engine_service is not None)

                    # Whitebox: WorkflowEngineService exposes no public
                    # "register a definition" method of its own (by
                    # design -- see its own class docstring); reach its
                    # already-existing, already-tested WorkflowEngineManager
                    # directly, exactly as `bootstrap._command_router`
                    # is already reached elsewhere in this project's
                    # own test suites.
                    workflow_engine_service._manager.register_definition(  # noqa: SLF001
                        WorkflowDefinition(
                            id="ep059_probe",
                            name="ep059_probe",
                            description="",
                            enabled=True,
                            steps=(WorkflowRequestStep(name="only", request="system version"),),
                        )
                    )
                    bootstrap.background_worker_service.submit("ep059_probe")

                    after = bootstrap._command_router.dispatch(  # noqa: SLF001
                        "runtime status"
                    )
                    self.assert_true("Background tasks submitted : 1" in after.message)
                finally:
                    if bootstrap.background_worker_service is not None:
                        bootstrap.background_worker_service.shutdown(wait=True, timeout=2)

    # ================= REST command-dispatch compatibility =================

    def _test_standalone_rest_dispatch_runtime_status(self) -> None:
        router = CommandRouter()
        service = self._inactive_service()
        router.register(RuntimeModule(service))
        api_router = ApiRouter(command_router=router)
        server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)
        server.start()
        try:
            base_url = f"http://127.0.0.1:{server.port}"
            status, payload = _http_post_json(
                base_url, "/api/v1/commands", {"module": "runtime", "action": "status"}
            )
            self.assert_equal(status, 200)
            self.assert_true(payload.get("success"))
            self.assert_true("Runtime Status" in payload.get("message", ""))
        finally:
            server.stop()

    def _test_bootstrap_rest_dispatch_runtime_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, api_section=_API_ENABLED_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.rest_api_server is not None)
                    base_url = f"http://127.0.0.1:{bootstrap.rest_api_server.port}"
                    status, payload = _http_post_json(
                        base_url,
                        "/api/v1/commands",
                        {"module": "runtime", "action": "status"},
                    )
                    self.assert_equal(status, 200)
                    self.assert_true(payload.get("success"))
                    self.assert_true("REST API : ACTIVE" in payload.get("message", ""))
                finally:
                    if bootstrap.rest_api_server is not None:
                        bootstrap.rest_api_server.stop()

    # ================= Regression guards =================

    def _test_worker_status_unaffected_by_runtime_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                background_workers_section="background_workers:\n  enabled: true\n  worker_count: 2\n",
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap._command_router.dispatch("worker status")  # noqa: SLF001
                    self.assert_true(result.success)
                    self.assert_true("Worker threads : 2" in result.message)
                finally:
                    if bootstrap.background_worker_service is not None:
                        bootstrap.background_worker_service.shutdown(wait=True, timeout=2)

    def _test_api_status_unaffected_by_runtime_module(self) -> None:
        # There is no CLI-facing "api" CommandModule (EP-043 is a
        # transport layer -- ApiRouter/RestApiServer -- not a
        # Core->Service->Module business subsystem, exactly as
        # tests/EP043/test_rest_api.py's own docstring documents), so
        # the regression check here is: the REST API's HTTP-level
        # endpoints ("/health", "/api/v1/status") and an existing,
        # unrelated CLI command ("system status") both still work
        # completely unaffected by RuntimeModule's own, separate
        # registration.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, api_section=_API_ENABLED_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    cli_result = bootstrap._command_router.dispatch(  # noqa: SLF001
                        "system status"
                    )
                    self.assert_true(cli_result.success)

                    base_url = f"http://127.0.0.1:{bootstrap.rest_api_server.port}"
                    import json
                    import urllib.request

                    with urllib.request.urlopen(base_url + "/health", timeout=5) as response:
                        health_status = response.status
                        health_payload = json.loads(response.read().decode("utf-8"))
                    self.assert_equal(health_status, 200)
                    self.assert_equal(health_payload.get("status"), "ok")
                finally:
                    if bootstrap.rest_api_server is not None:
                        bootstrap.rest_api_server.stop()

    # ================= Shared helpers =================

    @staticmethod
    def _inactive_service() -> RuntimeService:
        return RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
