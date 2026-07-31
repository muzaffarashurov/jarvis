"""Real engineering tests for EP-022 - Provider-Independent RAG Engine.

Builds real `ProjectIndex`/`ProjectIndexer` instances (temporary
on-disk repositories with a real `PROJECT_MANIFEST.md`, as in
`tests/EP019/test_project_index_engine.py`), real `EmbeddingManager`/
`EmbeddingEngine` instances (loading a real `Config` from a temporary
`config.yaml`, as in `tests/EP021/test_embedding_engine.py`), and real
`RetrievalEngine` instances (EP-020, untouched) -- then drives
`RagEngine`/`RagManager`/`RagService`/`RagModule` exactly as a caller
would. No mocked internals, matching every other EP's test suite in
this project.
"""

from __future__ import annotations

import ast
import inspect
import os
import tempfile
from pathlib import Path

from src.core.config import Config
from src.core.embedding.engine import EmbeddingEngine
from src.core.embedding.manager import EmbeddingManager
from src.core.indexing import ProjectIndex, ProjectIndexer
from src.core.rag import (
    EmbeddingUnavailableError,
    EmptyQueryError,
    IndexNotBuiltError,
    NoEmbeddingProviderError,
    RagConfigurationError,
    RagContextItem,
    RagDisabledError,
    RagEngine,
    RagEngineError,
    RagManager,
    RagManagerError,
    RagProviderInfo,
    RagResult,
)
from src.core.rag import rag_engine as rag_engine_module
from src.core.rag import rag_manager as rag_manager_module
from src.core.rag import rag_provider as rag_provider_module
from src.core.rag import rag_result as rag_result_module
from src.core.retrieval import RetrievalEngine, RetrievalResult
from src.modules.rag_module import RagModule
from src.services.rag_service import RagService
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


