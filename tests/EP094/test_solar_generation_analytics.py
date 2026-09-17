"""Real engineering tests for EP-094 - Solar Generation Analytics.

Builds real `SolarCsvSource`/`PersonalDataModule`/`PersonalDataManager`/
`JsonlPersonalDataProvider` instances -- composed with real, temporary-
directory-backed files and a real `Config` -- and drives them exactly
as a caller would, no mocked internals, matching every other EP's test
suite in this project (in particular `tests/EP093/
test_electricity_gas_monitoring.py`, whose structure and lessons this
suite reuses directly).

EP-094 consumes EP-092's Personal Data Collection Framework exclusively
through the existing `PersonalDataSource` contract (EP093_DESIGN.md
§6.2, Design A -- reused unmodified, no separate acquisition-provider
abstraction). This suite covers:

1. `append_solar_reading`/`import_solar_csv`: manual-entry and CSV
   validation and local-log writing, including finite-value
   validation applied from day one (the EP093-AUDIT-001 lesson).
2. `SolarCsvSource.collect()`: reading the local log back, malformed-
   line tolerance, and the idempotent "return everything, let EP-092
   dedupe" behavior.
3. Full integration through a real `PersonalDataManager` +
   `JsonlPersonalDataProvider`: registration, collection, EP-092's
   consent gate, and dedup across repeated collection.
4. `PersonalDataModule`, generalized for a third, independently-
   toggleable category (EP094_DESIGN.md §4/§11): every CLI action for
   solar, the per-category `enabled_categories` gate (verifying
   enabling one domain group does not enable another), and a
   regression check that electricity/gas actions still work correctly
   after the constructor generalization.
5. Architecture compliance: `personal_data_module.py` never imports
   `PersonalDataManager`/`PersonalDataProvider`/
   `PersonalDataPersistence`/`PersonalDataRegistry` or any concrete
   `PersonalDataSource` subclass; `solar_source.py` never imports
   `CommandResult`.
"""

from __future__ import annotations

import ast
import inspect
import tempfile
from pathlib import Path

from src.core.config import Config
from src.core.personal_data import (
    JsonlPersonalDataProvider,
    PersonalDataManager,
    PersonalDataRegistry,
)
from src.core.personal_data.sources import electricity_source as electricity_source_module
from src.core.personal_data.sources import gas_source as gas_source_module
from src.core.personal_data.sources import solar_source as solar_source_module
from src.core.personal_data.sources.electricity_source import ElectricityCsvSource
from src.core.personal_data.sources.gas_source import GasCsvSource
from src.core.personal_data.sources.solar_source import CATEGORY as SOLAR_CATEGORY
from src.core.personal_data.sources.solar_source import SOURCE_ID as SOLAR_SOURCE_ID
from src.core.personal_data.sources.solar_source import (
    SolarCsvSource,
    SolarMeterReadingError,
    append_solar_reading,
    import_solar_csv,
)
from src.modules import personal_data_module as personal_data_module_module
from src.modules.personal_data_module import PersonalDataModule
from src.services.personal_data_service import PersonalDataService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry

_ELECTRICITY_CATEGORY = "electricity_consumption"
_GAS_CATEGORY = "gas_consumption"


def _write_config(directory: Path, enabled_categories: list[str] | None = None) -> Config:
    """Write a minimal config.yaml (personal_data only) and load it."""
    categories = enabled_categories if enabled_categories is not None else [SOLAR_CATEGORY]
    categories_yaml = "[" + ", ".join(f'"{item}"' for item in categories) + "]"
    storage_root = directory / "personal_data"
    # Single-quoted YAML scalar: backslashes are literal here (unlike in a
    # double-quoted scalar, where PyYAML treats "\U"/"\u"/etc. as escape
    # sequences), so a Windows Path's native "C:\Users\...\personal_data"
    # form parses correctly. A literal single quote (never present in a
    # filesystem path) would need doubling per YAML's single-quote rule.
    storage_root_yaml = str(storage_root).replace("'", "''")
    config_path = directory / "config.yaml"
    config_path.write_text(
        "personal_data:\n"
        "  enabled: true\n"
        f"  enabled_categories: {categories_yaml}\n"
        f"  storage_root: '{storage_root_yaml}'\n",
        encoding="utf-8",
    )
    return Config(config_path).load()


