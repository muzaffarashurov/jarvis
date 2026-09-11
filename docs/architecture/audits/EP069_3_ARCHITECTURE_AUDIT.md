# EP-069.3 — Independent Architecture Audit
## Cost-Aware AI Provider Selection

STEP 3: Independent Adversarial Architecture Audit

Status: AUDIT COMPLETE — awaiting Owner decision on findings before STEP 3.1/STEP 4

---

## 1. Audit Scope

This audit independently reviews the EP-069.3 STEP 2 implementation
against `docs/architecture/designs/EP069_3_DESIGN.md`, verifies its
integration with the already-completed EP-069.1 and EP-069.2
architecture, and reports findings. No production code, test,
configuration, or design document was modified to produce this audit.
This document is the only file created in STEP 3.

Per the governing instructions, this audit does not accept the STEP 2
report's own claims at face value: every claim below was independently
re-verified against the actual source tree, including direct,
adversarial reproduction of edge cases (NaN/Infinity sort safety, list/
dict-typed configuration, zero-cost handling) rather than trusting the
STEP 2 test suite's assertions alone.

## 2. Sources Reviewed

- `docs/architecture/designs/EP069_3_DESIGN.md` (full).
- `src/core/ai/provider_manager.py` (full, current working tree).
- `src/bootstrap.py` — the EP-069.3 additions (`_parse_cost_aware_enabled`,
  `_parse_relative_cost`, `_parse_provider_relative_costs`) and their
  call site.
- `config/config.yaml` — `ai.cost_aware_enabled`, `ai.fallback_order`,
  and every `providers.<name>.relative_cost` comment block.
- `src/modules/test_module.py`.
- `tests/EP069_3/test_cost_aware_provider_selection.py` (full, 34 test
  methods).
- `tests/EP069_2/test_provider_fallback_ordering.py` (full, for
  compatibility verification).
- `tests/EP069/test_ai_provider_fallback.py` (for EP-069.1
  compatibility verification).
- `src/services/ai_service.py`'s `ask()` (unmodified; reviewed to
  confirm both that claim and to check its own documentation currency).
- `src/core/ai/provider.py`, `src/core/ai/provider_registry.py`,
  `src/core/ai/claude_provider.py`,
  `src/core/ai/providers/gemini_provider.py`,
  `src/core/ai/provider_factory.py` (diffed byte-for-byte against the
  pristine pre-EP-069.2 tree).
- `ep069_2_changed_files.zip`: `docs/architecture/designs/EP069_2_DESIGN.md`,
  `docs/architecture/audits/EP069_2_ARCHITECTURE_AUDIT.md`,
  `docs/architecture/audits/EP069_2_FINDINGS_RESOLUTION.md` — read in
  full as architectural context, particularly EP-069.2's own carried-
  forward findings (Section 4 below).

## 3. Architecture Summary

`ProviderManager.list_fallback_candidates()` now performs, in order:

1. Compute `eligible` — unchanged eligibility rule (`is_available()`
   and not in `exclude`), identical to EP-069.1.
2. If `fallback_order` (EP-069.2) is non-empty: partition `eligible`
   into `ordered` (candidates named in `fallback_order`, in its
   sequence, deduplicated) and `unlisted` (everyone else, in
   registry-alphabetical order). If empty: `ordered = []`,
   `unlisted = eligible`.
3. If `cost_aware_enabled` (EP-069.3) is true: re-sort `unlisted` by
   `(known/unknown group, relative_cost ascending, name ascending)`.
   Otherwise `unlisted` keeps its order from step 2 unchanged.
4. Return `ordered + unlisted`.

`relative_cost` and `cost_aware_enabled` are read once, at
`bootstrap.py`'s composition root, through two new validating helper
functions, and passed into `ProviderManager.__init__` as already-
sanitized values. `AIProvider`, `ProviderResponse`, `AIService`, and
`ProviderRegistry` are untouched.

## 4. EP-069.2 Compatibility Review

Verified directly against `tests/EP069_2/test_provider_fallback_ordering.py`
(26/26 passing, unmodified — confirmed byte-identical to the archive)
and by code inspection:

