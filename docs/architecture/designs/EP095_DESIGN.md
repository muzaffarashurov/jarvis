# EP-095 — Energy Visualization & Reporting — Design

Version: 1.1
Status: STEP 1.1 — Design Refinement / Implementation-Readiness Verification
(STEP 1 — Architecture Design — complete; superseded in place by this
revision, following this repository's own EP069.2/EP069.3-style
convention of a "STEP 3.1"-equivalent refinement pass updating the
existing document in place rather than creating a second one.)

---

## 0. Source-of-Truth Note

This document was produced from direct repository inspection performed
across two sessions: `docs/architecture/JARVIS_ROADMAP.md`,
`docs/BACKLOG.md`, `docs/architecture/designs/EP092_DESIGN.md` (§11,
§12, §15, §21), `EP093_DESIGN.md`, `EP094_DESIGN.md`,
`docs/architecture/designs/JARVIS_DECISION_REQUIRED_ARCHITECTURE_RESOLUTION.md`,
`src/core/command_router.py`, `src/bootstrap.py`,
`src/core/capability/`, `src/core/capability_discovery/`,
`src/core/capability_security/`, `src/core/capability_policy/`,
`src/core/capability_lifecycle/`, `src/skills/capability_registry/skill.py`,
`src/core/personal_data/` (all files), `src/services/personal_data_service.py`,
`src/modules/personal_data_module.py`, `src/modules/test_module.py`,
`src/testing/base_test.py`, `src/testing/registry.py`,
`src/testing/runner.py`, `config/config.yaml`, and `tests/EP092/`,
`tests/EP093/`, `tests/EP094/`. Where documentation and code could
conceivably disagree, the code and its tests are treated as
authoritative; every such point is called out explicitly below.

### 0.1 Discrepancy Found and Resolved at STEP 1 (unchanged at STEP 1.1)

The original task framing repeatedly suggested that EP-095 might now
be, or need to be reconsidered as, the **Capability Governance
Integration / Wiring** work identified by
`JARVIS_DECISION_REQUIRED_ARCHITECTURE_RESOLUTION.md` (Decision 2) as
the project's recommended next Engineering Package. This was resolved
at STEP 1 and is **re-verified, unchanged, at STEP 1.1**:

- `JARVIS_DECISION_REQUIRED_ARCHITECTURE_RESOLUTION.md` Decision 2
  names Capability Governance Wiring "`EP-NEW-CANDIDATE-1`" —
  explicitly unnumbered, pending Owner approval.
- The same document's Decision 7 (re-read this session, unchanged)
  states plainly that EP-095 and EP-096 are unblocked today and
  independent of Decision 1/Decision 2; nothing anywhere proposes
  redefining EP-095 as the Governance Wiring work.
- `docs/BACKLOG.md` (re-read this session) still lists **"EP-095 —
  Energy Visualization & Reporting (MEDIUM)"** unchanged; grepping both
  `JARVIS_ROADMAP.md` and `BACKLOG.md` for "governance wiring" /
  "EP-NEW-CANDIDATE" still returns zero matches.

**Conclusion, re-confirmed at STEP 1.1:** EP-095 is, and remains,
Energy Visualization & Reporting, with no dependency relationship to
Capability Governance Wiring in either direction. §11 below documents
this as an architectural relationship only (what happens automatically
if that wiring lands later), never as EP-095 implementation work.

---

## 1. Purpose

EP-095 gives the Personal Data Collection Framework (EP-092) and its
two shipped acquisition sources (EP-093 Electricity & Gas, EP-094
Solar) a read-only reporting and export surface. Today, the only way
to see collected data is `personal_data query <category> [start]
[end]` (`src/modules/personal_data_module.py`), which returns a flat,
unaggregated list of `PersonalDataPoint` values with no totals,
averages, time-bucketing, or export path. EP-095 adds three new
`personal_data` actions:

- **`report`** — aggregated totals/averages/min/max over a category
  and time range, optionally broken down by day/week/month bucket.
