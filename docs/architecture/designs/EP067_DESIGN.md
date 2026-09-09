# EP-067 — TelegramService Poll Loop Exception Containment

STEP 1: Architecture Discovery & Design

Status: DESIGN PROPOSED — awaiting Owner Decision approval before STEP 2

---

## 1. Title

EP-067 — TelegramService Poll Loop Exception Containment

## 2. Status

STEP 1 complete (this document). STEP 2 (Implementation & Testing),
STEP 3 (Architecture Audit), and STEP 4 (Documentation Synchronization)
have not started.

## 3. Problem Statement

`TelegramService._poll_loop()` (`src/services/telegram_service.py`) is
now the **only** background tick/poll loop left in this repository
whose per-iteration call is not wrapped in a broad exception guard.
Its body is:

```python
def _poll_loop(self) -> None:
    interval = float(self._config.get("telegram.polling_interval", 2))
    while not self._stop_event.wait(interval):
        self._poll_once()
    logger.info("Telegram polling stopped.")
```

`_poll_once()` only converts `TelegramClientError` (raised by
`TelegramClient.fetch_updates()`/`send_message()` for the specific,
already-anticipated cases documented on `TelegramClientError` itself —
invalid token, connection timeout, general Bot-API-unavailable
conditions surfaced through `python-telegram-bot`'s own `TelegramError`
hierarchy) into a logged, swallowed failure. Any exception of a
*different* type — for example a `RuntimeError` from the private
asyncio event loop (`TelegramClient._run()`), a transport-level
`OSError`/`ConnectionError` that `python-telegram-bot` does not wrap
into `TelegramError`, or any unexpected attribute/parsing failure
while iterating `Bot.get_updates()`'s returned `Update` objects —
propagates straight out of `_poll_once()`, out of `_poll_loop()`, and
kills the `"telegram-poll"` daemon thread permanently. There is no
supervisor and no restart mechanism, so once this happens, the bot
stops receiving Telegram messages for the remainder of the process's
life — indistinguishable, from the outside, from the same
already-fixed accidental-death shape EP-061, EP-063, and EP-066 each
closed for their own respective loops.

Every other structurally equivalent background loop in this codebase
already guards against exactly this:

- `SchedulerService._tick_loop()` (EP-061) —
  `except Exception as exc: logger.error(...)`, loop continues.
- `WorkflowSchedulerService._tick_loop()` (EP-063) — same shape.
- `MemoryPersistence._auto_save_loop()` (EP-066) — same shape, closing
  the exact same class of gap for the auto-save thread.

`TelegramService._poll_loop()` is now the sole remaining outlier.

This is not a new observation, but it has never been the subject of
its own dedicated fix. `EP065_DESIGN.md` Section 2.5 documented the
absence of any `try`/`except` around `_poll_loop()`'s body directly,
and its Owner Decision D7 explicitly considered — and declined —
hardening it, but **only** with respect to the one, narrow,
already-demonstrated failure mode EP-065 was itself scoped to: a raw
`ValueError` from `CommandRouter._tokenize()` reaching
`TelegramRouter.route()` through a malformed chat message. D7's own
stated reasoning was that this *specific* failure mode was already
closed at its source (inside `CommandRouter.dispatch()`), and that
D7 "does not claim [`TelegramService`] is exception-safe in general —
only that this specific, demonstrated failure mode requires no change."
EP-067 is the dedicated follow-up D7 itself anticipated: closing the
loop's *general* exception-safety gap, the same way EP-066 was the
dedicated follow-up EP-064's own Finding F1/Owner Decision D6 had
anticipated for `MemoryPersistence`.

## 4. Current Architecture / Behavior

`TelegramService` (`src/services/telegram_service.py`, EP-012) owns a
daemon thread, `"telegram-poll"`, started by `start()` when
`telegram.enabled` is true, running `_poll_loop()`:

```python
def _poll_loop(self) -> None:
    """Repeatedly poll for and route messages every 'telegram.polling_interval' seconds."""
    interval = float(self._config.get("telegram.polling_interval", 2))
    while not self._stop_event.wait(interval):
        self._poll_once()
    logger.info("Telegram polling stopped.")

def _poll_once(self) -> None:
    """Fetch and route any new messages, replying with each command's result."""
    if self._client is None:
        return

    try:
        messages = self._client.fetch_updates()
    except TelegramClientError as exc:  # noqa: BLE001 - the poll loop must never die silently
        logger.error(f"Telegram polling failed: {exc}")
        return

    for message in messages:
        result = self._router.route(message.chat_id, message.text)
        try:
            self._client.send_message(message.chat_id, result.message)
        except TelegramClientError as exc:
            logger.error(f"Telegram outgoing message failed: {exc}")
```

