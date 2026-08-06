"""Real engineering tests for EP-032 - Multi-Agent Collaboration.

Builds real `AgentOutcomeStatus`/`AgentOutcome`/`CollaborationResult`/
`CollaborationProvider`/`DefaultCollaborationProvider`/
`CollaborationManager`/`CollaborationEngine`/`CollaborationService`/
`CollaborationModule` instances -- composed, where needed, with a real
EP-028 `AgentManager`/`AgentProvider` -- and drives them exactly as a
caller would, no mocked internals, matching every other EP's test
suite in this project (see tests/EP031/test_tool_engine.py).

Multi-Agent Collaboration (EP-032) is a new, independent package
(`src/core/collaboration/`) that implements the Multi-Agent Coordinator
explicitly deferred by EP-028 through EP-030's own docstrings --
deterministic broadcast of a request across every agent currently
registered with EP-028's Agent Framework, with each agent's own
outcome collected and reported. This suite covers:

1. The domain model: `AgentOutcomeStatus`, `AgentOutcome`,
   `CollaborationResult`.
2. The provider abstraction: `CollaborationProvider` (abstract
   contract), `DefaultCollaborationProvider` (built-in, deterministic
   broadcast provider) -- READY agent success, READY agent failure,
   non-READY agent skipped, a misbehaving agent isolated from others.
3. `CollaborationManager`: configuration validation, registration,
   enable/disable, active-provider switching, status.
4. `CollaborationEngine`: the agent-catalog -> broadcast-dispatch
   pipeline -- empty request, no agents registered at all, no provider
   selected, a real multi-agent scenario.
5. `CollaborationService`/`CollaborationModule`: configuration-driven
   construction and every CLI command ("status", "providers",
   "agents", "use", "run", "help").
6. Bootstrap wiring: real construction from the same `AgentManager`
   built for EP-028, graceful degradation on invalid
   'collaboration.*' configuration, and skipping entirely when the
   Agent Framework itself is unavailable.
7. Backward compatibility: EP-028 through EP-031's own behavior is
   provably unaffected by EP-032 being wired in.
8. Architecture compliance: no forbidden imports, no private-API
   access into `AgentManager`/`AgentProvider`, no duplicated
   provider/manager logic, correct exception hierarchy.
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.agent.agent_manager import AgentManager
from src.core.agent.agent_provider import AgentFrameworkError, AgentProvider
from src.core.agent.agent_result import AgentCancelResult, AgentExecutionResult, SubsystemInfo
from src.core.agent.agent_state import AgentState
from src.core.collaboration import collaboration_engine as collaboration_engine_module
from src.core.collaboration import collaboration_manager as collaboration_manager_module
from src.core.collaboration import collaboration_provider as collaboration_provider_module
from src.core.collaboration.collaboration_engine import (
    CollaborationEngine,
    CollaborationEngineError,
    EmptyCollaborationRequestError,
    NoAgentsAvailableError,
    NoCollaborationProviderSelectedError,
)
from src.core.collaboration.collaboration_manager import (
    CollaborationManager,
    CollaborationProviderNotFoundError,
    CollaborationProviderRegistryError,
)
from src.core.collaboration.collaboration_provider import (
    CollaborationConfigurationError,
    CollaborationError,
    CollaborationProvider,
    DefaultCollaborationProvider,
)
from src.core.collaboration.collaboration_result import (
    AgentOutcome,
    AgentOutcomeStatus,
    CollaborationResult,
)
from src.core.config import Config
from src.modules.collaboration_module import CollaborationModule
from src.services.collaboration_service import CollaborationService
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


_DEFAULT_COLLABORATION_YAML = (
    "collaboration:\n  enabled: true\n  default_provider: \"collaboration\"\n"
)

_DISABLED_COLLABORATION_YAML = (
    "collaboration:\n  enabled: false\n  default_provider: \"collaboration\"\n"
)

_INVALID_PROVIDER_COLLABORATION_YAML = (
    "collaboration:\n  enabled: true\n  default_provider: \"\"\n"
)

_INVALID_ENABLED_COLLABORATION_YAML = (
    "collaboration:\n  enabled: \"yes\"\n  default_provider: \"collaboration\"\n"
)

_UNKNOWN_PROVIDER_COLLABORATION_YAML = (
    "collaboration:\n  enabled: true\n  default_provider: \"does-not-exist\"\n"
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
# tests/EP031/test_tool_engine.py's own copy, plus the new 'collaboration:' section
# EP-032 introduces.
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
    "  enabled: {agent_enabled}\n"
    "  default_agent: \"jarvis\"\n"
    "  startup_mode: \"{agent_startup_mode}\"\n\n"
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
    "  enabled: {collaboration_enabled}\n"
    "  default_provider: \"{collaboration_default_provider}\"\n"
)


def _write_full_bootstrap_config(
    directory: Path,
    agent_enabled: bool = True,
    agent_startup_mode: str = "auto",
    collaboration_enabled: bool = True,
    collaboration_default_provider: str = "collaboration",
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`.

    `agent_startup_mode` defaults to "auto" (not the project-wide
    default "idle") so a real end-to-end Bootstrap run has at least
    one READY agent to actually broadcast to, without every test
    needing to separately call 'agent initialize'.
    """
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            agent_enabled=str(agent_enabled).lower(),
            agent_startup_mode=agent_startup_mode,
            collaboration_enabled=str(collaboration_enabled).lower(),
            collaboration_default_provider=collaboration_default_provider,
        ),
        encoding="utf-8",
    )


