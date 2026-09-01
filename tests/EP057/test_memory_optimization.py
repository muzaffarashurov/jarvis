"""Real engineering tests for EP-057 STEP 2/STEP 4 - Memory Optimization.

Single combined test suite (NAME = "EP057"), following the same
precedent EP-043 through EP-056 already established.

Per `EP057_DESIGN.md` (Owner Decision D1, "Candidate A"), EP-057 adds
exactly one new capability: `compression query "<text>"`, a thin
CLI/Service forward to the already-existing, already-tested EP-027
`CompressionEngine.compress_query()` -- previously reachable only from
EP-027's own test suite (`tests/EP027/test_context_compression.py`).
No new compression, semantic-search, or Long-Term Memory logic is
introduced; this suite proves the new forward behaves correctly end
to end, including through a real, unmodified `Bootstrap` run, without
duplicating EP-027's own exhaustive engine-level coverage.

Per Owner Decision D2, `top_k`/`threshold` are not exposed as CLI
arguments in v1 -- `compression query` relies on 'semantic.top_k' /
'semantic.similarity_threshold''s already-configured defaults, so no
argument-parsing test for either is needed beyond the single required
query-text argument.

Per Owner Decision D3, `compression query` requires no additional
information-disclosure gate beyond the already-existing
'context_compression.enabled' flag.

STEP 4 remediation (`EP057_ARCHITECTURE_AUDIT.md` Finding 2): the
original `_test_cli_query_command_failure_when_disabled` never
actually set `context_compression.enabled: false` -- it exercised "no
SemanticEngine configured" instead, a different code path, because
`compress_query()` checks for a `None` SemanticEngine before ever
reaching the enabled/provider-selection check. It has been renamed to
`_test_cli_query_command_failure_without_semantic_engine`, and a new
test, `_test_cli_query_command_failure_when_context_compression_disabled`,
now exercises the actual `context_compression.enabled: false` gate
using the previously-unused `_DISABLED_COMPRESSION_YAML` fixture
together with a real, configured SemanticEngine, so a failure there
can only come from the gate itself.

Covers:
    - `CompressionService.query()`: forwards to the real, unmodified
      `CompressionEngine.compress_query()`, using a real
      `SemanticEngine`/`KnowledgeService` (EP-026/EP-024), never a
      fake -- this is the one genuine cross-subsystem integration
      point this EP touches, mirroring EP-027's/EP-055's/EP-056's own
      "prefer one real, non-fake integration test over mocking the
      one genuine integration surface" precedent.
        - Positive path: a stored fact is found and returned,
          deduplicated/size-bounded.
        - `SemanticSearchUnavailableError` translated into a clean
          `QueryOutcome` failure when no `SemanticEngine` is
          configured.
        - `EmptyContextError` translated into a clean `QueryOutcome`
          failure when the search returns no results.
        - `NoCompressionProviderSelectedError` translated into a clean
          `QueryOutcome` failure when `context_compression.enabled` is
          `false`, with a real `SemanticEngine` configured (STEP 4
          remediation, Finding 2).
    - `ContextCompressionModule._query()` (CLI): argument-shape
      validation ("query" with no text is a usage error), positive
      path, "no SemanticEngine" failure path, "`context_compression.
      enabled: false`" failure path (STEP 4 remediation, Finding 2),
      and `HELP_TEXT` lists the new command.
    - `CommandRouter` dispatch equivalence for the new "query" action.
    - `Bootstrap` wiring: `compression query` is reachable through the
      already-registered `compression` namespace with zero Bootstrap
      changes (per `EP057_DESIGN.md` Section 3.4/6.4/14 -- no new
      construction site, no new config key), driven end to end
      through a real `Bootstrap.initialize()` -> real
      `CommandRouter.dispatch()` -> real `CompressionService.query()`
      -> real `CompressionEngine.compress_query()` -> real
      `SemanticEngine.search()` -> real `KnowledgeService` path, not
      an isolated/mocked component.
    - Every other existing `compression` action (`help`, `status`,
      `providers`, `use`, `analyze`, `compress`, `limits`) is
      unaffected by this addition.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from src.bootstrap import Bootstrap
from src.core.command_router import CommandRouter
from src.core.config import Config
from src.core.context_compression.compression_engine import CompressionEngine
from src.core.context_compression.compression_manager import CompressionManager
from src.core.embedding.engine import EmbeddingEngine
from src.core.embedding.manager import EmbeddingManager
from src.core.semantic.semantic_engine import SemanticEngine
from src.core.semantic.semantic_manager import SemanticManager
from src.modules.context_compression_module import ContextCompressionModule
from src.services.context_compression_service import CompressionService
from src.services.knowledge_service import KnowledgeService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

import os


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

# Full, offline-safe config.yaml covering every section Bootstrap._build_command_router
# reads, so a real Bootstrap.initialize() can be exercised end to end in a temporary
# project root without any network access or long-lived background threads. Mirrors
# tests/EP027/test_context_compression.py's own _FULL_BOOTSTRAP_CONFIG_YAML exactly
# (kept independent per-file rather than imported, matching every other EP test
# suite's own self-contained fixture convention in this project).
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
    "  deduplicate: true\n"
)


_CONFIG_CACHE: dict[str, Config] = {}


def _write_config(directory: Path, sections: str) -> Config:
    """Return a Config for `sections`, parsing it at most once per distinct text.

    Mirrors tests/EP027/test_context_compression.py's own caching
    helper, for the same reason (avoiding redundant disk writes and
    re-parses across many independent temporary directories).
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


