# EP001–EP092 Retrospective Consistency Audit

### Historical verification of current GitHub implementation against existing design documents, architecture audits, tests, and Git history

---

## Audit Record

| Field | Value |
|---|---|
| **Audit type** | Retrospective, read-only consistency audit (NOT a normal STEP 3 execution) |
| **Audit scope** | EP-001 through EP-092 |
| **Audit purpose** | Determine whether the *current* GitHub/repository state is consistent with the *existing, previously-recorded* EP documentation and STEP 3 audit results |
| **Repository** | `muzaffarashurov/jarvis` |
| **Branch** | `main` |
| **Commit examined** | `cbe664cc95f4648584af475752d1e1bb5f5c5b92` (`feat(EP-069.6): capability security provider; docs pending`) |
| **Audit date** | 2026-09-14 |
| **Files modified during audit** | **None** — this report is the only new file produced |
| **Final overall verdict** | **ACTION REQUIRED — MATERIAL DRIFT FOUND** |

> **This was a retrospective, read-only consistency audit.** It did not re-run STEP 1/STEP 2/STEP 3 for any EP, did not implement any new architecture review, and did not fix, refactor, or alter any file other than the creation of this document. Its sole purpose was to check whether the repository, as it exists right now, still matches what its own historical documentation says it contains.

---

## 1. Why This Audit Was Performed

Engineering Packages (EPs) in this repository each go through a documented `STEP 1 (Design) → STEP 2 (Implementation) → STEP 3 (Architecture Audit) → STEP 4 (Documentation Sync)` process, sometimes followed by a `STEP 3.1 (Findings Resolution)` pass. Each completed EP leaves behind a design document, an architecture-audit document, a dedicated test suite, and (for most EPs) a roadmap entry recording the final verdict and test counts.

Over time, on a project of this size, the possibility exists that:

- A STEP 3 audit claimed a fix was applied, but the fix is not actually present in the current source.
- A STEP 3 audit claimed a specific test passed and confirmed specific behavior, but that test does not actually cover — or actually fails — the claimed behavior.
- Test counts recorded in an audit document no longer match the test suite that currently exists on disk.
- Implementation changed after an audit was written, silently invalidating the audit's conclusions.
- A bug exists in currently-committed code despite an audit's final verdict being "PASS."
- The test infrastructure itself hides or silently skips part of a suite, so a "PASS" was never actually earned.
- Environment limitations (missing system libraries, unavailable platform-specific packages) prevent certain tests from running at all, and this gets conflated with an actual implementation defect.
- Documentation drifts away from implementation (or vice versa) without any corresponding functional regression.

This audit was commissioned specifically to walk EP-001 through EP-092, cross-check each of the above failure modes against the *current* repository state (not the state at the time of the original STEP 2/STEP 3), and produce an accurate historical baseline — without fixing anything found.

---

## 2. Audit Methodology

### 2.1 Repository Verification

- The repository was cloned locally (`git clone --depth 100 https://github.com/muzaffarashurov/jarvis.git`).
- The current implementation under `src/` was inspected directly (file existence, function/class presence, call-site behavior).
- Git history was inspected selectively with `git log`, `git log --oneline -- <path>`, and `git show --stat <hash>` / `git show <hash> -- <path>` to determine, for each finding, whether a defect was present from the *original* commit that introduced a feature, or whether it was introduced by a *later* commit (i.e., distinguishing an original defect from a regression).
- No `git checkout`, `git reset`, `git rebase`, or any history-rewriting command was used. No working-tree file was modified, created (other than this report), or deleted in the source repository.

### 2.2 Documentation Verification

For each EP with formal documentation, the following were cross-checked against each other and against the current repository:

- `docs/architecture/designs/EPxxx_DESIGN.md`
- `docs/architecture/audits/EPxxx_ARCHITECTURE_AUDIT.md` (or `EPxxx_AUDIT.md` for earlier-format documents)
- `docs/architecture/audits/EPxxx_FINDINGS_RESOLUTION.md` (STEP 3.1 documents, where present)
- The corresponding `tests/EPxxx/` directory and its test file(s)
- The corresponding implementation files under `src/`
- `docs/architecture/JARVIS_ROADMAP.md` (which, for several EPs — notably EP082 — contains the only recorded narrative of STEP 3 findings)
- `CHANGELOG.md`, `docs/BACKLOG.md`, and `docs/RELEASE_NOTES.md` where relevant to establishing whether an EP number was ever actually used

No assumption was made that either the audit document or the implementation was correct by default; every claim checked against the other, and where possible against directly executed code.

### 2.3 Test Verification

**The project does not use a plain pytest-discoverable test model for its EP suites.** Instead:

- Every EP test file defines a class inheriting from `src.testing.base_test.BaseTest`, decorated with `@TestRegistry.register`, and exposes a `NAME` class attribute (e.g. `NAME = "EP039"`).
- `src.testing.registry.TestRegistry` stores these classes in a dictionary keyed by `NAME.upper()`.
- `src.testing.runner.TestRunner` looks suites up by name and executes their `.run()` method, which returns a `TestResult` (passed/failed/skipped counts and failure messages) via custom `assert_true`/`assert_equal`/`assert_false`/`assert_not_none` methods — not Python's built-in `assert` or pytest's assertion rewriting.
- Running `python -m pytest tests/` against this repository collects **zero tests** for these files (confirmed directly) because none of the test classes/methods follow pytest's `Test*`/`test_*` naming convention in a pytest-discoverable shape.

Because of this, a custom harness was written for this audit that:

1. Enumerates every `tests/EP*/test_*.py` file.
2. Imports each one via `importlib.import_module` using its full dotted package path (`tests.EPxxx.test_yyy`), which correctly populates `TestRegistry` (an earlier attempt using `importlib.util.spec_from_file_location` produced spurious `AttributeError` exceptions from module-identity conflicts — a harness artifact, not a real bug — and was discarded in favor of standard package imports).
3. Runs every suite currently reachable through `TestRegistry.names()` and records passed/failed/skipped counts and failure messages.
4. Where the standard combined run could not be trusted (see §9, the TestRegistry collision finding), individual test files were imported and executed **in isolation** — one file at a time, in a fresh registry state — to recover the true assertion counts for each file independently. This is how the true, previously-hidden `test_github_service.py` (EP039) and `test_discord_service.py` (EP041) results were recovered.

Test counts recorded in each historical audit document were then compared, assertion-for-assertion, against the counts actually produced by execution. Where a mismatch appeared, the full audit document (including any addendum, STEP 3.1 findings-resolution document, or later section of the same document) was read in full before concluding that a mismatch was genuine drift rather than legitimate, self-documented test-suite growth.

### 2.4 Environment Verification

The sandbox used for this audit initially lacked several dependencies declared in `requirements.txt`. These were installed as follows:

- `pip install -r requirements.txt --break-system-packages`, with `openwakeword` excluded from the initial pass because its `tflite-runtime` sub-dependency has **no compatible PyPI wheel for Linux + Python 3.12** — confirmed directly (`pip install` fails with "Could not find a version that satisfies the requirement tflite-runtime<3,>=2.8.0").
- `apt-get install -y tesseract-ocr` — succeeded (already present), enabling EP053 (vision/OCR) tests.
- `apt-get install -y portaudio19-dev tesseract-ocr` — **failed atomically** the first time: `libasound2-dev` returned a 404 from `security.ubuntu.com`, which aborted the *entire* apt transaction, silently leaving `libportaudio2` uninstalled even though it had been successfully downloaded.
- This was diagnosed directly: `import sounddevice` raised `OSError: PortAudio library not found`.
- Installing `libportaudio2` directly (`apt-get install -y libportaudio2`, bypassing the failed `-dev`/`libasound2-dev` dependency chain) resolved this. After installation, `sounddevice.query_devices()` succeeds and returns an empty device list (0 physical audio devices exist in the sandbox — expected for a headless container — but the *library* itself now loads and constructs correctly).

**Practical effect on verifiability:**

- **EP046, EP047, EP049** became fully verifiable once `libportaudio2` was installed, and their results were re-measured and compared against their respective audit documents (see §11).
- **EP048** remains **UNVERIFIABLE — ENVIRONMENT** for 2 of its assertions, because those assertions specifically exercise `OpenWakeWordEngine`'s error-handling paths, and `OpenWakeWordEngine` cannot even be constructed in this sandbox — `import openwakeword` fails (`ModuleNotFoundError`) because the package could not be installed at all (its `tflite-runtime` dependency has no compatible wheel), so a *different*, earlier `ModuleNotFoundError`-derived message is raised instead of the model-directory/model-file validation error the tests are checking for.
- **EP044/EP050 (PySide6/Qt desktop UI)** — PySide6 installed successfully from PyPI and desktop-related suites executed normally; no separate limitation was found here in this sandbox, though EP069.2's own audit document notes that 3 of its 15 sub-tests could not execute without Qt in *its* audit environment (a pre-existing, documented, unrelated note, not a finding of this audit).

---

## 3. Classification Logic Used

Each EP in the requested EP-001–EP-092 range was assigned exactly one of the following classifications:

- **MATCH** — Current implementation, current tests, and existing design/audit documentation are all mutually consistent. Any minor test-count differences are fully explained by the audit document's own later sections/addenda.
- **MINOR DRIFT** — A real but non-functional discrepancy exists (e.g., a documentation figure that no longer matches reality, or a structural documentation inconsistency), with no evidence of any corresponding functional defect.
- **MATERIAL DRIFT** — An audit document makes a specific, testable factual claim about behavior that is contradicted by directly executing the current code and its own regression test. This is the most serious category found in this audit.
- **UNVERIFIABLE — ENVIRONMENT** — The current sandbox cannot execute the relevant code path at all (a required package/library is unavailable on this platform/Python version), so no verdict can be reached one way or the other; explicitly *not* treated as a defect.
- **UNVERIFIABLE (no audit baseline)** — Implementation and tests exist and pass, but no design/audit document exists for that EP to check consistency against, because the EP predates the project's formal documentation convention. Explicitly *not* treated as "broken" or "missing" — the deliverable is present and working, there is simply nothing recorded to compare it to.
- **EXPECTED — FUTURE ROADMAP** — The EP number has no commits, no design/audit documents, and no tests in the current repository, and this absence is explicitly and correctly documented in `docs/architecture/designs/ROADMAP_070_138_REBUILD_PROPOSAL.md` as intentional future planning, not a completed-but-lost deliverable. Never classified as "missing implementation."

**On EP070–EP081 and EP084–EP091 specifically:** these ranges were *not* classified as missing implementation. `ROADMAP_070_138_REBUILD_PROPOSAL.md` (itself scoped as "documentation/planning only. No source code, tests, configuration, or dependencies were touched") establishes that only 69 EPs (EP001–EP069, including sub-EPs) constitute the completed "Core," and that EP070–EP140 is a forward-looking roadmap proposal. Zero commits, zero CHANGELOG entries, and zero test directories exist for any of these numbers anywhere in `git log` — fully consistent with "not yet started," not "started and then lost."

**On EP082, EP083, and EP092 specifically:** these three EP numbers fall inside the "future roadmap" numeric range described above, but they are, in fact, real, implemented, out-of-sequence EPs — each with its own commit, its own `tests/EPxxx/` suite, and (for EP083 and EP092) its own dedicated architecture-audit document. They were therefore audited individually and in full, exactly like EP036–EP069, rather than being treated as roadmap placeholders.

---

## 4. Complete EP Status Table (EP001–EP092)

