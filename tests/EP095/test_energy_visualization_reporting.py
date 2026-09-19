"""Real engineering tests for EP-095 - Energy Visualization & Reporting.

Builds real `PersonalDataReportService` functions directly (pure,
no I/O beyond CSV writing) and real, temporary-directory-backed
`Config`/`PersonalDataService`/`PersonalDataManager`/
`JsonlPersonalDataProvider`/`ElectricityCsvSource` instances -- driven
exactly as a caller would, no mocked internals, matching every other
EP's test suite in this project (in particular `tests/EP093/
test_electricity_gas_monitoring.py`, whose structure this suite
reuses directly).

EP-095 consumes EP-092's Personal Data Collection Framework exclusively
through `PersonalDataService.query()` (EP095_DESIGN.md §2/§7 -- never
`PersonalDataManager`/`PersonalDataProvider` directly). This suite
covers:

1. `aggregate()`: day/week/month bucketing, count/sum/avg/min/max,
   chronological ordering, bucket boundaries, empty input, invalid
   bucket, mixed-unit handling.
2. `write_raw_csv()`/`write_report_csv()`: exact header/column order,
   zero-row (header-only) exports, round-trip reading, missing-
   directory failure.
3. `render_ascii_chart()`: chronological order, proportional bars,
   empty data.
4. `PersonalDataModule`'s `report`/`export`/`chart` actions end to
   end, through a real `PersonalDataService`: valid/invalid
   arguments, empty data, Windows-style paths with spaces, overwrite
   behavior, and the corrected consent/read-behavior semantics
   (EP095_DESIGN.md §11 -- historical data remains readable after a
   category is removed from `enabled_categories`).
5. Architecture compliance: `personal_data_report_service.py` never
   imports `PersonalDataManager`/`PersonalDataProvider`/
   `PersonalDataPersistence`/`PersonalDataRegistry`, and never
   references `CommandResult`; `personal_data_module.py` continues to
   never import those same forbidden symbols.
"""

from __future__ import annotations

import ast
import inspect
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.core.config import Config
from src.core.personal_data.personal_data_record import PersonalDataPoint
from src.core.personal_data.sources.electricity_source import (
    CATEGORY as ELECTRICITY_CATEGORY,
)
from src.core.personal_data.sources.electricity_source import (
    SOURCE_ID as ELECTRICITY_SOURCE_ID,
)
from src.core.personal_data.sources.electricity_source import (
    ElectricityCsvSource,
    append_electricity_reading,
)
from src.modules import personal_data_module as personal_data_module_module
from src.modules.personal_data_module import PersonalDataModule
from src.services import personal_data_report_service as report_service_module
from src.services.personal_data_report_service import (
    OverallSummary,
    PersonalDataReportError,
    aggregate,
    render_ascii_chart,
    write_raw_csv,
    write_report_csv,
)
from src.services.personal_data_service import PersonalDataService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


def _write_config(
    directory: Path, enabled_categories: list[str] | None = None, enabled: bool = True
) -> Config:
    """Write a minimal config.yaml (personal_data only) and load it.

    Always writes to `directory / "config.yaml"` and always resolves
    `storage_root` to `directory / "personal_data"` -- calling this
    twice for the same `directory` intentionally reuses the same
    on-disk storage, which is exactly how the historical-data/
    subsystem-disabled tests below simulate an operator editing
    `config/config.yaml` and restarting Jarvis (EP095_DESIGN.md §11).
    """
    categories = enabled_categories if enabled_categories is not None else [ELECTRICITY_CATEGORY]
    categories_yaml = "[" + ", ".join(f'"{item}"' for item in categories) + "]"
    storage_root = directory / "personal_data"
    storage_root_yaml = str(storage_root).replace("'", "''")
    config_path = directory / "config.yaml"
    config_path.write_text(
        "personal_data:\n"
        f"  enabled: {'true' if enabled else 'false'}\n"
        f"  enabled_categories: {categories_yaml}\n"
        f"  storage_root: '{storage_root_yaml}'\n",
        encoding="utf-8",
    )
    return Config(config_path).load()


def _point(
    value: float,
    unit: str,
    timestamp: str,
    point_id: str | None = None,
    source_id: str = "test_source",
    category: str = ELECTRICITY_CATEGORY,
) -> PersonalDataPoint:
    """Build a `PersonalDataPoint` directly, for pure aggregation/CSV/chart tests."""
    ts = datetime.fromisoformat(timestamp)
    return PersonalDataPoint(
        id=point_id or f"{source_id}:{timestamp}",
        source_id=source_id,
        category=category,
        timestamp=ts,
        value=value,
        unit=unit,
    )


