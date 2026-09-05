# BACKLOG.md

Version: 1.0

Status: Active

---

# Current Backlog

## Next Engineering Package

**None yet defined.** EP-061 (Scheduler Tick-Loop Shutdown) completed
the last item EP-060 itself had explicitly flagged as its own natural
follow-up. No EP-062 or Phase 11 exists anywhere in this repository as
of this release.

### EP-061 — Scheduler Tick-Loop Shutdown

STEP 1 (Architecture Discovery & Design), STEP 2 (Implementation &
Testing), STEP 3 (Architecture Audit), and STEP 4 (Documentation
Synchronization) all complete. EP-061 is marked **COMPLETE / AUDIT
PASSED, NO BLOCKING FINDINGS** -- STEP 3 identified two non-blocking
WARNINGs and zero blocking findings; STEP 4 resolved both (see below)
rather than leaving them open, since resolving them required no
design or scope change, only correcting one stale test-helper
docstring and one imprecise evidence citation in the design document
itself -- see
`docs/architecture/audits/EP061_ARCHITECTURE_AUDIT.md`. Full design,
including Owner Decisions D1-D4: `docs/architecture/designs/
EP061_DESIGN.md`.

Neither this backlog nor `docs/architecture/JARVIS_ROADMAP.md` named
an EP-061 scope -- both said "none yet defined," since EP-060 closed
the roadmap's last currently-named phase (Phase 10). STEP 1 found no
textual anchor naming a specific EP-061 mechanism, but did find a
real, code-verified gap that EP-060 itself explicitly flagged as its
own most natural follow-up (`EP060_DESIGN.md` Section 15, Owner
Decision D5): `SchedulerService`'s automatic tick loop already had a
private `_stop_event`/`_tick_thread` pair built for shutdown, but no
public method to use it, so `RuntimeService.shutdown()`/`Bootstrap.
shutdown()` could stop the REST API Server and the Background Worker
Service but never the Scheduler -- it kept running as a daemon thread
until the whole process exited.

