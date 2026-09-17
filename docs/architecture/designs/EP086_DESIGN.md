# EP-086 — Presentation Generation Integration

**Status: DESIGN READY WITH OWNER DECISIONS**

## 1. Title / EP Identifier

EP-086 — Presentation Generation Integration.

## 2. Authoritative Scope

Confirmed by direct search of all four planning documents. `BACKLOG.md`'s
"AI Content Platform (EP-082–EP-087)" section is the sole primary
definition:

```
- **EP-086 — Presentation Generation Integration** (MEDIUM)
```

No contradicting title exists anywhere in the repository. However, a
second, independent reference in `BACKLOG.md` materially narrows and
clarifies what this title means, and is treated as authoritative
scope evidence, not merely a passing mention:

```
- **EP-103 — Presentation Generation for Claims** (MEDIUM). **REUSE**:
  EP-076 (document assembly) and EP-086 (AI presentation-content
  generation, formerly EP-084).
```

This is the repository's own, most specific description of what
EP-086 actually produces: **"AI presentation-content generation"** —
and, critically, it is REUSED *together with*, and explicitly
distinct from, **EP-076 (document assembly)**. If EP-086 itself
already produced a finished, rendered presentation file, EP-103 would
have no reason to separately cite an "assembly" dependency alongside
it. This is the single most important piece of scope evidence this
design relies on, and it resolves Section 3's central question
(Section 6 below) directly from repository evidence rather than
design inference.

**Documentation-currency note (reported, not corrected — out of STEP
1 scope):** `JARVIS_ROADMAP.md`'s Phase C header still reads *"planning
only, except EP-082 and EP-083"* and does not reflect EP-084's or
EP-085's actual completion (both finished STEP 1-3 with `PASS`/`PASS
WITH WARNINGS` verdicts). This predates EP-086 and is unrelated to
it; not touched by this design.

## 3. Goals

- Standalone, non-conversational generation of **structured
  presentation content** (a title plus an ordered sequence of slides,
  each with a title, bullet points, and optional speaker notes) from
  a text prompt, via the existing AI provider abstraction.
- Follow the same additive extension pattern EP-082/083/084/085 all
  used: new `AIProvider` capability pair, new `ProviderRequestExecutor`
  method reusing the unmodified `_run()`, new standalone service,
  additive configuration, no CLI/CommandRouter exposure.

## 4. Non-Goals / Exclusions

- **Producing a rendered presentation file** (`.pptx`, `.odp`, PDF
  slides, or any other file format). Per Section 2's evidence, this
  is explicitly a *separate* concern ("document assembly", EP-076's
  domain) from what EP-086 itself produces. This repository has zero
  existing `.pptx`/slide-rendering code or dependency (confirmed by a
  repository-wide search — no `python-pptx`, no file-format library,
  no "slide" business logic anywhere in `src/`), so introducing one
  here would be scope creep unsupported by any authoritative source.
- Speaker delivery, narration audio, or any composition with EP-084's
  speech generation.
- Any visual design, theming, layout, image selection, or branding —
  content only.
- Persistent storage of generated content (no database, no file
  writes — matches every prior modality's own "no persistence"
  precedent, and is even more clear-cut here since there is no
  binary artifact to persist in the first place).
- Any modification to EP-069.4's capability abstraction.
- Any modification to `AIService`, `TextGenerationService`,
  `ImageGenerationService`, `AudioGenerationService`,
  `VideoGenerationService`, or their tests.
- CLI/CommandRouter exposure (deferred to EP-087 or later, matching
  every prior modality's own deferral).
- EP-103's own claim-specific presentation logic (a distinct, future,
  higher-level EP that is expected to *consume* EP-086, not be built
  by it).

## 5. Existing Architecture

```
<Modality>GenerationService -> ProviderRequestExecutor.execute_<modality>()
    -> ProviderManager -> AIProvider.<generate_method>() -> GeminiProvider
