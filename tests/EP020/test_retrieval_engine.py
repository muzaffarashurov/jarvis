"""Real engineering tests for EP-020 - Semantic Retrieval Engine.

Builds a real `ProjectIndex` in memory, using only EP-019's own public
`ProjectIndex`/`IndexedDocument`/`DocumentChunk` constructors (see
`src.core.indexing`), and drives `RetrievalEngine` against it exactly
as a caller would -- no mocked internals, matching every other EP's
test suite in this project.
"""

from __future__ import annotations

import ast
import inspect

from src.core.indexing import DocumentChunk, IndexedDocument, ProjectIndex
from src.core.retrieval import (
    Query,
    RankingEngine,
    RetrievalEngine,
    RetrievalResult,
    query,
    ranking,
    result,
    retrieval_engine,
)
from src.core.retrieval.result import PREVIEW_MAX_CHARACTERS
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


def _build_index() -> ProjectIndex:
    """Build a small, deterministic ProjectIndex fixture for retrieval tests.

    Three documents:
        - "guide.md" ("User Guide"): two chunks, one under an
          "Installation" heading, one under a "Usage" heading.
        - "faq.md" ("FAQ"): one chunk, no heading, that also mentions
          installation.
        - "empty.md" ("Empty Document"): zero chunks, to exercise the
          no-chunks-to-score edge case.
    """
    guide_chunks = (
        DocumentChunk(
            chunk_id="guide:0",
            document_id="guide",
            relative_path="guide.md",
            heading="Installation",
            text=(
                "Install the package by running pip install jarvis. "
                "This section is the installation guide."
            ),
            start_line=1,
            end_line=3,
        ),
        DocumentChunk(
            chunk_id="guide:1",
            document_id="guide",
            relative_path="guide.md",
            heading="Usage",
            text="Run jarvis start to launch the application. Usage is simple and fast.",
            start_line=4,
            end_line=6,
        ),
    )
    guide = IndexedDocument(
        document_id="guide",
        relative_path="guide.md",
        absolute_path="/repo/guide.md",
        title="User Guide",
        size=200,
        last_modified=0.0,
        checksum="guide-checksum",
        chunks=guide_chunks,
    )

    faq_chunks = (
        DocumentChunk(
            chunk_id="faq:0",
            document_id="faq",
            relative_path="faq.md",
            heading="",
            text="Frequently asked questions about jarvis, including common installation issues.",
            start_line=1,
            end_line=2,
        ),
    )
    faq = IndexedDocument(
        document_id="faq",
        relative_path="faq.md",
        absolute_path="/repo/faq.md",
        title="FAQ",
        size=100,
        last_modified=0.0,
        checksum="faq-checksum",
        chunks=faq_chunks,
    )

    empty = IndexedDocument(
        document_id="empty",
        relative_path="empty.md",
        absolute_path="/repo/empty.md",
        title="Empty Document",
        size=0,
        last_modified=0.0,
        checksum="empty-checksum",
        chunks=(),
    )

    return ProjectIndex(
        repository_root="/repo",
        project_name="RetrievalFixture",
        version="1.0.0",
        project_type="library",
        description="Fixture project for EP-020 retrieval tests.",
        documents=(guide, faq, empty),
    )


