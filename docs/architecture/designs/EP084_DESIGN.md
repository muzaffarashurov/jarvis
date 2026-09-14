# EP-084 — Audio & Speech Generation Integration

**Status: DESIGN PROPOSED — awaiting Owner Decision**

## 1. Purpose

Extend Jarvis's AI content-generation platform (Phase C, EP-082–EP-087)
with a third standalone content modality: audio generated from text,
via the same provider abstraction and shared execution path EP-082
(text) and EP-083 (image) already established. Confirmed EP-084
scope, per the repository's own authoritative `BACKLOG.md`/
`JARVIS_ROADMAP.md` (unchanged by the earlier "Event-Driven Runtime &
Scheduler" mix-up, which did not describe this repository and has
been discarded):

```text
EP-082 — Text Generation Provider Integration        COMPLETE
EP-083 — Image Generation Provider Integration        COMPLETE
EP-084 — Audio & Speech Generation Integration        THIS DESIGN
EP-085 — Video Generation Provider Integration
EP-086 — Presentation Generation Integration
EP-087 — Content Production Pipeline
```

## 2. Scope

In scope:

- A provider-independent request/result contract for generating
  spoken audio from text (text-to-speech).
- One new `AIProvider` extension point pair:
  `supports_audio_generation()` / `generate_speech()`.
- `ProviderRequestExecutor.execute_speech()`, sharing the existing
  private `_run()` retry/fallback control flow `execute()`/
  `execute_image()` already use.
- A new, standalone, non-conversational `AudioGenerationService`
  mirroring `TextGenerationService`/`ImageGenerationService` exactly.
- One concrete provider implementation: `GeminiProvider`, using
  Google's documented Gemini TTS models via the same raw-HTTP
  `generateContent` architecture `ask()`/`generate_image()` already
  use.
- An additive `audio_generation:` configuration namespace and
  `providers.gemini.audio_model`.
- Bootstrap wiring mirroring `text_generation_service`/
  `image_generation_service` (stored for a future in-process
  consumer; no CommandRouter registration).

Out of scope (see Section 19 for the full list and rationale):
speech-to-text/transcription, general (non-speech) audio generation
(music, sound effects), voice cloning, multi-speaker dialogue,
persistent audio storage, audio editing/mixing, and any EP-085/086/087
functionality.

## 3. Non-Goals

- Does not modify EP-069.4's Unified Capability Abstraction
  (`src/core/capability/`) — that catalogs external/internal tools
  and services, not AI-provider content modalities, exactly as
  EP-083 already established and left unchanged.
- Does not modify `ProviderManager`, `execute()`, or
  `execute_image()`'s existing signatures/behavior.
- Does not modify EP-046 (`speech_to_text.py`, Vosk-based) or EP-047
  (`text_to_speech.py`, `pyttsx3`-based) — see Section 6 for why
  these are a genuinely different, unrelated architecture that this
  design must not be confused with or duplicate.
