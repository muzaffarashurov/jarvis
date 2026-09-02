# EP-058 — Autonomous Planning — Design Specification (STEP 1)

Status: **STEP 1 — DESIGN APPROVED (D1-D3 all Owner-approved). STEP 2
— COMPLETE. STEP 3 — AUDIT PASSED (zero blocking findings; two
non-blocking, informational findings). STEP 4 — COMPLETE (both
findings' final disposition recorded; one documentation-only prose
correction applied; zero code/test/config change).**

**Owner Decisions D1-D3 (Section 18/20 -- see this document's own
numbering below) are all APPROVED, exactly as recommended, with no
modification.** Candidate A is the approved v1 scope for EP-058, and
Sections 6-16's provisional architecture is the approved, as-built
architecture -- see the Owner Approval Checklist at the end of this
document for the approved value of each decision, and
`docs/architecture/audits/EP058_ARCHITECTURE_AUDIT.md` for the STEP 3
audit and STEP 4 remediation record.

This document's original STEP 1 text is preserved as first approved,
with one exception disclosed here rather than left silently
corrected: Sections 3.2/3.9/5/17 originally described
`_KEYWORD_RULES` as having "nine" entries. STEP 3's audit
(`EP058_ARCHITECTURE_AUDIT.md` Finding 1) independently confirmed the
actual count is **seventeen** keyword rules, collapsing to **eight**
unique `(subsystem, action)` pairs after deduplication -- a prose
miscount with zero effect on the implementation, which derives its
menu programmatically from the live table rather than from any
hardcoded count (confirmed unchanged, Section 6.5 below). Per the
owner's STEP 4 instruction to consider documentation-only
clarification for non-blocking findings, the four affected passages
below have been corrected to the accurate figures; no other wording
in Sections 0-17 was altered, and no code, test, or configuration
file was touched to produce this correction. Only this status block
and the Owner Approval Checklist at the end are new as of STEP 4,
mirroring the precedent `EP055_DESIGN.md`/`EP056_DESIGN.md`/
`EP057_DESIGN.md` already established.

No source file, test file, configuration file, dependency file, or
Bootstrap file has been created or modified as part of producing this
document. The only artifact created by EP-058 STEP 1 is this document
itself, `docs/architecture/designs/EP058_DESIGN.md`.

---

## 0. How this document relates to EP-054, EP-055, EP-056, and EP-057

Each of the four prior Phase 9 EPs began with a roadmap line whose
only content was a title and Phase 9's shared, one-sentence,
five-EP-wide goal. Each STEP 1 document disclosed this gap explicitly
rather than inventing scope, derived candidate interpretations from
already-existing architecture, and asked the owner to choose among
them via an Owner Decision before any provisional architecture was
treated as authorized. **EP-058 is in the identical situation**,
confirmed by the same exhaustive-search method (Section 2).

