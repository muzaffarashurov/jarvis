# EP-069 — AI Provider & Tool Registry (Parent Package)
## EP-069.4 — Unified Capability Abstraction

STEP 1: Architecture Discovery & Design

Status: DESIGN PROPOSED — awaiting Owner Decision approval before STEP 2

---

## 1. Title

EP-069.4 — Unified Capability Abstraction

## 2. Status

STEP 1 (this document) only. STEP 2 (Implementation & Testing), STEP 3
(Architecture Audit), and STEP 4 (Documentation Synchronization) have
not started. No source, test, configuration, or tracked documentation
file has been modified to produce this document, other than this new
file itself.

## 3. Target selection evidence

Determined by direct repository inspection, not from memory or the
uploaded task brief alone:

- `git log --oneline` head is `73ca133 docs: rebuild roadmap for
  EP-070–138`, on top of `223fac6 feat(EP-069.3): finalize cost-aware
  provider selection`. EP-069.3 is therefore the latest **completed**
  Engineering Package; the `73ca133` commit is documentation-only
  (confirmed below, Section 3.1).
- `docs/architecture/JARVIS_ROADMAP.md` lines 125, 2378–2384 mark
  EP-069.1/.2/.3 `COMPLETE` and state verbatim: "EP-069 now also
  carries four new planning-only sub-packages (EP-069.4–EP-069.7)
  covering the Unified Capability Abstraction, Capability Discovery,
  External Capability Security/Supply-Chain Trust, and Capability
  Lifecycle Management." EP-069.4 is listed first.
