# EP-094 — STEP 1: Architecture Discovery & Design

## Solar Generation Analytics

## 0. Status

`DESIGN PROPOSED — awaiting Owner Decision`

---

## 0.1 Source-of-Truth Note

No GitHub connector is available in this session. Consistent with the
established pattern for this project (`EP092_DESIGN.md` §0,
`EP093_DESIGN.md` §0.1), the repository state already present in this
session (`/home/claude/jarvis/jarvis-main`) was used as the current
repository state, verified fresh for this task by direct `grep`/`view`
against the actual files — including re-reading EP-092's and EP-093's
design/audit documents fresh rather than relying on conversation
memory of writing them.

---

## 1. Scope Verification (Purpose)

**What EP-094 is**, per direct evidence:

- `docs/BACKLOG.md` line 3131: **"EP-094 — Solar Generation Analytics"**
  (MEDIUM priority), immediately after EP-093 in "Phase E — Personal
  Intelligence / Energy / Weather."
- `EP092_DESIGN.md` §11 ("FUTURE INTEGRATION"), already approved and
  implemented: *"EP-093 (Electricity & Gas), EP-094 (Solar) each add
  one `PersonalDataSource` implementation plus their own Scheduler
  Job."* This is the pre-existing, already-accepted architectural
  contract for what EP-094 does — not a new interpretation.
- `EP093_DESIGN.md` (multiple places, e.g. §4, §15), already approved
  and implemented: electricity production/import/export
  ("net-metering") was explicitly excluded from EP-093 on the grounds
  that it *"belongs to EP-094 per the roadmap."*

**Title vs. actual scope (an evidence-based observation, not a
guess):** EP-094's title contains the word "Analytics," which could
suggest trend analysis or forecasting. Direct evidence rules this out:
`docs/BACKLOG.md`'s own Phase E list separately names **EP-096 —
Energy Forecast & Anomaly Detection** and **EP-095 — Energy
Visualization & Reporting** as the EPs that own trend analysis and
visualization respectively. Combined with EP-092 §11's explicit "adds
one `PersonalDataSource`" framing, EP-094's real, current-phase-
appropriate scope is **acquisition** of solar generation data — the
same interpretation gap already resolved identically for EP-093
(titled "Monitoring," also pure acquisition). This mirrors, rather
than invents, the resolution EP-093's own STEP 1/STEP 1-revision
process already established for the identical ambiguity.

**Exact architectural responsibility:** implement one (or more)
concrete `PersonalDataSource` subclass(es) producing solar-generation
`PersonalDataPoint`s, make solar-generation acquisition operable
end-to-end (CLI, configuration, optional Scheduler), and define the
`solar_generation` category — nothing more.

**What EP-094 is not:**

- Not visualization/reporting (EP-095), forecasting/anomaly detection
  (EP-096), weather (EP-097), or recommendations (EP-098).
- Not a second acquisition framework, not a second CLI, not a second
  persistence layer — EP-092's framework and EP-093's already-built
  `personal_data` CLI namespace are reused, not duplicated (Section 4,
  Section 5).
- Not a specific named inverter/vendor/protocol integration (Section
  3, mirroring EP-093's already-established Unknown API Policy
  constraint — no solar vendor, model, or protocol is named anywhere
  in this repository, confirmed by repository-wide search).
- Not net-metering / grid import-export accounting (Section 6C
  Non-Goals) — no repository evidence currently specifies its data
  shape (single value? separate import/export readings? a running
  balance?), and inventing one would repeat the exact mistake EP-093's
  Unknown-API constraint exists to prevent.

---

## 2. Repository Investigation (Evidence)

