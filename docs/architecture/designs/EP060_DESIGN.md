# EP-060 — Jarvis Operating System — Design Specification (STEP 1)

Status: **STEP 1 — DESIGN PROPOSED / OWNER APPROVAL REQUIRED.**

**STEP 2 implementation has NOT begun.**

No source file, test file, configuration file, dependency file, or
Bootstrap file has been created or modified as part of producing this
document. The only artifact created by EP-060 STEP 1 is this document
itself, `docs/architecture/designs/EP060_DESIGN.md`.

---

## 0. How this document relates to EP-059

EP-059 (`EP059_DESIGN.md`, COMPLETE, STEP 1–4, audit passed, zero
blocking findings) already established that "Distributed Runtime" has
no textual anchor anywhere in this repository, and instead built a
read-only introspection surface — `RuntimeService`/`RuntimeModule` —
over Jarvis's already-existing, already-running concurrent execution
contexts (the interactive Shell, the REST API Server, the Background
Worker Pool). This document performs the same exhaustive-search
discipline for EP-060 and reaches the same first finding: **no file
anywhere in this repository names a specific mechanism EP-060 is meant
to build** (Section 2).

Unlike EP-059, however, this document does not have to build its
candidate set purely from the runtime's own shape. EP-059 itself left
three concrete, quoted hooks pointing at what a follow-on EP might do,
and this document's own direct reading of the current
`RuntimeService`/`Bootstrap` code — not assumption, not the roadmap
title — surfaced a fourth, more important one: **a real, confirmed
lifecycle-coordination gap in `Bootstrap.shutdown()`** that did not
exist, and could not have existed, before EP-059 built the one
component (`RuntimeService`) that already holds references to every
execution context needed to close it. Section 5 documents this gap in
full, with exact file/line evidence. This document's recommended
approach (Section 7, Candidate A) is a direct, minimal response to
that gap — not an invention driven by the phrase "Operating System."

---

## 1. Problem / Goal

**Stated goal (verbatim, the only place EP-060 is named beyond a bare
title):** `docs/engineering/ENGINEERING_GUIDE.md` line 175 / Phase 10
header — *"Complete the AI Operating System."* — a two-EP-wide
sentence shared with EP-059, not an EP-060-specific specification.
Beyond this and the bare roadmap title, no further specification
exists anywhere in the repository (Section 2).

