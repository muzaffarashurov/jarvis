"""CompressionProvider domain model for EP-027 Context Compression.

Defines the abstraction every context-compression provider must
implement so the rest of Jarvis never needs to know which compression
strategy is currently active, matching the pattern already used by
the Semantic Search Provider Framework
(see `src/core/semantic/semantic_provider.py`), the Embedding Provider
Framework (`src/core/embedding/provider.py`) and the AI Provider
Framework (`src/core/ai/provider.py`).

The task brief for EP-027 names three *future* provider strategies --
`TokenCompressionProvider`, `AdaptiveCompressionProvider`,
`SmartCompressionProvider` -- and is explicit that none of them is to
be implemented yet, "only create abstraction". Taken literally that
would leave Context Compression without any working provider at all,
which conflicts with this EP's own responsibilities ("Context
Compression must: receive context, estimate context size, estimate
token count, remove duplicated chunks, remove duplicated paragraphs,
preserve chunk ordering, preserve metadata, enforce maximum context
size"). This module resolves that the same way EP-026 resolved the
analogous conflict: it implements exactly one concrete, built-in
provider -- `DefaultCompressionProvider`, registered under the stable
name "compression" (matching 'context_compression.default_provider'
in config/config.yaml) -- so the subsystem is actually usable today,
while still not implementing any of the three named *future* provider
classes. `TokenCompressionProvider`, `AdaptiveCompressionProvider` and
`SmartCompressionProvider` remain unimplemented extension points for a
future EP.

This module performs no AI reasoning, no summarization, and never
rewrites a chunk's text (other than truncating it verbatim to fit a
character budget): it only deduplicates, orders, and limits
`ContextChunk` instances it is handed, exactly like
`DefaultSemanticProvider.search()` only scores and ranks
`SemanticCandidate` instances it is handed.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from src.core.context_compression.compression_result import CompressionResult, ContextChunk

__all__ = [
    "CompressionProviderStatus",
    "CompressionProviderHealth",
    "ContextCompressionError",
    "CompressionConfigurationError",
    "CompressionProviderError",
    "CompressionProviderConfigurationError",
    "CompressionProviderUnavailableError",
    "CompressionProvider",
    "DefaultCompressionProvider",
]

#: Characters-per-token used by `DefaultCompressionProvider.estimate_tokens()`.
#: A fixed, documented arithmetic heuristic (never a tokenizer model,
#: never a network call) -- comparable to the widely cited "~4
#: characters per token" rule of thumb for English text.
_CHARACTERS_PER_TOKEN: int = 4

#: Regular expression splitting text into paragraphs on one or more
#: blank lines (matching common Markdown/plain-text paragraph
#: conventions). Used for paragraph-level deduplication only -- it
#: never merges, rewrites, or reorders paragraph content.
_PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n")


class CompressionProviderStatus(str, Enum):
    """Lifecycle status a registered compression provider can report.

    Attributes:
        DISABLED: The provider is turned off in configuration.
        NOT_CONFIGURED: The provider is enabled but is missing
            configuration it needs to be usable.
        AVAILABLE: The provider is enabled and fully configured.
    """

    DISABLED = "DISABLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    AVAILABLE = "AVAILABLE"


@dataclass(frozen=True)
class CompressionProviderHealth:
    """Result of a provider's own `health()` check.

    This is a configuration-derived readiness check only -- no
    provider performs a network request or compresses real context as
    part of `health()`.

    Attributes:
        available: Whether the provider reports itself ready for use.
        message: Human-readable explanation of the health result.
    """

    available: bool
    message: str


class ContextCompressionError(Exception):
    """Common root for every exception raised by Context Compression (EP-027).

    Downstream packages (e.g. a future Agent Framework) can catch this
    single type to handle "anything context-compression-related"
    without needing to know about every specific failure mode
    (provider-level, engine-level, manager-level, or
    configuration-level).
    """


class CompressionConfigurationError(ContextCompressionError):
    """Raised when 'context_compression.*' configuration itself is invalid.

    This is distinct from `CompressionProviderConfigurationError`,
    which is a *runtime* condition (a provider is currently disabled
    or unconfigured, and may become available later without
    restarting). `CompressionConfigurationError` means the
    configuration value itself is malformed (wrong type, empty, or
    references a provider that does not exist) -- restarting with
    corrected configuration is required to resolve it.
    """


class CompressionProviderError(ContextCompressionError):
    """Base class for errors raised while using a compression provider."""


class CompressionProviderConfigurationError(CompressionProviderError):
    """Raised when a provider is disabled or missing required configuration."""


class CompressionProviderUnavailableError(CompressionProviderError):
    """Raised when a provider cannot currently serve compression requests."""


class CompressionProvider(ABC):
    """Structural contract every context-compression provider must implement.

    A provider deduplicates, orders, and limits `ContextChunk`
    instances it is handed -- it never fetches context itself, never
    calls an AI provider, never builds a prompt, and never changes a
    chunk's semantic meaning (only its inclusion, and -- to fit a
    character budget -- its length). Identity and status reporting
    must never perform network requests or expensive work, matching
    `SemanticProvider`'s convention
    (`src/core/semantic/semantic_provider.py`).
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return this provider's stable identifier (e.g. "compression")."""
        raise NotImplementedError

    @abstractmethod
    def compress(
        self,
        chunks: list[ContextChunk],
        max_characters: int,
        max_chunks: int,
        deduplicate: bool,
    ) -> CompressionResult:
        """Deduplicate, order, and limit `chunks` into a `CompressionResult`.

        Args:
            chunks: The chunks to compress, in their original order.
                Never mutated.
            max_characters: Maximum total character count the
                compressed chunks' text may occupy.
            max_chunks: Maximum number of chunks the result may contain.
            deduplicate: Whether duplicate chunks/paragraphs should be
                removed before limits are enforced.

        Returns:
            A `CompressionResult` describing the compressed chunks and
            compression statistics.

        Raises:
            CompressionProviderError: If this provider cannot
                currently compress context (e.g. disabled, not
                configured), or if `max_characters`/`max_chunks` is
                not a positive integer.
        """
        raise NotImplementedError

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """Estimate the number of AI-provider tokens `text` would occupy.

        A pure arithmetic heuristic -- never a real tokenizer, never a
        network call, never an AI provider invocation.

        Args:
            text: The text to estimate.

        Returns:
            The estimated token count. Zero for empty text.
        """
        raise NotImplementedError

    # ---------- Lifecycle / diagnostics extension points ----------

    def status(self) -> CompressionProviderStatus:
        """Return this provider's current CompressionProviderStatus.

        Base implementation always reports AVAILABLE. Providers with
        an enabled/configured distinction should override this method.
        """
        return CompressionProviderStatus.AVAILABLE

    def is_available(self) -> bool:
        """Return whether this provider is enabled and fully configured."""
        return self.status() == CompressionProviderStatus.AVAILABLE

    def health(self) -> CompressionProviderHealth:
        """Return a configuration-derived readiness check (no network access, no compression)."""
        if self.is_available():
            return CompressionProviderHealth(
                available=True, message=f"Provider '{self.provider_name()}' is configured."
            )
        return CompressionProviderHealth(
            available=False,
            message=f"Provider '{self.provider_name()}' is not available.",
        )


