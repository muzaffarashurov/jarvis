# EP-055 — Prompt Optimizer — Design Specification (STEP 1)

Status: **STEP 1 — DESIGN APPROVED (D1-D9 all Owner-approved). STEP 2
— COMPLETE. STEP 3 — AUDIT PASSED WITH FINDINGS, then PASS AFTER
REMEDIATION following Owner Decision D10 (STEP 4 fix). STEP 4 —
COMPLETE.**

**Owner Decisions D1-D9 (Section 20) are all APPROVED, exactly as
recommended in this document, with no modification.** Candidate A
(Section 5) is now the approved v1 scope for EP-055, and Sections
6-17's provisional architecture is now the approved architecture —
see the Owner Approval Checklist at the end of this document for the
approved value of each decision.

No source file, test file, configuration file, dependency file, or
Bootstrap file was created or modified as part of producing the
original STEP 1 version of this document. STEP 2 (implementation),
now authorized by the approvals above, is tracked separately per the
repository's own STEP 1 → STEP 2 → STEP 3 → STEP 4 convention
(`docs/BACKLOG.md`'s EP-054 entry).

---

## 0. A note on how this document differs from EP-050…EP-053, and how it relates to EP-054

EP-050 through EP-053 each began with a roadmap line naming a
concrete, well-understood capability whose scope, while still
requiring Owner Decisions on implementation detail, was never in
doubt at the conceptual level. **EP-054 broke that pattern**: direct
inspection found "EP-054 Self Reflection" had no functional
specification beyond its four-word title and Phase 9's one-sentence,
five-EP-wide goal. EP-054's STEP 1 handled this by disclosing the gap
explicitly and deriving several repository-grounded candidate
interpretations rather than inventing a scope from outside knowledge.

**EP-055 is in the identical situation, confirmed by the same
exhaustive-search method (Section 2).** "EP-055 Prompt Optimizer" has
no functional specification anywhere in the repository beyond its
three-word title and the same Phase 9 one-sentence goal EP-054 already
shared with it. This document therefore follows EP-054's own
methodology exactly: Section 2 is a verbatim inventory of every
existing reference, Section 5 derives candidate interpretations from
already-existing architecture (chiefly the already-built EP-017 Prompt
Engine, EP-018 Context Engine, and one explicit clue in
`JARVIS_ARCHITECTURE_VISION.md`, Section 3.6), and Section 20's Owner
Decisions ask the owner to choose among them before any provisional
architecture in Sections 6-17 can be treated as more than a starting
proposal.

**One material difference from EP-054:** EP-054 composed a capability
(Self Reflection) that had *no* existing infrastructure of its own —
it built a new `CommandModule` from already-existing but previously
uncombined managers. EP-055, by contrast, names a capability
("Prompt Optimizer") that overlaps, at least in name, with a
subsystem that **already exists and is fully implemented**: the
EP-017 Prompt Engine (`Prompt`/`PromptBuilder`/`PromptManager`,
Section 3.1). Per `AI_GENERATION_STANDARD.md`'s "Existing Code
Policy" ("Always reuse existing services... Never replace working
implementations unless explicitly requested") and `AI_DEVELOPMENT_
PLAYBOOK.md`'s "No Duplicate Responsibilities" rule, this document
treats the Prompt Engine as **the foundation EP-055 extends**, not
something to redesign, replace, or duplicate. Every candidate in
Section 5 is deliberately framed as an *addition* to
`PromptBuilder`/`PromptManager`'s existing, unmodified pipeline.

---

## 1. Metadata

- **Engineering Package:** EP-055 — Prompt Optimizer
- **Phase:** Phase 9 — Intelligence (`JARVIS_ROADMAP.md` line 719;
  `docs/engineering/ENGINEERING_GUIDE.md` line 163-167: "Improve
  reasoning and autonomous decision making.")
- **Predecessor:** EP-054 Self Reflection — **COMPLETE / PASSED WITH
  FINDINGS** (`docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md`;
  full design and Owner Decisions D1-D9:
  `docs/architecture/designs/EP054_DESIGN.md`).
- **Successors (same phase):** EP-056 Capability Learning, EP-057
  Memory Optimization, EP-058 Autonomous Planning.
- **Foundational, already-complete dependency (different phase):**
  EP-017 Prompt Engine (`Prompt`, `PromptBuilder`, `PromptManager`) and
  EP-018 Context Engine (`Context`, `ContextManager`, `ContextLoader`),
  both fully implemented, unmodified by EP-054, and the subject of
  Section 3's grounding analysis below.
- **This document's scope:** STEP 1 only — repository discovery,
  scope clarification, architecture proposal (contingent on Owner
  Decision D1), and Owner Decision preparation. No code, test,
  configuration, dependency, or Bootstrap file has been created or
  modified as part of producing this document.
- **File created by STEP 1:** this document,
  `docs/architecture/designs/EP055_DESIGN.md`, only.
- **Files modified by STEP 1:** none.

---

## 2. What the repository actually says about EP-055 (verbatim inventory)

Every reference to EP-055 or "Prompt Optimizer" found anywhere in the
repository, found by direct, exhaustive search (not sampling) of
`docs/`, `AI_GENERATION_STANDARD.md`, `AI_DEVELOPMENT_PLAYBOOK.md`,
`CHANGELOG.md`, and `src/`:

| Location | Exact content |
|---|---|
| `docs/architecture/JARVIS_ROADMAP.md` line 723 (Phase 9 list) | `EP-055 Prompt Optimizer` — a bare title, no elaboration |
| `docs/architecture/JARVIS_ROADMAP.md` line 199 ("Current Progress" section, added by EP-054 STEP 4) | `**Next Engineering Package: EP-055 Prompt Optimizer — NOT STARTED.** No EP-055 design, research, or implementation work has begun.` — a status pointer, not a spec |
| `docs/architecture/JARVIS_ROADMAP.md` line 200 | Same "NOT STARTED" statement, repeated |
| `docs/BACKLOG.md` lines 13-18 ("Next Engineering Package" section, added by EP-054 STEP 4) | `### EP-055 — Prompt Optimizer` / `**NOT STARTED.** Per docs/architecture/JARVIS_ROADMAP.md's Phase 9 sequencing, EP-055 (Prompt Optimizer) is the next Engineering Package after EP-054's completion. No design, research, or implementation work has begun.` — same pointer, same lack of elaboration |
| `CHANGELOG.md` line 128 | References EP-055 (Prompt Optimizer) only as "the next, not-started Engineering [Package]" in an EP-054-completion entry — a status note, not a spec |
| `docs/architecture/designs/EP054_DESIGN.md` (five occurrences: lines 50, 197, 214, 605, 696) | All five are EP-054's own Section 1/4/19/20 cross-references listing EP-055 as a *successor* EP that Self Reflection's output might one day feed, or that Self Reflection deliberately does not attempt to replicate the role of (e.g. line 197: "That capability, if ever built, belongs to EP-055 Prompt Optimizer..."). None define EP-055's own scope; each treats it as a name only |
| `docs/engineering/ENGINEERING_GUIDE.md` (Phase 9 section, lines 163-168) | `## Phase 9 — Intelligence` / `Improve reasoning and autonomous decision making.` / `Engineering Packages:` / `EP-054 … EP-058` — a **phase-level** goal shared across all five Phase-9 EPs (identical text EP-054's own Section 2 already quoted), not an EP-055-specific one |
| `docs/architecture/JARVIS_ARCHITECTURE_VISION.md` "Prompt Engine" section (lines 184-199) | Does not mention EP-055 or "Prompt Optimizer" by name, but lists the Prompt Engine's intended responsibilities as: prompt templates, context loading, project rules, coding standards, memory injection, task formatting, **and "provider optimization"** — the single most concrete, repository-grounded clue this document found toward what "optimizing" a prompt might mean (Section 5) |
| Everywhere else (`PROJECT_MANIFEST.md`, `AI_GENERATION_STANDARD.md`, `AI_DEVELOPMENT_PLAYBOOK.md`, every EP-001…EP-053 design/audit document, `src/`) | **Zero** additional mention of EP-055, "Prompt Optimizer", or any synonym of it |

**Conclusion (identical in kind to EP-054's own Section 2
conclusion):** the repository establishes *that* Prompt Optimizer is
next, and *that* it belongs conceptually to "Intelligence" alongside
reasoning/autonomous decision-making, and offers one indirect,
pre-existing clue (`JARVIS_ARCHITECTURE_VISION.md`'s "provider
optimization" phrase, written when EP-017 was designed, long before
EP-055 was ever scheduled) — but it establishes **no concrete
behavior, input, output, trigger, metric, or user interface** for
EP-055. Per the task's explicit instruction, this gap is reported
here rather than silently filled.

---

## 3. Relevant existing architecture (grounds for the candidate interpretations in Section 5)

Direct inspection, to ground Section 5's candidates in what actually
exists rather than in the abstract.

### 3.1 The EP-017 Prompt Engine — already built, already the sole prompt-composition authority

`src/core/ai/prompt.py` (`Prompt`, an immutable, already-composed
prompt: `system_prompt` + `context` + `user_prompt`, rendered in that
fixed order), `src/core/ai/prompt_builder.py` (`PromptBuilder`,
fluent assembly + validation + the project's **one** prompt-sizing
authority — `resolve_max_prompt_size()`, `resolve_document_budget()`,
`resolve_conversation_budget()`, all `@staticmethod`, all consumed by
`ContextManager`/`ContextLoader` via Dependency Injection per
EP-018.5/018.6), and `src/core/ai/prompt_manager.py` (`PromptManager`,
resolves the configurable default system prompt from `prompt.*`,
drives `PromptBuilder` through the fixed "Prompt Flow" — System Prompt
→ Conversation Context → Memory (future) → Capability Context
(future) → Additional Instructions → User Prompt — and owns the
in-memory prompt registry). This is a complete, tested, unmodified-
by-EP-054 subsystem. **Any EP-055 design must extend this pipeline,
never re-implement or bypass it** (Section 0).

### 3.2 `PromptBuilder.load_template()` / `PromptManager.build(template=...)` — an existing, currently-unused extension seam

`PromptBuilder.load_template(name)` reads a file from the configured
`paths.prompts` directory (default `"prompts"`) and appends its
content as an instruction block; `PromptManager.build()` accepts an
optional `template` argument that drives this. Direct inspection
(`grep -rn "template=" src/`, excluding tests) found **zero existing
callers** of this parameter anywhere in the composition root
(`src/bootstrap.py`) or any service (`AIService.ask()` calls
`PromptManager.build()` without a `template` argument, Section 3.4).
The `prompts/` directory itself is currently **empty** (`ls prompts/`
found no files). This is a fully-wired but never-exercised extension
point — a plausible, low-risk integration seam for a "prompt
optimizer" that works by selecting or improving templates, without
requiring any change to `PromptBuilder`/`PromptManager` themselves.

### 3.3 `Prompt.metadata` — an existing, generic, currently underused attachment point

`Prompt` carries a `metadata: dict[str, Any]` field, settable via
`PromptBuilder.append_metadata(key, value)` and
`PromptManager.build(metadata=...)`/`create(metadata=...)`. Today,
`AIService.ask()` never populates it (Section 3.4). This is a
plausible place to record *how* a given `Prompt` was produced (e.g.
"template used", "optimization applied: none/v1") for later
inspection or comparison, without changing `Prompt`'s frozen
dataclass shape.

### 3.4 `AIService.ask()` (`src/services/ai_service.py`) — the one place the full pipeline is assembled

`ask()` implements the fixed flow (module docstring, lines 18-48):
`User → Conversation Engine → Context Engine → Prompt Engine →
ProviderManager → Provider`. It calls `self._context_manager.create()`
then `self._prompt_manager.build(user_prompt=prompt, context=[context]
if context else None, provider_name=name)`, then
`current.ask(built_prompt.rendered)`. **This is the single call site**
any "optimize the prompt before sending it" behavior would need to
sit alongside — either inside `PromptManager.build()` itself (Section
3.1's existing pipeline) or as an additional step `AIService.ask()`
invokes between `PromptManager.build()` and `current.ask()`. No
second call site exists anywhere else in the repository that also
sends a prompt to a provider outside this pipeline, **except**
`ReflectionModule` (EP-054), which deliberately bypasses
`AIService`/`PromptManager` entirely and calls
`ProviderManager.get_current().ask()` directly, precisely so a
reflection request never becomes a new conversation turn
(`EP054_DESIGN.md` Section 6.4). This is a **deliberate exception**
recorded by EP-054's own design, not a second general-purpose pipeline
EP-055 should extend.

### 3.5 `AIProvider.ask()` (`src/core/ai/provider.py`) — the unmodifiable provider contract

`AIProvider.ask(prompt: str, max_tokens: int | None = None) ->
ProviderResponse` is the one method every provider (Claude, OpenAI,
Ollama, LM Studio, Gemini, ...) implements. Per `AI_GENERATION_
STANDARD.md`'s "Public API Policy" ("Never change method signatures...
unless explicitly requested"), this document does not propose changing
this signature. **No per-provider model/token-limit/capability
metadata exists anywhere in `provider.py`, `provider_manager.py`, or
`provider_registry.py`** beyond `ProviderStatus`
(`DISABLED`/`NOT_CONFIGURED`/`AVAILABLE`) and each concrete provider's
own `list_models()` (EP-015). This is a material grounding fact:
`JARVIS_ARCHITECTURE_VISION.md`'s "provider optimization" phrase
(Section 2) has **no existing per-provider data model to optimize
against** today (e.g. no stored context-window size, no stored
per-model pricing, no stored "this provider prefers XML-tagged
instructions" preference). Any candidate that assumes such
optimization exists at a granular, per-provider level would require
building that data model first — recorded as a real gap, not silently
assumed away (Section 4, Section 19).

### 3.6 `JARVIS_ARCHITECTURE_VISION.md`'s "Prompt Engine" section — the one indirect design clue

Lines 184-199 (quoted in full in Section 2's table) list the Prompt
Engine's intended responsibilities, including "provider optimization"
alongside "prompt templates", "context loading", "memory injection",
and "task formatting" — all of which EP-017/018 already substantially
deliver except "provider optimization" itself. This document treats
this phrase as the **strongest available, though still indirect,**
grounding for what "Prompt Optimizer" might concretely mean: the
vision document was written describing the Prompt Engine's own
long-term responsibilities, and "provider optimization" is the one
listed responsibility no EP has yet built. It is not, however, a
functional specification — it does not say *how* a prompt should be
optimized "for" a provider, does not name a metric, and does not say
whether "optimization" means format/structure changes, length/token
reduction, wording/phrasing quality, or something else entirely.

### 3.7 The Feedback Loop / Human Approval principles (`JARVIS_ARCHITECTURE_VISION.md` lines 459-511)

The vision document's "Feedback Loop" section describes a general
Generate → Test → Review → Improve → Repeat → Approve → Complete cycle
("Jarvis should continuously improve results before presenting
them"), and its "Human Approval" section requires user confirmation
before "irreversible actions" (publishing, sending emails, deleting
files, git push, production deployment). Neither section names
prompts specifically, and neither is EP-055-specific, but both are
relevant background: they suggest that *if* EP-055 is scoped to
autonomously rewrite prompts, that rewriting is not the kind of
"irreversible action" the Human Approval section is concerned with
(a rewritten prompt is fully inspectable and reversible, unlike
publishing or deleting), but the Feedback Loop language does imply
some notion of "improve, then evaluate" that Section 5's Candidate A
takes as its closest available grounding.

### 3.8 `src/testing/` (Jarvis's own test framework) — confirmed absence of any prompt-evaluation infrastructure

`src/testing/` (`BaseTest`, `TestResult`, `TestRegistry`, `TestRunner`,
`TestReport`) is Jarvis's own internal test-suite framework used to
run `tests/EPxxx/` suites — it has no relationship to evaluating or
scoring the *quality* of a generated prompt or an AI response. Direct
inspection confirms **no existing component anywhere in the repository
measures, scores, or compares prompt effectiveness, response quality,
token efficiency, or provider-specific prompt performance.** Any
candidate that requires such a metric (e.g. "shorten prompts without
losing quality", "select the best-performing template") would need to
define that metric from nothing — flagged here as a real, unresolved
gap (Section 19), exactly as EP-054's own Section 5 flagged Candidate
D's lack of a reasoning-quality rubric.

### 3.9 `CommandRouter` / `CommandModule` precedent (`src/core/command_router.py`, Section 3.1 of `EP054_DESIGN.md`)

`desktop`, `browser`, `file`, `vision`, and `reflect` (EP-054) are
each a `CommandModule` registered with the unmodified
`CommandRouter.dispatch()`. This remains the established pattern for
any EP-055 capability that should be **manually, explicitly
invokable** by a user (e.g. "optimize this specific prompt on
request") — as opposed to capability that runs automatically, inline,
inside `PromptManager.build()`/`AIService.ask()`'s existing pipeline
(Section 3.4) for **every** request. Which of these two integration
shapes is appropriate depends entirely on Owner Decision D1/D2
(Section 20) — this document does not assume one over the other.

---

## 4. Non-goals (applicable regardless of which Section 5 candidate is chosen)

- **This document does not implement, and does not authorize STEP 2
  to implement, any per-provider capability database** (context-window
  sizes, pricing, model-specific prompting preferences) that does not
  already exist (Section 3.5). If a chosen candidate requires one,
  that is a separate, larger prerequisite this document flags but does
  not design.
- **No redesign, replacement, or bypass of the EP-017 Prompt Engine.**
  `Prompt`/`PromptBuilder`/`PromptManager`'s existing public API,
  fixed "Prompt Flow" order, and sole prompt-sizing authority
  (`resolve_max_prompt_size()`/`resolve_document_budget()`/
  `resolve_conversation_budget()`) are treated as fixed, per Section
  0 and `AI_GENERATION_STANDARD.md`'s "Existing Code Policy". Any
  EP-055 candidate is additive to this pipeline.
- **No modification of `ConversationManager`, `ContextManager`,
  `ContextLoader`, `ProviderManager`, `AIProvider`, or any provider
  implementation's existing behavior.** EP-055 reads from/composes
  with these through their existing public APIs only, exactly as
  EP-054 did with `ConversationManager`/`AIProvider`/`MemoryManager`.
- **No autonomous, unattended, budget-uncapped AI-provider usage** —
  if a chosen candidate uses an AI provider to *evaluate* or *rewrite*
  a prompt (an "AI optimizing AI prompts" loop), that usage must be
  bounded and rate-limited exactly as `reflection.max_message_count`/
  `reflection.min_seconds_between_calls` bound EP-054's own
  AI-provider usage (`EP054_DESIGN.md` Section 7/8) — not built here,
  but recorded as a hard constraint any Section 5 candidate involving
  an AI-provider call must satisfy.
- **No automatic, unreviewable rewriting of user-authored request
  text.** Per the Human Approval principle's spirit (Section 3.7),
  even though prompt rewriting is reversible/inspectable rather than
  "irreversible," this document does not recommend a v1 where a
  user's literal request text is silently replaced with no visibility
  into what changed — see Candidate A's `metadata`-based transparency
  requirement (Section 5).
- **No cross-EP scope creep.** This document does not redesign or
  re-scope EP-054, EP-056, EP-057, or EP-058; it only notes, where
  relevant, that a given Prompt Optimizer candidate's output could be
  a plausible *future* input to one of them, without building that
  integration itself.

---

## 5. Candidate interpretations of "Prompt Optimizer" (grounds for Owner Decision D1)

Each candidate is derived from an existing, already-inspected part of
the repository (Section 3), not invented from outside knowledge of
what "prompt optimization" might mean in the abstract. None is
authorized; Owner Decision D1 (Section 20) asks the owner to choose
one (or explicitly reject all of them and redirect this document).

### Candidate A — Template-based prompt improvement via the existing, unused template seam (recommended starting point)

A new, explicit, on-demand capability that takes an existing prompt
template (or ad-hoc prompt text) and produces an *improved* version of
it — restructured, clarified, or shortened — using the currently
configured AI provider via a single, direct `AIProvider.ask()` call
(mirroring `ReflectionModule`'s own deliberate bypass of
`AIService`/`PromptManager` for the same reason: an optimization
request must not itself become a new conversation turn, nor
recursively re-invoke the very Prompt Engine it is trying to improve).
The improved result is returned to the user (and, optionally, written
back to a file under `paths.prompts` as a new or updated template,
Owner Decision D4) — never applied automatically to live traffic. This
exercises Section 3.2's already-existing, currently-dead
`load_template()`/`template=` seam by finally giving templates a
reason to be authored, without any change to `PromptBuilder`/
`PromptManager` themselves.

**Why recommended:** smallest, most bounded, most easily tested
interpretation; composes exactly one already-existing, unmodified
component (`AIProvider`, via the same "one direct call, not through
`AIService`" pattern EP-054 already established and tested); produces
a concrete, inspectable artifact (the improved prompt text) rather
than an abstract, hard-to-verify "reasoning improvement"; and directly
exercises Section 3.2's already-built-but-idle extension point instead
of adding a new one. Mirrors `EP054_DESIGN.md` Section 5 Candidate A's
own reasoning almost exactly, one layer up the stack (optimizing the
*template that becomes* a prompt, rather than critiquing a
*conversation*).

### Candidate B — Automatic, per-request prompt structuring inside the existing Prompt Engine pipeline

A capability that runs *automatically*, inline, for every
`PromptManager.build()` call — e.g. re-ordering, deduplicating, or
compressing the assembled context/instruction blocks before
`PromptBuilder.build()` validates and renders them, so every outgoing
prompt is "optimized" without any explicit user action. This would sit
inside `PromptBuilder`'s own `_compose_context()`/`build()` methods
(Section 3.1) or as a new step `PromptManager.build()` calls between
composing parts and calling `builder.build()`.

**Blocked by a real gap and a real risk, both confirmed by
inspection:** (1) EP-018.5 already established `PromptBuilder` as the
"SOLE authority on prompt sizing in the project" specifically to
prevent multiple, drifting sizing/composition rules (its own module
docstring); inserting a second, EP-055-owned transformation step
inside that same class risks exactly the "hidden coupling"/
"duplicate responsibility" `AI_GENERATION_STANDARD.md` warns against
unless very carefully scoped as a distinct, injectable step, not an
edit to `PromptBuilder`'s existing methods. (2) Automatic,
provider-facing content transformation with no user-visible
before/after (unlike Candidate A's explicit request/response shape)
is harder to test deterministically and harder for an operator to
reason about when something goes wrong — every existing
`prompt.*`/`context.*` config default is currently either
`enabled: true` with fully deterministic, non-AI-provider-based
logic (character budgets, ordering) or `enabled: false` by default
for anything that reaches an AI provider. This document does not
recommend attempting this candidate inside EP-055 v1 without a much
more detailed follow-up design specifically addressing where inside
`PromptBuilder`'s pipeline the step would live and how it stays
provider-independent and deterministic-by-default.

### Candidate C — Prompt/response effectiveness tracking and reporting (no rewriting)

A capability that only *measures* — e.g. recording, per `Prompt`
(using the already-existing but currently-empty `Prompt.metadata`
field, Section 3.3), some cheap, deterministic proxy for
"efficiency" (character/token count relative to `prompt.
max_prompt_size`, template used, provider used) and exposing a report
(`prompt stats`, mirroring `reflect recall`'s read-back shape) — never
rewriting or suggesting changes to any prompt itself.

**Viable but narrower than the roadmap's own framing suggests:**
Section 2's evidence (`JARVIS_ARCHITECTURE_VISION.md`'s "provider
optimization") and Phase 9's own "Improve reasoning and autonomous
decision making" goal both imply EP-055 does something *active*
toward improving prompts, not merely reporting on them passively.
This document records Candidate C as a smaller, safer *fallback* if
the owner rejects Candidate A's AI-provider-driven rewriting outright
(Owner Decision D1's option (c)), not as the primary recommendation.

### Candidate D — General, provider-specific prompt-formatting rules (rejected as a v1 candidate)

An interpretation where Jarvis maintains a table of provider-specific
prompt-formatting best practices (e.g. "Claude prefers XML tags",
"provider X prefers system-prompt-first framing") and rewrites prompts
to match whichever provider is currently active, closest to a literal
reading of `JARVIS_ARCHITECTURE_VISION.md`'s "provider optimization"
phrase. **This document does not recommend this candidate for v1**:
Section 3.5 already confirmed no per-provider capability/preference
data model exists anywhere in the repository today, and building one
from nothing, with no existing convention to model it on, would be
exactly the kind of "invent[ed]... because it seems technically
interesting" scope `AI_GENERATION_STANDARD.md`/this task's own
instructions warn against. This candidate is recorded only to be
explicitly rejected, not silently omitted — the owner may of course
choose it anyway (Owner Decision D1), in which case this document
would need substantial revision to design that missing data model
first.

---

## 6. Proposed architecture (contingent on Owner Decision D1 = Candidate A)

**Everything in this section and Sections 7-19 is provisional,
written against Section 5's recommended Candidate A, and is not
authorized until Owner Decision D1 (Section 20) is explicitly
approved.** If the owner selects a different candidate, or rejects
all of them, this document's STEP 1 must be revised before STEP 2 can
begin — this document does not pre-authorize a fallback path.

### 6.1 Namespace and module

A new `prompt` `CommandModule` (`src/skills/prompt_optimizer/skill.py`,
`PromptOptimizerModule`), dispatched through the *existing*,
unmodified `CommandRouter.dispatch()` — the same, now six-times-
independently-applied pattern (Section 3.9). **Note on naming:**
`prompt` is not currently a registered `CommandRouter` namespace
(confirmed by inspection — no existing `CommandModule` claims it), so
no collision exists; the exact namespace name is nonetheless recorded
as part of Owner Decision D2, since "prompt" could later be confused
with the (non-command-facing) EP-017 "Prompt Engine" internals.

### 6.2 No new backend Protocol

Like EP-054's Candidate A and unlike `desktop`/`browser`/`file`/
`vision`, Candidate A introduces no new external I/O surface beyond
the already-existing `AIProvider`/`ProviderManager` and, optionally,
the filesystem access already implied by `paths.prompts` (Section
3.2) — not a *new* filesystem surface, since `PromptBuilder.
load_template()` already reads from that same directory today. This
document proposes `PromptOptimizerModule` depend on `ProviderManager`
directly via constructor injection (mirroring `ReflectionModule`'s own
`ProviderManager` dependency, `EP054_DESIGN.md` Section 6.2), with
**no new Protocol/backend abstraction**.

### 6.3 Command/action design (provisional)

| Action | Arguments | Description |
|---|---|---|
| `prompt help` | none | List available actions. |
| `prompt optimize <text>` | free-text prompt or `--template <name>` | Send `text` (or the named template's current content) to the configured AI provider via `AIProvider.ask()`, with a fixed, optimization-oriented instruction ("improve clarity/structure of this prompt; do not change its intent"), and return the improved version as `CommandResult.message`. Never modifies the original template file (Owner Decision D4 governs whether a *separate* save action exists). |
| `prompt save <name>` | template name | (Only if Owner Decision D4 authorizes it) Write the most recently produced `prompt optimize` result to `paths.prompts/<name>.txt`, so it becomes usable via `PromptManager.build(template=<name>)`'s existing, already-built mechanism (Section 3.2). Requires an explicit, separate action — never an automatic side effect of `prompt optimize` itself, consistent with Section 4's "no automatic, unreviewable rewriting" non-goal. |

### 6.4 Integration points

- `ProviderManager.get_current()` → the active `AIProvider`, on which
  `PromptOptimizerModule` calls the existing, unmodified `AIProvider.
  ask()` (EP-015) directly — mirroring `ReflectionModule`'s own
  deliberate bypass of `AIService`'s higher-level pipeline
  (`EP054_DESIGN.md` Section 6.4), for the same reason: an
  optimization request must not append itself as a conversation turn,
  nor recursively pass through the very `PromptManager`/`PromptBuilder`
  pipeline whose *template input* it is trying to improve.
- `paths.prompts` (already-configured, `config/config.yaml` — Section
  3.2) — read, to load an existing template's current content when
  `--template <name>` is given; written, only if Owner Decision D4
  authorizes `prompt save`.
- **No** integration with `PromptBuilder`/`PromptManager`'s own
  `build()`/`create()` methods proposed for v1 (Candidate B, Section
  5, is explicitly not built here) — `PromptOptimizerModule` never
  intercepts or modifies a live, in-flight `Prompt`.
- **No** integration with `AgentEngine.register_subsystem()` proposed
  for v1, for the same reasoning EP-054's own Owner Decision D6
  recorded (`EP054_DESIGN.md` Section 3.2/20): the subsystem registry
  is used exclusively by Phase 3-6 components today, and extending it
  here would be a speculative addition with no concrete consumer.

---

## 7. Security model (provisional, Candidate A)

- `prompt_optimizer.enabled` (default `false`) — the master gate,
  re-checked on every dispatched `prompt ...` action, identical in
  spirit to `reflection.enabled`/`vision.enabled`/`file.enabled`/
  `browser.enabled`/`desktop.enabled`.
- **AI-provider cost/privacy gate, separate from `prompt_optimizer.
  enabled` or not** — every `prompt optimize` call sends prompt/
  template text (which, per Section 4's non-goal, is never
  conversation content — only template text or ad-hoc text the caller
  explicitly supplies as an argument) to whichever AI provider is
  currently configured. This document recommends **no second,
  separate gate** beyond `prompt_optimizer.enabled` itself (Owner
  Decision D3), for the same reasoning `EP054_DESIGN.md` Section 7
  already recorded for `reflection.enabled`/`reflect summary`: this is
  not qualitatively different from what every other AI-provider-
  consuming feature in this repository already does. Recorded
  explicitly so the owner can override it if they disagree, exactly as
  EP-054's own Owner Decision D2 was recorded for the same reason.
- **Resource/rate limits** — `prompt_optimizer.max_input_size`
  (bounds how large a single `prompt optimize` input may be, protecting
  `AIProvider` token cost and prompt size, mirroring `reflection.
  max_message_count`'s own resource-cap precedent) and
  `prompt_optimizer.min_seconds_between_calls` (a simple, in-process
  rate limit, mirroring `reflection.min_seconds_between_calls` exactly)
  — Owner Decision D6.
- **Filesystem write gate for `prompt save`** (only relevant if Owner
  Decision D4 authorizes that action at all): writing to `paths.
  prompts` is a **new** write surface (Section 3.2's `load_template()`
  is read-only today) — this document recommends `prompt save` be
  gated by `prompt_optimizer.allow_save` (default `false`), a second,
  independent flag beyond `prompt_optimizer.enabled`, mirroring
  `vision.allowed_roots`'s own "the master gate alone is not enough
  for a filesystem-touching action" precedent (`EP053_DESIGN.md`).
- **No shell/code execution, no network call beyond the already-
  existing `AIProvider` call** — `PromptOptimizerModule` introduces no
  new I/O surface beyond the two named above.

---

## 8. Configuration (provisional, Candidate A)

A new `prompt_optimizer:` block in `config/config.yaml`, following the
established `enabled`-default-`false` convention (deliberately named
`prompt_optimizer`, not `prompt`, so it cannot be confused with the
already-existing `prompt:` block that configures the EP-017 Prompt
Engine itself, Section 3.1):

```yaml
prompt_optimizer:
  enabled: false
  allow_save: false          # Owner Decision D4
  max_input_size: 4000
  min_seconds_between_calls: 30
```

---

## 9. Dependencies

**No new third-party dependency is anticipated for Candidate A.**
`ProviderManager`/`AIProvider` are already-installed, already-imported,
unmodified components; `ask()` already returns free text with no new
parsing library required; `paths.prompts` file I/O uses only the
standard library (`pathlib`), exactly as `PromptBuilder.
load_template()` already does. This document explicitly recommends
**against** introducing any new dependency for EP-055's v1.

---

## 10. Error handling (provisional, Candidate A)

- `PromptOptimizerModule` catches exactly the exception types already
  defined by its one real dependency — `AIProvider`'s own
  `ProviderUnavailableError`/`ProviderConfigurationError`/
  `ProviderError` (already exist, Section 3.5) — translating each
  into a failed `CommandResult`, never an uncaught exception,
  mirroring every prior skill's convention (including `Reflection
  Module`'s own).
- `PromptTemplateNotFoundError` (already exists, `src/core/ai/
  prompt_builder.py`, Section 3.2) is reused, not re-implemented, when
  `--template <name>` references a template that does not exist —
  consistent with `AI_GENERATION_STANDARD.md`'s "No Duplicate
  Responsibilities" rule.
- If `prompt_optimizer.enabled` is `false`, or the configured AI
  provider is unavailable, or `max_input_size` is exceeded, `prompt
  optimize` returns a clear, non-crashing failure message.

---

## 11. Cross-platform considerations

None anticipated beyond what `PromptBuilder.load_template()` already
handles today (plain UTF-8 text file read via `pathlib`, Section 3.2)
— Candidate A introduces no OS-specific I/O of any kind (no device, no
external binary), unlike `desktop`/`browser`/`vision`.

---

## 12. Testing strategy (provisional, Candidate A)

Mirrors the now-established convention (`EP054_DESIGN.md` Section 12):

- **`tests/EP055/test_prompt_optimizer.py`** (primary, always-run
  suite):
  - Protocol/argument-shape tests (wrong argument count/missing
    `<text>` for `prompt optimize`; unknown `--template` name).
  - `prompt_optimizer.enabled` gate tests (disabled rejects with zero
    calls to `AIProvider`).
  - `allow_save` gate tests (Owner Decision D4-dependent: `prompt
    save` rejected while `allow_save` is `false`, even when
    `prompt_optimizer.enabled` is `true`).
  - Rate-limit tests (`min_seconds_between_calls`) using a fake clock,
    not a real `time.sleep()`, mirroring `ReflectionModule`'s own
    tested rate-limit pattern.
  - Input-size-cap tests (`max_input_size`).
  - Positive-path test using a fake `AIProvider` returning
    deterministic content, asserting the exact prompt constructed
    (the fixed optimization instruction plus the input text) and the
    exact `CommandResult` produced.
  - `--template` loading test using a real, temporary `paths.prompts`
    directory with a known fixture file, and a not-found case using
    the already-existing `PromptTemplateNotFoundError`.
  - Negative/security cases: provider unavailable, provider raises a
    configuration error.
  - `CommandRouter` dispatch-equivalence test, mirroring
    `EP054_DESIGN.md`'s own
    `_test_command_router_dispatch_matches_direct_execute`.
  - `Bootstrap` wiring tests (namespace registered even when disabled,
    disabled message reported, other modules unaffected).
- **No separate "real integration" tier is anticipated**, mirroring
  `EP054_DESIGN.md` Section 12's own reasoning: `paths.prompts` file
  I/O has no external-binary dependency requiring a separate,
  credential-gated tier the way EP-053's Tesseract OCR did.
- **Real-`AIProvider` end-to-end test:** explicitly **not** proposed
  for the default suite, for the identical reasoning
  `EP054_DESIGN.md` Section 12/Owner Decision D9 already recorded
  (live credentials, non-deterministic output). Recorded here as the
  same open question (Section 19) rather than assumed either way.

---

## 13. Regression strategy

Full regression suite (`test all`) re-run exactly as in every prior
EP's STEP 2/3, expecting the same, already-disclosed EP-046/048/049
pre-existing figures plus the new EP-055 suite passing cleanly, with
zero change to any other suite's result — in particular, zero change
to any existing EP-017/EP-018 behavior, since Candidate A adds no code
to `prompt.py`/`prompt_builder.py`/`prompt_manager.py`/
`context_manager.py` at all (Section 14).

---

## 14. File-scope matrix (provisional, Candidate A — NOT authorized until D1 is approved)

### CREATE

- `src/skills/prompt_optimizer/skill.py` — `PromptOptimizerModule`.
- `tests/EP055/__init__.py`, `tests/EP055/test_prompt_optimizer.py`.

**Note:** matching `EP054_DESIGN.md` Section 14's own precedent, this
document does **not** propose a `backend.py`/`local_backend.py` pair
(Section 6.2) — if the owner disagrees, that should be raised as a
revision to Owner Decision D1 before STEP 2, not assumed.

### MODIFY

- `src/bootstrap.py` — additive only: construct
  `PromptOptimizerModule` (injected with `ProviderManager`/
  `AIProvider`), gated by `prompt_optimizer.enabled`, registered
  unconditionally with `CommandRouter`, following the identical wiring
  convention `EP054_DESIGN.md` Section 14/`src/bootstrap.py`'s own
  `ReflectionModule` wiring already established.
- `config/config.yaml` — additive only: new `prompt_optimizer:` block
  (Section 8).
- `src/modules/test_module.py` — additive only: one new import
  registering `tests.EP055.test_prompt_optimizer`.

### DO NOT MODIFY

- `src/core/ai/prompt.py`, `src/core/ai/prompt_builder.py`,
  `src/core/ai/prompt_manager.py` — **zero changes** (Section 0/3.1);
  this is the central architectural constraint of this entire
  document. `PromptOptimizerModule` calls neither `PromptBuilder` nor
  `PromptManager` at all in Candidate A (Section 6.4) — it only reads
  the same `paths.prompts` directory `PromptBuilder.load_template()`
  already reads, via its own, independent file access.
- `src/core/ai/context_manager.py`, `src/core/ai/context_loader.py`,
  `src/core/ai/context.py` — zero changes; unrelated to Candidate A.
- `src/core/command_router.py` — zero changes (Section 3.9).
- `src/core/tool/` — zero changes (same, now six-times-independently-
  confirmed limitation `EP054_DESIGN.md` Section 3.7 already
  documented for `Tool.handler`'s zero-argument-only signature).
- `src/core/ai/provider.py`, `src/core/ai/provider_manager.py`,
  `src/core/ai/provider_registry.py`, `src/core/ai/conversation.py`,
  `src/core/ai/conversation_manager.py` — zero changes; used strictly
  through their existing, unmodified public APIs.
- `src/services/ai_service.py` — zero changes; `PromptOptimizerModule`
  never routes through `AIService.ask()` (Section 6.4), exactly as
  `ReflectionModule` does not.
- `src/skills/reflection/`, `src/skills/desktop/`, `src/skills/
  browser/`, `src/skills/files/`, `src/skills/vision/` — zero changes;
  no relationship to Prompt Optimizer in any candidate considered.
- `src/core/agent/`, `src/core/planning/`, `src/core/scheduler/`,
  `src/core/memory/` — zero changes; no candidate considered here
  proposes using any of them.
- Every EP-001…EP-054 design/audit document and every other prior
  EP's source/test files, and `JARVIS_ROADMAP.md`/`BACKLOG.md`/
  `CHANGELOG.md` (STEP 1 does not update documentation per this task's
  own instruction).

---

## 15. Compatibility considerations

Fully additive under Candidate A — no existing manager's method
signature, return type, or behavior changes; no existing config key's
meaning or default changes; no existing `CommandModule` is affected;
`prompts/` directory's existing (currently empty) contents are
unaffected unless `prompt save` (Owner Decision D4) is both authorized
and explicitly invoked by the user.

---

## 16. Implementation constraints

Bound by `AI_GENERATION_STANDARD.md` exactly as every prior EP was: no
architecture redesign, no invented API on `AIProvider`/`ProviderManager`
(Section 3.5's "Unknown API Policy"), one class one responsibility,
300-line-recommended/500-line-hard file-size limit, type hints,
docstrings, no hardcoded credentials/paths.

---

## 17. Resource/operational limits

`prompt_optimizer.max_input_size` and `prompt_optimizer.
min_seconds_between_calls` (Section 7/8) are the only two operational
limits Candidate A introduces — both new, independent config keys with
no interaction with any other EP's own limits (e.g. `reflection.
max_message_count`, `vision.max_dimension`, `prompt.max_prompt_size`
itself, which Candidate A never reads or enforces, since it never
constructs a `Prompt` object at all).

---

## 18. Acceptance criteria (for STEP 1)

- [x] Every roadmap/backlog/engineering-guide/prior-EP-docstring
  reference to EP-055/"Prompt Optimizer" was found and quoted verbatim
  (Section 2) — not summarized from memory.
- [x] The genuine absence of a functional specification is reported
  explicitly, not silently filled (Section 0/2).
- [x] The existing EP-017 Prompt Engine and related architecture
  (EP-018 Context Engine, `AIService`, `AIProvider`) were inspected in
  depth specifically to ground candidate interpretations in what
  already exists, not outside knowledge (Section 3).
- [x] At least the minimum necessary Owner Decision to proceed (D1, a
  definitional choice among repository-grounded candidates) is
  presented, with three further candidates explicitly considered and
  either recommended, deferred, or rejected with reasoning (Section
  5).
- [x] A complete, provisional architecture is presented for the
  *recommended* candidate only, explicitly marked contingent on D1's
  approval (Sections 6-17), and explicitly does not modify the
  existing Prompt Engine (Section 14's DO NOT MODIFY list).
- [x] File scope is narrow, explicit, and auditable — no directory-
  level authorization (Section 14).
- [x] No source, test, configuration, dependency, or Bootstrap file
  was created or modified.
- [x] STEP 2 has not begun.

---

## 19. Unresolved questions this document does not answer

Recorded explicitly, per the task's instruction not to silently guess:

- Whether the owner even agrees "Prompt Optimizer" should mean
  Candidate A at all — this is precisely Owner Decision D1, and this
  document's entire Sections 6-17 are void if the answer is anything
  else.
- Whether "provider optimization" (`JARVIS_ARCHITECTURE_VISION.md`,
  Section 3.6) was ever intended to mean *per-provider*-specific
  prompt rewriting (Candidate D) rather than the provider-agnostic
  template improvement this document recommends (Candidate A) — no
  repository evidence resolves this either way; Section 3.5 already
  confirmed no per-provider capability data model exists today to
  build Candidate D against even if the owner wants it.
- Whether a future EP-056/057/058 will expect Prompt Optimizer's
  output (an improved template, or Candidate C's effectiveness
  report) in a specific, machine-readable format — no such
  requirement exists anywhere in the repository today, so this
  document assumes free-text/plain-`.txt`-template output is
  sufficient for v1, flagged as revisitable.
- Whether real, live-provider end-to-end testing is wanted at all
  (Section 12's last bullet) — recorded as an open question rather
  than decided either way, mirroring `EP054_DESIGN.md`'s own Owner
  Decision D9.
- Whether `prompt` is the right `CommandRouter` namespace name given
  its proximity to the (non-command-facing) "Prompt Engine" concept,
  or whether a more distinct name (e.g. `promptopt`, `optimize`) would
  reduce operator confusion — recorded as part of Owner Decision D2.

---

## 20. Owner Decisions

**All nine decisions below (D1-D9) are APPROVED, exactly as
recommended, with no modification.** The "Recommended option" in each
decision below is therefore also the **approved option**. Sections
6-17's provisional architecture is confirmed as the approved
architecture for EP-055 v1's STEP 2.

### D1 — What does "Prompt Optimizer" concretely mean for v1? (primary, definitional decision)

**Question:** Which of Section 5's candidate interpretations (or an
owner-supplied alternative not considered here) should EP-055 v1
actually build?
**Options:** (a) Candidate A — on-demand template/prompt-text
improvement via a direct AI-provider call, optionally saved back as a
new template (recommended); (b) Candidate B — automatic, inline
optimization inside `PromptBuilder`/`PromptManager`'s existing
pipeline for every request (not recommended — see Section 5's
"hidden coupling" risk); (c) Candidate C — effectiveness tracking/
reporting only, no rewriting (viable fallback if the owner rejects (a)
outright); (d) Candidate D — per-provider-specific prompt-formatting
rewriting (not recommended — requires a new, undesigned per-provider
capability data model, Section 3.5); (e) an owner-supplied
alternative, in which case this entire document would need to be
revised before STEP 2.
**Recommended option:** (a).
**Technical reasoning:** (a) is the only candidate that requires zero
change to the existing, already-tested EP-017 Prompt Engine files
(Section 14), composes exactly one already-existing, unmodified
component (`AIProvider`, via the same direct-call pattern EP-054
already established and tested), and finally exercises Section 3.2's
already-built-but-idle template-loading seam.
**Security impact:** (a) introduces exactly two new gates
(`prompt_optimizer.enabled`, and — if D4 authorizes saving —
`prompt_optimizer.allow_save`) and reuses `AIProvider`'s
already-reviewed call path; (b) risks silently altering every
outgoing prompt with no per-request visibility; (c) has the smallest
security surface of all (no AI-provider call at all, if built as pure
reporting); (d) is unscoped until a per-provider data model exists.
**Compatibility impact:** (a)/(c) are fully additive; (b) risks
interacting with EP-018.5's sizing/budget guarantees inside
`PromptBuilder` itself; (d) is undefined until scoped.
**What changes in STEP 2:** (a) → build exactly Section 14's file
scope. (b) → this document would need a full revision specifically
designing where inside `PromptBuilder`'s pipeline the automatic step
lives and how determinism-by-default is preserved. (c) → Section
6/14 narrow considerably: no `AIProvider` dependency, `Prompt.metadata`
population plus a `prompt stats` read-only action replaces `prompt
optimize`/`prompt save`. (d) → this document would need a full
revision adding a per-provider capability/preference data model design
before STEP 2 could begin.

### D2 — Command namespace and action names

**Question:** Should the new `CommandModule` claim the `prompt`
namespace (Section 6.1, as currently proposed), or a more
distinct name to avoid confusion with the (non-command-facing)
"Prompt Engine" (`prompt.*` config keys, `PromptManager`, etc.)?
**Options:** (a) `prompt` (as proposed, e.g. `prompt optimize ...`);
(b) a more distinct name, e.g. `promptopt` or `optimize`.
**Recommended option:** (a) — no existing `CommandRouter` namespace
collision was found (Section 6.1), and `prompt` most directly
communicates the feature's purpose to a user typing a command,
matching how `reflect`/`vision`/`browser`/`file`/`desktop` are each
named for what they do rather than for their internal architecture
layer.
**Security impact:** none either way.
**Compatibility impact:** none either way — this is a purely cosmetic
choice with no effect on any existing `prompt.*` config key or
`PromptManager`/`PromptBuilder` code.
**What changes in STEP 2:** whichever name is approved is used
verbatim for the `CommandModule.name` property and every action in
Section 6.3's table.

### D3 — Separate AI-provider/privacy gate for `prompt optimize`, or reuse `prompt_optimizer.enabled` alone?

**Question:** Should sending prompt/template text to the configured
AI provider for optimization require a second, independent config
flag, or is the single `prompt_optimizer.enabled` flag sufficient?
**Options:** (a) `prompt_optimizer.enabled` alone (as proposed,
Section 7); (b) a second, independent
`prompt_optimizer.ai_rewrite.enabled` flag.
**Recommended option:** (a) — mirrors `EP054_DESIGN.md`'s own Owner
Decision D2 reasoning for `reflection.enabled`: sending prompt/
template text (not conversation content) to the already-configured AI
provider is not new data-exfiltration surface in the way EP-053's
`vision describe` would have been the first time image bytes left the
machine. The owner may reasonably disagree; recorded explicitly so it
can be overridden.
**Security impact:** (a) is a single point of control; (b) gives
finer-grained control at the cost of one more flag to configure
correctly.
**Compatibility impact:** none either way — new, independent config
key(s) regardless.
**What changes in STEP 2:** (a) → Section 8's config block as shown.
(b) → an additional `prompt_optimizer.ai_rewrite.enabled` key, checked
alongside `prompt_optimizer.enabled` in `PromptOptimizerModule`'s
gate.

### D4 — Allow `prompt save` (writing an optimized result back to `paths.prompts`), or return-only in v1?

**Question:** Should EP-055 v1 include a `prompt save` action that
writes an optimized result to disk as a new/updated template file
(Section 6.3), or should `prompt optimize` be strictly return-only in
v1 (the caller must save it manually via their own file tools)?
**Options:** (a) include `prompt save`, gated by a second, independent
`prompt_optimizer.allow_save` flag (default `false`), Section 7; (b)
return-only — no filesystem write capability at all in v1.
**Recommended option:** (b) for the smallest possible v1 surface, with
(a) recorded as the natural, low-risk fast-follow that gives Section
3.2's idle `load_template()`/`template=` seam an actual reason to be
used going forward. The owner may prefer (a) immediately, in which
case Section 7's `allow_save` gate as already designed applies
directly.
**Security impact:** (b) has zero new filesystem-write surface; (a)
introduces exactly one new, narrowly-scoped write path (`paths.
prompts` only, never an arbitrary path), gated independently of
`prompt_optimizer.enabled` itself, mirroring `vision.allowed_roots`'s
"the master gate alone is not enough" precedent.
**Compatibility impact:** neither changes `PromptBuilder.
load_template()` itself; (a) only ever adds files under `paths.
prompts`, never modifies an existing one without an explicit,
separate confirmation this document has not yet designed (recorded as
a further, later decision if (a) is chosen: overwrite vs. refuse vs.
prompt-for-confirmation).
**What changes in STEP 2:** (a) → `prompt save` (Section 6.3) is
built, `prompt_optimizer.allow_save` is added to Section 8's config
block. (b) → `prompt save` is dropped from Section 6.3's action
table entirely, and `prompt_optimizer.allow_save` is dropped from
Section 8.

### D5 — Register as an Agent Framework subsystem, in addition to being a `CommandModule`?

**Question:** Should `PromptOptimizerModule` also register itself
with `AgentEngine.register_subsystem()`, so `agent status`/
`list_subsystems()` reports on it, or should it remain purely a
`CommandModule` like `desktop`/`browser`/`file`/`vision`/`reflect`
(none of which register as Agent subsystems today)?
**Options:** (a) `CommandModule` only, no Agent subsystem registration
(matching Phase 7/8/EP-054 precedent exactly, as proposed); (b) both.
**Recommended option:** (a) — identical reasoning to `EP054_DESIGN.md`
Section 20's own Owner Decision D6: the subsystem registry is used
exclusively by Phase 3-6 components today, and extending it here
without an already-established, concrete need would be a speculative
addition.
**Security impact:** none either way — `register_subsystem()` is
read-only status reporting.
**Compatibility impact:** (a) touches nothing in `src/core/agent/`;
(b) requires one additive call in `src/bootstrap.py`'s existing Agent
Framework wiring block (Section 14 currently lists `src/core/agent/`
as DO NOT MODIFY — approving (b) would need to narrow that to "no
behavioral change, one additive registration call in `bootstrap.py`
only").
**What changes in STEP 2:** (a) → no change to Section 14's DO NOT
MODIFY list. (b) → `src/bootstrap.py`'s existing Agent Framework
`available_subsystems` list gains one new tuple.

### D6 — Exact values for `max_input_size`/`min_seconds_between_calls`

**Question:** What should the default resource/rate limits be?
**Options:** the values shown in Section 8 (`max_input_size: 4000`,
`min_seconds_between_calls: 30`) are this document's own reasonable
starting proposal — `max_input_size` chosen as a smaller figure than
`reflection.max_message_count`'s implied character volume, since a
single prompt/template is typically far shorter than 20 full
conversation messages; `min_seconds_between_calls` copied directly
from `reflection`'s own precedent (Section 8, `EP054_DESIGN.md`), as
no comparable existing convention suggests a different value is
warranted for a structurally similar single-AI-provider-call action.
**Recommended option:** accept the proposed defaults, or specify
different ones.
**Security impact:** lower values reduce AI-provider cost/exposure
per call; higher values allow richer optimization input at higher
cost.
**Compatibility impact:** none — new, independent config keys.
**What changes in STEP 2:** whichever values are approved are used
verbatim in `config/config.yaml` and enforced in
`PromptOptimizerModule`.

### D7 — `CommandRouter` vs. Tool Engine

**Question:** Restated per this project's own established practice
(Section 3.9) of never assuming a prior EP's answer still holds:
should `PromptOptimizerModule` dispatch through `CommandRouter` (as
this document proposes) or attempt to use/extend Tool Engine?
**Options:** (a) `CommandRouter`, matching EP-050…EP-054 exactly; (b)
extend Tool Engine to support parameterized handlers first.
**Recommended option:** (a) — restated from Section 3.9; this is now
the sixth independent EP to reach the same conclusion for the same
reason (`Tool.handler`'s zero-argument-only signature).
**Security impact:** none either way.
**Compatibility impact:** (a) requires no `src/core/tool/` change; (b)
would be a cross-cutting change this EP is not authorized to make
unilaterally.
**What changes in STEP 2:** (a) → `PromptOptimizerModule` registers
with `CommandRouter` exactly like every prior skill. (b) → not planned
by this document at all.

### D8 — Real-`AIProvider` end-to-end testing (Section 12, Section 19)

**Question:** Should EP-055 include a separate, unregistered,
real-provider integration script (mirroring EP-053's real-Tesseract
script and EP-054's own considered-and-declined equivalent), given it
would require live, costed API credentials and would assert against
non-deterministic model output rather than an exact, fixed string?
**Options:** (a) no real-provider integration script — the primary
suite's fake-`AIProvider` tests are the only coverage (matching
EP-054's own Owner Decision D9 outcome); (b) build one anyway,
asserting only loose properties (non-empty response, no exception)
rather than exact content.
**Recommended option:** (a) — identical reasoning to `EP054_DESIGN.md`
Section 20's Owner Decision D9: a real `AIProvider.ask()` call's
output is not deterministic, so a real-provider test would mostly
confirm network/credential plumbing rather than genuine
optimization-quality behavior.
**Security impact:** none either way.
**Compatibility impact:** none either way.
**What changes in STEP 2:** (a) → `tests/EP055/` contains only the
primary, fake-backed suite (Section 12). (b) → an additional,
unregistered `tests/EP055/test_prompt_optimizer_ai_integration.py`
following EP-053/EP-054's own established convention.

### D9 — Should this document also flag/request remediation of the pre-existing EP-014…EP-017 test-registration gap (Section 3.8/19 observation)?

**Question:** Section 3.8 and this document's own repository
inspection (mirroring Section 3 of `EP054_DESIGN.md`) found that
`src/modules/test_module.py` registers no dedicated `tests/EP0xx/`
suite for EP-014 (AI Provider Manager), EP-015 (Claude Provider),
EP-016 (Conversation Engine), or EP-017 (Prompt Engine) itself —
inconsistent with the convention established from EP-018 onward
(`tests/EP018/`, `tests/EP019/`, ..., `tests/EP054/` all exist and are
registered). This is a **pre-existing observation about prior EPs**,
not a defect introduced by this document or by EP-055's own proposed
work — it is recorded here, as `AI_DEVELOPMENT_PLAYBOOK.md`'s
Architecture Debt Workflow requires, rather than silently noticed and
dropped.
**Options:** (a) record only, take no action — EP-055 STEP 2 (if
approved) adds only `tests/EP055/`, exactly as scoped in Section 14,
and this observation is left for the owner to act on separately
(e.g. via `docs/architecture/ARCHITECTURE_DEBT.md`, per the
Playbook's own workflow) or to explicitly fold into a future EP; (b)
expand EP-055's own scope to also backfill EP-014…EP-017 test
registration.
**Recommended option:** (a) — `AI_DEVELOPMENT_PLAYBOOK.md`'s own
"General Rules" ("Do not modify unrelated code... Do not optimize
previous EPs unless explicitly requested") argue directly against
folding an unrelated, prior-EP test-debt backfill into EP-055's scope.
**Security impact:** none either way.
**Compatibility impact:** (a) leaves the current, already-existing gap
unchanged; (b) would touch EP-014…EP-017 test files, outside this
document's DO NOT MODIFY list (Section 14) as currently scoped.
**What changes in STEP 2:** (a) → no change; this remains a
recorded observation only. (b) → this document's Section 14 file-scope
matrix would need to be revised to add EP-014…EP-017 backfill test
files, a materially different and larger STEP 2 than Sections 6-17
currently describe.

---

## Owner Approval Checklist

**Owner-approved on the date this section was updated, exactly as
recommended, with no modification to any option below.**

- [x] **D1** — What does "Prompt Optimizer" concretely mean for v1?
  **APPROVED: Candidate A** — on-demand prompt/template improvement
  via one direct `AIProvider.ask()` call.
- [x] **D2** — Command namespace name. **APPROVED: `prompt`.**
- [x] **D3** — Separate AI-provider/privacy gate, or reuse
  `prompt_optimizer.enabled` alone? **APPROVED: reuse
  `prompt_optimizer.enabled` alone; no separate privacy gate in v1.**
- [x] **D4** — Include `prompt save` (filesystem write) in v1?
  **APPROVED: no — return-only behavior in v1.** `prompt save` and
  `prompt_optimizer.allow_save` are dropped from Section 6.3/8's
  implementation scope (retained in the sections above only as the
  documented, not-built, possible fast-follow).
- [x] **D5** — Register as an Agent Framework subsystem? **APPROVED:
  no — `CommandModule` only, no `AgentEngine.register_subsystem()`
  call.**
- [x] **D6** — Exact resource/rate-limit default values. **APPROVED:
  `max_input_size: 4000`, `min_seconds_between_calls: 30`, used
  verbatim.**
- [x] **D7** — `CommandRouter` vs. Tool Engine. **APPROVED:
  `CommandRouter`, matching EP-050…EP-054 exactly.**
- [x] **D8** — Real-`AIProvider` end-to-end testing in v1? **APPROVED:
  no — `tests/EP055/` contains only the primary, fake-`AIProvider`-
  backed suite.**
- [x] **D9** — Act on the pre-existing EP-014…EP-017 test-registration
  gap as part of EP-055? **APPROVED: no — record only, out of
  EP-055's scope; EP-055 STEP 2 adds only `tests/EP055/`.**

**Consequence of D4's approval for Section 6.3/8:** the `prompt save`
row is not implemented in STEP 2; `PromptOptimizerModule` in v1
exposes exactly `prompt help` and `prompt optimize <text>`, and
`config/config.yaml`'s `prompt_optimizer:` block in STEP 2 does not
include `allow_save` (it is not needed since the gated action it
would guard is not built).

**D10 (raised during STEP 3, not present in the original STEP 1
scope) — APPROVED, option (a).** The STEP 3 architecture audit
(`docs/architecture/audits/EP055_ARCHITECTURE_AUDIT.md` Section 17)
identified two non-blocking findings (a `--template`
filesystem-read/existence-disclosure ordering issue, and a
`max_input_size` value-leak ordering issue, both relative to the
`prompt_optimizer.enabled` gate) and proposed Owner Decision D10: fix
both in STEP 4 via a minimal, behavior-preserving reordering. The
owner approved option (a). The fix, independent verification that
both findings are genuinely resolved (not merely covered by new
tests), and the final resolved status are recorded in
`EP055_ARCHITECTURE_AUDIT.md` Section 18. This does not alter D1-D9
or any part of Candidate A's approved scope (Sections 6-17 above) —
it is an internal ordering correction within the already-approved
`PromptOptimizerModule`.
