"""Real engineering tests for EP-035 - Automation Engine.

Builds real `AutomationRule`/`AutomationRuleRegistry`/`AutomationEngine`/
`AutomationService`/`AutomationModule` instances -- composed, where
needed, with a real EP-033 `WorkflowEngine` (itself backed by a
duck-typed `PlanExecutionEngine` stand-in, the same technique EP-033's
and EP-034's own test suites used) and a real EP-034
`WorkflowSchedulerEngine` -- and drives them exactly as a caller
would, no mocked internals, matching every other EP's test suite in
this project (see tests/EP034/test_workflow_scheduler.py).

Automation Engine (EP-035) is a new, independent package
(`src/core/automation_engine/`) that chains one EP-033 workflow's
completion into a second workflow run, based on outcome. This suite
covers:

1. The domain model: `AutomationRule`, `AutomationTriggerCondition`.
2. `AutomationRuleRegistry`: register/unregister/get/list, duplicate
   and unknown-id handling.
3. `AutomationEngine`: register/remove/enable/disable/list/get rules,
   `notify_run()` for ON_SUCCESS/ON_FAILURE/ON_ANY, wrong trigger
   workflow id, disabled rules, multiple matching rules, a failing
   action workflow, hook/dispatch failure isolation, and the
   single-hop / no-recursive-chaining guarantee.
4. `AutomationService`: configuration-driven `_ensure_enabled`
   short-circuiting, and every CLI-facing method.
5. `AutomationModule`: every CLI command ("list", "status", "info",
   "enable", "stop", "help").
6. Bootstrap wiring: real construction from the same `WorkflowEngine`
   built for EP-033, the hook actually reaching `AutomationEngine`
   through both `WorkflowEngineService.run()` (on-demand) and
   `WorkflowSchedulerEngine.run_now()` (scheduled/manual), graceful
   degradation on invalid configuration, and skipping entirely when
   the Workflow Engine itself is unavailable.
7. Disabled automation: 'automation.enabled: false' both rejects
   `AutomationService` mutations AND is never wired as a hook, so no
   rule can fire regardless of which path is used.
8. Backward compatibility: EP-033's `WorkflowEngineService.run()` and
   EP-034's `WorkflowSchedulerEngine.run_now()` behave identically to
   their pre-EP-035 selves when no hook is wired (default None), and
   EP-033/034's own test suites are provably unaffected.
9. Architecture compliance: no forbidden imports, no private-API
   access into `WorkflowEngine`, and neither
   `WorkflowEngineService`/`WorkflowSchedulerEngine` import any
   EP-035 type (the hook stays a bare `Callable`).
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.automation_engine.automation_engine import AutomationEngine, AutomationError
from src.core.automation_engine.automation_rule import AutomationRule, AutomationTriggerCondition
from src.core.automation_engine.automation_rule_registry import AutomationRuleRegistry
from src.core.automation_engine import automation_engine as automation_engine_module
from src.core.config import Config
from src.core.plan_execution.plan_execution_result import PlanExecutionResult
from src.core.scheduler.job import Schedule, ScheduleType
from src.core.workflow_engine.workflow_definition import WorkflowDefinition, WorkflowRequestStep
from src.core.workflow_engine.workflow_engine import WorkflowEngine
from src.core.workflow_engine.workflow_engine_manager import WorkflowEngineManager
from src.core.workflow_scheduler.scheduled_workflow import ScheduledWorkflow
from src.core.workflow_scheduler.scheduled_workflow_registry import ScheduledWorkflowRegistry
from src.core.workflow_scheduler.workflow_scheduler_engine import WorkflowSchedulerEngine
from src.modules.automation_module import AutomationModule
from src.services.automation_service import AutomationService
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

_DEFAULT_AUTOMATION_YAML = "automation:\n  enabled: true\n"

_DISABLED_AUTOMATION_YAML = "automation:\n  enabled: false\n"


class _StubPlanExecutionEngine:
    """A minimal, duck-typed stand-in for EP-030's PlanExecutionEngine.

    Identical technique to tests/EP033/test_workflow_engine.py's and
    tests/EP034/test_workflow_scheduler.py's own
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


