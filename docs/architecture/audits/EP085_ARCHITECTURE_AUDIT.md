# EP-085 — STEP 3: Independent Architecture Audit & Hardening

**Verdict: PASS WITH WARNINGS**

## 1. Audit Scope

Independent re-audit of EP-085 (Video Generation Provider Integration)
against `EP085_DESIGN.md`, established EP-082/083/084 patterns, and
Gemini's actual, current, publicly documented Veo API — performed
without assuming STEP 2's implementation, its 90/90 passing tests, or
its PASS verdict were correct. STEP 2's claims ("nothing invented",
"bounded polling", "safe fallback") were each independently re-derived
from source, not accepted as given.

## 2. Sources Inspected

Re-read in full: `EP085_DESIGN.md`; `src/core/ai/provider.py`;
`src/core/ai/provider_request_executor.py` (including `_run()`'s
complete body, traced line-by-line); `src/core/ai/providers/
gemini_provider.py` (`generate_video()`, `_start_video_operation()`,
`_poll_video_operation()`, `_parse_video_operation_response()`,
`_extract_video()`, and `_send_request()`/`_raise_for_transport_
status()` for their exact exception-mapping behavior); `src/core/ai/
provider_factory.py`; `src/core/ai/provider_manager.py` (`__init__`,
`list_fallback_candidates()` — read directly to confirm its exclude-
set semantics rather than trusting the design/STEP-2 description of
it); `src/services/video_generation_service.py`; the EP-085 wiring
block in `src/bootstrap.py`; `config/config.yaml`; `src/modules/
test_module.py`; and the complete `tests/EP085/
test_video_generation_provider_integration.py` suite. Compared
against `tests/EP083`/`tests/EP084`'s equivalent test architecture to
determine which apparent gaps are EP-085-specific versus established,
repository-wide testing-boundary choices.

## 3. STEP 1 Compliance Matrix

| Design requirement | Implementation | Status |
|---|---|---|
| `VideoGenerationRequest(prompt, aspect_ratio, duration_seconds, negative_prompt, seed)` | Present, exact fields, frozen dataclass | PASS |
| `GeneratedVideo(uri, mime_type)`, reference-only (D2) | Present; no `data_base64`/bytes field exists on the type at all (verified via `__dataclass_fields__` in a dedicated test) | PASS |
| `VideoGenerationResult(video, model, latency_ms)` | Present, matches `SpeechGenerationResult`'s shape exactly | PASS |
| `AIProvider.supports_video_generation()`/`generate_video()`, safe defaults | Present; `ClaudeProvider`/`ConfigDrivenProvider` unmodified and confirmed to inherit the safe defaults | PASS |
| `ProviderRequestExecutor.execute_video()`/`VideoProviderRequestOutcome` | Present; mechanical repetition of `execute_speech()`; `_run()` itself byte-unmodified (diffed against its EP-084 form) | PASS |
| `VideoGenerationService` mirrors `AudioGenerationService`'s control flow | Confirmed identical check ordering (`enabled` -> `get_current()` -> `is_enabled()` -> `supports_video_generation()` -> executor -> `result is None` guard) | PASS |
| `video_generation:` config namespace incl. `poll_interval_seconds`/`max_wait_seconds` | Present, defaults 10/600 per Owner Decision D3 | PASS |
| `providers.gemini.video_model` | Present, threaded through `provider_factory.py` with the established `or None` empty-string guard | PASS |
| Bootstrap wiring, no CLI/CommandRouter/RuntimeService integration | Confirmed: `_video_generation_service` constructed in `_build_command_router()`, never registered on `CommandRouter`, no `RuntimeService` reference | PASS |
| D1 — synchronous/blocking, no async job framework | Confirmed: `generate_video()` is one blocking call; no queue, thread pool, or callback mechanism introduced | PASS |
| `fallback_enabled` defaults `False`, more firmly than prior modalities | Confirmed in both `config.yaml` and `VideoGenerationService.__init__`'s default | PASS |
| No EP-069.4 modification | Confirmed: `src/core/capability/` untouched, not referenced by any EP-085 file | PASS |
| Predict/poll endpoint shapes match Section 6 | Confirmed against live Google documentation, re-verified this STEP (Section 5) | PASS |
| **Poll-failure resilience** | Design Section 12's error table maps every polling failure straight to the standard hierarchy with no resilience layer; STEP 2 implemented exactly that (no tolerance for transient poll blips) | **FINDING F1 (see Section 12/13)** — not a violation of the design, but a real robustness gap this audit closed |

