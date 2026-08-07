# RELEASE_NOTES.md

Version: 1.0

Status: Active

---

# Purpose

This document summarizes the user-visible changes introduced in each released version of Jarvis.

Unlike CHANGELOG.md, this document focuses on features and improvements rather than implementation details.

---

EP-019 completed.

Jarvis now supports project indexing.

Available commands:

index build
index rebuild
index status
index clear

# Release 0.1.0-alpha

## Added

- Interactive Shell
- AI Provider Framework
- Conversation Engine
- Prompt Engine
- Universal Context Engine

## Improved

- Provider abstraction
- Context loading
- Prompt generation
- Configuration management

## Fixed

- Context budgeting
- Prompt size validation
- Conversation history handling

---

Future releases will be documented here.

---

# EP-020 — Retrieval Engine

Status: Released

Highlights:

- Added Retrieval Engine
- Semantic retrieval API
- Integration with Project Index Engine
- Document search by relevance
- Modular retrieval architecture
- Provider-independent implementation

Compatibility:

Fully compatible with EP-019.

No breaking changes.

---

# EP-021 — Embedding Engine

Status: Released

Highlights:

- Added a provider-independent Embedding Engine
- Transforms text into embedding vectors only -- no retrieval, no RAG, no chat completion
- Local embedding provider: fully offline, deterministic, no third-party dependency
- Cloud embedding provider: configuration-driven, ready for a future real integration
- CLI integration: embedding status / providers / use / embed / dimension
- Switching providers takes effect immediately, no restart required

Compatibility:

Fully compatible with EP-020. Does not modify the Retrieval Engine.

No breaking changes.

---

# EP-022 — RAG Engine

Status: Released

Highlights:

- Added a provider-independent RAG (Retrieval-Augmented Generation) Engine
- Combines the Project Index Engine (EP-019), the Retrieval Engine (EP-020) and
  the Embedding Engine (EP-021) into a single, reusable context-generation pipeline
- Given a query: obtains its embedding, retrieves and ranks relevant chunks, then
  assembles the highest-ranked chunks (full text, not just a preview) into a single
  context block
- Returns a structured result: the ranked matches used, the assembled context text,
  and which embedding provider produced the query embedding
- Does not call any AI provider and performs no chat completion -- context assembly
  only; feeding this context into a chat completion call is future work
- CLI integration: rag status / query / context / provider / use
- Switching the embedding provider used for RAG takes effect immediately, no restart
  required

Compatibility:

Fully compatible with EP-019, EP-020 and EP-021. Does not modify the Project Index
Engine, the Retrieval Engine, or the Embedding Engine.

No breaking changes.

---

# EP-023 — Memory Manager

Status: Released

Highlights:

- Added a Memory Manager: an orchestration layer over registered memory
  providers, built on top of the existing (EP-013) Memory & Context Manager
  rather than a second memory subsystem
- Register, enable, disable and switch between memory providers, and
  inspect their status, through a single unified API
- The built-in "memory" provider wraps the existing MemoryStore, so every
  entry set/retrieved through the Memory Manager is the same data already
  managed by `memory get` / `memory set` / `memory list`
- CLI integration: memory providers / memory use <provider>, alongside the
  existing memory status / doctor / get / set / delete / clear / list /
  export / import / help
- Invalid provider configuration disables the Memory subsystem for that run
  (logged) instead of crashing the rest of Jarvis on startup
- Only the abstraction and the MemoryStore adapter are implemented -- no
  Knowledge Base, Long-Term Memory, Semantic Search, or External provider
  yet; those remain future work (EP-024 onward)

Compatibility:

Fully backward compatible with EP-013. Every existing `MemoryService` method
and every existing `memory` CLI command behaves exactly as before.

No breaking changes.

---

# EP-024 — Knowledge Base

Status: Released

Highlights:

- Added a Knowledge Base: a new, independent subsystem for storing and
  organizing structured project knowledge into named collections
