# EP-065 Architecture Audit — CommandRouter Malformed-Input Dispatch Safety

Audit performed: STEP 3, independently, against the actual current
repository state (no `.git` metadata is present in this repository, so
the untouched original uploaded archive was used as the independent
baseline for every "unchanged" claim below). This audit does not
accept the STEP 2 report's claims at face value; every finding below
was independently re-derived by re-reading the approved design,
re-reading the actual implementation and test files byte-for-byte
against the untouched baseline, independently re-executing the
dedicated EP-065 suite plus the mandated regression suites, and
independently constructing fresh runtime checks (a module that raises
`ValueError`, a fresh sensitive-marker string, a fresh fake Telegram
client, and fresh adversarial REST arguments) rather than re-running
STEP 2's own test file as the sole evidence source.

---

## 1. Audit Scope

Files independently re-inspected in full during this audit:

- `docs/architecture/designs/EP065_DESIGN.md` (complete re-read)
- `src/core/command_router.py` (complete re-read, all 195 lines)
- `src/modules/test_module.py` (registration line, diffed against baseline)
- `tests/EP065/__init__.py` (confirmed empty, matching convention)
- `tests/EP065/test_command_router_malformed_input.py` (complete re-read, all 442 lines, all 17 test methods)
- `tests/EP002/test_shell.py` (diffed against baseline; confirmed unmodified)
- `src/core/shell.py` (`InteractiveShell.run()`, `_display_result()`)
- `src/services/telegram_service.py`, `src/core/telegram/telegram_router.py`, `src/core/telegram/telegram_client.py`, `src/modules/telegram_module.py` (diffed against baseline; confirmed unmodified)
- `src/core/api/api_router.py`, `src/core/api/rest_api_server.py`, `src/core/api/dto.py` (diffed against baseline; confirmed unmodified)
- `src/bootstrap.py`, `src/main.py`, `src/services/memory_service.py`, `src/core/memory/memory_persistence.py`, `src/services/workflow_scheduler_service.py`, `src/services/runtime_service.py`, `config/config.yaml`, `docs/architecture/ARCHITECTURE_DEBT.md`, `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`, and every `tests/EP0XX/` file for EP002/EP043/EP051/EP052/EP059-EP064 (diffed against baseline; confirmed byte-identical)

Independent test execution performed during this STEP 3 (not inherited
from the STEP 2 report):

| Suite | Passed | Failed | Skipped | Independently re-run in STEP 3? |
|---|---|---|---|---|
| EP065 (dedicated) | 42 | 0 | 0 | Yes |
| EP002 | 21 | 0 | 0 | Yes |
| EP043 | 83 | 0 | 0 | Yes |
| EP051 | 105 | 0 | 0 | Yes |
| EP052 | 135 | 0 | 0 | Yes |
| EP059 | 93 | 0 | 0 | Yes |
| EP060 | 65 | 0 | 0 | Yes |
| EP061 | 62 | 0 | 0 | Yes |
| EP062 | 39 | 0 | 0 | Yes |
| EP063 | 78 | 0 | 0 | Yes |
| EP064 | 93 | 0 | 0 | Yes |
| Full suite (`TestRunner.run_all()`, every registered EP) | 6,917 | 3 (pre-existing, independently reproduced on the untouched baseline) | 1 (pre-existing, same) | Yes |

Additionally, five fresh, STEP-3-authored runtime checks were executed
directly against the live repository (not reused from
`tests/EP065/`), specifically to independently verify the critical
exception-boundary claim, the raw-input-leakage claim, the
malformed-quoting-variant claim, the Shell-survival claim, the
Telegram-survival claim, and the REST-immunity claim — see Sections 5
and 7 below for each script and its result.

---

## 2. Design Baseline

`docs/architecture/designs/EP065_DESIGN.md` was re-read in full
(1,593 lines, all 17 sections plus the Section-7 Owner Decisions
D1-D10). No inconsistency was found between the final, revised design
and the implementation described below — every Owner Decision's
"Architectural consequence" clause matches the actual code exactly
(see Section 4).

---

## 3. Implementation Inspection

`src/core/command_router.py` was read in full (195 lines) and
independently diffed against the untouched original baseline:

