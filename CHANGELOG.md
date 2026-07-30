# CHANGELOG.md

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog.

---

## v0.1.0-ep021

Released: 2026-07-30

### Added

- Embedding Engine
- EmbeddingProvider interface
- Embedding Manager
- Embedding Service
- Embedding Module
- Local embedding provider (deterministic, offline)
- Cloud embedding provider (configuration-driven placeholder)
- CLI integration
- Embedding tests

### Improved

- Provider-independent architecture pattern extended beyond chat completion

### Fixed

-

### Compatibility

Backward compatible with EP-020. Does not modify the Retrieval Engine.

---

## v0.1.0-ep020

Released: 2026-07-30

### Added

- Retrieval Engine
- Retrieval Service
- Retrieval Module
- Search API
- CLI integration
- Retrieval tests

### Improved

- AI infrastructure
- Project navigation
- Knowledge retrieval pipeline

### Fixed

- Internal integration issues between EP-019 and EP-020

### Compatibility

Backward compatible with EP-019.

---

# [Unreleased]

## Added

-

## Changed

-

## Fixed

-

---

# [0.1.0-alpha] - 2026-07-28

## Added

- Interactive Shell (EP-002)
- Process Manager (EP-003)
- AI Provider Framework (EP-014)
- AI Providers (EP-015)
- Conversation Engine (EP-016)
- Prompt Engine (EP-017)
- Universal Context Engine (EP-018)
- PROJECT_MANIFEST.md
- Architecture documentation
- Engineering documentation

## EP-019

Added Project Index Engine.

Features:

- ProjectIndexer
- ChunkBuilder
- JsonIndexStorage
- MemoryIndexStorage
- Index CLI
- Shared PROJECT_MANIFEST parser

## Changed

- Project documentation reorganized.
- Architecture documentation moved to `docs/architecture/`.
- Engineering documentation moved to `docs/engineering/`.
- Context loading redesigned to use `PROJECT_MANIFEST.md` as the single entry point.

## Fixed

- Prompt size budgeting.
- Conversation history budgeting.
- Context Loader document discovery.
- Provider-independent context loading.
- Gemini prompt overflow issues.

---

Future releases will be documented here.