Note the existing `# noqa: BLE001 - the poll loop must never die
silently` comment already sits on `_poll_once()`'s `fetch_updates()`
guard — the stated *intent* ("must never die silently") already
exists in this file, but the guard is narrower than that stated intent
in two independent ways:

1. It only catches `TelegramClientError`, not the broader `Exception`
   every sibling loop's guard catches.
2. It only wraps `fetch_updates()`. There is **no** guard at all
   around `_poll_loop()`'s own call to `_poll_once()` — so even a
   second `TelegramClientError`-raising call site added to
   `_poll_once()` in the future (or a non-`TelegramClientError`
   exception from anywhere inside it, including the `for message in
   messages:` loop body, `TelegramRouter.route()`, or
   `self._client.send_message()`) would still kill the thread today,
   exactly as it would have before EP-012's own `_poll_once()` guard
   was written.

Confirmed by direct reading of the only two calls inside the `for`
loop:

- `TelegramRouter.route()` (`src/core/telegram/telegram_router.py`) —
  a chat-id set-membership check plus one call into
  `CommandRouter.dispatch()`. `dispatch()` itself already converts its
  own two documented failure classes (malformed quoting, per EP-065;
  `module.execute()` raising) into a `CommandResult`, so `route()`
  cannot currently propagate an exception through this specific path —
  but `TelegramRouter`/`CommandRouter` carry no *contractual*
  exception-safety guarantee against every future change, and nothing
  in `_poll_loop()` itself protects against a regression there.
- `TelegramClient.send_message()` — already guarded by its own
  `except TelegramClientError` in `_poll_once()`; not part of this
  gap.

`TelegramClient.fetch_updates()` (`src/core/telegram/telegram_client.py`)
itself only catches `TelegramError` (the `python-telegram-bot` library
hierarchy) around its own `Bot.get_updates()` call; unwrapped
`asyncio`/event-loop errors from `TelegramClient._run()`
(`self._loop.run_until_complete(coroutine)`, e.g. `RuntimeError` if the
private loop is ever driven from an unexpected state) are not
`TelegramError` subclasses and are therefore not caught by
`fetch_updates()`'s own `except TelegramError`, and would not be caught
by `_poll_once()`'s `except TelegramClientError` either — both are
narrower than "any exception."

Sibling background loops, for direct contrast (all three confirmed
unchanged by any later EP, all three sharing the identical shape and
comment convention):

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

All three wrap their single per-iteration unit of work directly inside
the `while not self._stop_event.wait(interval):` loop, in a
`try`/`except Exception as exc:` block carrying the identical
`# noqa: BLE001 - the ... loop must never die silently` comment
convention. `TelegramService._poll_loop()` is the only one of the four
background loops in this repository (`SchedulerService`,
`WorkflowSchedulerService`, `MemoryPersistence`, `TelegramService`)
that does not follow this now-three-times-established pattern at the
loop level itself.