_AGENT_ONLY_YAML = (
    "agent:\n  enabled: true\n  default_agent: \"jarvis\"\n  startup_mode: \"auto\"\n"
)


class _RecordingAgentProvider(AgentProvider):
    """A minimal, independent AgentProvider used only to test multi-agent scenarios.

    Entirely separate from `DefaultAgentProvider`, so tests can prove
    `CollaborationEngine`/`DefaultCollaborationProvider` truly iterate
    every registered agent rather than only the built-in one.
    """

    def __init__(self, name: str, initial_state: AgentState = AgentState.READY) -> None:
        self._name = name
        self._state = initial_state

    def agent_name(self) -> str:
        return self._name

    def initialize(self) -> None:
        self._state = AgentState.READY

    def shutdown(self) -> None:
        self._state = AgentState.SHUTDOWN

    def reset(self) -> None:
        pass

    def status(self) -> AgentState:
        return self._state

    def execute(self, request: str, metadata=None) -> AgentExecutionResult:
        return AgentExecutionResult(
            request_id=f"{self._name}-1",
            success=True,
            dispatched=False,
            state=self._state,
            message=f"{self._name} acknowledged: {request}",
        )

    def cancel(self, request_id: str) -> AgentCancelResult:
        return AgentCancelResult(request_id=request_id, success=False, message="n/a")

    def register_subsystem(self, name, status_check=None) -> None:
        pass

    def unregister_subsystem(self, name) -> None:
        pass

    def list_subsystems(self) -> list[SubsystemInfo]:
        return []


class _FailingExecuteAgentProvider(_RecordingAgentProvider):
    """A READY agent whose `execute()` reports a rejected request."""

    def execute(self, request: str, metadata=None) -> AgentExecutionResult:
        return AgentExecutionResult(
            request_id=f"{self._name}-1",
            success=False,
            dispatched=False,
            state=self._state,
            message=f"{self._name} rejected the request.",
        )


class _RaisingAgentProvider(_RecordingAgentProvider):
    """A READY agent whose `execute()` raises -- must not break the other agents."""

    def execute(self, request: str, metadata=None) -> AgentExecutionResult:
        raise AgentFrameworkError(f"{self._name} exploded")


