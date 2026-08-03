"""Real engineering tests for EP-027 - Context Compression.

Builds real `ContextChunk`/`CompressionResult`/`CompressionProvider`/
`CompressionManager`/`CompressionEngine`/`CompressionService`/
`ContextCompressionModule` instances -- composed, where needed, with a
real `SemanticEngine`/`SemanticManager` (EP-026) built on top of a real
`EmbeddingManager`/`EmbeddingEngine` (EP-021) -- and drives them
exactly as a caller would, no mocked internals, matching every other
EP's test suite in this project (see tests/EP026/test_semantic_search.py).

Context Compression (EP-027) is a new, independent package
(`src/core/context_compression/`) that shrinks already-assembled
context (raw text, or EP-026 `SemanticResult` instances) down to a
configured character/chunk budget, using only deterministic,
arithmetic operations -- never touching Semantic Search's internals,
only its public `SemanticEngine.search()` method and `SemanticResult`
dataclass fields. This suite covers:

1. The domain model: `ContextChunk`, `CompressionResult`.
2. The provider abstraction: `CompressionProvider` (abstract
   contract), `DefaultCompressionProvider` (built-in dedup + limit
   enforcement provider) -- deduplication (chunk-level and
   paragraph-level), ordering preservation, metadata preservation,
   maximum chunk/character enforcement, and token estimation.
3. `CompressionManager`: configuration validation, registration,
   enable/disable, active-provider switching, status, and the default
   `max_context_characters` / `max_chunks` / `deduplicate` parameters.
4. `CompressionEngine`: the text/chunks -> compressed-result pipeline,
   including optional integration with a real EP-026 `SemanticEngine`
   via `compress_query()`.
5. `CompressionService`/`ContextCompressionModule`: configuration-driven
   construction, graceful degradation, and every CLI command ("status",
   "providers", "use", "analyze", "compress", "limits", "help").
6. Architecture compliance: no forbidden imports, no duplicated
   provider/manager/storage logic, no future-EP functionality, no
   private-API access into EP-026, and a real `Bootstrap` run proving
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
from src.core.context_compression import compression_engine as compression_engine_module
from src.core.context_compression import compression_manager as compression_manager_module
from src.core.context_compression import compression_provider as compression_provider_module
from src.core.context_compression.compression_engine import (
    CompressionEngine,
    CompressionEngineError,
    EmptyContextError,
    NoCompressionProviderSelectedError,
    SemanticSearchUnavailableError,
)
from src.core.context_compression.compression_manager import (
    CompressionManager,
    CompressionProviderNotFoundError,
    CompressionProviderRegistryError,
)
from src.core.context_compression.compression_provider import (
    CompressionConfigurationError,
    CompressionProvider,
    CompressionProviderError,
    CompressionProviderStatus,
    ContextCompressionError,
    DefaultCompressionProvider,
)
from src.core.context_compression.compression_result import CompressionResult, ContextChunk
from src.core.embedding.engine import EmbeddingEngine
from src.core.embedding.manager import EmbeddingManager
from src.core.semantic.semantic_engine import SemanticEngine
from src.core.semantic.semantic_manager import SemanticManager
from src.core.semantic.semantic_result import SemanticResult
from src.modules.context_compression_module import ContextCompressionModule
from src.services.context_compression_service import CompressionService
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

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        os.chdir(self._original)


_EMBEDDING_YAML = (
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
    "      dimension: 1536\n"
)

_KNOWLEDGE_YAML = "knowledge:\n  enabled: true\n  default_provider: \"local\"\n"

_SEMANTIC_YAML = (
    "semantic:\n"
    "  enabled: true\n"
    "  default_provider: \"semantic\"\n"
    "  top_k: 5\n"
    "  similarity_threshold: 0.0\n"
)

_DEFAULT_COMPRESSION_YAML = (
    "context_compression:\n"
    "  enabled: true\n"
    "  default_provider: \"compression\"\n"
    "  max_context_characters: 12000\n"
    "  max_chunks: 20\n"
    "  deduplicate: true\n"
)

_DISABLED_COMPRESSION_YAML = (
    "context_compression:\n"
    "  enabled: false\n"
    "  default_provider: \"compression\"\n"
    "  max_context_characters: 12000\n"
    "  max_chunks: 20\n"
    "  deduplicate: true\n"
)

_INVALID_PROVIDER_COMPRESSION_YAML = (
    "context_compression:\n"
    "  enabled: true\n"
    "  default_provider: \"\"\n"
    "  max_context_characters: 12000\n"
    "  max_chunks: 20\n"
    "  deduplicate: true\n"
)

_INVALID_MAX_CHARACTERS_COMPRESSION_YAML = (
    "context_compression:\n"
    "  enabled: true\n"
    "  default_provider: \"compression\"\n"
    "  max_context_characters: -5\n"
    "  max_chunks: 20\n"
    "  deduplicate: true\n"
)

_INVALID_MAX_CHUNKS_COMPRESSION_YAML = (
    "context_compression:\n"
    "  enabled: true\n"
    "  default_provider: \"compression\"\n"
    "  max_context_characters: 12000\n"
    "  max_chunks: 0\n"
    "  deduplicate: true\n"
)

_INVALID_DEDUPLICATE_COMPRESSION_YAML = (
    "context_compression:\n"
    "  enabled: true\n"
    "  default_provider: \"compression\"\n"
    "  max_context_characters: 12000\n"
    "  max_chunks: 20\n"
    "  deduplicate: \"yes\"\n"
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
    "  default_provider: \"{compression_default_provider}\"\n"
    "  max_context_characters: {max_context_characters}\n"
    "  max_chunks: 20\n"
    "  deduplicate: true\n"
)


_CONFIG_CACHE: dict[str, Config] = {}


def _write_config(directory: Path, sections: str) -> Config:
    """Return a Config for `sections`, parsing it at most once per distinct text.

    Many test methods request byte-identical configuration text across
    dozens of independent temporary directories; re-writing and
    re-parsing identical YAML from scratch every time is pure overhead
    -- profiled at roughly two-thirds of this suite's total runtime
    (see the EP-025/EP-026/EP-027 performance investigation). Caching
    by the exact YAML text keeps every test's observed `Config.get()`
    behavior byte-for-byte identical (the returned `Config` is never
    mutated after `load()`) while eliminating the redundant disk write
    and re-parse. Callers that need a real config.yaml physically
    present in a specific directory (e.g. a real `Bootstrap(...)`
    run) use `_write_full_bootstrap_config()` instead, which is never
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
    compression_default_provider: str = "compression",
    max_context_characters: int = 12000,
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            compression_default_provider=compression_default_provider,
            max_context_characters=max_context_characters,
        ),
        encoding="utf-8",
    )