- Does not introduce a generic "media generation" or
  "UniversalContentGenerationService" abstraction merely because
  text/image/audio are related (mirrors EP-083's own restraint).
- Does not add a new external dependency.

## 4. Repository Baseline

Inspected directly rather than assumed:

- `JARVIS_ROADMAP.md`/`BACKLOG.md` — confirmed EP-084's authoritative
  scope (Section 1) and confirmed no other roadmap entry describes
  audio/speech differently.
- `docs/architecture/designs/EP082_DESIGN.md`,
  `EP083_DESIGN.md`, and `docs/architecture/audits/
  EP083_ARCHITECTURE_AUDIT.md` — the direct precedent this design
  follows.
- `src/core/ai/provider.py` — `AIProvider` ABC,
  `ImageGenerationRequest`/`GeneratedImage`/`ImageGenerationResult`
  dataclasses, `supports_image_generation()`/`generate_image()`
  extension points, `ProviderError` hierarchy, `validate_temperature()`.
- `src/core/ai/provider_request_executor.py` — `execute()`,
  `execute_image()`, and the shared private `_run()` helper,
  `ProviderRequestOutcome`/`ImageProviderRequestOutcome`,
  `_FALLBACK_ELIGIBLE_ERRORS`.
- `src/core/ai/providers/gemini_provider.py` — the concrete
  `generate_image()` implementation (raw HTTP to `generateContent`,
  `responseModalities: ["IMAGE"]`, `inlineData` extraction,
  `_parse_image_response()`/`_extract_images()`).
- `src/core/ai/provider_factory.py` — how `providers.gemini.
  image_model` is threaded into `GeminiProvider`'s constructor.
- `src/services/text_generation_service.py`,
  `src/services/image_generation_service.py` — the exact
  non-conversational service shape and failure-reporting convention
  this design's `AudioGenerationService` mirrors.
- `src/bootstrap.py` — exact wiring pattern for
  `text_generation_service`/`image_generation_service` (shared
  `ai_request_executor`, config-driven `enabled`/`fallback_enabled`,
  stored as an instance attribute, no `CommandRouter` registration).
- `config/config.yaml` — `content_generation:`/`image_generation:`
  namespace conventions and the commented `providers.gemini.
  image_model` example.
- `src/skills/voice/text_to_speech.py` (EP-047) and
  `src/skills/voice/speech_to_text.py` (EP-046) — read in full; see
  Section 6.
- `requirements.txt` — confirmed `requests` is already a dependency
  (used by `GeminiProvider` today) and Python's `wave` module
  (considered in Section 9) is standard library, requiring no
  addition either way.
- Verified Gemini's actual, current TTS API shape via live
  documentation/reference lookup during this STEP 1 (Section 7),
  matching EP-083's own precedent of not inventing undocumented
  provider behavior.

## 5. Existing Architecture (EP-082/EP-083 Precedent)

```text
Text:
  TextGenerationService -> ProviderRequestExecutor.execute()
    -> ProviderManager -> AIProvider.ask() -> ClaudeProvider/GeminiProvider

Image:
  ImageGenerationService -> ProviderRequestExecutor.execute_image()
    -> ProviderManager -> AIProvider.generate_image() -> GeminiProvider
```

Both slices share one `ProviderRequestExecutor` instance (via
`ai_request_executor` in Bootstrap) and one private `_run()`
retry/fallback implementation. Both services are non-conversational
(no `ConversationManager`/`ContextManager`/persistence), both are
disabled by default via their own config namespace, and neither is
registered on `CommandRouter` (CLI exposure explicitly deferred to
EP-087 or later, per both prior designs).

## 6. Critical Distinction: EP-084 vs. the Existing EP-046/EP-047 Voice Skill

The repository already contains audio-related code — `src/skills/
voice/text_to_speech.py` (EP-047) and `speech_to_text.py` (EP-046) —
and it is essential this design does not confuse the two or duplicate
either:

| | EP-046/EP-047 (existing) | EP-084 (this design) |
|---|---|---|
| Purpose | Jarvis speaking its own replies aloud / transcribing microphone input, as an interactive voice *interface* | Standalone AI *content generation*: producing spoken audio as a deliverable, like EP-082/083 produce text/images |
| Backend | Fully offline: `pyttsx3` (OS-native SAPI5/eSpeak/NSSpeechSynthesizer voices), `Vosk` (local STT models) | A remote AI provider (Gemini), through the existing `AIProvider`/`ProviderRequestExecutor` architecture |
| Network | None | HTTP, via the same `generateContent` endpoint `ask()`/`generate_image()` already use |
| Trigger | `VoiceModule`/`CommandRouter`, an interactive voice session | A direct, non-conversational service call (mirroring `TextGenerationService`/`ImageGenerationService`) |
| Output | Audio played directly through the OS audio device (TTS) or PCM captured from a microphone (STT) | An in-memory `GeneratedAudio` result (bytes + MIME type), returned to the caller — never played, never captured |
| Language/voice model | OS-installed SAPI5 voices / per-language Vosk models, manually provisioned | Whatever voices/languages the configured Gemini TTS model supports |

These are two independent architectures serving two independent
purposes, and this design introduces no dependency between them in
either direction. `AudioGenerationService` does not call, wrap, or
replace `Pyttsx3TextToSpeechEngine`/`VoskSpeechToTextEngine`, and vice
versa. A future EP could conceivably let the voice skill use an
AI-provider-backed engine as an alternative to `pyttsx3` — that is
explicitly not this EP's concern and is called out again in Section
19/20.

## 7. What "Audio & Speech Generation" Means Here (Critical Design Question)

Investigated directly against Gemini's current, documented API rather
than assumed:

- **Text-to-speech (Option A) is the only capability actually
  available.** Gemini's TTS-capable models (e.g.
  `gemini-2.5-flash-preview-tts`, `gemini-3.1-flash-tts-preview`) are
  documented as TTS-only: *"the model can only do TTS, so you should
  always tell it to 'say', 'read', 'TTS' something"* — there is no
  separate, general "prompt → arbitrary audio" capability (music,
  sound effects) exposed through this same API surface. Option C
  (general audio generation) and Option D (both) are therefore not
  supported by the one provider in scope and are excluded, not by
  design preference but because there is nothing to implement them
  against without inventing undocumented behavior (forbidden by
  Section 22 of this prompt and by this repository's own
  `AI_GENERATION_STANDARD.md` precedent, cited throughout EP-082/083).