```

Confirmed directly from the current source tree (not from prose):

- `src/core/ai/provider.py` — `AIProvider` ABC now carries four
  additive capability pairs (`supports_image_generation()`/
  `generate_image()`, `supports_speech_generation()`/
  `generate_speech()`, `supports_video_generation()`/
  `generate_video()`), each defaulting to "unsupported"/"always
  raises". `ask()` already supports `temperature`/`system_prompt`
  and is a single, synchronous `generateContent` call.
- `src/core/ai/provider_request_executor.py` — `execute()`/
  `execute_image()`/`execute_speech()`/`execute_video()` all delegate
  to one private, synchronous `_run()` helper. `execute_video()` is
  the one exception to "single HTTP call": it wraps a `generate_
  video()` implementation that internally performs a long-running
  initiate-then-poll cycle (EP-085), which `_run()` tolerates only
  because it treats `request_fn` as an opaque, blocking call — `_run()`
  itself has no notion of polling or long-running operations.
- `src/core/ai/providers/gemini_provider.py` — `ask()`/
  `generate_image()`/`generate_speech()` all call the same
  `generateContent` endpoint; `generate_video()` additionally calls
  `predictLongRunning` and a separate operation-polling endpoint
  (Veo-specific, EP-085).
- `src/services/{text,image,audio,video}_generation_service.py` — all
  four share one structural pattern: `enabled` check ->
  `provider_manager.get_current() is None` check ->
  `provider_manager.is_enabled()` check -> `supports_<modality>_
  generation()` check -> executor call -> `result is None` guard.
  None depend on `ConversationManager`/`ContextManager`.
- `src/bootstrap.py` — all four services share one
  `ai_provider_manager`/`ai_request_executor` instance, wired inside
  `Bootstrap._build_command_router()`, none registered on
  `CommandRouter`.
- `config/config.yaml` — each modality has its own namespace
  (`content_generation:`, `image_generation:`, `audio_generation:`,
  `video_generation:`) plus, for image/audio/video, a dedicated
  `providers.gemini.<modality>_model` field. Text generation
  (`content_generation:`) has **no** dedicated model field — it
  reuses the single `providers.gemini.model` already configured for
  `ask()`.
- `src/core/capability/` (EP-069.4) — confirmed unrelated (external/
  internal tool cataloging), untouched by every prior modality.

## 6. The Central Architectural Finding — Presentation Generation Is Structured Text Generation, Not a Binary Media Modality

This is the finding that governs every subsequent decision in this
design, and it is the reason this design does **not** mechanically
copy EP-083/084/085's `Generated<X>(bytes-or-uri)` pattern.

Independently verified (not assumed) against Google's current,
official documentation for `generateContent` (the exact endpoint
`ask()`/`generate_image()`/`generate_speech()` already call, on the
exact host — `generativelanguage.googleapis.com` — this codebase
already targets): `generationConfig.responseMimeType: "application/
json"` combined with `generationConfig.responseSchema: {...}`
produces schema-conformant, structured JSON output from an ordinary
text-generation call. Google's own documentation states this is
*"supported by all Gemini models (except for Gemini 1.0 models)"* —
i.e. it is a **generationConfig option available on the same
general-purpose text model already configured for EP-082**, not a
capability requiring its own specialized model family the way
Veo (video) or the TTS-specific models (speech) do.

Combined with Section 2's repository evidence (EP-086 produces
"content", not an assembled file), the correct architecture for
EP-086 is:

- **No binary artifact, no URI, no MIME type, no file bytes anywhere
  in this EP's contracts.** The result is structured, parsed,
  validated data (a title and an ordered list of slides), held
  entirely as ordinary Python objects — closer in spirit to
  `TextGenerationResult`/`AskResult` than to `GeneratedImage`/
  `GeneratedAudio`/`GeneratedVideo`.
- **No long-running operation.** `generate_presentation()` is a single,
  synchronous `generateContent` call, exactly like `ask()`/
  `generate_image()`/`generate_speech()` — **not** like `generate_
  video()`'s initiate-then-poll cycle. There is no Google-documented
  long-running "generate a presentation" operation to poll; this
  would be pure invention if assumed otherwise.
- **No new dedicated `providers.gemini.presentation_model` field is
  architecturally required** the way `image_model`/`audio_model`/
  `video_model` were — those exist because Gemini genuinely requires
  a *different, specialized* model for those modalities. Structured
  JSON output works on the *same* general-purpose model already
  configured via `providers.gemini.model`. Whether to still add a
  dedicated field anyway (for operational flexibility, e.g. letting
  an operator pick a distinct/cheaper model for structured content)
  is a real, legitimate choice — but it is not forced by any Gemini
  capability boundary the way it was for image/audio/video. This is
  Owner Decision D1 (Section 23).