Observability once the thread has died: `TelegramService._is_poll_loop_running()`
and `TelegramStatus.running` (both pre-existing, unaffected by this
EP) report the thread's actual `is_alive()` state, so `telegram
status` would eventually show `running: False` if queried — but
nothing proactively surfaces *why* it stopped, and nothing restarts
it, exactly the same observability shape EP-066's Section 4 described
for `MemoryPersistence` before its own fix.

## 5. Discovery Findings

Discovery was performed by reading, in order: `docs/BACKLOG.md`,
`CHANGELOG.md`, `docs/RELEASE_NOTES.md`,
`docs/architecture/JARVIS_ROADMAP.md`,
`docs/architecture/designs/EP066_DESIGN.md`, and
`docs/architecture/audits/EP066_ARCHITECTURE_AUDIT.md` in full,
followed by re-reading `docs/architecture/designs/EP065_DESIGN.md`
(Sections 2.5, D6, D7) and `docs/architecture/ARCHITECTURE_DEBT.md` in
full, a repository-wide search for TODO/FIXME/XXX markers, and direct
inspection of all four background-loop implementations
(`src/services/scheduler_service.py`,
`src/services/workflow_scheduler_service.py`,
`src/core/memory/memory_persistence.py`,
`src/services/telegram_service.py`) plus their immediate dependencies
(`src/core/telegram/telegram_client.py`,
`src/core/telegram/telegram_router.py`, `src/core/command_router.py`).

Candidates considered (full comparison in Section 7):

1. **`TelegramService._poll_loop()` exception containment**
   (anticipated but explicitly not fixed by EP-065 Owner Decision D7,
   re-confirmed still absent by direct inspection of current source)
   — selected.
2. `GitService.show(ref)` missing `--` argument separator
   (Architecture Debt AD-009) — rejected, Architecture Debt item.
3. `workflow_scheduler.tick_interval` validation / `Bootstrap`'s
   unreachable `WorkflowSchedulerError` handler (Architecture Debt
   AD-001/AD-002) — rejected, Architecture Debt items.
4. Telegram Gateway shutdown coordination (`RuntimeService` never
   observing/coordinating the `"telegram-poll"` thread) — rejected,
   the same candidate independently investigated and rejected by
   EP-063, EP-064, and EP-065 in turn, for the same two reasons each
   time; re-confirmed unchanged (Section 7). **Distinct** from the
   selected candidate: shutdown coordination concerns *deliberate*,
   process-level stop orchestration; the selected candidate concerns
   an *accidental* death from an uncaught exception mid-loop — the
   same distinction EP-066 Section 6 drew between itself and EP-064's
   `shutdown()` work on the same file.
5. REST API authentication — rejected, real but architecturally large,
   independently identified and deferred by EP-064, EP-065, and
   EP-066 for the same reason.
6. `PluginLoader`'s metadata-only-plugin status bookkeeping not
   cross-checked against `ProcessService`/`InvoiceService`/
   `FastResponseService` (explicit TODO in `plugin_loader.py`) —
   rejected, requires a constructor-injection change spanning multiple
   services, larger than a single bounded EP.
7. Cron schedule support (`Scheduler.calculate_next_run`,
   `WorkflowSchedulerEngine`'s `ScheduleType.CRON` branch) — rejected,
   a net-new feature (a cron expression parser), not an architecture
   fix, explicitly out of scope since EP-011.

`docs/architecture/ARCHITECTURE_DEBT.md` was re-read in full. Its own
governing rule — "Never fix Architecture Debt during a normal
Engineering Phase (EP)... Architecture Debt is addressed only during a
dedicated cleanup milestone" — categorically excludes every open
AD-item (AD-001, AD-002, AD-003, AD-006, AD-007, AD-008, AD-009) from
EP-067 regardless of individual merit, consistent with EP-065's and
EP-066's own discovery sections. This STEP 1 independently re-confirms
that exclusion rather than assuming it; no new Architecture Debt item
has been added since EP-066, and the selected candidate is not itself
a recorded Architecture Debt item (it is a currently-live gap in
exception containment, verified by direct code reading against the
same evidentiary bar EP-061/EP-063/EP-066 used for their own selected
candidates, not a documentation-only or postponed-by-policy item).

## 6. Selected Candidate

**`TelegramService._poll_loop()` Exception Containment.**

`_poll_loop()`'s call to `_poll_once()` will be wrapped in its own
`try`/`except Exception` block, structurally identical in shape,
placement, and log-wording convention to `SchedulerService._tick_loop()`,
`WorkflowSchedulerService._tick_loop()`, and
`MemoryPersistence._auto_save_loop()`: on any exception not already
converted into a logged, swallowed failure by `_poll_once()`'s own
narrower `except TelegramClientError` guard, log it via
`logger.error(...)` and continue the loop rather than letting the
`"telegram-poll"` thread die. This is purely additive at the
`_poll_loop()` level; `_poll_once()`, `TelegramClient`,
`TelegramRouter`, and every other method are untouched.

- **Current implementation:** see Section 4.
- **Exact problem:** any exception raised while executing
  `_poll_once()` that is not a `TelegramClientError` — reachable today
  through, at minimum, an unwrapped `asyncio`/event-loop failure
  inside `TelegramClient._run()`, and structurally guaranteed to
  reopen for any future change to `_poll_once()`, `TelegramRouter.route()`,
  or `CommandRouter.dispatch()` that introduces a new exception type —
  is uncaught inside `_poll_loop()` and permanently, silently kills the
  polling thread.
- **Affected files/modules:** `src/services/telegram_service.py` (one
  method, `_poll_loop()`) only.
- **Why it matters:** Telegram is disabled by default
  (`telegram.enabled: false`), so this does not affect a default
  installation, but for any installation that does enable it, a
  silent, permanent stop of message polling (with zero log evidence of
  why beyond `_poll_once()`'s own narrower, already-existing guard)
  directly contradicts this repository's own stated invariant — "the
  poll loop must never die silently," a comment that already exists in
  this exact file today, one guard too narrow to fully deliver on its
  own stated promise.
- **Estimated implementation scope:** one new `try`/`except` block, ~4
  lines, no signature change, no new public method, no new dataclass
  field.
- **Expected tests:** see Section 13.
- **Architectural risk:** minimal — the change narrows failure impact
  (an isolated bad poll iteration no longer kills the thread) and does
  not widen any existing exception boundary elsewhere; it mirrors an
  already-approved, already-audited pattern used three times before in
  this same codebase.
- **Dependencies on previous/future EPs:** builds directly on EP-012's
  `TelegramService`/`_poll_loop()` machinery and is the direct,
  anticipated follow-up to EP-065 Owner Decision D7; no dependency on
  EP-066's `MemoryPersistence` work (a different file), though it
  applies the identical, now three-times-precedented pattern. No known
  future EP depends on this one.
- **Why suitable for EP-067:** real (not hypothetical —
  `TelegramClientError` is demonstrably narrower than "any exception,"
  and the loop-level guard is demonstrably absent by direct reading),
  small, bounded to one file, independently testable via a fake
  `TelegramClient`/`TelegramRouter` without any real network access,
  consistent with existing architecture (copies an already-three-times-
  approved pattern verbatim), not cosmetic, and not a duplicate of any
  completed EP (EP-065 closed one specific, narrow `ValueError` source
  at `CommandRouter`, explicitly declining to also harden
  `TelegramService` itself per D7; EP-067 is that declined, deferred,
  general hardening — a different file, a different exception class,
  and a different architectural layer, confirmed non-overlapping in
  Section 8).

## 7. Rejected Alternatives

**GitService.show(ref) missing `--` separator (AD-009).** Real,
narrow, single-line fix. Rejected solely because it is a recorded,
open Architecture Debt item, and this repository's own governance
(`ARCHITECTURE_DEBT.md` Rules section) forbids fixing Architecture
Debt during a normal EP — it is reserved for a dedicated Architecture
Cleanup milestone. Not rejected on technical merit. (Independently
re-confirmed still present and still unmodified in current
`src/services/git_service.py` during this discovery.)

**AD-001 / AD-002 (`workflow_scheduler.tick_interval` validation;
`Bootstrap`'s unreachable `WorkflowSchedulerError` handler).** Same
reason as AD-009 — both are recorded Architecture Debt, off-limits to
a normal EP by the repository's own rule, independent of their
individual merit.

**Telegram Gateway shutdown coordination.** The same candidate
independently investigated and rejected three EPs running (EP-063,
EP-064, EP-065), each time for the same two reasons: a manual
`telegram stop` escape hatch already exists, and there was zero
pre-existing dedicated test coverage for `TelegramService` to build on
safely. The second reason changes with this EP's own selection —
EP-067 will itself introduce the first dedicated `tests/EP067/`
coverage for `TelegramService` — but shutdown *coordination*
(`RuntimeService` observing/joining the `"telegram-poll"` thread on
process exit) remains a distinct, larger, and still-unevidenced-as-
broken concern from this EP's own narrow exception-containment fix:
`TelegramService.stop()` today already deterministically joins its own
thread with a timeout when invoked, and nothing in this discovery
found a demonstrated defect in `RuntimeService`'s shutdown ordering
itself (as opposed to the loop's internal exception safety, which is
what EP-067 actually fixes). Folding shutdown-coordination work into
this EP would be exactly the kind of scope creep Section 6 discipline
(narrow production scope) exists to prevent; it remains a separate,
still-open candidate for a future, dedicated EP now that baseline test
coverage will exist to build it on safely.

**REST API authentication.** A real, repeatedly disclosed gap (noted
by name in EP-064's, EP-065's, and EP-066's own discovery sections),
but architecturally large — it would touch request handling across
every REST endpoint, credential storage, and configuration, well
beyond a single bounded EP. Consistently deferred by every EP that has
encountered it so far; EP-067 does the same.

**PluginLoader metadata-only-plugin status bookkeeping (`plugin_loader.py`
TODO).** Real gap, but its own TODO already explains why it is
out of scope: fixing it requires injecting one of
`ProcessService`/`InvoiceService`/`FastResponseService` into
`PluginLoader`/`PluginService`, a constructor-signature change
spanning multiple services — a multi-service wiring change, not a
single-file, independently bounded fix. Rejected on scope grounds, not
merit, consistent with EP-066 Section 7's own identical reasoning.

**Cron schedule support.** `Scheduler.calculate_next_run()` and
`WorkflowSchedulerEngine`'s `ScheduleType.CRON` branch both remain
interface-only, documented since EP-011 as having no cron expression
parser. A net-new feature, not a bounded architectural fix; explicitly
out of scope for the kind of small, well-bounded EP this discovery is
looking for.

**Why the selected candidate is better than all of the above:** it is
the only candidate that is (a) not recorded Architecture Debt subject
to the repository's own fix-timing rule, (b) not something already
rejected multiple times with unchanged facts (Telegram shutdown
coordination remains rejected, but for a narrower, still-valid reason
distinct from this EP's own fix — see above), (c) not architecturally
large, (d) not a multi-service wiring change, and (e) not a net-new
feature — while still being a real, verified, currently-uncovered gap
with a precedented, low-risk fix shape already three-times-approved in
this same codebase, and directly anticipated by name in EP-065's own
Owner Decision D7.

## 8. Scope

In scope:

- `src/services/telegram_service.py`: wrap the `self._poll_once()`
  call inside `_poll_loop()` in `try`/`except Exception`, logging via
  `logger.error(...)` and continuing the loop, mirroring
  `SchedulerService._tick_loop()`/`WorkflowSchedulerService._tick_loop()`/
  `MemoryPersistence._auto_save_loop()` exactly in shape and
  log-wording convention (a new, distinct message identifying the poll
  loop itself, e.g. `f"Telegram poll loop encountered an unexpected
  error: {exc}"`, to remain visibly distinct from the pre-existing
  `f"Telegram polling failed: {exc}"` message `_poll_once()`'s own
  narrower `except TelegramClientError` guard already logs).