- **Option B (speech synthesis) and Option A (TTS) are the same thing
  for this API** — Gemini's TTS *is* speech synthesis from text; there
  is no meaningful distinction to preserve as two abstractions
  (Section 8's Option C, "separate `generate_speech()`/
  `generate_audio()` abstractions," is therefore rejected — see
  Section 8).
- **Option E (speech-to-text/transcription) is explicitly out of
  scope.** Nothing in `BACKLOG.md`'s "AI Content Platform" section
  (EP-082–EP-087) — a "*generation*" track — mentions transcription,
  and EP-046 already provides offline STT for the unrelated voice-
  interface purpose (Section 6). Adding provider-backed transcription
  here would silently duplicate EP-046's responsibility with a second,
  network-dependent implementation with no roadmap mandate to do so.

**Conclusion: EP-084 is text-to-speech generation only.**

## 8. Audio vs. Speech Abstraction (Owner Decision Candidate — recommended)

Per Section 6 of the STEP 1 prompt:

- **Option A — generic `generate_audio()`.** Misleading: implies
  support for non-speech audio (music, sound effects) that the one
  in-scope provider cannot produce. Would set an inaccurate
  expectation for any future provider added under this same name.
- **Option B — explicit `generate_speech()`.** Accurately names what
  the method actually does, matches Section 7's conclusion exactly,
  and leaves `generate_audio()` free for a genuinely different, future
  capability (e.g. a music-generation provider) to claim on its own
  terms without a naming collision or an awkward "well, actually it's
  speech-only" caveat on an `_audio_` name.
- **Option C — both `generate_speech()` and `generate_audio()`.**
  Rejected: Section 6's "do not create a generic media generation
  framework" instruction applies directly — there is no second
  capability to abstract yet, so a second method would be speculative.
- **Option D — other.** No repository or provider evidence supports a
  different name.

**Recommendation: Option B, `generate_speech()` /
`supports_speech_generation()`.** This is the one departure from a
naming pattern that would otherwise mechanically mirror
`generate_image()`/`supports_image_generation()`, so it is called out
explicitly as an owner decision rather than assumed (Section 24,
Decision D1).

## 9. Binary Data Handling (Owner Decision Candidate — recommended)

This is the one place EP-084 cannot simply copy EP-083's precedent
verbatim, and is worth stating plainly:

- EP-083's Gemini image response returns `inlineData` whose bytes are
  an immediately usable, self-contained image file (e.g. PNG) — no
  further transformation is needed to open or display it.
- Gemini's TTS response also returns `inlineData`, but its bytes are
  **raw, headerless 16-bit linear PCM** (`mimeType` literally reads
  `"audio/L16;codec=pcm;rate=24000"` or similar, per Google's current
  documentation and multiple independent, current implementation
  reports checked during this STEP 1). Unlike the image case, these
  bytes are *not* directly playable by an ordinary audio
  player/browser `<audio>` element — a WAV (or other container) header
  must be attached first, and the sample rate needed to build a
  correct header must itself be parsed out of the `mimeType` string
  (there is no separate structured sample-rate field in the response).

Two legitimate options:

- **Option A — pass through raw bytes + `mime_type` unchanged**
  (mirrors `GeneratedImage`'s exact "no transformation of provider
  output" precedent, and needs zero new code). The consumer is
  responsible for wrapping the PCM in a WAV header before playback.
- **Option B — wrap the PCM into a valid WAV container before
  returning it**, using Python's built-in `wave` module (already
  available; no new dependency) to attach a correct header (mono,
  16-bit, sample rate parsed from `mimeType`), so the returned bytes
  are immediately playable exactly like EP-083's image bytes are
  immediately viewable.

**Recommendation: Option B.** The WAV-wrapping step is small (a few
lines using the standard-library `wave` module), self-contained
inside `GeminiProvider.generate_speech()` only (no new class, no new
persistence, no new dependency), and removes a footgun every consumer
would otherwise have to solve identically and independently. This
does not contradict EP-083's "no transformation of provider output"
precedent in spirit — EP-083 had nothing to transform, because
Gemini's image bytes were already complete files; EP-084's provider
bytes are not, and returning them as literally unplayable audio would
be a materially less useful deliverable for no stated benefit. This
is nonetheless flagged as an owner decision (Section 24, Decision D2)
because it is a real design choice with a legitimate simpler
alternative (Option A), not a fact the repository already settles.

