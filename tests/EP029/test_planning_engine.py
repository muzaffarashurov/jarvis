"""Real engineering tests for EP-029 - Planning Engine.

Builds real `PlanStep`/`Plan`/`PlanningProvider`/`DefaultPlanningProvider`/
`PlanningManager`/`PlanningEngine`/`PlanningService`/`PlanningModule`
instances -- composed, where needed, with a real EP-028 `AgentEngine`/
`AgentManager` -- and drives them exactly as a caller would, no mocked
internals, matching every other EP's test suite in this project (see
tests/EP028/test_agent_framework.py).

Planning Engine (EP-029) is a new, independent package
(`src/core/planning/`) that decomposes a request into an ordered Plan
of steps referencing already-implemented Engineering Packages by name
-- deterministic, fixed keyword rules only, never AI reasoning, an AI
provider call, prompt construction, or task execution. This suite
covers:

1. The domain model: `PlanStep`, `Plan`.
2. The provider abstraction: `PlanningProvider` (abstract contract),
   `DefaultPlanningProvider` (built-in, deterministic keyword-rule
   provider) -- rule matching, per-subsystem deduplication, ordering,
   the fallback step, and maximum step-count enforcement.
3. `PlanningManager`: configuration validation, registration,
   enable/disable, active-provider switching, status, and the default
   `max_steps` parameter.
4. `PlanningEngine`: the request -> Plan pipeline, including optional
   integration with a real EP-028 `AgentEngine` to reconcile per-step
   availability against a live subsystem registry.
5. `PlanningService`/`PlanningModule`: configuration-driven
   construction, graceful degradation, and every CLI command
   ("status", "providers", "use", "plan", "limits", "help").
6. Architecture compliance: no forbidden imports, no duplicated
   provider/manager/storage logic, no future-EP functionality, no
   private-API access into EP-028, and a real `Bootstrap` run proving
   normal wiring, dependency injection, and graceful degradation on
   invalid configuration.
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.agent.agent_engine import AgentEngine
from src.core.agent.agent_manager import AgentManager
from src.core.config import Config
from src.core.planning import planning_engine as planning_engine_module
from src.core.planning import planning_manager as planning_manager_module
from src.core.planning import planning_provider as planning_provider_module
from src.core.planning.planning_engine import (
    EmptyPlanningRequestError,
    NoPlanningProviderSelectedError,
    PlanningEngine,
    PlanningEngineError,
)
from src.core.planning.planning_manager import (
    PlanningManager,
    PlanningProviderNotFoundError,
    PlanningProviderRegistryError,
)
from src.core.planning.planning_provider import (
    DefaultPlanningProvider,
    PlanningConfigurationError,
    PlanningError,
    PlanningProvider,
    PlanningProviderError,
    PlanningProviderStatus,
)
from src.core.planning.planning_result import Plan, PlanStep
from src.modules.planning_module import PlanningModule
from src.services.planning_service import PlanningService
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


_DEFAULT_PLANNING_YAML = (
    "planning:\n"
    "  enabled: true\n"
    "  default_provider: \"planning\"\n"
    "  max_steps: 10\n"
)

_DISABLED_PLANNING_YAML = (
    "planning:\n"
    "  enabled: false\n"
    "  default_provider: \"planning\"\n"
    "  max_steps: 10\n"
)

_INVALID_PROVIDER_PLANNING_YAML = (
    "planning:\n"
    "  enabled: true\n"
    "  default_provider: \"\"\n"
    "  max_steps: 10\n"
)

_INVALID_MAX_STEPS_PLANNING_YAML = (
    "planning:\n"
    "  enabled: true\n"
    "  default_provider: \"planning\"\n"
    "  max_steps: 0\n"
)

_INVALID_ENABLED_PLANNING_YAML = (
    "planning:\n"
    "  enabled: \"yes\"\n"
    "  default_provider: \"planning\"\n"
    "  max_steps: 10\n"
)

_AGENT_YAML = (
    "agent:\n"
    "  enabled: true\n"
    "  default_agent: \"jarvis\"\n"
    "  startup_mode: \"idle\"\n"
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
    "  default_provider: \"{planning_default_provider}\"\n"
    "  max_steps: {max_steps}\n"
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
    planning_default_provider: str = "planning",
    max_steps: int = 10,
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            planning_default_provider=planning_default_provider, max_steps=max_steps
        ),
        encoding="utf-8",
    )


class _RecordingPlanningProvider(PlanningProvider):
    """A minimal, independent PlanningProvider used only to test PlanningManager.

    Always returns a fixed, single-step Plan, entirely separate from
    `DefaultPlanningProvider`, so tests can prove `PlanningManager`
    truly delegates to whichever provider is active rather than always
    using the built-in one.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def provider_name(self) -> str:
        return self._name

    def plan(self, request: str, max_steps: int) -> Plan:
        step = PlanStep(
            order=1, subsystem=None, action="recorded", description="recorded plan", available=True
        )
        return Plan(request=request, steps=[step], step_count=1, truncated=False)