- `docs/BACKLOG.md` lines 2962–2968 defines EP-069.4 — "Unified
  Capability Abstraction" (HIGH) — as the first of the four new
  sub-packages, with EP-069.5/.6/.7 explicitly building on it (EP-069.5
  "the single decision point... instead of hard-coding," EP-069.6
  "every external capability," EP-069.7 "regardless of backend" —
  all presuppose EP-069.4's `Capability` model exists first).
- No design document exists yet for EP-069.4 (`docs/architecture/
  designs/` contains `EP069_DESIGN.md`, `EP069_2_DESIGN.md`,
  `EP069_3_DESIGN.md` only), and no EP-070–EP-073 design document
  exists either — confirming EP-069.4 is the correct next unstarted
  item, not EP-070 or a later phase.
- Per the calling task's own rule ("If the next roadmap item is a
  sub-EP such as `EP-069.4`, treat it as the target instead of
  automatically jumping to `EP-070`"), EP-069.4 is selected over
  EP-070, even though EP-070 is also fully planning-only.

**Target: EP-069.4 — Unified Capability Abstraction.**

### 3.1 Verifying `73ca133` is documentation-only

```
git show --stat 73ca133
```
touches only `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`,
and adds `docs/architecture/designs/
ROADMAP_070_138_REBUILD_PROPOSAL.md`. No file under `src/`, `tests/`,
`config/`, or dependency manifests is touched. This confirms the
commit is the documentation rebuild described in that file's own
"Files changed" section, not a code change that would alter what
"latest completed EP" means.

### 3.2 A discrepancy, found and resolved, not silently passed over

`docs/architecture/designs/EP069_DESIGN.md` Section 29 ("Deferred
EP-069.x Scope"), written at EP-069.1 STEP 1 time, speculatively named
its own next four candidate slots. Its "EP-069.4 (candidate)" was
**"LLM function/tool calling"** — a different subject than the
canonical "Unified Capability Abstraction" now assigned to EP-069.4 by
`docs/BACKLOG.md` and `docs/architecture/JARVIS_ROADMAP.md`. This is a
genuine textual disagreement between an old document and the current
canonical roadmap, so it is documented here rather than silently
resolved:

- Section 29 explicitly framed every entry as a **candidate**, not a
  reservation: "each a candidate for its own future EP-069.x with its
  own STEP 1." EP-069.2 and EP-069.3 candidates in that same list *did*
  become the real EP-069.2/EP-069.3 (numbers and subjects both
  matched), which is presumably why the later rebuild reused
  EP-069.4-.7 as sequential numbers rather than jumping past them —
  but nothing in this repository's documented Engineering Package
  Policy binds a "candidate" name to its number.
- The current canonical sources — `docs/BACKLOG.md` and
  `docs/architecture/JARVIS_ROADMAP.md` — agree with each other on
  EP-069.4's subject (Unified Capability Abstraction) and were
  explicitly synchronized by the same commit (`ROADMAP_070_138_REBUILD_
  PROPOSAL.md`, Status line: "canonical documents have been
  synchronized"). Per the calling task's own instruction to select the
  target "from the current canonical roadmap, not guessed from old
  conversations, memory, filenames, or assumptions," these two
  documents — not `EP069_DESIGN.md` Section 29 — are authoritative.
- This is judged a **documentation naming-drift finding**, not a
  repository-vs-roadmap conflict requiring an Owner Decision to halt
  on: the two canonical documents that actually govern "what is
  EP-069.4" fully agree with each other. It is recorded here (mirroring
  the rebuild proposal's own precedent of flagging the EP-051/EP-073
  overlap rather than silently rewriting either document) so a future
  reader of `EP069_DESIGN.md` Section 29 does not treat its stale
  candidate name as current. `EP069_DESIGN.md` itself is left
  unmodified (Section 24, Protected Files) — Section 29 is historical
  context, correctly labeled speculative at the time it was written,
  and not this STEP 1's responsibility to edit.
- "LLM function/tool calling" (native provider tool-calling) remains
  genuinely unscoped by any current EP number. It is recorded as an
  open question for the project owner in Section 28.

## 4. Previous completed EP

**EP-069.3 — Cost-Aware AI Provider Selection** (`docs/architecture/
designs/EP069_3_DESIGN.md`, `docs/architecture/audits/
EP069_3_ARCHITECTURE_AUDIT.md`, `docs/architecture/audits/
EP069_3_FINDINGS_RESOLUTION.md`).

- **Problem solved**: gave an operator a way to express "prefer the
  cheaper of two available, equally-eligible providers" during
  fallback, via a static per-provider `relative_cost` weight.
- **Architecture introduced**: a pure, additive ordering branch inside
  `ProviderManager.list_fallback_candidates()`; no new class, no new
  file, no `AIProvider`/`ProviderResponse` contract change.
- **Files touched (per its own STEP 2 forecast)**:
  `src/core/ai/provider_manager.py`, `src/bootstrap.py`,
  `config/config.yaml`, plus a new `tests/EP069_3/` package.
- **APIs/contracts established**: `ai.cost_aware_enabled` (config,
  default `false`); `providers.<name>.relative_cost` (config,
  provider-scoped, default `1.0`/"unknown → sorted last, never
  excluded").
- **Tests**: `tests/EP069_3/test_cost_aware_provider_selection.py`
  (1,020 lines; per the design doc, "EP-069_3 80/0/0," i.e. 80
  passed/0 failed/0 skipped, a new suite additive to the pre-existing
  baseline).
- **Design decisions**: relative, not usage-based, cost (D1);
  provider-scoped config location (D2); applies only to fallback
  ordering, never to primary/current-provider selection (D3);
  standalone of EP-069.2, which is not in the source tree (D4).
- **Explicitly deferred**: real usage-based cost tracking/reporting
  (D8, Section 27), a CLI command to change cost weights at runtime
  (D6).
- **Future EPs that depend on it**: none identified — EP-069.4-.7 are
  a parallel extension of EP-069's *tool/capability* scope, not of its
  *provider-fallback* scope; EP-069.4's own Capability model does not
  need cost-aware provider selection to exist, and does not touch
  `src/core/ai/` at all (confirmed by direct inspection, Section 6).
- **What EP-069.4 must NOT duplicate**: EP-069.4 must not invent a
  second "prefer the cheaper/more-trustworthy option" ranking
  algorithm — Capability *discovery/ranking* by cost and trust is
  EP-069.5's explicit, separate job ("ranks them by fit, trust, and
  cost," `docs/BACKLOG.md` line 2970). EP-069.4 defines the `Capability`
  data model only; it must not pre-empt EP-069.5 by embedding ranking
  logic inside the model or its registry.

## 5. Roadmap source

- `docs/architecture/JARVIS_ROADMAP.md` (Phase A section, lines
  2372–2391): EP-069.4-.7 planning-only, subject line as quoted in
  Section 3 above.
- `docs/BACKLOG.md` (lines 2940–2999): full EP-069.4-.7 definitions
  and their reuse relationships to EP-070/EP-071/EP-072/EP-073.
- `docs/architecture/designs/ROADMAP_070_138_REBUILD_PROPOSAL.md`: the
  design record explaining *why* EP-069.4-.7 exist (Sections 0–3),
  including the explicit boundary rule: "Local GitHub projects, CLI
  apps, APIs, and browser services become *backends* behind this one
  abstraction, not separate EPs" (`docs/BACKLOG.md` line 2965-2968,
  restated in the rebuild proposal Section 5).

## 6. Problem statement

Today, "something Jarvis can do" is represented by at least three
unrelated, structurally different catalog-entry types, each scoped to
exactly one execution mechanism, with no shared model an EP-069.5
discovery engine or an EP-069.6 security engine could operate over
uniformly:

- `Tool` (`src/core/tool/tool.py`) — id/name/description/subsystem/
  action/**zero-argument** `handler`/enabled. No input schema, no
  output schema, no permission list, no trust level, no source/
  provenance, no version. Its handler is a Python closure bound at
  `src/bootstrap.py` composition-root time — it can only ever wrap
  code already compiled into this process.
- `Plugin` (`src/core/plugins/plugin.py`) — id/name/version/
  description/author/enabled/entry_point/dependencies/**capabilities**
  (free-form string tags, e.g. `"invoice.automation"`, carrying no
  interface, schema, or trust information at all)/aliases/status. A
  plugin's "capabilities" field is advertising metadata, not an
  invocable contract.
- `CapabilityRegistryModule` (`src/skills/capability_registry/
  skill.py`, EP-056) — despite its name, defines **no** `Capability`
  class. It is a read-only `CommandModule` that composes a text
  summary of `Plugin.capabilities` tags plus `CommandRouter`
  namespace names, for injection into an AI prompt via
  `PromptManager.build(capabilities=[...])`. It performs no
  invocation, no discovery ranking, no security check, and has no
  domain model to extend (Section 7.3 below has the full overlap
  analysis).

None of these three can represent a local GitHub project's CLI, a REST
API endpoint, or a browser-executed external web service — the four
backend kinds `docs/BACKLOG.md`'s EP-069.4 bullet names explicitly.
Without one shared model, EP-069.5 (Discovery) would have to special-
case three-plus unrelated types to "find matching internal, local, or
remote capabilities and rank them," and EP-069.6 (Security) would have
to bolt permission/trust checks onto types (`Tool`, `Plugin`) that were
never designed to carry them — exactly the "parallel, disconnected
infrastructure" `docs/BACKLOG.md` says this rebuild is meant to avoid.

## 7. Goals

- Define a single `Capability` domain model — interface/input-output
  schema, required permissions, trust level, source/provenance,
  version — that can describe an internal tool, a local CLI/GitHub-
  project tool, a REST API, an external web service, or a
  browser-executed service, without any backend-specific field leaking
  into the shared model.
- Define a thread-safe `CapabilityRegistry` catalog for these entries,
  matching this repository's existing registry pattern exactly
  (`ToolRegistry`, `PluginRegistry`, `ProcessRegistry`).
- Define the extension seam (a `CapabilityBackend`-shaped structural
  contract, analogous to `ToolProvider`) that a *future* EP can
  implement per backend kind, without this EP implementing any backend
  itself.
- Establish, and explicitly justify, the classification of `Tool` and
  `Plugin` relative to `Capability` (Section 7.3): reused as-is,
  wrapped, or left alone.
- Produce a model that EP-069.5 (Discovery), EP-069.6 (Security), and
  EP-069.7 (Lifecycle) can each build on independently, without this
  EP pre-empting any of their scope.

## 8. Non-Goals

Per `docs/BACKLOG.md`'s own scoping of EP-069.5/.6/.7 as separate
sub-packages, EP-069.4 does **not**:

- implement capability *discovery*, matching, or ranking by task, fit,
  trust, or cost — that is EP-069.5's entire subject.
- implement any security check: no source-provenance verification, no
  dependency/package inspection, no sandboxing, no permission
  *enforcement* (only permission *declaration*, as a static field) —
  that is EP-069.6's entire subject.
- implement registration workflow, versioning *transitions*,
  enable/disable *commands*, update, revocation, or an audit trail —
  that is EP-069.7's entire subject. EP-069.4's registry supports only
  the same minimal register/unregister/find/list operations
  `ToolRegistry` already has, as the substrate EP-069.7 will later
  govern.
- implement any real backend: no local CLI/GitHub-project executor, no
  REST client, no external-web-service client, no browser-automation
  client. `CapabilityBackend` is a structural contract only, with zero
  concrete implementations in this EP (mirrors how `ToolProvider` was
  introduced by EP-031 with exactly one concrete class,
  `DefaultToolProvider` — this EP introduces the contract with *zero*
  concrete classes, since even the "internal" backend is Section 7.3's
  reuse of the existing `ToolEngine`/`ToolProvider`, not a new class).
- implement the EP-070 Policy/Approval gate, the EP-071 Credential
  Manager, the EP-072 execution/rollback machinery, or the EP-073
  browser automation engine. `Capability.required_permissions` is a
  declared, structural field only — nothing in this EP calls into a
  policy engine, because none exists yet in this repository (Section
  6, verified: no `class.*Policy` matching EP-070's subject exists
  anywhere under `src/`).
- modify `Tool`, `ToolRegistry`, `ToolProvider`, `ToolEngine`,
  `ToolManager`, `Plugin`, `PluginRegistry`, `PluginManifest`,
  `PluginLoader`, `PluginDiscovery`, or `CapabilityRegistryModule`
  (Section 24, Protected Files) — every relationship to these existing
  components is additive and read-only from the new model's side.
- register a new CommandRouter namespace, add a new CLI surface, or
  wire anything into `src/bootstrap.py`. `Capability`/
  `CapabilityRegistry` are pure domain types with no composition-root
  presence yet, exactly like `Tool`/`ToolRegistry` were before
  `ToolManager`/`ToolEngine`/bootstrap wiring existed — that wiring is
  legitimately a later EP-069.4 STEP 2 concern once EP-069.5's
  discovery consumer exists to justify it, not invented speculatively
  here.

## 9. Repository findings (Section 3 of the required investigation)

Full inspection performed for this STEP 1 (paths and line counts
verified directly against the checked-out repository):

- `src/core/tool/` (8 files, 129+66+159+109+277+157+148+59 = 1,104
  lines): `Tool`, `ToolRegistry`, `ToolProvider`/`DefaultToolProvider`,
  `ToolEngine`, `ToolManager`, `ToolExecutionProvider`, `ToolResult`.
  Internal-only, zero-argument-handler tool invocation for
  already-implemented subsystems, bridged into EP-030's Plan Execution
  Engine.
- `src/core/plugins/` (6 files, 1,087 lines): `Plugin`/`PluginStatus`/
  `PluginInterface`, `PluginRegistry`, `PluginLoader`,
  `PluginDiscovery`, `PluginManifest`, `PluginContext`. Full five-stage
  lifecycle (load → initialize → start → stop → unload) for
  Python-object plugins with a `manifest.yaml` on disk, discovered via
  `PluginDiscovery`, resolved via `PluginLoader.resolve_dependencies()`
  (topological, cycle-detecting).
- `src/skills/capability_registry/skill.py` (EP-056, 318 lines):
  read-only prompt-context composer, no domain model — full analysis
  in Section 7.3.
- `src/core/github/` (`github_error.py`, `github_result.py` only — no
  `github_client.py`/`github_service.py`) and `src/core/git/`
  (`git_error.py`, `git_result.py` only) — both packages define only
  error and result types today; no capability-invocation surface
  exists to reuse or duplicate for a "local GitHub project" backend.
- No `src/core/policy/`, no `class.*Policy` matching an approval-gate
  subject anywhere under `src/` (the only `Policy` class in the
  repository is `RestartPolicy` in `src/core/processes/process.py`, an
  unrelated process-supervision concept) — confirms EP-070 does not
  exist yet, as the roadmap states.
- No `pydantic`, `jsonschema`, or any schema-validation library in
  `requirements.txt` — every existing catalog-entry model in this
  repository (`Tool`, `Plugin`, `PluginManifest`) is a plain
  `@dataclass` with hand-written field validation. A new dependency
  for `Capability`'s input/output schema would violate this project's
  "no unnecessary frameworks" rule (Section 8's Non-Goals extend to
  dependencies) and is explicitly rejected (Section 13.2).
- Provider-pattern precedent, verified directly in
  `src/core/tool/tool_provider.py`: an `ABC` structural contract
  (`ToolProvider`) with `provider_name()`/an invocation method/
  `is_available()`, one concrete built-in implementation
  (`DefaultToolProvider`), owned/selected by a `*Manager`
  (`ToolManager`), matching `docs/architecture/JARVIS_ROADMAP.md`'s
  and `tool_provider.py`'s own docstring list of five prior instances
  of the same pattern (Semantic Search, Context Compression, Agent,
  Planning, Plan Execution). `CapabilityBackend` (Section 15) follows
  this exact shape.
- `config/config.yaml` `tool:`/`capability_registry:` blocks confirm
  the `<subsystem>.enabled` / `<subsystem>.default_provider` config
  convention this project uses for every optional subsystem.

## 10. Existing functionality — classification

Per the calling task's Section 4 requirement, classified against
EP-069.4's actual intended responsibility (the shared `Capability`
model + registry):

| Component | Classification | Reasoning |
|---|---|---|
| `Tool` / `ToolRegistry` / `ToolProvider` / `ToolEngine` | **REUSABLE** (as a backend, not modified) | Becomes the "internal" `Capability` backend by wrapping, not replacing, `ToolEngine` (Section 15.1). |
| `Plugin` / `PluginRegistry` | **OUT OF SCOPE** (not a capability backend) | A plugin is a *loadable Python-object lifecycle*, not an invocable action with input/output; `Plugin.capabilities` is advertising, not an interface. No plugin currently exposes a callable, schema-typed action `Capability` could wrap without inventing an API `PluginInterface` does not have (Section 7.3). |
| `CapabilityRegistryModule` (EP-056) | **OUT OF SCOPE** (different subject, same word) | Prompt-context text composer; has no domain model to extend and performs no invocation (Section 7.3). |
| A `Capability` domain model | **MISSING** | Confirmed absent repository-wide (`grep -rIl "class Capability"` matches only the EP-056 module name and its own test file, neither of which defines a `Capability` class). This EP creates it. |
| A shared local-CLI/REST/browser backend | **MISSING** | Confirmed absent (Section 9's `git`/`github` finding). Explicitly **not** built in this EP (Non-Goals) — only the `CapabilityBackend` contract shape is defined, for a future EP to implement. |
| Discovery/ranking by task, trust, cost | **MISSING, OUT OF SCOPE** | EP-069.5's job. |
| Security/supply-chain trust enforcement | **MISSING, OUT OF SCOPE** | EP-069.6's job. |
| Registration workflow / versioning / revocation / audit trail | **PARTIALLY IMPLEMENTED for `Plugin`/`Tool` (register/unregister only), MISSING for `Capability`; full scope OUT OF SCOPE** | EP-069.7's job; EP-069.4's registry supplies only the same register/unregister/find/list baseline `ToolRegistry` already has. |
| `RestartPolicy` (`src/core/processes/process.py`) | **OUT OF SCOPE, unrelated** | Process-supervision restart policy, not an approval/permission policy; not a naming collision worth flagging further. |

## 11. Overlap analysis — `CapabilityRegistryModule` (EP-056) in full

This is the one component whose *name* collides with this EP's
subject, so it receives its own dedicated analysis rather than a
one-line table entry:

- **What EP-056 actually is**: a `CommandModule` implementing the
  `capability` CLI/Telegram namespace (`capability help|list|inject`).
  `capability list` calls `PluginService.running_plugins()` and
  `CommandRouter.module_names()` — both already-existing, read-only
  accessors — and formats their output as text. `capability inject`
  passes that same text through `PromptManager.build(capabilities=
  [...])`, an existing Prompt Engine parameter that predates EP-056
  (its own docstring says "reserved for the future Capability
  Registry" — EP-056 fills that reservation with a *summary string*,
  not a structured type).
- **What it is not**: it defines no class named `Capability`, no
  schema, no permission model, no trust level, no backend concept, and
  performs no invocation of anything. Its own module docstring
  confirms this directly: "No shell/subprocess/arbitrary code
  execution of any kind exists in this module."
  `tests/EP056/test_capability_registry.py` (found by the same grep
  that found this module) tests exactly this text-composition
  behavior, not a `Capability` type.
- **Is it a duplicate of EP-069.4's `Capability` model?** No — it
  operates one layer up (assembling a human/AI-readable summary *of*
  whatever capabilities already exist) rather than *defining* what a
  capability is. There is no code to reuse from it for the `Capability`
  model itself.
- **Should EP-069.4 extend it?** No, and not now: EP-056's own
  docstring lists `plugin_service`, `command_router`, and
  `prompt_manager`/`prompt_builder` as files this project's Dependency
  Policy forbids modifying gratuitously, and `CapabilityRegistryModule`
  is explicitly out of this EP's scope (Section 8, Non-Goals — no new
  CommandRouter namespace). A **future** EP (plausibly EP-069.5,
  discovery, or a later EP-056.x) is the natural place to have
  `capability list` additionally summarize the new `CapabilityRegistry`
  catalog created here — recorded as a Future Extension Point (Section
  19), not implemented or even wired toward in this EP.
- **Naming recommendation**: keep the class name `Capability` (matches
  `docs/BACKLOG.md`'s own vocabulary exactly) but do not rename or
  touch `CapabilityRegistryModule`/`capability_registry.*` — the two
  live in different packages (`src/core/` vs `src/skills/`), serve
  different consumers (a discovery/security substrate vs. a
  prompt-context CLI command), and this project does not have a
  documented "package prefix owns a word" convention that would compel
  a rename. This is recorded explicitly rather than left implicit so a
  future STEP 1 or code reviewer does not mistake the two for the same
  subsystem.

## 12. Scope

### 12.1 In Scope

- `Capability` — a frozen dataclass domain model: id, name,
  description, interface/input schema, output schema, required
  permissions, trust level, source/provenance, version, backend kind,
  enabled.
- `CapabilityTrustLevel` — a small enum (Section 14.2).
- `CapabilitySourceKind` — a small enum identifying which of the four
  backend kinds a capability belongs to (`INTERNAL`, `LOCAL_CLI`,
  `REST_API`, `BROWSER_SERVICE`), used for classification only, not
  dispatch (dispatch is EP-069.5's job).
- `CapabilitySchema` — a minimal, hand-rolled (no new dependency)
  input/output shape descriptor (Section 13.2).
- `CapabilityRegistry` — thread-safe catalog: register/unregister/
  get/find/list/is_registered, mirroring `ToolRegistry` exactly.
- `CapabilityBackend` — an `ABC` structural contract (analogous to
  `ToolProvider`) that a future backend-specific EP implements. Zero
  concrete implementations shipped in this EP.
- A worked mapping showing how one existing `Tool` (e.g.
  `memory_recall`) *could* be described as a `Capability` without
  modifying `Tool` itself (Section 15.1) — proof-of-fit only, not
  shipped as production wiring.
- Error hierarchy: `CapabilityError` (root), `CapabilityRegistryError`,
  `CapabilityNotFoundError`, `CapabilityValidationError`.

### 12.2 Out of Scope

- Everything listed in Section 8 (discovery/ranking, security/trust
  enforcement, lifecycle/versioning/revocation workflow, any concrete
  backend, policy/credential/execution/browser engines, CLI/bootstrap
  wiring).
- Any change to `Tool`, `Plugin`, or `CapabilityRegistryModule`.
- "LLM function/tool calling" (Section 3.2's open question) — a
  different, currently unscoped subject.

### 12.3 Reused Existing Components

- The `*Registry` catalog pattern (`ToolRegistry`/`PluginRegistry`/
  `ProcessRegistry`) — `CapabilityRegistry` copies its exact shape
  (thread lock, register/unregister/get/find/list/is_registered,
  sorted-by-id `list()`).
- The `*Provider`/`ABC` structural-contract pattern
  (`ToolProvider`/`CompressionProvider`/`AgentProvider`/
  `PlanningProvider`/`PlanExecutionProvider`) — `CapabilityBackend`
  copies its exact shape (a `provider_name()`-equivalent identity
  method, one domain-action method, an `is_available()` extension
  point with a default `True`).
- `Tool`/`ToolEngine`/`ToolProvider` themselves, as the concrete
  internal backend a *future* EP wires behind `CapabilityBackend`
  (Section 15.1) — not modified, only wrapped.
- This project's existing error-hierarchy convention (a package-root
  `<X>Error`, with specific subclasses) — `tool_provider.py`'s
  `ToolError`/`ToolConfigurationError`/`ToolProviderError` and
  `tool_registry.py`'s `ToolRegistryError`/`ToolNotFoundError` are the
  direct templates for Section 12.1's error hierarchy.

### 12.4 New Components

Only the items in Section 12.1 — nothing else. No new third-party
dependency, no new configuration key, no new CLI namespace, no
bootstrap wiring.

### 12.5 Future Extension Points

Interfaces/hooks EP-069.5/.6/.7 (and, in principle, the four backend
kinds) will need, defined here but not implemented:

- `CapabilityBackend.invoke(capability, arguments)` — the seam
  EP-069.5's discovered choice is ultimately dispatched through, and
  where EP-069.6's execution-time checks would sit, without either EP
  needing to touch `Capability`/`CapabilityRegistry` themselves.
- `Capability.required_permissions: tuple[str, ...]` — a declared,
  inert field today; EP-070's future policy engine and EP-069.6's
  future security engine are its intended consumers.
- `Capability.trust_level: CapabilityTrustLevel` — inert classification
  today; EP-069.5's ranking and EP-069.6's sandboxing policy are its
  intended consumers.
- `Capability.source: str` / `Capability.version: str` — inert
  provenance fields today; EP-069.7's lifecycle/audit trail is their
  intended consumer.
- A future `capability list` extension to `CapabilityRegistryModule`
  (Section 11) summarizing `CapabilityRegistry`'s catalog alongside
  its existing plugin/namespace summary — explicitly not built here.

## 13. Architecture

### 13.1 Placement

`src/core/capability/` — a new package at Core Level 1, alongside
`src/core/tool/` and `src/core/plugins/`, per this repository's Level-1
examples list ("tool registry" is named explicitly). This is not a
Universal Engine (Level 2) or a Capability-domain (Level 3, unrelated
use of the word "capability" in the brief's own leveling scheme) —
`Capability` the data model is exactly the kind of "reusable runtime
mechanism" Level 1 exists for, matching where `Tool`/`Plugin` already
live.

```
src/core/capability/
    __init__.py                # public API surface (mirrors tool/__init__.py)
    capability.py               # Capability, CapabilityTrustLevel,
                                 # CapabilitySourceKind, CapabilitySchema
    capability_registry.py      # CapabilityRegistry (+ its errors)
    capability_backend.py       # CapabilityBackend ABC (+ its errors)
```

Four files, matching `src/core/tool/`'s own granularity (one file per
concern: domain model / registry / provider-equivalent contract), not
`src/core/plugins/`'s six-file granularity — no manifest/discovery/
loader/context equivalent is needed yet, since this EP defines no
on-disk manifest format or dynamic loading mechanism (that is either
already covered by `PluginManifest`/`PluginDiscovery` for the plugin
case, or explicitly EP-069.5/.7's future concern for the other three
backend kinds).

### 13.2 Why no schema-validation dependency

`CapabilitySchema` is a plain, frozen dataclass describing named fields
and their primitive kind (`str`, `int`, `float`, `bool`, `list`,
`dict`), each with a `required: bool` flag — deliberately far short of
full JSON Schema. This is a direct application of Section 9's finding
(`Tool`/`Plugin`/`PluginManifest` are all plain dataclasses with
hand-written validation, and no schema library exists in
`requirements.txt`) combined with Section 8's Non-Goal (no unnecessary
frameworks). A capability author declares parameter *names and kinds*;
actual argument validation against that shape is left as
`CapabilityBackend.invoke()`'s own responsibility (a Non-Goal here,
Section 8) — matching how `PluginManifest.from_dict()` validates its
own structure by hand rather than via a schema library, and how
`Tool`'s own contract intentionally requires nothing beyond "zero
argument, returns an object" from its handler.

### 13.3 Components

**`Capability`** (`capability.py`)
- Responsibility: immutable catalog-entry data plus (optionally) a
  bound-at-registration handler for the internal backend case only.
- Location: `src/core/capability/capability.py`.
- Interface: `@dataclass(frozen=True)` — see Section 14.1 for fields.
- Dependencies: none beyond `CapabilityTrustLevel`,
  `CapabilitySourceKind`, `CapabilitySchema` in the same package.
- Interaction with existing components: none directly — a *separate*,
  future composition-root step (out of scope here) would construct a
  `Capability` instance that references an existing `Tool`/`Plugin`
  by id, exactly as `built_in_tools` are constructed today in
  `src/bootstrap.py` by closing over already-built services.
- Lifecycle: none — pure, frozen data.
- Error handling: `CapabilityValidationError` raised by a
  `Capability.validate()` classmethod-equivalent factory analogous to
  `PluginManifest.from_dict()`'s hand-written checks (Section 14.3).
- Security implications: none directly enforced here — fields are
  declarative only (Section 8).
- Observability: none needed — no runtime behavior.
- Testability: trivially unit-testable as plain data + validation
  function, matching `tests/EP069_3/`'s style of direct construction
  and assertion.

**`CapabilityRegistry`** (`capability_registry.py`)
- Responsibility: thread-safe catalog of `Capability` entries; no
  invocation, no discovery ranking (mirrors `ToolRegistry` exactly).
- Location: `src/core/capability/capability_registry.py`.
- Interface: `register`, `unregister`, `get`, `find`, `list`,
  `is_registered` — identical method set and semantics to
  `ToolRegistry` (Section 9's line-by-line comparison target).
- Dependencies: `Capability` only.
- Interaction with existing components: none — deliberately does not
  import `ToolRegistry`/`PluginRegistry` (each catalog remains its own
  source of truth; a future composition-root step reads from both to
  populate `CapabilityRegistry`, this package does not reach into
  either).
- Lifecycle: constructed empty; entries added/removed only through its
  own methods.
- Error handling: `CapabilityRegistryError` (duplicate id),
  `CapabilityNotFoundError` (unknown id) — mirrors
  `ToolRegistryError`/`ToolNotFoundError` exactly.
- Security implications: none — a catalog is not an execution surface.
- Observability: `logger.info()` on register/unregister, matching
  `ToolRegistry`'s own two log lines exactly.
- Testability: directly portable test shape from
  `tests/EP069/` or `tests/EP056/`'s registry-style tests (duplicate
  id, unknown id, list-sorted-by-id, is_registered).

**`CapabilityBackend`** (`capability_backend.py`)
- Responsibility: structural contract every backend-specific invocation
  strategy (internal/local-CLI/REST/browser) will implement in a
  *future* EP. Zero concrete subclasses shipped here.
- Location: `src/core/capability/capability_backend.py`.
- Interface: `ABC` with `backend_kind() -> CapabilitySourceKind`,
  `invoke(capability: Capability, arguments: dict) -> CapabilityResult`
  (abstract), `is_available() -> bool` (default `True`, mirroring
  `ToolProvider.is_available()`).
- Dependencies: `Capability`, `CapabilitySourceKind`, a new
  `CapabilityResult` outcome type (mirrors `ToolResult` exactly: `id`,
  `status` (`COMPLETED`/`FAILED`), `message`, `data`).
- Interaction with existing components: none in this EP — a future
  EP's concrete backend (e.g. one wrapping `ToolEngine` for the
  internal case, Section 15.1) is the first real implementer.
- Lifecycle: none defined here — a future `CapabilityBackendManager`
  (EP-069.5's natural companion, analogous to `ToolManager`) would own
  provider-style selection; not built in this EP (Non-Goals).
- Error handling: `CapabilityBackendError` base class, matching
  `ToolProviderError`'s role.
- Security implications: this is precisely the seam EP-069.6's future
  checks attach to (Section 12.5) — recorded, not implemented.
- Observability: none in this EP (no concrete implementation exists to
  log from).
- Testability: the ABC itself is tested only for "cannot be
  instantiated directly" / "subclass must implement `invoke`," matching
  how `ToolProvider` has no direct test of its own beyond
  `DefaultToolProvider`'s behavioral tests.

## 14. Data / contracts

### 14.1 `Capability` fields

| Field | Type | Purpose |
|---|---|---|
| `id` | `str` | Unique, stable identifier (registry key), mirrors `Tool.id`/`Plugin.id`. |
| `name` | `str` | Human-readable display name. |
| `description` | `str` | Short description. |
| `source_kind` | `CapabilitySourceKind` | Which of the four backend kinds this capability belongs to. Classification only — no dispatch behavior in this EP. |
| `input_schema` | `CapabilitySchema` | Declared parameter names/kinds/required-ness (Section 13.2). |
| `output_schema` | `CapabilitySchema` | Declared result shape, same type as `input_schema`. |
| `required_permissions` | `tuple[str, ...]` | Free-form permission tags (e.g. `"filesystem.read"`, `"network.external"`) — inert until EP-070/EP-069.6 exist (Section 12.5). Mirrors `Plugin.capabilities`' own "free-form tags, validated for shape only" precedent. |
| `trust_level` | `CapabilityTrustLevel` | Section 14.2. |
| `source` | `str` | Provenance string (e.g. `"internal"`, a GitHub URL, an API base URL) — free text in this EP; structured provenance is EP-069.6/.7's job. |
| `version` | `str` | Version string, matches `Plugin.version`'s convention (e.g. `"1.0.0"`). |
| `enabled` | `bool`, default `True` | Mirrors `Tool.enabled`/`Plugin.enabled`. |

### 14.2 `CapabilityTrustLevel`

A `str, Enum` (matching `PluginStatus`'s own style): `TRUSTED_INTERNAL`
(this codebase's own tools), `TRUSTED_CONFIGURED` (an operator
explicitly registered it), `UNVERIFIED` (default for anything
discovered automatically, once EP-069.5 exists) — three levels, no
more, since finer-grained trust scoring is EP-069.6's explicit subject
and inventing a richer scale here would prejudge that EP's own design.

### 14.3 Validation

`Capability` construction goes through a `Capability.create(...)`
factory (not `__init__` directly, since `frozen=True` dataclasses
cannot self-validate in `__post_init__` without extra ceremony;
`Capability.create` mirrors `PluginManifest.from_dict`'s pattern of "a
separate validating constructor, not a permissive raw one"). Raises
`CapabilityValidationError` for: blank `id`/`name`/`description`;
duplicate names in `required_permissions`; an `input_schema`/
`output_schema` with a duplicate field name.

### 14.4 Public / internal / future-extension distinction

- **Public contract** (frozen, stable once shipped): `Capability`'s
  field set, `CapabilityRegistry`'s five methods, `CapabilityBackend`'s
  two abstract + one default method.
- **Internal implementation detail**: `CapabilityRegistry`'s internal
  dict/lock, matching `ToolRegistry`'s own (never part of the public
  contract).
- **Future extension point**: `CapabilityBackend`'s eventual concrete
  subclasses and a future `CapabilityBackendManager`/
  `CapabilityDiscoveryEngine` — named here (Section 12.5) but not
  designed in any further detail, since that detail belongs to
  EP-069.5's own STEP 1.

## 15. Reuse — worked example (proof of fit, not shipped wiring)

### 15.1 Wrapping the existing `memory_recall` `Tool`

Without modifying `src/core/tool/tool.py` or
`src/bootstrap.py`, a future composition-root step could describe the
already-registered `memory_recall` `Tool` as:

```python
Capability.create(
    id="memory_recall",
    name="Memory Recall",
    description="Retrieve relevant entries from the Memory Manager (EP-023).",
    source_kind=CapabilitySourceKind.INTERNAL,
    input_schema=CapabilitySchema(fields=()),   # matches Tool's zero-argument handler
    output_schema=CapabilitySchema(fields=()),  # Tool's return type is untyped `object`
    required_permissions=(),
    trust_level=CapabilityTrustLevel.TRUSTED_INTERNAL,
    source="internal:tool_engine",
    version="1.0.0",
)
```

This demonstrates the model can describe an existing internal `Tool`
one-to-one with no field left unpopulated and no `Tool` change
required — the concrete `CapabilityBackend` that would actually
*invoke* this by delegating to `ToolEngine.invoke("memory_recall")` is
explicitly **not** built in this EP (Section 8, Non-Goals); this
example exists only to prove the model's adequacy, per Section 3 of
the calling task's own required investigation ("reusable components").

## 16. Dependency graph

```
Capability, CapabilityTrustLevel, CapabilitySourceKind, CapabilitySchema
    (no dependencies beyond stdlib + each other)
          |
          v
CapabilityRegistry  ---------->  (depends on) Capability
          |
          v
CapabilityBackend (ABC)  ----->  (depends on) Capability, CapabilitySourceKind,
                                  new CapabilityResult

No dependency in the other direction: Tool/ToolRegistry/ToolProvider,
Plugin/PluginRegistry, and CapabilityRegistryModule (EP-056) depend on
NOTHING introduced in this EP, and this EP's new package imports
NOTHING from src/core/tool/ or src/core/plugins/ (Section 13.3,
"Interaction with existing components: none").

Forward dependents (not built in this EP, shown for completeness):
EP-069.5 (Discovery)  -> depends on Capability, CapabilityRegistry
EP-069.6 (Security)   -> depends on Capability.required_permissions,
                          Capability.trust_level, Capability.source
EP-069.7 (Lifecycle)  -> depends on Capability.version, CapabilityRegistry
Future backend EPs    -> depend on CapabilityBackend
```

No circular dependency exists or is introduced. No Core → Capability
(Level 3) contamination: nothing in `src/core/capability/` references
any Level-3 domain concept. No Capability → Core architectural leakage
in the other direction either, since nothing outside this new package
references it yet (Section 8: no bootstrap wiring in this EP).

## 17. Security and safety review

Per the calling task's Section 10 checklist:

- **Filesystem / shell/CLI execution / external APIs / browser
  automation / network access / external code / downloaded packages**:
  none touched by this EP — `Capability`/`CapabilityRegistry`/
  `CapabilityBackend` are pure in-memory data and an unimplemented
  ABC. The *future* backends that would touch these are explicitly out
  of scope (Section 8).
- **Credentials/secrets**: `Capability.source` is a free-text
  provenance string; this EP does not define how a credential would be
  attached to it — that is EP-071's (Credential & Secret Management)
  job, reused by a future REST/browser backend, per `docs/BACKLOG.md`'s
  own "Reused by" note for EP-069.4.
- **Agents / autonomous execution / permissions / user approval**:
  `Capability.required_permissions` and `trust_level` are declared,
  inert fields with no enforcement path in this EP — enforcement is
  explicitly EP-070 (approval) and EP-069.6 (security)'s job, both
  unimplemented in this repository today (Section 9). This is
  responsible-by-design: it would be *worse* to half-enforce
  permissions here without EP-070's approval engine existing, since
  that would create a false sense of a security boundary that isn't
  real.
- **Logging / sensitive data**: `CapabilityRegistry`'s two log lines
  log only `capability.id`, matching `ToolRegistry`'s own logging
  scope exactly — never `source`, never any future credential.
- **Trust/provenance**: `trust_level`/`source` are declared fields only
  (Section 14.1/14.2); no trust *decision* is made anywhere in this EP.
- **Rollback/recovery**: not applicable — no invocation exists in this
  EP to roll back.
- **Responsible EP/component for each of the above once implemented**:
  EP-070 (policy/approval), EP-071 (credentials), EP-069.6 (security/
  trust), EP-072 (execution safety/rollback), EP-073 (browser). This
  EP owns none of the enforcement — it owns only the shared vocabulary
  (the `Capability` fields) those five future EPs will each read from
  a single place instead of inventing their own.

## 18. Observability

- `CapabilityRegistry.register()`/`unregister()` log at `INFO`,
  matching `ToolRegistry`'s exact two log lines (`logger.info(f"...
  registered: '{id}'.")` / `"... unregistered: '{id}'."`).
- No metrics, tracing, or additional observability surface — nothing
  in this EP executes anything to observe.

## 19. Testing strategy

New package: `tests/EP069_4/`, matching `tests/EP069_3/`'s convention
(`tests/EP069_4/__init__.py`, `tests/EP069_4/
test_unified_capability_abstraction.py`).

- **Unit tests**: `Capability.create()` validation (blank fields,
  duplicate permission tags, duplicate schema field names — success
  and each failure path); `CapabilitySchema` field-shape validation.
- **Integration tests**: `CapabilityRegistry` register → get/find/list
  → unregister round-trip; duplicate-id rejection; unknown-id lookup
  raises; `list()` returns entries sorted by id (mirrors
  `ToolRegistry`'s own existing test shape, portable one-to-one).
- **Contract tests**: `CapabilityBackend` cannot be instantiated
  directly (abstract methods enforced); a minimal test double
  subclassing it round-trips through `is_available()`'s default.
- **Regression tests**: none needed to be re-run beyond the existing
  suite, since no existing file is modified — full `tests/EP069/`,
  `tests/EP069_2/`, `tests/EP069_3/`, `tests/EP056/` suites must remain
  green untouched (verified no shared file; Section 24).
- **Security tests**: not applicable in this EP (no enforcement to
  test) — recorded as EP-069.6's future responsibility.
- **Failure-path tests**: every `CapabilityValidationError`/
  `CapabilityRegistryError`/`CapabilityNotFoundError` raise path.
- **Boundary tests**: empty `CapabilitySchema` (zero fields, matching
  the `Tool`-wrapping example, Section 15.1); `required_permissions=()`
  (no permissions declared).
- **Existing tests that must remain compatible**: all of them — this
  EP adds a new, isolated package and modifies zero existing files
  (Section 24).

### Acceptance criteria

1. `Capability.create()` succeeds for the worked `memory_recall`
   example (Section 15.1) with all fields populated as shown.
2. `Capability.create()` raises `CapabilityValidationError` for a
   blank `id`, a blank `name`, a duplicate `required_permissions` tag,
   and a duplicate field name across `input_schema`/its own fields.
3. `CapabilityRegistry.register()` raises `CapabilityRegistryError` on
   a duplicate id and succeeds otherwise; `unregister()`/`get()` raise
   `CapabilityNotFoundError` for an unknown id.
4. `CapabilityRegistry.list()` returns entries sorted by `id`,
   matching `ToolRegistry.list()`'s exact ordering guarantee.
5. `CapabilityBackend` cannot be instantiated directly (raises
   `TypeError` per Python's `ABC` machinery) and a minimal concrete
   subclass implementing only `backend_kind()`/`invoke()` inherits a
   working default `is_available() -> True`.
6. Zero existing test file is modified; `tests/EP069/`, `tests/EP069_2/`,
   `tests/EP069_3/`, `tests/EP056/` all remain green, unchanged in
   count, after STEP 2.
7. No new third-party dependency appears in `requirements.txt`.
8. `src/bootstrap.py`, `config/config.yaml`, `src/core/tool/*`,
   `src/core/plugins/*`, `src/skills/capability_registry/skill.py` are
   byte-identical before and after STEP 2 (Section 24).

## 20. Implementation plan for STEP 2 (forecast only, not performed here)

1. Create `src/core/capability/__init__.py` (public API surface, mirrors
   `src/core/tool/__init__.py`'s docstring-plus-`__all__` shape).
2. Create `src/core/capability/capability.py` (`Capability`,
   `CapabilityTrustLevel`, `CapabilitySourceKind`, `CapabilitySchema`,
   `CapabilityValidationError`).
3. Create `src/core/capability/capability_registry.py`
   (`CapabilityRegistry`, `CapabilityRegistryError`,
   `CapabilityNotFoundError`).
4. Create `src/core/capability/capability_backend.py`
   (`CapabilityBackend`, `CapabilityResult`, `CapabilityBackendError`).
5. Create `tests/EP069_4/__init__.py` and
   `tests/EP069_4/test_unified_capability_abstraction.py` covering
   Section 19's full test list.
6. No change to `src/bootstrap.py` or `config/config.yaml` (Section 8:
   no wiring in this EP).
7. STEP 3 (Architecture Audit) and STEP 4 (Documentation
   Synchronization — updating `docs/BACKLOG.md`'s EP-069.4 entry to
   `COMPLETE` and `docs/architecture/JARVIS_ROADMAP.md`'s "## Current"
   section) both follow this repository's existing EP-069.1/.2/.3
   precedent and are not performed in STEP 1 or forecast further here.

## 21. Files expected to change in STEP 2

- `src/core/capability/__init__.py` (new)
- `src/core/capability/capability.py` (new)
- `src/core/capability/capability_registry.py` (new)
- `src/core/capability/capability_backend.py` (new)
- `tests/EP069_4/__init__.py` (new)
- `tests/EP069_4/test_unified_capability_abstraction.py` (new)
- Documentation synchronization (STEP 4, not STEP 2, per Section 20.7):
  `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`.

No existing source file changes — this is itself a notable, favorable
property of this EP's scope (Section 12.4: only new components).

## 22. Protected files (explicitly not modified in STEP 1)

Per the calling task's STEP 1 rule, none of the following was
modified to produce this document: any file under `src/`, `tests/`,
`config/`; `requirements.txt`, `pyproject.toml`; `docs/BACKLOG.md`;
`docs/architecture/JARVIS_ROADMAP.md`; `docs/architecture/designs/
EP069_DESIGN.md`, `EP069_2_DESIGN.md`, `EP069_3_DESIGN.md`; any file
under `docs/architecture/audits/`;
`docs/architecture/designs/ROADMAP_070_138_REBUILD_PROPOSAL.md`. The
only file created is this document.

## 23. Owner decisions

- **D1 — Package location.** `src/core/capability/`, a new Level-1
  Core package alongside `src/core/tool/`/`src/core/plugins/`, not a
  fifth file added inside `src/core/tool/` itself. Chosen because
  `Capability` is a superset abstraction over `Tool` (Section 6), not
  a `Tool` variant, and `docs/BACKLOG.md`'s own wording ("Local GitHub
  projects, CLI apps, APIs, and browser services become *backends*
  behind this one abstraction") describes a new, independent
  abstraction layer, not an extension of `ToolRegistry`'s existing
  one.
- **D2 — `Capability` vs. extending `Tool` directly.** A new,
  independent model, not new optional fields bolted onto `Tool`.
  Chosen because `Tool.handler` is fundamentally zero-argument and
  closure-bound at composition-root time (Section 6) — REST/CLI/
  browser backends need argument-carrying, schema-typed invocation
  `Tool` was never designed for, and retrofitting that onto `Tool`
  would be exactly the "Core change only when the repository proves it
  necessary" question answered here as: necessary, but as a *new*
  type, not a `Tool` rewrite (which would also violate Section 8's
  Non-Goal of leaving `Tool` unmodified and risk every existing
  `ToolEngine` caller's assumptions about a zero-argument handler).
- **D3 — Schema representation.** A minimal hand-rolled
  `CapabilitySchema` (Section 13.2), not `pydantic`/`jsonschema`.
  Chosen directly from Section 9's repository-wide finding that no
  schema library exists today and every comparable model in this
  repository hand-validates.
- **D4 — Whether to ship any concrete `CapabilityBackend`.** No —
  zero concrete implementations, not even one for the internal `Tool`
  case. Chosen because building even one concrete backend requires
  deciding how a `CapabilityRegistry` entry gets *matched* to an
  invocation request in the first place, which is EP-069.5's explicit
  subject ("the single decision point Planning/Agents use") — shipping
  a backend without that decision point would either duplicate part of
  EP-069.5 or dead-end unused. Section 15.1's worked example proves
  model adequacy without needing a real backend.
- **D5 — `required_permissions` representation.** Free-form
  `tuple[str, ...]` tags, not a structured/typed permission object.
  Chosen to match `Plugin.capabilities`' own existing "free-form tags,
  duplicate-checked, otherwise unconstrained" precedent
  (`PluginManifest.from_dict`) rather than inventing a new permission
  taxonomy that would prejudge EP-070/EP-069.6's own future design.
- **D6 — `trust_level` cardinality.** Exactly three levels (Section
  14.2), not a numeric score. Chosen to avoid prejudging EP-069.6's
  own trust-scoring design (a numeric score implies a scoring
  *algorithm*, which is squarely EP-069.6's subject) while still
  giving EP-069.5's future ranking something coarse-grained to sort
  on.
- **D7 — Whether `CapabilityRegistryModule` (EP-056) should be
  touched, renamed, or extended.** No, on all three (Section 11).
  Recorded as a Future Extension Point (Section 12.5), not decided
  further here, since it is neither required for EP-069.4's own scope
  nor requested by any current roadmap item.

## 24. Risks

- **Naming confusion risk** between this EP's `Capability` class and
  EP-056's `CapabilityRegistryModule`/`capability_registry.*` config
  namespace, despite them being unrelated (Section 11). Mitigation:
  this document's explicit Section 11 analysis, referenced by class
  docstrings in STEP 2 (each new class's docstring should cross-
  reference this document and explicitly note it is unrelated to
  EP-056, mirroring how `EP069_DESIGN.md`'s own Section 9.4 already
  disambiguates "EP-031 Tool Engine" from an unrelated EP-069.4
  candidate).
- **Speculative-abstraction risk**: defining `CapabilityBackend` with
  zero concrete implementations risks the interface being wrong for
  the first real backend EP-069.5/a future backend EP actually needs.
  Mitigation: kept deliberately minimal (two methods plus one default)
  and directly modeled on `ToolProvider`'s already-proven shape
  (Section 13.3), rather than speculatively adding methods for
  capabilities this EP cannot yet enumerate concretely.
- **Under-specification risk for `CapabilitySchema`**: a hand-rolled
  schema (Section 13.2) is deliberately less expressive than
  JSON Schema; a future backend with genuinely nested/recursive
  parameter shapes may find it insufficient. Mitigation: recorded as a
  Future Extension (Section 25) rather than solved speculatively now,
  consistent with this project's "avoid speculative overengineering"
  rule.

## 25. Deferred decisions / future extensions

- Whether `CapabilitySchema` needs to grow beyond flat, primitive-typed
  fields (nested objects, arrays-of-objects) — deferred until a real
  backend (a future EP) has an actual parameter shape that needs it.
- Whether `CapabilityBackendManager` (a `ToolManager`-equivalent
  owning backend-provider selection) is EP-069.5's own component or a
  distinct EP-069.4.x sub-package — left for EP-069.5's own STEP 1 to
  decide, since it depends entirely on how EP-069.5's discovery engine
  wants to select among available backends.
- Whether `EP069_DESIGN.md` Section 29's "LLM function/tool calling"
  candidate should become a real EP number, and if so which one
  (Section 3.2) — **OWNER DECISION REQUIRED** if/when the project
  owner wants that capability scoped; not decided here since it is
  unrelated to EP-069.4's actual subject and inventing a number for it
  would violate this task's "do not invent a new EP number unless the
  roadmap clearly requires one" rule.

## 26. Consistency check with roadmap

- Matches `docs/BACKLOG.md` line 2962-2968's description verbatim: "A
  single `Capability` model (interface, input/output schema, required
  permissions, trust level, source/provenance, version)" — every one
  of those six nouns has a corresponding field in Section 14.1, no
  more, no fewer.
- Matches "Local GitHub projects, CLI apps, APIs, and browser services
  become *backends* behind this one abstraction, not separate EPs" —
  `CapabilitySourceKind` names exactly four kinds, and
  `CapabilityBackend` is the single shared contract, not four parallel
  ones.
- Does not silently redefine EP-069.4's intent: no discovery, security,
  or lifecycle logic was added under this EP's number (Sections 8, 12,
  matching the roadmap's own EP-069.5/.6/.7 boundary).
- The one genuine textual disagreement found (Section 3.2, old
  `EP069_DESIGN.md` Section 29 candidate name) was documented, not
  silently resolved or silently ignored.

## 27. Architectural quality gates (self-check)

- **No duplication**: verified against `Tool`, `Plugin`,
  `CapabilityRegistryModule` (Sections 10-11) — none recreated.
- **No unnecessary Core changes**: zero existing files modified
  (Section 21/22).
- **No future-EP implementation**: no discovery/security/lifecycle/
  backend logic implemented (Section 8).
- **Dependency correctness**: no circular dependency (Section 16).
- **Boundary correctness**: placed at Level 1 Core only; no Level-3
  concept referenced (Section 13.1, Section 16).
- **Security correctness**: no enforcement invented ahead of EP-070/
  EP-069.6 (Section 17).
- **Reuse**: registry/provider patterns and error-hierarchy convention
  reused exactly (Section 12.3).
- **Backward compatibility**: 100% additive; zero existing contract
  changed (Section 21).
- **Testability**: every component has a defined test category
  (Section 19).
- **Roadmap consistency**: Section 26.

## 28. Open questions (for the project owner)

1. Should "LLM function/tool calling" (Section 3.2's stale
   `EP069_DESIGN.md` candidate name for "EP-069.4") be given its own
   EP number in a future roadmap pass? It is currently unscoped by any
   canonical document. **OWNER DECISION REQUIRED** if the owner wants
   this pursued; not blocking EP-069.4 itself.
2. Should `CapabilityBackendManager`/backend-provider selection live
   under EP-069.4 as a `.5` sub-package of its own, or fully inside
   EP-069.5's scope (Section 25)? Recommendation: leave inside
   EP-069.5, since selection-among-backends is inseparable from
   discovery/ranking. Not an Owner Decision blocking this STEP 1 — a
   recommendation for EP-069.5's own future STEP 1 to confirm or
   override.

---

## EP-069.4 STEP 1 — COMPLETE
