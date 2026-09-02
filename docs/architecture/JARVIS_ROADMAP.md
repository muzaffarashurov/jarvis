# Jarvis Development Roadmap

Version: 2.0

Status: Active Development

---

# Vision

Jarvis is not a chatbot.

Jarvis is not a single Large Language Model.

Jarvis is an AI Operating System.

Its purpose is to orchestrate AI providers, project knowledge, memory, workflows, tools and autonomous agents through a unified architecture.

Every Engineering Package (EP) contributes one reusable architectural building block.

---

# Engineering Principles

Every EP must:

- extend the existing architecture
- preserve backward compatibility
- follow PROJECT_MANIFEST.md
- follow AI_GENERATION_STANDARD.md
- remain provider independent
- avoid duplicated functionality
- reuse existing infrastructure
- include automated tests
- deliver production-quality code

Large EPs may be implemented incrementally using sub-packages:

- EP-018.1
- EP-018.2
- EP-018.3
- ...

Sub-packages never replace the main EP number.

---

# Current Progress

## Completed

EP-001 Core Foundation

EP-002 Interactive Shell

EP-003 Process Manager

EP-004 Quality & Testing Framework

EP-005 Invoice Automation

EP-006 Fast Response Board

EP-007 Core Improvements

EP-008 Process Aliases

EP-009 Process Catalog

EP-010 Configuration Improvements

EP-011 Logging Improvements

EP-012 Core Refactoring

EP-013 AI Infrastructure Preparation

EP-014 AI Provider Manager

EP-015 AI Provider Integration

EP-016 Conversation Engine

EP-017 Prompt Engine

EP-018 Universal Context Engine

Completed sub-packages:

- EP-018.1 Context Engine Foundation
- EP-018.2 PROJECT_MANIFEST Integration
- EP-018.3 Repository Detection
- EP-018.4 Document Budget
- EP-018.5 Unified Prompt Budget
- EP-018.6 Conversation Budget
- EP-019 Project Index Engine
- EP-020 Retrieval Engine
- EP-021 Embedding Engine
- EP-022 RAG Engine
- EP-023 Memory Manager
- EP-024 Knowledge Base
- EP-025 Long-Term Memory
- EP-026 Semantic Search
- EP-027 Context Compression
- EP-028 Agent Framework
- EP-029 Planning Engine
- EP-030 Execution Engine
- EP-031 Tool Engine
- EP-032 Multi-Agent Collaboration
- EP-033 Workflow Engine
- EP-034 Scheduler
- EP-035 Automation Engine
- EP-036 Background Workers
- EP-037 Event Bus
- EP-038 Git Integration
- EP-039 GitHub Integration
- EP-040 Telegram Integration
- EP-041 Discord Integration
- EP-042 Email Integration

---

## Current

