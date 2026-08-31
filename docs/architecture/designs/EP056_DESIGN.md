# EP-056 — Capability Learning — Design Specification (STEP 1)

Status: **STEP 1 — DESIGN APPROVED (D1-D7 all Owner-approved). STEP 2
— COMPLETE. STEP 3 — AUDIT FAILED (ONE BLOCKING FINDING), then PASS
AFTER REMEDIATION following Owner Decision D8 (STEP 4 fix). STEP 4 —
COMPLETE.**

**Owner Decisions D1-D7 (Section 20) are all APPROVED, exactly as
recommended in this document, with no modification.** Candidate A
(Section 5) is the approved v1 scope for EP-056, and Sections 6-17's
provisional architecture is the approved architecture — see the Owner
Approval Checklist at the end of this document for the approved value
of each decision.

---

## 0. How this document relates to EP-054 and EP-055

EP-054 and EP-055 each began with a roadmap line whose only content
was a title and Phase 9's shared, one-sentence, five-EP-wide goal.
Both STEP 1 documents disclosed this gap explicitly rather than
inventing scope, derived candidate interpretations from
already-existing, already-inspected architecture, and asked the owner
to choose among them via an Owner Decision before any provisional
architecture was treated as authorized.

**EP-056 is in the identical situation, confirmed by the same
exhaustive-search method (Section 2).** "EP-056 Capability Learning"
has no functional specification anywhere in the repository beyond its
title and the same Phase 9 goal EP-054/EP-055 already shared. This
document follows the identical methodology: Section 2 is a verbatim
inventory of every reference found, Section 3 grounds candidate
interpretations in already-existing architecture, and Section 20's
Owner Decisions ask the owner to choose before Sections 6-17's
provisional architecture is treated as more than a starting proposal.

**One material difference from both prior EPs, found during
discovery (Section 3.3):** unlike EP-054/EP-055, which each found only
one indirect, one-word textual clue toward their own scope,
EP-056's discovery process found an **explicit, unambiguous, purpose-
built textual reference**: `PromptBuilder.append_capabilities()`'s own
docstring literally reads "reserved for the future Capability
Registry" (`src/core/ai/prompt_builder.py`, line 202), and
`PromptManager.build()`'s `capabilities` parameter's own docstring
repeats "reserved for the future Capability Registry" verbatim
(`src/core/ai/prompt_manager.py`, line 163). This is the single
strongest piece of repository-grounded evidence found across all
three "bare title" EPs (054/055/056) — it is not merely a plausible
inference from a general architectural principle, but a literal,
already-written statement of what a "Capability Registry" is for.
Section 3.3 examines this in full; Section 5's recommended candidate
is built directly on it.

---

## 1. Metadata

