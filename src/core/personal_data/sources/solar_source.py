"""Solar generation PersonalDataSource for EP-094.

Mirrors `electricity_source.py`/`gas_source.py` exactly, for the
`solar_generation` category. See `electricity_source.py`'s module
docstring for the full architectural rationale (EP093_DESIGN.md §6.2's
Design A, §6.4's V1 scope, §11's layering rule -- reused unmodified by
EP-094, per EP094_DESIGN.md §5/§6) -- not repeated here to avoid drift
between three copies of the same explanation; this module's *behavior*
is independently complete and does not import anything from
`electricity_source.py`/`gas_source.py`.

Value validation includes the finite-value check
(EP093_DESIGN.md's own EP093-AUDIT-001 lesson, applied here from the
start rather than discovered again, per EP094_DESIGN.md §7/§12).
"""

from __future__ import annotations

import csv as csv_module
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

from loguru import logger

from src.core.personal_data.personal_data_record import PersonalDataPoint
from src.core.personal_data.personal_data_source import PersonalDataSource

CATEGORY: str = "solar_generation"
SOURCE_ID: str = "solar_local_entry"
DEFAULT_LOG_PATH: Path = Path("data/database/personal_data_solar") / f"{CATEGORY}.jsonl"

_REQUIRED_CSV_COLUMNS = ("date", "value", "unit")


class SolarMeterReadingError(Exception):
    """Raised for an unrecoverable solar-reading operation (EP-094).

    Raised only for a failure that prevents *any* progress (e.g. the
    CSV file does not exist at all) -- a per-row problem within an
    otherwise readable file is reported via logging and a skip, not
    this exception (EP093_DESIGN.md §6.4's "invalid-row handling"
    rule, reused unmodified).
    """


def _parse_value(raw: str) -> float:
    """Parse a CSV/CLI `value` field into a finite float.

    Raises:
        ValueError: If `raw` is not a valid decimal number, or is
            non-finite (`NaN`/`Infinity`/`-Infinity` -- `float()`
            itself accepts these spellings, but a non-finite reading
            is never a valid solar-generation measurement, per
            EP093-AUDIT-001's already-established lesson, applied here
            from the start).
    """
    try:
        parsed = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"value must be a decimal number, got {raw!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"value must be a finite number, got {raw!r}")
    return parsed


