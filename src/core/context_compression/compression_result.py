"""Domain model for EP-027 Context Compression.

Defines the plain data types shared by `CompressionProvider` (the
actual compression algorithm), `CompressionEngine` (pipeline
orchestration) and `CompressionService` (the CLI-facing layer): a
single unit of input context (`ContextChunk`) and the outcome of
compressing a whole ordered sequence of them (`CompressionResult`).
This module owns no storage, no deduplication logic and no size
enforcement -- it mirrors the role of
`src/core/semantic/semantic_result.py` relative to
`SemanticProvider`/`SemanticEngine`.

Context Compression performs no reasoning and no summarization. This
module has no dependency on any LLM, AI provider, prompt, agent, or
reflection component.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ContextChunk",
    "CompressionResult",
]


@dataclass(frozen=True)
class ContextChunk:
    """A single unit of context handed to Context Compression.

    Built by `CompressionEngine` either from raw text (split into
    paragraphs) or from EP-026 `SemanticResult` instances (one chunk
    per result). `CompressionProvider` implementations consume this
    type -- they never read a `SemanticResult`, `KnowledgeRecord`, or
    `LongTermRecord` directly.

    Attributes:
        text: The chunk's text content, exactly as received (never
            rewritten or summarized).
        index: The chunk's position in the original, pre-compression
            ordering. Used to preserve ordering through deduplication
            and limit enforcement, never to re-sort chunks by any
            other criterion.
        metadata: The chunk's own metadata, carried through unchanged
            (e.g. a `SemanticResult`'s `source`/`identifier`/`score`).
    """

    text: str
    index: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CompressionResult:
    """The outcome of a single `CompressionEngine.compress_chunks()` call.

    Attributes:
        chunks: The final, compressed chunks, in their original
            relative order (a subsequence of the input, never
            reordered, never rewritten).
        original_chunk_count: Number of chunks received, before any
            deduplication or limit enforcement.
        chunk_count: Number of chunks remaining after compression.
        original_character_count: Total character count of every
            input chunk's text, before compression.
        character_count: Total character count of every output
            chunk's text, after compression.
        estimated_tokens: The active provider's estimated token count
            for the compressed (output) text.
        deduplicated_chunk_count: Number of chunks (or paragraphs
            folded into a surviving chunk) removed as duplicates.
        truncated: Whether one or more chunks were dropped, or a
            chunk's text was shortened, to satisfy the configured
            maximum chunk count or maximum character count.
    """

    chunks: list[ContextChunk]
    original_chunk_count: int
    chunk_count: int
    original_character_count: int
    character_count: int
    estimated_tokens: int
    deduplicated_chunk_count: int
    truncated: bool

    def joined_text(self, separator: str = "\n\n") -> str:
        """Return every output chunk's text joined back into one string.

        Args:
            separator: The separator placed between consecutive
                chunks. Defaults to a blank line, matching the
                paragraph boundary `CompressionEngine` splits raw text
                on.

        Returns:
            The compressed chunks' text, in order, joined by
            `separator`. Empty string if there are no chunks.
        """
        return separator.join(chunk.text for chunk in self.chunks)
