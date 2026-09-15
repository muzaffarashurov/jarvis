# EP-093 — STEP 1: Architecture Discovery & Design

## Electricity & Gas Monitoring

**Revision note:** this document was revised after its initial draft
to resolve the acquisition-mechanism blocker identified there. See the
"STEP 1 Revision Summary" at the end for the consolidated result;
Sections 0-5, 7-8 (data model), 11-14 carry over from the original
investigation largely unchanged, Section 6 was substantially revised,
and Sections 9, 15-17 and the Owner Decision Summary were updated for
consistency with that revision.

## 0. Status

`DESIGN PROPOSED — awaiting Owner Decision`

---

## 0.1 Source-of-Truth Note

No GitHub connector is available in this session. Per the established
pattern for this project (see `EP092_DESIGN.md` §0), the repository
state already extracted from the project owner's uploaded archive in
this session (`/home/claude/jarvis/jarvis-main`) was used as the
current repository state, verified as of this task's start by direct
`grep`/`view` against the actual files — not by memory of any prior
EP's content, including EP-092's own design/audit documents, which
were re-read fresh for this task rather than assumed from
conversation history.

---

## 1. Scope Verification

**What EP-093 is:** the first concrete consumer of EP-092's
domain-agnostic Personal Data Collection Framework. Per
`docs/BACKLOG.md` line 3130, EP-093 is titled **"Electricity & Gas
Monitoring"** (MEDIUM priority), the first of the six EPs
(EP-093–EP-098) in `docs/architecture/JARVIS_ROADMAP.md`'s "Phase E —
Personal Intelligence / Energy / Weather" that EP-092's own STEP 1
design explicitly anticipated: *"EP-093 (Electricity & Gas), EP-094
(Solar), and EP-097 (Weather) each add one `PersonalDataSource`
implementation plus their own Scheduler Job"* (`EP092_DESIGN.md` §11,
"FUTURE INTEGRATION").

EP-093's exact architectural responsibility, as evidenced by that
already-approved and already-implemented boundary:

1. Implement one or more concrete `PersonalDataSource` subclasses
   (`src/core/personal_data/personal_data_source.py`'s `ABC`) that
   produce electricity- and gas-consumption `PersonalDataPoint`s.
2. Make electricity/gas collection operable end-to-end: register the
   source(s) with a `PersonalDataManager`, and — since no such surface
   currently exists (Section 2, Finding F3) — provide the CLI command
   surface and Scheduler wiring needed to actually run collection, not
   just define the source class.
3. Define the electricity/gas-specific configuration (which
   acquisition mechanism, credentials/paths, meter identifiers, units)
   needed to construct and run those sources.

**What EP-093 is not:**

- It is not a second data-collection framework. Registry, manager,
  provider, persistence, and the consent gate are all owned by EP-092
  and must be consumed, not re-implemented (Section 5).
- It is not solar (EP-094), visualization/reporting (EP-095),
  forecasting/anomaly detection (EP-096), weather (EP-097), or
  recommendations (EP-098) — each is a separate, later EP in the same
  phase.
- It is not a generic "connect any external API" framework. Per
  `AI_GENERATION_STANDARD.md`'s Unknown API Policy ("If a required
  method does not exist, DO NOT invent it... Never invent APIs"), and
  because no electricity/gas vendor, protocol, or API is named
  anywhere in this repository (Section 2, Finding F5), EP-093 must not
  invent a specific vendor integration speculatively.

**Why this responsibility belongs to EP-093 specifically (not EP-092
or a later EP):** EP-092's own design (`EP092_DESIGN.md` §6
"Non-Goals") explicitly excludes "any electricity, gas, solar, or
weather-specific code, units, or API clients," assigning that
explicitly to "EP-093/094/097." No later EP in Phase E is described as
owning ingestion (EP-095 is visualization, EP-096 is
forecasting/anomaly detection, EP-098 is recommendations — all
consumers of collected data, not producers of it, per
`docs/BACKLOG.md`'s Phase E list). EP-093 is therefore the correct and
only owner of electricity/gas *ingestion*.

---

## 2. Evidence

Files and existing implementations inspected for this design, with
the specific finding each supports:

| # | Evidence | Finding |
|---|---|---|
| E1 | `docs/BACKLOG.md` line 3130 | EP-093's title and priority are the *only* specification that exists; no further detail (acquisition mechanism, units, cadence, vendor) is given anywhere. |
| E2 | `docs/architecture/JARVIS_ROADMAP.md` "Phase E" section (~line 2420) | EP-093 sits in a "planning only" phase; grouped EP-092–098; no EP-093-specific detail beyond the phase grouping already known from EP-092's own design. |
| E3 | `docs/architecture/designs/` and `docs/architecture/audits/` directory listings | No `EP093_DESIGN.md` or `EP093_*AUDIT*.md` exists yet — confirmed by direct listing, not assumption. |
| E4 | Repository-wide `grep -rniE "electricity\|kwh\|smart meter\|utility api\|tibber\|octopus energy\|shelly\|p1 dongle"` | Zero hits outside EP-092's own already-known files (`personal_data_record.py`, `personal_data_source.py`, `config.yaml`, `tests/EP092/...`) and EP-092's own design/audit docs. No vendor, protocol, or specific API is named anywhere in this codebase. |
| E5 | `docs/architecture/designs/EP092_DESIGN.md` (full document, re-read fresh) | Defines `PersonalDataPoint`, `PersonalDataSource`, `PersonalDataProvider`/`JsonlPersonalDataProvider`, `PersonalDataPersistence`, `PersonalDataRegistry`, `PersonalDataManager`/`PersonalDataCollectionError`, `PersonalDataService` — the exact abstractions EP-093 must consume. §11 "FUTURE INTEGRATION" explicitly names EP-093 as the first `PersonalDataSource` implementer. |
| E6 | `docs/architecture/audits/EP092_ARCHITECTURE_AUDIT.md` (full document, re-read fresh, including its STEP 3 remediation §18) | EP-092's final verdict is **PASS** — no open HIGH/MEDIUM finding remains, so EP-093 can safely build on it as a stable foundation. `store_if_new()` is confirmed as the sole atomic dedup-safe write path (relevant to Section 6/7 below — EP-093 must never call `exists()`+`store()` separately). |
| E7 | `src/core/personal_data/*.py`, `src/services/personal_data_service.py` (actual source, re-read fresh, not from memory) | Confirms the exact public API EP-093 will call: `PersonalDataManager.register_source(source)`, `.collect_from(source_id) -> int`, `.query(...)`; `PersonalDataService.register_source(source) -> CommandResult`, `.collect(source_id) -> CommandResult`, `.query(...)`, `.status()`. Confirms `PersonalDataSource` is an `ABC` with `source_id`, `category` properties and `collect() -> list[PersonalDataPoint]`. |
| E8 | `config/config.yaml` `personal_data:` block | `enabled: true`, `enabled_categories: []` (empty — nothing collected until an operator adds a category), `storage_root: "data/database/personal_data"`. EP-093 will add its own category names to this existing list, not invent a parallel enable mechanism. |
| E9 | `src/modules/` directory listing (33 files) | **No `personal_data_module.py` exists.** Every other core subsystem with a `*_service.py` has a matching `*_module.py` CLI surface (`long_term_memory_module.py`, `knowledge_module.py`, `memory_module.py`, etc.) — `PersonalDataService` is the one exception, confirming it has no CLI command surface today. |
| E10 | `src/core/scheduler/scheduler.py` `Scheduler.run_job()` (line ~178): `result = self._execution_engine.run(job.command)` | Every Scheduler `Job.command`, with no exception, is dispatched through `ExecutionEngine.run()`. |
| E11 | `src/core/scheduler/job.py` `Job.command`'s own docstring: *"Raw target string passed unchanged to ExecutionEngine.run() -- never interpreted by the Scheduler itself."* | Confirms E10 is not an implementation detail that might change casually — it is the documented contract of `Job.command`. |
| E12 | `src/core/execution/engine.py` `ExecutionEngine`'s class docstring: *"a program name, file path, or URL"* | `ExecutionEngine` dispatches to `Executor` implementations chosen by `supports(raw_target)`; it has no concept of an internal service/CLI command. |
| E13 | `src/core/execution/executors/python_executor.py` `PythonExecutor.run()`: `subprocess.Popen([sys.executable, str(path)])`, with `supports()` requiring `Path(raw_target...).suffix.lower() == ".py"` | A Scheduler Job pointed at a `.py` file launches it as a **subprocess with no arguments** — `Job.command` is a single string with no argument-splitting mechanism into the target script. |
| E14 | `src/bootstrap.py` (~line 2440-2487), the *only* two real `Job(...)` construction sites in the entire codebase (`invoice_automation`, `fast_response_board`) | Both use `command=<a config-supplied file path>` (`invoice.script`, `fast_response.workbook`) and `schedule=Schedule(type=ScheduleType.MANUAL)`. This is the codebase's own, actually-used precedent for how a Job should reference work: an external, config-driven file path — never an internal method call, and never with the schedule type doing anything different to how `command` is interpreted. |
| E15 | `AI_GENERATION_STANDARD.md` "Unknown API Policy" (~line 144) and the comment at `src/bootstrap.py` ~line 2436 explicitly invoking it (*"there is no real backup target defined in this project's configuration, so registering it would mean inventing one -- forbidden by AI_GENERATION_STANDARD.md's Unknown API Policy"*) | Direct, in-repository precedent for exactly EP-093's situation: when no real external target/API is defined in configuration, the correct action is to document the gap (a `# TODO:` comment, in that example), not invent one. |
| E16 | `grep` across `src/core/*/provider*.py` for any generic external-HTTP-API base class | Every `*Provider` abstraction in this codebase (`AIProvider`, `EmbeddingProvider`, `PlanningProvider`, etc.) is a domain-specific pluggable-backend abstraction for that subsystem, not a generic, reusable "call an external REST API" client. `ClaudeProvider`/`GeminiProvider` each call `requests.post(...)` directly with their own URL/header/timeout handling — there is no shared HTTP client utility to reuse. |
| E17 | `tests/EP092/`, `tests/EP069_3/`, `tests/EP025/`, etc. directory listings | Confirms the universal `tests/EP###/` convention: one `__init__.py` + one `test_<name>.py` file, one `TestRegistry`-registered `BaseTest` subclass. |
| E18 | `.env.example` | Confirms the existing convention: any real credential a concrete `PersonalDataSource` needs belongs in `.env`, read through `Config`, never hardcoded or placed in `config.yaml`. |

No architectural claim in this document is made without a
corresponding row above.

---

## 3. Dependency Analysis

**Direct dependencies:**

- `src/core/personal_data/` (EP-092) — `PersonalDataSource` (the
  contract EP-093 implements), `PersonalDataPoint` (the value object
  EP-093 constructs), `PersonalDataManager` (registration/collection),
  `PersonalDataRegistry` (indirectly, via the manager).
- `src/services/personal_data_service.py` (EP-092) — the CLI-facing
  layer EP-093's new CLI module will call, exactly as
  `long_term_memory_module.py` calls `LongTermMemoryService` (E9).
- `src/core/config.py` (`Config`) — for EP-093's own configuration
  keys, exactly as every existing subsystem reads its own section.
- `src/core/command_router.py` (`CommandResult`) — the CLI module's
  return type, matching every existing `*_module.py`.
- `src/testing/` (`BaseTest`/`TestRegistry`/`TestRunner`) — required
  for `tests/EP093/`.

**Indirect dependencies (via EP-092, not touched directly):**

- `src/core/personal_data/personal_data_provider.py` /
  `personal_data_persistence.py` — EP-093 never imports these
  directly; it only ever goes through `PersonalDataManager`/
  `PersonalDataService` (Section 11's layering rule makes this
  explicit).

**Optional, conditional on the Owner Decision in Section 4/6:**

- `src/core/scheduler/` (EP-011) — required only if/when automatic,
  unattended collection is enabled (Section 10); not required for a
  manually-triggered v1.
- Whatever a chosen concrete acquisition mechanism needs (e.g. the
  `csv` standard-library module for a CSV-import source) — deferred
  until Section 4's Owner Decision is made; not resolved by this
  document.

**Is EP-092 a dependency of EP-093?** Yes — EP-093 cannot exist without
it; it supplies the contract, the storage, and the consent gate
EP-093's sources plug into.

**Is EP-093 a dependency of later EPs?** Per `EP092_DESIGN.md` §11: not
directly. EP-095 (Visualization), EP-096 (Forecast/Anomaly), and
EP-098 (Recommendation) are documented to read through
`PersonalDataManager.query()`/`PersonalDataService.query()` — the
*category* EP-093 collects into (`electricity_consumption`,
`gas_consumption`, Section 8) becomes their input, but they depend on
EP-092's query surface and on data existing in that category, not on
EP-093's internal implementation. EP-094 (Solar) and EP-097 (Weather)
are structurally parallel to EP-093 (each their own
`PersonalDataSource`), not dependent on it.

---

## 4. Conflict Analysis

| Area / EP | Potential Conflict | Finding | Resolution |
|---|---|---|---|
| EP-092 Personal Data Collection Framework | EP-093 could duplicate registry/manager/provider/persistence, or bypass the consent gate | Checked `PersonalDataManager`'s actual public API (E7): it already provides everything a source-adding EP needs (`register_source`, `collect_from`, `query`). Duplicating any of it would violate `AI_GENERATION_STANDARD.md`'s Existing Code Policy and EP-092's own explicit non-goal boundary. | **A — proceed with constrained scope.** EP-093 consumes EP-092's abstractions exclusively (Section 5, Section 11); it introduces no new registry, manager, provider, or persistence mechanism. |
| EP-011 Scheduler | A naive design might assume `Job.command` can invoke `PersonalDataService.collect()` directly, as EP-092's own STEP 1 design informally assumed ("`command` referencing something like `personal_data.collect:<source_id>`", `EP092_DESIGN.md` §12) | Directly refuted by evidence E10-E14: `Job.command` only ever dispatches to `ExecutionEngine`, which only launches external programs/files/URLs, never an in-process method call, and carries no arguments. This is a **real, previously-undocumented gap in EP-092's own design assumption**, only surfaced now because EP-093 is the first EP that actually needs Scheduler-driven automatic collection to work. | **A — proceed with constrained scope**, using existing infrastructure correctly rather than inventing new infrastructure: a single standalone collection script (not one script per source, since `Job.command` cannot carry arguments, E13) that iterates every registered/configured source and calls `PersonalDataService.collect(source_id)` for each; that script's path becomes a Scheduler `Job.command`, exactly matching the codebase's own only real precedent (E14). No change to Scheduler, `ExecutionEngine`, or `CommandRouter` is required or proposed. See Section 10. |
| CLI / `src/modules/` | EP-093 needs a working CLI command surface for `personal_data`, but none exists (E9) — is inventing `personal_data_module.py` "EP-093 doing EP-092's job," or legitimate? | EP-092's own STEP 1 design's §18 File Impact table never listed a CLI module as in-scope, and its STEP 3 audit (re-read fresh, E6) raised no finding about its absence — it was a deliberate, accepted omission, not an oversight EP-092 left unresolved for itself to fix later. EP-093 is the first and only current consumer that actually needs `PersonalDataService` reachable from the shell/Scheduler. | **A — proceed with constrained scope.** EP-093 creates `src/modules/personal_data_module.py`, following the exact `long_term_memory_module.py` pattern (E9): thin CLI parsing only, all logic in `PersonalDataService`. This is not "redesigning EP-092" — the module contains zero EP-092 business logic, only argument parsing and `CommandResult` formatting, matching every existing `*_module.py` in this repository. |
| Unknown external API / vendor | EP-093's title implies "monitoring," which colloquially suggests live polling of a smart meter or utility API — but no such API is named anywhere (E4) | Per `AI_GENERATION_STANDARD.md`'s Unknown API Policy (E15) and its own directly-applicable precedent in `bootstrap.py` (E14's surrounding comment), inventing a specific vendor integration now would be exactly the forbidden pattern. | **C — scope must be adjusted / Owner Decision required.** See Section 6's Owner Decision: recommend a manual/CSV-import acquisition mechanism for v1 (requires no unknown API), with a specific vendor/API integration explicitly deferred to a follow-up once the Owner names one. |
| EP-094 (Solar), EP-097 (Weather) | Could EP-093 accidentally build something so specific to electricity/gas that EP-094/097 can't reuse the pattern? | Checked `EP092_DESIGN.md` §11 "FUTURE INTEGRATION" — each of EP-093/094/097 is expected to add *its own* `PersonalDataSource`; there is no shared "energy source" abstraction above `PersonalDataSource` itself that EP-092 defined for them to jointly extend. | **No conflict.** EP-093's concrete `PersonalDataSource` subclass(es) and its CLI module additions (`personal_data <action>`, extended with electricity/gas-specific actions, or category-agnostic actions reusable by EP-094/097 — see Section 6) are additive; nothing in EP-093's proposed design prevents EP-094/097 from following the identical pattern (their own `PersonalDataSource` subclass, registered the same way). |
| EP-095/096/098 (Visualization/Forecast/Recommendation) | Could EP-093 be tempted to add visualization, trend detection, or recommendation logic since it's "the first one built" and it might seem convenient? | Checked `docs/BACKLOG.md`'s Phase E list: EP-095/096/098 are separately titled and scoped. EP-093's backlog entry has no such scope. | **No conflict, provided scope discipline is maintained** — explicitly enforced in Section 15 (Deferred / Out of Scope). |
| EP-069.x (AI Provider & Tool Registry) | Could EP-093's electricity/gas API client duplicate or need to integrate with the AI provider/tool framework? | Checked `EP069_3_DESIGN.md`/audit and `src/core/ai/`, `src/core/tool/` — these are for LLM providers and agent-invokable tools, an entirely different concern (E16: no generic external-API-client abstraction exists there either, nor would collecting electricity data be an "AI provider"). | **No conflict** — no overlap in responsibility; EP-093 has no dependency on EP-069.x and vice versa. |
| Roadmap/backlog structure itself | Is the roadmap internally consistent for EP-093? | `docs/BACKLOG.md` and `docs/architecture/JARVIS_ROADMAP.md` agree with each other (both place EP-093 as "Electricity & Gas Monitoring" in Phase E, first after EP-092) — no contradiction found between the two documents. | **No roadmap inconsistency found** — only *underspecification* (no acquisition-mechanism detail), which is a normal, expected state for a "planning only" phase entry and is resolved via the Owner Decision in Section 6, not a roadmap defect requiring correction. |

---

## 5. Responsibility Boundary

**EP-092 owns (unchanged, not modified by EP-093):**

- The `PersonalDataPoint` data shape, its `timestamp`/`collected_at`
  semantics, and its dedup key `(source_id, category, timestamp)`.
- The `PersonalDataSource` abstract contract's shape (EP-093
  implements it; does not alter it).
- `PersonalDataRegistry`, `PersonalDataManager` (including the
  atomic, concurrency-safe `store_if_new()`-based collection cycle and
  the consent gate against `personal_data.enabled_categories`),
  `PersonalDataProvider`/`JsonlPersonalDataProvider`,
  `PersonalDataPersistence` — the entire storage and orchestration
  stack.
- `PersonalDataService` and its `CommandResult` boundary.
- The `personal_data:` config block's existing keys (`enabled`,
  `enabled_categories`, `storage_root`).