def _parse_timestamp(raw: str | None) -> datetime:
    """Parse a CSV/CLI `date`/`timestamp` field into a timezone-aware UTC datetime.

    A bare date (e.g. "2026-01-01") is treated as midnight UTC on that
    date, per EP093_DESIGN.md §6.4. An empty/None value means "now."

    Raises:
        ValueError: If `raw` is neither empty nor a valid ISO-8601
            date or datetime.
    """
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.combine(date.fromisoformat(raw), datetime.min.time(), tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(f"date/timestamp must be ISO-8601, got {raw!r}") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _make_id(source_id: str, timestamp: datetime) -> str:
    """Build a stable, human-readable id for a reading.

    Dedup itself is entirely EP-092's, keyed on
    `(source_id, category, timestamp)` -- this id is for readability/
    debugging only, not a second identity mechanism.
    """
    return f"{source_id}:{timestamp.isoformat()}"


def _build_point(
    value: str, unit: str, timestamp_raw: str | None, meter_id: str | None = None
) -> PersonalDataPoint:
    """Validate raw fields and construct one solar-generation `PersonalDataPoint`.

    Raises:
        ValueError: If `value` is not numeric/finite, `unit` is
            empty, or `timestamp_raw` is not empty/valid ISO-8601
            (EP093_DESIGN.md §6.4's "validation" rule, reused
            unmodified).
    """
    parsed_value = _parse_value(value)
    if not unit or not unit.strip():
        raise ValueError("unit must not be empty")
    timestamp = _parse_timestamp(timestamp_raw)
    source_id = f"{SOURCE_ID}:{meter_id}" if meter_id else SOURCE_ID
    raw: dict[str, object] = {}
    if meter_id:
        raw["meter_id"] = meter_id
    return PersonalDataPoint(
        id=_make_id(source_id, timestamp),
        source_id=source_id,
        category=CATEGORY,
        timestamp=timestamp,
        value=parsed_value,
        unit=unit.strip(),
        raw=raw,
    )


def _append_to_log(point: PersonalDataPoint, log_path: Path) -> None:
    """Append `point` to `log_path` as one JSONL line (EP-094's own log, not EP-092's)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(point.to_dict()))
        file.write("\n")


def append_solar_reading(
    value: str,
    unit: str,
    timestamp: str | None = None,
    log_path: Path | None = None,
) -> PersonalDataPoint:
    """Validate and append one manually-entered solar-generation reading.

    Used by the `personal_data record-reading` CLI action. This is a
    plain module-level function (not a method on `SolarCsvSource`) so
    `personal_data_module.py` can call it without importing the
    `PersonalDataSource` subclass itself, per EP093_DESIGN.md §11's
    layering rule ("may NOT import ... any concrete PersonalDataSource
    subclass directly").

    Args:
        value: The reading's value, as a string (e.g. from CLI args).
        unit: The reading's unit (e.g. "kWh").
        timestamp: Optional ISO-8601 date/datetime; "now" if omitted.
        log_path: Where to append the reading. Defaults to
            `DEFAULT_LOG_PATH`.

    Returns:
        The constructed, now-persisted-to-the-local-log
        `PersonalDataPoint`. Note this is EP-094's own local log, not
        yet EP-092's actual persisted storage -- a subsequent
        `PersonalDataService.collect(SOURCE_ID)` call (via
        `PersonalDataManager`/`SolarCsvSource.collect()`) is required
        for it to reach `JsonlPersonalDataProvider`.

    Raises:
        ValueError: If `value`/`unit`/`timestamp` fail validation.
    """
    point = _build_point(value=value, unit=unit, timestamp_raw=timestamp)
    _append_to_log(point, log_path or DEFAULT_LOG_PATH)
    return point


def import_solar_csv(path: str | Path, log_path: Path | None = None) -> tuple[int, list[str]]:
    """Parse and append every valid row of a solar-generation readings CSV.

    Used by the `personal_data import-csv` CLI action. Follows the
    canonical EP-093/EP-094 CSV format (EP093_DESIGN.md §6.4, reused
    unmodified): `date,value,unit,meter_id` (`meter_id` optional). One
    malformed row is logged and skipped -- it must not abort the
    remaining rows.

    Args:
        path: The CSV file to import.
        log_path: Where to append valid readings. Defaults to
            `DEFAULT_LOG_PATH`.

    Returns:
        `(imported_count, skipped_row_messages)` -- the number of
        rows successfully appended, and one human-readable message per
        skipped row (empty if every row was valid).

    Raises:
        SolarMeterReadingError: If `path` does not exist or cannot be
            opened at all -- a failure that prevents *any* progress,
            per §6.4's "error reporting" rule. A per-row problem
            within an otherwise readable file is never raised.
    """
    csv_path = Path(path)
    try:
        file = csv_path.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise SolarMeterReadingError(f"Cannot read CSV file '{csv_path}': {exc}") from exc

    imported = 0
    skipped: list[str] = []
    with file:
        reader = csv_module.DictReader(file)
        missing = [column for column in _REQUIRED_CSV_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise SolarMeterReadingError(
                f"CSV file '{csv_path}' is missing required column(s): {', '.join(missing)}"
            )
        for row_number, row in enumerate(reader, start=2):  # header is row 1
            try:
                point = _build_point(
                    value=row.get("value", ""),
                    unit=row.get("unit", ""),
                    timestamp_raw=row.get("date"),
                    meter_id=(row.get("meter_id") or "").strip() or None,
                )
            except ValueError as exc:
                message = f"row {row_number}: {exc}"
                logger.error(f"Solar CSV import: skipping {message} in '{csv_path}'.")
                skipped.append(message)
                continue
            _append_to_log(point, log_path or DEFAULT_LOG_PATH)
            imported += 1
    return imported, skipped


class SolarCsvSource(PersonalDataSource):
    """Manual-entry + CSV-import `PersonalDataSource` for `solar_generation`.

    `collect()` reads every entry from this source's local log
    (written by `append_solar_reading()`/`import_solar_csv()`) and
    returns all of them, every time it is called -- it keeps no
    "already returned" cursor of its own. This is safe and idempotent
    by construction: EP-092's `PersonalDataManager`/
    `JsonlPersonalDataProvider.store_if_new()` already deduplicates on
    `(source_id, category, timestamp)` (EP093_DESIGN.md §10's
    "repeated execution" rule, reused unmodified), so re-collecting
    the same log entries never creates a duplicate persisted record.
    """

    def __init__(self, log_path: Path | None = None) -> None:
        """Initialize the source.

        Args:
            log_path: The local log file to read from. Defaults to
                `DEFAULT_LOG_PATH`.
        """
        self._log_path = log_path or DEFAULT_LOG_PATH

    @property
    def source_id(self) -> str:
        """Return this source's registration id ("solar_local_entry")."""
        return SOURCE_ID

    @property
    def category(self) -> str:
        """Return this source's category ("solar_generation")."""
        return CATEGORY

    def collect(self) -> list[PersonalDataPoint]:
        """Return every reading currently in this source's local log.

        Returns:
            All `PersonalDataPoint`s in the log, in file order. Empty
            if the log does not exist yet (nothing recorded/imported).
            A malformed line is logged and skipped, never aborting the
            rest (mirrors `JsonlPersonalDataProvider`'s established
            malformed-line tolerance, `EP092_ARCHITECTURE_AUDIT.md`
            EP092-AUDIT-004).
        """
        points: list[PersonalDataPoint] = []
        if not self._log_path.exists():
            return points
        with self._log_path.open("r", encoding="utf-8") as file:
            for line_number, raw_line in enumerate(file, start=1):
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    points.append(PersonalDataPoint.from_dict(json.loads(stripped)))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    logger.error(
                        f"Solar local-entry log: skipping malformed line "
                        f"{line_number} in '{self._log_path}' ({exc})."
                    )
        return points
