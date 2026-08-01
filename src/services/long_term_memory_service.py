"""Business logic for EP-025 Long-Term Memory.

`LongTermMemoryService` is a core, LLM-independent service that exposes
Long-Term Memory's record-lifecycle API to the CLI
(`LongTermMemoryModule`). Per EP-025's architecture, it depends only on:

    LongTermMemoryService -> LongTermMemoryManager -> LongTermProvider

and integrates with EP-023's Memory Manager and EP-024's Knowledge Base
exclusively through their public APIs (`MemoryService.register_provider`,
`KnowledgeService.store`/`load`/`update`/`delete`/`list_records`) --
never touching either subsystem's internals.

At construction, `LongTermMemoryService` reads its own
'long_term_memory.*' section from Config (enabled, default_provider)
and builds a default `LongTermMemoryManager` registering a
`KnowledgeBackedLongTermProvider` (backed by the injected
`KnowledgeService`) as the built-in "knowledge" provider -- mirroring
how `KnowledgeService` builds its default `KnowledgeManager` around a
`KnowledgeCollectionProvider` (EP-024). If a `MemoryService` is also
provided, this service additionally registers a `LongTermMemoryProvider`
with it (via `MemoryService.register_provider`), extending EP-023's
Memory Manager per EP-025's brief. That extension is best-effort: if it
fails for any reason, Long-Term Memory itself still works, only the
'memory providers' integration is skipped (logged).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

from src.core.command_router import CommandResult
from src.core.config import Config
from src.core.long_term_memory.long_term_manager import (
    LongTermManagerStatus,
    LongTermMemoryManager,
)
from src.core.long_term_memory.long_term_provider import (
    DEFAULT_COLLECTION,
    KnowledgeBackedLongTermProvider,
    LongTermMemoryProvider,
    LongTermProviderError,
    LongTermStats,
)
from src.core.long_term_memory.long_term_record import LongTermRecord
from src.services.knowledge_service import KnowledgeService
from src.services.memory_service import MemoryService

DEFAULT_PROVIDER_NAME: str = "knowledge"
MEMORY_MANAGER_PROVIDER_NAME: str = "long_term"


@dataclass(frozen=True)
class LongTermMemoryStatus:
    """Result of `ltm status`.

    Attributes:
        enabled: Whether Long-Term Memory is enabled
            ('long_term_memory.enabled').
        active_provider: Name of the currently active long-term-memory
            provider, or None if none is active.
        provider_count: Number of registered long-term-memory providers.
        total: Total number of memories (active + archived).
        active: Number of memories with status STATUS_ACTIVE.
        archived: Number of memories with status STATUS_ARCHIVED.
        memory_manager_integrated: Whether a `LongTermMemoryProvider`
            was successfully registered with EP-023's Memory Manager.
    """

    enabled: bool
    active_provider: str | None
    provider_count: int
    total: int
    active: int
    archived: int
    memory_manager_integrated: bool


class LongTermMemoryService:
    """Coordinates the LongTermMemoryManager and exposes it as a CLI-friendly API.

    Depends only on LongTermMemoryManager (provider orchestration) and
    Config (its own 'long_term_memory.*' settings), matching EP-025's
    architecture: LongTermMemoryModule -> LongTermMemoryService ->
    LongTermMemoryManager -> LongTermProvider. Implements no domain
    logic belonging to any other Engineering Package, and performs no
    ranking, similarity search, embeddings, or AI reasoning.

    If 'long_term_memory.enabled' is False, every operation is rejected
    via CommandResult (or returns an empty/None read), matching the
    graceful-degradation pattern used by every other service in this
    project.
    """

    def __init__(
        self,
        config: Config,
        knowledge_service: KnowledgeService,
        memory_service: MemoryService | None = None,
        manager: LongTermMemoryManager | None = None,
    ) -> None:
        """Initialize the LongTermMemoryService.

        Args:
            config: Loaded application configuration, used to resolve
                'long_term_memory.*' settings.
            knowledge_service: The EP-024 KnowledgeService used to
                persist memories, if `manager` is None (a default
                LongTermMemoryManager is built around it).
            memory_service: If given, a `LongTermMemoryProvider` is
                registered with it (`MemoryService.register_provider`),
                extending EP-023's Memory Manager per EP-025's brief.
                This integration is best-effort: failures are logged,
                never raised.
            manager: The LongTermMemoryManager to use for provider
                orchestration. If None, a default LongTermMemoryManager
                is built, registering a `KnowledgeBackedLongTermProvider`
                (wrapping `knowledge_service`) as the built-in
                "knowledge" provider, activated per
                'long_term_memory.default_provider' (defaults to
                "knowledge").

        Raises:
            LongTermProviderError: If `manager` is None and
                'long_term_memory.default_provider' is not a non-empty
                string.
        """
        self._config = config
        self._manager = (
            manager if manager is not None else self._build_default_manager(config, knowledge_service)
        )
        self._memory_manager_integrated = self._try_register_with_memory_manager(memory_service)

    # ---------- Public API: memories ----------

    def store(
        self, memory_id: str, content: Any, metadata: dict[str, Any] | None = None
    ) -> CommandResult:
        """Create (or overwrite) an active long-term memory.

        Args:
            memory_id: The memory's unique identifier.
            content: The memory payload to store.
            metadata: Optional caller-supplied metadata.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled
        if not memory_id:
            return CommandResult(success=False, message="Memory id must not be empty.")

        try:
            self._manager.store(memory_id, content, metadata)
        except LongTermProviderError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Long-term memory '{memory_id}' stored.")

    def get(self, memory_id: str) -> LongTermRecord | None:
        """Retrieve a single long-term memory.

        Returns:
            The stored LongTermRecord, or None if absent or the
            subsystem is disabled / has no active provider.
        """
        if not self._is_enabled():
            return None
        try:
            return self._manager.get(memory_id)
        except LongTermProviderError:
            return None

    def update(
        self, memory_id: str, content: Any = None, metadata: dict[str, Any] | None = None
    ) -> CommandResult:
        """Update an existing long-term memory's content and/or metadata.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            updated = self._manager.update(memory_id, content, metadata)
        except LongTermProviderError as exc:
            return CommandResult(success=False, message=str(exc))
        if updated is None:
            return CommandResult(success=False, message=f"Memory not found: '{memory_id}'.")
        return CommandResult(success=True, message=f"Long-term memory '{memory_id}' updated.")

    def archive(self, memory_id: str) -> CommandResult:
        """Archive an existing long-term memory (a lifecycle transition, not a delete).

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            archived = self._manager.archive(memory_id)
        except LongTermProviderError as exc:
            return CommandResult(success=False, message=str(exc))
        if archived is None:
            return CommandResult(success=False, message=f"Memory not found: '{memory_id}'.")
        return CommandResult(success=True, message=f"Long-term memory '{memory_id}' archived.")

    def delete(self, memory_id: str) -> CommandResult:
        """Permanently delete a long-term memory.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            removed = self._manager.delete(memory_id)
        except LongTermProviderError as exc:
            return CommandResult(success=False, message=str(exc))
        if not removed:
            return CommandResult(success=False, message=f"Memory not found: '{memory_id}'.")
        return CommandResult(success=True, message=f"Long-term memory '{memory_id}' deleted.")

    def clear(self) -> CommandResult:
        """Permanently delete every long-term memory.

        Returns:
            A CommandResult describing the outcome.
        """
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            count = self._manager.clear()
        except LongTermProviderError as exc:
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Cleared {count} long-term memories.")

    def list_memories(self, status: str | None = None) -> list[LongTermRecord]:
        """List stored long-term memories.

        Args:
            status: If given (STATUS_ACTIVE or STATUS_ARCHIVED), only
                memories with that status are returned.

        Returns:
            The matching memories, sorted by id. Empty if the
            subsystem is disabled or has no active provider.
        """
        if not self._is_enabled():
            return []
        try:
            return self._manager.list(status)
        except LongTermProviderError:
            return []

    def stats(self) -> LongTermStats:
        """Return aggregate active/archived/total statistics.

        Returns:
            A LongTermStats with every count at zero if the subsystem
            is disabled or has no active provider.
        """
        if not self._is_enabled():
            return LongTermStats(total=0, active=0, archived=0)
        try:
            return self._manager.stats()
        except LongTermProviderError:
            return LongTermStats(total=0, active=0, archived=0)

    # ---------- Public API: status / providers ----------

    def status(self) -> LongTermMemoryStatus:
        """Return the `ltm status` snapshot."""
        manager_status = self._manager.status()
        stats = self.stats()
        return LongTermMemoryStatus(
            enabled=self._is_enabled(),
            active_provider=manager_status.active_provider,
            provider_count=manager_status.provider_count,
            total=stats.total,
            active=stats.active,
            archived=stats.archived,
            memory_manager_integrated=self._memory_manager_integrated,
        )

    def providers_status(self) -> LongTermManagerStatus:
        """Return the status snapshot of every registered long-term-memory provider."""
        return self._manager.status()

    # ---------- Internal helpers: configuration ----------

    def _is_enabled(self) -> bool:
        """Return whether Long-Term Memory is enabled ('long_term_memory.enabled')."""
        return bool(self._config.get("long_term_memory.enabled", True))

    def _ensure_enabled(self) -> CommandResult | None:
        """Return a failing CommandResult if 'long_term_memory.enabled' is False.

        Returns:
            A failing CommandResult if Long-Term Memory is disabled,
            otherwise None (meaning the caller may proceed).
        """
        if self._is_enabled():
            return None
        logger.error("Long-term memory operation rejected: subsystem disabled.")
        return CommandResult(success=False, message="Long-term memory subsystem disabled.")

    # ---------- Internal helpers: default manager / integration ----------

    @staticmethod
    def _build_default_manager(
        config: Config, knowledge_service: KnowledgeService
    ) -> LongTermMemoryManager:
        """Build the default LongTermMemoryManager around `knowledge_service`.

        Args:
            config: Used to resolve 'long_term_memory.default_provider'.
            knowledge_service: Wrapped (not copied) via
                `KnowledgeBackedLongTermProvider`, so the manager
                introduces no second persistent-storage subsystem.

        Returns:
            A LongTermMemoryManager with a KnowledgeBackedLongTermProvider
            registered under 'long_term_memory.default_provider'
            (defaults to "knowledge") and activated.

        Raises:
            LongTermProviderError: If
                'long_term_memory.default_provider' is not a non-empty
                string.
        """
        default_provider = config.get("long_term_memory.default_provider", DEFAULT_PROVIDER_NAME)
        if not isinstance(default_provider, str) or not default_provider:
            raise LongTermProviderError(
                "Invalid value for 'long_term_memory.default_provider': expected a "
                f"non-empty string, got {default_provider!r}."
            )

        manager = LongTermMemoryManager(default_provider=default_provider)
        manager.register(
            KnowledgeBackedLongTermProvider(
                knowledge_service=knowledge_service,
                collection=DEFAULT_COLLECTION,
                name=default_provider,
            )
        )
        return manager

    def _try_register_with_memory_manager(self, memory_service: MemoryService | None) -> bool:
        """Best-effort registration of a LongTermMemoryProvider with Memory Manager.

        Args:
            memory_service: The EP-023 MemoryService to extend, or
                None if Memory Manager integration was not requested
                (e.g. the Memory subsystem is disabled this run).

        Returns:
            True if registration succeeded, False otherwise (logged,
            never raised -- this integration is optional).
        """
        if memory_service is None:
            return False
        try:
            memory_service.register_provider(
                LongTermMemoryProvider(self._manager, name=MEMORY_MANAGER_PROVIDER_NAME)
            )
        except Exception as exc:  # noqa: BLE001 - best-effort integration, never fatal
            logger.error(f"Long-term memory could not extend Memory Manager: {exc}")
            return False
        logger.info(
            f"Long-term memory registered with Memory Manager as '{MEMORY_MANAGER_PROVIDER_NAME}'."
        )
        return True
