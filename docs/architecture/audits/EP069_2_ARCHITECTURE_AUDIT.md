# EP-069.2 Architecture Audit — Configured AI Provider Fallback Ordering

STEP 3: Independent Architecture Audit

## 1. Title

EP-069.2 Architecture Audit — Configured AI Provider Fallback Ordering

## 2. EP / Version

EP-069.2 (parent: EP-069 — AI Provider & Tool Registry, planning identifier only; prior slice: EP-069.1 — Automatic AI Provider Fallback on Request Failure, frozen and unmodified). STEP 2 implementation as delivered — no revision suffix; this is the first audit pass.

## 3. Audit Status

COMPLETE. Adversarial, independent review of the STEP 2 implementation against `docs/architecture/designs/EP069_2_DESIGN.md` and this repository's established architecture. No production code, test, or configuration file was modified during this audit. The only file created is this document. Verified in Section 12/13.

## 4. Audit Objective

Determine whether EP-069.2 is architecturally correct, faithful to its approved design, backward compatible with EP-069.1, safe under malformed-configuration and failure conditions, sufficiently tested, free of scope creep, consistent with prior EPs' conventions, and ready for STEP 4 — independent of the STEP 2 report's claimed 26/26-passing/68/68-passing/7119/3/1/2 result. That report is treated as a claim to verify, not as evidence.

## 5. Scope