**What this document treats as the actual, derivable problem,** given
Section 5's discovery: `Bootstrap` already coordinates *startup* of
every execution context Jarvis runs (`initialize()`'s single,
sequential build order), and EP-059 already gave the process a single,
authoritative place that knows which of those execution contexts exist
this run (`RuntimeService`, holding `rest_api_server`,
`background_worker_service`, `shell`). **No equivalent coordination
exists for *shutdown*.** `Bootstrap.shutdown()` — the one method
`src/main.py` already calls, unconditionally, at the end of every
normal run — stops exactly one of Jarvis's three auto-started
execution contexts (the REST API Server) and leaves the other two
(Background Worker Pool, and — a new finding this document makes, not
carried over from EP-059 — the Scheduler's tick loop) running,
unstopped, until the process itself terminates and their daemon
threads are torn down non-gracefully by the interpreter. This
document's recommended approach (Section 7, Candidate A) treats
*closing this gap* as EP-060's grounded v1 scope: widening
`RuntimeService`/`RuntimeModule` from EP-059's read-only introspection
surface into a small, additive lifecycle **control plane** — able to
*coordinate* an already-known, already-owned shutdown sequence over
the exact execution contexts it already observes — without inventing
a second runtime abstraction, a registry, a scheduler, or any
multi-process infrastructure.

---

## 2. Repository/specification inventory — what the repository actually says about EP-060 (verbatim)

| Location | Exact content |
|---|---|
| `docs/architecture/JARVIS_ROADMAP.md` (Phase 10 checklist) | `EP-060 Jarvis Operating System` — a bare title, no elaboration, no checkmark |
| `docs/architecture/JARVIS_ROADMAP.md` lines 217-219 ("Next Engineering Package" note, added by EP-059 STEP 4 doc-sync) | `**Next Engineering Package: EP-060 Jarvis Operating System — NOT STARTED.** No EP-060 design, research, or implementation work has begun.` — a status pointer, not a spec |
| `docs/BACKLOG.md` ("Next Engineering Package" section) | `### EP-060 — Jarvis Operating System` / `**NOT STARTED.**` — same pointer |
| `docs/engineering/ENGINEERING_GUIDE.md` line 173-179 | `## Phase 10 — Jarvis Operating System` / `Complete the AI Operating System.` / `Engineering Packages: EP-059 … EP-060` — a **phase-level** goal shared with EP-059 only, not EP-060-specific |
| `docs/architecture/JARVIS_ROADMAP.md` "Architecture Evolution" diagram | Lists `Jarvis Operating System` as the final stage after `User Interfaces` — an evolutionary label, not a mechanism |
| `docs/architecture/NON_GOALS.md` | States Jarvis "IS … an AI Operating System … capability-driven … modular", and that "Architectural consistency is always more important than short-term functionality" — a philosophy statement, applies to every EP equally, names no EP-060 mechanism |
| `docs/architecture/JARVIS_ARCHITECTURE_VISION.md` | A 647-line, project-wide vision document ("Jarvis is an AI Operating System… Jarvis should think in terms of workflows") describing the *product's* long-term behavior (AI routing, capability-first task decomposition) — confirmed, by reading it in full, to describe **already-covered ground** (AI Router → EP-014/015, Capability First → EP-056, Workflow Engine → EP-033) and to contain no sentence naming a distinct, unbuilt "Operating System layer" EP-060 should construct |
| `EP059_DESIGN.md` Section 5, Candidate D (rejected) | *"a plausible, separately-scoped future direction (very possibly relevant to EP-060's own 'Jarvis Operating System' capstone)"* — names generalizing `BackgroundWorkerPool` as one possible future direction, evaluated as Candidate B below (Section 7) |
| `EP059_DESIGN.md` Section 15, Owner Decision D5 | *"Owner Decision D5 exists specifically so the owner can explicitly widen this if desired, rather than this document silently assuming it"* — explicitly flags a future control action atop `RuntimeService` as a live, deferred option, not something EP-059 ruled out |
| `EP059_DESIGN.md` Section 15, Owner Decision D4 | Excluded Scheduler/Telegram from v1 status on the stated premise that *"neither is auto-started as a side effect of `Bootstrap.initialize()`"* — Section 5.3 below shows this premise is **factually incorrect for the Scheduler** under this repository's own default configuration |
| Every EP-001–058 `_DESIGN.md`/`_ARCHITECTURE_AUDIT.md` | Zero mention of EP-060 by name or scope anywhere |
| Everywhere else (`PROJECT_MANIFEST.md`, `AI_GENERATION_STANDARD.md`, every package docstring in `src/`) | **Zero** mentions of "EP-060," "EP060," "lifecycle coordinator," "system controller," or any close synonym referring to an unbuilt EP-060 mechanism (confirmed by repository-wide `grep`) |

**Conclusion:** exactly as EP-059 found for itself, no existing file
names a specific mechanism EP-060 is meant to build. Unlike EP-059,
though, EP-059's own design document left two explicit, quoted,
deferred hooks (D4's factual premise and D5's "widen this if desired"
framing) directly relevant to what EP-060 should do — and this
document's own direct code reading (Section 5) found a third, more
concrete one that neither hook by itself predicted: a real behavioral
gap in `Bootstrap.shutdown()`.

---

## 3. Relationship to EP-059 and previous EPs

EP-060 does not introduce a second runtime/status abstraction.
Everything in this document is phrased as a *widening* of the exact
two files EP-059 created (`src/services/runtime_service.py`,
`src/modules/runtime_module.py`) plus one small, disclosed,
non-purely-additive change to `src/bootstrap.py` (Section 9.5). No new
package, no new `Engine`/`Manager`/`Provider` hierarchy, and no
second `CommandRouter` namespace are introduced. `RuntimeService`
keeps Owner Decision D3's outcome (EP-059): it remains a small, inline
class in `runtime_service.py`, not a new `src/core/runtime/` package.

Every Engineering Principle in `docs/architecture/JARVIS_ROADMAP.md`
("extend the existing architecture," "avoid duplicated functionality,"
"reuse existing infrastructure") is read by this document as directly
favoring widening `RuntimeService` over building anything new — it is,
by construction, the one component already holding exactly the
references this EP needs.

---

## 4. Investigation summary (per this task's own numbered questions)

This section directly answers the ten investigation points this
task's own instructions enumerate, each expanded with file/line
evidence in Section 5.

1. **How `RuntimeService`/`RuntimeModule` currently work** — Section
   5.1.
2. **Which execution contexts they already know about** — Section
   5.1 (REST API Server, Background Worker Service, Shell — exactly
   three, per EP-059 Owner Decision D4).
3. **Current lifecycle/start/stop behavior of REST API, Background
   Worker Service/Pool, Scheduler, Shell** — Section 5.2.
4. **Current `Bootstrap.initialize()`/`Bootstrap.shutdown()`
   behavior** — Section 5.2, 5.4.
5. **The lifecycle inconsistency** (REST stopped; Background Workers
   not stopped; Scheduler has no public shutdown path at all; Scheduler
   auto-starts by actual default configuration) — Section 5.4/5.3, the
   central finding this document is built around.
6. **The unused `orchestrator.started`/`orchestrator.stopped` EventBus
   hooks** — Section 5.6; evaluated and found not relevant to EP-060's
   recommended design (Section 7, Candidate D rejection).
7. **`CommandRouter` lifecycle limitations (no `unregister`)** —
   Section 5.7.
8. **Why `CapabilityRegistryModule` must not be duplicated** — Section
   5.8; directly informs Candidate C's rejection (Section 7).
9. **Reusing EP-059's Runtime infrastructure instead of a second
   abstraction** — Section 3, Section 8.
10. **Exact lifecycle operations in/out of scope** — Section 12
    ("In Scope"/"Out of Scope").

---

## 5. Current architecture / discovery findings

### 5.1 `RuntimeService`/`RuntimeModule` today (EP-059, unmodified so far)

Confirmed by direct reading of `src/services/runtime_service.py` and
`src/modules/runtime_module.py`:

- `RuntimeService.__init__(self, started_at, rest_api_server,
  background_worker_service, shell)` — four required, positional-or-
  keyword parameters, each a `None`-able reference to an
  already-constructed object. **Every existing test in
  `tests/EP059/test_runtime.py` calls this constructor with all four
  arguments passed by keyword** (confirmed: every one of the 15
  `RuntimeService(...)` call sites in that file uses
  `started_at=…, rest_api_server=…, background_worker_service=…,
  shell=…`, never positionally) — a fact this document relies on
  directly in Section 9.1 to guarantee backward compatibility for a
  widened constructor.
- `RuntimeService` exposes exactly **one** public method: `status()
  -> RuntimeStatus`. It performs no computation beyond reading
  already-public facts from already-constructed objects
  (`RestApiServer.is_running`/`.host`/`.port`,
  `BackgroundWorkerService.status()`), and never starts, stops, or
  reconfigures anything (EP-059 Owner Decision D5).
- `RuntimeStatus` is a frozen dataclass with nine fields (`pid`,
  `uptime_seconds`, `shell_active`, `api_active`, `api_host`,
  `api_port`, `background_workers_active`, `background_worker_count`,
  `background_worker_task_count`). **It is never constructed directly
  by any test** (confirmed: `grep -c "RuntimeStatus("
  tests/EP059/test_runtime.py` finds zero direct-construction call
  sites — every test reads attributes off the object `status()`
  returns) — a second fact Section 9.1 relies on: new fields can be
  appended to this dataclass with zero risk of breaking an existing
  positional-construction call site, because none exists.
- `RuntimeModule` exposes exactly two CLI actions, `status`/`help`,
  under the `"runtime"` `CommandRouter` namespace, and — because
  `ApiRouter` already forwards any registered `CommandRouter` action
  unchanged — `runtime status` is already reachable, unauthenticated,
  over the REST API today (EP-059 Section 14, unchanged by this
  document).

**Conclusion:** `RuntimeService`'s public surface today is exactly
`{status}`; `RuntimeModule`'s is exactly `{status, help}`. Both are
the smallest possible read-only surface EP-059 could have built, by
design (Owner Decision D5). This document proposes widening the
former to `{status, shutdown}` and the latter to remain `{status,
help}` unchanged (Section 9, Owner Decision D3 below).

### 5.2 Lifecycle/start/stop behavior of each execution context, read directly from source

| Component | Constructed when | Started | Stopped by | Public stop/shutdown method exists? |
|---|---|---|---|---|
| **REST API Server** (`RestApiServer`, EP-043) | `api.enabled: true` (default `false`) | `server.start()` called unconditionally inside `Bootstrap._build_rest_api_server()` the moment it is constructed | `Bootstrap.shutdown()` today, via `self._rest_api_server.stop()` | **Yes** — `RestApiServer.stop()` (`src/core/api/rest_api_server.py` line 418): idempotent (`if self._httpd is not None: …`), safe to call multiple times, matching its own docstring *"Safe to call multiple times."* `is_running` correctly reports `False` after `stop()` (`_httpd`/`_thread` are set to `None`). |
| **Background Worker Service/Pool** (`BackgroundWorkerService`, EP-036) | `background_workers.enabled: true` (default `true`) | `BackgroundWorkerPool.__init__` starts its `worker_count` daemon threads (`daemon=True`, confirmed `background_worker_pool.py` line 214) **immediately at construction**, inside `BackgroundWorkerService.__init__` — no decoupled "construct but don't start" step (confirmed by `background_worker_service.py`'s own module docstring, quoted in Section 5.4) | **Nothing today** — `Bootstrap.shutdown()` never calls it (Section 5.4) | **Yes, but never called by the running application** — `BackgroundWorkerService.shutdown(wait=True, timeout=None)` (`src/services/background_worker_service.py` line 230) delegates to `BackgroundWorkerPool.shutdown()`, itself idempotent via an internal `_is_shutdown` flag (`background_worker_pool.py` line 334-336: sets the flag and a `threading.Event` unconditionally, safe to call twice). **Known limitation (Section 5.5): `status().running` does not reflect having been shut down.** |
| **Scheduler** (`SchedulerService`/`Scheduler`, EP-011) | `scheduler.enabled: true` (default `true`, `config/config.yaml` line 87) | **Auto-started at `SchedulerService.__init__` time** whenever `scheduler.enabled` **and** `scheduler.auto_start` are both true (`scheduler_service.py` lines 100-103) — `scheduler.auto_start` also defaults to `true` (`config/config.yaml` line 88) | **Nothing, ever** — no code path anywhere in this repository calls it | **No.** `SchedulerService` has a private `_stop_event: threading.Event` (line 98) that is never `.set()` by any public method; there is no public `stop()`/`shutdown()` counterpart to `_start_tick_loop()` at all (confirmed: `grep -n "def " src/services/scheduler_service.py` lists `register/unregister/start(job_id)/stop(job_id)/run(job_id)/list_jobs/get_job/status/doctor` — every `start`/`stop` pair operates on one *job*, not on the service's own tick loop). |
| **Shell** (`InteractiveShell`) | Always, unconditionally, in `Bootstrap.initialize()` | Owns the foreground blocking loop `main.py` runs via `shell.run()` | Returns control to `main.py` when the user exits/Ctrl+C/EOF — not something `Bootstrap.shutdown()` acts on | N/A — `InteractiveShell` has no background thread or held OS resource of its own to release (EP-059's own framing, unchanged; confirmed no `Thread`/socket/file handle owned by `InteractiveShell` beyond the `CommandRouter` reference it is given). |

### 5.3 The Scheduler auto-start finding — a direct correction to EP-059 Owner Decision D4's stated premise

EP-059 Owner Decision D4 (Section 2 above) excluded Scheduler from
`RuntimeStatus` v1 on the explicit premise that it is *"not
auto-started as a side effect of `Bootstrap.initialize()`."* Direct
reading of `SchedulerService.__init__` (quoted in full, Section 5.2)
shows this premise does not hold under this repository's own default
configuration: `scheduler.enabled` defaults to `true`
(`config/config.yaml` line 87) and `scheduler.auto_start` defaults to
`true` (line 88), and `SchedulerService.__init__` starts its tick
thread unconditionally whenever both are true — with **no** explicit,
separate `.start()` call required from `Bootstrap` at all, unlike
`RestApiServer`. `SchedulerService`'s own module docstring says so
directly: *"the background tick loop … started automatically at
construction when 'scheduler.enabled' and 'scheduler.auto_start' are
true (see config/config.yaml)."* EP-059's Section 3.2 read
`Bootstrap.initialize()`'s own call sequence for an explicit
`.start()`-shaped call and correctly found none — but did not follow
`SchedulerService.__init__` itself, where the real auto-start
decision is made. **Under this repository's own shipped
configuration, Jarvis today auto-starts three background execution
contexts as a side effect of `Bootstrap.initialize()`, not two: the
REST API Server (gated `false` by default), the Background Worker
Pool (gated `true` by default), and the Scheduler tick loop (gated
`true` by default).** This is disclosed here as a correction to a
prior EP's own documented reasoning, not as a defect in EP-059's
implementation — EP-059's actual code is unaffected; only the
narrative justification for excluding Scheduler from v1's status
snapshot no longer holds.

### 5.4 The lifecycle inconsistency — `Bootstrap.shutdown()`, read directly

```python
def shutdown(self) -> None:
    """Stop any background component started by this Bootstrap.

    Currently only the EP-043 REST API server needs an explicit
    stop -- every other subsystem built by `initialize()` is a
    stateless, per-call client with no background thread or open
    socket. Safe to call multiple times, and safe to call even if
    the REST API server was never started/enabled.
    """
    if self._rest_api_server is not None:
        self._rest_api_server.stop()
        self._rest_api_server = None
```

(`src/bootstrap.py`, lines 2149-2160, quoted verbatim.) Its own
docstring's premise — *"every other subsystem … is a stateless,
per-call client with no background thread or open socket"* — is, per
Section 5.2, **not true of the Background Worker Pool** (`worker_count`
daemon threads, started at construction, confirmed) nor of the
**Scheduler** (one daemon tick thread, started at construction under
default configuration, per Section 5.3's correction). `src/main.py`
calls `bootstrap.shutdown()` unconditionally at the end of every
normal run (line 51, confirmed: `shell.run(); bootstrap.shutdown();
_save_memory_on_shutdown(bootstrap)`), then the process exits. Because
every one of these threads is `daemon=True` (confirmed for both
`BackgroundWorkerPool` and `SchedulerService`), the process does not
hang — but neither pool nor scheduler is ever given the chance to
finish in-flight work or terminate cleanly; the interpreter simply
tears the threads down when the process exits. This is the concrete,
confirmed gap this document's recommended candidate (Section 7,
Candidate A) closes for the two subsystems that already expose a
public shutdown primitive (REST API, Background Workers) and
explicitly, disclosedly leaves open for the one that does not
(Scheduler — Section 5.2, Section 12 "Out of Scope").

### 5.5 A related, pre-existing limitation this document does not fix: `BackgroundWorkerService.status().running`

```python
def status(self) -> BackgroundWorkerStatus:
    if self._pool is None:
        return BackgroundWorkerStatus(enabled=False, running=False, worker_count=0, task_count=0)
    return BackgroundWorkerStatus(enabled=True, running=True, worker_count=self._pool.worker_count, task_count=len(self._pool.list_tasks()))
```

(`src/services/background_worker_service.py`, lines 176-187, quoted
verbatim.) `running` is hard-set to `True` whenever `self._pool is not
None` — **it does not check whether `shutdown()` has already been
called** (`self._pool` is never set back to `None` by `shutdown()`
either; confirmed by reading `BackgroundWorkerService.shutdown()` in
full, Section 5.2). Consequence: **after EP-060's own recommended
`RuntimeService.shutdown()` runs, a subsequent `RuntimeService.status()`
call will still report `background_workers_active=True`**, even though
shutdown has genuinely been signaled (and, if `wait=True` completed
successfully, every worker thread has genuinely terminated). This is a
pre-existing characteristic of `BackgroundWorkerService.status()`, not
something EP-060 introduces — and fixing it would require modifying
`background_worker_service.py`, an EP-036 core file, which this
document does not propose (Section 12, Owner Decision D5). Section 9.4
specifies this precisely so STEP 2's tests assert this exact,
surprising-but-correct behavior rather than silently "fixing" it.

### 5.6 The unused `EventBus` lifecycle hooks — investigated, found not relevant to EP-060's recommended design

`Orchestrator.start()`/`stop()` (`src/core/orchestrator.py`) publish
`"orchestrator.started"`/`"orchestrator.stopped"` (lines 81, 91).
Repository-wide `grep` for `event_bus.subscribe` (confirmed, full
list in Section 5 of the discovery notes underlying this document)
shows **zero subscribers to either event anywhere in this repository**
— unlike `"workflow.completed"`/`"background_worker.task_completed"`,
which each have exactly one, real, wired subscriber
(`AutomationEngine.notify_run`, `src/bootstrap.py` lines 1397, 1433).
More decisively: **`Orchestrator.stop()` itself is never called by any
part of the running application** — confirmed by `grep -rn
"orchestrator.stop()\|_orchestrator.stop()"` across `src/`, which
returns no match outside `orchestrator.py`'s own method definition.
`"orchestrator.stopped"` is therefore not merely unsubscribed; it is
**never published at all** during a real run of Jarvis today. Building
EP-060's shutdown coordination around this hook would mean first
reviving and wiring up an entirely dead code path (deciding when
`Orchestrator.stop()` itself should be called, and by whom) before any
new lifecycle logic could even begin — a materially larger, more
speculative undertaking than directly extending `Bootstrap.shutdown()`
(which is already, today, the one place that is unconditionally called
exactly once per run). Candidate D (Section 7) evaluates and rejects an
event-driven design on this basis. EP-060's recommended approach
introduces no new `EventBus` publish or subscribe call.

### 5.7 `CommandRouter` lifecycle limitations — no `unregister`

`CommandRouter` (`src/core/command_router.py`) exposes `register()`
and `register_modules()` only — **no `unregister()` method exists**
(confirmed: the class's complete method list is `register`,
`register_modules`, `_tokenize` (static), `dispatch`, and the
`module_names` property). Once `RuntimeModule` is registered, it
remains dispatchable via the Shell (and, while the REST API Server is
running, via REST) for the remainder of the process's life,
regardless of whether the components it reports on/coordinates have
since been shut down. This is unchanged by this document: EP-060 does
not propose adding `CommandRouter.unregister()`, since nothing in its
recommended scope (Section 7, Candidate A) requires removing a command
surface — only coordinating the shutdown of the resources some of
those commands report on. After `RuntimeService.shutdown()` runs,
`runtime status` (via the Shell — the REST transport is itself one of
the two things now stopped) continues to work exactly as it does
today, now correctly reporting `api_active=False` and (per Section
5.5's disclosed limitation) inaccurately continuing to report
`background_workers_active=True`.

### 5.8 Why `CapabilityRegistryModule` (EP-056) must not be duplicated

`src/skills/capability_registry/skill.py` already implements a
running, working capability/service discovery layer: `capability list`
composes a summary of every currently-`RUNNING` plugin's declared
capability tags (`PluginService.running_plugins()`) plus the bare list
of every registered `CommandRouter` namespace
(`CommandRouter.module_names`), and `capability inject` passes that
summary through the Prompt Engine's own, previously-unused "Capability
Context" seam (`PromptBuilder.append_capabilities()`, whose docstring
literally reads *"reserved for the future Capability Registry"* —
EP-056 **is** that future Capability Registry, already built,
already wired into `Bootstrap`, already registered under the
`"capability"` `CommandRouter` namespace). This is, verbatim, the
mechanism this task's own instructions describe as "Candidate C" (*"A
capability/service registry that turns Jarvis's existing
modules/services into a discoverable operating-system-like
environment"*) — it already exists. Building a second one in EP-060
would directly violate this project's own, repeatedly-stated
Engineering Principles (`JARVIS_ROADMAP.md`: *"avoid duplicated
functionality," "reuse existing infrastructure"*) with zero new,
grounded need identified anywhere in this document's discovery.
Candidate C (Section 7) is rejected on this basis. EP-060's
recommended design does not touch `src/core/plugins/`,
`src/services/plugin_service.py`, or
`src/skills/capability_registry/skill.py` in any way.

### 5.9 `Bootstrap` does not currently expose `scheduler_service` at all

Confirmed by direct reading of `src/bootstrap.py`: inside
`_build_command_router()`, `scheduler_service = SchedulerService(...)`
(line 2041) is a **local variable**, used only to register default
jobs and to construct `SchedulerModule(scheduler_service)` (line
2044) — it is never assigned to `self._scheduler_service`, and
`Bootstrap` exposes no public `scheduler_service` property (confirmed:
`grep -n "self\._telegram_service\|self\._scheduler_service\|def
scheduler_service" src/bootstrap.py` returns no match). The same is
true of `telegram_service` (line 2059) — neither is stored on
`Bootstrap` the way `_rest_api_server`/`_background_worker_service`
already are (confirmed present, EP-059's own reuse list, Section 6.1
above). This is a real, necessary piece of file-scope this document's
recommended approach must account for (Section 9.5): observing
Scheduler's status from `RuntimeService` requires `Bootstrap` to start
holding a reference it currently discards.

---

## 6. Existing infrastructure reuse (what this document will and will not touch)

**Reusable, unmodified, as-is:**

- `RestApiServer.stop()`/`.is_running` (EP-043) — already idempotent,
  already correctly reflects post-stop state. Called, never modified.
- `BackgroundWorkerService.shutdown()`/`.status()` (EP-036) — already
  idempotent. Called, never modified (Section 5.5's limitation is
  disclosed, not fixed).
- `SchedulerService.status()` (EP-011) — already exists, already
  read-only, already safe to call regardless of tick-loop state.
  Called, never modified. `SchedulerService`'s tick loop itself is
  **not** stopped by this document's recommended approach (Section 12,
  Owner Decision D5) — only observed.
- `CommandRouter`/`CommandModule` pattern (unmodified) — `RuntimeModule`
  keeps its existing two actions; no new namespace is introduced.
- `Bootstrap`'s own existing per-subsystem property pattern
  (`rest_api_server`, `background_worker_service`, …) — extended by
  exactly one new property, `scheduler_service` (Owner Decision D6).

**Explicitly not reused, and not proposed to be built:** the
`EventBus` (Section 5.6, deliberately not used for this widening);
`CapabilityRegistryModule`/plugin infrastructure (Section 5.8,
deliberately untouched); `BackgroundWorkerPool`'s internal task-queue
logic (Candidate B, Section 7, rejected — not generalized, not
duplicated); any networking, discovery, or multi-process primitive
(none exists in this repository today, and this document proposes
none, exactly as EP-059 did not).

---

## 7. Candidate approaches

### Candidate A — Additive lifecycle control plane over `RuntimeService`/`RuntimeModule` (recommended)

**What it builds:** widens `RuntimeStatus` with two new, read-only
fields (`scheduler_active`, `scheduler_jobs_registered`), correcting
EP-059 Owner Decision D4's now-outdated premise (Section 5.3); adds
exactly one new public method, `RuntimeService.shutdown() ->
RuntimeShutdownReport`, that coordinates an ordered, idempotent
shutdown of the two execution contexts that already expose a public,
idempotent shutdown primitive (REST API Server, Background Worker
Service); and wires that new method into `Bootstrap.shutdown()`,
replacing its current REST-only body with a delegation to
`RuntimeService.shutdown()` (Section 9.5) so the one place `main.py`
already calls at process exit becomes genuinely coordinated across
every subsystem it safely can be.

**Existing components reused:** `RestApiServer.stop()`,
`BackgroundWorkerService.shutdown()`, `SchedulerService.status()`
— all already-existing, unmodified, already-public.

**New abstractions introduced:** exactly one, a small frozen
dataclass, `RuntimeShutdownReport` (Section 9.3) — no new
Engine/Manager/Provider/registry.

**Files likely affected:** `src/services/runtime_service.py` (widen),
`src/modules/runtime_module.py` (widen status formatting only — no new
action), `src/bootstrap.py` (one new attribute + property for
`scheduler_service`; one new keyword argument at the existing
`RuntimeService(...)` construction site; `shutdown()`'s existing body
replaced with a delegation — Section 9.5 discloses this is *not*
purely additive, unlike every prior EP's touch to this file).

**Why the repository provides evidence for this direction:** Section
5.4's `Bootstrap.shutdown()` gap is the single most concrete,
code-verified finding in this document — a real behavioral
inconsistency, not an interpretation of the roadmap title. EP-059
Owner Decision D5 explicitly anticipated and deferred exactly this
kind of widening (*"exists specifically so the owner can explicitly
widen this if desired"*). No other candidate below addresses this
finding as directly or with as small a footprint.

**Risks:** Section 5.4/5.5's disclosed limitations mean the resulting
system is *more correct* (background workers are actually asked to
drain) but not *fully observable* (status still can't distinguish
"running" from "just shut down" for Background Workers) — a partial,
disclosed improvement, not a complete one. `Bootstrap.shutdown()`'s
body must be altered, not merely appended to (Owner Decision D2,
Section 15) — the first non-purely-additive touch to this file across
every EP's own history in this repository (Section 12.13's audit
trail confirms EP-059 itself never altered an existing line).

**What it deliberately does not solve:** Scheduler's tick loop is
still never stopped (Section 12, "Out of Scope") — no public primitive
exists to stop it without modifying an EP-011 core file, which this
document does not authorize by default (Owner Decision D5). No
forceful/interrupt-in-flight termination of any kind is added.

**Fit with the roadmap's goal:** direct — it makes Jarvis's own
process lifecycle (start *and* stop) genuinely coordinated for the
first time, the most literal, smallest reading of "Operating System"
this document's discovery supports (a system that manages the
lifecycle of its own components), without inventing anything the
repository does not already evidence a need for.

**Duplication check:** none — `RuntimeService`/`RuntimeModule` are the
one place EP-059 already built for exactly this purpose; this is a
widening of that file pair, not a new one.

### Candidate B — Generalize `BackgroundWorkerPool` into an arbitrary task/resource operating layer (rejected for v1)

Widen EP-036's worker-thread pool so any subsystem, not only
`WorkflowEngine`, can submit background work — the mechanism
`EP059_DESIGN.md` Section 5 (its own rejected Candidate D) flagged as
*"possibly relevant to EP-060's own … capstone"* (Section 2 above).
**Not recommended:** `BackgroundWorkerPool.__init__(self,
workflow_engine: WorkflowEngine, ...)`/`submit(self, workflow_id:
str)` remain deliberately, tightly coupled to a concrete
`WorkflowEngine` (confirmed unchanged since EP-059's own reading);
genuinely widening it still requires either modifying EP-036's own
core file (against this project's own, now six-times-repeated
precedent of never altering a completed EP's core file — EP-054
through EP-059 each confirmed this explicitly) or duplicating its
thread-pool/status-tracking logic in a new, parallel class (against
the "minimal duplication" principle every EP is held to). It also does
not address Section 5.4's confirmed shutdown-coordination gap at all
— a generalized task queue is orthogonal to *whether* the pool that
already exists is gracefully drained at process exit. Recorded as the
second-most-grounded candidate (it has a real, quoted textual anchor,
unlike Candidates C/D below), but a larger, separately-scoped, future
direction, not a v1 fit.

### Candidate C — A capability/service registry over Jarvis's modules/services (rejected — already built)

**Not recommended, and not a genuine choice:** Section 5.8 confirms
this candidate already exists, complete and wired, as EP-056's
`CapabilityRegistryModule` (`capability list`/`capability inject`,
composing running-plugin capability tags and registered
`CommandRouter` namespaces). Building a second implementation would be
pure duplication, forbidden by this project's own Engineering
Principles, with zero repository evidence that the existing one is
insufficient (this document searched EP-056's design/audit
documentation and found no owner-flagged gap or deferred-scope note
suggesting a "v2" was ever anticipated).

### Candidate D — A system state/event-driven control layer coordinating execution contexts via `EventBus` (rejected for v1)

Publish lifecycle transition events (e.g., a genuine
`"runtime.shutdown_requested"`/`"runtime.shutdown_completed"` pair) and
have execution contexts react to them, rather than `RuntimeService`
calling their stop methods directly. **Not recommended:** Section 5.6
found the two existing, structurally analogous hooks
(`"orchestrator.started"`/`"orchestrator.stopped"`) have **zero
subscribers**, and `"orchestrator.stopped"` specifically is **never
even published** by the running application — `Orchestrator.stop()` is
dead code from `main.py`'s perspective today. Building EP-060 around
this pattern would mean reviving and, for the first time, wiring up an
entirely unused mechanism before any new logic could run — a larger,
more speculative footprint than Candidate A's direct method calls,
which mirror `Bootstrap.initialize()`'s own existing, working,
direct-call style exactly. It would also introduce a new,
currently-unconsumed `EventBus` event pair, compounding rather than
resolving the pattern Section 5.6 found, and would still need
something to decide *when* to publish "shutdown requested" in the
first place — unresolved by this candidate alone, and most naturally
resolved by `Bootstrap.shutdown()` calling `RuntimeService.shutdown()`
directly, i.e., Candidate A.

---

## 8. Recommended approach

**Candidate A**, per Section 7's reasoning. Everything in Sections
9–14 is provisional, written against Candidate A, and not authorized
for STEP 2 until Owner Decision D1 (Section 15) is explicitly
approved.

---

## 9. Architecture

### 9.1 `RuntimeService` — widened interface

```text
class RuntimeService:
    def __init__(
        self,
        started_at: float,
        rest_api_server: RestApiServer | None,
        background_worker_service: BackgroundWorkerService | None,
        shell: InteractiveShell | None,
        scheduler_service: SchedulerService | None = None,   # NEW, keyword-defaulted
    ) -> None: ...

    def status(self) -> RuntimeStatus: ...          # unchanged signature, widened body

    def shutdown(self) -> RuntimeShutdownReport: ... # NEW
```

`scheduler_service` is added as the **fifth**, keyword-defaulted
parameter, specifically so that every one of `tests/EP059/
test_runtime.py`'s fifteen existing `RuntimeService(...)` call sites —
all of which pass the original four arguments by keyword (Section
5.1) — continues to construct a valid `RuntimeService` completely
unchanged, with `scheduler_service` implicitly `None` (reported as
`scheduler_active=False`, matching every other "dependency not
supplied" field's existing convention). This is the same backward-
compatibility technique already used by every optional constructor
parameter elsewhere in this project's Service layer.

`RuntimeStatus` gains two new, appended fields:
`scheduler_active: bool`, `scheduler_jobs_registered: int`. Per
Section 5.1, no test constructs `RuntimeStatus` directly, so
appending fields carries zero risk to `tests/EP059/test_runtime.py`.
Both are derived, read-only, from `SchedulerService.status()` exactly
as the six background-worker fields are already derived from
`BackgroundWorkerService.status()` — no new computation.

**Telegram remains excluded**, unlike Scheduler: `telegram.auto_start`
defaults to `false` (confirmed, `TelegramService.__init__`, Section
5.2's table), so EP-059 Owner Decision D4's original reasoning still
holds for Telegram specifically. This document does not widen v1's
scope to include it (Section 12).

### 9.2 Ownership boundaries — the four distinctions this document is required to keep explicit

This document is deliberately structured around four different kinds
of thing `RuntimeService` could do, and states exactly which ones its
recommended `shutdown()` method performs:

1. **Observing runtime state** (already exists, EP-059's entire
   scope) — `status()`, read-only, unchanged in kind, merely widened
   in coverage (Section 9.1).
2. **Requesting a lifecycle transition** (this document's entire new
   surface) — `shutdown()` calls exactly two already-existing, already-
   public methods (`RestApiServer.stop()`,
   `BackgroundWorkerService.shutdown()`) in a fixed, predetermined
   order (Section 9.3). `RuntimeService` invents no new stop logic of
   its own for either component.
3. **Owning lifecycle** (explicitly **not** introduced) —
   `RuntimeService` does not construct, restart, or become the sole
   holder of any subsystem's reference. `Bootstrap` remains the sole
   constructor and sole reference-holder of every subsystem, exactly
   as today; `RuntimeService` continues to be handed already-built
   references at the end of `initialize()`, unchanged in kind from
   EP-059.
4. **Forceful termination** (explicitly **not** introduced) — no
   `kill`/interrupt-in-flight/`wait=False` path is added.
   `BackgroundWorkerService.shutdown()` is always called with its own
   default (`wait=True`), so in-flight background tasks are allowed to
   finish exactly as `BackgroundWorkerPool.shutdown()`'s own,
   unmodified docstring already documents (*"Workers finish any task
   they are currently executing … never interrupted mid-`run()`"*).

`RuntimeService`'s public surface remains exactly `{status, shutdown}`
— two methods, both read/coordinate against a fixed, hard-coded set of
already-known dependencies. It gains no `start()`, no `restart()`, no
per-component-targeted operation, and no parameterization of *which*
components to act on — there is nothing to configure, and nothing
dynamically dispatched. This is a deliberate, disclosed boundary
against the "god object" risk this task's own instructions warn
against: `RuntimeService` coordinates one predetermined sequence, not
a general control API.

### 9.3 `RuntimeService.shutdown()` — behavior specification

```text
@dataclass(frozen=True)
class RuntimeShutdownReport:
    rest_api_was_active: bool
    rest_api_stopped: bool
    background_workers_was_active: bool
    background_workers_stopped: bool

def shutdown(self) -> RuntimeShutdownReport:
    ...
```

- **Scope:** coordinates exactly the two subsystems that already
  expose a public, idempotent stop/shutdown primitive — REST API
  Server, Background Worker Service. Scheduler and Shell are
  deliberately excluded (Section 5.2, Section 12).
- **Ordering:** REST API Server is stopped **first**, Background
  Worker Service **second**. Rationale: closing the external,
  network-reachable listener before background execution is signaled
  to stop means no new HTTP-triggered `CommandRouter` dispatch
  (including a hypothetical future `worker submit`) can occur while
  the pool is draining. This mirrors no existing precedent directly
  (this is the first coordinated multi-component shutdown sequence in
  this repository), but is the same "close the front door first"
  principle `Bootstrap.initialize()`'s own construction order already
  applies in reverse (dependencies are built before the components
  that depend on them are allowed to serve traffic).
- **Idempotency:** safe to call more than once. Every underlying call
  is already independently idempotent (Section 5.2's table); a second
  call finds `RestApiServer.is_running` already `False` (`stop()`
  no-ops) and `BackgroundWorkerPool._is_shutdown` already `True`
  (`shutdown()` no-ops, per Section 5.2). `RuntimeService.shutdown()`
  itself holds no additional "already shut down" state of its own —
  it is idempotent purely by composition of already-idempotent parts,
  matching this project's own stated preference for minimal new state.
- **Behavior when a dependency is `None`:** identical to `status()`'s
  existing convention — `rest_api_was_active`/`background_workers_
  was_active` report `False` immediately, `*_stopped` reports `True`
  (nothing to do counts as success, matching
  `BackgroundWorkerService.shutdown()`'s own existing "disabled
  service reports success immediately" convention, Section 6).
- **Behavior when a component is already stopped:** `*_was_active`
  is computed from the same `status()`-equivalent read used for
  observation, so it inherits Section 5.5's disclosed limitation for
  Background Workers specifically — a *second* call to `shutdown()`
  will still report `background_workers_was_active=True` even though
  the first call already shut it down, because
  `BackgroundWorkerService.status().running` cannot distinguish the
  two states. This is documented, not hidden (Section 9.4's STEP 2
  test plan asserts this exact, surprising behavior explicitly).
- **Partial failure handling:** `RuntimeService.shutdown()` adds no
  `try`/`except` of its own around either call. `RestApiServer.stop()`
  today already propagates any OS-level exception unguarded (confirmed
  — `Bootstrap.shutdown()` calls it directly with no `try`/`except`
  today either, so this is unchanged behavior, not a new risk).
  `BackgroundWorkerService.shutdown()` already returns `False` rather
  than raising for a timeout (Section 6); `RuntimeService.shutdown()`
  forwards that `bool` into `background_workers_stopped` unchanged. If
  `RestApiServer.stop()` does raise, `BackgroundWorkerService.shutdown()`
  is never reached for that call — the ordering (Section 9.3) makes
  this a simple, sequential, fail-fast composition, not a "best
  effort, catch everything" one. This document treats that as the
  correct default (matching `Bootstrap.shutdown()`'s own current,
  unguarded behavior) and does not propose isolating failures between
  the two steps (Section 15, not raised as an Owner Decision — no
  repository evidence motivates the added complexity of partial-
  failure isolation for a two-step sequence with no existing
  precedent for it anywhere else in this codebase).

### 9.4 Testing implications of Section 9.3 (detailed further in Section 13)

The idempotency and "already stopped" behaviors above are exact,
disclosed specifications, not incidental side effects — STEP 2's test
suite (Section 13) must assert them precisely, including the
Section-5.5-disclosed `background_workers_was_active` inaccuracy on a
second call, so a future change that silently alters
`BackgroundWorkerService.status()`'s semantics is caught as a
regression against *this* document, not discovered by surprise.

### 9.5 Integration with `Bootstrap`

- **`Bootstrap.__init__`:** one new, `None`-defaulted instance
  attribute, `self._scheduler_service: SchedulerService | None = None`
  (Section 5.9).
- **`Bootstrap._build_command_router()`:** one new line immediately
  after the existing `scheduler_service = SchedulerService(config=config,
  scheduler=scheduler)` (line 2041): `self._scheduler_service =
  scheduler_service`. No reordering of any existing line.
- **`Bootstrap` public properties:** one new property,
  `scheduler_service`, mirroring the existing pattern exactly (Owner
  Decision D6, Section 15).
- **`RuntimeService(...)` construction site** (end of `initialize()`,
  unchanged position — Section 5.1/EP-059 Section 8): one new keyword
  argument, `scheduler_service=self._scheduler_service`, added to the
  existing call.
- **`Bootstrap.shutdown()` — the one non-purely-additive change in
  this document (Owner Decision D2, Section 15):**

  ```python
  def shutdown(self) -> None:
      """Coordinate shutdown of every background component started by
      this Bootstrap, via RuntimeService (EP-060). Falls back to a
      direct RestApiServer.stop() if RuntimeService was never
      constructed (e.g. initialize() was never called). Safe to call
      multiple times.
      """
      if self._runtime_service is not None:
          self._runtime_service.shutdown()
      elif self._rest_api_server is not None:
          self._rest_api_server.stop()
      self._rest_api_server = None
      self._background_worker_service = None
  ```

  This preserves every existing, observable postcondition
  (`bootstrap.rest_api_server is None` after `shutdown()`, unchanged)
  and adds one new one, symmetric with the REST API's own existing
  pattern: `bootstrap.background_worker_service is None` after
  `shutdown()` too. `self._scheduler_service` is **deliberately not**
  set to `None` here — Scheduler is not stopped by this change
  (Section 12), and nulling out a reference to a component that is
  still, in fact, running would misrepresent Bootstrap's own state.
  This is disclosed as a deliberate asymmetry, not an oversight.

  **Why this is flagged, not silently done:** every prior EP's own
  touch to `bootstrap.py` — confirmed independently by
  `EP059_ARCHITECTURE_AUDIT.md` Section 12, which re-diffed the file
  line by line — has been a **pure insertion**: new import lines, new
  attributes, new construction/registration blocks, new properties,
  never an alteration to an existing line. This document's Candidate A
  requires *altering* `shutdown()`'s existing body (not merely
  appending near it), because leaving that body's current, narrow
  REST-only behavior untouched would mean EP-060 documents the gap in
  Section 5.4 and then does nothing about it. Owner Decision D2 exists
  specifically so this one, disclosed exception to an otherwise
  unbroken precedent is explicitly approved, not assumed.

---

## 10. Component responsibilities

| Component | Responsibility (after EP-060) |
|---|---|
| `Bootstrap` | Sole constructor and reference-owner of every subsystem, unchanged. `initialize()` unchanged in structure. `shutdown()` now delegates its coordination logic to `RuntimeService`, but remains the sole thing `main.py` calls at process exit — no new caller is introduced anywhere. |
| `RuntimeService` | Sole aggregator of cross-cutting runtime **status**, and — new — sole coordinator of the specific, fixed, two-step **shutdown** sequence over the subsystems it already observes. Owns no subsystem, starts nothing, forcefully terminates nothing. |
| `RuntimeModule` | Unchanged role: thin CLI/REST-reachable formatter of `RuntimeService.status()`. Gains no new action in v1 (Owner Decision D3/D4, Section 15) — `shutdown()` is not CLI/REST-reachable. |
| `RestApiServer`, `BackgroundWorkerService` | Unchanged. Continue to own their own start/stop mechanics entirely; `RuntimeService` only calls their already-public methods. |
| `SchedulerService` | Unchanged. Observed (read-only, via `status()`) but not controlled — no shutdown call is ever made against it by this document's recommended design. |

---

## 11. Data / control flow

```text
Bootstrap.initialize()
  |-- constructs RestApiServer (if api.enabled)              [existing, EP-043]
  |-- constructs BackgroundWorkerService (if enabled)         [existing, EP-036]
  |-- constructs SchedulerService (if enabled)                [existing, EP-011,
  |                                                             auto-starts its own
  |                                                             tick thread here]
  |-- self._scheduler_service = scheduler_service              [NEW, additive]
  |-- constructs InteractiveShell                              [existing]
  '-- constructs RuntimeService(..., scheduler_service=self._scheduler_service)  [WIDENED]
      '-- registers RuntimeModule(runtime_service) with CommandRouter [unchanged]

--- normal operation: unchanged, "runtime status" reads all four --------------

src/main.py, end of a normal run:
  shell.run()                       [unchanged, blocks until exit]
  bootstrap.shutdown()              [WIDENED]
    '-- RuntimeService.shutdown()   [NEW]
          |-- rest_api_server.stop()                (1st, if present)
          '-- background_worker_service.shutdown()  (2nd, if present, wait=True)
    '-- self._rest_api_server = None                [existing postcondition]
    '-- self._background_worker_service = None      [NEW postcondition, symmetric]
    (self._scheduler_service left untouched -- Scheduler keeps running
     until the daemon thread is torn down at process exit, unchanged)
  _save_memory_on_shutdown(bootstrap)   [unchanged, unaffected]
```

No new thread, socket, file, or process is introduced anywhere in this
diagram. The only new "arrow" is `Bootstrap.shutdown()` now calling
into `RuntimeService`, and `RuntimeService.shutdown()` calling two
already-existing methods in a fixed order.

---

## 12. In Scope / Out of Scope

### In Scope

- Widening `RuntimeStatus`/`RuntimeService.status()` with
  `scheduler_active`/`scheduler_jobs_registered`, correcting EP-059
  Owner Decision D4's now-outdated premise for Scheduler specifically
  (Section 5.3).
- Adding `RuntimeService.shutdown() -> RuntimeShutdownReport`,
  coordinating REST API Server + Background Worker Service shutdown,
  in that order, reusing their already-existing, already-idempotent
  public methods only.
- Widening `Bootstrap` with one new attribute + property
  (`scheduler_service`) and rewiring `Bootstrap.shutdown()` to delegate
  to `RuntimeService.shutdown()`.
- Widening `RuntimeModule`'s existing `status` action's formatted
  output with one new line for Scheduler. No new CLI action.
- New tests under `tests/EP060/` (Section 13) plus unmodified
  re-runs of `tests/EP059/test_runtime.py`, `tests/EP036/*`,
  `tests/EP043/*` as regression.

### Out of Scope (explicitly, per this document's own findings)

- **Stopping the Scheduler's tick loop.** No public primitive exists
  (Section 5.2); adding one means modifying an EP-011 core file never
  touched since its creation — an Owner Decision (D5), not a default
  action, and **not** authorized by this document's recommended
  approach.
- **Any CLI/REST-reachable mutating `runtime` action** (e.g. `runtime
  shutdown`). Shutdown coordination is invoked exclusively by
  `Bootstrap.shutdown()`, i.e., only at genuine process exit — never
  dispatchable via the Shell or (especially) the still-unauthenticated
  REST API (Owner Decision D3, mirroring EP-059's own Owner Decision D5
  risk framing directly).
- **Telegram inclusion in status.** `telegram.auto_start` genuinely
  defaults to `false` — EP-059's original D4 reasoning still holds for
  it, unchanged.
- **Forceful/interrupt-in-flight termination of any kind.**
- **Fixing `BackgroundWorkerService.status().running`'s inability to
  reflect post-shutdown state** (Section 5.5) — would require modifying
  an EP-036 core file; disclosed as a known limitation, not remediated.
- **Reviving or wiring up `EventBus`'s `orchestrator.started`/
  `orchestrator.stopped` hooks** (Section 5.6) — evaluated, found to
  require a materially larger, more speculative change than Candidate
  A, rejected.
- **A second capability/service registry** (Section 5.8) — already
  built by EP-056; not duplicated.
- **Generalizing `BackgroundWorkerPool` into an arbitrary task queue**
  (Section 7, Candidate B) — a plausible, separately-scoped future
  direction, not v1.
- **Any multi-process, multi-machine, networking, discovery, or
  consensus mechanism** — none is evidenced as needed, exactly as
  EP-059 found for itself.
- **A new `src/core/runtime/` package** — `RuntimeService` remains a
  small, inline class in `runtime_service.py` (EP-059 Owner Decision
  D3, unchanged).
- **A `runtime.enabled`/`runtime.shutdown_timeout`-style new
  configuration key** — `RuntimeService` continues to be constructed
  unconditionally (EP-059 Owner Decision D6, unchanged); `shutdown()`
  reuses `background_workers.shutdown_timeout`'s already-existing
  default via `BackgroundWorkerService.shutdown()`'s own resolution,
  requiring no new config key of its own.

---

## 13. Testing strategy (for STEP 2)

- **`tests/EP060/test_runtime_lifecycle.py`** (new, primary suite):
  - **Widened status, backward compatibility:** construct
    `RuntimeService` with the exact original four keyword arguments
    (no `scheduler_service`) — confirms it still succeeds and
    `status().scheduler_active is False`, matching every other
    "dependency not supplied" field's existing convention. This is the
    direct regression proof for Section 9.1's backward-compatibility
    claim.
  - **Widened status, real Scheduler:** construct with a real,
    unmodified `SchedulerService` under both `scheduler.auto_start:
    true` and `false` — confirms `scheduler_active` matches
    `SchedulerService.status().running` in both cases, and
    `scheduler_jobs_registered` matches `status().jobs_registered`.
  - **`shutdown()`, all dependencies `None`:** confirms both
    `*_was_active=False`/`*_stopped=True`, never raises.
  - **`shutdown()`, real `RestApiServer` + real `BackgroundWorkerService`**
    (bound to an ephemeral local port / a real `WorkflowEngine`,
    matching EP-059's own "real objects, not mocks" precedent):
    confirms both are genuinely stopped (`rest_api_server.is_running`
    becomes `False`); explicitly asserts the Section 5.5 limitation —
    `background_worker_service.status().running` remains `True`
    afterward — so this exact, documented, non-obvious behavior is
    pinned as expected, not accidentally "fixed" by a future change
    without updating this design.
  - **Idempotency:** call `shutdown()` twice in direct succession —
    confirms no exception, and confirms the second call's report
    shows `rest_api_was_active=False` (correctly reflecting
    `is_running` is now `False`) while
    `background_workers_was_active=True` (per the same, disclosed
    Section 5.5 limitation) on the second call too.
  - **Ordering:** confirms REST API is stopped strictly before
    Background Worker Service is signaled to shut down (minimal
    instrumentation — e.g., a thin call-order-recording wrapper around
    the two real objects' `stop()`/`shutdown()` methods — is
    acceptable here specifically to verify ordering, since no simpler
    way to observe interleaving exists without it; this is the one
    place in this suite where a wrapper, not a bare real object, is
    used).
  - **`RuntimeModule` formatting:** `runtime status`'s output includes
    a Scheduler line reflecting the widened `RuntimeStatus`; confirms
    `runtime help`/action-dispatch behavior is unchanged from EP-059.
  - **Real, end-to-end `Bootstrap` test** (mirroring EP-059's own
    precedent): a full `Bootstrap().run()`, followed by `.shutdown()`
    — confirms `bootstrap.scheduler_service` is populated after
    `initialize()`; confirms `bootstrap.rest_api_server is None` and
    `bootstrap.background_worker_service is None` after `shutdown()`
    (the new, symmetric postcondition, Section 9.5); confirms a
    **second** `bootstrap.shutdown()` call remains safe (matches
    `Bootstrap.shutdown()`'s own pre-existing "safe to call multiple
    times" docstring, now proven through the new delegation path).
  - **Regression guard:** confirms `runtime status`/`worker status`/
    `scheduler status` (already-existing, unmodified actions) are
    unaffected in their own right by this widening.
- **Regression:** `tests/EP059/test_runtime.py` re-run **completely
  unmodified** — every original assertion must continue to pass
  unchanged, proving the widened constructor/dataclass are genuinely
  backward compatible, not merely by this document's own reasoning.
  `tests/EP036/*` (Background Worker Pool/Service/Module) and
  `tests/EP043/*` (REST API Server) re-run to confirm zero change to
  either subsystem's own behavior (their own files are not modified at
  all by this document).
- **Note on `SchedulerService`'s own test coverage:** this repository
  has no dedicated `tests/EP011/` suite for `SchedulerService` at all
  (confirmed: no such directory exists; only `tests/EP034/
  test_workflow_scheduler.py`, a distinct component, EP-034's own
  `WorkflowSchedulerService`). EP-060's new tests are, incidentally,
  the first automated coverage this repository has ever given
  `SchedulerService`'s auto-start/`status()` behavior — worth noting
  for the owner's awareness, not a defect this document is
  responsible for fixing.

---

## 14. Configuration considerations

**No new configuration key is proposed.** `RuntimeService` continues
to read no `runtime.*` configuration of its own (EP-059 Owner Decision
D6, unchanged) — it is constructed unconditionally, as today.
`shutdown()` reuses `BackgroundWorkerService.shutdown()`'s own,
already-existing default-timeout resolution
(`background_workers.shutdown_timeout`) by calling it with no explicit
`timeout` argument — introducing a new `runtime.shutdown_timeout` key
would only duplicate a control that already exists one layer down, so
this document does not propose one.

---

## 15. Owner Decisions

None of the decisions below is yet approved. Sections 8–13's
provisional architecture is **not** authorized for STEP 2 until D1 is
approved (and D2–D6, where applicable, are resolved).

### D1 — Which candidate should EP-060 v1 build? (primary, definitional decision)

**Question:** Given Section 2's finding that no existing file names a
specific mechanism, which of Section 7's candidates (or an
owner-supplied alternative) should EP-060 v1 actually build?
**Options:** (a) Candidate A — additive lifecycle control plane over
`RuntimeService`/`RuntimeModule` (recommended); (b) Candidate B —
generalize `BackgroundWorkerPool` into an arbitrary task queue (not
recommended for v1 — requires modifying or duplicating an EP-036 core
file, and does not address Section 5.4's confirmed gap); (c) Candidate
C — a new capability/service registry (not recommended — already built
by EP-056, would be pure duplication); (d) Candidate D — an
event-driven control layer via `EventBus` (not recommended — the two
existing analogous hooks are unused/dead code, a larger and more
speculative undertaking than (a)); (e) an owner-supplied alternative,
in which case this document would need revision before STEP 2.
**Recommended option:** (a).

### D2 — Is it acceptable for `Bootstrap.shutdown()`'s existing body to be altered, not merely appended to?

**Question:** Section 9.5 requires replacing `shutdown()`'s current,
narrow, REST-only body with a delegation to `RuntimeService.shutdown()`
— the first change to `bootstrap.py` across this project's entire
history that is not a pure insertion (confirmed by
`EP059_ARCHITECTURE_AUDIT.md` Section 12's own independent, line-by-
line re-diff of every prior EP's touch to this file). Does the owner
approve this one, disclosed exception?
**Options:** (a) approve the alteration, as proposed in Section 9.5
(recommended — the alternative leaves Section 5.4's confirmed gap
unfixed, which defeats this document's entire purpose); (b) do not
alter `shutdown()`; instead, add a new, separate, opt-in method (e.g.
`Bootstrap.shutdown_coordinated()`) that `main.py` would have to be
changed to call instead of/in addition to `shutdown()` — preserves the
insertion-only precedent, but requires an additional `main.py` change
this document did not otherwise scope, and leaves the *existing*
`shutdown()` call in `main.py` still only partially coordinating
shutdown unless replaced.
**Recommended option:** (a).
**What changes in STEP 2:** (a) → exactly Section 9.5's diff. (b) →
`main.py` enters this document's file scope (Section 12 would need
revision), and `Bootstrap.shutdown()` itself would remain as-is,
Section 5.4's gap only closed for callers who remember to call the new
method instead.

### D3 — Should shutdown coordination be reachable via CLI/REST in v1?

**Question:** EP-059 Owner Decision D5 explicitly deferred exactly
this widening to a future EP for explicit approval. Should
`RuntimeModule` gain a new, mutating `runtime shutdown` action in v1
(automatically REST-reachable and unauthenticated, per EP-059 Section
14, unchanged), or should shutdown coordination remain internal-only,
invoked solely by `Bootstrap.shutdown()` at genuine process exit?
**Options:** (a) internal-only, no new CLI/REST action (as proposed,
Section 12 "Out of Scope" — recommended, matches EP-059's own explicit
risk-minimization framing for exactly this kind of widening); (b) add
`runtime shutdown` as a new CLI action, automatically REST-reachable
and unauthenticated — a materially different, self-inflicted denial-
of-service risk (any unauthenticated caller could shut down Jarvis's
own REST API and background workers remotely) this document has not
attempted to scope or mitigate.
**Recommended option:** (a).
**What changes in STEP 2:** (a) → `RuntimeModule` gains no new action;
its `_actions` dict remains exactly `{"status": …, "help": …}`. (b) →
a new action, its own argument handling, and a dedicated security
review this document does not currently include (very likely requiring
REST authentication to be addressed first, which is itself
out-of-scope for this EP per every prior EP's own disclosure of the
same pre-existing gap, e.g. `EP059_DESIGN.md` Section 14).

### D4 — Should Telegram also be added to the widened status/shutdown scope?

**Question:** Section 9.1 keeps Telegram excluded because
`telegram.auto_start` genuinely defaults to `false` (unlike Scheduler,
where the original exclusion premise was found to be incorrect).
Should the owner nonetheless want Telegram folded in now, for
completeness?
**Options:** (a) leave Telegram excluded, as proposed (recommended —
its exclusion premise remains factually correct, unlike Scheduler's);
(b) widen `RuntimeStatus`/`RuntimeService`'s constructor to also accept
`telegram_service`, and (since `TelegramService.stop()` already exists,
Section 5.2's table) fold it into `shutdown()`'s coordinated sequence
too.
**Recommended option:** (a).
**What changes in STEP 2:** (a) → no Telegram-related change anywhere.
(b) → one more constructor parameter, two more `RuntimeStatus` fields,
one more step in `shutdown()`'s sequence (ordering relative to REST
API/Background Workers would need to be decided), and `Bootstrap`
would need `self._telegram_service`/a public property added exactly as
Section 9.5 does for `scheduler_service` (`telegram_service` has the
same Section 5.9 gap today).

### D5 — Should EP-060 add a public stop/shutdown method to `SchedulerService` (an EP-011 core file), so Scheduler can eventually be included in coordinated shutdown?

**Question:** Section 5.2 confirms `SchedulerService` has no public
counterpart to `_start_tick_loop()` at all. Closing this gap fully
(matching what this document does for REST API/Background Workers)
would require adding a genuinely new public method to a completed EP's
own core file — something no EP has done to any other EP's file across
this repository's entire history (Section 7, Candidate B's rejection
reasoning applies with equal force here).
**Options:** (a) do not modify `scheduler_service.py`; Scheduler
remains observed-but-uncontrollable in v1, explicitly documented as a
known limitation and a natural, separately-scoped EP-061+ candidate
(as proposed, Section 12 — recommended, preserves this project's own,
so-far-unbroken precedent); (b) authorize a small, additive
`SchedulerService.stop_tick_loop()`-style new method (setting the
existing, currently-unused `_stop_event` and joining `_tick_thread`),
analogous in spirit to `BackgroundWorkerService.shutdown()`, then fold
it into `RuntimeService.shutdown()`'s sequence.
**Recommended option:** (a) for v1's minimal-footprint framing —
though this document notes (b) is the more *complete* fix for Section
5.4's underlying problem, and is the most natural single follow-up EP-
061 candidate this document's own discovery surfaces, exactly as
EP-059 flagged Candidate B/D as its own follow-ups.
**What changes in STEP 2:** (a) → Scheduler status is observed only
(Section 9.1); `shutdown()`'s scope is exactly Section 9.3, unchanged.
(b) → `scheduler_service.py` enters this document's file scope for the
first time, a new method's own tests are required, and `shutdown()`'s
sequence/ordering (Section 9.3) would need to specify Scheduler's
position relative to REST API/Background Workers.

### D6 — Should `Bootstrap` gain a public `scheduler_service` property, in addition to the required private attribute?

**Question:** Section 5.9/9.5 requires a new `self._scheduler_service`
attribute regardless (it is the only way `RuntimeService` can be
handed the reference at all). A public property is not strictly
required for `RuntimeService`'s own internal use, but every other
subsystem `Bootstrap` exposes has one, for consistency and external
testability.
**Options:** (a) add the public `scheduler_service` property, mirroring
every other subsystem's existing convention exactly (as proposed —
recommended, minimal cost, matches this project's own established
pattern precisely); (b) keep `self._scheduler_service` private only,
with no public property, minimizing `Bootstrap`'s public surface by
one member.
**Recommended option:** (a).
**What changes in STEP 2:** (a) → one new `@property` block, mirroring
every existing one exactly (Section 9.5). (b) → `Bootstrap`'s public
surface is unchanged; STEP 2's end-to-end test (Section 13) would need
to reach `SchedulerService` some other way (e.g. via
`bootstrap.command_router`/`SchedulerModule` indirection) to verify
wiring, a strictly worse test ergonomics outcome for no disclosed
benefit.

---

## 16. Final recommendation

Build **Candidate A**: widen `RuntimeService`/`RuntimeModule` (EP-059)
into a small, additive lifecycle control plane — status observation
extended to correctly cover the Scheduler (Section 5.3's correction),
plus exactly one new, narrow, idempotent `shutdown()` coordination
method covering REST API Server and Background Worker Service, wired
into the one place (`Bootstrap.shutdown()`) `main.py` already calls
unconditionally at process exit. This closes a real, confirmed,
code-verified gap (Section 5.4) with the smallest possible new
abstraction (one new method, one new report dataclass, one new
Bootstrap attribute/property), explicitly declines to become a general
control API (Section 9.2's four-way ownership-boundary distinction),
and explicitly, disclosedly leaves Scheduler shutdown, Telegram
inclusion, REST-reachable control actions, and `BackgroundWorkerPool`
generalization to future, separately-scoped decisions (Owner Decisions
D4/D5, and Candidate B) rather than silently expanding this EP's own
scope to cover them.

---

## 17. Verification — file scope of this STEP 1 task

Only `docs/architecture/designs/EP060_DESIGN.md` was created by this
task. No source file (`src/**`), test file (`tests/**`), configuration
file (`config/**`), dependency file, or `src/bootstrap.py` was created
or modified. STEP 2 implementation has not begun and will not begin
without explicit owner approval of Section 15's Owner Decisions
(principally D1).
