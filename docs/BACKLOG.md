# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-035 — Automation Engine

Planned objectives:

- Tracked in docs/architecture/JARVIS_ROADMAP.md, Phase 5 (Workflow
  Automation), as the third of that phase (after EP-033 Workflow
  Engine and EP-034 Workflow Scheduler; alongside EP-036 Background
  Workers and EP-037 Event Bus). Not yet scoped in detail.

Status:

Planned

Note: EP-034 — Workflow Scheduler is now complete (see CHANGELOG.md /
docs/RELEASE_NOTES.md). It is a new, independent package
(`src/core/workflow_scheduler/`) that gives an EP-033 workflow
definition a time trigger: runs it automatically on a schedule
(manual/once/interval/daily/weekly -- cron remains an interface only,
matching EP-011's own documented TODO), by calling EP-033's
already-existing `WorkflowEngine.run(workflow_id)` exclusively. It
performs no AI reasoning, no planning, and no direct real-subsystem/
tool invocation of its own. `ScheduledWorkflow`
(`scheduled_workflow.py`) reuses EP-011's `Schedule`/`ScheduleType`/
`JobStatus` value types unchanged; `WorkflowSchedulerEngine`
(`workflow_scheduler_engine.py`) is the only component holding a
reference to EP-033's `WorkflowEngine`, reached through its public
`run()` method only, and deliberately reimplements (rather than
calls) EP-011's `Scheduler.calculate_next_run` date math, since that
method is typed to and reads fields from `Job` specifically.

NAMING NOTE: this project already had a completed, **actively wired**
`Job`/`Scheduler`/`SchedulerService`/`SchedulerModule` component from
EP-011 (`src/core/scheduler/`, still running its own default jobs on
its own background thread today, left completely untouched by
EP-034). EP-034 is deliberately namespaced apart from it at every
layer -- package (`workflow_scheduler`, not `scheduler`), domain type
(`ScheduledWorkflow`, not `Job`), registry
(`ScheduledWorkflowRegistry`, not `JobRegistry`), engine
(`WorkflowSchedulerEngine`, not `Scheduler`), CLI namespace
("autoflow", not "scheduler" or "schedule"), and config key
('workflow_scheduler.*', not 'scheduler.*') -- to avoid any collision,
present or future. See src/core/workflow_scheduler/__init__.py for the
full note.

SCOPE NOTE carried over from EP-034: `WorkflowSchedulerEngine` has no
separate Provider/Manager layer -- there is exactly one way to compute
a next-run time and exactly one way to dispatch a due entry, so a
swappable provider abstraction with only one implementation would be
speculative rather than justified by an actual second strategy
(matching EP-011's own Scheduler, which likewise has no Provider
layer). No "register" CLI command exists for `autoflow` either,
matching EP-011's `SchedulerModule` and EP-033's
`WorkflowEngineModule` precedent -- entries are registered only
through the public `WorkflowSchedulerService.register()` API. An
Automation Engine (Phase 5 of JARVIS_ROADMAP.md) remains future work,
tracked as EP-035 above.

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