No genuine contradiction between the design and the implementation was
found. The one finding (F1) is a hardening opportunity the design did
not explicitly forbid or require, not a deviation from an explicit
requirement.

## 4. Architecture Verification

Confirmed directly from source, not from STEP 2's description of it:

- `ProviderManager` gained zero new methods; `execute_video()` reaches
  it only through the unmodified `_run()`'s existing `list_fallback_
  candidates()` call.
- `ProviderRequestExecutor._run()` — read in full this STEP, line by
  line. Confirmed byte-identical in structure to its EP-084 form
  aside from the (already-audited, mechanical) addition of
  `execute_video()`'s own wrapper method.
- `GeminiProvider` is the sole owner of Veo-specific lifecycle
  behavior; no polling/operation logic leaked into the executor or
  service layer.
- No parallel provider-selection mechanism, no duplicate retry engine.
- No unnecessary abstraction: `VideoProviderRequestOutcome` and
  `execute_video()` each pull their own weight exactly as their
  EP-083/084 counterparts do.

## 5. Veo API Verification (independently re-derived, not re-trusted)

Re-confirmed against Google's current, official documentation and
independent, dated implementation reports, checked again fresh this
STEP rather than carried over from STEP 1/2's research notes:

- `POST .../v1beta/models/{model}:predictLongRunning` with
  `{"instances": [{"prompt": ...}], "parameters": {...}}` — confirmed
  correct; `aspectRatio`/`negativePrompt`/`seed`/`durationSeconds`
  confirmed as the real, documented parameter names (not invented).
- `GET .../v1beta/{operation_name}` (operation name used verbatim,
  never reconstructed) — confirmed correct, and the implementation
  test suite explicitly asserts the poll URL is built from the
  operation name as-is (`poll_url.endswith("operations/generate_123")`)
  and never contains `/models/`.
- `response.generateVideoResponse.generatedSamples[].video.uri` —
  confirmed correct.
- This implementation targets the Gemini Developer API
  (`generativelanguage.googleapis.com`), the same host every other
  provider capability in this codebase already uses — explicitly
  distinguished from Vertex AI's separate API surface, which was the
  source of the STEP 1 "UNVERIFIED" ambiguity that STEP 2 correctly
  resolved in favor of the Developer API's own official documentation.
- No undocumented behavior was found invented anywhere in the
  implementation.

## 6. Long-Running Operation Audit

Every transition in `initiate -> operation reference -> poll ->
completion/failure -> URI` was traced against the actual code:

- Successful initiation: `_start_video_operation()` returns the
  operation name from `data["name"]`.
- Missing/non-string/empty operation name: raises
  `ProviderUnavailableError` — confirmed by test.
- Malformed initiate JSON: raises `ProviderUnavailableError` (does not
  leak a raw `ValueError`/`binascii`-style exception, mirroring the
  exact class of defect EP-084's own STEP 3 found and fixed) —
  confirmed by test.
- Operation still running (`done` absent or not `True`): the strict
  `data.get("done") is True` check means a missing `done` field, or a
  non-boolean truthy value (e.g. a string `"true"`), is *not*
  mistaken for completion — it safely falls through to "keep polling"
  rather than crashing or misreporting success. This is a
  deliberately safe default, not an oversight; confirmed by direct
  code inspection (no test previously asserted this specific
  edge case, so this audit adds one — see Section 13).
- Operation completion with a successful `response`: extracted
  correctly via `_extract_video()`.
- Operation completion with an `error` field: raises
  `ProviderUnavailableError` including the provider's own message —
  confirmed by test, and confirmed safe to log (a provider-generated
  status string, not user prompt content or credentials).
- Completion without a generated video (empty `generatedSamples`):
  raises `ProviderUnavailableError` — confirmed by test.
- Multiple generated samples: `_extract_video()` returns the first
  sample with a non-empty `uri`, skipping any malformed entries —
  a reasonable, simple choice; the design's v1 contract has no
  "select N of many" requirement, so returning the first usable one
  is correct, not a shortfall.
- Unexpected sample structure (non-dict sample, missing `video` key,
  non-dict `video`): each is skipped via `isinstance` guards rather
  than raising — confirmed safe.
- **Empty URI: found to be already handled correctly in the STEP 2
  code (`if isinstance(uri, str) and uri:` rejects `""`), but STEP 2's
  own test suite never exercised this exact case (Section 18,
  Scenario E) — this audit adds
  `_test_gemini_generate_video_empty_uri_rejected` to close the
  coverage gap. No code change was needed; only test coverage was
  missing.**

## 7. Retry / Duplicate-Generation Audit (Section 6 of the audit brief — highest priority)

This was independently re-derived by reading `_run()`'s actual body,
not by trusting the design or STEP 2 report's description of it.

**Finding: duplicate generation on the same provider cannot happen.**
`_run()` maintains an `attempted: list[str]` of every provider name
tried so far (including the very first one), and calls
`self._provider_manager.list_fallback_candidates(exclude=attempted)`
on every fallback attempt. `ProviderManager.list_fallback_candidates()`
was read directly (`src/core/ai/provider_manager.py`, confirmed by its
own docstring and signature) and excludes every name in `exclude` from
its returned candidate list by construction. This means the specific
sequence the audit brief describes —
*"a polling request fails or times out... the executor potentially
starts another generation operation [on the same provider]"* — is
**structurally impossible**: `_run()` can never select `gemini` again
once `gemini` has already been attempted, regardless of how many
times fallback triggers. This is confirmed both by direct code
reading and by a dedicated regression test,
`_test_executor_video_default_config_never_retries_failed_generation`,
which asserts `primary.generate_video_calls` has length exactly 1
after a failure.

**What genuinely can happen, and is accepted, documented, current
behavior (not a defect):** if a second, independent video-capable
provider existed (none does today — Gemini is the only implementation
of `generate_video()` in this codebase) and `fallback_enabled=True`
were explicitly opted into, a mid-poll failure on Gemini could trigger
a fallback to that second provider, which would start its own,
genuinely independent video-generation operation, while Gemini's
original operation might still complete on Google's servers,
unretrieved. This is not "duplicate generation on one provider"; it
is "wasted generation across two different providers," a materially
different and much narrower risk, already identified by the design
(Section 13) and closed off in practice today by `fallback_enabled`
defaulting to `False` — confirmed enforced at the service boundary
(`VideoGenerationService.__init__`'s default) and unable to be
silently overridden by any lower layer (the executor takes
`fallback_enabled` as an explicit, required keyword argument with no
default of its own, so it cannot silently diverge from what the
service passes it).

**Finding F1 (MEDIUM, FIXED) — a different, previously-undiscovered
robustness gap.** While tracing every failure path through
`_poll_video_operation()`, this audit found that STEP 2's
implementation treated *any* single transient poll-request failure
(e.g. one dropped connection, one HTTP 500, one rate-limit response
among what could be dozens of polls over a multi-minute window) as
immediately fatal to the entire video generation — discarding a Veo
operation that may well have still been running successfully on
Google's infrastructure, with no way to resume or re-check it (per
D2, no operation identifier is ever returned to a caller). Given a
polling window that can span up to 600 seconds (60 polls at the
default 10-second interval), the probability of at least one
transient network hiccup is materially higher than for any prior
modality's single, fast HTTP call — making video generation
disproportionately fragile relative to text/image/speech generation
for reasons unrelated to Veo itself. This is squarely inside
`GeminiProvider`'s own scope (not the executor, not `_run()`, not a
second retry framework), does not touch fallback/service-layer
behavior, and is a "safe to fix without redesigning the architecture"
case per the Hardening Rule. **Fixed**: `_poll_video_operation()` now
treats a `ProviderNetworkError`/`ProviderRateLimitError`/
`ProviderTimeoutError`/`ProviderUnavailableError` on an individual
poll exactly like an ordinary "not done yet" response — logged,
checked against the same `max_wait_seconds` deadline, and retried
after the same `poll_interval_seconds`, reusing the existing
deadline/sleep mechanism unchanged. A persistent failure of this kind
still deterministically surfaces as `ProviderTimeoutError` once the
deadline elapses — it does not hang, and it does not silently
succeed. Non-transient failures (`ProviderAuthenticationError`,
`ProviderConfigurationError`, any other `ProviderError`) and malformed/
unparseable responses still propagate immediately, unchanged — this
fix does not weaken error surfacing for genuine, persistent problems.
Three regression tests were added and confirmed passing (Section 13).

## 8. Timeout / Polling Audit

- **Timeout cannot be bypassed**: confirmed — every code path through
  the poll loop either returns a completed operation or eventually
  reaches the deadline check.
- **Polling cannot continue forever**: confirmed by construction — the
  deadline is computed once (`time.monotonic() + video_max_wait_
  seconds`) before the loop starts and is checked every iteration.
- **Clock calculations are correct**: `time.monotonic()` is used
  throughout (never `time.time()`), which is documented to never
  regress, so "negative elapsed time" cannot occur in production.
- **Zero/negative `max_wait_seconds`/`poll_interval_seconds` are
  rejected**: confirmed by explicit `<= 0` checks raising
  `ProviderConfigurationError` before any HTTP call, and by dedicated
  tests covering `0`, `-1`, and other negative values for both
  settings.
- **This is "maximum wait", not "maximum poll count"**: confirmed —
  the deadline is time-based (`time.monotonic() >= deadline`), not a
  counted number of iterations. A slow-responding server issuing few,
  long-latency polls and a fast-responding server issuing many
  short-latency polls both correctly respect the same wall-clock
  ceiling.
- **Minor, accepted imprecision (INFORMATIONAL, no fix needed)**: the
  deadline is checked *before* sleeping, not after, so the true
  worst-case wall-clock overrun beyond the nominal `max_wait_seconds`
  is bounded by, at most, one `poll_interval_seconds` plus one poll
  HTTP call's duration (e.g. up to roughly 10-15 seconds beyond a
  600-second ceiling with default settings) — not unbounded, not a
  "timeout can be bypassed" condition, just a small, well-understood
  epsilon. Tightening this further (e.g. checking the deadline both
  before and after the sleep) was considered and rejected as
  unnecessary complexity for a marginal precision gain nothing in the
  design requires.
- **No busy loop**: confirmed — `time.sleep(self._video_poll_interval_
  seconds)` is unconditionally called between iterations whenever the
  operation is not yet done and the deadline has not passed.
- **Mocked clocks do not leak into production**: confirmed —
  `time.sleep`/`time.monotonic` are called via the `time` module
  attribute specifically so tests can patch them; production code
  calls the real `time` module with no test-only branching anywhere
  in `gemini_provider.py`.

## 9. HTTP / Network Failure Audit

Every HTTP interaction (initiate, poll) was traced. 4xx/5xx/timeout/
connection-error/malformed-JSON/unexpected-shape cases all map into
the existing `ProviderError` hierarchy via the same, unmodified
`_send_request()`/`_raise_for_transport_status()` helpers every other
capability already uses, with two EP-085-specific additions: the 404
handler on `_start_video_operation()` (mirrors `_parse_image_
response()`'s/`_parse_speech_response()`'s own 404 precedent, naming
`video_model` specifically) and F1's poll-level transient-failure
tolerance (Section 7). No raw third-party (`requests`, `json`)
exception was found able to escape past the provider layer in any
code path this audit traced — confirmed both by inspection and by the
`_test_gemini_generate_video_malformed_initiate_response`/
`_malformed_poll_response` tests, which explicitly assert that any
exception other than `ProviderUnavailableError` is a test failure.

## 10. Error Hierarchy Audit

No new error type was introduced by EP-085 at any point (confirmed by
grep across every changed file). Every exception path uses an
existing `ProviderError` subtype, applied consistently with EP-082/
083/084's own conventions (config errors before any I/O; transport
errors from the shared HTTP helpers; parsing/shape errors as
`ProviderUnavailableError`, mirroring `_extract_images()`/`_extract_
audio()`'s "return None on anything unexpected, let the caller raise"
idiom). No broad `except Exception` exists anywhere in the EP-085
code added or modified this STEP or in STEP 2 — every `except` clause
names specific, expected exception types (`ProviderError` subtypes,
`ValueError`, or nothing at all where no fallback tolerance is
intended).

## 11. Configuration Audit

- `video_generation.poll_interval_seconds`/`max_wait_seconds`:
  positivity validated at the point of use (`generate_video()`);
  non-numeric config values are coerced with a safe fallback in
  `provider_factory.py` (`isinstance` guard, defaulting to 10/600).
- `providers.gemini.video_model`: empty string correctly normalized
  to `None` in `GeminiProvider.__init__` (`video_model or None`),
  confirmed by test.
- **Very large values**: no upper bound is enforced on either setting.
  Reasoned through (not merely asserted): an extremely large
  `poll_interval_seconds` exceeding `max_wait_seconds` does not cause
  an infinite loop or crash — the implementation still performs at
  least one poll, checks the deadline, and terminates in bounded time
  (worst case, roughly one interval's worth of extra wait beyond the
  deadline, consistent with Section 8's documented imprecision). No
  fix needed; recorded as INFORMATIONAL.
- **Cross-namespace access** (`provider_factory.py` reading
  `video_generation.*` while constructing a `providers.gemini.*`-scoped
  object): confirmed intentional and explicitly approved by
  `EP085_DESIGN.md` Section 15 — not changed, per the audit brief's
  own instruction not to alter explicitly-approved unusual patterns.

## 12. Test-Quality Audit

STEP 2's 90 tests were read in full, not merely counted, against the
specific failure modes this audit brief lists in Section 17-18. Most
were already covered (contract construction, executor fallback/
non-eligible/exhaustion, service-layer checks, the full Gemini/Veo
success and failure lifecycle, deterministic timeout, D1/D2
confirmation). Three genuine gaps were found and closed this STEP:

1. **No test exercised a transient poll failure at all** (the F1 gap
   itself) — closed with three new tests (Section 13).
2. **No test asserted an empty `uri` is rejected** (Scenario E) —
   closed (Section 6).
3. **The "entire chain" through a real `ProviderManager`/
   `GeminiProvider` together was not tested end-to-end** — investigated
   and found to be consistent with, not a gap unique to, EP-085:
   `tests/EP083`/`tests/EP084` also test each layer independently via
   a purpose-built fake (`_FakeProviderManager`) that was verified
   this STEP to genuinely implement the same interface contract
   (`get_current`/`is_enabled`/`list_fallback_candidates(exclude=...)`)
   the real `ProviderManager` exposes (confirmed by reading `provider_
   manager.py`'s actual signature). This is an established,
   repository-wide testing-boundary choice, not an EP-085-specific
   weakness, and this audit does not introduce a new, inconsistent
   testing pattern solely for this EP.

No over-mocking, no assertion found to be too weak to catch a real
regression, no duplicate tests, and no test found that could pass
despite genuinely broken production behavior.

## 13. Findings Table

| ID | Severity | Description | Status |
|---|---|---|---|
| F1 | MEDIUM | A single transient poll-request failure discarded an entire in-progress video generation with no resilience, disproportionately fragile given a multi-minute, many-poll window. | **Fixed** in `_poll_video_operation()`; 3 regression tests added (`_test_gemini_generate_video_poll_transient_failure_then_success`, `..._persistent_transient_failure_times_out`, `..._auth_failure_propagates_immediately`) |
| F2 | LOW | Missing test coverage for an empty (but present) `video.uri` — code already handled it correctly, only the test was missing. | **Fixed** (test added: `_test_gemini_generate_video_empty_uri_rejected`) |
| F3 | INFORMATIONAL | Timeout has a small, bounded overrun (up to ~1 poll interval + 1 HTTP call) beyond the nominal `max_wait_seconds`, since the deadline is checked before sleeping, not after. | No fix — not a "timeout can be bypassed" condition, and tightening it further is unjustified complexity. |
| F4 | INFORMATIONAL | No upper bound on `poll_interval_seconds`/`max_wait_seconds`; reasoned through and confirmed safe (bounded termination either way). | No fix needed. |
| F5 | INFORMATIONAL | Pre-existing, unrelated: `tests.EP083...` still not registered in `test_module.py` (documented at EP-084 STEP 2/3 already); `src/core/ai/text_generation_service.py` remains a dead duplicate (found at EP-085 STEP 1). Neither touched this STEP. | Not in scope. |

No CRITICAL or HIGH finding was identified. Duplicate generation on
the same provider — the audit brief's highest-priority concern — was
independently confirmed structurally impossible via `_run()`'s own
exclude-based candidate selection, not merely asserted safe.

## 14. Remediations Performed

1. `src/core/ai/providers/gemini_provider.py` — `_poll_video_
   operation()` now tolerates a single transient poll failure exactly
   like a "not done yet" response, reusing the existing deadline/sleep
   mechanism (F1).
2. `tests/EP085/test_video_generation_provider_integration.py` —
   added `_test_gemini_generate_video_poll_transient_failure_then_
   success`, `_test_gemini_generate_video_poll_persistent_transient_
   failure_times_out`, `_test_gemini_generate_video_poll_auth_
   failure_propagates_immediately` (F1), and `_test_gemini_generate_
   video_empty_uri_rejected` (F2). Test count: 90 -> 97.

No other file was modified during STEP 3. `EP085_DESIGN.md` was not
altered — no finding required a design-level correction.

## 15. Remaining Informational / Deferred Items

F3, F4, F5 (Section 13) — none block PASS; none require code changes.

## 16. Regression Results

Run directly in this audit session, both before and after the F1/F2
remediation, and re-run a final time after all fixes:

```
tests/EP085   : 97 passed / 0 failed / 0 skipped   (was 90 before this STEP)
tests/EP084   : 77 passed / 0 failed / 0 skipped
tests/EP083   : 60 passed / 0 failed / 0 skipped
tests/EP082   : 69 passed / 0 failed / 0 skipped
tests/EP069   : 68 passed / 0 failed / 0 skipped
tests/EP069_3 : 80 passed / 0 failed / 0 skipped
tests/EP069_4 : 41 passed / 0 failed / 0 skipped
TOTAL         : 492 passed / 0 failed
```

`tests/EP085` re-run 10 times total across this session (5 before the
fix existed for the new tests, 5 after) — stable at 97/97 every time
after the fix, confirming the new tests are deterministic (no real
network access, no real wall-clock waiting; `time.sleep`/`time.
monotonic` fully mocked in every timing-sensitive test).

## 17. Final Verdict

```
PASS WITH WARNINGS
```

The audit brief's highest-priority concern (retry-induced duplicate
generation) was independently investigated and confirmed
structurally impossible, not merely asserted safe by STEP 2. One
genuine MEDIUM-severity robustness gap (F1) was found through
adversarial reasoning about polling over a multi-minute window — a
failure mode STEP 2's own passing tests had not exercised — and is
now fixed and regression-tested. One LOW test-coverage gap (F2) was
closed. The remaining items (F3-F5) are informational or pre-existing
and unrelated, warranting no further action.
