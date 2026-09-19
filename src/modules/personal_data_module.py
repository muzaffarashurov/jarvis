"""Personal data module: CLI command surface for EP-092/EP-093/EP-094.

Exposes the "personal_data" command namespace (status, collect, query,
record-reading, import-csv, help) as thin CommandModule handlers,
following the same pattern as LongTermMemoryModule/MemoryModule/
KnowledgeModule. All framework logic (registration, collection,
dedup, persistence, consent) lives in EP-092's `PersonalDataService`/
`PersonalDataManager`; all domain-specific validation and local-log
I/O lives in each acquisition EP's own
`src/core/personal_data/sources/` module (EP-093's electricity/gas,
EP-094's solar). This module only parses CLI arguments and formats
CommandResult objects for the shell -- it never becomes a second
orchestration/service layer (EP093_DESIGN.md §9.1).

This is a shared CLI namespace, not any one acquisition EP's exclusive
property (EP093_DESIGN.md §9.1 explicitly anticipated EP-094/EP-097
extending it the same way EP-093 built it after EP-092 left it
unbuilt): each acquisition EP adds one entry to `_CATEGORY_HANDLERS`
for its own category/categories, without introducing a new verb or
namespace.

Per the established layering rule (EP093_DESIGN.md §11), this module
imports only `PersonalDataService`, `CommandResult`, and a small set
of plain, per-acquisition-EP-owned symbols (`SOURCE_ID` constants and
the `append_*_reading()`/`import_*_csv()` module-level functions and
their error classes) from each `src/core/personal_data/sources/*`
module -- never `PersonalDataManager`, `PersonalDataProvider`,
`PersonalDataPersistence`, `PersonalDataRegistry`, or any concrete
`PersonalDataSource` subclass itself. `record-reading`/`import-csv`
call those plain functions (not the source classes) to write to the
local log, then delegate to `PersonalDataService.collect(source_id)`
for the actual EP-092 persistence step -- see those functions' own
docstrings for why they are free functions rather than source-class
methods.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Callable

from src.core.command_router import CommandResult
from src.core.personal_data.sources.electricity_source import (
    SOURCE_ID as ELECTRICITY_SOURCE_ID,
)
from src.core.personal_data.sources.electricity_source import (
    ElectricityMeterReadingError,
    append_electricity_reading,
    import_electricity_csv,
)
from src.core.personal_data.sources.gas_source import SOURCE_ID as GAS_SOURCE_ID
from src.core.personal_data.sources.gas_source import (
    GasMeterReadingError,
    append_gas_reading,
    import_gas_csv,
)
from src.core.personal_data.sources.solar_source import SOURCE_ID as SOLAR_SOURCE_ID
from src.core.personal_data.sources.solar_source import (
    SolarMeterReadingError,
    append_solar_reading,
    import_solar_csv,
)
from src.services.personal_data_report_service import (
    VALID_BUCKETS,
    VALID_EXPORT_MODES,
    PersonalDataReportError,
    aggregate,
    render_ascii_chart,
    render_report_text,
    write_raw_csv,
    write_report_csv,
)
from src.services.personal_data_service import PersonalDataService, PersonalDataStatus

HELP_TEXT: str = (
    "Available commands\n\n"
    "personal_data status\n"
    "personal_data collect <source_id>\n"
    "personal_data query <category> [start] [end]\n"
    "personal_data record-reading <category> <value> <unit> [timestamp]\n"
    "personal_data import-csv <category> <path>\n"
    "personal_data report <category> [start] [end] [bucket]\n"
    "personal_data export <category> <path> [start] [end] [mode]\n"
    "personal_data chart <category> [start] [end] [bucket]\n"
    "personal_data help"
)

# EP-095's default bucket size, applied whenever `report`/`chart` omit the
# optional trailing `[bucket]` argument, and whenever `export`'s `report`
# mode is used (that action's own CLI contract, EP095_DESIGN.md §7, takes
# no separate bucket argument, so its report-mode CSV always uses this
# same default).
_DEFAULT_BUCKET = "day"

# category -> (source_id, append_reading fn, import_csv fn), so record-reading/
# import-csv stay generic across category rather than hard-coding per-domain verbs
# (EP093_DESIGN.md §9.1). Each acquisition EP (EP-093 electricity/gas, EP-094 solar,
# future EP-097 weather) adds its own entry/entries here -- this dict is the one,
# already-disclosed coupling point (EP093-AUDIT-004; EP094_DESIGN.md §6C explicitly
# does not remediate it, only extends it).
_ELECTRICITY_CATEGORY = "electricity_consumption"
_GAS_CATEGORY = "gas_consumption"
_SOLAR_CATEGORY = "solar_generation"
_CATEGORY_HANDLERS: dict[str, tuple[str, Callable, Callable]] = {
    _ELECTRICITY_CATEGORY: (ELECTRICITY_SOURCE_ID, append_electricity_reading, import_electricity_csv),
    _GAS_CATEGORY: (GAS_SOURCE_ID, append_gas_reading, import_gas_csv),
    _SOLAR_CATEGORY: (SOLAR_SOURCE_ID, append_solar_reading, import_solar_csv),
}

# Every error class any registered category's import_*_csv() may raise for an
# unrecoverable (whole-file) failure -- extended by each acquisition EP.
_CSV_IMPORT_ERRORS = (ElectricityMeterReadingError, GasMeterReadingError, SolarMeterReadingError)

ActionHandler = Callable[[list[str]], CommandResult]


class PersonalDataModule:
    """Built-in "personal_data" command namespace for EP-092/EP-093/EP-094."""

    def __init__(
        self,
        personal_data_service: PersonalDataService,
        enabled_categories: frozenset[str] | None = None,
    ) -> None:
        """Initialize the PersonalDataModule.

        Args:
            personal_data_service: The EP-092 service used for
                collect/query/status.
            enabled_categories: The set of categories whose
                `record-reading`/`import-csv` actions are currently
                allowed -- resolved by the caller (`Bootstrap`) from
                each acquisition EP's own opt-in flag (e.g.
                'personal_data_electricity_gas.enabled',
                'personal_data_solar.enabled'), independent of EP-092's
                own 'personal_data.enabled'/'enabled_categories'
                consent gate. Defaults to an empty set (nothing
                enabled) when omitted. `status`/`collect`/`query`
                remain generic EP-092 pass-throughs, ungated by this
                value (EP093_DESIGN.md §9's "Enable/disable behavior",
                generalized from a single electricity/gas boolean to a
                per-category set per EP094_DESIGN.md §4/§11).
        """
        self._service = personal_data_service
        self._enabled_categories = enabled_categories if enabled_categories is not None else frozenset()
        self._actions: dict[str, ActionHandler] = {
            "status": self._status,
            "collect": self._collect,
            "query": self._query,
            "record-reading": self._record_reading,
            "import-csv": self._import_csv,
            "report": self._report,
            "export": self._export,
            "chart": self._chart,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "personal_data"."""
        return "personal_data"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "personal_data" action.

        Args:
            action: The requested action (e.g. "status").
            arguments: Additional arguments (e.g. a category).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "personal_data help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available personal_data commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display Personal Data Collection's overall status."""
        status: PersonalDataStatus = self._service.status()
        lines = [
            "Personal Data Collection Status",
            f"Enabled : {self._mark(status.enabled)}",
            f"Enabled Categories : {', '.join(status.enabled_categories) or 'none'}",
            f"Registered Sources : {', '.join(status.registered_sources) or 'none'}",
            f"Categories With Data : {status.category_count}",
            f"Total Points : {status.point_count}",
            f"Acquisition Enabled For : {', '.join(sorted(self._enabled_categories)) or 'none'}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    def _collect(self, arguments: list[str]) -> CommandResult:
        """Run one collection cycle for a registered source."""
        if not arguments:
            return CommandResult(success=False, message="Usage: personal_data collect <source_id>")
        return self._service.collect(arguments[0])

    def _query(self, arguments: list[str]) -> CommandResult:
        """List persisted points for a category, optionally bounded by time."""
        if not arguments:
            return CommandResult(
                success=False, message="Usage: personal_data query <category> [start] [end]"
            )
        category = arguments[0]
        start = self._parse_optional_datetime(arguments[1]) if len(arguments) > 1 else None
        end = self._parse_optional_datetime(arguments[2]) if len(arguments) > 2 else None
        if start is False or end is False:
            return CommandResult(
                success=False, message="start/end must be ISO-8601 dates or datetimes."
            )
        points = self._service.query(category, start or None, end or None)
        if not points:
            return CommandResult(success=True, message=f"personal_data: {category}\n\n(empty)")
        lines = [f"personal_data: {category}"]
        for point in points:
            lines.append(f"{point.timestamp.isoformat()} : {point.value} {point.unit}")
        return CommandResult(success=True, message="\n\n".join(lines))

    def _report(self, arguments: list[str]) -> CommandResult:
        """Show aggregated totals/averages/min/max for a category, optionally bucketed.

        EP-095 (EP095_DESIGN.md §7). Reuses `_parse_optional_datetime`
        and `_service.query()` exactly as `_query` does; all
        aggregation/formatting logic lives in
        `PersonalDataReportService`.
        """
        if not arguments:
            return CommandResult(
                success=False,
                message="Usage: personal_data report <category> [start] [end] [bucket]",
            )
        category = arguments[0]
        start = self._parse_optional_datetime(arguments[1]) if len(arguments) > 1 else None
        end = self._parse_optional_datetime(arguments[2]) if len(arguments) > 2 else None
        if start is False or end is False:
            return CommandResult(
                success=False, message="start/end must be ISO-8601 dates or datetimes."
            )
        bucket = arguments[3].lower() if len(arguments) > 3 else _DEFAULT_BUCKET
        if bucket not in VALID_BUCKETS:
            return CommandResult(
                success=False, message=f"bucket must be one of: {', '.join(VALID_BUCKETS)}."
            )
        points = self._service.query(category, start or None, end or None)
        if not points:
            return CommandResult(
                success=True, message=f"personal_data report: {category}\n\n(empty)"
            )
        overall, buckets = aggregate(points, bucket)
        text = render_report_text(category, start or None, end or None, overall, buckets)
        return CommandResult(success=True, message=text)

    def _export(self, arguments: list[str]) -> CommandResult:
        """Export a category's points (raw) or bucketed report to CSV.

        EP-095 (EP095_DESIGN.md §7/§13). CSV file I/O and schema
        formatting live in `PersonalDataReportService`; this handler
        only parses arguments and translates a `PersonalDataReportError`
        into a failing `CommandResult`, following `_import_csv`'s
        existing catch-and-translate pattern.
        """
        if len(arguments) < 2:
            return CommandResult(
                success=False,
                message="Usage: personal_data export <category> <path> [start] [end] [mode]",
            )
        category, path = arguments[0], arguments[1]
        start = self._parse_optional_datetime(arguments[2]) if len(arguments) > 2 else None
        end = self._parse_optional_datetime(arguments[3]) if len(arguments) > 3 else None
        if start is False or end is False:
            return CommandResult(
                success=False, message="start/end must be ISO-8601 dates or datetimes."
            )
        mode = arguments[4].lower() if len(arguments) > 4 else "raw"
        if mode not in VALID_EXPORT_MODES:
            return CommandResult(
                success=False, message=f"mode must be one of: {', '.join(VALID_EXPORT_MODES)}."
            )
        points = self._service.query(category, start or None, end or None)
        try:
            if mode == "raw":
                row_count = write_raw_csv(points, path)
            else:
                _, buckets = aggregate(points, _DEFAULT_BUCKET) if points else (None, [])
                row_count = write_report_csv(category, buckets, path)
        except PersonalDataReportError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Exported {row_count} row(s) to '{path}'.")

    def _chart(self, arguments: list[str]) -> CommandResult:
        """Render a console ASCII bar chart of a category's bucketed values.

        EP-095 (EP095_DESIGN.md §7/§20). No plotting dependency, no
        image file, no GUI -- pure text, dependency-free.
        """
        if not arguments:
            return CommandResult(
                success=False,
                message="Usage: personal_data chart <category> [start] [end] [bucket]",
            )
        category = arguments[0]
        start = self._parse_optional_datetime(arguments[1]) if len(arguments) > 1 else None
        end = self._parse_optional_datetime(arguments[2]) if len(arguments) > 2 else None
        if start is False or end is False:
            return CommandResult(
                success=False, message="start/end must be ISO-8601 dates or datetimes."
            )
        bucket = arguments[3].lower() if len(arguments) > 3 else _DEFAULT_BUCKET
        if bucket not in VALID_BUCKETS:
            return CommandResult(
                success=False, message=f"bucket must be one of: {', '.join(VALID_BUCKETS)}."
            )
        points = self._service.query(category, start or None, end or None)
        if not points:
            return CommandResult(
                success=True, message=f"personal_data chart: {category}\n\n(empty)"
            )
        _, buckets = aggregate(points, bucket)
        chart_text = render_ascii_chart(buckets)
        return CommandResult(success=True, message=f"personal_data chart: {category}\n\n{chart_text}")

    def _record_reading(self, arguments: list[str]) -> CommandResult:
        """Record one manually-entered reading for a category."""
        if len(arguments) < 3:
            return CommandResult(
                success=False,
                message="Usage: personal_data record-reading <category> <value> <unit> [timestamp]",
            )
        category, value, unit = arguments[0], arguments[1], arguments[2]
        timestamp = arguments[3] if len(arguments) > 3 else None
        handlers = _CATEGORY_HANDLERS.get(category)
        if handlers is None:
            return CommandResult(
                success=False,
                message=(
                    f"Unknown category '{category}'. Supported: "
                    f"{', '.join(_CATEGORY_HANDLERS)}."
                ),
            )
        disabled = self._ensure_category_enabled(category)
        if disabled is not None:
            return disabled
        source_id, append_reading, _import_csv = handlers
        try:
            append_reading(value=value, unit=unit, timestamp=timestamp)
        except ValueError as exc:
            return CommandResult(success=False, message=f"Invalid reading: {exc}")
        return self._collect_after_append(source_id, category)

    def _import_csv(self, arguments: list[str]) -> CommandResult:
        """Import every valid row of a CSV file for a category."""
        if len(arguments) < 2:
            return CommandResult(
                success=False, message="Usage: personal_data import-csv <category> <path>"
            )
        category, path = arguments[0], arguments[1]
        handlers = _CATEGORY_HANDLERS.get(category)
        if handlers is None:
            return CommandResult(
                success=False,
                message=(
                    f"Unknown category '{category}'. Supported: "
                    f"{', '.join(_CATEGORY_HANDLERS)}."
                ),
            )
        disabled = self._ensure_category_enabled(category)
        if disabled is not None:
            return disabled
        source_id, _append_reading, import_csv = handlers
        try:
            imported, skipped = import_csv(path)
        except _CSV_IMPORT_ERRORS as exc:
            return CommandResult(success=False, message=str(exc))
        summary = f"Imported {imported} row(s) from '{path}'."
        if skipped:
            summary += f" Skipped {len(skipped)} invalid row(s):\n" + "\n".join(skipped)
        if imported == 0:
            # Nothing valid was found to collect -- per EP-093 STEP 3 audit finding
            # EP093-AUDIT-002, this must not be reported as success, even though
            # PersonalDataService.collect() itself "succeeds" trivially with zero
            # new points. There is nothing to collect, so collect() is not called.
            return CommandResult(success=False, message=summary)
        collect_result = self._collect_after_append(source_id, category)
        return CommandResult(
            success=collect_result.success,
            message=f"{summary}\n\n{collect_result.message}",
        )

    # ---------- Internal helpers ----------

    def _collect_after_append(self, source_id: str, category: str) -> CommandResult:
        """Trigger EP-092 collection after writing to the local log.

        Writing a reading to an acquisition EP's own local log (via
        `append_*_reading()`/`import_*_csv()`) does not by itself
        reach EP-092's actual persisted storage -- this calls
        `PersonalDataService.collect(source_id)` so the newly-written
        entries are picked up by the matching `PersonalDataSource`
        subclass's `collect()` and go through EP-092's consent gate +
        dedup + persistence, exactly as `personal_data collect
        <source_id>` would.
        """
        result = self._service.collect(source_id)
        if not result.success:
            return CommandResult(
                success=False,
                message=(
                    f"Reading recorded locally, but collection into personal_data.{category} "
                    f"failed: {result.message}"
                ),
            )
        return result

    def _ensure_category_enabled(self, category: str) -> CommandResult | None:
        """Return a failing CommandResult if `category`'s acquisition is disabled, else None."""
        if category in self._enabled_categories:
            return None
        return CommandResult(
            success=False,
            message=(
                f"Acquisition for category '{category}' is disabled. Enable the matching "
                "domain-group config block (e.g. 'personal_data_electricity_gas.enabled' or "
                "'personal_data_solar.enabled') in config/config.yaml to use this command."
            ),
        )

    @staticmethod
    def _parse_optional_datetime(raw: str):
        """Parse an optional ISO-8601 date/datetime argument.

        Returns:
            The parsed datetime, or `False` if `raw` is not valid
            ISO-8601 (a sentinel distinct from `None`, which means
            "not supplied").
        """
        try:
            return datetime.combine(date.fromisoformat(raw), datetime.min.time(), tzinfo=timezone.utc)
        except ValueError:
            pass
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return False
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean status check as "OK" or "FAIL"."""
        return "OK" if value else "FAIL"
