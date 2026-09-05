# EP-061 STEP 3 — Architecture Audit

Status: **AUDIT COMPLETE.**

Scope: `docs/architecture/designs/EP061_DESIGN.md` vs. the actual EP-061
implementation (`src/services/scheduler_service.py`,
`src/services/runtime_service.py`, `src/bootstrap.py`,
`src/modules/test_module.py`, `tests/EP061/`, the one disclosed comment
change in `tests/EP060/test_runtime_lifecycle.py`), Owner Decisions
D1–D4, EP-060's assumptions/compatibility boundaries, and this
project's existing lifecycle/architecture contracts.

Methodology: every finding below is checked directly against the
repository's current file contents (re-viewed during this audit, not
assumed from the STEP 2 report), cross-checked against a `git diff`
taken against the exact pre-STEP-1 baseline commit
(`c8cc5b8 baseline EP-060 state`, created before `EP061_DESIGN.md`
existed), plus a fresh, independent, from-scratch re-run of every
relevant test suite in a clean process. No source, test, configuration,
dependency, or design file was modified to produce this document except
where explicitly noted in Section 7 (test-file documentation staleness
findings, reported but **not** remediated in STEP 3, matching
`EP060_ARCHITECTURE_AUDIT.md` Section 7's own precedent of disclosing
without fixing).

---

## 1. SchedulerService

| Check | Evidence | Verdict |
|---|---|---|
| `shutdown()` is purely additive | `git diff c8cc5b8 -- src/services/scheduler_service.py` shows zero deleted/modified lines — every hunk is a pure insertion (docstrings, `_DEFAULT_SHUTDOWN_TIMEOUT`, `_shutdown_timeout` field, `_resolve_shutdown_timeout()`, `shutdown()`) | **PASS** |
| No existing method's body changed | Same diff: `_start_tick_loop()`, `_tick_loop()`, `_is_tick_loop_running()`, `register/unregister/start/stop/run/list_jobs/get_job/status/doctor` all appear with zero changed lines | **PASS** |
| `shutdown()` signature matches Section 7.1 | Direct introspection: `inspect.signature(SchedulerService.shutdown)` → `(self, wait: 'bool' = True, timeout: 'float | None' = None) -> 'bool'` | **PASS** |
| Public method count = previous 9 + 1 | Direct introspection: `{'doctor','get_job','list_jobs','register','run','shutdown','start','status','stop','unregister'}`, 10 total | **PASS** |
| Lock-scope: `_lifecycle_lock` not held across `thread.join()` | Re-read current source: the `with self._lifecycle_lock:` block ends before `if not wait:`/`thread.join(...)`; a second `with self._lifecycle_lock:` re-acquires only for the final identity-guarded clear | **PASS** |
| Identity guard on cleanup (`if self._tick_thread is thread`) | Present, unchanged from STEP 2 | **PASS** |
| No new public restart/resume method | Same 10-method set above contains no `restart`/`resume`/second `start`-like entry point beyond the pre-existing per-job `start()` | **PASS** |
| Fixed timeout constant, no new config key | `_DEFAULT_SHUTDOWN_TIMEOUT: float = 5.0` is a class constant, not read from `Config`; `config/config.yaml` confirmed byte-identical to baseline (Section 9) | **PASS** |

Executed proof: `tests/EP061/test_scheduler_shutdown.py`'s isolation
tests (`_test_shutdown_never_started_returns_true_immediately`,
`_test_shutdown_stops_a_running_tick_loop`,
`_test_shutdown_is_idempotent`, `_test_shutdown_no_wait_returns_promptly`,
`_test_manual_run_still_works_after_shutdown`,
`_test_shutdown_does_not_hold_lock_during_join`,
`_test_concurrent_shutdown_calls_are_race_safe`,
`_test_concurrent_shutdown_does_not_clear_a_replacement_thread`) — all
passed in this audit's fresh re-run (Section 8).