class _RecordingCompressionProvider(CompressionProvider):
    """A minimal, independent CompressionProvider used only to test CompressionManager.

    Always returns an empty CompressionResult, entirely separate from
    `DefaultCompressionProvider`, so tests can prove `CompressionManager`
    truly delegates to whichever provider is active rather than always
    using the built-in one.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def provider_name(self) -> str:
        return self._name

    def compress(self, chunks, max_characters, max_chunks, deduplicate):
        return CompressionResult(
            chunks=[],
            original_chunk_count=len(chunks),
            chunk_count=0,
            original_character_count=sum(len(c.text) for c in chunks),
            character_count=0,
            estimated_tokens=0,
            deduplicated_chunk_count=0,
            truncated=False,
        )

    def estimate_tokens(self, text: str) -> int:
        return 0


@TestRegistry.register
class ContextCompressionTest(BaseTest):
    NAME = "EP027"

    def run(self):
        # ---------- Domain model ----------
        self._test_chunk_and_result_construction()

        # ---------- CompressionProvider / DefaultCompressionProvider ----------
        self._test_provider_is_abstract()
        self._test_default_provider_name()
        self._test_default_provider_no_duplicates_no_truncation()
        self._test_default_provider_removes_duplicate_chunks()
        self._test_default_provider_removes_duplicate_paragraphs()
        self._test_default_provider_preserves_ordering()
        self._test_default_provider_preserves_metadata()
        self._test_default_provider_deduplicate_false_keeps_duplicates()
        self._test_default_provider_enforces_max_chunks()
        self._test_default_provider_enforces_max_characters()
        self._test_default_provider_truncates_boundary_chunk()
        self._test_default_provider_token_estimation()
        self._test_default_provider_invalid_limits_raise()
        self._test_default_provider_health_and_status()

        # ---------- CompressionManager ----------
        self._test_manager_registers_default_provider()
        self._test_manager_config_defaults()
        self._test_manager_invalid_enabled_raises()
        self._test_manager_invalid_max_context_characters_raises()
        self._test_manager_invalid_max_chunks_raises()
        self._test_manager_invalid_deduplicate_raises()
        self._test_manager_invalid_default_provider_raises()
        self._test_manager_duplicate_registration_raises()
        self._test_manager_unknown_provider_raises()
        self._test_manager_set_current_switches_provider()
        self._test_manager_disable_clears_current()
        self._test_manager_get_current_none_when_disabled()
        self._test_manager_current_provider_name_none_when_disabled_via_config()
        self._test_manager_setters_validate()
        self._test_manager_second_provider_registers_without_stealing_active()

        # ---------- CompressionEngine ----------
        self._test_engine_empty_text_raises()
        self._test_engine_empty_chunks_raises()
        self._test_engine_no_provider_selected_raises()
        self._test_engine_compress_text_splits_paragraphs()
        self._test_engine_compress_chunks_preserves_order_and_metadata()
        self._test_engine_estimate_does_not_truncate()
        self._test_engine_compress_semantic_results()
        self._test_engine_compress_query_without_semantic_engine_raises()
        self._test_engine_compress_query_with_real_semantic_engine()
        self._test_engine_compress_query_empty_results_raises()

        # ---------- CompressionService ----------
        self._test_service_status_and_providers()
        self._test_service_use_unknown_provider_fails_gracefully()
        self._test_service_analyze_success_and_failure()
        self._test_service_compress_success_and_failure()
        self._test_service_limits_get_set()
        self._test_service_disable()

        # ---------- ContextCompressionModule (CLI) ----------
        self._test_cli_help_lists_commands()
        self._test_cli_status_command()
        self._test_cli_providers_command()
        self._test_cli_use_command()
        self._test_cli_analyze_command_usage_and_results()
        self._test_cli_compress_command_usage_and_results()
        self._test_cli_limits_command()
        self._test_cli_unknown_action()

        # ---------- Bootstrap wiring ----------
        self._test_bootstrap_registers_compression_module()
        self._test_bootstrap_degrades_gracefully_on_invalid_compression_config()
        self._test_bootstrap_compression_independent_of_semantic_availability()
        self._test_bootstrap_default_config_compress_returns_results()

        # ---------- Architectural acceptance criteria ----------
        self._test_no_forbidden_imports()
        self._test_manager_owns_no_storage_state()
        self._test_exception_hierarchy()
        self._test_only_expected_provider_classes_exist()
        self._test_no_private_api_access_on_foreign_objects()

        return self.result

    # ---------- Helpers ----------

    def _build_manager(self, tmp_path: Path, yaml_text: str = _DEFAULT_COMPRESSION_YAML) -> CompressionManager:
        config = _write_config(tmp_path, yaml_text)
        return CompressionManager(config=config)

    def _build_engine(
        self, tmp_path: Path, yaml_text: str = _DEFAULT_COMPRESSION_YAML, with_semantic: bool = False
    ) -> tuple[CompressionEngine, KnowledgeService | None]:
        manager = self._build_manager(tmp_path, yaml_text)
        if not with_semantic:
            return CompressionEngine(manager=manager), None

        embedding_config = _write_config(tmp_path, _EMBEDDING_YAML)
        embedding_manager = EmbeddingManager(config=embedding_config)
        embedding_engine = EmbeddingEngine(manager=embedding_manager)

        knowledge_config = _write_config(tmp_path, _KNOWLEDGE_YAML)
        knowledge_service = KnowledgeService(config=knowledge_config)

        semantic_config = _write_config(tmp_path, _SEMANTIC_YAML)
        semantic_manager = SemanticManager(config=semantic_config)
        semantic_engine = SemanticEngine(
            manager=semantic_manager,
            embedding_engine=embedding_engine,
            embedding_manager=embedding_manager,
            knowledge_service=knowledge_service,
        )
        engine = CompressionEngine(manager=manager, semantic_engine=semantic_engine)
        return engine, knowledge_service

    def _build_service(
        self, tmp_path: Path, yaml_text: str = _DEFAULT_COMPRESSION_YAML
    ) -> CompressionService:
        engine, _knowledge = self._build_engine(tmp_path, yaml_text)
        return CompressionService(manager=engine._manager, engine=engine)  # noqa: SLF001

    # ---------- Domain model ----------

    def _test_chunk_and_result_construction(self) -> None:
        chunk = ContextChunk(text="hello", index=0, metadata={"source": "x"})
        self.assert_equal(chunk.text, "hello")
        self.assert_equal(chunk.index, 0)
        self.assert_equal(chunk.metadata, {"source": "x"})

        result = CompressionResult(
            chunks=[chunk],
            original_chunk_count=2,
            chunk_count=1,
            original_character_count=10,
            character_count=5,
            estimated_tokens=2,
            deduplicated_chunk_count=1,
            truncated=False,
        )
        self.assert_equal(result.joined_text(), "hello")
        self.assert_equal(result.joined_text(separator="|"), "hello")

        result_multi = CompressionResult(
            chunks=[chunk, ContextChunk(text="world", index=1)],
            original_chunk_count=2,
            chunk_count=2,
            original_character_count=10,
            character_count=10,
            estimated_tokens=3,
            deduplicated_chunk_count=0,
            truncated=False,
        )
        self.assert_equal(result_multi.joined_text(), "hello\n\nworld")
        self.assert_equal(result_multi.joined_text(separator=" "), "hello world")

    # ---------- CompressionProvider / DefaultCompressionProvider ----------

    def _test_provider_is_abstract(self) -> None:
        try:
            CompressionProvider()  # type: ignore[abstract]
        except TypeError:
            self.result.add_pass()
        else:
            self.assert_true(False, "CompressionProvider must be abstract")

    def _test_default_provider_name(self) -> None:
        provider = DefaultCompressionProvider()
        self.assert_equal(provider.provider_name(), "compression")

    def _test_default_provider_no_duplicates_no_truncation(self) -> None:
        provider = DefaultCompressionProvider()
        chunks = [
            ContextChunk(text="Paragraph one.", index=0),
            ContextChunk(text="Paragraph two.", index=1),
        ]
        result = provider.compress(chunks, max_characters=1000, max_chunks=10, deduplicate=True)
        self.assert_equal(result.chunk_count, 2)
        self.assert_equal(result.original_chunk_count, 2)
        self.assert_equal(result.deduplicated_chunk_count, 0)
        self.assert_false(result.truncated)

    def _test_default_provider_removes_duplicate_chunks(self) -> None:
        provider = DefaultCompressionProvider()
        chunks = [
            ContextChunk(text="Same text here.", index=0),
            ContextChunk(text="Something else.", index=1),
            ContextChunk(text="Same text here.", index=2),
        ]
        result = provider.compress(chunks, max_characters=1000, max_chunks=10, deduplicate=True)
        self.assert_equal(result.chunk_count, 2)
        self.assert_equal(result.deduplicated_chunk_count, 1)
        self.assert_equal([c.text for c in result.chunks], ["Same text here.", "Something else."])

    def _test_default_provider_removes_duplicate_paragraphs(self) -> None:
        provider = DefaultCompressionProvider()
        chunks = [
            ContextChunk(text="Alpha paragraph.\n\nShared paragraph.", index=0),
            ContextChunk(text="Shared paragraph.\n\nBeta paragraph.", index=1),
        ]
        result = provider.compress(chunks, max_characters=1000, max_chunks=10, deduplicate=True)
        self.assert_equal(result.chunk_count, 2)
        self.assert_true("Shared paragraph." not in result.chunks[1].text)
        self.assert_true("Beta paragraph." in result.chunks[1].text)
        self.assert_equal(result.deduplicated_chunk_count, 1)

    def _test_default_provider_preserves_ordering(self) -> None:
        provider = DefaultCompressionProvider()
        chunks = [ContextChunk(text=f"Unique chunk number {i}.", index=i) for i in range(5)]
        result = provider.compress(chunks, max_characters=10000, max_chunks=10, deduplicate=True)
        self.assert_equal([c.index for c in result.chunks], [0, 1, 2, 3, 4])

    def _test_default_provider_preserves_metadata(self) -> None:
        provider = DefaultCompressionProvider()
        chunks = [ContextChunk(text="Some content.", index=0, metadata={"source": "knowledge", "identifier": "doc1"})]
        result = provider.compress(chunks, max_characters=1000, max_chunks=10, deduplicate=True)
        self.assert_equal(result.chunks[0].metadata, {"source": "knowledge", "identifier": "doc1"})

    def _test_default_provider_deduplicate_false_keeps_duplicates(self) -> None:
        provider = DefaultCompressionProvider()
        chunks = [
            ContextChunk(text="Repeat me.", index=0),
            ContextChunk(text="Repeat me.", index=1),
        ]
        result = provider.compress(chunks, max_characters=1000, max_chunks=10, deduplicate=False)
        self.assert_equal(result.chunk_count, 2)
        self.assert_equal(result.deduplicated_chunk_count, 0)

    def _test_default_provider_enforces_max_chunks(self) -> None:
        provider = DefaultCompressionProvider()
        chunks = [ContextChunk(text=f"Chunk {i}.", index=i) for i in range(10)]
        result = provider.compress(chunks, max_characters=10000, max_chunks=3, deduplicate=True)
        self.assert_equal(result.chunk_count, 3)
        self.assert_equal([c.index for c in result.chunks], [0, 1, 2])
        self.assert_true(result.truncated)

    def _test_default_provider_enforces_max_characters(self) -> None:
        provider = DefaultCompressionProvider()
        chunks = [
            ContextChunk(text="A" * 50, index=0),
            ContextChunk(text="B" * 50, index=1),
            ContextChunk(text="C" * 50, index=2),
        ]
        result = provider.compress(chunks, max_characters=60, max_chunks=10, deduplicate=True)
        self.assert_true(result.character_count <= 60)
        self.assert_true(result.truncated)
        # First chunk kept whole; second truncated to fill remaining budget.
        self.assert_equal(result.chunks[0].text, "A" * 50)

    def _test_default_provider_truncates_boundary_chunk(self) -> None:
        provider = DefaultCompressionProvider()
        chunks = [ContextChunk(text="X" * 100, index=0)]
        result = provider.compress(chunks, max_characters=30, max_chunks=10, deduplicate=True)
        self.assert_equal(result.chunk_count, 1)
        self.assert_equal(len(result.chunks[0].text), 30)
        self.assert_true(result.truncated)

    def _test_default_provider_token_estimation(self) -> None:
        provider = DefaultCompressionProvider()
        self.assert_equal(provider.estimate_tokens(""), 0)
        self.assert_equal(provider.estimate_tokens("abcd"), 1)
        self.assert_equal(provider.estimate_tokens("abcde"), 2)
        self.assert_equal(provider.estimate_tokens("a" * 12), 3)

    def _test_default_provider_invalid_limits_raise(self) -> None:
        provider = DefaultCompressionProvider()
        chunks = [ContextChunk(text="x", index=0)]
        try:
            provider.compress(chunks, max_characters=0, max_chunks=10, deduplicate=True)
        except CompressionProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Expected CompressionProviderError for max_characters=0")

        try:
            provider.compress(chunks, max_characters=100, max_chunks=0, deduplicate=True)
        except CompressionProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Expected CompressionProviderError for max_chunks=0")

    def _test_default_provider_health_and_status(self) -> None:
        provider = DefaultCompressionProvider()
        self.assert_equal(provider.status(), CompressionProviderStatus.AVAILABLE)
        self.assert_true(provider.is_available())
        health = provider.health()
        self.assert_true(health.available)

    # ---------- CompressionManager ----------

    def _test_manager_registers_default_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            providers = manager.list_providers()
            self.assert_equal(len(providers), 1)
            self.assert_equal(providers[0].provider_name(), "compression")
            self.assert_equal(manager.current_provider_name(), "compression")

    def _test_manager_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            self.assert_equal(manager.max_context_characters(), 12000)
            self.assert_equal(manager.max_chunks(), 20)
            self.assert_true(manager.deduplicate())
            self.assert_true(manager.is_enabled())

    def _test_manager_invalid_enabled_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            yaml_text = (
                "context_compression:\n"
                "  enabled: \"yes\"\n"
                "  default_provider: \"compression\"\n"
                "  max_context_characters: 12000\n"
                "  max_chunks: 20\n"
                "  deduplicate: true\n"
            )
            try:
                self._build_manager(Path(tmp), yaml_text)
            except CompressionConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected CompressionConfigurationError")

    def _test_manager_invalid_max_context_characters_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_MAX_CHARACTERS_COMPRESSION_YAML)
            except CompressionConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected CompressionConfigurationError")

    def _test_manager_invalid_max_chunks_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_MAX_CHUNKS_COMPRESSION_YAML)
            except CompressionConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected CompressionConfigurationError")

    def _test_manager_invalid_deduplicate_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_DEDUPLICATE_COMPRESSION_YAML)
            except CompressionConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected CompressionConfigurationError")

    def _test_manager_invalid_default_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                self._build_manager(Path(tmp), _INVALID_PROVIDER_COMPRESSION_YAML)
            except CompressionConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected CompressionConfigurationError")

    def _test_manager_duplicate_registration_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.register_provider(DefaultCompressionProvider())
            except CompressionProviderRegistryError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected CompressionProviderRegistryError")

    def _test_manager_unknown_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            try:
                manager.get_provider("does-not-exist")
            except CompressionProviderNotFoundError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected CompressionProviderNotFoundError")

            try:
                manager.set_current("does-not-exist")
            except CompressionProviderNotFoundError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected CompressionProviderNotFoundError")

    def _test_manager_set_current_switches_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            recorder = _RecordingCompressionProvider("recorder")
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

    def _test_manager_get_current_none_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.disable()
            self.assert_true(manager.get_current() is None)

    def _test_manager_current_provider_name_none_when_disabled_via_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp), _DISABLED_COMPRESSION_YAML)
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.current_provider_name() is None)

    def _test_manager_setters_validate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.set_max_context_characters(500)
            self.assert_equal(manager.max_context_characters(), 500)
            manager.set_max_chunks(3)
            self.assert_equal(manager.max_chunks(), 3)
            manager.set_deduplicate(False)
            self.assert_false(manager.deduplicate())

            try:
                manager.set_max_context_characters(-1)
            except CompressionConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected CompressionConfigurationError")

            try:
                manager.set_max_chunks(0)
            except CompressionConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected CompressionConfigurationError")

            try:
                manager.set_deduplicate("nope")  # type: ignore[arg-type]
            except CompressionConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected CompressionConfigurationError")

    def _test_manager_second_provider_registers_without_stealing_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            manager.register_provider(_RecordingCompressionProvider("recorder"))
            self.assert_equal(manager.current_provider_name(), "compression")
            self.assert_equal(len(manager.list_providers()), 2)

    # ---------- CompressionEngine ----------

    def _test_engine_empty_text_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _k = self._build_engine(Path(tmp))
            try:
                engine.compress_text("   ")
            except EmptyContextError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected EmptyContextError")

    def _test_engine_empty_chunks_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _k = self._build_engine(Path(tmp))
            try:
                engine.compress_chunks([])
            except EmptyContextError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected EmptyContextError")

    def _test_engine_no_provider_selected_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _k = self._build_engine(Path(tmp))
            engine._manager.disable()  # noqa: SLF001
            try:
                engine.compress_text("some text")
            except NoCompressionProviderSelectedError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected NoCompressionProviderSelectedError")

    def _test_engine_compress_text_splits_paragraphs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _k = self._build_engine(Path(tmp))
            text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
            result = engine.compress_text(text)
            self.assert_equal(result.original_chunk_count, 3)
            self.assert_equal(result.chunk_count, 3)

    def _test_engine_compress_chunks_preserves_order_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _k = self._build_engine(Path(tmp))
            chunks = [
                ContextChunk(text="One.", index=0, metadata={"tag": "a"}),
                ContextChunk(text="Two.", index=1, metadata={"tag": "b"}),
            ]
            result = engine.compress_chunks(chunks)
            self.assert_equal([c.metadata["tag"] for c in result.chunks], ["a", "b"])

    def _test_engine_estimate_does_not_truncate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(
                Path(tmp),
                (
                    "context_compression:\n"
                    "  enabled: true\n"
                    "  default_provider: \"compression\"\n"
                    "  max_context_characters: 5\n"
                    "  max_chunks: 1\n"
                    "  deduplicate: true\n"
                ),
            )
            engine = CompressionEngine(manager=manager)
            text = "This text is much longer than five characters."
            character_count, estimated_tokens, chunk_count = engine.estimate(text)
            self.assert_equal(character_count, len(text))
            self.assert_true(estimated_tokens > 0)
            self.assert_equal(chunk_count, 1)

            try:
                engine.estimate("   ")
            except EmptyContextError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected EmptyContextError")

    def _test_engine_compress_semantic_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _k = self._build_engine(Path(tmp))
            results = [
                SemanticResult(
                    source="knowledge", identifier="doc1", text="First fact.", score=0.9,
                    metadata={"extra": "1"},
                ),
                SemanticResult(
                    source="long_term_memory", identifier="mem1", text="Second fact.", score=0.8,
                    metadata={},
                ),
            ]
            compression_result = engine.compress_semantic_results(results)
            self.assert_equal(compression_result.chunk_count, 2)
            self.assert_equal(compression_result.chunks[0].metadata["identifier"], "doc1")
            self.assert_equal(compression_result.chunks[0].metadata["source"], "knowledge")
            self.assert_equal(compression_result.chunks[0].metadata["score"], 0.9)
            self.assert_equal(compression_result.chunks[0].metadata["extra"], "1")

    def _test_engine_compress_query_without_semantic_engine_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _k = self._build_engine(Path(tmp), with_semantic=False)
            try:
                engine.compress_query("anything")
            except SemanticSearchUnavailableError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected SemanticSearchUnavailableError")

    def _test_engine_compress_query_with_real_semantic_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, knowledge = self._build_engine(Path(tmp), with_semantic=True)
            fact_text = "The Eiffel Tower is located in Paris France"
            knowledge.store("fact1", fact_text)
            result = engine.compress_query(fact_text, threshold=-1.0)
            self.assert_true(result.chunk_count >= 1)
            self.assert_true(any(c.metadata.get("identifier") == "fact1" for c in result.chunks))

    def _test_engine_compress_query_empty_results_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _knowledge = self._build_engine(Path(tmp), with_semantic=True)
            try:
                engine.compress_query("nothing has ever been stored", threshold=2.0)
            except EmptyContextError:
                self.result.add_pass()
            else:
                self.assert_true(False, "Expected EmptyContextError")

    # ---------- CompressionService ----------

    def _test_service_status_and_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            status = service.status()
            self.assert_true(status.enabled)
            self.assert_equal(status.current_provider, "compression")
            self.assert_equal(status.registered_provider_count, 1)
            self.assert_equal(status.max_context_characters, 12000)
            self.assert_equal(status.max_chunks, 20)
            self.assert_true(status.deduplicate)

            providers = service.list_providers()
            self.assert_equal(len(providers), 1)
            self.assert_equal(providers[0].name, "compression")
            self.assert_true(providers[0].is_current)

    def _test_service_use_unknown_provider_fails_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            outcome = service.use_provider("does-not-exist")
            self.assert_false(outcome.success)

    def _test_service_analyze_success_and_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            outcome = service.analyze("Some text to analyze.")
            self.assert_true(outcome.success)
            self.assert_true(outcome.character_count > 0)
            self.assert_true(outcome.estimated_tokens > 0)
            self.assert_equal(outcome.chunk_count, 1)

            failure = service.analyze("   ")
            self.assert_false(failure.success)
            self.assert_true(failure.error != "")

    def _test_service_compress_success_and_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            outcome = service.compress("Paragraph one.\n\nParagraph one.\n\nParagraph two.")
            self.assert_true(outcome.success)
            self.assert_true(outcome.result is not None)
            self.assert_equal(outcome.result.chunk_count, 2)

            failure = service.compress("")
            self.assert_false(failure.success)
            self.assert_true(failure.error != "")

    def _test_service_limits_get_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            limits = service.limits()
            self.assert_equal(limits.max_context_characters, 12000)
            self.assert_equal(limits.max_chunks, 20)

            result = service.set_max_context_characters(500)
            self.assert_true(result.success)
            self.assert_equal(service.limits().max_context_characters, 500)

            result = service.set_max_chunks(4)
            self.assert_true(result.success)
            self.assert_equal(service.limits().max_chunks, 4)

            bad = service.set_max_context_characters(-1)
            self.assert_false(bad.success)

    def _test_service_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            result = service.disable()
            self.assert_true(result.success)
            self.assert_false(service.status().enabled)

    # ---------- ContextCompressionModule (CLI) ----------

    def _test_cli_help_lists_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ContextCompressionModule(service)
            self.assert_equal(module.name, "compression")
            result = module.execute("help", [])
            self.assert_true(result.success)
            for command in ("status", "providers", "use", "analyze", "compress", "limits"):
                self.assert_true(command in result.message)

    def _test_cli_status_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ContextCompressionModule(service)
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Enabled" in result.message)

    def _test_cli_providers_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ContextCompressionModule(service)
            result = module.execute("providers", [])
            self.assert_true(result.success)
            self.assert_true("compression" in result.message)

    def _test_cli_use_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ContextCompressionModule(service)
            self.assert_false(module.execute("use", []).success)
            self.assert_false(module.execute("use", ["nope"]).success)
            self.assert_true(module.execute("use", ["compression"]).success)

    def _test_cli_analyze_command_usage_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ContextCompressionModule(service)
            self.assert_false(module.execute("analyze", []).success)
            result = module.execute("analyze", ["Hello", "world"])
            self.assert_true(result.success)
            self.assert_true("Characters" in result.message)

    def _test_cli_compress_command_usage_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ContextCompressionModule(service)
            self.assert_false(module.execute("compress", []).success)
            result = module.execute("compress", ["Hello", "world"])
            self.assert_true(result.success)
            self.assert_true("Compressed chunks" in result.message)

    def _test_cli_limits_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ContextCompressionModule(service)
            result = module.execute("limits", [])
            self.assert_true(result.success)
            self.assert_true("Max context characters" in result.message)

    def _test_cli_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service = self._build_service(Path(tmp))
            module = ContextCompressionModule(service)
            result = module.execute("bogus", [])
            self.assert_false(result.success)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_compression_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                service = bootstrap.compression_service
                self.assert_true(service is not None)
                status = service.status()
                self.assert_true(status.enabled)
                self.assert_equal(status.current_provider, "compression")

                result = bootstrap._command_router.dispatch("compression status")  # noqa: SLF001
                self.assert_true(result.success)

    def _test_bootstrap_degrades_gracefully_on_invalid_compression_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, compression_default_provider="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()  # must not raise -- Context Compression degrades, Jarvis still starts
                self.assert_true(bootstrap.compression_service is None)
                # The rest of the application is unaffected.
                self.assert_true(bootstrap.knowledge_service is not None)
                self.assert_true(bootstrap.semantic_service is not None)

    def _test_bootstrap_compression_independent_of_semantic_availability(self) -> None:
        """Context Compression must not require Semantic Search or the Embedding Engine."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            config_dir = directory / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            # Reuse the full bootstrap config, then disable embedding (which
            # in turn disables Semantic Search, per EP-026's own wiring).
            full_config = _FULL_BOOTSTRAP_CONFIG_YAML.format(
                compression_default_provider="compression", max_context_characters=12000
            ).replace("embedding:\n  enabled: true", "embedding:\n  enabled: false")
            (config_dir / "config.yaml").write_text(full_config, encoding="utf-8")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.compression_service is not None)
                self.assert_true(bootstrap.compression_service.status().enabled)
                result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    "compression compress Hello world"
                )
                self.assert_true(result.success)

    def _test_bootstrap_default_config_compress_returns_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_equal(
                    bootstrap.compression_service.status().max_context_characters, 12000
                )

                result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    "compression compress Repeated words here. Repeated words here. New words here."
                )
                self.assert_true(result.success)
                self.assert_true("Deduplicated" in result.message)

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """EP-027 must not import RAG, AI providers, Planner, Reflection, or Agent Framework code."""
        forbidden_fragments = (
            "src.core.rag",
            "src.core.ai",
            "src.core.planner",
            "src.core.reflection",
            "src.core.agent",
            "src.core.prompt",
            "browser_automation",
            "tool_calling",
            "src.core.conversation",
        )
        for module in (
            compression_engine_module,
            compression_manager_module,
            compression_provider_module,
        ):
            source = inspect.getsource(module)
            for fragment in forbidden_fragments:
                self.assert_true(
                    fragment not in source,
                    f"{module.__name__} must not reference '{fragment}'",
                )

    def _test_manager_owns_no_storage_state(self) -> None:
        """CompressionManager owns provider registration only, never chunk/context storage."""
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._build_manager(Path(tmp))
            instance_attrs = vars(manager)
            forbidden_attr_names = ("_records", "_collection", "_store", "_documents", "_index")
            for attr_name in instance_attrs:
                for forbidden in forbidden_attr_names:
                    self.assert_true(
                        forbidden not in attr_name.lower(),
                        f"CompressionManager should not own storage state ('{attr_name}')",
                    )

    def _test_exception_hierarchy(self) -> None:
        """CompressionProviderError is a ContextCompressionError, catchable through the shared root."""
        self.assert_true(issubclass(CompressionProviderError, ContextCompressionError))
        self.assert_true(issubclass(CompressionEngineError, ContextCompressionError))
        try:
            raise CompressionProviderError("boom")
        except ContextCompressionError:
            self.result.add_pass()
        else:
            self.assert_true(
                False, "CompressionProviderError should be catchable as ContextCompressionError"
            )

    def _test_only_expected_provider_classes_exist(self) -> None:
        """Only the two documented provider classes exist -- no future-EP providers.

        EP-027 must implement only `CompressionProvider` (abstraction)
        and `DefaultCompressionProvider` (built-in dedup + limit
        enforcement provider) -- not `TokenCompressionProvider`,
        `AdaptiveCompressionProvider`, or `SmartCompressionProvider`,
        which are explicitly future work per the task brief.
        """
        forbidden_class_names = (
            "TokenCompressionProvider",
            "AdaptiveCompressionProvider",
            "SmartCompressionProvider",
        )
        module_source = inspect.getsource(compression_provider_module)
        for class_name in forbidden_class_names:
            self.assert_true(
                f"class {class_name}" not in module_source,
                f"{class_name} must not be implemented in EP-027",
            )

    def _test_no_private_api_access_on_foreign_objects(self) -> None:
        """CompressionEngine reaches Semantic Search only through public methods/fields.

        Scans `compression_engine.py`'s source for any attribute
        access beginning with an underscore on the injected
        collaborator (`semantic_engine`) or on a `SemanticResult`
        (`result`) -- only `self._*` (this class's own attributes) is
        permitted.
        """
        source = inspect.getsource(compression_engine_module)
        forbidden_accesses = (
            "semantic_engine._",
            "result._",
        )
        for forbidden in forbidden_accesses:
            self.assert_true(
                forbidden not in source,
                f"CompressionEngine must not access a private attribute via '{forbidden}'",
            )
