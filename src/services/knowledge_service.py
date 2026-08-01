"""Business logic for EP-024 Knowledge Base.

`KnowledgeService` is a core, LLM-independent service that exposes the
Knowledge Base's structured-record API to the CLI (`KnowledgeModule`).
Per EP-024's architecture, it depends only on:

    KnowledgeService -> KnowledgeManager -> KnowledgeProvider

It implements no business logic belonging to any other module and
never calls Embedding, Retrieval, RAG, Long-Term Memory, Semantic
Search, Context Compression, Planner, Reflection, Agent Framework,
Browser Automation, or Vector Database components. Knowledge Base
performs no reasoning of its own.

At construction, `KnowledgeService` reads its own 'knowledge.*' section
from Config (enabled, default_provider) and builds a default
`KnowledgeManager` registering a `KnowledgeCollectionProvider` (backed
by a fresh, in-process `KnowledgeCollection`) as the built-in "local"
provider -- mirroring how `MemoryService` builds its default
`MemoryManager` around a `MemoryStoreProvider` (EP-023).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.knowledge.knowledge_collection import CollectionStats, KnowledgeCollection
from src.core.knowledge.knowledge_manager import KnowledgeManager, ManagerStatus
from src.core.knowledge.knowledge_provider import (
    DEFAULT_COLLECTION,
    KnowledgeCollectionProvider,
    KnowledgeProviderError,
)
from src.core.knowledge.knowledge_record import KnowledgeRecord

DEFAULT_PROVIDER_NAME: str = "local"


@dataclass(frozen=True)
class KnowledgeStatus:
    """Result of `knowledge status`.

    Attributes:
        enabled: Whether the Knowledge subsystem is enabled
            ('knowledge.enabled').
        active_provider: Name of the currently active knowledge
            provider, or None if none is active.
        provider_count: Number of registered knowledge providers.
        total_records: Total number of records across every collection.
        collection_count: Number of collections with at least one record.
    """

    enabled: bool
    active_provider: str | None
    provider_count: int
    total_records: int
    collection_count: int


class KnowledgeService:
    """Coordinates the KnowledgeManager and exposes it as a CLI-friendly API.

    Depends only on KnowledgeManager (provider orchestration) and
    Config (its own 'knowledge.*' settings), matching EP-024's
    architecture: KnowledgeModule -> KnowledgeService -> KnowledgeManager
    -> KnowledgeProvider. Implements no domain logic belonging to any
    other Engineering Package.

    If 'knowledge.enabled' is False, the subsystem does not build a
    default provider and every mutating (and read) operation is
    rejected via CommandResult, matching the graceful-degradation
    pattern used by MemoryService/EmbeddingService.
    """

    def __init__(self, config: Config, manager: KnowledgeManager | None = None) -> None:
        """Initialize the KnowledgeService.

        Args:
            config: Loaded application configuration, used to resolve
                'knowledge.*' settings.
            manager: The KnowledgeManager to use for provider
                orchestration. If None, a default KnowledgeManager is
                built, registering a fresh KnowledgeCollection wrapped
                in a KnowledgeCollectionProvider as the built-in
                "local" provider, activated per
                'knowledge.default_provider' (defaults to "local").

        Raises:
            KnowledgeProviderError: If `manager` is None and
                'knowledge.default_provider' is not a non-empty string.
        """
        self._config = config
        self._manager = manager if manager is not None else self._build_default_manager(config)

    # ---------- Public API: records ----------

    def store(
        self,
        key: str,
        content: Any,
        collection: str = DEFAULT_COLLECTION,
        metadata: dict[str, Any] | None = None,
    ) -> CommandResult:
        """Create (or overwrite) a knowledge record.

        Args:
            key: The record's key, unique within `collection`.
            content: The knowledge payload to store.
            collection: The collection to store the record in.
            metadata: Optional caller-supplied metadata.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled
        if not key:
            return CommandResult(success=False, message="Key must not be empty.")

        try:
            self._manager.store(key, content, collection, metadata)
        except KnowledgeProviderError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(
            success=True, message=f"Record '{key}' stored in collection '{collection}'."
        )

    def load(self, key: str, collection: str = DEFAULT_COLLECTION) -> KnowledgeRecord | None:
        """Retrieve a single knowledge record.

        Args:
            key: The record's key.
            collection: The collection to look in.

        Returns:
            The stored KnowledgeRecord, or None if absent or the
            subsystem is disabled / has no active provider.
        """
        if not self._is_enabled():
            return None
        try:
            return self._manager.load(key, collection)
        except KnowledgeProviderError:
            return None

    def update(
        self,
        key: str,
        content: Any,
        collection: str = DEFAULT_COLLECTION,
        metadata: dict[str, Any] | None = None,
    ) -> CommandResult:
        """Update an existing knowledge record's content.

        Args:
            key: The record's key.
            content: The new content to store.
            collection: The collection the record belongs to.
            metadata: If given, replaces the record's metadata.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            updated = self._manager.update(key, content, collection, metadata)
        except KnowledgeProviderError as exc:
            return CommandResult(success=False, message=str(exc))
        if updated is None:
            return CommandResult(
                success=False,
                message=f"Record not found: '{key}' in collection '{collection}'.",
            )
        return CommandResult(success=True, message=f"Record '{key}' updated.")

    def delete(self, key: str, collection: str = DEFAULT_COLLECTION) -> CommandResult:
        """Delete a single knowledge record.

        Args:
            key: The record's key.
            collection: The collection to delete from.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            removed = self._manager.delete(key, collection)
        except KnowledgeProviderError as exc:
            return CommandResult(success=False, message=str(exc))
        if not removed:
            return CommandResult(
                success=False,
                message=f"Record not found: '{key}' in collection '{collection}'.",
            )
        return CommandResult(success=True, message=f"Record '{key}' deleted.")

    def clear(self, collection: str | None = None) -> CommandResult:
        """Clear all records in a collection, or every collection.

        Args:
            collection: The collection to clear. If None, every
                collection is cleared.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            count = self._manager.clear(collection)
        except KnowledgeProviderError as exc:
            return CommandResult(success=False, message=str(exc))
        scope = "all collections" if collection is None else f"collection '{collection}'"
        return CommandResult(success=True, message=f"Cleared {count} record(s) from {scope}.")

    def list_records(self, collection: str | None = None) -> list[KnowledgeRecord]:
        """List stored knowledge records.

        Args:
            collection: If given, only records in this collection are
                returned. If None, records from every collection are
                returned.

        Returns:
            The matching records, sorted by (collection, key). Empty
            if the subsystem is disabled or has no active provider.
        """
        if not self._is_enabled():
            return []
        try:
            return self._manager.list(collection)
        except KnowledgeProviderError:
            return []

    # ---------- Public API: collections ----------

    def collection_names(self) -> list[str]:
        """List every collection that currently has at least one record.

        Returns:
            A sorted list of collection names, empty if the subsystem
            is disabled or has no active provider.
        """
        if not self._is_enabled():
            return []
        try:
            return self._manager.collections()
        except KnowledgeProviderError:
            return []

    def collection_stats(self, collection: str | None = None) -> list[CollectionStats]:
        """Return per-collection statistics.

        Args:
            collection: If given, statistics for just this collection.
                If None, statistics for every non-empty collection.

        Returns:
            A list of CollectionStats, empty if the subsystem is
            disabled or has no active provider.
        """
        if not self._is_enabled():
            return []
        try:
            return self._manager.stats(collection)
        except KnowledgeProviderError:
            return []

    # ---------- Public API: status / providers ----------

    def status(self) -> KnowledgeStatus:
        """Return the `knowledge status` snapshot."""
        manager_status = self._manager.status()
        total_records = 0
        collection_count = 0
        if self._is_enabled():
            try:
                total_records = len(self._manager.list())
                collection_count = len(self._manager.collections())
            except KnowledgeProviderError:
                pass
        return KnowledgeStatus(
            enabled=self._is_enabled(),
            active_provider=manager_status.active_provider,
            provider_count=manager_status.provider_count,
            total_records=total_records,
            collection_count=collection_count,
        )

    def providers_status(self) -> ManagerStatus:
        """Return the status snapshot of every registered knowledge provider."""
        return self._manager.status()

    # ---------- Internal helpers: configuration ----------

    def _is_enabled(self) -> bool:
        """Return whether the Knowledge subsystem is enabled ('knowledge.enabled')."""
        return bool(self._config.get("knowledge.enabled", True))

    def _ensure_enabled(self) -> CommandResult | None:
        """Return a failing CommandResult if 'knowledge.enabled' is False.

        Returns:
            A failing CommandResult if the Knowledge subsystem is
            disabled, otherwise None (meaning the caller may proceed).
        """
        if self._is_enabled():
            return None
        logger.error("Knowledge operation rejected: Knowledge subsystem disabled.")
        return CommandResult(success=False, message="Knowledge subsystem disabled.")

    # ---------- Internal helpers: default manager ----------

    @staticmethod
    def _build_default_manager(config: Config) -> KnowledgeManager:
        """Build the default KnowledgeManager, registering a fresh "local" provider.

        Args:
            config: Used to resolve 'knowledge.default_provider'.

        Returns:
            A KnowledgeManager with a KnowledgeCollectionProvider
            registered under 'knowledge.default_provider' (defaults to
            "local") and activated.

        Raises:
            KnowledgeProviderError: If 'knowledge.default_provider' is
                not a non-empty string.
        """
        default_provider = config.get("knowledge.default_provider", DEFAULT_PROVIDER_NAME)
        if not isinstance(default_provider, str) or not default_provider:
            raise KnowledgeProviderError(
                "Invalid value for 'knowledge.default_provider': expected a non-empty "
                f"string, got {default_provider!r}."
            )

        manager = KnowledgeManager(default_provider=default_provider)
        manager.register(
            KnowledgeCollectionProvider(store=KnowledgeCollection(), name=default_provider)
        )
        return manager