**EP-058 differs from all four prior Phase 9 EPs in one important
way, found during discovery (Section 3):** this is the first
Phase-9 EP where the relevant prior infrastructure is not one or two
adjacent subsystems, but an entire, already-complete five-EP chain
(EP-028 through EP-032, "Phase 4 — Agent Framework") plus a further
five-EP chain built on top of it (EP-033 through EP-037, "Phase 5 —
Workflow Automation") — ten already-shipped Engineering Packages in
total, every one of which explicitly, repeatedly, and by design
declines to perform "AI reasoning" and explicitly defers that to a
named-but-unbuilt future concept ("Reasoning Engine" / "Planner").
Per this task's explicit instruction ("do not assume that a similarly
named class or module is intended for EP-058"), this document treats
none of that existing infrastructure as automatically EP-058's target
— Section 3 inventories it precisely, and Section 5 evaluates,
against equal footing, several genuinely different ways EP-058 could
build on top of it.

---

## 1. Metadata

- **Engineering Package:** EP-058 — Autonomous Planning
- **Phase:** Phase 9 — Intelligence (`docs/architecture/JARVIS_ROADMAP.md`
  line 1006/1016; `docs/engineering/ENGINEERING_GUIDE.md`: "Improve
  reasoning and autonomous decision making.")
- **Predecessors (same phase):** EP-054 Self Reflection, EP-055
  Prompt Optimizer, EP-056 Capability Registry, EP-057 Memory
  Optimization — all COMPLETE, all followed the identical "bare
  title, no spec" discovery methodology this document also follows.
- **Predecessors (different phases, directly relevant — Section 3):**
  EP-014/015 AI Provider Manager/Integration, EP-017 Prompt Engine,
  EP-028 Agent Framework, EP-029 Planning Engine, EP-030 Plan
  Execution Engine, EP-031 Tool Engine, EP-032 Multi-Agent
  Collaboration, EP-033 Workflow Engine, EP-034 Workflow Scheduler,
  EP-035 Automation Engine, EP-036 Background Worker Pool.
- **This document's scope:** STEP 1 only — repository discovery,
  scope clarification, architecture proposal (contingent on Owner
  Decision D1), and Owner Decision preparation. No code, test,
  configuration, dependency, or Bootstrap file has been created or
  modified as part of producing this document.
- **File created by STEP 1:** this document,
  `docs/architecture/designs/EP058_DESIGN.md`, only.
- **Files modified by STEP 1:** none.

---

## 2. What the repository actually says about EP-058 (verbatim inventory)

Every reference to EP-058 or "Autonomous Planning" found anywhere in
the repository, by direct, exhaustive search of `docs/`,
`AI_GENERATION_STANDARD.md`, `CHANGELOG.md`, and `src/`:

| Location | Exact content |
|---|---|
| `docs/architecture/JARVIS_ROADMAP.md` line 1016 (Phase 9 checklist) | `EP-058 Autonomous Planning` — a bare title, no elaboration, no checkmark (consistent with every Phase-9 EP in this specific list, including the four already-completed ones -- this list's checkmarks were never maintained past EP-050, a pre-existing, unrelated documentation gap this document does not attempt to fix) |
| `docs/architecture/JARVIS_ROADMAP.md` line 242-244 ("Next Engineering Package" note, added by EP-057 STEP 4) | `**Next Engineering Package: EP-058 Autonomous Planning — NOT STARTED.** No EP-058 design, research, or implementation work has begun.` — a status pointer, not a spec |
| `docs/BACKLOG.md` lines 13-16 ("Next Engineering Package" section, added by EP-057 STEP 4) | `### EP-058 — Autonomous Planning` / `**NOT STARTED.**` — same pointer, same lack of elaboration |
| `CHANGELOG.md` (EP-057 STEP 4 entry) | References EP-058 only as "the next, not-started Engineering Package" — a status note, not a spec |
| `docs/architecture/designs/EP054_DESIGN.md`/`EP055_DESIGN.md`/`EP056_DESIGN.md` | List EP-058 only as a same-phase successor in scope-boundary reasoning — do not define EP-058's scope |
| `docs/architecture/designs/EP057_DESIGN.md` Section 19 ("Unresolved questions") | Explicitly records, as an unresolved question, "Whether a future EP-058 (Autonomous Planning) will expect `compression query`'s output in a specific, machine-readable format, or will want it wired automatically into planning's own context assembly" and answers "no such requirement exists anywhere in the repository today" |
| `docs/architecture/designs/EP050_DESIGN.md` | Lists `EP-054 … EP-058` as the Phase 9 range while establishing that EP-050 is the correct next package at that time — does not define EP-058's scope |
| `docs/engineering/ENGINEERING_GUIDE.md` (Phase 9 section) | `## Phase 9 — Intelligence` / `Improve reasoning and autonomous decision making.` / `Engineering Packages:` / `EP-054 … EP-058` — a **phase-level** goal shared across all five Phase-9 EPs, not an EP-058-specific one |
| `docs/architecture/audits/EP057_ARCHITECTURE_AUDIT.md` | References EP-058 only as "not yet started" in file-scope commentary |
| Everywhere else (`PROJECT_MANIFEST.md`, `AI_GENERATION_STANDARD.md`, every other design/audit document, `src/`) | **Zero** additional mention of EP-058, "Autonomous Planning," or any synonym of it |

**Conclusion (identical in kind to EP-054's/EP-055's/EP-056's/
EP-057's own Section 2 conclusions):** the repository establishes
*that* Autonomous Planning is next, and *that* it belongs
conceptually to "Intelligence," but establishes **no concrete
behavior, input, output, trigger, metric, or user interface** for
EP-058 by that name. No prior EP's design document names EP-058 as an
already-anticipated consumer of anything it built. Section 3,
however, identifies unusually strong *functional* anchors (distinct
from a naming anchor) — several already-existing, already-shipped
packages whose own docstrings and runtime-visible messages explicitly
and repeatedly name the exact concept this task asks about
("Reasoning Engine", "Planner") as deliberately deferred to an
unnamed future EP.

---

## 3. Relevant existing infrastructure (grounds for the candidate interpretations in Section 5)

Per this task's explicit instruction, each area below was inspected
directly against its own source — no area was assumed relevant or
irrelevant based on its name alone.

### 3.1 Agent Framework (EP-028, Phase 4, `src/core/agent/`) — lifecycle and subsystem registry only, explicitly no reasoning

`AgentEngine`/`AgentProvider`/`AgentManager` implement agent
lifecycle (`initialize`/`shutdown`/`reset`/`status`), a subsystem
registry (`register_subsystem`/`unregister_subsystem`/
`list_subsystems`), and `execute(request, metadata)`/`cancel()`. The
package's own module docstring (`src/core/agent/__init__.py`, quoted
verbatim) states it implements agent lifecycle and subsystem registry
**"entirely without planning, reasoning, task decomposition, tool
execution, or prompt construction"** and explicitly says this package
**"must NOT ... implement a Planner, Reasoning Engine, Reflection
Engine, Workflow Engine, Task Scheduler, Tool Executor, Conversation
Engine integration, or Multi-Agent Coordinator -- those are
explicitly future Engineering Packages (EP-029 onward)."**

**The single strongest, most literal, runtime-visible anchor found
anywhere in this repository for any Phase-9 EP so far:**
`DefaultAgentProvider.execute()` (`src/core/agent/agent_provider.py`,
lines 316-325) returns, as its actual, live `AgentExecutionResult.
message` on every single call, the literal string:

```text
"Request accepted. No Planner/Reasoning Engine is registered yet
(future EP); the Agent Framework performed no reasoning, planning,
or task execution."
```

This is not a code comment or a docstring aspiration — it is text a
real user or caller of `agent execute` (if such a CLI action existed;
Section 3.7 confirms it currently does not) would actually see,
today, confirmed unchanged and confirmed still accurate as literally
worded (Section 3.7): nothing in `AgentEngine`/`AgentProvider` calls
`PlanningEngine`, and `AgentEngine.execute()` contains zero reference
to `PlanningEngine`/`PlanExecutionEngine` anywhere (confirmed:
`grep -n "PlanningEngine\|PlanExecutionEngine" src/core/agent/agent_engine.py`
returns no match).

### 3.2 Planning Engine (EP-029, Phase 4, `src/core/planning/`) — deterministic keyword decomposition, with an explicitly named AI extension point

`PlanningEngine`/`PlanningManager`/`PlanningProvider`/
`DefaultPlanningProvider` decompose a request's text into an ordered
`Plan` of `PlanStep`s, purely via a fixed table of seventeen
case-insensitive substring rules (`_KEYWORD_RULES`,
`src/core/planning/planning_provider.py` lines 44-79), collapsing to
eight unique `(subsystem, action)` pairs after deduplication (several
keywords map to the same pair, e.g. "remember"/"recall" both map to
`memory`/`retrieve_from_memory`), each mapping a
keyword (e.g. "remember", "knowledge", "search", "compress",
"coordinate") to one `(subsystem, action, description)` triple. A
request matching no rule yields a single fallback
`acknowledge_request` step. The package's own module docstring states
it "must NOT implement a Reasoning Engine ... and never AI reasoning,
an AI provider call, prompt construction."

**The second, and most specific, anchor found anywhere in this
repository for any Phase-9 EP so far** is `PlanningProvider`'s own
module docstring (`src/core/planning/planning_provider.py`, lines
9-19, quoted verbatim):

> "A future AI-/LLM-backed planning strategy (e.g. one that reasons
> about a request using an AI provider) is an obvious, natural
> extension point for this abstraction -- but implementing it is
> explicitly out of scope here: EP-029 must not call an AI provider,
> an LLM, or perform any reasoning beyond deterministic, rule-based
> keyword matching. This module resolves that the same way
> EP-026/EP-027/EP-028 resolved the analogous conflict: it implements
> exactly one concrete, built-in provider -- `DefaultPlanningProvider`
> ... -- so the subsystem is actually usable today, while
> implementing no AI-backed decomposition strategy at all."

This is a direct, unambiguous, textual pointer to a specific
mechanism (a second `PlanningProvider` implementation), not merely a
vague "future EP" reference — considerably more specific than
EP-056's own "reserved for the future Capability Registry" anchor,
which named a concept but not a mechanism.

`PlanningManager.register_provider(provider)` (`planning_manager.py`
line 131) is a already-built, already-generic extension point,
requiring the new provider's name to not collide with an existing one
and nothing else — confirmed by direct code reading, this method
performs no type-check beyond `PlanningProvider` conformance and
takes no dependency on which concrete class is passed. `planning use
<provider>` (`src/modules/planning_module.py`) is an **already
existing, already-shipped CLI action** that activates any registered
provider by name — confirmed present in `ContextCompressionModule`'s
sibling, `PlanningModule`'s own `self._actions` dict
(`help`/`status`/`providers`/`use`/`plan`/`limits`). `planning.
default_provider` (`config/config.yaml` line 894, currently
`"planning"`) is the exact configuration key that selects which
registered provider is active at startup, following the identical
convention `context_compression.default_provider`/`semantic.
default_provider`/`embedding.default_provider` already establish.

### 3.3 Plan Execution Engine (EP-030, Phase 4, `src/core/plan_execution/`) — deterministic dispatch, already end-to-end with Planning

`PlanExecutionEngine.execute_request(request)` (confirmed present via
`src/core/workflow_engine/__init__.py`'s own docstring, which already
depends on it) already composes `PlanningEngine.plan()` and
dispatches every resulting step, in order, halting on failure per
`plan_execution.stop_on_failure` — this two-EP combination
(Planning + Plan Execution) is **already fully wired and already
reachable today** via the existing `execution run "<request>"` CLI
action (`src/modules/plan_execution_module.py`, confirmed by direct
code reading: `outcome: RunOutcome = self._service.run(request)`,
where `request` is the raw user-supplied text, planned and executed
in one call). This package's own module docstring states it "must NOT
call an AI provider, build a prompt, invoke a real subsystem action,
or re-implement decomposition."

**This is an important, potentially counter-intuitive discovery: a
complete, working, "give it plain English, get real dispatched work"
pipeline already exists in this repository today, with zero AI
involvement anywhere in it.** Any EP-058 candidate must be evaluated
against what this pipeline can already do, not assumed to be filling
an "cannot go from English to action" gap that does not actually
exist.

### 3.4 Tool Engine (EP-031, Phase 4, `src/core/tool/`) — the real dispatch target, with a confirmed, narrower-than-Planning action vocabulary

`ToolEngine`/`ToolManager`/`ToolProvider` turn an already-identified
`(subsystem, action)` reference into a real call of an
already-implemented Engineering Package's public method. Confirmed by
direct inspection of `src/bootstrap.py` (lines 1021-1085, the only
place built-in tools are registered): **only five `(subsystem,
action)` pairs are actually dispatchable today** --
`memory`/`retrieve_from_memory`, `knowledge`/`query_knowledge_base`,
`long_term_memory`/`query_long_term_memory`,
`agent`/`coordinate_subsystems`, and the subsystem-less
`acknowledge_request` fallback. The remaining four actions Planning's
own keyword table recognizes (`embedding`/`generate_embedding`,
`rag`/`retrieve_context`, `semantic`/`semantic_search`,
`compression`/`compress_context`) are **deliberately left
unregistered** per this project's Unknown API Policy, because
`PlanStep` carries no text parameter for the four actions that would
need one (confirmed: `src/bootstrap.py` lines 1000-1009's own
comment, and `src/core/tool/__init__.py`'s own "NAMING / SCOPE NOTE").
Dispatching one of these four today already produces an honest
`FAILED` result, per Tool Engine's own existing, unmodified behavior
-- not a crash, and not new behavior EP-058 would introduce.

Also confirmed: `ToolExecutionProvider` (a second `PlanExecutionProvider`
implementation, backed by Tool Engine) is already registered as an
*additional*, selectable plan-execution provider (`execution use
tool_engine`) but is **not** the default (`plan_execution.
default_provider` stays `"plan_execution"`) -- this is the exact
precedent (an additional, explicitly-opt-in provider registered
alongside an unchanged default) Section 6's provisional architecture
follows for a new Planning provider.

### 3.5 Multi-Agent Collaboration (EP-032, Phase 4, `src/core/collaboration/`) — broadcast only, not reasoning

Distributes an already-formed request to every currently registered
`AgentProvider` (deterministic broadcast) and aggregates each agent's
own `AgentExecutionResult`. Its own module docstring states it
"performs no AI reasoning, no negotiation, and no inter-agent
messaging." With only one `AgentProvider` registered today
("jarvis", Section 3.1), this package currently has no practical
effect beyond that single agent's own behavior. Confirmed irrelevant
to autonomous planning specifically -- it coordinates *agents*, not
*decomposition strategies* (a materially different axis, per its own
docstring's explicit clarification against EP-028's *subsystem*
registry).

### 3.6 Workflow Engine / Scheduler / Automation Engine / Background Worker Pool (EP-033–036, Phase 5) — sequencing, timing, and reaction only, all layered on Planning + Plan Execution, never on Agent Framework

Each of these four packages' own module docstring states, in
materially identical language, that it "performs no AI reasoning, no
[scheduling/planning/decomposition] of its own" and only
sequences/schedules/reacts-to calls into `WorkflowEngine.run()` (which
itself calls `PlanExecutionEngine.execute_request()` per-step,
Section 3.3). **None of these four packages ever reaches `AgentEngine`
directly** (confirmed: `grep -rn "AgentEngine\|AgentProvider"
src/core/workflow_engine/ src/core/workflow_scheduler/
src/core/automation_engine/ src/core/background_workers/` returns no
match) -- they compose Planning + Plan Execution's already-wired
pipeline (Section 3.3), not Agent Framework's separate one (Section
3.1). This confirms the two pipelines identified in Section 3.1/3.3
are genuinely parallel and disconnected today, not merely
under-documented.

Two important, pre-existing, honestly-documented dormant/collision
notes surfaced during this inspection, recorded here because a
careless EP-058 implementation could otherwise re-trip them:
`src/core/workflows/`/`WorkflowService`/`WorkflowModule` (EP-007, an
unrelated, dormant, never-Bootstrap-wired package that happens to
share the word "Workflow") and `src/core/scheduler/`/
`SchedulerService`/`SchedulerModule` (EP-011, an unrelated, actively-
wired package that happens to share the word "Scheduler"). Both are
explicitly out of EP-058's scope and neither is touched by any
candidate in Section 5.

### 3.7 The CommandRouter / CLI surface, confirmed precisely

`agent` (`AgentModule`, `src/modules/agent_module.py`) registers only
`help`/`status`/`subsystems`/`register`/`unregister`/`reset`/
`initialize`/`shutdown` -- **confirmed: no `execute` or `cancel`
action exists in the CLI today**, even though `AgentEngine.execute()`/
`cancel()` exist at the Service/Engine layer. `planning`
(`PlanningModule`) registers `help`/`status`/`providers`/`use`/
`plan`/`limits`. `execution` (`PlanExecutionModule`, EP-030's CLI
namespace, deliberately not named `plan_execution` to avoid clashing
with the pre-existing, unrelated `src/core/execution/` OS-level
target launcher from EP-003) registers `help`/`status`/`providers`/
`use`/`run`. `tool` (`ToolModule`) registers `help`/`status`/
`providers`/`list`/`use`/`run`. Every one of these is an unmodified,
existing `CommandModule` following the identical `CommandRouter.
dispatch()` pattern every other skill in this repository already
uses (confirmed unchanged from every prior EP's own Section 3.7-
equivalent finding).

### 3.8 AI Provider Manager / Prompt Engine (EP-014/015/017) — the established "call an AI provider directly, bypassing Conversation Engine" pattern

`ProviderManager.get_current()` (`src/core/ai/provider_manager.py`)
returns the currently-selected raw `AIProvider`, or `None` if none is
selected (`ai.default_provider` defaults to `"none"`,
`config/config.yaml` line 578 -- confirmed no real provider is active
by default). `AIProvider.ask(prompt, max_tokens=None) ->
ProviderResponse` (`src/core/ai/provider.py`) is the raw, single-turn
call every real provider (e.g. `ClaudeProvider`) implements.
`PromptOptimizerModule` (EP-055, `src/skills/prompt_optimizer/skill.py`,
its own docstring quoted directly) establishes the precedent this
document's recommended candidate follows: call `ProviderManager.
get_current().ask(...)` **directly**, deliberately bypassing
`AIService`'s higher-level Conversation/Context/Prompt Engine
pipeline, because going through `AIService.ask()` would incorrectly
append the call as a new conversation turn and route it back through
machinery the call itself has no need of. This exact bypass pattern
is already established by two prior Phase-9 EPs (EP-054 Self
Reflection also avoids `AIService.ask()` for an analogous reason) and
is not a new invention this document introduces.

Confirmed by direct search
(`grep -rn "json.loads\|json.load" src/skills/ src/core/ai/
src/core/agent/ src/core/planning/`, excluding voice/conversation
persistence, which serialize their own data, not an AI provider's
free-text reply): **no existing skill or subsystem parses a
structured (e.g. JSON) response out of an AI provider's own text
reply.** Every existing Phase-9 EP that calls an AI provider
(Reflection, Prompt Optimizer) treats the reply as opaque display
text, never as data to be parsed back into a typed object. A
candidate that needs to turn an AI reply into `PlanStep`s (Section 5,
Candidate B) is the first to need this, and Section 6.5 addresses it
with the narrowest possible parsing approach, consistent with this
project's Unknown API Policy and its general aversion to inventing
new dependencies (no JSON-mode API feature is used or assumed; no new
third-party parsing library is introduced).

### 3.9 Memory/LTM/Semantic Search/Context Compression (EP-023/025/026/027) — already reachable through Planning's own recognized action vocabulary, not otherwise relevant

Already inventoried in depth by `EP057_DESIGN.md` Section 3 and
`EP057_ARCHITECTURE_AUDIT.md`; unchanged since EP-057's completion
(confirmed still byte-identical to their EP-057-audited state, since
nothing in this discovery pass touched them). Relevant to EP-058 only
indirectly, as four of Planning's eight recognized keyword-matched
actions (`retrieve_from_memory`, `query_knowledge_base`,
`query_long_term_memory`, `compress_context`) reference these
subsystems by name (Section 3.2/3.4) -- no direct integration with
any of them is proposed by any candidate in Section 5.

---

## 4. What this document does NOT propose (scope boundaries, stated up front)

- **No new Reasoning Engine, Reflection Engine, Workflow Engine, Task
  Scheduler, Tool Executor, or Multi-Agent Coordinator of any kind**
  -- every one of these is either already built (Workflow Engine,
  EP-033; Reflection, EP-054) or explicitly, repeatedly named across
  five different packages' docstrings as *not* this document's
  concern; EP-058 is scoped narrowly around the one specific,
  textually-anchored gap Section 3.2 identifies.
- **No modification to `AgentEngine`/`AgentProvider`/`AgentManager`
  (EP-028), `PlanExecutionEngine`/`PlanExecutionProvider`/
  `PlanExecutionManager` (EP-030), `ToolEngine`/`ToolProvider`/
  `ToolManager` (EP-031), `CollaborationEngine`/`CollaborationProvider`
  (EP-032), or any Phase 5 package (EP-033-037)'s own core files.**
  All are treated as fixed, exactly as `EP057_DESIGN.md` treated
  EP-024/025/026/027 as fixed; this document's recommended candidate
  is additive to `src/core/planning/` only.
- **No change to `DefaultPlanningProvider`'s existing, deterministic
  behavior, its `_KEYWORD_RULES` table, or its selection as the
  default provider.** `planning.default_provider` remains `"planning"`
  unless an operator explicitly opts in, mirroring `plan_execution.
  default_provider` remaining `"plan_execution"` despite
  `ToolExecutionProvider`'s own registration (Section 3.4).
- **No automatic wiring of any AI-backed planning into `AgentEngine.
  execute()`, `AIService.ask()`'s own request pipeline, or any
  background/scheduled trigger.** Every Phase-9 EP so far (EP-054,
  055, 056) is a strictly on-demand, explicitly-invoked capability,
  never an automatic one; this document's recommended candidate
  follows that same precedent (Section 6.4).
- **No new persistence, no new background thread, no new event bus
  integration.** `PlanStep`/`Plan` remain the plain, already-existing
  data types (EP-029); nothing is written to disk.
- **No structured-output/function-calling AI provider feature is
  assumed or required.** `ClaudeProvider.ask()`'s existing, plain
  `prompt -> text` contract (EP-015) is the only interface used
  (Section 3.8/6.5).
- **No cross-EP scope creep.** This document does not redesign or
  re-scope EP-054, EP-055, EP-056, EP-057, or any Phase 4/5/8 package.

---

## 5. Candidate interpretations of "Autonomous Planning" (grounds for Owner Decision D1)

Each candidate is derived from an existing, already-inspected part of
the repository (Section 3), not invented from outside knowledge of
what "autonomous planning" might mean in the abstract. None is
authorized; Owner Decision D1 (Section 20) asks the owner to choose
one (or explicitly reject all of them and redirect this document).

### Candidate A — An AI-/LLM-backed `PlanningProvider`, selectable alongside the existing deterministic one (recommended)

Add a new, second `PlanningProvider` implementation (e.g.
`AIPlanningProvider`) that calls `ProviderManager.get_current().
ask(...)` **directly** (Section 3.8's established bypass pattern) to
choose which of Planning's own already-recognized `(subsystem,
action)` pairs (Section 3.2's eight-entry vocabulary, unchanged) best
match a request's *meaning*, rather than `DefaultPlanningProvider`'s
fixed substring rules -- genuinely reasoning about intent, using an
AI provider, exactly as `PlanningProvider`'s own module docstring
(Section 3.2) explicitly names as "an obvious, natural extension
point... explicitly out of scope [for EP-029]". Registered via
`PlanningManager`'s already-existing, already-generic
`register_provider()` (Section 3.2) alongside, never replacing,
`DefaultPlanningProvider`; selectable via the already-existing,
unmodified `planning use ai` CLI action (Section 3.2) -- requiring,
in the best case, **zero new CLI surface**, only a new provider class
plus its Bootstrap registration.

**Why recommended:** (1) it is the only candidate directly named by
an existing module's own docstring as the intended extension point
for this exact scenario (Section 3.2) -- the single strongest textual
anchor found for any Phase-9 EP so far, more specific than EP-056's
own "reserved for the future Capability Registry." (2) It is
purely additive to `src/core/planning/`'s already-built,
already-generic multi-provider machinery (`register_provider()`,
`use_provider()`, `planning.default_provider`) -- zero modification
to `PlanningManager`, `PlanningEngine`, `PlanStep`/`Plan`, or any
Phase 4/5 package's core files (Section 4). (3) It reuses the
established, already-precedented "call `AIProvider.ask()` directly,
bypass `AIService`" pattern (Section 3.8) two prior Phase-9 EPs
already established, rather than inventing a new AI-integration
style. (4) It directly answers the literal words "Autonomous
Planning": an AI provider *autonomously* decides, from a fixed,
already-real menu of dispatchable actions, what a request's plan
should be -- a genuinely different, reasoning-based decomposition
strategy standing in for, not replacing, the deterministic one. (5)
It leaves `DefaultPlanningProvider` as the default provider,
unaffected either way (Section 4), exactly mirroring
`ToolExecutionProvider`'s own already-accepted "additional, opt-in,
non-default provider" precedent (Section 3.4).

**Risks / dependencies:** requires a real AI provider to be
configured and selected (`ai.default_provider` is `"none"` by
default, Section 3.8) -- the new provider must fail cleanly and
predictably when none is available (Section 6.3/10), exactly the way
every other multi-provider subsystem in this repository already
handles an unconfigured provider. Requires a new, narrow
text-parsing routine to turn the AI's reply into `PlanStep`s (Section
3.8's own finding: no precedent for this exists yet in this
repository) -- Section 6.5 scopes this to the minimum necessary,
explicitly rejecting any JSON/structured-output dependency.

### Candidate B — Wire `AgentEngine.execute()` to the already-existing, purely deterministic Planning + Plan Execution pipeline (rejected as a v1 candidate, but the second-most-grounded)

Address Section 3.1's literal, runtime-visible "No Planner/Reasoning
Engine is registered yet (future EP)" message directly: give
`AgentProvider.execute()` a real `PlanningEngine`/`PlanExecutionEngine`
call, so `agent execute "<request>"` (once such a CLI action also
exists -- Section 3.7 confirms none does today) would actually plan
and dispatch the request, using **zero AI reasoning** -- purely the
already-existing deterministic pipeline (Section 3.3). **This
document does not recommend this candidate for v1:** (1) it requires
modifying `AgentProvider`/`AgentEngine` (EP-028)'s own core files,
an already-complete, already-shipped Phase 4 package this document
would otherwise leave untouched, unlike Candidate A's purely additive
change to Planning's own provider registry. (2) It also requires
adding a new `execute` CLI action to `AgentModule` that does not
exist today (Section 3.7), a second file this candidate would need to
touch. (3) Most importantly, it involves **no reasoning of any kind**
-- it is a wiring fix, not "Intelligence," and sits awkwardly against
Phase 9's own stated goal ("Improve reasoning and autonomous decision
making") and the literal word "Autonomous" in EP-058's own title,
compared to Candidate A's genuine AI-driven decision-making. Recorded
as the strongest fallback if the owner specifically wants EP-058 to
close the literal stale-message gap in Section 3.1 rather than build
genuinely AI-driven decomposition.

### Candidate C — Extend `DefaultPlanningProvider`'s own keyword table with new rules, or teach it to call an AI provider internally (rejected)

A narrower reading: rather than a second provider, modify
`DefaultPlanningProvider` itself to add new keyword rules, or to fall
back to an AI provider call when no keyword matches. **This document
does not recommend this candidate:** `DefaultPlanningProvider`'s own
class docstring and `PlanningProvider`'s own module docstring
(Section 3.2) explicitly, repeatedly state this provider "must NOT
call an AI provider... or perform any reasoning beyond deterministic,
rule-based keyword matching" -- modifying it to do so would directly
violate an already-shipped, already-audited (implicitly, by
`AI_GENERATION_STANDARD.md`'s "Completed EPs should not be redesigned
unless an explicit architectural decision requires it") package's own
documented invariant, for no benefit Candidate A does not already
provide more cleanly (a second, additive, explicitly-opt-in
provider).

### Candidate D — A new, standalone "Reasoning Engine" / "Autonomous Agent Loop" package, independent of Planning/Agent Framework (rejected)

A maximalist reading: build an entirely new subsystem (e.g. a
multi-step, self-directed agent loop that repeatedly reasons, acts,
and observes, in the style of a general "autonomous agent"
architecture) from first principles, independent of EP-028/029/030's
existing data types. **This document does not recommend this
candidate:** it would duplicate, rather than reuse, `Plan`/`PlanStep`
(EP-029), `PlanExecutionEngine`'s dispatch loop (EP-030), and
`AgentEngine`'s subsystem registry (EP-028) -- exactly the "propose
duplication of functionality that already exists" this task's own
instructions warn against. It would also require inventing a
multi-step control-flow policy (when to stop reasoning, how many
iterations, what "observation" means for a text-only CLI tool) with
zero repository evidence to derive any of it from, mirroring
`EP057_DESIGN.md`'s own rejected Candidates B/D ("invent a policy
from nothing").

---

## 6. Proposed architecture (contingent on Owner Decision D1 = Candidate A)

**Everything in this section and Sections 7-19 is provisional,
written against Section 5's recommended Candidate A, and is not
authorized until Owner Decision D1 (Section 20) is explicitly
approved.** If the owner selects a different candidate, or rejects
all of them, this document's STEP 1 must be revised before STEP 2 can
begin.

### 6.1 New file: `src/core/planning/ai_planning_provider.py`

A new module, sibling to `planning_provider.py`, containing exactly
one new class, `AIPlanningProvider(PlanningProvider)`. This document
recommends a **new file**, not an addition to `planning_provider.py`
itself, for the same reason `compression_provider.py`/
`semantic_provider.py` each already keep every concrete provider
implementation in one file per provider family member only when the
family is small (two); here, `planning_provider.py` is already
451 lines (confirmed) and adding a second, AI-calling provider class
with materially different dependencies (an `AIProvider`, not just
`Config`) to the same file would blur the "no AI reasoning" boundary
`planning_provider.py`'s own module docstring currently, correctly,
states applies to that entire file.

### 6.2 No new backend Protocol

Like every recommended Candidate A across EP-054/055/056/057, this
candidate introduces no new external I/O surface of its own -- it
composes two already-existing, already-built components directly:
`ProviderManager.get_current()`/`AIProvider.ask()` (EP-014/015,
Section 3.8) and `PlanningProvider`'s own already-existing abstract
contract (EP-029, Section 3.2). No new Manager, Engine, or Protocol
class is proposed.

### 6.3 `AIPlanningProvider` — provisional interface

```text
class AIPlanningProvider(PlanningProvider):
    def __init__(self, provider_manager: ProviderManager) -> None: ...
    def provider_name(self) -> str:            # returns "ai"
    def plan(self, request: str, max_steps: int) -> Plan: ...
    def status(self) -> PlanningProviderStatus: ...  # override
    def is_available(self) -> bool: ...              # inherited
    def health(self) -> PlanningProviderHealth: ...  # inherited
```

- `provider_name()` returns the stable literal `"ai"` -- distinct
  from `DefaultPlanningProvider`'s `"planning"`, matching
  `planning.default_provider`'s existing config convention (Section
  3.2) so an operator can select it via `planning use ai` or
  `planning.default_provider: "ai"` without any new CLI surface.
- `status()` is overridden (unlike `DefaultPlanningProvider`, which
  uses the base class's always-`AVAILABLE` implementation) to report
  `PlanningProviderStatus.NOT_CONFIGURED` when `provider_manager.
  get_current()` returns `None` (Section 3.8's confirmed default) --
  mirroring exactly how `CompressionProvider`/`SemanticProvider`
  report an unconfigured backing provider today (`EP057_DESIGN.md`
  Section 3.4's own precedent, one layer up the stack).
- `plan(request, max_steps)` raises `PlanningProviderConfigurationError`
  (an already-existing, unmodified exception type, Section 3.2) when
  no AI provider is currently selected -- never crashes, never
  silently falls back to keyword matching (falling back silently
  would make `planning use ai` misleading: an operator who explicitly
  selected the AI provider should get a clear, honest failure, not a
  disguised deterministic result).

### 6.4 Command/action design

**No new CLI action is proposed.** `planning help`/`status`/
`providers`/`use`/`plan`/`limits` are unchanged, and `PlanningModule`
requires zero code change: `planning providers` already lists every
registered provider generically (confirmed by direct code reading of
the existing `_providers` handler, which iterates `PlanningManager.
list_providers()` without any hardcoded provider name), `planning use
ai` already activates any registered provider by name (Section 3.2),
and `planning plan "<request>"` already calls whichever provider is
currently active. This is a smaller command-surface footprint than
any prior Phase-9 EP's own recommended Candidate A (each of which
added at least one new CLI action) -- confirmed as a genuine
consequence of `PlanningManager`'s own, already-generic multi-provider
design (Section 3.2), not an oversight in this document's scoping.

### 6.5 Turning an AI reply into `PlanStep`s -- the one genuinely new mechanism this EP introduces

Per Section 3.8's finding (no precedent exists in this repository for
parsing structured data out of an AI provider's free-text reply),
this document proposes the narrowest mechanism that avoids inventing
a new dependency or a new AI-provider capability:

1. Compose a single prompt (built entirely from already-known,
   static text plus `request`) that: states the exact, fixed menu of
   `(subsystem, action)` pairs `DefaultPlanningProvider`'s own
   `_KEYWORD_RULES` table already recognizes (Section 3.2, unchanged
   -- reusing the identical vocabulary, not inventing a new one, so
   both providers remain genuinely interchangeable per `planning.
   default_provider`'s existing semantics), and asks the AI provider
   to reply with **one line per relevant step**, each line in the
   literal form `subsystem|action`, in priority order, choosing only
   from the given menu, with no other text.
2. Call `provider.ask(prompt, max_tokens=...)` once per `plan()`
   call -- a single, synchronous, non-streaming call, exactly
   matching `PromptOptimizerModule`'s/`ReflectionModule`'s own
   established one-call-per-action pattern (Section 3.8).
3. Parse the reply defensively, line by line: split each non-blank
   line on the first `|`; if the resulting `(subsystem, action)` pair
   exactly matches one of the fixed menu's entries (case-sensitive,
   no fuzzy matching, no invented pair ever accepted -- this
   project's Unknown API Policy applied to the AI's own output, not
   only to hand-written code), build a `PlanStep` with that entry's
   already-known `description` (Section 3.2's own table -- the AI
   never invents step descriptions, only selects which fixed steps
   apply); any line that does not parse or does not match the menu is
   silently skipped, never raising and never fabricating a
   plausible-looking but incorrect step.
4. If, after parsing, zero valid steps were produced (a malformed or
   empty reply), emit the identical fallback
   `acknowledge_request` step `DefaultPlanningProvider` already emits
   in the analogous case (Section 3.2) -- `AIPlanningProvider` never
   returns an empty-steps `Plan`, matching `Plan`'s own existing
   invariant ("never has an empty `steps` list").
5. Enforce `max_steps`, preserving order -- identical to
   `DefaultPlanningProvider`'s own existing truncation behavior.

This mechanism calls no new library, assumes no JSON-mode or
function-calling feature of any provider, and treats the AI's reply
exactly the way `AI_GENERATION_STANDARD.md`'s Unknown API Policy
treats hand-written code: nothing not already known to be valid is
ever accepted.

### 6.6 Integration points

- `ProviderManager.get_current()` / `AIProvider.ask()` (EP-014/015,
  unmodified) -- the entire new AI call surface.
- `PlanningManager.register_provider()` (EP-029, unmodified) -- the
  entire new registration surface; `AIPlanningProvider` is registered
  alongside, never replacing, `DefaultPlanningProvider`.
- **No** integration with `AgentEngine`/`AgentProvider` (Section 4 --
  Candidate B's own territory, explicitly not this candidate's).
  `AIPlanningProvider` never calls `AgentEngine.list_subsystems()`
  itself -- exactly like `DefaultPlanningProvider`, that reconciliation
  remains `PlanningEngine`'s job alone (Section 3.2), applied
  uniformly regardless of which provider produced the raw `Plan`.
- **No** integration with `PlanExecutionEngine`/`ToolEngine` directly
  -- `AIPlanningProvider` only ever produces a `Plan`; turning it into
  dispatched work remains exactly as reachable (or not) as it already
  is today via `execution run "<request>"` (Section 3.3), regardless
  of which planning provider is currently selected.
- **No** integration with `AIService`/`ConversationManager`/
  `PromptManager`/`PromptBuilder` -- the established bypass pattern
  (Section 3.8) is followed exactly; none of these four components is
  touched or called.

---

## 7. Configuration considerations

**No new top-level configuration section is proposed.**
`AIPlanningProvider` reads no configuration of its own beyond what
`planning.*` (unchanged: `enabled`, `default_provider`, `max_steps`)
and `ai.*`/`providers.*` (unchanged: which provider `ProviderManager`
currently has selected) already provide. This mirrors
`ToolExecutionProvider`'s own precedent (Section 3.4): a second
provider for an existing multi-provider subsystem needs no
configuration section of its own when it has no tunable parameter
beyond "which underlying resource does it call," which is already
governed by `ai.default_provider`/`providers.*`. `planning.
default_provider` remains `"planning"` by default (Section 4) --
selecting `"ai"` is an explicit, opt-in operator action, exactly
mirroring how `plan_execution.default_provider` remains
`"plan_execution"` despite `ToolExecutionProvider`'s own registration.

One new, small, optional tuning value is worth the owner's explicit
consideration (Owner Decision D3, Section 20): a `max_tokens` cap for
the one `AIProvider.ask()` call this provider makes per `plan()`
invocation -- reusing `ai.max_context_messages`-style existing
precedent would not fit (that key governs Conversation Engine
history, unrelated), so this would be a genuinely new value if the
owner wants a cap smaller than each provider's own configured
default.

---

## 8. Command/API surface

As established in Section 6.4: **no new command or API surface**.
Every action an operator needs (`planning use ai`, `planning plan
"<request>"`, `planning providers`, `planning status`) already
exists, unmodified, today.

---

## 9. Security and privacy considerations

- **This is the first Phase-9 EP whose recommended candidate makes a
  real AI-provider call** (EP-054/055/056/057 each either made no AI
  call at all, in EP-056's/EP-057's case, or made one only via an
  explicit, separate on-demand action in EP-054's/EP-055's case, never
  through an already-existing, generically-reused CLI verb like
  `planning plan`). This means selecting `planning use ai` changes
  the meaning of the *already-existing* `planning plan "<request>"`
  command from "always free, local, instant" to "costs one AI-provider
  call, subject to that provider's own latency, availability, and (if
  applicable) billing" -- entirely opt-in, but worth the owner's
  explicit attention (Owner Decision D2, Section 20), since no other
  provider swap in this repository changes an existing command's cost
  profile this way (embedding/semantic/compression's "cloud" providers
  are all today configured `enabled: false` and would need the same
  explicit opt-in before incurring any cost).
- **What text is sent to the AI provider:** only the request text
  passed to `plan()` (already user-supplied, already handled
  identically by `DefaultPlanningProvider` today) plus the fixed,
  static menu text (Section 6.5) -- no memory, conversation history,
  or file content is read or sent, since `AIPlanningProvider` has no
  dependency on `MemoryService`/`ConversationManager`/`KnowledgeService`
  of any kind (confirmed by Section 6.6's integration-point list).
- **No new AI-provider privacy gate is proposed beyond the provider
  selection itself** -- selecting `"ai"` as the active planning
  provider is itself the consent action, exactly the way selecting a
  "cloud" embedding/semantic/compression provider already is the
  consent action for those subsystems, with no separate opt-in flag
  layered on top.
- **No new information-disclosure surface:** `plan()`'s output is the
  same `Plan`/`PlanStep` shape `DefaultPlanningProvider` already
  produces and `planning plan` already displays -- no new field, no
  new disclosure.
- **No credential handling of any kind in this package** --
  `AIPlanningProvider` never reads an API key directly; it reaches
  the provider only through `ProviderManager.get_current()`, exactly
  as `PromptOptimizerModule` already does (Section 3.8).

---

## 10. Error handling

- `PlanningProviderConfigurationError` (already-existing, unmodified,
  EP-029, Section 3.2) when no AI provider is currently selected
  (`ProviderManager.get_current()` returns `None`).
- Whatever exception `AIProvider.ask()` itself raises on a real
  provider failure (network error, rate limit, authentication
  failure) is caught and re-raised as `PlanningProviderError`
  (already-existing, unmodified, EP-029) -- following the same
  "wrap the underlying failure in this subsystem's own exception
  type" convention `CompressionService`/`SemanticService` already
  establish, so callers of `PlanningEngine.plan()` can continue to
  catch one exception family regardless of which provider is active.
- A malformed, empty, or unparseable AI reply never raises -- Section
  6.5 step 4 guarantees a valid fallback `Plan` is always returned,
  matching `Plan`'s own existing "never empty" invariant.
- `max_steps` validation is unchanged -- inherited directly from
  `PlanningEngine`'s own existing, unmodified validation, applied
  identically regardless of which provider is active.

---

## 11. Performance and resource considerations

- **One AI-provider call per `plan()` invocation, only when the
  `"ai"` provider is explicitly selected** -- `DefaultPlanningProvider`
  remains the zero-latency, zero-cost default (Section 4/7). No
  caching, batching, or streaming is proposed for v1; each `planning
  plan "<request>"` call while `"ai"` is active makes exactly one
  synchronous `ask()` call, matching `PromptOptimizerModule`'s own
  "one call per action" precedent (Section 3.8).
- **No background work, no new thread, no new persistence** --
  `AIPlanningProvider` holds no state between calls beyond the
  `ProviderManager` reference passed to its constructor.
- **Reply size is bounded** by whatever `max_tokens` value is passed
  to `ask()` (Section 7) and further bounded by `max_steps` after
  parsing (Section 6.5 step 5) -- no unbounded growth is possible
  regardless of how verbose a real provider's reply is.

---

## 12. Testing strategy (provisional, Candidate A)

Mirrors the now-four-times-established convention
(`EP054_DESIGN.md`/`EP055_DESIGN.md`/`EP056_DESIGN.md`/
`EP057_DESIGN.md` Section 12):

- **`tests/EP058/test_autonomous_planning.py`** (primary, always-run
  suite):
  - `provider_name()` returns `"ai"`, distinct from
    `DefaultPlanningProvider`'s `"planning"`.
  - `status()`/`is_available()` correctly report `NOT_CONFIGURED`
    when `ProviderManager.get_current()` is `None`, and `AVAILABLE`
    when a provider is selected -- using a real, unmodified
    `ProviderManager` (constructed with no real network-calling
    provider registered, following the same "real component, no
    fake" preference `EP057_DESIGN.md` Section 12 already
    established) for the unconfigured case, and a minimal fake
    `AIProvider` (implementing only `ask()`) for the configured-and-
    called cases, since a real network call to `ClaudeProvider` is
    out of scope for a repeatable, offline test suite -- mirroring
    exactly how `EP056_ARCHITECTURE_AUDIT.md` Section 8 already
    distinguished when a fake is appropriate (an external network
    dependency) from when it is not (an in-repo component).
  - `plan()` raises `PlanningProviderConfigurationError` cleanly when
    unconfigured -- never crashes.
  - `plan()`'s reply-parsing (Section 6.5) is unit-tested directly
    against a table of representative fake replies: a well-formed
    multi-line reply, a reply with one malformed line mixed with
    valid ones (the malformed line is skipped, not fatal), a reply
    naming a pair outside the fixed menu (rejected, per the Unknown
    API Policy applied to AI output), a completely empty reply
    (falls back to `acknowledge_request`), and a reply exceeding
    `max_steps` (truncated, order preserved).
  - `PlanningManager.register_provider(AIPlanningProvider(...))`
    followed by `use_provider("ai")` and `plan()` -- proving
    `AIPlanningProvider` genuinely satisfies `PlanningManager`'s
    already-existing, unmodified registration/selection contract,
    with zero change to `PlanningManager` itself.
  - `CommandRouter`/`Bootstrap` wiring test: `planning providers`
    (already-existing, unmodified action) lists `"ai"` once
    registered, and `planning use ai` (already-existing, unmodified
    action) succeeds -- proving Section 6.4's "zero new CLI surface"
    claim is genuinely true, not merely argued, mirroring
    `EP057_DESIGN.md` Section 12's own "Bootstrap wiring test" for an
    analogous "no Bootstrap/CLI change needed" claim.
- **Regression:** `tests/EP029` (Planning Engine) re-run to confirm
  `DefaultPlanningProvider`'s own behavior is completely unaffected,
  plus `tests/EP028`, `tests/EP030`, `tests/EP031`, `tests/EP032`
  (Agent Framework, Plan Execution, Tool Engine, Multi-Agent
  Collaboration) to confirm zero regression in any package this
  document declines to modify (Section 4).

---

## 13. File-scope matrix (provisional, Candidate A — NOT authorized until D1 is approved)

### CREATE

- `src/core/planning/ai_planning_provider.py` (Section 6.1) --
  `AIPlanningProvider` only.
- `tests/EP058/__init__.py`, `tests/EP058/test_autonomous_planning.py`.

### MODIFY

- `src/bootstrap.py` -- additive only: construct one
  `AIPlanningProvider(provider_manager=...)` at the existing Planning
  construction site (immediately after `PlanningManager`'s own
  construction, mirroring exactly how `ToolExecutionProvider` is
  registered as an additional plan-execution provider at the existing
  Plan Execution construction site, Section 3.4) and register it via
  `planning_manager.register_provider(...)` -- the already-existing,
  unmodified public method (Section 3.2). `planning.default_provider`
  is **not** changed anywhere in `config/config.yaml` (remains
  `"planning"`). No existing construction, ordering, or registration
  call for any other subsystem is touched.
- `src/modules/test_module.py` -- additive only: one new import
  registering `tests.EP058.test_autonomous_planning`.

### DO NOT MODIFY

- `src/core/planning/planning_provider.py`, `planning_manager.py`,
  `planning_engine.py`, `planning_result.py` -- **zero changes**;
  `DefaultPlanningProvider`'s own behavior, `_KEYWORD_RULES`, and
  `PlanningEngine`'s Agent-Framework reconciliation logic are called,
  never modified.
- `src/core/agent/`, `src/services/agent_service.py`,
  `src/modules/agent_module.py` -- **zero changes**; Candidate B
  (Section 5), which would require modifying these, is explicitly
  rejected for v1.
- `src/core/plan_execution/`, `src/services/plan_execution_service.py`,
  `src/modules/plan_execution_module.py` -- **zero changes**;
  `AIPlanningProvider` only ever produces a `Plan` (Section 6.6);
  turning it into dispatched work is unaffected.
- `src/core/tool/`, `src/services/tool_service.py`,
  `src/modules/tool_module.py` -- **zero changes**; Tool Engine's
  existing, narrower-than-Planning action vocabulary (Section 3.4) is
  read only implicitly, through Planning's own already-existing menu
  (Section 6.5), never modified or extended.
- `src/core/collaboration/`, `src/core/workflow_engine/`,
  `src/core/workflow_scheduler/`, `src/core/automation_engine/`,
  `src/core/background_workers/` (EP-032-036) -- **zero changes**;
  none is touched or called by this candidate at all.
- `src/core/ai/provider_manager.py`, `provider.py`, `conversation.py`,
  `conversation_manager.py`, `context_manager.py`, `prompt.py`,
  `prompt_builder.py`, `prompt_manager.py`, `src/services/ai_service.py`
  -- **zero changes**; `ProviderManager.get_current()`/`AIProvider.
  ask()` are called only through their existing, unmodified public
  API (Section 3.8), and `AIService`'s own Conversation/Context/
  Prompt Engine pipeline is never touched or entered.
- `src/core/memory/`, `src/core/long_term_memory/`, `src/core/knowledge/`,
  `src/core/semantic/`, `src/core/context_compression/` -- **zero
  changes**; none is called directly by `AIPlanningProvider` (Section
  6.6) -- they remain reachable only exactly as they already are,
  through Planning's existing keyword vocabulary regardless of which
  provider is active.
- `src/core/command_router.py` -- zero changes; no new namespace, no
  new action (Section 6.4/8).
- `config/config.yaml` -- **zero changes** required for `AIPlanningProvider`
  itself (Section 7); a possible, owner-decided `max_tokens` addition
  is scoped as Owner Decision D3, not assumed.
- Every EP-001…EP-057 design/audit document and every other prior
  EP's source/test files, and `JARVIS_ROADMAP.md`/`BACKLOG.md`/
  `CHANGELOG.md`/`RELEASE_NOTES.md` (STEP 1 does not update
  documentation per this task's own instruction).

---

## 14. Compatibility considerations

Fully additive under Candidate A -- no existing method's signature,
return type, or behavior changes; `DefaultPlanningProvider` remains
the default and remains completely unaffected; no existing config
key's meaning or default changes; no existing `CommandModule` action
is affected. `PlanningEngine`'s existing consumers
(`PlanExecutionEngine.execute_request()`, `WorkflowEngine`, and
everything built on top of them, Section 3.3/3.6) continue to receive
`Plan`/`PlanStep` objects in the exact same shape regardless of which
provider produced them -- `AIPlanningProvider` is, by design, a
drop-in, same-shape substitute for `DefaultPlanningProvider`, not a
new kind of output consumers must special-case.

---

## 15. Implementation constraints

Bound by `AI_GENERATION_STANDARD.md` exactly as every prior EP was:
no architecture redesign, no invented API on `ProviderManager`/
`AIProvider`/`PlanningManager` ("Unknown API Policy" -- applied here
also to the AI's own free-text output, Section 6.5), one class one
responsibility, 300-line-recommended/500-line-hard file-size limit
(the new file is a single, small provider class, well under this
limit), type hints, docstrings, no hardcoded credentials/paths.

---

## 16. Acceptance criteria (for STEP 1)

- [x] Every roadmap/backlog/engineering-guide/prior-EP-cross-reference
  to EP-058/"Autonomous Planning" was found and quoted verbatim
  (Section 2) -- not summarized from memory.
- [x] The genuine absence of a functional specification is reported
  explicitly, not silently filled (Section 0/2).
- [x] Every one of the eight named infrastructure areas (Agent
  Framework, CommandRouter, Tool Engine, AIService/ProviderManager,
  Conversation/Context Engine, Memory/LTM/Semantic Search, Prompt
  Engine, Scheduler/automation infrastructure, task/job/execution
  infrastructure) was inspected directly against its own source
  (Section 3), not assumed relevant or irrelevant by name alone, per
  this task's explicit instruction.
- [x] No similarly-named existing class or module (`PlanningEngine`,
  `AgentEngine`, `ExecutionEngine`, `WorkflowEngine`, `Scheduler`) was
  assumed to be EP-058's target without direct evidence -- each was
  individually confirmed to be a distinct, already-complete,
  differently-scoped Engineering Package (Section 3.1-3.7), and two
  deliberate same-word naming collisions with unrelated, pre-existing
  packages (EP-007's dormant Workflow, EP-011's active Scheduler)
  were explicitly identified and avoided (Section 3.6).
- [x] The single strongest-looking piece of evidence (`PlanningProvider`'s
  own docstring naming an AI-backed provider as its intended extension
  point) was presented alongside three independently-derived
  alternatives, one of which (Candidate B) is arguably better-anchored
  to a literal, runtime-visible message, rather than assumed correct
  by default (Section 5).
- [x] Reusable existing components were identified and no candidate
  proposes duplicating `Plan`/`PlanStep` (EP-029),
  `PlanExecutionEngine`'s dispatch loop (EP-030), `AgentEngine`'s
  subsystem registry (EP-028), or any Phase 5 package's sequencing
  logic (Section 4/6.6).
- [x] At least the minimum necessary Owner Decision to proceed (D1, a
  definitional choice among repository-grounded candidates) is
  presented, with three further candidates explicitly considered and
  either recommended, deferred, or rejected with reasoning (Section
  5).
- [x] A complete, provisional architecture is presented for the
  *recommended* candidate only, explicitly marked contingent on D1's
  approval (Sections 6-15), and explicitly does not modify any
  existing subsystem's core files (Section 13's DO NOT MODIFY list).
- [x] File scope is narrow, explicit, and auditable -- no directory-
  level authorization (Section 13).
- [x] No source, test, configuration, dependency, or Bootstrap file
  was created or modified.
- [x] STEP 2 has not begun.

---

## 17. Unresolved questions this document does not answer

Recorded explicitly, per this task's instruction not to silently
guess:

- Whether the owner even agrees "Autonomous Planning" should mean
  Candidate A at all -- this is precisely Owner Decision D1, and this
  document's entire Sections 6-16 are void if the answer is anything
  else.
- Whether closing Section 3.1's literal "No Planner/Reasoning Engine
  is registered yet (future EP)" message (Candidate B) is a direction
  the owner wants pursued at all, now or later, independently of
  whichever candidate D1 selects -- recorded as rejected for v1 but
  not foreclosed permanently, and genuinely well-grounded in its own
  right (Section 5).
- Whether a future EP (EP-059 onward, Phase 10 "Jarvis Operating
  System") will expect `AIPlanningProvider`'s output in a specific,
  machine-readable format beyond the existing `Plan`/`PlanStep` shape,
  or will want it wired automatically into some future orchestration
  loop -- no such requirement exists anywhere in the repository today,
  mirroring every prior Phase-9 EP's own identically-worded open
  question about its own successors.
- Whether the fixed, static action-menu approach (Section 6.5) should
  eventually be replaced or supplemented by something that queries
  `AgentEngine.list_subsystems()` or the EP-056 Capability Registry
  for a *dynamic* menu, rather than a hardcoded copy of
  `DefaultPlanningProvider`'s own eight-entry table -- no repository
  evidence currently requires this, and doing so today would add a
  new dependency (`AgentEngine`/Capability Registry) this document's
  recommended candidate deliberately avoids (Section 6.6); recorded
  as a possible, owner-decided future refinement, not built here.

---

## 18. Owner Decisions

None of the decisions below is yet approved. Sections 6-16's
provisional architecture is **not** authorized for STEP 2 until D1 is
approved (and D2-D3, where applicable, are resolved).

### D1 — What does "Autonomous Planning" concretely mean for v1? (primary, definitional decision)

**Question:** Which of Section 5's candidate interpretations (or an
owner-supplied alternative not considered here) should EP-058 v1
actually build?
**Options:** (a) Candidate A -- add `AIPlanningProvider`, a new,
AI-/LLM-backed `PlanningProvider` implementation, registered
alongside (never replacing) `DefaultPlanningProvider`, selectable via
the already-existing `planning use ai` action (recommended); (b)
Candidate B -- wire `AgentEngine.execute()` to the already-existing,
purely deterministic Planning + Plan Execution pipeline, closing
Section 3.1's literal "No Planner/Reasoning Engine is registered yet"
message with zero AI reasoning of any kind (well-grounded, but
requires modifying EP-028's own core files and involves no actual
reasoning); (c) Candidate C -- teach `DefaultPlanningProvider` itself
new rules or an AI fallback (not recommended -- would violate that
provider's own documented "never AI reasoning" invariant); (d)
Candidate D -- a new, standalone multi-step autonomous agent loop,
independent of existing Planning/Agent infrastructure (not
recommended -- duplicates existing infrastructure and requires
inventing a control-flow policy from nothing); (e) an owner-supplied
alternative, in which case this entire document would need to be
revised before STEP 2.
**Recommended option:** (a).
**Technical reasoning:** (a) is the only candidate directly named by
an existing module's own docstring as its intended extension point
(Section 3.2) -- a more specific, more literal anchor than any prior
Phase-9 EP's own strongest evidence. It is purely additive to
Planning's already-existing, already-generic multi-provider machinery,
requires zero modification to any Phase 4/5 package's core files, and
(uniquely among every Phase-9 EP so far) requires **zero new CLI
surface** at all, since `planning use`/`providers`/`plan` already work
generically. (b) is real and well-grounded (Section 3.1) but requires
modifying an already-complete, already-shipped Phase 4 package
(EP-028) and adding a CLI action that does not exist today, for a
result that involves no actual reasoning -- a mismatch with Phase 9's
own stated goal. (c) and (d) both conflict with explicit, existing
architectural invariants or require inventing scope from nothing.
**Security impact:** (a) is the first Phase-9 EP whose recommended
candidate makes a real AI-provider call through an *already-existing*
command (`planning plan`), changing that command's cost/latency
profile only when explicitly opted into via `planning use ai` --
Owner Decision D2 asks the owner to confirm this framing explicitly.
(b) makes no AI-provider call at all. (c)/(d) are unscoped until
their own designs exist.
**Compatibility impact:** (a) is fully additive; (b) modifies
`AgentProvider`/`AgentEngine`; (c) violates `DefaultPlanningProvider`'s
own documented invariant; (d) is unscoped.
**What changes in STEP 2:** (a) → build exactly Section 13's file
scope. (b) → this document would need a full revision scoping the
new `agent execute` CLI action and the `AgentProvider.execute()`
change itself, plus its own test surface. (c) → this document would
need a full revision explicitly overriding `DefaultPlanningProvider`'s
own documented "no AI reasoning" invariant, which this document does
not recommend regardless of which option is otherwise chosen. (d) →
this document would need a full revision designing a control-flow
policy, its own data types, and its own integration points from
scratch.

### D2 — Confirm the cost/latency framing of an already-existing command changing behavior when a new provider is selected

**Question:** Section 9 highlights that `planning plan "<request>"`
(an already-existing, already-familiar command) would, for the first
time, incur a real AI-provider call's cost and latency once an
operator explicitly runs `planning use ai` -- a different situation
from every embedding/semantic/compression "cloud" provider swap,
which are all `enabled: false` by default and today have no realistic
path to accidental selection. Does the owner want any additional
safeguard (e.g. a confirmation message on `planning use ai`, or a
`planning.ai.confirm_cost`-style flag) beyond the existing, unmodified
`planning use <provider>` action's own plain success/failure result?
**Options:** (a) no additional safeguard -- `planning use ai`'s
existing, plain confirmation message is sufficient, exactly as
selecting any other provider anywhere in this repository already
works (as proposed); (b) add a one-time, explicit confirmation step
or flag specific to the `"ai"` planning provider.
**Recommended option:** (a) -- consistent with how every other
provider selection in this repository already behaves, and
`ai.default_provider`/`providers.*.enabled` (both already `false`/
`"none"` by default) are themselves already the primary safeguard
against an unconfigured AI provider being reachable at all (Section
6.3's `NOT_CONFIGURED` handling).
**Security impact:** (a) matches existing precedent exactly; (b)
would be a new, EP-058-specific UX pattern with no analogue elsewhere
in this repository.
**Compatibility impact:** none either way -- new, independent
provider regardless.
**What changes in STEP 2:** (a) → no change to `PlanningModule`. (b)
→ `PlanningModule._use()` (or `PlanningService.use_provider()`) would
need new, provider-name-specific branching logic that does not exist
for any other provider in this subsystem today.

### D3 — Should a `max_tokens` cap be configurable for `AIPlanningProvider`'s one `ask()` call?

**Question:** Section 7 notes `AIPlanningProvider` could optionally
expose a `max_tokens` override, distinct from whatever default the
selected `AIProvider` itself already applies. Should v1 add this as
a new, small configuration value, or rely entirely on the active
provider's own existing default?
**Options:** (a) rely on the active provider's own default -- no new
configuration key (simplest, smallest configuration surface, matches
`PromptOptimizerModule`'s own precedent of not adding a bespoke
per-call token cap); (b) add a new, narrowly-scoped configuration
value (e.g. under a small addition to `planning.*`) specifically for
this call.
**Recommended option:** (a) -- the fixed, short prompt and short,
line-oriented reply format (Section 6.5) make an unusually large or
runaway reply unlikely, and `max_steps` (already-existing, Section
6.5 step 5) already bounds the practical effect of a longer-than-
expected reply regardless.
**Security impact:** none either way.
**Compatibility impact:** none either way -- v1 argument-surface
decision, extendable later without a breaking change.
**What changes in STEP 2:** (a) → `AIPlanningProvider.plan()` calls
`provider.ask(prompt)` with no `max_tokens` argument. (b) → a new
`planning.ai_max_tokens`-style key (exact name to be finalized) is
read once, at `AIPlanningProvider` construction time, mirroring
`PlanningManager`'s own existing config-reading convention.

---

## Owner Approval Checklist

**Owner-approved on the date this section was updated, exactly as
recommended, with no modification to any option below.**

- [x] **D1** — What does "Autonomous Planning" concretely mean for
  v1? **APPROVED: Candidate A** — a new, additive `AIPlanningProvider`
  implementation of the existing `PlanningProvider` abstraction,
  registered alongside (never replacing) `DefaultPlanningProvider`.
- [x] **D2** — Additional cost/latency safeguard beyond the existing
  `planning use ai` action? **APPROVED: no** — `planning use ai`'s
  existing, plain confirmation message is sufficient.
- [x] **D3** — New `max_tokens` configuration value? **APPROVED: no**
  — rely on the active AI provider's own existing default.

**STEP 3 architecture audit
(`docs/architecture/audits/EP058_ARCHITECTURE_AUDIT.md`) found zero
blocking findings — no Owner Decision was required to proceed to
STEP 4.** Two non-blocking, informational findings were identified
and their final disposition recorded during STEP 4
(`EP058_ARCHITECTURE_AUDIT.md` Section 19):

- **Finding 1** (a prose miscount of `_KEYWORD_RULES`'s size in this
  document, Sections 3.2/3.9/5/17) — **corrected** in this document
  during STEP 4 (documentation-only; zero code, test, or config
  change; the implementation itself was never affected, since it
  derives its menu programmatically rather than from any hardcoded
  count).
- **Finding 2** (a pre-existing, project-wide test-framework
  characteristic unrelated to EP-058's own test design) —
  **acknowledged, no action taken**, per the audit's own explicit
  recommendation that any fix belongs to a separate, cross-cutting
  testing-infrastructure decision outside any single EP's scope.

D1-D3 and Sections 6-16's approved architecture are unchanged by STEP
4 — no redesign, no new Owner Decision, no code/test/config
modification beyond the one documentation-only prose correction noted
above.
