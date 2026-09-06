"""EP-063 test suite: WorkflowSchedulerService.shutdown() and its wiring.

Covers, per `EP063_DESIGN.md` Section 11:
    1. `WorkflowSchedulerService.shutdown()` in isolation, including the
       blocking-tick/timeout behavior that has no analogue in EP-061's
       own test suite (`EP063_DESIGN.md` Section 2.2).
    2. `RuntimeService.status()`/`.shutdown()`'s widened (REST API ->
       Scheduler -> Workflow Scheduler -> Background Workers) behavior.
    3. Real `Bootstrap` end-to-end wiring.
    4. Public-surface guards (`WorkflowSchedulerService`,
       `WorkflowSchedulerModule`, `RuntimeModule`).

Self-contained per this repository's own per-EP test convention (no
import from `tests/EP059/`-`tests/EP062/`) -- local builder functions
below are deliberately near-identical to (but independent copies of)
the ones `tests/EP061/test_scheduler_shutdown.py` already uses for the
same real objects.
"""

from __future__ import annotations

import inspect
import os
import tempfile
import threading as _threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.api.api_router import ApiRouter
from src.core.api.rest_api_server import RestApiServer
from src.core.command_router import CommandRouter
from src.core.config import Config
from src.core.execution.engine import ExecutionEngine
from src.core.execution.process_registry import ProcessRegistry
from src.core.plan_execution.plan_execution_result import PlanExecutionResult
from src.core.scheduler.job import Schedule, ScheduleType
from src.core.scheduler.job_registry import JobRegistry
from src.core.scheduler.scheduler import Scheduler
from src.core.workflow_engine.workflow_definition import (
    WorkflowDefinition,
    WorkflowRequestStep,
)
from src.core.workflow_engine.workflow_engine import WorkflowEngine
from src.core.workflow_engine.workflow_engine_manager import WorkflowEngineManager
from src.core.workflow_scheduler.scheduled_workflow import ScheduledWorkflow
from src.core.workflow_scheduler.scheduled_workflow_registry import ScheduledWorkflowRegistry
from src.core.workflow_scheduler.workflow_scheduler_engine import (
    WorkflowSchedulerEngine,
    WorkflowSchedulerError,
)
from src.modules.runtime_module import RuntimeModule
from src.modules.workflow_scheduler_module import WorkflowSchedulerModule
from src.services.background_worker_service import BackgroundWorkerService
from src.services.runtime_service import RuntimeService, RuntimeShutdownReport
from src.services.scheduler_service import SchedulerService
from src.services.workflow_scheduler_service import WorkflowSchedulerService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

