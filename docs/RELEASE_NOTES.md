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

End of document.