- **`fallback_order` priority.** Confirmed structurally, not just by
  test: `ordered`/`unlisted` partitioning happens entirely before the
  cost-aware sort is even considered (`provider_manager.py` lines
  271–289); the cost-aware `sorted()` call is applied only to
  `unlisted`, never to `ordered`. A candidate `fallback_order` has
  already placed cannot be moved by cost, by construction.
- **Deduplication.** The `seen: set[str]` guard from EP-069.2 is
  untouched; EP-069.3 adds no second deduplication path.
- **Availability/exclusion.** `eligible` is computed once, before
  either `fallback_order` or `relative_cost` is consulted — the same
  structural guarantee EP-069.2's own audit relied on (its Section
  8.5) extends unbroken through EP-069.3's addition.
- **Unknown provider names in `fallback_order`.** Unaffected — still
  simply never matched, verified via
  `_test_unmatched_fallback_order_name_has_no_effect_alongside_cost`.
- **Determinism.** `EP069_2_ARCHITECTURE_AUDIT.md`'s own findings
  (Section 4 below) are unaffected by EP-069.3's addition — the same
  code paths, unchanged.
- **New composition tests.** Five tests
  (`tests/EP069_3/test_cost_aware_provider_selection.py`,
  `_test_fallback_order_takes_priority_over_cost_for_listed_names`
  through `_test_unmatched_fallback_order_name_has_no_effect_alongside_cost`)
  exercise the real, combined `fallback_order` + `relative_cost`
  behavior end-to-end against a real `ProviderManager` — not mocked.

**No EP-069.2 semantics are changed, bypassed, or duplicated.**
`ai.fallback_order` has exactly one implementation, in
`list_fallback_candidates()`; EP-069.3 does not introduce a second
ordering mechanism elsewhere.

## 5. EP-069.1 Compatibility Review

`tests/EP069/test_ai_provider_fallback.py` — 68/68 passing, confirmed
byte-identical to the pre-EP-069.2/EP-069.3 archive (no lines added,
removed, or reordered). `AIService.ask()`'s fallback loop
(`src/services/ai_service.py` lines 468–604) is byte-identical to the
pristine pre-EP-069.2 tree. The loop's termination guarantee (`attempted`
strictly grows every iteration and is passed as `exclude`, so the
eligible set is strictly non-increasing) is structurally independent of
candidate *order* — cost-aware ordering changes which candidate is
tried at each step, never whether the loop terminates. Reviewed for:
exception classification (`_FALLBACK_ELIGIBLE_ERRORS` — untouched),
recursive calls (none — the loop is a single `while True` with no
recursion), unbounded loops (impossible — bounded by strictly-shrinking
`remaining`). No regression found.

**One documentation-currency issue found here — see Finding
EP069.3-AUDIT-002.**

## 6. Backward Compatibility Review

Verified by direct code inspection, not merely by test:

- `cost_aware_enabled = False` (the default): `list_fallback_candidates()`'s
  final `if self._cost_aware_enabled: unlisted = sorted(...)` branch is
  skipped entirely — `unlisted` is returned exactly as EP-069.2's own
  partitioning produced it. This is byte-for-byte the same code path
  EP-069.2 exercises alone; EP-069.3 adds a branch, not a rewrite.
- Absent `ai.cost_aware_enabled`/`providers.*.relative_cost` in
  `config.yaml`: both are commented-out/absent in the shipped default
  config; `config.get(..., False)`/`config.get(..., _RELATIVE_COST_ABSENT)`
  both resolve to their documented defaults with **zero** log output
  (verified directly — see Section 10).
- No existing key was renamed, removed, retyped, or repurposed —
  diffed against the EP-069.2 archive's `config.yaml`
  (`config/config.yaml`): every line removed by the diff is the single
  `fallback_order: []` line replaced by the same line plus new,
  additive content immediately after it.
- `ProviderManager.__init__`'s pre-existing positional/keyword
  contract for `registry`, `enabled`, `default_provider` is unchanged;
  the two new parameters are keyword-defaulted, so any caller
  constructing `ProviderManager` exactly as EP-069.1 always did (no
  `fallback_order`, no cost arguments) gets identical behavior —
  verified by `_test_provider_manager_default_constructor_args_unchanged`.

