# EP-067 Architecture Audit — TelegramService Poll Loop Exception Containment

STEP 3: Independent Architecture Audit

Status: COMPLETE

---

## 1. Audit Scope

This audit independently verifies STEP 2's implementation of EP-067
against `docs/architecture/designs/EP067_DESIGN.md`. It does not treat
the STEP 2 report as evidence; every number, code excerpt, and
behavioral claim below was re-derived directly from source, from
freshly-run test suites, and from audit-authored runtime probes
constructed independently of `tests/EP067/`'s own fixtures.

No production code, tests, or design document were modified during
this audit. The only file created is this one.

## 2. Authoritative Design

`docs/architecture/designs/EP067_DESIGN.md` was re-read in full,
independently of the STEP 2 report. Its Owner Decisions D1–D10
(Section 11 of that document) are treated as authoritative and audited
individually in Section 4 below.

## 3. Independent Implementation Review

Direct, fresh reading of the current
`src/services/telegram_service.py` (not the STEP 2 report's excerpt)
confirms `_poll_loop()` now reads:

```python
def _poll_loop(self) -> None:
    """Repeatedly poll for and route messages every 'telegram.polling_interval' seconds.

    Mirrors SchedulerService._tick_loop() / WorkflowSchedulerService
    ._tick_loop() / MemoryPersistence._auto_save_loop() (EP-061/
    EP-063/EP-066): any exception raised while executing
    _poll_once() -- beyond the narrower TelegramClientError cases
    _poll_once() already converts into a logged, swallowed failure --
    is caught, logged, and the loop continues rather than the
    "telegram-poll" thread dying silently (EP-067).
    """
    interval = float(self._config.get("telegram.polling_interval", 2))
    while not self._stop_event.wait(interval):
        try:
            self._poll_once()
        except Exception as exc:  # noqa: BLE001 - the poll loop must never die silently
            logger.error(f"Telegram poll loop encountered an unexpected error: {exc}")
    logger.info("Telegram polling stopped.")
```

(Verified via direct `view`/`grep` of the file at
`src/services/telegram_service.py:223-240`, not copy-pasted from any
prior report.)

`start()` (lines 117-145), `stop()` (lines 147-160), `status()` (lines
162-172), `doctor()` (lines 174-185), `send_message()` (lines
187-207), and `_poll_once()` (lines 242-258) were each independently
read in full. All match the pre-EP-067 baseline exactly (Section 13).

## 4. D1–D10 Compliance

**D1 — Guard wraps only `self._poll_once()`.** **PASS.** Confirmed by
direct reading: the `try:` block (line 236) contains exactly one
statement, `self._poll_once()` (line 237). `_stop_event.wait(interval)`
sits in the `while` condition (line 235), textually and structurally
outside the `try`. No other statement is inside the guard.

**D2 — Existing `_poll_once()` `TelegramClientError` handling
unchanged.** **PASS.** A line-level diff of `_poll_once()` against the
untouched baseline (`diff -u` against the original, unmodified archive
extraction) shows zero changes to `_poll_once()` — the diff hunk
produced by the entire EP-067 change touches only `_poll_loop()`'s
docstring and body; `_poll_once()` does not appear in the diff at all
(Section 13).

**D3 — Broad `except Exception` is used.** **PASS.** Line 238 reads
`except Exception as exc:  # noqa: BLE001 - the poll loop must never
die silently`, textually identical in shape and comment wording to
`SchedulerService._tick_loop()` (`src/services/scheduler_service.py:344`),
`WorkflowSchedulerService._tick_loop()`
(`src/services/workflow_scheduler_service.py:330`), and
`MemoryPersistence._auto_save_loop()`
(`src/core/memory/memory_persistence.py:260`), each independently
re-read for this audit (Section 15).

**D4 — Distinct error message and exception reason only; no raw
Telegram payload.** **PASS.** Line 239:
`logger.error(f"Telegram poll loop encountered an unexpected error:
{exc}")` — distinct from `_poll_once()`'s own pre-existing `f"Telegram
polling failed: {exc}"` (line 250) and `f"Telegram outgoing message
failed: {exc}"` (line 258). Only `str(exc)` (via f-string interpolation)
is included; no chat id, message text, username, or token variable is
referenced anywhere in the new line. Independently confirmed at
runtime by audit Probe A (Section 6) and by a dedicated
sensitive-data-leakage probe using a distinctive marker string that
never appeared in captured logs (Section 8).

**D5 — Loop continues after failure; no restart or backoff.**
**PASS.** After the `except` block, control falls through to the
bottom of the `while` body (line 240's `logger.info` is only reached
after the loop exits) and the loop re-evaluates
`self._stop_event.wait(interval)` on its next pass — no `continue`,
`break`, `time.sleep`, retry counter, or new thread is present.
Independently confirmed at runtime: audit Probe C (Section 6) measured
inter-attempt gaps of ~0.100–0.101s against a configured
`polling_interval` of `0.1`, for four consecutive failures — consistent
spacing, no acceleration, no backoff growth.

**D6 — `start()` and `stop()` remain unchanged.** **PASS.** Confirmed
via the same full-file diff (Section 13): the diff hunk contains no
changes outside `_poll_loop()`. `start()`/`stop()` are byte-identical
to the pre-EP-067 baseline.

**D7 — No new public API or status field.** **PASS.** `TelegramStatus`,
`TelegramDoctorReport`, `status()`, and `doctor()` are unchanged
(confirmed by the same diff). No new method was added to
`TelegramService`; `_poll_loop()`'s signature (`() -> None`) is
unchanged.

**D8 — Exactly two production files changed.** **PASS.** Full-tree
diff against the untouched baseline (Section 13) shows exactly
`src/services/telegram_service.py` and `src/modules/test_module.py`
as modified production files, plus the new `docs/architecture/designs/
EP067_DESIGN.md` (STEP 1, pre-existing before this STEP) and the new
`tests/EP067/` directory (STEP 2). No other production file differs.

**D9 — Dedicated, self-contained `tests/EP067/` package.** **PASS.**
`tests/EP067/__init__.py` exists and is empty (0 lines), matching the
`tests/EP061/`–`tests/EP066/` convention. `tests/EP067/
test_telegram_poll_loop_resilience.py` declares `NAME = "EP067"` and
registers via `@TestRegistry.register`. A repository-wide grep of the
test file for `tests\.EP0[1-6]` returns zero matches — no cross-EP
import (Section 9).

**D10 — Previously deferred items remain untouched.** **PASS.**
`docs/architecture/ARCHITECTURE_DEBT.md`, `CHANGELOG.md`,
`docs/RELEASE_NOTES.md`, `docs/BACKLOG.md`, and
`docs/architecture/JARVIS_ROADMAP.md` are all absent from the
full-tree diff (Section 13) — none were touched. `TelegramService`'s
`start()`/`stop()` (shutdown coordination is unrelated to this EP,
Section 15 of the design) are unchanged; `src/core/api/*` (REST auth),
`src/core/plugins/plugin_loader.py` (PluginLoader TODO), and
`Scheduler.calculate_next_run()`/`WorkflowSchedulerEngine` (cron) were
all independently spot-checked and are absent from the diff.

**Summary: 10/10 PASS. No PARTIAL or FAIL.**

## 5. Critical Exception-Boundary Verification

Per the audit brief's Section 3, this is the single most important
check. Direct reading of lines 235-239 confirms the `try`/`except`
protects **only** the call to `self._poll_once()` on line 237.
Specifically confirmed **not** encompassed by the guard:

- `self._stop_event.wait(interval)` — evaluated as the `while`
  condition on line 235, syntactically outside the `try` block that
  begins on line 236.
- `logger.info("Telegram polling stopped.")` — line 240, outside the
  `while` loop entirely; reached only after the loop exits via
  `_stop_event` being set, never as a side effect of the new
  `except` block.
- Thread-lifecycle logic (`threading.Thread(...)`, `.start()`,
  `.join()`) — all located in `start()`/`stop()`, methods entirely
  separate from `_poll_loop()`'s body and untouched by this EP
  (Section 4, D6).
- `self._lifecycle_lock` acquisition/release — occurs only inside
  `start()`/`stop()`, never inside `_poll_loop()`.

The six-point behavioral chain the audit brief specifies was
independently verified end-to-end via runtime probes, not inferred
from source alone (Section 6): (1) caught — confirmed; (2) logged —
confirmed, with the correct message and exception text; (3) does not
terminate the thread — confirmed via `_is_poll_loop_running()`/
`status().running` remaining `True`; (4) loop continues — confirmed
via a second `fetch_updates()` call being observed; (5) a subsequent
`_poll_once()` call succeeds — confirmed via Probe B; (6) normal
shutdown eventually still succeeds — confirmed via Probe D.

## 6. Runtime Verification (Independent Probes)

Five fresh, audit-authored probes were written and executed
independently of `tests/EP067/`'s own fixtures (a separate fake
`TelegramClient`, separate `Config`/router construction, no reuse of
any helper from the checked-in suite). Full probe source and raw
output are reproduced in Section 18.

