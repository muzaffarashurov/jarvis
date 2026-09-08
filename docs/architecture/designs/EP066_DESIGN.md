# EP-066 — MemoryPersistence Auto-Save Loop Exception Containment

STEP 1: Architecture Discovery & Design

Status: DESIGN PROPOSED — awaiting Owner Decision approval before STEP 2

---

## 1. Title

EP-066 — MemoryPersistence Auto-Save Loop Exception Containment

## 2. Status

STEP 1 complete (this document). STEP 2 (Implementation & Testing),
STEP 3 (Architecture Audit), and STEP 4 (Documentation Synchronization)
have not started.

## 3. Problem Statement

`MemoryPersistence._auto_save_loop()` (`src/core/memory/memory_persistence.py`)
is the only background tick/poll loop in this repository whose
per-iteration work is not wrapped in a broad exception guard. If
`self.save()` raises anything other than `OSError` — which is the only
exception type `save()` itself catches — the exception propagates out
of `_auto_save_loop()` uncaught, killing the `"memory-auto-save"`
daemon thread permanently, silently, with **no log line at all**
(the loop's own closing `logger.info("Memory auto-save stopped.")`
never runs, because the exception unwinds past it). `MemoryPersistence`
has no supervisor and no restart mechanism, so auto-save is gone for
the remainder of the process's life, with nothing in the logs to
explain why.

Every structurally equivalent background loop in this codebase
already guards against exactly this: `SchedulerService._tick_loop()`
(EP-061) and `WorkflowSchedulerService._tick_loop()` (EP-063) each
wrap their per-iteration call in `except Exception as exc: logger.error(...)`
and keep looping; `TelegramService._poll_once()` (pre-existing, audited
unchanged by EP-065) wraps its network call in
`except TelegramClientError` for the same self-healing purpose.
`MemoryPersistence._auto_save_loop()` is the outlier.

This is not a new observation. It was raised and explicitly deferred
twice already:

- **EP-064 STEP 3 Finding F1** (`docs/architecture/audits/EP064_ARCHITECTURE_AUDIT.md`):
  *"`MemoryPersistence._auto_save_loop()` lacks the broad exception
  guard `SchedulerService._tick_loop()` has — a pre-existing asymmetry,
  not introduced by EP-064, correctly left alone per Owner Decision
  D6."*
- **EP-064 Owner Decision D6** (`docs/architecture/designs/EP064_DESIGN.md`)
  deliberately scoped EP-064 to adding `shutdown()` only, rejecting any
  adjacent improvement to `_auto_save_loop()`'s error handling as
  out-of-scope, "not a rider on this one," recommending it get "its
  own STEP 1 discovery and Owner Decision."
- **EP-065 Owner Decision D9** re-confirmed, by direct diff against
  the untouched baseline, that `src/core/memory/memory_persistence.py`
  (specifically "EP064-F1") remained byte-identical and untouched
  through EP-065 as well.

EP-066 is that dedicated follow-up.

## 4. Current Architecture / Behavior

`MemoryPersistence` (`src/core/memory/memory_persistence.py`, 330
lines) owns:

- `load()` — reads the storage file at startup; a missing/invalid file
  is logged and skipped, not raised.
- `save()` — writes every persistent `MemoryEntry` (via
  `MemoryStore.export_snapshot()`) to the storage file as JSON.
  Wrapped in `try: ... except OSError as exc: logger.error(...); return
  False, message`. Any exception that is not an `OSError` — e.g. a
  `TypeError`/`ValueError` from `json.dump()` encountering a
  non-JSON-serializable or unencodable value inside a snapshot entry,
  or any exception raised inside `MemoryStore.export_snapshot()` itself
  — is **not** caught here and propagates to the caller.
- `_start_auto_save_loop()` — starts a daemon thread named
  `"memory-auto-save"` running `_auto_save_loop()`.
