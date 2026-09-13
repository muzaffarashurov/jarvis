"""Business logic for EP-092 Personal Data Collection Framework.

`PersonalDataService` is a core, LLM-independent service exposing
Personal Data Collection's ingestion/query API in a CLI-friendly
shape, mirroring `KnowledgeService`'s
(`src/services/knowledge_service.py`) construction and
graceful-degradation pattern. Per EP-092's architecture, it depends
only on:

    PersonalDataService -> PersonalDataManager -> PersonalDataProvider

It implements no business logic belonging to any other Engineering
Package and never calls Embedding, Retrieval, RAG, Knowledge Base,
Semantic Search, Context Compression, Planner, Reflection, Agent
Framework, Browser Automation, or Vector Database components.

`CommandResult` is constructed exclusively in this module.
`PersonalDataManager` never returns or raises `CommandResult` -- this
service is the only place `PersonalDataCollectionError` is caught and
translated into one.

At construction, `PersonalDataService` reads its own 'personal_data.*'
section from Config ('enabled', 'enabled_categories') and builds a
default `PersonalDataManager` registering a fresh `PersonalDataRegistry`
and the Owner-approved `JsonlPersonalDataProvider` (STEP 1 design §21).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.personal_data.personal_data_manager import (
    PersonalDataCollectionError,
    PersonalDataManager,
)
from src.core.personal_data.personal_data_provider import JsonlPersonalDataProvider
from src.core.personal_data.personal_data_record import PersonalDataPoint
from src.core.personal_data.personal_data_registry import (
    PersonalDataRegistry,
    PersonalDataRegistryError,
)
from src.core.personal_data.personal_data_source import PersonalDataSource


@dataclass(frozen=True)
class PersonalDataStatus:
    """Result of `personal_data status`.

    Attributes:
        enabled: Whether the Personal Data Collection subsystem is
            enabled ('personal_data.enabled').
        enabled_categories: The consent allowlist
            ('personal_data.enabled_categories'), sorted.
        registered_sources: Registered `PersonalDataSource` ids, sorted.
        category_count: Number of categories with at least one stored
            point.
        point_count: Total points stored across every category.
    """

    enabled: bool
    enabled_categories: list[str]
    registered_sources: list[str]
    category_count: int
    point_count: int


class PersonalDataService:
    """Coordinates the PersonalDataManager and exposes it as a CLI-friendly API.

    Depends only on PersonalDataManager (collection/query
    orchestration) and Config (its own 'personal_data.*' settings).
    Implements no domain logic belonging to any other Engineering
    Package.

    If 'personal_data.enabled' is False, every mutating operation
    (`collect`, `register_source`) is rejected via CommandResult,
    matching the graceful-degradation pattern used by
    KnowledgeService/MemoryService. Reads (`query`, `status`) return
    empty results rather than raising, exactly as KnowledgeService's
    read methods do when disabled.
    """

    def __init__(self, config: Config, manager: PersonalDataManager | None = None) -> None:
        """Initialize the PersonalDataService.

        Args:
            config: Loaded application configuration, used to resolve
                'personal_data.*' settings.
            manager: The PersonalDataManager to use. If None, a
                default one is built: a fresh PersonalDataRegistry and
                a JsonlPersonalDataProvider (the Owner-approved
                persistence backend, STEP 1 design §21), with the
                consent allowlist resolved from
                'personal_data.enabled_categories'.
        """
        self._config = config
        self._manager = manager if manager is not None else self._build_default_manager(config)

    # ---------- Public API: collection ----------

    def register_source(self, source: PersonalDataSource) -> CommandResult:
        """Register a `PersonalDataSource` for later collection.

        Args:
            source: The source to register.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            self._manager.register_source(source)
        except PersonalDataRegistryError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(
            success=True, message=f"Personal data source '{source.source_id}' registered."
        )

    def collect(self, source_id: str) -> CommandResult:
        """Run one collection cycle for `source_id`.

        Args:
            source_id: The registered source to collect from.

        Returns:
            A CommandResult describing the outcome. On success, the
            message reports how many new points were stored.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            stored_count = self._manager.collect_from(source_id)
        except PersonalDataCollectionError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(
            success=True,
            message=f"Collected {stored_count} new point(s) from source '{source_id}'.",
        )

    # ---------- Public API: query ----------

    def query(
        self, category: str, start: datetime | None = None, end: datetime | None = None
    ) -> list[PersonalDataPoint]:
        """Return persisted points for `category`, optionally bounded by time.

        Args:
            category: The category to query.
            start: If given, only points with `timestamp >= start`.
            end: If given, only points with `timestamp <= end`.

        Returns:
            Matching points, sorted by `timestamp`. Empty if the
            subsystem is disabled or `category` has never been
            collected.
        """
        if not self._is_enabled():
            return []
        return self._manager.query(category, start, end)

    # ---------- Public API: status ----------

    def status(self) -> PersonalDataStatus:
        """Return the `personal_data status` snapshot."""
        stats = {"category_count": 0, "point_count": 0}
        registered_sources: list[str] = []
        if self._is_enabled():
            stats = self._manager.stats()
            registered_sources = self._manager.source_ids()
        return PersonalDataStatus(
            enabled=self._is_enabled(),
            enabled_categories=sorted(self._enabled_categories()),
            registered_sources=registered_sources,
            category_count=stats["category_count"],
            point_count=stats["point_count"],
        )

    # ---------- Internal helpers: configuration ----------

    def _is_enabled(self) -> bool:
        """Return whether the Personal Data subsystem is enabled ('personal_data.enabled')."""
        return bool(self._config.get("personal_data.enabled", True))

    def _enabled_categories(self) -> frozenset[str]:
        """Resolve the consent allowlist ('personal_data.enabled_categories')."""
        configured = self._config.get("personal_data.enabled_categories", [])
        if not isinstance(configured, list):
            return frozenset()
        return frozenset(str(category) for category in configured)

    def _ensure_enabled(self) -> CommandResult | None:
        """Return a failing CommandResult if 'personal_data.enabled' is False.

        Returns:
            A failing CommandResult if the Personal Data subsystem is
            disabled, otherwise None (meaning the caller may proceed).
        """
        if self._is_enabled():
            return None
        logger.error("Personal data operation rejected: Personal Data subsystem disabled.")
        return CommandResult(success=False, message="Personal Data subsystem disabled.")

    # ---------- Internal helpers: default manager ----------

    @staticmethod
    def _build_default_manager(config: Config) -> PersonalDataManager:
        """Build the default PersonalDataManager.

        Args:
            config: Used to resolve 'personal_data.enabled_categories'.

        Returns:
            A PersonalDataManager wrapping a fresh
            PersonalDataRegistry and a JsonlPersonalDataProvider (the
            Owner-approved persistence backend, STEP 1 design §21),
            with the consent allowlist resolved from
            'personal_data.enabled_categories'.
        """
        configured = config.get("personal_data.enabled_categories", [])
        enabled_categories = (
            frozenset(str(category) for category in configured)
            if isinstance(configured, list)
            else frozenset()
        )
        return PersonalDataManager(
            registry=PersonalDataRegistry(),
            provider=JsonlPersonalDataProvider(config),
            enabled_categories=enabled_categories,
        )
