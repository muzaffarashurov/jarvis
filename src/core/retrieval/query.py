"""Query domain model for the EP-020 Semantic Retrieval Engine.

Represents one search request against a `ProjectIndex` (EP-019): the
original text as given by the caller, its normalized form, and any
search options. Carries no scoring or retrieval logic of its own --
see `ranking.py`/`retrieval_engine.py` for that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Query", "normalize_query"]

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_query(text: str) -> str:
    """Normalize `text` for matching: lowercase, trim, collapse whitespace.

    Args:
        text: Raw query text.

    Returns:
        The normalized text: lowercased, leading/trailing whitespace
        stripped, and every run of internal whitespace collapsed to a
        single space.
    """
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


@dataclass(frozen=True)
class Query:
    """One search request.

    Attributes:
        original: The query text exactly as provided by the caller.
        normalized: `original` (with surrounding quotes stripped, if
            `exact_phrase` is True), normalized -- see
            `normalize_query`.
        terms: `normalized` split into individual whitespace-separated
            terms, in order, with duplicates preserved. Empty for an
            empty/whitespace-only query.
        exact_phrase: Whether `original` was wrapped in double quotes
            (e.g. '"exact phrase"'), requesting a strict, contiguous
            phrase match rather than plain keyword overlap.
        options: Arbitrary extra search options, reserved for future
            use (e.g. filters). Never mutated or inspected by
            `RankingEngine`/`RetrievalEngine` today.
    """

    original: str
    normalized: str
    terms: tuple[str, ...]
    exact_phrase: bool = False
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_text(cls, text: str, options: dict[str, Any] | None = None) -> Query:
        """Build a Query from raw input text.

        A query wrapped in double quotes (e.g. '"exact phrase"') is
        treated as an exact-phrase request: `exact_phrase` is True and
        the quotes are stripped before normalization.

        Args:
            text: Raw query text, as typed/passed by the caller.
            options: Arbitrary extra search options. Defaults to an
                empty dict.

        Returns:
            A new Query with `normalized`/`terms`/`exact_phrase`
            derived from `text`.
        """
        stripped = text.strip()
        exact_phrase = len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"')
        body = stripped[1:-1] if exact_phrase else stripped
        normalized = normalize_query(body)
        terms = tuple(normalized.split(" ")) if normalized else ()
        return cls(
            original=text,
            normalized=normalized,
            terms=terms,
            exact_phrase=exact_phrase,
            options=dict(options) if options else {},
        )

    @property
    def is_empty(self) -> bool:
        """Return True if this query has no searchable terms."""
        return len(self.terms) == 0
