# EP-085 — Video Generation Provider Integration

**Status: DESIGN PROPOSED — OWNER DECISION REQUIRED**

## 1. Title

EP-085 — Video Generation Provider Integration.

## 2. Scope Discovery (Phase 1) — Authoritative Finding

The current repository's authoritative planning documents were
searched in full (`JARVIS_ROADMAP.md`, `BACKLOG.md`, `CHANGELOG.md`,
`RELEASE_NOTES.md`) for every `EP-085`/`EP085` occurrence. **Exactly
one match exists, in `BACKLOG.md`'s "AI Content Platform
(EP-082–EP-087)" section:**

```
- **EP-085 — Video Generation Provider Integration** (MEDIUM)
```

No other file mentions EP-085 under any other title, and no
contradicting definition was found anywhere in the repository. This
is a single, unambiguous, authoritative scope — **not** the
"Event-Driven Runtime & Scheduler" concept a prior, out-of-band
instruction incorrectly attached to a different EP number in this
project's history (that concept does not exist anywhere in this
repository's planning documents under any EP number, exactly as was
already established and corrected before EP-084). This STEP 1
proceeds on the single, verified title above.

**Documentation-currency note (reported, not corrected — Rule 6/10
forbid touching these files in STEP 1):** `JARVIS_ROADMAP.md`'s Phase
C header still reads *"planning only, except EP-082 and EP-083"* and
`BACKLOG.md`'s own EP-084 bullet carries no **COMPLETE** marker,
even though EP-084 (Audio & Speech Generation Integration) completed
STEP 1–3 with a `PASS WITH WARNINGS` audit verdict prior to this
task. This is a stale documentation gap (EP-084's own STEP 4 was
never run) — not a contradiction about EP-085's identity, and not
something this STEP 1 will fix. It does mean this design treats
EP-084's actual, current source-tree state (not what the stale
roadmap prose implies) as the true baseline — verified directly
against `src/` below, not assumed from prose.

## 3. Non-Goals / Explicit Exclusions