```
--- original
+++ current
@@ -140,9 +140,20 @@
         Returns:
             A CommandResult describing the outcome of execution. Returns
-            an empty, unsuccessful result for blank input.
+            an empty, unsuccessful result for blank input. Malformed
+            quoting (e.g. an unbalanced quote character) is likewise
+            returned as an unsuccessful CommandResult rather than
+            raising -- see the `except ValueError` block below.
         """
-        tokens = self._tokenize(raw_input.strip())
+        try:
+            tokens = self._tokenize(raw_input.strip())
+        except ValueError as exc:  # noqa: BLE001 - malformed input must never crash a caller
+            logger.error(f"Failed to parse command input: {exc}")
+            return CommandResult(
+                success=False,
+                message=f"Invalid command syntax: {exc}",
+            )
+
         if not tokens:
             return CommandResult(success=False, message="")
```

This is the entire diff. No other line in the 195-line file changed.
`_tokenize()` (lines 106-129), `register()`, `register_modules()`,
`CommandResult`, `CommandModule`, `module_names`, and the
`module.execute()` exception handler (lines 174-181) are confirmed
byte-identical to the original by direct `diff` of the surrounding
line ranges.

`src/modules/test_module.py` was independently diffed:

```
--- original
+++ current
@@ -63,6 +63,7 @@
 import tests.EP062.test_background_worker_status
 import tests.EP063.test_workflow_scheduler_shutdown
 import tests.EP064.test_memory_persistence_shutdown
+import tests.EP065.test_command_router_malformed_input
```

Exactly one new line, appended in the established position. No other
line changed.

---

## 4. Owner Decisions D1-D10

### D1 — Guard lives inside `CommandRouter.dispatch()`
**PASS.** The `try/except ValueError` block wraps only
`self._tokenize(raw_input.strip())` at line 149, inside `dispatch()`
itself. No transport file (`InteractiveShell`, `TelegramRouter`,
`ApiRouter`) contains any new guard — confirmed byte-identical to
baseline (Section 7).

### D2 — `_tokenize()` remains unchanged
**PASS.** Independently diffed lines 106-129 against the original
baseline: zero differences (`bash -c 'diff <(sed -n "106,129p" orig) <(sed -n "106,129p" current)'` produced no output). Independently
re-confirmed at runtime: `CommandRouter._tokenize('bad "quote')`
still raises `ValueError: No closing quotation` directly, uncaught,
when called outside of `dispatch()`.

### D3 — Distinct syntax-error message
**PASS.** Independently dispatched `'nosuchmodule help'` and
`'login "unbalanced'` through a fresh `CommandRouter`: the two
returned messages differ (`"Unknown module: nosuchmodule\n..."` vs.
`"Invalid command syntax: No closing quotation"`); the malformed-input
message does not start with "Unknown module" and does not contain
"Internal error". Wording is deterministic — five different malformed
variants (unmatched `"`, unmatched `'`, bare `"`, bare `'`, three
non-pairing quotes) each independently produced the exact same
message text, `"Invalid command syntax: No closing quotation"`.