| EP | Implementation | Tests | Design Doc | Architecture Audit | Verification | Result | Notes |
|---|---|---|---|---|---|---|---|
| EP001 | Yes | 20/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP002 | Yes | 21/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP003 | Yes | 22/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP004–EP017 | Commits exist (`1b359e8`…`d7a441a`) | None currently tracked (`tests/EP004`…`EP017` do not exist) | None | None | Git history only | UNVERIFIABLE (no audit baseline) | Commits present in `git log` but no current test dir, design doc, audit doc, or CHANGELOG entry survives under these numbers; deliverables (e.g. EP004's test framework) appear to be subsumed into the later, unnumbered `src/testing/` structure. No removal commit found. Outside STEP-3 audit system scope; not deep-audited per task instructions. |
| EP018 | Yes | 26/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP019 | Yes | 431/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP020 | Yes | 239/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP021 | Yes | 340/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP022 | Yes | 802/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP023 | Yes | 330/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP024 | Yes | 407/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP025 | Yes | 442/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP026 | Yes | 204/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP027 | Yes | 229/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP028 | Yes | 214/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP029 | Yes | 197/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP030 | Yes | 179/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP031 | Yes | 212/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP032 | Yes | 176/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP033 | Yes | 182/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP034 | Yes | 113/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP035 | Yes | 143/0/0 | None | None | Executed directly | UNVERIFIABLE (no audit baseline) | Pre-formal-documentation era |
| EP036 | Yes | 101/0/0 + STEP2 48/0/0 + STEP3 53/0/0 | — | `EP036_AUDIT.md` | Executed directly | **MATCH** | 3 distinct suite names — no registry collision |
| EP037 | Yes | 87/0/0 | — | `EP037_AUDIT.md` | Executed directly | **MATCH** | |
| EP038 | Yes | Module 30/0/0 (audit-reported); Service 25/0/0 (isolated) | — | `EP038_AUDIT.md` | Executed both in isolation | **MATCH** | Registry collision present (§9) but hidden service suite is clean |
| EP039 | Yes | Module 36/0/0 (audit-reported); **Service 43/1/0 (isolated)** | — | `EP039_ARCHITECTURE_AUDIT.md` | Executed both in isolation | **MATERIAL DRIFT** | See §8 — URL quoting defect hidden by registry collision |
| EP040 | Yes | Module 25/0/0 (audit-reported); Service 30/0/0 (isolated) | — | `EP040_ARCHITECTURE_AUDIT.md` | Executed both in isolation | **MATCH** | Registry collision present but hidden service suite is clean |
| EP041 | Yes | Module 39/0/0 (audit-reported); **Service 40/1/0 (isolated)** | — | `EP041_ARCHITECTURE_AUDIT.md` | Executed both in isolation | **MATERIAL DRIFT** | See §8 — URL quoting defect hidden by registry collision; commit mislabeled "EP040" |
| EP042 | Yes | Service 55/0/0, Module 28/0/0 — both independently reported | — | `EP042_ARCHITECTURE_AUDIT.md` | Executed both in isolation | **MATCH** | This EP's own audit discovered and documented the registry collision (§9) |
| EP043 | Yes | 83/0/0 | — | `EP043_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | |
| EP044 | Yes | 52/0/0 | — | `EP044_AUDIT.md` | Executed directly | **MATCH** | |
| EP045 | Yes | 38/0/0 | — | `EP045_AUDIT.md` | Executed directly | **MATCH** | |
| EP046 | Yes | 58/0/1 (audit claims 57/0/1) | — | `EP046_AUDIT.md` | Executed after `libportaudio2` install | **MINOR DRIFT** | See §11/§10 — 1-assertion discrepancy, no functional defect |
| EP047 | Yes | 49/0/0 (exact match) | — | `EP047_AUDIT.md` | Executed after `libportaudio2` install | **MATCH** | See §11 — corrected from an earlier, environment-incomplete measurement |
| EP048 | Yes | 110/2/1 in this sandbox (2 failures are environment-caused) | — | `EP048_AUDIT.md` | Attempted; `openwakeword` unavailable | **UNVERIFIABLE — ENVIRONMENT** | See §11 |
| EP049 | Yes | 87/0/1 (exact match) | — | `EP049_AUDIT.md` | Executed after `libportaudio2` install | **MATCH** | See §11 — corrected from an earlier, environment-incomplete measurement |
| EP050 | Yes | 112/0/0 | — | `EP050_AUDIT.md` | Executed directly | **MATCH** | |
| EP051 | Yes | 105/0/0 | — | `EP051_AUDIT.md` | Executed directly | **MATCH** | |
| EP052 | Yes | 135/0/0 | — | `EP052_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | |
| EP053 | Yes | 58/0/0 | — | `EP053_ARCHITECTURE_AUDIT.md` | Executed directly (tesseract-ocr installed) | **MATCH** | |
| EP054 | Yes | 76/0/0 | — | `EP054_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | |
| EP055 | Yes | 64/0/0 (audit's own final, post-growth figure) | — | `EP055_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | See §14 |
| EP056 | Yes | 62/0/0 (audit claims 51/0/0) | — | `EP056_ARCHITECTURE_AUDIT.md` | Executed directly | **MINOR DRIFT** | See §10 — unresolved documentation drift, no functional defect |
| EP057 | Yes | 41/0/0 (audit's own final figure: 35→41, +6 documented) | — | `EP057_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | See §14 |
| EP058 | Yes | 110/0/0 | — | `EP058_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | See §14 |
| EP059 | Yes | 93/0/0 | — | `EP059_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | Exact match, incl. audit's own reported `passed=93 failed=0 skipped=0` |
| EP060 | Yes | 65/0/0 | — | `EP060_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | |
| EP061 | Yes | 62/0/0 | — | `EP061_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | |
| EP062 | Yes | 39/0/0 | — | `EP062_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | Exact match to audit's `EP062 : 39 passed / 0 failed / 0 skipped` |
| EP063 | Yes | 78/0/0 | — | `EP063_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | |
| EP064 | Yes | 93/0/0 | — | `EP064_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | |
| EP065 | Yes | 42/0/0 | — | `EP065_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | |
| EP066 | Yes | 23/0/0 | — | `EP066_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | |
| EP067 | Yes | 33/0/0 | — | `EP067_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | |
| EP068 (+REV2) | Yes | 52/0/0 | — | `EP068_ARCHITECTURE_AUDIT.md`, `EP068_REV2_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | |
| EP069.1 | Yes | 68/0/0 | `EP069_DESIGN.md` | `EP069_ARCHITECTURE_AUDIT.md`, `EP069_FINDINGS_RESOLUTION.md` | Executed directly | **MATCH** | See §12 |
| EP069.2 | Yes | 26/0/0 | `EP069_2_DESIGN.md` | `EP069_2_ARCHITECTURE_AUDIT.md`, `..._FINDINGS_RESOLUTION.md` | Executed directly | **MATCH** | See §12 |
| EP069.3 | Yes | 80/0/0 | `EP069_3_DESIGN.md` | `EP069_3_ARCHITECTURE_AUDIT.md`, `..._FINDINGS_RESOLUTION.md` | Executed directly + source-verified | **MATCH** | See §12 |
| EP069.4 | Yes | 41/0/0 (33→41, +8 documented) | `EP069_4_DESIGN.md` | `EP069_4_ARCHITECTURE_AUDIT.md`, `..._FINDINGS_RESOLUTION.md` | Executed directly | **MATCH** | See §12, §14 |
| EP069.5 | Yes | 37/0/0 | `EP069_5_DESIGN.md` | `EP069_5_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | See §12 |
| EP069.6 | Yes | 51/0/0 | `EP069_6_DESIGN.md` | `EP069_6_ARCHITECTURE_AUDIT.md` | Executed directly | **MATCH** | See §12 |
| EP070–EP081 | No | None | None | None | Git history search: zero matches | **EXPECTED — FUTURE ROADMAP** | See §15 |
| EP082 | Yes | 69/0/0 | `EP082_DESIGN.md` | **None (no dedicated audit doc)** | Executed directly + source-verified | **MINOR DRIFT** | See §10, §12 — implementation and claimed fix verified true; audit-artifact structure inconsistent with every other audited EP |
| EP083 | Yes | 60/0/0 (54→60, +3 documented) | `EP083_DESIGN.md` | `EP083_ARCHITECTURE_AUDIT.md` | Executed directly + source-verified | **MATCH** | See §12, §14 |
| EP084–EP091 | No | None | None | None | Git history search: zero matches | **EXPECTED — FUTURE ROADMAP** | See §15 |
| EP092 | Yes | 820/0/0 (775→820, +45 across 3 fix rounds, all documented) | `EP092_DESIGN.md` | `EP092_ARCHITECTURE_AUDIT.md` | Executed directly + source-verified | **MATCH** | See §12, §14 |

---

## 5. Overall Audit Statistics

These figures are carried forward unchanged from the completed audit; no recalculation was required or performed.

| Category | Count |
|---|---|
| EP numbers in requested range (001–092) | 92 |
| EPs with real commits/implementation in this repository | 70 (EP001–EP069 incl. sub-EPs .2–.6, EP082, EP083, EP092) |
| EPs with formal DESIGN + ARCHITECTURE_AUDIT documents | EP036–EP069(.2–.6), EP083, EP092 = 45 audit/design document pairs (EP082 has a design document only) |
| EPs predating the formal audit system (implemented, but with no design/audit docs to check against) | EP001–EP035 = 35 |
| EPs that are EXPECTED — FUTURE ROADMAP (correctly not yet implemented) | EP070–EP081, EP084–EP091 = 20 |
| **MATCH** (of 70 implemented, audit-eligible EPs) | **66** |
| **MINOR DRIFT** | **3** (EP046, EP056, EP082) |
| **MATERIAL DRIFT** | **2** (EP039, EP041) |
| **MISSING IMPLEMENTATION** | **0** — every EP claiming completion has its claimed artifacts present |
| **UNVERIFIABLE — ENVIRONMENT** | 1 EP with partial impact (EP048 — 2 of its assertions) |
| **UNVERIFIABLE (no audit baseline; historical/pre-formal era)** | EP001–EP035, plus EP004–EP017 as a special historical case (see §16) |

---

## 6. Material Drift Findings

### 6.1 EP039 — GitHub Service URL Path-Segment Quoting Defect

- **Affected file:** `src/services/github_service.py`
- **Root cause:** `urllib.parse.quote()` is called on `owner`/`repo`/`number`/`sha` path components (6 call sites, e.g. line 129: `path = f"/repos/{quote(owner)}/{quote(repo)}"`) **without** `safe=''`. `urllib.parse.quote()`'s default `safe` parameter is `'/'`, meaning `/` characters are explicitly *not* percent-encoded by default.
- **Consequence:** A `/` character inside a path segment (e.g. a repository name literally containing a slash) is passed through **unencoded**. Confirmed directly: `python3 -c "from urllib.parse import quote; print(quote('hello/world'))"` → `hello/world` (unchanged); only `quote('hello/world', safe='')` → `hello%2Fworld` produces the expected encoding.
- **The relevant regression test actually fails.** `tests/EP039/test_github_service.py::_test_path_segments_are_url_quoted` (line 477) asserts:
  ```python
  self.assert_true("hello%2Fworld" in url)
  ```
  This assertion **fails** on direct, isolated execution of `test_github_service.py`. The isolated result for that file alone is:
  ```
  43 passed / 1 failed / 0 skipped
  ```
- **What the audit claims:** `EP039_ARCHITECTURE_AUDIT.md` §6 states: *"URL path segments (owner/repo/number/sha) are quoted using `urllib.parse.quote`"* and reports the overall EP039 test result as **"EP039 : 36 passed / 0 failed / 0 skipped."** Both of these statements are demonstrably incorrect against the actual `test_github_service.py` file, once it is run.
- **Why the audit's reported 36/0/0 never caught this:** The reported figure of 36 passed is **exactly** what `tests/EP039/test_github_module.py` alone produces when run in isolation (confirmed: 36/0/0). `test_github_service.py` — the file containing the failing assertion, at 44 total assertions — was never actually executed by whatever process generated the audit's reported number. This is the direct consequence of the TestRegistry NAME collision documented in §9.
- **Origin — this is NOT a later regression.** `git show 236f731 -- src/services/github_service.py` confirms the unsanitized `quote()` calls were present in the **very first commit** that introduced this file (`236f731`, "feat(ep039): add read-only GitHub integration"). `git log --oneline -- src/services/github_service.py` and `git log --oneline -- tests/EP039/test_github_service.py` each show **exactly one commit** — neither file has ever been modified since. The defect and the test that catches it have coexisted, unexecuted together, since EP039 was created.
- **Classification: MATERIAL DRIFT.** A specific, falsifiable technical claim in an architecture audit document is contradicted by directly executing the code and the audit's own named regression test.

### 6.2 EP041 — Discord Service URL Path-Segment Quoting Defect

- **Affected file:** `src/services/discord_service.py`
- **Root cause:** Identical defect class to EP039 — `quote()` is used on `guild_id`/`channel_id`/`user_id`/`message_id` (5 call sites, e.g. line 203: `path = f"/guilds/{quote(str(guild_id))}/members/{quote(str(user_id))}"`) without `safe=''`, so `/` is not encoded.
- **Consequence / failing test:** `tests/EP041/test_discord_service.py::_test_path_segments_are_url_quoted` (line ~440) asserts:
  ```python
  self.assert_true("user%2Fid" in url)
  ```
  This fails on isolated execution. Isolated result for `test_discord_service.py` alone:
  ```
  40 passed / 1 failed / 0 skipped
  ```
- **What the audit claims:** `EP041_ARCHITECTURE_AUDIT.md` §3 states, explicitly and specifically: *"Every path parameter (`guild_id`, `channel_id`, `user_id`, `message_id`) is passed through `urllib.parse.quote(str(...))` before being interpolated into the URL — confirmed at all five call sites in `discord_service.py`. `tests/EP041/test_discord_service.py`'s `_test_path_segments_are_url_quoted` independently exercises this with a space and a slash, **confirming `%20`/`+` and `%2F` encoding**."* This claim of independent confirmation is false — the test, when actually run, fails at exactly the `%2F` assertion.
- **Why this was hidden:** Same TestRegistry-collision mechanism as EP039 (§9). `EP041_ARCHITECTURE_AUDIT.md`'s reported figure ("Passed: 39") matches `test_discord_module.py` run alone (39/0/0) exactly; `test_discord_service.py` (41 total assertions including the failing one) was never actually executed by the process that produced that reported number.
- **Origin — this is NOT a later regression.** `git show 19de629 --stat` confirms `src/services/discord_service.py`, `src/modules/discord_module.py`, `src/core/discord/`, and **both** EP041 test files were added together in a single commit. `git log --oneline -- src/services/discord_service.py` shows exactly one commit. The defect has existed, uncaught, since EP041's creation.
- **Misleading commit labeling (also part of this audit's findings):** The commit that introduced all of EP041's deliverables (`19de629`) is labeled in its commit message as *"feat(jarvis): complete EP040 implementation and validation"* — i.e., EP041's entire implementation, test suite, design document, and architecture-audit document were committed under an EP040-labeled commit message. This is a git-hygiene/attribution error layered on top of, but separate from, the quoting defect itself.
- **Classification: MATERIAL DRIFT.** Same category and severity rationale as EP039.

Neither EP039 nor EP041's defect was fixed as part of this audit, per the read-only constraint governing this entire engagement.

---

## 7. Test Infrastructure Finding — EP038–EP042 Registry Collision

**This is a test-infrastructure defect, not an application-feature defect.**

- **Mechanism:** `src/testing/registry.py`'s `TestRegistry.register` classmethod stores every registered test class in a single dictionary keyed by `test_class.NAME.upper()`:
  ```python
  _tests: Dict[str, Type[BaseTest]] = {}

  @classmethod
  def register(cls, test_class):
      cls._tests[test_class.NAME.upper()] = test_class
      return test_class
  ```
  If two different test classes, in two different files, both declare `NAME = "EP039"` (for example), the second one imported **silently overwrites** the first in `_tests`. There is no warning, no error, no collision detection of any kind.
- **Affected EPs (confirmed by direct inspection of every `NAME =` class attribute in every multi-file `tests/EPxxx/` directory):**

  | EP | File 1 | File 2 | Both share `NAME`? |
  |---|---|---|---|
  | EP038 | `test_git_module.py` (`NAME = "EP038"`) | `test_git_service.py` (`NAME = "EP038"`) | Yes |
  | EP039 | `test_github_module.py` (`NAME = "EP039"`) | `test_github_service.py` (`NAME = "EP039"`) | Yes |
  | EP040 | `test_telegram_info_module.py` (`NAME = "EP040"`) | `test_telegram_info_service.py` (`NAME = "EP040"`) | Yes |
  | EP041 | `test_discord_module.py` (`NAME = "EP041"`) | `test_discord_service.py` (`NAME = "EP041"`) | Yes |
  | EP042 | `test_email_module.py` (`NAME = "EP042"`) | `test_email_service.py` (`NAME = "EP042"`) | Yes |

  (EP036's three test files, and EP050/EP051/EP053's secondary "integration" files, were checked and confirmed **not** to collide — EP036 uses three distinct names, `"EP036"`, `"EP036-STEP2"`, `"EP036-STEP3"`; EP050/EP051/EP053's `*_integration.py` files do not use `@TestRegistry.register` at all.)

- **Practical effect:** The single-command CLI invocation `test EPxxx` (and any regression-run process built on `TestRunner.run("EPxxx")` or `TestRunner.run_all()`) only ever exercises **whichever of the two files' classes happens to be imported last**, not both. The other file's assertions are silently never run under that invocation path, even though the file itself still exists, is still valid Python, and would pass or fail if executed directly.
- **This is exactly how EP039's and EP041's service-level defects were hidden** (§6.1, §6.2) — through every original STEP 3 audit and every subsequent full-project regression run referenced in later EP audits (e.g. the "7370 passed / 2 failed / 3 skipped" and similar aggregate figures quoted across EP064–EP069 audits never actually included `test_github_service.py`'s or `test_discord_service.py`'s full assertion sets).
- **EP042's own architecture-audit document had already identified this exact technical debt.** `EP042_ARCHITECTURE_AUDIT.md` §16 ("Known Technical Debt") states that `TestRegistry.register` keys by `NAME.upper()`, that both `EmailServiceTest` and `EmailModuleTest` share `NAME = "EP042"`, that "the identical collision exists for every prior integration EP's Service/Module test-class pair (confirmed present for EP-038 through EP-041 by inspection of their `NAME` class attributes)," that it "was not fixed" and is "outside EP042 scope," and that it "should be handled separately by a dedicated future maintenance EP." For **EP042 itself**, that audit did the correct thing and independently ran and reported both suites separately (55/0/0 and 28/0/0) — both confirmed genuinely clean by this retrospective audit's own isolated re-execution.
- **The gap that allowed EP039/EP041 to go undetected:** EP042's audit flagged the collision as existing for EP038–EP041 *by inspecting their `NAME` attributes*, but did not go back and **execute** EP039's and EP041's previously-hidden service suites to check whether anything was actually wrong behind the collision. No later document closed that loop either — until this retrospective audit did so.
- **Independent execution was therefore necessary for this retrospective audit.** Every one of EP038, EP039, EP040, EP041, and EP042's two test files was run in isolation (fresh `TestRegistry` state per file) specifically to recover each file's true, independent result. This is how EP039's (43/1/0) and EP041's (40/1/0) hidden failures were surfaced, and equally how EP038's (25/0/0) and EP040's (30/0/0) hidden-but-clean service suites were confirmed *not* to hide any defect.
- **Explicitly not every affected EP is classified as defective.** The collision itself is an infrastructure problem affecting all five EPs equally. Whether a *real* defect was hiding behind it had to be checked EP-by-EP — and only EP039 and EP041 turned out to have one.

---

## 8. Minor Drift Findings

### 8.1 EP056 — Test-Count Documentation Drift

- **Architecture audit claim:** `EP056_ARCHITECTURE_AUDIT.md` line 269 states the STEP 3 re-run "reproduced exactly **51 passed / 0 failed / 0 skipped**."
- **Current isolated suite result:** Direct execution of `tests/EP056/test_capability_registry.py` in isolation produces **62 passed / 0 failed / 0 skipped** (60 static `self.assert_*` call sites in the source, 62 executed at runtime due to loop-generated assertions).
- **No later implementation commit explains the difference.** `git log --oneline -- tests/EP056/test_capability_registry.py` returns exactly one commit (`b3638b9`, "feat(EP-056): complete Capability Registry") — the file has never been modified since. No `EP056`-related addendum, resolution document, or later section of the audit document itself records or explains the growth from 51 to 62 (unlike EP055, EP057, EP058, EP069.4, and EP092, each of which self-documents its own count growth elsewhere in the same or a companion document — see §14).
- **Classification: MINOR DRIFT — documentation only.** The current suite is 100% clean (62/62 passing), so there is no functional problem of any kind. This is purely a mismatch between a recorded historical figure and the test file that has existed, unchanged, since the EP was created — most plausibly a transcription error in the original STEP 3 report.

### 8.2 EP082 — Documentation-Structure and Hygiene Drift

- **`ProviderRequestExecutor` — confirmed present and matches its claimed design.** `src/core/ai/provider_request_executor.py` exists; its module docstring and implementation match the roadmap's description of a shared fallback/retry executor used by both `AIService.ask()` (EP-018) and the new `TextGenerationService` (EP-082), later extended by `ImageGenerationService` (EP-083).
- **The claimed bare-`assert` → explicit-`None`-check fix — confirmed present.** `src/services/ai_service.py` lines 557–569 contain exactly the pattern described: a `response is None` guard with an explanatory comment referencing the `-O`-mode risk of a bare `assert`, replacing what the roadmap describes as the pre-fix bare assertion. The identical pattern is present in `src/services/text_generation_service.py`. No bare `assert` statement (as opposed to the custom `self.assert_*` test helpers) remains in either file.
- **Current tests: 69/0/0**, matching the roadmap's claimed figure for `tests/EP082/test_text_generation_provider_integration.py` exactly.
- **No dedicated `EP082_ARCHITECTURE_AUDIT.md` exists.** `git show --stat 077002f` (EP082's sole commit) shows only `docs/architecture/designs/EP082_DESIGN.md` was added — no audit document of any kind. This is the *only* EP in the entire 036–092 audited range that claims a completed "STEP 3 Architecture Audit" (per `JARVIS_ROADMAP.md`'s explicit wording: *"STEP 3 Architecture Audit, and STEP 4 Documentation Synchronization all complete"*) without a standalone, independently reviewable audit artifact backing that claim. By contrast, EP083's commit (`6a7944b`) added both a design document and a dedicated audit document in the same commit.
- **STEP 3 information exists elsewhere** — specifically, embedded directly in `JARVIS_ROADMAP.md`'s narrative prose (its verdict, "PASS WITH WARNINGS, ZERO CRITICAL, ZERO HIGH," and its one named LOW finding and fix, are both recorded there rather than in a dedicated document).
- **A previously unreported duplicate file was discovered during this verification:** `src/core/ai/text_generation_service.py` and `src/services/text_generation_service.py` are **byte-identical** (confirmed via `diff`, zero output). Both were added in the same commit (`077002f`). Only the `src/services/` copy is ever imported anywhere (`tests/EP082/test_text_generation_provider_integration.py` imports `from src.services.text_generation_service import ...`); `src/core/ai/text_generation_service.py` is fully orphaned — no file in `src/`, `tests/`, or `docs/` references it.
- **Classification: MINOR DRIFT (hygiene/documentation), not a confirmed functional defect.** Every substantive technical claim about EP082's behavior was independently verified true. The issues here are (a) a missing audit artifact where every comparable EP has one, and (b) an unreferenced duplicate file that cannot itself cause any runtime divergence since nothing executes it.

### 8.3 EP046 — Minor Test-Count Discrepancy

- **Current result (post-`libportaudio2` install): 58 passed / 0 failed / 1 skipped.**
- **Historical audit claim (`EP046_AUDIT.md`): 57 passed / 0 failed / 1 skipped.**
- **Discrepancy:** exactly 1 assertion. No functional failure exists in either figure (both report 0 failed). This was not investigated further to a root cause given the complete absence of any actual failure; it is recorded here for completeness and classified as a trivial, non-functional discrepancy.
- **Classification: MINOR DRIFT.**

---

## 9. Environment-Limited Verification

This section exists specifically to separate genuine **environment limitations** (this sandbox cannot exercise certain code) from **implementation failures** (the code itself is wrong). None of the findings in this section were treated as defects.

### 9.1 EP047 — Resolved to MATCH after installing `libportaudio2`

Initial execution (before `libportaudio2` was correctly installed) produced 2 spurious failures related to `bootstrap.voice_engine` construction. Root-caused directly: `import sounddevice` raised `OSError: PortAudio library not found` because an earlier `apt-get install portaudio19-dev tesseract-ocr` had failed atomically (a 404 on the unrelated `libasound2-dev` package aborted the whole transaction). After `apt-get install -y libportaudio2` (bypassing the failed `-dev` package chain), `sounddevice.query_devices()` succeeds (returning 0 devices — expected in a headless container, but no longer erroring). Re-run result:

```
EP047 passed 49 failed 0 skipped 0
```

This is an **exact match** to `EP047_AUDIT.md`'s claimed 49/0/0. **EP047 is classified MATCH, not a failure** — the earlier reading of 2 failures reported during this audit's first working session was itself an environment artifact of this sandbox's incomplete initial library installation, corrected once the true root cause was found.

### 9.2 EP049 — Resolved to MATCH after installing `libportaudio2`

Same root cause and same resolution as EP047. Re-run result:

```
EP049 passed 87 failed 0 skipped 1
```

This is an **exact match** to `EP049_AUDIT.md`'s claimed 87/0/1. **EP049 is classified MATCH.**

### 9.3 EP048 — Remains UNVERIFIABLE — ENVIRONMENT

Even after `libportaudio2` was correctly installed, EP048 continued to show 2 failures:

```
EP048 passed 110 failed 2 skipped 1
```

Root cause, confirmed directly: `import openwakeword` raises `ModuleNotFoundError` in this sandbox, because the `openwakeword` package's `tflite-runtime` sub-dependency has **no compatible PyPI wheel for Linux + Python 3.12** (confirmed via a direct `pip install` attempt, which fails with "Could not find a version that satisfies the requirement tflite-runtime<3,>=2.8.0"). The two failing assertions — `_test_open_wake_word_engine_rejects_missing_model_dir` and `_test_open_wake_word_engine_rejects_missing_model_files` — both expect `OpenWakeWordEngine` construction to raise a specific `WakeWordEngineError` referencing `model_dir`/`melspectrogram.onnx`; instead, construction fails earlier, with a different, import-level error, because the underlying package cannot be present in this environment at all.

**This is explicitly not classified as an implementation failure.** It is a hard platform/dependency-availability limitation of the current sandbox, not evidence that `OpenWakeWordEngine`'s validation logic is wrong. **EP048 is classified UNVERIFIABLE — ENVIRONMENT** for these 2 assertions; the remaining 110 assertions in the suite executed and passed normally.

---

## 10. EP082, EP083, EP092 — STEP 3 Verification for Implemented Out-of-Sequence EPs

These three EPs fall numerically inside the "future roadmap" EP070–EP140 range but are, in fact, real and complete. Each was independently source-verified, not merely trusted from its documentation.

### 10.1 EP082

- **Verified STEP 3 fixes:** the bare-`assert`-to-explicit-`None`-check hardening described in §8.2, confirmed present in both `src/services/ai_service.py` and `src/services/text_generation_service.py`.
- **`ProviderRequestExecutor`:** confirmed present, shared correctly between `AIService` and the new `TextGenerationService`, matching its documented responsibility boundaries (it owns request execution/retry mechanics only; `ProviderManager` remains the sole owner of provider selection/ordering).
- **Test result: 69/0/0.**
- Classified **MINOR DRIFT** overall (§8.2) due to the missing dedicated audit document and the orphaned duplicate file — not due to any incorrect behavior.

### 10.2 EP083

- **F1 (the one "fixed" finding) — confirmed.** `EP083_ARCHITECTURE_AUDIT.md` §13 describes removing a redundant duplicate validation block plus a now-dead bare `assert` from `GeminiProvider.generate_image()`, replacing both with a single explicit `image_model = self._image_model; if image_model is None: raise ProviderConfigurationError(...)` narrowing pattern. Confirmed verbatim in `src/core/ai/providers/gemini_provider.py` lines 289–293; no bare `assert` remains anywhere in any EP-083-touched file.
- **F2–F5 — confirmed intentionally NOT fixed**, exactly as the audit's own disposition states for each (deferred/by-design/no architectural requirement) — verified by inspection that none of the described gaps (initial-provider capability check, empty-prompt rejection, size-parameter forwarding, response-size cap) have since been added.
- **Test result: 60/0/0** (54→60, +3 tests added during the same audit session, fully documented in the audit itself — see §14).
- Classified **MATCH**.

### 10.3 EP092

- **MATCH — 820/0/0**, fully consistent with its own audit's remediation history (775 → 820 across 3 documented fix rounds — see §14).
- **All three claimed STEP 3 fixes independently confirmed present in current source, not merely trusted:**
  1. **Category allowlist regex** — `src/core/personal_data/personal_data_persistence.py`: `category_path()` (line 101) calls `_validate_category(category)` before ever constructing a path; the validator enforces `^[A-Za-z0-9_-]+$`, rejecting path separators, `..`, absolute paths, and null bytes, applied identically on both the `append_line()` (write) and `read_lines()`/`query()` (read) directions.
  2. **`threading.Lock` + atomic `store_if_new()`** — `src/core/personal_data/personal_data_provider.py`: `self._lock = threading.Lock()` (line 207); `store_if_new()` (line 225) performs the existence-check-and-store sequence under a single lock acquisition; `PersonalDataManager.collect_from()` (line 115) calls exclusively `store_if_new()` — the separate `exists()` + `store()` sequence that created the original race is confirmed absent from every production call path.
  3. **`_rebuild_dedup_index()` per-category exception handling** — confirmed present at line 304 of the same file, catching `PersonalDataPersistenceError` per category during startup rather than aborting construction entirely, with the docstring explicitly citing "EP-092 STEP 3 audit finding" by name.
- EP092's audit is a strong positive example within this audit: its addendum (§18.1–18.3 of `EP092_ARCHITECTURE_AUDIT.md`) explicitly re-verifies all three fixes with fresh, out-of-repo, disposable-directory testing and reports the exact same 820/0/0 figure this retrospective audit independently reproduced.

---

## 11. EP069.x Sub-EP Verification

| Sub-EP | Result | Test Count | Key Finding(s) |
|---|---|---|---|
| **EP069.1** | MATCH | 68/0/0 | "PASS WITH WARNINGS" — 7 MEDIUM/LOW findings (`EP069.1-AUDIT-001` through `-007`), all non-blocking and informational/deferred in nature, none requiring or claiming a code fix. Consistent with current implementation. |
| **EP069.2** | MATCH | 26/0/0 | Finding `EP069.2-AUDIT-001` (and its companion test-coverage gap `-002`) was **deliberately deferred** rather than fixed reactively, per the audit's own explicit instruction ("Do not implement any fix during STEP 3.1 unless a corrective-action decision is explicitly made to do so as a separate, scoped step") — mirroring how EP069.1's own MEDIUM findings were handled. Matches current state; this deferred item was later picked up and actually fixed under EP069.3 (see below). |
| **EP069.3** | MATCH | 80/0/0 | `EP069.3-AUDIT-001` (`ProviderManager` did not independently enforce the `relative_cost` invariant it documents, MEDIUM) was **fixed**: `_is_valid_relative_cost()` confirmed present at `src/core/ai/provider_manager.py:79`, called at line 195 to filter invalid entries. `EP069.3-AUDIT-002` through `-006` are either documentation-staleness notes, test-coverage-gap-only observations, or an explicitly inherited (not introduced by EP069.3) issue — none required or claimed further code fixes beyond `-001`. |
| **EP069.4** | MATCH | 41/0/0 (33→41) | `EP069_4_FINDINGS_RESOLUTION.md` documents an exception-hierarchy fix as the one actionable finding (`EP069.4-AUDIT-001`), plus 8 new regression-test assertions added alongside it (33→41, exactly matching this audit's own measured 41/0/0). `EP069.4-AUDIT-002/003/004` are explicitly recorded as INFORMATIONAL, requiring no action. |
| **EP069.5** | MATCH | 37/0/0 | "No STEP 3.1 was required" — STEP 1 findings (`EP069.5-AUDIT-001/002`) were both resolved by direct construction correctness at STEP 2 time, not by a later fix pass; figure matches exactly. |
| **EP069.6** | MATCH | 51/0/0 | Single finding `AUDIT-001` (LOW/INFORMATIONAL) concerns test design only — verifying a private `_provider` attribute directly because no public accessor exists — explicitly assessed as the correct trade-off (adding a public accessor solely for test convenience would itself violate the project's "no speculative public API" rule) and requiring **no resolution**. Final Verdict: **PASS**, with zero CRITICAL/HIGH/MEDIUM findings. |

---

## 12. Test Count Reconciliation

Several apparent test-count mismatches between an audit document's *first-reported* figure and this audit's measured figure were investigated and **fully reconciled** once each audit document's complete text — including any addendum, STEP 3.1 resolution document, or later section — was read in full, rather than relying on the first matching grep result. These were **not** classified as drift.

| EP | Audit's earliest figure | This audit's measured figure | Reconciliation |
|---|---|---|---|
| EP055 | 52 passed (initial STEP 3 re-run) | 64 passed | The audit document's own §-later text records 12 new assertions (4 new test methods) added during the same STEP 3 session, "bringing the suite to 64 passed / 0 failed / 0 skipped" — exact match to this audit's measurement. |
| EP057 | 35 passed (STEP 2 baseline, reproduced in STEP 3) | 41 passed | The same audit document records, later, "now reports 41 passed / 0 failed / 0 skipped (up from the original 35 — the six additional passing assertions are exactly the new test's own three CLI-layer and three Service-layer/message... [assertions])" — exact match. |
| EP058 | 110 passed | 110 passed | No growth occurred here; the audit explicitly confirms a later re-run after a documentation-only edit "reproduced the identical 110 passed / 0 failed / 0 skipped result ... as expected, since no code was touched." Straightforward match. |
| EP069.4 | 33 passed (STEP 3 baseline) | 41 passed | `EP069_4_FINDINGS_RESOLUTION.md` explicitly tabulates this exact delta: "EP069_4 | 41 | 0 | 0 | 33/0/0 | +8 passed (the fix's own new tests)." Exact match. |
| EP092 | 775 passed (fresh STEP 3 re-audit, before fixes) | 820 passed | `EP092_ARCHITECTURE_AUDIT.md` §18.2 records the final post-remediation figure as "820 passed / 0 failed / 0 skipped, stable across 3 independent fresh runs" after all three STEP 3 fixes (§10.3) were applied. Exact match. |
| EP083 | 54 (implied pre-audit baseline) | 60 passed | The audit document's own summary line states explicitly: "tests/EP083 : 60 passed / 0 failed / 0 skipped (54 -> 60: 3 tests added during this audit, Section 9 above)." Exact match. |

**Only EP056 (§8.1) failed to reconcile** — no addendum, later section, or companion document exists anywhere for EP056 that accounts for its 51-vs-62 discrepancy, distinguishing it clearly from the fully-self-documented cases above.

---

## 13. Future / Not-Yet-Implemented EPs

**EP070–EP081 and EP084–EP091** were investigated and confirmed to have:

- Zero commits referencing these EP numbers anywhere in `git log --oneline` (full history, 89 commits, checked).
- Zero entries for any of these numbers in `CHANGELOG.md`.
- No `tests/EPxxx` directory for any of these numbers.
- No design or architecture-audit document for any of these numbers.

This absence is **explicitly and correctly documented** by `docs/architecture/designs/ROADMAP_070_138_REBUILD_PROPOSAL.md`, whose own stated scope is "documentation/planning only. No source code, tests, configuration, or dependencies were touched," and which establishes that the repository's completed "Core" consists of 69 EPs (EP001–EP069, Phases 1–10), with EP070–EP140 constituting a forward-looking roadmap proposal, not a set of completed-but-lost deliverables.

**These EPs are therefore classified EXPECTED — FUTURE ROADMAP, never MISSING IMPLEMENTATION.**

**EP082, EP083, and EP092**, despite falling numerically inside this same future-roadmap range, are real, implemented, out-of-sequence exceptions — each with its own commit, its own dedicated `tests/EPxxx/` suite, and (for EP083/EP092) its own dedicated architecture-audit document. They were therefore excluded from the "future roadmap" treatment and instead audited individually and in full detail (§10).

---

## 14. Historical / Pre-Formal EP Documentation

**EP001–EP003, EP004–EP017, and EP018–EP035** all predate the project's later, consistently-applied `DESIGN → IMPLEMENTATION → ARCHITECTURE AUDIT` workflow, which first appears (as a dedicated, per-EP document pair) starting at **EP036**.

- **EP001–EP003 and EP018–EP035:** implementation and dedicated `tests/EPxxx/` directories exist and execute cleanly (e.g. EP001: 20/0/0; EP022: 802/0/0; EP035: 143/0/0), but **no `EPxxx_DESIGN.md` or `EPxxx_AUDIT.md`/`EPxxx_ARCHITECTURE_AUDIT.md` document exists for any of them.** There is therefore nothing to check current behavior *against* — the absence of a formal document is not, by itself, evidence that anything is wrong or missing. These EPs are classified **UNVERIFIABLE (no audit baseline)**, not MATCH (there is no claim to match against) and not MISSING (the implementation and tests are demonstrably present and passing).
- **EP004–EP017:** a special case. `git log --oneline` shows real, individually-labeled commits for every one of these numbers (e.g. `1b359e8` "EP-004: Implement Test Framework with automated test runner," `f279963` "EP-013: implement enterprise Memory & Context Manager," `2b16130`/`9fa2e3c`/`dde2452` "EP-015"/"EP-015.2"/"EP-015.3" for the Anthropic/Gemini provider work, `d7a441a` "EP-017: implement provider-independent Prompt Engine"), but **none of these numbers has a surviving `tests/EPxxx/` directory, design document, audit document, or CHANGELOG entry in the current repository.** No commit removing or renumbering these deliverables was found. The most plausible explanation, consistent with the evidence, is that these EPs' actual deliverables were carried forward and subsumed into later, unnumbered project structure (for example, EP004's "Test Framework" commit corresponds directly to what is now the unnumbered `src/testing/` package that every later EP's tests depend on) as the project's documentation and numbering conventions were established and tightened starting around EP018/EP036. This range is classified **UNVERIFIABLE (no audit baseline / historical)**, and — per this audit's explicit scope instructions — was not deep-audited beyond establishing this git-history context, since it sits entirely outside the formal STEP-3 audit system this retrospective audit was built to verify.

**In all cases, the absence of formal design/audit documentation for these EP ranges was never treated as evidence of a missing or broken implementation.**

---

# Final Audit Verdict

## ACTION REQUIRED — MATERIAL DRIFT FOUND

The overwhelming majority of this repository's historical documentation record is accurate: **66 of the 70 implemented, audit-eligible EPs are clean MATCHes**, and every STEP-3 "fixed" claim sampled across EP039 through EP092 — including EP092's complete three-round remediation history and EP069.x's cost-validation and exception-hierarchy fixes — was independently confirmed present in the current source, not merely trusted from documentation. The "future roadmap" numbering gaps (EP070–EP081, EP084–EP091) are correctly and consistently documented as intentional forward planning, not lost or missing implementation.

However, the baseline **cannot** be certified as a clean PASS, because of the following, in priority order:

1. **EP039 — MATERIAL functional drift.** `github_service.py`'s URL path-segment quoting does not encode `/` as claimed; the audit's own named regression test fails when actually run (43 passed / 1 failed, isolated). Present since the original EP039 commit; not a regression.
2. **EP041 — MATERIAL functional drift.** Identical defect class in `discord_service.py`; the audit's claim that its regression test "confirm[ed] ... %2F encoding" is false (40 passed / 1 failed, isolated). Present since the original EP041 commit; not a regression. The originating commit is also mislabeled as completing EP040.
3. **TestRegistry collision affecting EP038–EP042** — a test-infrastructure defect (silent suite overwrite via shared `NAME` keys) that is the direct mechanism by which Findings 1 and 2 went undetected through every subsequent regression run, despite EP042's own audit having already identified the collision's existence (but not its consequences for EP039/EP041) months earlier.
4. **EP056 — documentation/test-count drift.** Audit claims 51/0/0; actual, unchanged-since-creation suite is 62/0/0; no reconciling document exists. No functional defect.
5. **EP082 — documentation/hygiene drift.** Missing dedicated audit artifact (unique among EP036–EP092); one orphaned, byte-identical duplicate source file. No functional defect — every substantive technical claim checked out true.
6. **EP046 — minor test-count discrepancy** (58 vs. 57 reported), no functional defect.
7. **EP048 — environment limitation**, not an implementation failure: `openwakeword`'s `tflite-runtime` dependency is unavailable on this sandbox's platform/Python version, leaving 2 of its assertions genuinely UNVERIFIABLE rather than passing or failing.
8. All other verified, implemented EPs (EP036–EP038, EP040, EP042–EP045, EP047, EP049–EP069 incl. all EP069.x sub-EPs, EP083, EP092) are **broadly and, in most cases, exactly consistent** with their existing documentation, including self-documented, legitimate test-suite growth over time.
9. Future-roadmap EPs (EP070–EP081, EP084–EP091) are **not** missing-implementation defects; their absence is intentional, current, and correctly documented.

**The repository requires corrective work — specifically, fixing the EP039 and EP041 URL-encoding defects and addressing the TestRegistry collision that hid them — before the EP-001–EP-092 historical baseline should be treated as fully trustworthy.** No other finding in this audit rises to a level that would, on its own, prevent that certification; it is specifically the combination of two real, currently-live functional defects and a test-infrastructure gap that actively concealed them from every audit and regression run since their introduction that drives this verdict.

---

## Recommendations

*(Recorded for future action only. Nothing in this section was implemented as part of this audit or this documentation task.)*

### Immediate Technical Repairs
- **EP039:** Correct `src/services/github_service.py`'s `quote()` calls to use `safe=''` (or an equivalent guarantee that `/` is percent-encoded in path segments), and correct `EP039_ARCHITECTURE_AUDIT.md`'s factually incorrect claim about this behavior.
- **EP041:** Apply the identical correction to `src/services/discord_service.py`; correct `EP041_ARCHITECTURE_AUDIT.md`'s factually incorrect claim; consider correcting the commit-message/EP-attribution record for `19de629`.
- **TestRegistry multi-suite collision:** Give each paired `_module.py`/`_service.py` test file (EP038, EP039, EP040, EP041, EP042) a unique `NAME`, or extend `TestRegistry`/`TestRunner` to support and execute multiple suites per EP, so a single `test EPxxx` invocation can no longer silently skip half of an EP's own test coverage.

### Documentation Cleanup
- **EP056:** Reconcile the audit's reported 51/0/0 figure against the actual, unchanged-since-creation 62/0/0 test suite — most likely a simple correction of a transcription error in the original STEP 3 report.
- **EP082:** Produce a proper, dedicated `EP082_ARCHITECTURE_AUDIT.md` reflecting the STEP 3 findings currently only recorded inline in `JARVIS_ROADMAP.md` (or explicitly document that this folding-in was an intentional, permanent choice for this EP specifically). Separately, remove the orphaned, unreferenced duplicate `src/core/ai/text_generation_service.py`.
- **EP046:** Investigate and reconcile the minor 57-vs-58 test-count discrepancy for completeness, though it carries no functional risk.

### Future Process Improvements
- Ensure every EP's sub-suites (module/service, or any other file split) can always be executed both independently and in combination, with no silent overwrite possible.
- Prevent `TestRegistry` key collisions structurally (e.g. namespacing by file, or raising an error on duplicate registration) rather than relying on individual EPs' authors to notice and work around the issue.
- Ensure that STEP 3 audit claims about specific test behavior are verified against suites that are actually, provably executed at audit time — not merely assumed to run because a `test EPxxx` command returned a plausible-looking number.
- Preserve STEP 3 "final changed-file" snapshots (as EP092's audit already does well, in its §18.2 "Scope" diff-against-pristine-baseline check) as a standard practice for every future EP, to make this kind of retrospective consistency check faster and more reliable.
- Maintain explicit, bidirectional traceability between any STEP 3 fix and the audit document paragraph that claims it — including, where a fix is later superseded or found incomplete (as happened between EP069.2's deferred finding and EP069.3's actual fix), a clear forward/backward pointer between the two audit documents.

---

## Audit Integrity Statement

This document records the results of the retrospective, read-only consistency audit of EP-001 through EP-092 that was completed prior to this document's creation. **It is a historical audit artifact and does not represent a new STEP 3 execution for each EP** — no new architecture review, design revision, or STEP 3 process was performed or claimed for any individual EP as part of producing this document.

During **this specific documentation-export task**:

- **No source files were changed.**
- **No test files were changed.**
- **No configuration files were changed.**
- **No existing EP design or architecture-audit documentation was changed.**
- **No roadmap, backlog, changelog, or release-notes file was changed.**
- **Only this new retrospective audit report — `docs/architecture/audits/EP001_EP092_RETROSPECTIVE_CONSISTENCY_AUDIT.md` — was created.**

No bug identified in this document (EP039, EP041, or otherwise) was fixed, worked around, or otherwise altered in the course of producing this report.
