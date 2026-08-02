"""Domain model for EP-026 Semantic Search.

Defines the plain data types shared by `SemanticProvider` (scoring),
`SemanticEngine` (pipeline orchestration) and `SemanticService`
(CLI-facing layer): a single searchable candidate (`SemanticCandidate`)
and a single ranked match (`SemanticResult`). This module owns no
storage, no embedding logic and no similarity calculation -- it
mirrors the role of `src/core/knowledge/knowledge_record.py` relative
to `KnowledgeCollection` and `src/core/long_term_memory/long_term_record.py`
relative to the Long-Term Memory providers.

Semantic Search performs no reasoning. This module has no dependency
on any LLM, RAG, prompt, agent, or reflection component.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SOURCE_KNOWLEDGE: str = "knowledge"
SOURCE_LONG_TERM_MEMORY: str = "long_term_memory"

__all__ = [
    "SOURCE_KNOWLEDGE",
    "SOURCE_LONG_TERM_MEMORY",
    "SemanticCandidate",
    "SemanticResult",
]


@dataclass(frozen=True)
class SemanticCandidate:
    """A single record made searchable for one `SemanticEngine.search()` call.

    Built by `SemanticEngine` from Knowledge Base (EP-024) and
    Long-Term Memory (EP-025) records, after their text representation
    has already been embedded by the Embedding Engine (EP-021).
    `SemanticProvider` implementations consume this type -- they never
    read `KnowledgeRecord`/`LongTermRecord` or call the Embedding
    Engine themselves.

    Attributes:
        source: Which subsystem this candidate came from -- either
            `SOURCE_KNOWLEDGE` or `SOURCE_LONG_TERM_MEMORY`.
        identifier: The record's identifier in its owning subsystem
            (a Knowledge Base key, or a Long-Term Memory id).
        text: The text representation of the record that was embedded.
        vector: The embedding vector for `text`, produced by the
            Embedding Engine. Same dimension as the query vector.
        metadata: The record's own metadata, carried through unchanged.
    """

    source: str
    identifier: str
    text: str
    vector: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticResult:
    """A single ranked match returned by a `SemanticEngine.search()` call.

    Attributes:
        source: Which subsystem this match came from -- either
            `SOURCE_KNOWLEDGE` or `SOURCE_LONG_TERM_MEMORY`.
        identifier: The matched record's identifier in its owning
            subsystem.
        text: The text representation of the matched record.
        score: The similarity score assigned by the active
            `SemanticProvider`, in the range [-1.0, 1.0] for cosine
            similarity (never generated, only calculated).
        metadata: The matched record's own metadata, carried through
            unchanged.
    """

    source: str
    identifier: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
