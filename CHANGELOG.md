# CHANGELOG.md

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog.

---

## v0.1.0-ep024

Released: 2026-08-01

### Added

- Knowledge Base subsystem (src/core/knowledge/), a new independent package:
  - KnowledgeRecord (knowledge_record.py): plain data model for a single
    structured knowledge record (key, content, collection, metadata,
    timestamps)
  - KnowledgeCollection (knowledge_collection.py): thread-safe,
    collection-organized storage engine -- store/load/update/delete/clear/
    list plus per-collection statistics
  - KnowledgeProvider interface and KnowledgeCollectionProvider adapter
    (knowledge_provider.py), mirroring EP-023's MemoryProvider pattern
  - KnowledgeManager (knowledge_manager.py): orchestration layer --
    register/unregister providers, enable/disable, switch the active
    provider, expose status, and delegate the unified knowledge API to
    whichever provider is active
  - src/core/knowledge/__init__.py: package-level public exports
- KnowledgeService (src/services/knowledge_service.py): config-driven
  ('knowledge.enabled', 'knowledge.default_provider') business logic,
  building a default KnowledgeManager around a KnowledgeCollectionProvider
  named "local"
- KnowledgeModule (src/modules/knowledge_module.py): "knowledge" CLI
  namespace -- status / collections / list / info / clear / help
- config/config.yaml: new 'knowledge' section ('enabled', 'default_provider')
- EP-024 test suite (tests/EP024/test_knowledge_base.py)

### Changed

- src/bootstrap.py: registers KnowledgeService/KnowledgeModule, wrapped in
  a try/except for KnowledgeProviderError so invalid
  'knowledge.default_provider' configuration disables the Knowledge
  subsystem for that run (logged) instead of crashing startup, mirroring
  the Memory/Embedding/RAG degrade-gracefully pattern. No change to
  startup order or to any other subsystem's wiring.
- src/modules/test_module.py: registers the EP-024 test suite so
  'test EP024' and 'test all' pick it up

### Improved

- Structured project knowledge (docs, facts, reference records) now has a
  dedicated home, decoupled from EP-023's Memory Manager, EP-021's
  Embedding, and EP-022's RAG Engine, so those subsystems can evolve
  independently of how knowledge is organized into collections

### Fixed

-

### Compatibility

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its signature/
behavior changed. Introduces no duplicate memory/embedding/retrieval
subsystem -- Knowledge Base performs no reasoning, has no dependency on
Embedding, Retrieval, RAG, Long-Term Memory, Semantic Search, Context
Compression, Planner, Reflection, Agent Framework, Browser Automation, or
Vector Database, and KnowledgeManager owns no storage state of its own.

---



Released: 2026-07-31

### Added

- MemoryProvider interface (src/core/memory/memory_provider.py):
  store/load/delete/clear/exists/list contract every memory provider must
  implement
- MemoryStoreProvider (src/core/memory/memory_provider.py): adapter wrapping
  the existing (EP-013) MemoryStore as the built-in "memory" provider,
  introducing no new storage logic
- MemoryManager (src/core/memory/memory_manager.py): orchestration layer --
  register/unregister providers, enable/disable, switch the active
  provider, expose status, and delegate the unified memory API to whichever
  provider is active
- src/core/memory/__init__.py: package-level exports for both EP-013 and
  EP-023 public symbols
- CLI integration: memory providers / memory use <provider>
- EP-023 test suite (tests/EP023/test_memory_manager.py)

### Changed

- src/services/memory_service.py: added an optional `manager` constructor
  parameter (MemoryManager | None = None, default preserves prior
  behavior); composes a MemoryManager that registers the same MemoryStore
  as the "memory" provider; added `providers_status()`, `current_provider()`
  and `use_provider()`. Every existing EP-013 method and signature is
  unchanged.
- src/modules/memory_module.py: added "providers" and "use" CLI actions and
  updated help text. Every existing EP-013 command is unchanged.
- config/config.yaml: added 'memory.default_provider' ("memory") to the
  existing 'memory' section