- **Engineering Package:** EP-056 — Capability Learning
- **Phase:** Phase 9 — Intelligence (`JARVIS_ROADMAP.md` line 806;
  `docs/engineering/ENGINEERING_GUIDE.md` lines 163-168: "Improve
  reasoning and autonomous decision making.")
- **Predecessors:** EP-054 Self Reflection — COMPLETE (AUDIT PASSED
  WITH FINDINGS); EP-055 Prompt Optimizer — COMPLETE (PASS AFTER
  REMEDIATION). Both followed the identical "bare title, no spec"
  discovery methodology this document also follows.
- **Successors (same phase):** EP-057 Memory Optimization, EP-058
  Autonomous Planning.
- **Foundational, already-complete dependencies (different phases):**
  EP-010 Plugin Manifest & Auto Discovery (`Plugin.capabilities`,
  already-declared, already-validated free-form capability tags);
  EP-017 Prompt Engine (`PromptBuilder.append_capabilities()`,
  `PromptManager.build(capabilities=...)`, both fully built,
  currently uncalled by any code); the `CommandRouter`
  namespace-registration mechanism (Phase 3 onward).
- **This document's scope:** STEP 1 only — repository discovery,
  scope clarification, architecture proposal (contingent on Owner
  Decision D1), and Owner Decision preparation. No code, test,
  configuration, dependency, or Bootstrap file has been created or
  modified as part of producing this document.
- **File created by STEP 1:** this document,
  `docs/architecture/designs/EP056_DESIGN.md`, only.
- **Files modified by STEP 1:** none.

---

## 2. What the repository actually says about EP-056 (verbatim inventory)

Every reference to EP-056 or "Capability Learning" found anywhere in
the repository, by direct, exhaustive search (not sampling) of
`docs/`, `AI_GENERATION_STANDARD.md`, `AI_DEVELOPMENT_PLAYBOOK.md`,
`CHANGELOG.md`, and `src/`:

| Location | Exact content |
|---|---|
| `docs/architecture/JARVIS_ROADMAP.md` line 806 (Phase 9 checklist) | `EP-056 Capability Learning` — a bare title, no elaboration |
| `docs/architecture/JARVIS_ROADMAP.md` line 205-206 ("Current" section, added by EP-055 STEP 4) | `**Next Engineering Package: EP-056 Capability Learning — NOT STARTED.** No EP-056 design, research, or implementation work has begun.` — a status pointer, not a spec |
| `docs/BACKLOG.md` lines 13-16 ("Next Engineering Package" section, added by EP-055 STEP 4) | `### EP-056 — Capability Learning` / `**NOT STARTED.** Per docs/architecture/JARVIS_ROADMAP.md's Phase 9 sequencing, EP-056 (Capability Learning) is the next Engineering Package after EP-055's completion. No design, research, or implementation work has begun.` — same pointer, same lack of elaboration |
| `CHANGELOG.md` line 173 | References EP-056 only as "the next, not-started Engineering [Package]" in an EP-055-completion entry — a status note, not a spec |
| `docs/architecture/designs/EP054_DESIGN.md` (line 50, line 197) | Lists EP-056 as a successor EP that Self Reflection's own output might one day feed, or whose eventual role Self Reflection deliberately does not attempt to replicate. Does not define EP-056's own scope |
| `docs/architecture/designs/EP055_DESIGN.md` (lines 78, 321, 797) | Same pattern — lists EP-056 as a successor EP in scope-boundary reasoning; line 797 explicitly records as an *open question* "Whether a future EP-056/057/058 will expect Prompt Optimizer's output ... in a specific, machine-readable format" and answers "no such requirement exists ... today" — i.e. EP-055 itself found no forward-looking specification for EP-056 either |
| `docs/engineering/ENGINEERING_GUIDE.md` (Phase 9 section, lines 163-168) | `## Phase 9 — Intelligence` / `Improve reasoning and autonomous decision making.` / `Engineering Packages:` / `EP-054 … EP-058` — a **phase-level** goal shared across all five Phase-9 EPs, not an EP-056-specific one (identical text EP-054 and EP-055 already quoted in their own Section 2) |
| Everywhere else (`PROJECT_MANIFEST.md`, `AI_GENERATION_STANDARD.md`, `AI_DEVELOPMENT_PLAYBOOK.md`, every EP-001…EP-055 design/audit document except the two cross-references above, `src/`) | **Zero** additional mention of EP-056, "Capability Learning", or any synonym of it |

**Conclusion (identical in kind to EP-054's and EP-055's own Section 2
conclusions):** the repository establishes *that* Capability Learning
is next, and *that* it belongs conceptually to "Intelligence" —
reasoning and autonomous decision-making — but establishes **no
concrete behavior, input, output, trigger, metric, or user interface**
for EP-056 by that name. Per the task's explicit instruction, this gap
is reported here rather than silently filled. Section 3.3, however,
identifies a strong, independently-discovered textual anchor for the
word "Capability" specifically (as distinct from "Learning") — found
not in a roadmap or backlog entry, but in the Prompt Engine's own,
already-existing source code.

---

## 3. Relevant existing architecture (grounds for the candidate interpretations in Section 5)

### 3.1 `CommandRouter` — the only existing "what can Jarvis currently do" registry

`src/core/command_router.py`'s `CommandRouter` maintains a dict of
registered `CommandModule` instances keyed by namespace, exposed
read-only via `module_names() -> list[str]`. This is the *only*
existing mechanism that can answer "what capabilities does Jarvis
currently have" at all, but it is minimal by construction: the
`CommandModule` Protocol (Section 3.1 of `EP054_DESIGN.md`, confirmed
still current, byte-identical) defines exactly two members — `name`
(the namespace) and `execute(action, arguments)`. **It carries no
description, no action list, and no capability metadata of any
kind.** As of EP-055's completion, roughly 38 namespaces are
registered (`desktop`, `browser`, `file`, `vision`, `reflect`,
`prompt`, `plugin`, `memory`, `agent`, `planning`, ... — enumerated by
direct inspection of every `router.register(...)` call in
`src/bootstrap.py`). Enumerating *that these namespaces exist* is
trivial and already possible today via `module_names()`; describing
*what each one does*, beyond its bare name, is not something any
existing interface supports without either (a) a new, static,
hand-maintained description table (duplicative, drifts from reality),
or (b) extending the `CommandModule` Protocol itself (a cross-cutting
change touching every one of ~38 existing skills, explicitly the kind
of unrelated-file modification this task's own instructions prohibit
inventing without owner approval). This constraint materially shapes
Section 5's candidates and is recorded as Finding-equivalent evidence,
not assumed away.

### 3.2 EP-010 Plugin system — the one place a real, already-populated "capabilities" data model exists

`src/core/plugins/plugin.py`'s `Plugin` dataclass already carries
`id`, `name`, `version`, `description`, `capabilities` (a
`list[str]` of "free-form capability tags describing what this
plugin provides, e.g. 'invoice.automation'" — direct quote from the
class docstring), `status` (`PluginStatus`, owned exclusively by
`PluginRegistry`), and more. `src/core/plugins/plugin_manifest.py`'s
`PluginManifest` validates these same fields from each plugin's
on-disk `manifest.yaml` (EP-010), including duplicate-capability
rejection within a single plugin
(`ManifestValidationError(f"Plugin '{plugin_id}' declares a duplicate
capability.")`). **This is a real, validated, already-populated data
model** — not a placeholder — but it is read in exactly one place
today: `src/modules/plugin_module.py` line 121, formatting
`plugin.capabilities` into a comma-joined string purely for `plugin
info`'s human-readable display. **No other component reads
`Plugin.capabilities` for any purpose** (confirmed:
`grep -rn "\.capabilities\b" src/` finds only this one call site,
outside the Plugin system's own internals). `PluginService`
(`src/services/plugin_service.py`) already exposes
`list_plugins() -> list[Plugin]` and `running_plugins() -> list[Plugin]`
as its own, already-existing, read-only, unmodified public API — this
is the one existing seam through which a "Capability Registry" could
reach real, already-declared capability data without inventing any
new data model or touching the Plugin system's own files.

### 3.3 `PromptBuilder.append_capabilities()` / `PromptManager.build(capabilities=...)` — the strongest textual anchor found, fully built, currently dead

`src/core/ai/prompt_builder.py`'s `PromptBuilder` already carries a
`_capability_parts: list[str]` field (initialized in `__init__`,
cleared in `reset()`), an `append_capabilities(text: str)` method
(fluent, mirrors `append_context()`/`append_memory()`/
`append_instruction()` exactly), and includes `*self._capability_parts`
in `_compose_context()`'s fixed assembly order — **"Capability
Context" is one of the six named stages in EP-017's own "Prompt Flow"
docstring**: `System Prompt -> Conversation Context -> Memory (future)
-> Capability Context (future) -> Additional Instructions -> User
Prompt`. `src/core/ai/prompt_manager.py`'s `PromptManager.build()`
already accepts a `capabilities: list[str] | None = None` parameter,
threaded straight through to `builder.append_capabilities()` for each
item, exactly matching `context`/`memory`/`instructions`'s own
already-wired handling.

**Both docstrings state, verbatim, that this parameter is "reserved
for the future Capability Registry."** This is not this document's
own inference — it is a direct quotation of existing, unmodified
source code, written when EP-017 (Prompt Engine) was built, long
before EP-056 was ever scheduled. Confirmed by direct search
(`grep -rn "append_capabilities\|capabilities="`) that **zero
callers** exist anywhere in `src/services/ai_service.py` or any
other module — `AIService.ask()`'s one call to `self._prompt_manager.
build(...)` (line 465) passes only `user_prompt`, `context`, and
`provider_name`; `capabilities` is never supplied, so `Prompt.rendered`
never actually contains a Capability Context block in current,
unmodified production behavior. This is the same "fully-built,
currently-dead extension seam" pattern EP-055's own Section 3.2 found
for `PromptBuilder.load_template()`/`template=` — except here, the
seam's docstring names the exact future consumer ("Capability
Registry") that EP-056's own title now matches almost verbatim.

### 3.4 `JARVIS_ARCHITECTURE_VISION.md`'s "Capability First" and "AI Router" sections — aspirational, unbuilt

Lines 136-163 ("Capability First"): *"Jarvis should think in
capabilities. Never in providers. ... The user requests a capability.
Jarvis selects the provider."* Lines 166-183 ("AI Router"): provider
selection should consider, among other things, *"capability"* itself
as one criterion. Line 574 ("Design Principles"): *"Capability-based
routing"* is listed as a principle to always prefer. **None of this
is implemented today** — confirmed by direct search
(`grep -n -i "capability" src/core/ai/provider.py provider_manager.py
provider_registry.py`): **zero matches**. No per-provider capability
data model exists anywhere (this is the same absence
`EP055_DESIGN.md` Section 3.5 already confirmed and declined to build
from nothing for its own "Candidate D"). This vision-document
language establishes *that* "capability" is a first-class concept
Jarvis's architecture aspires to reason about, but gives no concrete
specification either — it is directional, not a design.

### 3.5 No usage/outcome tracking, analytics, or "learning" infrastructure exists anywhere

Direct, exhaustive search
(`grep -rln -i "success_rate|usage_stat|telemetry|analytics|track.*usage|capability_registry" src/`)
found no match relevant to capability usage tracking (the one
incidental hit, `src/services/invoice_service.py`, concerns invoice
analytics and is unrelated). **No component anywhere in the
repository records whether a given skill/command/capability
"succeeded," was used frequently, or should be preferred over another
based on any historical signal.** `CommandResult.success: bool`
(`src/core/command_router.py`) is the only existing outcome signal of
any kind, and it is discarded by `CommandRouter.dispatch()` immediately
after being returned to the caller — nothing persists it. This
confirms, by the same method `EP055_DESIGN.md` Section 3.8 already
applied to prompt-effectiveness metrics, that an *adaptive,
statistical* reading of "Learning" (e.g. "learn which skills work
well over time") has **zero existing infrastructure to build on** and
would require inventing a success metric, a persistence schema, and
an adaptation policy from nothing — the same category of gap that led
`EP055_DESIGN.md` to decline its own "Candidate D" (per-provider
optimization) as unsuitable for a v1.

### 3.6 `MemoryService` — the established, already-reusable persistence seam (if any persistence is wanted at all)

`src/services/memory_service.py`'s `MemoryService` (EP-023,
unmodified) already provides a generic, namespaced key/value store
(`set(key, value, namespace=...)`, `get()`, `list_entries()`, `delete()`,
`clear()`) that `ReflectionModule` (EP-054) already reuses, gated by
its own `reflection.persist_to_memory` flag, for an analogous
"optionally persist this on-demand AI-generated artifact" pattern.
Confirmed unmodified since EP-054 (byte-identical). If EP-056 ever
wanted to persist anything (e.g. a generated Capability Context
snapshot, for inspection or audit), this is the established, already-
reusable mechanism — not a new persistence layer.

### 3.7 `CommandRouter` / `CommandModule` precedent (`src/core/command_router.py`) — confirmed still current

Every skill (`desktop`, `browser`, `file`, `vision`, `reflect`,
`prompt`, `plugin`, and ~31 others) is a `CommandModule` registered
with the unmodified `CommandRouter.dispatch()`. Confirmed
byte-identical to its state at EP-055's completion. This remains the
established pattern for any EP-056 capability that should be
manually, explicitly invokable by a user, exactly as EP-054/EP-055's
own Section 3.9/D7 already established (now a third independent EP
reaching the identical conclusion for the identical reason: `Tool.
handler`'s zero-argument-only signature, `src/core/tool/`, makes Tool
Engine unsuitable for a parameterized action, confirmed unmodified).

### 3.8 `AIService`/`Bootstrap` construction ordering — a real, concrete integration constraint

`src/bootstrap.py` constructs `ai_service = AIService(...)` at line
538, but `plugin_service = PluginService(...)` — the one existing
component with real, populated capability data (Section 3.2) — is not
constructed until line 1906, roughly 1,370 lines and dozens of other
services later. **`AIService` is fully constructed and already
capable of serving requests long before `PluginService` exists.**
This means any interpretation that automatically injects a live
Capability Context into *every* `AIService.ask()` call (analogous to
`EP055_DESIGN.md` Section 5's rejected "Candidate B: automatic inline
optimization") would require either (a) constructing `PluginService`
much earlier than every other EP that already depends on its current
position, a cross-cutting `Bootstrap` reordering this document does
not recommend attempting without explicit owner approval, or (b)
`AIService`/`PromptManager` computing the Capability Context lazily,
at request time, from a reference resolved after both are already
constructed — itself a change to `AIService.ask()`'s own call to
`PromptManager.build()`, which is currently untouched by both EP-054
and EP-055 and would be the first EP to modify it. This ordering
constraint is recorded here as a concrete, evidence-based reason
Section 5's recommended candidate scopes automatic wiring out of v1,
not as a hypothetical concern.

---

## 4. Non-goals (applicable regardless of which Section 5 candidate is chosen)

- **This document does not implement, and does not authorize STEP 2
  to implement, any usage/outcome-tracking, success-metric, or
  adaptive/statistical "learning" system that does not already exist**
  (Section 3.5). Building one from nothing is explicitly the kind of
  invented, ungrounded scope this task's own instructions and
  `AI_GENERATION_STANDARD.md`'s "Existing Code Policy" warn against.
- **No extension of the `CommandModule` Protocol.** Adding a
  `description`/`capabilities` member to the Protocol that every one
  of ~38 existing skills would then need to implement is a
  cross-cutting change to unrelated, already-shipped files this
  document does not recommend for a v1 (Section 3.1) — it is recorded
  as a possible, larger future direction, not built here.
- **No modification of the EP-010 Plugin system, the EP-017 Prompt
  Engine, `CommandRouter`, or `Bootstrap`'s existing construction
  order.** `Plugin`/`PluginManifest`/`PluginRegistry`/`PluginService`,
  `Prompt`/`PromptBuilder`/`PromptManager`, and `CommandRouter`'s
  existing public APIs are treated as fixed; EP-056 is additive to
  them, exactly as EP-054/EP-055 were additive to the components they
  each reused.
- **No automatic, unattended AI-provider usage of any kind is
  authorized by this document.** Section 5's recommended candidate
  involves no AI-provider call at all (it composes only already-
  declared, static metadata) — if a future candidate did call a
  provider, it would need the same bounded, rate-limited treatment
  `EP054_DESIGN.md`/`EP055_DESIGN.md` already required for their own
  AI-provider-consuming actions.
- **No automatic wiring into every `AIService.ask()` call in v1**
  (Section 3.8's ordering constraint) — recorded as a possible,
  larger future direction (Owner Decision D-equivalent in Section 20),
  not assumed or built here.
- **No cross-EP scope creep.** This document does not redesign or
  re-scope EP-054, EP-055, EP-057, or EP-058.

---

## 5. Candidate interpretations of "Capability Learning" (grounds for Owner Decision D1)

Each candidate is derived from an existing, already-inspected part of
the repository (Section 3), not invented from outside knowledge of
what "capability learning" might mean in the abstract. None is
authorized; Owner Decision D1 (Section 20) asks the owner to choose
one (or explicitly reject all of them and redirect this document).

### Candidate A — On-demand Capability Registry, finally giving the EP-017 "Capability Context" seam real content (recommended starting point)

A new, explicit, on-demand capability that composes a human/AI-
readable summary of Jarvis's currently-available capabilities from
already-existing, already-populated data — namely, each currently
`RUNNING`/enabled plugin's `id`/`name`/`description`/`capabilities`
(`PluginService.list_plugins()`/`running_plugins()`, Section 3.2) plus
the bare list of currently-registered `CommandRouter` namespaces
(`module_names()`, Section 3.1, disclosed as name-only, since no
richer per-skill description exists without a Protocol change this
document does not recommend, Section 4) — and exposes it two ways:
(1) a new `capability list` on-demand `CommandModule` action a user
can inspect directly; (2) the same composed text, **only when
explicitly requested by the caller** (not automatically on every
request, Section 3.8), passed as the `capabilities` argument to the
already-existing, currently-unused `PromptManager.build(capabilities=
...)` parameter — finally giving `append_capabilities()`'s own
"reserved for the future Capability Registry" docstring a real
caller.

**Why recommended:** this is the only candidate directly grounded in
an existing docstring that names the exact concept EP-056's own title
echoes ("Capability Registry," Section 3.3) — the strongest textual
anchor found across all three "bare title" EPs so far. It requires
zero new data model (reuses EP-010's already-validated
`Plugin.capabilities`), zero modification to EP-017's Prompt Engine,
EP-010's Plugin system, or `CommandRouter` (purely additive, reading
only their existing public APIs), and avoids Section 3.8's
construction-ordering problem entirely by never wiring itself into
the *automatic* per-request pipeline in v1. It also mirrors
`EP055_DESIGN.md` Section 5 Candidate A's own reasoning almost
exactly: smallest, most bounded, most easily tested, produces a
concrete, inspectable artifact, and exercises an already-built,
currently-idle seam instead of inventing a new one.

### Candidate B — Usage/outcome-based adaptive learning (rejected as a v1 candidate)

An interpretation closer to a literal reading of "Learning" as
statistical adaptation: track every `CommandRouter.dispatch()`
outcome (success/failure, frequency) per namespace/action, persist it
(e.g. via `MemoryService`, Section 3.6), and surface some derived
signal (e.g. "capability X has failed N times recently" or "capability
Y is rarely used") — potentially feeding that signal back into the
Prompt Engine or a future routing decision. **This document does not
recommend this candidate for v1**: Section 3.5 already confirmed zero
existing infrastructure of any kind for this (no metric, no
persistence schema, no adaptation policy), and building one from
nothing would be exactly the kind of invented, ungrounded scope
`EP055_DESIGN.md` already declined for its own structurally similar
"Candidate D" (per-provider optimization, Section 3.5 of that
document). It is recorded here to be explicitly rejected, not
silently omitted — the owner may of course choose it anyway (Owner
Decision D1), in which case this document would need substantial
revision to design a metric/persistence/adaptation scheme first.

### Candidate C — Manual capability curation command only (smaller fallback)

A narrower version of Candidate A that skips reading `PluginService`
entirely and instead lets a user manually register/describe
capabilities via a new command (e.g. `capability add "does X"`),
storing them via `MemoryService` (Section 3.6) for later
`PromptManager.build(capabilities=...)` injection. **Viable but
strictly worse-grounded than Candidate A**: it ignores real,
already-declared, already-validated data that already exists
(`Plugin.capabilities`, Section 3.2) in favor of asking the user to
re-type equivalent information by hand, and introduces a new,
hand-maintained data store for something a read-only composition of
existing data can already answer. Recorded as a fallback only if the
owner specifically wants to avoid depending on the Plugin system for
some reason not evidenced in the repository today.

### Candidate D — Extend the `CommandModule` Protocol with a `capabilities`/`description` member (rejected as a v1 candidate)

An interpretation where every one of ~38 existing skills is updated to
declare its own rich capability description via a new Protocol
member, giving Candidate A's registry a complete picture (not just
Plugin-provided capabilities, but every built-in skill's too).
**This document does not recommend this candidate for v1**: it is a
cross-cutting change touching every existing skill file — exactly the
kind of "modify unrelated files" this task's own instructions
prohibit without explicit direction, and a much larger surface than
either prior EP's own v1 scope. Recorded here to be explicitly
rejected, not silently omitted, and noted as a plausible *future*
extension of Candidate A once the owner has seen its smaller v1 in
practice.

---

## 6. Proposed architecture (contingent on Owner Decision D1 = Candidate A)

**Everything in this section and Sections 7-19 is provisional,
written against Section 5's recommended Candidate A, and is not
authorized until Owner Decision D1 (Section 20) is explicitly
approved.** If the owner selects a different candidate, or rejects
all of them, this document's STEP 1 must be revised before STEP 2 can
begin.

### 6.1 Namespace and module

A new `capability` `CommandModule`
(`src/skills/capability_registry/skill.py`, `CapabilityRegistryModule`),
dispatched through the *existing*, unmodified `CommandRouter.
dispatch()` (Section 3.7). Confirmed no existing namespace collision
(`capability` does not appear in Section 3.1's ~38-namespace list).

### 6.2 No new backend Protocol

Like EP-054's and EP-055's own Candidate A, Candidate A introduces no
new external I/O surface — it reads two already-existing, unmodified
components (`PluginService`, `CommandRouter`) via their existing
public APIs. This document proposes `CapabilityRegistryModule` depend
on `PluginService` and `CommandRouter` directly via constructor
injection, with **no new Protocol/backend abstraction**.

### 6.3 Command/action design (provisional)

| Action | Arguments | Description |
|---|---|---|
| `capability help` | none | List available actions. |
| `capability list` | none | Compose and return the current Capability Context summary: each currently `RUNNING`/enabled plugin's `id`, `name`, `description`, and `capabilities` tags (`PluginService.running_plugins()`), plus the bare list of currently-registered `CommandRouter` namespaces (`module_names()`). Read-only, no side effect. |
| `capability inject` | `<user prompt text>` | (Only if Owner Decision D2 authorizes this action) Compose the same summary as `capability list` and pass it, together with the given prompt text, through `PromptManager.build(user_prompt=..., capabilities=[summary])`, returning the assembled `Prompt.rendered` text for inspection — demonstrating the Capability Context seam end-to-end without sending anything to an AI provider. Never calls `AIProvider.ask()` itself (no AI-provider cost, no new safety gate needed beyond the master `capability_registry.enabled` flag). |

### 6.4 Integration points

- `PluginService.running_plugins()` (already-existing, unmodified,
  EP-010) — read-only, to compose the plugin-provided portion of the
  Capability Context.
- `CommandRouter.module_names()` (already-existing, unmodified) — to
  compose the bare-namespace portion.
- `PromptManager.build(capabilities=...)` (already-existing,
  unmodified, EP-017) — used only by the optional `capability inject`
  action (Owner Decision D2), and even then only to demonstrate
  assembly, never to call an AI provider or to insert itself into
  `AIService.ask()`'s own, separate call to the same method (Section
  3.8's ordering constraint means `CapabilityRegistryModule` cannot
  safely inject itself into every live request in v1 regardless; it
  can safely call `PromptManager.build()` a second, independent time
  for its own on-demand purposes, since `PromptManager` supports
  multiple, independent `Prompt` objects concurrently by design,
  confirmed unmodified).
- **No** integration with `AIService.ask()` in v1 (Section 3.8,
  Section 4) — this is the central architectural constraint of this
  entire document.
- **No** integration with `MemoryService` in v1 (Candidate A's output
  is composed fresh on every `capability list`/`capability inject`
  call, not persisted) — recorded as a plausible, small future
  addition (mirroring EP-054's own `persist_to_memory` opt-in
  pattern) but not part of this document's recommended v1 scope.
- **No** integration with `AgentEngine.register_subsystem()` proposed
  for v1, for the same reasoning EP-054's Owner Decision D6 and
  EP-055's Owner Decision D5 both already recorded: the subsystem
  registry has no concrete consumer for this capability today.

---

## 7. Security model (provisional, Candidate A)

- `capability_registry.enabled` (default `false`) — the master gate,
  re-checked on every dispatched `capability ...` action, identical in
  spirit to `reflection.enabled`/`prompt_optimizer.enabled`/
  `vision.enabled`/`file.enabled`/`browser.enabled`/`desktop.enabled`.
- **No AI-provider call exists anywhere in Candidate A** — unlike
  EP-054/EP-055, this candidate composes only already-declared,
  static metadata and never calls `AIProvider.ask()`. There is
  therefore no AI-provider-cost/privacy gate to design (no equivalent
  of EP-054/EP-055's own Owner Decision D2/D3 is needed).
- **No new filesystem write surface** — `PluginService`/
  `CommandRouter` are both read-only from `CapabilityRegistryModule`'s
  perspective; no `prompt save`/`allow_save`-equivalent gate is
  needed.
- **Information-disclosure consideration:** `capability list`
  discloses which plugins are currently running and their declared
  capability tags — information already fully visible today via the
  existing, unmodified `plugin status`/`plugin info` commands
  (`src/modules/plugin_module.py`, Section 3.2), so `capability list`
  discloses nothing that is not already disclosed by an existing,
  already-shipped command. This is a materially different situation
  from EP-055's own Finding 1 (a genuinely *new* disclosure surface) —
  recorded here explicitly so the owner can weigh in if they read it
  differently (Owner Decision D3, Section 20).
- **No shell/code execution, no network call** — `CapabilityRegistryModule`
  introduces no new I/O surface beyond the two already-existing,
  read-only method calls named in Section 6.4.

---

## 8. Configuration (provisional, Candidate A)

A new `capability_registry:` block in `config/config.yaml`, following
the established `enabled`-default-`false` convention:

```yaml
capability_registry:
  enabled: false
```

No resource/rate-limit keys are proposed (unlike `reflection.*`/
`prompt_optimizer.*`) because Candidate A performs no AI-provider call
and therefore has no provider-cost surface to bound (Section 7).

---

## 9. Dependencies

**No new third-party dependency is anticipated for Candidate A.**
`PluginService`/`CommandRouter`/`PromptManager` are already-installed,
already-imported, unmodified components; composing a summary string
from their existing return values requires only the standard library.
This document explicitly recommends **against** introducing any new
dependency for EP-056's v1.

---

## 10. Error handling (provisional, Candidate A)

- `CapabilityRegistryModule` performs no operation that can raise a
  new exception type — `PluginService.running_plugins()` and
  `CommandRouter.module_names()` are both already-existing, already-
  tested, exception-free (by their own established contracts) read
  accessors. `PromptManager.build()` (only reached by the optional
  `capability inject` action, Owner Decision D2) already raises
  `PromptValidationError`/`PromptTemplateNotFoundError` on its own
  established terms — both already-existing exception types would be
  reused, never re-implemented, exactly as `EP055_DESIGN.md` Section
  10 already established as the project's convention.
- If `capability_registry.enabled` is `false`, every action returns a
  clear, non-crashing failure message, matching every other skill's
  convention.

---

## 11. Cross-platform considerations

None anticipated — Candidate A performs no OS-specific I/O of any
kind (no device, no external binary, no filesystem write).

---

## 12. Testing strategy (provisional, Candidate A)

Mirrors the now-three-times-established convention
(`EP054_DESIGN.md`/`EP055_DESIGN.md` Section 12):

- **`tests/EP056/test_capability_registry.py`** (primary, always-run
  suite):
  - Protocol/argument-shape tests.
  - `capability_registry.enabled` gate tests (disabled rejects with
    zero calls to `PluginService`/`CommandRouter`).
  - Positive-path test using a fake `PluginService`/`CommandRouter`
    returning deterministic content, asserting the exact composed
    summary text.
  - Empty-state test (zero running plugins, zero registered
    namespaces beyond `capability` itself) — must not raise, must
    return a clear, non-empty message.
  - If Owner Decision D2 authorizes `capability inject`: a test
    asserting the exact `Prompt.rendered` text contains the composed
    Capability Context block, reusing the real, unmodified
    `PromptManager`/`PromptBuilder` (not a fake) — this is the one
    real, non-fake integration point Candidate A has, mirroring
    EP-055's own real, temporary-directory-backed template tests
    rather than mocking the one genuine integration surface.
  - `CommandRouter` dispatch-equivalence test, mirroring
    `EP054_DESIGN.md`'s/`EP055_DESIGN.md`'s own
    `_test_command_router_dispatch_matches_direct_execute`.
  - `Bootstrap` wiring tests (namespace registered even when
    disabled, disabled message reported, other modules unaffected).
- **No AI-provider-related test tier is needed at all** — Candidate A
  makes no AI-provider call (Section 7), so no Owner-Decision-D8-
  equivalent question about real-provider integration testing arises
  for this EP.

---

## 13. Regression strategy

Full regression suite (`test all`) re-run exactly as in every prior
EP's STEP 2/3, expecting the same, already-disclosed pre-existing
figures plus the new EP-056 suite passing cleanly, with zero change to
any other suite's result — in particular, zero change to any existing
EP-010 Plugin system or EP-017 Prompt Engine behavior, since Candidate
A adds no code to `plugin.py`/`plugin_manifest.py`/`plugin_service.py`/
`prompt.py`/`prompt_builder.py`/`prompt_manager.py` at all (Section
14).

---

## 14. File-scope matrix (provisional, Candidate A — NOT authorized until D1 is approved)

### CREATE

- `src/skills/capability_registry/skill.py` —
  `CapabilityRegistryModule`.
- `tests/EP056/__init__.py`, `tests/EP056/test_capability_registry.py`.

### MODIFY

- `src/bootstrap.py` — additive only: construct
  `CapabilityRegistryModule` (injected with the already-constructed
  `plugin_service` and `command_router`/`router`), gated by
  `capability_registry.enabled`, registered unconditionally with
  `CommandRouter`, following the identical wiring convention
  `EP054_DESIGN.md`/`EP055_DESIGN.md` Section 14 already established.
  **Construction-ordering note (Section 3.8):** since
  `CapabilityRegistryModule` depends on `plugin_service`, its
  registration must occur at or after line ~1906 (`plugin_service`'s
  own construction), not alongside `ai_provider_manager`/
  `prompt_manager` at line ~493/530 — a real, concrete placement
  constraint this document records so STEP 2 does not need to
  rediscover it.
- `config/config.yaml` — additive only: new `capability_registry:`
  block (Section 8).
- `src/modules/test_module.py` — additive only: one new import
  registering `tests.EP056.test_capability_registry`.

### DO NOT MODIFY

- `src/core/plugins/plugin.py`, `plugin_manifest.py`,
  `plugin_registry.py`, `plugin_loader.py`, `plugin_discovery.py`,
  `src/services/plugin_service.py` — **zero changes**; this is the
  central architectural constraint alongside the Prompt Engine
  restriction below. `CapabilityRegistryModule` calls only
  `PluginService.running_plugins()`, an already-existing, unmodified
  public method.
- `src/core/ai/prompt.py`, `src/core/ai/prompt_builder.py`,
  `src/core/ai/prompt_manager.py` — **zero changes**. Even the
  optional `capability inject` action (Owner Decision D2) only *calls*
  `PromptManager.build(capabilities=...)` with its already-existing
  signature — it does not modify any of these three files.
- `src/core/command_router.py` — zero changes; `module_names()` is
  called, never modified.
- `src/core/tool/` — zero changes (the same, now three-times-
  independently-confirmed limitation, Section 3.7).
- `src/services/ai_service.py` — zero changes; Candidate A never
  routes through `AIService.ask()` at all (Section 4/6.4).
- `src/skills/reflection/`, `src/skills/prompt_optimizer/`,
  `src/skills/desktop/`, `src/skills/browser/`, `src/skills/files/`,
  `src/skills/vision/`, and every other existing skill — zero
  changes; no candidate considered here proposes modifying any
  existing skill (Candidate D, Section 5, which would require this,
  is explicitly rejected for v1).
- `src/core/agent/`, `src/core/planning/`, `src/core/scheduler/`,
  `src/core/memory/` — zero changes; no candidate considered here
  proposes using any of them.
- Every EP-001…EP-055 design/audit document and every other prior
  EP's source/test files, and `JARVIS_ROADMAP.md`/`BACKLOG.md`/
  `CHANGELOG.md`/`RELEASE_NOTES.md` (STEP 1 does not update
  documentation per this task's own instruction).

---

## 15. Compatibility considerations

Fully additive under Candidate A — no existing manager's method
signature, return type, or behavior changes; no existing config key's
meaning or default changes; no existing `CommandModule` is affected;
the EP-010 Plugin system's and EP-017 Prompt Engine's existing
behavior for every other caller is unaffected, since
`CapabilityRegistryModule` only ever reads from them via already-
existing, unmodified public methods.

---

## 16. Implementation constraints

Bound by `AI_GENERATION_STANDARD.md` exactly as every prior EP was: no
architecture redesign, no invented API on `PluginService`/
`CommandRouter`/`PromptManager` ("Unknown API Policy"), one class one
responsibility, 300-line-recommended/500-line-hard file-size limit,
type hints, docstrings, no hardcoded credentials/paths.

---

## 17. Resource/operational limits

None beyond the single `capability_registry.enabled` gate (Section
7/8) — Candidate A has no AI-provider cost surface, no filesystem
write surface, and no rate-limit-worthy external call of any kind to
bound.

---

## 18. Acceptance criteria (for STEP 1)

- [x] Every roadmap/backlog/engineering-guide/prior-EP-docstring
  reference to EP-056/"Capability Learning" was found and quoted
  verbatim (Section 2) — not summarized from memory.
- [x] The genuine absence of a functional specification is reported
  explicitly, not silently filled (Section 0/2).
- [x] The existing EP-010 Plugin system, EP-017 Prompt Engine, and
  `CommandRouter` were inspected in depth specifically to ground
  candidate interpretations in what already exists, not outside
  knowledge (Section 3).
- [x] At least the minimum necessary Owner Decision to proceed (D1, a
  definitional choice among repository-grounded candidates) is
  presented, with three further candidates explicitly considered and
  either recommended, deferred, or rejected with reasoning (Section
  5).
- [x] A complete, provisional architecture is presented for the
  *recommended* candidate only, explicitly marked contingent on D1's
  approval (Sections 6-17), and explicitly does not modify the
  existing Plugin system or Prompt Engine (Section 14's DO NOT MODIFY
  list).
- [x] File scope is narrow, explicit, and auditable — no directory-
  level authorization (Section 14).
- [x] No source, test, configuration, dependency, or Bootstrap file
  was created or modified.
- [x] STEP 2 has not begun.

---

## 19. Unresolved questions this document does not answer

Recorded explicitly, per the task's instruction not to silently guess:

- Whether the owner even agrees "Capability Learning" should mean
  Candidate A at all — this is precisely Owner Decision D1, and this
  document's entire Sections 6-17 are void if the answer is anything
  else.
- Whether "Learning" in the EP's title was ever intended to mean
  genuine statistical adaptation (Candidate B) rather than the
  static, declarative "self-awareness of current capabilities"
  reading this document recommends (Candidate A) — no repository
  evidence resolves this either way; Section 3.5 already confirmed no
  metric/persistence/adaptation infrastructure exists today to build
  Candidate B against even if the owner wants it.
- Whether a future EP (EP-057 Memory Optimization, EP-058 Autonomous
  Planning) will expect Capability Registry's output in a specific,
  machine-readable format, or will want it wired automatically into
  every request — no such requirement exists anywhere in the
  repository today (mirroring `EP055_DESIGN.md`'s own, identically-
  worded open question about its own successors, Section 2), so this
  document assumes free-text output and on-demand-only invocation are
  sufficient for v1, flagged as revisitable.
- Whether extending the `CommandModule` Protocol (Candidate D) is a
  direction the owner wants pursued at all, now or later — recorded
  as rejected for v1 but not foreclosed permanently.
- Whether `capability` is the right `CommandRouter` namespace name,
  or whether something more specific (e.g. `capabilities`,
  `registry`) would read more naturally — recorded as part of Owner
  Decision D4.

---

## 20. Owner Decisions

**All seven decisions below (D1-D7) are APPROVED, exactly as
recommended, with no modification.** The "Recommended option" in each
decision below is therefore also the **approved option**. Sections
6-17's provisional architecture is confirmed as the approved
architecture for EP-056 v1's STEP 2.

### D1 — What does "Capability Learning" concretely mean for v1? (primary, definitional decision)

**Question:** Which of Section 5's candidate interpretations (or an
owner-supplied alternative not considered here) should EP-056 v1
actually build?
**Options:** (a) Candidate A — on-demand Capability Registry composing
already-declared Plugin capability data plus bare `CommandRouter`
namespace names, exposed via a new `capability list` command and,
optionally, wired into the already-existing, currently-unused
`PromptManager.build(capabilities=...)` seam on demand (recommended);
(b) Candidate B — usage/outcome-based adaptive learning (not
recommended — requires inventing a metric/persistence/adaptation
scheme from nothing, Section 3.5); (c) Candidate C — manual capability
curation command only, no Plugin-system integration (viable fallback
if the owner specifically wants to avoid depending on
`PluginService`); (d) Candidate D — extend the `CommandModule`
Protocol so every skill can self-describe (not recommended for v1 —
cross-cutting change to ~38 existing files, Section 3.1/4); (e) an
owner-supplied alternative, in which case this entire document would
need to be revised before STEP 2.
**Recommended option:** (a).
**Technical reasoning:** (a) is the only candidate directly grounded
in an existing docstring that names the exact concept EP-056's own
title echoes ("reserved for the future Capability Registry," Section
3.3) — the strongest textual anchor found across all three "bare
title" EPs so far. It requires zero new data model, zero modification
to the EP-010 Plugin system or EP-017 Prompt Engine, and avoids
Section 3.8's real, concrete `Bootstrap` construction-ordering problem
by never wiring itself into the automatic per-request pipeline in v1.
**Security impact:** (a) introduces exactly one gate
(`capability_registry.enabled`) and makes no AI-provider call at all
— the smallest security surface of any candidate considered,
including EP-054's/EP-055's own Candidate A; (b) would need its own,
new persistence/gating design; (c) has a similarly small surface to
(a) but a new, hand-maintained data store; (d) is unscoped until the
Protocol change itself is designed.
**Compatibility impact:** (a)/(c) are fully additive; (b) is
unscoped; (d) touches every existing skill file.
**What changes in STEP 2:** (a) → build exactly Section 14's file
scope. (b) → this document would need a full revision specifically
designing a usage-metric/persistence/adaptation scheme before STEP 2
could begin. (c) → Section 6/14 narrow to drop the `PluginService`
dependency, replaced by a new `MemoryService`-backed manual-entry
store. (d) → this document would need a full revision scoping the
`CommandModule` Protocol change and its ~38-file blast radius before
STEP 2 could begin.

### D2 — Include the optional `capability inject` demonstration action in v1, or `capability list` only?

**Question:** Should EP-056 v1 include the `capability inject <text>`
action (Section 6.3) that calls the real, unmodified
`PromptManager.build(capabilities=...)` to demonstrate the Capability
Context seam end-to-end, or should v1 ship only the simpler
`capability list` (composed summary text, no Prompt Engine call at
all)?
**Options:** (a) include `capability inject` (as proposed); (b)
`capability list`/`help` only in v1, with `capability inject` recorded
as a natural, low-risk fast-follow.
**Recommended option:** (a) — `capability inject` makes no AI-provider
call and modifies nothing (it only calls an already-existing,
read-only-with-respect-to-everything-except-its-own-return-value
method, `PromptManager.build()`, which registers the new `Prompt`
object in `PromptManager`'s own, already-existing, unmodified internal
registry exactly as every other caller's `build()` call already does)
— so the marginal risk over (b) is minimal, while (a) is the only way
to concretely demonstrate, in an automated test, that
`append_capabilities()`'s "reserved for the future Capability
Registry" docstring promise is now genuinely fulfilled end-to-end
rather than merely composed as a standalone string.
**Security impact:** negligible either way — `PromptManager.build()`
is already exercised, unmodified, by every other EP that calls it,
including options (a) here.
**Compatibility impact:** neither option modifies
`PromptManager`/`PromptBuilder` — the difference is only whether
`CapabilityRegistryModule` itself calls the already-existing method.
**What changes in STEP 2:** (a) → build both actions in Section 6.3's
table, and the "real, non-fake `PromptManager`" test noted in Section
12. (b) → drop `capability inject` from Section 6.3, and Section 12's
Prompt-Engine-integration test drops with it (a smaller v1 test
surface).

### D3 — Is `capability list`'s information disclosure acceptable given the existing `plugin status`/`plugin info` precedent?

**Question:** Section 7 argues `capability list` discloses nothing
`plugin status`/`plugin info` do not already disclose today. Does the
owner agree, or is there a reason (not evidenced in the repository
today) to treat aggregated capability disclosure differently from
per-plugin disclosure?
**Options:** (a) accept Section 7's reasoning — no additional gate
beyond `capability_registry.enabled` (as proposed); (b) require a
second, independent gate anyway (mirroring EP-055's own Owner
Decision D3 pattern, applied out of caution rather than a
repository-evidenced need).
**Recommended option:** (a).
**Security impact:** (a) is a single point of control, consistent
with the actual disclosure-equivalence finding; (b) adds a flag with
no corresponding new risk this document could identify.
**Compatibility impact:** none either way — new, independent config
key(s) regardless.
**What changes in STEP 2:** (a) → Section 8's config block as shown.
(b) → an additional `capability_registry.allow_list.enabled`-style key
(or equivalent), checked alongside `capability_registry.enabled`.

### D4 — Command namespace name

**Question:** Should the new `CommandModule` claim the `capability`
namespace (Section 6.1, singular, as currently proposed), or a
different name (e.g. `capabilities`, plural, or `registry`)?
**Options:** (a) `capability` (as proposed, e.g. `capability list`);
(b) `capabilities` (plural); (c) `registry`.
**Recommended option:** (a) — no existing `CommandRouter` namespace
collision was found for any of the three (Section 3.1's ~38-namespace
list contains none of them), and `capability` most directly echoes
the "Capability Registry" language EP-017's own docstrings already
use (Section 3.3).
**Security impact:** none either way.
**Compatibility impact:** none either way — purely cosmetic.
**What changes in STEP 2:** whichever name is approved is used
verbatim for the `CommandModule.name` property and every action in
Section 6.3's table.

### D5 — Bootstrap construction-ordering placement (Section 3.8/14)

**Question:** Section 3.8/14 identified that `CapabilityRegistryModule`
must be constructed at or after `plugin_service`'s own construction
(currently line ~1906 of `src/bootstrap.py`), not alongside
`ai_provider_manager`/`prompt_manager` (lines ~493/530). Does the
owner want `CapabilityRegistryModule` registered immediately after
`plugin_service`'s existing registration site (simplest, smallest
diff), or is there a reason to consider restructuring `Bootstrap`'s
construction order instead (a larger, cross-cutting change this
document does not recommend)?
**Options:** (a) register immediately after `plugin_service`/
`PluginModule`'s existing site (as proposed); (b) restructure
`Bootstrap`'s construction order so `plugin_service` (or capability
data more generally) is available earlier, enabling a future
automatic-injection design without this specific ordering constraint.
**Recommended option:** (a) — matches this document's own recommended
v1 scope (no automatic injection at all, Section 4/6.4), and (b) is a
larger, cross-cutting `Bootstrap` change with no concrete v1 consumer
to justify it yet.
**Security impact:** none either way.
**Compatibility impact:** (a) is a minimal, additive diff; (b) risks
disturbing every other service's own construction-order assumptions,
none of which this document has audited for reordering safety.
**What changes in STEP 2:** (a) → `CapabilityRegistryModule` is
constructed and registered directly after `plugin_service`'s existing
block. (b) → out of scope for this document entirely; would need its
own, separate design and audit.

### D6 — Real-`PromptManager` integration test for `capability inject` (Section 12, contingent on D2 = (a))

**Question:** If D2 approves `capability inject`, should its test
coverage call the real, unmodified `PromptManager`/`PromptBuilder`
(as Section 12 proposes, mirroring EP-055's own real,
temporary-directory-backed template tests) rather than a fake?
**Options:** (a) real `PromptManager`/`PromptBuilder`, asserting the
exact `Prompt.rendered` text (as proposed); (b) a fake/mocked
`PromptManager` instead.
**Recommended option:** (a) — this is the one place Candidate A
touches a shared, already-existing component in a way worth
proving genuinely works end-to-end, exactly as EP-055's own STEP 3
audit valued its real (non-fake) `--template` filesystem tests over
an all-fake alternative.
**Security impact:** none either way.
**Compatibility impact:** none either way.
**What changes in STEP 2:** (a) → the `capability inject` test
constructs a real `PromptManager` (with a minimal, real `Config`)
rather than a fake. (b) → a fake `PromptManager` double instead,
asserting only that `build(capabilities=[...])` was called with the
expected argument.

### D7 — `CommandRouter` vs. Tool Engine

**Question:** Restated per this project's own established practice
(Section 3.7) of never assuming a prior EP's answer still holds:
should `CapabilityRegistryModule` dispatch through `CommandRouter` (as
this document proposes) or attempt to use/extend Tool Engine?
**Options:** (a) `CommandRouter`, matching EP-050…EP-055 exactly; (b)
extend Tool Engine to support parameterized handlers first.
**Recommended option:** (a) — restated from Section 3.7; this is now
the third independent EP to reach the same conclusion for the same
reason (`Tool.handler`'s zero-argument-only signature).
**Security impact:** none either way.
**Compatibility impact:** (a) requires no `src/core/tool/` change; (b)
would be a cross-cutting change this EP is not authorized to make
unilaterally.
**What changes in STEP 2:** (a) → `CapabilityRegistryModule` registers
with `CommandRouter` exactly like every prior skill. (b) → not planned
by this document at all.

---

## Owner Approval Checklist

**Owner-approved on the date this section was updated, exactly as
recommended, with no modification to any option below.**

- [x] **D1** — What does "Capability Learning" concretely mean for
  v1? **APPROVED: Candidate A** — on-demand Capability Registry
  composing already-declared Plugin capability data plus
  `CommandRouter` namespace names.
- [x] **D2** — Include the optional `capability inject` demonstration
  action in v1? **APPROVED: yes.**
- [x] **D3** — Separate privacy/AI-provider gate for `capability
  list`? **APPROVED: no** — no additional gate beyond
  `capability_registry.enabled`.
- [x] **D4** — Command namespace name. **APPROVED: `capability`.**
- [x] **D5** — Bootstrap construction-ordering placement. **APPROVED:
  register immediately after `plugin_service`'s existing site.**
- [x] **D6** — Real vs. fake `PromptManager` for `capability inject`
  tests. **APPROVED: real, unmodified `PromptManager`.**
- [x] **D7** — `CommandRouter` vs. Tool Engine. **APPROVED:
  `CommandRouter`, matching EP-050…EP-055 exactly.**

**D8 (raised during STEP 3, not present in the original STEP 1
scope) — APPROVED, option (a).** The STEP 3 architecture audit
(`docs/architecture/audits/EP056_ARCHITECTURE_AUDIT.md` Section 17)
found a blocking defect: `src/bootstrap.py` passed `router.
module_names` (a `@property`, evaluated eagerly) where
`CapabilityRegistryModule`'s own documented constructor contract
required a live callable, causing every `capability list`/`capability
inject` call to fail with `TypeError` in real production wiring. The
owner approved fixing this in STEP 4. The fix (a single-line change
confined to `src/bootstrap.py`, `module_names=router.module_names` →
`module_names=lambda: router.module_names`), independent verification
that it is genuinely resolved, and the final status are recorded in
`EP056_ARCHITECTURE_AUDIT.md` Section 18. This does not alter D1-D7
or any part of Candidate A's approved scope (Sections 6-17 above) —
it is a wiring correction confined to how one already-approved
dependency is passed to the already-approved `CapabilityRegistryModule`.
