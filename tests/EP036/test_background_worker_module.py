"""Real engineering tests for EP-036 STEP 3 - Background Worker Module (CLI).

Builds a real `BackgroundWorkerService` (STEP 2, unchanged) and drives
a real `BackgroundWorkerModule` directly through `execute()`, exactly
as `tests/EP035/test_automation_engine.py`'s own "AutomationModule
(CLI)" section drives `AutomationModule` -- no mocked internals.
Also drives a real `Bootstrap` for the wiring section, matching both
EP-035's own approach and this EP's own STEP 2 suite
(`tests/EP036/test_background_worker_service.py`).

This suite covers exactly STEP 3's scope and nothing else:

1. `BackgroundWorkerModule.name` and unknown-action handling.
2. Every CLI command ("status", "submit", "list", "info", "stop",
   "help"), including their usage-error and not-found paths.
3. That STEP 2's `BackgroundWorkerService` public API is used
   completely unchanged -- this module only translates its existing
   return values/exceptions into `CommandResult`, so these tests
   double as a guard that STEP 3 did not modify STEP 2 behavior.
4. Bootstrap wiring: the "worker" namespace is registered whenever
   `BackgroundWorkerService` itself is built (mirrors
   AutomationModule's own "registered regardless of
   'automation.enabled'" precedent) -- including when
   'background_workers.enabled' is false (the module still answers
   "worker status" truthfully) -- and is NOT registered when the
   Workflow Engine is unavailable or 'background_workers.worker_count'
   is invalid, mirroring `tests/EP036/test_background_worker_service.py`'s
   own equivalent Bootstrap-degradation cases for the Service.
5. Test-registry naming guard: this suite is registered under a
   distinct `TestRegistry` name ("EP036-STEP3") from both STEP 1's
   "EP036" and STEP 2's "EP036-STEP2", for the same reason documented
   in `tests/EP036/test_background_worker_service.py`'s own module
   docstring (point 7) -- avoiding a silent `TestRegistry.register`
   collision. This section proves all three suites remain
   independently reachable.
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.config import Config
from src.core.plan_execution.plan_execution_result import PlanExecutionResult
from src.core.workflow_engine.workflow_definition import WorkflowDefinition, WorkflowRequestStep
from src.core.workflow_engine.workflow_engine import WorkflowEngine
from src.core.workflow_engine.workflow_engine_manager import WorkflowEngineManager
from src.core.background_workers.background_worker_pool import TaskStatus
from src.modules.background_worker_module import BackgroundWorkerModule
from src.services.background_worker_service import BackgroundWorkerService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

import os


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


def _write_config(directory: Path, sections: str) -> Config:
    """Return a freshly loaded Config for `directory` (never cached/reused)."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(sections, encoding="utf-8")
    return Config(config_path).load()


_WORKFLOW_ENGINE_ONLY_YAML = (
    "workflow_engine:\n"
    "  enabled: true\n"
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: true\n"
)


def _background_workers_yaml(
    enabled: bool | None = None,
    worker_count: object = None,
    shutdown_timeout: object = None,
) -> str:
    """Build a 'workflow_engine: + background_workers:' config text.

    Identical technique to
    `tests/EP036/test_background_worker_service.py`'s own helper of
    the same name (duplicated here, not imported, matching this
    project's per-EP-suite self-containment precedent).
    """
    text = _WORKFLOW_ENGINE_ONLY_YAML
    if enabled is None and worker_count is None and shutdown_timeout is None:
        return text

    text += "\nbackground_workers:\n"
    if enabled is not None:
        text += f"  enabled: {str(enabled).lower()}\n"
    if worker_count is not None:
        text += f"  worker_count: {worker_count}\n"
    if shutdown_timeout is not None:
        text += f"  shutdown_timeout: {shutdown_timeout}\n"
    return text