- Manage structured knowledge records: store, load, update, delete, and
  clear -- scoped to a single collection or across all of them
- Inspect collection statistics (record counts per collection) and
  provider status through a single unified API, mirroring the
  provider/manager pattern already used by the Memory Manager (EP-023)
- CLI integration: knowledge status / collections / list / info / clear /
  help
- Invalid provider configuration disables the Knowledge subsystem for
  that run (logged) instead of crashing the rest of Jarvis on startup
- Knowledge Base performs no reasoning and has no dependency on Memory,
  Embedding, Retrieval, RAG, Long-Term Memory, Semantic Search, Context
  Compression, Planning, Reflection, Agent Memory, or Vector Storage --
  those remain future work (EP-025 onward)

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior changed.

No breaking changes.

---

# EP-025 — Long-Term Memory

Status: Released

Highlights:

- Added Long-Term Memory: persistent storage and lifecycle management
  (active / archived) for important, long-lived memories
- Manage memories: store, retrieve, update, archive, and permanently
  delete -- individually or all at once
- Inspect aggregate statistics (total / active / archived) and provider
  status through a single unified API, mirroring the provider/manager
  pattern already used by the Memory Manager (EP-023) and Knowledge Base
  (EP-024)
- CLI integration: ltm status / list / info / archive / clear /
  statistics / help
- Persists through Knowledge Base (EP-024) rather than a new storage
  engine, and extends the Memory Manager (EP-023) with a "long_term"
  provider so it is visible to `memory providers` / `memory use
  long_term`
- Invalid configuration disables Long-Term Memory for that run (logged)
  instead of crashing the rest of Jarvis on startup; it also disables
  itself gracefully if Knowledge Base is unavailable
- Long-Term Memory performs no ranking, similarity search, embeddings,
  or AI reasoning -- Semantic Search and Context Compression remain
  future work (EP-026, EP-027)

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed, aside from the additive `MemoryService.register_provider` method.

No breaking changes.

---

# EP-026 — Semantic Search

Status: Released

Highlights:

- Added Semantic Search: meaning-based similarity search over
  Knowledge Base (EP-024) and Long-Term Memory (EP-025) records
- Generates vectors through the existing Embedding Engine (EP-021) --
  no new embedding pipeline
- Scores and ranks matches through a pluggable provider, mirroring the
  provider/manager pattern already used by the Memory Manager
  (EP-023), Knowledge Base (EP-024), and Long-Term Memory (EP-025);
  ships with one built-in provider ("semantic", cosine similarity)
- CLI integration: semantic status / providers / use / search /
  threshold / help
- Invalid configuration disables Semantic Search for that run (logged)
  instead of crashing the rest of Jarvis on startup; it also disables
  itself gracefully if the Embedding Engine is unavailable
- Semantic Search performs no answer generation, AI provider calls,
  prompt construction, context compression, planning, reflection, or
  reasoning -- Context Compression and an Agent Framework remain
  future work (EP-027 onward)

Known limitation:

The Embedding Engine's only offline, always-available provider
("local") derives vectors from a SHA-256 hash of the whole input text,
not a real language model. It reliably finds exact or near-exact
duplicate text, but cannot recognize that two *differently worded*
sentences mean the same thing -- non-identical text scores as
statistically uncorrelated noise regardless of how related it
actually is. 'semantic status' and the logs will show a warning
whenever this provider is active. For genuine meaning-based matching,
configure a real embedding provider via 'embedding.default_provider'.

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed.

No breaking changes.

---

# EP-027 — Context Compression

Status: Released

Highlights:

- Added Context Compression: shrinks already-assembled context (raw
  text, or the results of Semantic Search EP-026) down to a configured
  size before it is used elsewhere
- Removes duplicated chunks and duplicated paragraphs, preserves chunk
  ordering and metadata, and enforces a maximum chunk count and a
  maximum total character count
