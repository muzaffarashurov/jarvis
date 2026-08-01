"""Real engineering tests for EP-025 - Long-Term Memory.

Builds real `LongTermRecord`/`LongTermProvider`/`LongTermMemoryManager`/
`LongTermMemoryService`/`LongTermMemoryModule` instances -- composed
with real `KnowledgeService` (EP-024) and `MemoryService` (EP-023)
instances loaded from a temporary `Config` -- and drives them exactly
as a caller would, no mocked internals, matching every other EP's test
suite in this project.

Long-Term Memory (EP-025) is a new, independent package
(`src/core/long_term_memory/`) that persists memories through EP-024's
`KnowledgeService` public API (a dedicated "long_term_memory"
collection) and extends EP-023's Memory Manager through
`MemoryService.register_provider` -- never touching either
subsystem's internals. This suite covers:

1. The domain model: `LongTermRecord`.
2. The provider abstraction: `LongTermProvider`,
   `KnowledgeBackedLongTermProvider` (Knowledge-Base-backed
   persistence), `LongTermMemoryProvider` (the EP-023 MemoryProvider
   adapter).
3. `LongTermMemoryManager`: registration, enable/disable,
   active-provider switching, status, and the unified
   store/get/update/archive/delete/clear/list/stats API.
4. `LongTermMemoryService`/`LongTermMemoryModule`: configuration-driven
   construction, Memory Manager integration (best-effort), graceful
   degradation, and every CLI command ("status", "list", "info",
   "archive", "clear", "statistics", "help").
5. Architecture compliance: no forbidden imports, no duplicated
   storage/provider logic, no future-EP functionality, and a real
   `Bootstrap` run proving normal wiring, EP-023/EP-024 integration,
   and graceful degradation on invalid configuration (both for
   Long-Term Memory itself and for its hard dependency, Knowledge Base).
"""

from __future__ import annotations

import ast
import inspect
import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.config import Config
from src.core.long_term_memory import (
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    KnowledgeBackedLongTermProvider,
    LongTermManagerStatus,
    LongTermMemoryManager,
    LongTermMemoryProvider,
    LongTermProvider,
    LongTermProviderError,
    LongTermProviderStatus,
    LongTermRecord,
)
from src.core.long_term_memory import long_term_manager as long_term_manager_module
from src.core.long_term_memory import long_term_provider as long_term_provider_module
from src.core.memory.memory_provider import MemoryProvider
from src.core.memory.memory_store import MemoryStore
from src.modules.long_term_memory_module import LongTermMemoryModule
from src.services.knowledge_service import KnowledgeService
from src.services.long_term_memory_service import LongTermMemoryService
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


def _write_config(directory: Path, config_yaml: str) -> Config:
    """Write a minimal, self-contained config.yaml and load it."""
    config_path = directory / "config.yaml"
    config_path.write_text(config_yaml, encoding="utf-8")
    return Config(config_path).load()


_KNOWLEDGE_ONLY_YAML = (
    "knowledge:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n"
)

_DEFAULT_LTM_YAML = (
    "knowledge:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n"
    "long_term_memory:\n"
    "  enabled: true\n"
    "  default_provider: \"knowledge\"\n"
)

_DISABLED_LTM_YAML = (
    "knowledge:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n"
    "long_term_memory:\n"
    "  enabled: false\n"
    "  default_provider: \"knowledge\"\n"
)

_INVALID_PROVIDER_LTM_YAML = (
    "knowledge:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n"
    "long_term_memory:\n"
    "  enabled: true\n"
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
    "  enabled: {memory_enabled}\n"
    "  persistent: false\n"
    "  auto_save: false\n"
    "  max_entries: 10000\n"
    "  default_ttl: null\n"
    "  default_provider: \"memory\"\n\n"
    "knowledge:\n"
    "  enabled: {knowledge_enabled}\n"
    "  default_provider: \"{knowledge_default_provider}\"\n\n"
    "long_term_memory:\n"
    "  enabled: true\n"
    "  default_provider: \"{ltm_default_provider}\"\n\n"
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


def _write_full_bootstrap_config(
    directory: Path,
    knowledge_default_provider: str = "local",
    ltm_default_provider: str = "knowledge",
    memory_enabled: bool = True,
    knowledge_enabled: bool = True,
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            knowledge_default_provider=knowledge_default_provider,
            ltm_default_provider=ltm_default_provider,
            memory_enabled=str(memory_enabled).lower(),
            knowledge_enabled=str(knowledge_enabled).lower(),
        ),
        encoding="utf-8",
    )