This means EP-086's provider integration is architecturally much
closer to (and reuses far more of) EP-082's pattern than EP-083's/
EP-084's/EP-085's, despite sitting in the same "AI Content Platform"
numbering sequence as the three binary-media EPs.

## 7. Proposed Architecture

```
PresentationGenerationService -> ProviderRequestExecutor.execute_presentation()
    -> ProviderManager -> AIProvider.generate_presentation() -> GeminiProvider
                                                                  [single generateContent call,
                                                                   responseSchema-constrained JSON]
```

Mechanical repetition of the executor/service pattern; the one
deliberate divergence from EP-083/084/085 is that `generate_
presentation()` behaves like `ask()` (single call, fast, no polling),
not like `generate_video()`.

## 8. Component Responsibilities

- **`ProviderManager`**: unchanged; remains the sole provider-
  selection/fallback-candidate authority.
- **`ProviderRequestExecutor`**: gains `execute_presentation()`,
  mechanically identical in shape to `execute_image()`/
  `execute_speech()` (single-call wrapper around `_run()`, its own
  capability filter). `_run()` itself requires no change.
- **`GeminiProvider`**: owns the Gemini-specific request shape
  (`responseMimeType`/`responseSchema`) and response parsing/
  validation (turning returned JSON text into the structured
  contract, or a `ProviderError` if it doesn't conform).
- **`PresentationGenerationService`**: the standalone, non-
  conversational entry point, mirroring `AudioGenerationService`'s
  control flow exactly.

## 9. Contracts / Interfaces

### NEW

```python
@dataclass(frozen=True)
class PresentationSlide:
    title: str
    bullet_points: tuple[str, ...]
    speaker_notes: str | None = None

@dataclass(frozen=True)
class PresentationGenerationRequest:
    topic: str
    slide_count: int | None = None
    audience: str | None = None
    temperature: float | None = None

@dataclass(frozen=True)
class GeneratedPresentation:
    title: str
    slides: tuple[PresentationSlide, ...]

@dataclass(frozen=True)
class PresentationGenerationResult:
    presentation: GeneratedPresentation
    model: str
    latency_ms: float
```

Rationale for each field:

- `PresentationSlide`/`GeneratedPresentation` deliberately keep the
  `Generated<X>` naming convention from EP-083/084/085 for
  consistency of naming pattern, even though their *contents* are
  structured text, not bytes/URI — this naming choice is cosmetic,
  not a claim that this type behaves like the binary ones.
- `PresentationGenerationRequest.topic` (required) mirrors
  `SpeechGenerationRequest.text`/`ImageGenerationRequest.prompt`'s
  role as the primary content driver.
- `slide_count` (optional) — a project-level hint forwarded into the
  prompt/schema (e.g. a `minItems`/`maxItems` constraint on the
  `slides` array, or a natural-language instruction), not a guarantee
  Gemini will produce exactly that many; bounded validation is
  required (Section 18) to prevent a pathological request (e.g.
  `slide_count=100000`).
- `audience` (optional) — a natural-language steering hint (e.g.
  "engineers", "executives"), analogous to `SpeechGenerationRequest.
  language`'s prompt-steering precedent (EP-084) for a dimension
  Gemini has no dedicated structured field for.
- `temperature` (optional) — reuses the existing, already-validated
  `validate_temperature()` concept from `ask()`, since this capability
  is fundamentally a text-generation call. No prior binary-media
  modality exposed this (image/audio/video have their own randomness
  controls, `seed`, instead); presentation generation's closer
  kinship to text generation justifies exposing it here.
- `PresentationSlide.speaker_notes` is optional (`None` allowed) since
  nothing in Google's documentation or this repository's evidence
  guarantees a model always produces them, and forcing a non-optional
  field would require inventing a fallback value.
- **Deliberately excluded**: `output_format`, `theme`, `template`,
  `image_suggestions` — no evidence supports these, and Section 4
  explicitly excludes rendering/design as out of scope.

### MODIFIED (additive only)

- `src/core/ai/provider.py` — four new dataclasses,
  `supports_presentation_generation()`/`generate_presentation()` on
  `AIProvider` with safe defaults. Every existing provider remains
  valid without modification other than `GeminiProvider`.
- `src/core/ai/provider_request_executor.py` — one new method
  (`execute_presentation()`) and one new outcome dataclass
  (`PresentationProviderRequestOutcome`), mirroring
  `SpeechProviderRequestOutcome`. `_run()`, `execute()`,
  `execute_image()`, `execute_speech()`, `execute_video()` unchanged.
- `src/core/ai/providers/gemini_provider.py` — new
  `generate_presentation()` (single `generateContent` call with
  `responseSchema`), `supports_presentation_generation()`, and
  response-parsing/validation helpers. See Owner Decision D1
  (Section 23) for whether a new constructor parameter
  (`presentation_model`) is added or `self._model` is reused.
- `src/core/ai/provider_factory.py` — threads whichever configuration
  Decision D1 selects.
- `config/config.yaml` — additive `presentation_generation:`
  namespace (Section 15).
- `src/bootstrap.py` — additive `presentation_generation_service`
  wiring (Section 16).

### EXISTING (fully reused, unmodified)

`ProviderManager`, `_run()`, `execute()`, `execute_image()`,
`execute_speech()`, `execute_video()`, every existing service,
`ClaudeProvider`, `ConfigDrivenProvider`, `validate_temperature()`,
EP-069.4's `src/core/capability/`.

### DEFERRED

- Actual `.pptx`/file assembly (Section 4 — a separate, future
  concern, likely EP-087's or a document-assembly EP's territory).
- Multi-language presentation generation as a structured field
  (handled, if at all, the same prompt-steering way EP-084 handled
  `language`).
- Any CLI/CommandRouter exposure.

### OUT OF SCOPE

Everything in Section 4.

## 10. Provider Integration

**Gemini is the only candidate**, for the same reason as every prior
modality: `ClaudeProvider` has no evidence of a compatible structured-
output guarantee investigated for this design (Anthropic's own API
has a different mechanism for structured output, not verified here
and not required — Gemini alone is in scope, exactly as EP-083/084/085
scoped to Gemini alone), and the `openai`/`ollama`/`lmstudio`
placeholders remain non-functional stubs.

Request shape (verified against Google's current, official
documentation for this exact endpoint/host):

```text
POST {_API_BASE_URL}/{model}:generateContent
Headers: x-goog-api-key, content-type: application/json
Body:
{
  "contents": [{"role": "user", "parts": [{"text": "<prompt built from topic/audience/slide_count>"}]}],
  "generationConfig": {
    "responseMimeType": "application/json",
    "responseSchema": { <object schema: title (string), slides (array of {title, bullet_points, speaker_notes})> },
    "temperature": <if provided>
  }
}
```

Response: `candidates[0].content.parts[0].text` contains the
schema-conformant JSON *as a string* (this is `generateContent`'s
existing, already-handled text-response shape — confirmed identical
to how `_parse_response()` already extracts `ask()`'s plain-text
replies; the only difference is that this text is then additionally
parsed as JSON and validated against the expected structure).

**UNVERIFIED — STEP 2 MUST VERIFY**: the exact JSON Schema dialect
`responseSchema` accepts (a subset of OpenAPI 3.0 Schema Object,
per every source consulted) and whether `minItems`/`maxItems` on the
`slides` array are honored as a genuine constraint or only a
best-effort hint — STEP 2 should confirm this with a real, minimal
API call before finalizing how `slide_count` is encoded, rather than
assuming either behavior.

## 11. Artifact Model

There is no artifact in the EP-083/084/085 sense. `GeneratedPresentation`
is ordinary, in-memory structured data (a dataclass containing strings
and a tuple of dataclasses) — not bytes, not a URI, not a file
reference, not anything requiring MIME-type/filename/temporary-storage/
download/lifetime/size-limit reasoning the way a binary artifact
would. This is a direct, evidence-based consequence of Section 6, not
an oversight: Section 5/11 of the STEP 1 prompt's own artifact-
handling questions (file bytes vs URI, filename, temporary storage,
download behavior, artifact lifetime) are **not applicable** to this
EP's actual scope, and this design does not manufacture answers to
them for a scenario that does not exist here.

## 12. Lifecycle

**Synchronous**, matching `ask()`/`generate_image()`/`generate_speech()`
— explicitly **not** EP-085's long-running/polling lifecycle. No
async, no job/queue framework, no polling, no operation identifiers.
This is justified directly by Section 6's evidence (no long-running
"generate a presentation" API exists to poll) rather than by
convenience — the STEP 1 prompt's explicit warning not to
"automatically copy EP-085's polling architecture" is honored here
because the evidence genuinely points away from it, not merely
because copying would be extra work.