**No backward-compatibility regression found.**

## 7. Configuration Validation Review

Directly re-executed (not merely re-read) `bootstrap.py`'s three new
functions against every case in `EP069_3_DESIGN.md` Section 15 plus
several the STEP 2 report's own test suite did not itself directly
exercise:

| Input to `relative_cost` | Result | Verified how |
|---|---|---|
| absent | `None`, 0 warnings | test + direct call |
| `0` / `0.0` | `0.0` (valid, known-cost) | test (`_parse_relative_cost` level) + **direct `ProviderManager`-level reproduction in this audit** (Section 8) |
| `True` / `False` | `None`, 1 warning | test |
| string (`"3.0"`) | `None`, 1 warning, not coerced | test |
| `None`/`null` | `None`, 1 warning | test |
| negative | `None`, 1 warning | test |
| `NaN` | `None`, 1 warning | test |
| `+Infinity` / `-Infinity` | `None`, 1 warning | test |
| **`list`** (e.g. `[1, 2, 3]`) | `None`, 1 warning | **not covered by any STEP 2 test — independently reproduced in this audit (Section 8); implementation is correct** |
| **`dict`** (e.g. `{"a": 1}`) | `None`, 1 warning | **not covered by any STEP 2 test — independently reproduced in this audit (Section 8); implementation is correct** |

`ai.cost_aware_enabled`: absent → `False`, 0 warnings; valid bool →
honored, 0 warnings; invalid type → `False`, 1 warning naming key and
type. All independently re-executed and confirmed.

Multiple providers with a mix of valid/invalid/absent `relative_cost`
in a single `_parse_provider_relative_costs()` call were independently
re-executed in this audit (Section 8): each malformed provider
produces **exactly one** warning (no duplication, no warning
suppression of subsequent providers) and the resulting mapping
contains only the valid entries.

## 8. Cost Ordering Review (Independent Reproduction)

This audit did not rely on the STEP 2 test suite's own assertions for
the highest-risk claims (bool rejection, NaN/Infinity safety, zero
handling); each was independently reproduced against the real,
unmodified source in this session.

- **`True`/`False` rejection confirmed independently.** `isinstance(raw, bool)`
  is checked before the `isinstance(raw, (int, float))` fallthrough in
  `_parse_relative_cost` — verified by reading the exact code path, not
  merely by re-running the existing test.
- **`0.0` confirmed valid and distinct from "unknown".** Independently
  constructed a real `ProviderManager` with `relative_cost={"claude":
  0.0, "gemini": 5.0}` and a third, unconfigured provider `"openai"`;
  result: `["claude", "gemini", "openai"]` — `claude` (cost `0.0`)
  correctly sorts first as the cheapest *known* cost, `openai` correctly
  sorts last as unknown. This exact scenario is **not exercised by any
  test in `tests/EP069_3/`** at the `ProviderManager`/ordering level
  (only at the `_parse_relative_cost` unit level) — see Finding
  EP069.3-AUDIT-004.
- **`list`/`dict`/`tuple`-typed `relative_cost` independently
  reproduced.** All three fall through `isinstance(raw, (int, float))`
  correctly, are logged once each with the correct observed type
  name (`list`, `dict`, `tuple`), and never raise. **Not covered by any
  dedicated test** despite being explicitly required test coverage in
  the STEP 2 task's own Section 13 — see Finding EP069.3-AUDIT-003.

### 8.1 NaN/Infinity sort-safety: a real, reproduced gap in defense-in-depth

`bootstrap.py`'s validation guarantees that **values it produces** are
always finite and non-negative before they ever reach
`ProviderManager`. However, `ProviderManager.__init__` itself performs
**no independent validation** of the `relative_cost` mapping it is
given — its own docstring's claim ("every value here is guaranteed to
be a finite, non-negative, non-bool `float`") is a documented
*expectation of the caller*, not a *guarantee the class itself
enforces*.

