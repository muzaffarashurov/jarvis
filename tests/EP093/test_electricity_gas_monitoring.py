"""Real engineering tests for EP-093 - Electricity & Gas Monitoring.

Builds real `ElectricityCsvSource`/`GasCsvSource`/`PersonalDataModule`/
`PersonalDataManager`/`JsonlPersonalDataProvider` instances -- composed
with real, temporary-directory-backed files and a real `Config` --
and drives them exactly as a caller would, no mocked internals,
matching every other EP's test suite in this project.

EP-093 consumes EP-092's Personal Data Collection Framework exclusively
through the existing `PersonalDataSource` contract (STEP 1 design
§6.2, Design A -- no separate acquisition-provider abstraction). This
suite covers:

1. `append_electricity_reading`/`append_gas_reading`: manual-entry
   validation and local-log writing.
2. `import_electricity_csv`/`import_gas_csv`: canonical CSV parsing,
   validation, malformed-row tolerance, and missing-file/missing-
   column errors.
3. `ElectricityCsvSource`/`GasCsvSource.collect()`: reading the local
   log back, malformed-line tolerance, and the idempotent
   "return everything, let EP-092 dedupe" behavior.
4. Full integration through a real `PersonalDataManager` +
   `JsonlPersonalDataProvider`: registration, collection, EP-092's
   consent gate, and EP-092's dedup guarantee across repeated
   collection.
5. `PersonalDataModule`: every CLI action, including the
   `personal_data_electricity_gas.enabled` gate on
   `record-reading`/`import-csv`.
6. Architecture compliance: `personal_data_module.py` never imports
   `PersonalDataManager`/`PersonalDataProvider`/
   `PersonalDataPersistence`/`PersonalDataRegistry` or either
   `PersonalDataSource` subclass; the source modules never import
   `CommandResult`.
"""

from __future__ import annotations

import ast
import inspect
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.core.config import Config
from src.core.personal_data import (
    JsonlPersonalDataProvider,
    PersonalDataManager,
    PersonalDataRegistry,
)
from src.core.personal_data.sources import electricity_source as electricity_source_module
from src.core.personal_data.sources import gas_source as gas_source_module
from src.core.personal_data.sources.electricity_source import (
    CATEGORY as ELECTRICITY_CATEGORY,
)
from src.core.personal_data.sources.electricity_source import (
    SOURCE_ID as ELECTRICITY_SOURCE_ID,
)
from src.core.personal_data.sources.electricity_source import (
    ElectricityCsvSource,
    ElectricityMeterReadingError,
    append_electricity_reading,
    import_electricity_csv,
)
from src.core.personal_data.sources.gas_source import CATEGORY as GAS_CATEGORY
from src.core.personal_data.sources.gas_source import SOURCE_ID as GAS_SOURCE_ID
from src.core.personal_data.sources.gas_source import (
    GasCsvSource,
    GasMeterReadingError,
    append_gas_reading,
    import_gas_csv,
)
from src.modules import personal_data_module as personal_data_module_module
from src.modules.personal_data_module import PersonalDataModule
from src.services.personal_data_service import PersonalDataService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


