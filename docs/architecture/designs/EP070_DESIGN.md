# EP-070 — Policy, Permissions & Human Approval Engine (Capability Decision Slice)

## 1. Title

EP-070 — Policy, Permissions & Human Approval Engine (this STEP 1
scopes a **capability policy-decision slice** only — see Section 7 and
Section 31, Scope-Creep Guard, for why the full BACKLOG title's
broader scope is not built in one pass).

## 2. Status

**DESIGN PROPOSED — READY FOR OWNER APPROVAL (CORRECTED).** All nine
Owner Decisions (Section 12) have been reviewed. OD4 (the
deterministic policy rule table) was approved exactly as proposed,
with one mandatory semantic clarification: `OBSERVE` is a restrictive
policy decision, never execution authorization — this clarification
is now reflected consistently throughout this document. No table row,
`PolicyLevel` value, or architectural boundary changed as a result.

## 3. Executive Summary

`docs/BACKLOG.md`'s EP-070 bullet is one sentence: *"Centralized
policy control over sensitive/external actions, with graduated levels
such as OBSERVE, ANALYZE, PREPARE, EXECUTE, and REQUIRE_APPROVAL.
Reused by: every EP-069.4-.7 capability execution path — external
capabilities never bypass this gate."* Direct inspection confirms two
things simultaneously: (1) this is a genuine, still-open architectural
gap — no policy/approval/authorization engine of any kind exists
anywhere in this repository (confirmed by repository-wide search,
Section 6); and (2) there is, at an even deeper level than EP-069.5's,
EP-069.6's, or EP-069.7's own STEP 1 findings, **no execution path for
"capabilities" to gate at all** — the only real invocation pipeline in
this codebase (`ToolEngine`, for internal `Tool`s) has never been
connected to the `Capability` model, and `CapabilityBackend` still has
zero concrete implementations. This design therefore proposes the same
pattern already established three times over (EP-069.5/.6/.7): a
small, fully self-contained, deterministic **decision engine** —
`src/core/capability_policy/` — that computes a `PolicyLevel` for one
capability given its EP-069.4 identity and optional EP-069.6/EP-069.7
outputs, with **zero enforcement, zero wiring, and zero new persistence
or configuration**, because there is nothing yet to enforce against.

## 4. Repository Evidence

- `docs/BACKLOG.md` line 3176-3180: the sole authoritative scope
  statement, quoted in full above.
- `docs/architecture/JARVIS_ROADMAP.md` line 2523 references EP-070
  consistently, still planning-only.
- `docs/architecture/designs/ROADMAP_070_138_REBUILD_PROPOSAL.md`:
  positions EP-070 as the stage immediately after the
  Capability/Tool Registry and immediately before Credential Isolation
  (EP-071) in its architecture diagram (§5); its dependency graph (§6)
  shows `EP-069(+.4-.7) --> EP-070 --> EP-071 --> EP-072 --> EP-073`;
  and its own validation pass states *"External capabilities never
  bypass security: every adapter path... routes through
  EP-070/EP-069.6 before execution."*
- `docs/BACKLOG.md`'s "Global Security Principles" section (line 3550)
  gives the only elaboration of *intent* found anywhere: *"least
  privilege; human approval for sensitive actions;... auditability of
  important actions; preferring reversible/cancellable/rollback-capable
  actions;... and pausing for human intervention whenever... an action
  is high-risk, ambiguous, irreversible, or confidence is
  insufficient."* No document anywhere defines the graduated levels'
  precise semantics, ordering, or the mapping rules that would produce
  one.
- Two other BACKLOG entries (EP-128, EP-130) reference EP-070 as a
  generic future "approval" dependency for unrelated, far-future
  domains (device command approval, enterprise document changes) —
  confirming EP-070 is intended as a reusable, general decision point,
  not a capability-only mechanism forever, but with capability
  execution named as its first, current consumer.
- **No existing policy/approval/authorization engine exists anywhere
  in this repository.** A repository-wide search for `policy`/
  `approval`/`permission`/`authoriz` across `src/` was independently
  reviewed match-by-match: every hit is either `RestartPolicy`
  (process-supervision, `src/core/processes/process.py`, unrelated),
  `stop_on_failure` policy (`src/core/plan_execution/`, unrelated
  failure-handling), `TelegramRouter.is_authorized()` (a static
  chat-id allowlist, unrelated), or an HTTP `Content-Type` policy
  (`src/core/api/rest_api_server.py`, unrelated). None is a
  capability-action policy/approval mechanism.
