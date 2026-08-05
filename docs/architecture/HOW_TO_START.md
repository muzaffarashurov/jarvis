# HOW_TO_START.md

# How to Start Working on a Project

Version: 2.0

Status: Active

---

# Purpose

This document explains how an AI should begin working on any project.

Jarvis must understand the project before generating or modifying code.

---

# Step 1 — Discover the Project

Read:

PROJECT_MANIFEST.md

Purpose:

- Identify the project.
- Locate the project root.
- Discover project documentation.
- Discover architecture documents.
- Discover engineering documents.
- Discover coding standards.
- Discover startup documents.

The manifest is the single entry point to the project.

---

# Step 2 — Understand the Architecture

Read every architecture document listed in the manifest.

Typical examples:

- JARVIS_ARCHITECTURE_VISION.md
- ARCHITECTURE_DECISIONS.md
- NON_GOALS.md
- PROJECT_OVERVIEW.md

Purpose:

- Understand the long-term vision.
- Understand architectural principles.
- Understand design decisions.

Never implement code before understanding the architecture.

---

# Step 3 — Read Engineering Documentation

Read engineering documents listed in the manifest.

Typical examples:

- ENGINEERING_GUIDE.md
- EP specifications

Purpose:

- Understand the current Engineering Package.
- Understand completed work.
- Understand future work.

---

# Step 4 — Read Coding Standards

Read:

AI_GENERATION_STANDARD.md

Purpose:

- Understand coding rules.
- Follow project conventions.
- Respect architectural constraints.

---

# Step 5 — Build the Project Context

The Universal Context Engine should:

- locate the project
- read PROJECT_MANIFEST.md
- load required documents
- respect prompt budgets
- build the project context

Future components may extend the context using:

- Project Index
- Retrieval Engine
- Embedding Engine
- RAG Engine

---

# Recommended Reading Order

PROJECT_MANIFEST.md

↓

Architecture Documents

↓

Engineering Documents

↓

Coding Standards

↓

Current Engineering Package

↓

Source Code

---

# Golden Rule

Architecture always has priority over implementation.

If implementation conflicts with the architecture, follow the architecture.

Never redesign completed modules without an explicit Engineering Package.

---

## Engineering

Development process is described in:

docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md

---

End of document.