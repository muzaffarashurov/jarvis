# CHANGELOG.md

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog.

---

## v0.1.0-ep028

Released: 2026-08-03

### Added

- Agent Framework (src/core/agent/), a new independent package -- the
  central orchestration layer coordinating already-implemented
  Engineering Packages, with no planning, reasoning, task
  decomposition, tool execution, prompt construction, or AI provider
  call anywhere in the package:
  - AgentState (agent_state.py): lifecycle enum every agent reports
    through and transitions via (UNINITIALIZED, READY, RUNNING,
    SHUTDOWN, ERROR)
  - SubsystemInfo / AgentExecutionResult / AgentCancelResult
    (agent_result.py): plain data model for a registered subsystem's
    diagnostic snapshot, the outcome of accepting a request, and the
    outcome of attempting to cancel one
  - AgentProvider interface (agent_provider.py): unified
    initialize()/shutdown()/reset()/status()/execute()/cancel()/
    register_subsystem()/unregister_subsystem()/list_subsystems()
    contract every agent implementation must satisfy
  - DefaultAgentProvider (agent_provider.py): the built-in agent,
    registered under the name "jarvis" -- maintains lifecycle state and
    a name -> availability-check subsystem registry, and synchronously
    accepts and acknowledges every `execute()` call
    (`AgentExecutionResult.dispatched` is always False: there is no
    Planner yet to dispatch to). `cancel()` always reports nothing left
    to cancel for a known request id, since every request already
    completed synchronously
  - AgentManager (agent_manager.py): orchestration layer --
    register/select agents, enable/disable the subsystem, and resolve
    'agent.startup_mode' ("idle": leave the selected agent
    UNINITIALIZED until an explicit `agent initialize`; "auto":
    initialize it immediately once AgentEngine is constructed) from
    'agent.*' configuration
  - AgentEngine (agent_engine.py): the provider-independent pipeline
    forwarding every lifecycle/subsystem-registry/request call to the
    currently selected AgentProvider
  - src/core/agent/__init__.py: package-level public exports
- AgentService (src/services/agent_service.py): config-driven
  ('agent.enabled', 'agent.default_agent', 'agent.startup_mode')
  business logic, a thin CLI-facing wrapper around
  AgentManager/AgentEngine. Also exposes `execute()`/`cancel()` for
  future programmatic callers (e.g. a future Planner), not wired to
  any CLI command in this EP
- AgentModule (src/modules/agent_module.py): "agent" CLI namespace --
  help / status / subsystems / register / unregister / reset /
  initialize / shutdown
- config/config.yaml: new 'agent' section ('enabled', 'default_agent',
  'startup_mode')
- EP-028 test suite (tests/EP028/test_agent_framework.py)

### Changed

- src/bootstrap.py: registers AgentManager/AgentEngine/AgentService/
  AgentModule after Context Compression, wrapped in a try/except for
  AgentFrameworkError so invalid 'agent.*' configuration disables the
  Agent Framework subsystem for that run (logged) instead of crashing
  startup. Every subsystem service already built earlier in this
  method (Embedding, RAG, Memory, Knowledge Base, Long-Term Memory,
  Semantic Search, Context Compression) that is available this run is
  registered with the Agent Framework's subsystem registry, by name,
  bound to that service's own public `status().enabled` -- read-only,
  no private access. A subsystem unavailable this run is simply
  skipped, matching every other soft dependency already present in
  this method; one subsystem's registration failing is logged and
  skipped rather than aborting the whole Agent Framework build. No
  change to startup order or wiring for any other subsystem.
- src/modules/test_module.py: registers the EP-028 test suite so
  'test EP028' and 'test all' pick it up

### Improved

- Every completed Engineering Package's enabled/disabled status is now
  visible in one place ('agent subsystems'), without any new status
  storage -- each subsystem's own `status().enabled` is read live, on
  demand.

---



Released: 2026-08-03

### Added

