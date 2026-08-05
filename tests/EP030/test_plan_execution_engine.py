"""Real engineering tests for EP-030 - Plan Execution Engine.

Builds real `StepResult`/`PlanExecutionResult`/`PlanExecutionProvider`/
`DefaultPlanExecutionProvider`/`PlanExecutionManager`/
`PlanExecutionEngine`/`PlanExecutionService`/`PlanExecutionModule`
instances -- composed, where needed, with a real EP-029 `PlanningEngine`/
`PlanningManager` -- and drives them exactly as a caller would, no
mocked internals, matching every other EP's test suite in this project
(see tests/EP029/test_planning_engine.py).

Plan Execution Engine (EP-030) is a new, independent package
(`src/core/plan_execution/`) that dispatches an EP-029 `Plan`'s steps,
in order -- deterministic, recognized-action dispatch only, never AI
reasoning, an AI provider call, or real subsystem invocation. This
suite covers:

1. The domain model: `StepStatus`, `StepResult`, `PlanExecutionResult`.
2. The provider abstraction: `PlanExecutionProvider` (abstract
   contract), `DefaultPlanExecutionProvider` (built-in,
   recognized-action provider) -- recognized vs. unrecognized actions.
3. `PlanExecutionManager`: configuration validation, registration,
   enable/disable, active-provider switching, status, and the default
   `stop_on_failure` policy.
4. `PlanExecutionEngine`: the Plan -> dispatched-work pipeline --
   ordering, skipping unavailable steps, the stop-on-failure policy,
   and optional integration with a real EP-029 `PlanningEngine` via
   `execute_request()`.
5. `PlanExecutionService`/`PlanExecutionModule`: configuration-driven
   construction, graceful degradation, and every CLI command
   ("status", "providers", "use", "run", "help").
6. Architecture compliance: no forbidden imports, no accidental
   coupling to the unrelated, pre-existing `src/core/execution/`
   package (EP-003's OS-level launcher), no duplicated
   provider/manager/storage logic, no future-EP functionality, no
   private-API access into EP-029, and a real `Bootstrap` run proving
   normal wiring, dependency injection, and graceful degradation on
   invalid configuration.
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.config import Config
from src.core.plan_execution import plan_execution_engine as plan_execution_engine_module
from src.core.plan_execution import plan_execution_manager as plan_execution_manager_module
from src.core.plan_execution import plan_execution_provider as plan_execution_provider_module
from src.core.plan_execution.plan_execution_engine import (
    EmptyPlanError,
    NoPlanExecutionProviderSelectedError,
    PlanExecutionEngine,
    PlanExecutionEngineError,
    PlanningEngineUnavailableError,
)
from src.core.plan_execution.plan_execution_manager import (
    PlanExecutionManager,
    PlanExecutionProviderNotFoundError,
    PlanExecutionProviderRegistryError,
)
from src.core.plan_execution.plan_execution_provider import (
    DefaultPlanExecutionProvider,
    PlanExecutionConfigurationError,
    PlanExecutionError,
    PlanExecutionProvider,
)
from src.core.plan_execution.plan_execution_result import PlanExecutionResult, StepResult, StepStatus
from src.core.planning.planning_engine import PlanningEngine
from src.core.planning.planning_manager import PlanningManager
from src.core.planning.planning_result import Plan, PlanStep
from src.modules.plan_execution_module import PlanExecutionModule
from src.services.plan_execution_service import PlanExecutionService
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


_DEFAULT_PLAN_EXECUTION_YAML = (
    "plan_execution:\n"
    "  enabled: true\n"
    "  default_provider: \"plan_execution\"\n"
    "  stop_on_failure: true\n"
)

_NO_STOP_ON_FAILURE_YAML = (
    "plan_execution:\n"
    "  enabled: true\n"
    "  default_provider: \"plan_execution\"\n"
    "  stop_on_failure: false\n"
)

_DISABLED_PLAN_EXECUTION_YAML = (
    "plan_execution:\n"
    "  enabled: false\n"
    "  default_provider: \"plan_execution\"\n"
    "  stop_on_failure: true\n"
)

_INVALID_PROVIDER_PLAN_EXECUTION_YAML = (
    "plan_execution:\n"
    "  enabled: true\n"
    "  default_provider: \"\"\n"
    "  stop_on_failure: true\n"
)

_INVALID_ENABLED_PLAN_EXECUTION_YAML = (
    "plan_execution:\n"
    "  enabled: \"yes\"\n"
    "  default_provider: \"plan_execution\"\n"
    "  stop_on_failure: true\n"
)

_INVALID_STOP_ON_FAILURE_YAML = (
    "plan_execution:\n"
    "  enabled: true\n"
    "  default_provider: \"plan_execution\"\n"
    "  stop_on_failure: \"yes\"\n"
)

_PLANNING_YAML = (
    "planning:\n"
    "  enabled: true\n"
    "  default_provider: \"planning\"\n"
    "  max_steps: 10\n"
)

# Full, offline-safe config.yaml covering every section Bootstrap._build_command_router
# reads, so a real Bootstrap.initialize() can be exercised end to end in a
# temporary project root without any network access or long-lived background threads.
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
    "  default_provider: \"{plan_execution_default_provider}\"\n"
    "  stop_on_failure: {stop_on_failure}\n"
)

_CONFIG_CACHE: dict[str, Config] = {}


def _write_config(directory: Path, sections: str) -> Config:
    """Return a Config for `sections`, parsing it at most once per distinct text.

    Many test methods request byte-identical configuration text across
    dozens of independent temporary directories; re-writing and
    re-parsing identical YAML from scratch every time is pure overhead
    (see the EP-025/EP-026/EP-027 performance investigation). Caching
    by the exact YAML text keeps every test's observed `Config.get()`
    behavior byte-for-byte identical (the returned `Config` is never
    mutated after `load()`) while eliminating the redundant disk write
    and re-parse. Callers that need a real config.yaml physically
    present in a specific directory (e.g. a real `Bootstrap(...)` run)
    use `_write_full_bootstrap_config()` instead, which is never
    cached.
    """
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


def _write_full_bootstrap_config(
    directory: Path,
    plan_execution_default_provider: str = "plan_execution",
    stop_on_failure: bool = True,
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            plan_execution_default_provider=plan_execution_default_provider,
            stop_on_failure=str(stop_on_failure).lower(),
        ),
        encoding="utf-8",
    )


def _step(order: int, subsystem: str | None, action: str, available: bool = True) -> PlanStep:
    """Build a PlanStep for tests without needing a real PlanningProvider."""
    return PlanStep(order=order, subsystem=subsystem, action=action, description="test step", available=available)


class _RecordingPlanExecutionProvider(PlanExecutionProvider):
    """A minimal, independent PlanExecutionProvider used only to test PlanExecutionManager.

    Always reports success, entirely separate from
    `DefaultPlanExecutionProvider`, so tests can prove
    `PlanExecutionManager` truly delegates to whichever provider is
    active rather than always using the built-in one.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def provider_name(self) -> str:
        return self._name

    def execute_step(self, step: PlanStep) -> StepResult:
        return StepResult(step=step, status=StepStatus.COMPLETED, message="recorded")


