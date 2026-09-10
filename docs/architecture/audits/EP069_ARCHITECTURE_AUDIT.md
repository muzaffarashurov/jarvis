# EP-069.1 Architecture Audit — Automatic AI Provider Fallback on Request Failure

STEP 3: Independent Architecture Audit

## 1. Title

EP-069.1 Architecture Audit — Automatic AI Provider Fallback on Request Failure

## 2. EP / Version

EP-069.1 (parent: EP-069 — AI Provider & Tool Registry, planning identifier only). STEP 2 implementation as delivered — no revision suffix; this is the first audit pass.

## 3. Audit Status

COMPLETE. Adversarial, independent review of the STEP 2 implementation against `docs/architecture/designs/EP069_DESIGN.md` and this repository's established architecture. No production code, test, or configuration file was modified during this audit — verified in Section 20/26.

## 4. Audit Objective

Determine whether EP-069.1 is architecturally correct, faithful to its approved design, backward compatible, sufficiently tested, safe under failure conditions, free of scope creep, consistent with prior EPs, and ready for STEP 4 — independent of the fact that STEP 2 reported 68/68 passing tests and a clean regression run. Passing tests are treated as evidence, not proof (Section 32 of the governing instructions).

## 5. Scope

In scope: `src/core/ai/provider_manager.py`, `src/services/ai_service.py`, `src/bootstrap.py`, `config/config.yaml`, `src/modules/test_module.py`, `tests/EP069/`, and `docs/architecture/designs/EP069_DESIGN.md` itself (design-quality audit). Also independently re-inspected: `AIProvider`/`ProviderRegistry`/`ProviderFactory`/`ClaudeProvider`/`GeminiProvider`/`ConfigDrivenProvider` (unchanged, but their exact behavior is load-bearing for this audit's findings), `src/core/tool/*` (EP-031), `src/skills/capability_registry/skill.py` (EP-056), and EP-064 through EP-068's design/audit documents for architectural precedent.

## 6. Evidence Reviewed

- Direct reading of `src/services/ai_service.py` lines 468-608 (the entire `ask()` method, post-EP-069.1) and its module docstring.
- Direct reading of `src/core/ai/provider_manager.py` in full (134 lines).
- Direct reading of `src/core/ai/provider_registry.py` in full (thread-safety of `list()`).
- Direct reading of `src/core/ai/claude_provider.py`'s exception-raising sites (lines 155-294), specifically `_extract_error_message()`.
- Direct reading of `src/bootstrap.py`'s AI composition-root block and the new `fallback_enabled` line.
- Direct reading of `config/config.yaml`'s `ai:` block.
- Direct reading of `src/core/config.py`'s `Config.get()` (dotted-key resolution, missing-key/missing-section safety).
- Direct reading of `tests/EP069/test_ai_provider_fallback.py` in full (all 16 test methods and every fixture).
- Independent execution: the EP-069 suite in isolation, in reversed method order (order-independence probe), and the full 57-suite registered regression set, individually per suite (not via `run_all()`, which aborts on the first uncaught exception).
- Cross-reference against `tests/EP058/test_autonomous_planning.py` for this repository's own precedent on full-`Bootstrap`-level config-to-service wiring tests.
- Full-tree diff against a fresh extraction of the pre-EP-069.1 archive (established as this audit's git-equivalent baseline; see Section 20).

## 7. Design-to-Code Traceability

| Design Requirement | Implementation | Evidence | Status |
|---|---|---|---|
| Fallback disabled by default (`ai.fallback_enabled: false`) | `config/config.yaml` new key; `AIService.__init__(..., fallback_enabled: bool = False)` | `config/config.yaml` diff; `ai_service.py` constructor | PASS |
| `ProviderManager.list_fallback_candidates(exclude)` added, additive only | New method, no change to any pre-existing method | `provider_manager.py` diff (pure addition) | PASS |
| Candidate = registered, `is_available()==True`, not in `exclude` | List comprehension exactly matching this predicate | `provider_manager.py` lines implementing `list_fallback_candidates` | PASS |
| Deterministic, name-sorted order | Delegates to `ProviderRegistry.list()`, itself `sorted(..., key=name())` | `provider_registry.py` `list()` docstring + body | PASS |
| Prompt built exactly once, reused for every candidate | `built_prompt` constructed before the loop; loop only calls `candidate.ask(built_prompt.rendered)` | `ai_service.py` lines 534-552 | PASS |
| Only different, already-registered providers attempted (never same-provider retry) | `attempted` list seeded with the primary's name before the loop's first iteration; every subsequent exclude set is cumulative | `ai_service.py` lines 544-550, 572 | PASS |
| Bounded fallback (no infinite loop) | Each iteration adds exactly one new name to `attempted`; loop only continues while `list_fallback_candidates` returns a non-empty, always-shrinking set | `ai_service.py` lines 548-597; see Section 9 for the caveat on registry mutation mid-request | PASS, with a documented residual risk (Finding EP069.1-AUDIT-004) |
| Eligibility table (Unavailable/Network/Timeout/RateLimit eligible; Configuration/Authentication/base ProviderError not) | `_FALLBACK_ELIGIBLE_ERRORS` frozen tuple + `isinstance` check | `ai_service.py` module-level constant + line 562-564 | PASS |
| Final exhausted-fallback error names every attempted provider and its failure type | `failure_summary` list, joined into `AskResult.error` | `ai_service.py` lines 560, 583-589 | PASS |
| `AskResult.provider` on failure names the *originally selected* provider | Every failure return path uses `provider=name` (the pre-loop variable), never `candidate.name()` | `ai_service.py` lines 570, 585 | PASS |
| `AskResult.provider` on success names the provider that *actually* served the request | Success path uses `provider=candidate.name()` | `ai_service.py` lines 602-608 | PASS |
| `ai use <provider>` / `get_current()` unaffected by fallback (Owner Decision D1) | No call to `set_current()` anywhere in `ask()` | `ai_service.py` — confirmed absent | PASS |
| Fallback-decision logging: provider names + exception class names only, never raw prompt/response | New `logger.info`/aggregated `logger.error` lines use only names/`type(exc).__name__` | `ai_service.py` lines 579-582, 592-595 | PASS for the *new* lines; see Finding EP069.1-AUDIT-001 for the *pre-existing, reused* per-attempt log line |
| `AIProvider` contract unchanged | No new abstract method; five concrete/placeholder providers unmodified | Full diff shows zero change to `provider.py`, `claude_provider.py`, `gemini_provider.py`, `provider_factory.py` | PASS |
| `tests/EP069/` self-contained, `NAME="EP069"`, registered in `test_module.py` | Confirmed | `test_module.py` diff; `tests/EP069/test_ai_provider_fallback.py` | PASS |
| Protected files untouched (`src/core/tool/*`, `capability_registry/skill.py`, historical `tests/EP0NN/`) | Confirmed via full-tree diff | Section 20 | PASS |
| `ai.retry_count` left semantically untouched | Confirmed — diff shows only a new key appended after the unmodified line | `config/config.yaml` diff | PASS |

No requirement was found in FAIL or NOT VERIFIABLE status. Two requirements carry a documented residual risk despite an overall PASS classification (see Findings 001 and 004); these are not traceability failures — the code does exactly what the design specifies — but the design's own underlying assumption is not fully supportable, which is a design-quality finding (Section 30 below), not an implementation defect.

## 8. Architecture Assessment

The implementation places the *policy* (when to fall back, how many attempts) in `AIService`, and the *mechanism* (which providers currently qualify) in `ProviderManager.list_fallback_candidates()`, which is the same split of responsibility the pre-existing code already used for provider selection generally (`AIService` never touches `ProviderRegistry` directly). No new class, no new file, no new abstraction layer was introduced. This matches Section 25's "smallest coherent change" test: the same behavior could not plausibly have been achieved with meaningfully less code without either (a) duplicating registry-filtering logic inline in `AIService` (worse — breaks One Responsibility) or (b) inventing a `FallbackPolicy` class (unwarranted for a single, five-line predicate). No architectural concern is raised here.

## 9. Provider Selection Assessment

- **Same provider selected twice?** No. `attempted` is seeded with the primary's name at the top of the very first loop iteration and is cumulative; `list_fallback_candidates(exclude=attempted)` excludes every name in it. Independently traced through all three fallback-chain tests (`_test_multiple_fallback_providers_deterministic_order`, `_test_all_eligible_providers_fail_bounded_and_reported`) plus a fresh manual trace of the source — confirmed no path re-adds an already-attempted name to the candidate pool.
- **Fallback provider equal to primary?** No — same mechanism as above.
- **Unavailable or disabled providers selected?** No — `is_available()` is part of the candidate filter predicate; a `ConfigDrivenProvider` placeholder reporting `DISABLED`/`NOT_CONFIGURED` status returns `is_available() == False` (confirmed by reading `provider_factory.py`'s `ConfigDrivenProvider.is_available()`), so it is never selected.
- **Deterministic ordering — actual contract, not accident?** Confirmed as an actual, documented contract: `ProviderRegistry.list()`'s own docstring states "sorted by `name()`" and its implementation calls Python's `sorted()` with an explicit key — this is not incidental dict-iteration order, and `list_fallback_candidates()`'s own docstring explicitly commits to reusing that ordering. Independently verified with a real `ProviderRegistry`/`ProviderManager` (not a fake) registering three providers out of alphabetical order and calling twice to rule out any hidden non-determinism (`_test_list_fallback_candidates_orders_by_name`).
- **Registry mutation during iteration?** `ProviderRegistry.list()` takes its lock, builds a fresh `sorted()` list, and releases the lock before returning — this is a snapshot, so concurrent `register()`/`remove()` calls cannot corrupt an in-progress iteration (no `RuntimeError: dict changed size during iteration` is possible). However, see Finding EP069.1-AUDIT-004 for the residual question of what a *newly-registered* provider mid-request means for the loop's iteration bound.
- **Duplicate providers?** Cannot occur — `ProviderRegistry.register()` raises `ProviderRegistryError` on a duplicate name.
- **Empty registry / only-primary-registered?** Handled correctly by construction: `list_fallback_candidates` returns `[]`, the "exhausted" branch fires immediately with a `failure_summary` of exactly one entry. **Not directly exercised by a dedicated test** — see Finding EP069.1-AUDIT-005 (test coverage gap, not a code defect; the general N-provider exhaustion path is tested with N=3, and the empty-list branch is the same code path, just reached in one iteration instead of two).
- **`is_available()` itself raising an unexpected exception?** **Not handled.** See Finding EP069.1-AUDIT-004 — this is a real, undefined-behavior gap, not merely theoretical: `is_available()` is a method every third-party or future provider must implement, and nothing in `AIProvider`'s contract or `list_fallback_candidates()` catches or documents behavior for a misbehaving implementation.

## 10. Fallback Loop Assessment

Traced line-by-line (`ai_service.py` lines 544-597). The loop is a `while True` with exactly two exits: `break` on success (line 598, immediately after the `try`/`except`, only reached when no exception was raised) and an early `return` inside the `except` block for every failure branch that isn't "continue to next candidate." The only path that `continue`s is line 597, reached only when `remaining` (line 572) is non-empty. Because `remaining` is computed by excluding every name in the monotonically-growing `attempted` list, and the underlying provider set is finite (bounded by however many providers are registered in `ProviderRegistry` at the time `list()` is called), the loop must terminate: **maximum possible attempts in one `ask()` call = number of currently-registered providers** (today, 5: `claude`, `gemini`, `openai`, `ollama`, `lmstudio` — confirmed via `ProviderFactory.KNOWN_PROVIDER_NAMES` and `build_all()`'s unconditional registration of all five). No recursion exists (`ask()` never calls itself). No duplicate attempt is possible (Section 9). No accidental retry of the primary is possible (Section 9). No mutation of `attempted` or `failure_summary` occurs outside the single control-flow path shown. No interaction whatsoever with `ai.retry_count` — confirmed by `grep` showing zero references to that key anywhere in `ai_service.py`, `provider_manager.py`, or `bootstrap.py`.

**Direct answer to the mandated question:** *Can one request cause more provider attempts than intended?* No, under the registry's state as observed at the moment of the first `list_fallback_candidates()` call within that request, and no under normal operation (providers are registered once, at bootstrap, and never re-registered at runtime by any exposed command). The only way this bound could be exceeded is if the registry started with strictly more providers registered than the four fallback slots this audit observed (i.e., the bound scales with configuration, not with EP-069.1's own logic) — that is a controlled parameter of the deployment, not an EP-069.1 defect. See Finding EP069.1-AUDIT-004 for the narrower, still-open question of runtime registry mutation.

## 11. Failure Taxonomy Assessment

| Exception | Fallback? (design) | Actual behavior | Design-compliant? |
|---|---:|---|---|
| `ProviderUnavailableError` | Yes | `isinstance(exc, _FALLBACK_ELIGIBLE_ERRORS)` → True | Yes |
| `ProviderNetworkError` | Yes | → True | Yes |
| `ProviderTimeoutError` | Yes | → True | Yes |
| `ProviderRateLimitError` | Yes | → True | Yes |
| `ProviderConfigurationError` | No | → False (not in tuple) | Yes |
| `ProviderAuthenticationError` | No | → False (not in tuple) | Yes |
| `ProviderError` (base, uncategorized) | No | → False (not in tuple; `isinstance` on the exact base class against a tuple of *subclasses* correctly returns False) | Yes |

The implementation uses a single broad `except ProviderError as exc:` followed by an `isinstance(exc, _FALLBACK_ELIGIBLE_ERRORS)` check, **not** a chain of narrower `except` clauses. This is architecturally sound, not a weakness: it guarantees every `ProviderError` subtype (including any not yet imagined) is *caught* uniformly (so none can accidentally propagate uncaught and crash `ask()`), while eligibility is decided by an explicit, closed, reviewable allow-list rather than a deny-list — a new future `ProviderError` subclass defaults to *non-eligible* (fail-closed) unless someone deliberately adds it to `_FALLBACK_ELIGIBLE_ERRORS`. A subclass of an already-eligible type (e.g. a hypothetical `ClaudeSpecificTimeout(ProviderTimeoutError)`) would inherit eligibility via `isinstance`'s transitivity — this is very likely the intended behavior for a specialization, not a flaw, but it is worth stating explicitly since it was not called out anywhere in `EP069_DESIGN.md` itself (a minor design-documentation gap, not a code defect).

## 12. Error Propagation Assessment

| # | Scenario | What escapes `ask()` | Diagnostics preserved? |
|---|---|---|---|
| 1 | Primary success | `AskResult(success=True, provider=<primary>, ...)` | N/A |
| 2 | Primary eligible failure, fallback disabled | `AskResult(success=False, provider=<primary>, error=str(exc))` — identical to pre-EP-069.1 | Yes (unchanged) |
| 3 | Primary non-eligible failure | Same as #2, regardless of `fallback_enabled` | Yes |
| 4 | Primary eligible failure, fallback succeeds | `AskResult(success=True, provider=<fallback>, ...)` | Primary's failure is logged (line 559) but **not** surfaced in the successful `AskResult` itself — the caller sees only a clean success. This is a deliberate, reasonable design choice (a successful response shouldn't carry failure noise) but means a *caller* (as opposed to the log) cannot programmatically detect that a fallback occurred except by comparing `AskResult.provider` against whichever provider they expected. Worth noting as a minor observability gap, not a defect (see Finding EP069.1-AUDIT-006). |
| 5 | Primary eligible failure, fallback also eligible-fails, more candidates remain | Loop continues; nothing escapes yet | N/A |
| 6 | All eligible providers fail | `AskResult(success=False, provider=<primary>, error="All providers failed. p1: T1; p2: T2; ...")` | Yes — every attempted provider and its exception *type* is preserved. Raw exception *messages* are deliberately excluded from this aggregated field (correct, per EP-068 alignment — see Section 17). |
| 7 | No provider selected (`get_current() is None`) | `AskResult(success=False, provider="", error=_NO_PROVIDER_SELECTED)` — unchanged from pre-EP-069.1; `list_fallback_candidates` is never called (confirmed by test) | N/A |
| 8 | Provider unavailable (i.e. `current` itself unavailable) | Provider's own `ask()` raises `ProviderConfigurationError`/`ProviderUnavailableError` per its own logic — routed through the same taxonomy as any other failure | Yes |
| 9 | Unexpected (non-`ProviderError`) exception from any candidate | Propagates uncaught out of `ask()`, exactly as it did before EP-069.1 — confirmed by inspection: no `except Exception` anywhere in the modified code | Yes — no swallowing, no misclassification |

