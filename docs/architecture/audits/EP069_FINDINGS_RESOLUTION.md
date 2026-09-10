# EP-069.1 Findings Resolution — Automatic AI Provider Fallback on Request Failure

STEP 3.1: Findings Resolution Review

## 1. Title

EP-069.1 Findings Resolution Review

## 2. Purpose

`docs/architecture/audits/EP069_ARCHITECTURE_AUDIT.md` (STEP 3) reported seven findings (EP069.1-AUDIT-001 through -007) and a verdict of PASS WITH WARNINGS. This document independently re-verifies each finding directly against current source code and tests — not by re-reading the audit's own conclusions and accepting them — classifies each with a concrete resolution, and issues a final STEP 4 readiness decision. Per the governing instructions, this is a decision review only: no production code, test, configuration, or prior document (`EP069_DESIGN.md`, `EP069_ARCHITECTURE_AUDIT.md`) was modified while producing it.

## 3. Review Methodology

For every finding: (a) re-read the exact cited source location fresh, independent of the audit's prose description; (b) where the audit's claim was about exception-message content, trace the concrete construction site rather than relying on the audit's characterization; (c) determine whether the finding is factually accurate, overstated, understated, or invalid; (d) classify using the six-value scheme in Section 6 of the governing instructions; (e) decide blocking/non-blocking for STEP 4. Source-of-truth order followed: actual code and tests first, then established EP conventions, then `EP069_DESIGN.md`, then the STEP 3 audit itself, then roadmap/backlog — the audit is treated as a hypothesis to verify, not a conclusion to inherit.

## 4. Findings Review Table

| Finding | Severity | Verified? | Classification | STEP 4 Blocking? | Resolution |
|---|---|---|---|---|---|
| EP069.1-AUDIT-001 | MEDIUM | Partially — narrower than originally stated (Section 5) | DOCUMENT RESIDUAL RISK | No | Document the forward-looking contract gap; no code change now |
| EP069.1-AUDIT-002 | MEDIUM | Yes, factually correct, but precedent weaker than audit implied (Section 7.1) | TEST IMPROVEMENT — CAN DEFER | No | Add a Bootstrap-level test in a future revision or EP-069.x |
| EP069.1-AUDIT-003 | LOW | Yes | TEST IMPROVEMENT — CAN DEFER | No | Optional explicit iteration-ceiling test, future work |
| EP069.1-AUDIT-004 | MEDIUM | Yes, but real-world exploitability is currently zero (Section 6) | DOCUMENT RESIDUAL RISK | No | Document the assumption explicitly; no defensive code now |
| EP069.1-AUDIT-005 | LOW | Yes | TEST IMPROVEMENT — CAN DEFER | No | Optional standalone test, future work |
| EP069.1-AUDIT-006 | LOW | Yes | ACCEPTED TRADE-OFF | No | None — already a deliberate, documented Owner Decision (D8) |
| EP069.1-AUDIT-007 | LOW | Yes, but pre-existing repo-wide pattern, not EP-069.1-specific | ACCEPTED TRADE-OFF | No | None — inherited convention; not EP-069.1's to fix in isolation |

**Zero findings classified FIX BEFORE STEP 4. Zero findings classified DESIGN UPDATE REQUIRED (as a blocking category) or NOT A VALID FINDING** (all seven are real observations at some level of accuracy; none are spurious).

## 5. Detailed Analysis of AUDIT-001

**Traced path:** Provider API response → `_handle_response()`/`_parse_response()` → a specific `ProviderError` subclass constructed with a specific message → raised → caught by `AIService.ask()`'s `except ProviderError as exc:` → (a) always logged once via `logger.error(f"AI request failed (provider='{candidate_name}'): {exc}")`, then (b) either returned immediately (non-eligible or fallback disabled) or fed into the fallback loop (eligible + enabled).

**Independently re-inspected every exception-construction site in both `ClaudeProvider` and `GeminiProvider`** (not just the one the STEP 3 audit cited):

