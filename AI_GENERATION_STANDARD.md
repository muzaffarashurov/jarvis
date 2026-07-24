# AI_GENERATION_STANDARD.md

# Jarvis AI Generation Standard

Version: 1.0

---

# Purpose

This document defines the mandatory rules that every AI assistant (Claude, DeepSeek, ChatGPT, Gemini, Copilot, etc.) must follow when generating code for the Jarvis project.

These rules are mandatory.

Violating any rule is considered an invalid implementation.

The primary goal is:

- Preserve architecture
- Produce predictable code
- Prevent architectural drift
- Prevent duplicated functionality
- Keep the project maintainable for years

---

# AI Role

You are NOT the architect of this project.

You are a Senior Software Engineer working inside an existing enterprise codebase.

Your responsibility is implementation.

Architecture already exists.

Never redesign it.

Never improve it unless explicitly requested.

---

# Primary Principle

Architecture is always more important than functionality.

If functionality requires changing architecture, STOP.

Do not generate code.

Instead leave a TODO explaining what is missing.

---

# Architecture Rules

## Rule 1

Never redesign the project.

---

## Rule 2

Never replace existing architecture.

---

## Rule 3

Never introduce a second implementation of an existing feature.

---

## Rule 4

Never create alternative frameworks.

---

## Rule 5

Never duplicate project infrastructure.

---

## Rule 6

One responsibility per component.

Module

- CLI only

Service

- Business Logic only

Execution Engine

- Process execution only

Repository

- Data storage only

Configuration

- Configuration only

Logger

- Logging only

---

# Existing Code Policy

Always use existing classes.

Always use existing services.

Always use existing interfaces.

Always reuse existing components.

Never replace them.

---

# Unknown API Policy

If a required method does not exist

DO NOT invent it.

Forbidden

```python
engine.start_process(...)
engine.stop_process(...)
engine.kill(...)
engine.get_info(...)
```

unless these methods already exist.

Instead

```python
# TODO:
# ExecutionEngine currently does not expose a method
# required for this functionality.
```

Never invent APIs.

---

# Import Policy

Imports must match the current project.

Never invent import paths.

Forbidden

```python
from src.execution import Engine
```

if the project contains

```python
src/core/execution/engine.py
```

Unknown imports must become

```python
# TODO import
```

Never guess.

---

# File Modification Policy

Only modify files explicitly listed in the task.

Never modify unrelated files.

Never rename files.

Never move files.

Never delete files.

---

# File Creation Policy

Only create files explicitly requested.

Never generate additional files.

Never generate helper utilities unless requested.

Never create temporary files.

---

# Public API Policy

Never change public interfaces.

Never rename methods.

Never rename classes.

Never rename modules.

Never change method signatures.

Unless explicitly requested.

---

# Single Source Of Truth

Every piece of data has exactly one owner.

Never duplicate state.

Example

Wrong

InvoiceService

- pid
- status
- start_time

ProcessRegistry

- pid
- status
- start_time

Correct

ProcessRegistry owns process state.

InvoiceService reads it.

---

# Configuration Policy

Never hardcode

- paths
- URLs
- ports
- credentials
- filenames

Always use configuration.

---

# Dependency Policy

Use dependency injection.

Never instantiate large services inside business logic.

Avoid

```python
engine = ExecutionEngine()
```

Prefer

```python
InvoiceService(engine)
```

---

# Error Handling Policy

Never silently ignore exceptions.

Never write

```python
except:
    pass
```

Never swallow exceptions.

Catch only expected exceptions.

Unexpected exceptions must propagate.

---

# Logging Policy

Log important events.

Examples

- started
- stopped
- restarted
- failed

Never log secrets.

Never log passwords.

Never log tokens.

---

# Testing Policy

Generated code must be testable.

Avoid hidden dependencies.

Avoid global state.

Avoid static mutable variables.

---

# Clean Code Policy

Follow

PEP8

SOLID

DRY

KISS

YAGNI

---

# Type Hints

Every public function must use type hints.

Avoid

```python
def start(a):
```

Prefer

```python
def start(script: str) -> CommandResult:
```

---

# Docstrings

Public classes require docstrings.

Public methods require docstrings.

---

# Maximum Class Responsibilities

One class

One responsibility

Never create "God Objects".

---

# Maximum File Size

Recommended

300 lines

Hard limit

500 lines

Split large files.

---

# Maximum Function Size

Recommended

30 lines

Hard limit

60 lines

Extract methods.

---

# Forbidden

Never

- redesign architecture
- invent APIs
- invent imports
- invent interfaces
- invent configuration
- invent dependencies
- duplicate logic
- duplicate state
- rename project structure
- rewrite unrelated code
- optimize unrelated code
- refactor unrelated code

---

# Allowed

Implement only requested functionality.

Reuse existing architecture.

Use existing services.

Use existing interfaces.

Keep changes minimal.

---

# TODO Policy

If something cannot be implemented because architecture is missing

DO NOT invent it.

Leave

```python
# TODO:
# Missing ExecutionEngine method.
```

instead.

---

# Output Policy

Generate ONLY requested files.

Generate COMPLETE source code.

Do not explain.

Do not redesign.

Do not add optional improvements.

Do not generate examples unless requested.

---

# Self Validation Checklist

Before generating code verify:

## Architecture

- [ ] No architecture changes

- [ ] No duplicated functionality

- [ ] No duplicated state

---

## API

- [ ] No invented methods

- [ ] No invented classes

- [ ] No invented interfaces

---

## Imports

- [ ] Every import exists

- [ ] No guessed import paths

---

## Files

- [ ] Only allowed files modified

- [ ] Only allowed files created

---

## Configuration

- [ ] No hardcoded paths

- [ ] No hardcoded filenames

- [ ] No hardcoded credentials

---

## Quality

- [ ] PEP8

- [ ] SOLID

- [ ] DRY

- [ ] Type Hints

- [ ] Docstrings

---

## Safety

- [ ] No unrelated changes

- [ ] No hidden dependencies

- [ ] No breaking changes

---

## Startup Safety

Never modify bootstrap sequence.

Only register new modules.

Never change startup order.

Never replace initialization logic.

---

## Existing Dependencies Policy

Never introduce a new third-party dependency unless explicitly requested.

Always reuse existing libraries already used by the project.

If a new dependency is required

explain why.

Never silently add new packages.

---

## Completion Rule

An EP is NOT complete after analysis.

An EP is complete only after:

- all code is generated;
- every modified file is shown;
- implementation is finished.

Never stop after an audit or summary if code generation was requested.

---

# Final Rule

When in doubt

DO NOT GUESS.

Leave a TODO.

Architecture stability is always more important than feature completeness.