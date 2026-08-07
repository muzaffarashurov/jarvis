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

Architecture Audit is always performed as STEP 4.

STEP 4 is READ-ONLY.

The AI must NOT modify source code.

The AI must NOT modify tests.

The AI must NOT refactor anything.

The audit reviews ONLY the current EP.

The audit must check:

- architecture layering
- SOLID
- dependency direction
- Bootstrap wiring
- service wiring
- module wiring
- duplicate responsibilities
- duplicate DTOs
- duplicate CLI logic
- hidden coupling
- circular dependencies
- backward compatibility
- public API consistency
- roadmap compliance
- unnecessary abstractions
- dead code
- maintainability risks

The audit must classify findings as:

- Critical
- High
- Medium
- Low

Only Critical issues may interrupt roadmap implementation.

The audit must NEVER automatically fix issues.

STEP 4 is strictly READ-ONLY.

If issues are discovered:

- Critical:
  Stop and ask the user whether to perform a dedicated Bug Fix step.

- High:
  Report them and wait for user approval.

- Medium:
  Record them in ARCHITECTURE_DEBT.md.

- Low:
  Record them in ARCHITECTURE_DEBT.md.

Never modify code during STEP 4.

Never regenerate the implementation during STEP 4.

Never repeat the audit automatically.

Always wait for user approval before performing corrective work.

Medium and Low findings must NOT trigger immediate refactoring.

---

# Engineering Review

After the STEP 4 audit is completed:

Perform a second READ-ONLY engineering review.

Do NOT modify any source code.

Do NOT modify tests.

Do NOT refactor.

Review:

- overengineering
- dead code
- unused methods
- unused interfaces
- unused enum values
- hidden assumptions
- maintainability
- complexity
- TODOs
- technical debt

Return findings only.

If issues are found:

- classify them by severity
- Critical issues must be fixed before the EP can be committed
- High issues should be discussed with the user
- Medium and Low issues must be recorded in
  docs/architecture/ARCHITECTURE_DEBT.md

Do NOT perform fixes automatically.

Never repeat the audit automatically.

Always wait for user approval before any corrective work.

---

# Final Validation

Default validation:

test EPxxx

Run test all only if explicitly requested by the user.

Regression testing is optional unless the current EP modifies shared infrastructure.

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

# Prompt Strategy

Large Engineering Phases must be divided into independent prompts.

Never combine architecture, implementation, documentation and audit into one request.

Always use the following sequence:

STEP 1
Architecture Design

↓

User Approval

↓

STEP 2
Implementation

↓

User Approval

↓

STEP 3
Documentation

↓

User Approval

↓

STEP 4
Architecture Audit

Each step must be completely independent.

Never continue automatically.

Always wait for the user's approval.

---

# Token Optimization

Always minimize token usage.

Never repeat information already approved.

Do not regenerate architecture after STEP 1.

Do not regenerate implementation during STEP 3.

Do not regenerate documentation during STEP 4.

When possible:

- reference previous approved decisions
- modify only affected files
- avoid repeating unchanged explanations
- avoid repeating full file lists
- avoid repeating project description

Generate only what belongs to the current step.

---

# Architecture Debt Workflow

After every STEP 4 audit:

If Medium or Low issues are discovered:

- update docs/architecture/ARCHITECTURE_DEBT.md
- assign the next available ID
- never renumber existing IDs
- never delete existing entries

If no Medium or Low issues exist:

leave ARCHITECTURE_DEBT.md unchanged.

Critical issues are never added to Architecture Debt.

They must be fixed before the EP can be committed.

After completing STEP 4:

create:

docs/architecture/audits/EPxxx_AUDIT.md

containing the complete audit report.

Package both files into a ZIP archive:

- docs/architecture/ARCHITECTURE_DEBT.md
- docs/architecture/audits/EPxxx_AUDIT.md

Return the archive for download.

---

# Prompt Scope

Each prompt must have exactly one purpose.

Allowed prompt types:

- Architecture Design
- Implementation
- Documentation
- Architecture Audit
- Bug Fix
- Refactoring
- Regression Investigation

Never combine multiple prompt types in one request.

If the requested work belongs to another prompt type:

Stop.

Ask for confirmation.

Wait for the next prompt.

---

At the end of STEP 2:

- run only test EPxxx
- do not run test all unless explicitly requested
- package the updated project into a ZIP archive
- return the archive for download

---

At the end of STEP 3:

package the updated documentation into a ZIP archive.

Return the archive for download.

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

---

# Completion Checklist

Before declaring any EP complete, verify:

□ All new source files are included.
□ All required imports are added.
□ New EP registered inside test_module.py.
□ Bootstrap wiring completed.
□ Config updated if required.
□ EP tests pass.
□ Documentation updated (STEP 3 only).
□ Architecture audit completed (STEP 4 only).
□ Architecture Debt updated if required.
□ Audit report saved.
□ ZIP archive generated.
□ Commit message prepared.
□ Git tag prepared.

---