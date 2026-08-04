# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-030 — Execution Engine

Planned objectives:

- Tracked in docs/architecture/JARVIS_ROADMAP.md, Phase 4 (Agent
  Framework), alongside EP-031 Tool Engine and EP-032 Multi-Agent
  Collaboration. Not yet scoped in detail. Will be the first component
  to turn an EP-029 `Plan` into actual work -- executing (or
  dispatching for execution) each `PlanStep` in order, respecting the
  `available` flag EP-029 already computes per step.

Status:

Planned

Note: EP-029 — Planning Engine is now complete (see CHANGELOG.md /
docs/RELEASE_NOTES.md). It is a new, independent package
(`src/core/planning/`) that decomposes a request into an ordered Plan
of steps referencing already-implemented Engineering Packages by name,
structurally mirroring EP-026/EP-027/EP-028's provider/manager pattern
(PlanningProvider / DefaultPlanningProvider / PlanningManager). It
performs no AI reasoning, no AI provider call, no prompt construction,
and no task execution: the built-in provider matches the request
against a fixed, deterministic keyword-rule table (case-insensitive
substring matching only), emits at most one step per matched
subsystem, and falls back to a single explicit "nothing matched" step
rather than ever raising an error for an unrecognized request. It
reaches EP-028's Agent Framework only through its public
`AgentEngine.list_subsystems()` method, to optionally reconcile each
step's `available` flag against the subsystems actually registered and
enabled at runtime -- never any subsystem's internals, and this
integration is itself optional (planning works standalone with no
Agent Framework at all). It has no dependency on any AI provider, the
Prompt Engine, the Conversation Engine, a Reasoning Engine, a
Reflection Engine, or a Tool Executor. An Execution Engine (Phase 4 of
JARVIS_ROADMAP.md) remains future work, tracked as EP-030 above.

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