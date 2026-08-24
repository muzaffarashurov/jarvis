# Jarvis Development Roadmap

Version: 2.0

Status: Active Development

---

# Vision

Jarvis is not a chatbot.

Jarvis is not a single Large Language Model.

Jarvis is an AI Operating System.

Its purpose is to orchestrate AI providers, project knowledge, memory, workflows, tools and autonomous agents through a unified architecture.

Every Engineering Package (EP) contributes one reusable architectural building block.

---

# Engineering Principles

Every EP must:

- extend the existing architecture
- preserve backward compatibility
- follow PROJECT_MANIFEST.md
- follow AI_GENERATION_STANDARD.md
- remain provider independent
- avoid duplicated functionality
- reuse existing infrastructure
- include automated tests
- deliver production-quality code

Large EPs may be implemented incrementally using sub-packages:

- EP-018.1
- EP-018.2
- EP-018.3
- ...

Sub-packages never replace the main EP number.

---

# Current Progress

## Completed

EP-001 Core Foundation

EP-002 Interactive Shell

EP-003 Process Manager

EP-004 Quality & Testing Framework

EP-005 Invoice Automation

EP-006 Fast Response Board

EP-007 Core Improvements

EP-008 Process Aliases

EP-009 Process Catalog

EP-010 Configuration Improvements

EP-011 Logging Improvements

EP-012 Core Refactoring

EP-013 AI Infrastructure Preparation

EP-014 AI Provider Manager

EP-015 AI Provider Integration

EP-016 Conversation Engine

EP-017 Prompt Engine

EP-018 Universal Context Engine

Completed sub-packages:

- EP-018.1 Context Engine Foundation
- EP-018.2 PROJECT_MANIFEST Integration
- EP-018.3 Repository Detection
- EP-018.4 Document Budget
- EP-018.5 Unified Prompt Budget
- EP-018.6 Conversation Budget
- EP-019 Project Index Engine
- EP-020 Retrieval Engine
- EP-021 Embedding Engine
- EP-022 RAG Engine
- EP-023 Memory Manager
- EP-024 Knowledge Base
- EP-025 Long-Term Memory
- EP-026 Semantic Search
- EP-027 Context Compression
- EP-028 Agent Framework
- EP-029 Planning Engine
- EP-030 Execution Engine
- EP-031 Tool Engine
- EP-032 Multi-Agent Collaboration
- EP-033 Workflow Engine
- EP-034 Scheduler
- EP-035 Automation Engine
- EP-036 Background Workers
- EP-037 Event Bus
- EP-038 Git Integration
- EP-039 GitHub Integration
- EP-040 Telegram Integration
- EP-041 Discord Integration
- EP-042 Email Integration

---

## Current