**Section 1 verdict: PASS, no findings.**

---

## 2. RuntimeService

### 2.1 `RuntimeShutdownReport`

Direct introspection (`dataclasses.fields`) confirms exactly six
fields, in the order: `rest_api_was_active`, `rest_api_stopped`,
`background_workers_was_active`, `background_workers_stopped`,
`scheduler_was_active`, `scheduler_stopped` — the two new fields
appended last, both defaulted (`False`/`True`), matching
`EP061_DESIGN.md` Section 7.2 exactly, including the explicit
design-doc note that declaration order (append-only, for
backward-compatibility) intentionally differs from execution order
(Scheduler stopped second, not last).

**Verdict: PASS.**

### 2.2 `shutdown()` body — placement and ordering

`git diff c8cc5b8 -- src/services/runtime_service.py` shows the new
Scheduler block (`scheduler_was_active`/`scheduler_stopped` computation
and the `SchedulerService.shutdown()` call) inserted as a contiguous
hunk **between** the pre-existing, byte-identical REST API block and
the pre-existing, byte-identical Background Worker Service block — not
appended after it. This is a structural, diff-verified guarantee that
the code matches Owner Decision D2's revised (STEP 1 validation)
ordering, not merely a claim in a docstring.

Executed, real-object proof:
`_test_runtime_shutdown_orders_rest_api_then_scheduler_then_background_workers`
wraps a real `RestApiServer`, a real `SchedulerService`, and a real
`BackgroundWorkerService` in call-order-recording proxies and asserts
`order_log == ["rest_api", "scheduler", "background_workers"]` — passed
in this audit's fresh re-run.

**Verdict: PASS.**

### 2.3 Constructor / backward compatibility

`RuntimeService.__init__`'s five parameters (`started_at`,
`rest_api_server`, `background_worker_service`, `shell`,
`scheduler_service`) are unchanged in name, order, type, and default
from the pre-EP-061 (EP-060) state — confirmed by the diff touching
only docstring lines inside `__init__`, zero signature lines. All 15
`RuntimeService(...)` construction call sites in
`tests/EP059/test_runtime.py` (itself confirmed byte-identical to
baseline, Section 9) continue to pass, unmodified, in this audit's
fresh re-run (93/93).

**Verdict: PASS.**

### 2.4 Reuse of existing lifecycle primitives only

`shutdown()` calls exactly three subsystem methods, all pre-existing
except one: `RestApiServer.stop()` (EP-043, unchanged), the new
`SchedulerService.shutdown()` (EP-061, Section 1), and
`BackgroundWorkerService.shutdown()` (EP-036, unchanged — confirmed
byte-identical to baseline, Section 9). No new thread, socket,
subprocess, signal handler, timer, queue, or registry is created
anywhere in `runtime_service.py`.

**Verdict: PASS.**

### 2.5 Idempotency

`shutdown()` holds no new "already shut down" instance state — the
diff adds no new `self.<attr> =` assignment anywhere in the method or
`__init__`. Idempotency is entirely a composed property of the three
callees, each independently idempotent: `RestApiServer.stop()` (guard
confirmed unchanged), `SchedulerService.shutdown()` (Section 1's
identity-guarded, `None`-check-first implementation), and
`BackgroundWorkerService.shutdown()` (unchanged, EP-060-confirmed
`_is_shutdown`-guarded).

Executed proof: `_test_runtime_shutdown_idempotent_with_scheduler`
(two consecutive `shutdown()` calls on a `RuntimeService` wired to a
real, running `SchedulerService`; neither raises; `scheduler_stopped`
is `True` both times; final `status().running` is `False`) — passed.

**Verdict: PASS.**

### 2.6 Partial-failure / exception behavior

No `try`/`except` was added anywhere in `shutdown()` (confirmed: the
diff introduces zero `try` keywords). Matches `EP061_DESIGN.md`
Section 7.2/13's explicit choice to keep unguarded, fail-fast,
sequential composition, consistent with the pre-existing (EP-060)
behavior for the same reason.

