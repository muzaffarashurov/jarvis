"""Real engineering tests for EP-060 - Jarvis Operating System (Candidate A).

Per `EP060_DESIGN.md` (Owner Decision D1, "Candidate A"), EP-060 widens
EP-059's read-only `RuntimeService`/`RuntimeModule` pair into a small,
additive lifecycle control plane:

    - `RuntimeStatus` gains `scheduler_active`/`scheduler_jobs_registered`,
      derived read-only from a real `SchedulerService.status()`,
      correcting EP-059 Owner Decision D4's now-outdated premise that
      the Scheduler is never auto-started as a side effect of
      `Bootstrap.initialize()` (Section 5.3).
    - `RuntimeService` gains exactly one new public method,
      `shutdown() -> RuntimeShutdownReport`, coordinating an ordered,
      idempotent shutdown of the REST API Server and the Background
      Worker Service only -- reusing their own already-existing,
      already-public `stop()`/`shutdown()` primitives, never inventing
      new stop logic (Section 9.3).
    - `Bootstrap.shutdown()` now delegates to `RuntimeService.shutdown()`
      (Section 9.5, Owner Decision D2), closing a confirmed gap where
      the Background Worker Pool's daemon threads were never asked to
      drain at process exit (Section 5.4).
    - `RuntimeModule` gains no new action (Owner Decision D3):
      `shutdown()` is never CLI/REST-reachable, only ever invoked by
      `Bootstrap.shutdown()` at genuine process exit.
    - The Scheduler's tick loop is deliberately never stopped by this
      EP (Owner Decision D5) -- `SchedulerService` (EP-011) exposes no
      public primitive to do so; it is observed, not controlled.

This suite is deliberately self-contained (does not import from
`tests/EP059`), matching that suite's own "per-EP-suite
self-containment" precedent. `tests/EP059/test_runtime.py` itself is
left completely unmodified and re-run unchanged as a regression guard
(see the EP-060 STEP 2 report) -- it is the direct proof that the
widened constructor/dataclass remain backward compatible.

Covers:
    - Backward compatibility: constructing `RuntimeService` with only
      the original four EP-059 keyword arguments (no
      `scheduler_service`) still succeeds, unchanged.
    - Widened `status()`: a real, unmodified `SchedulerService` observed
      correctly under both `scheduler.auto_start: true` and `false`;
      `scheduler_jobs_registered` reflects real registered jobs; no
      dependency supplied reports a clean, zero snapshot.
    - `RuntimeService.shutdown()` in isolation: all-`None` dependencies
      (never raises, reports "nothing to do" as success); a real,
      unmodified `RestApiServer` + a real, unmodified
      `BackgroundWorkerService` (both genuinely stopped); the Section
      5.5 limitation (`background_workers_was_active` remaining `True`
      on a second call) that EP-060 disclosed but did not fix, and
      that EP-062 has since fixed at its source
      (`BackgroundWorkerService.status()`, `EP062_DESIGN.md` Section
      6) -- the corresponding test now asserts the corrected `False`
      result rather than pinning the old bug; idempotency (two
      consecutive calls, neither raises); ordering (REST API stopped
      strictly before Background Workers).
    - `RuntimeModule`/`RuntimeService` public-surface guarantees:
      `RuntimeModule` still exposes exactly `{"status", "help"}` (no
      new CLI action); `RuntimeService` now exposes exactly
      `{"status", "shutdown"}` (widened from EP-059's `{"status"}`,
      still no `start()`/`restart()`/per-component-targeted operation).
    - `RuntimeModule` status formatting: the widened Scheduler line
      appears/is omitted correctly depending on `scheduler_active`.
    - Real, enabled `Bootstrap` end-to-end wiring (mirroring EP-059's
      own "real object graph, not a fake" precedent): `initialize()`
      populates `bootstrap.scheduler_service`; `RuntimeService` observes
      the exact same live object Bootstrap's own public property
      exposes; `runtime status` reflects it; a full
      `initialize()` -> `shutdown()` cycle genuinely stops the REST API
      Server and Background Worker Service and leaves
      `bootstrap.rest_api_server`/`bootstrap.background_worker_service`
      `None` afterward; a second `shutdown()` call remains safe;
      `shutdown()` is safe to call even when `initialize()` was never
      run.
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
from src.core.execution.engine import ExecutionEngine
from src.core.execution.process_registry import ProcessRegistry
from src.core.plan_execution.plan_execution_result import PlanExecutionResult
from src.core.scheduler.job import Job, Schedule, ScheduleType
from src.core.scheduler.job_registry import JobRegistry
from src.core.scheduler.scheduler import Scheduler
from src.core.workflow_engine.workflow_definition import (
    WorkflowDefinition,
    WorkflowRequestStep,
)
from src.core.workflow_engine.workflow_engine import WorkflowEngine
from src.core.workflow_engine.workflow_engine_manager import WorkflowEngineManager
from src.modules.runtime_module import RuntimeModule
from src.services.background_worker_service import BackgroundWorkerService
from src.services.runtime_service import (
    RuntimeService,
    RuntimeShutdownReport,
    RuntimeStatus,
)
from src.services.scheduler_service import SchedulerService
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

    Kept local and self-contained, matching `tests/EP059/test_runtime.py`'s
    own precedent (not imported from any other EP's test suite).
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


def _build_real_background_worker_service(
    tmp_path: Path, worker_count: int = 2
) -> BackgroundWorkerService:
    """Build a real, minimal, enabled BackgroundWorkerService."""
    engine = _build_real_workflow_engine(tmp_path)
    (tmp_path / "config" / "config.yaml").write_text(
        'workflow_engine:\n  enabled: true\n  default_provider: "workflow_engine"\n'
        "  stop_on_failure: true\n\n"
        f"background_workers:\n  enabled: true\n  worker_count: {worker_count}\n",
        encoding="utf-8",
    )
    config = Config(tmp_path / "config" / "config.yaml").load()
    return BackgroundWorkerService(config=config, workflow_engine=engine)


def _build_real_scheduler_service(
    tmp_path: Path, enabled: bool = True, auto_start: bool = True
) -> SchedulerService:
    """Build a real, minimal SchedulerService (EP-011 Scheduler underneath).

    `tick_interval` is set deliberately large (3600s) so no tick ever
    actually fires during a test, regardless of `auto_start`.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        "scheduler:\n"
        f"  enabled: {str(enabled).lower()}\n"
        f"  auto_start: {str(auto_start).lower()}\n"
        "  tick_interval: 3600\n",
        encoding="utf-8",
    )
    config = Config(config_dir / "config.yaml").load()
    registry = JobRegistry()
    execution_engine = ExecutionEngine(executors=[], registry=ProcessRegistry())
    scheduler = Scheduler(registry=registry, execution_engine=execution_engine)
    return SchedulerService(config=config, scheduler=scheduler)


