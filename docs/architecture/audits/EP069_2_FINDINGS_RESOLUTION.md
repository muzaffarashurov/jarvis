# EP-069.2 Findings Resolution — Configured AI Provider Fallback Ordering

STEP 3.1: Findings Resolution Review

## 1. Title

EP-069.2 Findings Resolution Review

## 2. Purpose

`docs/architecture/audits/EP069_2_ARCHITECTURE_AUDIT.md` (STEP 3) reported seven findings (EP069.2-AUDIT-001 through -007, the last carried forward unchanged from EP-069.1) and a verdict of PASS WITH WARNINGS. This document independently re-verifies each finding directly against current source code — not by re-reading the audit's own conclusions and accepting them — classifies each with a concrete resolution, and issues a final STEP 4 readiness decision. Per the governing instructions, this is a decision review only: no production code, test, configuration, or prior document (`EP069_2_DESIGN.md`, `EP069_2_ARCHITECTURE_AUDIT.md`) was modified while producing it.

## 3. Review Methodology

For every finding: (a) re-read the exact cited source location fresh, independent of the audit's prose description; (b) where the audit's claim was about a reproducible crash, re-run the reproduction independently and probe adjacent inputs the audit did not itself enumerate, to narrow or widen the claim precisely; (c) cross-check against `EP069_2_DESIGN.md`'s own Acceptance Criteria to determine whether the finding represents an implementation deviation from an explicit, testable requirement, or a gap in the design's own completeness; (d) classify using the six-value scheme; (e) decide blocking/non-blocking for STEP 4. Source-of-truth order followed: actual code first, then the STEP 3 audit's claims (treated as a hypothesis to verify, not a conclusion to inherit), then `EP069_2_DESIGN.md`, then EP-069.1's own findings-resolution precedent for classification style.

## 4. Findings Review Table