**Verdict: PASS.**

### 2.7 No accidental widening of `RuntimeService`'s own public surface

Direct introspection confirms exactly `{shutdown, status}` — unchanged
count (2) from EP-060. `status()`'s body is untouched by the diff
(zero changed lines inside `status()` itself — the new Scheduler
observation logic it already had, from EP-060, is unmodified by
EP-061).

**Verdict: PASS.**

**Section 2 verdict: PASS, no findings.**

---

## 3. Bootstrap

### 3.1 `shutdown()` body is unmodified (Owner Decision D3)

`git diff c8cc5b8 -- src/bootstrap.py` shows the diff confined entirely
to docstring lines. The four executable lines of `shutdown()`'s body
(`if self._runtime_service is not None: ... elif ...: ... self.
_rest_api_server = None; self._background_worker_service = None`) do
not appear anywhere in the diff — direct, structural proof the body is
byte-identical to its pre-EP-061 (EP-060) state, not merely a claim.

**Verdict: PASS.**

### 3.2 `self._scheduler_service` is not nulled

Consequence of 3.1: since the body is unchanged and the pre-EP-061
body never referenced `_scheduler_service` at all, it necessarily
still doesn't null it. Confirmed by direct text search of the current
method body: no `scheduler` token appears in the executable code, only
in the docstring.

Executed proof:
`_test_bootstrap_shutdown_preserves_scheduler_service_identity` (real
`Bootstrap`, `auto_start: true`, `initialize()` → capture reference →
`shutdown()` → assert `bootstrap.scheduler_service is not None` and
`is` the captured reference) — passed. This is a stronger, more direct
proof than the pre-existing EP-060 guard test (Section 7 discusses that
test separately), since this new EP-061 test uses a Scheduler that
*was actually running* before `shutdown()`, whereas the pre-existing
EP-060 test's default config never started the tick loop in the first
place.

**Verdict: PASS.**

### 3.3 Scheduler tick loop is actually stopped end-to-end

Executed proof:
`_test_bootstrap_shutdown_stops_scheduler_tick_loop` (real `Bootstrap`,
`auto_start: true`, confirms `status().running` is `True` after
`initialize()` and `False` after `shutdown()`) — passed. This closes
the loop from "the code path exists" (Sections 1–2) to "the real,
composed system actually exhibits the fixed behavior."

**Verdict: PASS.**

### 3.4 Repeated / uninitialized-state safety unchanged

Executed proof: `_test_bootstrap_shutdown_twice_does_not_raise_or_hang`
and `_test_bootstrap_shutdown_without_initialize_does_not_raise` —
both passed, reproducing the exact safety guarantees
`EP060_ARCHITECTURE_AUDIT.md` Sections 3.3–3.4 already established and
confirming EP-061 did not regress them.

**Verdict: PASS.**

**Section 3 verdict: PASS, no findings.**

---

## 4. SchedulerModule / RuntimeModule public surface (Owner Decision D1)

| Check | Evidence | Verdict |
|---|---|---|
| `src/modules/scheduler_module.py` byte-identical to baseline | `git diff c8cc5b8 -- src/modules/scheduler_module.py` → 0 lines | **PASS** |
| `src/modules/runtime_module.py` byte-identical to baseline | `git diff c8cc5b8 -- src/modules/runtime_module.py` → 0 lines | **PASS** |
| `SchedulerModule` exposes exactly the original 8 actions | Direct instantiation + introspection: `{'doctor','help','info','list','run','start','status','stop'}` | **PASS** |
| No `shutdown`/`stop-loop`/`kill` action leaked in | Confirmed absent from the same set above | **PASS** |
| `RuntimeModule` exposes exactly `{status, help}` | Direct instantiation + introspection: `{'help','status'}` | **PASS** |

