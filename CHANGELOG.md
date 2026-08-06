# CHANGELOG.md

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog.

---

## v0.1.0-ep032

Released: 2026-08-06

### Added

- Multi-Agent Collaboration (src/core/collaboration/), a new
  independent package -- implements the Multi-Agent Coordinator
  explicitly deferred by EP-028 through EP-030's own docstrings:
  deterministic broadcast of a single request across every agent
  currently registered with EP-028's Agent Framework, with each
  agent's own `AgentExecutionResult` collected into a uniform
  outcome. No AI reasoning, no negotiation, and no inter-agent
  messaging anywhere in the package:
  - AgentOutcomeStatus / AgentOutcome / CollaborationResult
    (collaboration_result.py): plain data model for the outcome of
    dispatching to a single agent and of a whole collaborate() call
  - CollaborationProvider interface (collaboration_provider.py):
    unified `collaborate(request, metadata, agents) -> CollaborationResult`
    contract every multi-agent distribution strategy must implement
  - DefaultCollaborationProvider (collaboration_provider.py): the
    built-in provider, registered under the name "collaboration" --
    sorts agents by name, dispatches to every currently READY agent
    through its own public `execute()`, reports every non-READY agent
    UNAVAILABLE without calling it, and isolates a single agent's
    raised `AgentFrameworkError` so it never breaks the other agents'
    outcomes
  - CollaborationManager (collaboration_manager.py): orchestration
    layer -- register/select collaboration providers, enable/disable
    the subsystem, and resolve 'collaboration.*' configuration. Owns
    no reference to `AgentManager` or its catalog
  - CollaborationEngine (collaboration_engine.py): the
    provider-independent pipeline -- reads the live agent catalog from
    EP-028's `AgentManager` through its public `list_providers()`
    method only, and dispatches to the active CollaborationProvider
  - src/core/collaboration/__init__.py: package-level public exports
  - EP-032 test suite (tests/EP032/test_collaboration_engine.py)
- CollaborationService (src/services/collaboration_service.py):
  config-driven ('collaboration.enabled',
  'collaboration.default_provider') business logic, a thin CLI-facing
  wrapper around CollaborationManager/CollaborationEngine
- CollaborationModule (src/modules/collaboration_module.py):
  "collaborate" CLI namespace -- help / status / providers / agents /
  use / run
- config/config.yaml: new 'collaboration' section ('enabled',
  'default_provider')

### Changed

- src/bootstrap.py: registers CollaborationManager/CollaborationEngine/
  CollaborationService/CollaborationModule after the Tool Engine,
  wrapped in a try/except for CollaborationError so invalid
  'collaboration.*' configuration disables the Multi-Agent
  Collaboration subsystem for that run (logged) instead of crashing
  startup. The live AgentManager built for EP-028 is captured locally
  (`agent_manager_for_collaboration`) and forwarded to
  CollaborationEngine through its existing public `list_providers()`
  method only -- no file under src/core/agent/ is modified, no
  existing wiring step is reordered or removed. Multi-Agent
  Collaboration has a hard dependency on a live `AgentManager`
  existing this run (a genuine `AgentFrameworkError` above skips this
  subsystem entirely), but not on the Agent Framework being *enabled*
  -- a disabled Agent Framework still constructs a valid `AgentManager`
  with its catalog intact, so Multi-Agent Collaboration still wires up
  and honestly reports every agent UNAVAILABLE
- src/modules/test_module.py: registers the EP-032 test suite so
  'test EP032' and 'test all' pick it up

### Improved

- A request can now be broadcast to every currently registered agent
  in one call and every individual agent's outcome inspected through
  the "collaborate" CLI namespace -- without any new AI reasoning,
  negotiation, or inter-agent messaging component being introduced,
  and without changing any prior release's default behavior

---

## v0.1.0-ep031

Released: 2026-08-05

### Added

- Tool Engine (src/core/tool/), a new independent package -- turns an
  already-identified `(subsystem, action)` reference into a real
  invocation of an already-implemented Engineering Package's public
  API, with no AI reasoning, no planning, no plan walking, and no
  dispatch-order/failure-policy logic anywhere in the package:
  - Tool (tool.py): plain catalog-entry data model -- id, name,
    description, subsystem, action, a pre-bound zero-argument handler
    closure, and an enabled flag
  - ToolStatus / ToolResult (tool_result.py): plain data model for the
    outcome of a single tool invocation
  - ToolRegistry (tool_registry.py): thread-safe catalog of registered
    tools -- register/unregister/get/find/find_for_step/list, mirroring
    PluginRegistry/ProcessRegistry
  - ToolProvider interface (tool_provider.py): unified
    `invoke_tool(tool) -> ToolResult` contract every invocation
    strategy must implement
  - DefaultToolProvider (tool_provider.py): the built-in provider,
    registered under the name "tool_engine" -- invokes a Tool's
    pre-bound handler and translates any raised exception into a
    failed ToolResult rather than letting it propagate
  - ToolManager (tool_manager.py): orchestration layer --
    register/select tool providers, own the ToolRegistry, enable/
    disable the subsystem, and resolve 'tool.*' configuration
  - ToolEngine (tool_engine.py): the provider-independent
    lookup -> real-invocation pipeline -- resolves a tool by id or by
    a `(subsystem, action)` pair and dispatches it to the active
    ToolProvider
  - ToolExecutionProvider (tool_execution_provider.py): the bridge
    adapter implementing EP-030's `PlanExecutionProvider` ABC -- the
    "Tool-Engine-backed provider" EP-030's own docstrings anticipated.
    The only file in the project that imports from both
    `src.core.tool` and `src.core.plan_execution`
  - src/core/tool/__init__.py: package-level public exports
  - Five built-in, real tools wired from src/bootstrap.py: Memory
    Recall, Knowledge Base Query, Long-Term Memory Query, Agent
    Subsystem Coordination, and Acknowledge Request -- each a closure
    over an already-built subsystem Service instance's public,
    parameter-free method. Four EP-029 actions that require a text
    parameter neither `PlanStep` nor
    `PlanExecutionProvider.execute_step()` currently carries
    (`generate_embedding`, `retrieve_context`, `semantic_search`,
    `compress_context`) are deliberately left unregistered rather than
    invented -- see docs/BACKLOG.md
