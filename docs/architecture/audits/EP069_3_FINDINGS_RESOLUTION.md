# EP-069.3 — STEP 3.1: Findings Resolution
## Cost-Aware AI Provider Selection

Status: STEP 3.1 COMPLETE — READY FOR STEP 4 (pending Owner sign-off)

---

## 1. Resolution Scope

This document is the formal STEP 3.1 resolution record for the six
findings reported in
`docs/architecture/audits/EP069_3_ARCHITECTURE_AUDIT.md` (STEP 3).
Per the governing instructions for this step, exactly two findings
(EP069.3-AUDIT-001, EP069.3-AUDIT-002) were approved for a fix in
STEP 3.1; the remaining four were classified as deferred or inherited
and were explicitly **not** touched. No STEP 3.1 finding disposition
in this document overrides or reclassifies the mandatory
classification supplied for this step — this document records the
verification evidence for that classification, not a re-litigation of
it. No new architecture audit was performed; the original STEP 3
audit document was preserved in full and only extended with a
resolution-status addendum (its own Section 18).

## 2. Source Documents

- `docs/architecture/designs/EP069_3_DESIGN.md`
- `docs/architecture/audits/EP069_3_ARCHITECTURE_AUDIT.md` (STEP 3,
  Sections 15–17 for original findings; Section 18 addendum added by
  this step)
- `docs/architecture/designs/EP069_2_DESIGN.md`
- `docs/architecture/audits/EP069_2_ARCHITECTURE_AUDIT.md`
- `docs/architecture/audits/EP069_2_FINDINGS_RESOLUTION.md`

EP-069.2 was used only as read-only architectural context. It was not
redesigned, and none of its implementation or test files were
modified in this step.

## 3. Finding Classification

| Finding | Severity | Classification |
|---|---|---|
| EP069.3-AUDIT-001 | MEDIUM | FIX BEFORE STEP 4 |
| EP069.3-AUDIT-002 | LOW-MEDIUM | FIX BEFORE STEP 4 |
| EP069.3-AUDIT-003 | LOW | TEST IMPROVEMENT — CAN DEFER |
| EP069.3-AUDIT-004 | LOW | TEST IMPROVEMENT — CAN DEFER |
| EP069.3-AUDIT-005 | LOW | TEST IMPROVEMENT — CAN DEFER |
| EP069.3-AUDIT-006 | LOW/MEDIUM (inherited) | INHERITED / DEFERRED FROM EP-069.2 |

FIX BEFORE STEP 4: 2. TEST IMPROVEMENT — CAN DEFER: 3.
INHERITED/DEFERRED: 1. DESIGN UPDATE REQUIRED: 0.

## 4. AUDIT-001 Resolution — FIXED

**Original finding (unchanged, see audit Section 8.1/15):**
`ProviderManager` did not independently validate `relative_cost`;
`bootstrap.py` was the only layer enforcing "numeric, non-bool,
finite, >= 0," so a `ProviderManager` constructed directly (bypassing
`bootstrap.py`) could treat `NaN`/`Infinity`/negative/`bool` values as
legitimate known costs.

**Fix implemented:** A new module-level predicate,
`_is_valid_relative_cost(value)`, was added to
`src/core/ai/provider_manager.py`, re-implementing the exact same
validity rule `bootstrap.py`'s `_parse_relative_cost()` already
enforces (reject `bool` explicitly before the numeric check, reject
non-`int`/`float`, reject non-finite, reject negative).
`ProviderManager.__init__` now builds `self._relative_cost` by
filtering every incoming `(name, cost)` pair through this predicate,
so an invalid entry is silently dropped — treated exactly like an
absent entry (unknown cost) — regardless of whether the caller
already validated it.

This intentionally duplicates only the pure predicate, not
`bootstrap.py`'s logging/warning responsibility: `ProviderManager` has
no configuration key name to attribute a warning to at this layer (it
only ever sees a plain, already-provider-keyed mapping), and
`bootstrap.py` already warns on every value it rejects in the one real
configuration path. This is the smallest change that closes the gap
without introducing a second configuration/validation architecture,
per the mandatory constraint for this fix.

**Files changed:** `src/core/ai/provider_manager.py` only.

**Verification (independently re-run in this step, not merely
re-reading the fix):**

