# CHANGELOG.md

All notable changes to this project will be documented in this file.

The format is inspired by Keep a Changelog.

---

## v0.1.21-ep062

Released: 2026-09-05

Status: EP-062 COMPLETE / STEP 3 PASS WITH WARNINGS, NO BLOCKING
FINDINGS (STEP 1 Architecture Discovery & Design, STEP 2
Implementation & Testing, STEP 3 Architecture Audit, STEP 4
Documentation Synchronization all complete). STEP 3's verdict was
**PASS WITH WARNINGS** -- two non-blocking findings (F1, F2) and two
observations (F3, F4), zero blocking. Per explicit instruction, STEP 4
did not remediate F1-F4: all four were reviewed and accepted as
non-blocking/informational, not requiring a code, test, or design
change, so STEP 4 performed documentation synchronization only. Final
status after STEP 4: four release/project documentation files
updated, zero production-code, test, or configuration change beyond
what STEP 2 already implemented.

Neither `docs/BACKLOG.md` nor `docs/architecture/JARVIS_ROADMAP.md`
named an EP-062 scope -- both said "none yet defined," and, unlike
EP-060 naming EP-061, EP-061's own design/audit documents did not name
a specific "next EP" candidate either. STEP 1 found no textual anchor
naming a specific EP-062 mechanism, but did find a real, code-verified
gap disclosed by EP-060 and left open by EP-061:
`BackgroundWorkerService.status()` (EP-036) derived `running`
exclusively from whether it owned a pool object at all
(`self._pool is not None`), never from whether `shutdown()` had
already been called on that pool -- so `status().running` stayed
`True` for the rest of the object's life once ever `True`, even after
a full, confirmed shutdown. This was already disclosed by name in
`EP060_DESIGN.md` Section 5.5, still pinned by an explicit,
unfixed-limitation test in `tests/EP060/test_runtime_lifecycle.py`,
and reachable live through the `worker status` CLI (`worker stop`
followed by `worker status` printed "Running : YES" while a
subsequent `worker submit` would immediately raise
`PoolShutDownError`). STEP 1 recommended closing it at its source with
the smallest possible change: `BackgroundWorkerPool` (EP-036) already
exposed a public, thread-safe `is_shutdown` property that nothing
above it consumed -- wiring that one property into `status()` fixes
every downstream consumer (`RuntimeService`, `worker status`)
automatically, with no change to either consumer.

### Added

- tests/EP062/test_background_worker_status.py: new, self-contained
  EP-062 test suite (`NAME = "EP062"`), 39 assertions covering
  `BackgroundWorkerService.status()` in isolation (disabled, never
  shut down, shut down with `wait=True`/`wait=False`, called twice
  after shutdown, `worker_count`/`task_count` unaffected by shutdown
  state), `RuntimeService`'s corrected `status()`/`shutdown()`
  behavior (including a second `shutdown()` call and `runtime status`
  CLI output), `BackgroundWorkerModule` CLI consistency (`worker
  status` after `worker stop`, `worker submit` still raising
  afterward), and public-surface guards for `BackgroundWorkerService`
  and `BackgroundWorkerStatus`
- docs/architecture/designs/EP062_DESIGN.md: full design document,
  including Owner Decisions D1-D3
- docs/architecture/audits/EP062_ARCHITECTURE_AUDIT.md: EP-062
  Architecture Audit, Final Verdict PASS WITH WARNINGS, NO BLOCKING
  FINDINGS

### Changed

- src/services/background_worker_service.py: `status()`'s `running`
  field changed from an unconditional `True` to
  `not self._pool.is_shutdown` -- the one behavioral change this EP
  makes. `status()`'s docstring and `BackgroundWorkerStatus.running`'s
  field docstring were also updated to describe the corrected
  semantics. No other line, method, or public surface in this file
  changed (`BackgroundWorkerService` still exposes exactly `{status,
  submit, get_task, list_tasks, shutdown}`; `BackgroundWorkerStatus`
  still has exactly `{enabled, running, worker_count, task_count}`)
- src/services/runtime_service.py: documentation-only --
  `RuntimeShutdownReport.background_workers_was_active`'s docstring
  updated to state that the limitation it previously described as
  "disclosed, not fixed, by EP-060" is now fixed at its source by
  EP-062. Zero executable lines changed; `status()` and `shutdown()`
  are unmodified and still call `BackgroundWorkerService.status()`
  exactly as before
- tests/EP060/test_runtime_lifecycle.py: one test corrected, not
  weakened -- `_test_shutdown_disclosed_background_worker_status_
  limitation` (which pinned the pre-EP-062 bug) renamed to
  `_test_shutdown_background_worker_status_reflects_shutdown_state`
  and its two assertions updated from `assert_true` to `assert_false`
  to match the now-corrected contract; its docstring and one module-
  level docstring bullet updated to match. No other test in this file
  changed (23 of its 24 test methods required no change at all)
- src/modules/test_module.py: one added import line
  (`import tests.EP062.test_background_worker_status`)
- No existing method's signature, return type, or behavior changed for
  `BackgroundWorkerPool`, `BackgroundWorkerModule`, `RuntimeModule`,
  `Bootstrap`, `SchedulerService`, or `RestApiServer` -- all
  independently confirmed unmodified. No existing `config/config.yaml`
  key was added, removed, or had its meaning changed, and no new key
  was added. No new dependency was added to `requirements.txt`.

### Security

- No new control surface reachable via CLI or REST: `worker`'s six
  actions (`status, submit, list, info, stop, help`) and `runtime`'s
  two actions (`status, help`) are unchanged in count and dispatch --
  only the value displayed by `worker status`/`runtime status`
  changes, at its one source

### Validation

```
EP062 : 39 passed / 0 failed / 0 skipped
EP036 : 101 passed / 0 failed / 0 skipped
EP036-STEP2 : 48 passed / 0 failed / 0 skipped
EP036-STEP3 : 53 passed / 0 failed / 0 skipped
EP059 : 93 passed / 0 failed / 0 skipped
EP060 : 65 passed / 0 failed / 0 skipped
EP061 : 62 passed / 0 failed / 0 skipped
```

All figures above were independently reproduced from a clean process
at STEP 2, STEP 3, and STEP 4 -- no figure changed between STEP 3 and
STEP 4, since STEP 4 made no code or test change.

### STEP 3 -- Architecture Audit

Verdict: EP-062 STEP 3 -- **PASS WITH WARNINGS**, zero blocking
findings. All three Owner Decisions (D1-D3) confirmed VERIFIED against
direct source inspection, not merely against the STEP 2 report.
`BackgroundWorkerPool`, `BackgroundWorkerModule`, `RuntimeModule`,
`Bootstrap`, `SchedulerService`, `config/config.yaml`,
`requirements.txt`, `docs/BACKLOG.md`, `docs/RELEASE_NOTES.md`,
`docs/architecture/JARVIS_ROADMAP.md`, and
`docs/architecture/ARCHITECTURE_DEBT.md` were all independently
confirmed untouched. Two non-blocking findings and two observations
were identified:

1. **(F1, non-blocking)** `background_worker_service.py`'s `status()`
   and `BackgroundWorkerStatus.running`'s docstrings were expanded
   beyond the design's literal "no other line changes" wording for
   this file -- accurate and non-behavioral, but a deviation from the
   design's stated scope.
2. **(F2, non-blocking)** `src/modules/test_module.py`'s one added
   import line and the new `tests/EP062/__init__.py` package marker
   were not itemized anywhere in `EP062_DESIGN.md` Section 13 -- both
   necessary for the new suite to register/import at all, and both
   mirror identical precedent from EP-059/EP-060/EP-061's own STEP 2
   work, none of which was itemized in those EPs' own design documents
   either.
3. **(F3, observation)** No test exercises a genuinely concurrent
   `status()` call racing an in-progress `shutdown()` from a second
   thread; verified safe by direct source inspection instead (both
   operations share one short-lived lock, never held across a blocking
   call), and not required by the design's own Testing Strategy.
4. **(F4, observation)** A citation-accuracy note only, with no
   bearing on correctness.

The owner reviewed all four and directed STEP 4 to leave each
unchanged, since none violated `EP062_DESIGN.md` or any approved Owner
Decision (D1-D3) and none required a design, scope, or behavior
change. Final status after STEP 4: zero code/test/config change. See
`docs/architecture/audits/EP062_ARCHITECTURE_AUDIT.md` for the full
audit.

### STEP 4 -- Documentation Synchronization

No STEP 3 finding was remediated (owner directed all four left
unchanged, per above). Release/project documentation (`CHANGELOG.md`,
`docs/BACKLOG.md`, `docs/RELEASE_NOTES.md`,
`docs/architecture/JARVIS_ROADMAP.md`) synchronized to mark EP-062
COMPLETE / STEP 3 PASS WITH WARNINGS, NO BLOCKING FINDINGS. No further
Engineering Package is yet named anywhere in this repository.

---

## v0.1.20-ep061

Released: 2026-09-05

Status: EP-061 COMPLETE / AUDIT PASSED, NO BLOCKING FINDINGS (STEP 1
Architecture Discovery & Design, STEP 2 Implementation & Testing,
STEP 3 Architecture Audit, STEP 4 Documentation Synchronization all
complete). STEP 3's verdict was **AUDIT PASSED, NO BLOCKING FINDINGS**
-- two non-blocking, documentation-only WARNINGs, zero blocking. STEP
4 resolved both (rather than leaving them open) because doing so
required no design, scope, or behavior change -- only correcting one
stale test-helper docstring and one imprecise evidence citation in the
design document itself. Final status after STEP 4: one test-helper
docstring corrected, one design-document sentence corrected, four
release/project documentation files synchronized, zero production-code
behavior change and zero test-assertion change beyond what STEP 2
already implemented.

Neither `docs/BACKLOG.md` nor `docs/architecture/JARVIS_ROADMAP.md`
named an EP-061 scope -- both said "none yet defined," since EP-060
closed the roadmap's last currently-named phase (Phase 10). STEP 1
found no textual anchor naming a specific EP-061 mechanism, but did
find a real, code-verified gap that EP-060 itself explicitly flagged as
its own most natural follow-up (`EP060_DESIGN.md` Section 15, Owner
Decision D5): `SchedulerService`'s automatic tick loop had a private
`_stop_event`/`_tick_thread` pair built for shutdown, but no public
method to use it, so `RuntimeService.shutdown()`/`Bootstrap.shutdown()`
could stop the REST API Server and the Background Worker Service but
never the Scheduler -- it kept ticking as a daemon thread until the
whole process exited. STEP 1 recommended closing that gap directly:
add one new public method, `SchedulerService.shutdown()`, and wire it
into the one coordination point that already existed for exactly this
purpose.

### Added

- src/services/scheduler_service.py: one new public method,
  `shutdown(wait=True, timeout=None) -> bool`, stopping the background
  tick loop using the already-existing `_stop_event`/`_tick_thread`
  mechanism -- idempotent, identity-guarded against a hypothetical
  replacement thread, and deliberately releasing its internal lock
  before the (bounded) thread join so a concurrent `status()`/`doctor()`
  call is never blocked by an in-progress shutdown; a fixed
  `_DEFAULT_SHUTDOWN_TIMEOUT = 5.0` class constant (not a new
  configuration key -- see "Changed" below)
- src/services/runtime_service.py: `RuntimeShutdownReport` gains
  `scheduler_was_active`/`scheduler_stopped`, both defaulted and
  appended after the four existing fields, so the one existing,
  entirely-keyword-based construction call site is unaffected;
  `shutdown()`'s body gains one new step, calling
  `SchedulerService.shutdown()` -- placed between the REST API Server
  step and the Background Worker Service step (Owner Decision D2:
  independently verified during STEP 1 that `Scheduler` and
  `BackgroundWorkerService` share no queue, pool, or execution engine,
  so this ordering is chosen to silence both new-work triggers, REST
  and Scheduler, before draining the Background Worker Service's own,
  potentially much longer-running, already-accepted work)
- tests/EP061/test_scheduler_shutdown.py: new, self-contained EP-061
  test suite (`NAME = "EP061"`), 62 assertions covering
  `SchedulerService.shutdown()` in isolation (never-started,
  already-running, idempotent, `wait=False`, manual `run()` still
  working afterward), genuine multi-threaded concurrent-shutdown
  race-safety and a whitebox identity-guard regression test, the
  widened `RuntimeService.shutdown()` (all-`None` defaults, a real
  running Scheduler actually stopped, REST-API-then-Scheduler-then-
  Background-Workers ordering via call-order-recording proxies,
  idempotency, a lock-scope regression guard), real end-to-end
  `Bootstrap` wiring (tick loop actually starts/stops,
  `scheduler_service` reference identity-preserved, repeated/
  uninitialized-state safety), and public-surface guards for
  `SchedulerService`, `SchedulerModule`, and `RuntimeModule`
- docs/architecture/designs/EP061_DESIGN.md: full design document,
  including Owner Decisions D1-D4 and a documented, disclosed
  correction made during STEP 1 validation (an initial "Scheduler
  stops last" ordering draft was revised to "second" after
  independently verifying, from source, that the initial rationale's
  premise -- a shared execution path with Background Workers -- was
  factually incorrect)
- docs/architecture/audits/EP061_ARCHITECTURE_AUDIT.md: EP-061
  Architecture Audit, Final Verdict AUDIT PASSED, NO BLOCKING FINDINGS

### Changed

- src/bootstrap.py: `shutdown()`'s docstring updated to describe the
  new three-subsystem ordering and the (unchanged) decision not to
  null `self._scheduler_service`; the method's executable body has
  zero changed lines -- confirmed by diff against the pre-EP-061
  baseline
- src/modules/test_module.py: one added import line
  (`import tests.EP061.test_scheduler_shutdown`)
- tests/EP060/test_runtime_lifecycle.py: two documentation-only
  changes, no assertion changed --
  (1) the comment inside
  `_test_bootstrap_shutdown_does_not_touch_scheduler_service` updated
  to describe the new, widened `shutdown()` behavior (made during
  STEP 2, per the approved design's explicit, narrow authorization);
  (2) `_stop_scheduler_tick_loop_for_test_cleanup()`'s docstring
  updated during STEP 4 to no longer claim, in the present tense, that
  `SchedulerService` exposes no public shutdown method -- it now notes
  that `SchedulerService.shutdown()` exists (EP-061) and that this
  whitebox helper is retained only as a minimal, already-proven
  test-cleanup convenience predating that method, not because no
  public alternative exists today (STEP 3 finding, `EP061_
  ARCHITECTURE_AUDIT.md` Section 7, resolved in STEP 4)
- docs/architecture/designs/EP061_DESIGN.md: one wording correction
  made during STEP 4, resolving the second STEP 3 finding
  (`EP061_ARCHITECTURE_AUDIT.md` Section 5/D4/7) -- the document
  previously stated that "every executor...uses `subprocess.Popen(...)`
  with no `.wait()` call...confirmed by grepping all four executor
  files," which overstated uniformity: three of the four
  (`process_executor.py`, `python_executor.py`, `file_executor.py`)
  use `subprocess.Popen()`, while the fourth (`url_executor.py`) uses
  the standard library's `webbrowser.open()`, a different but equally
  non-blocking mechanism. The wording was corrected everywhere it
  appeared (Sections 2.1, 6, 10, 14, and Owner Decision D2) to
  accurately describe both mechanisms while preserving the actual
  architectural conclusion this evidence supports -- unchanged: none
  of the four executor paths blocks the tick thread on arbitrary,
  long-running external execution, so `SchedulerService.shutdown()`'s
  fixed, unconfigurable join timeout (Owner Decision D4) remains
  correctly justified
- No existing method's signature, return type, or behavior changed
  for `RestApiServer`, `BackgroundWorkerService`, `Scheduler`,
  `JobRegistry`, `ExecutionEngine` (EP-003, confirmed byte-identical),
  `SchedulerModule`, `RuntimeModule`, `CommandRouter`, or
  `InteractiveShell`. No existing `config/config.yaml` key was added,
  removed, or had its meaning changed, and no new `scheduler.*` key
  was added (`SchedulerService.shutdown()`'s join timeout is a fixed
  class constant, not a configuration value -- Owner Decision D4). No
  new dependency was added to `requirements.txt`.

### Security

- No new control surface reachable via CLI or REST:
  `scheduler list`/`status`/`doctor`/`run`/`start`/`stop`/`info`/
  `help` remain the only eight `SchedulerModule` actions (Owner
  Decision D1); `runtime status`/`runtime help` remain the only two
  `RuntimeModule` actions (unchanged from EP-060); the new
  `SchedulerService.shutdown()` is invoked exclusively by
  `RuntimeService.shutdown()`, itself invoked exclusively by
  `Bootstrap.shutdown()` at genuine process exit -- never dispatchable
  through `CommandRouter`/`ApiRouter`
- `shutdown()` never forcefully terminates anything: the tick loop is
  signaled via `threading.Event.set()` and joined via `Thread.join()`
  with a bounded, disclosed timeout; no `os.kill`/`SIGKILL`/thread
  interrupt is used anywhere in this EP

### Validation

```
EP061 : 62 passed / 0 failed / 0 skipped
EP060 : 65 passed / 0 failed / 0 skipped
EP059 : 93 passed / 0 failed / 0 skipped
EP034 : 113 passed / 0 failed / 0 skipped
EP035 : 143 passed / 0 failed / 0 skipped
EP037 : 87 passed / 0 failed / 0 skipped
Full repository regression : 6838 passed / 0 failed / 3 skipped
  (3 skips pre-existing, environment-gated, unrelated to EP-061 --
  confirmed present and unmodified in the pre-EP-061 baseline commit)
```

All figures above were independently reproduced from a clean process
at STEP 2, STEP 3, and STEP 4 -- no figure changed between STEP 3 and
STEP 4, since STEP 4's two documentation corrections touched no
assertion.

### STEP 3 -- Architecture Audit

Verdict: EP-061 STEP 3 -- **AUDIT PASSED, NO BLOCKING FINDINGS**. All
four Owner Decisions (D1-D4) confirmed correctly implemented against a
`git diff` taken against the exact pre-STEP-1 baseline commit, not
merely against the STEP 2 report. Every explicitly-protected file
(`src/core/scheduler/*.py`, `scheduler_module.py`, `runtime_module.py`,
`background_worker_service.py`, `rest_api_server.py`,
`execution/engine.py`, `config/config.yaml`, `requirements.txt`,
`pyproject.toml`, `tests/EP059/test_runtime.py`) confirmed
byte-identical to that baseline. Owner Decision D2's factual basis
(that `Scheduler` and `BackgroundWorkerService` share no execution
path) was independently re-derived from source during the audit, not
merely re-cited from the design document. Exactly two non-blocking
findings were identified:

1. **(WARNING, non-blocking)** `tests/EP060/test_runtime_lifecycle.py`'s
   `_stop_scheduler_tick_loop_for_test_cleanup()` docstring made a
   present-tense claim -- "`SchedulerService` exposes no public method
   to stop its tick loop" -- that EP-061 made false. Did not affect any
   assertion.
2. **(WARNING, non-blocking)** `EP061_DESIGN.md`'s evidence citation
   for "no executor blocks the tick thread" overstated that all four
   executors use `subprocess.Popen()`; one (`url_executor.py`) actually
   uses `webbrowser.open()`. The underlying architectural conclusion
   was unaffected.

File scope confirmed to exactly match the approved STEP 2 scope
(8 files, `git diff <baseline> --stat`), with zero unauthorized changes
anywhere. See `docs/architecture/audits/EP061_ARCHITECTURE_AUDIT.md`
for the full audit.

### STEP 4 -- Documentation Synchronization

Both non-blocking WARNINGs were resolved, documentation-only, with
zero behavior or assertion change:

1. `tests/EP060/test_runtime_lifecycle.py`'s
   `_stop_scheduler_tick_loop_for_test_cleanup()` docstring was
   updated to note that `SchedulerService.shutdown()` now exists
   (EP-061) and that this whitebox helper is retained only as a
   pre-existing test-cleanup convenience, not because no public
   alternative exists. No `assert_*` line in this file was touched.
2. `EP061_DESIGN.md`'s executor-evidence wording was corrected in
   every location it appeared (Sections 2.1, 6, 10, 14, Owner Decision
   D2) to accurately describe three `Popen`-based executors and one
   `webbrowser.open()`-based executor, while explicitly preserving the
   conclusion that evidence supports: none of the four executor paths
   causes `SchedulerService.shutdown()`'s fixed join timeout to bound
   arbitrary, long-running external execution.

The full regression suite was re-run fresh after both corrections and
reproduced the exact same figures as STEP 2/STEP 3 (Validation,
above) -- as expected, since neither correction touched executable
code or test assertions. Release/project documentation (`CHANGELOG.md`,
`docs/BACKLOG.md`, `docs/RELEASE_NOTES.md`,
`docs/architecture/JARVIS_ROADMAP.md`) synchronized to mark EP-061
COMPLETE / AUDIT PASSED, NO BLOCKING FINDINGS. No further Engineering
Package is yet named beyond Phase 10 anywhere in this repository.

---

## v0.1.19-ep060

Released: 2026-09-04

Status: EP-060 COMPLETE / AUDIT PASSED, NO BLOCKING FINDINGS (STEP 1
Architecture Discovery & Design, STEP 2 Implementation & Testing,
STEP 3 Architecture Audit, STEP 4 Finalization all complete). STEP
3's verdict was **AUDIT PASSED, NO BLOCKING FINDINGS** -- one
non-blocking WARNING, zero blocking. STEP 4 resolved the WARNING
(rather than leaving it open, per EP-059's precedent for its own three
findings) because doing so required no design or scope change -- only
synchronizing one stale EP-059 test assertion with the already-approved
EP-060 contract. Final status after STEP 4: one test file
(`tests/EP059/test_runtime.py`) synchronized, four documentation files
updated, zero production-code or configuration change beyond what
STEP 2 already implemented.

EP-060's roadmap entry ("Jarvis Operating System") had no functional
specification anywhere in the repository beyond Phase 10's own
one-sentence goal, shared with EP-059. STEP 1 found no textual anchor
naming a specific EP-060 mechanism, but did find a real, code-verified
gap: `Bootstrap.shutdown()` stopped only the REST API Server, never
the Background Worker Pool, and the Scheduler auto-starts its own tick
loop by default (`scheduler.enabled`/`scheduler.auto_start` both
default `true`) with no public method to stop it at all -- directly
correcting EP-059 Owner Decision D4's premise that Scheduler is never
auto-started as a side effect of `initialize()`. STEP 1 recommended
Owner Decision D1 = "Candidate A": widen EP-059's `RuntimeService`/
`RuntimeModule` from a read-only introspection surface into a small,
additive lifecycle control plane, reachable through the already-
existing `runtime` CLI namespace (no new namespace).

### Added

- src/services/runtime_service.py: `RuntimeStatus` gains
  `scheduler_active`/`scheduler_jobs_registered`, both defaulted so
  every original EP-059 construction call site is unaffected; a new
  `RuntimeShutdownReport` frozen dataclass; `RuntimeService` gains
  exactly one new public method, `shutdown() -> RuntimeShutdownReport`,
  coordinating REST API Server then Background Worker Service
  shutdown, in that order, reusing only their own already-existing,
  already-idempotent `stop()`/`shutdown()` methods -- no new stop
  logic of its own, and no Scheduler/Shell control of any kind
- src/modules/runtime_module.py: `_status()` formatting gains a
  Scheduler line; the module still exposes exactly two actions,
  `status` and `help` (Owner Decision D3) -- no `shutdown` action was
  added
- src/bootstrap.py: one new `_scheduler_service` attribute plus public
  property (Owner Decision D6), promoted from a previously-discarded
  local variable inside `_build_command_router()`; the existing
  `RuntimeService(...)` construction site widened with one new keyword
  argument; `shutdown()`'s existing body replaced (Owner Decision D2)
  to delegate to `RuntimeService.shutdown()`, with a fallback for when
  `RuntimeService` was never built, now also nulling
  `background_worker_service` after shutdown (a new, symmetric
  postcondition alongside the pre-existing `rest_api_server` one)
- tests/EP060/test_runtime_lifecycle.py: EP-060 test suite (`NAME =
  "EP060"`), 65 assertions covering the widened constructor/`status()`,
  `shutdown()` in isolation (all-`None` dependencies, real
  `RestApiServer`/`BackgroundWorkerService` instances, idempotency,
  ordering via call-order-recording proxies, and the disclosed,
  explicitly-pinned `BackgroundWorkerService.status()` post-shutdown
  limitation), the `{status, shutdown}`/`{status, help}` public-surface
  guarantees, `RuntimeModule` status formatting, and real end-to-end
  `Bootstrap` wiring/shutdown
- docs/architecture/designs/EP060_DESIGN.md: full design document,
  including Owner Decisions D1-D6
- docs/architecture/audits/EP060_ARCHITECTURE_AUDIT.md: EP-060
  Architecture Audit, Final Verdict AUDIT PASSED, NO BLOCKING FINDINGS

### Changed

- src/modules/test_module.py: one added import line
  (`import tests.EP060.test_runtime_lifecycle`)
- tests/EP059/test_runtime.py:
  `_test_service_exposes_only_status`'s assertion updated from
  `["status"]` to `["shutdown", "status"]`, with a docstring explaining
  why -- synchronizing this EP-059 Owner-Decision-D5 guard assertion
  with EP-060's own, separately-approved Owner Decision D1 widening,
  rather than leaving it contradicting the now-approved contract. No
  other assertion in this file was changed; 92 of its 93 assertions
  required no change at all
- No existing method's signature, return type, or behavior changed
  for `RestApiServer`, `BackgroundWorkerService`,
  `SchedulerService`/`Scheduler` (EP-011, confirmed byte-identical),
  `CommandRouter`, or `InteractiveShell`. No existing `config/
  config.yaml` key was added, removed, or had its meaning changed, and
  no new `runtime.*`/`scheduler.*` key was added

### Security

- No new control surface reachable via CLI or REST: `runtime status`/
  `runtime help` remain the only two actions (Owner Decision D3);
  `RuntimeService.shutdown()` is invoked exclusively by `Bootstrap.
  shutdown()` at genuine process exit, never dispatchable through
  `CommandRouter`/`ApiRouter`
- `shutdown()` never forcefully terminates anything: `Background
  WorkerService.shutdown()` is always called with its own default
  `wait=True`, letting in-flight background tasks finish

### Validation

```
EP060 : 65 passed / 0 failed / 0 skipped
EP059 : 93 passed / 0 failed / 0 skipped
EP036 : 101 passed / 0 failed / 0 skipped
EP036-STEP2 : 48 passed / 0 failed / 0 skipped
EP036-STEP3 : 53 passed / 0 failed / 0 skipped
EP043 : 83 passed / 0 failed / 0 skipped
```

All figures above were independently reproduced from a clean process
at STEP 2, STEP 3, and STEP 4. `EP059`'s figure is 93/93 only after
the STEP 4 synchronization described above; STEP 2/STEP 3 each
observed 92/93 with the one, now-resolved, disclosed WARNING.

### STEP 3 -- Architecture Audit

Verdict: EP-060 STEP 3 -- **AUDIT PASSED, NO BLOCKING FINDINGS**. All
six Owner Decisions (D1-D6) confirmed correctly implemented with zero
findings against their literal text. `src/services/
scheduler_service.py` and every file under `src/core/scheduler/`
independently re-hashed and confirmed byte-identical to their
pre-EP-060 state -- Scheduler is observed, never controlled. Exactly
one non-blocking finding was identified:

1. **(WARNING, non-blocking)**
   `tests/EP059/test_runtime.py::_test_service_exposes_only_status`
   asserted `RuntimeService`'s public method list equals `["status"]`
   -- an EP-059 Owner-Decision-D5 guard assertion that, by
   construction, could not survive any future, legitimate widening of
   that surface. Classified as an obsolete historical guard, not an
   EP-060 defect: every other, compatibility-relevant assertion in
   that file passed unmodified.

File scope confirmed to exactly match the approved STEP 2 scope, with
zero unauthorized changes to `src/services/scheduler_service.py`,
`src/core/scheduler/*.py`, `config/config.yaml`, or `requirements.txt`.
See `docs/architecture/audits/EP060_ARCHITECTURE_AUDIT.md` for the
full audit.

### STEP 4 -- Finalization (including remediation)

The one non-blocking WARNING was resolved: `tests/EP059/
test_runtime.py::_test_service_exposes_only_status`'s assertion was
updated to `["shutdown", "status"]`, with an added docstring
explaining the change and citing `EP060_ARCHITECTURE_AUDIT.md` Section
7 as its basis. This is the smallest possible change that makes the
test agree with the already-approved EP-060 contract: no other
assertion in the file was touched, and `RuntimeService.shutdown()`
itself was not hidden, removed, or weakened to avoid the conflict. The
STEP 3 audit document was left unmodified -- its finding was not
edited, softened, or removed. The full regression suite was re-run
fresh after the synchronization and reproduced EP-059 at 93/93, with
every other suite unchanged from STEP 2/STEP 3. Release/project
documentation (`CHANGELOG.md`, `docs/BACKLOG.md`,
`docs/RELEASE_NOTES.md`, `docs/architecture/JARVIS_ROADMAP.md`)
synchronized to mark EP-060 COMPLETE / AUDIT PASSED, NO BLOCKING
FINDINGS. No further Engineering Package is yet named beyond Phase 10
anywhere in this repository.

---

## v0.1.18-ep059

Released: 2026-09-03

Status: EP-059 COMPLETE / AUDIT PASSED, NO BLOCKING FINDINGS (STEP 1
Architecture Discovery & Design, STEP 2 Implementation & Testing,
STEP 3 Architecture Audit, STEP 4 Finalization all complete). STEP
3's verdict was **AUDIT PASSED, NO BLOCKING FINDINGS** -- three
non-blocking, informational findings, zero blocking. The owner
reviewed all three findings and directed STEP 4 to leave each
unchanged, since none violated `EP059_DESIGN.md` or any approved
Owner Decision (D1-D6) -- in particular, Finding 3 (no
`runtime.enabled` config key) is the literal, explicit outcome of
approved Owner Decision D6, not an oversight. Final status after STEP
4: zero code/test/config change.

EP-059's roadmap entry ("Distributed Runtime") had no functional
specification anywhere in the repository beyond Phase 10's own
one-sentence goal, and no prior EP anchored a multi-process or
networked runtime concept of any kind. STEP 1 recommended Owner
Decision D1 = "Candidate A": a new, additive, read-only
`RuntimeService`/`RuntimeModule` pair that aggregates
already-existing, already-public facts -- `RestApiServer.is_running`/
`.host`/`.port` (EP-043), `BackgroundWorkerService.status()`
(EP-036), and `InteractiveShell` presence -- plus process PID/uptime
via the standard library only, into one `RuntimeStatus` snapshot,
reachable through a new `runtime` CLI namespace (Owner Decision D2).

### Added

- src/services/runtime_service.py: `RuntimeStatus` (a small, inline,
  frozen dataclass -- Owner Decision D3, no new `src/core/runtime/`
  package) and `RuntimeService`, whose only public method is
  `status()`. Read-only: never starts, stops, restarts, or
  reconfigures anything it reports on. Handles every dependency being
  `None` cleanly, never raising
- src/modules/runtime_module.py: `RuntimeModule`, the `"runtime"` CLI
  namespace (Owner Decision D2), exposing exactly two actions --
  `status` and `help` -- and no control action of any kind (Owner
  Decision D5)
- src/bootstrap.py: one new import block, `self._started_at` captured
  once at `Bootstrap.__init__()` time, one new `RuntimeService(...)`
  construction and `router.register(RuntimeModule(...))` call placed
  at the true end of `initialize()` -- after `_build_command_router()`
  (which assigns `_background_worker_service`) has already returned
  and `_shell`/`_rest_api_server` have also already been assigned, so
  `RuntimeService` always observes the final, live references, never
  an early or stale `None` -- and one new `runtime_service` property
- tests/EP059/test_runtime.py: EP-059 test suite (`NAME = "EP059"`),
  93 assertions covering `RuntimeService.status()` in isolation (all-
  `None` dependencies, real `RestApiServer`/`BackgroundWorkerService`/
  `InteractiveShell` instances, PID, uptime monotonicity, task-count
  changes after a real `submit()`), a dedicated field-wiring mutation
  guard, `RuntimeModule` CLI behavior, `CommandRouter` dispatch
  equivalence, the read-only/no-control-surface guarantee, real
  `Bootstrap` end-to-end wiring, construction-ordering identity and
  behavioral checks, REST command-dispatch compatibility through the
  existing, unmodified `ApiRouter`/`RestApiServer` path (no new
  endpoint), and regression guards for `system status`/`/health`
- docs/architecture/designs/EP059_DESIGN.md: full design document,
  including Owner Decisions D1-D6 and (added during STEP 2) the two
  owner-approved documentation clarifications (construction-ordering
  and REST-authentication-inheritance)
- docs/architecture/audits/EP059_ARCHITECTURE_AUDIT.md: EP-059
  Architecture Audit, Final Verdict AUDIT PASSED, NO BLOCKING FINDINGS

### Changed

- No existing method's signature, return type, or behavior changed.
  `RestApiServer`, `BackgroundWorkerService`, `InteractiveShell`, and
  `CommandRouter` are completely unaffected -- every change above is a
  pure addition (two new files, one new import block plus one new
  construction/registration block plus one new property in
  `bootstrap.py`, one new test-registration import line). No existing
  `config/config.yaml` key was added, removed, or had its meaning
  changed, and no new `runtime.*` key was added (Owner Decision D6)

### Security

- No new control surface of any kind: `runtime status`/`runtime help`
  are the only two actions, matching Owner Decision D5
- `runtime status` becomes reachable over the existing REST API the
  moment `RuntimeModule` is registered, with zero new endpoint code --
  it therefore inherits the REST API's own pre-existing lack of
  authentication, exactly as `worker status`/`/health` already do
  today; this is a pre-existing characteristic of `RestApiServer`, not
  something EP-059 introduces or regresses
- Information disclosed (PID, uptime, REST host/port, background-
  worker thread/task counts) is not materially more sensitive than
  what already-existing, unauthenticated commands disclose today

### Validation

```
EP059 : 93 passed / 0 failed / 0 skipped
EP036 : 101 passed / 0 failed / 0 skipped
EP036-STEP2 : 48 passed / 0 failed / 0 skipped
EP036-STEP3 : 53 passed / 0 failed / 0 skipped
EP043 : 83 passed / 0 failed / 0 skipped
EP033 : 182 passed / 0 failed / 0 skipped
EP034 : 113 passed / 0 failed / 0 skipped
EP035 : 143 passed / 0 failed / 0 skipped
EP037 : 87 passed / 0 failed / 0 skipped
```

All regression figures above were independently reproduced from a
clean process at STEP 2, STEP 3, and STEP 4. Five distinct mutation
tests (one field-wiring swap, one stale-`None` Bootstrap-wiring
mutation, one silent-unknown-action mutation, one hardcoded-boolean
mutation, and one inverted-shell-active-logic mutation), each applied
and then fully restored (byte-identical checksums reconfirmed after
each), were all independently caught by the EP-059 suite. The
sandbox's own pre-existing, environment-only failures (missing
`vosk`/`sounddevice`+PortAudio, affecting EP-046/047/048/049
identically both before and after EP-059) are unrelated to this EP
and unchanged by it.

