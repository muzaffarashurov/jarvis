"""Domain model for EP-024 Knowledge Base.

Defines the plain data type shared by `KnowledgeCollection` (storage)
and `KnowledgeService` (business logic): a single structured knowledge
record (`KnowledgeRecord`). This module owns no storage and no
business logic -- it mirrors the role of `src/core/memory/context.py`
relative to `MemoryStore`/`MemoryEntry`.

Knowledge Base performs no reasoning. This module has no dependency on
any LLM, embedding, retrieval, RAG, or memory component.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

DEFAULT_COLLECTION: str = "default"


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Returns:
        The current UTC datetime.
    """
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime:
    """Parse an ISO-8601 string (or pass through a datetime) into a datetime.

    Args:
        value: An ISO-8601 timestamp string or an existing datetime.

    Returns:
        The parsed datetime.

    Raises:
        ValueError: If `value` is a string that is not valid ISO-8601.
        TypeError: If `value` is not a string or datetime.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Expected a datetime or ISO-8601 string, got {type(value).__name__}.")


@dataclass
class KnowledgeRecord:
    """A single structured knowledge record stored within a collection.

    Attributes:
        key: The record's key, unique within its collection.
        content: The stored knowledge payload. Should be
            JSON-serializable so records remain exportable/inspectable.
        collection: The named collection this record belongs to.
        metadata: Arbitrary caller-supplied metadata describing the
            record (e.g. source, tags, author).
        created_at: When the record was first created.
        updated_at: When the record's content was last written.
    """

    key: str
    content: Any
    collection: str = DEFAULT_COLLECTION
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this record to a plain, JSON-ready dictionary.

        Returns:
            A dictionary representation suitable for `json.dump`.
        """
        return {
            "key": self.key,
            "content": self.content,
            "collection": self.collection,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KnowledgeRecord":
        """Reconstruct a KnowledgeRecord from a dictionary produced by `to_dict`.

        Args:
            data: A dictionary as produced by `to_dict`.

        Returns:
            The reconstructed KnowledgeRecord.

        Raises:
            KeyError: If a required field is missing.
            TypeError: If a field has an unexpected type.
            ValueError: If a timestamp field is not valid ISO-8601.
        """
        return cls(
            key=str(data["key"]),
            content=data["content"],
            collection=str(data.get("collection", DEFAULT_COLLECTION)),
            metadata=dict(data.get("metadata") or {}),
            created_at=_parse_timestamp(data.get("created_at") or utc_now()),
            updated_at=_parse_timestamp(data.get("updated_at") or utc_now()),
        )
