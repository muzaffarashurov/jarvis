# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-029 — Planning Engine

Planned objectives:

- Tracked in docs/architecture/JARVIS_ROADMAP.md, Phase 4 (Agent
  Framework), alongside EP-030 Execution Engine, EP-031 Tool Engine,
  and EP-032 Multi-Agent Collaboration. Not yet scoped in detail. Will
  be the first component to make real use of EP-028's Agent Framework
  orchestration scaffolding -- specifically its `execute()` /
  `AgentExecutionResult.dispatched` extension point, left at False by
  every EP-028 request until a real Planner exists to dispatch to.

Status:

Planned

Note: EP-028 — Agent Framework is now complete (see CHANGELOG.md /
docs/RELEASE_NOTES.md). It is a new, independent package
(`src/core/agent/`) that orchestrates already-implemented Engineering
Packages -- agent lifecycle (initialize/shutdown/reset/status), a
subsystem registry (register_subsystem/unregister_subsystem/
list_subsystems), and request acknowledgment (execute/cancel) --
structurally mirroring EP-026/EP-027's provider/manager pattern
(AgentProvider / DefaultAgentProvider / AgentManager). It performs no
planning, reasoning, task decomposition, tool execution, prompt
construction, or AI provider call: every `execute()` call is
synchronously accepted and acknowledged only
(`AgentExecutionResult.dispatched` is always False), and `cancel()`
always reports nothing left to cancel, since there is no asynchronous
task to interrupt. It reaches every subsystem (Embedding Engine, RAG
Engine, Memory Manager, Knowledge Base, Long-Term Memory, Semantic
Search, Context Compression) only through a single, caller-supplied
status-check callable bound to that subsystem's own public
`status().enabled` -- never its internals. It has no dependency on any
AI provider, the Prompt Engine, the Conversation Engine, or any of the
eight future orchestration components named in its own task brief
(Planner, Reasoning Engine, Reflection Engine, Workflow Engine, Task
Scheduler, Tool Executor, Conversation Engine integration, Multi-Agent
Coordinator). A Planning Engine (Phase 4 of JARVIS_ROADMAP.md) remains
future work, tracked as EP-029 above.

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