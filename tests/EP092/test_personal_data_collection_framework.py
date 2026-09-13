"""Real engineering tests for EP-092 - Personal Data Collection Framework.

Builds real `PersonalDataPoint`/`PersonalDataRegistry`/
`JsonlPersonalDataProvider`/`PersonalDataManager`/`PersonalDataService`
instances -- composed with a real, temporary-directory-backed
`Config` -- and drives them exactly as a caller would, no mocked
internals, matching every other EP's test suite in this project.

Personal Data Collection (EP-092) is a new, independent package
(`src/core/personal_data/`) that persists through a dedicated
append-only JSONL store (Owner Decision, STEP 1 design §21) and has no
dependency on Knowledge Base, Embedding, Retrieval, RAG, Semantic
Search, or Context Compression. This suite covers:

1. The domain model: `PersonalDataPoint` (construction, validation,
   dedup key, timestamp/collected_at semantics, serialization).
2. `PersonalDataPersistence`: raw JSONL append/read file I/O, and
   category-name validation (STEP 3 audit finding EP092-AUDIT-001:
   path-traversal rejection).
3. `PersonalDataProvider` abstract contract and its sole approved
   implementation, `JsonlPersonalDataProvider`: store/store_if_new/
   exists/query/stats, dedup semantics, malformed-line tolerance,
   dedup-index rebuild-from-disk after a simulated restart, and
   concurrency safety of `store_if_new()` under concurrent callers
   (STEP 3 audit finding EP092-AUDIT-002).
4. `PersonalDataRegistry`: register/duplicate-rejection/lookup/
   unregister.
5. `PersonalDataManager`: the collect -> consent-gate -> dedupe ->
   persist cycle, `PersonalDataCollectionError` on source/storage
   failure, and the read-side `query()` surface.
6. `PersonalDataService`: configuration-driven construction,
   CommandResult-returning mutations, graceful degradation when
   disabled, and status reporting.
7. Architecture compliance: no forbidden imports (Knowledge Base,
   Embedding, Retrieval, RAG, Semantic Search, Context Compression,
   etc.), and `PersonalDataManager` never constructs `CommandResult`.

The illustrative `_FixturePersonalDataSource` defined below exists
solely so this suite can exercise the full collect -> dedupe ->
persist -> query path without a real network dependency. It is
test-support only, never a real integration -- EP-093/094/097 will
each implement their own real `PersonalDataSource`.
"""

from __future__ import annotations

import ast
import inspect
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.personal_data import (
    JsonlPersonalDataProvider,
    PersonalDataCollectionError,
    PersonalDataManager,
    PersonalDataPersistence,
    PersonalDataPersistenceError,
    PersonalDataPoint,
    PersonalDataProvider,
    PersonalDataProviderError,
    PersonalDataRegistry,
    PersonalDataRegistryError,
    PersonalDataSource,
)
from src.core.personal_data import personal_data_manager as personal_data_manager_module
from src.core.personal_data import personal_data_provider as personal_data_provider_module
from src.core.personal_data import personal_data_record as personal_data_record_module
from src.core.personal_data import personal_data_registry as personal_data_registry_module
from src.core.personal_data import personal_data_source as personal_data_source_module
from src.services import personal_data_service as personal_data_service_module
from src.services.personal_data_service import PersonalDataService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


def _write_config(directory: Path, config_yaml: str) -> Config:
    """Write `config_yaml` to `directory/config.yaml` and load it."""
    config_path = directory / "config.yaml"
    config_path.write_text(config_yaml, encoding="utf-8")
    return Config(config_path).load()


def _personal_data_yaml(
    enabled: bool = True, enabled_categories: list[str] | None = None, storage_root: str = ""
) -> str:
    """Build a minimal 'personal_data:' config block for tests."""
    categories = enabled_categories if enabled_categories is not None else ["electricity"]
    categories_yaml = (
        "[]" if not categories else "[" + ", ".join(f'"{item}"' for item in categories) + "]"
    )
    lines = [
        "personal_data:",
        f"  enabled: {str(enabled).lower()}",
        f"  enabled_categories: {categories_yaml}",
    ]
    if storage_root:
        # Single-quoted YAML scalars take backslashes literally (no escape
        # processing), unlike double-quoted scalars where '\' introduces an
        # escape sequence. Windows temp paths (e.g. 'D:\Temp\...') contain
        # backslashes that PyYAML's double-quoted scanner rejects as unknown
        # escapes (e.g. '\T'), so single-quoting keeps this valid on both
        # Windows and POSIX. The only special character in single-quoted
        # style is `'` itself, escaped by doubling it per the YAML spec.
        escaped_storage_root = storage_root.replace("'", "''")
        lines.append(f"  storage_root: '{escaped_storage_root}'")
    return "\n".join(lines) + "\n"


