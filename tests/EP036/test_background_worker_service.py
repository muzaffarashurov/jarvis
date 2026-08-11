"""Real engineering tests for EP-036 STEP 2 - Background Worker Service.

Builds a real `WorkflowEngineManager` + real `WorkflowEngine`, composed
with a duck-typed `PlanExecutionEngine` stand-in (the same technique
EP-033/034/035's own suites use, and the same one STEP 1's own
`tests/EP036/test_background_worker_pool.py` uses), and drives a real
`BackgroundWorkerService` exactly as a caller would -- no mocked
internals. Also drives a real `Bootstrap` for the wiring section,
matching `tests/EP035/test_automation_engine.py`'s own approach.

This suite covers exactly STEP 2's scope and nothing else:

1. `BackgroundWorkerService` construction and 'background_workers.*'
   configuration resolution: default-enabled (config section absent
   entirely), explicit enabled/disabled, custom `worker_count`, and
   rejection of invalid `worker_count`/`shutdown_timeout` values.
2. Disabled-service behavior: `submit()` raises, `get_task()`/
   `list_tasks()` degrade to None/[] rather than raising, `shutdown()`
   is a trivial success (nothing to shut down).
3. `shutdown()`: the configured 'background_workers.shutdown_timeout'
   is used when no explicit timeout is given, an explicit timeout
   overrides it, and the underlying pool's own
   never-a-false-positive guarantee is preserved end to end.
4. End-to-end task execution through the Service -> Pool ->
   WorkflowEngine chain (mirrors STEP 1's own pool-level coverage,
   but exercised through the Service's public API only).
5. Bootstrap wiring: real construction from the same `WorkflowEngine`
   built for EP-033, backward-compatible default when
   'background_workers' is absent from configuration entirely,
   graceful degradation on invalid configuration, and skipping
   entirely when the Workflow Engine itself is unavailable -- mirrors
   EP-035's own Bootstrap-wiring section
   (`_test_bootstrap_skipped_when_workflow_engine_unavailable`, etc.).
6. Bootstrap module-registration guard: as of STEP 2, no CLI
   module/command namespace was registered for background workers
   (explicitly out of scope for that step; see
   `src/services/background_worker_service.py`'s module docstring).
   EP-036 STEP 3 later adds `BackgroundWorkerModule` (the "worker"
   namespace) as a pure, additive layer on top of this exact,
   unchanged Service -- see `tests/EP036/test_background_worker_module.py`
   for STEP 3's own coverage of that module. This section's Bootstrap
   test below is kept in sync with that authorized, later addition
   (verifying "worker" IS registered) rather than asserting a
   permanently-true "never any CLI module" invariant this subsystem
   was never meant to have.
7. Test-registry naming guard: STEP 1's `tests/EP036/test_background_worker_pool.py`
   suite is registered as `NAME = "EP036"`. This file's suite is
   registered under a distinct name (`"EP036-STEP2"`) specifically to
   avoid silently clobbering that registration in
   `TestRegistry._tests` (a dict keyed by `NAME.upper()`) -- both
   `test_module.py` imports execute at process start, and the second
   import's `@TestRegistry.register` would otherwise overwrite the
   first. This section proves both suites remain independently
   reachable, so `test EP036` (and STEP 1's own 101 assertions within
   it) are provably unaffected by this file's existence.
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
from src.core.background_workers.background_worker_pool import PoolShutDownError, TaskStatus
from src.services.background_worker_service import (
    BackgroundWorkerService,
    BackgroundWorkerServiceError,
)
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

    Only fields explicitly given (not None) are written, so callers
    can construct a Config where the whole 'background_workers'
    section is entirely absent (the backward-compatibility case) by
    passing no arguments at all.
    """
    text = _WORKFLOW_ENGINE_ONLY_YAML
    if enabled is None and worker_count is None and shutdown_timeout is None:
        return text

    text += "\nbackground_workers:\n"
    if enabled is not None:
        text += f"  enabled: {str(enabled).lower()}\n"
    if worker_count is not None:
        text += f"  worker_count: {worker_count!r}\n" if isinstance(worker_count, str) else f"  worker_count: {worker_count}\n"
    if shutdown_timeout is not None:
        text += (
            f"  shutdown_timeout: {shutdown_timeout!r}\n"
            if isinstance(shutdown_timeout, str)
            else f"  shutdown_timeout: {shutdown_timeout}\n"
        )
    return text


