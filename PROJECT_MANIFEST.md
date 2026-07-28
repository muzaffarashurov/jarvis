# PROJECT_MANIFEST.md

This file is the single source of truth for `ContextLoader`
(`src/core/ai/context_loader.py`, EP-018.4). It is the only
project-specific filename `ContextLoader` ever hardcodes: everything
else it knows about this project comes from the sections below.

Each `#` heading below is a fixed, project-independent category that
`ContextLoader` understands. Scalar fields hold one line of text;
document categories hold a list of file paths (relative to this
file's directory) or directory references (a path ending in `/`,
whose files are all included, minus `# Ignore Directories`).

To adapt this file to a different project (Language Learning, CRM,
ERP, Invoice Automation, a Spring Boot service, a React app, ...),
only the content under each heading changes. `ContextLoader`'s code
never changes.


# Project Name

Jarvis

# Current Version:

0.1.0-alpha

# Repository Root


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

- config/config.yaml
- config/logging.yaml
- config/commands.yaml


# Coding Standards

- AI_GENERATION_STANDARD.md


# Architecture Documents

- docs/architecture/JARVIS_ARCHITECTURE_VISION.md


# Roadmaps

- docs/architecture/JARVIS_ROADMAP.md


# Active Processes

- AI Core build-out, currently in the Context Engine (EP-018 series)


# Knowledge Files

- knowledge/


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