@TestRegistry.register
class RetrievalEngineTest(BaseTest):
    """Real tests covering EP-020's Semantic Retrieval Engine."""

    NAME = "EP020"

    def run(self):
        """Execute every Retrieval Engine check and return the aggregated result."""
        self._test_empty_query()
        self._test_unknown_query()
        self._test_exact_match()
        self._test_multiple_matches()
        self._test_ranking_order()
        self._test_top_k()
        self._test_statistics()
        self._test_deterministic_output()
        self._test_search_documents_deduplicates_per_document()
        self._test_search_is_alias_for_search_chunks()
        self._test_query_normalization()
        self._test_exact_phrase_detection()
        self._test_case_insensitivity()
        self._test_results_never_expose_raw_chunks()
        self._test_preview_is_truncated()
        self._test_document_with_no_chunks_never_crashes()
        self._test_ranking_engine_direct_scoring()
        self._test_no_ai_or_embedding_dependencies()
        return self.result

    # ---------- Core search behavior ----------

    def _test_empty_query(self) -> None:
        """An empty (or whitespace-only) query returns no results, from every entry point."""
        engine = RetrievalEngine(_build_index())
        self.assert_equal(engine.search(""), [], "Empty string query should return no results")
        self.assert_equal(engine.search("   "), [], "Whitespace-only query should return no results")
        self.assert_equal(
            engine.search_documents(""), [], "Empty query should return no document results"
        )
        self.assert_equal(engine.top_k("", 5), [], "Empty query should return no top_k results")

    def _test_unknown_query(self) -> None:
        """A query matching nothing in the index returns an empty list, not an error."""
        engine = RetrievalEngine(_build_index())
        results = engine.search("zzz_completely_unknown_term_zzz")
        self.assert_equal(results, [], "Unknown query should return zero results")

    def _test_exact_match(self) -> None:
        """A quoted exact phrase matches only the chunk containing that exact phrase."""
        engine = RetrievalEngine(_build_index())
        results = engine.search('"installation guide"')
        self.assert_equal(len(results), 1, "Exact phrase should match exactly one chunk")
        self.assert_equal(
            results[0].chunk_id, "guide:0", "Exact phrase match should be the Installation chunk"
        )
        self.assert_equal(
            results[0].relative_path, "guide.md", "Exact phrase match should come from guide.md"
        )

        no_match = engine.search('"this exact phrase does not exist anywhere"')
        self.assert_equal(no_match, [], "A phrase that appears nowhere should match nothing")

    def _test_multiple_matches(self) -> None:
        """A single-keyword query can match chunks across multiple documents."""
        engine = RetrievalEngine(_build_index())
        results = engine.search("installation")
        matched_paths = {result_item.relative_path for result_item in results}
        self.assert_equal(len(results), 2, "'installation' should match chunks in two documents")
        self.assert_equal(
            matched_paths, {"guide.md", "faq.md"}, "Matches should come from guide.md and faq.md"
        )

    def _test_ranking_order(self) -> None:
        """Results are always returned highest score first."""
        engine = RetrievalEngine(_build_index())
        results = engine.search("installation")
        scores = [result_item.score for result_item in results]
        self.assert_equal(scores, sorted(scores, reverse=True), "Results should be sorted by descending score")

        # The Installation-heading chunk should outrank the FAQ chunk:
        # it earns the heading bonus and the title bonus (via "installation
        # guide" appearing in guide.md's own chunk text) that the FAQ
        # chunk does not.
        self.assert_equal(
            results[0].chunk_id, "guide:0", "The heading+title-matching chunk should rank first"
        )

    def _test_top_k(self) -> None:
        """top_k() caps the number of returned results and rejects non-positive k."""
        engine = RetrievalEngine(_build_index())
        full = engine.search("installation")
        limited = engine.top_k("installation", 1)
        self.assert_equal(len(limited), 1, "top_k(query, 1) should return exactly one result")
        self.assert_equal(limited[0], full[0], "top_k(query, 1) should return the single best result")
        self.assert_equal(engine.top_k("installation", 0), [], "top_k(query, 0) should return no results")
        self.assert_equal(engine.top_k("installation", -3), [], "top_k(query, negative) should return no results")
        self.assert_equal(
            engine.top_k("installation", 999),
            full,
            "top_k() with k larger than the result count should return every result",
        )

    def _test_statistics(self) -> None:
        """statistics() reports exactly what the underlying ProjectIndex reports."""
        index = _build_index()
        engine = RetrievalEngine(index)
        self.assert_equal(
            engine.statistics(), index.statistics(), "RetrievalEngine.statistics() should match ProjectIndex.statistics()"
        )
        self.assert_equal(engine.statistics()["document_count"], 3, "Fixture should have three documents")
        self.assert_equal(engine.statistics()["chunk_count"], 3, "Fixture should have three chunks total")

    def _test_deterministic_output(self) -> None:
        """Running the identical query twice produces the identical ordered result list."""
        engine = RetrievalEngine(_build_index())
        first_run = engine.search("installation jarvis")
        second_run = engine.search("installation jarvis")
        self.assert_equal(first_run, second_run, "Identical queries should produce identical output")

        third_run = RetrievalEngine(_build_index()).search("installation jarvis")
        self.assert_equal(
            first_run, third_run, "A fresh engine over an equivalent index should produce identical output"
        )

    # ---------- search_documents / search aliasing ----------

    def _test_search_documents_deduplicates_per_document(self) -> None:
        """search_documents() returns at most one result per document: its best-scoring chunk."""
        engine = RetrievalEngine(_build_index())
        results = engine.search_documents("installation")
        document_ids = [result_item.document_id for result_item in results]
        self.assert_equal(len(document_ids), len(set(document_ids)), "Each document should appear at most once")
        self.assert_equal(len(results), 2, "'installation' should match exactly two documents")

        guide_result = next(r for r in results if r.document_id == "guide")
        self.assert_equal(
            guide_result.chunk_id, "guide:0", "guide.md's best chunk for 'installation' should be guide:0"
        )

    def _test_search_is_alias_for_search_chunks(self) -> None:
        """search() and search_chunks() return identical results for the same query."""
        engine = RetrievalEngine(_build_index())
        self.assert_equal(
            engine.search("usage"), engine.search_chunks("usage"), "search() should equal search_chunks()"
        )

    # ---------- Query normalization ----------

    def _test_query_normalization(self) -> None:
        """Query.from_text() lowercases, trims, and collapses internal whitespace."""
        built = Query.from_text("  Hello    World  ")
        self.assert_equal(built.normalized, "hello world", "Query should be lowercased and whitespace-collapsed")
        self.assert_equal(built.terms, ("hello", "world"), "Query terms should split on whitespace")
        self.assert_false(built.exact_phrase, "An unquoted query should not be an exact-phrase query")

        empty_query = Query.from_text("   ")
        self.assert_true(empty_query.is_empty, "A whitespace-only query should be empty")

    def _test_exact_phrase_detection(self) -> None:
        """A double-quoted query is detected as an exact-phrase query, quotes stripped."""
        built = Query.from_text('"Foo   Bar"')
        self.assert_true(built.exact_phrase, "A quoted query should be detected as exact-phrase")
        self.assert_equal(built.normalized, "foo bar", "Quotes should be stripped before normalization")

    def _test_case_insensitivity(self) -> None:
        """Search is case-insensitive: an uppercase query matches lowercase content."""
        engine = RetrievalEngine(_build_index())
        self.assert_equal(
            engine.search("INSTALLATION"), engine.search("installation"), "Search should be case-insensitive"
        )

    # ---------- Output shape ----------

    def _test_results_never_expose_raw_chunks(self) -> None:
        """Every returned result is a RetrievalResult, never a DocumentChunk."""
        engine = RetrievalEngine(_build_index())
        results = engine.search("installation")
        self.assert_true(len(results) > 0, "Sanity check: query should have matches")
        for result_item in results:
            self.assert_true(
                isinstance(result_item, RetrievalResult), "Every result should be a RetrievalResult"
            )
            self.assert_false(
                isinstance(result_item, DocumentChunk), "No result should ever be a raw DocumentChunk"
            )

    def _test_preview_is_truncated(self) -> None:
        """A chunk longer than the preview limit is truncated with a trailing ellipsis."""
        long_text = "word " * 100  # far longer than PREVIEW_MAX_CHARACTERS
        long_chunk = DocumentChunk(
            chunk_id="long:0",
            document_id="long",
            relative_path="long.md",
            heading="",
            text=long_text,
            start_line=1,
            end_line=1,
        )
        preview_result = RetrievalResult.from_chunk(long_chunk, score=1.0)
        self.assert_true(
            len(preview_result.preview) <= PREVIEW_MAX_CHARACTERS + 3, "Preview should be capped in length"
        )
        self.assert_true(preview_result.preview.endswith("..."), "A truncated preview should end with '...'")

        short_chunk = DocumentChunk(
            chunk_id="short:0",
            document_id="short",
            relative_path="short.md",
            heading="",
            text="A short chunk.",
            start_line=1,
            end_line=1,
        )
        short_result = RetrievalResult.from_chunk(short_chunk, score=1.0)
        self.assert_equal(short_result.preview, "A short chunk.", "A short chunk's preview should be unchanged")

    def _test_document_with_no_chunks_never_crashes(self) -> None:
        """A document with zero chunks (e.g. 'empty.md') never crashes search and is never matched."""
        engine = RetrievalEngine(_build_index())
        results = engine.search("empty document anything")
        matched_paths = {result_item.relative_path for result_item in results}
        self.assert_true("empty.md" not in matched_paths, "A chunkless document should never appear in results")

    # ---------- RankingEngine (direct) ----------

    def _test_ranking_engine_direct_scoring(self) -> None:
        """RankingEngine.score_chunk() applies the title/heading/phrase bonuses deterministically."""
        index = _build_index()
        guide = index.document("guide")
        installation_chunk = guide.chunks()[0]
        usage_chunk = guide.chunks()[1]
        engine = RankingEngine()

        empty_query_score = engine.score_chunk(Query.from_text(""), installation_chunk, guide)
        self.assert_equal(empty_query_score, 0.0, "An empty query should always score 0.0")

        no_match_score = engine.score_chunk(Query.from_text("zzz_no_match_zzz"), installation_chunk, guide)
        self.assert_equal(no_match_score, 0.0, "A non-matching query should score 0.0")

        heading_query = Query.from_text("installation")
        installation_score = engine.score_chunk(heading_query, installation_chunk, guide)
        usage_score = engine.score_chunk(heading_query, usage_chunk, guide)
        self.assert_true(
            installation_score > usage_score,
            "The chunk under the matching heading should outscore the chunk that is not",
        )

        repeated_score = engine.score_chunk(heading_query, installation_chunk, guide)
        self.assert_equal(installation_score, repeated_score, "Scoring the same inputs twice should be deterministic")

    # ---------- Architectural acceptance criteria ----------

    def _test_no_ai_or_embedding_dependencies(self) -> None:
        """The retrieval package never imports any AI, embedding, vector, or Prompt/Context module."""
        forbidden_module_fragments = (
            "gemini", "claude", "ollama", "openai",
            "prompt_builder", "context_loader", "context_manager",
            "embedding", "vector", "faiss", "numpy", "torch",
        )
        modules = [query, ranking, result, retrieval_engine]
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
