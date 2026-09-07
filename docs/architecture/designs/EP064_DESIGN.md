# EP-064 — MemoryPersistence Shutdown Coordination

Status: **STEP 1 — DESIGN ONLY. Not implemented.**

---

## 0. How this scope was derived

Neither `docs/architecture/JARVIS_ROADMAP.md` nor `docs/BACKLOG.md`
names an EP-064 scope; both say "none yet defined," and no EP-059
through EP-063 design/audit document names a specific "next EP"
candidate for this number either. Per this task's instructions, this
document discovers EP-064's scope from repository evidence rather
than inventing one.

### 0.1 Candidates investigated

**Candidate A — Telegram Gateway shutdown coordination.** `TelegramService`
(EP-012) auto-starts a daemon polling thread (`_poll_thread`) when
`telegram.enabled` and `telegram.auto_start` are both true (both
default `false` in `config/config.yaml`), and this thread is never
observed or coordinated by `RuntimeService`. This is the exact
candidate `EP063_DESIGN.md`'s own STEP 1 already investigated and
explicitly rejected (cited in `JARVIS_ROADMAP.md`'s EP-063 entry: "a
manual escape hatch already available and zero pre-existing test
coverage"). Independently re-verified during this STEP 1:
`TelegramModule._actions` already contains a `"stop"` key wired to
`TelegramService.stop()` (confirmed, `telegram_module.py` line 47/85;
`telegram_service.py` lines 147-160) — a real, existing, idempotent
manual escape hatch — and `tests/` contains no `EP012`-numbered
directory or any other test file for `TelegramService`/`TelegramModule`/
`TelegramClient`/`TelegramRouter` (confirmed via repository-wide
search; only `tests/EP040/test_telegram_info_service.py` and
`tests/EP040/test_telegram_info_module.py` exist, and those cover the
architecturally separate, read-only `TelegramInfoService`, not this
one). Both of EP-063's stated rejection reasons independently
reconfirmed true today. Not selected.

**Candidate B — MemoryPersistence shutdown coordination (selected).**
`MemoryPersistence` (`src/core/memory/memory_persistence.py`, EP-013.2)
auto-starts a daemon auto-save thread (`_save_thread`) whenever
`memory.enabled`, `memory.persistent`, and `memory.auto_save` are all
true. Confirmed in `config/config.yaml` lines 24-28: **all three
default to `true`** — this is the only one of the four
previously-closed-or-considered "auto-started background thread"
candidates (Scheduler pre-EP-061, WorkflowScheduler pre-EP-063,
Telegram) that is unconditionally active in every default
installation, not merely under an opt-in flag. Unlike Telegram, there
is **no manual escape hatch at all**: `MemoryModule._actions`
(`src/modules/memory_module.py` lines 56-67) contains no `"start"` or
`"stop"` key, and `MemoryService` (`src/services/memory_service.py`)
exposes no public `stop()`/`shutdown()` method of any kind — confirmed
by a full listing of its public methods (Section 2.4 below). This is
a strictly more severe instance of the same defect class EP-061 closed
for `SchedulerService` and EP-063 closed for `WorkflowSchedulerService`:
an auto-started, always-on-by-default background thread with **zero**
public way to stop it, anywhere in the codebase. Test coverage is
also absent (confirmed: no `tests/EP013*` directory and no test file
anywhere constructs `MemoryPersistence` directly or exercises its
auto-save lifecycle — see Section 2.8), matching Telegram's own
coverage gap, but this does not carry the same disqualifying weight
here because (a) Candidate B has no competing "manual escape hatch
already covers this" reason to prefer leaving it alone, and (b) the
underlying implementation shape is small and near-identical to
`SchedulerService.shutdown()`'s already-proven EP-061 pattern, so the
STEP 2 testing burden is bounded and precedented rather than open-ended
(unlike Telegram's live network/Bot-API surface).

**Candidate C — REST API authentication.** Not re-investigated in
depth here; already disclosed as real but architecturally enormous by
every prior EP back through `EP059_DESIGN.md` Section 14, and
explicitly rejected by EP-063's own STEP 1 for the same reason. No new
evidence in this repository changes that conclusion. Not selected.

**Architecture Debt items (AD-001 through AD-009,
`docs/architecture/ARCHITECTURE_DEBT.md`).** Explicitly ineligible per
that document's own rules ("Never fix Architecture Debt during a
normal Engineering Phase (EP). Architecture Debt is addressed only
during a dedicated cleanup milestone."). None of them describe the
`MemoryPersistence` gap this document addresses; AD-005 is the closest
in spirit (background-worker shutdown wiring into `main.py`) but names
a different file pair (`background_worker_service.py`/`main.py`) and a
different, already-superseded mechanism (EP-060 already wired
`BackgroundWorkerService.shutdown()` into `RuntimeService.shutdown()`,
which AD-005 itself does not mention, since AD-005 predates EP-060).
Not applicable to EP-064's scope determination either way.

### 0.2 Final selection

**Candidate B, MemoryPersistence Shutdown Coordination**, is the
strongest, most evidence-supported EP-064 scope: a real, code-verified,
default-on gap with no existing mitigation, structurally identical to
two already-successful precedents (EP-061, EP-063), and bounded in
size (the smallest architecturally correct scope, per Section 4/5
below).

---

## 1. Problem Statement

`MemoryPersistence` (`src/core/memory/memory_persistence.py`, EP-013.2)
owns a background daemon thread (`_save_thread`, target
`_auto_save_loop`) that periodically calls `save()` every
`memory.auto_save_interval` seconds (default 60), started
automatically by `MemoryService.__init__` → `MemoryPersistence.start()`
whenever `memory.enabled` (default `true`), `memory.persistent`
(default `true`), and `memory.auto_save` (default `true`) all hold —
i.e., in every default Jarvis installation.

There is currently **no public method anywhere in this repository**
that can stop this thread once started:

- `MemoryPersistence` itself exposes `start()`, `load()`, `save()`,
  `is_running()`, `diagnostics()` — no `stop()`/`shutdown()`.
- `MemoryService` (the only class that owns a `MemoryPersistence`
  instance) exposes `status()`, `doctor()`, `export()`, `import_()`,
  `save()`, `providers_status()`, `current_provider()`, `use_provider()`,
  `register_provider()`, plus the CRUD surface (`set`/`get`/`delete`/
  `clear`/`list_entries`) — no `stop()`/`shutdown()` passthrough.
- `MemoryModule`'s CLI action map (`src/modules/memory_module.py`)
  contains no `"start"`/`"stop"` action at all (unlike
  `SchedulerModule`, `WorkflowSchedulerModule`, and `TelegramModule`,
  each of which has at least a manual stop path).
- `RuntimeService` (`src/services/runtime_service.py`, EP-059,
  widened by EP-060/061/063) — the one place `Bootstrap.shutdown()`
  already delegates coordinated subsystem shutdown to — has no
  constructor parameter, no `status()` field, and no `shutdown()` step
  for Memory/`MemoryPersistence` at all.
- `Bootstrap.shutdown()` (`src/bootstrap.py`) nulls
  `self._rest_api_server`/`self._background_worker_service` and
  (via `RuntimeService.shutdown()`) stops the Scheduler and Workflow
  Scheduler tick loops, but never touches `self._memory_service` or
  anything inside it.

Because `_save_thread` is a daemon thread (`daemon=True`, confirmed
line 187-188), this does not hang process exit (`src/main.py`'s
`sys.exit(main())` terminates the interpreter regardless of any live
daemon thread) — so this is not the same *hang* risk `AD-005` describes
for `BackgroundWorkerService`. The actual problems are:

1. **No observability.** `RuntimeService.status()` cannot report
   whether the Memory subsystem's auto-save loop is actually running —
   unlike every other auto-started thread in this repository
   (Scheduler, Workflow Scheduler, Background Workers), which
   `RuntimeStatus` already surfaces.
2. **No coordinated shutdown.** `Bootstrap.shutdown()`/
   `RuntimeService.shutdown()` — the one place this repository has
   established as the single, ordered, idempotent shutdown sequence
   for every other auto-started background thread — does not reach
   this one at all. A caller that relies on `RuntimeService.shutdown()`
   to mean "every background thread this process started has been
   signaled to stop" (as `EP060_DESIGN.md`/`EP061_DESIGN.md`/
   `EP063_DESIGN.md` each frame it) gets an incomplete guarantee today.
3. **No manual escape hatch of any kind**, unlike Telegram
   (`telegram stop`) or the pre-EP-061/pre-EP-063 states of Scheduler/
   Workflow Scheduler (which, even before their own `shutdown()`
   methods existed, were never silently uncontrollable in quite the
   same total sense, since `SchedulerService`/`WorkflowSchedulerService`
   are the more actively-managed subsystems with richer existing CLI
   surfaces). Memory's auto-save loop is the most completely
   unreachable background thread in this codebase today.

This is the same defect class EP-061 closed for `SchedulerService` and
EP-063 closed for `WorkflowSchedulerService`, now confirmed present in
a third, default-on subsystem that no prior EP's scope statement ever
mentioned (EP-059 through EP-063 each explicitly fenced their own scope
to Shell/REST/Background-Workers/Scheduler/Workflow-Scheduler; none
discussed Memory).

---

## 2. Evidence / Current Architecture

### 2.1 `MemoryPersistence` lifecycle (`src/core/memory/memory_persistence.py`, 269 lines)

- `__init__(config, store)`: stores `_config`, `_store`; creates
  `_save_lock: threading.Lock`, `_save_thread: threading.Thread | None
  = None`, `_stop_event: threading.Event`. Does **not** start
  anything itself.
- `start()`: no-op if `is_persistent()` is False; otherwise calls
  `load()` and, if `is_auto_save()`, calls `_start_auto_save_loop()`.
  Docstring states it is "intended to be called once, by
  MemoryService, after `memory.enabled` has already been confirmed
  True" — confirmed true at the one call site
  (`MemoryService.__init__`, guarded by `if self._is_enabled():`).
- `_start_auto_save_loop()`: under `_save_lock`, no-ops if
  `_save_thread is not None`; otherwise clears `_stop_event`, creates
  `threading.Thread(target=self._auto_save_loop, name="memory-auto-save",
  daemon=True)`, and starts it.
- `_auto_save_loop()`: `while not self._stop_event.wait(interval):
  save()` (logs on failure), then logs "Memory auto-save stopped."
  once the loop exits. **This is structurally identical in shape to
  `SchedulerService._tick_loop()`** (EP-011/EP-061) and
  `WorkflowSchedulerService._tick_loop()` (EP-034/EP-063): a
  `while not self._stop_event.wait(interval):` loop with no other
  exit path.
- `is_running()`: `with self._save_lock: return self._save_thread is
  not None and self._save_thread.is_alive()`.
- **No `stop()`/`shutdown()` method exists.** Confirmed by a full
  method listing (`__init__`, `start`, `is_persistent`, `is_auto_save`,
  `auto_save_interval`, `storage_path`, `load`, `save`, `is_running`,
  `diagnostics`, `_start_auto_save_loop`, `_auto_save_loop`,
  `_validate_auto_save`, `_validate_persistence`, `_path_writable`) —
  eleven public/protected methods, none of which signals
  `_stop_event` or joins `_save_thread`.

### 2.2 Auto-save thread creation conditions

Confirmed via `config/config.yaml` lines 20-29 and
`MemoryPersistence.is_persistent()`/`is_auto_save()`:

```
memory.enabled: true            # gates MemoryPersistence.start() being called at all
memory.persistent: true         # gates start()'s load()+auto-save-loop branch
memory.auto_save: true          # gates the auto-save-loop branch specifically
memory.auto_save_interval: 60   # seconds between saves
```

All three gating flags default to `true`. A fresh checkout with an
unmodified `config/config.yaml` therefore auto-starts this thread on
every `Bootstrap.initialize()` call. This is a stronger default than
Scheduler (`scheduler.enabled`/`scheduler.auto_start`, also both
`true` by default, confirmed already true per `EP060_DESIGN.md`
Section 5.3) or Workflow Scheduler (`workflow_scheduler.auto_start`
defaults `false`, per `EP063_DESIGN.md` Section 2.4) or Telegram
(`telegram.auto_start` defaults `false`).

### 2.3 Thread loop/exit behavior — no implicit or indirect termination mechanism

Confirmed by direct reading: `_auto_save_loop()`'s only exit condition
is `self._stop_event.wait(interval)` returning `True`, which only
happens if `_stop_event.set()` is called. **No code anywhere in this
repository calls `self._persistence._stop_event.set()`** (confirmed by
a repository-wide search for `_stop_event.set` limited to this file —
zero matches outside the pattern this document proposes adding). The
thread runs for the entire process lifetime once started, with no
implicit timeout, no exception-triggered exit, and no cooperative
shutdown signal from any existing caller. `src/main.py`'s
`_save_memory_on_shutdown()` (lines 56-74) calls `bootstrap` for an
explicit final `save()` after `bootstrap.shutdown()` returns, but this
is a one-time explicit save — it does not touch `_save_thread` or
`_stop_event`, and does not stop the loop; it only adds one more save
on top of whatever the (still-running, until process exit) loop was
already doing. There is no other indirect termination path.

### 2.4 `MemoryService` ownership and public surface (`src/services/memory_service.py`, 588 lines)

`MemoryService.__init__` constructs exactly one `MemoryPersistence`
instance (`self._persistence = MemoryPersistence(config=config,
store=store)`) and calls `self._persistence.start()` if
`self._is_enabled()`. No other class constructs or holds a
`MemoryPersistence` reference. Full public method list (confirmed by
direct reading): `set`, `get`, `delete`, `clear`, `list_entries`,
`status`, `doctor`, `export`, `import_`, `save`, `providers_status`,
`current_provider`, `use_provider`, `register_provider` — 13 public
methods, none of which is `stop`/`shutdown`. `status()` (Section 2.6)
already reads three `MemoryPersistence` accessors
(`is_persistent()`, `is_auto_save()`, `auto_save_interval()`) but not
`is_running()` — the one existing signal that could distinguish
"configured to auto-save" from "the thread is actually alive right
now" is read by `doctor()`'s `_validate_auto_save()` internally, but
never surfaced on `MemoryStatus` itself.

`MemoryService.__init__` can raise `MemoryProviderError` — but only
from `_build_default_manager()` when `manager is None` and
`memory.default_provider` is not a non-empty string (confirmed,
`_build_default_manager` static method, lines ~531-560). This is
unrelated to persistence/auto-save configuration: `is_persistent()`,
`is_auto_save()`, and `auto_save_interval()` are all read live via
`bool(...)`/`float(...)` coercion with no validation and no raise
path. **There is no `MemoryPersistenceError` type, and
`MemoryPersistence` never raises for a malformed `auto_save_interval`
or any other config value** — confirmed by reading the entire file;
every config read goes through `Config.get(key, default)` and a bare
type coercion, never a guard clause that raises.

### 2.5 `MemoryModule` CLI surface (`src/modules/memory_module.py`)

`_actions` (lines 56-67): `{"status", "doctor", "get", "set",
"delete", "clear", "list", "export", "import", "providers", "use",
"help"}` — 12 actions, confirmed no `"start"`/`"stop"`/`"shutdown"`
key. Unlike `SchedulerModule`/`WorkflowSchedulerModule`/
`TelegramModule`, Memory's CLI surface has never exposed any lifecycle
control over the auto-save loop specifically.

### 2.6 `MemoryStatus`/`MemoryDoctorReport` (frozen dataclasses, `memory_service.py`)

`MemoryStatus` has exactly one construction call site
(`MemoryService.status()`, entirely keyword-based) with 11 fields:
`total_entries`, `namespace_count`, `persistent_entries`,
`session_entries`, `enabled`, `persistent`, `storage_file`,
`auto_save`, `auto_save_interval`, `max_entries`, `default_ttl` — no
default values on any field (all positional-or-keyword, required).
`auto_save: bool` reflects `is_auto_save()` (the **configuration**
flag), not whether the thread is actually alive.
`MemoryDoctorReport.auto_save_valid` is a correctness check
(`_validate_auto_save`: "does the running state match configuration,"
Section 2.1) — also not a direct "is it running right now" signal
exposed as its own field.

### 2.7 `Bootstrap` construction and ownership (`src/bootstrap.py`)

`self._memory_service: MemoryService | None = None` is declared at
`__init__` (line 265) and assigned inside `_build_command_router()`
(lines 440-450):

```python
try:
    memory_store = MemoryStore()
    memory_service = MemoryService(config=config, store=memory_store)
    self._memory_service = memory_service
    router.register(MemoryModule(memory_service))
except MemoryProviderError as exc:
    logger.error(...)
    self._memory_service = None
```

This assignment happens unconditionally on the success path
regardless of `memory.enabled` (only an invalid
`memory.default_provider` triggers the `except` branch — the
"disabled" case still produces a valid `MemoryService` instance with
`_is_enabled() == False`, per Section 2.4). A public
`bootstrap.memory_service` property already exists (confirmed, line
~2489), returning `self._memory_service`. **Unlike Telegram (which
required a first-time promotion from local variable to instance
attribute in `EP060_DESIGN.md`'s own D4 discussion of Telegram), the
`self._memory_service` attribute and its public property already
exist today** — this EP is the first to make `RuntimeService` consume
it, not the first to store it.

`Bootstrap.shutdown()` (lines 2172-2225): delegates to
`self._runtime_service.shutdown()` if constructed, else falls back to
a direct `self._rest_api_server.stop()` call; nulls
`self._rest_api_server`/`self._background_worker_service`
unconditionally at the end. **Never references `self._memory_service`
anywhere in this method today.**

`Bootstrap.initialize()` constructs `RuntimeService` (lines 356-364)
only after `_build_command_router()` has returned — so
`self._memory_service` is already assigned (Section 2.7 above,
whether `None` or a real instance) by the time `RuntimeService.__init__`
runs, exactly the same timing guarantee `EP059_DESIGN.md` Section 8
already establishes for every other dependency `RuntimeService` reads.

### 2.8 Existing test coverage

Confirmed via repository-wide search: **no test file anywhere
constructs `MemoryPersistence` directly**, and no `tests/EP013*`
directory exists. `MemoryService` itself is constructed in four other
EPs' test files (`tests/EP023/test_memory_manager.py`,
`tests/EP025/test_long_term_memory.py`, `tests/EP026/
test_semantic_search.py` — indirectly, via `LongTermMemoryService` —
and `tests/EP054/test_reflection.py`, which uses a hand-written
`_FakeMemoryService` stub, not the real class at all), but none of
these exercises `MemoryPersistence`'s auto-save lifecycle, calls
`is_running()`, or asserts anything about the background thread —
they use `MemoryService` purely for its CRUD/provider surface. This
confirms Section 0.1's claim: EP-064 is adding coordinated shutdown to
a subsystem with **zero existing lifecycle test coverage**, the same
gap Telegram has, but (per Section 0.2) not disqualifying here because
nothing else already mitigates it.

### 2.9 `RuntimeService`/`RuntimeModule`/`Bootstrap` shutdown architecture established by EP-060–063

Confirmed by direct reading of `src/services/runtime_service.py`
(current, post-EP-063 state):

- `RuntimeStatus` (frozen dataclass): 13 fields today, the last four
  added by EP-060/063 as defaulted, keyword-only-in-practice fields
  appended last (`scheduler_active=False`,
  `scheduler_jobs_registered=0`, `workflow_scheduler_active=False`,
  `workflow_scheduler_entries_registered=0`).
- `RuntimeShutdownReport` (frozen dataclass): 8 fields, same
  defaulted-and-appended-last pattern
  (`scheduler_was_active=False`/`scheduler_stopped=True`,
  `workflow_scheduler_was_active=False`/
  `workflow_scheduler_stopped=True`).
- `RuntimeService.__init__`: `started_at`, `rest_api_server`,
  `background_worker_service`, `shell` (all required/positional), then
  `scheduler_service: SchedulerService | None = None`,
  `workflow_scheduler_service: WorkflowSchedulerService | None = None`
  — each new dependency added as a keyword-defaulted trailing
  parameter, preserving every prior call site.
- `status()`: reads each dependency defensively (`if self._x is not
  None: ...`), never raises, defaults every field to `False`/`0` for a
  `None` dependency.
- `shutdown()`: reads `<x>_was_active` from `.status().running` (or
  `.is_running`, for `RestApiServer`) **before** calling the
  subsystem's own stop primitive, then calls it, in a fixed, linear,
  unconditional sequence with no `try`/`except` — REST API Server,
  then Scheduler, then Workflow Scheduler, then Background Worker
  Service (confirmed, Section "3. Shutdown ordering" of
  `EP063_ARCHITECTURE_AUDIT.md`, independently re-confirmed here by
  reading the current `shutdown()` body directly, lines ~408-449).
  Each step's `<x>_stopped` field is the `bool` the subsystem's own
  `shutdown()` method returns, forwarded unchanged; a `None`
  dependency defaults `<x>_stopped` to `True` ("nothing to do counts
  as success").
- `RuntimeModule._status()` (`src/modules/runtime_module.py`, lines
  87-118): appends one `"<Subsystem> : ACTIVE/INACTIVE"` line per
  observed subsystem, plus a conditional detail line when active,
  exactly mirroring the dataclass fields above. `_actions` is `{
  "status", "help" }` — no mutating action exists or has ever existed
  here (Owner Decision D1, first established `EP060_DESIGN.md` Section
  9.2, re-verified unbroken by every subsequent EP).
- `Bootstrap.shutdown()`: unconditionally calls
  `self._runtime_service.shutdown()` when constructed; never nulls
  `self._scheduler_service`/`self._workflow_scheduler_service`
  (both remain fully usable — `status()`, manual `run()`/`run_now()`,
  `list_*()` all still work — after their tick loops stop), but does
  null `self._rest_api_server`/`self._background_worker_service`
  (both become meaningfully unusable once stopped).

This is the exact, already-proven shape EP-064 extends.

---

## 3. Gap Analysis

| Subsystem | Auto-started thread | Default | Manual stop | `RuntimeService`-coordinated | Test coverage |
|---|---|---|---|---|---|
| Scheduler (EP-011) | Yes | on | Yes (EP-061 `shutdown()`) | Yes (EP-061) | Yes (`tests/EP061/`) |
| Workflow Scheduler (EP-034) | Yes | off | Yes (EP-063 `shutdown()`) | Yes (EP-063) | Yes (`tests/EP063/`) |
| Background Workers (EP-036) | Yes (pool threads) | on | Yes (`shutdown()`, EP-036) | Yes (EP-060) | Yes (`tests/EP036/`, `EP062`) |
| REST API Server (EP-043) | N/A (socket server) | on | Yes (`stop()`) | Yes (EP-059) | Yes |
| **Telegram (EP-012)** | Yes | **off** | **Yes** (`stop()`) | **No** | **No** |
| **Memory auto-save (EP-013.2)** | Yes | **on** | **No** | **No** | **No** |

Memory auto-save is the only row with both "on by default" and "no
manual stop" — the strictly worst combination in this table, and the
one EP-064 closes.

---

## 4. Goals

1. Add a public, idempotent `MemoryPersistence.shutdown(wait: bool =
   True, timeout: float | None = None) -> bool` method, structurally
   mirroring `SchedulerService.shutdown()` (EP-061), that signals
   `_stop_event` and joins `_save_thread`.
2. Add a thin `MemoryService.shutdown(wait: bool = True, timeout:
   float | None = None) -> bool` passthrough, mirroring how
   `SchedulerModule`/`WorkflowSchedulerModule` do **not** need such a
   passthrough (those modules call their service's `shutdown()`
   directly) — here the passthrough exists because `RuntimeService`
   depends on the **`MemoryService`** layer, not on
   `MemoryPersistence` directly (Section 6.1 rationale).
3. Widen `MemoryStatus` with one new field,
   `auto_save_running: bool`, reflecting
   `MemoryPersistence.is_running()` — distinct from the existing
   `auto_save: bool` (configuration flag).
4. Widen `RuntimeStatus`/`RuntimeShutdownReport` with two new
   defaulted, appended-last fields each (`memory_persistence_active`/
   `memory_persistence_auto_save_running`... — see Section 6.3 for
   exact naming), following the exact EP-060/061/063 pattern.
5. Widen `RuntimeService.__init__` with one new keyword-defaulted
   `memory_service: MemoryService | None = None` parameter.
6. Widen `RuntimeService.shutdown()`'s sequence with a fifth step,
   positioned per Owner Decision D2 (Section 14).
7. Wire `Bootstrap.initialize()` to pass `memory_service=
   self._memory_service` into the existing `RuntimeService(...)` call.
8. Widen `RuntimeModule._status()` with one new display block,
   mirroring the Scheduler/Workflow Scheduler blocks exactly.
9. Close the gap with the smallest possible new abstraction: no new
   module, no new file, no new configuration key, no new CLI/REST/
   Telegram-reachable action.

## 5. Non-Goals

- No new `MemoryModule` CLI action (no `"start"`/`"stop"`/`"shutdown"`
  key added to `_actions`) — matches Owner Decision D1 precedent from
  EP-061/EP-063 (Section 14, D1 below).
- No new configuration key (e.g. no `memory.shutdown_timeout`) — see
  Owner Decision D4 (Section 14): the join timeout is a fixed
  constant, mirroring `SchedulerService`'s EP-061 Owner Decision D4
  precedent, not `WorkflowSchedulerService`'s EP-063 configurable-key
  precedent.
- No change to `MemoryStore`, `MemoryManager`, `MemoryProvider`, or any
  provider-orchestration code (EP-023) — this EP touches only the
  disk-backed auto-save lifecycle, not the in-memory store or provider
  system.
- No change to `load()`, `save()`, `export()`, `import_()`, or any
  other existing `MemoryPersistence`/`MemoryService` method's body —
  purely additive.
- No change to `_auto_save_loop()`'s save cadence, error handling, or
  logging.
- No change to `Bootstrap.shutdown()`'s existing null-out lines
  (`self._rest_api_server = None`, `self._background_worker_service =
  None`) — `self._memory_service` is explicitly not added to this list
  (Owner Decision D8, Section 14).
- No change to `main.py`'s `_save_memory_on_shutdown()` — it continues
  to perform its own explicit final `save()` call after
  `bootstrap.shutdown()` returns, unrelated to whether the auto-save
  *loop* itself was already stopped.
- No absorption of `EP063_ARCHITECTURE_AUDIT.md` Findings F1-F6.
  Those findings are scoped entirely to
  `WorkflowSchedulerService.shutdown()` and its test suite
  (`tests/EP063/test_workflow_scheduler_shutdown.py`) — a different
  file this document does not touch. **F1 (missing concurrent-shutdown
  tests for `WorkflowSchedulerService`), F2 (design-narrative precision
  about `tick()` iterating multiple due entries), F3 (missing
  `ScheduledWorkflow.enabled`-unchanged assertion), F4 (`wait=False`
  stale-thread-reference NOTE), F5 (untested `0`/boolean
  `shutdown_timeout` edge cases), and F6 (one causally-guaranteed test
  assertion) all remain exactly as EP-063's audit left them: disclosed,
  not remediated, and explicitly deferred to a future, separately-
  scoped step at the owner's discretion — not silently folded into
  EP-064, which does not modify `workflow_scheduler_service.py`,
  `runtime_service.py`'s Workflow-Scheduler-specific lines beyond the
  additive widening in Section 6.4, or
  `tests/EP063/test_workflow_scheduler_shutdown.py` at all.**
- No attempt to close Telegram's or REST API authentication's own,
  separately-disclosed gaps (Section 0.1, Candidates A/C) — explicitly
  out of scope for this EP.
- No refactor of `memory_service.py` despite it already exceeding
  `AI_GENERATION_STANDARD.md`'s 500-line soft limit (588 lines today,
  confirmed) — the new passthrough method is kept to the minimum
  possible line count (Owner Decision D7, Section 14) rather than
  triggering an unrelated file-size cleanup, consistent with every
  prior EP's practice of not opportunistically refactoring a file it
  touches for an unrelated reason.

---

## 6. Proposed Architecture

### 6.1 `MemoryPersistence.shutdown()`

New method, added to `src/core/memory/memory_persistence.py`,
structurally mirroring `SchedulerService.shutdown()` (`scheduler_service.py`
lines 251-296) exactly, substituting this file's existing attribute
names (`_save_lock` for `_lifecycle_lock`, `_save_thread` for
`_tick_thread`):

```python
_DEFAULT_SHUTDOWN_TIMEOUT: float = 5.0
"""Fixed join timeout for `shutdown()` (Owner Decision D4)."""

def shutdown(self, wait: bool = True, timeout: float | None = None) -> bool:
    """Stop the background auto-save loop, if one is running.

    Safe to call regardless of whether the auto-save loop was ever
    started (e.g. 'memory.auto_save: false', or already stopped) --
    reports success immediately since there is nothing to stop. Does
    not affect any entry already written to 'memory.storage_file' or
    the in-memory MemoryStore -- only the periodic background save is
    stopped; `save()` remains callable manually afterward.

    Args:
        wait: If True (default), block until the auto-save thread has
            exited or `timeout` elapses. If False, signal the stop and
            return immediately without joining.
        timeout: Maximum seconds to wait when `wait` is True. Defaults
            to `_DEFAULT_SHUTDOWN_TIMEOUT` (5.0) when not given
            explicitly.

    Returns:
        True if the auto-save loop is confirmed not running after this
        call (including if it was never running to begin with); False
        if `wait=True` and the thread did not exit within `timeout`.
    """
    with self._save_lock:
        thread = self._save_thread
        if thread is None:
            return True
        self._stop_event.set()

    if not wait:
        return not thread.is_alive()

    resolved_timeout = timeout if timeout is not None else self._DEFAULT_SHUTDOWN_TIMEOUT
    thread.join(timeout=resolved_timeout)
    stopped = not thread.is_alive()
    if stopped:
        with self._save_lock:
            if self._save_thread is thread:
                self._save_thread = None
    return stopped
```

No `_resolve_shutdown_timeout()` helper is needed (unlike
`SchedulerService`'s own, which exists solely to document/centralize
why no config key is read) — Owner Decision D4 (Section 14) keeps this
inline as a class constant, since there is only one call site for it
and no coercion/validation logic to centralize (unlike
`BackgroundWorkerService`/`WorkflowSchedulerService`'s configurable-key
variant, which needs a dedicated resolver to validate the config
value).

### 6.2 `MemoryService.shutdown()`

New method, added to `src/services/memory_service.py`, a thin,
one-line-body passthrough (kept minimal per Owner Decision D7,
Section 14, given this file's existing size):

```python
def shutdown(self, wait: bool = True, timeout: float | None = None) -> bool:
    """Stop the Memory subsystem's background auto-save loop, if running.

    Passthrough to `MemoryPersistence.shutdown()`. Invoked internally
    by `RuntimeService.shutdown()` -- not exposed as a `MemoryModule`
    CLI/REST/Telegram action (Owner Decision D1). Does not affect the
    in-memory MemoryStore, the Memory Manager, or any registered
    provider -- `set`/`get`/`delete`/`clear`/`list_entries`/
    `export`/`import_`/manual `save()` all remain correct and callable
    afterward.
    """
    return self._persistence.shutdown(wait=wait, timeout=timeout)
```

**Why `RuntimeService` depends on `MemoryService`, not
`MemoryPersistence` directly:** every existing `RuntimeService`
dependency is a *Service*-layer object
(`SchedulerService`/`WorkflowSchedulerService`/
`BackgroundWorkerService`), never a lower-level component a Service
owns internally (`Scheduler`, `WorkflowSchedulerEngine`,
`BackgroundWorkerPool`). `MemoryPersistence` is exactly such a
lower-level, Service-owned component relative to `MemoryService` — the
same ownership shape. Reaching past `MemoryService` to hold a direct
`MemoryPersistence` reference would break this repository's own,
so-far-unbroken layering convention, confirmed at every one of
`RuntimeService`'s four existing dependencies.

### 6.3 `MemoryStatus` widening

One new field, appended last with no default removed from any existing
field (all 11 existing fields remain required/positional-or-keyword,
matching Section 2.6's confirmation of the one, all-keyword call
site — this widening does not need to be defaulted, since the
existing fields aren't defaulted either, but the new field's own value
must be computed from `MemoryPersistence.is_running()`):

```python
auto_save_running: bool
"""Whether the background auto-save thread is actually alive right
now (`MemoryPersistence.is_running()`), distinct from `auto_save`
above, which reflects only the configuration flag. Added by EP-064."""
```

`MemoryService.status()`'s body gains one new line:
`auto_save_running=self._persistence.is_running()`.

### 6.4 `RuntimeStatus` widening

Two new fields, appended last, defaulted (matching every prior
widening's backward-compatibility shape):

```python
memory_persistence_active: bool = False
memory_persistence_entries_saved: int = 0
```

`memory_persistence_active` mirrors `scheduler_active`/
`workflow_scheduler_active`'s naming shape exactly:
`self._memory_service.status().auto_save_running` when
`self._memory_service is not None`, else `False`.
`memory_persistence_entries_saved` mirrors the existing
`<subsystem>_<count-noun>` shape (`scheduler_jobs_registered`,
`workflow_scheduler_entries_registered`,
`background_worker_task_count`) — populated from
`self._memory_service.status().persistent_entries` (the number of
entries currently marked persistent, i.e. eligible to be written by
the next auto-save), `0` when `memory_persistence_active` is `False`
or `self._memory_service is None`, exactly mirroring how
`scheduler_jobs_registered`/`workflow_scheduler_entries_registered`
are only populated when their own `_active` flag is `True`.

### 6.5 `RuntimeShutdownReport` widening

Two new fields, appended last, defaulted:

```python
memory_persistence_was_active: bool = False
memory_persistence_stopped: bool = True
```

Same shape as `scheduler_was_active`/`scheduler_stopped` and
`workflow_scheduler_was_active`/`workflow_scheduler_stopped`. The
class docstring's existing "declaration order ≠ execution order" note
(already present, covering the Scheduler/Workflow-Scheduler pairs)
gains one more clause covering this pair too.

### 6.6 `RuntimeService.__init__` widening

One new, trailing, keyword-defaulted parameter:

```python
def __init__(
    self,
    started_at: float,
    rest_api_server: RestApiServer | None,
    background_worker_service: BackgroundWorkerService | None,
    shell: InteractiveShell | None,
    scheduler_service: SchedulerService | None = None,
    workflow_scheduler_service: WorkflowSchedulerService | None = None,
    memory_service: MemoryService | None = None,
) -> None:
```

Placed last, after `workflow_scheduler_service` — every existing call
site (production `Bootstrap.initialize()`, and every one of
EP-059 through EP-063's own tests) continues to construct a valid
`RuntimeService` unmodified, per the same backward-compatibility
argument `EP060_DESIGN.md` Section 9.1/`EP063_DESIGN.md` Section 6.5
already make for their own new parameters.

### 6.7 `RuntimeService.status()` widening

```python
memory_persistence_active = False
memory_persistence_entries_saved = 0
if self._memory_service is not None:
    memory_status = self._memory_service.status()
    memory_persistence_active = memory_status.auto_save_running
    if memory_persistence_active:
        memory_persistence_entries_saved = memory_status.persistent_entries
```

### 6.8 `RuntimeService.shutdown()` widening

A fifth block, added per Owner Decision D2's ordering (Section 14):

```python
memory_persistence_was_active = False
if self._memory_service is not None:
    memory_persistence_was_active = self._memory_service.status().auto_save_running
memory_persistence_stopped = True
if self._memory_service is not None:
    memory_persistence_stopped = self._memory_service.shutdown()
```

...with the `RuntimeShutdownReport(...)` construction call widened to
pass both new fields. Placement within the existing four-block
sequence is Owner Decision D2 (Section 14).

### 6.9 `Bootstrap.initialize()` widening

The existing `RuntimeService(...)` call (lines 356-364) gains one new
keyword argument:

```python
self._runtime_service = RuntimeService(
    started_at=self._started_at,
    rest_api_server=self._rest_api_server,
    background_worker_service=self._background_worker_service,
    shell=self._shell,
    scheduler_service=self._scheduler_service,
    workflow_scheduler_service=self._workflow_scheduler_service,
    memory_service=self._memory_service,
)
```

`self._memory_service` is already assigned by this point (Section
2.7) — no reordering of any existing line in `_build_command_router()`
or `initialize()` is required, exactly the same "already-available
dependency, first use by `RuntimeService`" shape `EP063_DESIGN.md`
Section 6.6 describes for `self._workflow_scheduler_service`.

### 6.10 `RuntimeModule._status()` widening

One new, unconditional display block, appended after the existing
Workflow Scheduler block, mirroring its exact structure:

```python
lines.append(
    f"Memory Auto-Save : "
    f"{'ACTIVE' if status.memory_persistence_active else 'INACTIVE'}"
)
if status.memory_persistence_active:
    lines.append(
        f"Memory entries pending auto-save : "
        f"{status.memory_persistence_entries_saved}"
    )
```

`_actions` remains `{"status", "help"}` — unchanged (Section 5,
Non-Goals; Owner Decision D1, Section 14).

---

## 7. Ownership and Lifecycle

- `MemoryPersistence` remains the sole owner of `_save_thread`,
  `_stop_event`, `_save_lock` — `shutdown()` is a new method on the
  same class that already owns these fields, not a new owner.
- `MemoryService` remains the sole owner of the one
  `MemoryPersistence` instance — `RuntimeService` never constructs,
  replaces, or holds a direct reference to `MemoryPersistence`.
- `Bootstrap` remains the sole owner of the one `MemoryService`
  instance (`self._memory_service`) — `RuntimeService` is handed a
  reference, never becomes a second owner, exactly matching the
  ownership contract already documented for every other
  `RuntimeService` dependency (`RuntimeService`'s own class docstring:
  "never constructs any of them, never becomes their sole
  reference-holder").
- `RuntimeService` never starts, restarts, or reconfigures
  `MemoryService`/`MemoryPersistence` — only `.status()` (read) and
  `.shutdown()` (the one new, narrow control operation) are ever
  called, matching the existing four-way ownership-boundary
  distinction `EP060_DESIGN.md` Section 9.2 already establishes.

---

## 8. Shutdown Semantics

- **Idempotent.** A second `shutdown()` call (at any layer —
  `MemoryPersistence`, `MemoryService`, or via
  `RuntimeService.shutdown()`) sees `_save_thread is None` and returns
  `True` immediately, identical in shape to
  `SchedulerService.shutdown()`'s own idempotency guarantee.
- **`wait`/`timeout` supported**, mirroring
  `SchedulerService.shutdown()`'s signature exactly: `wait=True`
  (default) blocks on `thread.join(timeout=resolved_timeout)`;
  `wait=False` signals the stop and returns
  `not thread.is_alive()` without joining.
- **Return-value semantics.** `True` ⇔ "confirmed not running after
  this call, including never having run"; `False` ⇔ "`wait=True` and
  the thread did not exit within `timeout`." Exhaustively covers every
  branch, matching `SchedulerService.shutdown()`'s own documented
  contract.
- **Does not affect enabled/disabled state or stored data.** No
  registered entry, provider, or the `MemoryStore` itself is touched —
  only the background thread. Manual `save()` remains callable after
  `shutdown()`, exactly as manual `run(job_id)` remains callable after
  `SchedulerService.shutdown()`.
- **No restart path.** Exactly like Scheduler/Workflow Scheduler,
  `_start_auto_save_loop()` remains private, called only from
  `start()`, which is itself called only once, from
  `MemoryService.__init__`. No public method can re-arm the loop after
  `shutdown()` — an explicit Non-Goal, matching both precedents.
- **Thread/event state after successful shutdown.** `self._save_thread
  is None`; `self._stop_event` remains set (never cleared by
  `shutdown()` — only `_start_auto_save_loop()` clears it, and that
  method is never called again without a restart path that does not
  exist) — behaviorally inert for the same reason `SchedulerService`'s
  and `WorkflowSchedulerService`'s own `shutdown()` leave this
  identical, already-audited-as-fine state behind
  (`EP063_ARCHITECTURE_AUDIT.md` Section 2, "Thread/event state after
  successful shutdown" row).

---

## 9. API / Contract Changes

| Class | Change | Backward compatible? |
|---|---|---|
| `MemoryPersistence` | New public method `shutdown(wait=True, timeout=None) -> bool`. | Yes — purely additive; no existing method's signature or body changes. |
| `MemoryService` | New public method `shutdown(wait=True, timeout=None) -> bool`. | Yes — purely additive. |
| `MemoryStatus` | New field `auto_save_running: bool`, appended last. | The one existing construction call site is entirely keyword-based (Section 2.6) and is itself updated in the same change, so no external caller is affected. Any hypothetical external positional construction would break — none exists in this repository. |
| `RuntimeStatus` | Two new fields, appended last, both defaulted. | Yes — matches EP-060/061/063's own precedent exactly. |
| `RuntimeShutdownReport` | Two new fields, appended last, both defaulted. | Yes — same precedent. |
| `RuntimeService.__init__` | One new trailing keyword-defaulted parameter. | Yes — every existing call site (production and EP-059 through EP-063 tests) continues to construct a valid instance unmodified. |
| `RuntimeService.status()`/`shutdown()` | Widened bodies; public signatures (`() -> RuntimeStatus`/`() -> RuntimeShutdownReport`) unchanged. | Yes. |
| `MemoryModule`, `RuntimeModule` CLI action sets | `MemoryModule._actions` unchanged; `RuntimeModule._actions` unchanged (`{"status", "help"}`). Only `RuntimeModule._status()`'s message body gains new lines. | Yes — no action set changes, so no REST/Telegram-reachable surface changes either (Owner Decision D1). |

If no public API change is required for a given file, this is stated
explicitly above rather than left ambiguous: `MemoryModule.execute()`,
`MemoryModule._actions`, `RuntimeModule.execute()`, and
`RuntimeModule._actions` all have **zero** contract change.

---

## 10. Configuration

**No new configuration key is introduced.** `memory.enabled`,
`memory.persistent`, `memory.auto_save`, `memory.auto_save_interval`,
`memory.storage_file`, `memory.max_entries`, `memory.default_ttl` are
all read exactly as before, by exactly the same existing methods
(`is_persistent()`, `is_auto_save()`, `auto_save_interval()`,
`storage_path()`). The new `shutdown()` method's join timeout is a
fixed, in-code constant (`_DEFAULT_SHUTDOWN_TIMEOUT = 5.0`, Section
6.1), not a configuration-driven value — Owner Decision D4 (Section
14) explains why this mirrors `SchedulerService`'s EP-061 precedent
rather than `WorkflowSchedulerService`'s EP-063 precedent.

---

## 11. File-Level Impact

Identified here for STEP 2's benefit; **not authorized by this
document** (Section 15).

### Expected to change (production)

- `src/core/memory/memory_persistence.py` — add `shutdown()`,
  `_DEFAULT_SHUTDOWN_TIMEOUT`.
- `src/services/memory_service.py` — add `shutdown()` passthrough;
  widen `MemoryStatus` (one new field); widen `status()`'s body (one
  new line).
- `src/services/runtime_service.py` — widen `RuntimeStatus` (two new
  fields), `RuntimeShutdownReport` (two new fields),
  `RuntimeService.__init__` (one new parameter), `status()` (new
  block), `shutdown()` (new block + widened `RuntimeShutdownReport(...)`
  construction call), and the module docstring (one new paragraph,
  matching the existing per-EP docstring-narrative convention).
- `src/bootstrap.py` — widen the existing `RuntimeService(...)` call
  (one new keyword argument) inside `initialize()`. No other line in
  this file changes (Section 5, Non-Goals).
- `src/modules/runtime_module.py` — widen `_status()`'s body (new
  lines); `_actions` unchanged.

### Expected to be created

- `tests/EP064/__init__.py`
- `tests/EP064/test_memory_persistence_shutdown.py`

### Expected to change (test registration only)

- `src/modules/test_module.py` — one new import line
  (`import tests.EP064.test_memory_persistence_shutdown`), matching
  the existing registration convention exactly (Section 2.9's sibling
  evidence: `tests/EP063/test_workflow_scheduler_shutdown.py`'s own
  registration is a single import line at the end of the existing
  list).

### Explicitly NOT expected to change

See Section 13, Protected Files.

---

## 12. Testing Strategy

New suite: `tests/EP064/test_memory_persistence_shutdown.py`,
structurally modeled on `tests/EP061/test_scheduler_shutdown.py`
(Section 2.9's naming evidence) and `tests/EP063/
test_workflow_scheduler_shutdown.py`, substituting `MemoryPersistence`/
`MemoryService` for `SchedulerService`. Because no existing
`MemoryPersistence`/`MemoryService` lifecycle test file exists
(Section 2.8), this suite must establish baseline coverage for the
auto-save lifecycle itself (start/is_running/idempotent-start), not
only the new `shutdown()` behavior — otherwise `shutdown()` would be
the only tested behavior of a previously wholly-untested subsystem.

Isolation tests (`MemoryPersistence` constructed directly, real
`threading.Thread`, no mocks):

- `_test_shutdown_never_started_returns_true_immediately` — `memory.auto_save: false` (or `memory.persistent: false`), `shutdown()` returns `True` without ever having a thread.
- `_test_auto_save_loop_starts_when_persistent_and_auto_save_enabled` — baseline: confirms `is_running()` is `True` after `start()` with both flags `true` (establishes the missing baseline coverage, Section 2.8).
- `_test_shutdown_stops_a_running_auto_save_loop` — start, then `shutdown()`, then `is_running()` is `False`.
- `_test_shutdown_is_idempotent` — two consecutive `shutdown()` calls, both `True`, no exception.
- `_test_shutdown_no_wait_returns_promptly` — `wait=False` returns quickly without joining.
- `_test_manual_save_still_works_after_shutdown` — `save()` remains callable and returns success after `shutdown()`.
- `_test_default_shutdown_timeout_is_five_seconds` — confirms `_DEFAULT_SHUTDOWN_TIMEOUT == 5.0`.
- `_test_explicit_timeout_argument_overrides_default` — an explicit `timeout=` argument is honored over the constant.
- `_test_concurrent_shutdown_calls_are_race_safe` — mirrors `tests/EP061/test_scheduler_shutdown.py`'s own
  `_test_concurrent_shutdown_calls_are_race_safe`, retargeted at
  `MemoryPersistence` — proactively included here (unlike EP-063's
  Finding F1 gap) since this design document is aware of that
  precedent gap and deliberately does not repeat it for a new
  subsystem when the pattern is already established and cheap to
  reuse.
- `_test_shutdown_does_not_hold_lock_during_join` — mirrors EP-061's own test of the identical lock-scope shape.

`MemoryService`-level tests:

- `_test_memory_service_shutdown_passthrough` — `MemoryService.shutdown()` delegates correctly and `MemoryStatus.auto_save_running` reflects the change.
- `_test_memory_status_auto_save_running_reflects_actual_thread_state` — confirms `auto_save_running` is `True` while running and `False` after `shutdown()`, distinct from `auto_save` (config flag), which stays `True` throughout (config unchanged).
- `_test_memory_service_public_surface_is_previous_plus_shutdown` — mirrors `_test_scheduler_service_public_surface_is_previous_plus_shutdown` (EP-061); asserts the exact 14-method set (13 existing + `shutdown`).

`RuntimeService`-level tests (real objects, no mocks, mirroring
`tests/EP063`'s own conventions):

- `_test_runtime_status_reports_inactive_memory_persistence_by_default` — `memory.auto_save: false` fixture.
- `_test_runtime_status_reports_active_memory_persistence` — default config, confirms `memory_persistence_active is True`.
- `_test_runtime_shutdown_all_none_unchanged_defaults` (extended) — confirms `memory_service=None` still produces valid, all-default `RuntimeStatus`/`RuntimeShutdownReport` fields.
- `_test_runtime_shutdown_stops_real_memory_persistence` — real `MemoryService`, confirms `auto_save_running` becomes `False` after `RuntimeService.shutdown()`.
- `_test_runtime_shutdown_orders_rest_scheduler_workflow_scheduler_memory_background_workers` — extends EP-063's own order-recording-proxy test (Section 2.9) with a `MemoryService`-shaped proxy, asserting the five-step order specified by Owner Decision D2 (Section 14).
- `_test_runtime_shutdown_idempotent_with_memory_persistence` — mirrors the Scheduler/Workflow-Scheduler equivalents.

`Bootstrap`-level end-to-end tests:

- `_test_bootstrap_shutdown_stops_memory_auto_save_loop` — real `Bootstrap`, full config, confirms the auto-save thread is gone after `bootstrap.shutdown()`.
- `_test_bootstrap_shutdown_preserves_memory_service_identity` — `bootstrap.memory_service is memory_service` (identity, not equality) after `shutdown()` — mirrors the Scheduler/Workflow-Scheduler precedent (Owner Decision D8, Section 14: not nulled).
- `_test_bootstrap_shutdown_twice_does_not_raise_or_hang`.
- `_test_bootstrap_shutdown_without_initialize_does_not_raise`.

CLI/public-surface guard tests:

- `_test_memory_module_cli_actions_unchanged` — asserts the exact 12-action set, explicitly asserting `"start"`/`"stop"`/`"shutdown"` are absent (Owner Decision D1).
- `_test_runtime_module_cli_actions_unchanged` — asserts `{"status", "help"}`, extended to also cover this EP.

**Full regression** (every existing suite, run unmodified, per this
repository's established convention): `tests/EP023/test_memory_manager.py`,
`tests/EP025/test_long_term_memory.py`, `tests/EP026/test_semantic_search.py`,
`tests/EP054/test_reflection.py` (Section 2.8's evidence — these
already construct/stub `MemoryService` and must continue passing
unmodified), plus every suite `EP063_ARCHITECTURE_AUDIT.md` Section 12
already lists (`EP034`, `EP036` ×3, `EP043`, `EP059`, `EP060`, `EP061`,
`EP062`, `EP063` — 735 assertions total, confirmed by that audit's own
fresh re-run), none of which construct or depend on
`MemoryPersistence`'s new method, so none should observe any
behavioral change.

**Explicitly not required:** no test count is invented here beyond
what STEP 2 will actually produce (matching this task's instruction
"Do not invent test counts unless already established by the
repository" — the test names above are a specification of required
coverage, not a promised final assertion count).

---

## 13. Compatibility / Regression Risk

- **Zero risk to `MemoryStore`/`MemoryManager`/provider system** — not
  touched.
- **Zero risk to any existing `MemoryService` caller** (`ConversationManager`,
  `SemanticEngine`, `LongTermMemoryService`, every CLI/REST/Telegram
  command through `MemoryModule`, every plugin using `PluginContext`) —
  no existing method's signature or behavior changes; `shutdown()` is
  new and unreachable except through `RuntimeService`/direct
  programmatic access (no CLI/REST/Telegram route exists, Owner
  Decision D1).
- **Zero risk to Scheduler/Workflow Scheduler/Background Worker/REST
  API shutdown behavior** — their own steps in
  `RuntimeService.shutdown()`'s sequence are unchanged; only a new
  step is inserted (position per Owner Decision D2). Verified no
  shared state: `MemoryPersistence`'s `_save_lock`/`_stop_event`/
  `_save_thread` are entirely private to that one instance, and (per
  Section 2, no execution-path reference from `workflow_engine`,
  `plan_execution`, `background_workers`, or `tool` packages to
  `memory_service` was found by direct grep) there is no verified
  shutdown-correctness dependency between Memory auto-save and any
  other coordinated subsystem, in either direction.
- **Existing test suites that construct `MemoryService` with
  `memory.auto_save: true`** (Section 2.8: `tests/EP023/`, `tests/EP025/`,
  `tests/EP026/`, `tests/EP054/`) already tolerate a live daemon
  auto-save thread today, with no cleanup call — this EP does not
  change that tolerance; it only adds an optional way to stop it that
  those tests do not call, so their behavior is unaffected.
- **`RuntimeStatus`/`RuntimeShutdownReport` widening risk**: identical
  in shape and risk profile to EP-060/061/063's own three prior,
  successful widenings — both dataclasses have exactly one
  construction call site each, entirely keyword-based, matching the
  "safe to widen" precondition every prior audit already relied on.
- **File-size risk**: `memory_service.py` (588 lines) and
  `memory_persistence.py` (269 lines) both grow slightly. Neither
  crosses a *hard* limit (`AI_GENERATION_STANDARD.md` states 500 lines
  is a soft limit, exceptions allowed for practicality); `memory_service.py`
  is already over that soft limit today, independent of this EP —
  Owner Decision D7 (Section 14) keeps the new method to the smallest
  possible line count rather than triggering a refactor.

---

## 14. Explicit Owner Decisions

### D1 — Should `MemoryPersistence.shutdown()`/`MemoryService.shutdown()` be exposed through `MemoryModule`'s CLI/REST/Telegram surface?

**Question:** Every other coordinated-shutdown subsystem
(Scheduler, Workflow Scheduler) keeps its new `shutdown()` internal
only. Should Memory differ, given it currently has zero manual control
of any kind (unlike Telegram, which already has `stop`)?

**Options:** (a) keep `shutdown()` internal-only, invoked exclusively
by `RuntimeService.shutdown()` — no new `MemoryModule` action (as
proposed — recommended, matches the unbroken EP-060/061/063
precedent); (b) add a new `"stop"`/`"shutdown"` action to
`MemoryModule`, giving operators a manual escape hatch for the first
time.

**Recommended option:** (a).

**Reason:** Every prior EP in this family (EP-060 D3, EP-061 D1,
EP-063 D1) has kept its new lifecycle-control method internal-only,
and independently verified (Section 2.9) that no exception to this
pattern exists anywhere in this codebase's `RuntimeService`-adjacent
history. Introducing a CLI-exposed mutating action is a materially
different, larger decision (REST-reachability, since
`ApiRouter.dispatch_command()` passes through unconditionally per
`EP063_ARCHITECTURE_AUDIT.md` Section 7) that this EP's narrow scope
should not make as a side effect.

**Alternative rejected:** (b) — would require its own security/REST-
reachability review this document does not include, exactly the same
reasoning `EP060_DESIGN.md` D3 already gives for Scheduler.

**Architectural consequence:** `MemoryModule._actions` remains
exactly its current 12-entry set; no REST/Telegram command can ever
reach `MemoryPersistence.shutdown()`, independently verifiable at the
CLI/REST/Telegram layers exactly as `EP063_ARCHITECTURE_AUDIT.md`
Section 7 already did for Workflow Scheduler.

### D2 — Where should Memory auto-save be stopped relative to REST API Server, Scheduler, Workflow Scheduler, and Background Worker Service?

**Question:** `RuntimeService.shutdown()`'s existing four-step sequence
is REST API Server → Scheduler → Workflow Scheduler → Background
Worker Service, ordered by "external trigger first, then internal
triggers grouped fast-to-slow, then the long drain last"
(`EP063_DESIGN.md` Owner Decision D2's own rationale, re-confirmed
Section 2.9). Memory auto-save is not a command-dispatch trigger of
any kind — it is a passive, periodic side-effect loop. Where does it
fit?

**Options:** (a) immediately after Workflow Scheduler, before
Background Worker Service — grouping it with the other fast-to-settle,
non-trigger-related internal loops, keeping the long Background Worker
drain last (as proposed — recommended); (b) after Background Worker
Service (last) — on the theory that background-worker-executed
workflows might still write to Memory during their drain window, so
keeping auto-save alive throughout that window maximizes intermediate-save
coverage; (c) first, before REST API Server.

**Recommended option:** (a).

**Reason:** Verified by direct, repository-wide search (Section 13)
that no execution path in `workflow_engine`, `plan_execution`,
`background_workers`, or `tool` references `memory_service` at
all — confirmed by grep, zero matches. **Option (b)'s premise is
therefore factually unsupported by this repository's actual code**:
there is no verified case of a background-worker-executed workflow
writing to Memory during the drain window, so there is no
data-coverage benefit to stopping Memory auto-save last. Given no
verified dependency in either direction, this EP defers to the
existing, established "group fast-to-settle steps before the one slow
step" convention, and Memory auto-save settles just as fast as
Scheduler/Workflow Scheduler's own `_stop_event.set()` mechanism (no
workflow-dependent blocking — `save()` is a bounded local file write,
unlike `WorkflowSchedulerEngine.tick()`). Option (c) is rejected because
Memory auto-save, unlike REST API Server, is not an external,
network-reachable command-dispatch trigger — grouping it with REST
would conflate two different rationales (external-trigger-first vs.
fast-internal-loops-together) that this repository's existing
ordering keeps cleanly separated.

**Alternative rejected:** (b) — factually unsupported (see above); (c)
— conflates unrelated ordering rationales.

**Architectural consequence:** `RuntimeService.shutdown()`'s sequence
becomes REST API Server → Scheduler → Workflow Scheduler → Memory
Persistence → Background Worker Service (five steps). STEP 2's
`RuntimeShutdownReport` field order and the order-recording-proxy test
(Section 12) must both reflect this exact position.

### D3 — Should `MemoryPersistence.shutdown()` be public?

**Question:** Could this instead remain a private helper, with only
`MemoryService.shutdown()` public?

**Options:** (a) `MemoryPersistence.shutdown()` public, mirroring
`SchedulerService.shutdown()`'s own visibility exactly (as proposed —
recommended); (b) make it a private `_shutdown()`/`_stop_auto_save()`,
accessible only through `MemoryService`.

**Recommended option:** (a).

**Reason:** Matches the established precedent exactly:
`SchedulerService.shutdown()` and `WorkflowSchedulerService.shutdown()`
are both public on the component that directly owns the thread/lock/
event, even though in practice only their owning Service-layer class
(here, indirectly, `RuntimeService`) calls them. Keeping it public
also allows `MemoryPersistence` to be tested in isolation (Section 12's
isolation tests), matching how `tests/EP061/test_scheduler_shutdown.py`
exercises `SchedulerService.shutdown()` directly, not only through
`RuntimeService`.

**Alternative rejected:** (b) — would block the isolation-test tier of
Section 12's testing strategy and depart from precedent for no
disclosed benefit.

**Architectural consequence:** `MemoryPersistence`'s public surface
grows from 10 to 11 methods (Section 2.1's count, plus `shutdown()`).

### D4 — Should the join timeout be a new `memory.shutdown_timeout` configuration key, or a fixed constant?

**Question:** `BackgroundWorkerService`/`WorkflowSchedulerService` both
read a configurable `*.shutdown_timeout` key (EP-036, EP-063 D3).
`SchedulerService` instead uses a fixed constant (EP-061 D4). Which
precedent applies here?

**Options:** (a) fixed constant, `_DEFAULT_SHUTDOWN_TIMEOUT = 5.0`,
mirroring `SchedulerService`'s own EP-061 D4 reasoning exactly (as
proposed — recommended); (b) new configurable `memory.shutdown_timeout`
key, mirroring `WorkflowSchedulerService`'s EP-063 D3 reasoning.

**Recommended option:** (a).

**Reason:** EP-063 D3's own stated reason for choosing a configurable
key was that `WorkflowSchedulerEngine.tick()` "genuinely blocks on
workflow-dependent execution time" — an open-ended, potentially long
duration. `MemoryPersistence._auto_save_loop()`'s only blocking work
per iteration is `save()`, which performs one bounded local JSON
`open`/`json.dump`/`close` sequence (confirmed, Section 2.1/`save()`
body) — structurally identical in boundedness to
`Scheduler.tick()`'s own executors, which is exactly the case EP-061
D4 chose a fixed constant for. There is no workflow-dependent,
externally-triggered blocking risk here, so EP-063's rationale for a
configurable key does not transfer; EP-061's rationale for a fixed
constant does.

**Alternative rejected:** (b) — would add a new configuration key
this repository's own precedent (EP-061 D4) says is unnecessary for a
bounded-duration loop, and would grow `config/config.yaml` for no
disclosed benefit.

**Architectural consequence:** No `_resolve_shutdown_timeout()` helper
is needed (Section 6.1) — one class constant suffices, keeping
`memory_persistence.py`'s growth minimal (Section 13's file-size risk
note).

### D5 — What should `MemoryService` expose?

**Question:** Should `MemoryService` expose only a thin `shutdown()`
passthrough, or also a `status()`-adjacent method/field for the
running state?

**Options:** (a) a thin `shutdown()` passthrough (Section 6.2) plus
one new field on the *existing* `MemoryStatus` dataclass
(`auto_save_running`, Section 6.3) — as proposed, recommended; (b) a
brand-new, separate dataclass/method (e.g. `MemoryService.
auto_save_status() -> AutoSaveStatus`) parallel to `status()`.

**Recommended option:** (a).

**Reason:** `MemoryStatus` already exists, already carries the
closely-related `auto_save`/`auto_save_interval` configuration fields,
and already has exactly one, all-keyword construction call site
(Section 2.6) — the same "safe to widen" precondition every
`RuntimeStatus` widening has relied on. A second, parallel dataclass
would duplicate information (`auto_save`/`auto_save_interval` would
need to appear on both) for no disclosed benefit, and none of
EP-060/061/063's own widenings introduced a second dataclass for an
analogous case (`BackgroundWorkerStatus`/`SchedulerStatus`/
`WorkflowSchedulerStatus` are each already the one, single status
dataclass their respective services return).

**Alternative rejected:** (b) — duplicative, no precedent, no
disclosed benefit.

**Architectural consequence:** `MemoryStatus` grows from 11 to 12
fields; `MemoryService`'s public method count grows from 13 to 14
(`shutdown` added); no new dataclass is introduced.

### D6 — Should the existing daemon-thread behavior otherwise remain unchanged?

**Question:** Should `_auto_save_loop()`'s save cadence, error
handling, logging, or the thread's `daemon=True` flag change in any
way?

**Options:** (a) no change of any kind to `_auto_save_loop()`,
`_start_auto_save_loop()`, `load()`, `save()`, or any existing
attribute — `shutdown()` is purely additive (as proposed —
recommended); (b) also address some adjacent improvement while this
file is already open (e.g. bounding `save()`'s own duration, adding
retry logic).

**Recommended option:** (a).

**Reason:** Matches this repository's own, so-far-unbroken practice
(confirmed at every one of EP-060/061/063's own "Non-Goals" sections)
of not opportunistically expanding an EP's scope to cover adjacent,
separately-disclosable concerns. Any such improvement would need its
own STEP 1 discovery and Owner Decision, not a rider on this one.

**Alternative rejected:** (b) — scope creep, explicitly disallowed by
this task's own instructions ("STEP 2 must not become an opportunity
to redesign unrelated architecture").

**Architectural consequence:** Every existing line of
`memory_persistence.py` other than the new `shutdown()` method and
`_DEFAULT_SHUTDOWN_TIMEOUT` constant remains byte-identical to today's
implementation — independently verifiable by `diff`/`md5sum` at STEP 3,
exactly as every prior EP's audit has already done for its own
predecessor files.

### D7 — How much should `memory_service.py` grow?

**Question:** `memory_service.py` is already at 588 lines, above
`AI_GENERATION_STANDARD.md`'s 500-line soft limit. Should adding
`shutdown()` also trigger a refactor/split?

**Options:** (a) add the smallest possible passthrough method (Section
6.2's exact body: one docstring, one `return` statement) and do not
otherwise touch this file's structure (as proposed — recommended); (b)
use this EP as an opportunity to split `memory_service.py` into
smaller files, matching the `memory_persistence.py`/`memory_service.py`
split precedent this file's own docstring already describes.

**Recommended option:** (a).

**Reason:** `AI_GENERATION_STANDARD.md` states the 500-line figure is
a "soft limit," not a hard one, and explicitly allows exceptions;
this file already exceeds it today, independent of this EP, for
reasons predating EP-064. Splitting it is a legitimate, separately-
scoped architectural improvement, not something this EP's narrow
shutdown-coordination goal should absorb (Non-Goals, Section 5).

**Alternative rejected:** (b) — unrelated scope expansion, and risks
introducing regressions across every one of `memory_service.py`'s 13
existing public methods for no benefit to this EP's actual goal.

**Architectural consequence:** `memory_service.py` grows by
approximately 10-12 lines (one new method plus its docstring, plus one
new `MemoryStatus` field and one new line in `status()`'s body); it
remains a single file, structurally unchanged otherwise.

### D8 — Should `Bootstrap` retain the `MemoryService` reference after shutdown?

**Question:** `Bootstrap.shutdown()` nulls `self._rest_api_server`/
`self._background_worker_service` but does not null
`self._scheduler_service`/`self._workflow_scheduler_service`. Which
category does `self._memory_service` belong to?

**Options:** (a) do not null `self._memory_service` — it remains fully
usable after `shutdown()` (`set`/`get`/`delete`/`clear`/`list_entries`/
`export`/`import_`/`status`/`doctor`/manual `save()` all continue to
operate correctly on the in-memory `MemoryStore`, which `shutdown()`
never touches), matching the Scheduler/Workflow-Scheduler category (as
proposed — recommended); (b) null it, matching the REST-API-Server/
Background-Worker-Service category.

**Recommended option:** (a).

**Reason:** The REST API Server and Background Worker Service are
nulled because they become *meaningfully unusable* once stopped (a
stopped `RestApiServer` cannot serve requests; a shut-down
`BackgroundWorkerPool` raises `PoolShutDownError` on `submit()`).
`MemoryService` after `shutdown()` is in exactly the opposite
situation: every one of its 13 pre-existing methods continues to work
correctly, because `shutdown()` only stops the *periodic disk
auto-save*, never the in-memory `MemoryStore` those methods actually
read/write. This is architecturally identical to why
`self._scheduler_service`/`self._workflow_scheduler_service` are not
nulled (`status()`, `list_*()`, manual `run()`/`run_now()` all remain
correct for those too).

**Alternative rejected:** (b) — would incorrectly make
`bootstrap.memory_service` return `None` after `shutdown()`, breaking
`_save_memory_on_shutdown()` in `main.py` (which runs *after*
`bootstrap.shutdown()` and needs a non-`None` `bootstrap.memory_service`
to call its final explicit `save()` — confirmed, `main.py` lines 51-52,
this call ordering is unchanged by this EP). Nulling `self._memory_service`
would therefore be an actual regression, not merely an inconsistency.

**Architectural consequence:** `Bootstrap.shutdown()`'s own body gains
zero new lines (Section 5, Non-Goals) — no null-out line is added for
`self._memory_service`, and the existing two null-out lines
(`self._rest_api_server`/`self._background_worker_service`) are
untouched.

---

## 15. STEP 2 Implementation Boundary

STEP 2 will implement, and only implement:

1. `MemoryPersistence.shutdown()` + `_DEFAULT_SHUTDOWN_TIMEOUT`
   (Section 6.1).
2. `MemoryService.shutdown()` passthrough + `MemoryStatus.auto_save_running`
   field + one new line in `status()` (Sections 6.2-6.3).
3. `RuntimeStatus`/`RuntimeShutdownReport` widening (two fields each,
   Sections 6.4-6.5).
4. `RuntimeService.__init__`/`status()`/`shutdown()` widening
   (Sections 6.6-6.8), with the fifth shutdown step positioned per
   Owner Decision D2.
5. `Bootstrap.initialize()`'s existing `RuntimeService(...)` call
   widened by one keyword argument (Section 6.9). No other line in
   `bootstrap.py` changes.
6. `RuntimeModule._status()` widened by one display block (Section
   6.10). `_actions` unchanged.
7. `tests/EP064/__init__.py` and
   `tests/EP064/test_memory_persistence_shutdown.py` (Section 12).
8. One new import line in `src/modules/test_module.py`.

**Files expected to change:** exactly the six production files listed
in Section 11, plus the two new test files and one test-registration
import line.

**Protected files:** Section 13.

**Tests expected:** Section 12's full list (exact assertion count to
be determined by STEP 2's actual implementation — not invented here).

**What must remain unchanged:** every existing method's signature and
body across all six touched production files, except the specific new
lines/fields/parameters enumerated in Section 6; every existing test
file's content; `CHANGELOG.md`, `docs/RELEASE_NOTES.md`,
`docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`,
`docs/architecture/ARCHITECTURE_DEBT.md`, and every prior EP's design/
audit document.

STEP 2 must not redesign `MemoryStore`, `MemoryManager`, the provider
system, or any other subsystem's shutdown behavior while implementing
this scope.

---

## 16. Protected Files

The following must remain byte-identical to their pre-STEP-1 state
through STEP 2, independently verifiable by `diff`/`md5sum` at a
future STEP 3, exactly as every prior EP's audit has already done:

- `src/core/memory/memory_store.py`
- `src/core/memory/memory_manager.py`
- `src/core/memory/memory_provider.py`
- `src/core/memory/context.py`
- `src/modules/memory_module.py`
- `src/services/scheduler_service.py`
- `src/services/workflow_scheduler_service.py`
- `src/services/background_worker_service.py`
- `src/core/background_workers/background_worker_pool.py`
- `src/core/api/rest_api_server.py`
- `src/services/telegram_service.py`
- `src/modules/telegram_module.py`
- `src/modules/scheduler_module.py`
- `src/modules/workflow_scheduler_module.py`
- `src/modules/background_worker_module.py`
- `src/core/workflow_engine/workflow_engine.py`
- `src/core/plan_execution/` (entire package)
- `src/core/tool/` (entire package)
- `config/config.yaml`
- `docs/architecture/ARCHITECTURE_DEBT.md`
- `docs/architecture/designs/EP059_DESIGN.md` through
  `EP063_DESIGN.md` (all five)
- `docs/architecture/audits/` (every existing file)
- `tests/EP023/test_memory_manager.py`,
  `tests/EP025/test_long_term_memory.py`,
  `tests/EP026/test_semantic_search.py`,
  `tests/EP054/test_reflection.py`
- `tests/EP034/test_workflow_scheduler.py`,
  `tests/EP036/*`, `tests/EP043/test_rest_api.py`,
  `tests/EP059/test_runtime.py`, `tests/EP060/test_runtime_lifecycle.py`,
  `tests/EP061/test_scheduler_shutdown.py`,
  `tests/EP062/test_background_worker_status.py`,
  `tests/EP063/test_workflow_scheduler_shutdown.py`
- `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `docs/BACKLOG.md`,
  `docs/architecture/JARVIS_ROADMAP.md`

---

## 17. Acceptance Criteria

1. `MemoryPersistence.shutdown(wait=True, timeout=None) -> bool`
   exists, is idempotent, and matches Section 6.1's exact
   never-started/running/idempotent/`wait=False`/timeout-honoring
   behavior.
2. `MemoryPersistence`'s public method set is exactly its previous 10
   methods plus `shutdown` (11 total) — no other new public method.
3. `MemoryService.shutdown(wait=True, timeout=None) -> bool` exists
   and correctly passes through to `MemoryPersistence.shutdown()`;
   `MemoryService`'s public method set is exactly its previous 13
   methods plus `shutdown` (14 total).
4. `MemoryStatus.auto_save_running` exists, reflects
   `MemoryPersistence.is_running()` accurately in both the
   auto-save-enabled and auto-save-disabled states, and is distinct
   in value from `auto_save` whenever the loop has been stopped after
   having been started.
5. `RuntimeService.__init__` accepts an optional
   `memory_service: MemoryService | None = None` parameter; every
   pre-EP-064 call site continues to construct a valid instance
   unmodified.
6. `RuntimeStatus` gains exactly two new, defaulted, appended-last
   fields (`memory_persistence_active`, `memory_persistence_entries_saved`);
   `RuntimeShutdownReport` gains exactly two new, defaulted,
   appended-last fields (`memory_persistence_was_active`,
   `memory_persistence_stopped`).
7. `RuntimeService.status()` correctly reports Memory Persistence's
   active state and entry count in both a `None`-dependency case and a
   real, active-auto-save case.
8. `RuntimeService.shutdown()`'s five-step sequence is confirmed, via
   a real, non-mocked call-order-recording proxy test, to execute in
   exactly the order Owner Decision D2 specifies: REST API Server →
   Scheduler → Workflow Scheduler → Memory Persistence → Background
   Worker Service.
9. `bootstrap.memory_service` is non-`None` and identity-preserved
   (`is`, not `==`) across `bootstrap.shutdown()`, matching Owner
   Decision D8.
10. `runtime status`'s CLI output gains one new "Memory Auto-Save :
    ACTIVE/INACTIVE" line (plus a conditional entry-count line),
    formatted consistently with the existing Scheduler/Workflow
    Scheduler blocks; `RuntimeModule._actions` and `MemoryModule._actions`
    remain exactly their current sets (no `"start"`/`"stop"`/`"shutdown"`
    key added to either).
11. Every full-regression suite listed in Section 12 (including the
    four pre-existing suites that construct/stub `MemoryService`)
    passes unmodified.
12. The new `tests/EP064/test_memory_persistence_shutdown.py` suite
    passes, registered via exactly one new import line in
    `src/modules/test_module.py`.
13. No file outside Section 11's expected-to-change list is modified;
    every file in Section 16 (Protected Files) is confirmed
    byte-identical to its pre-STEP-1 state.
14. `EP063_ARCHITECTURE_AUDIT.md` Findings F1-F6 remain undisturbed and
    unaddressed by this EP — confirmed by `workflow_scheduler_service.py`
    and `tests/EP063/test_workflow_scheduler_shutdown.py` both being
    byte-identical to their pre-EP-064 state (Section 16).

Acceptance is not "all tests must pass" alone — it is the specific,
named, above criteria, each independently verifiable against the
actual repository state, matching this task's own instruction not to
use vague acceptance criteria.

---

## 18. Final Verification (performed before concluding STEP 1)

- Re-read this complete document end-to-end against the actual,
  current repository content (not assumed from memory of earlier
  reads in this session): every file path, method name, field name,
  line-number reference, config key, and default value cited above
  was independently confirmed via direct file reads during this STEP 1
  session (Sections 2, 6, 9, 13).
- Goals (Section 4) do not contradict Non-Goals (Section 5): every
  Goal names a specific, additive change; every Non-Goal names a
  specific thing intentionally left alone; no overlap.
- Owner Decisions (Section 14) match the Proposed Architecture
  (Section 6) exactly: D1↔Section 6 (no CLI exposure anywhere in
  Section 6's code), D2↔6.8 (five-step order), D3↔6.1 (public method),
  D4↔6.1 (fixed constant, no config), D5↔6.2-6.3 (thin passthrough +
  existing-dataclass widening), D6↔ Section 5 (no other line changes),
  D7↔6.2 (minimal method body), D8↔ Section 5 (`Bootstrap.shutdown()`
  unchanged).
- File-impact list (Section 11) matches the Proposed Architecture
  (Section 6) file-by-file, with no omission or addition.
- Testing Strategy (Section 12) matches the Proposed Architecture: every
  new method/field introduced in Section 6 has at least one
  corresponding named test in Section 12.
- Protected files (Section 16) are consistent with File-Level Impact
  (Section 11): no file appears in both lists.
- No requirement in this document depends on an undocumented
  assumption: every load-bearing claim (daemon-thread flag, config
  defaults, absence of a stop method, absence of test coverage,
  absence of a cross-subsystem memory-write dependency, `Bootstrap`
  attribute/property already existing) was independently verified
  against current source during this STEP 1 session, not merely
  asserted.
- No previous EP's Owner Decision is contradicted: EP-059 through
  EP-063's own Owner Decisions concern Shell/REST/Background-Workers/
  Scheduler/Workflow-Scheduler exclusively; none of them make any
  claim about `MemoryService`/`MemoryPersistence`, so none can be
  contradicted by this EP addressing that subsystem for the first
  time.
- EP-064 does not duplicate an existing capability: no prior EP added
  any lifecycle control to `MemoryPersistence`/`MemoryService`
  (confirmed, Section 2.1/2.4/2.5's exhaustive method/action listings).
- EP-063's Findings F1-F6 are explicitly and by name preserved as
  deferred, not silently absorbed (Section 5, final Non-Goal item; and
  Acceptance Criterion 14).
- Confirmed: this STEP 1 session created **only**
  `docs/architecture/designs/EP064_DESIGN.md`. No production code,
  test, configuration, dependency, `CHANGELOG.md`,
  `docs/RELEASE_NOTES.md`, `docs/BACKLOG.md`,
  `docs/architecture/JARVIS_ROADMAP.md`, or other documentation file
  was created or modified during this investigation.

**STEP 1 is complete. Do not proceed to STEP 2.**