| Finding | Severity | Verified? | Classification | STEP 4 Blocking? | Resolution |
|---|---|---|---|---|---|
| EP069.2-AUDIT-001 | MEDIUM | Yes, reproduced independently; narrower and also *wider* than originally stated in different respects (Section 5) | DESIGN UPDATE REQUIRED | No (see Section 5's explicit priority caveat) | Extend `EP069_2_DESIGN.md` Section 14 to define element-level validation; implement in a fast-follow revision |
| EP069.2-AUDIT-002 | LOW | Yes, factually correct | TEST IMPROVEMENT — CAN DEFER | No | Add regression test for AUDIT-001 once fixed; add "only-unlisted-remain" AIService-level test |
| EP069.2-AUDIT-003 | LOW | Yes, but the underlying claim ("contract unaffected") is independently confirmed true by stronger evidence (Section 7.1) | TEST IMPROVEMENT — CAN DEFER | No | Optional rename/strengthen, future work |
| EP069.2-AUDIT-004 | LOW | Yes, but structural correctness already independently confirmed (Section 7.2) | TEST IMPROVEMENT — CAN DEFER | No | Optional combined-scenario test, future work |
| EP069.2-AUDIT-005 | LOW | Yes | DESIGN UPDATE REQUIRED | No | Cosmetic correction to `EP069_2_DESIGN.md` Section 12's pseudocode in a future documentation pass |
| EP069.2-AUDIT-006 | LOW | Yes, confirmed no live risk under current (sequential) test execution model | ACCEPTED TRADE-OFF | No | None — documented, non-live assumption |
| EP069.2-AUDIT-007 (carried forward from EP-069.1) | MEDIUM (inherited) | Not re-litigated — already resolved under `EP069_FINDINGS_RESOLUTION.md` Section 6 (DOCUMENT RESIDUAL RISK) | NOT A VALID (NEW) FINDING | No | None — inherited, unchanged, already tracked under EP-069.1's own resolution |

**Zero findings classified FIX BEFORE STEP 4. Two findings classified DESIGN UPDATE REQUIRED (both non-blocking); zero classified NOT A VALID FINDING for the six substantive EP-069.2-specific findings** (AUDIT-007 is excluded from that count because it is not a new EP-069.2 finding at all, per Section 6).

## 5. Detailed Analysis of AUDIT-001

**Independently re-read both cited source locations fresh** (not from the audit's own prose): `src/bootstrap.py`'s `if not isinstance(ai_fallback_order, list): ...` block, and `src/core/ai/provider_manager.py`'s `list_fallback_candidates()` ordering loop (`for name in self._fallback_order: if name in eligible_by_name and name not in seen:`).

**Independently re-reproduced the crash**, and additionally probed inputs the STEP 3 audit did not itself enumerate, to determine the *exact* boundary of the defect rather than accepting "an unhashable element crashes it" as sufficient characterization:

| `fallback_order` value | Passes `isinstance(..., list)`? | Result |
|---|---|---|
| `[{"bad": "entry"}, "gemini"]` (dict element) | Yes | **Crashes**: `TypeError: unhashable type: 'dict'` |
| `[["gemini", "claude"]]` (nested list element) | Yes | **Crashes**: `TypeError: unhashable type: 'list'` |
| `[1, 2, "gemini"]` (int elements) | Yes | **Safe** — ints are hashable; `1 in eligible_by_name` and `2 in eligible_by_name` simply evaluate `False`, exactly like an unmatched string. Correctly inert. |
| `[None, "gemini"]` (`None` element) | Yes | **Safe** — same reasoning; `None` is hashable. |

**This narrows the STEP 3 audit's own characterization**, which described the trigger only as "an unhashable element" without confirming which YAML-representable element types are actually unhashable in Python (dicts and lists — i.e., nested mappings or nested lists) versus which merely-non-string types are safe (numbers, booleans, null, and, if ever produced by a custom YAML tag, tuples). The practical trigger is specifically: **a YAML author nesting a mapping or a sub-list inside the `fallback_order` list**, not "any wrong element type" as a blanket category. This is narrower than a first reading of AUDIT-001 might suggest.

**This also widens the audit's original framing in one respect**: the audit's illustrative example (`- {"bad": "entry"}`, a deliberately artificial-looking flow-mapping) undersells how *plausible* the trigger is. Independently constructing a second, more natural-looking trigger — a simple YAML indentation mistake —

```yaml
ai:
  fallback_order:
    - - gemini
      - claude
```

— produces `[["gemini", "claude"]]`, a nested list, and crashes identically. This is a materially more realistic authoring slip (an accidental extra list level from misplaced indentation, a well-known class of YAML mistake) than the audit's own dict-literal example, and it requires no unusual syntax knowledge to accidentally produce. This raises this audit's assessed real-world likelihood slightly above what the STEP 3 audit's own example implied.

**Cross-checked against `EP069_2_DESIGN.md`'s Acceptance Criteria** (Section 20): Acceptance Criterion 5 reads: *"With `ai.fallback_order` set to a non-list value (e.g. a string), exactly one `WARNING`-level log line is emitted..."* — this criterion is scoped explicitly to the **whole value** being a non-list type. It says nothing about a list whose **elements** are of an invalid type. The current implementation satisfies AC5 exactly as literally worded (independently re-confirmed via `_test_bootstrap_invalid_type_fallback_order_is_ignored`, re-run in Section 8 below). **This is not an implementation deviation from an approved, testable requirement — it is a genuine gap in the design's own Section 14/Acceptance-Criteria completeness**, which anticipated the "wrong container type" case but not the "right container, wrong element type" case.

**Concrete conclusion**: Real, reproducible, currently-live defect — unlike EP-069.1-AUDIT-004 (a hypothetical *future* misbehaving provider), this requires no new code or future provider to trigger; a single malformed `config.yaml` value, authored today, against the current, shipped implementation, reproducibly crashes fallback evaluation. This pushes it toward more urgency than a typical "document and defer" MEDIUM finding. However, three factors keep it non-blocking for STEP 4 specifically:

1. It violates no explicit, currently-approved Acceptance Criterion (AC5 is satisfied as literally worded) and no Owner Decision needs to be reversed — the gap is in the design's own scope, not a deviation from it.
2. The failure mode is loud, not silent: an operator who introduces this misconfiguration would see an immediate, unambiguous `TypeError` in logs/output the moment fallback is attempted — not silent data corruption, not a security leak, not a wrong answer returned as if correct.
3. No default configuration, no currently-passing test, and no documented example anywhere in `config/config.yaml`'s own `fallback_order` comment (which only shows a flat list-of-strings shape) triggers this. The comment's own example (`["gemini", "claude"]`, flat strings) is the form every operator following the shipped documentation would naturally produce.

**Resolution: DESIGN UPDATE REQUIRED, non-blocking for STEP 4, but flagged as the highest-priority deferred item from this audit.** `EP069_2_DESIGN.md` Section 14 should be extended in a near-term follow-up (a small design addendum, not a full new EP-069.x slice) to explicitly define element-level validation behavior (e.g., "any non-`str` element in an otherwise-list-typed `ai.fallback_order` is treated as absent for that element, with the same `WARNING` discipline as the whole-value case"), followed by the corresponding four-to-six-line implementation change in `src/bootstrap.py`. Given the defect is live today (not merely theoretical), this repository's maintainers should prioritize this fast-follow ahead of unrelated future work, but it does not rise to blocking STEP 4's purely-documentary synchronization work, and STEP 3.1 explicitly prohibits implementing it now.

## 6. Analysis of Carried-Forward AUDIT-007

Independently re-checked: this finding is a restatement of `EP069_ARCHITECTURE_AUDIT.md`'s own Finding EP069.1-AUDIT-004 (`is_available()` raising during `list_fallback_candidates()`'s eligibility computation), noted in the EP-069.2 audit only because EP-069.2's new ordering code executes inside the same method and inherits the identical unguarded call. This finding was already independently re-verified and resolved in `docs/architecture/audits/EP069_FINDINGS_RESOLUTION.md` Section 6 (classification: DOCUMENT RESIDUAL RISK; re-confirmed there that none of the three current concrete `is_available()` implementations — `ClaudeProvider`, `GeminiProvider`, `ConfigDrivenProvider` — can raise under any realistic runtime condition, since each is a pure boolean expression over already-set instance attributes with no I/O).

Re-confirmed directly for this review: EP-069.2's changes do not touch the `is_available()` call site at all (it remains `if provider.name() not in excluded and provider.is_available()`, textually identical to the pre-EP-069.2 line, per the full-tree diff in the STEP 3 audit's Section 15). EP-069.2 neither introduces, worsens, nor fixes this risk.