class _ControllableStubPlanExecutionEngine:
    """A duck-typed PlanExecutionEngine stand-in with test-controllable behavior.

    Identical technique to STEP 1's/STEP 2's own stand-ins
    (duplicated here, not imported -- see this file's module
    docstring).
    """

    def __init__(
        self,
        failing_requests: frozenset = frozenset(),
        gate: threading.Event | None = None,
    ) -> None:
        self._failing_requests = failing_requests
        self._gate = gate
        self._calls_lock = threading.Lock()
        self.calls: list[str] = []

    def execute_request(self, request: str) -> PlanExecutionResult:
        with self._calls_lock:
            self.calls.append(request)
        if self._gate is not None:
            self._gate.wait()
        success = request not in self._failing_requests
        return PlanExecutionResult(
            plan=None,
            step_results=[],
            completed_count=1 if success else 0,
            failed_count=0 if success else 1,
            skipped_count=0,
            success=success,
        )


def _build_engine(
    tmp_path: Path,
    workflow_ids: list[str],
    failing_requests: frozenset = frozenset(),
    gate: threading.Event | None = None,
) -> WorkflowEngine:
    """Build a real WorkflowEngine with one single-step definition per workflow id."""
    config = _write_config(tmp_path, _WORKFLOW_ENGINE_ONLY_YAML)
    manager = WorkflowEngineManager(config=config)
    for workflow_id in workflow_ids:
        manager.register_definition(
            WorkflowDefinition(
                id=workflow_id,
                name=workflow_id,
                description="",
                enabled=True,
                steps=(WorkflowRequestStep(name="only", request=workflow_id),),
            )
        )
    stub = _ControllableStubPlanExecutionEngine(failing_requests=failing_requests, gate=gate)
    return WorkflowEngine(manager=manager, plan_execution_engine=stub)


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.01) -> bool:
    """Poll `predicate()` until it returns truthy or `timeout` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _build_module(
    tmp_path: Path,
    workflow_ids: list[str],
    enabled: bool = True,
    worker_count: int = 2,
    gate: threading.Event | None = None,
) -> tuple[BackgroundWorkerModule, BackgroundWorkerService]:
    engine = _build_engine(tmp_path, workflow_ids, gate=gate)
    config = _write_config(
        tmp_path,
        _background_workers_yaml(enabled=enabled, worker_count=worker_count),
    )
    service = BackgroundWorkerService(config=config, workflow_engine=engine)
    return BackgroundWorkerModule(service), service


# ---------- Full Bootstrap configuration (mirrors STEP 2's own) ----------

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
    "  default_provider: \"{workflow_engine_provider}\"\n"
    "  stop_on_failure: true\n\n"
    "workflow_scheduler:\n"
    "  enabled: true\n"
    "  auto_start: false\n"
    "  tick_interval: 5\n\n"
    "automation:\n"
    "  enabled: true\n"
    "{background_workers_section}"
)


def _write_full_bootstrap_config(
    directory: Path,
    workflow_engine_provider: str = "workflow_engine",
    background_workers_section: str = "",
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`.

    Identical technique/parameters to
    `tests/EP036/test_background_worker_service.py`'s own helper of
    the same name (duplicated here, not imported).
    """
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            workflow_engine_provider=workflow_engine_provider,
            background_workers_section=background_workers_section,
        ),
        encoding="utf-8",
    )