EP-048 Wake Word — **COMPLETE** (STEP 1 Design & Research, STEP 2
Implementation & Verification, STEP 3 Documentation & Audit Closure,
and a post-STEP-3 real-Windows-hardware bug fix all complete -- see
docs/architecture/designs/EP048_DESIGN.md (including its Section 9a
owner-decision record, Section 17 as-built summary, and Section 17.7
post-STEP-3 bug-fix account) and
docs/architecture/audits/EP048_AUDIT.md (Section 17, "Post-Audit Bug
Fix / Final Verification"). Verdict: **PASS** (updated from STEP 3's
original "PASS WITH DOCUMENTED LIMITATIONS" once real Windows
hardware verification closed the one limitation that was actually
EP-048's own -- an `openwakeword==0.6.0` Linux packaging quirk in the
automated-testing environment remains disclosed, unrelated to the
Windows target). Built as offline, `openWakeWord`-based
wake-phrase detection (`src/skills/voice/wake_word.py`) fed by a new,
separate `StreamingAudioCapture` component
(`src/skills/voice/streaming_audio_capture.py`, kept apart from
EP-046's existing fixed-duration `AudioCapture`, which was not
modified), composed into the *existing* `voice` `CommandModule`
(`src/skills/voice/skill.py`) as additive `wake listen`/`wake status`
actions -- no second namespace, no new dispatch mechanism, no change
to `src/core/command_router.py`, `src/core/api/`, Telegram,
`desktop/`, or `web/`. `voice wake listen` only ever reports a
detection: it never dispatches through `CommandRouter`, never starts
an STT (`voice listen`) cycle, never speaks via TTS, and never runs
as a background listener or daemon -- confirmed by dedicated
call-counting tests, not only by design. Supports English ("Hey
Jarvis") only; Russian and Uzbek wake-word detection are explicitly
out of scope (no offline wake-word model evaluated has first-class
support for either) and receive no special-case handling anywhere in
code. Model files are never downloaded automatically -- manual
placement only, mirroring EP-046's own Vosk precedent.
`voice.wake.enabled` defaults to `false`. This EP also **fully**
closed EP-047's own disclosed registration-gating limitation: STT,
TTS, and Wake Word can now each be enabled independently, with the
`voice` namespace registering whenever any one of the three is
enabled (previously, TTS-only operation was not reachable -- see the
audit document's Known Limitations for what remains disclosed).
Real microphone/real-loaded-model wake-word detection has since been
verified by a human on the actual target Windows workstation --
`voice wake status` reported the model available and `voice wake
listen` correctly detected "hey_jarvis" (scores 0.80 and 0.64 across
two runs). That same verification pass also surfaced and led to the
correction of a real model-filename-resolution defect (the
implementation originally looked only for a bare `hey_jarvis.onnx`
file; openWakeWord's own official models ship as
`hey_jarvis_v0.1.onnx` -- now resolved deterministically without any
automatic download) -- see the audit document's Section 17 for full
detail.) EP-047
Text-to-Speech remains **COMPLETE** (STEP 1-3, unchanged by EP-048 --
`src/skills/voice/text_to_speech.py` confirmed byte-identical to its
EP-047-shipped state; its own disclosed TTS-only registration
limitation is now resolved by EP-048's D6 fix, recorded in both EPs'
audit documents -- see docs/architecture/designs/EP047_DESIGN.md and
docs/architecture/audits/EP047_AUDIT.md.) EP-046 Speech-to-Text
remains **COMPLETE** (STEP 1-3, unchanged by EP-047/EP-048 --
`src/skills/voice/speech_to_text.py` and
`src/skills/voice/audio_capture.py` confirmed byte-identical to their
EP-046-shipped state -- see
docs/architecture/designs/EP046_DESIGN.md and
docs/architecture/audits/EP046_AUDIT.md.) EP-045 Web Dashboard
remains **COMPLETE** (STEP 1-3, unchanged by EP-046/EP-047/EP-048,
`web/` confirmed absent from the EP-048 changeset -- see
docs/architecture/designs/EP045_DESIGN.md and
docs/architecture/audits/EP045_AUDIT.md.) EP-044 Desktop UI remains
**COMPLETE** (STEP 1-3, unchanged by EP-045/EP-046/EP-047/EP-048,
`desktop/` confirmed absent from the EP-048 changeset -- see
docs/architecture/designs/EP044_DESIGN.md and
docs/architecture/audits/EP044_AUDIT.md.) EP-043 REST API remains
**COMPLETE** (STEP 1-4, unchanged by EP-044/EP-045/EP-046/EP-047/
EP-048 -- see docs/architecture/designs/EP043_DESIGN.md and
docs/RELEASE_NOTES.md.)

**Next Engineering Package: EP-049 Voice Assistant — NOT STARTED.**
No EP-049 design, research, or implementation work has begun.

---

# Roadmap

## Phase 1 — Core Platform

EP-001 Core Foundation

EP-002 Interactive Shell

EP-003 Process Manager

EP-004 Testing Framework

EP-005 Invoice Automation

EP-006 Fast Response Board

EP-007 Core Improvements

EP-008 Process Aliases

EP-009 Process Catalog

EP-010 Configuration

EP-011 Logging

EP-012 Refactoring

EP-013 AI Infrastructure

---

## Phase 2 — AI Core

✓ EP-014 AI Provider Manager

✓ EP-015 AI Provider Integration

✓ EP-016 Conversation Engine

✓ EP-017 Prompt Engine

✓ EP-018 Universal Context Engine

✓ EP-019 Project Index Engine

✓ EP-020 Retrieval Engine

✓ EP-021 Embedding Engine

✓ EP-022 RAG Engine

---

## Phase 3 — Memory

✓ EP-023 Memory Manager

✓ EP-024 Knowledge Base

✓ EP-025 Long-Term Memory

✓ EP-026 Semantic Search

✓ EP-027 Context Compression

---

## Phase 4 — Agent Framework

✓ EP-028 Agent Framework

✓ EP-029 Planning Engine

✓ EP-030 Execution Engine

✓ EP-031 Tool Engine

✓ EP-032 Multi-Agent Collaboration

---

## Phase 5 — Workflow Automation

✓ EP-033 Workflow Engine

✓ EP-034 Scheduler

✓ EP-035 Automation Engine

✓ EP-036 Background Workers

✓ EP-037 Event Bus

---

## Phase 6 — Integrations

✓ EP-038 Git Integration

✓ EP-039 GitHub Integration

✓ EP-040 Telegram Integration

✓ EP-041 Discord Integration

✓ EP-042 Email Integration

✓ EP-043 REST API

✓ EP-044 Desktop UI

✓ EP-045 Web Dashboard

---

## Phase 7 — Voice

✓ EP-046 Speech-to-Text

✓ EP-047 Text-to-Speech

✓ EP-048 Wake Word

EP-049 Voice Assistant

---

## Phase 8 — Computer Automation

EP-050 Computer Use

EP-051 Browser Automation

EP-052 File Automation

EP-053 Vision Integration

---

## Phase 9 — Intelligence

EP-054 Self Reflection

EP-055 Prompt Optimizer

EP-056 Capability Learning

EP-057 Memory Optimization

EP-058 Autonomous Planning

---

## Phase 10 — Jarvis Operating System

EP-059 Distributed Runtime

EP-060 Jarvis Operating System

---

# Architecture Evolution

Core Platform

↓

AI Provider Layer

↓

Conversation Engine

↓

Prompt Engine

↓

Universal Context Engine

↓

Project Index

↓

Retrieval

↓

Embeddings

↓

RAG

↓

Memory

↓

Agent Framework

↓

Tool Engine

↓

Workflow Engine

↓

Automation

↓

Voice

↓

User Interfaces

↓

Jarvis Operating System

---

# Engineering Package Policy

Large Engineering Packages should be implemented in multiple incremental iterations.

Example:

EP-018 Universal Context Engine

- EP-018.1 Foundation
- EP-018.2 Manifest Integration
- EP-018.3 Repository Detection
- EP-018.4 Document Budget
- EP-018.5 Unified Prompt Budget
- EP-018.6 Conversation Budget

EP-019 Project Index Engine

- EP-019.1 Repository Scanner
- EP-019.2 File Index
- EP-019.3 Chunk Generator
- EP-019.4 Metadata Builder
- EP-019.5 Incremental Index
- EP-019.6 Testing
- Status: Completed

This approach allows large architectural modules to evolve without changing the long-term roadmap.

---

# Current Objective

Jarvis evolves incrementally through Engineering Packages.

Only one major Engineering Package should be actively implemented at a time.

Each completed Engineering Package becomes a permanent architectural building block for future development.

The implementation order is defined by this roadmap.

The currently active Engineering Package is tracked separately by the engineering process and project documentation.

# Long-Term Goal

Build a provider-independent AI Operating System capable of:

- understanding software projects
- maintaining engineering knowledge
- retrieving relevant information
- planning complex tasks
- executing tools
- coordinating multiple AI providers
- orchestrating autonomous agents
- automating engineering workflows

The ultimate goal is to create a modular, reusable and extensible AI Operating System that remains independent of any single AI provider or technology.

# Notes

This roadmap defines the official long-term engineering direction of Jarvis.

The numbering of Engineering Packages is stable.

New functionality should normally be implemented as sub-packages (EP-XXX.Y) rather than renumbering the roadmap.

Completed EPs should not be redesigned unless an explicit architectural decision requires it.

End of document.