**Probe A — Single unexpected failure (`KeyError`).**
Result: `fetch_updates()` was called; the loop was still alive ~50ms
after the failure; the log capture contains
`"Telegram poll loop encountered an unexpected error:
'audit-injected unexpected failure'"`; a second `fetch_updates()` call
was subsequently observed, confirming genuine continuation, not merely
a thread object that hadn't yet crashed. **Confirmed as designed.**

**Probe B — Recovery.** First `fetch_updates()` raised `RuntimeError`;
second call returned one message. Result: `send_message()` was
observed to fire with the routed reply
(`"Unknown module: hi\nType \"system help\" for available
commands."`), proving the second, successful poll cycle was actually
executed end-to-end (fetch → route → dispatch → send), not merely that
`fetch_updates()` was called again. **Confirmed as designed.**

**Probe C — Repeated failures / no busy loop.** Five consecutive
`ValueError` raises against a `polling_interval` of `0.1`. Result: all
five attempts occurred; the thread was alive afterward; inter-attempt
gaps measured `[0.1004, 0.1005, 0.1004, 0.1005]` seconds — consistent
with the configured interval, no acceleration, no busy-loop signature.
**Confirmed as designed.**

**Probe D — Shutdown after a survived exception.** One `OSError`
raised, then `stop()` called. Result: `stop()` returned success in
`0.0003s` (well inside its `timeout=5` join bound);
`_is_poll_loop_running()` was `False` immediately after. No exception
from the `stop()` call path was observed, confirming the new handler
does not interfere with shutdown. **Confirmed as designed.**

