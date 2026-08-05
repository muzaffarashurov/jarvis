# AI Development Playbook

**Project:** Jarvis
**Purpose:** This document defines the mandatory engineering workflow for all AI assistants contributing to the Jarvis project (Claude, ChatGPT, Gemini, Qwen, DeepSeek, etc.).

---

# Core Principles

The primary objective is **maintaining a clean, scalable, production-quality architecture** while implementing roadmap features one EP at a time.

Every implementation must be:

* deterministic
* backward compatible
* modular
* maintainable
* production-ready

The AI must never sacrifice architecture quality for speed.

---

# General Rules

Always implement **only the current EP**.

Do not modify unrelated code.

Do not redesign previous EPs.

Do not optimize previous EPs unless explicitly requested.

Do not refactor unrelated modules.

Do not introduce new architectural layers without necessity.

Do not change project conventions.

Do not break backward compatibility.

---

# Development Workflow

Every EP must follow exactly this sequence.

## Phase 0 — Audit

Before writing any code:

* inspect the current project structure
* search for duplicate implementations
* verify whether the requested feature already exists
* identify possible architectural conflicts

Do not modify files during this phase.

---

## Phase 1 — Design

Understand:

* responsibilities
* dependencies
* integration points
* required services
* required modules
* configuration changes

The implementation must fit naturally into the existing architecture.

---

## Phase 2 — Implementation

Generate production-ready code.

Follow SOLID principles.

Keep responsibilities separated.

Avoid duplicated logic.

Avoid feature creep.

Implement only what belongs to the current EP.

---

## Phase 3 — Testing

Generate a dedicated test suite for the current EP.

Register the suite inside TestRegistry.

Run only:

test EPxxx

Never run:

test all

until explicitly requested.

Fix every failing assertion.

Repeat until:

Passed > 0

Failed = 0

Skipped = 0 (unless intentionally skipped)

---

## Phase 4 — Documentation

Update only when required:

* CHANGELOG
* RELEASE_NOTES
* ROADMAP
* BACKLOG

Do not modify unrelated documentation.

---

# Architecture Rules

Always follow these principles.

## Single Responsibility

Each class has one responsibility.

---

## Open/Closed Principle

Prefer extension over modification.

---

## Dependency Inversion

High-level components depend on abstractions.

---

## Dependency Direction

Dependencies must always point toward lower architectural layers.

Never create reverse dependencies.

---

## No Circular Dependencies

Circular imports are forbidden.

---

## No Duplicate Responsibilities

Never implement the same feature twice.

Search the project before creating new classes.

---

## No Hidden Coupling

Do not access private attributes of other EPs.

Use only public APIs.

---

## Backward Compatibility

Never break previous EPs.

Never rename public methods without necessity.

Never remove public interfaces.

---

# Bootstrap Rules

Do not modify Bootstrap unless the current EP explicitly requires it.

Never change lifecycle behavior without justification.

Do not modify:

* initialization order
* service registration
* CLI startup

unless required.

---

# Test Rules

Never optimize the test framework unless explicitly requested.

Never modify previous EP tests unless they are genuinely broken by the current EP.

Never remove assertions.

Never weaken assertions.

---

# Performance Rules

Performance optimization is **not** part of normal EP implementation.

Only optimize when explicitly requested.

Never mix feature implementation and optimization work.

---

# Code Quality Rules

Avoid:

* dead code
* unused interfaces
* unused methods
* duplicated enums
* duplicated DTOs
* speculative abstractions

Keep implementations simple.

---

# CLI Rules

Avoid duplicated CLI logic.

Reuse existing command patterns.

Maintain consistent output formatting.

---

# Architecture Audit

After implementation, perform a strict architecture audit.

Do not modify files during the first audit.

Review only the current EP.

Check:

* duplicate responsibilities
* duplicated business logic
* duplicated CLI logic
* SOLID violations
* dependency direction
* circular dependencies
* Bootstrap wiring
* service wiring
* unnecessary abstractions
* hidden coupling
* backward compatibility
* public API consistency
* roadmap compliance
* naming consistency
* misplaced code
* accidental feature creep

If issues exist:

* list every issue
* explain why
* fix them
* repeat the audit

Continue until:

No architecture issues remain.

---

# Engineering Review

After the architecture audit passes:

Perform a second engineering review.

Check:

* overengineering
* dead code
* unused methods
* unused interfaces
* unused enum values
* hidden assumptions
* maintainability
* complexity
* TODOs
* technical debt

Fix everything.

Repeat until:

No engineering concerns remain.

---

# Final Validation

Run only:

test EPxxx

Verify:

Passed > 0

Failed = 0

Do not run test all unless explicitly requested.

---

# Commit Rules

Generate a commit message using Conventional Commits.

Preferred format:

feat(EPxxx): short description

Example:

feat(EP029): implement deterministic Planning Engine

---

# Final Report

Every completed EP must produce a report containing:

1. Phase 0 audit
2. Design summary
3. New files
4. Modified files
5. Architecture notes
6. Validation results
7. Architecture audit
8. Engineering review
9. Known limitations

The report must finish with:

EP-XXX is ready to commit.

---

# AI Must Never

The AI must never:

* modify unrelated code
* redesign completed EPs
* optimize unrelated systems
* weaken tests
* silently remove functionality
* introduce duplicate implementations
* access private APIs from other modules
* ignore architecture violations
* ignore engineering issues
* skip validation
* skip the architecture audit
* skip the engineering review

---

# Goal

The long-term goal of this playbook is to ensure that every EP is implemented with the same engineering standards, regardless of which AI model performs the work.

Every completed EP should improve the project without increasing technical debt.

Before finishing ANY EP, verify:

□ All new source files are included.
□ All new test files are included.
□ New EP is imported into test_module.py.
□ Bootstrap wiring is complete.
□ Config.yaml updated if required.
□ Documentation updated if requested.
□ ZIP archive generated successfully.
□ EP tests pass.
□ Regression tests pass.
□ Commit message prepared.