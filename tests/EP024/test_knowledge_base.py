"""Real engineering tests for EP-024 - Knowledge Base.

Builds real `KnowledgeCollection`/`KnowledgeProvider`/`KnowledgeManager`/
`KnowledgeService`/`KnowledgeModule` instances (loading a real `Config`
from a temporary config.yaml, as in `tests/EP023/test_memory_manager.py`)
and drives them exactly as a caller would -- no mocked internals,
matching every other EP's test suite in this project.

Knowledge Base (EP-024) is a new subsystem, structurally mirroring the
provider/manager pattern already used by EP-023's Memory Manager, but
implemented as its own independent package (`src/core/knowledge/`)
with no dependency on MemoryStore/MemoryManager, ProjectIndexer,
Embedding, or RAG. This suite covers:

1. The domain model and storage engine: `KnowledgeRecord`,
   `KnowledgeCollection` (collection-organized CRUD + statistics).
2. The provider abstraction: `KnowledgeProvider`,
   `KnowledgeCollectionProvider`.
3. `KnowledgeManager`: registration, enable/disable, active-provider
   switching, status, and the unified store/load/update/delete/clear/
   list/collections/stats API.
4. `KnowledgeService`/`KnowledgeModule`: configuration-driven
   construction, graceful degradation, and every CLI command
   ("status", "collections", "list", "info", "clear", "help").
5. Architecture compliance: no forbidden imports, no duplicated
   storage logic, no future-EP functionality, and a real `Bootstrap`
   run proving both normal wiring and graceful degradation on invalid
   'knowledge.*' configuration.
"""

from __future__ import annotations

import ast
import inspect
import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.config import Config
from src.core.knowledge import (
    DEFAULT_COLLECTION,
    CollectionStats,
    KnowledgeCollection,
    KnowledgeCollectionProvider,
    KnowledgeManager,
    KnowledgeProvider,
    KnowledgeProviderError,
    KnowledgeRecord,
    ManagerStatus,
    ProviderStatus,
)
from src.core.knowledge import knowledge_manager as knowledge_manager_module
from src.core.knowledge import knowledge_provider as knowledge_provider_module
from src.modules.knowledge_module import KnowledgeModule
from src.services.knowledge_service import KnowledgeService
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


def _write_config(directory: Path, knowledge_settings: str) -> Config:
    """Write a minimal, self-contained config.yaml and load it.

    Only 'knowledge.*' keys are set; every other key resolves to its
    own built-in default via `Config.get`'s `default` argument, exactly
    as it would for an operator who never configured it.
    """
    config_path = directory / "config.yaml"
    config_path.write_text(knowledge_settings, encoding="utf-8")
    return Config(config_path).load()


_DEFAULT_CONFIG_YAML = (
    "knowledge:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n"
)

_DISABLED_CONFIG_YAML = (
    "knowledge:\n"
    "  enabled: false\n"
    "  default_provider: \"local\"\n"
)

_INVALID_PROVIDER_CONFIG_YAML = (
    "knowledge:\n"
    "  enabled: true\n"
    "  default_provider: \"\"\n"
)

# Full, offline-safe config.yaml covering every section Bootstrap._build_command_router
# reads, so a real Bootstrap.initialize() can be exercised end to end in a temporary
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


def _write_full_bootstrap_config(directory: Path, default_provider: str) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(default_provider=default_provider),
        encoding="utf-8",
    )