Executed proof: `_test_scheduler_module_cli_actions_unchanged` and
`_test_runtime_module_cli_actions_unchanged` — both passed.

**Section 4 verdict: PASS, no findings.**

---

## 5. Owner Decisions — audited one by one

**D1 — No CLI/REST exposure for the new capability.** Approved
option (a). Confirmed in Section 4: neither module file was touched at
all (0-line diffs), so there is no code path by which `shutdown()`
could have become CLI/REST-reachable. **PASS.**

**D2 — Shutdown ordering: REST API → Scheduler → Background Workers.**
Approved, revised during STEP 1 validation from an initial ("last")
draft after independently verifying `Scheduler`/`BackgroundWorkerService`
share no execution path (re-confirmed directly in this audit, not just
trusted from the design doc — see the box below). Implementation
matches: Section 2.2's diff-level proof plus the passing three-way
ordering test. **PASS.**

*Independent re-verification of D2's factual basis (not merely
trusting `EP061_DESIGN.md`'s own text):* `src/core/scheduler/scheduler.py`
line 179 confirmed `self._execution_engine.run(job.command)` (EP-003
`ExecutionEngine`, `src/core/execution/engine.py`) is called directly
and synchronously from `run_job()`, itself called synchronously from
`tick()`. `src/core/workflow_engine/workflow_engine.py` line 32
confirmed it imports and depends on `PlanExecutionEngine` (EP-030,
`src/core/plan_execution/plan_execution_engine.py`) — a separate class
from EP-003's `ExecutionEngine`, with no import relationship between
the two files. This audit independently re-derived the same
"structurally independent, no shared queue" conclusion the design doc
states, from source, not from the design doc's own prose. **PASS.**

**D3 — `Bootstrap.shutdown()` does not null `_scheduler_service`.**
Approved. Confirmed via diff (Section 3.1) and via the strongest
available executed proof (Section 3.2's test, using a Scheduler that
was actually running before shutdown, not the weaker pre-existing
EP-060 guard test whose default config never started the tick loop at
all). **PASS.**

**D4 — Fixed 5-second join timeout, no new `scheduler.shutdown_timeout`
config key.** Approved. `config/config.yaml` confirmed byte-identical
to baseline (Section 9) — no key added. `_DEFAULT_SHUTDOWN_TIMEOUT: float
= 5.0` confirmed present as a class constant (Section 1).

*Independent re-verification of D4's factual basis:* this audit
re-ran the same grep the design doc cites (`Popen`/`.wait(` across
`src/core/execution/executors/*.py`) and found `process_executor.py`,
`python_executor.py`, and `file_executor.py` each call
`subprocess.Popen(...)` with no `.wait()` — consistent with the
design's claim. However, `url_executor.py` does **not** call
`subprocess.Popen()` at all; it calls `webbrowser.open(target)`
(Python standard library), which is also non-blocking in practice (it
launches the browser and returns immediately, without waiting for the
browser process to exit) but is a different mechanism than the other
three executors. `EP061_DESIGN.md` Section 2.1/10's phrasing —
*"every executor that launches an OS process uses
`subprocess.Popen(...)`... confirmed by grepping all four executor
files: none blocks on subprocess completion"* — is imprecise: three of
the four use `Popen`; the fourth uses `webbrowser.open()`. The
**conclusion** (no executor blocks the tick thread) remains correct
and unaffected — `webbrowser.open()`'s own non-blocking behavior is
well-established standard-library behavior, not something this audit
disputes — but the design doc's evidence citation overstates
uniformity across the four executors.

**Verdict: PASS on the decision itself; WARNING (non-blocking,
documentation-only) on the precision of its supporting evidence
citation in `EP061_DESIGN.md`.** See Section 7 for disposition
alongside this audit's other documentation-only finding. No
implementation change is warranted: `SchedulerService.shutdown()`'s
behavior does not depend on which specific non-blocking mechanism a
given executor uses, only on the (independently reconfirmed) fact that
none of the four blocks the tick thread.

