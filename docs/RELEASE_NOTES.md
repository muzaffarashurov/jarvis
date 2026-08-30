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

# EP-034 — Workflow Scheduler

Status: Released

Highlights:

- Added Workflow Scheduler: gives an EP-033 workflow definition a time
  trigger -- runs it automatically on a schedule
  (manual/once/interval/daily/weekly) or on demand
- Every scheduled run is dispatched through the already-existing
  Workflow Engine (EP-033) via `WorkflowEngine.run()` -- no new AI
  reasoning, no new planning logic, and no direct real-subsystem/tool
  invocation is introduced anywhere in this package
- Reuses EP-011's `Schedule`/`ScheduleType`/`JobStatus` value types
  unchanged; its own `WorkflowSchedulerEngine` decides when an entry
  is due and always delegates the actual run to EP-033
- Runs on its own background thread (separate from EP-011's own
  scheduler thread, no shared state), started automatically only when
  both 'workflow_scheduler.enabled' and 'workflow_scheduler.auto_start'
  are true -- off by default, since no scheduled workflow is
  registered out of the box
- CLI integration: autoflow list / status / run / start / stop / info
  / help
- Naming note: this project already had a completed, **actively
  wired** Job/Scheduler/SchedulerService/SchedulerModule component
  from EP-011 (still running its own default jobs today, left
  completely untouched by this release). EP-034 is an entirely new,
  independent package, deliberately namespaced apart from it at every
  layer -- including a distinct CLI namespace ("autoflow", not
  "scheduler") -- to avoid any collision, present or future. See
  src/core/workflow_scheduler/__init__.py for the full note
- Invalid configuration disables Workflow Scheduler for that run
  (logged) instead of crashing the rest of Jarvis on startup. Workflow
  Scheduler has a hard dependency on the Workflow Engine being
  available this run: without one there is nothing to actually run a
  scheduled entry's referenced workflow

New service: `WorkflowSchedulerService` (src/services/workflow_scheduler_service.py).
New module: `WorkflowSchedulerModule` (src/modules/workflow_scheduler_module.py).

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed. EP-011's active Job/Scheduler/SchedulerService/SchedulerModule
package remains exactly as it was -- still registered, still running
its own default jobs, verified unaffected by this release.

No breaking changes.

---

# EP-035 — Automation Engine — Outcome-Triggered Workflow Chaining

Status: Released

Purpose:

Adds reactive workflow automation on top of the existing EP-033
Workflow Engine and EP-034 Workflow Scheduler: lets a completed
workflow automatically trigger a second workflow, based on how the
first one finished.

Implemented functionality:

- A completed EP-033 workflow can now automatically trigger a second
  EP-033 workflow, according to the first workflow's outcome
- Supported trigger conditions:
  - ON_SUCCESS -- fires only when the trigger workflow succeeded
  - ON_FAILURE -- fires only when the trigger workflow failed
  - ON_ANY -- fires regardless of outcome
- Behavior is synchronous, single-hop, and non-recursive: an
  automation rule's action workflow is dispatched directly through
  the Workflow Engine, and that action workflow's own completion does
  not itself trigger any further automation rule (no A -> B -> C
  chaining)
- CLI integration: automate list / status / info / enable / stop /
  help
- Works with a workflow run started on demand ("flow run") and with
  a workflow run started by EP-034's scheduler ("autoflow run", or an
  automatic scheduled tick) -- both paths can trigger a matching
  automation rule
- Automation rules are registered through the public
  `AutomationService` API

Highlights:

- Added Automation Engine: an EP-033 workflow's completion can chain
  directly into a second EP-033 workflow's run
- Every triggered action run is dispatched through the
  already-existing Workflow Engine (EP-033) via `WorkflowEngine.run()`
  -- no new AI reasoning and no direct real-subsystem/tool invocation
  is introduced anywhere in this package
- Purely reactive: Automation Engine owns no background thread, no
  queue, and no polling loop -- it only ever runs in response to
  another EP's own execution path reporting that a run has completed
- Naming note: `AutomationRule`/`AutomationRuleRegistry`/
  `AutomationEngine` are a new, independent set of types -- not a
  reuse of EP-034's `ScheduledWorkflow`/`ScheduledWorkflowRegistry`/
  `WorkflowSchedulerEngine`. An automation rule carries no schedule or
  tick participation; a scheduled workflow carries no trigger
  condition or action workflow. See
  src/core/automation_engine/__init__.py for the full note
- Invalid configuration disables Automation Engine for that run
  (logged) instead of crashing the rest of Jarvis on startup.
  Automation Engine has a hard dependency on the Workflow Engine being
  available this run: without one there is nothing to actually
  dispatch a matched rule's action workflow
- When 'automation.enabled' is false, no automation rule can ever
  fire, regardless of whether the triggering workflow ran on demand
  or on a schedule

Not implemented in this release (future roadmap):

- Background/async dispatch of triggered automations (tracked as
  EP-036 Background Workers)
- A generic publish/subscribe event bus (tracked as EP-037 Event Bus)
- Multi-hop or recursive automation chains
- Condition types beyond workflow outcome (e.g. data-based or
  step-level conditions)

New service: `AutomationService` (src/services/automation_service.py).
New module: `AutomationModule` (src/modules/automation_module.py).

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed. `WorkflowEngineService.run()` and
`WorkflowSchedulerEngine.run_now()` behave identically to their
pre-EP-035 selves when no automation hook is wired. EP-033's and
EP-034's own test suites pass unchanged after this release.

No breaking changes.

Validation:

EP035: 141 passed / 0 failed / 0 skipped
EP033: 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP034: 113 passed / 0 failed / 0 skipped (regression, unchanged)

---

# EP-036 — Background Workers

Status: Released

Purpose:

Runs already-registered EP-033 workflows in the background, off the
calling thread, so a workflow can be dispatched without blocking the
caller on its full execution.

Implemented functionality:

- A configurable pool of daemon worker threads (`worker_count`,
  default 4) dequeues submitted `workflow_id`s and runs each one
  through the already-existing Workflow Engine (EP-033) via
  `WorkflowEngine.run(workflow_id)` -- the only cross-EP dependency,
  reached exclusively through that one public method, mirroring
  EP-034's `WorkflowSchedulerEngine` and EP-035's `AutomationEngine`
- Each submission returns a task id; task status moves through
  PENDING -> RUNNING -> COMPLETED or FAILED, tracked thread-safely and
  readable at any time via `worker info <task_id>` / `worker list`
- A task already running is never interrupted mid-`WorkflowEngine.run()`
  -- shutdown lets in-flight work finish, and only tasks still sitting
  in the queue are left PENDING and not started
- Shutdown never reports a worker as stopped merely because
  `Thread.join()` returned -- every join is followed by an explicit
  `Thread.is_alive()` check, and only a confirmed-dead worker counts as
  stopped
- A single failing/misbehaving workflow can never kill its worker
  thread: both a `WorkflowEngineError` and any other exception raised
  by `WorkflowEngine.run()` are caught and recorded as that task's
  FAILED status with an error message, and the worker loop continues
- CLI integration: worker status / submit / list / info / stop / help
- Invalid configuration disables Background Worker Service for that
  run (logged) instead of crashing the rest of Jarvis on startup.
  Background Worker Service has a hard dependency on the Workflow
  Engine being available this run: without one there is nothing to
  actually run a submitted task's workflow

Highlights:

- Added Background Worker Pool: dispatches already-registered EP-033
  workflows off the calling thread through a fixed pool of daemon
  worker threads
- Layering: `BackgroundWorkerPool` (core) -> `BackgroundWorkerService`
  (config-driven lifecycle owner) -> `BackgroundWorkerModule` (CLI
  translation layer only) -- each layer reaches the one below it
  through its public API only, matching the dependency discipline
  already used by EP-033/EP-034/EP-035
- `background_workers.enabled` defaults to true, matching every other
  soft-toggle subsystem (`workflow_engine.enabled`,
  `workflow_scheduler.enabled`, `automation.enabled`); an enabled pool
  with nothing submitted to it is just `worker_count` idle daemon
  threads, with no other observable effect
- No "register" CLI command, matching EP-034's WorkflowSchedulerModule
  and EP-035's AutomationModule precedent -- a task is created directly
  by `worker submit`, not pre-registered then triggered

Known limitations (tracked as Architecture Debt -- see
docs/architecture/ARCHITECTURE_DEBT.md and
docs/architecture/audits/EP036_AUDIT.md):

