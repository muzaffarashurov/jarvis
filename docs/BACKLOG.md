# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-026 — Semantic Search

Planned objectives:

- Meaning-based search over Knowledge Base (EP-024) and Long-Term
  Memory (EP-025) records, building on EP-021's Embedding Engine and
  EP-022's RAG Engine rather than duplicating either
- Read API consumed by the future AI Agent Framework
- Provider-independent, no direct dependency on any AI provider
- Keep clear separation from EP-022's RAG Engine (retrieval-time
  context assembly for chat completion), EP-024's Knowledge Base
  (static structured storage), and EP-025's Long-Term Memory
  (persistent lifecycle storage) -- Semantic Search adds ranking and
  similarity, it does not store anything itself

Status:

Planned

Note: EP-025 — Long-Term Memory is now complete (see CHANGELOG.md /
docs/RELEASE_NOTES.md). It is a new, independent package
(`src/core/long_term_memory/`) that manages the persistent storage and
active/archived lifecycle of long-lived memories, structurally
mirroring EP-023's and EP-024's provider/manager pattern
(LongTermProvider / KnowledgeBackedLongTermProvider /
LongTermMemoryManager). It introduces no third storage engine:
persistence is delegated entirely to EP-024's KnowledgeService (a
dedicated "long_term_memory" collection), reached only through its
public API. It also extends EP-023's Memory Manager -- a
`LongTermMemoryProvider` is registered with `MemoryService` (via the
new, additive `MemoryService.register_provider` method) as a
"long_term" provider, visible to `memory providers` / `memory use
long_term`. It performs no ranking, similarity search, embeddings, or
AI reasoning. Semantic Search and Context Compression remain future
work, tracked as EP-026 (Semantic Search) and EP-027 (Context
Compression) below, matching Phase 3 of JARVIS_ROADMAP.md.

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