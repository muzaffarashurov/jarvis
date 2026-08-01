"""Domain model for EP-025 Long-Term Memory.

Defines the plain data type shared by every `LongTermProvider`
implementation and `LongTermMemoryService`/`LongTermMemoryManager`: a
single long-lived memory (`LongTermRecord`). This module owns no
storage and no business logic -- it mirrors the role of
`src/core/knowledge/knowledge_record.py` relative to
`KnowledgeCollection`, and `src/core/memory/context.py` relative to
`MemoryStore`.

Long-Term Memory performs no reasoning, ranking, similarity search, or
embeddings. This module has no dependency on any LLM, embedding,
retrieval, RAG, semantic search, or context compression component.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

STATUS_ACTIVE: str = "active"
STATUS_ARCHIVED: str = "archived"


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime.

    Returns:
        The current UTC datetime.
    """
    return datetime.now(timezone.utc)


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an ISO-8601 string (or pass through a datetime) into a datetime.

    Args:
        value: An ISO-8601 timestamp string, an existing datetime, or None.

    Returns:
        The parsed datetime, or None if `value` is None.

    Raises:
        ValueError: If `value` is a string that is not valid ISO-8601.
        TypeError: If `value` is not a string, datetime, or None.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Expected a datetime, ISO-8601 string, or None, got {type(value).__name__}.")


@dataclass
class LongTermRecord:
    """A single long-lived memory managed by the Long-Term Memory subsystem.

    Attributes:
        id: The record's unique identifier.
        content: The stored memory payload. Should be JSON-serializable.
        metadata: Arbitrary caller-supplied metadata describing the
            record (e.g. source, tags, importance).
        status: Either STATUS_ACTIVE or STATUS_ARCHIVED.
        created_at: When the record was first created.
        updated_at: When the record's content was last written.
        archived_at: When the record was archived, or None if it has
            never been archived.
    """

    id: str
    content: Any
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = STATUS_ACTIVE
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    archived_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this record to a plain, JSON-ready dictionary.

        Returns:
            A dictionary representation suitable for `json.dump`.
        """
        return {
            "id": self.id,
            "content": self.content,
            "metadata": self.metadata,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongTermRecord":
        """Reconstruct a LongTermRecord from a dictionary produced by `to_dict`.

        Args:
            data: A dictionary as produced by `to_dict`.

        Returns:
            The reconstructed LongTermRecord.

        Raises:
            KeyError: If a required field is missing.
            TypeError: If a field has an unexpected type.
            ValueError: If a timestamp field is not valid ISO-8601.
        """
        created_at = _parse_timestamp(data.get("created_at") or utc_now())
        updated_at = _parse_timestamp(data.get("updated_at") or utc_now())
        return cls(
            id=str(data["id"]),
            content=data["content"],
            metadata=dict(data.get("metadata") or {}),
            status=str(data.get("status", STATUS_ACTIVE)),
            created_at=created_at if created_at is not None else utc_now(),
            updated_at=updated_at if updated_at is not None else utc_now(),
            archived_at=_parse_timestamp(data.get("archived_at")),
        )