**Probe E — Existing `TelegramClientError` path unchanged.** A
`TelegramClientError` raised from `fetch_updates()`. Result: the
pre-existing `"Telegram polling failed: audit simulated bot api
failure"` message fired (from `_poll_once()`'s own, unmodified guard);
the **new** `"Telegram poll loop encountered an unexpected error"`
message did **not** fire for this call; the thread remained alive.
This confirms the two guards are correctly layered — `_poll_once()`'s
narrower, pre-existing guard still takes full effect for
`TelegramClientError`, and the new, broader guard in `_poll_loop()`
never double-handles or re-logs an exception `_poll_once()` already
converted into a return. **Confirmed as designed.**

All five probes' raw `loguru` output was captured and inspected
directly; none showed the new handler firing where it should not, and
none showed the new handler failing to fire where it should.

## 7. Test Verification

`tests/EP067/test_telegram_poll_loop_resilience.py` was read in full
and audited method-by-method against the criteria in the audit brief's
Section 7:

| Test | Behavior tested | Can fail if impl. wrong? | Deterministic? | Cleans up? |
|---|---|---|---|---|
| `_test_normal_polling_still_occurs` | Baseline routing still works | Yes — asserts module was actually called | Yes (bounded wait) | Yes (`finally: stop()`) |
| `_test_unexpected_exception_from_fetch_does_not_escape_the_thread` | Thread survives a generic exception from `fetch_updates()` | Yes — would fail if the guard were removed or narrowed | Yes | Yes |
| `_test_unexpected_exception_from_routing_does_not_escape_the_thread` | Thread survives a generic exception from `route()`, proving the boundary is not limited to the client | Yes | Yes | Yes |
| `_test_loop_recovers_and_polls_after_one_failure` | A later, real poll cycle actually executes after a failure | Yes — checks `module.calls`, not just call counts | Yes | Yes |
| `_test_repeated_unexpected_failures_do_not_kill_the_loop` | Survives 4 consecutive failures | Yes | Yes | Yes |
| `_test_unexpected_failure_is_logged_at_error_level` | New message + exception text appear in real log output | Yes — real `loguru` sink, not a mock | Yes | Yes (`finally: stop(); logger.remove(sink_id)`) |
| `_test_no_sensitive_data_leaks_into_the_new_log_message` | A distinctive marker present in the routed message text never reaches the log via the new handler | Yes — meaningful negative assertion | Yes | Yes |
| `_test_existing_telegramclienterror_handling_is_unchanged` | Old message still fires; new handler does *not* also fire for the same event | Yes — this is the regression test for D2/D3 layering | Yes | Yes |
| `_test_stop_still_terminates_cleanly_after_a_survived_exception` | `stop()` still succeeds and joins promptly | Yes — bounds `stop_duration < 5.5` | Yes | Self-cleaning (is the stop call) |
| `_test_no_busy_loop_after_a_failure` | Inter-attempt spacing after failures | Yes — would fail on a busy loop or on a broken `wait()` | Yes | Yes |

All 33 assertions (`self.assert_true`/`self.assert_false` calls,
counted directly via `grep -c` against the file) map 1:1 to the 33
passed results reported by `TestResult` — there is no discrepancy
between claimed and actual assertion count.

Every test uses a real `TelegramService`, a real `TelegramRouter`
(except the two tests deliberately substituting a duck-typed router to
prove containment beyond the client boundary), and a real
`CommandRouter` with one recording stub module — faking only the one
genuine I/O boundary (`TelegramClient`), consistent with this
repository's own established preference (already praised in EP-065's
own audit) for real objects over tautological mocks. No test makes a
real network call; no token or credential is used (`"fake-token-not-
used-by-fake-client"`/`"audit-fake-token"` placeholders throughout).

