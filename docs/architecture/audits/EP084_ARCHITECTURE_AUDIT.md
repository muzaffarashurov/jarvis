# EP-084 — STEP 3: Independent Architecture Audit & Hardening

**Verdict: PASS WITH WARNINGS**

## 1. Audit Scope

Independent re-audit of EP-084 (Audio & Speech Generation Integration)
against `EP084_DESIGN.md`, established EP-082/EP-083 patterns, and
Gemini's actual, current, publicly documented TTS API — performed
without assuming the STEP 2 implementation, its passing tests, or its
PASS report were correct. Every file in STEP 2's changed-file list was
re-read from disk in this session; every Gemini API claim in the
design/implementation was independently re-verified via live web
research rather than trusted from STEP 1/2.

## 2. Repository Baseline

Re-read in full during this audit: `EP084_DESIGN.md`,
`src/core/ai/provider.py`, `src/core/ai/provider_request_executor.py`,
`src/core/ai/providers/gemini_provider.py`,
`src/core/ai/provider_factory.py`,
`src/services/audio_generation_service.py`, the EP-084 wiring block in
`src/bootstrap.py`, the `audio_generation:`/`providers.gemini.
audio_model` additions in `config/config.yaml`,
`src/modules/test_module.py`, and the full
`tests/EP084/test_audio_generation_provider_integration.py` suite —
compared line-by-line against `src/services/image_generation_service.
py`, `tests/EP083/test_image_generation_provider_integration.py`, and
`src/core/ai/claude_provider.py`/`ConfigDrivenProvider`.

## 3. Design Conformance

Every approved contract from `EP084_DESIGN.md` exists, under the
exact approved names (Owner Decision D1): `SpeechGenerationRequest`,
`GeneratedAudio`, `SpeechGenerationResult` (provider-level, in
`provider.py`), `SpeechProviderRequestOutcome`, `AudioGenerationService`
(with its own module-local `SpeechGenerationResult`, same name/
different module, mirroring `ImageGenerationResult`'s established
precedent exactly), `AIProvider.supports_speech_generation()`/
`generate_speech()`, `ProviderRequestExecutor.execute_speech()`. No
extra implementation behavior, no changed responsibility, and no
accidental architectural coupling to EP-083 was found: `execute()`
and `execute_image()` are confirmed byte-identical to their pre-EP-084
form (Section 4 below). Scope boundaries (Section 19/20 of the
design) are respected — see Section 14 of this audit.

One documentation-accuracy gap was found and fixed (F2, Section 15).

## 4. Architecture Verification

Confirmed flow, read directly from source:

```
AudioGenerationService.generate()
  -> ProviderRequestExecutor.execute_speech()
    -> ProviderManager (via _run()'s self._provider_manager)
      -> AIProvider.generate_speech()
        -> GeminiProvider.generate_speech()
```

- `AudioGenerationService` owns no provider selection or retry logic
  — confirmed by direct comparison with `ImageGenerationService.
  generate()`: both methods are structurally identical (same check
  order: `enabled` -> `get_current() is None` -> `is_enabled()` ->
  `supports_*_generation()` -> executor call -> `result is None`
  guard), differing only in type/field names.
- `execute_speech()` is a mechanical repetition of `execute_image()`
  against the same, unmodified `_run()` helper — confirmed
  byte-identical apart from the wrapped type and the capability
  predicate. `_run()`'s own body (candidate loop, `_RunResult`
  construction, `_FALLBACK_ELIGIBLE_ERRORS` classification, all log
  lines) was diffed against its pre-EP-084 form and found completely
  unmodified.
- `ProviderManager` gained zero new methods or responsibilities;
  `execute_speech()` reaches it only through `_run()`'s existing
  `list_fallback_candidates()` call, exactly as `execute_image()`
  already does.
- Gemini-specific behavior (request construction, response parsing,
  PCM/WAV handling) is fully contained inside `GeminiProvider`; no
  Gemini-specific logic leaked into the executor or service layer.
