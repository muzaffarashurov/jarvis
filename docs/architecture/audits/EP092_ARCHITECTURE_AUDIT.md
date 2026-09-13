# EP-092 — Independent Architecture Audit
## Personal Data Collection Framework

STEP 3: Architecture Audit

Status: REMEDIATED — STEP 3 FINAL VERDICT: PASS (see §18 for the
final remediation record; §§1-17 below are preserved unedited as the
original STEP 3 audit and are superseded only where §18 says so)

---

## 1. Scope

This audit independently reviews the EP-092 STEP 2 implementation
against the approved `docs/architecture/designs/EP092_DESIGN.md`
(including its STEP 1 §21 Owner Decision resolution), and against the
project's actual existing architecture and conventions. It does not
accept the STEP 2 report's own claims at face value: every claim below
was independently re-verified against the actual source tree,
including direct, adversarial reproduction of edge cases (path
handling, concurrent collection) rather than trusting the STEP 2 test
suite's assertions alone.

No production code, test, configuration, or design document was
modified to produce this audit. This document is the only file
created in STEP 3. All 12 files created or modified in STEP 2 were
confirmed byte-for-byte unchanged immediately before this audit began.

## 2. References

- `docs/architecture/designs/EP092_DESIGN.md` (full, including the §21
  Owner Decision resolution and the collect_from()/timestamp/value-type
  corrections made after initial approval).
- `src/core/personal_data/__init__.py`
- `src/core/personal_data/personal_data_record.py`
- `src/core/personal_data/personal_data_source.py`
- `src/core/personal_data/personal_data_persistence.py`
- `src/core/personal_data/personal_data_provider.py`
- `src/core/personal_data/personal_data_registry.py`
- `src/core/personal_data/personal_data_manager.py`
- `src/services/personal_data_service.py`
- `tests/EP092/__init__.py`
- `tests/EP092/test_personal_data_collection_framework.py`
- `config/config.yaml` (`personal_data:` block)
- `src/modules/test_module.py` (EP-092 registration import)
- Comparison references: `src/core/knowledge/knowledge_collection.py`,
  `src/core/knowledge/knowledge_manager.py`,
  `src/core/long_term_memory/long_term_record.py`,
  `src/core/long_term_memory/long_term_provider.py`,
  `src/core/memory/memory_persistence.py`,
  `src/services/knowledge_service.py`,
  `src/core/command_router.py`, `src/core/config.py`.

## 3. Implementation Reviewed

Confirmed by direct diff against the pre-EP-092 repository state: EP-092
added exactly 10 new files and additively modified exactly 2 existing
files (`config/config.yaml`, `src/modules/test_module.py`), touching no
other file. Line counts (`wc -l`):

| File | Lines |
|---|---|
| `personal_data_record.py` | 213 |
| `personal_data_source.py` | 71 |
| `personal_data_persistence.py` | 124 |
| `personal_data_provider.py` | 240 |
| `personal_data_registry.py` | 70 |
| `personal_data_manager.py` | 189 |
| `__init__.py` | 66 |
| `personal_data_service.py` | 239 |
| `test_personal_data_collection_framework.py` | 670 |

Architecture as implemented:

```text
PersonalDataService
        |
PersonalDataManager  (PersonalDataCollectionError; no CommandResult)
        |
PersonalDataProvider  (abstract: store/exists/query/stats)
        |
JsonlPersonalDataProvider  (sole implementation; owns dedup-key index)
        |
PersonalDataPersistence  (raw JSONL append/read only)
        |
data/database/personal_data/<category>.jsonl
```

This matches the approved layering exactly (Section 4).

## 4. STEP 1 Compliance

Verified item by item, against actual source, not the STEP 2 report:

