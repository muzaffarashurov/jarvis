# EP-069.7 — Capability Lifecycle Management

## 1. Title

EP-069.7 — Capability Lifecycle Management

## 2. Status

**DESIGN PROPOSED — OWNER DECISION REQUIRED.** No Owner Decision for
EP-069.7 exists anywhere in the repository prior to this document.
This STEP 1 does not approve itself.

## 3. Executive Summary

`docs/BACKLOG.md`'s own EP-069.7 bullet names five responsibilities:
*"Registration, versioning, enable/disable, update, revocation, and an
audit trail for every capability regardless of backend."* Direct
inspection shows `Capability` (EP-069.4) is an immutable
(`frozen=True`) dataclass with no history-tracking mechanism, and
`CapabilityRegistry` already owns the mechanical
catalog-membership operations (`register`/`unregister`). What is
genuinely missing — and genuinely EP-069.7's own responsibility — is
a separate, append-only **record of what happened to a capability
over time**: an id-keyed status (`ACTIVE`/`DISABLED`/`REVOKED`) plus
an ordered audit trail of lifecycle events, tracked independently of
`Capability`'s own immutable fields. This design proposes exactly
that, as one new, small, dependency-light package
(`src/core/capability_lifecycle/`), with **no** dependency on
`CapabilityRegistry`, **no** mutation of any `Capability`, **no**
Provider/Engine/Manager framework (there is no pluggable "strategy" to
select between — lifecycle transition rules are fixed, not
interchangeable), and **no** persistence, configuration, or wiring of
any kind.

## 4. Planning Candidate / Source

Confirmed as a genuine, defined planning candidate directly in the
current repository state:

- `docs/BACKLOG.md` (line 3173-3175): **"EP-069.7 — Capability
  Lifecycle Management" (MEDIUM).** *"Registration, versioning,
  enable/disable, update, revocation, and an audit trail for every
  capability regardless of backend."* This is the single authoritative
  scope statement.
- `docs/architecture/JARVIS_ROADMAP.md` (lines 215, 2524) references
  EP-069.7 consistently with the same subject, still planning-only.
