"""Real engineering tests for EP-026 - Semantic Search.

Builds real `SemanticCandidate`/`SemanticResult`/`SemanticProvider`/
`SemanticManager`/`SemanticEngine`/`SemanticService`/`SemanticModule`
instances -- composed with real `EmbeddingManager`/`EmbeddingEngine`
(EP-021), `KnowledgeService` (EP-024) and `LongTermMemoryService`
(EP-025) instances loaded from a temporary `Config` -- and drives them
exactly as a caller would, no mocked internals, matching every other
EP's test suite in this project.

Semantic Search (EP-026) is a new, independent package
(`src/core/semantic/`) that performs meaning-based similarity search
over Knowledge Base and Long-Term Memory records, using vectors
produced by the Embedding Engine -- never touching any of those three
subsystems' internals, only their public APIs. This suite covers:

1. The domain model: `SemanticCandidate`, `SemanticResult`.
2. The provider abstraction: `SemanticProvider` (abstract contract),
   `DefaultSemanticProvider` (built-in cosine-similarity provider).
3. `SemanticManager`: configuration validation, registration,
   enable/disable, active-provider switching, status, and the default
   `top_k` / `similarity_threshold` parameters.
4. `SemanticEngine`: the query -> candidates -> ranked-results
   pipeline, integrated with real EP-021/EP-024/EP-025 instances.
5. `SemanticService`/`SemanticModule`: configuration-driven
   construction, graceful degradation, and every CLI command
   ("status", "providers", "use", "search", "threshold", "help").
6. Architecture compliance: no forbidden imports, no duplicated
   provider/manager/storage logic, no future-EP functionality, no
   private-API access into EP-021/EP-024/EP-025, and a real
   `Bootstrap` run proving normal wiring, dependency injection, and
   graceful degradation on invalid configuration (both for Semantic
   Search itself and for its hard dependency, the Embedding Engine).
"""

from __future__ import annotations

import inspect
import os
import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.config import Config
from src.core.embedding.engine import EmbeddingEngine
from src.core.embedding.manager import EmbeddingManager
from src.core.semantic import semantic_engine as semantic_engine_module
from src.core.semantic import semantic_manager as semantic_manager_module
from src.core.semantic import semantic_provider as semantic_provider_module
from src.core.semantic.semantic_engine import (
    PLACEHOLDER_EMBEDDING_PROVIDER_NAME,
    EmptySemanticQueryError,
    NoSemanticProviderSelectedError,
    SemanticEngine,
    SemanticEngineError,
)
from src.core.semantic.semantic_manager import (
    SemanticManager,
    SemanticProviderNotFoundError,
    SemanticProviderRegistryError,
)
from src.core.semantic.semantic_provider import (
    DefaultSemanticProvider,
    SemanticConfigurationError,
    SemanticError,
    SemanticProvider,
    SemanticProviderError,
    SemanticProviderStatus,
)
from src.core.semantic.semantic_result import (
    SOURCE_KNOWLEDGE,
    SOURCE_LONG_TERM_MEMORY,
    SemanticCandidate,
    SemanticResult,
)
from src.modules.semantic_module import SemanticModule
from src.services.knowledge_service import KnowledgeService
from src.services.long_term_memory_service import LongTermMemoryService
from src.services.semantic_service import SemanticService
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

_LONG_TERM_MEMORY_YAML = "long_term_memory:\n  enabled: true\n  default_provider: \"knowledge\"\n"

_DEFAULT_SEMANTIC_YAML = (
    "semantic:\n"
    "  enabled: true\n"
    "  default_provider: \"semantic\"\n"
    "  top_k: 5\n"
    "  similarity_threshold: 0.0\n"
)

# Matches the real, shipped config/config.yaml default exactly -- used by the H1
# regression tests, which must exercise the actual default, not a test-only 0.0
# threshold that would silently mask the very bug being regression-tested.
_REAL_DEFAULT_THRESHOLD_SEMANTIC_YAML = (
    "semantic:\n"
    "  enabled: true\n"
    "  default_provider: \"semantic\"\n"
    "  top_k: 5\n"
    "  similarity_threshold: 0.70\n"
)

_DISABLED_SEMANTIC_YAML = (
    "semantic:\n"
    "  enabled: false\n"
    "  default_provider: \"semantic\"\n"
    "  top_k: 5\n"
    "  similarity_threshold: 0.0\n"
)

_INVALID_PROVIDER_SEMANTIC_YAML = (
    "semantic:\n"
    "  enabled: true\n"
    "  default_provider: \"\"\n"
    "  top_k: 5\n"
    "  similarity_threshold: 0.0\n"
)

_INVALID_THRESHOLD_SEMANTIC_YAML = (
    "semantic:\n"
    "  enabled: true\n"
    "  default_provider: \"semantic\"\n"
    "  top_k: 5\n"
    "  similarity_threshold: 3.5\n"
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
    "  enabled: {embedding_enabled}\n"
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
    "  default_provider: \"{semantic_default_provider}\"\n"
    "  top_k: 5\n"
    "  similarity_threshold: 0.70\n"
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
    semantic_default_provider: str = "semantic",
    embedding_enabled: bool = True,
) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(
        _FULL_BOOTSTRAP_CONFIG_YAML.format(
            semantic_default_provider=semantic_default_provider,
            embedding_enabled=str(embedding_enabled).lower(),
        ),
        encoding="utf-8",
    )