- src/bootstrap.py: wrapped the existing Memory subsystem wiring in a
  try/except for MemoryProviderError, so invalid 'memory.default_provider'
  configuration disables the Memory subsystem for that run (logged) instead
  of crashing startup, mirroring the Embedding/RAG degrade-gracefully
  pattern. No change to startup order or to any other subsystem's wiring.
- src/modules/test_module.py: registers the EP-023 test suite so
  'test EP023' and 'test all' pick it up

### Improved

- Memory now has a single, provider-agnostic API surface
  (register/enable/disable/switch/status) that future providers
  (Knowledge Base, Long-Term Memory, External, etc.) can register against
  without any caller needing to change

### Fixed

-

### Compatibility

Fully backward compatible with EP-013. No existing MemoryService method,
MemoryStore behavior, or `memory` CLI command was renamed, removed, or had
its signature/behavior changed. Introduces no second memory subsystem --
MemoryManager owns no storage state of its own and delegates every
operation to the same MemoryStore EP-013 already manages.

---

## v0.1.0-ep022

Released: 2026-07-31

### Added

- RAG Engine (src/core/rag/rag_engine.py)
- RAG Manager (src/core/rag/rag_manager.py)
- RagProviderInfo / RagContextItem / RagResult domain models
- RAG Service
- RAG Module
- CLI integration: rag help / status / query / context / provider / use
- EP-022 test suite (tests/EP022/test_rag_engine.py)

### Changed

- src/bootstrap.py: wires RagManager/RagService/RagModule into the command
  router, mirroring the Embedding Engine's degrade-gracefully-on-invalid-config
  pattern
- config/config.yaml: added a 'rag' configuration section (enabled, top_k,
  max_context_characters)
- src/modules/test_module.py: registers the EP-022 test suite so 'test EP022'
  and 'test all' pick it up

### Improved

- Retrieval (EP-020) and embedding (EP-021) are now composed into a single,
  reusable context-generation pipeline consumable by future EPs

### Fixed

-

### Compatibility

Backward compatible with EP-019, EP-020 and EP-021. Does not modify the
Project Index Engine, the Retrieval Engine, or the Embedding Engine. The RAG
Engine calls no AI provider and performs no chat completion.

---

## v0.1.0-ep021

Released: 2026-07-30

### Added

- Embedding Engine
- EmbeddingProvider interface
- Embedding Manager
- Embedding Service
- Embedding Module
- Local embedding provider (deterministic, offline)
- Cloud embedding provider (configuration-driven placeholder)
- CLI integration
- Embedding tests

### Improved

- Provider-independent architecture pattern extended beyond chat completion

### Fixed

-

### Compatibility

Backward compatible with EP-020. Does not modify the Retrieval Engine.

---

## v0.1.0-ep020

Released: 2026-07-30

### Added

- Retrieval Engine
- Retrieval Service
- Retrieval Module
- Search API
- CLI integration
- Retrieval tests

### Improved

- AI infrastructure
- Project navigation
- Knowledge retrieval pipeline

### Fixed

- Internal integration issues between EP-019 and EP-020

### Compatibility

Backward compatible with EP-019.

---

# [Unreleased]

## Added

-

## Changed

-

## Fixed

-

---

# [0.1.0-alpha] - 2026-07-28

## Added

- Interactive Shell (EP-002)
- Process Manager (EP-003)
- AI Provider Framework (EP-014)
- AI Providers (EP-015)
- Conversation Engine (EP-016)
- Prompt Engine (EP-017)
- Universal Context Engine (EP-018)
- PROJECT_MANIFEST.md
- Architecture documentation
- Engineering documentation

## EP-019

Added Project Index Engine.

Features:

- ProjectIndexer
- ChunkBuilder
- JsonIndexStorage
- MemoryIndexStorage
- Index CLI
- Shared PROJECT_MANIFEST parser

## Changed

- Project documentation reorganized.
- Architecture documentation moved to `docs/architecture/`.
- Engineering documentation moved to `docs/engineering/`.
- Context loading redesigned to use `PROJECT_MANIFEST.md` as the single entry point.

## Fixed

- Prompt size budgeting.
- Conversation history budgeting.
- Context Loader document discovery.
- Provider-independent context loading.
- Gemini prompt overflow issues.

---

Future releases will be documented here.