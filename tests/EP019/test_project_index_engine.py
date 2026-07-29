"""Real engineering tests for EP-019 - Project Index Engine.

Builds real temporary repositories on disk (a `PROJECT_MANIFEST.md`
plus real files) and drives `ProjectIndexer` against them exactly as a
caller would -- no mocked internals, matching every other EP's test
suite in this project.
"""

from __future__ import annotations

import ast
import inspect
import json
import os
import tempfile
import time
from pathlib import Path

from src.core.indexing import (
    ChunkBuilder,
    DocumentChunk,
    IndexedDocument,
    IndexStorage,
    JsonIndexStorage,
    MemoryIndexStorage,
    ProjectIndex,
    ProjectIndexer,
    chunk,
    chunk_builder,
    document,
    index,
    indexer,
    storage,
)
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


def _write_project(directory: Path, files: dict[str, str], manifest_body: str) -> None:
    """Write a minimal, self-contained PROJECT_MANIFEST.md plus a set of real files.

    Args:
        directory: Repository root to write into.
        files: relative_path -> file content, for every non-manifest
            file this project should contain.
        manifest_body: The full text of PROJECT_MANIFEST.md.
    """
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "PROJECT_MANIFEST.md").write_text(manifest_body, encoding="utf-8")
    for relative_path, content in files.items():
        path = directory / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


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