class _RecordingSemanticProvider(SemanticProvider):
    """A minimal, independent SemanticProvider used only to test SemanticManager.

    Always returns an empty result set, entirely separate from
    `DefaultSemanticProvider`, so tests can prove `SemanticManager`
    truly delegates to whichever provider is active rather than always
    using the built-in one.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def provider_name(self) -> str:
        return self._name

    def search(self, query_vector, candidates, top_k, threshold):
        return []

    def rank(self, results):
        return list(results)


class _ChdirEmbeddingFixture:
    """Builds a real EmbeddingManager/EmbeddingEngine pair from a temporary directory."""

    def __init__(self, tmp_path: Path) -> None:
        config = _write_config(tmp_path, _EMBEDDING_YAML)
        self.manager = EmbeddingManager(config=config)
        self.engine = EmbeddingEngine(manager=self.manager)


class _FakeEmbeddingProvider:
    """A minimal duck-typed stand-in exposing only `provider_name()`.

    Used solely to prove H1's placeholder-provider detection is
    genuinely name-specific -- it must not fire for a provider named
    anything other than `PLACEHOLDER_EMBEDDING_PROVIDER_NAME`.
    """

    def __init__(self, name: str) -> None:
        self._name = name

    def provider_name(self) -> str:
        return self._name


class _FakeEmbeddingManager:
    """A minimal duck-typed stand-in exposing only `get_current()`.

    `SemanticEngine._uses_placeholder_embedding_provider()` calls only
    this one public method, so a full `EmbeddingManager` is
    unnecessary to isolate that specific behavior.
    """

    def __init__(self, current_provider_name: str | None) -> None:
        self._current = (
            _FakeEmbeddingProvider(current_provider_name)
            if current_provider_name is not None
            else None
        )

    def get_current(self):
        return self._current


@TestRegistry.register
class SemanticSearchTest(BaseTest):
    """Real tests covering EP-026's Semantic Search."""

    NAME = "EP026"

    def run(self):
        """Execute every Semantic Search check and return the aggregated result."""
        # Domain model
        self._test_candidate_and_result_construction()

        # SemanticProvider abstract contract
        self._test_provider_is_abstract()

        # DefaultSemanticProvider
        self._test_default_provider_name()
        self._test_default_provider_identical_vectors_score_one()
        self._test_default_provider_orthogonal_vectors_score_zero()
        self._test_default_provider_opposite_vectors_score_negative_one()
        self._test_default_provider_zero_vector_scores_zero()
        self._test_default_provider_threshold_filters_results()
        self._test_default_provider_top_k_limits_results()
        self._test_default_provider_rank_is_deterministic_on_ties()
        self._test_default_provider_invalid_top_k_raises()
        self._test_default_provider_health_and_status()

        # SemanticManager
        self._test_manager_registers_default_provider()
        self._test_manager_config_defaults()
        self._test_manager_invalid_enabled_raises()
        self._test_manager_invalid_top_k_raises()
        self._test_manager_invalid_threshold_raises()
        self._test_manager_invalid_default_provider_raises()
        self._test_manager_duplicate_registration_raises()
        self._test_manager_unknown_provider_raises()
        self._test_manager_set_current_switches_provider()
        self._test_manager_disable_clears_current()
        self._test_manager_get_current_none_when_disabled()
        self._test_manager_current_provider_name_none_when_disabled_via_config()
        self._test_manager_set_similarity_threshold_validates()
        self._test_manager_second_provider_registers_without_stealing_active()

        # SemanticEngine (integration with real EP-021/EP-024/EP-025)
        self._test_engine_empty_query_raises()
        self._test_engine_no_provider_selected_raises()
        self._test_engine_no_candidates_returns_empty()
        self._test_engine_searches_knowledge_records()
        self._test_engine_searches_long_term_memory_records()
        self._test_engine_combines_both_sources()
        self._test_engine_top_k_and_threshold_overrides()
        self._test_engine_blank_records_are_excluded()
        self._test_engine_deduplicates_records_shared_by_knowledge_and_long_term_memory()

        # H1 fix: placeholder (non-semantic) embedding provider detection
        self._test_engine_no_warning_without_embedding_manager()
        self._test_engine_warns_for_placeholder_embedding_provider()
        self._test_engine_no_warning_for_non_placeholder_provider()
        self._test_engine_no_threshold_relaxation_for_placeholder_provider()
        self._test_engine_explicit_threshold_still_wins_for_placeholder_provider()
        self._test_engine_non_placeholder_provider_keeps_configured_threshold()

        # SemanticService
        self._test_service_status_and_providers()
        self._test_service_status_includes_embedding_provider_warning()
        self._test_service_use_unknown_provider_fails_gracefully()
        self._test_service_search_success_and_failure()
        self._test_service_threshold_get_set()
        self._test_service_disable()

        # SemanticModule (CLI)
        self._test_cli_help_lists_commands()
        self._test_cli_status_command()
        self._test_cli_status_command_shows_placeholder_warning()
        self._test_cli_providers_command()
        self._test_cli_use_command()
        self._test_cli_search_command_usage_and_results()
        self._test_cli_threshold_command()
        self._test_cli_unknown_action()

        # Bootstrap wiring (dependency injection + integration + graceful degradation)
        self._test_bootstrap_registers_semantic_module()
        self._test_bootstrap_degrades_gracefully_on_invalid_semantic_config()
        self._test_bootstrap_degrades_when_embedding_unavailable()
        self._test_bootstrap_default_config_search_returns_results()

        # Architectural acceptance criteria
        self._test_no_forbidden_imports()
        self._test_manager_owns_no_storage_state()
        self._test_exception_hierarchy()
        self._test_only_expected_provider_classes_exist()
        self._test_no_private_api_access_on_foreign_objects()

        return self.result

    # ---------- Domain model ----------

    def _test_candidate_and_result_construction(self) -> None:
        """SemanticCandidate/SemanticResult carry their fields through unchanged."""
        candidate = SemanticCandidate(
            source=SOURCE_KNOWLEDGE, identifier="doc1", text="hello world", vector=[1.0, 0.0]
        )
        self.assert_equal(candidate.source, SOURCE_KNOWLEDGE)
        self.assert_equal(candidate.identifier, "doc1")
        self.assert_equal(candidate.metadata, {})

        result = SemanticResult(
            source=SOURCE_LONG_TERM_MEMORY, identifier="mem1", text="hi", score=0.42
        )
        self.assert_equal(result.source, SOURCE_LONG_TERM_MEMORY)
        self.assert_equal(result.score, 0.42)
        self.assert_equal(result.metadata, {})

    # ---------- SemanticProvider abstract contract ----------

    def _test_provider_is_abstract(self) -> None:
        """SemanticProvider cannot be instantiated directly."""
        try:
            SemanticProvider()  # type: ignore[abstract]
        except TypeError:
            self.result.add_pass()
        else:
            self.assert_true(False, "SemanticProvider should not be directly instantiable")

    # ---------- DefaultSemanticProvider ----------

    def _test_default_provider_name(self) -> None:
        provider = DefaultSemanticProvider()
        self.assert_equal(provider.provider_name(), "semantic")

    def _test_default_provider_identical_vectors_score_one(self) -> None:
        provider = DefaultSemanticProvider()
        candidate = SemanticCandidate(
            source=SOURCE_KNOWLEDGE, identifier="a", text="x", vector=[1.0, 2.0, 3.0]
        )
        results = provider.search([1.0, 2.0, 3.0], [candidate], top_k=5, threshold=-1.0)
        self.assert_equal(len(results), 1)
        self.assert_true(abs(results[0].score - 1.0) < 1e-9, "identical vectors should score ~1.0")

    def _test_default_provider_orthogonal_vectors_score_zero(self) -> None:
        provider = DefaultSemanticProvider()
        candidate = SemanticCandidate(
            source=SOURCE_KNOWLEDGE, identifier="a", text="x", vector=[0.0, 1.0]
        )
        results = provider.search([1.0, 0.0], [candidate], top_k=5, threshold=-1.0)
        self.assert_equal(len(results), 1)
        self.assert_true(abs(results[0].score) < 1e-9, "orthogonal vectors should score ~0.0")

    def _test_default_provider_opposite_vectors_score_negative_one(self) -> None:
        provider = DefaultSemanticProvider()
        candidate = SemanticCandidate(
            source=SOURCE_KNOWLEDGE, identifier="a", text="x", vector=[-1.0, -2.0, -3.0]
        )
        results = provider.search([1.0, 2.0, 3.0], [candidate], top_k=5, threshold=-1.0)
        self.assert_equal(len(results), 1)
        self.assert_true(
            abs(results[0].score - (-1.0)) < 1e-9, "opposite vectors should score ~-1.0"
        )

    def _test_default_provider_zero_vector_scores_zero(self) -> None:
        """A zero-magnitude vector never divides by zero; it simply scores 0.0."""
        provider = DefaultSemanticProvider()
        candidate = SemanticCandidate(
            source=SOURCE_KNOWLEDGE, identifier="a", text="x", vector=[0.0, 0.0]
        )
        results = provider.search([1.0, 1.0], [candidate], top_k=5, threshold=-1.0)
        self.assert_equal(len(results), 1)
        self.assert_equal(results[0].score, 0.0)

    def _test_default_provider_threshold_filters_results(self) -> None:
        provider = DefaultSemanticProvider()
        near = SemanticCandidate(source=SOURCE_KNOWLEDGE, identifier="near", text="x", vector=[1.0, 0.0])
        far = SemanticCandidate(source=SOURCE_KNOWLEDGE, identifier="far", text="y", vector=[0.0, 1.0])
        results = provider.search([1.0, 0.0], [near, far], top_k=5, threshold=0.5)
        self.assert_equal(len(results), 1)
        self.assert_equal(results[0].identifier, "near")

    def _test_default_provider_top_k_limits_results(self) -> None:
        provider = DefaultSemanticProvider()
        candidates = [
            SemanticCandidate(source=SOURCE_KNOWLEDGE, identifier=f"c{i}", text="x", vector=[1.0, 0.0])
            for i in range(5)
        ]
        results = provider.search([1.0, 0.0], candidates, top_k=2, threshold=-1.0)
        self.assert_equal(len(results), 2)

    def _test_default_provider_rank_is_deterministic_on_ties(self) -> None:
        """Equal scores are broken by (source, identifier) for a reproducible order."""
        provider = DefaultSemanticProvider()
        results = [
            SemanticResult(source=SOURCE_KNOWLEDGE, identifier="zeta", text="", score=0.5),
            SemanticResult(source=SOURCE_KNOWLEDGE, identifier="alpha", text="", score=0.5),
        ]
        ranked = provider.rank(results)
        self.assert_equal([entry.identifier for entry in ranked], ["alpha", "zeta"])

    def _test_default_provider_invalid_top_k_raises(self) -> None:
        provider = DefaultSemanticProvider()
        try:
            provider.search([1.0], [], top_k=0, threshold=0.0)
        except SemanticProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "top_k=0 should raise SemanticProviderError")

    def _test_default_provider_health_and_status(self) -> None:
        provider = DefaultSemanticProvider()
        self.assert_equal(provider.status(), SemanticProviderStatus.AVAILABLE)
        self.assert_true(provider.is_available())
        health = provider.health()
        self.assert_true(health.available)

    # ---------- SemanticManager ----------

    def _test_manager_registers_default_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DEFAULT_SEMANTIC_YAML)
            manager = SemanticManager(config=config)
            self.assert_equal(manager.current_provider_name(), "semantic")
            self.assert_true(manager.get_current() is not None)
            names = [provider.provider_name() for provider in manager.list_providers()]
            self.assert_equal(names, ["semantic"])

    def _test_manager_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "semantic:\n  enabled: true\n")
            manager = SemanticManager(config=config)
            self.assert_equal(manager.top_k(), 5)
            self.assert_equal(manager.similarity_threshold(), 0.70)
            self.assert_true(manager.is_enabled())

    def _test_manager_invalid_enabled_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "semantic:\n  enabled: \"yes\"\n")
            try:
                SemanticManager(config=config)
            except SemanticConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "non-boolean 'semantic.enabled' should raise")

    def _test_manager_invalid_top_k_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), "semantic:\n  top_k: 0\n")
            try:
                SemanticManager(config=config)
            except SemanticConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "non-positive 'semantic.top_k' should raise")

    def _test_manager_invalid_threshold_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _INVALID_THRESHOLD_SEMANTIC_YAML)
            try:
                SemanticManager(config=config)
            except SemanticConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "out-of-range 'semantic.similarity_threshold' should raise")

    def _test_manager_invalid_default_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _INVALID_PROVIDER_SEMANTIC_YAML)
            try:
                SemanticManager(config=config)
            except SemanticConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "empty 'semantic.default_provider' should raise")

    def _test_manager_duplicate_registration_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DEFAULT_SEMANTIC_YAML)
            manager = SemanticManager(config=config)
            try:
                manager.register_provider(DefaultSemanticProvider())
            except SemanticProviderRegistryError:
                self.result.add_pass()
            else:
                self.assert_true(False, "duplicate provider registration should raise")

    def _test_manager_unknown_provider_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DEFAULT_SEMANTIC_YAML)
            manager = SemanticManager(config=config)
            try:
                manager.set_current("does-not-exist")
            except SemanticProviderNotFoundError:
                self.result.add_pass()
            else:
                self.assert_true(False, "unknown provider name should raise")

    def _test_manager_set_current_switches_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DEFAULT_SEMANTIC_YAML)
            manager = SemanticManager(config=config)
            secondary = _RecordingSemanticProvider("secondary")
            manager.register_provider(secondary)
            manager.set_current("secondary")
            self.assert_equal(manager.current_provider_name(), "secondary")
            self.assert_true(manager.get_current() is secondary)

    def _test_manager_disable_clears_current(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DEFAULT_SEMANTIC_YAML)
            manager = SemanticManager(config=config)
            manager.disable()
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.get_current() is None)
            self.assert_true(manager.current_provider_name() is None)

    def _test_manager_get_current_none_when_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DISABLED_SEMANTIC_YAML)
            manager = SemanticManager(config=config)
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.get_current() is None)

    def _test_manager_current_provider_name_none_when_disabled_via_config(self) -> None:
        """Regression test for independent-audit finding M1.

        Before the fix, a manager built from 'semantic.enabled: false'
        (disabled from the start, never via `.disable()`) still
        resolved and stored a current-provider name internally, so
        `current_provider_name()` incorrectly returned "semantic" even
        though `is_enabled()` was False and `get_current()` correctly
        returned None. `current_provider_name()` must be consistent
        with `get_current()` in both disablement paths.
        """
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DISABLED_SEMANTIC_YAML)
            manager = SemanticManager(config=config)
            self.assert_false(manager.is_enabled())
            self.assert_true(manager.current_provider_name() is None)
            self.assert_true(manager.get_current() is None)

        # The other disablement path -- disable() at runtime -- must behave identically.
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DEFAULT_SEMANTIC_YAML)
            manager = SemanticManager(config=config)
            self.assert_equal(manager.current_provider_name(), "semantic")
            manager.disable()
            self.assert_true(manager.current_provider_name() is None)

    def _test_manager_set_similarity_threshold_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DEFAULT_SEMANTIC_YAML)
            manager = SemanticManager(config=config)
            manager.set_similarity_threshold(0.9)
            self.assert_equal(manager.similarity_threshold(), 0.9)
            try:
                manager.set_similarity_threshold(1.5)
            except SemanticConfigurationError:
                self.result.add_pass()
            else:
                self.assert_true(False, "threshold above 1.0 should raise")

    def _test_manager_second_provider_registers_without_stealing_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DEFAULT_SEMANTIC_YAML)
            manager = SemanticManager(config=config)
            manager.register_provider(_RecordingSemanticProvider("secondary"))
            self.assert_equal(manager.current_provider_name(), "semantic")
            names = sorted(provider.provider_name() for provider in manager.list_providers())
            self.assert_equal(names, ["secondary", "semantic"])

    # ---------- SemanticEngine ----------

    def _build_engine(
        self,
        tmp_path: Path,
        with_knowledge: bool = True,
        with_long_term_memory: bool = True,
        with_embedding_manager: bool = False,
    ) -> tuple[SemanticEngine, KnowledgeService | None, LongTermMemoryService | None]:
        """Build a real SemanticEngine wired to real EP-021/EP-024/EP-025 instances.

        Args:
            with_embedding_manager: If True, wires the real
                `EmbeddingManager` behind `embedding.engine` into the
                engine too (as EP-026's H1 fix requires for
                placeholder-embedding-provider detection). Defaults to
                False so tests unrelated to that detection are
                unaffected by it.
        """
        semantic_config = _write_config(tmp_path / "semantic", _DEFAULT_SEMANTIC_YAML)
        semantic_manager = SemanticManager(config=semantic_config)

        embedding = _ChdirEmbeddingFixture(tmp_path / "embedding")

        knowledge_service: KnowledgeService | None = None
        long_term_memory_service: LongTermMemoryService | None = None
        if with_knowledge:
            knowledge_config = _write_config(tmp_path / "knowledge", _KNOWLEDGE_YAML)
            knowledge_service = KnowledgeService(config=knowledge_config)
        if with_long_term_memory:
            if knowledge_service is None:
                knowledge_config = _write_config(tmp_path / "knowledge2", _KNOWLEDGE_YAML)
                ltm_knowledge_service = KnowledgeService(config=knowledge_config)
            else:
                ltm_knowledge_service = knowledge_service
            ltm_config = _write_config(tmp_path / "ltm", _LONG_TERM_MEMORY_YAML)
            long_term_memory_service = LongTermMemoryService(
                config=ltm_config, knowledge_service=ltm_knowledge_service
            )

        engine = SemanticEngine(
            manager=semantic_manager,
            embedding_engine=embedding.engine,
            embedding_manager=embedding.manager if with_embedding_manager else None,
            knowledge_service=knowledge_service,
            long_term_memory_service=long_term_memory_service,
        )
        return engine, knowledge_service, long_term_memory_service

    def _test_engine_empty_query_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _knowledge, _ltm = self._build_engine(Path(tmp))
            try:
                engine.search("   ")
            except EmptySemanticQueryError:
                self.result.add_pass()
            else:
                self.assert_true(False, "blank query should raise EmptySemanticQueryError")

    def _test_engine_no_provider_selected_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _knowledge, _ltm = self._build_engine(Path(tmp))
            # Reach through the public disable() API -- not a private attribute.
            engine._manager.disable()  # noqa: SLF001 -- SemanticEngine's own collaborator
            try:
                engine.search("hello")
            except NoSemanticProviderSelectedError:
                self.result.add_pass()
            else:
                self.assert_true(False, "disabled subsystem should raise")

    def _test_engine_no_candidates_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _knowledge, _ltm = self._build_engine(
                Path(tmp), with_knowledge=False, with_long_term_memory=False
            )
            results = engine.search("anything")
            self.assert_equal(results, [])

    def _test_engine_searches_knowledge_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, knowledge, _ltm = self._build_engine(
                Path(tmp), with_knowledge=True, with_long_term_memory=False
            )
            knowledge.store("greeting", "hello there, general kenobi")
            knowledge.store("weather", "it is raining in london today")
            results = engine.search("hello there", top_k=5, threshold=-1.0)
            self.assert_true(len(results) >= 1)
            self.assert_true(all(result.source == SOURCE_KNOWLEDGE for result in results))
            identifiers = {result.identifier for result in results}
            self.assert_true("greeting" in identifiers or "weather" in identifiers)

    def _test_engine_searches_long_term_memory_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _knowledge, ltm = self._build_engine(
                Path(tmp), with_knowledge=False, with_long_term_memory=True
            )
            ltm.store("mem-1", "the project deadline is next friday")
            results = engine.search("deadline", top_k=5, threshold=-1.0)
            self.assert_true(len(results) >= 1)
            self.assert_true(all(result.source == SOURCE_LONG_TERM_MEMORY for result in results))

    def _test_engine_combines_both_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, knowledge, ltm = self._build_engine(Path(tmp))
            knowledge.store("k1", "knowledge base record about cats")
            ltm.store("m1", "long term memory record about dogs")
            results = engine.search("animals", top_k=10, threshold=-1.0)
            sources = {result.source for result in results}
            self.assert_equal(sources, {SOURCE_KNOWLEDGE, SOURCE_LONG_TERM_MEMORY})

    def _test_engine_top_k_and_threshold_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, knowledge, _ltm = self._build_engine(
                Path(tmp), with_knowledge=True, with_long_term_memory=False
            )
            for index in range(4):
                knowledge.store(f"k{index}", f"record number {index} about topic {index}")
            results = engine.search("topic", top_k=2, threshold=-1.0)
            self.assert_true(len(results) <= 2)

            # A threshold of 1.01 is above any real cosine similarity, so
            # nothing qualifies -- proving the override actually reaches
            # the provider rather than being ignored.
            no_results = engine.search("topic", top_k=10, threshold=1.01)
            self.assert_equal(no_results, [])

    def _test_engine_blank_records_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, knowledge, _ltm = self._build_engine(
                Path(tmp), with_knowledge=True, with_long_term_memory=False
            )
            knowledge.store("blank", "   ")
            knowledge.store("real", "an actual sentence to search against")
            results = engine.search("sentence", top_k=10, threshold=-1.0)
            identifiers = {result.identifier for result in results}
            self.assert_true("blank" not in identifiers)

    def _test_engine_deduplicates_records_shared_by_knowledge_and_long_term_memory(self) -> None:
        """Regression test: a record must never be returned twice under two source labels.

        EP-025's built-in `KnowledgeBackedLongTermProvider` persists
        Long-Term Memory records inside `KnowledgeService`'s own
        storage under the record's own id as the key -- so, in real
        Bootstrap wiring (a shared `KnowledgeService` instance), the
        very same physical record is reachable through both
        `knowledge_service.list_records()` and
        `long_term_memory_service.list_memories()`. It must appear
        exactly once in search results, labeled `SOURCE_LONG_TERM_MEMORY`.
        """
        with tempfile.TemporaryDirectory() as tmp:
            engine, _knowledge, ltm = self._build_engine(Path(tmp))
            ltm.store("shared-1", "the user prefers dark mode interfaces")
            results = engine.search("dark mode interfaces", top_k=10, threshold=-1.0)
            matches = [result for result in results if result.identifier == "shared-1"]
            self.assert_equal(len(matches), 1)
            self.assert_equal(matches[0].source, SOURCE_LONG_TERM_MEMORY)

    # ---------- H1 fix: placeholder (non-semantic) embedding provider detection ----------

    def _test_engine_no_warning_without_embedding_manager(self) -> None:
        """Without an EmbeddingManager supplied, detection is simply skipped (no crash, no warning)."""
        with tempfile.TemporaryDirectory() as tmp:
            engine, _knowledge, _ltm = self._build_engine(Path(tmp), with_embedding_manager=False)
            self.assert_true(engine.embedding_provider_warning() is None)

    def _test_engine_warns_for_placeholder_embedding_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine, _knowledge, _ltm = self._build_engine(Path(tmp), with_embedding_manager=True)
            warning = engine.embedding_provider_warning()
            self.assert_true(warning is not None)
            self.assert_true(PLACEHOLDER_EMBEDDING_PROVIDER_NAME in warning)

    def _test_engine_no_warning_for_non_placeholder_provider(self) -> None:
        """Detection must be name-specific -- any provider other than "local" produces no warning."""
        with tempfile.TemporaryDirectory() as tmp:
            semantic_config = _write_config(Path(tmp) / "semantic", _DEFAULT_SEMANTIC_YAML)
            semantic_manager = SemanticManager(config=semantic_config)
            embedding = _ChdirEmbeddingFixture(Path(tmp) / "embedding")
            engine = SemanticEngine(
                manager=semantic_manager,
                embedding_engine=embedding.engine,
                embedding_manager=_FakeEmbeddingManager(current_provider_name="cloud"),
            )
            self.assert_true(engine.embedding_provider_warning() is None)

            # No embedding provider currently selected at all -- also no warning.
            engine_no_current = SemanticEngine(
                manager=semantic_manager,
                embedding_engine=embedding.engine,
                embedding_manager=_FakeEmbeddingManager(current_provider_name=None),
            )
            self.assert_true(engine_no_current.embedding_provider_warning() is None)

    def _test_engine_no_threshold_relaxation_for_placeholder_provider(self) -> None:
        """Regression test for independent-audit finding H1 (revised).

        An earlier fix relaxed the effective threshold toward 0.0 for
        the placeholder "local" provider. Root-cause investigation
        proved that was wrong: `LocalHashEmbeddingProvider` hashes each
        text as a whole (SHA-256's avalanche property), so any two
        non-identical texts -- related or not -- produce statistically
        uncorrelated scores (empirically measured across eight
        reworded-sentence pairs: -0.60 to +0.34, no consistent bias for
        "more related"). Relaxing the threshold doesn't reliably find
        related content -- it only admits a coin-flip ~50% of *all*
        candidates. The corrected fix makes no threshold adjustment at
        all: 'semantic.similarity_threshold' is used exactly as
        configured for every provider, always. This test asserts that
        deterministic invariant directly, rather than asserting whether
        one specific reworded query happens to score above or below any
        particular number (which -- being genuine hash noise -- is not
        a stable, reproducible fact to assert on; it was exactly this
        instability that broke the previous version of this test).
        """
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            semantic_config = _write_config(
                tmp_path / "semantic", _REAL_DEFAULT_THRESHOLD_SEMANTIC_YAML
            )
            semantic_manager = SemanticManager(config=semantic_config)
            self.assert_equal(semantic_manager.similarity_threshold(), 0.70)
            embedding = _ChdirEmbeddingFixture(tmp_path / "embedding")
            knowledge_config = _write_config(tmp_path / "knowledge", _KNOWLEDGE_YAML)
            knowledge = KnowledgeService(config=knowledge_config)
            knowledge.store("doc", "The Eiffel Tower is located in Paris, France")
            knowledge.store("other", "Python is a popular programming language")

            engine = SemanticEngine(
                manager=semantic_manager,
                embedding_engine=embedding.engine,
                embedding_manager=embedding.manager,
                knowledge_service=knowledge,
            )
            self.assert_true(engine._uses_placeholder_embedding_provider())  # noqa: SLF001

            # The deterministic invariant: with the placeholder provider active,
            # omitting `threshold` must resolve to exactly the configured value --
            # never adjusted, whatever that value is.
            self.assert_equal(engine._default_threshold(), 0.70)  # noqa: SLF001

            # Proven the same way at the observable API level: for any query, omitting
            # `threshold` must return byte-for-byte the same results as explicitly
            # passing the configured threshold. This holds regardless of what the
            # hash provider's noisy scores for that query happen to be -- it is a
            # structural property of "no relaxation happens", not a claim about any
            # specific similarity value.
            for query in (
                "The Eiffel Tower is located in Paris, France",  # exact duplicate of "doc"
                "The Eiffel Tower is located in Paris",  # reworded, not identical
                "completely unrelated query about weather",
            ):
                default_results = engine.search(query)
                explicit_results = engine.search(query, threshold=0.70)
                self.assert_equal(
                    [(r.identifier, r.score) for r in default_results],
                    [(r.identifier, r.score) for r in explicit_results],
                )

            # And the feature's one genuinely reliable use case still works: an
            # exact-duplicate query deterministically scores 1.0 and is found, even
            # at the real, unrelaxed, shipped default threshold of 0.70.
            exact_match_results = engine.search("The Eiffel Tower is located in Paris, France")
            self.assert_true(any(r.identifier == "doc" for r in exact_match_results))

    def _test_engine_explicit_threshold_still_wins_for_placeholder_provider(self) -> None:
        """An explicitly passed threshold is always honored, regardless of provider."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            semantic_config = _write_config(
                tmp_path / "semantic", _REAL_DEFAULT_THRESHOLD_SEMANTIC_YAML
            )
            semantic_manager = SemanticManager(config=semantic_config)
            embedding = _ChdirEmbeddingFixture(tmp_path / "embedding")
            knowledge_config = _write_config(tmp_path / "knowledge", _KNOWLEDGE_YAML)
            knowledge = KnowledgeService(config=knowledge_config)
            knowledge.store("doc", "The Eiffel Tower is located in Paris, France")

            engine = SemanticEngine(
                manager=semantic_manager,
                embedding_engine=embedding.engine,
                embedding_manager=embedding.manager,
                knowledge_service=knowledge,
            )
            # An explicit low threshold (-1.0) must admit the candidate regardless of
            # the placeholder provider's noisy score for this non-identical query --
            # proving the explicit bound is honored, not silently raised back to 0.70.
            results = engine.search("The Eiffel Tower is located in Paris", threshold=-1.0)
            self.assert_equal(len(results), 1)
            self.assert_equal(results[0].identifier, "doc")

    def _test_engine_non_placeholder_provider_keeps_configured_threshold(self) -> None:
        """When the active provider is not the placeholder, the configured threshold applies unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            semantic_config = _write_config(
                tmp_path / "semantic", _REAL_DEFAULT_THRESHOLD_SEMANTIC_YAML
            )
            semantic_manager = SemanticManager(config=semantic_config)
            embedding = _ChdirEmbeddingFixture(tmp_path / "embedding")
            engine = SemanticEngine(
                manager=semantic_manager,
                embedding_engine=embedding.engine,
                embedding_manager=_FakeEmbeddingManager(current_provider_name="cloud"),
            )
            self.assert_equal(engine._default_threshold(), 0.70)  # noqa: SLF001

    # ---------- SemanticService ----------

    def _build_service(
        self, tmp_path: Path, with_embedding_manager: bool = False
    ) -> tuple[SemanticService, KnowledgeService]:
        engine, knowledge, _ltm = self._build_engine(
            tmp_path,
            with_knowledge=True,
            with_long_term_memory=False,
            with_embedding_manager=with_embedding_manager,
        )
        service = SemanticService(manager=engine._manager, engine=engine)  # noqa: SLF001
        return service, knowledge

    def _test_service_status_and_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            status = service.status()
            self.assert_true(status.enabled)
            self.assert_equal(status.current_provider, "semantic")
            self.assert_equal(status.registered_provider_count, 1)
            self.assert_true(status.embedding_provider_warning is None)

            providers = service.list_providers()
            self.assert_equal(len(providers), 1)
            self.assert_equal(providers[0].name, "semantic")
            self.assert_true(providers[0].is_current)

    def _test_service_status_includes_embedding_provider_warning(self) -> None:
        """SemanticService.status() must surface SemanticEngine.embedding_provider_warning()."""
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp), with_embedding_manager=True)
            status = service.status()
            self.assert_true(status.embedding_provider_warning is not None)
            self.assert_true(PLACEHOLDER_EMBEDDING_PROVIDER_NAME in status.embedding_provider_warning)

    def _test_service_use_unknown_provider_fails_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            outcome = service.use_provider("does-not-exist")
            self.assert_false(outcome.success)

    def _test_service_search_success_and_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, knowledge = self._build_service(Path(tmp))
            knowledge.store("doc", "a sentence about robots and automation")
            outcome = service.search("robots", top_k=5, threshold=-1.0)
            self.assert_true(outcome.success)
            self.assert_true(len(outcome.results) >= 1)

            failure = service.search("")
            self.assert_false(failure.success)
            self.assert_true(failure.error != "")

    def _test_service_threshold_get_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            self.assert_equal(service.threshold(), 0.0)
            result = service.set_threshold(0.42)
            self.assert_true(result.success)
            self.assert_equal(service.threshold(), 0.42)
            bad = service.set_threshold(9.0)
            self.assert_false(bad.success)

    def _test_service_disable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            result = service.disable()
            self.assert_true(result.success)
            self.assert_false(service.status().enabled)

    # ---------- SemanticModule (CLI) ----------

    def _test_cli_help_lists_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            module = SemanticModule(service)
            self.assert_equal(module.name, "semantic")
            result = module.execute("help", [])
            self.assert_true(result.success)
            for command in ("status", "providers", "use", "search", "threshold"):
                self.assert_true(command in result.message)

    def _test_cli_status_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            module = SemanticModule(service)
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Enabled" in result.message)
            self.assert_true("Warning" not in result.message)

    def _test_cli_status_command_shows_placeholder_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp), with_embedding_manager=True)
            module = SemanticModule(service)
            result = module.execute("status", [])
            self.assert_true(result.success)
            self.assert_true("Warning" in result.message)
            self.assert_true(PLACEHOLDER_EMBEDDING_PROVIDER_NAME in result.message)

    def _test_cli_providers_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            module = SemanticModule(service)
            result = module.execute("providers", [])
            self.assert_true(result.success)
            self.assert_true("semantic" in result.message)

    def _test_cli_use_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            module = SemanticModule(service)
            self.assert_false(module.execute("use", []).success)
            self.assert_false(module.execute("use", ["nope"]).success)
            self.assert_true(module.execute("use", ["semantic"]).success)

    def _test_cli_search_command_usage_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, knowledge = self._build_service(Path(tmp))
            module = SemanticModule(service)
            self.assert_false(module.execute("search", []).success)

            knowledge.store("doc", "an article discussing renewable energy")
            result = module.execute("search", ["renewable", "energy"])
            self.assert_true(result.success)

    def _test_cli_threshold_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            module = SemanticModule(service)
            result = module.execute("threshold", [])
            self.assert_true(result.success)
            self.assert_true("threshold" in result.message.lower())

    def _test_cli_unknown_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            module = SemanticModule(service)
            result = module.execute("bogus", [])
            self.assert_false(result.success)

    # ---------- Bootstrap wiring ----------

    def _test_bootstrap_registers_semantic_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.run()
                service = bootstrap.semantic_service
                self.assert_true(service is not None)
                status = service.status()
                self.assert_true(status.enabled)
                self.assert_equal(status.current_provider, "semantic")

                result = bootstrap._command_router.dispatch("semantic status")  # noqa: SLF001
                self.assert_true(result.success)

    def _test_bootstrap_degrades_gracefully_on_invalid_semantic_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, semantic_default_provider="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.run()  # must not raise -- Semantic Search degrades, Jarvis still starts
                self.assert_true(bootstrap.semantic_service is None)
                # The rest of the application is unaffected.
                self.assert_true(bootstrap.knowledge_service is not None)
                self.assert_true(bootstrap.embedding_service is not None)

    def _test_bootstrap_degrades_when_embedding_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory, embedding_enabled=False)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.run()
                # 'embedding.enabled: false' itself does not raise -- EmbeddingManager
                # simply reports no current provider, so Semantic Search still builds
                # around it (an EmbeddingEngine that currently has none selected),
                # exactly as EP-022's RAG Engine does in the same situation.
                self.assert_true(bootstrap.embedding_service is not None)
                self.assert_false(bootstrap.embedding_service.status().enabled)

    def _test_bootstrap_default_config_search_returns_results(self) -> None:
        """End-to-end regression test for independent-audit findings H1 and M1/H1-adjacent dedup.

        Drives the exact same path a real user would: real Bootstrap
        wiring, real KnowledgeService/LongTermMemoryService storage,
        real CLI dispatch, the real, unmodified default
        'semantic.similarity_threshold: 0.70' with the "local"
        placeholder embedding provider active. Root-cause investigation
        (see `_test_engine_no_threshold_relaxation_for_placeholder_provider`)
        proved that provider carries no signal for non-identical text,
        so this test queries with the exact stored text -- the one
        case this provider can reliably serve (score deterministically
        1.0) -- rather than asserting on a reworded query's noisy,
        non-reproducible score. It also confirms the threshold is left
        genuinely unmodified (0.70, not silently relaxed) and that the
        placeholder-provider warning is surfaced via 'semantic status'.
        """
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.run()
                self.assert_equal(bootstrap.semantic_service.status().similarity_threshold, 0.70)

                fact_text = "The Eiffel Tower is located in Paris France"
                memory_text = "the user prefers dark mode interfaces"
                bootstrap.knowledge_service.store("fact1", fact_text)
                bootstrap.long_term_memory_service.store("mem1", memory_text)

                # Deterministic: querying with the exact stored text scores 1.0,
                # comfortably above the real, unrelaxed 0.70 default -- proving the
                # default configuration finds real content, not that it happens to
                # tolerate this specific hash function's noise for reworded text.
                outcome = bootstrap.semantic_service.search(fact_text)
                self.assert_true(outcome.success)
                self.assert_true(any(r.identifier == "fact1" for r in outcome.results))

                status_result = bootstrap._command_router.dispatch("semantic status")  # noqa: SLF001
                self.assert_true(status_result.success)
                self.assert_true("Warning" in status_result.message)
                self.assert_true(PLACEHOLDER_EMBEDDING_PROVIDER_NAME in status_result.message)

                # The Long-Term Memory record must not be double-counted as a Knowledge
                # Base record too (dedup regression, discovered while fixing H1). Query
                # with its exact text so it is deterministically included in results,
                # then assert it is not duplicated under two source labels.
                search_result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    f"semantic search {memory_text}"
                )
                self.assert_true(search_result.success)
                self.assert_true("mem1" in search_result.message)
                self.assert_equal(search_result.message.count("mem1"), 1)

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """EP-026 must not import RAG, AI providers, Planner, Reflection, or Agent Framework code."""
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
        for module in (semantic_engine_module, semantic_manager_module, semantic_provider_module):
            source = inspect.getsource(module)
            for fragment in forbidden_fragments:
                self.assert_true(
                    fragment not in source,
                    f"{module.__name__} must not reference '{fragment}'",
                )

    def _test_manager_owns_no_storage_state(self) -> None:
        """SemanticManager owns provider registration only, never record/vector storage."""
        with tempfile.TemporaryDirectory() as tmp:
            config = _write_config(Path(tmp), _DEFAULT_SEMANTIC_YAML)
            manager = SemanticManager(config=config)
            instance_attrs = vars(manager)
            forbidden_attr_names = ("records", "vectors", "collections", "index")
            for attr_name in instance_attrs:
                for forbidden in forbidden_attr_names:
                    self.assert_true(
                        forbidden not in attr_name.lower(),
                        f"SemanticManager should not own storage state ('{attr_name}')",
                    )

    def _test_exception_hierarchy(self) -> None:
        """SemanticProviderError is a SemanticError, catchable through the shared root."""
        self.assert_true(issubclass(SemanticProviderError, SemanticError))
        self.assert_true(issubclass(SemanticEngineError, SemanticError))
        try:
            raise SemanticProviderError("boom")
        except SemanticError:
            self.result.add_pass()
        else:
            self.assert_true(False, "SemanticProviderError should be catchable as SemanticError")

    def _test_only_expected_provider_classes_exist(self) -> None:
        """Only the two documented provider classes exist -- no future-EP providers.

        EP-026 must implement only `SemanticProvider` (abstraction) and
        `DefaultSemanticProvider` (built-in cosine-similarity provider)
        -- not `CosineSimilarityProvider`, `HybridSearchProvider`,
        `ANNProvider`, or `VectorDatabaseProvider`, which are
        explicitly future work per the task brief.
        """
        forbidden_class_names = (
            "CosineSimilarityProvider",
            "HybridSearchProvider",
            "ANNProvider",
            "VectorDatabaseProvider",
        )
        module_source = inspect.getsource(semantic_provider_module)
        for class_name in forbidden_class_names:
            self.assert_true(
                f"class {class_name}" not in module_source,
                f"{class_name} must not be implemented in EP-026",
            )

    def _test_no_private_api_access_on_foreign_objects(self) -> None:
        """SemanticEngine reaches Knowledge Base/Long-Term Memory only through public methods.

        Scans `semantic_engine.py`'s source for any attribute access
        beginning with an underscore on the injected collaborators
        (`knowledge_service`, `long_term_memory_service`,
        `embedding_engine`, `record`) -- only `self._*` (this class's
        own attributes) is permitted.
        """
        source = inspect.getsource(semantic_engine_module)
        forbidden_accesses = (
            "knowledge_service._",
            "long_term_memory_service._",
            "embedding_engine._",
            "record._",
        )
        for forbidden in forbidden_accesses:
            self.assert_true(
                forbidden not in source,
                f"SemanticEngine must not access a private attribute via '{forbidden}'",
            )
