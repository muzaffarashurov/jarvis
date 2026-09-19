"""Business logic for EP-095 Energy Visualization & Reporting.

`PersonalDataReportService` is a small, pure, LLM-independent service
implementing EP-095's reporting/export/chart logic on top of
`PersonalDataPoint` values already obtained through
`PersonalDataService.query()` (EP-092). Per the approved EP095_DESIGN.md
Version 1.1 architecture:

    PersonalDataModule -> PersonalDataReportService
    PersonalDataModule -> PersonalDataService -> PersonalDataManager -> PersonalDataProvider

This module never imports `PersonalDataManager`, `PersonalDataProvider`,
`PersonalDataPersistence`, or `PersonalDataRegistry` -- it operates
exclusively on `PersonalDataPoint` values handed to it by
`PersonalDataModule` (which obtains them, unmodified, from
`PersonalDataService.query()`). `CommandResult` is never constructed
here -- that remains exclusively `PersonalDataModule`'s responsibility
(EP095_DESIGN.md §7/§10), mirroring the same layering rule EP-092/093
already established for this namespace.

Units (EP095_DESIGN.md §14): `PersonalDataPoint.unit` is a free-form,
non-empty string with no per-category uniformity guarantee anywhere in
EP-092/093/094. This module never converts units. Arithmetic
(count/sum/avg/min/max) is always computed on raw numeric values; when
more than one distinct unit is observed in a queried range or a single
bucket, the affected `units` tuple simply contains more than one
entry, and formatting/display code labels it "mixed" -- deterministic,
never a silently chosen or fabricated unit.

Bucketing/timezone (EP095_DESIGN.md §15): all timestamps in this
repository are already timezone-aware UTC; this module introduces no
new timezone infrastructure. A defensively-encountered naive timestamp
is treated as UTC. Weeks are ISO weeks (Monday start, via
`date.isocalendar()`); months are grouped by `(year, month)`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from src.core.personal_data.personal_data_record import PersonalDataPoint

VALID_BUCKETS: tuple[str, ...] = ("day", "week", "month")
VALID_EXPORT_MODES: tuple[str, ...] = ("raw", "report")

_RAW_CSV_HEADER: tuple[str, ...] = (
    "id",
    "source_id",
    "category",
    "timestamp",
    "value",
    "unit",
    "collected_at",
)
_REPORT_CSV_HEADER: tuple[str, ...] = (
    "category",
    "bucket_start",
    "bucket_end",
    "count",
    "sum",
    "avg",
    "min",
    "max",
    "unit",
)


class PersonalDataReportError(Exception):
    """Raised for an unrecoverable EP-095 reporting/export operation.

    Raised only for a failure that prevents any progress (e.g. the
    export directory does not exist, or the destination cannot be
    opened for writing) -- mirroring
    `ElectricityMeterReadingError`'s/`GasMeterReadingError`'s existing
    role for EP-093's CSV import (EP095_DESIGN.md §10). Never raised
    for a "no data" outcome, which is a normal, successful result
    (EP095_DESIGN.md §7).
    """


@dataclass(frozen=True)
class OverallSummary:
    """The overall count/sum/avg/min/max for an entire queried range.

    Attributes:
        count: Number of points summarized.
        sum: Sum of `value` across every point, unconverted.
        avg: Arithmetic mean of `value`.
        min: Minimum `value`.
        max: Maximum `value`.
        units: The distinct `unit` strings observed, sorted. A single
            entry means every point shared one unit; more than one
            entry means the range is "mixed" (EP095_DESIGN.md §14) --
            never converted, never collapsed to one.
    """

    count: int
    sum: float
    avg: float
    min: float
    max: float
    units: tuple[str, ...]

    @property
    def is_mixed_unit(self) -> bool:
        """Return whether this summary spans more than one distinct unit."""
        return len(self.units) > 1

    @property
    def csv_unit(self) -> str:
        """Return the single unit, or the literal string "mixed" (EP095_DESIGN.md §13)."""
        return self.units[0] if len(self.units) == 1 else "mixed"


@dataclass(frozen=True)
class BucketSummary:
    """One day/week/month bucket's aggregated values.

    Attributes:
        bucket_start: The bucket's inclusive start instant (UTC).
        bucket_end: The bucket's exclusive end instant (UTC).
        count: Number of points in this bucket.
        sum: Sum of `value` across the bucket's points, unconverted.
        avg: Arithmetic mean of `value` within the bucket.
        min: Minimum `value` within the bucket.
        max: Maximum `value` within the bucket.
        units: The distinct `unit` strings observed in this bucket,
            sorted (see `OverallSummary.units`).
    """

    bucket_start: datetime
    bucket_end: datetime
    count: int
    sum: float
    avg: float
    min: float
    max: float
    units: tuple[str, ...]

    @property
    def is_mixed_unit(self) -> bool:
        """Return whether this bucket spans more than one distinct unit."""
        return len(self.units) > 1

    @property
    def csv_unit(self) -> str:
        """Return the single unit, or the literal string "mixed" (EP095_DESIGN.md §13)."""
        return self.units[0] if len(self.units) == 1 else "mixed"


# ---------- Timezone/bucket-boundary helpers (EP095_DESIGN.md §15) ----------


def _ensure_utc(value: datetime) -> datetime:
    """Return `value` as a timezone-aware UTC datetime.

    Defensive normalization only -- every timestamp this module
    actually receives is already UTC-aware per EP-092/093/094's own
    conventions (`utc_now()`, `_parse_optional_datetime()`). No new
    timezone system is introduced.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _day_bucket_start(timestamp: datetime) -> datetime:
    ts = _ensure_utc(timestamp)
    return datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)


