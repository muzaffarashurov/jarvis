"""Real engineering tests for EP-033 - Workflow Engine.

Builds real `WorkflowRequestStep`/`WorkflowDefinition`/
`WorkflowStepOutcome`/`WorkflowRunResult`/`WorkflowRunProvider`/
`DefaultWorkflowRunProvider`/`WorkflowDefinitionRegistry`/
`WorkflowEngineManager`/`WorkflowEngine`/`WorkflowEngineService`/
`WorkflowEngineModule` instances -- composed, where needed, with a
real EP-029 `PlanningEngine` and EP-030 `PlanExecutionEngine` -- and
drives them exactly as a caller would, no mocked internals, matching
every other EP's test suite in this project (see
tests/EP032/test_collaboration_engine.py).

Workflow Engine (EP-033) is a new, independent package
(`src/core/workflow_engine/`) that runs a named, ordered sequence of
plain-text requests through EP-030's already-existing
`PlanExecutionEngine.execute_request()`. This suite covers:

1. The domain model: `WorkflowRequestStep`, `WorkflowDefinition`,
   `WorkflowStepOutcomeStatus`, `WorkflowStepOutcome`, `WorkflowRunResult`.
2. The provider abstraction: `WorkflowRunProvider` (abstract
   contract), `DefaultWorkflowRunProvider` (built-in provider) --
   successful step, failing step, an executor that raises.
3. `WorkflowDefinitionRegistry`: register/unregister/get/list, duplicate
   and unknown-id handling.
4. `WorkflowEngineManager`: configuration validation, provider
   registration, enable/disable, active-provider switching,
   stop_on_failure policy, definition catalog delegation.
5. `WorkflowEngine`: the definition -> multi-step-run pipeline --
   empty definition, disabled definition, no provider selected, halts
   on failure per `stop_on_failure`, a real multi-step happy path
   using a real `PlanningEngine` + `PlanExecutionEngine`.
6. `WorkflowEngineService`/`WorkflowEngineModule`: configuration-driven
   construction and every CLI command ("status", "list", "info",
   "use", "run", "help").
7. Bootstrap wiring: real construction from the same
   `PlanExecutionEngine` built for EP-030, graceful degradation on
   invalid 'workflow_engine.*' configuration, and skipping entirely
   when the Plan Execution Engine itself is unavailable.
8. Backward compatibility: EP-029/EP-030/EP-031/EP-032's own behavior
   is provably unaffected, AND EP-007's dormant `src/core/workflows/`/
   `WorkflowService`/`WorkflowModule`/`"workflow"` CLI namespace/
   `workflows.*` config remain completely untouched and unregistered.
9. Architecture compliance: no forbidden imports, no private-API
   access into `PlanExecutionEngine`/`PlanningEngine`, correct
   exception hierarchy, no collision with EP-007's Workflow classes.
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.plan_execution.plan_execution_engine import PlanExecutionEngine
from src.core.plan_execution.plan_execution_manager import PlanExecutionManager
from src.core.plan_execution.plan_execution_result import PlanExecutionResult
from src.core.planning.planning_engine import PlanningEngine
from src.core.planning.planning_manager import PlanningManager
from src.core.config import Config
from src.core.workflow_engine import workflow_engine as workflow_engine_module
from src.core.workflow_engine import workflow_engine_manager as workflow_engine_manager_module
from src.core.workflow_engine import workflow_run_provider as workflow_run_provider_module
from src.core.workflow_engine.workflow_definition import WorkflowDefinition, WorkflowRequestStep
from src.core.workflow_engine.workflow_definition_registry import (
    WorkflowDefinitionNotFoundError,
    WorkflowDefinitionRegistry,
    WorkflowDefinitionRegistryError,
)
from src.core.workflow_engine.workflow_engine import (
    DisabledWorkflowDefinitionError,
    EmptyWorkflowDefinitionError,
    NoWorkflowRunProviderSelectedError,
    WorkflowEngine,
    WorkflowRunError,
)
from src.core.workflow_engine.workflow_engine_manager import (
    WorkflowEngineManager,
    WorkflowRunProviderNotFoundError,
    WorkflowRunProviderRegistryError,
)
from src.core.workflow_engine.workflow_run_provider import (
    DefaultWorkflowRunProvider,
    WorkflowEngineConfigurationError,
    WorkflowEngineError,
    WorkflowRunProvider,
)
from src.core.workflow_engine.workflow_run_result import (
    WorkflowRunResult,
    WorkflowStepOutcome,
    WorkflowStepOutcomeStatus,
)
from src.modules.workflow_engine_module import WorkflowEngineModule
from src.services.workflow_engine_service import WorkflowEngineService
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


_DEFAULT_WORKFLOW_ENGINE_YAML = (
    "workflow_engine:\n"
    "  enabled: true\n"
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: true\n"
)

_NO_STOP_ON_FAILURE_YAML = (
    "workflow_engine:\n"
    "  enabled: true\n"
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: false\n"
)

_DISABLED_WORKFLOW_ENGINE_YAML = (
    "workflow_engine:\n"
    "  enabled: false\n"
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: true\n"
)

_INVALID_PROVIDER_WORKFLOW_ENGINE_YAML = (
    "workflow_engine:\n"
    "  enabled: true\n"
    "  default_provider: \"\"\n"
    "  stop_on_failure: true\n"
)

_INVALID_ENABLED_WORKFLOW_ENGINE_YAML = (
    "workflow_engine:\n"
    "  enabled: \"yes\"\n"
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: true\n"
)

_INVALID_STOP_ON_FAILURE_YAML = (
    "workflow_engine:\n"
    "  enabled: true\n"
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: \"yes\"\n"
)

_UNKNOWN_PROVIDER_WORKFLOW_ENGINE_YAML = (
    "workflow_engine:\n"
    "  enabled: true\n"
    "  default_provider: \"does-not-exist\"\n"
    "  stop_on_failure: true\n"
)

_PLANNING_AND_PLAN_EXECUTION_YAML = (
    "planning:\n"
    "  enabled: true\n"
    "  default_provider: \"planning\"\n"
    "  max_steps: 10\n\n"
    "plan_execution:\n"
    "  enabled: true\n"
    "  default_provider: \"plan_execution\"\n"
    "  stop_on_failure: true\n"
)

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


# Full, offline-safe config.yaml covering every section Bootstrap._build_command_router
# reads, so a real Bootstrap.initialize() can be exercised end to end in a temporary
# project root without any network access or long-lived background threads. Mirrors
# tests/EP032/test_collaboration_engine.py's own copy, plus the new 'workflow_engine:'
# section EP-033 introduces.
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
    "  enabled: {plan_execution_enabled}\n"
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
    "  default_provider: \"{workflow_engine_default_provider}\"\n"
    "  stop_on_failure: true\n"
)


def _write_full_bootstrap_config(
    directory: Path,
    plan_execution_enabled: bool = True,
    workflow_engine_enabled: bool = True,
    workflow_engine_default_provider: str = "workflow_engine",
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            plan_execution_enabled=str(plan_execution_enabled).lower(),
            workflow_engine_enabled=str(workflow_engine_enabled).lower(),
            workflow_engine_default_provider=workflow_engine_default_provider,
        ),
        encoding="utf-8",
    )


def _step(name: str, request: str) -> WorkflowRequestStep:
    return WorkflowRequestStep(name=name, request=request)


class _StubPlanExecutionEngine:
    """A minimal, duck-typed stand-in for EP-030's PlanExecutionEngine.

    `WorkflowEngine` only ever calls `execute_request()` on the object
    it is given -- this test double lets tests control exactly which
    requests succeed or fail, something the real default pipeline
    cannot easily produce (its fallback action, "acknowledge_request",
    is itself a recognized action -- see
    `src/core/plan_execution/plan_execution_provider.py`'s
    `_RECOGNIZED_ACTIONS` -- so virtually any request text COMPLETES
    through the real, unmodified pipeline).
    """

    def __init__(self, failing_requests: frozenset = frozenset()) -> None:
        self._failing_requests = failing_requests
        self.calls: list[str] = []

    def execute_request(self, request: str) -> PlanExecutionResult:
        self.calls.append(request)
        success = request not in self._failing_requests
        return PlanExecutionResult(
            plan=None,  # not inspected by anything under test
            step_results=[],
            completed_count=1 if success else 0,
            failed_count=0 if success else 1,
            skipped_count=0,
            success=success,
        )


class _RaisingPlanExecutionEngine:
    """A duck-typed PlanExecutionEngine stand-in whose execute_request() always raises."""

    def execute_request(self, request: str) -> PlanExecutionResult:
        raise RuntimeError(f"boom while executing '{request}'")


@TestRegistry.register
class WorkflowEngineTest(BaseTest):
    NAME = "EP033"

    def run(self):
        # ---------- Domain model ----------
        self._test_workflow_request_step_construction()
        self._test_workflow_definition_construction()
        self._test_workflow_step_outcome_status_values()
        self._test_workflow_step_outcome_and_run_result_construction()
        self._test_workflow_run_result_summary()

        # ---------- WorkflowRunProvider / DefaultWorkflowRunProvider ----------
        self._test_provider_is_abstract()
        self._test_default_provider_name()
        self._test_default_provider_completes_successful_step()
        self._test_default_provider_reports_failed_step()
        self._test_default_provider_isolates_raising_executor()
        self._test_default_provider_status()

        # ---------- WorkflowDefinitionRegistry ----------
        self._test_registry_register_and_get()
        self._test_registry_duplicate_raises()
        self._test_registry_unknown_raises()
        self._test_registry_unregister()
        self._test_registry_list_sorted()
        self._test_registry_is_registered()

        # ---------- WorkflowEngineManager ----------
        self._test_manager_registers_default_provider()
        self._test_manager_config_defaults()
        self._test_manager_stop_on_failure_config()
        self._test_manager_invalid_enabled_raises()
        self._test_manager_invalid_default_provider_raises()
        self._test_manager_invalid_stop_on_failure_raises()
        self._test_manager_unknown_configured_provider_raises()
        self._test_manager_duplicate_provider_registration_raises()
        self._test_manager_unknown_provider_raises()
        self._test_manager_set_current_switches_provider()
        self._test_manager_set_stop_on_failure()
        self._test_manager_set_stop_on_failure_invalid_raises()
        self._test_manager_disable_clears_current()
        self._test_manager_current_provider_name_none_when_disabled_via_config()
        self._test_manager_register_definition_delegates_to_registry()

        # ---------- WorkflowEngine ----------
        self._test_engine_empty_definition_raises()
        self._test_engine_disabled_definition_raises()
        self._test_engine_no_provider_selected_raises()
        self._test_engine_unknown_definition_id_raises()
        self._test_engine_list_definitions()
        self._test_engine_all_steps_succeed()
        self._test_engine_halts_on_failure_by_default()
        self._test_engine_continues_on_failure_when_configured()
        self._test_engine_real_planning_and_plan_execution_end_to_end()

        # ---------- WorkflowEngineService ----------
        self._test_service_status_and_definitions()
        self._test_service_get_unknown_definition_returns_none()
        self._test_service_use_unknown_provider_fails_gracefully()
        self._test_service_run_success_and_failure()
        self._test_service_disable()

        # ---------- WorkflowEngineModule (CLI) ----------
        self._test_cli_help_lists_commands()
        self._test_cli_status_command()
        self._test_cli_list_command()
        self._test_cli_info_command_usage_and_result()
        self._test_cli_use_command()
        self._test_cli_run_command_usage_and_results()
        self._test_cli_unknown_action()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_registers_workflow_engine_module()
        self._test_bootstrap_degrades_gracefully_on_invalid_workflow_engine_config()
        self._test_bootstrap_disabled_workflow_engine_still_boots()
        self._test_bootstrap_skipped_when_plan_execution_engine_unavailable()
        self._test_bootstrap_uses_same_plan_execution_engine_instance()

        # ---------- Backward compatibility ----------
        self._test_bootstrap_plan_execution_service_unaffected()
        self._test_bootstrap_planning_service_unaffected()
        self._test_bootstrap_tool_service_unaffected()
        self._test_bootstrap_collaboration_service_unaffected()
        self._test_ep007_workflow_package_untouched()

        # ---------- Architectural acceptance criteria ----------
        self._test_no_forbidden_imports()
        self._test_no_planning_import_in_engine()
        self._test_exception_hierarchy()
        self._test_no_private_api_access_on_foreign_objects()
        self._test_cli_namespace_is_flow_not_workflow()

        return self.result

    # ---------- Helpers ----------

    def _build_manager(
        self, tmp_path: Path, yaml_text: str = _DEFAULT_WORKFLOW_ENGINE_YAML
    ) -> WorkflowEngineManager:
        config = _write_config(tmp_path, yaml_text)
        return WorkflowEngineManager(config=config)

    def _build_engine(
        self,
        tmp_path: Path,
        yaml_text: str = _DEFAULT_WORKFLOW_ENGINE_YAML,
        plan_execution_engine=None,
    ) -> WorkflowEngine:
        manager = self._build_manager(tmp_path, yaml_text)
        if plan_execution_engine is None:
            plan_execution_engine = _StubPlanExecutionEngine()
        return WorkflowEngine(manager=manager, plan_execution_engine=plan_execution_engine)

    def _build_service(self, tmp_path: Path) -> WorkflowEngineService:
        engine = self._build_engine(tmp_path)
        return WorkflowEngineService(manager=engine._manager, engine=engine)  # noqa: SLF001

    def _build_real_plan_execution_engine(self, tmp_path: Path) -> PlanExecutionEngine:
        config = _write_config(tmp_path, _PLANNING_AND_PLAN_EXECUTION_YAML)
        planning_manager = PlanningManager(config=config)
        planning_engine = PlanningEngine(manager=planning_manager)
        plan_execution_manager = PlanExecutionManager(config=config)
        return PlanExecutionEngine(manager=plan_execution_manager, planning_engine=planning_engine)

    # ---------- Domain model ----------

    def _test_workflow_request_step_construction(self) -> None:
        step = _step("Recall preferences", "remember my preferences")
        self.assert_equal(step.name, "Recall preferences")
        self.assert_equal(step.request, "remember my preferences")

    def _test_workflow_definition_construction(self) -> None:
        definition = WorkflowDefinition(
            id="morning_briefing",
            name="Morning Briefing",
            description="Recall preferences and summarize context.",
            enabled=True,
            steps=(_step("Recall", "remember my preferences"),),
        )
        self.assert_equal(definition.id, "morning_briefing")
        self.assert_equal(len(definition.steps), 1)
        self.assert_true(definition.enabled)

    def _test_workflow_step_outcome_status_values(self) -> None:
        self.assert_equal(WorkflowStepOutcomeStatus.COMPLETED.value, "COMPLETED")
        self.assert_equal(WorkflowStepOutcomeStatus.FAILED.value, "FAILED")
        self.assert_equal(WorkflowStepOutcomeStatus.SKIPPED.value, "SKIPPED")

    def _test_workflow_step_outcome_and_run_result_construction(self) -> None:
        outcome = WorkflowStepOutcome(
            step_name="Recall", status=WorkflowStepOutcomeStatus.COMPLETED, message="ok"
        )
        self.assert_equal(outcome.step_name, "Recall")
        self.assert_true(outcome.plan_execution_result is None)

        result = WorkflowRunResult(
            definition_id="morning_briefing",
            definition_name="Morning Briefing",
            step_outcomes=[outcome],
            completed_count=1,
            failed_count=0,
            skipped_count=0,
            success=True,
        )
        self.assert_equal(result.completed_count, 1)
        self.assert_true(result.success)

    def _test_workflow_run_result_summary(self) -> None:
        outcome = WorkflowStepOutcome(
            step_name="Recall", status=WorkflowStepOutcomeStatus.COMPLETED, message="acknowledged"
        )
        result = WorkflowRunResult(definition_id="x", definition_name="X", step_outcomes=[outcome])
        self.assert_equal(result.summary(), "Recall - COMPLETED: acknowledged")
        self.assert_equal(WorkflowRunResult(definition_id="x", definition_name="X").summary(), "")

    # ---------- WorkflowRunProvider / DefaultWorkflowRunProvider ----------

    def _test_provider_is_abstract(self) -> None:
        try:
            WorkflowRunProvider()  # type: ignore[abstract]
            self.assert_true(False, "WorkflowRunProvider must be abstract")
        except TypeError:
            self.result.add_pass()

    def _test_default_provider_name(self) -> None:
        provider = DefaultWorkflowRunProvider()
        self.assert_equal(provider.provider_name(), "workflow_engine")

    def _test_default_provider_completes_successful_step(self) -> None:
        provider = DefaultWorkflowRunProvider()
        step = _step("Recall", "remember my preferences")
        engine = _StubPlanExecutionEngine()
        outcome = provider.run_step(step, engine.execute_request)
        self.assert_equal(outcome.status, WorkflowStepOutcomeStatus.COMPLETED)
        self.assert_true(outcome.plan_execution_result is not None)
        self.assert_true(outcome.plan_execution_result.success)
        self.assert_equal(engine.calls, ["remember my preferences"])

    def _test_default_provider_reports_failed_step(self) -> None:
        provider = DefaultWorkflowRunProvider()
        step = _step("Broken", "do the impossible")
        engine = _StubPlanExecutionEngine(failing_requests=frozenset({"do the impossible"}))
        outcome = provider.run_step(step, engine.execute_request)
        self.assert_equal(outcome.status, WorkflowStepOutcomeStatus.FAILED)
        self.assert_true(outcome.plan_execution_result is not None)
        self.assert_false(outcome.plan_execution_result.success)

    def _test_default_provider_isolates_raising_executor(self) -> None:
        provider = DefaultWorkflowRunProvider()
        step = _step("Explodes", "trigger error")
        engine = _RaisingPlanExecutionEngine()
        outcome = provider.run_step(step, engine.execute_request)
        self.assert_equal(outcome.status, WorkflowStepOutcomeStatus.FAILED)
        self.assert_true(outcome.plan_execution_result is None)
        self.assert_true("boom" in outcome.message)

    def _test_default_provider_status(self) -> None:
        provider = DefaultWorkflowRunProvider()
        self.assert_true(provider.is_available())

    # ---------- WorkflowDefinitionRegistry ----------

    def _test_registry_register_and_get(self) -> None:
        registry = WorkflowDefinitionRegistry()
        definition = WorkflowDefinition(
            id="wf1", name="WF1", description="", enabled=True, steps=(_step("A", "a"),)
        )
        registry.register(definition)
        self.assert_equal(registry.get("wf1").id, "wf1")

    def _test_registry_duplicate_raises(self) -> None:
        registry = WorkflowDefinitionRegistry()
        definition = WorkflowDefinition(
            id="wf1", name="WF1", description="", enabled=True, steps=(_step("A", "a"),)
        )
        registry.register(definition)
        try:
            registry.register(definition)
            self.assert_true(False, "Expected WorkflowDefinitionRegistryError")
        except WorkflowDefinitionRegistryError:
            self.result.add_pass()

    def _test_registry_unknown_raises(self) -> None:
        registry = WorkflowDefinitionRegistry()
        try:
            registry.get("does-not-exist")
            self.assert_true(False, "Expected WorkflowDefinitionNotFoundError")
        except WorkflowDefinitionNotFoundError:
            self.result.add_pass()

    def _test_registry_unregister(self) -> None:
        registry = WorkflowDefinitionRegistry()
        definition = WorkflowDefinition(
            id="wf1", name="WF1", description="", enabled=True, steps=(_step("A", "a"),)
        )
        registry.register(definition)
        registry.unregister("wf1")
        self.assert_false(registry.is_registered("wf1"))
        try:
            registry.unregister("wf1")
            self.assert_true(False, "Expected WorkflowDefinitionNotFoundError")
        except WorkflowDefinitionNotFoundError:
            self.result.add_pass()

    def _test_registry_list_sorted(self) -> None:
        registry = WorkflowDefinitionRegistry()
        for definition_id in ("zeta", "alpha", "mu"):
            registry.register(
                WorkflowDefinition(
                    id=definition_id,
                    name=definition_id,
                    description="",
                    enabled=True,
                    steps=(_step("A", "a"),),
                )
            )
        ids = [definition.id for definition in registry.list()]
        self.assert_equal(ids, sorted(ids))

    def _test_registry_is_registered(self) -> None:
        registry = WorkflowDefinitionRegistry()
        self.assert_false(registry.is_registered("wf1"))
        registry.register(
            WorkflowDefinition(id="wf1", name="WF1", description="", enabled=True, steps=(_step("A", "a"),))
        )
        self.assert_true(registry.is_registered("wf1"))

    # ---------- WorkflowEngineManager ----------

    def _test_manager_registers_default_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            names = [provider.provider_name() for provider in manager.list_providers()]
            self.assert_true("workflow_engine" in names)

    def _test_manager_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            self.assert_true(manager.is_enabled())
            self.assert_equal(manager.current_provider_name(), "workflow_engine")

    def _test_manager_stop_on_failure_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp), _NO_STOP_ON_FAILURE_YAML)
            self.assert_false(manager.stop_on_failure())

    def _test_manager_invalid_enabled_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _INVALID_ENABLED_WORKFLOW_ENGINE_YAML)
            try:
                WorkflowEngineManager(config=config)
                self.assert_true(False, "Expected WorkflowEngineConfigurationError")
            except WorkflowEngineConfigurationError:
                self.result.add_pass()

    def _test_manager_invalid_default_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _INVALID_PROVIDER_WORKFLOW_ENGINE_YAML)
            try:
                WorkflowEngineManager(config=config)
                self.assert_true(False, "Expected WorkflowEngineConfigurationError")
            except WorkflowEngineConfigurationError:
                self.result.add_pass()

    def _test_manager_invalid_stop_on_failure_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _INVALID_STOP_ON_FAILURE_YAML)
            try:
                WorkflowEngineManager(config=config)
                self.assert_true(False, "Expected WorkflowEngineConfigurationError")
            except WorkflowEngineConfigurationError:
                self.result.add_pass()

    def _test_manager_unknown_configured_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _UNKNOWN_PROVIDER_WORKFLOW_ENGINE_YAML)
            try:
                WorkflowEngineManager(config=config)
                self.assert_true(False, "Expected WorkflowEngineConfigurationError")
            except WorkflowEngineConfigurationError:
                self.result.add_pass()

    def _test_manager_duplicate_provider_registration_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.register_provider(DefaultWorkflowRunProvider())
                self.assert_true(False, "Expected WorkflowRunProviderRegistryError")
            except WorkflowRunProviderRegistryError:
                self.result.add_pass()

    def _test_manager_unknown_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.get_provider("does-not-exist")
                self.assert_true(False, "Expected WorkflowRunProviderNotFoundError")
            except WorkflowRunProviderNotFoundError:
                self.result.add_pass()

    def _test_manager_set_current_switches_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))

            class _OtherProvider(DefaultWorkflowRunProvider):
                def provider_name(self) -> str:
                    return "other"

            manager.register_provider(_OtherProvider())
            manager.set_current("other")
            self.assert_equal(manager.current_provider_name(), "other")

    def _test_manager_set_stop_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.set_stop_on_failure(False)
            self.assert_false(manager.stop_on_failure())

    def _test_manager_set_stop_on_failure_invalid_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.set_stop_on_failure("yes")  # type: ignore[arg-type]
                self.assert_true(False, "Expected WorkflowEngineConfigurationError")
            except WorkflowEngineConfigurationError:
                self.result.add_pass()

    def _test_manager_disable_clears_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.disable()
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.get_current() is None)
            self.assert_true(manager.current_provider_name() is None)

    def _test_manager_current_provider_name_none_when_disabled_via_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DISABLED_WORKFLOW_ENGINE_YAML)
            manager = WorkflowEngineManager(config=config)
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.current_provider_name() is None)
            self.assert_true(manager.get_current() is None)

    def _test_manager_register_definition_delegates_to_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.register_definition(
                WorkflowDefinition(id="wf1", name="WF1", description="", enabled=True, steps=(_step("A", "a"),))
            )
            self.assert_true(manager.registry.is_registered("wf1"))

    # ---------- WorkflowEngine ----------

    def _test_engine_empty_definition_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            definition = WorkflowDefinition(id="wf1", name="WF1", description="", enabled=True, steps=())
            try:
                engine.run_definition(definition)
                self.assert_true(False, "Expected EmptyWorkflowDefinitionError")
            except EmptyWorkflowDefinitionError:
                self.result.add_pass()

    def _test_engine_disabled_definition_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            definition = WorkflowDefinition(
                id="wf1", name="WF1", description="", enabled=False, steps=(_step("A", "a"),)
            )
            try:
                engine.run_definition(definition)
                self.assert_true(False, "Expected DisabledWorkflowDefinitionError")
            except DisabledWorkflowDefinitionError:
                self.result.add_pass()

    def _test_engine_no_provider_selected_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp), _DISABLED_WORKFLOW_ENGINE_YAML)
            definition = WorkflowDefinition(
                id="wf1", name="WF1", description="", enabled=True, steps=(_step("A", "a"),)
            )
            try:
                engine.run_definition(definition)
                self.assert_true(False, "Expected NoWorkflowRunProviderSelectedError")
            except NoWorkflowRunProviderSelectedError:
                self.result.add_pass()

    def _test_engine_unknown_definition_id_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            try:
                engine.run("does-not-exist")
                self.assert_true(False, "Expected WorkflowDefinitionNotFoundError")
            except WorkflowDefinitionNotFoundError:
                self.result.add_pass()

    def _test_engine_list_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            engine._manager.register_definition(  # noqa: SLF001
                WorkflowDefinition(id="wf1", name="WF1", description="", enabled=True, steps=(_step("A", "a"),))
            )
            ids = [definition.id for definition in engine.list_definitions()]
            self.assert_true("wf1" in ids)

    def _test_engine_all_steps_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stub = _StubPlanExecutionEngine()
            engine = self._build_engine(Path(tmp), plan_execution_engine=stub)
            definition = WorkflowDefinition(
                id="wf1",
                name="WF1",
                description="",
                enabled=True,
                steps=(_step("A", "remember my preferences"), _step("B", "summarize context")),
            )
            result = engine.run_definition(definition)
            self.assert_equal(result.completed_count, 2)
            self.assert_equal(result.failed_count, 0)
            self.assert_equal(result.skipped_count, 0)
            self.assert_true(result.success)
            self.assert_equal(stub.calls, ["remember my preferences", "summarize context"])

    def _test_engine_halts_on_failure_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stub = _StubPlanExecutionEngine(failing_requests=frozenset({"step two"}))
            engine = self._build_engine(Path(tmp), plan_execution_engine=stub)
            definition = WorkflowDefinition(
                id="wf1",
                name="WF1",
                description="",
                enabled=True,
                steps=(_step("A", "step one"), _step("B", "step two"), _step("C", "step three")),
            )
            result = engine.run_definition(definition)
            self.assert_equal(result.completed_count, 1)
            self.assert_equal(result.failed_count, 1)
            self.assert_equal(result.skipped_count, 1)
            self.assert_false(result.success)
            statuses = [outcome.status for outcome in result.step_outcomes]
            self.assert_equal(
                statuses,
                [
                    WorkflowStepOutcomeStatus.COMPLETED,
                    WorkflowStepOutcomeStatus.FAILED,
                    WorkflowStepOutcomeStatus.SKIPPED,
                ],
            )
            # Step three was never dispatched at all.
            self.assert_equal(stub.calls, ["step one", "step two"])

    def _test_engine_continues_on_failure_when_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            stub = _StubPlanExecutionEngine(failing_requests=frozenset({"step two"}))
            engine = self._build_engine(Path(tmp), _NO_STOP_ON_FAILURE_YAML, plan_execution_engine=stub)
            definition = WorkflowDefinition(
                id="wf1",
                name="WF1",
                description="",
                enabled=True,
                steps=(_step("A", "step one"), _step("B", "step two"), _step("C", "step three")),
            )
            result = engine.run_definition(definition)
            self.assert_equal(result.completed_count, 2)
            self.assert_equal(result.failed_count, 1)
            self.assert_equal(result.skipped_count, 0)
            self.assert_false(result.success)
            self.assert_equal(stub.calls, ["step one", "step two", "step three"])

    def _test_engine_real_planning_and_plan_execution_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            real_plan_execution_engine = self._build_real_plan_execution_engine(directory)
            engine = self._build_engine(directory, plan_execution_engine=real_plan_execution_engine)
            definition = WorkflowDefinition(
                id="briefing",
                name="Morning Briefing",
                description="",
                enabled=True,
                steps=(
                    _step("Recall preferences", "remember my preferences"),
                    _step("Summarize context", "summarize the current context"),
                ),
            )
            result = engine.run_definition(definition)
            self.assert_equal(result.completed_count, 2)
            self.assert_equal(result.failed_count, 0)
            self.assert_true(result.success)
            for outcome in result.step_outcomes:
                self.assert_true(outcome.plan_execution_result is not None)

    # ---------- WorkflowEngineService ----------

    def _test_service_status_and_definitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            status = service.status()
            self.assert_true(status.enabled)
            self.assert_equal(status.current_provider, "workflow_engine")
            self.assert_true(status.stop_on_failure)
            self.assert_equal(status.registered_provider_count, 1)
            self.assert_equal(status.registered_definition_count, 0)
            self.assert_equal(service.list_definitions(), [])

    def _test_service_get_unknown_definition_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            self.assert_true(service.get_definition("does-not-exist") is None)

    def _test_service_use_unknown_provider_fails_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.use_provider("does-not-exist")
            self.assert_false(result.success)

    def _test_service_run_success_and_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            service._manager.register_definition(  # noqa: SLF001
                WorkflowDefinition(
                    id="wf1",
                    name="WF1",
                    description="",
                    enabled=True,
                    steps=(_step("A", "remember my preferences"),),
                )
            )
            outcome = service.run("wf1")
            self.assert_true(outcome.success)
            self.assert_true(outcome.result is not None)

            unknown_outcome = service.run("does-not-exist")
            self.assert_false(unknown_outcome.success)
            self.assert_true(unknown_outcome.error != "")

    def _test_service_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.disable()
            self.assert_true(result.success)
            self.assert_false(service.status().enabled)

    # ---------- WorkflowEngineModule (CLI) ----------

    def _test_cli_help_lists_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = WorkflowEngineModule(self._build_service(Path(tmp)))
            result = module.execute("help", [])
            self.assert_true(result.success)
            self.assert_true("flow run" in result.message)

    def _test_cli_status_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = WorkflowEngineModule(self._build_service(Path(tmp)))
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Workflow Engine Status" in result.message)

    def _test_cli_list_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = WorkflowEngineModule(service)
            empty_result = module.execute("list", [])
            self.assert_true(empty_result.success)
            self.assert_true("No workflows registered" in empty_result.message)

            service._manager.register_definition(  # noqa: SLF001
                WorkflowDefinition(
                    id="wf1", name="WF1", description="", enabled=True, steps=(_step("A", "a"),)
                )
            )
            result = module.execute("list", [])
            self.assert_true("wf1" in result.message)

    def _test_cli_info_command_usage_and_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = WorkflowEngineModule(service)
            usage = module.execute("info", [])
            self.assert_false(usage.success)

            unknown = module.execute("info", ["does-not-exist"])
            self.assert_false(unknown.success)

            service._manager.register_definition(  # noqa: SLF001
                WorkflowDefinition(
                    id="wf1",
                    name="WF1",
                    description="A test workflow.",
                    enabled=True,
                    steps=(_step("Recall", "remember my preferences"),),
                )
            )
            result = module.execute("info", ["wf1"])
            self.assert_true(result.success)
            self.assert_true("Recall" in result.message)

    def _test_cli_use_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = WorkflowEngineModule(self._build_service(Path(tmp)))
            usage = module.execute("use", [])
            self.assert_false(usage.success)

            result = module.execute("use", ["workflow_engine"])
            self.assert_true(result.success)

    def _test_cli_run_command_usage_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = WorkflowEngineModule(service)
            usage = module.execute("run", [])
            self.assert_false(usage.success)

            service._manager.register_definition(  # noqa: SLF001
                WorkflowDefinition(
                    id="wf1",
                    name="WF1",
                    description="",
                    enabled=True,
                    steps=(_step("A", "remember my preferences"),),
                )
            )
            result = module.execute("run", ["wf1"])
            self.assert_true(result.success)
            self.assert_true("Workflow Run Result" in result.message)

    def _test_cli_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = WorkflowEngineModule(self._build_service(Path(tmp)))
            result = module.execute("bogus", [])
            self.assert_false(result.success)
            self.assert_true("flow help" in result.message)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_workflow_engine_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.workflow_engine_service is not None)
                self.assert_true("flow" in bootstrap._command_router.module_names)  # noqa: SLF001

    def _test_bootstrap_degrades_gracefully_on_invalid_workflow_engine_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, workflow_engine_default_provider="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()  # must not raise -- Workflow Engine degrades
                self.assert_true(bootstrap.workflow_engine_service is None)
                self.assert_true(bootstrap.plan_execution_service is not None)
                self.assert_true(bootstrap.collaboration_service is not None)

    def _test_bootstrap_disabled_workflow_engine_still_boots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, workflow_engine_enabled=False)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.workflow_engine_service is not None)
                self.assert_false(bootstrap.workflow_engine_service.status().enabled)

    def _test_bootstrap_skipped_when_plan_execution_engine_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            # Malformed 'plan_execution.*' (via a non-boolean 'enabled') makes
            # PlanExecutionManager raise PlanExecutionConfigurationError inside
            # Bootstrap's own try/except, leaving
            # `plan_execution_engine_for_workflow` None -- Workflow Engine must
            # then be skipped entirely (not merely degraded).
            config_text = _FULL_BOOTSTRAP_CONFIG_YAML.format(
                plan_execution_enabled='"not-a-boolean"',
                workflow_engine_enabled="true",
                workflow_engine_default_provider="workflow_engine",
            )
            config_dir = directory / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.yaml").write_text(config_text, encoding="utf-8")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()  # must not raise
                self.assert_true(bootstrap.plan_execution_service is None)
                self.assert_true(bootstrap.workflow_engine_service is None)

    def _test_bootstrap_uses_same_plan_execution_engine_instance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                workflow_engine = bootstrap.workflow_engine_service._engine  # noqa: SLF001
                self.assert_true(
                    workflow_engine._plan_execution_engine  # noqa: SLF001
                    is bootstrap.plan_execution_service._engine  # noqa: SLF001
                )

    # ---------- Backward compatibility ----------

    def _test_bootstrap_plan_execution_service_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                status = bootstrap.plan_execution_service.status()
                self.assert_equal(status.current_provider, "plan_execution")

    def _test_bootstrap_planning_service_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.planning_service is not None)

    def _test_bootstrap_tool_service_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                status = bootstrap.tool_service.status()
                self.assert_equal(status.current_provider, "tool_engine")

    def _test_bootstrap_collaboration_service_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                status = bootstrap.collaboration_service.status()
                self.assert_equal(status.current_provider, "collaboration")

    def _test_ep007_workflow_package_untouched(self) -> None:
        """EP-007's dormant Workflow classes/CLI/config remain exactly as before EP-033."""
        from src.core.workflows.workflow import Workflow, WorkflowStep
        from src.core.workflows.workflow_registry import WorkflowRegistry
        from src.modules.workflow_module import WorkflowModule
        from src.services.workflow_service import WorkflowService

        self.assert_true(Workflow is not None)
        self.assert_true(WorkflowStep is not None)
        self.assert_true(WorkflowRegistry is not None)
        self.assert_true(WorkflowModule is not None)
        self.assert_true(WorkflowService is not None)

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                # EP-007's "workflow" CLI namespace must still be unregistered.
                self.assert_true("workflow" not in bootstrap._command_router.module_names)  # noqa: SLF001
                # EP-033's "flow" CLI namespace must be registered instead.
                self.assert_true("flow" in bootstrap._command_router.module_names)  # noqa: SLF001

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """EP-033 must not import an AI provider, Prompt Engine, or Planning directly."""
        forbidden_fragments = (
            "src.core.ai",
            "src.core.reasoning",
            "src.core.reflection",
            "src.core.prompt",
            "src.core.conversation",
            "src.core.planning",
            "src.core.agent",
            "src.core.collaboration",
            "src.core.workflows",  # EP-007's package -- must never be imported here
            "openai",
            "anthropic",
            "gemini",
            "ollama",
        )
        for module in (
            workflow_engine_module,
            workflow_engine_manager_module,
            workflow_run_provider_module,
        ):
            source = inspect.getsource(module)
            for fragment in forbidden_fragments:
                self.assert_true(
                    fragment not in source, f"{module.__name__} must not reference '{fragment}'"
                )

    def _test_no_planning_import_in_engine(self) -> None:
        """WorkflowEngine must reach EP-030 only, never EP-029's PlanningEngine directly."""
        source = inspect.getsource(workflow_engine_module)
        self.assert_true("PlanningEngine" not in source)
        self.assert_true("from src.core.plan_execution.plan_execution_engine import" in source)

    def _test_exception_hierarchy(self) -> None:
        """WorkflowRunError is catchable through the shared WorkflowEngineError root."""
        self.assert_true(issubclass(WorkflowRunError, WorkflowEngineError))
        self.assert_true(issubclass(WorkflowDefinitionNotFoundError, WorkflowEngineError))
        self.assert_true(issubclass(WorkflowRunProviderNotFoundError, WorkflowEngineError))
        try:
            raise WorkflowRunError("boom")
        except WorkflowEngineError:
            self.result.add_pass()
        else:
            self.assert_true(False, "WorkflowRunError should be catchable as WorkflowEngineError")

    def _test_no_private_api_access_on_foreign_objects(self) -> None:
        """WorkflowEngine reaches PlanExecutionEngine only through its public execute_request()."""
        source = inspect.getsource(workflow_engine_module)
        cleaned = source.replace("self._manager", "").replace("self._plan_execution_engine", "")
        self.assert_true(
            "plan_execution_engine._" not in cleaned,
            "WorkflowEngine must not access a private attribute of PlanExecutionEngine",
        )

    def _test_cli_namespace_is_flow_not_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = WorkflowEngineModule(self._build_service(Path(tmp)))
            self.assert_equal(module.name, "flow")
            self.assert_true(module.name != "workflow")
