"""Personal data module: CLI command surface for EP-092/EP-093.

Exposes the "personal_data" command namespace (status, collect, query,
record-reading, import-csv, help) as thin CommandModule handlers,
following the same pattern as LongTermMemoryModule/MemoryModule/
KnowledgeModule. All framework logic (registration, collection,
dedup, persistence, consent) lives in EP-092's `PersonalDataService`/
`PersonalDataManager`; all electricity/gas-specific validation and
local-log I/O lives in EP-093's `src/core/personal_data/sources/`
modules. This module only parses CLI arguments and formats
CommandResult objects for the shell -- it never becomes a second
orchestration/service layer (STEP 1 design §9.1).

Per STEP 1 design §11's layering rule, this module imports only
`PersonalDataService`, `CommandResult`, and a small set of plain,
EP-093-owned symbols (`SOURCE_ID` constants and the
`append_*_reading()`/`import_*_csv()` module-level functions and their
error classes) from `src/core/personal_data/sources/` -- never
`PersonalDataManager`, `PersonalDataProvider`,
`PersonalDataPersistence`, `PersonalDataRegistry`, or either
`ElectricityCsvSource`/`GasCsvSource` class itself. `record-reading`/
`import-csv` call those plain functions (not the source classes) to
write to the local log, then delegate to
`PersonalDataService.collect(source_id)` for the actual EP-092
persistence step -- see those functions' own docstrings for why they
are free functions rather than source-class methods.
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
from src.services.personal_data_service import PersonalDataService, PersonalDataStatus

HELP_TEXT: str = (
    "Available commands\n\n"
    "personal_data status\n"
    "personal_data collect <source_id>\n"
    "personal_data query <category> [start] [end]\n"
    "personal_data record-reading <category> <value> <unit> [timestamp]\n"
    "personal_data import-csv <category> <path>\n"
    "personal_data help"
)

# category -> (source_id, append_reading fn, import_csv fn), so record-reading/
# import-csv stay generic across category rather than hard-coding per-domain verbs
# (STEP 1 design §9.1).
_ELECTRICITY_CATEGORY = "electricity_consumption"
_GAS_CATEGORY = "gas_consumption"
_CATEGORY_HANDLERS: dict[str, tuple[str, Callable, Callable]] = {
    _ELECTRICITY_CATEGORY: (ELECTRICITY_SOURCE_ID, append_electricity_reading, import_electricity_csv),
    _GAS_CATEGORY: (GAS_SOURCE_ID, append_gas_reading, import_gas_csv),
}

ActionHandler = Callable[[list[str]], CommandResult]


class PersonalDataModule:
    """Built-in "personal_data" command namespace for EP-092/EP-093."""

    def __init__(
        self, personal_data_service: PersonalDataService, electricity_gas_enabled: bool = False
    ) -> None:
        """Initialize the PersonalDataModule.

        Args:
            personal_data_service: The EP-092 service used for
                collect/query/status.
            electricity_gas_enabled: The resolved
                'personal_data_electricity_gas.enabled' setting
                (EP-093's own opt-in, independent of EP-092's
                'personal_data.enabled'/'enabled_categories'). Gates
                `record-reading`/`import-csv` only -- `status`/
                `collect`/`query` remain generic EP-092 pass-throughs
                (STEP 1 design §9's "Enable/disable behavior").
        """
        self._service = personal_data_service
        self._electricity_gas_enabled = electricity_gas_enabled
        self._actions: dict[str, ActionHandler] = {
            "status": self._status,
            "collect": self._collect,
            "query": self._query,
            "record-reading": self._record_reading,
            "import-csv": self._import_csv,
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
            f"Electricity & Gas Monitoring (EP-093) : "
            f"{self._mark(self._electricity_gas_enabled)}",
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

    def _record_reading(self, arguments: list[str]) -> CommandResult:
        """Record one manually-entered reading for a category."""
        disabled = self._ensure_electricity_gas_enabled()
        if disabled is not None:
            return disabled
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
        source_id, append_reading, _import_csv = handlers
        try:
            append_reading(value=value, unit=unit, timestamp=timestamp)
        except ValueError as exc:
            return CommandResult(success=False, message=f"Invalid reading: {exc}")
        return self._collect_after_append(source_id, category)

    def _import_csv(self, arguments: list[str]) -> CommandResult:
        """Import every valid row of a CSV file for a category."""
        disabled = self._ensure_electricity_gas_enabled()
        if disabled is not None:
            return disabled
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
        source_id, _append_reading, import_csv = handlers
        try:
            imported, skipped = import_csv(path)
        except (ElectricityMeterReadingError, GasMeterReadingError) as exc:
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

        Writing a reading to EP-093's own local log (via
        `append_*_reading()`/`import_*_csv()`) does not by itself
        reach EP-092's actual persisted storage -- this calls
        `PersonalDataService.collect(source_id)` so the newly-written
        entries are picked up by `ElectricityCsvSource`/`GasCsvSource
        .collect()` and go through EP-092's consent gate + dedup +
        persistence, exactly as `personal_data collect <source_id>`
        would.
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

    def _ensure_electricity_gas_enabled(self) -> CommandResult | None:
        """Return a failing CommandResult if EP-093 is disabled, else None."""
        if self._electricity_gas_enabled:
            return None
        return CommandResult(
            success=False,
            message=(
                "Electricity & Gas Monitoring (EP-093) is disabled. Set "
                "'personal_data_electricity_gas.enabled: true' in config/config.yaml "
                "to use this command."
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
