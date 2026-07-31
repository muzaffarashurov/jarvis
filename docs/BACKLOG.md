# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-024 — Knowledge Base

Planned objectives:

- Persistent, structured storage of conversational/task knowledge,
  building on EP-023's Memory Manager (provider registration/
  switching) rather than duplicating it
- Read/write API consumed by the future AI Agent Framework
- Provider-independent, no direct dependency on any AI provider
- Keep clear separation from EP-022's RAG Engine (retrieval-time
  context assembly) and EP-019's ProjectIndex (static repository
  content)

Status:

Planned

Note: EP-023 — Memory Manager is now complete (see CHANGELOG.md /
docs/RELEASE_NOTES.md). It is an orchestration layer over
`MemoryProvider` implementations -- registration, enable/disable,
active-provider switching, unified store/load/delete/clear/exists/list
API -- built on top of the existing (EP-013) MemoryStore rather than a
second memory subsystem. It implements no persistent structured
storage of its own beyond that: the "memory" provider it registers by
default simply wraps EP-013's in-process MemoryStore. Persistent,
structured, queryable storage for the AI Agent Framework -- along with
KnowledgeBaseProvider, LongTermMemoryProvider and ExternalProvider --
remains future work, tracked as EP-024 (Knowledge Base) and EP-025
(Long-Term Memory) below, matching Phase 3 of JARVIS_ROADMAP.md.

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