## 13. Retry / Fallback Behavior

`execute_presentation()` reuses `_run()` unchanged, exactly like
`execute()`/`execute_image()`/`execute_speech()`. Because generation
is a single, fast call (not a multi-minute operation), the
duplicate-generation risk that justified EP-085's especially firm
`fallback_enabled=False` default does not apply with the same
severity here — a retried presentation-generation call costs roughly
what a retried text-generation call costs, not what a retried video
generation costs. `fallback_enabled` should still default to `false`,
for the same baseline reason every modality defaults it off (opt-in
fallback, consistent platform-wide default), not because of an
EP-085-style expensive-operation concern. No custom fallback logic is
needed in the service layer; the shared executor already owns this
concern in full.

## 14. Configuration

```yaml
presentation_generation:
  enabled: false
  fallback_enabled: false
```

Plus, contingent on Owner Decision D1:

```yaml
  gemini:
    ...
    # presentation_model: "gemini-3.1-flash"   # only if D1 selects a dedicated field
```

No existing configuration semantics are altered. No secrets
introduced — reuses `providers.gemini.api_key` unchanged.

## 15. Bootstrap / Service Integration

Mirrors `audio_generation_service`'s/`video_generation_service`'s
wiring in `Bootstrap._build_command_router()` exactly: same shared
`ai_provider_manager`/`ai_request_executor`, config-gated
`enabled`/`fallback_enabled`, stored as
`self._presentation_generation_service` for a future in-process
consumer (a strong candidate: EP-103's own claim-presentation logic,
per Section 2's evidence), **no** `CommandRouter` registration, **no**
`RuntimeService` integration.

## 16. Error Handling

No new error type. Extends the existing `ProviderError` hierarchy
exactly as every prior modality did:

| Case | Behavior |
|---|---|
| Disabled / missing API key / no configured model | `ProviderConfigurationError`, before any HTTP call |
| Empty `topic` | `ProviderConfigurationError` |
| `slide_count` out of a sane bound (Section 18) | `ProviderConfigurationError` |
| Auth/rate-limit/timeout/network failure | Existing `ProviderAuthenticationError`/`ProviderRateLimitError`/`ProviderTimeoutError`/`ProviderNetworkError`, unchanged, fallback-eligible where already established |
| Model not found (404) | `ProviderUnavailableError`, mirrors every prior modality's own 404 handling, naming the relevant config key |
| Malformed response body (not valid JSON at the transport level) | `ProviderUnavailableError`, mirrors `_parse_speech_response()`'s `except ValueError` precedent |
| Response text is not valid JSON matching the requested schema (model deviated) | `ProviderUnavailableError` — `responseSchema` is a strong constraint, not a hard guarantee; STEP 2 must not assume perfect conformance |
| Missing/empty `title` or `slides` | `ProviderUnavailableError`, mirrors `_extract_video()`'s "no usable data" idiom |
| Fallback exhaustion | Aggregated via the outcome's `error`, mirrors every prior modality exactly |

## 17. Security / Resource Safety

Because Section 11 establishes there is no binary artifact, most of
the STEP 1 prompt's file-oriented threat list (path traversal,
malicious filenames, MIME spoofing, oversized binary artifacts,
insecure temporary files) is **not applicable** to this EP's actual
scope — this design does not invent controls for a threat surface
that does not exist here, mirroring Section 11's own guidance to only
design controls relevant to the actual scope.