def _automation_rule(
    rule_id: str = "ar1",
    trigger_workflow_id: str = "wf1",
    condition: AutomationTriggerCondition = AutomationTriggerCondition.ON_SUCCESS,
    action_workflow_id: str = "wf2",
    enabled: bool = True,
) -> AutomationRule:
    return AutomationRule(
        id=rule_id,
        name=rule_id,
        description="A test automation rule.",
        trigger_workflow_id=trigger_workflow_id,
        trigger_condition=condition,
        action_workflow_id=action_workflow_id,
        enabled=enabled,
    )


def _build_automation_service(tmp_path: Path, enabled: bool = True) -> tuple[AutomationService, AutomationEngine, WorkflowEngineManager]:
    """Build a real AutomationService backed by a real WorkflowEngine (EP-033)."""
    engine, manager = _build_workflow_engine(tmp_path)
    registry = AutomationRuleRegistry()
    automation_engine = AutomationEngine(registry=registry, workflow_engine=engine)
    config = _write_config(tmp_path, _DEFAULT_AUTOMATION_YAML if enabled else _DISABLED_AUTOMATION_YAML)
    service = AutomationService(config=config, engine=automation_engine)
    return service, automation_engine, manager


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
    "  default_provider: \"workflow_engine\"\n"
    "  stop_on_failure: true\n\n"
    "workflow_scheduler:\n"
    "  enabled: {workflow_scheduler_enabled}\n"
    "  auto_start: false\n"
    "  tick_interval: 5\n\n"
    "automation:\n"
    "  enabled: {automation_enabled}\n"
)


def _write_full_bootstrap_config(
    directory: Path,
    workflow_scheduler_enabled: bool = True,
    automation_enabled: bool = True,
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            workflow_scheduler_enabled=str(workflow_scheduler_enabled).lower(),
            automation_enabled=str(automation_enabled).lower(),
        ),
        encoding="utf-8",
    )