**Section 5 verdict: PASS on all four Owner Decisions; one
non-blocking documentation-precision WARNING carried into Section 7.**

---

## 6. Architecture boundaries — confirmed NOT introduced

| Boundary | Check performed | Verdict |
|---|---|---|
| New registry, event bus, or scheduler abstraction | `grep -n "EventBus\|event_bus\|class.*Registry\|class.*Scheduler"` across the diffed files returns no new class definition of any of these shapes | **PASS** |
| New CLI/REST action | Section 4 | **PASS** |
| New configuration key | `config/config.yaml` confirmed byte-identical to baseline (0-line diff) | **PASS** |
| New dependency | `requirements.txt` confirmed byte-identical to baseline (0-line diff); no new third-party `import` anywhere in the diff | **PASS** |
| Forceful termination (`os.kill`/`SIGKILL`/thread interrupt) | None present anywhere in the diff; `shutdown()` uses only `threading.Event.set()` and `Thread.join()` | **PASS** |
| Unrelated refactoring | Full `git diff c8cc5b8 --stat` (Section 9) contains exactly 8 files, all within the approved STEP 2 scope | **PASS** |
| `src/core/scheduler/*.py` untouched | `scheduler.py`, `job.py`, `job_registry.py` each confirmed 0-line diff against baseline | **PASS** |
| `SchedulerModule`/`RuntimeModule` untouched | Section 4 | **PASS** |
| `BackgroundWorkerService`/`RestApiServer`/`ExecutionEngine` untouched | Each confirmed 0-line diff against baseline (Section 9) | **PASS** |
| `pyproject.toml` untouched | Confirmed 0-line diff against baseline | **PASS** |

**Section 6 verdict: PASS, no findings.**

---

## 7. Test-file documentation staleness (findings, not remediated in STEP 3)