**No coverage gaps that would block acceptance were found.** Two
minor, non-blocking observations are recorded as findings in Section
11.

## 8. Test Self-Containment

- `tests/EP067/__init__.py` exists, 0 lines (confirmed via `wc -l`).
- `NAME = "EP067"` confirmed present (line 192).
- `grep -n "tests\.EP0[1-6]"` against the test file returns **zero**
  matches — no cross-EP import of any kind.
- Exactly one new import line,
  `import tests.EP067.test_telegram_poll_loop_resilience`, appears in
  `src/modules/test_module.py`, appended immediately after the
  pre-existing `import tests.EP066.test_memory_persistence_auto_save_resilience`
  line — confirmed via direct `diff` (Section 13), not by assumption.

## 9. Owner Decisions Audit

See Section 4 (D1–D10), each independently marked **PASS** with
concrete, source-level and/or runtime evidence. No PARTIAL or FAIL
determinations.

## 10. Regression Validation

Independently re-run (not copied from the STEP 2 report) via direct
`TestRunner`/`TestRegistry` invocation:

| Suite | Passed | Failed | Skipped |
|---|---|---|---|
| EP067 | 33 | 0 | 0 |
| EP061 | 62 | 0 | 0 |
| EP062 | 39 | 0 | 0 |
| EP063 | 78 | 0 | 0 |
| EP064 | 93 | 0 | 0 |
| EP065 | 42 | 0 | 0 |
| EP066 | 23 | 0 | 0 |

All figures match the STEP 2 report and this repository's established
per-suite baselines exactly.

**Full suite (independent run):** 53 suites completed, **6,973
passed / 3 failed / 1 skipped.** `EP046` and `EP048` still cannot
execute in this sandbox (`AudioCaptureError`/`StreamingAudioCaptureError`:
`sounddevice`/PortAudio unusable; `openwakeword` has no installable
distribution for this Python/platform) — both pre-existing,
environmental, unrelated to `TelegramService`. `EP047` shows 2
failures (STT-availability-despite-TTS-construction-failure assertions)
and `EP049` shows 1 failure + 1 skip — both pre-existing per this
repository's own prior EP-065/EP-066 audits.

