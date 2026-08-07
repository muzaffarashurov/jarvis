# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-034 — Scheduler

Planned objectives:

- Tracked in docs/architecture/JARVIS_ROADMAP.md, Phase 5 (Workflow
  Automation), as the second of that phase (after EP-033 Workflow
  Engine; alongside EP-035 Automation Engine, EP-036 Background
  Workers, and EP-037 Event Bus). Not yet scoped in detail. A
  'scheduler:' configuration section already exists
  ('enabled'/'auto_start'/'tick_interval' in config/config.yaml) but
  is not backed by any EP-034 component yet -- likely the natural
  starting point once this Engineering Package is scoped.

Status:

Planned

Note: EP-033 — Workflow Engine is now complete (see CHANGELOG.md /
docs/RELEASE_NOTES.md). It is a new, independent package
(`src/core/workflow_engine/`) that runs a named, ordered sequence of
plain-text requests (a `WorkflowDefinition`) as a single, repeatable
unit: each `WorkflowRequestStep` is planned and executed through
EP-030's already-existing `PlanExecutionEngine.execute_request()`
(which itself already optionally calls EP-029's
`PlanningEngine.plan()`), in order, halting the remaining workflow on
failure per 'workflow_engine.stop_on_failure'. It performs no AI
reasoning, no new planning logic, and no direct real-subsystem/tool
invocation of its own, and structurally mirrors
EP-026/EP-027/EP-028/EP-029/EP-030/EP-031/EP-032's own provider/manager
pattern (WorkflowRunProvider / DefaultWorkflowRunProvider /
WorkflowEngineManager / WorkflowEngine). It reaches EP-030's Plan
Execution Engine only through its public `execute_request()` method --
never any subsystem's internals, and never imports EP-029's
`PlanningEngine` directly.

NAMING NOTE: this project already had a completed, dormant
`Workflow`/`WorkflowService`/`WorkflowModule` component from EP-007
(`src/core/workflows/`, never wired into Bootstrap, left untouched by
EP-033). EP-033 is deliberately namespaced apart from it at every
layer -- package (`workflow_engine`, not `workflows`), domain types
(`WorkflowDefinition`/`WorkflowRequestStep`, not
`Workflow`/`WorkflowStep`), registry (`WorkflowDefinitionRegistry`,
not `WorkflowRegistry`), CLI namespace ("flow", not "workflow"), and
config key ('workflow_engine.*', not 'workflows.*') -- to avoid any
collision, present or future. See
src/core/workflow_engine/__init__.py for the full note.

SCOPE NOTE carried over from EP-033: only one built-in workflow-run
provider exists today ("workflow_engine"), and the workflow definition
catalog (`WorkflowDefinitionRegistry`) starts empty at Bootstrap --
this Engineering Package ships the pipeline and its public
`register_definition()` API, not any specific built-in business
workflow, nor a CLI command to author one (only to list/inspect/run
already-registered ones). A Scheduler (Phase 5 of
JARVIS_ROADMAP.md) remains future work, tracked as EP-034 above.

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