**EP-093 owns (new):**

- One or more concrete `PersonalDataSource` subclasses for
  electricity and gas consumption (Section 6, Section 8).
- The category names `electricity_consumption` and
  `gas_consumption` (Section 8) — EP-093 is their sole producer.
- `src/modules/personal_data_module.py` — the CLI command surface for
  `PersonalDataService` (Section 4's second-to-last conflict row;
  Section 6).
- EP-093-specific configuration: which acquisition mechanism is
  active, and whatever that mechanism needs (Section 9).
- The standalone collection-runner script used for Scheduler
  integration (Section 10), if/when automatic collection is enabled.
- Its own `tests/EP093/` suite.

**Existing infrastructure owns (consumed as-is, not modified):**

- `Config`/`.env` (credential and settings resolution).
- `CommandResult`/`command_router.py` (CLI return type).
- `Scheduler`/`Job`/`ExecutionEngine`/`PythonExecutor` (automatic
  execution, if enabled) — used exactly as they exist today (E10-E14);
  no change proposed to any of them.
- `BaseTest`/`TestRegistry`/`TestRunner` (testing).

**Future EPs must own:**

- EP-094: its own `PersonalDataSource` for solar generation, following
  the identical pattern EP-093 establishes — not EP-093's concern to
  pre-build.
- EP-095/096/098: all reading, visualization, forecasting, and
  recommendation logic over the `electricity_consumption`/
  `gas_consumption` categories EP-093 populates — EP-093 must not
  implement any of this itself (Section 15).
- EP-097: weather, structurally parallel to EP-093, not derived from
  it.

---

## 6. Proposed Architecture

### 6.1 Overview

```text
                    ┌───────────────────────────┐
                    │   personal_data_module.py  │  NEW — CLI surface (EP-093)
                    │   (thin CommandModule)     │  following long_term_memory_module.py
                    └─────────────┬───────────────┘
                                  │  calls
                    ┌─────────────▼───────────────┐
                    │   PersonalDataService        │  EP-092, UNCHANGED, consumed as-is
                    └─────────────┬───────────────┘
                                  │  calls
                    ┌─────────────▼───────────────┐
                    │   PersonalDataManager        │  EP-092, UNCHANGED
                    └───┬─────────────────────┬───┘
                        │ register_source()    │ collect_from(source_id)
          ┌─────────────▼─────────┐  ┌─────────▼──────────────────┐
          │ PersonalDataRegistry   │  │ (concrete) ElectricitySource │  NEW (EP-093)
          │ EP-092, UNCHANGED      │  │ (concrete) GasSource          │  NEW (EP-093)
          └────────────────────────┘  │  implements PersonalDataSource│
                                       └────────────────────────────┘
                                                  │ (Section 6.4 --
                                                  │  manual/CSV V1,
                                                  │  RESOLVED, no
                                                  │  provider layer)

    Scheduler integration (only if automatic collection is enabled, Section 10):

    scripts/collect_personal_data.py   NEW (EP-093) -- standalone script,
            │                          iterates configured sources, calls
            │                          PersonalDataService.collect(source_id)
            │                          for each
            ▼
    Job(command="scripts/collect_personal_data.py", schedule=Schedule(INTERVAL, ...))
    -- registered via existing SchedulerService/CLI, exactly like the
       invoice_automation/fast_response_board precedent (E14)
```

### 6.2 Acquisition Architecture Decision (Design A vs Design B) — RESOLVED

This section replaces the original design's open "Option A/B/C"
framing (which conflated two separate questions) with two
independently-resolved questions, per the STEP 1 revision instructions.

**Question 1 — does EP-093 need its own acquisition-provider
abstraction, separate from `PersonalDataSource`?**

Evaluated as instructed (Section 11 of the revision task), evidence-first:

| | **Design A** — no new abstraction; CSV/manual logic lives directly inside a concrete `PersonalDataSource` subclass | **Design B** — a new EP-093-owned `AcquisitionProvider` interface, with the `PersonalDataSource` subclass delegating to a pluggable provider instance |
|---|---|---|
| Complexity | One class, one job. | Two abstraction layers doing nearly the same job (see "duplication" below). |
| Testability | Direct: construct with a CSV path or reading log, test `collect()`. | Marginally more moving parts, with no current second implementation to justify the polymorphism. |
| Future extension | A future vendor becomes a **new, independent `PersonalDataSource` subclass**, registered via the existing `PersonalDataManager.register_source()` — already fully supported today, for any number of sources, per category. | A future vendor becomes a new `AcquisitionProvider` implementation — functionally equivalent capability, gained at the cost of an extra layer. |
| Coupling | CSV-specific parsing is fully contained in one class; nothing else in EP-093 or EP-092 knows about CSV. | Same isolation is achievable, but only by introducing a second data-transfer shape (a "raw reading" type) that has to be kept in sync with `PersonalDataPoint`'s own fields — added surface for zero current benefit. |
| Duplication | None — `PersonalDataSource` (`source_id`, `category`, `collect() -> list[PersonalDataPoint]`) already *is* the acquisition-provider contract the task's Section 3 asks whether EP-093 needs to invent. | A new `AcquisitionProvider` interface (something like `fetch() -> list[RawReading]` plus a normalization step) is nearly isomorphic to `PersonalDataSource` itself — duplicating a contract EP-092 already supplies. |
| EP-092 compatibility | Full — nothing added between EP-093's code and EP-092's contract. | Also compatible, but redundant with the extension point EP-092 already exposes. |
| Risk of speculative architecture | None — this is "implement the interface EP-092 already gives you." | High — a generic provider abstraction built for a hypothetical second implementation that does not exist yet is exactly the pattern this project's conventions warn against (Section 2, E15; the already-rejected Option C "generic HTTP adapter" from this design's first draft is a close cousin of this same mistake, one layer up). |

**Resolution: Design A.** A separate acquisition-provider abstraction
is **not** justified. `PersonalDataSource` (EP-092) already is the
correctly-scoped "acquisition provider" boundary the task's Section 3
asks about — reusing it directly, rather than wrapping it in a second,
EP-093-owned interface, is the smallest correct architecture and the
literal application of "reuse EP-092's existing provider/source
abstractions where appropriate" and "do not duplicate them." Each
future acquisition mechanism (manual/CSV today; a named vendor API
later) becomes its **own concrete `PersonalDataSource` subclass**,
registered independently — including, if ever useful, running more
than one simultaneously (e.g. CSV import *and* a real API both feeding
`electricity_consumption`, under different `source_id`s), which
`PersonalDataRegistry`/`PersonalDataManager` already support with no
change.

This directly answers the task's conceptual diagram
("Acquisition Provider -> Electricity/Gas Data -> EP-093 normalization
-> EP-092 PersonalDataService -> EP-092 persistence"): all three of
"Acquisition Provider," "Electricity/Gas Data," and "EP-093
normalization/validation" collapse into a single method —
`collect()` — on one concrete `PersonalDataSource` subclass per
mechanism. No standalone "normalization" component or "provider"
component is introduced above or beside it.

**Question 2 — is manual/CSV import sufficient to fully specify a V1
without knowing a future real vendor?**

Yes — evaluated in full in Section 6.3-6.6 and Section 8 below.
Nothing about a CSV/manual reading's shape (a date, a value, a unit,
optionally a meter identifier) depends on which real vendor is chosen
later; the canonical data contract (Section 8) is deliberately vendor-
independent. This resolves what was previously this design's sole
blocker: manual/CSV is not a stand-in guess at an unknown API, it is a
complete, self-contained V1 acquisition mechanism in its own right.

