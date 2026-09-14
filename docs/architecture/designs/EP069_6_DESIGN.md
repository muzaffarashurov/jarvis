# EP-069.6 — External Capability Security & Supply-Chain Trust (Advisory Assessment Slice)

STEP 1: Architecture Discovery & Design

Status: DESIGN PROPOSED — awaiting Owner Decision approval before STEP 2

---

## 1. Scope Verification — does EP-069.6 exist as a defined planning candidate?

Yes, confirmed directly from the current, canonical repository state:

- `docs/BACKLOG.md` (lines 3165-3172): **"EP-069.6 — External Capability
  Security & Supply-Chain Trust" (HIGH).** *"Source-provenance checks,
  dependency/package inspection, permission mapping (filesystem/
  network/credential/process access), and sandboxing/isolation policy
  for anything not written by Jarvis itself. Explicitly forbids an
  unrestricted 'download -> pip install -> execute' path for local
  GitHub projects; every external capability is untrusted until
  inspected and approved under EP-070's policy engine."* This is the
  single authoritative scope statement.
- `docs/architecture/JARVIS_ROADMAP.md` (lines 214, 2524) references
  EP-069.6 consistently with the same subject, still planning-only as
  of the current "## Current" entry (EP-069.5).
- `docs/architecture/designs/ROADMAP_070_138_REBUILD_PROPOSAL.md`
  positions EP-069.6 in its architecture diagram (Section 5) between
  the Capability/Tool Registry and Credential Isolation (EP-071), and
  — critically — its own "Unresolved questions" section (§10, item 2)
  states verbatim: *"EP-069.4–.7 are scoped narrowly ... to avoid
  becoming a fifth 'mega-EP' under EP-069; a future STEP 1 may find
  that EP-069.6 (security) is large enough to deserve its own
  top-level EP number rather than a sub-package — left as a judgment
  call for that STEP 1."* **This STEP 1 is that judgment call**
  (Section 13, Owner Decision OD1).
- No `docs/architecture/designs/EP069_6_DESIGN.md` exists yet, and no
  `docs/architecture/audits/EP069_6_*` exists.

**Confirmed: EP-069.6 is a valid, well-defined next planning
candidate**, with one explicitly acknowledged, still-open structural
question (its own possible renumbering) inherited from the document
that created it. This STEP 1 proceeds and resolves that question as
Owner Decision OD1.

## 2. Title

EP-069.6 — External Capability Security & Supply-Chain Trust (this
STEP 1 scopes an **advisory assessment slice** only; see Section 7,
Non-Goals, and Owner Decision OD1/OD6 for why the full bullet's scope
is not built in one pass).

## 3. Problem Statement

`docs/BACKLOG.md`'s own bullet names four distinct technical
responsibilities in one sentence: (a) source-provenance checks, (b)
dependency/package inspection, (c) permission mapping, and (d)
sandboxing/isolation policy — for "anything not written by Jarvis
itself." Direct inspection of the current repository shows that
**none of the infrastructure any of these four responsibilities would
need to act on yet exists**:

- **No concrete `CapabilityBackend` implementation exists anywhere**
  (`EP069_4_DESIGN.md` Owner Decision D4 — zero shipped; confirmed
  still zero by `grep -rn "(CapabilityBackend)" src/` matching only
  the ABC's own declaration). There is no "download," no "pip
  install," and no "execute" step in this codebase for *anything* to
  forbid yet — the exact forbidden pattern BACKLOG names
  ("download -> pip install -> execute") has no corresponding code
  path to intercept.
- **EP-070 (Policy, Permissions & Human Approval Engine) does not
  exist** — confirmed absent again in this STEP 1 (Section 4) exactly
  as EP-069.4's and EP-069.5's own STEP 1 investigations found. The
  BACKLOG bullet's own final clause — "approved under EP-070's policy
  engine" — names the actual approval authority as a *different*,
  unimplemented EP. EP-069.6 is not that approval authority.
- **No dependency/package scanning tool is a project dependency**
  (`requirements.txt` contains no `pip-audit`, `bandit`, `safety`, or
  equivalent) and **no sandboxing/isolation mechanism exists anywhere**
  in `src/` (confirmed by repository-wide search, Section 4).

This means the BACKLOG bullet, read as one indivisible unit of work,
describes a security *enforcement* pipeline with no artifact yet to
enforce anything on, and names an approval authority (EP-070) that is
itself unimplemented. Building (b) real dependency/package inspection
or (d) real sandboxing today would mean inventing speculative
infrastructure with nothing genuine to inspect or isolate — directly
violating this task's own "no speculative abstractions" and "no
unnecessary runtime wiring" principles (Section 5). The only
genuinely buildable, non-speculative slice today is a **declarative,
advisory assessment** of the metadata EP-069.4's `Capability` model
already carries (`source`, `source_kind`, `trust_level`,
`required_permissions`) — matching exactly how EP-069.4 itself shipped
a `CapabilityBackend` contract with zero real backends, and EP-069.5
shipped a ranking engine with zero real callers, both by explicit,
approved design.

## 4. Current Architecture (discovery findings)

- `src/core/capability/` (EP-069.4, finalized, unmodified):
  `Capability.source` (free-text provenance), `Capability.source_kind`
  (`INTERNAL`/`LOCAL_CLI`/`REST_API`/`BROWSER_SERVICE`),
  `Capability.trust_level` (`TRUSTED_INTERNAL`/`TRUSTED_CONFIGURED`/
  `UNVERIFIED`), `Capability.required_permissions` (free-form
  `tuple[str, ...]` tags, per `EP069_4_DESIGN.md` Owner Decision D5 --
  "no structured permission taxonomy," deliberately unconstrained
  strings). These four fields are the *only* security-relevant data
  that exists anywhere in this codebase today.
- `src/core/capability_discovery/` (EP-069.5, finalized, unmodified):
  `CapabilityDiscoveryEngine`/`DefaultCapabilityDiscoveryProvider`
  read `trust_level` as a ranking signal only, never an enforcement
  decision (`EP069_5_DESIGN.md` Section 5: "'Ranking by trust' is not
  'enforcing trust.'"). No security assessment of any kind is
  performed there.
- **No policy/approval engine exists**: `grep -rn "class.*Policy"
  src/` still matches only `RestartPolicy`
  (`src/core/processes/process.py`, unrelated process-supervision
  concept) — re-confirmed in this STEP 1, unchanged since EP-069.4's
  and EP-069.5's own findings.
- **No credential/secret management exists**: no `src/core/
  credential*` or equivalent.
- **No sandboxing/isolation mechanism exists**: `grep -rli "sandbox"
  src/` matches only test-environment "headless sandbox" references
  in `src/skills/desktop/windows_backend.py` (an unrelated,
  display-availability concept), never a capability-isolation
  mechanism.
- **No dependency/package scanning tool is present**: `requirements.txt`
  contains no security-scanning library.
- **No concrete `CapabilityBackend` exists** (Section 3) — nothing
  downloads, installs, or executes an external capability today.

## 5. Existing Implementation Evidence — What EP-069.6 Must NOT Duplicate

- **Must not duplicate `Capability`'s own field set** — `source`,
  `source_kind`, `trust_level`, `required_permissions` already exist
  and are read-only inputs to this EP's assessment logic, never
  redefined or extended (EP-069.4 boundary, Section 12).
- **Must not duplicate `CapabilityDiscoveryEngine`'s ranking
  responsibility** — discovery ranks by fit/trust/cost for *task
  matching*; this EP assesses *security risk*, a different question
  answered for a different consumer (a future policy gate, not
  Planning/Agents).
- **Must not duplicate EP-070's future approval-decision
  responsibility** — this EP produces an advisory risk
  classification and a list of findings; it never grants, denies, or
  enforces anything. "Assessing risk" is not "approving execution."
- **Must not duplicate EP-071's future credential-isolation
  responsibility** — no credential/secret is read, stored, or
  evaluated anywhere in this EP.
- **Must not duplicate EP-072's future execution/rollback
  responsibility** — no capability is invoked, sandboxed, or rolled
  back by this EP.
- **Must not duplicate EP-069.7's future lifecycle/registration
  responsibility** — this EP does not register, version, or revoke a
  capability.

## 6. Goals

- Define a `CapabilitySecurityAssessment` data model (a risk
  classification plus a list of specific findings) that a future
  EP-070 policy engine, or any other future consumer, can read to make
  an actual approval decision — without this EP making that decision
  itself.
- Define a `CapabilitySecurityProvider` structural contract (ABC),
  following this repository's established Provider/Engine pattern
  (as used by `capability_discovery`, `planning`, `tool`), with
  exactly one concrete, deterministic, non-AI, built-in provider --
  `DefaultCapabilitySecurityProvider` -- that assesses a `Capability`'s
  *already-declared* metadata only (no external tool invocation, no
  network access, no filesystem access).
- Ship a `CapabilitySecurityEngine` matching `CapabilityDiscoveryEngine`'s
  own minimal, provider-independent orchestration shape.
- Explicitly and honestly resolve, rather than silently ignore, the
  rebuild proposal's own flagged "is EP-069.6 too big" question
  (Owner Decision OD1) and the resulting scope boundary between what
  is genuinely buildable today and what depends on infrastructure that
  does not exist yet (Owner Decision OD6).
- Leave `Capability`, `CapabilityRegistry`, `CapabilityBackend`
  (EP-069.4), and every EP-069.5 component completely unmodified.

## 7. Non-Goals

- **No real dependency/package inspection** — no integration with
  `pip-audit`, `bandit`, `safety`, or any equivalent tool; no parsing
  of a downloaded project's `requirements.txt`/manifest. There is no
  "download" step anywhere in this codebase for such a tool to act on
  (Section 3). A future EP, once a local-CLI/GitHub-project
  `CapabilityBackend` exists, is the natural home for this (Section
  22).
- **No real sandboxing/isolation mechanism** — no process isolation,
  container, `seccomp`, or filesystem-jail implementation of any kind.
  No infrastructure exists today to isolate, and inventing one
  speculatively is explicitly out of scope (Section 5's "no
  unnecessary runtime wiring").
- **No binding approve/reject/execution-authorization decision** —
  this EP's output is advisory (a risk classification plus findings)
  only. Actual approval remains EP-070's named, future, exclusive
  responsibility, per BACKLOG's own text.
- **No policy-engine integration** — EP-070 does not exist; this EP
  makes no call into it and defines no interface *for* it beyond the
  plain `CapabilitySecurityAssessment` data shape a future EP-070
  could choose to read.
- **No credential/secret handling of any kind** (EP-071's future job).
- **No capability execution, invocation, or rollback of any kind**
  (EP-072's future job; `CapabilityBackend.invoke()` is never called).
- **No capability registration, mutation, or lifecycle action**
  (EP-069.7's future job).
- **No modification to `Capability`, `CapabilityRegistry`,
  `CapabilityBackend`, or any EP-069.5 file** — Section 12.
- **No `src/bootstrap.py` or `config/config.yaml` wiring, no CLI
  surface, no Manager** — mirroring EP-069.5's own immediate
  precedent (Owner Decision OD4) exactly, for the identical reason: no
  live consumer of this engine exists yet.
- **No renumbering of EP-069.6 to a new top-level EP number in this
  STEP 1** — Owner Decision OD1 recommends keeping the current number
  while narrowing the *content* scope; an actual renumbering, if the
  Owner prefers it, is itself a documentation-wide change larger than
  this STEP 1's own mandate.

## 8. Proposed Architecture

Placement: `src/core/capability_security/`, mirroring
`src/core/capability_discovery/`'s own naming and placement pattern
exactly (Section 13, Owner Decision OD3). Three files -- one fewer
than `capability_discovery`'s four, since there is no separate
"result" concern distinct enough from the assessment model itself to
warrant a fourth file (the assessment *is* the result; see Section 9):

```
src/core/capability_security/
    __init__.py                      # public API surface
    capability_security_result.py    # plain data: SecurityRiskLevel, SecurityFinding, CapabilitySecurityAssessment
    capability_security_provider.py  # CapabilitySecurityProvider (ABC) + DefaultCapabilitySecurityProvider, error hierarchy
    capability_security_engine.py    # CapabilitySecurityEngine (provider-independent orchestration)
```

No `capability_security_manager.py` -- identical reasoning to
EP-069.5's own Owner Decision OD2: exactly one concrete provider, no
live consumer, so a config-driven Manager would add real but currently
unused complexity (Owner Decision OD4).

## 9. Component Responsibilities

**`SecurityRiskLevel`** (`capability_security_result.py`)
- A small enum: `LOW`, `MEDIUM`, `HIGH`. Deliberately no `CRITICAL`
  tier and no numeric score (mirroring EP-069.4's own Owner Decision
  D6 rationale for `CapabilityTrustLevel`: a finer-grained or numeric
  scale implies a scoring *algorithm* sophistication this advisory
  slice does not attempt, and would prejudge a future, more complete
  EP-069.6 phase's own design).

**`SecurityFinding`** (`capability_security_result.py`)
- A single, specific concern: `category` (a short string, e.g.
  `"missing_provenance"`, `"trust_source_mismatch"`,
  `"high_risk_permission"`), `message` (human-readable explanation),
  `risk_level` (this finding's own contribution, `SecurityRiskLevel`).
  Plain, frozen dataclass -- no behavior.

**`CapabilitySecurityAssessment`** (`capability_security_result.py`)
- The outcome of assessing one `Capability`: `capability_id`,
  `overall_risk_level` (the highest `risk_level` among `findings`, or
  `LOW` if `findings` is empty), `findings: list[SecurityFinding]`.
  **Advisory only** -- carries no `approved`/`rejected` field of any
  kind (Owner Decision OD2); a future EP-070 or other policy consumer
  is expected to read this shape and make its own decision.

**`CapabilitySecurityProvider`** (ABC, `capability_security_provider.py`)
- `provider_name() -> str` (identity, no network/expensive work).
- `assess(capability: Capability) -> CapabilitySecurityAssessment`
  (abstract). Takes one already-fetched `Capability` -- never queries
  a live `CapabilityRegistry` itself, mirroring
  `CapabilityDiscoveryProvider`'s own identical convention.
- `is_available() -> bool` (default `True`, matching every sibling
  provider's own default).

**`DefaultCapabilitySecurityProvider`** (concrete,
`capability_security_provider.py`)
- Performs exactly three deterministic, declarative-metadata-only
  checks, each producing zero or one `SecurityFinding`:
  1. **Missing provenance**: `source_kind != INTERNAL` and `source`
     is blank -> `MEDIUM` finding (`"missing_provenance"`).
  2. **Trust/source inconsistency**: `source_kind != INTERNAL` and
     `trust_level == TRUSTED_INTERNAL` -> `HIGH` finding
     (`"trust_source_mismatch"`) -- an externally sourced capability
     cannot legitimately claim the internal trust tier.
  3. **High-risk permission tag on a non-internal capability**:
     `source_kind != INTERNAL` and any tag in `required_permissions`
     case-insensitively contains one of a small, fixed, documented set
     of substrings (Owner Decision OD5) -> `HIGH` finding
     (`"high_risk_permission"`, naming the matched tag).
- `overall_risk_level` is the maximum `risk_level` across all
  triggered findings, or `LOW` when none trigger.
- Performs no network access, no filesystem access beyond reading the
  in-memory `Capability` object's own fields, and no external tool
  invocation of any kind.

**`CapabilitySecurityEngine`** (`capability_security_engine.py`)
- `assess(capability: Capability) -> CapabilitySecurityAssessment`:
  delegates directly to its configured provider (constructed directly,
  defaulting to `DefaultCapabilitySecurityProvider`, no Manager --
  identical shape to `CapabilityDiscoveryEngine`).
- Never mutates `capability`. Never queries or mutates a
  `CapabilityRegistry` -- callers wanting to assess every registered
  capability iterate `registry.list()` themselves and call `assess()`
  per entry; this EP does not ship a batch/registry-driven convenience
  method, to avoid an unrequested, speculative public-API addition
  (Section 5).

## 10. Data / Control Flow

```
caller (a future EP-070 policy gate, or a direct test/CLI caller)
    |
    v
CapabilitySecurityEngine.assess(capability)
    |
    v
CapabilitySecurityProvider.assess(capability)
    |
    | 1. check missing provenance
    | 2. check trust/source inconsistency
    | 3. check high-risk permission tags
    v
CapabilitySecurityAssessment(capability_id, overall_risk_level, findings)
```

No step performs network I/O, filesystem access beyond the in-memory
object, external tool invocation, or AI/LLM inference. No step
mutates `capability` or any registry.

## 11. Public API / Contracts

Exported from `src/core/capability_security/__init__.py`:
`SecurityRiskLevel`, `SecurityFinding`, `CapabilitySecurityAssessment`,
`CapabilitySecurityProvider`, `DefaultCapabilitySecurityProvider`,
`CapabilitySecurityEngine`, and this package's own error hierarchy
(Section 12) -- mirroring `src/core/capability_discovery/__init__.py`'s
own export-everything-public convention exactly.

## 12. Error Handling

A package-root `CapabilitySecurityError(Exception)`, matching
`CapabilityError`/`CapabilityDiscoveryError`'s now-universal
convention in this repository, with:
- `CapabilitySecurityProviderError(CapabilitySecurityError)` -- raised
  only if `assess()` is called with a `capability` that is `None` (a
  caller error; there is no numeric/count parameter in this EP's
  contract analogous to `max_results`, so this is the sole validation
  case).

`CapabilitySecurityEngine.assess()` never swallows a provider
exception -- propagates unchanged, matching
`CapabilityDiscoveryEngine.discover()`'s own documented behavior.

## 13. Owner Decisions

**OD1 — Should EP-069.6 be renumbered to a new top-level EP, per the
rebuild proposal's own explicitly flagged open question?**
`docs/architecture/designs/ROADMAP_070_138_REBUILD_PROPOSAL.md` §10
item 2 explicitly leaves this as "a judgment call for that STEP 1" --
this STEP 1.
  - Option A (**Recommended**): Keep the current `EP-069.6` number.
    Narrow this STEP 1's own *content* scope to the advisory
    assessment slice described above (Sections 6-9), explicitly
    deferring the two genuinely large, infrastructure-dependent
    responsibilities (real dependency/package scanning, real
    sandboxing) rather than renumbering. This mirrors exactly how
    EP-069 itself was already split into .1 through .7 to avoid one
    "mega-EP" -- the same technique (splitting scope) is applied
    *within* EP-069.6 rather than by inventing a new top-level EP
    number, which would itself require a documentation-wide
    renumbering exercise (BACKLOG.md, JARVIS_ROADMAP.md, and every
    cross-reference to EP-069.6/.7 and EP-070-074) far larger than
    this STEP 1's own mandate.
  - Option B: Renumber EP-069.6 to a new top-level EP (e.g. reserving
    a number in the EP-138+ range) and leave `EP-069.6` retired/empty,
    matching the precedent the rebuild proposal itself used for
    merged/retired placeholders (EP-099, EP-129, EP-132).
  - **Consequence of Option A**: a future EP-069.6.x (or a later
    top-level EP once genuinely justified) remains available for the
    deferred dependency-scanning/sandboxing work, without this STEP 1
    committing to that structure prematurely.

**OD2 — Advisory assessment vs. binding approve/reject decision.**
  - Option A (**Recommended**): `CapabilitySecurityAssessment` is
    advisory only -- a risk classification and a list of findings,
    with no `approved`/`rejected`/`allowed` field of any kind. A
    future EP-070 (or any other policy consumer) reads this shape to
    make its own binding decision.
  - Option B: `CapabilitySecurityAssessment` includes a binding
    decision field this EP itself computes (e.g. `decision:
    Literal["ALLOW", "DENY"]`).
  - **Consequence of Option A**: preserves BACKLOG's own explicit
    text ("approved under EP-070's policy engine") -- EP-069.6 never
    encroaches on EP-070's named authority. Option B would make
    EP-069.6 a de facto policy engine before EP-070 exists, duplicating
    a responsibility BACKLOG assigns elsewhere.

**OD3 — Physical package location.**
  - Option A (**Recommended**): `src/core/capability_security/`,
    mirroring `src/core/capability_discovery/`'s own established
    physical convention exactly (Core Level-1 placement despite the
    conceptual Level-2/3 tension already discussed and resolved
    identically in `EP069_5_DESIGN.md` Owner Decision OD1).
  - Option B: A new top-level `src/engines/` or `src/security/`
    directory.
  - **Consequence of Option A**: zero new top-level directory
    convention invented, consistent with EP-069.4's and EP-069.5's own
    precedent.

**OD4 — Composition-root wiring.**
  - Option A (**Recommended**): No `CapabilitySecurityManager`, no
    `src/bootstrap.py` wiring, no `config/config.yaml` keys, no CLI
    surface -- identical reasoning and shape to `EP069_5_DESIGN.md`
    Owner Decision OD2 (no live consumer exists yet; EP-070 does not
    exist to consume this either).
  - Option B: Full Provider/Engine/Manager wiring plus bootstrap/
    config/CLI, matching the *older* Core subsystems' own precedent.
  - **Consequence of Option A**: consistent with the two most recent,
    most directly relevant precedents (EP-069.4 and EP-069.5 both
    chose this).

**OD5 — Starter high-risk permission-tag keyword list.**
Since `required_permissions` is a free-form `tuple[str, ...]`
(EP-069.4 Owner Decision D5, no structured taxonomy), the default
provider's third check (Section 9) needs a concrete, documented
substring list to match against. Recommended starter set (case-
insensitive substring match): `"credential"`, `"secret"`, `"network"`,
`"filesystem.write"`, `"process"`, `"shell"`. This is a genuine,
consequential implementation choice (affects false positive/negative
rates) with no single objectively correct answer -- flagged
explicitly rather than silently chosen. The Owner may adjust this
list; STEP 2 will implement exactly whatever list is approved here.

**OD6 — Should placeholder types for the deferred responsibilities
(dependency/package inspection, sandboxing/isolation policy) be
shipped now, even if unimplemented?**
  - Option A (**Recommended**): No. Ship nothing for these two
    responsibilities beyond the prose description in Section 22
    (Deferred Items). Adding an empty `DependencyScanResult` or
    `SandboxPolicy` type today, with no real logic behind it, is
    exactly the "speculative abstraction" Section 5 instructs against.
  - Option B: Ship empty/stub data types now as forward-compatible
    placeholders, for a future EP to fill in.
  - **Consequence of Option A**: a future EP that actually builds
    dependency scanning or sandboxing designs its own data shapes
    against real requirements, unconstrained by a guessed-at stub
    shipped years earlier with no real usage to validate it.

## 14. Security / Trust Implications

This EP's entire purpose is security-adjacent, so this section
records what it does *not* do as carefully as what it does: it reads
already-declared, in-memory `Capability` metadata only; performs no
network access, no filesystem access, no subprocess execution, no
credential handling; and makes no binding decision (Owner Decision
OD2). It cannot be bypassed maliciously because it is not yet a gate
of anything -- nothing calls it, and no execution path exists for it
to have guarded even if something did. The actual security boundary
work (real inspection, real sandboxing, real approval enforcement)
remains EP-069.6's own deferred future scope (Section 22), EP-070's,
EP-071's, and EP-072's responsibility respectively -- none of which
exist in this repository today.

## 15. Configuration Requirements

Per Owner Decision OD4's recommended option: **none** in this EP.

## 16. Composition-Root Implications

Per Owner Decision OD4's recommended option: **none** --
`src/bootstrap.py` is not touched by this design.

## 17. Logging Requirements

`CapabilitySecurityEngine.assess()` logs at `DEBUG` the capability id
and resulting `overall_risk_level` only -- never the full finding
messages or the capability's own `source`/`required_permissions`
values, to avoid incidentally logging potentially sensitive
provenance/permission detail at a default log level (mirroring
`EP069_5_DESIGN.md` Section 17's identical caution).

## 18. Testing Strategy

New, isolated package: `tests/EP069_6/` (STEP 2), matching the
established convention (`tests/EP069_6/__init__.py`, `tests/EP069_6/
test_capability_security_engine.py`).

- **Core behavior**: an `INTERNAL` capability with blank `source` and
  no `required_permissions` yields `LOW` risk, zero findings; a
  non-`INTERNAL` capability with a populated `source` and no
  high-risk permission tags yields `LOW` risk.
- **Validation / error handling**: `assess(None)` raises
  `CapabilitySecurityProviderError`.
- **Each finding category independently**: missing provenance
  triggers exactly the `"missing_provenance"` finding at `MEDIUM`;
  trust/source inconsistency triggers exactly
  `"trust_source_mismatch"` at `HIGH`; a high-risk permission tag on a
  non-`INTERNAL` capability triggers exactly `"high_risk_permission"`
  at `HIGH`, naming the matched tag.
- **Edge cases**: a capability triggering multiple findings
  simultaneously reports `overall_risk_level` as the maximum across
  all of them and lists every triggered finding, not just the first;
  an `INTERNAL` capability never triggers the trust/source-mismatch or
  missing-provenance checks regardless of its other field values,
  since both are gated on `source_kind != INTERNAL`.
- **Deterministic behavior**: repeated `assess()` calls on the same
  `Capability` produce byte-identical `CapabilitySecurityAssessment`
  values.
- **Integration boundaries**: verify `CapabilitySecurityEngine`/
  `DefaultCapabilitySecurityProvider` never mutate the input
  `Capability`, never import or call `CapabilityRegistry`/
  `CapabilityBackend`, and never import `src.core.capability_discovery`,
  `src.core.planning`, `src.core.agent`, `src.bootstrap`, or `config`.
- **Regression suites**: re-run `EP069_5`, `EP069_4`, `EP069_3`,
  `EP069_2`, `EP069`, and `EP056` unchanged, to confirm zero regression
  from this purely additive new package.

Test counts are not inflated -- each behavioral distinction above maps
to exactly one focused test method.

## 19. Regression Strategy

Purely additive new package; zero existing file is modified by this
design except the one, standard, repository-wide `src/modules/
test_module.py` registration line every prior EP also adds. Full
reachable regression suite should be re-run in STEP 2/3, to confirm
the established, unaffected baseline (`7277 passed / 3 failed / 1
skipped`, per EP-069.5's own final count) is preserved.

## 20. Dependency Analysis

```
Capability, CapabilityTrustLevel, CapabilitySourceKind (EP-069.4, unmodified)
          |
          v (read-only: field access only, no registry query)
CapabilitySecurityProvider (ABC), DefaultCapabilitySecurityProvider
          |
          v
CapabilitySecurityEngine
          |
          v (not built in this EP -- Future Extension Point)
   [future EP-070 policy gate, or other future consumer]
```

No dependency on `src.core.capability_discovery`, `src.core.planning`,
`src.core.agent`, `src.core.tool`, `src.bootstrap`, or `config`. No
dependency in the other direction: `Capability`/`CapabilityRegistry`/
`CapabilityBackend` and every EP-069.5 component depend on **nothing**
introduced by this design. No circular dependency. No new third-party
dependency.

## 21. File-Level Impact Forecast

**Expected new files (STEP 2):**
- `src/core/capability_security/__init__.py`
- `src/core/capability_security/capability_security_result.py`
- `src/core/capability_security/capability_security_provider.py`
- `src/core/capability_security/capability_security_engine.py`
- `tests/EP069_6/__init__.py`
- `tests/EP069_6/test_capability_security_engine.py`

**Expected modified files (STEP 2):**
- `src/modules/test_module.py` (+1 import line, the standard
  registration convention every prior EP-069.x also required). This
  is the only expected modification; identified here explicitly per
  this task's Section 8 requirement.

**Files explicitly expected to remain untouched:**
- `src/bootstrap.py`, `config/config.yaml`.
- `src/core/capability/*` (EP-069.4) -- `capability.py`,
  `capability_registry.py`, `capability_backend.py`, `__init__.py`.
- `src/core/capability_discovery/*` (EP-069.5) -- all four files.
- `src/core/tool/*`, `src/core/plugins/*`, `src/core/planning/*`,
  `src/core/agent/*`.
- `src/skills/capability_registry/skill.py` (EP-056).
- `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`,
  `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `VERSION`,
  `PROJECT_MANIFEST.md`, every `docs/architecture/audits/*` file --
  STEP 4/audit concerns, not STEP 1/2.

## 22. Deferred Items / Future Extension Points

- **Real dependency/package inspection** (e.g. integrating a
  `pip-audit`/`bandit`/`safety`-class tool against a downloaded
  project's manifest) -- deferred until a local-CLI/GitHub-project
  `CapabilityBackend` actually exists to download/install anything
  (Section 3/7).
- **Real sandboxing/isolation policy** (process isolation, containers,
  `seccomp`, filesystem jails) -- deferred until EP-072 (execution)
  exists to actually run a capability inside such an isolation
  boundary.
- **EP-070 policy-engine integration** -- EP-070 does not exist;
  `CapabilitySecurityAssessment` is designed to be consumable by a
  future EP-070 without this EP calling into it.
- **A possible future EP-069.6.x split, or the top-level renumbering
  Option B of Owner Decision OD1**, once the deferred dependency-
  scanning/sandboxing work is itself ready for its own STEP 1.
- EP-069.7 (lifecycle) and EP-071/EP-072 (credentials/execution) all
  remain entirely out of scope and unaffected.

## 23. Risks

- **OD1's "keep the number, narrow the content" choice risks a future
  reader assuming `EP-069.6` is "done" in the full sense BACKLOG's
  bullet describes**, when only the advisory-assessment slice is
  built. Mitigation: this document's title itself
  ("Advisory Assessment Slice") and Section 7's explicit Non-Goals
  list make the narrower scope unambiguous; STEP 4 documentation
  should carry the same qualifier forward.
- **OD5's starter keyword list may produce false positives/negatives**
  on real-world permission tags not yet in use anywhere (since no
  capability is registered in production at all, Section 4 of
  `EP069_5_DESIGN.md`) -- low practical impact today, and easily
  revised once real tags exist to validate against.
- **A genuinely large future EP-069.6 phase (real scanning/sandboxing)
  may eventually justify Option B's renumbering after all** -- this
  STEP 1 does not foreclose that; Section 22 records it as still
  available.

## 24. Relationship to EP-069.1-.5

- **EP-069.1/.2/.3** (AI provider fallback/ordering/cost-awareness):
  no relationship -- entirely different subsystem, untouched and
  unreferenced.
- **EP-069.4** (Unified Capability Abstraction): EP-069.6's sole
  upstream data dependency. Consumes `Capability`'s already-declared
  fields read-only. Does not modify, extend, or subclass anything in
  `src/core/capability/`.
- **EP-069.5** (Capability Discovery Engine): no dependency in either
  direction. Both are independent, sibling consumers of EP-069.4's
  `Capability` model; EP-069.6 does not import, call, or depend on
  anything in `src/core/capability_discovery/`.

## 25. STEP 2 Implementation Constraints

- Implement exactly the files listed in Section 21 -- no
  `capability_security_manager.py`, no `src/bootstrap.py` change, no
  `config/config.yaml` change, per Owner-approved OD3/OD4.
- No modification to any EP-069.4 or EP-069.5 file, under any
  circumstance.
- No dependency/package scanning tool integration, no sandboxing
  mechanism, no `approved`/`rejected` decision field -- per
  Owner-approved OD2/OD6.
- Follow the exact Provider/Engine file-per-concern granularity and
  naming convention already used by `src/core/capability_discovery/`.
- New test package must be self-contained (`tests/EP069_6/`), must not
  modify any existing test file, and must register via the standard
  one-line `src/modules/test_module.py` addition only.

---

## EP-069.6 STEP 1 — COMPLETE — OWNER DECISION REQUIRED