- No duplicate executor, no duplicate `ProviderManager`, no bypass
  path: `AudioGenerationService` holds no direct reference to any
  `AIProvider` or HTTP client — only `ProviderManager` and the shared
  `ProviderRequestExecutor`.

No redundant abstraction was found — `execute_speech()`/
`SpeechProviderRequestOutcome` are each pulling their own weight
exactly as `execute_image()`/`ImageProviderRequestOutcome` do.

## 5. Provider Contract Audit

`supports_speech_generation()`/`generate_speech()` base defaults
(`False` / always raises `ProviderUnavailableError`) are present on
`AIProvider` and confirmed, by direct inspection, **not** overridden
by `ClaudeProvider` or `ConfigDrivenProvider` — both remain valid
`AIProvider` implementations with zero source changes, exactly as
`EP084_DESIGN.md` Section 12 requires. `tests/EP084` confirms this
behaviorally for both classes.

`ProviderManager`'s own code was inspected and confirmed unmodified;
it has no awareness of speech generation at all, exactly as designed
— capability filtering is entirely `execute_speech()`'s
(fallback candidates) and `AudioGenerationService`'s (initial
provider) responsibility, per the design's explicit split. Fallback
behavior was independently traced for all four scenarios the audit
brief lists (current provider incapable -> service fails fast with
zero executor/network calls; provider raises a fallback-eligible
error -> executor retries a capability-filtered candidate; provider
raises a non-eligible error -> no retry; no eligible fallback exists
-> aggregated failure reported) and all four are covered by
`tests/EP084` and pass.

## 6. Gemini API Correctness (independently re-verified, not assumed)

