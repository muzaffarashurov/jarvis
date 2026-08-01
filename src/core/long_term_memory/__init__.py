"""Long-term memory package: EP-025 Long-Term Memory.

Long-Term Memory is responsible for persistent storage and lifecycle
management (active/archived) of important, long-lived memories. It
performs no ranking, similarity search, embeddings, or AI reasoning,
and is not responsible for Semantic Search, Context Compression,
Reflection, Planning, Conversation Intelligence, Agent Memory, Browser
Automation, AI Completion, Vector Storage, Retrieval, or RAG.

`LongTermRecord` (`long_term_record.py`) is the plain data model for a
single long-lived memory. `LongTermProvider` /
`KnowledgeBackedLongTermProvider` (`long_term_provider.py`) define the
provider interface and its default adapter, which persists memories
through EP-024's `KnowledgeService` public API rather than introducing
a new storage engine. `LongTermMemoryProvider` (also in
`long_term_provider.py`) adapts Long-Term Memory to EP-023's
`MemoryProvider` interface so it can be registered with the Memory
Manager (via `MemoryService.register_provider`), extending EP-023
without any change to `MemoryManager` itself. `LongTermMemoryManager`
(`long_term_manager.py`) is a thin orchestration layer over registered
`LongTermProvider` instances -- registration, enable/disable,
active-provider switching, and delegation of the unified store/get/
update/archive/delete/clear/list/stats API -- mirroring the pattern
already used by EP-023's `MemoryManager` and EP-024's
`KnowledgeManager`.

Public API:
    STATUS_ACTIVE / STATUS_ARCHIVED -- Lifecycle status constants.
    LongTermRecord -- A single long-lived memory.
    LongTermProvider / LongTermProviderError -- The provider interface.
    KnowledgeBackedLongTermProvider -- The default Knowledge-Base-backed adapter.
    LongTermMemoryProvider -- The EP-023 MemoryProvider adapter.
    LongTermProviderStatus -- Per-provider status snapshot.
    LongTermStats -- Aggregate active/archived/total statistics.
    LongTermMemoryManager / LongTermManagerStatus -- The orchestration layer.
"""

from __future__ import annotations

from src.core.long_term_memory.long_term_manager import (
    LongTermManagerStatus,
    LongTermMemoryManager,
)
from src.core.long_term_memory.long_term_provider import (
    DEFAULT_COLLECTION,
    KnowledgeBackedLongTermProvider,
    LongTermMemoryProvider,
    LongTermProvider,
    LongTermProviderError,
    LongTermProviderStatus,
    LongTermStats,
)
from src.core.long_term_memory.long_term_record import (
    STATUS_ACTIVE,
    STATUS_ARCHIVED,
    LongTermRecord,
)

__all__ = [
    "STATUS_ACTIVE",
    "STATUS_ARCHIVED",
    "DEFAULT_COLLECTION",
    "LongTermRecord",
    "LongTermProvider",
    "LongTermProviderError",
    "KnowledgeBackedLongTermProvider",
    "LongTermMemoryProvider",
    "LongTermProviderStatus",
    "LongTermStats",
    "LongTermMemoryManager",
    "LongTermManagerStatus",
]