- `docs/architecture/designs/ROADMAP_070_138_REBUILD_PROPOSAL.md`
  positions EP-069.7 as the terminal stage of the external-capability
  pipeline in its architecture diagram (§5, line ~205: "Lifecycle Mgmt
  (EP-069.7)", after Verification), and in its validation passes
  (§9): *"all versionable/revocable (EP-069.7)"* and *"lifecycle/
  revocation (EP-069.7) each have a named owner for all four
  scenarios."*
- No `docs/architecture/designs/EP069_7_DESIGN.md` exists yet, and no
  `docs/architecture/audits/EP069_7_*` exists.

**No ambiguity requiring reconciliation was found** — every mention of
EP-069.7 across all three documents describes the same, single
responsibility (registration/versioning/enable-disable/update/
revocation/audit-trail) with no conflicting alternative description
anywhere.

## 5. Architectural Problem

EP-069.4's own STEP 1 design (`EP069_4_DESIGN.md` Section 8) explicitly
deferred this exact scope: *"Registration workflow, versioning
*transitions*, enable/disable *commands*, update, revocation, or an
audit trail — that is EP-069.7's job; EP-069.4's registry supports
only the same minimal register/unregister/find/list operations
`ToolRegistry` already has, as the substrate EP-069.7 will later
govern."* Direct inspection of the current implementation confirms
this gap is real and unfilled:

- `Capability` (`src/core/capability/capability.py`) is
  `@dataclass(frozen=True)` — its `version` and `enabled` fields are
  fixed at construction time and can never be changed on an existing
  instance. There is no way, using `Capability` alone, to represent
  "this capability was version 1.0.0, then became 2.0.0" or "this
  capability was active, then was disabled for reason X, then
  re-enabled."
- `CapabilityRegistry` (`src/core/capability/capability_registry.py`)
  supports only `register`/`unregister`/`get`/`find`/`list`/
  `is_registered` — a *current-state* catalog with no history. Calling
  `unregister()` then `register()` again to simulate an "update"
  would silently discard all information about the previous version
  ever having existed.
- **No audit-trail or event-log pattern exists anywhere in this
  repository** (`grep -rli "audit_trail\|AuditTrail\|AuditLog\|
  event_log\|EventLog" src/` returns zero matches) — this is a
  genuinely new pattern for this codebase, not a reuse of an existing
  one.
- The closest prior-art precedent, `Plugin`/`PluginStatus`
  (EP-009, `src/core/plugins/plugin.py`), tracks a five-stage runtime
  lifecycle (`REGISTERED`/`LOADED`/`INITIALIZED`/`RUNNING`/`STOPPED`/
  `UNLOADED`/`FAILED`) by **mutating a plain (non-frozen) `Plugin`
  dataclass's own `status` field in place**. This exact technique is
  unavailable to EP-069.7, because `Capability` is deliberately
  immutable (EP-069.4's own design choice) — lifecycle status and
  history must be tracked in a *separate* structure, keyed by
  capability id, external to `Capability` itself. This is the single
  most important architectural constraint this design responds to.

## 6. Current-State Analysis

- **No concrete `CapabilityBackend` exists** (re-confirmed:
  `grep -rn "(CapabilityBackend)" src/` matches only the ABC's own
  declaration) — there is still no "external capability" being
  downloaded, installed, or executed anywhere in this codebase.
- **`CapabilityRegistry` is never populated in production**
  (re-confirmed absent from `src/bootstrap.py`, unchanged since
  EP-069.4's own STEP 1 finding) — exactly as EP-069.5's and
  EP-069.6's own STEP 1 designs each independently found and
  explicitly declined to fix.
- **EP-070 (Policy, Permissions & Human Approval Engine) does not
  exist** (re-confirmed: `grep -rn "class.*Policy" src/` still matches
  only the unrelated `RestartPolicy`) — nothing in this codebase
  currently reads a capability's enabled/disabled/revoked status to
  gate anything.
- This means EP-069.7, like EP-069.5 and EP-069.6 before it, is being
  built with **no live consumer and no populated registry to operate
  against in production**. The design responds to this exactly as its
  two predecessors did: build a small, fully self-contained,
  independently testable component now; defer any integration wiring
  to a future EP once a real consumer exists.

## 7. Existing Architecture Relevant to EP-069.7

- `src/core/capability/capability.py` — `Capability` (frozen),
  `CapabilitySourceKind`, `CapabilityTrustLevel`, `CapabilityError`
  (root). Public, stable, unmodified dependency surface.
- `src/core/capability/capability_registry.py` — `CapabilityRegistry`,
  `CapabilityRegistryError`, `CapabilityNotFoundError`. Not consumed
  by this design at all (Section 12, Owner Decision OD1).
- `src/core/capability_discovery/` (EP-069.5) — no relationship in
  either direction; a sibling consumer of `Capability`.
- `src/core/capability_security/` (EP-069.6) — no relationship in
  either direction; a sibling consumer of `Capability`. Notably,
  EP-069.6 already established the precedent this design follows most
  closely: a small, dependency-light package with a correctly-rooted
  error hierarchy, zero registry coupling, and zero composition-root
  wiring.
- `src/core/plugins/plugin.py` — `PluginStatus` (a 7-state lifecycle
  enum) — read for precedent (Section 5) but not reused directly,
  since it assumes a mutable host object `Capability` does not permit.
- `src/core/tool/tool_registry.py`, `src/core/capability/
  capability_registry.py` — the established "thread-safe, in-memory,
  id-keyed dict + lock" registry shape this design's own tracker
  reuses structurally (Section 9).

## 8. Architectural Goals

- Provide a small, standalone, in-memory tracker that records a
  capability's lifecycle status (`ACTIVE`/`DISABLED`/`REVOKED`) and an
  ordered, append-only history of the events that produced it
  (registration, update, enable, disable, revocation).
- Enforce the one genuine business rule this domain requires:
  revocation is terminal — a revoked capability accepts no further
  lifecycle transition.
- Keep the component fully independent of `CapabilityRegistry`,
  `CapabilityDiscoveryEngine`, and `CapabilitySecurityEngine` — a
  fourth, sibling consumer of `Capability`'s public data model only.
- Make every operation deterministic and fully testable in isolation,
  with no wall-clock, filesystem, network, or process dependency.

## 9. Non-Goals

- **No mutation of any `Capability` instance** — `Capability` remains
  frozen and untouched; this design tracks status/history *about* a
  capability id, never *on* the `Capability` object itself.
- **No dependency on, or call into, `CapabilityRegistry`** — this
  design does not register, unregister, or query the live catalog
  (Section 12, Owner Decision OD1). A capability's presence in
  `CapabilityRegistry` and its lifecycle status in this new package
  are two independent facts a future orchestration layer would
  reconcile — not this EP's job.
- **No discovery, ranking, or security assessment** — EP-069.5's and
  EP-069.6's responsibilities remain entirely theirs; this design
  imports nothing from either package and duplicates none of their
  logic.
- **No security/policy enforcement** — a `REVOKED` status has no
  effect on anything outside this package; nothing in this codebase
  currently reads it to block execution, because no execution pathway
  exists (Section 6).
- **No Provider/Engine/Manager framework** — there is exactly one
  correct way to enforce lifecycle transition rules; there is no
  pluggable "strategy" analogous to `DefaultCapabilityDiscoveryProvider`'s
  swappable fit-scoring algorithm or
  `DefaultCapabilitySecurityProvider`'s swappable check set. A single
  concrete class is the correctly-sized architecture (Owner Decision
  OD4).
- **No persistence of any kind** — no file, database, or cache. All
  state is in-memory only and lost on process restart, exactly like
  `CapabilityRegistry`'s own catalog.
- **No wall-clock timestamp field** — event ordering is by a
  monotonic, in-process sequence number only, to keep every operation
  deterministic and independent of system time (Owner Decision OD5).
- **No `src/bootstrap.py`, `config/config.yaml`, Manager, or CLI
  wiring of any kind** — mirroring EP-069.5's and EP-069.6's own
  immediate, identical precedent (Owner Decision OD7).
- **No modification to `Capability`, `CapabilityRegistry`,
  `CapabilityBackend`, or any EP-069.5/.6 file.**

## 10. Proposed Architecture

Placement: `src/core/capability_lifecycle/`, mirroring
`src/core/capability_discovery/`/`src/core/capability_security/`'s own
naming and placement pattern (Owner Decision OD3). Two files — fewer
than either sibling package, since there is no Provider/Engine split
to make (Owner Decision OD4):

```
src/core/capability_lifecycle/
    __init__.py                        # public API surface
    capability_lifecycle_result.py     # plain data: CapabilityLifecycleStatus, CapabilityLifecycleEventType, CapabilityLifecycleEvent
    capability_lifecycle_registry.py   # CapabilityLifecycleRegistry, error hierarchy
```

## 11. Component Responsibilities

**`CapabilityLifecycleStatus`** (`capability_lifecycle_result.py`)
- A 3-value enum: `ACTIVE`, `DISABLED`, `REVOKED`. `REVOKED` is
  terminal (Section 14, Owner Decision OD6).

**`CapabilityLifecycleEventType`** (`capability_lifecycle_result.py`)
- A 5-value enum naming exactly the five BACKLOG-named actions:
  `REGISTERED`, `UPDATED`, `ENABLED`, `DISABLED`, `REVOKED`.

**`CapabilityLifecycleEvent`** (`capability_lifecycle_result.py`)
- A single, immutable, ordered audit-trail entry. Fields:
  `sequence: int` (monotonic, assigned by the registry, the sole
  ordering key), `capability_id: str`, `event_type:
  CapabilityLifecycleEventType`, `version: str` (the capability's
  version as of this event — unchanged from the prior event for
  `ENABLED`/`DISABLED`/`REVOKED`, which never alter version),
  `reason: str = ""` (optional; populated for `DISABLED`/`REVOKED`,
  blank for the other three). Frozen dataclass — no behavior.

**`CapabilityLifecycleRecord`** (`capability_lifecycle_result.py`)
- The current, queryable state for one capability id:
  `capability_id: str`, `status: CapabilityLifecycleStatus`,
  `current_version: str`, `history: list[CapabilityLifecycleEvent]`
  (ordered by `sequence`, oldest first). Returned by
  `CapabilityLifecycleRegistry.record(...)` — a read-only snapshot,
  not a live reference into the registry's own internal state
  (mirroring `CapabilityRegistry.list()`'s own "returns a new list
  each call" convention).

**`CapabilityLifecycleRegistry`** (`capability_lifecycle_registry.py`)
- A single concrete class (no ABC, no Provider, no Engine, no
  Manager — Owner Decision OD4), thread-safe (a lock, mirroring
  `CapabilityRegistry`'s own shape), holding an in-memory,
  capability-id-keyed dict of tracked records plus a single, shared,
  monotonically increasing sequence counter.
- Public methods:
  - `register(capability: Capability) -> CapabilityLifecycleEvent` —
    begins tracking `capability.id`, initial status `ACTIVE`, logs a
    `REGISTERED` event. Raises `CapabilityLifecycleConflictError` if
    already tracked.
  - `update(capability: Capability) -> CapabilityLifecycleEvent` —
    logs an `UPDATED` event and updates `current_version` to
    `capability.version`. Raises `CapabilityLifecycleNotFoundError` if
    untracked; raises `CapabilityLifecycleConflictError` if current
    status is `REVOKED`.
  - `disable(capability_id: str, reason: str = "") ->
    CapabilityLifecycleEvent` — `ACTIVE` -> `DISABLED`, logs a
    `DISABLED` event. Raises `NotFound` if untracked; raises
    `Conflict` if `REVOKED`. Calling on an already-`DISABLED`
    capability is a harmless no-op that still logs a new event (an
    operator may disable again with a different reason).
  - `enable(capability_id: str) -> CapabilityLifecycleEvent` —
    `DISABLED` -> `ACTIVE`, logs an `ENABLED` event. Calling on an
    already-`ACTIVE` capability is a no-op that does **not** log a
    duplicate event (returns the capability's current record
    unchanged) — avoids polluting the audit trail with meaningless
    repeats of an already-true fact. Raises `Conflict` if `REVOKED`.
  - `revoke(capability_id: str, reason: str) ->
    CapabilityLifecycleEvent` — any non-terminal status -> `REVOKED`,
    logs a `REVOKED` event. `reason` is **required**
    (`CapabilityLifecycleValidationError` if blank). Raises `Conflict`
    if already `REVOKED` (no double-revocation).
  - `status(capability_id: str) -> CapabilityLifecycleStatus` —
    raises `NotFound` if untracked.
  - `history(capability_id: str) -> list[CapabilityLifecycleEvent]` —
    a fresh, ordered copy; raises `NotFound` if untracked.
  - `is_tracked(capability_id: str) -> bool` — mirrors
    `CapabilityRegistry.is_registered()`; never raises.
- Never imports, references, or calls `CapabilityRegistry`,
  `CapabilityBackend`, `CapabilityDiscoveryEngine`, or
  `CapabilitySecurityEngine` (Owner Decision OD1).
- Never mutates the `Capability` instance passed to `register()`/
  `update()` — only reads `.id`/`.version` from it.

## 12. Owner Decisions

**OD1 — Dependency on `CapabilityRegistry`.**
  - Option A (**Recommended**): `CapabilityLifecycleRegistry` has zero
    dependency on, and never calls, `CapabilityRegistry`. It operates
    purely on `Capability` objects/ids handed to it by a caller. A
    future orchestration layer is responsible for coordinating both
    components together.
  - Option B: `CapabilityLifecycleRegistry` wraps `CapabilityRegistry`
    internally, calling its `register()`/`unregister()` as part of its
    own lifecycle operations, so a caller only needs to call one
    component.
  - **Consequence of Option A**: matches EP-069.5's and EP-069.6's own
    identical "operate on data handed in, never own the registry"
    precedent exactly; keeps this package trivially testable with
    plain `Capability` objects and no registry construction required;
    avoids a new dependency edge onto `CapabilityRegistry`'s mutation
    methods (a stricter, more conservative boundary than strictly
    necessary, but consistent with the established pattern).

**OD2 — Should `disable`/`revoke` also remove the capability from
`CapabilityRegistry`'s live catalog?**
  - Option A (**Recommended**): No — this design tracks status only;
    it never calls `CapabilityRegistry.unregister()`. A
    `REVOKED`/`DISABLED` status recorded here has no automatic effect
    on the live catalog.
  - Option B: `revoke()` (and/or `disable()`) also calls
    `CapabilityRegistry.unregister()` to make the capability
    immediately undiscoverable.
  - **Consequence of Option A**: consistent with OD1 (zero
    `CapabilityRegistry` dependency); avoids this EP silently becoming
    a second, competing entry point for catalog mutation. A future
    integration layer that already depends on both packages is the
    correct place to wire "revoked implies unregistered," once such a
    layer's own STEP 1 scopes it.

**OD3 — Physical package location.**
  - Option A (**Recommended**): `src/core/capability_lifecycle/`,
    matching the established sibling convention exactly.
  - Option B: A new top-level `src/engines/` directory.
  - **Consequence of Option A**: zero new top-level directory
    convention invented, consistent with EP-069.4/.5/.6's own
    precedent.

**OD4 — Provider/Engine/Manager framework vs. a single concrete class.**
  - Option A (**Recommended**): One concrete class,
    `CapabilityLifecycleRegistry`, with no ABC and no swappable
    strategy.
  - Option B: Mirror `CapabilityDiscoveryProvider`/
    `CapabilitySecurityProvider`'s ABC-plus-one-default-implementation
    shape speculatively, for "consistency."
  - **Consequence of Option A**: this domain has exactly one correct
    set of transition rules (Section 11) — there is nothing to make
    pluggable, and introducing an ABC with a single, permanently-sole
    implementation would be exactly the "unnecessary Manager layer"/
    "speculative abstraction" this task's own Section 9 instructs
    against. `CapabilityRegistry` (EP-069.4) itself is the closer,
    more apt precedent: a single concrete registry class, no ABC.

**OD5 — Event timestamping.**
  - Option A (**Recommended**): No wall-clock `timestamp` field.
    Ordering is by a monotonic `sequence: int` only.
  - Option B: Include a `datetime`-based `timestamp` field on
    `CapabilityLifecycleEvent`.
  - **Consequence of Option A**: keeps every operation deterministic
    and independent of system time, directly enabling the exact
    determinism guarantees Section 19/24 require and mirroring
    EP-069.6's own audited preference for no speculative field with no
    current consumer (`EP069_6_ARCHITECTURE_AUDIT.md` Section 8 praised
    the absence of exactly this kind of premature field). A future EP
    that needs wall-clock time can add it additively without breaking
    this contract.

**OD6 — Terminal-state strictness for `REVOKED`.**
  - Option A (**Recommended**): `REVOKED` is strictly terminal — any
    further call to `update()`/`disable()`/`enable()`/`revoke()` on an
    already-`REVOKED` capability id raises
    `CapabilityLifecycleConflictError`.
  - Option B: Allow re-enabling a revoked capability (treat `REVOKED`
    as merely another reversible state, like `DISABLED`).
  - **Consequence of Option A**: matches real-world "revocation is
    final" semantics and BACKLOG's own framing of revocation as a
    distinct, more severe action than disabling; prevents a caller
    from silently undoing a revocation decision through an ordinary
    `enable()` call.

**OD7 — Composition-root wiring.**
  - Option A (**Recommended**): None — no `src/bootstrap.py`,
    `config/config.yaml`, CLI surface, or Manager registration of any
    kind, identical to EP-069.5's OD2/EP-069.6's OD4.
  - Option B: Full wiring, matching the *older* Core subsystems'
    precedent.
  - **Consequence of Option A**: consistent with the two most recent,
    most directly relevant precedents, and appropriate given no live
    consumer exists yet (Section 6).

## 13. Scope

### IN SCOPE
- `CapabilityLifecycleStatus`, `CapabilityLifecycleEventType`,
  `CapabilityLifecycleEvent`, `CapabilityLifecycleRecord` (data model).
- `CapabilityLifecycleRegistry` with exactly the 8 methods in Section
  11.
- The correctly-rooted `CapabilityLifecycleError` hierarchy (Section
  16).
- Isolated `tests/EP069_7/` tests.

### OUT OF SCOPE
- Anything already owned by `CapabilityRegistry` (catalog membership
  itself), `CapabilityDiscoveryEngine` (ranking), or
  `CapabilitySecurityEngine` (risk assessment).
- Anything owned by EP-070 (actual policy enforcement of a
  `REVOKED`/`DISABLED` status).
- Persistence, configuration, CLI, bootstrap wiring (Section 15/20).
- `Tool -> Capability` / `Plugin -> Capability` bridging (still
  nobody's job yet — orthogonal to this EP).

## 14. Deferred Work

- **Wiring `CapabilityLifecycleRegistry` together with
  `CapabilityRegistry`** (so that, e.g., revocation actually
  unregisters) — deferred to a future integration EP once both a real
  backend and a real consumer exist (Owner Decision OD1/OD2's Option B
  remains available then, not foreclosed by this design).
- **Wall-clock timestamps on events** — deferred (Owner Decision OD5);
  additive, non-breaking to add later.
- **Persistence across process restarts** — deferred; no current
  requirement exists since nothing populates `CapabilityRegistry` in
  production yet either (Section 6).
- **EP-070 policy-engine integration** — EP-070 does not exist; this
  design leaves `CapabilityLifecycleRegistry.status()` as a plain,
  readable fact a future EP-070 could consult, without this EP calling
  into it.

No placeholder types for any of the above are introduced now
(consistent with EP-069.6's own explicit, audited Non-Goal on this
exact point).

## 15. Dependency Direction

```
Capability (EP-069.4, unmodified)
          |
          v (read-only: .id, .version only)
CapabilityLifecycleEvent, CapabilityLifecycleRecord,
CapabilityLifecycleStatus, CapabilityLifecycleEventType
          |
          v
CapabilityLifecycleRegistry
```

No dependency on `CapabilityRegistry`, `CapabilityBackend`,
`CapabilityDiscoveryEngine`, `CapabilitySecurityEngine`,
`src.core.planning`, `src.core.agent`, `src.bootstrap`, or `config`.
No dependency in the other direction: nothing in EP-069.4/.5/.6
depends on this package. No circular dependency. EP-069.7 depends only
on `Capability`'s public data model (`id`, `version` fields), never on
any private implementation detail of any sibling package.

## 16. Public Contracts

All raise/return behavior is exact and deterministic; see Section 11
for the full method list. Error hierarchy:

- `CapabilityLifecycleError(Exception)` — root, mirroring
  `CapabilityError`/`CapabilityDiscoveryError`/`CapabilitySecurityError`'s
  now-universal convention in this repository.
- `CapabilityLifecycleNotFoundError(CapabilityLifecycleError)` —
  raised by `update`/`disable`/`enable`/`revoke`/`status`/`history`
  when `capability_id` has never been `register()`-ed.
- `CapabilityLifecycleConflictError(CapabilityLifecycleError)` —
  raised by `register()` on a duplicate id; by
  `update`/`disable`/`enable`/`revoke` when current status is
  `REVOKED` (Owner Decision OD6); and by `revoke()` on an
  already-`REVOKED` id.
- `CapabilityLifecycleValidationError(CapabilityLifecycleError)` —
  raised by `revoke()` when `reason` is blank.

Invariants: `history(id)`'s returned list is always non-empty once
`register()` has succeeded (registration itself is always the first
event); `sequence` values are strictly increasing across the entire
registry instance (not per-capability), so the global event order
across every tracked capability is always recoverable by sorting on
`sequence`.

## 17. Error Handling

Reuses this repository's now-established, four-EP-consistent pattern
(a rooted exception hierarchy, specific subclasses per failure mode,
no bare `except`, no silent failure) rather than inventing a new
convention. Invalid input (`revoke()` with a blank `reason`) is
rejected loudly at the boundary, never silently coerced into a valid
value.

## 18. Data / State / Persistence

**Stateful in-memory only; no persistence.** Unlike EP-069.5/EP-069.6
(both stateless, pure functions over data handed in per call),
`CapabilityLifecycleRegistry` genuinely holds state — an id-keyed dict
of `CapabilityLifecycleRecord`s and a shared sequence counter — because
remembering history *is* this component's entire purpose. This state
is not written to any file, database, or cache, and is lost when the
process restarts, exactly like `CapabilityRegistry`'s own catalog.

## 19. Security / Trust Boundary

EP-069.7 does not consume EP-069.6's `CapabilitySecurityAssessment`
and does not produce one — the two are unrelated data shapes for
unrelated questions ("is this capability risky" vs. "what happened to
this capability over time"). EP-069.7 **does not enforce security**:
a `REVOKED` or `DISABLED` status is a recorded fact, not an enforced
one — nothing in this codebase currently reads it to block anything
(Section 6). It does not approve or reject capabilities (that remains
EP-070's named, future, exclusive responsibility, exactly as
EP-069.6's own design established for the identical class of concern)
and does not execute any capability. This design does not duplicate
EP-069.6 in any way: it introduces no risk classification, no finding
category, and reads none of `Capability`'s security-relevant fields
(`trust_level`, `required_permissions`, `source_kind`) at all — only
`id` and `version`.

## 20. Configuration / Bootstrap / CLI

**None required.** Per Owner Decision OD7, no `config/config.yaml`
key, no `src/bootstrap.py` change, no CLI namespace, and no Manager
registration are part of this design. These remain explicitly out of
scope, not added merely to make the architecture "look complete."

## 21. Test Strategy

New, isolated package: `tests/EP069_7/` (STEP 2), matching the
established convention (`tests/EP069_7/__init__.py`, `tests/EP069_7/
test_capability_lifecycle_registry.py`).

- **Core behavior**: `register()` creates an `ACTIVE` record with a
  `REGISTERED` event; `update()` changes `current_version` and appends
  an `UPDATED` event; `disable()`/`enable()` toggle status correctly
  and append the expected event types.
- **Happy paths**: a full lifecycle (register -> update -> disable ->
  enable -> revoke) produces the expected final status and an exactly
  ordered 5-event history.
- **Invalid input / error handling**: `register()` on a duplicate id
  raises `Conflict`; `update`/`disable`/`enable`/`revoke`/`status`/
  `history` on an untracked id raise `NotFound`; `revoke()` with a
  blank `reason` raises `Validation`.
- **Boundary conditions**: `enable()` on an already-`ACTIVE`
  capability is a no-op that does not append a duplicate event
  (assert `history()` length unchanged); `disable()` on an
  already-`DISABLED` capability *does* append a new event (assert
  length increases).
- **Terminal-state enforcement**: after `revoke()`, every one of
  `update`/`disable`/`enable`/`revoke` raises `Conflict` — tested
  individually for all four.
- **Determinism**: `sequence` values are strictly increasing and
  stable across repeated `history()` calls for the same registry
  instance; two independent `CapabilityLifecycleRegistry` instances
  given the identical sequence of operations produce
  identically-shaped (modulo instance identity) records.
- **Dependency boundaries**: verify (via the same import-line static
  check technique used in `tests/EP069_6/`) that the package never
  imports `capability_registry`, `capability_backend`,
  `capability_discovery`, `capability_security`, `planning`, `agent`,
  `bootstrap`, or `config`.
- **Regression suites**: re-run `EP069_6`, `EP069_5`, `EP069_4`,
  `EP069_3`, `EP069_2`, `EP069`, and `EP056` unchanged.

Test counts are not inflated — each behavioral distinction above maps
to exactly one focused test method.

## 22. Exact File Forecast

**NEW:**
- `src/core/capability_lifecycle/__init__.py`
- `src/core/capability_lifecycle/capability_lifecycle_result.py`
- `src/core/capability_lifecycle/capability_lifecycle_registry.py`
- `tests/EP069_7/__init__.py`
- `tests/EP069_7/test_capability_lifecycle_registry.py`

**MODIFIED:**
- `src/modules/test_module.py` (+1 import line, the standard,
  repository-wide test-registration convention every prior EP-069.x
  also required).

**EXPECTED UNTOUCHED:**
- `src/core/capability/*` (EP-069.4) — all four files.
- `src/core/capability_discovery/*` (EP-069.5) — all four files.
- `src/core/capability_security/*` (EP-069.6) — all four files.
- `src/bootstrap.py`, `config/config.yaml`.
- `src/core/tool/*`, `src/core/plugins/*`, `src/core/planning/*`,
  `src/core/agent/*`.
- `src/skills/capability_registry/skill.py` (EP-056).
- `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`,
  `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `VERSION`,
  `PROJECT_MANIFEST.md`, every `docs/architecture/audits/*` file —
  STEP 4/audit concerns, not STEP 1/2.

## 23. Scope-Creep Guard

STEP 2 MUST NOT implement any of the following:

- No execution of any capability.
- No mutation of any `Capability` instance.
- No dependency on, or call into, `CapabilityRegistry`
  (`register()`/`unregister()`/`get()`/`find()`/`list()`/
  `is_registered()` must never appear as a call anywhere in this
  package).
- No import of `capability_discovery` or `capability_security`.
- No security enforcement, risk assessment, or policy decision of any
  kind.
- No policy engine, no EP-070 reference or integration.
- No external services, no network calls, no filesystem access beyond
  the package's own source files.
- No CLI namespace, no `CommandModule`/`CommandRouter` reference.
- No `src/bootstrap.py` or `config/config.yaml` change.
- No Manager class, no Provider/Engine ABC framework.
- No wall-clock `datetime`/`time` dependency anywhere in the event
  model or registry logic.
- No persistence (file, database, cache) of any kind.
- No modification to any EP-069.4, EP-069.5, or EP-069.6 file.

## 24. Acceptance Criteria

1. `CapabilityLifecycleRegistry`, `CapabilityLifecycleStatus`,
   `CapabilityLifecycleEventType`, `CapabilityLifecycleEvent`,
   `CapabilityLifecycleRecord`, and the four-class error hierarchy all
   exist and are exported from `src/core/capability_lifecycle/__init__.py`.
2. `register()` on a fresh id succeeds with status `ACTIVE` and a
   single `REGISTERED` event; on a duplicate id raises
   `CapabilityLifecycleConflictError`.
3. `update()`/`disable()`/`enable()`/`revoke()`/`status()`/`history()`
   on an untracked id each raise `CapabilityLifecycleNotFoundError`.
4. `revoke()` with a blank `reason` raises
   `CapabilityLifecycleValidationError`.
5. After `revoke()`, every one of `update`/`disable`/`enable`/`revoke`
   raises `CapabilityLifecycleConflictError`.
6. `enable()` on an already-`ACTIVE` id does not append a new event;
   `disable()` on an already-`DISABLED` id does append a new event.
7. `sequence` values are strictly increasing across the registry
   instance's entire lifetime, and `history()` is always returned
   sorted by `sequence`.
8. No test or implementation file imports `capability_registry`,
   `capability_backend`, `capability_discovery`, or
   `capability_security` from this package.
9. `EP069_6`, `EP069_5`, `EP069_4`, `EP069_3`, `EP069_2`, `EP069`, and
   `EP056` all remain green, unchanged in count, after STEP 2.
10. `src/bootstrap.py`, `config/config.yaml`, and every EP-069.4/.5/.6
    file are byte-identical before and after STEP 2.

## 25. Design Risks / Trade-offs

- **OD1/OD2's full decoupling from `CapabilityRegistry` means a
  capability can be `REVOKED` here while still fully live and
  discoverable in `CapabilityRegistry`** — an intentional, accepted
  trade-off (Section 14) rather than an oversight; a future
  integration layer is the correct place to close this gap once one
  is actually needed.
- **`enable()`'s asymmetric no-op behavior (silent for `ACTIVE`,
  event-logging for `DISABLED`) could be seen as an inconsistency** —
  it is a deliberate choice to keep the audit trail free of
  meaningless "enabled an already-enabled thing" noise while still
  respecting an operator's explicit intent to re-disable with a new
  reason; documented explicitly here and in Section 11/24 rather than
  left implicit.
- **No timestamp (OD5) may be seen as a real limitation for a genuine
  audit trail** by some reviewers who expect wall-clock time in any
  audit-trail concept — mitigated by the additive, non-breaking path
  to add it later (Section 14) once a real consumer needs it.

## 26. Design Validation

Explicitly re-challenged per this task's own Section 20 checklist:

1. *Genuinely needed?* Yes — EP-069.4 explicitly named this exact gap
   as EP-069.7's job in its own STEP 1 (Section 5).
2. *Already implemented elsewhere?* No — confirmed zero audit-trail
   pattern exists anywhere in this repository (Section 5).
3. *Actually EP-069.7's responsibility?* Yes — matches BACKLOG's bullet
   verbatim.
4. *Overlaps EP-069.4?* No — `CapabilityRegistry`'s catalog-membership
   operations are untouched and uncalled; this design tracks history,
   not current catalog membership.
5. *Overlaps EP-069.5?* No — no discovery/ranking logic anywhere.
6. *Overlaps EP-069.6?* No — no security/risk assessment anywhere;
   confirmed by the complete absence of any `trust_level`/
   `required_permissions`/`source_kind` read.
7. *Belongs to EP-070 instead?* No — EP-070 is the future *enforcement*
   authority; this design produces no enforcement, only a recorded
   fact a future EP-070 could read.
8. *Any component speculative?* No — every field/method maps directly
   to one of the five BACKLOG-named responsibilities; Section 14 lists
   what was deliberately deferred rather than spuriously included.
9. *Any Manager unnecessary?* Confirmed none included (Owner Decision
   OD4).
10. *Persistence necessary?* No (Section 18).
11. *Configuration necessary?* No (Section 20).
12. *CLI necessary?* No (Section 20).
13. *Dependency direction clean?* Yes — depends only on `Capability`'s
    public `id`/`version` fields (Section 15).
14. *Can the design be made smaller without losing required behavior?*
    No further reduction was found possible without dropping one of
    BACKLOG's five explicitly named responsibilities
    (registration/versioning/enable-disable/update/revocation) or the
    audit trail itself.

## 27. Final Recommendation

Proceed to STEP 2 implementing exactly the architecture in Sections
10-11, contingent on Owner approval of the seven Owner Decisions in
Section 12 (all seven recommended options are mutually consistent with
each other and with the established EP-069.5/EP-069.6 precedent).

---

## EP-069.7 STEP 1 — COMPLETE — OWNER DECISION REQUIRED
