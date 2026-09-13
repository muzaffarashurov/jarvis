# EP-069.5 — Capability Discovery Engine

STEP 1: Architecture Discovery & Design

Status: **STEP 1 COMPLETE — OWNER APPROVED — READY FOR STEP 2**. All
six Owner Decisions (OD1-OD6, Section 13) were reviewed and approved
exactly as originally recommended in this document; no alternative
option was selected for any decision. This document has been updated
to record the approved decisions and to remove every conditional
("if Owner selects option (b)...") that existed prior to approval.

---

## 1. Scope Verification — does EP-069.5 exist as a defined planning candidate?

Yes, confirmed directly from the current, canonical repository state
(not from memory or the EP-069.4 work already performed):

- `docs/BACKLOG.md` (line 3075-3078): **"EP-069.5 — Capability
  Discovery Engine" (HIGH). "Given a task, finds matching internal,
  local, or remote capabilities and ranks them by fit, trust, and
  cost; the single decision point Planning/Agents use instead of
  hard-coding 'which tool for which task.'"** This is the single
  authoritative scope statement.
- `docs/architecture/JARVIS_ROADMAP.md` (lines 143, 2466) references
  EP-069.5 consistently with the same subject and confirms it remains
  planning-only as of the current "## Current" entry (EP-069.4).
- `docs/architecture/designs/ROADMAP_070_138_REBUILD_PROPOSAL.md`
  (the document that originally proposed EP-069.4-.7 as sub-packages)
  additionally shows EP-069.5 in an architecture diagram (Section 5)
  and in a validation table (Section 9), consistently describing it as
  the "discovery" step that precedes execution, gated by EP-070/
  EP-069.6, for external-capability scenarios.
- No `docs/architecture/designs/EP069_5_DESIGN.md` exists yet (only
  `EP069_DESIGN.md`, `EP069_2_DESIGN.md`, `EP069_3_DESIGN.md`,
  `EP069_4_DESIGN.md`), and no `docs/architecture/audits/
  EP069_5_*` exists.

**Confirmed: EP-069.5 is a valid, well-defined next planning
candidate.** This STEP 1 proceeds.

## 2. Title

EP-069.5 — Capability Discovery Engine

## 3. Problem Statement

`docs/BACKLOG.md`'s own EP-069.5 bullet identifies the problem
directly by naming what it replaces: *"instead of hard-coding 'which
tool for which task.'"* Direct inspection of the two subsystems the
bullet names as consumers confirms this hard-coding exists today,
literally:

- **Planning Engine (EP-029)**, `src/core/planning/
  planning_provider.py`: `DefaultPlanningProvider.plan()` maps a
  request's text to a `(subsystem, action)` pair using a fixed,
  ordered, in-source Python tuple of 16 keyword rules
  (`_KEYWORD_RULES`). Its own module docstring explicitly says this
  provider "must not call an AI provider, an LLM, or perform any
  reasoning beyond deterministic, rule-based keyword matching" and
  frames an AI-backed strategy as "an obvious, natural extension
  point... but implementing it is explicitly out of scope." There is
  no notion of "capability" here at all -- only a fixed table of
  Jarvis's own, already-known, internal subsystem names.
