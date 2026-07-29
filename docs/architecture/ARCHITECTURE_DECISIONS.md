# Architecture Decisions (ADR)

Version: 1.0

This document records architectural decisions made during the development of the project.

Its purpose is to preserve engineering knowledge and explain WHY the architecture looks the way it does.

---

# ADR-001
## PROJECT_MANIFEST is the project entry point

Decision

Every project MUST contain PROJECT_MANIFEST.md.

The manifest is the only official source that identifies the current project.

Reason

The AI must never determine project identity from folder names or hardcoded paths.

---

# ADR-002
## Universal Repository Detection

Decision

Repository detection must work for every project.

No project-specific paths are allowed.

Reason

The same AI engine must work with Jarvis and any future project.

---

# ADR-003
## No Hardcoded Project Knowledge

Decision

AI components must never contain project-specific knowledge.

All project information must come from:

- PROJECT_MANIFEST.md
- README.md
- architecture documents

Reason

The engine must be reusable.

---

# ADR-004
## Single Source of Truth

Decision

Every responsibility has exactly one owner.

Examples

Repository detection

Manifest parsing

Prompt budget

Conversation budget

Configuration loading

Reason

Avoid duplicated logic.

---

# ADR-005
## Shared Components

Decision

If multiple modules need the same functionality,
that functionality must be extracted into a shared module.

Reason

Avoid copy-paste implementations.

---

# ADR-006
## Context Engine Responsibilities

Context Engine is responsible ONLY for

- locating repository
- reading PROJECT_MANIFEST
- loading project documents
- assembling project context
- enforcing context budget

Context Engine is NOT responsible for

- indexing
- embeddings
- retrieval
- vector search

---

# ADR-007
## Project Index Responsibilities

Project Index is responsible ONLY for

- scanning project files
- chunk generation
- metadata
- index persistence

Project Index never talks to an LLM.

---

# ADR-008
## Retrieval Responsibilities

Retrieval only selects relevant chunks.

It does not generate embeddings.

It does not call AI providers.

---

# ADR-009
## Embedding Responsibilities

Embedding Engine converts text into vectors.

Nothing else.

---

# ADR-010
## RAG Responsibilities

RAG combines

- Retrieval
- Embeddings
- Ranking

and prepares AI context.

---

# ADR-011
## AI Provider Isolation

Every AI provider implements the same interface.

Supported providers may include

- Gemini
- Claude
- Ollama
- OpenAI
- LM Studio

Business logic must never depend on a concrete provider.

---

# ADR-012
## Prompt Budget

Prompt size is controlled centrally.

All components must respect the same budget.

No component may independently exceed the configured limits.

---

# ADR-013
## Conversation Budget

Conversation history has its own reserved budget.

Oldest messages are discarded first.

Newest messages always have priority.

---

# ADR-014
## Documentation First

Every architectural decision must be documented before implementation.

The roadmap, manifest and architecture documents define the expected behaviour.

Code follows documentation.

Never the opposite.

---

End of document.