- `tests/EP067/`: a new, dedicated, self-contained test package —
  the first dedicated test coverage for `TelegramService` in this
  repository.
- `src/modules/test_module.py`: exactly one new import line,
  registering `tests.EP067.<module>`, in the established position
  (appended after the existing `tests.EP066...` line).

Out of scope (see Non-Goals): any change to `_poll_once()`'s existing
`except TelegramClientError` handling, `TelegramClient`,
`TelegramRouter`, `start()`/`stop()`/`status()`/`doctor()`/
`send_message()`, Telegram Gateway shutdown coordination via
`RuntimeService`, or any file outside
`src/services/telegram_service.py`.

## 9. Non-Goals

- Does **not** change `_poll_once()`'s existing `except
  TelegramClientError` block, its return-early-on-failure shape, or
  its own log message.
- Does **not** add a restart/auto-recovery mechanism for the polling
  thread beyond "keep looping past this exception" (matching
  `SchedulerService`/`WorkflowSchedulerService`/`MemoryPersistence`'s
  own behavior exactly — none of those restarts its thread either;
  they simply don't let a single bad iteration kill it).
- Does **not** add any new public method, CLI/REST/Telegram action, or
  `TelegramStatus`/`TelegramDoctorReport` field. `TelegramStatus.running`
  (pre-existing) already reflects `is_alive()` correctly for both the
  "stopped cleanly via `stop()`" and "would have died, now doesn't"
  cases — no new field is needed to observe this fix's effect.
- Does **not** touch `TelegramService.start()`/`stop()` in any way —
  those methods handle deliberate lifecycle transitions and are
  structurally unrelated to an accidental-death exception path inside
  the loop body.
- Does **not** address Telegram Gateway shutdown coordination via
  `RuntimeService` — a distinct, larger, still-separately-deferred
  concern (Section 7).
- Does **not** address any Architecture Debt item (AD-001 through
  AD-009), REST API authentication, the PluginLoader status-sync TODO,
  or cron support — all remain explicitly deferred, unchanged
  (Section 7).
- Does **not** modify `TelegramClient` or `TelegramRouter` — both are
  confirmed, by direct reading (Section 4), not to require any change
  to close this specific defect; the fix is fully contained inside
  `TelegramService._poll_loop()`.
- Does **not** modify any historical EP's test file.

## 10. Proposed Design

`_poll_loop()` becomes:

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

Design notes:

- `_poll_once()` itself, including its own existing `except
  TelegramClientError` block around `fetch_updates()` and its own
  `except TelegramClientError` block around `send_message()`, is
  completely unchanged. The new guard only ever fires for exceptions
  `_poll_once()` does not already convert into a return/log itself.
- The new `except Exception` block sits directly around the
  `self._poll_once()` call, exactly mirroring where
  `SchedulerService`/`WorkflowSchedulerService`/`MemoryPersistence`
  place their own guard around their own single per-iteration call.
- No `continue` statement is needed: unlike
  `MemoryPersistence._auto_save_loop()` (which has an `if not success:`
  branch after its guarded call that an exception path must not fall
  into), `_poll_loop()`'s guarded call is the only statement in the
  loop body, matching `SchedulerService`/`WorkflowSchedulerService`'s
  own simpler shape exactly — after the `except` block, control
  reaches the bottom of the `while` body regardless, and the loop
  proceeds to its next `_stop_event.wait(interval)` cycle.
- The new log message is deliberately worded differently
  ("...poll loop encountered an unexpected error...") from the
  existing "Telegram polling failed: {exc}" message so the two paths
  remain distinguishable in logs — mirroring EP-066 Owner Decision D4's
  identical reasoning for keeping its own new/old messages textually
  distinct.
- No raw message text, chat id, or token is included in the new log
  message — only `str(exc)`, matching this repository's existing
  convention (EP-065 Owner Decision D4 and EP-066 Owner Decision D4
  both applied the same principle; `SchedulerService`/
  `WorkflowSchedulerService`/`MemoryPersistence`'s own equivalent
  messages likewise log only `str(exc)`, never task/job/entry
  payloads).

## 11. Owner Decisions

**D1 — Where does the guard live?**
The `try`/`except Exception` wraps only the `self._poll_once()` call
inside `_poll_loop()`, matching `SchedulerService._tick_loop()`'s,
`WorkflowSchedulerService._tick_loop()`'s, and
`MemoryPersistence._auto_save_loop()`'s own placement exactly. No
other method changes.

**D2 — Does `_poll_once()`'s own exception handling change?**
No. `_poll_once()` is completely unchanged — same two existing
`except TelegramClientError` blocks, same return-early-on-fetch-failure
shape, same per-message send-failure handling. The new guard in
`_poll_loop()` only catches what `_poll_once()` itself does not
already convert.

**D3 — Exception type caught.**
`except Exception` (broad), matching all three sibling loops verbatim
(`# noqa: BLE001 - the ... loop must never die silently`), not a
narrower type — the whole point is that any *unanticipated* exception
type must not kill the thread, mirroring the existing, now
three-times-established precedent exactly rather than inventing a
narrower policy for this one loop.

