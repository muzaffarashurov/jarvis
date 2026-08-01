# RELEASE_NOTES.md

Version: 1.0

Status: Active

---

# Purpose

This document summarizes the user-visible changes introduced in each released version of Jarvis.

Unlike CHANGELOG.md, this document focuses on features and improvements rather than implementation details.

---

EP-019 completed.

Jarvis now supports project indexing.

Available commands:

index build
index rebuild
index status
index clear

# Release 0.1.0-alpha

## Added

- Interactive Shell
- AI Provider Framework
- Conversation Engine
- Prompt Engine
- Universal Context Engine

## Improved

- Provider abstraction
- Context loading
- Prompt generation
- Configuration management

## Fixed

- Context budgeting
- Prompt size validation
- Conversation history handling

---

Future releases will be documented here.

---

# EP-020 — Retrieval Engine

Status: Released

Highlights:

- Added Retrieval Engine
- Semantic retrieval API
- Integration with Project Index Engine
- Document search by relevance
- Modular retrieval architecture
- Provider-independent implementation

Compatibility:

Fully compatible with EP-019.

No breaking changes.

---

# EP-021 — Embedding Engine

Status: Released

Highlights:

- Added a provider-independent Embedding Engine
- Transforms text into embedding vectors only -- no retrieval, no RAG, no chat completion
- Local embedding provider: fully offline, deterministic, no third-party dependency
- Cloud embedding provider: configuration-driven, ready for a future real integration
- CLI integration: embedding status / providers / use / embed / dimension
- Switching providers takes effect immediately, no restart required

Compatibility:

Fully compatible with EP-020. Does not modify the Retrieval Engine.

No breaking changes.

---

# EP-022 — RAG Engine

Status: Released

Highlights:

- Added a provider-independent RAG (Retrieval-Augmented Generation) Engine
- Combines the Project Index Engine (EP-019), the Retrieval Engine (EP-020) and
  the Embedding Engine (EP-021) into a single, reusable context-generation pipeline
- Given a query: obtains its embedding, retrieves and ranks relevant chunks, then
  assembles the highest-ranked chunks (full text, not just a preview) into a single
  context block
- Returns a structured result: the ranked matches used, the assembled context text,
  and which embedding provider produced the query embedding
- Does not call any AI provider and performs no chat completion -- context assembly
  only; feeding this context into a chat completion call is future work
- CLI integration: rag status / query / context / provider / use
- Switching the embedding provider used for RAG takes effect immediately, no restart
  required

Compatibility:

Fully compatible with EP-019, EP-020 and EP-021. Does not modify the Project Index
Engine, the Retrieval Engine, or the Embedding Engine.

No breaking changes.

---

# EP-023 — Memory Manager

Status: Released

Highlights:

- Added a Memory Manager: an orchestration layer over registered memory
  providers, built on top of the existing (EP-013) Memory & Context Manager
  rather than a second memory subsystem
- Register, enable, disable and switch between memory providers, and
  inspect their status, through a single unified API
- The built-in "memory" provider wraps the existing MemoryStore, so every
  entry set/retrieved through the Memory Manager is the same data already
  managed by `memory get` / `memory set` / `memory list`
- CLI integration: memory providers / memory use <provider>, alongside the
  existing memory status / doctor / get / set / delete / clear / list /
  export / import / help
- Invalid provider configuration disables the Memory subsystem for that run
  (logged) instead of crashing the rest of Jarvis on startup
- Only the abstraction and the MemoryStore adapter are implemented -- no
  Knowledge Base, Long-Term Memory, Semantic Search, or External provider
  yet; those remain future work (EP-024 onward)

Compatibility:

Fully backward compatible with EP-013. Every existing `MemoryService` method
and every existing `memory` CLI command behaves exactly as before.

No breaking changes.

---

# EP-024 — Knowledge Base

Status: Released

Highlights:

- Added a Knowledge Base: a new, independent subsystem for storing and
  organizing structured project knowledge into named collections
- Manage structured knowledge records: store, load, update, delete, and
  clear -- scoped to a single collection or across all of them
- Inspect collection statistics (record counts per collection) and
  provider status through a single unified API, mirroring the
  provider/manager pattern already used by the Memory Manager (EP-023)
- CLI integration: knowledge status / collections / list / info / clear /
  help
- Invalid provider configuration disables the Knowledge subsystem for
  that run (logged) instead of crashing the rest of Jarvis on startup
- Knowledge Base performs no reasoning and has no dependency on Memory,
  Embedding, Retrieval, RAG, Long-Term Memory, Semantic Search, Context
  Compression, Planning, Reflection, Agent Memory, or Vector Storage --
  those remain future work (EP-025 onward)

Compatibility:

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its behavior changed.

No breaking changes.

---

End of document.