**Independent baseline comparison performed fresh for this audit:**
the same full suite was re-run, under the same installed package set,
against the untouched pre-EP-067 archive (a separate, unmodified
extraction of the original upload). Result: **52 suites, 6,940
passed / 3 failed / 1 skipped**, with the identical two crashed suites
(`EP046`, `EP048`) and the identical two failing suites (`EP047`,
`EP049`), byte-for-byte the same failure messages. `6,973 − 6,940 =
33`, exactly the size of the new `tests/EP067/` suite.
**Zero regressions independently confirmed.**

## 11. Protected-File Verification

A full-tree `diff -rq` (excluding regenerated `__pycache__` bytecode,
which is not source and differs only by compilation timestamp/hash)
between the untouched baseline archive and the current working tree
was run fresh for this audit and shows exactly:

```
Only in <working>/docs/architecture/designs: EP067_DESIGN.md
Files <baseline>/src/modules/test_module.py and <working>/src/modules/test_module.py differ
Files <baseline>/src/services/telegram_service.py and <working>/src/services/telegram_service.py differ
Only in <working>/tests: EP067
```

Nothing else differs. In particular, independently confirmed
unchanged (present in the baseline, absent from the diff output
above): every `tests/EP061/`–`tests/EP066/` file; `src/services/
scheduler_service.py`; `src/services/workflow_scheduler_service.py`;
`src/core/memory/memory_persistence.py`; `src/core/telegram/
telegram_client.py`; `src/core/telegram/telegram_router.py`;
`src/modules/telegram_module.py`; `src/core/command_router.py`;
`src/bootstrap.py`; `src/main.py`; `config/config.yaml`;
`docs/BACKLOG.md`; `CHANGELOG.md`; `docs/RELEASE_NOTES.md`;
`docs/architecture/JARVIS_ROADMAP.md`;
`docs/architecture/ARCHITECTURE_DEBT.md`; and every EP-001–EP-066
design and audit document.

(Note: the audit brief refers to `src/services/telegram_client.py`
and `src/services/telegram_router.py`; the actual repository paths are
`src/core/telegram/telegram_client.py` and
`src/core/telegram/telegram_router.py`. Both were checked at their
real locations and confirmed unchanged — see Section 16, Finding
EP067-N1.)

## 12. Comparison Against the Sibling Architectural Pattern

Direct, independent re-reading of all three sibling loops:

```python
# SchedulerService._tick_loop()  (src/services/scheduler_service.py:339-347)
def _tick_loop(self) -> None:
    interval = float(self._config.get("scheduler.tick_interval", 1))
    while not self._stop_event.wait(interval):
        try:
            self._scheduler.tick()
        except Exception as exc:  # noqa: BLE001 - the tick loop must never die silently
            logger.error(f"Scheduler tick failed: {exc}")
    logger.info("Scheduler stopped.")
```

```python
# WorkflowSchedulerService._tick_loop()  (src/services/workflow_scheduler_service.py:325-333)
def _tick_loop(self) -> None:
    interval = float(self._config.get("workflow_scheduler.tick_interval", 5))
    while not self._stop_event.wait(interval):
        try:
            self._engine.tick()
        except Exception as exc:  # noqa: BLE001 - the tick loop must never die silently
            logger.error(f"Workflow Scheduler tick failed: {exc}")
    logger.info("Workflow Scheduler stopped.")
```

```python
# MemoryPersistence._auto_save_loop()  (src/core/memory/memory_persistence.py:254-267)
def _auto_save_loop(self) -> None:
    interval = self.auto_save_interval()
    while not self._stop_event.wait(interval):
        try:
            success, message = self.save()
        except Exception as exc:  # noqa: BLE001 - the auto-save loop must never die silently
            logger.error(f"Memory auto-save loop encountered an unexpected error: {exc}")
            continue
        if not success:
            logger.error(f"Memory auto-save failed: {message}")
    logger.info("Memory auto-save stopped.")
```

