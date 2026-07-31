# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-023 — Memory Manager

Planned objectives:

- Persistent, structured storage of conversational/task memory
- Read/write API consumed by the future AI Agent Framework
- Provider-independent, no direct dependency on any AI provider
- Keep clear separation from EP-022's RAG Engine (retrieval-time
  context assembly) and EP-019's ProjectIndex (static repository
  content)

Status:

Planned

Note: EP-022 — RAG Engine is now complete (see CHANGELOG.md /
docs/RELEASE_NOTES.md). It combines ProjectIndexer (EP-019),
RetrievalEngine (EP-020) and the Embedding Engine (EP-021) into a
provider-independent context-generation pipeline; it does not call any
AI provider and performs no chat completion — that integration
(RAG-assembled context feeding an AI Provider Framework completion
call) is deliberately out of scope for EP-022 and remains future work,
tracked under "AI" below. Memory Manager is next, matching Phase 3 of
JARVIS_ROADMAP.md.

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