- Deterministic and purely arithmetic throughout -- no AI reasoning, no
  summarization, no rewriting of surviving text, and no calls to any
  AI provider or LLM. Token counts are estimated with a fixed,
  documented characters-per-token heuristic, not a real tokenizer
- Delegates the actual compression work to a pluggable provider,
  mirroring the provider/manager pattern already used by the Memory
  Manager (EP-023), Knowledge Base (EP-024), Long-Term Memory (EP-025),
  and Semantic Search (EP-026); ships with one built-in provider
  ("compression", deduplication + limit enforcement)
- CLI integration: compression status / providers / use / analyze /
  compress / limits / help
- Invalid configuration disables Context Compression for that run
  (logged) instead of crashing the rest of Jarvis on startup. Unlike
  Semantic Search, Context Compression has no hard dependency on the
  Embedding Engine, Knowledge Base, or Long-Term Memory -- compressing
  raw text/chunks works even when none of them are available; only the
  optional "compress a live semantic search" convenience needs
  Semantic Search itself
- Context Compression performs no answer generation, AI provider
  calls, prompt construction, retrieval, planning, reflection, or
  reasoning -- an Agent Framework remains future work

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed.

No breaking changes.

---

# EP-028 — Agent Framework

Status: Released

Highlights:

- Added the Agent Framework: the central orchestration layer that
  coordinates every already-implemented Engineering Package (Embedding
  Engine, RAG Engine, Memory Manager, Knowledge Base, Long-Term Memory,
  Semantic Search, Context Compression) behind one lifecycle and one
  subsystem registry
- Agent lifecycle: initialize / shutdown / reset, with a current status
  (UNINITIALIZED / READY / RUNNING / SHUTDOWN / ERROR)
- Subsystem registry: every available subsystem is automatically
  registered at startup and its live enabled/disabled status can be
  inspected in one place with `agent subsystems`; subsystems can also
  be registered/unregistered by name
- Accepts and acknowledges requests, but performs no planning,
  reasoning, task decomposition, tool execution, prompt construction,
  or AI provider call of any kind -- this release is orchestration
  scaffolding only. A future Planner (EP-029 onward) is what will
  actually reason about and dispatch a request; every request accepted
  in this release says so explicitly
- Delegates the actual agent behavior to a pluggable agent
  implementation, mirroring the provider/manager pattern already used
  by Semantic Search (EP-026) and Context Compression (EP-027); ships
  with one built-in agent ("jarvis")
- CLI integration: agent status / subsystems / register / unregister /
  reset / initialize / shutdown / help
- Invalid configuration disables the Agent Framework for that run
  (logged) instead of crashing the rest of Jarvis on startup. The
  Agent Framework has no hard dependency on any other subsystem --
  every already-built service is registered opportunistically, and a
  subsystem missing this run is simply absent from `agent subsystems`,
  never a startup failure

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed.

No breaking changes.

---

# EP-029 — Planning Engine

Status: Released

Highlights:

- Added the Planning Engine: turns a request into a concrete, ordered
  Plan of steps, each naming the completed Engineering Package that
  would carry it out (e.g. Knowledge Base, Semantic Search, Context
  Compression)
- Fully deterministic: request text is matched against a fixed table
  of keyword rules -- no AI reasoning, no AI provider call, no network
  access. The same request always produces the same plan
- When the Agent Framework (EP-028) is available, every plan is
  automatically cross-checked against the subsystems actually
  registered and enabled at runtime, so a step can be seen to be
  currently unavailable before anything is attempted
- A request matching no known subsystem still produces a plan -- a
  single, explicit "acknowledged, nothing to decompose" step, never an
  error
- Delegates the actual decomposition to a pluggable planning strategy,
  mirroring the provider/manager pattern already used by Semantic
  Search (EP-026), Context Compression (EP-027), and the Agent
  Framework (EP-028); ships with one built-in provider ("planning")
- CLI integration: planning status / providers / use / plan / limits /
  help