class _RecordingProvider(KnowledgeProvider):
    """A minimal, independent KnowledgeProvider used only to test KnowledgeManager.

    Stores records in a plain dict, entirely separate from
    KnowledgeCollection, so tests can prove KnowledgeManager truly
    delegates to whichever provider is active rather than always
    reading the built-in one.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._data: dict[str, dict[str, KnowledgeRecord]] = {}

    @property
    def name(self) -> str:
        return self._name

    def store(self, key, content, collection=DEFAULT_COLLECTION, metadata=None) -> KnowledgeRecord:
        record = KnowledgeRecord(key=key, content=content, collection=collection, metadata=metadata or {})
        self._data.setdefault(collection, {})[key] = record
        return record

    def load(self, key, collection=DEFAULT_COLLECTION):
        return self._data.get(collection, {}).get(key)

    def update(self, key, content, collection=DEFAULT_COLLECTION, metadata=None):
        bucket = self._data.get(collection, {})
        if key not in bucket:
            return None
        existing = bucket[key]
        updated = KnowledgeRecord(
            key=key,
            content=content,
            collection=collection,
            metadata=metadata if metadata is not None else existing.metadata,
            created_at=existing.created_at,
        )
        bucket[key] = updated
        return updated

    def delete(self, key, collection=DEFAULT_COLLECTION) -> bool:
        bucket = self._data.get(collection, {})
        if key not in bucket:
            return False
        del bucket[key]
        return True

    def clear(self, collection=None) -> int:
        if collection is None:
            count = sum(len(bucket) for bucket in self._data.values())
            self._data.clear()
            return count
        bucket = self._data.pop(collection, {})
        return len(bucket)

    def list(self, collection=None):
        if collection is None:
            records: list[KnowledgeRecord] = []
            for bucket in self._data.values():
                records.extend(bucket.values())
            return sorted(records, key=lambda record: (record.collection, record.key))
        return sorted(self._data.get(collection, {}).values(), key=lambda record: record.key)

    def collections(self):
        return sorted(name for name, bucket in self._data.items() if bucket)

    def stats(self, collection=None):
        if collection is None:
            return [
                CollectionStats(name=name, record_count=len(bucket))
                for name, bucket in sorted(self._data.items())
                if bucket
            ]
        bucket = self._data.get(collection)
        if not bucket:
            return []
        return [CollectionStats(name=collection, record_count=len(bucket))]


@TestRegistry.register
class KnowledgeBaseTest(BaseTest):
    """Real tests covering EP-024's Knowledge Base."""

    NAME = "EP024"

    def run(self):
        """Execute every Knowledge Base check and return the aggregated result."""
        # KnowledgeRecord
        self._test_record_to_dict_and_from_dict_roundtrip()

        # KnowledgeCollection (storage engine)
        self._test_collection_store_load()
        self._test_collection_update_existing_and_missing()
        self._test_collection_delete()
        self._test_collection_clear_collection_and_all()
        self._test_collection_list_scoped_and_all()
        self._test_collection_collections_and_stats()

        # KnowledgeProvider / KnowledgeCollectionProvider (adapter)
        self._test_provider_delegates_to_collection_store()
        self._test_provider_preserves_created_at_on_overwrite()
        self._test_provider_is_abstract()

        # KnowledgeManager: registration
        self._test_register_activates_default_provider()
        self._test_register_second_provider_does_not_steal_active()
        self._test_providers_list_sorted()
        self._test_unregister_clears_active_if_active()
        self._test_unregister_unknown_returns_false()

        # KnowledgeManager: enable / disable / switch
        self._test_disable_active_clears_active()
        self._test_enable_unknown_returns_false()
        self._test_use_switches_active_provider()
        self._test_use_unknown_provider_raises()
        self._test_use_disabled_provider_raises()

        # KnowledgeManager: status + unified API
        self._test_status_snapshot()
        self._test_unified_api_delegates_to_active_provider()
        self._test_unified_api_raises_without_active_provider()

        # KnowledgeService
        self._test_service_builds_default_manager_and_registers_local_provider()
        self._test_service_invalid_default_provider_raises()
        self._test_service_non_string_default_provider_raises()
        self._test_service_accepts_injected_manager()
        self._test_service_store_load_update_delete()
        self._test_service_collections_and_stats()
        self._test_service_status()
        self._test_service_disabled_subsystem_rejects_mutations_and_reads()

        # KnowledgeModule (CLI)
        self._test_cli_help_lists_commands()
        self._test_cli_status_command()
        self._test_cli_collections_command()
        self._test_cli_list_command_scoped_and_all()
        self._test_cli_info_command_found_and_missing()
        self._test_cli_clear_command()
        self._test_cli_unknown_action()

        # Bootstrap wiring (dependency injection + graceful degradation)
        self._test_bootstrap_registers_knowledge_module()
        self._test_bootstrap_degrades_gracefully_on_invalid_provider_config()

        # Architectural acceptance criteria
        self._test_no_forbidden_imports()
        self._test_no_future_ep_provider_classes()
        self._test_manager_owns_no_storage_state()
        self._test_exception_hierarchy()

        return self.result

    # ---------- Helpers ----------

    def _build_collection_and_provider(self) -> tuple[KnowledgeCollection, KnowledgeCollectionProvider]:
        store = KnowledgeCollection()
        return store, KnowledgeCollectionProvider(store=store)

    def _build_service(self, config_yaml: str = _DEFAULT_CONFIG_YAML) -> KnowledgeService:
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), config_yaml)
        service = KnowledgeService(config=config)
        # Keep the TemporaryDirectory alive for the caller's lifetime by
        # attaching it to the service instance (avoids premature cleanup).
        service._test_tmp_dir = tmp_dir  # type: ignore[attr-defined]
        return service

    def _build_module(self, config_yaml: str = _DEFAULT_CONFIG_YAML) -> KnowledgeModule:
        return KnowledgeModule(self._build_service(config_yaml))

    # ---------- KnowledgeRecord ----------

    def _test_record_to_dict_and_from_dict_roundtrip(self) -> None:
        """`to_dict`/`from_dict` roundtrip a record without losing information."""
        record = KnowledgeRecord(key="k", content={"a": 1}, collection="notes", metadata={"tag": "x"})
        data = record.to_dict()
        rebuilt = KnowledgeRecord.from_dict(data)
        self.assert_equal(rebuilt.key, "k")
        self.assert_equal(rebuilt.content, {"a": 1})
        self.assert_equal(rebuilt.collection, "notes")
        self.assert_equal(rebuilt.metadata, {"tag": "x"})
        self.assert_equal(rebuilt.created_at, record.created_at)

    # ---------- KnowledgeCollection ----------

    def _test_collection_store_load(self) -> None:
        """`store`/`load` round-trip a record under (collection, key)."""
        store = KnowledgeCollection()
        record = KnowledgeRecord(key="a", content="hello", collection="notes")
        store.store(record)
        loaded = store.load("notes", "a")
        self.assert_not_none(loaded)
        self.assert_equal(loaded.content, "hello")
        self.assert_true(store.load("notes", "missing") is None)
        self.assert_true(store.load("missing-collection", "a") is None)

    def _test_collection_update_existing_and_missing(self) -> None:
        """`update` modifies an existing record and returns None for a missing one."""
        store = KnowledgeCollection()
        store.store(KnowledgeRecord(key="a", content="v1", collection="notes"))
        updated = store.update("notes", "a", "v2")
        self.assert_not_none(updated)
        self.assert_equal(updated.content, "v2")
        self.assert_equal(store.load("notes", "a").content, "v2")

        missing = store.update("notes", "does-not-exist", "v3")
        self.assert_true(missing is None)

    def _test_collection_delete(self) -> None:
        """`delete` removes an existing record and reports False for a repeat delete."""
        store = KnowledgeCollection()
        store.store(KnowledgeRecord(key="a", content="v1", collection="notes"))
        self.assert_true(store.delete("notes", "a"))
        self.assert_true(store.load("notes", "a") is None)
        self.assert_false(store.delete("notes", "a"))

    def _test_collection_clear_collection_and_all(self) -> None:
        """`clear(collection)` only removes that collection; `clear(None)` removes everything."""
        store = KnowledgeCollection()
        store.store(KnowledgeRecord(key="a", content=1, collection="c1"))
        store.store(KnowledgeRecord(key="b", content=2, collection="c2"))

        removed = store.clear(collection="c1")
        self.assert_equal(removed, 1)
        self.assert_true(store.load("c1", "a") is None)
        self.assert_not_none(store.load("c2", "b"))

        removed_all = store.clear(None)
        self.assert_equal(removed_all, 1)
        self.assert_true(store.load("c2", "b") is None)

    def _test_collection_list_scoped_and_all(self) -> None:
        """`list(collection)` scopes to one collection; `list(None)` spans every collection."""
        store = KnowledgeCollection()
        store.store(KnowledgeRecord(key="a", content=1, collection="c1"))
        store.store(KnowledgeRecord(key="b", content=2, collection="c2"))

        scoped = store.list("c1")
        self.assert_equal([record.key for record in scoped], ["a"])

        everything = store.list()
        self.assert_equal([record.key for record in everything], ["a", "b"])

    def _test_collection_collections_and_stats(self) -> None:
        """`collections()`/`stats()` reflect only non-empty collections."""
        store = KnowledgeCollection()
        store.store(KnowledgeRecord(key="a", content=1, collection="c1"))
        store.store(KnowledgeRecord(key="b", content=2, collection="c1"))
        store.store(KnowledgeRecord(key="c", content=3, collection="c2"))

        self.assert_equal(store.collections(), ["c1", "c2"])

        all_stats = store.stats()
        by_name = {entry.name: entry for entry in all_stats}
        self.assert_equal(by_name["c1"].record_count, 2)
        self.assert_equal(by_name["c2"].record_count, 1)

        scoped_stats = store.stats("c1")
        self.assert_equal(len(scoped_stats), 1)
        self.assert_equal(scoped_stats[0].record_count, 2)

        self.assert_equal(store.stats("does-not-exist"), [])
        self.assert_equal(store.count(), 3)
        self.assert_equal(store.count("c1"), 2)

    # ---------- KnowledgeProvider / KnowledgeCollectionProvider ----------

    def _test_provider_delegates_to_collection_store(self) -> None:
        """`store`/`load`/`update`/`delete` on the provider reach the wrapped KnowledgeCollection."""
        store, provider = self._build_collection_and_provider()
        provider.store("a", "hello", collection="notes")
        self.assert_equal(provider.load("a", collection="notes").content, "hello")
        self.assert_equal(store.load("notes", "a").content, "hello")

        updated = provider.update("a", "world", collection="notes")
        self.assert_equal(updated.content, "world")

        self.assert_true(provider.delete("a", collection="notes"))
        self.assert_true(provider.load("a", collection="notes") is None)
        self.assert_false(provider.delete("a", collection="notes"))

    def _test_provider_preserves_created_at_on_overwrite(self) -> None:
        """Storing under an existing key preserves the original `created_at`."""
        _, provider = self._build_collection_and_provider()
        first = provider.store("a", "v1")
        second = provider.store("a", "v2")
        self.assert_equal(first.created_at, second.created_at)
        self.assert_equal(provider.load("a").content, "v2")

    def _test_provider_is_abstract(self) -> None:
        """`KnowledgeProvider` cannot be instantiated directly."""
        try:
            KnowledgeProvider()  # type: ignore[abstract]
        except TypeError:
            self.result.add_pass()
        else:
            self.assert_true(False, "KnowledgeProvider should not be directly instantiable")

    # ---------- KnowledgeManager: registration ----------

    def _test_register_activates_default_provider(self) -> None:
        """Registering the configured default provider activates it automatically."""
        manager = KnowledgeManager(default_provider="local")
        _, provider = self._build_collection_and_provider()
        manager.register(provider)
        self.assert_equal(manager.active_provider_name(), "local")
        self.assert_true(manager.active_provider() is provider)

    def _test_register_second_provider_does_not_steal_active(self) -> None:
        """A second registered provider never displaces an already-active one."""
        manager = KnowledgeManager(default_provider="local")
        _, first = self._build_collection_and_provider()
        manager.register(first)
        second = _RecordingProvider("secondary")
        manager.register(second)
        self.assert_equal(manager.active_provider_name(), "local")

    def _test_providers_list_sorted(self) -> None:
        """`providers()` returns every registered name, sorted."""
        manager = KnowledgeManager()
        manager.register(_RecordingProvider("zeta"))
        manager.register(_RecordingProvider("alpha"))
        self.assert_equal(manager.providers(), ["alpha", "zeta"])

    def _test_unregister_clears_active_if_active(self) -> None:
        """Unregistering the active provider clears the active selection."""
        manager = KnowledgeManager(default_provider="local")
        _, provider = self._build_collection_and_provider()
        manager.register(provider)
        self.assert_true(manager.unregister("local"))
        self.assert_true(manager.active_provider_name() is None)
        self.assert_equal(manager.providers(), [])

    def _test_unregister_unknown_returns_false(self) -> None:
        """Unregistering an unknown provider name returns False, not an exception."""
        manager = KnowledgeManager()
        self.assert_false(manager.unregister("does-not-exist"))

    # ---------- KnowledgeManager: enable / disable / switch ----------

    def _test_disable_active_clears_active(self) -> None:
        """Disabling the currently active provider clears the active selection."""
        manager = KnowledgeManager(default_provider="local")
        _, provider = self._build_collection_and_provider()
        manager.register(provider)
        self.assert_true(manager.disable("local"))
        self.assert_true(manager.active_provider_name() is None)
        self.assert_false(manager.is_enabled("local"))

    def _test_enable_unknown_returns_false(self) -> None:
        """Enabling an unknown provider name returns False, not an exception."""
        manager = KnowledgeManager()
        self.assert_false(manager.enable("does-not-exist"))

    def _test_use_switches_active_provider(self) -> None:
        """`use()` switches to a different, enabled provider."""
        manager = KnowledgeManager(default_provider="local")
        _, provider = self._build_collection_and_provider()
        manager.register(provider)
        secondary = _RecordingProvider("secondary")
        manager.register(secondary, enabled=True)

        manager.use("secondary")
        self.assert_equal(manager.active_provider_name(), "secondary")
        self.assert_true(manager.active_provider() is secondary)

    def _test_use_unknown_provider_raises(self) -> None:
        """`use()` on an unregistered name raises KnowledgeProviderError."""
        manager = KnowledgeManager()
        try:
            manager.use("nope")
        except KnowledgeProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "use() should raise for an unknown provider")

    def _test_use_disabled_provider_raises(self) -> None:
        """`use()` on a disabled provider raises KnowledgeProviderError."""
        manager = KnowledgeManager(default_provider="local")
        _, provider = self._build_collection_and_provider()
        manager.register(provider, enabled=False)
        try:
            manager.use("local")
        except KnowledgeProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "use() should raise for a disabled provider")

    # ---------- KnowledgeManager: status + unified API ----------

    def _test_status_snapshot(self) -> None:
        """`status()` reports provider count, active provider, and per-provider flags."""
        manager = KnowledgeManager(default_provider="local")
        _, provider = self._build_collection_and_provider()
        manager.register(provider)
        manager.register(_RecordingProvider("secondary"), enabled=False)

        status: ManagerStatus = manager.status()
        self.assert_equal(status.provider_count, 2)
        self.assert_equal(status.active_provider, "local")

        by_name = {entry.name: entry for entry in status.providers}
        self.assert_true(isinstance(by_name["local"], ProviderStatus))
        self.assert_true(by_name["local"].enabled)
        self.assert_true(by_name["local"].active)
        self.assert_false(by_name["secondary"].enabled)
        self.assert_false(by_name["secondary"].active)

    def _test_unified_api_delegates_to_active_provider(self) -> None:
        """KnowledgeManager's store/load/update/delete/clear/list/collections/stats reach the active provider."""
        manager = KnowledgeManager(default_provider="local")
        _, provider = self._build_collection_and_provider()
        manager.register(provider)

        manager.store("k", "v", collection="notes")
        self.assert_equal(manager.load("k", "notes").content, "v")
        self.assert_equal([record.key for record in manager.list("notes")], ["k"])
        self.assert_equal(manager.collections(), ["notes"])
        self.assert_equal(manager.stats("notes")[0].record_count, 1)

        updated = manager.update("k", "v2", "notes")
        self.assert_equal(updated.content, "v2")

        self.assert_true(manager.delete("k", "notes"))

        manager.store("a", 1, collection="notes")
        manager.store("b", 2, collection="notes")
        self.assert_equal(manager.clear("notes"), 2)

    def _test_unified_api_raises_without_active_provider(self) -> None:
        """Every unified-API method raises KnowledgeProviderError with no active provider."""
        manager = KnowledgeManager()
        for operation in (
            lambda: manager.store("k", "v"),
            lambda: manager.load("k"),
            lambda: manager.update("k", "v"),
            lambda: manager.delete("k"),
            lambda: manager.clear(),
            lambda: manager.list(),
            lambda: manager.collections(),
            lambda: manager.stats(),
        ):
            try:
                operation()
            except KnowledgeProviderError:
                self.result.add_pass()
            else:
                self.assert_true(False, "operation should raise without an active provider")

    # ---------- KnowledgeService ----------

    def _test_service_builds_default_manager_and_registers_local_provider(self) -> None:
        """A KnowledgeService built without an explicit manager registers the "local" provider."""
        service = self._build_service()
        status = service.providers_status()
        self.assert_equal(status.provider_count, 1)
        self.assert_equal(status.providers[0].name, "local")
        self.assert_true(status.providers[0].active)

    def _test_service_invalid_default_provider_raises(self) -> None:
        """An empty 'knowledge.default_provider' raises KnowledgeProviderError at construction."""
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), _INVALID_PROVIDER_CONFIG_YAML)
        try:
            KnowledgeService(config=config)
        except KnowledgeProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "empty default_provider should raise KnowledgeProviderError")

    def _test_service_non_string_default_provider_raises(self) -> None:
        """A non-string 'knowledge.default_provider' raises KnowledgeProviderError at construction."""
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(
            Path(tmp_dir.name),
            "knowledge:\n  enabled: true\n  default_provider: 123\n",
        )
        try:
            KnowledgeService(config=config)
        except KnowledgeProviderError:
            self.result.add_pass()
        else:
            self.assert_true(
                False, "non-string default_provider should raise KnowledgeProviderError"
            )

    def _test_service_accepts_injected_manager(self) -> None:
        """A KnowledgeService can be constructed with a pre-built KnowledgeManager (DI)."""
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), _DEFAULT_CONFIG_YAML)
        manager = KnowledgeManager(default_provider="custom")
        manager.register(KnowledgeCollectionProvider(store=KnowledgeCollection(), name="custom"))

        service = KnowledgeService(config=config, manager=manager)
        self.assert_equal(service.providers_status().active_provider, "custom")

    def _test_service_store_load_update_delete(self) -> None:
        """`store`/`load`/`update`/`delete` behave as documented."""
        service = self._build_service()

        result = service.store("key1", "value1", collection="notes")
        self.assert_true(result.success)

        record = service.load("key1", "notes")
        self.assert_not_none(record)
        self.assert_equal(record.content, "value1")

        update_result = service.update("key1", "value2", "notes")
        self.assert_true(update_result.success)
        self.assert_equal(service.load("key1", "notes").content, "value2")

        missing_update = service.update("does-not-exist", "x", "notes")
        self.assert_false(missing_update.success)

        delete_result = service.delete("key1", "notes")
        self.assert_true(delete_result.success)
        self.assert_true(service.load("key1", "notes") is None)

        missing_delete = service.delete("key1", "notes")
        self.assert_false(missing_delete.success)

        empty_key_result = service.store("", "value", collection="notes")
        self.assert_false(empty_key_result.success)

    def _test_service_collections_and_stats(self) -> None:
        """`collection_names`/`collection_stats`/`list_records` reflect stored records."""
        service = self._build_service()
        service.store("a", 1, collection="c1")
        service.store("b", 2, collection="c1")
        service.store("c", 3, collection="c2")

        self.assert_equal(service.collection_names(), ["c1", "c2"])

        stats = service.collection_stats()
        by_name = {entry.name: entry for entry in stats}
        self.assert_equal(by_name["c1"].record_count, 2)
        self.assert_equal(by_name["c2"].record_count, 1)

        self.assert_equal(len(service.list_records("c1")), 2)
        self.assert_equal(len(service.list_records()), 3)

        clear_result = service.clear("c1")
        self.assert_true(clear_result.success)
        self.assert_equal(service.collection_names(), ["c2"])

    def _test_service_status(self) -> None:
        """`status()` reports enabled state, active provider and record/collection counts."""
        service = self._build_service()
        service.store("a", 1, collection="notes")
        status = service.status()
        self.assert_true(status.enabled)
        self.assert_equal(status.active_provider, "local")
        self.assert_equal(status.provider_count, 1)
        self.assert_equal(status.total_records, 1)
        self.assert_equal(status.collection_count, 1)

    def _test_service_disabled_subsystem_rejects_mutations_and_reads(self) -> None:
        """A disabled Knowledge subsystem rejects mutations and returns empty reads."""
        service = self._build_service(_DISABLED_CONFIG_YAML)
        self.assert_false(service.store("k", "v").success)
        self.assert_false(service.update("k", "v").success)
        self.assert_false(service.delete("k").success)
        self.assert_false(service.clear().success)
        self.assert_true(service.load("k") is None)
        self.assert_equal(service.list_records(), [])
        self.assert_equal(service.collection_names(), [])
        self.assert_equal(service.collection_stats(), [])
        self.assert_false(service.status().enabled)

    # ---------- KnowledgeModule (CLI) ----------

    def _test_cli_help_lists_commands(self) -> None:
        """`knowledge help` lists every documented command."""
        module = self._build_module()
        result = module.execute("help", [])
        self.assert_true(result.success)
        for command in (
            "knowledge status",
            "knowledge collections",
            "knowledge list",
            "knowledge info",
            "knowledge clear",
            "knowledge help",
        ):
            self.assert_true(command in result.message, f"missing '{command}' in help text")

    def _test_cli_status_command(self) -> None:
        """`knowledge status` reports the built-in "local" provider as active."""
        module = self._build_module()
        result = module.execute("status", [])
        self.assert_true(result.success)
        self.assert_true("local" in result.message)

    def _test_cli_collections_command(self) -> None:
        """`knowledge collections` lists collections with their record counts."""
        service = self._build_service()
        service.store("a", 1, collection="notes")
        module = KnowledgeModule(service)

        result = module.execute("collections", [])
        self.assert_true(result.success)
        self.assert_true("notes" in result.message)
        self.assert_true("1" in result.message)

    def _test_cli_list_command_scoped_and_all(self) -> None:
        """`knowledge list [collection]` scopes correctly and reports empty state."""
        empty_module = self._build_module()
        empty_result = empty_module.execute("list", [])
        self.assert_true(empty_result.success)
        self.assert_true("(empty)" in empty_result.message)

        service = self._build_service()
        service.store("a", 1, collection="c1")
        service.store("b", 2, collection="c2")
        module = KnowledgeModule(service)

        all_result = module.execute("list", [])
        self.assert_true("c1:a" in all_result.message)
        self.assert_true("c2:b" in all_result.message)

        scoped_result = module.execute("list", ["c1"])
        self.assert_true("c1:a" in scoped_result.message)
        self.assert_false("c2:b" in scoped_result.message)

    def _test_cli_info_command_found_and_missing(self) -> None:
        """`knowledge info <key> [collection]` shows a record or reports it missing."""
        service = self._build_service()
        service.store("a", "hello", collection="notes", metadata={"tag": "x"})
        module = KnowledgeModule(service)

        missing_usage = module.execute("info", [])
        self.assert_false(missing_usage.success)

        found = module.execute("info", ["a", "notes"])
        self.assert_true(found.success)
        self.assert_true("hello" in found.message)
        self.assert_true("notes" in found.message)

        not_found = module.execute("info", ["does-not-exist", "notes"])
        self.assert_false(not_found.success)

    def _test_cli_clear_command(self) -> None:
        """`knowledge clear [collection]` clears one collection or everything."""
        service = self._build_service()
        service.store("a", 1, collection="c1")
        service.store("b", 2, collection="c2")
        module = KnowledgeModule(service)

        result = module.execute("clear", ["c1"])
        self.assert_true(result.success)
        self.assert_equal(service.collection_names(), ["c2"])

        result_all = module.execute("clear", [])
        self.assert_true(result_all.success)
        self.assert_equal(service.collection_names(), [])

    def _test_cli_unknown_action(self) -> None:
        """An unrecognized action returns a failing CommandResult, not an exception."""
        module = self._build_module()
        result = module.execute("bogus-action", [])
        self.assert_false(result.success)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_knowledge_module(self) -> None:
        """A real Bootstrap.run() with valid config registers "knowledge" and activates "local"."""
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            project_root = Path(tmp_dir_name)
            _write_full_bootstrap_config(project_root, default_provider="local")
            with _ChdirGuard(project_root):
                bootstrap = Bootstrap(project_root=project_root)
                orchestrator = bootstrap.initialize()
                try:
                    self.assert_not_none(bootstrap.knowledge_service)
                    self.assert_equal(
                        bootstrap.knowledge_service.providers_status().active_provider, "local"
                    )
                    router = bootstrap.command_router
                    self.assert_true("knowledge" in router.module_names)
                    dispatch_result = router.dispatch("knowledge status")
                    self.assert_true(dispatch_result.success)
                finally:
                    orchestrator.stop()

    def _test_bootstrap_degrades_gracefully_on_invalid_provider_config(self) -> None:
        """Invalid 'knowledge.default_provider' disables Knowledge but the rest of Jarvis still starts."""
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            project_root = Path(tmp_dir_name)
            _write_full_bootstrap_config(project_root, default_provider="")
            with _ChdirGuard(project_root):
                bootstrap = Bootstrap(project_root=project_root)
                orchestrator = bootstrap.initialize()
                try:
                    self.assert_true(bootstrap.knowledge_service is None)
                    router = bootstrap.command_router
                    self.assert_false("knowledge" in router.module_names)
                    # The rest of the application still started successfully.
                    self.assert_true("system" in router.module_names)
                    self.assert_true(orchestrator is not None)
                finally:
                    orchestrator.stop()

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """The Knowledge package never imports Embedding, RAG, Memory, Agent, etc.

        Per EP-024's task brief, Knowledge Base must not import
        Embedding, Retrieval, RAG, Long-Term Memory, Semantic Search,
        Context Compression, Planner, Reflection, Agent Framework,
        Browser Automation, Vector Database, or any future EP.
        """
        forbidden_module_fragments = (
            "memory",
            "long_term_memory",
            "semantic_search",
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
        modules = [knowledge_manager_module, knowledge_provider_module]
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
                        f"{module.__name__} must not import '{imported_name}' "
                        f"(matches forbidden fragment '{forbidden_fragment}')",
                    )

    def _test_no_future_ep_provider_classes(self) -> None:
        """Only `KnowledgeCollectionProvider` is a concrete provider; no future EP providers exist.

        EP-024 must implement only the abstraction (`KnowledgeProvider`)
        and the adapter around `KnowledgeCollection`
        (`KnowledgeCollectionProvider`) -- not LongTermMemoryProvider,
        SemanticSearchProvider, ExternalProvider, or VectorStoreProvider,
        which are explicitly future work.
        """
        forbidden_class_names = (
            "LongTermMemoryProvider",
            "SemanticSearchProvider",
            "ExternalProvider",
            "VectorStoreProvider",
        )
        module_source = inspect.getsource(knowledge_provider_module)
        for class_name in forbidden_class_names:
            self.assert_true(
                f"class {class_name}" not in module_source,
                f"{class_name} must not be implemented in EP-024",
            )

    def _test_manager_owns_no_storage_state(self) -> None:
        """KnowledgeManager keeps no record data itself -- only provider registration state.

        Confirmed structurally: KnowledgeManager's __init__ only tracks
        dictionaries of provider *references* and enabled flags, never
        a dict of stored records/collections.
        """
        manager = KnowledgeManager()
        instance_attrs = vars(manager)
        forbidden_attr_names = ("records", "values", "data", "collections")
        for attr_name in instance_attrs:
            for forbidden in forbidden_attr_names:
                self.assert_true(
                    forbidden not in attr_name.lower(),
                    f"KnowledgeManager should not own storage state ('{attr_name}')",
                )

    def _test_exception_hierarchy(self) -> None:
        """KnowledgeProviderError is a plain Exception, catchable on its own."""
        self.assert_true(issubclass(KnowledgeProviderError, Exception))
        try:
            raise KnowledgeProviderError("boom")
        except KnowledgeProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "KnowledgeProviderError should be catchable directly")