@TestRegistry.register
class ProjectIndexEngineTest(BaseTest):
    """Real tests covering EP-019's Project Index Engine."""

    NAME = "EP019"

    def run(self):
        """Execute every Project Index Engine check and return the aggregated result."""
        self._test_empty_repository()
        self._test_missing_manifest()
        self._test_invalid_manifest()
        self._test_single_document()
        self._test_multiple_documents()
        self._test_large_document()
        self._test_very_small_document()
        self._test_unicode_documents()
        self._test_document_with_headings()
        self._test_document_without_headings()
        self._test_chunk_overlap()
        self._test_chunk_ordering()
        self._test_line_numbers()
        self._test_metadata_is_defensively_copied()
        self._test_index_serialization()
        self._test_index_deserialization_round_trip()
        self._test_index_rebuild_picks_up_disk_changes()
        self._test_cache_clear()
        self._test_chunk_builder_never_produces_empty_chunks()
        self._test_chunk_builder_never_splits_a_word()
        self._test_memory_storage_backend()
        self._test_no_ai_specific_dependencies()
        return self.result

    # ---------- Repository / manifest edge cases ----------

    def _test_empty_repository(self) -> None:
        """A manifest with no Context Documents produces a valid, empty index."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            _write_project(
                project,
                files={},
                manifest_body=(
                    "# Project Name\nEmpty Project\n\n"
                    "# Current Version\n1.0.0\n\n"
                    "# Project Type\nlibrary\n"
                ),
            )
            with _ChdirGuard(project):
                index_result = ProjectIndexer().build()
            self.assert_equal(index_result.documents(), (), "Empty repository should index zero documents")
            self.assert_equal(index_result.chunks(), (), "Empty repository should have zero chunks")
            self.assert_equal(
                index_result.statistics()["document_count"], 0, "statistics() should report zero documents"
            )

    def _test_missing_manifest(self) -> None:
        """build() raises ValueError when no manifest file can be found.

        Uses a manifest filename that cannot exist anywhere on disk --
        pointing at the real 'PROJECT_MANIFEST.md' name would let
        `find_manifest_path()`'s deterministic fallback walk up from
        this module's own directory and find *this repository's own*
        manifest, which is correct production behavior but would make
        this specific test meaningless when run from within this repo.
        """
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "no_manifest"
            project.mkdir(parents=True, exist_ok=True)
            with _ChdirGuard(project):
                raised = False
                try:
                    ProjectIndexer(manifest_filename="NO_SUCH_MANIFEST_EP019_TEST.md").build()
                except ValueError:
                    raised = True
            self.assert_true(raised, "build() should raise ValueError when the manifest is missing")

    def _test_invalid_manifest(self) -> None:
        """A malformed/near-empty manifest never crashes the indexer -- it degrades gracefully."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "invalid_manifest"
            _write_project(
                project,
                files={},
                manifest_body="not a real manifest, just some free text with no headings at all\n",
            )
            with _ChdirGuard(project):
                index_result = ProjectIndexer().build()
            self.assert_equal(index_result.project_name, "", "Malformed manifest should yield an empty project name")
            self.assert_equal(index_result.documents(), (), "Malformed manifest declares no Context Documents")

    # ---------- Document counts ----------

    def _test_single_document(self) -> None:
        """A manifest declaring exactly one document indexes exactly one document."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "single_doc"
            _write_project(
                project,
                files={"README.md": "# Readme\nJust one short document to index.\n"},
                manifest_body="# Project Name\nSingle Doc\n\n# Context Documents\n- README.md\n",
            )
            with _ChdirGuard(project):
                index_result = ProjectIndexer().build()
            self.assert_equal(len(index_result.documents()), 1, "Exactly one document should be indexed")
            self.assert_equal(
                index_result.documents()[0].relative_path, "README.md", "The indexed document's path should match"
            )
            self.assert_true(len(index_result.documents()[0].chunks()) >= 1, "Document should have at least one chunk")

    def _test_multiple_documents(self) -> None:
        """A manifest declaring several documents indexes every one of them, each with a unique id."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "multi_doc"
            _write_project(
                project,
                files={
                    "docs/a.md": "# A\nContent of document A.\n",
                    "docs/b.md": "# B\nContent of document B.\n",
                    "docs/c.md": "# C\nContent of document C.\n",
                },
                manifest_body="# Project Name\nMulti Doc\n\n# Context Documents\n- docs/\n",
            )
            with _ChdirGuard(project):
                index_result = ProjectIndexer().build()
            self.assert_equal(len(index_result.documents()), 3, "All three documents should be indexed")
            paths = {document_obj.relative_path for document_obj in index_result.documents()}
            self.assert_equal(
                paths, {"docs/a.md", "docs/b.md", "docs/c.md"}, "Every declared document should be present"
            )
            ids = {document_obj.document_id for document_obj in index_result.documents()}
            self.assert_equal(len(ids), 3, "Every document should have a unique document_id")

    # ---------- Chunking behavior ----------

    def _test_large_document(self) -> None:
        """A document larger than the default chunk size is split into multiple chunks."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "large_doc"
            paragraph = "This paragraph repeats to build a long document body for chunking. " * 30
            content = f"# Large\n\n{paragraph}\n\n{paragraph}\n\n{paragraph}\n"
            _write_project(
                project, files={"large.md": content}, manifest_body="# Context Documents\n- large.md\n"
            )
            with _ChdirGuard(project):
                index_result = ProjectIndexer().build()
            document_obj = index_result.documents()[0]
            self.assert_true(len(document_obj.chunks()) > 1, "A document far larger than chunk_size should split")
            for chunk_obj in document_obj.chunks():
                self.assert_true(
                    chunk_obj.character_count <= ChunkBuilder().chunk_size + 200,
                    "Each chunk should stay close to the configured chunk_size",
                )

    def _test_very_small_document(self) -> None:
        """A document far smaller than chunk_size produces exactly one chunk containing its full text."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "small_doc"
            _write_project(project, files={"tiny.md": "Hi."}, manifest_body="# Context Documents\n- tiny.md\n")
            with _ChdirGuard(project):
                index_result = ProjectIndexer().build()
            chunks = index_result.documents()[0].chunks()
            self.assert_equal(len(chunks), 1, "A tiny document should produce exactly one chunk")
            self.assert_equal(chunks[0].text(), "Hi.", "The single chunk should contain the document's full text")

    def _test_unicode_documents(self) -> None:
        """Unicode content (non-Latin scripts, emoji) is indexed byte-for-byte intact."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "unicode_doc"
            content = "# Заголовок\nПривет, мир! 😀 こんにちは世界。"
            _write_project(project, files={"u.md": content}, manifest_body="# Context Documents\n- u.md\n")
            with _ChdirGuard(project):
                index_result = ProjectIndexer().build()
            document_obj = index_result.documents()[0]
            reconstructed = "".join(chunk_obj.text() for chunk_obj in document_obj.chunks())
            self.assert_true("😀" in reconstructed, "Emoji should survive chunking intact")
            self.assert_true("こんにちは世界" in reconstructed, "Non-Latin scripts should survive chunking intact")
            self.assert_equal(
                document_obj.chunks()[0].heading, "Заголовок", "A unicode heading should be parsed correctly"
            )

    def _test_document_with_headings(self) -> None:
        """Every chunk's `heading` matches the Markdown heading it actually falls under."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "headings_doc"
            content = (
                "# Intro\nIntroductory text here.\n\n"
                "## Details\nDetailed text here.\n\n"
                "# Conclusion\nConcluding text here.\n"
            )
            _write_project(project, files={"h.md": content}, manifest_body="# Context Documents\n- h.md\n")
            with _ChdirGuard(project):
                index_result = ProjectIndexer().build()
            headings = {chunk_obj.heading for chunk_obj in index_result.documents()[0].chunks()}
            self.assert_equal(
                headings, {"Intro", "Details", "Conclusion"}, "Every declared heading should appear on some chunk"
            )

    def _test_document_without_headings(self) -> None:
        """A document with no Markdown headings produces chunks whose heading is always ''."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "no_headings_doc"
            content = "Plain paragraph one, no headings anywhere in this file.\n\nPlain paragraph two, same story.\n"
            _write_project(project, files={"p.md": content}, manifest_body="# Context Documents\n- p.md\n")
            with _ChdirGuard(project):
                index_result = ProjectIndexer().build()
            for chunk_obj in index_result.documents()[0].chunks():
                self.assert_equal(chunk_obj.heading, "", "A headingless document's chunks should have heading ''")

    def _test_chunk_overlap(self) -> None:
        """Consecutive chunks under the same heading share trailing/leading overlap text."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "overlap_doc"
            sentences = " ".join(f"Sentence number {i} of the overlap test document." for i in range(20))
            content = f"# Section\n{sentences}\n"
            _write_project(project, files={"o.md": content}, manifest_body="# Context Documents\n- o.md\n")
            with _ChdirGuard(project):
                indexer_obj = ProjectIndexer(chunk_builder=ChunkBuilder(chunk_size=200, overlap=65))
                index_result = indexer_obj.build()
            chunks = index_result.documents()[0].chunks()
            self.assert_true(len(chunks) > 1, "This document should split into multiple chunks under this config")
            found_overlap = False
            for first, second in zip(chunks, chunks[1:]):
                if first.heading != second.heading:
                    continue
                a, b = first.text(), second.text()
                if any(a[-length:] == b[:length] for length in range(5, min(len(a), len(b)) + 1)):
                    found_overlap = True
                    break
            self.assert_true(found_overlap, "At least one pair of consecutive same-heading chunks should overlap")

    def _test_chunk_ordering(self) -> None:
        """Chunks come back in document order with sequential, document-scoped ids."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "ordering_doc"
            content = "# Sec\n" + ("Filler sentence to pad the section out nicely. " * 40)
            _write_project(project, files={"seq.md": content}, manifest_body="# Context Documents\n- seq.md\n")
            with _ChdirGuard(project):
                indexer_obj = ProjectIndexer(chunk_builder=ChunkBuilder(chunk_size=100, overlap=10))
                index_result = indexer_obj.build()
            chunks = index_result.documents()[0].chunks()
            self.assert_true(len(chunks) > 2, "This document should produce several chunks")
            for position, chunk_obj in enumerate(chunks):
                self.assert_equal(
                    chunk_obj.chunk_id, f"{chunk_obj.document_id}:{position:04d}", "Chunk ids should be sequential"
                )
            self.assert_true(
                all(a.start_line <= b.start_line for a, b in zip(chunks, chunks[1:])),
                "Chunks should be returned in non-decreasing start_line order",
            )

    def _test_line_numbers(self) -> None:
        """start_line/end_line accurately reflect a chunk's position in the source file."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "lines_doc"
            content = "Line one paragraph.\n\nLine three paragraph.\n\nLine five paragraph.\n"
            _write_project(project, files={"l.md": content}, manifest_body="# Context Documents\n- l.md\n")
            with _ChdirGuard(project):
                indexer_obj = ProjectIndexer(chunk_builder=ChunkBuilder(chunk_size=25, overlap=2))
                index_result = indexer_obj.build()
            chunks = index_result.documents()[0].chunks()
            self.assert_equal(len(chunks), 3, "Three well-separated paragraphs should yield three chunks")
            self.assert_equal(chunks[0].start_line, 1, "First paragraph should start on line 1")
            self.assert_equal(chunks[1].start_line, 3, "Second paragraph should start on line 3")
            self.assert_equal(chunks[2].start_line, 5, "Third paragraph should start on line 5")

    # ---------- Metadata / immutability ----------

    def _test_metadata_is_defensively_copied(self) -> None:
        """metadata() always returns a copy -- mutating it can never affect the stored object."""
        chunk_obj = DocumentChunk(
            chunk_id="doc:0000",
            document_id="doc",
            relative_path="a.md",
            heading="",
            text="hello",
            start_line=1,
            end_line=1,
            metadata={"key": "value"},
        )
        returned = chunk_obj.metadata()
        returned["key"] = "mutated"
        returned["new_key"] = "also mutated"
        self.assert_equal(chunk_obj.metadata(), {"key": "value"}, "Chunk metadata should be immutable from outside")

        document_obj = IndexedDocument(
            document_id="doc",
            relative_path="a.md",
            absolute_path="/tmp/a.md",
            title="A",
            size=5,
            last_modified=0.0,
            checksum="abc",
            metadata={"key": "value"},
        )
        document_metadata = document_obj.metadata()
        document_metadata["key"] = "mutated"
        self.assert_equal(
            document_obj.metadata(), {"key": "value"}, "Document metadata should be immutable from outside"
        )

        self.assert_true(
            DocumentChunk.__init__.__code__.co_argcount > 0, "Sanity check: DocumentChunk is constructible"
        )

    # ---------- Serialization ----------

    def _test_index_serialization(self) -> None:
        """to_dict() produces a plain, JSON-serializable structure preserving every chunk field."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "serialize_doc"
            _write_project(
                project,
                files={"a.md": "# A\nSome content with headings and text.\n"},
                manifest_body="# Project Name\nSerialize\n\n# Context Documents\n- a.md\n",
            )
            with _ChdirGuard(project):
                index_result = ProjectIndexer().build()
            data = index_result.to_dict()
            serialized = json.dumps(data)
            reparsed = json.loads(serialized)
            self.assert_equal(reparsed["project_name"], "Serialize", "Project name should round-trip through JSON")
            first_chunk = reparsed["documents"][0]["chunks"][0]
            for field in ("chunk_id", "document_id", "relative_path", "heading", "text", "start_line", "end_line"):
                self.assert_true(field in first_chunk, f"Serialized chunk should preserve '{field}'")

    def _test_index_deserialization_round_trip(self) -> None:
        """from_dict(to_dict(index)) reconstructs an index equal to the original."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "roundtrip_doc"
            _write_project(
                project,
                files={"a.md": "# A\nRound trip content.\n", "b.md": "No heading here at all.\n"},
                manifest_body="# Project Name\nRoundTrip\n\n# Context Documents\n- a.md\n- b.md\n",
            )
            with _ChdirGuard(project):
                index_result = ProjectIndexer().build()
            reconstructed = ProjectIndex.from_dict(json.loads(json.dumps(index_result.to_dict())))
            self.assert_true(index_result == reconstructed, "Deserialized index should equal the original")
            self.assert_equal(
                len(reconstructed.chunks()), len(index_result.chunks()), "Chunk count should survive round-trip"
            )

            storage_path = Path(tmp) / "index.json"
            json_storage = JsonIndexStorage(storage_path)
            json_storage.save(index_result)
            self.assert_true(storage_path.is_file(), "JsonIndexStorage.save() should write a file")
            loaded = json_storage.load()
            self.assert_true(loaded == index_result, "JsonIndexStorage round-trip should equal the original index")

    # ---------- Rebuild / cache lifecycle ----------

    def _test_index_rebuild_picks_up_disk_changes(self) -> None:
        """rebuild() reflects the current on-disk content, even after a prior build()."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "rebuild_doc"
            _write_project(
                project, files={"a.md": "Original content.\n"}, manifest_body="# Context Documents\n- a.md\n"
            )
            with _ChdirGuard(project):
                indexer_obj = ProjectIndexer()
                first = indexer_obj.build()
                original_checksum = first.documents()[0].checksum

                time.sleep(0.05)
                (project / "a.md").write_text("Completely different content now.\n", encoding="utf-8")
                os.utime(project / "a.md", None)

                second = indexer_obj.rebuild()
            self.assert_true(
                second.documents()[0].checksum != original_checksum,
                "rebuild() should reflect the file's new content",
            )

    def _test_cache_clear(self) -> None:
        """clear() drops the in-memory index and lets a fresh build() succeed afterward."""
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "clear_doc"
            _write_project(
                project, files={"a.md": "Some content to index.\n"}, manifest_body="# Context Documents\n- a.md\n"
            )
            with _ChdirGuard(project):
                indexer_obj = ProjectIndexer()
                indexer_obj.build()
                self.assert_not_none(indexer_obj.index(), "index() should be populated right after build()")
                indexer_obj.clear()
                self.assert_true(indexer_obj.index() is None, "index() should be None right after clear()")
                rebuilt = indexer_obj.build()
                self.assert_equal(len(rebuilt.documents()), 1, "build() after clear() should work normally again")

    # ---------- ChunkBuilder invariants ----------

    def _test_chunk_builder_never_produces_empty_chunks(self) -> None:
        """No chunk (across a variety of inputs) is ever empty or whitespace-only."""
        builder = ChunkBuilder(chunk_size=40, overlap=5)
        samples = [
            "",
            "   \n\n   ",
            "# Heading Only\n",
            "# H\n\n\n\n\nSome text after blank lines.\n\n\n",
            "Word " * 500,
        ]
        for sample in samples:
            for chunk_obj in builder.build("doc", "s.md", sample):
                self.assert_true(len(chunk_obj.text()) > 0, "No chunk should ever be empty")
                self.assert_true(chunk_obj.text().strip() != "", "No chunk should ever be whitespace-only")

    def _test_chunk_builder_never_splits_a_word(self) -> None:
        """Even under a pathologically small chunk_size, a long word is kept whole, never fragmented."""
        builder = ChunkBuilder(chunk_size=5, overlap=1)
        long_word = "Supercalifragilisticexpialidocious"
        chunks = builder.build("doc", "w.md", f"{long_word} short words here")
        self.assert_true(
            any(chunk_obj.text().strip() == long_word for chunk_obj in chunks),
            "The oversized word should appear intact in exactly one chunk",
        )
        for chunk_obj in chunks:
            for word in chunk_obj.text().split():
                self.assert_true(
                    word == long_word or word in ["short", "words", "here"],
                    f"Chunk should never contain a fragment of a word: {word!r}",
                )

    # ---------- Storage backends ----------

    def _test_memory_storage_backend(self) -> None:
        """MemoryIndexStorage persists within the process but exists()/clear() behave correctly."""
        backend: IndexStorage = MemoryIndexStorage()
        self.assert_false(backend.exists(), "A fresh MemoryIndexStorage should report no stored index")
        self.assert_true(backend.load() is None, "A fresh MemoryIndexStorage should load None")

        sample_index = ProjectIndex(repository_root="/tmp/x", project_name="X", version="1", project_type="lib", description="")
        backend.save(sample_index)
        self.assert_true(backend.exists(), "exists() should be True right after save()")
        self.assert_true(backend.load() == sample_index, "load() should return exactly what was saved")

        backend.clear()
        self.assert_false(backend.exists(), "exists() should be False right after clear()")

    # ---------- Architectural acceptance criteria ----------

    def _test_no_ai_specific_dependencies(self) -> None:
        """The indexing package never imports any AI provider, PromptBuilder, ContextLoader, or ContextManager module."""
        forbidden_module_fragments = (
            "gemini", "claude", "ollama", "openai",
            "prompt_builder", "context_loader", "context_manager",
        )
        modules = [chunk, chunk_builder, document, index, indexer, storage]
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