class DefaultCompressionProvider(CompressionProvider):
    """Built-in context-compression provider: deduplication + limit enforcement only.

    Registered by `CompressionManager` under the name "compression"
    (see 'context_compression.default_provider' in config/config.yaml).
    Performs a deterministic, purely-arithmetic pipeline -- no AI
    reasoning, no summarization, no network access:

        1. (optional) Remove whole chunks that duplicate an earlier
           chunk's normalized text.
        2. (optional) Remove paragraphs, within each remaining chunk,
           that duplicate an earlier paragraph seen anywhere in the
           context so far (across chunks). A chunk that becomes empty
           after this step is dropped entirely.
        3. Drop any chunk beyond `max_chunks`.
        4. Drop, or truncate, trailing chunks so the compressed
           chunks' combined text never exceeds `max_characters`.

    Every step preserves the original relative ordering of surviving
    chunks and their metadata unchanged.
    """

    _NAME: str = "compression"

    def provider_name(self) -> str:
        """Return this provider's stable identifier: "compression"."""
        return self._NAME

    def compress(
        self,
        chunks: list[ContextChunk],
        max_characters: int,
        max_chunks: int,
        deduplicate: bool,
    ) -> CompressionResult:
        """Deduplicate, order, and limit `chunks` into a `CompressionResult`.

        Args:
            chunks: The chunks to compress, in their original order.
                Never mutated.
            max_characters: Maximum total character count the
                compressed chunks' text may occupy. Must be positive.
            max_chunks: Maximum number of chunks the result may
                contain. Must be positive.
            deduplicate: Whether duplicate chunks/paragraphs should be
                removed before limits are enforced.

        Returns:
            A `CompressionResult` describing the compressed chunks and
            compression statistics.

        Raises:
            CompressionProviderError: If `max_characters` or
                `max_chunks` is not a positive integer.
        """
        if max_characters <= 0:
            raise CompressionProviderError("'max_characters' must be a positive integer.")
        if max_chunks <= 0:
            raise CompressionProviderError("'max_chunks' must be a positive integer.")

        original_chunk_count = len(chunks)
        original_character_count = sum(len(chunk.text) for chunk in chunks)

        if deduplicate:
            deduplicated, removed_count = self._deduplicate(chunks)
        else:
            deduplicated, removed_count = list(chunks), 0

        limited, chunk_limited = self._enforce_chunk_limit(deduplicated, max_chunks)
        final_chunks, size_truncated = self._enforce_character_limit(limited, max_characters)

        compressed_text = "\n\n".join(chunk.text for chunk in final_chunks)
        character_count = sum(len(chunk.text) for chunk in final_chunks)

        return CompressionResult(
            chunks=final_chunks,
            original_chunk_count=original_chunk_count,
            chunk_count=len(final_chunks),
            original_character_count=original_character_count,
            character_count=character_count,
            estimated_tokens=self.estimate_tokens(compressed_text),
            deduplicated_chunk_count=removed_count,
            truncated=chunk_limited or size_truncated,
        )

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using a fixed characters-per-token heuristic.

        Args:
            text: The text to estimate.

        Returns:
            `ceil(len(text) / 4)`, i.e. roughly one token per four
            characters (a documented heuristic, not a real tokenizer).
            Zero for empty text.
        """
        if not text:
            return 0
        return -(-len(text) // _CHARACTERS_PER_TOKEN)  # ceiling division

    # ---------- Pipeline steps ----------

    @staticmethod
    def _normalize(text: str) -> str:
        """Collapse internal whitespace and strip ends, for duplicate comparison only.

        Args:
            text: The text to normalize.

        Returns:
            `text` with leading/trailing whitespace removed and every
            internal run of whitespace collapsed to a single space.
            Used only to *detect* duplicates -- the original,
            unnormalized text is always what gets kept and returned.
        """
        return " ".join(text.split())

    @classmethod
    def _deduplicate(cls, chunks: list[ContextChunk]) -> tuple[list[ContextChunk], int]:
        """Remove duplicate whole chunks, then duplicate paragraphs within survivors.

        Args:
            chunks: The chunks to deduplicate, in their original order.

        Returns:
            A tuple of `(surviving_chunks, removed_count)`, where
            `surviving_chunks` preserves the original relative
            ordering and every surviving chunk's original metadata,
            and `removed_count` is the number of whole chunks plus the
            number of duplicate paragraphs removed.
        """
        removed_count = 0
        seen_chunk_texts: set[str] = set()
        seen_paragraphs: set[str] = set()
        survivors: list[ContextChunk] = []

        for chunk in chunks:
            normalized_chunk = cls._normalize(chunk.text)
            if normalized_chunk and normalized_chunk in seen_chunk_texts:
                removed_count += 1
                continue

            deduplicated_text, paragraphs_removed = cls._deduplicate_paragraphs(
                chunk.text, seen_paragraphs
            )
            removed_count += paragraphs_removed

            if not deduplicated_text.strip():
                # Every paragraph in this chunk was a duplicate of
                # something seen earlier: the whole chunk is dropped,
                # but it was already counted paragraph-by-paragraph
                # above, so it is not double-counted here.
                continue

            if normalized_chunk:
                seen_chunk_texts.add(normalized_chunk)

            survivors.append(
                ContextChunk(text=deduplicated_text, index=chunk.index, metadata=chunk.metadata)
            )

        return survivors, removed_count

    @classmethod
    def _deduplicate_paragraphs(cls, text: str, seen_paragraphs: set[str]) -> tuple[str, int]:
        """Remove paragraphs in `text` that duplicate one already recorded in `seen_paragraphs`.

        Args:
            text: A single chunk's text, to be split into paragraphs
                on blank lines.
            seen_paragraphs: Normalized paragraphs already seen
                earlier in the context (across chunks); updated
                in-place with every new, distinct paragraph kept from
                `text`.

        Returns:
            A tuple of `(text_with_duplicates_removed,
            paragraphs_removed_count)`. If `text` contains no blank
            line, it is treated as a single paragraph.
        """
        paragraphs = _PARAGRAPH_SPLIT_PATTERN.split(text.strip())
        kept: list[str] = []
        removed = 0

        for paragraph in paragraphs:
            if not paragraph.strip():
                continue
            normalized = cls._normalize(paragraph)
            if normalized in seen_paragraphs:
                removed += 1
                continue
            seen_paragraphs.add(normalized)
            kept.append(paragraph)

        return "\n\n".join(kept), removed

    @staticmethod
    def _enforce_chunk_limit(
        chunks: list[ContextChunk], max_chunks: int
    ) -> tuple[list[ContextChunk], bool]:
        """Drop every chunk beyond `max_chunks`, preserving ordering.

        Args:
            chunks: The chunks to limit, in their original order.
            max_chunks: Maximum number of chunks to keep.

        Returns:
            A tuple of `(limited_chunks, was_truncated)`.
        """
        if len(chunks) <= max_chunks:
            return chunks, False
        return chunks[:max_chunks], True

    @staticmethod
    def _enforce_character_limit(
        chunks: list[ContextChunk], max_characters: int
    ) -> tuple[list[ContextChunk], bool]:
        """Keep leading chunks (verbatim) up to `max_characters`, truncating the boundary chunk.

        Chunks are considered in order; each is included whole as
        long as the running character total stays within budget. The
        first chunk that would exceed the remaining budget is
        included truncated (its text cut to exactly the remaining
        character budget, from the start, never rewritten) if any
        budget remains, and no further chunks are considered.

        Args:
            chunks: The chunks to limit, in their original order.
            max_characters: Maximum total character count the
                returned chunks' text may occupy.

        Returns:
            A tuple of `(limited_chunks, was_truncated)`.
        """
        limited: list[ContextChunk] = []
        remaining = max_characters
        truncated = False

        for chunk in chunks:
            length = len(chunk.text)
            if length <= remaining:
                limited.append(chunk)
                remaining -= length
                continue

            if remaining > 0:
                limited.append(
                    ContextChunk(
                        text=chunk.text[:remaining], index=chunk.index, metadata=chunk.metadata
                    )
                )
            truncated = True
            break

        return limited, truncated