- **No execution path connects to `Capability` at all.** The only
  real invocation pipeline in this codebase,
  `src/core/tool/tool_execution_provider.py`
  (`ToolExecutionProvider` -> `ToolEngine.invoke_for_step()`), bridges
  Plan Execution (EP-030) to internal `Tool`s only — it has no
  reference to `Capability`, `CapabilityBackend`, or any EP-069.x
  package. `CapabilityBackend` (EP-069.4) still has zero concrete
  implementations (re-confirmed: `grep -rn "(CapabilityBackend)"
  src/` matches only the ABC's own declaration).

## 5. Architectural Problem

EP-069.4 through EP-069.7 each independently, and by explicit design,
declined to make a binding decision:

- EP-069.4's `Capability.trust_level`/`required_permissions` are
  declared, inert fields (`EP069_4_DESIGN.md` Section 8: "no policy
  engine, no execution").
- EP-069.5's `CapabilityDiscoveryEngine` ranks by trust as a sort key
  only ("'Ranking by trust' is not 'enforcing trust,'"
  `EP069_5_DESIGN.md` Section 5).
- EP-069.6's `CapabilitySecurityEngine` produces an advisory
  `CapabilitySecurityAssessment` with explicitly no `approved`/
  `rejected` field (`EP069_6_DESIGN.md` Owner Decision OD2): *"Actual
  approval remains EP-070's named, future, exclusive responsibility."*
- EP-069.7's `CapabilityLifecycleRegistry` records status
  (`ACTIVE`/`DISABLED`/`REVOKED`) as a fact, never an enforcement
  decision (`EP069_7_DESIGN.md` Section 19).

Every one of these four EPs, independently, named EP-070 as the place
this decision finally gets made. That is a real, load-bearing gap:
nothing today can answer "given everything currently known about this
capability, what should happen next?" This design fills exactly that
gap — and no more.

## 6. Existing Architecture

Summarized from Section 4's evidence: no policy engine, no execution
path connecting to `Capability`, and (from EP-069.4/.5/.6/.7's own
STEP 1 findings, independently re-confirmed unchanged in this STEP 1)
`CapabilityRegistry` is never populated in production. The four
sibling packages this design consumes:

- `src/core/capability/capability.py` — `Capability` (frozen),
  `CapabilitySourceKind`, `CapabilityTrustLevel`.
- `src/core/capability_discovery/` — irrelevant to this design (ranks
  candidates for a task; does not participate in a policy decision for
  one already-identified capability).
- `src/core/capability_security/` — `CapabilitySecurityAssessment`
  (`overall_risk_level`, `findings`).
- `src/core/capability_lifecycle/` — `CapabilityLifecycleStatus`
  (`ACTIVE`/`DISABLED`/`REVOKED`).

## 7. EP-070 Responsibility

**In this slice**: given one `Capability` and (optionally) its
EP-069.6 security assessment and EP-069.7 lifecycle status, compute a
deterministic `PolicyLevel` (one of the five BACKLOG-named values)
plus the reasons that produced it. **Not in this slice**: actually
enforcing that level anywhere (no execution path exists to enforce it
on, Section 4), providing a human-approval workflow/UI (`REQUIRE_APPROVAL`
is a computed label, not a paused, resumable process — building the
latter needs an execution engine and a notification mechanism, neither
of which exist), or replacing any of EP-069.4/.5/.6/.7's own
responsibilities.

**Mandatory semantic clarification (Owner-issued):** `OBSERVE` is a
**restrictive** policy decision, not permission to execute. A
`REVOKED` or `DISABLED` capability mapping to `OBSERVE` (Section 12,
OD4/OD5) does **not** mean that capability is executable — it means
the opposite: this engine has decided the capability should, at most,
be observed, never acted on. EP-070 itself performs no enforcement of
this or any other decision (Section 17); any future enforcement or
integration code that consumes a `PolicyDecision` must treat `OBSERVE`
as a restrictive outcome and must never treat it as execution
authorization.

## 8. Relationship to EP-069.4

Depends on `Capability`'s public fields (`id`, `source_kind`,
`trust_level`) read-only. Does not modify, extend, or subclass
anything in `src/core/capability/`. No dependency on
`CapabilityRegistry` — mirrors EP-069.5/.6/.7's own identical "operate
on data handed in, never own the registry" precedent.

## 9. Relationship to EP-069.5

**None.** Discovery answers "which capability fits this task"; policy
answers "given this one, already-identified capability, what should
happen." This design does not import, call, or depend on anything in
`src/core/capability_discovery/`.

## 10. Relationship to EP-069.6

**Read-only consumer.** Accepts an optional
`CapabilitySecurityAssessment` (produced by a caller having already
called `CapabilitySecurityEngine.assess()`) as one input to the policy
decision. Does not call `CapabilitySecurityEngine` itself (this design
never imports `capability_security` — the caller is responsible for
running the assessment and passing its result in, keeping this
package's own dependency surface minimal and matching the "operate on
data handed in" pattern already used throughout this capability
architecture). Does not modify EP-069.6's data model or engine.

## 11. Relationship to EP-069.7

**Read-only consumer.** Accepts an optional
`CapabilityLifecycleStatus` (produced by a caller having already
queried `CapabilityLifecycleRegistry.status()`) as a second input.
Same "caller supplies it, this package never imports
`capability_lifecycle`" pattern as Section 10. Does not modify
EP-069.7's data model or registry.

## 12. Owner Decisions

**OD1 — Physical package location — APPROVED.**
  - Option A (**Recommended**): `src/core/capability_policy/` —
    scoped explicitly to gating *capability* actions, matching this
    slice's actual, evidenced scope (the "Reused by: every
    EP-069.4-.7 capability execution path" framing).
  - Option B: A more generic `src/core/policy/`, anticipating
    BACKLOG's broader "sensitive/external actions" framing and its
    reuse by unrelated future EPs (EP-128, EP-130).
  - **Consequence of Option A**: avoids naming a package after a
    generality (arbitrary future non-capability actions) this slice
    does not yet serve; a future generalization can rename or
    re-export once a second, non-capability consumer actually exists,
    which is not evidenced today.

**OD2 — Provider/Engine framework vs. a single concrete class — APPROVED.**
  - Option A (**Recommended**): `PolicyProvider` ABC + one concrete
    `DefaultPolicyProvider`, mirroring EP-069.5's/EP-069.6's own
    Provider/Engine pattern (not EP-069.7's single-class pattern).
  - Option B: A single concrete `PolicyRegistry`-style class, mirroring
    EP-069.7's own choice.
  - **Consequence of Option A**: policy *rules* (unlike lifecycle
    *transition semantics*, which have exactly one correct behavior)
    are plausibly something a future EP or operator wants to swap out
    entirely (stricter or looser default posture) without changing the
    orchestration layer — the same justification EP-069.5/.6 gave for
    their own Provider abstraction.

**OD3 — Input contract: required vs. optional EP-069.6/.7 data — APPROVED.**
  - Option A (**Recommended**): `evaluate(capability, security_assessment:
    CapabilitySecurityAssessment | None = None, lifecycle_status:
    CapabilityLifecycleStatus | None = None) -> PolicyDecision`. Both
    extra inputs are optional; the provider degrades to a
    more-conservative decision when either is absent.
  - Option B: Require both, forcing every caller to always run
    discovery+security+lifecycle first.
  - **Consequence of Option A**: does not force a caller to depend on
    EP-069.6/.7 merely to get *any* policy answer, and correctly
    reflects that most capabilities today have neither an assessment
    nor a tracked lifecycle record (nothing populates either in
    production, Section 6) — a mandatory-input design would make this
    engine unusable for every capability that exists today.

**OD4 — Default deterministic rule set — APPROVED WITH MANDATORY
CLARIFICATION.**
  The Owner approved the six-row table exactly as proposed, evaluated
  top-to-bottom, first match wins, with one mandatory semantic
  clarification (restated from Section 7): the first two rows produce
  a **restrictive** result, not an executable one.

  | Condition | Resulting `PolicyLevel` |
  |---|---|
  | `lifecycle_status` is `REVOKED` | `OBSERVE` (restrictive — not executable; see clarification below) |
  | `lifecycle_status` is `DISABLED` | `OBSERVE` (restrictive — not executable; see clarification below) |
  | `security_assessment.overall_risk_level` is `HIGH` | `REQUIRE_APPROVAL` |
  | `security_assessment.overall_risk_level` is `MEDIUM` | `PREPARE` |
  | `capability.source_kind` is not `INTERNAL` and `security_assessment` is `None` | `ANALYZE` |
  | Otherwise (internal, or externally-sourced with a `LOW`/no-finding assessment, and lifecycle `ACTIVE` or untracked) | `EXECUTE` |

  Every `PolicyDecision` also carries a `reasons: tuple[str, ...]`
  explaining which row matched. **Mandatory clarification**: `OBSERVE`
  is a restrictive policy decision under every circumstance that
  produces it, including rows 1 and 2. Mapping `REVOKED`/`DISABLED` to
  `OBSERVE` does **not** mean a revoked or disabled capability is
  executable — it means the opposite. This is not a redesign of the
  table (which is otherwise adopted exactly as originally proposed,
  unchanged) — it is a semantic clarification of what `OBSERVE` means
  wherever it appears, including here. No `DENY` level is introduced;
  no sixth `PolicyLevel` is introduced; the five values and the
  six-row table are otherwise unchanged from the original proposal.

**OD5 — Should `REVOKED` and `DISABLED` map to the same level? — APPROVED.**
  - Option A (**Approved**): Yes, both `OBSERVE` (folded into OD4's
    table) — the smallest coherent slice does not invent a distinction
    BACKLOG never draws. `OBSERVE` here is a restrictive result (per
    OD4's mandatory clarification), not a `DENY` state and not an
    executable one — no sixth category or dedicated `DENY` value is
    introduced for either case.
  - Option B (not chosen): Treat them differently (e.g. `REVOKED` ->
    a level not yet in the five, or a dedicated error instead of a
    `PolicyLevel` at all).
  - **Consequence of Option A**: avoids inventing a sixth category or
    special-casing beyond the five named levels, while still keeping
    `REVOKED`/`DISABLED` unambiguously restrictive via `OBSERVE`'s own
    clarified semantics rather than via a separate `DENY` value.

**OD6 — Should `PolicyLevel` expose a total ordering (e.g. `__lt__`)? — APPROVED (no ordering).**
  - Option A (**Recommended**): No. A plain, unordered `str, Enum`
    with exactly the five named values. Any "restrictiveness" ordering
    lives only inside `DefaultPolicyProvider`'s own rule table (OD4),
    not as a public, comparable contract.
  - Option B: Define and expose an explicit linear ordering across all
    five levels.
  - **Consequence of Option A**: BACKLOG's one-line mention gives no
    evidence for a specific total order (Section 3's own analysis
    shows `REQUIRE_APPROVAL`'s position in the list is ambiguous
    between "most restrictive" and "a checkpoint before `EXECUTE`");
    asserting one publicly would be exactly the kind of
    unevidenced, speculative structure this task's Section 9 instructs
    against.

**OD7 — No enforcement, no wiring — APPROVED.**
  - Option A (**Recommended**): No call site anywhere in this
    repository is modified to actually consult
    `PolicyEngine.evaluate()`; no `src/bootstrap.py`, `config/
    config.yaml`, CLI, or Manager wiring. Mirrors EP-069.5 OD2/
    EP-069.6 OD4/EP-069.7 OD7's identical, now three-times-established
    precedent.
  - Option B: Wire `PolicyEngine` into `ToolExecutionProvider` (the one
    real execution path found, Section 4) as a gate.
  - **Consequence of Option A**: `ToolExecutionProvider` gates `Tool`
    invocations, not `Capability` invocations — the two are unrelated
    identity spaces today (Section 4); wiring them together would be a
    significant, unevidenced architectural leap belonging to a future
    integration EP, not this one.

**OD8 — No persistence or decision audit trail in this slice — APPROVED.**
  - Option A (**Recommended**): `PolicyDecision` is returned to the
    caller and not stored anywhere by this package. A policy-decision
    audit trail (distinct from EP-069.7's lifecycle history) is
    explicitly named in this task's own Section 19 as something to
    "distinguish" — this document distinguishes it by deferring it
    entirely, since nothing yet calls `evaluate()` in production to
    generate decisions worth auditing.
  - Option B: Introduce a decision log now.
  - **Consequence of Option A**: avoids persistence infrastructure
    with no current consumer, matching every sibling package's own
    "in-memory/no persistence until a real need exists" precedent.

**OD9 — No configuration for policy rules — APPROVED.**
  - Option A (**Recommended**): `DefaultPolicyProvider`'s rule table
    (OD4) is hardcoded, not configuration-driven. An operator wanting
    different rules implements a different `PolicyProvider`.
  - Option B: Externalize thresholds into `config/config.yaml`.
  - **Consequence of Option A**: mirrors `DefaultCapabilityDiscoveryProvider`'s
    and `DefaultCapabilitySecurityProvider`'s own precedent (both
    hardcode their own default rules; configurability, if ever needed,
    comes from swapping the *provider*, not from a config file).

## 13. Proposed Architecture

Placement per OD1/OD3: `src/core/capability_policy/`, four files
mirroring EP-069.5's/EP-069.6's own Provider+Engine granularity:

```
src/core/capability_policy/
    __init__.py                     # public API surface
    capability_policy_result.py     # PolicyLevel, PolicyDecision
    capability_policy_provider.py   # PolicyProvider (ABC) + DefaultPolicyProvider, error hierarchy
    capability_policy_engine.py     # PolicyEngine (provider-independent orchestration)
```

## 14. Component Responsibilities

**`PolicyLevel`** (`capability_policy_result.py`)
- A 5-value enum, exact BACKLOG names, in BACKLOG's own listed order:
  `OBSERVE`, `ANALYZE`, `PREPARE`, `EXECUTE`, `REQUIRE_APPROVAL`. No
  ordering/comparison exposed (OD6).

**`PolicyDecision`** (`capability_policy_result.py`)
- `capability_id: str`, `level: PolicyLevel`, `reasons: tuple[str,
  ...]` (which rule(s) produced this level — always at least one
  entry). Frozen dataclass, no behavior.

**`PolicyProvider`** (ABC, `capability_policy_provider.py`)
- `provider_name() -> str`.
- `evaluate(capability: Capability, security_assessment:
  CapabilitySecurityAssessment | None = None, lifecycle_status:
  CapabilityLifecycleStatus | None = None) -> PolicyDecision`
  (abstract).
- `is_available() -> bool` (default `True`).
- Never mutates any input; never calls `CapabilityRegistry`,
  `CapabilitySecurityEngine`, `CapabilityDiscoveryEngine`, or
  `CapabilityLifecycleRegistry`.

**`DefaultPolicyProvider`** (concrete)
- Implements OD4's table exactly, top-to-bottom, first match wins.
  Deterministic; no randomness, no time dependency, no I/O.

**`PolicyEngine`** (`capability_policy_engine.py`)
- Constructed directly with a `PolicyProvider` (default
  `DefaultPolicyProvider`), no Manager (OD2's Provider/Engine choice
  still excludes a Manager layer, consistent with every sibling
  package). `evaluate(...)` delegates unchanged to the configured
  provider.

## 15. Policy Model

Deliberately the simplest model that names the five BACKLOG levels and
nothing more: no principal/subject field (no multi-user access-control
concept exists anywhere in this codebase to attach one to), no
permission-language DSL, no rule-precedence configuration language —
just a fixed, ordered table of conditions (OD4) evaluated
deterministically against three already-existing data shapes
(`Capability`, `CapabilitySecurityAssessment`,
`CapabilityLifecycleStatus`).

## 16. Decision Flow

```
caller already has: capability (EP-069.4)
caller optionally has: security_assessment (from EP-069.6, if run)
caller optionally has: lifecycle_status (from EP-069.7, if tracked)
        |
        v
PolicyEngine.evaluate(capability, security_assessment, lifecycle_status)
        |
        v
PolicyProvider.evaluate(...) -- OD4's table, first match wins
        |
        v
PolicyDecision(capability_id, level, reasons)
```
Per-condition behavior (Section 8 of the calling task, addressed
explicitly): **unknown capability** — not applicable, this design
takes an already-constructed `Capability` object, not an id lookup, so
there is no "unknown" case at this layer (a caller failing to find one
via `CapabilityRegistry` never reaches this engine at all).
**Disabled/revoked** — OD4/OD5 produce `OBSERVE`, a **restrictive**
result; this does **not** mean the capability is executable, and no
future enforcement code may treat it as such (Section 7's mandatory
clarification). **High-risk finding** —
OD4 (`REQUIRE_APPROVAL`). **No policy conflict is possible** — OD4's
table is evaluated top-to-bottom with a strict first-match-wins rule,
so no two rows can ever both apply. **Security information
unavailable** — OD4's `ANALYZE` row (non-`INTERNAL` with no
assessment).

## 17. Enforcement Boundary (Mandatory)

**No enforcement boundary is modified or created in this slice**
(OD7). The only real execution path found anywhere in this repository,
`ToolExecutionProvider`/`ToolEngine` (Section 4), operates on `Tool`,
not `Capability`, and is not touched. Where a future EP should
actually consult `PolicyEngine.evaluate()` before invoking a
`CapabilityBackend` is explicitly identified as future integration
work (Section 32, Deferred Work) — not decided here, since no
`CapabilityBackend` implementation exists yet to attach an enforcement
point to. This applies uniformly to every `PolicyLevel` this engine
can produce, including `OBSERVE`: computing a restrictive decision is
not the same as enforcing one, and this design creates no mechanism
that stops, blocks, or otherwise prevents anything from happening as a
result of any `PolicyDecision` it returns.

## 18. Lifecycle Interaction

Consumes `CapabilityLifecycleStatus` as an optional input (Section
11). `DISABLED` and `REVOKED` both map to `OBSERVE` (OD4/OD5) — a
**restrictive** decision, not an executable one; a revoked or disabled
capability mapping to `OBSERVE` must never be read as meaning that
capability is now executable (Section 7's mandatory clarification).
`ACTIVE` (or untracked, i.e. `None`) does not by itself force a
restrictive level — it is "eligible but not necessarily allowed,"
exactly as this task's own Section 11 framing anticipates: `ACTIVE`
only clears one gate; the security-assessment rows (OD4) still apply
independently. No lifecycle operation is mutated by this package, and
no policy operation mutates lifecycle state.

## 19. Security Interaction

Per this task's own Section 10 options: this design is closest to
**(A) consumes its assessment**, converting it into part of a
decision-level judgment — but does
**not** treat EP-069.6 itself as an
enforcement engine (EP-069.6 remains purely advisory, unchanged); this
design is the one place that *reads* that advisory output and folds it
into an actual decision, per BACKLOG's own explicit assignment of
"approval" to EP-070. This decision is authoritative *as a decision*
(EP-070 is the named decision-maker), but is still not itself
enforcement (Section 17) — nothing in this package stops, blocks, or
authorizes anything from actually happening. `HIGH` risk forces `REQUIRE_APPROVAL`
unconditionally (cannot be overridden by any other input in OD4's
table) — a deliberate, evidenced-by-BACKLOG choice ("least privilege,"
"pausing for human intervention... [when] an action is high-risk").
An absent assessment does **not** default to the most permissive
level for non-`INTERNAL` capabilities (OD4's `ANALYZE` row) — absence
of information is treated conservatively, not optimistically.

## 20. Discovery Interaction

**None** (Section 9). This design does not consume discovered
candidates and does not require discovery as a prerequisite — it
evaluates one already-identified `Capability`, however the caller
obtained it.

## 21. Registry Interaction

**None.** `CapabilityRegistry` is never imported, queried, or modified
(Section 8) — read-only integration was preferred per this task's
Section 13 instruction, and this design goes further: zero
integration at all, matching every sibling package's own established
boundary.

## 22. Error Model

Minimal, per this task's own Section 15 instruction to avoid
speculative hierarchies:
- `CapabilityPolicyError(Exception)` — root, matching the now
  four-times-established convention (`CapabilityError`,
  `CapabilityDiscoveryError`, `CapabilitySecurityError`,
  `CapabilityLifecycleError`).
- `CapabilityPolicyProviderError(CapabilityPolicyError)` — raised only
  if `evaluate()` is called with `capability=None` (mirroring
  EP-069.6's identical, sole validation case).

No "policy denied" error exists — a restrictive `PolicyLevel` (e.g.
`OBSERVE`) is a **successful, valid decision result**, not a failure;
this design never raises to signal a restrictive outcome, only to
signal genuinely invalid input.

## 23. Configuration

**None required** (OD9). Deferred explicitly, not omitted by
oversight.

## 24. Persistence

**None required** (OD8). `PolicyEngine`/`DefaultPolicyProvider` are
fully stateless — unlike `CapabilityLifecycleRegistry` (EP-069.7),
which genuinely holds state because remembering history is its
purpose, this engine computes a fresh answer from its inputs every
call, with nothing to remember between calls.

## 25. CLI / Bootstrap

**Neither required** (OD7). Deferred to whatever future EP actually
wires a real enforcement point.

## 26. Audit / Observability

Distinguished explicitly from EP-069.7's lifecycle history (per this
task's Section 19 instruction): no decision log/audit trail is
introduced in this slice (OD8). `PolicyEngine.evaluate()` logs at
`DEBUG` the capability id and resulting `PolicyLevel` only (mirroring
`CapabilityDiscoveryEngine`'s/`CapabilitySecurityEngine`'s own
identical, minimal logging convention) — never the full `reasons`
text or any assessment/lifecycle detail, to avoid incidentally logging
potentially sensitive detail at a default log level.

## 27. Data Flow

See Section 16 (identical diagram; this task requests the same content
under two section headings, both reproduced for completeness of
cross-reference).

## 28. Thread Safety

**Not required, and not added.** `PolicyEngine`/`DefaultPolicyProvider`
hold no mutable state between calls (Section 24) — every `evaluate()`
call is a pure function of its three arguments, so no lock, no shared
counter, and no concurrency architecture of any kind is needed, unlike
`CapabilityLifecycleRegistry`'s genuine, evidenced need for one
(EP-069.7 holds real, accumulated state; this package does not).

## 29. Test Strategy

New, isolated package: `tests/EP070/` (STEP 2), matching this
repository's own convention for a base (non-`.N`) EP number (e.g.
`tests/EP069/`) — `tests/EP070/__init__.py`, `tests/EP070/
test_capability_policy_engine.py`.

- **Core policy behavior**: each row of OD4's table individually
  triggered and asserted (six distinct scenarios).
- **Allow/deny-equivalent behavior**: since this model has no literal
  "deny," verify instead that `REQUIRE_APPROVAL`/`OBSERVE` (both
  restrictive outcomes, per the mandatory clarification) are
  produced exactly for their intended trigger conditions and no
  others, and that neither is ever produced for an `EXECUTE`-eligible
  scenario.
- **Precedence**: construct a `Capability`/assessment/status
  combination matching *two* of OD4's rows simultaneously (e.g.
  `REVOKED` **and** `HIGH` risk) and assert the **first** matching row
  (`OBSERVE`, from the `REVOKED` check) wins, proving the top-to-bottom
  precedence is real, not incidental.
- **Default behavior**: an `INTERNAL` capability with no assessment
  and no tracked lifecycle status (both `None`) yields `EXECUTE`.
- **Lifecycle interaction**: `DISABLED` and `REVOKED` each
  independently tested.
- **Security interaction**: `HIGH`, `MEDIUM`, `LOW`, and "no
  assessment" each independently tested for a non-`INTERNAL`
  capability.
- **Discovery/registry interaction**: negative tests confirming no
  import of `capability_discovery`/`capability_registry` anywhere in
  the package (the same static import-line technique independently
  validated sound in `EP069_6_ARCHITECTURE_AUDIT.md` and
  `EP069_7_ARCHITECTURE_AUDIT.md`).
- **Invalid input**: `evaluate(None, ...)` raises
  `CapabilityPolicyProviderError`.
- **Deterministic results**: two identical calls produce
  `PolicyDecision`s that compare equal.
- **Architectural boundaries**: no mutation of `Capability`; engine
  delegates to its configured provider without duplicating rule logic
  (a recording fake provider, mirroring EP-069.5's/EP-069.6's own test
  technique).
- **Regression**: re-run `EP069_7`, `EP069_6`, `EP069_5`, `EP069_4`,
  `EP069_3`, `EP069_2`, `EP069`, and `EP056` unchanged.
- **Mandatory `OBSERVE` semantics (Owner-required)**: in addition to
  the precedence and lifecycle-interaction tests above, the suite must
  explicitly and individually verify: (1) `REVOKED` produces exactly
  `OBSERVE`; (2) `DISABLED` produces exactly `OBSERVE`; (3) `OBSERVE`
  is documented/asserted as a restrictive result in the test suite's
  own docstrings/comments, not merely produced incidentally; (4) no
  test, helper, or comment anywhere in the suite characterizes
  `OBSERVE` as execution authorization, "allowed," or equivalent to
  the capability being executable; (5) `PolicyLevel` contains exactly
  the five approved values — a test asserts its member count and
  membership, proving no `DENY` or sixth value was introduced; (6) no
  test constructs, calls, imports, or otherwise exercises any
  enforcement, wiring, bootstrap, config, or CLI integration — the
  suite only ever constructs `PolicyEngine`/`DefaultPolicyProvider`
  directly and calls `evaluate()`.

Test counts are not inflated — each behavioral distinction above maps
to exactly one focused test method (loop-based boundary/dependency
checks, if used, are reconciled explicitly, matching this exercise's
own now-established transparency convention).

## 30. Exact File Forecast

**NEW:**
- `src/core/capability_policy/__init__.py` — public API surface.
- `src/core/capability_policy/capability_policy_result.py` —
  `PolicyLevel`, `PolicyDecision`.
- `src/core/capability_policy/capability_policy_provider.py` —
  `PolicyProvider` (ABC), `DefaultPolicyProvider`, error hierarchy.
- `src/core/capability_policy/capability_policy_engine.py` —
  `PolicyEngine`.
- `tests/EP070/__init__.py`
- `tests/EP070/test_capability_policy_engine.py`

**MODIFIED:**
- `src/modules/test_module.py` (+1 import line, the standard,
  repository-wide test-registration convention every prior EP also
  required — the exact minimal change, nothing else in this file
  touched).

**UNTOUCHED:**
- `src/core/capability/*` (EP-069.4) — all four files.
- `src/core/capability_discovery/*` (EP-069.5) — all four files.
- `src/core/capability_security/*` (EP-069.6) — all four files.
- `src/core/capability_lifecycle/*` (EP-069.7) — all three files.
- `src/bootstrap.py`, `config/config.yaml`.
- `src/core/tool/*` (including `tool_execution_provider.py`),
  `src/core/plugins/*`, `src/core/planning/*`, `src/core/agent/*`,
  `src/core/plan_execution/*`.
- `src/skills/capability_registry/skill.py` (EP-056).
- `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`,
  `docs/architecture/designs/ROADMAP_070_138_REBUILD_PROPOSAL.md`,
  `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `VERSION`,
  `PROJECT_MANIFEST.md`, every `docs/architecture/audits/*` file —
  explicitly excluded from STEP 1 by this task's own Section 26.

## 31. Scope-Creep Guard — "EP-070 MUST NOT IMPLEMENT"

- A generic, system-wide security or authorization framework (only
  capability-action policy, per OD1's evidenced scope).
- A generic policy engine reused by non-capability domains (EP-128/
  EP-130's own future integration is explicitly deferred, Section
  32).
- Any replacement of, or new field on, `Capability`,
  `CapabilityRegistry`, `CapabilitySecurityAssessment`, or
  `CapabilityLifecycleStatus`/`CapabilityLifecycleRegistry`.
- Any call into `CapabilityRegistry`, `CapabilityDiscoveryEngine`,
  `CapabilitySecurityEngine`, or `CapabilityLifecycleRegistry` from
  this package (the caller supplies their outputs; this package never
  fetches them itself).
- Any actual enforcement, blocking, pausing, or human-notification
  mechanism for `REQUIRE_APPROVAL` — this remains a computed label
  only.
- Any wiring into `ToolExecutionProvider`, `ToolEngine`,
  `src/bootstrap.py`, `config/config.yaml`, or any CLI surface.
- A `PolicyManager`, config-driven provider selection, or any
  persistence/decision-audit-log mechanism.
- Credential handling of any kind (EP-071's future job).
- Capability execution, sandboxing, or rollback of any kind (EP-072's
  future job).
- A `DENY` `PolicyLevel`, any sixth `PolicyLevel`, or any permission
  DSL — `OBSERVE` is the sole restrictive value this design produces
  for `REVOKED`/`DISABLED`, and it is not a stand-in for a missing
  `DENY` (Section 7/12, OD4/OD5's mandatory clarification).
- Any code, comment, or test that treats `OBSERVE` as execution
  authorization, as "allow but monitor," or as evidence that a
  `REVOKED`/`DISABLED` capability may be executed.

## 32. Deferred Work

- Wiring `PolicyEngine.evaluate()` into a real enforcement point —
  deferred until a concrete `CapabilityBackend` and its invocation
  path exist (a future EP's own STEP 1 territory). **Whatever future
  EP builds this must interpret `OBSERVE` as restrictive and must not
  treat it as execution authorization** (Section 7); this document
  does not design that future enforcement layer, only states the
  constraint it must honor.
- A human-approval workflow/notification mechanism for
  `REQUIRE_APPROVAL` — deferred; needs a UI/notification surface that
  does not exist today.
- A policy-decision audit trail — deferred (OD8); a future EP's own
  scope once real decisions are being made in production.
- Reuse of `PolicyEngine` by non-capability domains (EP-128, EP-130) —
  deferred until those far-future EPs' own STEP 1s scope it; no
  placeholder generalization is introduced now (OD1).
- A richer policy model (principals, precedence configuration, a
  rule DSL) — deferred; nothing in the current, single-slice use case
  justifies it.

No placeholder types for any of the above are introduced now,
consistent with the identical, explicit Non-Goal already established
by EP-069.6's and EP-069.7's own audited designs.

## 33. Acceptance Criteria

1. `PolicyLevel`, `PolicyDecision`, `PolicyProvider`,
   `DefaultPolicyProvider`, `PolicyEngine`, and the two-class error
   hierarchy all exist and are exported from
   `src/core/capability_policy/__init__.py`.
2. `DefaultPolicyProvider.evaluate()` reproduces OD4's table exactly,
   verified by one test per row plus one precedence test proving
   first-match-wins.
3. `evaluate(None, ...)` raises `CapabilityPolicyProviderError`.
4. No import of `capability_registry`, `capability_backend`,
   `capability_discovery`, `planning`, `agent`, `bootstrap`, or
   `config` anywhere in the package.
5. No mutation of any `Capability`, `CapabilitySecurityAssessment`, or
   `CapabilityLifecycleStatus` instance passed in.
6. `EP069_7`, `EP069_6`, `EP069_5`, `EP069_4`, `EP069_3`, `EP069_2`,
   `EP069`, and `EP056` all remain green, unchanged in count, after
   STEP 2.
7. `src/bootstrap.py`, `config/config.yaml`, and every EP-069.4/.5/.6/.7
   file are byte-identical before and after STEP 2.
8. Two identical `evaluate()` calls produce equal `PolicyDecision`
   values (determinism).
9. `PolicyLevel` contains exactly five members (`OBSERVE`, `ANALYZE`,
   `PREPARE`, `EXECUTE`, `REQUIRE_APPROVAL`) — no `DENY`, no sixth
   value — verified by an explicit membership/count test.
10. `REVOKED` and `DISABLED` each independently, verifiably produce
    `OBSERVE`, and no test, docstring, or comment anywhere in the
    shipped test suite or source characterizes `OBSERVE` as execution
    authorization or treats a `REVOKED`/`DISABLED` capability as
    executable.

## 34. Open Questions

- OD4's rule table is now approved as final (Section 12) — no longer
  open. Resolved.
- Whether `REQUIRE_APPROVAL` is conceptually "more" or "less"
  permissive than `EXECUTE` remains genuinely unresolved by any
  repository document (Section 3) — OD6 sidesteps this by exposing no
  ordering at all (also now approved, Section 12), but a future EP
  that *does* need to compare levels (e.g. "is this at least as
  permissive as that") will need this question resolved explicitly at
  that time. This does not block STEP 2, since no ordering is exposed
  or relied upon by this slice.

## 35. Final Architectural Verdict

EP-070, scoped as a capability policy-decision slice, is the smallest
architecture that fills the specific, four-times-independently-named
gap EP-069.4 through EP-069.7 each left for it, without retroactively
violating any of their own established boundaries and without
inventing enforcement infrastructure this repository has nothing to
attach it to yet. All nine Owner Decisions are now approved, OD4 with
one mandatory semantic clarification: `OBSERVE` is a restrictive
policy decision, never execution authorization, including when
produced by a `REVOKED` or `DISABLED` lifecycle status. This
clarification changes no code, no table row, and no `PolicyLevel`
value — it fixes the meaning of an already-approved outcome for every
future reader of this document.

---

## EP-070 STEP 1 — CORRECTED — DESIGN PROPOSED — READY FOR OWNER APPROVAL