- Speech-to-text, audio understanding (EP-046/047's territory, untouched).
- Presentation generation (EP-086).
- The combined content-production pipeline (EP-087).
- Any modification to `AIService`, `TextGenerationService`,
  `ImageGenerationService`, `AudioGenerationService`, or EP-069.4's
  capability abstraction beyond the minimal, additive extension
  points this design proposes.
- Video *understanding*/analysis (distinct from video *generation*;
  no evidence anything in `BACKLOG.md` asks for it here).
- Video editing, trimming, mixing, or post-processing.
- A generic "long-running operation" framework for arbitrary future
  use — only what video generation itself requires.
- Persistent video storage/media library (see Section 11 — the
  recommended contract does not download video bytes into this
  repository at all in v1).

## 4. Repository Evidence

Inspected directly, not assumed:

- `docs/architecture/designs/EP082_DESIGN.md`, `EP083_DESIGN.md`,
  `EP084_DESIGN.md`, and `docs/architecture/audits/
  EP083_ARCHITECTURE_AUDIT.md`/`EP084_ARCHITECTURE_AUDIT.md` — the
  direct precedent chain this design is measured against.
- `src/core/ai/provider.py` — current `AIProvider` ABC, confirmed to
  already carry `supports_image_generation()`/`generate_image()`
  (EP-083) and `supports_speech_generation()`/`generate_speech()`
  (EP-084), each with a safe "unsupported" default.
- `src/core/ai/provider_request_executor.py` — confirmed `execute()`/
  `execute_image()`/`execute_speech()` all delegate to one private,
  synchronous `_run()` helper, which calls `request_fn(candidate)`
  once per attempted provider and expects it to either return a
  result or raise a `ProviderError` **within a single call** — there
  is no support anywhere in `_run()` for a multi-step,
  initiate-then-poll-then-fetch flow with its own internal waiting.
- `src/core/ai/providers/gemini_provider.py` (962 lines) — confirmed
  `_API_BASE_URL = ".../v1beta/models"`, used as `f"{_API_BASE_URL}/
  {model}:generateContent"` for every existing capability (`ask()`,
  `generate_image()`, `generate_speech()`). All three are single,
  synchronous HTTP calls via the shared `_send_request()`
  helper, which blocks for up to `self._timeout` seconds and then
  parses one complete JSON response.
- `src/core/ai/provider_factory.py` — confirmed the `image_model`/
  `audio_model` threading pattern (`config.get(...)` ->
  `isinstance` guard -> constructor kwarg).
- `src/services/image_generation_service.py`/
  `audio_generation_service.py` — confirmed both are structurally
  identical: `enabled` -> `get_current() is None` -> `is_enabled()`
  -> `supports_*_generation()` -> executor call -> `result is None`
  guard. Both assume the executor call **returns promptly** (no
  service-level timeout/cancellation handling exists anywhere).
- `src/bootstrap.py` — confirmed `text_generation_service`/
  `image_generation_service`/`audio_generation_service` all share one
  `ai_request_executor`/`ai_provider_manager` instance, wired inside
  `Bootstrap._build_command_router()`, none registered on
  `CommandRouter`.
- `config/config.yaml` — confirmed `providers.gemini.timeout: 120`
  (seconds) governs `_send_request()`'s blocking HTTP call today;
  no provider currently has a multi-minute timeout.
- `src/core/capability/` (EP-069.4) — confirmed unrelated (external/
  internal tool cataloging), untouched by EP-083/EP-084, and will
  remain untouched by this design for the same reason.
- **A genuine, pre-existing, unrelated finding surfaced during this
  reconnaissance (reported per Phase 1/8, not fixed per Rule 10):**
  `src/core/ai/text_generation_service.py` is a byte-identical,
  completely unreferenced duplicate of `src/services/
  text_generation_service.py` (confirmed via `diff` and via a
  repository-wide import search — nothing imports the `core/ai/`
  copy). This predates EP-084 and is unrelated to EP-085; it is
  flagged here only because Phase 2 explicitly asks whether existing
  "EP-082 extension patterns" are being read from the correct,
  live file — they are (`src/services/`), and this design does not
  reference or extend the dead copy.
- No design/audit document for EP-085/086/087 exists yet.

## 5. Existing Architecture (Confirmed Pattern, EP-082→EP-084)

```
<Modality>GenerationService -> ProviderRequestExecutor.execute_<modality>()
    -> ProviderManager -> AIProvider.<generate_method>() -> GeminiProvider
```

Every step in this chain, for text/image/speech, is a **single
synchronous request-response cycle**, typically completing in
seconds. This is the load-bearing assumption the entire existing
`_run()`/executor/service architecture is built on.

## 6. The Central Architectural Finding — Video Generation Is Not Request/Response

This is the finding that must govern every decision in this design.
Independently verified (not assumed) against Google's current,
official Veo documentation (`ai.google.dev/gemini-api/docs/veo`) and
cross-checked against multiple independent, dated implementation
reports:

Video generation is a **long-running operation**, structurally
different from `ask()`/`generate_image()`/`generate_speech()` in
every dimension that matters to this codebase's executor:

1. **Initiate**: `POST /v1beta/models/{model}:predictLongRunning`
   (not `:generateContent`) with `{"instances": [{"prompt": ...}],
   "parameters": {...}}`. Returns immediately with an operation
   handle, e.g. `{"name": "operations/generate_12345"}` — **not**
   the video.
2. **Poll**: `GET /v1beta/{operation_name}` repeatedly, checking a
   `done: bool` field, until `true`. Every source consulted describes
   this as taking **minutes**, not seconds — one official example
   polls every 10 seconds with sample timeouts of 5–15 minutes.
3. **Fetch**: once `done`, the response contains a `video.uri` (a
   Google-hosted download URL, requiring the same `x-goog-api-key`
   header to fetch), not inline `base64` bytes the way `inlineData`
   is for images/audio. A **separate** HTTP request is needed to
   actually retrieve video bytes, and those bytes are potentially
   tens to hundreds of megabytes — utterly unlike a small base64 PCM
   clip or a single generated image.

None of `_run()`, `execute()`, `execute_image()`, `execute_speech()`,
or any existing service assumes or supports any of this. A minimal,
mechanical repetition of EP-083/EP-084's pattern (`execute_video()`
wrapping a single `AIProvider.generate_video()` call through the
existing synchronous `_run()`) is possible **only if** `generate_video()`
itself performs the entire initiate+poll+(optionally fetch) sequence
internally before returning — which means a single `_run()` attempt
could now block the calling thread for several minutes, something
`_run()`'s design (a fast in-process retry loop) never anticipated
and every existing config `timeout` value (120s) is far too small
for.