def _day_bucket_end(bucket_start: datetime) -> datetime:
    return bucket_start + timedelta(days=1)


def _week_bucket_start(timestamp: datetime) -> datetime:
    """Return the Monday-start ISO week containing `timestamp` (EP095_DESIGN.md §15)."""
    ts = _ensure_utc(timestamp)
    iso_weekday = ts.isocalendar()[2]  # 1 (Monday) .. 7 (Sunday)
    day_start = datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)
    return day_start - timedelta(days=iso_weekday - 1)


def _week_bucket_end(bucket_start: datetime) -> datetime:
    return bucket_start + timedelta(days=7)


def _month_bucket_start(timestamp: datetime) -> datetime:
    ts = _ensure_utc(timestamp)
    return datetime(ts.year, ts.month, 1, tzinfo=timezone.utc)


def _month_bucket_end(bucket_start: datetime) -> datetime:
    if bucket_start.month == 12:
        return bucket_start.replace(year=bucket_start.year + 1, month=1)
    return bucket_start.replace(month=bucket_start.month + 1)


_BUCKET_FUNCTIONS: dict[str, tuple] = {
    "day": (_day_bucket_start, _day_bucket_end),
    "week": (_week_bucket_start, _week_bucket_end),
    "month": (_month_bucket_start, _month_bucket_end),
}


# ---------- Aggregation ----------


def aggregate(
    points: Sequence[PersonalDataPoint], bucket: str
) -> tuple[OverallSummary | None, list[BucketSummary]]:
    """Aggregate `points` into an overall summary and chronological buckets.

    Args:
        points: The points to aggregate (typically the unmodified
            result of `PersonalDataService.query()`).
        bucket: One of `VALID_BUCKETS` ("day", "week", "month"),
            case-insensitive.

    Returns:
        `(overall, buckets)` -- `overall` is `None` and `buckets` is
        empty if `points` is empty (a normal, non-error outcome; the
        caller is responsible for the "(empty)" `CommandResult`
        convention, EP095_DESIGN.md §7). `buckets` is always sorted by
        `bucket_start` ascending.

    Raises:
        ValueError: If `bucket` (lowercased) is not one of
            `VALID_BUCKETS`.
    """
    normalized_bucket = bucket.lower()
    if normalized_bucket not in VALID_BUCKETS:
        raise ValueError(f"bucket must be one of: {', '.join(VALID_BUCKETS)}.")

    if not points:
        return None, []

    values = [point.value for point in points]
    overall_units = tuple(sorted({point.unit for point in points}))
    overall = OverallSummary(
        count=len(points),
        sum=sum(values),
        avg=sum(values) / len(values),
        min=min(values),
        max=max(values),
        units=overall_units,
    )

    start_fn, end_fn = _BUCKET_FUNCTIONS[normalized_bucket]
    grouped: dict[datetime, list[PersonalDataPoint]] = {}
    for point in points:
        key = start_fn(point.timestamp)
        grouped.setdefault(key, []).append(point)

    buckets: list[BucketSummary] = []
    for bucket_start in sorted(grouped):
        group = grouped[bucket_start]
        group_values = [point.value for point in group]
        group_units = tuple(sorted({point.unit for point in group}))
        buckets.append(
            BucketSummary(
                bucket_start=bucket_start,
                bucket_end=end_fn(bucket_start),
                count=len(group),
                sum=sum(group_values),
                avg=sum(group_values) / len(group_values),
                min=min(group_values),
                max=max(group_values),
                units=group_units,
            )
        )

    return overall, buckets


# ---------- Text formatting (report/chart) ----------


def _unit_suffix(units: tuple[str, ...]) -> str:
    """Return a display suffix for a unit tuple: the unit itself, or "(mixed: ...)"."""
    if len(units) == 1:
        return units[0]
    return f"(mixed: {', '.join(units)})"