Genuinely applicable considerations:

- `slide_count` must be bounded (Section 18) to prevent a
  pathological request from generating an excessively large response/
  consuming excessive tokens — bounded the same way `max_tokens`
  already bounds `ask()`'s output, no new mechanism required.
- Prompt/topic content must never be logged, exactly matching
  `generate_image()`/`generate_speech()`/`generate_video()`'s
  existing discipline. Generated slide content (titles, bullets,
  speaker notes) must likewise never be logged verbatim — only
  provider name, model, slide count, and latency, mirroring the
  existing "log metadata, never content" convention.
- API key handling: reuses `providers.gemini.api_key`, no new secret
  mechanism.
- Untrusted provider responses: the returned JSON must be parsed
  defensively (Section 16), never `eval`'d or trusted to match the
  schema without validation.

## 18. Concurrency / Lifecycle

No new concurrency concern beyond what `ask()`/`generate_image()`/
`generate_speech()` already have: `generate_presentation()` reads only
immutable/read-only instance state (`self._enabled`, `self._api_key`,
`self._model`, etc.) and uses purely local variables for the request/
response cycle, so concurrent calls on the same `GeminiProvider`
instance do not share mutable state. No operation identifiers, no
cleanup, no cancellation — none of these apply to a single synchronous
call. `slide_count`'s upper bound (recommended: reject values outside
1-30, mirroring a sane, conservative range with no repository
precedent to contradict it — flagged as an Owner Decision candidate
only if the Owner wants a different ceiling; the *existence* of a
bound is not optional, only its exact value is a minor tuning
question) is the one concrete safety mechanism this EP adds.

