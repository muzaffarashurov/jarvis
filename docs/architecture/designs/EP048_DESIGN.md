# EP-048 — Wake Word — Design Specification (STEP 1)

**Status:** STEP 1 COMPLETE — OWNER DECISIONS RESOLVED.
STEP 2 NOT STARTED. Implementation, tests, configuration, and
`requirements.txt` remain untouched. Section 9's seven Owner
Decisions were reviewed and approved by the project owner; their
resolution is recorded in Section 9a. STEP 2 begins only on
explicit owner instruction.

---

## 1. Purpose

Per `docs/architecture/JARVIS_ROADMAP.md`'s Phase 7 sequencing
(EP-046 Speech-to-Text ✓, EP-047 Text-to-Speech ✓, **EP-048 Wake
Word**, EP-049 Voice Assistant) and `docs/BACKLOG.md`'s own
statement of the next Engineering Package, EP-048 gives Jarvis the
ability to detect a spoken trigger phrase (e.g. "Hey Jarvis") from a
continuous audio stream, entirely offline, without transcribing or
acting on anything else that is said.

This is a narrow, single-responsibility capability: **detect the
wake phrase, report the detection.** It deliberately does **not**
build the "hear wake word → capture the following command →
transcribe → dispatch" assistant loop — that is EP-049's explicitly
named scope, one phase later, per the roadmap's own sequencing and
per EP-046_DESIGN.md/EP-047_DESIGN.md's repeated, explicit
non-goals ("no wake-word detection... that is EP-048", "no
always-on/continuous voice loop... that is EP-049").

## 2. Scope

### In scope (EP-048 v1)

* A `WakeWordEngine` interface and one concrete, offline
  implementation.
* A continuous/streaming microphone capture component, separate
  from `AudioCapture`'s existing fixed-duration, one-shot design
  (Section 5.3).
* Two new, additive actions on the existing `voice` `CommandModule`
  (`src/skills/voice/skill.py`): a foreground, blocking detection
  loop the operator explicitly starts, and a status/readiness
  check. No new command namespace.
* `Bootstrap` wiring: constructing the engine/stream and registering
  the new action(s), gated by configuration, degrading safely (never
  crashing) when the dependency, model files, or microphone are
  unavailable — the same idiom EP-046/EP-047 already established.
* Configuration additions under the existing `voice:` block in
  `config/config.yaml` (proposed in Section 8/9, not applied in
  STEP 1).

### Out of scope (EP-048 v1) — deferred to EP-049 or `docs/BACKLOG.md`

* Automatically triggering `voice listen`/transcription/dispatch
  when the wake word is detected. v1 only ever *reports* a
  detection — mirroring `voice transcribe`'s existing "never
  dispatch" precedent (`skill.py`).
* An always-on, Bootstrap-managed background listener that starts
  automatically when Jarvis starts. v1's detection loop is a
  foreground command the operator explicitly runs (Section 9,
  Decision D5).
* A full conversational/assistant loop, barge-in, or multi-turn
  interaction — `EP-049 Voice Assistant`, per roadmap.
* Training or shipping a custom Russian or Uzbek wake-word model
  (Section 9, Decision D2 — a disclosed v1 gap, not an oversight,
  mirroring EP-047's own Uzbek TTS gap).
* Any change to `CommandRouter`, `src/core/api/`, Telegram routing,
  `desktop/`, or `web/`.
* Any change to EP-046 (`speech_to_text.py`, the existing
  `AudioCapture.capture()` contract) or EP-047
  (`text_to_speech.py`) implementations.
* Voice Activity Detection / noise suppression tuning beyond
  whatever the chosen engine already does internally.
* Multiple simultaneous wake phrases, per-user/speaker
  verification, or wake-word retraining tooling.

## 3. Current architecture (repository findings)

### 3.1 The one true command entry point (unchanged from EP-046/047)

`src/core/command_router.py`'s `CommandRouter.dispatch()` is the
single entry point `InteractiveShell`, `TelegramRouter`, and
`ApiRouter` all already dispatch through. EP-048 introduces no
second dispatch mechanism and does not modify this file — consistent
with `AI_GENERATION_STANDARD.md`'s Public API Policy and the
project's "no duplicate responsibilities" rule.

### 3.2 `src/skills/voice/` today

```
src/skills/voice/
    audio_capture.py      (161 lines) — EP-046, fixed-duration mic capture
    speech_to_text.py     (386 lines) — EP-046, Vosk STT engine
    text_to_speech.py     (305 lines) — EP-047, pyttsx3 TTS engine
    skill.py               (312 lines) — VoiceModule, the "voice" CommandModule
    wake_word.py             (0 bytes) — empty placeholder, confirmed
                                          byte-identical since EP-046,
                                          reconfirmed untouched through
                                          EP-047 (EP046_DESIGN.md
                                          Section 3.2, EP047_DESIGN.md
                                          Section 3.2/17.3)
```

`wake_word.py` has been an intentional, empty placeholder since
EP-046 — both prior designs explicitly earmarked it for this EP
("`wake_word.py` ↔ EP-048") and neither implementation touched it.
This document is the first STEP 1 to actually define what belongs
there.

### 3.3 `VoiceModule` (`skill.py`) today

Implements the `CommandModule` protocol, namespace `"voice"`, with
five flat actions dispatched through an `_actions` dict: `help`,
`listen`, `transcribe`, `status`, `speak`. Constructor signature:

```python
def __init__(
    self,
    config: Config,
    command_router: CommandRouter,
    engine: SpeechToTextEngine,
    audio_capture: AudioCapture,
    tts_engine: TextToSpeechEngine | None = None,
) -> None:
```

`tts_engine` was added in EP-047 as an *optional*, defaulted
keyword argument specifically so no EP-046 call site or test needed
to change — the same additive-constructor pattern EP-048 should
reuse for its own new collaborators (Section 5.4, Section 9
Decision D5).

### 3.4 `AudioCapture` (`audio_capture.py`) today — the key constraint

`AudioCapture.capture()` is a **single, blocking, fixed-duration**
recording: `sounddevice.rec(frame_count, ...)` followed by
`sounddevice.wait()`, returning one `AudioCaptureResult` after
`voice.listen_duration_seconds` (default 5s) elapses. Its own
docstring is explicit that this is "v1... not silence-terminated,"
and it holds no notion of a start/stop lifecycle or of continuously
streaming short frames to a caller.

**Wake-word detection is architecturally a different shape of
problem**: it needs a continuous stream of short (tens-of-
milliseconds) audio frames, each scored independently and
indefinitely, until the operator stops listening — not "record N
seconds, then return." `AudioCapture` cannot be reused as-is for
this; see Section 5.3/9 Decision D4.

### 3.5 Configuration — the existing `voice:` block

`config/config.yaml`'s `voice:` block (lines 207–305) currently has
two independent sub-areas: the top-level STT keys (`enabled`,
`engine`, `languages`, `default_language`, `model_dir`,
`offline_only`, `device`, `sample_rate`,
`listen_duration_seconds`, `timeout_seconds`, `min_confidence`) and
a nested `tts:` block with its own `enabled` flag, independent of
the top-level one (EP-047 Owner Decision D6). No `wake:` sub-block
exists yet. Section 8 proposes one, following the same nested,
independently-gated pattern.

### 3.6 Testing convention (unchanged)

`tests/EP046/test_voice.py` and `tests/EP047/test_voice_tts.py`
each register a single, combined `TestRegistry` suite (`NAME =
"EP046"` / `"EP047"`) rather than separate Service/Module suites —
deliberately sidestepping the pre-existing `TestRegistry`
`NAME.upper()` collision technical debt recorded in
`docs/BACKLOG.md`. Both are fully deterministic: real hardware/model
dependence is isolated behind fakes conforming to the relevant
`Protocol`, with `self.skip()` reserved for the one scenario that
truly cannot be exercised without physical hardware or model files
present. EP-048 must follow the same pattern (Section 11).

### 3.7 Windows / Python environment (unchanged from EP-046/047)

Target is a Windows workstation, Python 3.12+, no native build
toolchain available — the reason `sounddevice` (prebuilt PortAudio
wheels) was chosen over `pyaudio` in EP-046, and a hard constraint
repeated in Section 7's technology evaluation below.

## 4. EP-048 objectives

1. Detect a configured wake phrase from a live, continuous
   microphone stream, entirely offline (no network call at
   detection time).
2. Report each detection (text output; no automatic dispatch),
   consistent with the "explicit, observable, never-silent" idiom
   `voice transcribe`/`voice status` already established.
3. Never crash `Bootstrap.initialize()` if the wake-word dependency,
   its model files, or the microphone are unavailable — the
   subsystem simply does not register, exactly as EP-046/EP-047
   already do for their own dependencies.
4. Introduce no new dispatch mechanism, no second command namespace,
   and no change to `CommandRouter`.
5. Keep the wake-word *engine* replaceable via configuration (a
   `Protocol`, not a hard-coded class) — mirroring
   `SpeechToTextEngine`/`TextToSpeechEngine`'s own "engine is a
   config value" precedent, specifically so a future EP could add a
   Russian/Uzbek-capable engine without touching `VoiceModule`.
6. Leave `EP-049 Voice Assistant`'s eventual "wake → listen →
   dispatch" loop buildable on top of this EP's output, without
   this EP building it.

## 5. Proposed architecture

### 5.1 Data flow

```
Microphone
   │
   ▼
StreamingAudioCapture (new, Section 5.3)
   │  short PCM frames, continuously, until stopped
   ▼
WakeWordEngine.process_frame() -> score  (new, Section 5.2)
   │
   ▼
score ≥ voice.wake.threshold ?
   │
   ├─ no  → keep listening
   └─ yes → WakeDetectionResult(detected=True, ...) → VoiceModule
               reports "Wake word detected" to the caller
               (never calls CommandRouter.dispatch() — Section 2)
```

This is the same "engine has no knowledge of `CommandRouter` or of
capture" separation EP-046/EP-047 already used for
`SpeechToTextEngine`/`TextToSpeechEngine` — `WakeWordEngine` only
turns audio frames into a score.

### 5.2 `WakeWordEngine` — the detection interface

A `Protocol`, mirroring `TextToSpeechEngine`'s role (Section 5.2 of
EP047_DESIGN.md): the seam through which the engine is replaceable
by configuration (`voice.wake.engine`) with no change to
`VoiceModule`.

```python
class WakeWordEngine(Protocol):
    @property
    def frame_length(self) -> int: ...   # samples expected per call

    @property
    def sample_rate(self) -> int: ...

    def process_frame(self, pcm_frame: bytes) -> float:
        """Return a 0.0-1.0 detection score for one audio frame."""
        ...
```

Exact method shape is confirmed during STEP 2 against the chosen
library's real API (Section 7); this is the STEP 1-level contract,
not final code.

### 5.3 `StreamingAudioCapture` — a new, separate component

Per Section 3.4/9 Decision D4: a **new** class in
`src/skills/voice/`, not a modification of `AudioCapture`.
Responsibilities: open an input stream (`sounddevice.InputStream`,
callback- or generator-based) at the wake engine's required frame
size/sample rate, yield frames until told to stop, and hold no
knowledge of `WakeWordEngine`, `CommandRouter`, or Jarvis commands —
matching `AudioCapture`'s own "only turns a microphone into PCM
bytes" boundary. Its lifecycle (start/stop, run indefinitely) is
genuinely different from `AudioCapture.capture()`'s
call-and-return shape, which is exactly why it is a separate class
rather than a second method bolted onto `AudioCapture` — see
Section 9 Decision D4 for the alternative considered and rejected.

Reuses the same configuration precedent as `AudioCapture`
(`voice.device`, a sample rate) rather than inventing a parallel
set of device-selection keys.

### 5.4 `VoiceModule` — additive extension, not a rewrite

Two new actions, added to the existing `_actions` dict exactly as
EP-047 added `"speak"` — no change to the module's existing
`help`/`listen`/`transcribe`/`status`/`speak` behavior, no change to
`CommandModule`'s interface:

* `voice wake listen` — starts the continuous detection loop in the
  foreground; runs until interrupted (Ctrl+C) or a configured
  timeout; prints each detection as it happens; never calls
  `CommandRouter.dispatch()` (Section 2, Section 9 Decision D5).
* `voice wake status` — reports engine/model readiness and the
  configured wake phrase(s)/threshold, mirroring `voice status`'s
  existing shape for STT.

New constructor parameter `wake_engine: WakeWordEngine | None =
None` (and a streaming-capture collaborator), **optional and
defaulted to `None`**, exactly as `tts_engine` was added in EP-047 —
every existing EP-046/EP-047 call site and test keeps working
unmodified. `voice wake *` reports a clear failure (never a crash)
when `wake_engine` is `None`, the same shape `_speak` already uses
when `tts_engine` is `None`.

Sub-command dispatch (`listen`/`status` as a first argument to the
`wake` action) is new to `VoiceModule` — every existing action is
currently flat. This is a small, additive pattern, not a second
routing mechanism: `_wake(arguments)` inspects `arguments[0]`
exactly the way `_listen`/`_transcribe` already inspect their own
optional first argument for a language code.

### 5.5 Failure behavior

Every expected failure (dependency not importable, model files
missing/invalid, no input device, stream error) is reported via a
result object's `success`/`detected` field or a `CommandResult`
with `success=False` — never raised as an exception past
`process_frame()`/the streaming capture's `start()` — the same
"never raises for an expected failure" idiom `TranscriptionResult`/
`SynthesisResult` already establish (Section 5.4 of both prior
designs).

## 6. Integration points

`Bootstrap.initialize()` (`src/bootstrap.py`) already has a
precedent-setting block for `voice.*` (STT) and `voice.tts.*` (TTS),
each independently gated and each degrading safely
(Section 1487–1562 of the current file). EP-048 adds a third,
similarly-shaped, independently-gated block for `voice.wake.*`:
construct the engine and the streaming-capture component inside
their own `try`/`except`, log and set the corresponding attribute to
`None` on any expected failure, and pass both into `VoiceModule`'s
already-additive constructor.

The one integration question this EP must resolve, and cannot
silently decide, is the **outer registration gate**: `VoiceModule`
today is registered only when `voice.enabled` (STT) is `True` — a
disclosed, as-built limitation from EP-047 (`docs/BACKLOG.md`'s
EP-047 entry: "the `voice` namespace itself remains registered only
when `voice.enabled` (STT) is also true"). Whether EP-048 inherits
this same limitation for `voice wake`, or fixes the gate to register
`VoiceModule` when *any* of `voice.enabled` /
`voice.tts.enabled` / `voice.wake.enabled` is true, is Section 9
Decision D6 — it touches `Bootstrap`'s existing wiring shape beyond
pure, uncontested addition, so it is not decided here.

No other integration point changes: `src/core/api/`, Telegram,
`desktop/`, `web/`, and `CommandRouter` itself are all untouched by
this design.

> **Implemented As (STEP 2):** Owner Decision D6 (Section 9a)
> resolved "fix the registration architecture... do not preserve the
> current STT-only registration limitation." As actually wired,
> `Bootstrap.initialize()` registers `VoiceModule` when *any* of
> `voice.enabled` / `voice.tts.enabled` / `voice.wake.enabled` is
> true — this required also making `VoiceModule`'s `engine` and
> `audio_capture` constructor parameters `Optional` (previously
> required), with `_listen`/`_transcribe`/`_status` each gaining a
> `None`-guard mirroring `_speak`'s pre-existing pattern. This is a
> **full** implementation of D6, not a partial one: unlike EP-047's
> own disclosed "TTS-only operation is not supported" gap
> (`EP047_AUDIT.md` Known Limitations), EP-048 closes that gap
> entirely — STT-only, TTS-only, and Wake-Word-only operation are
> all independently reachable, each confirmed by a dedicated
> Bootstrap-wiring test (`EP048_AUDIT.md` Section 5/11). EP-046's and
> EP-047's own already-shipped behavior is unchanged when their own
> flags are enabled exactly as before (confirmed: their own test
> suites pass unmodified).

## 7. Technology evaluation

| Candidate | Offline at runtime | Windows | Streaming/continuous | Russian | Uzbek | License | Model acquisition | Notes |
|---|---|---|---|---|---|---|---|---|
| **openWakeWord** | Yes (after one-time model file setup) | Yes — `onnxruntime`-only path on Windows (project's own README: tflite is not supported/available on Windows, ONNX is the default there) | Yes — designed for per-frame (~80 ms) streaming scoring | No off-the-shelf model | No off-the-shelf model | Apache-2.0 | Shared feature-extraction models + per-phrase classifier heads, `.onnx` files, normally fetched once via `openwakeword.utils.download_models()` — can instead be placed manually (Section 9 Decision D3) | Ships a pre-trained **"hey jarvis"** model out of the box; requires `python_requires >= 3.10` (satisfied by the project's Python 3.12+ target); no per-language STT-style model directory structure — a different acquisition shape than Vosk's, worth documenting clearly for the operator |
| **Picovoice Porcupine** | No — every SDK call requires a valid Picovoice `AccessKey`, obtained from and periodically re-validated against Picovoice's own servers ("online activation") | Yes | Yes | Not evaluated (moot, see below) | Not evaluated (moot, see below) | Proprietary/commercial core (some SDK glue is Apache-2.0, the engine itself is not) | Cloud account + AccessKey; **Picovoice has announced its Free Tier AccessKeys stop working after June 30, 2026** | Disqualified for this project on two independent grounds: (1) it is not genuinely offline — it depends on an external account/activation service, contradicting `voice.offline_only: true`'s existing philosophy and every prior EP's "no cloud" framing; (2) the free tier this project would need is being discontinued, making it an actively-expiring dependency to adopt today |
| **Vosk + restricted grammar (keyword-spot) on top of the existing EP-046 engine** | Yes — no new dependency at all | Yes (already proven) | Only by repeatedly re-running short capture-and-transcribe cycles — not true continuous frame-level scoring | Yes (existing model) | Yes (existing model) | Apache-2.0 (already in use) | None — reuses EP-046's already-installed models | Attractive for "zero new dependency" and Russian/Uzbek support, but architecturally the wrong shape: it re-purposes a full STT engine as a keyword spotter, is heavier per frame than a purpose-built wake-word model, blurs `SpeechToTextEngine`'s single responsibility (Section 3.4 of EP046_DESIGN.md), and Vosk's own recognizer is not designed for tight, low-latency continuous scoring loops. Recorded here as the "no new dependency" alternative, not recommended (Section 9 Decision D1) |
| **Mycroft Precise** | Yes | Uncertain / not actively verified for modern Windows+Python 3.12 | Yes (designed for it) | No | No | Apache-2.0 | Manual | Project (and its parent, Mycroft AI) is effectively dormant; not a safe technology bet for new v1 work in 2026 |
| **Snowboy** | Yes | Historically yes, unmaintained since | N/A | N/A | N/A | N/A | N/A | Discontinued/archived years ago; excluded outright |

## 8. Recommended approach

**openWakeWord**, used only for its detection role (Section 5.1/5.2),
with:

* A new `StreamingAudioCapture` component (Section 5.3), not a
  modification of `AudioCapture`.
* Model files (shared feature-extraction models + the "hey jarvis"
  classifier head) placed manually under a new `voice.wake.model_dir`
  configuration key, mirroring Vosk's own "manual install, no
  automatic downloader" precedent (EP-046 Owner Decision 10) rather
  than calling `openwakeword.utils.download_models()` at runtime.
* A new, independent `voice.wake.enabled` flag and nested `wake:`
  config sub-block, mirroring `tts:`'s existing shape.
* v1 ships with English wake-phrase detection only
  ("hey jarvis" — thematically apt, and the one pre-trained model
  requiring no custom training). Russian and Uzbek wake-phrase
  detection is an explicitly disclosed v1 gap (Section 9 Decision
  D2), the same disclosure pattern already used for EP-047's Uzbek
  TTS gap — not a silent omission.

This is proposed, not decided — see Section 9.

## 9. Owner decisions required

Per this task's own instruction ("Do not silently make significant
architectural decisions on behalf of the owner. Present the
recommended option and alternatives."):

| # | Decision | Options | Recommended | Reason | Impact |
|---|---|---|---|---|---|
| D1 | Wake-word engine | (a) `openWakeWord`; (b) Picovoice Porcupine; (c) Vosk-based restricted-grammar keyword spotting (no new dependency); (d) Mycroft Precise | **(a)** | Purpose-built for streaming frame-level detection, genuinely offline once model files are in place, Apache-2.0, Windows-viable via prebuilt `onnxruntime` wheels (no build toolchain, matching the project's existing dependency preference), and ships a pre-trained "hey jarvis" model. (b) is disqualified by its online-activation requirement and its free tier's announced June 30, 2026 discontinuation. (c) blurs `SpeechToTextEngine`'s single responsibility and is architecturally a worse fit for continuous scoring. (d) is an effectively dormant project. | Determines `wake_word.py`'s implementation, the new dependency in `requirements.txt`, and Section 7's full evaluation. |
| D2 | Russian/Uzbek wake-phrase gap | (a) Ship v1 with English-only wake-phrase detection, explicitly documented as not covering Russian/Uzbek; (b) invest in training a custom Russian and/or Uzbek wake-word model (via openWakeWord's synthetic-data training pipeline) before shipping v1; (c) fall back to Vosk keyword-spotting (option D1-c) specifically to keep Russian/Uzbek coverage, accepting its architectural downsides | **(a)** | No off-the-shelf model exists for either language today; (b) is open-ended, unbounded research effort with no guaranteed quality outcome, not appropriate to bundle into v1's critical path; (c) reintroduces D1's rejected architecture just to chase language coverage. Mirrors EP-047 Owner Decision D2's own reasoning and resolution for the identical Uzbek-TTS situation. | Determines `voice.wake.phrase`/`voice.wake.model`'s v1 contents and a disclosed, documented limitation either way. |
| D3 | Model file acquisition | (a) Manual placement under `voice.wake.model_dir`, no automatic downloader (mirrors Vosk/EP-046 Owner Decision 10); (b) call `openwakeword.utils.download_models()` automatically the first time `voice.wake.enabled` is true, fetching files over the network at runtime | **(a)** | Consistent with the project's one existing precedent for model-backed offline engines (Vosk); keeps `voice.offline_only: true` meaningful — a Bootstrap-time network call the first time a feature is enabled would be a new, undisclosed category of behavior for this project. (b) is materially more convenient for a first-time operator, which is a real, non-trivial cost of (a). | Determines the wake-word onboarding/setup documentation and whether `Bootstrap.initialize()` can ever make an outbound network call (currently: never, for any voice subsystem). |
| D4 | Streaming capture component shape | (a) A new, separate `StreamingAudioCapture` class in `src/skills/voice/`, leaving `AudioCapture` completely untouched; (b) add a second method (e.g. `AudioCapture.stream()`) to the existing `AudioCapture` class alongside its current `capture()` | **(a)** | `AudioCapture.capture()`'s contract (single blocking call, fixed duration, one `AudioCaptureResult` returned) is exercised by existing EP-046 tests and real EP-046 behavior; a `stream()` method would give the same class two materially different lifecycles (call-and-return vs. start/stop-and-run-indefinitely), which is a Single-Responsibility violation `AI_GENERATION_STANDARD.md`'s Architecture Rules (Rule: prefer extension over modification, avoid growing an existing class's responsibilities) would flag. (b) has a smaller total line count but risks EP-046 regressions from touching an already-COMPLETE EP's file. | Determines whether `src/skills/voice/audio_capture.py` is touched at all in STEP 2 (recommended: no) and what new file(s) STEP 2 creates. |
| D5 | How detection surfaces / auto-dispatch | (a) `voice wake listen` — foreground, blocking, operator-initiated; reports detections as text; never calls `CommandRouter.dispatch()`; (b) same, but on detection automatically starts a `voice listen` cycle (STT capture → transcribe → dispatch) — effectively pulling EP-049's core loop forward into EP-048; (c) a `Bootstrap`-managed, always-on background thread/listener that starts automatically whenever `voice.wake.enabled` is true, independent of any CLI command | **(a)** | Matches the roadmap's own phase boundary — Wake Word (EP-048) and Voice Assistant (EP-049) are deliberately separate Engineering Packages: EP-046/EP-047 explicitly named the full wake→listen→dispatch loop as EP-049's scope, not EP-048's, and this project's `AI_DEVELOPMENT_PLAYBOOK.md` instructs "implement only the current EP." (b) would silently expand EP-048 into EP-049's stated territory. (c) introduces this project's first-ever Bootstrap-managed background thread — a materially larger architectural commitment (thread lifecycle, shutdown behavior, concurrent microphone access from other interfaces) that deserves its own dedicated design pass, very plausibly as part of EP-049 itself, not as a rider on EP-048. | Determines whether EP-048 introduces any background threading into `Bootstrap` (recommended: no) and what, precisely, `voice wake listen` does and does not do. |
| D6 | `VoiceModule` registration gate | (a) Fix the existing gate so `VoiceModule` registers when *any* of `voice.enabled` / `voice.tts.enabled` / `voice.wake.enabled` is true (resolves EP-047's already-disclosed "TTS-only operation is not supported" gap as a side effect); (b) leave the current gate as-is (`voice.enabled` only) and require STT to also be enabled for `voice wake` to be reachable, inheriting the same disclosed limitation EP-047 has today | **(a)**, but flagged rather than silently applied, because it changes `Bootstrap`'s existing, already-COMPLETE EP-047 wiring shape, not just adds to it | (a) is the more correct long-term shape and directly closes a gap `EP047_AUDIT.md`/`docs/BACKLOG.md` already recorded as a known, non-blocking limitation; (b) is the more conservative, strictly-additive change (touches nothing EP-047 already shipped) but means an operator who wants wake-word detection without STT enabled cannot get it, and compounds a second Voice sub-feature into the same restrictive gate. | Determines the exact `if`/`elif` shape of the relevant `Bootstrap.initialize()` block (Section 6) and whether this EP quietly touches EP-047-authored wiring or leaves it alone. |
| D7 | Command naming | (a) `voice wake listen` / `voice wake status` (one new `wake` action with a sub-argument, Section 5.4); (b) two new flat actions, e.g. `voice wakelisten` / `voice wakestatus`; (c) a fully separate namespace, e.g. `wake listen` (rejected by Section 2's "no new namespace" non-goal, listed only for completeness) | **(a)** | Reads naturally next to the existing `voice listen`/`voice transcribe` pair; avoids the awkward concatenated verbs of (b); (c) already conflicts with this EP's own non-goals. Introducing one level of sub-argument dispatch inside a single `wake` action is a small, contained addition to `VoiceModule`, not a new routing mechanism. | Cosmetic but flagged for the same reason EP-046 Owner Decision 8 and EP-047 Owner Decision D8 flagged their own action names — cheaper to confirm now than rename after STEP 2, per `AI_GENERATION_STANDARD.md`'s Public API Policy. |

None of these seven items is silently decided by this document.

## 9a. Owner Decisions (received prior to STEP 2) — Resolution of Section 9

The project owner reviewed and approved EP-048 STEP 1 with the
following decisions. STEP 2 has **not** started; these decisions
govern it once it does.

| # | Question | Owner Decision |
|---|---|---|
| D1 | Wake-word engine | **`openWakeWord`**, confirming Section 9's recommendation. It must sit entirely behind the `WakeWordEngine` interface (Section 5.2) — `VoiceModule` must never be coupled directly to `openWakeWord`'s own API, mirroring the "engine is a config value, not a hard-coded assumption" property `SpeechToTextEngine`/`TextToSpeechEngine` already established. |
| D2 | Russian/Uzbek wake-phrase gap | **English-only "Hey Jarvis" for EP-048 v1.** Russian and Uzbek wake-word support are **out of scope**. No translation layer, cloud fallback, hidden multilingual workaround, or custom model training may be introduced to cover them in this EP. The limitation must be **explicitly documented** (in `config/config.yaml`'s comments and this document's STEP 2/3 as-built summary), not silently absent — the same disclosure standard EP-047 Owner Decision D2 already set for Uzbek TTS. |
| D3 | Model file acquisition | **Manual model placement.** `openwakeword.utils.download_models()` (or any equivalent automatic, network-dependent acquisition) must **not** be called at runtime. Model files are placed under `voice.wake.model_dir` by the operator, following the same manual-installation precedent EP-046 Owner Decision 10 already established for Vosk models. `Bootstrap.initialize()` must not make an outbound network call for any voice subsystem, now or after EP-048. |
| D4 | Streaming capture component shape | **A new, separate `StreamingAudioCapture` component**, confirming Section 9's recommendation. `AudioCapture` (`audio_capture.py`) must not be modified, and its existing fixed-duration `capture()` behavior must remain fully regression-compatible — verified in STEP 2/3 by confirming `audio_capture.py` is byte-identical to its pre-EP-048 state, exactly as EP-047 verified for `wake_word.py`. |
| D5 | How detection surfaces / auto-dispatch | **Detection only.** EP-048 must **not**: automatically dispatch commands through `CommandRouter`; automatically start an STT (`voice listen`) cycle after a detection; create a permanent/always-on background listener; introduce any wake-word service or daemon; or pull any part of EP-049's wake→listen→dispatch loop forward into this EP. `voice wake listen` remains a foreground, operator-initiated, blocking command that only reports detections, confirming Section 9's recommended option (a). EP-049 owns the next-stage flow in full. |
| D6 | `VoiceModule` registration gate | **Fix the registration architecture** so Speech-to-Text, Text-to-Speech, and Wake-Word can each be enabled independently — the current STT-only gate must not be preserved if it would prevent TTS-only or Wake-Word-only operation. This is an explicitly authorized, minimal, additive correction (not unrelated refactoring): EP-046's and EP-047's own existing, already-shipped behavior must be fully preserved as-is when their respective flags are enabled exactly as before. EP-047's TTS-only limitation was already recorded as a disclosed, non-blocking as-built limitation (`docs/BACKLOG.md`, `EP047_AUDIT.md`), so EP-048 is authorized to close it as a side effect of this fix, per Section 9's option (a). |
| D7 | Command naming | **`voice wake listen`** and **`voice wake status`**, confirming Section 9's recommendation. Both live under the existing `voice` `CommandModule` namespace — no new command namespace is created. |

All seven Section 9 questions are now resolved; none remains open
from the original list.

**Confirmed non-goals (restated, not new — consistent with Section
2/14):** no auto-dispatch on detection, no automatic STT trigger, no
permanent background listener or daemon, no EP-049 functionality of
any kind, no Russian/Uzbek wake-word support, no automatic/network-
dependent model download, no new command namespace, no change to
`CommandRouter`, `src/core/api/`, Telegram, `desktop/`, or `web/`,
and no modification of `AudioCapture`'s existing behavior.

**STEP 1 boundary maintained while resolving these decisions:** no
file under `src/`, `tests/`, or `config/` was modified, and
`requirements.txt` was not modified, to produce this resolution.
STEP 2 has not started and begins only on the owner's explicit
instruction.

---

## 10. Security and reliability

* No network access at detection time under any configuration —
  `openWakeWord`'s inference is fully local once model files exist
  on disk (Section 9 Decision D3 governs whether *acquiring* those
  files ever touches the network, and if so, only once, manually,
  outside of any Jarvis process).
* No credentials, API keys, or account/activation state of any kind
  are introduced by the recommended engine — a direct, deliberate
  contrast with the rejected Porcupine alternative (Section 7).
* Every expected failure path (missing dependency, missing/invalid
  model files, no input device, stream error) degrades to "wake-word
  detection disabled" with a clear log message — never a crash of
  `Bootstrap.initialize()`, matching EP-046/EP-047 Section 5.4's
  established idiom (Section 5.5 above).
* `voice wake listen` claims the microphone as a hardware resource
  for as long as it runs, exactly as `voice listen`/`voice
  transcribe` already do for the duration of one fixed-length
  capture — this EP does not introduce any new class of resource
  contention beyond "one voice operation active at a time," and does
  not attempt to solve concurrent multi-interface microphone access
  (Section 15 Risks).

## 11. Testing strategy

Follows Section 3.6's established convention exactly:

* A single, combined `TestRegistry` suite, `NAME = "EP048"`, in
  `tests/EP048/test_wake_word.py` (created in STEP 2/3, not STEP 1),
  imported by `src/modules/test_module.py` alongside the existing
  EP046/EP047 imports.
* `WakeWordEngine` is a `Protocol` (Section 5.2) — tests exercise a
  fake implementation for all detection-logic and `VoiceModule`
  integration scenarios, needing no real model files or microphone.
* `StreamingAudioCapture`'s construction-time validation (bad
  config, no `sounddevice` device) is exercised directly against the
  real class wherever it does not require an actual physical input
  device to be present in the test environment — mirroring how
  `AudioCapture`'s own "no input device" graceful-failure path is
  already tested for real today (Section 3.6).
* One scenario — an actual wake phrase detected from a real audio
  clip through the real, loaded `openWakeWord` model — is expected
  to be reported via `self.skip()`, not silently omitted, exactly as
  EP-046's "no Vosk model files present" scenario is skipped today
  (`docs/BACKLOG.md`'s EP-046 entry, `EP046_AUDIT.md` Section 14).
  This is the first manual-verification item once EP-048 reaches
  real hardware — the same category of disclosed gap EP-046 and
  EP-047 each already carry for their own hardware-dependent
  scenarios.
* `Bootstrap` wiring tests: `voice.wake.enabled` true/false/absent,
  and an invalid/missing `voice.wake.model_dir`, must all degrade
  safely with no crash and (per whichever of Section 9 Decision D6's
  options the owner selects) the correct, corresponding registration
  outcome for `VoiceModule`.
* Existing EP-043 through EP-047 suites must remain unchanged and
  passing, per this task's own hard constraint (Section 12).

## 12. STEP 1 / STEP 2 boundary

STEP 1 (this document) performed only reading, analysis, research,
and this document's own creation/update of `docs/BACKLOG.md`. It did
**not**:

* Create or modify any file under `src/`.
* Create or modify any file under `tests/`.
* Modify `config/config.yaml`.
* Modify `requirements.txt`.
* Modify `src/skills/voice/wake_word.py` — it remains the empty,
  0-byte placeholder it has been since EP-046.
* Modify any EP-043–EP-047 implementation, design, or audit
  document.
* Modify `docs/architecture/JARVIS_ROADMAP.md`.
* Start STEP 2.

STEP 2 (implementation) has not begun and must not begin until the
owner has resolved Section 9.

## 13. Acceptance criteria (for STEP 2, not yet met)

* `WakeWordEngine` `Protocol` and one concrete implementation exist
  in `src/skills/voice/wake_word.py`, filling the placeholder;
  construction fails safely (a dedicated exception type, mirroring
  `SpeechToTextEngineError`/`AudioCaptureError`/
  `TextToSpeechEngineError`) for every expected failure mode.
* `StreamingAudioCapture` (Section 5.3, per Decision D4) exists as
  its own class; `AudioCapture` (`audio_capture.py`) is confirmed
  byte-identical to its pre-EP-048 state.
* `VoiceModule` gains `wake listen`/`wake status` additively
  (Section 5.4); `HELP_TEXT` is updated; every existing EP-046/
  EP-047 action, and every existing EP-046/EP-047 test, is
  unaffected.
* `Bootstrap.initialize()` wires the new engine/capture components
  under the config gate the owner selects in Decision D6, with
  independent `try`/`except` handling, never raising past
  `initialize()`.
* No automatic `CommandRouter.dispatch()` call exists anywhere in
  the new code — confirmed by a dedicated test, mirroring the
  precedent EP-047 Owner Decision D4 established for `voice speak`.
* `tests/EP048/test_wake_word.py` registers a single `EP048` suite;
  `test EP048` reports Passed > 0, Failed = 0, Skipped = 0 except
  the one disclosed real-hardware/real-model scenario (Section 11).
* Full suite (`test all`) remains at its current pass count plus
  EP-048's new tests, with no regression in EP-001 through EP-047.
* The Russian/Uzbek wake-phrase gap (Decision D2) is explicitly
  documented in `config/config.yaml`'s comments and in this
  document's own STEP 2/3 as-built summary, not silently absent.
* `requirements.txt` gains exactly the new dependency Decision D1
  requires, with a comment explaining its purpose — mirroring the
  existing Vosk/sounddevice/pyttsx3 comment style.

## 14. Out-of-scope items (explicit)

Restated from Section 2, for STEP 3 audit convenience:

* Auto-dispatch on wake detection (Decision D5(b)) — none.
* Any Bootstrap-managed background/always-on listener (Decision
  D5(c)) — none.
* Any part of EP-049's conversational/assistant loop.
* Russian or Uzbek wake-phrase detection (Decision D2) — disclosed
  gap, not built.
* Any change to `src/core/api/`, Telegram, `desktop/`, or `web/`.
* Any change to EP-046/EP-047 implementation files.
* Voice Activity Detection tuning, noise-suppression configuration,
  or multi-wake-phrase support beyond whatever the chosen engine
  does by default.
* Automatic model downloading at runtime (Decision D3(b)) — unless
  the owner selects it, in which case this line is revisited at
  STEP 2.

## 15. Risks / limitations

* **First-ever continuous/long-running foreground audio operation
  in this project.** `voice listen`/`voice transcribe` block for a
  few seconds; `voice wake listen` (Decision D5(a)) blocks
  indefinitely until interrupted. This is a materially different
  usage pattern for the `InteractiveShell` even though it introduces
  no new *architecture* (no threading, no Bootstrap change beyond
  registration) — worth calling out explicitly rather than treating
  as "just another blocking command."
* **Model acquisition is a different shape than Vosk's.** Vosk uses
  one self-contained model directory per language under
  `voice.model_dir`. `openWakeWord` needs both shared
  feature-extraction models and a separate per-phrase classifier
  head, normally fetched by a helper function rather than downloaded
  as a single archive per language. If Decision D3(a) (manual
  placement) is selected, onboarding documentation must be precise,
  or `voice wake` will silently be unavailable to an operator who
  reasonably believed they had "installed the model" — the same
  class of risk EP-046 already carries for Vosk, now doubled across
  two model-acquisition shapes in the same `voice:` config block.
* **Unverified accuracy on real hardware.** False-accept/false-reject
  rates for a non-native English speaker (this project's owner is
  based in Uzbekistan, per `docs/architecture/PROJECT_OVERVIEW.md`'s
  general framing) triggering an English-only "hey jarvis" phrase,
  in a real acoustic environment, are unknown until manual
  verification — the same category of gap EP-046 and EP-047 each
  disclosed and left as their own "first manual-verification item."
* **Dependency footprint.** `onnxruntime` (openWakeWord's runtime
  dependency) is a meaningfully larger wheel than `vosk` or
  `sounddevice`. It is expected to install cleanly alongside the
  project's existing dependencies (including `PySide6`, `pandas`,
  `openpyxl`) via prebuilt wheels, but this is unverified until
  STEP 2 actually runs `pip install` in the target environment.
* **Windows/tflite is a non-issue, not a risk** — openWakeWord's own
  README already documents that Windows uses the `onnxruntime` path
  exclusively (no `tflite-runtime` availability on Windows), which
  is also this design's only supported path (Section 7) — recorded
  here so a future contributor does not attempt to force a
  TensorFlow Lite path on the target workstation.
* **`TestRegistry` NAME-collision debt.** Unaffected by this EP —
  EP-048 follows EP-043/045/046/047's precedent of registering one
  combined suite, sidestepping rather than fixing the pre-existing
  debt item `docs/BACKLOG.md` already tracks separately.

## 16. Recommended implementation sequence (for STEP 2, contingent on owner approval)

1. Update `requirements.txt` with the Decision-D1 dependency and a
   precise, dated comment (mirroring the existing Vosk/sounddevice
   block's comment style).
2. Per Decision D3, document and (if manual) perform model-file
   placement under the new `voice.wake.model_dir`.
3. Implement `WakeWordEngine` (`Protocol`) and the concrete engine
   class in `src/skills/voice/wake_word.py`.
4. Implement `StreamingAudioCapture` as its own new file/class in
   `src/skills/voice/` (Decision D4).
5. Extend `VoiceModule` (`skill.py`) additively: new optional
   constructor parameters, `wake` action with `listen`/`status`
   sub-dispatch, updated `HELP_TEXT` (Decision D7 naming).
6. Wire `Bootstrap.initialize()`: construct the new components under
   independent `try`/`except`, apply the registration-gate shape
   Decision D6 selects.
7. Add the `wake:` sub-block to `config/config.yaml`'s existing
   `voice:` section, with comment density matching the existing
   `tts:` block, including an explicit Russian/Uzbek gap note
   (Decision D2).
8. Write `tests/EP048/test_wake_word.py`; register it in
   `src/modules/test_module.py`; run `test EP048` only, fix every
   failing assertion, then run the full suite once (`test all`),
   per `AI_DEVELOPMENT_PLAYBOOK.md`'s Phase 3.
9. STEP 3: architecture audit (read-only), `docs/BACKLOG.md`/
   `CHANGELOG.md`/`docs/RELEASE_NOTES.md` updates, and this
   document's own as-built summary section — not started until
   STEP 2 is verified complete.

---

## 17. STEP 2/3 Implementation Summary (as-built)

This section records what was actually built, verified fresh at
STEP 3. It does not replace Sections 1-16 above — those remain the
STEP 1 design record and Section 9a's owner decisions exactly as
approved. Where the two differ, the difference is a deliberate,
explained refinement (Section 6's "Implemented As" note above), never
an undocumented substitution. Full verification evidence lives in
`docs/architecture/audits/EP048_AUDIT.md`; this section is the design
document's own summary of the same facts.

### 17.1 Implementation files

| File | Role |
|---|---|
| `src/skills/voice/wake_word.py` (new) | `WakeWordEngine` Protocol, `WakeWordDetectionResult`, `WakeWordEngineError`, `OpenWakeWordEngine` — fills the empty EP-046-era placeholder |
| `src/skills/voice/streaming_audio_capture.py` (new) | `StreamingAudioCapture`, `StreamingCaptureStartResult`, `StreamingAudioCaptureError` — separate from `AudioCapture` (Decision D4) |
| `src/skills/voice/skill.py` | `VoiceModule` — additive: `wake_engine`/`wake_capture` optional constructor parameters; `engine`/`audio_capture` widened to `Optional` (required by D6's full-independence fix); `wake` action with `listen`/`status` sub-dispatch; `_wake_listen`/`_wake_status` methods; `_listen`/`_transcribe`/`_status` gained `None`-guards; updated `HELP_TEXT` |
| `src/bootstrap.py` | Additive: `WakeWordEngine`/`StreamingAudioCapture`-related imports; `self._voice_wake_engine`/`self._voice_wake_capture` attributes; registration condition widened to `voice_enabled or voice_tts_enabled or voice_wake_enabled` (Section 6's "Implemented As" note); each of STT/TTS/Wake constructed independently in its own `try`/`except`; two new properties |
| `config/config.yaml` | New `voice.wake:` block (Section 8), nested under the existing `voice:` key, disabled by default; corrected the now-stale EP-047 "TTS-only not supported" comment to reflect the D6 fix |
| `requirements.txt` | `openwakeword==0.6.0` added, with a dated, rationale-bearing comment (Decision D1/D3) |
| `src/modules/test_module.py` | One registration import line (`import tests.EP048.test_wake_word`) — the same mechanical addition every prior EP's test suite required |
| `tests/EP048/__init__.py`, `tests/EP048/test_wake_word.py` | `TestRegistry`-registered suite, `NAME = "EP048"`, 33 test methods covering the 25 required scenarios |

### 17.2 Technology (Owner Decision D1, Section 9a)

`openwakeword` **0.6.0**, added to `requirements.txt`. Confirmed
importable and functionally exercised in the verification
environment (construction-time validation paths — missing
`model_dir`, missing model files, invalid `wake_word`/`threshold` —
all run against the *real* `OpenWakeWordEngine` class, not a fake).

**Environment-dependent installation note (disclosed, not hidden):**
`openwakeword==0.6.0`'s own PyPI metadata hard-requires
`tflite-runtime` on Linux, for which no installable wheel exists in
the Linux verification environment used across STEP 2/3. This was
worked around, for verification purposes only, via `pip install
--no-deps` plus manually installing `openwakeword`'s actual runtime
dependencies (`onnxruntime`, `tqdm`, `requests`, `scipy`,
`scikit-learn`). This does not affect the actual Windows target — the
Windows path never depends on `tflite-runtime` in the first place
(Section 7's own technology evaluation) — but a plain `pip install -r
requirements.txt` on the real target remains unverified until it is
actually run there (Section 17.6).

Wake phrase actually configured (`config/config.yaml`,
`voice.wake.wake_word`): **`hey_jarvis`** (English only), matching
Section 8's proposal exactly. **Russian and Uzbek are deliberately
absent and explicitly out of scope**, per Owner Decision D2 — no
translation layer, cloud fallback, hidden multilingual workaround, or
custom model training exists anywhere in the implementation. This is
documented in `config/config.yaml`'s own comments, in
`wake_word.py`'s module docstring, and surfaced live in `voice wake
status`'s own output (`"Russian and Uzbek wake-word detection are out
of scope for EP-048"`).

### 17.3 Architecture (Section 5, confirmed unchanged)

`Microphone → StreamingAudioCapture → WakeWordEngine.process_frame()
→ WakeWordDetectionResult → VoiceModule reports the detection`,
implemented exactly as designed (Owner Decisions D1/D4/D5).
`src/core/command_router.py` and `src/skills/voice/audio_capture.py`
were **not modified** — confirmed byte-identical against the
pristine pre-EP-048 archive (`EP048_AUDIT.md` Section 4). `VoiceModule`
remains the only `CommandModule` for the `"voice"` namespace — no
second namespace, no parallel routing mechanism (Owner Decision D7).
`VoiceModule` depends only on the `WakeWordEngine` **protocol**,
never on `OpenWakeWordEngine` directly (confirmed by direct import
inspection: `skill.py` imports exactly `WakeWordEngine`, nothing
else, from `wake_word.py`) — the engine remains swappable via
`Bootstrap` wiring alone, satisfying Owner Decision D1's "must not
couple `VoiceModule` directly to `openWakeWord`" requirement.

Only `voice wake listen`/`voice wake status` were added (Owner
Decision D7). `voice wake listen` never calls
`CommandRouter.dispatch()`, never calls `AudioCapture.capture()` or
`SpeechToTextEngine.transcribe_audio()`, and never calls
`TextToSpeechEngine.synthesize()` — each confirmed by a dedicated
test using a call-counting fake collaborator, not merely by reading
the source (Owner Decision D5). No thread, background loop, or
daemon exists anywhere in `wake_word.py`, `streaming_audio_capture.py`,
or `skill.py`'s wake-related code (confirmed by direct search for
threading/daemon patterns — none found). `voice listen`, `voice
transcribe`, `voice status`, `voice speak`, and `voice help` are
unchanged in behavior for callers that still supply STT/TTS engines
(confirmed: `skill.py`'s diff against its EP-047-shipped state
contains zero altered lines in the pre-existing action bodies except
the `None`-guards Decision D6 required) and are covered by regression
tests in `tests/EP048/test_wake_word.py` in addition to their own,
still-passing `tests/EP046/test_voice.py`/`tests/EP047/test_voice_tts.py`
suites.

`voice.wake.enabled` defaults to `false` (`config/config.yaml`,
confirmed by a dedicated test reading the key's absence-default). No
EP-049 functionality (automatic STT-after-detection, automatic
dispatch, a conversational loop) was implemented anywhere in the
changeset.

### 17.4 Tests (as re-verified at STEP 3)

```
test EP048  →  Passed: 102   Failed: 0   Skipped: 1
test EP047  →  Passed: 49    Failed: 0   Skipped: 0
test EP046  →  Passed: 57    Failed: 0   Skipped: 1
test EP043  →  Passed: 83    Failed: 0   Skipped: 0
test EP044  →  Passed: 52    Failed: 0   Skipped: 0
test EP045  →  Passed: 38    Failed: 0   Skipped: 0
test all    →  Passed: 5757  Failed: 0   Skipped: 2
```

The two skips across the full suite are EP-046's own disclosed,
pre-existing real-microphone/real-loaded-Vosk-model gap (unchanged by
EP-048) and EP-048's own disclosed real-loaded-openWakeWord-model gap
(Section 17.6). `EP-039`/`EP-041` were also re-run in this STEP, both
individually (36/0/0 and 39/0/0) and as part of the full suite,
consistent with `EP047_AUDIT.md`'s own finding that their earlier-
documented baseline failures were an environment-dependent,
network-availability property, not a code regression either EP could
have caused — this verification environment has outbound network
access.

Manual real-microphone/real-"Hey Jarvis"-detection test at STEP 3
time: **NOT AVAILABLE** — no physical microphone and no openWakeWord
model files existed in the verification environment used across
STEP 1-3 of this EP. Not claimed as passed at that time.

> **Superseded (post-STEP-3):** this STEP-3-time gap has since been
> closed by real Windows hardware verification, which also surfaced
> and led to the correction of a real implementation defect. See
> Section 17.7 below for the full account — this paragraph is
> preserved unchanged as the honest, historical STEP-3-time record.

### 17.5 Owner decisions — implementation status

| # | Decision (Section 9a) | Status |
|---|---|---|
| D1 | `openWakeWord` behind `WakeWordEngine` | Implemented — protocol-only coupling confirmed (17.3) |
| D2 | English-only "Hey Jarvis"; Russian/Uzbek out of scope, no workaround | Implemented — no special-casing anywhere in code (17.2) |
| D3 | Manual model placement only, no automatic download | Implemented — no `download_models()` call, no network access anywhere in `wake_word.py` (confirmed by direct search) |
| D4 | New, separate `StreamingAudioCapture` | Implemented — `audio_capture.py` byte-identical to its pre-EP-048 state (17.3) |
| D5 | Detection only — no auto-dispatch/STT/TTS/daemon | Implemented — confirmed by dedicated call-counting tests (17.3) |
| D6 | Fix registration gate for independent STT/TTS/Wake enablement | **Fully** implemented — see Section 6's "Implemented As" note; closes EP-047's own disclosed partial gap too |
| D7 | Extend existing `voice` `CommandModule`, no new namespace | Implemented — `voice wake listen`/`voice wake status` only |

All seven decisions are implemented exactly as recorded, with no
silent reinterpretation and no partial/disclosed gap on any of them
— a stronger conformance result than EP-047's own D6 (Section 17.6).

### 17.6 Known limitations

- **`openwakeword==0.6.0` installation required a workaround in this
  verification environment** (Section 17.2) due to a Linux-only
  `tflite-runtime` dependency with no available wheel here — does not
  affect the Windows target's own dependency path, but a plain `pip
  install -r requirements.txt` on the real target workstation remains
  unverified.
- **RESOLVED (post-STEP-3) — see Section 17.7:** at STEP 3 time, no
  real microphone/real-"Hey Jarvis"-detection verification had been
  performed in any environment this project had run in (Section
  17.4) — construction-time validation (missing model directory,
  missing model files, invalid configuration) was exercised against
  the real `OpenWakeWordEngine` class; an actual loaded-model
  detection was not, and was not claimed as such at that time. Real
  Windows hardware verification has since confirmed detection works
  end to end, and also surfaced a real model-filename-resolution
  defect that has since been corrected. Full account in Section 17.7.
- Russian and Uzbek wake-word detection remain explicitly out of
  scope (Owner Decision D2) — not a limitation of this
  implementation, a deliberate, disclosed exclusion.
- `CHANGELOG.md`/`docs/RELEASE_NOTES.md` were not updated for EP-048,
  consistent with the same, already-established documentation gap
  `EP045_AUDIT.md`/`EP046_AUDIT.md`/`EP047_AUDIT.md` recorded for
  themselves (carried forward, not new — see `EP048_AUDIT.md` Section
  13).

None of these limitations reflect an unresolved design ambiguity or a
scope violation (Sections 13/14 remain fully honored) — each is
either an environment constraint (no physical microphone/model files
available to verify against, a Linux-only packaging quirk unrelated
to the Windows target) or a deliberate, owner-approved exclusion
(Russian/Uzbek), recorded honestly rather than silently smoothed
over.

### 17.7 Post-STEP-3 bug fix and final real-world verification

Real Windows hardware verification (working microphone, `openwakeword
==0.6.0` installed, real model files placed under
`voice.wake.model_dir`) surfaced a real implementation defect that no
prior verification in this project's history had been able to catch,
since no environment prior to this had a physical microphone or real
model files available at all.

**The defect:** `OpenWakeWordEngine.__init__` constructed the
wake-word model path as a hardcoded `model_dir / f"{wake_word}.onnx"`.
openWakeWord's own official pretrained models are published with a
version suffix (e.g. `hey_jarvis_v0.1.onnx`, exactly what
`openwakeword.utils.download_models()` produces on a real
installation) — not the bare `<wake_word>.onnx` name this
implementation assumed. On the real Windows machine, where
`melspectrogram.onnx`, `embedding_model.onnx`, and
`hey_jarvis_v0.1.onnx` all genuinely existed, construction still
failed with "missing model file(s)" because it was looking for the
wrong filename — `Bootstrap` then caught the resulting
`WakeWordEngineError` and left `voice_wake_engine = None`, which is
why `voice wake status` reported `Enabled: No` despite everything
being correctly installed. A second, latent issue was found in the
same investigation: `openwakeword.Model` keys its `predict()` output
by the *loaded file's own stem* — for a versioned file that is
`"hey_jarvis_v0.1"`, not the configured logical `"hey_jarvis"` — so
`process_frame()`'s original `predictions.get(self._wake_word, 0.0)`
lookup would have always scored `0.0` even after fixing the filename
alone.

**The fix** (owner-approved, applied to
`src/skills/voice/wake_word.py` only): a new
`resolve_wakeword_model_path(model_dir, wake_word)` function tries an
exact `<wake_word>.onnx` match first (preserving prior behavior where
that file is actually present), then exactly one
`<wake_word>_v*.onnx` versioned candidate. Zero or multiple candidates
both raise a clear, actionable `WakeWordEngineError` — never a silent
guess, fully preserving owner Decision D3 (no download, no rename, no
file creation; this only discovers files already present). The
resolved path's `.stem` is stored as a new `model_key` property and
used by `process_frame()` to index `predict()`'s result; the
configured logical `wake_word` property is unchanged and still drives
all user-facing text (`voice wake status`, `WakeWordDetectionResult`).
No owner decision was reopened or reinterpreted by this fix — it
corrects an implementation detail within D1/D3's existing scope, not
the architecture itself.

**Additional regression tests** (`tests/EP048/test_wake_word.py`,
9 new test methods): exact-match resolution, exact-match preferred
over a versioned candidate when both exist, versioned-only resolution
(the exact real-world scenario reported), missing-candidate handling,
multiple-candidate ambiguity handling, and a real
`OpenWakeWordEngine.__init__` construction test reproducing the
reported directory layout end to end.

A second, unrelated test-only issue was found and fixed in the same
verification pass: `_test_streaming_audio_capture_reports_no_device_gracefully`
had assumed the verification environment would always have zero audio
input devices — true of the original sandbox, false on the real
Windows workstation's working microphone. The test was made
environment-independent (it now asserts whichever of "device
available" or "device unavailable" `StreamingAudioCapture.start()`
actually reports, rather than assuming one) with no change to
`streaming_audio_capture.py` itself — this was purely a test-authoring
assumption, not a production defect.

**Real Windows verification, now confirmed successful:**

```
voice wake status
Wake Word Status
Enabled : Yes
Engine : openWakeWord
Wake word : hey_jarvis
Model : available
Model directory : data\models\wake
Threshold : 0.50

voice wake listen
Wake word detected: "hey_jarvis" (score 0.80)
```

and, on a subsequent run:

```
voice wake listen
Wake word detected: "hey_jarvis" (score 0.64)
```

This is the first genuine real-microphone/real-loaded-model
confirmation in this project's history, and it succeeded end to end
on the actual target environment.

**Final test status** (re-verified independently against the current
repository state while producing this update):

```
test EP048  →  Passed: 112   Failed: 0   Skipped: 1
test EP047  →  Passed: 49    Failed: 0   Skipped: 0
test EP045  →  Passed: 38    Failed: 0   Skipped: 0
test EP044  →  Passed: 52    Failed: 0   Skipped: 0
test EP043  →  Passed: 83    Failed: 0   Skipped: 0
```

(112 = the prior 111 plus one further environment-independence fix to
the same `StreamingAudioCapture` test described above, applied in a
separate, later verification pass.) EP-046 encountered its own,
separate, unrelated environment-dependent test issue (an analogous
"assumed no microphone" test assumption in `tests/EP046/test_voice.py`)
which was investigated and fixed independently of EP-048 -- it is not
an EP-048 regression and is not detailed further in this document.

Only `src/skills/voice/wake_word.py` and `tests/EP048/test_wake_word.py`
were modified to produce this fix. No other implementation file,
test file, configuration file, or EP-043–EP-047 file was touched.
`docs/architecture/audits/EP048_AUDIT.md` Section 17 records the same
account with full audit-level evidence and an updated final verdict.

---

*(End of EP-048 STEP 1/2/3 design record. Sections 1-16 are the
original STEP 1 design and Section 9a's STEP 1 owner-decision
resolution, preserved unchanged except for the one inline
"Implemented As" note in Section 6. Section 17 is the STEP 3 as-built
summary, with Section 17.7 recording a post-STEP-3 bug fix and its
real-world verification. No implementation, test, or configuration
file was modified to produce this documentation update.)*

