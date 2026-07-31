"""Real engineering tests for EP-023 - Memory Manager.

Builds real `MemoryStore`/`MemoryProvider`/`MemoryManager`/
`MemoryService`/`MemoryModule` instances (loading a real `Config` from
a temporary config.yaml, as in `tests/EP021/test_embedding_engine.py`)
and drives them exactly as a caller would -- no mocked internals,
matching every other EP's test suite in this project.

EP-023 extends the existing (EP-013) Memory & Context Manager with a
provider-orchestration layer instead of replacing it, so this suite
covers three things:

1. The new EP-023 abstraction itself: `MemoryProvider`,
   `MemoryStoreProvider`, `MemoryManager` (registration, enable/
   disable, active-provider switching, status, the unified
   store/load/delete/clear/exists/list API).
2. `MemoryService`/`MemoryModule` regression: every EP-013 public
   method and CLI command must behave exactly as before.
3. Architecture compliance: no forbidden imports, no duplicated
   storage logic, no future-EP provider implementations, and a real
   `Bootstrap` run proving both normal wiring and graceful
   degradation on invalid 'memory.*' configuration.
"""

from __future__ import annotations

import ast
import inspect
import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.config import Config
from src.core.memory import (
    DEFAULT_NAMESPACE,
    ManagerStatus,
    MemoryEntry,
    MemoryManager,
    MemoryProvider,
    MemoryProviderError,
    MemoryStore,
    MemoryStoreProvider,
    ProviderStatus,
)
from src.core.memory import memory_manager as memory_manager_module
from src.core.memory import memory_provider as memory_provider_module
from src.modules.memory_module import MemoryModule
from src.services.memory_service import MemoryService
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

    def __exit__(self, *_exc_info: object) -> None:
        os.chdir(self._original)


def _write_config(directory: Path, memory_settings: str) -> Config:
    """Write a minimal, self-contained config.yaml and load it.

    Only 'memory.*' keys are set; every other key resolves to its own
    built-in default via `Config.get`'s `default` argument, exactly as
    it would for an operator who never configured it.
    """
    config_path = directory / "config.yaml"
    config_path.write_text(memory_settings, encoding="utf-8")
    return Config(config_path).load()


_DEFAULT_CONFIG_YAML = (
    "memory:\n"
    "  enabled: true\n"
    "  persistent: false\n"
    "  auto_save: false\n"
    "  default_provider: \"memory\"\n"
)

_DISABLED_CONFIG_YAML = (
    "memory:\n"
    "  enabled: false\n"
    "  persistent: false\n"
    "  auto_save: false\n"
    "  default_provider: \"memory\"\n"
)

_INVALID_PROVIDER_CONFIG_YAML = (
    "memory:\n"
    "  enabled: true\n"
    "  persistent: false\n"
    "  auto_save: false\n"
    "  default_provider: \"\"\n"
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
    "  default_provider: \"{default_provider}\"\n\n"
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
    "      dimension: 32\n"
    "    cloud:\n"
    "      enabled: false\n"
    "      api_key: \"\"\n"
    "      model: \"text-embedding-cloud-v1\"\n"
    "      dimension: 1536\n\n"
    "rag:\n"
    "  enabled: true\n"
    "  top_k: 5\n"
    "  max_context_characters: 4000\n"
)

_BOOTSTRAP_REQUIRED_DIRECTORIES: tuple[str, ...] = (
    "logs",
    "data/input",
    "data/output",
    "data/cache",
    "data/database",
    "knowledge",
    "prompts",
)


def _write_full_bootstrap_config(directory: Path, default_provider: str) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(default_provider=default_provider),
        encoding="utf-8",
    )


