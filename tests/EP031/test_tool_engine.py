"""Real engineering tests for EP-031 - Tool Engine.

Builds real `Tool`/`ToolResult`/`ToolProvider`/`DefaultToolProvider`/
`ToolManager`/`ToolEngine`/`ToolExecutionProvider`/`ToolService`/
`ToolModule` instances -- composed, where needed, with a real EP-030
`PlanExecutionEngine`/`PlanExecutionManager` and a real EP-029
`PlanningEngine`/`PlanningManager` -- and drives them exactly as a
caller would, no mocked internals, matching every other EP's test
suite in this project (see tests/EP030/test_plan_execution_engine.py).

Tool Engine (EP-031) is a new, independent package
(`src/core/tool/`) that turns an already-identified `(subsystem,
action)` reference into a real invocation of an already-implemented
Engineering Package's public API -- no AI reasoning, no planning, no
plan walking, and no dispatch-order/failure-policy logic. This suite
covers:

1. The domain model: `ToolStatus`, `ToolResult`, `Tool`.
2. The provider abstraction: `ToolProvider` (abstract contract),
   `DefaultToolProvider` (built-in, real-invocation provider) --
   successful handler, failing handler.
3. `ToolRegistry`: registration, duplicate/unknown handling,
   subsystem/action lookup.
4. `ToolManager`: configuration validation, registration,
   enable/disable, active-provider switching, status.
5. `ToolEngine`: the lookup -> real-invocation pipeline -- invoke by
   id, invoke by (subsystem, action), unknown tool, no provider
   selected.
6. `ToolExecutionProvider`: the EP-030 `PlanExecutionProvider` bridge
   -- real dispatch of a `PlanStep` into a real invocation, and the
   honest-failure path for an action with no registered tool.
7. `ToolService`/`ToolModule`: configuration-driven construction and
   every CLI command ("status", "providers", "list", "use", "run",
   "help").
8. Bootstrap wiring: real tool registration from already-built
   subsystem services, graceful degradation on invalid 'tool.*'
   configuration, the bridge provider registered with
   `PlanExecutionManager` without changing its default, and a full
   pipeline exercised end to end through both the "tool" and
   "execution" CLI namespaces.
9. Backward compatibility: EP-030's own default behavior
   ('plan_execution.default_provider' unchanged) is provably
   unaffected by EP-031 being wired in.
10. Architecture compliance: no forbidden imports, no private-API
    access into EP-029/EP-030 objects, no duplicated provider/manager
    logic, correct exception hierarchy.
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.config import Config
from src.core.plan_execution.plan_execution_engine import PlanExecutionEngine
from src.core.plan_execution.plan_execution_manager import PlanExecutionManager
from src.core.plan_execution.plan_execution_result import StepStatus
from src.core.planning.planning_engine import PlanningEngine
from src.core.planning.planning_manager import PlanningManager
from src.core.planning.planning_result import Plan, PlanStep
from src.core.tool import tool_engine as tool_engine_module
from src.core.tool import tool_execution_provider as tool_execution_provider_module
from src.core.tool import tool_manager as tool_manager_module
from src.core.tool import tool_provider as tool_provider_module
from src.core.tool.tool import Tool
from src.core.tool.tool_engine import (
    NoToolProviderSelectedError,
    ToolEngine,
    ToolEngineError,
    ToolNotRegisteredError,
)
from src.core.tool.tool_execution_provider import ToolExecutionProvider
from src.core.tool.tool_manager import (
    ToolManager,
    ToolProviderNotFoundError,
    ToolProviderRegistryError,
)
from src.core.tool.tool_provider import (
    DefaultToolProvider,
    ToolConfigurationError,
    ToolError,
    ToolProvider,
)
from src.core.tool.tool_registry import ToolNotFoundError, ToolRegistry, ToolRegistryError
from src.core.tool.tool_result import ToolResult, ToolStatus
from src.modules.tool_module import ToolModule
from src.services.tool_service import ToolService
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


_DEFAULT_TOOL_YAML = "tool:\n  enabled: true\n  default_provider: \"tool_engine\"\n"

_DISABLED_TOOL_YAML = "tool:\n  enabled: false\n  default_provider: \"tool_engine\"\n"

_INVALID_PROVIDER_TOOL_YAML = "tool:\n  enabled: true\n  default_provider: \"\"\n"

_INVALID_ENABLED_TOOL_YAML = "tool:\n  enabled: \"yes\"\n  default_provider: \"tool_engine\"\n"

_UNKNOWN_PROVIDER_TOOL_YAML = (
    "tool:\n  enabled: true\n  default_provider: \"does-not-exist\"\n"
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


# Full, offline-safe config.yaml covering every section
# Bootstrap._build_command_router reads, so a real Bootstrap.initialize()
# can be exercised end to end in a temporary project root without any
# network access or long-lived background threads. Mirrors
# tests/EP030/test_plan_execution_engine.py's own copy, plus the new
# 'tool:' section EP-031 introduces.
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
    "  enabled: {tool_enabled}\n"
    "  default_provider: \"{tool_default_provider}\"\n"
)


def _write_full_bootstrap_config(
    directory: Path,
    tool_enabled: bool = True,
    tool_default_provider: str = "tool_engine",
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            tool_enabled=str(tool_enabled).lower(),
            tool_default_provider=tool_default_provider,
        ),
        encoding="utf-8",
    )


def _step(order: int, subsystem: str | None, action: str, available: bool = True) -> PlanStep:
    """Build a PlanStep for tests without needing a real PlanningProvider."""
    return PlanStep(
        order=order, subsystem=subsystem, action=action, description="test step", available=available
    )


def _recording_tool(tool_id: str = "recorder", subsystem: str | None = "memory", action: str = "retrieve_from_memory", value: object = "recorded") -> Tool:
    """Build a Tool whose handler returns a fixed value -- no real subsystem needed."""
    return Tool(
        id=tool_id,
        name="Recorder",
        description="A tool used only for testing.",
        subsystem=subsystem,
        action=action,
        handler=lambda: value,
    )


def _failing_tool(tool_id: str = "failer") -> Tool:
    """Build a Tool whose handler always raises."""

    def _raise() -> object:
        raise RuntimeError("handler exploded")

    return Tool(
        id=tool_id,
        name="Failer",
        description="A tool whose handler always raises.",
        subsystem="custom",
        action="do_something_unrecognized",
        handler=_raise,
    )


@TestRegistry.register
class ToolEngineTest(BaseTest):
    NAME = "EP031"

    def run(self):
        # ---------- Domain model ----------
        self._test_tool_status_values()
        self._test_tool_result_construction()
        self._test_tool_construction()

        # ---------- ToolProvider / DefaultToolProvider ----------
        self._test_provider_is_abstract()
        self._test_default_provider_name()
        self._test_default_provider_successful_handler_completes()
        self._test_default_provider_failing_handler_fails_gracefully()
        self._test_default_provider_status()

        # ---------- ToolRegistry ----------
        self._test_registry_register_and_get()
        self._test_registry_duplicate_registration_raises()
        self._test_registry_unknown_tool_raises()
        self._test_registry_find_returns_none_for_unknown()
        self._test_registry_find_for_step_matches()
        self._test_registry_find_for_step_ignores_disabled()
        self._test_registry_list_ordered_by_id()
        self._test_registry_unregister()

        # ---------- ToolManager ----------
        self._test_manager_registers_default_provider()
        self._test_manager_config_defaults()
        self._test_manager_invalid_enabled_raises()
        self._test_manager_invalid_default_provider_raises()
        self._test_manager_unknown_configured_provider_raises()
        self._test_manager_duplicate_provider_registration_raises()
        self._test_manager_unknown_provider_raises()
        self._test_manager_set_current_switches_provider()
        self._test_manager_disable_clears_current()
        self._test_manager_current_provider_name_none_when_disabled_via_config()
        self._test_manager_owns_registry()

        # ---------- ToolEngine ----------
        self._test_engine_list_tools_empty_by_default()
        self._test_engine_invoke_unregistered_tool_raises()
        self._test_engine_invoke_no_provider_selected_raises()
        self._test_engine_invoke_success()
        self._test_engine_invoke_for_step_matches_real_tool()
        self._test_engine_invoke_for_step_no_match_returns_failed_not_raise()

        # ---------- ToolExecutionProvider (EP-030 bridge) ----------
        self._test_bridge_provider_name()
        self._test_bridge_dispatches_matching_step_to_completed()
        self._test_bridge_no_matching_tool_reports_failed_step()
        self._test_bridge_failing_handler_reports_failed_step()
        self._test_bridge_is_available()
        self._test_bridge_never_skips()
        self._test_bridge_integrates_with_real_plan_execution_engine()

        # ---------- ToolService ----------
        self._test_service_status_and_providers()
        self._test_service_list_tools()
        self._test_service_use_unknown_provider_fails_gracefully()
        self._test_service_run_success_and_failure()
        self._test_service_disable()

        # ---------- ToolModule (CLI) ----------
        self._test_cli_help_lists_commands()
        self._test_cli_status_command()
        self._test_cli_providers_command()
        self._test_cli_list_command()
        self._test_cli_use_command()
        self._test_cli_run_command_usage_and_results()
        self._test_cli_unknown_action()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_registers_tool_module()
        self._test_bootstrap_real_tools_registered_from_subsystem_services()
        self._test_bootstrap_degrades_gracefully_on_invalid_tool_config()
        self._test_bootstrap_disabled_tool_engine_still_boots()
        self._test_bootstrap_full_pipeline_via_tool_cli()

        # ---------- Backward compatibility with EP-030 ----------
        self._test_bootstrap_plan_execution_default_provider_unchanged()
        self._test_bootstrap_plan_execution_default_behavior_unchanged()
        self._test_bootstrap_tool_engine_provider_registered_but_not_selected()
        self._test_bootstrap_switching_to_tool_engine_produces_real_invocation()
        self._test_bootstrap_os_level_execution_engine_unaffected()

        # ---------- Architectural acceptance criteria ----------
        self._test_no_forbidden_imports()
        self._test_no_ai_or_planning_imports_in_core_tool_files()
        self._test_manager_owns_no_plan_or_step_storage()
        self._test_exception_hierarchy()
        self._test_no_private_api_access_on_foreign_objects()
        self._test_bridge_is_only_file_coupling_tool_and_plan_execution()

        return self.result

    # ---------- Helpers ----------

    def _build_manager(self, tmp_path: Path, yaml_text: str = _DEFAULT_TOOL_YAML) -> ToolManager:
        config = _write_config(tmp_path, yaml_text)
        return ToolManager(config=config)

    def _build_engine(self, tmp_path: Path, yaml_text: str = _DEFAULT_TOOL_YAML) -> ToolEngine:
        manager = self._build_manager(tmp_path, yaml_text)
        return ToolEngine(manager=manager)

    def _build_service(self, tmp_path: Path, yaml_text: str = _DEFAULT_TOOL_YAML) -> ToolService:
        engine = self._build_engine(tmp_path, yaml_text)
        return ToolService(manager=engine._manager, engine=engine)  # noqa: SLF001

    def _build_plan_execution_engine(self, tmp_path: Path) -> PlanExecutionEngine:
        pe_config = _write_config(
            tmp_path / "pe",
            "plan_execution:\n  enabled: true\n  default_provider: \"plan_execution\"\n  stop_on_failure: true\n",
        )
        return PlanExecutionEngine(manager=PlanExecutionManager(config=pe_config))

    # ---------- Domain model ----------

    def _test_tool_status_values(self) -> None:
        self.assert_equal(ToolStatus.COMPLETED.value, "COMPLETED")
        self.assert_equal(ToolStatus.FAILED.value, "FAILED")

    def _test_tool_result_construction(self) -> None:
        result = ToolResult(tool_id="x", status=ToolStatus.COMPLETED, message="ok", data=[1, 2])
        self.assert_equal(result.tool_id, "x")
        self.assert_equal(result.status, ToolStatus.COMPLETED)
        self.assert_equal(result.data, [1, 2])

        default_result = ToolResult(tool_id="y", status=ToolStatus.FAILED, message="nope")
        self.assert_true(default_result.data is None)

    def _test_tool_construction(self) -> None:
        tool = _recording_tool()
        self.assert_equal(tool.id, "recorder")
        self.assert_equal(tool.subsystem, "memory")
        self.assert_equal(tool.action, "retrieve_from_memory")
        self.assert_true(tool.enabled)
        self.assert_equal(tool.handler(), "recorded")

    # ---------- ToolProvider / DefaultToolProvider ----------

    def _test_provider_is_abstract(self) -> None:
        try:
            ToolProvider()  # type: ignore[abstract]
        except TypeError:
            self.result.add_pass()
        else:
            self.assert_true(False, "ToolProvider must be abstract")

    def _test_default_provider_name(self) -> None:
        provider = DefaultToolProvider()
        self.assert_equal(provider.provider_name(), "tool_engine")

    def _test_default_provider_successful_handler_completes(self) -> None:
        provider = DefaultToolProvider()
        tool = _recording_tool(value=42)
        result = provider.invoke_tool(tool)
        self.assert_equal(result.status, ToolStatus.COMPLETED)
        self.assert_equal(result.data, 42)
        self.assert_true("invoked successfully" in result.message)

    def _test_default_provider_failing_handler_fails_gracefully(self) -> None:
        provider = DefaultToolProvider()
        tool = _failing_tool()
        result = provider.invoke_tool(tool)
        self.assert_equal(result.status, ToolStatus.FAILED)
        self.assert_true("handler exploded" in result.message)
        self.assert_true(result.data is None)

    def _test_default_provider_status(self) -> None:
        provider = DefaultToolProvider()
        self.assert_true(provider.is_available())

    # ---------- ToolRegistry ----------

    def _test_registry_register_and_get(self) -> None:
        registry = ToolRegistry()
        tool = _recording_tool()
        registry.register(tool)
        self.assert_true(registry.get("recorder") is tool)
        self.assert_true(registry.is_registered("recorder"))

    def _test_registry_duplicate_registration_raises(self) -> None:
        registry = ToolRegistry()
        registry.register(_recording_tool())
        try:
            registry.register(_recording_tool())
        except ToolRegistryError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Expected ToolRegistryError")

    def _test_registry_unknown_tool_raises(self) -> None:
        registry = ToolRegistry()
        try:
            registry.get("does-not-exist")
        except ToolNotFoundError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Expected ToolNotFoundError")

    def _test_registry_find_returns_none_for_unknown(self) -> None:
        registry = ToolRegistry()
        self.assert_true(registry.find("nope") is None)

    def _test_registry_find_for_step_matches(self) -> None:
        registry = ToolRegistry()
        tool = _recording_tool(subsystem="knowledge", action="query_knowledge_base")
        registry.register(tool)
        found = registry.find_for_step("knowledge", "query_knowledge_base")
        self.assert_true(found is tool)
        self.assert_true(registry.find_for_step("knowledge", "other_action") is None)
        self.assert_true(registry.find_for_step("other_subsystem", "query_knowledge_base") is None)

    def _test_registry_find_for_step_ignores_disabled(self) -> None:
        registry = ToolRegistry()
        disabled_tool = Tool(
            id="disabled_tool",
            name="Disabled",
            description="disabled",
            subsystem="memory",
            action="retrieve_from_memory",
            handler=lambda: None,
            enabled=False,
        )
        registry.register(disabled_tool)
        self.assert_true(registry.find_for_step("memory", "retrieve_from_memory") is None)

    def _test_registry_list_ordered_by_id(self) -> None:
        registry = ToolRegistry()
        registry.register(_recording_tool(tool_id="zzz"))
        registry.register(_recording_tool(tool_id="aaa", subsystem="agent", action="coordinate_subsystems"))
        ids = [tool.id for tool in registry.list()]
        self.assert_equal(ids, ["aaa", "zzz"])

    def _test_registry_unregister(self) -> None:
        registry = ToolRegistry()
        registry.register(_recording_tool())
        registry.unregister("recorder")
        self.assert_false(registry.is_registered("recorder"))
        try:
            registry.unregister("recorder")
        except ToolNotFoundError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Expected ToolNotFoundError")

    # ---------- ToolManager ----------

    def _test_manager_registers_default_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            providers = manager.list_providers()
            self.assert_equal(len(providers), 1)
            self.assert_equal(providers[0].provider_name(), "tool_engine")
            self.assert_equal(manager.current_provider_name(), "tool_engine")

    def _test_manager_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            self.assert_true(manager.is_enabled())

    def _test_manager_invalid_enabled_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_ENABLED_TOOL_YAML)
            except ToolConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected ToolConfigurationError")

    def _test_manager_invalid_default_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_PROVIDER_TOOL_YAML)
            except ToolConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected ToolConfigurationError")

    def _test_manager_unknown_configured_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _UNKNOWN_PROVIDER_TOOL_YAML)
            except ToolConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected ToolConfigurationError")

    def _test_manager_duplicate_provider_registration_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.register_provider(DefaultToolProvider())
            except ToolProviderRegistryError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected ToolProviderRegistryError")

    def _test_manager_unknown_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.get_provider("does-not-exist")
            except ToolProviderNotFoundError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected ToolProviderNotFoundError")

            try:
                manager.set_current("does-not-exist")
            except ToolProviderNotFoundError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected ToolProviderNotFoundError")

    def _test_manager_set_current_switches_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))

            class _Recorder(ToolProvider):
                def provider_name(self) -> str:
                    return "recorder"

                def invoke_tool(self, tool: Tool) -> ToolResult:
                    return ToolResult(tool_id=tool.id, status=ToolStatus.COMPLETED, message="recorded")

            recorder = _Recorder()
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
            manager = self._build_manager(Path(tmp), _DISABLED_TOOL_YAML)
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.current_provider_name() is None)

    def _test_manager_owns_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.register_tool(_recording_tool())
            self.assert_true(manager.registry.is_registered("recorder"))

    # ---------- ToolEngine ----------

    def _test_engine_list_tools_empty_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            self.assert_equal(engine.list_tools(), [])

    def _test_engine_invoke_unregistered_tool_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            try:
                engine.invoke("does-not-exist")
            except ToolNotRegisteredError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected ToolNotRegisteredError")

    def _test_engine_invoke_no_provider_selected_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.register_tool(_recording_tool())
            engine = ToolEngine(manager=manager)
            manager.disable()
            try:
                engine.invoke("recorder")
            except NoToolProviderSelectedError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected NoToolProviderSelectedError")

    def _test_engine_invoke_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.register_tool(_recording_tool(value="hello"))
            engine = ToolEngine(manager=manager)
            result = engine.invoke("recorder")
            self.assert_equal(result.status, ToolStatus.COMPLETED)
            self.assert_equal(result.data, "hello")

    def _test_engine_invoke_for_step_matches_real_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.register_tool(
                _recording_tool(subsystem="knowledge", action="query_knowledge_base", value=["a", "b"])
            )
            engine = ToolEngine(manager=manager)
            result = engine.invoke_for_step("knowledge", "query_knowledge_base")
            self.assert_equal(result.status, ToolStatus.COMPLETED)
            self.assert_equal(result.data, ["a", "b"])

    def _test_engine_invoke_for_step_no_match_returns_failed_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            result = engine.invoke_for_step("embedding", "generate_embedding")
            self.assert_equal(result.status, ToolStatus.FAILED)
            self.assert_true("No tool registered" in result.message)

    # ---------- ToolExecutionProvider (EP-030 bridge) ----------

    def _test_bridge_provider_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            bridge = ToolExecutionProvider(tool_engine=engine)
            self.assert_equal(bridge.provider_name(), "tool_engine")

    def _test_bridge_dispatches_matching_step_to_completed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.register_tool(
                _recording_tool(subsystem="semantic", action="semantic_search", value="found")
            )
            engine = ToolEngine(manager=manager)
            bridge = ToolExecutionProvider(tool_engine=engine)
            step = _step(1, "semantic", "semantic_search")
            step_result = bridge.execute_step(step)
            self.assert_equal(step_result.status, StepStatus.COMPLETED)
            self.assert_true(step_result.step is step)

    def _test_bridge_no_matching_tool_reports_failed_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            bridge = ToolExecutionProvider(tool_engine=engine)
            step = _step(1, "rag", "retrieve_context")
            step_result = bridge.execute_step(step)
            self.assert_equal(step_result.status, StepStatus.FAILED)
            self.assert_true("No tool registered" in step_result.message)

    def _test_bridge_failing_handler_reports_failed_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.register_tool(_failing_tool())
            engine = ToolEngine(manager=manager)
            bridge = ToolExecutionProvider(tool_engine=engine)
            step = _step(1, "custom", "do_something_unrecognized")
            step_result = bridge.execute_step(step)
            self.assert_equal(step_result.status, StepStatus.FAILED)
            self.assert_true("handler exploded" in step_result.message)

    def _test_bridge_is_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            bridge = ToolExecutionProvider(tool_engine=engine)
            self.assert_true(bridge.is_available())

    def _test_bridge_never_skips(self) -> None:
        """StepStatus.SKIPPED must never be produced by the bridge itself."""
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            bridge = ToolExecutionProvider(tool_engine=engine)
            step = _step(1, "rag", "retrieve_context")
            step_result = bridge.execute_step(step)
            self.assert_true(step_result.status in (StepStatus.COMPLETED, StepStatus.FAILED))

    def _test_bridge_integrates_with_real_plan_execution_engine(self) -> None:
        """End-to-end: a real PlanExecutionEngine dispatches to a real ToolExecutionProvider."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            tool_manager = self._build_manager(tmp_path / "tool")
            tool_manager.register_tool(
                _recording_tool(subsystem="knowledge", action="query_knowledge_base", value="ok")
            )
            tool_engine = ToolEngine(manager=tool_manager)
            bridge = ToolExecutionProvider(tool_engine=tool_engine)

            pe_engine = self._build_plan_execution_engine(tmp_path)
            pe_engine._manager.register_provider(bridge)  # noqa: SLF001
            pe_engine._manager.set_current("tool_engine")  # noqa: SLF001

            plan = Plan(
                request="query the knowledge base",
                steps=[_step(1, "knowledge", "query_knowledge_base")],
            )
            result = pe_engine.execute_plan(plan)
            self.assert_equal(result.completed_count, 1)
            self.assert_equal(result.failed_count, 0)
            self.assert_true(result.success)

    # ---------- ToolService ----------

    def _test_service_status_and_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            status = service.status()
            self.assert_true(status.enabled)
            self.assert_equal(status.current_provider, "tool_engine")
            self.assert_equal(status.registered_provider_count, 1)
            self.assert_equal(status.registered_tool_count, 0)

            providers = service.list_providers()
            self.assert_equal(len(providers), 1)
            self.assert_equal(providers[0].name, "tool_engine")
            self.assert_true(providers[0].is_current)

    def _test_service_list_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            engine._manager.register_tool(_recording_tool())  # noqa: SLF001
            service = ToolService(manager=engine._manager, engine=engine)  # noqa: SLF001
            tools = service.list_tools()
            self.assert_equal(len(tools), 1)
            self.assert_equal(tools[0].id, "recorder")
            self.assert_equal(tools[0].subsystem, "memory")

    def _test_service_use_unknown_provider_fails_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.use_provider("does-not-exist")
            self.assert_false(result.success)

    def _test_service_run_success_and_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            engine._manager.register_tool(_recording_tool(value="ok"))  # noqa: SLF001
            service = ToolService(manager=engine._manager, engine=engine)  # noqa: SLF001

            success_outcome = service.run("recorder")
            self.assert_true(success_outcome.success)
            self.assert_equal(success_outcome.result.status, ToolStatus.COMPLETED)

            failure_outcome = service.run("does-not-exist")
            self.assert_false(failure_outcome.success)
            self.assert_true(failure_outcome.result is None)

    def _test_service_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.disable()
            self.assert_true(result.success)
            self.assert_false(service.status().enabled)

    # ---------- ToolModule (CLI) ----------

    def _test_cli_help_lists_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ToolModule(service)
            self.assert_equal(module.name, "tool")
            result = module.execute("help", [])
            self.assert_true(result.success)
            self.assert_true("tool run <tool_id>" in result.message)

    def _test_cli_status_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ToolModule(service)
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Tool Engine Status" in result.message)

    def _test_cli_providers_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ToolModule(service)
            result = module.execute("providers", [])
            self.assert_true(result.success)
            self.assert_true("tool_engine" in result.message)

    def _test_cli_list_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            engine._manager.register_tool(_recording_tool())  # noqa: SLF001
            service = ToolService(manager=engine._manager, engine=engine)  # noqa: SLF001
            module = ToolModule(service)
            result = module.execute("list", [])
            self.assert_true(result.success)
            self.assert_true("recorder" in result.message)

            empty_service = self._build_service(Path(tmp) / "empty")
            empty_module = ToolModule(empty_service)
            empty_result = empty_module.execute("list", [])
            self.assert_true(empty_result.success)
            self.assert_true("No tools registered" in empty_result.message)

    def _test_cli_use_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ToolModule(service)
            self.assert_false(module.execute("use", []).success)
            self.assert_false(module.execute("use", ["nope"]).success)
            self.assert_true(module.execute("use", ["tool_engine"]).success)

    def _test_cli_run_command_usage_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            engine._manager.register_tool(_recording_tool())  # noqa: SLF001
            service = ToolService(manager=engine._manager, engine=engine)  # noqa: SLF001
            module = ToolModule(service)
            self.assert_false(module.execute("run", []).success)
            result = module.execute("run", ["recorder"])
            self.assert_true(result.success)
            self.assert_true("COMPLETED" in result.message)

    def _test_cli_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ToolModule(service)
            result = module.execute("bogus", [])
            self.assert_false(result.success)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_tool_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                service = bootstrap.tool_service
                self.assert_true(service is not None)
                status = service.status()
                self.assert_true(status.enabled)
                self.assert_equal(status.current_provider, "tool_engine")

                result = bootstrap._command_router.dispatch("tool status")  # noqa: SLF001
                self.assert_true(result.success)

    def _test_bootstrap_real_tools_registered_from_subsystem_services(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                tools = {tool.id for tool in bootstrap.tool_service.list_tools()}
                self.assert_true("memory_recall" in tools)
                self.assert_true("knowledge_query" in tools)
                self.assert_true("long_term_memory_query" in tools)
                self.assert_true("agent_coordinate" in tools)
                self.assert_true("acknowledge_request" in tools)

                run_result = bootstrap._command_router.dispatch("tool run memory_recall")  # noqa: SLF001
                self.assert_true(run_result.success)
                self.assert_true("COMPLETED" in run_result.message)

    def _test_bootstrap_degrades_gracefully_on_invalid_tool_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, tool_default_provider="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()  # must not raise -- Tool Engine degrades
                self.assert_true(bootstrap.tool_service is None)
                # The rest of the application is unaffected.
                self.assert_true(bootstrap.knowledge_service is not None)
                self.assert_true(bootstrap.plan_execution_service is not None)

    def _test_bootstrap_disabled_tool_engine_still_boots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, tool_enabled=False)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.tool_service is not None)
                self.assert_false(bootstrap.tool_service.status().enabled)

    def _test_bootstrap_full_pipeline_via_tool_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                result = bootstrap._command_router.dispatch("tool run agent_coordinate")  # noqa: SLF001
                self.assert_true(result.success)
                self.assert_true("COMPLETED" in result.message)

    # ---------- Backward compatibility with EP-030 ----------

    def _test_bootstrap_plan_execution_default_provider_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                status = bootstrap.plan_execution_service.status()
                self.assert_equal(status.current_provider, "plan_execution")

    def _test_bootstrap_plan_execution_default_behavior_unchanged(self) -> None:
        """EP-030's own default dispatch output must be byte-for-byte identical to pre-EP-031."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    'execution run "remember my preferences"'
                )
                self.assert_true(result.success)
                self.assert_true("No Tool Engine is registered yet (future EP)" in result.message)

    def _test_bootstrap_tool_engine_provider_registered_but_not_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                providers_result = bootstrap._command_router.dispatch("execution providers")  # noqa: SLF001
                self.assert_true("tool_engine" in providers_result.message)
                self.assert_true("plan_execution" in providers_result.message)
                status = bootstrap.plan_execution_service.status()
                self.assert_equal(status.registered_provider_count, 2)

    def _test_bootstrap_switching_to_tool_engine_produces_real_invocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                switch_result = bootstrap._command_router.dispatch("execution use tool_engine")  # noqa: SLF001
                self.assert_true(switch_result.success)

                run_result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    'execution run "remember my preferences"'
                )
                self.assert_true(run_result.success)
                self.assert_true("Completed : 1" in run_result.message)
                self.assert_true(
                    "No Tool Engine is registered yet" not in run_result.message
                )

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
        """EP-031 must not import an AI provider, Prompt Engine, Planning, or a Planning provider."""
        forbidden_fragments = (
            "src.core.ai",
            "src.core.reasoning",
            "src.core.reflection",
            "src.core.prompt",
            "src.core.conversation",
            "browser_automation",
            "openai",
            "anthropic",
            "gemini",
            "ollama",
        )
        for module in (tool_engine_module, tool_manager_module, tool_provider_module):
            source = inspect.getsource(module)
            for fragment in forbidden_fragments:
                self.assert_true(
                    fragment not in source, f"{module.__name__} must not reference '{fragment}'"
                )

    def _test_no_ai_or_planning_imports_in_core_tool_files(self) -> None:
        """tool.py/tool_result.py/tool_registry.py must depend on nothing but stdlib + loguru."""
        for module_name in ("tool", "tool_result", "tool_registry"):
            module = __import__(f"src.core.tool.{module_name}", fromlist=[module_name])
            source = inspect.getsource(module)
            self.assert_true("src.core.planning" not in source, f"{module_name} must not import Planning Engine")
            self.assert_true(
                "src.core.plan_execution" not in source,
                f"{module_name} must not import Plan Execution Engine",
            )

    def _test_manager_owns_no_plan_or_step_storage(self) -> None:
        """ToolManager owns provider registration and the tool catalog only, never plan/step storage."""
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            instance_attrs = vars(manager)
            forbidden_attr_names = ("_plans", "_steps", "_records", "_collection", "_documents", "_index")
            for attr_name in instance_attrs:
                for forbidden in forbidden_attr_names:
                    self.assert_true(
                        forbidden not in attr_name.lower(),
                        f"ToolManager should not own plan/step storage ('{attr_name}')",
                    )

    def _test_exception_hierarchy(self) -> None:
        """ToolEngineError is catchable through the shared ToolError root."""
        self.assert_true(issubclass(ToolEngineError, ToolError))
        try:
            raise ToolEngineError("boom")
        except ToolError:
            self.result.add_pass()
        else:
            self.assert_true(False, "ToolEngineError should be catchable as ToolError")

    def _test_no_private_api_access_on_foreign_objects(self) -> None:
        """ToolEngine reaches ToolManager only through public methods/fields."""
        source = inspect.getsource(tool_engine_module)
        self.assert_true(
            "manager._" not in source.replace("self._manager", ""),
            "ToolEngine must not access a private attribute of ToolManager",
        )

    def _test_bridge_is_only_file_coupling_tool_and_plan_execution(self) -> None:
        """Only tool_execution_provider.py may import both src.core.tool and src.core.plan_execution."""
        for module_name in ("tool", "tool_result", "tool_registry", "tool_provider", "tool_manager", "tool_engine"):
            module = __import__(f"src.core.tool.{module_name}", fromlist=[module_name])
            source = inspect.getsource(module)
            self.assert_true(
                "src.core.plan_execution" not in source,
                f"{module_name} must not import src.core.plan_execution -- "
                "only tool_execution_provider.py may bridge the two packages",
            )

        bridge_source = inspect.getsource(tool_execution_provider_module)
        self.assert_true("src.core.plan_execution" in bridge_source)
        self.assert_true("src.core.tool" in bridge_source or "src.core.tool.tool_engine" in bridge_source)