| # | Evidence | Finding |
|---|---|---|
| E1 | `docs/BACKLOG.md` line 3131 | EP-094's title and priority are the *only* backlog specification; no acquisition-mechanism, vendor, or unit detail given. |
| E2 | `docs/architecture/JARVIS_ROADMAP.md` "Phase E" (~line 2420) | EP-094 sits in the same "planning only" phase grouping as EP-092/093; no EP-094-specific detail beyond the phase list already known from EP-092/093's own designs. |
| E3 | `docs/architecture/designs/` and `docs/architecture/audits/` directory listings | No `EP094_DESIGN.md` or `EP094_*AUDIT*.md` exists yet — confirmed by direct listing. |
| E4 | Repository-wide `grep -rniE "solar\|inverter\|\bpv\b\|photovoltaic"` | Zero hits for any concrete vendor/model/protocol. Every existing hit is either EP-092/EP-093's own design/audit prose (already-known context) or `tests/EP092/`'s own generic `"solar"` category-name fixture data (illustrative test data, not a real integration). |
| E5 | `docs/architecture/designs/EP092_DESIGN.md` (full, re-read fresh) | §11 explicitly assigns EP-094 "one `PersonalDataSource`"; the `PersonalDataPoint`/`PersonalDataSource`/`PersonalDataManager`/`PersonalDataProvider`/`PersonalDataPersistence`/`PersonalDataRegistry`/`PersonalDataService` stack is the exact, unmodified extension point EP-094 must use. |
| E6 | `docs/architecture/designs/EP093_DESIGN.md` (full, re-read fresh) | Establishes the concrete precedent EP-094 should follow almost exactly: Design A (no `AcquisitionProvider`), manual+CSV V1, the shared `personal_data` CLI namespace ("generic across category," §9.1, explicitly written to also serve EP-094/097), Scheduler-integration deferral, and the exact `date,value,unit,meter_id` canonical CSV shape. |
| E7 | `docs/architecture/audits/EP092_ARCHITECTURE_AUDIT.md` §18 (re-read fresh) | EP-092 final verdict: PASS. Stable foundation; no open finding. |
| E8 | EP-093 STEP 3/3.1 audit history (this conversation's own record, cross-checked against the actual current source) | EP093-AUDIT-001 (non-finite value acceptance) was a real, proven defect in `_parse_value()`, fixed via `math.isfinite()`. This is a concrete, already-learned lesson directly reusable for EP-094's own value parsing (Section 5F) — not a "fix" of EP-093, a design input for new code. |
| E9 | `src/core/personal_data/sources/electricity_source.py`, `gas_source.py` (actual source, re-read fresh) | Confirms the exact, already-proven-correct pattern: one module per category, module-level `CATEGORY`/`SOURCE_ID`/`DEFAULT_LOG_PATH` constants, `_parse_value`/`_parse_timestamp`/`_make_id`/`_build_point`/`_append_to_log` helpers, `append_<x>_reading()`/`import_<x>_csv()` free functions, and a thin `<X>CsvSource(PersonalDataSource)` class whose `collect()` re-reads the whole local log every call. |
| E10 | `src/modules/personal_data_module.py` (actual source, re-read fresh) | The `personal_data` CLI namespace already exists (built by EP-093) with a `_CATEGORY_HANDLERS: dict[str, tuple[str, Callable, Callable]]` dispatch table and a **single** `electricity_gas_enabled: bool` constructor parameter gating `record-reading`/`import-csv`. Extending this table for a third category is straightforward; the single boolean flag is not sufficient for a *second, independently-toggleable* domain group (Section 4, Section 6). |
| E11 | `config/config.yaml` `personal_data_electricity_gas:` block (actual, re-read fresh) | Confirms the exact, already-established per-domain-group config shape (`enabled`, `acquisition`, `csv_import_path`) EP-094 should mirror under its own top-level key. |
| E12 | `src/bootstrap.py` (actual source, re-read fresh, the exact block EP-093 added) | Confirms the exact wiring pattern: `PersonalDataService` construction is unconditional (already done, EP-094 does not repeat it); a domain-group's sources are registered conditionally on that domain's own config flag; the CLI module is registered once, unconditionally. |
| E13 | `tests/EP093/test_electricity_gas_monitoring.py` (actual, re-read fresh) | Confirms the `tests/EP0##/` one-file convention and the specific regression patterns (non-finite rejection, all-invalid/mixed CSV success semantics, CRLF/BOM) that a new solar suite should replicate for its own category. |
| E14 | `AI_GENERATION_STANDARD.md` "Unknown API Policy" (re-read fresh) | Directly applicable, unchanged: no solar vendor/inverter/protocol may be invented; EP-094 must define only the acquisition-agnostic contract and a manual/CSV V1, exactly as EP-093 did. |
| E15 | `src/core/scheduler/`, `src/core/execution/` (unchanged since EP-093's investigation, spot-checked, not re-litigated in full) | The `Job.command`-launches-external-programs-only constraint EP-093 discovered and resolved (a standalone runner script, never implemented, deferred) applies identically and is not re-derived here — see Section 4/8. |

---

## 3. Dependency Analysis

**Direct dependencies:**

- `src/core/personal_data/` (EP-092) — `PersonalDataSource`,
  `PersonalDataPoint`, `PersonalDataManager` (via `PersonalDataService`).
- `src/services/personal_data_service.py` (EP-092) — unchanged,
  reused exactly as EP-093 uses it (`register_source`, `collect`,
  `query`, `status`).
- `src/modules/personal_data_module.py` (EP-093-built, but per
  `EP093_DESIGN.md` §9.1 explicitly intended as the **shared**
  `personal_data` CLI namespace for EP-093/094/097, not EP-093's
  exclusive property) — extended, not duplicated (Section 6).
- `src/bootstrap.py` — extended with one more domain-group wiring
  block, mirroring EP-093's own.
- `src/core/config.py` (`Config`) — EP-094's own new configuration
  section.
- `src/core/command_router.py` (`CommandResult`).
- `src/testing/` (`BaseTest`/`TestRegistry`/`TestRunner`).

**Indirect dependencies (via EP-092, never touched directly):**
`PersonalDataProvider`/`JsonlPersonalDataProvider`/
`PersonalDataPersistence`/`PersonalDataRegistry` — EP-094 never
imports these, exactly as EP-093 does not (§11 layering rule,
replicated in Section 6 below).

**What must NOT depend on EP-094:** EP-092 (must remain fully
ignorant of EP-094, as it already is of EP-093); EP-093 (structurally
parallel, not a dependency in either direction — confirmed by
`EP093_DESIGN.md`'s own Conflict Analysis, which found "no conflict"
between EP-093 and EP-094 because neither depends on the other, only
both on EP-092); EP-011 Scheduler (used, never modified, matching
EP-093's precedent).

**Should EP-094 extend an existing abstraction or introduce a new
one?** Extend. `PersonalDataSource` is already the correct, proven
abstraction (Section 4 confirms no drift risk). No new abstraction is
introduced.

---

## 4. Architectural Drift Check

| Risk | Assessment |
|---|---|
| Duplicated functionality / duplicate persistence | None — EP-094 reuses `PersonalDataManager`/`JsonlPersonalDataProvider` exactly as EP-093 does; its own local log (Section 5) is the same *pattern* EP-093 already established (a per-category local staging log outside EP-092's storage root), not a second instance of EP-092's persistence layer. |
| Circular dependencies | None — dependency direction is strictly `solar_source.py` → EP-092's `PersonalDataSource`/`PersonalDataPoint` only; `personal_data_module.py` → `PersonalDataService` + the new `append_solar_reading`/`import_solar_csv` functions (never the source class itself, replicating EP-093's own layering rule, Section 6). |
| CLI-to-core coupling / bypassing services | None new — the CLI still only reaches EP-092 through `PersonalDataService`. |
| Accidental dependency on EP-092/EP-093 internals | None — only public, already-exported symbols are used (`PersonalDataSource`, `PersonalDataPoint`, `PersonalDataService`'s public methods, and the two already-public free functions per category EP-093 established as the intended per-category extension shape). |
| Scheduler coupling where not required | Avoided — Scheduler integration is deferred (Section 8), exactly as EP-093 deferred it; manual/CLI-triggered acquisition is a complete, working V1 on its own. |
| Unnecessary new configuration | Avoided — one new, additive top-level block (`personal_data_solar:`), mirroring the existing `personal_data_electricity_gas:` shape; no speculative keys. |
| Unnecessary new abstraction | Avoided (Section 3's Design A confirmation). |
| Breaking changes to existing public APIs | **One real, necessary, and disclosed exception** — see below. |

**The one genuine drift risk, and why it is required, not optional:**
`PersonalDataModule.__init__`'s current signature,
`electricity_gas_enabled: bool = False` (E10), gates *both*
electricity and gas together under one flag, because EP-093 only ever
needed one domain group. EP-094 introduces a *second*,
independently-toggleable domain group (solar), which a single boolean
cannot represent. Leaving the signature as-is and adding a second,
differently-named boolean parameter (`solar_enabled: bool = False`)
would work today but does not scale — EP-097 (Weather) would need a
third, and so on, hard-coding an ever-growing parameter list into the
CLI module's constructor. The smallest change that avoids repeating
this problem for every future category-owning EP is to generalize the
single boolean into a **per-category-enabled mapping**
(`enabled_categories: frozenset[str] | None = None`, defaulting to
"all categories in `_CATEGORY_HANDLERS` disabled" when omitted, or an
explicit set of category names whose `record-reading`/`import-csv`
actions are allowed) — a signature change to an EP-093-built file,
disclosed here explicitly rather than silently introduced in STEP 2.
This is the only public-API change this design proposes, and it is
backward-compatible in spirit (Bootstrap, the only caller, is updated
in the same STEP 2 pass — Section 9).

---

## 5. Architecture

### 5A. Components

**`SolarCsvSource`** (`src/core/personal_data/sources/solar_source.py`
— new file, peer to `electricity_source.py`/`gas_source.py`)

- `CATEGORY = "solar_generation"`, `SOURCE_ID = "solar_local_entry"`,
  `DEFAULT_LOG_PATH = Path("data/database/personal_data_solar") /
  "solar_generation.jsonl"` — a **separate top-level data directory**
  from `personal_data_electricity_gas/` (Section 5C), not shared,
  matching the existing per-domain-group isolation pattern.
- Implements `PersonalDataSource` directly — no new abstraction.
- `collect()` re-reads the entire local log every call (identical
  pattern to `ElectricityCsvSource`/`GasCsvSource`; the AUDIT-005
  scalability observation is inherited as the *same*, already-accepted
  pattern, not a new or worse instance of it — no remediation proposed
  here, per this task's explicit instruction not to fold deferred
  EP-093 observations into EP-094 unless required).
- `append_solar_reading(value, unit, timestamp=None, log_path=None)`
  and `import_solar_csv(path, log_path=None) -> tuple[int, list[str]]`
  — free module-level functions, not source-class methods, for the
  identical layering reason `EP093_DESIGN.md` §11 established
  (`personal_data_module.py` must not import the source class).
- `SolarMeterReadingError` (naming choice: see Section 5F) — the
  module's own unrecoverable-failure exception, mirroring
  `ElectricityMeterReadingError`/`GasMeterReadingError` exactly.

**`personal_data_module.py`** (MODIFY, not create)

- `_CATEGORY_HANDLERS` gains one entry:
  `"solar_generation": (SOLAR_SOURCE_ID, append_solar_reading, import_solar_csv)`.
- `HELP_TEXT` is unchanged in shape (still category-generic — no new
  verb is added, per EP-093's already-established CLI-boundary
  decision, Section 6).
- Constructor signature changes per Section 4's disclosed exception.

**`src/bootstrap.py`** (MODIFY, not create)

- One more domain-group wiring block, structurally identical to
  EP-093's: construct `SolarCsvSource()`, register it with the
  already-unconditionally-constructed `personal_data_service` when
  `personal_data_solar.enabled` is true; update the `PersonalDataModule(...)`
  call site for the new constructor signature (Section 4).

### 5B. Dependency / Data Flow

```text
personal_data record-reading solar_generation 4.2 kWh
        |
personal_data_module.py::_record_reading()
        | (category "solar_generation" -> _CATEGORY_HANDLERS lookup)
solar_source.py::append_solar_reading()  -- validates, appends to local log
        |
personal_data_module.py::_collect_after_append()
        |
PersonalDataService.collect("solar_local_entry")   [EP-092, unchanged]
        |
PersonalDataManager.collect_from(...)              [EP-092, unchanged]
        | (consent gate: "solar_generation" in personal_data.enabled_categories?)
        | (store_if_new(), atomic dedup)            [EP-092, unchanged]
JsonlPersonalDataProvider                           [EP-092, unchanged]
        v
data/database/personal_data/solar_generation.jsonl  [EP-092's storage, unchanged]
```

Identical shape to EP-093's already-audited-PASS data flow, substituting the one new category.

### 5C. Storage boundary (explicit, per this task's drift-check requirement)

Two separate concepts, exactly as EP-093 established:

1. EP-094's own local staging log:
   `data/database/personal_data_solar/solar_generation.jsonl` — owned
   entirely by `solar_source.py`, written by
   `append_solar_reading()`/`import_solar_csv()`, read by
   `SolarCsvSource.collect()`.
2. EP-092's actual persisted storage:
   `data/database/personal_data/solar_generation.jsonl` — owned
   entirely by `JsonlPersonalDataProvider`, reached only through
   `PersonalDataManager`/`store_if_new()`.

These must never be the same path or directory (mirrors the
already-audited-correct EP-093 separation, `EP093_ARCHITECTURE_AUDIT`
Section 8 equivalent verification during EP-093's own audit).

---

## 6. Public Interfaces / Contracts

Identical shape to `EP093_DESIGN.md` §7, substituting solar:

- `SolarCsvSource`: purpose, inputs, outputs, errors, invariants,
  ownership, dependency restrictions — all identical in kind to
  `ElectricityCsvSource`'s own contract (§7 of `EP093_DESIGN.md`), not
  reproduced verbatim here to avoid drift between two copies of the
  same explanation (the same reasoning `gas_source.py`'s own
  docstring already gives for not repeating `electricity_source.py`'s
  rationale).
- `personal_data_module.py`'s layering rule (`EP093_DESIGN.md` §11)
  is unchanged in kind: may import `PersonalDataService`,
  `CommandResult`, and the plain `SOURCE_ID` constants /
  `append_*_reading()` / `import_*_csv()` functions and their error
  classes for **every** registered category — never
  `PersonalDataManager`/`PersonalDataProvider`/
  `PersonalDataPersistence`/`PersonalDataRegistry`, never a
  `PersonalDataSource` subclass itself. EP-094 extends this rule's
  *application* (one more category), not its *content*.
- **CLI boundary (re-confirmed, not re-decided):** no `solar`-specific
  verb is introduced. `record-reading solar_generation ...` and
  `import-csv solar_generation ...` reuse the exact existing actions,
  exactly as `EP093_DESIGN.md` §9.1 already anticipated when it wrote
  "no separate `electricity`/`gas`/`collect-electricity` namespaces or
  verbs" with EP-094/097 explicitly in mind.

---

## 7. Data Model

No new data structure — `PersonalDataPoint` (EP-092) is reused
unmodified, exactly as EP-093 established (`EP093_DESIGN.md` §8's own
"EP-093 introduces no new data structure" conclusion applies
identically here).

New category:

| Category | Meaning | Typical `unit` | Owned by |
|---|---|---|---|
| `solar_generation` | A single solar-generation reading/measurement | `"kWh"` | EP-094 |

- **Identity/uniqueness**: identical mechanism to EP-093 — dedup key
  `(source_id, category, timestamp)`, entirely EP-092's; `id` is a
  human-readable `f"{source_id}:{timestamp.isoformat()}"`, not a
  second identity mechanism.
- **Timestamps**: `timestamp` = when the generation reading was taken
  (e.g. a CSV row's date, or "now" for manual entry); `collected_at` =
  ingestion time — identical, unmodified distinction to EP-092/EP-093.
- **Validation** (informed by EP093-AUDIT-001, Section 2 E8): `value`
  must parse as a finite `float` — `math.isfinite()` check included
  from the start, not added after the fact. `unit` must be non-empty.
  `timestamp`, if given, must be valid ISO-8601 (bare date treated as
  midnight UTC, identical to EP-093's already-audited-correct
  behavior).
- **Serialization/persistence semantics**: entirely EP-092's
  (`PersonalDataPoint.to_dict()`/`from_dict()`, JSONL) — EP-094 never
  serializes anything itself, reusing exactly what EP-093 reuses.
- **Compatibility expectations**: none broken; new data, no migration
  (Section 12).

**Deferred data-model question, explicitly not resolved now:**
whether solar generation eventually needs `production`/`import`/
`export` as distinct sub-measurements (net-metering) is a Non-Goal
(Section 6C below) — no repository evidence specifies this shape, and
guessing it now risks a wrong, hard-to-change data model. If/when a
future EP needs it, `PersonalDataPoint.raw` already provides an
extensible bag for source-specific detail without a
`PersonalDataPoint` schema change, exactly as EP-093 used it for
`meter_id`.

---

## 8. Error Handling

Identical mechanism to EP-093, reused not reinvented, per this task's
own instruction ("do not invent a new error mechanism if an existing
one already fits"):

- `SolarMeterReadingError` — raised only for a failure that prevents
  *any* progress (CSV file missing/unreadable, required column
  missing) — never for a single bad row.
- A single malformed/non-finite CSV row is logged and skipped, never
  aborting the rest — identical to `import_electricity_csv`/
  `import_gas_csv`'s already-audited-correct behavior.
- `personal_data_module.py`'s `_import_csv` action: an all-invalid CSV
  (zero rows imported) returns `CommandResult(success=False, ...)`
  without attempting collection; a CSV with at least one valid row
  proceeds to `PersonalDataService.collect()` and reports its
  `success` — this is the exact, already-fixed EP093-AUDIT-002
  behavior, applied identically to the new category through the same
  code path (no per-category branching needed — the fix lives in the
  shared `_import_csv` method, not per-category logic).
- Collection/persistence failures: entirely EP-092's existing
  `PersonalDataCollectionError`/`PersonalDataProviderError` chain,
  unmodified.

---

## 9. Configuration

New, additive, top-level block, mirroring
`personal_data_electricity_gas:` exactly:

```yaml
personal_data_solar:
  # EP-094 Solar Generation Analytics. Configures which concrete
  # PersonalDataSource(s) this EP registers with EP-092's
  # PersonalDataManager (see src/core/personal_data/sources/
  # solar_source.py). Does not affect whether personal_data.* itself
  # is enabled, or which categories are allowed -- those remain
  # governed exclusively by the personal_data: block ('enabled_categories'
  # must separately include "solar_generation" for anything collected
  # here to actually be stored -- EP-092's consent gate, unchanged).
  enabled: false          # off by default; the operator opts in explicitly
  acquisition: "manual"   # V1: manual/CSV import via "personal_data
                          # record-reading"/"import-csv". A future named
                          # inverter/vendor value may be added once the
                          # Owner supplies one; none exists or is guessed today.
  csv_import_path: ""     # optional: reserved for a future default-path
                          # convenience, unused by STEP 2 -- identical
                          # disclosed status to personal_data_electricity_gas's
                          # own csv_import_path key.
```

- **Defaults**: `enabled: false` — opt-in, consistent with EP-093's
  precedent and EP-092's own "no personal data collected until an
  operator opts in" principle.
- **Validation**: mirrors `PersonalDataService`'s own defensive
  `isinstance` pattern for malformed config — a STEP 2 implementation
  detail, not a new mechanism.
- **Backward compatibility**: purely additive; no existing key
  (`personal_data:`, `personal_data_electricity_gas:`, or any
  unrelated block) is touched.
- **Interaction with existing configuration**: the operator must set
  *both* `personal_data_solar.enabled: true` *and* add
  `"solar_generation"` to `personal_data.enabled_categories` — the
  same two-independent-opt-ins pattern EP-093 established, not a new
  rule.

No configuration for a hypothetical inverter/vendor integration is
introduced (Section 6C Non-Goals).

---

## 6C. Non-Goals (mandatory section, per this task's Section 5C)

EP-094 explicitly does **not** include:

- Any named inverter/vendor/protocol integration (Modbus, a cloud
  inverter API, a specific brand's local API) — no repository
  evidence names one; inventing one would violate the Unknown API
  Policy exactly as it would have for EP-093.
- Net-metering / grid import-export accounting, or any data-model
  extension beyond a single `solar_generation` reading value.
- Visualization, charting, or reporting (EP-095).
- Forecasting, trend analysis, or anomaly detection (EP-096) —
  despite EP-094's own title containing "Analytics" (Section 1's
  evidence-based resolution of that naming ambiguity).
- Weather data (EP-097) or recommendations (EP-098).
- Automatic/Scheduler-driven collection in this pass (Section 5A/8 of
  `EP093_DESIGN.md`'s equivalent deferral; Section 10 below) — a
  complete, working V1 exists via CLI alone.
- Any change to `PersonalDataPoint`, `PersonalDataSource`,
  `PersonalDataProvider`, `PersonalDataPersistence`,
  `PersonalDataRegistry`, `PersonalDataManager`, or
  `PersonalDataService` (EP-092, closed and audited PASS).
- Remediation of EP093-AUDIT-004 (CLI coupling), EP093-AUDIT-005
  (unbounded local log), or EP093-AUDIT-007 (design-doc wording) — per
  this task's explicit instruction, these remain intentionally
  deferred; EP-094 *extends* the existing `_CATEGORY_HANDLERS` pattern
  and log-reading pattern without altering their shape.
- Any change to `Scheduler`, `Job`, `ExecutionEngine`, or any
  `Executor` (EP-011).

---

## 10. Runtime / Lifecycle Behavior

Identical in kind to `EP093_DESIGN.md` §10 — reused, not reinvented:
initialization (source constructed/registered once at Bootstrap time
when enabled), normal execution (CLI-triggered), failure isolation
(one source's failure never aborts a multi-source runner, if/when one
exists), idempotent repeated execution (via EP-092's `store_if_new()`
dedup, unchanged), restart/recovery (entirely EP-092's, unchanged),
concurrency (entirely EP-092's, unchanged). Scheduler integration
follows the exact same deferred-but-fully-specified shape EP-093
already established (a future, still-unbuilt standalone
multi-category runner script could iterate every enabled domain
group's registered sources — not proposed for implementation now).

---

## 11. File-Level Plan

**CREATE:**

| Path | Purpose | Dependencies |
|---|---|---|
| `src/core/personal_data/sources/solar_source.py` | `SolarCsvSource` + `append_solar_reading()`/`import_solar_csv()` + `SolarMeterReadingError` | `PersonalDataPoint`, `PersonalDataSource` (EP-092); stdlib `csv`/`json`/`math`/`pathlib`/`datetime` |
| `tests/EP094/__init__.py` | Test package marker | none |
| `tests/EP094/test_solar_generation_analytics.py` | EP-094 test suite | as Section 12 |

**MODIFY:**

| Path | Exact change | Public API impact |
|---|---|---|
| `src/core/personal_data/sources/__init__.py` | Add `solar_source` exports (`SolarCsvSource`, `append_solar_reading`, `import_solar_csv`, `SOLAR_CATEGORY`, `SOLAR_SOURCE_ID`), mirroring the existing electricity/gas export list | Additive only |
| `src/modules/personal_data_module.py` | Add a `"solar_generation"` entry to `_CATEGORY_HANDLERS`; **generalize** `__init__`'s `electricity_gas_enabled: bool` parameter into a per-category-enabled mechanism (Section 4) | **Breaking constructor signature change** — the only one this design proposes, fully specified here, not left for STEP 2 to improvise |
| `src/bootstrap.py` | Add one domain-group wiring block (construct `SolarCsvSource`, conditionally register with the already-existing `personal_data_service`, mirroring EP-093's block exactly); update the one `PersonalDataModule(...)` call site for the new constructor signature | None beyond the internal call-site update — `Bootstrap`'s own public properties are unaffected |
| `config/config.yaml` | Add the additive `personal_data_solar:` block (Section 9) | Additive only |
| `src/modules/test_module.py` | Add one import line: `import tests.EP094.test_solar_generation_analytics` | Additive only |

**MUST NOT be touched (explicit, per this task's Section 6 requirement):**

- Every file under `src/core/personal_data/` **except** `sources/__init__.py` (i.e., `personal_data_record.py`, `personal_data_source.py`, `personal_data_persistence.py`, `personal_data_provider.py`, `personal_data_registry.py`, `personal_data_manager.py`, and the package's own top-level `__init__.py`) — EP-092, closed.
- `src/services/personal_data_service.py` — EP-092, closed.
- `src/core/personal_data/sources/electricity_source.py`,
  `gas_source.py` — EP-093, closed; EP-094 does not need to modify
  either.
- `src/core/scheduler/`, `src/core/execution/` — untouched, per
  Section 6C.
- `tests/EP092/`, `tests/EP093/` — untouched; EP-094 adds its own new
  test directory only.
- `docs/architecture/JARVIS_ROADMAP.md`, `docs/BACKLOG.md`,
  `CHANGELOG.md`, `docs/RELEASE_NOTES.md` — per this project's
  established convention (EP-052/EP-092/EP-093 precedent), these are
  updated only at STEP 4 finalization, never at STEP 1 or STEP 2.

None of these files are created or modified by this STEP 1 document
itself, consistent with the hard rule that STEP 1 is design only.

---

## 12. Test Design (not implemented — specification only)

`tests/EP094/test_solar_generation_analytics.py`, one
`TestRegistry`-registered `BaseTest` subclass, `NAME = "EP094"`,
mirroring `tests/EP093/test_electricity_gas_monitoring.py`'s already-
proven structure and, informed by that suite's own STEP 3/3.1 audit
history, applying its lessons from the start rather than after a
defect is found:

- **Unit — manual entry**: valid reading accepted; non-numeric value
  rejected; empty unit rejected; malformed timestamp rejected;
  **all six non-finite spellings** (`nan`/`NaN`/`inf`/`Infinity`/
  `-inf`/`-Infinity`) rejected *before* any log write occurs (asserted
  by checking the log file does not exist/gain content after a
  rejected attempt — the exact assertion shape EP093-AUDIT-001's
  remediation test established, applied here from day one).
- **Unit — CSV import**: valid rows imported; a malformed row skipped
  without aborting the rest; a non-finite-value row skipped the same
  way; missing file raises `SolarMeterReadingError`; missing required
  column raises `SolarMeterReadingError`; `meter_id` disambiguates
  `source_id` (mirrors `EP093_DESIGN.md`'s own meter-disambiguation
  behavior, reused identically for e.g. multiple inverters).
- **Unit — `collect()`**: empty when no log exists; reads back
  appended readings; skips a malformed log line without aborting.
- **Integration**: full register → `collect_from()` → `query()` round
  trip through a real `PersonalDataManager` + `JsonlPersonalDataProvider`
  (temp directory) — proves EP-092 integration, not just EP-094's
  isolated logic; repeated `collect_from()` is idempotent (EP-092's
  `store_if_new()` dedup, re-verified for the new category rather than
  assumed); the consent gate correctly blocks `solar_generation` when
  not in `enabled_categories`.
- **Negative — boundary/failure paths**: an all-invalid CSV via the
  CLI action returns `CommandResult(success=False, ...)` (the
  EP093-AUDIT-002 lesson, applied to solar from day one, not
  discovered again); a mixed valid/invalid CSV returns `success=True`
  with the correct imported/skipped counts; a disabled
  `personal_data_solar.enabled` correctly rejects `record-reading`/
  `import-csv` via the CLI while `status`/`collect`/`query` remain
  available (mirrors EP-093's own already-audited-correct gating
  split).
- **CLI module**: `record-reading`/`import-csv` for the new category
  end-to-end through `PersonalDataModule`; unknown category still
  rejected; missing-argument usage messages unchanged.
- **Regression/architecture-compliance**: an AST-based check (mirroring
  `EP093_DESIGN.md`'s and the actual EP-093 suite's own pattern) that
  `solar_source.py` never imports `CommandResult`, and that
  `personal_data_module.py` still never imports `PersonalDataManager`/
  `PersonalDataProvider`/`PersonalDataPersistence`/
  `PersonalDataRegistry`/`ElectricityCsvSource`/`GasCsvSource`/
  `SolarCsvSource` after being extended for the new category.
- **CRLF/BOM regression** (test-only, no defect expected — applying
  the EP093-AUDIT-006 lesson proactively): a CRLF-terminated CSV and a
  BOM-prefixed CSV both import correctly.

**Existing regression suites that MUST remain green:** `tests/EP092`
(820 assertions) and `tests/EP093` (540 assertions) — both re-run
unmodified as part of STEP 2's own verification, exactly as EP-093's
STEP 2 re-ran EP-092's suite.

---

## 13. Regression Safety

| Area | Risk | Mitigation |
|---|---|---|
| EP-092 | None expected — no EP-092 file is touched (Section 11's explicit "must not touch" list) | Re-run `tests/EP092` (must remain 820/0/0) |
| EP-093 | The one real risk: `personal_data_module.py`'s constructor signature change (Section 4) could break any EP-093 test that constructs `PersonalDataModule(..., electricity_gas_enabled=...)` by keyword | Re-run `tests/EP093` (must remain 540/0/0); if the signature change breaks it, STEP 2 must update those call sites as part of the same change — not a silent, separate fix |
| Existing Personal Data CLI behavior | `status`/`collect`/`query`/`help` for electricity/gas must behave identically after the constructor generalization | Covered by the existing EP-093 suite re-run, plus new EP-094 tests exercising the same actions for solar |
| Test discovery | One new `test_module.py` import line, identical mechanism to EP-092/EP-093's own additions — same, already-proven-safe risk profile (a broken import would abort the whole chain, exactly as already true for every prior EP's line) | Verify `TestRunner().run("EP094")` and re-verify `("EP092")`/`("EP093")` still resolve after the addition |
| Existing persistence behavior | None — EP-094 writes to its own new `data/database/personal_data_solar/` directory and, via EP-092 unchanged, to `data/database/personal_data/solar_generation.jsonl`; neither path is shared with any existing data | Verified by the new integration tests (Section 12) |

Per this task's own instruction, passing EP-094's own tests alone does
not prove safety — the EP-092 and EP-093 regression re-runs above are
the actual safety evidence, exactly as EP-093's own STEP 2/3 process
already demonstrated is necessary.

---

## 14. Migration / Compatibility

**No data/config/persistence migration required.** `solar_generation`
is a brand-new category; no existing data exists for it.

**One compatibility note, already disclosed in Section 4/11:** the
`PersonalDataModule.__init__` signature change is a breaking change to
that one constructor's call sites. There is exactly one production
call site (`src/bootstrap.py`) and whatever EP-093's own test suite
uses — both must be updated in the same STEP 2 change, not
independently. No external/third-party caller of this constructor
exists (it is an internal wiring detail, never part of any public,
documented API surface).

---

## 15. Alternatives Considered

**Alternative A — Mirror EP-093 exactly, extend the shared CLI module
(RECOMMENDED).** As specified above: one new source file, one new
category, one extended `_CATEGORY_HANDLERS` entry, one generalized
constructor parameter, one new Bootstrap wiring block, one new config
block.
*Advantages:* smallest possible change; reuses every already-audited-
PASS piece of infrastructure; no new abstraction; directly
implementable in STEP 2 with zero ambiguity.
*Disadvantages:* the one disclosed breaking constructor-signature
change (Section 4), and a (already-accepted, not worsened) increase in
`_CATEGORY_HANDLERS`'s hard-coded size.
*Complexity:* low. *Compatibility risk:* low, fully specified.

**Alternative B — Give EP-094 its own, separate `solar` CLI
namespace/module, avoiding any change to `personal_data_module.py`.**
*Advantages:* zero risk to EP-093's existing CLI module or its tests;
no constructor-signature change.
*Disadvantages:* directly contradicts `EP093_DESIGN.md` §9.1's own,
already-approved reasoning for why per-domain CLI namespaces were
rejected for EP-093 itself ("a namespace per domain category... would
need to be reinvented again for EP-094's solar and EP-097's weather
categories" — the exact scenario this alternative would enact); would
leave two inconsistent CLI patterns for what is conceptually the same
kind of action (recording a reading, importing a CSV) across
categories.
*Complexity:* low individually, but scales badly (a third namespace
for EP-097). *Compatibility risk:* low, but at the cost of
architectural consistency EP-093 explicitly established.

**Alternative C — Introduce a small, generic "personal-data category
registration" mechanism (e.g., each acquisition EP registers its own
CLI-action metadata into a shared registry, rather than a hand-edited
`_CATEGORY_HANDLERS` dict) so future EPs (EP-097+) never need to touch
`personal_data_module.py` again.**
*Advantages:* would fully resolve EP093-AUDIT-004's coupling concern
for all future categories at once.
*Disadvantages:* exactly the kind of generic, "might be useful for a
third/fourth future consumer" infrastructure this project's own
conventions (and EP-093's own rejected "Option C generic HTTP
adapter") caution against building before it is genuinely load-bearing
— today there are only two categories, about to become three; a
registry abstraction for three hard-coded dict entries is premature.
Also explicitly out of this task's scope ("do NOT automatically
include \[EP093-AUDIT-004\] in EP-094... only consider \[it\] if the
actual EP-094 scope explicitly requires addressing \[it\]" — it does
not; a third dict entry is sufficient).
*Complexity:* medium, for a benefit not yet needed.
*Compatibility risk:* medium (a real, if small, redesign of already-
audited-PASS EP-093 code, for no EP-094-specific requirement).

---

## 16. Recommended Design

**Alternative A.** It is the smallest architecture that correctly
satisfies EP-094's requirement, reuses every already-proven-correct
piece of infrastructure (EP-092's framework, EP-093's CLI namespace
and per-category source pattern) without duplicating any of it,
introduces no new abstraction, and is fully specified — every file,
every exact change, every test — such that STEP 2 requires no further
architectural decision-making. The one breaking change it requires
(`PersonalDataModule`'s constructor) is real, disclosed, minimal, and
has exactly one production call site to update in the same pass.

---

## 17. Final Self-Check

- [x] EP-094 scope derived from repository evidence (Section 1/2), not guessed.
- [x] Current architecture inspected (EP-092/EP-093 source, actual, re-read fresh).
- [x] EP-092 and EP-093 dependencies inspected explicitly (Section 2/3).
- [x] No implementation code changed.
- [x] No tests implemented.
- [x] No unrelated refactoring proposed.
- [x] Non-Goals explicitly documented (Section 6C).
- [x] Dependency direction explicit (Section 3/5B).
- [x] File-level implementation plan exists (Section 11), including files that must NOT be touched.
- [x] Test strategy exists (Section 12), not implemented.
- [x] Regression risks identified (Section 13).
- [x] Migration requirements addressed (Section 14: none, except the one disclosed constructor change).
- [x] Recommended design explicit (Section 16).
- [x] STEP 2 can start directly from this design with no further architectural decision required.

---

## Final Report

1. **EP-094 title/purpose**: Solar Generation Analytics — in current-
   phase scope, this means acquisition of solar-generation data as
   `PersonalDataPoint`s via a new `solar_generation` category, the
   same interpretation already established for EP-093's "Monitoring"
   title; true analytics/visualization belong to EP-095/096.
2. **Design status**: `DESIGN PROPOSED — awaiting Owner Decision`.
3. **Recommended architecture**: Alternative A — one new
   `SolarCsvSource` (manual entry + CSV import, Design A, no new
   abstraction) registered with EP-092's existing
   `PersonalDataManager` via the already-built, shared `personal_data`
   CLI namespace, extended (not duplicated) for the new category.
4. **Files planned for STEP 2**: `src/core/personal_data/sources/
   solar_source.py` (new); `src/core/personal_data/sources/__init__.py`,
   `src/modules/personal_data_module.py`, `src/bootstrap.py`,
   `config/config.yaml`, `src/modules/test_module.py` (all modified,
   additively except for `personal_data_module.py`'s one disclosed
   constructor-signature change); `tests/EP094/__init__.py` and
   `tests/EP094/test_solar_generation_analytics.py` (new).
5. **Files explicitly not to be touched**: every other EP-092 file,
   `electricity_source.py`/`gas_source.py` (EP-093), `Scheduler`/
   `ExecutionEngine` files, `tests/EP092/`/`tests/EP093/`, and
   roadmap/backlog/changelog/release-notes documents (updated only at
   STEP 4, per established convention).
6. **Test strategy**: full unit/integration/negative/architecture-
   compliance coverage for the new category (Section 12), proactively
   applying the three lessons EP-093's own STEP 3/3.1 audit already
   proved necessary (non-finite rejection, CSV success-flag semantics,
   CRLF/BOM handling) rather than waiting to discover them again; both
   EP-092 (820) and EP-093 (540) regression suites re-run unmodified.
7. **Regression risks**: the one disclosed constructor-signature
   change to `personal_data_module.py` is the sole real risk, fully
   scoped to its single production call site (`bootstrap.py`) plus
   whatever EP-093 tests construct it directly — both updated in the
   same STEP 2 pass, verified by re-running `tests/EP093` green
   afterward.
8. **Ready for STEP 2**: **Yes.**
