# EP-065 — CommandRouter Malformed-Input Dispatch Safety

Status: **STEP 1 — DESIGN ONLY. Not implemented.**

---

## 0. How this scope was derived

Neither `docs/architecture/JARVIS_ROADMAP.md` nor `docs/BACKLOG.md`
names an EP-065 scope; both say "none yet defined," and no EP-061
through EP-064 design/audit document names a specific "next EP"
candidate either. Per this task's instructions, this document
discovers EP-065's scope from repository evidence rather than
inventing one.

### 0.1 Candidates investigated

**Candidate A — Telegram Gateway shutdown coordination.** Re-verified,
independently of EP-063's and EP-064's own investigations: `TelegramModule.
_actions` still contains a `"stop"` key wired to `TelegramService.stop()`
(confirmed, `telegram_module.py`; `telegram_service.py` lines 147-160)
— a real, existing, idempotent manual escape hatch — and `tests/`
still contains no `EP012`-numbered directory and no other test file
for `TelegramService`/`TelegramModule`/`TelegramClient`/
`TelegramRouter` (confirmed by repository-wide search; only
`tests/EP040/test_telegram_info_service.py` and
`tests/EP040/test_telegram_info_module.py` exist, and those cover the
architecturally separate, read-only `TelegramInfoService`). Both of
EP-063's and EP-064's stated rejection reasons reconfirmed true today.
Not selected — no new evidence materially changes this repeatedly
re-confirmed conclusion.

**Candidate B — REST API authentication.** Not re-investigated in
depth; already disclosed as real but architecturally enormous by every
prior EP back through `EP059_DESIGN.md`, and explicitly rejected by
EP-063's and EP-064's own STEP 1 for the same reason. No new evidence
changes that conclusion. Not selected.

**Architecture Debt items (AD-001 through AD-009,
`docs/architecture/ARCHITECTURE_DEBT.md`).** Explicitly ineligible per
that document's own rule ("Never fix Architecture Debt during a
normal Engineering Phase"). AD-001 ("Malformed
`workflow_scheduler.tick_interval` may terminate the background
thread instead of degrading gracefully") is adjacent in *theme* to
this document's selected scope but is a **different code location and
a different failure mechanism** (a malformed *configuration value*
read once, before a loop starts, vs. this EP's selected scope, which
is a malformed *piece of user/chat input* rejected by a tokenizer on
every call) — see Non-Goals (Section 5) and Owner Decision D9 for the
explicit boundary between the two. Not applicable to this EP's scope
determination.

**Candidate C — `MemoryPersistence._auto_save_loop()`'s narrower
exception guard (EP064-F1).** `EP064_ARCHITECTURE_AUDIT.md` Finding
EP064-F1 disclosed that `_auto_save_loop()` lacks the broad
`except Exception` guard `SchedulerService._tick_loop()` has, so a
non-`OSError` failure inside `save()` could silently kill the
`memory-auto-save` thread. Independently re-confirmed true today by
re-reading `memory_persistence.py`. This is a real, legitimate future
candidate, but it is a **single-file, single-subsystem** correctness
gap with a narrower blast radius (one background thread, already
independently observable via `memory doctor`'s `auto_save_valid`
check) than Candidate D below, which affects the interactive shell
process itself, the Telegram gateway, and (per Section 2) is proven,
by direct code reading of `src/main.py`, to also skip the graceful
shutdown of *every* other subsystem EP-059 through EP-064 built.
Comparing the two directly: Candidate D's failure mode terminates the
entire process; Candidate C's failure mode stops one already-monitored
background thread. Not selected for this EP, and explicitly not
absorbed into it (see Non-Goals) — recorded here as a legitimate,
still-open, separately-scoped future candidate, exactly as
EP064-F1 itself already recommended.

**Candidate D — `CommandRouter.dispatch()`'s `_tokenize()` raising an
uncaught `ValueError` on malformed quoting (selected).** See Sections
1-4 below for the full evidence trail. Selected as strictly the
highest-severity, best-evidenced, most isolated candidate found during
this STEP 1's repository-wide search.

### 0.2 Final selection

**Candidate D, CommandRouter Malformed-Input Dispatch Safety**, is the
strongest, most evidence-supported EP-065 scope: a real, code-verified,
100%-reproducible defect whose failure mode — an uncaught process
crash of the interactive shell, or an uncaught, permanent death of the
Telegram polling thread — is more severe than any single-subsystem
background-thread gap this project has closed to date (EP-061,
EP-062, EP-063, EP-064 each concerned one already-isolated background
thread; this defect concerns the single shared dispatch path used by
every current and future command-driven interface), yet the fix
itself is minimal, isolated to one call site in one already-frequently-
touched file (`src/core/command_router.py`, last touched by EP-052's
D11), and requires no new abstraction.

---

## 1. Problem Statement

`CommandRouter.dispatch()` (`src/core/command_router.py`) is the
single, shared entry point every current interface in this repository
dispatches user-supplied command text through:

```
InteractiveShell.run()        -> CommandRouter.dispatch(raw)
TelegramRouter.route()        -> CommandRouter.dispatch(text)
ApiRouter.dispatch_command()  -> CommandRouter.dispatch(raw_command)
```

`dispatch()` already converts exactly one class of failure —
an exception raised by `module.execute(action, arguments)` — into a
graceful `CommandResult(success=False, message=...)`, via an
`except Exception` block already present in the method (line
165-170). This is the method's own, already-established convention:
a caller of `dispatch()` should never need to catch an exception
itself; every outcome, success or failure, is expressed as a
`CommandResult`.

However, `dispatch()`'s very first line —

```python
tokens = self._tokenize(raw_input.strip())
```

— is **not** covered by that convention. `_tokenize()` delegates to
Python's standard-library `shlex.shlex(..., posix=True)` (added by
EP-052's Owner Decision D11, to fix a Windows-backslash-corruption
defect; see `EP052_ARCHITECTURE_AUDIT.md` Section 6). `shlex`'s POSIX
tokenizer raises a plain `ValueError("No closing quotation")` whenever
its input contains an odd number of unescaped `"` or `'` characters —
independently reproduced during this STEP 1 for every tested variant
(a trailing unmatched `"`, a trailing unmatched `'`, a lone `"` or `'`
character alone, and multiple quote characters that don't pair off).
No other malformed input this STEP 1 tested (null bytes, tab
characters, ANSI escape sequences, a trailing unescaped backslash)
raises anything.

This `ValueError` is **not caught anywhere between `_tokenize()` and
whichever interface first called `dispatch()`**:

- `InteractiveShell.run()`'s own `try` block only catches
  `KeyboardInterrupt` and `EOFError` (confirmed, `src/core/shell.py`
  lines 39-49) — any other exception, including this one, propagates
  straight out of `run()`.
- `TelegramService._poll_loop()` has **no** `try`/`except` around its
  call to `_poll_once()` at all (confirmed, `src/services/
  telegram_service.py` lines 221-226) — `_poll_once()` in turn calls
  `self._router.route(...)` (which calls `dispatch()`) with no
  surrounding guard either (only `fetch_updates()` and
  `send_message()` are individually wrapped, each in a narrower
  `except TelegramClientError`, Section 2.5 below).

The result is two independent, 100%-reproducible failure modes, both
triggerable by ordinary, plausible user input (a stray quote character
in a natural-language sentence, a half-typed shell command, a file
path containing an apostrophe):

1. **Interactive shell process crash.** A user typing, e.g.,
   `system status "oops` at the `jarvis> ` prompt raises `ValueError`
   out of `InteractiveShell.run()`. `src/main.py`'s `main()` function
   calls `shell.run()` with **no surrounding `try`/`except`** (confirmed,
   `src/main.py` lines 43-46), so the exception propagates all the way
   to the interpreter, printing a raw Python traceback and terminating
   the process with a non-zero exit code. Because `main()`'s next two
   lines — `bootstrap.shutdown()` and `_save_memory_on_shutdown(bootstrap)`
   — are never reached, this crash **also skips every graceful shutdown
   step EP-059 through EP-064 built**: the REST API Server is never
   stopped, the Scheduler and Workflow Scheduler tick loops are never
   signaled, the Memory auto-save loop is never signaled, the
   Background Worker Service is never drained, and the final,
   unconditional Memory save that normally happens on every clean exit
   never runs.
2. **Permanent, silent death of the Telegram polling thread.** The
   identical malformed text, sent as a Telegram message to a bot with
   `telegram.enabled`/`telegram.auto_start` both true, raises the same
   `ValueError` out of `_poll_once()`, which is called directly (no
   `try`/`except`) from `_poll_loop()`'s `while` loop body. The
   `"telegram-poll"` daemon thread terminates permanently; `telegram
   status`'s existing `running` field (backed by
   `_is_poll_loop_running()`) correctly reports `False` from that point
   on, but nothing restarts the thread automatically, and — unlike
   every deliberately-added `shutdown()` method this repository has
   built (EP-061, EP-063, EP-064) — this is not a controlled,
   requested stop; it is an unrequested, unrecoverable failure
   triggered by a single malformed inbound message from any authorized
   chat.