- `_auto_save_loop()` (lines 254-261):

  ```python
  def _auto_save_loop(self) -> None:
      """Repeatedly call save() every 'memory.auto_save_interval' seconds."""
      interval = self.auto_save_interval()
      while not self._stop_event.wait(interval):
          success, message = self.save()
          if not success:
              logger.error(f"Memory auto-save failed: {message}")
      logger.info("Memory auto-save stopped.")
  ```

  There is no `try`/`except` around the `self.save()` call itself.
  `save()`'s internal `(success, message)` return contract only
  covers the `OSError` case; any other exception raised by `save()`
  is not converted into that contract and is not caught here either.

- `shutdown(wait=True, timeout=None) -> bool` (EP-064) — the public,
  idempotent way to *deliberately* stop the loop, using
  `_stop_event.set()` plus `thread.join()`. This is unrelated to, and
  unaffected by, the gap above: `shutdown()` handles a clean,
  intentional stop; the gap concerns an *unintentional* death from an
  uncaught exception mid-loop.

Sibling background loops, for contrast (both confirmed by direct
reading during this STEP 1, both unchanged by any later EP):

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

Both comments say, verbatim, *"the tick loop must never die silently"*
— stating exactly the property `_auto_save_loop()` currently lacks.

Observability once the thread has died: `MemoryPersistence.is_running()`
and `MemoryStatus.auto_save_running` (EP-064) both report the thread's
actual `is_alive()` state, so `memory status`/`memory doctor` would
eventually show `auto_save_running: False` if queried — but nothing
proactively surfaces *why* it stopped, and nothing restarts it. An
operator who never happens to run `memory status` has no signal at
all.

## 5. Discovery Findings

Discovery was performed by reading, in order: `docs/BACKLOG.md`,
`docs/architecture/JARVIS_ROADMAP.md`, `CHANGELOG.md`,
`docs/RELEASE_NOTES.md`, `docs/architecture/designs/EP065_DESIGN.md`,
`docs/architecture/audits/EP065_ARCHITECTURE_AUDIT.md`, and the
EP-061 through EP-064 designs/audits, followed by a repository-wide
search for TODO/FIXME markers, re-reading
`docs/architecture/ARCHITECTURE_DEBT.md` in full, and direct
inspection of the background-loop implementations in
`src/services/scheduler_service.py`,
`src/services/workflow_scheduler_service.py`,
`src/services/telegram_service.py`, and
`src/core/memory/memory_persistence.py`.

Candidates considered (full comparison in Section 7):

1. **`MemoryPersistence._auto_save_loop()` exception containment**
   (EP-064 Finding F1, deferred by D6, re-confirmed untouched by
   EP-065 D9) — selected.
2. `GitService.show(ref)` missing `--` argument separator (Architecture
   Debt AD-009) — rejected, Architecture Debt item.
3. `WorkflowSchedulerService`/`Bootstrap` malformed
   `workflow_scheduler.tick_interval` handling (Architecture Debt
   AD-001, `Bootstrap`'s unreachable `WorkflowSchedulerError` handler,
   AD-002) — rejected, Architecture Debt items.
4. Telegram Gateway shutdown coordination — rejected, the same
   candidate independently investigated and rejected by EP-063,
   EP-064, and EP-065 in turn, for the same two reasons each time.
5. REST API authentication — rejected, real but architecturally large,
   independently identified and deferred by EP-064 and EP-065 for the
   same reason.
6. `PluginLoader`'s metadata-only-plugin status bookkeeping not
   cross-checked against `ProcessService`/`InvoiceService`/
   `FastResponseService` (explicit TODO in `plugin_loader.py`) —
   rejected, requires a constructor-injection change spanning multiple
   services, larger than a single bounded EP.