The "all providers fail" case (#6) is the one the governing instructions single out. The caller/log *does* know which provider failed first, which fallbacks failed and with what exception type, and what the aggregate outcome was — all three pieces of information are present in `failure_summary` and reflected in both the aggregated log line and the returned `error` string. Nothing is lost.

## 13. Unexpected-Exception Assessment

Confirmed by direct reading: the only `except` clause added or modified by EP-069.1 is `except ProviderError as exc:` (line 553) — identical in type to the pre-existing clause it replaces. A `ValueError`, `TypeError`, `KeyError`, or any third-party exception raised by a provider's `ask()` implementation is **not** caught by this clause and propagates directly out of `AIService.ask()`, uncaught — exactly matching pre-EP-069.1 behavior (confirmed: the original single-attempt code had the identical `except ProviderError` scope, no broader). No `except Exception` was introduced anywhere in `ai_service.py` or `provider_manager.py`. This correctly satisfies the instruction's explicit prohibition against recommending broad exception handling "merely for resilience" — none was added, and none should be recommended here, since a non-`ProviderError` exception represents a programming defect in a provider implementation, not a runtime condition fallback should mask.

## 14. Configuration Assessment

- `ai.fallback_enabled` is read via `config.get("ai.fallback_enabled", False)` in `bootstrap.py`, matching the exact pattern already used for `ai.enabled`/`ai.default_provider` on the two lines immediately above it.
- `Config.get()`'s dotted-key resolution (`src/core/config.py` lines 72-89) safely falls through to the `default` argument at any point a path segment is missing or not a dict — confirmed a missing `ai:` section entirely, or a present `ai:` section simply lacking `fallback_enabled`, both correctly yield `False`. No crash risk.
- **Type-coercion risk (pre-existing pattern, inherited, not newly introduced):** `bool(config.get("ai.fallback_enabled", False))` will evaluate to `True` for *any* non-empty string, including the string `"false"` if an operator mistakenly quotes the YAML value (`fallback_enabled: "false"` instead of `fallback_enabled: false`). This is identical, letter-for-letter, to the pre-existing risk already present in `ai.enabled=bool(config.get("ai.enabled", False))` one line above it in `bootstrap.py` — EP-069.1 did not introduce a new risk class, it reused an existing, already-accepted one. Documented as Finding EP069.1-AUDIT-007 (LOW) since it applies to the new key too, even though it is not EP-069.1-specific in origin.
- No duplicate configuration key was introduced. No dead configuration was introduced — `ai.fallback_enabled` is read and consumed by `bootstrap.py` and threaded into a used constructor parameter.
- `ai.retry_count` is confirmed byte-for-byte unmodified (Section 20) and is not referenced by any new or modified code — the pre-existing dead-config finding from STEP 1 remains exactly as documented, neither fixed nor worsened.
- **Not independently verified through an automated test:** whether `bootstrap.py`'s actual `Bootstrap.initialize()` path, given a real `config.yaml` on disk with the key absent, produces `AIService._fallback_enabled == False` end-to-end. This is a real, evidenced test-coverage gap — see Finding EP069.1-AUDIT-002 (this repository has a directly comparable precedent test at `tests/EP058/test_autonomous_planning.py` for `ai.enabled`/`ai.default_provider`, and EP-069.1 has no equivalent).

## 15. Backward Compatibility Assessment

Directly compared, both by code reading and by test evidence:

- **Same provider selection:** with `fallback_enabled=False` (the default), `current = self._provider_manager.get_current()` is resolved identically to before; no additional call is made.
- **Same call count:** `_test_fallback_disabled_preserves_existing_behavior` asserts `len(fallback.ask_calls) == 0` and `len(provider_manager.list_fallback_candidates_calls) == 0` when disabled — the new machinery is provably inert, not merely "expected to be."
- **Same exception/return behavior:** the same test asserts `result.error == "claude is down"` — the exact string a `ProviderUnavailableError("claude is down")`'s `str()` produces, with no added prefix/suffix, matching the pre-EP-069.1 line-for-line.
- **Same logging:** the per-attempt `logger.error(f"AI request failed (provider='{name}'): {exc}")` line is reused verbatim (same format string, same content) for the primary-only, no-fallback path — confirmed by direct source comparison against the pre-EP-069.1 baseline (the only textual change is the variable name `name`→`candidate_name`, which is value-identical on the primary's first iteration).
- **Same public API:** `ask()`'s signature (`prompt: str) -> AskResult`) is unchanged; `AskResult`'s field set is unchanged (confirmed via diff — no new field was added).

This is evidence-based, not an unverified claim: the specific test named above would fail if any of these four properties were violated (it asserts call counts, not just outcomes).

## 16. AIProvider Contract Assessment

Confirmed via full-tree diff: `src/core/ai/provider.py`, `src/core/ai/claude_provider.py`, `src/core/ai/providers/gemini_provider.py`, and `src/core/ai/provider_factory.py` are **byte-for-byte unmodified**. No abstract method was added or removed. No method signature changed. No provider-specific branching (`if name == "claude"` or equivalent) exists anywhere in `ai_service.py` or `provider_manager.py` — confirmed by `grep` for provider name literals in the modified files: the only string literals matching provider names appear in test fixtures (`tests/EP069/`), never in production code. The fallback mechanism operates exclusively through `AIProvider.name()`/`is_available()`/`ask()` — the same three methods already used for the pre-existing single-provider path — so a hypothetical sixth, entirely new provider type would participate in fallback with zero additional code, which is the correct outcome for an abstraction-respecting design.

## 17. Concurrency / Thread-Safety Assessment

`AIService` has historically been (and remains) accessed by a single composition-root instance shared across whichever consumers call it (CLI, and potentially a REST API path per `src/core/api/`). EP-069.1 introduces exactly three new local variables inside `ask()` (`candidate`, `attempted`, `failure_summary`) — all are function-local, never stored on `self`, and therefore cannot leak between concurrent invocations of `ask()` on the same `AIService` instance. `ProviderManager.list_fallback_candidates()` introduces no new instance state on `ProviderManager` either (confirmed: it reads `self._registry.list()` fresh every call and holds nothing between calls). `ProviderRegistry.list()` is already lock-protected (Section 9) and was not modified. **Conclusion: fallback state is entirely request-local; EP-069.1 introduces zero new shared mutable state.** Concurrent `ask()` calls cannot interfere with each other's provider selection or fallback ordering through anything EP-069.1 added. This project's broader threading model (whether `AIService.ask()` itself is ever invoked from more than one thread concurrently, e.g. from a REST handler) is unchanged by this EP and was not introduced or altered here — it is a pre-existing characteristic of the composition root, out of this EP's scope to alter or further audit.

## 18. Logging / EP-068 Assessment

Independently re-read `src/core/command_router.py`'s `dispatch()` (the EP-068 precedent) to confirm its exact discipline: log only `module_name` and `type(exc).__name__`, never `action`, never `str(exc)`. Then independently re-read every log statement EP-069.1 touches or introduces:

- **New (EP-069.1-introduced) log lines** — the `logger.info(f"AI request falling back from provider='{candidate_name}' to provider='{next_candidate.name()}'.")` line and the aggregated `logger.error("AI request failed on every eligible provider: " + ", ".join(failure_summary) + ".")` line — contain only provider names (a closed, five-value, code-authored set) and `type(exc).__name__` values (a closed, seven-value set). **Verified empirically**, not just by reading: `_test_fallback_logging_never_contains_prompt_or_response_text` injects a distinctive sentinel string as both the prompt and a fallback provider's successful reply text and asserts neither sentinel appears in any captured log line across a full fallback sequence; `_test_exhausted_fallback_logging_uses_exception_type_names_only` injects a distinctive "secret" substring into two providers' exception *messages* and asserts it does **not** appear in the aggregated all-failed log line, while confirming the exception *type names* do appear. Both tests pass. This directly answers the mandated question ("what happens when logging receives hostile/sensitive input?") with empirical evidence, not assumption.
- **Reused (pre-existing, unmodified in content) log line** — `logger.error(f"AI request failed (provider='{candidate_name}'): {exc}")` — is the *same* line that existed before EP-069.1, but EP-069.1 changes how many times it can fire per request: at most once before EP-069.1 (single provider, single attempt), at most N times now (once per candidate in the fallback chain, N ≤ number of registered providers). This line does include `str(exc)`, i.e. the exception's message text, not just its type. **This is the audit's most significant finding — see Finding EP069.1-AUDIT-001.** The risk is not hypothetical: `ClaudeProvider._handle_response()` (line 283-285) constructs a bare `ProviderError` for any non-401/403/429/5xx HTTP status using `self._extract_error_message(response)`, which the method's own docstring states returns "the API's own error message, or the raw response text" — i.e., server-controlled content that is not guaranteed to exclude an echo of request-derived text (many LLM APIs' validation-error bodies quote back the offending portion of a request). Note carefully: this specific `ProviderError` branch is **non-fallback-eligible** per Section 11's table, so EP-069.1 does not cause it to be logged *more often* than it already would have been for that exact failure — but the general finding (this log line's safety rests on an unverified assumption about provider-supplied text) is real, pre-existing, and now repeated up to N times per request for the *eligible* failure types too, none of which were shown to definitely never carry echoed content either (their messages are currently code-authored/static as of the two providers that exist today, but nothing enforces this for a *future* provider).

## 19. Test Quality Assessment

Applying the mandated test — "if I intentionally broke the fallback loop, would these tests fail?" — to each required scenario:

| Scenario | Test | Would a broken fallback loop be caught? |
|---|---|---|
| Primary success, no fallback | `_test_primary_success_no_fallback_attempted` | Yes — asserts `fallback.ask_calls == 0` and `list_fallback_candidates_calls == 0`, not just the return value |
| Fallback disabled | `_test_fallback_disabled_preserves_existing_behavior` | Yes — same call-count assertions |
| Eligible failure → fallback attempted | `_test_eligible_failure_triggers_fallback_attempt` | Yes — asserts the fallback's `ask_calls == 1` and the exact exclude-set passed |
| Non-eligible failure → no fallback | `_test_non_eligible_failure_never_triggers_fallback` | Yes — parameterized over all three non-eligible types, asserts zero fallback calls for each |
| Fallback success | `_test_fallback_provider_success_returns_its_response` | Yes — asserts `result.provider == "gemini"` (not the primary), catching a bug that reported the wrong provider on success |
| Multiple candidates, deterministic order | `_test_multiple_fallback_providers_deterministic_order` | Yes — asserts each provider's `ask_calls == 1` individually, catching both "skipped a candidate" and "attempted a candidate twice" bugs |
| All fail, bounded | `_test_all_eligible_providers_fail_bounded_and_reported` | Yes for duplicate-attempt bugs (per-provider call-count assertions) and for lost-diagnostics bugs (substring assertions on `result.error`); **no** for a true infinite-loop bug — a hang would only surface as a test-runner timeout, not a clean assertion failure. This is a genuine, if minor, gap — see Finding EP069.1-AUDIT-003. |
| Identical prompt per candidate | `_test_fallback_candidate_receives_identical_rendered_prompt` | Yes — asserts `fallback.ask_calls[0] == primary.ask_calls[0]` |
| `list_fallback_candidates()` ordering (real registry) | `_test_list_fallback_candidates_orders_by_name` | Yes — uses the *real* `ProviderManager`/`ProviderRegistry`, not a fake, so a regression in the actual sort/filter logic would be caught, not just in the test's own fake mirror of it |
| `list_fallback_candidates()` availability/exclusion (real registry) | `_test_list_fallback_candidates_excludes_unavailable_and_named` | Yes, same reasoning |
| EP-068 logging safety | Two dedicated sentinel-based tests (Section 18) | Yes — these are not "does it look safe" assertions, they inject adversarial content and check for its literal absence |
| Config default safety | **Not independently tested at the `bootstrap.py`/`Config` level** | No — see Finding EP069.1-AUDIT-002 |
| Duplicate-call / bounded-execution via explicit iteration cap | Present as a side effect of per-provider call-count assertions, not as a standalone "assert total attempts ≤ N regardless of what happens" invariant test | Partial — see Finding EP069.1-AUDIT-003 |

None of the tests use permissive mocks that would pass trivially regardless of implementation — every fake `AIProvider` records real call counts and real prompt arguments, and every assertion checks those recorded values rather than only the final `AskResult`. This is materially stronger than a "does it return success" style test suite. The gaps found (config-path integration, single-provider-registered degenerate case, explicit infinite-loop guard) are coverage gaps, not evidence that the current tests are false positives.

## 20. Regression Assessment

Executed every one of the 57 currently-registered test suites (56 pre-existing + the new `EP069`) individually via direct `suite_class().run()` calls (not `TestRunner.run_all()`, which aborts on the first uncaught exception and would have obscured the true per-suite picture). Result:

```
TOTAL passed=7093 failed=3 skipped=1
env_blocked=['EP046', 'EP048']
EP047: ['Expected True', 'STT must remain available even if TTS construction fails']
EP049: ['Expected True']
```

- **`EP046`, `EP048`**: raise an uncaught exception before any assertion runs, due to missing `vosk`/`sounddevice`+PortAudio in this sandbox — confirmed pre-existing and environment-only by installing every other declared dependency (including `PySide6`, which was also initially missing) and observing these two remain the only ones blocked by a genuinely unavailable native/ML dependency.
- **`EP047` (2 failures), `EP049` (1 failure, 1 skip)**: independently reproduced against a **fresh, untouched extraction of the pre-EP-069.1 archive** — identical failure count and identical error messages on the unmodified baseline. These are pre-existing, unrelated (Text-to-Speech and Voice Assistant, neither imports `AIService`/`ProviderManager`/`ProviderRegistry`) failures, not introduced by this EP.
- **Every AI/provider-adjacent suite** (`EP018` Context Engine, `EP054` Self Reflection, `EP055` Prompt Optimizer, `EP056` Capability Registry, `EP058` Autonomous Planning, `EP061`-`EP068` reliability EPs) passed with **exactly the same pass counts** as the pre-EP-069.1 baseline (verified by running the full baseline suite for direct numeric comparison: baseline total `7025 passed, 3 failed, 1 skipped`; EP-069.1 total `7093 passed, 3 failed, 1 skipped` — the delta, `+68`, exactly equals the new `EP069` suite's own passed count, and nothing else moved).

**No new failure was introduced anywhere in the regression suite.**

## 21. Protected-File Assessment

Full-tree diff (`diff -rq`) against a fresh extraction of the original pre-EP-069.1 archive, with all `__pycache__` bytecode-cache noise excluded, shows exactly these differences:

```
Modified: config/config.yaml
Modified: src/bootstrap.py
Modified: src/core/ai/provider_manager.py
Modified: src/services/ai_service.py
Modified: src/modules/test_module.py
Added:    docs/architecture/designs/EP069_DESIGN.md   (STEP 1, unchanged since)
Added:    tests/EP069/  (new package)
```

Explicitly verified byte-for-byte identical (zero diff) for every file `EP069_DESIGN.md` names as protected, specifically including: `src/core/tool/*` (all files, EP-031 Tool Engine), `src/skills/capability_registry/skill.py` (EP-056), `src/core/command_router.py`, `src/core/ai/provider.py`, `src/core/ai/provider_registry.py`, `src/core/ai/provider_factory.py`, `src/core/ai/claude_provider.py`, `src/core/ai/providers/gemini_provider.py`, every EP-016/017/018 engine file, and every file under `tests/EP001/` through `tests/EP068/`. `docs/BACKLOG.md`, `docs/architecture/JARVIS_ROADMAP.md`, `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, and `PROJECT_MANIFEST.md` are also confirmed unmodified. No unexpected modification was found anywhere in the tree.

## 22. Scope-Creep Assessment

Searched the full diff and the new test file for any of: cost/pricing terminology, token-cost calculation, LLM function/tool-calling schema constructs, any import of or reference to `src/core/tool/` or `src/skills/capability_registry/`, provider-scoring/health-check/circuit-breaker/load-balancing constructs, exponential-backoff or generic-retry-framework constructs, and any new concrete `AIProvider` implementation. **None found.** The only new production logic is the bounded fallback loop and its one supporting query method, exactly matching the design's Non-Goals list.

## 23. Dead-Code / Dead-Config Assessment

- `ProviderManager.list_fallback_candidates()` is used exactly once, from `AIService.ask()` — not dead.
- `AIService`'s new `fallback_enabled` constructor parameter is read exactly once, in the fallback-eligibility check — not dead.
- `_FALLBACK_ELIGIBLE_ERRORS` is referenced exactly once — not dead.
- `ai.fallback_enabled` is read exactly once, in `bootstrap.py` — not dead.
- `ai.retry_count` **remains dead**, exactly as it was before EP-069.1 (confirmed: still zero references anywhere in `src/`) — this is consistent with the design's explicit Owner Decision D9 (do not repurpose it) and is correctly *not* "cleaned up" here, per this STEP's own prohibition against incidental refactoring.
- No unreachable branch was found: every `if`/`return`/`continue` in the modified `ask()` body is reachable and is in fact exercised by at least one test (confirmed by cross-referencing each branch against the test list in Section 19).

## 24. Architectural Simplicity Assessment

No unnecessary abstraction, class, or state was introduced (Section 8). The one candidate for "could this be simpler" — inlining `list_fallback_candidates()`'s filter directly into `AIService.ask()` instead of adding a `ProviderManager` method — was considered and rejected correctly: doing so would require `AIService` to reach into `ProviderRegistry` directly, violating the pre-existing, explicitly documented invariant ("the rest of Jarvis is expected to depend only on ProviderManager... never on ProviderRegistry... directly," `provider_manager.py`'s own module docstring, unchanged from EP-014). The chosen design is the simpler one once that invariant is honored, not a more complex one.

## 25. Failure Matrix

| Scenario | Expected | Actual | Risk | Status |
|---|---|---|---|---|
| Primary success | Success, no fallback call | Confirmed by test | None | PASS |
| Fallback disabled | Pre-EP-069.1 behavior, byte-identical | Confirmed by test (call counts + exact error string) | None | PASS |
| Primary eligible failure | Fallback attempted (if enabled) | Confirmed | None | PASS |
| Primary non-eligible failure | No fallback, ever | Confirmed for all 3 non-eligible types | None | PASS |
| Fallback success | Fallback's response returned, `provider` field correct | Confirmed | None | PASS |
| First fallback also fails | Second fallback attempted, in order | Confirmed | None | PASS |
| Multiple fallback providers | Deterministic order, stop at first success | Confirmed (real registry ordering test + AIService-level test) | None | PASS |
| All providers fail | Bounded, all failures preserved in `error` | Confirmed | LOW — no explicit hang-detection assertion (Finding 003) | PASS with note |
| No providers registered / only primary | Exhausted branch fires with one entry | Code-path confirmed by reading; not directly unit-tested in isolation | LOW (Finding 005) | PASS with note |
| Unavailable provider (non-primary) | Excluded from candidates | Confirmed | None | PASS |
| Malformed configuration (`"false"` string) | Would silently enable fallback | Confirmed as a real risk, inherited from pre-existing `ai.enabled` pattern | LOW (Finding 007) | PASS with note |
| Unexpected (non-`ProviderError`) exception | Propagates uncaught, no fallback triggered | Confirmed by code inspection | None | PASS |
| Sensitive log content (prompt/response) | Never appears in any log line | Confirmed empirically via sentinel tests | None (new lines); MEDIUM residual (reused per-attempt line, Finding 001) | PASS with finding |
| Concurrent requests | No shared mutable state introduced | Confirmed by code inspection (request-local variables only) | None | PASS |
| `is_available()` raises unexpectedly | Undefined by design | Propagates uncaught mid-fallback-evaluation, undocumented | MEDIUM (Finding 004) | Gap |

## 26. Owner Decision Audit

| Decision | Design | Implementation | Correct? | Notes |
|---|---|---|---|---|
| D1 — `ai use`/current-provider unaffected by fallback | Never call `set_current()` from within a fallback | Confirmed absent | Yes | — |
| D2 — Reuse the single already-built prompt across all candidates | No re-run of Conversation/Context/Prompt Engine steps per candidate | Confirmed — `built_prompt` constructed once, before the loop | Yes | — |
| D3 — Cross-provider fallback only, never same-provider retry | No retry of the same provider | Confirmed by exclusion-set construction | Yes | — |
| D4 — Failure-type eligibility table | Unavailable/Network/Timeout/RateLimit eligible; Configuration/Authentication/base not | Confirmed exact match | Yes | See Section 11 — sound implementation, but the design's underlying "these messages are always safe to log" premise is not fully supportable (Finding 001) |
| D5 — Attempt bound is structural, not a configured counter | No `ai.fallback_max_attempts` key | Confirmed — no such key exists | Yes | — |
| D6 — Fallback order reuses registry's alphabetical order | No configured priority list | Confirmed | Yes | — |
| D7 — `list_fallback_candidates()` lives on `ProviderManager` | Not a new class | Confirmed | Yes | — |
| D8 — No new public API surface beyond one method + one config key | No new `AskResult` field, no new CLI action | Confirmed via diff | Yes | — |
| D9 — `ai.retry_count` left untouched | Not repurposed | Confirmed byte-for-byte unmodified | Yes | — |
| D10 — Files allowed to change (exact list) | As enumerated in Section 23 of the design | Matches exactly (Section 21 of this audit) | Yes | — |
| D11 — Test placement, self-contained `tests/EP069/` | New, dedicated package | Confirmed; no cross-EP import | Yes | — |

**Summary: 11/11 Owner Decisions correctly implemented as specified.** No decision was implemented differently from its design. The audit's findings concern the *soundness of the design's own assumptions* underlying D4 (Finding 001) and an *undefined case* the design did not address at all (Finding 004), not any deviation between design and code.

## 27. Acceptance Criteria Audit

Against `EP069_DESIGN.md` Section 26's ten checklist items:

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `AIProvider`/`ProviderRegistry`/`ProviderFactory`/`ClaudeProvider`/`GeminiProvider` byte-for-byte unmodified | PASS | Section 21 diff |
| 2 | `ProviderManager` has exactly one new public method, no other change | PASS | Section 7/23 |
| 3 | `fallback_enabled` absent/False → byte-identical behavior | PASS | Section 15, direct test evidence |
| 4 | `fallback_enabled=True`, eligible failure, alternative available → alternative tried with identical prompt, reported correctly | PASS | Section 7/10 |
| 5 | Non-eligible failure never triggers a second `ask()` call | PASS | Section 11, direct test evidence |
| 6 | Exhausted candidates → failure naming every attempted provider and its failure type | PASS | Section 12 |
| 7 | No log line in the fallback path contains prompt/response/raw `str(exc)` from fallback-evaluation exceptions | **PARTIAL** — true for every *new* log line; the *reused* per-attempt line still carries `str(exc)`, which this audit shows is not provably always safe (Finding 001). The acceptance criterion as literally worded ("no log line... contains... any `str(exc)` value derived from a `ProviderError` raised during fallback evaluation") is technically violated by design, not by an implementation bug — the design itself specifies reusing that line. | Section 18 |
| 8 | `tests/EP069/` exists, registered, self-contained, passes in full | PASS | Section 19/20 |
| 9 | No file outside the approved list modified | PASS | Section 21 |
| 10 | Every Section 25 coverage item has a corresponding passing assertion | PASS, with the caveats in Section 19 (a passing assertion exists for every item, though two items' assertions are weaker than ideal — bounded-loop-via-hang-only-detection, and the degenerate single-provider case is exercised only as a subset of a larger scenario, not standalone) | Section 19 |

**9 of 10 acceptance criteria fully satisfied; criterion 7 is not fully satisfied as literally worded**, because it was written (in STEP 1) on the same overclaimed assumption Finding 001 identifies — the design document, not the implementation, is the source of this shortfall.

## 28. Findings

**Finding ID: EP069.1-AUDIT-001**
Severity: MEDIUM
Category: Logging / EP-068 alignment / Design-document accuracy
Location: `src/services/ai_service.py` line 559 (`logger.error(f"AI request failed (provider='{candidate_name}'): {exc}")`); `docs/architecture/designs/EP069_DESIGN.md` Section 9/11/19 (the claim that `exc`'s message is "always a static, code-authored string... never user-supplied content")
Evidence: `src/core/ai/claude_provider.py` lines 283-285 construct a bare `ProviderError` using `self._extract_error_message(response)`, whose own docstring (line 318-325) states it returns "the API's own error message, or the raw response text" — i.e., content controlled by the remote API, not solely code-authored. This exact log line, reused verbatim from before EP-069.1, now fires up to once per fallback candidate (previously at most once per request) whenever any candidate in the chain raises a `ProviderError`.
Expected: A log statement's safety should not rest on an unverified assumption about third-party API response content, per EP-068's own established discipline (log closed, code-authored values only at failure boundaries).
Actual: The reused line logs `str(exc)` for every candidate's failure, and the design document asserts this is always safe without having examined `_extract_error_message()`'s actual behavior.
Impact: In the specific branch that constructs a bare `ProviderError` (non-401/403/429/5xx HTTP statuses), a validation-style error response from the Anthropic (or a future) API could, in principle, echo back a fragment of the request — this is not confirmed to happen today (the two current providers do not clearly do this in the observed code paths for the *fallback-eligible* exception types specifically), but nothing prevents it for the generic-`ProviderError` case, and nothing prevents a future provider's timeout/network/rate-limit/unavailable message construction from doing the same. EP-069.1 multiplies this line's firing frequency per request without re-examining its safety.
Recommendation: In a future revision, either (a) change this specific log line, for fallback-chain iterations, to log `type(exc).__name__` only (matching the new aggregated line's discipline) rather than `str(exc)`, or (b) add an explicit, tested guarantee to every current and future `ProviderError`-message-construction site that it never echoes request-derived content, and correct `EP069_DESIGN.md`'s Section 9/11 claim to state this as a verified invariant rather than an assumption. Do not implement this during STEP 3.

**Finding ID: EP069.1-AUDIT-002**
Severity: MEDIUM
Category: Test coverage
Location: `src/bootstrap.py` (the `ai.fallback_enabled` read site); `tests/EP069/test_ai_provider_fallback.py` (no corresponding test)
Evidence: `tests/EP058/test_autonomous_planning.py` establishes this repository's own precedent for verifying `ai.enabled`/`ai.default_provider` end-to-end through a real `Bootstrap.initialize()` call against a real on-disk `config.yaml`. No equivalent test exists for `ai.fallback_enabled` in `tests/EP069/`; every EP-069 test constructs `AIService` directly with an explicit `fallback_enabled` argument, bypassing the `config.get(...)` → `bootstrap.py` → `AIService.__init__` wiring path entirely.
Expected: Per this repository's own established precedent for AI-related boolean configuration, a full-bootstrap test confirming the config key's absence/presence produces the correct `AIService._fallback_enabled` value.
Actual: This wiring path is untested by automation; it is currently correct only by manual code inspection (Section 14).
Impact: A future refactor of `bootstrap.py`'s AI composition-root block could silently break this specific wiring (e.g., an argument-order mistake, since `AIService`'s constructor now takes six parameters) with no test catching it.
Recommendation: Add a `Bootstrap`-level integration test to `tests/EP069/` mirroring `tests/EP058/`'s pattern before STEP 4, or explicitly accept this gap as a documented, deliberate STEP 2 scope reduction.

**Finding ID: EP069.1-AUDIT-003**
Severity: LOW
Category: Test quality
Location: `tests/EP069/test_ai_provider_fallback.py`, `_test_all_eligible_providers_fail_bounded_and_reported`
Evidence: The test's "bounded" claim rests entirely on per-provider call-count assertions (each fake's `ask_calls` length) plus a sum-equals-3 assertion; there is no assertion independent of a potential infinite loop (e.g., no explicit iteration counter with a hard ceiling, no `assert time_elapsed < N`).
Expected: Per the governing audit instructions, a genuinely bounded-execution test should be robust even against an implementation bug that causes the loop to never terminate.
Actual: A true infinite-loop regression would manifest as the test process hanging, relying on an external test-runner timeout (if any) rather than a deterministic, fast assertion failure.
Impact: Low — the current implementation is provably bounded by code inspection (Section 10), so this is a defense-in-depth gap, not a live defect.
Recommendation: Consider adding a fake `ProviderManager.list_fallback_candidates()` that raises after being called more than `len(registered_providers)` times, turning a hypothetical future infinite loop into an immediate, clean test failure rather than a hang.

**Finding ID: EP069.1-AUDIT-004**
Severity: MEDIUM
Category: Architecture / undefined behavior
Location: `src/core/ai/provider_manager.py`, `list_fallback_candidates()`; `EP069_DESIGN.md` (silent on this case)
Evidence: `list_fallback_candidates()`'s list comprehension calls `provider.is_available()` for every currently-registered provider with no exception handling. `AIProvider.is_available()` is an abstract method every current and future provider implementation must supply; nothing in its contract (`provider.py`) guarantees it cannot raise.
Expected: The governing audit instructions explicitly direct: "Do not assume `is_available()` is infallible. If the implementation does not define behavior for an unexpected failure from availability checks, identify the risk."
Actual: An exception raised from any candidate's `is_available()` during fallback evaluation propagates out of `list_fallback_candidates()`, then out of the `except ProviderError` block in `ask()` that called it (superseding the original `ProviderError` being handled), and out of `ask()` itself entirely, uncaught — crashing the request with an exception whose type has nothing to do with AI-provider failure. Neither `EP069_DESIGN.md` nor the implementation's docstrings address this case.
Impact: A single misbehaving provider implementation (including a future third-party or placeholder provider with a coding defect in `is_available()`) can turn what should be a recoverable, fallback-eligible failure into an unhandled crash for every request that reaches the fallback-evaluation step, for as long as that provider remains registered — regardless of whether that specific provider was ever selected as `current`.
Recommendation: Decide (as a new Owner Decision) whether `list_fallback_candidates()` should defensively skip a candidate whose `is_available()` raises (logging the anomaly, per EP-068 discipline) or whether this is accepted as intentionally fail-loud behavior; document the decision explicitly in a design revision. Do not implement a fix during STEP 3.

**Finding ID: EP069.1-AUDIT-005**
Severity: LOW
Category: Test coverage
Location: `tests/EP069/test_ai_provider_fallback.py`
Evidence: No test constructs a scenario with exactly one registered provider (the primary) and zero others, exercising the "exhausted" branch on its very first iteration (`remaining == []` immediately). The existing "all fail" test uses three providers, reaching the same code branch only after two iterations.
Expected: The degenerate single-provider case is a distinct boundary condition worth its own explicit assertion.
Actual: The branch is code-path-identical and almost certainly behaves correctly (confirmed by inspection), but is not independently verified in isolation.
Impact: Very low — this is the same code path already exercised, just reached differently.
Recommendation: Add a small, standalone test for the zero-fallback-candidates-exist case before STEP 4, for completeness.

**Finding ID: EP069.1-AUDIT-006**
Severity: LOW
Category: Observability
Location: `src/services/ai_service.py`, success path (lines 599-608)
Evidence: When a fallback succeeds, `AskResult` carries no field distinguishing "this succeeded on the first try" from "this succeeded only after N fallback attempts" beyond the caller comparing `AskResult.provider` to whatever they expected. The design deliberately chose not to add a new field (Owner Decision D8).
Expected: N/A — this is consistent with the approved design, not a deviation.
Actual: A caller programmatically consuming `AskResult` (as opposed to reading logs) cannot distinguish a "clean" success from a "recovered via fallback" success except by this indirect comparison.
Impact: Low — logs do carry this information (Section 18); this only affects programmatic/automated consumers of `AskResult` who don't inspect logs.
Recommendation: None required; documented for completeness since it was explicitly requested that error-propagation paths be traced for lost information. This is an accepted, deliberate trade-off (D8), not a defect.

**Finding ID: EP069.1-AUDIT-007**
Severity: LOW
Category: Configuration robustness
Location: `src/bootstrap.py`, `fallback_enabled=bool(config.get("ai.fallback_enabled", False))`
Evidence: `bool("false")` evaluates to `True` in Python; a YAML author who writes `fallback_enabled: "false"` (quoted) instead of `fallback_enabled: false` (unquoted boolean) would silently enable fallback against their evident intent. This is byte-for-byte the same pattern already used for `ai.enabled` one line above.
Expected: N/A — this is an inherited, pre-existing repository-wide convention, not an EP-069.1-specific defect.
Actual: The risk now also applies to `ai.fallback_enabled`.
Impact: Low, and no worse than the pre-existing risk for `ai.enabled`.
Recommendation: If this class of risk is ever addressed, address it uniformly across all `ai.*` boolean keys in a dedicated future EP — not as a one-off fix scoped to `fallback_enabled` alone.

## 29. Required Corrective Actions

None of the findings above rise to CRITICAL or HIGH severity, and none represent a deviation between the approved design and the implementation (all 11 Owner Decisions were implemented exactly as specified — Section 26). Findings 001 and 004 are the most significant (both MEDIUM) and concern gaps in the *design's* own assumptions/completeness rather than implementation defects: the code faithfully implements what `EP069_DESIGN.md` specifies, but the design did not fully account for (a) the real provenance of `ProviderError` messages, or (b) `is_available()` failing unexpectedly. No corrective action is required before STEP 4 can proceed; however, Findings 001, 002, and 004 should be tracked (e.g., in `ARCHITECTURE_DEBT.md` or a future EP-069.x STEP 1) rather than silently dropped, since they identify real, if non-blocking, gaps.

## 30. Residual Risks

- A future provider (or a future revision of `ClaudeProvider`/`GeminiProvider`) could construct a `ProviderError` message containing request-derived content, which the fallback-chain's per-attempt log line would then log up to N times per request (Finding 001).
- A misbehaving `is_available()` implementation on any registered provider (not necessarily the one selected as `current`) can crash any request that reaches fallback evaluation (Finding 004).
- The `bootstrap.py` → `AIService` wiring for the new config key is protected only by manual inspection, not automated regression (Finding 002).
- The type-coercion risk for a quoted-string boolean value in `config.yaml` applies to the new key exactly as it already did to `ai.enabled` (Finding 007) — a pre-existing, unamplified risk.

## 31. Final Verdict

### PASS WITH WARNINGS

No CRITICAL or HIGH finding exists. Every Owner Decision, every acceptance criterion but one (which fails only as literally worded, due to a design-document overclaim rather than an implementation defect), every protected-file boundary, and every backward-compatibility property was independently verified with direct evidence — not inferred from the 68/68 test-pass count alone. Two MEDIUM findings (001, 004) identify real, non-blocking gaps in the design's own assumptions that should be tracked and addressed in a future revision or EP-069.x slice, but neither represents an implementation deviation from the approved design, an architectural boundary violation, a regression, or a scope-creep instance. EP-069.1 may proceed to STEP 4 with these warnings documented.

## 32. STEP 3 Completion Criteria

- [x] Re-read the entire audit document before finalizing.
- [x] Every finding verified against actual source (exact file/line evidence cited for each).
- [x] Every line reference independently re-confirmed against the current file contents at time of writing.
- [x] Every PASS claim in Sections 7/26/27 backed by cited evidence, not assertion alone.
- [x] Every finding backed by cited evidence; none based solely on speculation (Finding 001's risk is evidenced by the actual `_extract_error_message()` code path, not a hypothetical).
- [x] No production code changed during this audit (verified: Section 21's diff is identical to the diff already established at the end of STEP 2, with only this audit document itself and no other file added).
- [x] No test changed.
- [x] No configuration changed.
- [x] Only `docs/architecture/audits/EP069_ARCHITECTURE_AUDIT.md` was created.
- [x] Protected files independently re-verified untouched (Section 21).
- [x] The final verdict (PASS WITH WARNINGS) follows directly from the absence of CRITICAL/HIGH findings and the presence of non-blocking MEDIUM findings, per Section 34 of the governing instructions.
- [x] This audit performed independent evidence-gathering (fresh regression runs, fresh source reads, an independently-constructed real-registry ordering test trace, and an order-independence probe) rather than repeating STEP 2's self-reported summary.
