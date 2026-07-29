# Project Overview

Version: 1.0

Status: Active Development

---

# What is Jarvis?

Jarvis is an AI Operating System.

It is not a chatbot.

It is not a single Large Language Model (LLM).

Jarvis is a modular platform that orchestrates multiple AI providers, project knowledge, workflows, tools, memory and autonomous agents through a unified architecture.

The system is designed to become a reusable engineering platform capable of understanding software projects, assisting developers, automating engineering workflows and executing complex tasks.

---

# Project Goals

The primary goals of Jarvis are:

- provide a unified interface for multiple AI providers
- understand software projects automatically
- maintain project knowledge
- retrieve relevant information efficiently
- execute tools and workflows
- assist software development
- automate repetitive engineering tasks
- remain provider independent
- remain reusable across different projects

---

# Core Principles

Jarvis follows several fundamental principles.

## Provider Independence

Business logic must never depend on a specific AI provider.

Supported providers may include:

- Gemini
- Claude
- Ollama
- OpenAI
- LM Studio

All providers implement a common interface.

---

## Modularity

Every component has exactly one responsibility.

Each Engineering Package (EP) introduces one reusable module.

Components communicate through stable interfaces.

---

## Reusability

Jarvis itself must never contain assumptions about a specific project.

Every software project is identified through its own PROJECT_MANIFEST.md.

The same AI engine should work for any future project without code changes.

---

## Documentation First

Architecture is defined by documentation.

Implementation follows documentation.

The primary architectural documents are:

- PROJECT_MANIFEST.md
- AI_GENERATION_STANDARD.md
- JARVIS_ROADMAP.md
- ARCHITECTURE_DECISIONS.md
- ENGINEERING_GUIDE.md

---

# High-Level Architecture

Jarvis is composed of several major subsystems.

Interactive Shell

↓

Process Manager

↓

Testing Framework

↓

AI Provider Framework

↓

Prompt Engine

↓

Conversation Engine

↓

Universal Context Engine

↓

Project Index

↓

Retrieval

↓

Embedding Engine

↓

RAG Engine

↓

Memory Engine

↓

Tool Engine

↓

Agent Engine

↓

Workflow Engine

↓

Plugin System

↓

Voice Engine

↓

User Interface

↓

Jarvis Assistant

---

# Engineering Packages

Jarvis is developed incrementally through Engineering Packages (EP).

Each Engineering Package introduces one reusable architectural capability while preserving compatibility with the existing system.

Engineering Packages define:

- architectural objectives
- implementation scope
- completion criteria
- testing requirements
- documentation updates

Detailed Engineering Package specifications are documented in:

- ENGINEERING_GUIDE.md
- docs/engineering/EP-XXX.md

The implementation sequence of all Engineering Packages is defined in:

- JARVIS_ROADMAP.md

# Project Knowledge

Every project using Jarvis contains a PROJECT_MANIFEST.md.

The manifest defines:

- project identity
- architecture documents
- context documents
- indexing rules
- engineering rules

Jarvis never guesses project information.

Everything must originate from the manifest and referenced documents.

---

# Architecture Evolution

Jarvis evolves incrementally through Engineering Packages.

The architecture continuously expands by introducing new reusable capabilities while preserving backward compatibility.

Major architectural layers include:

- AI Provider Framework
- Prompt Engine
- Conversation Engine
- Universal Context Engine
- Project Index
- Retrieval Engine
- Embedding Engine
- RAG Engine
- Memory Engine
- Tool Engine
- Agent Framework
- Workflow Engine
- Plugin System
- Voice Engine
- User Interfaces

The current implementation status and future development roadmap are maintained separately in:

- JARVIS_ROADMAP.md
- CHANGELOG.md
- RELEASE_NOTES.md

# Long-Term Vision

Jarvis aims to become a complete AI Operating System capable of:

- understanding any software project
- maintaining engineering knowledge
- retrieving relevant information
- planning tasks
- executing tools
- coordinating multiple AI providers
- orchestrating autonomous agents
- automating software engineering workflows

Ultimately, Jarvis should function as an intelligent engineering assistant capable of supporting the complete software development lifecycle.

---

# Related Documents

Project identity

- PROJECT_MANIFEST.md

Coding standards

- AI_GENERATION_STANDARD.md

Architecture decisions

- ARCHITECTURE_DECISIONS.md

Engineering packages

- ENGINEERING_GUIDE.md

Development roadmap

- JARVIS_ROADMAP.md

Architecture vision

- JARVIS_ARCHITECTURE_VISION.md

Project limitations

- NON_GOALS.md

Getting started

- HOW_TO_START.md

---

End of document.