class _ControllableStubPlanExecutionEngine:
    """A duck-typed PlanExecutionEngine stand-in with test-controllable behavior.

    Identical technique to STEP 1's own
    `_ControllableStubPlanExecutionEngine` in
    `tests/EP036/test_background_worker_pool.py` -- duplicated here
    (not imported) matching this project's per-EP-suite
    self-containment precedent (see e.g. how
    `tests/EP034/test_workflow_scheduler.py` and
    `tests/EP035/test_automation_engine.py` each keep their own
    `_StubPlanExecutionEngine` rather than sharing one).
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
) -> tuple[WorkflowEngine, _ControllableStubPlanExecutionEngine]:
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
    engine = WorkflowEngine(manager=manager, plan_execution_engine=stub)
    return engine, stub


def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.01) -> bool:
    """Poll `predicate()` until it returns truthy or `timeout` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ---------- Full Bootstrap configuration (mirrors tests/EP035's own) ----------

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

    Args:
        directory: Project root to write 'config/config.yaml' under.
        workflow_engine_provider: 'workflow_engine.default_provider'.
            Set to an empty string to force EP-033 construction to
            fail (exercising the "Workflow Engine unavailable" skip
            path for this subsystem, mirroring EP-035's own
            `_test_bootstrap_skipped_when_workflow_engine_unavailable`).
        background_workers_section: Raw YAML text (including its own
            'background_workers:' key and trailing newline) to append
            after 'automation:'. Empty string (the default) means the
            'background_workers' section is entirely absent from the
            written config -- the backward-compatibility case.
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
class BackgroundWorkerServiceTest(BaseTest):
    # Deliberately distinct from STEP 1's "EP036" (see this file's
    # module docstring, point 7) so both suites remain independently
    # registered in TestRegistry rather than one clobbering the other.
    NAME = "EP036-STEP2"

    def run(self):
        # ---------- Construction / configuration resolution ----------
        self._test_default_enabled_when_section_absent()
        self._test_explicit_enabled_with_custom_worker_count()
        self._test_explicit_disabled()
        self._test_invalid_worker_count_zero_raises()
        self._test_invalid_worker_count_wrong_type_raises()
        self._test_invalid_worker_count_bool_raises()
        self._test_invalid_shutdown_timeout_raises()

        # ---------- Disabled-service behavior ----------
        self._test_disabled_submit_raises()
        self._test_disabled_get_task_returns_none()
        self._test_disabled_list_tasks_returns_empty()
        self._test_disabled_shutdown_returns_true()

        # ---------- End-to-end task execution through the Service ----------
        self._test_submit_and_await_completion()
        self._test_status_reflects_task_count()

        # ---------- shutdown() ----------
        self._test_shutdown_uses_configured_timeout_by_default()
        self._test_shutdown_explicit_timeout_overrides_config()
        self._test_shutdown_idle_pool_is_fast()
        self._test_submit_after_shutdown_raises_pool_shutdown_error()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_wires_service_when_enabled()
        self._test_bootstrap_backward_compatible_when_section_absent()
        self._test_bootstrap_wires_service_but_disabled_when_configured_false()
        self._test_bootstrap_skipped_when_workflow_engine_unavailable()
        self._test_bootstrap_degrades_on_invalid_worker_count()
        self._test_bootstrap_registers_worker_module()

        # ---------- Test-registry naming guard ----------
        self._test_step1_suite_still_independently_registered()

        return self.result

    # ---------- Construction / configuration resolution ----------

    def _test_default_enabled_when_section_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(tmp_path, _background_workers_yaml())
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            try:
                status = service.status()
                self.assert_true(status.enabled, "Expected 'background_workers.enabled' to default True")
                self.assert_true(status.running, "Expected a pool to be running by default")
                self.assert_equal(status.worker_count, 4, "Expected default worker_count of 4")
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_explicit_enabled_with_custom_worker_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(
                tmp_path, _background_workers_yaml(enabled=True, worker_count=2)
            )
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            try:
                status = service.status()
                self.assert_true(status.running)
                self.assert_equal(status.worker_count, 2)
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_explicit_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(tmp_path, _background_workers_yaml(enabled=False))
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            status = service.status()
            self.assert_false(status.enabled)
            self.assert_false(status.running)
            self.assert_equal(status.worker_count, 0)

    def _test_invalid_worker_count_zero_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(
                tmp_path, _background_workers_yaml(enabled=True, worker_count=0)
            )
            try:
                BackgroundWorkerService(config=config, workflow_engine=engine)
                self.assert_true(False, "Expected BackgroundWorkerServiceError for worker_count=0")
            except BackgroundWorkerServiceError:
                self.result.add_pass()

    def _test_invalid_worker_count_wrong_type_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(
                tmp_path, _background_workers_yaml(enabled=True, worker_count="four")
            )
            try:
                BackgroundWorkerService(config=config, workflow_engine=engine)
                self.assert_true(False, "Expected BackgroundWorkerServiceError for a string worker_count")
            except BackgroundWorkerServiceError:
                self.result.add_pass()

    def _test_invalid_worker_count_bool_raises(self) -> None:
        # Guards the isinstance(value, bool) check specifically: True/False
        # are `int` subclasses in Python and must NOT silently pass as 1/0.
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(
                tmp_path, _WORKFLOW_ENGINE_ONLY_YAML + "\nbackground_workers:\n  enabled: true\n  worker_count: true\n"
            )
            try:
                BackgroundWorkerService(config=config, workflow_engine=engine)
                self.assert_true(False, "Expected BackgroundWorkerServiceError for a boolean worker_count")
            except BackgroundWorkerServiceError:
                self.result.add_pass()

    def _test_invalid_shutdown_timeout_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(
                tmp_path, _background_workers_yaml(enabled=True, shutdown_timeout=0)
            )
            try:
                BackgroundWorkerService(config=config, workflow_engine=engine)
                self.assert_true(False, "Expected BackgroundWorkerServiceError for shutdown_timeout=0")
            except BackgroundWorkerServiceError:
                self.result.add_pass()

    # ---------- Disabled-service behavior ----------

    def _test_disabled_submit_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(tmp_path, _background_workers_yaml(enabled=False))
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            try:
                service.submit("wf-a")
                self.assert_true(False, "Expected BackgroundWorkerServiceError from a disabled service")
            except BackgroundWorkerServiceError:
                self.result.add_pass()

    def _test_disabled_get_task_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(tmp_path, _background_workers_yaml(enabled=False))
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            self.assert_true(service.get_task("anything") is None)

    def _test_disabled_list_tasks_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(tmp_path, _background_workers_yaml(enabled=False))
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            self.assert_equal(service.list_tasks(), [])

    def _test_disabled_shutdown_returns_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(tmp_path, _background_workers_yaml(enabled=False))
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            self.assert_true(service.shutdown() is True)

    # ---------- End-to-end task execution through the Service ----------

    def _test_submit_and_await_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(tmp_path, _background_workers_yaml(enabled=True, worker_count=2))
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            try:
                task_id = service.submit("wf-a")
                self.assert_not_none(task_id)

                completed = _wait_until(
                    lambda: service.get_task(task_id) is not None
                    and service.get_task(task_id).status
                    in (TaskStatus.COMPLETED, TaskStatus.FAILED)
                )
                self.assert_true(completed, "Task did not finish in time")
                task = service.get_task(task_id)
                self.assert_equal(task.status, TaskStatus.COMPLETED)
            finally:
                service.shutdown(wait=True, timeout=2)

    def _test_status_reflects_task_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a", "wf-b"])
            config = _write_config(tmp_path, _background_workers_yaml(enabled=True, worker_count=2))
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            try:
                service.submit("wf-a")
                service.submit("wf-b")
                self.assert_true(
                    _wait_until(lambda: service.status().task_count == 2),
                    "Expected status().task_count to reach 2",
                )
            finally:
                service.shutdown(wait=True, timeout=2)

    # ---------- shutdown() ----------

    def _test_shutdown_uses_configured_timeout_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            gate = threading.Event()
            engine, _ = _build_engine(tmp_path, ["wf-slow"], gate=gate)
            config = _write_config(
                tmp_path,
                _background_workers_yaml(enabled=True, worker_count=1, shutdown_timeout=0.2),
            )
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            try:
                service.submit("wf-slow")
                self.assert_true(
                    _wait_until(lambda: service.status().task_count == 1),
                    "Task was never picked up",
                )
                started = time.monotonic()
                result = service.shutdown()  # no explicit timeout -> uses config's 0.2s
                elapsed = time.monotonic() - started
                self.assert_false(result, "Expected shutdown() to report False while task is gated")
                self.assert_true(
                    elapsed < 2.0,
                    f"shutdown() took {elapsed:.2f}s; expected it to honor the short configured timeout",
                )
            finally:
                gate.set()
                service.shutdown(wait=True, timeout=2)

    def _test_shutdown_explicit_timeout_overrides_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            gate = threading.Event()
            engine, _ = _build_engine(tmp_path, ["wf-slow"], gate=gate)
            config = _write_config(
                tmp_path,
                # Configured timeout deliberately long; explicit call uses a short one.
                _background_workers_yaml(enabled=True, worker_count=1, shutdown_timeout=30),
            )
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            try:
                service.submit("wf-slow")
                self.assert_true(_wait_until(lambda: service.status().task_count == 1))
                started = time.monotonic()
                result = service.shutdown(timeout=0.2)
                elapsed = time.monotonic() - started
                self.assert_false(result)
                self.assert_true(
                    elapsed < 2.0,
                    f"shutdown(timeout=0.2) took {elapsed:.2f}s; explicit timeout should override config",
                )
            finally:
                gate.set()
                service.shutdown(wait=True, timeout=2)

    def _test_shutdown_idle_pool_is_fast(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(tmp_path, _background_workers_yaml(enabled=True, worker_count=2))
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            started = time.monotonic()
            result = service.shutdown()
            elapsed = time.monotonic() - started
            self.assert_true(result)
            self.assert_true(elapsed < 1.0, f"Idle shutdown took {elapsed:.2f}s")

    def _test_submit_after_shutdown_raises_pool_shutdown_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine, _ = _build_engine(tmp_path, ["wf-a"])
            config = _write_config(tmp_path, _background_workers_yaml(enabled=True, worker_count=1))
            service = BackgroundWorkerService(config=config, workflow_engine=engine)
            service.shutdown(wait=True, timeout=2)
            try:
                service.submit("wf-a")
                self.assert_true(False, "Expected PoolShutDownError to propagate unchanged")
            except PoolShutDownError:
                self.result.add_pass()

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_wires_service_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                background_workers_section="background_workers:\n  enabled: true\n  worker_count: 2\n",
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                service = bootstrap.background_worker_service
                self.assert_true(service is not None)
                status = service.status()
                self.assert_true(status.running)
                self.assert_equal(status.worker_count, 2)
                service.shutdown(wait=True, timeout=2)

    def _test_bootstrap_backward_compatible_when_section_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, background_workers_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                service = bootstrap.background_worker_service
                self.assert_true(
                    service is not None,
                    "Expected BackgroundWorkerService to still be built when "
                    "'background_workers' is absent from config.yaml entirely",
                )
                status = service.status()
                self.assert_true(status.enabled, "Expected the default-True fallback to apply")
                self.assert_equal(status.worker_count, 4)
                service.shutdown(wait=True, timeout=2)

    def _test_bootstrap_wires_service_but_disabled_when_configured_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory, background_workers_section="background_workers:\n  enabled: false\n"
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                service = bootstrap.background_worker_service
                self.assert_true(
                    service is not None,
                    "The Service object itself should still be built even when disabled",
                )
                status = service.status()
                self.assert_false(status.enabled)
                self.assert_false(status.running)

    def _test_bootstrap_skipped_when_workflow_engine_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            # Empty 'default_provider' makes WorkflowEngineManager fail to
            # resolve a provider, so EP-033 construction itself fails,
            # leaving `workflow_engine_for_scheduler` None in Bootstrap.
            _write_full_bootstrap_config(directory, workflow_engine_provider="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()  # must not raise
                self.assert_true(bootstrap.workflow_engine_service is None)
                self.assert_true(bootstrap.background_worker_service is None)

    def _test_bootstrap_degrades_on_invalid_worker_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                background_workers_section="background_workers:\n  enabled: true\n  worker_count: 0\n",
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()  # must not raise
                self.assert_true(bootstrap.background_worker_service is None)
                # Confirm the rest of the app still started successfully.
                self.assert_true(bootstrap.workflow_engine_service is not None)

    def _test_bootstrap_registers_worker_module(self) -> None:
        # Updated for EP-036 STEP 3 (see this file's module docstring,
        # point 6): STEP 2 originally asserted NO CLI module existed
        # for this subsystem, which was correct at the time. STEP 3
        # later added `BackgroundWorkerModule` as a pure, additive
        # layer on top of this exact, unchanged
        # `BackgroundWorkerService` -- this test now verifies that
        # addition landed correctly, keeping this Bootstrap-wiring
        # guard accurate rather than leaving a stale assertion behind.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory, background_workers_section="background_workers:\n  enabled: true\n"
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.background_worker_service is not None)
                module_names = bootstrap._command_router.module_names  # noqa: SLF001
                self.assert_true(
                    "worker" in module_names,
                    "Expected the 'worker' CLI namespace (EP-036 STEP 3) to be registered",
                )
                bootstrap.background_worker_service.shutdown(wait=True, timeout=2)

    # ---------- Test-registry naming guard ----------

    def _test_step1_suite_still_independently_registered(self) -> None:
        from tests.EP036.test_background_worker_pool import BackgroundWorkerPoolTest

        step1_class = TestRegistry.get("EP036")
        step2_class = TestRegistry.get("EP036-STEP2")
        self.assert_true(step1_class is not None, "STEP 1 suite 'EP036' must still be registered")
        self.assert_true(step2_class is not None, "STEP 2 suite 'EP036-STEP2' must be registered")
        self.assert_true(
            step1_class is BackgroundWorkerPoolTest,
            "'EP036' in TestRegistry must resolve to STEP 1's own suite class, unclobbered",
        )
        self.assert_true(step2_class is BackgroundWorkerServiceTest)