- ToolService (src/services/tool_service.py): config-driven
  ('tool.enabled', 'tool.default_provider') business logic, a thin
  CLI-facing wrapper around ToolManager/ToolEngine
- ToolModule (src/modules/tool_module.py): "tool" CLI namespace --
  help / status / providers / list / use / run
- config/config.yaml: new 'tool' section ('enabled', 'default_provider')
- EP-031 test suite (tests/EP031/test_tool_engine.py)

### Changed

- src/bootstrap.py: registers ToolManager/ToolEngine/ToolService/
  ToolModule after the Plan Execution Engine, wrapped in a try/except
  for ToolError so invalid 'tool.*' configuration disables the Tool
  Engine subsystem for that run (logged) instead of crashing startup.
  The live PlanExecutionManager built for EP-030 (when available) is
  captured locally and, once Tool Engine is built, has a
  ToolExecutionProvider registered with it through its existing
  public `register_provider()` method only -- no file under
  src/core/plan_execution/ is modified, no existing wiring step is
  reordered or removed, and 'plan_execution.default_provider' is left
  unchanged ("plan_execution"), so default plan-execution dispatch
  behavior from EP-030 is byte-for-byte unaffected unless an operator
  explicitly runs 'execution use tool_engine'
- src/modules/test_module.py: registers the EP-031 test suite so
  'test EP031' and 'test all' pick it up

### Improved

- A dispatched `PlanStep` can now, for the five actions with a
  registered tool, produce a real subsystem effect and report it back
  through both the "tool" and "execution" CLI namespaces -- without
  any new AI reasoning, planning, or dispatch-order component being
  introduced, and without changing any prior release's default
  behavior.

---

## v0.1.0-ep030

Released: 2026-08-05

### Added

