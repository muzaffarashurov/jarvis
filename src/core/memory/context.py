"""Domain model for EP-013 Memory & Context Manager.

Defines the plain data types shared by MemoryStore (storage) and
MemoryService (business logic): a single stored key/value record
(`MemoryEntry`) plus the small helpers used to build and (de)serialize
it. This module owns no storage and no business logic -- it mirrors
the role of `src/core/scheduler/job.py` and `src/core/processes/process.py`
relative to their respective registries.

The Memory Manager has no dependency on any LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

DEFAULT_NAMESPACE: str = "default"


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
        ValueError: If `value` is neither a datetime nor a valid
            ISO-8601 string.
        TypeError: If `value` is not a string or datetime.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(f"Expected a datetime or ISO-8601 string, got {type(value).__name__}.")


@dataclass
class MemoryEntry:
    """A single namespaced key/value record with metadata and lifecycle info.

    Attributes:
        key: The entry's key, unique within its namespace.
        value: The stored value. Must be JSON-serializable to support
            export/import.
        namespace: Logical grouping the entry belongs to (e.g. "cli",
            "telegram", "workflow:invoice_run").
        persistent: Whether the entry represents persistent memory
            (included in `export`) as opposed to session memory
            (in-process only, excluded from `export`).
        metadata: Arbitrary caller-supplied metadata about the entry.
        created_at: When the entry was first created.
        updated_at: When the entry's value was last written.
        expires_at: Optional TTL expiry. None means the entry never
            expires on its own.
    """

    key: str
    value: Any
    namespace: str = DEFAULT_NAMESPACE
    persistent: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None

    def is_expired(self, at: datetime | None = None) -> bool:
        """Return whether this entry's TTL has elapsed.

        Args:
            at: The time to check against. Defaults to now (UTC).

        Returns:
            True if `expires_at` is set and is at or before `at`.
        """
        if self.expires_at is None:
            return False
        return (at or utc_now()) >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        """Serialize this entry to a plain, JSON-ready dictionary.

        Returns:
            A dictionary representation suitable for `json.dump`.
        """
        return {
            "key": self.key,
            "value": self.value,
            "namespace": self.namespace,
            "persistent": self.persistent,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemoryEntry":
        """Reconstruct a MemoryEntry from a dictionary produced by `to_dict`.

        Args:
            data: A dictionary as produced by `to_dict` (e.g. loaded
                from an export JSON file).

        Returns:
            The reconstructed MemoryEntry.

        Raises:
            KeyError: If a required field is missing.
            TypeError: If a field has an unexpected type.
            ValueError: If a timestamp field is not valid ISO-8601.
        """
        expires_at_raw = data.get("expires_at")
        return cls(
            key=str(data["key"]),
            value=data["value"],
            namespace=str(data.get("namespace", DEFAULT_NAMESPACE)),
            persistent=bool(data.get("persistent", False)),
            metadata=dict(data.get("metadata") or {}),
            created_at=_parse_timestamp(data.get("created_at") or utc_now()),
            updated_at=_parse_timestamp(data.get("updated_at") or utc_now()),
            expires_at=_parse_timestamp(expires_at_raw) if expires_at_raw else None,
        )
