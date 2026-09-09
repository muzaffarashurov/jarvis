# EP-068 — CommandRouter Dispatch-Level Sensitive Argument Log Redaction

STEP 1: Architecture Discovery & Design

Status: DESIGN PROPOSED — awaiting Owner Decision approval before STEP 2

---

## 1. Title

EP-068 — CommandRouter Dispatch-Level Sensitive Argument Log Redaction

## 2. Problem Statement

`CommandRouter.dispatch()` (`src/core/command_router.py`) unconditionally
writes the **entire raw command line** — including every argument a
user typed — to the application log on two of its four exit paths:
a successful dispatch (line 184) and a module-raised exception (line
177). Because `dispatch()` is the single, shared entry point used by
`InteractiveShell`, `TelegramRouter`, and `ApiRouter` alike, this means
any command with a free-text argument that happens to be sensitive —
a password typed via `desktop type`, clipboard content sent via
`desktop write-clipboard`, an email body via `email send`, a commit
message via `git commit -m` — is written to the log file in full,
regardless of what the invoked module itself does internally.

This is not a new observation. It was identified, reproduced, and
recorded as a **HIGH**-severity finding during the EP-050 architecture
audit (`docs/architecture/audits/EP050_AUDIT.md`, Section 9 and
Section 22), specifically because EP-050's own design document made an
explicit, first-class "never logged" privacy commitment for typed text
and clipboard content that this pre-existing `CommandRouter` behavior
silently defeats end-to-end. The audit's own Section 23 recommended
follow-up explicitly named the three possible directions for a fix and
explicitly stated this is "exactly the kind of cross-cutting
`CommandRouter` change... requiring its own architectural decision, not
a unilateral EP-050 fix" — i.e., it was deliberately left for a future,
dedicated EP rather than folded into EP-050 or fixed unilaterally by
any single module. `docs/BACKLOG.md` has carried this exact item,
unaddressed, since EP-050:

> `CommandRouter.dispatch()` raw-input logging exposes sensitive
> command arguments in full (e.g. `desktop type`/`desktop
> write-clipboard`'s text) -- HIGH finding from `EP050_AUDIT.md`,
> deferred from EP-050 v1; needs its own architectural decision on how
> a `CommandModule` can mark specific actions as sensitive before this
> is fixed at the `CommandRouter` level

EP-065 (`CommandRouter Malformed-Input Dispatch Safety`) touched the
same file and the same method for a different, narrower defect
(unhandled `ValueError` from malformed quoting) and explicitly declined
to broaden or fix this pre-existing raw-input-echoing behavior at the
two sites this EP targets, treating them as an existing precedent left
"completely unmodified" outside its own scope (`EP065_DESIGN.md`
Section 6/D4). This finding has therefore now been independently
confirmed, deferred, and left untouched across two separate EPs and
their audits (EP-050, EP-065) and every EP since (EP-061 through
EP-067, none of which touched `CommandRouter.dispatch()`'s logging
calls). Direct re-reading of the current source (Section 3 below)
confirms both log lines are still present, unchanged, today.

## 3. Current Behavior

`CommandRouter.dispatch()` currently reads (line numbers as of the
current repository state, `src/core/command_router.py:131-186`):

```python
def dispatch(self, raw_input: str) -> CommandResult:
    try:
        tokens = self._tokenize(raw_input.strip())
    except ValueError as exc:  # noqa: BLE001 - malformed input must never crash a caller
        logger.error(f"Failed to parse command input: {exc}")
        return CommandResult(success=False, message=f"Invalid command syntax: {exc}")

    if not tokens:
        return CommandResult(success=False, message="")

    module_name, *rest = tokens
    module = self._modules.get(module_name.lower())

    if module is None:
        logger.info(f"Unknown module: {module_name}")
        message = (
            f"Unknown module: {module_name}\n"
            'Type "system help" for available commands.'
        )
        return CommandResult(success=False, message=message)

    action = rest[0].lower() if rest else ""
    arguments = rest[1:]

    try:
        result = module.execute(action, arguments)
    except Exception as exc:  # noqa: BLE001 - a module must never crash the shell
        logger.error(f"Error executing '{raw_input.strip()}': {exc}")
        return CommandResult(
            success=False,
            message=f"Internal error while executing '{raw_input.strip()}'.",
        )

    if result.success:
        logger.info(f"Command executed: {raw_input.strip()}")

    return result
```

Four distinct exit paths exist; two are already safe, two are not:

1. **Malformed quoting (`except ValueError`, line 150-151).** Already
   safe — EP-065 deliberately made this branch log only the parser's
   own short, fixed-vocabulary exception reason (e.g. `"No closing
   quotation"`), never `raw_input`. **Not part of this EP's problem;
   confirmed unchanged (Section 10, Protected Files).**
2. **Unknown module (line 163-164).** Logs `module_name` only — the
   first whitespace/quote-delimited token of the input, before any
   free-text argument content begins. This is a bounded, small-
   vocabulary value (whatever a user typed as a namespace, valid or
   not), not the kind of substantive free-text argument content the
   HIGH finding is about (a typed password, a clipboard value, an
   email body). **Not part of this EP's problem; confirmed unchanged
   (Section 10).**
3. **Module raises an exception (`except Exception`, line 174-177).**
   Logs `f"Error executing '{raw_input.strip()}': {exc}"` —
   the **entire raw command line**, including any argument content,
   unconditionally. **This is one of the two sites this EP fixes.**
4. **Successful dispatch (line 183-184).** Logs
   `f"Command executed: {raw_input.strip()}"` — again the entire raw
   command line, unconditionally, on every single successful command,
   regardless of module or action. **This is the other site this EP
   fixes.**

This is insufficient because `dispatch()` has no visibility into
whether a given module/action's arguments are safe to log (a `system
status` call is harmless; a `desktop type <password>` call is not),
and today it does not even try to distinguish them — it logs
everything, unconditionally, for every module. `DesktopModule` itself
already goes out of its way to avoid this exact problem internally
(`_type`/`_write_clipboard` log only a character count, confirmed
unchanged by direct reading of `src/skills/desktop/skill.py`), but that
module-level discipline is completely undermined because the shared
`CommandRouter.dispatch()` entry point every transport uses re-logs the
full original input regardless.

## 4. Architectural Context

`CommandRouter` (introduced pre-EP-061, most recently touched by
EP-065) is the single, shared dispatch point for every transport in
this repository — `InteractiveShell`, `TelegramRouter`, and `ApiRouter`
all call `CommandRouter.dispatch(raw_input)` and nothing else to
execute a command. This makes it the correct and only place to fix a
concern that applies uniformly across every module and every transport,
exactly as EP-065 already established for its own, narrower malformed-
quoting defect (Owner Decision D1 there: "the fix lives inside
`CommandRouter.dispatch()`... not in any individual `CommandModule`").
EP-068 follows the same architectural placement principle for a
different defect in the same method.

This EP does **not** touch `CommandRouter.dispatch()`'s parsing,
routing, or error-classification logic — only its logging calls at the
two sites identified in Section 3. It does not reopen EP-065's own
newly-added `except ValueError` branch (Section 3, exit path 1), which
is confirmed byte-identical before and after this design's proposed
change (Section 10).

This finding is architecturally distinct from the exception-
containment pattern established by EP-061/EP-063/EP-066/EP-067
(`SchedulerService._tick_loop()`, `WorkflowSchedulerService._tick_loop()`,
`MemoryPersistence._auto_save_loop()`, `TelegramService._poll_loop()`):
those four EPs each closed a gap in a background daemon thread's
resilience to an *unexpected exception* killing the thread silently.
This EP addresses a different architectural responsibility entirely —
what a *synchronous, request-scoped* dispatch call is permitted to
write to a shared log file — and does not touch, extend, or depend on
any of those four loops or their guards. No further loop-exception-
containment candidate was found during this EP's discovery (Section 5
documents the loops re-inspected and confirmed already covered).

## 5. Candidate Alternatives

Discovery re-read `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`,
`docs/architecture/ARCHITECTURE_DEBT.md` (in full), every EP-061 through
EP-067 design and audit document, and searched the source tree for
`TODO`/`FIXME`/`XXX` markers. Serious candidates considered:

**1. `CommandRouter.dispatch()` sensitive-argument log exposure (this
EP's selection).** Real, HIGH-severity, independently confirmed still
present by direct source reading. Distinct architectural responsibility
from the now-fully-closed loop-exception-containment pattern (Section
4). Bounded to one file, two log call sites. Fully testable in pure
Python with no OS-specific or hardware dependency. Not recorded in
`ARCHITECTURE_DEBT.md`, so not categorically excluded by that
document's own governance rule.

**2. `WindowsComputerUseBackend.active_window_title()` swallowing all
exceptions into `""` instead of distinguishing "no active window" from
a genuine backend failure** (MEDIUM finding, same EP-050 audit, Section
17/23). Real and still open — confirmed present by direct reading of
`src/skills/desktop/windows_backend.py:205-217`. Rejected for now:
(a) lower severity (MEDIUM vs. HIGH); (b) this backend is Windows-only
and depends on `pyautogui`/Win32 APIs not present in this Linux
sandbox — the repository's own existing convention
(`tests/EP050/test_desktop_windows_integration.py`) deliberately keeps
all real `WindowsComputerUseBackend` verification in a manual,
un-registered, real-hardware-only tier specifically because it cannot
be exercised in an automated/headless environment; a STEP 2 for this
candidate would produce materially weaker independent test evidence
than the CommandRouter candidate, which needs no such carve-out.

**3. Architecture Debt items (AD-001, AD-002, AD-003, AD-005 through
AD-009).** All real, all previously investigated by multiple prior EPs
(EP-063 through EP-067 discovery sections each re-confirm this
exclusion). `docs/architecture/ARCHITECTURE_DEBT.md`'s own governance
rule — "Never fix Architecture Debt during a normal Engineering Phase"
— categorically excludes every one of these regardless of individual
merit. Re-confirmed unchanged and still open by direct reading of that
document during this EP's own discovery.

**4. REST API authentication/authorization.** Real, repeatedly
disclosed (named in EP-064 through EP-067's own discovery sections),
architecturally large — spans every REST endpoint, credential storage,
and configuration. Continues to be deferred by every EP that has
encountered it.

**5. `PluginLoader` metadata-only-plugin status-bookkeeping TODO.**
Real, but its own TODO comment (`src/core/plugins/plugin_loader.py:214-222`)
already explains why it is out of scope: requires injecting one of
`ProcessService`/`InvoiceService`/`FastResponseService` into
`PluginLoader`/`PluginService`, a multi-service constructor-injection
change spanning several services.

**6. Cron schedule support (`Scheduler.calculate_next_run`,
`WorkflowSchedulerEngine`'s `ScheduleType.CRON` branch).** Both remain
interface-only since EP-011. A net-new feature (a cron expression
parser), not a bounded architecture fix.

**7. Telegram Gateway shutdown coordination.** The same candidate
independently investigated and rejected by EP-063, EP-064, EP-065, and
EP-067 in turn, for reasons unrelated to this EP's own selection (a
manual `telegram stop` escape hatch already exists; process-level
shutdown-orchestration scope, not a per-call logging concern).

Candidate 1 is selected: it is the only candidate that is simultaneously
(a) not recorded Architecture Debt subject to the repository's own
fix-timing rule, (b) not architecturally large, (c) not a multi-service
wiring change, (d) not a net-new feature, (e) not something already
carrying a documented test-evidence limitation in this sandbox, and
(f) HIGH severity with a clear, explicitly-recommended fix direction
already sketched by a prior audit.

## 6. Owner Decisions

**D1 — Where does the fix live?** Exactly inside
`CommandRouter.dispatch()`, at the two log call sites identified in
Section 3 as exit paths 3 and 4 (the `except Exception` handler around
`module.execute()`, and the post-`if result.success:` success log). No
other method, and no other exit path within `dispatch()` itself
(exit paths 1 and 2, Section 3), is touched.

**D2 — What replaces the raw-input echo?** Both log lines change from
logging `raw_input.strip()` (the full command line, including every
argument) to logging only `module_name` and `action` — the two already-
parsed, small-vocabulary tokens that identify *which* command ran, never
`arguments` (the free-text portion where sensitive content lives) and
never any value derived from `arguments`. This mirrors EP-065's own
established convention (`EP065_DESIGN.md` D4: log "a short, fixed...
safe, deterministic description," never raw content) and
`DesktopModule`'s own convention of logging only structural metadata
(a character count) rather than content — applied here at the shared
`CommandRouter` layer instead of duplicated per-module.

**D3 — Exact new log wording.**
Success path: `f"Command executed: {module_name} {action}".rstrip()`
(the `.rstrip()` handles the module-only case where `action` is `""`,
e.g. a bare `system` command, without leaving a trailing space).
Exception path: `f"Error executing '{module_name} {action}'.rstrip()"`
is refactored into
`f"Error executing '{(module_name + ' ' + action).rstrip()}': {exc}"`
so the quoted portion never includes argument content either. `str(exc)`
is preserved in the exception-path message exactly as before (a
module's own exception message is that module's responsibility, not
`CommandRouter`'s, and is unaffected by this EP — Non-Goals, Section
7).

**D4 — Is the returned `CommandResult.message` (as opposed to the log
line) changed?** No. The message returned to the caller on a module
exception (`f"Internal error while executing '{raw_input.strip()}'."`)
is left completely unchanged. The HIGH finding (Section 2) is
specifically about content reaching a persistent, potentially
differently-audienced **log file** — the returned message goes back to
the exact same session (console, Telegram chat, or API caller) that
already supplied the input, so it discloses nothing to a new audience.
Changing it is outside this EP's bounded scope and was not part of the
finding as documented.

**D5 — Is the "Unknown module" log line (exit path 2, Section 3)
touched?** No. It logs only `module_name`, the first token of the
input, before any free-text argument content begins — not the kind of
substantive argument content (a password, a clipboard value, a message
body) the HIGH finding is about. Left unchanged.

**D6 — Is EP-065's `except ValueError` branch (exit path 1, Section 3)
touched?** No. Already safe by EP-065's own design (D4 there); this EP
does not modify, reopen, or extend it in any way.

**D7 — Is a new "mark this action as sensitive" mechanism introduced
on `CommandModule`?** No. This was Option (a) in EP-050's own audit
Section 23 recommendation and is explicitly rejected here as
oversized for one bounded EP — it would require extending the
`CommandModule` Protocol (or an equivalent registration mechanism) and
updating or auditing every existing module to consider whether any of
its actions should be marked. Instead, this EP applies the simpler,
strictly safer default (Option (b) from that same Section 23 list):
`CommandRouter` never logs argument content for *any* module, with no
per-module opt-in/opt-out surface. This closes the HIGH finding for
every current and future module uniformly, at the cost of the log no
longer showing full argument content even for commands whose arguments
are harmless (e.g. `system status`) — accepted as the correct trade-off
per D8.

**D8 — Trade-off accepted: log verbosity vs. safety.** After this
change, the log records *that* a command ran (module + action) but not
*what* it was called with, for every module, including modules whose
arguments were never sensitive. This is a deliberate, uniform reduction
in the CommandRouter-level log's granularity, matching Option (c)'s
concern from EP-050's audit ("accept... a known, documented limitation")
resolved in the opposite direction: this EP does not merely document
the limitation, it removes it at the cost of some log detail, judged an
acceptable trade-off because (a) `CommandResult.message` and downstream
per-transport logging (e.g. `InteractiveShell`, `TelegramRouter`) remain
completely unaffected — an operator or user still sees the command's
outcome; (b) a module that wants richer telemetry can already log its
own bounded, safe metadata internally, exactly as `DesktopModule` does
today; (c) no test or design document was found requiring full
argument-level detail in the `CommandRouter`-level log specifically.

**D9 — Files allowed to change.** Exactly one production file:
`src/core/command_router.py` (only the two log statements identified in
D1/D3), plus `src/modules/test_module.py` (one new import line for
`tests.EP068`, per the established convention). No other production
file changes.

**D10 — Test placement.** A new, dedicated, self-contained `tests/EP068/`
package, per this repository's now-consistently-applied convention
(`tests/EP061/` through `tests/EP067/`).

**D11 — No new public API.** No new method, no new `CommandResult`
field, no new `CommandModule` Protocol member, no new configuration key.
`dispatch()`'s signature and return type are unchanged.

**D12 — Deferred items remain untouched.** The MEDIUM finding
(`WindowsComputerUseBackend.active_window_title()`), every open
Architecture Debt item, REST API authentication, the `PluginLoader`
status-sync TODO, cron schedule support, and Telegram Gateway shutdown
coordination all remain explicitly deferred and untouched (Section 5,
Section 11).

## 7. Scope

### In scope

- `src/core/command_router.py` — `dispatch()`'s two log statements
  (currently lines 177 and 184) changed per D2/D3. No other line in
  this file changes.
- `src/modules/test_module.py` — exactly one new import line
  registering `tests.EP068`, appended after the existing
  `tests.EP067...` line.
- `tests/EP068/__init__.py` — new, empty, per convention.
- `tests/EP068/test_command_router_log_redaction.py` (exact name to be
  finalized in STEP 2) — new, self-contained, `NAME = "EP068"`.
- `docs/architecture/designs/EP068_DESIGN.md` — this document.

### Out of scope

- `dispatch()`'s parsing (`_tokenize`), routing, module-lookup, or
  `except ValueError` logic (exit paths 1 and 2, Section 3) — all
  unchanged (D5/D6).
- The returned `CommandResult.message` on any exit path — unchanged
  (D4).
- Any individual `CommandModule`'s own internal logging (e.g.
  `DesktopModule`'s existing character-count logging) — unchanged; no
  module file is modified by this EP.
- A per-module "mark this action as sensitive" mechanism (D7) —
  explicitly rejected as oversized for this EP.
- The MEDIUM finding (`WindowsComputerUseBackend.active_window_title()`),
  any Architecture Debt item, REST API authentication, the
  `PluginLoader` status-sync TODO, cron schedule support, and Telegram
  Gateway shutdown coordination (D12).
- `InteractiveShell`, `TelegramRouter`, `TelegramClient`, `ApiRouter`,
  `RestApiServer`, or any other transport-layer file — none call
  `logger` with `raw_input` themselves (confirmed by direct reading);
  none require any change.

## 8. Implementation Plan

Two, and only two, statements inside `CommandRouter.dispatch()` change:

1. The exception-path log call (currently
   `logger.error(f"Error executing '{raw_input.strip()}': {exc}")`,
   inside the `except Exception as exc:` block around
   `module.execute()`) is replaced with a version that logs
   `module_name` and `action` in place of `raw_input.strip()`, per D2/D3.
   The returned `CommandResult` on this path is unchanged (D4).
2. The success-path log call (currently
   `logger.info(f"Command executed: {raw_input.strip()}")`, inside the
   `if result.success:` block) is replaced with a version that logs
   `module_name` and `action` in place of `raw_input.strip()`, per
   D2/D3.

No other statement, branch, docstring behavior, or control-flow path in
`dispatch()` changes. `_tokenize()`, `register()`, `register_modules()`,
and `module_names` are untouched. STEP 2 must confirm, via direct diff
against the pre-EP-068 baseline, that no other line in
`src/core/command_router.py` differs.

## 9. Testing Strategy

New package: `tests/EP068/`, self-contained (no import from
`tests/EP061/` through `tests/EP067/`), `NAME = "EP068"`, registered via
exactly one new import line in `src/modules/test_module.py`.

STEP 2 tests must verify, using a real `CommandRouter` with real,
minimal stub `CommandModule` implementations (no network, no real
Telegram/REST transport) and a real `loguru` capture sink (not a mock):

- **Normal behavior — success path redaction.** Dispatch a command with
  a distinctive, sensitive-looking marker argument (e.g.
  `"stub speak MySecretMarker123"`) that succeeds; assert the captured
  log contains `module_name`/`action` (`"stub"`/`"speak"`) but does
  **not** contain the marker string anywhere in any captured log line.
- **Failure behavior — exception path redaction.** Register a stub
  module whose `execute()` raises an exception when called with a
  distinctive marker argument; dispatch it; assert the captured log's
  `"Error executing"` line contains `module_name`/`action` and the
  exception's own `str(exc)`, but does **not** contain the marker
  argument string anywhere in any captured log line.
- **Regression — returned message unchanged on exception.** Confirm
  the returned `CommandResult.message` for the exception path still
  reads `f"Internal error while executing '{raw_input.strip()}'."`
  (i.e., D4's "returned message is unchanged" decision holds) — this is
  a deliberate, explicit regression check that this EP's fix is
  logging-only, not response-content redaction.
- **Regression — module-only command (no action).** Dispatch a
  bare module name with no action/arguments (e.g. `"system"`); assert
  the new success/log message formatting does not produce a malformed
  string (e.g. a trailing space) and the command still dispatches
  exactly as before.
- **Regression — "Unknown module" path unchanged.** Confirm dispatching
  an unregistered module name still logs `f"Unknown module: {module_name}"`
  exactly as before (D5) — a fixed regression check that this EP's
  change did not accidentally spread into this branch.
- **Regression — malformed-quoting path unchanged.** Confirm dispatching
  a line with an unbalanced quote still logs only the parser's own
  exception reason (e.g. `"No closing quotation"`), never the raw input
  — reconfirming EP-065's own, still-unmodified behavior (D6) is
  unaffected by this EP.
- **Regression — non-sensitive commands still dispatch correctly.**
  Confirm an ordinary, harmless command (e.g. a stub module's
  `"status"` action) still returns the expected `CommandResult` and
  still produces a `"Command executed: ..."` log line (containing
  `module_name`/`action`, not asserting its *absence*, to prove this EP
  reduces detail rather than breaking the log entirely).
- **Logging severity/channel unchanged.** Confirm the exception path
  still logs at `ERROR` and the success path still logs at `INFO`,
  matching current behavior exactly — only the message content changes,
  not the severity.

Protected/regression suites to re-run unchanged at STEP 2/STEP 3:
`tests/EP065/test_command_router_malformed_input.py` (the suite most
directly adjacent to this EP's own file and method), plus
`tests/EP061/`, `tests/EP062/`, `tests/EP063/`, `tests/EP064/`,
`tests/EP066/`, `tests/EP067/`, and the full project suite.

## 10. Protected Files

At minimum:

- `tests/EP061/` through `tests/EP067/` (every file) — untouched.
- `src/services/scheduler_service.py`,
  `src/services/workflow_scheduler_service.py`,
  `src/core/memory/memory_persistence.py`,
  `src/services/telegram_service.py`,
  `src/core/telegram/telegram_client.py`,
  `src/core/telegram/telegram_router.py`,
  `src/modules/telegram_module.py`,
  `src/core/api/api_router.py`, `src/core/api/rest_api_server.py`,
  `src/core/api/dto.py`, `src/core/shell.py` — untouched.
- Every individual `CommandModule` implementation (`src/modules/*.py`,
  `src/skills/*/skill.py`, including `src/skills/desktop/skill.py`) —
  untouched; this EP fixes the shared dispatch layer, not any module.
- `src/skills/desktop/windows_backend.py`,
  `src/skills/desktop/backend.py` — untouched (D12).
- `config/config.yaml` — untouched; no new configuration key.
- `docs/architecture/ARCHITECTURE_DEBT.md`, `CHANGELOG.md`,
  `docs/RELEASE_NOTES.md`, `docs/BACKLOG.md`,
  `docs/architecture/JARVIS_ROADMAP.md` — untouched during STEP 1/2
  (STEP 4 concerns).
- Every EP-001 through EP-067 design and audit document — untouched.

## 11. Deferred Items

- `WindowsComputerUseBackend.active_window_title()`'s overly broad
  exception handling (MEDIUM, EP-050 audit) — remains open, reserved
  for a future EP with access to real Windows hardware or a suitable
  mocking strategy for its automated test coverage.
- Every Architecture Debt item (AD-001, AD-002, AD-003, AD-005 through
  AD-009) — unchanged, reserved for a dedicated Architecture Cleanup
  milestone.
- REST API authentication — unchanged, still architecturally large.
- `PluginLoader` metadata-only-plugin status cross-checking —
  unchanged, still requires a multi-service constructor-injection
  change.
- Cron schedule support — unchanged, still a net-new feature.
- Telegram Gateway shutdown coordination — unchanged, a distinct,
  larger, still-separately-deferred concern (Section 5, Candidate 7).
- A per-module "mark this action as sensitive" mechanism (D7) —
  explicitly rejected in favor of a simpler, uniform default; may be
  revisited in a future EP if a real need for selective, richer
  argument logging emerges.

## 12. Acceptance Criteria

STEP 2/STEP 3/STEP 4 may verify completion against the following,
objective criteria:

1. `src/core/command_router.py`'s two identified log statements
   (Section 3, exit paths 3 and 4) no longer include `raw_input` or any
   value derived from `arguments`; both now include only `module_name`
   and `action`, per D2/D3.
2. A full-file diff of `src/core/command_router.py` against the
   pre-EP-068 baseline shows changes confined to those two statements
   only — `_tokenize()`, `register()`, `register_modules()`,
   `module_names`, and the two other exit paths (D5/D6) are
   byte-identical.
3. `CommandResult.message` returned on the exception path is
   byte-identical to the pre-EP-068 baseline (D4).
4. A dedicated, freshly-authored test using a real `loguru` capture
   sink and a distinctive marker argument demonstrates the marker is
   absent from every captured log line on both the success and
   exception paths.
5. `tests/EP068/` exists, is self-contained (no cross-EP import),
   registers `NAME = "EP068"`, and is imported exactly once from
   `src/modules/test_module.py`.
6. All EP-068 tests pass; `tests/EP065/`'s existing suite (the file
   most directly adjacent to this change) and all of `tests/EP061/`
   through `tests/EP067/` reproduce their own established baselines
   exactly, with zero regressions.
7. A full-repository diff against the pre-EP-068 baseline shows exactly
   the files listed in Section 7 ("In scope") and nothing else.
8. No Architecture Debt item, and none of the other deferred candidates
   in Section 11, is touched.
