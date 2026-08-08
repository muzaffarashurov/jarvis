# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-036 — Background Workers

Planned objectives:

- Tracked in docs/architecture/JARVIS_ROADMAP.md, Phase 5 (Workflow
  Automation), as the fourth of that phase (after EP-033 Workflow
  Engine, EP-034 Workflow Scheduler, and EP-035 Automation Engine;
  alongside EP-037 Event Bus). Not yet scoped in detail.

Status:

Planned

Note: EP-035 — Automation Engine is now complete (see CHANGELOG.md /
docs/RELEASE_NOTES.md). It is a new, independent package
(`src/core/automation_engine/`) that chains one EP-033 workflow's
completion -- whether started on-demand via
`WorkflowEngineService.run()`, or automatically via EP-034's
`WorkflowSchedulerEngine.run_now()`/`tick()` -- into a second workflow
run, based on outcome (ON_SUCCESS / ON_FAILURE / ON_ANY), by calling
EP-033's already-existing `WorkflowEngine.run(workflow_id)`
exclusively. It performs no AI reasoning, no scheduling of its own,
and no direct real-subsystem/tool invocation of its own.
`AutomationRule`/`AutomationTriggerCondition`
(`automation_rule.py`) are a new, independent domain type -- not a
reuse of EP-034's `ScheduledWorkflow` (an automation rule carries no
`Schedule` or tick participation; a `ScheduledWorkflow` carries no
trigger condition or action workflow). `AutomationEngine`
(`automation_engine.py`) is the only component holding a reference to
EP-033's `WorkflowEngine`, reached through its public `run()` method
only. The reactive hook itself (`AutomationEngine.notify_run`) is
wired into `WorkflowEngineService`/`WorkflowSchedulerEngine` as a bare
`Callable`, so neither of those EP-033/EP-034 classes imports
Automation Engine or any of its types -- the dependency direction
stays one-way.

SCOPE NOTE: EP-035 is deliberately synchronous, single-hop, and
non-recursive -- it owns no background thread, no queue, and no
generic event bus (those remain EP-036/EP-037, both still future
work, tracked above/below). An action workflow's own completion is
dispatched directly through `WorkflowEngine.run()`, bypassing the
hook entirely, so it never re-enters `notify_run()` and can never
trigger a further rule (A -> B is supported; A -> B -> C is not, and
no cycle detection was implemented, since recursive chaining itself
was out of scope). `AutomationEngine` has no separate Provider/Manager
layer either, matching EP-034's own `WorkflowSchedulerEngine`
precedent -- there is exactly one way to evaluate a rule and exactly
one way to dispatch a match. No "register" or manual "trigger"/"run"
CLI command exists for `automate` either, matching EP-011's
`SchedulerModule`, EP-033's `WorkflowEngineModule`, and EP-034's
`WorkflowSchedulerModule` precedent -- rules are registered only
through the public `AutomationService.register()` API.

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