- Context Compression subsystem (src/core/context_compression/), a new
  independent package:
  - ContextChunk / CompressionResult (compression_result.py): plain
    data model for one unit of input context (text, index, metadata)
    and the outcome of compressing an ordered chunk sequence (chunks,
    original/compressed chunk and character counts, estimated tokens,
    deduplicated-chunk count, truncated flag)
  - CompressionProvider interface (compression_provider.py): unified
    compress()/estimate_tokens()/status() contract for every
    context-compression provider
  - DefaultCompressionProvider (compression_provider.py): the built-in
    provider, registered under the name "compression" -- deterministic,
    purely-arithmetic deduplication (whole-chunk, then paragraph-level
    across chunks) followed by max-chunk and max-character enforcement,
    with ordering and metadata preserved throughout; token count is
    estimated with a documented, fixed characters-per-token heuristic,
    never a real tokenizer or network call. No AI reasoning, no
    summarization, no rewriting of surviving text (only truncation, to
    fit a character budget)
  - CompressionManager (compression_manager.py): orchestration layer --
    register/select compression providers, enable/disable the
    subsystem, and own the default `max_context_characters` /
    `max_chunks` / `deduplicate` parameters read from
    'context_compression.*' configuration
  - CompressionEngine (compression_engine.py): the
    text/chunks -> compressed-result pipeline -- splits raw text into
    paragraph chunks, or accepts pre-built chunks (e.g. one per EP-026
    `SemanticResult`), and delegates deduplication/ordering/limit
    enforcement to the active CompressionProvider. Also exposes
    `compress_query()`, an optional integration point that runs a query
    through EP-026's SemanticEngine (public `search()` method and
    `SemanticResult` fields only) and compresses the results in one
    call -- entirely optional; `compress_text()`/`compress_chunks()`/
    `compress_semantic_results()` work with no Semantic Search
    dependency at all
  - src/core/context_compression/__init__.py: package-level public
    exports
- CompressionService (src/services/context_compression_service.py):
  config-driven ('context_compression.enabled',
  'context_compression.default_provider',
  'context_compression.max_context_characters',
  'context_compression.max_chunks', 'context_compression.deduplicate')
  business logic, a thin CLI-facing wrapper around
  CompressionManager/CompressionEngine
- ContextCompressionModule (src/modules/context_compression_module.py):
  "compression" CLI namespace -- help / status / providers / use /
  analyze / compress / limits
- config/config.yaml: new 'context_compression' section ('enabled',
  'default_provider', 'max_context_characters', 'max_chunks',
  'deduplicate')
- EP-027 test suite (tests/EP027/test_context_compression.py)

### Changed

- src/bootstrap.py: registers CompressionManager/CompressionEngine/
  CompressionService/ContextCompressionModule after Semantic Search,
  wrapped in a try/except for ContextCompressionError so invalid
  'context_compression.*' configuration disables the Context
  Compression subsystem for that run (logged) instead of crashing
  startup. Context Compression has no hard dependency on Semantic
  Search, the Embedding Engine, Knowledge Base, or Long-Term Memory --
  `compress_text()`/`compress_chunks()` work on raw text/chunks alone,
  so the subsystem is wired unconditionally; only the optional
  `compress_query()` path is affected if Semantic Search is
  unavailable this run. The SemanticEngine instance built for EP-026
  (when available) is captured locally and passed to CompressionEngine,
  read-only, through its public `search()` method only. No change to
  startup order or wiring for any other subsystem.
- src/modules/test_module.py: registers the EP-027 test suite so
  'test EP027' and 'test all' pick it up

### Improved

- Context assembled from EP-026 Semantic Search (or from any raw text)
  can now be deduplicated and capped to a maximum size before it is
  used elsewhere, reusing EP-026's public `SemanticResult` model
  instead of introducing a new retrieval pipeline or new storage.

---



Released: 2026-08-02

### Added

