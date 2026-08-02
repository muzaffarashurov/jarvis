# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-027 — Context Compression

Planned objectives:

- Compress/summarize retrieved context (from EP-022's RAG Engine and/or
  EP-026's Semantic Search) to fit within an AI provider's prompt
  budget, building on EP-021's Embedding Engine rather than duplicating
  it
- Read API consumed by the future AI Agent Framework
- Provider-independent, no direct dependency on any AI provider
- Keep clear separation from EP-022's RAG Engine (retrieval-time
  context assembly), EP-024's Knowledge Base (static structured
  storage), EP-025's Long-Term Memory (persistent lifecycle storage),
  and EP-026's Semantic Search (meaning-based ranking) -- Context
  Compression only shrinks already-assembled context, it does not
  retrieve, store, or rank anything itself

Status:

Planned

Note: EP-026 — Semantic Search is now complete (see CHANGELOG.md /
docs/RELEASE_NOTES.md). It is a new, independent package
(`src/core/semantic/`) that performs meaning-based similarity search
over Knowledge Base (EP-024) and Long-Term Memory (EP-025) records,
structurally mirroring EP-021/EP-023/EP-024/EP-025's provider/manager
pattern (SemanticProvider / DefaultSemanticProvider / SemanticManager).
It introduces no new embedding pipeline: query and candidate vectors
are generated entirely through EP-021's EmbeddingEngine, reached only
through its public API, and it reads Knowledge Base / Long-Term Memory
records only through KnowledgeService.list_records() /
LongTermMemoryService.list_memories(). It has no dependency on EP-022's
RAG Engine, any AI provider, or any future Agent Framework component --
it performs no answer generation, prompt construction, context
compression, planning, reflection, or reasoning. Note that with
EP-021's built-in offline "local" (SHA-256 hash) embedding provider,
only exact/near-exact text matches are meaningful -- see
docs/RELEASE_NOTES.md's "Known limitation" for EP-026. Context
Compression remains future work, tracked as EP-027 (Context
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