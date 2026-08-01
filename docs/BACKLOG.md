# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-025 — Long-Term Memory

Planned objectives:

- Durable, queryable long-term memory for the future AI Agent Framework,
  building on EP-023's Memory Manager (provider registration/switching)
  and EP-024's Knowledge Base (structured records/collections) rather
  than duplicating either
- Read/write API consumed by the future AI Agent Framework
- Provider-independent, no direct dependency on any AI provider
- Keep clear separation from EP-022's RAG Engine (retrieval-time
  context assembly), EP-024's Knowledge Base (static structured
  records), and EP-019's ProjectIndex (static repository content)

Status:

Planned

Note: EP-024 — Knowledge Base is now complete (see CHANGELOG.md /
docs/RELEASE_NOTES.md). It is a new, independent package
(`src/core/knowledge/`) that manages structured project-knowledge
records organized into named collections, structurally mirroring
EP-023's provider/manager pattern (KnowledgeProvider /
KnowledgeCollectionProvider / KnowledgeManager) but with its own
storage engine (KnowledgeCollection) -- it does not wrap or extend
MemoryStore/MemoryManager, and it performs no reasoning, embeddings,
retrieval, or RAG. Long-Term Memory, Semantic Search, Context
Compression, and any External knowledge provider remain future work,
tracked as EP-025 (Long-Term Memory), EP-026 (Semantic Search) and
EP-027 (Context Compression) below, matching Phase 3 of
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