- Semantic Search subsystem (src/core/semantic/), a new independent
  package:
  - SemanticCandidate / SemanticResult (semantic_result.py): plain
    data model for one searchable record (source, identifier, text,
    vector, metadata) and one ranked match (source, identifier, text,
    score, metadata)
  - SemanticProvider interface (semantic_provider.py): unified
    search()/rank()/status() contract for every semantic search
    provider
  - DefaultSemanticProvider (semantic_provider.py): the built-in
    provider, registered under the name "semantic" -- brute-force
    cosine similarity over already-embedded candidates, no external
    index, no network access, no AI reasoning
  - SemanticManager (semantic_manager.py): orchestration layer --
    register/select semantic providers, enable/disable the subsystem,
    expose status, and own the default `top_k` /
    `similarity_threshold` search parameters read from
    'semantic.*' configuration
  - SemanticEngine (semantic_engine.py): the query -> candidates ->
    ranked-results pipeline -- generates a query vector via EP-021's
    EmbeddingEngine, gathers and embeds candidates from EP-024's
    KnowledgeService and EP-025's LongTermMemoryService (both public
    APIs only, both optional), deduplicates any record reachable
    through both (see Fixed), and delegates scoring/ranking to the
    active SemanticProvider
  - Placeholder-embedding-provider detection
    (`SemanticEngine.embedding_provider_warning()`): EP-021's only
    offline, always-available embedding provider ("local") hashes
    each text as a whole via SHA-256, so by the avalanche property any
    two non-identical texts -- related or not -- score as uncorrelated
    noise; only byte-identical text is meaningfully matched. When that
    specific, well-known provider is active (detected via
    EmbeddingManager's public `provider_name()`, never by touching any
    private state), a clear warning is surfaced through
    `SemanticService.status()` and `semantic status` explaining the
    limitation and how to get genuine semantic search (configure a
    real embedding provider). 'semantic.similarity_threshold' is used
    exactly as configured for every provider, always -- this module
    never adjusts it (an earlier iteration of this feature relaxed the
    threshold toward 0.0 for the placeholder provider; broader testing
    proved that only admits a coin-flip ~50% of unrelated candidates
    as if they were meaningful matches, which is worse than returning
    nothing, so that adjustment was removed before release)
  - src/core/semantic/__init__.py: package-level public exports
- SemanticService (src/services/semantic_service.py): config-driven
  ('semantic.enabled', 'semantic.default_provider', 'semantic.top_k',
  'semantic.similarity_threshold') business logic, a thin CLI-facing
  wrapper around SemanticManager/SemanticEngine
- SemanticModule (src/modules/semantic_module.py): "semantic" CLI
  namespace -- help / status / providers / use / search / threshold
- config/config.yaml: new 'semantic' section ('enabled',
  'default_provider', 'top_k', 'similarity_threshold')
- EP-026 test suite (tests/EP026/test_semantic_search.py)

### Changed

- src/bootstrap.py: registers SemanticManager/SemanticEngine/
  SemanticService/SemanticModule after the RAG Engine, wrapped in a
  try/except for SemanticError so invalid 'semantic.*' configuration
  disables the Semantic Search subsystem for that run (logged) instead
  of crashing startup. Because generating a query/candidate vector is
  a hard dependency on the Embedding Engine, Semantic Search also
  disables itself gracefully (logged) if the Embedding Engine is
  unavailable this run -- mirroring exactly how EP-022's RAG Engine
  already degrades in the same situation. Knowledge Base and Long-Term
  Memory are soft dependencies: either being unavailable this run only
  narrows what Semantic Search can find, it never disables the
  subsystem itself. EmbeddingManager (already built for the Embedding
  Engine/RAG Engine) is also passed to SemanticEngine, read-only, for
  placeholder-provider detection. No change to startup order or wiring
  for any other subsystem.
- src/modules/test_module.py: registers the EP-026 test suite so
  'test EP026' and 'test all' pick it up

### Improved

- Knowledge Base and Long-Term Memory records can now be found by
  meaning rather than only by exact key/id lookup, reusing EP-021's
  Embedding Engine and EP-024/EP-025's public read APIs instead of
  introducing a new storage engine or a new embedding pipeline

### Fixed

- SemanticManager.current_provider_name() incorrectly returned the
  resolved provider name (e.g. "semantic") even when
  'semantic.enabled: false' was set from startup, contradicting
  is_enabled() and get_current() (which already correctly returned
  False/None). Now consistently returns None in both disablement
  paths -- config-time and the runtime disable() call.
- A record reachable through both KnowledgeService.list_records() and
  LongTermMemoryService.list_memories() -- which happens for every
  Long-Term Memory record, since EP-025's
  KnowledgeBackedLongTermProvider persists them inside KnowledgeService's
  own storage under the record's own id as the key -- was returned
  twice in search results, once under each source label. Long-Term
  Memory records are now deduplicated against Knowledge Base results
  by identifier, keeping the more specific `long_term_memory` label.

