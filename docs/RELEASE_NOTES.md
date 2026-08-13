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

End of document.