EP-058 Autonomous Planning — **COMPLETE** (STEP 1 Architecture
Discovery & Design, STEP 2 Implementation & Testing, STEP 3
Architecture Audit, STEP 4 Finalization all complete -- see
docs/architecture/designs/EP058_DESIGN.md (including its Owner
Decisions D1-D3 and the Owner Approval Checklist added during STEP 4)
and docs/architecture/audits/EP058_ARCHITECTURE_AUDIT.md. **Final
Verdict: STEP 3 — AUDIT PASSED, NO BLOCKING FINDINGS** (two
non-blocking, informational findings; STEP 4 corrected one via a
documentation-only edit and acknowledged the other with no action, as
originally recommended -- see below). Like EP-054/EP-055/EP-056/
EP-057, EP-058's roadmap entry was a bare title with no functional
specification -- but STEP 1 found an unusually strong anchor for a
Phase-9 EP: an entire, already-complete ten-Engineering-Package chain
(Phase 4 "Agent Framework", EP-028-032, and Phase 5 "Workflow
Automation", EP-033-037) whose every package explicitly, repeatedly
declares in its own docstring that it performs no AI reasoning and
defers that to a named-but-unbuilt future concept.
`DefaultAgentProvider.execute()` (EP-028) returns, on every real call,
the literal runtime message "No Planner/Reasoning Engine is
registered yet (future EP)"; `PlanningProvider`'s own module
docstring (EP-029) explicitly names "a future AI-/LLM-backed planning
strategy... an obvious, natural extension point for this
abstraction" as the reason it implements only one, deterministic
provider. STEP 1 recommended Owner Decision D1 = "Candidate A": a
new, additive `AIPlanningProvider` implementation of the existing
`PlanningProvider` abstraction (EP-029), registered alongside --
never replacing -- the deterministic `DefaultPlanningProvider`,
selectable via the already-existing `planning use ai` action. Owner
Decision D2: no additional cost/latency safeguard beyond that
existing action's own plain result. Owner Decision D3: no new
`max_tokens` configuration value -- rely on the active AI provider's
own existing default. Built as one new file,
`src/core/planning/ai_planning_provider.py`, containing exactly one
new class, `AIPlanningProvider`, which reasons about a request's
meaning using an AI provider (EP-014/015, reached only through
`ProviderManager.get_current()` -> `AIProvider.ask()` directly, the
same deliberate bypass of `AIService`'s Conversation/Context/Prompt
Engine pipeline `PromptOptimizerModule`, EP-055, already established)
but chooses only from the exact same, already-real `(subsystem,
action)` vocabulary `DefaultPlanningProvider`'s own `_KEYWORD_RULES`
table already recognizes -- derived programmatically at import time,
never hardcoded, so the two providers remain genuine, interchangeable
substitutes over the identical action space. Registered via
`PlanningManager`'s already-existing, generic `register_provider()`
method (EP-029, unmodified) at the existing Planning construction
site in `src/bootstrap.py` -- one new import, one new comment block,
and one new line inside the pre-existing `try`/`except PlanningError`
block, with that block's original structure, including its
graceful-degradation-on-bad-config behavior, fully preserved.
`planning.default_provider` remains `"planning"` -- `AIPlanningProvider`
never becomes the default; an operator must explicitly run `planning
use ai` (or set `planning.default_provider: "ai"`) to select it. Like
every recommended Candidate A across EP-054/055/056/057, EP-058
introduces no new backend Protocol, Manager, or Engine -- it composes
two already-existing, unmodified components directly, read-only:
`ProviderManager.get_current()`/`AIProvider.ask()` (EP-014/015) and
`PlanningProvider`'s own already-existing abstract contract (EP-029).
Zero new CLI action was needed -- `planning use`/`providers`/`plan`
already work generically for any registered provider, the smallest
command-surface footprint of any Phase-9 EP's own recommended
Candidate A so far. Required zero change to
`PlanningManager`/`PlanningEngine`/`PlanningProvider`/`PlanStep`/
`Plan` (EP-029), `AgentEngine`/`AgentProvider` (EP-028),
`PlanExecutionEngine` (EP-030), `ToolEngine` (EP-031),
`CollaborationEngine` (EP-032), any Phase 5 package (EP-033-037), or
`config/config.yaml`. Owner Decisions D1-D3 are all confirmed
correctly implemented with zero findings against their literal text.
Tests: EP-058 110/0/0, covering the reply-parsing helpers directly
(well-formed, messy/bulleted/numbered formatting, off-menu-pair
rejection per this project's Unknown API Policy applied to AI output,
deduplication, empty-reply fallback, `max_steps` truncation), the
provider in isolation against a real `ProviderManager` with a fake
AI backend (faking only the one genuine external network dependency
this EP introduces, never an in-repo component), `PlanningManager`
compliance (registration, duplicate-name rejection, listing),
non-interference with the deterministic provider, five real, enabled
`Bootstrap` -> `CommandRouter` -> `PlanningService` -> `PlanningEngine`
-> `PlanningManager` -> `AIPlanningProvider` -> `ProviderManager`
end-to-end tests (including the real no-AI-provider-configured
failure path and a real fake-backend success path, injected into the
already-registered provider's own real, shared `ProviderManager` --
never a second, duplicate registration), and architecture-compliance
import scans. Full regression: EP-028 214/0/0, EP-029 197/0/0, EP-030
179/0/0, EP-031 212/0/0, EP-032 176/0/0, EP-033 182/0/0, EP-034
113/0/0, EP-035 143/0/0, EP-036 101/0/0, EP-055 64/0/0, EP-056
62/0/0, EP-057 41/0/0 -- all independently reproduced exactly, both
before and after the STEP 4 documentation-only edit, confirming
EP-029's own deterministic-provider logic was never modified. **STEP
3 findings (identified, then both dispositioned during STEP 4 -- zero
findings were security-, disclosure-, or blocking-related):** (1,
LOW, informational) `EP058_DESIGN.md`'s own prose described
`DefaultPlanningProvider`'s keyword table as having "nine" entries;
the audit independently confirmed the actual count is seventeen
keyword rules, collapsing to eight unique `(subsystem, action)` pairs
after deduplication -- a prose miscount with zero effect on the
implementation, which derives its menu programmatically rather than
from any hardcoded count; corrected via a targeted, four-passage
documentation-only edit to `EP058_DESIGN.md`, with zero code, test,
or configuration change. (2, LOW, informational) a mutation causing
an unhandled exception partway through the EP-058 test suite's own
`run()` method prevents subsequent test methods from executing -- a
characteristic shared by every EP's own pre-existing
`BaseTest`/`TestRunner` convention, not specific to EP-058; explicitly
acknowledged with no action taken, since fixing it would require a
separate, cross-cutting change to shared testing infrastructure
outside any single EP's scope. Separately, and unrelated to either
finding, the audit's own independent examination of EP-029's
unmodified `planning_provider.py` noted a pre-existing textual
tension between that file's module- and class-level docstrings
regarding AI-backed providers -- predating EP-058 entirely, requiring
no action, and recorded purely for completeness.
`src/core/planning/planning_provider.py`, `planning_manager.py`,
`planning_engine.py`, `planning_result.py` (EP-029),
`src/core/agent/`, `src/services/agent_service.py`,
`src/modules/agent_module.py` (EP-028), `src/core/plan_execution/`,
`src/services/plan_execution_service.py`,
`src/modules/plan_execution_module.py` (EP-030), `src/core/tool/`,
`src/services/tool_service.py`, `src/modules/tool_module.py`
(EP-031), `src/core/collaboration/` (EP-032),
`src/core/workflow_engine/`, `src/core/workflow_scheduler/`,
`src/core/automation_engine/`, `src/core/background_workers/`
(EP-033-036), `src/core/ai/provider_manager.py`, `provider.py`,
`conversation.py`, `conversation_manager.py`, `context_manager.py`,
`prompt.py`, `prompt_builder.py`, `prompt_manager.py`,
`src/services/ai_service.py` (EP-014/015/016/017/018),
`src/core/memory/`, `src/core/long_term_memory/`,
`src/core/knowledge/`, `src/core/semantic/`,
`src/core/context_compression/` (EP-023-027),
`src/core/command_router.py`, `config/config.yaml`,
`src/services/planning_service.py`, and `src/modules/planning_module.py`
are all confirmed byte-identical/unmodified by EP-058, both before
and after the STEP 4 documentation-only edit.

**Next Engineering Package: EP-059 Distributed Runtime — NOT
STARTED.** No EP-059 design, research, or implementation work has
begun.

EP-057 Memory Optimization — **COMPLETE** (STEP 1 Architecture
Discovery & Design, STEP 2 Implementation & Testing, STEP 3
Architecture Audit, STEP 4 Finalization all complete -- see
docs/architecture/designs/EP057_DESIGN.md (including its Section 20
owner-decision record, D1-D4, and the Owner Approval Checklist added
during STEP 4) and docs/architecture/audits/EP057_ARCHITECTURE_AUDIT.md.
**Final Verdict: STEP 3 — PASS AFTER REMEDIATION** (first pass: AUDIT
PASSED WITH FINDINGS -- three non-blocking findings, zero blocking;
the owner directed all three be closed during STEP 4, and they are
now resolved and independently verified -- see below). Like
EP-054/EP-055/EP-056, EP-057's roadmap entry was a bare title with no
functional specification -- STEP 1 found the strongest anchor of any
Phase-9 EP so far: `CompressionEngine.compress_query()`/
`compress_semantic_results()` (EP-027), already fully built and
already fully tested, had exactly zero production callers anywhere in
the repository, and `src/bootstrap.py`'s own construction-site
comment already named this exact situation, stating Semantic Search
was reached there "only ... used only by `compression`'s future
callers via `compress_query()`, never by the CLI commands wired
here" -- and recommended Owner Decision D1 = "Candidate A": expose
that already-built, already-tested method as a new, on-demand
`compression query "<text>"` command, finally giving it a real
caller. Owner Decision D2: no `top_k`/`threshold` CLI arguments --
rely on the existing `semantic.*` configuration defaults. Owner
Decision D3: no additional information-disclosure gate beyond the
already-existing `context_compression.enabled` flag. Owner Decision
D4: extend the existing `compression` `CommandModule` namespace
rather than create a new one or extend `ltm`. Built as one new
`query()` method on `CompressionService` (a one-line forward to
`CompressionEngine.compress_query()`, introducing no new compression
or semantic-search logic of its own) and one new `query` action on
`ContextCompressionModule`, dispatched through the *existing*,
unmodified `CommandRouter.dispatch()`, exactly as every prior skill
already is: no second dispatch mechanism, no change to Tool Engine.
Like EP-054/EP-055/EP-056, EP-057 introduces no new backend Protocol,
Manager, Engine, or Provider (Owner Decision D1) -- `compression
query` instead composes already-existing, unmodified components
directly, read-only: `CompressionEngine.compress_query()` (EP-027),
which itself reaches `SemanticEngine.search()` (EP-026) over
Knowledge Base (EP-024) and Long-Term Memory (EP-025) content. The
EP-016 Conversation Engine, EP-018 Context Loader, EP-024 Knowledge
Base, EP-025 Long-Term Memory, EP-026 Semantic Search, and EP-027
Context Compression's own core logic are never modified or
redesigned; `CompressionEngine`/`SemanticEngine` are called only
through their existing, unmodified public API. No separate AI-provider
privacy gate exists, since `compression query` never calls an AI
provider (Owner Decision D3) and, independently confirmed during the
architecture audit, discloses strictly less than the already-existing
`semantic search` command already discloses today. No `AgentEngine`
subsystem registration exists in v1. No new dependency was
introduced. Required zero `src/bootstrap.py` construction-ordering or
wiring change and zero new configuration key, since `CompressionEngine`
was already constructed with a live `SemanticEngine` wherever Semantic
Search is available. Owner Decisions D1-D4 are all confirmed
correctly implemented with zero findings against their literal text.
Tests: EP-057 41/0/0 (35 original plus 6 added during STEP 4
specifically to close a test-coverage gap around the
`context_compression.enabled: false` gate -- see STEP 3 findings
below), covering argument-shape/gate/dispatch behavior, a real,
unmodified `SemanticEngine`/`KnowledgeService` integration (not a
fake) for the one genuine cross-subsystem call this EP makes, and
three real, enabled `Bootstrap` -> `CommandRouter` ->
`CompressionService` -> `CompressionEngine` -> `SemanticEngine` ->
`KnowledgeService` end-to-end tests. Full regression: EP-056 62/0/0,
EP-055 64/0/0, EP-054 76/0/0, EP-053 58/0/0, EP-052 135/0/0, EP-051
105/0/0, EP-050 112/0/0, plus EP-024 Knowledge Base 407/0/0, EP-025
Long-Term Memory 442/0/0, EP-026 Semantic Search 204/0/0, and EP-027
Context Compression 229/0/0 -- all independently reproduced exactly,
both before and after the STEP 4 fixes, confirming EP-027's own
compression logic was never modified. **STEP 3 findings (identified,
then all three fixed and verified during STEP 4 -- zero findings were
security- or disclosure-related, and none was blocking):** (1, LOW,
informational) `src/bootstrap.py`'s own construction-site comment
became factually stale the moment EP-057 gave `compress_query()` a
real CLI caller, since the comment still said no such caller existed;
fixed by a comment-only, two-line edit, independently confirmed to
touch zero executable statements. (2, LOW) the registered test suite
defined a `context_compression.enabled: false` configuration fixture
but never actually used it, and a test named for that scenario
instead tested a different code path ("no `SemanticEngine`
configured"), because `compress_query()` checks for a `None`
`SemanticEngine` before ever reaching the `enabled`/provider-selection
check; fixed by renaming the misleadingly-named test and adding a new
test that exercises the actual `context_compression.enabled: false`
gate together with a real `SemanticEngine`, independently confirmed
via a dedicated mutation test to genuinely detect a simulated gate
bypass that would have passed through the original suite entirely
undetected. (3, informational) `EP057_DESIGN.md`, approved during
STEP 1, had been delivered to the owner but never committed into the
repository tree, unlike EP-054/EP-055/EP-056's own design documents;
fixed by committing it to
`docs/architecture/designs/EP057_DESIGN.md`. Separately, and
unrelated to any of the above, two pre-existing EP-048 (Wake Word)
test failures were independently investigated and conclusively proven
pre-existing and environment-only (the `openwakeword` package is not
installable in the audit environment) by reproducing the identical
failure against a separate, pristine copy of the repository
containing zero EP-057 code -- see
`docs/architecture/audits/EP057_ARCHITECTURE_AUDIT.md` Section 15.
`src/core/context_compression/compression_engine.py`,
`compression_manager.py`, `compression_provider.py`,
`compression_result.py` (EP-027 Context Compression),
`src/core/semantic/semantic_engine.py`,
`src/services/semantic_service.py`, `src/modules/semantic_module.py`
(EP-026 Semantic Search), `src/core/long_term_memory/`,
`src/services/long_term_memory_service.py`,
`src/modules/long_term_memory_module.py` (EP-025 Long-Term Memory),
`src/core/knowledge/`, `src/services/knowledge_service.py` (EP-024
Knowledge Base), `src/core/memory/`, `src/services/memory_service.py`,
`src/modules/memory_module.py` (EP-013/023 Memory & Context Manager),
`src/core/ai/conversation.py`, `conversation_manager.py`,
`context_manager.py`, `src/services/ai_service.py`,
`src/core/command_router.py`, and `config/config.yaml` are all
confirmed byte-identical/unmodified by EP-057, both before and after
the STEP 4 fixes; `src/bootstrap.py`'s only change across all of
EP-057 is the single, comment-only edit described above.

EP-056 Capability Registry — **COMPLETE** (STEP 1 Architecture
Discovery & Design, STEP 2 Implementation & Testing, STEP 3
Architecture Audit, STEP 4 Finalization all complete -- see
docs/architecture/designs/EP056_DESIGN.md (including its Section 20
owner-decision record, D1-D7, and Section 17's D8) and
docs/architecture/audits/EP056_ARCHITECTURE_AUDIT.md. **Final Verdict:
STEP 3 — PASS AFTER REMEDIATION** (first pass: AUDIT FAILED with one
HIGH/BLOCKING finding; the owner approved fixing it during STEP 4 via
Owner Decision D8, and it is now resolved and verified -- see below).
Like EP-054/EP-055, EP-056's roadmap entry was a bare title with no
functional specification (Owner Decision D1) -- STEP 1 found the
strongest textual anchor of any Phase-9 EP so far:
`PromptBuilder.append_capabilities()`'s own docstring, already
written during EP-017, reads "reserved for the future Capability
Registry" verbatim, and recommended "Candidate A": an on-demand
Capability Registry composing already-declared Plugin capability data
(EP-010) plus bare `CommandRouter` namespace names. Built as a new
`capability` `CommandModule`
(`src/skills/capability_registry/skill.py`) providing `list` (compose
a summary of every currently running plugin's declared capability
tags plus the bare list of registered built-in commands) and `inject
<text>` (pass that same summary through the Prompt Engine's existing,
previously-unused `PromptManager.build(capabilities=...)` seam
together with `<text>`, returning the assembled prompt for
inspection -- never calling an AI provider) -- plus `help`, dispatched
through the *existing*, unmodified `CommandRouter.dispatch()`, exactly
as every prior skill already is: no second dispatch mechanism, no
change to Tool Engine. Like EP-054/EP-055, EP-056 introduces no new
external I/O surface and therefore no new backend Protocol (Owner
Decision D1) -- `CapabilityRegistryModule` instead composes two
already-existing, unmodified components directly, read-only:
`PluginService.running_plugins()` (EP-010) and `CommandRouter.
module_names`. The EP-010 Plugin system and EP-017 Prompt Engine are
never modified or redesigned; `PromptManager`/`PromptBuilder` are
called only through their existing, unmodified public API. No
separate AI-provider privacy gate exists, since neither action ever
calls an AI provider (Owner Decision D3). No `AgentEngine` subsystem
registration exists in v1. No new dependency was introduced. Gated by
`capability_registry.enabled` (default `false`, re-checked on every
dispatched action). Owner Decisions D1-D7 (Candidate A scope, include
`capability inject`, no separate privacy gate, `capability` namespace
name, `Bootstrap` registration at the existing `plugin_service` site,
real `PromptManager` in integration tests, `CommandRouter` dispatch)
are all confirmed correctly implemented with zero findings against
their literal text. Tests: EP-056 62/0/0 (51 original plus 11 added
during STEP 4 specifically to exercise the real, enabled `Bootstrap`
wiring end-to-end), covering argument-shape/gate/dispatch behavior
against fake `PluginService`/`module_names` stand-ins, a real,
unmodified `PromptManager` integration for `capability inject`, and a
real-`Bootstrap` regression guard. Full regression: EP-055 64/0/0,
EP-054 76/0/0, EP-053 58/0/0, EP-052 135/0/0, EP-051 105/0/0, EP-050
112/0/0, independently reproduced exactly both before and after the
STEP 4 fix. **STEP 3 finding (identified, then fixed and verified
during STEP 4):** (1, HIGH/BLOCKING) the STEP 3 audit's direct
exercise of the real, fully-wired `Bootstrap` with
`capability_registry.enabled: true` -- a step beyond what the
registered test suite performed -- found that `src/bootstrap.py`
passed `CommandRouter.module_names` (a `@property`, evaluated eagerly
at construction time) where `CapabilityRegistryModule`'s own
documented constructor contract required a live, zero-argument
callable, causing a 100%-reproducible `TypeError` on every single call
to `capability list` or `capability inject`, surfaced to the end user
only as a generic "Internal error" message; `capability help` was
unaffected, and no security, disclosure, or gate-bypass issue was
involved. The registered 51-assertion suite did not catch it because
its fake `module_names` collaborator correctly implemented the
*documented* interface -- only a real, enabled `Bootstrap` exercise
could surface the mismatch between that documentation and what
`bootstrap.py` actually supplied. Fixed in STEP 4 by a single-line,
behavior-preserving change (`module_names=router.module_names` ->
`module_names=lambda: router.module_names`) confined entirely to
`src/bootstrap.py`, requiring zero change to
`src/skills/capability_registry/skill.py`, `CommandRouter`,
`PluginService`, or `PromptManager`. Verified against a reverted,
pre-fix scratch copy (confirming the new tests would have caught the
original defect, not merely passing vacuously) and against the real,
fixed code's before/after responses through the actual `Bootstrap` ->
`CommandRouter` -> `CapabilityRegistryModule` path -- see
`docs/architecture/audits/EP056_ARCHITECTURE_AUDIT.md` Sections 15-18
for full detail. `src/core/plugins/plugin.py`, `plugin_manifest.py`,
`plugin_registry.py`, `plugin_loader.py`, `plugin_discovery.py`
(EP-010 Plugin system), `src/services/plugin_service.py`,
`src/core/ai/prompt.py`, `prompt_builder.py`, `prompt_manager.py`
(EP-017 Prompt Engine), `src/core/command_router.py`,
`src/services/ai_service.py`, and every prior skill (`desktop`,
`browser`, `files`, `vision`, `reflect`, `prompt`) are all confirmed
byte-identical/unmodified by EP-056, both before and after the STEP 4
fix.

EP-055 Prompt Optimizer — **COMPLETE** (STEP 1 Architecture Discovery
& Design, STEP 2 Implementation & Testing, STEP 3 Architecture Audit,
STEP 4 Finalization all complete -- see
docs/architecture/designs/EP055_DESIGN.md (including its Section 20
owner-decision record, D1-D9, and Section 17's D10) and
docs/architecture/audits/EP055_ARCHITECTURE_AUDIT.md. **Final
Verdict: STEP 3 — PASS AFTER REMEDIATION** (first pass: AUDIT PASSED
WITH FINDINGS, one non-blocking MEDIUM finding and one non-blocking
LOW finding; unlike EP-054, the owner approved fixing both during
STEP 4 via Owner Decision D10, and both are now resolved and verified
-- see below). Like EP-054, EP-055's roadmap entry was a bare title
with no functional specification (Owner Decision D1) -- STEP 1
surveyed the already-built EP-017 Prompt Engine and recommended
"Candidate A": on-demand improvement of a prompt's or an existing
template's clarity/structure. Built as a new `prompt` `CommandModule`
(`src/skills/prompt_optimizer/skill.py`) providing `optimize <text>` /
`optimize --template <name>` -- plus `help`, dispatched through the
*existing*, unmodified `CommandRouter.dispatch()`, exactly as every
prior skill already is: no second dispatch mechanism, no change to
Tool Engine. Like EP-054, EP-055 introduces no new external I/O
surface and therefore no new backend Protocol (Owner Decision D1) --
`PromptOptimizerModule` instead composes one already-existing,
unmodified component directly: `ProviderManager`/`AIProvider` (via
`ProviderManager.get_current().ask()`, deliberately bypassing
`AIService`'s pipeline so an optimization request neither becomes a
new conversation turn nor recursively re-enters the very Prompt
Engine pipeline whose template input it is improving). `paths.prompts`
(already reserved by EP-017) is read, never written to (Owner
Decision D4 -- return-only in v1, no `prompt save`). EP-017's Prompt
Engine (`Prompt`/`PromptBuilder`/`PromptManager`) is never modified or
called by EP-055. No `AgentEngine` subsystem registration exists in
v1 (Owner Decision D5 -- `CommandModule` only). No new dependency was
introduced. Gated by `prompt_optimizer.enabled` (default `false`,
re-checked on every dispatched action), `prompt_optimizer.
max_input_size` (default 4000, an input exceeding it is refused,
never silently truncated), and `prompt_optimizer.
min_seconds_between_calls` (default 30, a simple, in-process rate
limit). Owner Decisions D1-D9 (Candidate A scope, single
`prompt_optimizer.enabled` gate with no separate AI-provider privacy
gate, return-only v1, no Agent subsystem registration, resource/
rate-limit defaults, `CommandRouter` dispatch, no real-`AIProvider`
integration test, no EP-014-017 test-registration backfill) are all
confirmed correctly implemented with zero findings against their
literal text. Tests: EP-055 64/0/0 (52 original plus 12 added during
STEP 4 specifically to prove the corrected gate ordering), covering
argument-shape/gate/rate-limit/resource-cap/dispatch behavior against
fake `ProviderManager` stand-ins plus real, temporary-directory-backed
template-file tests, plus `CommandRouter` dispatch equivalence and
`Bootstrap` wiring tests. Full regression: EP-054 76/0/0, EP-053
58/0/0, EP-052 135/0/0, EP-051 105/0/0, EP-050 112/0/0, independently
reproduced exactly both before and after the STEP 4 fix. **STEP 3
findings (identified, then fixed and verified during STEP 4):** (1,
originally MEDIUM) `PromptOptimizerModule._optimize()`'s `--template`
resolution performed a real filesystem read and could disclose a
named template's existence, emptiness, or absolute resolved path via
an error message before the `prompt_optimizer.enabled` gate was
checked -- no AI-provider call ever occurred and template content was
never disclosed; fixed in STEP 4 by splitting argument-shape
validation (no filesystem access, runs before the gate) from actual
input resolution (which may read a template file, now runs strictly
after the gate/rate-limit). (2, originally LOW) the `max_input_size`
cap check ran before the same gate, allowing that non-secret,
operator-configured numeric value to be observed via an error message
while disabled -- closely mirroring EP-054's own previously-accepted
Finding 2; resolved by the same reordering. Both fixes were verified
against a reverted, pre-fix scratch copy (confirming the new tests
would have caught the original behavior, not merely passing
vacuously) and against the real, fixed code's before/after responses
-- see `docs/architecture/audits/EP055_ARCHITECTURE_AUDIT.md` Sections
15-18 for full detail. `src/core/ai/prompt.py`, `prompt_builder.py`,
`prompt_manager.py` (EP-017 Prompt Engine), `src/core/ai/
context_manager.py`, `context_loader.py`, `context.py` (EP-018
Context Engine), `src/core/command_router.py`, `src/core/tool/`,
`src/core/ai/provider.py`, `provider_manager.py`,
`conversation_manager.py`, `src/services/ai_service.py`, `src/core/
agent/`, `src/core/planning/`, `src/core/scheduler/`, and every prior
skill (`desktop`, `browser`, `files`, `vision`, `reflect`) are all
confirmed byte-identical/unmodified by EP-055, both before and after
the STEP 4 fix.

EP-054 Self Reflection — **COMPLETE** (STEP 1 Architecture Discovery
& Design, STEP 2 Implementation & Testing, STEP 3 Architecture Audit,
STEP 4 Finalization all complete -- see
docs/architecture/designs/EP054_DESIGN.md (including its Section 20
owner-decision record, D1-D9) and
docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md. **Final Verdict:
STEP 3 — AUDIT PASSED WITH FINDINGS** (one non-blocking MEDIUM finding
and one non-blocking LOW finding, both documented and not fixed
during STEP 4 -- see below). Unlike EP-050 through EP-053, EP-054's
roadmap entry was a bare title with no functional specification
(Owner Decision D1) -- STEP 1 surveyed the existing architecture and
recommended "Candidate A": on-demand session/conversation
self-critique. Built as a new `reflect` `CommandModule`
(`src/skills/reflection/skill.py`) providing `summary` (ask the
configured AI provider to critique the last N messages of the current
conversation) and `recall` (return previously persisted critiques) --
plus `help`, dispatched through the *existing*, unmodified
`CommandRouter.dispatch()`, exactly as every prior skill (`desktop`,
`browser`, `file`, `vision`) already is: no second dispatch mechanism,
no change to Tool Engine. Unlike `desktop`/`browser`/`file`/`vision`,
EP-054 introduces no new external I/O surface and therefore no new
backend Protocol (Owner Decision D1) -- `ReflectionModule` instead
composes three already-existing, unmodified components directly:
`ConversationManager` (read-only), `ProviderManager`/`AIProvider`
(via `ProviderManager.get_current().ask()`, deliberately bypassing
`AIService`'s conversation-mutating pipeline so a reflection never
appends itself to the conversation it is reflecting on), and,
optionally, `MemoryService` (only when `reflection.persist_to_memory`
is enabled). v1 is strictly descriptive (Owner Decision D3): it never
autonomously changes any configuration, prompt, or other component's
behavior. No `Scheduler` integration and no `AgentEngine` subsystem
registration exist in v1 (Owner Decisions D5/D6 -- manual-only,
`CommandModule` only). No new dependency was introduced. Gated by
`reflection.enabled` (default `false`, re-checked on every dispatched
action), `reflection.max_message_count` (default and cap: 20, an
explicit count exceeding it is refused, never silently reduced), and
`reflection.min_seconds_between_calls` (default 30, a simple,
in-process rate limit). Owner Decisions D1-D9 (Candidate A scope, no
separate AI-provider privacy gate, strictly descriptive output,
opt-in Memory persistence, manual-only triggering, no Agent subsystem
registration, resource/rate-limit defaults, `CommandRouter` dispatch,
no real-`AIProvider` integration test) are all confirmed correctly
implemented, aside from the two findings below. Tests: EP-054 76/0/0,
covering argument-shape/gate/rate-limit/resource-cap/dispatch behavior
against fake `ConversationManager`/`ProviderManager`/`MemoryService`
stand-ins, plus `CommandRouter` dispatch equivalence and `Bootstrap`
wiring tests. Full regression: 6339/2/3 -- the 2 failures and 3 skips
are the same pre-existing EP-046/EP-048/EP-049 voice-stack/sandbox
limitations already documented at EP-053's completion, independently
reproduced again and confirmed unrelated to EP-054. **STEP 3 findings
(documented, not fixed):** (1, MEDIUM) `EP054_DESIGN.md`'s own Section
12 committed to adding a real, non-fake `MemoryService`-backed test
once Owner Decision D4 was approved; no such test exists in the
registered suite -- every persistence test uses a fake `MemoryService`
only. The STEP 3 audit independently built and ran a real
`MemoryService`/`MemoryStore` integration probe and confirmed the
actual integration works correctly; the finding is a test-coverage
gap against a self-imposed design commitment, not a functional
defect. (2, LOW) `ReflectionModule._summary()`'s `max_message_count`
cap check runs before the `reflection.enabled` gate, so a caller can
observe the configured cap's numeric value via an error message even
while Self Reflection is disabled -- confirmed, via dummy objects that
raise on any call, that zero downstream (conversation/provider) calls
occur in this case; no gate or resource-limit bypass exists. See
`docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md` Section 15 for
full detail on both findings. `src/core/command_router.py`,
`src/core/tool/`, `src/core/ai/provider.py`,
`src/core/ai/provider_manager.py`, `src/core/ai/conversation_manager.py`,
`src/core/ai/conversation.py`, `src/core/memory/`, `src/core/agent/`,
`src/core/planning/`, `src/core/scheduler/`,
`src/services/ai_service.py`, `src/services/memory_service.py`, and
every Phase 7/8 skill (`desktop`, `browser`, `files`, `vision`) are
all confirmed unmodified by EP-054.

EP-053 Vision Integration — **COMPLETE** (STEP 1 Architecture
Discovery, Technology Evaluation & Design, STEP 2 Implementation &
Testing, STEP 3 Architecture Audit, STEP 4 Finalization all complete
-- see docs/architecture/designs/EP053_DESIGN.md (including its
Section 20 owner-decision record, D1-D10) and
docs/architecture/audits/EP053_ARCHITECTURE_AUDIT.md. **Final Verdict:
STEP 3 — AUDIT PASSED WITH FINDINGS** (one non-blocking MEDIUM
finding, documented and not fixed during STEP 4 -- see below). Built
as a new `vision` `CommandModule` (`src/skills/vision/skill.py`)
providing local, read-only image interpretation -- `info` (image
metadata: width, height, format, color mode, file size) and `ocr`
(text extraction) -- plus `help`, dispatched through the *existing*,
unmodified `CommandRouter.dispatch()`, exactly as every prior skill
(`desktop`, `browser`, `file`, ...) already is: no second dispatch
mechanism, no change to Tool Engine. A new `VisionBackend` protocol
(`src/skills/vision/backend.py`) defines the vision-interpretation
contract; `LocalVisionBackend` (`src/skills/vision/local_backend.py`)
is the sole real implementation, built on Pillow (image decoding) and
`pytesseract` (OCR, wrapping an external Tesseract binary) -- v1 is
local-only: no AI-provider/network path exists, and `src/core/ai/
provider.py` is entirely unmodified. Gated by `vision.enabled`
(default `false`, re-checked on every dispatched action) and an
independent `vision.allowed_roots` allow-list (empty blocks
everything; no runtime coupling to `file.allowed_roots` or
`FileBackend`), plus resource limits (`vision.max_file_size_mb`,
`vision.max_dimension`) enforced inside `LocalVisionBackend`. `info`
never depends on the Tesseract binary being installed (split
availability); only `ocr` does. Owner Decisions D1-D10 (local-only
scope, `pytesseract` OCR engine, path-only input, independent
path-safety model, resource limits, CPU-only, dependency approval,
split availability, `CommandRouter` dispatch, fake-backend +
real-Pillow test strategy) are all confirmed correctly implemented.
Tests: EP-053 58/0/0, covering protocol conformance, argument-shape/
gate/path-safety/dispatch behavior against a `_FakeVisionBackend`,
and real-Pillow filesystem/image behavior (including resource-limit
enforcement) against `LocalVisionBackend`; a separate, intentionally
unregistered real-Tesseract OCR check
(`tests/EP053/test_vision_ocr_integration.py`) independently verified
genuine end-to-end text recognition. Full regression: 6263/2/3 --
the 2 failures and 3 skips are pre-existing EP-046/EP-048/EP-049
voice-stack/sandbox limitations (`openwakeword`/`tflite-runtime`
having no Linux wheel in this environment, and real-hardware-only
scenarios already documented as skippable by their own design
documents), independently reproduced and confirmed unrelated to
EP-053. **STEP 3 finding (MEDIUM, non-blocking, not fixed):**
`LocalVisionBackend` currently enforces its `max_dimension` resource
limit *after* Pillow fully decodes the image, rather than before, as
`EP053_DESIGN.md`'s own Owner Decision D5 specified -- the limit is
still always enforced and no oversized result is ever returned, but
an oversized-dimension image is unnecessarily fully decoded before
being rejected. This is documented, not remediated, per the STEP 3
audit's "record, do not fix" instruction; see
`docs/architecture/audits/EP053_ARCHITECTURE_AUDIT.md` Section 15,
Finding 1 for full detail. `src/core/command_router.py`,
`src/core/tool/`, `src/core/ai/provider.py`, `src/skills/desktop/`,
`src/skills/browser/`, and `src/skills/files/` are all confirmed
unmodified by EP-053.

EP-052 File Automation — **COMPLETE** (STEP 1 Architecture Discovery,
Technology Evaluation & Design, STEP 2 Implementation & Testing,
STEP 3 Architecture Audit, STEP 4 Finalization all complete -- see
docs/architecture/designs/EP052_DESIGN.md (including its Section 20
owner-decision record, D1-D11) and
docs/architecture/audits/EP052_ARCHITECTURE_AUDIT.md. Verdict:
**PASS AFTER REMEDIATION** (one narrowly-scoped Owner-Decision-D11
remediation to `src/core/command_router.py`'s command tokenizer,
fixing Windows backslash-path corruption for `file` actions -- no
other defect, security-gate weakening, or scope expansion). Built as
a new `file` `CommandModule` (`src/skills/files/skill.py`) providing
9 CRUD actions -- `list`, `exists`, `stat`, `read`, `write`, `copy`,
`move`, `mkdir`, `delete` -- plus `help`, dispatched through the
*existing*, unmodified `CommandRouter.dispatch()`, exactly as every
prior skill (`desktop`, `browser`, ...) already is: no second dispatch
mechanism. A new `FileBackend` protocol (`src/skills/files/backend.py`)
defines the file-automation contract; `LocalFileBackend`
(`src/skills/files/local_backend.py`) is the sole real implementation,
gated by a layered security model -- `file.enabled` (default `false`,
re-checked on every dispatched action), `file.allow_destructive`
(separately gating `move`/`delete`/overwrite), `file.allowed_roots`
(an explicit allow-list; empty blocks everything), `file.denied_paths`
(excludes specific paths inside an allowed root), path-traversal/
absolute-path rejection, non-recursive `delete`, and UTF-8-only file
content. Tests: EP-052 135/0/0, covering protocol conformance and
argument-shape/gate/path-safety/dispatch behavior against a
`_FakeFileBackend`, plus real CRUD/overwrite/non-recursive-delete/
UTF-8 behavior against `LocalFileBackend` in a disposable
`tempfile.TemporaryDirectory()` -- never the repository root or an
operator's home directory. `src/core/tool/`, Agent Framework, Planning
Engine, Plan Execution Engine, `src/skills/browser/` (EP-051), and
`src/skills/desktop/` (EP-050) are all confirmed unmodified by
EP-052, aside from the one owner-authorized `CommandRouter` line
described above.

EP-051 Browser Automation — **COMPLETE** (STEP 1 Architecture
Discovery, Technology Evaluation & Design, STEP 2 Implementation &

Testing, STEP 3 Architecture Audit, STEP 4 Documentation Completion
all complete -- see docs/architecture/designs/EP051_DESIGN.md
(including its Section 21 owner-decision record, D1-D12) and
docs/architecture/audits/EP051_AUDIT.md. Verdict: **PASS WITH
FINDINGS** (one HIGH, three MEDIUM, three LOW -- see below; none
blocking, none fixed during STEP 4 per the audit's own "document, do
not fix" rule). Built as a new `browser` `CommandModule`
(`src/skills/browser/skill.py`) providing fifteen actions -- `launch`,
`close`, `goto`, `back`, `forward`, `reload`, `title`, `current-url`,
`page-text`, `exists`, `click`, `type`, `clear`, `press`,
`screenshot` -- plus `help`, for controlled browser lifecycle,
navigation, and single-element DOM interaction, dispatched through the
*existing*, unmodified `CommandRouter.dispatch()`, exactly as every
prior skill (`desktop`, `voice`, `system`, ...) already is: no second
dispatch mechanism, no change to `src/core/command_router.py`. A new
`BrowserBackend` protocol (`src/skills/browser/backend.py`) defines
the browser-automation contract; `PlaywrightBrowserBackend`
(`src/skills/browser/playwright_backend.py`, Owner Decision D1) is the
sole real implementation, built on Playwright's synchronous API
(`playwright==1.62.0`, replacing the previously-declared, unpinned,
and confirmed-unused `selenium` entry -- zero migration cost, since
nothing in the repository imported Selenium before EP-051). Genuinely
cross-platform by design (Owner Decision D11) -- no Windows-only guard
exists in `PlaywrightBrowserBackend`, unlike EP-050's own
`WindowsComputerUseBackend`, though Windows remains the intended
manual-verification target. `browser.enabled` defaults to `false`,
re-checked on every dispatched action (not only at registration),
guaranteeing zero backend interaction while disabled -- confirmed by
dedicated tests. No per-action human-confirmation framework was built
(Owner Decision D2), no domain allow-list exists (Owner Decision D6,
a disclosed, accepted v1 limitation), and no JavaScript execution,
download, upload, multi-session, or multi-tab capability exists
anywhere (Owner Decisions D7/D8/D5/D12) -- confirmed absent by direct
code inspection during the architecture audit, not merely by design
intent. `src/skills/desktop/` (EP-050), Tool Engine (`src/core/tool/`),
`src/core/command_router.py`, Agent Framework, Planning Engine, and
Plan Execution Engine are all confirmed byte-identical to their
pre-EP-051 state. `CommandRouter` was chosen over Tool Engine for the
same, now twice-independently-confirmed reason EP-050 already
established: `Tool.handler` remains zero-argument-only for every
action registered in the project. Tests: EP-051 105/0/0, entirely
deterministic against a `_FakeBrowserBackend`, no real browser process
required; a separate, intentionally unregistered
`tests/EP051/test_browser_integration.py` exists for manual,
real-browser verification, but the architecture audit found this
script itself misreports its own skip condition (see findings below)
and confirmed real Chromium execution remains unverified in the
development sandbox (`playwright install chromium` cannot complete
there -- the Playwright CDN is outside the sandbox's allowed network
egress list). Focused regression check: EP-031/044/045/050 all pass
unchanged; EP-046/049 reproduce the same pre-existing, sandbox-only
conditions already disclosed against EP-048/049 above, confirmed
unrelated to and unmodified by EP-051.

**Audit findings (verdict PASS WITH FINDINGS, none blocking, none
fixed during EP-051 -- see `EP051_AUDIT.md` Section 17 for full detail
and Section 21 for recommended follow-up):**

- **HIGH** -- the same pre-existing `CommandRouter.dispatch()` raw-
  input logging (`src/core/command_router.py`) EP050_AUDIT.md already
  documented for `desktop type`/`desktop write-clipboard` was
  independently re-confirmed for `browser type`'s typed text and
  `browser goto`'s URL (which may embed a token/credential as a query
  parameter) -- undermining EP051_DESIGN.md Section 12's "never
  logged" commitment end-to-end, even though `BrowserModule` itself
  never logs this content. Not introduced by EP-051; tracked as a
  follow-up item below, not fixed during EP-051.
- **MEDIUM (x3)** -- `PlaywrightBrowserBackend._call()`'s exception
  catch is narrower than `launch()`'s own, better-justified broad
  catch, risking an unnormalized exception on an in-session action
  failure (contained by `CommandRouter`'s own top-level catch-all, no
  crash); a `close()` failure may skip stopping the underlying
  Playwright driver subprocess while internal state is reset
  regardless; the unregistered real-browser integration script reports
  "FAILED" rather than "SKIPPED" when Playwright is installed but no
  browser binary has been downloaded -- the exact state of the
  development sandbox -- correcting the STEP 2 report's original
  "skips gracefully" claim.
- **LOW (x3)** -- no explicitly-named "double close"/"action after
  close" test scenario (the underlying code path is correct by
  inspection); raw Playwright exception message text (not type)
  reaches `CommandResult.message`, mirroring an already-accepted
  EP-050 precedent; `src/skills/browser/selenium_driver.py` (a 0-byte
  placeholder predating EP-051) was not deleted as
  EP051_DESIGN.md Section 22 proposed, and remains present, empty, and
  unimported.

EP-050 Computer Use — **COMPLETE** (STEP 1 Architecture Research,
Design & Owner Decisions, STEP 2 Implementation & Testing, STEP 3
Architecture Audit, STEP 4 Documentation Completion all complete --
see docs/architecture/designs/EP050_DESIGN.md (including its Section
30 owner-decision record, D1-D6, and its Section 32 STEP 1 Final
Review of the CommandRouter-vs-Tool-Engine decision) and
docs/architecture/audits/EP050_AUDIT.md. Verdict: **PASS WITH
FINDINGS** (one HIGH, one MEDIUM, four LOW, four INFO -- see below;
none blocking, none fixed during STEP 4 per the audit's own "document,
do not fix" rule). Built as a new `desktop` `CommandModule`
(`src/skills/desktop/skill.py`) providing raw, local, offline OS-level
input control -- `help`, `move`, `click`, `scroll`, `type`, `key`,
`read-clipboard`, `write-clipboard`, `screenshot`, `cursor`,
`screen-size`, `active-window`, `focus` -- dispatched through the
*existing*, unmodified `CommandRouter.dispatch()`, exactly as every
prior skill (`voice`, `system`, ...) already is: no second dispatch
mechanism, no change to `src/core/command_router.py`. A new
`ComputerUseBackend` protocol (`src/skills/desktop/backend.py`)
defines the OS-input contract; `WindowsComputerUseBackend`
(`src/skills/desktop/windows_backend.py`, PyAutoGUI-based, Owner
Decision D3) is the sole real implementation, honestly scoped as
Windows v1 (Owner Decision D5) rather than claiming cross-platform
support. `desktop.enabled` defaults to `false`, re-checked on every
dispatched action (not only at registration), guaranteeing zero
backend interaction -- including no `screen_size()` call for bounds
validation -- while disabled; a general per-action human-confirmation
framework was deliberately not built (no such mechanism exists
anywhere in the project today), a disclosed limitation carried
forward from Owner Decision D2, not fixed by EP-050. Tool Engine
(`src/core/tool/`), Agent Framework, Planning Engine, Plan Execution
Engine, `src/core/execution/` (EP-003's process/application launcher),
the EP-044 `desktop/` PySide6 GUI client (a distinct, unrelated
directory from `src/skills/desktop/` -- the two are never merged), and
`src/skills/browser/` (still empty, confirmed reserved for EP-051) are
all confirmed byte-identical to their pre-EP-050 state. `CommandRouter`
was deliberately chosen over Tool Engine for v1 because Tool Engine's
`Tool.handler` is zero-argument-only for every action already
registered in the project (a pre-existing, already-disclosed
limitation, not introduced by EP-050) -- this is documented as a
deferred architectural evolution (a future, dedicated "parameterized
Tool support" Engineering Package, left unscheduled and unnumbered by
this EP), not a permanent rejection. Tests: EP-050 112/0/0, entirely
deterministic against a fake backend, no real mouse/keyboard/screen/
PyAutoGUI/display required; a separate, intentionally unregistered
`tests/EP050/test_desktop_windows_integration.py` exists for manual,
real-hardware verification and correctly self-skips in a headless
environment. The architecture audit's one HIGH finding: `CommandRouter
.dispatch()`'s own pre-existing, unmodified raw-input logging
(`src/core/command_router.py`) logs the full command line on every
dispatch, including `desktop type`/`desktop write-clipboard`'s
sensitive argument content -- a shared-infrastructure behavior
pre-dating and extending beyond EP-050 (equally true of, e.g., `email
send`'s body or `git commit -m`'s message), not a defect in EP-050's
own code, but one that undermines EP050_DESIGN.md Section 19's
explicit "never logged" privacy commitment end-to-end; tracked as a
recommended follow-up (see docs/BACKLOG.md), not fixed during EP-050.
One MEDIUM finding (`WindowsComputerUseBackend.active_window_title()`
over-broadly swallows all exceptions into an empty-string return
rather than raising for genuine failures) and four LOW/four INFO
findings (click-argument ambiguity, no literal `'+'`-key support, no
partial-file cleanup on a failed screenshot write, no runtime
Windows-platform guard, a `runtime_checkable` Protocol signature-
checking limitation, `desktop.backend`'s intentional omission,
active-window-title logging) are recorded in full in
`EP050_AUDIT.md` Section 22 -- none blocking.)

EP-049 Voice Assistant — **COMPLETE** (STEP 1 Design & Owner
Decisions, STEP 2 Implementation & Verification, STEP 3 Architecture
Audit / Final Verification all complete -- see
docs/architecture/designs/EP049_DESIGN.md (including its Section 23a
final owner-decision record) and
docs/architecture/audits/EP049_AUDIT.md. Verdict: **PASS WITH
PRE-EXISTING ENVIRONMENT LIMITATION** (the limitation being an
EP-048-owned, sandbox-only `openwakeword`/`tflite-runtime` Linux
packaging quirk, unrelated to and unmodified by EP-049 -- see below).
Built as a strictly one-shot `voice wake assist` action, composed
into the *existing* `voice` `CommandModule`
(`src/skills/voice/skill.py`) alongside EP-048's `wake
listen`/`wake status` -- no second namespace, no new dispatch
mechanism, no change to `src/core/command_router.py`,
`src/core/api/`, Telegram, `desktop/`, or `web/`. On a wake-word
detection, `voice wake assist` stops the existing
`StreamingAudioCapture` wake stream and calls the existing, unmodified
`_listen()` directly -- the same method `voice listen` already
calls -- which owns EP-046's `AudioCapture`/STT, EP-046's existing
confidence gate, and `CommandRouter.dispatch()`. An optional TTS step
(EP-047's existing `TextToSpeechEngine`) may speak the dispatched
result. `_listen()`, `CommandRouter`, and `Bootstrap` are all
confirmed byte-identical to their pre-EP-049 state -- EP-049
introduces no second STT/wake/dispatch implementation, no new
`VoiceModule` constructor parameter, and no new dependency
(`requirements.txt` unchanged). Strictly one-shot by owner decision:
exactly one wake -> command -> result cycle per invocation, with no
loop, no repeat/continuous-listening configuration, no
Bootstrap-managed background thread or daemon, and no automatic
re-arming of wake listening -- a new invocation of `voice wake
assist` is required for another cycle. New configuration:
`voice.wake.assist.enabled` and `voice.wake.assist.speak_result`,
both defaulting to `false`; no `one_shot` key exists. Automated
tests: EP-049 87/0/1 (one disclosed skip -- the real-hardware
scenario, see below); EP-046 58/0/1 and EP-047 49/0/0 both fully
unchanged. On the real target Windows workstation, where
`openwakeword`'s `tflite-runtime` Linux-only constraint does not
apply, EP-048's own suite has been independently verified by the
project owner at **112 passed / 0 failed / 1 skipped** -- the two
failures seen in the Linux sandbox used for STEP 1-3 development
(`tflite-runtime` has no published distribution for that
platform/Python combination, confirmed unfixable from within the
sandbox) do not reproduce on the actual target machine and are not
an EP-049 regression. Manual, real-microphone/real-loaded-model
wake-to-dispatch verification (the full `voice wake assist` pipeline
end to end, not just EP-048's own wake-detection step) remains an
outstanding, disclosed item -- see `EP049_AUDIT.md` Section 14 for
the exact checklist.) EP-048
Wake Word remains **COMPLETE** (STEP 1-3 plus a post-STEP-3 real-
Windows-hardware bug fix, unchanged by EP-049 --
`src/skills/voice/wake_word.py` and
`src/skills/voice/streaming_audio_capture.py` confirmed byte-identical
to their EP-048-shipped state -- see
docs/architecture/designs/EP048_DESIGN.md (including its Section 9a
owner-decision record, Section 17 as-built summary, and Section 17.7
post-STEP-3 bug-fix account) and
docs/architecture/audits/EP048_AUDIT.md (Section 17, "Post-Audit Bug
Fix / Final Verification"). Verdict: **PASS** (updated from STEP 3's
original "PASS WITH DOCUMENTED LIMITATIONS" once real Windows
hardware verification closed the one limitation that was actually
EP-048's own -- an `openwakeword==0.6.0` Linux packaging quirk in the
automated-testing environment remains disclosed, unrelated to the
Windows target). Built as offline, `openWakeWord`-based
wake-phrase detection (`src/skills/voice/wake_word.py`) fed by a new,
separate `StreamingAudioCapture` component
(`src/skills/voice/streaming_audio_capture.py`, kept apart from
EP-046's existing fixed-duration `AudioCapture`, which was not
modified), composed into the *existing* `voice` `CommandModule`
(`src/skills/voice/skill.py`) as additive `wake listen`/`wake status`
actions -- no second namespace, no new dispatch mechanism, no change
to `src/core/command_router.py`, `src/core/api/`, Telegram,
`desktop/`, or `web/`. `voice wake listen` only ever reports a
detection: it never dispatches through `CommandRouter`, never starts
an STT (`voice listen`) cycle, never speaks via TTS, and never runs
as a background listener or daemon -- confirmed by dedicated
call-counting tests, not only by design. Supports English ("Hey
Jarvis") only; Russian and Uzbek wake-word detection are explicitly
out of scope (no offline wake-word model evaluated has first-class
support for either) and receive no special-case handling anywhere in
code. Model files are never downloaded automatically -- manual
placement only, mirroring EP-046's own Vosk precedent.
`voice.wake.enabled` defaults to `false`. This EP also **fully**
closed EP-047's own disclosed registration-gating limitation: STT,
TTS, and Wake Word can now each be enabled independently, with the
`voice` namespace registering whenever any one of the three is
enabled (previously, TTS-only operation was not reachable -- see the
audit document's Known Limitations for what remains disclosed).
Real microphone/real-loaded-model wake-word detection has since been
verified by a human on the actual target Windows workstation --
`voice wake status` reported the model available and `voice wake
listen` correctly detected "hey_jarvis" (scores 0.80 and 0.64 across
two runs). That same verification pass also surfaced and led to the
correction of a real model-filename-resolution defect (the
implementation originally looked only for a bare `hey_jarvis.onnx`
file; openWakeWord's own official models ship as
`hey_jarvis_v0.1.onnx` -- now resolved deterministically without any
automatic download) -- see the audit document's Section 17 for full
detail.) EP-047
Text-to-Speech remains **COMPLETE** (STEP 1-3, unchanged by
EP-048/EP-049 -- `src/skills/voice/text_to_speech.py` confirmed
byte-identical to its EP-047-shipped state; its own disclosed
TTS-only registration limitation is now resolved by EP-048's D6 fix,
recorded in both EPs' audit documents -- see
docs/architecture/designs/EP047_DESIGN.md and
docs/architecture/audits/EP047_AUDIT.md.) EP-046 Speech-to-Text
remains **COMPLETE** (STEP 1-3, unchanged by EP-047/EP-048/EP-049 --
`src/skills/voice/speech_to_text.py` and
`src/skills/voice/audio_capture.py` confirmed byte-identical to their
EP-046-shipped state -- see
docs/architecture/designs/EP046_DESIGN.md and
docs/architecture/audits/EP046_AUDIT.md.) EP-045 Web Dashboard
remains **COMPLETE** (STEP 1-3, unchanged by
EP-046/EP-047/EP-048/EP-049, `web/` confirmed absent from the EP-049
changeset -- see
docs/architecture/designs/EP045_DESIGN.md and
docs/architecture/audits/EP045_AUDIT.md.) EP-044 Desktop UI remains
**COMPLETE** (STEP 1-3, unchanged by
EP-045/EP-046/EP-047/EP-048/EP-049, `desktop/` confirmed absent from
the EP-049 changeset -- see
docs/architecture/designs/EP044_DESIGN.md and
docs/architecture/audits/EP044_AUDIT.md.) EP-043 REST API remains
**COMPLETE** (STEP 1-4, unchanged by
EP-044/EP-045/EP-046/EP-047/EP-048/EP-049 -- see
docs/architecture/designs/EP043_DESIGN.md and
docs/RELEASE_NOTES.md.)

---

# Roadmap

## Phase 1 — Core Platform

EP-001 Core Foundation

EP-002 Interactive Shell

EP-003 Process Manager

EP-004 Testing Framework

EP-005 Invoice Automation

EP-006 Fast Response Board

EP-007 Core Improvements

EP-008 Process Aliases

EP-009 Process Catalog

EP-010 Configuration

EP-011 Logging

EP-012 Refactoring

EP-013 AI Infrastructure

---

## Phase 2 — AI Core

✓ EP-014 AI Provider Manager

✓ EP-015 AI Provider Integration

✓ EP-016 Conversation Engine

✓ EP-017 Prompt Engine

✓ EP-018 Universal Context Engine

✓ EP-019 Project Index Engine

✓ EP-020 Retrieval Engine

✓ EP-021 Embedding Engine

✓ EP-022 RAG Engine

---

## Phase 3 — Memory

✓ EP-023 Memory Manager

✓ EP-024 Knowledge Base

✓ EP-025 Long-Term Memory

✓ EP-026 Semantic Search

✓ EP-027 Context Compression

---

## Phase 4 — Agent Framework

✓ EP-028 Agent Framework

✓ EP-029 Planning Engine

✓ EP-030 Execution Engine

✓ EP-031 Tool Engine

✓ EP-032 Multi-Agent Collaboration

---

## Phase 5 — Workflow Automation

✓ EP-033 Workflow Engine

✓ EP-034 Scheduler

✓ EP-035 Automation Engine

✓ EP-036 Background Workers

✓ EP-037 Event Bus

---

## Phase 6 — Integrations

✓ EP-038 Git Integration

✓ EP-039 GitHub Integration

✓ EP-040 Telegram Integration

✓ EP-041 Discord Integration

✓ EP-042 Email Integration

✓ EP-043 REST API

✓ EP-044 Desktop UI

✓ EP-045 Web Dashboard

---

## Phase 7 — Voice

✓ EP-046 Speech-to-Text

✓ EP-047 Text-to-Speech

✓ EP-048 Wake Word

✓ EP-049 Voice Assistant

---

## Phase 8 — Computer Automation

✓ EP-050 Computer Use

EP-051 Browser Automation

EP-052 File Automation

EP-053 Vision Integration

---

## Phase 9 — Intelligence

EP-054 Self Reflection

EP-055 Prompt Optimizer

EP-056 Capability Learning

EP-057 Memory Optimization

EP-058 Autonomous Planning

---

## Phase 10 — Jarvis Operating System

EP-059 Distributed Runtime

EP-060 Jarvis Operating System

---

# Architecture Evolution

Core Platform

↓

AI Provider Layer

↓

Conversation Engine

↓

Prompt Engine

↓

Universal Context Engine

↓

Project Index

↓

Retrieval

↓

Embeddings

↓

RAG

↓

Memory

↓

Agent Framework

↓

Tool Engine

↓

Workflow Engine

↓

Automation

↓

Voice

↓

User Interfaces

↓

Jarvis Operating System

---

# Engineering Package Policy

Large Engineering Packages should be implemented in multiple incremental iterations.

Example:

EP-018 Universal Context Engine

- EP-018.1 Foundation
- EP-018.2 Manifest Integration
- EP-018.3 Repository Detection
- EP-018.4 Document Budget
- EP-018.5 Unified Prompt Budget
- EP-018.6 Conversation Budget

EP-019 Project Index Engine

- EP-019.1 Repository Scanner
- EP-019.2 File Index
- EP-019.3 Chunk Generator
- EP-019.4 Metadata Builder
- EP-019.5 Incremental Index
- EP-019.6 Testing
- Status: Completed

This approach allows large architectural modules to evolve without changing the long-term roadmap.

---

# Current Objective

Jarvis evolves incrementally through Engineering Packages.

Only one major Engineering Package should be actively implemented at a time.

Each completed Engineering Package becomes a permanent architectural building block for future development.

The implementation order is defined by this roadmap.

The currently active Engineering Package is tracked separately by the engineering process and project documentation.

# Long-Term Goal

Build a provider-independent AI Operating System capable of:

- understanding software projects
- maintaining engineering knowledge
- retrieving relevant information
- planning complex tasks
- executing tools
- coordinating multiple AI providers
- orchestrating autonomous agents
- automating engineering workflows

The ultimate goal is to create a modular, reusable and extensible AI Operating System that remains independent of any single AI provider or technology.

# Notes

This roadmap defines the official long-term engineering direction of Jarvis.

The numbering of Engineering Packages is stable.

New functionality should normally be implemented as sub-packages (EP-XXX.Y) rather than renumbering the roadmap.

Completed EPs should not be redesigned unless an explicit architectural decision requires it.

End of document.