# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-033 — Workflow Engine

Planned objectives:

- Tracked in docs/architecture/JARVIS_ROADMAP.md, Phase 5 (Workflow
  Automation), as the first of that phase (alongside EP-034 Scheduler,
  EP-035 Automation Engine, EP-036 Background Workers, and EP-037
  Event Bus). Not yet scoped in detail.

Status:

Planned

Note: EP-032 — Multi-Agent Collaboration is now complete (see
CHANGELOG.md / docs/RELEASE_NOTES.md). It is a new, independent
package (`src/core/collaboration/`) that implements the Multi-Agent
Coordinator explicitly deferred by EP-028 through EP-030's own
docstrings: deterministic broadcast of a single request across every
agent currently registered with EP-028's Agent Framework
(`AgentManager.list_providers()`), with each agent's own
`AgentExecutionResult` collected into a uniform outcome. It performs
no AI reasoning, no negotiation, and no inter-agent messaging, and
structurally mirrors EP-026/EP-027/EP-028/EP-029/EP-030/EP-031's own
provider/manager pattern (CollaborationProvider /
DefaultCollaborationProvider / CollaborationManager /
CollaborationEngine). It reaches EP-028's Agent Framework only through
`AgentManager`'s public `list_providers()` method and each
`AgentProvider`'s own public `agent_name()`/`status()`/`execute()`
methods -- never any subsystem's internals. It is distinct from
EP-028's own subsystem registry (`AgentProvider.register_subsystem()`),
which coordinates *subsystems* a single agent is aware of; EP-032
coordinates *agents* themselves.

SCOPE NOTE carried over from EP-032: this Engineering Package
coordinates whole requests across agents (broadcast), not individual
EP-029 `PlanStep`s across agents. Distributing a single `Plan`'s steps
across multiple agents would require widening `PlanStep`'s schema with
an agent assignment -- an EP-029/EP-030 architecture change explicitly
out of scope for EP-032, per this project's Unknown API Policy. Only
one real agent ("jarvis", EP-028's `DefaultAgentProvider`) is
registered in this project today; multi-agent scenarios are exercised
in EP-032's own test suite through independently registered test
agents, not through any new built-in agent. A Workflow Engine (Phase 5
of JARVIS_ROADMAP.md) remains future work, tracked as EP-033 above.

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