**D4 — Log message wording and content.**
A new, fixed message, `f"Telegram poll loop encountered an unexpected
error: {exc}"`, distinct from the existing `f"Telegram polling failed:
{exc}"` wording, so the two failure paths remain independently
identifiable in logs. Only `str(exc)` is included — no chat id, no
message text, no token, no other payload beyond what `str(exc)` itself
may already contain from the underlying library error.

**D5 — Loop continuation, not thread restart.**
On catching the exception, the loop falls through to the bottom of its
body and waits for the next `_stop_event.wait(interval)` cycle exactly
as normal — no immediate retry, no backoff, no restart of a new
thread. This matches `SchedulerService`/`WorkflowSchedulerService`/
`MemoryPersistence`'s own behavior identically; introducing
backoff/retry logic not present in any of the three siblings would be
inconsistent, unrequested scope growth.

**D6 — `start()`/`stop()` behavior is unaffected.**
Neither `start()` nor `stop()` (both pre-existing) is modified.
`_stop_event.set()` + `thread.join(timeout=5)` inside `stop()` continue
to work exactly as before; the new `except Exception` block does not
intercept `_stop_event`-driven termination in any way, since
`_stop_event.wait(interval)` is outside the new `try` block, exactly
as in all three sibling loops.

**D7 — No new public API surface.**
No new method, no new `TelegramModule`/`RuntimeModule` CLI/REST
action, no new `TelegramStatus`/`TelegramDoctorReport` field.
`TelegramStatus.running` already correctly reports `is_alive()`; this
fix changes *whether* the thread stays alive, not how that liveness is
observed.

