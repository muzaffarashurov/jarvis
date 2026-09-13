# EP-092 — Personal Data Collection Framework

STEP 1: Architecture Discovery & Design

Status: DESIGN APPROVED — Owner approved Option B (dedicated
append-only JSONL persistence, §21); ready for STEP 2

---

## 0. Source-of-Truth Note

Section 2 of the calling task requires direct inspection of the
GitHub repository (`github.com/muzaffarashurov/jarvis`, per
`ROADMAP_070_138_REBUILD_PROPOSAL.md` §1) as the primary source of
truth, and instructs this process to STOP with `GITHUB REPOSITORY
ACCESS BLOCKED` if that repository cannot be inspected. No GitHub
connector is available in this session. In its place, the project
owner supplied the repository as an uploaded archive
(`jarvis-main.zip`) alongside the STEP 1 prompt. That archive was
extracted and inspected directly (file listings, `grep`, and full-file
reads against the extracted tree) — every finding below is sourced
from that extracted tree, not from training-data assumptions or from
the historical documentation quoted in Section 3. This substitutes for
live GitHub access; it does not substitute for "read the files
yourself." No file in the extracted tree was modified to produce this
document except the creation of this design document itself.

## 1. Title

EP-092 — Personal Data Collection Framework

## 2. Status

STEP 1 (this document) only. STEP 2 (Implementation & Testing), STEP 3
(Architecture Audit), and STEP 4 (Documentation Synchronization) have
not started. No source, test, configuration, or tracked documentation
file has been modified to produce this document.

## 3. Context