def _stop_scheduler_tick_loop_for_test_cleanup(scheduler_service: SchedulerService) -> None:
    """Whitebox test-cleanup helper only -- NOT part of any public API.

    At the time this EP-060 suite was written, `SchedulerService`
    (EP-011) exposed no public method to stop its tick loop
    (`EP060_DESIGN.md` Section 5.2/9.3, Owner Decision D5). EP-061
    (`EP061_DESIGN.md` Section 7.1) has since added a public
    `SchedulerService.shutdown()` that closes that gap -- see
    `tests/EP061/test_scheduler_shutdown.py` for its dedicated
    coverage. This helper is retained here unchanged, reaching into
    the private `_stop_event`/`_tick_thread` directly, purely as a
    minimal, already-proven test-cleanup convenience predating that
    public method, not because no public alternative exists today; it
    still exists solely so this suite does not leak an un-joined
    daemon thread per test, and must not be read as a production-facing
    shutdown mechanism.
    """
    scheduler_service._stop_event.set()  # noqa: SLF001
    thread = scheduler_service._tick_thread  # noqa: SLF001
    if thread is not None:
        thread.join(timeout=2)


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
    "{scheduler_section}"
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
    scheduler_section: str = "scheduler:\n  enabled: true\n  auto_start: false\n  tick_interval: 3600\n\n",
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`.

    `scheduler_section` defaults to `auto_start: false` (mirroring
    `tests/EP059/test_runtime.py`'s own hardcoded default) so an
    ordinary `Bootstrap.initialize()` in this suite does not leave a
    live tick thread running unless a test explicitly asks for one via
    a non-default `scheduler_section`. `tick_interval` is set large
    (3600s) even when `auto_start: true` so no tick ever actually
    fires during a test.
    """
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            api_section=api_section,
            background_workers_section=background_workers_section,
            scheduler_section=scheduler_section,
        ),
        encoding="utf-8",
    )


_API_ENABLED_SECTION = 'api:\n  enabled: true\n  host: "127.0.0.1"\n  port: 0\n'
_SCHEDULER_AUTO_START_SECTION = (
    "scheduler:\n  enabled: true\n  auto_start: true\n  tick_interval: 3600\n\n"
)


class _OrderRecordingRestApiServer:
    """Thin proxy around a real RestApiServer that records call order.

    Duck-typed to exactly the surface `RuntimeService` reads/calls
    (`is_running`, `host`, `port`, `stop()`) -- used only in
    `_test_shutdown_orders_rest_api_before_background_workers` to
    verify Section 9.3's ordering guarantee without needing to modify
    or subclass `RestApiServer` itself.
    """

    def __init__(self, real: RestApiServer, order_log: list[str]) -> None:
        self._real = real
        self._order_log = order_log

    @property
    def is_running(self) -> bool:
        return self._real.is_running

    @property
    def host(self) -> str:
        return self._real.host

    @property
    def port(self) -> int:
        return self._real.port

    def stop(self) -> None:
        self._order_log.append("rest_api")
        self._real.stop()


class _OrderRecordingBackgroundWorkerService:
    """Thin proxy around a real BackgroundWorkerService that records call order.

    See `_OrderRecordingRestApiServer`; duck-typed to exactly the
    surface `RuntimeService` reads/calls (`status()`, `shutdown()`).
    """

    def __init__(self, real: BackgroundWorkerService, order_log: list[str]) -> None:
        self._real = real
        self._order_log = order_log

    def status(self):
        return self._real.status()

    def shutdown(self, wait: bool = True, timeout: float | None = None) -> bool:
        self._order_log.append("background_workers")
        return self._real.shutdown(wait=wait, timeout=timeout)


@TestRegistry.register
class RuntimeLifecycleTest(BaseTest):
    NAME = "EP060"

    def run(self):
        # ---------- Backward compatibility with EP-059 ----------
        self._test_construct_without_scheduler_service_still_succeeds()
        self._test_status_scheduler_inactive_when_none_supplied()

        # ---------- Widened status(): real Scheduler ----------
        self._test_scheduler_active_true_with_auto_start()
        self._test_scheduler_active_false_without_auto_start()
        self._test_scheduler_jobs_registered_reflects_real_jobs()

        # ---------- shutdown() in isolation ----------
        self._test_shutdown_all_none_reports_nothing_to_do()
        self._test_shutdown_never_raises_with_all_none()
        self._test_shutdown_stops_real_rest_api_server()
        self._test_shutdown_stops_real_background_worker_service()
        self._test_shutdown_background_worker_status_reflects_shutdown_state()
        self._test_shutdown_is_idempotent()
        self._test_shutdown_orders_rest_api_before_background_workers()

        # ---------- Public-surface / ownership-boundary guarantees ----------
        self._test_module_still_exposes_only_status_and_help()
        self._test_service_exposes_exactly_status_and_shutdown()

        # ---------- RuntimeModule formatting ----------
        self._test_status_message_includes_scheduler_line_when_active()
        self._test_status_message_omits_scheduler_line_when_inactive()

        # ---------- Real Bootstrap wiring ----------
        self._test_bootstrap_exposes_scheduler_service()
        self._test_bootstrap_runtime_service_observes_live_scheduler_service()
        self._test_bootstrap_runtime_status_reflects_scheduler()

        # ---------- Real Bootstrap shutdown coordination ----------
        self._test_bootstrap_shutdown_stops_rest_api_and_background_workers()
        self._test_bootstrap_shutdown_nulls_both_properties()
        self._test_bootstrap_shutdown_safe_when_called_twice()
        self._test_bootstrap_shutdown_safe_without_initialize()
        self._test_bootstrap_shutdown_does_not_touch_scheduler_service()

        return self.result

    # ================= Backward compatibility =================

    def _test_construct_without_scheduler_service_still_succeeds(self) -> None:
        # Exact original EP-059 call shape: four keyword arguments,
        # no `scheduler_service` at all.
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        status = service.status()
        self.assert_true(isinstance(status, RuntimeStatus))
        self.assert_false(status.scheduler_active)
        self.assert_equal(status.scheduler_jobs_registered, 0)

    def _test_status_scheduler_inactive_when_none_supplied(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
            scheduler_service=None,
        )
        status = service.status()
        self.assert_false(status.scheduler_active)
        self.assert_equal(status.scheduler_jobs_registered, 0)

    # ================= Widened status(): real Scheduler =================

    def _test_scheduler_active_true_with_auto_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler_service = _build_real_scheduler_service(
                Path(tmp), enabled=True, auto_start=True
            )
            try:
                self.assert_true(scheduler_service.status().running)
                service = RuntimeService(
                    started_at=time.monotonic(),
                    rest_api_server=None,
                    background_worker_service=None,
                    shell=None,
                    scheduler_service=scheduler_service,
                )
                status = service.status()
                self.assert_true(status.scheduler_active)
                self.assert_equal(
                    status.scheduler_active, scheduler_service.status().running
                )
            finally:
                _stop_scheduler_tick_loop_for_test_cleanup(scheduler_service)

    def _test_scheduler_active_false_without_auto_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler_service = _build_real_scheduler_service(
                Path(tmp), enabled=True, auto_start=False
            )
            try:
                self.assert_false(scheduler_service.status().running)
                service = RuntimeService(
                    started_at=time.monotonic(),
                    rest_api_server=None,
                    background_worker_service=None,
                    shell=None,
                    scheduler_service=scheduler_service,
                )
                status = service.status()
                self.assert_false(status.scheduler_active)
            finally:
                _stop_scheduler_tick_loop_for_test_cleanup(scheduler_service)

    def _test_scheduler_jobs_registered_reflects_real_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler_service = _build_real_scheduler_service(
                Path(tmp), enabled=True, auto_start=False
            )
            try:
                scheduler_service.register(
                    Job(
                        id="job-a",
                        name="Job A",
                        description="",
                        command="noop",
                        schedule=Schedule(type=ScheduleType.MANUAL),
                    )
                )
                scheduler_service.register(
                    Job(
                        id="job-b",
                        name="Job B",
                        description="",
                        command="noop",
                        schedule=Schedule(type=ScheduleType.MANUAL),
                    )
                )
                service = RuntimeService(
                    started_at=time.monotonic(),
                    rest_api_server=None,
                    background_worker_service=None,
                    shell=None,
                    scheduler_service=scheduler_service,
                )
                status = service.status()
                self.assert_equal(status.scheduler_jobs_registered, 2)
                self.assert_equal(
                    status.scheduler_jobs_registered,
                    scheduler_service.status().jobs_registered,
                )
            finally:
                _stop_scheduler_tick_loop_for_test_cleanup(scheduler_service)

    # ================= shutdown() in isolation =================

    def _test_shutdown_all_none_reports_nothing_to_do(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        report = service.shutdown()
        self.assert_true(isinstance(report, RuntimeShutdownReport))
        self.assert_false(report.rest_api_was_active)
        self.assert_true(report.rest_api_stopped)
        self.assert_false(report.background_workers_was_active)
        self.assert_true(report.background_workers_stopped)

    def _test_shutdown_never_raises_with_all_none(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        try:
            service.shutdown()
            self.assert_true(True)
        except Exception as exc:  # noqa: BLE001
            self.assert_true(False, f"shutdown() raised unexpectedly: {exc!r}")

    def _test_shutdown_stops_real_rest_api_server(self) -> None:
        router = CommandRouter()
        api_router = ApiRouter(command_router=router)
        server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)
        server.start()
        self.assert_true(server.is_running)
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=server,
            background_worker_service=None,
            shell=None,
        )
        report = service.shutdown()
        self.assert_true(report.rest_api_was_active)
        self.assert_true(report.rest_api_stopped)
        self.assert_false(server.is_running)

    def _test_shutdown_stops_real_background_worker_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bg_service = _build_real_background_worker_service(Path(tmp), worker_count=2)
            self.assert_true(bg_service.status().running)
            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=bg_service,
                shell=None,
            )
            report = service.shutdown()
            self.assert_true(report.background_workers_was_active)
            self.assert_true(report.background_workers_stopped)

    def _test_shutdown_background_worker_status_reflects_shutdown_state(self) -> None:
        """`EP060_DESIGN.md` Section 5.5/9.3's limitation, fixed by EP-062.

        `BackgroundWorkerService.status().running` used to be unable to
        distinguish "running" from "already shut down" (it only checked
        whether the pool object existed, not whether `shutdown()` had
        been called on it) -- disclosed, not fixed, by EP-060. EP-062
        (`EP062_DESIGN.md` Section 6) fixed this at its source by
        having `status()` read the owned pool's own already-existing
        `is_shutdown` property. This test now asserts the corrected
        contract -- `status().running` becomes `False` once `shutdown()`
        has been called, and a second `RuntimeService.shutdown()` call
        correctly reports `background_workers_was_active=False` -- so a
        future, silent regression back to the old behavior is caught,
        not discovered by surprise.
        """
        with tempfile.TemporaryDirectory() as tmp:
            bg_service = _build_real_background_worker_service(Path(tmp), worker_count=1)
            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=bg_service,
                shell=None,
            )
            service.shutdown()
            # Fixed by EP-062: correctly reports running=False.
            self.assert_false(bg_service.status().running)
            second_report = service.shutdown()
            self.assert_false(second_report.background_workers_was_active)

    def _test_shutdown_is_idempotent(self) -> None:
        router = CommandRouter()
        api_router = ApiRouter(command_router=router)
        server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)
        server.start()
        with tempfile.TemporaryDirectory() as tmp:
            bg_service = _build_real_background_worker_service(Path(tmp), worker_count=1)
            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=server,
                background_worker_service=bg_service,
                shell=None,
            )
            try:
                first = service.shutdown()
                second = service.shutdown()
                self.assert_true(first.rest_api_stopped)
                self.assert_true(second.rest_api_stopped)
                # Second call correctly observes REST API already inactive.
                self.assert_false(second.rest_api_was_active)
                self.assert_true(second.background_workers_stopped)
                self.assert_false(server.is_running)
            except Exception as exc:  # noqa: BLE001
                self.assert_true(False, f"second shutdown() raised: {exc!r}")

    def _test_shutdown_orders_rest_api_before_background_workers(self) -> None:
        order_log: list[str] = []
        router = CommandRouter()
        api_router = ApiRouter(command_router=router)
        real_server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)
        real_server.start()
        with tempfile.TemporaryDirectory() as tmp:
            real_bg = _build_real_background_worker_service(Path(tmp), worker_count=1)
            proxy_server = _OrderRecordingRestApiServer(real_server, order_log)
            proxy_bg = _OrderRecordingBackgroundWorkerService(real_bg, order_log)
            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=proxy_server,  # type: ignore[arg-type]
                background_worker_service=proxy_bg,  # type: ignore[arg-type]
                shell=None,
            )
            service.shutdown()
            self.assert_equal(order_log, ["rest_api", "background_workers"])

    # ================= Public-surface guarantees =================

    def _test_module_still_exposes_only_status_and_help(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        module = RuntimeModule(service)
        self.assert_equal(set(module._actions.keys()), {"status", "help"})  # noqa: SLF001
        for forbidden in ("start", "stop", "restart", "reconfigure", "register", "shutdown"):
            self.assert_true(forbidden not in module._actions)  # noqa: SLF001

    def _test_service_exposes_exactly_status_and_shutdown(self) -> None:
        public_methods = [
            name
            for name, member in inspect.getmembers(RuntimeService, predicate=inspect.isfunction)
            if not name.startswith("_")
        ]
        self.assert_equal(sorted(public_methods), ["shutdown", "status"])

    # ================= RuntimeModule formatting =================

    def _test_status_message_includes_scheduler_line_when_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler_service = _build_real_scheduler_service(
                Path(tmp), enabled=True, auto_start=True
            )
            try:
                service = RuntimeService(
                    started_at=time.monotonic(),
                    rest_api_server=None,
                    background_worker_service=None,
                    shell=None,
                    scheduler_service=scheduler_service,
                )
                module = RuntimeModule(service)
                result = module.execute("status", [])
                self.assert_true(result.success)
                self.assert_true("Scheduler : ACTIVE" in result.message)
                self.assert_true("Scheduler jobs registered : 0" in result.message)
            finally:
                _stop_scheduler_tick_loop_for_test_cleanup(scheduler_service)

    def _test_status_message_omits_scheduler_line_when_inactive(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        module = RuntimeModule(service)
        result = module.execute("status", [])
        self.assert_true(result.success)
        self.assert_true("Scheduler : INACTIVE" in result.message)
        self.assert_true("Scheduler jobs registered" not in result.message)

    # ================= Real Bootstrap wiring =================

    def _test_bootstrap_exposes_scheduler_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                self.assert_true(bootstrap.scheduler_service is None)
                bootstrap.initialize()
                self.assert_true(bootstrap.scheduler_service is not None)

    def _test_bootstrap_runtime_service_observes_live_scheduler_service(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                # Whitebox identity check, mirroring EP-059's own
                # construction-ordering-correctness tests.
                self.assert_true(
                    bootstrap.runtime_service._scheduler_service  # noqa: SLF001
                    is bootstrap.scheduler_service
                )

    def _test_bootstrap_runtime_status_reflects_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory, scheduler_section=_SCHEDULER_AUTO_START_SECTION
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.scheduler_service.status().running)
                    result = bootstrap._command_router.dispatch("runtime status")  # noqa: SLF001
                    self.assert_true(result.success)
                    self.assert_true("Scheduler : ACTIVE" in result.message)
                finally:
                    if bootstrap.scheduler_service is not None:
                        _stop_scheduler_tick_loop_for_test_cleanup(bootstrap.scheduler_service)

    # ================= Real Bootstrap shutdown coordination =================

    def _test_bootstrap_shutdown_stops_rest_api_and_background_workers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                api_section=_API_ENABLED_SECTION,
                background_workers_section="background_workers:\n  enabled: true\n  worker_count: 2\n",
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                rest_api_server = bootstrap.rest_api_server
                self.assert_true(rest_api_server is not None)
                self.assert_true(rest_api_server.is_running)
                bootstrap.shutdown()
                self.assert_false(rest_api_server.is_running)

    def _test_bootstrap_shutdown_nulls_both_properties(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                api_section=_API_ENABLED_SECTION,
                background_workers_section="background_workers:\n  enabled: true\n  worker_count: 1\n",
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.rest_api_server is not None)
                self.assert_true(bootstrap.background_worker_service is not None)
                bootstrap.shutdown()
                self.assert_true(bootstrap.rest_api_server is None)
                self.assert_true(bootstrap.background_worker_service is None)

    def _test_bootstrap_shutdown_safe_when_called_twice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory,
                api_section=_API_ENABLED_SECTION,
                background_workers_section="background_workers:\n  enabled: true\n  worker_count: 1\n",
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                try:
                    bootstrap.shutdown()
                    bootstrap.shutdown()
                    self.assert_true(True)
                except Exception as exc:  # noqa: BLE001
                    self.assert_true(False, f"second bootstrap.shutdown() raised: {exc!r}")

    def _test_bootstrap_shutdown_safe_without_initialize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.shutdown()
                    self.assert_true(True)
                except Exception as exc:  # noqa: BLE001
                    self.assert_true(
                        False, f"shutdown() without initialize() raised: {exc!r}"
                    )

    def _test_bootstrap_shutdown_does_not_touch_scheduler_service(self) -> None:
        # EP-061 Owner Decision D3: `RuntimeService.shutdown()` now
        # does stop the Scheduler's tick loop (via the new
        # `SchedulerService.shutdown()`), closing the gap EP-060 Owner
        # Decision D5 deferred -- but `bootstrap.scheduler_service`
        # must still remain populated (not nulled out) after
        # `shutdown()`, unlike REST API/Background Workers, because
        # `SchedulerService` remains a fully usable object once its
        # tick loop is stopped (status()/doctor()/list_jobs()/manual
        # run() all still work). This test's config uses the default
        # `scheduler_section` (`auto_start: false`), so the tick loop
        # is never actually started here either way; the assertions
        # below only cover reference identity/non-nullness, which
        # holds regardless.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                scheduler_service = bootstrap.scheduler_service
                self.assert_true(scheduler_service is not None)
                try:
                    bootstrap.shutdown()
                    self.assert_true(bootstrap.scheduler_service is not None)
                    self.assert_true(bootstrap.scheduler_service is scheduler_service)
                finally:
                    _stop_scheduler_tick_loop_for_test_cleanup(scheduler_service)
