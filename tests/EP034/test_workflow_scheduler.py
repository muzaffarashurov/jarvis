"""Real engineering tests for EP-034 - Workflow Scheduler.

Builds real `ScheduledWorkflow`/`ScheduledWorkflowRegistry`/
`WorkflowSchedulerEngine`/`WorkflowSchedulerService`/
`WorkflowSchedulerModule` instances -- composed, where needed, with a
real EP-033 `WorkflowEngine` (itself backed by a duck-typed
`PlanExecutionEngine` stand-in, the same technique EP-033's own test
suite used for EP-030) -- and drives them exactly as a caller would,
no mocked internals, matching every other EP's test suite in this
project (see tests/EP033/test_workflow_engine.py).

Workflow Scheduler (EP-034) is a new, independent package
(`src/core/workflow_scheduler/`) that gives an EP-033
`WorkflowDefinition` a time trigger, by calling EP-033's
already-existing `WorkflowEngine.run()` exclusively. This suite covers:

1. The domain model: `ScheduledWorkflow`, and reused EP-011
   `Schedule`/`ScheduleType`/`JobStatus`.
2. `ScheduledWorkflowRegistry`: register/unregister/get/list, duplicate
   and unknown-id handling.
3. `WorkflowSchedulerEngine`: `calculate_next_run` for every
   `ScheduleType` (manual/once/interval/daily/weekly/cron),
   register/remove/start/stop/run_now, `tick()` dispatch, failure
   isolation.
4. `WorkflowSchedulerService`: configuration-driven construction,
   the background tick loop (start/stop safety), and every CLI-facing
   method.
5. `WorkflowSchedulerModule`: every CLI command ("status", "list",
   "info", "start", "stop", "run", "help").
6. Bootstrap wiring: real construction from the same `WorkflowEngine`
   built for EP-033, graceful degradation on invalid configuration,
   and skipping entirely when the Workflow Engine itself is
   unavailable.
7. Backward compatibility: EP-029/030/031/032/033's own behavior is
   provably unaffected, AND EP-011's active `src/core/scheduler/`/
   `SchedulerService`/`SchedulerModule`/`"scheduler"` CLI namespace/
   `scheduler.*` config/default jobs remain completely untouched and
   still function exactly as before.
8. Architecture compliance: no forbidden imports, no private-API
   access into `WorkflowEngine`, correct reuse of EP-011's pure value
   types, no collision with EP-011's active Scheduler classes.
"""

from __future__ import annotations

import inspect
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.config import Config
from src.core.plan_execution.plan_execution_result import PlanExecutionResult
from src.core.scheduler.job import JobStatus, Schedule, ScheduleType
from src.core.workflow_engine.workflow_definition import WorkflowDefinition, WorkflowRequestStep
from src.core.workflow_engine.workflow_engine import WorkflowEngine
from src.core.workflow_engine.workflow_engine_manager import WorkflowEngineManager
from src.core.workflow_scheduler import workflow_scheduler_engine as workflow_scheduler_engine_module
from src.core.workflow_scheduler.scheduled_workflow import ScheduledWorkflow
from src.core.workflow_scheduler.scheduled_workflow_registry import ScheduledWorkflowRegistry
from src.core.workflow_scheduler.workflow_scheduler_engine import (
    WorkflowSchedulerEngine,
    WorkflowSchedulerError,
)
from src.modules.workflow_scheduler_module import WorkflowSchedulerModule
from src.services.workflow_scheduler_service import WorkflowSchedulerService
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


_CONFIG_CACHE: dict[str, Config] = {}


def _write_config(directory: Path, sections: str) -> Config:
    """Return a Config for `sections`, parsing it at most once per distinct text."""
    cached = _CONFIG_CACHE.get(sections)
    if cached is not None:
        return cached

    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(sections, encoding="utf-8")
    config = Config(config_path).load()
    _CONFIG_CACHE[sections] = config
    return config


_WORKFLOW_ENGINE_ONLY_YAML = (
    "workflow_engine:\n"
    "  enabled: true\n"
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: true\n"
)

_DEFAULT_WORKFLOW_SCHEDULER_YAML = (
    "workflow_scheduler:\n"
    "  enabled: true\n"
    "  auto_start: false\n"
    "  tick_interval: 5\n"
)