`docs/BACKLOG.md` (§"Personal Intelligence / Energy / Weather
(EP-092–EP-098)") defines EP-092 as:

> EP-092 — Personal Data Collection Framework (MEDIUM). Structured
> ingestion of permitted personal operational data.

`docs/architecture/JARVIS_ROADMAP.md` places EP-092 in "Phase E —
Personal Intelligence / Energy / Weather (planning only)," spanning
EP-092–EP-098:

- EP-093 — Electricity & Gas Monitoring
- EP-094 — Solar Generation Analytics
- EP-095 — Energy Visualization & Reporting
- EP-096 — Energy Forecast & Anomaly Detection
- EP-097 — Weather Intelligence Agent
- EP-098 — Personal Daily/Weekly Recommendation Engine (combines the
  above)

No design document exists for EP-092 today (`docs/architecture/
designs/` runs `EP001`…`EP069_3` plus the roadmap rebuild proposal;
there is no `EP070`–`EP091` design and no `EP092_DESIGN.md` prior to
this one), confirming Phase E's "planning only" status by direct
inspection, not just by the roadmap label.

EP-092 is explicitly the **framework** the five EPs behind it
(EP-093–097) will plug into: it must define how "permitted personal
operational data" is modeled, sourced, validated, stored, and queried
in a way that is domain-agnostic (it must not itself know about
electricity, gas, solar, or weather), so that EP-093–097 each supply a
domain-specific `PersonalDataSource` rather than each building its own
ingestion, storage, and scheduling stack.

## 4. Problem Statement

Jarvis has no concept of recurring, external, real-world personal
data today. The closest existing subsystems are:

- **EP-024 Knowledge Base** (`src/core/knowledge/`) — structured
  records the *operator or an agent* writes deliberately, organized
  into named collections, keyed `(collection, key)`, one record per
  key (last-write-wins).
- **EP-025 Long-Term Memory** (`src/core/long_term_memory/`) — a
  thin adapter on top of Knowledge Base for durable, agent-authored
  memories.
- **EP-011 Scheduler** (`src/core/scheduler/`) — runs arbitrary
  command strings on a schedule; has no concept of a data source or a
  collected value.

None of these model **externally observed measurements arriving
repeatedly over time from an outside system** (a utility API, a
solar-inverter API, a weather API, a CSV export, a manual entry) where
every arrival is a new fact to keep, not an update to an existing
key. There is no ingestion contract, no dedup/validation step, no
category taxonomy, and no storage shape suited to append-only
time-series growth. EP-093–097 cannot be started safely without this
foundation existing first — each would otherwise invent its own
incompatible ingestion/storage pattern, which is exactly the
duplication `AI_GENERATION_STANDARD.md` Architecture Rule 3/4 ("never
introduce a second implementation of existing functionality," "never
duplicate infrastructure") forbids.

## 5. Goals

- Define a single, domain-agnostic contract (`PersonalDataSource`) that
  EP-093 (electricity/gas), EP-094 (solar), and EP-097 (weather) can
  each implement without EP-092 knowing anything about any of them.
- Define the one owned data shape (`PersonalDataPoint`) every source
  produces, and the one store/query surface every downstream EP
  (including EP-095 Visualization, EP-096 Forecast, EP-098
  Recommendation) reads from.
- Reuse the existing Scheduler (EP-011) for recurring collection
  instead of inventing a second scheduling mechanism.
- Reuse the existing Config (`src/core/config.py`) / `.env` split for
  all source credentials, per `AI_GENERATION_STANDARD.md`'s
  Configuration Policy ("never hardcode … credentials").
- Establish an explicit **consent boundary**: a category of personal
  data may only be collected if the operator has explicitly enabled it
  in configuration, and collected personal data must not silently
  become reachable by Embedding (EP-021) / Retrieval (EP-020) /
  Semantic Search (EP-026) / RAG (EP-022) without a separate,
  explicit opt-in.
- Persist personal data through a new, narrowly-scoped append-only
  store rather than reusing EP-024 Knowledge Base (as EP-025
  Long-Term Memory did), because time-series data does not fit
  Knowledge Base's one-record-per-key model — Owner-approved as
  Option B (see §10, §21).

## 6. Non-Goals

Per the calling task's "STEP 1 is design only" boundary and per the
EP-092 backlog entry itself, EP-092 does **not**:

- implement electricity, gas, solar, or weather collection — that is
  EP-093/094/097's job; EP-092 supplies the contract they implement
  against, and MAY ship one trivial illustrative/manual source (see
  §12) purely to prove the contract, never a real utility integration;
- implement visualization, reporting, forecasting, anomaly detection,
  or recommendations — EP-095/096/098;
- implement a general-purpose time-series database, analytics engine,
  or dashboard;
- change Knowledge Base, Long-Term Memory, Memory Manager, or
  Scheduler's existing contracts — EP-092 only consumes their existing
  public APIs (`AI_GENERATION_STANDARD.md`'s Existing Code Policy);
- decide the specific external APIs, polling cadences, credentials, or
  units for any real-world data source — those are EP-093/094/097
  decisions;
- introduce embeddings, RAG, or semantic search over personal data —
  explicitly out of scope and, per §15, disabled by default even once
  EP-093–097 exist.

## 7. Repository Discovery — Findings

Direct inspection of the extracted archive (not the historical prose
in `docs/architecture/JARVIS_ROADMAP.md`, which was cross-checked
against and matches these findings):

1. **`src/core/knowledge/knowledge_collection.py`** —
   `KnowledgeCollection.__init__` holds `self._collections:
   dict[str, dict[str, KnowledgeRecord]]` guarded by an `RLock`; it is
   **entirely in-memory**. `store()` is `bucket[record.key] = record`
   — an overwrite, not an append. There is no file/database backing
   inside `KnowledgeCollection` itself.
2. **`src/core/memory/memory_persistence.py`** — the disk-backed
   pattern that *does* exist in this repository: `MemoryPersistence`
   is a separate class (not inside `MemoryStore`) that loads a JSON
   snapshot (`DEFAULT_STORAGE_FILE = "data/database/memory.json"`) at
   startup and periodically calls `MemoryStore.export_snapshot()` to
   rewrite it, gated by `memory.persistent` / `memory.auto_save` /
   `memory.auto_save_interval` in `config/config.yaml`. This
   Store/Persistence split (storage-only class + separate
   load/auto-save class) is called out in the module's own docstring
   as existing "solely to keep both files under
   `AI_GENERATION_STANDARD.md`'s file-size limit."
3. **`src/core/long_term_memory/long_term_provider.py`** — shows the
   established way a new EP piggybacks on Knowledge Base rather than
   building its own storage: `KnowledgeBackedLongTermProvider`
   persists `LongTermRecord` objects as `KnowledgeRecord`s in a
   dedicated collection, talking to `KnowledgeService` only through
   its public `store/load/update/delete/list_records/collection_stats`
   API — "never touching `KnowledgeCollection` or `KnowledgeManager`
   directly." The same file also shows the mirrored adapter direction:
   `LongTermMemoryProvider` adapts a `LongTermMemoryManager` to EP-023's
   `MemoryProvider` interface so it can register with `MemoryManager`
   "with no code change" to `MemoryManager` itself.
4. **`src/core/scheduler/job.py`** — `ScheduleType` already includes
   `MANUAL`, `ONCE`, `INTERVAL`, `DAILY`, `WEEKLY`, `CRON`; a `Job`'s
   `command` is, per the module docstring, "always a raw target
   string, handed unchanged to `ExecutionEngine.run()`" — the
   Scheduler "executes commands only" and has no knowledge of what a
   command does.
5. **`config/config.yaml`** — top-level `paths:` block already defines
   `data_database: "data/database"` (used by `memory.storage_file`)
   alongside `data_input`, `data_output`, `data_cache`; `memory:` and
   `knowledge:` blocks show the established per-subsystem
   `enabled` / `persistent` / `storage_file` / `default_provider`
   shape new subsystem config blocks in this repository follow.
6. **`.env.example`** — every third-party credential (`OPENAI_API_KEY`,
   `OPENROUTER_API_KEY`, `TELEGRAM_*`, `GITHUB_TOKEN`, …) lives here,
   never in `config/config.yaml` or in source — confirmed the pattern
   `AI_GENERATION_STANDARD.md`'s Configuration Policy requires.
7. **`src/services/*.py`** — 30 files, one per subsystem, each named
   `<subsystem>_service.py` (`knowledge_service.py`,
   `long_term_memory_service.py`, `scheduler_service.py`, …).
   `knowledge_service.py` shows the CLI-facing shape: methods return
   `CommandResult` (`src/core/command_router.py`), constructed from
   `Config` plus an optional injected manager
   (`__init__(self, config: Config, manager: KnowledgeManager | None =
   None)`), matching `AI_GENERATION_STANDARD.md`'s Dependency Policy
   ("prefer `InvoiceService(engine)`" over internal instantiation).
8. **`src/testing/base_test.py`** — `BaseTest` is an `ABC` with a
   single abstract `run() -> TestResult` and a fixed set of
   `assert_*` helpers (`assert_true`, `assert_equal`,
   `assert_not_none`, …) feeding a `TestResult`; `tests/` contains one
   directory per EP (`tests/EP052/` … `tests/EP069_3/`), confirming
   the `tests/EP###/` convention the calling task's §17 anticipates.
9. **No existing subsystem models "a measurement from an external,
   real-world system arriving repeatedly over time."** Knowledge Base,
   Long-Term Memory, and Memory Manager are all key-addressed,
   overwrite-semantics stores for facts an agent or operator writes
   deliberately. This is the concrete gap EP-092 fills — confirmed by
   absence, not assumed.

## 8. Architectural Context

Only the layers actually touched:

- **Core infrastructure** — new `src/core/personal_data/` package,
  peer to `src/core/knowledge/` and `src/core/long_term_memory/`.
- **Domain/services** — new `src/services/personal_data_service.py`,
  peer to `knowledge_service.py`.
- **Scheduler layer** — EP-092 registers Jobs with the existing
  Scheduler (EP-011); it does not modify the Scheduler.
- **Configuration** — a new `personal_data:` block in
  `config/config.yaml`, following the `memory:`/`knowledge:` shape.

Layers explicitly **not** touched: Planning, Execution, Workflow,
Agent Framework, Embedding, Retrieval, RAG, Semantic Search, Context
Compression, any Integration/External-provider layer beyond Config,
and any Security/policy layer beyond the consent gate this EP itself
introduces (§15) — none of these exist as EP-092 dependencies per the
backlog, and none were touched during this discovery.

## 9. Dependency Analysis

**REQUIRED**

- `src/core/config.py` (`Config`) — reads `personal_data.*` settings,
  exactly as `KnowledgeService` reads `knowledge.*`.
- `src/core/scheduler/` (EP-011) — recurring collection is scheduled
  Jobs whose `command` targets a new `personal_data.collect` command
  surface; EP-092 depends on Scheduler's existing public job-model,
  not the reverse.
- `src/core/command_router.py` (`CommandResult`) — the CLI-facing
  return type `PersonalDataService` methods must use, matching
  `KnowledgeService`.
- `src/testing/` (`BaseTest`/`TestRegistry`/`TestRunner`) — required
  for `tests/EP092/`.

**DEFERRED (belongs to EP-093/094/097, not EP-092)**

- Any real external HTTP client, utility-provider SDK, or weather API
  client.
- Any unit-conversion or domain-specific validation (kWh, m³, kWp,
  °C, …) beyond the generic `unit: str` field EP-092 defines.

**OUT OF SCOPE**

- Embedding (EP-021), Retrieval (EP-020), RAG (EP-022), Semantic
  Search (EP-026) — see §15; EP-092 has zero import dependency on any
  of them, matching the same "no dependency on Embedding/Retrieval/
  RAG/Semantic Search" disclaimer already present verbatim in
  `long_term_record.py`, `long_term_provider.py`, and
  `knowledge_manager.py`'s own docstrings.
- EP-024 Knowledge Base / `KnowledgeService` — per the approved Owner
  Decision (§21, Option B), EP-092's persistence backend is the
  dedicated `JsonlPersonalDataProvider`, not Knowledge Base. EP-092
  has zero import dependency on `src/core/knowledge/` or
  `src/services/knowledge_service.py`.

## 10. Existing Functionality Analysis

| Existing component | Classification | Reason |
|---|---|---|
| `KnowledgeCollection` / `KnowledgeManager` / `KnowledgeService` | **DO NOT TOUCH** — rejected for EP-092 persistence (Owner Decision, §21: Option A rejected, Option B approved) | One-record-per-key, overwrite-on-store semantics fit agent-authored facts, not an unbounded, append-only measurement history; reusing it either requires embedding a timestamp into every key (workable, but means `KnowledgeCollection`'s fully-in-memory dict holds the *entire* personal-data history for the life of the process — see §10.1) or accepting last-value-only semantics (loses history, unacceptable for time-series). The Owner has approved the dedicated `JsonlPersonalDataProvider` instead (§21). |
| `Scheduler` / `Job` / `JobRegistry` (EP-011) | **REUSE**, unmodified | Already supports `INTERVAL`/`CRON`/`DAILY` schedules and treats `command` as an opaque string; EP-092 only needs to register Jobs whose command routes to `PersonalDataService.collect(source_id)`. No new scheduling primitive is needed. |
| `Config` (`config/config.yaml`, `.env`) | **EXTEND** | Add a `personal_data:` block following the `memory:`/`knowledge:` shape; add no new mechanism. |
| `CommandResult` / `command_router.py` | **REUSE**, unmodified | `PersonalDataService` returns `CommandResult` exactly as `KnowledgeService` does. |
| `BaseTest` / `TestRegistry` / `TestRunner` | **REUSE**, unmodified | `tests/EP092/` follows the same pattern as every prior EP's test directory. |
| Embedding / Retrieval / RAG / Semantic Search | **DO NOT TOUCH** | Explicitly out of scope (§6, §15); no import dependency in either direction. |

### 10.1 Why this required an Owner Decision rather than a default "reuse"

`AI_GENERATION_STANDARD.md`'s Existing Code Policy says "always reuse
existing infrastructure … prefer extending existing components over
creating new ones." The literal reading favors reusing Knowledge
Base, the way EP-025 did. But EP-025 reused Knowledge Base to store a
*bounded* number of agent-authored memories, each independently
addressed and independently overwritten/archived. EP-092's data is,
by nature, unbounded and append-only (a smart-meter reading every 15
minutes, indefinitely). Storing that inside `KnowledgeCollection`
means the *entire* history sits in one process's RAM for the life of
the process (per Finding §7.1 — there is no lazy loading or paging
anywhere in `KnowledgeCollection`), growing without bound, with no
existing eviction/retention mechanism. That is a real architectural
cost the "reuse" instinct does not surface on its own, so §21 raised
it explicitly rather than silently picking either side. The Owner has
since reviewed and approved Option B (dedicated JSONL store, §21);
this section is retained as the record of why that decision was
necessary.

## 11. Scope Definition

### IN SCOPE

- `PersonalDataPoint` domain model: a single collected measurement
  (`id: str`, `source_id: str`, `category: str`, `timestamp: datetime`,
  `value: float`, `unit: str`, `raw: dict[str, Any]`,
  `collected_at: datetime`). `timestamp` and `collected_at` are
  distinct and never conflated: `timestamp` is when the measurement
  itself occurred (part of the dedup identity); `collected_at` is
  when Jarvis ingested it (ingestion metadata only, excluded from
  dedup) — see §13/§14 for the full definition.
- `PersonalDataSource` abstract contract every EP-093/094/097 source
  implements: `source_id`, `category`, `collect() ->
  list[PersonalDataPoint]`.
- `PersonalDataRegistry`: register/list/get sources by `source_id`,
  mirroring `KnowledgeProvider` registration in `KnowledgeManager`.
- `PersonalDataManager`: orchestrates one collection cycle for a given
  `source_id` (call `collect()`, validate, dedupe by `(source_id,
  category, timestamp)`, persist, return count), and the read-side
  query surface (`query(category, start, end) ->
  list[PersonalDataPoint]`) every downstream EP (EP-095/096/098)
  reads from.
- A persistence layer implementing the Owner-approved dedicated
  append-only JSONL provider (§21).
- `PersonalDataService` (CLI-facing, `CommandResult`-returning,
  Config-driven, mirrors `KnowledgeService`).
- A `personal_data:` config block (`enabled`, `enabled_categories`,
  storage settings for the approved JSONL provider per §21).
- Scheduler integration: a documented convention for how EP-093/094/
  097 register a recurring collection Job (EP-092 does not itself
  schedule collection for a category that does not exist yet; it only
  defines the convention and, optionally, exercises it with the
  illustrative source in §12).
- One illustrative, non-external `PersonalDataSource` implementation
  (e.g. a manual/CSV-style source) purely to prove the contract
  end-to-end in tests — see §12 boundary.
- Consent gate: a category can only be collected if present in
  `personal_data.enabled_categories`.

### OUT OF SCOPE

- Any electricity, gas, solar, or weather-specific code, units, or API
  clients (EP-093/094/097).
- Visualization, reporting, forecasting, anomaly detection,
  recommendations (EP-095/096/098).
- Embedding/RAG/Semantic Search integration of any kind.
- A general-purpose analytics or dashboard capability.
- Multi-user / multi-tenant data isolation (Jarvis is single-operator
  today across every existing subsystem inspected; EP-092 does not
  introduce a first exception).

### DEFERRED

- Retention/archival policy for very old personal data points (flagged
  as a risk in §16, deferred to whichever of EP-093–096 first produces
  enough volume to need it).
- Export/import of personal data (e.g. to CSV) — natural fit for
  EP-095 Visualization, not EP-092.

### FUTURE INTEGRATION

- EP-093 (Electricity & Gas), EP-094 (Solar) each add one
  `PersonalDataSource` implementation plus their own Scheduler Job.
- EP-095 (Visualization) and EP-096 (Forecast/Anomaly) both read
  through `PersonalDataManager.query()` / `PersonalDataService`,
  never through the persistence layer directly.
- EP-097 (Weather) adds a `PersonalDataSource` implementation even
  though weather is not "personal" in the strict sense — the backlog
  groups it into this phase because EP-098's recommendation engine
  needs weather alongside energy data through the same query surface.
- EP-098 (Recommendation Engine) is the first consumer expected to
  query across multiple categories at once.

## 12. Architectural Design

```
                    ┌─────────────────────────┐
                    │   PersonalDataService    │  (CLI-facing, CommandResult)
                    └────────────┬─────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │   PersonalDataManager     │  (orchestration)
                    │   collect_from() -> int   │  (never does file I/O,
                    │   raises PersonalData-    │   never knows about
                    │   CollectionError on fail │   JSONL/file paths)
                    └───┬───────────────────┬───┘
                        │                   │
          ┌─────────────▼───────┐   ┌───────▼───────────────┐
          │ PersonalDataRegistry │   │  PersonalDataProvider  │  (ABC — abstract
          │  (source lookup)     │   │                        │   storage contract)
          └─────────┬────────────┘   └───────┬────────────────┘
                     │                        │
     ┌───────────────┼──────────┐   ┌─────────▼──────────────────┐
     ▼               ▼          ▼   │ JsonlPersonalDataProvider   │  Approved (§21):
 ManualSource   EP-093 source  EP-094│ (dedup index + query logic)│  sole concrete
 (illustrative)  (future)      (fut.)└─────────┬───────────────────┘  PersonalDataProvider
                                                │
                                      ┌─────────▼──────────────────┐
                                      │  PersonalDataPersistence    │  low-level file
                                      │  (append/read .jsonl lines  │  I/O only — not
                                      │   only; no dedup/query      │  a second
                                      │   logic)                    │  abstraction
                                      └─────────┬───────────────────┘
                                                │
                              data/database/personal_data/<category>.jsonl

                    Scheduler (EP-011, unmodified)
                    Job.command == "personal_data.collect <source_id>"
                    dispatched via ExecutionEngine, as with every
                    other scheduled command.
```

### Components

**`PersonalDataPoint`** (`src/core/personal_data/personal_data_record.py`)

- Purpose: the one owned data shape for a single collected
  measurement.
- Fields and types (see §13 for the full dataclass sketch): `id: str`,
  `source_id: str`, `category: str`, `timestamp: datetime`,
  `value: float`, `unit: str`, `raw: dict[str, Any]`,
  `collected_at: datetime`.
- `timestamp` vs. `collected_at` (distinct, never conflated):
  - `timestamp` — the point in time the *measurement itself* refers
    to (e.g. "the meter reading for 10:00"). Part of the logical
    identity: the dedup key is `(source_id, category, timestamp)`
    (§13, §14).
  - `collected_at` — the point in time *Jarvis received/ingested* the
    point (e.g. "Jarvis polled the API at 10:02 and got the 10:00
    reading"). Pure ingestion metadata; it MUST NOT participate in
    the dedup key, and two calls to `collect()` that both surface the
    same `timestamp` for the same `(source_id, category)` are the
    same point regardless of how their `collected_at` differ.
  - Example: a source reports a meter reading for 10:00, but Jarvis
    receives it at 10:02 → `timestamp = 10:00`, `collected_at = 10:02`.
- Responsibilities: immutable value object; ISO-8601 timestamp
  parsing/serialization, mirroring `long_term_record.py`'s
  `_parse_timestamp()`/`utc_now()` helpers rather than reinventing
  them.
- Inputs: constructed by a `PersonalDataSource`.
- Outputs: consumed by `PersonalDataManager` and every downstream
  reader.
- Dependencies: none beyond the standard library.
- Failure behavior: raises `ValueError`/`TypeError` on malformed
  timestamps or a non-`float` `value`, exactly as
  `long_term_record._parse_timestamp` does for timestamps — never
  silently coerces.
- Security considerations: `raw: dict[str, Any]` (the source's
  original payload) must never be logged in full at `INFO` level, only
  at `DEBUG`, since it may contain provider-specific identifiers.

**`PersonalDataSource`** (`src/core/personal_data/personal_data_source.py`, `ABC`)

- Purpose: the contract EP-093/094/097 implement.
- Responsibilities: expose `source_id: str`, `category: str`,
  `collect(self) -> list[PersonalDataPoint]`.
- Inputs: whatever the concrete source needs (an HTTP client, a file
  path, …) — injected at construction, not read from global state,
  per the Dependency Policy.
- Outputs: a list of `PersonalDataPoint` (empty list, not an
  exception, when there is nothing new).
- Dependencies: none on `PersonalDataManager`/`PersonalDataRegistry`
  (the direction of dependency is manager → source, never reversed).
- Failure behavior: a source-level exception during `collect()` must
  not crash the Scheduler tick and must not be swallowed inside the
  source itself; it propagates out of `collect()` and is caught by
  `PersonalDataManager.collect_from()`, the collection boundary (see
  §13, §16), which converts it into `PersonalDataCollectionError`.
  `PersonalDataSource` implementations never touch `CommandResult` —
  that type belongs to `PersonalDataService` only.
- Security considerations: any credential a concrete source needs must
  come from `Config`/`.env`, never be hardcoded in the source class.

**`PersonalDataRegistry`** (`src/core/personal_data/personal_data_registry.py`)

- Purpose: register/list/get `PersonalDataSource` instances by
  `source_id`.
- Responsibilities: pure registration bookkeeping, no storage, no
  scheduling — mirrors `KnowledgeManager`'s "pure orchestration layer"
  framing (Finding §7's `knowledge_manager.py` docstring) scoped down
  to sources instead of storage providers.
- Failure behavior: duplicate `source_id` registration raises, rather
  than silently overwriting (Single Source Of Truth).

**`PersonalDataProvider`** (`src/core/personal_data/personal_data_provider.py`, `ABC`)

- Purpose: the abstract storage contract used exclusively by
  `PersonalDataManager` — `store(point)`, `query(category, start,
  end) -> list[PersonalDataPoint]`, `exists(source_id, category,
  timestamp) -> bool` (for dedup), `stats() -> dict`.
- Approved concrete implementation (Owner Decision, §21):
  `JsonlPersonalDataProvider` — the sole implementation of this
  contract; owns dedup-index bookkeeping and query filtering, and
  delegates all raw file reads/writes to `PersonalDataPersistence`
  (below). `KnowledgeBackedPersonalDataProvider` (the Knowledge-Base-
  backed alternative considered in §21) was evaluated and rejected —
  it is not implemented.
  - **Dedup-index rebuild on initialization**: `JsonlPersonalDataProvider`
    does not persist its dedup index separately. On construction it
    discovers each category's existing `.jsonl` file (if any) via
    `PersonalDataPersistence`, reads it once, and rebuilds an
    in-memory index containing *only the dedup keys* —
    `set[tuple[str, str, datetime]]` of `(source_id, category,
    timestamp)`, never full `PersonalDataPoint` objects. After that
    one-time rebuild, `exists()` is an in-memory set lookup; `store()`
    appends to both the file (via `PersonalDataPersistence`) and the
    in-memory index. No database and no second cache of full history
    is introduced — the index holds keys only.
  - `query()` does not read the dedup index (which holds keys only,
    not points); it reads and filters the persisted `.jsonl` data
    directly, via `PersonalDataPersistence`, once per call.
  `PersonalDataProvider` remains the abstraction boundary regardless,
  so a second implementation could be added later without touching
  `PersonalDataManager` or anything above it — but none is planned.

**`PersonalDataPersistence`** (`src/core/personal_data/personal_data_persistence.py`)

- Purpose: low-level, narrowly-scoped JSONL file I/O only — append one
  serialized `PersonalDataPoint` line to the correct
  `data/database/personal_data/<category>.jsonl` file, and iterate the
  lines already stored in a category's file. Scoped the same way
  `memory_persistence.py` is scoped to Memory's on-disk snapshot
  mechanics (Finding §7.2), not a general storage framework.
- Responsibilities: directory/file creation, line-append, line-
  iteration under the configured `data/database/personal_data/` root.
  Nothing else — no dedup logic, no query filtering, no knowledge of
  what a "point" means beyond a serialized line.
- Used exclusively by `JsonlPersonalDataProvider` — never called
  directly by `PersonalDataManager`, `PersonalDataService`, or any
  `PersonalDataSource`.
- Not a second storage-provider abstraction: it does not implement
  `PersonalDataProvider` and exposes no `store`/`query`/`exists`/
  `stats` surface. `JsonlPersonalDataProvider` composes it as an
  internal helper; it does not stand beside it as an alternative.
- Dependency direction (single, unambiguous chain): `PersonalDataManager`
  → `PersonalDataProvider` (abstract) → `JsonlPersonalDataProvider`
  (concrete) → `PersonalDataPersistence` (file I/O) → `*.jsonl` files.
  `PersonalDataManager` never performs file I/O directly and never
  knows about JSONL or file paths — it only calls the abstract
  `PersonalDataProvider` contract (§13).

**`PersonalDataManager`** (`src/core/personal_data/personal_data_manager.py`)

- Purpose: orchestration — the only component that calls both
  `PersonalDataRegistry` and `PersonalDataProvider`.
- Responsibilities: `collect_from(source_id) -> int` (count of newly
  stored points; §13), `query(category, start=None, end=None) ->
  list[PersonalDataPoint]`, consent-gate enforcement (§15).
- Failure behavior: `collect_from()` never returns or raises
  `CommandResult` — that type belongs to `PersonalDataService` only.
  It catches any exception from the source's `collect()` or the
  provider's `store()`/`exists()`, and re-raises the single dedicated
  `PersonalDataCollectionError` (§13) so the caller has exactly one
  exception type to handle and so the original failure never escapes
  to crash the Scheduler tick.

**`PersonalDataService`** (`src/services/personal_data_service.py`)

- Purpose: CLI-facing surface, `__init__(self, config: Config,
  manager: PersonalDataManager | None = None)`, matching
  `KnowledgeService`'s constructor shape (Finding §7.7).
- Responsibilities: read `personal_data.*` Config, build the default
  manager/provider if none injected, expose `collect(source_id) ->
  CommandResult`, `list_data(category, ...) -> CommandResult`,
  `status() -> CommandResult`.

### Illustrative source boundary

The one non-external `PersonalDataSource` EP-092 may ship (e.g. a
`ManualEntrySource` reading operator-supplied values, or a
fixture-backed `CsvPersonalDataSource`) exists solely so `tests/EP092/`
can exercise the full collect → dedupe → persist → query path without
a real network dependency. It must not read from, or write to, any
real utility/weather API, and must be clearly marked in its own
docstring as illustrative/test-support only, so a future EP does not
mistake it for a real integration.

## 13. Contracts and Interfaces

```python
# PersonalDataPoint -- the one owned data shape (see §12 for full semantics)
@dataclass(frozen=True)
class PersonalDataPoint:
    id: str
    source_id: str
    category: str
    timestamp: datetime      # when the measurement occurred; part of the dedup key
    value: float              # strongly typed -- see §12/§15; not a union type
    unit: str
    raw: dict[str, Any]
    collected_at: datetime   # when Jarvis ingested it; ingestion metadata only,
                              # excluded from the dedup key (see §14)
```

```python
# PersonalDataSource contract
class PersonalDataSource(ABC):
    source_id: str
    category: str

    @abstractmethod
    def collect(self) -> list[PersonalDataPoint]:
        """Return newly observed points since the last call.

        Returns an empty list when there is nothing new -- this is
        the normal, expected outcome of a call that succeeded but
        found no new data, and is not an error.

        May raise an exception when collection itself fails (e.g. a
        transient network error, an unreachable API, a malformed
        response). A source must let such a failure propagate rather
        than silently swallowing it inside `collect()` -- swallowing
        would hide the failure from the collection boundary below.

        The source is never responsible for containing that failure:
        `PersonalDataManager.collect_from()` is the collection
        boundary. It catches any exception `collect()` raises, so the
        failure never escapes to crash the Scheduler tick, and
        converts it into the zero-new-points / failed-collection
        outcome defined in the error-handling contract (see §16),
        logging it there.
        """
```

```python
# PersonalDataProvider contract (as implemented; store_if_new() was
# added during STEP 3 remediation of EP092-AUDIT-002 -- see §21)
class PersonalDataProvider(ABC):
    @abstractmethod
    def store(self, point: PersonalDataPoint) -> None: ...

    @abstractmethod
    def store_if_new(self, point: PersonalDataPoint) -> bool: ...

    @abstractmethod
    def exists(self, source_id: str, category: str, timestamp: datetime) -> bool: ...

    @abstractmethod
    def query(
        self, category: str, start: datetime | None = None, end: datetime | None = None
    ) -> list[PersonalDataPoint]: ...

    @abstractmethod
    def stats(self) -> dict[str, int]: ...
```

- **`store_if_new(point) -> bool`** (added during STEP 3 remediation,
  finding EP092-AUDIT-002): atomically checks the dedup key and stores
  `point` only if it is not already present, returning `True` if newly
  stored or `False` if it was a duplicate. This is the concurrency-safe
  combination of `exists()` + `store()` -- a caller that performs those
  as two separate calls is exposed to a check-then-act race between
  concurrent callers. `PersonalDataManager.collect_from()` calls only
  `store_if_new()` in production; `store()`/`exists()` remain as
  lower-level primitives (still directly useful, e.g. in tests), not a
  duplicate mechanism. `JsonlPersonalDataProvider` implements this with
  a single per-instance lock held across both the check and the store,
  so two independent provider instances (e.g. different storage roots)
  never contend with each other. On a failed write, the dedup index is
  never updated -- a failed persist is never mistaken for a stored
  point. This addition is recorded as an accepted architectural
  deviation from this section's original contract sketch (STEP 3 audit
  finding EP092-AUDIT-003, resolved as "necessary and correctly
  scoped," not a defect).

```python
# PersonalDataManager -- the manager-level collection contract (single,
# unambiguous, no CommandResult at this layer -- CommandResult belongs to
# PersonalDataService only)
class PersonalDataCollectionError(Exception):
    """Raised by PersonalDataManager.collect_from() when a collection
    cycle fails (source raised, or the provider's store_if_new()
    raised). Never raised for the normal "nothing new" or "duplicate/
    filtered" outcomes -- those simply do not add to the returned count.
    """


class PersonalDataManager:
    def collect_from(self, source_id: str) -> int:
        """Run one collection cycle for `source_id`.

        Returns the number of newly stored points. Points dropped
        because their category is not in `personal_data.
        enabled_categories`, or because `provider.store_if_new(...)`
        reports the point already existed, do NOT contribute to this
        count and are not errors (§16).

        Raises PersonalDataCollectionError if the source's collect()
        raises, or if the provider's store_if_new() raises. Never
        returns or raises CommandResult -- PersonalDataService is the
        only layer that constructs CommandResult, by catching this
        exception at its own boundary (see PersonalDataService below).
        """
```

- **Layering rule (resolves the collect_from()/CommandResult
  ambiguity)**: `PersonalDataManager` is domain/application
  orchestration and speaks only in plain return values
  (`int`) and this one domain exception
  (`PersonalDataCollectionError`); `PersonalDataService` is the
  CLI-facing layer and is the only place `CommandResult` is
  constructed. `PersonalDataService.collect(source_id)` calls
  `PersonalDataManager.collect_from(source_id)`, returns
  `CommandResult(success=True, ...)` with the count on success, and
  catches `PersonalDataCollectionError` to return
  `CommandResult(success=False, ...)` on failure. `CommandResult`
  never appears in `src/core/personal_data/`, only in
  `src/services/personal_data_service.py`.
- Validation rules: `PersonalDataManager.collect_from()` drops (does
  not store, does not count, does not error) any point whose
  `category` is absent from `personal_data.enabled_categories` (§15),
  and any point `provider.store_if_new(...)` reports as already
  present (dedup, keyed on `(source_id, category, timestamp)` —
  `collected_at` is never part of this check, §14).
- **Path-traversal protection (added during STEP 3 remediation,
  finding EP092-AUDIT-001)**: `PersonalDataPersistence.category_path()`
  validates every category against an allowlist
  (`^[A-Za-z0-9_-]+$`) before turning it into a filesystem path,
  applied identically to both the write (`append_line`) and read
  (`read_lines`/`query`) directions, rejecting path separators, `..`,
  and absolute paths by construction. `category` originates from
  `PersonalDataSource.category` (§12), which EP-093/094/097 implement
  and which this design already classified as untrusted input (§15);
  this closes that gap.
- **Invalid/legacy on-disk category handling (added during STEP 3
  remediation, finding EP092-AUDIT-004)**: on initialization,
  `JsonlPersonalDataProvider._rebuild_dedup_index()` processes each
  category discovered by `PersonalDataPersistence.known_categories()`
  independently; if a category's file name fails the validation above
  (e.g. a legacy or externally-placed file predating it), that one
  category is logged and skipped rather than aborting construction,
  and every other, valid category still rebuilds normally. A skipped
  category's data is never silently treated as valid, and explicitly
  querying it still raises.
- Compatibility requirements: all four of `PersonalDataPoint`,
  `PersonalDataSource`, `PersonalDataProvider`, and
  `PersonalDataCollectionError` are new — there is no existing
  interface being changed, so no compatibility constraint applies to
  them directly (see §20 for the config/CLI compatibility angle).

## 14. Data and State

- **Entities**: `PersonalDataPoint` only (§12). No entity relationships
  beyond `(source_id, category)` grouping.
- **Ownership**: `PersonalDataProvider` is the single owner of
  collected personal data (Single Source Of Truth); `PersonalDataManager`
  never caches a second copy beyond what a query briefly returns to
  its caller.
- **Lifecycle**: append-only; points are never updated once stored
  (real-world measurements do not change after the fact). Deletion is
  out of scope for EP-092 (no requirement identified) but the
  provider contract's `stats()` method exists specifically so a future
  EP can build retention/archival on top without changing the
  contract.
- **Persistence requirements**: durable across restarts — provided by
  the Owner-approved `JsonlPersonalDataProvider` (§21). Durability
  does not require an in-memory copy of full history: on
  initialization the provider rebuilds only its dedup-key index by
  reading each category's `.jsonl` file once through
  `PersonalDataPersistence` (§12); `query()` reads persisted data
  directly rather than from that index.
- **Serialization**: ISO-8601 for all timestamps, matching
  `long_term_record.py`'s established convention exactly (Finding
  §7.3) rather than inventing a second timestamp format in the same
  codebase. This applies identically to both `timestamp` and
  `collected_at` (§12, §13) — they use the same format, only their
  meaning differs.
- **Consistency rules**: dedup key is `(source_id, category,
  timestamp)` — `collected_at` is ingestion metadata and is never
  part of this key (§12, §13); two points with the same `timestamp`
  for the same `(source_id, category)` are the same observation even
  if collected at different times. Two sources are never allowed to
  be registered under the same `source_id` (enforced by
  `PersonalDataRegistry`, §12).
- **Migration considerations**: none for STEP 1 — there is no existing
  personal-data state to migrate from.

## 15. Security

- **Credentials**: any future concrete source's API key/token lives in
  `.env` (added to `.env.example` by that EP, not by EP-092), read
  through `Config`, never hardcoded — matching `AI_GENERATION_STANDARD.md`'s
  Configuration Policy and Finding §7.6.
- **Consent boundary**: `personal_data.enabled_categories` in
  `config/config.yaml` is an explicit allowlist; `PersonalDataManager`
  refuses to store (and the illustrative source refuses to be
  collected from) any category not on that list. Default value is an
  empty list — personal data collection is **opt-in per category**,
  not opt-out.
- **No implicit RAG/embedding exposure**: `src/core/personal_data/`
  must carry the same "no dependency on Embedding, Retrieval, RAG,
  Semantic Search" disclaimer already used verbatim in
  `long_term_record.py` / `long_term_provider.py` /
  `knowledge_manager.py` (Finding §7.3), and neither
  `PersonalDataProvider` implementation registers itself as a
  `KnowledgeProvider`/`MemoryProvider` available to those subsystems.
  If EP-098's future recommendation engine needs project-context
  visibility into personal data, that is a distinct, explicit design
  decision for EP-098 to make, not a default this EP grants silently.
- **Untrusted input**: a concrete source's raw API response is
  untrusted input; `PersonalDataPoint` construction must validate
  types (`value: float`, non-empty `unit: str` — §12/§13; no
  `int | float | str | bool | Any` union) and never `eval`/exec
  anything from `raw`.
- **Logging/auditability**: `collect_from()` logs
  `source_id`/`category`/count at `INFO`; the full `raw` payload only
  at `DEBUG` (§12's `PersonalDataPoint` note).
- **Least privilege / sandboxing / filesystem / network access**: not
  applicable to EP-092 itself (it makes no network calls and only
  writes to its own configured `data/database/personal_data/` path,
  per the approved `JsonlPersonalDataProvider`, §21); these become
  relevant to EP-093/094/097's own concrete sources, not to this
  framework.

## 16. Error Handling

| Failure | Detection | System behavior | User-visible behavior | Recovery | Logging |
|---|---|---|---|---|---|
| Source `collect()` raises | `try/except` in `PersonalDataManager.collect_from()` | Caught; `collect_from()` raises `PersonalDataCollectionError` (§13) — never `CommandResult` | `PersonalDataService.collect()` catches `PersonalDataCollectionError` and returns `CommandResult(success=False, message=...)` | Next scheduled tick retries automatically | `ERROR`-level, includes `source_id`, exception message |
| Category not in `enabled_categories` | Checked before persistence, inside `collect_from()` | Point dropped, not stored, not counted, not an error — `collect_from()` still returns normally | `CommandResult` (built from the returned count) notes N points skipped (consent) | Operator adds category to config, re-run | `WARNING`-level once per collection cycle, not per-point |
| Duplicate point (`exists()` true) | Checked before persistence, inside `collect_from()` | Point skipped, not stored, not counted — not an error | Included in "skipped (duplicate)" count reported by the service | None needed — expected/normal | `DEBUG`-level |
| Storage backend unavailable (disk full / provider error) | Exception from `provider.store()` inside `collect_from()` | Caught; `collect_from()` raises `PersonalDataCollectionError`. Already-stored points from the same cycle are unaffected (points are stored one at a time, not batch-committed) | `PersonalDataService.collect()` catches it and returns `CommandResult(success=False, ...)` | Operator resolves underlying storage issue; next tick retries | `ERROR`-level |
| Malformed `PersonalDataPoint` (bad timestamp/non-`float` value) from a source | Raised during construction, inside `collect()` | Propagates out of `collect()`; same handling as "source `collect()` raises" above — caught and re-raised as `PersonalDataCollectionError` | Same | Source implementation bug — requires a source-side fix, not a framework retry | `ERROR`-level, includes offending source |

`PersonalDataManager.collect_from(source_id) -> int` therefore has
exactly two outcomes: a successful return (an `int` count of newly
stored points, which excludes duplicate/filtered points per the two
middle rows above) or a raised `PersonalDataCollectionError` (rows 1,
4, and 5 above). It never returns or raises `CommandResult` — see
§13's layering rule.

Retention/unbounded-growth risk (Finding §10.1) is documented here as
a known architectural risk rather than solved: the approved
`JsonlPersonalDataProvider` (§21) avoids holding the *entire* history
in RAM (Knowledge Base's failure mode), but the on-disk `.jsonl` file
itself still has no rotation, compaction, or retention policy in this
design. No retention policy is defined in EP-092, and this must be
revisited once real collection volume exists (EP-093+).

## 17. Testing Strategy

`tests/EP092/`, following the `tests/EP069_3/`-style convention
(Finding §7.8), all subclassing `BaseTest`:

- **Unit** — `PersonalDataPoint` construction/validation, including
  `value: float` type enforcement and the `timestamp`/`collected_at`
  distinction (§12–§14) (`test_personal_data_record.py`);
  `PersonalDataRegistry` register/duplicate-rejection/lookup
  (`test_personal_data_registry.py`).
- **Contract** — a shared contract-test suite run against the
  approved `JsonlPersonalDataProvider` implementation (and any future
  second implementation, since `PersonalDataProvider` remains the
  abstraction boundary), asserting `store`/`exists`/`query`/`stats`
  behave identically regardless of backend, including that
  `exists()`/dedup keys on `(source_id, category, timestamp)` only —
  never `collected_at` (§14)
  (`test_personal_data_provider_contract.py`).
- **Integration** — full collect → dedupe → persist → query round
  trip using the illustrative source from §12, and a
  provider-restart scenario asserting the dedup index is correctly
  rebuilt from the persisted `.jsonl` files on re-initialization (§12,
  §14) (`test_personal_data_manager_integration.py`).
- **Negative** — collection from a source that raises (asserting
  `collect_from()` raises `PersonalDataCollectionError`, per §13/§16);
  a point in a disabled category; a duplicate point; a malformed
  point (bad timestamp or non-`float` value)
  (`test_personal_data_manager_negative.py`).
- **Regression** — config-driven `enabled_categories` allowlist is
  actually enforced end-to-end through `PersonalDataService`, and
  `PersonalDataService.collect()` correctly converts a raised
  `PersonalDataCollectionError` into `CommandResult(success=False,
  ...)` without ever letting the exception type itself leak into the
  CLI-facing response (`test_personal_data_service.py`).

No production Python file, config file, or existing test is modified
during STEP 1; STEP 2 must implement all of the above.

## 18. File Impact Analysis

| File | Action | Reason |
|---|---|---|
| `docs/architecture/designs/EP092_DESIGN.md` | **CREATE** | This document — the only file this STEP 1 process creates. |
| `src/core/personal_data/__init__.py` | CREATE (STEP 2) | New package, peer to `src/core/knowledge/`. |
| `src/core/personal_data/personal_data_record.py` | CREATE (STEP 2) | `PersonalDataPoint` domain model. |
| `src/core/personal_data/personal_data_source.py` | CREATE (STEP 2) | `PersonalDataSource` contract. |
| `src/core/personal_data/personal_data_provider.py` | CREATE (STEP 2) | `PersonalDataProvider` contract + `JsonlPersonalDataProvider` implementation (approved, §21). |
| `src/core/personal_data/personal_data_registry.py` | CREATE (STEP 2) | Source registration. |
| `src/core/personal_data/personal_data_manager.py` | CREATE (STEP 2) | Orchestration. |
| `src/core/personal_data/personal_data_persistence.py` | CREATE (STEP 2), unconditional | Approved dedicated-store option (§21); mirrors `memory_persistence.py`'s Store/Persistence split. |
| `src/services/personal_data_service.py` | CREATE (STEP 2) | CLI-facing service, peer to `knowledge_service.py`. |
| `config/config.yaml` | MODIFY (STEP 2) | Add `personal_data:` block. |
| `.env.example` | NO CHANGE | No credential exists yet — EP-092 introduces no real external source. |
| `tests/EP092/*.py` | CREATE (STEP 2) | Per §17. |
| `CHANGELOG.md`, `docs/BACKLOG.md`, `docs/RELEASE_NOTES.md`, `docs/architecture/JARVIS_ROADMAP.md` | NO CHANGE in STEP 1 or STEP 2 | Per the established EP-052 pattern (`/topics/recent-work.md`: "EP-052 finalization was documentation-only updates to four tracked files"), these are updated only at STEP 4 Finalization, not during design or implementation. |
| Any Embedding/Retrieval/RAG/Semantic Search file | NO CHANGE | Out of scope (§6, §15). |
| Any Scheduler (`src/core/scheduler/`) file | NO CHANGE | REUSE unmodified (§10). |
| Any Knowledge Base file | NO CHANGE | Knowledge Base is not used as EP-092's persistence backend (Owner Decision, §21: Option A rejected); untouched, and carries no import dependency from EP-092. |

## 19. Parallel Development Safety

```
PARALLEL DEVELOPMENT RISK
Potential overlap: none identified with any in-flight EP.
Affected files: entirely new files under src/core/personal_data/,
  src/services/personal_data_service.py, tests/EP092/; the only
  shared file touched is config/config.yaml, and only via an
  additive new top-level block ("personal_data:"), not an edit to
  any existing block.
Reason: Phase E (EP-092-098) is "planning only" with no prior design
  document (Finding §7's absence check); the only other in-flight
  work visible in this repository is EP-069.x (AI Provider & Tool
  Registry, already COMPLETE per docs/architecture/JARVIS_ROADMAP.md
  "## Current"), which shares no file with this design.
Recommended coordination: if another agent is concurrently adding a
  different new top-level block to config/config.yaml, merge by
  concatenation (both blocks are additive and independent); no other
  coordination is required.
```

The target EP can be safely developed independently.

## 20. Backward Compatibility

- **Existing APIs**: none changed. `KnowledgeService`, `MemoryService`,
  `SchedulerService`, `CommandResult`, and every other existing public
  API are consumed exactly as documented, never modified.
- **Existing CLI behavior**: unaffected — EP-092 only *adds* new
  `personal_data.*` CLI-facing methods; no existing command's
  behavior changes.
- **Existing configuration**: unaffected — `personal_data:` is a new,
  additive top-level key; no existing key in `config/config.yaml` is
  renamed, removed, or repurposed.
- **Existing tests**: unaffected — no existing test file is modified.
- **Existing workflows/data formats**: unaffected — no existing data
  format changes; the new `PersonalDataPoint` format is introduced
  fresh with no predecessor to be compatible with.
- No breaking change is introduced by this design.

## 21. Owner Decision Gate

```
OWNER DECISION — RESOLVED / APPROVED

Decision: Personal-data persistence backend.

APPROVED: Option B — dedicated append-only JSONL persistence.

  PersonalDataManager
          |
  PersonalDataProvider          (abstract storage contract)
          |
  JsonlPersonalDataProvider     (approved concrete provider;
          |                      owns the dedup-key index, rebuilt
          |                      from disk on initialization -- §12)
  PersonalDataPersistence       (low-level JSONL file I/O only;
          |                      not a second provider abstraction)
          |
  data/database/personal_data/<category>.jsonl

  One append-only .jsonl file per category, with a small in-memory
  index of (source_id, category, timestamp) dedup keys only -- never
  full PersonalDataPoint objects, and never `collected_at` (§14) --
  reconstructed by scanning the persisted files once at startup, and
  following the Store/Persistence-class split memory_persistence.py
  already establishes (Finding §7.2). Each category is reconstructed
  independently: a category whose on-disk file name fails the
  path-traversal validation added during STEP 3 remediation (finding
  EP092-AUDIT-004, §13) is logged and skipped without aborting
  construction of the other, valid categories.

REJECTED: Option A — reuse Knowledge Base
(KnowledgeBackedPersonalDataProvider). Knowledge Base is NOT used as
EP-092's persistence backend. EP-092 carries no dependency on
src/core/knowledge/ or src/services/knowledge_service.py.

Reason (structural, not stylistic):
- KnowledgeCollection is an in-memory, key-addressed store.
- Its store semantics are overwrite-per-key.
- Personal data is potentially unbounded historical/time-series data.
- Personal data must preserve individual observations rather than
  overwrite previous observations.
- Reusing Knowledge Base here would be reuse in name only, while
  quietly building an unbounded in-memory time series inside a
  component whose own documentation (Finding §7.1) says it holds no
  such thing.

Scope constraint on the approved backend: the dedicated JSONL
provider must remain narrowly scoped to EP-092 personal-data
persistence. It must not become a general-purpose storage framework,
must not be registered as a `KnowledgeProvider` or `MemoryProvider`,
and must not gain responsibilities beyond store/query/exists/stats
for `PersonalDataPoint` records.

Finality: This decision is final for STEP 2. STEP 2 must implement
Option B and must not reconsider Option A. This decision can only be
changed by a new, explicit Owner Decision issued separately -- it is
not open for silent re-litigation during implementation.

Impact: src/core/personal_data/personal_data_persistence.py is
unconditionally part of STEP 2 (§18). EP-092's import graph carries
no "knowledge" dependency. EP-093-097's own testing later validates
storage against JsonlPersonalDataProvider (via the
PersonalDataProvider contract-test suite, §17). This decision does
not affect PersonalDataSource, PersonalDataRegistry, or
PersonalDataManager's public shape -- EP-093-097 are unaffected by
which persistence backend was chosen.
```

No other issue encountered during this discovery required an
Owner Decision — Scheduler reuse, Config shape, CommandResult return
type, and the `tests/EP###/` convention all follow existing,
unambiguous precedent found by direct inspection (§7), not judgment
calls. No new blocking ambiguity was identified while resolving this
decision.

**Post-approval note (STEP 3 remediation, documentation-only):** three
findings surfaced during the STEP 3 architecture audit after this
design was approved and implemented — EP092-AUDIT-001 (path traversal,
HIGH), EP092-AUDIT-002 (concurrency race, MEDIUM), and EP092-AUDIT-004
(provider-initialization crash on an invalid legacy category, MEDIUM,
discovered as a consequence of the EP092-AUDIT-001 fix). All three
were remediated and independently re-verified fixed; a fourth
(EP092-AUDIT-003, LOW) was re-evaluated and accepted as a necessary,
correctly-scoped API addition rather than a defect. None of the four
reopened or altered the persistence-backend decision above (Option B
remains as approved); full detail is in
`docs/architecture/audits/EP092_ARCHITECTURE_AUDIT.md` §18.

## 22. Design Document

This document — `docs/architecture/designs/EP092_DESIGN.md` — is the
canonical design document for EP-092, following the naming and
directory convention of every prior `EP###_DESIGN.md` file (Finding
§7 / directory listing in §3). It covers EP-092 only; it defines no
scope, decision, or file impact for EP-093–098, each of which requires
its own independent STEP 1 once EP-092 is implemented and approved.

## 23. Quality Gate

### Target correctness

- [x] Target EP matches `TARGET_EP` (`EP-092`)
- [x] Target exists in canonical roadmap (`docs/BACKLOG.md`,
      `docs/architecture/JARVIS_ROADMAP.md`)
- [x] No automatic EP substitution occurred

### Architecture

- [x] Existing architecture inspected (Knowledge Base, Long-Term
      Memory, Memory, Scheduler, Config, Services, Testing — §7)
- [x] Relevant existing functionality identified (§10)
- [x] Dependencies documented (§9)
- [x] Boundaries documented (§8)
- [x] Contracts documented (§13)
- [x] Security considered (§15)
- [x] Error handling considered (§16)
- [x] Testing strategy defined (§17)

### Scope

- [x] IN SCOPE defined (§11)
- [x] OUT OF SCOPE defined (§11)
- [x] DEFERRED defined (§11)
- [x] No unnecessary scope expansion — EP-093–098's domain-specific
      work is explicitly excluded (§6, §11)

### Implementation readiness

- [x] STEP 2 can implement without architectural guessing — the §21
      Owner Decision is resolved and approved (Option B)
- [x] Expected file impact documented (§18)
- [x] Parallel-development risks documented (§19 — none identified)
- [x] Backward compatibility considered (§20 — no breaking change)

### Safety

- [x] No production code implemented
- [x] No tests implemented
- [x] No unrelated refactoring performed
- [x] No unrelated files modified

---

## 24. Final STEP 1 Report

```text
TARGET EP: EP-092
OFFICIAL NAME: Personal Data Collection Framework
STATUS: STEP 1 — APPROVED

DESIGN DOCUMENT:
docs/architecture/designs/EP092_DESIGN.md

OWNER DECISION:
APPROVED — Option B, dedicated append-only JSONL persistence.
Option A (Knowledge Base) is rejected for EP-092 persistence.

SUMMARY:
EP-092 defines the domain-agnostic ingestion framework
(PersonalDataPoint / PersonalDataSource / PersonalDataRegistry /
PersonalDataManager / PersonalDataProvider / PersonalDataService)
that EP-093 (Electricity & Gas), EP-094 (Solar), and EP-097 (Weather)
will each implement one PersonalDataSource against, and that EP-095
(Visualization), EP-096 (Forecast/Anomaly), and EP-098
(Recommendation) will read through. PersonalDataPoint is strongly
typed (value: float, unit: str) with an explicit, non-conflated
timestamp (measurement time, part of the dedup key) vs. collected_at
(ingestion time, excluded from the dedup key) distinction (§12-§14).
PersonalDataManager.collect_from(source_id) -> int is the single
manager-level contract: it returns a count or raises
PersonalDataCollectionError, never CommandResult; only
PersonalDataService constructs CommandResult (§13, §16). It reuses
the existing Scheduler (EP-011) for recurring collection and the
existing Config/.env split for credentials, and introduces a
per-category consent allowlist that keeps personal data out of
Embedding/Retrieval/RAG/Semantic Search by default. Persistence is a
single, unambiguous chain -- PersonalDataManager ->
PersonalDataProvider (abstract) -> JsonlPersonalDataProvider
(approved concrete) -> PersonalDataPersistence (low-level JSONL file
I/O only) -- whose dedup-key index is rebuilt from the persisted
`.jsonl` files on initialization rather than persisted separately
(§12, §21), rather than Knowledge Base: KnowledgeCollection's
overwrite-per-key, fully in-memory model does not fit unbounded
time-series data. This decision is final for STEP 2.

MAIN COMPONENTS:
- PersonalDataPoint (src/core/personal_data/personal_data_record.py)
- PersonalDataSource (src/core/personal_data/personal_data_source.py)
- PersonalDataProvider (src/core/personal_data/personal_data_provider.py)
- PersonalDataRegistry (src/core/personal_data/personal_data_registry.py)
- PersonalDataManager (src/core/personal_data/personal_data_manager.py)
- PersonalDataService (src/services/personal_data_service.py)
- PersonalDataPersistence (src/core/personal_data/personal_data_persistence.py)

DEPENDENCIES:
REQUIRED: Config, Scheduler (EP-011), CommandResult/command_router,
  BaseTest/TestRegistry/TestRunner.
DEFERRED: any real external API client (EP-093/094/097).
OUT OF SCOPE: Embedding, Retrieval, RAG, Semantic Search, Knowledge
  Base / KnowledgeService (rejected as persistence backend, §21).

EXPECTED FILE IMPACT:
CREATE: src/core/personal_data/*.py (7 files: __init__.py,
  personal_data_record.py, personal_data_source.py,
  personal_data_provider.py, personal_data_registry.py,
  personal_data_manager.py, personal_data_persistence.py --
  the last unconditional per §21),
  src/services/personal_data_service.py, tests/EP092/*.py.
MODIFY: config/config.yaml (additive "personal_data:" block only).
NO CHANGE: .env.example, CHANGELOG.md, docs/BACKLOG.md,
  docs/RELEASE_NOTES.md, docs/architecture/JARVIS_ROADMAP.md
  (deferred to STEP 4), Scheduler, Knowledge Base, Memory, Embedding/
  Retrieval/RAG/Semantic Search.

PARALLEL DEVELOPMENT RISK:
None identified. Phase E (EP-092-098) has no prior design document
and no other in-flight EP shares any file this design touches.

BLOCKING DECISIONS:
NONE. The persistence-backend decision (§21) is resolved and
approved. No new blocking architectural ambiguity was identified
while resolving it.

IMPLEMENTATION READINESS:
READY FOR STEP 2

FILES MODIFIED (this task):
- docs/architecture/designs/EP092_DESIGN.md

PRODUCTION CODE:
NOT IMPLEMENTED

TESTS:
NOT IMPLEMENTED

STEP 2:
READY TO BEGIN — but DO NOT BEGIN STEP 2 in this task.
```

```text
STEP 1 COMPLETE AND APPROVED.
No implementation was performed.
STEP 2 may begin once separately instructed by the Owner.
```