Neither failure mode requires anything unusual: an ordinary user
typing an unmatched quotation mark, or a file path/sentence containing
one, is sufficient. This is a defect in the single most foundational,
shared piece of dispatch infrastructure in the entire project, not an
edge case confined to one optional subsystem.

---

## 2. Current Architecture / Evidence

### 2.1 `CommandRouter._tokenize()` (`src/core/command_router.py`, lines 107-129)

```python
@staticmethod
def _tokenize(raw_input: str) -> list[str]:
    lexer = shlex.shlex(raw_input, posix=True)
    lexer.whitespace_split = True
    lexer.escape = ""
    return list(lexer)
```

Added by EP-052 Owner Decision D11 (`EP052_ARCHITECTURE_AUDIT.md`
Section 6) specifically to stop `shlex.split()`'s POSIX-mode escape
processing from corrupting Windows paths (`C:\Temp\file.txt` ->
`C:Tempfile.txt`) by disabling `lexer.escape`. This did not change,
and was never intended to change, `shlex`'s separate, unrelated
quote-*balancing* check: `list(lexer)` (equivalently,
`lexer.get_token()` called repeatedly until `None`) still raises
`ValueError("No closing quotation")` whenever the input contains an
odd number of unescaped quote characters, **independent of the
`escape` setting** — independently reproduced during this STEP 1 with
`lexer.escape = ""` set exactly as it is in the current code.

Exhaustively tested during this STEP 1 (Python 3, this repository's
own interpreter): every input containing an unbalanced `"` or `'`
character (trailing unmatched, leading unmatched, multiple
non-pairing quotes, or a single bare quote character) raises
`ValueError`; every other tested pathological input (null bytes, tab
characters, ANSI escape sequences, a trailing unescaped backslash,
embedded newlines, empty string, whitespace-only string) does not
raise anything and tokenizes exactly as `shlex`'s documented behavior
predicts. `ValueError` is the *only* exception type this method can
currently raise for any string input.

### 2.2 `CommandRouter.dispatch()` (lines 131-171) — the one call site

```python
def dispatch(self, raw_input: str) -> CommandResult:
    tokens = self._tokenize(raw_input.strip())          # <- unguarded
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

`_tokenize()` has exactly **one** call site in the entire repository:
this line, inside `dispatch()`. `dispatch()` itself already
demonstrates the repository's own established convention for
converting an internal failure into a `CommandResult` — twice, for two
different failure classes already (`module is None`; `module.execute()`
raising) — but the tokenize call, three lines above the first of
these, has no equivalent guard. `dispatch()`'s own docstring
(`"Returns: A CommandResult describing the outcome of execution."`)
implicitly promises exactly the invariant this defect breaks: that
`dispatch()` always returns a `CommandResult` and never raises.

### 2.3 `InteractiveShell.run()` (`src/core/shell.py`, lines 33-49)

```python
def run(self) -> None:
    logger.info("Interactive shell started.")
    while True:
        try:
            raw = input(self.PROMPT)
            result = self._router.dispatch(raw)
            self._display_result(result)
            if result.should_exit:
                logger.info("Interactive shell stopped.")
                break
        except KeyboardInterrupt:
            print("\nUse 'system exit' to quit.")
            continue
        except EOFError:
            print("\nGoodbye.")
            break
```

Confirmed: exactly two exception types are caught, both around the
entire loop body. No `except ValueError` or `except Exception` exists
anywhere in this file. `self._router.dispatch(raw)` is the only call
into `CommandRouter` this class makes.

### 2.4 `src/main.py` (lines 40-47) — confirming the shutdown-skip consequence

```python
shell = bootstrap.shell
if shell is None:
    ...
    return 1

shell.run()
bootstrap.shutdown()
_save_memory_on_shutdown(bootstrap)
return 0
```

Confirmed: `shell.run()` is called with **no** surrounding
`try`/`except` in `main()`. `bootstrap.shutdown()` (the
`RuntimeService`-coordinated shutdown sequence EP-059 through EP-064
built: REST API Server, Scheduler, Workflow Scheduler, Memory
Persistence, Background Worker Service, in that order) and
`_save_memory_on_shutdown(bootstrap)` (the final, unconditional Memory
save) are both reached **only if `shell.run()` returns normally**. An
uncaught exception from `shell.run()` skips both unconditionally.
`main()`'s own top-level `try`/`except Exception` (lines 30-36) wraps
only `bootstrap.run()` — the *startup* sequence — not `shell.run()`.

### 2.5 `TelegramService._poll_loop()` / `_poll_once()` (`src/services/telegram_service.py`, lines 221-244)

```python
def _poll_loop(self) -> None:
    interval = float(self._config.get("telegram.polling_interval", 2))
    while not self._stop_event.wait(interval):
        self._poll_once()                                # <- unguarded
    logger.info("Telegram polling stopped.")

def _poll_once(self) -> None:
    if self._client is None:
        return
    try:
        messages = self._client.fetch_updates()
    except TelegramClientError as exc:
        logger.error(f"Telegram polling failed: {exc}")
        return
    for message in messages:
        result = self._router.route(message.chat_id, message.text)   # <- unguarded
        try:
            self._client.send_message(message.chat_id, result.message)
        except TelegramClientError as exc:
            logger.error(f"Telegram outgoing message failed: {exc}")
```

Confirmed: `_poll_loop()`'s `while` loop has no `try`/`except` of any
kind around its call to `_poll_once()`. Inside `_poll_once()`, only
`fetch_updates()` and `send_message()` are individually guarded, each
by the narrow, Telegram-Bot-API-specific `TelegramClientError` —
`self._router.route(...)` (which calls `CommandRouter.dispatch()`) has
no guard at all. This is independently, and more severely, exposed
than `InteractiveShell`: any authorized chat can trigger it with a
single message, at any time, with no restart mechanism.

### 2.6 `TelegramRouter.route()` (`src/core/telegram/telegram_router.py`, lines 62-80)

```python
def route(self, chat_id: int, text: str) -> CommandResult:
    if not self.is_authorized(chat_id):
        logger.warning(...)
        return CommandResult(success=False, message="Unauthorized.")
    logger.info(f"Telegram incoming command: chat_id={chat_id}")
    result = self._command_router.dispatch(text)
    logger.info(f"Telegram outgoing message: chat_id={chat_id}")
    return result
```

Confirmed: `route()` performs no parsing or tokenization of its own —
it is a thin, direct pass-through to `CommandRouter.dispatch()`,
exactly as its own class docstring states ("Hand authorized message
text to CommandRouter.dispatch() unchanged. Never executes business
logic itself"). The specific `ValueError` this EP addresses currently
propagates through `route()` only because it propagates, unmodified,
straight out of its one call to `self._command_router.dispatch(text)`
— `route()` adds no `try`/`except` of its own around that call.
Containing this specific exception inside `dispatch()` itself
(Section 8) is therefore sufficient to stop it from ever reaching
`route()`'s caller (`TelegramService._poll_once()`), with no change to
`route()` required. This document makes no broader claim about
`route()`'s exception-safety for failure classes other than the one
this EP addresses.

### 2.7 REST dispatch path (`ApiRouter.dispatch_command()`, `src/core/api/api_router.py`, lines 46-70)

```python
def dispatch_command(self, module: str, action: str, arguments: list[str]) -> CommandResult:
    tokens = [module]
    if action:
        tokens.append(action)
    tokens.extend(arguments)
    raw_command = " ".join(shlex.quote(token) for token in tokens)
    return self._command_router.dispatch(raw_command)
```

`ApiRouter` re-escapes every token via `shlex.quote()` before
rejoining and handing the result to `dispatch()`. `shlex.quote()`'s
own output is, by construction, always safely re-tokenizable by
`shlex.shlex(..., posix=True)`: it wraps any token containing a
special character (including a literal `"` or `'`) in single quotes,
escaping any embedded single quote as `'"'"'`. Independently verified
during this STEP 1 by round-tripping a wide set of adversarial token
values (a bare `"`, a bare `'`, mixed quotes, an unmatched quote
embedded mid-string, embedded newlines, embedded backslashes, an empty
string) through `shlex.quote()` then back through
`CommandRouter._tokenize()`'s exact lexer configuration — **zero**
raised a `ValueError`, for every value tested. This confirms
`ApiRouter`'s own docstring claim ("so the REST API can never diverge
in behaviour from the CLI") is not merely aspirational for this
specific failure mode: the malformed-quoting defect this EP addresses
is **structurally unreachable** via the REST path, for any request
body, by construction of `dispatch_command()` itself.

As a second, independent safety net (not required to close this
defect, but confirmed present): `RestApiServer._dispatch()`
(`src/core/api/rest_api_server.py`, lines 241-273) wraps its call to
`api_router.dispatch_command(...)` in a broad
`except Exception as exc: ... self._send_error(ApiInternalError(...))`
— so even in a hypothetical future where `dispatch_command()`'s
escaping guarantee were ever broken, an exception from `dispatch()`
would still only fail that one HTTP request (returning `500 Internal
server error` to the caller) inside `ThreadingHTTPServer`'s own
per-request thread, never crash the server process or any other
in-flight request.

