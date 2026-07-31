"""Memory package: EP-013 Memory & Context Manager + EP-023 Memory Manager.

EP-013 (`context.py`, `memory_store.py`, `memory_persistence.py`)
provides the namespaced, TTL-aware, optionally disk-persisted
key/value store consumed by `MemoryService`/`MemoryModule`.

EP-023 (`memory_provider.py`, `memory_manager.py`) adds a thin
orchestration layer on top: a `MemoryProvider` interface plus
`MemoryManager`, which registers providers, enables/disables them,
switches the active one, and exposes a unified store/load/delete/
clear/exists/list API delegating to whichever provider is active.
`MemoryStoreProvider` adapts the existing `MemoryStore` to this
interface so the default "memory" provider reuses EP-013's storage
rather than duplicating it. EP-023 implements no storage logic of its
own and no future provider (Knowledge Base, Long-Term Memory,
Semantic Search, External, etc.).

Public API:
    MemoryEntry -- EP-013's single stored key/value record.
    MemoryStore / MemoryStoreError -- EP-013's storage engine.
    MemoryPersistence -- EP-013's disk-backed load/auto-save lifecycle.
    MemoryProvider / MemoryProviderError -- EP-023's provider interface.
    MemoryStoreProvider -- EP-023's adapter around MemoryStore.
    ProviderStatus -- EP-023's per-provider status snapshot.
    MemoryManager / ManagerStatus -- EP-023's orchestration layer.
"""

from __future__ import annotations

from src.core.memory.context import DEFAULT_NAMESPACE, MemoryEntry
from src.core.memory.memory_manager import ManagerStatus, MemoryManager
from src.core.memory.memory_persistence import MemoryPersistence
from src.core.memory.memory_provider import (
    MemoryProvider,
    MemoryProviderError,
    MemoryStoreProvider,
    ProviderStatus,
)
from src.core.memory.memory_store import MemoryStore, MemoryStoreError

__all__ = [
    "DEFAULT_NAMESPACE",
    "MemoryEntry",
    "MemoryStore",
    "MemoryStoreError",
    "MemoryPersistence",
    "MemoryProvider",
    "MemoryProviderError",
    "MemoryStoreProvider",
    "ProviderStatus",
    "MemoryManager",
    "ManagerStatus",
]