# ================= Shared local builders =================


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
    """Minimal, real `PlanExecutionEngine`-shaped stub -- always succeeds instantly.

    Kept local and self-contained, matching
    `tests/EP061/test_scheduler_shutdown.py`'s own precedent.
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


class _SlowPlanExecutionEngine:
    """Real `PlanExecutionEngine`-shaped stub that blocks before succeeding.

    Simulates a scheduled workflow whose step genuinely takes time to
    run -- the scenario `EP063_DESIGN.md` Section 2.2 identifies as
    the reason `WorkflowSchedulerService.shutdown()` cannot reuse
    `SchedulerService.shutdown()`'s fixed-constant timeout precedent.
    Records when execution started/finished so tests can assert on
    genuine blocking, not merely on the final return value.
    """

    def __init__(self, sleep_seconds: float) -> None:
        self._sleep_seconds = sleep_seconds
        self.started_at: float | None = None
        self.finished_at: float | None = None

    def execute_request(self, request: str) -> PlanExecutionResult:
        self.started_at = time.monotonic()
        time.sleep(self._sleep_seconds)
        self.finished_at = time.monotonic()
        return PlanExecutionResult(
            plan=None,
            step_results=[],
            completed_count=1,
            failed_count=0,
            skipped_count=0,
            success=True,
        )


def _build_real_workflow_engine(
    tmp_path: Path,
    workflow_id: str = "noop",
    plan_execution_engine=None,
) -> WorkflowEngine:
    """Build a real, minimal WorkflowEngine with one single-step definition.

    Writes its own isolated 'workflow_engine.yaml'-shaped config file
    under `tmp_path / "we_config"` so it never collides with the
    Workflow Scheduler's own config file written by
    `_build_real_workflow_scheduler_service` below (both would
    otherwise need to share one `config/config.yaml`, matching
    `tests/EP061/test_scheduler_shutdown.py`'s own
    `_build_real_background_worker_service` precedent of combining
    sections into a single file where the two must share one `Config`
    instance -- not needed here since `WorkflowEngineManager` and
    `WorkflowSchedulerService` are never required to share the same
    `Config` object, only the same `WorkflowEngine` instance).
    """
    config_dir = tmp_path / "we_config"
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
    return WorkflowEngine(
        manager=manager,
        plan_execution_engine=plan_execution_engine or _StubPlanExecutionEngine(),
    )


def _build_real_workflow_scheduler_service(
    tmp_path: Path,
    enabled: bool = True,
    auto_start: bool = True,
    tick_interval: int = 3600,
    shutdown_timeout: object = None,
    plan_execution_engine=None,
    workflow_id: str = "noop",
) -> tuple[WorkflowSchedulerService, WorkflowEngine]:
    """Build a real, minimal WorkflowSchedulerService (EP-034 engine underneath).

    `tick_interval` defaults to a large value (3600s) so no tick ever
    actually fires during a test unless a test explicitly overrides it
    (or drives the tick loop directly) to exercise the automatic path.

    `shutdown_timeout`: if not None, written as
    'workflow_scheduler.shutdown_timeout' verbatim (so a test can pass
    an invalid value, e.g. a negative number or a string, to exercise
    `_resolve_shutdown_timeout()`'s validation). Left out of the
    written config entirely when None, exercising the documented
    default (`EP063_DESIGN.md` Section 6.2).
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    shutdown_timeout_line = (
        f"  shutdown_timeout: {shutdown_timeout!r}\n" if shutdown_timeout is not None else ""
    )
    (config_dir / "config.yaml").write_text(
        "workflow_scheduler:\n"
        f"  enabled: {str(enabled).lower()}\n"
        f"  auto_start: {str(auto_start).lower()}\n"
        f"  tick_interval: {tick_interval}\n"
        f"{shutdown_timeout_line}",
        encoding="utf-8",
    )
    config = Config(config_dir / "config.yaml").load()
    workflow_engine = _build_real_workflow_engine(
        tmp_path, workflow_id=workflow_id, plan_execution_engine=plan_execution_engine
    )
    registry = ScheduledWorkflowRegistry()
    engine = WorkflowSchedulerEngine(registry=registry, workflow_engine=workflow_engine)
    service = WorkflowSchedulerService(config=config, engine=engine)
    return service, workflow_engine


def _register_and_start_due_entry(
    service: WorkflowSchedulerService, entry_id: str = "due-entry", workflow_id: str = "noop"
) -> None:
    """Register a scheduled workflow entry that is already due, and enable it.

    Uses a `ScheduleType.ONCE` schedule with `run_at` in the past, so
    `WorkflowSchedulerEngine.calculate_next_run` (called by `start()`)
    sets `next_run` to that already-past timestamp -- making the entry
    immediately due on the very next `tick()`, with no need to wait
    out a real interval.
    """
    result = service.register(
        ScheduledWorkflow(
            id=entry_id,
            name=entry_id,
            description="",
            workflow_id=workflow_id,
            schedule=Schedule(
                type=ScheduleType.ONCE,
                run_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            ),
            enabled=False,
        )
    )
    assert result.success, f"register() failed: {result.message}"
    start_result = service.start(entry_id)
    assert start_result.success, f"start() failed: {start_result.message}"


def _build_real_scheduler_service(
    tmp_path: Path,
    enabled: bool = True,
    auto_start: bool = True,
    tick_interval: int = 3600,
) -> SchedulerService:
    """Build a real, minimal SchedulerService (EP-011 Scheduler underneath)."""
    config_dir = tmp_path / "sched_config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        "scheduler:\n"
        f"  enabled: {str(enabled).lower()}\n"
        f"  auto_start: {str(auto_start).lower()}\n"
        f"  tick_interval: {tick_interval}\n",
        encoding="utf-8",
    )
    config = Config(config_dir / "config.yaml").load()
    registry = JobRegistry()
    execution_engine = ExecutionEngine(executors=[], registry=ProcessRegistry())
    scheduler = Scheduler(registry=registry, execution_engine=execution_engine)
    return SchedulerService(config=config, scheduler=scheduler)