**UNVERIFIED — STEP 2 MUST VERIFY:** one source encountered
during this research (`gemini_ex`, a third-party Elixir client)
claims video generation is available "currently only through Vertex
AI, not the [Developer/Gemini] API" — directly contradicting Google's
own official `ai.google.dev/gemini-api/docs/veo` page and two other
independent, dated sources, all of which show `predictLongRunning`
called directly against `generativelanguage.googleapis.com` (the
exact host this codebase's `_API_BASE_URL` already uses). The
official first-party source is weighted as authoritative for this
design, but STEP 2 must make one live, low-cost verification call
(e.g. a `predictLongRunning` initiate call, or at minimum a
`ListModels` check for a `veo-*` model ID under this project's actual
API key) before writing any implementation code, since if the
third-party claim is correct for this project's specific API key
tier, `GeminiProvider` cannot support this capability at all and
Section 12/13's Owner Decisions would need to be revisited.

## 7. Proposed Architecture

```
                         EXISTING (unchanged)
Service               -> ProviderRequestExecutor.execute()/execute_image()/execute_speech()
                             -> ProviderManager -> AIProvider -> GeminiProvider

                         NEW (EP-085, additive)
VideoGenerationService -> ProviderRequestExecutor.execute_video()
                             -> ProviderManager -> AIProvider.generate_video()
                                 -> GeminiProvider.generate_video()
                                     [internally: initiate -> poll -> return operation result]
```

`execute_video()` is added the same mechanical way `execute_image()`/
`execute_speech()` were: a thin wrapper around the existing, entirely
unmodified `_run()` helper, with its own `capability_filter` via a
new `AIProvider.supports_video_generation()`. **The only genuine
deviation from the EP-083/084 pattern is inside `GeminiProvider.
generate_video()` itself**, which must now perform three HTTP calls
(initiate, repeated poll, and optionally fetch) instead of one, and
must run for potentially minutes instead of seconds. `_run()`,
`ProviderManager`, and the service-layer's structural pattern
(enabled -> provider selected -> capability check -> executor call ->
result) all remain unmodified and fully reused — the long-running
nature is fully absorbed inside the provider, not leaked into the
executor or service layer. This is presented as the recommended
option; Section 20 below lays out the alternative considered and
rejected.

## 8. Proposed Data / Control Flow

```
VideoGenerationRequest(prompt, aspect_ratio?, duration_seconds?, negative_prompt?, seed?)
    |
    v
AudioGenerationService-style capability/enabled checks (service layer, unchanged pattern)
    |
    v
ProviderRequestExecutor.execute_video()  [new, mirrors execute_speech() exactly]
    |
    v
GeminiProvider.generate_video(request)
    |
    +-> POST .../models/{video_model}:predictLongRunning  -> operation name
    |
    +-> loop: GET .../{operation_name}  [sleep between polls]
    |         until done == true, or a configured max-wait elapses
    |
    +-> on done: extract video reference (Section 11) from
    |            response.generateVideoResponse.generatedSamples[0].video
    |
    v
VideoGenerationResult(video: GeneratedVideo(uri, mime_type), model, latency_ms)
```

## 9. Contracts / Interfaces

### NEW

- `VideoGenerationRequest` (frozen dataclass, `provider.py`) —
  `prompt: str`, `aspect_ratio: str | None`, `duration_seconds: int |
  None`, `negative_prompt: str | None`, `seed: int | None`. Modeled
  directly on the parameters every source above consistently
  documents as real, current Veo controls — deliberately excludes
  richer, less-universal controls seen in some sources (reference
  images, first/last-frame interpolation, video extension,
  multi-sample output) as speculative for a v1 contract, mirroring
  EP-083/084's own restraint (`EP083_DESIGN.md` Section 6,
  `EP084_DESIGN.md` Section 19).