`TelegramService._poll_loop()`'s new shape matches
`SchedulerService`/`WorkflowSchedulerService` most closely (single
guarded call, no follow-up statement inside the loop body, hence no
`continue` needed — correctly distinguished from `MemoryPersistence`,
which does need a `continue` because of its trailing `if not success:`
check). Evaluated explicitly against the audit brief's four criteria:

- **Narrowly scoped:** Yes — wraps only the one per-iteration call,
  identical placement to all three siblings (Section 5).
- **Logged:** Yes — `logger.error(...)`, same severity and channel as
  all three siblings.
- **Non-fatal to the background loop:** Yes — confirmed by Probes A/C
  (Section 6); the loop demonstrably continues.
- **Free of unintended lifecycle changes:** Yes — `start()`/`stop()`
  unchanged (D6); no new thread, no restart, no backoff (D5).

No architectural divergence from the sibling pattern was found. The
one cosmetic difference — the new `except` block has no `continue`
statement, unlike `MemoryPersistence`'s — is correct and intentional,
not a divergence: `_poll_loop()`'s guarded call is the only statement
in its loop body, so there is nothing to skip past, exactly matching
`SchedulerService`/`WorkflowSchedulerService`'s own simpler shape.

## 13. Verification Evidence — Full-File Diff

```diff
--- <baseline>/src/services/telegram_service.py
+++ <working>/src/services/telegram_service.py
@@ -221,10 +221,22 @@
         return CommandResult(success=False, message="Telegram disabled.")

     def _poll_loop(self) -> None:
-        """Repeatedly poll for and route messages every 'telegram.polling_interval' seconds."""
+        """Repeatedly poll for and route messages every 'telegram.polling_interval' seconds.
+
+        Mirrors SchedulerService._tick_loop() / WorkflowSchedulerService
+        ._tick_loop() / MemoryPersistence._auto_save_loop() (EP-061/
+        EP-063/EP-066): any exception raised while executing
+        _poll_once() -- beyond the narrower TelegramClientError cases
+        _poll_once() already converts into a logged, swallowed failure --
+        is caught, logged, and the loop continues rather than the
+        "telegram-poll" thread dying silently (EP-067).
+        """
         interval = float(self._config.get("telegram.polling_interval", 2))
         while not self._stop_event.wait(interval):
-            self._poll_once()
+            try:
+                self._poll_once()
+            except Exception as exc:  # noqa: BLE001 - the poll loop must never die silently
+                logger.error(f"Telegram poll loop encountered an unexpected error: {exc}")
         logger.info("Telegram polling stopped.")

     def _poll_once(self) -> None:
```

```diff
--- <baseline>/src/modules/test_module.py
+++ <working>/src/modules/test_module.py
@@ -65,6 +65,7 @@
 import tests.EP064.test_memory_persistence_shutdown
 import tests.EP065.test_command_router_malformed_input
 import tests.EP066.test_memory_persistence_auto_save_resilience
+import tests.EP067.test_telegram_poll_loop_resilience

 class TestModule(CommandModule):
```

These are the complete, entire diffs of both modified production
files — no other hunk exists in either file.

## 14. Findings

**EP067-N1 (NOTE, non-blocking).** The STEP 3 audit brief itself names
protected paths as `src/services/telegram_client.py` and
`src/services/telegram_router.py`; the actual files live at
`src/core/telegram/telegram_client.py` and
`src/core/telegram/telegram_router.py` (matching the design document's
own, correct paths throughout). Both were located and confirmed
unchanged at their real paths. Documentation/brief-wording
discrepancy only; no code or process defect.

**EP067-L1 (LOW).** `tests/EP067/test_telegram_poll_loop_resilience.py`
imports `threading` at module level but never references it (`grep -n
"threading\." <file>` returns zero matches — the module only uses
`time`, `tempfile`, and `pathlib.Path` for its actual mechanics; the
real thread being exercised is `TelegramService`'s own internal
`"telegram-poll"` thread, not one created directly by the test file).
Dead import; no functional effect, does not weaken any assertion.