| Requirement (EP-092 STEP 1 design) | Verified against | Result |
|---|---|---|
| `PersonalDataPoint`: `value: float`, non-`bool`, no union type | `personal_data_record.py:_parse_value` — rejects `bool` explicitly, rejects non-`int`/`float` | **PASS** |
| `timestamp` vs `collected_at`: distinct, dedup excludes `collected_at` | `personal_data_record.py:dedup_key()` returns `(source_id, category, timestamp)` only; independently reproduced (Section 8) | **PASS** |
| `PersonalDataSource.collect()`: empty list = nothing new, raise = failure, never swallowed | `personal_data_source.py` docstring and `PersonalDataManager.collect_from()`'s `except Exception` boundary | **PASS** |
| `PersonalDataManager.collect_from(source_id) -> int`; raises `PersonalDataCollectionError`; never returns/raises `CommandResult` | `personal_data_manager.py` — confirmed by AST-based test and independently by `grep`; no `CommandResult` import or reference anywhere in the file | **PASS** |
| `PersonalDataService` is the sole `CommandResult` constructor | `personal_data_service.py` — every `CommandResult(...)` call site is in this file; `personal_data_manager.py` has zero | **PASS** |
| Persistence: Option B (dedicated JSONL), Option A (Knowledge Base) rejected | No import of `src.core.knowledge` or `src.services.knowledge_service` anywhere under `src/core/personal_data/` or `src/services/personal_data_service.py` (confirmed by `grep -rl` across the whole repo — zero hits outside the design doc) | **PASS** |
| Dedup-index rebuilt from disk on provider initialization, keys only (not full points) | `JsonlPersonalDataProvider.__init__` -> `_rebuild_dedup_index()` -> `_extract_dedup_key()`, which parses only `source_id`/`category`/`timestamp` per line, never constructs a `PersonalDataPoint`; independently reproduced across a simulated restart (Section 8) | **PASS** |
| Manager never performs file I/O or knows about JSONL/paths | `personal_data_manager.py` has no `pathlib`/`open`/`json` import | **PASS** |
| Consent gate: category not in `enabled_categories` is skipped, not an error | `collect_from()`'s `skipped_consent` branch; reproduced by test and independently | **PASS** |
| Duplicate points skipped, not an error | `collect_from()`'s `skipped_duplicate` branch via `provider.exists()` | **PASS** |
| One illustrative source, test-support only, never a real integration | `_FixturePersonalDataSource` lives only in `tests/EP092/test_personal_data_collection_framework.py`; no production file references it | **PASS** |
| `personal_data:` config block additive only | `config/config.yaml` diff shows a pure insertion; every pre-existing key/block byte-identical | **PASS** |

No STEP 1 requirement was found violated. Two implementation details go
beyond STEP 1's illustrative code sketch (§13) without contradicting
it — see Finding EP092-AUDIT-003.

## 5. Architecture / Layering Review

Cross-module import graph, obtained by direct inspection (not
assumption):

```text
personal_data_record.py        -> (none; leaf)
personal_data_source.py        -> personal_data_record
personal_data_persistence.py   -> src.core.config (leaf w.r.t. package)
personal_data_provider.py      -> src.core.config, personal_data_persistence, personal_data_record
personal_data_registry.py      -> personal_data_source
personal_data_manager.py       -> personal_data_provider, personal_data_record, personal_data_registry, personal_data_source
personal_data_service.py       -> src.core.command_router, src.core.config, personal_data_manager,
                                   personal_data_provider (JsonlPersonalDataProvider only),
                                   personal_data_record, personal_data_registry, personal_data_source
```

**PASS.** No cycle exists. No lower layer imports a higher layer:
`personal_data_persistence.py` never imports `personal_data_provider.py`
or anything above it; `personal_data_provider.py` never imports
`personal_data_manager.py` or `personal_data_service.py`;
`personal_data_manager.py` never imports `personal_data_service.py`.
The one place a higher layer reaches past the immediately-adjacent
abstraction (`personal_data_service.py` importing the concrete
`JsonlPersonalDataProvider`, not just the abstract `PersonalDataProvider`)
is required to construct the default instance and mirrors
`KnowledgeService._build_default_manager` instantiating
`KnowledgeCollectionProvider` directly — an established, not novel,
pattern in this codebase.

No dependency-inversion violation, circular dependency, or hidden
coupling was found.

## 6. Responsibility Review

| Component | Assigned responsibility (STEP 1) | Verified actual responsibility |
|---|---|---|
| `PersonalDataPersistence` | Raw JSONL file I/O only, no domain knowledge | Confirmed: operates on pre-serialized strings; no `PersonalDataPoint` import; no dedup/consent logic |
| `JsonlPersonalDataProvider` | Serialization, dedup-index bookkeeping, query filtering | Confirmed: owns `_dedup_index`; delegates every byte written/read to `PersonalDataPersistence` |
| `PersonalDataManager` | Consent gate, dedup orchestration, error boundary | Confirmed: no file I/O; no `CommandResult` |
| `PersonalDataService` | Config resolution, `CommandResult` construction | Confirmed: sole `CommandResult` site; sole `Config.get("personal_data...")` call site outside `PersonalDataPersistence`'s own `storage_root` read |
| `PersonalDataRegistry` | Source bookkeeping only | Confirmed: no storage, no scheduling logic |