### 2.8 `dispatch()`'s own established error-conversion convention

`dispatch()` already has two, and only two, precedents for converting
an internal condition into a returned `CommandResult` rather than
raising:

| Condition | Existing handling |
|---|---|
| `module_name` not registered | `CommandResult(success=False, message="Unknown module: ...")`, logged at `logger.info(...)` |
| `module.execute()` raises any `Exception` | `CommandResult(success=False, message="Internal error while executing '<raw_input>'.")`, logged at `logger.error(...)` |

No third precedent exists for a tokenizer-level parse failure — this
is a genuinely new failure class for this method, not a variant of
either existing one, since it occurs *before* a module is even
identified.

### 2.9 Existing test coverage

Confirmed via repository-wide search: `tests/EP002/test_shell.py` is
the **only** test file that constructs and dispatches through a real
`CommandRouter` directly (eight test methods: router creation, empty
router, registration count, duplicate-registration rejection, unknown
module, blank input, case-insensitive lookup, whitespace trimming).
None of these eight tests supplies any quoted or malformed input of
any kind. No test file anywhere calls `InteractiveShell.run()` (its
blocking `input()` loop has no existing test harness in this
repository). `tests/EP059/test_runtime.py` and
`tests/EP043/test_rest_api.py` each construct an `InteractiveShell`
instance only to observe its *presence* via `RuntimeService.status()`
— neither calls `.run()`. No test file anywhere constructs a
`TelegramService`/`TelegramModule`/`TelegramClient`/`TelegramRouter`
(reconfirmed, Section 0.1, Candidate A). This defect and its two
failure modes have zero existing regression coverage of any kind.

---

## 3. Failure Path / Impact Summary

| Path | Reaches unguarded `_tokenize()` call? | Consequence today | After this EP |
|---|---|---|---|
| `InteractiveShell.run()` -> `dispatch()` | Yes (raw, untrusted user keystrokes) | Uncaught `ValueError` crashes the whole process; skips `bootstrap.shutdown()` and the final Memory save | `dispatch()` returns a failure `CommandResult`; shell prints it and continues its loop |
| `TelegramRouter.route()` -> `dispatch()` | Yes (raw, untrusted chat message text) | Uncaught `ValueError` permanently kills the `"telegram-poll"` daemon thread; no auto-restart | `dispatch()` returns a failure `CommandResult`; `route()` returns it to `_poll_once()`, which sends it back to the chat exactly like any other failed command; polling continues |
| `ApiRouter.dispatch_command()` -> `dispatch()` | No — `shlex.quote()` makes the specific malformed string this method could ever pass to `_tokenize()` always well-formed, independently verified (Section 2.7) | N/A — not reachable | Unchanged; not reachable before or after this EP |

---

## 4. Selected Scope

Close the single unguarded call site inside `CommandRouter.dispatch()`
so that `_tokenize()`'s `ValueError` is converted into a
`CommandResult(success=False, ...)`, following the exact pattern
`dispatch()` already uses for `module.execute()`'s own exception
guard. This specific `ValueError` originates only at
`CommandRouter._tokenize()` (Section 2.1); containing it at
`dispatch()`'s own call site (Section 2.2) prevents it from escaping
into `InteractiveShell.run()` (Section 2.3) or into
`TelegramService._poll_loop()` via `TelegramRouter.route()` (Sections
2.5-2.6), since both reach `_tokenize()` only indirectly, through
`dispatch()`. No change to `InteractiveShell` or any Telegram
production file is required to close this specific failure mode. The
REST path is already unaffected by this specific failure mode
(Section 2.7) and must remain behaviorally unchanged.

---

## 5. Goals

1. `CommandRouter.dispatch()` never raises `ValueError` (or any other
   exception) for malformed quoting in `raw_input` — it always returns
   a `CommandResult`, for every string input, matching the invariant
   its own docstring and its two existing failure-conversion
   precedents (Section 2.8) already establish.
2. A malformed command line reaching `InteractiveShell.run()` is
   reported to the user as a normal, unsuccessful command result; the
   shell's main loop continues to the next prompt exactly as it does
   after any other unsuccessful command (e.g. "Unknown module").
3. A malformed message reaching `TelegramService`'s polling loop is
   reported back to the sending chat exactly like any other failed
   command; the `"telegram-poll"` thread is never terminated by it.
4. The original exception detail remains observable via the existing
   `logger.error(...)` sink, following the exact logging convention
   `dispatch()`'s neighboring `module.execute()` handler already uses.
5. Every currently-passing behavior of `dispatch()`, `_tokenize()`,
   `InteractiveShell`, `TelegramService`, and the REST dispatch path,
   for well-formed input, remains byte-for-byte unchanged.

## 6. Non-Goals

- **Does not touch `InteractiveShell.run()`, `TelegramService._poll_loop()`/
  `_poll_once()`, `TelegramRouter.route()`, `ApiRouter.dispatch_command()`,
  or `RestApiServer`.** Sections 2.3, 2.5-2.6, and 2.7 confirm that this
  specific `ValueError` reaches each of these only indirectly, through
  its one call into `dispatch()`; once `dispatch()` itself contains
  this specific exception (Section 8), none of these files needs to
  change to stop it from escaping to them. This document makes no
  broader claim about these files' exception-safety in general; adding
  a redundant guard to any of them
  would be an unrequested, unevidenced defense-in-depth change this EP's
  scope does not require (Owner Decision D6/D7).
- **Does not fix EP064-F1** (`MemoryPersistence._auto_save_loop()`'s
  narrower exception guard) — a real, disclosed, but separate,
  single-subsystem gap (Section 0.1, Candidate C) requiring its own,
  independently-scoped future EP. `src/core/memory/memory_persistence.py`
  is not touched by this EP.
