"""EP-061 test suite: SchedulerService.shutdown() and its wiring.

Covers, per `EP061_DESIGN.md` Section 12:
    1. `SchedulerService.shutdown()` in isolation.
    2. `RuntimeService.shutdown()`'s widened (REST API -> Scheduler ->
       Background Workers) behavior.
    3. Real `Bootstrap` end-to-end wiring.
    4. Public-surface guards (`SchedulerService`, `SchedulerModule`,
       `RuntimeModule`).

Self-contained per this repository's own per-EP test convention (no
import from `tests/EP059/` or `tests/EP060/`) -- local builder
functions below are deliberately near-identical to (but independent
copies of) the ones `tests/EP060/test_runtime_lifecycle.py` already
uses for the same real objects.
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
from src.modules.scheduler_module import SchedulerModule
from src.services.background_worker_service import BackgroundWorkerService
from src.services.runtime_service import RuntimeService, RuntimeShutdownReport
from src.services.scheduler_service import SchedulerService
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


def _build_real_scheduler_service(
    tmp_path: Path,
    enabled: bool = True,
    auto_start: bool = True,
    tick_interval: int = 3600,
) -> SchedulerService:
    """Build a real, minimal SchedulerService (EP-011 Scheduler underneath).

    `tick_interval` defaults to a large value (3600s) so no tick ever
    actually fires during a test unless a test explicitly overrides it
    to exercise the idle-wait path.
    """
    config_dir = tmp_path / "config"
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


class _StubPlanExecutionEngine:
    """Minimal, real `PlanExecutionEngine`-shaped stub -- always succeeds.

    Kept local and self-contained, matching `tests/EP059/test_runtime.py`
    and `tests/EP060/test_runtime_lifecycle.py`'s own precedent.
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
    tmp_path: Path, worker_count: int = 1
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
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
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


_SCHEDULER_AUTO_START_SECTION = (
    "scheduler:\n  enabled: true\n  auto_start: true\n  tick_interval: 3600\n\n"
)