def render_report_text(
    category: str,
    start: datetime | None,
    end: datetime | None,
    overall: OverallSummary | None,
    buckets: Sequence[BucketSummary],
) -> str:
    """Render `report`'s full console output (EP095_DESIGN.md §7).

    Args:
        category: The queried category.
        start: The queried range's start bound, or `None` if unbounded.
        end: The queried range's end bound, or `None` if unbounded.
        overall: The overall summary, or `None` if there is no data
            (callers normally short-circuit to the "(empty)" message
            before reaching this function in that case).
        buckets: The chronologically-ordered bucket breakdown.

    Returns:
        The complete, multi-line report text.
    """
    start_label = start.isoformat() if start is not None else "-"
    end_label = end.isoformat() if end is not None else "-"
    lines = [f"personal_data report: {category} [{start_label}..{end_label}]"]

    if overall is None:
        lines.append("(empty)")
        return "\n".join(lines)

    lines.append(
        f"Count: {overall.count}  Sum: {overall.sum} {_unit_suffix(overall.units)}  "
        f"Avg: {overall.avg}  Min: {overall.min}  Max: {overall.max}"
    )
    for bucket in buckets:
        lines.append(
            f"{bucket.bucket_start.isoformat()} .. {bucket.bucket_end.isoformat()}: "
            f"count={bucket.count} sum={bucket.sum} avg={bucket.avg} "
            f"min={bucket.min} max={bucket.max} unit={_unit_suffix(bucket.units)}"
        )
    return "\n".join(lines)


def render_ascii_chart(buckets: Sequence[BucketSummary], max_width: int = 40) -> str:
    """Render a dependency-free ASCII bar chart of `buckets` (EP095_DESIGN.md §7/§20).

    Bar length is proportional to each bucket's `sum` (by absolute
    value, so a negative-sum category such as net metering still
    renders a visible, non-negative-width bar), scaled so the largest
    bucket in `buckets` renders at `max_width` characters.

    Args:
        buckets: The chronologically-ordered bucket breakdown.
        max_width: The maximum bar width, in characters.

    Returns:
        The complete, multi-line chart text, or the literal string
        `"(empty)"` if `buckets` is empty.
    """
    if not buckets:
        return "(empty)"

    max_abs_sum = max(abs(bucket.sum) for bucket in buckets)
    lines: list[str] = []
    for bucket in buckets:
        if max_abs_sum > 0 and bucket.sum != 0:
            bar_length = max(1, round((abs(bucket.sum) / max_abs_sum) * max_width))
        else:
            bar_length = 0
        bar = "#" * bar_length
        label = bucket.bucket_start.date().isoformat()
        lines.append(f"{label} | {bar} {bucket.sum} {_unit_suffix(bucket.units)}")
    return "\n".join(lines)


# ---------- CSV export (EP095_DESIGN.md §13) ----------


def _open_for_write(path: str | Path):
    """Open `path` for CSV writing, raising `PersonalDataReportError` on failure.

    Never auto-creates a missing parent directory (EP095_DESIGN.md
    §7); an existing target file is overwritten unconditionally.
    """
    csv_path = Path(path)
    if not csv_path.parent.exists():
        raise PersonalDataReportError(f"Cannot write to '{csv_path}': directory does not exist.")
    try:
        return csv_path.open("w", encoding="utf-8", newline="")
    except OSError as exc:
        raise PersonalDataReportError(f"Cannot write to '{csv_path}': {exc}") from exc


def write_raw_csv(points: Sequence[PersonalDataPoint], path: str | Path) -> int:
    """Write `points` to `path` as a raw-export CSV (EP095_DESIGN.md §13).

    `raw` is deliberately never exported (see the module docstring's
    reference to `PersonalDataPoint`'s own "never log `raw` in full at
    INFO level" rule). The header row is always written, including for
    zero points.

    Args:
        points: The points to export, in the order given.
        path: The destination CSV path.

    Returns:
        The number of data rows written (excludes the header).

    Raises:
        PersonalDataReportError: If `path`'s parent directory does not
            exist, or the file cannot be opened/written.
    """
    file = _open_for_write(path)
    with file:
        writer = csv.writer(file)
        writer.writerow(_RAW_CSV_HEADER)
        for point in points:
            writer.writerow(
                [
                    point.id,
                    point.source_id,
                    point.category,
                    point.timestamp.isoformat(),
                    point.value,
                    point.unit,
                    point.collected_at.isoformat(),
                ]
            )
    return len(points)


def write_report_csv(category: str, buckets: Sequence[BucketSummary], path: str | Path) -> int:
    """Write `buckets` to `path` as a report-export CSV (EP095_DESIGN.md §13).

    The header row is always written, including for zero buckets.

    Args:
        category: The queried category (written on every row).
        buckets: The chronologically-ordered bucket breakdown.
        path: The destination CSV path.

    Returns:
        The number of data rows written (excludes the header).

    Raises:
        PersonalDataReportError: If `path`'s parent directory does not
            exist, or the file cannot be opened/written.
    """
    file = _open_for_write(path)
    with file:
        writer = csv.writer(file)
        writer.writerow(_REPORT_CSV_HEADER)
        for bucket in buckets:
            writer.writerow(
                [
                    category,
                    bucket.bucket_start.isoformat(),
                    bucket.bucket_end.isoformat(),
                    bucket.count,
                    bucket.sum,
                    bucket.avg,
                    bucket.min,
                    bucket.max,
                    bucket.csv_unit,
                ]
            )
    return len(buckets)