- `GeneratedVideo` (frozen dataclass, `provider.py`) — **NOT** modeled
  on `GeneratedAudio`/`GeneratedImage`'s `data_base64` shape (Section
  11 explains why). Proposed: `uri: str`, `mime_type: str`.
- `VideoGenerationResult` (frozen dataclass, `provider.py`) —
  `video: GeneratedVideo`, `model: str`, `latency_ms: float`
  (`latency_ms` here spans the *entire* initiate+poll+fetch cycle —
  callers must not assume this is fast, unlike every other
  `*GenerationResult.latency_ms` in the codebase).
- `AIProvider.supports_video_generation()` / `generate_video()` —
  same safe-default pattern as `supports_image_generation()`/
  `supports_speech_generation()`.
- `ProviderRequestExecutor.execute_video()` / `VideoProviderRequestOutcome`
  — mechanical repetition of `execute_image()`/`execute_speech()`.
- `VideoGenerationService` (new file,
  `src/services/video_generation_service.py`) — mirrors
  `AudioGenerationService` exactly at the service-layer control-flow
  level (Section 7).

### MODIFIED (additive only)

- `src/core/ai/provider.py` — three new dataclasses, two new
  `AIProvider` methods with safe defaults. `ask()`/`generate_image()`/
  `generate_speech()` and every existing provider are unaffected;
  confirmed by the same reasoning EP-084's own audit already applied
  to EP-083's equivalent change.
- `src/core/ai/provider_request_executor.py` — one new method
  (`execute_video()`) and one new outcome dataclass. `_run()`,
  `execute()`, `execute_image()`, `execute_speech()` unchanged.
- `src/core/ai/providers/gemini_provider.py` — one new
  `video_model` constructor parameter (mirrors `image_model`/
  `audio_model`), `supports_video_generation()`, `generate_video()`,
  and internal helpers for the initiate/poll/fetch sequence. A new
  base-URL constant is required alongside the existing
  `_API_BASE_URL` (`.../v1beta/models`), since the operation-polling
  endpoint (`GET /v1beta/{operation_name}`) is **not** under
  `/models/` — this is a small, genuinely new wrinkle, not an
  oversight to copy from image/audio.
- `src/core/ai/provider_factory.py` — threads `providers.gemini.
  video_model` through, mirroring `image_model`/`audio_model`.
- `config/config.yaml` — additive `video_generation:` namespace and
  `providers.gemini.video_model` (Section 15).
- `src/bootstrap.py` — additive `video_generation_service` wiring
  (Section 16).

### EXISTING (fully reused, unmodified)

`ProviderManager`, `_run()`, `execute()`, `execute_image()`,
`execute_speech()`, `TextGenerationService`, `ImageGenerationService`,
`AudioGenerationService`, `ClaudeProvider`, `ConfigDrivenProvider`,
EP-069.4's `src/core/capability/`.

### DEFERRED

- Actually downloading video bytes into this repository (Section 11).
- Multi-sample output (`generatedSamples[N>1]`).
- Reference-image-conditioned generation, first/last-frame
  interpolation, video extension.
- Any CLI/CommandRouter exposure (matches EP-082/083/084's own
  deferral to EP-087 or later).
- Cancellation of an in-flight operation.

### OUT OF SCOPE

Everything listed in Section 3.

## 10. Provider Strategy

**Gemini (Veo) is the only candidate**, for the same reason it was
the only candidate for EP-083/084: `ClaudeProvider` has no public
video-generation capability, and the `openai`/`ollama`/`lmstudio`
placeholders remain non-functional stubs. This is consistent with,
not a deviation from, established precedent.