def _write_config(directory: Path, enabled_categories: list[str] | None = None) -> Config:
    """Write a minimal config.yaml (personal_data + personal_data_electricity_gas) and load it."""
    categories = enabled_categories if enabled_categories is not None else [
        ELECTRICITY_CATEGORY,
        GAS_CATEGORY,
    ]
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
class ElectricityGasMonitoringTest(BaseTest):
    """Real tests covering EP-093's Electricity & Gas Monitoring."""

    NAME = "EP093"

    def run(self):
        """Execute every Electricity & Gas Monitoring check and return the result."""
        # Manual entry
        self._test_append_electricity_reading_valid()
        self._test_append_electricity_reading_rejects_bad_value()
        self._test_append_electricity_reading_rejects_empty_unit()
        self._test_append_electricity_reading_rejects_bad_timestamp()
        self._test_append_gas_reading_valid()

        # CSV import
        self._test_import_electricity_csv_valid_rows()
        self._test_import_csv_skips_malformed_row_keeps_others()
        self._test_import_csv_missing_file_raises()
        self._test_import_csv_missing_required_column_raises()
        self._test_import_csv_meter_id_disambiguates_source_id()

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
        self._test_cli_collect_and_query()

        # EP093-AUDIT-001 regression: non-finite values must be rejected
        self._test_reject_nonfinite_manual_electricity()
        self._test_reject_nonfinite_manual_gas()
        self._test_reject_nonfinite_csv_row_not_persisted()

        # EP093-AUDIT-002 regression: import-csv success semantics
        self._test_import_csv_all_invalid_reports_failure()
        self._test_import_csv_mixed_valid_invalid_reports_success()

        # EP093-AUDIT-006: CRLF / BOM regression coverage
        self._test_import_csv_crlf_line_endings()
        self._test_import_csv_bom_prefixed_file()

        # Architecture compliance
        self._test_module_never_imports_forbidden_symbols()
        self._test_sources_never_import_command_result()

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

    def _electricity_log_path(self) -> Path:
        return self._temp_dir() / "electricity_consumption.jsonl"

    def _gas_log_path(self) -> Path:
        return self._temp_dir() / "gas_consumption.jsonl"

    def _write_csv(self, rows: list[str], header: str = "date,value,unit,meter_id") -> Path:
        path = self._temp_dir() / "readings.csv"
        path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
        return path

    def _build_manager(self, tmp: Path, enabled_categories: list[str] | None = None):
        config = _write_config(tmp, enabled_categories)
        provider = JsonlPersonalDataProvider(config)
        categories = enabled_categories if enabled_categories is not None else [
            ELECTRICITY_CATEGORY,
            GAS_CATEGORY,
        ]
        return PersonalDataManager(
            registry=PersonalDataRegistry(), provider=provider, enabled_categories=frozenset(categories)
        )

    def _build_service(self, enabled_categories: list[str] | None = None) -> PersonalDataService:
        tmp = self._temp_dir()
        config = _write_config(tmp, enabled_categories)
        return PersonalDataService(config=config)

    # ---------- Manual entry ----------

    def _test_append_electricity_reading_valid(self) -> None:
        log_path = self._electricity_log_path()
        point = append_electricity_reading(value="412.5", unit="kWh", log_path=log_path)
        self.assert_equal(point.category, ELECTRICITY_CATEGORY)
        self.assert_equal(point.source_id, ELECTRICITY_SOURCE_ID)
        self.assert_equal(point.value, 412.5)
        self.assert_true(log_path.exists())

    def _test_append_electricity_reading_rejects_bad_value(self) -> None:
        log_path = self._electricity_log_path()
        try:
            append_electricity_reading(value="not-a-number", unit="kWh", log_path=log_path)
        except ValueError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Non-numeric value should raise ValueError")

    def _test_append_electricity_reading_rejects_empty_unit(self) -> None:
        log_path = self._electricity_log_path()
        try:
            append_electricity_reading(value="1.0", unit="   ", log_path=log_path)
        except ValueError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Empty unit should raise ValueError")

    def _test_append_electricity_reading_rejects_bad_timestamp(self) -> None:
        log_path = self._electricity_log_path()
        try:
            append_electricity_reading(value="1.0", unit="kWh", timestamp="not-a-date", log_path=log_path)
        except ValueError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Malformed timestamp should raise ValueError")

    def _test_append_gas_reading_valid(self) -> None:
        log_path = self._gas_log_path()
        point = append_gas_reading(value="10.2", unit="m3", timestamp="2026-01-01", log_path=log_path)
        self.assert_equal(point.category, GAS_CATEGORY)
        self.assert_equal(point.source_id, GAS_SOURCE_ID)
        self.assert_equal(point.timestamp, datetime(2026, 1, 1, tzinfo=timezone.utc))

    # ---------- CSV import ----------

    def _test_import_electricity_csv_valid_rows(self) -> None:
        csv_path = self._write_csv(["2026-01-01,412.5,kWh,", "2026-01-02,418.2,kWh,main"])
        log_path = self._electricity_log_path()
        imported, skipped = import_electricity_csv(csv_path, log_path=log_path)
        self.assert_equal(imported, 2)
        self.assert_equal(skipped, [])
        source = ElectricityCsvSource(log_path=log_path)
        points = source.collect()
        self.assert_equal(len(points), 2)
        self.assert_true(any(point.raw.get("meter_id") == "main" for point in points))

    def _test_import_csv_skips_malformed_row_keeps_others(self) -> None:
        csv_path = self._write_csv(
            ["2026-01-01,412.5,kWh,", "not-a-date,bad,kWh,", "2026-01-03,420.0,kWh,"]
        )
        log_path = self._electricity_log_path()
        imported, skipped = import_electricity_csv(csv_path, log_path=log_path)
        self.assert_equal(imported, 2)
        self.assert_equal(len(skipped), 1)
        self.assert_true("row 3" in skipped[0])

    def _test_import_csv_missing_file_raises(self) -> None:
        missing_path = self._temp_dir() / "does_not_exist.csv"
        try:
            import_electricity_csv(missing_path, log_path=self._electricity_log_path())
        except ElectricityMeterReadingError:
            self.result.add_pass()
        else:
            self.assert_true(False, "A missing CSV file should raise ElectricityMeterReadingError")

    def _test_import_csv_missing_required_column_raises(self) -> None:
        csv_path = self._write_csv(["1.0,kWh"], header="value,unit")
        try:
            import_gas_csv(csv_path, log_path=self._gas_log_path())
        except GasMeterReadingError:
            self.result.add_pass()
        else:
            self.assert_true(False, "A CSV missing 'date' should raise GasMeterReadingError")

    def _test_import_csv_meter_id_disambiguates_source_id(self) -> None:
        csv_path = self._write_csv(["2026-01-01,1.0,kWh,garage", "2026-01-01,2.0,kWh,main"])
        log_path = self._electricity_log_path()
        import_electricity_csv(csv_path, log_path=log_path)
        source = ElectricityCsvSource(log_path=log_path)
        points = source.collect()
        source_ids = {point.source_id for point in points}
        self.assert_equal(source_ids, {f"{ELECTRICITY_SOURCE_ID}:garage", f"{ELECTRICITY_SOURCE_ID}:main"})

    # ---------- Source collect() ----------

    def _test_source_collect_empty_when_no_log(self) -> None:
        source = ElectricityCsvSource(log_path=self._electricity_log_path())
        self.assert_equal(source.collect(), [])

    def _test_source_collect_reads_back_appended_readings(self) -> None:
        log_path = self._gas_log_path()
        append_gas_reading(value="1.0", unit="m3", log_path=log_path)
        append_gas_reading(value="2.0", unit="m3", log_path=log_path)
        source = GasCsvSource(log_path=log_path)
        points = source.collect()
        self.assert_equal(len(points), 2)

    def _test_source_collect_skips_malformed_log_line(self) -> None:
        log_path = self._electricity_log_path()
        append_electricity_reading(value="1.0", unit="kWh", log_path=log_path)
        with log_path.open("a", encoding="utf-8") as file:
            file.write("not valid json\n")
        source = ElectricityCsvSource(log_path=log_path)
        points = source.collect()
        self.assert_equal(len(points), 1)

    def _test_source_category_and_source_id(self) -> None:
        electricity = ElectricityCsvSource()
        gas = GasCsvSource()
        self.assert_equal(electricity.category, ELECTRICITY_CATEGORY)
        self.assert_equal(electricity.source_id, ELECTRICITY_SOURCE_ID)
        self.assert_equal(gas.category, GAS_CATEGORY)
        self.assert_equal(gas.source_id, GAS_SOURCE_ID)

    # ---------- Full EP-092 integration ----------

    def _test_integration_register_collect_query_round_trip(self) -> None:
        tmp = self._temp_dir()
        log_path = tmp / "electricity_consumption.jsonl"
        append_electricity_reading(value="412.5", unit="kWh", log_path=log_path)
        manager = self._build_manager(tmp)
        manager.register_source(ElectricityCsvSource(log_path=log_path))
        stored = manager.collect_from(ELECTRICITY_SOURCE_ID)
        self.assert_equal(stored, 1)
        self.assert_equal(len(manager.query(ELECTRICITY_CATEGORY)), 1)

    def _test_integration_repeated_collect_is_idempotent(self) -> None:
        tmp = self._temp_dir()
        log_path = tmp / "electricity_consumption.jsonl"
        append_electricity_reading(value="412.5", unit="kWh", timestamp="2026-01-01", log_path=log_path)
        manager = self._build_manager(tmp)
        manager.register_source(ElectricityCsvSource(log_path=log_path))
        first = manager.collect_from(ELECTRICITY_SOURCE_ID)
        second = manager.collect_from(ELECTRICITY_SOURCE_ID)
        self.assert_equal(first, 1)
        self.assert_equal(second, 0, "Re-collecting the same log entry must not duplicate it")
        self.assert_equal(len(manager.query(ELECTRICITY_CATEGORY)), 1)

    def _test_integration_consent_gate_blocks_disabled_category(self) -> None:
        tmp = self._temp_dir()
        log_path = tmp / "gas_consumption.jsonl"
        append_gas_reading(value="1.0", unit="m3", log_path=log_path)
        manager = self._build_manager(tmp, enabled_categories=[ELECTRICITY_CATEGORY])  # gas NOT enabled
        manager.register_source(GasCsvSource(log_path=log_path))
        stored = manager.collect_from(GAS_SOURCE_ID)
        self.assert_equal(stored, 0, "A non-enabled category must not be stored")
        self.assert_equal(manager.query(GAS_CATEGORY), [])

    # ---------- CLI module ----------

    def _test_cli_help_and_unknown_action(self) -> None:
        module = PersonalDataModule(self._build_service())
        self.assert_equal(module.name, "personal_data")
        help_result = module.execute("help", [])
        self.assert_true(help_result.success)
        unknown_result = module.execute("does-not-exist", [])
        self.assert_false(unknown_result.success)

    def _test_cli_status(self) -> None:
        module = PersonalDataModule(self._build_service(), enabled_categories=frozenset({ELECTRICITY_CATEGORY, GAS_CATEGORY}))
        result = module.execute("status", [])
        self.assert_true(result.success)
        self.assert_true("Acquisition Enabled For" in result.message)
        self.assert_true(ELECTRICITY_CATEGORY in result.message)
        self.assert_true(GAS_CATEGORY in result.message)

    def _test_cli_record_reading_disabled_by_default(self) -> None:
        module = PersonalDataModule(self._build_service())  # enabled_categories defaults empty
        result = module.execute("record-reading", [ELECTRICITY_CATEGORY, "1.0", "kWh"])
        self.assert_false(result.success)
        self.assert_true("disabled" in result.message.lower())

    def _test_cli_record_reading_end_to_end(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service, enabled_categories=frozenset({ELECTRICITY_CATEGORY, GAS_CATEGORY}))
        # Point the source's default log path at a temp file for this test by
        # registering our own source instance against the service's manager.
        log_path = self._electricity_log_path()
        original_default = electricity_source_module.DEFAULT_LOG_PATH
        electricity_source_module.DEFAULT_LOG_PATH = log_path
        try:
            service.register_source(ElectricityCsvSource(log_path=log_path))
            result = module.execute("record-reading", [ELECTRICITY_CATEGORY, "412.5", "kWh"])
        finally:
            electricity_source_module.DEFAULT_LOG_PATH = original_default
        self.assert_true(result.success, result.message)
        points = service.query(ELECTRICITY_CATEGORY)
        self.assert_equal(len(points), 1)

    def _test_cli_record_reading_unknown_category(self) -> None:
        module = PersonalDataModule(self._build_service(), enabled_categories=frozenset({ELECTRICITY_CATEGORY, GAS_CATEGORY}))
        result = module.execute("record-reading", ["not_a_real_category", "1.0", "kWh"])
        self.assert_false(result.success)

    def _test_cli_record_reading_missing_args(self) -> None:
        module = PersonalDataModule(self._build_service(), enabled_categories=frozenset({ELECTRICITY_CATEGORY, GAS_CATEGORY}))
        result = module.execute("record-reading", [ELECTRICITY_CATEGORY, "1.0"])
        self.assert_false(result.success)
        self.assert_true("Usage" in result.message)

    def _test_cli_import_csv_end_to_end(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service, enabled_categories=frozenset({ELECTRICITY_CATEGORY, GAS_CATEGORY}))
        csv_path = self._write_csv(["2026-01-01,412.5,kWh,", "2026-01-02,418.2,kWh,"])
        electricity_log_path = self._electricity_log_path()
        original_default = electricity_source_module.DEFAULT_LOG_PATH
        electricity_source_module.DEFAULT_LOG_PATH = electricity_log_path
        try:
            service.register_source(ElectricityCsvSource(log_path=electricity_log_path))
            result = module.execute("import-csv", [ELECTRICITY_CATEGORY, str(csv_path)])
        finally:
            electricity_source_module.DEFAULT_LOG_PATH = original_default
        self.assert_true(result.success, result.message)
        self.assert_true("Imported 2 row(s)" in result.message)
        self.assert_equal(len(service.query(ELECTRICITY_CATEGORY)), 2)

    def _test_cli_collect_and_query(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service)
        missing_args_result = module.execute("collect", [])
        self.assert_false(missing_args_result.success)
        missing_query_args_result = module.execute("query", [])
        self.assert_false(missing_query_args_result.success)
        empty_query_result = module.execute("query", [ELECTRICITY_CATEGORY])
        self.assert_true(empty_query_result.success)
        self.assert_true("(empty)" in empty_query_result.message)

    # ---------- EP093-AUDIT-001 regression: non-finite values rejected ----------

    _NONFINITE_VALUES = ("nan", "NaN", "inf", "Infinity", "-inf", "-Infinity")

    def _test_reject_nonfinite_manual_electricity(self) -> None:
        for bad_value in self._NONFINITE_VALUES:
            log_path = self._electricity_log_path()
            try:
                append_electricity_reading(value=bad_value, unit="kWh", log_path=log_path)
            except ValueError:
                self.result.add_pass()
            else:
                self.assert_true(False, f"value={bad_value!r} should raise ValueError")
            # Must not have been written before raising -- the log must stay empty/absent.
            self.assert_false(
                log_path.exists() and log_path.read_text(encoding="utf-8").strip() != "",
                f"A rejected value ({bad_value!r}) must never reach the local log",
            )

    def _test_reject_nonfinite_manual_gas(self) -> None:
        for bad_value in self._NONFINITE_VALUES:
            log_path = self._gas_log_path()
            try:
                append_gas_reading(value=bad_value, unit="m3", log_path=log_path)
            except ValueError:
                self.result.add_pass()
            else:
                self.assert_true(False, f"value={bad_value!r} should raise ValueError")
            self.assert_false(
                log_path.exists() and log_path.read_text(encoding="utf-8").strip() != "",
                f"A rejected value ({bad_value!r}) must never reach the local log",
            )

    def _test_reject_nonfinite_csv_row_not_persisted(self) -> None:
        csv_path = self._write_csv(
            ["2026-01-01,412.5,kWh,", "2026-01-02,nan,kWh,", "2026-01-03,Infinity,kWh,"]
        )
        log_path = self._electricity_log_path()
        imported, skipped = import_electricity_csv(csv_path, log_path=log_path)
        self.assert_equal(imported, 1, "Only the one genuinely finite row should be imported")
        self.assert_equal(len(skipped), 2, "Both non-finite rows should be reported as skipped")
        source = ElectricityCsvSource(log_path=log_path)
        points = source.collect()
        self.assert_equal(len(points), 1)
        self.assert_true(
            all(str(point.value) not in ("nan", "inf", "-inf") for point in points),
            "No non-finite value should ever appear in the persisted log",
        )

    # ---------- EP093-AUDIT-002 regression: import-csv success semantics ----------

    def _test_import_csv_all_invalid_reports_failure(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service, enabled_categories=frozenset({ELECTRICITY_CATEGORY, GAS_CATEGORY}))
        csv_path = self._write_csv(["not-a-date,not-a-number,kWh,"])
        log_path = self._electricity_log_path()
        original_default = electricity_source_module.DEFAULT_LOG_PATH
        electricity_source_module.DEFAULT_LOG_PATH = log_path
        try:
            service.register_source(ElectricityCsvSource(log_path=log_path))
            result = module.execute("import-csv", [ELECTRICITY_CATEGORY, str(csv_path)])
        finally:
            electricity_source_module.DEFAULT_LOG_PATH = original_default
        self.assert_false(result.success, "An all-invalid CSV import must report failure")
        self.assert_true("Imported 0 row(s)" in result.message)
        self.assert_equal(len(service.query(ELECTRICITY_CATEGORY)), 0)

    def _test_import_csv_mixed_valid_invalid_reports_success(self) -> None:
        service = self._build_service()
        module = PersonalDataModule(service, enabled_categories=frozenset({ELECTRICITY_CATEGORY, GAS_CATEGORY}))
        csv_path = self._write_csv(["2026-01-01,412.5,kWh,", "not-a-date,bad,kWh,"])
        log_path = self._electricity_log_path()
        original_default = electricity_source_module.DEFAULT_LOG_PATH
        electricity_source_module.DEFAULT_LOG_PATH = log_path
        try:
            service.register_source(ElectricityCsvSource(log_path=log_path))
            result = module.execute("import-csv", [ELECTRICITY_CATEGORY, str(csv_path)])
        finally:
            electricity_source_module.DEFAULT_LOG_PATH = original_default
        self.assert_true(result.success, "A CSV with at least one valid row must report success")
        self.assert_true("Imported 1 row(s)" in result.message)
        self.assert_true("Skipped 1 invalid row(s)" in result.message)
        self.assert_equal(len(service.query(ELECTRICITY_CATEGORY)), 1)

    # ---------- EP093-AUDIT-006: CRLF / BOM regression coverage ----------

    def _test_import_csv_crlf_line_endings(self) -> None:
        csv_path = self._temp_dir() / "crlf.csv"
        csv_path.write_bytes(
            b"date,value,unit,meter_id\r\n2026-01-01,412.5,kWh,\r\n2026-01-02,418.2,kWh,main\r\n"
        )
        log_path = self._electricity_log_path()
        imported, skipped = import_electricity_csv(csv_path, log_path=log_path)
        self.assert_equal(imported, 2)
        self.assert_equal(skipped, [])

    def _test_import_csv_bom_prefixed_file(self) -> None:
        csv_path = self._temp_dir() / "bom.csv"
        csv_path.write_bytes(b"\xef\xbb\xbfdate,value,unit\r\n2026-01-01,1.0,kWh\r\n")
        log_path = self._gas_log_path()
        imported, skipped = import_gas_csv(csv_path, log_path=log_path)
        self.assert_equal(imported, 1)
        self.assert_equal(skipped, [])

    # ---------- Architecture compliance ----------

    def _test_module_never_imports_forbidden_symbols(self) -> None:
        """personal_data_module.py never imports the manager/provider/persistence/registry/sources.

        Per EP-093 STEP 1 design §11's layering rule.
        """
        forbidden_names = (
            "PersonalDataManager",
            "PersonalDataProvider",
            "PersonalDataPersistence",
            "PersonalDataRegistry",
            "ElectricityCsvSource",
            "GasCsvSource",
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

    def _test_sources_never_import_command_result(self) -> None:
        """electricity_source.py/gas_source.py never reference CommandResult.

        Per EP-093 STEP 1 design §11: EP-093's PersonalDataSource
        subclasses never touch CommandResult directly.
        """
        for module in (electricity_source_module, gas_source_module):
            tree = ast.parse(inspect.getsource(module))
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    self.assert_true(
                        node.id != "CommandResult",
                        f"{module.__name__} must never reference CommandResult",
                    )
                if isinstance(node, ast.ImportFrom) and node.module:
                    for alias in node.names:
                        self.assert_true(
                            alias.name != "CommandResult",
                            f"{module.__name__} must never import CommandResult",
                        )