@TestRegistry.register
class SolarGenerationAnalyticsTest(BaseTest):
    """Real tests covering EP-094's Solar Generation Analytics."""

    NAME = "EP094"

    def run(self):
        """Execute every Solar Generation Analytics check and return the result."""
        # Manual entry
        self._test_append_solar_reading_valid()
        self._test_append_solar_reading_rejects_bad_value()
        self._test_append_solar_reading_rejects_empty_unit()
        self._test_append_solar_reading_rejects_bad_timestamp()
        self._test_reject_nonfinite_manual_solar()

        # CSV import
        self._test_import_solar_csv_valid_rows()
        self._test_import_csv_skips_malformed_row_keeps_others()
        self._test_import_csv_missing_file_raises()
        self._test_import_csv_missing_required_column_raises()
        self._test_import_csv_meter_id_disambiguates_source_id()
        self._test_reject_nonfinite_csv_row_not_persisted()
        self._test_import_csv_crlf_line_endings()
        self._test_import_csv_bom_prefixed_file()

        # Source collect()
        self._test_source_collect_empty_when_no_log()
        self._test_source_collect_reads_back_appended_readings()
        self._test_source_collect_skips_malformed_log_line()
        self._test_source_category_and_source_id()

        # Full EP-092 integration
        self._test_integration_register_collect_query_round_trip()
        self._test_integration_repeated_collect_is_idempotent()
        self._test_integration_consent_gate_blocks_disabled_category()

        # CLI module
        self._test_cli_help_and_unknown_action()
        self._test_cli_status()
        self._test_cli_record_reading_disabled_by_default()
        self._test_cli_record_reading_end_to_end()
        self._test_cli_record_reading_unknown_category()
        self._test_cli_record_reading_missing_args()
        self._test_cli_import_csv_end_to_end()
        self._test_cli_import_csv_all_invalid_reports_failure()
        self._test_cli_import_csv_mixed_valid_invalid_reports_success()
        self._test_cli_collect_and_query()

        # Generalized per-category enable gate (EP094_DESIGN.md §4/§11)
        self._test_enabling_solar_does_not_enable_electricity_gas()
        self._test_electricity_gas_still_work_after_generalization()

        # Architecture compliance
        self._test_module_never_imports_forbidden_symbols()
        self._test_solar_source_never_imports_command_result()

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

    def _solar_log_path(self) -> Path:
        return self._temp_dir() / "solar_generation.jsonl"

    def _write_csv(self, rows: list[str], header: str = "date,value,unit,meter_id") -> Path:
        path = self._temp_dir() / "readings.csv"
        path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
        return path

    def _build_manager(self, tmp: Path, enabled_categories: list[str] | None = None):
        config = _write_config(tmp, enabled_categories)
        provider = JsonlPersonalDataProvider(config)
        categories = enabled_categories if enabled_categories is not None else [SOLAR_CATEGORY]
        return PersonalDataManager(
            registry=PersonalDataRegistry(), provider=provider, enabled_categories=frozenset(categories)
        )

    def _build_service(self, enabled_categories: list[str] | None = None) -> PersonalDataService:
        tmp = self._temp_dir()
        config = _write_config(tmp, enabled_categories)
        return PersonalDataService(config=config)

    # ---------- Manual entry ----------

    def _test_append_solar_reading_valid(self) -> None:
        log_path = self._solar_log_path()
        point = append_solar_reading(value="4.2", unit="kWh", log_path=log_path)
        self.assert_equal(point.category, SOLAR_CATEGORY)
        self.assert_equal(point.source_id, SOLAR_SOURCE_ID)
        self.assert_equal(point.value, 4.2)
        self.assert_true(log_path.exists())

    def _test_append_solar_reading_rejects_bad_value(self) -> None:
        log_path = self._solar_log_path()
        try:
            append_solar_reading(value="not-a-number", unit="kWh", log_path=log_path)
        except ValueError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Non-numeric value should raise ValueError")

    def _test_append_solar_reading_rejects_empty_unit(self) -> None:
        log_path = self._solar_log_path()
        try:
            append_solar_reading(value="1.0", unit="   ", log_path=log_path)
        except ValueError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Empty unit should raise ValueError")

    def _test_append_solar_reading_rejects_bad_timestamp(self) -> None:
        log_path = self._solar_log_path()
        try:
            append_solar_reading(value="1.0", unit="kWh", timestamp="not-a-date", log_path=log_path)
        except ValueError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Malformed timestamp should raise ValueError")

    _NONFINITE_VALUES = ("nan", "NaN", "inf", "Infinity", "-inf", "-Infinity")

    def _test_reject_nonfinite_manual_solar(self) -> None:
        for bad_value in self._NONFINITE_VALUES:
            log_path = self._solar_log_path()
            try:
                append_solar_reading(value=bad_value, unit="kWh", log_path=log_path)
            except ValueError:
                self.result.add_pass()
            else:
                self.assert_true(False, f"value={bad_value!r} should raise ValueError")
            self.assert_false(
                log_path.exists() and log_path.read_text(encoding="utf-8").strip() != "",
                f"A rejected value ({bad_value!r}) must never reach the local log",
            )

    # ---------- CSV import ----------

    def _test_import_solar_csv_valid_rows(self) -> None:
        csv_path = self._write_csv(["2026-01-01,4.2,kWh,", "2026-01-02,5.1,kWh,inverter1"])
        log_path = self._solar_log_path()
        imported, skipped = import_solar_csv(csv_path, log_path=log_path)
        self.assert_equal(imported, 2)
        self.assert_equal(skipped, [])
        source = SolarCsvSource(log_path=log_path)
        points = source.collect()
        self.assert_equal(len(points), 2)
        self.assert_true(any(point.raw.get("meter_id") == "inverter1" for point in points))

    def _test_import_csv_skips_malformed_row_keeps_others(self) -> None:
        csv_path = self._write_csv(
            ["2026-01-01,4.2,kWh,", "not-a-date,bad,kWh,", "2026-01-03,5.0,kWh,"]
        )
        log_path = self._solar_log_path()
        imported, skipped = import_solar_csv(csv_path, log_path=log_path)
        self.assert_equal(imported, 2)
        self.assert_equal(len(skipped), 1)
        self.assert_true("row 3" in skipped[0])

    def _test_import_csv_missing_file_raises(self) -> None:
        missing_path = self._temp_dir() / "does_not_exist.csv"
        try:
            import_solar_csv(missing_path, log_path=self._solar_log_path())
        except SolarMeterReadingError:
            self.result.add_pass()
        else:
            self.assert_true(False, "A missing CSV file should raise SolarMeterReadingError")

    def _test_import_csv_missing_required_column_raises(self) -> None:
        csv_path = self._write_csv(["1.0,kWh"], header="value,unit")
        try:
            import_solar_csv(csv_path, log_path=self._solar_log_path())
        except SolarMeterReadingError:
            self.result.add_pass()
        else:
            self.assert_true(False, "A CSV missing 'date' should raise SolarMeterReadingError")

    def _test_import_csv_meter_id_disambiguates_source_id(self) -> None:
        csv_path = self._write_csv(["2026-01-01,1.0,kWh,inverter-a", "2026-01-01,2.0,kWh,inverter-b"])
        log_path = self._solar_log_path()
        import_solar_csv(csv_path, log_path=log_path)
        source = SolarCsvSource(log_path=log_path)
        points = source.collect()
        source_ids = {point.source_id for point in points}
        self.assert_equal(
            source_ids, {f"{SOLAR_SOURCE_ID}:inverter-a", f"{SOLAR_SOURCE_ID}:inverter-b"}
        )

    def _test_reject_nonfinite_csv_row_not_persisted(self) -> None:
        csv_path = self._write_csv(
            ["2026-01-01,4.2,kWh,", "2026-01-02,nan,kWh,", "2026-01-03,Infinity,kWh,"]
        )
        log_path = self._solar_log_path()
        imported, skipped = import_solar_csv(csv_path, log_path=log_path)
        self.assert_equal(imported, 1, "Only the one genuinely finite row should be imported")
        self.assert_equal(len(skipped), 2, "Both non-finite rows should be reported as skipped")
        source = SolarCsvSource(log_path=log_path)
        points = source.collect()
        self.assert_equal(len(points), 1)

    def _test_import_csv_crlf_line_endings(self) -> None:
        csv_path = self._temp_dir() / "crlf.csv"
        csv_path.write_bytes(
            b"date,value,unit,meter_id\r\n2026-01-01,4.2,kWh,\r\n2026-01-02,5.1,kWh,inverter1\r\n"
        )
        log_path = self._solar_log_path()
        imported, skipped = import_solar_csv(csv_path, log_path=log_path)
        self.assert_equal(imported, 2)
        self.assert_equal(skipped, [])

    def _test_import_csv_bom_prefixed_file(self) -> None:
        csv_path = self._temp_dir() / "bom.csv"
        csv_path.write_bytes(b"\xef\xbb\xbfdate,value,unit\r\n2026-01-01,4.2,kWh\r\n")
        log_path = self._solar_log_path()
        imported, skipped = import_solar_csv(csv_path, log_path=log_path)
        self.assert_equal(imported, 1)
        self.assert_equal(skipped, [])

    # ---------- Source collect() ----------

    def _test_source_collect_empty_when_no_log(self) -> None:
        source = SolarCsvSource(log_path=self._solar_log_path())
        self.assert_equal(source.collect(), [])

    def _test_source_collect_reads_back_appended_readings(self) -> None:
        log_path = self._solar_log_path()
        append_solar_reading(value="1.0", unit="kWh", log_path=log_path)
        append_solar_reading(value="2.0", unit="kWh", log_path=log_path)
        source = SolarCsvSource(log_path=log_path)
        points = source.collect()
        self.assert_equal(len(points), 2)

    def _test_source_collect_skips_malformed_log_line(self) -> None:
        log_path = self._solar_log_path()
        append_solar_reading(value="1.0", unit="kWh", log_path=log_path)
        with log_path.open("a", encoding="utf-8") as file:
            file.write("not valid json\n")
        source = SolarCsvSource(log_path=log_path)
        points = source.collect()
        self.assert_equal(len(points), 1)

    def _test_source_category_and_source_id(self) -> None:
        solar = SolarCsvSource()
        self.assert_equal(solar.category, SOLAR_CATEGORY)
        self.assert_equal(solar.source_id, SOLAR_SOURCE_ID)

    # ---------- Full EP-092 integration ----------

    def _test_integration_register_collect_query_round_trip(self) -> None:
        tmp = self._temp_dir()
        log_path = tmp / "solar_generation.jsonl"
        append_solar_reading(value="4.2", unit="kWh", log_path=log_path)
        manager = self._build_manager(tmp)
        manager.register_source(SolarCsvSource(log_path=log_path))
        stored = manager.collect_from(SOLAR_SOURCE_ID)
        self.assert_equal(stored, 1)
        self.assert_equal(len(manager.query(SOLAR_CATEGORY)), 1)

    def _test_integration_repeated_collect_is_idempotent(self) -> None:
        tmp = self._temp_dir()
        log_path = tmp / "solar_generation.jsonl"
        append_solar_reading(value="4.2", unit="kWh", timestamp="2026-01-01", log_path=log_path)
        manager = self._build_manager(tmp)
        manager.register_source(SolarCsvSource(log_path=log_path))
        first = manager.collect_from(SOLAR_SOURCE_ID)
        second = manager.collect_from(SOLAR_SOURCE_ID)
        self.assert_equal(first, 1)
        self.assert_equal(second, 0, "Re-collecting the same log entry must not duplicate it")
        self.assert_equal(len(manager.query(SOLAR_CATEGORY)), 1)

    def _test_integration_consent_gate_blocks_disabled_category(self) -> None:
        tmp = self._temp_dir()
        log_path = tmp / "solar_generation.jsonl"
        append_solar_reading(value="4.2", unit="kWh", log_path=log_path)
        manager = self._build_manager(tmp, enabled_categories=[_ELECTRICITY_CATEGORY])  # solar NOT enabled
        manager.register_source(SolarCsvSource(log_path=log_path))
        stored = manager.collect_from(SOLAR_SOURCE_ID)
        self.assert_equal(stored, 0, "A non-enabled category must not be stored")
        self.assert_equal(manager.query(SOLAR_CATEGORY), [])

    # ---------- CLI module ----------

    def _test_cli_help_and_unknown_action(self) -> None:
        module = PersonalDataModule(self._build_service())
        self.assert_equal(module.name, "personal_data")
        help_result = module.execute("help", [])
        self.assert_true(help_result.success)
        unknown_result = module.execute("does-not-exist", [])
        self.assert_false(unknown_result.success)

    def _test_cli_status(self) -> None:
        module = PersonalDataModule(self._build_service(), enabled_categories=frozenset({SOLAR_CATEGORY}))
        result = module.execute("status", [])
        self.assert_true(result.success)
        self.assert_true("Acquisition Enabled For" in result.message)
        self.assert_true(SOLAR_CATEGORY in result.message)

    def _test_cli_record_reading_disabled_by_default(self) -> None:
        module = PersonalDataModule(self._build_service())  # enabled_categories defaults empty
        result = module.execute("record-reading", [SOLAR_CATEGORY, "1.0", "kWh"])
        self.assert_false(result.success)
        self.assert_true("disabled" in result.message.lower())

    def _test_cli_record_reading_end_to_end(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service, enabled_categories=frozenset({SOLAR_CATEGORY}))
        log_path = self._solar_log_path()
        original_default = solar_source_module.DEFAULT_LOG_PATH
        solar_source_module.DEFAULT_LOG_PATH = log_path
        try:
            service.register_source(SolarCsvSource(log_path=log_path))
            result = module.execute("record-reading", [SOLAR_CATEGORY, "4.2", "kWh"])
        finally:
            solar_source_module.DEFAULT_LOG_PATH = original_default
        self.assert_true(result.success, result.message)
        points = service.query(SOLAR_CATEGORY)
        self.assert_equal(len(points), 1)

    def _test_cli_record_reading_unknown_category(self) -> None:
        module = PersonalDataModule(self._build_service(), enabled_categories=frozenset({SOLAR_CATEGORY}))
        result = module.execute("record-reading", ["not_a_real_category", "1.0", "kWh"])
        self.assert_false(result.success)

    def _test_cli_record_reading_missing_args(self) -> None:
        module = PersonalDataModule(self._build_service(), enabled_categories=frozenset({SOLAR_CATEGORY}))
        result = module.execute("record-reading", [SOLAR_CATEGORY, "1.0"])
        self.assert_false(result.success)
        self.assert_true("Usage" in result.message)

    def _test_cli_import_csv_end_to_end(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service, enabled_categories=frozenset({SOLAR_CATEGORY}))
        csv_path = self._write_csv(["2026-01-01,4.2,kWh,", "2026-01-02,5.1,kWh,"])
        log_path = self._solar_log_path()
        original_default = solar_source_module.DEFAULT_LOG_PATH
        solar_source_module.DEFAULT_LOG_PATH = log_path
        try:
            service.register_source(SolarCsvSource(log_path=log_path))
            result = module.execute("import-csv", [SOLAR_CATEGORY, str(csv_path)])
        finally:
            solar_source_module.DEFAULT_LOG_PATH = original_default
        self.assert_true(result.success, result.message)
        self.assert_true("Imported 2 row(s)" in result.message)
        self.assert_equal(len(service.query(SOLAR_CATEGORY)), 2)

    def _test_cli_import_csv_all_invalid_reports_failure(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service, enabled_categories=frozenset({SOLAR_CATEGORY}))
        csv_path = self._write_csv(["not-a-date,not-a-number,kWh,"])
        log_path = self._solar_log_path()
        original_default = solar_source_module.DEFAULT_LOG_PATH
        solar_source_module.DEFAULT_LOG_PATH = log_path
        try:
            service.register_source(SolarCsvSource(log_path=log_path))
            result = module.execute("import-csv", [SOLAR_CATEGORY, str(csv_path)])
        finally:
            solar_source_module.DEFAULT_LOG_PATH = original_default
        self.assert_false(result.success, "An all-invalid CSV import must report failure")
        self.assert_true("Imported 0 row(s)" in result.message)
        self.assert_equal(len(service.query(SOLAR_CATEGORY)), 0)

    def _test_cli_import_csv_mixed_valid_invalid_reports_success(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service, enabled_categories=frozenset({SOLAR_CATEGORY}))
        csv_path = self._write_csv(["2026-01-01,4.2,kWh,", "not-a-date,bad,kWh,"])
        log_path = self._solar_log_path()
        original_default = solar_source_module.DEFAULT_LOG_PATH
        solar_source_module.DEFAULT_LOG_PATH = log_path
        try:
            service.register_source(SolarCsvSource(log_path=log_path))
            result = module.execute("import-csv", [SOLAR_CATEGORY, str(csv_path)])
        finally:
            solar_source_module.DEFAULT_LOG_PATH = original_default
        self.assert_true(result.success, "A CSV with at least one valid row must report success")
        self.assert_true("Imported 1 row(s)" in result.message)
        self.assert_true("Skipped 1 invalid row(s)" in result.message)
        self.assert_equal(len(service.query(SOLAR_CATEGORY)), 1)

    def _test_cli_collect_and_query(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service)
        missing_args_result = module.execute("collect", [])
        self.assert_false(missing_args_result.success)
        missing_query_args_result = module.execute("query", [])
        self.assert_false(missing_query_args_result.success)
        empty_query_result = module.execute("query", [SOLAR_CATEGORY])
        self.assert_true(empty_query_result.success)
        self.assert_true("(empty)" in empty_query_result.message)

    # ---------- Generalized per-category enable gate ----------

    def _test_enabling_solar_does_not_enable_electricity_gas(self) -> None:
        module = PersonalDataModule(
            self._build_service(), enabled_categories=frozenset({SOLAR_CATEGORY})
        )
        electricity_result = module.execute("record-reading", [_ELECTRICITY_CATEGORY, "1.0", "kWh"])
        gas_result = module.execute("record-reading", [_GAS_CATEGORY, "1.0", "m3"])
        solar_result_check = module._ensure_category_enabled(SOLAR_CATEGORY)
        self.assert_false(electricity_result.success, "Enabling solar must not enable electricity")
        self.assert_false(gas_result.success, "Enabling solar must not enable gas")
        self.assert_true(solar_result_check is None, "Solar itself must remain enabled")

    def _test_electricity_gas_still_work_after_generalization(self) -> None:
        service = self._build_service(enabled_categories=[_ELECTRICITY_CATEGORY, _GAS_CATEGORY])
        module = PersonalDataModule(
            service, enabled_categories=frozenset({_ELECTRICITY_CATEGORY, _GAS_CATEGORY})
        )
        electricity_log = self._temp_dir() / "electricity_consumption.jsonl"
        gas_log = self._temp_dir() / "gas_consumption.jsonl"
        original_electricity_default = electricity_source_module.DEFAULT_LOG_PATH
        original_gas_default = gas_source_module.DEFAULT_LOG_PATH
        electricity_source_module.DEFAULT_LOG_PATH = electricity_log
        gas_source_module.DEFAULT_LOG_PATH = gas_log
        try:
            service.register_source(ElectricityCsvSource(log_path=electricity_log))
            service.register_source(GasCsvSource(log_path=gas_log))
            electricity_result = module.execute(
                "record-reading", [_ELECTRICITY_CATEGORY, "412.5", "kWh"]
            )
            gas_result = module.execute("record-reading", [_GAS_CATEGORY, "10.0", "m3"])
        finally:
            electricity_source_module.DEFAULT_LOG_PATH = original_electricity_default
            gas_source_module.DEFAULT_LOG_PATH = original_gas_default
        self.assert_true(electricity_result.success, electricity_result.message)
        self.assert_true(gas_result.success, gas_result.message)
        self.assert_equal(len(service.query(_ELECTRICITY_CATEGORY)), 1)
        self.assert_equal(len(service.query(_GAS_CATEGORY)), 1)

    # ---------- Architecture compliance ----------

    def _test_module_never_imports_forbidden_symbols(self) -> None:
        """personal_data_module.py never imports the manager/provider/persistence/registry/sources.

        Per EP-093 STEP 1 design §11's layering rule, extended by
        EP-094 (EP094_DESIGN.md §6) to also forbid importing
        `SolarCsvSource`.
        """
        forbidden_names = (
            "PersonalDataManager",
            "PersonalDataProvider",
            "PersonalDataPersistence",
            "PersonalDataRegistry",
            "ElectricityCsvSource",
            "GasCsvSource",
            "SolarCsvSource",
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

    def _test_solar_source_never_imports_command_result(self) -> None:
        """solar_source.py never references CommandResult.

        Per EP-093 STEP 1 design §11, reused unmodified by EP-094:
        acquisition source modules never touch CommandResult directly.
        """
        tree = ast.parse(inspect.getsource(solar_source_module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                self.assert_true(
                    node.id != "CommandResult",
                    "solar_source.py must never reference CommandResult",
                )
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    self.assert_true(
                        alias.name != "CommandResult",
                        "solar_source.py must never import CommandResult",
                    )
