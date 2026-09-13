"""Central orchestration for EP-092 Personal Data Collection Framework.

`PersonalDataManager` is the only component that calls both
`PersonalDataRegistry` (source lookup) and `PersonalDataProvider`
(storage). It owns the collection cycle (collect -> consent-gate ->
dedupe -> persist) and the read-side query surface every downstream EP
(EP-095/096/098) reads from.

Layering rule: `PersonalDataManager` is domain/application
orchestration and speaks only in plain return values (`int`) and one
domain exception (`PersonalDataCollectionError`). `CommandResult`
belongs exclusively to `PersonalDataService`
(`src/services/personal_data_service.py`) -- it never appears in this
module.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger

from src.core.personal_data.personal_data_provider import (
    PersonalDataProvider,
    PersonalDataProviderError,
)
from src.core.personal_data.personal_data_record import PersonalDataPoint
from src.core.personal_data.personal_data_registry import PersonalDataRegistry
from src.core.personal_data.personal_data_source import PersonalDataSource


class PersonalDataCollectionError(Exception):
    """Raised by `PersonalDataManager.collect_from()` when a collection cycle fails.

    Raised when the source's `collect()` raises, or when the
    provider's `store_if_new()` raises. Never raised for the
    normal "nothing new" or "duplicate/filtered" outcomes -- those
    simply do not add to the returned count.
    """


class PersonalDataManager:
    """Orchestrates registered `PersonalDataSource` instances against one `PersonalDataProvider`."""

    def __init__(
        self,
        registry: PersonalDataRegistry,
        provider: PersonalDataProvider,
        enabled_categories: frozenset[str] = frozenset(),
    ) -> None:
        """Initialize the manager.

        Args:
            registry: The `PersonalDataRegistry` used to look up
                sources by `source_id`.
            provider: The `PersonalDataProvider` used to persist and
                query points. Injected explicitly (Dependency Policy)
                rather than read from global Config here --
                `PersonalDataService` resolves the concrete provider
                from configuration and injects it.
            enabled_categories: The consent allowlist
                ('personal_data.enabled_categories', resolved by
                `PersonalDataService` and injected here). A category
                not in this set is never collected or stored (§15 of
                the EP-092 STEP 1 design). Defaults to empty --
                personal data collection is opt-in per category, not
                opt-out.
        """
        self._registry = registry
        self._provider = provider
        self._enabled_categories = frozenset(enabled_categories)

    def collect_from(self, source_id: str) -> int:
        """Run one collection cycle for `source_id`.

        Args:
            source_id: The registered source to collect from.

        Returns:
            The number of newly stored points. Points dropped because
            their category is not in `enabled_categories`, or because
            `provider.exists(...)` is already True, do NOT contribute
            to this count and are not errors.

        Raises:
            PersonalDataCollectionError: If `source_id` is not
                registered, if the source's `collect()` raises, or if
                the provider's `store_if_new()` raises for any
                point. Never returns or raises `CommandResult` --
                `PersonalDataService` is the only layer that
                constructs `CommandResult`.
        """
        source = self._registry.get(source_id)
        if source is None:
            raise PersonalDataCollectionError(
                f"No personal data source registered under '{source_id}'."
            )

        try:
            points = source.collect()
        except Exception as exc:  # noqa: BLE001 - collection boundary: never crash the caller
            logger.error(f"Personal data collection failed for source '{source_id}': {exc}")
            raise PersonalDataCollectionError(
                f"Collection failed for source '{source_id}': {exc}"
            ) from exc

        stored_count = 0
        skipped_consent = 0
        skipped_duplicate = 0
        for point in points:
            if point.category not in self._enabled_categories:
                skipped_consent += 1
                continue
            try:
                stored = self._provider.store_if_new(point)
            except PersonalDataProviderError as exc:
                logger.error(
                    f"Personal data storage failed for source '{source_id}', "
                    f"point '{point.id}': {exc}"
                )
                raise PersonalDataCollectionError(
                    f"Storage failed for source '{source_id}', point '{point.id}': {exc}"
                ) from exc
            if stored:
                stored_count += 1
            else:
                skipped_duplicate += 1

        if skipped_consent:
            logger.warning(
                f"Personal data collection from '{source_id}': {skipped_consent} point(s) "
                "skipped (category not in personal_data.enabled_categories)."
            )
        logger.info(
            f"Personal data collection from '{source_id}': {stored_count} stored, "
            f"{skipped_consent} skipped (consent), {skipped_duplicate} skipped (duplicate)."
        )
        return stored_count

    def query(
        self, category: str, start: datetime | None = None, end: datetime | None = None
    ) -> list[PersonalDataPoint]:
        """Return persisted points for `category`, optionally bounded by time.

        Args:
            category: The category to query.
            start: If given, only points with `timestamp >= start`.
            end: If given, only points with `timestamp <= end`.

        Returns:
            Matching points, sorted by `timestamp`. Empty if
            `category` has never been collected.
        """
        return self._provider.query(category, start, end)

    def is_category_enabled(self, category: str) -> bool:
        """Return whether `category` is in the consent allowlist."""
        return category in self._enabled_categories

    def stats(self) -> dict[str, int]:
        """Return aggregate storage statistics via the underlying provider.

        Returns:
            `{"category_count": ..., "point_count": ...}` (see
            `PersonalDataProvider.stats()`).
        """
        return self._provider.stats()

    # ---------- Source registration (delegates to PersonalDataRegistry) ----------

    def register_source(self, source: PersonalDataSource) -> None:
        """Register `source` with this manager's `PersonalDataRegistry`.

        Args:
            source: The `PersonalDataSource` instance to register.

        Raises:
            PersonalDataRegistryError: If a source is already
                registered under the same `source_id`.
        """
        self._registry.register(source)

    def source_ids(self) -> list[str]:
        """Return every registered source's id, sorted."""
        return self._registry.source_ids()

    def is_source_registered(self, source_id: str) -> bool:
        """Return whether a source is registered under `source_id`."""
        return self._registry.is_registered(source_id)