@TestRegistry.register
class BackgroundWorkerModuleTest(BaseTest):
    # Deliberately distinct from STEP 1's "EP036" and STEP 2's
    # "EP036-STEP2" (see this file's module docstring, point 5).
    NAME = "EP036-STEP3"

    def run(self):
        # ---------- BackgroundWorkerModule (CLI) ----------
        self._test_module_name()
        self._test_cli_help_lists_commands()
        self._test_cli_unknown_action()
        self._test_cli_status_command_enabled()
        self._test_cli_status_command_disabled()
        self._test_cli_submit_usage_error()
        self._test_cli_submit_success_and_task_id_in_message()
        self._test_cli_submit_on_disabled_service_fails()
        self._test_cli_submit_after_stop_fails()
        self._test_cli_list_empty_then_populated()
        self._test_cli_info_usage_error()
        self._test_cli_info_not_found()
        self._test_cli_info_success_shows_workflow_and_status()
        self._test_cli_info_shows_error_on_failed_task()
        self._test_cli_stop_idle_pool_succeeds()
        self._test_cli_stop_does_not_report_success_when_gated()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_registers_worker_module_when_enabled()
        self._test_bootstrap_registers_worker_module_when_disabled()
        self._test_bootstrap_skips_worker_module_when_workflow_engine_unavailable()
        self._test_bootstrap_skips_worker_module_on_invalid_worker_count()

        # ---------- Test-registry naming guard ----------
        self._test_all_three_step_suites_independently_registered()

        return self.result

    # ---------- BackgroundWorkerModule (CLI) ----------

    def _test_module_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"])
            try:
                self.assert_equal(module.name, "worker")
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_cli_help_lists_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"])
            try:
                result = module.execute("help", [])
                self.assert_true(result.success)
                for command in ("status", "submit", "list", "info", "stop", "help"):
                    self.assert_true(f"worker {command}" in result.message)
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_cli_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"])
            try:
                result = module.execute("bogus", [])
                self.assert_false(result.success)
                self.assert_true("worker help" in result.message)
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_cli_status_command_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"], enabled=True, worker_count=3)
            try:
                result = module.execute("status", [])
                self.assert_true(result.success)
                self.assert_true("Background Worker Status" in result.message)
                self.assert_true("Enabled : YES" in result.message)
                self.assert_true("Running : YES" in result.message)
                self.assert_true("Worker threads : 3" in result.message)
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_cli_status_command_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"], enabled=False)
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Enabled : NO" in result.message)
            self.assert_true("Running : NO" in result.message)

    def _test_cli_submit_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"])
            try:
                result = module.execute("submit", [])
                self.assert_false(result.success)
                self.assert_true("Usage" in result.message)
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_cli_submit_success_and_task_id_in_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"])
            try:
                result = module.execute("submit", ["wf-a"])
                self.assert_true(result.success)
                self.assert_true("Task submitted:" in result.message)
                task_id = result.message.split(":", 1)[1].strip()
                self.assert_true(
                    _wait_until(
                        lambda: service.get_task(task_id) is not None
                        and service.get_task(task_id).status
                        in (TaskStatus.COMPLETED, TaskStatus.FAILED)
                    )
                )
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_cli_submit_on_disabled_service_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"], enabled=False)
            result = module.execute("submit", ["wf-a"])
            self.assert_false(result.success)

    def _test_cli_submit_after_stop_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"], worker_count=1)
            module.execute("stop", [])
            result = module.execute("submit", ["wf-a"])
            self.assert_false(result.success)

    def _test_cli_list_empty_then_populated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"])
            try:
                empty = module.execute("list", [])
                self.assert_true(empty.success)
                self.assert_true("(none submitted)" in empty.message)

                submit_result = module.execute("submit", ["wf-a"])
                task_id = submit_result.message.split(":", 1)[1].strip()
                result = module.execute("list", [])
                self.assert_true(result.success)
                self.assert_true(task_id in result.message)
                self.assert_true("wf-a" in result.message)
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_cli_info_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"])
            try:
                result = module.execute("info", [])
                self.assert_false(result.success)
                self.assert_true("Usage" in result.message)
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_cli_info_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"])
            try:
                result = module.execute("info", ["nonexistent-task-id"])
                self.assert_false(result.success)
                self.assert_true("not found" in result.message.lower())
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_cli_info_success_shows_workflow_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, service = _build_module(Path(tmp), ["wf-a"])
            try:
                submit_result = module.execute("submit", ["wf-a"])
                task_id = submit_result.message.split(":", 1)[1].strip()
                self.assert_true(
                    _wait_until(
                        lambda: service.get_task(task_id) is not None
                        and service.get_task(task_id).status
                        in (TaskStatus.COMPLETED, TaskStatus.FAILED)
                    )
                )
                result = module.execute("info", [task_id])
                self.assert_true(result.success)
                self.assert_true("wf-a" in result.message)
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_cli_info_shows_error_on_failed_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine = _build_engine(tmp_path, ["wf-fail"], failing_requests=frozenset({"wf-fail"}))
            config = _write_config(
                tmp_path, _background_workers_yaml(enabled=True, worker_count=1)
            )
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            module = BackgroundWorkerModule(service)
            try:
                submit_result = module.execute("submit", ["wf-fail"])
                task_id = submit_result.message.split(":", 1)[1].strip()
                self.assert_true(
                    _wait_until(
                        lambda: service.get_task(task_id) is not None
                        and service.get_task(task_id).status
                        in (TaskStatus.COMPLETED, TaskStatus.FAILED)
                    )
                )
                result = module.execute("info", [task_id])
                self.assert_true(result.success)
                self.assert_true("Error" in result.message)
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_cli_stop_idle_pool_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module, _ = _build_module(Path(tmp), ["wf-a"])
            result = module.execute("stop", [])
            self.assert_true(result.success)
            self.assert_true("stopped" in result.message.lower())

    def _test_cli_stop_does_not_report_success_when_gated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            gate = threading.Event()
            engine = _build_engine(tmp_path, ["wf-slow"], gate=gate)
            config = _write_config(
                tmp_path,
                _background_workers_yaml(enabled=True, worker_count=1, shutdown_timeout=0.2),
            )
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            module = BackgroundWorkerModule(service)
            try:
                module.execute("submit", ["wf-slow"])
                self.assert_true(_wait_until(lambda: service.status().task_count == 1))
                result = module.execute("stop", [])
                self.assert_false(result.success)
            finally:
                gate.set()
                service.shutdown(wait=True, timeout=2)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_worker_module_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                background_workers_section="background_workers:\n  enabled: true\n  worker_count: 2\n",
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                module_names = bootstrap._command_router.module_names  # noqa: SLF001
                self.assert_true("worker" in module_names)
                bootstrap.background_worker_service.shutdown(wait=True, timeout=2)

    def _test_bootstrap_registers_worker_module_when_disabled(self) -> None:
        # Mirrors AutomationModule's own precedent: the CLI namespace
        # is registered whenever the Service itself is built,
        # regardless of 'background_workers.enabled' -- the module
        # still truthfully reports the disabled state via "worker
        # status" (see _test_cli_status_command_disabled above).
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory, background_workers_section="background_workers:\n  enabled: false\n"
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                module_names = bootstrap._command_router.module_names  # noqa: SLF001
                self.assert_true("worker" in module_names)

    def _test_bootstrap_skips_worker_module_when_workflow_engine_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, workflow_engine_provider="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.background_worker_service is None)
                module_names = bootstrap._command_router.module_names  # noqa: SLF001
                self.assert_false("worker" in module_names)

    def _test_bootstrap_skips_worker_module_on_invalid_worker_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                background_workers_section="background_workers:\n  enabled: true\n  worker_count: 0\n",
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.background_worker_service is None)
                module_names = bootstrap._command_router.module_names  # noqa: SLF001
                self.assert_false("worker" in module_names)

    # ---------- Test-registry naming guard ----------

    def _test_all_three_step_suites_independently_registered(self) -> None:
        from tests.EP036.test_background_worker_pool import BackgroundWorkerPoolTest
        from tests.EP036.test_background_worker_service import BackgroundWorkerServiceTest

        self.assert_true(TestRegistry.get("EP036") is BackgroundWorkerPoolTest)
        self.assert_true(TestRegistry.get("EP036-STEP2") is BackgroundWorkerServiceTest)
        self.assert_true(TestRegistry.get("EP036-STEP3") is BackgroundWorkerModuleTest)