| Exception raised | Construction (Claude) | Construction (Gemini) | Message source | Fallback-eligible? |
|---|---|---|---|---|
| `ProviderConfigurationError` | Static string (`"Provider 'claude' is disabled."` / `"...missing 'api_key'."`) | Same pattern | Code-authored, static | No |
| `ProviderAuthenticationError` (401/403) | Static string | Static string | Code-authored, static | No |
| `ProviderRateLimitError` (429) | Static string | Static string | Code-authored, static | **Yes** |
| `ProviderTimeoutError` | `f"...timed out after {self._timeout}s."` | Same pattern | Code-authored + an `int` from config, not user/API-controlled | **Yes** |
| `ProviderNetworkError` (from `ConnectionError`) | Static string (`"Could not reach the Anthropic API."`) | Static string (`"...Google Gemini API."`) | Code-authored, static | **Yes** |
| `ProviderNetworkError` (from generic `RequestException`) | `str(exc)` | `str(exc)` | `requests`/`urllib3` transport-error text (e.g. `MissingSchema`, `InvalidURL`, `SSLError`) — see below | **Yes** |
| `ProviderUnavailableError` (5xx, or invalid JSON body) | Static string(s) | Static string(s) | Code-authored, static | **Yes** |
| `ProviderError` (bare — any other non-2xx status) | `f"...(HTTP {status}): {message}"` where `message = self._extract_error_message(response)` | Same pattern | **API response body/text** — server-controlled | **No** |

**The one construction site that pulls content from the API response body (`_extract_error_message()`, which its own docstring says returns "the API's own error message, or the raw response text") is the bare/generic `ProviderError` branch — and this branch is the single exception type explicitly excluded from `_FALLBACK_ELIGIBLE_ERRORS`.** Because a non-eligible failure causes `ask()` to `return` immediately after the single per-attempt log line (line 570 of `ai_service.py`), this exact branch logs at most once per request — identical in frequency to pre-EP-069.1 behavior. EP-069.1 does not amplify this specific risk at all.

**For the remaining construction site that could theoretically repeat** — `ProviderNetworkError(str(exc))` on a generic `requests.exceptions.RequestException` — independently confirmed both providers send the request via `requests.post(_API_URL, headers=..., json=payload, timeout=...)`, where `_API_URL`/the Gemini endpoint URL are fixed, code-controlled module constants (no user input embedded), the API key is sent via an HTTP header (`x-api-key` / `x-goog-api-key`, never the URL), and the prompt is sent via the JSON body (never the URL). The `requests` library's transport-level exceptions in this residual category (`TooManyRedirects`, `ChunkedEncodingError`, `InvalidURL`, `MissingSchema`, `SSLError`, etc.) stringify to messages describing the URL/connection/encoding problem itself — they do not include header values or JSON body content. **Concretely: `str(exc)` here cannot contain the API key, the prompt, or the response text, for either provider as currently implemented.**

**Concrete conclusion: C — Real risk, but safely deferrable with explicit residual-risk documentation.**

Not **A** ("safe as implemented," full stop): while nothing currently in the codebase is unsafe, `AIProvider`'s abstract contract (`provider.py`) places no documented constraint on what a concrete implementation's exception messages may contain for the four fallback-eligible exception types — a future provider (third-party or in-house) could construct, say, `ProviderRateLimitError(response.text)` for a rate-limit response that happens to echo request metadata, and nothing today would catch or prevent that at review time beyond code review discipline. This is a real, if currently dormant, contract gap.

Not **B** (a live defect requiring correction before STEP 4): the STEP 3 audit's framing — "this line now fires up to N times, amplifying exposure" — is factually incorrect once each exception type's actual message-construction is traced individually rather than treated as a class. The only unsafe-content branch (`_extract_error_message()`) is mutually exclusive with the multiple-firing branches by construction of the eligibility table itself (Owner Decision D4). There is no live, exploitable defect in the current implementation. Requiring a code change before STEP 4 would be fixing a risk that does not currently exist, based on an overstated restatement of the original finding.

This also means the original STEP 3 audit (Section 18, Section 28 Finding 001) overstated the severity by treating "the log line exists and reuses `str(exc)`" as sufficient evidence of amplified risk, without separately verifying whether the specific exception types that can actually loop ever carry unsafe content. STEP 3.1's independent re-trace narrows, but does not eliminate, the finding.

## 6. Detailed Analysis of AUDIT-004

**Inspected every concrete/existing implementation of `is_available()`:**