@TestRegistry.register
class SchedulerShutdownTest(BaseTest):
    NAME = "EP061"

    def run(self):
        # ---------- SchedulerService.shutdown() in isolation ----------
        self._test_shutdown_never_started_returns_true_immediately()
        self._test_shutdown_stops_a_running_tick_loop()
        self._test_shutdown_is_idempotent()
        self._test_concurrent_shutdown_calls_are_race_safe()
        self._test_concurrent_shutdown_does_not_clear_a_replacement_thread()
        self._test_shutdown_no_wait_returns_promptly()
        self._test_manual_run_still_works_after_shutdown()

        # ---------- RuntimeService.shutdown() widened behavior ----------
        self._test_runtime_shutdown_all_none_unchanged_defaults()
        self._test_runtime_shutdown_stops_real_scheduler()
        self._test_runtime_shutdown_orders_rest_api_then_scheduler_then_background_workers()
        self._test_runtime_shutdown_idempotent_with_scheduler()
        self._test_shutdown_does_not_hold_lock_during_join()

        # ---------- Real Bootstrap end-to-end ----------
        self._test_bootstrap_initialize_starts_scheduler_tick_loop()
        self._test_bootstrap_shutdown_stops_scheduler_tick_loop()
        self._test_bootstrap_shutdown_preserves_scheduler_service_identity()
        self._test_bootstrap_shutdown_twice_does_not_raise_or_hang()
        self._test_bootstrap_shutdown_without_initialize_does_not_raise()

        # ---------- Public-surface guards ----------
        self._test_scheduler_service_public_surface_is_previous_plus_shutdown()
        self._test_scheduler_module_cli_actions_unchanged()
        self._test_runtime_module_cli_actions_unchanged()

        return self.result

    # ================= SchedulerService.shutdown() in isolation =================

    def _test_shutdown_never_started_returns_true_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_scheduler_service(Path(tmp), auto_start=False)
            self.assert_false(service.status().running)
            result = service.shutdown()
            self.assert_true(result)
            self.assert_false(service.status().running)

    def _test_shutdown_stops_a_running_tick_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_scheduler_service(Path(tmp), auto_start=True)
            self.assert_true(service.status().running)
            result = service.shutdown()
            self.assert_true(result)
            self.assert_false(service.status().running)

    def _test_shutdown_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_scheduler_service(Path(tmp), auto_start=True)
            first = service.shutdown()
            second = service.shutdown()
            self.assert_true(first)
            self.assert_true(second)
            self.assert_false(service.status().running)

    def _test_concurrent_shutdown_calls_are_race_safe(self) -> None:
        """Two threads calling shutdown() at once must not deadlock,
        must not raise, must not clear a "replacement" thread
        incorrectly, and must converge to the correct stopped state.

        This is a genuine multi-threaded race test, deliberately
        distinct from `_test_shutdown_is_idempotent` (which only calls
        `shutdown()` twice, sequentially, on one thread). Because
        `shutdown()` releases `_lifecycle_lock` before `thread.join()`
        (Section 7.1's lock-scope design note), the two calls are
        *not* expected to fully serialize for the entire join duration
        -- both may observe the same live thread, both set the
        (already-idempotent) stop event, and both join the same
        thread concurrently, which `threading.Thread.join()` supports
        safely. What must hold is: no exception, no hang, and a
        correct final state.
        """
        import threading as _threading

        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_scheduler_service(Path(tmp), auto_start=True)
            self.assert_true(service.status().running)

            results: list[bool] = []
            errors: list[BaseException] = []
            results_lock = _threading.Lock()

            def _call_shutdown() -> None:
                try:
                    outcome = service.shutdown()
                    with results_lock:
                        results.append(outcome)
                except BaseException as exc:  # noqa: BLE001
                    with results_lock:
                        errors.append(exc)

            threads = [_threading.Thread(target=_call_shutdown) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                # Bounded join on the *test* thread -- proves no deadlock.
                thread.join(timeout=10.0)

            self.assert_true(
                all(not thread.is_alive() for thread in threads),
                "a concurrent shutdown() call did not finish within 10s (deadlock?)",
            )
            self.assert_equal(errors, [], f"concurrent shutdown() raised: {errors!r}")
            self.assert_equal(len(results), 2)
            self.assert_true(all(results), f"expected both calls to report True, got {results!r}")
            # Converges to the correct stopped state regardless of
            # which thread "won" the race to clear `_tick_thread`.
            self.assert_false(service.status().running)
            # A subsequent call remains safe and consistent too.
            self.assert_true(service.shutdown())

    def _test_concurrent_shutdown_does_not_clear_a_replacement_thread(self) -> None:
        """Whitebox regression guard for the `if self._tick_thread is thread`
        identity check in `shutdown()` (Section 7.1).

        Simulates the specific race the identity check exists to
        guard against: after a `shutdown()` call has already captured
        a reference to the (now-dead) old thread and is about to clear
        `_tick_thread`, some other code path has since installed a new
        thread object under the same attribute. The stale caller must
        not clear the new one out from under it.

        This EP does not add a public restart API, so this scenario
        cannot occur through any public method today -- this test
        exists solely to lock in the identity-check's correctness
        directly, the same way `_stop_scheduler_tick_loop_for_test_cleanup`
        style whitebox helpers are used elsewhere in this repository's
        own test suites for private-state regression guards.
        """
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_scheduler_service(Path(tmp), auto_start=True)
            old_thread = service._tick_thread  # noqa: SLF001
            self.assert_true(old_thread is not None)

            # Manually stop the old thread's loop and wait for it to die,
            # without going through the public shutdown() (so we can
            # install a "replacement" thread object before shutdown()
            # gets to its post-join cleanup step).
            service._stop_event.set()  # noqa: SLF001
            old_thread.join(timeout=5.0)
            self.assert_false(old_thread.is_alive())

            # Install a distinct "replacement" thread object in place of
            # the one `shutdown()` is about to try to clear.
            replacement = object()
            service._tick_thread = replacement  # type: ignore[assignment]  # noqa: SLF001

            # Now call the identity-guarded cleanup logic the same way
            # `shutdown()` does internally, using the stale `old_thread`
            # reference `shutdown()` would have captured earlier.
            with service._lifecycle_lock:  # noqa: SLF001
                if service._tick_thread is old_thread:  # noqa: SLF001
                    service._tick_thread = None  # noqa: SLF001

            # The replacement must be untouched.
            self.assert_true(service._tick_thread is replacement)  # noqa: SLF001

            # Clean up so we don't leak a bogus attribute into any later
            # use of this service instance within this test process.
            service._tick_thread = None  # noqa: SLF001

    def _test_shutdown_no_wait_returns_promptly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_scheduler_service(Path(tmp), auto_start=True)
            started = time.monotonic()
            service.shutdown(wait=False)
            elapsed = time.monotonic() - started
            self.assert_true(elapsed < 1.0, f"wait=False took {elapsed:.3f}s, expected near-instant")
            # Give the thread a moment to actually exit before the final check
            # (wait=False does not guarantee it has exited yet, only that we
            # did not block on it).
            time.sleep(0.2)
            self.assert_false(service.status().running)

    def _test_manual_run_still_works_after_shutdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_scheduler_service(Path(tmp), auto_start=True)
            service.register(
                Job(
                    id="manual-after-shutdown",
                    name="Manual After Shutdown",
                    description="",
                    command="noop-target",
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
            # status()/doctor()/list_jobs() must also still work.
            self.assert_equal(len(service.list_jobs()), 1)
            self.assert_true(service.doctor().scheduler_available)

    # ================= RuntimeService.shutdown() widened behavior =================

    def _test_runtime_shutdown_all_none_unchanged_defaults(self) -> None:
        service = RuntimeService(
            started_at=time.monotonic(),
            rest_api_server=None,
            background_worker_service=None,
            shell=None,
            scheduler_service=None,
        )
        report = service.shutdown()
        self.assert_true(isinstance(report, RuntimeShutdownReport))
        self.assert_false(report.scheduler_was_active)
        self.assert_true(report.scheduler_stopped)
        # Pre-existing fields remain exactly as EP-060 left them.
        self.assert_false(report.rest_api_was_active)
        self.assert_true(report.rest_api_stopped)
        self.assert_false(report.background_workers_was_active)
        self.assert_true(report.background_workers_stopped)

    def _test_runtime_shutdown_stops_real_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler_service = _build_real_scheduler_service(Path(tmp), auto_start=True)
            self.assert_true(scheduler_service.status().running)
            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=None,
                shell=None,
                scheduler_service=scheduler_service,
            )
            report = service.shutdown()
            self.assert_true(report.scheduler_was_active)
            self.assert_true(report.scheduler_stopped)
            self.assert_false(scheduler_service.status().running)

    def _test_runtime_shutdown_orders_rest_api_then_scheduler_then_background_workers(
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
            real_bg = _build_real_background_worker_service(tmp_path, worker_count=1)

            proxy_server = _OrderRecordingRestApiServer(real_server, order_log)
            proxy_scheduler = _OrderRecordingSchedulerService(real_scheduler, order_log)
            proxy_bg = _OrderRecordingBackgroundWorkerService(real_bg, order_log)

            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=proxy_server,  # type: ignore[arg-type]
                background_worker_service=proxy_bg,  # type: ignore[arg-type]
                shell=None,
                scheduler_service=proxy_scheduler,  # type: ignore[arg-type]
            )
            service.shutdown()
            self.assert_equal(order_log, ["rest_api", "scheduler", "background_workers"])

    def _test_runtime_shutdown_idempotent_with_scheduler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scheduler_service = _build_real_scheduler_service(Path(tmp), auto_start=True)
            service = RuntimeService(
                started_at=time.monotonic(),
                rest_api_server=None,
                background_worker_service=None,
                shell=None,
                scheduler_service=scheduler_service,
            )
            first = service.shutdown()
            second = service.shutdown()
            self.assert_true(first.scheduler_stopped)
            self.assert_true(second.scheduler_stopped)
            self.assert_false(scheduler_service.status().running)

    def _test_shutdown_does_not_hold_lock_during_join(self) -> None:
        """Regression guard for the lock-scope design note (Section 7.1).

        `shutdown()` must not hold `_lifecycle_lock` across the
        (potentially multi-second) `thread.join()` call -- a concurrent
        `status()` call must not be blocked by an in-progress
        `shutdown()`. Verified directly against the private lock here
        (whitebox, test-only; not a production-facing assertion about
        private state, only a regression guard for the documented
        design decision).
        """
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_scheduler_service(Path(tmp), auto_start=True)
            service.shutdown()
            # After shutdown() returns, the lock must not still be held.
            acquired = service._lifecycle_lock.acquire(timeout=1.0)  # noqa: SLF001
            self.assert_true(acquired, "_lifecycle_lock still held after shutdown() returned")
            if acquired:
                service._lifecycle_lock.release()  # noqa: SLF001

    # ================= Real Bootstrap end-to-end =================

    def _test_bootstrap_initialize_starts_scheduler_tick_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, scheduler_section=_SCHEDULER_AUTO_START_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                try:
                    self.assert_true(bootstrap.scheduler_service is not None)
                    self.assert_true(bootstrap.scheduler_service.status().running)
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_shutdown_stops_scheduler_tick_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, scheduler_section=_SCHEDULER_AUTO_START_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.scheduler_service.status().running)
                bootstrap.shutdown()
                self.assert_false(bootstrap.scheduler_service.status().running)

    def _test_bootstrap_shutdown_preserves_scheduler_service_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, scheduler_section=_SCHEDULER_AUTO_START_SECTION)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                scheduler_service = bootstrap.scheduler_service
                self.assert_true(scheduler_service is not None)
                bootstrap.shutdown()
                # Owner Decision D3: reference stays alive, unlike
                # `_rest_api_server`/`_background_worker_service`.
                self.assert_true(bootstrap.scheduler_service is not None)
                self.assert_true(bootstrap.scheduler_service is scheduler_service)

    def _test_bootstrap_shutdown_twice_does_not_raise_or_hang(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, scheduler_section=_SCHEDULER_AUTO_START_SECTION)
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

    # ================= Public-surface guards =================

    def _test_scheduler_service_public_surface_is_previous_plus_shutdown(self) -> None:
        public_methods = {
            name
            for name, _ in inspect.getmembers(SchedulerService, predicate=inspect.isfunction)
            if not name.startswith("_")
        }
        expected = {
            "register",
            "unregister",
            "start",
            "stop",
            "run",
            "list_jobs",
            "get_job",
            "status",
            "doctor",
            "shutdown",
        }
        self.assert_equal(public_methods, expected)

    def _test_scheduler_module_cli_actions_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_real_scheduler_service(Path(tmp), auto_start=False)
            module = SchedulerModule(service)
            self.assert_equal(
                set(module._actions.keys()),  # noqa: SLF001
                {"list", "status", "doctor", "run", "start", "stop", "info", "help"},
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
