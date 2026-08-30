# EP-054 — Self Reflection — Design Specification (STEP 1)

Status: **STEP 1 — DESIGN COMPLETE / OWNER APPROVAL REQUIRED**

**STEP 2 implementation has NOT begun.**

No source file, test file, configuration file, dependency file, or
Bootstrap file has been created or modified as part of producing this
document. The only artifact created by EP-054 STEP 1 is this document
itself, `docs/architecture/designs/EP054_DESIGN.md`.

---

## 0. A note on how this document differs from EP-050/051/052/053's

EP-050 through EP-053 each began with a roadmap line that named a
concrete, well-understood capability ("Computer Use", "Browser
Automation", "File Automation", "Vision Integration") whose scope,
while still requiring Owner Decisions on implementation detail, was
never in doubt at the conceptual level. **EP-054 is different.**
Direct inspection of every roadmap/backlog/engineering-guide document
in this repository (Section 2) found that "EP-054 Self Reflection"
has **no functional specification anywhere** beyond its four-word
title and Phase 9's one-sentence phase-level goal ("Improve reasoning
and autonomous decision making"). This is disclosed here plainly,
per the task's own instruction, rather than silently inventing a
scope that merely "seems technically interesting."

Consequently, this document's primary Owner Decision (D1, Section
20) is **definitional, not implementational** — it asks the owner to
choose *what Self Reflection concretely does*, among several
candidate interpretations this document derives from the repository's
own existing architecture and naming precedent (Section 5), not from
guesswork. Every other section of this document (architecture,
file scope, testing, etc.) is written against D1's *recommended*
option, explicitly marked as provisional and contingent on that
choice — not as an already-decided implementation plan.

---

## 1. Metadata