**PASS**, with one WARNING: see Finding EP092-AUDIT-001 (path
construction) for a case where `PersonalDataPersistence` performs the
file I/O exactly as scoped, but without a validation responsibility
that no other layer performs either — an unassigned, not misassigned,
responsibility. No component performs another's assigned duties, and
no hidden global/module-level mutable state exists anywhere in the
package (confirmed: `_dedup_index` and `_sources` are both
instance-level, initialized in `__init__`, never class-level).

## 7. API / Contracts Review

Every exported symbol in `src/core/personal_data/__init__.py`'s
`__all__` was checked against its actual definition; all ten resolve
correctly and match their documented shape (`PersonalDataPoint`,
`PersonalDataSource`, `PersonalDataProvider`/`PersonalDataProviderError`,
`JsonlPersonalDataProvider`, `PersonalDataPersistence`,
`PersonalDataRegistry`/`PersonalDataRegistryError`,
`PersonalDataManager`/`PersonalDataCollectionError`).

`PersonalDataProvider.exists()`'s method signature
(`exists(self, source_id: str, category: str, timestamp: datetime) -> bool`)
matches STEP 1 §13 exactly. `store()`/`query()`/`stats()` likewise
match.

**WARNING (Finding EP092-AUDIT-003, LOW):** `PersonalDataManager`
exposes `register_source()`, `source_ids()`, `is_source_registered()`,
`stats()`, and `is_category_enabled()` — none of which appear in STEP
1 §13's contract sketch, which showed only `collect_from()` and
`query()`. These are legitimate, necessary additions (without them,
`PersonalDataService` would have to reach into
`PersonalDataManager`'s private `_registry`/`_provider` attributes to
register sources or report status, breaking encapsulation), but they
are an undocumented API surface expansion relative to the STEP 1
sketch.

`PersonalDataService`'s public methods
(`register_source`, `collect`, `query`, `status`) all return the
documented types (`CommandResult`, `CommandResult`,
`list[PersonalDataPoint]`, `PersonalDataStatus`) and were exercised
directly, not only through the STEP 2 test suite (Section 13).

## 8. Error-Handling Review (Independent Reproduction)

Re-verified directly, not only via the STEP 2 suite:

- **Unknown source id.** `manager.collect_from("does-not-exist")`
  raises `PersonalDataCollectionError` — reproduced directly.
- **Source exception.** A source whose `collect()` raises
  `RuntimeError` causes `collect_from()` to raise
  `PersonalDataCollectionError` wrapping it, and `PersonalDataService
  .collect()` converts that into `CommandResult(success=False, ...)`
  — reproduced directly through both layers.
- **Provider store failure.** Pointing `personal_data.storage_root` at
  a path already occupied by a regular file (so `mkdir()` fails)
  causes `JsonlPersonalDataProvider.store()` to raise
  `PersonalDataProviderError`, which `collect_from()` re-raises as
  `PersonalDataCollectionError` — reproduced directly.
- **Malformed persisted line.** A hand-written non-JSON line in a
  `.jsonl` file is skipped (logged at `ERROR`) both during dedup-index
  rebuild and during `query()`, without aborting either — reproduced
  directly with a mixed valid/invalid file.
- **Empty collection.** A source returning `[]` yields
  `collect_from() == 0`, no error — reproduced directly.
- **Duplicate record.** Re-collecting an identical point yields `0` on
  the second call, `1` on the first — reproduced directly.
- **Consent-gate rejection.** A point in a non-enabled category is
  dropped, not counted, not an error — reproduced directly.
- **Disabled subsystem.** With `personal_data.enabled: false`,
  `PersonalDataService.register_source()`/`collect()` both return
  `CommandResult(success=False, ...)`, and `query()`/`status()` return
  empty/zeroed results rather than raising — reproduced directly.

**PASS.** Every documented error path in STEP 1 §16 behaves exactly as
specified, independently reproduced rather than assumed from the
existing test suite.