@TestRegistry.register
class PlanExecutionEngineTest(BaseTest):
    NAME = "EP030"

    def run(self):
        # ---------- Domain model ----------
        self._test_step_status_values()
        self._test_step_result_and_execution_result_construction()

        # ---------- PlanExecutionProvider / DefaultPlanExecutionProvider ----------
        self._test_provider_is_abstract()
        self._test_default_provider_name()
        self._test_default_provider_recognized_action_completes()
        self._test_default_provider_unrecognized_action_fails()
        self._test_default_provider_status()

        # ---------- PlanExecutionManager ----------
        self._test_manager_registers_default_provider()
        self._test_manager_config_defaults()
        self._test_manager_invalid_enabled_raises()
        self._test_manager_invalid_stop_on_failure_raises()
        self._test_manager_invalid_default_provider_raises()
        self._test_manager_duplicate_registration_raises()
        self._test_manager_unknown_provider_raises()
        self._test_manager_set_current_switches_provider()
        self._test_manager_disable_clears_current()
        self._test_manager_current_provider_name_none_when_disabled_via_config()
        self._test_manager_set_stop_on_failure_validates()

        # ---------- PlanExecutionEngine ----------
        self._test_engine_empty_plan_raises()
        self._test_engine_no_provider_selected_raises()
        self._test_engine_executes_recognized_steps_in_order()
        self._test_engine_skips_unavailable_steps()
        self._test_engine_stop_on_failure_halts_remaining_steps()
        self._test_engine_continue_on_failure_when_disabled()
        self._test_engine_execute_request_without_planning_engine_raises()
        self._test_engine_execute_request_with_real_planning_engine()

        # ---------- PlanExecutionService ----------
        self._test_service_status_and_providers()
        self._test_service_use_unknown_provider_fails_gracefully()
        self._test_service_run_success_and_failure()
        self._test_service_disable()
        self._test_service_set_stop_on_failure()

        # ---------- PlanExecutionModule (CLI) ----------
        self._test_cli_help_lists_commands()
        self._test_cli_status_command()
        self._test_cli_providers_command()
        self._test_cli_use_command()
        self._test_cli_run_command_usage_and_results()
        self._test_cli_unknown_action()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_registers_plan_execution_module()
        self._test_bootstrap_degrades_gracefully_on_invalid_plan_execution_config()
        self._test_bootstrap_plan_execution_independent_of_planning_availability()
        self._test_bootstrap_full_pipeline_via_cli()
        self._test_bootstrap_os_level_execution_engine_unaffected()

        # ---------- Architectural acceptance criteria ----------
        self._test_no_forbidden_imports()
        self._test_no_coupling_to_unrelated_os_execution_package()
        self._test_manager_owns_no_storage_state()
        self._test_exception_hierarchy()
        self._test_no_private_api_access_on_foreign_objects()

        return self.result

    # ---------- Helpers ----------

    def _build_manager(
        self, tmp_path: Path, yaml_text: str = _DEFAULT_PLAN_EXECUTION_YAML
    ) -> PlanExecutionManager:
        config = _write_config(tmp_path, yaml_text)
        return PlanExecutionManager(config=config)

    def _build_engine(
        self,
        tmp_path: Path,
        yaml_text: str = _DEFAULT_PLAN_EXECUTION_YAML,
        with_planning: bool = False,
    ) -> PlanExecutionEngine:
        manager = self._build_manager(tmp_path, yaml_text)
        if not with_planning:
            return PlanExecutionEngine(manager=manager)

        planning_config = _write_config(tmp_path, _PLANNING_YAML)
        planning_manager = PlanningManager(config=planning_config)
        planning_engine = PlanningEngine(manager=planning_manager)
        return PlanExecutionEngine(manager=manager, planning_engine=planning_engine)

    def _build_service(
        self, tmp_path: Path, yaml_text: str = _DEFAULT_PLAN_EXECUTION_YAML
    ) -> PlanExecutionService:
        engine = self._build_engine(tmp_path, yaml_text, with_planning=True)
        return PlanExecutionService(manager=engine._manager, engine=engine)  # noqa: SLF001

    # ---------- Domain model ----------

    def _test_step_status_values(self) -> None:
        self.assert_equal(StepStatus.COMPLETED.value, "COMPLETED")
        self.assert_equal(StepStatus.FAILED.value, "FAILED")
        self.assert_equal(StepStatus.SKIPPED.value, "SKIPPED")

    def _test_step_result_and_execution_result_construction(self) -> None:
        step = _step(1, "knowledge", "query_knowledge_base")
        result = StepResult(step=step, status=StepStatus.COMPLETED, message="ok")
        self.assert_equal(result.status, StepStatus.COMPLETED)

        plan = Plan(request="find something", steps=[step], step_count=1, truncated=False)
        execution_result = PlanExecutionResult(
            plan=plan,
            step_results=[result],
            completed_count=1,
            failed_count=0,
            skipped_count=0,
            success=True,
        )
        summary = execution_result.summary()
        self.assert_true("knowledge" in summary)
        self.assert_true("COMPLETED" in summary)

        empty_result = PlanExecutionResult(plan=plan)
        self.assert_equal(empty_result.step_results, [])
        self.assert_equal(empty_result.summary(), "")

    # ---------- PlanExecutionProvider / DefaultPlanExecutionProvider ----------

    def _test_provider_is_abstract(self) -> None:
        try:
            PlanExecutionProvider()  # type: ignore[abstract]
        except TypeError:
            self.result.add_pass()
        else:
            self.assert_true(False, "PlanExecutionProvider must be abstract")

    def _test_default_provider_name(self) -> None:
        provider = DefaultPlanExecutionProvider()
        self.assert_equal(provider.provider_name(), "plan_execution")

    def _test_default_provider_recognized_action_completes(self) -> None:
        provider = DefaultPlanExecutionProvider()
        step = _step(1, "semantic", "semantic_search")
        result = provider.execute_step(step)
        self.assert_equal(result.status, StepStatus.COMPLETED)
        self.assert_true("dispatched" in result.message)

    def _test_default_provider_unrecognized_action_fails(self) -> None:
        provider = DefaultPlanExecutionProvider()
        step = _step(1, "custom", "do_something_unrecognized")
        result = provider.execute_step(step)
        self.assert_equal(result.status, StepStatus.FAILED)
        self.assert_true("No executor registered" in result.message)

    def _test_default_provider_status(self) -> None:
        provider = DefaultPlanExecutionProvider()
        self.assert_true(provider.is_available())

    # ---------- PlanExecutionManager ----------

    def _test_manager_registers_default_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            providers = manager.list_providers()
            self.assert_equal(len(providers), 1)
            self.assert_equal(providers[0].provider_name(), "plan_execution")
            self.assert_equal(manager.current_provider_name(), "plan_execution")

    def _test_manager_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            self.assert_true(manager.stop_on_failure())
            self.assert_true(manager.is_enabled())

    def _test_manager_invalid_enabled_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_ENABLED_PLAN_EXECUTION_YAML)
            except PlanExecutionConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanExecutionConfigurationError")

    def _test_manager_invalid_stop_on_failure_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_STOP_ON_FAILURE_YAML)
            except PlanExecutionConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanExecutionConfigurationError")

    def _test_manager_invalid_default_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_PROVIDER_PLAN_EXECUTION_YAML)
            except PlanExecutionConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanExecutionConfigurationError")

    def _test_manager_duplicate_registration_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.register_provider(DefaultPlanExecutionProvider())
            except PlanExecutionProviderRegistryError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanExecutionProviderRegistryError")

    def _test_manager_unknown_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.get_provider("does-not-exist")
            except PlanExecutionProviderNotFoundError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanExecutionProviderNotFoundError")

            try:
                manager.set_current("does-not-exist")
            except PlanExecutionProviderNotFoundError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanExecutionProviderNotFoundError")

    def _test_manager_set_current_switches_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            recorder = _RecordingPlanExecutionProvider("recorder")
            manager.register_provider(recorder)
            manager.set_current("recorder")
            self.assert_equal(manager.current_provider_name(), "recorder")
            self.assert_true(manager.get_current() is recorder)

    def _test_manager_disable_clears_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.disable()
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.current_provider_name() is None)
            self.assert_true(manager.get_current() is None)

    def _test_manager_current_provider_name_none_when_disabled_via_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp), _DISABLED_PLAN_EXECUTION_YAML)
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.current_provider_name() is None)

    def _test_manager_set_stop_on_failure_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.set_stop_on_failure(False)
            self.assert_false(manager.stop_on_failure())

            try:
                manager.set_stop_on_failure("nope")  # type: ignore[arg-type]
            except PlanExecutionConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanExecutionConfigurationError")

    # ---------- PlanExecutionEngine ----------

    def _test_engine_empty_plan_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            empty_plan = Plan(request="x", steps=[], step_count=0, truncated=False)
            try:
                engine.execute_plan(empty_plan)
            except EmptyPlanError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected EmptyPlanError")

    def _test_engine_no_provider_selected_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            engine._manager.disable()  # noqa: SLF001
            plan = Plan(request="x", steps=[_step(1, "knowledge", "query_knowledge_base")])
            try:
                engine.execute_plan(plan)
            except NoPlanExecutionProviderSelectedError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected NoPlanExecutionProviderSelectedError")

    def _test_engine_executes_recognized_steps_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            plan = Plan(
                request="x",
                steps=[
                    _step(1, "knowledge", "query_knowledge_base"),
                    _step(2, "semantic", "semantic_search"),
                ],
            )
            result = engine.execute_plan(plan)
            self.assert_equal(result.completed_count, 2)
            self.assert_equal(result.failed_count, 0)
            self.assert_equal(result.skipped_count, 0)
            self.assert_true(result.success)
            self.assert_equal([r.step.order for r in result.step_results], [1, 2])

    def _test_engine_skips_unavailable_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            plan = Plan(
                request="x",
                steps=[
                    _step(1, "knowledge", "query_knowledge_base", available=False),
                    _step(2, "semantic", "semantic_search", available=True),
                ],
            )
            result = engine.execute_plan(plan)
            self.assert_equal(result.step_results[0].status, StepStatus.SKIPPED)
            self.assert_equal(result.step_results[1].status, StepStatus.COMPLETED)
            self.assert_equal(result.skipped_count, 1)
            self.assert_equal(result.completed_count, 1)
            self.assert_true(result.success)  # skipped steps don't cause failure

    def _test_engine_stop_on_failure_halts_remaining_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp), _DEFAULT_PLAN_EXECUTION_YAML)
            plan = Plan(
                request="x",
                steps=[
                    _step(1, "custom", "unrecognized_action"),
                    _step(2, "semantic", "semantic_search"),
                ],
            )
            result = engine.execute_plan(plan)
            self.assert_equal(result.step_results[0].status, StepStatus.FAILED)
            self.assert_equal(result.step_results[1].status, StepStatus.SKIPPED)
            self.assert_true("halted" in result.step_results[1].message)
            self.assert_false(result.success)

    def _test_engine_continue_on_failure_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp), _NO_STOP_ON_FAILURE_YAML)
            plan = Plan(
                request="x",
                steps=[
                    _step(1, "custom", "unrecognized_action"),
                    _step(2, "semantic", "semantic_search"),
                ],
            )
            result = engine.execute_plan(plan)
            self.assert_equal(result.step_results[0].status, StepStatus.FAILED)
            self.assert_equal(result.step_results[1].status, StepStatus.COMPLETED)
            self.assert_false(result.success)

    def _test_engine_execute_request_without_planning_engine_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp), with_planning=False)
            try:
                engine.execute_request("search for something")
            except PlanningEngineUnavailableError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanningEngineUnavailableError")

    def _test_engine_execute_request_with_real_planning_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp), with_planning=True)
            result = engine.execute_request("search the knowledge base")
            self.assert_true(result.completed_count >= 1)
            self.assert_true(result.success)

    # ---------- PlanExecutionService ----------

    def _test_service_status_and_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            status = service.status()
            self.assert_true(status.enabled)
            self.assert_equal(status.current_provider, "plan_execution")
            self.assert_equal(status.registered_provider_count, 1)
            self.assert_true(status.stop_on_failure)

            providers = service.list_providers()
            self.assert_equal(len(providers), 1)
            self.assert_equal(providers[0].name, "plan_execution")
            self.assert_true(providers[0].is_current)

    def _test_service_use_unknown_provider_fails_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            outcome = service.use_provider("does-not-exist")
            self.assert_false(outcome.success)

    def _test_service_run_success_and_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            outcome = service.run("search the knowledge base")
            self.assert_true(outcome.success)
            self.assert_true(outcome.result is not None)
            self.assert_true(outcome.result.completed_count >= 1)

            no_planning_engine = PlanExecutionService(
                manager=service._manager,  # noqa: SLF001
                engine=PlanExecutionEngine(manager=service._manager),  # noqa: SLF001
            )
            failure = no_planning_engine.run("search")
            self.assert_false(failure.success)
            self.assert_true(failure.error != "")

    def _test_service_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.disable()
            self.assert_true(result.success)
            self.assert_false(service.status().enabled)

    def _test_service_set_stop_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.set_stop_on_failure(False)
            self.assert_true(result.success)
            self.assert_false(service.status().stop_on_failure)

            bad = service.set_stop_on_failure("nope")  # type: ignore[arg-type]
            self.assert_false(bad.success)

    # ---------- PlanExecutionModule (CLI) ----------

    def _test_cli_help_lists_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanExecutionModule(service)
            self.assert_equal(module.name, "execution")
            result = module.execute("help", [])
            self.assert_true(result.success)
            for command in ("status", "providers", "use", "run"):
                self.assert_true(command in result.message)

    def _test_cli_status_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanExecutionModule(service)
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Enabled" in result.message)

    def _test_cli_providers_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanExecutionModule(service)
            result = module.execute("providers", [])
            self.assert_true(result.success)
            self.assert_true("plan_execution" in result.message)

    def _test_cli_use_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanExecutionModule(service)
            self.assert_false(module.execute("use", []).success)
            self.assert_false(module.execute("use", ["nope"]).success)
            self.assert_true(module.execute("use", ["plan_execution"]).success)

    def _test_cli_run_command_usage_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanExecutionModule(service)
            self.assert_false(module.execute("run", []).success)
            result = module.execute("run", ["search", "the", "knowledge", "base"])
            self.assert_true(result.success)
            self.assert_true("Completed" in result.message)

    def _test_cli_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanExecutionModule(service)
            result = module.execute("bogus", [])
            self.assert_false(result.success)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_plan_execution_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                service = bootstrap.plan_execution_service
                self.assert_true(service is not None)
                status = service.status()
                self.assert_true(status.enabled)
                self.assert_equal(status.current_provider, "plan_execution")

                result = bootstrap._command_router.dispatch("execution status")  # noqa: SLF001
                self.assert_true(result.success)

    def _test_bootstrap_degrades_gracefully_on_invalid_plan_execution_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, plan_execution_default_provider="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()  # must not raise -- Plan Execution Engine degrades
                self.assert_true(bootstrap.plan_execution_service is None)
                # The rest of the application is unaffected.
                self.assert_true(bootstrap.knowledge_service is not None)
                self.assert_true(bootstrap.planning_service is not None)

    def _test_bootstrap_plan_execution_independent_of_planning_availability(self) -> None:
        """Plan Execution Engine must not require Planning Engine to be available."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config_dir = directory / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            full_config = _FULL_BOOTSTRAP_CONFIG_YAML.format(
                plan_execution_default_provider="plan_execution", stop_on_failure="true"
            ).replace('default_provider: "planning"', 'default_provider: ""')
            (config_dir / "config.yaml").write_text(full_config, encoding="utf-8")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.planning_service is None)
                self.assert_true(bootstrap.plan_execution_service is not None)
                self.assert_true(bootstrap.plan_execution_service.status().enabled)
                # `execution run` needs a PlanningEngine -- verify it fails gracefully.
                result = bootstrap._command_router.dispatch("execution run search")  # noqa: SLF001
                self.assert_false(result.success)

    def _test_bootstrap_full_pipeline_via_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    "execution run search the knowledge base and compress it"
                )
                self.assert_true(result.success)
                self.assert_true("Completed" in result.message)
                self.assert_true("FAILED" not in result.message)

    def _test_bootstrap_os_level_execution_engine_unaffected(self) -> None:
        """The pre-existing OS-level ExecutionEngine (EP-003) must still work unmodified."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                result = bootstrap._command_router.dispatch("process list")  # noqa: SLF001
                self.assert_true(result.success)

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """EP-030 must not import an AI provider, Prompt Engine, or Tool Executor."""
        forbidden_fragments = (
            "src.core.rag",
            "src.core.ai",
            "src.core.reasoning",
            "src.core.reflection",
            "src.core.prompt",
            "src.core.conversation",
            "browser_automation",
            "tool_executor",
            "openai",
            "anthropic",
            "gemini",
            "ollama",
        )
        for module in (
            plan_execution_engine_module,
            plan_execution_manager_module,
            plan_execution_provider_module,
        ):
            source = inspect.getsource(module)
            for fragment in forbidden_fragments:
                self.assert_true(
                    fragment not in source, f"{module.__name__} must not reference '{fragment}'"
                )

    def _test_no_coupling_to_unrelated_os_execution_package(self) -> None:
        """EP-030 must never import the pre-existing, unrelated src/core/execution/ package."""
        for module in (
            plan_execution_engine_module,
            plan_execution_manager_module,
            plan_execution_provider_module,
        ):
            source = inspect.getsource(module)
            self.assert_true(
                "src.core.execution" not in source,
                f"{module.__name__} must not import the unrelated OS-level execution package",
            )

    def _test_manager_owns_no_storage_state(self) -> None:
        """PlanExecutionManager owns provider registration only, never plan/step storage."""
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            instance_attrs = vars(manager)
            forbidden_attr_names = ("_records", "_collection", "_store", "_documents", "_index", "_plans")
            for attr_name in instance_attrs:
                for forbidden in forbidden_attr_names:
                    self.assert_true(
                        forbidden not in attr_name.lower(),
                        f"PlanExecutionManager should not own storage state ('{attr_name}')",
                    )

    def _test_exception_hierarchy(self) -> None:
        """PlanExecutionEngineError is catchable through the shared PlanExecutionError root."""
        self.assert_true(issubclass(PlanExecutionEngineError, PlanExecutionError))
        try:
            raise PlanExecutionEngineError("boom")
        except PlanExecutionError:
            self.result.add_pass()
        else:
            self.assert_true(
                False, "PlanExecutionEngineError should be catchable as PlanExecutionError"
            )

    def _test_no_private_api_access_on_foreign_objects(self) -> None:
        """PlanExecutionEngine reaches Planning Engine only through public methods/fields.

        Scans `plan_execution_engine.py`'s source for any attribute
        access beginning with an underscore on the injected
        collaborator (`planning_engine`) -- only `self._*` (this
        class's own attributes) is permitted.
        """
        source = inspect.getsource(plan_execution_engine_module)
        self.assert_true(
            "planning_engine._" not in source,
            "PlanExecutionEngine must not access a private attribute of PlanningEngine",
        )
