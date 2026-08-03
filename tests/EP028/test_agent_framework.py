"""Real engineering tests for EP-028 - Agent Framework.

Builds real `AgentState`/`SubsystemInfo`/`AgentExecutionResult`/
`AgentCancelResult`/`AgentProvider`/`DefaultAgentProvider`/
`AgentManager`/`AgentEngine`/`AgentService`/`AgentModule` instances and
drives them exactly as a caller would, no mocked internals, matching
every other EP's test suite in this project (see
tests/EP027/test_context_compression.py).

The Agent Framework (EP-028) is a new, independent package
(`src/core/agent/`) that orchestrates already-implemented Engineering
Packages -- lifecycle management, a subsystem registry, and request
acknowledgment only. It performs no planning, reasoning, tool
execution, or AI provider call. This suite covers:

1. The domain model: `AgentState`, `SubsystemInfo`,
   `AgentExecutionResult`, `AgentCancelResult`.
2. The provider abstraction: `AgentProvider` (abstract contract),
   `DefaultAgentProvider` (built-in "jarvis" agent) -- lifecycle
   transitions (initialize/shutdown/reset), request
   acknowledgment/cancellation, and subsystem registration.
3. `AgentManager`: configuration validation, registration,
   enable/disable, active-agent selection, status, and the resolved
   'agent.startup_mode'.
4. `AgentEngine`: the lifecycle/subsystem-registry/request forwarding
   pipeline, including "auto" startup-mode initialization.
5. `AgentService`/`AgentModule`: configuration-driven construction,
   graceful degradation, and every CLI command ("status",
   "subsystems", "register", "unregister", "reset", "initialize",
   "shutdown", "help").
6. Architecture compliance: no forbidden imports, no duplicated
   provider/manager/storage logic, no future-EP functionality, no
   private-API access into any subsystem, and a real `Bootstrap` run
   proving normal wiring, dependency injection, subsystem
   auto-registration, and graceful degradation on invalid
   configuration.
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.agent import agent_engine as agent_engine_module
from src.core.agent import agent_manager as agent_manager_module
from src.core.agent import agent_provider as agent_provider_module
from src.core.agent.agent_engine import AgentEngine, AgentEngineError, EmptyRequestError, NoAgentSelectedError
from src.core.agent.agent_manager import (
    AgentManager,
    AgentProviderNotFoundError,
    AgentProviderRegistryError,
)
from src.core.agent.agent_provider import (
    AgentConfigurationError,
    AgentFrameworkError,
    AgentNotInitializedError,
    AgentProvider,
    AgentProviderError,
    AgentRequestNotFoundError,
    DefaultAgentProvider,
    SubsystemAlreadyRegisteredError,
    SubsystemNotFoundError,
)
from src.core.agent.agent_result import AgentCancelResult, AgentExecutionResult, SubsystemInfo
from src.core.agent.agent_state import AgentState
from src.core.config import Config
from src.modules.agent_module import AgentModule
from src.services.agent_service import AgentService
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


_DEFAULT_AGENT_YAML = (
    "agent:\n"
    "  enabled: true\n"
    "  default_agent: \"jarvis\"\n"
    "  startup_mode: \"idle\"\n"
)

_AUTO_STARTUP_AGENT_YAML = (
    "agent:\n"
    "  enabled: true\n"
    "  default_agent: \"jarvis\"\n"
    "  startup_mode: \"auto\"\n"
)

_DISABLED_AGENT_YAML = (
    "agent:\n"
    "  enabled: false\n"
    "  default_agent: \"jarvis\"\n"
    "  startup_mode: \"idle\"\n"
)

_INVALID_AGENT_YAML = (
    "agent:\n"
    "  enabled: true\n"
    "  default_agent: \"\"\n"
    "  startup_mode: \"idle\"\n"
)

_INVALID_STARTUP_MODE_YAML = (
    "agent:\n"
    "  enabled: true\n"
    "  default_agent: \"jarvis\"\n"
    "  startup_mode: \"eager\"\n"
)

_INVALID_ENABLED_YAML = (
    "agent:\n"
    "  enabled: \"yes\"\n"
    "  default_agent: \"jarvis\"\n"
    "  startup_mode: \"idle\"\n"
)

# Full, offline-safe config.yaml covering every section Bootstrap._build_command_router
# reads, so a real Bootstrap.run() can be exercised end to end in a temporary
# project root without any network access or long-lived background threads.
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
    "  default_agent: \"{agent_default_agent}\"\n"
    "  startup_mode: \"{agent_startup_mode}\"\n"
)


def _write_config(directory: Path, sections: str) -> Config:
    """Write `sections` to a temporary config.yaml and load it as a `Config`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(sections, encoding="utf-8")
    return Config(config_path).load()