Either way: **no persistence** (in-memory only, mirroring
`GeneratedImage`'s "no file writes" precedent exactly), and **no
streaming** — Gemini's documented TTS response for `generateContent`
(non-streaming) is a single, complete `inlineData` payload per
request, matching the existing synchronous `_send_request()` call
`generate_image()` already uses; a genuinely streaming variant is not
what this design targets and is not required by anything in
`BACKLOG.md`.

## 10. Request Contract

```python
@dataclass(frozen=True)
class SpeechGenerationRequest:
    text: str
    voice: str | None = None
    language: str | None = None
    seed: int | None = None
```

Rationale for each field, and for what is deliberately excluded:

- `text` (required, non-empty) — the text to speak. Mirrors
  `ImageGenerationRequest.prompt`'s role exactly.
- `voice` (optional) — a prebuilt voice name (Gemini exposes ~30,
  e.g. `"Kore"`, `"Puck"`; passed through unchanged as
  `speechConfig.voiceConfig.prebuiltVoiceConfig.voiceName`). `None`
  uses the provider's own default voice. This is a genuine,
  documented, stable cross-request dimension (unlike a provider-
  specific tuning knob), so it belongs in the shared contract rather
  than being provider-specific-only.
- `language` (optional) — Gemini's documented behavior is to
  auto-detect language from the text/prompt content and has no
  separate structured "language" request field in `generateContent`
  for this capability (confirmed during this STEP 1's provider
  research; language is instead steered by natural-language
  instruction embedded in the prompt itself, e.g. *"Read this in
  French: ..."*). This field is kept as a **project-level, best-effort
  hint only**: when set, `GeminiProvider.generate_speech()` prefixes
  the request text with a short natural-language instruction (e.g.
  `"Speak the following in {language}: "`) rather than mapping it to
  a Gemini-specific structured parameter that does not exist. This
  keeps the contract stable even if a future provider *does* expose a
  structured language parameter — that provider would honor
  `language` directly, `GeminiProvider` honors it via prompt-steering.
  Explicitly documented as best-effort, not a guarantee.
- `seed` (optional) — mirrors `ImageGenerationRequest.seed` for
  consistency; forwarded to `generationConfig.seed` exactly as
  `generate_image()` already does, when Gemini's TTS endpoint accepts
  it (same `generateContent` config object).
- **Explicitly excluded**: `speaking style`/`speed`/`pitch` and
  multi-speaker configuration. Gemini supports rich, free-form
  "audio-control" instructions embedded directly in prompt text
  (documented as controllable via natural language — tone, pace,
  emotion) rather than as discrete structured parameters equivalent to
  `temperature`; inventing structured fields for something the
  provider itself treats as prompt content would misrepresent the
  actual API and could not be validated meaningfully at the contract
  level. A caller wanting style control uses `text` itself, exactly as
  Gemini's own documentation recommends. Multi-speaker configuration
  (`multiSpeakerVoiceConfig`) is excluded per Section 19 (multi-
  speaker dialogue is out of scope for a v1 single-request contract).
- **Explicitly excluded**: `model`/`output format`/`sample rate` as
  request fields — `model` is a `providers.gemini.audio_model`
  configuration concern (Section 13, mirroring `image_model` exactly,
  not a per-request field); output format/sample rate are dictated by
  the provider's response, not requestable inputs for this API
  (Section 9).

## 11. Result Contract

```python
@dataclass(frozen=True)
class GeneratedAudio:
    data_base64: str
    mime_type: str

@dataclass(frozen=True)
class SpeechGenerationResult:
    audio: GeneratedAudio
    model: str
    latency_ms: float
```

Mirrors `GeneratedImage`/`ImageGenerationResult`'s exact shape.
Singular `audio: GeneratedAudio` (not a tuple) rather than
`ImageGenerationResult.images: tuple[...]`, because Gemini's TTS
`generateContent` response yields exactly one `inlineData` audio part
per request (no `number_of_images`-equivalent "how many outputs"
request parameter exists for this capability, confirmed during
research) — a tuple-of-one would misrepresent the contract as
supporting multiple outputs when nothing produces more than one.
`mime_type` reflects Section 9's chosen handling: `"audio/wav"` if
Option B (WAV-wrapping) is approved, or the provider's raw
`"audio/L16;codec=pcm;rate=..."` string if Option A is approved
instead.

## 12. Provider Contract

Additive to `src/core/ai/provider.py`, exactly mirroring
`supports_image_generation()`/`generate_image()`'s existing shape:

```python
def supports_speech_generation(self) -> bool:
    """Base implementation always returns False."""
    return False

def generate_speech(self, request: SpeechGenerationRequest) -> SpeechGenerationResult:
    """Base implementation always raises ProviderUnavailableError."""
    raise ProviderUnavailableError(
        f"Provider '{self.name()}' does not support speech generation."
    )
```

Every existing provider (`ClaudeProvider` — Anthropic's API has no
public audio-generation endpoint, exactly as it has none for images;
the `openai`/`ollama`/`lmstudio` placeholders) remains a valid
`AIProvider` implementation with zero changes, exactly as EP-083 left
every provider but `GeminiProvider` untouched.

## 13. Executor Integration

Additive to `src/core/ai/provider_request_executor.py`:

```python
def execute_speech(
    self,
    provider: AIProvider,
    request: SpeechGenerationRequest,
    *,
    fallback_enabled: bool,
) -> SpeechProviderRequestOutcome:
    def request_fn(candidate: AIProvider) -> SpeechGenerationResult:
        return candidate.generate_speech(request)

    run_result = self._run(
        provider,
        request_fn,
        fallback_enabled=fallback_enabled,
        capability_filter=lambda candidate: candidate.supports_speech_generation(),
    )
    return SpeechProviderRequestOutcome(...)
```

This is a mechanical repetition of `execute_image()`'s exact shape
against the already-generic `_run()` helper — `_run()` itself requires
no change at all (it is already generic over `request_fn`'s return
type and already accepts an optional `capability_filter`).
`execute()`'s and `execute_image()`'s public signatures, behavior, and
log lines remain completely unchanged, exactly as EP-083 left
`execute()` unchanged when adding `execute_image()`. There remains
exactly one retry/fallback implementation (`_run()`) in the
repository, now serving three callers via three thin wrapper methods.

`SpeechProviderRequestOutcome` mirrors `ImageProviderRequestOutcome`'s
shape exactly (`success`, `initial_provider`, `final_provider`,
`result: SpeechGenerationResult | None`, `error`).

## 14. Service Layer

`AudioGenerationService` mirrors `ImageGenerationService` line for
line (constructor shape, `_NO_PROVIDER_SELECTED`/subsystem-disabled/
capability-mismatch checks performed before ever reaching the
executor, `generate()` method, identical failure-reporting
convention — every failure becomes `success=False` with a
user-friendly `error`, never a raised `ProviderError`). No
`ConversationManager`/`ContextManager`/persistence dependency, exactly
as Section 3 of this design's Non-Goals states.

```python
class AudioGenerationService:
    def __init__(
        self,
        provider_manager: ProviderManager,
        request_executor: ProviderRequestExecutor,
        enabled: bool = False,
        fallback_enabled: bool = False,
    ) -> None: ...

    def generate(self, request: SpeechGenerationRequest) -> SpeechGenerationResult: ...
```

(Named `AudioGenerationService`, not `SpeechGenerationService` —
Section 24 Decision D1 covers the provider-method naming; the service
name is kept aligned with the EP's own "Audio & Speech Generation"
title and with `image_generation.py`'s file-naming precedent, which
names the file/service after the EP's subject rather than the
specific verb. This is a naming-only distinction from Section 8's
`generate_speech()` method name and carries no behavioral
significance either way.)

## 15. Provider Implementation

`GeminiProvider` is the one concrete implementation in scope, for the
same reason EP-083 chose it: it is the only configured provider whose
underlying API (`generateContent`) documents this capability, reached
through the same raw-HTTP architecture already in place — no new SDK,
no new dependency.

```text
POST {_API_BASE_URL}/{audio_model}:generateContent
Headers: x-goog-api-key, content-type: application/json
Body:
{
  "contents": [{"role": "user", "parts": [{"text": "<prompt>"}]}],
  "generationConfig": {
    "responseModalities": ["AUDIO"],
    "speechConfig": {
      "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "<voice>"}}
    },
    "seed": <seed>
  }
}
```

Response parsing mirrors `_parse_image_response()`/`_extract_images()`
exactly in structure (`_parse_speech_response()`/`_extract_audio()`):
a 404 means the configured `audio_model` was not found (same
diagnostic message pattern as `_parse_image_response()`'s existing
404 handling); an empty/missing `inlineData` part raises
`ProviderUnavailableError` with the same "no data in response" idiom
`_extract_images()` already uses for images. If Section 9's Option B
is approved, WAV-wrapping happens inside this parsing step only,
using the sample rate parsed from the response's own `mimeType`
string (with a hard-coded, documented fallback of 24000 Hz — Gemini's
current default — if parsing the rate out of an unexpected `mimeType`
string ever fails, rather than raising and discarding an otherwise-
successful response).

`voiceConfig` is included only when `request.voice` is not `None`
(mirrors `generate_image()`'s "only include what was actually
requested" pattern for `negative_prompt`/`seed`); `seed` is included
only when not `None`, identically to `generate_image()`.

## 16. Configuration

Mirrors `image_generation:`/`providers.gemini.image_model` exactly:

```yaml
audio_generation:
  # EP-084 Audio & Speech Generation Integration. Additive namespace
  # for Phase C (AI Content Platform); does not alter 'ai:',
  # 'providers:', 'content_generation:', or 'image_generation:'
  # semantics above. Governs standalone (non-conversational)
  # speech-generation requests only -- see
  # src/services/audio_generation_service.py and
  # docs/architecture/designs/EP084_DESIGN.md. Disabled by default,
  # matching 'image_generation.enabled''s own off-by-default
  # precedent.
  enabled: false
  fallback_enabled: false
```

```yaml
  gemini:
    ...
    # EP-084 Audio & Speech Generation Integration. The TTS-capable
    # Gemini model identifier. Absent/empty means this provider does
    # not support speech generation (supports_speech_generation()
    # returns False). Distinct from 'model' (text) and 'image_model'
    # (EP-083) above.
    # audio_model: "gemini-2.5-flash-preview-tts"
```

Secrets: no new secret is introduced — the existing `providers.
gemini.api_key` is reused unchanged, exactly as `generate_image()`
already reuses it for image generation.

## 17. Bootstrap Wiring

Mirrors the existing `text_generation_service`/
`image_generation_service` block exactly:

```python
self._audio_generation_service = AudioGenerationService(
    provider_manager=ai_provider_manager,
    request_executor=ai_request_executor,
    enabled=bool(config.get("audio_generation.enabled", False)),
    fallback_enabled=bool(config.get("audio_generation.fallback_enabled", False)),
)
```

Same shared `ai_request_executor` instance (so there remains exactly
one fallback/retry implementation in the repository, now serving
`AIService`, `TextGenerationService`, `ImageGenerationService`, and
`AudioGenerationService`). No `CommandRouter` registration — CLI
exposure remains deferred to EP-087 or a later EP, identically to
EP-082/EP-083's own explicit deferral. Stored as an instance attribute
for a future in-process consumer, exactly like
`text_generation_service`/`image_generation_service` are today.

## 18. Error Handling

| Case | Where raised/reported |
|---|---|
| Speech generation disabled | `AudioGenerationService`, before executor/network |
| No provider selected / AI subsystem disabled | `AudioGenerationService`, before executor/network |
| Current provider lacks capability | `AudioGenerationService`, before executor/network (mirrors `ImageGenerationService`'s "initial provider is this service's responsibility" split with `execute_image()`'s fallback-only filtering) |
| Empty `text` | `GeminiProvider.generate_speech()` raises `ProviderConfigurationError`, mirroring `generate_image()`'s `number_of_images` validation pattern |
| Missing `audio_model` config | `ProviderConfigurationError`, mirrors `generate_image()`'s missing-`image_model` case exactly |
| Auth rejected | `ProviderAuthenticationError` (existing, unchanged) |
| Rate limit | `ProviderRateLimitError` (existing, unchanged; fallback-eligible) |
| Timeout | `ProviderTimeoutError` (existing, unchanged; fallback-eligible) |
| Network failure | `ProviderNetworkError` (existing, unchanged; fallback-eligible) |
| Audio model not found (404) | `ProviderUnavailableError`, mirrors `_parse_image_response()`'s existing 404 handling (fallback-eligible) |
| Malformed/empty response | `ProviderUnavailableError`, mirrors `_extract_images()`'s "no data in response" idiom (fallback-eligible) |
| Every fallback candidate exhausted | Reported via `SpeechProviderRequestOutcome.error`, mirroring `_run()`'s existing aggregation exactly |

No new error type is introduced anywhere in this design — every case
above reuses an existing `ProviderError` subtype from
`src/core/ai/provider.py`.

## 19. Security

- API key handling: unchanged, reuses `providers.gemini.api_key`
  exactly as `generate_image()` already does; never logged (existing
  `configuration()` convention already excludes it).
- Logging: mirrors `generate_image()`'s logging exactly — provider
  name, model identifier, and latency are logged; **request `text`
  content and response audio bytes/base64 are never logged**, matching
  `generate_image()`'s precedent of never logging `prompt` or
  `data_base64` (spoken text can be at least as sensitive as an image
  prompt; the same discipline applies without needing a new rule).
- No temporary files: Section 9 keeps everything in-memory regardless
  of which binary-handling option is chosen.

## 20. Scope Boundaries

Explicitly NOT implemented by EP-084:

- Speech-to-text/transcription (Section 7 — belongs to EP-046's
  existing, unrelated offline architecture, not this content-
  generation track).
- General (non-speech) audio generation — music, sound effects,
  ambient audio (Section 7 — no provider in scope supports it; would
  require inventing undocumented behavior).
- Audio understanding/classification, voice cloning, speaker
  identification.
- Multi-speaker/dialogue synthesis (Gemini's `multiSpeakerVoiceConfig`
  — a real, documented capability, but a materially larger request
  contract than a v1 single-speaker `SpeechGenerationRequest` needs;
  deferred, not rejected, exactly as EP-083 deferred `size` forwarding
  rather than ruling it out forever).
- Persistent media storage / a media library.
- Audio editing, mixing, or waveform processing beyond the single,
  optional WAV-header attachment described in Section 9.
- Video generation (EP-085), presentation generation (EP-086), or the
  combined content pipeline (EP-087) — this design introduces no
  "UniversalContentGenerationService" or other abstraction that
  would implicitly pre-solve any of those.
- Any modification to EP-046/EP-047's offline voice skill (Section 6),
  EP-069.4's capability abstraction, `ProviderManager`, or
  `execute()`/`execute_image()`'s existing behavior.
- CLI/CommandRouter exposure (deferred to EP-087 or later, matching
  EP-082/083's own precedent).

## 21. Future EP Compatibility

`EP-085 — Video Generation Provider Integration` and
`EP-086 — Presentation Generation Integration` can each follow this
exact same mechanical pattern (`supports_<x>()`/`generate_<x>()` on
`AIProvider`, `execute_<x>()` on the executor via the existing generic
`_run()`, a new standalone `<X>GenerationService`, an additive config
namespace) without EP-084 needing to anticipate either — `_run()`
already accepts an arbitrary `request_fn`/`capability_filter` pair and
needs no further generalization to support a fourth or fifth modality.
`EP-087 — Content Production Pipeline` is expected to compose
`TextGenerationService`/`ImageGenerationService`/
`AudioGenerationService` (and whatever EP-085/086 add) from outside,
exactly as `EP083_DESIGN.md` already anticipated for image; nothing in
this design closes off that composition or requires EP-087 to reach
into any of these services' internals.

## 22. Testing Strategy

Mirrors `tests/EP083/test_image_generation_provider_integration.py`'s
coverage shape, applied to speech:

- `SpeechGenerationRequest`/`GeneratedAudio`/`SpeechGenerationResult`
  construction and immutability.
- `AIProvider` base `supports_speech_generation()` (False) /
  `generate_speech()` (raises `ProviderUnavailableError`) defaults,
  for every non-Gemini provider.
- `GeminiProvider.supports_speech_generation()` true/false based on
  `audio_model` configuration.
- `GeminiProvider.generate_speech()`: successful single-voice request;
  successful default-voice (no `voice`) request; `language` hint
  prompt-steering; `seed` forwarding; empty-`text` validation error;
  missing-`audio_model` configuration error; 404 "model not found";
  malformed/empty `inlineData`; auth/rate-limit/timeout/network error
  passthrough. If Section 9 Option B is approved: WAV-header
  correctness for at least one known sample rate, and the documented
  24000 Hz fallback when `mimeType` rate-parsing fails.
- `ProviderRequestExecutor.execute_speech()`: success; fallback across
  a capability-filtered candidate list; every candidate exhausted;
  non-fallback-eligible error stops immediately — mirrors
  `execute_image()`'s existing test list exactly.
- `AudioGenerationService.generate()`: disabled; no provider selected;
  AI subsystem disabled; capability mismatch (never reaches executor);
  success; executor failure passthrough; successful-outcome-with-
  `None`-result internal-error guard (mirrors `ImageGenerationService`'s
  own such guard and its EP-082 STEP 3 "no bare `assert`" precedent).
- Regression: `tests/EP083` (69 or 60, whichever is unaffected —
  actual current count TBD at STEP 2 time) and `tests/EP082` must
  remain fully green and untouched, exactly as EP-083 verified zero
  regression against EP-082.
- Bootstrap wiring: `audio_generation_service` constructed with
  config-driven `enabled`/`fallback_enabled`, sharing the existing
  `ai_request_executor` instance.

Not written during STEP 1, per this prompt's rule.

## 23. Dependency Analysis

No new dependency is required under either Section 9 option:

- `requests` — already a dependency, already used by `GeminiProvider`
  for every existing HTTP call.
- `wave` (Python standard library) — only needed if Section 9's Option
  B is approved; already available in every Python environment this
  project targets, requiring no addition to `requirements.txt`.

## 24. Alternatives Considered

Beyond Sections 7-9's explicit option analysis:

- **A separate `speech_generation.py`/`audio_generation.py` module
  split** (one file per verb) was considered against keeping
  everything under one `AudioGenerationService`/one config namespace.
  Rejected: EP-082/083 each keep one service per EP regardless of how
  many request/result types that EP introduces; there is exactly one
  request type here (`SpeechGenerationRequest`), so no split is
  warranted.
- **Introducing a `MediaGenerationService` base class** shared by
  `ImageGenerationService`/`AudioGenerationService` (both currently
  have near-identical bodies) was considered. Rejected per this
  prompt's own Section 20/6 instruction not to build abstractions
  merely because they could be useful later, and because EP-083 itself
  never introduced such a base class despite the same opportunity
  existing between `TextGenerationService`/`ImageGenerationService`.

## 25. Owner Decisions

Only the two genuine architecture choices this repository's own
evidence does not already settle:

- **D1 — Provider-method naming.** `generate_speech()`/
  `supports_speech_generation()` (recommended, Section 8) vs. a
  generic `generate_audio()`/`supports_audio_generation()` naming
  that would overstate the actual capability.
- **D2 — Binary result handling.** WAV-wrap the raw PCM into a
  directly playable container using the standard-library `wave`
  module (recommended, Section 9) vs. pass through Gemini's raw
  `audio/L16` bytes and `mime_type` unchanged, leaving WAV-wrapping to
  every future consumer independently.

Not asked as owner decisions (resolved from repository/provider
evidence directly): scope (Section 7 — TTS only, forced by actual
provider capability); executor integration shape (Section 13 —
mechanical repetition of `execute_image()`); service layer shape
(Section 14 — mechanical repetition of `ImageGenerationService`);
first provider (Section 15 — Gemini is the only candidate, exactly as
for EP-083); configuration structure (Section 16 — mechanical
repetition of `image_generation:`/`image_model`); persistence
(Section 9 — no persistence either way, matching `GeneratedImage`'s
settled precedent); multi-speaker/style parameters (Section 10/19 —
excluded on documented-API-shape grounds, not preference).

## 26. Acceptance Criteria (for STEP 2)

- `SpeechGenerationRequest`/`GeneratedAudio`/`SpeechGenerationResult`
  exist as frozen dataclasses with exactly the fields in Sections
  10-11 (adjusted only for whichever D1/D2 decision is made).
- `AIProvider.supports_speech_generation()`/`generate_speech()` exist
  with the exact default (non-overriding) behavior in Section 12;
  every existing provider remains a valid `AIProvider` with zero
  changes other than `GeminiProvider`.
- `ProviderRequestExecutor.execute_speech()` exists, delegates to the
  existing `_run()` helper unchanged, and `execute()`/`execute_image()`
  remain byte-identical in signature and behavior to their current
  form.
- `GeminiProvider.generate_speech()` implements the exact HTTP
  contract in Section 15, verified (not assumed) against Gemini's
  current TTS documentation at STEP 2 implementation time.
- `AudioGenerationService` exists, mirrors
  `ImageGenerationService`'s structure and failure-reporting
  convention exactly, and is wired in `Bootstrap` sharing the existing
  `ai_request_executor` instance, config-gated by
  `audio_generation.enabled`/`audio_generation.fallback_enabled`.
- No CommandRouter registration is added.
- `EP069_4`'s capability abstraction is untouched.
- `EP046`/`EP047`'s voice skill files are untouched.
- Full regression: `tests/EP083`, `tests/EP082`, `tests/EP069`,
  `tests/EP069_3`, `tests/EP069_4` all remain green with zero changes
  to their own test files.
- No new dependency is added to `requirements.txt`.
- No scope leakage into transcription, general audio generation,
  multi-speaker synthesis, persistence, or EP-085/086/087
  functionality (Section 20).

## 27. Status

```text
DESIGN PROPOSED — awaiting Owner Decision
```

Two genuine decisions require owner approval (Section 25, D1/D2);
every other design choice in this document is resolved directly from
repository conventions or from Gemini's documented, verified API
behavior and requires no further approval to proceed to STEP 2 once
D1/D2 are settled.
