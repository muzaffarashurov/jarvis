# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-031 — Tool Engine

Planned objectives:

- Tracked in docs/architecture/JARVIS_ROADMAP.md, Phase 4 (Agent
  Framework), alongside EP-032 Multi-Agent Collaboration. Not yet
  scoped in detail. Will be the first component to turn an EP-030
  dispatched `StepResult` into a real external effect -- actually
  invoking the subsystem action a `PlanStep` names, rather than only
  recognizing and acknowledging it.

Status:

Planned

Note: EP-030 — Plan Execution Engine is now complete (see
CHANGELOG.md / docs/RELEASE_NOTES.md). It is a new, independent
package (`src/core/plan_execution/`) that dispatches an EP-029 Plan's
steps, in order, structurally mirroring EP-026/EP-027/EP-028/EP-029's
provider/manager pattern (PlanExecutionProvider /
DefaultPlanExecutionProvider / PlanExecutionManager). It performs no
AI reasoning, no AI provider call, no prompt construction, and no real
subsystem invocation: the built-in provider recognizes the fixed set
of actions EP-029's `DefaultPlanningProvider` is known to produce and
reports success (dispatched, not yet actually carried out) or a
genuine failure for anything else. It skips any step already reported
unavailable, and (by default) halts the remaining plan after a step
fails. It reaches EP-029's Planning Engine only through its public
`plan()` method, to optionally plan a request before executing it --
never any subsystem's internals, and this integration is itself
optional (execution works standalone given an already-built Plan). It
is deliberately named and namespaced (`plan_execution`, not
`execution`) to avoid any collision with the pre-existing, unrelated
`src/core/execution/` package (EP-003's OS-level target launcher). A
Tool Engine (Phase 4 of JARVIS_ROADMAP.md) remains future work,
tracked as EP-031 above.

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