### STEP 3 -- Architecture Audit

Verdict: EP-059 STEP 3 -- **AUDIT PASSED, NO BLOCKING FINDINGS**. All
six Owner Decisions (D1-D6) confirmed correctly implemented with zero
findings against their literal text. Dependency direction confirmed
strictly `Module -> Service -> Core` with zero reverse coupling into
`RestApiServer`/`BackgroundWorkerService`/`InteractiveShell` (all
three independently confirmed byte-identical to the pristine,
pre-EP-059 repository). Three non-blocking, informational findings
were identified:

1. **(LOW, informational)** `uptime_seconds` measures time since
   `Bootstrap.__init__()`, not since `initialize()` completes -- a
   deliberate, documented choice, not a defect.
2. **(LOW, informational)** `RuntimeModule` silently ignores trailing
   arguments to `status`/`help` rather than returning a usage error --
   consistent with these actions taking no parameters.
3. **(LOW, informational)** no `runtime.enabled` config key exists,
   so the subsystem cannot be disabled without a code change -- the
   explicit, approved outcome of Owner Decision D6, not an oversight.

File scope confirmed to exactly match the approved STEP 2 scope, with
zero unauthorized changes to `src/core/api/rest_api_server.py`/
`api_router.py` (EP-043), `src/services/background_worker_service.py`/
`src/core/background_workers/background_worker_pool.py` (EP-036),
`src/core/shell.py`, `src/core/command_router.py`,
`src/modules/background_worker_module.py`, or `config/config.yaml`.
See `docs/architecture/audits/EP059_ARCHITECTURE_AUDIT.md` for the
full audit, including an auditor-independent mutation test and a
direct object-identity probe of the real Bootstrap wiring.

### STEP 4 -- Finalization (including remediation)

The owner reviewed all three non-blocking findings individually and
directed that none required remediation: Finding 1 and Finding 2 are
deliberate design choices consistent with `EP059_DESIGN.md`, and
Finding 3 is the literal, approved result of Owner Decision D6, which
specifically forbade adding a `runtime.enabled` key. No code, test,
or configuration change was made during STEP 4. The STEP 3 audit
document was left unmodified -- its findings were not edited, softened,
or removed. An additional, fifth mutation test (auditor-independent,
distinct from the four already recorded) was applied and confirmed
caught, then fully restored and reconfirmed byte-identical, before
the full regression suite was re-run and reproduced results identical
to STEP 2/3. Release/project documentation (`CHANGELOG.md`,
`docs/BACKLOG.md`, `docs/RELEASE_NOTES.md`,
`docs/architecture/JARVIS_ROADMAP.md`) synchronized to mark EP-059
COMPLETE / AUDIT PASSED, NO BLOCKING FINDINGS, with no next
Engineering Package yet started.

**EP-059 is COMPLETE (AUDIT PASSED, NO BLOCKING FINDINGS -- three
non-blocking, informational findings identified during STEP 3, each
reviewed and left unchanged during STEP 4 as correctly not requiring
remediation; zero open findings requiring further action).**

---

## v0.1.17-ep058

Released: 2026-09-01

Status: EP-058 COMPLETE / AUDIT PASSED, NO BLOCKING FINDINGS (STEP 1
Architecture Discovery & Design, STEP 2 Implementation & Testing,
STEP 3 Architecture Audit, STEP 4 Finalization all complete). STEP
3's verdict was **AUDIT PASSED, NO BLOCKING FINDINGS** -- two
non-blocking, informational findings, zero blocking. The owner
reviewed both findings and directed STEP 4 to correct the one that
was documentation-only (Finding 1) and acknowledge the other with no
action, exactly as its own original recommendation already advised
(Finding 2). Final status after STEP 4: both findings' final
disposition recorded, zero code/test/config change.

EP-058's roadmap entry ("Autonomous Planning") had no functional
specification anywhere in the repository beyond Phase 9's
one-sentence, five-EP-wide goal already shared with
EP-054/EP-055/EP-056/EP-057. STEP 1 disclosed this explicitly and
found an unusually strong anchor for a Phase-9 EP: an entire,
already-complete ten-Engineering-Package chain (Phase 4 "Agent
Framework", EP-028-032, and Phase 5 "Workflow Automation",
EP-033-037), every package of which explicitly, repeatedly declares
in its own docstring that it performs no AI reasoning and defers that
to a named-but-unbuilt future concept.
`DefaultAgentProvider.execute()` (EP-028) returns, on every real
call, the literal runtime message "No Planner/Reasoning Engine is
registered yet (future EP)"; `PlanningProvider`'s own module
docstring (EP-029) explicitly names "a future AI-/LLM-backed planning
strategy... an obvious, natural extension point for this
abstraction" as the reason it implements only one, deterministic
provider. STEP 1 recommended Owner Decision D1 = "Candidate A": a
new, additive `AIPlanningProvider` implementation of the existing
`PlanningProvider` abstraction (EP-029), registered alongside --
never replacing -- the deterministic `DefaultPlanningProvider`,
selectable via the already-existing `planning use ai` action.

### Added

- src/core/planning/ai_planning_provider.py: `AIPlanningProvider`, a
  new, additive `PlanningProvider` implementation -- reasons about a
  request's meaning using an AI provider (EP-014/015, reached only
  through `ProviderManager.get_current()` -> `AIProvider.ask()`
  directly, the same deliberate bypass of `AIService`'s
  Conversation/Context/Prompt Engine pipeline `PromptOptimizerModule`
  (EP-055) already established), choosing only from the exact same,
  already-real `(subsystem, action)` vocabulary
  `DefaultPlanningProvider`'s own `_KEYWORD_RULES` table already
  recognizes -- derived programmatically at import time, never
  hardcoded, so the two providers remain genuine, interchangeable
  substitutes over the identical action space. Reply parsing is
  defensive: tolerant of bulleted/numbered/inline-description
  formatting an AI reply may add despite instructions, rejects any
  pair outside the fixed menu (this project's Unknown API Policy
  applied to AI output), deduplicates repeated pairs, falls back to
  the identical `acknowledge_request` step `DefaultPlanningProvider`
  already produces in the analogous case when nothing valid parses,
  and enforces `max_steps`