class _FixturePersonalDataSource(PersonalDataSource):
    """Illustrative, test-support-only `PersonalDataSource`.

    Never a real integration: returns a preset list of points (or
    raises a preset exception) so this suite can drive
    `PersonalDataManager`/`PersonalDataService` exactly as a real
    caller would. EP-093/094/097 each implement their own real source
    against the same `PersonalDataSource` contract.
    """

    def __init__(
        self,
        source_id: str,
        category: str,
        points: list[PersonalDataPoint] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._source_id = source_id
        self._category = category
        self._points = points if points is not None else []
        self._raises = raises

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def category(self) -> str:
        return self._category

    def collect(self) -> list[PersonalDataPoint]:
        if self._raises is not None:
            raise self._raises
        return list(self._points)


def _make_point(
    point_id: str = "p1",
    source_id: str = "meter-1",
    category: str = "electricity",
    timestamp: datetime | None = None,
    value: float = 1.5,
    unit: str = "kWh",
    collected_at: datetime | None = None,
) -> PersonalDataPoint:
    return PersonalDataPoint(
        id=point_id,
        source_id=source_id,
        category=category,
        timestamp=timestamp or datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        value=value,
        unit=unit,
        raw={"raw_field": "raw_value"},
        collected_at=collected_at or datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc),
    )