def _write_full_bootstrap_config(directory: Path) -> None:
    """Write config/config.yaml (a full, offline-safe config) under `directory`."""
    config_dir = directory / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.yaml").write_text(_FULL_BOOTSTRAP_CONFIG_YAML, encoding="utf-8")


@TestRegistry.register
class MemoryOptimizationTest(BaseTest):
    NAME = "EP057"

    def run(self):
        # ---------- CompressionService.query() ----------
        self._test_service_query_without_semantic_engine_fails_gracefully()
        self._test_service_query_with_real_semantic_engine_returns_match()
        self._test_service_query_empty_results_fails_gracefully()

        # ---------- ContextCompressionModule (CLI) "query" action ----------
        self._test_cli_help_lists_query_command()
        self._test_cli_query_command_usage_error()
        self._test_cli_query_command_success()
        self._test_cli_query_command_failure_without_semantic_engine()
        self._test_cli_query_command_failure_when_context_compression_disabled()
        self._test_cli_existing_actions_unaffected()

        # ---------- CommandRouter dispatch equivalence ----------
        self._test_command_router_dispatch_matches_direct_execute()

        # ---------- Bootstrap wiring: real end-to-end command path ----------
        self._test_bootstrap_compression_query_reachable_with_zero_wiring_changes()
        self._test_bootstrap_compression_query_finds_stored_knowledge_fact()
        self._test_bootstrap_compression_query_no_match_returns_clean_failure()

        return self.result

    # ---------- Helpers ----------

    def _build_engine(
        self, tmp_path: Path, yaml_text: str = _DEFAULT_COMPRESSION_YAML, with_semantic: bool = False
    ) -> tuple[CompressionEngine, KnowledgeService | None]:
        """Mirrors tests/EP027/test_context_compression.py's own `_build_engine`."""
        config = _write_config(tmp_path, yaml_text)
        manager = CompressionManager(config=config)
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
        self, tmp_path: Path, yaml_text: str = _DEFAULT_COMPRESSION_YAML, with_semantic: bool = False
    ) -> tuple[CompressionService, KnowledgeService | None]:
        engine, knowledge = self._build_engine(tmp_path, yaml_text, with_semantic=with_semantic)
        service = CompressionService(manager=engine._manager, engine=engine)  # noqa: SLF001
        return service, knowledge

    # ---------- CompressionService.query() ----------

    def _test_service_query_without_semantic_engine_fails_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp), with_semantic=False)
            outcome = service.query("anything")
            self.assert_false(outcome.success)
            self.assert_true(outcome.result is None)
            self.assert_true(outcome.error != "")

    def _test_service_query_with_real_semantic_engine_returns_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, knowledge = self._build_service(Path(tmp), with_semantic=True)
            fact_text = "The Eiffel Tower is located in Paris France"
            knowledge.store("fact1", fact_text)
            outcome = service.query(fact_text)
            self.assert_true(outcome.success)
            self.assert_true(outcome.result is not None)
            self.assert_true(outcome.result.chunk_count >= 1)
            self.assert_true(
                any(c.metadata.get("identifier") == "fact1" for c in outcome.result.chunks)
            )

    def _test_service_query_empty_results_fails_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp), with_semantic=True)
            outcome = service.query("nothing has ever been stored anywhere at all")
            self.assert_false(outcome.success)
            self.assert_true(outcome.result is None)
            self.assert_true(outcome.error != "")

    # ---------- ContextCompressionModule (CLI) "query" action ----------

    def _test_cli_help_lists_query_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            module = ContextCompressionModule(service)
            result = module.execute("help", [])
            self.assert_true(result.success)
            self.assert_true('compression query "<text>"' in result.message)

    def _test_cli_query_command_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            module = ContextCompressionModule(service)
            result = module.execute("query", [])
            self.assert_false(result.success)
            self.assert_true("Usage" in result.message)

    def _test_cli_query_command_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, knowledge = self._build_service(Path(tmp), with_semantic=True)
            module = ContextCompressionModule(service)
            fact_text = "The Great Wall of China is visible from certain orbits"
            knowledge.store("fact2", fact_text)
            result = module.execute("query", fact_text.split(" "))
            self.assert_true(result.success)
            self.assert_true("Compressed chunks" in result.message)

    def _test_cli_query_command_failure_without_semantic_engine(self) -> None:
        """No SemanticEngine configured (distinct from Finding 2's disabled-gate test below)."""
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp), with_semantic=False)
            module = ContextCompressionModule(service)
            result = module.execute("query", ["anything", "at", "all"])
            self.assert_false(result.success)
            self.assert_true("SemanticEngine" in result.message)

    def _test_cli_query_command_failure_when_context_compression_disabled(self) -> None:
        """`context_compression.enabled: false`, WITH a real SemanticEngine configured.

        Fixes STEP 3's Finding 2: the previous
        `_test_cli_query_command_failure_when_disabled` never actually
        set `context_compression.enabled: false` -- it tested "no
        SemanticEngine" instead (a different code path, see
        `_test_cli_query_command_failure_without_semantic_engine`
        above), because `compress_query()` checks for a `None`
        SemanticEngine before ever reaching the
        enabled/provider-selection check. This test uses the
        already-defined `_DISABLED_COMPRESSION_YAML` fixture
        *together with* a real, configured SemanticEngine, so the
        `context_compression.enabled: false` gate itself is the one
        and only thing under test -- exactly matching the scenario
        `EP057_ARCHITECTURE_AUDIT.md`'s own Finding 2 and its manual
        verification (`NoCompressionProviderSelectedError`).
        """
        with tempfile.TemporaryDirectory() as tmp:
            service, knowledge = self._build_service(
                Path(tmp), yaml_text=_DISABLED_COMPRESSION_YAML, with_semantic=True
            )
            module = ContextCompressionModule(service)
            fact_text = "Disabled compression must not return this fact"
            knowledge.store("fact_disabled", fact_text)

            # The SemanticEngine itself is real and configured (unlike
            # the test above), so a failure here can only come from
            # the `context_compression.enabled` gate itself, not from
            # a missing SemanticEngine.
            result = module.execute("query", fact_text.split(" "))
            self.assert_false(result.success)
            self.assert_true("No compression provider is currently selected" in result.message)

            # Same assertion at the Service layer directly, for a
            # second, independent confirmation of the gate.
            outcome = service.query(fact_text)
            self.assert_false(outcome.success)
            self.assert_true(outcome.result is None)
            self.assert_true("No compression provider is currently selected" in outcome.error)

    def _test_cli_existing_actions_unaffected(self) -> None:
        """Every pre-existing "compression" action still behaves exactly as before."""
        with tempfile.TemporaryDirectory() as tmp:
            service, _knowledge = self._build_service(Path(tmp))
            module = ContextCompressionModule(service)

            self.assert_true(module.execute("status", []).success)
            self.assert_true(module.execute("providers", []).success)
            self.assert_true(module.execute("limits", []).success)

            compress_result = module.execute("compress", ["Hello", "world"])
            self.assert_true(compress_result.success)
            self.assert_true("Compressed chunks" in compress_result.message)

            analyze_result = module.execute("analyze", ["Some", "text"])
            self.assert_true(analyze_result.success)

            self.assert_false(module.execute("compress", []).success)
            self.assert_false(module.execute("analyze", []).success)

    # ---------- CommandRouter dispatch equivalence ----------

    def _test_command_router_dispatch_matches_direct_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            service, knowledge = self._build_service(Path(tmp), with_semantic=True)
            module = ContextCompressionModule(service)
            router = CommandRouter()
            router.register(module)

            fact_text = "Mount Everest is the tallest mountain above sea level"
            knowledge.store("fact3", fact_text)

            direct = module.execute("query", fact_text.split(" "))
            dispatched = router.dispatch(f"compression query {fact_text}")
            self.assert_equal(direct.success, dispatched.success)
            self.assert_equal(direct.message, dispatched.message)

    # ---------- Bootstrap wiring: real end-to-end command path ----------

    def _test_bootstrap_compression_query_reachable_with_zero_wiring_changes(self) -> None:
        """`compression query` is reachable through the already-registered namespace.

        Per `EP057_DESIGN.md` Section 3.4/6.4/14, no Bootstrap or
        configuration change is required for this action to work --
        this test drives a real, unmodified `Bootstrap.initialize()`
        against the same full config every other EP's Bootstrap test
        already uses, with no EP-057-specific config addition.
        """
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                service = bootstrap.compression_service
                self.assert_true(service is not None)

                result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    "compression query nothing will match this exact phrase"
                )
                # No stored knowledge yet -- a clean, non-crashing failure
                # (EmptyContextError translated to CommandResult) proves the
                # action is wired end to end without asserting a match.
                self.assert_false(result.success)

    def _test_bootstrap_compression_query_finds_stored_knowledge_fact(self) -> None:
        """Full real path: Bootstrap -> CommandRouter -> CompressionService.query()

        -> CompressionEngine.compress_query() -> SemanticEngine.search()
        -> KnowledgeService -- not an isolated/mocked component at any layer.
        """
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()
                self.assert_true(bootstrap.knowledge_service is not None)

                fact_text = "Jarvis stores this fact for the EP-057 end to end test"
                bootstrap.knowledge_service.store("ep057_fact", fact_text)

                result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    f"compression query {fact_text}"
                )
                self.assert_true(result.success)
                self.assert_true("Compressed chunks" in result.message)
                self.assert_true("Jarvis stores this fact" in result.message)

    def _test_bootstrap_compression_query_no_match_returns_clean_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            _write_full_bootstrap_config(directory)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                bootstrap.initialize()

                result = bootstrap._command_router.dispatch(  # noqa: SLF001
                    "compression query absolutely nothing has ever matched this"
                )
                self.assert_false(result.success)
                self.assert_true(result.message != "")