Built by adding exactly one new public method to
`src/services/scheduler_service.py`: `shutdown(wait=True,
timeout=None) -> bool`, stopping the background tick loop via the
already-existing `_stop_event`/`_tick_thread` mechanism -- idempotent,
identity-guarded against a hypothetical replacement thread, and
deliberately releasing its internal lock before the bounded thread
join so a concurrent `status()`/`doctor()` call is never blocked by an
in-progress shutdown. Wired into `src/services/runtime_service.py`'s
existing `shutdown()` (`RuntimeShutdownReport` gains
`scheduler_was_active`/`scheduler_stopped`, both defaulted and
appended after the four existing fields) -- placed between the
existing REST API Server step and the existing Background Worker
Service step (Owner Decision D2), after independently verifying during
STEP 1 that `Scheduler` and `BackgroundWorkerService` share no queue,
pool, or execution engine (`Scheduler` executes jobs synchronously
through EP-003's `ExecutionEngine`; `BackgroundWorkerService` runs
EP-033 workflows through EP-030's `PlanExecutionEngine`), so this
ordering silences both new-work triggers (REST, then Scheduler) before
draining the Background Worker Service's own, potentially
longer-running, already-accepted work. `src/bootstrap.py`'s
`shutdown()` required only a docstring update -- its body already
delegated unconditionally to `RuntimeService.shutdown()`, so the
widened behavior reached it automatically; `self._scheduler_service`
is deliberately still not nulled afterward (Owner Decision D3),
since `SchedulerService` remains a fully usable object once its tick
loop is stopped. No CLI/REST action was added for the new capability
(Owner Decision D1); the join timeout is a fixed, unconfigurable
5-second class constant, not a new `scheduler.*` configuration key
(Owner Decision D4).

Owner Decisions D1-D4 were all confirmed correctly implemented with
zero findings against their literal text during STEP 3, checked
against a `git diff` taken against the exact pre-STEP-1 baseline
commit rather than merely against the STEP 2 report. Every
explicitly-protected file (`src/core/scheduler/*.py`,
`scheduler_module.py`, `runtime_module.py`,
`background_worker_service.py`, `rest_api_server.py`,
`execution/engine.py`, `config/config.yaml`, `requirements.txt`,
`pyproject.toml`, `tests/EP059/test_runtime.py`) was independently
confirmed byte-identical to that baseline. STEP 3 identified exactly
two further findings, both non-blocking WARNINGs:

1. `tests/EP060/test_runtime_lifecycle.py`'s
   `_stop_scheduler_tick_loop_for_test_cleanup()` docstring made a
   present-tense claim -- "`SchedulerService` exposes no public method
   to stop its tick loop" -- that EP-061 made false. STEP 4 updated
   the docstring only; no `assert_*` line in that file was touched.
2. `EP061_DESIGN.md`'s evidence citation for "no executor blocks the
   tick thread" overstated that all four executors use
   `subprocess.Popen()`; independent re-reading of
   `src/core/execution/executors/*.py` during the audit found that
   three do (`process_executor.py`, `python_executor.py`,
   `file_executor.py`) while the fourth (`url_executor.py`) uses the
   standard library's `webbrowser.open()` -- also non-blocking, but a
   different mechanism. STEP 4 corrected the wording everywhere it
   appeared in the design document, preserving the architectural
   conclusion the evidence actually supports (none of the four
   executor paths causes the shutdown timeout to bound arbitrary,
   long-running external execution).

Tests: EP-061 62/0/0, covering `SchedulerService.shutdown()` in
isolation (never-started, already-running, idempotent, `wait=False`,
manual `run()` still working afterward, genuine multi-threaded
concurrent-shutdown race-safety, and a whitebox identity-guard
regression test), the widened `RuntimeService.shutdown()` (all-`None`
defaults; a real, running `SchedulerService` actually stopped;
REST-API-then-Scheduler-then-Background-Workers ordering verified via
call-order-recording proxies wrapping real objects; idempotency; a
lock-scope regression guard proving `status()` is never blocked by an
in-progress `shutdown()`), real end-to-end `Bootstrap` wiring (tick
loop actually starts on `initialize()` and stops on `shutdown()`,
`scheduler_service` reference identity-preserved across `shutdown()`,
repeated-shutdown and uninitialized-shutdown safety), and
public-surface guards confirming `SchedulerService` gained exactly one
new public method while `SchedulerModule`'s eight CLI actions and
`RuntimeModule`'s two CLI actions are both unchanged. Full regression:
EP-060 65/0/0, EP-059 93/0/0, EP-034 113/0/0, EP-035 143/0/0, EP-037
87/0/0 -- all independently reproduced exactly at STEP 2, STEP 3, and
STEP 4 (STEP 4's two documentation corrections touched no assertion,
so every figure is identical across all three steps). Full repository
regression: 6838 passed / 0 failed / 3 skipped (skips pre-existing,
environment-gated, confirmed present and unmodified in the pre-EP-061
baseline commit).

### EP-060 — Jarvis Operating System

STEP 1 (Architecture Discovery & Design), STEP 2 (Implementation &
Testing), STEP 3 (Architecture Audit), and STEP 4 (Finalization) all
complete. EP-060 is marked **COMPLETE / AUDIT PASSED, NO BLOCKING
FINDINGS** -- STEP 3 identified one non-blocking WARNING and zero
blocking findings; STEP 4 resolved it (see below) rather than leaving
it open, since resolving it required no design or scope change, only
synchronizing one stale test assertion with the already-approved
EP-060 contract -- see
`docs/architecture/audits/EP060_ARCHITECTURE_AUDIT.md`. Full design,
including Owner Decisions D1-D6: `docs/architecture/designs/
EP060_DESIGN.md`.

EP-060's roadmap entry ("Jarvis Operating System") had no functional
specification anywhere in the repository beyond Phase 10's own
one-sentence goal, shared with EP-059. STEP 1 found no textual anchor
naming a specific EP-060 mechanism, but did find a real, code-verified
gap: `Bootstrap.shutdown()` stopped only the REST API Server, never
the Background Worker Pool, and the Scheduler auto-starts its own tick
loop by default (`scheduler.enabled`/`scheduler.auto_start` both
default `true` in `config/config.yaml`) with no public method to stop
it at all -- directly correcting EP-059 Owner Decision D4's premise
that Scheduler is never auto-started as a side effect of
`initialize()`. STEP 1 recommended Owner Decision D1 = "Candidate A":
widen EP-059's `RuntimeService`/`RuntimeModule` from a read-only
introspection surface into a small, additive lifecycle control plane,
rather than build a new registry (already built by EP-056's
`CapabilityRegistryModule`), a generalized task queue (would require
modifying EP-036's own core file), or an event-driven design (the
existing `orchestrator.started`/`orchestrator.stopped` EventBus hooks
have zero subscribers and are never even published by the running
application today).

Built by widening `src/services/runtime_service.py` (`RuntimeStatus`
gains `scheduler_active`/`scheduler_jobs_registered`, both defaulted
for backward compatibility with every EP-059 constructor/dataclass
call site; `RuntimeService` gains exactly one new public method,
`shutdown() -> RuntimeShutdownReport`, coordinating REST API Server
then Background Worker Service shutdown, in that order, reusing only
their own already-existing, already-idempotent `stop()`/`shutdown()`
methods -- no new stop logic of its own) and `src/modules/
runtime_module.py` (status formatting gains a Scheduler line; still
exposes exactly `status`/`help` -- Owner Decision D3, no CLI/REST
`runtime shutdown` action). In `src/bootstrap.py`: one new
`_scheduler_service` attribute plus public property (Owner Decision
D6), promoted from a previously-discarded local variable inside
`_build_command_router()`; the existing `RuntimeService(...)`
construction site widened with `scheduler_service=self.
_scheduler_service`; and `shutdown()`'s existing body replaced (Owner
Decision D2 -- the first non-purely-additive touch to this file across
every EP's own history, disclosed and approved rather than assumed)
to delegate to `RuntimeService.shutdown()`, with a fallback for when
`RuntimeService` was never built, now also nulling
`background_worker_service` (a new, symmetric postcondition alongside
the pre-existing `rest_api_server` one). `self._scheduler_service` is
deliberately left untouched by `shutdown()` -- Owner Decision D5:
`src/services/scheduler_service.py` (EP-011) was not modified;
Scheduler is observed, not controlled, in v1.

Owner Decisions D1-D6 were all confirmed correctly implemented with
zero findings against their literal text during STEP 3. The STEP 3
audit identified exactly one further finding, a non-blocking WARNING:
`tests/EP059/test_runtime.py::_test_service_exposes_only_status`
asserted `RuntimeService`'s public method list equals `["status"]` --
an EP-059 Owner-Decision-D5 guard assertion that, by construction,
could not survive any future, legitimate widening of that surface, and
had therefore begun (correctly) failing once EP-060's approved
`shutdown()` method existed. STEP 3 classified this as an obsolete
historical guard, not an EP-060 defect, since every other,
compatibility-relevant assertion in that file (covering the original
four constructor arguments, the original nine `RuntimeStatus` fields,
`RuntimeModule` CLI dispatch, and real-`Bootstrap` wiring) continued to
pass unmodified. STEP 4 updated the one assertion to `["shutdown",
"status"]`, with a docstring explaining the change and citing the
approved contract it now matches -- no test was weakened, skipped, or
deleted; `tests/EP059/test_runtime.py`'s other 92 assertions were left
completely untouched.

Tests: EP-060 65/0/0, covering `RuntimeService`'s widened constructor/
`status()` (backward compatibility with the original four-argument
call shape; real, unmodified `SchedulerService` observed correctly
under both `scheduler.auto_start: true` and `false`;
`scheduler_jobs_registered` reflecting real registered jobs),
`shutdown()` in isolation (all-`None` dependencies never raising; a
real `RestApiServer` genuinely stopped; a real
`BackgroundWorkerService` genuinely signaled to shut down; the
disclosed, pinned `BackgroundWorkerService.status()` post-shutdown
limitation, asserted explicitly rather than silently "fixed";
idempotency across two consecutive calls; REST-API-before-
Background-Workers ordering, verified via call-order-recording
proxies), the `{status, shutdown}`/`{status, help}` public-surface
guarantees, `RuntimeModule` status formatting, and real end-to-end
`Bootstrap` wiring/shutdown (scheduler_service property population,
object-identity confirmation that `RuntimeService` observes the exact
live `SchedulerService` Bootstrap's own property exposes, `runtime
status` reflecting Scheduler over a real `CommandRouter` dispatch, a
full `initialize()` -> `shutdown()` cycle genuinely stopping the REST
API Server and Background Worker Service, both properties nulled
afterward, a second `shutdown()` call remaining safe, `shutdown()`
remaining safe even when `initialize()` was never called, and
Scheduler's own property remaining populated and identity-unchanged
after `shutdown()`). Full regression: EP-059 93/0/0 (after the STEP 4
synchronization above), EP-036 101/0/0, EP-036-STEP2 48/0/0,
EP-036-STEP3 53/0/0, EP-043 83/0/0 -- all independently reproduced
exactly at STEP 2, STEP 3, and STEP 4. `src/services/
scheduler_service.py`, `src/core/scheduler/scheduler.py`,
`src/core/scheduler/job.py`, `src/core/scheduler/job_registry.py`,
`config/config.yaml`, and `requirements.txt` are all confirmed
byte-identical/unmodified by EP-060 (independently re-hashed during
STEP 3 and reconfirmed unchanged at STEP 4).

### EP-059 — Distributed Runtime

STEP 1 (Architecture Discovery & Design), STEP 2 (Implementation &
Testing), STEP 3 (Architecture Audit), and STEP 4 (Finalization) all
complete. EP-059 is marked **COMPLETE / AUDIT PASSED, NO BLOCKING
FINDINGS** -- STEP 3 identified three non-blocking, informational
findings and zero blocking findings; the owner reviewed each
individually and directed STEP 4 to leave all three unchanged, since
none violated `EP059_DESIGN.md` or any approved Owner Decision
(D1-D6) -- in particular, Finding 3 (no `runtime.enabled` config key)
is the literal, explicit outcome of approved Owner Decision D6, not
an oversight -- see `docs/architecture/audits/EP059_ARCHITECTURE_AUDIT.md`
Sections 17-18. Full design, including Owner Decisions D1-D6 and the
two owner-approved documentation clarifications (added during STEP
2): `docs/architecture/designs/EP059_DESIGN.md`.

EP-059's roadmap entry ("Distributed Runtime") had no functional
specification anywhere in the repository beyond Phase 10's own
one-sentence goal, and no prior EP anchored a multi-process or
networked runtime concept. STEP 1 recommended Owner Decision D1 =
"Candidate A": a new, additive, read-only `RuntimeService`/
`RuntimeModule` pair that aggregates already-existing, already-public
facts -- `RestApiServer.is_running`/`.host`/`.port` (EP-043),
`BackgroundWorkerService.status()` (EP-036), and `InteractiveShell`
presence -- plus process PID/uptime via the standard library only,
into one `RuntimeStatus` snapshot.

Built as two new files, `src/services/runtime_service.py`
(`RuntimeStatus`, a small, inline, frozen dataclass -- Owner Decision
D3, no new `src/core/runtime/` package -- and `RuntimeService`, whose
only public method is `status()`) and `src/modules/runtime_module.py`
(`RuntimeModule`, the `"runtime"` CLI namespace -- Owner Decision D2 --
exposing exactly two actions, `status` and `help`, and no control
action of any kind -- Owner Decision D5). Registered in
`src/bootstrap.py` at the true end of `initialize()` -- after
`_build_command_router()` (which assigns `_background_worker_service`)
has already returned and `_shell`/`_rest_api_server` have also
already been assigned -- so `RuntimeService` always observes the
final, live references, never an early or stale `None`. No Scheduler
or Telegram status was added (Owner Decision D4); no
`runtime.enabled` config key was added (Owner Decision D6). `runtime
status` becomes reachable over the existing REST API with zero new
endpoint code, through the already-existing, unmodified
`ApiRouter`/`RestApiServer` forwarding path.

Owner Decisions D1-D6 were all confirmed correctly implemented with
zero findings against their literal text during STEP 3. The STEP 3
audit identified three further, non-blocking findings, none
security- or disclosure-related: (1, LOW, informational)
`uptime_seconds` measures time since `Bootstrap.__init__()`, not
since `initialize()` completes -- a deliberate, documented choice; (2,
LOW, informational) `RuntimeModule` silently ignores trailing
arguments to `status`/`help` rather than returning a usage error --
consistent with these actions taking no parameters; (3, LOW,
informational) no `runtime.enabled` config key exists, so the
subsystem cannot be disabled without a code change -- the explicit,
approved outcome of Owner Decision D6. Owner Decision: the owner
reviewed all three findings individually and directed that none
required remediation, since each was either a deliberate design
choice consistent with `EP059_DESIGN.md` or the literal, approved
result of an Owner Decision. Zero code, test, or configuration change
was made during STEP 4.

Tests: EP-059 93/0/0, covering `RuntimeService.status()` in isolation
(all-`None` dependencies, real `RestApiServer`/`BackgroundWorkerService`/
`InteractiveShell` instances, PID, uptime monotonicity, task-count
changes after a real `submit()`), a dedicated field-wiring mutation
guard, `RuntimeModule` CLI behavior, `CommandRouter` dispatch
equivalence, the read-only/no-control-surface guarantee, real
`Bootstrap` end-to-end wiring, construction-ordering identity and
behavioral checks, REST command-dispatch compatibility through the
existing, unmodified `ApiRouter`/`RestApiServer` path (no new
endpoint), and regression guards for `system status`/`/health`. Five
distinct mutation tests (one field-wiring swap, one stale-`None`
Bootstrap-wiring mutation, one silent-unknown-action mutation, one
hardcoded-boolean mutation applied independently during the audit,
and one inverted-shell-active-logic mutation applied during STEP 4),
each fully restored (byte-identical checksums reconfirmed after
each), were all independently caught. Full regression suites EP-036
101/0/0, EP-036-STEP2 48/0/0, EP-036-STEP3 53/0/0, EP-043 83/0/0,
EP-033 182/0/0, EP-034 113/0/0, EP-035 143/0/0, EP-037 87/0/0 were
independently reproduced exactly at STEP 2, STEP 3, and STEP 4.
`src/core/api/rest_api_server.py`, `api_router.py` (EP-043),
`src/services/background_worker_service.py`,
`src/core/background_workers/background_worker_pool.py` (EP-036),
`src/core/shell.py`, `src/core/command_router.py`,
`src/modules/background_worker_module.py`, and `config/config.yaml`
are all confirmed byte-identical/unmodified by EP-059.

### EP-058 — Autonomous Planning

STEP 1 (Architecture Discovery & Design), STEP 2 (Implementation &
Testing), STEP 3 (Architecture Audit), and STEP 4 (Finalization) all
complete. EP-058 is marked **COMPLETE / AUDIT PASSED, NO BLOCKING
FINDINGS** -- STEP 3 identified two non-blocking, informational
findings and zero blocking findings; the owner reviewed both and
directed STEP 4 to correct the one that was documentation-only
(Finding 1) and acknowledge the other with no action, exactly as its
own original recommendation already advised (Finding 2) -- see
`docs/architecture/audits/EP058_ARCHITECTURE_AUDIT.md` Sections
17-20. Full design, including Owner Decisions D1-D3 and the Owner
Approval Checklist (added during STEP 4):
`docs/architecture/designs/EP058_DESIGN.md`.

Like EP-054/EP-055/EP-056/EP-057, EP-058's roadmap entry ("Autonomous
Planning") was a bare title with no functional specification beyond
Phase 9's shared, one-sentence goal. STEP 1 disclosed this gap and
found an unusually strong anchor: an entire, already-complete
ten-Engineering-Package chain (Phase 4 "Agent Framework", EP-028-032,
and Phase 5 "Workflow Automation", EP-033-037), every package of
which explicitly, repeatedly declares in its own docstring that it
performs no AI reasoning and defers that to a named-but-unbuilt
future concept. `DefaultAgentProvider.execute()` (EP-028) returns, on
every real call, the literal runtime message "No Planner/Reasoning
Engine is registered yet (future EP)"; `PlanningProvider`'s own
module docstring (EP-029) explicitly names "a future AI-/LLM-backed
planning strategy... an obvious, natural extension point for this
abstraction" as the reason it implements only one, deterministic
provider. STEP 1 recommended Owner Decision D1 = "Candidate A": a
new, additive `AIPlanningProvider` implementation of the existing
`PlanningProvider` abstraction, registered alongside -- never
replacing -- the deterministic `DefaultPlanningProvider`.

Built as one new file,
`src/core/planning/ai_planning_provider.py` -- `AIPlanningProvider`
reasons about a request's meaning using an AI provider (EP-014/015,
reached only through `ProviderManager.get_current()` ->
`AIProvider.ask()` directly, the same deliberate bypass of
`AIService`'s Conversation/Context/Prompt Engine pipeline
`PromptOptimizerModule` (EP-055) already established), choosing only
from the exact same, already-real `(subsystem, action)` vocabulary
`DefaultPlanningProvider`'s own `_KEYWORD_RULES` table already
recognizes -- derived programmatically at import time, never
hardcoded, so the two providers remain genuine, interchangeable
substitutes over the identical action space. Registered via
`PlanningManager`'s already-existing, generic `register_provider()`
method (EP-029, unmodified) at the existing Planning construction
site in `src/bootstrap.py` -- one new import, one new comment block,
and one new line inside the pre-existing `try`/`except PlanningError`
block, with that block's original structure fully preserved.
`planning.default_provider` remains `"planning"` (Owner Decision D1)
-- an operator must explicitly run `planning use ai` (or set
`planning.default_provider: "ai"`) to select the new provider. No
`top_k`/`threshold`-equivalent tuning was added (Owner Decision D2:
no additional cost/latency safeguard beyond the existing `planning
use ai` action's own plain result); no new configuration key was
added (Owner Decision D3: no `max_tokens` value -- relies on the
active AI provider's own existing default). Zero new CLI action was
needed -- `planning use`/`providers`/`plan` already work generically
for any registered provider. Introduces no new backend Protocol,
Manager, or Engine -- composes only `ProviderManager.get_current()`/
`AIProvider.ask()` (EP-014/015) and `PlanningProvider`'s own
already-existing abstract contract (EP-029), both unmodified.

Owner Decisions D1-D3 were all confirmed correctly implemented with
zero findings against their literal text during STEP 3. The STEP 3
audit identified two further, non-blocking findings, neither
security- or disclosure-related: (1, LOW, informational)
`EP058_DESIGN.md`'s own prose described `DefaultPlanningProvider`'s
keyword table as having "nine" entries, when the actual count is
seventeen keyword rules collapsing to eight unique `(subsystem,
action)` pairs after deduplication -- a prose miscount with zero
effect on the implementation, which derives its menu programmatically
rather than from any hardcoded count; (2, LOW, informational) a
mutation causing an unhandled exception partway through the EP-058
test suite's own `run()` method prevents subsequent test methods from
executing -- a characteristic shared by every EP's own pre-existing
`BaseTest`/`TestRunner` convention, not specific to EP-058. Owner
Decision: the owner directed Finding 1 be corrected via a
documentation-only edit to `EP058_DESIGN.md` (four passages,
"nine" -> "seventeen ... eight unique pairs"), and Finding 2 be
acknowledged with no action, exactly as its own original
recommendation already advised (fixing it would require a separate,
cross-cutting change to shared testing infrastructure outside any
single EP's scope). Zero code, test, or configuration change was made
during STEP 4.

Tests: EP-058 110/0/0, covering the reply-parsing helpers directly
(well-formed, messy/bulleted/numbered formatting, off-menu-pair
rejection per this project's Unknown API Policy applied to AI output,
deduplication, empty-reply fallback, `max_steps` truncation), the
provider in isolation against a real `ProviderManager` with a fake AI
backend (faking only the one genuine external network dependency
this EP introduces, never an in-repo component), `PlanningManager`
compliance (registration, duplicate-name rejection, listing),
non-interference with the deterministic provider, five real, enabled
`Bootstrap` -> `CommandRouter` -> `PlanningService` -> `PlanningEngine`
-> `PlanningManager` -> `AIPlanningProvider` -> `ProviderManager`
end-to-end tests (including the real no-AI-provider-configured
failure path and a real fake-backend success path, injected into the
already-registered provider's own real, shared `ProviderManager` --
never a second, duplicate registration), and architecture-compliance
import scans. Full regression suites EP-028 214/0/0, EP-029 197/0/0,
EP-030 179/0/0, EP-031 212/0/0, EP-032 176/0/0, EP-033 182/0/0,
EP-034 113/0/0, EP-035 143/0/0, EP-036 101/0/0, EP-055 64/0/0, EP-056
62/0/0, EP-057 41/0/0 were independently reproduced exactly, both
before and after the STEP 4 documentation-only edit.
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
`conversation.py`, `conversation_manager.py`, `context_manager.py`
(EP-014/015/016/018), `src/services/ai_service.py`,
`src/core/memory/`, `src/core/long_term_memory/`,
`src/core/knowledge/`, `src/core/semantic/`,
`src/core/context_compression/` (EP-013/023/024/025/026/027),
`src/core/command_router.py`, `config/config.yaml`,
`src/services/planning_service.py`, and `src/modules/planning_module.py`
are all confirmed byte-identical/unmodified by EP-058, both before
and after the STEP 4 documentation-only edit.

### EP-057 — Memory Optimization

STEP 1 (Architecture Discovery & Design), STEP 2 (Implementation &
Testing), STEP 3 (Architecture Audit), and STEP 4 (Finalization) all
complete. EP-057 is marked **COMPLETE / PASS AFTER REMEDIATION** --
STEP 3's first-pass verdict was **AUDIT PASSED WITH FINDINGS** (three
non-blocking findings, zero blocking). Unlike EP-054, where two
comparable findings were left documented and unfixed, the owner
reviewed EP-057's findings and directed that all three be closed
during STEP 4; the STEP 3 audit document was then updated in place
with a dated remediation section recording each fix and its
independent verification. Final verdict: **PASS AFTER REMEDIATION**,
zero open findings -- see
`docs/architecture/audits/EP057_ARCHITECTURE_AUDIT.md` Sections 15-20.
Full design, including Owner Decisions D1-D4 (Section 20) and the
Owner Approval Checklist (added during STEP 4):
`docs/architecture/designs/EP057_DESIGN.md`.

Like EP-054/EP-055/EP-056, EP-057's roadmap entry ("Memory
Optimization") was a bare title with no functional specification
beyond Phase 9's shared, one-sentence goal. STEP 1 disclosed this gap
and found the strongest anchor of any Phase-9 EP so far:
`CompressionEngine.compress_query()`/`compress_semantic_results()`
(EP-027) were already fully built and fully tested but had exactly
zero production callers anywhere in the repository, and
`src/bootstrap.py`'s own construction-site comment already named this
exact situation, describing the underlying Semantic Search access as
"used only by `compression`'s future callers via `compress_query()`,
never by the CLI commands wired here." STEP 1 recommended Owner
Decision D1 = "Candidate A": expose that already-built,
already-tested method as a new, on-demand `compression query
"<text>"` command, finally giving it a real caller.

Built as one new `query()` method on `CompressionService`
(`src/services/context_compression_service.py`) -- a one-line forward
to `CompressionEngine.compress_query()`, introducing no new
compression or semantic-search logic of its own -- and one new
`query` action on `ContextCompressionModule`
(`src/modules/context_compression_module.py`), dispatched through the
*existing*, unmodified `CommandRouter.dispatch()`. Introduces no new
backend Protocol, Manager, Engine, or Provider (Owner Decision D1) --
`compression query` instead composes already-existing, unmodified
components directly, read-only: `CompressionEngine.compress_query()`
(EP-027), which itself reaches `SemanticEngine.search()` (EP-026)
over Knowledge Base (EP-024) and Long-Term Memory (EP-025) content.
The EP-016 Conversation Engine, EP-018 Context Loader, EP-024
Knowledge Base, EP-025 Long-Term Memory, EP-026 Semantic Search, and
EP-027 Context Compression's own core logic are never modified or
redesigned. No `top_k`/`threshold` CLI arguments are exposed --
`compression query` relies on the existing `semantic.*` configuration
defaults (Owner Decision D2). No separate AI-provider privacy gate
exists, since `compression query` never calls an AI provider and,
independently confirmed during the architecture audit, discloses
strictly less than the already-existing `semantic search` command
already discloses today (Owner Decision D3). Extends the existing
`compression` `CommandModule` namespace rather than creating a new one
or extending `ltm` (Owner Decision D4). No `AgentEngine` subsystem
registration exists in v1. No new dependency was introduced. Required
zero `src/bootstrap.py` construction-ordering change and zero new
configuration key, since `CompressionEngine` was already constructed
with a live `SemanticEngine` wherever Semantic Search is available.

Owner Decisions D1-D4 were all confirmed correctly implemented with
zero findings against their literal text during STEP 3. The STEP 3
audit identified three further, non-blocking findings, none security-
or disclosure-related: (1, LOW, informational) `src/bootstrap.py`'s
own construction-site comment became factually stale the moment
EP-057 gave `compress_query()` a real CLI caller; (2, LOW) the
registered test suite defined a `context_compression.enabled: false`
configuration fixture but never actually used it, and a test named
for that scenario instead tested a different code path ("no
`SemanticEngine` configured"), because `compress_query()` checks for
a `None` `SemanticEngine` before ever reaching the
`enabled`/provider-selection check; (3, informational)
`EP057_DESIGN.md`, approved during STEP 1, had been delivered to the
owner but never committed into the repository tree. Owner Decision:
the owner directed a STEP 4 fix for all three findings -- rather than
leaving them documented and unfixed, as EP-054's STEP 4 did with its
own two non-blocking findings. Fixed by: (1) a comment-only, two-line
edit to `src/bootstrap.py`, independently confirmed to touch zero
executable statements; (2) renaming the misleadingly-named test and
adding a new test that exercises the actual `context_compression.
enabled: false` gate together with a real `SemanticEngine`,
independently confirmed via a dedicated mutation test to genuinely
detect a simulated gate bypass that would have passed through the
original suite entirely undetected; (3) committing
`EP057_DESIGN.md`'s approved content to
`docs/architecture/designs/EP057_DESIGN.md`, restoring parity with
EP-054/EP-055/EP-056's own design documents.

Tests: EP-057 41/0/0 (35 original plus 6 added during STEP 4
specifically to close finding (2) above), covering
argument-shape/gate/dispatch behavior, a real, unmodified
`SemanticEngine`/`KnowledgeService` integration (not a fake) for the
one genuine cross-subsystem call this EP makes, and three real,
enabled `Bootstrap` -> `CommandRouter` -> `CompressionService` ->
`CompressionEngine` -> `SemanticEngine` -> `KnowledgeService`
end-to-end tests. Full regression suites EP-056 62/0/0, EP-055
64/0/0, EP-054 76/0/0, EP-053 58/0/0, EP-052 135/0/0, EP-051 105/0/0,
EP-050 112/0/0, plus EP-024 Knowledge Base 407/0/0, EP-025 Long-Term
Memory 442/0/0, EP-026 Semantic Search 204/0/0, and EP-027 Context
Compression 229/0/0 were independently reproduced exactly, both
before and after the STEP 4 fixes.
`src/core/context_compression/compression_engine.py`,
`compression_manager.py`, `compression_provider.py`,
`compression_result.py` (EP-027), `src/core/semantic/semantic_engine.py`
(EP-026), `src/core/long_term_memory/`,
`src/services/long_term_memory_service.py` (EP-025),
`src/core/knowledge/`, `src/services/knowledge_service.py` (EP-024),
`src/core/memory/`, `src/services/memory_service.py` (EP-013/023),
`src/core/ai/conversation.py`, `conversation_manager.py`,
`context_manager.py` (EP-016/018), `src/core/command_router.py`, and
`config/config.yaml` are all confirmed byte-identical/unmodified by
EP-057, both before and after the STEP 4 fixes; `src/bootstrap.py`'s
only change across all of EP-057 is the single, comment-only edit
described above. Separately, and unrelated to EP-057, two pre-existing
EP-048 (Wake Word) test failures were independently investigated
during STEP 3 and conclusively proven pre-existing and
environment-only (the `openwakeword` package is not installable in
the audit environment) by reproducing the identical failure against a
separate, pristine copy of the repository containing zero EP-057
code.

### EP-056 — Capability Registry

STEP 1 (Architecture Discovery & Design), STEP 2 (Implementation &
Testing), STEP 3 (Architecture Audit), and STEP 4 (Finalization) all
complete. EP-056 is marked **COMPLETE / PASS AFTER REMEDIATION** --
STEP 3's first-pass verdict was **AUDIT FAILED (ONE BLOCKING
FINDING)**: a HIGH-severity defect made `capability list`/`capability
inject` completely non-functional in real, production `Bootstrap`
wiring. The owner reviewed the finding and approved fixing it during
STEP 4 (Owner Decision D8); the STEP 3 audit document was then
updated in place with a dated remediation section recording the fix
and its independent verification. Final verdict: **PASS AFTER
REMEDIATION**, zero open findings -- see
`docs/architecture/audits/EP056_ARCHITECTURE_AUDIT.md` Sections 15-18.
Full design, including Owner Decisions D1-D7 (Section 20) and D8
(Section 17): `docs/architecture/designs/EP056_DESIGN.md`.

Like EP-054/EP-055, EP-056's roadmap entry ("Capability Learning") was
a bare title with no functional specification beyond Phase 9's
shared, one-sentence goal. STEP 1 disclosed this gap and found the
strongest textual anchor of any Phase-9 EP so far:
`PromptBuilder.append_capabilities()`'s own docstring, already
written during EP-017, reads "reserved for the future Capability
Registry" verbatim. STEP 1 recommended Owner Decision D1 =
"Candidate A": an on-demand Capability Registry composing already-
declared Plugin capability data (EP-010) plus bare `CommandRouter`
namespace names, finally giving that seam real content.

Built as a new `capability` `CommandModule`
(`src/skills/capability_registry/skill.py`) providing `list` (compose
a summary of every currently running plugin's declared capability
tags plus the bare list of registered built-in commands) and `inject
<text>` (pass that same summary through the Prompt Engine's existing,
previously-unused `PromptManager.build(capabilities=...)` seam
together with `<text>`, returning the assembled prompt for
inspection -- never calling an AI provider) -- plus `help`, dispatched
through the *existing*, unmodified `CommandRouter.dispatch()`.
Introduces no new backend Protocol (Owner Decision D1) -- composes
`PluginService.running_plugins()` and `CommandRouter.module_names`
directly, read-only. The EP-010 Plugin system and EP-017 Prompt
Engine are never modified or redesigned; `PromptManager`/
`PromptBuilder` are called only through their existing, unmodified
public API. Gated by `capability_registry.enabled` (default `false`,
re-checked on every dispatched action). No separate AI-provider
privacy gate exists, since neither action ever calls an AI provider
(Owner Decision D3). No `AgentEngine` subsystem registration exists in
v1. No new dependency was introduced.

Owner Decisions D1-D7 were all confirmed correctly implemented with
zero findings against their literal text during STEP 3. However, the
STEP 3 audit's direct exercise of the real, fully-wired `Bootstrap`
with `capability_registry.enabled: true` -- a step beyond what the
registered test suite performed -- found that `src/bootstrap.py`
passed `CommandRouter.module_names` (a `@property`, evaluated eagerly
at construction time) where `CapabilityRegistryModule`'s own
documented constructor contract required a live, zero-argument
callable. This caused a 100%-reproducible `TypeError` on every single
call to `capability list` or `capability inject`, surfaced to the
end user only as a generic "Internal error" message. `capability
help` was unaffected. No security, disclosure, or gate-bypass issue
was involved -- this was a pure availability defect. The registered
51-assertion test suite did not catch it because its fake
`module_names` collaborator correctly implemented the *documented*
interface; only a real, enabled `Bootstrap` exercise could surface the
mismatch between that documentation and what `bootstrap.py` actually
supplied. Owner Decision D8 (approved, option (a)) directed a STEP 4
fix: a single-line, behavior-preserving change
(`module_names=router.module_names` -> `module_names=lambda: router.
module_names`) confined entirely to `src/bootstrap.py`, requiring zero
change to `src/skills/capability_registry/skill.py`,
`CommandRouter`, `PluginService`, or `PromptManager`. The fix was
independently verified against a reverted, pre-fix scratch copy
(proving new tests genuinely catch the original defect, not merely
passing vacuously) and against the real, fixed code's before/after
responses through the actual `Bootstrap` -> `CommandRouter` ->
`CapabilityRegistryModule` path.

Tests: EP056 62/0/0 (51 original + 11 added in STEP 4, three new test
methods specifically exercising the real, enabled `Bootstrap` wiring
end-to-end -- not fakes -- to prevent this exact wiring defect from
returning), covering argument-shape/gate/dispatch behavior against
fake `PluginService`/`module_names` stand-ins, a real, unmodified
`PromptManager` integration for `capability inject` (Owner Decision
D6), and the real-`Bootstrap` regression guard. Full regression
suites EP-055 64/0/0, EP-054 76/0/0, EP-053 58/0/0, EP-052 135/0/0,
EP-051 105/0/0, EP-050 112/0/0 were independently reproduced exactly,
both before and after the STEP 4 fix. `src/core/plugins/plugin.py`,
`plugin_manifest.py`, `plugin_registry.py`, `plugin_loader.py`,
`plugin_discovery.py` (EP-010), `src/services/plugin_service.py`,
`src/core/ai/prompt.py`, `prompt_builder.py`, `prompt_manager.py`
(EP-017), `src/core/command_router.py`, `src/services/ai_service.py`,
and every prior skill (`desktop`/`browser`/`files`/`vision`/`reflect`/
`prompt`) are all confirmed byte-identical/unmodified by EP-056, both
before and after the STEP 4 fix.

### EP-055 — Prompt Optimizer

STEP 1 (Architecture Discovery & Design), STEP 2 (Implementation &
Testing), STEP 3 (Architecture Audit), and STEP 4 (Finalization) all
complete. EP-055 is marked **COMPLETE / PASS AFTER REMEDIATION** --
STEP 3's first-pass verdict was **AUDIT PASSED WITH FINDINGS** (one
non-blocking MEDIUM finding and one non-blocking LOW finding).
Unlike EP-054, where two comparable findings were left documented and
unfixed, the owner reviewed EP-055's findings and approved fixing
both during STEP 4 (Owner Decision D10); the STEP 3 audit document
was then updated in place with a dated remediation section recording
the fix and its independent verification. Final verdict: **PASS
AFTER REMEDIATION**, zero open findings -- see
`docs/architecture/audits/EP055_ARCHITECTURE_AUDIT.md` Sections 15-18.
Full design, including Owner Decisions D1-D9 (Section 20) and D10
(Section 17): `docs/architecture/designs/EP055_DESIGN.md`.

Like EP-054, EP-055's roadmap entry ("Prompt Optimizer") was a bare
title with no functional specification beyond Phase 9's shared,
one-sentence goal. STEP 1 disclosed this gap and surveyed the
already-built EP-017 Prompt Engine, recommending Owner Decision D1 =
"Candidate A": on-demand improvement of a prompt's or an existing
template's clarity/structure via one direct AI-provider call.

Built as a new `prompt` `CommandModule`
(`src/skills/prompt_optimizer/skill.py`) providing `optimize <text>` /
`optimize --template <name>` -- plus `help` -- dispatched through the
*existing*, unmodified `CommandRouter.dispatch()`. Introduces no new
backend Protocol (Owner Decision D1) -- composes
`ProviderManager`/`AIProvider` directly (via
`ProviderManager.get_current().ask()`, deliberately bypassing
`AIService`'s pipeline so an optimization request neither becomes a
new conversation turn nor recursively re-enters the very Prompt
Engine pipeline whose template input it is improving) and reads
(never writes -- Owner Decision D4, return-only in v1) the
already-reserved `paths.prompts` directory EP-017's `PromptBuilder.
load_template()` already establishes. The EP-017 Prompt Engine
(`Prompt`/`PromptBuilder`/`PromptManager`) itself is never modified or
called. Gated by `prompt_optimizer.enabled` (default `false`,
re-checked on every dispatched action), `prompt_optimizer.
max_input_size` (default 4000), and `prompt_optimizer.
min_seconds_between_calls` (default 30). No `AgentEngine` subsystem
registration exists in v1 (Owner Decision D5). No new dependency was
introduced.

Owner Decisions D1-D9 were all confirmed correctly implemented with
zero findings against their literal text during STEP 3. Two related,
non-blocking ordering findings were identified independently of the
Owner Decisions: (1, originally MEDIUM) the `--template` path
performed a real filesystem read and could disclose a template's
existence/emptiness/absolute path before the `prompt_optimizer.
enabled` gate was checked; (2, originally LOW) the `max_input_size`
cap check ran before the same gate, allowing that numeric config
value to be observed while disabled -- closely mirroring EP-054's own
previously-accepted Finding 2. In neither case did an AI-provider
call ever occur, and template content was never disclosed. Owner
Decision D10 (approved, option (a)) directed a STEP 4 fix: a minimal,
behavior-preserving reordering so `prompt_optimizer.enabled` is
checked before any filesystem access or config-value-dependent
message. The fix was independently verified against a reverted,
pre-fix scratch copy (proving the new tests genuinely catch the
original behavior, not merely passing vacuously) and against the real
code's before/after responses.

Tests: EP055 64/0/0 (52 original + 12 added in STEP 4 specifically to
prove the corrected gate ordering), covering argument-shape/gate/
rate-limit/resource-cap/dispatch behavior against fake
`ProviderManager` stand-ins plus real, temporary-directory-backed
template-file tests. Full regression suites EP-054 76/0/0, EP-053
58/0/0, EP-052 135/0/0, EP-051 105/0/0, EP-050 112/0/0 were
independently reproduced exactly, both before and after the STEP 4
fix. `src/core/ai/prompt.py`, `prompt_builder.py`, `prompt_manager.py`
(EP-017), `src/core/ai/context_manager.py`, `src/core/command_router.py`,
`src/core/ai/provider.py`, `provider_manager.py`,
`src/services/ai_service.py`, `src/core/agent/`, `src/core/planning/`,
`src/core/scheduler/`, and every prior skill (`desktop`/`browser`/
`files`/`vision`/`reflect`) are all confirmed byte-identical/unmodified
by EP-055, both before and after the STEP 4 fix.

### EP-054 — Self Reflection

STEP 1 (Architecture Discovery & Design), STEP 2 (Implementation &
Testing), STEP 3 (Architecture Audit), and STEP 4 (Finalization) all
complete. EP-054 is marked **COMPLETE / PASSED WITH FINDINGS** --
STEP 3's final verdict is **AUDIT PASSED WITH FINDINGS** (one
non-blocking MEDIUM finding and one non-blocking LOW finding,
documented and not fixed -- see below), not a clean, zero-finding
pass -- see `docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md`.
Full design, including Owner Decisions D1-D9 (Section 20):
`docs/architecture/designs/EP054_DESIGN.md`.

Unlike EP-050 through EP-053, EP-054's roadmap entry was a bare title
("Self Reflection") with no functional specification anywhere in the
repository beyond Phase 9's one-sentence, five-EP-wide goal. STEP 1
disclosed this gap explicitly and surveyed the existing architecture
(Conversation Engine, AI Provider Manager, Memory Manager, Agent
Framework's subsystem registry, Scheduler) to derive several
grounded candidate interpretations, recommending Owner Decision D1
= "Candidate A": on-demand session/conversation self-critique.

Built as a new `reflect` `CommandModule`
(`src/skills/reflection/skill.py`) providing `summary [count]` (ask
the configured AI provider to critique the last `count` messages of
the current conversation) and `recall [count]` (return previously
persisted critiques, most recent first) -- plus `help`, dispatched
through the *existing*, unmodified `CommandRouter.dispatch()` -- no
new dispatch mechanism, no Tool Engine change. Unlike
`desktop`/`browser`/`file`/`vision`, EP-054 introduces no new external
I/O surface and therefore no new backend Protocol (Owner Decision
D1) -- `ReflectionModule` instead composes three already-existing,
unmodified components directly via constructor injection:
`ConversationManager` (read-only -- `ReflectionModule` never appends
to or mutates a conversation), `ProviderManager`/`AIProvider` (via
`ProviderManager.get_current().ask()`, deliberately bypassing
`AIService`'s higher-level pipeline so a reflection request never
appends itself as a new turn in the very conversation being reflected
upon), and, optionally, `MemoryService` (only consulted when
`reflection.persist_to_memory` is enabled; `reflect recall` reports a
clear failure if persistence is requested but the Memory subsystem is
unavailable). v1 is strictly descriptive (Owner Decision D3): it
never autonomously changes any configuration, prompt, or other
component's behavior -- that remains explicitly reserved for later
Phase 9 EPs (Prompt Optimizer, Capability Learning, Autonomous
Planning) by the roadmap's own sequencing. No `Scheduler` integration
and no `AgentEngine.register_subsystem()` call exist in v1 (Owner
Decisions D5/D6 -- manual-only, `CommandModule` only). No new
dependency was introduced (Owner Decision D9's sibling finding in
Section 9 of the design).

Gated by `reflection.enabled` (default `false`, re-checked on every
dispatched action, matching `desktop.enabled`/`browser.enabled`/
`file.enabled`/`vision.enabled`'s own precedent), `reflection
.max_message_count` (default and cap: 20 -- an explicit `count`
argument exceeding it is refused, never silently reduced, mirroring
`vision.max_dimension`'s own "reject, never silently downscale"
convention), and `reflection.min_seconds_between_calls` (default 30
-- a simple, in-process rate limit bounding AI-provider cost from
rapid, repeated invocation; reset on restart, not a durable
cross-restart limit).

Owner Decisions D1-D9 are all confirmed correctly implemented, aside
from the two findings below: Candidate A scope, no new backend
Protocol (D1); no separate AI-provider/privacy gate beyond
`reflection.enabled` itself (D2); strictly descriptive output, no
autonomous effect on anything (D3); opt-in `MemoryService` persistence,
default `false` (D4); manual-only triggering, no `Scheduler`
integration in v1 (D5); no `AgentEngine` subsystem registration in v1
(D6); `max_message_count: 20`/`min_seconds_between_calls: 30` resource/
rate-limit defaults (D7); `CommandRouter` dispatch, no Tool Engine
redesign (D8); and no real-`AIProvider` integration test, since a live
provider call is not deterministic the way EP-053's real-Tesseract OCR
check was (D9).

Tests: **EP-054 76 passed / 0 failed / 0 skipped**, covering
argument-shape validation, the `reflection.enabled` gate (zero
downstream calls while disabled), `max_message_count` cap enforcement,
`min_seconds_between_calls` rate-limiting (using a fake, injected
clock, never a real `time.sleep()`), positive-path prompt/response
generation, negative cases (no provider available, provider raises an
error, empty conversation), `persist_to_memory` behavior, `help`/
unknown-action handling, `CommandRouter` dispatch equivalence, and
`Bootstrap` wiring -- all against fake `ConversationManager`/
`ProviderManager`/`MemoryService` stand-ins (Owner Decision D10's
sibling reasoning in the design: a real AI-provider call's
non-deterministic output makes it unsuitable for the primary,
always-green suite).

Full regression: **6339 passed / 2 failed / 3 skipped**. The 2
failures and 3 skips are the same, already-documented, pre-existing
EP-046/EP-048/EP-049 voice-stack/sandbox limitations recorded at
EP-053's own completion, independently re-verified during the STEP 3
audit and confirmed unrelated to, and unmodified by, EP-054.

**STEP 3 findings (documented, not fixed):**

1. **(MEDIUM, non-blocking)** `EP054_DESIGN.md`'s own Section 12
   explicitly committed to adding a real, non-fake `MemoryService`
   -backed test to the primary suite once Owner Decision D4 (opt-in
   Memory persistence) was approved. No such test exists in the
   registered suite -- every persistence-related test uses a fake
   `MemoryService` only. The STEP 3 audit independently built and ran
   a real `MemoryService`/`MemoryStore` integration probe and
   confirmed the actual integration (`reflect summary` persisting,
   `reflect recall` retrieving) works correctly end-to-end -- the
   finding is a test-coverage gap against a self-imposed design
   commitment, not a functional defect.
2. **(LOW, non-blocking)** `ReflectionModule._summary()`'s
   `max_message_count`-exceeded check currently runs *before* the
   `reflection.enabled` gate, so a caller can observe the configured
   cap's numeric value via an error message even while Self Reflection
   is disabled. The STEP 3 audit confirmed, using dummy
   `ConversationManager`/`ProviderManager` objects that raise on any
   call, that zero downstream calls occur in this case -- no gate or
   resource-limit bypass exists; only a non-secret, already-visible
   config value can be observed out of order.

Per the STEP 3 audit's own "record, do not fix" rule, and per this
STEP 4's instruction to write and update documentation only, no code
change was made to address either finding. See
`docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md` Section 15 for
full detail and evidence on both.

`src/core/command_router.py`, `src/core/tool/`,
`src/core/ai/provider.py`, `src/core/ai/provider_manager.py`,
`src/core/ai/conversation_manager.py`, `src/core/ai/conversation.py`,
`src/core/memory/`, `src/core/agent/`, `src/core/planning/`,
`src/core/scheduler/`, `src/services/ai_service.py`,
`src/services/memory_service.py`, and every Phase 7/8 skill
(`desktop`, `browser`, `files`, `vision`) are all confirmed unmodified
by EP-054.

### EP-053 — Vision Integration

STEP 1 (Architecture Discovery, Technology Evaluation & Design), STEP
2 (Implementation & Testing), STEP 3 (Architecture Audit), and STEP 4
(Finalization) all complete. EP-053 is marked **COMPLETE / PASSED
WITH FINDINGS** -- STEP 3's final verdict is **AUDIT PASSED WITH
FINDINGS** (one non-blocking MEDIUM finding, documented and not
fixed -- see below), not a clean, zero-finding pass -- see
`docs/architecture/audits/EP053_ARCHITECTURE_AUDIT.md`. Full design,
including Owner Decisions D1-D10 (Section 20):
`docs/architecture/designs/EP053_DESIGN.md`.

Built as a new `vision` `CommandModule` (`src/skills/vision/skill.py`)
providing local, read-only image interpretation -- `info` (image
metadata: width, height, format, color mode, file size) and `ocr`
(text extraction) -- plus `help`, dispatched through the *existing*,
unmodified `CommandRouter.dispatch()` -- no new dispatch mechanism, no
Tool Engine change. A new `VisionBackend` protocol
(`src/skills/vision/backend.py`) is the only interface `VisionModule`
depends on; `LocalVisionBackend` (`src/skills/vision/local_backend.py`)
is the sole real implementation, built on Pillow (image decoding) and
`pytesseract` (OCR, wrapping an external Tesseract binary). v1 is
local-only and CPU-only: no AI-provider/network path exists anywhere
in `src/skills/vision/`, and `src/core/ai/provider.py` is entirely
unmodified. Gated by `vision.enabled` (default `false`, re-checked on
every dispatched action) and an independent `vision.allowed_roots`
allow-list (empty blocks everything; no runtime coupling to
`file.allowed_roots`/`FileBackend`), plus resource limits
(`vision.max_file_size_mb`, `vision.max_dimension`) enforced inside
`LocalVisionBackend`. `info` never depends on the Tesseract binary
being installed (split availability, Owner Decision D8); only `ocr`
does.

Owner Decisions D1-D10 are all confirmed correctly implemented:
local-only scope/no AI-provider path (D1), `pytesseract` OCR engine
(D2), path-only image input (D3), independent path-safety model (D4),
`max_file_size_mb`/`max_dimension` resource limits (D5), CPU-only
operation (D6), `Pillow==12.1.1`/`pytesseract==0.3.13` dependency
approval (D7), split availability (D8), `CommandRouter` dispatch, no
Tool Engine redesign (D9), and fake-backend + real-Pillow testing with
real-Tesseract integration handled separately (D10).

Tests: **EP-053 58 passed / 0 failed / 0 skipped**, covering protocol
conformance and argument-shape/gate/path-safety/dispatch behavior
against a `_FakeVisionBackend`, plus real-Pillow filesystem/image
behavior (including resource-limit enforcement) against
`LocalVisionBackend`. A separate, intentionally unregistered
real-Tesseract OCR check (`tests/EP053/test_vision_ocr_integration.py`)
independently verified genuine end-to-end text recognition against a
freshly rendered image -- it is never imported by `test_vision.py`,
`test_module.py`, or `TestRegistry`.

Full regression: **6263 passed / 2 failed / 3 skipped**. The 2
failures and 3 skips are pre-existing EP-046/EP-048/EP-049
voice-stack/sandbox limitations (`openwakeword`/`tflite-runtime`
having no Linux wheel in this environment, and real-hardware-only
scenarios each EP's own design already documented as skippable),
independently re-traced to their root causes during the STEP 3 audit
and confirmed unrelated to, and unmodified by, EP-053.

**STEP 3 finding (MEDIUM, non-blocking, documented, not fixed):**
`LocalVisionBackend` currently enforces its `max_dimension` resource
limit *after* Pillow fully decodes the image (`image.load()`), rather
than before, as `EP053_DESIGN.md`'s own Owner Decision D5 specified.
The limit is still always enforced, and no oversized result is ever
returned to a caller -- the finding is a decode-cost-ordering
inefficiency, not a path-safety bypass, a limit that fails to apply,
or an unsafe result. Per the STEP 3 audit's own "record, do not fix"
rule, and per this STEP 4's explicit instruction not to modify source
code without an already-documented, approved remediation, no code
change was made to address this finding during STEP 4. See
`docs/architecture/audits/EP053_ARCHITECTURE_AUDIT.md` Section 15,
Finding 1, for full detail and evidence.

`src/core/command_router.py`, `src/core/tool/`,
`src/core/ai/provider.py`, `src/skills/desktop/`,
`src/skills/browser/`, and `src/skills/files/` are all confirmed
unmodified by EP-053.

### EP-052 — File Automation

STEP 1 (Architecture Discovery, Technology Evaluation & Design), STEP
2 (Implementation & Testing), STEP 3 (Architecture Audit with one
narrowly-scoped remediation), and STEP 4 (Finalization) all complete.
EP-052 is marked COMPLETE with verdict **PASS AFTER REMEDIATION** --
see `docs/architecture/audits/EP052_ARCHITECTURE_AUDIT.md`. Full
design, including Owner Decisions D1-D11 (Section 20):
`docs/architecture/designs/EP052_DESIGN.md`.

Built as a new `file` `CommandModule` (`src/skills/files/skill.py`)
providing 9 CRUD actions -- `list`, `exists`, `stat`, `read`, `write`,
`copy`, `move`, `mkdir`, `delete` -- plus `help`, dispatched through
the *existing*, unmodified `CommandRouter.dispatch()` -- no new
dispatch mechanism. A new `FileBackend` protocol
(`src/skills/files/backend.py`) is the only interface `FileModule`
depends on; `LocalFileBackend` (`src/skills/files/local_backend.py`)
is the sole real implementation, operating directly on the local
filesystem behind a layered security model: `file.enabled` (default
`false`, re-checked on every dispatched action), `file.allow_destructive`
(gating `move`/`delete`/overwrite separately from non-destructive
actions), `file.allowed_roots` (an explicit allow-list -- empty blocks
everything), `file.denied_paths` (excludes specific paths inside an
allowed root), path-traversal/absolute-path rejection, non-recursive
`delete`, and UTF-8-only file content.

Owner Decision D11 authorized one narrowly-scoped remediation during
the STEP 3 Architecture Audit: `src/core/command_router.py`'s command
tokenizer corrupted Windows-style backslash paths before they reached
`FileModule`; the minimal fix preserves them. This is the only source
file EP-052 modified outside `src/skills/files/`,

`src/bootstrap.py`, and `src/modules/test_module.py`.

Tests: EP-052 135/0/0 (`tests/EP052/test_file.py`) -- protocol
conformance and argument-shape/gate/path-safety/dispatch tests against
a `_FakeFileBackend`, plus real CRUD/overwrite/non-recursive-delete/
UTF-8 behavior against `LocalFileBackend` in a disposable
`tempfile.TemporaryDirectory()`, never the repository root or an
operator's home directory.

### EP-051 — Browser Automation

STEP 1 (Architecture Discovery, Technology Evaluation & Design), STEP
2 (Implementation & Testing), STEP 3 (Architecture Audit), and STEP 4
(Documentation Completion) all complete. EP-051 is marked COMPLETE
with verdict **PASS WITH FINDINGS** (one HIGH, three MEDIUM, three
LOW -- none blocking; see below and
`docs/architecture/audits/EP051_AUDIT.md` Section 17 for the full,
verbatim finding list). Full design:
`docs/architecture/designs/EP051_DESIGN.md` (including Section 21's
record of the twelve owner decisions, D1-D12). Full audit:
`docs/architecture/audits/EP051_AUDIT.md`.

Built as a new `browser` `CommandModule`
(`src/skills/browser/skill.py`) providing 15 actions -- `launch`,
`close`, `goto`, `back`, `forward`, `reload`, `title`, `current-url`,
`page-text`, `exists`, `click`, `type`, `clear`, `press`,
`screenshot` -- plus `help`, for controlled browser lifecycle,
navigation, observation, and single-element DOM interaction,
dispatched through the *existing*, unmodified
`CommandRouter.dispatch()` -- no new dispatch mechanism, no change to
`src/core/command_router.py`, `src/core/api/`, Telegram, `desktop/`
(the EP-044 PySide6 GUI client, a distinct, unrelated directory), or
`web/`. A new `BrowserBackend` protocol
(`src/skills/browser/backend.py`, 15 methods, exactly the v1 action
set) is the only interface `BrowserModule` depends on --
`PlaywrightBrowserBackend` (`src/skills/browser/playwright_backend.py`)
is the sole real implementation, built on Playwright's synchronous API
(Owner Decision D1). This replaced a previously-declared, unpinned
`selenium` dependency confirmed, by direct repository inspection, to
be entirely unused (zero imports anywhere in the project) --
`requirements.txt` now pins `playwright==1.62.0`, and the swap is a
from-scratch technology choice rather than a migration away from
working infrastructure, since nothing was ever built on Selenium.
Genuinely cross-platform by design (Owner Decision D11) -- no
`sys.platform`/OS-conditional branch exists anywhere in
`PlaywrightBrowserBackend`, unlike EP-050's own, deliberately
Windows-scoped `WindowsComputerUseBackend` -- though Windows remains
the intended v1 manual-verification target and no artificial
cross-platform complexity (extra config keys, per-OS test scaffolding)
was added.

`browser.enabled` defaults to `false` and is re-checked on every
dispatched action, not only at registration -- confirmed by dedicated
tests that zero backend calls occur while disabled, across all 14
backend-touching actions. No general per-action human-confirmation
framework exists or was added (Owner Decision D2, the same disclosed
gap EP-050 already carries forward, now independently reaffirmed
rather than resolved) -- disabled-by-default plus a single category
gate is v1's only safety mechanism. No domain allow-list exists (Owner
Decision D6) -- `browser.enabled: true` permits navigation to any
reachable URL, an explicitly approved and explicitly documented v1
limitation, not an oversight. No JavaScript execution, download,
upload, multi-session, or multi-tab/window-management capability
exists anywhere in `src/skills/browser/` (Owner Decisions
D7/D8/D5/D12) -- confirmed absent by direct grep during the
architecture audit, not assumed from design intent alone. Page text
extracted via `browser page-text` is returned as inert string data,
never re-interpreted as a command -- the audit confirmed no
observe-to-dispatch loop exists anywhere in the current codebase
(`src/core/agent/`, `src/core/planning/`, and
`src/core/plan_execution/` call `CommandRouter.dispatch()` nowhere at
all today), so the prompt-injection trust boundary EP051_DESIGN.md
Section 13 describes has no live enforcement gap to close in v1.

`Tool Engine` (`src/core/tool/`), `Agent Framework`, `Planning
Engine`, `Plan Execution Engine`, `src/core/execution/` (EP-003), and
`src/skills/desktop/` (EP-050) are all confirmed byte-identical to
their pre-EP-051 state -- EP-051 introduces no second Tool-execution
path and does not touch EP-050's own OS-input capability in any way.
`CommandRouter` was chosen over Tool Engine for the same reason
EP-050 already established, now independently re-confirmed by a
second EP: `Tool.handler` remains zero-argument-only for every action
already registered in the project -- recorded again as a deferred
architectural evolution, not a permanent rejection, and not something
EP-051 attempted to fix unilaterally.

Tests: EP-051 105/0/0, entirely deterministic against a
`_FakeBrowserBackend` (`tests/EP051/test_browser.py`), no real browser
process required anywhere in the normal suite. A separate,
intentionally unregistered `tests/EP051/test_browser_integration.py`
exists for manual, real-browser verification against a local, static
`file://` fixture page -- but the architecture audit found this
script's own environment-detection logic incomplete (see findings
below) and confirmed **real Chromium execution remains unverified**
in the development sandbox: `playwright install chromium` cannot
complete there because the Playwright CDN is outside the sandbox's
allowed network egress list. Focused regression check: EP-031/044/045/
050 all pass unchanged; EP-046 (a `vosk` import error) and EP-049 (one
pre-existing assertion failure) both reproduce identically against the
pristine, pre-EP-051 upload itself, confirming both are pre-existing,
sandbox-only conditions fully unrelated to EP-051.

**Audit findings (verdict PASS WITH FINDINGS, none blocking, none
fixed during EP-051 -- see `EP051_AUDIT.md` Section 17 for full detail
and Section 21 for recommended follow-up):**

- **HIGH** -- `CommandRouter.dispatch()`'s own pre-existing,
  EP-051-unmodified raw-input logging (`src/core/command_router.py`)
  logs the entire command line on every successful dispatch, including
  `browser type`'s typed text and `browser goto`'s URL (which may
  embed a session token or credential as a query parameter) --
  undermining EP051_DESIGN.md Section 12's "never logged" privacy
  commitment end-to-end, even though `BrowserModule` itself never logs
  this content. This is the identical defect class
  `EP050_AUDIT.md` already documented as HIGH for `desktop type`/
  `desktop write-clipboard` -- independently re-confirmed here rather
  than assumed EP-050-specific, and now affecting two EPs. Tracked as
  a follow-up item below, not fixed during EP-051.
- **MEDIUM** -- `PlaywrightBrowserBackend._call()` (used by 11 of 15
  actions) catches only Playwright's own `Error`/`TimeoutError` types,
  narrower than `launch()`'s own, deliberately broader
  `except Exception` catch and narrower than `backend.py`'s own stated
  "raise only `BrowserBackendError`" contract -- contained by
  `CommandRouter`'s top-level catch-all (no crash), but an
  inconsistency the class's own `launch()` method already shows
  awareness of without applying uniformly.
- **MEDIUM** -- `PlaywrightBrowserBackend.close()`'s failure path may
  leave the underlying Playwright driver subprocess unstopped while
  internal session state is unconditionally reset, permitting an
  uninformed `browser launch` retry with no indication a previous
  browser process may still be running.
- **MEDIUM** -- `tests/EP051/test_browser_integration.py` reports
  "FAILED" (exit code 1), not "SKIPPED", when Playwright's Python
  package is installed but no browser binary has been downloaded --
  the exact state STEP 2's own verification work left the development
  sandbox in. This corrects the STEP 2 report's original claim that
  the script "skips gracefully"; the underlying CDN-blocking
  limitation itself was accurately disclosed, but the script's own
  reporting of that specific state was not.
- **LOW (x3)** -- "double close" and "action after close" are not
  separately, explicitly named test scenarios, though the shared
  underlying code path is correct by direct inspection; raw Playwright
  exception message text (not type) reaches `CommandResult.message`,
  mirroring an already-accepted EP-050 precedent
  (`ComputerUseBackendError`'s identical construction) rather than a
  new pattern; `src/skills/browser/selenium_driver.py` (a 0-byte
  placeholder predating EP-051, superseded by Owner Decision D1's
  choice of Playwright) was not deleted as EP051_DESIGN.md Section 22
  proposed, and remains present, empty, and unimported.

### EP-050 — Computer Use

STEP 1 (Architecture Research, Design & Owner Decisions), STEP 2
(Implementation & Testing), STEP 3 (Architecture Audit), and STEP 4
(Documentation Completion) all complete. EP-050 is marked COMPLETE
with verdict **PASS WITH FINDINGS** (one HIGH, one MEDIUM, four LOW,
four INFO -- none blocking; see below and
`docs/architecture/audits/EP050_AUDIT.md` Section 22 for the full,
verbatim finding list). Full design:
`docs/architecture/designs/EP050_DESIGN.md` (including Section 30's
record of the six owner decisions, D1-D6, and Section 32's dedicated
STEP 1 Final Review of the CommandRouter-vs-Tool-Engine choice). Full
audit: `docs/architecture/audits/EP050_AUDIT.md`.

Built as a new `desktop` `CommandModule`
(`src/skills/desktop/skill.py`) providing 13 actions -- `help`,
`move`, `click`, `scroll`, `type`, `key`, `read-clipboard`,
`write-clipboard`, `screenshot`, `cursor`, `screen-size`,
`active-window`, `focus` -- for raw, local, offline OS-level mouse,
keyboard, clipboard, screenshot, and window-focus control, dispatched
through the *existing*, unmodified `CommandRouter.dispatch()` -- no
new dispatch mechanism, no change to `src/core/command_router.py`,
`src/core/api/`, Telegram, `desktop/` (the EP-044 PySide6 GUI client,
a distinct, unrelated directory never merged with
`src/skills/desktop/`), or `web/`. A new `ComputerUseBackend` protocol
(`src/skills/desktop/backend.py`, 12 methods, exactly the v1 primitive
set) is the only interface `DesktopModule` depends on;
`WindowsComputerUseBackend` (`src/skills/desktop/windows_backend.py`)
is the sole real implementation, PyAutoGUI-based (Owner Decision D3,
already declared in `requirements.txt` before EP-050, unused until
now -- no new top-level dependency added) and honestly scoped as
Windows v1 (Owner Decision D5) with every PyAutoGUI/pygetwindow/
pyperclip import deferred to `__init__` (confirmed necessary: a
top-level import crashes with `KeyError: 'DISPLAY'` in a headless
sandbox).

`desktop.enabled` defaults to `false` and is re-checked on every
dispatched action, not only at registration -- confirmed by dedicated
tests that zero backend calls occur while disabled, including that
`screen_size()` is never called for bounds validation before the gate
passes. No general per-action human-confirmation framework exists or
was added (Owner Decision D2, reaffirmed unfixed) -- disabled-by-
default is v1's only safety mechanism beyond argument/bounds
validation. `Tool Engine` (`src/core/tool/`), `Agent Framework`,
`Planning Engine`, `Plan Execution Engine`, `src/core/execution/`
(EP-003), and `src/skills/browser/` (confirmed still empty, reserved
for EP-051) are all confirmed byte-identical to their pre-EP-050
state -- EP-050 introduces no second Tool-execution path.
`CommandRouter` was chosen over Tool Engine specifically because
`Tool.handler` is zero-argument-only for every action already
registered in the project (a pre-existing, already-disclosed
limitation predating EP-050, confirmed by `src/core/tool/__init__.py`'s
own admission about four already-unregistered EP-029 actions) --
recorded as a deferred architectural evolution (a future, dedicated,
still-unscheduled "parameterized Tool support" Engineering Package),
not a permanent rejection.

Tests: EP-050 112/0/0, entirely deterministic against a
`_FakeComputerUseBackend` (`tests/EP050/test_desktop.py`), no real
mouse/keyboard/screen/PyAutoGUI/display required anywhere in the
normal suite; a separate, intentionally unregistered
`tests/EP050/test_desktop_windows_integration.py` exists for manual,
real-hardware verification on the actual target Windows workstation
and correctly self-skips (exit code 0) in a headless environment.
Focused regression check: EP-031/043/044/045/046/047/049 all pass
unchanged; EP-048 has 2 pre-existing, sandbox-only failures
(`openwakeword`'s `tflite-runtime` has no Linux wheel in the
development sandbox -- the same, already-disclosed condition recorded
against EP-049 above), confirmed unrelated to and unmodified by
EP-050.

**Audit findings (verdict PASS WITH FINDINGS, none blocking, none
fixed during EP-050 -- see `EP050_AUDIT.md` Section 22 for full
detail and Section 23 for recommended follow-up):**

- **HIGH** -- `CommandRouter.dispatch()`'s own pre-existing,
  EP-050-unmodified raw-input logging
  (`src/core/command_router.py`) logs the entire command line on every
  successful/errored dispatch, including `desktop type`/`desktop
  write-clipboard`'s sensitive argument content -- undermining
  EP050_DESIGN.md Section 19's "never logged" privacy commitment
  end-to-end, even though `DesktopModule` itself never logs this
  content. Shared-infrastructure behavior, equally true of every other
  module with a free-text argument (e.g. `email send`, `git commit
  -m`); tracked as a follow-up item below, not fixed during EP-050.
- **MEDIUM** -- `WindowsComputerUseBackend.active_window_title()`
  catches every exception (not only the documented "no active window"
  case) and silently returns `""`, deviating from `backend.py`'s own
  documented Protocol contract.
- **LOW (x4)** -- no literal `'+'`-key support in `desktop key`;
  `desktop click`'s trailing-argument parser silently resolves
  conflicting button names instead of rejecting them; no partial-file
  cleanup if a `desktop screenshot` write fails mid-way; no runtime
  `platform.system() == "Windows"` guard in
  `WindowsComputerUseBackend`.
- **INFO (x4)** -- `runtime_checkable` Protocol conformance checks
  verify method names only, not signatures (a Python language
  characteristic); `WindowsComputerUseBackend._call()` lacks an
  explicit return-type annotation; `desktop.backend` (a config key
  described in EP050_DESIGN.md Section 22) was intentionally not
  implemented since v1 has no backend-selection logic for it to feed;
  active window titles are logged in full (consistent with Section
  19's actual scope, which never listed window titles as a "never
  log" category).

### EP-049 — Voice Assistant

STEP 1 (Design & Owner Decisions), STEP 2 (Implementation &
Verification), and STEP 3 (Architecture Audit / Final Verification)
all complete. EP-049 is marked COMPLETE with verdict **PASS WITH
PRE-EXISTING ENVIRONMENT LIMITATION** (the limitation being an
EP-048-owned, sandbox-only `openwakeword`/`tflite-runtime` Linux
packaging quirk -- see below; not an EP-049 defect). Full design:
`docs/architecture/designs/EP049_DESIGN.md` (including Section 23a's
record of the seven owner decisions, D1-D7, that resolved STEP 1's
open questions). Full audit:
`docs/architecture/audits/EP049_AUDIT.md`.

Built as a strictly one-shot `voice wake assist` action, composed
into the *existing* `voice` `CommandModule`
(`src/skills/voice/skill.py`) as an additive sub-action alongside
EP-048's `wake listen`/`wake status` -- no new dispatch mechanism, no
second namespace, no change to `src/core/command_router.py`,
`src/core/api/`, Telegram, `desktop/`, or `web/`. On a wake-word
detection, `voice wake assist` stops EP-048's existing
`StreamingAudioCapture` wake stream (mandatory hand-off, confirmed by
a dedicated ordering test, not just by design) and calls the
existing, unmodified `_listen()` method directly -- the exact same
method `voice listen` already calls -- which owns EP-046's
`AudioCapture`/STT, EP-046's existing confidence gate, and
`CommandRouter.dispatch()`. An optional final step speaks the
dispatched result aloud via EP-047's existing `TextToSpeechEngine`,
off by default. `_listen()`, `CommandRouter`, and `Bootstrap` are all
confirmed byte-identical to their pre-EP-049 state by direct diff --
EP-049 introduces no second STT/wake/dispatch implementation, no new
`VoiceModule` constructor parameter (EP-049 configuration is read
directly from the existing `config` object), and no new dependency
(`requirements.txt` unchanged).

Strictly one-shot by owner decision (D2): exactly one wake -> command
-> result cycle per invocation, with no loop, no repeat/continuous-
listening configuration, no Bootstrap-managed background thread or
daemon (D1), and no automatic re-arming of wake listening -- a new
invocation of `voice wake assist` is required for another cycle. New
configuration: `voice.wake.assist.enabled` and
`voice.wake.assist.speak_result`, both defaulting to `false`; no
`one_shot` key exists (a loop/repeat mode was explicitly considered
and explicitly rejected for v1 -- see Owner Decision D2). A failed,
rejected, misunderstood, or low-confidence command is handled purely
through the existing `CommandResult`/`TranscriptionResult` error
mechanisms already established by EP-046 -- no retry loop,
confirmation dialog, or failure counter was added (Owner Decision
D7).

Tests: EP-049 87/0/1 (one disclosed, expected skip -- the real
end-to-end hardware scenario, no physical microphone or loaded model
available in the Linux sandbox used for STEP 1-3 development, exactly
mirroring EP-046/047/048's own precedent for their own real-hardware
scenarios); EP-046 58/0/1 and EP-047 49/0/0 both unchanged.

**Target-environment vs. sandbox test results.** All EP-049 STEP 1-3
work was performed in a Linux (Python 3.12) sandbox in which
`openwakeword==0.6.0` cannot be installed at all: its PyPI metadata
hard-requires `tflite-runtime` on Linux, and no distribution of
`tflite-runtime` exists for this platform/Python combination
(confirmed unfixable from within the sandbox, both via `pip install`
and via `pip index versions`). This causes exactly 2 of EP-048's own,
pre-existing tests (`test_wake_word.py`'s two model-file-error-message
assertions) to fail in that sandbox with 110/2/1 instead of clean --
a condition that already existed before any EP-049 code was written
and is fully unrelated to EP-049's own changeset (`requirements.txt`,
`wake_word.py`, and `streaming_audio_capture.py` are all confirmed
byte-identical to their pre-EP-049 state). On the real target Windows
workstation, where `tflite-runtime`'s Linux-only platform marker does
not apply, `openwakeword` installs and runs cleanly, and the project
owner has independently verified EP-048's suite there at **112 passed
/ 0 failed / 1 skipped** -- matching EP-048's own original,
pre-sandbox-limitation verified state (see `EP048_DESIGN.md`'s
"Current verified state" and `EP048_AUDIT.md`). A full-project
regression count on that same target environment has not yet been
independently reported to reconcile against this project's own
sandbox-verified full-suite count (5853 passed / 2 failed / 3
skipped, all 5853 successes and all 3 skips identical across both
environments, with the difference confined entirely to the same 2
EP-048 assertions above); arithmetically, closing those 2 on the
target environment would be expected to yield 5855 passed / 0 failed
/ 3 skipped, but this specific figure is a derived expectation, not
an owner-verified target-environment measurement, and is recorded
here as such rather than as a confirmed result.

Manual, real-microphone/real-loaded-model wake-to-dispatch
verification -- the full `voice wake assist` pipeline end to end (a
real "Hey Jarvis" utterance leading to a real transcribed command,
real dispatch, and optionally real spoken output), not just
EP-048's own already-verified wake-detection step in isolation --
remains an outstanding, disclosed item. See `EP049_AUDIT.md` Section
14 for the exact manual verification checklist.

*(EP-049's test suite (`tests/EP049/test_voice_assistant.py`) uses
deterministic fakes exclusively for wake-word scoring and audio
capture, precisely so its own 87/0/1 result is entirely unaffected by
the sandbox's `openwakeword` limitation described above -- none of
EP-049's own passing assertions depend on a real, loaded wake-word or
STT model.)*

### EP-048 — Wake Word

STEP 1 (Design & Research), STEP 2 (Implementation & Verification),
and STEP 3 (Documentation & Audit Closure) all complete, plus a
post-STEP-3 bug fix from real Windows hardware verification (see
below). EP-048 is marked COMPLETE with verdict **PASS** (updated from
STEP 3's original **PASS WITH DOCUMENTED LIMITATIONS** once real
hardware verification closed the one limitation that was actually
EP-048's own — see `EP048_AUDIT.md` Section 17). Full design:
`docs/architecture/designs/EP048_DESIGN.md` (including Section 9a's
record of the owner decisions that resolved STEP 1's open questions,
Section 17's as-built summary, and Section 17.7's account of the
post-STEP-3 fix). Full audit: `docs/architecture/audits/EP048_AUDIT.md`
(Section 17, "Post-Audit Bug Fix / Final Verification").

Built as offline, `openWakeWord`-based wake-phrase detection
(`src/skills/voice/wake_word.py`) fed by a new, separate
`StreamingAudioCapture` component
(`src/skills/voice/streaming_audio_capture.py`, kept apart from
EP-046's existing, fixed-duration `AudioCapture`, which was not
modified), composed into the *existing* `voice` `CommandModule`
(`src/skills/voice/skill.py`) as additive `wake listen`/`wake status`
actions -- no new dispatch mechanism, no second namespace, no change
to `src/core/command_router.py`, `src/core/api/`, Telegram,
`desktop/`, or `web/`. Actions: `voice wake listen` (starts
continuous detection, reports a single detection or a graceful
failure -- never dispatches, never starts STT, never speaks via TTS,
never runs as a background listener or daemon), `voice wake status`.
Supports English ("Hey Jarvis") only -- Russian and Uzbek wake-word
detection are explicitly out of scope (no offline wake-word model
evaluated has first-class support for either) and receive no
special-case handling anywhere in code. Model files are never
downloaded automatically -- manual placement under
`voice.wake.model_dir` only, mirroring EP-046's own Vosk precedent.
`voice.wake.enabled` defaults to `false`. This EP also fully resolved
EP-047's own disclosed registration-gating limitation
(Owner Decision D6): `Bootstrap` now registers the `voice` namespace
whenever any of `voice.enabled` (STT) / `voice.tts.enabled` /
`voice.wake.enabled` is true, so STT-only, TTS-only, and
Wake-Word-only operation are all independently reachable -- this
required widening `VoiceModule`'s `engine`/`audio_capture`
constructor parameters to `Optional`, with `voice listen`/`voice
transcribe`/`voice status` each reporting a clear failure (never a
crash) when STT is disabled. Tests: EP-048 112/0/1 (one disclosed,
expected skip -- see below); EP-043 83/83, EP-044 52/52, EP-045
38/38, EP-047 49/0/0 all unchanged.

**Post-STEP-3 bug fix (real Windows hardware verification):** the
first real-microphone/real-model verification of EP-048 found that
`OpenWakeWordEngine` looked only for a bare `<wake_word>.onnx` model
filename, while openWakeWord's own official pretrained models are
published with a version suffix (e.g. `hey_jarvis_v0.1.onnx`) -- so a
correctly installed, real model directory was still reported as
unavailable. A second, latent issue was found in the same pass:
prediction lookup needs the resolved model file's own key
(`"hey_jarvis_v0.1"`), not the shorter configured `wake_word`
(`"hey_jarvis"`). Both are fixed in `src/skills/voice/wake_word.py`
via a new, deterministic `resolve_wakeword_model_path()` (exact name
preferred, else exactly one versioned candidate; zero or multiple
candidates raise a clear error -- never a silent guess), with 9 new
regression tests. The configured logical wake word
(`voice.wake.wake_word: "hey_jarvis"`) did not change, and owner
Decision D3 (manual model placement, no automatic download) remains
fully honored. Real Windows verification subsequently confirmed
`voice wake status` reporting `Enabled: Yes`/`Model: available` and
`voice wake listen` correctly detecting "hey_jarvis" (scores 0.80 and
0.64 across two runs) -- the first genuine real-hardware confirmation
of EP-048 in this project's history. Only `src/skills/voice/wake_word.py`
and `tests/EP048/test_wake_word.py` were modified for this fix.

The one limitation that remains disclosed is unrelated to EP-048's
own implementation: `openwakeword==0.6.0` required a Linux-specific
installation workaround in the automated-testing environment used
across STEP 1-3 (its own PyPI metadata hard-requires `tflite-runtime`
on Linux, unavailable there); the actual Windows target never depends
on `tflite-runtime` and installed and ran correctly. See
`EP048_AUDIT.md` Section 17.6 for the updated final verdict and full
detail.

*(A separate, unrelated environment-dependent test issue was also
found and fixed in `tests/EP046/test_voice.py` during the same
real-hardware verification pass -- it is not an EP-048 regression and
is tracked under EP-046's own entry below, not here.)*

### EP-047 — Text-to-Speech

STEP 1 (Design & Research), STEP 2 (Implementation & Verification),
and STEP 3 (Documentation & Audit Closure) all complete. EP-047 is
now marked COMPLETE with verdict **PASS WITH DOCUMENTED
LIMITATIONS**. Full design: `docs/architecture/designs/EP047_DESIGN.md`
(including Section 9a's record of the owner decisions that resolved
STEP 1's open questions, and Section 17's as-built summary). Full
audit: `docs/architecture/audits/EP047_AUDIT.md`.

Built as an offline `pyttsx3`-based TTS engine
(`src/skills/voice/text_to_speech.py`) that speaks text through the
OS's native speech driver (SAPI5 on Windows), composed into the
*existing* `voice` `CommandModule` (`src/skills/voice/skill.py`) as
an additive `speak` action -- no new dispatch mechanism, no second
namespace, no change to `src/core/command_router.py`,
`src/core/api/`, Telegram, `desktop/`, or `web/`. Action: `voice
speak <text>`, joined from its arguments and spoken via a blocking
`engine.say()`/`engine.runAndWait()` call; never dispatches through
`CommandRouter` and never automatically speaks another command's
result. Supports English and Russian, contingent on a matching OS
voice being installed -- Uzbek is explicitly out of scope (no offline
TTS engine evaluated has a first-class Uzbek voice) and receives no
special-case handling anywhere in code: an unconfigured or
voice-less language always fails the same generic path, whether
that language is Uzbek or any other. `voice.tts.enabled` defaults to
`false`, independent of `voice.enabled` (STT) for failure-mode
purposes (a TTS construction failure never disables STT, and vice
versa) -- though the `voice` namespace itself remains registered only
when `voice.enabled` (STT) is also true, a disclosed, as-built
limitation (see `EP047_AUDIT.md` Known Limitations). Tests: EP-047
49/0/0; EP-043 83/83, EP-044 52/52, EP-045 38/38, EP-046 57/0/1 all
unchanged; full suite 5,655 passed / 0 failed / 1 skipped in this
verification run (an earlier-documented two-failure baseline for
EP-039/EP-041 was re-investigated and found to be an
environment-dependent, network-availability difference, not a code
regression -- see `EP047_AUDIT.md` Section 11 for detail).

Two disclosed, non-blocking gaps remain: no real Windows/SAPI5
audible speech has been confirmed by a human in any environment this
project has run in, and TTS-only operation (with STT/microphone
fully disabled) is not currently supported, due to the
registration-gating limitation above. Recommended as the first
manual-verification item, and a candidate small follow-up design
decision, once EP-047 reaches the actual target Windows workstation.
See `EP047_AUDIT.md` Section 13 for full detail.

### EP-046 — Speech-to-Text

STEP 1 (Design & Planning), STEP 2 (Implementation & Verification),
and STEP 3 (Documentation & Audit Closure) all complete. EP-046 is
now marked COMPLETE with verdict **PASS WITH DOCUMENTED
LIMITATIONS**. Full design: `docs/architecture/designs/EP046_DESIGN.md`
(including Section 9a/9b/9c's record of the owner decisions that
resolved STEP 1's open questions, and Section 16's as-built summary).
Full audit: `docs/architecture/audits/EP046_AUDIT.md`.

Built as an offline Vosk-based STT engine
(`src/skills/voice/speech_to_text.py`) plus a separate `sounddevice`
audio-capture layer (`src/skills/voice/audio_capture.py`), composed
by a new `voice` `CommandModule` (`src/skills/voice/skill.py`) that
dispatches recognized text through the existing, unmodified
`CommandRouter` -- no new dispatch mechanism, no `src/core/api/`,
Telegram, or `desktop/`/`web/` change. Actions: `voice listen`
(primary -- capture, transcribe, and dispatch if confident enough),
`voice transcribe` (capture and transcribe only, never dispatch),
`voice status`, `voice help`. Supports Russian, Uzbek, and English
via Vosk small models (`vosk-model-small-ru-0.22`,
`vosk-model-small-uz-0.22`, `vosk-model-small-en-us-0.15`), manually
installed under `voice.model_dir` -- none bundled in the repository.
`voice.enabled` defaults to `false`; low-confidence transcripts are
never auto-executed. Tests: EP-046 57/0/1 (one disclosed, expected
skip); EP-043 83/83, EP-044 52/52, EP-045 38/38 all unchanged; full
suite 5,641 passed / 2 failed (EP-039/EP-041, pre-existing and
independently confirmed unrelated to EP-046) / 1 skipped.

Two disclosed, non-blocking gaps remain, both stemming from the same
cause -- no Vosk model files and no physical microphone exist in any
environment this project has run in: no real audio has been
transcribed by a loaded model, and no real microphone capture has
been verified. Recommended as the first manual-verification item
once EP-046 reaches the actual target workstation. See
`EP046_AUDIT.md` Section 14 for full detail.

### EP-045 — Web Dashboard

STEP 1 (Design & Architecture Investigation), STEP 2
(Implementation), and STEP 3 (Documentation & Audit Closure) all
complete. EP-045 is now marked COMPLETE with verdict **PASS**. Full
design: `docs/architecture/designs/EP045_DESIGN.md` (including
Section 22a's record of the owner decisions that resolved STEP 1's
open questions). Full audit:
`docs/architecture/audits/EP045_AUDIT.md`.

As built: `web/public/{index.html, app.js, styles.css}` is a plain
HTML/CSS/JavaScript dashboard -- no framework, no build step, no new
dependency -- consuming EP-043's REST API exclusively, over
same-origin `fetch()` calls to `GET /health`, `GET /api/v1/status`,
and `POST /api/v1/commands` using relative URLs (no dashboard-side
API base URL configuration is needed, a direct consequence of
same-origin serving). Same-origin serving was implemented by adding
an **optional** `static_dir` capability to the existing
`RestApiServer` (`src/core/api/rest_api_server.py`) -- off by
default, gated by a new, opt-in `api.web_dashboard_dir` config key
(`config/config.yaml`) resolved in `src/bootstrap.py`. This was the
one `src/core/api/` change made in this EP, demonstrated as
technically necessary before being made (only one process can bind
`api.host:api.port`, and a CORS policy was ruled out by owner
decision) -- see `EP045_AUDIT.md` Section 6/7 for the verification.
No CORS policy, no authentication, and no network-exposure change
were introduced; EP-043's three existing routes and their behavior
are byte-identical to before this EP.

DEFERRED (see Non-Goals in `EP045_DESIGN.md`, and Future Ideas
below): chat, memory browser, agent management, workflow editor,
voice control, file management, notifications, authentication UI,
periodic health-check polling, command history, CLI-syntax command
input.

NON-BLOCKING LIMITATION (see `EP045_AUDIT.md` Section 5/14 for
detail): `web/public/app.js` and `styles.css` have no dedicated
automated unit test -- no JavaScript test runner exists in this
project. Both were verified working via a manual functional smoke
test during STEP 2. This does not affect correctness, security,
architecture, or any passing `test EP045` assertion.

OWNER DECISION REQUIRED (carried from STEP 1, still open): explicit
target-browser sign-off (STEP 1 proposed "current evergreen browsers
only"; STEP 2 implemented against that assumption but the owner has
not explicitly re-confirmed it as final).

Note: EP-044 — Desktop UI is now fully complete through STEP 3 (see
`docs/architecture/designs/EP044_DESIGN.md` and
`docs/architecture/audits/EP044_AUDIT.md`), and remains marked
complete in `docs/architecture/JARVIS_ROADMAP.md`, unchanged by
EP-045 (`desktop/` confirmed byte-identical to its pre-EP-045 state).
STEP 1 (Design & Architecture Investigation), STEP 2
(Implementation), and STEP 3 (Final Verification, Architectural
Audit & Documentation) all complete. EP-044 is now marked COMPLETE
with verdict **PASS WITH DOCUMENTED LIMITATIONS**. Full design:
`docs/architecture/designs/EP044_DESIGN.md`. Full audit:
`docs/architecture/audits/EP044_AUDIT.md`.

As built: `desktop/` is a new top-level package (a PySide6 MVVM
client, not nested under `src/`), consuming EP-043's REST API
exclusively over HTTP -- `desktop/api/jarvis_api_client.py` (built on
the already-existing `requests` dependency) is the only component
that talks to Jarvis, calling `GET /health`, `GET /api/v1/status`,
and `POST /api/v1/commands` unchanged. No file under `src/core/`,
`src/services/`, or `src/modules/` is imported by `desktop/`
business logic. Network calls run on a worker `QThread`
(`desktop/viewmodels/api_worker.py`) with results delivered back to
the UI thread via Qt signals, so the GUI event loop is never blocked.
Desktop configuration (host/port/timeout) is stored separately from
`config/config.yaml`, in a per-user YAML file
(`desktop/config/desktop_config.py`), matching the design's required
separation of client and server configuration. `PySide6==6.11.2` was
added to `requirements.txt` as the project's first-ever GUI
dependency; no other dependency changed.

DEFERRED (see Non-Goals in `EP044_DESIGN.md`, and Future Ideas
below): tray integration, desktop notifications, command history,
CLI-syntax command input, packaging/installer/executable generation,
authentication UI, chat/memory/agent browsers, workflow editor,
voice control, file management.

NON-BLOCKING LIMITATION (see `EP044_AUDIT.md` Section 5 for detail):
`EP044_DESIGN.md` Section 20 (Logging) specifies reusing the
project's `loguru` convention for connection attempts, state
transitions, and command submissions/results; the STEP 2
implementation does not yet call `loguru` anywhere in `desktop/`.
This does not affect correctness, security, architecture, or any
passing test, and is left for a small, separate follow-up rather
than folded into the STEP 3 audit gate.

OWNER DECISION REQUIRED (carried from STEP 1, still open): automatic
health-check polling cadence (STEP 2 implemented manual-only,
consistent with the design leaving this unresolved); target
platform(s) for future packaging (Windows/Linux/macOS); packaging
scope (own EP vs. EP-044 sub-package); ownership of the three
pre-existing, empty `src/ui/dashboard.py` / `tray.py` /
`notifications.py` placeholder files, which STEP 1, STEP 2, and
STEP 3 all confirmed remain untouched and byte-identical to their
pre-EP-044 state.

Note: EP-043 — REST API is now fully complete through STEP 4 (see
CHANGELOG.md / docs/RELEASE_NOTES.md), and remains marked complete in
docs/architecture/JARVIS_ROADMAP.md, unchanged by EP-044. STEP 1
(Investigation), STEP 2 (Implementation), STEP 3 (API Contract
Hardening), and STEP 4 (Finalization & Release Readiness) all
complete. Scope was confirmed directly by the project owner (the
STEP 1 investigation stopped because the repository established only
the title "REST API," with no purpose, consumers, endpoint surface,
security model, dependency, or lifecycle integration defined anywhere
-- see `EP043_STEP1_REPORT.md`). Full design:
`docs/architecture/designs/EP043_DESIGN.md`.

As built: `RestApiServer` (`src/core/api/rest_api_server.py`) is a
Bootstrap-level sibling of `InteractiveShell` -- not a
Core -> Service -> Module subsystem -- built entirely on the Python
standard library (`http.server`), with no new `requirements.txt`
dependency (at the time of EP-043; EP-044 subsequently added
`PySide6` for its own, separate Desktop client). It binds
`127.0.0.1:8080` by default and exposes three endpoints:
`GET /health`, `GET /api/v1/status`, `POST /api/v1/commands`.
`ApiRouter` (`src/core/api/api_router.py`) dispatches every command
request through the exact same `CommandRouter` instance
`InteractiveShell` and `TelegramRouter` already use -- no business
logic was added or duplicated. `api.enabled` defaults to `false`
(unlike EP-039/040/041's `true` default), a deliberate deviation from
the implementation prompt's illustrative `enabled: true` example:
unlike those stateless outbound clients, enabling this subsystem
binds and listens on a real network socket as a side effect of
`Bootstrap.initialize()`, so it stays off by default for safety and
to avoid port conflicts in the many existing EP-001..042 tests that
construct a real `Bootstrap` for wiring checks alone.

DEFERRED (see Non-goals in `EP043_DESIGN.md`, and Future Ideas below):
authentication/authorization, TLS, CORS, rate limiting, OpenAPI/Swagger
generation, WebSocket support, per-subsystem REST resources (v1 has
one generic command endpoint instead of e.g. dedicated
`/api/v1/email/...` routes).

STEP 3 (contract hardening, see `EP043_STEP3_REPORT.md`) added a
`415 Unsupported Media Type` response for `POST /api/v1/commands`
when `Content-Type` is present and not `application/json` (a missing
header is still treated leniently), and fixed a robustness gap where a
malformed `api.port` (wrong type or out of range) could raise an
uncaught exception during `Bootstrap.initialize()` instead of
degrading safely to "REST API disabled." No endpoint, status-code
policy, or configuration default changed.

Note: EP-042 — Email Integration is now fully complete through
STEP 4 (see CHANGELOG.md / docs/RELEASE_NOTES.md), and is now marked
complete in docs/architecture/JARVIS_ROADMAP.md. It is a new,
independent Core -> Service -> Module subsystem
(`src/core/email/`, `src/services/email_service.py`,
`src/modules/email_module.py`) exposing exactly four read-only
operations -- `list_folders()`, `list_messages(folder, limit)`,
`get_message(folder, uid)`, `search_messages(folder, criteria)` --
against a standard, provider-independent IMAP server, using the
Python standard library (`imaplib` + `email`) directly. No
send/reply/forward/delete/move/flag operation, no provider-specific
API (Gmail API, Microsoft Graph, Outlook API), no OAuth, and no
background polling exists anywhere in this subsystem.
Authentication uses two configurable environment-variable names
(default `EMAIL_IMAP_USERNAME`/`EMAIL_IMAP_PASSWORD`), read per-call
and never placed in config. `email.enabled` defaults to `false`
(unlike EP-039/040/041's `true` default), since IMAP has no safe
universal default host. `EmailService` has no dependency on any
other Engineering Package's service or engine.

SCOPE NOTE: EP-042 STEP 3 was a Deep Audit and returned a final
verdict of PASS WITH NOTES. Three defects were found and fixed (see
CHANGELOG.md "Fixed" section for v0.1.9-ep042), and no P0
(security/data-mutation) issue was identified. One pre-existing,
out-of-scope technical-debt item was recorded but deliberately left
unfixed: `TestRegistry`'s `NAME.upper()` keying means only one of
`EmailServiceTest`/`EmailModuleTest` is reachable via the CLI
`test EP042` command -- this predates EP-042, affects every prior
integration EP's Service/Module test pair as well, and should be
handled by a separate future maintenance EP. EP-043 deliberately
sidesteps this collision by registering a single `EP043` test suite
rather than a same-named Service/Module pair.

---

# Purpose

This document contains ideas, improvements, feature requests and future work that are not yet assigned to an Engineering Package.

Items in this document are not commitments.

They serve as a pool of potential future work.

---

# Rules

Items may be added at any time.

Items may be removed.

Items may later become Engineering Packages.

Priority may change.

---

# Current Backlog

## AI

- Improve project retrieval quality
- Support hybrid search
- Support code embeddings
- Improve provider selection
- Feed EP-022's assembled RAG context into the AI Provider Framework
  for chat completion (deliberately out of scope for EP-022 itself)

---

## User Experience

- Better shell autocomplete
- Command history search
- Improved progress indicators

---

## Tools

- Git integration improvements
- Local file watcher
- Background indexing
- REST API authentication/authorization (API keys, JWT, OAuth, RBAC) -- deferred from EP-043 v1
- REST API TLS/HTTPS support -- deferred from EP-043 v1
- REST API CORS configuration -- deferred from EP-043 v1
- REST API rate limiting -- deferred from EP-043 v1
- REST API OpenAPI/Swagger schema generation -- deferred from EP-043 v1
- Per-subsystem REST resources (e.g. dedicated /api/v1/email/... routes) -- deferred from EP-043 v1, which ships one generic /api/v1/commands endpoint instead
- TestRegistry NAME-collision fix (Service/Module test pairs sharing a NAME are only partially reachable via `test EP0NN`) -- pre-existing since EP-038, tracked again during EP-042 and EP-043
- `CommandRouter.dispatch()` raw-input logging exposes sensitive command arguments in full (e.g. `desktop type`/`desktop write-clipboard`'s text) -- HIGH finding from `EP050_AUDIT.md`, deferred from EP-050 v1; needs its own architectural decision on how a `CommandModule` can mark specific actions as sensitive before this is fixed at the `CommandRouter` level
- `WindowsComputerUseBackend.active_window_title()` should distinguish "no active window" from a genuine backend failure instead of swallowing all exceptions into an empty string -- MEDIUM finding from `EP050_AUDIT.md`, deferred from EP-050 v1

---

## Future Ideas

- Voice commands

- Browser automation

- Desktop assistant

- Plugin marketplace

---

End of document.