def _build_real_background_worker_service(
    tmp_path: Path, worker_count: int = 1
) -> BackgroundWorkerService:
    """Build a real, minimal, enabled BackgroundWorkerService."""
    engine = _build_real_workflow_engine(tmp_path)
    config_dir = tmp_path / "bg_config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        f"background_workers:\n  enabled: true\n  worker_count: {worker_count}\n",
        encoding="utf-8",
    )
    config = Config(config_dir / "config.yaml").load()
    return BackgroundWorkerService(config=config, workflow_engine=engine)


class _OrderRecordingRestApiServer:
    """Thin proxy around a real RestApiServer that records call order.

    Duck-typed to exactly the surface `RuntimeService` reads/calls
    (`is_running`, `host`, `port`, `stop()`).
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


class _OrderRecordingSchedulerService:
    """Thin proxy around a real SchedulerService that records call order.

    Duck-typed to exactly the surface `RuntimeService` reads/calls
    (`status()`, `shutdown()`).
    """

    def __init__(self, real: SchedulerService, order_log: list[str]) -> None:
        self._real = real
        self._order_log = order_log

    def status(self):
        return self._real.status()

    def shutdown(self, wait: bool = True, timeout: float | None = None) -> bool:
        self._order_log.append("scheduler")
        return self._real.shutdown(wait=wait, timeout=timeout)


class _OrderRecordingWorkflowSchedulerService:
    """Thin proxy around a real WorkflowSchedulerService that records call order.

    Duck-typed to exactly the surface `RuntimeService` reads/calls
    (`status()`, `shutdown()`).
    """

    def __init__(self, real: WorkflowSchedulerService, order_log: list[str]) -> None:
        self._real = real
        self._order_log = order_log

    def status(self):
        return self._real.status()

    def shutdown(self, wait: bool = True, timeout: float | None = None) -> bool:
        self._order_log.append("workflow_scheduler")
        return self._real.shutdown(wait=wait, timeout=timeout)


class _OrderRecordingBackgroundWorkerService:
    """Thin proxy around a real BackgroundWorkerService that records call order.

    Duck-typed to exactly the surface `RuntimeService` reads/calls
    (`status()`, `shutdown()`).
    """

    def __init__(self, real: BackgroundWorkerService, order_log: list[str]) -> None:
        self._real = real
        self._order_log = order_log

    def status(self):
        return self._real.status()

    def shutdown(self, wait: bool = True, timeout: float | None = None) -> bool:
        self._order_log.append("background_workers")
        return self._real.shutdown(wait=wait, timeout=timeout)


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
    "scheduler:\n  enabled: true\n  auto_start: false\n  tick_interval: 3600\n\n"
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
    "{workflow_scheduler_section}"
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
    workflow_scheduler_section: str = (
        "workflow_scheduler:\n  enabled: true\n  auto_start: false\n"
        "  tick_interval: 3600\n\n"
    ),
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            api_section=api_section,
            background_workers_section=background_workers_section,
            workflow_scheduler_section=workflow_scheduler_section,
        ),
        encoding="utf-8",
    )


_WORKFLOW_SCHEDULER_AUTO_START_SECTION = (
    "workflow_scheduler:\n  enabled: true\n  auto_start: true\n"
    "  tick_interval: 3600\n\n"
)


@TestRegistry.register
class WorkflowSchedulerShutdownTest(BaseTest):
    NAME = "EP063"

    def run(self):
        # ---------- WorkflowSchedulerService.shutdown() in isolation ----------
        self._test_shutdown_never_started_returns_true_immediately()
        self._test_shutdown_stops_a_running_tick_loop()
        self._test_shutdown_is_idempotent()
        self._test_shutdown_no_wait_returns_promptly()
        self._test_manual_run_still_works_after_shutdown()
        self._test_default_shutdown_timeout_is_ten_seconds()
        self._test_configured_shutdown_timeout_is_honored()
        self._test_explicit_timeout_argument_overrides_configured_default()
        self._test_invalid_shutdown_timeout_configuration_raises()

        # ---------- Blocking-tick / timeout semantics (EP-063-specific) ----------
        self._test_shutdown_waits_for_in_progress_tick_to_finish()
        self._test_shutdown_returns_false_when_timeout_exceeded_during_tick()

        # ---------- RuntimeService.status()/.shutdown() widened behavior ----------
        self._test_runtime_status_reports_inactive_workflow_scheduler_by_default()
        self._test_runtime_status_reports_active_workflow_scheduler()
        self._test_runtime_shutdown_all_none_unchanged_defaults()
        self._test_runtime_shutdown_stops_real_workflow_scheduler()
        self._test_runtime_shutdown_orders_rest_scheduler_workflow_scheduler_background_workers()
        self._test_runtime_shutdown_idempotent_with_workflow_scheduler()

        # ---------- Real Bootstrap end-to-end ----------
        self._test_bootstrap_initialize_starts_workflow_scheduler_tick_loop()
        self._test_bootstrap_shutdown_stops_workflow_scheduler_tick_loop()
        self._test_bootstrap_shutdown_preserves_workflow_scheduler_service_identity()
        self._test_bootstrap_shutdown_twice_does_not_raise_or_hang()
        self._test_bootstrap_shutdown_without_initialize_does_not_raise()
        self._test_bootstrap_runtime_status_shows_workflow_scheduler_line()

        # ---------- Public-surface guards ----------
        self._test_workflow_scheduler_service_public_surface_is_previous_plus_shutdown()
        self._test_workflow_scheduler_module_cli_actions_unchanged()
        self._test_runtime_module_cli_actions_unchanged()

        return self.result

    # ================= WorkflowSchedulerService.shutdown() in isolation =================

    def _test_shutdown_never_started_returns_true_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = _build_real_workflow_scheduler_service(Path(tmp), auto_start=False)
            self.assert_false(service.status().running)
            result = service.shutdown()
            self.assert_true(result)
            self.assert_false(service.status().running)

    def _test_shutdown_stops_a_running_tick_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = _build_real_workflow_scheduler_service(Path(tmp), auto_start=True)
            self.assert_true(service.status().running)
            result = service.shutdown()
            self.assert_true(result)
            self.assert_false(service.status().running)

    def _test_shutdown_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = _build_real_workflow_scheduler_service(Path(tmp), auto_start=True)
            first = service.shutdown()
            second = service.shutdown()
            self.assert_true(first)
            self.assert_true(second)
            self.assert_false(service.status().running)

    def _test_shutdown_no_wait_returns_promptly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = _build_real_workflow_scheduler_service(Path(tmp), auto_start=True)
            started = time.monotonic()
            service.shutdown(wait=False)
            elapsed = time.monotonic() - started
            self.assert_true(
                elapsed < 1.0, f"wait=False took {elapsed:.3f}s, expected near-instant"
            )
            # Give the thread a moment to actually exit before the final check
            # (wait=False does not guarantee it has exited yet, only that we
            # did not block on it).
            time.sleep(0.2)
            self.assert_false(service.status().running)

    def _test_manual_run_still_works_after_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = _build_real_workflow_scheduler_service(Path(tmp), auto_start=True)
            service.register(
                ScheduledWorkflow(
                    id="manual-after-shutdown",
                    name="Manual After Shutdown",
                    description="",
                    workflow_id="noop",
                    schedule=Schedule(type=ScheduleType.MANUAL),
                )
            )
            service.shutdown()
            self.assert_false(service.status().running)
            # `run()` must still execute without raising -- the service
            # object itself remains usable; only the automatic loop stopped.
            try:
                result = service.run("manual-after-shutdown")
                self.assert_true(result is not None)
            except Exception as exc:  # noqa: BLE001
                self.assert_true(False, f"run() after shutdown() raised: {exc!r}")
            # status()/list_entries()/get_entry() must also still work.
            self.assert_equal(len(service.list_entries()), 1)
            self.assert_true(service.get_entry("manual-after-shutdown") is not None)

    def _test_default_shutdown_timeout_is_ten_seconds(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = _build_real_workflow_scheduler_service(
                Path(tmp), auto_start=False, shutdown_timeout=None
            )
            self.assert_equal(service._shutdown_timeout, 10.0)  # noqa: SLF001

    def _test_configured_shutdown_timeout_is_honored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = _build_real_workflow_scheduler_service(
                Path(tmp), auto_start=False, shutdown_timeout=0.25
            )
            self.assert_equal(service._shutdown_timeout, 0.25)  # noqa: SLF001

    def _test_explicit_timeout_argument_overrides_configured_default(self) -> None:
        """`shutdown(timeout=...)` must win over the configured default.

        A long configured default (10s) combined with a slow tick and a
        short explicit `timeout` argument must still return `False`
        promptly, proving the explicit argument -- not the configured
        default -- governs this call.
        """
        with tempfile.TemporaryDirectory() as tmp:
            slow = _SlowPlanExecutionEngine(sleep_seconds=2.0)
            service, _ = _build_real_workflow_scheduler_service(
                Path(tmp),
                auto_start=True,
                tick_interval=1,
                shutdown_timeout=10,
                plan_execution_engine=slow,
            )
            _register_and_start_due_entry(service)
            # Wait until the slow tick has genuinely started.
            deadline = time.monotonic() + 5.0
            while slow.started_at is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assert_true(slow.started_at is not None, "tick never started")

            started = time.monotonic()
            result = service.shutdown(timeout=0.2)
            elapsed = time.monotonic() - started
            self.assert_false(result)
            self.assert_true(
                elapsed < 1.5,
                f"explicit timeout=0.2 was not honored over the configured 10s default "
                f"(took {elapsed:.3f}s)",
            )

    def _test_invalid_shutdown_timeout_configuration_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                _build_real_workflow_scheduler_service(
                    Path(tmp), auto_start=False, shutdown_timeout=-1
                )
                self.assert_true(
                    False, "expected WorkflowSchedulerError for a negative shutdown_timeout"
                )
            except WorkflowSchedulerError:
                self.assert_true(True)
            except Exception as exc:  # noqa: BLE001
                self.assert_true(
                    False, f"expected WorkflowSchedulerError, got {type(exc).__name__}: {exc}"
                )

        with tempfile.TemporaryDirectory() as tmp:
            try:
                _build_real_workflow_scheduler_service(
                    Path(tmp), auto_start=False, shutdown_timeout="not-a-number"
                )
                self.assert_true(
                    False, "expected WorkflowSchedulerError for a non-numeric shutdown_timeout"
                )
            except WorkflowSchedulerError:
                self.assert_true(True)
            except Exception as exc:  # noqa: BLE001
                self.assert_true(
                    False, f"expected WorkflowSchedulerError, got {type(exc).__name__}: {exc}"
                )

    # ================= Blocking-tick / timeout semantics =================

    def _test_shutdown_waits_for_in_progress_tick_to_finish(self) -> None:
        """The central EP-063 regression proof (`EP063_DESIGN.md` Section 2.2).

        Unlike `Scheduler.tick()`, `WorkflowSchedulerEngine.tick()` can
        block on `WorkflowEngine.run()`. `shutdown()` must wait for a
        genuinely in-progress tick to finish naturally (up to its
        timeout) rather than abandoning it instantly, and must return
        `True` once it actually has.
        """
        with tempfile.TemporaryDirectory() as tmp:
            slow = _SlowPlanExecutionEngine(sleep_seconds=0.5)
            service, _ = _build_real_workflow_scheduler_service(
                Path(tmp),
                auto_start=True,
                tick_interval=1,
                shutdown_timeout=5,
                plan_execution_engine=slow,
            )
            _register_and_start_due_entry(service)
            deadline = time.monotonic() + 5.0
            while slow.started_at is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assert_true(slow.started_at is not None, "tick never started")

            before_shutdown = time.monotonic()
            result = service.shutdown()
            elapsed = time.monotonic() - before_shutdown

            self.assert_true(result)
            self.assert_false(service.status().running)
            self.assert_true(slow.finished_at is not None, "slow step never finished")
            # shutdown() must not have returned before the in-progress
            # step actually finished -- proves it waited rather than
            # abandoning the thread the instant _stop_event was set.
            self.assert_true(
                slow.finished_at <= before_shutdown + elapsed + 0.05,
                "shutdown() returned before the in-progress tick finished",
            )
            self.assert_true(
                elapsed >= 0.3,
                f"shutdown() returned suspiciously fast ({elapsed:.3f}s) for a 0.5s in-progress "
                "tick -- expected it to actually wait",
            )

    def _test_shutdown_returns_false_when_timeout_exceeded_during_tick(self) -> None:
        """A timeout shorter than the in-progress tick must yield `False`."""
        with tempfile.TemporaryDirectory() as tmp:
            slow = _SlowPlanExecutionEngine(sleep_seconds=2.0)
            service, _ = _build_real_workflow_scheduler_service(
                Path(tmp),
                auto_start=True,
                tick_interval=1,
                shutdown_timeout=5,
                plan_execution_engine=slow,
            )
            _register_and_start_due_entry(service)
            deadline = time.monotonic() + 5.0
            while slow.started_at is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assert_true(slow.started_at is not None, "tick never started")

            result = service.shutdown(timeout=0.2)
            self.assert_false(result)
            # The tick loop's thread is genuinely still alive/finishing
            # its current, still-in-progress step -- not confirmed
            # stopped immediately after a too-short timeout.
            self.assert_true(service._tick_thread is not None)  # noqa: SLF001

            # Let the slow step actually finish so the thread exits
            # naturally and does not leak into a later test.
            deadline = time.monotonic() + 5.0
            while slow.finished_at is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assert_true(slow.finished_at is not None, "slow step never finished")
            # Clean stop now that the blocking step is done.
            service.shutdown(timeout=5)
            self.assert_false(service.status().running)

    # ================= RuntimeService.status()/.shutdown() widened behavior =================

    def _test_runtime_status_reports_inactive_workflow_scheduler_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = _build_real_workflow_scheduler_service(Path(tmp), auto_start=False)
            runtime = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=None,
                shell=None,
                workflow_scheduler_service=service,
            )
            status = runtime.status()
            self.assert_false(status.workflow_scheduler_active)
            self.assert_equal(status.workflow_scheduler_entries_registered, 0)

    def _test_runtime_status_reports_active_workflow_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = _build_real_workflow_scheduler_service(Path(tmp), auto_start=True)
            service.register(
                ScheduledWorkflow(
                    id="entry-1",
                    name="entry-1",
                    description="",
                    workflow_id="noop",
                    schedule=Schedule(type=ScheduleType.MANUAL),
                )
            )
            runtime = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=None,
                shell=None,
                workflow_scheduler_service=service,
            )
            status = runtime.status()
            self.assert_true(status.workflow_scheduler_active)
            self.assert_equal(status.workflow_scheduler_entries_registered, 1)
            service.shutdown()

    def _test_runtime_shutdown_all_none_unchanged_defaults(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
        )
        report = service.shutdown()
        self.assert_true(isinstance(report, RuntimeShutdownReport))
        self.assert_false(report.workflow_scheduler_was_active)
        self.assert_true(report.workflow_scheduler_stopped)
        # Pre-existing fields remain exactly as EP-060/EP-061 left them.
        self.assert_false(report.rest_api_was_active)
        self.assert_true(report.rest_api_stopped)
        self.assert_false(report.background_workers_was_active)
        self.assert_true(report.background_workers_stopped)
        self.assert_false(report.scheduler_was_active)
        self.assert_true(report.scheduler_stopped)

    def _test_runtime_shutdown_stops_real_workflow_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wf_scheduler_service, _ = _build_real_workflow_scheduler_service(
                Path(tmp), auto_start=True
            )
            self.assert_true(wf_scheduler_service.status().running)
            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=None,
                shell=None,
                workflow_scheduler_service=wf_scheduler_service,
            )
            report = service.shutdown()
            self.assert_true(report.workflow_scheduler_was_active)
            self.assert_true(report.workflow_scheduler_stopped)
            self.assert_false(wf_scheduler_service.status().running)

    def _test_runtime_shutdown_orders_rest_scheduler_workflow_scheduler_background_workers(
        self,
    ) -> None:
        order_log: list[str] = []
        router = CommandRouter()
        api_router = ApiRouter(command_router=router)
        real_server = RestApiServer(api_router=api_router, host="127.0.0.1", port=0)
        real_server.start()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            real_scheduler = _build_real_scheduler_service(tmp_path, auto_start=True)
            real_wf_scheduler, _ = _build_real_workflow_scheduler_service(
                tmp_path, auto_start=True
            )
            real_bg = _build_real_background_worker_service(tmp_path, worker_count=1)

            proxy_server = _OrderRecordingRestApiServer(real_server, order_log)
            proxy_scheduler = _OrderRecordingSchedulerService(real_scheduler, order_log)
            proxy_wf_scheduler = _OrderRecordingWorkflowSchedulerService(
                real_wf_scheduler, order_log
            )
            proxy_bg = _OrderRecordingBackgroundWorkerService(real_bg, order_log)

            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=proxy_server,  # type: ignore[arg-type]
                background_worker_service=proxy_bg,  # type: ignore[arg-type]
                shell=None,
                scheduler_service=proxy_scheduler,  # type: ignore[arg-type]
                workflow_scheduler_service=proxy_wf_scheduler,  # type: ignore[arg-type]
            )
            service.shutdown()
            self.assert_equal(
                order_log,
                ["rest_api", "scheduler", "workflow_scheduler", "background_workers"],
            )

    def _test_runtime_shutdown_idempotent_with_workflow_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wf_scheduler_service, _ = _build_real_workflow_scheduler_service(
                Path(tmp), auto_start=True
            )
            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=None,
                shell=None,
                workflow_scheduler_service=wf_scheduler_service,
            )
            first = service.shutdown()
            second = service.shutdown()
            self.assert_true(first.workflow_scheduler_stopped)
            self.assert_true(second.workflow_scheduler_stopped)
            self.assert_false(wf_scheduler_service.status().running)

    # ================= Real Bootstrap end-to-end =================

    def _test_bootstrap_initialize_starts_workflow_scheduler_tick_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory, workflow_scheduler_section=_WORKFLOW_SCHEDULER_AUTO_START_SECTION
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                try:
                    self.assert_true(bootstrap.workflow_scheduler_service is not None)
                    self.assert_true(bootstrap.workflow_scheduler_service.status().running)
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_shutdown_stops_workflow_scheduler_tick_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory, workflow_scheduler_section=_WORKFLOW_SCHEDULER_AUTO_START_SECTION
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.workflow_scheduler_service.status().running)
                bootstrap.shutdown()
                self.assert_false(bootstrap.workflow_scheduler_service.status().running)

    def _test_bootstrap_shutdown_preserves_workflow_scheduler_service_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory, workflow_scheduler_section=_WORKFLOW_SCHEDULER_AUTO_START_SECTION
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                wf_scheduler_service = bootstrap.workflow_scheduler_service
                self.assert_true(wf_scheduler_service is not None)
                bootstrap.shutdown()
                # Owner Decision D4: reference stays alive, unlike
                # `_rest_api_server`/`_background_worker_service`.
                self.assert_true(bootstrap.workflow_scheduler_service is not None)
                self.assert_true(bootstrap.workflow_scheduler_service is wf_scheduler_service)

    def _test_bootstrap_shutdown_twice_does_not_raise_or_hang(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory, workflow_scheduler_section=_WORKFLOW_SCHEDULER_AUTO_START_SECTION
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                try:
                    bootstrap.shutdown()
                    bootstrap.shutdown()
                    self.assert_true(True)
                except Exception as exc:  # noqa: BLE001
                    self.assert_true(False, f"second shutdown() raised: {exc!r}")

    def _test_bootstrap_shutdown_without_initialize_does_not_raise(self) -> None:
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

    def _test_bootstrap_runtime_status_shows_workflow_scheduler_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(
                directory, workflow_scheduler_section=_WORKFLOW_SCHEDULER_AUTO_START_SECTION
            )
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                try:
                    module = RuntimeModule(bootstrap.runtime_service)
                    result = module.execute("status", [])
                    self.assert_true(result.success)
                    self.assert_true("Workflow Scheduler : ACTIVE" in result.message)
                    self.assert_true("Workflow Scheduler entries registered : 0" in result.message)
                finally:
                    bootstrap.shutdown()

    # ================= Public-surface guards =================

    def _test_workflow_scheduler_service_public_surface_is_previous_plus_shutdown(
        self,
    ) -> None:
        public_methods = {
            name
            for name, _ in inspect.getmembers(
                WorkflowSchedulerService, predicate=inspect.isfunction
            )
            if not name.startswith("_")
        }
        expected = {
            "register",
            "unregister",
            "start",
            "stop",
            "run",
            "list_entries",
            "get_entry",
            "status",
            "shutdown",
        }
        self.assert_equal(public_methods, expected)

    def _test_workflow_scheduler_module_cli_actions_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = _build_real_workflow_scheduler_service(Path(tmp), auto_start=False)
            module = WorkflowSchedulerModule(service)
            self.assert_equal(
                set(module._actions.keys()),  # noqa: SLF001
                {"list", "status", "run", "start", "stop", "info", "help"},
            )
            for forbidden in ("shutdown", "stop-loop", "kill"):
                self.assert_true(forbidden not in module._actions)  # noqa: SLF001

    def _test_runtime_module_cli_actions_unchanged(self) -> None:
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