**D8 — Files allowed to change.**
Exactly one production file: `src/services/telegram_service.py`, and
only within `_poll_loop()`'s body plus its docstring. No other
production file changes.

**D9 — Test placement.**
A new, dedicated, self-contained `tests/EP067/` package, per this
repository's now-consistently-applied convention (`tests/EP061/`
through `tests/EP066/`) — this is also the first dedicated test
package for `TelegramService` in this repository (Section 7's
Telegram-shutdown-coordination rejection notes that this closes half
of the reason that candidate was previously rejected, without itself
taking on shutdown-coordination work). No historical EP test file is
modified.

**D10 — Deferred items remain untouched.**
Every Architecture Debt item (AD-001 through AD-009), Telegram Gateway
shutdown coordination via `RuntimeService`, REST API authentication,
the PluginLoader status-sync TODO, and cron schedule support all
remain explicitly deferred and untouched by this EP (Section 7/9).

## 12. Production Files Allowed to Change

- `src/services/telegram_service.py` (`_poll_loop()` body and
  docstring only)
- `src/modules/test_module.py` (exactly one new import line for
  `tests.EP067`, in the established appended position)

No other production file may change.

## 13. Test Strategy

New package: `tests/EP067/`.

- `tests/EP067/__init__.py` — empty, matching `tests/EP061/__init__.py`
  through `tests/EP066/__init__.py`.
- `tests/EP067/test_telegram_poll_loop_resilience.py` (exact name to
  be finalized in STEP 2; module must register via `TestRegistry`
  with `NAME = "EP067"`, following the `BaseTest`/`TestRegistry`
  convention already used by `tests/EP061/` through `tests/EP066/`).