@TestRegistry.register
class AutomationEngineTest(BaseTest):
    NAME = "EP035"

    def run(self):
        # ---------- Domain model ----------
        self._test_automation_rule_construction()
        self._test_trigger_condition_values()

        # ---------- AutomationRuleRegistry ----------
        self._test_registry_register_and_get()
        self._test_registry_duplicate_raises()
        self._test_registry_unregister_unknown_raises()
        self._test_registry_list()
        self._test_registry_list_by_trigger()

        # ---------- AutomationEngine: lifecycle ----------
        self._test_engine_register_and_remove()
        self._test_engine_register_duplicate_raises()
        self._test_engine_remove_unknown_raises()
        self._test_engine_enable_disable()
        self._test_engine_enable_unknown_raises()

        # ---------- AutomationEngine: notify_run matching ----------
        self._test_notify_run_on_success_matches()
        self._test_notify_run_on_failure_matches()
        self._test_notify_run_on_any_matches_both()
        self._test_notify_run_wrong_workflow_id_no_match()
        self._test_notify_run_disabled_rule_no_match()
        self._test_notify_run_multiple_matching_rules()
        self._test_notify_run_failed_action_workflow_recorded()
        self._test_notify_run_never_raises_on_internal_error()
        self._test_notify_run_no_recursive_chaining()

        # ---------- AutomationService ----------
        self._test_service_register_enable_disable()
        self._test_service_disabled_rejects_operations()
        self._test_service_status()

        # ---------- AutomationModule (CLI) ----------
        self._test_cli_help_lists_commands()
        self._test_cli_status_command()
        self._test_cli_list_command()
        self._test_cli_info_command_usage_and_result()
        self._test_cli_enable_stop_commands()
        self._test_cli_unknown_action()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_registers_automation_module()
        self._test_bootstrap_skipped_when_workflow_engine_unavailable()
        self._test_bootstrap_on_demand_run_triggers_automation()
        self._test_bootstrap_scheduled_run_triggers_automation()
        self._test_bootstrap_disabled_automation_never_fires()

        # ---------- Backward compatibility ----------
        self._test_workflow_engine_service_unaffected_without_hook()
        self._test_workflow_scheduler_engine_unaffected_without_hook()
        self._test_bootstrap_workflow_engine_service_unaffected()

        # ---------- Architectural acceptance criteria ----------
        self._test_no_forbidden_imports()
        self._test_no_private_api_access_on_workflow_engine()
        self._test_cli_namespace_is_automate()
        self._test_hook_types_are_not_ep035_types()

        return self.result

    # ---------- Domain model ----------

    def _test_automation_rule_construction(self) -> None:
        rule = _automation_rule()
        self.assert_equal(rule.id, "ar1")
        self.assert_equal(rule.trigger_workflow_id, "wf1")
        self.assert_equal(rule.action_workflow_id, "wf2")
        self.assert_true(rule.enabled)
        self.assert_true(rule.last_triggered is None)
        self.assert_true(rule.last_action_success is None)

    def _test_trigger_condition_values(self) -> None:
        self.assert_equal(AutomationTriggerCondition.ON_SUCCESS.value, "ON_SUCCESS")
        self.assert_equal(AutomationTriggerCondition.ON_FAILURE.value, "ON_FAILURE")
        self.assert_equal(AutomationTriggerCondition.ON_ANY.value, "ON_ANY")

    # ---------- AutomationRuleRegistry ----------

    def _test_registry_register_and_get(self) -> None:
        registry = AutomationRuleRegistry()
        rule = _automation_rule("ar-reg")
        registry.register(rule)
        self.assert_equal(registry.get("ar-reg"), rule)
        self.assert_true(registry.get("missing") is None)

    def _test_registry_duplicate_raises(self) -> None:
        registry = AutomationRuleRegistry()
        registry.register(_automation_rule("ar-dup"))
        try:
            registry.register(_automation_rule("ar-dup"))
            self.assert_true(False, "Expected ValueError on duplicate registration")
        except ValueError:
            self.result.add_pass()

    def _test_registry_unregister_unknown_raises(self) -> None:
        registry = AutomationRuleRegistry()
        try:
            registry.unregister("nope")
            self.assert_true(False, "Expected KeyError on unknown unregister")
        except KeyError:
            self.result.add_pass()

    def _test_registry_list(self) -> None:
        registry = AutomationRuleRegistry()
        registry.register(_automation_rule("ar-a"))
        registry.register(_automation_rule("ar-b"))
        ids = {rule.id for rule in registry.list()}
        self.assert_equal(ids, {"ar-a", "ar-b"})

    def _test_registry_list_by_trigger(self) -> None:
        registry = AutomationRuleRegistry()
        registry.register(_automation_rule("ar-t1", trigger_workflow_id="wfX"))
        registry.register(_automation_rule("ar-t2", trigger_workflow_id="wfY"))
        matches = registry.list_by_trigger("wfX")
        self.assert_equal(len(matches), 1)
        self.assert_equal(matches[0].id, "ar-t1")

    # ---------- AutomationEngine: lifecycle ----------

    def _test_engine_register_and_remove(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_workflow_engine(Path(tmp))
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            automation_engine.register_rule(_automation_rule("ar-lc"))
            self.assert_true(automation_engine.get_rule("ar-lc") is not None)
            automation_engine.remove_rule("ar-lc")
            self.assert_true(automation_engine.get_rule("ar-lc") is None)

    def _test_engine_register_duplicate_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_workflow_engine(Path(tmp))
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            automation_engine.register_rule(_automation_rule("ar-dup2"))
            try:
                automation_engine.register_rule(_automation_rule("ar-dup2"))
                self.assert_true(False, "Expected AutomationError on duplicate")
            except AutomationError:
                self.result.add_pass()

    def _test_engine_remove_unknown_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_workflow_engine(Path(tmp))
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            try:
                automation_engine.remove_rule("nope")
                self.assert_true(False, "Expected AutomationError on unknown remove")
            except AutomationError:
                self.result.add_pass()

    def _test_engine_enable_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_workflow_engine(Path(tmp))
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            automation_engine.register_rule(_automation_rule("ar-ed", enabled=True))
            automation_engine.disable_rule("ar-ed")
            self.assert_false(automation_engine.get_rule("ar-ed").enabled)
            automation_engine.enable_rule("ar-ed")
            self.assert_true(automation_engine.get_rule("ar-ed").enabled)

    def _test_engine_enable_unknown_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _ = _build_workflow_engine(Path(tmp))
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            try:
                automation_engine.enable_rule("nope")
                self.assert_true(False, "Expected AutomationError on unknown enable")
            except AutomationError:
                self.result.add_pass()

    # ---------- AutomationEngine: notify_run matching ----------

    def _test_notify_run_on_success_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "trigger-wf")
            _register_workflow(manager, "action-wf")
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            automation_engine.register_rule(
                _automation_rule(
                    "ar-success",
                    trigger_workflow_id="trigger-wf",
                    condition=AutomationTriggerCondition.ON_SUCCESS,
                    action_workflow_id="action-wf",
                )
            )
            result = engine.run("trigger-wf")
            self.assert_true(result.success)
            triggered = automation_engine.notify_run("trigger-wf", result)
            self.assert_equal(len(triggered), 1)
            rule = automation_engine.get_rule("ar-success")
            self.assert_true(rule.last_action_success)
            self.assert_true(rule.last_triggered is not None)

    def _test_notify_run_on_failure_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager = _build_workflow_engine(Path(tmp), failing_requests=frozenset({"do it"}))
            _register_workflow(manager, "trigger-wf")
            _register_workflow(manager, "action-wf")
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            automation_engine.register_rule(
                _automation_rule(
                    "ar-failure",
                    trigger_workflow_id="trigger-wf",
                    condition=AutomationTriggerCondition.ON_FAILURE,
                    action_workflow_id="action-wf",
                )
            )
            result = engine.run("trigger-wf")
            self.assert_false(result.success)
            triggered = automation_engine.notify_run("trigger-wf", result)
            self.assert_equal(len(triggered), 1)

    def _test_notify_run_on_any_matches_both(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Success case
            engine, manager = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "trigger-wf")
            _register_workflow(manager, "action-wf")
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            automation_engine.register_rule(
                _automation_rule(
                    "ar-any",
                    trigger_workflow_id="trigger-wf",
                    condition=AutomationTriggerCondition.ON_ANY,
                    action_workflow_id="action-wf",
                )
            )
            success_result = engine.run("trigger-wf")
            triggered = automation_engine.notify_run("trigger-wf", success_result)
            self.assert_equal(len(triggered), 1)

        with tempfile.TemporaryDirectory() as tmp2:
            # Failure case, fresh engine/registry
            engine2, manager2 = _build_workflow_engine(Path(tmp2), failing_requests=frozenset({"do it"}))
            _register_workflow(manager2, "trigger-wf")
            _register_workflow(manager2, "action-wf")
            automation_engine2 = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine2)
            automation_engine2.register_rule(
                _automation_rule(
                    "ar-any2",
                    trigger_workflow_id="trigger-wf",
                    condition=AutomationTriggerCondition.ON_ANY,
                    action_workflow_id="action-wf",
                )
            )
            failure_result = engine2.run("trigger-wf")
            triggered2 = automation_engine2.notify_run("trigger-wf", failure_result)
            self.assert_equal(len(triggered2), 1)

    def _test_notify_run_wrong_workflow_id_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "trigger-wf")
            _register_workflow(manager, "other-wf")
            _register_workflow(manager, "action-wf")
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            automation_engine.register_rule(
                _automation_rule(
                    "ar-wrong",
                    trigger_workflow_id="trigger-wf",
                    condition=AutomationTriggerCondition.ON_ANY,
                    action_workflow_id="action-wf",
                )
            )
            result = engine.run("other-wf")
            triggered = automation_engine.notify_run("other-wf", result)
            self.assert_equal(len(triggered), 0)

    def _test_notify_run_disabled_rule_no_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "trigger-wf")
            _register_workflow(manager, "action-wf")
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            automation_engine.register_rule(
                _automation_rule(
                    "ar-disabled",
                    trigger_workflow_id="trigger-wf",
                    condition=AutomationTriggerCondition.ON_ANY,
                    action_workflow_id="action-wf",
                    enabled=False,
                )
            )
            result = engine.run("trigger-wf")
            triggered = automation_engine.notify_run("trigger-wf", result)
            self.assert_equal(len(triggered), 0)

    def _test_notify_run_multiple_matching_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "trigger-wf")
            _register_workflow(manager, "action-wf-1")
            _register_workflow(manager, "action-wf-2")
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            automation_engine.register_rule(
                _automation_rule(
                    "ar-multi-1",
                    trigger_workflow_id="trigger-wf",
                    condition=AutomationTriggerCondition.ON_ANY,
                    action_workflow_id="action-wf-1",
                )
            )
            automation_engine.register_rule(
                _automation_rule(
                    "ar-multi-2",
                    trigger_workflow_id="trigger-wf",
                    condition=AutomationTriggerCondition.ON_ANY,
                    action_workflow_id="action-wf-2",
                )
            )
            result = engine.run("trigger-wf")
            triggered = automation_engine.notify_run("trigger-wf", result)
            self.assert_equal(len(triggered), 2)

    def _test_notify_run_failed_action_workflow_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager = _build_workflow_engine(Path(tmp), failing_requests=frozenset({"boom"}))
            _register_workflow(manager, "trigger-wf")
            manager.register_definition(
                WorkflowDefinition(
                    id="action-wf",
                    name="action-wf",
                    description="",
                    enabled=True,
                    steps=(WorkflowRequestStep(name="Step", request="boom"),),
                )
            )
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            automation_engine.register_rule(
                _automation_rule(
                    "ar-action-fail",
                    trigger_workflow_id="trigger-wf",
                    condition=AutomationTriggerCondition.ON_ANY,
                    action_workflow_id="action-wf",
                )
            )
            trigger_result = engine.run("trigger-wf")
            self.assert_true(trigger_result.success)  # trigger itself succeeded

            # notify_run must not raise even though the action workflow fails.
            triggered = automation_engine.notify_run("trigger-wf", trigger_result)
            self.assert_equal(len(triggered), 1)
            rule = automation_engine.get_rule("ar-action-fail")
            self.assert_false(rule.last_action_success)

    def _test_notify_run_never_raises_on_internal_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "trigger-wf")

            class _ExplodingRegistry(AutomationRuleRegistry):
                def list_by_trigger(self, trigger_workflow_id: str):
                    raise RuntimeError("boom")

            automation_engine = AutomationEngine(registry=_ExplodingRegistry(), workflow_engine=engine)
            result = engine.run("trigger-wf")
            try:
                triggered = automation_engine.notify_run("trigger-wf", result)
                self.assert_equal(triggered, [])
            except Exception:
                self.assert_true(False, "notify_run must never raise")

    def _test_notify_run_no_recursive_chaining(self) -> None:
        """Rule A(trigger=wf1 -> action=wf2), Rule B(trigger=wf2 -> action=wf3).

        Calling notify_run for wf1 must trigger Rule A (running wf2)
        but must NOT trigger Rule B, since dispatch bypasses the hook
        and never re-enters notify_run.
        """
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "wf1")
            _register_workflow(manager, "wf2")
            _register_workflow(manager, "wf3")
            automation_engine = AutomationEngine(registry=AutomationRuleRegistry(), workflow_engine=engine)
            automation_engine.register_rule(
                _automation_rule(
                    "rule-a",
                    trigger_workflow_id="wf1",
                    condition=AutomationTriggerCondition.ON_ANY,
                    action_workflow_id="wf2",
                )
            )
            automation_engine.register_rule(
                _automation_rule(
                    "rule-b",
                    trigger_workflow_id="wf2",
                    condition=AutomationTriggerCondition.ON_ANY,
                    action_workflow_id="wf3",
                )
            )
            result = engine.run("wf1")
            triggered = automation_engine.notify_run("wf1", result)
            self.assert_equal(len(triggered), 1)
            self.assert_equal(triggered[0].id, "rule-a")
            # Rule B must never have fired: wf2's completion (run directly
            # by AutomationEngine._trigger) never re-enters notify_run.
            rule_b = automation_engine.get_rule("rule-b")
            self.assert_true(rule_b.last_triggered is None)
            self.assert_true(rule_b.last_action_success is None)

    # ---------- AutomationService ----------

    def _test_service_register_enable_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _, _ = _build_automation_service(Path(tmp))
            result = service.register(_automation_rule("ar-svc"))
            self.assert_true(result.success)
            result = service.disable("ar-svc")
            self.assert_true(result.success)
            self.assert_false(service.get_rule("ar-svc").enabled)
            result = service.enable("ar-svc")
            self.assert_true(result.success)
            self.assert_true(service.get_rule("ar-svc").enabled)
            result = service.unregister("ar-svc")
            self.assert_true(result.success)
            self.assert_true(service.get_rule("ar-svc") is None)

    def _test_service_disabled_rejects_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _, _ = _build_automation_service(Path(tmp), enabled=False)
            result = service.register(_automation_rule("ar-off"))
            self.assert_false(result.success)
            self.assert_equal(result.message, "Automation Engine stopped.")

    def _test_service_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _, _ = _build_automation_service(Path(tmp))
            service.register(_automation_rule("ar-s1"))
            service.register(_automation_rule("ar-s2"))
            service.disable("ar-s2")
            status = service.status()
            self.assert_true(status.enabled)
            self.assert_equal(status.rules_registered, 2)
            self.assert_equal(status.rules_enabled, 1)

    # ---------- AutomationModule (CLI) ----------

    def _test_cli_help_lists_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _, _ = _build_automation_service(Path(tmp))
            module = AutomationModule(service)
            result = module.execute("help", [])
            self.assert_true(result.success)
            for command in ("list", "status", "info", "enable", "stop", "help"):
                self.assert_true(f"automate {command}" in result.message)

    def _test_cli_status_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _, _ = _build_automation_service(Path(tmp))
            module = AutomationModule(service)
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Automation Engine Status" in result.message)

    def _test_cli_list_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _, _ = _build_automation_service(Path(tmp))
            module = AutomationModule(service)
            empty = module.execute("list", [])
            self.assert_true("(none registered)" in empty.message)
            service.register(_automation_rule("ar-list"))
            result = module.execute("list", [])
            self.assert_true("ar-list" in result.message)

    def _test_cli_info_command_usage_and_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _, _ = _build_automation_service(Path(tmp))
            module = AutomationModule(service)
            usage = module.execute("info", [])
            self.assert_false(usage.success)
            self.assert_true("Usage" in usage.message)

            not_found = module.execute("info", ["nope"])
            self.assert_false(not_found.success)

            service.register(_automation_rule("ar-info"))
            result = module.execute("info", ["ar-info"])
            self.assert_true(result.success)
            self.assert_true("ar-info" in result.message or "Name" in result.message)

    def _test_cli_enable_stop_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _, _ = _build_automation_service(Path(tmp))
            module = AutomationModule(service)
            service.register(_automation_rule("ar-toggle"))
            stop_result = module.execute("stop", ["ar-toggle"])
            self.assert_true(stop_result.success)
            self.assert_false(service.get_rule("ar-toggle").enabled)
            enable_result = module.execute("enable", ["ar-toggle"])
            self.assert_true(enable_result.success)
            self.assert_true(service.get_rule("ar-toggle").enabled)

    def _test_cli_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _, _ = _build_automation_service(Path(tmp))
            module = AutomationModule(service)
            result = module.execute("bogus", [])
            self.assert_false(result.success)
            self.assert_true("automate help" in result.message)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_automation_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.automation_service is not None)
                self.assert_true("automate" in bootstrap._command_router.module_names)  # noqa: SLF001

    def _test_bootstrap_skipped_when_workflow_engine_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            # Force an invalid 'workflow_engine.default_provider' so EP-033 itself
            # fails to construct, leaving `workflow_engine_for_scheduler` None.
            config_text = _FULL_BOOTSTRAP_CONFIG_YAML.format(
                workflow_scheduler_enabled="true", automation_enabled="true"
            ).replace('default_provider: "workflow_engine"\n  stop_on_failure', 'default_provider: ""\n  stop_on_failure')
            config_dir = directory / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            (config_dir / "config.yaml").write_text(config_text, encoding="utf-8")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()  # must not raise
                self.assert_true(bootstrap.workflow_engine_service is None)
                self.assert_true(bootstrap.automation_service is None)

    def _test_bootstrap_on_demand_run_triggers_automation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.workflow_engine_service is not None)
                self.assert_true(bootstrap.automation_service is not None)

                engine_service = bootstrap.workflow_engine_service
                automation_service = bootstrap.automation_service

                trigger = WorkflowDefinition(
                    id="e2e-trigger",
                    name="e2e-trigger",
                    description="",
                    enabled=True,
                    steps=(WorkflowRequestStep(name="Step", request="noop"),),
                )
                action = WorkflowDefinition(
                    id="e2e-action",
                    name="e2e-action",
                    description="",
                    enabled=True,
                    steps=(WorkflowRequestStep(name="Step", request="noop"),),
                )
                # Register directly on the manager reachable through the service.
                engine_service._manager.registry.register(trigger)  # noqa: SLF001
                engine_service._manager.registry.register(action)  # noqa: SLF001

                rule_result = automation_service.register(
                    _automation_rule(
                        "e2e-rule",
                        trigger_workflow_id="e2e-trigger",
                        condition=AutomationTriggerCondition.ON_ANY,
                        action_workflow_id="e2e-action",
                    )
                )
                self.assert_true(rule_result.success)

                outcome = engine_service.run("e2e-trigger")
                self.assert_true(outcome.success)

                rule = automation_service.get_rule("e2e-rule")
                self.assert_true(rule.last_triggered is not None)
                self.assert_true(rule.last_action_success)

    def _test_bootstrap_scheduled_run_triggers_automation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.workflow_scheduler_service is not None)
                self.assert_true(bootstrap.automation_service is not None)

                engine_service = bootstrap.workflow_engine_service
                scheduler_service = bootstrap.workflow_scheduler_service
                automation_service = bootstrap.automation_service

                trigger = WorkflowDefinition(
                    id="e2e-sched-trigger",
                    name="e2e-sched-trigger",
                    description="",
                    enabled=True,
                    steps=(WorkflowRequestStep(name="Step", request="noop"),),
                )
                action = WorkflowDefinition(
                    id="e2e-sched-action",
                    name="e2e-sched-action",
                    description="",
                    enabled=True,
                    steps=(WorkflowRequestStep(name="Step", request="noop"),),
                )
                engine_service._manager.registry.register(trigger)  # noqa: SLF001
                engine_service._manager.registry.register(action)  # noqa: SLF001

                automation_service.register(
                    _automation_rule(
                        "e2e-sched-rule",
                        trigger_workflow_id="e2e-sched-trigger",
                        condition=AutomationTriggerCondition.ON_ANY,
                        action_workflow_id="e2e-sched-action",
                    )
                )

                scheduler_service.register(
                    ScheduledWorkflow(
                        id="e2e-sched-entry",
                        name="e2e-sched-entry",
                        description="",
                        workflow_id="e2e-sched-trigger",
                        schedule=Schedule(type=ScheduleType.MANUAL),
                    )
                )
                run_result = scheduler_service.run("e2e-sched-entry")
                self.assert_true(run_result.success)

                rule = automation_service.get_rule("e2e-sched-rule")
                self.assert_true(rule.last_triggered is not None)
                self.assert_true(rule.last_action_success)

    def _test_bootstrap_disabled_automation_never_fires(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, automation_enabled=False)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.automation_service is not None)
                self.assert_false(bootstrap.automation_service.status().enabled)

                engine_service = bootstrap.workflow_engine_service
                automation_service = bootstrap.automation_service

                trigger = WorkflowDefinition(
                    id="e2e-off-trigger",
                    name="e2e-off-trigger",
                    description="",
                    enabled=True,
                    steps=(WorkflowRequestStep(name="Step", request="noop"),),
                )
                action = WorkflowDefinition(
                    id="e2e-off-action",
                    name="e2e-off-action",
                    description="",
                    enabled=True,
                    steps=(WorkflowRequestStep(name="Step", request="noop"),),
                )
                engine_service._manager.registry.register(trigger)  # noqa: SLF001
                engine_service._manager.registry.register(action)  # noqa: SLF001

                # Registering a rule through the disabled service is itself rejected...
                rule_result = automation_service.register(
                    _automation_rule(
                        "e2e-off-rule",
                        trigger_workflow_id="e2e-off-trigger",
                        condition=AutomationTriggerCondition.ON_ANY,
                        action_workflow_id="e2e-off-action",
                    )
                )
                self.assert_false(rule_result.success)

                # ...and even if a rule existed, the hook was never wired at
                # Bootstrap time, so running the trigger workflow cannot fire it.
                outcome = engine_service.run("e2e-off-trigger")
                self.assert_true(outcome.success)
                self.assert_equal(len(automation_service.list_rules()), 0)

    # ---------- Backward compatibility ----------

    def _test_workflow_engine_service_unaffected_without_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "bc-wf")
            service = WorkflowEngineService(manager=manager, engine=engine)
            outcome = service.run("bc-wf")
            self.assert_true(outcome.success)
            self.assert_equal(outcome.definition_id, "bc-wf")
            self.assert_true(outcome.result is not None)

    def _test_workflow_scheduler_engine_unaffected_without_hook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, manager = _build_workflow_engine(Path(tmp))
            _register_workflow(manager, "bc-sched-wf")
            scheduler_engine = WorkflowSchedulerEngine(
                registry=ScheduledWorkflowRegistry(), workflow_engine=engine
            )
            scheduler_engine.register_entry(
                ScheduledWorkflow(
                    id="bc-entry",
                    name="bc-entry",
                    description="",
                    workflow_id="bc-sched-wf",
                    schedule=Schedule(type=ScheduleType.MANUAL),
                )
            )
            entry = scheduler_engine.run_now("bc-entry")
            self.assert_true(entry.last_run is not None)

    def _test_bootstrap_workflow_engine_service_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                status = bootstrap.workflow_engine_service.status()
                self.assert_equal(status.current_provider, "workflow_engine")

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """EP-035 must not import an AI provider, Prompt Engine, Planning, or EP-011's Scheduler."""
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
            "src.core.scheduler.scheduler",
            "openai",
            "anthropic",
            "gemini",
            "ollama",
        )
        source = inspect.getsource(automation_engine_module)
        for fragment in forbidden_fragments:
            self.assert_true(
                fragment not in source,
                f"{automation_engine_module.__name__} must not reference '{fragment}'",
            )

    def _test_no_private_api_access_on_workflow_engine(self) -> None:
        """AutomationEngine reaches WorkflowEngine only through its public run()."""
        source = inspect.getsource(automation_engine_module)
        cleaned = source.replace("self._registry", "").replace("self._workflow_engine", "")
        self.assert_true(
            "workflow_engine._" not in cleaned,
            "AutomationEngine must not access a private attribute of WorkflowEngine",
        )

    def _test_cli_namespace_is_automate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _, _ = _build_automation_service(Path(tmp))
            module = AutomationModule(service)
            self.assert_equal(module.name, "automate")
            self.assert_true(module.name != "flow")
            self.assert_true(module.name != "autoflow")

    def _test_hook_types_are_not_ep035_types(self) -> None:
        """WorkflowEngineService/WorkflowSchedulerEngine never import any EP-035 type.

        Checks actual import statements only (not docstring prose,
        which legitimately explains the hook's EP-035 purpose in both
        files) -- the architectural requirement is that neither module
        imports `src.core.automation_engine` or `AutomationEngine`,
        not that the word "Automation" never appears in a comment.
        """
        from src.services import workflow_engine_service as workflow_engine_service_module
        from src.core.workflow_scheduler import (
            workflow_scheduler_engine as workflow_scheduler_engine_module,
        )

        for module in (workflow_engine_service_module, workflow_scheduler_engine_module):
            import_lines = [
                line
                for line in inspect.getsource(module).splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            for line in import_lines:
                self.assert_true(
                    "automation_engine" not in line and "Automation" not in line,
                    f"{module.__name__} must not import any EP-035 type or module: {line!r}",
                )