### Compatibility

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its signature/
behavior changed. Introduces no duplicate embedding/knowledge/memory/
retrieval subsystem -- Semantic Search performs no answer generation,
AI provider calls, prompt construction, context compression, planning,
reflection, or reasoning, has no dependency on the RAG Engine, any AI
Provider, the Prompt Engine, Browser Automation, Tool Calling, the
Conversation Engine, or any future Agent Framework component, and
SemanticManager owns no record/vector storage state of its own.

---

## v0.1.0-ep025

Released: 2026-08-01

### Added

- Long-Term Memory subsystem (src/core/long_term_memory/), a new
  independent package:
  - LongTermRecord (long_term_record.py): plain data model for a single
    long-lived memory (id, content, metadata, status, timestamps,
    archived_at)
  - LongTermProvider interface (long_term_provider.py): unified
    store/get/update/archive/delete/clear/list/stats contract for
    every long-term-memory provider
  - KnowledgeBackedLongTermProvider (long_term_provider.py): the default
    provider, persisting memories through EP-024's KnowledgeService
    public API inside a dedicated "long_term_memory" collection --
    introduces no new storage engine
  - LongTermMemoryProvider (long_term_provider.py): adapts Long-Term
    Memory to EP-023's MemoryProvider interface so it can be registered
    with the Memory Manager
  - LongTermMemoryManager (long_term_manager.py): orchestration layer --
    register/unregister providers, enable/disable, switch the active
    provider, expose status, and delegate the unified long-term-memory
    API to whichever provider is active
  - src/core/long_term_memory/__init__.py: package-level public exports
- LongTermMemoryService (src/services/long_term_memory_service.py):
  config-driven ('long_term_memory.enabled',
  'long_term_memory.default_provider') business logic, building a
  default LongTermMemoryManager around a KnowledgeBackedLongTermProvider
  named "knowledge", and best-effort registering a LongTermMemoryProvider
  with EP-023's Memory Manager when available
- LongTermMemoryModule (src/modules/long_term_memory_module.py): "ltm"
  CLI namespace -- status / list / info / archive / clear / statistics
  / help
- config/config.yaml: new 'long_term_memory' section ('enabled',
  'default_provider')
- EP-025 test suite (tests/EP025/test_long_term_memory.py)

### Changed

- src/services/memory_service.py: added `register_provider(provider,
  enabled=True)`, a thin pass-through to `MemoryManager.register` --
  the public extension point EP-025 uses to register its
  LongTermMemoryProvider without reaching into MemoryService's
  internals. Every existing MemoryService method, CLI command, and
  public signature is unchanged.
- src/bootstrap.py: registers LongTermMemoryService/LongTermMemoryModule
  after Memory and Knowledge Base, wrapped in a try/except for
  LongTermProviderError so invalid 'long_term_memory.default_provider'
  configuration disables the Long-Term Memory subsystem for that run
  (logged) instead of crashing startup. Because Long-Term Memory's
  persistence is a hard dependency on Knowledge Base, it also disables
  itself gracefully (logged) if Knowledge Base is unavailable this run.
  No change to startup order or wiring for any other subsystem.
- src/modules/test_module.py: registers the EP-025 test suite so
  'test EP025' and 'test all' pick it up

### Improved

- Important memories can now be persisted long-term and moved through
  an active/archived lifecycle, decoupled from EP-023's short-lived
  Memory Manager store and EP-024's general-purpose Knowledge Base
  collections, while reusing both through their public APIs instead of
  introducing a third storage engine

### Fixed

-

### Compatibility

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its signature/
behavior changed, aside from the additive `MemoryService.register_provider`
method. Introduces no duplicate memory/knowledge/embedding/retrieval
subsystem -- Long-Term Memory performs no ranking, similarity search,
embeddings, or AI reasoning, has no dependency on Semantic Search,
Context Compression, Reflection, Planner, Agent Framework, Browser
Automation, Vector Database, Embedding, Retrieval, RAG, or any future
EP, and LongTermMemoryManager owns no storage state of its own.

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