- src/bootstrap.py: one new import and one new registration line
  (`planning_manager.register_provider(AIPlanningProvider(...))`)
  inside the pre-existing Planning construction `try`/`except
  PlanningError` block, registering `AIPlanningProvider` under the
  name "ai" alongside -- never replacing -- the deterministic
  `"planning"` provider. `planning.default_provider` is untouched and
  stays `"planning"` (Owner Decision D1). No new CLI action was
  needed -- `planning use`/`providers`/`plan` (already existing,
  unmodified) already work generically for any registered provider
  (Owner Decision D2: no additional cost/latency safeguard beyond
  that existing action's own plain result)
- tests/EP058/test_autonomous_planning.py: EP-058 test suite (`NAME =
  "EP058"`) -- reply-parsing tests (well-formed, messy formatting,
  off-menu rejection, deduplication, empty-reply fallback, `max_steps`
  truncation), the provider in isolation against a real
  `ProviderManager` with a fake AI backend (faking only the one
  genuine external network dependency this EP introduces, never an
  in-repo component), `PlanningManager` compliance (registration,
  duplicate-name rejection, listing), non-interference with the
  deterministic provider, five real, enabled `Bootstrap` ->
  `CommandRouter` -> `PlanningService` -> `PlanningEngine` ->
  `PlanningManager` -> `AIPlanningProvider` -> `ProviderManager`
  end-to-end tests, and architecture-compliance import scans
- docs/architecture/designs/EP058_DESIGN.md: full design document,
  including the scope-definition discovery, Owner Decisions D1-D3,
  and (added during STEP 4) an Owner Approval Checklist recording
  their final approved values and both STEP 3 findings' final
  disposition
- docs/architecture/audits/EP058_ARCHITECTURE_AUDIT.md: EP-058
  Architecture Audit, Final Verdict AUDIT PASSED, NO BLOCKING
  FINDINGS (Section 19 records the STEP 4 disposition of both
  non-blocking findings and their independent re-verification)

### Changed

- No existing method's signature, return type, or behavior changed.
  `DefaultPlanningProvider`'s own behavior is completely unaffected
  and remains the default provider either way -- every change above
  is a pure addition (one new file containing one new class, one new
  import plus one new registration line in an already-existing
  `try`/`except` block, one new test-registration import line). No
  existing `config/config.yaml` key was added, removed, or had its
  meaning changed (Owner Decision D3: no new `max_tokens`-style key --
  `AIPlanningProvider` relies on the active AI provider's own
  existing default)

### Security

- `AIPlanningProvider` is the first Phase-9 EP whose recommended
  candidate changes an *already-existing* command's (`planning plan`)
  cost/latency profile -- but only once an operator explicitly runs
  `planning use ai`; the deterministic provider remains the default
  and incurs no AI-provider call of any kind unless this explicit
  opt-in step is taken
- Only the request text and a fixed, static menu of already-real
  `(subsystem, action)` pairs are ever sent to the AI provider -- no
  memory, conversation history, knowledge base content, or file
  content of any kind, since `AIPlanningProvider` has no dependency on
  `MemoryService`/`ConversationManager`/`KnowledgeService` of any kind
- No new information-disclosure surface: `plan()`'s output is the
  same `Plan`/`PlanStep` shape `DefaultPlanningProvider` already
  produces and `planning plan` already displays
- No credential handling of any kind in this module --
  `AIPlanningProvider` never reads an API key directly; it reaches
  the provider only through `ProviderManager.get_current()`, exactly
  as `PromptOptimizerModule` already does

### Validation

```
EP058 : 110 passed / 0 failed / 0 skipped
EP028 : 214 passed / 0 failed / 0 skipped
EP029 : 197 passed / 0 failed / 0 skipped
EP030 : 179 passed / 0 failed / 0 skipped
EP031 : 212 passed / 0 failed / 0 skipped
EP032 : 176 passed / 0 failed / 0 skipped
EP033 : 182 passed / 0 failed / 0 skipped
EP034 : 113 passed / 0 failed / 0 skipped
EP035 : 143 passed / 0 failed / 0 skipped
EP036 : 101 passed / 0 failed / 0 skipped
EP055 : 64 passed / 0 failed / 0 skipped
EP056 : 62 passed / 0 failed / 0 skipped
EP057 : 41 passed / 0 failed / 0 skipped

Full suite (test all, 58 suites): 6616 passed / 2 failed / 3 skipped
```

All regression figures above were independently reproduced from a
clean process both before and after the STEP 4 documentation-only
edit. The 2 full-suite failures are the same, already-conclusively-
proven pre-existing, environment-only EP-048 (Wake Word) failures
`EP057_ARCHITECTURE_AUDIT.md` already investigated and proved
unrelated to any Phase-9 EP's own work -- see
`docs/architecture/audits/EP058_ARCHITECTURE_AUDIT.md` Section 14.

### STEP 3 -- Architecture Audit

Verdict: EP-058 STEP 3 -- **AUDIT PASSED, NO BLOCKING FINDINGS**. All
three Owner Decisions (D1-D3) confirmed correctly implemented with
zero findings against their literal text, and `AIPlanningProvider`
independently confirmed, through static analysis, object-identity
inspection of the real `Bootstrap` object graph, and three mutation
tests, to be genuinely additive -- it reuses EP-029's own vocabulary
and exception types, never duplicating or reimplementing EP-029/030/
031's logic, and never displacing `DefaultPlanningProvider` as the
default. Two non-blocking, informational findings were identified:

1. **(LOW, informational)** `EP058_DESIGN.md`'s own prose described
   `DefaultPlanningProvider`'s keyword table as having "nine"
   entries; the audit independently confirmed the actual count is
   seventeen keyword rules collapsing to eight unique `(subsystem,
   action)` pairs after deduplication -- a prose miscount with zero
   effect on the implementation, which derives its menu
   programmatically rather than from any hardcoded count.
2. **(LOW, informational)** a mutation causing an unhandled exception
   partway through the EP-058 test suite's own `run()` method
   prevents subsequent test methods from executing -- a
   characteristic shared by every EP's own pre-existing
   `BaseTest`/`TestRunner` convention, not specific to EP-058.

File scope confirmed to exactly match the approved STEP 2 scope, with
zero unauthorized changes to `src/core/planning/planning_provider.py`/
`planning_manager.py`/`planning_engine.py`/`planning_result.py`
(EP-029, byte-compared against the pre-EP-058 archive and confirmed
identical), `src/core/agent/` (EP-028), `src/core/plan_execution/`
(EP-030), `src/core/tool/` (EP-031), `src/core/collaboration/`
(EP-032), any Phase 5 package (EP-033-037), `src/core/ai/provider_manager.py`/
`provider.py`/`conversation.py`/`conversation_manager.py`/
`context_manager.py` (EP-014/015/016/018), or `config/config.yaml`.
See `docs/architecture/audits/EP058_ARCHITECTURE_AUDIT.md` for the
full first-pass audit, including three independent mutation tests
and a direct object-identity probe of the real Bootstrap wiring.

### STEP 4 -- Finalization (including remediation)

The owner reviewed both non-blocking findings and directed
documentation-only clarification where appropriate, explicitly
declining to modify production code, tests, or configuration merely
to address an informational finding. Finding 1 was corrected via a
targeted, four-passage prose edit to `EP058_DESIGN.md` (the design
document's own numeric claim, "nine" -> "seventeen ... eight unique
pairs"); Finding 2 was acknowledged with no action taken, exactly as
its own original recommendation already advised, since fixing it
would require a separate, cross-cutting change to shared testing
infrastructure (`src/testing/base_test.py`/`runner.py`) outside any
single EP's scope. No public interface, config key, or
previously-correct behavior changed; all 110 EP-058 test assertions
continued to pass unchanged after the documentation-only edit.

The fixes were independently verified: `src/core/planning/ai_planning_provider.py`,
`src/bootstrap.py`, `src/modules/test_module.py`, and
`tests/EP058/test_autonomous_planning.py` were each confirmed
byte-identical before and after STEP 4; the full regression suite was
re-run and reproduced the identical `6616 passed / 2 failed / 3
skipped` result. `docs/architecture/audits/EP058_ARCHITECTURE_AUDIT.md`
was updated in place with a Section 19 remediation record -- the
original first-pass findings (Sections 1-18) were preserved verbatim,
not edited or removed, per the same "record both passes factually"
precedent `EP052_ARCHITECTURE_AUDIT.md`/`EP055_ARCHITECTURE_AUDIT.md`/
`EP056_ARCHITECTURE_AUDIT.md`/`EP057_ARCHITECTURE_AUDIT.md` already
established. Release/project documentation (`CHANGELOG.md`,
`docs/BACKLOG.md`, `docs/RELEASE_NOTES.md`,
`docs/architecture/JARVIS_ROADMAP.md`) synchronized to mark EP-058
COMPLETE / AUDIT PASSED, NO BLOCKING FINDINGS and EP-059 (Distributed
Runtime) as the next, not-started Engineering Package.

**EP-058 is COMPLETE (AUDIT PASSED, NO BLOCKING FINDINGS -- two
non-blocking, informational findings identified during STEP 3 were
each given a final, independently-verified disposition during STEP
4; zero open findings requiring further action).**

---

## v0.1.16-ep057

Released: 2026-09-01

Status: EP-057 COMPLETE / PASS AFTER REMEDIATION (STEP 1 Architecture
Discovery & Design, STEP 2 Implementation & Testing, STEP 3
Architecture Audit, STEP 4 Finalization all complete). STEP 3's
first-pass verdict was **AUDIT PASSED WITH FINDINGS** -- three
non-blocking findings, zero blocking. The owner reviewed all three
findings and directed they be closed during STEP 4, rather than left
documented and unfixed. Final verdict, after the fixes and their
independent verification: **PASS AFTER REMEDIATION**, zero open
findings.

EP-057's roadmap entry ("Memory Optimization") had no functional
specification anywhere in the repository beyond Phase 9's
one-sentence, five-EP-wide goal already shared with
EP-054/EP-055/EP-056. STEP 1 disclosed this explicitly and found the
strongest anchor of any Phase-9 EP so far:
`CompressionEngine.compress_query()`/`compress_semantic_results()`
(EP-027) were already fully built and fully tested but had exactly
zero production callers anywhere in the repository -- and
`src/bootstrap.py`'s own construction-site comment already named this
exact situation verbatim, describing Semantic Search as reached there
"only ... used only by `compression`'s future callers via
`compress_query()`, never by the CLI commands wired here." STEP 1
recommended Owner Decision D1 = "Candidate A": expose that
already-built, already-tested method as a new, on-demand `compression
query "<text>"` command, finally giving it a real caller.

### Added

- src/services/context_compression_service.py: `QueryOutcome` (a
  `CompressOutcome`-shaped frozen dataclass) and
  `CompressionService.query()` -- a one-line forward to
  `CompressionEngine.compress_query()`, introducing no new compression
  or semantic-search logic of its own
- src/modules/context_compression_module.py: a new `query` action on
  the existing `compression` `CommandModule` namespace (Owner Decision
  D4), `'compression query "<text>"'`, dispatched through the
  existing, unmodified `CommandRouter.dispatch()`. Introduces no new
  backend Protocol (Owner Decision D1) -- composes
  `CompressionEngine.compress_query()` (EP-027) directly, read-only,
  which itself reaches `SemanticEngine.search()` (EP-026) over
  Knowledge Base (EP-024) and Long-Term Memory (EP-025) content. No
  `top_k`/`threshold` CLI arguments are exposed -- relies on the
  existing `semantic.*` configuration defaults (Owner Decision D2).
  The EP-016 Conversation Engine, EP-018 Context Loader, EP-024
  Knowledge Base, EP-025 Long-Term Memory, EP-026 Semantic Search, and
  EP-027 Context Compression are never modified or called except
  through their existing, unmodified public API
- tests/EP057/test_memory_optimization.py: EP-057 test suite (`NAME =
  "EP057"`) -- argument-shape and gate tests, a real, unmodified
  `SemanticEngine`/`KnowledgeService` integration test (not a fake)
  for the one genuine cross-subsystem call this EP makes, positive/
  negative-path tests for `CompressionService.query()`, `CommandRouter`
  dispatch equivalence, `Bootstrap` wiring tests, and three real,
  enabled `Bootstrap` -> `CommandRouter` -> `CompressionService` ->
  `CompressionEngine` -> `SemanticEngine` -> `KnowledgeService`
  end-to-end tests (added during STEP 2), plus (added during STEP 4)
  one new test and one renamed test specifically exercising the
  `context_compression.enabled: false` gate together with a real
  `SemanticEngine`
- docs/architecture/designs/EP057_DESIGN.md: full design document,
  including the scope-definition discovery (Section 0-5), Owner
  Decisions D1-D4 (Section 20), and (added during STEP 4) an Owner
  Approval Checklist recording their final approved values -- this
  file was committed to the repository during STEP 4 (see "Fixed"
  below)
- docs/architecture/audits/EP057_ARCHITECTURE_AUDIT.md: EP-057
  Architecture Audit, Final Verdict PASS AFTER REMEDIATION (first
  pass: AUDIT PASSED WITH FINDINGS, three non-blocking findings;
  Section 19 records the STEP 4 fixes and their independent
  verification)

### Changed

- No existing method's signature, return type, or behavior changed.
  Every change above is a pure addition (a new dataclass, two new
  methods/actions, one new dict entry, one new `HELP_TEXT` line). No
  existing `config/config.yaml` key was added, removed, or had its
  meaning changed -- `compression query` reuses
  `context_compression.enabled`/`default_provider`/
  `max_context_characters`/`max_chunks`/`deduplicate` and
  `semantic.top_k`/`similarity_threshold` unchanged

### Security

- `compression query` is gated exactly as `compression compress`
  already is, through `CompressionManager`'s existing enabled/
  provider-selection check -- no new gate was introduced (Owner
  Decision D3)
- No AI-provider call exists anywhere in this feature; no filesystem
  write of any kind
- Independently confirmed during the architecture audit:
  `compression query`'s information disclosure is a strict subset of
  what the already-existing `semantic search` command already
  discloses today (chunk text and aggregate counts only -- never a
  per-result similarity score or source identifier)

### Fixed

- **STEP 4 (Finding 1, LOW/informational):** `src/bootstrap.py`'s
  own construction-site comment for the Context Compression
  subsystem read "used only by `compression`'s future callers via
  `compress_query()`, never by the CLI commands wired here" -- this
  became factually stale the moment EP-057 gave `compress_query()` a
  real CLI caller. Fixed by a comment-only, two-line edit,
  independently confirmed to touch zero executable statements; the
  three real-`Bootstrap` end-to-end tests were re-run and produced
  byte-identical output before and after the edit
- **STEP 4 (Finding 2, LOW):** the registered EP-057 test suite
  defined a `context_compression.enabled: false` configuration
  fixture (`_DISABLED_COMPRESSION_YAML`) but never actually used it
  anywhere, and a test named
  `_test_cli_query_command_failure_when_disabled` instead tested a
  different code path ("no `SemanticEngine` configured"), because
  `CompressionEngine.compress_query()` checks for a `None`
  `SemanticEngine` before ever reaching the `enabled`/
  provider-selection check. This meant the `context_compression.
  enabled: false` gate itself, while functionally correct (confirmed
  by manual audit probe both before and after this fix), was not
  exercised by any repeatable, registered test. Fixed by renaming the
  test to `_test_cli_query_command_failure_without_semantic_engine`
  (behavior unchanged, name now accurate) and adding a new test,
  `_test_cli_query_command_failure_when_context_compression_disabled`,
  using the previously-unused fixture together with a real,
  configured `SemanticEngine`, asserting the failure at both the CLI
  and Service layers. A dedicated mutation test (simulating a
  bypassed gate in an isolated scratch copy, never the real
  repository) confirmed the new test genuinely detects a regression
  that would have passed through the original 35-assertion suite
  entirely undetected (3 of 41 assertions failed against the
  mutation). This fix is confined entirely to
  `tests/EP057/test_memory_optimization.py` -- zero change to
  `src/services/context_compression_service.py` or
  `src/modules/context_compression_module.py`, independently
  confirmed byte-identical to their STEP 2/STEP 3 state
- **STEP 4 (Finding 3, informational):** `docs/architecture/designs/EP057_DESIGN.md`,
  approved by the owner during STEP 1, had been delivered as a
  standalone document but was never committed into the repository
  tree, unlike `EP054_DESIGN.md`/`EP055_DESIGN.md`/`EP056_DESIGN.md`,
  each present in the repository following its own STEP 1. Fixed by
  committing the approved content to
  `docs/architecture/designs/EP057_DESIGN.md`, with a status header
  and an Owner Approval Checklist appended at STEP 4; Sections 0-20's
  original approved text is otherwise unchanged

### Validation

```
EP057 : 41 passed / 0 failed / 0 skipped
EP056 : 62 passed / 0 failed / 0 skipped
EP055 : 64 passed / 0 failed / 0 skipped
EP054 : 76 passed / 0 failed / 0 skipped
EP053 : 58 passed / 0 failed / 0 skipped
EP052 : 135 passed / 0 failed / 0 skipped
EP051 : 105 passed / 0 failed / 0 skipped
EP050 : 112 passed / 0 failed / 0 skipped
EP024 : 407 passed / 0 failed / 0 skipped
EP025 : 442 passed / 0 failed / 0 skipped
EP026 : 204 passed / 0 failed / 0 skipped
EP027 : 229 passed / 0 failed / 0 skipped

Full suite (test all, 57 suites): 6506 passed / 2 failed / 3 skipped
```

All regression figures above were independently reproduced from a
clean process both before and after the STEP 4 fixes. The 2 full-suite
failures are pre-existing EP-048 (Wake Word) failures, independently
investigated during STEP 3 and conclusively proven environment-only
(the `openwakeword` package is not installable in the audit
environment) and unrelated to EP-057, by reproducing the identical
failure against a separate, pristine copy of the repository
containing zero EP-057 code -- see
`docs/architecture/audits/EP057_ARCHITECTURE_AUDIT.md` Section 15.

### STEP 3 -- Architecture Audit

First-pass verdict: EP-057 STEP 3 -- **AUDIT PASSED WITH FINDINGS**.
All four Owner Decisions (D1-D4) confirmed correctly implemented with
zero findings against their literal text, and `compression query`
independently confirmed, through static analysis, object-identity
inspection of the real `Bootstrap` object graph, and mutation testing,
to genuinely reuse EP-027's existing `compress_query()` path rather
than duplicating or reimplementing it. Three non-blocking findings
were identified:

1. **(LOW, informational)** `src/bootstrap.py`'s own comment describing
   Semantic Search access at the Context Compression construction
   site became factually stale once EP-057 wired a real CLI caller
   for `compress_query()`.
2. **(LOW)** the registered test suite's `context_compression.enabled:
   false` fixture was defined but never used, and the test named for
   that scenario actually tested a different, earlier-checked code
   path ("no `SemanticEngine` configured") -- a test-coverage/naming
   gap around a gate this audit independently confirmed functions
   correctly, not a functional or security defect.
3. **(informational)** `EP057_DESIGN.md` had been approved and
   delivered to the owner but was never committed into the repository
   tree.

File scope confirmed to exactly match the approved STEP 2 scope, with
zero unauthorized changes to `src/core/context_compression/*.py`
(EP-027, byte-compared against the pre-EP-057 archive and confirmed
identical), `src/core/semantic/semantic_engine.py` (EP-026),
`src/core/long_term_memory/*.py` (EP-025), `src/core/knowledge/`
(EP-024), `src/core/memory/*.py` (EP-013/023),
`src/core/ai/conversation*.py`/`context_manager.py` (EP-016/018),
`src/core/command_router.py`, `src/bootstrap.py` (unchanged in this
first pass), or `config/config.yaml`. Two pre-existing EP-048 (Wake
Word) test failures were investigated to their exact root cause and
conclusively proven pre-existing and unrelated to EP-057 by
reproducing the identical result against a separate, pristine copy of
the repository. See `docs/architecture/audits/EP057_ARCHITECTURE_AUDIT.md`
for the full first-pass audit, including two independent mutation
tests, a direct object-identity probe of the real Bootstrap wiring,
and the EP-048 investigation.

### STEP 4 -- Finalization (including remediation)

Like EP-055's and EP-056's STEP 4, and unlike EP-054's STEP 4
(documentation sync only, findings left unfixed), the owner explicitly
directed all three non-blocking findings be closed before closing
EP-057. Each fix was minimal and either behavior-preserving or
test-only -- see "Fixed" above for each finding's exact fix. No
public interface, config key, or previously-correct behavior changed;
all 35 pre-existing EP-057 test assertions continued to pass
unchanged, and 6 new assertions (one new test method, one renamed
test method with one added assertion) were added specifically to
close the coverage gap Finding 2 identified.

The fixes were independently verified: (1) the `bootstrap.py` comment
edit was confirmed via `diff` to touch exactly two comment lines and
zero executable statements, and the three real-`Bootstrap` end-to-end
tests were re-run and produced byte-identical output before and
after; (2) a dedicated mutation test, performed in an isolated scratch
copy never touching the real repository, confirmed the new test would
have genuinely caught a simulated gate-bypass regression that the
original suite would have missed entirely; (3) the committed
`EP057_DESIGN.md`'s Sections 0-20 were confirmed identical, word for
word, to the content originally audited against in STEP 3.

`docs/architecture/audits/EP057_ARCHITECTURE_AUDIT.md` was updated in
place with a Section 19 remediation record -- the original first-pass
findings (Sections 1-18) were preserved verbatim, not edited or
removed, per the same "record both passes factually" precedent
`EP052_ARCHITECTURE_AUDIT.md`/`EP055_ARCHITECTURE_AUDIT.md`/
`EP056_ARCHITECTURE_AUDIT.md` already established. Release/project
documentation (`CHANGELOG.md`, `docs/BACKLOG.md`,
`docs/RELEASE_NOTES.md`, `docs/architecture/JARVIS_ROADMAP.md`)
synchronized to mark EP-057 COMPLETE / PASS AFTER REMEDIATION and
EP-058 (Autonomous Planning) as the next, not-started Engineering
Package.

**EP-057 is COMPLETE (PASS AFTER REMEDIATION -- all three non-blocking
findings identified during STEP 3 were fixed and independently
verified during STEP 4; zero open findings).**

---

## v0.1.15-ep056

Released: 2026-08-31

Status: EP-056 COMPLETE / PASS AFTER REMEDIATION (STEP 1 Architecture
Discovery & Design, STEP 2 Implementation & Testing, STEP 3
Architecture Audit, STEP 4 Finalization all complete). STEP 3's
first-pass verdict was **AUDIT FAILED (ONE BLOCKING FINDING)** -- one
HIGH-severity, blocking finding. The owner reviewed the finding and
approved fixing it during STEP 4 (Owner Decision D8). Final verdict,
after the fix and its independent verification: **PASS AFTER
REMEDIATION**, zero open findings.

EP-056's roadmap entry ("Capability Learning") had no functional
specification anywhere in the repository beyond Phase 9's
one-sentence, five-EP-wide goal already shared with EP-054/EP-055.
STEP 1 disclosed this explicitly and found the strongest textual
anchor of any Phase-9 EP so far: `PromptBuilder.append_capabilities()`'s
own docstring, already written during EP-017, reads "reserved for
the future Capability Registry" verbatim. STEP 1 recommended Owner
Decision D1 = "Candidate A": an on-demand Capability Registry
composing already-declared Plugin capability data (EP-010) plus bare
`CommandRouter` namespace names, finally giving that seam real
content.

### Added

- src/skills/capability_registry/skill.py: `CapabilityRegistryModule`,
  the "capability" `CommandModule` namespace -- `list` (compose a
  summary of every currently running plugin's declared capability
  tags, plus the bare list of registered built-in commands) and
  `inject <text>` (pass that same summary through the Prompt Engine's
  existing, previously-unused `PromptManager.build(capabilities=...)`
  seam together with `<text>`, returning the assembled prompt for
  inspection -- never calling an AI provider), plus `help`, dispatched
  through the existing, unmodified `CommandRouter.dispatch()`.
  Introduces no new backend Protocol (Owner Decision D1) -- composes
  `PluginService.running_plugins()` (EP-010) and `CommandRouter.
  module_names` directly, read-only. The EP-010 Plugin system and
  EP-017 Prompt Engine are never modified or called
- config/config.yaml: new `capability_registry` section (`enabled`),
  deliberately separate from the pre-existing `prompt:`/
  `prompt_optimizer:` sections
- tests/EP056/test_capability_registry.py: EP-056 test suite (`NAME =
  "EP056"`) -- argument-shape, gate, positive/negative-path,
  `capability list`/`capability inject` composition tests against
  fake `PluginService`/`module_names` stand-ins, a real, unmodified
  `PromptManager` integration test for `capability inject`,
  `CommandRouter` dispatch equivalence, `Bootstrap` wiring tests, and
  (added during STEP 4) 3 additional tests exercising the real,
  enabled `Bootstrap` -> `CommandRouter` -> `CapabilityRegistryModule`
  path end-to-end
- docs/architecture/designs/EP056_DESIGN.md: full design document,
  including the scope-definition discovery (Section 0-5), Owner
  Decisions D1-D7 (Section 20), and D8 (Section 17, added during
  STEP 3)
- docs/architecture/audits/EP056_ARCHITECTURE_AUDIT.md: EP-056
  Architecture Audit, Final Verdict PASS AFTER REMEDIATION (first
  pass: AUDIT FAILED with one HIGH/BLOCKING finding; Section 18
  records the STEP 4 fix and its independent verification)

### Changed

- src/bootstrap.py: constructs `CapabilityRegistryModule` immediately
  after `plugin_service`'s own construction and `PluginModule`'s own
  registration (Owner Decision D5), gated by
  `capability_registry.enabled` (default `false`). `capability`
  namespace registers even when disabled, reporting a disabled
  message for every action, matching every other skill's convention

### Security

- `capability_registry.enabled` defaults to `false` and is
  re-checked on every dispatched action, not only at registration
- No separate AI-provider privacy gate exists (Owner Decision D3):
  neither `capability list` nor `capability inject` ever calls an AI
  provider, and both disclose no more than the already-existing
  `plugin status`/`plugin info` commands already disclose today
- No filesystem write capability exists anywhere in this module

### Fixed

- **STEP 4 (Owner Decision D8):** `src/bootstrap.py` previously passed
  `module_names=router.module_names` when constructing
  `CapabilityRegistryModule`. Because `CommandRouter.module_names` is
  a `@property`, this evaluated the property immediately at
  construction time, yielding a `list[str]` rather than the live,
  zero-argument callable `CapabilityRegistryModule`'s own documented
  constructor contract required. Every single call to `capability
  list` or `capability inject`, in real production `Bootstrap`
  wiring, raised `TypeError: 'list' object is not callable`, surfaced
  to the end user only as a generic "Internal error" message.
  `capability help` was unaffected, and no security, disclosure, or
  gate-bypass issue was involved. Fixed by a single-line,
  behavior-preserving change confined to `src/bootstrap.py`
  (`module_names=router.module_names` ->
  `module_names=lambda: router.module_names`), requiring zero change
  to `src/skills/capability_registry/skill.py`, `CommandRouter`,
  `PluginService`, or `PromptManager`. This also corrects
  `capability list`/`capability inject`'s summary to correctly
  reflect namespaces registered after `capability` itself (e.g.
  `scheduler`, `telegram`, `test`), since the namespace list is now
  evaluated live at dispatch time rather than captured once at
  construction time.

### Validation

```
EP056 : 62 passed / 0 failed / 0 skipped
EP055 : 64 passed / 0 failed / 0 skipped
EP054 : 76 passed / 0 failed / 0 skipped
EP053 : 58 passed / 0 failed / 0 skipped
EP052 : 135 passed / 0 failed / 0 skipped
EP051 : 105 passed / 0 failed / 0 skipped
EP050 : 112 passed / 0 failed / 0 skipped
```

All regression figures above were independently reproduced from a
clean process both before and after the STEP 4 fix.

### STEP 3 -- Architecture Audit

First-pass verdict: EP-056 STEP 3 -- **AUDIT FAILED (ONE BLOCKING
FINDING)**. All seven Owner Decisions (D1-D7) confirmed correctly
implemented with zero findings against their literal text. One
finding was identified through a direct exercise of the real,
fully-wired `Bootstrap` with `capability_registry.enabled: true` -- a
step beyond what the registered test suite performed:

1. **(HIGH -- BLOCKING)** `src/bootstrap.py` passed `CommandRouter.
   module_names` (a `@property`, evaluated eagerly at construction
   time) where `CapabilityRegistryModule`'s own documented
   constructor contract required a live, zero-argument callable,
   causing a 100%-reproducible `TypeError` on every call to
   `capability list` or `capability inject`. No security, disclosure,
   or gate-bypass issue was involved -- this was a pure availability
   defect. The registered 51-assertion suite did not catch it because
   its fake `module_names` collaborator correctly implemented the
   *documented* interface; only a real, enabled `Bootstrap` exercise
   surfaced the mismatch between that documentation and what
   `bootstrap.py` actually supplied.

File scope confirmed to exactly match the approved STEP 2 scope, with
zero unauthorized changes to `src/core/plugins/plugin.py`,
`plugin_manifest.py`, `plugin_registry.py`, `plugin_loader.py`,
`plugin_discovery.py` (EP-010 Plugin system, byte-compared against
the pre-EP-056 archive and confirmed identical),
`src/services/plugin_service.py`, `src/core/ai/prompt.py`,
`prompt_builder.py`, `prompt_manager.py` (EP-017 Prompt Engine),
`src/core/command_router.py`, `src/services/ai_service.py`, or any
prior skill. See `docs/architecture/audits/EP056_ARCHITECTURE_AUDIT.md`
for the full first-pass audit, including two independent mutation
tests and a direct, real-`Bootstrap` edge-case probe.

### STEP 4 -- Finalization (including remediation)

Unlike EP-054's STEP 4 (documentation sync only, findings left
unfixed), and consistent with EP-055's STEP 4, the owner explicitly
approved Owner Decision D8 (option (a)): fix the finding before
closing EP-056. The fix was minimal and behavior-preserving -- a
single line in `src/bootstrap.py`'s `CapabilityRegistryModule`
registration call. No public interface, config key, or previously-
correct behavior changed; all 51 pre-existing test assertions
continued to pass unchanged, and 11 new assertions (3 new test
methods) were added specifically to exercise the real, enabled
`Bootstrap` wiring end-to-end and prevent this exact wiring defect
from returning.

The fix was independently verified two ways: (1) a reverted, pre-fix
scratch copy (never touching the real repository) was used to confirm
the new tests would have genuinely caught the original defect --
exactly the 9 assertions belonging to the 3 new test methods failed
against it, with the exact predicted error messages, while every
other test continued to pass; (2) the same live probe from the first
audit pass was re-run against the real, fixed code through the actual
`Bootstrap` -> `CommandRouter` -> `CapabilityRegistryModule` path and
confirmed both `capability list` and `capability inject` now succeed,
correctly including namespaces registered after `capability` itself
(`scheduler`, `telegram`, `test`).

`docs/architecture/audits/EP056_ARCHITECTURE_AUDIT.md` was updated in
place with a Section 18 remediation record -- the original first-pass
finding (Sections 1-17) was preserved verbatim, not edited or removed,
per the same "record both passes factually" precedent
`EP052_ARCHITECTURE_AUDIT.md`/`EP055_ARCHITECTURE_AUDIT.md` already
established. Release/project documentation (`CHANGELOG.md`,
`docs/BACKLOG.md`, `docs/RELEASE_NOTES.md`,
`docs/architecture/JARVIS_ROADMAP.md`) synchronized to mark EP-056
COMPLETE / PASS AFTER REMEDIATION and EP-057 (Memory Optimization) as
the next, not-started Engineering Package.

**EP-056 is COMPLETE (PASS AFTER REMEDIATION -- the one blocking
finding identified during STEP 3 was fixed and independently verified
during STEP 4; zero open findings).**

---

## v0.1.14-ep055

Released: 2026-08-30

Status: EP-055 COMPLETE / PASS AFTER REMEDIATION (STEP 1 Architecture
Discovery & Design, STEP 2 Implementation & Testing, STEP 3
Architecture Audit, STEP 4 Finalization all complete). STEP 3's
first-pass verdict was **AUDIT PASSED WITH FINDINGS** -- one
non-blocking MEDIUM finding and one non-blocking LOW finding. Unlike
EP-054, where two comparable findings were documented and left
unfixed, the owner reviewed EP-055's findings and approved fixing
both during STEP 4 (Owner Decision D10). Final verdict, after the fix
and its independent verification: **PASS AFTER REMEDIATION**, zero
open findings.

EP-055's roadmap entry ("Prompt Optimizer") had no functional
specification anywhere in the repository beyond Phase 9's
one-sentence, five-EP-wide goal already shared with EP-054. STEP 1
disclosed this explicitly rather than inventing scope, surveyed the
already-built EP-017 Prompt Engine, and recommended Owner Decision D1
= "Candidate A": on-demand improvement of a prompt's or an existing
template's clarity/structure via one direct AI-provider call.

### Added

- src/skills/prompt_optimizer/skill.py: `PromptOptimizerModule`, the
  "prompt" `CommandModule` namespace -- `optimize <text>` / `optimize
  --template <name>` (ask the configured AI provider to improve the
  clarity/structure of the given text, or of a named template's
  current content, without changing its intent), plus `help`,
  dispatched through the existing, unmodified
  `CommandRouter.dispatch()`. Introduces no new backend Protocol
  (Owner Decision D1) -- composes `ProviderManager`/`AIProvider`
  directly via `ProviderManager.get_current().ask()`, deliberately
  bypassing `AIService`'s pipeline, and reads (never writes -- Owner
  Decision D4) the already-reserved `paths.prompts` directory. The
  EP-017 Prompt Engine (`Prompt`/`PromptBuilder`/`PromptManager`) is
  never modified or called
- config/config.yaml: new `prompt_optimizer` section (`enabled`,
  `max_input_size`, `min_seconds_between_calls`), deliberately
  separate from the pre-existing `prompt:` section (EP-017)
- tests/EP055/test_prompt_optimizer.py: EP-055 test suite (`NAME =
  "EP055"`) -- argument-shape, gate, rate-limit (fake clock),
  resource-cap, positive/negative-path, `--template` loading (real,
  temporary-directory-backed, non-fake), `CommandRouter` dispatch
  equivalence, `Bootstrap` wiring tests, and (added during STEP 4) 4
  additional tests specifically proving the corrected gate ordering
  -- all against fake `ProviderManager` stand-ins where a fake is
  appropriate
- docs/architecture/designs/EP055_DESIGN.md: full design document,
  including the scope-definition discovery (Section 0-5), Owner
  Decisions D1-D9 (Section 20), and D10 (Section 17, added during
  STEP 3)
- docs/architecture/audits/EP055_ARCHITECTURE_AUDIT.md: EP-055
  Architecture Audit, Final Verdict PASS AFTER REMEDIATION (first
  pass: AUDIT PASSED WITH FINDINGS; Section 18 records the STEP 4 fix
  and its independent verification)

### Changed

- src/bootstrap.py: constructs `PromptOptimizerModule` after
  `ai_provider_manager` (pre-existing) is already wired, gated by
  `prompt_optimizer.enabled` (default `false`). `prompt` namespace
  registers even when disabled, reporting a disabled message for
  every action, matching every other skill's convention
- src/modules/test_module.py: registers the EP-055 test suite so
  `test EP055` and `test all` pick it up

### Security

- `prompt_optimizer.enabled` defaults to `false` and is re-checked on
  every dispatched action, not only at registration
- `prompt_optimizer.max_input_size` bounds how much text a single
  `prompt optimize` call may send to the AI provider; an input
  exceeding it is refused, never silently truncated
- `prompt_optimizer.min_seconds_between_calls` rate-limits
  AI-provider calls in-process (reset on restart)
- v1 is strictly return-only (Owner Decision D4): no `prompt save`
  action exists; no autonomous change to any configuration, prompt,
  or other component's behavior
- **Fixed during STEP 4 (Owner Decision D10):** argument-shape
  validation (no filesystem access) and the `prompt_optimizer.enabled`
  gate now both run before template resolution and the
  `max_input_size` check, so a disabled request can no longer read a
  template file from disk, disclose whether a named template exists,
  is empty, or its resolved path, or reveal the configured
  `max_input_size` value

### Validation

```
EP055 : 64 passed / 0 failed / 0 skipped
EP054 : 76 passed / 0 failed / 0 skipped
EP053 : 58 passed / 0 failed / 0 skipped
EP052 : 135 passed / 0 failed / 0 skipped
EP051 : 105 passed / 0 failed / 0 skipped
EP050 : 112 passed / 0 failed / 0 skipped
```

All regression figures above were independently reproduced from a
clean process both before and after the STEP 4 fix.

### STEP 3 -- Architecture Audit

First-pass verdict: EP-055 STEP 3 -- **AUDIT PASSED WITH FINDINGS**.
All nine Owner Decisions (D1-D9) confirmed correctly implemented with
zero findings against their literal text. Two related, non-blocking
ordering findings were identified independently of the Owner
Decisions:

1. **(originally MEDIUM)** `PromptOptimizerModule._optimize()`'s
   `--template` resolution performed a real filesystem read and could
   disclose a named template's existence, emptiness, or absolute
   resolved path via an error message before the `prompt_optimizer.
   enabled` gate was checked. No AI-provider call ever occurred, and
   template content was never disclosed.
2. **(originally LOW)** The `max_input_size` cap check ran before the
   same gate, allowing that non-secret, operator-configured numeric
   value to be observed via an error message while disabled --
   closely mirroring EP-054's own previously-accepted Finding 2.

File scope confirmed to exactly match the approved STEP 2 scope, with
zero unauthorized changes to `src/core/ai/prompt.py`,
`prompt_builder.py`, `prompt_manager.py` (EP-017 Prompt Engine, byte-
compared against the pre-EP-055 archive and confirmed identical),
`src/core/command_router.py`, `src/core/tool/`, `src/services/
ai_service.py`, `src/core/agent/`, `src/core/planning/`,
`src/core/scheduler/`, or any Phase 7/8 skill. See
`docs/architecture/audits/EP055_ARCHITECTURE_AUDIT.md` for the full
first-pass audit, including three independent mutation tests and
several live edge-case probes performed against the real, unmutated
code.

### STEP 4 -- Finalization (including remediation)

Unlike EP-054's STEP 4 (documentation sync only, findings left
unfixed), the owner explicitly approved Owner Decision D10 (option
(a)): fix both findings before closing EP-055. The fix was minimal
and behavior-preserving -- `_optimize()`'s argument-shape validation
was extracted into a new method with zero filesystem access, and the
`prompt_optimizer.enabled` gate now runs immediately afterward,
before template resolution or the `max_input_size` check. No public
interface, config key, or enabled-path behavior changed; all 52
pre-existing test assertions continued to pass unchanged, and 12 new
assertions (4 new test methods) were added specifically to prove the
corrected ordering.

The fix was independently verified two ways: (1) a reverted, pre-fix
scratch copy (never touching the real repository) was used to confirm
the new tests would have genuinely caught the original behavior --
one test raised a real `AssertionError` against the reverted code,
and another's core assertion demonstrably failed against it; (2) the
same three live probes from the first audit pass were re-run against
the real, fixed code and confirmed each now returns the standard
disabled message with no filesystem-fact or config-value disclosure.

`docs/architecture/audits/EP055_ARCHITECTURE_AUDIT.md` was updated in
place with a Section 18 remediation record -- the original first-pass
findings (Sections 1-17) were preserved verbatim, not edited or
removed, per the same "record both passes factually" precedent
`EP052_ARCHITECTURE_AUDIT.md` established. Release/project
documentation (`CHANGELOG.md`, `docs/BACKLOG.md`,
`docs/RELEASE_NOTES.md`, `docs/architecture/JARVIS_ROADMAP.md`)
synchronized to mark EP-055 COMPLETE / PASS AFTER REMEDIATION and
EP-056 (Capability Learning) as the next, not-started Engineering
Package.

**EP-055 is COMPLETE (PASS AFTER REMEDIATION -- both findings
identified during STEP 3 were fixed and independently verified during
STEP 4; zero open findings).**

---

## v0.1.13-ep054

Released: 2026-08-29

Status: EP-054 COMPLETE / PASSED WITH FINDINGS (STEP 1 Architecture
Discovery & Design, STEP 2 Implementation & Testing, STEP 3
Architecture Audit, STEP 4 Finalization all complete). STEP 3's final
verdict is **AUDIT PASSED WITH FINDINGS** -- one non-blocking MEDIUM
finding and one non-blocking LOW finding are documented and were not
fixed; this is not a clean, zero-finding pass.

EP-054's roadmap entry ("Self Reflection") had no functional
specification anywhere in the repository beyond Phase 9's one-sentence
goal. STEP 1 disclosed this explicitly rather than inventing scope,
surveyed the existing architecture, and recommended Owner Decision D1
= "Candidate A": on-demand session/conversation self-critique.

### Added

- src/skills/reflection/skill.py: `ReflectionModule`, the "reflect"
  `CommandModule` namespace -- `summary [count]` (ask the configured
  AI provider to critique the last `count` messages of the current
  conversation) and `recall [count]` (return previously persisted
  critiques, most recent first), plus `help`, dispatched through the
  existing, unmodified `CommandRouter.dispatch()`. Introduces no new
  backend Protocol (Owner Decision D1) -- composes `ConversationManager`
  (read-only), `ProviderManager`/`AIProvider` (via `get_current().ask()`,
  deliberately bypassing `AIService`'s conversation-mutating pipeline),
  and optional `MemoryService` directly
- config/config.yaml: new `reflection` section (`enabled`,
  `max_message_count`, `min_seconds_between_calls`,
  `persist_to_memory`)
- tests/EP054/test_reflection.py: EP-054 test suite (`NAME = "EP054"`)
  -- argument-shape, gate, rate-limit (fake clock), resource-cap,
  positive/negative-path, persistence, `CommandRouter` dispatch
  equivalence, and `Bootstrap` wiring tests, all against fake
  `ConversationManager`/`ProviderManager`/`MemoryService` stand-ins
- docs/architecture/designs/EP054_DESIGN.md: full design document,
  including the scope-definition discovery (Section 0-5) and Owner
  Decisions D1-D9 (Section 20)
- docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md: EP-054
  Architecture Audit, Final Verdict AUDIT PASSED WITH FINDINGS

### Changed

- src/bootstrap.py: constructs `ReflectionModule` after
  `ConversationManager`/`ProviderManager`/`MemoryService` (all
  pre-existing) are already wired, gated by `reflection.enabled`
  (default `false`). `reflect` namespace registers even when disabled,
  reporting a disabled message for every action, matching every other
  skill's convention
- src/modules/test_module.py: registers the EP-054 test suite so
  `test EP054` and `test all` pick it up

### Security

- `reflection.enabled` defaults to `false` and is re-checked on every
  dispatched action, not only at registration
- `reflection.max_message_count` bounds how much conversation history
  a single `reflect summary` call may send to the AI provider; an
  explicit count exceeding it is refused, never silently reduced
- `reflection.min_seconds_between_calls` rate-limits AI-provider calls
  in-process (reset on restart)
- v1 is strictly descriptive (Owner Decision D3): no autonomous change
  to any configuration, prompt, or other component's behavior
- `ReflectionModule` never appends to or mutates the conversation it
  reads from
- `reflection.persist_to_memory` defaults to `false`; `reflect recall`
  fails clearly if persistence is requested but unavailable

### Validation

```
EP054 : 76 passed / 0 failed / 0 skipped
test all : 6339 passed / 2 failed / 3 skipped
```

The 2 failures and 3 skips are the same pre-existing EP-046/EP-048/
EP-049 voice-stack/sandbox limitations already documented at EP-053's
completion, independently re-verified during the STEP 3 audit and
reconfirmed unrelated to and unmodified by EP-054.

### STEP 3 -- Architecture Audit

Final Verdict: EP-054 STEP 3 -- **AUDIT PASSED WITH FINDINGS**. Seven
of nine Owner Decisions (D1, D2, D3, D5, D6, D8, D9) confirmed
correctly implemented with zero findings; D4 and D7 are each
functionally correct but carry one finding apiece:

1. **(MEDIUM)** The design document's own Section 12 committed to a
   real, non-fake `MemoryService`-backed test once Owner Decision D4
   was approved; none exists in the registered suite. The audit
   independently built and ran a real `MemoryService`/`MemoryStore`
   integration probe and confirmed the actual integration works
   correctly -- a test-coverage gap, not a functional defect.
2. **(LOW)** The `max_message_count`-exceeded check runs before the
   `reflection.enabled` gate, allowing a non-secret config value to be
   observed via an error message while disabled -- confirmed, via
   dummy objects that raise on any call, that zero downstream calls
   occur; no gate or resource-limit bypass exists.

File scope confirmed to exactly match the approved STEP 2 scope, with
zero unauthorized changes to `src/core/command_router.py`, `src/core/
tool/`, any `src/core/ai/*` file, `src/core/memory/`, `src/core/
agent/`, `src/core/planning/`, `src/core/scheduler/`,
`src/services/ai_service.py`/`memory_service.py`, or any Phase 7/8
skill. See `docs/architecture/audits/EP054_ARCHITECTURE_AUDIT.md` for
the full audit, including three independent mutation tests and a real
`MemoryService` integration probe performed against the real,
unmutated code.

### STEP 4 -- Finalization

Per the STEP 3 audit's own "record, do not fix" rule, neither finding
was remediated during STEP 4 -- both remain documented and
non-blocking, exactly as the audit recorded them. Release/project
documentation (`CHANGELOG.md`, `docs/BACKLOG.md`,
`docs/RELEASE_NOTES.md`, `docs/architecture/JARVIS_ROADMAP.md`)
synchronized to mark EP-054 COMPLETE / PASSED WITH FINDINGS and
EP-055 (Prompt Optimizer) as the next, not-started Engineering
Package. No source, test, configuration, or dependency file was
modified during STEP 4.

**EP-054 is COMPLETE (PASSED WITH FINDINGS -- one non-blocking MEDIUM
finding and one non-blocking LOW finding, documented, not fixed).**

---

## v0.1.12-ep053

Released: 2026-08-29

Status: EP-053 COMPLETE / PASSED WITH FINDINGS (STEP 1 Architecture
Discovery/Design, STEP 2 Implementation & Testing, STEP 3 Architecture
Audit, STEP 4 Finalization all complete). STEP 3's final verdict is
**AUDIT PASSED WITH FINDINGS** -- one non-blocking MEDIUM finding is
documented and was not fixed; this is not a clean, zero-finding pass.

### Added

- src/skills/vision/backend.py: `VisionBackend` protocol -- the
  vision-interpretation contract (`image_info`, `extract_text`),
  mirroring the `ComputerUseBackend`/`BrowserBackend`/`FileBackend`
  pattern EP-050/EP-051/EP-052 already established
- src/skills/vision/local_backend.py: `LocalVisionBackend`, the sole
  real implementation -- local, read-only image interpretation built
  on Pillow (image decoding) and `pytesseract` (OCR, wrapping an
  external Tesseract binary), gated by resource limits
  (`vision.max_file_size_mb`, `vision.max_dimension`). Local-only:
  v1 contains no AI-provider/network path
- src/skills/vision/skill.py: `VisionModule`, the "vision"
  `CommandModule` namespace -- `info`, `ocr`, `help` -- dispatched
  through the existing, unmodified `CommandRouter.dispatch()`, exactly
  as every prior skill (`desktop`, `browser`, `file`, ...) already is
- config/config.yaml: new `vision` section (`enabled`,
  `allowed_roots`, `max_file_size_mb`, `max_dimension`) -- independent
  of `file.allowed_roots`, no runtime coupling to `FileBackend`
- requirements.txt: `Pillow==12.1.1`, `pytesseract==0.3.13` (plus a
  documented one-time external Tesseract system-binary install step)
- tests/EP053/test_vision.py: EP-053 test suite (`NAME = "EP053"`) --
  protocol conformance, argument-shape/gate/path-safety/dispatch
  tests against a `_FakeVisionBackend`, and real-Pillow filesystem/
  image behavior (including resource-limit enforcement) against
  `LocalVisionBackend`
- tests/EP053/test_vision_ocr_integration.py: a separate,
  intentionally unregistered real-Tesseract OCR check -- never
  imported by `test_vision.py`, `test_module.py`, or `TestRegistry`
- docs/architecture/designs/EP053_DESIGN.md: full design document,
  including Owner Decisions D1-D10 (Section 20)
- docs/architecture/audits/EP053_ARCHITECTURE_AUDIT.md: EP-053
  Architecture Audit, Final Verdict AUDIT PASSED WITH FINDINGS

### Changed

- src/bootstrap.py: constructs `LocalVisionBackend`/`VisionModule`
  after the existing EP-052 wiring, gated by `vision.enabled` (default
  `false`). `vision` namespace registers even when disabled, reporting
  a disabled message for every action, matching every other skill's
  convention
- src/modules/test_module.py: registers the EP-053 test suite so
  `test EP053` and `test all` pick it up

### Security

- `vision.enabled` defaults to `false` and is re-checked on every
  dispatched action, not only at registration
- `vision.allowed_roots` is an explicit, independently-configured
  allow-list; an empty list blocks every action -- no runtime
  dependency on `file.allowed_roots`/`FileBackend`
- Path traversal, absolute-path escapes, symlink-escape attempts, and
  malformed/NUL-byte paths are all rejected before any backend call
  (independently re-verified during the STEP 3 audit)
- `vision.max_file_size_mb`/`vision.max_dimension` bound resource
  consumption; both are genuinely enforced and cannot be bypassed
  through an alternate command path
- v1 is local-only and CPU-only: no image byte or path ever leaves the
  machine, and no GPU dependency was introduced
- `image_info` never requires the Tesseract binary (split
  availability); only `extract_text`/`vision ocr` does

### Validation

```
EP053 : 58 passed / 0 failed / 0 skipped
test all : 6263 passed / 2 failed / 3 skipped
```

The 2 failures and 3 skips are pre-existing EP-046/EP-048/EP-049
voice-stack/sandbox limitations (`openwakeword`/`tflite-runtime`
having no Linux wheel in this environment, and real-hardware-only
scenarios already documented by their own design documents as
skippable), independently re-traced to their root causes during the
STEP 3 audit and reconfirmed unrelated to and unmodified by EP-053.

### STEP 3 -- Architecture Audit

Final Verdict: EP-053 STEP 3 -- **AUDIT PASSED WITH FINDINGS**. All
ten Owner Decisions (D1-D10) confirmed correctly implemented; all
eight critical security questions resolved safely (NO); file scope
confirmed to exactly match the approved STEP 2 scope, with zero
unauthorized changes to `src/core/command_router.py`, `src/core/
tool/`, `src/core/ai/provider.py`, or `src/skills/desktop/`/
`browser/`/`files/`. One non-blocking MEDIUM finding was identified:
`LocalVisionBackend` enforces `max_dimension` after full image decode
rather than before, contrary to `EP053_DESIGN.md`'s own stated D5
intent -- the limit is still always enforced and no unsafe result is
ever returned. See
`docs/architecture/audits/EP053_ARCHITECTURE_AUDIT.md` for the full
audit, including two independent mutation tests and live
security probes performed against the real, unmutated code.

### STEP 4 -- Finalization

Per explicit owner instruction, the STEP 3 MEDIUM finding was **not**
remediated during STEP 4 (no approved remediation exists for it, and
none was authorized) -- it remains documented and non-blocking, exactly
as the audit recorded it. Release/project documentation
(`CHANGELOG.md`, `docs/BACKLOG.md`, `docs/RELEASE_NOTES.md`,
`docs/architecture/JARVIS_ROADMAP.md`) synchronized to mark EP-053
COMPLETE / PASSED WITH FINDINGS and EP-054 (Self Reflection) as the
next, not-started Engineering Package. No source, test, configuration,
or dependency file was modified during STEP 4.

**EP-053 is COMPLETE (PASSED WITH FINDINGS -- one non-blocking MEDIUM
finding, documented, not fixed).**

---

## v0.1.11-ep052

Released: 2026-08-28

Status: EP-052 COMPLETE (STEP 1 Architecture Discovery/Design, STEP 2
Implementation & Testing, STEP 3 Architecture Audit with one
narrowly-scoped remediation, STEP 4 Finalization all complete)

### Added

- src/skills/files/backend.py: `FileBackend` protocol -- the
  file-automation contract (`list`, `exists`, `stat`, `read`, `write`,
  `copy`, `move`, `mkdir`, `delete`), mirroring the
  `ComputerUseBackend`/`BrowserBackend` pattern EP-050/EP-051 already
  established
- src/skills/files/local_backend.py: `LocalFileBackend`, the sole real
  implementation -- direct local-filesystem operations gated by a
  layered security model (enabled flag, destructive-action
  permission, allowed-roots allow-list, denied-paths deny-list, path
  traversal / absolute-path protection, source/destination
  validation, overwrite protection, non-recursive delete, UTF-8-only
  file content)
- src/skills/files/skill.py: `FileModule`, the \"file\" `CommandModule`
  namespace -- `list`, `exists`, `stat`, `read`, `write`, `copy`,
  `move`, `mkdir`, `delete`, `help` -- dispatched through the
  existing, unmodified `CommandRouter.dispatch()`, exactly as every
  prior skill (`desktop`, `browser`, ...) already is
- config/config.yaml: new `file` section (`enabled`,
  `allow_destructive`, `allowed_roots`, `denied_paths`)
- tests/EP052/test_file.py: EP-052 test suite (`NAME = "EP052"`) --
  protocol conformance, argument-shape/gate/path-safety/dispatch
  tests against a `_FakeFileBackend`, and real-filesystem CRUD/
  overwrite/non-recursive-delete/UTF-8 behavior against
  `LocalFileBackend` in a disposable `tempfile.TemporaryDirectory()`
  (never the repository root or an operator's home directory)
- docs/architecture/designs/EP052_DESIGN.md: full design document,
  including Owner Decisions D1-D11 (Section 20) and D11's STEP 3
  Windows-path-tokenization remediation record
- docs/architecture/audits/EP052_ARCHITECTURE_AUDIT.md: EP-052
  Architecture Audit, Final Verdict PASS AFTER REMEDIATION

### Changed

- src/core/command_router.py: minimal, owner-authorized fix (Owner
  Decision D11) to the command tokenizer so Windows-style backslash
  paths passed to `file` actions are preserved rather than corrupted.
  No other `CommandRouter` behavior changed
- src/bootstrap.py: constructs `LocalFileBackend`/`FileModule` after
  the existing EP-051 wiring, gated by `file.enabled` (default
  `false`), wrapped so invalid `file.*` configuration disables the
  subsystem for that run (logged) instead of crashing startup.
  `file` namespace registers even when disabled, reporting a disabled
  message for every action, matching every other skill's convention
- src/modules/test_module.py: registers the EP-052 test suite so
  `test EP052` and `test all` pick it up

### Security

- `file.enabled` defaults to `false` and is re-checked on every
  dispatched action, not only at registration
- `file.allow_destructive` gates `move`/`delete`/overwriting `write`/
  `copy` separately from read and non-destructive-write actions
- `file.allowed_roots` is an explicit allow-list; an empty list blocks
  every action. `file.denied_paths` further excludes specific paths
  inside an allowed root
- Path traversal and absolute-path escapes are rejected before any
  backend call; destructive permission never bypasses path-safety
  checks
- `delete` is non-recursive only -- a non-empty directory is refused
- File content is UTF-8-only; a non-UTF-8 read/write is refused
  cleanly rather than corrupting or silently transcoding data

### Validation

```
EP052 : 135 passed / 0 failed / 0 skipped
```

Focused regression (EP-050, EP-051, and prior integration EPs)
unchanged. Two pre-existing, sandbox-only environment failures
(`sounddevice`/PortAudio unavailable in this Linux sandbox, affecting
EP-046/EP-048's own suites) remain documented as unrelated to and
unmodified by EP-052, consistent with the same condition already
disclosed against EP-049/EP-051 above.

### STEP 3 -- Architecture Audit / Remediation

Final Verdict: EP-052 STEP 3 -- PASS AFTER REMEDIATION. One
narrowly-scoped defect was found and fixed: `CommandRouter`'s command
tokenizer corrupted Windows-style backslash paths before they reached
`FileModule`. Owner Decision D11 explicitly authorized the minimal
`src/core/command_router.py` fix described above. No other defect,
security-gate weakening, or scope expansion was introduced during
remediation. See
`docs/architecture/audits/EP052_ARCHITECTURE_AUDIT.md` for the full
audit.

### STEP 4 -- Finalization

Final EP-052 file set, Owner Decisions D1-D11, CRUD action set, and
security-gate set re-verified directly against the live
implementation. EP-052 test suite re-run: 135/135, unchanged from
STEP 3. No source, test, or configuration file was modified during
STEP 4.

**EP-052 is COMPLETE.**

---

## v0.1.10-ep043

Released: 2026-08-20

Status: EP-043 COMPLETE (STEP 1 stopped pending owner scope
confirmation, per `EP043_STEP1_REPORT.md`; owner confirmed scope,
STEP 2 implemented it, STEP 3 hardened the API contract, STEP 4
finalized and archived it)

### Added

- src/core/api/api_error.py: `ApiError` base and four subclasses
  (`ApiValidationError` 400, `ApiNotFoundError` 404,
  `ApiMethodNotAllowedError` 405, `ApiInternalError` 500), each
  carrying its own HTTP status code and machine-readable `code`
- src/core/api/dto.py: `CommandRequest`, `CommandResponse`,
  `HealthResponse`, `ErrorPayload` -- the REST API's external JSON
  contract, independent of any internal domain object
- src/core/api/api_router.py: `ApiRouter`, a thin bridge from a
  `(module, action, arguments)` triple to the existing, shared
  `CommandRouter.dispatch()` -- the exact same entry point
  `InteractiveShell` and `TelegramRouter` already use. No business
  logic, no command parsing of its own; arguments are shell-quoted
  before being rejoined so values containing spaces round-trip safely
- src/core/api/rest_api_server.py: `RestApiServer`, an HTTP transport
  built entirely on the Python standard library
  (`http.server.ThreadingHTTPServer`) -- no new third-party
  dependency. Binds `127.0.0.1` by default, serves on a background
  daemon thread, and exposes `GET /health`, `GET /api/v1/status`, and
  `POST /api/v1/commands`. Centralized error handling maps every
  `ApiError` to its status code and converts any unexpected exception
  to a generic `ApiInternalError` -- no stack trace is ever returned
  to a client
  - EP-043 test suite (tests/EP043/test_rest_api.py), `NAME = "EP043"`
    (single combined suite; not split into a same-named Service/Module
    pair, to avoid triggering the pre-existing `TestRegistry`
    NAME-collision technical debt -- see "Known technical debt" below)
- src/bootstrap.py: `_build_rest_api_server()`, `shutdown()`, and the
  `rest_api_server` property. `RestApiServer` is built and (if
  `api.enabled`) started inside `initialize()`, after
  `CommandRouter`/`InteractiveShell` are built, so `ApiRouter` always
  receives the fully-populated router
- config/config.yaml: new `api:` section (`enabled: false`,
  `host: "127.0.0.1"`, `port: 8080`)
- docs/architecture/designs/EP043_DESIGN.md: full design document,
  including the owner-confirmed scope, the deliberate `api.enabled`
  default deviation from the implementation prompt's illustrative
  example, and the no-new-dependency decision

### Changed

- src/main.py: one line added -- `bootstrap.shutdown()` is now called
  after `shell.run()` returns, so a clean CLI exit also stops a
  running `RestApiServer` and releases its bound port. No-op whenever
  `rest_api_server` is `None` (the default)

### Design decisions worth noting

- `api.enabled` defaults to `false`, unlike EP-039/040/041's `true`
  default. Every prior EP-038..042 subsystem is a stateless, per-call
  outbound client with no observable effect when idle; `RestApiServer`
  is Jarvis's first component that binds and listens on a real network
  socket as a side effect of `Bootstrap.initialize()`. Defaulting to
  `false` keeps every existing EP-001..042 test that constructs a real
  `Bootstrap` for wiring checks alone (none of which include an `api`
  section) unaffected, and avoids introducing port-conflict flakiness
- No new dependency was added. `RestApiServer` uses only
  `http.server`/`json`/`threading` from the standard library --
  `requirements.txt` is unchanged. This mirrors EP-042's
  `EmailService` precedent (`imaplib`/`email` only) and resolves the
  STEP 1 investigation's open "framework/library" ambiguity in the
  lowest-risk way available given no design document specified one
- A successfully routed command request always returns HTTP `200`,
  even when the command's own result is `success: false`. Only
  REST-transport-level problems (malformed JSON, missing `module`, an
  unknown path, an unsupported method) produce a non-2xx status. See
  `EP043_DESIGN.md` section 9 for the full rationale
- `RestApiServer` is architecturally a Bootstrap-level sibling of
  `InteractiveShell`, not a `Core -> Service -> Module` subsystem --
  it is Jarvis's first inbound listener, a different architectural
  role from every prior integration EP's outbound, per-call client

### STEP 3 — API Contract Hardening (Added)

- src/core/api/api_error.py: `ApiUnsupportedMediaTypeError` (415) --
  new error for a `POST /api/v1/commands` request whose `Content-Type`
  header is present and not `application/json`
- src/core/api/rest_api_server.py: `Content-Type` policy -- a present
  `Content-Type` other than `application/json` (parameters like
  `; charset=utf-8` are ignored) now returns 415; a missing header is
  still treated leniently and parsed as JSON (documented, not
  changed)
- tests/EP043/test_rest_api.py: 45 new assertions -- Content-Type
  policy (415, charset tolerance, true header-absence leniency via a
  raw `http.client` request), wrong-field-type and unexpected-field
  validation, a `/api/v1/status` DTO shape assertion, five repeated
  start/stop cycles with a thread-leak check, malformed-`api.port`
  Bootstrap robustness (bad type and out-of-range), and one
  end-to-end "external client" test (health -> status -> command ->
  clean shutdown) using only the documented public contract
- EP043_STEP3_REPORT.md, docs/architecture/designs/EP043_DESIGN.md
  (contract-hardening addendum)

### STEP 3 — Fixed

- src/core/api/rest_api_server.py: `RestApiServer.start()` previously
  caught only `OSError` when binding; a malformed `api.port` (wrong
  type, e.g. a string, or out of the 0-65535 range) raised an
  uncaught `TypeError`/`OverflowError` that would have crashed
  `Bootstrap.initialize()` instead of degrading to "REST API
  disabled" like every other invalid-configuration case. Now catches
  `OSError`/`TypeError`/`ValueError`/`OverflowError` uniformly

### STEP 3 — Explicitly reviewed, unchanged

- The `success: false` -> HTTP `200` status-code policy (STEP 2's
  decision, `EP043_DESIGN.md` section 10) was re-reviewed against
  STEP 3's HTTP-semantics requirement and retained as-is; no
  business-outcome-to-status mapping was introduced
- `api.enabled` default (`false`) and `api.host` default
  (`"127.0.0.1"`) are unchanged

### Known technical debt (pre-existing, not introduced by EP-043)

Same `TestRegistry` `NAME.upper()` collision documented for EP-042
below. EP-043 sidesteps it entirely by registering a single `EP043`
suite rather than a same-named Service/Module pair.

### Validation

```
EP043 : 83 passed / 0 failed / 0 skipped
```

`test all`: 5459 passed / 0 failed / 0 skipped (previous baseline
5414 + STEP 3's 45 new assertions). `ruff check` on every new/changed
file: clean. `py_compile` across the full `src/` + `tests/` tree:
clean. No leaked `jarvis-rest-api` threads and port `8080` confirmed
free after a full regression run.

### STEP 4 — Finalization & Release Readiness

Audit-only step: re-verified architecture, API contract,
configuration, and lifecycle against the live code (not assumed from
prior reports) and found no discrepancy and no blocking defect, so no
source file was changed. `docs/architecture/designs/EP043_DESIGN.md`
gained a `## 22. STEP 4 Addendum` consolidating the Implemented/
Deferred split into one explicit reference. `VERSION` and
`PROJECT_MANIFEST.md` were checked against every prior EP's actual
convention (neither has ever been updated per-EP) and deliberately
left unchanged — see `EP043_STEP4_REPORT.md` §8-9. Test/regression/
ruff/compile results are unchanged from STEP 3 (83/5459/clean/clean),
confirmed by re-execution rather than assumed. Final archive:
`jarvis-ep043-complete.zip` (`jarvis-ep043-step3-complete.zip`
retained, untouched, as the prior recovery point). Full detail:
`EP043_STEP4_REPORT.md`.

**EP-043 is COMPLETE.**

---

## v0.1.9-ep042

Released: 2026-08-20

Status: COMPLETE (STEP 1-4 complete; STEP 3 Deep Audit -- Final
Verdict: EP042 STEP 3 -- PASS)

### Added

- src/core/email/email_result.py: `EmailFolder`, `EmailAttachment`,
  `EmailMessageSummary`, `EmailMessage`, `EmailResult` -- frozen
  dataclasses describing normalized IMAP mailbox/message data. Pure
  data, no IMAP/network call in this module
- src/core/email/email_error.py: flat `EmailError` exception hierarchy
  (`EmailError`, `EmailAuthenticationError`, `EmailConnectionError`,
  `EmailTimeoutError`, `EmailTLSError`, `EmailMailboxError`,
  `EmailMessageNotFoundError`, `EmailSearchError`,
  `EmailProtocolError`), mirroring `DiscordError`'s pattern from
  EP-041
- src/core/email/__init__.py: package docstring and public re-exports
- src/services/email_service.py: `EmailService`, a config-driven,
  read-only wrapper around a standard, provider-independent IMAP
  server, using the Python standard library (`imaplib` + `email`)
  only -- no third-party dependency, no provider-specific API (Gmail
  API, Microsoft Graph, Outlook API), no OAuth. Exposes exactly four
  operations -- `list_folders()`, `list_messages(folder, limit)`,
  `get_message(folder, uid)`, `search_messages(folder, criteria)` --
  no send/reply/forward/delete/move/flag method exists anywhere.
  Every mailbox `SELECT` is performed read-only (IMAP `EXAMINE`
  semantics). Username/password are read via `os.environ` at the
  start of every operation call (never at `__init__`, never cached on
  `self` beyond the call, never logged), using the two configured
  environment-variable *names*
  (`email.imap_username_env_var`/`email.imap_password_env_var`);
  missing/blank credentials raise `EmailAuthenticationError` before
  any connection is opened. `connection_factory` is an injectable,
  optional callable, defaulting to a real
  `imaplib.IMAP4_SSL`/`IMAP4` connection, enabling dependency-free
  test doubles. All operations use IMAP `UID` command variants
  (`UID SEARCH`, `UID FETCH`), with SEARCH results explicitly sorted
  by numeric UID rather than trusting server-returned order.
  `EmailServiceError` (raised only from `__init__`, for invalid
  `email.*` configuration) is defined here, not in
  `src/core/email/email_error.py`, mirroring `DiscordServiceError`'s
  split from `DiscordError`
  - EP-042 test suite (tests/EP042/test_email_service.py)
- src/modules/email_module.py: `EmailModule`, the "email" CLI
  namespace (`folders`, `list`, `message`, `search`, `help`). A pure,
  additive translation layer: calls `EmailService`'s existing public
  methods unchanged and catches `EmailError` to format
  `CommandResult(success=False, ...)`, matching `DiscordModule`'s
  pattern exactly. Never reads or handles IMAP credentials, never
  imports `imaplib`
  - EP-042 test suite (tests/EP042/test_email_module.py)
- config/config.yaml: new `email` section (`enabled`, `imap_host`,
  `imap_port`, `tls_mode`, `imap_username_env_var`,
  `imap_password_env_var`, `default_mailbox`,
  `default_message_limit`, `timeout_seconds` -- deliberately no
  credential value key)

### Changed

- src/bootstrap.py: constructs `EmailService` (and registers
  `EmailModule`, once construction is confirmed) after the existing
  EP-041 wiring, gated by `email.enabled` (default `false` --
  deliberately unlike EP-039/040/041's `true` default, since IMAP has
  no safe universal default host) and wrapped in a
  `try/except EmailServiceError` so invalid `email.*` configuration
  disables the subsystem for that run (logged) instead of crashing
  startup. Exposes a new `email_service` property, mirroring the
  EP-039/040/041 pattern. No cross-EP hard-dependency gate; this
  subsystem has no dependency on any other Engineering Package's
  service or engine
- src/modules/test_module.py: registers the EP-042 test suite so
  `test EP042` and `test all` pick it up

### Fixed

(Found and fixed during STEP 3 Deep Audit, before this version was
released -- not a post-release regression)

- Message/header decoding no longer raises an untyped `LookupError`
  when a message declares a malformed/unrecognized MIME charset
  (e.g. a nonstandard or misspelled encoded-word charset) -- both
  header decoding and body-part decoding now fall back to a
  best-effort UTF-8 decode instead of crashing the calling operation
- To/Cc headers are now RFC 2047-decoded the same way Subject/From
  already were (previously only comma-split, undecoded)
- `list_messages`/`search_messages` now explicitly sort IMAP UIDs
  numerically ascending before determining "most recent"/order, since
  RFC 3501 does not guarantee `SEARCH` results are returned in any
  particular order

### Security

- IMAP username/password are environment-only -- read via
  `os.environ` at call time, never accepted from or written to
  `config/config.yaml` or any other config file; only the two
  environment-variable *names* are configurable
- Credentials never stored in config
- Credentials never exposed in logs, exceptions, or CLI output --
  every error message in this subsystem is built from fixed text
  and/or non-secret server response text, never from the credential
  values
- TLS is mandatory -- `email.tls_mode` only accepts `"ssl"` (implicit
  TLS/IMAPS) or `"starttls"`; no code path connects over plaintext
  IMAP. Certificate validation uses `ssl.create_default_context()`,
  with no configuration option to disable it
- Every mailbox is opened read-only (`SELECT ... readonly=True`, IMAP
  `EXAMINE` semantics) -- this subsystem cannot set the `\Seen` flag
  or otherwise mutate a mailbox as a side effect of any operation

### Known limitations

- No SMTP / message-sending capability anywhere in this subsystem
- No reply, forward, delete, move, or flag/mark (read/unread)
  operation exists anywhere in this subsystem
- No provider-specific API (Gmail API, Microsoft Graph, Outlook API)
- No OAuth2 authentication
- No background/scheduled polling and no `IDLE` connection -- every
  operation opens one short-lived connection and closes it before
  returning
- No EventBus integration
- No Tool Engine integration (deferred, matching EP-039/040/041)
- No upper bound on retrieved message size -- `get_message` fetches
  the full message body for the requested UID; this was not part of
  the owner-confirmed scope
- `email.enabled` defaults to `false`, unlike EP-039/040/041's `true`
  default (see "Changed" above for rationale)

### Validation

EP042 Service : 55 passed / 0 failed / 0 skipped
EP042 Module  : 28 passed / 0 failed / 0 skipped
EP041         : 39 passed / 0 failed / 0 skipped (regression, unchanged)
EP040         : 25 passed / 0 failed / 0 skipped (regression, unchanged)
EP039         : 36 passed / 0 failed / 0 skipped (regression, unchanged)
EP038         : 30 passed / 0 failed / 0 skipped (regression, unchanged)
EP037         : 87 passed / 0 failed / 0 skipped (regression, unchanged)
EP036         : 101 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP2   : 48 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP3   : 53 passed / 0 failed / 0 skipped (regression, unchanged)
EP035         : 143 passed / 0 failed / 0 skipped (regression, unchanged)
EP034         : 113 passed / 0 failed / 0 skipped (regression, unchanged)
EP033         : 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP001         : 20 passed / 0 failed / 0 skipped (regression, unchanged)

`test all` was run: 5376 passed / 0 failed / 0 skipped.

### STEP 3 — Deep Audit / Verification / Hardening

Final Verdict: EP042 STEP 3 -- PASS WITH NOTES. Three defects found
and fixed (see "Fixed" above), one Bootstrap-level test-coverage gap
closed (real `Bootstrap().initialize()` enabled/disabled wiring
tests, matching the EP-041 precedent), no P0 (security/data-mutation)
issues found. One pre-existing, out-of-scope technical-debt item was
identified and deliberately left unfixed: `TestRegistry` keys test
suites by `NAME.upper()`, so of the two EP-042 test classes sharing
`NAME = "EP042"` (`EmailServiceTest`, `EmailModuleTest`), only the
one imported last is reachable through the CLI `test EP042` command.
This predates EP-042 (the same collision exists for every prior
integration EP's Service/Module test pair since at least EP-038) and
should be addressed by a separate future maintenance EP, not here.

EP-042 is now fully complete through STEP 4.

---

## v0.1.8-ep041

Released: 2026-08-19

Status: COMPLETE (STEP 1-4 complete; STEP 4 Architecture Audit --
Final Verdict: EP041 STEP 4 -- PASS)

### Added

- src/core/discord/discord_result.py: `DiscordResult`, a frozen
  dataclass describing the outcome of one successful Discord REST
  API v10 call (`operation`, `status_code`, `data` -- the parsed
  JSON response body, exactly as Discord returns it). Pure data, no
  HTTP call in this module
- src/core/discord/discord_error.py: flat `DiscordError` exception
  hierarchy (`DiscordError`, `DiscordAuthenticationError`,
  `DiscordNotFoundError`, `DiscordRateLimitError`,
  `DiscordTimeoutError`, `DiscordAPIError`), mirroring
  `GitHubError`'s split from `requests.exceptions` in EP-039
- src/core/discord/__init__.py: package docstring and public
  re-exports
- src/services/discord_service.py: `DiscordService`, a config-driven,
  read-only wrapper around the Discord REST API (v10). Exposes
  exactly five operations -- `get_guild()`, `list_guild_channels()`,
  `get_channel()`, `get_guild_member()`, `get_message()` -- no
  create/update/delete/moderation/webhook/role/reaction/invite
  method exists. Owns the sole `requests.get(...)` invocation point
  in this subsystem. `DISCORD_TOKEN` is read via `os.environ` at the
  start of every operation call (never at `__init__`, never cached
  on `self` beyond the call, never logged); missing/blank token
  raises `DiscordAuthenticationError` before any HTTP call is
  attempted. `guild_id`/`channel_id`/`user_id`/`message_id` path
  segments are URL-quoted (`urllib.parse.quote`). `session` is an
  injectable, optional `requests.Session`-like parameter, defaulting
  to a real `requests.Session()`, enabling dependency-free test
  doubles. `DiscordServiceError` (raised only from `__init__`, for
  invalid `discord.*` configuration) is defined here, not in
  `src/core/discord/discord_error.py`, mirroring `GitHubServiceError`'s
  split from `GitHubError` in EP-039
  - EP-041 test suite (tests/EP041/test_discord_service.py)
- src/modules/discord_module.py: `DiscordModule`, the "discord" CLI
  namespace (`guild`, `channels`, `channel`, `member`, `message`,
  `help`). A pure, additive translation layer: calls `DiscordService`'s
  existing public methods unchanged and catches `DiscordError` to
  format `CommandResult(success=False, ...)`, matching `GitHubModule`'s
  pattern exactly. Never reads or handles `DISCORD_TOKEN`
  - EP-041 test suite (tests/EP041/test_discord_module.py)
- config/config.yaml: new `discord` section (`enabled`,
  `api_base_url`, `timeout_seconds` -- deliberately no token key)

### Changed

- src/bootstrap.py: constructs `DiscordService` (and registers
  `DiscordModule`, once construction is confirmed) after the existing
  EP-040 wiring, gated by `discord.enabled` (default `true`) and
  wrapped in a `try/except DiscordServiceError` so a missing/blank
  token or invalid `discord.*` configuration disables the subsystem
  for that run (logged) instead of crashing startup. Exposes a new
  `discord_service` property, mirroring the EP-039/EP-040 pattern.
  No cross-EP hard-dependency gate; this subsystem has no dependency
  on any other Engineering Package's service or engine
- src/modules/test_module.py: registers the EP-041 test suite so
  `test EP041` and `test all` pick it up

### Security

- `DISCORD_TOKEN` is environment-only -- read via `os.environ` at
  call time, never accepted from or written to `config/config.yaml`
  or any other config file
- Token never stored in config
- Token never exposed in logs, exceptions, or CLI output -- every
  error message in this subsystem is built from fixed text and/or
  the HTTP response, never from the token value

### Known limitations

- No Discord Gateway/WebSocket connection is opened anywhere in this
  subsystem -- every operation is a single, stateless HTTP GET
- No message history retrieval. Discord's REST API does technically
  support bulk historical message retrieval
  (`GET /channels/{channel.id}/messages`) without Gateway state, but
  it was deliberately not included in this EP's confirmed scope
- No write operations (create/send/edit/delete)
- No moderation operations
- No role management
- No webhooks
- No Tool Engine integration (deferred, matching EP-039/EP-040)

### Validation

EP041       : 39 passed / 0 failed / 0 skipped
EP040       : 25 passed / 0 failed / 0 skipped (regression, unchanged)
EP039       : 36 passed / 0 failed / 0 skipped (regression, unchanged)
EP038       : 30 passed / 0 failed / 0 skipped (regression, unchanged)
EP037       : 87 passed / 0 failed / 0 skipped (regression, unchanged)
EP036       : 101 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP2 : 48 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP3 : 53 passed / 0 failed / 0 skipped (regression, unchanged)
EP035: 143 passed / 0 failed / 0 skipped (regression, unchanged)
EP034: 113 passed / 0 failed / 0 skipped (regression, unchanged)
EP033: 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP001: 20 passed / 0 failed / 0 skipped (regression, unchanged)

`test all` was not run.

### STEP 4 — Architecture Audit

Final Verdict: EP041 STEP 4 -- PASS. See
`docs/architecture/audits/EP041_ARCHITECTURE_AUDIT.md` for the full
audit (architecture layering, scope compliance, security, error
handling, CLI boundary, EP-012/EP-031/previous-EP integrity,
documentation consistency -- all PASS, no architecture debt found).

EP-041 is now fully complete through STEP 4.

---

## v0.1.7-ep040

Released: 2026-08-15

Status: STEP 1-3 complete (STEP 4 Architecture Audit pending)

### Added

- src/core/telegram_info/telegram_info_result.py: `TelegramInfoResult`,
  a frozen dataclass describing the outcome of one successful
  `get_chat` call (`chat_id`, `data` -- the chat's fields exactly as
  `telegram.Chat.to_dict()` returns them). Pure data, no Bot API call
  in this module
- src/core/telegram_info/telegram_info_error.py: flat
  `TelegramInfoError` exception hierarchy (`TelegramInfoError`,
  `TelegramInfoAuthenticationError`, `TelegramInfoNotFoundError`,
  `TelegramInfoRateLimitError`, `TelegramInfoTimeoutError`,
  `TelegramInfoNetworkError`, `TelegramInfoAPIError`), mapped onto
  `python-telegram-bot`'s actual `telegram.error` hierarchy
  (`InvalidToken`/`Forbidden`/`BadRequest`/`RetryAfter`/`TimedOut`/
  `NetworkError`), the same way `GitHubError` was mapped onto
  `requests.exceptions` in EP-039
- src/core/telegram_info/__init__.py: package docstring and public
  re-exports
- src/services/telegram_info_service.py: `TelegramInfoService`, a
  config-driven, read-only wrapper exposing exactly one operation --
  `get_chat(chat_id)`. Owns the sole `Bot.get_chat(...)` invocation
  point in this subsystem. Constructs its own, **independent**
  `telegram.Bot` instance -- never imports or instantiates
  `TelegramClient` (EP-012). `telegram.token` (EP-012's existing key)
  is read read-only and validated at construction (missing/blank ->
  `TelegramInfoServiceError`, raised before any Bot/network call is
  attempted). `bot` is an injectable, optional parameter, enabling
  dependency-free test doubles
  - EP-040 test suite (tests/EP040/test_telegram_info_service.py)
- src/modules/telegram_info_module.py: `TelegramInfoModule`, the
  "telegram-info" CLI namespace (`chat`, `help`). A pure, additive
  translation layer: calls `TelegramInfoService`'s single public
  method unchanged and catches `TelegramInfoError` to format
  `CommandResult(success=False, ...)`, matching `GitHubModule`'s
  pattern exactly. Never imports `telegram` and never reads
  `telegram.token`
  - EP-040 test suite (tests/EP040/test_telegram_info_module.py)
- config/config.yaml: new `telegram_info` section (`enabled`,
  `timeout_seconds` -- deliberately no token key), added immediately
  after EP-012's existing, unmodified `telegram` section

### Changed

- src/bootstrap.py: constructs `TelegramInfoService` (and registers
  `TelegramInfoModule`, once construction is confirmed) after the
  existing EP-039 wiring, gated by `telegram_info.enabled` (default
  `true`) and wrapped in a `try/except TelegramInfoServiceError` so a
  missing/blank token or invalid `telegram_info.*` configuration
  disables the subsystem for that run (logged) instead of crashing
  startup. Like `GitHubService`, there is no cross-EP hard-dependency
  gate. EP-012's own Bootstrap wiring (`TelegramClient`/
  `TelegramService`/`TelegramModule`) is untouched
- src/modules/test_module.py: registers the EP-040 test suite so
  `test EP040` and `test all` pick it up

### EP-012 boundary

EP-012 "Telegram Gateway" was not modified. All four of its files
(`src/core/telegram/telegram_client.py`, `telegram_router.py`,
`src/services/telegram_service.py`, `src/modules/telegram_module.py`)
were confirmed byte-identical before and after this implementation.
EP-040 does not use `TelegramClient`, `fetch_updates()`,
`get_updates()`, any update offset/cursor, Telegram polling, or
`TelegramRouter`.

### Security

`telegram.token` is never duplicated into a second configuration key,
never logged, and never appears in any exception message or CLI
output -- verified directly by a dedicated test asserting a fixed fake
token value never appears in any exception message across seven
different error scenarios. No new dependency was introduced.

### Known limitations

- Scope is intentionally limited to single-chat metadata lookup only
  (`get_chat`). Message history and chat discovery/listing are not
  implemented because the Telegram Bot API does not support them --
  a hard capability boundary, not a deferred future step
- `get_chat` requires an already-known chat id; there is no way to
  enumerate chats the bot has access to

### Validation

EP040       : 25 passed / 0 failed / 0 skipped
EP039       : 36 passed / 0 failed / 0 skipped (regression, unchanged)
EP038       : 30 passed / 0 failed / 0 skipped (regression, unchanged)
EP037       : 87 passed / 0 failed / 0 skipped (regression, unchanged)
EP036       : 101 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP2 : 48 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP3 : 53 passed / 0 failed / 0 skipped (regression, unchanged)
EP033: 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP034: 113 passed / 0 failed / 0 skipped (regression, unchanged)
EP035: 143 passed / 0 failed / 0 skipped (regression, unchanged)
EP001: 20 passed / 0 failed / 0 skipped (regression, unchanged)

`test all` was not run.

---

## v0.1.6-ep039

Released: 2026-08-14

Status: STEP 1-3 complete (STEP 4 Architecture Audit pending)

### Added

- src/core/github/github_result.py: `GitHubResult`, a frozen dataclass
  describing the outcome of one successful GitHub REST API call
  (`operation`, `status_code`, `data` -- the parsed JSON response body,
  exactly as GitHub returns it). Pure data, no HTTP call in this module
- src/core/github/github_error.py: flat `GitHubError` exception
  hierarchy (`GitHubError`, `GitHubAuthenticationError`,
  `GitHubNotFoundError`, `GitHubRateLimitError`, `GitHubTimeoutError`,
  `GitHubNetworkError`, `GitHubAPIError`), modeled directly on
  `src/core/ai/claude_provider.py`'s existing
  `ProviderAuthenticationError`/`ProviderRateLimitError`/etc. split
- src/core/github/__init__.py: package docstring and public re-exports
- src/services/github_service.py: `GitHubService`, a config-driven,
  read-only wrapper around the GitHub REST API. Exposes exactly eight
  operations -- `get_repository()`, `list_repositories()`,
  `list_issues()`, `get_issue()`, `list_pull_requests()`,
  `get_pull_request()`, `list_commits()`, `get_commit()` -- no
  create/update/delete/comment/merge/release method exists. Owns the
  sole `requests.get(...)` invocation point in this subsystem.
  `GITHUB_TOKEN` is read via `os.environ.get()` at the start of every
  operation call (never at `__init__`, never cached, never logged);
  missing/blank token raises `GitHubAuthenticationError` before any
  HTTP call is attempted. `owner`/`repo`/`number`/`sha` path segments
  are URL-quoted (`urllib.parse.quote`). `session` is an injectable,
  optional `requests.Session`-like parameter, defaulting to a real
  `requests.Session()`, enabling dependency-free test doubles.
  `GitHubServiceError` (raised only from `__init__`, for invalid
  `github.*` configuration) is defined here, not in
  `src/core/github/github_error.py`, mirroring how
  `GitServiceError` is distinct from `GitError` in EP-038
  - EP-039 test suite (tests/EP039/test_github_service.py)
- src/modules/github_module.py: `GitHubModule`, the "github" CLI
  namespace (`repo`, `repos`, `issues`, `issue`, `prs`, `pr`,
  `commits`, `commit`, `help`). A pure, additive translation layer:
  calls `GitHubService`'s existing public methods unchanged and
  catches `GitHubError` to format `CommandResult(success=False, ...)`,
  matching `GitModule`'s pattern exactly. Never reads or handles
  `GITHUB_TOKEN`
  - EP-039 test suite (tests/EP039/test_github_module.py)
- config/config.yaml: new `github` section (`enabled`,
  `api_base_url`, `timeout_seconds` -- deliberately no token key)

### Changed

- src/bootstrap.py: constructs `GitHubService` (and registers
  `GitHubModule`, once construction is confirmed) after the existing
  EP-038 wiring, gated by `github.enabled` (default `true`) and
  wrapped in a `try/except GitHubServiceError` so invalid `github.*`
  configuration disables the subsystem for that run (logged) instead
  of crashing startup. Like `GitService`, there is no cross-EP
  hard-dependency gate, since `GitHubService` depends only on `Config`
  and, at call time, the process environment
- src/modules/test_module.py: registers the EP-039 test suite so
  `test EP039` and `test all` pick it up

### Security

`GITHUB_TOKEN` is never placed in `config/config.yaml` or any other
config file by this implementation, is never logged, and never
appears in any exception message or CLI output -- verified directly by
a dedicated test asserting a fixed fake token value never appears in
any exception message across six different error scenarios.
`EP-031 Tool Engine was not modified.`

### Known limitations

- No pagination -- list operations return only GitHub's default first
  page
- `list_repositories()` covers the authenticated user's own
  repositories only, not an arbitrary named user's or organization's
- No retry/backoff on rate-limit errors
- `python-dotenv` (in `requirements.txt`) is not imported anywhere;
  `GITHUB_TOKEN` must be present in the actual process environment,
  not merely a `.env` file

### Validation

EP039       : 36 passed / 0 failed / 0 skipped
EP038       : 30 passed / 0 failed / 0 skipped (regression, unchanged)
EP037       : 87 passed / 0 failed / 0 skipped (regression, unchanged)
EP036       : 101 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP2 : 48 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP3 : 53 passed / 0 failed / 0 skipped (regression, unchanged)
EP033: 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP034: 113 passed / 0 failed / 0 skipped (regression, unchanged)
EP035: 143 passed / 0 failed / 0 skipped (regression, unchanged)
EP001: 20 passed / 0 failed / 0 skipped (regression, unchanged)

---

## v0.1.5-ep038

Released: 2026-08-13

Status: STEP 1-3 complete (STEP 4 Architecture Audit pending)

### Added

- src/core/git/git_result.py: `GitResult`, a frozen dataclass
  describing the outcome of one `git` subprocess invocation
  (`command`, `success`, `stdout`, `stderr`, `exit_code`). Pure data,
  no subprocess call in this module
- src/core/git/git_error.py: flat `GitError` exception hierarchy
  (`GitError`, `GitNotFoundError`, `GitRepositoryError`,
  `GitCommandError`), matching this project's existing per-subsystem
  domain-exception convention
- src/core/git/__init__.py: package docstring and public re-exports
- src/services/git_service.py: `GitService`, a config-driven, read-only
  wrapper around the system `git` executable. Exposes exactly five
  operations -- `status()`, `diff(path=None)`,
  `log(max_count=10)`, `branch()`, `show(ref)` -- no `commit`,
  `push`, `pull`, or `clone` method exists. Owns the sole
  `subprocess.run(["git", ...])` invocation point in this subsystem;
  every call passes `encoding="utf-8", errors="replace"` explicitly
  and is bounded by `git.timeout_seconds`. `GitServiceError` (raised
  only from `__init__`, for invalid `git.*` configuration or a
  non-repository path) is defined here, not in
  `src/core/git/git_error.py`, mirroring how
  `BackgroundWorkerServiceError` is distinct from the pool-level
  errors in EP-036
  - EP-038 test suite (tests/EP038/test_git_service.py)
- src/modules/git_module.py: `GitModule`, the "git" CLI namespace
  (`status`, `diff [path]`, `log [count]`, `branch`, `show <ref>`,
  `help`). A pure, additive translation layer: calls `GitService`'s
  existing public methods unchanged and catches `GitError` to format
  `CommandResult(success=False, ...)`, matching
  `BackgroundWorkerModule`'s pattern exactly
  - EP-038 test suite (tests/EP038/test_git_module.py)
- config/config.yaml: new `git` section (`enabled`, `repository_path`,
  `timeout_seconds`)

### Changed

- src/bootstrap.py: constructs `GitService` (and registers
  `GitModule`, once construction is confirmed) after the existing
  EP-036 wiring, gated by `git.enabled` (default `true`) and wrapped
  in a `try/except GitServiceError` so invalid `git.*` configuration
  or an unreachable/non-repository path disables the subsystem for
  that run (logged) instead of crashing startup. Unlike every
  EP-034/035/036 subsystem, there is no cross-EP "if `<other EP's
  engine>` is not None" hard-dependency gate, since `GitService`
  depends only on `Config` and the filesystem. `git.repository_path`
  is read from config in Bootstrap itself; Bootstrap's own project
  root is supplied as the `GitService(repository_path=...)` argument
  only when that config value is null/absent, so a real configured
  path is respected rather than silently overridden (see "Design
  deviation" below)
- src/modules/test_module.py: registers the EP-038 test suite so
  `test EP038` and `test all` pick it up

### Design deviation from EP038_DESIGN.md (approved, not a regression)

The design's Configuration section stated the intended outcome
("`repository_path` null/absent -> defaults to Bootstrap's project
root; a real configured value is respected") without spelling out the
mechanism. Implementing it required Bootstrap to resolve
`git.repository_path` from config itself before constructing
`GitService`, rather than passing its own project root unconditionally
as the `repository_path` constructor argument (which would have
silently ignored a real configured value, since that parameter is an
explicit override by design). `GitService`'s own public constructor
signature is unchanged from the design. The `git.enabled` gate --
implied by the design's CLI "Disabled behavior" row and every other
subsystem's convention, but not present in the Configuration section's
code snippet -- was added for the same reason: without it, the config
key would have had no effect.

### Known limitations

- No structured/parsed result shape; `GitResult.stdout` is raw
  `--porcelain=v1` (`status`) / `--oneline` (`log`) text. No parsing
  consumer need was identified for this initial scope
- `diff`/`show` output size is not bounded (`log` is, via its own
  count argument)
- The Vision document's "git push requires human confirmation" rule is
  not implemented, since `push` is out of this EP's scope entirely

### Validation

EP038       : 30 passed / 0 failed / 0 skipped
EP037       : 87 passed / 0 failed / 0 skipped (regression, unchanged)
EP036       : 101 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP2 : 48 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP3 : 53 passed / 0 failed / 0 skipped (regression, unchanged)
EP033: 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP034: 113 passed / 0 failed / 0 skipped (regression, unchanged)
EP035: 143 passed / 0 failed / 0 skipped (regression, unchanged)
EP001: 20 passed / 0 failed / 0 skipped (regression, unchanged)

---

## v0.1.4-ep037

Released: 2026-08-12

### Added

- docs/architecture/audits/EP037_AUDIT.md: EP-037 STEP 4 read-only
  Architecture Audit, covering EventBus thread-safety, the two new
  event paths, the background-worker adapter, duplicate-notification
  prevention, and EP-033/034/035/036 interaction

### Changed

- src/core/events.py: `EventBus` is now thread-safe. A single
  `threading.Lock` protects the subscriber registry; `subscribe()`/
  `unsubscribe()` mutate under the lock; `publish()` takes a snapshot
  copy of the relevant handler list under the lock, then releases the
  lock before invoking any handler -- the same lock-then-release-then-
  call-out discipline `BackgroundWorkerPool` (EP-036) already uses for
  `WorkflowEngine.run()`. Public API (`subscribe`, `unsubscribe`,
  `publish`, `event_names`) is unchanged
- src/services/workflow_engine_service.py: `WorkflowEngineService`
  gained an optional `event_bus` constructor parameter (default
  `None`, reproducing pre-EP-037 behavior exactly). `run()` publishes
  `"workflow.completed"` (`definition_id`, `result`) at the same point
  the existing `automation_hook` already fires. The hook and its call
  site are unchanged
- src/core/workflow_scheduler/workflow_scheduler_engine.py: same
  change, for `WorkflowSchedulerEngine.run_now()`
- src/core/background_workers/background_worker_pool.py:
  `BackgroundWorkerPool` gained an optional `event_bus` constructor
  parameter. `_execute_task` publishes
  `"background_worker.task_completed"` (`task_id`, `workflow_id`,
  `result`) or `"background_worker.task_failed"` (`task_id`,
  `workflow_id`, `error`) at its existing `COMPLETED`/`FAILED`
  transitions, always outside `_tasks_lock`. No change to task state
  semantics, locking, worker lifecycle, or shutdown behavior
- src/services/background_worker_service.py: threads the optional
  `event_bus` parameter through to the pool it constructs
- src/bootstrap.py:
  - Passes the existing `self._event_bus` into
    `WorkflowEngineService`, `WorkflowSchedulerEngine`, and
    `BackgroundWorkerService`
  - Production automation wiring now subscribes
    `AutomationEngine.notify_run()` to `"workflow.completed"` instead
    of calling `set_automation_hook()` on both engines separately --
    one subscription covers both the on-demand and scheduled paths.
    `set_automation_hook()` remains available and fully functional for
    direct/external callers; Bootstrap simply no longer uses it for
    production wiring
  - A small local adapter, `_on_background_worker_task_completed`,
    subscribes to `"background_worker.task_completed"` only and calls
    `automation_engine.notify_run(definition_id=workflow_id, result=result)`,
    re-keying the event's existing `workflow_id` kwarg without
    changing that event's payload contract. Not subscribed to
    `"background_worker.task_failed"` (no `WorkflowRunResult` in that
    event's payload)
- src/modules/test_module.py: registers the EP-037 test suite so
  `test EP037` and `test all` pick it up

### Known limitations

- AD-007 (Low) -- a background-worker-triggered automation action
  workflow runs synchronously on the pool worker thread that completed
  the triggering task. See docs/architecture/ARCHITECTURE_DEBT.md
- AD-008 (Low) -- the background-worker adapter's payload key access
  is implicitly coupled to `BackgroundWorkerPool`'s exact publish-call
  kwarg names, with a silent (log-only) failure mode if that shape
  changes. See docs/architecture/ARCHITECTURE_DEBT.md

### Validation

EP037       : 87 passed / 0 failed / 0 skipped
EP036       : 101 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP2 : 48 passed / 0 failed / 0 skipped (regression, unchanged)
EP036-STEP3 : 53 passed / 0 failed / 0 skipped (regression, unchanged)
EP033: 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP034: 113 passed / 0 failed / 0 skipped (regression, unchanged)
EP035: 143 passed / 0 failed / 0 skipped (regression -- see
  docs/RELEASE_NOTES.md for why this is 2 more than EP-036's release
  figure, and not a weakened assertion)
EP001: 20 passed / 0 failed / 0 skipped (regression, unchanged)

---

## v0.1.3-ep036

Released: 2026-08-11

### Added

- Background Worker Pool (src/core/background_workers/), a new
  independent package -- runs already-registered EP-033 workflows in
  the background, off the calling thread, by dispatching each
  submitted `workflow_id` through the already-existing
  `WorkflowEngine.run(workflow_id)` exclusively. No AI reasoning, no
  planning, and no direct real-subsystem/tool invocation anywhere in
  the package:
  - BackgroundWorkerPool (background_worker_pool.py): owns a fixed set
    of daemon worker threads that pull submitted `workflow_id`s off an
    internal, thread-safe queue. `_tasks_lock` protects the task
    registry (submission, status/result updates, reads via
    `get_task()`/`list_tasks()`, which return snapshots so a caller
    can never mutate this pool's internal state directly);
    `_lifecycle_lock` protects `_is_shutdown`. Neither lock is ever
    held while calling `WorkflowEngine.run()` or while blocked on
    `queue.get()`
  - BackgroundTask / TaskStatus: a submitted unit of work and its
    lifecycle state (PENDING -> RUNNING -> COMPLETED/FAILED)
  - Idle workers poll the queue every `poll_interval` (default 0.05s)
    so an idle pool shuts down quickly; this has no effect on a worker
    already executing a task via `WorkflowEngine.run()`
  - `shutdown()` never reports a worker as stopped merely because
    `Thread.join(timeout=...)` returned -- every join is followed by
    an explicit `Thread.is_alive()` check, and only workers that fail
    that check are ever reported "stuck"
  - `worker_threads()` returns the exact `Thread` objects this pool
    owns, so callers (tests in particular) can check this pool's own
    liveness without scanning `threading.enumerate()` -- another
    legitimate pool elsewhere in the process may use the same
    deterministic worker-naming scheme and must never be mistaken for
    this pool's own workers
  - `_execute_task` never raises: any exception from
    `WorkflowEngine.run()`, including a plain, non-`WorkflowEngineError`
    defect, is caught and recorded as that task's FAILED status, so a
    single bad workflow can never kill the worker thread running it
  - EP-036 STEP 1 test suite (tests/EP036/test_background_worker_pool.py)
- BackgroundWorkerService (src/services/background_worker_service.py):
  config-driven ('background_workers.enabled'), a thin owner of a
  single `BackgroundWorkerPool` instance. Implements no task-execution
  logic of its own -- every task-facing method (`submit`, `get_task`,
  `list_tasks`, `shutdown`) is a direct, narrow forward to the pool it
  owns. `background_workers.enabled` defaults to true, matching
  `workflow_engine.enabled` / `workflow_scheduler.enabled` /
  `automation.enabled`
  - EP-036 STEP 2 test suite
    (tests/EP036/test_background_worker_service.py)
- BackgroundWorkerModule (src/modules/background_worker_module.py):
  "worker" CLI namespace -- status / submit / list / info / stop /
  help. A pure, additive translation layer: calls
  BackgroundWorkerService's existing public methods unchanged and
  catches the domain exceptions it already documents raising
  (`BackgroundWorkerServiceError`, `PoolShutDownError`) to format them
  as `CommandResult(success=False, ...)` for the shell. No "register"
  command, matching EP-034's WorkflowSchedulerModule and EP-035's
  AutomationModule precedent
  - EP-036 STEP 3 test suite
    (tests/EP036/test_background_worker_module.py)
- config/config.yaml: new 'background_workers' section ('enabled',
  'worker_count', 'shutdown_timeout')
- docs/architecture/audits/EP036_AUDIT.md: EP-036 STEP 4 read-only
  Architecture Audit, covering the Pool/Service/Module layering,
  thread/task lifecycle, fault containment, and Bootstrap wiring

### Changed

- src/bootstrap.py: constructs BackgroundWorkerService (and registers
  BackgroundWorkerModule once the service is confirmed available)
  after the existing EP-035 wiring, wrapped in a try/except for
  `BackgroundWorkerServiceError`/`BackgroundWorkerPoolError` so invalid
  'background_workers.*' configuration disables the subsystem for that
  run (logged) instead of crashing startup. The live `WorkflowEngine`
  built for EP-033 is reused (through its public `run()` method only,
  via the same `workflow_engine_for_scheduler` reference EP-034/EP-035
  already captured). Background Worker Service has a hard dependency
  on a live WorkflowEngine existing this run
- src/modules/test_module.py: registers the EP-036 STEP 1/2/3 test
  suites so 'test EP036' / 'test EP036-STEP2' / 'test EP036-STEP3' and
  'test all' pick them up

### Known limitations

- AD-005 (Medium) -- no process-exit shutdown wiring calls
  `BackgroundWorkerService.shutdown()` automatically; deferred and
  documented in the package/service docstrings and
  config/config.yaml. See docs/architecture/ARCHITECTURE_DEBT.md
- AD-006 (Low) -- `BackgroundWorkerPool` task history has no
  eviction/TTL and grows unbounded over a long-running process. See
  docs/architecture/ARCHITECTURE_DEBT.md

### Validation

EP036       : 101 passed / 0 failed / 0 skipped
EP036-STEP2 : 48 passed / 0 failed / 0 skipped
EP036-STEP3 : 53 passed / 0 failed / 0 skipped
EP033: 182 passed / 0 failed / 0 skipped (regression, unchanged)
EP034: 113 passed / 0 failed / 0 skipped (regression, unchanged)
EP035: 141 passed / 0 failed / 0 skipped (regression, unchanged)

---

## v0.1.2-ep035

Released: 2026-08-08

### Added

- Automation Engine (src/core/automation_engine/), a new independent
  package -- chains one EP-033 workflow's completion (whether started
  on-demand through `WorkflowEngineService.run()`, or automatically
  through EP-034's `WorkflowSchedulerEngine.run_now()`/`tick()`) into a
  second workflow's run, based on the first run's outcome
  (ON_SUCCESS / ON_FAILURE / ON_ANY), by calling EP-033's
  already-existing `WorkflowEngine.run(workflow_id)` exclusively. No
  AI reasoning, no scheduling of its own, and no direct
  real-subsystem/tool invocation anywhere in the package -- it is
  purely reactive: it never decides that a workflow should run, it is
  only ever told, after the fact, that one already did:
  - AutomationRule / AutomationTriggerCondition
    (automation_rule.py): plain domain types -- a rule bundling a
    `trigger_workflow_id` reference to an EP-033 `WorkflowDefinition`,
    an outcome condition, and an `action_workflow_id` reference to a
    second `WorkflowDefinition`. Deliberately a new, independent type,
    not a reuse of EP-034's `ScheduledWorkflow` (an automation rule
    carries no `Schedule` or tick participation; a `ScheduledWorkflow`
    carries no trigger condition or action workflow)
  - AutomationRuleRegistry (automation_rule_registry.py):
    thread-safe, in-memory catalog of registered automation rules
  - AutomationEngine (automation_engine.py): register_rule /
    remove_rule / enable_rule / disable_rule / list_rules / get_rule /
    notify_run -- the only component holding a reference to EP-033's
    `WorkflowEngine`, reached through its public `run()` method only.
    `notify_run()` is the reactive entry point: it matches a
    just-completed run against registered, enabled rules and
    dispatches each match's action workflow, updating
    `last_triggered`/`last_action_success` on the rule. It never
    propagates a failure -- neither an internal matching/dispatch
    error nor a failed action-workflow run -- back to its caller
  - src/core/automation_engine/__init__.py: package-level public
    exports, and the single-hop/no-recursive-chaining note documented
    below
  - EP-035 test suite (tests/EP035/test_automation_engine.py)
- AutomationService (src/services/automation_service.py):
  config-driven ('automation.enabled'), a thin CLI-facing wrapper
  around AutomationEngine. Unlike EP-034's WorkflowSchedulerService,
  it owns no background thread -- Automation Engine is purely
  reactive, with no tick loop to start or stop
- AutomationModule (src/modules/automation_module.py): "automate"
  CLI namespace -- list / status / info / enable / stop / help (no
  "register" command, matching EP-011's SchedulerModule, EP-033's
  WorkflowEngineModule, and EP-034's WorkflowSchedulerModule
  precedent -- rules are registered only through the public
  `AutomationService.register()` API. No manual "trigger"/"run"
  command either -- a rule only ever fires reactively, through
  `AutomationEngine.notify_run()`, when its trigger workflow actually
  completes)
- config/config.yaml: new 'automation' section ('enabled')

### Single-hop / no recursive chaining

- EP-035 is deliberately synchronous, single-hop, and non-recursive.
  `AutomationEngine.notify_run()` dispatches a matched rule's action
  workflow by calling `WorkflowEngine.run()` directly, bypassing the
  automation hook entirely -- so an action workflow's own completion
  never re-enters `notify_run()`. A -> B is supported; A -> B -> C is
  not. No cycle detection was implemented, because recursive chaining
  itself was out of scope for this release. Background workers
  (queued/async dispatch) and a generic publish/subscribe event bus
  remain future work, tracked as EP-036 and EP-037 respectively --
  EP-035 introduces neither

### Changed

- src/services/workflow_engine_service.py: `run()` optionally invokes
  a new `automation_hook` callback (wired via a new
  `set_automation_hook()` setter) immediately after a run produces a
  `WorkflowRunResult`, isolated in a try/except that never propagates,
  so a defect in the hook can never turn a successful `run()` call
  into a failure. The hook is a bare
  `Callable[[str, WorkflowRunResult], None]` -- this file does not
  import AutomationEngine or any EP-035 type. Default is `None`,
  which reproduces this file's exact pre-EP-035 behavior
- src/core/workflow_scheduler/workflow_scheduler_engine.py: `run_now()`
  gains the identical optional `automation_hook` (via the same
  `set_automation_hook()` pattern), covering both a manual `autoflow
  run` and an automatic `tick()`-driven run, since `tick()` calls
  `run_now()`. Same isolation guarantee, same bare-`Callable` typing,
  same `None` default and unchanged pre-EP-035 behavior
- src/bootstrap.py: constructs AutomationRuleRegistry /
  AutomationEngine / AutomationService after the existing EP-034
  wiring, wrapped in a try/except for AutomationError so invalid
  configuration disables the Automation Engine subsystem for that run
  (logged) instead of crashing startup. The live WorkflowEngine built
  for EP-033 is reused (through its public `run()` method only, via
  the same `workflow_engine_for_scheduler` reference EP-034 already
  captured). The reactive hook is wired into both
  WorkflowEngineService and WorkflowSchedulerEngine only when
  'automation.enabled' is true, so a disabled Automation Engine can
  never fire a rule regardless of which path is used to reach
  `AutomationEngine.notify_run()`. No file under
  src/core/workflow_engine/ is modified, no existing wiring step is
  reordered or removed. Automation Engine has a hard dependency on a
  live WorkflowEngine existing this run (a genuine `WorkflowEngineError`
  during EP-033 construction, or the Plan Execution Engine itself
  being unavailable, skips this subsystem entirely)
- src/modules/test_module.py: registers the EP-035 test suite so
  'test EP035' and 'test all' pick it up

### Improved

- A completed EP-033 workflow can now automatically trigger a second
  EP-033 workflow based on its outcome (success, failure, or either),
  whether that first workflow ran on demand or on an EP-034 schedule,
  without any new AI reasoning, background thread, queue, or event
  bus being introduced, and without changing any prior release's
  default behavior -- verified by EP-033's and EP-034's own test
  suites, which pass unchanged after this release

---

## v0.1.1-ep034

Released: 2026-08-07

### Added

- Workflow Scheduler (src/core/workflow_scheduler/), a new independent
  package -- gives an EP-033 workflow definition a time trigger: runs
  it automatically on a schedule (manual/once/interval/daily/weekly;
  cron remains an interface only, not yet implemented, matching
  EP-011's own documented TODO), by calling EP-033's already-existing
  `WorkflowEngine.run(workflow_id)` exclusively. No AI reasoning, no
  planning, and no direct real-subsystem/tool invocation anywhere in
  the package -- it only decides *when* an already-completed EP's
  public API should be called again:
  - ScheduledWorkflow (scheduled_workflow.py): plain domain type
    bundling a `workflow_id` reference to an EP-033
    `WorkflowDefinition` with scheduling runtime state
    (last_run/next_run/status). Reuses `Schedule`, `ScheduleType`, and
    `JobStatus` UNCHANGED from EP-011's Task Scheduler
    (src/core/scheduler/job.py) -- genuine reuse of pure, stateless
    value types, not a redefinition
  - ScheduledWorkflowRegistry (scheduled_workflow_registry.py):
    thread-safe, in-memory catalog of registered scheduled workflows
  - WorkflowSchedulerEngine (workflow_scheduler_engine.py):
    register_entry / remove_entry / start_entry / stop_entry /
    run_now / list_entries / calculate_next_run / tick -- the only
    component holding a reference to EP-033's `WorkflowEngine`,
    reached through its public `run()` method only.
    `calculate_next_run` deliberately reimplements (rather than calls)
    EP-011's `Scheduler.calculate_next_run`, since that method is
    typed to and reads fields from `Job` specifically; duck-typing a
    `ScheduledWorkflow` into it would create undocumented, fragile
    coupling with no formal compatibility contract
  - src/core/workflow_scheduler/__init__.py: package-level public
    exports, and the naming-collision decision documented below
  - EP-034 test suite (tests/EP034/test_workflow_scheduler.py)
- WorkflowSchedulerService (src/services/workflow_scheduler_service.py):
  config-driven ('workflow_scheduler.enabled',
  'workflow_scheduler.auto_start', 'workflow_scheduler.tick_interval'),
  a thin CLI-facing wrapper around WorkflowSchedulerEngine that also
  owns its own background tick thread (daemon, entirely separate from
  EP-011's own tick thread -- no shared state) providing automatic
  execution
- WorkflowSchedulerModule (src/modules/workflow_scheduler_module.py):
  "autoflow" CLI namespace -- list / status / run / start / stop /
  info / help (no "register" command, matching EP-011's SchedulerModule
  and EP-033's WorkflowEngineModule precedent -- entries are registered
  only through the public `WorkflowSchedulerService.register()` API)
- config/config.yaml: new 'workflow_scheduler' section ('enabled',
  'auto_start', 'tick_interval')

### Naming decision

- EP-011 ("Logging Improvements" era) already shipped a completed,
  **actively wired** `Job`/`Schedule`/`ScheduleType`/`JobStatus`/
  `JobRegistry`/`Scheduler` (src/core/scheduler/), `SchedulerService`
  (src/services/scheduler_service.py, which owns a live background
  tick thread auto-started at Bootstrap), and `SchedulerModule`
  (src/modules/scheduler_module.py, CLI namespace "scheduler", config
  key 'scheduler.*') -- unlike EP-007's dormant Workflow package, this
  one is live and registers real default jobs today. EP-034 does not
  touch, fix, or repurpose any of it -- it remains exactly as EP-011
  left it, verified still running (2 default jobs, tick loop active)
  after this release. EP-034 is deliberately namespaced apart from it
  at every layer -- package (`workflow_scheduler`, not `scheduler`),
  domain type (`ScheduledWorkflow`, not `Job`), registry
  (`ScheduledWorkflowRegistry`, not `JobRegistry`), engine
  (`WorkflowSchedulerEngine`, not `Scheduler`), CLI namespace
  ("autoflow", not "scheduler" -- and deliberately not "schedule"
  either, to avoid the same near-miss confusion EP-033 avoided by
  rejecting "workflows" for its own CLI namespace), and config key
  ('workflow_scheduler.*', not 'scheduler.*') -- to avoid any
  collision, present or future. See
  src/core/workflow_scheduler/__init__.py for the full note.

### Changed

- src/bootstrap.py: registers WorkflowSchedulerEngine/
  WorkflowSchedulerService/WorkflowSchedulerModule after Workflow
  Engine, wrapped in a try/except for WorkflowSchedulerError so
  invalid configuration disables the Workflow Scheduler subsystem for
  that run (logged) instead of crashing startup. The live
  WorkflowEngine built for EP-033 is captured locally
  (`workflow_engine_for_scheduler`) and forwarded to
  WorkflowSchedulerEngine through its existing public `run()` method
  only -- no file under src/core/workflow_engine/ or
  src/core/scheduler/ is modified, no existing wiring step is
  reordered or removed. Workflow Scheduler has a hard dependency on a
  live WorkflowEngine existing this run (a genuine
  `WorkflowEngineError` above, or the Plan Execution Engine itself
  being unavailable, skips this subsystem entirely)
- src/modules/test_module.py: registers the EP-034 test suite so
  'test EP034' and 'test all' pick it up

### Improved

- An EP-033 workflow definition can now be scheduled to run
  automatically (interval/daily/weekly/once) or on demand through the
  "autoflow" CLI namespace, without any new AI reasoning, planning
  logic, or direct subsystem/tool invocation being introduced, and
  without changing any prior release's default behavior -- including
  EP-011's own, entirely separate Task Scheduler, verified still
  functioning identically after this release

---

## v0.1.1-ep033

Released: 2026-08-07

### Added

- Workflow Engine (src/core/workflow_engine/), a new independent
  package -- runs a named, ordered sequence of plain-text requests (a
  `WorkflowDefinition`) as a single, repeatable unit: each
  `WorkflowRequestStep` is planned and executed through EP-030's
  already-existing `PlanExecutionEngine.execute_request()` (which
  itself already optionally calls EP-029's `PlanningEngine.plan()`),
  in order, halting the remaining workflow on failure per
  'workflow_engine.stop_on_failure'. No AI reasoning, no new planning
  logic, and no direct real-subsystem/tool invocation anywhere in the
  package -- it only sequences calls to already-completed EPs' public
  APIs:
  - WorkflowRequestStep / WorkflowDefinition
    (workflow_definition.py): plain, immutable domain model for a
    workflow's steps
  - WorkflowStepOutcomeStatus / WorkflowStepOutcome / WorkflowRunResult
    (workflow_run_result.py): plain data model for the outcome of a
    single step and of a whole run, each step outcome wrapping the
    underlying EP-030 `PlanExecutionResult`
  - WorkflowRunProvider interface (workflow_run_provider.py): unified
    `run_step(step, executor) -> WorkflowStepOutcome` contract every
    workflow-step dispatch strategy must implement -- the `executor`
    callable is supplied by the engine (bound to
    `PlanExecutionEngine.execute_request()`), so the provider itself
    never imports `PlanExecutionEngine`/`PlanningEngine`
  - DefaultWorkflowRunProvider (workflow_run_provider.py): the
    built-in provider, registered under the name "workflow_engine" --
    calls the supplied executor and translates the resulting
    `PlanExecutionResult` into COMPLETED/FAILED, isolating any raised
    exception into a FAILED outcome rather than letting it propagate
  - WorkflowDefinitionRegistry (workflow_definition_registry.py):
    in-memory catalog of registered workflow definitions
    (register/unregister/get/list)
  - WorkflowEngineManager (workflow_engine_manager.py): orchestration
    layer -- register/select workflow-run providers, own the
    definition catalog, enable/disable the subsystem, and resolve
    'workflow_engine.*' configuration including the stop-on-failure
    policy
  - WorkflowEngine (workflow_engine.py): the provider-independent
    pipeline -- walks a definition's steps in order, dispatching each
    through the active WorkflowRunProvider, and halts the remaining
    workflow (reporting SKIPPED) after a failure if
    'workflow_engine.stop_on_failure' is enabled, mirroring EP-030's
    own halting policy one level up
  - src/core/workflow_engine/__init__.py: package-level public
    exports, and the naming-collision decision documented below
  - EP-033 test suite (tests/EP033/test_workflow_engine.py)
- WorkflowEngineService (src/services/workflow_engine_service.py):
  config-driven ('workflow_engine.enabled',
  'workflow_engine.default_provider', 'workflow_engine.stop_on_failure'),
  a thin CLI-facing wrapper around WorkflowEngineManager/WorkflowEngine
- WorkflowEngineModule (src/modules/workflow_engine_module.py):
  "flow" CLI namespace -- help / status / list / info / use / run
- config/config.yaml: new 'workflow_engine' section ('enabled',
  'default_provider', 'stop_on_failure')

### Naming decision

- EP-007 ("Core Improvements") already shipped a completed, dormant
  `Workflow`/`WorkflowStep`/`WorkflowRegistry`
  (src/core/workflows/), `WorkflowService`
  (src/services/workflow_service.py), and `WorkflowModule`
  (src/modules/workflow_module.py, CLI namespace "workflow", config
  key 'workflows.*'). `src/bootstrap.py` has never instantiated
  `WorkflowService` or registered `WorkflowModule` -- that package
  remains completed, honestly documented (its own docstring records a
  known architecture gap), and untouched by this release. EP-033 is
  deliberately namespaced apart from it at every layer -- package
  (`workflow_engine`, not `workflows`), domain types
  (`WorkflowDefinition`/`WorkflowRequestStep`, not
  `Workflow`/`WorkflowStep`), registry (`WorkflowDefinitionRegistry`,
  not `WorkflowRegistry`), CLI namespace ("flow", not "workflow"), and
  config key ('workflow_engine.*', not 'workflows.*') -- to avoid any
  collision, present or future. See
  src/core/workflow_engine/__init__.py for the full note.

### Changed

- src/bootstrap.py: registers WorkflowEngineManager/WorkflowEngine/
  WorkflowEngineService/WorkflowEngineModule after Multi-Agent
  Collaboration, wrapped in a try/except for WorkflowEngineError so
  invalid 'workflow_engine.*' configuration disables the Workflow
  Engine subsystem for that run (logged) instead of crashing startup.
  The live PlanExecutionEngine built for EP-030 is captured locally
  (`plan_execution_engine_for_workflow`) and forwarded to
  WorkflowEngine through its existing public `execute_request()`
  method only -- no file under src/core/plan_execution/ or
  src/core/planning/ is modified, no existing wiring step is reordered
  or removed. Workflow Engine has a hard dependency on a live
  PlanExecutionEngine existing this run (a genuine
  `PlanExecutionError` above skips this subsystem entirely), but not
  on the Plan Execution Engine being *enabled* -- mirroring the same
  distinction already established for Multi-Agent Collaboration's
  dependency on the Agent Framework
- src/modules/test_module.py: registers the EP-033 test suite so
  'test EP033' and 'test all' pick it up

### Improved

- A named, ordered sequence of requests can now be run as one
  repeatable unit through the "flow" CLI namespace, reusing the
  existing Planning + Plan Execution pipeline end to end -- without
  any new AI reasoning, planning logic, or direct subsystem/tool
  invocation being introduced, and without changing any prior
  release's default behavior

---

## v0.1.0-ep032

Released: 2026-08-06

### Added

- Multi-Agent Collaboration (src/core/collaboration/), a new
  independent package -- implements the Multi-Agent Coordinator
  explicitly deferred by EP-028 through EP-030's own docstrings:
  deterministic broadcast of a single request across every agent
  currently registered with EP-028's Agent Framework, with each
  agent's own `AgentExecutionResult` collected into a uniform
  outcome. No AI reasoning, no negotiation, and no inter-agent
  messaging anywhere in the package:
  - AgentOutcomeStatus / AgentOutcome / CollaborationResult
    (collaboration_result.py): plain data model for the outcome of
    dispatching to a single agent and of a whole collaborate() call
  - CollaborationProvider interface (collaboration_provider.py):
    unified `collaborate(request, metadata, agents) -> CollaborationResult`
    contract every multi-agent distribution strategy must implement
  - DefaultCollaborationProvider (collaboration_provider.py): the
    built-in provider, registered under the name "collaboration" --
    sorts agents by name, dispatches to every currently READY agent
    through its own public `execute()`, reports every non-READY agent
    UNAVAILABLE without calling it, and isolates a single agent's
    raised `AgentFrameworkError` so it never breaks the other agents'
    outcomes
  - CollaborationManager (collaboration_manager.py): orchestration
    layer -- register/select collaboration providers, enable/disable
    the subsystem, and resolve 'collaboration.*' configuration. Owns
    no reference to `AgentManager` or its catalog
  - CollaborationEngine (collaboration_engine.py): the
    provider-independent pipeline -- reads the live agent catalog from
    EP-028's `AgentManager` through its public `list_providers()`
    method only, and dispatches to the active CollaborationProvider
  - src/core/collaboration/__init__.py: package-level public exports
  - EP-032 test suite (tests/EP032/test_collaboration_engine.py)
- CollaborationService (src/services/collaboration_service.py):
  config-driven ('collaboration.enabled',
  'collaboration.default_provider') business logic, a thin CLI-facing
  wrapper around CollaborationManager/CollaborationEngine
- CollaborationModule (src/modules/collaboration_module.py):
  "collaborate" CLI namespace -- help / status / providers / agents /
  use / run
- config/config.yaml: new 'collaboration' section ('enabled',
  'default_provider')

### Changed

- src/bootstrap.py: registers CollaborationManager/CollaborationEngine/
  CollaborationService/CollaborationModule after the Tool Engine,
  wrapped in a try/except for CollaborationError so invalid
  'collaboration.*' configuration disables the Multi-Agent
  Collaboration subsystem for that run (logged) instead of crashing
  startup. The live AgentManager built for EP-028 is captured locally
  (`agent_manager_for_collaboration`) and forwarded to
  CollaborationEngine through its existing public `list_providers()`
  method only -- no file under src/core/agent/ is modified, no
  existing wiring step is reordered or removed. Multi-Agent
  Collaboration has a hard dependency on a live `AgentManager`
  existing this run (a genuine `AgentFrameworkError` above skips this
  subsystem entirely), but not on the Agent Framework being *enabled*
  -- a disabled Agent Framework still constructs a valid `AgentManager`
  with its catalog intact, so Multi-Agent Collaboration still wires up
  and honestly reports every agent UNAVAILABLE
- src/modules/test_module.py: registers the EP-032 test suite so
  'test EP032' and 'test all' pick it up

### Improved

- A request can now be broadcast to every currently registered agent
  in one call and every individual agent's outcome inspected through
  the "collaborate" CLI namespace -- without any new AI reasoning,
  negotiation, or inter-agent messaging component being introduced,
  and without changing any prior release's default behavior

---

## v0.1.0-ep031

Released: 2026-08-05

### Added

- Tool Engine (src/core/tool/), a new independent package -- turns an
  already-identified `(subsystem, action)` reference into a real
  invocation of an already-implemented Engineering Package's public
  API, with no AI reasoning, no planning, no plan walking, and no
  dispatch-order/failure-policy logic anywhere in the package:
  - Tool (tool.py): plain catalog-entry data model -- id, name,
    description, subsystem, action, a pre-bound zero-argument handler
    closure, and an enabled flag
  - ToolStatus / ToolResult (tool_result.py): plain data model for the
    outcome of a single tool invocation
  - ToolRegistry (tool_registry.py): thread-safe catalog of registered
    tools -- register/unregister/get/find/find_for_step/list, mirroring
    PluginRegistry/ProcessRegistry
  - ToolProvider interface (tool_provider.py): unified
    `invoke_tool(tool) -> ToolResult` contract every invocation
    strategy must implement
  - DefaultToolProvider (tool_provider.py): the built-in provider,
    registered under the name "tool_engine" -- invokes a Tool's
    pre-bound handler and translates any raised exception into a
    failed ToolResult rather than letting it propagate
  - ToolManager (tool_manager.py): orchestration layer --
    register/select tool providers, own the ToolRegistry, enable/
    disable the subsystem, and resolve 'tool.*' configuration
  - ToolEngine (tool_engine.py): the provider-independent
    lookup -> real-invocation pipeline -- resolves a tool by id or by
    a `(subsystem, action)` pair and dispatches it to the active
    ToolProvider
  - ToolExecutionProvider (tool_execution_provider.py): the bridge
    adapter implementing EP-030's `PlanExecutionProvider` ABC -- the
    "Tool-Engine-backed provider" EP-030's own docstrings anticipated.
    The only file in the project that imports from both
    `src.core.tool` and `src.core.plan_execution`
  - src/core/tool/__init__.py: package-level public exports
  - Five built-in, real tools wired from src/bootstrap.py: Memory
    Recall, Knowledge Base Query, Long-Term Memory Query, Agent
    Subsystem Coordination, and Acknowledge Request -- each a closure
    over an already-built subsystem Service instance's public,
    parameter-free method. Four EP-029 actions that require a text
    parameter neither `PlanStep` nor
    `PlanExecutionProvider.execute_step()` currently carries
    (`generate_embedding`, `retrieve_context`, `semantic_search`,
    `compress_context`) are deliberately left unregistered rather than
    invented -- see docs/BACKLOG.md
- ToolService (src/services/tool_service.py): config-driven
  ('tool.enabled', 'tool.default_provider') business logic, a thin
  CLI-facing wrapper around ToolManager/ToolEngine
- ToolModule (src/modules/tool_module.py): "tool" CLI namespace --
  help / status / providers / list / use / run
- config/config.yaml: new 'tool' section ('enabled', 'default_provider')
- EP-031 test suite (tests/EP031/test_tool_engine.py)

### Changed

- src/bootstrap.py: registers ToolManager/ToolEngine/ToolService/
  ToolModule after the Plan Execution Engine, wrapped in a try/except
  for ToolError so invalid 'tool.*' configuration disables the Tool
  Engine subsystem for that run (logged) instead of crashing startup.
  The live PlanExecutionManager built for EP-030 (when available) is
  captured locally and, once Tool Engine is built, has a
  ToolExecutionProvider registered with it through its existing
  public `register_provider()` method only -- no file under
  src/core/plan_execution/ is modified, no existing wiring step is
  reordered or removed, and 'plan_execution.default_provider' is left
  unchanged ("plan_execution"), so default plan-execution dispatch
  behavior from EP-030 is byte-for-byte unaffected unless an operator
  explicitly runs 'execution use tool_engine'
- src/modules/test_module.py: registers the EP-031 test suite so
  'test EP031' and 'test all' pick it up

### Improved

- A dispatched `PlanStep` can now, for the five actions with a
  registered tool, produce a real subsystem effect and report it back
  through both the "tool" and "execution" CLI namespaces -- without
  any new AI reasoning, planning, or dispatch-order component being
  introduced, and without changing any prior release's default
  behavior.

---

## v0.1.0-ep030

Released: 2026-08-05

### Added

- Plan Execution Engine (src/core/plan_execution/), a new independent
  package -- the first component to turn an EP-029 `Plan` into
  dispatched work, with no AI reasoning, no AI provider call, and no
  real subsystem/tool invocation anywhere in the package (that remains
  a future Tool Engine's responsibility):
  - StepStatus / StepResult / PlanExecutionResult
    (plan_execution_result.py): plain data model for the outcome of
    dispatching a single step and of executing a whole Plan.
    Deliberately named `plan_execution` (not `execution`) to avoid
    colliding with the pre-existing, unrelated `src/core/execution/`
    package (EP-003's OS-level target launcher)
  - PlanExecutionProvider interface (plan_execution_provider.py):
    unified `execute_step(step) -> StepResult` contract every
    execution strategy must implement
  - DefaultPlanExecutionProvider (plan_execution_provider.py): the
    built-in provider, registered under the name "plan_execution" --
    deterministic, recognized-action dispatch only (the same actions
    EP-029's DefaultPlanningProvider can emit). Reports a step
    "completed" once it has been successfully dispatched to a
    recognized action -- not that any real external effect was
    produced
  - PlanExecutionManager (plan_execution_manager.py): orchestration
    layer -- register/select execution providers, enable/disable the
    subsystem, and resolve the default `stop_on_failure` policy from
    'plan_execution.*' configuration. New provider types (e.g. a
    future Tool-Engine-backed provider) can be added at runtime via
    `register_provider()` without modifying this class
  - PlanExecutionEngine (plan_execution_engine.py): the
    provider-independent Plan -> PlanExecutionResult pipeline --
    walks a Plan's steps in order, skips any step EP-029 already
    reported unavailable, dispatches every available step to the
    active provider, and halts the remaining plan on the first
    failure when 'stop_on_failure' is enabled. Optionally accepts an
    EP-029 `PlanningEngine` and, when supplied, exposes
    `execute_request()` to plan and execute a request in one call
    through its public `plan()` method only
  - src/core/plan_execution/__init__.py: package-level public exports
- PlanExecutionService (src/services/plan_execution_service.py):
  config-driven ('plan_execution.enabled',
  'plan_execution.default_provider', 'plan_execution.stop_on_failure')
  business logic, a thin CLI-facing wrapper around
  PlanExecutionManager/PlanExecutionEngine
- PlanExecutionModule (src/modules/plan_execution_module.py):
  "execution" CLI namespace -- help / status / providers / use / run /
  stop-on-failure
- config/config.yaml: new 'plan_execution' section ('enabled',
  'default_provider', 'stop_on_failure')
- EP-030 test suite (tests/EP030/test_plan_execution_engine.py)

### Changed

- src/bootstrap.py: registers PlanExecutionManager/PlanExecutionEngine/
  PlanExecutionService/PlanExecutionModule after the Planning Engine,
  wrapped in a try/except for PlanExecutionError so invalid
  'plan_execution.*' configuration disables the Plan Execution Engine
  subsystem for that run (logged) instead of crashing startup. The
  PlanningEngine built for EP-029 (when available) is captured locally
  and passed to PlanExecutionEngine, read-only, through its public
  `plan()` method only. Plan Execution Engine has no hard dependency
  on Planning Engine: `execute_plan()` works standalone given an
  already-built Plan even when Planning Engine is unavailable this
  run; that only narrows what `execution run` can do, it never
  disables the Plan Execution Engine subsystem itself. No change to
  startup order or wiring for any other subsystem
- src/modules/test_module.py: registers the EP-030 test suite so
  'test EP030' and 'test all' pick it up

### Improved

- An EP-029 Plan's steps can now actually be dispatched, in order,
  respecting availability and a configurable failure policy, and the
  outcome inspected per step or as a whole -- without any new
  reasoning, retrieval, or real subsystem-invocation component being
  introduced.

---

## v0.1.0-ep029

Released: 2026-08-04

### Added

- Planning Engine (src/core/planning/), a new independent package --
  decomposes a request into an ordered Plan of steps referencing
  already-implemented Engineering Packages by name, with no AI
  reasoning, no AI provider call, no prompt construction, and no task
  execution anywhere in the package:
  - PlanStep / Plan (planning_result.py): plain data model for a
    single ordered step and the outcome of decomposing a whole request
  - PlanningProvider interface (planning_provider.py): unified
    `plan(request, max_steps) -> Plan` contract every planning
    strategy must implement
  - DefaultPlanningProvider (planning_provider.py): the built-in
    provider, registered under the name "planning" -- deterministic,
    fixed keyword -> (subsystem, action, description) rule table,
    applied via case-insensitive substring matching only. Emits at
    most one step per matched subsystem (first matching keyword wins),
    preserves rule order, enforces `max_steps`, and falls back to a
    single `acknowledge_request` step (no subsystem) when nothing
    matches. Every step is returned with `available=True`; this
    provider never queries a live subsystem registry
  - PlanningManager (planning_manager.py): orchestration layer --
    register/select planning providers, enable/disable the subsystem,
    and resolve the default `max_steps` limit from 'planning.*'
    configuration
  - PlanningEngine (planning_engine.py): the provider-independent
    request -> Plan pipeline. Optionally accepts an EP-028
    `AgentEngine` and, when supplied, reconciles each step's
    `available` flag against that agent's live subsystem registry via
    its public `list_subsystems()` method only -- the first component
    to make real use of EP-028's Agent Framework subsystem registry
  - src/core/planning/__init__.py: package-level public exports
- PlanningService (src/services/planning_service.py): config-driven
  ('planning.enabled', 'planning.default_provider', 'planning.max_steps')
  business logic, a thin CLI-facing wrapper around
  PlanningManager/PlanningEngine
- PlanningModule (src/modules/planning_module.py): "planning" CLI
  namespace -- help / status / providers / use / plan / limits
- config/config.yaml: new 'planning' section ('enabled',
  'default_provider', 'max_steps')
- EP-029 test suite (tests/EP029/test_planning_engine.py)

### Changed

- src/bootstrap.py: registers PlanningManager/PlanningEngine/
  PlanningService/PlanningModule after the Agent Framework, wrapped in
  a try/except for PlanningError so invalid 'planning.*' configuration
  disables the Planning Engine subsystem for that run (logged) instead
  of crashing startup. The AgentEngine built for EP-028 (when
  available) is captured locally and passed to PlanningEngine,
  read-only, through its public `list_subsystems()` method only.
  Planning Engine has no hard dependency on the Agent Framework:
  `plan()` works standalone (every step reported available) even when
  the Agent Framework is unavailable this run; that only narrows what
  Planning Engine can see, it never disables the Planning Engine
  subsystem itself. No change to startup order or wiring for any other
  subsystem.
- src/modules/test_module.py: registers the EP-029 test suite so
  'test EP029' and 'test all' pick it up

### Improved

- A request can now be decomposed into a concrete, inspectable
  sequence of subsystem-referencing steps -- and, when the Agent
  Framework is available, each step's real-world feasibility can be
  checked against the subsystems actually registered and enabled at
  runtime -- without any new reasoning, retrieval, or storage
  component being introduced.

---



Released: 2026-08-03

### Added

- Agent Framework (src/core/agent/), a new independent package -- the
  central orchestration layer coordinating already-implemented
  Engineering Packages, with no planning, reasoning, task
  decomposition, tool execution, prompt construction, or AI provider
  call anywhere in the package:
  - AgentState (agent_state.py): lifecycle enum every agent reports
    through and transitions via (UNINITIALIZED, READY, RUNNING,
    SHUTDOWN, ERROR)
  - SubsystemInfo / AgentExecutionResult / AgentCancelResult
    (agent_result.py): plain data model for a registered subsystem's
    diagnostic snapshot, the outcome of accepting a request, and the
    outcome of attempting to cancel one
  - AgentProvider interface (agent_provider.py): unified
    initialize()/shutdown()/reset()/status()/execute()/cancel()/
    register_subsystem()/unregister_subsystem()/list_subsystems()
    contract every agent implementation must satisfy
  - DefaultAgentProvider (agent_provider.py): the built-in agent,
    registered under the name "jarvis" -- maintains lifecycle state and
    a name -> availability-check subsystem registry, and synchronously
    accepts and acknowledges every `execute()` call
    (`AgentExecutionResult.dispatched` is always False: there is no
    Planner yet to dispatch to). `cancel()` always reports nothing left
    to cancel for a known request id, since every request already
    completed synchronously
  - AgentManager (agent_manager.py): orchestration layer --
    register/select agents, enable/disable the subsystem, and resolve
    'agent.startup_mode' ("idle": leave the selected agent
    UNINITIALIZED until an explicit `agent initialize`; "auto":
    initialize it immediately once AgentEngine is constructed) from
    'agent.*' configuration
  - AgentEngine (agent_engine.py): the provider-independent pipeline
    forwarding every lifecycle/subsystem-registry/request call to the
    currently selected AgentProvider
  - src/core/agent/__init__.py: package-level public exports
- AgentService (src/services/agent_service.py): config-driven
  ('agent.enabled', 'agent.default_agent', 'agent.startup_mode')
  business logic, a thin CLI-facing wrapper around
  AgentManager/AgentEngine. Also exposes `execute()`/`cancel()` for
  future programmatic callers (e.g. a future Planner), not wired to
  any CLI command in this EP
- AgentModule (src/modules/agent_module.py): "agent" CLI namespace --
  help / status / subsystems / register / unregister / reset /
  initialize / shutdown
- config/config.yaml: new 'agent' section ('enabled', 'default_agent',
  'startup_mode')
- EP-028 test suite (tests/EP028/test_agent_framework.py)

### Changed

- src/bootstrap.py: registers AgentManager/AgentEngine/AgentService/
  AgentModule after Context Compression, wrapped in a try/except for
  AgentFrameworkError so invalid 'agent.*' configuration disables the
  Agent Framework subsystem for that run (logged) instead of crashing
  startup. Every subsystem service already built earlier in this
  method (Embedding, RAG, Memory, Knowledge Base, Long-Term Memory,
  Semantic Search, Context Compression) that is available this run is
  registered with the Agent Framework's subsystem registry, by name,
  bound to that service's own public `status().enabled` -- read-only,
  no private access. A subsystem unavailable this run is simply
  skipped, matching every other soft dependency already present in
  this method; one subsystem's registration failing is logged and
  skipped rather than aborting the whole Agent Framework build. No
  change to startup order or wiring for any other subsystem.
- src/modules/test_module.py: registers the EP-028 test suite so
  'test EP028' and 'test all' pick it up

### Improved

- Every completed Engineering Package's enabled/disabled status is now
  visible in one place ('agent subsystems'), without any new status
  storage -- each subsystem's own `status().enabled` is read live, on
  demand.

---



Released: 2026-08-03

### Added

- Context Compression subsystem (src/core/context_compression/), a new
  independent package:
  - ContextChunk / CompressionResult (compression_result.py): plain
    data model for one unit of input context (text, index, metadata)
    and the outcome of compressing an ordered chunk sequence (chunks,
    original/compressed chunk and character counts, estimated tokens,
    deduplicated-chunk count, truncated flag)
  - CompressionProvider interface (compression_provider.py): unified
    compress()/estimate_tokens()/status() contract for every
    context-compression provider
  - DefaultCompressionProvider (compression_provider.py): the built-in
    provider, registered under the name "compression" -- deterministic,
    purely-arithmetic deduplication (whole-chunk, then paragraph-level
    across chunks) followed by max-chunk and max-character enforcement,
    with ordering and metadata preserved throughout; token count is
    estimated with a documented, fixed characters-per-token heuristic,
    never a real tokenizer or network call. No AI reasoning, no
    summarization, no rewriting of surviving text (only truncation, to
    fit a character budget)
  - CompressionManager (compression_manager.py): orchestration layer --
    register/select compression providers, enable/disable the
    subsystem, and own the default `max_context_characters` /
    `max_chunks` / `deduplicate` parameters read from
    'context_compression.*' configuration
  - CompressionEngine (compression_engine.py): the
    text/chunks -> compressed-result pipeline -- splits raw text into
    paragraph chunks, or accepts pre-built chunks (e.g. one per EP-026
    `SemanticResult`), and delegates deduplication/ordering/limit
    enforcement to the active CompressionProvider. Also exposes
    `compress_query()`, an optional integration point that runs a query
    through EP-026's SemanticEngine (public `search()` method and
    `SemanticResult` fields only) and compresses the results in one
    call -- entirely optional; `compress_text()`/`compress_chunks()`/
    `compress_semantic_results()` work with no Semantic Search
    dependency at all
  - src/core/context_compression/__init__.py: package-level public
    exports
- CompressionService (src/services/context_compression_service.py):
  config-driven ('context_compression.enabled',
  'context_compression.default_provider',
  'context_compression.max_context_characters',
  'context_compression.max_chunks', 'context_compression.deduplicate')
  business logic, a thin CLI-facing wrapper around
  CompressionManager/CompressionEngine
- ContextCompressionModule (src/modules/context_compression_module.py):
  "compression" CLI namespace -- help / status / providers / use /
  analyze / compress / limits
- config/config.yaml: new 'context_compression' section ('enabled',
  'default_provider', 'max_context_characters', 'max_chunks',
  'deduplicate')
- EP-027 test suite (tests/EP027/test_context_compression.py)

### Changed

- src/bootstrap.py: registers CompressionManager/CompressionEngine/
  CompressionService/ContextCompressionModule after Semantic Search,
  wrapped in a try/except for ContextCompressionError so invalid
  'context_compression.*' configuration disables the Context
  Compression subsystem for that run (logged) instead of crashing
  startup. Context Compression has no hard dependency on Semantic
  Search, the Embedding Engine, Knowledge Base, or Long-Term Memory --
  `compress_text()`/`compress_chunks()` work on raw text/chunks alone,
  so the subsystem is wired unconditionally; only the optional
  `compress_query()` path is affected if Semantic Search is
  unavailable this run. The SemanticEngine instance built for EP-026
  (when available) is captured locally and passed to CompressionEngine,
  read-only, through its public `search()` method only. No change to
  startup order or wiring for any other subsystem.
- src/modules/test_module.py: registers the EP-027 test suite so
  'test EP027' and 'test all' pick it up

### Improved

- Context assembled from EP-026 Semantic Search (or from any raw text)
  can now be deduplicated and capped to a maximum size before it is
  used elsewhere, reusing EP-026's public `SemanticResult` model
  instead of introducing a new retrieval pipeline or new storage.

---



Released: 2026-08-02

### Added

- Semantic Search subsystem (src/core/semantic/), a new independent
  package:
  - SemanticCandidate / SemanticResult (semantic_result.py): plain
    data model for one searchable record (source, identifier, text,
    vector, metadata) and one ranked match (source, identifier, text,
    score, metadata)
  - SemanticProvider interface (semantic_provider.py): unified
    search()/rank()/status() contract for every semantic search
    provider
  - DefaultSemanticProvider (semantic_provider.py): the built-in
    provider, registered under the name "semantic" -- brute-force
    cosine similarity over already-embedded candidates, no external
    index, no network access, no AI reasoning
  - SemanticManager (semantic_manager.py): orchestration layer --
    register/select semantic providers, enable/disable the subsystem,
    expose status, and own the default `top_k` /
    `similarity_threshold` search parameters read from
    'semantic.*' configuration
  - SemanticEngine (semantic_engine.py): the query -> candidates ->
    ranked-results pipeline -- generates a query vector via EP-021's
    EmbeddingEngine, gathers and embeds candidates from EP-024's
    KnowledgeService and EP-025's LongTermMemoryService (both public
    APIs only, both optional), deduplicates any record reachable
    through both (see Fixed), and delegates scoring/ranking to the
    active SemanticProvider
  - Placeholder-embedding-provider detection
    (`SemanticEngine.embedding_provider_warning()`): EP-021's only
    offline, always-available embedding provider ("local") hashes
    each text as a whole via SHA-256, so by the avalanche property any
    two non-identical texts -- related or not -- score as uncorrelated
    noise; only byte-identical text is meaningfully matched. When that
    specific, well-known provider is active (detected via
    EmbeddingManager's public `provider_name()`, never by touching any
    private state), a clear warning is surfaced through
    `SemanticService.status()` and `semantic status` explaining the
    limitation and how to get genuine semantic search (configure a
    real embedding provider). 'semantic.similarity_threshold' is used
    exactly as configured for every provider, always -- this module
    never adjusts it (an earlier iteration of this feature relaxed the
    threshold toward 0.0 for the placeholder provider; broader testing
    proved that only admits a coin-flip ~50% of unrelated candidates
    as if they were meaningful matches, which is worse than returning
    nothing, so that adjustment was removed before release)
  - src/core/semantic/__init__.py: package-level public exports
- SemanticService (src/services/semantic_service.py): config-driven
  ('semantic.enabled', 'semantic.default_provider', 'semantic.top_k',
  'semantic.similarity_threshold') business logic, a thin CLI-facing
  wrapper around SemanticManager/SemanticEngine
- SemanticModule (src/modules/semantic_module.py): "semantic" CLI
  namespace -- help / status / providers / use / search / threshold
- config/config.yaml: new 'semantic' section ('enabled',
  'default_provider', 'top_k', 'similarity_threshold')
- EP-026 test suite (tests/EP026/test_semantic_search.py)

### Changed

- src/bootstrap.py: registers SemanticManager/SemanticEngine/
  SemanticService/SemanticModule after the RAG Engine, wrapped in a
  try/except for SemanticError so invalid 'semantic.*' configuration
  disables the Semantic Search subsystem for that run (logged) instead
  of crashing startup. Because generating a query/candidate vector is
  a hard dependency on the Embedding Engine, Semantic Search also
  disables itself gracefully (logged) if the Embedding Engine is
  unavailable this run -- mirroring exactly how EP-022's RAG Engine
  already degrades in the same situation. Knowledge Base and Long-Term
  Memory are soft dependencies: either being unavailable this run only
  narrows what Semantic Search can find, it never disables the
  subsystem itself. EmbeddingManager (already built for the Embedding
  Engine/RAG Engine) is also passed to SemanticEngine, read-only, for
  placeholder-provider detection. No change to startup order or wiring
  for any other subsystem.
- src/modules/test_module.py: registers the EP-026 test suite so
  'test EP026' and 'test all' pick it up

### Improved

- Knowledge Base and Long-Term Memory records can now be found by
  meaning rather than only by exact key/id lookup, reusing EP-021's
  Embedding Engine and EP-024/EP-025's public read APIs instead of
  introducing a new storage engine or a new embedding pipeline

### Fixed

- SemanticManager.current_provider_name() incorrectly returned the
  resolved provider name (e.g. "semantic") even when
  'semantic.enabled: false' was set from startup, contradicting
  is_enabled() and get_current() (which already correctly returned
  False/None). Now consistently returns None in both disablement
  paths -- config-time and the runtime disable() call.
- A record reachable through both KnowledgeService.list_records() and
  LongTermMemoryService.list_memories() -- which happens for every
  Long-Term Memory record, since EP-025's
  KnowledgeBackedLongTermProvider persists them inside KnowledgeService's
  own storage under the record's own id as the key -- was returned
  twice in search results, once under each source label. Long-Term
  Memory records are now deduplicated against Knowledge Base results
  by identifier, keeping the more specific `long_term_memory` label.

### Compatibility

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its signature/
behavior changed. Introduces no duplicate embedding/knowledge/memory/
retrieval subsystem -- Semantic Search performs no answer generation,
AI provider calls, prompt construction, context compression, planning,
reflection, or reasoning, has no dependency on the RAG Engine, any AI
Provider, the Prompt Engine, Browser Automation, Tool Calling, the
Conversation Engine, or any future Agent Framework component, and
SemanticManager owns no record/vector storage state of its own.

---

## v0.1.0-ep025

Released: 2026-08-01

### Added

- Long-Term Memory subsystem (src/core/long_term_memory/), a new
  independent package:
  - LongTermRecord (long_term_record.py): plain data model for a single
    long-lived memory (id, content, metadata, status, timestamps,
    archived_at)
  - LongTermProvider interface (long_term_provider.py): unified
    store/get/update/archive/delete/clear/list/stats contract for
    every long-term-memory provider
  - KnowledgeBackedLongTermProvider (long_term_provider.py): the default
    provider, persisting memories through EP-024's KnowledgeService
    public API inside a dedicated "long_term_memory" collection --
    introduces no new storage engine
  - LongTermMemoryProvider (long_term_provider.py): adapts Long-Term
    Memory to EP-023's MemoryProvider interface so it can be registered
    with the Memory Manager
  - LongTermMemoryManager (long_term_manager.py): orchestration layer --
    register/unregister providers, enable/disable, switch the active
    provider, expose status, and delegate the unified long-term-memory
    API to whichever provider is active
  - src/core/long_term_memory/__init__.py: package-level public exports
- LongTermMemoryService (src/services/long_term_memory_service.py):
  config-driven ('long_term_memory.enabled',
  'long_term_memory.default_provider') business logic, building a
  default LongTermMemoryManager around a KnowledgeBackedLongTermProvider
  named "knowledge", and best-effort registering a LongTermMemoryProvider
  with EP-023's Memory Manager when available
- LongTermMemoryModule (src/modules/long_term_memory_module.py): "ltm"
  CLI namespace -- status / list / info / archive / clear / statistics
  / help
- config/config.yaml: new 'long_term_memory' section ('enabled',
  'default_provider')
- EP-025 test suite (tests/EP025/test_long_term_memory.py)

### Changed

- src/services/memory_service.py: added `register_provider(provider,
  enabled=True)`, a thin pass-through to `MemoryManager.register` --
  the public extension point EP-025 uses to register its
  LongTermMemoryProvider without reaching into MemoryService's
  internals. Every existing MemoryService method, CLI command, and
  public signature is unchanged.
- src/bootstrap.py: registers LongTermMemoryService/LongTermMemoryModule
  after Memory and Knowledge Base, wrapped in a try/except for
  LongTermProviderError so invalid 'long_term_memory.default_provider'
  configuration disables the Long-Term Memory subsystem for that run
  (logged) instead of crashing startup. Because Long-Term Memory's
  persistence is a hard dependency on Knowledge Base, it also disables
  itself gracefully (logged) if Knowledge Base is unavailable this run.
  No change to startup order or wiring for any other subsystem.
- src/modules/test_module.py: registers the EP-025 test suite so
  'test EP025' and 'test all' pick it up

### Improved

- Important memories can now be persisted long-term and moved through
  an active/archived lifecycle, decoupled from EP-023's short-lived
  Memory Manager store and EP-024's general-purpose Knowledge Base
  collections, while reusing both through their public APIs instead of
  introducing a third storage engine

### Fixed

-

### Compatibility

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its signature/
behavior changed, aside from the additive `MemoryService.register_provider`
method. Introduces no duplicate memory/knowledge/embedding/retrieval
subsystem -- Long-Term Memory performs no ranking, similarity search,
embeddings, or AI reasoning, has no dependency on Semantic Search,
Context Compression, Reflection, Planner, Agent Framework, Browser
Automation, Vector Database, Embedding, Retrieval, RAG, or any future
EP, and LongTermMemoryManager owns no storage state of its own.

---

## v0.1.0-ep024

Released: 2026-08-01

### Added

- Knowledge Base subsystem (src/core/knowledge/), a new independent package:
  - KnowledgeRecord (knowledge_record.py): plain data model for a single
    structured knowledge record (key, content, collection, metadata,
    timestamps)
  - KnowledgeCollection (knowledge_collection.py): thread-safe,
    collection-organized storage engine -- store/load/update/delete/clear/
    list plus per-collection statistics
  - KnowledgeProvider interface and KnowledgeCollectionProvider adapter
    (knowledge_provider.py), mirroring EP-023's MemoryProvider pattern
  - KnowledgeManager (knowledge_manager.py): orchestration layer --
    register/unregister providers, enable/disable, switch the active
    provider, expose status, and delegate the unified knowledge API to
    whichever provider is active
  - src/core/knowledge/__init__.py: package-level public exports
- KnowledgeService (src/services/knowledge_service.py): config-driven
  ('knowledge.enabled', 'knowledge.default_provider') business logic,
  building a default KnowledgeManager around a KnowledgeCollectionProvider
  named "local"
- KnowledgeModule (src/modules/knowledge_module.py): "knowledge" CLI
  namespace -- status / collections / list / info / clear / help
- config/config.yaml: new 'knowledge' section ('enabled', 'default_provider')
- EP-024 test suite (tests/EP024/test_knowledge_base.py)

### Changed

- src/bootstrap.py: registers KnowledgeService/KnowledgeModule, wrapped in
  a try/except for KnowledgeProviderError so invalid
  'knowledge.default_provider' configuration disables the Knowledge
  subsystem for that run (logged) instead of crashing startup, mirroring
  the Memory/Embedding/RAG degrade-gracefully pattern. No change to
  startup order or to any other subsystem's wiring.
- src/modules/test_module.py: registers the EP-024 test suite so
  'test EP024' and 'test all' pick it up

### Improved

- Structured project knowledge (docs, facts, reference records) now has a
  dedicated home, decoupled from EP-023's Memory Manager, EP-021's
  Embedding, and EP-022's RAG Engine, so those subsystems can evolve
  independently of how knowledge is organized into collections

### Fixed

-

### Compatibility

Fully backward compatible with every prior EP. No existing service,
manager, or CLI command was renamed, removed, or had its signature/
behavior changed. Introduces no duplicate memory/embedding/retrieval
subsystem -- Knowledge Base performs no reasoning, has no dependency on
Embedding, Retrieval, RAG, Long-Term Memory, Semantic Search, Context
Compression, Planner, Reflection, Agent Framework, Browser Automation, or
Vector Database, and KnowledgeManager owns no storage state of its own.

---



Released: 2026-07-31

### Added

- MemoryProvider interface (src/core/memory/memory_provider.py):
  store/load/delete/clear/exists/list contract every memory provider must
  implement
- MemoryStoreProvider (src/core/memory/memory_provider.py): adapter wrapping
  the existing (EP-013) MemoryStore as the built-in "memory" provider,
  introducing no new storage logic
- MemoryManager (src/core/memory/memory_manager.py): orchestration layer --
  register/unregister providers, enable/disable, switch the active
  provider, expose status, and delegate the unified memory API to whichever
  provider is active
- src/core/memory/__init__.py: package-level exports for both EP-013 and
  EP-023 public symbols
- CLI integration: memory providers / memory use <provider>
- EP-023 test suite (tests/EP023/test_memory_manager.py)

### Changed

- src/services/memory_service.py: added an optional `manager` constructor
  parameter (MemoryManager | None = None, default preserves prior
  behavior); composes a MemoryManager that registers the same MemoryStore
  as the "memory" provider; added `providers_status()`, `current_provider()`
  and `use_provider()`. Every existing EP-013 method and signature is
  unchanged.
- src/modules/memory_module.py: added "providers" and "use" CLI actions and
  updated help text. Every existing EP-013 command is unchanged.
- config/config.yaml: added 'memory.default_provider' ("memory") to the
  existing 'memory' section
- src/bootstrap.py: wrapped the existing Memory subsystem wiring in a
  try/except for MemoryProviderError, so invalid 'memory.default_provider'
  configuration disables the Memory subsystem for that run (logged) instead
  of crashing startup, mirroring the Embedding/RAG degrade-gracefully
  pattern. No change to startup order or to any other subsystem's wiring.
- src/modules/test_module.py: registers the EP-023 test suite so
  'test EP023' and 'test all' pick it up

### Improved

- Memory now has a single, provider-agnostic API surface
  (register/enable/disable/switch/status) that future providers
  (Knowledge Base, Long-Term Memory, External, etc.) can register against
  without any caller needing to change

### Fixed

-

### Compatibility

Fully backward compatible with EP-013. No existing MemoryService method,
MemoryStore behavior, or `memory` CLI command was renamed, removed, or had
its signature/behavior changed. Introduces no second memory subsystem --
MemoryManager owns no storage state of its own and delegates every
operation to the same MemoryStore EP-013 already manages.

---

## v0.1.0-ep022

Released: 2026-07-31

### Added

- RAG Engine (src/core/rag/rag_engine.py)
- RAG Manager (src/core/rag/rag_manager.py)
- RagProviderInfo / RagContextItem / RagResult domain models
- RAG Service
- RAG Module
- CLI integration: rag help / status / query / context / provider / use
- EP-022 test suite (tests/EP022/test_rag_engine.py)

### Changed

- src/bootstrap.py: wires RagManager/RagService/RagModule into the command
  router, mirroring the Embedding Engine's degrade-gracefully-on-invalid-config
  pattern
- config/config.yaml: added a 'rag' configuration section (enabled, top_k,
  max_context_characters)
- src/modules/test_module.py: registers the EP-022 test suite so 'test EP022'
  and 'test all' pick it up

### Improved

- Retrieval (EP-020) and embedding (EP-021) are now composed into a single,
  reusable context-generation pipeline consumable by future EPs

### Fixed

-

### Compatibility

Backward compatible with EP-019, EP-020 and EP-021. Does not modify the
Project Index Engine, the Retrieval Engine, or the Embedding Engine. The RAG
Engine calls no AI provider and performs no chat completion.

---

## v0.1.0-ep021

Released: 2026-07-30

### Added

- Embedding Engine
- EmbeddingProvider interface
- Embedding Manager
- Embedding Service
- Embedding Module
- Local embedding provider (deterministic, offline)
- Cloud embedding provider (configuration-driven placeholder)
- CLI integration
- Embedding tests

### Improved

- Provider-independent architecture pattern extended beyond chat completion

### Fixed

-

### Compatibility

Backward compatible with EP-020. Does not modify the Retrieval Engine.

---

## v0.1.0-ep020

Released: 2026-07-30

### Added

- Retrieval Engine
- Retrieval Service
- Retrieval Module
- Search API
- CLI integration
- Retrieval tests

### Improved

- AI infrastructure
- Project navigation
- Knowledge retrieval pipeline

### Fixed

- Internal integration issues between EP-019 and EP-020

### Compatibility

Backward compatible with EP-019.

---

# [Unreleased]

## Added

-

## Changed

-

## Fixed

-

---

# [0.1.0-alpha] - 2026-07-28

## Added

- Interactive Shell (EP-002)
- Process Manager (EP-003)
- AI Provider Framework (EP-014)
- AI Providers (EP-015)
- Conversation Engine (EP-016)
- Prompt Engine (EP-017)
- Universal Context Engine (EP-018)
- PROJECT_MANIFEST.md
- Architecture documentation
- Engineering documentation

## EP-019

Added Project Index Engine.

Features:

- ProjectIndexer
- ChunkBuilder
- JsonIndexStorage
- MemoryIndexStorage
- Index CLI
- Shared PROJECT_MANIFEST parser

## Changed

- Project documentation reorganized.
- Architecture documentation moved to `docs/architecture/`.
- Engineering documentation moved to `docs/engineering/`.
- Context loading redesigned to use `PROJECT_MANIFEST.md` as the single entry point.

## Fixed

- Prompt size budgeting.
- Conversation history budgeting.
- Context Loader document discovery.
- Provider-independent context loading.
- Gemini prompt overflow issues.

---

Future releases will be documented here.