This audit independently constructed a `ProviderManager` directly
(bypassing `bootstrap.py` entirely — the only production call site)
with `relative_cost={"claude": float("nan"), "gemini": 1.0, "openai": 2.0}`
and `cost_aware_enabled=True`, then called `list_fallback_candidates()`
five times:

```
trial 0 -> ['claude', 'gemini', 'openai']
trial 1 -> ['claude', 'gemini', 'openai']
... (identical across all 5 trials)
```

Findings from this reproduction:
- **No crash, no exception, no provider disappearance** — `sorted()`
  with a `NaN` in the tuple's second position does not raise in
  CPython; the process completes normally regardless of the group
  sharing a NaN or not (also verified with two simultaneous NaN-cost
  providers).
- **Result is repeatable within a run** (same input always produces
  the same output, since CPython's Timsort is a deterministic function
  of its input) — so the letter of "determinism" (Section 13's
  concern) is not violated.
- **However, the result is semantically wrong relative to the design's
  own invariant.** A `NaN` cost is placed in the *known*-cost sort
  group (`_KNOWN_COST_SORT_GROUP`, since `cost is None` is `False` for
  `NaN`) and, in this reproduction, sorted to the very front — ahead of
  a legitimately cheaper, real-valued provider. The design
  (`EP069_3_DESIGN.md` Section 15 case 6, Section 9) states such a
  value "must be treated exactly as unknown cost" — that guarantee is
  currently true only because `bootstrap.py` is the sole caller and
  always filters `NaN` out before construction, not because
  `ProviderManager`/`_cost_sort_key` itself enforces it.
- The same reproduction with `+Infinity`/`-Infinity` produced the same
  class of result: no crash, deterministic-within-run, but
  `-Infinity` and `+Infinity` are both treated as ordinary "known"
  costs rather than unknown, contrary to design intent if this path
  were ever reached.

**This is not a currently-exploitable production defect** — the only
code path that constructs a real `ProviderManager` is `bootstrap.py`,
and it always validates first (confirmed by inspection of the single
call site in `_build_ai_service`/equivalent). It **is** a genuine
defense-in-depth gap: the invariant the design promises is enforced at
exactly one layer, with no redundancy, and the component that performs
the actual sort does not itself defend the guarantee its own docstring
claims. See Finding EP069.3-AUDIT-001.

## 9. Determinism Review

- Registry base order: `ProviderRegistry.list()`'s existing sort by
  `name()` — unchanged, confirmed via `provider_registry.py`'s diff
  (byte-identical to pristine).
- `fallback_order` partitioning: list iteration order over
  `self._fallback_order`, unchanged from EP-069.2.
- Cost-aware sort: `sorted()` (stable) over a tuple key with no
  reliance on dict/set iteration order for the *returned* order — `set`
  is used only for O(1) membership tests (`excluded`, `seen`), never
  iterated for ordering purposes. `dict` (`_relative_cost`,
  `eligible_by_name`) is used only for `.get()`/keyed lookups, never
  iterated for ordering purposes either. No accidental reliance on
  hash/insertion order was found.
- Repeated-call determinism independently re-confirmed in this audit
  (Section 8.1) even for the NaN/Infinity edge case, beyond what the
  STEP 2 test suite itself exercises.

**No determinism defect found**, subject to the semantic (not
stability) caveat in Section 8.1.

## 10. Logging / Warning Review

- Exactly one warning per malformed value, independently re-verified
  in this audit with a multi-provider, mixed-validity configuration
  (Section 7) — no duplication, no suppression.
- Warnings are emitted only at `bootstrap.py`'s composition-root call
  (once per process startup), never inside `list_fallback_candidates()`
  itself — confirmed no per-request or per-fallback-attempt logging
  exists in the cost-aware code path, so no warning-storm risk exists
  under repeated `ask()` calls.