- A Plan is a proposal only -- nothing in this release executes a
  step, calls a tool, or talks to an AI provider. Turning a Plan into
  actual work is left to a future Execution Engine
- Invalid configuration disables the Planning Engine for that run
  (logged) instead of crashing the rest of Jarvis on startup. The
  Planning Engine has no hard dependency on the Agent Framework or any
  other subsystem -- `planning plan` still works standalone, reporting
  every step as available, if the Agent Framework is unavailable this
  run

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed.

No breaking changes.

---

# EP-032 — Multi-Agent Collaboration

Status: Released

Highlights:

- Added Multi-Agent Collaboration: distributes a single request across
  every agent currently registered with the Agent Framework (EP-028)
  and reports each agent's own outcome
- Fully deterministic: the same request is broadcast, unchanged, to
  every currently READY agent -- no AI reasoning, no negotiation, and
  no inter-agent messaging of any kind
- An agent that is not currently READY is reported UNAVAILABLE without
  ever being called; an agent whose own execution fails or raises is
  isolated so it never affects any other agent's outcome
- Delegates the actual distribution strategy to a pluggable
  collaboration provider, mirroring the provider/manager pattern
  already used by Semantic Search (EP-026), Context Compression
  (EP-027), the Agent Framework (EP-028), the Planning Engine
  (EP-029), the Plan Execution Engine (EP-030), and the Tool Engine
  (EP-031); ships with one built-in provider ("collaboration")
- CLI integration: collaborate status / providers / agents / use / run
  / help
- This release coordinates whole requests across agents (broadcast),
  not individual plan steps across agents -- distributing a single
  Plan's steps across multiple agents remains a future extension
- Invalid configuration disables Multi-Agent Collaboration for that
  run (logged) instead of crashing the rest of Jarvis on startup.
  Multi-Agent Collaboration has a hard dependency on the Agent
  Framework being available this run: without a registered agent
  catalog there is nothing to coordinate

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed.

No breaking changes.

---

# EP-033 — Workflow Engine

Status: Released

Highlights:

- Added Workflow Engine: runs a named, ordered sequence of plain-text
  requests (a workflow definition) as a single, repeatable unit
- Each step is planned and executed through the already-existing
  Planning Engine (EP-029) + Plan Execution Engine (EP-030) pipeline,
  via `PlanExecutionEngine.execute_request()` -- no new AI reasoning,
  no new planning logic, and no direct real-subsystem/tool invocation
  is introduced anywhere in this package
- Steps run in order; a failing step halts the remaining workflow
  (each remaining step reported SKIPPED) unless
  'workflow_engine.stop_on_failure' is turned off, in which case every
  step still runs and failures are simply reported
- Delegates the actual per-step dispatch to a pluggable workflow-run
  provider, mirroring the provider/manager pattern already used by
  the Planning Engine (EP-029), the Plan Execution Engine (EP-030),
  the Tool Engine (EP-031), and Multi-Agent Collaboration (EP-032);
  ships with one built-in provider ("workflow_engine")
- CLI integration: flow status / list / info / use / run / help
- Naming note: this project already had a completed, dormant
  Workflow/WorkflowService/WorkflowModule component from EP-007 (never
  wired into Bootstrap, and left untouched by this release). EP-033 is
  an entirely new, independent package, deliberately namespaced apart
  from it at every layer -- including a distinct CLI namespace
  ("flow", not "workflow") -- to avoid any collision, present or
  future. See src/core/workflow_engine/__init__.py for the full note
- Invalid configuration disables Workflow Engine for that run (logged)
  instead of crashing the rest of Jarvis on startup. Workflow Engine
  has a hard dependency on the Plan Execution Engine being available
  this run: without one there is nothing to actually plan and execute
  a step's request

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed. EP-007's dormant Workflow/WorkflowService/WorkflowModule
package remains exactly as it was -- still unregistered, still
untouched.

No breaking changes.

---

End of document.