class _RecordingLongTermProvider(LongTermProvider):
    """A minimal, independent LongTermProvider used only to test LongTermMemoryManager.

    Stores records in a plain dict, entirely separate from
    KnowledgeBackedLongTermProvider, so tests can prove
    LongTermMemoryManager truly delegates to whichever provider is
    active rather than always reading the built-in one.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._data: dict[str, LongTermRecord] = {}

    @property
    def name(self) -> str:
        return self._name

    def store(self, memory_id, content, metadata=None) -> LongTermRecord:
        record = LongTermRecord(id=memory_id, content=content, metadata=metadata or {})
        self._data[memory_id] = record
        return record

    def get(self, memory_id):
        return self._data.get(memory_id)

    def update(self, memory_id, content=None, metadata=None):
        existing = self._data.get(memory_id)
        if existing is None:
            return None
        updated = LongTermRecord(
            id=memory_id,
            content=content if content is not None else existing.content,
            metadata=metadata if metadata is not None else existing.metadata,
            status=existing.status,
            created_at=existing.created_at,
            archived_at=existing.archived_at,
        )
        self._data[memory_id] = updated
        return updated

    def archive(self, memory_id):
        existing = self._data.get(memory_id)
        if existing is None:
            return None
        from src.core.long_term_memory.long_term_record import utc_now

        archived = LongTermRecord(
            id=memory_id,
            content=existing.content,
            metadata=existing.metadata,
            status=STATUS_ARCHIVED,
            created_at=existing.created_at,
            archived_at=utc_now(),
        )
        self._data[memory_id] = archived
        return archived

    def delete(self, memory_id) -> bool:
        if memory_id not in self._data:
            return False
        del self._data[memory_id]
        return True

    def clear(self) -> int:
        count = len(self._data)
        self._data.clear()
        return count

    def list(self, status=None):
        records = list(self._data.values())
        if status is not None:
            records = [record for record in records if record.status == status]
        return sorted(records, key=lambda record: record.id)

    def stats(self):
        from src.core.long_term_memory.long_term_provider import LongTermStats

        records = self.list()
        active = sum(1 for record in records if record.status == STATUS_ACTIVE)
        archived = sum(1 for record in records if record.status == STATUS_ARCHIVED)
        return LongTermStats(total=len(records), active=active, archived=archived)


@TestRegistry.register
class LongTermMemoryTest(BaseTest):
    """Real tests covering EP-025's Long-Term Memory."""

    NAME = "EP025"

    def run(self):
        """Execute every Long-Term Memory check and return the aggregated result."""
        # LongTermRecord
        self._test_record_to_dict_and_from_dict_roundtrip()
        self._test_record_from_dict_with_no_archived_at()

        # KnowledgeBackedLongTermProvider (integration with EP-024)
        self._test_knowledge_backed_provider_store_get()
        self._test_knowledge_backed_provider_update_preserves_status()
        self._test_knowledge_backed_provider_archive()
        self._test_knowledge_backed_provider_delete()
        self._test_knowledge_backed_provider_clear()
        self._test_knowledge_backed_provider_list_filtered_by_status()
        self._test_knowledge_backed_provider_stats()
        self._test_knowledge_backed_provider_uses_dedicated_collection()

        # LongTermProvider abstract contract
        self._test_provider_is_abstract()

        # LongTermMemoryManager
        self._test_register_activates_default_provider()
        self._test_register_second_provider_does_not_steal_active()
        self._test_providers_list_sorted()
        self._test_unregister_clears_active_if_active()
        self._test_unregister_unknown_returns_false()
        self._test_disable_active_clears_active()
        self._test_enable_unknown_returns_false()
        self._test_use_switches_active_provider()
        self._test_use_unknown_provider_raises()
        self._test_use_disabled_provider_raises()
        self._test_status_snapshot()
        self._test_unified_api_delegates_to_active_provider()
        self._test_unified_api_raises_without_active_provider()

        # LongTermMemoryProvider (EP-023 MemoryProvider adapter, integration with EP-023)
        self._test_memory_provider_adapter_store_load_delete()
        self._test_memory_provider_adapter_clear_and_list()
        self._test_memory_provider_adapter_is_memory_provider()

        # LongTermMemoryService
        self._test_service_builds_default_manager_and_registers_knowledge_provider()
        self._test_service_invalid_default_provider_raises()
        self._test_service_accepts_injected_manager()
        self._test_service_registers_with_memory_manager_when_provided()
        self._test_service_memory_manager_integration_is_best_effort()
        self._test_service_without_memory_service_still_works()
        self._test_service_store_get_update_archive_delete()
        self._test_service_clear_and_list_memories()
        self._test_service_stats_and_status()
        self._test_service_disabled_subsystem_rejects_mutations_and_reads()

        # LongTermMemoryModule (CLI)
        self._test_cli_help_lists_commands()
        self._test_cli_status_command()
        self._test_cli_list_command_scoped_and_all()
        self._test_cli_info_command_found_and_missing()
        self._test_cli_archive_command()
        self._test_cli_clear_command()
        self._test_cli_statistics_command()
        self._test_cli_unknown_action()

        # Bootstrap wiring (dependency injection + integration + graceful degradation)
        self._test_bootstrap_registers_ltm_module_and_integrates_memory_manager()
        self._test_bootstrap_degrades_gracefully_on_invalid_ltm_config()
        self._test_bootstrap_degrades_when_knowledge_base_unavailable()

        # Architectural acceptance criteria
        self._test_no_forbidden_imports()
        self._test_manager_owns_no_storage_state()
        self._test_exception_hierarchy()
        self._test_only_expected_provider_classes_exist()

        return self.result

    # ---------- Helpers ----------

    def _build_knowledge_service(self, yaml_text: str = _KNOWLEDGE_ONLY_YAML) -> KnowledgeService:
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), yaml_text)
        service = KnowledgeService(config=config)
        service._test_tmp_dir = tmp_dir  # type: ignore[attr-defined]
        return service

    def _build_memory_service(self) -> MemoryService:
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), "memory:\n  enabled: true\n")
        service = MemoryService(config=config, store=MemoryStore())
        service._test_tmp_dir = tmp_dir  # type: ignore[attr-defined]
        return service

    def _build_knowledge_backed_provider(
        self, collection: str = "long_term_memory"
    ) -> KnowledgeBackedLongTermProvider:
        knowledge_service = self._build_knowledge_service()
        return KnowledgeBackedLongTermProvider(knowledge_service, collection=collection)

    def _build_service(
        self,
        config_yaml: str = _DEFAULT_LTM_YAML,
        with_memory_service: bool = False,
    ) -> LongTermMemoryService:
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), config_yaml)
        knowledge_service = KnowledgeService(config=config)
        memory_service = self._build_memory_service() if with_memory_service else None
        service = LongTermMemoryService(
            config=config, knowledge_service=knowledge_service, memory_service=memory_service
        )
        service._test_tmp_dir = tmp_dir  # type: ignore[attr-defined]
        return service

    def _build_module(self, config_yaml: str = _DEFAULT_LTM_YAML) -> LongTermMemoryModule:
        return LongTermMemoryModule(self._build_service(config_yaml))

    # ---------- LongTermRecord ----------

    def _test_record_to_dict_and_from_dict_roundtrip(self) -> None:
        """`to_dict`/`from_dict` roundtrip a record without losing information."""
        record = LongTermRecord(
            id="mem-1", content={"a": 1}, metadata={"tag": "x"}, status=STATUS_ARCHIVED
        )
        record.archived_at = record.updated_at
        data = record.to_dict()
        rebuilt = LongTermRecord.from_dict(data)
        self.assert_equal(rebuilt.id, "mem-1")
        self.assert_equal(rebuilt.content, {"a": 1})
        self.assert_equal(rebuilt.metadata, {"tag": "x"})
        self.assert_equal(rebuilt.status, STATUS_ARCHIVED)
        self.assert_equal(rebuilt.created_at, record.created_at)
        self.assert_equal(rebuilt.archived_at, record.archived_at)

    def _test_record_from_dict_with_no_archived_at(self) -> None:
        """`from_dict` tolerates a missing/None 'archived_at'."""
        record = LongTermRecord(id="mem-2", content="hello")
        data = record.to_dict()
        rebuilt = LongTermRecord.from_dict(data)
        self.assert_true(rebuilt.archived_at is None)
        self.assert_equal(rebuilt.status, STATUS_ACTIVE)

    # ---------- KnowledgeBackedLongTermProvider ----------

    def _test_knowledge_backed_provider_store_get(self) -> None:
        """`store`/`get` round-trip a memory through KnowledgeService."""
        provider = self._build_knowledge_backed_provider()
        stored = provider.store("mem-1", "hello", metadata={"tag": "x"})
        self.assert_equal(stored.status, STATUS_ACTIVE)
        self.assert_equal(stored.metadata, {"tag": "x"})

        loaded = provider.get("mem-1")
        self.assert_not_none(loaded)
        self.assert_equal(loaded.content, "hello")
        self.assert_equal(loaded.metadata, {"tag": "x"})
        self.assert_true(provider.get("does-not-exist") is None)

    def _test_knowledge_backed_provider_update_preserves_status(self) -> None:
        """`update` changes content/metadata but never the lifecycle status."""
        provider = self._build_knowledge_backed_provider()
        provider.store("mem-1", "v1")
        provider.archive("mem-1")

        updated = provider.update("mem-1", content="v2")
        self.assert_not_none(updated)
        self.assert_equal(updated.content, "v2")
        self.assert_equal(updated.status, STATUS_ARCHIVED)

        missing = provider.update("does-not-exist", content="x")
        self.assert_true(missing is None)

    def _test_knowledge_backed_provider_archive(self) -> None:
        """`archive` transitions status and sets `archived_at`."""
        provider = self._build_knowledge_backed_provider()
        provider.store("mem-1", "v1")
        archived = provider.archive("mem-1")
        self.assert_not_none(archived)
        self.assert_equal(archived.status, STATUS_ARCHIVED)
        self.assert_not_none(archived.archived_at)

        reloaded = provider.get("mem-1")
        self.assert_equal(reloaded.status, STATUS_ARCHIVED)

        missing = provider.archive("does-not-exist")
        self.assert_true(missing is None)

    def _test_knowledge_backed_provider_delete(self) -> None:
        """`delete` permanently removes a memory."""
        provider = self._build_knowledge_backed_provider()
        provider.store("mem-1", "v1")
        self.assert_true(provider.delete("mem-1"))
        self.assert_true(provider.get("mem-1") is None)
        self.assert_false(provider.delete("mem-1"))

    def _test_knowledge_backed_provider_clear(self) -> None:
        """`clear` removes every memory and returns the count removed."""
        provider = self._build_knowledge_backed_provider()
        provider.store("mem-1", "v1")
        provider.store("mem-2", "v2")
        removed = provider.clear()
        self.assert_equal(removed, 2)
        self.assert_equal(len(provider.list()), 0)

    def _test_knowledge_backed_provider_list_filtered_by_status(self) -> None:
        """`list(status=...)` scopes to active or archived memories."""
        provider = self._build_knowledge_backed_provider()
        provider.store("mem-1", "v1")
        provider.store("mem-2", "v2")
        provider.archive("mem-2")

        active_only = provider.list(status=STATUS_ACTIVE)
        self.assert_equal([record.id for record in active_only], ["mem-1"])

        archived_only = provider.list(status=STATUS_ARCHIVED)
        self.assert_equal([record.id for record in archived_only], ["mem-2"])

        everything = provider.list()
        self.assert_equal([record.id for record in everything], ["mem-1", "mem-2"])

    def _test_knowledge_backed_provider_stats(self) -> None:
        """`stats()` reports correct active/archived/total counts."""
        provider = self._build_knowledge_backed_provider()
        provider.store("mem-1", "v1")
        provider.store("mem-2", "v2")
        provider.store("mem-3", "v3")
        provider.archive("mem-2")

        stats = provider.stats()
        self.assert_equal(stats.total, 3)
        self.assert_equal(stats.active, 2)
        self.assert_equal(stats.archived, 1)

    def _test_knowledge_backed_provider_uses_dedicated_collection(self) -> None:
        """The provider stores memories in Knowledge Base under its configured collection."""
        knowledge_service = self._build_knowledge_service()
        provider = KnowledgeBackedLongTermProvider(knowledge_service, collection="custom_ltm")
        provider.store("mem-1", "v1")

        self.assert_equal(knowledge_service.collection_names(), ["custom_ltm"])
        record = knowledge_service.load("mem-1", "custom_ltm")
        self.assert_not_none(record)

    # ---------- LongTermProvider abstract contract ----------

    def _test_provider_is_abstract(self) -> None:
        """`LongTermProvider` cannot be instantiated directly."""
        try:
            LongTermProvider()  # type: ignore[abstract]
        except TypeError:
            self.result.add_pass()
        else:
            self.assert_true(False, "LongTermProvider should not be directly instantiable")

    # ---------- LongTermMemoryManager ----------

    def _test_register_activates_default_provider(self) -> None:
        """Registering the configured default provider activates it automatically."""
        manager = LongTermMemoryManager(default_provider="knowledge")
        provider = self._build_knowledge_backed_provider()
        manager.register(provider)
        self.assert_equal(manager.active_provider_name(), "knowledge")
        self.assert_true(manager.active_provider() is provider)

    def _test_register_second_provider_does_not_steal_active(self) -> None:
        """A second registered provider never displaces an already-active one."""
        manager = LongTermMemoryManager(default_provider="knowledge")
        manager.register(self._build_knowledge_backed_provider())
        manager.register(_RecordingLongTermProvider("secondary"))
        self.assert_equal(manager.active_provider_name(), "knowledge")

    def _test_providers_list_sorted(self) -> None:
        """`providers()` returns every registered name, sorted."""
        manager = LongTermMemoryManager()
        manager.register(_RecordingLongTermProvider("zeta"))
        manager.register(_RecordingLongTermProvider("alpha"))
        self.assert_equal(manager.providers(), ["alpha", "zeta"])

    def _test_unregister_clears_active_if_active(self) -> None:
        """Unregistering the active provider clears the active selection."""
        manager = LongTermMemoryManager(default_provider="knowledge")
        manager.register(self._build_knowledge_backed_provider())
        self.assert_true(manager.unregister("knowledge"))
        self.assert_true(manager.active_provider_name() is None)
        self.assert_equal(manager.providers(), [])

    def _test_unregister_unknown_returns_false(self) -> None:
        """Unregistering an unknown provider name returns False, not an exception."""
        manager = LongTermMemoryManager()
        self.assert_false(manager.unregister("does-not-exist"))

    def _test_disable_active_clears_active(self) -> None:
        """Disabling the currently active provider clears the active selection."""
        manager = LongTermMemoryManager(default_provider="knowledge")
        manager.register(self._build_knowledge_backed_provider())
        self.assert_true(manager.disable("knowledge"))
        self.assert_true(manager.active_provider_name() is None)
        self.assert_false(manager.is_enabled("knowledge"))

    def _test_enable_unknown_returns_false(self) -> None:
        """Enabling an unknown provider name returns False, not an exception."""
        manager = LongTermMemoryManager()
        self.assert_false(manager.enable("does-not-exist"))

    def _test_use_switches_active_provider(self) -> None:
        """`use()` switches to a different, enabled provider."""
        manager = LongTermMemoryManager(default_provider="knowledge")
        manager.register(self._build_knowledge_backed_provider())
        secondary = _RecordingLongTermProvider("secondary")
        manager.register(secondary, enabled=True)

        manager.use("secondary")
        self.assert_equal(manager.active_provider_name(), "secondary")
        self.assert_true(manager.active_provider() is secondary)

    def _test_use_unknown_provider_raises(self) -> None:
        """`use()` on an unregistered name raises LongTermProviderError."""
        manager = LongTermMemoryManager()
        try:
            manager.use("nope")
        except LongTermProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "use() should raise for an unknown provider")

    def _test_use_disabled_provider_raises(self) -> None:
        """`use()` on a disabled provider raises LongTermProviderError."""
        manager = LongTermMemoryManager(default_provider="knowledge")
        manager.register(self._build_knowledge_backed_provider(), enabled=False)
        try:
            manager.use("knowledge")
        except LongTermProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "use() should raise for a disabled provider")

    def _test_status_snapshot(self) -> None:
        """`status()` reports provider count, active provider, and per-provider flags."""
        manager = LongTermMemoryManager(default_provider="knowledge")
        manager.register(self._build_knowledge_backed_provider())
        manager.register(_RecordingLongTermProvider("secondary"), enabled=False)

        status: LongTermManagerStatus = manager.status()
        self.assert_equal(status.provider_count, 2)
        self.assert_equal(status.active_provider, "knowledge")

        by_name = {entry.name: entry for entry in status.providers}
        self.assert_true(isinstance(by_name["knowledge"], LongTermProviderStatus))
        self.assert_true(by_name["knowledge"].enabled)
        self.assert_true(by_name["knowledge"].active)
        self.assert_false(by_name["secondary"].enabled)
        self.assert_false(by_name["secondary"].active)

    def _test_unified_api_delegates_to_active_provider(self) -> None:
        """Manager's store/get/update/archive/delete/clear/list/stats reach the active provider."""
        manager = LongTermMemoryManager(default_provider="knowledge")
        manager.register(self._build_knowledge_backed_provider())

        manager.store("mem-1", "v1")
        self.assert_equal(manager.get("mem-1").content, "v1")
        self.assert_equal([record.id for record in manager.list()], ["mem-1"])
        self.assert_equal(manager.stats().total, 1)

        updated = manager.update("mem-1", content="v2")
        self.assert_equal(updated.content, "v2")

        archived = manager.archive("mem-1")
        self.assert_equal(archived.status, STATUS_ARCHIVED)

        self.assert_true(manager.delete("mem-1"))

        manager.store("a", 1)
        manager.store("b", 2)
        self.assert_equal(manager.clear(), 2)

    def _test_unified_api_raises_without_active_provider(self) -> None:
        """Every unified-API method raises LongTermProviderError with no active provider."""
        manager = LongTermMemoryManager()
        for operation in (
            lambda: manager.store("k", "v"),
            lambda: manager.get("k"),
            lambda: manager.update("k", content="v"),
            lambda: manager.archive("k"),
            lambda: manager.delete("k"),
            lambda: manager.clear(),
            lambda: manager.list(),
            lambda: manager.stats(),
        ):
            try:
                operation()
            except LongTermProviderError:
                self.result.add_pass()
            else:
                self.assert_true(False, "operation should raise without an active provider")

    # ---------- LongTermMemoryProvider (EP-023 MemoryProvider adapter) ----------

    def _test_memory_provider_adapter_store_load_delete(self) -> None:
        """LongTermMemoryProvider.store/load/delete reach the wrapped LongTermMemoryManager."""
        manager = LongTermMemoryManager(default_provider="knowledge")
        manager.register(self._build_knowledge_backed_provider())
        adapter = LongTermMemoryProvider(manager)

        adapter.store("k1", "hello")
        self.assert_equal(adapter.load("k1"), "hello")
        self.assert_true(adapter.exists("k1"))
        self.assert_true(adapter.delete("k1"))
        self.assert_true(adapter.load("k1") is None)
        self.assert_false(adapter.exists("k1"))

    def _test_memory_provider_adapter_clear_and_list(self) -> None:
        """LongTermMemoryProvider.clear/list ignore `namespace` and reach the whole store."""
        manager = LongTermMemoryManager(default_provider="knowledge")
        manager.register(self._build_knowledge_backed_provider())
        adapter = LongTermMemoryProvider(manager)

        adapter.store("k1", "v1", namespace="ignored-a")
        adapter.store("k2", "v2", namespace="ignored-b")
        self.assert_equal(sorted(adapter.list()), ["k1", "k2"])
        self.assert_equal(adapter.clear(namespace="ignored-a"), 2)
        self.assert_equal(adapter.list(), [])

    def _test_memory_provider_adapter_is_memory_provider(self) -> None:
        """LongTermMemoryProvider satisfies EP-023's MemoryProvider interface."""
        manager = LongTermMemoryManager(default_provider="knowledge")
        manager.register(self._build_knowledge_backed_provider())
        adapter = LongTermMemoryProvider(manager, name="long_term")
        self.assert_true(isinstance(adapter, MemoryProvider))
        self.assert_equal(adapter.name, "long_term")

    # ---------- LongTermMemoryService ----------

    def _test_service_builds_default_manager_and_registers_knowledge_provider(self) -> None:
        """A LongTermMemoryService built without an explicit manager registers "knowledge"."""
        service = self._build_service()
        status = service.providers_status()
        self.assert_equal(status.provider_count, 1)
        self.assert_equal(status.providers[0].name, "knowledge")
        self.assert_true(status.providers[0].active)

    def _test_service_invalid_default_provider_raises(self) -> None:
        """An empty 'long_term_memory.default_provider' raises LongTermProviderError."""
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), _INVALID_PROVIDER_LTM_YAML)
        knowledge_service = KnowledgeService(config=config)
        try:
            LongTermMemoryService(config=config, knowledge_service=knowledge_service)
        except LongTermProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "empty default_provider should raise LongTermProviderError")

    def _test_service_accepts_injected_manager(self) -> None:
        """A LongTermMemoryService can be constructed with a pre-built LongTermMemoryManager (DI)."""
        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), _DEFAULT_LTM_YAML)
        knowledge_service = KnowledgeService(config=config)
        manager = LongTermMemoryManager(default_provider="custom")
        manager.register(
            KnowledgeBackedLongTermProvider(knowledge_service, collection="c", name="custom")
        )

        service = LongTermMemoryService(
            config=config, knowledge_service=knowledge_service, manager=manager
        )
        self.assert_equal(service.providers_status().active_provider, "custom")

    def _test_service_registers_with_memory_manager_when_provided(self) -> None:
        """Providing a MemoryService causes registration as a "long_term" MemoryProvider."""
        service = self._build_service(with_memory_service=True)
        self.assert_true(service.status().memory_manager_integrated)

    def _test_service_memory_manager_integration_is_best_effort(self) -> None:
        """A MemoryService whose `register_provider` raises never breaks LongTermMemoryService."""

        class _ExplodingMemoryService:
            def register_provider(self, provider, enabled=True):
                raise RuntimeError("boom")

        tmp_dir = tempfile.TemporaryDirectory()
        config = _write_config(Path(tmp_dir.name), _DEFAULT_LTM_YAML)
        knowledge_service = KnowledgeService(config=config)
        service = LongTermMemoryService(
            config=config,
            knowledge_service=knowledge_service,
            memory_service=_ExplodingMemoryService(),  # type: ignore[arg-type]
        )
        self.assert_false(service.status().memory_manager_integrated)
        # The subsystem itself still works despite the failed integration.
        self.assert_true(service.store("mem-1", "v1").success)

    def _test_service_without_memory_service_still_works(self) -> None:
        """Omitting `memory_service` entirely leaves `memory_manager_integrated` False."""
        service = self._build_service(with_memory_service=False)
        self.assert_false(service.status().memory_manager_integrated)
        self.assert_true(service.store("mem-1", "v1").success)

    def _test_service_store_get_update_archive_delete(self) -> None:
        """`store`/`get`/`update`/`archive`/`delete` behave as documented."""
        service = self._build_service()

        store_result = service.store("mem-1", "v1", metadata={"tag": "x"})
        self.assert_true(store_result.success)

        record = service.get("mem-1")
        self.assert_not_none(record)
        self.assert_equal(record.content, "v1")
        self.assert_equal(record.status, STATUS_ACTIVE)

        update_result = service.update("mem-1", content="v2")
        self.assert_true(update_result.success)
        self.assert_equal(service.get("mem-1").content, "v2")

        missing_update = service.update("does-not-exist", content="x")
        self.assert_false(missing_update.success)

        archive_result = service.archive("mem-1")
        self.assert_true(archive_result.success)
        self.assert_equal(service.get("mem-1").status, STATUS_ARCHIVED)

        missing_archive = service.archive("does-not-exist")
        self.assert_false(missing_archive.success)

        delete_result = service.delete("mem-1")
        self.assert_true(delete_result.success)
        self.assert_true(service.get("mem-1") is None)

        missing_delete = service.delete("mem-1")
        self.assert_false(missing_delete.success)

        empty_id_result = service.store("", "value")
        self.assert_false(empty_id_result.success)

    def _test_service_clear_and_list_memories(self) -> None:
        """`clear`/`list_memories` behave as documented, including status filtering."""
        service = self._build_service()
        service.store("mem-1", "v1")
        service.store("mem-2", "v2")
        service.archive("mem-2")

        self.assert_equal(len(service.list_memories()), 2)
        self.assert_equal(
            [record.id for record in service.list_memories(STATUS_ACTIVE)], ["mem-1"]
        )
        self.assert_equal(
            [record.id for record in service.list_memories(STATUS_ARCHIVED)], ["mem-2"]
        )

        clear_result = service.clear()
        self.assert_true(clear_result.success)
        self.assert_equal(service.list_memories(), [])

    def _test_service_stats_and_status(self) -> None:
        """`stats()`/`status()` reflect stored memories accurately."""
        service = self._build_service()
        service.store("mem-1", "v1")
        service.store("mem-2", "v2")
        service.archive("mem-2")

        stats = service.stats()
        self.assert_equal(stats.total, 2)
        self.assert_equal(stats.active, 1)
        self.assert_equal(stats.archived, 1)

        status = service.status()
        self.assert_true(status.enabled)
        self.assert_equal(status.active_provider, "knowledge")
        self.assert_equal(status.provider_count, 1)
        self.assert_equal(status.total, 2)
        self.assert_equal(status.active, 1)
        self.assert_equal(status.archived, 1)

    def _test_service_disabled_subsystem_rejects_mutations_and_reads(self) -> None:
        """A disabled Long-Term Memory subsystem rejects mutations and returns empty reads."""
        service = self._build_service(_DISABLED_LTM_YAML)
        self.assert_false(service.store("k", "v").success)
        self.assert_false(service.update("k", content="v").success)
        self.assert_false(service.archive("k").success)
        self.assert_false(service.delete("k").success)
        self.assert_false(service.clear().success)
        self.assert_true(service.get("k") is None)
        self.assert_equal(service.list_memories(), [])
        stats = service.stats()
        self.assert_equal(stats.total, 0)
        self.assert_false(service.status().enabled)

    # ---------- LongTermMemoryModule (CLI) ----------

    def _test_cli_help_lists_commands(self) -> None:
        """`ltm help` lists every documented command."""
        module = self._build_module()
        result = module.execute("help", [])
        self.assert_true(result.success)
        for command in (
            "ltm status",
            "ltm list",
            "ltm info",
            "ltm archive",
            "ltm clear",
            "ltm statistics",
            "ltm help",
        ):
            self.assert_true(command in result.message, f"missing '{command}' in help text")

    def _test_cli_status_command(self) -> None:
        """`ltm status` reports the built-in "knowledge" provider as active."""
        module = self._build_module()
        result = module.execute("status", [])
        self.assert_true(result.success)
        self.assert_true("knowledge" in result.message)

    def _test_cli_list_command_scoped_and_all(self) -> None:
        """`ltm list [status]` scopes correctly and reports empty state."""
        empty_module = self._build_module()
        empty_result = empty_module.execute("list", [])
        self.assert_true(empty_result.success)
        self.assert_true("(empty)" in empty_result.message)

        service = self._build_service()
        service.store("mem-1", "v1")
        service.store("mem-2", "v2")
        service.archive("mem-2")
        module = LongTermMemoryModule(service)

        all_result = module.execute("list", [])
        self.assert_true("mem-1" in all_result.message)
        self.assert_true("mem-2" in all_result.message)

        scoped_result = module.execute("list", [STATUS_ARCHIVED])
        self.assert_true("mem-2" in scoped_result.message)
        self.assert_false("mem-1" in scoped_result.message)

    def _test_cli_info_command_found_and_missing(self) -> None:
        """`ltm info <id>` shows a memory or reports it missing."""
        service = self._build_service()
        service.store("mem-1", "hello", metadata={"tag": "x"})
        module = LongTermMemoryModule(service)

        missing_usage = module.execute("info", [])
        self.assert_false(missing_usage.success)

        found = module.execute("info", ["mem-1"])
        self.assert_true(found.success)
        self.assert_true("hello" in found.message)
        self.assert_true("active" in found.message)

        not_found = module.execute("info", ["does-not-exist"])
        self.assert_false(not_found.success)

    def _test_cli_archive_command(self) -> None:
        """`ltm archive <id>` archives a memory."""
        service = self._build_service()
        service.store("mem-1", "v1")
        module = LongTermMemoryModule(service)

        missing_usage = module.execute("archive", [])
        self.assert_false(missing_usage.success)

        result = module.execute("archive", ["mem-1"])
        self.assert_true(result.success)
        self.assert_equal(service.get("mem-1").status, STATUS_ARCHIVED)

    def _test_cli_clear_command(self) -> None:
        """`ltm clear` clears every memory."""
        service = self._build_service()
        service.store("mem-1", "v1")
        service.store("mem-2", "v2")
        module = LongTermMemoryModule(service)

        result = module.execute("clear", [])
        self.assert_true(result.success)
        self.assert_equal(service.list_memories(), [])

    def _test_cli_statistics_command(self) -> None:
        """`ltm statistics` reports total/active/archived counts."""
        service = self._build_service()
        service.store("mem-1", "v1")
        service.store("mem-2", "v2")
        service.archive("mem-2")
        module = LongTermMemoryModule(service)

        result = module.execute("statistics", [])
        self.assert_true(result.success)
        self.assert_true("Total" in result.message)
        self.assert_true("Active" in result.message)
        self.assert_true("Archived" in result.message)

    def _test_cli_unknown_action(self) -> None:
        """An unrecognized action returns a failing CommandResult, not an exception."""
        module = self._build_module()
        result = module.execute("bogus-action", [])
        self.assert_false(result.success)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_ltm_module_and_integrates_memory_manager(self) -> None:
        """A real Bootstrap.run() wires "ltm", persists via Knowledge Base, and extends Memory Manager."""
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            project_root = Path(tmp_dir_name)
            _write_full_bootstrap_config(project_root)
            with _ChdirGuard(project_root):
                bootstrap = Bootstrap(project_root=project_root)
                orchestrator = bootstrap.run()
                try:
                    self.assert_not_none(bootstrap.long_term_memory_service)
                    self.assert_equal(
                        bootstrap.long_term_memory_service.providers_status().active_provider,
                        "knowledge",
                    )
                    router = bootstrap.command_router
                    self.assert_true("ltm" in router.module_names)

                    dispatch_result = router.dispatch("ltm status")
                    self.assert_true(dispatch_result.success)

                    # EP-023 integration: "long_term" is now a registered
                    # (though not necessarily active) memory provider.
                    self.assert_true(bootstrap.long_term_memory_service.status().memory_manager_integrated)
                    memory_providers = bootstrap.memory_service.providers_status()
                    provider_names = [entry.name for entry in memory_providers.providers]
                    self.assert_true("long_term" in provider_names)

                    # EP-024 integration: storing through ltm surfaces in Knowledge Base too.
                    store_result = router.dispatch("ltm archive mem-does-not-exist")
                    self.assert_false(store_result.success)
                    bootstrap.long_term_memory_service.store("mem-1", "hello")
                    self.assert_true(
                        "long_term_memory" in bootstrap.knowledge_service.collection_names()
                    )
                finally:
                    orchestrator.stop()

    def _test_bootstrap_degrades_gracefully_on_invalid_ltm_config(self) -> None:
        """Invalid 'long_term_memory.default_provider' disables LTM but the rest of Jarvis still starts."""
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            project_root = Path(tmp_dir_name)
            _write_full_bootstrap_config(project_root, ltm_default_provider="")
            with _ChdirGuard(project_root):
                bootstrap = Bootstrap(project_root=project_root)
                orchestrator = bootstrap.run()
                try:
                    self.assert_true(bootstrap.long_term_memory_service is None)
                    router = bootstrap.command_router
                    self.assert_false("ltm" in router.module_names)
                    # The rest of the application, including Knowledge Base, still started.
                    self.assert_true("knowledge" in router.module_names)
                    self.assert_true("system" in router.module_names)
                finally:
                    orchestrator.stop()

    def _test_bootstrap_degrades_when_knowledge_base_unavailable(self) -> None:
        """LTM disables itself when its hard dependency (Knowledge Base) is unavailable."""
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            project_root = Path(tmp_dir_name)
            _write_full_bootstrap_config(project_root, knowledge_default_provider="")
            with _ChdirGuard(project_root):
                bootstrap = Bootstrap(project_root=project_root)
                orchestrator = bootstrap.run()
                try:
                    self.assert_true(bootstrap.knowledge_service is None)
                    self.assert_true(bootstrap.long_term_memory_service is None)
                    router = bootstrap.command_router
                    self.assert_false("knowledge" in router.module_names)
                    self.assert_false("ltm" in router.module_names)
                    self.assert_true("system" in router.module_names)
                finally:
                    orchestrator.stop()

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """The Long-Term Memory package never imports Embedding, RAG, Agent, etc.

        Per EP-025's task brief, Long-Term Memory must not import
        Embedding, Retrieval, RAG, Semantic Search, Context
        Compression, Reflection, Planner, Agent Framework, Browser
        Automation, Vector Database, or any future EP. It MAY import
        Memory Manager (EP-023) and Knowledge Base (EP-024) public APIs.
        """
        forbidden_module_fragments = (
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
        modules = [long_term_manager_module, long_term_provider_module]
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

    def _test_manager_owns_no_storage_state(self) -> None:
        """LongTermMemoryManager keeps no record data itself -- only provider registration state."""
        manager = LongTermMemoryManager()
        instance_attrs = vars(manager)
        forbidden_attr_names = ("records", "values", "memories", "collections")
        for attr_name in instance_attrs:
            for forbidden in forbidden_attr_names:
                self.assert_true(
                    forbidden not in attr_name.lower(),
                    f"LongTermMemoryManager should not own storage state ('{attr_name}')",
                )

    def _test_exception_hierarchy(self) -> None:
        """LongTermProviderError is a plain Exception, catchable on its own."""
        self.assert_true(issubclass(LongTermProviderError, Exception))
        try:
            raise LongTermProviderError("boom")
        except LongTermProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "LongTermProviderError should be catchable directly")

    def _test_only_expected_provider_classes_exist(self) -> None:
        """Only the two documented provider classes exist -- no future-EP providers.

        EP-025 must implement only `LongTermProvider` (abstraction),
        `KnowledgeBackedLongTermProvider` (Knowledge-Base-backed
        adapter), and `LongTermMemoryProvider` (EP-023 MemoryProvider
        adapter) -- not SemanticSearchProvider, ExternalProvider, or
        VectorStoreProvider, which are explicitly future work.
        """
        forbidden_class_names = (
            "SemanticSearchProvider",
            "ExternalProvider",
            "VectorStoreProvider",
            "ReflectionProvider",
        )
        module_source = inspect.getsource(long_term_provider_module)
        for class_name in forbidden_class_names:
            self.assert_true(
                f"class {class_name}" not in module_source,
                f"{class_name} must not be implemented in EP-025",
            )