- **Engineering Package:** EP-054 — Self Reflection
- **Phase:** Phase 9 — Intelligence (`JARVIS_ROADMAP.md` line 587;
  `ENGINEERING_GUIDE.md`: "Improve reasoning and autonomous decision
  making")
- **Predecessor:** EP-053 Vision Integration — **COMPLETE / PASSED
  WITH FINDINGS** (`docs/architecture/audits/EP053_ARCHITECTURE_AUDIT.md`,
  `CHANGELOG.md` `v0.1.12-ep053`)
- **Successors (same phase):** EP-055 Prompt Optimizer, EP-056
  Capability Learning, EP-057 Memory Optimization, EP-058 Autonomous
  Planning
- **This document's scope:** STEP 1 only — repository discovery,
  scope clarification, architecture proposal (contingent on Owner
  Decision D1), and Owner Decision preparation. No code, test,
  configuration, dependency, or Bootstrap file has been created or
  modified as part of producing this document.
- **File created by STEP 1:** this document,
  `docs/architecture/designs/EP054_DESIGN.md`, only.
- **Files modified by STEP 1:** none.

---

## 2. What the repository actually says about EP-054 (verbatim inventory)

Every reference to EP-054 or "Self Reflection" found anywhere in the
repository, found by direct, exhaustive search (not sampling) of
`docs/`, `AI_GENERATION_STANDARD.md`, and `src/`:

| Location | Exact content |
|---|---|
| `docs/architecture/JARVIS_ROADMAP.md` line 589 (Phase 9 list) | `EP-054 Self Reflection` — a bare title, no elaboration |
| `docs/architecture/JARVIS_ROADMAP.md` line 183 ("Current" section, added by EP-053 STEP 4) | `**Next Engineering Package: EP-054 Self Reflection — NOT STARTED.** No EP-054 design, research, or implementation work has begun.` — a status pointer, not a spec |
| `docs/BACKLOG.md` lines 13-18 ("Next Engineering Package" section, added by EP-053 STEP 4) | Same "NOT STARTED" pointer, same lack of elaboration |
| `docs/engineering/ENGINEERING_GUIDE.md` (Phase 9 section) | `## Phase 9 — Intelligence` / `Improve reasoning and autonomous decision making.` / `Engineering Packages:` / `EP-054 … EP-058` — a **phase-level** goal shared across all five Phase-9 EPs, not an EP-054-specific one |
| `src/core/agent/agent_engine.py` (EP-028 module docstring, "No AI provider, no Planner, no Reasoning Engine, **no Reflection Engine**, no Workflow Engine, ...") | Confirms "Reflection Engine" was already anticipated, by name, as a *future*, not-yet-built subsystem at the time EP-028 (Agent Framework) was written — naming precedent only, no functional detail |
| `src/core/planning/planning_engine.py` (EP-029 module docstring, "No AI provider, no prompt engine, no execution engine, **no reflection**, ...") | Same naming precedent, same lack of functional detail |
| Everywhere else (`PROJECT_MANIFEST.md`, `AI_GENERATION_STANDARD.md`, `AI_DEVELOPMENT_PLAYBOOK.md`, `JARVIS_ARCHITECTURE_VISION.md`, every EP-050/051/052/053 design/audit document) | **Zero** additional mention of EP-054 or "Self Reflection" of any kind |

**Conclusion:** the repository establishes *that* Self Reflection is
next, and *that* it belongs conceptually to "Intelligence" alongside
reasoning/autonomous decision-making, and confirms (via two
independent EP-028/029 non-goal statements) that a "Reflection
Engine" was always envisioned as a distinct subsystem name — but it
establishes **no concrete behavior, input, output, trigger, or user
interface** for it. Per the task's explicit instruction, this gap is
reported here rather than silently filled.

---

## 3. Relevant existing architecture (grounds for the candidate interpretations in Section 5)

Direct inspection, to ground Section 5's candidates in what actually
exists rather than in the abstract:

### 3.1 Phase 7/8 precedent: `CommandModule` skills (EP-046…EP-053)

`desktop`, `browser`, `file`, `vision` are each a `CommandModule`
(`src/core/command_router.py`'s `Protocol`) registered with
`CommandRouter`, each backed by a Protocol-typed backend
(`ComputerUseBackend`/`BrowserBackend`/`FileBackend`/`VisionBackend`),
each gated by an `<namespace>.enabled` config flag re-checked on
every dispatch, each with a fake-backend + real-backend two-tier test
suite. This pattern is now used four times independently
(Section 5.2 of `EP053_DESIGN.md` already documented this
convergence) and is the natural default for **any new, discrete,
user-invokable capability** — Section 5.2 below examines whether
Self Reflection fits this shape.

### 3.2 Phase 3-6 precedent: `Service`-style subsystems registered with Agent Framework

Distinct from Section 3.1's pattern, `src/bootstrap.py` (lines
~767-786) registers a *different* set of components — `embedding`,
`rag`, `memory`, `knowledge`, `long_term_memory`, `semantic`,
`compression` — as **Agent Framework subsystems**, via
`AgentEngine.register_subsystem(name, status_check=...)`. This is a
lightweight, status-only registration (a name plus a zero-argument
`status_check` callable returning whether the subsystem is enabled) —
it does **not** give the Agent Framework the ability to *invoke* the
subsystem, only to *report on* it (`AgentEngine.list_subsystems()`).
Confirmed by direct inspection: `desktop`/`browser`/`file`/`vision`
(Section 3.1's `CommandModule`s) are **not** registered as Agent
subsystems today — this registry is used exclusively for the
Phase 3-6 "Intelligence-adjacent" services that predate Phase 7/8.
This is a meaningful, non-obvious precedent split this document
surfaces as part of Owner Decision D6 (Section 20): if Self
Reflection is conceptually an "Intelligence" capability rather than a
"skill", it may belong in *this* registry pattern instead of (or in
addition to) Section 3.1's.

### 3.3 `ConversationManager` (`src/core/ai/conversation_manager.py`, EP-016) — a plausible reflection input

`ConversationManager.current()` returns the active `Conversation`
object, which holds an ordered `Message` list
(`src/core/ai/conversation.py`) with a configurable `max_messages`
retention policy. This is the most direct, already-existing source of
"what has Jarvis (and the operator) been doing/saying recently" — a
natural candidate input for any interpretation of "reflection" that
means reviewing recent interaction (Section 5, Candidate A/B).

### 3.4 `MemoryManager` (`src/core/memory/memory_manager.py`, EP-023) — a plausible reflection output store

A provider-independent key/value store (`store`/`load`/`delete`/
`list`, namespaced) already used for durable, cross-session state.
This is a natural candidate destination for persisting a reflection's
output (a "lesson learned" note, a self-critique summary) so it can
be recalled in a later session — relevant to Candidate A/C (Section
5) and to EP-057 Memory Optimization's own stated future scope
("Improve reasoning" via better memory use), which this document
does not build, but whose existence suggests Self Reflection's output
is meant to eventually feed *that* EP, not necessarily to
auto-modify anything itself in v1 (Owner Decision D3, Section 20).

### 3.5 `AIProvider` (`src/core/ai/provider.py`, EP-014/015) — how a reflection would actually be generated

`AIProvider.ask(prompt: str, max_tokens: int | None = None) ->
ProviderResponse` is the only mechanism in this repository for
producing free-text, reasoning-shaped output from an LLM. Any
interpretation of "Self Reflection" that involves the AI critiquing
its own recent behavior (rather than a purely mechanical/statistical
report) will need to call this existing, unmodified method — exactly
as `EP053_DESIGN.md` Section 5.5 already established `ask()` is
text-only and requires no signature change for a text-in/text-out
reflection prompt (unlike EP-053's *deferred* image-input question).
No `AIProvider` change of any kind is anticipated by this document,
under any Owner Decision below.

### 3.6 `Scheduler` (`src/core/scheduler/scheduler.py`, EP-034) — a plausible trigger mechanism

Already supports registering, starting, stopping, and ticking
recurring `Job`s. A natural candidate for a Self Reflection capability
that runs periodically ("reflect on the last day's sessions every
night") rather than only on manual request — relevant to Owner
Decision D5 (Section 20).

### 3.7 `Tool Engine` (`src/core/tool/`, EP-031) — the same, now five-times-independently-confirmed limitation

`Tool.handler` remains zero-argument-only (confirmed unchanged by
EP-050/051/052/053, each independently reaching the same conclusion —
see `EP053_DESIGN.md` Section 5.4). If Self Reflection's v1 interface
needs even one argument (e.g. a message-count window, a target
conversation name), this limitation applies a fifth time (Owner
Decision D8, Section 20) — presented again for explicit confirmation
per this project's own established practice of never assuming a
prior EP's answer still holds without re-asking.

---

## 4. Non-goals (applicable regardless of which Section 5 candidate is chosen)

- **This document does not implement, and does not authorize STEP 2
  to implement, any autonomous behavior-modification.** Whatever
  Section 5's chosen candidate produces, it is descriptive/advisory
  output for a human (or a later EP) to act on — it never
  automatically changes a prompt, a configuration value, an agent's
  behavior, or any other EP's code or state. That capability, if ever
  built, belongs to EP-055 Prompt Optimizer, EP-056 Capability
  Learning, or EP-058 Autonomous Planning by the roadmap's own
  sequencing (Section 1) — not to EP-054.
- **No new AI provider, no change to `AIProvider`'s existing
  contract** (Section 3.5) — reflection generation, if it uses an AI
  provider at all, uses the existing `ask()` method unmodified.
- **No modification of `ConversationManager`, `MemoryManager`,
  `Scheduler`, `AgentEngine`, or any other Section 3 component's own
  behavior.** EP-054 reads from/writes to these components through
  their existing public APIs only, exactly as `VisionModule` never
  modified `FileBackend` while still being informed by its allow-list
  pattern (`EP053_DESIGN.md` Section 7).
- **No autonomous, unattended, budget-uncapped AI-provider usage.**
  Any reflection that calls `AIProvider.ask()` must be triggered by an
  explicit, bounded action (a manual command or a rate-limited
  scheduled job, Owner Decision D5) — never an unbounded loop.
- **No cross-EP scope creep.** This document does not redesign or
  re-scope EP-055/056/057/058; it only notes, where relevant, that a
  given Self Reflection candidate's output is a plausible *future*
  input to one of them (Section 3.4), without building that
  integration itself.

---

## 5. Candidate interpretations of "Self Reflection" (grounds for Owner Decision D1)

Each candidate is derived from an existing, already-inspected part of
the repository (Section 3), not invented from outside knowledge of
what "AI self-reflection" might mean in the abstract. None is
authorized; Owner Decision D1 (Section 20) asks the owner to choose
one (or explicitly reject all of them and redirect this document).

### Candidate A — Session/conversation self-critique (recommended starting point)

A new, explicit, on-demand action (e.g. `reflect summary [n]`) that
takes the last *n* messages of the current (or a named)
`Conversation` (Section 3.3), sends them to the configured AI
provider via `AIProvider.ask()` (Section 3.5) with a fixed,
reflection-oriented prompt template ("review this exchange; what
went well, what could be improved, what should be remembered for next
time"), and returns the critique as a `CommandResult` — optionally
persisting it to `MemoryManager` (Section 3.4) under a dedicated
namespace (e.g. `reflection`) for later recall. Mirrors Section 3.1's
`CommandModule` pattern almost exactly (a `ReflectionModule`, no new
backend Protocol needed since it composes two already-existing
managers rather than a new external system, unlike
`desktop`/`browser`/`file`/`vision` which each needed a new Protocol
for a genuinely new I/O surface).

**Why recommended:** smallest, most bounded, most easily tested
interpretation; reuses three already-existing, unmodified components
(`ConversationManager`, `AIProvider`, `MemoryManager`); has an
obvious default-off, default-deny security/cost posture (Owner
Decisions D2/D5); and produces a concrete, inspectable artifact
(the critique text) rather than an abstract, hard-to-test "reasoning
improvement."

### Candidate B — Agent/tool-execution failure review

A capability that inspects the Agent Framework's/Tool Engine's own
recent execution history (successes/failures of dispatched tool
calls) and produces a structured report of what failed and why —
closer to the `AgentEngine`/`ToolEngine`-facing "Reflection Engine"
name from Section 2's EP-028/029 non-goal statements. **Blocked by a
real gap**, confirmed by inspection: neither `AgentEngine` nor
`src/core/tool/` currently persists a queryable execution/failure
history anywhere (`AgentEngine` only exposes live subsystem status,
Section 3.2; `Tool Engine` dispatches synchronously with no logged
history store). Building this candidate would require a new
execution-history persistence layer as a prerequisite — a
materially larger, cross-cutting change this document does not
recommend attempting inside EP-054 itself without a separate, explicit
Owner Decision authorizing that prerequisite.

### Candidate C — Scheduled, periodic self-assessment

Similar output to Candidate A, but triggered by `Scheduler`
(Section 3.6) on a recurring basis rather than on manual request,
summarizing a longer window (e.g. "reflect on today's sessions,
nightly"). Viable, but strictly a superset of Candidate A's core
generation logic plus a `Scheduler` `Job` registration — this document
recommends treating scheduled triggering as an *additive*, later
refinement of Candidate A (Owner Decision D5) rather than a
separate candidate to choose between.

### Candidate D — General "reasoning quality" self-scoring (rejected as a v1 candidate)

An interpretation where Jarvis scores its own reasoning quality
against some rubric, independent of any specific conversation or
tool-execution history. **This document does not recommend this
candidate for v1**: no existing component in this repository defines
or stores any such rubric, no existing EP references one, and
building one from nothing would be exactly the kind of
"invent[ed]... because it seems technically interesting" scope this
task explicitly warns against (Section 2 of the task prompt). This
candidate is recorded only to be explicitly rejected, not silently
omitted.

---

## 6. Proposed architecture (contingent on Owner Decision D1 = Candidate A)

**Everything in this section and Sections 7-19 is provisional,
written against Section 5's recommended Candidate A, and is not
authorized until Owner Decision D1 (Section 20) is explicitly
approved.** If the owner selects a different candidate, or rejects
all of them, this document's STEP 1 must be revised before STEP 2 can
begin — this document does not pre-authorize a fallback path.

### 6.1 Namespace and module

A new `reflect` `CommandModule` (`src/skills/reflection/skill.py`,
`ReflectionModule`), dispatched through the *existing*, unmodified
`CommandRouter.dispatch()` — the same, now five-times-independently-
applied pattern (Section 3.1/3.7).

### 6.2 No new backend Protocol

Unlike `desktop`/`browser`/`file`/`vision`, Candidate A introduces no
new external I/O surface (no new device, browser, filesystem, or
image-decoding library) — it *composes* two already-existing,
unmodified managers (`ConversationManager`, `AIProvider`) and
optionally a third (`MemoryManager`). This document proposes
`ReflectionModule` depend on these three managers directly via
constructor injection (mirroring how `AgentService`/`PlanningService`
already receive their own dependencies in `src/bootstrap.py`), with
**no new Protocol/backend abstraction** — introducing one here, for
components that are already Protocol-free, well-tested managers in
their own right, would be exactly the kind of unnecessary,
speculative abstraction `AI_GENERATION_STANDARD.md`'s YAGNI principle
warns against. **This itself is presented as part of Owner Decision
D1's implementation consequences, not a separate decision** — a
different Candidate (B, in particular) would very plausibly require a
new backend/Protocol layer.

### 6.3 Command/action design (provisional)

| Action | Arguments | Description |
|---|---|---|
| `reflect help` | none | List available actions. |
| `reflect summary [count]` | optional message count (default from config) | Generate a self-critique of the last `count` messages of the *current* conversation via `AIProvider.ask()`, return it as `CommandResult.message`. |
| `reflect recall [count]` | optional count | Return the last `count` previously generated and persisted reflections from `MemoryManager`'s `reflection` namespace (only if Owner Decision D4 authorizes persistence). |

### 6.4 Integration points

- `ConversationManager.current()` → `Conversation` → its message list
  (read-only; `ReflectionModule` never mutates a conversation).
- `AIProvider.ask(prompt, max_tokens=...)` via the existing
  `ProviderManager`'s active provider — no new provider-selection
  logic; `ReflectionModule` uses whichever provider is already
  configured, exactly as any other AI-provider-consuming module would.
- `MemoryManager.store()/load()` under a dedicated `reflection`
  namespace — only if Owner Decision D4 authorizes persistence.
- **No** integration with `AgentEngine.register_subsystem()`
  (Section 3.2) proposed for v1 — recorded as a possible, separate,
  later addition (Owner Decision D6), not built here.

---

## 7. Security model (provisional, Candidate A)

- `reflection.enabled` (default `false`) — the master gate, re-checked
  on every dispatched action, identical in spirit to
  `vision.enabled`/`file.enabled`/`browser.enabled`/`desktop.enabled`.
- **AI-provider cost/privacy gate, separate from `reflection.enabled`**
  (mirrors `EP053_DESIGN.md` Section 11.3's own precedent for
  `vision.ai_description.enabled`): every `reflect summary` call sends
  the last *n* conversation messages to whichever AI provider is
  currently configured — this is genuinely new data leaving the
  process boundary (to the provider, exactly as any other `ask()`
  call already does, but now containing potentially sensitive
  conversation history the operator may not expect to be
  re-summarized). This document recommends **no second, separate
  gate** beyond `reflection.enabled` itself (Owner Decision D2),
  since sending conversation content to the already-configured AI
  provider is not qualitatively different from what every other
  AI-provider-consuming feature in this repository already does
  (`ask`/`conversation` itself) — unlike EP-053's `vision describe`,
  which would have been the *first* time image bytes left the
  machine. This reasoning is recorded explicitly so the owner can
  override it if they disagree (Owner Decision D2).
- **Resource/rate limits** — `reflection.max_message_count` (bounds
  how much conversation history one `reflect summary` call may
  include, protecting both `AIProvider` token cost and prompt size)
  and `reflection.min_seconds_between_calls` (a simple, in-process
  rate limit protecting against rapid, repeated manual invocation
  running up AI-provider cost) — Owner Decision D7.
- **No shell/code execution, no filesystem access, no network call
  beyond the already-existing `AIProvider` call** — `ReflectionModule`
  introduces no new I/O surface (Section 6.2).

---

## 8. Configuration (provisional, Candidate A)

A new `reflection:` block in `config/config.yaml`, following the
established `enabled`-default-`false` convention:

```yaml
reflection:
  enabled: false
  max_message_count: 20
  min_seconds_between_calls: 30
  persist_to_memory: false   # Owner Decision D4
```

---

## 9. Dependencies

**No new third-party dependency is anticipated for Candidate A.**
`ConversationManager`, `AIProvider`, and `MemoryManager` are all
already-installed, already-imported, unmodified components; `ask()`
already returns free text with no new parsing library required.
This document explicitly recommends **against** introducing any new
dependency for EP-054's v1, and flags that if a future Owner Decision
revision selects Candidate B or D instead, that recommendation would
need to be revisited (Section 5's own text already notes Candidate B
would first require a new execution-history persistence layer, which
might justify a dependency this document has not evaluated).

---

## 10. Error handling (provisional, Candidate A)

- `ReflectionModule` catches exactly one exception type from each
  dependency it calls — `ConversationManager`'s own
  `ConversationManagerError`/`ConversationNotFoundError` and
  `AIProvider`'s own `ProviderUnavailableError`/
  `ProviderConfigurationError` (both already exist, Section 3.5) —
  translating each into a failed `CommandResult`, never an uncaught
  exception, mirroring every prior skill's convention.
- If `reflection.enabled` is `false`, or no conversation is currently
  active, or the configured AI provider is unavailable, `reflect
  summary` returns a clear, non-crashing failure message.

---

## 11. Cross-platform considerations

None anticipated — Candidate A introduces no OS-specific I/O of any
kind (no filesystem, no device, no external binary), unlike
`desktop`/`browser`/`vision`. Purely in-process composition of
already-cross-platform managers.

---

## 12. Testing strategy (provisional, Candidate A)

Mirrors the now-established two-tier convention
(`EP053_DESIGN.md` Section 16/20, Owner Decision D10):

- **`tests/EP054/test_reflection.py`** (primary, always-run suite):
  - Protocol/argument-shape tests (wrong argument count for
    `reflect summary`).
  - `reflection.enabled` gate tests (disabled rejects with zero calls
    to `AIProvider`/`ConversationManager`).
  - Rate-limit tests (`min_seconds_between_calls`) using a fake clock,
    not a real `time.sleep()`.
  - Message-count-cap tests (`max_message_count`) using a fake
    `ConversationManager` with a conversation longer than the cap.
  - Positive-path test using a fake `AIProvider`/`ConversationManager`
    returning deterministic content, asserting the exact prompt
    constructed and the exact `CommandResult` produced.
  - Negative/security cases: no active conversation, provider
    unavailable, provider raises a configuration error.
  - `CommandRouter` dispatch-equivalence test (mirrors
    `EP053_DESIGN.md`'s own `_test_command_router_dispatch_matches_direct_execute`).
  - `Bootstrap` wiring tests (namespace registered even when disabled,
    disabled message reported, other modules unaffected) — mirroring
    `EP053_DESIGN.md` Section 16's own Bootstrap-wiring tier exactly.
- **No separate "real integration" tier is anticipated** (unlike
  EP-053's real-Tesseract script) **unless** Owner Decision D4
  authorizes real `MemoryManager` persistence, in which case a small,
  real-`MemoryManager`-backed test (no fake) would be added to the
  *primary* suite itself — `MemoryManager` has no external-binary
  dependency the way Tesseract did, so no separate, unregistered tier
  is needed for it.
- **Real-`AIProvider` end-to-end test:** explicitly **not** proposed
  for the default suite (would require live, costed API credentials
  and non-deterministic model output — unlike EP-053's OCR, which
  could be verified deterministically against a fixed, exact rendered
  string). If the owner wants one, it should be a separate,
  intentionally unregistered script, following EP-053's own
  precedent, and is recorded here as an open question (Section 21)
  rather than assumed.

---

## 13. Regression strategy

Full regression suite (`test all`) re-run exactly as in every prior
EP's STEP 2/3, expecting the same, already-disclosed EP-046/048/049
pre-existing figures (Section 9 of `EP053_ARCHITECTURE_AUDIT.md`) plus
the new EP-054 suite passing cleanly, with zero change to any other
suite's result.

---

## 14. File-scope matrix (provisional, Candidate A — NOT authorized until D1 is approved)

### CREATE

- `src/skills/reflection/skill.py` — `ReflectionModule`.
- `tests/EP054/__init__.py`, `tests/EP054/test_reflection.py`.

**Note:** unlike EP-050/051/052/053, this document does **not**
propose a `backend.py`/`local_backend.py` pair (Section 6.2) — if the
owner disagrees and wants a Protocol-based abstraction even for
Candidate A (e.g. to ease future swapping of the reflection-generation
mechanism), that should be raised as a revision to Owner Decision D1
before STEP 2, not assumed.

### MODIFY

- `src/bootstrap.py` — additive only: construct `ReflectionModule`
  (injected with `ConversationManager`, `ProviderManager`/`AIProvider`,
  and — only if D4 authorizes it — `MemoryManager`), gated by
  `reflection.enabled`, registered unconditionally with
  `CommandRouter`, following the identical wiring convention Section
  5.12 of `EP053_DESIGN.md` already documented.
- `config/config.yaml` — additive only: new `reflection:` block
  (Section 8).
- `src/modules/test_module.py` — additive only: one new import
  registering `tests.EP054.test_reflection`.

### DO NOT MODIFY

- `src/core/command_router.py` — zero changes (Section 3.7).
- `src/core/tool/` — zero changes (Section 3.7).
- `src/core/ai/provider.py`, `src/core/ai/conversation_manager.py`,
  `src/core/ai/conversation.py` — zero changes; used strictly through
  their existing, unmodified public APIs (Section 3.3/3.5).
- `src/core/memory/` — zero changes; used strictly through its
  existing, unmodified public API (Section 3.4), only if D4 authorizes
  use at all.
- `src/core/agent/`, `src/core/planning/` — zero changes; Section 3.2's
  subsystem-registry integration is explicitly not built in v1 unless
  a revised Owner Decision D6 authorizes it.
- `src/core/scheduler/` — zero changes; Candidate C's scheduled-
  trigger refinement (Section 5) is not built in v1.
- `src/skills/desktop/`, `src/skills/browser/`, `src/skills/files/`,
  `src/skills/vision/` — zero changes; no relationship to Self
  Reflection in any candidate considered.
- Every EP-050/051/052/053 design/audit document and every other
  prior EP's source/test files.

---

## 15. Compatibility considerations

Fully additive under Candidate A — no existing manager's method
signature, return type, or behavior changes; no existing config key's
meaning or default changes; no existing `CommandModule` is affected.

---

## 16. Implementation constraints

Bound by `AI_GENERATION_STANDARD.md` exactly as every prior EP was:
no architecture redesign, no invented API on `ConversationManager`/
`AIProvider`/`MemoryManager`, one class one responsibility, 300-line-
recommended/500-line-hard file-size limit, type hints, docstrings, no
hardcoded credentials/paths.

---

## 17. Resource/operational limits

`reflection.max_message_count` and `reflection.min_seconds_between_calls`
(Section 7/8) are the only two operational limits Candidate A
introduces — both are new, independent config keys with no
interaction with any other EP's own limits (e.g. `vision.max_dimension`,
`file.allowed_roots`).

---

## 18. Acceptance criteria (for STEP 1)

- [x] Every roadmap/backlog/engineering-guide/prior-EP-docstring
  reference to EP-054/"Self Reflection"/"Reflection Engine" was
  found and quoted verbatim (Section 2) — not summarized from memory.
- [x] The genuine absence of a functional specification is reported
  explicitly, not silently filled (Section 0/2).
- [x] At least the minimum necessary Owner Decision to proceed (D1,
  a definitional choice among repository-grounded candidates) is
  presented, with three further candidates explicitly considered and
  either recommended, deferred, or rejected with reasoning (Section
  5).
- [x] A complete, provisional architecture is presented for the
  *recommended* candidate only, explicitly marked contingent on D1's
  approval (Sections 6-17).
- [x] File scope is narrow, explicit, and auditable — no directory-
  level authorization (Section 14).
- [x] No source, test, configuration, dependency, or Bootstrap file
  was created or modified.
- [x] STEP 2 has not begun.

---

## 19. Unresolved questions this document does not answer

Recorded explicitly, per the task's instruction not to silently guess:

- Whether the owner even agrees "Self Reflection" should mean
  Candidate A at all — this is precisely Owner Decision D1, and this
  document's entire Sections 6-17 are void if the answer is anything
  else.
- Whether a future EP-055/056/057/058 will expect Self Reflection's
  output in a specific, machine-readable format (e.g. structured JSON
  rather than free text) — no such requirement exists anywhere in the
  repository today (Section 2), so this document assumes free-text
  output is sufficient for v1, but flags that a future EP could
  require revisiting this.
- Whether real, live-provider end-to-end testing is wanted at all
  (Section 12's last bullet) — recorded as an open question rather
  than decided either way.

---

## 20. Owner Decisions

**None of the following are approved. STEP 2 will not begin until
they are explicitly reviewed — and, most importantly, D1 must be
resolved before Sections 6-17's provisional architecture can be
treated as anything more than a starting proposal.**

### D1 — What does "Self Reflection" concretely mean for v1? (primary, definitional decision)

**Question:** Which of Section 5's candidate interpretations (or an
owner-supplied alternative not considered here) should EP-054 v1
actually build?
**Options:** (a) Candidate A — session/conversation self-critique on
demand; (b) Candidate B — agent/tool-execution failure review
(requires a new execution-history persistence prerequisite this
document has not designed); (c) Candidate C — scheduled/periodic
self-assessment (treated here as an additive refinement of (a), not a
separate base); (d) Candidate D — general reasoning-quality
self-scoring (not recommended, no grounding found in the repository);
(e) an owner-supplied alternative, in which case this entire document
would need to be revised before STEP 2.
**Recommended option:** (a), optionally with (c) as a fast-follow
within the same EP if the owner wants it included in v1's initial
scope rather than as a later refinement.
**Technical reasoning:** (a) is the only candidate that requires zero
new persistence layer, zero new Protocol/backend abstraction, and
composes exclusively already-existing, unmodified, already-tested
managers (Section 3.3/3.4/3.5) — the smallest possible surface area
consistent with the roadmap's stated Phase 9 goal.
**Security impact:** (a) introduces exactly one new gate
(`reflection.enabled`) and reuses `AIProvider`'s already-reviewed
call path; (b) would need a new execution-history store with its own,
unreviewed security model; (c) inherits (a)'s; (d) is unscoped and
cannot be security-reviewed until it has content.
**Compatibility impact:** (a)/(c) are fully additive; (b) is fully
additive but larger; (d) is undefined.
**What changes in STEP 2:** (a) → build exactly Section 14's file
scope. (b) → this document would need a full revision adding an
execution-history persistence design before STEP 2 could begin. (c)
→ Section 14's scope plus a `Scheduler` `Job` registration and a
`reflection.schedule` config addition. (d) → this document would need
to be substantially rewritten once the owner defines what "reasoning
quality" means and how it would be measured.

### D2 — Separate AI-provider/privacy gate for `reflect summary`, or reuse `reflection.enabled` alone?

**Question:** Should sending recent conversation content to the
configured AI provider for reflection require a second, independent
config flag (mirroring `EP053_DESIGN.md`'s `vision.ai_description.enabled`
precedent), or is the single `reflection.enabled` flag sufficient?
**Options:** (a) `reflection.enabled` alone; (b) a second,
independent `reflection.ai_summary.enabled` flag.
**Recommended option:** (a) — see Section 7's reasoning: unlike
EP-053's `vision describe`, this would not be the first time
conversation content reaches the AI provider (the conversation itself
already went through `AIProvider.ask()` to be generated in the first
place) — it is not new data-exfiltration surface, only new
*re-processing* of data that already left the machine once. The owner
may reasonably disagree with this framing; it is recorded explicitly
so it can be overridden.
**Security impact:** (a) is a single point of control; (b) gives
finer-grained control at the cost of one more flag to configure
correctly.
**Compatibility impact:** none either way — new, independent config
key(s) regardless.
**What changes in STEP 2:** (a) → Section 8's config block as shown.
(b) → an additional `reflection.ai_summary.enabled` key, checked
alongside `reflection.enabled` in `ReflectionModule`'s gate.

### D3 — Autonomy level: descriptive-only output, or permitted to influence anything automatically?

**Question:** Should EP-054 v1's reflection output ever automatically
change any configuration, prompt, or behavior, or must it always be
purely descriptive (a human, or a *later*, separately-designed EP,
reads and acts on it)?
**Options:** (a) strictly descriptive/advisory output only, no
automatic effect on anything; (b) some bounded, automatic effect
(e.g. auto-adjusting a prompt template).
**Recommended option:** (a) — see Section 4's non-goals: the
roadmap's own sequencing places "Prompt Optimizer" (EP-055) and
"Autonomous Planning" (EP-058) as later, separate EPs, strongly
suggesting Self Reflection's role is to *produce* the material those
later EPs would consume, not to *act* on it itself.
**Security impact:** (a) has no autonomous-action risk surface at
all; (b) would need a full, separate security review this document
does not attempt (bounded scope, rollback, confirmation requirements,
etc. — exactly the class of concern `JARVIS_ARCHITECTURE_VISION.md`'s
Human Approval principle exists to address).
**Compatibility impact:** (a) is fully additive and inert with
respect to every other component; (b) could not be responsibly scoped
without knowing exactly what it would be permitted to change.
**What changes in STEP 2:** (a) → `reflect summary`/`reflect recall`
only ever return text; nothing else in the system reads or acts on
that text automatically. (b) → out of scope for this document
entirely; would require a new STEP 1 revision.

### D4 — Persist reflections to `MemoryManager`, or keep them ephemeral (return-only, never stored)?

**Question:** Should `reflect summary`'s output be persisted (via
`MemoryManager`, Section 3.4) so it can be recalled later (`reflect
recall`), or should it be purely ephemeral, returned once and never
stored by EP-054 itself?
**Options:** (a) persist to `MemoryManager` under a dedicated
`reflection` namespace, gated by `reflection.persist_to_memory`
(default `false`); (b) never persist — `reflect recall` does not
exist in v1.
**Recommended option:** (a), default `false` — gives the owner the
choice without forcing storage by default, and enables the one
plausible cross-EP value Section 3.4 identified (a later EP-057
Memory Optimization consuming stored reflections) without building
that consumption itself.
**Security impact:** (a) means reflection content (which may include
summarized conversation content) persists in `MemoryManager`'s active
provider's storage — subject to that provider's own existing
retention/access characteristics, unchanged by EP-054. (b) has zero
persistence-related risk.
**Compatibility impact:** neither changes `MemoryManager` itself;
(a) only adds a new namespace within its existing, generic key/value
model.
**What changes in STEP 2:** (a) → `ReflectionModule` gains a
`MemoryManager` constructor dependency and the `reflect recall`
action; `config/config.yaml` gains `reflection.persist_to_memory`.
(b) → `MemoryManager` is not a `ReflectionModule` dependency at all,
and `reflect recall` is dropped from Section 6.3's action table.

### D5 — Scheduled/periodic triggering (Candidate C) in v1, or manual-only?

**Question:** Should EP-054 v1 include `Scheduler`-based periodic
triggering (Candidate C, Section 5), or ship manual-only (`reflect
summary` invoked on demand) with scheduling deferred?
**Options:** (a) manual-only in v1; (b) include a `Scheduler` `Job`
registration in v1 for periodic reflection.
**Recommended option:** (a) — smaller v1 surface, and periodic
triggering multiplies Owner Decision D2/D7's cost/privacy
considerations (an unattended job calling `AIProvider.ask()`
repeatedly needs its own, separately-reviewed budget/frequency
story) in a way this document has not fully worked out.
**Security impact:** (a) has no unattended-execution risk; (b)
introduces exactly the kind of "no autonomous, unattended,
budget-uncapped AI-provider usage" risk Section 4 already flags as a
non-goal unless specifically, separately authorized.
**Compatibility impact:** neither changes `Scheduler` itself.
**What changes in STEP 2:** (a) → no `Scheduler` integration; Section
14's file scope stands as written. (b) → an additional `Job`
registration in `src/bootstrap.py`'s existing `Scheduler` wiring block,
plus a `reflection.schedule` config addition and its own dedicated
rate-limit/budget Owner Decision this document has not drafted.

### D6 — Register as an Agent Framework subsystem (Section 3.2), in addition to being a `CommandModule`?

**Question:** Should `ReflectionModule`/its underlying capability also
register itself with `AgentEngine.register_subsystem()` (Section 3.2),
so `agent status`/`list_subsystems()` reports on it alongside
`embedding`/`rag`/`memory`/etc., or should it remain purely a
`CommandModule` like `desktop`/`browser`/`file`/`vision` (none of
which register as Agent subsystems today)?
**Options:** (a) `CommandModule` only, no Agent subsystem
registration (matching Phase 7/8 precedent exactly); (b) both — a
`CommandModule` for direct invocation, plus a subsystem registration
for status visibility (matching the Phase 3-6 pattern in addition).
**Recommended option:** (a) — Section 3.2 confirmed the subsystem
registry is used exclusively by Phase 3-6 components today; extending
it to a Phase 9 capability without an already-established need (no
existing code queries `list_subsystems()` for anything beyond
diagnostic display) would be a speculative addition this document
cannot justify against a concrete requirement.
**Security impact:** none either way — `register_subsystem()` is
read-only status reporting.
**Compatibility impact:** (a) touches nothing in `src/core/agent/`;
(b) requires one additive call in `src/bootstrap.py`'s existing
Agent Framework wiring block (Section 14 currently lists
`src/core/agent/` as DO NOT MODIFY — approving (b) would need to
narrow that to "no behavioral change, one additive registration call
in `bootstrap.py` only").
**What changes in STEP 2:** (a) → no change to Section 14's DO NOT
MODIFY list. (b) → `src/bootstrap.py`'s existing Agent Framework
`available_subsystems` list (Section 3.2) gains one new tuple.

### D7 — Exact values for `max_message_count`/`min_seconds_between_calls`

**Question:** What should the default resource/rate limits be?
**Options:** the values shown in Section 8 (`max_message_count: 20`,
`min_seconds_between_calls: 30`) are this document's own reasonable
starting proposal, not derived from any existing project convention
(no comparable per-call AI-provider rate limit exists elsewhere in
the repository to model this on).
**Recommended option:** accept the proposed defaults, or specify
different ones.
**Security impact:** lower values reduce AI-provider cost/exposure
per call; higher values allow richer reflections at higher cost.
**Compatibility impact:** none — new, independent config keys.
**What changes in STEP 2:** whichever values are approved are used
verbatim in `config/config.yaml` and enforced in `ReflectionModule`.

### D8 — `CommandRouter` vs. Tool Engine

**Question:** Restated per this project's own established practice
(Section 3.7) of never assuming a prior EP's answer still holds:
should `ReflectionModule` dispatch through `CommandRouter` (as this
document proposes) or attempt to use/extend Tool Engine?
**Options:** (a) `CommandRouter`, matching EP-050/051/052/053 exactly;
(b) extend Tool Engine to support parameterized handlers first.
**Recommended option:** (a) — restated from Section 3.7; this is now
the fifth independent EP to reach the same conclusion for the same
reason (`Tool.handler`'s zero-argument-only signature).
**Security impact:** none either way.
**Compatibility impact:** (a) requires no `src/core/tool/` change; (b)
would be a cross-cutting change this EP is not authorized to make
unilaterally.
**What changes in STEP 2:** (a) → `ReflectionModule` registers with
`CommandRouter` exactly like every prior skill. (b) → not planned by
this document at all.

### D9 — Real-`AIProvider` end-to-end testing (Section 12, Section 19)

**Question:** Should EP-054 include a separate, unregistered,
real-provider integration script (mirroring EP-053's real-Tesseract
script), given it would require live, costed API credentials and
would assert against non-deterministic model output rather than an
exact, fixed string?
**Options:** (a) no real-provider integration script — the primary
suite's fake-`AIProvider` tests are the only coverage; (b) build one
anyway, asserting only loose properties (non-empty response, no
exception) rather than exact content.
**Recommended option:** (a) — unlike EP-053's OCR check (which could
assert an exact, deterministic recognized string), a real
`AIProvider.ask()` call's output is not deterministic, so a
real-provider test would mostly just confirm network/credential
plumbing rather than genuine reflection-quality behavior; this
document does not see enough value to justify the added cost/
complexity, but records the option for the owner to override.
**Security impact:** none either way.
**Compatibility impact:** none either way.
**What changes in STEP 2:** (a) → `tests/EP054/` contains only the
primary, fake-backed suite (Section 12). (b) → an additional,
unregistered `tests/EP054/test_reflection_ai_integration.py`
following EP-053's own "print a plain pass/fail summary, exit 0 on a
disclosed skip" convention, adapted for a loose-assertion,
credential-gated check.

---

## Owner Approval Checklist

- [ ] **D1** — What does "Self Reflection" concretely mean for v1?
  (recommended: Candidate A, session/conversation self-critique)
- [ ] **D2** — Separate AI-provider/privacy gate, or reuse
  `reflection.enabled` alone? (recommended: reuse alone)
- [ ] **D3** — Autonomy level (recommended: strictly descriptive,
  no automatic effect on anything)
- [ ] **D4** — Persist to `MemoryManager`? (recommended: yes,
  default `false`, opt-in)
- [ ] **D5** — Scheduled/periodic triggering in v1? (recommended:
  no, manual-only)
- [ ] **D6** — Register as an Agent Framework subsystem? (recommended:
  no, `CommandModule` only)
- [ ] **D7** — Exact resource/rate-limit default values (recommended:
  `max_message_count: 20`, `min_seconds_between_calls: 30`)
- [ ] **D8** — `CommandRouter` vs. Tool Engine (recommended:
  `CommandRouter`)
- [ ] **D9** — Real-`AIProvider` integration test? (recommended: no)

**STEP 2 (Implementation) will not begin until these are reviewed and
approved, revised, or rejected by the owner in a separate prompt —
and, in particular, until D1 is resolved, since Sections 6-17 of this
document are void under any answer other than Candidate A.**

End of document.