- **Does not fix Architecture Debt AD-001** (malformed
  `workflow_scheduler.tick_interval` config value) — a different code
  location (a config-value read, before a loop starts) and a
  different failure mechanism (bad configuration, not per-call user
  input); explicitly barred from a normal EP by
  `ARCHITECTURE_DEBT.md`'s own rule regardless. `src/services/
  workflow_scheduler_service.py` is not touched by this EP.
- **Does not widen `TelegramService._poll_once()`'s existing
  `except TelegramClientError` guards** around `fetch_updates()`/
  `send_message()` into a broader `except Exception`, even though this
  is thematically adjacent (Owner Decision D9). That is a separate,
  narrower observation about Telegram's own Bot-API-error handling,
  recorded here as a finding for a possible future EP, not fixed now.
- **Does not introduce a new exception type, a new `CommandResult`
  field, or an `error_code`/structured-error concept** (Owner Decision
  D8) — reuses the existing, untyped `CommandResult(success=False,
  message=...)` shape exactly as both existing failure paths in this
  method already do.
- **Does not change `_tokenize()`'s own body, return type, or
  docstring contract** (Owner Decision D2) — `_tokenize()` continues to
  raise `ValueError` exactly as `shlex` already does; only its single
  call site gains a guard.
- **Does not change REST behavior in any way** (Owner Decision D7) —
  `ApiRouter`/`RestApiServer`/`dto.py` are not touched; the defect this
  EP closes is not reachable via that path either before or after this
  change (Section 2.7).
- **Does not change the wording, structure, or logging of the two
  already-existing `dispatch()` failure paths** ("Unknown module: ...",
  "Internal error while executing ...") — both remain byte-for-byte
  identical.
- **Does not add a general `try`/`except` around `shell.run()` in
  `main.py`**, or otherwise change `main.py`'s own control flow. Fixing
  `dispatch()` at its source makes such an outer guard unnecessary for
  this specific defect; a broader "what should `main()` do about *any*
  unexpected exception from `shell.run()`" question is a distinct,
  larger architectural decision this EP does not make.
- **No refactor of `CommandRouter` beyond the one new `try`/`except`
  block.** `register()`, `register_modules()`, `module_names`, and
  every other existing method/line are untouched.

---

## 7. Owner Decisions

### D1 — Where should the malformed-input failure be caught?

**Question:** Should the guard live inside `CommandRouter.dispatch()`
itself, or in each transport (`InteractiveShell`, `TelegramService`,
`ApiRouter`) independently?

**Options:** (a) inside `CommandRouter.dispatch()`, wrapping only the
`self._tokenize(raw_input.strip())` call — recommended; (b) in each
transport, independently catching `ValueError` around its own call
into `dispatch()`; (c) inside `_tokenize()` itself, catching its own
`ValueError` and returning a best-effort/empty token list.

**Recommended option:** (a).

**Reason:** `dispatch()`'s own class/method docstrings already state
its responsibility is to parse, validate, delegate, and "return its
result" — and it already converts exactly one other exception class
(`module.execute()` raising) into a `CommandResult`, in this same
method, three lines below the unguarded call. `TelegramRouter`'s and
`ApiRouter`'s own docstrings each independently state their purpose is
to hand input to `dispatch()` "unchanged"/"never diverge... from the
CLI's [behavior]" — pushing the fix to option (b) would require
duplicating an identical guard in at least three places (today) and
every future transport, reintroducing exactly the kind of
per-transport divergence risk those classes exist to avoid. Option
(c) is rejected in Owner Decision D2 below.

**Alternative rejected:** (b) — duplicative, divergence-prone,
contradicts existing transport docstrings' own stated intent; (c) —
see D2.

**Architectural consequence:** Exactly one new `try`/`except` block,
inside `CommandRouter.dispatch()`, wrapping only the tokenize call.
No other file changes.

### D2 — Should `_tokenize()` itself change?

**Question:** Should `_tokenize()` swallow its own `ValueError` and
return an empty or best-effort token list, instead of `dispatch()`
catching it?

**Options:** (a) `_tokenize()`'s body is completely unchanged; it
keeps raising `ValueError` exactly as `shlex` already does — recommended;
(b) `_tokenize()` catches `ValueError` internally and returns `[]` (or
a partial token list).

**Recommended option:** (a).

**Reason:** `_tokenize()`'s own docstring already promises "the list
of parsed tokens (possibly empty)" for well-formed input — teaching it
to also silently swallow a genuine parse failure and return the same
shape (`[]`) as legitimate blank input would conflate two different
things (deliberately blank input vs. a rejected malformed input) that
`dispatch()` needs to distinguish in order to report a useful message
(D3). Handling the failure once, at the one call site, where the
established `CommandResult`-conversion pattern already lives, is the
smaller, more correct boundary — and keeps `_tokenize()` a pure,
single-purpose helper.

**Alternative rejected:** (b) — silently discards the distinction
between "nothing to parse" and "a syntax error," and moves knowledge
of `CommandResult`'s existence into a method that currently has none
and does not need it.

**Architectural consequence:** `_tokenize()` is byte-for-byte
unchanged; only `dispatch()`'s body changes.

### D3 — What message should the returned `CommandResult` carry?

**Question:** Should the new failure path reuse the existing "Internal
error while executing '<raw_input>'." wording, or use distinct wording
naming the actual problem?

**Options:** (a) distinct wording naming the syntax problem, e.g.
`f"Invalid command syntax: {exc}"` — recommended; (b) reuse the
existing "Internal error while executing '<raw_input>'." message
verbatim.

**Recommended option:** (a).

**Reason:** `dispatch()` already uses two distinct message shapes for
two distinct failure classes in this exact method ("Unknown module:
...", "Internal error while executing ..."); a third, distinct message
for a third, distinct failure class (a syntax error the *tokenizer*
rejected, before a module was ever identified) continues that existing
convention rather than collapsing three different failure reasons into
one ambiguous "Internal error" label, which would incorrectly suggest
a Jarvis-side defect for what is, in every observed case, a user
input mistake (an unmatched quote character).

**Alternative rejected:** (b) — technically works, but mislabels a
user syntax error as an internal defect, and gives an operator no
actionable signal about what went wrong.

**Architectural consequence:** A third, new, distinct message string
appears in `dispatch()`; it deliberately does not enumerate the exact
text (Section 9) but must clearly identify "invalid command syntax"
distinctly from "internal error" and from "unknown module."

### D4 — Should the raw input be echoed back in the new message or logs? (REVISED)

**Question:** Should the new malformed-syntax `CommandResult.message`,
or the corresponding log line, include the full offending `raw_input`
text?

**Options:** (a) include the full `raw_input`, mirroring the adjacent
`module.execute()` failure handler's own existing
`"Internal error while executing '<raw_input>'."` precedent, which
already echoes the full raw input back to both the caller and the
log — originally recommended in the prior revision of this document,
**now rejected**; (b) include only the parser's own exception reason
(a short, fixed-vocabulary string — for this defect, always exactly
`"No closing quotation"`, per Section 2.1's exhaustive testing) and
**not** the raw command text, in both the returned `CommandResult
.message` and the log line — **recommended**.

**Recommended option:** (b).

**Reason (revised):** `CommandRouter.dispatch()` receives arbitrary
command arguments from every transport in this repository, including
ones (`TelegramRouter`, `ApiRouter`) that pass through user- or
chat-supplied free text with no content restriction. A malformed
command line reaching the new branch this EP adds may itself contain
a credential, token, secret, or personal data fragment (e.g. a user
pasting `login "sk-abc123` with a forgotten closing quote, or a
Telegram message containing an unmatched quote inside an otherwise
sensitive sentence) — the fact that the input happened to fail
tokenization does not make its content any less sensitive than
successfully-tokenized input would have been. Requiring the *full*
raw string to be echoed, merely to diagnose a parse failure, is not
necessary: the parser's own exception reason alone (`"No closing
quotation"`, always drawn from a small, fixed, non-content-bearing
vocabulary — Section 2.1 confirms this is the *only* message `shlex`
produces for this failure class) is already sufficient for a user to
recognize and fix a quoting mistake, and for an operator to recognize
the failure class in logs, without ever reproducing what was typed.
This EP therefore does **not** follow the adjacent `module.execute()`
handler's own raw-input-echoing precedent for this *new* branch — that
existing precedent is left completely unmodified (Non-Goals, Section
6), but it is not extended to a code path this EP is introducing for
the first time. Per this task's explicit instruction, "if existing
sibling handlers log raw input, do not broaden that behavior as part
of EP-065" — this decision keeps the new branch's own, narrower policy
self-contained, rather than either broadening the sibling handler's
existing behavior or copying its raw-input-echoing shape into new
code that does not need it.