- Constructed `ProviderManager` directly (bypassing `bootstrap.py`)
  with `relative_cost={"claude": float("nan"), "gemini": True,
  "openai": 2.0}`, `cost_aware_enabled=True`. Result across 3 repeated
  calls: `["openai", "claude", "gemini"]` — `openai` (the one real,
  valid cost) sorts first; `claude` (`NaN`) and `gemini` (`bool`) both
  fall into the unknown-cost group and sort alphabetically between
  themselves. No crash. No provider excluded. Deterministic across
  repeated calls.
- Constructed with `{"claude": "bad", "gemini": [1, 2], "openai":
  {"a": 1}}` (string, list, dict) — all three treated as unknown,
  alphabetical order preserved, no crash, no exclusion.
- Constructed with `{"claude": -5.0, "gemini": "bad", "openai": [1,
  2]}` — same result: all invalid, all unknown, no crash.
- Constructed with `{"claude": 0.0, "gemini": 5.0}` (openai
  unconfigured) — confirms the fix does **not** regress valid-value
  handling: `claude` (`0.0`) still sorts first as the cheapest known
  cost, ahead of `gemini` (`5.0`) and `openai` (unknown).
- Constructed with `default_provider="claude"` and
  `relative_cost={"claude": float("nan"), "gemini": 0.01}` —
  `get_current().name()` still returns `"claude"`: sanitizing an
  invalid cost has zero effect on primary/current provider selection.
- `_is_valid_relative_cost()` itself was exercised directly against
  all fourteen cases from `EP069_3_DESIGN.md`/the STEP 2 task's
  required-coverage list: `True`, `False`, `None`, a string, a list, a
  dict, a negative float, `NaN`, `+Infinity`, `-Infinity` (all
  correctly `False`), and `0`, `0.0`, a positive `int`, a positive
  `float` (all correctly `True`).

Six new test methods (23 individual assertions) were added to
`tests/EP069_3/test_cost_aware_provider_selection.py` under a new
"ProviderManager direct-construction sanitization (EP069.3-AUDIT-001
fix)" section, reproducing every scenario above as a permanent
regression test — not merely verified ad hoc. This is fixing the new
code this step introduces, not expanding scope into the deferred
AUDIT-003/004/005 test gaps (which remain about the pre-existing
`bootstrap.py`-level validation, untouched here).

**Design/architecture impact:** None beyond `ProviderManager` itself.
No configuration key, no new logging behavior, no change to
`bootstrap.py`, no change to the cost model or ordering algorithm
(`EP069_3_DESIGN.md` Sections 9/14 are unaffected — this fix only
makes an already-documented invariant self-enforcing).

## 5. AUDIT-002 Resolution — FIXED

**Original finding (unchanged, see audit Section 5/13/15):**
`src/services/ai_service.py`'s `ask()` docstring stated fallback
candidates are retried "in that registry's deterministic, name-sorted
order" — stale since EP-069.2 and further inaccurate after EP-069.3.

**Fix implemented:** The docstring passage was rewritten to describe
the order as deterministic but not necessarily name-sorted, noting
that a configured fallback order or a cost-aware preference from later
EPs can change it, and pointing to
`ProviderManager.list_fallback_candidates()`'s own docstring as the
authoritative, current description of the algorithm — rather than
re-describing the full algorithm inline a second time (which is what
allowed it to drift out of date in the first place).

**Files changed:** `src/services/ai_service.py` — docstring text only,
within the existing EP-069.1 documentation paragraph of `ask()`.

**Verification:**
- Confirmed the edit is docstring-only: diffed the file against its
  pre-STEP-3.1 state; the only change is the replaced sentence.
- Confirmed no runtime behavior changed: `ai_service.py`'s executable
  code (every line outside the docstring) is byte-identical to its
  state before this fix — the file's own fallback loop, exception
  handling, and `AskResult` construction are untouched.
- `tests/EP069/test_ai_provider_fallback.py` (68/68) and
  `tests/EP069_2/test_provider_fallback_ordering.py` (26/26) both
  re-run after this change with zero failures, confirming the
  docstring-only nature of the fix empirically as well as by
  inspection.

**Design/architecture impact:** None. Documentation correction only,
as required.

## 6. AUDIT-003 Deferred

No implementation or test change made. `_parse_relative_cost()`'s
handling of `list`/`dict`-typed input was already independently
verified correct during STEP 3 (audit Section 8) and is unaffected by
either fix in this step. Remains an open, non-blocking test-coverage
item for a future pass.

## 7. AUDIT-004 Deferred