- **`export`** — CSV export of raw points or a bucketed report,
  written to an operator-specified path. Explicitly named as EP-095's
  own deferred scope by EP-092 itself (`EP092_DESIGN.md` §11 DEFERRED:
  *"Export/import of personal data (e.g. to CSV) — natural fit for
  EP-095 Visualization, not EP-092"*).
- **`chart`** — a console-rendered (ASCII/Unicode text) bar chart of a
  category's bucketed values over time. No new third-party dependency,
  no image file, no GUI (see §10 Non-Goals).

EP-095 is Phase E's second slice, alongside EP-096 (Forecast/Anomaly),
both reading through the same, already-complete query surface EP-092
established.

---

## 2. Current-State Analysis

**Personal Data Collection Framework (EP-092, COMPLETE):**
`PersonalDataService` (`src/services/personal_data_service.py`) is the
sole CLI-facing entry point, wrapping `PersonalDataManager`
(`src/core/personal_data/personal_data_manager.py`), which delegates
to `PersonalDataProvider` (ABC) and its sole approved concrete
implementation `JsonlPersonalDataProvider`
(`src/core/personal_data/personal_data_provider.py`), writing to
`data/database/personal_data/<category>.jsonl` via
`PersonalDataPersistence` (low-level file I/O only). Verified methods:

- `PersonalDataService.query(category, start=None, end=None) ->
  list[PersonalDataPoint]` — returns points sorted by `timestamp`.
  Internally: `if not self._is_enabled(): return []`, otherwise
  delegates to `PersonalDataManager.query()`, which delegates to
  `PersonalDataProvider.query()` with **no per-category consent
  filter** (see §11 — this is a load-bearing correction from STEP 1).
- `PersonalDataManager.query(category, start, end)` — `start` filters
  `timestamp >= start`, `end` filters `timestamp <= end` (both
  **inclusive**, verified directly from the method's own docstring).
- `PersonalDataService.status() -> PersonalDataStatus`,
  `PersonalDataManager.stats() -> dict[str, int]`,
  `PersonalDataManager.source_ids() -> list[str]`.

`PersonalDataPoint` (`src/core/personal_data/personal_data_record.py`)
is a frozen dataclass: `id: str`, `source_id: str`, `category: str`,
`timestamp: datetime`, `value: float`, `unit: str`, `raw: dict[str,
Any]`, `collected_at: datetime`. **Verified this session:** timestamps
are timezone-aware — `utc_now()` returns `datetime.now(timezone.utc)`,
and `_parse_timestamp()` accepts either an existing `datetime` or an
ISO-8601 string via `datetime.fromisoformat()`. Nothing in this module
enforces that all points within a category share the same `unit` — it
is a free-form, non-empty string validated only for non-emptiness,
and each manual `record-reading` call supplies its own `<unit>`
argument independently (see §14 for why this matters to EP-095).

**Acquisition sources (EP-093/EP-094, COMPLETE):** three real
categories: `electricity_consumption`, `gas_consumption` (EP-093,
`src/core/personal_data/sources/electricity_source.py` /
`gas_source.py`), and `solar_generation` (EP-094, `solar_source.py`).
All are manual/CSV-import sources today
(`personal_data_electricity_gas.acquisition: "manual"`), exposed via
the shared `personal_data` CommandRouter namespace,
`PersonalDataModule` (`src/modules/personal_data_module.py`).

**`PersonalDataModule`'s existing CLI conventions (verified this
session, load-bearing for §7 below):**

- Actions are dispatched via a flat `dict[str, ActionHandler]`
  (`self._actions`) keyed by exact lowercased action string —
  `CommandRouter.dispatch()` already lowercases the action token
  before calling `module.execute()`, so `PersonalDataModule` itself
  performs no further case-folding.
- `_parse_optional_datetime(raw: str)` (an existing `@staticmethod` on
  `PersonalDataModule`) is the **one and only** date/time parser used
  by the `query` action today: it first tries `date.fromisoformat(raw)`
  (a bare `YYYY-MM-DD`, combined with `datetime.min.time()` and
  `tzinfo=timezone.utc`), then falls back to
  `datetime.fromisoformat(raw)` (a full ISO-8601 datetime, with
  `tzinfo=timezone.utc` applied if the parsed value is naive). It
  returns the sentinel `False` (distinct from `None`) on a genuinely
  unparseable string, letting the caller distinguish "not supplied"
  from "supplied but invalid."
- The `_query` action's own error/empty-result conventions: invalid
  start/end → `CommandResult(success=False, message="start/end must be
  ISO-8601 dates or datetimes.")`; no matching points →
  `CommandResult(success=True, message=f"personal_data:
  {category}\n\n(empty)")`.
- `_import_csv`'s error-translation convention: the CSV-import
  function raises a domain-specific error (`ElectricityMeterReadingError`
  et al., collected as `_CSV_IMPORT_ERRORS`); the module catches it and
  returns `CommandResult(success=False, message=str(exc))` — file I/O
  and domain validation live below the module, the module only
  translates the outcome into a `CommandResult`.
- CSV reading convention (`electricity_source.py`,
  `import_electricity_csv`): `Path(path).open("r",
  encoding="utf-8-sig", newline="")`, `csv.DictReader`, explicit
  required-column check, one skipped-row message per malformed row
  rather than aborting the whole import.

**Test execution mechanism (verified this session — corrects STEP 1's
`pytest` wording, see §16):** This project's authoritative test runner
is **not** `pytest` as an external CLI invocation. It is a custom
in-process framework: `BaseTest` (`src/testing/base_test.py`, an `ABC`
with `run() -> TestResult` and `assert_*` helpers), `TestRegistry`
(`src/testing/registry.py`, a `@TestRegistry.register` class decorator
keyed by an uppercased `NAME` string), and `TestRunner`
(`src/testing/runner.py`, `run(suite_name)` / `run_all()` /
`list()`). Suites are dispatched through the CLI via `TestModule`
(`src/modules/test_module.py`, namespace `"test"`): `test list`
(lists registered suite names), `test all` (runs every registered
suite), and `test <NAME>` (e.g. `test EP092`, `test EP093`, `test
EP094` — runs `TestRunner.run("EP092")`, i.e. every class registered
under `NAME = "EP092"`). **Critically, a suite is registered only as a
side effect of its module being imported** — `test_module.py`
explicitly imports every EP's test module by name near its top (e.g.
`import tests.EP092.test_personal_data_collection_framework`,
`import tests.EP093.test_electricity_gas_monitoring`, `import
tests.EP094.test_solar_generation_analytics`), with a comment stating
these imports exist only for registration and are never used directly.
`pytest` is present in `requirements.txt` but nothing in `src/` invokes
it as this project's test-execution contract; the existing
`tests/EP09x/*.py` files' own docstrings ("Real engineering tests...
matching every other EP's test suite in this project") and their
`@TestRegistry.register` / `class ...(BaseTest)` structure are the
actual, working precedent.

**Capability governance stack (EP-069.4–.7, EP-070, all individually
COMPLETE but unwired):** unchanged from STEP 1 — `CapabilityRegistry`,
`CapabilityDiscoveryEngine`, `CapabilitySecurityEngine`, `PolicyEngine`,
`CapabilityLifecycleRegistry` are not constructed in `bootstrap.py` and
not consulted by `CommandRouter.dispatch()` (zero references, verified
directly in `src/core/command_router.py`, 194 lines).