- Plan Execution Engine (src/core/plan_execution/), a new independent
  package -- the first component to turn an EP-029 `Plan` into
  dispatched work, with no AI reasoning, no AI provider call, and no
  real subsystem/tool invocation anywhere in the package (that remains
  a future Tool Engine's responsibility):
  - StepStatus / StepResult / PlanExecutionResult
    (plan_execution_result.py): plain data model for the outcome of
    dispatching a single step and of executing a whole Plan.
    Deliberately named `plan_execution` (not `execution`) to avoid
    colliding with the pre-existing, unrelated `src/core/execution/`
    package (EP-003's OS-level target launcher)
  - PlanExecutionProvider interface (plan_execution_provider.py):
    unified `execute_step(step) -> StepResult` contract every
    execution strategy must implement
  - DefaultPlanExecutionProvider (plan_execution_provider.py): the
    built-in provider, registered under the name "plan_execution" --
    deterministic, recognized-action dispatch only (the same actions
    EP-029's DefaultPlanningProvider can emit). Reports a step
    "completed" once it has been successfully dispatched to a
    recognized action -- not that any real external effect was
    produced
  - PlanExecutionManager (plan_execution_manager.py): orchestration
    layer -- register/select execution providers, enable/disable the
    subsystem, and resolve the default `stop_on_failure` policy from
    'plan_execution.*' configuration. New provider types (e.g. a
    future Tool-Engine-backed provider) can be added at runtime via
    `register_provider()` without modifying this class
  - PlanExecutionEngine (plan_execution_engine.py): the
    provider-independent Plan -> PlanExecutionResult pipeline --
    walks a Plan's steps in order, skips any step EP-029 already
    reported unavailable, dispatches every available step to the
    active provider, and halts the remaining plan on the first
    failure when 'stop_on_failure' is enabled. Optionally accepts an
    EP-029 `PlanningEngine` and, when supplied, exposes
    `execute_request()` to plan and execute a request in one call
    through its public `plan()` method only
  - src/core/plan_execution/__init__.py: package-level public exports
- PlanExecutionService (src/services/plan_execution_service.py):
  config-driven ('plan_execution.enabled',
  'plan_execution.default_provider', 'plan_execution.stop_on_failure')
  business logic, a thin CLI-facing wrapper around
  PlanExecutionManager/PlanExecutionEngine
- PlanExecutionModule (src/modules/plan_execution_module.py):
  "execution" CLI namespace -- help / status / providers / use / run /
  stop-on-failure
- config/config.yaml: new 'plan_execution' section ('enabled',
  'default_provider', 'stop_on_failure')
- EP-030 test suite (tests/EP030/test_plan_execution_engine.py)

### Changed

- src/bootstrap.py: registers PlanExecutionManager/PlanExecutionEngine/
  PlanExecutionService/PlanExecutionModule after the Planning Engine,
  wrapped in a try/except for PlanExecutionError so invalid
  'plan_execution.*' configuration disables the Plan Execution Engine
  subsystem for that run (logged) instead of crashing startup. The
  PlanningEngine built for EP-029 (when available) is captured locally
  and passed to PlanExecutionEngine, read-only, through its public
  `plan()` method only. Plan Execution Engine has no hard dependency
  on Planning Engine: `execute_plan()` works standalone given an
  already-built Plan even when Planning Engine is unavailable this
  run; that only narrows what `execution run` can do, it never
  disables the Plan Execution Engine subsystem itself. No change to
  startup order or wiring for any other subsystem
- src/modules/test_module.py: registers the EP-030 test suite so
  'test EP030' and 'test all' pick it up

### Improved

- An EP-029 Plan's steps can now actually be dispatched, in order,
  respecting availability and a configurable failure policy, and the
  outcome inspected per step or as a whole -- without any new
  reasoning, retrieval, or real subsystem-invocation component being
  introduced.

---

## v0.1.0-ep029

Released: 2026-08-04

### Added

- Planning Engine (src/core/planning/), a new independent package --
  decomposes a request into an ordered Plan of steps referencing
  already-implemented Engineering Packages by name, with no AI
  reasoning, no AI provider call, no prompt construction, and no task
  execution anywhere in the package:
  - PlanStep / Plan (planning_result.py): plain data model for a
    single ordered step and the outcome of decomposing a whole request
  - PlanningProvider interface (planning_provider.py): unified
    `plan(request, max_steps) -> Plan` contract every planning
    strategy must implement
  - DefaultPlanningProvider (planning_provider.py): the built-in
    provider, registered under the name "planning" -- deterministic,
    fixed keyword -> (subsystem, action, description) rule table,
    applied via case-insensitive substring matching only. Emits at
    most one step per matched subsystem (first matching keyword wins),
    preserves rule order, enforces `max_steps`, and falls back to a
    single `acknowledge_request` step (no subsystem) when nothing
    matches. Every step is returned with `available=True`; this
    provider never queries a live subsystem registry
  - PlanningManager (planning_manager.py): orchestration layer --
    register/select planning providers, enable/disable the subsystem,
    and resolve the default `max_steps` limit from 'planning.*'
    configuration
  - PlanningEngine (planning_engine.py): the provider-independent
    request -> Plan pipeline. Optionally accepts an EP-028
    `AgentEngine` and, when supplied, reconciles each step's
    `available` flag against that agent's live subsystem registry via
    its public `list_subsystems()` method only -- the first component
    to make real use of EP-028's Agent Framework subsystem registry
  - src/core/planning/__init__.py: package-level public exports
- PlanningService (src/services/planning_service.py): config-driven
  ('planning.enabled', 'planning.default_provider', 'planning.max_steps')
  business logic, a thin CLI-facing wrapper around
  PlanningManager/PlanningEngine
- PlanningModule (src/modules/planning_module.py): "planning" CLI
  namespace -- help / status / providers / use / plan / limits
- config/config.yaml: new 'planning' section ('enabled',
  'default_provider', 'max_steps')
- EP-029 test suite (tests/EP029/test_planning_engine.py)

### Changed

- src/bootstrap.py: registers PlanningManager/PlanningEngine/
  PlanningService/PlanningModule after the Agent Framework, wrapped in
  a try/except for PlanningError so invalid 'planning.*' configuration
  disables the Planning Engine subsystem for that run (logged) instead
  of crashing startup. The AgentEngine built for EP-028 (when
  available) is captured locally and passed to PlanningEngine,
  read-only, through its public `list_subsystems()` method only.
  Planning Engine has no hard dependency on the Agent Framework:
  `plan()` works standalone (every step reported available) even when
  the Agent Framework is unavailable this run; that only narrows what
  Planning Engine can see, it never disables the Planning Engine
  subsystem itself. No change to startup order or wiring for any other
  subsystem.
- src/modules/test_module.py: registers the EP-029 test suite so
  'test EP029' and 'test all' pick it up

### Improved

- A request can now be decomposed into a concrete, inspectable
  sequence of subsystem-referencing steps -- and, when the Agent
  Framework is available, each step's real-world feasibility can be
  checked against the subsystems actually registered and enabled at
  runtime -- without any new reasoning, retrieval, or storage
  component being introduced.

---



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