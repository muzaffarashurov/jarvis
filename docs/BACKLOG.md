# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-038 — Git Integration

Implemented scope:

- A new, independent Core -> Service -> Module subsystem
  (`src/core/git/`, `src/services/git_service.py`,
  `src/modules/git_module.py`) exposing five read-only operations --
  `status`, `diff`, `log`, `branch`, `show` -- by shelling out to the
  system `git` executable via `subprocess`. No third-party git library
  was added. No `commit`, `push`, `pull`, or `clone` capability exists
  anywhere in this subsystem. `GitService` has no dependency on any
  other Engineering Package's service or engine -- the first EP since
  EP-033 with zero cross-EP runtime dependency. Config-gated in
  Bootstrap via `git.enabled` (default true), matching every other
  soft-toggle subsystem; `git.repository_path` defaults to Bootstrap's
  own project root when unset. See CHANGELOG.md / docs/RELEASE_NOTES.md
  / docs/architecture/designs/EP038_DESIGN.md for full detail.

Status:

STEP 1-3 complete (design, implementation, and documentation). STEP 4
Architecture Audit not yet performed -- EP-038 is not yet marked
complete in docs/architecture/JARVIS_ROADMAP.md, and "Next Engineering
Package" below remains EP-038 rather than advancing to EP-039 until
that audit is done.

Note: EP-037 — Event Bus is now complete through STEP 4 (see
CHANGELOG.md / docs/RELEASE_NOTES.md /
docs/architecture/audits/EP037_AUDIT.md). It did not create a second
event bus -- it strengthened and put the existing
`src/core/events.py::EventBus` (in place since EP-001) into real
production use: `EventBus.publish()`/`subscribe()`/`unsubscribe()`
became thread-safe (a lock-protected snapshot of subscribers is
invoked outside the lock), and two new production event paths were
wired through it. `WorkflowEngineService` (EP-033) and
`WorkflowSchedulerEngine` (EP-034) now publish `"workflow.completed"`
(`definition_id`, `result`) at the same point their existing
`automation_hook` already fired; `BackgroundWorkerPool` (EP-036) now
publishes `"background_worker.task_completed"` /
`"background_worker.task_failed"` (`task_id`, `workflow_id`,
`result`/`error`) at its existing task-completion transitions. In
production, Bootstrap now reaches `AutomationEngine.notify_run()`
(EP-035) by subscribing it to `"workflow.completed"`, replacing the
two separate `set_automation_hook()` calls that previously wired
on-demand and scheduled runs to it (the hook APIs themselves remain
intact for backward compatibility; they are simply no longer used for
production automation wiring). A second, small Bootstrap-local adapter
closes the one remaining gap: `BackgroundWorkerPool` calls the raw
`WorkflowEngine.run()` directly rather than going through
`WorkflowEngineService`, so a `worker submit` task previously had no
path to automation at all -- the adapter subscribes to
`"background_worker.task_completed"` only, re-keying its existing
`workflow_id` kwarg to the `definition_id` kwarg `notify_run()`
expects, without changing that event's payload contract.
`"background_worker.task_failed"` is deliberately not wired to
automation, since it carries no `WorkflowRunResult`. The two
production notification paths (`workflow.completed` and
`background_worker.task_completed`) are structurally disjoint --
different event names, one subscriber each, published from call paths
that never both fire for the same run -- so a workflow completion,
however it was dispatched, triggers automation exactly once.

SCOPE NOTE: EP-037 STEP 4 was a read-only Architecture Audit (no code,
test, or configuration changes), per
docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md. It identified two
tracked, non-urgent architecture-debt items rather than any Critical
or High finding: AD-007 (Low) -- a background-worker-triggered
automation action workflow runs synchronously on the pool worker
thread that completed the triggering task, which could delay that
worker under load; and AD-008 (Low) -- the background-worker adapter's
payload key access is implicitly, not explicitly, coupled to
`BackgroundWorkerPool`'s exact publish-call kwarg names, with a silent
(log-only) failure mode if that shape ever changes. Both are recorded
in docs/architecture/ARCHITECTURE_DEBT.md and are explicitly deferred
to a future Architecture Cleanup milestone, not to EP-038.

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