**No visualization/reporting/export infrastructure exists yet** and no
plotting library is present in `requirements.txt` (unchanged from
STEP 1, re-verified).

---

## 3. Architectural Context

Unchanged from STEP 1, re-verified:

- **EP-069.6/EP-069.7/EP-070 (Capability Security/Lifecycle/Policy):**
  Not consulted. EP-095 is a plain `CommandModule` dispatched through
  the existing, unmodified `CommandRouter.dispatch()` chokepoint,
  exactly as every other module (including `PersonalDataModule`
  itself) is today.
- **The capability architecture generally (`Capability`,
  `CapabilityRegistry`, EP-069.4):** Not used.
- **`CommandRouter`:** No change (re-verified at STEP 1.1, §9).
- **Upstream: EP-092/093/094 (COMPLETE):** EP-095 is a pure consumer
  of `PersonalDataService.query()`/`status()`. No new
  `PersonalDataSource`, persistence backend, or category is added.
- **Downstream: EP-096/EP-098:** Both independently gated on the same
  `PersonalDataManager.query()` surface EP-095 uses, per `EP092_
  DESIGN.md` §11 and the resolution document's Decision 7 — EP-095 has
  no documented downstream dependents and introduces no new shared
  abstraction they would be forced to depend on.

---

## 4. Problem Statement

`personal_data query` returns a flat, unaggregated point list with no
totals, trends, or export path. An operator who has recorded
electricity/gas/solar readings for weeks has no way to answer "how
much electricity did I use last month" or get a CSV for personal
record-keeping without hand-parsing raw output. This is an evidenced
gap, not a manufactured one — `EP092_DESIGN.md` §11 itself deferred CSV
export to EP-095 by name.

---

## 5. Scope

### IN SCOPE

- `personal_data report <category> [start] [end] [bucket]` — see §7
  for the finalized argument contract.
- `personal_data export <category> <path> [start] [end] [mode]` — see
  §7 and §13 (CSV Contract).
- `personal_data chart <category> [start] [end] [bucket]` — see §7.
- Reuse of the existing consent gate, `PersonalDataService.query()`,
  `_parse_optional_datetime()`, and `CommandResult`/`CommandModule`
  patterns exactly as `PersonalDataModule` already establishes them —
  no new date parser, no new CLI convention.
- One small, additive registration change identified at STEP 1.1 and
  **not previously disclosed at STEP 1**: adding `import
  tests.EP095.test_energy_visualization_reporting` to
  `src/modules/test_module.py`, mirroring the existing line-per-EP
  pattern already used for EP-092/093/094 (see §9). This is the one
  concrete, evidenced exception to STEP 1's "no bootstrap-adjacent
  file needs to change" claim.

### OUT OF SCOPE

- Any change to `PersonalDataManager`, `PersonalDataProvider`,
  `PersonalDataPersistence`, `PersonalDataRegistry`, or any existing
  `PersonalDataSource`.
- Any change to `CommandRouter`, `bootstrap.py`'s existing wiring
  logic, or any capability/discovery/security/policy/lifecycle
  package.