class _RecordingProvider(MemoryProvider):
    """A minimal, independent MemoryProvider used only to test MemoryManager.

    Stores entries in a plain dict, entirely separate from MemoryStore,
    so tests can prove MemoryManager truly delegates to whichever
    provider is active rather than always reading the built-in one.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._data: dict[str, dict[str, object]] = {}

    @property
    def name(self) -> str:
        return self._name

    def store(self, key: str, value: object, namespace: str = DEFAULT_NAMESPACE) -> None:
        self._data.setdefault(namespace, {})[key] = value

    def load(self, key: str, namespace: str = DEFAULT_NAMESPACE) -> object | None:
        return self._data.get(namespace, {}).get(key)

    def delete(self, key: str, namespace: str = DEFAULT_NAMESPACE) -> bool:
        bucket = self._data.get(namespace, {})
        if key not in bucket:
            return False
        del bucket[key]
        return True

    def clear(self, namespace: str | None = None) -> int:
        if namespace is None:
            count = sum(len(bucket) for bucket in self._data.values())
            self._data.clear()
            return count
        bucket = self._data.pop(namespace, {})
        return len(bucket)

    def exists(self, key: str, namespace: str = DEFAULT_NAMESPACE) -> bool:
        return key in self._data.get(namespace, {})

    def list(self, namespace: str | None = None) -> list[str]:
        if namespace is None:
            keys: list[str] = []
            for bucket in self._data.values():
                keys.extend(bucket.keys())
            return sorted(keys)
        return sorted(self._data.get(namespace, {}).keys())


@TestRegistry.register
class MemoryManagerTest(BaseTest):
    """Real tests covering EP-023's Memory Manager and its EP-013 integration."""

    NAME = "EP023"

    def run(self):
        """Execute every Memory Manager check and return the aggregated result."""
        # MemoryProvider / MemoryStoreProvider (adapter)
        self._test_store_provider_delegates_to_memory_store()
        self._test_store_provider_exists_and_list()
        self._test_store_provider_clear_namespace_and_all()
        self._test_provider_is_abstract()

        # MemoryManager: registration
        self._test_register_activates_default_provider()
        self._test_register_second_provider_does_not_steal_active()
        self._test_providers_list_sorted()
        self._test_unregister_clears_active_if_active()
        self._test_unregister_unknown_returns_false()

        # MemoryManager: enable / disable / switch
        self._test_disable_active_clears_active()
        self._test_enable_unknown_returns_false()
        self._test_use_switches_active_provider()
        self._test_use_unknown_provider_raises()
        self._test_use_disabled_provider_raises()

        # MemoryManager: status + unified API
        self._test_status_snapshot()
        self._test_unified_api_delegates_to_active_provider()
        self._test_unified_api_raises_without_active_provider()

        # MemoryService: EP-023 additions
        self._test_service_builds_default_manager_and_registers_memory_provider()
        self._test_service_invalid_default_provider_raises()
        self._test_service_non_string_default_provider_raises()
        self._test_service_providers_status_and_current_provider()
        self._test_service_use_provider_success_and_unknown()
        self._test_service_use_provider_rejected_when_disabled()
        self._test_service_accepts_injected_manager()

        # MemoryService: EP-013 regression (every existing public method)
        self._test_regression_set_get_delete()
        self._test_regression_clear_and_list()
        self._test_regression_export_import()
        self._test_regression_status_and_doctor()
        self._test_regression_disabled_subsystem_rejects_mutations()

        # MemoryModule (CLI): EP-023 additions
        self._test_cli_help_lists_new_commands()
        self._test_cli_providers_command()
        self._test_cli_use_command_success_missing_and_unknown()

        # MemoryModule (CLI): EP-013 regression
        self._test_cli_regression_status_set_get_delete_clear_list()

        # Bootstrap wiring (dependency injection + graceful degradation)
        self._test_bootstrap_registers_memory_module()
        self._test_bootstrap_degrades_gracefully_on_invalid_provider_config()

        # Architectural acceptance criteria
        self._test_no_forbidden_imports()
        self._test_no_future_ep_provider_classes()
        self._test_manager_owns_no_storage_state()
        self._test_exception_hierarchy()

        return self.result

    # ---------- Helpers ----------

    def _build_store_and_provider(self) -> tuple[MemoryStore, MemoryStoreProvider]:
        store = MemoryStore()
        return store, MemoryStoreProvider(store=store)

    def _build_service(self, config_yaml: str = _DEFAULT_CONFIG_YAML) -> MemoryService:
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), config_yaml)
        store = MemoryStore()
        service = MemoryService(config=config, store=store)
        # Keep the TemporaryDirectory alive for the caller's lifetime by
        # attaching it to the service instance (avoids premature cleanup).
        service._test_tmp_dir = tmp_dir  # type: ignore[attr-defined]
        return service

    # ---------- MemoryStoreProvider ----------

    def _test_store_provider_delegates_to_memory_store(self) -> None:
        """`store`/`load`/`delete` on MemoryStoreProvider reach the wrapped MemoryStore."""
        store, provider = self._build_store_and_provider()
        provider.store("greeting", "hello")
        self.assert_equal(provider.load("greeting"), "hello")
        self.assert_equal(store.get(DEFAULT_NAMESPACE, "greeting").value, "hello")

        self.assert_true(provider.delete("greeting"))
        self.assert_true(provider.load("greeting") is None)
        self.assert_false(provider.delete("greeting"), "second delete should return False")

    def _test_store_provider_exists_and_list(self) -> None:
        """`exists`/`list` reflect entries stored through the provider."""
        _, provider = self._build_store_and_provider()
        self.assert_false(provider.exists("a"))
        provider.store("a", 1, namespace="ns")
        provider.store("b", 2, namespace="ns")
        self.assert_true(provider.exists("a", namespace="ns"))
        self.assert_equal(provider.list(namespace="ns"), ["a", "b"])
        self.assert_equal(sorted(provider.list()), ["a", "b"])

    def _test_store_provider_clear_namespace_and_all(self) -> None:
        """`clear(namespace)` only removes that namespace; `clear(None)` removes everything."""
        _, provider = self._build_store_and_provider()
        provider.store("a", 1, namespace="ns1")
        provider.store("b", 2, namespace="ns2")

        removed = provider.clear(namespace="ns1")
        self.assert_equal(removed, 1)
        self.assert_false(provider.exists("a", namespace="ns1"))
        self.assert_true(provider.exists("b", namespace="ns2"))

        removed_all = provider.clear(None)
        self.assert_equal(removed_all, 1)
        self.assert_false(provider.exists("b", namespace="ns2"))

    def _test_provider_is_abstract(self) -> None:
        """`MemoryProvider` cannot be instantiated directly."""
        try:
            MemoryProvider()  # type: ignore[abstract]
        except TypeError:
            self.result.add_pass()
        else:
            self.assert_true(False, "MemoryProvider should not be directly instantiable")

    # ---------- MemoryManager: registration ----------

    def _test_register_activates_default_provider(self) -> None:
        """Registering the configured default provider activates it automatically."""
        manager = MemoryManager(default_provider="memory")
        _, provider = self._build_store_and_provider()
        manager.register(provider)
        self.assert_equal(manager.active_provider_name(), "memory")
        self.assert_true(manager.active_provider() is provider)

    def _test_register_second_provider_does_not_steal_active(self) -> None:
        """A second registered provider never displaces an already-active one."""
        manager = MemoryManager(default_provider="memory")
        _, first = self._build_store_and_provider()
        manager.register(first)
        second = _RecordingProvider("secondary")
        manager.register(second)
        self.assert_equal(manager.active_provider_name(), "memory")

    def _test_providers_list_sorted(self) -> None:
        """`providers()` returns every registered name, sorted."""
        manager = MemoryManager()
        manager.register(_RecordingProvider("zeta"))
        manager.register(_RecordingProvider("alpha"))
        self.assert_equal(manager.providers(), ["alpha", "zeta"])

    def _test_unregister_clears_active_if_active(self) -> None:
        """Unregistering the active provider clears the active selection."""
        manager = MemoryManager(default_provider="memory")
        _, provider = self._build_store_and_provider()
        manager.register(provider)
        self.assert_true(manager.unregister("memory"))
        self.assert_true(manager.active_provider_name() is None)
        self.assert_equal(manager.providers(), [])

    def _test_unregister_unknown_returns_false(self) -> None:
        """Unregistering an unknown provider name returns False, not an exception."""
        manager = MemoryManager()
        self.assert_false(manager.unregister("does-not-exist"))

    # ---------- MemoryManager: enable / disable / switch ----------

    def _test_disable_active_clears_active(self) -> None:
        """Disabling the currently active provider clears the active selection."""
        manager = MemoryManager(default_provider="memory")
        _, provider = self._build_store_and_provider()
        manager.register(provider)
        self.assert_true(manager.disable("memory"))
        self.assert_true(manager.active_provider_name() is None)
        self.assert_false(manager.is_enabled("memory"))

    def _test_enable_unknown_returns_false(self) -> None:
        """Enabling an unknown provider name returns False, not an exception."""
        manager = MemoryManager()
        self.assert_false(manager.enable("does-not-exist"))

    def _test_use_switches_active_provider(self) -> None:
        """`use()` switches to a different, enabled provider."""
        manager = MemoryManager(default_provider="memory")
        _, provider = self._build_store_and_provider()
        manager.register(provider)
        secondary = _RecordingProvider("secondary")
        manager.register(secondary, enabled=True)

        manager.use("secondary")
        self.assert_equal(manager.active_provider_name(), "secondary")
        self.assert_true(manager.active_provider() is secondary)

    def _test_use_unknown_provider_raises(self) -> None:
        """`use()` on an unregistered name raises MemoryProviderError."""
        manager = MemoryManager()
        try:
            manager.use("nope")
        except MemoryProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "use() should raise for an unknown provider")

    def _test_use_disabled_provider_raises(self) -> None:
        """`use()` on a disabled provider raises MemoryProviderError."""
        manager = MemoryManager(default_provider="memory")
        _, provider = self._build_store_and_provider()
        manager.register(provider, enabled=False)
        try:
            manager.use("memory")
        except MemoryProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "use() should raise for a disabled provider")

    # ---------- MemoryManager: status + unified API ----------

    def _test_status_snapshot(self) -> None:
        """`status()` reports provider count, active provider, and per-provider flags."""
        manager = MemoryManager(default_provider="memory")
        _, provider = self._build_store_and_provider()
        manager.register(provider)
        manager.register(_RecordingProvider("secondary"), enabled=False)

        status: ManagerStatus = manager.status()
        self.assert_equal(status.provider_count, 2)
        self.assert_equal(status.active_provider, "memory")

        by_name = {entry.name: entry for entry in status.providers}
        self.assert_true(isinstance(by_name["memory"], ProviderStatus))
        self.assert_true(by_name["memory"].enabled)
        self.assert_true(by_name["memory"].active)
        self.assert_false(by_name["secondary"].enabled)
        self.assert_false(by_name["secondary"].active)

    def _test_unified_api_delegates_to_active_provider(self) -> None:
        """MemoryManager's store/load/delete/clear/exists/list reach the active provider."""
        manager = MemoryManager(default_provider="memory")
        _, provider = self._build_store_and_provider()
        manager.register(provider)

        manager.store("k", "v")
        self.assert_equal(manager.load("k"), "v")
        self.assert_true(manager.exists("k"))
        self.assert_equal(manager.list(), ["k"])
        self.assert_true(manager.delete("k"))
        self.assert_false(manager.exists("k"))

        manager.store("a", 1)
        manager.store("b", 2)
        self.assert_equal(manager.clear(), 2)

    def _test_unified_api_raises_without_active_provider(self) -> None:
        """Every unified-API method raises MemoryProviderError with no active provider."""
        manager = MemoryManager()
        for operation in (
            lambda: manager.store("k", "v"),
            lambda: manager.load("k"),
            lambda: manager.delete("k"),
            lambda: manager.clear(),
            lambda: manager.exists("k"),
            lambda: manager.list(),
        ):
            try:
                operation()
            except MemoryProviderError:
                self.result.add_pass()
            else:
                self.assert_true(False, "operation should raise without an active provider")

    # ---------- MemoryService: EP-023 additions ----------

    def _test_service_builds_default_manager_and_registers_memory_provider(self) -> None:
        """A MemoryService built without an explicit manager registers the "memory" provider."""
        service = self._build_service()
        status = service.providers_status()
        self.assert_equal(status.provider_count, 1)
        self.assert_equal(service.current_provider(), "memory")
        self.assert_equal(status.providers[0].name, "memory")
        self.assert_true(status.providers[0].active)

    def _test_service_invalid_default_provider_raises(self) -> None:
        """An empty 'memory.default_provider' raises MemoryProviderError at construction."""
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), _INVALID_PROVIDER_CONFIG_YAML)
        try:
            MemoryService(config=config, store=MemoryStore())
        except MemoryProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "empty default_provider should raise MemoryProviderError")

    def _test_service_non_string_default_provider_raises(self) -> None:
        """A non-string 'memory.default_provider' raises MemoryProviderError at construction."""
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(
            Path(tmp_dir.name),
            "memory:\n  enabled: true\n  persistent: false\n  default_provider: 123\n",
        )
        try:
            MemoryService(config=config, store=MemoryStore())
        except MemoryProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "non-string default_provider should raise MemoryProviderError")

    def _test_service_providers_status_and_current_provider(self) -> None:
        """`providers_status()`/`current_provider()` reflect the built-in "memory" provider."""
        service = self._build_service()
        self.assert_equal(service.current_provider(), "memory")
        status = service.providers_status()
        self.assert_true(isinstance(status, ManagerStatus))
        self.assert_equal(status.active_provider, "memory")

    def _test_service_use_provider_success_and_unknown(self) -> None:
        """`use_provider()` succeeds for the registered provider, fails for an unknown one."""
        service = self._build_service()
        result = service.use_provider("memory")
        self.assert_true(result.success)

        result = service.use_provider("does-not-exist")
        self.assert_false(result.success)

    def _test_service_use_provider_rejected_when_disabled(self) -> None:
        """`use_provider()` is rejected while the Memory subsystem itself is disabled."""
        service = self._build_service(_DISABLED_CONFIG_YAML)
        result = service.use_provider("memory")
        self.assert_false(result.success)

    def _test_service_accepts_injected_manager(self) -> None:
        """A MemoryService can be constructed with a pre-built MemoryManager (DI)."""
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), _DEFAULT_CONFIG_YAML)
        store = MemoryStore()
        manager = MemoryManager(default_provider="custom")
        manager.register(MemoryStoreProvider(store=store, name="custom"))

        service = MemoryService(config=config, store=store, manager=manager)
        self.assert_equal(service.current_provider(), "custom")

    # ---------- MemoryService: EP-013 regression ----------

    def _test_regression_set_get_delete(self) -> None:
        """`set`/`get`/`delete` behave exactly as before EP-023."""
        service = self._build_service()
        result = service.set("key1", "value1")
        self.assert_true(result.success)

        entry = service.get("key1")
        self.assert_not_none(entry)
        self.assert_equal(entry.value, "value1")

        result = service.delete("key1")
        self.assert_true(result.success)
        self.assert_true(service.get("key1") is None)

    def _test_regression_clear_and_list(self) -> None:
        """`clear`/`list_entries` behave exactly as before EP-023."""
        service = self._build_service()
        service.set("a", 1)
        service.set("b", 2)
        entries = service.list_entries()
        self.assert_equal(len(entries), 2)

        result = service.clear()
        self.assert_true(result.success)
        self.assert_equal(service.list_entries(), [])

    def _test_regression_export_import(self) -> None:
        """`export`/`import_` behave exactly as before EP-023."""
        service = self._build_service()
        service.set("persisted", "value", persistent=True)

        tmp_dir = tempfile.TemporaryDirectory()
        export_path = str(Path(tmp_dir.name) / "export.json")
        export_result = service.export(export_path)
        self.assert_true(export_result.success)

        service.clear()
        import_result = service.import_(export_path)
        self.assert_true(import_result.success)
        entry = service.get("persisted")
        self.assert_not_none(entry)
        self.assert_equal(entry.value, "value")

    def _test_regression_status_and_doctor(self) -> None:
        """`status()`/`doctor()` still return well-formed EP-013 results."""
        service = self._build_service()
        service.set("k", "v")
        status = service.status()
        self.assert_equal(status.total_entries, 1)
        self.assert_true(status.enabled)

        report = service.doctor()
        self.assert_true(report.store_available)
        self.assert_true(report.is_ready)

    def _test_regression_disabled_subsystem_rejects_mutations(self) -> None:
        """A disabled Memory subsystem still rejects `set`/`clear`/`export`/`import_`."""
        service = self._build_service(_DISABLED_CONFIG_YAML)
        self.assert_false(service.set("k", "v").success)
        self.assert_false(service.clear().success)
        self.assert_false(service.export().success)
        self.assert_false(service.import_().success)

    # ---------- MemoryModule (CLI): EP-023 additions ----------

    def _build_module(self, config_yaml: str = _DEFAULT_CONFIG_YAML) -> MemoryModule:
        return MemoryModule(self._build_service(config_yaml))

    def _test_cli_help_lists_new_commands(self) -> None:
        """`memory help` lists both the EP-013 commands and the new EP-023 commands."""
        module = self._build_module()
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("memory providers" in result.message)
        self.assert_true("memory use <provider>" in result.message)
        self.assert_true("memory status" in result.message)
        self.assert_true("memory clear" in result.message)

    def _test_cli_providers_command(self) -> None:
        """`memory providers` lists the registered "memory" provider as active."""
        module = self._build_module()
        result = module.execute("providers", [])
        self.assert_true(result.success)
        self.assert_true("memory" in result.message)
        self.assert_true("enabled" in result.message)

    def _test_cli_use_command_success_missing_and_unknown(self) -> None:
        """`memory use` succeeds for a known provider, and fails cleanly otherwise."""
        module = self._build_module()

        result = module.execute("use", [])
        self.assert_false(result.success)

        result = module.execute("use", ["memory"])
        self.assert_true(result.success)

        result = module.execute("use", ["does-not-exist"])
        self.assert_false(result.success)

    # ---------- MemoryModule (CLI): EP-013 regression ----------

    def _test_cli_regression_status_set_get_delete_clear_list(self) -> None:
        """Every pre-existing CLI action still works after the EP-023 additions."""
        module = self._build_module()

        self.assert_true(module.execute("set", ["k", "v"]).success)
        get_result = module.execute("get", ["k"])
        self.assert_true(get_result.success)
        self.assert_equal(get_result.message, "v")

        self.assert_true(module.execute("status", []).success)
        self.assert_true(module.execute("list", []).success)
        self.assert_true(module.execute("delete", ["k"]).success)
        self.assert_true(module.execute("clear", []).success)

        unknown_result = module.execute("bogus-action", [])
        self.assert_false(unknown_result.success)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_memory_module(self) -> None:
        """A real Bootstrap.run() with valid config registers "memory" and activates it."""
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            project_root = Path(tmp_dir_name)
            _write_full_bootstrap_config(project_root, default_provider="memory")
            with _ChdirGuard(project_root):
                bootstrap = Bootstrap(project_root=project_root)
                orchestrator = bootstrap.run()
                try:
                    self.assert_not_none(bootstrap.memory_service)
                    self.assert_equal(bootstrap.memory_service.current_provider(), "memory")
                    router = bootstrap.command_router
                    self.assert_true("memory" in router.module_names)
                    dispatch_result = router.dispatch("memory providers")
                    self.assert_true(dispatch_result.success)
                finally:
                    orchestrator.stop()

    def _test_bootstrap_degrades_gracefully_on_invalid_provider_config(self) -> None:
        """Invalid 'memory.default_provider' disables Memory but the rest of Jarvis still starts."""
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            project_root = Path(tmp_dir_name)
            _write_full_bootstrap_config(project_root, default_provider="")
            with _ChdirGuard(project_root):
                bootstrap = Bootstrap(project_root=project_root)
                orchestrator = bootstrap.run()
                try:
                    self.assert_true(bootstrap.memory_service is None)
                    router = bootstrap.command_router
                    self.assert_false("memory" in router.module_names)
                    # The rest of the application still started successfully.
                    self.assert_true("system" in router.module_names)
                    self.assert_true(orchestrator is not None)
                finally:
                    orchestrator.stop()

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """The Memory package never imports Knowledge Base, RAG, Embedding, Agent, etc.

        Per EP-023's task brief, MemoryManager must not import Knowledge
        Base, Semantic Search, Long-Term Memory, Context Compression,
        Retrieval, RAG, Embedding, Agent Framework, Planner, Reflection,
        Vector Store, Browser Automation, or any future EP.
        """
        forbidden_module_fragments = (
            "knowledge_base",
            "semantic_search",
            "long_term_memory",
            "context_compression",
            "retrieval",
            "rag",
            "embedding",
            "agent_framework",
            "planner",
            "planning",
            "reflection",
            "vector_store",
            "faiss",
            "chroma",
            "pinecone",
            "qdrant",
            "weaviate",
            "browser_automation",
        )
        modules = [memory_manager_module, memory_provider_module]
        for module in modules:
            tree = ast.parse(inspect.getsource(module))
            imported_names: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_names.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_names.append(node.module)
            for imported_name in imported_names:
                lowered = imported_name.lower()
                for forbidden_fragment in forbidden_module_fragments:
                    self.assert_true(
                        forbidden_fragment not in lowered,
                        f"{module.__name__} should never import '{imported_name}'",
                    )

    def _test_no_future_ep_provider_classes(self) -> None:
        """Only `MemoryStoreProvider` is a concrete provider; no future EP providers exist.

        EP-023 must implement only the abstraction (`MemoryProvider`)
        and the adapter around the existing MemoryStore
        (`MemoryStoreProvider`) -- not InMemoryProvider,
        KnowledgeBaseProvider, LongTermMemoryProvider, or
        ExternalProvider, which are explicitly future work.
        """
        forbidden_class_names = (
            "InMemoryProvider",
            "KnowledgeBaseProvider",
            "LongTermMemoryProvider",
            "ExternalProvider",
        )
        module_source = inspect.getsource(memory_provider_module)
        for class_name in forbidden_class_names:
            self.assert_true(
                f"class {class_name}" not in module_source,
                f"{class_name} must not be implemented in EP-023",
            )

    def _test_manager_owns_no_storage_state(self) -> None:
        """MemoryManager keeps no entry data itself -- only provider registration state.

        Confirmed structurally: MemoryManager's __init__ only tracks
        dictionaries of provider *references* and enabled flags, never
        a dict of stored entries/values.
        """
        manager = MemoryManager()
        instance_attrs = vars(manager)
        forbidden_attr_names = ("entries", "values", "data", "namespaces")
        for attr_name in instance_attrs:
            for forbidden in forbidden_attr_names:
                self.assert_true(
                    forbidden not in attr_name.lower(),
                    f"MemoryManager should not own storage state ('{attr_name}')",
                )

    def _test_exception_hierarchy(self) -> None:
        """MemoryProviderError is a plain Exception, catchable on its own."""
        self.assert_true(issubclass(MemoryProviderError, Exception))
        try:
            raise MemoryProviderError("boom")
        except MemoryProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "MemoryProviderError should be catchable directly")