## 9. Persistence / Data-Integrity Review

- **Append-only.** `PersonalDataPersistence.append_line()` always opens
  in `"a"` mode; no code path anywhere in the package opens a
  `.jsonl` file for writing/truncation (`"w"`) — confirmed by `grep`.
- **Serialization/deserialization round trip.** `PersonalDataPoint.
  to_dict()`/`from_dict()` round-trips exactly, including both
  `timestamp` and `collected_at` independently — reproduced directly.
- **Ordering.** `query()` explicitly sorts by `timestamp` before
  returning, so on-disk insertion order never leaks into caller-visible
  ordering — reproduced with out-of-order inserts.
- **Dedup-index rebuild after restart.** A point stored by one
  `JsonlPersonalDataProvider` instance is correctly seen by a second,
  freshly-constructed instance pointed at the same `storage_root` (a
  simulated process restart) — reproduced directly, matching STEP 1
  §14's explicit requirement.
- **Missing-file / empty-storage-root behavior.** `read_lines()` for a
  never-collected category yields nothing; `known_categories()` on an
  empty storage root returns `[]` — both reproduced directly, no
  exception in either case.
- **Encoding.** All reads/writes explicitly use `encoding="utf-8"`,
  consistent throughout.

**FINDING (WARNING, HIGH — EP092-AUDIT-001): Unsanitized `category`
used directly as a filesystem path component.**

- **File/section:** `src/core/personal_data/personal_data_persistence.py`,
  `category_path()` (line 54): `self.storage_root() / f"{category}.jsonl"`.
- **Problem:** `category` is never validated against path separators
  or `..` traversal sequences anywhere in the call chain
  (`PersonalDataPoint.__post_init__` only checks non-emptiness;
  `PersonalDataManager`/`JsonlPersonalDataProvider` perform no
  additional validation). `category` originates from
  `PersonalDataSource.category` — a property EP-093/094/097 will each
  implement, potentially deriving it from external configuration or
  API data.
- **Reproduction:** Constructing `PersonalDataPersistence` with a
  configured `storage_root` and calling
  `append_line("../../escaped", '{"x": 1}')` writes a file at
  `<parent-of-storage_root's-parent>/escaped.jsonl`, fully outside the
  configured storage root. Independently reproduced in this audit
  (see command output archived alongside this review) — a real,
  triggerable path-traversal write, not a theoretical concern.
- **Why it matters:** This is exactly the "untrusted input" scenario
  STEP 1 §15 flags for `raw`/`value`/`unit` (validate types, never
  trust the source blindly), but no equivalent validation exists for
  `category`, which is used as a filesystem path component — a more
  dangerous use of untrusted data than the payload fields STEP 1
  explicitly called out.
- **Relationship to STEP 1:** Not an explicit violation — STEP 1 never
  specified category-string validation — but it is a gap in the
  "untrusted input" principle STEP 1 §15 establishes for this exact
  package.
- **Current reachability:** Not reachable through any code currently
  shipped in EP-092 itself (the only source in existence,
  `_FixturePersonalDataSource`, is test-only and fully trusted). It
  becomes reachable the moment EP-093/094/097 register a real source
  whose `category` is not a fixed, developer-chosen literal.
- **Recommended action (not implemented, per STEP 3 rules):**
  Validate/sanitize `category` (e.g. reject path separators, `..`, or
  restrict to a safe character set) at the earliest point it enters
  the system — either in `PersonalDataPoint.__post_init__` or in
  `PersonalDataPersistence.category_path()` — before any EP-093+
  source is wired in. This is an Owner Decision on where the
  validation belongs, not an architecture-mandated single answer.

**FINDING (WARNING, MEDIUM — EP092-AUDIT-002): No concurrency guard
around the check-then-act dedup sequence.**

- **File/section:** `src/core/personal_data/personal_data_manager.py`,
  `collect_from()` (line 73): the `provider.exists(...)` check and the
  subsequent `provider.store(point)` call are not atomic with respect
  to each other, and neither `PersonalDataManager` nor
  `JsonlPersonalDataProvider` holds any lock.
- **Problem:** Two concurrent calls to `collect_from()` for the same
  source (e.g. a manual `personal_data collect` invocation overlapping
  a Scheduler tick, or two sources racing on the same category/
  timestamp) can both observe `exists() == False` before either has
  called `store()`, resulting in duplicate points written to disk for
  what STEP 1 defines as a single logical observation.
