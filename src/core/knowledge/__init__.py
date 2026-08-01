"""Knowledge package: EP-024 Knowledge Base.

Knowledge Base manages structured project knowledge records, organized
into named collections. It performs no reasoning of its own and is not
responsible for Long-Term Memory, Semantic Search, Context Compression,
Planning, Reflection, Agent Memory, Vector Storage, Embeddings,
Retrieval, RAG, Conversation Intelligence, AI Completion, Browser
Automation, or any future Agent Framework.

`KnowledgeRecord` (`knowledge_record.py`) is the plain data model for a
single stored record. `KnowledgeCollection` (`knowledge_collection.py`)
is the thread-safe, collection-organized storage engine. `KnowledgeProvider`
/ `KnowledgeCollectionProvider` (`knowledge_provider.py`) define the
provider interface and the default adapter around `KnowledgeCollection`.
`KnowledgeManager` (`knowledge_manager.py`) is a thin orchestration
layer over registered providers -- registration, enable/disable,
active-provider switching, and delegation of the unified store/load/
update/delete/clear/list/collections/stats API -- mirroring the pattern
already used by EP-023's `MemoryManager`, scoped to Knowledge Base's own
responsibilities.

Public API:
    DEFAULT_COLLECTION -- The default collection name.
    KnowledgeRecord -- A single structured knowledge record.
    KnowledgeCollection / KnowledgeCollectionError -- The storage engine.
    CollectionStats -- Per-collection statistics snapshot.
    KnowledgeProvider / KnowledgeProviderError -- The provider interface.
    KnowledgeCollectionProvider -- The default KnowledgeCollection adapter.
    ProviderStatus -- Per-provider status snapshot.
    KnowledgeManager / ManagerStatus -- The orchestration layer.
"""

from __future__ import annotations

from src.core.knowledge.knowledge_collection import (
    CollectionStats,
    KnowledgeCollection,
    KnowledgeCollectionError,
)
from src.core.knowledge.knowledge_manager import KnowledgeManager, ManagerStatus
from src.core.knowledge.knowledge_provider import (
    DEFAULT_COLLECTION,
    KnowledgeCollectionProvider,
    KnowledgeProvider,
    KnowledgeProviderError,
    ProviderStatus,
)
from src.core.knowledge.knowledge_record import KnowledgeRecord

__all__ = [
    "DEFAULT_COLLECTION",
    "KnowledgeRecord",
    "KnowledgeCollection",
    "KnowledgeCollectionError",
    "CollectionStats",
    "KnowledgeProvider",
    "KnowledgeProviderError",
    "KnowledgeCollectionProvider",
    "ProviderStatus",
    "KnowledgeManager",
    "ManagerStatus",
]