**EP067-L2 (LOW).** Several tests (e.g.
`_test_normal_polling_still_occurs`,
`_test_unexpected_exception_from_fetch_does_not_escape_the_thread`)
call the private method `service._is_poll_loop_running()` directly
(annotated `# noqa: SLF001`) rather than the equivalent, already-public
`service.status().running` (confirmed structurally equivalent by
direct reading of `status()`, line 169:
`running=self._is_poll_loop_running()`). `tests/EP066/`'s own
equivalent resilience suite consistently used `MemoryPersistence`'s
public `is_running()` method rather than reaching into a private
member for the same check. Purely a minor style/consistency deviation
from the established sibling test convention; the private and public
accessors are provably equivalent today, so this does not affect
correctness, test validity, or the ability of any test to catch a
regression.

No BLOCKER, HIGH, or MEDIUM findings were identified.

## 15. Final Verdict

### PASS WITH NON-BLOCKING FINDINGS

Rationale: all ten Owner Decisions (D1–D10) are independently
confirmed compliant with concrete source-level evidence; the critical
exception boundary is exactly and only around `self._poll_once()`,
confirmed both statically and via five independently-authored runtime
probes covering the full failure → survive → recover → repeated-
failure → shutdown chain, plus explicit confirmation that the
pre-existing `TelegramClientError` path is untouched and does not
double-fire against the new handler; `_poll_once()`, `start()`,
`stop()`, `TelegramClient`, and `TelegramRouter` are all confirmed
byte-identical to the pre-EP-067 baseline via direct diff; the new
`tests/EP067/` suite is genuinely behavior-driven, self-contained, and
its 33 assertions were independently reproduced (33/0/0); every
regression suite (EP061–EP066) reproduces its own established
baseline exactly; the full-suite comparison against a freshly-run,
untouched-baseline execution shows a difference of precisely 33 tests
and zero regressions; and the complete repository diff shows exactly
the four files/directories STEP 1/STEP 2 were authorized to touch,
nothing more. Only two LOW findings and one NOTE exist — a dead
import, a minor private-vs-public accessor style deviation from a
sibling suite's convention, and a path-naming discrepancy in the audit
brief itself — none of which represent a correctness, safety, scope,
or architectural defect. None blocks release.

## 16. Verification Command Reference

For reproducibility, the principal commands used during this audit:

```bash
# Independent full-file diff of both modified production files
diff -u <baseline>/src/services/telegram_service.py <working>/src/services/telegram_service.py
diff -u <baseline>/src/modules/test_module.py <working>/src/modules/test_module.py

# Independent full-tree diff (excluding regenerated bytecode)
diff -rq -x "__pycache__" <baseline> <working>

# Independent dedicated + regression suite runs
python3 -c "
import src.modules.test_module
from src.testing.runner import TestRunner
runner = TestRunner()
for name in ['EP067','EP061','EP062','EP063','EP064','EP065','EP066']:
    print(name, runner.run(name))
"

# Independent full-suite run (both trees, for side-by-side comparison)
python3 -c "
import src.modules.test_module
from src.testing.registry import TestRegistry
import time
results, crashed = [], []
for suite_class in TestRegistry.all():
    try:
        r = suite_class(); started = time.perf_counter()
        result = r.run(); result.duration = time.perf_counter() - started
        results.append(result)
    except Exception as exc:
        crashed.append((suite_class.NAME, repr(exc)))
print(len(results), sum(r.passed for r in results), sum(r.failed for r in results), sum(r.skipped for r in results))
print(crashed)
"

# Dead-import / cross-EP-import checks
grep -n "threading\." tests/EP067/test_telegram_poll_loop_resilience.py
grep -n "tests\.EP0[1-6]" tests/EP067/test_telegram_poll_loop_resilience.py

# Thread-leak check
python3 -c "
import threading, src.modules.test_module
from src.testing.runner import TestRunner
before = set(t.name for t in threading.enumerate())
TestRunner().run('EP067')
print(set(t.name for t in threading.enumerate()) - before)
"
```

Five audit-authored runtime probes (Probes A–E, Section 6) were
executed as a standalone script independent of `tests/EP067/`'s own
fixtures; their full source and captured output are preserved in this
audit's working notes and summarized in Section 6.