**Finding, classified:** two comments/docstrings inside
`tests/EP060/test_runtime_lifecycle.py` — a file EP-061's approved
design (Section 12/16) authorized exactly **one** comment-only edit to
(inside `_test_bootstrap_shutdown_does_not_touch_scheduler_service`,
already correctly updated in STEP 2, verified in Section 9's diff) —
contain two *additional*, previously-undisclosed locations that now
make a present-tense factual claim about `SchedulerService` that
EP-061 has made false. Neither affects any test's pass/fail outcome
(confirmed: both are comments/docstrings, not assertions; the full
EP-060 suite passes 65/65 in this audit's fresh re-run, Section 8) —
this is a documentation-accuracy finding, not a correctness or
compatibility defect.

**Location 1 (module docstring, lines 25–27):**
```
- The Scheduler's tick loop is deliberately never stopped by this
  EP (Owner Decision D5) -- `SchedulerService` (EP-011) exposes no
  public primitive to do so; it is observed, not controlled.
```
This is defensible as-is: it is explicitly scoped to "by this EP"
(i.e., by EP-060), describing EP-060's own, historically accurate
decision at the time it was made. `EP061_DESIGN.md` itself is treated
as a frozen historical artifact once approved (this audit does not
require EP-060's own design doc to be retroactively rewritten either).
**No remediation required for this location.**

**Location 2 (`_stop_scheduler_tick_loop_for_test_cleanup`'s
docstring, lines 207–208):**
```
`SchedulerService` (EP-011) exposes no public method to stop its
tick loop (`EP060_DESIGN.md` Section 5.2/9.3, Owner Decision D5) --
this is exactly the confirmed gap EP-060 deliberately leaves
unclosed in production code.
```
This is a **live, present-tense claim about `SchedulerService`'s
current API surface**, not a historically-scoped one — and it is now
factually false: `SchedulerService.shutdown()` exists (Section 1).
The helper function itself remains correct and safe to keep using
(reaching into `_stop_event`/`_tick_thread` directly still works,
and `EP061_DESIGN.md` Section 12 explicitly allowed, but did not
require, simplifying this helper to call the new public `shutdown()`
instead) — only its docstring's justification for *why* the helper
reaches into private state is now stale, since a public alternative
exists.

**Why this was not remediated in STEP 3:** this task's explicit
instruction is "do not modify implementation code during STEP 3 unless
a genuine audit finding requires remediation," and this finding is
(a) documentation-only, (b) does not affect any assertion, correctness
guarantee, or the STEP 2 acceptance criteria, and (c) matches the exact
shape of `EP060_ARCHITECTURE_AUDIT.md` Section 7's own precedent — a
disclosed, classified, non-blocking documentation issue explicitly left
for a future step rather than fixed reactively during an audit that is
supposed to check, not silently patch, the approved implementation.

**Recommended disposition (for a future step, not this audit):**
update the docstring at lines 207–208 to note that a public `shutdown()`
now exists, and that this helper is retained only as a minimal,
whitebox test-cleanup convenience rather than because no public
alternative exists — mirroring the wording already used, correctly,
in the one location EP-061's own design *did* authorize updating
(`_test_bootstrap_shutdown_does_not_touch_scheduler_service`'s
comment, Section 9). This is a one-paragraph docstring edit with zero
assertion changes, the same class of fix `EP060_ARCHITECTURE_AUDIT.md`
Section 7 recommended for its own analogous finding.

**Also carried into this section:** Section 5/D4's WARNING regarding
`EP061_DESIGN.md` Section 2.1/10's imprecise "all four executors use
`subprocess.Popen()`" evidence citation (`url_executor.py` actually
uses `webbrowser.open()`). Recommended disposition: a one-sentence
correction to the design doc's own text in a future step, not a code
change — no implementation, test, or Owner Decision is affected.

**Verdict: WARNING (non-blocking) x2.** Neither finding indicates a
defect in EP-061's implementation, test coverage, or backward
compatibility. Both are pre-existing-style documentation drift, of the
same severity class this repository's own prior EP-060 audit
established a precedent for disclosing-without-fixing.

---

## 8. Tests — fresh, independent re-execution for this audit

All suites below were re-run from a clean process (`__pycache__`
cleared, fresh Python interpreter, fresh `TestRegistry` state),
independent of the STEP 2 report, as part of this audit:

| Suite | Result | Matches STEP 2 report? |
|---|---|---|
| EP061 (new) | **62/62 passed** | Yes |
| EP060 (directly affected) | **65/65 passed** | Yes |
| EP059 (directly affected) | **93/93 passed** | Yes |
| EP034 (regression discovery) | 113/113 passed | Yes |
| EP035 (regression discovery) | 143/143 passed | Yes |
| EP037 (regression discovery) | 87/87 passed | Yes |
| Full repository (`run_all`, EP001–EP061) | **6838 passed, 0 failed, 3 skipped** | Yes |

The 3 skips reconfirmed as pre-existing, intentional,
environment-gated `self.skip()` calls in `tests/EP003/
test_execution_engine.py`, `tests/EP046/test_voice.py`, and
`tests/EP048/test_wake_word.py` — all present, unmodified, in the
baseline commit (`git diff c8cc5b8 -- tests/EP003 tests/EP046
tests/EP048` → 0 lines), confirming they predate EP-061 and are
unrelated to it.

Also specifically re-confirmed in this audit: `tests/EP059/
test_runtime.py`'s `_test_service_exposes_only_status` assertion
(the historical `EP060_ARCHITECTURE_AUDIT.md` Section 7 WARNING) now
asserts `sorted(public_methods) == ["shutdown", "status"]` — already
updated prior to EP-061's STEP 1 (confirmed via the STEP 1 baseline
commit, which already contains this updated assertion) and still
correct today, since EP-061 does not change `RuntimeService`'s public
method count (Section 2.7). This is a previously-resolved item, not a
new EP-061 finding — recorded here only for completeness, matching
this repository's audit convention of positively confirming
previously-flagged items rather than silently ignoring them.

**Verdict: PASS.** Every number in the STEP 2 report is reproduced
exactly by this audit's independent re-run.

---

## 9. Diff / scope

Full diff against the exact pre-STEP-1 baseline commit
(`c8cc5b8 baseline EP-060 state`):

```
$ git diff c8cc5b8 --stat
 docs/architecture/designs/EP061_DESIGN.md | 1102 +++++++++++++++++++++++++++++
 src/bootstrap.py                          |   23 +-
 src/modules/test_module.py                |    1 +
 src/services/runtime_service.py           |  138 ++--
 src/services/scheduler_service.py         |   90 +++
 tests/EP060/test_runtime_lifecycle.py     |   17 +-
 tests/EP061/__init__.py                   |    0
 tests/EP061/test_scheduler_shutdown.py    |  840 ++++++++++++++++++++++
 8 files changed, 2157 insertions(+), 54 deletions(-)
```

This is the complete, exact set of files touched since before STEP 1
began (this baseline commit predates `EP061_DESIGN.md` itself), not an
inference from the STEP 2 report. Every file matches
`EP061_DESIGN.md` Section 16's "Changed" list, with one small,
precedent-matching addition (`src/modules/test_module.py`, one import
line) — not listed by name in Section 16, but structurally identical
in kind to `EP060_DESIGN.md`'s own silence on the same file for its
own test-suite registration, confirmed by the fact that EP-060's suite
is registered there too (`import tests.EP060.test_runtime_lifecycle`,
present and unchanged in this diff's context lines).

**No other file appears.** Specifically re-checked and confirmed
byte-identical to baseline (`git diff c8cc5b8 -- <path>` → 0 lines for
every path below):

- `src/core/scheduler/scheduler.py`, `src/core/scheduler/job.py`,
  `src/core/scheduler/job_registry.py`
- `src/modules/scheduler_module.py`, `src/modules/runtime_module.py`
- `src/services/background_worker_service.py`
- `src/core/api/rest_api_server.py`
- `src/core/execution/engine.py`
- `config/config.yaml`
- `requirements.txt`
- `pyproject.toml`
- `tests/EP059/test_runtime.py`

**`tests/EP060/test_runtime_lifecycle.py`'s 17-line diff** was read in
full (Section 2 of this audit's working notes, reproduced in Section 7
above): it consists of exactly one comment block replacement inside
`_test_bootstrap_shutdown_does_not_touch_scheduler_service` (the one
change `EP061_DESIGN.md` Section 12 explicitly authorized) — zero
`assert_*` lines appear in the diff.

**Verdict: PASS.** The diff is exactly the intended EP-061 scope, no
more and no less, verified against a true pre-STEP-1 baseline rather
than inferred.

---

## 10. Design consistency — line-by-line comparison

| Design section | Requirement | Implementation | Verdict |
|---|---|---|---|
| **7.1** | `SchedulerService.shutdown(wait=True, timeout=None) -> bool`, lock released before `join()`, identity-guarded cleanup | Exact match (Section 1); lock-scope note's specific concern independently re-verified against current source | **PASS** |
| **7.2** | `RuntimeShutdownReport` +2 fields (appended); `shutdown()` body places Scheduler between REST API and Background Workers | Exact match (Section 2.1–2.2), diff-verified | **PASS** |
| **7.3** | `Bootstrap.shutdown()` body unchanged; docstring only; `_scheduler_service` not nulled | Exact match (Section 3), diff-verified | **PASS** |
| **7.4** | `scheduler_module.py`, `runtime_module.py`, `core/scheduler/*.py`, `background_worker_service.py`, `rest_api_server.py`, `config.yaml`, `requirements.txt`, roadmap/backlog/changelog/release-notes all untouched | All confirmed byte-identical to baseline (Section 9) | **PASS** |
| **Owner Decisions D1–D4** | All four resolved per their approved (STEP-1-validated) options | Confirmed individually in Section 5 | **PASS**, with one non-blocking evidence-citation WARNING under D4 |
| **Section 9 (API surface table)** | Exact method/action/field counts specified | All reproduced by direct introspection (Sections 1, 2.1, 4) | **PASS** |
| **Section 10 (no new config)** | No `scheduler.shutdown_timeout` key | Confirmed (Section 6) | **PASS** |
| **Section 12 (testing)** | New self-contained `tests/EP061/` suite; full scenario coverage including isolation, ordering, idempotency, Bootstrap e2e, public-surface guards, lock-scope regression guard; one disclosed EP-060 comment update | All present and executed (Section 8); comment update verified scoped correctly (Section 9) | **PASS** |
| **Section 16 (file-level change scope)** | Exact file list | Reproduced exactly, plus one precedent-matching, unlisted registration line (Section 9) | **PASS** |
| **Section 18 (acceptance criteria, 1–10)** | See below | All ten independently re-checked | **PASS**, see detail below |

**Acceptance criteria (Section 18) re-checked individually:**

1. Exactly one new public method, correct signature — **PASS** (Section 1).
2. Every existing `SchedulerService` public method's behavior provably
   unchanged — **PASS** (Section 1, 0-line diff on all pre-existing methods).
3. `scheduler_service.status().running is False` after
   `RuntimeService.shutdown()`, via public API only — **PASS** (Section 2.5, 3.3).
4. `RuntimeShutdownReport` +2 fields exactly as specified — **PASS** (Section 2.1).
5. `RuntimeService`'s public surface remains `{status, shutdown}` — **PASS** (Section 2.7).
6. `Bootstrap.shutdown()` body unmodified; reference preserved — **PASS** (Section 3.1–3.2).
7. No new CLI action, REST action, or config key — **PASS** (Sections 4, 6).
8. `tests/EP059`/`tests/EP060` pass with only the one disclosed comment
   update — **PASS** (Section 8, 9).
9. Final diff touches only the approved file list — **PASS** (Section 9).
10. New, self-contained `tests/EP061/` suite covering Section 12's
    scenarios, passing in full — **PASS** (Section 8; suite also exceeds
    Section 12's minimum coverage with the two additional concurrency
    tests added after STEP 2's own review).

**Section 10 verdict: PASS, no blocking inconsistencies between design
and implementation.**

---

## Summary of findings

| # | Area | Verdict |
|---|---|---|
| 1 | SchedulerService | PASS |
| 2 | RuntimeService | PASS |
| 3 | Bootstrap | PASS |
| 4 | SchedulerModule / RuntimeModule public surface | PASS |
| 5 | Owner Decisions D1–D4 | PASS (all four); non-blocking evidence-citation WARNING under D4 |
| 6 | Architecture boundaries | PASS |
| 7 | Test-file documentation staleness | **WARNING x2** (non-blocking; documentation-only, not defects) |
| 8 | Tests | PASS |
| 9 | Diff / scope | PASS |
| 10 | Design consistency | PASS |

No BLOCKING findings were identified anywhere in this audit. The two
WARNINGs (Section 7) — one pre-existing test-docstring staleness left
by STEP 2's narrowly-scoped comment fix, one design-doc evidence
citation that is imprecise but whose conclusion remains correct — do
not affect correctness, backward compatibility, test validity, or
scope compliance. Consistent with `EP060_ARCHITECTURE_AUDIT.md`'s own
precedent, and this task's explicit "do not modify implementation code
during STEP 3 unless a genuine audit finding requires remediation"
instruction, neither was remediated during this audit: both are
documentation-only, non-blocking, and recommended for a future step.

---

## AUDIT PASSED — NO BLOCKING FINDINGS