- **Agent Framework (EP-028)**, `src/core/agent/agent_provider.py`:
  `DefaultAgentProvider` tracks a name -> availability-check
  subsystem registry, but every `execute()` call is accepted and
  acknowledged, never dispatched to a real task (`dispatched` is
  always `False`, per that module's own docstring). There is no
  matching or ranking of any kind.

Neither subsystem can express "given this task, which of the
capabilities Jarvis now knows about (via EP-069.4's
`CapabilityRegistry`) actually fits, is trustworthy enough, and is
affordable enough to use" -- because EP-069.4 only defined *what a
capability is* and *how it is cataloged*; it explicitly deferred
*matching a task to one* (`EP069_4_DESIGN.md` Section 8, Non-Goals:
"EP-069.4 does not implement capability discovery, matching, or
ranking by task, fit, trust, or cost -- that is EP-069.5's entire
subject"). EP-069.5 fills exactly that gap.

## 4. Current Architecture (discovery findings)

- `src/core/capability/` (EP-069.4, unmodified by this STEP 1):
  `Capability` (frozen dataclass: id, name, description, source_kind,
  input_schema, output_schema, required_permissions, trust_level,
  source, version, enabled), `CapabilityRegistry` (thread-safe
  catalog: register/unregister/get/find/list/is_registered, sorted by
  id), `CapabilityBackend` (ABC, zero concrete implementations),
  `CapabilityError` root exception hierarchy (added in STEP 3.1).
- **Critical finding: nothing populates `CapabilityRegistry` in
  production today.** `grep -rn "CapabilityRegistry" src/bootstrap.py
  src/services/ src/modules/` (excluding EP-056's unrelated module)
  returns zero matches. `src/core/capability/` is never imported by
  `src/bootstrap.py`. This means, as of today, a live
  `CapabilityRegistry` instance would always be empty in the running
  application -- there is no bridge from `Tool`/`Plugin` into
  `Capability` in production, only the illustrative,
  proof-of-concept-only worked example in `EP069_4_DESIGN.md` Section
  15.1 (never shipped as real wiring, by that EP's own explicit Non-
  Goal).
- `src/core/tool/` (EP-031): `Tool`/`ToolRegistry`/`ToolProvider`/
  `ToolEngine`/`ToolManager` -- internal-only, zero-argument-handler
  tools, unrelated to and unmodified by this design.
- `src/core/planning/` (EP-029): `PlanningProvider` (ABC) /
  `DefaultPlanningProvider` (concrete, deterministic keyword rules) /
  `PlanningEngine` / `PlanningManager` / `Plan`+`PlanStep` (plain
  data: `order`, `subsystem: str | None`, `action`, `description`,
  `available`). `PlanStep` is Planning-Engine-specific (its
  `subsystem` field names one of Jarvis's own already-known internal
  subsystems, not an arbitrary capability id) -- not a generic "task"
  type suitable for reuse as EP-069.5's own input contract without
  coupling EP-069.5 to Planning Engine internals.
- `src/core/agent/` (EP-028): `AgentProvider` (ABC) /
  `DefaultAgentProvider` / `AgentEngine` / `AgentManager` /
  `SubsystemInfo` (plain data: `name`, `available` -- no matching,
  ranking, schema, trust, or cost concept; no overlap with what
  EP-069.5 needs).
- **Universal provider-framework pattern, confirmed across every
  Core Level-1 subsystem inspected** (`src/core/tool/`,
  `src/core/planning/`, `src/core/agent/`,
  `src/core/context_compression/`, `src/core/semantic/`): exactly
  four files per subsystem -- `<name>_result.py` (plain data),
  `<name>_provider.py` (ABC + exactly one concrete, deterministic,
  non-AI, built-in provider), `<name>_engine.py` (orchestration,
  provider-independent), `<name>_manager.py` (provider registration/
  selection, config-driven via `<name>.default_provider`). Every
  `Default*Provider` inspected explicitly avoids AI/LLM reasoning at
  this layer, deferring it as "an obvious, natural extension point...
  explicitly out of scope" for a future AI-backed provider.
- No `src/engines/` (or equivalent) top-level directory exists
  anywhere in this repository -- the "LEVEL 2 -- UNIVERSAL ENGINES"
  conceptual tier (which explicitly names "Capability Discovery" as
  an example, distinct from "tool registry," a named LEVEL 1 example)
  has no physical convention established yet, since no other Level-2
  Universal Engine (e.g. EP-075/076) has been implemented in this
  repository.
- `config/config.yaml` confirms every Core Level-1 subsystem's
  `<name>.enabled`/`<name>.default_provider` config convention
  (verified for `tool:`, `planning:`, `agent:`, `compression:`,
  `semantic:` blocks).

## 5. Existing Implementation Evidence — What EP-069.5 Must NOT Duplicate

- **Must not duplicate `CapabilityRegistry`'s own register/unregister/
  catalog-mutation responsibility** -- EP-069.5 is a pure, read-only
  consumer of whatever is already in the registry; it never adds,
  removes, or edits an entry.
- **Must not duplicate `PlanningProvider`'s request-decomposition
  responsibility** -- EP-069.5 does not decompose a request into
  steps; it answers a narrower question ("given one task description,
  which registered capabilities fit it") that a future
  `PlanningProvider` (or `AgentProvider`) could call into, but does
  not call Planning/Agent itself.
- **Must not duplicate `CapabilityBackend`'s invocation
  responsibility** -- EP-069.5 never calls `CapabilityBackend.invoke()`
  and never executes anything; it only ranks and returns candidates.
- **Must not duplicate any future EP-070/EP-069.6 policy/security
  decision** -- EP-069.5 may expose `trust_level` as a rankable/
  filterable signal (a passive read of already-declared data), but
  makes no approval, permission-grant, or execution-authorization
  decision. "Ranking by trust" is not "enforcing trust."
- **Must not duplicate EP-069.7's future lifecycle/versioning
  responsibility** -- EP-069.5 does not validate, expire, or revoke a
  capability; it only reads whatever is currently registered and
  `enabled`.

## 6. Goals

- Define a `CapabilityDiscoveryProvider` structural contract (ABC),
  following this repository's own universal Provider/Engine/Manager
  pattern exactly, with exactly one concrete, deterministic,
  non-AI, built-in provider -- `DefaultCapabilityDiscoveryProvider` --
  so the subsystem is genuinely usable today, matching every prior
  Core Level-1 subsystem's own precedent.
- Given a plain-text task description and a `CapabilityRegistry`,
  return an ordered list of matching, `enabled` capabilities, ranked
  by a documented, deterministic combination of fit (text-match
  strength against `name`/`description`) and trust
  (`CapabilityTrustLevel` ordering), with an optional, externally
  supplied cost signal usable as an additional ranking/tie-break
  input (Section 13, Owner Decision OD3).
- Ship a `CapabilityDiscoveryEngine`, matching `ToolEngine`'s own
  provider-independent orchestration shape, constructed directly with
  a `CapabilityDiscoveryProvider` instance (no Manager -- Section 13,
  OD2).
- Leave `Capability`, `CapabilityRegistry`, and `CapabilityBackend`
  (EP-069.4) completely unmodified.

## 7. Non-Goals

- No AI/LLM-based or embedding-based semantic matching in the default
  provider -- deterministic, keyword/substring matching only, matching
  every other `Default*Provider`'s own established precedent. A
  future semantic-matching provider is a natural, later, alternate
  `CapabilityDiscoveryProvider` implementation, not built here.
- No capability registration, mutation, or lifecycle action of any
  kind (Section 5).
- No capability invocation of any kind -- `CapabilityBackend.invoke()`
  is never called (Section 5).
- No security/trust enforcement decision, policy gate, or permission
  grant -- `trust_level`/`required_permissions` are read-only ranking/
  filtering inputs, never an authorization decision (EP-070/EP-069.6's
  future job).
- No change to `Capability`, `CapabilityRegistry`, or
  `CapabilityBackend` (`src/core/capability/*.py`) -- see Section 13,
  which explicitly justifies why the one place this was considered
  (a `cost` field) is resolved without modifying EP-069.4.
- No change to `PlanningProvider`/`AgentProvider`/their `Default*`
  implementations, and no new call from either into this engine --
  wiring Planning/Agents to actually *use* `CapabilityDiscoveryEngine`
  is integration work for a future EP once Planning/Agent's own
  scope is revisited, not this EP (Section 13, Owner Decision OD2).
- No `src/bootstrap.py` or `config/config.yaml` wiring in this design
  by default (Section 13, Owner Decision OD2) -- unless the Owner
  overrides that decision.
- No new CLI command/`*Service` layer by default (same Owner Decision).
- No populating of `CapabilityRegistry` with real, bootstrap-wired
  `Capability` entries derived from `Tool`/`Plugin` -- Section 4's
  "critical finding" (the registry is always empty in production
  today) is a real, load-bearing fact this design must accommodate
  (Section 9's tests populate a registry directly, as data, for this
  reason), but *fixing* that emptiness is not this EP's job; it
  remains a future extension point (Section 22).

## 8. Proposed Architecture

Placement: `src/core/capability_discovery/`, per the Owner-approved
OD1 (Section 13). Four files, matching every other Core Level-1
subsystem's own established granularity exactly:

```
src/core/capability_discovery/
    __init__.py                        # public API surface
    capability_discovery_result.py     # plain data: CapabilityMatch, CapabilityDiscoveryResult
    capability_discovery_provider.py   # CapabilityDiscoveryProvider (ABC) + DefaultCapabilityDiscoveryProvider
    capability_discovery_engine.py     # CapabilityDiscoveryEngine (provider-independent orchestration)
```

A `capability_discovery_manager.py` (provider registration/selection,
matching `ToolManager`/`PlanningManager`) is **deliberately not
included** -- per the Owner-approved OD2 (Section 13): with exactly
one concrete provider and no live consumer yet, a full config-driven
Manager would add a real, but currently unused, config-loading
responsibility. `CapabilityDiscoveryEngine` is constructed directly
with a `CapabilityDiscoveryProvider` instance (defaulting to
`DefaultCapabilityDiscoveryProvider`) rather than resolving one
through a Manager.

## 9. Component Responsibilities

**`CapabilityMatch`** (`capability_discovery_result.py`)
- A single ranked result: the matched `Capability`, a `fit_score:
  float` (0.0-1.0, from text matching), and a `rank: int` (1-based
  position in the returned, already-sorted list). Plain, frozen
  dataclass -- no behavior.

**`CapabilityDiscoveryResult`** (`capability_discovery_result.py`)
- The outcome of one `discover()` call: `task` (the original task
  text, unchanged), `matches: list[CapabilityMatch]` (already sorted,
  best first), `match_count: int`, `truncated: bool` -- directly
  mirroring `Plan`'s own shape (`request`, `steps`, `step_count`,
  `truncated`) for consistency with the sibling subsystem this one is
  most likely to eventually be called from.

**`CapabilityDiscoveryProvider`** (ABC, `capability_discovery_provider.py`)
- `provider_name() -> str` (identity, no network/expensive work).
- `discover(task: str, capabilities: list[Capability], max_results:
  int, cost_hints: dict[str, float] | None = None) ->
  CapabilityDiscoveryResult` (abstract). Takes the *already-fetched*
  list of enabled capabilities, not a live `CapabilityRegistry`
  reference -- mirroring `PlanningProvider.plan()`'s own "never
  queries a live registry itself" convention (`PlanningEngine`
  fetches from `AgentEngine` and hands the result in; here,
  `CapabilityDiscoveryEngine` fetches from `CapabilityRegistry` and
  hands the list in). This keeps the provider layer trivially unit-
  testable with plain lists, with no registry construction required.
- `is_available() -> bool` (default `True`, matching every sibling
  provider's own default).

**`DefaultCapabilityDiscoveryProvider`** (concrete, `capability_discovery_provider.py`)
- Deterministic, case-insensitive substring matching of `task` against
  each candidate `Capability.name` and `Capability.description`
  (whichever produces a stronger, documented match contributes the
  `fit_score`); zero matches against both fields excludes that
  capability from the result entirely (unlike `DefaultPlanningProvider`,
  which always emits a fallback step -- there is no meaningful
  "fallback capability" concept here, so an empty `matches` list is a
  normal, valid outcome, not an error).
- Sorts surviving candidates by `(fit_score descending, trust_level
  descending -- TRUSTED_INTERNAL > TRUSTED_CONFIGURED > UNVERIFIED,
  cost_hints.get(capability.id) ascending if supplied else 0.0, id
  ascending)` -- a fully deterministic, documented tie-break chain
  with no random or AI-influenced ordering.
- Applies `max_results` truncation after sorting, setting `truncated`
  accordingly.

**`CapabilityDiscoveryEngine`** (`capability_discovery_engine.py`)
- Constructed with a `CapabilityDiscoveryProvider` instance directly
  (defaulting to `DefaultCapabilityDiscoveryProvider` when none is
  supplied) -- no Manager exists to resolve one (Section 13, OD2).
- `discover(task: str, registry: CapabilityRegistry, max_results: int
  = 10, cost_hints: dict[str, float] | None = None) ->
  CapabilityDiscoveryResult`: fetches `registry.list()`, filters to
  `enabled=True` only (mirroring `ToolEngine`/`ToolProvider`'s own
  "skip disabled" convention), delegates the filtered list to its
  configured provider, returns the result unchanged.
- Never mutates the provider it was constructed with, and never
  constructs a provider on its own behalf beyond the one default
  supplied at construction time, mirroring `ToolEngine`'s own
  boundary ("Never selects, constructs, or configures providers
  itself").
- Never mutates `registry`.

## 10. Data / Control Flow

```
caller (future Planning/Agent integration, or a direct test/CLI caller)
    |
    v
CapabilityDiscoveryEngine.discover(task, registry, max_results, cost_hints)
    |
    | 1. registry.list()  -- read-only, EP-069.4's own existing method
    | 2. filter: keep only capability.enabled == True
    v
CapabilityDiscoveryProvider.discover(task, enabled_capabilities, max_results, cost_hints)
    |
    | 3. score each candidate's fit against `task`
    | 4. drop zero-fit candidates
    | 5. sort by (fit desc, trust desc, cost asc, id asc)
    | 6. truncate to max_results
    v
CapabilityDiscoveryResult(task, matches, match_count, truncated)
```

No step writes to `registry`, no step calls `CapabilityBackend`, no
step performs network I/O or AI inference.

## 11. Public API / Contracts

Exported from `src/core/capability_discovery/__init__.py`:
`CapabilityMatch`, `CapabilityDiscoveryResult`,
`CapabilityDiscoveryProvider`, `DefaultCapabilityDiscoveryProvider`,
`CapabilityDiscoveryEngine`, and this package's own error hierarchy
(Section 12) -- mirroring `src/core/capability/__init__.py`'s own
export-everything-public convention exactly.

## 12. Error Handling

A package-root `CapabilityDiscoveryError(Exception)`, matching
`PlanningError`/`AgentFrameworkError`/`ToolError`/`CapabilityError`'s
own identical, now-universal convention in this repository, with:
- `CapabilityDiscoveryProviderError(CapabilityDiscoveryError)` --
  raised when `max_results` is not a positive integer (mirroring
  `PlanningProviderError`'s identical `max_steps` check), or when a
  `cost_hints` key does not correspond to any candidate's id (a
  caller error, fails loudly rather than silently ignoring a typo).

`CapabilityDiscoveryEngine.discover()` never swallows a provider
exception -- it propagates unchanged, matching `ToolEngine.invoke()`'s
own documented behavior.

## 13. Owner Decisions — APPROVED

All six Owner Decisions below were reviewed and explicitly approved by
the project owner, exactly as recommended in this document's original
proposal. No alternative option was selected for any decision. This
section records the approved decision, the rationale (unchanged from
the original proposal), and the resulting architectural constraint
STEP 2 must follow.

**OD1 — Physical package location: APPROVED.**
Use `src/core/capability_discovery/`, matching the exact physical
convention and file-level granularity of every already-implemented
Core Level-1 sibling (`src/core/planning/`, `src/core/agent/`,
`src/core/tool/`), even though "Capability Discovery" is named as a
Level-2 "Universal Engine" example in this project's own conceptual
taxonomy. **Do not create `src/engines/` or any other new top-level
directory.** This EP does not unilaterally establish a new physical
Level-2 convention.

**OD2 — Composition-root wiring and CLI surface: APPROVED.**
Ship `CapabilityDiscoveryProvider`/`DefaultCapabilityDiscoveryProvider`/
`CapabilityDiscoveryEngine` only. **No** `CapabilityDiscoveryManager`,
**no** `src/bootstrap.py` wiring, **no** `config/config.yaml` keys,
**no** CLI-facing `*Service`/command module, and **no** runtime
composition-root change of any kind -- directly mirroring EP-069.4's
own immediate precedent. `CapabilityDiscoveryManager` is removed from
this design entirely (Sections 8/21 updated accordingly, below).
Composition-root wiring and registry population/integration remain
explicitly deferred to a future EP (Section 22).

**OD3 — Sourcing "cost" for ranking: APPROVED.**
Use an optional, externally supplied `cost_hints: dict[str, float]`
parameter on `discover()` (keyed by capability id) as a pure ranking/
tie-break input. **Do not modify `Capability` to add a `relative_cost`
field or any other new field.** EP-069.4 is considered finalized and
must remain byte-for-byte unchanged. A capability with no entry in
`cost_hints` is treated as cost `0.0` (cost-neutral); ranking degrades
gracefully to "fit, then trust" alone when no cost data is supplied.

**OD4 — Default fit-scoring algorithm: APPROVED.**
Use deterministic, case-insensitive substring/token-oriented matching
against `Capability.name`/`Capability.description` as the sole
matching strategy in `DefaultCapabilityDiscoveryProvider`. **Do not
introduce EP-026's Semantic Search Engine, any embedding model, or any
AI/LLM call into EP-069.5.** Semantic/AI-assisted matching remains a
documented future extension point (Section 22) implemented by a
different, later `CapabilityDiscoveryProvider`, not built or
referenced in this EP.

**OD5 — Discovery input contract shape: APPROVED.**
`discover()`'s task parameter is a plain `str` task description,
mirroring `PlanningProvider.plan(request: str, ...)`'s own input shape
exactly. **Do not couple EP-069.5 to Planning Engine's `PlanStep` type
or to any Agent Framework type.** This keeps the engine callable by
Agents, a future EP-074.1, or any other future caller without
introducing a dependency edge onto `src/core/planning/` or
`src/core/agent/`.

**OD6 — Trust-level filtering default: APPROVED.**
`UNVERIFIED` capabilities are included in `discover()`'s results by
default, ranked below `TRUSTED_CONFIGURED` and `TRUSTED_INTERNAL` per
Section 9's documented sort order -- not silently excluded. This
engine only ranks and returns capabilities; it never executes them, so
including a lower-trust candidate in a read-only, informational ranked
list carries no security consequence by itself. Execution-time
security/policy enforcement (a future EP-070/EP-069.6 concern) remains
entirely outside this EP's scope and is never reached by this engine.
The optional `minimum_trust_level: CapabilityTrustLevel | None = None`
filter parameter remains available for a future caller that wants to
exclude low-trust candidates outright.

### Architectural confirmations (restated from Owner approval, binding on STEP 2)

1. `Capability`, `CapabilityRegistry`, `CapabilityBackend`,
   `CapabilityResult`, and every other EP-069.4 file remain exactly as
   finalized in STEP 4 -- **not modified, redesigned, or extended** by
   EP-069.5 in any way.
2. EP-069.1, EP-069.2, and EP-069.3 are unrelated to EP-069.5 (Section
   24) and are not touched.
3. The production `CapabilityRegistry` population gap identified in
   Section 4 ("nothing populates `CapabilityRegistry` in production
   today") is **explicitly and deliberately not solved by EP-069.5**.
   `Tool` -> `Capability` and `Plugin` -> `Capability` bridging remain
   deferred to a future EP (Section 22).
4. EP-069.5 is **not** integrated into Planning Engine, Agent
   Framework, Tool Engine, `src/bootstrap.py`, any CLI surface, or any
   runtime orchestration path, by this EP.
5. EP-069.5 is a read-only capability discovery/ranking layer only. It
   must not, and per this design does not: execute a capability;
   mutate `CapabilityRegistry`; mutate any `Capability` instance;
   enforce any security/permission policy; perform any lifecycle
   action; use semantic/LLM-based matching; or introduce any new
   `Capability` field (including a cost field).

## 14. Security / Trust Implications

This engine performs no execution, no permission grant, and no policy
decision -- it is a pure, read-only ranking function over already-
declared `Capability` metadata (Section 5). `trust_level` and
`required_permissions` are read as ranking/filtering signals only,
never evaluated against an actual policy (no such policy engine,
EP-070, exists yet -- confirmed absent in EP-069.4's own STEP 1
investigation and unchanged since). No credential, secret, or network
access occurs anywhere in this engine. Responsible future owner for
actual enforcement: EP-070 (policy/approval) and EP-069.6 (supply-
chain/permission checks), exactly as EP-069.4's own STEP 1 concluded
for the same class of concern.

## 15. Configuration Requirements

Per Owner-approved OD2 (Section 13): **none**. No `capability_discovery.*`
configuration key is added in this EP.

## 16. Composition-Root Implications

Per Owner-approved OD2 (Section 13): **none** -- `src/bootstrap.py` is
not touched by this design, under any circumstance.

## 17. Logging Requirements

`CapabilityDiscoveryEngine.discover()` logs at `DEBUG` (not `INFO`,
since this is a read-only, potentially frequent query operation, not a
state-changing one like `CapabilityRegistry.register()`) the task
text's length and the resulting match count only -- never the full
task text or full capability payloads, to avoid incidentally logging
potentially sensitive task content at a default log level.

## 18. Testing Strategy

New, isolated package: `tests/EP069_5/` (STEP 2), matching the exact
convention of `tests/EP069_4/`, `tests/EP069_3/`, etc.
(`tests/EP069_5/__init__.py`, `tests/EP069_5/
test_capability_discovery_engine.py`).

- **Behavioral tests**: a task description that substring-matches one
  capability's `name` returns that capability first; a task matching
  two capabilities' `description` returns both, ordered by fit; a
  higher-`trust_level` capability outranks an equal-fit,
  lower-`trust_level` one; a lower `cost_hints` value outranks an
  equal-fit-and-trust, higher-cost one.
- **Negative/error-path tests**: `max_results <= 0` raises
  `CapabilityDiscoveryProviderError`; a `cost_hints` key not matching
  any candidate id raises `CapabilityDiscoveryProviderError`.
- **Boundary tests**: an empty candidate list (mirroring today's real,
  empty-in-production `CapabilityRegistry`, Section 4) returns an
  empty `matches` list, not an error and not a fallback entry (unlike
  `DefaultPlanningProvider`'s own fallback-step behavior, deliberately
  different per Section 9); a task matching zero capabilities returns
  an empty list; `max_results` truncation with more matches than the
  limit sets `truncated=True`; a `disabled` (`enabled=False`)
  capability is never returned even if it would otherwise match
  (verified by constructing a registry containing a disabled, high-fit
  entry and confirming it is excluded).
- **Regression/compatibility tests**: verify `CapabilityRegistry`,
  `Capability`, `CapabilityBackend` are used only via their existing,
  unmodified public methods (`list()`, field access) -- no test
  reaches into `CapabilityRegistry` internals. Re-run `EP069_4`,
  `EP069`, `EP069_2`, `EP069_3`, and `EP056` unchanged, to confirm zero
  regression from this purely additive new package.
- **No security/trust enforcement tests** -- not applicable, since
  this engine performs no enforcement (Section 14).

Test counts are not inflated -- each behavioral distinction above
maps to exactly one focused test method.

## 19. Regression Strategy

Purely additive new package; zero existing file is modified by this
design (the Owner-approved OD2's zero bootstrap/config wiring
reinforces this -- no existing file needs touching at
all in STEP 2 except the one, standard, repository-wide
`src/modules/test_module.py` registration line every prior EP also
adds). Full reachable regression suite (all `EP0XX` suites this
environment can execute) should be re-run in STEP 2/3 exactly as was
done for EP-069.4, to confirm the established, unaffected baseline
(`7240 passed / 3 failed / 1 skipped`, per `EP069_4_FINDINGS_
RESOLUTION.md`'s own final count) is preserved.

## 20. Dependency Analysis

```
Capability, CapabilityRegistry (EP-069.4, unmodified)
          |
          v (read-only: .list(), field access only)
CapabilityDiscoveryProvider (ABC), DefaultCapabilityDiscoveryProvider
          |
          v
CapabilityDiscoveryEngine
          |
          v (not built in this EP -- Future Extension Point)
   [future Planning/Agent/EP-074.1 integration]
```

No dependency in the other direction: `Capability`/`CapabilityRegistry`/
`CapabilityBackend`, `Tool`/`ToolRegistry`, `Plugin`/`PluginRegistry`,
`PlanningProvider`, `AgentProvider` all depend on **nothing** introduced
by this design. No circular dependency. No Core -> Level-3 (Capability-
domain, unrelated sense) contamination. No new third-party dependency.

## 21. File-Level Impact Forecast

**Expected new files (STEP 2):**
- `src/core/capability_discovery/__init__.py`
- `src/core/capability_discovery/capability_discovery_result.py`
- `src/core/capability_discovery/capability_discovery_provider.py`
- `src/core/capability_discovery/capability_discovery_engine.py`
- `tests/EP069_5/__init__.py`
- `tests/EP069_5/test_capability_discovery_engine.py`

No `capability_discovery_manager.py` -- removed from scope by the
Owner-approved OD2 (Section 13).

**Expected modified files (STEP 2):**
- `src/modules/test_module.py` (+1 import line, the standard
  registration convention every prior EP-069.x also required).

**Files explicitly expected to remain untouched:**
- `src/bootstrap.py`, `config/config.yaml` -- no composition-root or
  configuration change of any kind, per the Owner-approved OD2.
- `src/core/capability/capability.py`, `capability_registry.py`,
  `capability_backend.py`, `__init__.py` (EP-069.4) -- finalized,
  unmodified.
- `src/core/tool/*`, `src/core/plugins/*`.
- `src/core/planning/*`, `src/core/agent/*` -- no integration call is
  added from either into this engine in this EP.
- `src/skills/capability_registry/skill.py` (EP-056).
- `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`,
  `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `VERSION`,
  `PROJECT_MANIFEST.md`, and every `docs/architecture/audits/*` file
  -- STEP 4/audit concerns, not STEP 1/2.

## 22. Deferred Items / Future Extension Points

- Populating `CapabilityRegistry` with real capabilities (bridging
  `Tool`/`Plugin` into `Capability`) -- Section 4's critical finding;
  explicitly not this EP's job (Owner-confirmed, Section 13).
- Wiring `PlanningProvider`/`AgentProvider` to actually call
  `CapabilityDiscoveryEngine` -- deferred until a future EP revisits
  Planning/Agent's own scope.
- A semantic/embedding-based `CapabilityDiscoveryProvider` (reusing
  EP-026's Semantic Search Engine) as an alternate, higher-quality
  provider -- deferred per the approved OD4.
- A `relative_cost` (or similarly named) field on `Capability` itself,
  should a future EP decide the `cost_hints` parameter-based approach
  (approved OD3) is no longer sufficient -- not part of this EP.
- `CapabilityDiscoveryManager`/bootstrap/config/CLI wiring, should a
  future EP decide to give this engine a live composition-root
  presence -- not part of this EP (approved OD2).
- EP-069.6 (security/trust enforcement) and EP-069.7 (lifecycle) both
  remain entirely out of scope and unaffected.

## 23. Risks

- **OD2's minimal-wiring choice risks the engine being "invisible"
  until a future integration EP** -- mitigated by full, direct
  testability (Section 18) independent of any live wiring, exactly
  matching EP-069.4's own accepted trade-off.
- **OD3's `cost_hints` design risks being awkward if a real,
  persistent per-capability cost source is added later** (it would
  then likely migrate into a `Capability` field in a future EP) --
  mitigated by keeping `cost_hints` an optional, additive parameter
  today; no breaking change is required to add a `Capability`-level
  cost field later, since `discover()`'s signature can simply start
  defaulting `cost_hints` from the registry instead of requiring the
  caller to supply it, without changing the parameter's name or type.
- **OD4's deterministic substring matching may produce weak fit scores
  for capabilities whose `name`/`description` doesn't share vocabulary
  with the task text** -- an accepted limitation matching every sibling
  `Default*Provider`'s own precedent; a semantic provider is the
  documented future remedy (Section 22), not a defect requiring a fix
  now.

## 24. Relationship to EP-069.1-.4

- **EP-069.1/.2/.3** (AI provider fallback/ordering/cost-awareness):
  no relationship -- entirely different subsystem
  (`src/core/ai/provider_manager.py`), untouched and unreferenced by
  this design.
- **EP-069.4** (Unified Capability Abstraction): EP-069.5's sole
  upstream dependency. Consumes `Capability`/`CapabilityRegistry`
  read-only, via already-existing public methods only. Does not
  modify, extend, or subclass anything in `src/core/capability/`.

## 25. STEP 2 Implementation Constraints

- Implement exactly the files listed in Section 21 -- no
  `capability_discovery_manager.py`, no `src/bootstrap.py` change, no
  `config/config.yaml` change, per the Owner-approved OD1/OD2.
- No modification to any EP-069.4 file, under any circumstance --
  Section 13/OD3 already resolves the one place an EP-069.4 change was
  considered, without requiring one.
- No modification to `PlanningProvider`/`AgentProvider` or their
  `Default*` implementations.
- Follow the exact Provider/Engine file-per-concern granularity and
  naming convention already used by `src/core/planning/`/
  `src/core/tool/` (Manager intentionally omitted, per OD2).
- New test package must be self-contained (`tests/EP069_5/`), must not
  modify any existing test file, and must register via the standard
  one-line `src/modules/test_module.py` addition only.

---

## EP-069.5 STEP 1 — COMPLETE — OWNER APPROVED — READY FOR STEP 2
