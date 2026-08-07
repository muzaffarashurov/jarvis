# Architecture Debt

Version: 1.0

This document tracks architectural debt discovered during STEP 4 architecture audits.

The purpose of this document is to prevent non-critical issues from interrupting roadmap development.

Only issues confirmed by architecture audits may be recorded here.

---

# Rules

Critical issues

- Must be fixed immediately.
- Roadmap development stops until resolved.

High issues

- Fix before the next major milestone.

Medium issues

- Postpone.
- Schedule for Architecture Cleanup milestone.

Low issues

- Postpone.
- Fix only when touching related code.

Never fix Architecture Debt during a normal Engineering Phase (EP).

Architecture Debt is addressed only during a dedicated cleanup milestone.

---

# Status

| ID | Severity | Status |
|----|----------|--------|
| - | - | - |

Status values:

- Open
- Planned
- In Progress
- Fixed
- Rejected

---

# Debt Items

---

## AD-001

**Severity**

Medium

**Discovered in**

EP034 Architecture Audit

**Files**

src/services/workflow_scheduler_service.py

**Description**

Malformed `workflow_scheduler.tick_interval` may terminate the background thread instead of degrading gracefully.

**Why it matters**

A configuration error can silently disable automatic workflow scheduling.

**Recommended solution**

Validate `tick_interval` during service initialization or move parsing inside the protected execution loop.

**Planned milestone**

Architecture Cleanup v0.2

**Status**

Open

---

## AD-002

**Severity**

Medium

**Discovered in**

EP034 Architecture Audit

**Files**

src/bootstrap.py

**Description**

Bootstrap catches `WorkflowSchedulerError`, but no component currently throws this exception.

**Why it matters**

Graceful degradation path exists but is currently unreachable.

**Recommended solution**

Introduce configuration validation that raises `WorkflowSchedulerError` for invalid scheduler settings.

**Planned milestone**

Architecture Cleanup v0.2

**Status**

Open

---

## AD-003

**Severity**

Low

**Discovered in**

EP033 Architecture Audit

**Files**

Multiple service modules

**Description**

Several service modules define identical `ProviderSelectionResult` DTOs.

**Why it matters**

Minor duplication of data transfer objects.

**Recommended solution**

Evaluate introducing a shared immutable DTO during Architecture Cleanup.

**Planned milestone**

Architecture Cleanup v0.2

**Status**

Open

---

# Completed Debt

Move resolved items here.

---

## AD-000

Example only.

Status: Fixed

Resolved in:

Architecture Cleanup v0.2

Description:

Example completed architecture improvement.