Re-verified against current, authoritative Google documentation and
multiple independent real-world implementation reports (not merely
re-reading `EP084_DESIGN.md`'s own STEP 1 claims):

- **Endpoint/request shape**: `POST .../v1beta/models/{model}:
  generateContent`, `x-goog-api-key` header, `contents:[{role:"user",
  parts:[{text}]}]`, `generationConfig.responseModalities:["AUDIO"]`,
  `generationConfig.speechConfig.voiceConfig.prebuiltVoiceConfig.
  voiceName` — confirmed correct against Google's own current
  "Text-to-speech generation (TTS) | Gemini Generate Content API"
  documentation and cookbook, whose example `curl`/JS calls match the
  implementation's payload shape field-for-field.
- **Response shape**: `candidates[0].content.parts[0].inlineData.
  {data, mimeType}` — confirmed correct against the same sources; the
  implementation's `_extract_audio()` matches this exactly.
- **PCM format assumption (mono, 16-bit)**: confirmed correct against
  multiple independent, current sources describing Gemini TTS output
  as "24kHz, 16-bit PCM" mono, across both the `gemini-2.5-flash-
  preview-tts` and `gemini-3.1-flash-tts-preview` model generations.
- **`language` handling (prompt-steering, not a structured field) —
  investigated in depth, confirmed correct as designed.** A
  `SpeechConfig.languageCode`/`language_code` field genuinely exists,
  but only confirmed documented for the **Live API**
  (`BidiGenerateContent`) and **Vertex AI**'s
  `aiplatform.v1beta1.SpeechConfig` proto — neither of which this
  codebase calls (it calls `generativelanguage.googleapis.com`'s
  `generateContent`, the Gemini Developer API). Google's own
  documentation and cookbook *for this exact endpoint* demonstrate
  and recommend natural-language language-steering ("Read this in
  French: ...") with no `languageCode` field shown anywhere in that
  page's request examples. The implementation's approach was
  therefore **not** a corner cut; it matches the officially
  recommended technique for the API surface actually in use. No
  fix applied. (Documented here as an example of what independent
  re-verification is for — this could easily have gone the other
  way.)
- **MIME type parsing robustness — independently stress-tested
  against a real, documented format change.** Web research surfaced
  a filed, dated defect in another open-source project
  (home-assistant/core #168453) caused by a Gemini model-generation
  MIME type change: `gemini-2.5-flash-preview-tts` returns
  `audio/L16;codec=pcm;rate=24000`, while `gemini-3.1-flash-tts-
  preview` returns `audio/l16; rate=24000; channels=1` — lowercase,
  space-separated, with an added `channels=` parameter, which broke
  that project's case-sensitive `startswith("audio/L")` check. This
  implementation's `_pcm_to_wav()` was directly tested against
  **both** real formats (Section 8 below) and correctly extracts the
  sample rate from each, because it never validates or branches on
  the MIME type's `audio/L16`/`audio/l16` prefix at all — it only
  regex-searches for `rate=`, which is present and unambiguous in
  both formats. This implementation is therefore not exposed to the
  class of bug that hit that other project. No fix required.
- **Voice/seed handling**: `voiceConfig.prebuiltVoiceConfig.
  voiceName` and `generationConfig.seed` are only included when
  actually requested (`if request.voice`/`if request.seed is not
  None`), confirmed correct and consistent with `generate_image()`'s
  own "don't send what wasn't asked for" convention.

## 7. Owner Decision D1 (Naming) — Verified Clean

`grep`-level and manual search across `src/` and `tests/EP084/`
confirms zero occurrences of a generic `generate_audio()` or
`supports_audio_generation()` anywhere. Every new symbol
consistently uses the approved speech-specific names.
`AudioGenerationService`'s own name is the one approved exception
(the *service*, not a provider method, is named after the EP's
subject — matching `image_generation_service.py`'s own file-naming
precedent) and does not conflict with D1's provider-method naming
requirement.

## 8. Owner Decision D2 (PCM → WAV) — Audited in Depth, One Defect Found and Fixed

`_pcm_to_wav()` was read in full and independently stress-tested
(not merely re-run through the existing suite):

- Sample width (16-bit / 2 bytes) and channel count (mono / 1) are
  fixed constants, confirmed correct against every real-world Gemini
  TTS response format found during this audit's research (Section 6).
- Sample-rate extraction (`_PCM_RATE_PATTERN = re.compile(r"rate=
  (\d+)")`) was manually tested against both the Gemini 2.5 format
  (`audio/L16;codec=pcm;rate=24000`) and the Gemini 3.1 format
  (`audio/l16; rate=24000; channels=1`) — both correctly yield the
  right rate; the pattern is insensitive to surrounding whitespace,
  parameter order, and casing elsewhere in the string, since it only
  searches for the literal lowercase `rate=` substring, which is
  consistent across every real example found.
- Fallback to `_PCM_DEFAULT_SAMPLE_RATE_HZ` (24000 Hz) when `rate=`
  cannot be parsed is justified: 24000 Hz is Gemini's own current
  default across every documented example.
- WAV header validity and exact PCM payload preservation were
  independently verified byte-for-byte (RIFF/WAVE magic bytes present;
  decoded frames equal the original PCM bytes exactly) both in this
  audit's own manual testing and in `tests/EP084`.
- No filesystem I/O: confirmed — `_pcm_to_wav()` writes only to an
  in-memory `BytesIO` buffer.
- No external dependency: confirmed — only the standard-library
  `wave`, `base64`, and `io` modules are used.

**F1 (MEDIUM, FIXED) — malformed/undecodable audio data was not
normalized into a `ProviderError`.** Manually confirmed (before
fixing) that `base64.b64decode()` on a malformed string raises
`binascii.Error` (a `ValueError` subclass) and that a `wave`-internal
failure raises `wave.Error` (**not** a `ValueError` subclass) —
neither is a `ProviderError` subclass. `ProviderRequestExecutor.
_run()`'s exception handling is `except ProviderError`, so either
exception would have propagated all the way past the executor,
crashing `AudioGenerationService.generate()` with a raw traceback
instead of a clean, reported failure — a real, exploitable
correctness gap for a genuinely possible failure mode (a malformed
or truncated `inlineData.data` field from the API, or any future
edge case the `wave` module itself rejects). **Fixed in this STEP**
by wrapping the `_pcm_to_wav()` call inside `_parse_speech_response()`
in `except (ValueError, wave.Error)`, raising
`ProviderUnavailableError` instead. A new regression test,
`_test_gemini_generate_speech_malformed_base64_raises_provider_error`,
was added and confirmed passing; full regression re-run afterward
(Section 12).

Odd-length PCM and empty PCM payloads were also tested directly
against Python's `wave` module: neither raises an exception (the
`wave` module does not enforce frame alignment), so no crash risk
exists there — flagged as INFORMATIONAL only, since real Gemini TTS
responses are not documented to ever produce partial-frame PCM.

## 9. Binary / Resource Safety

- No accidental text decoding of audio bytes anywhere — `GeneratedAudio.
  data_base64` stays base64-encoded end-to-end; `_pcm_to_wav()` is the
  only place raw bytes exist, and only transiently in memory.
- No unnecessary duplicate copies beyond the base64-decode ->
  WAV-encode -> base64-encode chain that Owner Decision D2 itself
  requires — this is the minimum work the approved design implies,
  not an inefficiency introduced by the implementation.
- No binary/credential logging anywhere in the speech path (Section
  13 below).
- No temporary files, no persistent storage — confirmed by direct
  inspection; `_pcm_to_wav()` uses only an in-memory `BytesIO`.
- No unbounded buffering beyond what a single request/response
  already requires — no streaming architecture was introduced, and
  none is demonstrated to be required by anything in `BACKLOG.md` or
  the design.

## 10. Error Handling — Traced End-to-End

| Case | Behavior | Verified |
|---|---|---|
| Missing API key | `ProviderConfigurationError` before any HTTP call | Yes, test + source read |
| `audio_model` unset | `ProviderConfigurationError`, names the config key | Yes |
| Empty/blank `text` | `ProviderConfigurationError` | Yes |
| HTTP 404 | `ProviderUnavailableError`, names `audio_model` (own handling, not shared with `ask()`'s 404 path) | Yes |
| Other HTTP errors | Shared `_raise_for_transport_status()` — unchanged | Yes, by inspection |
| Malformed JSON body | `ProviderUnavailableError` (`except ValueError` on `response.json()`) | Yes |
| Missing candidates/content/parts/inlineData | `_extract_audio()` returns `None` -> `ProviderUnavailableError` ("no audio data") | Yes, test + source |
| Malformed/undecodable audio `data` | **F1 above — now `ProviderUnavailableError`** | Yes, fixed + tested this STEP |
| Retry/fallback exhaustion | Aggregated into `SpeechProviderRequestOutcome.error`, mirrors `execute_image()` exactly | Yes |
| Unsupported provider (initial) | `AudioGenerationService` fails fast, zero executor/network calls | Yes |
| Unsupported provider (fallback candidate) | Silently skipped by `execute_speech()`'s capability filter | Yes |

All error normalization is consistent with EP-082/EP-083's existing
`ProviderError` hierarchy; no new error type was introduced.

## 11. Bootstrap / Configuration Audit

- `self._audio_generation_service = AudioGenerationService(...)` in
  `Bootstrap._build_command_router()` (not `__init__`/`initialize()`
  — this audit confirmed the actual enclosing method by direct
  inspection rather than assuming, the same care STEP 2's own
  bootstrap test needed after an initial wrong guess) uses
  `ai_provider_manager`/`ai_request_executor` — the same instances
  `text_generation_service`/`image_generation_service` use. No
  duplicate `ProviderManager` or `ProviderRequestExecutor` is
  constructed.
- `audio_generation.enabled`/`audio_generation.fallback_enabled` are
  read with `bool(config.get(..., False))`, defaulting closed exactly
  like `image_generation.*`.
- No `CommandRouter.register()` call for this service; no
  `RuntimeService` integration; no new global/module-level state.
- `providers.gemini.audio_model` is threaded through
  `ProviderFactory` with the same `isinstance(..., str)` guard and
  `or None` normalization already used for `image_model`; an empty
  string is correctly treated as unconfigured (verified by direct
  inspection of `GeminiProvider.__init__`'s `audio_model or None`
  line).
- Disabled configuration was confirmed, both by inspection and by
  `tests/EP084`, to never reach the executor or network — the
  `enabled` check is the very first thing `AudioGenerationService.
  generate()` does.

## 12. Test-Quality Audit

`tests/EP084` (77 tests after this STEP's addition) was read in
full, not merely counted. Coverage genuinely exercises behavior, not
implementation trivia: every executor/service test asserts on
observable outcomes (`outcome.success`, `outcome.final_provider`,
call counts on fakes) rather than internal state; the Gemini-level
tests assert on the actual HTTP payload sent (`mock_request.call_args
.kwargs["json"]`) and on byte-level WAV structure (channel count,
sample width, frame rate, and exact PCM payload equality via
`wave.open()`+`readframes()`), not just "is non-empty." Negative
paths present: unsupported provider (both providers), fallback
disabled, non-eligible failure, fallback exhaustion, capability
mismatch (service-level, fails fast), malformed response, 404,
missing/empty `text`, unconfigured model, and — newly added this
STEP — malformed base64 audio data. The one gap this audit found
(the malformed-base64 crash, F1) existed precisely because STEP 2's
suite, like STEP 2's implementation, had not exercised that specific
input; it is closed now with both a source fix and a regression test.

Regression discipline: `tests/EP084` re-confirms, at the executor
level, that `execute()`/`execute_image()` still route through
`.ask()`/`.generate_image()` respectively and are unaffected by the
speech addition — a light-touch check mirroring `tests/EP083`'s own
equivalent, with full regression ownership correctly left to
`tests/EP082`/`tests/EP083` themselves (not duplicated here).

## 13. Regression Verification

Directly re-run in this audit session (not taken from the STEP 2
report):

```
tests/EP084   : 77 passed / 0 failed / 0 skipped
tests/EP083   : 60 passed / 0 failed / 0 skipped
tests/EP082   : 69 passed / 0 failed / 0 skipped
tests/EP069   : 68 passed / 0 failed / 0 skipped
tests/EP069_3 : 80 passed / 0 failed / 0 skipped
tests/EP069_4 : 41 passed / 0 failed / 0 skipped
TOTAL         : 395 passed / 0 failed
```

Run both before and after this STEP's fix (F1) and again after adding
its regression test; all green throughout, confirming the fix
introduced no regression of its own.

## 14. Security Audit

- No API key or authorization header ever appears in a log line or
  exception message in the speech path — confirmed by direct
  `grep`/inspection of every `logger.*`/`raise` call touching
  `_api_key` in `gemini_provider.py`; only the human-readable
  configuration key name (`'providers.gemini.api_key'`) appears in
  error text, never the secret value.
- No raw audio bytes or base64 payload are ever logged — the two
  `logger.info()` calls in `generate_speech()` include only the
  provider name, model identifier, and latency.
- No prompt/spoken-text content is logged — `request.text` never
  appears in any log line, matching `generate_image()`'s own
  precedent of never logging `prompt`.
- No unsafe temporary-file behavior — none exists; everything is
  in-memory.
- No secret propagation into result objects — `SpeechGenerationResult`/
  `GeneratedAudio` carry only `model`/`latency_ms`/`data_base64`/
  `mime_type`, no credential fields.

No concrete security finding beyond F1 (which is a correctness/
error-handling defect, not a security exposure — the crash it caused
carried no sensitive data).

## 15. Scope-Creep Audit

Confirmed absent, by direct search and by reading every changed file
in full: generic audio-generation abstraction, universal media
framework, music/sound-effect generation, video/presentation
integration, STT implementation, persistent audio repository, audio
editing/mixing framework. `src/skills/voice/text_to_speech.py`/
`speech_to_text.py` (EP-046/047) are untouched — confirmed by
timestamp and by content diff against the copies inspected during
STEP 1.

## 16. Findings Summary

| ID | Severity | Area | Status |
|---|---|---|---|
| F1 | MEDIUM | `gemini_provider.py` `_parse_speech_response()`/`_pcm_to_wav()` | **Fixed this STEP** — malformed/undecodable audio data now raises `ProviderUnavailableError` instead of an uncaught `binascii.Error`/`wave.Error`. Regression test added. |
| F2 | LOW | `provider_request_executor.py` `_run()` docstring | **Fixed this STEP** — docstring updated to mention `execute_speech()` as a third caller (was documentation-only; no behavior change). |
| F3 | INFORMATIONAL | `gemini_provider.py` `generate_speech()` language handling | No fix needed — independently verified correct for the actual API endpoint in use. |
| F4 | INFORMATIONAL | `gemini_provider.py` `_pcm_to_wav()` MIME assumptions | No fix needed — independently stress-tested against two real Gemini model generations' MIME formats; implementation is robust to, and not exposed to, a real bug class that affected another project. |
| F5 | LOW/INFORMATIONAL | `src/modules/test_module.py` | Pre-existing (predates EP-084): `tests.EP083...` was never registered for the `test EP083` CLI command. Out of EP-084 scope; not fixed, per the Hardening Rule's "do not fix unrelated pre-existing issues" instruction. Already disclosed in the STEP 2 report; reconfirmed still present. |

No CRITICAL or HIGH finding remains. No finding required a design
change or any deviation from the approved `EP084_DESIGN.md`.

## 17. Fixes Applied (this STEP)

1. `src/core/ai/providers/gemini_provider.py` — `_parse_speech_response()`
   now wraps its `_pcm_to_wav()` call in `except (ValueError,
   wave.Error)`, raising `ProviderUnavailableError` (F1).
2. `src/core/ai/provider_request_executor.py` — `_run()`'s docstring
   updated to reflect its three current callers (F2).
3. `tests/EP084/test_audio_generation_provider_integration.py` — added
   `_test_gemini_generate_speech_malformed_base64_raises_provider_error`
   and registered it in `run()` (76 -> 77 tests).

No other file was modified during STEP 3. `EP084_DESIGN.md` was not
altered — no finding required a design-level correction.

## 18. Remaining Warnings

- F5 (pre-existing `test_module.py` gap for EP-083, unrelated to
  EP-084, not fixed here).
- F3/F4 are informational, not defects, but are recorded because they
  represent genuine external-API uncertainty (documented-elsewhere-
  but-unconfirmed-here `languageCode` field; theoretical non-mono/
  non-16-bit PCM) that a future Gemini API change could affect. No
  action is warranted without new evidence.
- The same pre-existing `tests/EP069_2`/`PySide6` environment
  limitation documented since EP-082/083 remains unrelated and
  unaffected.

## 19. Final Verdict

```
PASS WITH WARNINGS
```

One genuine MEDIUM-severity defect (F1) was found through independent
testing that STEP 2's own passing suite had not exercised, and is now
fixed and regression-tested. One LOW documentation-accuracy gap (F2)
was fixed. Two informational findings (F3/F4) were investigated in
depth via live, current API research and confirmed *not* to be
defects — Gemini's documented behavior for the specific endpoint and
model generations in scope matches the implementation exactly,
including robustness against a real-world MIME-format regression that
affected another project. The only remaining warning (F5) is a
pre-existing, unrelated gap correctly left out of scope.