**Alternative rejected:** (a) — copies an existing precedent's
disclosure level into a brand-new code path without evidence that the
new path needs it, and creates a real risk of writing sensitive
argument content into logs or returning it to a caller (a Telegram
chat, an interactive shell's stdout, or a future transport) solely
because that content happened to fail tokenization.

**Architectural consequence:** The new `CommandResult.message` and
the new log line each include only a fixed, safe, deterministic
description of the failure — the literal string `"Invalid command
syntax"` plus the parser's own short exception reason (e.g. `"Invalid
command syntax: No closing quotation"`) — and **never** the raw
`raw_input` text. See Section 8 (Detailed Design) and
Section 9 (Error Semantics) for the exact revised message shape.

### D5 — Logging level and content for the new failure path

**Question:** At what `loguru` level, and with what content, should
the new failure be logged?

**Options:** (a) `logger.error(...)`, matching the existing
`module.execute()` exception handler's own logging call immediately
below the new code — recommended; (b) a lower level (e.g.
`logger.warning`), on the theory that a quoting mistake is routine,
expected user behavior rather than an operational concern.

**Recommended option:** (a).

**Reason:** Matches the one, single, already-established convention
this exact method already uses for its only other caught-exception
path (`logger.error(f"Error executing '{raw_input.strip()}': {exc}")`),
preserving operator observability (every malformed-input event remains
visible in logs at the same severity as every other dispatch-level
failure) without introducing a second logging-severity convention into
one function for a similarly-shaped event.

**Alternative rejected:** (b) — introduces an inconsistent second
severity convention into the same method for no disclosed operational
benefit.

**Architectural consequence:** One new `logger.error(...)` call,
immediately mirroring the existing one's format.

### D6 — Should `InteractiveShell.run()` also be defensively hardened?

**Question:** Beyond fixing `dispatch()` itself, should
`InteractiveShell.run()` also gain a defensive `except Exception`
around its call to `self._router.dispatch(raw)`, as belt-and-braces
protection against some future, unrelated defect?

**Options:** (a) no change to `InteractiveShell` — recommended;
(b) add a defensive `except Exception` wrapper around the `dispatch()`
call in `run()`'s loop.

**Recommended option:** (a).

**Reason:** Direct code reading (Section 2.3) confirms
`InteractiveShell.run()`'s only call into `CommandRouter` is
`self._router.dispatch(raw)`, and this EP's fix (Section 8) is
sufficient to stop the one, specific `ValueError` this EP addresses
from ever reaching that call site again. This document does not claim
`InteractiveShell` is exception-safe against every possible future
failure in general — only that this specific, demonstrated failure
mode is closed by fixing its source. Adding a second, redundant guard
in `InteractiveShell` for a class of exception this EP has not
demonstrated exists would be a speculative, unevidenced scope
expansion into a file with no demonstrated defect of its own, and
would silently swallow a *different*, currently-unobserved class of
exception with no matching precedent anywhere else in this file.

**Alternative rejected:** (b) — unevidenced, duplicative, would be a
speculative scope expansion into a file with no demonstrated defect.

**Architectural consequence:** `src/core/shell.py` is not modified by
this EP.

### D7 — Should `TelegramService`/`TelegramRouter`, or the REST path, also be defensively hardened?

**Question:** Symmetric to D6, for `TelegramService._poll_loop()`/
`_poll_once()`, `TelegramRouter.route()`, and `ApiRouter.dispatch_command()`/
`RestApiServer`.

**Options:** (a) no change to any of these files — recommended;
(b) add defensive guards to one or more of them.

**Recommended option:** (a).

**Reason:** Sections 2.5-2.6 confirm `TelegramRouter.route()` reaches
this specific `ValueError` only through its one call into `dispatch()`,
which this EP's fix (Section 8) already contains at the source.
Section 2.7 confirms the REST path cannot reach this specific defect
at all, by construction (`shlex.quote()`'s escaping guarantee,
independently verified against a wide adversarial input set), and
additionally already has its own, independent, broad
`except Exception` safety net in `RestApiServer._dispatch()` regardless.
This document does not claim either file is exception-safe in
general — only that this specific, demonstrated failure mode requires
no change to either of them.

**Alternative rejected:** (b) — unevidenced for `TelegramRouter`;
unnecessary and duplicative for the already-safe REST path.

**Architectural consequence:** `src/core/telegram/telegram_router.py`,
`src/services/telegram_service.py`, `src/core/api/api_router.py`, and
`src/core/api/rest_api_server.py` are not modified by this EP.

### D8 — Is a new error type or `CommandResult` field needed?

**Question:** Should this EP introduce a dedicated exception class
(e.g. `CommandParseError`) or a structured `CommandResult.error_code`
field to let callers programmatically distinguish "syntax error" from
"internal error" from "unknown module"?

**Options:** (a) no new abstraction — reuse the existing, untyped
`CommandResult(success=False, message=...)` shape exactly as both
existing failure paths in this method already do — recommended;
(b) introduce a new exception type and/or a structured error-kind
field.

**Recommended option:** (a).

**Reason:** Every existing failure path in this exact method already
communicates its failure kind purely through `CommandResult.message`'s
free text, with no structured `error_code` anywhere in this dataclass
or any of its current consumers (`InteractiveShell._display_result`,
`ApiRouter`/`CommandResponse.from_command_result()`, `TelegramRouter`).
Introducing structure for only this one, third failure class while the
other two remain untyped would be an inconsistent half-measure. A
future, broader "structured command errors" decision, if the project
ever needs one, should apply uniformly to all three failure classes at
once — not be smuggled into this narrow bug fix.

**Alternative rejected:** (b) — inconsistent scope creep relative to
the two, already-established, unmodified sibling failure paths.

**Architectural consequence:** `CommandResult`'s dataclass definition
(`success`, `message`, `should_exit`) is unchanged. No new exception
class is added anywhere in this EP's scope.

### D9 — Is any other loop's exception-handling asymmetry in scope?

**Question:** `MemoryPersistence._auto_save_loop()` (EP064-F1) and
`TelegramService._poll_once()`'s own narrower `except TelegramClientError`
guards around `fetch_updates()`/`send_message()` are both,
independently, examples of a background loop that could die (or, for
Telegram, could still partially misbehave on a Bot-API-adjacent
failure) more easily than `SchedulerService`/`WorkflowSchedulerService`'s
tick loops, which both have a broad, deliberate
`except Exception ... # the tick loop must never die silently` guard.
Should this EP generalize that guard to either of them while it is
already investigating adjacent territory?

**Options:** (a) no — strictly out of scope, recorded as findings for
a future, separately-scoped EP — recommended; (b) fix one or both
while this EP is already touching related territory.

**Recommended option:** (a).

**Reason:** Both are real, but each is an independent, single-file,
single-subsystem defect requiring its own investigation, evidence
gathering, and Owner Decision — exactly the "must not silently expand
scope" and "must not absorb EP-064 F1" constraints this task's
instructions explicitly call out. `TelegramService._poll_once()`'s
narrower Bot-API-error guard is a *new* observation made during this
STEP 1 (not previously disclosed anywhere), recorded here rather than
fixed, following the same "record, do not fix" discipline this
repository's own audits already apply to comparable out-of-scope
findings (e.g. `EP053_ARCHITECTURE_AUDIT.md`'s Finding 1,
`EP064_ARCHITECTURE_AUDIT.md`'s Finding EP064-F1 itself).

**Alternative rejected:** (b) — would silently and materially expand
this EP's scope across two additional, independently-investigable
files this document's own selected scope (Section 4) does not cover.

**Architectural consequence:** `src/core/memory/memory_persistence.py`
and the `except TelegramClientError` guards inside
`src/services/telegram_service.py` are unmodified by this EP. Both are
recorded as legitimate future candidates (Section 0.1, Candidate C;
this section's own new observation, respectively).

---

## 8. Detailed Design

`src/core/command_router.py`'s `dispatch()` method gains one new
`try`/`except` block around its existing first line, structurally
mirroring the existing `module.execute()` guard three lines below it:

```python
def dispatch(self, raw_input: str) -> CommandResult:
    """Parse and execute a raw command line entered by the user.
    ...
    """
    try:
        tokens = self._tokenize(raw_input.strip())
    except ValueError as exc:  # noqa: BLE001 - malformed input must never crash a caller
        logger.error(f"Failed to parse command input: {exc}")
        return CommandResult(
            success=False,
            message=f"Invalid command syntax: {exc}",
        )

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

Notes on this exact shape (binding for STEP 2, not open for
re-interpretation):

- **No new local variable is introduced, and no existing line is
  touched, outside the new `try`/`except` block itself.** The
  pre-existing `raw_input.strip()` call (now appearing once, as the
  argument to `self._tokenize(...)`) is not extracted into a shared
  local, is not reused by the new `except` block, and is not
  otherwise consolidated with the two, separate, pre-existing
  `raw_input.strip()` calls further down the method (in the
  `module.execute()` failure path and the success-logging line) —
  **STEP 2 must not perform any such consolidation**, since doing so
  would touch lines outside this EP's approved diff (see Protected
  Files/Non-Goals). This is also why the new `except` block's own log
  line and message (below) deliberately do **not** reference
  `raw_input` at all, per the revised D4.
- `except ValueError` is deliberately narrow — not `except Exception`
  — since Section 2.1 independently confirmed `ValueError` is the only
  exception type `_tokenize()` can currently raise for any string
  input. A narrower catch here is more precise than the necessarily
  broader `except Exception` used for `module.execute()` (which must
  tolerate arbitrary, unknown third-party module code); narrowing to
  the exact, confirmed exception type is both more correct and follows
  this repository's own general preference for the narrowest
  sufficient exception type where one is known (e.g. `MemoryPersistence
  .save()`'s own `except OSError`, `TelegramService`'s own
  `except TelegramClientError`).
- **The new log line and the new message deliberately omit the raw
  command text (revised, D4).** `logger.error(f"Failed to parse
  command input: {exc}")` and `CommandResult(success=False,
  message=f"Invalid command syntax: {exc}")` both include only `exc`
  — the `shlex` exception's own short, fixed-vocabulary reason string
  (always exactly `"No closing quotation"` for every failure mode this
  method can currently produce, per Section 2.1's exhaustive testing)
  — and never `raw_input` or any derivative of it. This is a
  deliberate, intentional divergence from the neighboring
  `module.execute()` failure handler's own, unmodified
  `f"Error executing '{raw_input.strip()}': {exc}"` /
  `f"Internal error while executing '{raw_input.strip()}'."` lines,
  which continue to echo raw input exactly as before (Non-Goals,
  Section 6: existing sibling handlers are not modified, and their
  existing behavior is not broadened to the new branch, per D4).

No other line of `dispatch()`, `_tokenize()`, `register()`,
`register_modules()`, `CommandResult`, or `CommandModule` changes.

---

## 9. Error Semantics

- **`dispatch()` never raises, for any `str` input, of any length or
  content.** This becomes a verifiable, testable invariant (Section
  11) rather than an implicit assumption.
- **Exactly three, mutually exclusive `CommandResult(success=False,
  ...)` outcomes now exist for a failed dispatch**, corresponding to
  three, independently distinguishable causes: malformed syntax
  (new, this EP), unknown module (pre-existing, unchanged), and a
  module's own internal failure (pre-existing, unchanged). No overlap:
  a malformed-quoting input never reaches the "unknown module" or
  "internal error" branches, since it fails during tokenization,
  before a module name is ever extracted.
- **The original `shlex.ValueError`'s own short, fixed-vocabulary
  reason text (e.g. `"No closing quotation"`) is preserved** inside
  the returned `CommandResult.message` and inside the corresponding
  log line, converting a raised exception into a return value with no
  loss of the parser's own diagnostic. **The offending `raw_input`
  text itself is deliberately never included** in either the message
  or the log line (Owner Decision D4, revised) — unlike the adjacent,
  unmodified `module.execute()` failure path, which continues to echo
  raw input exactly as it always has. This asymmetry is intentional:
  malformed input may carry sensitive content (credentials, tokens,
  personal data) that its failure to tokenize does not make any safer
  to disclose.
- **Idempotent and side-effect-free.** Calling `dispatch()` repeatedly
  with the same malformed input produces the same `CommandResult`
  every time; no module's `execute()` is ever invoked for a syntax
  error (confirmed by the code shape: the new `except` block `return`s
  before `module_name, *rest = tokens` is ever reached).
- **Well-formed input's behavior is unchanged in every respect**,
  including exact return values, exact log lines, and exact timing —
  the new `try`/`except` block adds no observable behavior on the
  success path (a `try` block that does not raise has no run-time
  effect beyond the exception-handling machinery itself).

---

## 10. Shell / Telegram / REST Behavior

- **Shell:** `InteractiveShell.run()`'s loop, unmodified, receives a
  normal, unsuccessful `CommandResult` for a malformed line, displays
  its message via the existing, unmodified `_display_result()`, and
  proceeds to the next `input(self.PROMPT)` call exactly as it already
  does after any other unsuccessful command (e.g. "Unknown module").
  `should_exit` is `False` for this new failure path (mirroring both
  existing failure paths), so the shell never exits because of a
  malformed line. The full `main()` sequence (`shell.run()` returning
  normally when the user eventually types `system exit` or sends EOF)
  is preserved, so `bootstrap.shutdown()` and
  `_save_memory_on_shutdown()` are reached exactly as designed by
  EP-059 through EP-064, for every session that includes zero, one, or
  many malformed lines along the way.
- **Telegram:** `TelegramService._poll_once()`, unmodified, receives
  the same kind of `CommandResult` from `TelegramRouter.route()`
  (which itself is unmodified) and sends its `.message` back to the
  originating chat via the existing `self._client.send_message(...)`
  call, exactly as it already does for "Unknown module" or any
  module-level failure today. The `"telegram-poll"` thread's `while`
  loop continues to its next `_stop_event.wait(interval)` cycle
  exactly as it does after any other message. Repeated malformed
  messages, from the same or different authorized chats, each produce
  an independent failure reply with no cumulative state change and no
  risk to the thread.
- **REST:** No change. `ApiRouter.dispatch_command()`,
  `RestApiServer`, and `dto.py` are not touched; Section 2.7 confirms
  the defect this EP addresses was never reachable via this path
  before this change, and remains equally unreachable after it. A
  regression test (Section 11) confirms this explicitly rather than
  leaving it as an unverified assumption.

---

## 11. Testing Strategy

**EP-065 gets its own dedicated test package, `tests/EP065/`,
following the current, established convention** (revised; see Owner
Decision D10 below for the full reasoning and the repository evidence
that corrected the prior revision of this document). `tests/EP002/
test_shell.py` remains completely unmodified and continues to serve as
the existing `CommandRouter`/`InteractiveShell` regression baseline
(re-run, not edited — Section 13, Protected Files).

**`CommandRouter`-level tests (direct, real `CommandRouter`, no mocks):**

- `_test_dispatch_never_raises_for_unbalanced_double_quote` — a
  trailing, unmatched `"` returns a failing `CommandResult`, not an
  exception.
- `_test_dispatch_never_raises_for_unbalanced_single_quote` — same,
  for `'`.
- `_test_dispatch_never_raises_for_bare_quote_character` — input that
  is only a single `"` or `'` character.
- `_test_dispatch_never_raises_for_multiple_non_pairing_quotes` — e.g.
  `a "b" "c` (three quote characters, non-pairing).
- `_test_malformed_input_result_message_names_syntax_error` — the
  returned message is distinct in wording from both the "Unknown
  module: ..." and "Internal error while executing ..." messages,
  contains the parser's own exception reason (e.g. "No closing
  quotation"), and does **not** contain the original raw input text
  (Owner Decision D4, revised).
- `_test_malformed_input_never_calls_module_execute` — a registered
  `_StubModule`'s `execute()` is never invoked for any malformed-quote
  input (proves the new branch returns before module resolution).
- `_test_malformed_input_result_should_exit_is_false` — confirms the
  shell-continuation contract (Section 10).
- `_test_repeated_malformed_input_is_idempotent` — the identical
  malformed string dispatched three times in a row produces three
  identical `CommandResult` values, with no state change to the
  `CommandRouter` (`module_names` unchanged).
- `_test_well_formed_quoted_input_still_works` (regression) — a
  balanced, quoted argument (e.g. `gamma status "hello world"`) still
  dispatches successfully and the module receives the correctly
  unquoted argument — proving the fix does not alter legitimate
  quoting behavior at all.
- `_test_windows_path_backslash_handling_still_works` (regression,
  directly re-verifying EP-052 Owner Decision D11's own fix is
  untouched) — a Windows-style path argument (e.g.
  `C:\Temp\file.txt`) still tokenizes with its backslashes intact.
- `_test_unknown_module_and_internal_error_paths_unchanged`
  (regression) — re-asserts the two pre-existing failure messages'
  exact wording, byte for byte, to guard against an accidental edit
  while modifying the neighboring code.
- `_test_malformed_input_does_not_log_raw_command_text` — dispatches a
  malformed input containing a recognizable, sensitive-looking marker
  string (e.g. a fake token value) and, using `loguru`'s own testing
  hook (a temporary sink/handler attached for the duration of the
  test), asserts the marker string never appears in any log record
  emitted for that call, while the parser's own exception reason
  (e.g. "No closing quotation") does appear — directly verifying
  Owner Decision D4's revised no-echo policy at the logging layer, not
  only at the returned `CommandResult` layer.

**`InteractiveShell`-level test (real `InteractiveShell`, `builtins.input`
patched to simulate keyboard input — the standard, minimally-invasive
technique for testing a blocking `input()` loop, not a fake
collaborator replacing business logic):**

- `_test_shell_survives_malformed_line_and_continues` — patches
  `input()` to yield a malformed line (`'system status "oops'`)
  followed by a valid command that sets `should_exit=True` (e.g. via a
  `_StubModule` registered under `"system"` whose `execute()` returns
  `CommandResult(success=True, message="", should_exit=True)` for a
  known action); asserts `InteractiveShell.run()` returns normally
  (does not raise), and that the stub module's `execute()` was called
  exactly once (for the second, valid line) — proving the loop
  genuinely continued past the malformed line rather than exiting or
  crashing silently.

**`TelegramService`-level test (real `TelegramService`, a duck-typed
fake `TelegramClient`-shaped object — matching this repository's own
established "swap only the one genuine external dependency" testing
philosophy already used for, e.g., EP-058's fake AI backend and
EP-051's `_FakeBrowserBackend`; `TelegramService` performs no
`isinstance` check on its `client` dependency, confirmed by direct
code reading):**

- `_test_telegram_poll_loop_survives_malformed_message` — a fake
  client's `fetch_updates()` first returns one `TelegramMessage` whose
  `.text` is a malformed-quote string, then, on a later poll, one
  `TelegramMessage` with well-formed text; starts the real polling
  thread via `TelegramService.start()`; asserts
  `_is_poll_loop_running()` (via `telegram status`'s existing
  `running` field, or the service's own internal accessor) remains
  `True` after the malformed message has been processed, and that the
  well-formed follow-up message is still routed and replied to
  correctly, proving genuine survival and continued correct operation,
  not merely "did not crash within the test's own assertion window."
  `TelegramService.stop()` is called at the end of the test
  (idempotent, already-existing) to avoid leaking a background thread
  into later tests, following this repository's own established
  thread-cleanup convention.

**REST regression test (real `ApiRouter`, no fakes needed beyond what
`tests/EP043/test_rest_api.py` already exercises):**

- `_test_rest_dispatch_command_immune_to_malformed_quoting` — a
  `CommandRequest` whose `arguments` list contains a value that is
  itself an unbalanced-quote string (e.g. `'oops"'`) is dispatched via
  `ApiRouter.dispatch_command()`; asserts no exception is raised (this
  was already true before this EP, per Section 2.7 — this test exists
  to make that guarantee an explicit, permanent regression check
  rather than an unverified assumption) and that the argument's exact
  original text (including the embedded quote character) reaches the
  target module's `execute()` call unchanged, proving `shlex.quote()`'s
  round-trip is lossless as well as safe.

**Full regression** (every existing suite that dispatches through
`CommandRouter` with any quoted or special-character argument,
re-run unmodified): `tests/EP002/test_shell.py`'s own seven
pre-existing tests, `tests/EP043/test_rest_api.py` (REST dispatch),
`tests/EP051/test_browser.py` and `tests/EP052/test_file.py` (both
already exercise quoted/Windows-path arguments through real dispatch,
per their own design documents), plus a full-suite run (`TestRunner
.run_all()`) to confirm zero regressions project-wide, matching every
prior EP's own established full-regression practice.

**Explicitly not required:** no test count is invented here beyond
what STEP 2 will actually produce; the test names above are a
specification of required coverage, not a promised final assertion
count, matching this project's own established convention (see
`EP064_DESIGN.md` Section 12's identical disclaimer).

### Owner Decision D10 (REVISED) — dedicated `tests/EP065/` package vs. extending `tests/EP002/`

**Question:** Should EP-065's regression coverage live in a new,
dedicated `tests/EP065/` package, or be appended to the existing
`tests/EP002/test_shell.py`?

**Options:** (a) create `tests/EP065/` (an `__init__.py` plus one test
module), independently registered with `TestRegistry` under
`NAME = "EP065"`, self-contained per this repository's own established
per-EP convention — **recommended (revised)**; (b) append new methods
directly to `tests/EP002/test_shell.py`'s existing `ShellTest` class
— originally recommended in the prior revision of this document, **now
rejected**.

**Recommended option:** (a).

**Reason (revised):** Direct inspection of `tests/EP061/`, `tests/
EP062/`, `tests/EP063/`, and `tests/EP064/` confirms each is its own
directory, each with its own `__init__.py`, each self-contained (no
cross-EP imports — explicitly stated in, e.g., `tests/EP061/
test_scheduler_shutdown.py`'s own docstring and `tests/EP064/
test_memory_persistence_shutdown.py`'s own docstring), each registered
under its own `NAME = "EPxxx"` matching its own directory, and each
requiring exactly one new import line in `src/modules/test_module.py`
(confirmed: `tests.EP061.test_scheduler_shutdown` through
`tests.EP064.test_memory_persistence_shutdown` are each imported on
their own line, in EP order). This is the actual, current,
consistently-applied convention for every one of the four most recent
EPs — not merely "a" precedent among several, but the *only* pattern
this repository's four most recent EPs have followed. The prior
revision of this document reasoned from a much older precedent
(`tests/EP002/test_shell.py`, from EP-002 itself) and from a
misreading of EP-064's own stated reason for creating `tests/EP064/`
("MemoryPersistence had zero pre-existing tests") as though it were
the *only* valid reason a new EP package may be created, rather than
recognizing that EP-062 and EP-063 also each created their own new
directory (`tests/EP062/`, `tests/EP063/`) despite each one modifying
a production class that already had a pre-existing, dedicated test
file from an *earlier* EP — `BackgroundWorkerService` already had
`tests/EP036/test_background_worker_service.py` before EP-062 touched
it, and `WorkflowSchedulerService` already had `tests/EP034/
test_workflow_scheduler.py` before EP-063 touched it — meaning "the
production class already has some existing tests elsewhere" has never
actually been this repository's criterion for whether a new EP earns
its own test directory; each of the four most recent EPs gets its own
directory regardless. EP-065 owning its own package is therefore not
an exception to the convention; it is the convention. A dedicated
`tests/EP065/` package also gives EP-065's own new guarantee (Section
14, Acceptance Criteria) an independently identifiable, independently
runnable (`test EP065`) home, matching how every other EP's own
regression proof is independently runnable today, and cleanly
separates "does the pre-existing EP-002 baseline still pass"
(unmodified, re-run as a regression check per Section 11) from "does
EP-065's own new guarantee hold" (a new, EP-065-owned assertion set) —
exactly the kind of clear test ownership this revision requires.

**Alternative rejected:** (b) — based on a reasoning error about this
repository's actual, current convention (corrected above); would also
blur the same "pre-existing baseline vs. new guarantee" distinction
`tests/EP061/` through `tests/EP064/` each already keep separate for
their own EPs.

**Architectural consequence:** A new directory, `tests/EP065/`,
containing `__init__.py` (empty, matching `tests/EP061/__init__.py`
through `tests/EP064/__init__.py` exactly) and one new test module
(e.g. `tests/EP065/test_command_router_malformed_input.py`), whose
test class(es) register with `TestRegistry` under `NAME = "EP065"`.
`src/modules/test_module.py` gains exactly one new import line for
this new module, appended after the existing
`import tests.EP064.test_memory_persistence_shutdown` line, matching
the established ordering convention exactly. `tests/EP002/
test_shell.py` is not modified — it is re-run, unmodified, as part of
Section 11's full-regression pass, and remains the pre-existing
`CommandRouter`/`InteractiveShell` baseline it already was.

---

## 12. Expected File Changes

Identified here for STEP 2's benefit; **not authorized by this
document** (Section 15).

### Expected to change (production)

- `src/core/command_router.py` — `dispatch()`'s body gains one new
  `try`/`except ValueError` block around the existing `_tokenize()`
  call (Section 8). No other line changes.

### Expected to change (tests) — REVISED

- **New:** `tests/EP065/__init__.py` (empty, matching `tests/EP061/
  __init__.py` through `tests/EP064/__init__.py`).
- **New:** `tests/EP065/test_command_router_malformed_input.py` (name
  illustrative; STEP 2 may choose an equally descriptive name)
  containing the `CommandRouter`-level tests, the `InteractiveShell`-
  level test, the `TelegramService`-level test, and the REST
  regression test described in Section 11, each independently
  registered with `TestRegistry` under `NAME = "EP065"`.
- `tests/EP002/test_shell.py` — **unmodified.** Re-run, not edited, as
  part of Section 11's full-regression pass (Owner Decision D10,
  revised).

### Expected to change (test registration) — REVISED

- `src/modules/test_module.py` — exactly one new import line,
  `import tests.EP065.test_command_router_malformed_input`, appended
  after the existing `import tests.EP064.test_memory_persistence_shutdown`
  line, matching the established per-EP import convention (Owner
  Decision D10, revised).

### Explicitly NOT expected to change

See Section 13, Protected Files.

---

## 13. Protected Files

The following must remain byte-identical to their pre-STEP-1 state
through STEP 2, independently verifiable by `diff`/hash comparison at
a future STEP 3:

- `src/core/shell.py` (Owner Decision D6)
- `src/services/telegram_service.py` (Owner Decision D7/D9)
- `src/core/telegram/telegram_router.py` (Owner Decision D7)
- `src/core/telegram/telegram_client.py`
- `src/core/api/api_router.py` (Owner Decision D7)
- `src/core/api/rest_api_server.py` (Owner Decision D7)
- `src/core/api/dto.py`
- `src/core/memory/memory_persistence.py` (Owner Decision D9; EP064-F1
  explicitly deferred, not absorbed)
- `src/services/memory_service.py`
- `src/services/scheduler_service.py`
- `src/services/workflow_scheduler_service.py` (Architecture Debt
  AD-001 explicitly not touched)
- `src/services/background_worker_service.py`
- `src/core/background_workers/background_worker_pool.py`
- `src/services/runtime_service.py`
- `src/modules/runtime_module.py`
- `src/modules/telegram_module.py`
- `src/modules/scheduler_module.py`
- `src/modules/workflow_scheduler_module.py`
- `src/bootstrap.py`
- `src/main.py` (Non-Goals, Section 6)
- `config/config.yaml`
- `docs/architecture/ARCHITECTURE_DEBT.md`
- `docs/architecture/designs/EP059_DESIGN.md` through
  `EP064_DESIGN.md` (all six)
- `docs/architecture/audits/` (every existing file)
- `tests/EP002/test_shell.py` (REVISED — now fully protected; no
  longer an authorized extension point, per Owner Decision D10,
  revised) — all eight pre-existing test methods and the file's
  existing `_StubModule` fixture remain byte-for-byte unchanged; the
  file is re-run, unmodified, as part of Section 11's full-regression
  pass.
- `tests/EP043/test_rest_api.py`, `tests/EP051/test_browser.py`,
  `tests/EP052/test_file.py`, `tests/EP059/test_runtime.py`,
  `tests/EP060/test_runtime_lifecycle.py`,
  `tests/EP061/test_scheduler_shutdown.py`,
  `tests/EP062/test_background_worker_status.py`,
  `tests/EP063/test_workflow_scheduler_shutdown.py`,
  `tests/EP064/test_memory_persistence_shutdown.py` (run as full
  regression, per Section 11, but not modified)
- `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `docs/BACKLOG.md`,
  `docs/architecture/JARVIS_ROADMAP.md`

`src/modules/test_module.py` is **explicitly excluded** from this
list — it is the one file, besides `src/core/command_router.py` and
the new `tests/EP065/` package itself, this EP is authorized to
change, and only by exactly one new import line appended at the end
of the existing per-EP import block (Section 12, revised).

---

## 14. Acceptance Criteria

1. `CommandRouter.dispatch("")`, `dispatch("   ")`,
   `dispatch("nosuchmodule help")`, and every other pre-existing
   `tests/EP002/test_shell.py` scenario produce byte-identical
   `CommandResult` values to before this EP.
2. `CommandRouter.dispatch(<any string containing an unbalanced `"`
   or `'`>)` returns a `CommandResult(success=False, ...)` and never
   raises, for every malformed-quoting pattern this design document's
   Section 2.1 identified (trailing unmatched, leading unmatched, bare
   single-character, multiple non-pairing).
3. The returned `CommandResult.message` for case 2 is distinct in
   wording from both "Unknown module: ..." and "Internal error while
   executing '...'.", includes the underlying `shlex` exception's own
   reason text (e.g. "No closing quotation"), and does **not** include
   the original raw input text (Owner Decision D4, revised).
3a. The corresponding `logger.error(...)` call for case 2 likewise
    does not include the original raw input text.
4. No registered module's `execute()` method is ever invoked for a
   malformed-quoting input.
5. `_tokenize()`'s own body, signature, and docstring are unchanged;
   it still raises `ValueError` for malformed quoting exactly as
   before.
6. `InteractiveShell.run()`, given a mocked `input()` sequence
   containing one malformed line, does not raise, displays the
   returned failure message, and continues to process at least one
   subsequent line correctly.
7. A real `TelegramService`, given a fake client that returns one
   malformed-text message followed by one well-formed message across
   two poll cycles, keeps its polling thread alive after the first and
   correctly processes the second.
8. `ApiRouter.dispatch_command()`, given an argument value containing
   unbalanced quote characters, does not raise, and the module it
   dispatches to receives that value's exact original text.
9. `src/core/shell.py`, `src/services/telegram_service.py`,
   `src/core/telegram/telegram_router.py`, `src/core/api/api_router.py`,
   `src/core/api/rest_api_server.py`, `src/core/memory/
   memory_persistence.py`, `src/services/workflow_scheduler_service.py`,
   and every other file in Section 13's Protected Files list are
   confirmed byte-identical to their pre-STEP-1 state.
10. `src/modules/test_module.py` contains exactly one new line — the
    import for the new `tests/EP065/` test module — and is otherwise
    unmodified (Owner Decision D10, revised).
11. `tests/EP002/test_shell.py` is byte-identical to its pre-STEP-1
    state (Section 13, revised); `tests/EP065/` is a new, independent
    package whose own test class(es) register under `NAME = "EP065"`
    and are independently runnable (`test EP065`).
12. Every full-regression suite listed in Section 11 passes
    unmodified, including a project-wide `TestRunner.run_all()` run
    with zero new failures relative to the pre-EP-065 baseline.
13. `docs/architecture/designs/EP065_DESIGN.md` is the only file
    created or modified during this STEP 1 design-correction pass.

---

## 15. Validation Plan

STEP 2 must, at minimum:

1. Implement exactly the change described in Section 8, verified by a
   line-level diff against this document's own code block.
2. Run the new `tests/EP065/` package in full and confirm every
   assertion described in Section 11 passes.
3. Run `tests/EP002/test_shell.py` unmodified and confirm all eight
   pre-existing assertions still pass byte-for-byte (Section 13,
   Protected Files).
4. Run every suite listed in Section 11's "Full regression" paragraph
   and confirm zero regressions.
5. Run `TestRunner.run_all()` (the complete, project-wide suite) and
   report the before/after assertion counts, confirming they are
   identical apart from the new `tests/EP065/` assertions this EP adds.
6. Independently re-run this document's own Section 2.1/2.7
   reproduction steps (the exhaustive `shlex` malformed-input matrix,
   and the `shlex.quote()` round-trip matrix) against the actual
   post-fix code, to confirm the design's own evidence still holds
   after implementation, not only before it.
7. Confirm, via `diff`/hash comparison, that every file in Section 13
   (Protected Files) remains byte-identical to its pre-STEP-1 state.

STEP 3 (a future architecture audit, not part of this document) should
additionally re-verify Owner Decisions D1-D10 independently against
the actual implementation, exactly as `EP061_ARCHITECTURE_AUDIT.md`
through `EP064_ARCHITECTURE_AUDIT.md` each did for their own EP's
Owner Decisions.

---

## 16. STEP 2 Implementation Boundary (REVISED)

STEP 2 will implement, and only implement:

1. The one new `try`/`except ValueError` block inside
   `CommandRouter.dispatch()` (Section 8), exactly as specified,
   including the exact narrow exception type (`ValueError`, not
   `Exception`), the exact no-new-local-variable scoping rule (Section
   8's note), and the exact message-content requirements (Owner
   Decisions D3/D4, revised — the parser's own exception reason only,
   never the raw command text, in either the returned
   `CommandResult.message` or the log line).
2. A new, dedicated `tests/EP065/` package (`__init__.py` plus one
   test module), containing the tests described in Section 11,
   independently registered under `NAME = "EP065"` (Owner Decision
   D10, revised).
3. Exactly one new import line in `src/modules/test_module.py`, for
   the new `tests/EP065/` test module, appended after the existing
   `tests.EP064.test_memory_persistence_shutdown` import.

**Files expected to change:** exactly the two production/registration
files and the one new test package listed in Section 12 (revised).

**Protected files:** Section 13 (revised) — note in particular that
`tests/EP002/test_shell.py` is now fully protected and must **not**
be edited by STEP 2.

**What must remain unchanged:** every existing line of
`src/core/command_router.py` other than the one new `try`/`except`
block described in Section 8; every existing method's signature and
body across every other file in this repository; every existing test
method's content in `tests/EP002/test_shell.py` (now unmodified, not
extended); every existing import line in `src/modules/test_module.py`;
`CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `docs/BACKLOG.md`,
`docs/architecture/JARVIS_ROADMAP.md`,
`docs/architecture/ARCHITECTURE_DEBT.md`, and every prior EP's design/
audit document.

STEP 2 must not redesign `InteractiveShell`, `TelegramService`,
`TelegramRouter`, `ApiRouter`, `RestApiServer`, `MemoryPersistence`,
or `WorkflowSchedulerService` while implementing this scope, and must
not absorb EP064-F1 or Architecture Debt AD-001.

---

## 17. Final Verification (performed before concluding STEP 1)

- Re-read this complete document end-to-end against the actual,
  current repository content: every file path, line reference, method
  name, and behavioral claim above was independently confirmed via
  direct file reads and direct Python reproduction during this STEP 1
  session (Sections 2, 3), not assumed from memory of the earlier,
  interrupted discovery pass.
- The exhaustive `shlex` malformed-input matrix (Section 2.1) and the
  `shlex.quote()` round-trip matrix (Section 2.7) were both
  independently re-executed during this continuation, against this
  repository's own `_tokenize()` configuration (`posix=True`,
  `whitespace_split=True`, `escape=""`) exactly as it exists in
  `src/core/command_router.py` today — not against a generic `shlex`
  assumption.
- Goals (Section 5) do not contradict Non-Goals (Section 6): every
  Goal names a specific, additive change to `dispatch()`'s own
  contract; every Non-Goal names a specific adjacent file or concern
  intentionally left alone; no overlap.
- Owner Decisions (Section 7) match the Detailed Design (Section 8)
  exactly: D1↔Section 8 (fix lives inside `dispatch()`), D2↔`_tokenize()`
  unchanged, D3↔the new message's distinct wording, D4↔the new
  message's and log line's no-raw-input-echo content (revised), D5↔the
  new `logger.error(...)` call, D6/D7↔Section 6 (narrow claim only:
  no Shell/Telegram/REST production change required for this specific
  defect), D8↔no new type/field, D9↔Section 6 (EP064-F1/AD-001/
  Telegram's own narrower guard all explicitly deferred), D10↔Section
  11/12 (dedicated `tests/EP065/` package, revised).
- File-impact list (Section 12) matches the Detailed Design (Section
  8) and Owner Decision D10 exactly, with no omission or addition.
- Testing Strategy (Section 11) matches the Detailed Design: every
  new branch introduced in Section 8 has at least one corresponding
  named test, and every claim made in Sections 1-3 (shell crash,
  Telegram thread death, REST immunity) has at least one corresponding
  named regression test proving the claim both before conceptually
  (Sections 1-3) and after implementation (Section 15).
- Protected files (Section 13) are consistent with Expected File
  Changes (Section 12): no file appears in both lists.
  `tests/EP002/test_shell.py` is now fully protected (Section 13,
  revised) and correctly does **not** appear in Section 12's
  expected-to-change list; `src/modules/test_module.py` and the new
  `tests/EP065/` package correctly appear only in Section 12, not in
  Section 13's protected list.
- No requirement in this document depends on an undocumented
  assumption: every load-bearing claim (the exact exception type and
  message text `shlex` raises, the exact call sites lacking a guard in
  `InteractiveShell`/`TelegramService`, the exact immunity of the REST
  path, the complete absence of existing test coverage for this
  scenario) was independently verified against current source and via
  direct Python reproduction during this STEP 1 session, not merely
  asserted.
- No previous EP's Owner Decision is contradicted: EP-059 through
  EP-064's own Owner Decisions concern Shell/REST/Background-Workers/
  Scheduler/Workflow-Scheduler/Memory-Persistence lifecycle
  coordination exclusively; none of them make any claim about
  `CommandRouter.dispatch()`'s own exception-safety contract, so none
  can be contradicted by this EP addressing that contract for the
  first time. EP-052's Owner Decision D11 (the `_tokenize()` method
  itself) is extended, not reversed: `_tokenize()`'s own behavior for
  Windows paths is independently re-verified unchanged (Section 11's
  regression test).
- EP-065 does not duplicate an existing capability: no prior EP added
  any exception-safety guard to `CommandRouter.dispatch()`'s tokenize
  call (confirmed, Section 2.9's exhaustive pre-existing-test-coverage
  search, and Section 2.1's confirmation that `_tokenize()` has never
  had more than its one, current call site).
- Confirmed: this STEP 1 session created **only**
  `docs/architecture/designs/EP065_DESIGN.md`. No production code,
  test, configuration, dependency, `CHANGELOG.md`,
  `docs/RELEASE_NOTES.md`, `docs/BACKLOG.md`,
  `docs/architecture/JARVIS_ROADMAP.md`,
  `docs/architecture/ARCHITECTURE_DEBT.md`, or other documentation
  file was created or modified during this investigation.

**STEP 1 is complete. Do not proceed to STEP 2.**