### D4 — No raw command text in message or logs
**PASS.** Independently constructed a fresh sensitive marker
(`XYZZY-AUDIT-MARKER-99887766`, not reused from STEP 2's test file)
and dispatched `login "XYZZY-AUDIT-MARKER-99887766` through a fresh
`CommandRouter` with a live `loguru` sink attached. Result:
`CommandResult.message == "Invalid command syntax: No closing
quotation"` — the marker is absent from the message. The captured log
line was `"Failed to parse command input: No closing quotation"` —
the marker is absent from the log as well. Only the parser's own
fixed-vocabulary reason (`"No closing quotation"`) appears in either
sink, confirmed by both a positive assertion (`"No closing quotation"
in ...`) and a negative assertion (`marker not in ...`) in this
audit's own independent script, not merely reused from
`tests/EP065/`'s own equivalent test.

### D5 — Logging severity matches convention
**PASS.** The captured log record from the D4 check above shows level
`ERROR`, matching the sibling `module.execute()` handler's own
`logger.error(...)` call three lines below it (also independently
confirmed present and unchanged in Section 3's diff).

### D6 / D7 — Shell, Telegram, REST production files unchanged for this specific defect
**PASS**, narrowly scoped exactly as instructed — this audit makes no
claim that Shell, Telegram, or REST are generally exception-safe.
`src/core/shell.py`, `src/services/telegram_service.py`,
`src/core/telegram/telegram_router.py`,
`src/core/telegram/telegram_client.py`, `src/modules/telegram_module.py`,
`src/core/api/api_router.py`, `src/core/api/rest_api_server.py`, and
`src/core/api/dto.py` were each independently `diff`'d against the
untouched baseline and are byte-identical (Section 9). The
EP-065-specific claim — that this one, specific `ValueError` no longer
escapes through any of these three transports — was independently
verified at runtime for all three (Sections 6-8).

### D8 — No new exception type or `error_code` field
**PASS.** `CommandResult`'s dataclass definition (`success: bool`,
`message: str`, `should_exit: bool = False`) is unchanged (contained
within the byte-identical, untouched surrounding lines confirmed in
Section 3). No new exception class appears anywhere in
`src/core/command_router.py`'s diff. The new branch reuses
`CommandResult(success=False, message=...)` exactly, with no new
field.

### D9 — Deferred issues remain untouched
**PASS.** `src/core/memory/memory_persistence.py` (EP064-F1),
`src/services/workflow_scheduler_service.py` (AD-001),
`docs/architecture/ARCHITECTURE_DEBT.md`, and every Telegram file
(including the narrower `except TelegramClientError` guards inside
`telegram_service.py`'s `_poll_once()`, independently re-read and
confirmed still present, unwidened) are all confirmed byte-identical
to the untouched baseline (Section 9). No REST authentication code
exists anywhere in the diff.

### D10 — Dedicated, self-contained `tests/EP065/` package
**PASS.** `tests/EP065/__init__.py` exists and is empty (0 bytes),
matching `tests/EP061/__init__.py` through `tests/EP064/__init__.py`
exactly. `tests/EP065/test_command_router_malformed_input.py` contains
zero `import tests.` statements referencing any other EP package
(`grep -c "import tests\."` on the file returned `0`), confirming
genuine self-containment — its only local fixtures
(`_RecordingModule`, `_RaisingModule`, `_ExitOnCommandModule`,
`_FakeTelegramClient`) are independent, EP-065-owned definitions, not
imports from `tests/EP002/` or elsewhere. The suite registers under
`NAME = "EP065"` via `@TestRegistry.register`, and
`src/modules/test_module.py` was confirmed (Section 3) to contain
exactly one new import line for it, in the established position.

**D1-D10 summary: 10/10 PASS.**

---

## 5. Exception-Boundary Analysis (critical check)

The `try` block at line 148 contains exactly one statement:
`tokens = self._tokenize(raw_input.strip())`. It is closed by its
`except ValueError` at line 150 and the block ends at line 155. The
call to `module.execute()` occurs 19 lines later, at line 175, inside
a **structurally separate** `try` block (lines 174-181) with its own,
independent `except Exception` clause. The two blocks share no code
and cannot interact — a `ValueError` raised inside `module.execute()`
is physically outside the lexical scope of the first `except
ValueError` clause by the time control reaches it.

This was independently verified at runtime, not merely by static
reading. A fresh module was registered whose `execute()` deliberately
raises `ValueError` (a stricter test than the design's own suite,
which does not specifically test a `ValueError` from `module.execute()`
— see Finding F1 below):

```python
class RaisesValueErrorModule:
    @property
    def name(self): return 'vmod'
    def execute(self, action, arguments):
        raise ValueError('deliberate ValueError from module.execute()')

router.register(RaisesValueErrorModule())
result = router.dispatch('vmod dothing')
# result.success == False
# result.message == "Internal error while executing 'vmod dothing'."
```

**Result: PASS.** The module-raised `ValueError` took the pre-existing
`"Internal error while executing '...'."` path — the exact same
wording and behavior as before this EP, confirmed byte-for-byte
against the design's own documented pre-existing convention — and did
**not** produce `"Invalid command syntax: ..."`. The new handler does
not broaden exception swallowing: it is registered against a single,
specific call expression, not against any wider span of `dispatch()`'s
body.

**Conclusion: the exception boundary is exactly as narrow as approved.
No broadening found.**

---

## 6. Security / Raw-Input Exposure — Independent Verification

Repeated independently with a fresh marker string not present in
`tests/EP065/`'s own test (`XYZZY-AUDIT-MARKER-99887766` vs. the
suite's own `sk-super-secret-marker`), against both the returned
`CommandResult.message` and a live `loguru` capture sink attached for
the duration of the call only. Full script and result reproduced in
Section 4, D4 above. **PASS** — the marker appeared in neither sink;
only `"No closing quotation"` appeared in both.

Five malformed variants (unmatched `"`, unmatched `'`, bare `"`, bare
`'`, three non-pairing quotes, and one mixed `"`/`'` variant) were
each independently dispatched; all six produced the byte-identical
message `"Invalid command syntax: No closing quotation"`, confirming
the wording is deterministic and independent of which specific
characters triggered the parse failure — no variant leaked any part of
itself into the message.

---

## 7. Shell / Telegram / REST Verification — Independent

### Shell
`src/core/shell.py` confirmed byte-identical to baseline (Section 9).
A fresh, STEP-3-authored script (not `tests/EP065/`'s own shell test)
patched `builtins.input` to yield `'bad "input here'` then `'sys
exit'`, against a real `InteractiveShell`/`CommandRouter`/a
fresh exit-requesting stub module. `shell.run()` returned normally
(no exception); the stub module's `execute()` was called exactly once
— for the second line — independently proving the loop survived and
continued past the malformed first line. **PASS.**

### Telegram
All four Telegram production files confirmed byte-identical to
baseline (Section 9). A fresh, STEP-3-authored script built a real
`TelegramService`/`TelegramRouter`/`CommandRouter` with a
freshly-written fake client (distinct from `tests/EP065/`'s own
`_FakeTelegramClient`), queued a malformed message followed by a
well-formed one across two poll cycles (`polling_interval=0.03`, a
different interval than the suite's own `0.05`, to avoid any
possibility of coincidental timing coupling), and polled
`service.status().running` after both cycles completed. **Result:
`running == True`; both messages produced a reply; the first reply
started with `"Invalid command syntax:"` and did not contain
`"unbalanced"`; the second reply was the expected `"pong"` from the
echo module.** This independently confirms the poll thread survives
this specific defect and continues correct operation afterward, using
a script and inputs distinct from STEP 2's own test. **PASS.**

### REST
All three REST production files confirmed byte-identical to baseline
(Section 9). A fresh, STEP-3-authored script dispatched five
adversarial argument values (`'oops"unbalanced'`, `"oops'unbalanced"`,
`'"'`, `"'"`, `'a"b\'c'` — a broader set than `tests/EP065/`'s own
single-value REST test) through a real `ApiRouter.dispatch_command()`.
All five succeeded without raising, and in every case the module
received the argument's exact original text, confirming
`shlex.quote()`'s round-trip is both safe and lossless for a wider
adversarial set than the approved suite itself exercises. **PASS.**
No REST-specific behavior was introduced by this EP; the immunity is
a pre-existing structural property of `ApiRouter.dispatch_command()`'s
own escaping, confirmed unchanged.

---

## 8. Test Adequacy

`tests/EP065/test_command_router_malformed_input.py`'s 17 test methods
were read individually, not merely counted:

**Genuine, behavior-grounded tests (no tautologies or mock-only assertions found):**
- `_test_tokenize_still_raises_valueerror_directly` — directly re-verifies D2 against the live method, not merely inferred from `dispatch()`'s behavior.
- The four `_test_dispatch_never_raises_for_*` methods each independently exercise a distinct malformed-quoting shape (trailing double, trailing single, bare character, multi-quote) rather than one shape asserted four times under different names.
- `_test_malformed_input_does_not_log_raw_command_text` uses a real `loguru.add()` sink capturing genuine emitted records — not a mock of the `logger.error` call — a materially stronger test than asserting a mock was "called with" a particular string, since it proves the record actually reaches loguru's pipeline.
- `_test_malformed_input_never_calls_module_execute` and `_test_repeated_malformed_input_is_idempotent` use a real, call-recording `CommandModule`, not a mock — genuine behavioral proof, not an implementation-detail assertion.
- `_test_internal_error_path_unchanged_and_still_echoes_raw_input` is a well-designed contrast test: it positively re-asserts the *sibling* handler's raw-input-echoing behavior is unchanged, which indirectly strengthens confidence that the new branch's no-echo behavior (D4) is a deliberate, isolated choice rather than an accidental side effect of a broader refactor.
- The Shell test's only use of `unittest.mock` is to patch `builtins.input` — mocking the unavoidable external I/O boundary, not the unit under test — and its assertion (`exit_module.calls == 1`) is a genuine behavioral proof of continuation, not a call-count-only tautology, since the module is a real, executable `CommandModule`.
- The Telegram test constructs real `TelegramService`, `TelegramRouter`, and `CommandRouter` instances and fakes only the one genuine external boundary (`TelegramClient`), following this repository's own established fake-backend convention; its wait loop uses a bounded deadline rather than a blind `sleep`, and its final assertions inspect actual message content (`.startswith`, `not in`) rather than only call counts.
- The REST test similarly uses real objects throughout and asserts on the exact argument value received by the target module, not merely that `dispatch_command()` "did not raise."

**Non-blocking gaps identified (see Findings F1-F2):**
- No test in `tests/EP065/` specifically feeds a `ValueError` (as opposed to a generic `Exception`, which `_RaisingModule` uses) into `module.execute()` to prove the new handler cannot mis-catch it — this exact scenario was independently verified by this audit (Section 5) but is not itself present in the approved suite. **Finding F1.**
- No test in `tests/EP065/` re-asserts `CommandRouter.dispatch("")`/`dispatch("   ")` (blank-input) behavior; this is still covered by the untouched `tests/EP002/test_shell.py` (re-run as regression, Section 10) but is not duplicated in EP-065's own suite. **Finding F2.**

Neither gap affects implementation correctness — both scenarios were
independently exercised by this audit directly against the live code
(Section 5 for the first; the unmodified `tests/EP002/` suite,
independently re-run with 21/21 passing, for the second) and both
pass. Both findings are **non-blocking** documentation/coverage
observations, not correctness defects.

---

## 9. Protected-File Verification

Independently diffed (bytecode caches excluded) against the untouched
original archive:

```
$ diff -rq orig/jarvis-main work/jarvis-main
Only in work/.../docs/architecture/designs: EP065_DESIGN.md
Files .../src/core/command_router.py differ
Files .../src/modules/test_module.py differ
Only in work/.../tests: EP065
```

**Exactly four differences, matching the approved STEP 1/STEP 2 scope
precisely: one pre-existing design doc (from STEP 1, not a STEP 2
implementation change), the two approved production files, and the
new test package.** No other file anywhere in the repository differs.

Explicit, individual re-verification (not just the aggregate `diff
-rq`) was additionally performed for every file the design's Protected
Files list names, including `tests/EP002/test_shell.py`, all Telegram
and REST production files, `MemoryPersistence`, `WorkflowSchedulerService`,
`RuntimeService`, `Bootstrap`, `main.py`, `config/config.yaml`,
`ARCHITECTURE_DEBT.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`,
`BACKLOG.md`, `JARVIS_ROADMAP.md`, and every EP002/EP043/EP051/EP052/
EP059-EP064 test file — all confirmed byte-identical (Section 1).

---

## 10. Independent Validation

All figures below were produced by this audit's own, fresh process
invocations — not copied from the STEP 2 report.

| Suite | Passed | Failed | Skipped |
|---|---|---|---|
| EP065 | 42 | 0 | 0 |
| EP002 | 21 | 0 | 0 |
| EP043 | 83 | 0 | 0 |
| EP051 | 105 | 0 | 0 |
| EP052 | 135 | 0 | 0 |
| EP059 | 93 | 0 | 0 |
| EP060 | 65 | 0 | 0 |
| EP061 | 62 | 0 | 0 |
| EP062 | 39 | 0 | 0 |
| EP063 | 78 | 0 | 0 |
| EP064 | 93 | 0 | 0 |

Full project-wide `TestRunner`-equivalent execution (51 of 53
registered suites completed; 2 could not execute):

**Totals across completed suites: 6,917 passed, 3 failed, 1 skipped.**

Failing/non-executing suites, independently investigated:

- **EP047: 2 failures** (`"Expected True"`, `"STT must remain available
  even if TTS construction fails"`) — traced to `bootstrap.voice_engine`
  being `None` because real `VoskSpeechToTextEngine` construction
  requires the `vosk` package, which is not installed in this sandbox.
- **EP049: 1 failure + 1 skip** (`"Expected True"`) — same root
  dependency chain (voice/STT).
- **EP046, EP048: could not execute at all** — `SpeechToTextEngineError`
  (missing `vosk`) and `StreamingAudioCaptureError` (missing
  `sounddevice`/PortAudio), respectively.

**Independent cross-check against the untouched original baseline**
(not merely trusting STEP 2's identical claim): this audit separately
re-ran EP047, EP049, EP046, and EP048 against the completely unmodified
original archive, with `sys.path` pointed at that separate copy. The
result was **identical** — the same 2 failures in EP047, the same 1
failure + 1 skip in EP049, and the same two crashes in EP046/EP048,
all with byte-identical error messages, occurring on a codebase that
has never had EP-065's diff applied. **This independently and
conclusively confirms these four suites' issues are pre-existing
environment/dependency limitations (missing `vosk`, missing
`sounddevice`/PortAudio) and are not attributable to EP-065 in any
way.**

**Classification:**
- EP-065 regressions: **none found.**
- Pre-existing source failures: **none found** (the four affected
  suites fail identically with or without EP-065's diff, so the
  failures are not attributable to any source defect introduced or
  pre-existing in the audited code paths — they are purely a missing
  runtime dependency).
- Environment/dependency limitations: **EP046, EP047, EP048, EP049**
  (missing `vosk`, `sounddevice`/PortAudio in this sandbox).
- Hardware limitations: none observed beyond the above (no physical
  audio device was required to reach this specific failure point;
  the failure occurs at package-import/construction time).

---

## 11. Findings

| ID | Severity | Description | Evidence | Introduced by EP-065? | Blocking? | Recommended action |
|---|---|---|---|---|---|---|
| F1 | LOW | `tests/EP065/` does not include a test where `module.execute()` itself raises `ValueError` (only a generic `Exception` is used in `_RaisingModule`), which is the single scenario most likely to reveal an accidental overlap between the two `try/except` blocks if a future refactor merged them. | Read of `tests/EP065/test_command_router_malformed_input.py`; independently exercised by this audit's own script (Section 5), which passed. | No (a test-coverage gap, not an implementation defect) | No | Consider adding this exact case to `tests/EP065/` in a future, purely additive test-only change. |
| F2 | LOW | `tests/EP065/` does not itself re-assert blank-input (`""`, `"   "`) behavior; this remains covered only by the untouched `tests/EP002/test_shell.py`. | Read of both test files; `tests/EP002/` independently re-run, 21/21 passing. | No | No | None required; documented for completeness. Coverage is not missing overall, only not duplicated in EP-065's own package. |
| F3 | NOTE | The Telegram survival test (both STEP 2's and this audit's own independent version) relies on real-thread polling with a bounded wall-clock deadline rather than a fully deterministic synchronization primitive. | Read of `_test_telegram_poll_loop_survives_malformed_message`; this audit's own equivalent script used a different interval (0.03s vs. the suite's 0.05s) and passed identically. | No (inherent to real-thread integration testing, consistent with EP061/063/064's own established style) | No | None required; noted as an inherent, low-risk property of real-thread tests, not a defect. |

No BLOCKER, HIGH, or MEDIUM findings were identified. No finding above
implicates EP-065 in reopening EP064-F1, Architecture Debt AD-001, or
any Telegram lifecycle/shutdown/authentication concern — all were
independently confirmed untouched (Sections 4/9).

---

## 12. Final Verdict

**PASS WITH NON-BLOCKING FINDINGS.**

All ten Owner Decisions (D1-D10) independently verified PASS. The
critical exception-boundary check independently confirmed the new
`except ValueError` guard cannot and does not intercept a `ValueError`
raised by `module.execute()`. Raw command text was independently
confirmed absent from both the returned `CommandResult.message` and
the new log line, using a fresh marker string not reused from STEP 2's
own test. `_tokenize()` is independently confirmed byte-identical to
the pre-EP-065 baseline. Shell, Telegram, and REST production files
are independently confirmed byte-identical to baseline, and the
EP-065-specific survival/immunity claims for each were independently
re-verified at runtime with fresh scripts distinct from STEP 2's own
suite. Protected-file verification against the untouched original
archive shows exactly the four expected differences and nothing else.
Independent execution of the dedicated suite, the ten mandated
regression suites, and the full project-wide runner found zero
EP-065-attributable failures; the three failures and one skip present
in the full run were independently reproduced, unchanged, on the
completely untouched original baseline, conclusively confirming they
are pre-existing environment/dependency limitations unrelated to this
EP. The three findings recorded (F1, F2: LOW; F3: NOTE) are coverage
observations, not correctness defects, and do not warrant a blocking
verdict.