def _write_full_bootstrap_config(
    directory: Path,
    agent_default_agent: str = "jarvis",
    agent_startup_mode: str = "idle",
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            agent_default_agent=agent_default_agent, agent_startup_mode=agent_startup_mode
        ),
        encoding="utf-8",
    )


class _RecordingAgentProvider(AgentProvider):
    """A minimal, independent AgentProvider used only to test AgentManager.

    Entirely separate from `DefaultAgentProvider`, so tests can prove
    `AgentManager` truly delegates to whichever agent is active rather
    than always using the built-in one.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._state = AgentState.UNINITIALIZED

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
            request_id="rec-1", success=True, dispatched=False, state=self._state, message="recorded"
        )

    def cancel(self, request_id: str) -> AgentCancelResult:
        return AgentCancelResult(request_id=request_id, success=False, message="n/a")

    def register_subsystem(self, name, status_check=None) -> None:
        pass

    def unregister_subsystem(self, name) -> None:
        pass

    def list_subsystems(self) -> list[SubsystemInfo]:
        return []


@TestRegistry.register
class AgentFrameworkTest(BaseTest):
    NAME = "EP028"

    def run(self):
        # ---------- Domain model ----------
        self._test_agent_state_values()
        self._test_result_dataclasses()

        # ---------- AgentProvider / DefaultAgentProvider ----------
        self._test_provider_is_abstract()
        self._test_default_provider_name_and_initial_state()
        self._test_default_provider_initialize_is_idempotent()
        self._test_default_provider_shutdown_and_reinitialize()
        self._test_default_provider_execute_requires_ready()
        self._test_default_provider_execute_returns_result()
        self._test_default_provider_execute_after_shutdown_raises()
        self._test_default_provider_cancel_known_and_unknown()
        self._test_default_provider_reset_clears_state()
        self._test_default_provider_reset_does_not_initialize_or_resurrect()
        self._test_default_provider_subsystem_registration()
        self._test_default_provider_subsystem_double_registration_raises()
        self._test_default_provider_unregister_unknown_raises()
        self._test_default_provider_subsystem_status_check_failure_reported_unavailable()

        # ---------- AgentManager ----------
        self._test_manager_registers_default_agent()
        self._test_manager_config_defaults()
        self._test_manager_invalid_enabled_raises()
        self._test_manager_invalid_default_agent_raises()
        self._test_manager_invalid_startup_mode_raises()
        self._test_manager_auto_startup_mode_accepted()
        self._test_manager_duplicate_registration_raises()
        self._test_manager_unknown_agent_raises()
        self._test_manager_set_current_switches_agent()
        self._test_manager_disable_clears_current()
        self._test_manager_current_provider_name_none_when_disabled_via_config()

        # ---------- AgentEngine ----------
        self._test_engine_no_agent_selected_raises()
        self._test_engine_forwards_lifecycle_calls()
        self._test_engine_empty_request_raises()
        self._test_engine_execute_and_cancel()
        self._test_engine_subsystem_registry_forwarding()
        self._test_engine_auto_startup_mode_initializes()
        self._test_engine_idle_startup_mode_leaves_uninitialized()

        # ---------- AgentService ----------
        self._test_service_status_reports_uninitialized()
        self._test_service_status_reports_state_after_initialize()
        self._test_service_register_and_list_subsystems()
        self._test_service_unregister_subsystem()
        self._test_service_initialize_shutdown_reset()
        self._test_service_disable()
        self._test_service_execute_and_cancel_passthrough()

        # ---------- AgentModule (CLI) ----------
        self._test_cli_help_lists_commands()
        self._test_cli_status_command()
        self._test_cli_subsystems_command()
        self._test_cli_register_command()
        self._test_cli_unregister_command()
        self._test_cli_initialize_shutdown_reset_commands()
        self._test_cli_unknown_action()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_registers_agent_module()
        self._test_bootstrap_degrades_gracefully_on_invalid_agent_config()
        self._test_bootstrap_auto_registers_available_subsystems()
        self._test_bootstrap_auto_startup_mode_initializes_agent()

        # ---------- Architectural acceptance criteria ----------
        self._test_no_forbidden_imports()
        self._test_manager_owns_no_storage_state()
        self._test_exception_hierarchy()
        self._test_no_future_ep_components_implemented()
        self._test_no_private_api_access_in_bootstrap_wiring()

        return self.result

    # ---------- Helpers ----------

    def _build_manager(self, tmp_path: Path, yaml_text: str = _DEFAULT_AGENT_YAML) -> AgentManager:
        config = _write_config(tmp_path, yaml_text)
        return AgentManager(config=config)

    def _build_engine(self, tmp_path: Path, yaml_text: str = _DEFAULT_AGENT_YAML) -> AgentEngine:
        manager = self._build_manager(tmp_path, yaml_text)
        return AgentEngine(manager=manager)

    def _build_service(self, tmp_path: Path, yaml_text: str = _DEFAULT_AGENT_YAML) -> AgentService:
        engine = self._build_engine(tmp_path, yaml_text)
        return AgentService(manager=engine._manager, engine=engine)  # noqa: SLF001

    # ---------- Domain model ----------

    def _test_agent_state_values(self) -> None:
        self.assert_equal(AgentState.UNINITIALIZED.value, "UNINITIALIZED")
        self.assert_equal(AgentState.READY.value, "READY")
        self.assert_equal(AgentState.RUNNING.value, "RUNNING")
        self.assert_equal(AgentState.SHUTDOWN.value, "SHUTDOWN")
        self.assert_equal(AgentState.ERROR.value, "ERROR")

    def _test_result_dataclasses(self) -> None:
        info = SubsystemInfo(name="knowledge", available=True)
        self.assert_equal(info.name, "knowledge")
        self.assert_true(info.available)

        execution = AgentExecutionResult(
            request_id="req-1", success=True, dispatched=False, state=AgentState.READY, message="ok"
        )
        self.assert_equal(execution.request_id, "req-1")
        self.assert_false(execution.dispatched)

        cancel = AgentCancelResult(request_id="req-1", success=False, message="nothing")
        self.assert_false(cancel.success)

    # ---------- AgentProvider / DefaultAgentProvider ----------

    def _test_provider_is_abstract(self) -> None:
        try:
            AgentProvider()  # type: ignore[abstract]
        except TypeError:
            self.result.add_pass()
        else:
            self.assert_true(False, "AgentProvider must be abstract")

    def _test_default_provider_name_and_initial_state(self) -> None:
        provider = DefaultAgentProvider()
        self.assert_equal(provider.agent_name(), "jarvis")
        self.assert_equal(provider.status(), AgentState.UNINITIALIZED)

    def _test_default_provider_initialize_is_idempotent(self) -> None:
        provider = DefaultAgentProvider()
        provider.initialize()
        self.assert_equal(provider.status(), AgentState.READY)
        provider.initialize()
        self.assert_equal(provider.status(), AgentState.READY)

    def _test_default_provider_shutdown_and_reinitialize(self) -> None:
        provider = DefaultAgentProvider()
        provider.initialize()
        provider.shutdown()
        self.assert_equal(provider.status(), AgentState.SHUTDOWN)
        provider.shutdown()  # idempotent
        self.assert_equal(provider.status(), AgentState.SHUTDOWN)
        provider.initialize()
        self.assert_equal(provider.status(), AgentState.READY)

    def _test_default_provider_execute_requires_ready(self) -> None:
        provider = DefaultAgentProvider()
        try:
            provider.execute("do something")
        except AgentNotInitializedError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Expected AgentNotInitializedError")

    def _test_default_provider_execute_returns_result(self) -> None:
        provider = DefaultAgentProvider()
        provider.initialize()
        result = provider.execute("do something", metadata={"k": "v"})
        self.assert_true(result.success)
        self.assert_false(result.dispatched)
        self.assert_equal(result.state, AgentState.READY)
        self.assert_true(result.request_id.startswith("req-"))
        self.assert_equal(provider.status(), AgentState.READY)

        result2 = provider.execute("another")
        self.assert_true(result2.request_id != result.request_id)

    def _test_default_provider_execute_after_shutdown_raises(self) -> None:
        provider = DefaultAgentProvider()
        provider.initialize()
        provider.shutdown()
        try:
            provider.execute("anything")
        except AgentNotInitializedError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Expected AgentNotInitializedError")

    def _test_default_provider_cancel_known_and_unknown(self) -> None:
        provider = DefaultAgentProvider()
        provider.initialize()
        result = provider.execute("something")
        cancel_result = provider.cancel(result.request_id)
        self.assert_false(cancel_result.success)
        self.assert_equal(cancel_result.request_id, result.request_id)

        try:
            provider.cancel("does-not-exist")
        except AgentRequestNotFoundError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Expected AgentRequestNotFoundError")

    def _test_default_provider_reset_clears_state(self) -> None:
        provider = DefaultAgentProvider()
        provider.initialize()
        provider.execute("something")
        provider.reset()
        self.assert_equal(provider.status(), AgentState.READY)
        # Request ids restart from req-1 after reset (counter cleared).
        result = provider.execute("again")
        self.assert_equal(result.request_id, "req-1")

    def _test_default_provider_reset_does_not_initialize_or_resurrect(self) -> None:
        fresh = DefaultAgentProvider()
        fresh.reset()
        self.assert_equal(fresh.status(), AgentState.UNINITIALIZED)

        shut_down = DefaultAgentProvider()
        shut_down.initialize()
        shut_down.shutdown()
        shut_down.reset()
        self.assert_equal(shut_down.status(), AgentState.SHUTDOWN)

    def _test_default_provider_subsystem_registration(self) -> None:
        provider = DefaultAgentProvider()
        provider.register_subsystem("knowledge", status_check=lambda: True)
        provider.register_subsystem("declared_only")
        subsystems = provider.list_subsystems()
        self.assert_equal(len(subsystems), 2)
        names = {s.name for s in subsystems}
        self.assert_equal(names, {"knowledge", "declared_only"})
        by_name = {s.name: s.available for s in subsystems}
        self.assert_true(by_name["knowledge"])
        self.assert_true(by_name["declared_only"])  # None status_check -> always available

        provider.unregister_subsystem("knowledge")
        self.assert_equal(len(provider.list_subsystems()), 1)

    def _test_default_provider_subsystem_double_registration_raises(self) -> None:
        provider = DefaultAgentProvider()
        provider.register_subsystem("knowledge")
        try:
            provider.register_subsystem("knowledge")
        except SubsystemAlreadyRegisteredError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Expected SubsystemAlreadyRegisteredError")

    def _test_default_provider_unregister_unknown_raises(self) -> None:
        provider = DefaultAgentProvider()
        try:
            provider.unregister_subsystem("does-not-exist")
        except SubsystemNotFoundError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Expected SubsystemNotFoundError")

    def _test_default_provider_subsystem_status_check_failure_reported_unavailable(self) -> None:
        def _boom():
            raise RuntimeError("subsystem exploded")

        provider = DefaultAgentProvider()
        provider.register_subsystem("flaky", status_check=_boom)
        subsystems = provider.list_subsystems()
        self.assert_equal(len(subsystems), 1)
        self.assert_false(subsystems[0].available)

    # ---------- AgentManager ----------

    def _test_manager_registers_default_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            providers = manager.list_providers()
            self.assert_equal(len(providers), 1)
            self.assert_equal(providers[0].agent_name(), "jarvis")
            self.assert_equal(manager.current_provider_name(), "jarvis")

    def _test_manager_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            self.assert_true(manager.is_enabled())
            self.assert_equal(manager.startup_mode(), "idle")

    def _test_manager_invalid_enabled_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_ENABLED_YAML)
            except AgentConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected AgentConfigurationError")

    def _test_manager_invalid_default_agent_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_AGENT_YAML)
            except AgentConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected AgentConfigurationError")

    def _test_manager_invalid_startup_mode_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_STARTUP_MODE_YAML)
            except AgentConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected AgentConfigurationError")

    def _test_manager_auto_startup_mode_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp), _AUTO_STARTUP_AGENT_YAML)
            self.assert_equal(manager.startup_mode(), "auto")

    def _test_manager_duplicate_registration_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.register_provider(DefaultAgentProvider())
            except AgentProviderRegistryError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected AgentProviderRegistryError")

    def _test_manager_unknown_agent_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.get_provider("does-not-exist")
            except AgentProviderNotFoundError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected AgentProviderNotFoundError")

            try:
                manager.set_current("does-not-exist")
            except AgentProviderNotFoundError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected AgentProviderNotFoundError")

    def _test_manager_set_current_switches_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            recorder = _RecordingAgentProvider("recorder")
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
            manager = self._build_manager(Path(tmp), _DISABLED_AGENT_YAML)
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.current_provider_name() is None)

    # ---------- AgentEngine ----------

    def _test_engine_no_agent_selected_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            engine._manager.disable()  # noqa: SLF001
            try:
                engine.status()
            except NoAgentSelectedError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected NoAgentSelectedError")

    def _test_engine_forwards_lifecycle_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            self.assert_equal(engine.status(), AgentState.UNINITIALIZED)
            engine.initialize()
            self.assert_equal(engine.status(), AgentState.READY)
            engine.shutdown()
            self.assert_equal(engine.status(), AgentState.SHUTDOWN)

    def _test_engine_empty_request_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            engine.initialize()
            try:
                engine.execute("   ")
            except EmptyRequestError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected EmptyRequestError")

    def _test_engine_execute_and_cancel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            engine.initialize()
            result = engine.execute("do the thing")
            self.assert_true(result.success)
            cancel_result = engine.cancel(result.request_id)
            self.assert_false(cancel_result.success)

    def _test_engine_subsystem_registry_forwarding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp))
            engine.register_subsystem("knowledge", status_check=lambda: True)
            subsystems = engine.list_subsystems()
            self.assert_equal(len(subsystems), 1)
            self.assert_equal(subsystems[0].name, "knowledge")
            engine.unregister_subsystem("knowledge")
            self.assert_equal(len(engine.list_subsystems()), 0)

    def _test_engine_auto_startup_mode_initializes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp), _AUTO_STARTUP_AGENT_YAML)
            self.assert_equal(engine.status(), AgentState.READY)

    def _test_engine_idle_startup_mode_leaves_uninitialized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = self._build_engine(Path(tmp), _DEFAULT_AGENT_YAML)
            self.assert_equal(engine.status(), AgentState.UNINITIALIZED)

    # ---------- AgentService ----------

    def _test_service_status_reports_uninitialized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            status = service.status()
            self.assert_true(status.enabled)
            self.assert_equal(status.current_agent, "jarvis")
            self.assert_equal(status.state, AgentState.UNINITIALIZED)
            self.assert_equal(status.registered_agent_count, 1)
            self.assert_equal(status.startup_mode, "idle")
            self.assert_equal(status.subsystem_count, 0)

    def _test_service_status_reports_state_after_initialize(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            service.initialize()
            status = service.status()
            self.assert_equal(status.state, AgentState.READY)

    def _test_service_register_and_list_subsystems(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            outcome = service.register_subsystem("knowledge")
            self.assert_true(outcome.success)
            subsystems = service.list_subsystems()
            self.assert_equal(len(subsystems), 1)
            self.assert_equal(subsystems[0].name, "knowledge")

            duplicate = service.register_subsystem("knowledge")
            self.assert_false(duplicate.success)

    def _test_service_unregister_subsystem(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            service.register_subsystem("knowledge")
            outcome = service.unregister_subsystem("knowledge")
            self.assert_true(outcome.success)
            self.assert_equal(len(service.list_subsystems()), 0)

            missing = service.unregister_subsystem("does-not-exist")
            self.assert_false(missing.success)

    def _test_service_initialize_shutdown_reset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.initialize()
            self.assert_true(result.success)
            result = service.reset()
            self.assert_true(result.success)
            result = service.shutdown()
            self.assert_true(result.success)

    def _test_service_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.disable()
            self.assert_true(result.success)
            self.assert_false(service.status().enabled)

    def _test_service_execute_and_cancel_passthrough(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            service.initialize()
            result = service.execute("hello")
            self.assert_true(result.success)
            cancel_result = service.cancel(result.request_id)
            self.assert_false(cancel_result.success)

    # ---------- AgentModule (CLI) ----------

    def _test_cli_help_lists_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = AgentModule(service)
            self.assert_equal(module.name, "agent")
            result = module.execute("help", [])
            self.assert_true(result.success)
            for command in ("status", "subsystems", "register", "unregister", "reset", "initialize", "shutdown"):
                self.assert_true(command in result.message)

    def _test_cli_status_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = AgentModule(service)
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Enabled" in result.message)

    def _test_cli_subsystems_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = AgentModule(service)
            empty_result = module.execute("subsystems", [])
            self.assert_true(empty_result.success)

            module.execute("register", ["knowledge"])
            result = module.execute("subsystems", [])
            self.assert_true(result.success)
            self.assert_true("knowledge" in result.message)

    def _test_cli_register_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = AgentModule(service)
            self.assert_false(module.execute("register", []).success)
            result = module.execute("register", ["knowledge"])
            self.assert_true(result.success)
            duplicate = module.execute("register", ["knowledge"])
            self.assert_false(duplicate.success)

    def _test_cli_unregister_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = AgentModule(service)
            self.assert_false(module.execute("unregister", []).success)
            module.execute("register", ["knowledge"])
            result = module.execute("unregister", ["knowledge"])
            self.assert_true(result.success)

    def _test_cli_initialize_shutdown_reset_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = AgentModule(service)
            self.assert_true(module.execute("initialize", []).success)
            self.assert_true(module.execute("reset", []).success)
            self.assert_true(module.execute("shutdown", []).success)

    def _test_cli_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = AgentModule(service)
            result = module.execute("bogus", [])
            self.assert_false(result.success)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_agent_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.run()
                service = bootstrap.agent_service
                self.assert_true(service is not None)
                status = service.status()
                self.assert_true(status.enabled)
                self.assert_equal(status.current_agent, "jarvis")

                result = bootstrap._command_router.dispatch("agent status")  # noqa: SLF001
                self.assert_true(result.success)

    def _test_bootstrap_degrades_gracefully_on_invalid_agent_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, agent_default_agent="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.run()  # must not raise -- Agent Framework degrades, Jarvis still starts
                self.assert_true(bootstrap.agent_service is None)
                # The rest of the application is unaffected.
                self.assert_true(bootstrap.knowledge_service is not None)
                self.assert_true(bootstrap.compression_service is not None)

    def _test_bootstrap_auto_registers_available_subsystems(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.run()
                subsystems = bootstrap.agent_service.list_subsystems()
                names = {s.name for s in subsystems}
                expected = {
                    "embedding",
                    "rag",
                    "memory",
                    "knowledge",
                    "long_term_memory",
                    "semantic",
                    "compression",
                }
                self.assert_equal(names, expected)
                self.assert_true(all(s.available for s in subsystems))

    def _test_bootstrap_auto_startup_mode_initializes_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, agent_startup_mode="auto")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.run()
                self.assert_equal(bootstrap.agent_service.status().state, AgentState.READY)

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """EP-028 must not import a Planner, Reasoning Engine, Workflow Engine, or any AI provider."""
        forbidden_fragments = (
            "src.core.rag",
            "src.core.ai",
            "src.core.planner",
            "src.core.reasoning",
            "src.core.reflection",
            "src.core.workflow",
            "src.core.prompt",
            "src.core.conversation",
            "browser_automation",
            "tool_executor",
            "openai",
            "anthropic",
            "gemini",
            "ollama",
        )
        for module in (agent_engine_module, agent_manager_module, agent_provider_module):
            source = inspect.getsource(module)
            for fragment in forbidden_fragments:
                self.assert_true(
                    fragment not in source, f"{module.__name__} must not reference '{fragment}'"
                )

    def _test_manager_owns_no_storage_state(self) -> None:
        """AgentManager owns agent registration only, never subsystem or task storage."""
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            instance_attrs = vars(manager)
            forbidden_attr_names = ("_records", "_collection", "_store", "_documents", "_index", "_tasks")
            for attr_name in instance_attrs:
                for forbidden in forbidden_attr_names:
                    self.assert_true(
                        forbidden not in attr_name.lower(),
                        f"AgentManager should not own storage state ('{attr_name}')",
                    )

    def _test_exception_hierarchy(self) -> None:
        """AgentProviderError and AgentEngineError are both catchable through the shared root."""
        self.assert_true(issubclass(AgentProviderError, AgentFrameworkError))
        self.assert_true(issubclass(AgentEngineError, AgentFrameworkError))
        try:
            raise AgentProviderError("boom")
        except AgentFrameworkError:
            self.result.add_pass()
        else:
            self.assert_true(False, "AgentProviderError should be catchable as AgentFrameworkError")

    def _test_no_future_ep_components_implemented(self) -> None:
        """Only AgentProvider/DefaultAgentProvider exist -- no Planner/Reasoning/Reflection/etc."""
        forbidden_class_names = (
            "Planner",
            "ReasoningEngine",
            "ReflectionEngine",
            "WorkflowEngine",
            "TaskScheduler",
            "ToolExecutor",
            "MultiAgentCoordinator",
        )
        combined_source = "\n".join(
            inspect.getsource(module)
            for module in (agent_engine_module, agent_manager_module, agent_provider_module)
        )
        for class_name in forbidden_class_names:
            self.assert_true(
                f"class {class_name}" not in combined_source,
                f"{class_name} must not be implemented in EP-028",
            )

    def _test_no_private_api_access_in_bootstrap_wiring(self) -> None:
        """Bootstrap's EP-028 wiring reaches every subsystem only through its public `status()`."""
        import src.bootstrap as bootstrap_module

        source = inspect.getsource(bootstrap_module)
        start = source.find("EP-028: Agent Framework")
        self.assert_true(start != -1, "EP-028 wiring block not found in bootstrap.py")
        end = source.find("invoice_service = InvoiceService", start)
        wiring_block = source[start:end]
        forbidden_accesses = ("service._", "._manager.", "._providers", "._store")
        for forbidden in forbidden_accesses:
            self.assert_true(
                forbidden not in wiring_block,
                f"Agent Framework bootstrap wiring must not access '{forbidden}'",
            )