7. Cron schedule support (`Scheduler.calculate_next_run`,
   `WorkflowSchedulerEngine`'s `ScheduleType.CRON` branch) — rejected,
   a net-new feature (a cron expression parser), not an architecture
   fix, and explicitly out of scope since EP-011.

`docs/architecture/ARCHITECTURE_DEBT.md` was re-read in full. Its own
governing rule — *"Never fix Architecture Debt during a normal
Engineering Phase (EP)... Architecture Debt is addressed only during a
dedicated cleanup milestone"* — categorically excludes every open
AD-item (AD-001, AD-002, AD-003, AD-006, AD-007, AD-008, AD-009) from
EP-066 regardless of individual merit, consistent with EP-065's own
Section-0 discovery, which rejected "every Architecture Debt item" on
this same basis. This STEP 1 independently re-confirms that exclusion
rather than assuming it. Separately, AD-005 ("no process-exit shutdown
wiring calls `BackgroundWorkerService.shutdown()`") was independently
verified, by reading `RuntimeService.shutdown()` in full, to already be
resolved in current code (`RuntimeService.shutdown()`'s docstring and
body confirm the Background Worker Service is the fifth of five
services stopped, wired in by EP-060/061/063/064) — `ARCHITECTURE_DEBT.md`
itself was not updated to reflect this, but that is a documentation
staleness observation, not a code defect, and out of scope for this
STEP 1 (see Non-Goals).

## 6. Selected Candidate

**`MemoryPersistence._auto_save_loop()` Exception Containment.**

`self.save()` inside `_auto_save_loop()` will be wrapped in its own
`try`/`except Exception` block, structurally identical in shape,
placement, and log wording style to `SchedulerService._tick_loop()`
and `WorkflowSchedulerService._tick_loop()`: on any exception not
already converted into `save()`'s own `(False, message)` contract, log
it via `logger.error(...)` and continue the loop rather than letting
the thread die. This is purely additive to `_auto_save_loop()`'s error
handling; `save()` itself, `load()`, `shutdown()`, `_start_auto_save_loop()`,
and every other method are untouched.

- **Current implementation:** see Section 4.
- **Exact problem:** an exception raised by `self.save()` that is not
  an `OSError` (e.g. a `TypeError`/`ValueError`/`UnicodeEncodeError`
  from `json.dump()`, or any exception from
  `MemoryStore.export_snapshot()`) is uncaught inside
  `_auto_save_loop()` and permanently, silently kills the auto-save
  thread.
- **Affected files/modules:** `src/core/memory/memory_persistence.py`
  (one method, `_auto_save_loop()`) only.
- **Why it matters:** `memory.auto_save` defaults `true`, so this
  affects every default installation with persistence on; a silent,
  permanent stop of auto-save (with zero log evidence of why) is a
  worse operator experience than the sibling loops' proven
  self-healing behavior, and directly contradicts this repository's
  own stated invariant ("the tick loop must never die silently") for
  every other background loop of the same shape.
- **Estimated implementation scope:** one new `try`/`except` block, ~5
  lines, no signature change, no new public method, no new dataclass
  field.
- **Expected tests:** see Section 10.
- **Architectural risk:** minimal — the change narrows failure impact
  (an isolated bad save no longer kills the thread) and does not widen
  any existing exception boundary elsewhere; it mirrors an
  already-approved, already-audited pattern used twice before in this
  same codebase.
- **Dependencies on previous/future EPs:** builds directly on EP-064's
  `MemoryPersistence`/`_auto_save_loop()`/`shutdown()` machinery; no
  dependency on EP-065's `CommandRouter` work; no known future EP
  depends on this one.
- **Why suitable for EP-066:** real (not hypothetical — `save()`'s own
  `except OSError` is demonstrably not exhaustive), small, bounded to
  one file, independently testable without touching any other
  subsystem, consistent with existing architecture (copies an
  already-twice-approved pattern verbatim), not cosmetic, and not a
  duplicate of any completed EP (EP-064 added `shutdown()`, a
  *deliberate*-stop primitive; EP-066 addresses an *accidental*-death
  gap in the same loop — different problems, confirmed non-overlapping
  in Section 8).

## 7. Rejected Alternatives

**GitService.show(ref) missing `--` separator (AD-009).** Real,
narrow, single-line fix (`self._run("show", ["show", ref])` →
`self._run("show", ["show", "--", ref])`, matching `diff()`'s own
existing pattern in the same file). Rejected solely because it is a
recorded, open Architecture Debt item, and this repository's own
governance (`ARCHITECTURE_DEBT.md` Rules section) forbids fixing
Architecture Debt during a normal EP — it is reserved for a dedicated
Architecture Cleanup milestone. Not rejected on technical merit.

**AD-001 / AD-002 (`workflow_scheduler.tick_interval` validation;
`Bootstrap`'s unreachable `WorkflowSchedulerError` handler).** Same
reason as AD-009 — both are recorded Architecture Debt, off-limits to
a normal EP by the repository's own rule, independent of their
individual merit. (AD-001 was also independently re-confirmed to still
be present in `WorkflowSchedulerService` during this discovery.)

**Telegram Gateway shutdown coordination.** The same candidate
independently investigated and rejected three EPs running (EP-063,
EP-064, EP-065), each time for the same two reasons: a manual
`telegram stop` escape hatch already exists, and there is zero
pre-existing test coverage to build on safely. Nothing in the
repository has changed either of those two facts since EP-065; a
fourth independent rejection for the same reasons would add no new
information, so this STEP 1 does not re-litigate it beyond noting the
precedent.

**REST API authentication.** A real, repeatedly disclosed gap (noted
by name in both EP-064's and EP-065's own discovery sections), but
architecturally large — it would touch request handling across every
REST endpoint, credential storage, and configuration, well beyond a
single bounded EP. Consistently deferred by every EP that has
encountered it so far; EP-066 does the same.

**PluginLoader metadata-only-plugin status bookkeeping (`plugin_loader.py`
TODO).** Real gap: `RUNNING`/`STOPPED` bookkeeping for metadata-only
plugins is not cross-checked against the real state
`ProcessService`/`InvoiceService`/`FastResponseService` already track
for the same underlying modules. The plugin_loader.py TODO itself
already explains why: fixing it requires injecting one of those
services into `PluginLoader`/`PluginService`, a constructor-signature
change the original task that added the TODO was not authorized to
make. That same scope problem applies here — it is a multi-service
wiring change, not a single-file, independently bounded fix, so it is
rejected for EP-066 on scope grounds, not on merit.

**Cron schedule support.** `Scheduler.calculate_next_run()` and
`WorkflowSchedulerEngine`'s `ScheduleType.CRON` branch both return
`None`/no-op by design, documented since EP-011 as "interface only, no
cron expression parser exists." Implementing this is a net-new
feature (writing or vendoring a cron parser) rather than a bounded
architectural fix, and is explicitly out of scope for the kind of
small, well-bounded EP this discovery is looking for.

**Why the selected candidate is better than all of the above:** it is
the only candidate that is (a) not recorded Architecture Debt subject
to the repository's own fix-timing rule, (b) not something already
rejected multiple times with unchanged facts, (c) not architecturally
large, (d) not a multi-service wiring change, and (e) not a net-new
feature — while still being a real, verified, currently-uncovered gap
with a precedented, low-risk fix shape already twice-approved in this
same codebase.

## 8. Scope

In scope:

- `src/core/memory/memory_persistence.py`: wrap the `self.save()` call
  inside `_auto_save_loop()` in `try`/`except Exception`, logging via
  `logger.error(...)` and continuing the loop, mirroring
  `SchedulerService._tick_loop()`/`WorkflowSchedulerService._tick_loop()`
  exactly in shape and log-wording convention (a new, distinct message
  identifying the auto-save loop, e.g. `f"Memory auto-save loop
  encountered an unexpected error: {exc}"`, to remain visibly distinct
  from the pre-existing `f"Memory auto-save failed: {message}"` branch
  that already handles `save()`'s own `(False, message)` `OSError`
  contract).
- `tests/EP066/`: a new, dedicated, self-contained test package.
- `src/modules/test_module.py`: exactly one new import line,
  registering `tests.EP066.<module>`, in the established position
  (appended after the existing `tests.EP065...` line).

Out of scope (see Non-Goals): any change to `save()`'s own `OSError`
handling, `load()`, `shutdown()`, `_start_auto_save_loop()`,
`MemoryService`, `MemoryModule`, `RuntimeService`, `MemoryStatus`, or
any file outside `src/core/memory/memory_persistence.py`.

## 9. Non-Goals

- Does **not** change `save()`'s existing `except OSError` contract or
  its `(bool, str)` return shape.
- Does **not** add a restart/auto-recovery mechanism for the auto-save
  thread beyond "keep looping past this exception" (matching
  `SchedulerService`/`WorkflowSchedulerService`'s own behavior exactly
  — neither of those restarts its thread either; they simply don't let
  a single bad tick kill it).
- Does **not** add any new public method, CLI/REST/Telegram action, or
  `MemoryStatus`/`MemoryDoctorReport` field. `auto_save_running`
  (EP-064) already reflects `is_alive()` correctly for both the
  "stopped cleanly via `shutdown()`" and "would have died, now
  doesn't" cases — no new field is needed to observe this fix's effect.
- Does **not** touch `MemoryPersistence.shutdown()` (EP-064) in any
  way — that method handles a deliberate stop and is structurally
  unrelated to an accidental-death exception path.
- Does **not** address any Architecture Debt item (AD-001 through
  AD-009), Telegram Gateway shutdown, REST API authentication, the
  PluginLoader status-sync TODO, or cron support — all remain
  explicitly deferred, unchanged (Section 7).
- Does **not** modify `docs/architecture/ARCHITECTURE_DEBT.md`'s stale
  AD-005 entry — noted as a documentation observation in Section 5,
  but correcting it is a documentation-only change, explicitly
  disallowed as a normal-EP deliverable (criterion 9) and unrelated to
  this EP's own file scope.
- Does **not** modify `tests/EP064/test_memory_persistence_shutdown.py`
  or any other historical EP's test file.

## 10. Proposed Design

`_auto_save_loop()` becomes:

```python
def _auto_save_loop(self) -> None:
    """Repeatedly call save() every 'memory.auto_save_interval' seconds.

    Mirrors SchedulerService._tick_loop() / WorkflowSchedulerService
    ._tick_loop() (EP-061/EP-063): any exception raised by save()
    itself -- as opposed to save()'s own internal (False, message)
    OSError contract, handled below exactly as before -- is caught,
    logged, and the loop continues rather than the thread dying
    silently (EP-066).
    """
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

Design notes:

- The pre-existing `if not success: logger.error(...)` branch (the
  `OSError`-via-`save()`'s-own-contract path) is completely unchanged
  — same condition, same message, same placement relative to the loop.
- The new `except Exception` block sits around the `self.save()` call
  only, exactly mirroring where `SchedulerService`/`WorkflowSchedulerService`
  place their own guard around their own single per-iteration call.
- `continue` is used (rather than falling through) so an exception
  path never accidentally reaches the `if not success` branch with an
  undefined `success`/`message` pair.
- The new log message is deliberately worded differently
  ("...loop encountered an unexpected error...") from the existing
  "Memory auto-save failed: {message}" so the two paths remain
  distinguishable in logs (mirrors EP-065 Owner Decision D3's own
  reasoning for keeping new/old messages textually distinct).
- No raw `MemoryEntry` value is included in the new log message — only
  `str(exc)`, matching this repository's existing convention (EP-065
  Owner Decision D4 applied the same principle to `CommandRouter`;
  `SchedulerService`/`WorkflowSchedulerService`'s own equivalent
  messages likewise log only `str(exc)`, never task/job payloads).

## 11. Owner Decisions

**D1 — Where does the guard live?**
The `try`/`except Exception` wraps only the `self.save()` call inside
`_auto_save_loop()`, matching `SchedulerService._tick_loop()`'s and
`WorkflowSchedulerService._tick_loop()`'s own placement exactly. No
other method changes.

**D2 — Does `save()`'s own `except OSError` block change?**
No. `save()` is completely unchanged — same signature, same
`(bool, str)` return contract, same `except OSError` clause. The new
guard in `_auto_save_loop()` only catches what `save()` itself does
not already convert.

**D3 — Exception type caught.**
`except Exception` (broad), matching both sibling tick loops verbatim
(`# noqa: BLE001 - the ... loop must never die silently`), not a
narrower type — the whole point is that any *unanticipated* exception
type must not kill the thread, mirroring the existing precedent
exactly rather than inventing a narrower policy for this one loop.

**D4 — Log message wording and content.**
A new, fixed message, `f"Memory auto-save loop encountered an
unexpected error: {exc}"`, distinct from the existing `f"Memory
auto-save failed: {message}"` wording, so the two failure paths remain
independently identifiable in logs. Only `str(exc)` is included — no
`MemoryEntry` values, no snapshot content, no file paths beyond what
`str(exc)` itself may already contain from the underlying library
error.

**D5 — Loop continuation, not thread restart.**
On catching the exception, the loop calls `continue` and waits for the
next `_stop_event.wait(interval)` cycle exactly as normal — no
immediate retry, no backoff, no restart of a new thread. This matches
`SchedulerService`/`WorkflowSchedulerService`'s own behavior
identically; introducing backoff/retry logic not present in either
sibling would be inconsistent, unrequested scope growth.

**D6 — `shutdown()` behavior is unaffected.**
`shutdown()` (EP-064) is not modified. `_stop_event.set()` +
`thread.join()` continue to work exactly as before; the new
`except Exception` block does not intercept `_stop_event`-driven
termination in any way, since `_stop_event.wait(interval)` is outside
the new `try` block, exactly as in both sibling loops.

**D7 — No new public API surface.**
No new method, no new `MemoryModule`/`RuntimeModule` CLI/REST action,
no new `MemoryStatus`/`MemoryDoctorReport` field. `auto_save_running`
already correctly reports `is_alive()`; this fix changes *whether* the
thread stays alive, not how that liveness is observed.

**D8 — Files allowed to change.**
Exactly one production file:
`src/core/memory/memory_persistence.py`, and only within
`_auto_save_loop()`'s body plus its docstring. No other production
file changes.

**D9 — Test placement.**
A new, dedicated, self-contained `tests/EP066/` package, per this
repository's now-consistently-applied convention (`tests/EP061/`
through `tests/EP065/`). No historical EP test file is modified.

**D10 — Deferred items remain untouched.**
Every Architecture Debt item (AD-001 through AD-009), Telegram Gateway
shutdown coordination, REST API authentication, the PluginLoader
status-sync TODO, and cron schedule support all remain explicitly
deferred and untouched by this EP (Section 7/9).

## 12. Production Files Allowed to Change

- `src/core/memory/memory_persistence.py` (`_auto_save_loop()` body
  and docstring only)
- `src/modules/test_module.py` (exactly one new import line for
  `tests.EP066`, in the established appended position)

No other production file may change.

## 13. Test Strategy

New package: `tests/EP066/`.

- `tests/EP066/__init__.py` — empty, matching
  `tests/EP061/__init__.py` through `tests/EP065/__init__.py`.
- `tests/EP066/test_memory_persistence_auto_save_resilience.py` (exact
  name to be finalized in STEP 2; module docstring must name
  `NAME = "EP066"` via `@TestRegistry.register`, following the
  `BaseTest`/`TestRegistry` convention already used by
  `tests/EP061/` through `tests/EP065/`).
- Registration: one new line in `src/modules/test_module.py`,
  `import tests.EP066.<module_name>`, appended immediately after the
  existing `import tests.EP065.test_command_router_malformed_input`
  line.

Tests must be self-contained (no `import tests.EP0XX` from any other
package), using real `MemoryPersistence`/`MemoryStore`/`Config`
objects wherever possible, following this repository's own established
preference for real objects with one faked boundary over tautological
mocks (as EP-065's own audit specifically praised in `tests/EP065/`).

Planned coverage:

- **Happy-path:** a real `MemoryPersistence` with auto-save enabled,
  short interval, genuine `save()` succeeding repeatedly — confirms
  the new `try`/`except` does not alter successful-save behavior or
  timing.
- **Failure/edge-case — the critical regression test:** monkeypatch
  (or subclass-override) `save()` on a real `MemoryPersistence`
  instance to raise a generic `Exception` (not `OSError`) on its first
  call, then succeed normally on subsequent calls; assert (a) the
  `"memory-auto-save"` thread is still alive after the interval that
  raised, (b) a real `loguru` capture sink shows the new distinct
  error message and not the pre-existing "Memory auto-save failed:"
  wording, (c) a later, successful `save()` call still occurs on the
  next tick (proving the loop truly continued, not merely that the
  thread object didn't immediately die).
- **Failure/edge-case — `OSError` path unchanged (regression):**
  monkeypatch `save()`'s internal file write to raise `OSError`
  exactly as before this EP; confirm the pre-existing "Memory auto-save
  failed: {message}" log path still fires, unchanged, and the loop
  still continues (this already worked before EP-066; this test proves
  EP-066 did not accidentally change or duplicate that path).
- **Boundary — `_stop_event` still takes priority:** confirm that
  calling `shutdown()` while `save()` is (in a controlled, intercepted
  way) about to raise still results in a clean, timely stop — i.e. the
  new `except Exception`/`continue` does not create a busy-loop that
  starves `_stop_event.wait()`.
- **Regression — idempotent repeated failures:** `save()` raises on
  every call for several consecutive intervals; confirm the thread
  survives all of them and the loop only ever logs the new distinct
  message, never crashes, never duplicates the pre-existing OSError
  message.
- **Regression — `shutdown()` (EP-064) unaffected:** re-run the shape
  of EP-064's own isolated `shutdown()` tests (never-started,
  not-persistent, already-running, idempotent, `wait=False`, the fixed
  5-second timeout) against the modified file as local, independent
  EP-066-owned fixtures (not imported from `tests/EP064/`), to
  positively confirm `shutdown()`'s behavior is unchanged by this
  EP's edit to a neighboring method in the same file.
- **Integration-path:** a real `Bootstrap`-driven end-to-end
  construction (mirroring `tests/EP064/`'s own end-to-end test
  structure, independently reimplemented, not imported) confirming
  auto-save survives an injected transient failure without disrupting
  `Bootstrap.shutdown()`'s final memory save.

Protected/regression tests to re-run, unchanged: `tests/EP064/test_memory_persistence_shutdown.py`
(93/0/0 expected, unchanged), `tests/EP061/`, `tests/EP062/`,
`tests/EP063/`, `tests/EP065/`, plus the full project suite.

## 14. Protected Files

At minimum:

- `tests/EP061/`, `tests/EP062/`, `tests/EP063/`, `tests/EP064/`,
  `tests/EP065/` (every file) — untouched.
- `src/services/scheduler_service.py`,
  `src/services/workflow_scheduler_service.py`,
  `src/services/telegram_service.py`,
  `src/core/telegram/telegram_router.py`,
  `src/core/telegram/telegram_client.py`,
  `src/modules/telegram_module.py`,
  `src/core/api/api_router.py`, `src/core/api/rest_api_server.py`,
  `src/core/api/dto.py`, `src/core/command_router.py`,
  `src/core/shell.py` — untouched.
- `src/services/memory_service.py`, `src/modules/memory_module.py`,
  `src/services/runtime_service.py`, `src/modules/runtime_module.py`,
  `src/bootstrap.py`, `src/main.py` — untouched (this EP changes only
  `MemoryPersistence`'s own internal loop body, not any of its
  callers or wiring).
- `config/config.yaml` — untouched (no new configuration key; the
  fix introduces no new tunable).
- `docs/architecture/ARCHITECTURE_DEBT.md`, `CHANGELOG.md`,
  `docs/RELEASE_NOTES.md`, `docs/BACKLOG.md`,
  `docs/architecture/JARVIS_ROADMAP.md` — untouched during STEP 1/2
  (BACKLOG/RELEASE_NOTES/CHANGELOG updates are STEP 4 concerns, not
  STEP 1).
- Every EP-001 through EP-065 design and audit document — untouched.

The final STEP 2 implementation should modify only the two files named
in Section 12.

## 15. Validation Plan

STEP 2/STEP 3 must run and report:

- The dedicated `tests/EP066/` suite (new).
- Directly affected existing tests: `tests/EP064/test_memory_persistence_shutdown.py`
  (the same file whose subject, `MemoryPersistence`, this EP also
  edits — must remain 93/0/0, byte-identical file, unchanged results).
- Previous-EP regression suites for every other background-loop EP:
  `tests/EP061/`, `tests/EP062/`, `tests/EP063/`, `tests/EP065/`.
- The full project test runner (`TestRunner.run_all()`), to catch any
  unforeseen interaction.
- Protected-file verification: a full-repository diff against the
  pre-EP-066 baseline, confirming only the two files in Section 12
  changed (plus this design document and the new `tests/EP066/`
  package), exactly as EP-065's STEP 3 Section 9 performed.
- Final diff verification before STEP 3 sign-off.

Known environmental limitations (documented by EP-065's own STEP 3,
Section 1): the EP046/EP048 voice-related suites cannot execute in
this environment (missing `vosk`/`sounddevice`/PortAudio). STEP 2/STEP 3
must re-confirm these are unchanged/pre-existing by comparing against
the untouched baseline, exactly as EP-065 did, rather than attributing
them to this EP.

## 16. Risks

- **Masking a genuinely fatal condition.** A broad `except Exception`
  could theoretically hide a serious, unrecoverable problem (e.g. the
  storage directory becoming permanently inaccessible in a way
  `OSError` doesn't already cover) behind a log line instead of a
  crash. Mitigated by: this is exactly the same trade-off
  `SchedulerService`/`WorkflowSchedulerService` already made and had
  independently audited (EP-061/EP-063), and a permanently-inaccessible
  storage directory is already an `OSError`, already handled by
  `save()`'s own existing contract — the new branch only ever fires
  for exceptions *outside* that already-handled class.
- **Silent repeated failure without operator visibility.** If
  `save()` fails on every tick going forward, auto-save now silently
  "runs" (thread alive, `auto_save_running: True`) while never
  actually persisting anything, logging an error each time but not
  otherwise surfacing state to `memory status`. This is judged
  acceptable because it exactly matches `SchedulerService`'s own
  already-accepted behavior for a permanently-failing tick, and
  `memory doctor`'s existing round-trip write/read check
  (`_validate_persistence()`) already independently surfaces a broken
  storage path through a different, existing mechanism, unaffected by
  this EP.
- **Test flakiness from thread timing.** Tests asserting "the loop
  continued past a failure" need a short interval and a bounded wait
  loop rather than a fixed `sleep`, following `tests/EP064/`'s own
  established pattern for this exact kind of real-thread assertion.

## 17. Deferred/Future Work

- All Architecture Debt items (AD-001 through AD-009) — unchanged,
  reserved for a dedicated Architecture Cleanup milestone.
- Telegram Gateway shutdown coordination — unchanged, still blocked on
  zero pre-existing test coverage (and, structurally, a pre-existing
  manual escape hatch).
- REST API authentication — unchanged, still architecturally large.
- PluginLoader metadata-only-plugin status cross-checking — unchanged,
  still requires a multi-service constructor-injection change.
- Cron schedule support — unchanged, still a net-new feature.
- `docs/architecture/ARCHITECTURE_DEBT.md`'s stale AD-005 entry
  (already resolved in code, per Section 5) — a documentation
  correction, appropriate for a future STEP 4 of some EP that
  otherwise touches that file, or a dedicated documentation pass; not
  introduced as a side effect of EP-066.

## 18. STEP 1 Completion Criteria

- [x] Repository-first discovery performed: BACKLOG, ROADMAP,
      CHANGELOG, RELEASE_NOTES, and EP-061 through EP-065
      design/audit documents read.
- [x] Multiple plausible candidates identified and compared
      (Section 7), not merely the first issue found.
- [x] Actual production code inspected directly (not just comments,
      backlog text, or prior audit claims) for the selected candidate
      and its two closest siblings (`SchedulerService`,
      `WorkflowSchedulerService`).
- [x] Selected candidate verified not to duplicate or overlap any
      completed EP (EP-064 added a deliberate-stop primitive; EP-066
      closes an accidental-death gap in the same loop — confirmed
      non-overlapping).
- [x] Owner Decisions (D1-D10) drafted, concrete and verifiable.
- [x] Test strategy defined under `tests/EP066/`, following the
      established convention.
- [x] Protected files enumerated.
- [x] Validation plan defined, including full regression scope and
      the known pre-existing environmental limitations.
- [x] `docs/architecture/designs/EP066_DESIGN.md` created.
- [x] No production code modified. No test created. No documentation
      other than this file modified. STEP 2 not started.