## 19. Testing Strategy

Mirrors `tests/EP084`/`tests/EP085`'s structure and depth:

- **Contracts**: `PresentationSlide`/`PresentationGenerationRequest`/
  `GeneratedPresentation`/`PresentationGenerationResult` construction/
  immutability.
- **AIProvider defaults**: `ClaudeProvider`/`ConfigDrivenProvider`
  remain valid, `supports_presentation_generation()` False,
  `generate_presentation()` raises.
- **Executor**: `execute_presentation()` primary success, fallback
  disabled, fallback skips non-capable candidates, non-eligible
  failure never retries, fallback exhaustion — mirrors the five
  `_test_executor_speech_*`/`_test_executor_video_*` tests exactly.
- **Service**: disabled, no provider, AI subsystem disabled,
  capability mismatch (fails fast), success, fallback success,
  non-conversational structural check — mirrors `AudioGenerationService`'s
  seven tests exactly.
- **Gemini — request/response shape**: correct `responseMimeType`/
  `responseSchema` construction; `slide_count`/`audience`/`temperature`
  included only when provided; successful parse into
  `GeneratedPresentation`; malformed JSON text; JSON that parses but
  doesn't match the expected shape (missing `title`/`slides`, wrong
  types, extra/missing slide fields); empty `slides` array; model not
  found (404); empty `topic` validation; unconfigured model; auth/
  rate-limit/timeout/network passthrough.