@TestRegistry.register
class EnergyVisualizationReportingTest(BaseTest):
    """Real tests covering EP-095's Energy Visualization & Reporting."""

    NAME = "EP095"

    def run(self):
        """Execute every Energy Visualization & Reporting check and return the result."""
        # Aggregation
        self._test_aggregate_day_bucket()
        self._test_aggregate_week_bucket()
        self._test_aggregate_month_bucket()
        self._test_aggregate_bucket_boundary()
        self._test_aggregate_empty_input()
        self._test_aggregate_invalid_bucket_raises()
        self._test_aggregate_chronological_order()

        # Mixed units
        self._test_aggregate_mixed_units_overall()
        self._test_aggregate_mixed_units_per_bucket()
        self._test_aggregate_single_unit_not_marked_mixed()

        # Raw CSV
        self._test_write_raw_csv_round_trip()
        self._test_write_raw_csv_zero_rows_header_only()
        self._test_write_raw_csv_excludes_raw_field()
        self._test_write_raw_csv_missing_directory_raises()

        # Report CSV
        self._test_write_report_csv_round_trip()
        self._test_write_report_csv_mixed_unit_marks_row()
        self._test_write_report_csv_zero_rows_header_only()

        # ASCII chart
        self._test_render_ascii_chart_basic()
        self._test_render_ascii_chart_empty()
        self._test_render_ascii_chart_proportional()

        # CLI: report
        self._test_cli_report_end_to_end()
        self._test_cli_report_empty()
        self._test_cli_report_invalid_bucket()
        self._test_cli_report_invalid_dates()
        self._test_cli_report_missing_category()
        self._test_cli_report_default_bucket_is_day()

        # CLI: export
        self._test_cli_export_raw_end_to_end()
        self._test_cli_export_report_end_to_end()
        self._test_cli_export_invalid_mode()
        self._test_cli_export_missing_directory()
        self._test_cli_export_zero_rows_header_only()
        self._test_cli_export_overwrite_existing_file()
        self._test_cli_export_windows_style_path_with_spaces()
        self._test_cli_export_default_mode_is_raw()

        # CLI: chart
        self._test_cli_chart_end_to_end()
        self._test_cli_chart_empty()
        self._test_cli_chart_invalid_bucket()

        # Date/time semantics
        self._test_date_handling_bare_date()
        self._test_date_handling_inclusive_bounds()
        self._test_date_handling_start_equals_end()

        # Consent/read behavior (EP095_DESIGN.md §11)
        self._test_historical_data_readable_after_category_disabled()
        self._test_subsystem_disabled_yields_empty_for_all_three_actions()

        # Architecture compliance
        self._test_module_never_imports_forbidden_symbols()
        self._test_report_service_never_imports_forbidden_symbols()
        self._test_report_service_never_references_command_result()

        return self.result

    # ---------- Helpers ----------

    def _temp_dir(self) -> Path:
        tmp_dir = tempfile.TemporaryDirectory()
        self._keep_alive(tmp_dir)
        return Path(tmp_dir.name)

    def _keep_alive(self, obj: object) -> None:
        if not hasattr(self, "_tmp_dirs"):
            self._tmp_dirs = []
        self._tmp_dirs.append(obj)

    def _build_service(self, enabled_categories: list[str] | None = None) -> PersonalDataService:
        tmp = self._temp_dir()
        config = _write_config(tmp, enabled_categories)
        return PersonalDataService(config=config)

    def _build_service_in(
        self, directory: Path, enabled_categories: list[str] | None = None
    ) -> PersonalDataService:
        """Build a service backed by an explicit, reusable config/storage directory.

        Used to simulate re-reading already-persisted data under a
        *different* `enabled_categories` allowlist -- via a second,
        independently-constructed `Config`/`PersonalDataService` built
        from a config.yaml rewritten (in the same directory, so the
        JSONL storage path stays identical) with a different
        allowlist, exactly as would happen if an operator edited
        `config/config.yaml` and restarted Jarvis. No private
        attribute of either service is touched; the previously-built
        service already loaded its own `Config` into memory before
        this overwrites the file, so it is unaffected.
        """
        config = _write_config(directory, enabled_categories)
        return PersonalDataService(config=config)

    def _seed_electricity_points(
        self,
        service: PersonalDataService,
        readings: list[tuple[str, str, str]],
    ) -> None:
        """Append/collect real electricity readings: `[(value, unit, timestamp), ...]`."""
        log_path = self._temp_dir() / "electricity_consumption.jsonl"
        for value, unit, timestamp in readings:
            append_electricity_reading(value=value, unit=unit, timestamp=timestamp, log_path=log_path)
        service.register_source(ElectricityCsvSource(log_path=log_path))
        collect_result = service.collect(ELECTRICITY_SOURCE_ID)
        self.assert_true(collect_result.success, collect_result.message)

    # ---------- Aggregation ----------

    def _test_aggregate_day_bucket(self) -> None:
        points = [
            _point(10.0, "kWh", "2026-01-01T08:00:00+00:00"),
            _point(20.0, "kWh", "2026-01-01T18:00:00+00:00"),
            _point(30.0, "kWh", "2026-01-02T08:00:00+00:00"),
        ]
        overall, buckets = aggregate(points, "day")
        self.assert_true(isinstance(overall, OverallSummary))
        self.assert_equal(overall.count, 3)
        self.assert_equal(overall.sum, 60.0)
        self.assert_equal(overall.avg, 20.0)
        self.assert_equal(overall.min, 10.0)
        self.assert_equal(overall.max, 30.0)
        self.assert_equal(len(buckets), 2)
        self.assert_equal(buckets[0].count, 2)
        self.assert_equal(buckets[0].sum, 30.0)
        self.assert_equal(buckets[1].count, 1)
        self.assert_equal(buckets[1].sum, 30.0)
        self.assert_equal(buckets[0].bucket_start, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assert_equal(buckets[0].bucket_end, datetime(2026, 1, 2, tzinfo=timezone.utc))

    def _test_aggregate_week_bucket(self) -> None:
        # 2026-01-01 (Thu) and 2026-01-02 (Fri) fall in the same ISO week
        # (Monday 2025-12-29 .. Sunday 2026-01-04); 2026-01-05 (Mon) starts
        # the next ISO week.
        points = [
            _point(1.0, "kWh", "2026-01-01T00:00:00+00:00"),
            _point(2.0, "kWh", "2026-01-02T00:00:00+00:00"),
            _point(3.0, "kWh", "2026-01-05T00:00:00+00:00"),
        ]
        _, buckets = aggregate(points, "week")
        self.assert_equal(len(buckets), 2)
        self.assert_equal(buckets[0].bucket_start, datetime(2025, 12, 29, tzinfo=timezone.utc))
        self.assert_equal(buckets[0].bucket_end, datetime(2026, 1, 5, tzinfo=timezone.utc))
        self.assert_equal(buckets[0].count, 2)
        self.assert_equal(buckets[1].bucket_start, datetime(2026, 1, 5, tzinfo=timezone.utc))
        self.assert_equal(buckets[1].count, 1)

    def _test_aggregate_month_bucket(self) -> None:
        points = [
            _point(1.0, "kWh", "2026-01-31T23:00:00+00:00"),
            _point(2.0, "kWh", "2026-02-01T00:00:00+00:00"),
            _point(3.0, "kWh", "2026-12-15T00:00:00+00:00"),
        ]
        _, buckets = aggregate(points, "month")
        self.assert_equal(len(buckets), 3)
        self.assert_equal(buckets[0].bucket_start, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assert_equal(buckets[0].bucket_end, datetime(2026, 2, 1, tzinfo=timezone.utc))
        self.assert_equal(buckets[1].bucket_start, datetime(2026, 2, 1, tzinfo=timezone.utc))
        self.assert_equal(buckets[1].bucket_end, datetime(2026, 3, 1, tzinfo=timezone.utc))
        # December -> January year rollover
        self.assert_equal(buckets[2].bucket_start, datetime(2026, 12, 1, tzinfo=timezone.utc))
        self.assert_equal(buckets[2].bucket_end, datetime(2027, 1, 1, tzinfo=timezone.utc))

    def _test_aggregate_bucket_boundary(self) -> None:
        # Exactly at midnight -- must land in the *new* day, not the previous one.
        points = [
            _point(1.0, "kWh", "2026-01-01T23:59:59+00:00"),
            _point(2.0, "kWh", "2026-01-02T00:00:00+00:00"),
        ]
        _, buckets = aggregate(points, "day")
        self.assert_equal(len(buckets), 2)
        self.assert_equal(buckets[0].bucket_start, datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.assert_equal(buckets[0].count, 1)
        self.assert_equal(buckets[1].bucket_start, datetime(2026, 1, 2, tzinfo=timezone.utc))
        self.assert_equal(buckets[1].count, 1)

    def _test_aggregate_empty_input(self) -> None:
        overall, buckets = aggregate([], "day")
        self.assert_true(overall is None)
        self.assert_equal(buckets, [])

    def _test_aggregate_invalid_bucket_raises(self) -> None:
        try:
            aggregate([_point(1.0, "kWh", "2026-01-01T00:00:00+00:00")], "year")
        except ValueError as exc:
            self.assert_true("day, week, month" in str(exc))
        else:
            self.assert_true(False, "An invalid bucket value should raise ValueError")

    def _test_aggregate_chronological_order(self) -> None:
        # Points supplied out of order -- buckets must still come back sorted.
        points = [
            _point(1.0, "kWh", "2026-03-01T00:00:00+00:00"),
            _point(2.0, "kWh", "2026-01-01T00:00:00+00:00"),
            _point(3.0, "kWh", "2026-02-01T00:00:00+00:00"),
        ]
        _, buckets = aggregate(points, "month")
        starts = [bucket.bucket_start for bucket in buckets]
        self.assert_equal(starts, sorted(starts))

    # ---------- Mixed units ----------

    def _test_aggregate_mixed_units_overall(self) -> None:
        points = [
            _point(10.0, "kWh", "2026-01-01T00:00:00+00:00"),
            _point(20.0, "MWh", "2026-01-02T00:00:00+00:00"),
        ]
        overall, _ = aggregate(points, "day")
        self.assert_true(overall.is_mixed_unit)
        self.assert_equal(overall.units, ("MWh", "kWh"))
        self.assert_equal(overall.csv_unit, "mixed")
        # Arithmetic is still performed on raw values, never converted/dropped.
        self.assert_equal(overall.sum, 30.0)
        self.assert_equal(overall.count, 2)

    def _test_aggregate_mixed_units_per_bucket(self) -> None:
        points = [
            _point(10.0, "kWh", "2026-01-01T08:00:00+00:00"),
            _point(20.0, "MWh", "2026-01-01T18:00:00+00:00"),
            _point(30.0, "kWh", "2026-01-02T08:00:00+00:00"),
        ]
        _, buckets = aggregate(points, "day")
        self.assert_true(buckets[0].is_mixed_unit)
        self.assert_equal(buckets[0].csv_unit, "mixed")
        self.assert_false(buckets[1].is_mixed_unit)
        self.assert_equal(buckets[1].csv_unit, "kWh")

    def _test_aggregate_single_unit_not_marked_mixed(self) -> None:
        points = [
            _point(10.0, "kWh", "2026-01-01T00:00:00+00:00"),
            _point(20.0, "kWh", "2026-01-02T00:00:00+00:00"),
        ]
        overall, _ = aggregate(points, "day")
        self.assert_false(overall.is_mixed_unit)
        self.assert_equal(overall.units, ("kWh",))
        self.assert_equal(overall.csv_unit, "kWh")

    # ---------- Raw CSV ----------

    def _test_write_raw_csv_round_trip(self) -> None:
        points = [
            _point(10.0, "kWh", "2026-01-01T08:00:00+00:00", point_id="p1", source_id="s1"),
            _point(20.0, "kWh", "2026-01-02T08:00:00+00:00", point_id="p2", source_id="s1"),
        ]
        path = self._temp_dir() / "raw.csv"
        row_count = write_raw_csv(points, path)
        self.assert_equal(row_count, 2)
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        self.assert_equal(
            lines[0], "id,source_id,category,timestamp,value,unit,collected_at"
        )
        self.assert_equal(len(lines), 3)
        self.assert_true("p1" in lines[1] and "10.0" in lines[1] and "kWh" in lines[1])
        self.assert_true("p2" in lines[2])

    def _test_write_raw_csv_zero_rows_header_only(self) -> None:
        path = self._temp_dir() / "empty.csv"
        row_count = write_raw_csv([], path)
        self.assert_equal(row_count, 0)
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assert_equal(len(lines), 1)
        self.assert_equal(lines[0], "id,source_id,category,timestamp,value,unit,collected_at")

    def _test_write_raw_csv_excludes_raw_field(self) -> None:
        point = PersonalDataPoint(
            id="p1",
            source_id="s1",
            category=ELECTRICITY_CATEGORY,
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            value=1.0,
            unit="kWh",
            raw={"secret_provider_id": "should-never-appear"},
        )
        path = self._temp_dir() / "raw_excl.csv"
        write_raw_csv([point], path)
        text = path.read_text(encoding="utf-8")
        self.assert_false("secret_provider_id" in text)
        self.assert_false("should-never-appear" in text)

    def _test_write_raw_csv_missing_directory_raises(self) -> None:
        missing_dir_path = self._temp_dir() / "does_not_exist" / "raw.csv"
        try:
            write_raw_csv([], missing_dir_path)
        except PersonalDataReportError as exc:
            self.assert_true("directory does not exist" in str(exc))
        else:
            self.assert_true(False, "A missing parent directory should raise PersonalDataReportError")
        self.assert_false(missing_dir_path.exists(), "No partial file should be left behind")

    # ---------- Report CSV ----------

    def _test_write_report_csv_round_trip(self) -> None:
        points = [
            _point(10.0, "kWh", "2026-01-01T08:00:00+00:00"),
            _point(20.0, "kWh", "2026-01-02T08:00:00+00:00"),
        ]
        _, buckets = aggregate(points, "day")
        path = self._temp_dir() / "report.csv"
        row_count = write_report_csv(ELECTRICITY_CATEGORY, buckets, path)
        self.assert_equal(row_count, 2)
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assert_equal(
            lines[0], "category,bucket_start,bucket_end,count,sum,avg,min,max,unit"
        )
        self.assert_equal(len(lines), 3)
        self.assert_true(ELECTRICITY_CATEGORY in lines[1])
        self.assert_true("kWh" in lines[1])

    def _test_write_report_csv_mixed_unit_marks_row(self) -> None:
        points = [
            _point(10.0, "kWh", "2026-01-01T08:00:00+00:00"),
            _point(20.0, "MWh", "2026-01-01T18:00:00+00:00"),
        ]
        _, buckets = aggregate(points, "day")
        path = self._temp_dir() / "report_mixed.csv"
        write_report_csv(ELECTRICITY_CATEGORY, buckets, path)
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assert_true(lines[1].rstrip().endswith(",mixed"))
        self.assert_false("kWh" in lines[1])
        self.assert_false("MWh" in lines[1])

    def _test_write_report_csv_zero_rows_header_only(self) -> None:
        path = self._temp_dir() / "report_empty.csv"
        row_count = write_report_csv(ELECTRICITY_CATEGORY, [], path)
        self.assert_equal(row_count, 0)
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assert_equal(len(lines), 1)

    # ---------- ASCII chart ----------

    def _test_render_ascii_chart_basic(self) -> None:
        points = [
            _point(10.0, "kWh", "2026-01-01T00:00:00+00:00"),
            _point(20.0, "kWh", "2026-01-02T00:00:00+00:00"),
        ]
        _, buckets = aggregate(points, "day")
        text = render_ascii_chart(buckets)
        lines = text.splitlines()
        self.assert_equal(len(lines), 2)
        self.assert_true(lines[0].startswith("2026-01-01"))
        self.assert_true(lines[1].startswith("2026-01-02"))

    def _test_render_ascii_chart_empty(self) -> None:
        self.assert_equal(render_ascii_chart([]), "(empty)")

    def _test_render_ascii_chart_proportional(self) -> None:
        points = [
            _point(10.0, "kWh", "2026-01-01T00:00:00+00:00"),
            _point(20.0, "kWh", "2026-01-02T00:00:00+00:00"),
        ]
        _, buckets = aggregate(points, "day")
        text = render_ascii_chart(buckets, max_width=40)
        lines = text.splitlines()
        bar_0 = lines[0].split("|")[1].split("10.0")[0].strip()
        bar_1 = lines[1].split("|")[1].split("20.0")[0].strip()
        # The second bucket's sum is double the first's -- its bar must be
        # (approximately, allowing for rounding) double the length.
        self.assert_true(len(bar_1) > len(bar_0))
        self.assert_equal(len(bar_1), 40)

    # ---------- CLI: report ----------

    def _test_cli_report_end_to_end(self) -> None:
        service = self._build_service()
        self._seed_electricity_points(
            service,
            [
                ("10", "kWh", "2026-01-01T08:00:00+00:00"),
                ("20", "kWh", "2026-01-01T18:00:00+00:00"),
                ("30", "kWh", "2026-01-02T08:00:00+00:00"),
            ],
        )
        module = PersonalDataModule(service)
        result = module.execute("report", [ELECTRICITY_CATEGORY])
        self.assert_true(result.success, result.message)
        self.assert_true("Count: 3" in result.message)
        self.assert_true("Sum: 60.0" in result.message)

    def _test_cli_report_empty(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service)
        result = module.execute("report", [ELECTRICITY_CATEGORY])
        self.assert_true(result.success, result.message)
        self.assert_true("(empty)" in result.message)

    def _test_cli_report_invalid_bucket(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service)
        result = module.execute(
            "report", [ELECTRICITY_CATEGORY, "2026-01-01", "2026-01-02", "year"]
        )
        self.assert_false(result.success)
        self.assert_equal(result.message, "bucket must be one of: day, week, month.")

    def _test_cli_report_invalid_dates(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service)
        result = module.execute("report", [ELECTRICITY_CATEGORY, "not-a-date"])
        self.assert_false(result.success)
        self.assert_equal(result.message, "start/end must be ISO-8601 dates or datetimes.")

    def _test_cli_report_missing_category(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service)
        result = module.execute("report", [])
        self.assert_false(result.success)
        self.assert_true("Usage: personal_data report" in result.message)

    def _test_cli_report_default_bucket_is_day(self) -> None:
        service = self._build_service()
        self._seed_electricity_points(
            service,
            [
                ("10", "kWh", "2026-01-01T08:00:00+00:00"),
                ("20", "kWh", "2026-01-02T08:00:00+00:00"),
            ],
        )
        module = PersonalDataModule(service)
        result = module.execute("report", [ELECTRICITY_CATEGORY])
        # Two distinct calendar days -> two bucket lines under the default "day" bucket.
        bucket_lines = [line for line in result.message.splitlines() if " .. " in line]
        self.assert_equal(len(bucket_lines), 2)

    # ---------- CLI: export ----------

    def _test_cli_export_raw_end_to_end(self) -> None:
        service = self._build_service()
        self._seed_electricity_points(
            service,
            [
                ("10", "kWh", "2026-01-01T08:00:00+00:00"),
                ("20", "kWh", "2026-01-02T08:00:00+00:00"),
            ],
        )
        module = PersonalDataModule(service)
        out_path = self._temp_dir() / "export_raw.csv"
        result = module.execute("export", [ELECTRICITY_CATEGORY, str(out_path)])
        self.assert_true(result.success, result.message)
        self.assert_true("Exported 2 row(s)" in result.message)
        lines = out_path.read_text(encoding="utf-8").splitlines()
        self.assert_equal(len(lines), 3)
        self.assert_equal(
            lines[0], "id,source_id,category,timestamp,value,unit,collected_at"
        )

    def _test_cli_export_report_end_to_end(self) -> None:
        service = self._build_service()
        self._seed_electricity_points(
            service,
            [
                ("10", "kWh", "2026-01-01T08:00:00+00:00"),
                ("20", "kWh", "2026-01-02T08:00:00+00:00"),
            ],
        )
        module = PersonalDataModule(service)
        out_path = self._temp_dir() / "export_report.csv"
        result = module.execute(
            "export", [ELECTRICITY_CATEGORY, str(out_path), "2026-01-01", "2026-01-03", "report"]
        )
        self.assert_true(result.success, result.message)
        self.assert_true("Exported 2 row(s)" in result.message)
        lines = out_path.read_text(encoding="utf-8").splitlines()
        self.assert_equal(
            lines[0], "category,bucket_start,bucket_end,count,sum,avg,min,max,unit"
        )
        self.assert_equal(len(lines), 3)

    def _test_cli_export_invalid_mode(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service)
        out_path = self._temp_dir() / "bad_mode.csv"
        result = module.execute(
            "export", [ELECTRICITY_CATEGORY, str(out_path), "2026-01-01", "2026-01-02", "json"]
        )
        self.assert_false(result.success)
        self.assert_equal(result.message, "mode must be one of: raw, report.")
        self.assert_false(out_path.exists())

    def _test_cli_export_missing_directory(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service)
        out_path = self._temp_dir() / "no_such_dir" / "out.csv"
        result = module.execute("export", [ELECTRICITY_CATEGORY, str(out_path)])
        self.assert_false(result.success)
        self.assert_true("directory does not exist" in result.message)
        self.assert_false(out_path.exists(), "No partial file should be left behind")

    def _test_cli_export_zero_rows_header_only(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service)
        out_path = self._temp_dir() / "zero_rows.csv"
        result = module.execute("export", [ELECTRICITY_CATEGORY, str(out_path)])
        self.assert_true(result.success, result.message)
        self.assert_true("Exported 0 row(s)" in result.message)
        lines = out_path.read_text(encoding="utf-8").splitlines()
        self.assert_equal(len(lines), 1)

    def _test_cli_export_overwrite_existing_file(self) -> None:
        service = self._build_service()
        self._seed_electricity_points(service, [("10", "kWh", "2026-01-01T00:00:00+00:00")])
        module = PersonalDataModule(service)
        out_path = self._temp_dir() / "overwrite.csv"
        out_path.write_text("stale content that must be replaced\n", encoding="utf-8")
        result = module.execute("export", [ELECTRICITY_CATEGORY, str(out_path)])
        self.assert_true(result.success, result.message)
        text = out_path.read_text(encoding="utf-8")
        self.assert_false("stale content" in text)
        self.assert_true("id,source_id,category" in text)

    def _test_cli_export_windows_style_path_with_spaces(self) -> None:
        service = self._build_service()
        self._seed_electricity_points(service, [("10", "kWh", "2026-01-01T00:00:00+00:00")])
        module = PersonalDataModule(service)
        spaced_dir = self._temp_dir() / "AI Workspace" / "jarvis exports"
        spaced_dir.mkdir(parents=True)
        out_path = spaced_dir / "electricity export.csv"
        result = module.execute("export", [ELECTRICITY_CATEGORY, str(out_path)])
        self.assert_true(result.success, result.message)
        self.assert_true(out_path.exists())
        self.assert_true("Exported 1 row(s)" in result.message)

    def _test_cli_export_default_mode_is_raw(self) -> None:
        service = self._build_service()
        self._seed_electricity_points(service, [("10", "kWh", "2026-01-01T00:00:00+00:00")])
        module = PersonalDataModule(service)
        out_path = self._temp_dir() / "default_mode.csv"
        module.execute("export", [ELECTRICITY_CATEGORY, str(out_path)])
        header = out_path.read_text(encoding="utf-8").splitlines()[0]
        self.assert_equal(header, "id,source_id,category,timestamp,value,unit,collected_at")

    # ---------- CLI: chart ----------

    def _test_cli_chart_end_to_end(self) -> None:
        service = self._build_service()
        self._seed_electricity_points(
            service,
            [
                ("10", "kWh", "2026-01-01T00:00:00+00:00"),
                ("20", "kWh", "2026-01-02T00:00:00+00:00"),
            ],
        )
        module = PersonalDataModule(service)
        result = module.execute("chart", [ELECTRICITY_CATEGORY])
        self.assert_true(result.success, result.message)
        self.assert_true("2026-01-01" in result.message)
        self.assert_true("2026-01-02" in result.message)

    def _test_cli_chart_empty(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service)
        result = module.execute("chart", [ELECTRICITY_CATEGORY])
        self.assert_true(result.success, result.message)
        self.assert_true("(empty)" in result.message)

    def _test_cli_chart_invalid_bucket(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service)
        result = module.execute(
            "chart", [ELECTRICITY_CATEGORY, "2026-01-01", "2026-01-02", "fortnight"]
        )
        self.assert_false(result.success)
        self.assert_equal(result.message, "bucket must be one of: day, week, month.")

    # ---------- Date/time semantics ----------

    def _test_date_handling_bare_date(self) -> None:
        # A bare "YYYY-MM-DD" bound resolves to midnight UTC on that date
        # (the existing `_parse_optional_datetime` behavior, reused
        # unchanged) -- so a point later the same day falls outside a bare
        # date used as `end`. Two points confirm both directions: the
        # midnight-exact point is included (inclusive `end`), the
        # afternoon point on the same calendar day is correctly excluded.
        service = self._build_service()
        self._seed_electricity_points(
            service,
            [
                ("10", "kWh", "2026-01-01T00:00:00+00:00"),
                ("20", "kWh", "2026-01-01T12:00:00+00:00"),
            ],
        )
        module = PersonalDataModule(service)
        result = module.execute("report", [ELECTRICITY_CATEGORY, "2026-01-01", "2026-01-01"])
        self.assert_true(result.success, result.message)
        self.assert_true("Count: 1" in result.message)
        self.assert_true("Sum: 10.0" in result.message)

    def _test_date_handling_inclusive_bounds(self) -> None:
        service = self._build_service()
        self._seed_electricity_points(
            service,
            [
                ("10", "kWh", "2026-01-01T00:00:00+00:00"),
                ("20", "kWh", "2026-01-02T00:00:00+00:00"),
            ],
        )
        module = PersonalDataModule(service)
        # end == the second point's exact timestamp -> must be included (inclusive).
        result = module.execute(
            "report", [ELECTRICITY_CATEGORY, "2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00"]
        )
        self.assert_true("Count: 2" in result.message)

    def _test_date_handling_start_equals_end(self) -> None:
        service = self._build_service()
        self._seed_electricity_points(
            service,
            [
                ("10", "kWh", "2026-01-01T00:00:00+00:00"),
                ("20", "kWh", "2026-01-02T00:00:00+00:00"),
            ],
        )
        module = PersonalDataModule(service)
        result = module.execute(
            "report", [ELECTRICITY_CATEGORY, "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00+00:00"]
        )
        self.assert_true("Count: 1" in result.message)

    # ---------- Consent/read behavior (EP095_DESIGN.md §11) ----------

    def _test_historical_data_readable_after_category_disabled(self) -> None:
        directory = self._temp_dir()
        # Collect while the category IS in enabled_categories...
        service = self._build_service_in(directory, enabled_categories=[ELECTRICITY_CATEGORY])
        self._seed_electricity_points(service, [("10", "kWh", "2026-01-01T00:00:00+00:00")])
        module = PersonalDataModule(service)
        before = module.execute("report", [ELECTRICITY_CATEGORY])
        self.assert_true("Count: 1" in before.message)

        # ...then build a second service pointed at the SAME on-disk storage
        # (same directory -> same storage_root) but with the category
        # removed from enabled_categories, and confirm the already-collected
        # point is still visible to report/export/chart -- this is existing,
        # corrected EP-092 read-path behavior (§11), not something EP-095
        # may "fix" by adding a new read-side filter.
        disabled_service = self._build_service_in(directory, enabled_categories=[])
        after_module = PersonalDataModule(disabled_service)
        after = after_module.execute("report", [ELECTRICITY_CATEGORY])
        self.assert_true(after.success, after.message)
        self.assert_true(
            "Count: 1" in after.message,
            "Historical data must remain readable after a category is removed "
            "from enabled_categories -- report/export/chart never add a new "
            "read-side consent filter (EP095_DESIGN.md §11).",
        )
        chart_after = after_module.execute("chart", [ELECTRICITY_CATEGORY])
        self.assert_true("2026-01-01" in chart_after.message)
        export_path = self._temp_dir() / "still_readable.csv"
        export_after = after_module.execute("export", [ELECTRICITY_CATEGORY, str(export_path)])
        self.assert_true("Exported 1 row(s)" in export_after.message)

    def _test_subsystem_disabled_yields_empty_for_all_three_actions(self) -> None:
        directory = self._temp_dir()
        service = self._build_service_in(directory, enabled_categories=[ELECTRICITY_CATEGORY])
        self._seed_electricity_points(service, [("10", "kWh", "2026-01-01T00:00:00+00:00")])

        # A second service, same on-disk storage, with the top-level kill
        # switch off -- built via the public Config/PersonalDataService API,
        # exactly as an operator flipping 'personal_data.enabled: false' in
        # config/config.yaml and restarting Jarvis would produce.
        disabled_config = _write_config(
            directory, enabled_categories=[ELECTRICITY_CATEGORY], enabled=False
        )
        disabled_service = PersonalDataService(config=disabled_config)
        module = PersonalDataModule(disabled_service)

        report_result = module.execute("report", [ELECTRICITY_CATEGORY])
        self.assert_true(report_result.success, report_result.message)
        self.assert_true("(empty)" in report_result.message)

        chart_result = module.execute("chart", [ELECTRICITY_CATEGORY])
        self.assert_true(chart_result.success, chart_result.message)
        self.assert_true("(empty)" in chart_result.message)

        raw_export_path = self._temp_dir() / "disabled_raw.csv"
        raw_export = module.execute("export", [ELECTRICITY_CATEGORY, str(raw_export_path)])
        self.assert_true(raw_export.success, raw_export.message)
        self.assert_equal(len(raw_export_path.read_text(encoding="utf-8").splitlines()), 1)

        report_export_path = self._temp_dir() / "disabled_report.csv"
        report_export = module.execute(
            "export",
            [ELECTRICITY_CATEGORY, str(report_export_path), "2000-01-01", "2030-01-01", "report"],
        )
        self.assert_true(report_export.success, report_export.message)
        self.assert_equal(len(report_export_path.read_text(encoding="utf-8").splitlines()), 1)

    # ---------- Architecture compliance ----------

    def _test_module_never_imports_forbidden_symbols(self) -> None:
        """personal_data_module.py never imports the manager/provider/persistence/registry.

        Re-verifies EP-093's own architecture-compliance check still
        holds after EP-095's additions (EP095_DESIGN.md §8's layering
        rule -- PersonalDataModule still speaks only to
        PersonalDataService/PersonalDataReportService).
        """
        forbidden_names = (
            "PersonalDataManager",
            "PersonalDataProvider",
            "PersonalDataPersistence",
            "PersonalDataRegistry",
        )
        tree = ast.parse(inspect.getsource(personal_data_module_module))
        imported_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported_names.extend(alias.name for alias in node.names)
        for forbidden in forbidden_names:
            self.assert_true(
                forbidden not in imported_names,
                f"personal_data_module.py must not import '{forbidden}'",
            )

    def _test_report_service_never_imports_forbidden_symbols(self) -> None:
        """personal_data_report_service.py never imports the manager/provider/persistence/registry.

        Per EP095_DESIGN.md §8's layering rule: PersonalDataReportService
        consumes only already-obtained PersonalDataPoint values.
        """
        forbidden_names = (
            "PersonalDataManager",
            "PersonalDataProvider",
            "PersonalDataPersistence",
            "PersonalDataRegistry",
        )
        tree = ast.parse(inspect.getsource(report_service_module))
        imported_names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported_names.extend(alias.name for alias in node.names)
        for forbidden in forbidden_names:
            self.assert_true(
                forbidden not in imported_names,
                f"personal_data_report_service.py must not import '{forbidden}'",
            )

    def _test_report_service_never_references_command_result(self) -> None:
        """personal_data_report_service.py never constructs/references CommandResult.

        Per EP095_DESIGN.md §7/§10: CommandResult construction remains
        exclusively PersonalDataModule's responsibility.
        """
        tree = ast.parse(inspect.getsource(report_service_module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                self.assert_true(
                    node.id != "CommandResult",
                    "personal_data_report_service.py must never reference CommandResult",
                )
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    self.assert_true(
                        alias.name != "CommandResult",
                        "personal_data_report_service.py must never import CommandResult",
                    )