- AD-005 (Medium) -- no process-exit shutdown wiring calls
  `BackgroundWorkerService.shutdown()` automatically; an in-flight task
  is terminated mid-run and a still-queued task is silently dropped on
  interpreter exit unless `worker stop` was run manually first. Worker
  threads are daemon threads, so this cannot hang process exit
- AD-006 (Low) -- `BackgroundWorkerPool` retains every submitted task
  for the pool's lifetime with no eviction/TTL, so task history memory
  usage grows unbounded in a long-running process

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed. EP-033's, EP-034's, and EP-035's own test suites pass
unchanged after this release.

No breaking changes.

Validation:

EP036       : 101 passed / 0 failed / 0 skipped
EP036-STEP2 : 48 passed / 0 failed / 0 skipped
EP036-STEP3 : 53 passed / 0 failed / 0 skipped
EP033: 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP034: 113 passed / 0 failed / 0 skipped (regression, unchanged)
EP035: 141 passed / 0 failed / 0 skipped (regression, unchanged)

---

# EP-037 — Event Bus

Status: Released

Purpose:

Puts the existing, previously-dormant `EventBus` (in place since
EP-001) into real production use as a decoupling mechanism between
EP-033 through EP-036, replacing bespoke point-to-point callback
wiring where doing so genuinely improves decoupling, without creating
a second event bus implementation.

Implemented functionality:

- `EventBus` (`src/core/events.py`) is now thread-safe: a single lock
  protects its subscriber registry; `publish()` takes a snapshot copy
  of the relevant handlers under the lock, then invokes them outside
  it, so a handler that itself subscribes/unsubscribes/publishes
  during its own invocation can never deadlock or corrupt the
  subscriber list. The public API (`subscribe`, `unsubscribe`,
  `publish`, `event_names`) is unchanged; every pre-existing caller
  (including EP-001's own `Orchestrator` publishes) continues to work
  unmodified
- `WorkflowEngineService` (EP-033) and `WorkflowSchedulerEngine`
  (EP-034) publish `"workflow.completed"` (`definition_id`, `result`)
  at the same point their existing `automation_hook` already fired --
  purely additive; the hook and its call sites are left fully intact
- `BackgroundWorkerPool` (EP-036) publishes
  `"background_worker.task_completed"` / `"background_worker.task_failed"`
  (`task_id`, `workflow_id`, `result`/`error`) at its existing
  `COMPLETED`/`FAILED` task transitions, always outside its own task
  lock -- task state semantics, locking, and shutdown behavior are
  unchanged
- Bootstrap's production automation wiring now subscribes
  `AutomationEngine.notify_run()` (EP-035) to `"workflow.completed"`
  instead of calling `set_automation_hook()` on both engines
  separately -- one subscription now covers both the on-demand and
  scheduled paths. `set_automation_hook()` itself remains available
  and fully functional for any external/direct caller
- A small Bootstrap-local adapter subscribes to
  `"background_worker.task_completed"` only, and calls
  `AutomationEngine.notify_run(definition_id=workflow_id, result=result)`
  -- closing the one integration gap `BackgroundWorkerPool` had, since
  it calls the raw `WorkflowEngine.run()` directly rather than through
  `WorkflowEngineService`. `"background_worker.task_failed"` is
  deliberately not wired to automation, since it carries no
  `WorkflowRunResult`
- The two production notification paths are structurally disjoint --
  different event names, one subscriber each, published from call
  paths that never both fire for the same run -- so a workflow
  completion, however it was dispatched (on-demand, scheduled, or
  background), triggers automation exactly once, never zero or twice

Highlights:

- No second `EventBus` implementation anywhere in the codebase --
  EP-037 strengthens and reuses `src/core/events.py::EventBus`
  exclusively
- No new configuration and no new CLI namespace: an EventBus is
  internal architectural infrastructure, not a user-facing surface
- Every new production wiring point is additive: no existing public
  API (`set_automation_hook()`, `BackgroundWorkerPool`/`Service`'s
  pre-EP-037 call shape) was removed, narrowed, or had its behavior
  changed for a caller that doesn't use the new `event_bus` parameter

Known limitations (tracked as Architecture Debt -- see
docs/architecture/ARCHITECTURE_DEBT.md and
docs/architecture/audits/EP037_AUDIT.md):

- AD-007 (Low) -- a background-worker-triggered automation action
  workflow runs synchronously on the pool worker thread that completed
  the triggering task, which could delay that worker under load. A
  latency characteristic, not a defect
- AD-008 (Low) -- the background-worker adapter's payload key access
  (`workflow_id`, `result`) is implicitly, not explicitly, coupled to
  `BackgroundWorkerPool`'s exact publish-call kwarg names, with a
  silent (log-only) failure mode if that shape ever changes

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed. `set_automation_hook()` on both `WorkflowEngineService` and
`WorkflowSchedulerEngine` remains callable and functional directly.
EP-033's, EP-034's, EP-035's, and EP-036's own test suites pass
unchanged after this release.

No breaking changes.

Validation:

EP037       : 87 passed / 0 failed / 0 skipped
EP036       : 101 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP2 : 48 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP3 : 53 passed / 0 failed / 0 skipped (regression, unchanged)
EP033: 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP034: 113 passed / 0 failed / 0 skipped (regression, unchanged)
EP035: 143 passed / 0 failed / 0 skipped (regression -- 2 more than EP-036's
  release, explained by EP-035's own import-scanning test now also
  checking the one new `EventBus` import line EP-037 added to each of
  the two files it touched; not a weakened or modified assertion)
EP001: 20 passed / 0 failed / 0 skipped (regression, unchanged)

---

# EP-038 — Git Integration

Status: STEP 1-3 complete (STEP 4 Architecture Audit pending)

Purpose:

Gives Jarvis a way to inspect the state of a git repository -- what's
changed, what the history looks like, what branches exist, what a
given commit contains -- without any ability to alter that repository.
Before this EP, no git-related implementation existed anywhere in the
codebase.

Implemented functionality:

- Five read-only operations: `status`, `diff` (optionally scoped to a
  path), `log` (bounded by a count), `branch`, `show <ref>`. No
  `commit`, `push`, `pull`, or `clone` exists anywhere in this
  subsystem -- not merely unwired, genuinely absent from both
  `GitService`'s and `GitModule`'s code
- Core -> Service -> Module layering, matching the EP-033 through
  EP-036 precedent:
  - Core (`src/core/git/`): `GitResult` (a frozen dataclass carrying
    `command`, `success`, `stdout`, `stderr`, `exit_code`) and a flat
    `GitError` exception hierarchy (`GitNotFoundError`,
    `GitRepositoryError`, `GitCommandError`) -- pure data, no
    subprocess call
  - Service (`src/services/git_service.py`): `GitService` owns the one
    place `subprocess.run(["git", ...])` is ever called in this
    subsystem, exactly matching the "one component owns the one real
    invocation" discipline `BackgroundWorkerPool` (EP-036) established
    for `WorkflowEngine.run()`. Every call passes
    `encoding="utf-8", errors="replace"` explicitly (never `text=True`
    alone), and is bounded by `git.timeout_seconds` so a hung `git`
    process cannot hang the calling thread indefinitely
  - Module (`src/modules/git_module.py`): the `git` CLI namespace
    (`status`, `diff [path]`, `log [count]`, `branch`, `show <ref>`,
    `help`), a pure `CommandResult` translation layer over
    `GitService`'s existing public methods, matching
    `BackgroundWorkerModule`'s shape exactly
- No third-party git library: every operation shells out to the
  system `git` executable via the standard library's `subprocess`
  module. `requirements.txt` is unchanged
- `GitService` has no dependency on any other Engineering Package's
  service or engine -- the first EP since EP-033 with zero cross-EP
  runtime dependency
- Config-gated construction in Bootstrap (`git.enabled`, default
  `true`), matching every other soft-toggle subsystem. Invalid
  `git.*` configuration (an unreachable/non-repository path, an
  invalid `timeout_seconds`) disables the subsystem for that run
  (logged) instead of crashing startup, matching
  `BackgroundWorkerService`'s handling of invalid
  `background_workers.*` configuration
- Tool Engine (EP-031) readiness: `Tool`
  (`src/core/tool/tool.py`) already wraps an already-built subsystem
  service without requiring any change to Tool Engine itself, so
  `GitService`'s narrow, five-method public API can be exposed as
  `Tool` entries in a future EP with zero modification to
  `src/core/tool/`. No such registration was added in this EP --
  confirming Tool-Engine-readiness was a design analysis, not an
  implementation task in scope here

Configuration and disabled behavior:

`config/config.yaml`'s new `git` section has exactly three keys:
`enabled` (default `true`), `repository_path` (default `null`, meaning
Bootstrap's own project root), and `timeout_seconds` (default `10`).
When `git.enabled` is `false`, Bootstrap never constructs `GitService`
and never registers `GitModule` at all -- a `git status` (or any other
`git <action>`) command falls through to the router's existing
"Unknown command" handling, exactly matching how a disabled
`BackgroundWorkerModule`/`AutomationModule` behaves today; no
subsystem-specific "this is disabled" message is invented, since no
existing module produces one either. The same applies if `git.enabled`
is `true` but construction still fails (invalid `timeout_seconds`, or
`repository_path` not inside a git working tree) -- Bootstrap catches
`GitServiceError`, logs it, and leaves the subsystem disabled for that
run rather than crashing startup.

Error handling:

- `git` executable not on `PATH` -> `GitNotFoundError`
- configured/resolved path is not (or no longer is) a git working tree
  -> `GitRepositoryError`
- any other non-zero `git` exit (bad ref, bad path, ...) ->
  `GitCommandError`, carrying the underlying `GitResult`
- a call exceeding `git.timeout_seconds` -> also `GitCommandError`
  (the subprocess's own timeout, not a separate exception type)
- invalid `git.*` configuration, or a `repository_path` that isn't a
  valid working tree, at construction time -> `GitServiceError`
  (Bootstrap-only; can never be raised by a running CLI call)
- `GitModule` catches `GitError` (the common base of the first four)
  and formats it as `CommandResult(success=False, message=str(exc))`,
  never letting a raw exception reach the shell

Design deviation from `EP038_DESIGN.md` (approved, not a regression):

`GitService.__init__(config, repository_path=None)`'s `repository_path`
parameter is an explicit override, exactly as designed. Passing
Bootstrap's own project root unconditionally as that override would
have silently ignored a real `git.repository_path` value set in
config. Bootstrap therefore reads `git.repository_path` from config
itself first, and only supplies its own project root as the
`repository_path` argument when config's value is null/absent. The
design's Configuration section already stated the intended outcome
("null -> defaults to Bootstrap's project root, real value ->
respected") -- this is the mechanism that actually delivers that
outcome; `GitService`'s public constructor signature itself is
unchanged from the design. Bootstrap's `git.enabled` gate (implied by
the design's CLI "Disabled behavior" row and by every other
subsystem's convention, but not spelled out in the Configuration
section's code snippet) was likewise added so the config key has any
effect at all.

Known limitations:

- No structured/parsed result shape -- `GitResult.stdout` is raw text
  (`--porcelain=v1` for `status`, `--oneline` for `log`, chosen for
  stable script-parseable output). No concrete consumer need for
  further parsing was identified; deferred, per the design's own
  "avoid unnecessary abstraction" reasoning
- `diff`/`show` output is not size-bounded (`log` is, via its own
  count argument) -- acceptable for the initial read-only scope; see
  the design document's Risks section
- The safety rule that `git push` requires human confirmation
  (`docs/architecture/JARVIS_ARCHITECTURE_VISION.md`) is not
  implemented, since `push` itself is out of this EP's scope entirely

Testing:

`tests/EP038/test_git_service.py` and `tests/EP038/test_git_module.py`
(one shared `"EP038"` suite, matching how EP-037's two files share one
suite) never touch this project's own `.git`. Every test creates a
disposable, throwaway git repository in a `tempfile.TemporaryDirectory()`,
initialized via direct `subprocess` calls (not through `GitService`, so
fixture setup stays independent of the code under test) with a
*repository-local* `user.name`/`user.email` -- the sandbox's global git
configuration is never read or written either. Coverage includes all
five operations against real repository state, config validation
(bad path, bad timeout), timeout enforcement, CLI dispatch/error
formatting for every command including invalid arguments, and real
`Bootstrap` wiring for both the enabled and `git.enabled: false` cases.

Compatibility:

Fully additive. No existing service, manager, or CLI command was
renamed, removed, or had its behavior changed. `requirements.txt` is
unchanged -- no new third-party dependency. EP-033's, EP-034's,
EP-035's, EP-036's, and EP-037's own test suites pass unchanged after
this work.

No breaking changes.

Validation:

EP038       : 30 passed / 0 failed / 0 skipped
EP037       : 87 passed / 0 failed / 0 skipped (regression, unchanged)
EP036       : 101 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP2 : 48 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP3 : 53 passed / 0 failed / 0 skipped (regression, unchanged)
EP033: 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP034: 113 passed / 0 failed / 0 skipped (regression, unchanged)
EP035: 143 passed / 0 failed / 0 skipped (regression, unchanged)
EP001: 20 passed / 0 failed / 0 skipped (regression, unchanged)

---

# EP-039 — GitHub Integration

Status: STEP 1-3 complete (STEP 4 Architecture Audit pending)

Purpose:

Gives Jarvis a way to read information from GitHub -- repository
metadata, issues, pull requests, and commits -- without any ability to
change that state. Before this EP, no GitHub-related implementation
existed anywhere in the codebase. The direct architectural sibling of
EP-038 (Git Integration), one phase later in Phase 6 (Integrations).

Implemented functionality:

- Eight read-only operations: repository information, the
  authenticated user's own repositories, list/get issue, list/get
  pull request, list/get commit. No create, update, delete, comment,
  merge, close, reopen, release, or any other write/mutating GitHub
  operation exists anywhere in this subsystem -- not merely unwired,
  genuinely absent from both `GitHubService`'s and `GitHubModule`'s
  code
- Core -> Service -> Module layering, matching the EP-038 precedent
  exactly:
  - Core (`src/core/github/`): `GitHubResult` (a frozen dataclass
    carrying `operation`, `status_code`, `data` -- the parsed JSON
    response body, exactly as GitHub returns it) and a flat
    `GitHubError` exception hierarchy (`GitHubAuthenticationError`,
    `GitHubNotFoundError`, `GitHubRateLimitError`, `GitHubTimeoutError`,
    `GitHubNetworkError`, `GitHubAPIError`) -- pure data, no HTTP call
  - Service (`src/services/github_service.py`): `GitHubService` owns
    the one place `requests.get(...)` is ever called in this
    subsystem, exactly matching the "one component owns the one real
    invocation" discipline `GitService` (EP-038) established for
    `subprocess.run(["git", ...])`. HTTP error translation follows
    `claude_provider.py`'s existing, already-proven pattern
    (`Timeout`/`ConnectionError`/other `RequestException`, then
    status-code mapping)
  - Module (`src/modules/github_module.py`): the `github` CLI
    namespace (`repo`, `repos`, `issues`, `issue`, `prs`, `pr`,
    `commits`, `commit`, `help`), a pure `CommandResult` translation
    layer over `GitHubService`'s existing public methods, matching
    `GitModule`'s shape exactly
  - Bootstrap constructs `GitHubService` and registers `GitHubModule`,
    gated by `github.enabled`, mirroring the EP-038 wiring block
    exactly -- **EP-031 Tool Engine was not modified**; `GitHubService`'s
    eight side-effect-free methods remain clean future `Tool` candidates
    by construction, the same conclusion EP-038 reached for `GitService`
- No third-party GitHub SDK: every operation uses the project's
  existing `requests` dependency directly. `requirements.txt` is
  unchanged
- `GitHubService` has no dependency on any other Engineering Package's
  service or engine, like `GitService` before it

Authentication:

`GITHUB_TOKEN` is supplied **only** through an environment variable,
read fresh via `os.environ.get("GITHUB_TOKEN")` inside `GitHubService`
at the start of every operation call -- never at construction, never
cached beyond the duration of a single call. **The token must never be
placed in `config/config.yaml` or any other config file**, and none of
this subsystem's code paths do so. If the token is missing or blank
when an operation is requested, `GitHubAuthenticationError` is raised
immediately, before any HTTP call is attempted -- no wasted network
request. The token is sent only as the `Authorization` request header;
it is never logged, never included in an exception message, and never
appears in any CLI (`CommandResult`) output -- every error message in
this subsystem is built from fixed text and/or the HTTP response
itself, never from the token value. `GitHubModule` never reads or
handles the token at all.

Configuration and disabled behavior:

`config/config.yaml`'s new `github` section has exactly three keys:
`enabled` (default `true`), `api_base_url` (default
`"https://api.github.com"`, overridable for a GitHub Enterprise Server
deployment), and `timeout_seconds` (default `30`). `GITHUB_TOKEN` is
not one of them and never will be under this design. When
`github.enabled` is `false`, Bootstrap never constructs `GitHubService`
and never registers `GitHubModule` -- a `github <anything>` command
falls through to the router's existing "Unknown command" handling,
identical to a disabled `GitModule`. The same applies if construction
still fails (invalid `timeout_seconds`, empty `api_base_url`) --
Bootstrap catches `GitHubServiceError`, logs it, and leaves the
subsystem disabled for that run rather than crashing startup.

Error handling:

- `GITHUB_TOKEN` unset/blank, or GitHub returns HTTP 401, or HTTP 403
  without a rate-limit signal -> `GitHubAuthenticationError`
- HTTP 404 -> `GitHubNotFoundError`
- HTTP 403 with `X-RateLimit-Remaining: 0`, or HTTP 429 ->
  `GitHubRateLimitError`
- Request exceeds `github.timeout_seconds` -> `GitHubTimeoutError`
- A connection-level failure -> `GitHubNetworkError`
- Any other non-2xx status, or an unparseable (non-JSON) response body
  -> `GitHubAPIError`
- Invalid `github.*` configuration at construction ->
  `GitHubServiceError` (Bootstrap-only; can never be raised by a
  running CLI call)
- `GitHubModule` catches `GitHubError` (the common base of the first
  six) and formats it as `CommandResult(success=False, message=str(exc))`,
  never letting a raw exception reach the shell

Testing:

`tests/EP039/test_github_service.py` and
`tests/EP039/test_github_module.py` (one shared `"EP039"` suite) never
make a real GitHub API call. Every test constructs `GitHubService`
with a small duck-typed stub `session` object in place of a real
`requests.Session` -- the same technique
`tests/EP035/test_automation_engine.py`'s `_StubPlanExecutionEngine`
already uses for a different dependency -- so no new mocking/HTTP
library was added. Coverage includes all eight operations, missing/blank
token handling (asserting zero HTTP calls are attempted), every HTTP
status-code mapping, timeout/connection-error translation, malformed
JSON, CLI dispatch/argument validation for every command, real
Bootstrap wiring for both `github.enabled` states, and a dedicated
assertion that a fixed fake token value never appears in any exception
message across six different error scenarios.

Known limitations:

- No pagination -- list operations return only GitHub's default first
  page. Acceptable for the initial read-only scope; deferred rather
  than solved, matching `GitService`'s own restraint in EP-038
- `list_repositories()` covers the authenticated user's own
  repositories only (`GET /user/repos`), not an arbitrary named
  user's or organization's repositories
- No retry/backoff on rate-limit errors
- `python-dotenv` is listed in `requirements.txt` but is not imported
  anywhere in the codebase -- `GITHUB_TOKEN` must be present in the
  actual process environment Jarvis is started with, not merely placed
  in a `.env` file

Compatibility:

Fully additive. No existing service, manager, or CLI command was
renamed, removed, or had its behavior changed. `requirements.txt` is
unchanged -- no new third-party dependency. EP-033's, EP-034's,
EP-035's, EP-036's, EP-037's, and EP-038's own test suites pass
unchanged after this work.

No breaking changes.

Validation:

EP039       : 36 passed / 0 failed / 0 skipped
EP038       : 30 passed / 0 failed / 0 skipped (regression, unchanged)
EP037       : 87 passed / 0 failed / 0 skipped (regression, unchanged)
EP036       : 101 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP2 : 48 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP3 : 53 passed / 0 failed / 0 skipped (regression, unchanged)
EP033: 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP034: 113 passed / 0 failed / 0 skipped (regression, unchanged)
EP035: 143 passed / 0 failed / 0 skipped (regression, unchanged)
EP001: 20 passed / 0 failed / 0 skipped (regression, unchanged)

---

# EP-040 — Telegram Information Integration

Status: STEP 1-3 complete (STEP 4 Architecture Audit pending)

## Overview

Gives Jarvis a way to look up metadata for a known Telegram chat/channel
(type, title, description, and similar fields), independent of EP-012's
Telegram Gateway. Before this EP, no such read/lookup capability existed
anywhere in the codebase.

## Scope

Implements exactly one Telegram Bot API operation: `Bot.get_chat(chat_id)`.

**Not implemented** -- explicitly, not merely deferred:

- message history retrieval
- `getUpdates` / message polling
- reading recent/arbitrary messages
- listing or discovering chats
- sending, editing, or deleting messages
- joining, leaving, or creating chats
- any administrative operation
- any other Telegram mutation

None of the above exist anywhere in `TelegramInfoService` or
`TelegramInfoModule`'s code, and several (message history, chat listing)
are not achievable at all through the Telegram Bot API this project uses
-- they would require a different API tier (Telegram's User/MTProto API)
and an unapproved new dependency, neither of which this EP introduces.

## Architecture

Core -> Service -> Module -> Bootstrap, matching the EP-038/039
precedent:

- Core (`src/core/telegram_info/`): `TelegramInfoResult` (a frozen
  dataclass carrying `chat_id`, `data` -- the chat's fields exactly as
  `telegram.Chat.to_dict()` returns them) and a flat `TelegramInfoError`
  exception hierarchy (`TelegramInfoAuthenticationError`,
  `TelegramInfoNotFoundError`, `TelegramInfoRateLimitError`,
  `TelegramInfoTimeoutError`, `TelegramInfoNetworkError`,
  `TelegramInfoAPIError`) -- pure data, no Bot API call
- Service (`src/services/telegram_info_service.py`): `TelegramInfoService`
  owns the one place `Bot.get_chat(...)` is ever called in this
  subsystem, mirroring the "one component owns the one real invocation"
  discipline `GitHubService` (EP-039) established for `requests.get(...)`
- Module (`src/modules/telegram_info_module.py`): the `telegram-info`
  CLI namespace (`chat`, `help`), a pure `CommandResult` translation
  layer over `TelegramInfoService`'s single public method, matching
  `GitHubModule`'s shape exactly
- Bootstrap constructs `TelegramInfoService` and registers
  `TelegramInfoModule`, gated by `telegram_info.enabled`, mirroring the
  EP-038/039 wiring block exactly
- No third-party dependency was added: `python-telegram-bot` (already
  installed, already used by EP-012) is reused directly.
  `requirements.txt` is unchanged

## EP-012 boundary

EP040 does **not** replace, modify, or depend on EP-012 "Telegram
Gateway" (`src/core/telegram/`, `src/services/telegram_service.py`,
`src/modules/telegram_module.py`). EP-012 remains fully responsible for
the inbound Telegram Gateway -- a human messages Jarvis, the message is
routed through `TelegramRouter` into `CommandRouter`, and a reply is
sent back via `TelegramClient.send_message`. That behavior, its
`fetch_updates()`/`getUpdates` polling loop, and its update
offset/cursor are entirely unaffected by this EP.

EP040 constructs its own, **independent** `telegram.Bot` instance and
performs only the stateless `get_chat()` operation. It does not use
`TelegramClient`, `fetch_updates()`, `get_updates()`, any update offset,
Telegram polling, or `TelegramRouter`. All four EP-012 files were
confirmed byte-identical before and after EP040 STEP 2.

## CLI

```text
telegram-info chat <chat_id>
telegram-info help
```

No other command exists in `TelegramInfoModule`'s dispatch table.

## Configuration

```yaml
telegram_info:
  enabled: true
  timeout_seconds: 10
```

There is **no** new Telegram token configuration. EP040 reuses the
existing `telegram.token` value (EP-012's key) read-only -- it is never
duplicated into `telegram_info.*` or any other key. When
`telegram_info.enabled` is `false`, Bootstrap never constructs
`TelegramInfoService` and never registers `TelegramInfoModule` --
`telegram-info <anything>` falls through to "Unknown command," matching
every other disabled subsystem in this project.

## Security

- Read-only operation; no mutation capability exists anywhere in this
  subsystem.
- The existing `telegram.token` is reused, never duplicated into a
  second configuration key.
- `TelegramInfoModule` never reads or handles the token at all -- it
  has no import of `telegram` and no code path that could reference it.
- The token never appears in any exception message or CLI output --
  every error message in this subsystem is built from fixed text and/or
  the Telegram API's own error type, never the token value.
- No new secret and no new third-party dependency were introduced.

## Testing

`tests/EP040/test_telegram_info_service.py` and
`tests/EP040/test_telegram_info_module.py` (one shared `"EP040"` suite)
never make a real Telegram API call and never require a real bot token.
Every test constructs `TelegramInfoService` with a small duck-typed stub
`bot` object exposing only `get_chat` -- no `get_updates`/`fetch_updates`
method exists on the stub at all, structurally proving no such call path
is exercised. Coverage includes the successful call, every
`python-telegram-bot` exception mapping, missing/blank token handling,
invalid configuration, CLI dispatch/argument validation, real Bootstrap
wiring, and a dedicated assertion that a fixed fake token value never
appears in any exception message across all seven error scenarios.

Validation:

EP040       : 25 passed / 0 failed / 0 skipped
EP039       : 36 passed / 0 failed / 0 skipped (regression, unchanged)
EP038       : 30 passed / 0 failed / 0 skipped (regression, unchanged)
EP037       : 87 passed / 0 failed / 0 skipped (regression, unchanged)
EP036       : 101 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP2 : 48 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP3 : 53 passed / 0 failed / 0 skipped (regression, unchanged)
EP033: 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP034: 113 passed / 0 failed / 0 skipped (regression, unchanged)
EP035: 143 passed / 0 failed / 0 skipped (regression, unchanged)
EP001: 20 passed / 0 failed / 0 skipped (regression, unchanged)

`test all` was not run.

## Limitations

The scope is intentionally limited to single-chat metadata lookup only.
Message history and chat discovery/listing are not implemented because
the Telegram Bot API does not support them -- not a deferred future
step of this EP, but a hard capability boundary of the API tier this
project uses. `Bot.get_chat` also requires an already-known chat id;
there is no way to enumerate chats the bot has access to.

# EP-041 — Discord Integration

Status: COMPLETE. STEP 1-4 complete -- design, implementation,
documentation, and Architecture Audit (Final Verdict: EP041 STEP 4 --
PASS; see `docs/architecture/audits/EP041_ARCHITECTURE_AUDIT.md`).

## Overview

Gives Jarvis a way to read Discord server (guild), channel, member,
and message metadata via Discord's REST API v10. Before this EP, no
Discord-related implementation, dependency, or configuration existed
anywhere in the codebase.

## Scope

Implements exactly five read-only Discord REST API v10 operations:

- `get_guild(guild_id)`
- `list_guild_channels(guild_id)`
- `get_channel(channel_id)`
- `get_guild_member(guild_id, user_id)`
- `get_message(channel_id, message_id)`

**Not implemented** -- explicitly, not merely deferred:

- message history / bulk message retrieval
- sending, editing, or deleting messages
- moderation operations
- role management
- webhooks
- reactions
- invites
- any channel-scoped member listing (not a Discord API concept --
  channel access is computed from guild membership plus role/channel
  permission overwrites, not a per-channel member roster)
- any other Discord mutation
- any Discord Gateway/WebSocket connection

None of the above exist anywhere in `DiscordService` or
`DiscordModule`'s code. Discord's REST API does technically support
bulk historical message retrieval
(`GET /channels/{channel.id}/messages`) without Gateway state, but it
was deliberately excluded from this EP's confirmed scope pending
separate approval.

## Architecture

Core -> Service -> Module -> Bootstrap, matching the EP-038/039/040
precedent:

- Core (`src/core/discord/`): `DiscordResult` (a frozen dataclass
  carrying `operation`, `status_code`, `data` -- the parsed JSON
  response body, exactly as Discord returns it) and a flat
  `DiscordError` exception hierarchy (`DiscordAuthenticationError`,
  `DiscordNotFoundError`, `DiscordRateLimitError`,
  `DiscordTimeoutError`, `DiscordAPIError`) -- pure data, no HTTP
  call
- Service (`src/services/discord_service.py`): `DiscordService` owns
  the one place `requests.get(...)` is ever called in this
  subsystem, mirroring the "one component owns the one real
  invocation" discipline `GitHubService` (EP-039) established
- Module (`src/modules/discord_module.py`): the `discord` CLI
  namespace (`guild`, `channels`, `channel`, `member`, `message`,
  `help`), a pure `CommandResult` translation layer over
  `DiscordService`'s five public methods, matching `GitHubModule`'s
  shape exactly
- Bootstrap constructs `DiscordService` and registers `DiscordModule`,
  gated by `discord.enabled`, mirroring the EP-039/040 wiring block
- No third-party dependency was added: the project's existing
  `requests` dependency is reused directly against Discord's REST
  API. `requirements.txt` is unchanged

## Discord REST API usage

All five operations are single, stateless `GET` requests against
`https://discord.com/api/v10` (configurable via `discord.api_base_url`),
authenticated with the bot token as the `Authorization` request
header. No Gateway/WebSocket connection is opened, and no privileged
Gateway intent is required -- `get_guild_member` looks up a single
already-known member by id, which does not require the privileged
`GUILD_MEMBERS` intent that applies only to the Gateway member-stream
and to the bulk List/Search Guild Members endpoints.

## Read-only operations

Supported:

- `get_guild` -- `GET /guilds/{guild.id}`
- `list_guild_channels` -- `GET /guilds/{guild.id}/channels`
- `get_channel` -- `GET /channels/{channel.id}`
- `get_guild_member` -- `GET /guilds/{guild.id}/members/{user.id}`
- `get_message` -- `GET /channels/{channel.id}/messages/{message.id}`
  (requires `READ_MESSAGE_HISTORY` permission in that channel)

Unsupported (not implemented anywhere in this subsystem):

- message history / bulk message retrieval
- send message
- edit/delete message
- moderation
- roles
- reactions
- invites
- webhooks
- Gateway/WebSocket

## CLI commands

```text
discord guild <guild_id>
discord channels <guild_id>
discord channel <channel_id>
discord member <guild_id> <user_id>
discord message <channel_id> <message_id>
discord help
```

No other command exists in `DiscordModule`'s dispatch table.

## Configuration

```yaml
discord:
  enabled: true
  api_base_url: "https://discord.com/api/v10"
  timeout_seconds: 30
```

There is **no** token key in configuration. Authentication uses the
`DISCORD_TOKEN` environment variable only. When `discord.enabled` is
`false`, Bootstrap never constructs `DiscordService` and never
registers `DiscordModule` -- `discord <anything>` falls through to
"Unknown command," matching every other disabled subsystem in this
project.

## Security

- `DISCORD_TOKEN` is read from `os.environ` at the start of every
  operation call -- never at `__init__`, never cached on `self`
  beyond the duration of a single call, never logged
- The token is sent only as the `Authorization` request header; it
  never appears in a log line, an exception message, or a
  `DiscordResult` -- every error message in this subsystem is built
  from fixed text and/or the HTTP response, never the token value
- `DiscordModule` never reads or handles the token at all -- it has
  no code path that could reference it
- No new secret storage mechanism and no new third-party dependency
  were introduced

## Error handling

`DiscordService` maps HTTP-layer failures onto the `DiscordError`
hierarchy: authentication failures (401) raise
`DiscordAuthenticationError`, not-found (404) raises
`DiscordNotFoundError`, rate limiting (429) raises
`DiscordRateLimitError`, request timeouts raise `DiscordTimeoutError`,
network-layer failures raise `DiscordNetworkError`, and any other
non-2xx response raises `DiscordAPIError`. `DiscordModule` catches
`DiscordError` uniformly and formats every failure as
`CommandResult(success=False, ...)`, never letting an exception
propagate to the CLI layer.

## Testing strategy

`tests/EP041/test_discord_service.py` and
`tests/EP041/test_discord_module.py` (one shared `"EP041"` suite)
never make a real Discord API call and never require a real bot
token. Every test constructs `DiscordService` with a small
duck-typed stub `session` object exposing only `.get(...)` -- no
Gateway/WebSocket client exists on the stub at all, structurally
proving no such call path is exercised. Coverage includes the
successful call for each of the five operations, every HTTP-status
error mapping, missing/blank token handling, invalid configuration,
CLI dispatch/argument validation, real Bootstrap wiring, and a
dedicated read-only-boundary test asserting none of
"send"/"edit"/"delete"/moderation-style operations exist anywhere in
the subsystem, plus a dedicated assertion that a fixed fake token
value never appears in any exception message across all error
scenarios.

## Regression verification

The EP041 test suite and the existing EP001/EP033-040 regression
suites were run individually as part of the STEP 4 Architecture
Audit; `test all` was not run. Results:

```
EP041       : 39 passed / 0 failed / 0 skipped
EP040       : 25 passed / 0 failed / 0 skipped
EP039       : 36 passed / 0 failed / 0 skipped
EP038       : 30 passed / 0 failed / 0 skipped
EP037       : 87 passed / 0 failed / 0 skipped
EP036       : 101 passed / 0 failed / 0 skipped
EP036-STEP2 : 48 passed / 0 failed / 0 skipped
EP036-STEP3 : 53 passed / 0 failed / 0 skipped
EP035       : 143 passed / 0 failed / 0 skipped
EP034       : 113 passed / 0 failed / 0 skipped
EP033       : 182 passed / 0 failed / 0 skipped
EP001       : 20 passed / 0 failed / 0 skipped
```

Every regression count matches its last recorded baseline -- no
regression was introduced by EP041. Source, test, and configuration
files outside the files listed as modified for this EP were verified
unchanged. See
`docs/architecture/audits/EP041_ARCHITECTURE_AUDIT.md` (Final
Verdict: EP041 STEP 4 -- PASS) for the complete audit.

## Known limitations

- No Discord Gateway/WebSocket connection anywhere in this subsystem
- No message history retrieval -- technically available via Discord's
  REST API without Gateway state, but deliberately excluded from this
  EP's confirmed scope
- No write operations (send, edit, delete, create)
- No moderation operations
- No role management
- No webhooks
- No Tool Engine integration

## Future Gateway boundary

No Discord Gateway/WebSocket connection exists anywhere in this EP.
`DiscordService` is stateless REST-only, with no persistent
connection and no cursor/offset, so a future Discord Gateway EP could
be added later without sharing state with, or being blocked by, this
subsystem.

## Tool Engine boundary

`DiscordService` is not registered with the EP-031 Tool Engine in
this EP -- deferred, matching the same deferral EP-039 (GitHub) and
EP-040 (Telegram Info) made for their own Tool Engine registration.

---

# EP-042 — Email Integration

Status: COMPLETE. STEP 1-4 complete -- design, implementation, and
Deep Audit (Final Verdict: EP042 STEP 3 -- PASS WITH NOTES; see
CHANGELOG.md v0.1.9-ep042 for the defects found and fixed during the
audit).

## Overview

Gives Jarvis a way to read email via a standard, provider-independent
IMAP server -- list mailboxes/folders, list recent messages, retrieve
a specific message, and search a mailbox. Before this EP, no
email-related implementation, dependency, or configuration existed
anywhere in the codebase.

## Scope

Implements exactly four read-only IMAP operations:

- `list_folders()`
- `list_messages(folder, limit)`
- `get_message(folder, uid)`
- `search_messages(folder, criteria)`

**Not implemented** -- explicitly, not merely deferred:

- sending email / SMTP message submission of any kind
- reply, forward, delete, move, or flag/mark (read/unread) operations
- attachment content download (attachment *metadata* -- filename,
  content type, size -- is included; attachment *content* is not)
- Gmail API, Microsoft Graph, Outlook API, or any other
  provider-specific API
- OAuth2 or any provider-specific authentication flow
- background/scheduled polling or any `IDLE` connection
- any other IMAP mutation

None of the above exist anywhere in `EmailService` or `EmailModule`'s
code -- confirmed by a dedicated grep-based scope audit during STEP 3
(searching for `SELECT`/`STORE`/`EXPUNGE`/`APPEND`/`COPY`/`MOVE`/
`DELETE`/`SMTP`/`sendmail`/`oauth`/`gmail`/`graph.microsoft` across
every EP-042 file).

## Architecture

Core -> Service -> Module -> Bootstrap, matching the EP-038/039/040/041
precedent, with one necessary protocol-driven adaptation (see below):

- Core (`src/core/email/`): `EmailFolder`, `EmailAttachment`,
  `EmailMessageSummary`, `EmailMessage` (frozen dataclasses describing
  normalized IMAP data -- never raw IMAP/RFC 822 structures) and
  `EmailResult`, plus a flat `EmailError` exception hierarchy
  (`EmailAuthenticationError`, `EmailConnectionError`,
  `EmailTimeoutError`, `EmailTLSError`, `EmailMailboxError`,
  `EmailMessageNotFoundError`, `EmailSearchError`,
  `EmailProtocolError`) -- pure data, no IMAP call
- Service (`src/services/email_service.py`): `EmailService` owns the
  one place IMAP connections are opened in this subsystem, mirroring
  the "one component owns the one real invocation" discipline
  `DiscordService` (EP-041) established. Unlike a single stateless
  HTTP call per operation, IMAP is inherently connection-oriented, so
  each public method opens one short-lived connection
  (connect -> login -> read-only select -> operate -> logout) and
  always closes it before returning -- no connection is ever stored
  on `self`, keeping the service conceptually stateless between calls
  the same way `DiscordService`/`GitHubService` are
- Module (`src/modules/email_module.py`): the `email` CLI namespace
  (`folders`, `list`, `message`, `search`, `help`), a pure
  `CommandResult` translation layer over `EmailService`'s four public
  methods, matching `DiscordModule`'s shape exactly
- Bootstrap constructs `EmailService` and registers `EmailModule`,
  gated by `email.enabled`, mirroring the EP-039/040/041 wiring block
- No third-party dependency was added: the Python standard library
  (`imaplib` + `email`) is sufficient. `requirements.txt` is unchanged

## IMAP protocol usage

All four operations use IMAP `UID` command variants (`UID SEARCH`,
`UID FETCH`) rather than message sequence numbers, so UIDs remain
stable identifiers across separate calls. Every mailbox is selected
read-only (`SELECT ... readonly=True`, i.e. IMAP `EXAMINE` semantics)
-- this subsystem cannot set the `\Seen` flag or otherwise mutate a
mailbox as a side effect of any operation. `SEARCH` results are
explicitly sorted by numeric UID before use, since RFC 3501 does not
guarantee server-returned order.

## Read-only operations

Supported:

- `list_folders` -- IMAP `LIST`
- `list_messages` -- IMAP `UID SEARCH ALL` + `UID FETCH ... (BODY.PEEK[HEADER])`
- `get_message` -- IMAP `UID FETCH ... (RFC822)`, normalized via the
  standard-library `email` package
- `search_messages` -- IMAP `UID SEARCH <criteria>` (a raw IMAP
  search-key expression, passed through as-is) + the same header-only
  fetch `list_messages` uses

Unsupported (not implemented anywhere in this subsystem):

- send / reply / forward
- delete / move / flag / mark read-unread
- attachment content download
- Gmail API / Microsoft Graph / Outlook API
- OAuth2
- background polling / `IDLE`

## CLI commands

```text
email folders
email list [folder] [limit]
email message <folder> <uid>
email search <folder> <criteria...>
email help
```

No other command exists in `EmailModule`'s dispatch table.

## Configuration

```yaml
email:
  enabled: false
  imap_host: ""
  imap_port: 993
  tls_mode: "ssl"
  imap_username_env_var: "EMAIL_IMAP_USERNAME"
  imap_password_env_var: "EMAIL_IMAP_PASSWORD"
  default_mailbox: "INBOX"
  default_message_limit: 50
  timeout_seconds: 30
```

There is **no** credential value key in configuration -- only the two
environment-variable *names* are configurable. Authentication uses
those two environment variables only. `email.enabled` defaults to
`false`, unlike EP-039/040/041's `true` default, because IMAP has no
safe universal default host (unlike a fixed REST API root) -- an
operator must supply `imap_host` and explicitly enable the subsystem.
When `email.enabled` is `false`, Bootstrap never constructs
`EmailService` and never registers `EmailModule` -- `email <anything>`
falls through to "Unknown command," matching every other disabled
subsystem in this project.

## Security

- IMAP username/password are read from `os.environ` at the start of
  every operation call -- never at `__init__`, never cached on `self`
  beyond the duration of a single call, never logged
- Credentials are sent only inside the IMAP `LOGIN` command; they
  never appear in a log line, an exception message, or an
  `EmailResult` -- every error message in this subsystem is built
  from fixed text and/or non-secret server response text, never the
  credential values
- `EmailModule` never reads or handles credentials at all, and never
  imports `imaplib` -- it has no code path that could reference them
- TLS is mandatory -- `email.tls_mode` only accepts `"ssl"` (implicit
  TLS/IMAPS) or `"starttls"`; no code path connects over plaintext
  IMAP. Certificate validation uses `ssl.create_default_context()`,
  with no configuration option to disable it
- No new secret storage mechanism and no new third-party dependency
  were introduced

## Error handling

`EmailService` maps IMAP/protocol-layer failures onto the
`EmailError` hierarchy: missing/blank credentials or a rejected login
raise `EmailAuthenticationError`, connection-level failures raise
`EmailConnectionError`, timeouts raise `EmailTimeoutError`,
TLS/certificate failures raise `EmailTLSError`, an unselectable
folder raises `EmailMailboxError`, a missing UID raises
`EmailMessageNotFoundError`, rejected search criteria raise
`EmailSearchError`, and any other protocol failure or unparseable
response raises `EmailProtocolError`. Message/header decoding
additionally falls back to a best-effort UTF-8 decode rather than
raising on a malformed/unrecognized MIME charset (fixed during STEP 3
-- see CHANGELOG.md). `EmailModule` catches `EmailError` uniformly and
formats every failure as `CommandResult(success=False, ...)`, never
letting an exception propagate to the CLI layer.

## Testing strategy

`tests/EP042/test_email_service.py` and
`tests/EP042/test_email_module.py` never make a real IMAP network
call and never require a real mailbox. Every test constructs
`EmailService` with a small duck-typed stub `connection` object
mimicking `imaplib.IMAP4_SSL`/`IMAP4`'s tuple-response interface.
Coverage includes the successful call for each of the four
operations (including a real multipart message with an attachment,
parsed by the standard-library `email` package), every
connection/authentication/TLS/timeout/mailbox/search failure mapping,
missing/blank credential handling, invalid configuration, CLI
dispatch/argument validation, real `Bootstrap` enabled/disabled
wiring, a dedicated read-only-boundary assertion, a dedicated
assertion that a fixed fake credential value never appears in any
exception message, and (added during STEP 3) dedicated regression
tests for malformed-charset handling, RFC 2047-decoded To/Cc headers,
and numeric UID ordering.

## Regression verification

The EP042 test suite and the full project test suite were run via
the project's actual test runner as part of both STEP 3 and STEP 4.
Results (STEP 4, final):

```
EP042 Service : 55 passed / 0 failed / 0 skipped
EP042 Module  : 28 passed / 0 failed / 0 skipped
```

`test all`: 5376 passed / 0 failed / 0 skipped.

Every regression count matches its last recorded baseline -- no
regression was introduced by EP042. Source, test, and configuration
files outside the files listed as modified for this EP were verified
unchanged.

## Known limitations

- No SMTP / message-sending capability anywhere in this subsystem
- No reply, forward, delete, move, or flag/mark operation
- No provider-specific API (Gmail API, Microsoft Graph, Outlook API)
- No OAuth2 authentication
- No background/scheduled polling and no `IDLE` connection
- No upper bound on retrieved message size (`get_message` fetches the
  full message body for the requested UID)
- No Tool Engine integration (deferred, matching EP-039/040/041)
- `email.enabled` defaults to `false`, unlike EP-039/040/041's `true`
  default (see "Configuration" above for rationale)

## Known technical debt (pre-existing, not introduced by EP-042)

`TestRegistry` keys test suites by `NAME.upper()`. Both
`EmailServiceTest` and `EmailModuleTest` use `NAME = "EP042"`, so only
the class imported last in `src/modules/test_module.py` is reachable
through the CLI `test EP042` command -- the other suite's assertions
are only run when invoked directly. This condition predates EP-042
(the identical collision exists for every prior integration EP's
Service/Module test pair, back to at least EP-038) and was
deliberately left unfixed, per this EP's boundary, for a separate
future maintenance EP to address.

---

# EP-043 — REST API

STEP 1 (Investigation), STEP 2 (Implementation), STEP 3 (API Contract
Hardening), and STEP 4 (Finalization & Release Readiness) all
complete. **EP-043 is COMPLETE.** Scope was confirmed directly by the
project owner (the STEP 1 investigation stopped on an under-specified
title-only roadmap entry -- see `EP043_STEP1_REPORT.md`). Full design
and rationale: `docs/architecture/designs/EP043_DESIGN.md`.
Implementation report: `EP043_STEP2_REPORT.md`. Hardening report:
`EP043_STEP3_REPORT.md`. Finalization report: `EP043_STEP4_REPORT.md`.

## Summary

A REST API, `RestApiServer` (`src/core/api/rest_api_server.py`),
built entirely on the Python standard library (`http.server`) -- no
new `requirements.txt` dependency. Architecturally a Bootstrap-level
sibling of `InteractiveShell`, not a Core -> Service -> Module
subsystem: it holds no business logic and dispatches every request
through `ApiRouter` (`src/core/api/api_router.py`) into the exact
same `CommandRouter` instance `InteractiveShell` and `TelegramRouter`
already use.

## Endpoints

- `GET /health` -- liveness check.
- `GET /api/v1/status` -- equivalent of the CLI's `system status`.
- `POST /api/v1/commands` -- generic `{module, action, arguments}`
  command dispatch: any command the CLI itself could run.

Transport-level problems (malformed JSON, missing `module`, wrong
field types, an unknown path, an unsupported method, or a
`Content-Type` explicitly set to something other than
`application/json`) return `400`/`404`/`405`/`415` with a structured
`{"error": {"code", "message"}}` body. A missing `Content-Type` header
is treated leniently (still parsed as JSON) -- added in STEP 3, see
`EP043_STEP3_REPORT.md`, "Content-Type Handling". A successfully
*routed* request always returns `200`, even if the underlying
command's own result is `success: false` -- clients check the JSON
body's `success` field for the command's business outcome (reviewed
and explicitly retained, unchanged, in STEP 3 -- see `EP043_DESIGN.md`
section 9/10 and `EP043_STEP3_REPORT.md`, "HTTP Semantics").

## Configuration

```yaml
api:
  enabled: false
  host: "127.0.0.1"
  port: 8080
```

`api.enabled` defaults to `false`, unlike EP-039/040/041's `true`
default -- unlike those stateless outbound clients, enabling this
subsystem binds and listens on a real network socket as a side effect
of `Bootstrap.initialize()`, so it stays off until an operator opts
in. Absence of the `api` section is handled identically to
`enabled: false`. STEP 3 hardened this further: a malformed `api.port`
(wrong type, e.g. a string, or out of the 0-65535 range) is now caught
and degrades safely to "REST API disabled" rather than crashing
`Bootstrap.initialize()` -- see `EP043_STEP3_REPORT.md`, "Configuration
Hardening".

## Security

`127.0.0.1` is the default and only supported v1 bind host. No
authentication, TLS, CORS, or rate limiting exists in v1 -- the full
command surface is reachable by anything that can reach the bound
loopback port. Deferred to a future EP (see `docs/BACKLOG.md`).

## Lifecycle

Built and (if enabled) started inside `Bootstrap.initialize()`, after
`CommandRouter`/`InteractiveShell` are built. Runs on a daemon
background thread, independent of `InteractiveShell`'s blocking main
loop. `Bootstrap.shutdown()` (new) stops it cleanly; `src/main.py`
calls it once the shell exits.

## Testing strategy

Single combined suite, `tests/EP043/test_rest_api.py`
(`NAME = "EP043"`) -- deliberately not split into a same-named
Service/Module pair, sidestepping the pre-existing `TestRegistry`
collision (see below) entirely rather than triggering it. Covers
`ApiRouter` dispatch (including argument shell-quoting), all three
endpoints over real HTTP against an OS-assigned ephemeral port,
malformed JSON, missing `module`, 404/405 routing, server start/stop
idempotency, real `Bootstrap` wiring for `api.enabled: true` /
`false` / absent, `Bootstrap.shutdown()`, and a direct check that
`InteractiveShell`/`CommandRouter` still work with `RestApiServer`
running. STEP 3 added: the `415` Content-Type policy (wrong type,
`charset` parameter tolerance, and true header-absence leniency via a
raw `http.client` request), wrong-field-type and unexpected-field
validation, a DTO shape assertion for `/api/v1/status`, five repeated
start/stop cycles with a thread-leak check, malformed-`api.port`
Bootstrap robustness (bad type and out-of-range), and one end-to-end
"external client" test exercising the full documented contract only
(health -> status -> command -> clean shutdown).

## Regression verification

```
EP043 : 83 passed / 0 failed / 0 skipped
```

`test all`: 5459 passed / 0 failed / 0 skipped (previous baseline
5414 + STEP 3's 45 new assertions; every prior EP's count is
unchanged). `ruff check` on every new/changed file: clean (0
findings). Compile check (`py_compile`) across the full `src/` +
`tests/` tree: clean. No leaked `jarvis-rest-api` threads and port
`8080` confirmed free after a full regression run.

## Known limitations

- No authentication/authorization, TLS, CORS, or rate limiting (v1
  scope boundary -- reviewed again and explicitly retained in STEP 3
  -- see "Security" above and `EP043_DESIGN.md` section 5/19)
- No per-subsystem REST resources -- v1 ships one generic
  `/api/v1/commands` endpoint rather than e.g. dedicated
  `/api/v1/email/...` routes
- No OpenAPI/Swagger schema -- no existing project convention for one
  was found in STEP 3's audit, so this remains a documented future
  extension rather than newly introduced tooling
- No WebSocket/streaming support
- A command that sets `CommandResult.should_exit` (e.g. `system
  exit`) has no effect when dispatched over the REST API -- only
  `InteractiveShell`'s own loop reads that field
- `api.enabled` defaults to `false`, unlike EP-039/040/041's `true`
  default (see "Configuration" above for rationale)
- No code-level guard prevents an operator from setting `api.host` to
  a non-loopback address without also configuring authentication --
  documented as an operator responsibility, not enforced

## Known technical debt

Sidestepped rather than fixed for this EP: `TestRegistry`'s
`NAME.upper()` keying (pre-existing since at least EP-038 -- see the
EP-042 section above). EP-043 avoids triggering it by registering a
single `EP043` suite instead of a same-named Service/Module pair.

## STEP 4 — Finalization

A final architecture/contract/configuration/lifecycle audit found no
blocking defect and no discrepancy between documentation and the live
implementation, so no code change was required or made. `VERSION`
(`0.1.0-alpha`) and `PROJECT_MANIFEST.md` were checked against
established convention (neither has ever been updated per-EP, for any
prior EP) and deliberately left unchanged. Final validation:

```
EP043 : 83 passed / 0 failed / 0 skipped (unchanged from STEP 3 -- no
        new test was added, since no code changed)
test all : 5459 passed / 0 failed / 0 skipped (unchanged from STEP 3)
ruff check src/core/api/ tests/EP043/: 0 findings
py_compile (full src/ + tests/ tree): clean
```

Final archive: `jarvis-ep043-complete.zip` (the STEP 3 archive,
`jarvis-ep043-step3-complete.zip`, was retained unmodified as a prior
recovery point). Full detail: `EP043_STEP4_REPORT.md`.

**EP-043 is COMPLETE.**

---

# EP-052 — File Automation

Status: Released

Highlights:

- Added File Automation: general-purpose file and directory management
  (list, check existence, inspect metadata, read/write text, copy,
  move, create a directory, delete) as an explicit, first-class
  capability -- previously Jarvis could only launch files with the OS
  default application (EP-003) or write bytes as a side effect of one
  specific action (EP-050's `desktop screenshot`)
- CLI integration: file list / exists / stat / read / write / copy /
  move / mkdir / delete / help
- Layered security model: disabled by default, an explicit allowed-
  roots allow-list (empty blocks everything), a separate deny-list for
  specific paths inside an allowed root, path-traversal and
  absolute-path rejection, a separate destructive-action permission
  gating move/delete/overwrite, non-recursive delete only, and
  UTF-8-only file content
- A Windows-path-handling defect in the shared command tokenizer
  (`CommandRouter`) was found and fixed during the Architecture Audit,
  under an explicit owner decision -- Windows backslash paths are now
  preserved correctly for every `file` action
- Invalid configuration disables File Automation for that run (logged)
  instead of crashing the rest of Jarvis on startup

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed, aside from the owner-authorized `CommandRouter` tokenizer
fix described above.

No breaking changes.

Validation:

EP052 : 135 passed / 0 failed / 0 skipped

---

# EP-053 — Vision Integration

Status: Released (PASSED WITH FINDINGS -- one non-blocking finding
documented, not fixed; see "Known limitations" below)

Highlights:

- Added Vision Integration: local, read-only image interpretation --
  image metadata (dimensions, format, color mode, file size) and
  OCR text extraction -- as an explicit, first-class capability --
  previously Jarvis could capture a screenshot (EP-050/EP-051) but had
  no way to look at what was inside one
- CLI integration: vision info / ocr / help
- Local-only, CPU-only v1: built on Pillow (image decoding) and
  `pytesseract` (OCR, via an external Tesseract binary) -- no image
  byte or path is ever sent to an AI provider or any other network
  destination
- Layered security model: disabled by default, an explicit,
  independently-configured allowed-roots allow-list (empty blocks
  everything, no coupling to File Automation's own allow-list),
  path-traversal/absolute-path/symlink-escape rejection, and
  configurable file-size/dimension resource limits
- `vision info` works without the Tesseract OCR engine installed;
  only `vision ocr` requires it

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed. `src/core/command_router.py`, `src/core/tool/`, `src/core/
ai/provider.py`, and `src/skills/desktop/`/`browser/`/`files/` are
all unmodified.

No breaking changes.

Known limitations:

- `LocalVisionBackend` currently enforces its configured
  `max_dimension` resource limit *after* the image has already been
  fully decoded, rather than before -- a documented, non-blocking
  finding from the STEP 3 Architecture Audit. The limit is still
  always enforced and no oversized result is ever returned; the
  practical effect is that an oversized-dimension image is
  unnecessarily fully decoded immediately before being rejected. See
  `docs/architecture/audits/EP053_ARCHITECTURE_AUDIT.md` Section 15,
  Finding 1, for full detail. This was not fixed during STEP 4, per
  the audit's own "document, do not fix" rule.
- No AI-provider-based ("what does this image show") semantic
  description capability -- v1 is local OCR/metadata only

Validation:

EP053 : 58 passed / 0 failed / 0 skipped

---

# EP-054 — Self Reflection

Status: Released (PASSED WITH FINDINGS -- two non-blocking findings
documented, not fixed; see "Known limitations" below)

A note on scope: unlike prior Engineering Packages, "Self Reflection"
had no functional specification anywhere in the project's own
documentation beyond its title. Rather than inventing a feature scope,
the design phase surveyed the existing architecture and proposed the
smallest, most bounded interpretation consistent with it: an on-demand
self-critique of the current conversation.

Highlights:

- Added Self Reflection: on-demand, AI-generated self-critique of the
  current conversation's recent messages -- what went well, what could
  be improved, and one concrete thing to remember for next time
- CLI integration: reflect summary [count] / reflect recall [count] /
  reflect help
- Composes existing components only -- the Conversation Engine (read
  only) and the already-configured AI provider -- with no new external
  service, no new backend abstraction, and no new dependency
- Strictly descriptive in this release: reflections are returned as
  text (and, optionally, saved for later recall) but never
  automatically change any setting, prompt, or behavior
- Optional persistence: reflections can be saved and recalled later,
  off by default
- Built-in safeguards: disabled by default, a cap on how much
  conversation history one reflection may include, and a simple rate
  limit on how often it can call the AI provider

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior
changed. `src/core/command_router.py`, `src/core/tool/`, every
`src/core/ai/*` file, `src/core/memory/`, `src/core/agent/`,
`src/core/planning/`, `src/core/scheduler/`, and every prior skill
(`desktop`/`browser`/`files`/`vision`) are all unmodified.

No breaking changes.

Known limitations:

- A test the design document committed to adding (a real, non-fake
  check of the optional save/recall feature) was not included in the
  automated test suite. The underlying feature was independently
  verified to work correctly during the architecture audit; this is a
  test-coverage gap, not a functional problem. See
  `docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md` Section 15,
  Finding 1.
- If reflection is turned off and someone requests an unusually large
  reflection window in the same request, the response can reveal the
  configured limit's numeric value before confirming the feature is
  off. No conversation content or AI-provider call is ever involved --
  this is a minor, low-impact ordering detail. See
  `docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md` Section 15,
  Finding 2.
- No scheduled/automatic reflection (manual, on-demand only) and no
  autonomous use of a reflection's content -- both are intentionally
  reserved for later Engineering Packages

Validation:

EP054 : 76 passed / 0 failed / 0 skipped

---

End of document.