- **Adversarial**: `slide_count` at/beyond the configured bound
  (rejected); a response containing far more slides than requested
  (must not crash, only trust what's structurally valid); deeply
  nested or oversized JSON text (parsed safely via the standard
  library `json` module, which does not require any new dependency
  or new safety mechanism).
- **Determinism**: no time/polling/network/filesystem dependency
  exists in this EP at all (Section 6/11/12), so — unlike EP-085 —
  there is no injectable-clock requirement; only the HTTP boundary
  (`requests.request`) needs mocking, exactly like EP-082/083/084's
  simpler (non-video) test suites.
- **Regression**: `tests/EP085`, `tests/EP084`, `tests/EP083`,
  `tests/EP082`, `tests/EP069`, `tests/EP069_3`, `tests/EP069_4` must
  remain fully green and untouched.

## 20. Cross-EP Compatibility

### Existing contracts reused unchanged

`ProviderManager` (all methods), `ProviderRequestExecutor._run()`,
`execute()`/`execute_image()`/`execute_speech()`/`execute_video()`
(all four, byte-identical), `validate_temperature()`, every existing
provider class other than the additive `GeminiProvider` changes,
EP-069.4's `src/core/capability/` (entirely untouched).

### Existing contracts extended additively

`AIProvider` (two new methods, safe defaults), `ProviderRequestExecutor`
(one new method, one new outcome type), `GeminiProvider` (one new
capability, additively), `provider_factory.py`, `config.yaml`,
`bootstrap.py` — all in the same additive-only shape every prior
modality already used.

### New contracts introduced

`PresentationSlide`, `PresentationGenerationRequest`,
`GeneratedPresentation`, `PresentationGenerationResult`,
`PresentationProviderRequestOutcome`, `PresentationGenerationService`.

### Existing behavior that MUST remain unchanged

`ask()`, `generate_image()`, `generate_speech()`, `generate_video()`,
`execute()`, `execute_image()`, `execute_speech()`, `execute_video()`,
`TextGenerationService`, `ImageGenerationService`,
`AudioGenerationService`, `VideoGenerationService`, and every one of
their existing tests (`tests/EP082`-`tests/EP085`).

## 21. Files Expected to Change in STEP 2

```
Modified:
  src/core/ai/provider.py
  src/core/ai/provider_request_executor.py
  src/core/ai/providers/gemini_provider.py
  src/core/ai/provider_factory.py
  config/config.yaml
  src/bootstrap.py
  src/modules/test_module.py

Created:
  src/services/presentation_generation_service.py
  tests/EP086/__init__.py
  tests/EP086/test_presentation_generation_provider_integration.py
```

## 22. Owner Decisions Required

- **D1 — Dedicated model field vs. reuse of `providers.gemini.model`.**
  Section 6 established that Gemini does not architecturally require
  a separate model for structured JSON output the way it does for
  image/audio/video. Two legitimate options: (a) reuse
  `providers.gemini.model` directly, with `supports_presentation_
  generation()` mirroring `is_available()`'s own readiness check
  (no new config field at all); (b) add `providers.gemini.
  presentation_model` anyway, for operational flexibility (an
  operator may want a distinct/cheaper model for structured content
  generation than their primary chat model), falling back to `model`
  when unset. **Recommendation: (b)**, for consistency with every
  prior modality's own dedicated-field pattern and to preserve
  operator flexibility, even though it is not strictly forced by a
  Gemini capability boundary the way the others were. **Architectural
  consequence**: (a) is simpler (no new config, `supports_
  presentation_generation()` becomes trivial) but slightly
  inconsistent with the platform's established per-modality-field
  convention; (b) preserves consistency at the cost of one more,
  not-strictly-necessary config key.

- **D2 — `slide_count` upper bound.** Recommended: reject requests
  above 30 slides with `ProviderConfigurationError`, a conservative,
  no-repository-precedent-to-contradict value (Section 17/18). This
  is a genuine, if minor, tuning choice with no existing convention
  to derive it from.

Not asked as Owner Decisions (resolved from repository/provider
evidence directly): scope (Section 2/6 — content, not a file, forced
by the EP-103 cross-reference and Gemini's actual capability shape);
lifecycle (Section 12 — synchronous, forced by the absence of any
long-running presentation API); executor/service shape (mechanical
repetition of established pattern); provider choice (Gemini only,
same reasoning as every prior modality); fallback default (`false`,
consistent baseline).

## 23. Open Risks / Unresolved Issues

- **UNVERIFIED (Section 10)**: the precise JSON Schema dialect and
  whether array-length constraints (`minItems`/`maxItems`) are
  strictly honored by `responseSchema` — STEP 2 must verify with a
  real, minimal API call before finalizing how `slide_count` is
  encoded into the schema/prompt, rather than assuming.
- `responseSchema` is described everywhere as a strong constraint,
  not an absolute guarantee — STEP 2's parsing/validation logic must
  be genuinely defensive (Section 16), not merely a formality.
- No repository precedent exists for a "content-only" (non-binary)
  `Generated<X>` type; STEP 2 should take care that
  `GeneratedPresentation`'s naming does not mislead a future reader
  into assuming it behaves like `GeneratedImage`/`GeneratedAudio`/
  `GeneratedVideo` — the docstring must be explicit about this
  distinction (mirrored from this design's own Section 9 rationale).

## 24. STEP 2 Implementation Boundaries

STEP 2 MUST:

1. Resolve Owner Decisions D1/D2 before writing implementation code.
2. Perform the Section 10 UNVERIFIED live-API check before finalizing
   the exact `responseSchema` shape/`slide_count` encoding.
3. Implement `generate_presentation()` as a single, synchronous
   `generateContent` call — no polling, no long-running operation, no
   new dependency.
4. Never introduce a binary artifact, URI, MIME type, or file write
   anywhere in this EP's contracts or implementation.
5. Not implement EP-103's claim-specific logic, EP-076's document
   assembly, or any actual file-rendering capability — those remain
   explicitly out of scope (Section 4).

## 25. Final STEP 1 Recommendation

The scope is confirmed via two independent, mutually-reinforcing
repository sources (Section 2) and resolved to a materially simpler,
non-binary, synchronous architecture than a naive "copy EP-085"
assumption would have produced — a conclusion reached through
evidence (Section 6), not preference. Two small, genuinely open
choices (D1/D2) remain for the Owner.

```
DESIGN READY WITH OWNER DECISIONS
```