- **Reproduction:** Independently reproduced in this audit by
  widening the check-then-act window (monkeypatching `exists()` with a
  short sleep to simulate realistic I/O latency) and issuing 5
  concurrent `collect_from()` calls for an identical point from 5
  threads: all 5 passed the dedup check and all 5 were stored,
  yielding 5 duplicate lines on disk instead of 1. Without the
  artificial delay, the race did not reproduce in quick succession
  under CPython's GIL scheduling in this run — the gap is real and
  structural, not merely a timing artifact of one test run, but its
  default-timing reachability is narrow.
- **Why it matters:** `KnowledgeCollection` (EP-024), the comparison
  point this design was evaluated against in STEP 1 §21, is
  explicitly `RLock`-guarded for exactly this class of concern. No
  equivalent guard exists anywhere in EP-092.
- **Relationship to STEP 1:** STEP 1 did not discuss concurrency for
  EP-092 at all — this is a gap in the design as approved, not a
  deviation from it.
- **Current reachability:** Low under the single-threaded Scheduler
  tick model this project uses today, but real the moment a CLI/service
  call and a Scheduler tick (or two Scheduler jobs on overlapping
  categories) can execute concurrently.
- **Recommended action (not implemented, per STEP 3 rules):** Add a
  lock around the check-then-act sequence, either inside
  `PersonalDataManager.collect_from()` or inside
  `JsonlPersonalDataProvider` itself (mirroring
  `KnowledgeCollection`'s `RLock`). This is an Owner Decision on
  placement, not an architecture-mandated single answer.

No other data-integrity gap was found. File creation, missing-file
handling, and path/configuration resolution otherwise behave exactly
as documented.

## 10. Configuration Review

- **Actually consumed.** `personal_data.enabled` and `personal_data
  .enabled_categories` are read exclusively by
  `PersonalDataService`; `personal_data.storage_root` is read
  exclusively by `PersonalDataPersistence`. No dead/unread key exists
  in the added block — confirmed by cross-referencing every key in
  `config/config.yaml`'s new block against every `config.get(...)`
  call in the two files.
- **Validated/handled.** `enabled_categories` defensively falls back
  to an empty `frozenset` if misconfigured as a non-list (`_enabled_
  categories()` / `_build_default_manager()` both check
  `isinstance(configured, list)`), matching this project's existing
  defensive-config-parsing convention (e.g. `KnowledgeService
  ._build_default_manager`'s validation of `default_provider`).
- **Consistent with STEP 1.** Matches STEP 1 §21's approved shape
  exactly (`enabled`, `enabled_categories`, `storage_root`), with
  `enabled_categories` defaulting to `[]` (opt-in, not opt-out), as
  required.
- **No unnecessary global coupling.** `Config` is passed explicitly to
  every constructor that needs it (`PersonalDataPersistence`,
  `JsonlPersonalDataProvider`, `PersonalDataService`); no module-level
  `Config()` instantiation or global singleton was introduced.
- **Additive only.** Confirmed by diff: every pre-existing line in
  `config/config.yaml` is byte-identical; the new block is a pure
  insertion between `long_term_memory:` and `orchestrator:`.

**PASS.**

## 11. Test Architecture Review

- `tests/EP092/__init__.py` exists (empty, matching every other EP's
  convention, e.g. `tests/EP025/__init__.py`).
- `tests/EP092/test_personal_data_collection_framework.py` defines one
  `TestRegistry`-decorated `BaseTest` subclass, `NAME = "EP092"`,
  matching the universal one-file-per-EP convention independently
  confirmed across `tests/EP011`, `tests/EP023`, `tests/EP024`,
  `tests/EP025`, and `tests/EP069_3`.
- `src/modules/test_module.py` was extended with exactly one import
  line (`import tests.EP092.test_personal_data_collection_framework`),
  in the same position/style as every prior EP's registration line.
- **Independently re-executed in this audit** (not merely re-read from
  the STEP 2 report): `PersonalDataCollectionFrameworkTest().run()` ->
  **775 passed / 0 failed / 0 skipped**, fresh in this audit session.
- **Independently re-verified discovery**, not just direct
  instantiation: `TestRunner().run("EP092")` and
  `TestRunner().run("ep092")` (case-insensitivity) both correctly
  locate and execute the suite via `TestRegistry`, exactly as the CLI's
  `test EP092` command would.

Per the governing instructions, the following are explicitly recorded
as **Accepted by Owner** and are not re-litigated as findings:

1. The one import line in `src/modules/test_module.py` for EP-092 test
   registration.
2. The single consolidated `tests/EP092` test file.

No independent architectural or test-quality defect was found in
either of these two areas beyond what the Owner has already accepted.

**PASS.**

## 12. Existing-Project Compatibility

- **Breaking changes:** None. Every pre-EP-092 file outside the two
  additive edits is byte-identical (confirmed by diff against the
  pre-EP-092 tree).
- **Import/naming conflicts:** None. `grep -rl "personal_data"` across
  the entire repository returns only the 12 EP-092 files and the
  design/audit documents — no pre-existing symbol, module, or config
  key collides.
- **Circular imports:** None (Section 5).
- **Changes to existing behavior:** None observed; `Config`,
  `CommandResult`, `KnowledgeService`, `Scheduler`, and every other
  touched-by-reference-only component were read, never modified.
- **Convention violations:** None beyond the two Owner-accepted
  deviations (Section 11) and the API-surface note (Finding
  EP092-AUDIT-003).
- **Note (informational, not a finding):** `src/modules/test_module.py`
  imports every EP's test module unconditionally at module load time;
  a failure in any one import (EP-092's included) would currently
  abort the entire chain. This is a pre-existing architectural
  property of `test_module.py` itself, unrelated to and not
  introduced by EP-092 — every prior EP's registration line carries
  the identical exposure.

**PASS.**

## 13. Verification Results

| Check | Result |
|---|---|
| `python3 -m py_compile` on all 12 files | Clean |
| `python3 -m pyflakes` on all 9 new `.py` files | Clean (no unused imports/undefined names) |
| `tests/EP092` suite, fresh re-run in this audit | 775 passed / 0 failed / 0 skipped |
| `TestRunner().run("EP092")` / `run("ep092")` | Both correctly discover and execute the suite |
| `config/config.yaml` YAML parse + diff | Parses; additive-only confirmed |
| Import-graph extraction (Section 5) | No cycle, no upward dependency |
| Path-traversal reproduction (Finding 1) | Reproduced |
| Concurrency-race reproduction (Finding 2) | Reproduced (with widened window); not reproduced under default GIL timing in a quick unmodified run |
| Full `src.modules.test_module` import chain / broader project suite | **ENVIRONMENT** — blocked by pre-existing missing third-party dependencies (`telegram`, likely others) required by `src/bootstrap.py`, unrelated to EP-092. Identical limitation encountered and documented during STEP 2; unchanged in this audit. |

No **PRE-EXISTING** (unrelated existing defect) issue was newly
discovered in the audited files.

## 14. Findings

### EP092-AUDIT-001 — Unsanitized `category` used as a filesystem path component (WARNING, HIGH)

See Section 9 for full evidence, reproduction, and recommendation.

### EP092-AUDIT-002 — No concurrency guard around check-then-act deduplication (WARNING, MEDIUM)

See Section 9 for full evidence, reproduction, and recommendation.

### EP092-AUDIT-003 — `PersonalDataManager` API surface exceeds STEP 1 §13's contract sketch (WARNING, LOW)

See Section 7. `register_source()`, `source_ids()`,
`is_source_registered()`, `stats()`, `is_category_enabled()` are
legitimate, encapsulation-preserving additions, not a scope violation,
but were not documented in STEP 1 and should be reflected in the
design record for future EPs (EP-093+) that will call them.

## 15. Finding Classification Summary

| ID | Classification | Severity | Blocking? |
|---|---|---|---|
| EP092-AUDIT-001 | WARNING | HIGH (currently unreachable — no real source exists yet) | No |
| EP092-AUDIT-002 | WARNING | MEDIUM (narrow default reachability, structurally real) | No |
| EP092-AUDIT-003 | WARNING | LOW (documentation/API-surface only) | No |

Zero FAIL findings. Zero PRE-EXISTING findings attributable to the
audited files. One ENVIRONMENT limitation (Section 13), identical to
the one already documented in STEP 2, not new to this audit.

## 16. Overall Verdict

**PASS WITH WARNINGS.**

The implementation matches the approved STEP 1 design exactly on
every checked requirement (Section 4): correct layering and dependency
direction with no cycle or inversion (Section 5), correctly separated
responsibilities (Section 6), contracts matching STEP 1's signatures
(Section 7), every documented error path independently reproduced and
correct (Section 8), correct append-only/round-trip/ordering/restart-
recovery persistence behavior (Section 9), fully-consumed and
additive-only configuration (Section 10), and both Owner-accepted test
conventions correctly integrated and independently re-verified working
end to end (Section 11) — 775/775 assertions passing, fresh in this
audit, with `test EP092` confirmed to discover and execute the suite
exactly as every other EP's suite is discovered.

The three findings above are real but narrow. EP092-AUDIT-001 (path
traversal via an unsanitized `category` value) is the most significant:
it is a genuine, reproduced defect in principle, but is not reachable
through any code EP-092 itself ships — it becomes a live concern only
once EP-093/094/097 register a real, externally-influenced source, so
it should be resolved before that happens rather than being treated as
blocking EP-092's own acceptance now. EP092-AUDIT-002 (concurrency) is
a real, reproduced structural gap with narrow reachability under this
project's current single-threaded Scheduler model. EP092-AUDIT-003 is
a documentation/API-surface note, not a defect. None of the three
contradicts an explicit STEP 1 requirement, breaks a protected
boundary, or regresses any existing subsystem.

## 17. Recommended Follow-Up

Not implemented in this audit, per STEP 3 rules. For Owner
consideration ahead of EP-093 (the first EP to register a real
source):

1. Decide where `category` validation belongs (Finding
   EP092-AUDIT-001) and schedule it before EP-093/094/097 wire in a
   real source whose `category` is not a fixed literal.
2. Decide whether to add a lock around `collect_from()`'s
   check-then-act dedup sequence (Finding EP092-AUDIT-002), and at
   which layer (`PersonalDataManager` vs. `JsonlPersonalDataProvider`).
3. Fold `register_source()`/`source_ids()`/`is_source_registered()`/
   `stats()`/`is_category_enabled()` into the design record (Finding
   EP092-AUDIT-003) so EP-093+ authors know they exist without reading
   the implementation directly.

None of the above is required before STEP 4; all three are Owner
Decisions on scope and timing, not architecture-mandated blockers.

---

## 18. STEP 3 Remediation & Final Re-Audit Addendum

This section is appended after the original audit above (§§1-17,
preserved unedited as the historical record of what was originally
found). It documents what changed since, and records the final,
independently-verified STEP 3 verdict. Where this section's findings
differ from §§14-17 above, this section is authoritative.

### 18.1 Remediation History

| Finding | Original severity (§14-15) | Remediation | Result |
|---|---|---|---|
| EP092-AUDIT-001 — unsanitized `category` used as a filesystem path component | WARNING, HIGH | `PersonalDataPersistence.category_path()` now validates every category against an allowlist (`^[A-Za-z0-9_-]+$`) before it is ever turned into a path, applied identically on both the write (`append_line`) and read (`read_lines`/`query`) directions. Rejects path separators, `..`, absolute paths, and any other traversal form by construction. | **FIXED** — independently re-verified (§18.2) |
| EP092-AUDIT-002 — no concurrency guard around check-then-act deduplication | WARNING, MEDIUM | `JsonlPersonalDataProvider` gained a per-instance `threading.Lock` and a new atomic `PersonalDataProvider.store_if_new(point) -> bool` method that performs the existence check and the store under one lock acquisition. `PersonalDataManager.collect_from()` now calls only `store_if_new()` — the separate `exists()` + `store()` sequence that created the race is no longer used in any production code path. A failed write never updates the dedup index. | **FIXED** — independently re-verified (§18.2) |
| EP092-AUDIT-004 — provider initialization crashes on an invalid/legacy on-disk category filename (discovered during the first independent STEP 3 re-audit, after AUDIT-001/002 remediation; not present in the original §14 list because it did not exist until the AUDIT-001 fix introduced the stricter validation that made it possible) | Not in original audit; classified MEDIUM when discovered | `JsonlPersonalDataProvider._rebuild_dedup_index()` now catches `PersonalDataPersistenceError` per category during startup, logging and skipping only the offending category rather than aborting construction. Every other, valid category still rebuilds normally. The skip never bypasses `category_path()`'s validation and never treats a skipped category as valid. | **FIXED** — independently re-verified (§18.2) |
| EP092-AUDIT-003 — `PersonalDataManager`/`PersonalDataProvider` API surface exceeds STEP 1 §13's original contract sketch | WARNING, LOW | Re-evaluated after `store_if_new()` was added on top of the originally-flagged `register_source()`/`source_ids()`/`is_source_registered()`/`stats()`/`is_category_enabled()`. Confirmed `store_if_new()` is the *sole* production call path for dedup-safe writes — not a parallel or duplicate mechanism alongside `store()`/`exists()`, which remain as lower-level primitives. | **ACCEPTED** as a necessary, correctly-scoped architectural addition — not a defect. No code change required or made. |

### 18.2 Final Independent Re-Audit Evidence

A fresh, independent STEP 3 re-audit was performed after all three
fixes above, without trusting any prior remediation report's claims.
Reproduced directly against the current source, using disposable
out-of-repo temporary directories only (no repository file was
modified to produce this evidence):

- **AUDIT-001**: 19 traversal/malicious payload variants (`../../escaped`,
  `../escaped`, `..\escaped`, `../../nested/escaped`, absolute paths,
  `C:\Windows\System32`, mixed separators, traversal combined with
  valid-looking prefixes, embedded null bytes, etc.) rejected on both
  the write and read paths; zero files created outside — or even
  inside, for malicious inputs — the configured storage root; valid
  categories (`electricity_v2`, `solar_v2`, `meter-1`, `A1`, …)
  confirmed still working end to end through the full
  `PersonalDataPersistence → JsonlPersonalDataProvider →
  PersonalDataManager → PersonalDataService` stack.
- **AUDIT-002**: a 100-thread stress test against an identical point
  (write artificially slowed) produced exactly 1 stored record with
  valid, uncorrupted JSON; 50 distinct dedup keys stored concurrently
  all succeeded independently; a forced persistence failure left
  `exists()` correctly `False` (dedup index not poisoned) and a
  subsequent retry against working storage succeeded; two independent
  `JsonlPersonalDataProvider` instances (different storage roots) were
  confirmed not to contend on each other's lock (per-instance, not
  global, locking).
- **AUDIT-004**: a storage root containing multiple invalid/legacy
  category files (`a.b.jsonl`, `invalid category.jsonl`) alongside a
  valid category (`electricity.jsonl`, 5 real records), an empty
  valid-named file, and a valid category file with one malformed line
  mixed with one good line — initialization succeeded in every case,
  all valid data loaded correctly, invalid categories excluded and
  logged (never silently normalized to any alternate name), and
  explicit `query()` of an invalid category still raised rather than
  silently returning `[]`.
- **Test suite**: `tests/EP092` — 820 passed / 0 failed / 0 skipped,
  stable across 3 independent fresh runs. `TestRunner().run("EP092")`
  and the case-insensitive `run("ep092")` both confirmed working.
  `py_compile` and `pyflakes` both clean on every EP-092 file.
- **Scope**: a full diff against the pristine pre-EP-092 repository
  state showed exactly the expected accumulated file set (the two
  additive edits to `config/config.yaml` and
  `src/modules/test_module.py`, plus the EP-092 package, service,
  tests, design doc, and this audit doc) — nothing else, at every
  checkpoint across all three remediation rounds.

No new defect was found during the final independent re-audit beyond
the three already listed and fixed above.

### 18.3 Final Verdict

**PASS.**

All findings from the original STEP 3 audit (§§1-17) that represented
genuine defects — EP092-AUDIT-001 (HIGH) and EP092-AUDIT-002 (MEDIUM)
— are fixed and independently re-verified. EP092-AUDIT-004 (MEDIUM),
discovered as a direct consequence of remediating EP092-AUDIT-001, is
likewise fixed and independently re-verified. EP092-AUDIT-003 (LOW) is
not a defect: it is a necessary and correctly-scoped API addition
required to implement EP092-AUDIT-002's fix, accepted as a documented
architectural deviation from STEP 1's original illustrative contract
sketch rather than an unresolved issue. No HIGH or MEDIUM finding
remains open. No new blocking architectural, security, or correctness
defect was discovered at any point during remediation or the final
independent re-audit.

EP-092 is ready for STEP 4.