- No raw configuration value is logged in any reviewed warning message
  — every message names only the configuration key, the provider name,
  and either `type(value).__name__` or a fixed, closed-set phrase
  ("must be finite", "must be >= 0", "a boolean is not a valid
  relative_cost"). Independently confirmed with a value designed to
  look like a secret (`"SECRET-LOOKING-VALUE-4f9c"`) — it does not
  appear in any log line.
- An absent key never warns; only a present-but-invalid value does —
  independently re-confirmed.
- No provider is silently removed by an invalid cost — confirmed
  structurally (Section 6, Section 8) and by test.

**No logging/security defect found.**

## 11. Availability / Exclusion Review

Confirmed structurally (Section 4) that `eligible` is computed once,
before `fallback_order` or `relative_cost` is consulted at all — cost
can only reorder what is already eligible, never expand or shrink it.
Verified for: an unavailable provider (excluded regardless of a
favorable cost — test), an already-attempted/excluded provider
(excluded regardless of cost — test), an unregistered `fallback_order`
name (inert, regardless of cost — test). One combination was not
independently found in the test suite: a provider name that is
simultaneously (a) present in `exclude`, and (b) also named in
`fallback_order`, under `cost_aware_enabled=True`. This is
structurally guaranteed correct by the same "eligible computed first"
argument (Section 4), and this audit independently re-confirmed that
argument holds by reading the method body directly rather than
accepting it as asserted — but no dedicated regression test exists for
this exact combination. See Finding EP069.3-AUDIT-005 (test gap only;
no defect).

## 12. Test Quality Review

`tests/EP069_3/test_cost_aware_provider_selection.py` — 34 test
methods, 57 assertions-worth of `run()` calls, all against a real
`ProviderManager`/`ProviderRegistry` (never a mocked
`list_fallback_candidates()`), and one test
(`_test_fallback_loop_continues_after_cost_selected_candidate_fails`)
against a real `AIService` with real `ProviderManager` wiring. Tests
are meaningfully falsifiable — this audit confirmed this directly by
finding that one test's own expected value was wrong during STEP 2
(`_test_fallback_order_takes_priority_over_cost_for_listed_names`,
corrected before STEP 2 concluded) and the suite correctly failed
until it was fixed, rather than trivially passing.

Coverage confirmed present: `cost_aware_enabled` false/true/invalid-type;
ascending-cost ordering; lower-cost-before-higher-cost; higher-cost
remains eligible; equal-cost tie-break; single and multiple unknown-cost
providers; missing `relative_cost`; `bool` (both `True` and `False`
tested separately — a naive test suite testing only one would have
missed the `isinstance(x, bool)` requirement); string; `None`; negative;
`NaN`; `+Infinity`/`-Infinity`; availability filtering; exclusion
filtering; primary/current-provider isolation; deterministic repeated
calls; `AIService` fallback-loop continuation after a cost-preferred
candidate fails; bootstrap wiring end-to-end; `fallback_order` +
`relative_cost` composition (5 dedicated tests); backward-compatible
default construction.

**Coverage gaps found** (all test-only; the underlying implementation
was independently verified correct for each in Section 8 above):
- No test with `relative_cost` set to a `list` or `dict` value
  (EP069.3-AUDIT-003).
- No `ProviderManager`-level (ordering) test for a literal `0`/`0.0`
  `relative_cost` — only the `_parse_relative_cost` unit level is
  covered (EP069.3-AUDIT-004).
- No test for a provider name present in both `exclude` and
  `fallback_order` simultaneously, under cost-aware ordering
  (EP069.3-AUDIT-005).

None of these gaps correspond to a discovered implementation defect —
each was independently exercised by hand in this audit and found
correct (Section 8, Section 11).

## 13. Protected Boundary Review

Diffed byte-for-byte against the pristine pre-EP-069.2 tree:
`src/core/ai/provider.py`, `src/services/ai_service.py`,
`src/core/ai/provider_registry.py`, `src/core/ai/claude_provider.py`,
`src/core/ai/providers/gemini_provider.py`,
`src/core/ai/provider_factory.py` — **all byte-identical, zero
changes**. No Tool Engine, Capability Registry, retry framework,
billing/accounting, analytics, health/load-balancing, real-time
pricing, or token-usage-estimation code exists anywhere in the diff.

While reviewing `ai_service.py` for this confirmation, a
pre-existing, now-compounded documentation-currency issue was found —
see Finding EP069.3-AUDIT-002.

## 14. Scope Review

Diffed the full working tree against the EP-069.2 archive baseline.
Changed: `src/core/ai/provider_manager.py`, `src/bootstrap.py`,
`config/config.yaml`, `src/modules/test_module.py` (one import line),
plus new files `tests/EP069_3/__init__.py` and
`tests/EP069_3/test_cost_aware_provider_selection.py`. No unrelated
refactoring, no formatting-only changes, no renamed APIs, no changes to
`tests/EP069/` or `tests/EP069_2/` (both confirmed byte-identical to
their respective archives/originals), no changes to
`CHANGELOG.md`/`docs/BACKLOG.md`/`docs/RELEASE_NOTES.md`/
`docs/architecture/JARVIS_ROADMAP.md` (all confirmed byte-identical to
the EP-069.2 archive — correctly deferred to STEP 4), no accidental
generated files, no temporary files, no `__pycache__` artifacts left in
the delivered tree.

**No scope creep found.**

## 15. Findings

### EP069.3-AUDIT-001 — `ProviderManager` does not independently enforce the `relative_cost` invariant it documents (MEDIUM)

**Evidence:** Section 8.1. Directly constructing `ProviderManager` with
`relative_cost` containing `NaN`/`Infinity`/negative values (bypassing
`bootstrap.py`) causes those values to be treated as legitimate
*known* costs — potentially sorting a "poisoned" provider ahead of
genuinely cheaper ones — rather than as "unknown," contrary to the
design's stated invariant. No crash and no nondeterminism results
(Section 8.1, Section 9), only a semantic violation if this path is
ever reached.

**Architectural impact:** The finite/non-negative/non-bool guarantee
is enforced at exactly one layer (`bootstrap.py`), with the component
that actually performs the sort (`ProviderManager`/`_cost_sort_key`)
trusting its caller entirely. This is consistent with this project's
existing convention (EP-069.2's `fallback_order` is validated the same
way, only at the composition root, and carries the analogous
unresolved EP069.2-AUDIT-001 gap for its own element-level validation —
see Finding EP069.3-AUDIT-006), so this is not a novel pattern, but it
is a real, reproduced gap rather than a theoretical one.

**Reproduction/trigger:** Construct `ProviderManager(..., cost_aware_enabled=True, relative_cost={"x": float("nan")})` directly, bypassing `bootstrap.py`, then call `list_fallback_candidates()`.

**Recommendation:** Not fixed in this audit (per STEP 3 rules). If
accepted for resolution, options include: (a) defensively re-validate
`relative_cost` inside `ProviderManager.__init__` itself (redundant
with `bootstrap.py`, but closes the single-layer gap), or (b)
explicitly document this as an accepted trust boundary between
`bootstrap.py` and `ProviderManager` (mirroring EP-069.2's own accepted
pattern for `fallback_order`) and decline to change it. Both are
Owner Decisions, not architecture-mandated outcomes.

---

### EP069.3-AUDIT-002 — `AIService.ask()`'s docstring is stale regarding fallback ordering (LOW-MEDIUM)

**Evidence:** `src/services/ai_service.py` line 500 states fallback
candidates are retried "in that registry's deterministic, name-sorted
order." This has not been true since EP-069.2 introduced
`fallback_order`, and is now further inaccurate since EP-069.3 adds
cost-based ordering. `ai_service.py` is correctly unmodified by both
EPs (Section 5, Section 13), so no code behavior is affected — this is
a pure documentation-currency issue, inherited from EP-069.2 (this
audit found no record of it in
`EP069_2_ARCHITECTURE_AUDIT.md`/`EP069_2_FINDINGS_RESOLUTION.md`,
meaning it predates and was not previously caught).

**Architectural impact:** None on behavior. A maintainer reading only
this docstring (rather than `ProviderManager.list_fallback_candidates()`'s
own, accurate docstring) would form an incorrect mental model of
fallback ordering.

**Reproduction/trigger:** Read `src/services/ai_service.py` lines
488–501.

**Recommendation:** Not fixed in this audit — `ai_service.py` is a
protected file for STEP 2/STEP 3 of this EP. Flagged for STEP 4
documentation synchronization (or a small, separately-scoped
docs-only fix), not for EP-069.3 STEP 3.1.

---

### EP069.3-AUDIT-003 — No test exercises `list`/`dict`-typed `relative_cost` (LOW, test gap only)

**Evidence:** Section 7, Section 8, Section 12. `_parse_relative_cost`
was independently reproduced with `list`, `dict`, and `tuple` inputs in
this audit and found correct (rejected, one warning each, no crash) —
this is a test-coverage gap, not an implementation defect, despite
being explicitly named in the STEP 2 task's own required-coverage
list (Section 13: "lists; dictionaries").

**Recommendation:** Add the two missing test cases if STEP 3.1 is
authorized to include test-only additions; otherwise track as a
documented, non-blocking gap.

---

### EP069.3-AUDIT-004 — No `ProviderManager`-level test for a literal `0`/`0.0` `relative_cost` (LOW, test gap only)

**Evidence:** Section 7, Section 8. Independently reproduced in this
audit: a `0.0`-cost provider correctly sorts as the cheapest known
cost, never as "unknown." Only the `_parse_relative_cost` unit level
is covered by an existing test; the end-to-end ordering behavior with a
literal zero is not.

**Recommendation:** Add one `list_fallback_candidates()`-level test
with a `0.0`-cost provider mixed with a positive-cost and an
unconfigured provider, if STEP 3.1 is authorized to include test-only
additions.

---

### EP069.3-AUDIT-005 — No test for a name present in both `exclude` and `fallback_order` under cost-aware ordering (LOW, test gap only)

**Evidence:** Section 11. Structurally guaranteed correct (eligibility
is computed before either ordering rule is consulted), independently
re-confirmed by reading the method body in this audit, but not
covered by a dedicated regression test.

**Recommendation:** Optional additional test; non-blocking, matching
the same "structural guarantee, test optional" classification
EP-069.2's own audit used for its analogous Finding EP069.2-AUDIT-004.

---

### EP069.3-AUDIT-006 — Inherited: unhashable `fallback_order` element still crashes `list_fallback_candidates()` (LOW/MEDIUM, inherited, not introduced by EP-069.3)

**Evidence:** Documented and reproduced by EP-069.2's own STEP 3 audit
(`EP069_2_ARCHITECTURE_AUDIT.md` Section 8.4, finding
EP069.2-AUDIT-001) and its STEP 3.1 findings-resolution
(`EP069_2_FINDINGS_RESOLUTION.md` Section 5/9/10: MEDIUM, "DESIGN
UPDATE REQUIRED," explicitly non-blocking, deferred as a fast-follow).
This audit independently confirmed the defect is still present,
unchanged, in the current `list_fallback_candidates()` — EP-069.3 adds
its cost-aware sort *after* the `fallback_order` partitioning step
that contains the defect, so a crash there is never reached by
EP-069.3's own code, and EP-069.3 introduces no new unhashable-element
risk of its own (`relative_cost` keys are drawn from
`KNOWN_PROVIDER_NAMES`/dict lookups, never from iterating an
operator-supplied list of arbitrary YAML values the way
`fallback_order` is).

**Architectural impact on EP-069.3 specifically:** None additional —
this is purely an EP-069.2 finding being carried forward for
completeness, not a new EP-069.3 defect.

**Recommendation:** No action within EP-069.3's scope. Already tracked
under EP-069.2's own findings-resolution as a fast-follow, independent
of this EP.

## 16. Finding Classification Summary

| ID | Severity | Category | Blocking? |
|---|---|---|---|
| EP069.3-AUDIT-001 | MEDIUM | Defense-in-depth / contract-enforcement gap (reproduced, not currently exploitable via the sole production call site) | No |
| EP069.3-AUDIT-002 | LOW-MEDIUM | Documentation staleness (inherited, compounded) | No |
| EP069.3-AUDIT-003 | LOW | Test gap (implementation independently verified correct) | No |
| EP069.3-AUDIT-004 | LOW | Test gap (implementation independently verified correct) | No |
| EP069.3-AUDIT-005 | LOW | Test gap (structurally guaranteed correct) | No |
| EP069.3-AUDIT-006 | LOW/MEDIUM (inherited) | Not a new EP-069.3 finding; carried forward for completeness | No |

Zero CRITICAL findings. Zero HIGH findings. No finding invalidates an
`EP069_3_DESIGN.md` Acceptance Criterion (Section 22 of the design was
independently re-checked, item by item, against Sections 6–11 above;
all 9 criteria hold).

## 17. Overall Verdict

**PASS WITH WARNINGS.**

The implementation correctly and minimally extends
`list_fallback_candidates()` exactly as designed, composes correctly
and non-destructively with EP-069.2's `fallback_order`, changes no
protected contract, introduces no backward-compatibility regression,
and its most safety-critical claims (boolean rejection, NaN/Infinity
non-crash behavior, unknown-cost eligibility preservation) were
independently reproduced in this audit rather than accepted on faith.
The findings above are real but narrow: one genuine defense-in-depth
gap (EP069.3-AUDIT-001) that is not reachable through the actual
production wiring, one inherited documentation-staleness issue this
audit is the first to surface (EP069.3-AUDIT-002), three test-coverage
gaps whose underlying code was independently verified correct
(EP069.3-AUDIT-003/004/005), and one pre-existing, already-tracked
EP-069.2 defect carried forward for completeness
(EP069.3-AUDIT-006). None rises to a level that should block
acceptance of this implementation as-is; all are appropriate STEP 3.1
discussion items for the Owner to accept, defer, or schedule.

---

## Test Baseline (independently re-run in this audit)

- EP-069.3: 57/57 passed.
- EP-069.2: 26/26 passed (unmodified).
- EP-069.1: 68/68 passed (unmodified).
- Full registered regression suite: 7347 passed / 2 failed / 3 skipped.
  The 2 failures are in `EP048` (Wake Word) and are pre-existing,
  environment-only (missing `openwakeword`/`tflite-runtime` in this
  sandbox, unrelated to `src/core/ai/`, `src/bootstrap.py`'s AI
  section, or `config.yaml`'s `ai:`/`providers:` blocks) — confirmed
  identical before and after all EP-069.3 changes in this session.

---

## 18. STEP 3.1 Resolution Status (addendum — added during STEP 3.1, this audit's findings and verdict above are otherwise unchanged)

This section records STEP 3.1's disposition of each finding above. It
does not alter, retract, or soften any original finding, evidence, or
severity recorded in Sections 15–17 — those remain the historical
record of what STEP 3 found. See
`docs/architecture/audits/EP069_3_FINDINGS_RESOLUTION.md` for the full
STEP 3.1 resolution record, including verification evidence.

| Finding | STEP 3.1 Disposition |
|---|---|
| EP069.3-AUDIT-001 | **FIXED.** `ProviderManager.__init__` now independently sanitizes every `relative_cost` entry via a new `_is_valid_relative_cost()` predicate (the same rule `bootstrap.py` already enforced), before the mapping is ever stored. An invalid entry — `bool`, non-numeric, negative, NaN, or infinite — is now silently dropped and treated as unknown cost even when `ProviderManager` is constructed directly, bypassing `bootstrap.py` entirely. Independently re-reproduced against the exact NaN/Infinity/bool scenarios Section 8.1 originally used. |
| EP069.3-AUDIT-002 | **FIXED.** `src/services/ai_service.py`'s `ask()` docstring no longer claims fallback candidates are "name-sorted"; it now states the order is deterministic but may be changed by a configured fallback order or cost-aware preference, and points to `ProviderManager.list_fallback_candidates()`'s own docstring as the authoritative description. No runtime behavior was changed. |
| EP069.3-AUDIT-003 | Deferred (unchanged from Section 17). |
| EP069.3-AUDIT-004 | Deferred (unchanged from Section 17). |
| EP069.3-AUDIT-005 | Deferred (unchanged from Section 17). |
| EP069.3-AUDIT-006 | Inherited/deferred from EP-069.2 (unchanged from Section 17) — not in EP-069.3's scope. |
