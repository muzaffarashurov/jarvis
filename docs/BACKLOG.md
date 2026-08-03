# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

### EP-028 — Agent Framework

Planned objectives:

- Tracked in docs/architecture/JARVIS_ROADMAP.md, Phase 4 (Agent
  Framework), alongside EP-029 Planning Engine, EP-030 Execution
  Engine, EP-031 Tool Engine, and EP-032 Multi-Agent Collaboration.
  Not yet scoped in detail.

Status:

Planned

Note: EP-027 — Context Compression is now complete (see CHANGELOG.md /
docs/RELEASE_NOTES.md). It is a new, independent package
(`src/core/context_compression/`) that shrinks already-assembled
context (raw text, or EP-026 Semantic Search results) down to a
configured character/chunk budget, structurally mirroring
EP-021/EP-023/EP-024/EP-025/EP-026's provider/manager pattern
(CompressionProvider / DefaultCompressionProvider / CompressionManager).
It performs only deterministic, arithmetic operations -- deduplication
(whole-chunk and paragraph-level), ordering/metadata preservation, and
max-chunk/max-character enforcement -- never AI reasoning,
summarization, or text rewriting (only truncation to fit a character
budget). It has no hard dependency on Semantic Search, the Embedding
Engine, Knowledge Base, or Long-Term Memory: compressing raw
text/chunks works standalone; only the optional `compress_query()`
convenience reaches EP-026's SemanticEngine, through its public
`search()` method only. It has no dependency on any AI provider, the
Prompt Engine, the RAG Engine, the Conversation Engine, or any future
Agent Framework component. An Agent Framework (Phase 4 of
JARVIS_ROADMAP.md) remains future work, tracked as EP-028 above.

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