@TestRegistry.register
class CollaborationEngineTest(BaseTest):
    NAME = "EP032"

    def run(self):
        # ---------- Domain model ----------
        self._test_agent_outcome_status_values()
        self._test_agent_outcome_and_result_construction()
        self._test_collaboration_result_summary()

        # ---------- CollaborationProvider / DefaultCollaborationProvider ----------
        self._test_provider_is_abstract()
        self._test_default_provider_name()
        self._test_default_provider_broadcasts_to_ready_agents()
        self._test_default_provider_skips_non_ready_agents()
        self._test_default_provider_reports_failed_execute()
        self._test_default_provider_isolates_raising_agent()
        self._test_default_provider_deterministic_ordering()
        self._test_default_provider_status()

        # ---------- CollaborationManager ----------
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
        self._test_manager_owns_no_agent_catalog()

        # ---------- CollaborationEngine ----------
        self._test_engine_empty_request_raises()
        self._test_engine_no_agents_registered_raises()
        self._test_engine_no_provider_selected_raises()
        self._test_engine_list_agents()
        self._test_engine_single_agent_end_to_end()
        self._test_engine_multi_agent_end_to_end()
        self._test_engine_all_unavailable_reports_unsuccessful()

        # ---------- CollaborationService ----------
        self._test_service_status_and_providers()
        self._test_service_list_agents()
        self._test_service_use_unknown_provider_fails_gracefully()
        self._test_service_run_success_and_failure()
        self._test_service_disable()

        # ---------- CollaborationModule (CLI) ----------
        self._test_cli_help_lists_commands()
        self._test_cli_status_command()
        self._test_cli_providers_command()
        self._test_cli_agents_command()
        self._test_cli_use_command()
        self._test_cli_run_command_usage_and_results()
        self._test_cli_unknown_action()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_registers_collaboration_module()
        self._test_bootstrap_degrades_gracefully_on_invalid_collaboration_config()
        self._test_bootstrap_disabled_collaboration_still_boots()
        self._test_bootstrap_still_available_when_agent_framework_disabled()
        self._test_bootstrap_full_pipeline_via_collaborate_cli()

        # ---------- Backward compatibility ----------
        self._test_bootstrap_agent_service_unaffected()
        self._test_bootstrap_tool_service_unaffected()

        # ---------- Architectural acceptance criteria ----------
        self._test_no_forbidden_imports()
        self._test_no_ai_or_planning_imports_in_core_collaboration_files()
        self._test_manager_owns_no_plan_or_step_storage()
        self._test_exception_hierarchy()
        self._test_no_private_api_access_on_foreign_objects()

        return self.result

    # ---------- Helpers ----------

    def _build_manager(
        self, tmp_path: Path, yaml_text: str = _DEFAULT_COLLABORATION_YAML
    ) -> CollaborationManager:
        config = _write_config(tmp_path, yaml_text)
        return CollaborationManager(config=config)

    def _build_agent_manager(self, tmp_path: Path) -> AgentManager:
        config = _write_config(tmp_path, _AGENT_ONLY_YAML)
        manager = AgentManager(config=config)
        current = manager.get_current()
        if current is not None:
            current.initialize()
        return manager

    def _build_engine(
        self,
        tmp_path: Path,
        yaml_text: str = _DEFAULT_COLLABORATION_YAML,
        agent_manager: AgentManager | None = None,
    ) -> CollaborationEngine:
        manager = self._build_manager(tmp_path, yaml_text)
        if agent_manager is None:
            agent_manager = self._build_agent_manager(tmp_path)
        return CollaborationEngine(manager=manager, agent_manager=agent_manager)

    def _build_service(self, tmp_path: Path) -> CollaborationService:
        engine = self._build_engine(tmp_path)
        return CollaborationService(manager=engine._manager, engine=engine)  # noqa: SLF001

    # ---------- Domain model ----------

    def _test_agent_outcome_status_values(self) -> None:
        self.assert_equal(AgentOutcomeStatus.SUCCEEDED.value, "SUCCEEDED")
        self.assert_equal(AgentOutcomeStatus.FAILED.value, "FAILED")
        self.assert_equal(AgentOutcomeStatus.UNAVAILABLE.value, "UNAVAILABLE")

    def _test_agent_outcome_and_result_construction(self) -> None:
        outcome = AgentOutcome(
            agent_name="jarvis", status=AgentOutcomeStatus.SUCCEEDED, message="ok", request_id="r-1"
        )
        self.assert_equal(outcome.agent_name, "jarvis")
        self.assert_equal(outcome.status, AgentOutcomeStatus.SUCCEEDED)
        self.assert_equal(outcome.request_id, "r-1")

        result = CollaborationResult(
            request="do something",
            outcomes=[outcome],
            participant_count=1,
            succeeded_count=1,
            failed_count=0,
            unavailable_count=0,
            success=True,
        )
        self.assert_equal(result.participant_count, 1)
        self.assert_true(result.success)

    def _test_collaboration_result_summary(self) -> None:
        outcome = AgentOutcome(
            agent_name="jarvis", status=AgentOutcomeStatus.SUCCEEDED, message="acknowledged"
        )
        result = CollaborationResult(request="x", outcomes=[outcome], participant_count=1)
        self.assert_equal(result.summary(), "jarvis - SUCCEEDED: acknowledged")
        self.assert_equal(CollaborationResult(request="x").summary(), "")

    # ---------- CollaborationProvider / DefaultCollaborationProvider ----------

    def _test_provider_is_abstract(self) -> None:
        try:
            CollaborationProvider()  # type: ignore[abstract]
            self.assert_true(False, "CollaborationProvider must be abstract")
        except TypeError:
            self.result.add_pass()

    def _test_default_provider_name(self) -> None:
        provider = DefaultCollaborationProvider()
        self.assert_equal(provider.provider_name(), "collaboration")

    def _test_default_provider_broadcasts_to_ready_agents(self) -> None:
        provider = DefaultCollaborationProvider()
        agent = _RecordingAgentProvider("alpha", AgentState.READY)
        result = provider.collaborate("hello", None, [agent])
        self.assert_equal(result.participant_count, 1)
        self.assert_equal(result.succeeded_count, 1)
        self.assert_equal(result.outcomes[0].status, AgentOutcomeStatus.SUCCEEDED)
        self.assert_equal(result.outcomes[0].request_id, "alpha-1")
        self.assert_true(result.success)

    def _test_default_provider_skips_non_ready_agents(self) -> None:
        provider = DefaultCollaborationProvider()
        agent = _RecordingAgentProvider("beta", AgentState.UNINITIALIZED)
        result = provider.collaborate("hello", None, [agent])
        self.assert_equal(result.unavailable_count, 1)
        self.assert_equal(result.outcomes[0].status, AgentOutcomeStatus.UNAVAILABLE)
        self.assert_equal(result.outcomes[0].request_id, None)
        self.assert_false(result.success)

    def _test_default_provider_reports_failed_execute(self) -> None:
        provider = DefaultCollaborationProvider()
        agent = _FailingExecuteAgentProvider("gamma", AgentState.READY)
        result = provider.collaborate("hello", None, [agent])
        self.assert_equal(result.failed_count, 1)
        self.assert_equal(result.outcomes[0].status, AgentOutcomeStatus.FAILED)
        self.assert_false(result.success)

    def _test_default_provider_isolates_raising_agent(self) -> None:
        provider = DefaultCollaborationProvider()
        good = _RecordingAgentProvider("delta", AgentState.READY)
        bad = _RaisingAgentProvider("epsilon", AgentState.READY)
        result = provider.collaborate("hello", None, [good, bad])
        self.assert_equal(result.participant_count, 2)
        statuses = {outcome.agent_name: outcome.status for outcome in result.outcomes}
        self.assert_equal(statuses["delta"], AgentOutcomeStatus.SUCCEEDED)
        self.assert_equal(statuses["epsilon"], AgentOutcomeStatus.FAILED)

    def _test_default_provider_deterministic_ordering(self) -> None:
        provider = DefaultCollaborationProvider()
        agents = [
            _RecordingAgentProvider("zeta", AgentState.READY),
            _RecordingAgentProvider("alpha", AgentState.READY),
            _RecordingAgentProvider("mu", AgentState.READY),
        ]
        result = provider.collaborate("hello", None, agents)
        names = [outcome.agent_name for outcome in result.outcomes]
        self.assert_equal(names, sorted(names))

    def _test_default_provider_status(self) -> None:
        provider = DefaultCollaborationProvider()
        self.assert_true(provider.is_available())

    # ---------- CollaborationManager ----------

    def _test_manager_registers_default_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            names = [provider.provider_name() for provider in manager.list_providers()]
            self.assert_true("collaboration" in names)

    def _test_manager_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            self.assert_true(manager.is_enabled())
            self.assert_equal(manager.current_provider_name(), "collaboration")

    def _test_manager_invalid_enabled_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _INVALID_ENABLED_COLLABORATION_YAML)
            try:
                CollaborationManager(config=config)
                self.assert_true(False, "Expected CollaborationConfigurationError")
            except CollaborationConfigurationError:
                self.result.add_pass()

    def _test_manager_invalid_default_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _INVALID_PROVIDER_COLLABORATION_YAML)
            try:
                CollaborationManager(config=config)
                self.assert_true(False, "Expected CollaborationConfigurationError")
            except CollaborationConfigurationError:
                self.result.add_pass()

    def _test_manager_unknown_configured_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _UNKNOWN_PROVIDER_COLLABORATION_YAML)
            try:
                CollaborationManager(config=config)
                self.assert_true(False, "Expected CollaborationConfigurationError")
            except CollaborationConfigurationError:
                self.result.add_pass()

    def _test_manager_duplicate_provider_registration_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.register_provider(DefaultCollaborationProvider())
                self.assert_true(False, "Expected CollaborationProviderRegistryError")
            except CollaborationProviderRegistryError:
                self.result.add_pass()

    def _test_manager_unknown_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.get_provider("does-not-exist")
                self.assert_true(False, "Expected CollaborationProviderNotFoundError")
            except CollaborationProviderNotFoundError:
                self.result.add_pass()

    def _test_manager_set_current_switches_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))

            class _OtherProvider(DefaultCollaborationProvider):
                def provider_name(self) -> str:
                    return "other"

            manager.register_provider(_OtherProvider())
            manager.set_current("other")
            self.assert_equal(manager.current_provider_name(), "other")

    def _test_manager_disable_clears_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.disable()
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.get_current() is None)
            self.assert_true(manager.current_provider_name() is None)

    def _test_manager_current_provider_name_none_when_disabled_via_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DISABLED_COLLABORATION_YAML)
            manager = CollaborationManager(config=config)
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.current_provider_name() is None)
            self.assert_true(manager.get_current() is None)

    def _test_manager_owns_no_agent_catalog(self) -> None:
        """CollaborationManager must never hold a reference to AgentManager or an agent catalog."""
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            for attr_name, attr_value in vars(manager).items():
                self.assert_true(
                    not isinstance(attr_value, AgentManager),
                    f"CollaborationManager must not hold an AgentManager reference ('{attr_name}')",
                )

    # ---------- CollaborationEngine ----------

    def _test_engine_empty_request_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            try:
                engine.collaborate("   ")
                self.assert_true(False, "Expected EmptyCollaborationRequestError")
            except EmptyCollaborationRequestError:
                self.result.add_pass()

    def _test_engine_no_agents_registered_raises(self) -> None:
        """AgentManager always registers "jarvis" at construction time, so a truly
        empty catalog is only reachable through a public-API-only test double
        whose `list_providers()` reports nothing -- this proves CollaborationEngine
        reads the catalog exclusively through that one public method (never a
        private attribute), while still exercising the empty-catalog error path.
        """
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = _write_config(directory, _AGENT_ONLY_YAML)

            class _EmptyAgentManager(AgentManager):
                def list_providers(self):  # noqa: D102 - test double
                    return []

            manager = self._build_manager(directory)
            engine = CollaborationEngine(manager=manager, agent_manager=_EmptyAgentManager(config=config))
            try:
                engine.collaborate("hello")
                self.assert_true(False, "Expected NoAgentsAvailableError")
            except NoAgentsAvailableError:
                self.result.add_pass()

    def _test_engine_no_provider_selected_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = _write_config(directory, _DISABLED_COLLABORATION_YAML)
            manager = CollaborationManager(config=config)
            agent_manager = self._build_agent_manager(directory)
            engine = CollaborationEngine(manager=manager, agent_manager=agent_manager)
            try:
                engine.collaborate("hello")
                self.assert_true(False, "Expected NoCollaborationProviderSelectedError")
            except NoCollaborationProviderSelectedError:
                self.result.add_pass()

    def _test_engine_list_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            self.assert_true("jarvis" in engine.list_agents())

    def _test_engine_single_agent_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            result = engine.collaborate("remember my preferences")
            self.assert_equal(result.participant_count, 1)
            self.assert_equal(result.succeeded_count, 1)
            self.assert_true(result.success)

    def _test_engine_multi_agent_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config = _write_config(directory, _AGENT_ONLY_YAML)
            agent_manager = AgentManager(config=config)
            agent_manager.get_current().initialize()  # "jarvis", READY
            agent_manager.register_provider(_RecordingAgentProvider("scout", AgentState.READY))
            agent_manager.register_provider(
                _RecordingAgentProvider("watcher", AgentState.UNINITIALIZED)
            )

            collaboration_config = _write_config(directory, _DEFAULT_COLLABORATION_YAML)
            collaboration_manager = CollaborationManager(config=collaboration_config)
            engine = CollaborationEngine(manager=collaboration_manager, agent_manager=agent_manager)

            result = engine.collaborate("survey the area")
            self.assert_equal(result.participant_count, 3)
            self.assert_equal(result.succeeded_count, 2)
            self.assert_equal(result.unavailable_count, 1)
            statuses = {outcome.agent_name: outcome.status for outcome in result.outcomes}
            self.assert_equal(statuses["jarvis"], AgentOutcomeStatus.SUCCEEDED)
            self.assert_equal(statuses["scout"], AgentOutcomeStatus.SUCCEEDED)
            self.assert_equal(statuses["watcher"], AgentOutcomeStatus.UNAVAILABLE)

    def _test_engine_all_unavailable_reports_unsuccessful(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            # startup_mode "idle" (the project-wide default) -> "jarvis" starts
            # UNINITIALIZED, never READY, without an explicit 'agent initialize'.
            idle_agent_yaml = (
                "agent:\n  enabled: true\n  default_agent: \"jarvis\"\n  startup_mode: \"idle\"\n"
            )
            config = _write_config(directory, idle_agent_yaml)
            agent_manager = AgentManager(config=config)
            collaboration_config = _write_config(directory, _DEFAULT_COLLABORATION_YAML)
            collaboration_manager = CollaborationManager(config=collaboration_config)
            engine = CollaborationEngine(manager=collaboration_manager, agent_manager=agent_manager)

            result = engine.collaborate("hello")
            self.assert_equal(result.unavailable_count, 1)
            self.assert_equal(result.succeeded_count, 0)
            self.assert_false(result.success)

    # ---------- CollaborationService ----------

    def _test_service_status_and_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            status = service.status()
            self.assert_true(status.enabled)
            self.assert_equal(status.current_provider, "collaboration")
            self.assert_equal(status.registered_provider_count, 1)
            self.assert_equal(status.registered_agent_count, 1)

            providers = service.list_providers()
            self.assert_equal(len(providers), 1)
            self.assert_true(providers[0].is_current)

    def _test_service_list_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            self.assert_true("jarvis" in service.list_agents())

    def _test_service_use_unknown_provider_fails_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.use_provider("does-not-exist")
            self.assert_false(result.success)

    def _test_service_run_success_and_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            outcome = service.run("remember my preferences")
            self.assert_true(outcome.success)
            self.assert_true(outcome.result is not None)

            service.disable()
            failed_outcome = service.run("remember my preferences")
            self.assert_false(failed_outcome.success)
            self.assert_true(failed_outcome.error != "")

    def _test_service_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.disable()
            self.assert_true(result.success)
            self.assert_false(service.status().enabled)

    # ---------- CollaborationModule (CLI) ----------

    def _test_cli_help_lists_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = CollaborationModule(self._build_service(Path(tmp)))
            result = module.execute("help", [])
            self.assert_true(result.success)
            self.assert_true("collaborate run" in result.message)

    def _test_cli_status_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = CollaborationModule(self._build_service(Path(tmp)))
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Multi-Agent Collaboration Status" in result.message)

    def _test_cli_providers_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = CollaborationModule(self._build_service(Path(tmp)))
            result = module.execute("providers", [])
            self.assert_true(result.success)
            self.assert_true("collaboration" in result.message)

    def _test_cli_agents_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = CollaborationModule(self._build_service(Path(tmp)))
            result = module.execute("agents", [])
            self.assert_true(result.success)
            self.assert_true("jarvis" in result.message)

    def _test_cli_use_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = CollaborationModule(self._build_service(Path(tmp)))
            usage = module.execute("use", [])
            self.assert_false(usage.success)

            result = module.execute("use", ["collaboration"])
            self.assert_true(result.success)

    def _test_cli_run_command_usage_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = CollaborationModule(self._build_service(Path(tmp)))
            usage = module.execute("run", [])
            self.assert_false(usage.success)

            result = module.execute("run", ["remember", "my", "preferences"])
            self.assert_true(result.success)
            self.assert_true("Collaboration Result" in result.message)
            self.assert_true("jarvis" in result.message)

    def _test_cli_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            module = CollaborationModule(self._build_service(Path(tmp)))
            result = module.execute("bogus", [])
            self.assert_false(result.success)
            self.assert_true("collaborate help" in result.message)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_collaboration_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.collaboration_service is not None)
                self.assert_true("collaborate" in bootstrap._command_router.module_names)  # noqa: SLF001

    def _test_bootstrap_degrades_gracefully_on_invalid_collaboration_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, collaboration_default_provider="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()  # must not raise -- Multi-Agent Collaboration degrades
                self.assert_true(bootstrap.collaboration_service is None)
                # The rest of the application is unaffected.
                self.assert_true(bootstrap.agent_service is not None)
                self.assert_true(bootstrap.tool_service is not None)

    def _test_bootstrap_disabled_collaboration_still_boots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, collaboration_enabled=False)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.collaboration_service is not None)
                self.assert_false(bootstrap.collaboration_service.status().enabled)

    def _test_bootstrap_still_available_when_agent_framework_disabled(self) -> None:
        """A disabled Agent Framework ('agent.enabled: false') still constructs a
        valid AgentManager with its catalog intact, so Multi-Agent Collaboration
        still wires up -- it just honestly reports every agent UNAVAILABLE.
        """
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, agent_enabled=False)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()  # must not raise
                self.assert_true(bootstrap.collaboration_service is not None)
                outcome = bootstrap.collaboration_service.run("remember my preferences")
                self.assert_true(outcome.success)
                self.assert_false(outcome.result.success)
                self.assert_true(outcome.result.unavailable_count >= 1)

    def _test_bootstrap_full_pipeline_via_collaborate_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    'collaborate run "remember my preferences"'
                )
                self.assert_true(result.success)
                self.assert_true("jarvis" in result.message)

    # ---------- Backward compatibility ----------

    def _test_bootstrap_agent_service_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                status = bootstrap.agent_service.status()
                self.assert_equal(status.current_agent, "jarvis")
                self.assert_equal(status.registered_agent_count, 1)

    def _test_bootstrap_tool_service_unaffected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                status = bootstrap.tool_service.status()
                self.assert_equal(status.current_provider, "tool_engine")

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """EP-032 must not import an AI provider, Prompt Engine, Planning, or a Planning provider."""
        forbidden_fragments = (
            "src.core.ai",
            "src.core.reasoning",
            "src.core.reflection",
            "src.core.prompt",
            "src.core.conversation",
            "src.core.planning",
            "src.core.plan_execution",
            "browser_automation",
            "openai",
            "anthropic",
            "gemini",
            "ollama",
        )
        for module in (
            collaboration_engine_module,
            collaboration_manager_module,
            collaboration_provider_module,
        ):
            source = inspect.getsource(module)
            for fragment in forbidden_fragments:
                self.assert_true(
                    fragment not in source, f"{module.__name__} must not reference '{fragment}'"
                )

    def _test_no_ai_or_planning_imports_in_core_collaboration_files(self) -> None:
        """collaboration_result.py must depend on nothing but stdlib."""
        module = __import__(
            "src.core.collaboration.collaboration_result", fromlist=["collaboration_result"]
        )
        source = inspect.getsource(module)
        self.assert_true("src.core.planning" not in source)
        self.assert_true("src.core.plan_execution" not in source)
        self.assert_true("src.core.tool" not in source)

    def _test_manager_owns_no_plan_or_step_storage(self) -> None:
        """CollaborationManager owns provider registration only, never plan/step storage."""
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            instance_attrs = vars(manager)
            forbidden_attr_names = ("_plans", "_steps", "_records", "_collection", "_documents", "_index")
            for attr_name in instance_attrs:
                for forbidden in forbidden_attr_names:
                    self.assert_true(
                        forbidden not in attr_name.lower(),
                        f"CollaborationManager should not own plan/step storage ('{attr_name}')",
                    )

    def _test_exception_hierarchy(self) -> None:
        """CollaborationEngineError is catchable through the shared CollaborationError root."""
        self.assert_true(issubclass(CollaborationEngineError, CollaborationError))
        try:
            raise CollaborationEngineError("boom")
        except CollaborationError:
            self.result.add_pass()
        else:
            self.assert_true(False, "CollaborationEngineError should be catchable as CollaborationError")

    def _test_no_private_api_access_on_foreign_objects(self) -> None:
        """CollaborationEngine reaches AgentManager/CollaborationManager only through public methods."""
        source = inspect.getsource(collaboration_engine_module)
        cleaned = source.replace("self._manager", "").replace("self._agent_manager", "")
        self.assert_true(
            "manager._" not in cleaned,
            "CollaborationEngine must not access a private attribute of AgentManager/CollaborationManager",
        )