- Forecasting, anomaly detection, or predictive analytics (EP-096).
- Cross-category recommendations (EP-098).
- Any new external data source or credential handling (EP-097 /
  Decision 1's scope).
- Graphical (image-file or GUI) chart rendering, or any new
  third-party dependency (matplotlib/plotly/pandas-for-this-purpose)
  — see §18.
- Unit conversion of any kind (§14).
- A generic, reusable "Reporting Engine"/"Visualization Engine"
  abstraction — nothing in the repository evidences a second consumer.

### DEFERRED

- Image/GUI-rendered charts, scheduled/automatic report generation —
  unchanged from STEP 1; revisit only on explicit Owner request.

---

## 6. Out of Scope

(Restated as explicit boundaries, unchanged from STEP 1): no
modification to any file under `src/core/personal_data/`; no
modification to `src/core/command_router.py`; no modification to any
`src/core/capability*` package or `src/skills/capability_registry/`;
no new AI-provider, embedding, retrieval, RAG, semantic search, or
Knowledge Base dependency.

---

## 7. Architecture

```
                    CLI: "personal_data report <category> [start] [end] [bucket]"
                    CLI: "personal_data export <category> <path> [start] [end] [mode]"
                    CLI: "personal_data chart  <category> [start] [end] [bucket]"
                                 │
                    ┌────────────▼─────────────┐
                    │    PersonalDataModule      │  (existing, EP-092/093/094;
                    │  (src/modules/             │   extended with 3 new entries
                    │   personal_data_module.py) │   in self._actions + HELP_TEXT)
                    └────────────┬─────────────┘
                                 │  calls (new, EP-095-owned, thin, pure)
                    ┌────────────▼──────────────┐
                    │  PersonalDataReportService  │  new module,
                    │  (src/services/             │  src/services/
                    │   personal_data_report_     │  personal_data_report_
                    │   service.py)               │  service.py
                    │  - aggregate(points, bucket) │  -> ReportSummary
                    │  - write_raw_csv(points, path)│
                    │  - write_report_csv(buckets, path)│
                    │  - render_ascii_chart(buckets)│  -> str
                    └────────────┬──────────────┘
                                 │  calls (existing, unmodified)
                    ┌────────────▼─────────────┐
                    │   PersonalDataService      │  .query(category, start, end)
                    │   (existing, EP-092)       │  -- unmodified
                    └───────────────────────────┘
```

**Finalized CLI contract (this is the STEP 1.1 precision pass; every
sub-point below is a deliberate, documented decision, not left open
for STEP 2 to invent):**

### `report`

- **Required:** `<category>`.
- **Optional, positional, trailing (same convention as `query`):**
  `[start] [end] [bucket]`.
- **Date format:** identical to `query` — reuses
  `PersonalDataModule._parse_optional_datetime()` unchanged. Accepts a
  bare `YYYY-MM-DD` (midnight UTC) or a full ISO-8601 datetime (naive
  input is assumed UTC, matching the existing helper's behavior
  exactly). Invalid input → `CommandResult(success=False, message=
  "start/end must be ISO-8601 dates or datetimes.")`, identical wording
  to `query`'s existing error.
- **Default date behavior:** omitted `start`/`end` → unbounded on that
  side, exactly as `query` already behaves (`start or None`, `end or
  None` passed through unchanged).
- **Bucket options:** one of `day` | `week` | `month` (case-insensitive,
  lowercased before comparison, matching `CommandRouter`'s own
  case-insensitive convention for module/action names). Invalid value
  → `CommandResult(success=False, message="bucket must be one of:
  day, week, month.")`.
- **Default bucket:** `day`, applied only if a bucket breakdown is
  shown; the overall summary (count/sum/avg/min/max) is always
  computed regardless of bucket size.
- **Output structure:** a header line (`personal_data report:
  <category> [<start>..<end>]`), then an overall summary line
  (`Count: N  Sum: X <unit>  Avg: X  Min: X  Max: X`, or the
  mixed-unit form from §14 if applicable), then one line per non-empty
  bucket in ascending chronological order (`<bucket-start> .. <bucket-
  end>: count=N sum=X avg=X min=X max=X`).
- **No-data behavior:** `CommandResult(success=True, message=
  f"personal_data report: {category}\n\n(empty)")` — same
  success-with-"(empty)" convention as `query`, never a failure.

### `export`

- **Required:** `<category>`, `<path>`.
- **Optional, positional, trailing:** `[start] [end] [mode]`.
  **Decision (STEP 1.1, resolving an ambiguity STEP 1 left open):**
  `mode` is placed *after* `start`/`end`, mirroring `report`'s and
  `query`'s existing "date range first" ordering, for CLI consistency
  across all three new/existing actions on this namespace, at the cost
  of requiring explicit `start`/`end` tokens to reach `mode` when an
  unbounded-range report-mode export is wanted (no new sentinel token
  is introduced for "skip this argument," since none exists anywhere
  else in this codebase's CLI conventions).
- **Date format:** identical to `report`/`query` (see above).
- **Raw vs. report mode:** `mode` is one of `raw` | `report`
  (case-insensitive). **Default: `raw`** — exporting exactly what
  `query` already shows is the more predictable, least-surprising
  default; `report` mode must be explicitly requested. Invalid mode
  value → `CommandResult(success=False, message="mode must be one of:
  raw, report.")`.
- **CSV structure/columns:** see §13.
- **No-data behavior:** a CSV file **is still written**, containing
  only the header row — this matches `export`'s nature as a mechanical
  data dump, not a report; an empty file with no header would be
  ambiguous about whether export ran at all. `CommandResult(success=
  True, message=f"Exported 0 row(s) to '<path>'.")`.
- **Target directory does not exist:** **not** auto-created. Rejected
  with `CommandResult(success=False, message="Cannot write to
  '<path>': directory does not exist.")` — auto-creating directories on
  an operator-supplied path would be exactly the kind of silent,
  unrequested behavior this EP is meant to avoid; the operator creates
  the destination folder first.
- **Target file already exists:** **overwritten unconditionally**, no
  prompt — this CLI dispatches one command at a time with no
  interactive confirmation mechanism anywhere else in the codebase
  (verified: no existing module implements a confirm-before-overwrite
  step), so introducing one here would be a new, EP-095-only
  interaction pattern with no precedent. The overwrite is documented
  here explicitly so STEP 2 does not need to decide it independently.
- **Windows path handling:** the `<path>` argument is passed to
  `pathlib.Path(path)` and opened via `Path.open(...)` exactly as
  `import-csv`'s existing `csv_path = Path(path)` already does —
  native Windows paths (`D:\AI Workspace\jarvis\exports\file.csv`),
  quoted at the shell level by the existing `CommandRouter._tokenize()`
  (`shlex` with `escape=""`, already fixed for Windows backslash
  corruption per that method's own docstring), work unchanged. No new
  path-handling code is introduced.

### `chart`

- **Required:** `<category>`.
- **Optional, positional, trailing:** `[start] [end] [bucket]` —
  identical contract to `report`'s date/bucket arguments (same
  parser, same defaults, same error wording, `bucket` default `day`).
- **Ordering:** buckets rendered in ascending chronological order,
  identical to `report`.
- **Scaling behavior:** each bucket's bar length is proportional to
  its `sum` value, scaled so the largest bucket in the displayed range
  renders at a fixed maximum width (e.g. 40 characters) — a
  console-width-safe, dependency-free scaling rule; the exact bar
  character and width are an implementation-level (not
  architectural) choice for STEP 2, provided the *proportionality*
  rule above is followed.
- **Empty-data behavior:** `CommandResult(success=True, message=
  f"personal_data chart: {category}\n\n(empty)")` — same convention
  as `report`/`query`.
- **Unit display:** each bucket row shows its bucket label, numeric
  sum, and unit suffix when the category's queried points share one
  unit; see §14 for the mixed-unit case.

---

## 8. Integration Points

- `src/services/personal_data_service.py` — `PersonalDataService.query()`,
  `.status()` (both called unmodified).
- `src/core/personal_data/personal_data_record.py` — `PersonalDataPoint`
  (read-only).
- `src/modules/personal_data_module.py` — `PersonalDataModule` extended
  with `report`/`export`/`chart` entries in `self._actions` and three
  new `HELP_TEXT` lines; reuses the existing `_parse_optional_datetime`
  `@staticmethod` unchanged.
- `src/services/personal_data_report_service.py` — **new file**,
  `PersonalDataReportService` (see §7 diagram).
- `src/core/command_router.py` — `CommandModule` protocol,
  `CommandResult` dataclass (used, not modified).
- `src/bootstrap.py` — **no change** (re-verified at STEP 1.1; see
  §9).
- `src/modules/test_module.py` — **one new import line** required at
  STEP 2 for suite registration (see §5, §9); this is documentation of
  a required STEP 2 touch, not performed now.

---

## 9. Configuration

No new top-level `config.yaml` block is required (unchanged from
STEP 1). EP-095 reads no configuration of its own — it reuses
`personal_data.enabled`/`enabled_categories` transitively through
`query()`/`status()`. CSV export destination is a CLI argument, not a
configured default, matching `personal_data_electricity_gas.
csv_import_path`'s own precedent of leaving path selection to the CLI
call.

**STEP 1.1 verification of "no `CommandRouter`/`bootstrap.py` change
needed" (Critical Correction #7 — directly re-read this session):**

- `src/core/command_router.py` (194 lines, re-read in full):
  `CommandRouter.register()` stores one `CommandModule` instance per
  namespace in a `dict`; `dispatch()` looks up the namespace and calls
  `module.execute(action, arguments)` — the router has no knowledge of
  which actions a module supports, so adding entries to
  `PersonalDataModule._actions` requires zero router change.
- `src/bootstrap.py` (re-read lines 684–732): constructs one
  `PersonalDataService`, registers EP-093/094's sources conditionally
  on their own config flags, and calls `router.register(
  PersonalDataModule(personal_data_service, enabled_categories=...))`
  exactly once. This registration call passes the same
  `PersonalDataService` instance EP-095's new actions will call — no
  new constructor argument, dependency, or registration call is
  needed for `report`/`export`/`chart` to work, since they live inside
  the same `PersonalDataModule` class/instance already registered.
- **Confirmed: no `CommandRouter`/`bootstrap.py` change is required.**
  The one genuinely required addition is the test-registration import
  in `src/modules/test_module.py` (§5, §8) — a different file from
  either of these two, and not a "wiring" change in the
  `CommandRouter`/`bootstrap.py` sense the original claim addressed.

Windows-compatible export path example (illustrative only):

```
personal_data export electricity_consumption "D:\AI Workspace\jarvis\exports\electricity_2026.csv" 2026-01-01 2026-09-01 report
```

---

## 10. Error Handling

- **Category never collected / subsystem disabled:** `report`/`chart`
  return a successful `CommandResult` with the "(empty)" message (§7)
  — never an error, mirroring `query()`'s existing behavior exactly.
- **Invalid start/end:** rejected before calling `query()`, with the
  same message text `query` already uses (§7).
- **Invalid `bucket`/`mode`:** rejected with an explicit
  enumerated-values message (§7) — never silently defaulted.
- **CSV write failure (unwritable path, missing directory,
  permissions error):** `PersonalDataReportService`'s CSV-writing
  methods raise a new, EP-095-owned domain exception,
  `PersonalDataReportError` (mirroring `ElectricityMeterReadingError`'s
  existing role exactly — a plain `Exception` subclass, not shared
  with any other EP's error hierarchy). `PersonalDataModule` catches
  `PersonalDataReportError` and returns `CommandResult(success=False,
  message=str(exc))`, following the identical catch-and-translate
  pattern already used by `_import_csv`'s `except _CSV_IMPORT_ERRORS`.
  No unhandled exception is expected to reach `CommandRouter.
  dispatch()`'s own generic `except Exception` fallback.
- **Empty bucketed series for `chart`:** the "(empty)" message (§7),
  not a malformed/zero-width chart.

**Where CSV file I/O lives (Critical Correction #6, resolved):**
`PersonalDataReportService` performs the CSV file I/O itself
(`write_raw_csv`/`write_report_csv`), raising `PersonalDataReportError`
on failure — this mirrors the existing precedent set by
`import_electricity_csv`/`import_gas_csv`/`import_solar_csv` (§2),
which likewise perform their own file I/O one layer below
`PersonalDataModule` and raise a domain error the module then
translates. `PersonalDataModule` itself performs no file I/O directly,
consistent with its own documented role as "thin CLI parsing only."

---

## 11. Security / Governance Considerations

EP-095 is entirely read-only with respect to personal data — it never
writes to `data/database/personal_data/*.jsonl` and never mutates a
`PersonalDataPoint`. Its only write is the operator-specified CSV
export file, at a path the operator explicitly supplies (§7's
directory/overwrite rules apply).

EP-095 introduces no new authorization, permission, or security model,
and does not query `CapabilityRegistry`/`CapabilityDiscoveryEngine`/
`CapabilitySecurityEngine`/`PolicyEngine`/`CapabilityLifecycleRegistry`
— consistent with the fact that no existing `CommandModule` in this
repository (including `PersonalDataModule` itself) consults that stack
today. Should the not-yet-numbered Capability Governance Wiring EP
(§0.1) later wire enforcement into `CommandRouter.dispatch()`, EP-095's
new actions would be subject to it automatically and identically to
every other action already dispatched through that same chokepoint —
documented here purely as an architectural relationship, never as
EP-095 implementation work.

**Consent boundary — corrected and precisely stated (Critical
Correction — this materially changes the STEP 1 wording, which
overstated the guarantee):**

- `PersonalDataService.query()` checks only the top-level
  `personal_data.enabled` flag (`_is_enabled()`); if `False`, it
  returns `[]` immediately, and `report`/`export`/`chart` therefore
  correctly show "(empty)"/export zero rows.
- **`PersonalDataManager.query()`/`PersonalDataProvider.query()` apply
  no per-category consent filter** — `personal_data.
  enabled_categories` (the allowlist) is enforced only on the *write*
  path (`collect_from()` refuses to store, per `EP092_DESIGN.md` §15:
  *"`PersonalDataManager` refuses to store... any category not on that
  list"*), not on the *read* path. This is existing, documented
  EP-092 behavior (§15's own wording distinguishes "refuses to store"
  from any read-side guarantee) — **not** a gap EP-095 introduces, and
  **not** something EP-095 can or should silently "fix," since doing
  so would be an undisclosed behavior change to `PersonalDataManager.
  query()` itself, out of EP-095's scope (§6).
- **Practical consequence for EP-095, stated explicitly so STEP 2 does
  not need to rediscover it:** if a category is later removed from
  `enabled_categories` after data was already collected while it was
  allowed, `report`/`export`/`chart` (like `query` today) will still
  return that historical data. This is consistent, existing behavior
  across all four read actions — EP-095 neither widens nor narrows it.
- **What EP-095 genuinely does inherit and cannot bypass:** the
  top-level `personal_data.enabled` kill switch, and the fact that a
  category with zero ever-collected points returns nothing to any of
  the four actions.

**Path-handling constraint for STEP 2 (export):** the destination path
must be resolved via `pathlib.Path`, never raw string concatenation,
and no directory is ever auto-created (§7) — an operator-supplied path
is written to exactly as given, with a clear failure rather than
speculative filesystem mutation if the destination doesn't exist.

---

## 12. Backward Compatibility

Unchanged from STEP 1, re-verified: no existing `PersonalDataModule`
action changes signature/behavior/output; no existing
`tests/EP092/EP093/EP094` test is expected to require modification;
`config/config.yaml`'s `personal_data*` blocks are unchanged; existing
`.jsonl` files and their format are untouched.

---

## 13. CSV Contract

**Raw export columns (exact, minimal — mirrors `PersonalDataPoint`'s
own fields, `raw` deliberately excluded):**

```
id, source_id, category, timestamp, value, unit, collected_at
```

`raw` is intentionally **excluded** — `PersonalDataPoint`'s own
docstring states it "must never be logged in full at `INFO` level
(only `DEBUG`), since it may contain provider-specific identifiers"
(`personal_data_record.py`); a CSV export is an operator-facing,
`INFO`-equivalent-visibility artifact, so the same restraint applies
by direct extension of that existing rule, not a new EP-095 decision
invented from nothing.

**Report export columns (exact — the minimum stable schema needed to
reconstruct §7's `report` output programmatically):**

```
category, bucket_start, bucket_end, count, sum, avg, min, max, unit
```

`bucket_end` is the bucket's exclusive upper bound (e.g. for a `day`
bucket starting `2026-01-01T00:00:00+00:00`, `bucket_end` is
`2026-01-02T00:00:00+00:00`), included explicitly so a consumer of the
CSV never has to re-derive bucket width from `bucket_start` alone.
`unit` contains the literal string `mixed` when the bucket contains
points of more than one unit (§14) — never a fabricated converted
unit.

**Format decisions (all Python-standard-library, no new dependency):**

- **Module:** `csv.writer` (fixed column order, so `DictWriter`'s
  extra flexibility is not needed).
- **Encoding:** `"utf-8"` for writing (plain, no BOM) — distinct from
  the existing `"utf-8-sig"` used for *reading* operator-supplied
  import CSVs (`import_electricity_csv`), which tolerates a BOM from
  external tools; a file EP-095 itself generates has no such external
  origin to accommodate.
- **Newline handling:** `newline=""` on the `open()` call, per Python's
  own `csv` module documentation, to avoid the extra blank lines the
  `csv` module is documented to otherwise produce on Windows.
- **Delimiter:** `,` (the `csv` module default) — no existing
  convention in this repository uses a different delimiter.
- **Header behavior:** always written, exactly once, as the first row
  — including for the zero-row case (§7).
- **Numeric formatting:** `value`/`sum`/`avg`/`min`/`max` are written
  via plain `str(float_value)` (Python's default `float` repr) — no
  rounding or fixed-decimal formatting is introduced, since
  `PersonalDataPoint.value` itself carries no precision/rounding
  convention to match.
- **Timestamp serialization:** `datetime.isoformat()` — identical to
  the format `_query`'s own console output already uses
  (`point.timestamp.isoformat()`), for consistency across every
  personal_data output surface.
- **Overwrite behavior:** unconditional (§7).

---

## 14. Units and Aggregation Semantics

**Verified this session:** nothing in `PersonalDataPoint`,
`PersonalDataManager`, or any of the three existing sources enforces a
single unit per category — `unit` is a free-form, non-empty string
supplied independently by each `record-reading`/CSV-import call, and
EP-092 explicitly "assigns no meaning to specific category strings"
(`personal_data_record.py` docstring). It is therefore possible,
though not expected in normal operation, for a query result to contain
points with inconsistent units (e.g. a category recorded once in
`"kWh"` and once in `"MWh"`).

**Decision (deterministic, no silent combination, no conversion):**

- `sum`/`avg`/`min`/`max` are **always computed** on the raw numeric
  `value` fields, regardless of unit — EP-095 performs no unit
  conversion of any kind, because no existing repository component
  provides one to reuse and inventing one would be a new domain
  responsibility outside this EP's scope.
- If every point in the queried range shares one unit, that unit is
  displayed once, attached to the aggregate figures, in `report`,
  `chart`, and the CSV `unit` column.
- If the queried range contains **more than one distinct unit**, the
  aggregate figures are still computed and shown (deterministic, never
  silently dropped), but:
  - `report`'s summary/bucket lines display the literal word `mixed`
    in place of a single unit, followed by an explicit list of the
    distinct units actually observed in parentheses (e.g. `Sum: 940
    (mixed: kWh, MWh)`), so the reader is never misled into thinking
    the figure is expressed in one real unit.
  - `chart` labels an affected bucket the same way.
  - The CSV report export's `unit` column contains `mixed` for any
    row spanning more than one unit (§13) — never a fabricated
    converted unit, never silently picking "the first one seen."
- The raw CSV export is unaffected by this — it carries each point's
  own original `unit` column value unchanged (§13), so the source data
  is always fully recoverable regardless of any mixed-unit situation
  in a report/chart view.

---

## 15. Date, Time, and Bucket Semantics

- **Accepted input format:** identical to `query`'s existing
  `_parse_optional_datetime()` — bare `YYYY-MM-DD` or full ISO-8601
  datetime. No new format is introduced.
- **`start`/`end` inclusivity:** both **inclusive**, unchanged from
  `PersonalDataManager.query()`'s existing, verified semantics
  (`timestamp >= start`, `timestamp <= end`). EP-095 introduces no new
  inclusivity rule of its own — it simply passes the parsed values
  through to the existing method.
- **`start == end`:** no special case — the existing inclusive
  semantics already handle it correctly (only points with
  `timestamp == start == end` match, which is the mathematically
  correct and unsurprising result of two inclusive bounds set equal).
- **Timezone handling:** all timestamps in this repository are already
  timezone-aware UTC (`utc_now()`, `_parse_optional_datetime()`'s own
  `tzinfo=timezone.utc` normalization for naive input). EP-095
  introduces **no new timezone infrastructure** — it reuses the
  existing UTC-aware convention exactly. In the defensive edge case of
  encountering an already-stored point whose `timestamp` is naive
  (possible only if a `PersonalDataSource` implementation bypassed the
  existing normalization), bucket assignment treats it as UTC via
  `timestamp.replace(tzinfo=timezone.utc)` before comparison — a
  minimal, local defensive normalization, not a new timezone feature.
- **Week definition:** ISO week (Monday-start), using Python's
  standard-library `date.isocalendar()` — the simplest
  standard-library-only choice, with no repository precedent to
  contradict it (no existing EP defines a week convention).
- **Month bucket:** grouped by the point's `(year, month)` calendar
  pair; `bucket_start` is the first instant of that month at UTC
  midnight, `bucket_end` the first instant of the following month.
- **Chronological ordering:** buckets are always emitted in ascending
  `bucket_start` order for both `report` and `chart`, regardless of
  the order points were collected or stored.

---

## 16. Testing Strategy

**Corrected to match the project's real test infrastructure (§2) —
replaces STEP 1's `pytest`-flavored wording entirely.**

A future `tests/EP095/test_energy_visualization_reporting.py` should
follow the exact structure of `tests/EP093/
test_electricity_gas_monitoring.py`/`tests/EP094/
test_solar_generation_analytics.py`: a single `EnergyVisualization
ReportingTest(BaseTest)` class (or a small number of classes, all
`NAME = "EP095"`, per `TestRegistry`'s own documented support for
multiple classes sharing one `NAME`), built against real, temporary-
directory-backed `Config`/`PersonalDataManager`/
`JsonlPersonalDataProvider` instances — no mocked internals, matching
this project's established convention. It should cover, at STEP 2 (not
now):

1. `PersonalDataReportService.aggregate()`: correct sum/avg/min/max
   per bucket for `day`/`week`/`month`, including a bucket-boundary
   edge case and an empty-input case.
2. Mixed-unit aggregation (§14): a fixture with two distinct units in
   one queried range produces the `mixed` label and the correct
   underlying arithmetic, never a fabricated unit.
3. `write_raw_csv()`/`write_report_csv()`: correct header/row output
   for both CSV shapes (§13), verified via a real temporary-file
   round-trip (write, then re-read and compare) — including the
   zero-row (header-only) case, and a `PersonalDataReportError` on an
   unwritable/missing-directory path.
4. `render_ascii_chart()`: correct row count/ordering for a known
   bucketed series; the "(empty)" message for an empty series.
5. `PersonalDataModule`'s three new actions end-to-end, through a real
   `PersonalDataManager` + `JsonlPersonalDataProvider`: the
   already-collected-but-now-disallowed-category case (§11's corrected
   consent behavior — data still returned, matching `query`); an
   invalid `bucket`/`mode` value; an invalid start/end; an unwritable
   export path; the subsystem-disabled case.
6. Architecture-compliance checks mirroring EP-093's own suite's item
   6: `personal_data_report_service.py` never imports
   `PersonalDataManager`/`PersonalDataProvider`/
   `PersonalDataPersistence`/`PersonalDataRegistry`; `CommandResult` is
   constructed only in `personal_data_module.py`.
7. Regression: **run `test EP092`, `test EP093`, `test EP094`** (via
   `TestRunner`/the `test` CommandModule — not `pytest`) to confirm
   zero behavioral change to existing actions.
8. STEP 2 must add `import
   tests.EP095.test_energy_visualization_reporting` to
   `src/modules/test_module.py` (§5, §8, §9) — without it, `test EP095`
   would raise `ValueError("Unknown test suite: EP095")` from
   `TestRunner.run()`, since registration happens only on import.

---

## 17. Acceptance Criteria

**Rewritten at STEP 1.1 to be objective, deterministic, and
executable against the project's real test infrastructure.**

1. `personal_data report <category> [start] [end] day|week|month`
   returns count/sum/avg/min/max matching a hand-computed value
   against a known fixture, for all three existing categories, for
   each of `day`/`week`/`month` bucketing.
2. A category with zero collected points, or a range with no matching
   points, produces the `"(empty)"` `CommandResult(success=True, ...)`
   form for `report` and `chart` — never a failure, never an
   exception.
3. `personal_data export <category> <path> [start] [end] raw`
   produces a CSV at `<path>` with exactly the §13 raw-export header
   and one row per point an equivalent `query()` call would return, in
   the same order.
4. `personal_data export <category> <path> [start] [end] report`
   produces a CSV with exactly the §13 report-export header and one
   row per non-empty bucket an equivalent `report` call would show.
5. `personal_data chart <category> [start] [end] day|week|month`
   prints one row per non-empty bucket in ascending chronological
   order, with bar lengths proportional to each bucket's `sum` within
   the §7 scaling rule.
6. A category never removed from `personal_data.enabled_categories`
   after collecting data, then later removed, still returns that
   historically collected data to `report`/`export`/`chart`, matching
   `query`'s existing behavior exactly (§11) — this is a required, not
   merely tolerated, outcome.
7. `personal_data.enabled: false` makes `report`/`chart` return
   `"(empty)"` and `export` write a header-only, zero-row CSV.
8. An invalid `start`/`end` argument is rejected with the exact
   message `"start/end must be ISO-8601 dates or datetimes."` before
   any query is executed.
9. An invalid `bucket` value is rejected with the exact message
   `"bucket must be one of: day, week, month."`.
10. An invalid `mode` value (`export`) is rejected with the exact
    message `"mode must be one of: raw, report."`.
11. An `export` path whose parent directory does not exist is rejected
    with `"Cannot write to '<path>': directory does not exist."` and
    no partial file is left behind.
12. A queried range containing more than one distinct `unit` produces
    the `mixed` label (§14) in `report`, `chart`, and the report-mode
    CSV's `unit` column, with the underlying arithmetic still computed
    correctly on raw values — verified against a fixture with two
    known units.
13. A Windows-style export path containing spaces (e.g. `"D:\AI
    Workspace\jarvis\exports\file.csv"`) is accepted and written
    correctly, verified by a real temporary-directory test using such
    a path.
14. `test EP092`, `test EP093`, `test EP094` (via `TestRunner`) all
    pass unmodified after EP-095's changes land, and `test EP095`
    (once `src/modules/test_module.py`'s import is added at STEP 2)
    runs and passes.
15. `personal_data_report_service.py` contains no import of
    `PersonalDataManager`, `PersonalDataProvider`,
    `PersonalDataPersistence`, or `PersonalDataRegistry` (a static,
    grep-able architecture-compliance check, mirroring EP-093's own
    test suite item 6).
16. No new entry appears in `requirements.txt`.

---

## 18. Dependencies, Risks, Non-Goals, Implementation Boundary

**Dependencies (unchanged from STEP 1):** EP-092/093/094 complete, no
active dependency, no blocker — `JARVIS_DECISION_REQUIRED_ARCHITECTURE_
RESOLUTION.md` Decision 7 re-confirmed this session.

**Risks (updated):**

- Bucketing edge cases (§14's mixed-unit handling, and week/month
  boundary arithmetic) — mitigated by the explicit test cases in §16.
- CSV export on Windows paths with spaces — mitigated by exclusive use
  of `pathlib.Path` and a dedicated test case (§17 item 13).
- Scope creep toward EP-096's forecasting territory — bounded by §5/§6.
- `personal_data_module.py` growing large: three more actions bring
  its action count to nine; if STEP 2 finds the file unwieldy, moving
  `report`/`export`/`chart`'s argument-parsing (not their underlying
  logic, which already lives in `PersonalDataReportService`) into a
  small helper is a reasonable STEP 2 implementation choice, not a
  STEP 1.1 architectural change — this mirrors the risk already
  flagged for `_CATEGORY_HANDLERS` by `EP093-AUDIT-004`.
- **New at STEP 1.1:** forgetting the `src/modules/test_module.py`
  import addition (§5, §8, §16 item 8) would leave EP-095's own test
  suite unreachable via `test EP095` even if the suite file itself is
  written correctly — flagged explicitly so STEP 2 does not silently
  miss it the way STEP 1 initially did.

**Non-Goals (unchanged from STEP 1):** no plotting/charting
third-party dependency; no forecasting/anomaly detection; no
cross-category recommendation; no new external data source or
credential handling; no capability-governance wiring or enforcement of
any kind.

**Implementation Boundary:**

**STEP 1 + STEP 1.1 (this document) — design only.** No code, test, or
configuration file has been created or modified in the course of
producing or refining this document. `src/services/
personal_data_report_service.py` does not yet exist;
`src/modules/personal_data_module.py` and `src/modules/test_module.py`
have not been touched.

**Future STEP 2 (implementation, not performed here)** creates
`src/services/personal_data_report_service.py`, extends
`src/modules/personal_data_module.py` with the three new actions per
§7's finalized contract, adds the one import line to
`src/modules/test_module.py` (§5/§8), and adds
`tests/EP095/test_energy_visualization_reporting.py` per §16.

**Future STEP 3 (independent architecture audit)** and **STEP 4
(documentation synchronization)** are unchanged in scope from STEP 1's
own description and are not performed here.