No implementation or test change made. A `0.0` `relative_cost`'s
correct behavior at the `ProviderManager` ordering level was
independently verified during STEP 3 (audit Section 8) and was
additionally re-confirmed as a side effect of AUDIT-001's own
verification (Section 4 above, third bullet) — but no dedicated
standalone regression test for this exact scenario (independent of the
AUDIT-001 fix) was added, since AUDIT-004 itself was explicitly
excluded from this step's scope.

## 8. AUDIT-005 Deferred

No implementation or test change made. The structural guarantee that
eligibility (`exclude` + `is_available()`) is computed before either
`fallback_order` or `relative_cost` is consulted — which makes a name
present in both `exclude` and `fallback_order` behave correctly by
construction — was independently re-confirmed during STEP 3 (audit
Section 11) and is unaffected by either fix in this step. Remains an
open, non-blocking test-coverage item.

## 9. AUDIT-006 Inherited / Deferred

No action taken. This finding is EP-069.2's own
`EP069.2-AUDIT-001` (unhashable `fallback_order` element crashes
`list_fallback_candidates()`), carried forward for completeness in the
EP-069.3 audit. It is not introduced or altered by EP-069.3, and
`src/core/ai/provider_manager.py`'s `fallback_order`-partitioning code
path (the one containing this defect) was not touched by either fix in
this step — confirmed by diff: both fixes are additive
(`_is_valid_relative_cost`, the `relative_cost` sanitization
comprehension, and the docstring edit) and touch neither the
`fallback_order` loop nor its `seen`/`eligible_by_name` logic.
`tests/EP069_2/` was not modified. This remains tracked exclusively
under EP-069.2's own `EP069_2_FINDINGS_RESOLUTION.md` as a deferred
fast-follow, independent of EP-069.3.

## 10. Validation Results

### Targeted suites (this step)

| Suite | Result |
|---|---|
| EP-069.3 | 80/80 passed (57 from STEP 2/3 + 23 new assertions across 6 new AUDIT-001 verification tests) |
| EP-069.2 | 26/26 passed, unmodified |
| EP-069.1 | 68/68 passed, unmodified |

### Direct-construction adversarial verification (this step, beyond the automated tests)

All of the following were independently executed against the real,
fixed `ProviderManager`, not merely asserted by a test:

- `True`, `False`, `None`, string, list, dict, negative, `NaN`,
  `+Infinity`, `-Infinity` each individually confirmed to sanitize to
  "unknown cost" via `_is_valid_relative_cost()` directly.
- A `ProviderManager` constructed directly with a mix of these invalid
  values plus one valid value confirmed: no crash; no excluded
  provider; the valid value still sorts correctly; the invalid values
  group together, alphabetically, after it; result is identical across
  repeated calls (deterministic).
- `0.0` and positive finite values confirmed to remain valid and to
  sort correctly relative to both a higher valid cost and an
  unconfigured (unknown) provider.
- The primary/current provider (`get_current()`) confirmed unaffected
  by an invalid `relative_cost` for that same provider.
- EP-069.2's `fallback_order` ordering, verified via its own untouched
  test suite (26/26), confirmed intact and un-reordered by either fix.

### Full regression suite

7370 passed / 2 failed / 3 skipped (up from the STEP 2/STEP 3 baseline
of 7347 passed, by exactly the 23 new EP-069.3 assertions added in
this step; no other suite's pass count changed). The 2 failures are in
`EP048` (Wake Word) — pre-existing, environment-only (missing
`openwakeword`/`tflite-runtime` in this sandbox), unrelated to any
file touched in this step, and identical in count and identity to the
STEP 2 and STEP 3 baselines.

## 11. Final STEP 3.1 Verdict

**READY FOR STEP 4.**

Both approved findings (EP069.3-AUDIT-001, EP069.3-AUDIT-002) are
fixed and independently re-verified, including adversarial
reproduction of the exact scenarios the STEP 3 audit used to surface
them. EP-069.1 and EP-069.2 remain fully green and structurally
untouched. No deferred or inherited finding (AUDIT-003/004/005/006)
was fixed, redesigned, or otherwise touched, per this step's explicit
scope limit. No new blocking issue was introduced by either fix. No
Git operation was performed. No STEP 4 documentation
(`CHANGELOG.md`, `docs/BACKLOG.md`, `docs/RELEASE_NOTES.md`,
`docs/architecture/JARVIS_ROADMAP.md`) was created or modified.