**Resolution: NOT A VALID (NEW) FINDING for EP-069.2.** Already correctly resolved under EP-069.1's own findings resolution; no separate EP-069.2 action item is created by its restatement here.

## 7. Analysis of Remaining Findings

### 7.1 EP069.2-AUDIT-002 (missing regression test for AUDIT-001; missing "only-unlisted-remain" `AIService`-level test)

Independently re-confirmed both gaps by re-reading `tests/EP069_2/test_provider_fallback_ordering.py` in full: no test constructs an unhashable `fallback_order` element, and no `AIService.ask()`-level integration test exercises the shape where every name in `fallback_order` is ineligible and only unlisted candidates remain (this shape is exercised only at the `ProviderManager` unit level, as a side effect of `_test_unknown_names_are_inert`'s primary purpose, not through the real fallback loop). Both are genuine, narrow coverage gaps; neither currently causes a false-positive result for any passing test.

**Resolution: TEST IMPROVEMENT — CAN DEFER.** The AUDIT-001 regression test should be added at the same time AUDIT-001's design/implementation gap is closed (Section 5); the `AIService`-level "only unlisted remain" test can be added independently in a future pass.

### 7.2 EP069.2-AUDIT-003 (contract-stability test is weak in isolation)

Independently re-confirmed: `_test_provider_contract_unaffected` only demonstrates that a hand-written fake conforms to `AIProvider`'s current interface; it does not itself diff against the pre-EP-069.2 contract. However, re-checking the *actual* strength of the overall claim (not just this one test in isolation): the STEP 3 audit's Section 15 full-tree diff independently confirms `src/core/ai/provider.py` has zero byte-for-byte changes — this is stronger, direct evidence of contract stability than any test could provide indirectly. The test's weakness is real but does not leave the underlying claim ("the contract is unaffected") actually unverified overall; it is verified, just by a different, better source of evidence than this specific test.

**Resolution: TEST IMPROVEMENT — CAN DEFER.** Optional: rename the test to reflect what it actually verifies (fake-conformance, not contract-diff), or supplement with an explicit `AIProvider.__abstractmethods__` inspection. Not required before STEP 4.

### 7.3 EP069.2-AUDIT-004 (no combined ordering+exclude+availability test)

Independently re-confirmed: no single test combines all three filters in one scenario; each pairwise combination is tested once. Independently re-traced the code structure (Section 8 of the STEP 3 audit, re-verified here by re-reading `list_fallback_candidates()` again): `eligible` is computed once, applying both the `exclude` filter and the `is_available()` filter together, *before* `fallback_order` is consulted at all — meaning `fallback_order` cannot special-case or bypass either filter for any subset of providers. The triple-interaction case is not a new code path; it is the same single `eligible` computation already exercised (separately) by the existing availability test and the existing exclusion test. A defect specific to the triple combination would require the implementation to branch on the *combination* of filters, which it structurally does not do.

**Resolution: TEST IMPROVEMENT — CAN DEFER.** Add a combined-scenario test for defense-in-depth in a future pass; not required to unblock STEP 4 given the structural (single-code-path) guarantee.

### 7.4 EP069.2-AUDIT-005 (design pseudocode doesn't itself dedupe)

Independently re-confirmed: `EP069_2_DESIGN.md` Section 12's literal pseudocode (`ordered = [eligible_by_name[name] for name in self._fallback_order if name in eligible_by_name]`) would append a duplicate name twice if `fallback_order` itself contains a repeat, whereas the actual implementation correctly guards against this with a `seen` set — matching the *same* document's own Section 14 prose ("Duplicate names in the list: the first occurrence wins... No error raised") and the STEP 2 task's explicit "no duplicates" requirement. The implementation is correct; only the design document's illustrative code sample under-specifies its own stated behavior. No implementation defect exists.

**Resolution: DESIGN UPDATE REQUIRED** (cosmetic only) — correct `EP069_2_DESIGN.md` Section 12's pseudocode to include the `seen`-set guard in a future documentation pass, so the illustrative code matches the document's own prose and the shipped implementation. Not blocking for STEP 4; carries no behavioral risk since the implementation, not the pseudocode, is what shipped.

### 7.5 EP069.2-AUDIT-006 (`os.chdir` test-isolation fragility)

Independently re-confirmed: `_ChdirGuard.__exit__` unconditionally restores the original working directory (no conditional skip), and `src/testing/runner.py`'s `run_all()`/`run()` execute suites strictly sequentially, in-process, with no threading or async execution found anywhere in that module. Under this confirmed-sequential model, the narrow window during which cwd is altered cannot be observed by any other concurrently-running test, because no other test runs concurrently. This is a real but entirely non-live assumption, correctly scoped to "if the runner ever becomes concurrent," which it currently is not.

**Resolution: ACCEPTED TRADE-OFF.** No action required unless the test execution model changes; the assumption is now explicitly documented (Section 12 of the STEP 3 audit, and this section).

## 8. Independent Re-Verification of Regression Claims

Before issuing a final decision, the STEP 3 audit's regression claims were spot-checked once more against the current working tree (not merely re-read from that document):

- Re-ran `tests/EP069_2/test_provider_fallback_ordering.py`'s suite in isolation: 26 passed, 0 failed, 0 skipped — confirms none of the six findings above correspond to an actually-failing test; all six are gaps in what is tested or documented, not failures of what is tested.
- Re-ran the EP-069 (EP-069.1) suite in isolation: 68 passed, 0 failed, 0 skipped — confirms EP-069.2 (and this findings-resolution review's own analysis) has not identified any EP-069.1 regression.
- Re-confirmed AC5's literal test (`_test_bootstrap_invalid_type_fallback_order_is_ignored`, a non-list *whole value*) still passes, consistent with Section 5's conclusion that AC5 itself is satisfied and the gap is genuinely a scope omission in the design's own criteria, not a failing test.

## 9. Resolution Decision for Each Finding

- **EP069.2-AUDIT-001 — DESIGN UPDATE REQUIRED (highest-priority deferred item).** Real, reproducible, currently-live crash triggered purely by configuration content, requiring no future provider. Does not violate any current Acceptance Criterion (AC5 is scoped only to the whole-value type). Extend `EP069_2_DESIGN.md` Section 14 with element-level validation behavior, then implement a small `src/bootstrap.py` fix, as a fast-follow — not as part of STEP 4's purely-documentary work, and not implemented during this review.
- **EP069.2-AUDIT-002 — TEST IMPROVEMENT — CAN DEFER.** Add the AUDIT-001 regression test alongside its fix; add the "only unlisted remain" `AIService`-level test independently.
- **EP069.2-AUDIT-003 — TEST IMPROVEMENT — CAN DEFER.** Optional rename/strengthen; underlying claim already independently confirmed via the full-tree diff.
- **EP069.2-AUDIT-004 — TEST IMPROVEMENT — CAN DEFER.** Optional combined-scenario test; structural single-code-path guarantee already independently confirmed.
- **EP069.2-AUDIT-005 — DESIGN UPDATE REQUIRED (cosmetic).** Correct the design document's Section 12 pseudocode in a future documentation pass; no behavioral risk, since the implementation already matches the document's own prose.
- **EP069.2-AUDIT-006 — ACCEPTED TRADE-OFF.** No action; assumption is explicit and currently non-live.
- **EP069.2-AUDIT-007 — NOT A VALID (NEW) FINDING.** Already resolved under EP-069.1's own findings resolution; unchanged by EP-069.2.

No finding requires reversing an EP-069.2 Owner Decision. No finding requires new tests, code changes, or a design change *before* STEP 4 specifically — including AUDIT-001, whose fix is explicitly sequenced as design-then-code in a fast-follow, not as a STEP-4-blocking gate.

## 10. Required Actions Before STEP 4

**None.** No finding meets the bar for FIX BEFORE STEP 4. AUDIT-001, despite being the most substantive finding in this review, does not block STEP 4 because (a) it does not violate any currently-approved Acceptance Criterion, (b) its failure mode is loud and self-diagnosing rather than silent or data-corrupting, and (c) no default configuration or documented usage pattern triggers it. It is, however, flagged in Section 5 and Section 11 as warranting prompt attention independent of the STEP 4/STEP 5 sequence.

## 11. Deferred Actions / Future Considerations

- **(Priority)** Extend `EP069_2_DESIGN.md` Section 14 to define element-level validation for `ai.fallback_order` (each element must be a `str`; a non-`str` element is treated as absent for that element, with the same `WARNING`-then-ignore discipline already used for the whole-value case), then implement the corresponding `src/bootstrap.py` change and its regression test (from EP069.2-AUDIT-001/002).
- Add an `AIService`-level integration test for the "only unlisted providers remain eligible" shape (from EP069.2-AUDIT-002).
- Optional: rename or strengthen `_test_provider_contract_unaffected` (from EP069.2-AUDIT-003).
- Optional: add one combined `fallback_order` + `exclude` + unavailable-provider test (from EP069.2-AUDIT-004).
- Cosmetic: correct `EP069_2_DESIGN.md` Section 12's pseudocode to include the `seen`-set duplicate guard (from EP069.2-AUDIT-005).

None of the above are scheduled or scoped as part of EP-069.2's own STEP 4; they are candidates for a near-term fast-follow (AUDIT-001/002/005, given AUDIT-001's live-defect status) or future, separately-proposed work (AUDIT-003/004).

## 12. Residual Risks

- An operator who writes a `fallback_order` list containing a nested mapping or nested list (most plausibly via a YAML indentation mistake) will experience an unhandled `TypeError` the next time fallback evaluation actually runs, converting a recoverable `ProviderError` into a crash. Loud and self-diagnosing, not silent; no default or documented configuration triggers it (Section 5).
- The `is_available()`-raises risk inherited from EP-069.1 remains exactly as previously assessed and resolved: zero exploitability against any of the three current concrete provider implementations (Section 6).
- The design document's Section 12 pseudocode does not itself reflect the shipped, correct deduplication behavior; a reader consulting only the design document (not the implementation) could be misled, though no behavioral risk exists in the shipped code (Section 7.4).

## 13. Final STEP 4 Readiness Decision

### READY FOR STEP 4

All seven STEP 3 findings have been independently re-verified against actual source code and, for AUDIT-001, against additional adversarial inputs the original audit did not itself enumerate. One finding (EP069.2-AUDIT-001) was confirmed to be a genuine, currently-live, reproducible defect — a meaningfully different risk profile than EP-069.1's own precedent findings, which concerned hypothetical future providers rather than the shipped code's current behavior — but it does not block STEP 4 because it violates no approved Acceptance Criterion, fails loudly rather than silently or unsafely, and is not reachable through any documented or default configuration; it is elevated in this document as the highest-priority item for a near-term fast-follow rather than filed away as an equal-weight residual risk. One finding (EP069.2-AUDIT-005) identifies a documentation-only inaccuracy with zero behavioral consequence. Three findings (EP069.2-AUDIT-002, -003, -004) are genuine, non-blocking test-coverage improvements whose absence does not indicate incorrect behavior in the current implementation — each underlying code path was independently re-confirmed correct by direct structural inspection, not only inferred from the existing test suite's pass count. One finding (EP069.2-AUDIT-006) is a confirmed non-live assumption requiring no action under the current, verified-sequential test execution model. One finding (EP069.2-AUDIT-007) is not a new EP-069.2 finding at all — it is a restatement of an already-resolved EP-069.1 finding, unchanged and untouched by this EP. No finding violates an EP-069.2 Owner Decision, an approved Acceptance Criterion, an established architectural convention in a way that constitutes a regression, or creates a live security/privacy risk in the shipped code. All remaining warnings are acceptable to carry forward as documented residual risk and prioritized-but-non-blocking follow-up work.