_DISABLED_WORKFLOW_SCHEDULER_YAML = (
    "workflow_scheduler:\n"
    "  enabled: false\n"
    "  auto_start: false\n"
    "  tick_interval: 5\n"
)

_AUTO_START_FAST_TICK_YAML = (
    "workflow_scheduler:\n"
    "  enabled: true\n"
    "  auto_start: true\n"
    "  tick_interval: 0.05\n"
)


class _StubPlanExecutionEngine:
    """A minimal, duck-typed stand-in for EP-030's PlanExecutionEngine.

    Identical technique to tests/EP033/test_workflow_engine.py's own
    `_StubPlanExecutionEngine` -- WorkflowEngine only ever calls
    `execute_request()` on the object it is given.
    """

    def __init__(self, failing_requests: frozenset = frozenset()) -> None:
        self._failing_requests = failing_requests
        self.calls: list[str] = []

    def execute_request(self, request: str) -> PlanExecutionResult:
        self.calls.append(request)
        success = request not in self._failing_requests
        return PlanExecutionResult(
            plan=None,
            step_results=[],
            completed_count=1 if success else 0,
            failed_count=0 if success else 1,
            skipped_count=0,
            success=success,
        )


def _build_workflow_engine(
    tmp_path: Path, failing_requests: frozenset = frozenset()
) -> tuple[WorkflowEngine, WorkflowEngineManager]:
    """Build a real WorkflowEngine (EP-033) backed by a stub PlanExecutionEngine."""
    config = _write_config(tmp_path, _WORKFLOW_ENGINE_ONLY_YAML)
    manager = WorkflowEngineManager(config=config)
    stub = _StubPlanExecutionEngine(failing_requests=failing_requests)
    engine = WorkflowEngine(manager=manager, plan_execution_engine=stub)
    return engine, manager


def _register_workflow(manager: WorkflowEngineManager, workflow_id: str, request: str = "do it") -> None:
    manager.register_definition(
        WorkflowDefinition(
            id=workflow_id,
            name=workflow_id,
            description="",
            enabled=True,
            steps=(WorkflowRequestStep(name="Step", request=request),),
        )
    )


def _scheduled_workflow(
    entry_id: str = "sw1",
    workflow_id: str = "wf1",
    schedule: Schedule | None = None,
    enabled: bool = True,
) -> ScheduledWorkflow:
    return ScheduledWorkflow(
        id=entry_id,
        name=entry_id,
        description="A test scheduled workflow.",
        workflow_id=workflow_id,
        schedule=schedule or Schedule(type=ScheduleType.MANUAL),
        enabled=enabled,
    )


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
    "  enabled: {workflow_engine_enabled}\n"
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: true\n\n"
    "workflow_scheduler:\n"
    "  enabled: {workflow_scheduler_enabled}\n"
    "  auto_start: false\n"
    "  tick_interval: 5\n"
)


def _write_full_bootstrap_config(
    directory: Path,
    workflow_engine_enabled: bool = True,
    workflow_scheduler_enabled: bool = True,
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            workflow_engine_enabled=str(workflow_engine_enabled).lower(),
            workflow_scheduler_enabled=str(workflow_scheduler_enabled).lower(),
        ),
        encoding="utf-8",
    )


