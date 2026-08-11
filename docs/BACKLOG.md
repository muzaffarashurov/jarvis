# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-037 — Event Bus

Planned objectives:

- Tracked in docs/architecture/JARVIS_ROADMAP.md, Phase 5 (Workflow
  Automation), as the fifth and final EP of that phase (after
  EP-033 Workflow Engine, EP-034 Workflow Scheduler, EP-035 Automation
  Engine, and EP-036 Background Workers). Not yet scoped in detail.

Status:

Planned

Note: EP-036 — Background Workers is now complete through STEP 4 (see
CHANGELOG.md / docs/RELEASE_NOTES.md /
docs/architecture/audits/EP036_AUDIT.md). It is a new, independent
package (`src/core/background_workers/`) that runs already-registered
EP-033 workflows in the background, off the calling thread, through a
configurable pool of daemon worker threads, by calling EP-033's
already-existing `WorkflowEngine.run(workflow_id)` exclusively. It
performs no AI reasoning, no planning, and no direct
real-subsystem/tool invocation of its own. `BackgroundWorkerPool`
(`background_worker_pool.py`) is the only component holding a
reference to EP-033's `WorkflowEngine`, reached through its public
`run()` method only, the same discipline `WorkflowSchedulerEngine`
(EP-034) and `AutomationEngine` (EP-035) already follow. Layering is
`BackgroundWorkerPool` (core) -> `BackgroundWorkerService`
(config-driven lifecycle owner, `src/services/background_worker_service.py`)
-> `BackgroundWorkerModule` (CLI translation layer only,
`src/modules/background_worker_module.py`, exposing the `worker`
namespace) -- each layer reaches the one below it through its public
API only, so the dependency direction stays one-way.

SCOPE NOTE: EP-036 STEP 4 was a read-only Architecture Audit (no code,
test, or configuration changes), per
docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md. It identified two
tracked, non-urgent architecture-debt items rather than any Critical
or High finding: AD-005 (Medium) -- no process-exit shutdown wiring
for `BackgroundWorkerService.shutdown()`, meaning an in-flight task is
terminated mid-run and a still-queued task is silently dropped on
interpreter exit unless `worker stop` was run manually first; and
AD-006 (Low) -- `BackgroundWorkerPool` task history has no
eviction/TTL and grows unbounded over a long-running process. Both are
recorded in docs/architecture/ARCHITECTURE_DEBT.md and are explicitly
deferred to a future Architecture Cleanup milestone, not to EP-037.

---

# Purpose

This document contains ideas, improvements, feature requests and future work that are not yet assigned to an Engineering Package.

Items in this document are not commitments.

They serve as a pool of potential future work.

---

# Rules

Items may be added at any time.

Items may be removed.

Items may later become Engineering Packages.

Priority may change.

---

# Current Backlog

## AI

- Improve project retrieval quality
- Support hybrid search
- Support code embeddings
- Improve provider selection
- Feed EP-022's assembled RAG context into the AI Provider Framework
  for chat completion (deliberately out of scope for EP-022 itself)

---

## User Experience

- Better shell autocomplete
- Command history search
- Improved progress indicators

---

## Tools

- Git integration improvements
- Local file watcher
- Background indexing

---

## Future Ideas

- Voice commands

- Browser automation

- Desktop assistant

- Plugin marketplace

---

End of document.