**Consequence:** manual/CSV import is no longer merely "recommended
pending confirmation" — per the STEP 1 revision task's own instruction
("that alone should NOT necessarily block the architecture if a clean
provider boundary allows a manual/CSV first provider... make
manual/CSV the explicitly scoped V1"), it is adopted here as EP-093's
scoped V1 acquisition mechanism. A real named vendor/API remains
explicitly deferred (Section 6.6), and does not block STEP 2.

### 6.3 Components

**`ElectricityCsvSource` / `GasCsvSource`**
(`src/core/personal_data/sources/electricity_source.py`,
`gas_source.py` — new package, peer files, not inside EP-092's own
`src/core/personal_data/` package, to keep EP-092's package free of
any EP-093-owned code per Section 11's layering rule)

- Implements `PersonalDataSource` directly (Section 6.2's Design A
  resolution — no intermediate provider interface): `source_id` (e.g.
  `"electricity_csv_import"`/`"electricity_manual_entry"` — Section
  6.4 defines both a CSV-file mechanism and a manual single-reading
  mechanism as two small, independent concrete subclasses, not one
  class trying to do both), `category` (`"electricity_consumption"` /
  `"gas_consumption"`), `collect()`.
- `collect()` contains 100% of the CSV-parsing/manual-log-reading logic
  itself (Section 6.2's Design A) — there is no separate
  "acquisition provider" object it delegates to.
- Never touches `PersonalDataProvider`, `PersonalDataPersistence`,
  `PersonalDataRegistry`, or `CommandResult` directly (Section 11).

**`personal_data_module.py`** (`src/modules/`)

- Thin `CommandModule`, `name = "personal_data"` (Section 9 confirms
  this stays the *only* CLI namespace EP-093 touches — no separate
  `electricity`/`gas` namespaces), mirroring `long_term_memory_module.py`
  exactly (E9): a `HELP_TEXT`, an `_actions: dict[str, ActionHandler]`
  dispatch table, each handler a few lines that parse arguments and
  call one `PersonalDataService` method, formatting its
  `CommandResult`/return value.
- Actions: `status`, `collect <source_id>`, `query <category>
  [start] [end]`, `help`, plus, for the now-confirmed manual/CSV V1
  (Section 6.4): `record-reading <category> <value> <unit>
  [timestamp]` and `import-csv <category> <path>`.
- Zero business logic; all delegated to `PersonalDataService`
  (already implemented, unchanged) — see Section 9's full
  CLI-boundary discussion for why no per-domain verbs are introduced.

**`scripts/collect_personal_data.py`** (only if Section 10's automatic
collection is enabled)

- A standalone script (not a package module) that boots a minimal
  `Config`, constructs the same default `PersonalDataService` wiring
  `PersonalDataService.__init__` already builds when no manager is
  injected, iterates every source EP-093 has configured (Section 9),
  and calls `.collect(source_id)` for each, logging the outcome and
  exiting non-zero on any failure (for `scheduler info`'s `last_run`
  status to reflect it, via `ExecutionResult.success`).
- Exists specifically because `Job.command` cannot carry arguments
  (E13) — one script handling every configured source avoids needing
  one script per source. Full ownership boundary in Section 10.

### 6.4 Manual / CSV V1 — Confirmed Scope

Two small, independent concrete `PersonalDataSource` subclasses (per
category, each in both a manual and CSV form — four classes total, or
two classes each supporting both modes internally; a STEP 2 detail
that does not affect this architecture either way):

- **Manual entry**: the `personal_data record-reading <category>
  <value> <unit> [timestamp]` CLI action appends the reading to a
  small, EP-093-owned append-only log (its own file under, e.g.,
  `data/database/personal_data_electricity_gas/manual_readings_
  <category>.log` — deliberately **not** inside
  `data/database/personal_data/`, which is EP-092's exclusive
  persisted-output space, per Section 11's ownership rule); the
  matching `PersonalDataSource.collect()` reads whatever log entries
  have not yet been returned and turns them into `PersonalDataPoint`s.
- **CSV import**: the `personal_data import-csv <category> <path>` CLI
  action (or the configured `csv_import_path`, Section 9) points a
  `PersonalDataSource.collect()` at a CSV file; each unprocessed row
  becomes one `PersonalDataPoint`.

**Canonical CSV format** (EP-093's own, not a utility-specific export
format — per the revision task's explicit instruction not to invent a
utility-company-specific format):

```csv
date,value,unit,meter_id
2026-01-01,412.5,kWh,
2026-01-02,418.2,kWh,main
```

- **Required fields**: `date` (ISO-8601 date or datetime; a bare date
  is treated as midnight UTC on that date), `value` (a plain decimal
  number), `unit` (a non-empty string, e.g. `"kWh"`/`"m3"`).
- **Optional fields**: `meter_id` (free text; folded into
  `PersonalDataPoint.raw` and, if present, appended to `source_id` for
  disambiguation when multiple meters share one CSV/category — Section
  6.6 revisits multi-meter identification).
- **Electricity units**: `kWh` is the expected default; the field is
  free text (matching `PersonalDataPoint.unit`'s own "non-empty
  string, no conversion" contract, `EP092_DESIGN.md` §12) — EP-093
  performs no unit conversion.
- **Gas units**: commonly `m3` or `kWh`-equivalent depending on the
  operator's utility billing convention; same free-text, no-conversion
  handling.
- **Timestamp/date semantics**: `date` maps to `PersonalDataPoint.
  timestamp` (the measurement time — Section 8); `collected_at` is set
  to "now" at import time, exactly matching EP-092's existing
  distinction (`EP092_DESIGN.md` §12) — never conflated.
- **Meter/source identification**: `source_id` identifies *which
  acquisition mechanism/meter* produced a point (e.g.
  `"electricity_csv_import"`, or `"electricity_csv_import:main"` when
  `meter_id` disambiguates multiple meters); `category` identifies
  *what kind* of measurement it is. Both are orthogonal to EP-092's
  existing dedup key `(source_id, category, timestamp)` — unchanged.
- **Validation**: a row missing `date`, `value`, or `unit`, or with a
  non-numeric `value`, is rejected before construction reaches
  `PersonalDataPoint` (which would itself raise `TypeError`/
  `ValueError` for a bad `value`/timestamp per its existing
  `__post_init__`, `EP092_DESIGN.md` §12 — EP-093's row-level
  validation exists to produce a clear, row-specific error message
  rather than relying on that lower-level exception alone).
- **Duplicate handling**: entirely delegated to EP-092's existing
  `store_if_new()` dedup on `(source_id, category, timestamp)`
  (`EP092_ARCHITECTURE_AUDIT.md`, EP092-AUDIT-002, fixed and verified)
  — EP-093 introduces no second dedup mechanism. Re-importing the same
  CSV file a second time is therefore already safe by construction.
- **Invalid-row handling**: one malformed row is logged and skipped;
  it must not abort processing of the remaining rows (mirrors
  `JsonlPersonalDataProvider`'s own established "one bad line never
  aborts the whole operation" convention, `EP092_ARCHITECTURE_AUDIT.md`
  §9/§18, EP092-AUDIT-004 — the same principle, applied at CSV-import
  time instead of at persisted-file-read time).
- **Missing-data handling**: a gap in dates (e.g. no reading for three
  days) is not an error — `collect()` simply returns points for the
  rows/entries that exist; EP-093 performs no interpolation or
  estimation (that would be forecasting/analytics territory, Section
  7, explicitly deferred to EP-096).
- **Conversion rules**: none — EP-093 stores exactly the `value`/`unit`
  given, performing no unit conversion (consistent with EP-092's own
  "no unit conversion or validation beyond requiring a non-empty
  string" scope, `EP092_DESIGN.md` §12).
- **Normalization**: limited to mapping CSV columns / manual-entry CLI
  arguments onto `PersonalDataPoint`'s fields correctly (Section 8) —
  no semantic transformation of the values themselves.
- **Error reporting**: `collect()` raises (surfacing as
  `PersonalDataCollectionError` via `PersonalDataManager`, unchanged)
  only for a failure that prevents *any* progress (e.g. the CSV file
  does not exist at all); a per-row problem within an otherwise
  readable file is reported via logging and a skip, not a raised
  exception, matching the "invalid-row handling" rule above.

### 6.5 Data Flow

1. Operator runs `personal_data record-reading electricity_consumption
   412.5 kWh`, or `personal_data import-csv electricity_consumption
   /path/to/readings.csv`, or (Section 10) the Scheduler periodically
   runs `scripts/collect_personal_data.py`.
2. Any path ends at `PersonalDataService.collect(source_id)` ->
   `PersonalDataManager.collect_from(source_id)` -> the registered
   `ElectricityCsvSource`/manual-entry source's `collect()` -> zero or
   more new `PersonalDataPoint`s -> `PersonalDataManager`'s existing
   consent gate + `store_if_new()` cycle -> `JsonlPersonalDataProvider`
   -> `data/database/personal_data/electricity_consumption.jsonl`.
3. A later EP (EP-095/096/098) or an operator calls
   `PersonalDataService.query("electricity_consumption", ...)` to read
   it back — entirely EP-092's existing, unmodified read path.

### 6.6 Future Real Acquisition Sources — Extension Contract

Per the revision task's explicit instruction, no vendor, API,
protocol, or meter model is selected here. Instead, the exact
extension contract a future provider must satisfy:

```text
EP-093 Core (category taxonomy + PersonalDataPoint mapping, Section 8)
    |
    +-- ElectricityCsvSource / manual entry (V1, this revision)
    |
    +-- Future provider "X" (TBD) -- any new PersonalDataSource
    |     subclass whose collect() produces electricity_consumption
    |     or gas_consumption PersonalDataPoints
    |
    +-- Future provider "Y" (TBD) -- likewise
```

A future provider is simply **one more concrete `PersonalDataSource`
subclass** (Section 6.2's Design A) — it does not require any change
to `PersonalDataManager`, `PersonalDataService`, `PersonalDataProvider`,
`PersonalDataPersistence`, the CLI module, or this design's core
architecture. It may be registered alongside or instead of the V1
manual/CSV source(s).

**Exact information required from the Owner before implementing a
real external provider** (none of which this document selects or
guesses):

- Which specific mechanism: a named smart-meter brand/model, a named
  utility company's API, a national/regional open-data feed, a local
  protocol (e.g. a P1/DSMR smart-meter port reader), or an existing
  monitoring system already in place.
- If a cloud API: its authentication mechanism (API key, OAuth,
  username/password) and rate limits.
- If a local protocol: the communication method (serial port, Modbus
  register map, local HTTP endpoint) and any required
  library/dependency.
- The data shape it actually returns (field names, units, granularity
  — per-reading, hourly, daily) so it can be correctly mapped onto
  `PersonalDataPoint` (Section 8).
- Polling/access cadence limits, if any (relevant to Section 10's
  Scheduler `interval_seconds`).

This document deliberately supplies no default answer to any of the
above — selecting one without Owner evidence would repeat the mistake
this revision was specifically asked to avoid.

### 6.7 Dependency Flow

Strictly: `personal_data_module.py` -> `PersonalDataService` (EP-092)
-> `PersonalDataManager` (EP-092) -> {`PersonalDataRegistry`,
`PersonalDataProvider`} (EP-092). EP-093's concrete source classes are
*registered with*, but never *depend on being called by*, anything
above `PersonalDataManager` — they are passive: `collect()` is called,
they never reach upward. No new dependency is introduced into
`src/core/personal_data/`'s existing files; EP-093's source classes
live in a new subpackage (Section 11) that depends *on* EP-092's
package, never the reverse.

---

## 7. Public Contracts

**`ElectricityMeterReadingSource`/`GasMeterReadingSource`**
(new, `src/core/personal_data/sources/`)

- Purpose: produce electricity/gas `PersonalDataPoint`s for
  `PersonalDataManager` to collect.
- Inputs: whatever the active acquisition mechanism (the V1 manual/CSV
  source, Section 6.4, or a future named provider, Section 6.6) needs, injected at
  construction (e.g. a CSV file path, or a small in-process log of
  operator-recorded readings) — never read from global state.
- Outputs: `list[PersonalDataPoint]`, per `PersonalDataSource`'s
  existing contract (empty list = nothing new; never mutates
  anything outside itself).
- Errors: may raise on a read/parse failure (e.g. malformed CSV row);
  `PersonalDataManager.collect_from()` already converts any such
  exception into `PersonalDataCollectionError` (EP-092, unchanged) —
  EP-093 introduces no new exception type for this.
- Invariants: `source_id` and `category` are fixed for the lifetime of
  the instance (matching the existing contract); `collect()` never
  returns a point whose `category` differs from the instance's own
  `category` property.
- Ownership: EP-093.
- Dependency restrictions: no import of `PersonalDataProvider`,
  `PersonalDataPersistence`, `PersonalDataRegistry`, or
  `CommandResult` (Section 11).

**`personal_data_module.py`'s `PersonalDataModule`** (new)

- Purpose: CLI command surface, `name = "personal_data"`.
- Inputs: `execute(action: str, arguments: list[str]) -> CommandResult`
  — identical signature to every existing `CommandModule`.
- Outputs: `CommandResult` for every action.
- Errors: unknown action returns `CommandResult(success=False, ...)`,
  matching every existing module's convention; never raises.
- Invariants: contains no logic beyond argument parsing and
  delegation — verifiable the same way EP-092's own
  `_test_manager_never_constructs_command_result`-style test verified
  its own layering (`EP092_DESIGN.md` audit precedent), by asserting
  `PersonalDataService` is the only object this module calls.
- Ownership: EP-093.
- Dependency restrictions: imports only `PersonalDataService` and
  `CommandResult`; never imports `PersonalDataManager`,
  `PersonalDataProvider`, or `PersonalDataPersistence` directly.

**`scripts/collect_personal_data.py`** (new, conditional on
Section 10)

- Purpose: a Scheduler-invokable entry point for automatic collection.
- Inputs: none via arguments (E13); reads its own list of
  source-ids/categories to collect from `Config`
  (`personal_data_electricity_gas.*`, Section 9) or a small hardcoded
  list if the Owner prefers not to add another config surface for
  this.
- Outputs: process exit code (0 on full success, non-zero if any
  source's collection failed), and log lines.
- Errors: a single source's `PersonalDataCollectionError` must not
  prevent the script from attempting every other configured source
  (mirrors `PersonalDataManager.collect_from()`'s own per-point
  failure isolation, `EP092_DESIGN.md` §16).
- Ownership: EP-093.
- Dependency restrictions: may construct its own `Config`/
  `PersonalDataService` (exactly as `PersonalDataService.__init__`
  already supports when no manager is injected); must not duplicate
  `PersonalDataService`'s internal wiring logic.

---

## 8. Data Model

EP-093 introduces **no new data structure** — it is a pure consumer
and producer of EP-092's existing `PersonalDataPoint`
(`src/core/personal_data/personal_data_record.py`, unchanged). Per
this document's own Section 4 conflict-analysis conclusion ("Option
A — proceed with constrained scope"), duplicating `PersonalDataPoint`
is explicitly not necessary and not proposed.

What EP-093 does define is the **category taxonomy** it is the sole
producer of:

| Category | Meaning | Typical `unit` | Owned by |
|---|---|---|---|
| `electricity_consumption` | A single electricity consumption reading/measurement | `"kWh"` | EP-093 |
| `gas_consumption` | A single gas consumption reading/measurement | `"m3"` (or the operator's local convention — EP-092 assigns no meaning to `unit` beyond "non-empty string," per `EP092_DESIGN.md` §12) | EP-093 |

- **Identity**: `PersonalDataPoint.id` — EP-093's source(s) must
  generate a stable, unique id per reading (e.g. derived from
  `source_id` + `timestamp`, or a simple incrementing counter
  persisted alongside the source's own state under the V1 manual/CSV
  mechanism, Section 6.4) —
  EP-092 places no constraint on `id`'s format beyond non-empty
  (`personal_data_record.py`'s `__post_init__`).
- **Uniqueness**: enforced entirely by EP-092's existing dedup key
  `(source_id, category, timestamp)` — EP-093 must ensure its
  source(s) use a `timestamp` that genuinely identifies the
  measurement (e.g. the meter-reading time, not "now") so that two
  distinct real-world readings are never accidentally deduplicated
  against each other, and the same reading re-imported twice (e.g. a
  CSV re-run) *is* correctly deduplicated.
- **Timestamps**: `timestamp` = when the reading was taken;
  `collected_at` = when Jarvis ingested it — EP-093 must respect this
  distinction exactly as EP-092 defines it (`EP092_DESIGN.md` §12),
  never conflating "now" into `timestamp` when a real reading time is
  available (e.g. from a CSV row's own date column).
- **Serialization/persistence semantics**: entirely EP-092's
  (`PersonalDataPoint.to_dict()`/`from_dict()`, JSONL) — EP-093 never
  serializes anything itself.
- **Compatibility expectations**: none broken; this is new data, not a
  migration of existing data.

---

## 9. Configuration

EP-093 must not add new keys to `personal_data:`'s existing schema
(`enabled`, `enabled_categories`, `storage_root` remain exactly as
EP-092 defined them, per Section 4's first conflict-analysis row). It
adds a **new, separate, additive top-level block**, following this
project's per-subsystem config convention (`memory:`, `knowledge:`,
`personal_data:`, each self-contained):

```yaml
personal_data_electricity_gas:
  # EP-093 Electricity & Gas Monitoring. Configures which concrete
  # PersonalDataSource(s) this EP registers with EP-092's
  # PersonalDataManager. Does not affect whether personal_data.* itself
  # is enabled, or which categories are allowed -- those remain
  # governed exclusively by the existing personal_data: block
  # (enabled_categories must separately include "electricity_consumption"
  # / "gas_consumption" for anything collected here to actually be
  # stored -- EP-092's consent gate, unchanged).
  enabled: false          # off by default; the operator opts in explicitly
  acquisition: "manual"   # V1, resolved (§6.2/§6.4): manual/CSV import.
                          # A future named vendor value may be added as a
                          # new option once the Owner supplies one (§6.6);
                          # no such value exists or is guessed today.
  # Manual/CSV-V1-specific keys (§6.4; only meaningful when acquisition: "manual"):
  csv_import_path: ""     # optional: a default CSV file path to import readings from
                          # (also settable per-call via "personal_data import-csv");
                          # empty means operator-entered readings only, via the
                          # "personal_data record-reading" CLI action.
```

- **Defaults**: `enabled: false` — electricity/gas collection is
  opt-in, consistent with `personal_data.enabled_categories` already
  defaulting to `[]` (opt-in, not opt-out, `EP092_DESIGN.md` §15).
- **Validation**: `PersonalDataService`'s existing defensive pattern
  for malformed config (`_enabled_categories()`'s `isinstance` check,
  `EP092_DESIGN.md`/`personal_data_service.py`, unchanged) should be
  mirrored by whatever EP-093 code reads this new block — STEP 2's
  responsibility, not invented here.
- **Enable/disable behavior**: if `personal_data_electricity_gas.
  enabled` is `false`, EP-093's `personal_data_module.py` actions that
  require a registered source return a failing `CommandResult`,
  matching `PersonalDataService`'s own `_ensure_enabled()` pattern
  conceptually (EP-093's module, not EP-092's service, performs this
  check for EP-093-owned actions).
- **Backward compatibility**: purely additive; no existing key is
  touched (verified against the actual current `config/config.yaml`,
  Section 2 E8).
- **Interaction with existing configuration**: the operator must set
  *both* `personal_data_electricity_gas.enabled: true` *and* add
  `"electricity_consumption"`/`"gas_consumption"` to `personal_data.
  enabled_categories` for data to actually persist — two independent,
  intentional opt-ins (EP-093's "is this feature on" and EP-092's "is
  this category allowed"), not a redundant duplicate control.

No configuration is introduced for a hypothetical future vendor
integration — a future provider (Section 6.6) is explicitly deferred,
matching "Do not introduce configuration merely for hypothetical
future use" (this task's own Design Principles, Section 5).

### 9.1 CLI Boundary (resolved)

Per the STEP 1 revision task's Section 9: the CLI stays entirely
inside the single, existing `personal_data` namespace (Section 6.3) —
**no** separate `electricity`/`gas`/`collect-electricity` namespaces or
verbs are introduced. Reasoning:

- Every existing subsystem in this repository has exactly one CLI
  namespace per service (`ltm`, `knowledge`, `memory`, …, E9) — a
  namespace per *domain category* within a service (electricity vs.
  gas vs., later, solar/weather) would be a new, unprecedented CLI
  pattern, and one that would need to be reinvented again for EP-094's
  solar and EP-097's weather categories.
- `collect <source_id>` (already defined by EP-092's own
  `PersonalDataService.collect()`) already fully covers "collect
  electricity"/"collect gas" — the *category* is intrinsic to which
  `source_id` is registered, not a separate verb.
- The two genuinely new actions this V1 needs — `record-reading` and
  `import-csv` — are still generic across category (both take
  `<category>` as an argument), so they extend the existing namespace
  without hard-coding "electricity"/"gas" into the command surface
  itself.
- Every action remains a thin, few-line delegation to
  `PersonalDataService`, with no branching business logic of its own —
  the CLI module does not become a second orchestration/service layer
  (this task's explicit constraint), exactly matching
  `long_term_memory_module.py`'s existing shape (E9).

---

## 10. Runtime / Lifecycle Behavior

- **Initialization**: EP-093's source(s) are constructed and
  registered with a `PersonalDataManager` at the same point
  `PersonalDataService`'s default manager is normally built, or
  earlier in `Bootstrap` if `personal_data_electricity_gas.enabled` is
  `true` — exact wiring point is a STEP 2 detail; the architectural
  rule is that registration happens once, at startup, not per-CLI-call
  (mirroring how other `*_module.py`/`*_service.py` pairs are wired in
  `Bootstrap`).
- **Normal execution**: an operator-triggered `personal_data collect
  <source_id>`, `record-reading`, or `import-csv` call (Section 6.4),
  or — if Section 9's automatic mode is enabled — a Scheduler tick
  running `scripts/collect_personal_data.py`.
- **Failure behavior**: a single source's collection failure
  (`PersonalDataCollectionError`, EP-092, unchanged) must not crash
  the CLI shell or (per Section 7) abort the multi-source runner
  script's attempt at every other configured source.
- **Shutdown**: no special behavior — `JsonlPersonalDataProvider`
  writes synchronously per point (EP-092, unchanged); there is no
  in-flight state to flush.
- **Repeated execution**: idempotent by construction — EP-092's
  `store_if_new()` dedup guarantee (audit finding EP092-AUDIT-002,
  fixed and verified, E6) means re-running collection for the same
  underlying reading never creates a duplicate record, provided
  EP-093's source(s) use a stable `timestamp` per real-world reading
  (Section 8).
- **Restart behavior**: relies entirely on EP-092's existing
  restart/dedup-index-rebuild behavior (`JsonlPersonalDataProvider.
  __init__`, unchanged) — EP-093 introduces no new persisted state of
  its own beyond what the V1 manual/CSV mechanism (Section 6.4) needs
  (e.g. "which CSV rows have already been imported" bookkeeping, a
  STEP 2 detail scoped entirely inside EP-093's own source class,
  never touching EP-092's storage).
- **Persistence/recovery**: entirely EP-092's (Section 8).
- **Concurrency assumptions**: `PersonalDataManager.collect_from()` is
  already safe against concurrent calls for the same source (EP-092,
  fixed under EP092-AUDIT-002); EP-093 must not introduce its own
  competing locking or assume single-threaded access beyond what
  EP-092 already guarantees.
- **Scheduler integration specifics** (this design's own
  recommendation, Section 6.2/9, is that this can be deferred past
  STEP 2's initial manual/CSV cut, but is fully specified here so it
  is not blocked when the Owner does want it):
  a `Job` is registered (via existing `SchedulerService`/CLI, e.g.
  `scheduler` CLI actions already implemented, unchanged) with
  `command = "scripts/collect_personal_data.py"` and
  `schedule = Schedule(type=ScheduleType.INTERVAL, interval_seconds=
  <operator-chosen>)`, exactly matching the `invoice_automation`/
  `fast_response_board` precedent's shape (E14), substituting
  `ScheduleType.INTERVAL` for their `MANUAL` since electricity/gas
  monitoring is meant to run unattended once configured.

---

## 11. Layering Rules

Explicit, to prevent STEP 2 from creating architectural leakage:

- **`personal_data_module.py` may import**: `PersonalDataService`,
  `CommandResult`. It may NOT import `PersonalDataManager`,
  `PersonalDataProvider`, `PersonalDataPersistence`,
  `PersonalDataRegistry`, or any EP-093 source class directly (source
  registration happens at startup/bootstrap time, not per CLI call).
- **EP-093's `PersonalDataSource` subclasses may import**:
  `PersonalDataPoint`, `PersonalDataSource` (both from EP-092's
  package, read-only consumption) and whatever the V1 manual/CSV
  mechanism (Section 6.4) needs (e.g. `csv`, `pathlib`). They may NOT import
  `PersonalDataManager`, `PersonalDataProvider`,
  `PersonalDataPersistence`, `PersonalDataRegistry`, `CommandResult`,
  `Config` directly for reading `personal_data.*` (only their own
  `personal_data_electricity_gas.*`, via values passed to their
  constructor — Dependency Policy, matching `PersonalDataSource`'s
  existing "injected at construction, not read from global state"
  rule, `EP092_DESIGN.md` §12).
- **`scripts/collect_personal_data.py` may import**: `Config`,
  `PersonalDataService` — nothing from `src/core/personal_data/`
  directly (it only ever calls through the service).
- **Persistence ownership**: exclusively `PersonalDataPersistence`/
  `JsonlPersonalDataProvider` (EP-092). EP-093 owns zero bytes of the
  `data/database/personal_data/*.jsonl` format or files beyond writing
  through `PersonalDataManager` like any other source.
- **Orchestration ownership**: exclusively `PersonalDataManager`
  (EP-092). EP-093 never re-implements the collect → consent-gate →
  dedupe → persist cycle.
- **Configuration ownership**: EP-093 owns only
  `personal_data_electricity_gas.*`; `personal_data.*` remains
  EP-092's.
- **External integration ownership**: exclusively inside EP-093's
  concrete `PersonalDataSource` subclass(es) — no network/file-import
  code anywhere else in EP-093's additions (not in the CLI module, not
  in the runner script beyond invoking `.collect()`).
- **No component outside `src/core/personal_data/sources/`
  (EP-093-owned) may import a specific acquisition mechanism's
  library** (e.g. `csv`) — keeping that concern isolated to the source
  class, matching `PersonalDataSource`'s existing "no dependency on
  Embedding/Retrieval/RAG/Semantic Search" style isolation
  (`EP092_DESIGN.md` §15) extended to "no dependency on a specific
  vendor's SDK leaking outside the one class that needs it."

---

## 12. Testing Strategy

`tests/EP093/__init__.py` + `tests/EP093/test_electricity_gas_
monitoring.py` (single file, one `TestRegistry`-registered `BaseTest`
subclass, `NAME = "EP093"` — following the universal convention, E17,
and the same convention EP-092's own STEP 3 audit ultimately accepted
as correct over its STEP 1 design's initial multi-file guess).

- **Unit**: `ElectricityMeterReadingSource`/`GasMeterReadingSource`
  construction and `collect()` behavior (empty when nothing new;
  correct `PersonalDataPoint` fields; correct `category`/`unit`) using
  real objects, no mocks, matching every EP-092/EP-069.x test's style.
- **Integration**: full `register_source()` -> `collect_from()` ->
  `query()` round trip through a real `PersonalDataManager` +
  `JsonlPersonalDataProvider` (temp directory), exactly mirroring
  `tests/EP092/`'s own integration test pattern.
- **Configuration tests**: `personal_data_electricity_gas.enabled:
  false` correctly prevents collection via the CLI module; malformed
  config is handled defensively, not crashing.
- **CLI module tests**: `personal_data_module.py`'s actions return the
  correct `CommandResult` for success/failure/unknown-action cases,
  and — mirroring EP-092's own architectural self-check pattern
  (`_test_manager_never_constructs_command_result`-style AST
  inspection) — assert the module's source never imports
  `PersonalDataManager`/`PersonalDataProvider`/
  `PersonalDataPersistence` directly.
- **Failure-path tests**: a source that raises during `collect()`
  results in a failing `CommandResult`, not a crash; under the V1
  manual/CSV mechanism (Section 6.4), a malformed CSV row is handled
  without aborting the whole import (if
  CSV import is implemented in STEP 2).
- **Regression tests**: re-run `tests/EP092`'s suite unmodified as
  part of STEP 2's verification (not new tests, but a required check)
  to confirm EP-093 introduced no regression in the framework it
  consumes.
- **Backward-compatibility tests**: not applicable in the sense of
  "existing EP-093 behavior" (none exists yet); applicable in the
  sense that `config/config.yaml`'s pre-existing keys/tests must
  remain passing.

Not prescribed (out of EP-093's ownership, per Section 15): tests for
visualization, forecasting, or recommendation behavior — those belong
to EP-095/096/098 respectively.

---

## 13. Documentation Impact

STEP 2 will need to update, at finalization (STEP 4, not STEP 1 or
STEP 2 per this project's established EP-052/EP-092 convention of
documentation-only updates at finalization):

- `CHANGELOG.md`, `docs/BACKLOG.md` (EP-093's entry gains an
  implementation note), `docs/RELEASE_NOTES.md`,
  `docs/architecture/JARVIS_ROADMAP.md` (if its "planning only" phase
  marker for Phase E should be updated once EP-093 is implemented —
  an Owner Decision at STEP 4 time, not this document's to make).
- `.env.example` — only if a future named vendor/API (Section 6.6) is
  chosen later and needs a credential placeholder; not needed for the
  V1 manual/CSV mechanism (Section 6.4), which requires no credentials.

This STEP 1 document itself is the only documentation created now,
per this task's own instruction not to modify documentation beyond
recording the design.

---

## 14. Migration / Compatibility

**None required.** EP-093 introduces no change to any existing
behavior, API, configuration key, persisted data format, or test.
Verified against the actual current repository state (Section 2):

- No existing `config/config.yaml` key is renamed, removed, or
  repurposed (Section 9 is purely additive).
- No existing `src/core/personal_data/` file is modified (Section 11).
- No existing CLI command's behavior changes (a new `personal_data`
  namespace is additive, exactly as `personal_data:` itself was
  additive to `config.yaml` in EP-092).
- No existing test is modified.
- No existing persisted data exists yet for `electricity_consumption`/
  `gas_consumption` to migrate.

---

## 15. Deferred / Out of Scope

EP-093 MUST NOT implement:

- Solar generation collection (EP-094).
- Energy visualization, charting, or reporting (EP-095).
- Forecasting, trend analysis, or anomaly detection (EP-096).
- Weather data collection (EP-097).
- Any recommendation logic (EP-098).
- A specific named vendor/utility API integration (a future provider,
  Section 6.6) — explicitly deferred pending an Owner Decision naming
  one; not required to unblock STEP 2 (Section 6.2).
- A generic, configuration-driven HTTP polling adapter — explicitly
  rejected as speculative infrastructure without a real consumer
  (Section 6.2's Design A vs. B analysis; this was "Option C" in this
  design's first draft).
- Electricity production, import/export (net-metering), or any
  solar-adjacent measurement — per `docs/BACKLOG.md`'s Phase E list,
  generation belongs to EP-094 ("Solar Generation Analytics"), not
  EP-093 ("Electricity & Gas Monitoring," i.e. consumption). EP-093's
  V1 scope (Section 8, Section 10 of the revision task) is
  consumption-only for both `electricity_consumption` and
  `gas_consumption`.
- Any change to `PersonalDataPoint`, `PersonalDataSource`,
  `PersonalDataProvider`, `PersonalDataPersistence`,
  `PersonalDataRegistry`, `PersonalDataManager`, or `PersonalDataService`
  (EP-092, closed and audited PASS — Section 2 E6).
- Any change to `Scheduler`, `Job`, `ExecutionEngine`, or any
  `Executor` (EP-011) — EP-093 uses this infrastructure exactly as it
  exists (Section 4/6.2's conflict resolution).
- Multi-tenant / multi-household support — this project is
  single-operator throughout (consistent with every existing
  subsystem, `EP092_DESIGN.md` §11).
- Retention/archival policy for `electricity_consumption`/
  `gas_consumption` data — inherited, unresolved, deferred risk
  already documented by EP-092's own audit (`EP092_ARCHITECTURE_AUDIT.md`
  §9's retention note); not EP-093's to solve.

---

## 16. STEP 2 Implementation Contract

**Implement:**

1. `src/core/personal_data/sources/__init__.py`,
   `electricity_source.py`, `gas_source.py` — concrete
   `PersonalDataSource` subclasses per Section 6.3/6.4/8, implementing
   the now-resolved V1: manual entry + CSV import, no separate
   acquisition-provider abstraction (Section 6.2's Design A).
2. `src/modules/personal_data_module.py` — CLI module per Section
   6.3/7/9.1, following `long_term_memory_module.py`'s exact pattern.
3. Wiring in `Bootstrap` (or wherever other `*_module.py`/
   `*_service.py` pairs are constructed and registered — inspect that
   exact site fresh in STEP 2, do not assume; this document does not
   claim to have located the precise `Bootstrap` line, only the
   pattern to follow) to construct and register
   `PersonalDataModule`/EP-093's source(s) at startup when
   `personal_data_electricity_gas.enabled` is `true`.
4. The `personal_data_electricity_gas:` config block (Section 9),
   additive to `config/config.yaml`.
5. `tests/EP093/__init__.py` + `tests/EP093/test_electricity_gas_
   monitoring.py` per Section 12.
6. `scripts/collect_personal_data.py` and its `Job` registration —
   only if the Owner confirms automatic collection is wanted in this
   same STEP 2 pass; otherwise defer to a fast-follow (this design's
   V1 does not require it — manual/CSV entry via the CLI is a
   complete, working v1 on its own).

**Do NOT implement:** anything listed in Section 15.

**Existing abstractions that MUST be reused, not duplicated:**
`PersonalDataPoint`, `PersonalDataSource` (the contract, not a new
one), `PersonalDataManager`, `PersonalDataRegistry`,
`PersonalDataProvider`/`JsonlPersonalDataProvider`,
`PersonalDataPersistence`, `PersonalDataService`, `CommandResult`,
`Config`, `BaseTest`/`TestRegistry`/`TestRunner`, and — if Section 10's
automatic mode is built — `Scheduler`/`Job`/`Schedule`/
`ScheduleType.INTERVAL`/`PythonExecutor` exactly as they exist today.

**Files expected to change:** exactly the files listed in "Implement"
above, plus the additive `config/config.yaml` block, plus (per this
project's established test-discovery convention, `EP092_DESIGN.md`'s
own STEP 2 precedent) one added import line in `src/modules/
test_module.py` to register `tests.EP093...` with `TestRegistry`.

**Tests that MUST be added:** per Section 12, in full.

**Behavior that MUST remain unchanged:** every EP-092 file, every
existing `config/config.yaml` key, every existing test, every existing
CLI command, `Scheduler`/`ExecutionEngine`/any `Executor` — verified
via full regression (`tests/EP092` re-run) as part of STEP 2's own
verification, not merely assumed.

---

## 17. Final Architectural Verdict

`READY FOR OWNER REVIEW`

**Revised from the original draft's `BLOCKED — OWNER DECISION
REQUIRED`.** The original blocker was "which electricity/gas
data-acquisition mechanism EP-093 implements first." This revision
resolves it: manual/CSV import (Section 6.4) is adopted as EP-093's
explicitly-scoped V1, using EP-092's existing `PersonalDataSource`
contract directly with no new acquisition-provider abstraction
(Section 6.2's Design A vs. B analysis) — nothing about specifying V1
required knowing a future real vendor. A future named vendor/API
(Section 6.6) remains genuinely unspecified and is explicitly
deferred, with its exact information requirements documented, but its
absence no longer blocks STEP 2, per this revision task's own explicit
instruction: *"If the only missing information is the real future
vendor/meter/API, that alone should NOT necessarily block the
architecture if a clean provider boundary allows a manual/CSV first
provider."*

No other aspect of this design is blocked: the EP-092 boundary is
clean (Section 4/5), the Scheduler-integration concern that could have
been a second blocking issue is resolved using only existing
infrastructure (Section 4/6.2/10, evidence E10-E14), and no roadmap
inconsistency was found (Section 4's last row). See the "STEP 1
Revision Summary" below for the complete, consolidated resolution.

---

## Owner Decision Summary

1. **EP-093 purpose**: implement Jarvis's first real personal-data
   source — electricity and gas consumption tracking — as a concrete
   `PersonalDataSource` (or two) plugged into EP-092's already-built,
   already-audited-PASS Personal Data Collection Framework, plus the
   CLI command surface (`personal_data_module.py`) that framework has
   lacked since EP-092 shipped.
2. **Key architectural decision**: EP-093 introduces no new
   registry/manager/provider/persistence — it is a pure consumer of
   EP-092's abstractions, adding only (a) concrete source class(es),
   (b) the missing CLI module, and (c) — if automatic collection is
   wanted — a single multi-source runner script invoked by a Scheduler
   `Job`, since `Job.command` can only launch external
   programs/files/URLs with no arguments (confirmed by direct
   inspection of `Scheduler`/`ExecutionEngine`/`PythonExecutor`, not
   assumed).
3. **Relationship with EP-092**: strictly downstream/consumer. EP-092
   is a hard dependency; nothing in EP-093's proposed design modifies
   any EP-092 file, contract, or configuration key.
4. **Conflicts found**: one real, previously-undocumented gap between
   EP-092's STEP 1 design's informal Scheduler-integration assumption
   and the Scheduler's actual, documented contract — resolved here
   using only existing infrastructure, no fix to EP-092 or EP-011
   required. No unresolved conflict with EP-094/095/096/097/098/069.x,
   and no roadmap/backlog inconsistency.
5. **Dependencies**: hard dependency on EP-092 (implemented, audited
   PASS). Soft/optional dependency on EP-011 Scheduler, only if
   automatic collection is enabled. No dependency on any unimplemented
   EP.
6. **Whether STEP 2 can safely begin**: **yes, immediately** — this
   revision adopts manual/CSV import (Section 6.4) as EP-093's scoped
   V1, with no separate acquisition-provider abstraction (Section
   6.2), and automatic Scheduler collection deferred to a fast-follow
   (fully specified in Section 10 for when it is wanted). A named
   vendor/API integration (Section 6.6) remains an open, non-blocking
   future decision — STEP 2 does not need it to start.

---

## STEP 1 Revision Summary

1. **Original blocker**: which electricity/gas data-acquisition
   mechanism EP-093 should implement — no vendor, protocol, or API is
   named anywhere in the repository, and inventing one would violate
   `AI_GENERATION_STANDARD.md`'s Unknown API Policy (Section 2, E15).

2. **Investigation performed**: re-verified all prior evidence
   (Section 2) fresh, then specifically evaluated whether EP-093 needs
   its own acquisition-provider abstraction sitting between a concrete
   source and EP-092's `PersonalDataSource` contract (Section 6.2),
   whether manual/CSV import can be fully specified without knowing a
   future vendor (Section 6.4), what exact information a future real
   provider would require from the Owner (Section 6.6), whether the
   CLI should gain per-domain verbs or stay generic (Section 9.1), and
   whether electricity should carry consumption-only or also
   production/import/export semantics now (Section 15, resolved
   against `docs/BACKLOG.md`'s Phase E list: production belongs to
   EP-094 Solar).

3. **Decision between Design A and Design B**: **Design A** — no new
   acquisition-provider abstraction. `PersonalDataSource` (EP-092)
   already is the correctly-scoped extension point; each acquisition
   mechanism (manual/CSV today, a named vendor later) is simply its
   own concrete `PersonalDataSource` subclass. A separate
   `AcquisitionProvider` interface (Design B) would duplicate
   `PersonalDataSource`'s own responsibility for no current benefit,
   and was rejected as speculative infrastructure built for a second
   implementation that does not yet exist (Section 6.2's full
   comparison table).

4. **Exact EP-092 / EP-093 boundary** (Section 5, unchanged from the
   original draft, re-confirmed here): EP-092 owns
   `PersonalDataPoint`, `PersonalDataSource`'s contract shape,
   `PersonalDataRegistry`, `PersonalDataManager` (including the
   consent gate and atomic `store_if_new()` dedup), `PersonalDataProvider`
   /`JsonlPersonalDataProvider`/`PersonalDataPersistence`,
   `PersonalDataService`, and the `personal_data:` config block's
   existing keys. EP-093 owns its concrete `PersonalDataSource`
   subclass(es), the `electricity_consumption`/`gas_consumption`
   category names, the new `personal_data_module.py` CLI surface, the
   `personal_data_electricity_gas:` config block, and (if enabled) the
   Scheduler runner script. Future acquisition integrations
   (Section 6.6) own only their own concrete `PersonalDataSource`
   subclass and whatever library/credentials they individually need —
   nothing above `PersonalDataManager` changes for any of them.

5. **V1 acquisition mechanism**: manual entry (`personal_data
   record-reading <category> <value> <unit> [timestamp]`) and CSV
   import (`personal_data import-csv <category> <path>`), using a
   simple, EP-093-owned canonical CSV format (`date,value,unit,
   meter_id`) — not any utility-specific export format (Section 6.4
   defines required/optional fields, units, timestamp semantics,
   validation, duplicate/invalid-row/missing-data handling,
   conversion rules, normalization, and error reporting in full).

6. **Future-provider extension strategy**: a future real acquisition
   source is simply one more concrete `PersonalDataSource` subclass
   (Section 6.6), requiring no change to `PersonalDataManager`,
   `PersonalDataService`, the CLI module, or this design's core
   architecture. The exact information the Owner would need to supply
   before one can be implemented is listed explicitly (mechanism,
   authentication, protocol, data shape, cadence) — none of it is
   guessed or defaulted.

7. **Scheduler integration**: kept exactly as the original
   investigation found it and re-verified unchanged here — `Job.command`
   only launches external programs/files/URLs with no arguments
   (Section 2, E10-E14). The smallest architecture-compatible solution
   remains a single standalone `scripts/collect_personal_data.py` that
   iterates every configured source and calls
   `PersonalDataService.collect(source_id)` for each, registered as a
   `Job` exactly like the `invoice_automation`/`fast_response_board`
   precedent (Section 6.3/10). It owns only "loop over configured
   sources and call `.collect()`"; it must not own any business logic,
   CSV parsing, or normalization (all of which live inside the source
   classes themselves). Deferred past STEP 2's initial cut — a fully
   valid v1 requires only the CLI actions, not automatic scheduling.

8. **CLI responsibility**: stays entirely inside the single, existing
   `personal_data` namespace (Section 9.1) — no `electricity`/`gas`
   -specific namespaces or verbs. `collect <source_id>` already covers
   "collect electricity"/"collect gas" via which source is registered;
   `record-reading`/`import-csv` take `<category>` as a parameter
   rather than being split into per-domain commands. Every action
   remains a thin delegation to `PersonalDataService`, never a second
   orchestration layer.

9. **Deferred functionality** (Section 15, revised): solar (EP-094),
   visualization/reporting (EP-095), forecasting/anomaly detection
   (EP-096), weather (EP-097), recommendations (EP-098); a named
   vendor/API integration and a generic HTTP polling adapter (both
   Section 6.2/6.6); electricity production/import/export
   (net-metering — belongs to EP-094 per the roadmap, not EP-093);
   any change to EP-092 or EP-011 files; multi-tenant support;
   retention/archival policy (inherited, already-documented EP-092
   risk).

10. **Remaining Owner decisions, if any**: only the identity of a
    future real acquisition provider (Section 6.6) — explicitly
    non-blocking, per this revision's own resolution. The Owner may
    also confirm or override the choice to defer automatic Scheduler
    collection past the initial STEP 2 cut (Section 6.2/10), but the
    design is fully specified either way and does not require that
    confirmation to proceed.

11. **Final architectural verdict**: `READY FOR OWNER REVIEW`
    (revised from the original draft's `BLOCKED — OWNER DECISION
    REQUIRED`).