- `ClaudeProvider.is_available()`: `return self._enabled and bool(self._api_key.strip())` — pure boolean expression over two instance attributes (a `bool` and a `str` set in `__init__`), no I/O, no external call.
- `GeminiProvider.is_available()`: identical pattern.
- `ConfigDrivenProvider.is_available()` (`provider_factory.py`): `return self._enabled and self._configured` — pure boolean expression over two `bool` attributes.
- `AIProvider.is_available()` (abstract, `provider.py`): `raise NotImplementedError` — the abstract stub itself, never called directly (every concrete subclass overrides it).

**None of the three concrete implementations can raise under any realistic runtime condition.** The only theoretical path to an exception would be a broken constructor invariant (e.g., `self._api_key` somehow being `None` instead of `str`, causing `.strip()` to raise `AttributeError`) — this would be a distinct, pre-existing class of defect (a constructor bug), not a runtime failure mode `is_available()` itself introduces, and nothing in `EP069_DESIGN.md` or EP-069.1's implementation touches provider construction.

This matches the implicit design philosophy already stated elsewhere in `provider.py` for the sibling `health()` method: "This is a configuration-derived readiness check only... no provider performs a network request to verify connectivity" — the clear intent, carried from EP-014, is that these query methods are cheap, synchronous, side-effect-free, and by strong implication, exception-free. `is_available()`'s own docstring ("Return whether this provider is enabled and fully configured") is consistent with this: a well-formed implementation is a pure predicate.

**Should `ProviderManager` add defensive exception handling around `is_available()` calls?** No, not now, and doing so would arguably be an architectural regression, not an improvement. This project's own STEP 2 governing instructions explicitly warned against introducing broad exception handling "merely for resilience" outside an appropriately scoped boundary, and cited EP-066's broad-exception-containment precedent as applying specifically to an isolated background-loop boundary — not as a general pattern to apply throughout the synchronous request path. `list_fallback_candidates()` is called synchronously, inline, as part of handling a request already inside an exception-handling context (a `ProviderError` is already being processed) — wrapping every candidate's `is_available()` call in its own `try/except Exception` here would be speculative defensive programming against a failure mode no current implementation exhibits, is not required by any Owner Decision or acceptance criterion in `EP069_DESIGN.md`, and would itself constitute unrequested scope expansion beyond EP-069.1's approved boundary.

**Decision: this is a real, but currently zero-exploitability, architectural gap.** It should be documented as a residual risk and the assumption made explicit (either in a future design revision's prose, or as an added sentence to `AIProvider.is_available()`'s docstring in a future EP) rather than corrected with new exception-handling code now. If a future provider implementation ever needs `is_available()` to perform I/O (e.g., a live health-check-backed provider), that would be the appropriate trigger to revisit this decision — not a hypothetical concern about providers that do not exist today.

## 7. Analysis of Remaining Findings

### 7.1 EP069.1-AUDIT-002 (no Bootstrap-level integration test for `ai.fallback_enabled`)

Independently re-verified: `tests/EP069/test_ai_provider_fallback.py` indeed never exercises `src/bootstrap.py`'s `config.get("ai.fallback_enabled", False)` read site — every test constructs `AIService` directly, passing `fallback_enabled` as an explicit constructor argument. This part of the STEP 3 audit's factual claim is correct.

However, independently checking whether this is actually an "established convention" this EP deviated from (as the audit implied by citing `tests/EP058/`): a `grep` for `EP-066`/`EP-067`/`EP-068` config-key comments in `config/config.yaml` shows **none of the three most recent reliability EPs introduced a new configuration key at all**, so none of them provide a directly comparable precedent either way. `tests/EP058/test_autonomous_planning.py`'s full-`Bootstrap` test is a real precedent, but it is an older, more elaborate EP's practice, not a convention every subsequent config-adding EP has consistently followed — this is a "would be good practice to match" observation, not a documented, binding project rule EP-069.1 broke.

The actual wiring at risk (`fallback_enabled=bool(config.get("ai.fallback_enabled", False))` in `bootstrap.py`) is a single line, directly adjacent to and pattern-identical with the already-working `ai.enabled`/`ai.default_provider` lines, and was independently confirmed correct by direct reading (STEP 3 audit Section 14; re-confirmed here by re-reading `bootstrap.py` again). The risk this finding protects against — a future refactor silently breaking the wiring — is real but low-likelihood and would very likely be caught by the very next manual `ai doctor`/`ai use` smoke check, not silently shipped.