The specific Veo model identifier (e.g. `veo-3.1-generate-preview`,
`veo-3.0-generate-preview`, `veo-2.0-generate-001` all appear across
current sources as real, distinct models with different capabilities/
pricing) is left as pure configuration (`providers.gemini.video_model`),
exactly like `image_model`/`audio_model` — this design does not pick
one on the Owner's behalf.

## 11. The Binary-Data Owner Decision — Why This Cannot Mirror EP-083/084

This is the single most consequential decision in this design, and it
is a genuine Owner Decision (D2 in Section 22), not something
resolved by repository convention, because no existing precedent
fits:

- EP-083's `GeneratedImage`/EP-084's `GeneratedAudio` both hold
  `data_base64: str` — small, in-memory, self-contained payloads
  (a single image or a short speech clip).
- Veo's completed operation response does **not** hand back inline
  base64 data — it hands back a `uri` requiring a *separate*,
  authenticated HTTP GET to actually fetch bytes, and those bytes can
  be tens to hundreds of megabytes for even a short clip.
- Mirroring `data_base64` here would mean this design silently commits
  to downloading and base64-encoding a potentially huge file, held
  entirely in memory, inside a single service call — a materially
  different resource commitment than anything EP-082/083/084 ever
  made, and one `EP084_DESIGN.md`'s own "no persistence, no arbitrary
  limits without justification" reasoning did not have to confront at
  this scale.

Two legitimate options:

- **Option A — reference-only (`GeneratedVideo.uri`, no bytes).** The
  service returns Google's own download URI (plus its `mime_type`)
  and stops there. Simplest, matches the "no persistence" precedent
  most literally (there is truly nothing to persist — the video lives
  on Google's infrastructure until the URI expires), and avoids any
  new memory/timeout risk from downloading a large file. Trade-off:
  the URI requires the same `x-goog-api-key` to fetch and is
  presumably time-limited (no documented expiry window was found in
  this research — **UNVERIFIED, STEP 2 must confirm or document this
  gap explicitly to the Owner**), so a caller holding only a bare
  `uri` string may not be able to use it without also being handed
  (or independently possessing) the API key, and may find it expired
  by the time they act on it.
- **Option B — download-and-return-bytes (mirrors `data_base64`
  structurally).** `generate_video()` performs the extra fetch step
  itself and returns raw bytes (base64-encoded, matching the existing
  field name/shape for consistency). Matches the existing pattern's
  *shape* exactly, at the cost of a real, new resource commitment:
  every call holds a potentially large file fully in memory, and the
  existing `GeneratedAudio`/`GeneratedImage`-style dataclasses have
  never had to reason about a size limit — one would likely be needed
  here (an explicit, justified new limit, not an arbitrary one, per
  `EP084_DESIGN.md` Section 18's own precedent for *not* adding
  limits without justification — here the justification is unavoidable
  memory safety).

This design's recommendation is **Option A**, on the grounds that (a)
it is the only option that does not require inventing a new
size-limit policy from scratch, (b) it keeps `VideoGenerationService`'s
resource footprint comparable to every other service in this
codebase (no multi-hundred-megabyte in-memory buffers), and (c) a
reference-based result is still a complete, useful deliverable — a
future consumer (e.g. EP-087's pipeline) can decide for itself whether
and how to fetch the bytes. This is presented as a recommendation,
not a foregone conclusion — Section 22, Decision D2 asks the Owner to
confirm.

## 12. Error Handling

Extends the existing `ProviderError` hierarchy with **no new error
type**, mirroring EP-084's own "reuse existing hierarchy" discipline:

| Case | Behavior |
|---|---|
| Missing API key / disabled / no `video_model` configured | `ProviderConfigurationError`, before any HTTP call |
| Empty `prompt` | `ProviderConfigurationError` |
| Initiate call fails (auth/rate-limit/timeout/network/404) | Existing `ProviderAuthenticationError`/`ProviderRateLimitError`/`ProviderTimeoutError`/`ProviderNetworkError`/`ProviderUnavailableError`, exactly as `generate_image()`/`generate_speech()` already raise for their own single call |
| Operation never reaches `done` within a configured max-wait | `ProviderTimeoutError` — **new case this EP introduces**, since no prior capability had a "the request itself is still running" timeout distinct from "the HTTP call took too long" |
| Operation completes with an error status (`done: true` but with an error field, not a result) | `ProviderUnavailableError`, mirroring `_extract_audio()`/`_extract_images()`'s "no usable data" idiom |
| Malformed/missing `video.uri` in a completed operation | `ProviderUnavailableError` |
| Retry/fallback exhaustion | `VideoProviderRequestOutcome.error`, mirrors existing aggregation exactly |

## 13. Retry / Fallback Behavior

`execute_video()` reuses `_run()` unchanged, exactly like
`execute_image()`/`execute_speech()`. The one point requiring explicit
Owner attention (Decision D1, Section 22): **should a fallback-eligible
failure ever retry a video request at all?** Retrying a request that
may have already run for several minutes before failing (e.g. a
timeout after 8 minutes of polling) against a second provider, itself
potentially taking several more minutes, is a materially different
cost/latency trade-off than retrying a failed 2-second text request.
This design does not recommend disabling fallback outright — the
existing `fallback_enabled` config flag already makes this opt-in per
modality (`video_generation.fallback_enabled`, defaulting to `false`
like every other modality) — but flags that the *default* should very
likely remain `false` even more firmly here than for text/image/
speech, given the latency stakes, and that this is worth the Owner's
explicit awareness rather than silent inheritance of the existing
default rationale.

## 14. Capability Handling

`supports_video_generation()` is a narrow, additive `AIProvider`
capability flag — confirmed, by the same reasoning already applied to
`supports_image_generation()`/`supports_speech_generation()`, to be
architecturally distinct from and not a duplicate of EP-069.4's
`src/core/capability/` (external/internal tool cataloging). No change
to EP-069.4 is proposed or required.

## 15. Configuration Impact

Additive only, mirroring `image_generation:`/`audio_generation:`
exactly:

```yaml
video_generation:
  enabled: false
  fallback_enabled: false   # see Section 13 — default false, deliberately
  # New relative to EP-083/084's namespaces: video generation is a
  # long-running operation (Section 6), so the polling behavior needs
  # its own bounds, distinct from providers.gemini.timeout (which
  # governs a single HTTP call, not the multi-minute overall wait).
  poll_interval_seconds: 10     # UNVERIFIED default — STEP 2 should
                                 # confirm a reasonable value against
                                 # Google's own guidance (10s appears
                                 # consistently across every source)
  max_wait_seconds: 600          # Owner Decision candidate (D3) --
                                 # see Section 22
```

```yaml
  gemini:
    ...
    # video_model: "veo-3.1-generate-preview"
```

No existing configuration semantics are altered.

## 16. Bootstrap / Wiring Impact

Mirrors `audio_generation_service`'s wiring in
`Bootstrap._build_command_router()` exactly: same shared
`ai_provider_manager`/`ai_request_executor`, config-gated
`enabled`/`fallback_enabled`, stored as `self._video_generation_service`
for a future in-process consumer, **no** `CommandRouter` registration,
**no** `RuntimeService` integration.

## 17. Testing Strategy

Mirrors `tests/EP084`'s structure and depth, with genuinely new
categories the long-running nature requires:

- **Contracts**: construction/immutability of the three new
  dataclasses.
- **AIProvider defaults**: `ClaudeProvider`/`ConfigDrivenProvider`
  remain valid, unmodified, `supports_video_generation()` False,
  `generate_video()` raises.
- **Executor**: `execute_video()` primary success, fallback disabled,
  fallback skips non-capable candidates, non-eligible failure never
  retries, fallback exhaustion — mirrors `tests/EP084`'s five
  `_test_executor_speech_*` tests exactly, substituting types.
- **Service**: disabled, no provider, AI subsystem disabled,
  capability mismatch (fails fast), success, fallback success —
  mirrors `AudioGenerationService`'s six tests exactly.
- **Gemini — NEW categories this EP requires that EP-083/084 did not**:
  - Mocked initiate call returning an operation name.
  - Mocked poll sequence: `done: false` one or more times, then
    `done: true` — confirm the implementation actually loops and does
    not treat the first `done: false` response as failure or success.
  - Poll loop respects `max_wait_seconds` and raises
    `ProviderTimeoutError` when exceeded — **tests must not actually
    sleep for real minutes**; the poll-interval sleep must be
    injectable/mockable (an explicit STEP 2 implementation
    requirement, not optional).
  - Operation completes with an error status.
  - Operation completes with a missing/malformed `video.uri`.
  - 404 on the initiate call (unconfigured/invalid `video_model`).
  - Missing `video_model` configuration.
  - Empty `prompt`.
  - Confirm `GeneratedVideo` never contains base64 video bytes if
    Decision D2 selects Option A.
- **Malformed external response**: malformed JSON at any of the three
  HTTP steps (initiate/poll/fetch, if D2 selects Option B) must be
  normalized into a `ProviderError`, not escape as a raw exception —
  this is a direct, explicit regression check against the exact class
  of defect EP-084's own STEP 3 audit found and fixed
  (`EP084_ARCHITECTURE_AUDIT.md` F1).
- **Regression**: `tests/EP084`, `tests/EP083`, `tests/EP082`,
  `tests/EP069`, `tests/EP069_3`, `tests/EP069_4` must remain fully
  green and untouched.

## 18. Security Considerations

- API key handling: reuses `providers.gemini.api_key` unchanged,
  exactly as every prior modality does — no new secret.
- The download URI (Option A) itself is not a secret, but fetching it
  requires the same API key header; the design does not propose
  embedding the API key into any returned value or logging the URI's
  full contents if it could ever encode sensitive request parameters
  (no evidence it does, based on every example seen — the URI is a
  Google-hosted file reference, not a signed encoding of the prompt).
- Prompt content must never be logged, exactly matching
  `generate_image()`/`generate_speech()`'s existing discipline.
- No new temporary-file requirement under Option A; Option B would
  need explicit justification for keeping a large in-memory buffer
  safe (size cap, discussed but not resolved in Section 11).

## 19. Compatibility / Regression Considerations

Every change proposed is additive. `ask()`, `generate_image()`,
`generate_speech()`, `execute()`, `execute_image()`, `execute_speech()`,
`TextGenerationService`, `ImageGenerationService`,
`AudioGenerationService`, and every existing test suite are expected
to require zero modification. The one genuinely new shared-file touch
is `provider_request_executor.py`'s addition of a fourth method next
to three existing ones (mechanical, same pattern EP-084 already
applied to EP-083's file without incident).

## 20. Alternative Considered and Rejected

**Fully asynchronous contract** (`start_video_generation()` returning
an operation handle immediately, plus a separate `get_video_status()`
poll method exposed all the way up through the service layer to the
caller, who owns the poll loop). This would avoid ever blocking a
thread for minutes inside `_run()`. Rejected for this design's
recommendation because: (a) it cannot reuse `_run()`/`execute()`'s
existing retry/fallback shape at all — a "start" call and a "poll"
call are two entirely different requests with no shared retry
semantics, meaning this option would require a **second**,
new retry/fallback implementation, which Phase 3-D explicitly says to
avoid "unless technically unavoidable," and encapsulating the whole
cycle inside one blocking `generate_video()` call *is* technically
possible (if not ideal) via a longer timeout, so a second executor is
not unavoidable; (b) no existing consumer/caller convention in this
codebase (CLI, service, or otherwise) currently has any notion of an
outstanding "background operation" it could hold onto and poll later
— that concept does not exist anywhere else in this AI-provider
subsystem today. This alternative is not ruled out forever; it is
recorded here in case the Owner prefers it despite the added
complexity (Section 22, Decision D1 offers it as the alternative).

## 21. Risks

- **Thread-blocking risk (HIGH awareness, not a defect):** a single
  `generate_video()` call may block its caller's thread for several
  minutes. In the current, entirely synchronous request-handling
  model this codebase uses for every other AI capability, this is a
  new category of risk this EP alone introduces. No evidence was
  found that this codebase has any async/background-task convention
  suitable for AI-provider calls specifically (the existing
  `BackgroundWorkerPool`, EP-036, is scoped to workflow execution, not
  provider calls, and integrating with it is explicitly out of scope
  for this design per Section 3/9-DEFERRED).
- **UNVERIFIED Developer-API-vs-Vertex-AI availability** (Section 6)
  — if wrong, `GeminiProvider` cannot implement this capability at
  all under the current provider architecture, and EP-085 would need
  a materially different provider strategy (e.g. a new Vertex-AI-
  specific auth/config path this repository does not currently have
  for any provider).
- **Undocumented URI expiry** (Section 11) — Option A's usefulness
  depends on how long the returned URI remains valid; no expiry
  window was found documented in this research.
- **Config sprawl**: this is the first modality needing
  `poll_interval_seconds`/`max_wait_seconds` in addition to
  `enabled`/`fallback_enabled` — a small but real precedent-setting
  addition to the per-modality config shape.

## 22. Owner Decisions

- **D1 — Retry/blocking model.** Recommended: keep `generate_video()`
  fully synchronous/blocking (initiate+poll+return inside one call),
  reusing `_run()`/`execute_video()` exactly like image/speech, with
  `video_generation.fallback_enabled` defaulting to `false`.
  Alternative: the fully asynchronous start/poll contract (Section
  20), which avoids blocking but requires a second, new retry/
  fallback mechanism and has no existing caller convention to plug
  into. **Architectural consequence:** recommended option keeps the
  executor/service layer completely unmodified in shape; the
  alternative would require new executor-level and possibly
  service-level abstractions this design does not otherwise need.

- **D2 — Binary result handling.** Recommended: Option A,
  reference-only `GeneratedVideo.uri` (Section 11), no video bytes
  ever held in memory or returned by this codebase. Alternative:
  Option B, download-and-return-base64-bytes, mirroring
  `GeneratedAudio`/`GeneratedImage`'s shape at the cost of a new,
  large in-memory buffer per call and an as-yet-undefined size limit.
  **Architectural consequence:** Option A is a smaller, safer
  change; Option B is more consistent with EP-083/084's *literal*
  field shape but introduces the first real memory-size risk this
  provider subsystem has had to manage.

- **D3 — `max_wait_seconds` default.** Recommended: 600 seconds (10
  minutes), inside the range every source consulted suggests
  (5–15 minutes typical). No repository precedent exists for this
  value since no prior modality needed one. **Architectural
  consequence:** low — purely a configuration default, easily changed
  later without any code impact.

No other decision in this design requires Owner approval — naming
(`generate_video()`/`supports_video_generation()`), provider choice
(Gemini only), executor/service mechanical shape, and configuration
namespace structure all follow directly from established repository
convention with no legitimate alternative found.

## 23. STEP 2 Implementation Boundaries

STEP 2 MUST, before writing implementation code:

1. Resolve the Section 6 UNVERIFIED item (Developer API vs. Vertex-AI-
   only availability) with a live, minimal-cost check against this
   project's actual configured API key.
2. Confirm or correct the Section 11 UNVERIFIED item (URI expiry
   window) from Google's current documentation, and document whatever
   is found (even "undocumented, use promptly" is an acceptable,
   honest outcome) rather than inventing a number.
3. Implement exactly the Owner's D1/D2/D3 selections — no
   implementation may proceed against an unresolved Owner Decision.
4. Ensure the poll-loop's sleep is injectable/mockable from the very
   first line of test code written (Section 17) — this is not an
   optional nicety, since without it the test suite cannot be
   deterministic and fast, unlike every prior EP's test suite.
5. Not implement Section 20's rejected alternative unless the Owner
   explicitly overrides Decision D1.

## 24. Final STEP 1 Recommendation

The scope is confirmed, singular, and unambiguous (Section 2). The
architecture, however, contains a genuine, well-evidenced departure
from the EP-082→EP-084 pattern (Section 6) that this design does not
believe should be resolved unilaterally — Decisions D1/D2 materially
change what STEP 2 builds and are not implementation details.

```
DESIGN PROPOSED — OWNER DECISION REQUIRED
```