@TestRegistry.register
class PersonalDataCollectionFrameworkTest(BaseTest):
    """Real tests covering EP-092's Personal Data Collection Framework."""

    NAME = "EP092"

    def run(self):
        """Execute every Personal Data Collection Framework check and return the result."""
        # PersonalDataPoint
        self._test_point_construction_and_dedup_key()
        self._test_point_rejects_empty_required_fields()
        self._test_point_value_must_be_float_not_bool_or_str()
        self._test_point_to_dict_from_dict_roundtrip()
        self._test_point_timestamp_and_collected_at_are_distinct()

        # PersonalDataPersistence
        self._test_persistence_append_and_read_roundtrip()
        self._test_persistence_missing_category_returns_empty()
        self._test_persistence_known_categories_and_line_count()

        # PersonalDataProvider / JsonlPersonalDataProvider
        self._test_provider_is_abstract()
        self._test_provider_store_exists_query()
        self._test_provider_dedup_excludes_collected_at()
        self._test_provider_query_filters_by_time_range()
        self._test_provider_query_skips_malformed_line()
        self._test_provider_stats()
        self._test_provider_dedup_index_rebuilds_after_restart()
        self._test_provider_store_failure_raises_provider_error()
        self._test_provider_store_if_new_basic_semantics()
        self._test_provider_store_if_new_failure_does_not_update_index()

        # EP092-AUDIT-001: category path-traversal regression
        self._test_category_traversal_rejected_dotdot()
        self._test_category_traversal_rejected_slash()
        self._test_category_traversal_rejected_absolute_path()
        self._test_category_traversal_no_file_created_outside_root()
        self._test_valid_categories_still_work_after_sanitization()

        # EP092-AUDIT-002: concurrent deduplication race regression
        self._test_concurrent_collect_from_same_point_stores_exactly_once()
        self._test_concurrent_collect_from_different_points_all_succeed()
        self._test_provider_store_if_new_concurrent_calls_atomic()

        # EP092-AUDIT-004: invalid/legacy on-disk category must not crash initialization
        self._test_invalid_legacy_category_does_not_crash_initialization()
        self._test_valid_category_still_loaded_alongside_invalid_legacy_category()
        self._test_invalid_legacy_category_not_silently_accepted_as_valid()

        # PersonalDataRegistry
        self._test_registry_register_get_and_duplicate_rejection()
        self._test_registry_unregister_and_source_ids()

        # PersonalDataManager
        self._test_manager_collect_from_stores_new_points()
        self._test_manager_collect_from_skips_disabled_category()
        self._test_manager_collect_from_skips_duplicates()
        self._test_manager_collect_from_unknown_source_raises()
        self._test_manager_collect_from_source_exception_raises_collection_error()
        self._test_manager_query_delegates_to_provider()

        # PersonalDataService
        self._test_service_builds_default_manager_from_config()
        self._test_service_register_source_and_collect_returns_command_result()
        self._test_service_collect_failure_returns_failed_command_result()
        self._test_service_disabled_subsystem_rejects_mutations_and_reads()
        self._test_service_status_reports_stats_and_enabled_categories()

        # Architectural acceptance criteria
        self._test_no_forbidden_imports()
        self._test_manager_never_constructs_command_result()
        self._test_exception_hierarchy()

        return self.result

    # ---------- Helpers ----------

    def _temp_storage_root(self) -> Path:
        tmp_dir = tempfile.TemporaryDirectory()
        self._keep_alive(tmp_dir)
        return Path(tmp_dir.name) / "personal_data"

    def _keep_alive(self, obj: object) -> None:
        """Keep a TemporaryDirectory alive for the lifetime of the test run."""
        if not hasattr(self, "_tmp_dirs"):
            self._tmp_dirs = []
        self._tmp_dirs.append(obj)

    def _build_config(
        self,
        enabled: bool = True,
        enabled_categories: list[str] | None = None,
        storage_root: Path | None = None,
    ) -> Config:
        tmp_dir = tempfile.TemporaryDirectory()
        self._keep_alive(tmp_dir)
        root = storage_root if storage_root is not None else self._temp_storage_root()
        yaml_text = _personal_data_yaml(
            enabled=enabled, enabled_categories=enabled_categories, storage_root=str(root)
        )
        return _write_config(Path(tmp_dir.name), yaml_text)

    def _build_provider(self, storage_root: Path | None = None) -> JsonlPersonalDataProvider:
        config = self._build_config(storage_root=storage_root or self._temp_storage_root())
        return JsonlPersonalDataProvider(config)

    def _build_manager(
        self,
        enabled_categories: list[str] | None = None,
        provider: PersonalDataProvider | None = None,
        storage_root: Path | None = None,
    ) -> PersonalDataManager:
        root = storage_root or self._temp_storage_root()
        resolved_provider = provider if provider is not None else JsonlPersonalDataProvider(
            self._build_config(storage_root=root)
        )
        categories = enabled_categories if enabled_categories is not None else ["electricity"]
        return PersonalDataManager(
            registry=PersonalDataRegistry(),
            provider=resolved_provider,
            enabled_categories=frozenset(categories),
        )

    def _build_service(
        self, enabled: bool = True, enabled_categories: list[str] | None = None
    ) -> PersonalDataService:
        config = self._build_config(enabled=enabled, enabled_categories=enabled_categories)
        return PersonalDataService(config=config)

    # ---------- PersonalDataPoint ----------

    def _test_point_construction_and_dedup_key(self) -> None:
        point = _make_point()
        self.assert_equal(point.source_id, "meter-1")
        self.assert_equal(point.value, 1.5)
        self.assert_true(isinstance(point.value, float), "value should be coerced to float")
        self.assert_equal(
            point.dedup_key(),
            ("meter-1", "electricity", datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)),
        )

    def _test_point_rejects_empty_required_fields(self) -> None:
        for field_name, kwargs in (
            ("id", {"point_id": ""}),
            ("source_id", {"source_id": ""}),
            ("category", {"category": ""}),
            ("unit", {"unit": ""}),
        ):
            try:
                _make_point(**kwargs)
            except ValueError:
                self.result.add_pass()
            else:
                self.assert_true(False, f"Empty {field_name} should raise ValueError")

    def _test_point_value_must_be_float_not_bool_or_str(self) -> None:
        for bad_value in (True, False, "1.5", None):
            try:
                _make_point(value=bad_value)  # type: ignore[arg-type]
            except TypeError:
                self.result.add_pass()
            else:
                self.assert_true(False, f"value={bad_value!r} should raise TypeError")
        # int is accepted and coerced to float.
        point = _make_point(value=3)  # type: ignore[arg-type]
        self.assert_true(isinstance(point.value, float), "int value should coerce to float")
        self.assert_equal(point.value, 3.0)

    def _test_point_to_dict_from_dict_roundtrip(self) -> None:
        point = _make_point()
        restored = PersonalDataPoint.from_dict(point.to_dict())
        self.assert_equal(restored, point)

    def _test_point_timestamp_and_collected_at_are_distinct(self) -> None:
        timestamp = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        collected_at = datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc)
        point = _make_point(timestamp=timestamp, collected_at=collected_at)
        self.assert_equal(point.timestamp, timestamp)
        self.assert_equal(point.collected_at, collected_at)
        self.assert_true(
            point.collected_at not in point.dedup_key(),
            "collected_at must never appear in the dedup key",
        )

    # ---------- PersonalDataPersistence ----------

    def _test_persistence_append_and_read_roundtrip(self) -> None:
        config = self._build_config()
        persistence = PersonalDataPersistence(config)
        persistence.append_line("electricity", '{"a": 1}')
        persistence.append_line("electricity", '{"a": 2}')
        lines = list(persistence.read_lines("electricity"))
        self.assert_equal(lines, ['{"a": 1}', '{"a": 2}'])

    def _test_persistence_missing_category_returns_empty(self) -> None:
        config = self._build_config()
        persistence = PersonalDataPersistence(config)
        self.assert_equal(list(persistence.read_lines("never_collected")), [])

    def _test_persistence_known_categories_and_line_count(self) -> None:
        config = self._build_config()
        persistence = PersonalDataPersistence(config)
        self.assert_equal(persistence.known_categories(), [])
        persistence.append_line("electricity", '{"a": 1}')
        persistence.append_line("solar", '{"a": 1}')
        persistence.append_line("solar", '{"a": 2}')
        self.assert_equal(persistence.known_categories(), ["electricity", "solar"])
        self.assert_equal(persistence.line_count("solar"), 2)
        self.assert_equal(persistence.line_count("electricity"), 1)

    # ---------- PersonalDataProvider / JsonlPersonalDataProvider ----------

    def _test_provider_is_abstract(self) -> None:
        try:
            PersonalDataProvider()  # type: ignore[abstract]
        except TypeError:
            self.result.add_pass()
        else:
            self.assert_true(False, "PersonalDataProvider should not be directly instantiable")

    def _test_provider_store_exists_query(self) -> None:
        provider = self._build_provider()
        point = _make_point()
        self.assert_false(provider.exists(point.source_id, point.category, point.timestamp))
        provider.store(point)
        self.assert_true(provider.exists(point.source_id, point.category, point.timestamp))
        results = provider.query(point.category)
        self.assert_equal(results, [point])

    def _test_provider_dedup_excludes_collected_at(self) -> None:
        provider = self._build_provider()
        point = _make_point(collected_at=datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc))
        provider.store(point)
        # Same (source_id, category, timestamp) but a different collected_at
        # must still be considered "exists" -- collected_at is not part of the key.
        self.assert_true(
            provider.exists(point.source_id, point.category, point.timestamp),
            "exists() must key on (source_id, category, timestamp) only",
        )

    def _test_provider_query_filters_by_time_range(self) -> None:
        provider = self._build_provider()
        early = _make_point(point_id="p_early", timestamp=datetime(2026, 1, 1, 8, tzinfo=timezone.utc))
        mid = _make_point(point_id="p_mid", timestamp=datetime(2026, 1, 1, 10, tzinfo=timezone.utc))
        late = _make_point(point_id="p_late", timestamp=datetime(2026, 1, 1, 12, tzinfo=timezone.utc))
        for point in (early, mid, late):
            provider.store(point)
        results = provider.query(
            "electricity",
            start=datetime(2026, 1, 1, 9, tzinfo=timezone.utc),
            end=datetime(2026, 1, 1, 11, tzinfo=timezone.utc),
        )
        self.assert_equal(results, [mid])

    def _test_provider_query_skips_malformed_line(self) -> None:
        config = self._build_config()
        persistence = PersonalDataPersistence(config)
        persistence.append_line("electricity", "not valid json")
        provider = JsonlPersonalDataProvider(config, persistence=persistence)
        point = _make_point()
        provider.store(point)
        results = provider.query("electricity")
        self.assert_equal(results, [point])

    def _test_provider_stats(self) -> None:
        provider = self._build_provider()
        self.assert_equal(provider.stats(), {"category_count": 0, "point_count": 0})
        provider.store(_make_point(point_id="p1", category="electricity"))
        provider.store(_make_point(point_id="p2", category="solar", source_id="inverter-1"))
        stats = provider.stats()
        self.assert_equal(stats, {"category_count": 2, "point_count": 2})

    def _test_provider_dedup_index_rebuilds_after_restart(self) -> None:
        root = self._temp_storage_root()
        provider = self._build_provider(storage_root=root)
        point = _make_point()
        provider.store(point)

        # Simulate a process restart: a fresh provider instance pointing at
        # the same storage root must rebuild its dedup index from disk.
        restarted_config = self._build_config(storage_root=root)
        restarted_provider = JsonlPersonalDataProvider(restarted_config)
        self.assert_true(
            restarted_provider.exists(point.source_id, point.category, point.timestamp),
            "dedup index must be rebuilt from persisted JSONL files on initialization",
        )
        self.assert_equal(restarted_provider.query(point.category), [point])

    def _test_provider_store_failure_raises_provider_error(self) -> None:
        tmp_dir = tempfile.TemporaryDirectory()
        self._keep_alive(tmp_dir)
        # Create a plain file where the storage root directory should be,
        # so PersonalDataPersistence.append_line's mkdir() fails with OSError.
        blocked_root = Path(tmp_dir.name) / "blocked_root"
        blocked_root.write_text("not a directory", encoding="utf-8")
        config = self._build_config(storage_root=blocked_root)
        provider = JsonlPersonalDataProvider(config)
        try:
            provider.store(_make_point())
        except PersonalDataProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "store() should raise PersonalDataProviderError on I/O failure")

    def _test_provider_store_if_new_basic_semantics(self) -> None:
        provider = self._build_provider()
        point = _make_point()
        first = provider.store_if_new(point)
        second = provider.store_if_new(point)
        self.assert_true(first, "store_if_new() should return True for a genuinely new point")
        self.assert_false(second, "store_if_new() should return False for an already-stored point")
        self.assert_equal(provider.query(point.category), [point], "must not duplicate on disk")

    def _test_provider_store_if_new_failure_does_not_update_index(self) -> None:
        tmp_dir = tempfile.TemporaryDirectory()
        self._keep_alive(tmp_dir)
        blocked_root = Path(tmp_dir.name) / "blocked_root"
        blocked_root.write_text("not a directory", encoding="utf-8")
        config = self._build_config(storage_root=blocked_root)
        provider = JsonlPersonalDataProvider(config)
        point = _make_point()
        try:
            provider.store_if_new(point)
        except PersonalDataProviderError:
            self.result.add_pass()
        else:
            self.assert_true(False, "store_if_new() should raise PersonalDataProviderError on I/O failure")
        # A failed write must not be recorded as if the point were stored.
        self.assert_false(
            provider.exists(point.source_id, point.category, point.timestamp),
            "A failed store_if_new() must not update the dedup index",
        )

    # ---------- EP092-AUDIT-001: category path-traversal regression ----------

    def _test_category_traversal_rejected_dotdot(self) -> None:
        config = self._build_config()
        persistence = PersonalDataPersistence(config)
        try:
            persistence.append_line("../../escaped", '{"x": 1}')
        except PersonalDataPersistenceError:
            self.result.add_pass()
        else:
            self.assert_true(False, "'../../escaped' category must be rejected")

    def _test_category_traversal_rejected_slash(self) -> None:
        config = self._build_config()
        persistence = PersonalDataPersistence(config)
        for malicious_category in ("a/b", "a\\b", "..", "."):
            try:
                persistence.append_line(malicious_category, '{"x": 1}')
            except PersonalDataPersistenceError:
                self.result.add_pass()
            else:
                self.assert_true(False, f"category {malicious_category!r} must be rejected")

    def _test_category_traversal_rejected_absolute_path(self) -> None:
        config = self._build_config()
        persistence = PersonalDataPersistence(config)
        try:
            persistence.append_line("/etc/passwd", '{"x": 1}')
        except PersonalDataPersistenceError:
            self.result.add_pass()
        else:
            self.assert_true(False, "An absolute-path-like category must be rejected")

    def _test_category_traversal_no_file_created_outside_root(self) -> None:
        tmp_dir = tempfile.TemporaryDirectory()
        self._keep_alive(tmp_dir)
        storage_root = Path(tmp_dir.name) / "storage_root"
        config = self._build_config(storage_root=storage_root)
        persistence = PersonalDataPersistence(config)
        # The attack target from the original EP092-AUDIT-001 reproduction:
        # a file landing two directories above the configured storage root.
        # Clean up first in case a stray artifact from an unrelated prior
        # run (this audit's own manual reproduction, run outside this
        # suite) happens to occupy the same path -- a shared, predictable
        # path two levels above any temp dir under /tmp.
        escaped_path = (storage_root / ".." / ".." / "escaped.jsonl").resolve()
        if escaped_path.exists():
            escaped_path.unlink()
        try:
            persistence.append_line("../../escaped", '{"x": 1}')
        except PersonalDataPersistenceError:
            pass
        self.assert_false(
            escaped_path.exists(),
            f"No file should ever be created outside the storage root ({escaped_path})",
        )
        # Also confirm nothing at all was written inside the storage root either
        # (the operation must be fully rejected, not silently redirected).
        self.assert_false(storage_root.exists() and any(storage_root.glob("*.jsonl")))

    def _test_valid_categories_still_work_after_sanitization(self) -> None:
        provider = self._build_provider()
        for valid_category in ("electricity", "solar_v2", "meter-1", "A1"):
            point = _make_point(point_id=f"p-{valid_category}", category=valid_category)
            provider.store(point)
            self.assert_equal(provider.query(valid_category), [point])

    # ---------- EP092-AUDIT-002: concurrent deduplication race regression ----------

    def _test_concurrent_collect_from_same_point_stores_exactly_once(self) -> None:
        provider = self._build_provider()
        manager = self._build_manager(enabled_categories=["electricity"], provider=provider)
        point = _make_point()
        manager.register_source(_FixturePersonalDataSource("meter-1", "electricity", [point]))

        results: list[int] = []
        errors: list[Exception] = []

        def worker() -> None:
            try:
                results.append(manager.collect_from("meter-1"))
            except Exception as exc:  # noqa: BLE001 - captured for assertion, not swallowed silently
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assert_equal(errors, [], "No thread should raise for a normal concurrent collection")
        self.assert_equal(sum(results), 1, "Exactly one of the concurrent calls should store the point")
        self.assert_equal(
            len(provider.query("electricity")), 1, "Exactly one record must exist on disk"
        )

    def _test_concurrent_collect_from_different_points_all_succeed(self) -> None:
        provider = self._build_provider()
        manager = self._build_manager(enabled_categories=["electricity"], provider=provider)
        points = [
            _make_point(
                point_id=f"p{i}",
                timestamp=datetime(2026, 1, 1, 10, i, tzinfo=timezone.utc),
            )
            for i in range(10)
        ]
        for index, point in enumerate(points):
            manager.register_source(
                _FixturePersonalDataSource(f"meter-{index}", "electricity", [point])
            )

        results: list[int] = []

        def worker(source_id: str) -> None:
            results.append(manager.collect_from(source_id))

        threads = [
            threading.Thread(target=worker, args=(f"meter-{i}",)) for i in range(10)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assert_equal(sum(results), 10, "All 10 distinct points should be stored exactly once each")
        self.assert_equal(len(provider.query("electricity")), 10)

    def _test_provider_store_if_new_concurrent_calls_atomic(self) -> None:
        """Directly reproduces the original EP092-AUDIT-002 finding at the provider level.

        The original finding widened the gap between the dedup check
        and the write to force concurrent callers to interleave. With
        the fix, `store_if_new()` holds a single lock across both
        steps, so there is no gap left to widen from the outside.
        This test instead makes the *write itself* artificially slow
        (patching `PersonalDataPersistence.append_line`) -- if the
        check-and-store were still two separate, unlocked steps, this
        would make the race trivial to trigger; with the fix, it
        proves atomicity holds even while a slow write is in flight,
        since every other thread must block on the lock for the
        entire duration.
        """
        provider = self._build_provider()
        point = _make_point()

        original_append_line = provider._persistence.append_line  # noqa: SLF001 - white-box regression check

        def slow_append_line(category: str, line: str) -> None:
            time.sleep(0.02)
            original_append_line(category, line)

        provider._persistence.append_line = slow_append_line  # noqa: SLF001

        results: list[bool] = []

        def worker() -> None:
            results.append(provider.store_if_new(point))

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assert_equal(sum(1 for stored in results if stored), 1)
        self.assert_equal(len(provider.query(point.category)), 1)

    # ---------- EP092-AUDIT-004: invalid/legacy on-disk category regression ----------

    def _test_invalid_legacy_category_does_not_crash_initialization(self) -> None:
        storage_root = self._temp_storage_root()
        storage_root.mkdir(parents=True, exist_ok=True)
        # Simulate a legacy/externally-placed file whose category name
        # predates the stricter validation added for EP092-AUDIT-001 --
        # written directly to disk, bypassing PersonalDataPersistence
        # entirely, exactly as an out-of-band file would arrive.
        (storage_root / "a.b.jsonl").write_text(
            '{"id":"legacy1","source_id":"s","category":"a.b",'
            '"timestamp":"2026-01-01T00:00:00+00:00","value":1.0,"unit":"kWh",'
            '"raw":{},"collected_at":"2026-01-01T00:00:00+00:00"}\n',
            encoding="utf-8",
        )
        config = self._build_config(storage_root=storage_root)
        try:
            provider = JsonlPersonalDataProvider(config)
        except PersonalDataPersistenceError:
            self.assert_true(
                False,
                "Provider initialization must not crash on an invalid legacy category file",
            )
            return
        self.result.add_pass()
        self.assert_equal(provider.stats()["point_count"], 0)

    def _test_valid_category_still_loaded_alongside_invalid_legacy_category(self) -> None:
        storage_root = self._temp_storage_root()
        config = self._build_config(storage_root=storage_root)
        setup_provider = JsonlPersonalDataProvider(config)
        valid_point = _make_point(point_id="valid1", category="electricity")
        setup_provider.store(valid_point)

        # Land the invalid legacy file inside the same, already-created
        # storage root, alongside the valid category's file.
        (storage_root / "a.b.jsonl").write_text(
            '{"id":"legacy1","source_id":"s","category":"a.b",'
            '"timestamp":"2026-01-01T00:00:00+00:00","value":1.0,"unit":"kWh",'
            '"raw":{},"collected_at":"2026-01-01T00:00:00+00:00"}\n',
            encoding="utf-8",
        )

        # A fresh provider instance simulates a process restart that must
        # now rebuild its dedup index in the presence of the invalid file.
        restarted_provider = JsonlPersonalDataProvider(config)
        self.assert_true(
            restarted_provider.exists(
                valid_point.source_id, valid_point.category, valid_point.timestamp
            ),
            "A valid category's data must still be rebuilt into the dedup index",
        )
        self.assert_equal(restarted_provider.query("electricity"), [valid_point])

    def _test_invalid_legacy_category_not_silently_accepted_as_valid(self) -> None:
        storage_root = self._temp_storage_root()
        storage_root.mkdir(parents=True, exist_ok=True)
        (storage_root / "a.b.jsonl").write_text(
            '{"id":"legacy1","source_id":"s","category":"a.b",'
            '"timestamp":"2026-01-01T00:00:00+00:00","value":1.0,"unit":"kWh",'
            '"raw":{},"collected_at":"2026-01-01T00:00:00+00:00"}\n',
            encoding="utf-8",
        )
        config = self._build_config(storage_root=storage_root)
        provider = JsonlPersonalDataProvider(config)

        # The skipped category's data must not silently enter the dedup
        # index as if it had been successfully rebuilt.
        self.assert_false(
            provider.exists("s", "a.b", datetime(2026, 1, 1, tzinfo=timezone.utc)),
            "A skipped invalid category's data must not silently enter the dedup index",
        )
        # Explicitly querying it must still be rejected -- never silently
        # treated as an ordinary empty/never-collected category, and never
        # read via a path that bypasses category_path()'s validation.
        try:
            provider.query("a.b")
        except PersonalDataProviderError:
            self.result.add_pass()
        else:
            self.assert_true(
                False, "Explicitly querying an invalid category must still raise, not return []"
            )

    def _test_registry_register_get_and_duplicate_rejection(self) -> None:
        registry = PersonalDataRegistry()
        source = _FixturePersonalDataSource("meter-1", "electricity")
        registry.register(source)
        self.assert_true(registry.get("meter-1") is source)
        self.assert_true(registry.is_registered("meter-1"))
        try:
            registry.register(_FixturePersonalDataSource("meter-1", "electricity"))
        except PersonalDataRegistryError:
            self.result.add_pass()
        else:
            self.assert_true(False, "Duplicate source_id registration should raise")

    def _test_registry_unregister_and_source_ids(self) -> None:
        registry = PersonalDataRegistry()
        registry.register(_FixturePersonalDataSource("meter-1", "electricity"))
        registry.register(_FixturePersonalDataSource("inverter-1", "solar"))
        self.assert_equal(registry.source_ids(), ["inverter-1", "meter-1"])
        self.assert_true(registry.unregister("meter-1"))
        self.assert_false(registry.unregister("meter-1"))
        self.assert_equal(registry.source_ids(), ["inverter-1"])
        self.assert_true(registry.get("meter-1") is None)

    # ---------- PersonalDataManager ----------

    def _test_manager_collect_from_stores_new_points(self) -> None:
        manager = self._build_manager(enabled_categories=["electricity"])
        point = _make_point()
        manager.register_source(_FixturePersonalDataSource("meter-1", "electricity", [point]))
        stored = manager.collect_from("meter-1")
        self.assert_equal(stored, 1)
        self.assert_equal(manager.query("electricity"), [point])

    def _test_manager_collect_from_skips_disabled_category(self) -> None:
        manager = self._build_manager(enabled_categories=["solar"])  # electricity NOT enabled
        point = _make_point()
        manager.register_source(_FixturePersonalDataSource("meter-1", "electricity", [point]))
        stored = manager.collect_from("meter-1")
        self.assert_equal(stored, 0, "Points in a non-enabled category must not be stored")
        self.assert_equal(manager.query("electricity"), [])

    def _test_manager_collect_from_skips_duplicates(self) -> None:
        manager = self._build_manager(enabled_categories=["electricity"])
        point = _make_point()
        manager.register_source(_FixturePersonalDataSource("meter-1", "electricity", [point]))
        first = manager.collect_from("meter-1")
        second = manager.collect_from("meter-1")
        self.assert_equal(first, 1)
        self.assert_equal(second, 0, "Re-collecting the same point must not increase the count")
        self.assert_equal(len(manager.query("electricity")), 1)

    def _test_manager_collect_from_unknown_source_raises(self) -> None:
        manager = self._build_manager()
        try:
            manager.collect_from("does-not-exist")
        except PersonalDataCollectionError:
            self.result.add_pass()
        else:
            self.assert_true(False, "collect_from() on an unknown source should raise")

    def _test_manager_collect_from_source_exception_raises_collection_error(self) -> None:
        manager = self._build_manager(enabled_categories=["electricity"])
        manager.register_source(
            _FixturePersonalDataSource(
                "meter-1", "electricity", raises=RuntimeError("api unreachable")
            )
        )
        try:
            manager.collect_from("meter-1")
        except PersonalDataCollectionError:
            self.result.add_pass()
        else:
            self.assert_true(False, "A source raising should surface as PersonalDataCollectionError")

    def _test_manager_query_delegates_to_provider(self) -> None:
        provider = self._build_provider()
        point = _make_point()
        provider.store(point)
        manager = self._build_manager(provider=provider)
        self.assert_equal(manager.query("electricity"), [point])

    # ---------- PersonalDataService ----------

    def _test_service_builds_default_manager_from_config(self) -> None:
        service = self._build_service(enabled_categories=["electricity"])
        status = service.status()
        self.assert_true(status.enabled)
        self.assert_equal(status.enabled_categories, ["electricity"])
        self.assert_equal(status.point_count, 0)

    def _test_service_register_source_and_collect_returns_command_result(self) -> None:
        service = self._build_service(enabled_categories=["electricity"])
        source = _FixturePersonalDataSource("meter-1", "electricity", [_make_point()])
        register_result = service.register_source(source)
        self.assert_true(isinstance(register_result, CommandResult))
        self.assert_true(register_result.success)

        collect_result = service.collect("meter-1")
        self.assert_true(collect_result.success)
        self.assert_true("1" in collect_result.message)

        points = service.query("electricity")
        self.assert_equal(len(points), 1)

    def _test_service_collect_failure_returns_failed_command_result(self) -> None:
        service = self._build_service(enabled_categories=["electricity"])
        service.register_source(
            _FixturePersonalDataSource("meter-1", "electricity", raises=RuntimeError("boom"))
        )
        result = service.collect("meter-1")
        self.assert_false(result.success)

    def _test_service_disabled_subsystem_rejects_mutations_and_reads(self) -> None:
        service = self._build_service(enabled=False)
        register_result = service.register_source(
            _FixturePersonalDataSource("meter-1", "electricity")
        )
        self.assert_false(register_result.success)
        collect_result = service.collect("meter-1")
        self.assert_false(collect_result.success)
        self.assert_equal(service.query("electricity"), [])
        status = service.status()
        self.assert_false(status.enabled)
        self.assert_equal(status.point_count, 0)

    def _test_service_status_reports_stats_and_enabled_categories(self) -> None:
        service = self._build_service(enabled_categories=["electricity", "solar"])
        service.register_source(
            _FixturePersonalDataSource("meter-1", "electricity", [_make_point()])
        )
        service.collect("meter-1")
        status = service.status()
        self.assert_equal(status.enabled_categories, ["electricity", "solar"])
        self.assert_equal(status.registered_sources, ["meter-1"])
        self.assert_equal(status.point_count, 1)
        self.assert_equal(status.category_count, 1)

    # ---------- Architectural acceptance criteria ----------

    def _test_no_forbidden_imports(self) -> None:
        """The Personal Data package never imports Knowledge Base, Embedding, RAG, etc.

        Per EP-092's STEP 1 design (Owner Decision §21), Personal Data
        Collection must not import Knowledge Base, and per its Goals/
        Non-Goals must not import Embedding, Retrieval, RAG, Semantic
        Search, or Context Compression either.
        """
        forbidden_module_fragments = (
            "knowledge",
            "semantic_search",
            "context_compression",
            "retrieval",
            "rag",
            "embedding",
            "agent_framework",
            "planner",
            "planning",
            "reflection",
            "vector_store",
            "faiss",
            "chroma",
            "pinecone",
            "qdrant",
            "weaviate",
            "browser_automation",
        )
        modules = [
            personal_data_manager_module,
            personal_data_provider_module,
            personal_data_record_module,
            personal_data_registry_module,
            personal_data_source_module,
            personal_data_service_module,
        ]
        for module in modules:
            tree = ast.parse(inspect.getsource(module))
            imported_names: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported_names.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported_names.append(node.module)
            for imported_name in imported_names:
                lowered = imported_name.lower()
                for forbidden_fragment in forbidden_module_fragments:
                    self.assert_true(
                        forbidden_fragment not in lowered,
                        f"{module.__name__} must not import '{imported_name}' "
                        f"(matches forbidden fragment '{forbidden_fragment}')",
                    )

    def _test_manager_never_constructs_command_result(self) -> None:
        """PersonalDataManager never imports or references CommandResult in code.

        CommandResult belongs exclusively to PersonalDataService (see
        the EP-092 STEP 1 design §13 layering rule). This checks the
        actual import and name-usage nodes in the module's AST -- not
        the module's own explanatory docstrings/comments, which
        legitimately discuss the layering rule in prose.
        """
        tree = ast.parse(inspect.getsource(personal_data_manager_module))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    self.assert_true(
                        alias.name != "CommandResult",
                        "PersonalDataManager must never import CommandResult",
                    )
            if isinstance(node, ast.Name):
                self.assert_true(
                    node.id != "CommandResult",
                    "PersonalDataManager must never reference CommandResult in code",
                )

    def _test_exception_hierarchy(self) -> None:
        """PersonalDataCollectionError/ProviderError/RegistryError are plain, catchable Exceptions."""
        for exc_class in (
            PersonalDataCollectionError,
            PersonalDataProviderError,
            PersonalDataRegistryError,
        ):
            self.assert_true(issubclass(exc_class, Exception))
            try:
                raise exc_class("boom")
            except exc_class:
                self.result.add_pass()
            else:
                self.assert_true(False, f"{exc_class.__name__} should be catchable directly")