**Resolution: TEST IMPROVEMENT — CAN DEFER.** Worth doing, not worth blocking STEP 4 over.

### 7.2 EP069.1-AUDIT-003 (bounded-loop tested via hang-detection, not an explicit ceiling)

Re-confirmed: `_test_all_eligible_providers_fail_bounded_and_reported` asserts each fake's call count individually and their sum, which would catch a "duplicate attempt" or "skipped candidate" bug, but a genuine infinite loop would manifest as a hung test process rather than a fast, clean assertion failure. This is accurately characterized by the STEP 3 audit. The underlying code is independently re-confirmed bounded by construction (Section 10 of the STEP 3 audit; re-traced here — each loop iteration strictly grows `attempted` by exactly one name, and `list_fallback_candidates` excludes every name in it, over a fixed, currently-5-member provider set). This is a test-robustness gap, not a live defect.

**Resolution: TEST IMPROVEMENT — CAN DEFER.**

### 7.3 EP069.1-AUDIT-005 (no standalone zero-fallback-candidates test)

Re-confirmed: the exhausted-candidates branch (`if not remaining:`) is exercised only as the second occurrence within a three-provider chain, never in isolation with exactly one registered provider. The code path is identical either way (confirmed by re-reading `ai_service.py` — there is no special-casing for "zero candidates from the start" versus "zero candidates after N attempts"), so this is a coverage completeness gap, not a behavioral uncertainty.

**Resolution: TEST IMPROVEMENT — CAN DEFER.**

### 7.4 EP069.1-AUDIT-006 (`AskResult` doesn't expose whether fallback occurred)

Re-confirmed against `EP069_DESIGN.md` Section 18/Owner Decision D8: this is not an oversight — the design explicitly decided against adding a new `AskResult` field, reasoning that the richer diagnostic detail belongs in logs, not a new public-API field, to avoid growing `AskResult`'s surface for a single internal consumer's benefit. The implementation matches this decision exactly (confirmed: no new field exists on `AskResult`). Re-affirmed as correct and intentional, not a gap needing resolution.

**Resolution: ACCEPTED TRADE-OFF.** No action.

### 7.5 EP069.1-AUDIT-007 (YAML boolean quoting footgun)

Re-confirmed: `bool(config.get("ai.fallback_enabled", False))` shares the exact type-coercion behavior as the adjacent, pre-existing `bool(config.get("ai.enabled", False))` line — a quoted `"false"` string would evaluate truthy in both cases. This is not something EP-069.1 introduced; it is inherited, unmodified, pre-existing project convention applied consistently to the new key. Fixing it here, scoped only to `fallback_enabled`, would create an inconsistency (one `ai.*` boolean key handled more defensively than its neighbors) rather than a genuine improvement, and would constitute unrelated-code modification beyond EP-069.1's approved boundary.

**Resolution: ACCEPTED TRADE-OFF.** No action within EP-069.1; if ever addressed, address uniformly across all `ai.*` boolean keys in a dedicated future change, as the STEP 3 audit itself already recommended.

## 8. Resolution Decision for Each Finding

- **EP069.1-AUDIT-001 — DOCUMENT RESIDUAL RISK.** Current implementation is safe; the gap is in `AIProvider`'s contract not yet formally guaranteeing that fallback-eligible exception messages are always free of API-response-body content. Track for a future design revision or Owner Decision; no code change now.
- **EP069.1-AUDIT-002 — TEST IMPROVEMENT — CAN DEFER.** Add a `Bootstrap`-level integration test for `ai.fallback_enabled` in a future pass; not required before STEP 4.
- **EP069.1-AUDIT-003 — TEST IMPROVEMENT — CAN DEFER.** Consider an explicit iteration-ceiling assertion in a future pass.
- **EP069.1-AUDIT-004 — DOCUMENT RESIDUAL RISK.** No current implementation can trigger this; document the assumption that `is_available()` must remain side-effect-free and exception-free, rather than adding defensive exception handling now.
- **EP069.1-AUDIT-005 — TEST IMPROVEMENT — CAN DEFER.** Add a standalone single-provider exhaustion test in a future pass.
- **EP069.1-AUDIT-006 — ACCEPTED TRADE-OFF.** Already a deliberate, documented Owner Decision (D8); no action.
- **EP069.1-AUDIT-007 — ACCEPTED TRADE-OFF.** Pre-existing, project-wide convention; not EP-069.1's to fix in isolation.

