"""Domain model for EP-092 Personal Data Collection Framework.

Defines the one owned data shape every `PersonalDataSource`
implementation produces and every `PersonalDataProvider` persists:
`PersonalDataPoint`. This module owns no storage and no business
logic -- it mirrors the role of
`src/core/long_term_memory/long_term_record.py` relative to
`LongTermProvider`, and `src/core/knowledge/knowledge_record.py`
relative to `KnowledgeCollection`.

Personal Data Collection performs no reasoning, ranking, similarity
search, embeddings, forecasting, or visualization. This module has no
dependency on any LLM, Embedding, Retrieval, RAG, Semantic Search, or
Context Compression component.

`timestamp` and `collected_at` are distinct and never conflated:

    timestamp
        The point in time the *measurement itself* refers to (e.g.
        "the meter reading for 10:00"). Part of the point's logical
        identity: the dedup key used throughout EP-092 is
        `(source_id, category, timestamp)` (see
        `personal_data_provider.py` / `personal_data_manager.py`).

    collected_at
        The point in time Jarvis *received/ingested* the point (e.g.
        "Jarvis polled the source at 10:02 and got the 10:00
        reading"). Pure ingestion metadata -- it MUST NOT participate
        in the dedup key.

Example: a source reports a meter reading for 10:00, but Jarvis
receives it at 10:02 -> `timestamp = 10:00`, `collected_at = 10:02`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


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
        TypeError: If `value` is not a string or datetime (or is None).
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(
        f"Expected a datetime or ISO-8601 string for a PersonalDataPoint timestamp, "
        f"got {type(value).__name__}."
    )


def _parse_value(value: Any) -> float:
    """Validate and coerce a measurement value to `float`.

    `PersonalDataPoint.value` is strongly typed as `float` -- not a
    union of `int | float | str | bool | Any` -- per EP-092's STEP 1
    design (§12/§13/§15): the framework is for measurements, so the
    contract stays strongly typed. `bool` is explicitly rejected even
    though `bool` is a subclass of `int` in Python, since a boolean is
    never a sensible measurement value.

    Args:
        value: The raw value to validate.

    Returns:
        `value` coerced to `float`.

    Raises:
        TypeError: If `value` is a `bool`, or is not an `int`/`float`.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"PersonalDataPoint.value must be a float (or int), got {type(value).__name__}."
        )
    return float(value)


@dataclass(frozen=True)
class PersonalDataPoint:
    """A single collected, externally-observed personal-data measurement.

    Attributes:
        id: The point's unique identifier.
        source_id: The `PersonalDataSource.source_id` that produced
            this point.
        category: The measurement category (e.g. "electricity_
            consumption"). EP-092 assigns no meaning to specific
            category strings -- that is left entirely to EP-093/094/
            097.
        timestamp: When the measurement itself occurred. Part of the
            dedup key `(source_id, category, timestamp)` (see the
            module docstring).
        value: The measurement value. Strongly typed as `float`.
        unit: The measurement's unit (e.g. "kWh"), as a plain string.
            EP-092 performs no unit conversion or validation beyond
            requiring a non-empty string.
        raw: The source's original, unprocessed payload for this
            point. Must never be logged in full at `INFO` level (only
            `DEBUG`), since it may contain provider-specific
            identifiers.
        collected_at: When Jarvis ingested this point. Ingestion
            metadata only -- excluded from the dedup key (see the
            module docstring).
    """

    id: str
    source_id: str
    category: str
    timestamp: datetime
    value: float
    unit: str
    raw: dict[str, Any] = field(default_factory=dict)
    collected_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        """Validate and normalize field types.

        Raises:
            ValueError: If `id`, `source_id`, `category`, or `unit` is
                empty, or if a timestamp string is not valid ISO-8601.
            TypeError: If `value` is not a `float`/`int` (or is a
                `bool`), or if `timestamp`/`collected_at` is not a
                `datetime` or ISO-8601 string.
        """
        if not self.id:
            raise ValueError("PersonalDataPoint.id must not be empty.")
        if not self.source_id:
            raise ValueError("PersonalDataPoint.source_id must not be empty.")
        if not self.category:
            raise ValueError("PersonalDataPoint.category must not be empty.")
        if not self.unit:
            raise ValueError("PersonalDataPoint.unit must not be empty.")

        # dataclass(frozen=True) requires object.__setattr__ for normalization.
        object.__setattr__(self, "timestamp", _parse_timestamp(self.timestamp))
        object.__setattr__(self, "collected_at", _parse_timestamp(self.collected_at))
        object.__setattr__(self, "value", _parse_value(self.value))

    def dedup_key(self) -> tuple[str, str, datetime]:
        """Return this point's logical identity/dedup key.

        Returns:
            `(source_id, category, timestamp)` -- never includes
            `collected_at` (see the module docstring).
        """
        return (self.source_id, self.category, self.timestamp)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this point to a plain, JSON-ready dictionary.

        Returns:
            A dictionary representation suitable for `json.dumps`
            (e.g. for a `PersonalDataPersistence` JSONL line).
        """
        return {
            "id": self.id,
            "source_id": self.source_id,
            "category": self.category,
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "unit": self.unit,
            "raw": self.raw,
            "collected_at": self.collected_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PersonalDataPoint":
        """Reconstruct a PersonalDataPoint from a dictionary produced by `to_dict`.

        Args:
            data: A dictionary as produced by `to_dict`.

        Returns:
            The reconstructed PersonalDataPoint.

        Raises:
            KeyError: If a required field is missing.
            TypeError: If a field has an unexpected type.
            ValueError: If a timestamp field is not valid ISO-8601, or
                a required string field is empty.
        """
        return cls(
            id=str(data["id"]),
            source_id=str(data["source_id"]),
            category=str(data["category"]),
            timestamp=data["timestamp"],
            value=data["value"],
            unit=str(data["unit"]),
            raw=dict(data.get("raw") or {}),
            collected_at=data.get("collected_at") or utc_now(),
        )
