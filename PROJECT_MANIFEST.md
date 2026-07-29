# PROJECT_MANIFEST.md

This document is the single source of truth for project discovery.

Jarvis components must discover the project structure exclusively through this manifest.

This includes, but is not limited to:

- Universal Context Engine
- Project Index
- Retrieval Engine
- Knowledge Base
- Memory Manager
- Future AI components

The manifest describes the project's identity, documentation, configuration, architecture and knowledge sources.

Project-specific filenames, document locations and directory structures must never be hardcoded anywhere else in the project.

To adapt Jarvis to another project (CRM, ERP, Spring Boot, React, Python, Language Learning, etc.), only this manifest needs to be updated.

The implementation of project discovery remains unchanged.

# Project Name

Jarvis

# Current Version:

0.1.0-alpha

# Repository Root
.

# Project Type

Python / Modular AI Operating System


# Project Description

Jarvis is a modular AI operating system designed to orchestrate multiple AI providers, tools, workflows and business processes through a unified architecture. The long-term objective is an AI assistant capable of acting as a real software engineer, automation platform and personal operating system, supporting local and cloud AI providers without changing the internal architecture.


# Context Documents

- path: README.md
  priority: critical

- path: AI_GENERATION_STANDARD.md
  priority: critical

- path: docs/architecture/JARVIS_ROADMAP.md
  priority: critical

- path: docs/architecture/HOW_TO_START.md
  priority: high

- path: docs/architecture/JARVIS_ARCHITECTURE_VISION.md
  priority: high

- path: docs/architecture/NON_GOALS.md
  priority: high

- path: CHANGELOG.md
  priority: medium

- path: docs/RELEASE_NOTES.md
  priority: medium

- path: docs/BACKLOG.md
  priority: medium

# Context Sections

- Project Identity
- Project Documents
- Working Directory
- Environment
- Conversation
- Active Process

# Configuration Files

- path: config/config.yaml
- path: config/logging.yaml
- path: config/commands.yaml

# Coding Standards

- path: AI_GENERATION_STANDARD.md


# Architecture Documents

- path: docs/architecture/PROJECT_OVERVIEW.md

- path: docs/architecture/JARVIS_ARCHITECTURE_VISION.md

- path: docs/architecture/ARCHITECTURE_DECISIONS.md

- path: docs/architecture/NON_GOALS.md


# Roadmaps

- path: docs/architecture/JARVIS_ROADMAP.md


# Active Processes

The currently active Engineering Package is tracked by the engineering workflow and project documentation.

This section is intentionally independent of any specific EP to avoid modifying the manifest during normal project development.


# Knowledge Files

- path: knowledge/


# Ignore Directories

- __pycache__
- node_modules
- .venv

# Ignore Paths

- .git/
- .venv/
- __pycache__/
- node_modules/
- dist/
- build/

# Ignore Files

- *.png
- *.jpg
- *.jpeg
- *.gif
- *.pdf
- *.zip
- *.7z
- *.exe
- *.dll
- *.bin