@TestRegistry.register
class WorkflowSchedulerTest(BaseTest):
    NAME = "EP034"

    def run(self):
        # ---------- Domain model / reuse of EP-011 value types ----------
        self._test_scheduled_workflow_construction()
        self._test_reuses_ep011_schedule_and_status_types()

        # ---------- ScheduledWorkflowRegistry ----------
        self._test_registry_register_and_get()
        self._test_registry_duplicate_raises()
        self._test_registry_unregister_unknown_raises()
        self._test_registry_list()

        # ---------- WorkflowSchedulerEngine: calculate_next_run ----------
        self._test_next_run_manual_is_none()
        self._test_next_run_once_before_run()
        self._test_next_run_once_after_run_is_none()
        self._test_next_run_once_missing_run_at_raises()
        self._test_next_run_interval()
        self._test_next_run_interval_invalid_raises()
        self._test_next_run_daily()
        self._test_next_run_weekly()
        self._test_next_run_weekly_missing_day_raises()
        self._test_next_run_cron_is_none()

        # ---------- WorkflowSchedulerEngine: lifecycle ----------
        self._test_engine_register_and_remove()
        self._test_engine_register_duplicate_raises()
        self._test_engine_remove_unknown_raises()
        self._test_engine_start_unknown_raises()
        self._test_engine_start_sets_next_run()
        self._test_engine_stop_clears_next_run()
        self._test_engine_run_now_success()
        self._test_engine_run_now_failure()
        self._test_engine_run_now_unknown_raises()
        self._test_engine_run_now_workflow_missing_reports_failure()
        self._test_engine_tick_dispatches_due_entries()
        self._test_engine_tick_ignores_disabled_and_not_due()

        # ---------- WorkflowSchedulerService ----------
        self._test_service_register_run_status()
        self._test_service_start_stop()
        self._test_service_disabled_rejects_operations()
        self._test_service_tick_loop_start_stop()
        self._test_service_auto_start_from_config()

        # ---------- WorkflowSchedulerModule (CLI) ----------
        self._test_cli_help_lists_commands()
        self._test_cli_status_command()
        self._test_cli_list_command()
        self._test_cli_info_command_usage_and_result()
        self._test_cli_start_stop_commands()
        self._test_cli_run_command()
        self._test_cli_unknown_action()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_registers_workflow_scheduler_module()
        self._test_bootstrap_disabled_workflow_scheduler_still_boots()
        self._test_bootstrap_skipped_when_workflow_engine_unavailable()

        # ---------- Backward compatibility ----------
        self._test_bootstrap_workflow_engine_service_unaffected()
        self._test_bootstrap_collaboration_service_unaffected()
        self._test_ep011_scheduler_untouched_and_functional()

        # ---------- Architectural acceptance criteria ----------
        self._test_no_forbidden_imports()
        self._test_no_private_api_access_on_workflow_engine()
        self._test_cli_namespace_is_autoflow()

        return self.result

    # ---------- Domain model ----------

    def _test_scheduled_workflow_construction(self) -> None:
        entry = _scheduled_workflow()
        self.assert_equal(entry.id, "sw1")
        self.assert_equal(entry.workflow_id, "wf1")
        self.assert_true(entry.enabled)
        self.assert_equal(entry.status, JobStatus.IDLE)

    def _test_reuses_ep011_schedule_and_status_types(self) -> None:
        entry = _scheduled_workflow(schedule=Schedule(type=ScheduleType.INTERVAL, interval_seconds=60))
        self.assert_true(isinstance(entry.schedule, Schedule))
        self.assert_equal(entry.schedule.type, ScheduleType.INTERVAL)
        self.assert_true(isinstance(entry.status, JobStatus))

    # ---------- ScheduledWorkflowRegistry ----------

    def _test_registry_register_and_get(self) -> None:
        registry = ScheduledWorkflowRegistry()
        registry.register(_scheduled_workflow("a"))
        self.assert_equal(registry.get("a").id, "a")
        self.assert_true(registry.get("does-not-exist") is None)

    def _test_registry_duplicate_raises(self) -> None:
        registry = ScheduledWorkflowRegistry()
        registry.register(_scheduled_workflow("a"))
        try:
            registry.register(_scheduled_workflow("a"))
            self.assert_true(False, "Expected ValueError")
        except ValueError:
            self.result.add_pass()

    def _test_registry_unregister_unknown_raises(self) -> None:
        registry = ScheduledWorkflowRegistry()
        try:
            registry.unregister("does-not-exist")
            self.assert_true(False, "Expected KeyError")
        except KeyError:
            self.result.add_pass()

    def _test_registry_list(self) -> None:
        registry = ScheduledWorkflowRegistry()
        registry.register(_scheduled_workflow("a"))
        registry.register(_scheduled_workflow("b"))
        ids = sorted(entry.id for entry in registry.list())
        self.assert_equal(ids, ["a", "b"])

    # ---------- calculate_next_run ----------

    def _build_engine_only(self, tmp_path: Path) -> WorkflowSchedulerEngine:
        workflow_engine, manager = _build_workflow_engine(tmp_path)
        _register_workflow(manager, "wf1")
        return WorkflowSchedulerEngine(registry=ScheduledWorkflowRegistry(), workflow_engine=workflow_engine)

    def _test_next_run_manual_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            entry = _scheduled_workflow(schedule=Schedule(type=ScheduleType.MANUAL))
            self.assert_true(engine.calculate_next_run(entry) is None)

    def _test_next_run_once_before_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            run_at = datetime.now(timezone.utc) + timedelta(hours=1)
            entry = _scheduled_workflow(schedule=Schedule(type=ScheduleType.ONCE, run_at=run_at))
            self.assert_equal(engine.calculate_next_run(entry), run_at)

    def _test_next_run_once_after_run_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            run_at = datetime.now(timezone.utc) + timedelta(hours=1)
            entry = _scheduled_workflow(schedule=Schedule(type=ScheduleType.ONCE, run_at=run_at))
            entry.last_run = datetime.now(timezone.utc)
            self.assert_true(engine.calculate_next_run(entry) is None)

    def _test_next_run_once_missing_run_at_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            entry = _scheduled_workflow(schedule=Schedule(type=ScheduleType.ONCE))
            try:
                engine.calculate_next_run(entry)
                self.assert_true(False, "Expected WorkflowSchedulerError")
            except WorkflowSchedulerError:
                self.result.add_pass()

    def _test_next_run_interval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            entry = _scheduled_workflow(schedule=Schedule(type=ScheduleType.INTERVAL, interval_seconds=60))
            before = datetime.now(timezone.utc)
            next_run = engine.calculate_next_run(entry)
            self.assert_true(next_run is not None)
            self.assert_true(next_run >= before + timedelta(seconds=59))

    def _test_next_run_interval_invalid_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            entry = _scheduled_workflow(schedule=Schedule(type=ScheduleType.INTERVAL, interval_seconds=0))
            try:
                engine.calculate_next_run(entry)
                self.assert_true(False, "Expected WorkflowSchedulerError")
            except WorkflowSchedulerError:
                self.result.add_pass()

    def _test_next_run_daily(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            entry = _scheduled_workflow(schedule=Schedule(type=ScheduleType.DAILY, time_of_day="00:00"))
            next_run = engine.calculate_next_run(entry)
            self.assert_true(next_run is not None)
            self.assert_true(next_run > datetime.now(timezone.utc))

    def _test_next_run_weekly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            entry = _scheduled_workflow(
                schedule=Schedule(type=ScheduleType.WEEKLY, time_of_day="00:00", day_of_week=0)
            )
            next_run = engine.calculate_next_run(entry)
            self.assert_true(next_run is not None)
            self.assert_equal(next_run.weekday(), 0)
            self.assert_true(next_run > datetime.now(timezone.utc))

    def _test_next_run_weekly_missing_day_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            entry = _scheduled_workflow(schedule=Schedule(type=ScheduleType.WEEKLY, time_of_day="00:00"))
            try:
                engine.calculate_next_run(entry)
                self.assert_true(False, "Expected WorkflowSchedulerError")
            except WorkflowSchedulerError:
                self.result.add_pass()

    def _test_next_run_cron_is_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            entry = _scheduled_workflow(schedule=Schedule(type=ScheduleType.CRON, cron_expression="* * * * *"))
            self.assert_true(engine.calculate_next_run(entry) is None)

    # ---------- WorkflowSchedulerEngine: lifecycle ----------

    def _test_engine_register_and_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            engine.register_entry(_scheduled_workflow("a"))
            self.assert_true(engine.get_entry("a") is not None)
            engine.remove_entry("a")
            self.assert_true(engine.get_entry("a") is None)

    def _test_engine_register_duplicate_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            engine.register_entry(_scheduled_workflow("a"))
            try:
                engine.register_entry(_scheduled_workflow("a"))
                self.assert_true(False, "Expected WorkflowSchedulerError")
            except WorkflowSchedulerError:
                self.result.add_pass()

    def _test_engine_remove_unknown_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            try:
                engine.remove_entry("does-not-exist")
                self.assert_true(False, "Expected WorkflowSchedulerError")
            except WorkflowSchedulerError:
                self.result.add_pass()

    def _test_engine_start_unknown_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            try:
                engine.start_entry("does-not-exist")
                self.assert_true(False, "Expected WorkflowSchedulerError")
            except WorkflowSchedulerError:
                self.result.add_pass()

    def _test_engine_start_sets_next_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            entry = _scheduled_workflow(
                "a", schedule=Schedule(type=ScheduleType.INTERVAL, interval_seconds=60), enabled=False
            )
            engine.register_entry(entry)
            updated = engine.start_entry("a")
            self.assert_true(updated.enabled)
            self.assert_true(updated.next_run is not None)

    def _test_engine_stop_clears_next_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            entry = _scheduled_workflow("a", schedule=Schedule(type=ScheduleType.INTERVAL, interval_seconds=60))
            engine.register_entry(entry)
            engine.start_entry("a")
            updated = engine.stop_entry("a")
            self.assert_false(updated.enabled)
            self.assert_true(updated.next_run is None)
            self.assert_equal(updated.status, JobStatus.DISABLED)

    def _test_engine_run_now_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow_engine, manager = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "wf1")
            engine = WorkflowSchedulerEngine(registry=ScheduledWorkflowRegistry(), workflow_engine=workflow_engine)
            engine.register_entry(_scheduled_workflow("a", "wf1"))
            updated = engine.run_now("a")
            self.assert_equal(updated.status, JobStatus.SUCCESS)
            self.assert_true(updated.last_run is not None)

    def _test_engine_run_now_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow_engine, manager = _build_workflow_engine(Path(tmp), failing_requests=frozenset({"do it"}))
            _register_workflow(manager, "wf1")
            engine = WorkflowSchedulerEngine(registry=ScheduledWorkflowRegistry(), workflow_engine=workflow_engine)
            engine.register_entry(_scheduled_workflow("a", "wf1"))
            updated = engine.run_now("a")
            self.assert_equal(updated.status, JobStatus.FAILED)

    def _test_engine_run_now_unknown_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))
            try:
                engine.run_now("does-not-exist")
                self.assert_true(False, "Expected WorkflowSchedulerError")
            except WorkflowSchedulerError:
                self.result.add_pass()

    def _test_engine_run_now_workflow_missing_reports_failure(self) -> None:
        """A ScheduledWorkflow referencing an unregistered workflow_id fails gracefully."""
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine_only(Path(tmp))  # only "wf1" is registered
            engine.register_entry(_scheduled_workflow("a", "does-not-exist-workflow"))
            updated = engine.run_now("a")
            self.assert_equal(updated.status, JobStatus.FAILED)

    def _test_engine_tick_dispatches_due_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow_engine, manager = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "wf1")
            engine = WorkflowSchedulerEngine(registry=ScheduledWorkflowRegistry(), workflow_engine=workflow_engine)
            entry = _scheduled_workflow("a", "wf1", schedule=Schedule(type=ScheduleType.INTERVAL, interval_seconds=60))
            engine.register_entry(entry)
            entry.next_run = datetime.now(timezone.utc) - timedelta(seconds=1)  # already due
            executed = engine.tick()
            self.assert_equal(len(executed), 1)
            self.assert_equal(executed[0].id, "a")
            self.assert_equal(executed[0].status, JobStatus.SUCCESS)

    def _test_engine_tick_ignores_disabled_and_not_due(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workflow_engine, manager = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "wf1")
            engine = WorkflowSchedulerEngine(registry=ScheduledWorkflowRegistry(), workflow_engine=workflow_engine)

            disabled_entry = _scheduled_workflow("disabled", "wf1", enabled=False)
            disabled_entry.next_run = datetime.now(timezone.utc) - timedelta(seconds=1)
            engine.register_entry(disabled_entry)

            not_due_entry = _scheduled_workflow(
                "not-due", "wf1", schedule=Schedule(type=ScheduleType.INTERVAL, interval_seconds=3600)
            )
            not_due_entry.next_run = datetime.now(timezone.utc) + timedelta(hours=1)
            engine.register_entry(not_due_entry)

            executed = engine.tick()
            self.assert_equal(executed, [])

    # ---------- WorkflowSchedulerService ----------

    def _build_service(self, tmp_path: Path, yaml_text: str = _DEFAULT_WORKFLOW_SCHEDULER_YAML) -> WorkflowSchedulerService:
        workflow_engine, manager = _build_workflow_engine(tmp_path)
        _register_workflow(manager, "wf1")
        engine = WorkflowSchedulerEngine(registry=ScheduledWorkflowRegistry(), workflow_engine=workflow_engine)
        config = _write_config(tmp_path, yaml_text)
        return WorkflowSchedulerService(config=config, engine=engine)

    def _test_service_register_run_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.register(_scheduled_workflow("a", "wf1"))
            self.assert_true(result.success)

            run_result = service.run("a")
            self.assert_true(run_result.success)

            status = service.status()
            self.assert_equal(status.entries_registered, 1)
            self.assert_equal(status.entries_enabled, 1)

            self.assert_true(service.get_entry("a") is not None)
            self.assert_equal(len(service.list_entries()), 1)

    def _test_service_start_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            service.register(_scheduled_workflow("a", "wf1", enabled=False))
            start_result = service.start("a")
            self.assert_true(start_result.success)
            stop_result = service.stop("a")
            self.assert_true(stop_result.success)
            unknown_result = service.start("does-not-exist")
            self.assert_false(unknown_result.success)

    def _test_service_disabled_rejects_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp), _DISABLED_WORKFLOW_SCHEDULER_YAML)
            result = service.register(_scheduled_workflow("a", "wf1"))
            self.assert_false(result.success)
            self.assert_true("stopped" in result.message.lower())

    def _test_service_tick_loop_start_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            self.assert_false(service.status().running)
            service._start_tick_loop()  # noqa: SLF001
            self.assert_true(service.status().running)
            service._stop_event.set()  # noqa: SLF001
            service._tick_thread.join(timeout=2)  # noqa: SLF001
            self.assert_false(service.status().running)

    def _test_service_auto_start_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            workflow_engine, manager = _build_workflow_engine(directory)
            _register_workflow(manager, "wf1")
            sched_engine = WorkflowSchedulerEngine(
                registry=ScheduledWorkflowRegistry(), workflow_engine=workflow_engine
            )
            config = _write_config(directory / "autostart", _AUTO_START_FAST_TICK_YAML)
            service = WorkflowSchedulerService(config=config, engine=sched_engine)
            try:
                self.assert_true(service.status().running)
            finally:
                service._stop_event.set()  # noqa: SLF001
                if service._tick_thread is not None:  # noqa: SLF001
                    service._tick_thread.join(timeout=2)  # noqa: SLF001

    # ---------- WorkflowSchedulerModule (CLI) ----------

    def _test_cli_help_lists_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = WorkflowSchedulerModule(self._build_service(Path(tmp)))
            result = module.execute("help", [])
            self.assert_true(result.success)
            self.assert_true("autoflow run" in result.message)

    def _test_cli_status_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = WorkflowSchedulerModule(self._build_service(Path(tmp)))
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Workflow Scheduler Status" in result.message)

    def _test_cli_list_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = WorkflowSchedulerModule(service)
            empty = module.execute("list", [])
            self.assert_true("none registered" in empty.message)

            service.register(_scheduled_workflow("a", "wf1"))
            result = module.execute("list", [])
            self.assert_true("a" in result.message)
            self.assert_true("wf1" in result.message)

    def _test_cli_info_command_usage_and_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = WorkflowSchedulerModule(service)
            usage = module.execute("info", [])
            self.assert_false(usage.success)

            unknown = module.execute("info", ["does-not-exist"])
            self.assert_false(unknown.success)

            service.register(_scheduled_workflow("a", "wf1"))
            result = module.execute("info", ["a"])
            self.assert_true(result.success)
            self.assert_true("wf1" in result.message)

    def _test_cli_start_stop_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = WorkflowSchedulerModule(service)
            service.register(_scheduled_workflow("a", "wf1", enabled=False))
            usage = module.execute("start", [])
            self.assert_false(usage.success)
            result = module.execute("start", ["a"])
            self.assert_true(result.success)
            result = module.execute("stop", ["a"])
            self.assert_true(result.success)

    def _test_cli_run_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = WorkflowSchedulerModule(service)
            usage = module.execute("run", [])
            self.assert_false(usage.success)

            service.register(_scheduled_workflow("a", "wf1"))
            result = module.execute("run", ["a"])
            self.assert_true(result.success)

    def _test_cli_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = WorkflowSchedulerModule(self._build_service(Path(tmp)))
            result = module.execute("bogus", [])
            self.assert_false(result.success)
            self.assert_true("autoflow help" in result.message)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_workflow_scheduler_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.workflow_scheduler_service is not None)
                self.assert_true("autoflow" in bootstrap._command_router.module_names)  # noqa: SLF001

    def _test_bootstrap_disabled_workflow_scheduler_still_boots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, workflow_scheduler_enabled=False)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.workflow_scheduler_service is not None)
                self.assert_false(bootstrap.workflow_scheduler_service.status().running)

    def _test_bootstrap_skipped_when_workflow_engine_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, workflow_engine_enabled=True)
            # Force an invalid 'workflow_engine.default_provider' so EP-033 itself
            # fails to construct, leaving `workflow_engine_for_scheduler` None.
            config_text = _FULL_BOOTSTRAP_CONFIG_YAML.format(
                workflow_engine_enabled="true", workflow_scheduler_enabled="true"
            ).replace('default_provider: "workflow_engine"\n  stop_on_failure', 'default_provider: ""\n  stop_on_failure')
            config_dir = directory / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.yaml").write_text(config_text, encoding="utf-8")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()  # must not raise
                self.assert_true(bootstrap.workflow_engine_service is None)
                self.assert_true(bootstrap.workflow_scheduler_service is None)

    # ---------- Backward compatibility ----------

    def _test_bootstrap_workflow_engine_service_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                status = bootstrap.workflow_engine_service.status()
                self.assert_equal(status.current_provider, "workflow_engine")

    def _test_bootstrap_collaboration_service_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                status = bootstrap.collaboration_service.status()
                self.assert_equal(status.current_provider, "collaboration")

    def _test_ep011_scheduler_untouched_and_functional(self) -> None:
        """EP-011's active Scheduler/CLI/config/default jobs remain exactly as before EP-034."""
        from src.core.scheduler.job import Job
        from src.core.scheduler.job_registry import JobRegistry
        from src.core.scheduler.scheduler import Scheduler
        from src.modules.scheduler_module import SchedulerModule
        from src.services.scheduler_service import SchedulerService

        self.assert_true(Job is not None)
        self.assert_true(JobRegistry is not None)
        self.assert_true(Scheduler is not None)
        self.assert_true(SchedulerModule is not None)
        self.assert_true(SchedulerService is not None)

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                # EP-011's "scheduler" CLI namespace still registered and functional.
                self.assert_true("scheduler" in bootstrap._command_router.module_names)  # noqa: SLF001
                result = bootstrap._command_router.dispatch("scheduler status")  # noqa: SLF001
                self.assert_true(result.success)
                self.assert_true("Scheduler Status" in result.message)
                # EP-034's "autoflow" CLI namespace coexists alongside it.
                self.assert_true("autoflow" in bootstrap._command_router.module_names)  # noqa: SLF001

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """EP-034 must not import an AI provider, Prompt Engine, Planning, or EP-011's Scheduler."""
        forbidden_fragments = (
            "src.core.ai",
            "src.core.reasoning",
            "src.core.reflection",
            "src.core.prompt",
            "src.core.conversation",
            "src.core.planning",
            "src.core.agent",
            "src.core.collaboration",
            "src.core.workflows",
            "src.core.scheduler.scheduler",  # EP-011's Scheduler class -- must never be imported here
            "openai",
            "anthropic",
            "gemini",
            "ollama",
        )
        source = inspect.getsource(workflow_scheduler_engine_module)
        for fragment in forbidden_fragments:
            self.assert_true(
                fragment not in source,
                f"{workflow_scheduler_engine_module.__name__} must not reference '{fragment}'",
            )

    def _test_no_private_api_access_on_workflow_engine(self) -> None:
        """WorkflowSchedulerEngine reaches WorkflowEngine only through its public run()."""
        source = inspect.getsource(workflow_scheduler_engine_module)
        cleaned = source.replace("self._registry", "").replace("self._workflow_engine", "").replace("self._lock", "")
        self.assert_true(
            "workflow_engine._" not in cleaned,
            "WorkflowSchedulerEngine must not access a private attribute of WorkflowEngine",
        )

    def _test_cli_namespace_is_autoflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = WorkflowSchedulerModule(self._build_service(Path(tmp)))
            self.assert_equal(module.name, "autoflow")
            self.assert_true(module.name != "scheduler")
            self.assert_true(module.name != "schedule")