@TestRegistry.register
class PlanningEngineTest(BaseTest):
    NAME = "EP029"

    def run(self):
        # ---------- Domain model ----------
        self._test_step_and_plan_construction()

        # ---------- PlanningProvider / DefaultPlanningProvider ----------
        self._test_provider_is_abstract()
        self._test_default_provider_name()
        self._test_default_provider_single_keyword_match()
        self._test_default_provider_multiple_keyword_matches_ordered()
        self._test_default_provider_deduplicates_per_subsystem()
        self._test_default_provider_case_insensitive()
        self._test_default_provider_fallback_step_when_no_match()
        self._test_default_provider_enforces_max_steps()
        self._test_default_provider_invalid_max_steps_raises()
        self._test_default_provider_status_and_health()

        # ---------- PlanningManager ----------
        self._test_manager_registers_default_provider()
        self._test_manager_config_defaults()
        self._test_manager_invalid_enabled_raises()
        self._test_manager_invalid_max_steps_raises()
        self._test_manager_invalid_default_provider_raises()
        self._test_manager_duplicate_registration_raises()
        self._test_manager_unknown_provider_raises()
        self._test_manager_set_current_switches_provider()
        self._test_manager_disable_clears_current()
        self._test_manager_current_provider_name_none_when_disabled_via_config()
        self._test_manager_set_max_steps_validates()

        # ---------- PlanningEngine ----------
        self._test_engine_empty_request_raises()
        self._test_engine_no_provider_selected_raises()
        self._test_engine_plan_without_agent_engine_all_available()
        self._test_engine_plan_with_agent_engine_reconciles_availability()
        self._test_engine_plan_with_agent_engine_unregistered_subsystem_unavailable()
        self._test_engine_fallback_step_always_available()

        # ---------- PlanningService ----------
        self._test_service_status_and_providers()
        self._test_service_use_unknown_provider_fails_gracefully()
        self._test_service_plan_success_and_failure()
        self._test_service_limits_get_set()
        self._test_service_disable()

        # ---------- PlanningModule (CLI) ----------
        self._test_cli_help_lists_commands()
        self._test_cli_status_command()
        self._test_cli_providers_command()
        self._test_cli_use_command()
        self._test_cli_plan_command_usage_and_results()
        self._test_cli_limits_command()
        self._test_cli_unknown_action()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_registers_planning_module()
        self._test_bootstrap_degrades_gracefully_on_invalid_planning_config()
        self._test_bootstrap_planning_independent_of_agent_availability()
        self._test_bootstrap_reconciles_against_live_subsystem_registry()

        # ---------- Architectural acceptance criteria ----------
        self._test_no_forbidden_imports()
        self._test_manager_owns_no_storage_state()
        self._test_exception_hierarchy()
        self._test_no_future_ep_components_implemented()
        self._test_no_private_api_access_on_foreign_objects()

        return self.result

    # ---------- Helpers ----------

    def _build_manager(self, tmp_path: Path, yaml_text: str = _DEFAULT_PLANNING_YAML) -> PlanningManager:
        config = _write_config(tmp_path, yaml_text)
        return PlanningManager(config=config)

    def _build_engine(
        self, tmp_path: Path, yaml_text: str = _DEFAULT_PLANNING_YAML, with_agent: bool = False
    ) -> PlanningEngine:
        manager = self._build_manager(tmp_path, yaml_text)
        if not with_agent:
            return PlanningEngine(manager=manager)

        agent_config = _write_config(tmp_path, _AGENT_YAML)
        agent_manager = AgentManager(config=agent_config)
        agent_engine = AgentEngine(manager=agent_manager)
        return PlanningEngine(manager=manager, agent_engine=agent_engine)

    def _build_service(self, tmp_path: Path, yaml_text: str = _DEFAULT_PLANNING_YAML) -> PlanningService:
        engine = self._build_engine(tmp_path, yaml_text)
        return PlanningService(manager=engine._manager, engine=engine)  # noqa: SLF001

    # ---------- Domain model ----------

    def _test_step_and_plan_construction(self) -> None:
        step = PlanStep(
            order=1, subsystem="knowledge", action="query_knowledge_base", description="Query it.", available=True
        )
        self.assert_equal(step.order, 1)
        self.assert_equal(step.subsystem, "knowledge")
        self.assert_true(step.available)

        plan = Plan(request="find something", steps=[step], step_count=1, truncated=False)
        self.assert_equal(plan.request, "find something")
        self.assert_equal(plan.step_count, 1)
        self.assert_false(plan.truncated)
        summary = plan.summary()
        self.assert_true("knowledge" in summary)
        self.assert_true("query_knowledge_base" in summary)
        self.assert_true("available" in summary)

        empty_plan = Plan(request="x")
        self.assert_equal(empty_plan.steps, [])
        self.assert_equal(empty_plan.summary(), "")

    # ---------- PlanningProvider / DefaultPlanningProvider ----------

    def _test_provider_is_abstract(self) -> None:
        try:
            PlanningProvider()  # type: ignore[abstract]
        except TypeError:
            self.result.add_pass()
        else:
            self.assert_true(False, "PlanningProvider must be abstract")

    def _test_default_provider_name(self) -> None:
        provider = DefaultPlanningProvider()
        self.assert_equal(provider.provider_name(), "planning")

    def _test_default_provider_single_keyword_match(self) -> None:
        provider = DefaultPlanningProvider()
        plan = provider.plan("please search for the answer", max_steps=10)
        self.assert_equal(plan.step_count, 1)
        self.assert_equal(plan.steps[0].subsystem, "semantic")
        self.assert_equal(plan.steps[0].action, "semantic_search")
        self.assert_true(plan.steps[0].available)
        self.assert_false(plan.truncated)

    def _test_default_provider_multiple_keyword_matches_ordered(self) -> None:
        provider = DefaultPlanningProvider()
        plan = provider.plan("search the knowledge base and compress the results", max_steps=10)
        self.assert_equal(plan.step_count, 3)
        subsystems_in_order = [step.subsystem for step in plan.steps]
        # Rule-table order: "knowledge" is scanned before "search"/"compress".
        self.assert_equal(subsystems_in_order, ["knowledge", "semantic", "compression"])
        self.assert_equal([step.order for step in plan.steps], [1, 2, 3])

    def _test_default_provider_deduplicates_per_subsystem(self) -> None:
        provider = DefaultPlanningProvider()
        plan = provider.plan("search and find and search again", max_steps=10)
        # "search" and "find" both map to "semantic" -- only one step.
        self.assert_equal(plan.step_count, 1)
        self.assert_equal(plan.steps[0].subsystem, "semantic")

    def _test_default_provider_case_insensitive(self) -> None:
        provider = DefaultPlanningProvider()
        plan = provider.plan("SEARCH for something", max_steps=10)
        self.assert_equal(plan.step_count, 1)
        self.assert_equal(plan.steps[0].subsystem, "semantic")

    def _test_default_provider_fallback_step_when_no_match(self) -> None:
        provider = DefaultPlanningProvider()
        plan = provider.plan("hello there, how are you", max_steps=10)
        self.assert_equal(plan.step_count, 1)
        self.assert_true(plan.steps[0].subsystem is None)
        self.assert_equal(plan.steps[0].action, "acknowledge_request")
        self.assert_true(plan.steps[0].available)

    def _test_default_provider_enforces_max_steps(self) -> None:
        provider = DefaultPlanningProvider()
        request = "remember knowledge long-term embed retrieve search compress coordinate"
        plan = provider.plan(request, max_steps=3)
        self.assert_equal(plan.step_count, 3)
        self.assert_true(plan.truncated)
        self.assert_equal([step.order for step in plan.steps], [1, 2, 3])

    def _test_default_provider_invalid_max_steps_raises(self) -> None:
        provider = DefaultPlanningProvider()
        try:
            provider.plan("search", max_steps=0)
        except PlanningProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Expected PlanningProviderError for max_steps=0")

    def _test_default_provider_status_and_health(self) -> None:
        provider = DefaultPlanningProvider()
        self.assert_equal(provider.status(), PlanningProviderStatus.AVAILABLE)
        self.assert_true(provider.is_available())
        health = provider.health()
        self.assert_true(health.available)

    # ---------- PlanningManager ----------

    def _test_manager_registers_default_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            providers = manager.list_providers()
            self.assert_equal(len(providers), 1)
            self.assert_equal(providers[0].provider_name(), "planning")
            self.assert_equal(manager.current_provider_name(), "planning")

    def _test_manager_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            self.assert_equal(manager.max_steps(), 10)
            self.assert_true(manager.is_enabled())

    def _test_manager_invalid_enabled_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_ENABLED_PLANNING_YAML)
            except PlanningConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanningConfigurationError")

    def _test_manager_invalid_max_steps_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_MAX_STEPS_PLANNING_YAML)
            except PlanningConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanningConfigurationError")

    def _test_manager_invalid_default_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_PROVIDER_PLANNING_YAML)
            except PlanningConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanningConfigurationError")

    def _test_manager_duplicate_registration_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.register_provider(DefaultPlanningProvider())
            except PlanningProviderRegistryError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanningProviderRegistryError")

    def _test_manager_unknown_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.get_provider("does-not-exist")
            except PlanningProviderNotFoundError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanningProviderNotFoundError")

            try:
                manager.set_current("does-not-exist")
            except PlanningProviderNotFoundError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanningProviderNotFoundError")

    def _test_manager_set_current_switches_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            recorder = _RecordingPlanningProvider("recorder")
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
            manager = self._build_manager(Path(tmp), _DISABLED_PLANNING_YAML)
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.current_provider_name() is None)

    def _test_manager_set_max_steps_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.set_max_steps(3)
            self.assert_equal(manager.max_steps(), 3)

            try:
                manager.set_max_steps(0)
            except PlanningConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected PlanningConfigurationError")

    # ---------- PlanningEngine ----------

    def _test_engine_empty_request_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            try:
                engine.plan("   ")
            except EmptyPlanningRequestError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected EmptyPlanningRequestError")

    def _test_engine_no_provider_selected_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            engine._manager.disable()  # noqa: SLF001
            try:
                engine.plan("search for something")
            except NoPlanningProviderSelectedError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected NoPlanningProviderSelectedError")

    def _test_engine_plan_without_agent_engine_all_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp), with_agent=False)
            plan = engine.plan("search the knowledge base")
            self.assert_true(all(step.available for step in plan.steps))

    def _test_engine_plan_with_agent_engine_reconciles_availability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp), with_agent=True)
            engine._agent_engine.register_subsystem("knowledge", status_check=lambda: True)  # noqa: SLF001
            engine._agent_engine.register_subsystem("semantic", status_check=lambda: False)  # noqa: SLF001

            plan = engine.plan("search the knowledge base")
            by_subsystem = {step.subsystem: step.available for step in plan.steps}
            self.assert_true(by_subsystem["knowledge"])
            self.assert_false(by_subsystem["semantic"])

    def _test_engine_plan_with_agent_engine_unregistered_subsystem_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp), with_agent=True)
            # No subsystems registered with the agent at all.
            plan = engine.plan("compress the context")
            self.assert_equal(plan.step_count, 1)
            self.assert_false(plan.steps[0].available)

    def _test_engine_fallback_step_always_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp), with_agent=True)
            plan = engine.plan("good morning")
            self.assert_equal(plan.step_count, 1)
            self.assert_true(plan.steps[0].subsystem is None)
            self.assert_true(plan.steps[0].available)

    # ---------- PlanningService ----------

    def _test_service_status_and_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            status = service.status()
            self.assert_true(status.enabled)
            self.assert_equal(status.current_provider, "planning")
            self.assert_equal(status.registered_provider_count, 1)
            self.assert_equal(status.max_steps, 10)

            providers = service.list_providers()
            self.assert_equal(len(providers), 1)
            self.assert_equal(providers[0].name, "planning")
            self.assert_true(providers[0].is_current)

    def _test_service_use_unknown_provider_fails_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            outcome = service.use_provider("does-not-exist")
            self.assert_false(outcome.success)

    def _test_service_plan_success_and_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            outcome = service.plan("search the knowledge base")
            self.assert_true(outcome.success)
            self.assert_true(outcome.plan is not None)
            self.assert_equal(outcome.plan.step_count, 2)

            failure = service.plan("   ")
            self.assert_false(failure.success)
            self.assert_true(failure.error != "")

    def _test_service_limits_get_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            limits = service.limits()
            self.assert_equal(limits.max_steps, 10)

            result = service.set_max_steps(4)
            self.assert_true(result.success)
            self.assert_equal(service.limits().max_steps, 4)

            bad = service.set_max_steps(-1)
            self.assert_false(bad.success)

    def _test_service_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.disable()
            self.assert_true(result.success)
            self.assert_false(service.status().enabled)

    # ---------- PlanningModule (CLI) ----------

    def _test_cli_help_lists_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanningModule(service)
            self.assert_equal(module.name, "planning")
            result = module.execute("help", [])
            self.assert_true(result.success)
            for command in ("status", "providers", "use", "plan", "limits"):
                self.assert_true(command in result.message)

    def _test_cli_status_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanningModule(service)
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Enabled" in result.message)

    def _test_cli_providers_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanningModule(service)
            result = module.execute("providers", [])
            self.assert_true(result.success)
            self.assert_true("planning" in result.message)

    def _test_cli_use_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanningModule(service)
            self.assert_false(module.execute("use", []).success)
            self.assert_false(module.execute("use", ["nope"]).success)
            self.assert_true(module.execute("use", ["planning"]).success)

    def _test_cli_plan_command_usage_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanningModule(service)
            self.assert_false(module.execute("plan", []).success)
            result = module.execute("plan", ["search", "the", "knowledge", "base"])
            self.assert_true(result.success)
            self.assert_true("Steps" in result.message)

    def _test_cli_limits_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanningModule(service)
            result = module.execute("limits", [])
            self.assert_true(result.success)
            self.assert_true("Max steps" in result.message)

    def _test_cli_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = PlanningModule(service)
            result = module.execute("bogus", [])
            self.assert_false(result.success)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_planning_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                service = bootstrap.planning_service
                self.assert_true(service is not None)
                status = service.status()
                self.assert_true(status.enabled)
                self.assert_equal(status.current_provider, "planning")

                result = bootstrap._command_router.dispatch("planning status")  # noqa: SLF001
                self.assert_true(result.success)

    def _test_bootstrap_degrades_gracefully_on_invalid_planning_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, planning_default_provider="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()  # must not raise -- Planning Engine degrades, Jarvis still starts
                self.assert_true(bootstrap.planning_service is None)
                # The rest of the application is unaffected.
                self.assert_true(bootstrap.knowledge_service is not None)
                self.assert_true(bootstrap.agent_service is not None)

    def _test_bootstrap_planning_independent_of_agent_availability(self) -> None:
        """Planning Engine must not require the Agent Framework to be available."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config_dir = directory / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            # Reuse the full bootstrap config, then invalidate the agent
            # section (which disables the Agent Framework per EP-028's
            # own graceful-degradation wiring).
            full_config = _FULL_BOOTSTRAP_CONFIG_YAML.format(
                planning_default_provider="planning", max_steps=10
            ).replace('default_agent: "jarvis"', 'default_agent: ""')
            (config_dir / "config.yaml").write_text(full_config, encoding="utf-8")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.agent_service is None)
                self.assert_true(bootstrap.planning_service is not None)
                self.assert_true(bootstrap.planning_service.status().enabled)
                result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    "planning plan search the knowledge base"
                )
                self.assert_true(result.success)

    def _test_bootstrap_reconciles_against_live_subsystem_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()

                result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    "planning plan search the knowledge base and compress it"
                )
                self.assert_true(result.success)
                # Every referenced subsystem (knowledge, semantic,
                # compression) was auto-registered by EP-028's bootstrap
                # wiring and reports itself enabled, so every step
                # should be reconciled as available.
                self.assert_true("unavailable" not in result.message)

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """EP-029 must not import an AI provider, Prompt Engine, Reasoning/Reflection/Execution Engine, or Tool Executor."""
        forbidden_fragments = (
            "src.core.rag",
            "src.core.ai",
            "src.core.reasoning",
            "src.core.reflection",
            "src.core.execution",
            "src.core.prompt",
            "src.core.conversation",
            "browser_automation",
            "tool_executor",
            "openai",
            "anthropic",
            "gemini",
            "ollama",
        )
        for module in (planning_engine_module, planning_manager_module, planning_provider_module):
            source = inspect.getsource(module)
            for fragment in forbidden_fragments:
                self.assert_true(
                    fragment not in source, f"{module.__name__} must not reference '{fragment}'"
                )

    def _test_manager_owns_no_storage_state(self) -> None:
        """PlanningManager owns provider registration only, never plan/task storage."""
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            instance_attrs = vars(manager)
            forbidden_attr_names = ("_records", "_collection", "_store", "_documents", "_index", "_plans")
            for attr_name in instance_attrs:
                for forbidden in forbidden_attr_names:
                    self.assert_true(
                        forbidden not in attr_name.lower(),
                        f"PlanningManager should not own storage state ('{attr_name}')",
                    )

    def _test_exception_hierarchy(self) -> None:
        """PlanningProviderError and PlanningEngineError are both catchable through the shared root."""
        self.assert_true(issubclass(PlanningProviderError, PlanningError))
        self.assert_true(issubclass(PlanningEngineError, PlanningError))
        try:
            raise PlanningProviderError("boom")
        except PlanningError:
            self.result.add_pass()
        else:
            self.assert_true(False, "PlanningProviderError should be catchable as PlanningError")

    def _test_no_future_ep_components_implemented(self) -> None:
        """Only PlanningProvider/DefaultPlanningProvider exist -- no Reasoning/Reflection/Execution engines."""
        forbidden_class_names = (
            "ReasoningEngine",
            "ReflectionEngine",
            "ExecutionEngine",
            "ToolExecutor",
            "WorkflowEngine",
        )
        combined_source = "\n".join(
            inspect.getsource(module)
            for module in (planning_engine_module, planning_manager_module, planning_provider_module)
        )
        for class_name in forbidden_class_names:
            self.assert_true(
                f"class {class_name}" not in combined_source,
                f"{class_name} must not be implemented in EP-029",
            )

    def _test_no_private_api_access_on_foreign_objects(self) -> None:
        """PlanningEngine reaches the Agent Framework only through public methods/fields.

        Scans `planning_engine.py`'s source for any attribute access
        beginning with an underscore on the injected collaborator
        (`agent_engine`) or on a `SubsystemInfo` (`info`) -- only
        `self._*` (this class's own attributes) is permitted.
        """
        source = inspect.getsource(planning_engine_module)
        forbidden_accesses = ("agent_engine._", "info._")
        for forbidden in forbidden_accesses:
            self.assert_true(
                forbidden not in source,
                f"PlanningEngine must not access a private attribute via '{forbidden}'",
            )