- Registration: one new line in `src/modules/test_module.py`,
  `import tests.EP067.<module_name>`, appended immediately after the
  existing `import tests.EP066.test_memory_persistence_auto_save_resilience`
  line.

Tests must be self-contained (no `import tests.EP0XX` from any other
package — a fake `TelegramClient`/local `_RecordingModule`-style test
double must be independently (re)defined inside `tests/EP067/` itself,
not imported from `tests/EP065/`'s own fixtures), using real
`TelegramService`/`TelegramRouter`/`CommandRouter`/`Config` objects
wherever possible and faking only the one true I/O boundary
(`TelegramClient`), following this repository's own established
preference for real objects with one faked boundary over tautological
mocks (as EP-065's own audit specifically praised for its own
`tests/EP065/` Telegram survival test).

Planned coverage:

- **Happy-path:** a real `TelegramService` wired to a fake client that
  returns empty update batches, confirming the new `try`/`except` does
  not alter normal polling behavior or timing when nothing fails.
- **Failure/edge-case — the critical regression test:** a fake
  `TelegramClient` whose `fetch_updates()` raises a generic
  `Exception` (not `TelegramClientError`) on its first call, then
  returns normally on subsequent calls; assert (a) the
  `"telegram-poll"` thread is still alive after the interval that
  raised, (b) a real `loguru` capture sink shows the new distinct
  `"Telegram poll loop encountered an unexpected error: ..."` message
  and not the pre-existing `"Telegram polling failed: ..."` wording,
  (c) a later, successful poll still occurs and is routed normally on
  a subsequent tick (proving the loop truly continued, not merely that
  the thread object didn't immediately die).
- **Failure/edge-case — `TelegramClientError` path unchanged
  (regression):** a fake client raising `TelegramClientError` from
  `fetch_updates()` exactly as before this EP; confirm the
  pre-existing `"Telegram polling failed: ..."` log path still fires,
  unchanged, and the loop still continues (this already worked before
  EP-067; this test proves EP-067 did not accidentally change or
  duplicate that path).
- **Boundary — `_stop_event` still takes priority:** confirm that
  calling `stop()` shortly after a controlled, injected exception from
  `_poll_once()` still results in a clean, timely stop within the
  existing `thread.join(timeout=5)` bound — i.e. the new
  `except Exception` does not create a busy-loop that starves
  `_stop_event.wait()`.
- **Regression — idempotent repeated failures:** the fake client
  raises on every `fetch_updates()` call for several consecutive
  intervals; confirm the thread survives all of them and the loop only
  ever logs the new distinct message, never crashes.
- **Regression — `start()`/`stop()`/`status()`/`doctor()` unaffected:**
  local, independent EP-067-owned fixtures (not imported from any
  other EP) confirming `start()`/`stop()` idempotency, `status()`'s
  `running`/`connected` fields, and `doctor()`'s existing checks are
  all unchanged by this EP's edit to `_poll_loop()`.
- **Regression — the EP-065 malformed-message survival scenario still
  holds:** an independent, EP-067-owned reimplementation of the same
  "malformed Telegram message text does not kill the polling thread"
  scenario `tests/EP065/` already covers, confirming this EP's new,
  broader guard does not change that already-passing behavior (it
  simply becomes one of several exception shapes the loop now
  tolerates at two layers instead of one).

Protected/regression tests to re-run, unchanged:
`tests/EP065/test_command_router_malformed_input.py` (42/0/0 expected,
unchanged), `tests/EP061/`, `tests/EP062/`, `tests/EP063/`,
`tests/EP064/`, `tests/EP066/`, plus the full project suite.

## 14. Protected Files

At minimum:

- `tests/EP061/`, `tests/EP062/`, `tests/EP063/`, `tests/EP064/`,
  `tests/EP065/`, `tests/EP066/` (every file) — untouched.
- `src/services/scheduler_service.py`,
  `src/services/workflow_scheduler_service.py`,
  `src/core/memory/memory_persistence.py`,
  `src/core/telegram/telegram_client.py`,
  `src/core/telegram/telegram_router.py`,
  `src/modules/telegram_module.py`,
  `src/core/api/api_router.py`, `src/core/api/rest_api_server.py`,
  `src/core/api/dto.py`, `src/core/command_router.py`,
  `src/core/shell.py` — untouched.
- `src/services/memory_service.py`, `src/modules/memory_module.py`,
  `src/services/runtime_service.py`, `src/modules/runtime_module.py`,
  `src/bootstrap.py`, `src/main.py` — untouched (this EP changes only
  `TelegramService`'s own internal loop body, not any of its callers
  or wiring).
- `config/config.yaml` — untouched (no new configuration key; the fix
  introduces no new tunable).
- `docs/architecture/ARCHITECTURE_DEBT.md`, `CHANGELOG.md`,
  `docs/RELEASE_NOTES.md`, `docs/BACKLOG.md`,
  `docs/architecture/JARVIS_ROADMAP.md` — untouched during STEP 1/2
  (BACKLOG/RELEASE_NOTES/CHANGELOG updates are STEP 4 concerns, not
  STEP 1).
- Every EP-001 through EP-066 design and audit document — untouched.

The final STEP 2 implementation should modify only the two files named
in Section 12, plus create the new `tests/EP067/` package.

## 15. Validation Strategy

STEP 2/STEP 3 must run and report:

- The dedicated `tests/EP067/` suite (new).
- Directly affected existing tests:
  `tests/EP065/test_command_router_malformed_input.py` (the file whose
  own Telegram survival scenario overlaps in subject matter with this
  EP's own regression test — must remain 42/0/0, byte-identical file,
  unchanged results).
- Previous-EP regression suites for every other background-loop EP:
  `tests/EP061/`, `tests/EP062/`, `tests/EP063/`, `tests/EP064/`,
  `tests/EP066/`.
- The full project test runner (`TestRunner.run_all()`), to catch any
  unforeseen interaction.
- Protected-file verification: a full-repository diff against the
  pre-EP-067 baseline, confirming only the two files in Section 12
  changed (plus this design document and the new `tests/EP067/`
  package), exactly as EP-065's and EP-066's own STEP 3 audits
  performed.
- Baseline comparison for any pre-existing environmental failures:
  the EP046/EP048 voice-related suites are known, per EP-065's and
  EP-066's own STEP 3 audits, to be unable to execute in this
  environment (missing `vosk`/`sounddevice`/PortAudio), and EP047/
  EP049 are known to carry pre-existing, environment-specific
  failures unrelated to any EP's own code. STEP 2/STEP 3 must
  re-confirm these are unchanged by comparing against the untouched
  baseline, exactly as EP-065/EP-066 did, rather than attributing them
  to this EP.
- Final diff verification before STEP 3 sign-off.

## 16. Risks

- **Masking a genuinely fatal condition.** A broad `except Exception`
  could theoretically hide a serious, unrecoverable problem (e.g. the
  Telegram Bot API token becoming permanently invalid in a way not
  already surfaced through `TelegramClientError`) behind a log line
  instead of a crash. Mitigated by: this is exactly the same
  trade-off `SchedulerService`/`WorkflowSchedulerService`/
  `MemoryPersistence` already made and had independently audited
  (EP-061/EP-063/EP-066), and every currently-known Telegram Bot API
  failure mode is already `TelegramError`-derived and already
  converted to `TelegramClientError` by `TelegramClient` itself — the
  new branch only ever fires for exceptions *outside* that
  already-handled class.
- **Silent repeated failure without operator visibility.** If polling
  fails on every tick going forward (via the new, broader path), the
  poll loop now silently "runs" (thread alive, `TelegramStatus.running:
  True`) while never actually receiving messages, logging an error
  each time but not otherwise surfacing state beyond `telegram
  status`/`telegram doctor`, which an operator must proactively query.
  This is judged acceptable because it exactly matches
  `SchedulerService`'s own already-accepted behavior for a
  permanently-failing tick (EP-061), and is strictly better than the
  current behavior (thread silently dead, `running: False`, with no
  log evidence of why for any exception type this EP newly catches).
- **Test flakiness from thread timing.** Tests asserting "the loop
  continued past a failure" need a short polling interval and a
  bounded wait loop rather than a fixed `sleep`, following
  `tests/EP065/`'s own established pattern for its real-thread
  Telegram survival test, and `tests/EP066/`'s equivalent pattern for
  `MemoryPersistence`.

## 17. Deferred Items

- All Architecture Debt items (AD-001 through AD-009) — unchanged,
  reserved for a dedicated Architecture Cleanup milestone.
- Telegram Gateway shutdown coordination via `RuntimeService` —
  unchanged; still a distinct, larger concern from this EP's own
  narrow exception-containment fix (Section 7). With `tests/EP067/`
  now providing baseline `TelegramService` test coverage, a future EP
  investigating this candidate will have real fixtures to build on,
  removing one of the two reasons EP-063/EP-064/EP-065 each cited for
  rejecting it — but that investigation is explicitly not undertaken
  by EP-067 itself.
- REST API authentication — unchanged, still architecturally large.
- PluginLoader metadata-only-plugin status cross-checking — unchanged,
  still requires a multi-service constructor-injection change.
- Cron schedule support — unchanged, still a net-new feature.