def _write_project(directory: Path, files: dict[str, str], manifest_body: str) -> None:
    """Write a minimal, self-contained PROJECT_MANIFEST.md plus a set of real files."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "PROJECT_MANIFEST.md").write_text(manifest_body, encoding="utf-8")
    for relative_path, content in files.items():
        path = directory / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


_MANIFEST_BODY = (
    "# Project Name\nRAG Test Project\n\n"
    "# Current Version\n1.0.0\n\n"
    "# Project Type\nlibrary\n\n"
    "# Context Documents\n"
    "- guide.md\n"
    "- faq.md\n"
)

_GUIDE_MD = (
    "# User Guide\n\n"
    "## Installation\n"
    "Install the package by running pip install jarvis. "
    "This section is the installation guide for new users of the software.\n\n"
    "## Usage\n"
    "Run jarvis start to launch the application. Usage is simple and fast "
    "once installation is complete.\n"
)

_FAQ_MD = "# FAQ\n\nFrequently asked questions about installation of the jarvis package.\n"


def _build_project_indexer(project_root: Path) -> ProjectIndexer:
    """Build and return a ProjectIndexer with a real index already built, in `project_root`."""
    _write_project(
        project_root,
        files={"guide.md": _GUIDE_MD, "faq.md": _FAQ_MD},
        manifest_body=_MANIFEST_BODY,
    )
    with _ChdirGuard(project_root):
        indexer = ProjectIndexer()
        indexer.build()
    return indexer


_DEFAULT_CONFIG_YAML = (
    "embedding:\n"
    "  enabled: true\n"
    "  default_provider: \"local\"\n"
    "  providers:\n"
    "    local:\n"
    "      enabled: true\n"
    "      model: \"local-hash-v1\"\n"
    "      dimension: 8\n"
    "    cloud:\n"
    "      enabled: false\n"
    "      api_key: \"\"\n"
    "      model: \"text-embedding-cloud-v1\"\n"
    "      dimension: 16\n"
    "rag:\n"
    "  enabled: true\n"
    "  top_k: 5\n"
    "  max_context_characters: 4000\n"
)


def _write_config(directory: Path, config_yaml: str = _DEFAULT_CONFIG_YAML) -> Config:
    """Write a minimal, self-contained config.yaml and load it."""
    directory.mkdir(parents=True, exist_ok=True)
    config_path = directory / "config.yaml"
    config_path.write_text(config_yaml, encoding="utf-8")
    return Config(config_path).load()


class _Fixture:
    """Bundles a real, on-disk-backed ProjectIndexer + EmbeddingManager/Engine + RagManager.

    Owns its own TemporaryDirectory (for both the project repository
    and config.yaml); callers must always `cleanup()` when done.
    """

    def __init__(self, config_yaml: str = _DEFAULT_CONFIG_YAML, build_index: bool = True) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        root = Path(self.tmp_dir.name)
        self.config = _write_config(root / "config", config_yaml)
        if build_index:
            self.indexer = _build_project_indexer(root / "project")
        else:
            self.indexer = ProjectIndexer()
        self.embedding_manager = EmbeddingManager(self.config)
        self.embedding_engine = EmbeddingEngine(self.embedding_manager, batch_size=16)
        self.rag_manager = RagManager(
            indexer=self.indexer,
            embedding_manager=self.embedding_manager,
            embedding_engine=self.embedding_engine,
            config=self.config,
        )
        self.rag_service = RagService(self.rag_manager)
        self.rag_module = RagModule(self.rag_service)

    def cleanup(self) -> None:
        self.tmp_dir.cleanup()


class _StubRetrievalEngine:
    """A minimal stand-in for RetrievalEngine, returning a fixed set of results.

    Used only to exercise `RagEngine._assemble_context`'s handling of
    a `RetrievalResult` referencing a chunk id no longer present in
    the `ProjectIndex` (e.g. because the index changed between
    retrieval and assembly) -- a real `RetrievalEngine` can never
    produce such a result on its own since it reads chunk ids from the
    same index it searches, so this scenario must be constructed
    directly.
    """

    def __init__(self, results: list[RetrievalResult]) -> None:
        self._results = results

    def top_k(self, query, k: int) -> list[RetrievalResult]:
        return self._results[:k]


@TestRegistry.register
class RagEngineTest(BaseTest):
    """Real tests covering EP-022's Provider-Independent RAG Engine."""

    NAME = "EP022"

    def run(self):
        """Execute every RAG Engine check and return the aggregated result."""
        # RagEngine (pure pipeline)
        self._test_query_returns_ranked_context()
        self._test_context_matches_query_context_field()
        self._test_empty_query_raises()
        self._test_unmatched_query_returns_empty_result()
        self._test_top_k_limits_items()
        self._test_top_k_argument_overrides_default()
        self._test_invalid_top_k_raises()
        self._test_max_context_characters_truncates()
        self._test_context_uses_full_text_not_preview()
        self._test_stale_chunk_id_skipped_gracefully()
        self._test_no_embedding_provider_raises()
        self._test_constructor_rejects_non_positive_arguments()
        self._test_provider_and_model_left_blank_by_engine()

        # RagManager (lifecycle)
        self._test_manager_requires_built_index()
        self._test_manager_caches_retrieval_engine_until_rebuild()
        self._test_manager_provider_info_and_use_provider()
        self._test_manager_unknown_provider_raises()
        self._test_manager_disable()
        self._test_manager_query_fills_provider_and_model()
        self._test_manager_query_no_index_raises()
        self._test_manager_config_validation_rejects_non_bool_enabled()
        self._test_manager_config_validation_rejects_non_positive_top_k()
        self._test_manager_config_validation_rejects_non_positive_max_characters()

        # RagService / RagModule (CLI integration)
        self._test_cli_help()
        self._test_cli_status_before_and_after_index_build()
        self._test_cli_query_success_and_missing_argument()
        self._test_cli_context_success_and_no_match()
        self._test_cli_provider_success_and_failure()
        self._test_cli_use_success_and_failure()
        self._test_cli_unknown_action()

        # Architectural acceptance criteria
        self._test_no_ai_dependencies()
        self._test_no_vector_database_or_memory_dependencies()
        self._test_rag_engine_never_imports_manager_service_or_indexer()
        self._test_exception_hierarchies_have_common_roots()

        return self.result

    # ---------- RagEngine: core pipeline behavior ----------

    def _build_engine_from_index(
        self, index: ProjectIndex, embedding_engine: EmbeddingEngine, **kwargs
    ) -> RagEngine:
        return RagEngine(
            index=index,
            retrieval_engine=RetrievalEngine(index),
            embedding_engine=embedding_engine,
            **kwargs,
        )

    def _test_query_returns_ranked_context(self) -> None:
        """A query matching indexed content returns ranked items and assembled context."""
        fixture = _Fixture()
        try:
            engine = self._build_engine_from_index(
                fixture.indexer.index(), fixture.embedding_engine
            )
            result = engine.query("installation guide")
            self.assert_true(isinstance(result, RagResult))
            self.assert_true(len(result.items) > 0, "Should retrieve at least one matching chunk")
            self.assert_true(
                result.items[0].relative_path == "guide.md",
                "The Installation chunk from guide.md should rank first",
            )
            self.assert_true("Install the package" in result.context)
            self.assert_equal(result.query, "installation guide")
            self.assert_false(result.is_empty)
        finally:
            fixture.cleanup()

    def _test_context_matches_query_context_field(self) -> None:
        """`context()` returns exactly `query().context`."""
        fixture = _Fixture()
        try:
            engine = self._build_engine_from_index(
                fixture.indexer.index(), fixture.embedding_engine
            )
            via_query = engine.query("installation guide").context
            via_context = engine.context("installation guide")
            self.assert_equal(via_query, via_context)
        finally:
            fixture.cleanup()

    def _test_empty_query_raises(self) -> None:
        """Empty or whitespace-only query text raises EmptyQueryError, for both entry points."""
        fixture = _Fixture()
        try:
            engine = self._build_engine_from_index(
                fixture.indexer.index(), fixture.embedding_engine
            )
            for bad_text in ("", "   "):
                raised = False
                try:
                    engine.query(bad_text)
                except EmptyQueryError:
                    raised = True
                self.assert_true(raised, f"query({bad_text!r}) should raise EmptyQueryError")

                raised = False
                try:
                    engine.context(bad_text)
                except EmptyQueryError:
                    raised = True
                self.assert_true(raised, f"context({bad_text!r}) should raise EmptyQueryError")
        finally:
            fixture.cleanup()

    def _test_unmatched_query_returns_empty_result(self) -> None:
        """A query matching nothing in the index returns an empty result, not an error."""
        fixture = _Fixture()
        try:
            engine = self._build_engine_from_index(
                fixture.indexer.index(), fixture.embedding_engine
            )
            result = engine.query("zzz_completely_unknown_term_zzz")
            self.assert_true(result.is_empty)
            self.assert_equal(result.context, "")
            self.assert_equal(result.items, ())
            self.assert_false(result.truncated)
            self.assert_true(result.embedding_dimension > 0, "The embedding step should still run")
        finally:
            fixture.cleanup()

    def _test_top_k_limits_items(self) -> None:
        """`top_k` caps the number of assembled context items."""
        fixture = _Fixture()
        try:
            engine = self._build_engine_from_index(
                fixture.indexer.index(), fixture.embedding_engine, top_k=1
            )
            result = engine.query("installation usage jarvis")
            self.assert_true(len(result.items) <= 1)
        finally:
            fixture.cleanup()

    def _test_top_k_argument_overrides_default(self) -> None:
        """An explicit `top_k` argument overrides the engine's configured default."""
        fixture = _Fixture()
        try:
            engine = self._build_engine_from_index(
                fixture.indexer.index(), fixture.embedding_engine, top_k=1
            )
            unrestricted = engine.query("installation usage jarvis", top_k=10)
            restricted = engine.query("installation usage jarvis", top_k=1)
            self.assert_true(len(unrestricted.items) >= len(restricted.items))
            self.assert_true(len(restricted.items) <= 1)
        finally:
            fixture.cleanup()

    def _test_invalid_top_k_raises(self) -> None:
        """A non-positive `top_k` argument raises ValueError."""
        fixture = _Fixture()
        try:
            engine = self._build_engine_from_index(
                fixture.indexer.index(), fixture.embedding_engine
            )
            raised = False
            try:
                engine.query("installation", top_k=0)
            except ValueError:
                raised = True
            self.assert_true(raised, "top_k=0 should raise ValueError")
        finally:
            fixture.cleanup()

    def _test_max_context_characters_truncates(self) -> None:
        """A small `max_context_characters` budget truncates lower-ranked matches."""
        fixture = _Fixture()
        try:
            index = fixture.indexer.index()
            generous = self._build_engine_from_index(
                index, fixture.embedding_engine, top_k=10, max_context_characters=10_000
            )
            tight = self._build_engine_from_index(
                index, fixture.embedding_engine, top_k=10, max_context_characters=50
            )
            generous_result = generous.query("installation usage jarvis package")
            tight_result = tight.query("installation usage jarvis package")

            self.assert_true(len(tight_result.context) <= 50 + 250, "Should not wildly exceed budget")
            self.assert_true(
                len(tight_result.items) <= len(generous_result.items),
                "A tighter budget should never include more items than a generous one",
            )
            if len(generous_result.items) > 1:
                self.assert_true(tight_result.truncated, "Tight budget should report truncation")
            self.assert_true(len(tight_result.items) >= 1, "At least the top match should be included")
        finally:
            fixture.cleanup()

    def _test_context_uses_full_text_not_preview(self) -> None:
        """Assembled context contains the chunk's full text, not EP-020's short preview."""
        fixture = _Fixture()
        try:
            index = fixture.indexer.index()
            engine = self._build_engine_from_index(index, fixture.embedding_engine)
            result = engine.query("installation guide")
            item = result.items[0]
            chunk = index.chunk(item.chunk_id)
            self.assert_equal(item.text, chunk.text())
            self.assert_true(item.text in result.context)
        finally:
            fixture.cleanup()

    def _test_stale_chunk_id_skipped_gracefully(self) -> None:
        """A RetrievalResult referencing a chunk id no longer in the index is skipped, not crashed."""
        fixture = _Fixture()
        try:
            index = fixture.indexer.index()
            real_document_id = index.documents()[0].document_id
            fake_result = RetrievalResult(
                document_id=real_document_id,
                chunk_id="this-chunk-id-does-not-exist",
                score=99.0,
                relative_path="ghost.md",
                heading="",
                preview="a ghost result",
            )
            stub_retrieval = _StubRetrievalEngine([fake_result])
            engine = RagEngine(
                index=index, retrieval_engine=stub_retrieval, embedding_engine=fixture.embedding_engine
            )
            result = engine.query("anything")
            self.assert_equal(result.items, (), "A stale chunk id should be skipped, yielding no items")
            self.assert_equal(result.context, "")
        finally:
            fixture.cleanup()

    def _test_no_embedding_provider_raises(self) -> None:
        """If no embedding provider is selected, `query()` raises EmbeddingUnavailableError."""
        config_yaml = _DEFAULT_CONFIG_YAML.replace(
            'default_provider: "local"', 'default_provider: "none"'
        )
        fixture = _Fixture(config_yaml=config_yaml)
        try:
            engine = self._build_engine_from_index(
                fixture.indexer.index(), fixture.embedding_engine
            )
            raised = False
            try:
                engine.query("installation")
            except EmbeddingUnavailableError:
                raised = True
            self.assert_true(raised, "No embedding provider selected should raise EmbeddingUnavailableError")
        finally:
            fixture.cleanup()

    def _test_constructor_rejects_non_positive_arguments(self) -> None:
        """RagEngine's constructor rejects non-positive top_k/max_context_characters."""
        fixture = _Fixture()
        try:
            index = fixture.indexer.index()
            retrieval_engine = RetrievalEngine(index)
            for bad_kwargs in ({"top_k": 0}, {"top_k": -1}, {"max_context_characters": 0}):
                raised = False
                try:
                    RagEngine(
                        index=index,
                        retrieval_engine=retrieval_engine,
                        embedding_engine=fixture.embedding_engine,
                        **bad_kwargs,
                    )
                except ValueError:
                    raised = True
                self.assert_true(raised, f"{bad_kwargs} should raise ValueError")
        finally:
            fixture.cleanup()

    def _test_provider_and_model_left_blank_by_engine(self) -> None:
        """RagEngine itself never knows provider/model identity -- both stay "" on its RagResult."""
        fixture = _Fixture()
        try:
            engine = self._build_engine_from_index(
                fixture.indexer.index(), fixture.embedding_engine
            )
            result = engine.query("installation guide")
            self.assert_equal(result.provider, "")
            self.assert_equal(result.model, "")
        finally:
            fixture.cleanup()

    # ---------- RagManager: lifecycle ----------

    def _test_manager_requires_built_index(self) -> None:
        """`build_engine()` raises IndexNotBuiltError before any index has been built."""
        fixture = _Fixture(build_index=False)
        try:
            raised = False
            try:
                fixture.rag_manager.build_engine()
            except IndexNotBuiltError:
                raised = True
            self.assert_true(raised, "No index built should raise IndexNotBuiltError")
            self.assert_true(fixture.rag_manager.current_index() is None)
        finally:
            fixture.cleanup()

    def _test_manager_caches_retrieval_engine_until_rebuild(self) -> None:
        """`build_engine()` is stable while unchanged, and reflects `index rebuild` afterward.

        Exercises the RagManager's internal RetrievalEngine caching
        purely through observable behavior (no access to private
        attributes): two calls to `build_engine()` between rebuilds
        must agree on the underlying index's statistics, and a query
        for content added after `rebuild()` must find it -- which
        could not happen if a stale RetrievalEngine were reused
        forever.
        """
        fixture = _Fixture()
        try:
            index_before = fixture.rag_manager.build_engine()
            stats_first_call = fixture.indexer.index().statistics()
            stats_second_call = fixture.rag_manager.build_engine()
            self.assert_equal(stats_first_call, fixture.indexer.index().statistics())
            self.assert_true(isinstance(index_before, RagEngine))
            self.assert_true(isinstance(stats_second_call, RagEngine))

            before = fixture.rag_manager.query("unicornxyz_marker_term")
            self.assert_true(before.is_empty, "The marker term should not exist yet")

            project_root = Path(fixture.tmp_dir.name) / "project"
            guide_path = project_root / "guide.md"
            guide_path.write_text(
                guide_path.read_text(encoding="utf-8")
                + "\n\nunicornxyz_marker_term appears here for the very first time.\n",
                encoding="utf-8",
            )

            with _ChdirGuard(project_root):
                fixture.indexer.rebuild()

            after = fixture.rag_manager.query("unicornxyz_marker_term")
            self.assert_false(after.is_empty, "After rebuild, the new content should be retrievable")
        finally:
            fixture.cleanup()

    def _test_manager_provider_info_and_use_provider(self) -> None:
        """`provider_info()` reports the active provider; `use_provider()` switches it."""
        fixture = _Fixture()
        try:
            info = fixture.rag_manager.provider_info()
            self.assert_true(isinstance(info, RagProviderInfo))
            self.assert_equal(info.name, "local")
            self.assert_equal(info.dimension, 8)
            self.assert_true(info.available)

            fixture.rag_manager.use_provider("cloud")
            cloud_info = fixture.rag_manager.provider_info()
            self.assert_equal(cloud_info.name, "cloud")
            self.assert_false(cloud_info.available, "Cloud provider is disabled by default in the fixture")
        finally:
            fixture.cleanup()

    def _test_manager_unknown_provider_raises(self) -> None:
        """Selecting an unregistered provider name raises."""
        fixture = _Fixture()
        try:
            raised = False
            try:
                fixture.rag_manager.use_provider("does_not_exist")
            except Exception:
                raised = True
            self.assert_true(raised, "Unknown provider name should raise")
        finally:
            fixture.cleanup()

    def _test_manager_disable(self) -> None:
        """A disabled RAG subsystem raises RagDisabledError on query()/context()."""
        fixture = _Fixture()
        try:
            self.assert_true(fixture.rag_manager.is_enabled())
            fixture.rag_manager.disable()
            self.assert_false(fixture.rag_manager.is_enabled())

            raised = False
            try:
                fixture.rag_manager.query("installation")
            except RagDisabledError:
                raised = True
            self.assert_true(raised, "query() on a disabled manager should raise RagDisabledError")
        finally:
            fixture.cleanup()

    def _test_manager_query_fills_provider_and_model(self) -> None:
        """`RagManager.query()` fills in provider/model, unlike a bare RagEngine."""
        fixture = _Fixture()
        try:
            result = fixture.rag_manager.query("installation guide")
            self.assert_equal(result.provider, "local")
            self.assert_equal(result.model, "local-hash-v1")
            self.assert_equal(fixture.rag_manager.context("installation guide"), result.context)
        finally:
            fixture.cleanup()

    def _test_manager_query_no_index_raises(self) -> None:
        """`RagManager.query()` raises IndexNotBuiltError before any index has been built."""
        fixture = _Fixture(build_index=False)
        try:
            raised = False
            try:
                fixture.rag_manager.query("installation")
            except IndexNotBuiltError:
                raised = True
            self.assert_true(raised)
        finally:
            fixture.cleanup()

    def _test_manager_config_validation_rejects_non_bool_enabled(self) -> None:
        """A non-boolean 'rag.enabled' value raises RagConfigurationError."""
        config_yaml = _DEFAULT_CONFIG_YAML.replace("rag:\n  enabled: true", 'rag:\n  enabled: "yes"')
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), config_yaml)
            indexer = ProjectIndexer()
            embedding_manager = EmbeddingManager(config)
            embedding_engine = EmbeddingEngine(embedding_manager)
            raised = False
            try:
                RagManager(
                    indexer=indexer,
                    embedding_manager=embedding_manager,
                    embedding_engine=embedding_engine,
                    config=config,
                )
            except RagConfigurationError as exc:
                raised = True
                self.assert_true("rag.enabled" in str(exc))
            self.assert_true(raised, "A non-boolean 'rag.enabled' must raise")

    def _test_manager_config_validation_rejects_non_positive_top_k(self) -> None:
        """A zero/negative 'rag.top_k' value raises RagConfigurationError."""
        config_yaml = _DEFAULT_CONFIG_YAML.replace("  top_k: 5\n", "  top_k: 0\n")
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), config_yaml)
            indexer = ProjectIndexer()
            embedding_manager = EmbeddingManager(config)
            embedding_engine = EmbeddingEngine(embedding_manager)
            raised = False
            try:
                RagManager(
                    indexer=indexer,
                    embedding_manager=embedding_manager,
                    embedding_engine=embedding_engine,
                    config=config,
                )
            except RagConfigurationError as exc:
                raised = True
                self.assert_true("rag.top_k" in str(exc))
            self.assert_true(raised, "A non-positive 'rag.top_k' must raise")

    def _test_manager_config_validation_rejects_non_positive_max_characters(self) -> None:
        """A zero/negative 'rag.max_context_characters' value raises RagConfigurationError."""
        config_yaml = _DEFAULT_CONFIG_YAML.replace(
            "  max_context_characters: 4000\n", "  max_context_characters: -1\n"
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _write_config(Path(tmp_dir), config_yaml)
            indexer = ProjectIndexer()
            embedding_manager = EmbeddingManager(config)
            embedding_engine = EmbeddingEngine(embedding_manager)
            raised = False
            try:
                RagManager(
                    indexer=indexer,
                    embedding_manager=embedding_manager,
                    embedding_engine=embedding_engine,
                    config=config,
                )
            except RagConfigurationError as exc:
                raised = True
                self.assert_true("rag.max_context_characters" in str(exc))
            self.assert_true(raised, "A non-positive 'rag.max_context_characters' must raise")

    # ---------- RagService / RagModule: CLI integration ----------

    def _test_cli_help(self) -> None:
        """`rag help` lists every documented command."""
        fixture = _Fixture()
        try:
            result = fixture.rag_module.execute("help", [])
            self.assert_true(result.success)
            for expected in ("rag status", "rag query", "rag context", "rag provider", "rag use"):
                self.assert_true(expected in result.message, f"help text should mention '{expected}'")
        finally:
            fixture.cleanup()

    def _test_cli_status_before_and_after_index_build(self) -> None:
        """`rag status` reflects whether an index has been built."""
        fixture = _Fixture(build_index=False)
        try:
            before = fixture.rag_module.execute("status", [])
            self.assert_true(before.success)
            self.assert_true("Index built : NO" in before.message)

            project_root = Path(fixture.tmp_dir.name) / "project"
            _write_project(
                project_root,
                files={"guide.md": _GUIDE_MD, "faq.md": _FAQ_MD},
                manifest_body=_MANIFEST_BODY,
            )
            with _ChdirGuard(project_root):
                fixture.indexer.build()

            after = fixture.rag_module.execute("status", [])
            self.assert_true(after.success)
            self.assert_true("Index built : YES" in after.message)
            self.assert_true("Documents : 2" in after.message)
        finally:
            fixture.cleanup()

    def _test_cli_query_success_and_missing_argument(self) -> None:
        """`rag query "<text>"` succeeds with text and fails cleanly with none."""
        fixture = _Fixture()
        try:
            success_result = fixture.rag_module.execute("query", ["installation", "guide"])
            self.assert_true(success_result.success)
            self.assert_true("Provider : local" in success_result.message)
            self.assert_true("guide.md" in success_result.message)

            missing_arg_result = fixture.rag_module.execute("query", [])
            self.assert_false(missing_arg_result.success)
            self.assert_true("Usage" in missing_arg_result.message)
        finally:
            fixture.cleanup()

    def _test_cli_context_success_and_no_match(self) -> None:
        """`rag context "<text>"` returns assembled context, or a clear "no match" message."""
        fixture = _Fixture()
        try:
            success_result = fixture.rag_module.execute("context", ["installation", "guide"])
            self.assert_true(success_result.success)
            self.assert_true("Install the package" in success_result.message)

            no_match_result = fixture.rag_module.execute(
                "context", ["zzz_completely_unknown_term_zzz"]
            )
            self.assert_true(no_match_result.success)
            self.assert_equal(no_match_result.message, "No matching context found.")

            missing_arg_result = fixture.rag_module.execute("context", [])
            self.assert_false(missing_arg_result.success)
        finally:
            fixture.cleanup()

    def _test_cli_provider_success_and_failure(self) -> None:
        """`rag provider` reports the active provider, or a clear error when none is selected."""
        fixture = _Fixture()
        try:
            result = fixture.rag_module.execute("provider", [])
            self.assert_true(result.success)
            self.assert_true("Name : local" in result.message)
        finally:
            fixture.cleanup()

        no_provider_yaml = _DEFAULT_CONFIG_YAML.replace(
            'default_provider: "local"', 'default_provider: "none"'
        )
        fixture = _Fixture(config_yaml=no_provider_yaml)
        try:
            result = fixture.rag_module.execute("provider", [])
            self.assert_false(result.success)
        finally:
            fixture.cleanup()

    def _test_cli_use_success_and_failure(self) -> None:
        """`rag use <provider>` succeeds for a real provider and fails for a bad one/bad arg count."""
        fixture = _Fixture()
        try:
            success_result = fixture.rag_module.execute("use", ["cloud"])
            self.assert_true(success_result.success)

            failure_result = fixture.rag_module.execute("use", ["does_not_exist"])
            self.assert_false(failure_result.success)

            usage_result = fixture.rag_module.execute("use", [])
            self.assert_false(usage_result.success)

            too_many_result = fixture.rag_module.execute("use", ["local", "cloud"])
            self.assert_false(too_many_result.success)
        finally:
            fixture.cleanup()

    def _test_cli_unknown_action(self) -> None:
        """An unrecognized 'rag' action fails with a helpful message, not a crash."""
        fixture = _Fixture()
        try:
            result = fixture.rag_module.execute("not_a_real_action", [])
            self.assert_false(result.success)
            self.assert_true("help" in result.message.lower())
        finally:
            fixture.cleanup()

    # ---------- Architectural acceptance criteria ----------

    def _test_no_ai_dependencies(self) -> None:
        """The RAG package never imports any chat-completion / AI provider module.

        The RAG Engine must combine EP-019/EP-020/EP-021 only and must
        never call an LLM (see `rag_engine.py`'s module docstring).
        """
        forbidden_module_fragments = (
            "src.core.ai",
            "gemini",
            "claude_provider",
            "openai",
            "ollama",
            "lmstudio",
            "conversation_manager",
            "prompt_builder",
            "prompt_manager",
            "context_loader",
            "context_manager",
        )
        modules = [rag_engine_module, rag_manager_module, rag_provider_module, rag_result_module]
        self._assert_no_forbidden_imports(modules, forbidden_module_fragments)

    def _test_no_vector_database_or_memory_dependencies(self) -> None:
        """The RAG package never imports a vector database, agent, planning, or memory module.

        EP-022 must implement only the RAG Engine -- no Memory
        Manager, Knowledge Base, Long-Term Memory, Planning Engine,
        Tool Engine, Multi-Agent features, autonomous workflows, or
        vector database of any kind belong to this Engineering
        Package.
        """
        forbidden_module_fragments = (
            "faiss",
            "chroma",
            "pinecone",
            "qdrant",
            "weaviate",
            "numpy",
            "torch",
            "memory_manager",
            "memory_store",
            "knowledge_base",
            "planning",
            "tool_engine",
            "multi_agent",
            "agent_framework",
            "autonomous",
            "browser_automation",
            "computer_automation",
        )
        modules = [rag_engine_module, rag_manager_module, rag_provider_module, rag_result_module]
        self._assert_no_forbidden_imports(modules, forbidden_module_fragments)

    def _test_rag_engine_never_imports_manager_service_or_indexer(self) -> None:
        """`rag_engine.py` never imports RagManager, RagService, RagModule, or ProjectIndexer.

        Matches EP-020's/EP-021's own Engine/Manager separation of
        concerns: `RagEngine` is a pure pipeline over injected
        dependencies; lifecycle wiring belongs exclusively to
        `RagManager`.
        """
        forbidden_module_fragments = (
            "rag_manager",
            "rag_service",
            "rag_module",
            "indexer",
            "embedding.manager",
        )
        self._assert_no_forbidden_imports([rag_engine_module], forbidden_module_fragments)

    def _assert_no_forbidden_imports(self, modules: list, forbidden_module_fragments: tuple) -> None:
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

    def _test_exception_hierarchies_have_common_roots(self) -> None:
        """Every RagEngine/RagManager/RagProvider exception is catchable via its own base class."""
        engine_exceptions = (EmptyQueryError, EmbeddingUnavailableError)
        for exception_type in engine_exceptions:
            self.assert_true(issubclass(exception_type, RagEngineError))

        manager_exceptions = (RagConfigurationError, RagDisabledError, IndexNotBuiltError)
        for exception_type in manager_exceptions:
            self.assert_true(issubclass(exception_type, RagManagerError))

        try:
            raise EmptyQueryError("boom")
        except RagEngineError:
            self.result.add_pass()
        else:
            self.assert_true(False, "EmptyQueryError should be catchable as RagEngineError")

        try:
            raise IndexNotBuiltError("boom")
        except RagManagerError:
            self.result.add_pass()
        else:
            self.assert_true(False, "IndexNotBuiltError should be catchable as RagManagerError")

        self.assert_true(issubclass(NoEmbeddingProviderError, Exception))
        self.assert_true(isinstance(RagContextItem, type))