In scope: `src/core/ai/provider_manager.py`, `src/bootstrap.py`, `config/config.yaml`, `src/modules/test_module.py`, `tests/EP069_2/__init__.py`, `tests/EP069_2/test_provider_fallback_ordering.py`, and `docs/architecture/designs/EP069_2_DESIGN.md` itself (design-quality audit). Also independently re-inspected for evidence of non-modification: `src/services/ai_service.py`, `src/core/ai/provider.py`, `src/core/ai/provider_registry.py`, `src/core/ai/provider_factory.py`, `src/core/ai/claude_provider.py`, `src/core/ai/providers/gemini_provider.py`, `src/testing/base_test.py`, `src/testing/registry.py`, `src/testing/result.py`, `src/testing/runner.py`, and `docs/architecture/designs/EP069_DESIGN.md` / `docs/architecture/audits/EP069_ARCHITECTURE_AUDIT.md` / `docs/architecture/audits/EP069_FINDINGS_RESOLUTION.md` (EP-069.1's frozen documents, for continuity of known, already-tracked risk).

## 6. Source-of-Truth Hierarchy

1. Actual implementation and tests in the current working tree, read directly during this audit (Sections 8-9).
2. `docs/architecture/designs/EP069_2_DESIGN.md` (Section 7).
3. EP-069.1's implementation/design/audit/findings-resolution, for continuity and boundary verification (Section 10).
4. Established project architecture/test conventions (`tests/EP064/test_memory_persistence_shutdown.py`'s full-Bootstrap pattern; `TestRegistry`'s NAME-keyed registration).

Every substantive claim below is backed by a direct code read, a reproduced execution, or a full-tree diff performed during this audit — not inferred from the STEP 2 report.

## 7. Design-to-Code Verification

Read `docs/architecture/designs/EP069_2_DESIGN.md` Sections 0, 11, 12, 13, 14, 17, 21 in full and compared against `src/core/ai/provider_manager.py` as it exists in the working tree:

| Design requirement (Section) | Implementation | Verdict |
|---|---|---|
| Optional `fallback_order: list[str] \| None = None` constructor param (S11) | `ProviderManager.__init__` line 66 | MATCH |
| Absent/empty preserves original alphabetical order exactly (S11/S18) | `list_fallback_candidates()`: `if not self._fallback_order: return eligible` | MATCH, verified by test and by direct reasoning: `eligible` is built from `self._registry.list()`, identical to pre-EP-069.2 code |
| Configured-first, unlisted-alphabetical-after (S12) | `ordered = [...]` then `unlisted = [...]`, returned as `ordered + unlisted` | MATCH |
| Unknown names inert, no error, no fabricated candidate (S12/S14/D4) | `eligible_by_name` dict lookup guarded by `if name in eligible_by_name` | MATCH |
| No duplicate candidates (Section 3 of the STEP 2 task; implied by S12's "no duplicates" requirement) | `seen: set[str]` guards `ordered`; `unlisted` excludes names in `seen` | MATCH — see Section 7.1 below: the implementation is *stricter* than the design's own Section 12 pseudocode |
| Availability filtering never bypassed (S11, "Configured ordering must NOT bypass...") | `eligible` list comprehension applies `is_available()` before any ordering step; `fallback_order` never adds to `eligible` | MATCH, structurally guaranteed (ordering only reorders `eligible`, never unions with anything else) |
| Excluded providers never reappear (Section 3 of STEP 2 task) | Same structural guarantee — `exclude` is applied before `eligible` is computed | MATCH |
| Immutable after construction, no lock needed beyond existing (S17) | `self._fallback_order = list(fallback_order) if fallback_order else []` — defensive copy at construction; no setter exists anywhere in the class | MATCH, and additionally verified: the defensive copy means a caller mutating the list object it originally passed in cannot retroactively affect `ProviderManager` state (see Section 8.2) |
| No `AIProvider`, `ProviderRegistry`, `ProviderFactory`, `AIService` changes (S9, S11, D9) | Confirmed by full-tree diff (Section 12) | MATCH |
| `ai.fallback_order` config key, default `[]` (S13) | `config/config.yaml` line ~587 | MATCH |
| Invalid type → `WARNING` + treated as absent (S14, D8) | `src/bootstrap.py`: `isinstance(ai_fallback_order, list)` check, `logger.warning(...)`, `ai_fallback_order = []` | MATCH for the *outer* type; see Finding EP069.2-AUDIT-001 for a gap the design itself did not anticipate (element-level validation) |

### 7.1 Implementation exceeds design pseudocode (positive deviation)

`EP069_2_DESIGN.md` Section 12's pseudocode is:

```
ordered = [eligible_by_name[name] for name in self._fallback_order if name in eligible_by_name]
```

This literal pseudocode does **not** deduplicate a `fallback_order` list that itself contains a repeated name (e.g. `["gemini", "gemini", "claude"]`) — it would append `eligible_by_name["gemini"]` twice into `ordered`, violating the design's own stated "no duplicates" outcome and the STEP 2 task's explicit requirement 7 ("A provider must appear at most once"). The actual implementation correctly diverges from this literal pseudocode by introducing a `seen: set[str]` guard, which the STEP 2 task's Section 3 ("No duplicates") required but the design document's own Section 12 code sample did not itself account for. This is evidence of correct engineering judgment overriding an incomplete pseudocode sketch, not a design-to-code deviation to flag as a defect — but it is a genuine, minor gap in the design document's own precision, tracked as Finding EP069.2-AUDIT-005 (documentation accuracy only).

## 8. ProviderManager Audit

Read `src/core/ai/provider_manager.py` in full (231 lines) directly from the working tree.

### 8.1 Ordering responsibility placement

Ordering logic lives entirely inside `list_fallback_candidates()`, the same method EP-069.1 already introduced as the fallback-candidate boundary. No ordering logic exists in `ProviderRegistry`, `ProviderFactory`, `AIProvider`, or `AIService` — confirmed both by design intent and by the full-tree diff (Section 12) showing none of those files changed. This is the correct location: `ProviderManager` is already the sole consumer-facing boundary between "provider catalog" and "provider selection," per this file's own module docstring, and EP-069.2 adds a preference to selection, not to catalog storage.

### 8.2 Mutability / defensive copy

`self._fallback_order: list[str] = list(fallback_order) if fallback_order else []` performs a shallow copy of the caller-supplied list at construction time. Verified directly: a caller that retains a reference to the original list and mutates it after constructing `ProviderManager` cannot affect `self._fallback_order`, because `list(...)` creates a new list object. No setter or public mutator for `_fallback_order` exists anywhere in the class. This satisfies the design's Section 17 "immutable after construction" claim correctly — it is not merely asserted in a docstring, it is enforced by the copy.

### 8.3 Ordering algorithm and deduplication correctness

Independently re-derived and mentally executed the algorithm against several adversarial inputs beyond what STEP 2's own tests cover:

- `fallback_order` containing a name not present in the registry at all → correctly inert (verified by direct read: `eligible_by_name` only contains actually-eligible providers, so a foreign name simply never satisfies `if name in eligible_by_name`).
- `fallback_order` containing every eligible name plus extra unknown names interleaved → correctly produces the eligible subset in configured relative order, since the `for name in self._fallback_order` loop simply skips non-matching entries without disrupting the relative order of the ones that do match.
- `fallback_order` empty after `exclude` removes every provider it names → falls through cleanly to `unlisted` being empty and `ordered` being empty, returning `[]` — no crash, verified this is the same as EP-069.1's original "no fallback candidates" terminal state that `AIService.ask()` already handles.
- **`fallback_order` containing an unhashable element (e.g., a YAML mapping accidentally nested inside the list)** → reproduced directly during this audit (Section 8.4): this **raises an unhandled `TypeError`**, a genuine defect not covered by the design's Section 14 error-handling section, which only discusses the *entire value* being non-list-typed. See Finding EP069.2-AUDIT-001.

### 8.4 Reproduced defect: unhashable `fallback_order` element crashes `list_fallback_candidates()`

Direct reproduction performed during this audit:

```python
manager = ProviderManager(
    registry=registry, enabled=True, default_provider="none",
    fallback_order=[{"bad": "entry"}, "gemini"],
)
manager.list_fallback_candidates(exclude=[])
# TypeError: unhashable type: 'dict'
```

`src/bootstrap.py`'s validation (`if not isinstance(ai_fallback_order, list): ...`) only checks the *container's* type. A YAML author who accidentally writes a list of mappings under `fallback_order` (a plausible authoring mistake — YAML's list-of-mappings syntax is visually similar to a list-of-scalars) produces a value that passes this check (it genuinely is a `list`) but crashes the very first time `list_fallback_candidates()` is invoked — i.e., not at startup, but at first fallback attempt, turning a normally-recoverable `ProviderError` into an unhandled `TypeError` that propagates out of `AIService.ask()` entirely uncaught (same propagation path already described for a different root cause in EP-069.1-AUDIT-004). This is EP-069.2-specific: it is introduced by this EP's own new `name in eligible_by_name` dict-membership check, which EP-069.1's code never performed. See Finding EP069.2-AUDIT-001.

### 8.5 Interaction with `is_available()` and `exclude`

Confirmed structurally (not just by test) that `fallback_order` cannot bypass either filter: `eligible` is computed once, before `self._fallback_order` is consulted at all, and the ordering step only ever reads from `eligible_by_name` (built from `eligible`) — there is no code path by which a name in `fallback_order` can inject a provider that was excluded or unavailable. This is a stronger guarantee than "the tests happen to show this" — it follows from the order of operations in the method body.

### 8.6 Unrelated behavior change check

Diffed `provider_manager.py` line-by-line against the pre-EP-069.2 version (Section 12). Every other method (`register_provider`, `get_provider`, `set_current`, `get_current`, `list_providers`, `is_enabled`, `disable`) is byte-for-byte unchanged. The only non-docstring changes are: the new constructor parameter, the new `self._fallback_order` assignment, and the new ordering block inside `list_fallback_candidates()`. No hidden behavioral change outside EP-069.2's stated scope was found.

## 9. Bootstrap/Configuration Audit

Read the actual `src/bootstrap.py` composition-root block directly (the single `ProviderManager(...)` construction site).

- `ai.fallback_order` is read via `config.get("ai.fallback_order", [])` — the correct dotted-key location under the existing `ai:` block, consistent with the adjacent `ai.enabled`/`ai.default_provider` reads on the same lines.
- Absent key → `config.get(...)` returns the `[]` default → `isinstance([], list)` is `True` → passed through unchanged. Verified end-to-end via `_test_bootstrap_absent_fallback_order_preserves_alphabetical` (Section 11) and independently reproduced (Section 13).
- `[]` explicit value → identical code path to absent (no special-casing needed, since `[]` already satisfies `isinstance(..., list)`).
- Non-list value (e.g. a bare string) → `isinstance` check fails → one `logger.warning(...)` call → `ai_fallback_order` reset to `[]` → passed through. Verified end-to-end (Section 11) and independently reproduced (Section 13).
- The warning message logs only the key name and `type(value).__name__`, never the malformed value's contents — consistent with EP-068's redaction discipline as EP-069.1's own design already established and as `EP069_2_DESIGN.md` Section 15 requires.
- No accidental configuration mutation: `config.get(...)` is read-only; nothing in this new block calls any `Config` write path (none exists — `src/core/config.py` exposes no setter, per `provider_manager.py`'s own module docstring).
- The single `ProviderManager(...)` call site receives `fallback_order=ai_fallback_order` as its fourth keyword argument — confirmed by direct read, not merely by successful test execution.
- `ai.enabled`/`ai.default_provider` reads on the same lines are textually unchanged (`bool(config.get("ai.enabled", False))`, `str(config.get("ai.default_provider", "none"))`) — `ai.fallback_enabled` (read later, at `AIService` construction, outside this audit's diff scope) is untouched.
- No new configuration-parsing framework, decorator, schema library, or validator abstraction was introduced — the validation is four lines of plain `isinstance`/`logger.warning`, matching this repository's existing `telegram.allowed_chat_ids` precedent (`src/bootstrap.py`, confirmed present and structurally identical in shape: `isinstance(x, list)` else default).
- **Gap**: as established in Section 8.4, this validation does not inspect list *elements*, only the outer container. This is the same root cause as Finding EP069.2-AUDIT-001, viewed from the configuration-boundary side rather than the `ProviderManager`-internal side.

## 10. EP-069.1 Interaction Audit

This section specifically re-verifies that EP-069.2 is an ordering layer, not a second fallback mechanism, per the STEP 2 task's Section 2 architectural principle.

- **Fallback candidate generation**: still exactly one method, `list_fallback_candidates()`, still called from exactly one site in `AIService.ask()` (confirmed unchanged by the zero-diff on `ai_service.py` — Section 12). EP-069.2 did not add a second candidate-generation path anywhere.
- **Eligible/non-eligible `ProviderError` handling**: `_FALLBACK_ELIGIBLE_ERRORS` and the exception-classification logic in `ai_service.py` are untouched (zero diff). EP-069.2 has no opinion on which exceptions are fallback-eligible — it only reorders candidates once a fallback has already been triggered by EP-069.1's own unchanged logic.
- **Bounded fallback loop**: unchanged — `remaining[0]` (or its equivalent) still terminates once `list_fallback_candidates()` returns an empty list, and `list_fallback_candidates()`'s *output size* is never inflated by `fallback_order` (Section 8.5) — only its order changes, so the existing "at most one attempt per eligible provider" bound is untouched.
- **Exclusion of already-attempted providers**: verified structurally (Section 8.5) and by direct test (`_test_excluded_provider_remains_excluded_even_if_configured` — Section 11), reproduced independently (Section 13).
- **`fallback_enabled` behavior**: `AIService`'s `_fallback_enabled` gate and its call site for `list_fallback_candidates()` are unchanged (zero diff on `ai_service.py`). Independently reproduced (Section 13, `_test_fallback_disabled_ignores_configured_order`) that `fallback_order` has zero observable effect while `fallback_enabled` is `False` — confirmed by inspecting the fake `gemini` provider's `ask_calls` list remaining empty.
- **Interaction between configured ordering and fallback candidates**: fully covered — ordering only ever operates on the eligibility set EP-069.1 already computes; there is no second, parallel set.
- **All configured providers fail**: falls through correctly to `unlisted` candidates (verified by direct code read, Section 8.3 — the partial-order case already exercises exactly this shape once integrated with a real failing-then-succeeding chain, `_test_fallback_loop_follows_configured_order`).
- **Configured providers unavailable**: verified (Section 8.5, `_test_unavailable_configured_provider_still_excluded`).
- **Only unlisted providers remain** (i.e., `fallback_order` names nothing eligible): verified by direct code read (`ordered` becomes `[]`, `unlisted` becomes the full `eligible` list, in alphabetical order) — this exact shape is not independently exercised through the `AIService` integration test (only through the unit-level `ProviderManager` test), a minor test-coverage gap noted as Finding EP069.2-AUDIT-002.
- **Fallback disabled**: verified (above).

**Conclusion: EP-069.2 is a pure ordering layer.** No new fallback trigger, no new exception classification, no new termination condition, and no second candidate-generation path were found anywhere in the diff or in the runtime behavior.

## 11. Test Quality Audit

Read `tests/EP069_2/test_provider_fallback_ordering.py` in full (704 lines) directly — not merely counted its pass/fail totals.

### 11.1 Coverage against the STEP 2 task's required test list (Section 11 of that task)

| Required coverage | Test(s) | Assessment |
|---|---|---|
| Backward compatibility (empty→alphabetical) | `_test_empty_order_preserves_alphabetical`, `_test_bootstrap_absent_fallback_order_preserves_alphabetical` | Adequate; also independently confirmed by direct code reasoning (Section 7) |
| Configured ordering | `_test_full_order_is_respected` | Adequate |
| Partial ordering | `_test_partial_order_lists_first_then_alphabetical_remainder` | Adequate |
| Unknown names | `_test_unknown_names_are_inert` | Adequate — additionally asserts the registry itself was not mutated (`len(registry.list()) == 2`), a genuinely useful extra assertion beyond the minimum |
| Availability | `_test_unavailable_configured_provider_still_excluded` | Adequate |
| Exclusion | `_test_excluded_provider_remains_excluded_even_if_configured` | Adequate |
| No duplicates | `_test_duplicate_names_produce_no_duplicate_candidates` | Adequate — asserts both the exact expected order *and* `len(names) == len(set(names))` independently, which would catch a duplicate even if the exact-order assertion were coincidentally satisfied |
| Determinism | `_test_repeated_calls_are_deterministic` | Adequate |
| Fallback integration | `_test_fallback_loop_follows_configured_order` | **Strong** — this is a genuine integration test through the real `AIService.ask()`, using fakes only at the `AIProvider`/`Config`/`PromptManager` boundary, not a mock of `ProviderManager` itself. It proves the real production call chain (`AIService.ask()` → `ProviderManager.list_fallback_candidates()`) actually honors configured order, not merely that the two units are independently correct. |
| Fallback disabled | `_test_fallback_disabled_ignores_configured_order` | Adequate |
| `AIProvider` contract stability | `_test_provider_contract_unaffected` | Weak in isolation (see Finding EP069.2-AUDIT-003) but reasonable as a smoke check given the stronger evidence available from the full-tree zero-diff on `provider.py` (Section 12) |
| Bootstrap/config wiring | `_test_bootstrap_wires_configured_fallback_order`, `_test_bootstrap_absent_fallback_order_preserves_alphabetical`, `_test_bootstrap_invalid_type_fallback_order_is_ignored` | **Strong** — these construct a real `Bootstrap` against a real on-disk `config.yaml` (following `tests/EP064/`'s own established full-Bootstrap precedent) rather than mocking `Config`, directly addressing the exact gap `EP069_FINDINGS_RESOLUTION.md`/`EP069_ARCHITECTURE_AUDIT.md` Finding EP069.1-AUDIT-002 flagged as missing for `ai.fallback_enabled`. This is genuine evidence, not a test that "would pass even if the implementation were wrong": reaching into `bootstrap.command_router._modules["ai"]._service._provider_manager` and calling the real `list_fallback_candidates()` exercises the entire real wiring path. |

### 11.2 The specific "configured-order-then-alphabetical-while-filtering" claim (STEP 3 task Section 5, final paragraph)

No single test exercises **all three** of (partial `fallback_order`) + (an excluded provider) + (an unavailable provider) simultaneously in one scenario. The individual pairwise interactions are each tested once (ordering+availability in one test, ordering+exclusion in another), and Section 8.5 of this audit independently establishes structural correctness for the triple combination by code inspection — but no test empirically exercises all three at once. This is a genuine, if minor, coverage gap. See Finding EP069.2-AUDIT-004.

### 11.3 Weak-assertion / false-confidence review

- `_test_provider_contract_unaffected` (Section 11.1) asserts only that a hand-written fake correctly implements the `AIProvider` abstract interface — it would pass even if `AIProvider`'s contract had been silently narrowed (e.g. an abstract method removed) as long as the fake doesn't happen to rely on the removed method, and it would not by itself catch a *broadening* of the contract (a new required abstract method) unless the fake were also updated, since Python's ABC machinery would then raise `TypeError` at `_FakeAIProvider(...)` construction — which it did not (all 26 assertions passed, confirmed in Section 13), so this test *would* in fact catch a broadened contract, just not via an explicit assertion — the ABC's own instantiation check is what provides that guarantee, not this test's assertions. This is real but indirect protection, appropriately weaker than the zero-diff evidence in Section 12, which is the stronger authority for this specific claim.
- No test uses a mock/spy in place of the real `ProviderManager` or real `AIService` for the integration tests (Section 11.1) — the fakes exist only at the `AIProvider`/`Config`/`PromptManager`/`ContextManager` leaf boundaries, which is the correct place for test doubles in this architecture (mirroring `tests/EP069/`'s own established fake shapes, explicitly credited as such in this file's own docstring). No integration test was found to be "hiding a real problem" behind an inappropriate mock.
- Test count (26) is an **assertion** count, not a test-method count (14 `_test_*` methods produce 26 `self.assert_*` calls) — consistent with this repository's own established convention (independently confirmed: `tests/EP069/test_ai_provider_fallback.py` has 61 `self.assert_*` calls contributing to its reported 68 passes, the difference coming from assertions inside loops). This is not misleading once understood, but is worth stating plainly rather than implying "26 tests" without qualification.
- No test reproduces the unhashable-list-element crash found in Section 8.4 — this is expected, since STEP 2 was not aware of it, but it means the STEP 2 test suite provides **no regression protection** against this defect. See Finding EP069.2-AUDIT-001/002.

## 12. Test Isolation / Registry Audit

- `tests/EP069_2/__init__.py` is empty, matching `tests/EP069/__init__.py`'s own convention exactly (confirmed by direct read of both files).
- `NAME = "EP069_2"` is a deliberate, correctly-reasoned choice: `TestRegistry.register()` (`src/testing/registry.py`, read in full) keys purely by `cls._tests[test_class.NAME.upper()] = test_class` — a dict assignment with no collision check or warning. Two classes registered with the same `NAME` would result in the second-imported one silently replacing the first in `TestRegistry._tests`, permanently hiding the first suite from `test EP069`/`test all` for the remainder of the process. Reusing `"EP069"` for this new suite would have created exactly this collision against `tests.EP069.test_ai_provider_fallback`'s own `AIProviderFallbackTest` (confirmed: that class's `NAME = "EP069"`, read directly). Choosing `"EP069_2"` avoids this correctly.
- This NAME-collision behavior is pre-existing, repository-wide technical debt in `TestRegistry` itself, not something EP-069.2 introduced or is scoped to fix (the STEP 3 task explicitly directs: "If the existing naming collision is technical debt, classify it appropriately rather than fixing it"). Classified here as **NOT A VALID FINDING for EP-069.2** — it is inherited, correctly worked around, and out of this EP's scope.
- Registration side effect: importing `tests.EP069_2.test_provider_fallback_ordering` executes the module-level `@TestRegistry.register` decorator on class definition, exactly matching every other EP's test module (confirmed by reading `tests/EP069/test_ai_provider_fallback.py`'s own equivalent decorator usage). No additional side effect (no file writes, no network calls, no global state mutation) occurs at import time — confirmed by reading the full module: all file I/O (`_write_full_bootstrap_config`) and all `Bootstrap()` construction happens lazily, inside the three bootstrap-wiring test methods, not at import time.
- `src/modules/test_module.py`'s new import line (`import tests.EP069_2.test_provider_fallback_ordering`) was placed immediately after the existing `tests.EP069.test_ai_provider_fallback` import — confirmed by direct read; this is the single-line, minimal, convention-following change the STEP 2 report claimed.
- **Global `ProviderRegistry` pollution**: every unit-level test in this suite constructs its own fresh `ProviderRegistry()` via the local `_make_registry()` helper (confirmed: `ProviderRegistry` is a plain class with no module-level singleton instance anywhere in `src/core/ai/provider_registry.py`, read in full). The three bootstrap-wiring tests each construct their own fresh `Bootstrap()` (which internally constructs its own fresh `ProviderRegistry()`), and call `bootstrap.shutdown()` in a `finally` block. No shared, mutable, cross-test registry state was found. Test-created providers/registries do not leak across tests.
- **`os.chdir` side effect**: the three bootstrap-wiring tests temporarily change the process's current working directory via `_ChdirGuard`. Confirmed the guard's `__exit__` unconditionally restores the original directory (no conditional skip on exception), so a failure inside a `with _ChdirGuard(...):` block cannot leave the test process's cwd altered for subsequent tests or suites. This is a process-global side effect during the `with` block's body, though — if `TestRunner` or another suite's test were somehow interleaved with this one on another thread during that narrow window, it could observe the wrong cwd; this repository's test execution model (Section 13, confirmed via direct `TestRunner.run_all()` reading) is strictly sequential/single-threaded, so this is not a live risk today, but is worth noting as a latent fragility if the test runner is ever made concurrent. LOW severity, noted in Findings.

## 13. Runtime / Thread-Safety Audit

- `fallback_order` cannot be mutated after `ProviderManager` construction: no setter, no public/private mutator method exists anywhere in the 231-line file (confirmed by full read). The only write to `self._fallback_order` is the one line in `__init__`.
- Concurrent calls to `list_fallback_candidates()`: each call independently computes `excluded`, `eligible`, `eligible_by_name`, `seen`, `ordered`, and `unlisted` as fresh local variables — no shared mutable state is read-modify-written across calls. The only shared state read is `self._registry` (already thread-safe per `ProviderRegistry`'s own `Lock`-protected `list()`, confirmed by direct read of `provider_registry.py`) and `self._fallback_order` (read-only after construction, per above). Two threads calling `list_fallback_candidates()` concurrently cannot observe a torn or inconsistent `self._fallback_order`, because it is never modified after `__init__` — no lock is required for this specific field, and none was added, correctly matching the design's own Section 17 reasoning.
- No new lock, thread, or async primitive was introduced anywhere in this EP's diff (confirmed: `from threading import Lock` import in `provider_manager.py` is pre-existing, unchanged; `self._lock` continues to guard only `_current_name`/`_enabled`, exactly as before).
- No realistic concurrency risk was found beyond the already-noted, narrow, non-live `os.chdir` test-isolation observation (Section 12).

## 14. Backward Compatibility Audit

Directly re-verified, independent of the STEP 2 report:

- **Absent `fallback_order`** (no key in a `ProviderManager(...)` call, and no key in `config.yaml`): `list_fallback_candidates()` returns `eligible` unchanged — byte-for-byte the same object-construction path as pre-EP-069.2 code (the `if not self._fallback_order: return eligible` branch is taken, and `eligible`'s computation is textually identical to the old method body). Confirmed via independent re-execution (Section 13 test run below) of `_test_absent_order_preserves_alphabetical` and `_test_bootstrap_absent_fallback_order_preserves_alphabetical`.
- **`fallback_order` = `[]`**: `not []` is `True` in Python, so this takes the identical branch as "absent" — confirmed by direct code read, not merely inferred.
- **`fallback_enabled: false`**: confirmed via independent re-execution of `_test_fallback_disabled_ignores_configured_order` that the primary provider's failure remains final and the fallback candidate (`gemini`, even though configured first in `fallback_order`) is never invoked (`len(gemini.ask_calls) == 0`).
- **Existing configuration files without the new key**: `config.get("ai.fallback_order", [])` returns the default `[]` for any config lacking the key — no `KeyError`, no exception, no migration required. Confirmed by direct read of `Config.get()`'s dict-based implementation (`src/core/config.py`) and by the bootstrap-wiring absent-key test.

**Invariant confirmed**: EP-069.2 changes zero observable EP-069.1 behavior unless an operator explicitly sets a non-empty `ai.fallback_order`.

## 15. Scope Boundary Audit

Full-tree diff performed independently during this audit (fresh extraction of the original pre-EP-069.1 archive, compared against the current working tree, with `__pycache__`/`.pyc` excluded):

```
config/config.yaml                                  (differs)
docs/architecture/designs/EP069_2_DESIGN.md          (new, STEP 1)
src/bootstrap.py                                     (differs)
src/core/ai/provider_manager.py                      (differs)
src/modules/test_module.py                           (differs)
tests/EP069_2/                                       (new, STEP 2)
```

No other file in the entire repository differs from the pre-EP-069.1 archive. Specifically confirmed **unchanged** (zero diff):

- `src/services/ai_service.py`
- `src/core/ai/provider.py`
- `src/core/ai/provider_registry.py`
- `src/core/ai/provider_factory.py`
- `src/core/ai/claude_provider.py`, `src/core/ai/providers/gemini_provider.py`
- `src/core/tool/*` (Tool Engine)
- Capability Registry (`src/skills/capability_registry/`)
- Command Router (`src/core/command_router.py`)
- `docs/architecture/designs/EP069_DESIGN.md`
- `docs/architecture/audits/EP069_ARCHITECTURE_AUDIT.md`
- `docs/architecture/audits/EP069_FINDINGS_RESOLUTION.md`
- `CHANGELOG.md`, `docs/RELEASE_NOTES.md` (not present in this archive), `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`
- Every historical test under `tests/EP001` through `tests/EP068`

No cost-aware routing, token accounting, cost scoring, health checks, circuit breakers, load balancing, retry framework, provider-contract change, `AIService`-contract change, new provider, Tool Engine integration, Capability Registry integration, or unrelated refactoring was found anywhere in the diff. The implementation matches its declared scope exactly.

No secrets, `.pyc` files, `__pycache__` directories, log files, or runtime data artifacts were found in the diff (Python bytecode caches generated incidentally by running the suites during STEP 2/this audit were located and removed prior to this diff; none were part of the actual deliverable).

## 16. Regression Results

All three runs below were executed independently during this audit (not copied from the STEP 2 report), using direct `TestRunner`/`TestRegistry` invocation against the current working tree, with the full `requirements.txt` (minus `openwakeword`, which cannot install on this audit environment's Python version — an environment constraint, not a project defect) installed fresh into this audit environment.

**EP-069.2 suite** (`test EP069_2`):
```
Passed : 26
Failed : 0
Skipped: 0
```

**EP-069.1 suite** (`test EP069`):
```
Passed : 68
Failed : 0
Skipped: 0
```
Confirms EP-069.1's own suite is completely unaffected by EP-069.2's changes.

**Full registered-suite regression** (every suite in `TestRegistry`, run individually to avoid `run_all()`'s abort-on-first-uncaught-exception behavior — the same technique EP-069.1's own audit used):
```
Total passed: 7119
Total failed: 3
Total skipped: 1
Environment-blocked (crashed, not classified as failed): 2
```

Reproduced and identified, not assumed pre-existing:

- **EP046** (`AudioCaptureError: The 'sounddevice' package is not usable (missing package or missing PortAudio runtime library)`) — crashes at `AudioCapture.__init__`, before any assertion runs. Root cause is the audit environment's missing system-level PortAudio library, unrelated to `src/core/ai/*` or any file this EP touched.
- **EP048** (`StreamingAudioCaptureError`, same root cause) — same PortAudio absence.
- **EP047**: 47 passed, 2 failed. Reproduced the actual failure messages: `"Expected True"` and `"STT must remain available even if TTS construction fails"` — both in the Text-to-Speech/Speech-to-Text interaction area, unrelated to AI provider selection.
- **EP049**: 86 passed, 1 failed, 1 skipped. Reproduced the actual failure message: `"Expected True"` — in the Voice Assistant suite, unrelated to AI provider selection.

**Arithmetic check**: `7093` (established EP-069.1 baseline) `+ 26` (new EP-069.2 assertions) `= 7119` — exact match to the total observed. The count of failed (3) and skipped (1) suites, and the identity of the two environment-blocked suites (EP046, EP048), are unchanged from the established baseline. No new failure was introduced anywhere in the regression by this EP's changes.

## 17. Findings

**Finding ID: EP069.2-AUDIT-001**
Severity: MEDIUM
Category: Configuration robustness / unhandled exception
Location: `src/core/ai/provider_manager.py`, `list_fallback_candidates()` (`for name in self._fallback_order: if name in eligible_by_name`); `src/bootstrap.py` (`isinstance(ai_fallback_order, list)` validation, which checks only the container type)
Evidence: Directly reproduced during this audit (Section 8.4): constructing a `ProviderManager` with `fallback_order=[{"bad": "entry"}, "gemini"]` — a value that is a genuine Python `list` and therefore passes `src/bootstrap.py`'s existing `isinstance(..., list)` check — raises an unhandled `TypeError: unhashable type: 'dict'` the first time `list_fallback_candidates()` is called, because `name in eligible_by_name` requires hashing `name`.
Expected: Per `EP069_2_DESIGN.md` Section 14, invalid `ai.fallback_order` configuration should be treated as absent with a warning, never crash. The design's Section 14 explicitly enumerates "Invalid type for `ai.fallback_order`" but only discusses the case where the *whole value* is non-list-typed (e.g. a string) — it does not address a list containing invalid (unhashable) elements, which a YAML author could plausibly produce by accidentally writing a list of mappings.
Actual: The type check at the configuration boundary (`src/bootstrap.py`) is necessary but not sufficient — it validates the container, not its contents. A malformed-but-list-typed `ai.fallback_order` is silently accepted at startup and only crashes later, at the first actual fallback attempt, converting what should be a recoverable `ProviderError` into an unhandled `TypeError` that propagates out of `AIService.ask()` uncaught (the same propagation shape already described, for a different root cause, in `EP069_ARCHITECTURE_AUDIT.md` Finding EP069.1-AUDIT-004).
Impact: Any operator who misconfigures `ai.fallback_order` with a nested mapping or list (rather than a flat list of strings) will experience every fallback attempt failing with an unrelated `TypeError` instead of falling back to alphabetical order as the design intends and as every currently-passing test verifies for the cases it does cover. This is a genuine, reproducible defect, not a hypothetical one — but it requires a specific, non-default misconfiguration to trigger, and does not affect any currently-passing test or any default/typical configuration.
Recommendation: In a future revision, validate each element of `ai.fallback_order` is a `str` (e.g. filter out or warn-and-drop non-string entries) at the same `src/bootstrap.py` validation site, before passing the list into `ProviderManager`. Do not implement this during STEP 3.

**Finding ID: EP069.2-AUDIT-002**
Severity: LOW
Category: Test coverage
Location: `tests/EP069_2/test_provider_fallback_ordering.py`
Evidence: No test reproduces the unhashable-element crash described in Finding 001. Additionally, no `AIService`-level integration test exercises the specific shape where every name in `fallback_order` is ineligible (unregistered/unavailable/excluded) and only unlisted providers remain — this exact shape is verified only at the `ProviderManager` unit level (`_test_unknown_names_are_inert`, which happens to also demonstrate this shape as a side effect of its own primary purpose), not through the real `AIService.ask()` fallback loop.
Expected: Per this repository's own established pattern of pairing unit-level and integration-level coverage for load-bearing behavior (mirrored from `tests/EP069/test_ai_provider_fallback.py`'s own dual-layer approach), both gaps would ideally have dedicated coverage.
Actual: The gaps exist; neither currently causes a false-positive test result (the underlying code is correct for the "only unlisted remain" case, per Section 10, and incorrect — genuinely crashing — for the unhashable-element case, per Finding 001, with no test to catch it).
Impact: Low on its own; directly enables Finding 001 to have shipped without being caught by the STEP 2 test suite.
Recommendation: Add a regression test reproducing Finding 001 once a fix is designed, and add one `AIService`-level integration test for the "only unlisted providers remain eligible" shape, before STEP 4 or in a future revision.

**Finding ID: EP069.2-AUDIT-003**
Severity: LOW
Category: Test quality
Location: `tests/EP069_2/test_provider_fallback_ordering.py`, `_test_provider_contract_unaffected`
Evidence: This test only exercises a hand-written fake's conformance to the `AIProvider` interface; it does not itself prove `AIProvider`'s abstract method set is unchanged relative to the pre-EP-069.2 version (it would pass unmodified even if `provider.py` had been rewritten from scratch with an identical-looking interface).
Expected: A test whose name claims to verify contract *stability* would ideally diff against the previous contract, not merely demonstrate current conformance.
Actual: The stronger evidence for this specific claim is the full-tree zero-diff on `src/core/ai/provider.py` (Section 15), which this audit performed independently; the test itself provides weaker, indirect protection (via Python's ABC instantiation check implicitly rejecting a broadened contract, per Section 11.3).
Impact: Very low — the claim this test's name makes is true, but for a different reason than the test itself demonstrates. No live defect.
Recommendation: None required for STEP 4; if ever revisited, either rename the test to reflect what it actually verifies (fake-conformance) or supplement it with an explicit inspection of `AIProvider.__abstractmethods__`.

**Finding ID: EP069.2-AUDIT-004**
Severity: LOW
Category: Test coverage
Location: `tests/EP069_2/test_provider_fallback_ordering.py`
Evidence: No single test simultaneously combines (a) a partial `fallback_order`, (b) an `exclude`-d provider, and (c) an unavailable provider in one scenario, per Section 11.2.
Expected: Per the STEP 3 audit brief's explicit callout, tests should ideally prove the three-way interaction empirically, not only structurally (by code inspection, Section 8.5).
Actual: Each pairwise interaction is tested once; the triple combination is not empirically exercised, though it is correctly reasoned about by code structure.
Impact: Low — the code path is a straightforward composition of already-independently-tested filters with no special-cased interaction logic that could hide a defect specific to the triple case.
Recommendation: Add one combined-scenario test before STEP 4 or in a future revision, for defense-in-depth; not required to unblock STEP 4 given the structural guarantee in Section 8.5.

**Finding ID: EP069.2-AUDIT-005**
Severity: LOW
Category: Documentation accuracy
Location: `docs/architecture/designs/EP069_2_DESIGN.md`, Section 12 (pseudocode)
Evidence: Per Section 7.1 of this audit, the design document's own Section 12 pseudocode does not deduplicate a `fallback_order` list that itself contains repeated names, while the actual implementation correctly does (via a `seen` set) — matching the STEP 2 task's explicit "no duplicates" requirement, which the design's literal pseudocode does not itself satisfy.
Expected: A STEP 1 design document's pseudocode should match the behavior its own prose (Section 14's "Duplicate names in the list: the first occurrence wins... No error raised") already commits to.
Actual: The prose is correct and was correctly implemented; only the illustrative code sample in Section 12 is incomplete relative to that same document's own Section 14.
Impact: Negligible — no implementation defect resulted; a future reader of the design document in isolation (without reading the implementation) could be misled into thinking the naive pseudocode is what was built.
Recommendation: Cosmetic correction to `EP069_2_DESIGN.md` Section 12 in a future documentation pass, not required before STEP 4. Not implemented during this audit (STEP 3 permits no document changes other than this audit file).

**Finding ID: EP069.2-AUDIT-006**
Severity: LOW
Category: Test isolation / latent fragility
Location: `tests/EP069_2/test_provider_fallback_ordering.py`, `_ChdirGuard`
Evidence: Per Section 12, the three bootstrap-wiring tests temporarily change the process's current working directory. The guard correctly restores it unconditionally on exit, and this repository's test execution model is sequential (confirmed via `src/testing/runner.py`), so no live risk exists today.
Expected: N/A — this is a latent, not active, risk.
Actual: If test execution in this repository is ever made concurrent (e.g. parallel suite execution), a test relying on the process-global cwd during this narrow window could observe an unexpected directory.
Impact: None under the current, verified-sequential execution model.
Recommendation: No action required unless/until the test runner becomes concurrent; document as a residual, environment-dependent assumption.

**Finding ID: EP069.2-AUDIT-007 (carried forward, not new)**
Severity: MEDIUM (unchanged from EP-069.1)
Category: Architecture / undefined behavior (inherited)
Location: `src/core/ai/provider_manager.py`, `list_fallback_candidates()`'s `is_available()` call
Evidence: This is `EP069_ARCHITECTURE_AUDIT.md` Finding EP069.1-AUDIT-004, restated because EP-069.2's new ordering code executes in the same method and inherits the exact same unguarded `is_available()` call — a misbehaving provider's `is_available()` raising would crash `list_fallback_candidates()` exactly as it could before EP-069.2, with or without `fallback_order` configured.
Expected: N/A — this is explicitly out of EP-069.2's scope per the STEP 2 task ("Do not fix deferred STEP 3/3.1 findings from EP-069.1").
Actual: EP-069.2 neither fixes nor worsens this pre-existing risk. It is unchanged.
Impact: Same as originally assessed in EP-069.1's own audit.
Recommendation: **NOT A VALID (NEW) FINDING for EP-069.2** — already tracked under EP069.1-AUDIT-004; listed here only for completeness of this audit's "inherited risk" review, per Section 4's "safe under failure conditions" objective.

## 18. Finding Severity Summary

| Severity | Count | IDs |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 1 (new) + 1 (inherited, not new) | EP069.2-AUDIT-001; EP069.2-AUDIT-007 (carried forward from EP-069.1, not a new EP-069.2 finding) |
| LOW | 5 | EP069.2-AUDIT-002, -003, -004, -005, -006 |
| **Total new findings attributable to EP-069.2** | **6** | AUDIT-001 through -006 |

## 19. Overall Verdict

### PASS WITH WARNINGS

No CRITICAL or HIGH finding exists. Design-to-code conformance is otherwise exact (Section 7), all STEP 2 task requirements (Section 3 of that task) are structurally and empirically satisfied (Sections 8-10), EP-069.1's semantics are provably unaffected (Section 10, Section 14), the scope boundary is exactly as declared with zero unrelated file changes (Section 15), and independently-reproduced regression results exactly match the expected baseline plus the new suite's own passes with no new failures (Section 16). One genuine, reproducible MEDIUM-severity defect was found (EP069.2-AUDIT-001: an unhashable element inside an otherwise-valid `fallback_order` list crashes fallback evaluation with an unhandled `TypeError`) — this is a real gap in the design's own error-handling section (it anticipated the whole-value-wrong-type case but not the malformed-element case), not a deviation from what was designed, and it requires a specific, non-default misconfiguration to trigger; it does not manifest under any default configuration or any currently-passing test scenario. The remaining five findings are LOW-severity test-coverage and documentation-precision gaps that do not indicate a live defect. EP-069.2 may proceed to STEP 4 with these findings documented and tracked for a future revision or EP-069.x slice, consistent with how EP-069.1's own MEDIUM findings were handled at the equivalent point in that EP's lifecycle.

## 20. Recommended Next Step

Proceed to STEP 4 (documentation synchronization). Track Finding EP069.2-AUDIT-001 (and its companion test-coverage gap, EP069.2-AUDIT-002) in `docs/BACKLOG.md` or a future EP-069.x STEP 1 as a known, non-blocking configuration-robustness gap, mirroring how `EP069_ARCHITECTURE_AUDIT.md`'s own MEDIUM findings (EP069.1-AUDIT-001, -002, -004) were carried forward rather than fixed reactively mid-audit. Do not implement any fix during STEP 3.1 unless a corrective-action decision is explicitly made to do so as a separate, scoped step.