No finding requires a design document change to `EP069_DESIGN.md`'s substance (no Owner Decision needs to be reversed or altered), and no finding requires new tests, code changes, or an Owner Decision change *before* STEP 4 specifically.

## 9. Required Actions Before STEP 4

**None.** No finding meets the bar for FIX BEFORE STEP 4 or a blocking DESIGN UPDATE REQUIRED. All seven findings are either accepted trade-offs consistent with the approved design, or non-blocking test/documentation improvements whose absence does not represent a live defect, a regression, an Owner Decision violation, an acceptance-criterion violation, or a security/privacy/reliability risk in the current, shipped implementation.

## 10. Deferred Actions / Future Considerations

- Add a `Bootstrap`-level integration test for `ai.fallback_enabled`, mirroring `tests/EP058/test_autonomous_planning.py`'s pattern (from EP069.1-AUDIT-002).
- Consider an explicit, hang-independent iteration-ceiling assertion for the fallback loop's bounded-execution test (from EP069.1-AUDIT-003).
- Add a standalone test for the zero-fallback-candidates-exist case (from EP069.1-AUDIT-005).
- In a future EP-069.x or design revision, either (a) add an explicit note to `AIProvider`'s docstring/contract that implementations must not construct exception messages for fallback-eligible exception types from unsanitized, request-derived, or API-response-body content, or (b) narrow the per-attempt fallback log line to log `type(exc).__name__` only, matching the discipline already used for the newer aggregated "all providers failed" log line (from EP069.1-AUDIT-001).
- In a future EP-069.x or design revision, document explicitly (in `AIProvider.is_available()`'s docstring) that implementations must remain side-effect-free and must not raise — codifying the assumption `list_fallback_candidates()` currently relies on implicitly (from EP069.1-AUDIT-004).
- If the YAML boolean-quoting footgun (EP069.1-AUDIT-007) is ever addressed, address it uniformly across every `ai.*` boolean configuration key in one dedicated change, not scoped to `fallback_enabled` alone.

None of the above are scheduled or scoped as part of EP-069.1; they are candidates for future, separately-proposed work.

## 11. Residual Risks

- A future `AIProvider` implementation could construct a fallback-eligible exception's message from unsanitized, server-controlled content, which the reused per-attempt log line would then log verbatim, potentially multiple times per request. Not exploitable by any code in the repository today (Section 5).
- A future `AIProvider` implementation (or a bug introduced into an existing one) whose `is_available()` performs I/O or otherwise raises would crash any request that reaches fallback evaluation, for as long as that provider remains registered — regardless of whether it was ever selected as the active provider. Not exploitable by any code in the repository today (Section 6).
- The `bootstrap.py` → `AIService` wiring for `ai.fallback_enabled` is protected only by direct code inspection, not automated regression, until a future integration test is added.
- The YAML boolean-quoting type-coercion risk applies identically to `ai.fallback_enabled` as it already does to `ai.enabled` — an inherited, unamplified, project-wide characteristic.

## 12. Final STEP 4 Readiness Decision

### READY FOR STEP 4

All seven STEP 3 findings have been independently re-verified against actual source code rather than accepted at face value. Two findings (EP069.1-AUDIT-001, -004) were found to be real but substantially narrower in actual, current exploitability than the STEP 3 audit's framing suggested — both are architecture-contract gaps relevant to hypothetical future providers, not live defects in the two providers that exist today, and both are appropriately handled by documentation of the residual risk rather than a code change scoped to EP-069.1. Three findings (EP069.1-AUDIT-002, -003, -005) are genuine, non-blocking test-coverage improvements that would strengthen confidence but whose absence does not indicate incorrect behavior in the current implementation — the underlying code paths were independently re-confirmed correct by direct inspection, not only inferred from the existing test suite. Two findings (EP069.1-AUDIT-006, -007) are confirmed-correct, deliberate, already-documented trade-offs requiring no further action. No finding violates an EP-069.1 Owner Decision, an acceptance criterion in the currently-approved sense, an established architectural convention in a way that constitutes a real regression, or creates a live security/privacy/reliability risk in the shipped code. All remaining warnings are acceptable to carry forward as documented residual risk and deferred test-improvement work.
