# EP-049 — Voice Assistant — Design Specification (STEP 1)

**Status:** STEP 1 COMPLETE — OWNER DECISIONS RESOLVED.
Section 23's seven Owner Decisions (D1-D7) were reviewed and approved
by the project owner; their resolution is recorded in Section 23a.
STEP 2 (implementation) has **not** started. No file under `src/`,
`tests/`, or `config/` was created or modified to produce this
document, and `requirements.txt` was not modified. STEP 2 begins
only on explicit owner instruction, mirroring
EP046_DESIGN.md/EP047_DESIGN.md/EP048_DESIGN.md's own STEP 1 → owner
decision → STEP 2 sequencing.

**EP-049 v1 is strictly one-shot (Owner Decision D2):** exactly one
cycle — wake detection → one command capture → STT → dispatch →
optional TTS → return a `CommandResult` and terminate. There is no
loop mode, no repeat/continuous-listening configuration, no
Bootstrap-managed background thread, daemon, or automatic startup
behavior anywhere in this design. Continuous/repeating operation is
explicitly deferred to a future EP (Section 23a, D1/D2).

---

## 1. Executive Summary

Per `docs/architecture/JARVIS_ROADMAP.md`'s Phase 7 sequencing
(EP-046 Speech-to-Text ✓, EP-047 Text-to-Speech ✓, EP-048 Wake Word
✓, **EP-049 Voice Assistant**) and `docs/BACKLOG.md`'s own statement
of the next Engineering Package, EP-049 closes the loop EP-048
deliberately left open: it lets a detected wake word actually lead
to a dispatched Jarvis command, instead of only being reported.

EP-049 introduces no new recognition, dispatch, or synthesis
technology. Every capability it needs already exists in the
repository:

* `OpenWakeWordEngine` + `StreamingAudioCapture` (EP-048) — detect
  the wake phrase.
* `VoskSpeechToTextEngine` + `AudioCapture` (EP-046) — turn a spoken
  command into text.
* `CommandRouter.dispatch()` (pre-EP-046) — execute that text as a
  Jarvis command, exactly as the interactive shell, Telegram, and
  the REST API already do.
* `Pyttsx3TextToSpeechEngine` (EP-047) — optionally speak the result.

EP-049's own new work is therefore small and precisely scoped: one
new orchestration path inside the *existing* `VoiceModule`
(`src/skills/voice/skill.py`) — a `voice wake assist` action (name
confirmed by Owner Decision D5) — that sequences these four existing
components into:

```
wake detected -> stop wake stream -> record one command (existing
AudioCapture) -> transcribe (existing SpeechToTextEngine) -> dispatch
(existing CommandRouter.dispatch()) -> optionally speak the result
(existing TextToSpeechEngine) -> resume wake detection
```

No second STT, no second CommandRouter, no second microphone-capture
implementation, no new dispatch mechanism, and no background/daemon
listener are introduced — all four are explicit hard constraints
from this task and from EP-048's own Owner Decision D5, which named
this exact loop as EP-049's scope and nothing else's.

## 2. Problem Statement

EP-048 shipped `voice wake listen`: a foreground, blocking command
that detects the configured wake phrase and immediately returns,
reporting the detection. By EP-048's own explicit, owner-approved
design (Owner Decision D5), it never acts on that detection — no
STT, no dispatch, no TTS, no background loop.

This means Jarvis today cannot be operated hands-free at all: an
operator must type every command, even to discover whether wake-word
detection is working. EP-049's problem is narrow: **turn a single
wake-word detection into a single executed command**, reusing every
existing voice/dispatch component, without silently growing into a
continuous, multi-turn, or intent-aware assistant — none of which
this task, the roadmap, or `docs/architecture/NON_GOALS.md`
("Jarvis evolves by extending existing architecture rather than
replacing it... architectural consistency is always more important
than short-term functionality") authorize for this EP.

## 3. Goals

1. After a wake-word detection, capture and transcribe exactly one
   spoken command using the *existing* STT stack.
2. Dispatch that transcript through the *existing*, unmodified
   `CommandRouter.dispatch()` — the same entry point the shell,
   Telegram, and REST API already use.
3. Define precise audio-resource ownership across the
   detection → recording → dispatch → detection cycle, so the wake
   stream and the command-capture stream are never open
   simultaneously.
4. Define an explicit state machine covering every transition,
   including every failure and timeout path enumerated in Section
   15 below.
5. Preserve full backward compatibility: `voice listen`, `voice
   transcribe`, `voice speak`, `voice wake listen`, and `voice wake
   status` must all continue to behave exactly as EP-046/047/048
   shipped them.
6. Preserve the project's offline-only architecture for the full
   wake → STT → dispatch pipeline.
7. Identify, rather than silently resolve, every point where this
   task's instructions leave a genuine architectural choice open
   (Section 23, Owner Decisions — now resolved, Section 23a).

## 4. Non-Goals

Per this task's explicit "IMPORTANT SCOPE BOUNDARIES" and
`docs/architecture/NON_GOALS.md`'s "extend, don't replace"
philosophy, EP-049 does **not** introduce:

* A second STT implementation, a second `CommandRouter`, a second
  command parser, a second microphone-capture implementation, or a
  second wake-word engine (`VoiceModule` gains new *orchestration*
  logic only — every capability it orchestrates is EP-046/047/048's
  existing, unmodified code).
* A parallel dispatch mechanism, a `VoiceCommandRouter`,
  `VoiceDispatcher`, `VoiceExecutor`, or `VoiceParser` abstraction —
  recognized text reaches `CommandRouter.dispatch()` exactly the way
  `voice listen` already sends it there today (`skill.py`
  `_listen()`).
* Continuous/always-listening conversational mode, multi-turn
  context, barge-in, or a "keep listening after this command"
  behavior. EP-049 v1 is **strictly one-shot** (Owner Decision D2,
  Section 23a): one detection → one command capture → STT →
  dispatch → optional TTS → return a `CommandResult` and terminate.
  There is no loop/repeat mode, and no configuration key of any kind
  controls repeating or continuous behavior — this is deferred to a
  future EP, not merely defaulted off.
* Semantic intent recognition or LLM-based command interpretation —
  the transcript is handed to `CommandRouter.dispatch()` verbatim,
  exactly as `voice listen` does.
* Cloud STT, cloud wake-word detection, or any network dependency in
  the wake → STT → dispatch path.
* Automatic model downloading (unchanged from EP-046 Owner Decision
  10 / EP-048 Owner Decision D3).
* Multilingual wake words, or Russian/Uzbek wake-word models
  (unchanged, disclosed limitation from EP-048 Owner Decision D2).
* A new command-execution/authorization framework — `CommandRouter`
  remains the sole authority on whether a command is valid and safe
  to run (Section 17).
* A Bootstrap-managed background thread/daemon that starts wake
  detection automatically at process start. `voice wake assist`
  remains a foreground, operator-initiated command, exactly as
  `voice wake listen` is today — **confirmed by Owner Decision D1**
  (Section 23a): EP-049 introduces no background thread, daemon,
  always-on listener, or automatic startup behavior of any kind.
* Any change to `CommandRouter` (`src/core/command_router.py`),
  `src/core/api/`, Telegram routing, `desktop/`, or `web/`.
* Any change to `AudioCapture`'s, `SpeechToTextEngine`'s,
  `TextToSpeechEngine`'s, `WakeWordEngine`'s, or
  `StreamingAudioCapture`'s existing, already-shipped contracts.

## 5. Existing Architecture (Repository Findings)

### 5.1 Files inspected

| File | Role |
|---|---|
| `docs/architecture/JARVIS_ROADMAP.md` | Confirms EP-049 = "Voice Assistant", Phase 7, "NOT STARTED", immediately after EP-048. |
| `docs/BACKLOG.md` | Confirms EP-049 is next; restates EP-048 Owner Decision D5's scope hand-off verbatim. |
| `docs/architecture/designs/EP046_DESIGN.md` | STT design: Vosk, `AudioCapture` (fixed-duration), confidence-gating precedent (Owner Decision 9), `voice.*` config shape. |
| `docs/architecture/audits/EP046_AUDIT.md` | EP-046 as-built/verified state; confirms `speech_to_text.py`/`audio_capture.py` scope and test conventions. |
| `docs/architecture/designs/EP047_DESIGN.md` | TTS design: `pyttsx3`, additive `voice speak`, independent enable/disable precedent (Owner Decision D6 predecessor). |
| `docs/architecture/audits/EP047_AUDIT.md` | EP-047 as-built/verified state; records the pre-EP-048 registration-gate limitation. |
| `docs/architecture/designs/EP048_DESIGN.md` | Wake-word design: `openWakeWord`, `StreamingAudioCapture` (separate from `AudioCapture`), detection-only scope (Owner Decision D5), registration-gate fix (Owner Decision D6), naming (Owner Decision D7). |
| `docs/architecture/audits/EP048_AUDIT.md` | EP-048 as-built/verified state, including the post-STEP-3 versioned-model-filename bugfix. |
| `src/skills/voice/skill.py` (523 lines) | `VoiceModule`, the `"voice"` `CommandModule`. Implements `help`, `listen`, `transcribe`, `status`, `speak`, `wake` (→ `listen`/`status`). |
| `src/skills/voice/audio_capture.py` (161 lines) | `AudioCapture` — EP-046, fixed-duration (`voice.listen_duration_seconds`), blocking `sounddevice.rec()`/`wait()`, one `AudioCaptureResult` per call. |
| `src/skills/voice/streaming_audio_capture.py` (224 lines) | `StreamingAudioCapture` — EP-048, indefinite `sounddevice.InputStream`, `start()`/`frames()`/`stop()` lifecycle, fixed-size frame queue. |
| `src/skills/voice/speech_to_text.py` (386 lines) | `SpeechToTextEngine` Protocol + `VoskSpeechToTextEngine`. `transcribe_audio(pcm_data, sample_rate, language)` → `TranscriptionResult(success, text, confidence, language, error)`. Per-language lazy-loaded Vosk models, worker-thread timeout (`voice.timeout_seconds`). |
| `src/skills/voice/text_to_speech.py` (305 lines) | `TextToSpeechEngine` Protocol + `Pyttsx3TextToSpeechEngine`. `synthesize(text, language)` → `SynthesisResult`. |
| `src/skills/voice/wake_word.py` (415 lines) | `WakeWordEngine` Protocol + `OpenWakeWordEngine`. `process_frame(pcm_frame)` → `WakeWordDetectionResult(detected, score, wake_word)`. |
| `src/core/command_router.py` (158 lines) | `CommandRouter.dispatch(raw_input)` → `CommandResult(success, message, should_exit)`. The single entry point every interface uses. Case-insensitive module/action lookup; catches any module exception, never crashes. |
| `src/bootstrap.py` (voice wiring, ~lines 1490-1625) | Constructs `VoskSpeechToTextEngine`/`AudioCapture`, `Pyttsx3TextToSpeechEngine`, `OpenWakeWordEngine`/`StreamingAudioCapture` independently, each gated by its own `voice.*.enabled` flag, each degrading to `None` on any construction failure. Registers one `VoiceModule` as soon as *any* of the three flags is true (Owner Decision D6). |
| `config/config.yaml` (`voice:` block, lines ~207-360) | `voice.{enabled,engine,languages,default_language,model_dir,offline_only,device,sample_rate,listen_duration_seconds,timeout_seconds,min_confidence}`, `voice.tts.{enabled,engine,languages,default_language,rate,volume}`, `voice.wake.{enabled,engine,wake_word,model_dir,offline_only,device,sample_rate,frame_length,threshold}`. |
| `tests/EP046/test_voice.py`, `tests/EP047/test_voice_tts.py`, `tests/EP048/test_wake_word.py` | Establish the project's fake-collaborator, single-combined-`TestRegistry`-suite, `self.skip()`-for-hardware-dependent-scenarios testing conventions this EP must follow. |
| `docs/architecture/NON_GOALS.md`, `docs/architecture/AI_DEVELOPMENT_PLAYBOOK.md`, `AI_GENERATION_STANDARD.md` | Project-wide "extend, don't replace" / "no duplicated responsibilities" / "implement only the current EP" principles this design applies throughout. |

Every component named as "existing" in Sections 1-10 of this
document was directly located and read in the actual repository —
none is assumed or invented.

### 5.2 `VoiceModule` today (`skill.py`)

Namespace `"voice"`, six flat actions dispatched through an
`_actions` dict: `help`, `listen`, `transcribe`, `status`, `speak`,
`wake` (itself dispatching to `listen`/`status` sub-actions).
Constructor takes `config`, `command_router`, and four independently
optional collaborators: `engine` (STT), `audio_capture`, `tts_engine`,
`wake_engine`, `wake_capture`. Every action already reports a clear,
non-crashing `CommandResult(success=False, ...)` when its required
collaborator(s) are `None` — this is the exact idiom EP-049's new
action must also follow.

`_listen()` (lines 202-253) is the reference implementation for
"transcribe then dispatch": capture → `transcribe_audio()` → if
`_below_confidence_threshold()` is false → `self._command_router
.dispatch(transcription.text)`, wrapping the dispatched
`CommandResult` with a `'Heard: "..."'` prefix and forwarding its
`success`/`should_exit`. **EP-049's wake-triggered dispatch reuses
this exact sequence** — it does not reinvent it.

`_wake_listen()` (lines 412-465) is the reference implementation for
the wake detection loop itself: `wake_capture.start()` →
`for frame in wake_capture.frames(): ... wake_engine.process_frame
(frame)` → on `detection.detected`, `return` immediately, always
`wake_capture.stop()` in a `finally` block. **EP-049's wake-listening
phase reuses this exact loop shape**, extended only to *act* on a
detection instead of returning on it.

### 5.3 Audio resource shapes (critical for Section 9)

`AudioCapture` (EP-046) and `StreamingAudioCapture` (EP-048) are
deliberately separate classes (EP-048 Owner Decision D4) with two
incompatible lifecycles over the *same* underlying `sounddevice`
library and (by default) the *same* configured input device
(`voice.device`, shared by both blocks in `config.yaml`):

* `AudioCapture.capture()` calls the *module-level*
  `sounddevice.rec()` + `sounddevice.wait()` — a single blocking
  global recording call with no explicit stream handle to close.
* `StreamingAudioCapture.start()`/`stop()` open and close an
  explicit `sounddevice.InputStream` instance, continuously
  buffering frames into an in-memory queue until `stop()` is called.

`sounddevice`/PortAudio does not support two simultaneous open
streams against the same input device on most platforms (including
Windows, the project's real-hardware verification target, per
EP-048's own real-hardware notes). **This is why Section 9's audio
ownership rule — "the wake stream must be fully stopped before
`AudioCapture.capture()` is called, and not restarted until that
capture and its transcription complete" — is a hard correctness
requirement, not a style preference.**

## 6. EP-049 Architecture

### 6.1 High-level pipeline

```
Microphone
    |
    v
StreamingAudioCapture (existing, EP-048)
    |
    v
OpenWakeWordEngine.process_frame() (existing, EP-048)
    |
    v
Wake detected -> StreamingAudioCapture.stop()   [WAKE_LISTENING -> WAKE_DETECTED]
    |
    v
AudioCapture.capture() (existing, EP-046)        [COMMAND_LISTENING]
    |
    v
SpeechToTextEngine.transcribe_audio() (existing, EP-046)  [TRANSCRIBING]
    |
    v
CommandRouter.dispatch(text) (existing, pre-EP-046)       [DISPATCHING]
    |
    v
[optional] TextToSpeechEngine.synthesize(result.message) (existing, EP-047)  [SPEAKING]
    |
    v
Return CommandResult; action terminates (no restart of wake
listening -- v1 is strictly one-shot, Owner Decision D2)
                                              [RETURN_TO_WAKE_LISTENING]
```

Every box above is an existing, unmodified class. EP-049's own code
is entirely the arrows: the orchestration sequence, its state
machine, its timeouts, and its error handling — added as new methods
on the existing `VoiceModule`, not as a new class hierarchy.

**Naming note (Owner Decision D2):** the terminal state above retains
the name `RETURN_TO_WAKE_LISTENING` from this document's original
Section 8 sketch, but per the owner's one-shot decision it denotes
**final cleanup and return only** — confirming the wake stream is not
left running and handing the resulting `CommandResult` back to the
caller — not an automatic re-entry into `WAKE_LISTENING`. `_wake_assist()`
never calls `wake_capture.start()` a second time within one
invocation.

### 6.2 Where this lives

Following EP-047's (`speak`) and EP-048's (`wake`) own precedent of
adding one new action to the existing `voice` namespace, EP-049 adds
one new action — `voice wake assist` (confirmed by Owner Decision
D5) — implemented as a new private method on `VoiceModule`,
`_wake_assist()`, following `_wake_listen()`'s exact structure but
extended to call directly into the existing, unmodified `_listen()`
method (confirmed by Owner Decision D3 — no shared helper is
extracted) on detection, instead of returning.

No new class is introduced to hold this orchestration. `VoiceModule`
already is "the thing that sequences microphone/engine collaborators
into a `CommandResult`" for every other voice action; EP-049's flow
is one more sequencing responsibility of the same kind, not a new
architectural layer (`AI_GENERATION_STANDARD.md`'s "prefer extension
over modification" / "avoid growing... a new class where an existing
one already owns this responsibility" principle, as EP-048 Owner
Decision D4 itself already applied when choosing *not* to add a
`stream()` method to `AudioCapture`).

## 7. Component Responsibilities

| Component | New responsibility in EP-049 | Unchanged responsibility |
|---|---|---|
| `VoiceModule` (`skill.py`) | New `_wake_assist()` orchestration method; new `wake assist` sub-action wired into the existing `_wake()` dispatcher (line 399-410). | Everything else — `help`, `listen`, `transcribe`, `status`, `speak`, `wake listen`, `wake status` are byte-identical in behavior. |
| `StreamingAudioCapture` | None — used exactly as `_wake_listen()` already uses it (`start()`/`frames()`/`stop()`). | Frame streaming, device ownership while running. |
| `OpenWakeWordEngine` | None — used exactly as `_wake_listen()` already uses it (`process_frame()`). | Per-frame scoring only. |
| `AudioCapture` | None — used exactly as `_listen()` already uses it (`capture()`). | Fixed-duration blocking capture. |
| `VoskSpeechToTextEngine` | None — used exactly as `_listen()` already uses it (`transcribe_audio()`). | Transcription + confidence normalization. |
| `CommandRouter` | None — `dispatch()` called with the exact same signature and semantics `_listen()` already uses. | Sole authority for command parsing/execution/authorization. |
| `Pyttsx3TextToSpeechEngine` | None (if Owner Decision D6 selects "speak the result") — used exactly as `_speak()` already uses it (`synthesize()`). | Speech synthesis only. |
| `Bootstrap` | New: pass the *same* `voice_wake_engine`/`voice_wake_capture`/`voice_engine`/`voice_audio_capture`/`voice_tts_engine` instances it already constructs into `VoiceModule`'s existing constructor parameters — no new construction, no new config-reading beyond Section 14's minimal additions. | Independent per-subsystem construction/degradation (Section 5, EP-048 Owner Decision D6) is fully preserved. |

## 8. State Machine

Derived from `_wake_listen()`'s existing loop shape (Section 5.2)
extended with `_listen()`'s existing capture → transcribe → dispatch
sequence (Section 5.2), plus the new transitions this task requires.

**Per Owner Decision D2 (Section 23a), this state machine describes
exactly one cycle, start to finish, with no repetition.**
`RETURN_TO_WAKE_LISTENING` is the machine's single terminal state: it
performs final cleanup only (confirming the microphone is not held)
and then `_wake_assist()` returns its `CommandResult` to the caller.
It never triggers a new `wake_capture.start()` call or re-enters
`WAKE_LISTENING` within the same invocation.

| State | Entry condition | Action | Exit condition | Timeout | Error behavior | Resource ownership |
|---|---|---|---|---|---|---|
| **DISABLED** | `voice.wake.assist.enabled` false, or `wake_engine`/`wake_capture`/`engine`/`audio_capture` is `None` at call time (Section 14). | None — `voice wake assist` returns immediately. | N/A | N/A | `CommandResult(success=False, ...)`, never a crash — mirrors `_wake_listen()`'s/`_listen()`'s existing `None`-collaborator handling. | None held. |
| **WAKE_LISTENING** | `wake_capture.start()` succeeded. | `for frame in wake_capture.frames(): ... process_frame(frame)`, exactly `_wake_listen()`'s existing loop. | A frame scores `detected=True` → **WAKE_DETECTED**. Stream ends/errors with no detection → **RETURN_TO_WAKE_LISTENING** is not entered; the action returns a failure result directly (mirrors `_wake_listen()`'s own "ended without a detection" return). | None (matches `_wake_listen()`: this is an indefinite loop the operator can interrupt). | `KeyboardInterrupt` → stop stream, return failure (mirrors `_wake_listen()`). Any other frame-scoring error is already absorbed inside `process_frame()` itself (returns `detected=False`), per Section 5.2/EP-048 Section 5.5 — never propagates here. | `StreamingAudioCapture` (wake stream) owns the microphone. `AudioCapture` must not be invoked while in this state (Section 9). |
| **WAKE_DETECTED** | A frame's `WakeWordDetectionResult.detected` is `True`. | `wake_capture.stop()` (releases the wake stream) **before** anything else — the mandatory hand-off point Section 9 defines. | Stream stopped → **COMMAND_LISTENING**. | None (a single synchronous call). | `StreamingAudioCapture.stop()` never raises (Section 5.2's `finally`/error-logging contract) — this transition cannot itself fail. | Ownership transitions from `StreamingAudioCapture` to *no one* (brief gap) then to `AudioCapture` in the next state. |
| **COMMAND_LISTENING** | Wake stream confirmed stopped. | `audio_capture.capture()` — the *existing* EP-046 fixed-duration blocking capture, using its own existing `voice.listen_duration_seconds` (Section 14: no new duration setting). | `capture_result.success` True → **TRANSCRIBING**. False → **RETURN_TO_WAKE_LISTENING** (terminal) with a reported microphone error; `_wake_assist()` returns that failure, per Owner Decision D2/D7 (no retry, no resumed listening). | `voice.listen_duration_seconds` (existing EP-046 setting, unchanged) bounds this state's real-world duration; no new timeout setting is needed here because `AudioCapture.capture()` cannot itself hang past that duration. | Microphone unavailable/busy → `AudioCaptureResult(success=False, error=...)`, exactly `_listen()`'s existing handling. Must not raise. | `AudioCapture` owns the microphone. `StreamingAudioCapture` must not be started while in this state (Section 9). |
| **TRANSCRIBING** | `capture_result.success` is True. | `engine.transcribe_audio(pcm_data, sample_rate, language)` — the *existing* EP-046 call, same as `_listen()`. | `transcription.success` True → **DISPATCHING**. False (empty/no speech, timeout, model error) → **RETURN_TO_WAKE_LISTENING** (terminal) with the transcription's own `error` reported; `_wake_assist()` returns that failure (Owner Decision D2/D7). | `voice.timeout_seconds` (existing EP-046 setting, enforced inside `VoskSpeechToTextEngine._recognize()` via its own worker-thread `TimeoutError`, unchanged). | Any transcription failure is already a non-exceptional `TranscriptionResult(success=False, ...)` per Section 5.2 — never raises. | No microphone held during this state (recording already finished; `pcm_data` is an in-memory buffer). |
| **DISPATCHING** | `transcription.success` is True. | Confidence gate first (`_below_confidence_threshold()`, existing EP-046 helper, unchanged threshold/semantics) — if below threshold, **do not dispatch**; go directly to **RETURN_TO_WAKE_LISTENING** (terminal), reporting the heard text and confidence exactly as `_listen()` already does. Otherwise: `command_router.dispatch(transcription.text)` — the *existing*, unmodified entry point. | Dispatch returns (it always does — `CommandRouter.dispatch()` catches any module exception internally, Section 5.3) → **SPEAKING** (if TTS-on-result is enabled, Owner Decision D6) or directly **RETURN_TO_WAKE_LISTENING** (terminal). A failed, rejected, or misunderstood command is handled purely through the returned `CommandResult` — no retry, no confirmation step, no counter (Owner Decision D7). | None (dispatch is synchronous; a slow command is that command's own concern, unchanged from every other dispatch path). | `CommandRouter.dispatch()` never raises to its caller (Section 5.3) — a failing command still produces a `CommandResult(success=False, ...)`, which EP-049 reports/optionally speaks exactly as-is, never retried automatically (Owner Decision D7). | No microphone held. |
| **SPEAKING** *(conditional, Owner Decision D6)* | Dispatch completed and `tts_engine` is not `None` and `voice.wake.assist.speak_result` is true. | `tts_engine.synthesize(dispatched_result.message)` — the *existing* EP-047 call, same as `_speak()`. | Always → **RETURN_TO_WAKE_LISTENING** (terminal), regardless of synthesis success (a TTS failure must never block returning the final result). | None (bounded by `synthesize()`'s own internal behavior, unchanged). | Synthesis failure is a non-exceptional `SynthesisResult(success=False, ...)`, logged/reported but not fatal — the command's own `CommandResult` is still returned. | No microphone held (TTS uses an output device, never the input device `AudioCapture`/`StreamingAudioCapture` use). |
| **RETURN_TO_WAKE_LISTENING** *(terminal)* | Any terminal outcome of the states above (success or any listed failure), including a failed/rejected/misunderstood command from **DISPATCHING** (Owner Decision D7 — no special handling). | Final cleanup only: confirm the wake stream is not left running (it was already stopped in **WAKE_DETECTED** and is never restarted within this invocation). No new `wake_capture.start()` call is made. | `_wake_assist()` returns the resulting `CommandResult` to its caller and the invocation ends (Owner Decision D2 — strictly one-shot). | None. | This state performs no I/O and cannot itself fail. | None held — the microphone was already released in **WAKE_DETECTED**/at the end of **COMMAND_LISTENING** and remains unclaimed after this state. |

## 9. Audio Resource Ownership

This section answers this task's explicit ownership questions
directly, per component named in Section 5.3.

* **Is the wake stream stopped before command recording?** Yes,
  always, unconditionally, and *before* `AudioCapture.capture()` is
  ever called — this is the **WAKE_DETECTED** state's entire purpose
  (Section 8). `StreamingAudioCapture.stop()` is called exactly once
  per detection, synchronously, before `COMMAND_LISTENING` begins.
* **Can the same audio stream be reused for both phases?** No. Wake
  detection and command capture remain the two separate,
  differently-lifecycled components EP-048 Owner Decision D4 already
  established (`StreamingAudioCapture` vs. `AudioCapture`) — EP-049
  does not merge them, add a shared stream abstraction, or give
  `StreamingAudioCapture` a "capture N seconds then stop" mode.
  Reusing one component for both would revisit an already-settled
  EP-048 decision and blur `AudioCapture`'s/`StreamingAudioCapture`'s
  now-established single responsibilities.
* **Who owns the microphone at each point?** Exactly one of
  `StreamingAudioCapture` (while `WAKE_LISTENING`) or `AudioCapture`
  (while `COMMAND_LISTENING`) — never both, and never neither for an
  extended period (the gap between `wake_capture.stop()` returning
  and `audio_capture.capture()` being called is a single synchronous
  call stack, not an awaited/background gap). See Section 8's table,
  "Resource ownership" column, for the complete accounting.
* **How are simultaneous InputStreams prevented?** By construction,
  not by a new lock/semaphore: `_wake_assist()` is a single,
  sequential control-flow method (mirroring `_wake_listen()`'s and
  `_listen()`'s own already-sequential, single-threaded call shape).
  It never starts `AudioCapture.capture()` except after
  `wake_capture.stop()` has already returned, and never restarts
  `wake_capture.start()` until `capture()`+`transcribe_audio()`
  (+optionally `dispatch()`+`synthesize()`) have already returned.
  No new concurrency (threads, async tasks) is introduced — this
  entire pipeline runs on the same calling thread that invoked
  `voice wake assist`, exactly as `_wake_listen()` and `_listen()`
  each already do independently.
* **How are resources released after errors?** `StreamingAudioCapture
  .stop()` is documented as never-raising and safe to call multiple
  times / after a failed `start()` (Section 5.3's docstring,
  confirmed in `streaming_audio_capture.py` lines 208-224) — EP-049's
  orchestration calls it in exactly the same `finally`-guarded shape
  `_wake_listen()` already uses, so a mid-detection exception (should
  one somehow occur) still releases the wake stream. `AudioCapture
  .capture()` has no persistent stream handle to leak — it is a
  single call-and-return, so there is nothing to release on its
  error paths beyond what `_listen()` already relies on today.
* **Does wake detection resume automatically after command
  processing?** No. **Per Owner Decision D2, EP-049 v1 is strictly
  one-shot:** `_wake_assist()` never calls `wake_capture.start()`
  again within the same invocation. **RETURN_TO_WAKE_LISTENING**
  (Section 8) performs cleanup only and then returns the
  `CommandResult` — the microphone remains fully released and
  unclaimed once the invocation ends. An operator who wants to listen
  for the wake word again simply re-issues `voice wake assist` (or
  `voice wake listen`) as a new, independent invocation, exactly as
  `StreamingAudioCapture.start()`/`stop()` already supports being
  called repeatedly across independent sessions today. Continuous,
  automatic re-arming is explicitly deferred to a future EP.

## 10. Wake → STT → Dispatch Flow

Concretely, in terms of the actual existing method calls (all
already present in the repository, called in this new sequence):

```python
# Pseudocode -- illustrates the call sequence only. STEP 1 does not
# write this code (Section 20).
def _wake_assist(self, arguments: list[str]) -> CommandResult:
    if self._wake_engine is None or self._wake_capture is None:
        return CommandResult(success=False, message="Wake Word detection is not enabled or not available. ...")
    if self._engine is None or self._audio_capture is None:
        return CommandResult(success=False, message="Speech-to-Text is not enabled or not available. ...")

    # Exactly one cycle -- no loop (Owner Decision D2, strictly one-shot).
    start_result = self._wake_capture.start()
    if not start_result.success:
        return CommandResult(success=False, message=f"Microphone error: {start_result.error}")

    detected = False
    try:
        for frame in self._wake_capture.frames():
            detection = self._wake_engine.process_frame(frame)
            if detection.detected:
                detected = True
                break
    finally:
        self._wake_capture.stop()          # WAKE_DETECTED: mandatory hand-off

    if not detected:
        return CommandResult(success=False, message="Wake word listening ended without a detection.")

    # COMMAND_LISTENING -> TRANSCRIBING -> DISPATCHING: the existing
    # _listen() method, called directly and unmodified (Owner Decision D3).
    listen_result = self._listen(arguments)

    # SPEAKING (optional, Owner Decision D6): config read directly, no
    # new constructor parameter (Owner Decision D4).
    if self._tts_engine is not None and self._config.get("voice.wake.assist.speak_result", False):
        self._tts_engine.synthesize(listen_result.message)

    # RETURN_TO_WAKE_LISTENING (terminal): return immediately. No restart
    # of wake_capture, no loop -- v1 is strictly one-shot (Owner Decision D2).
    return listen_result
```

The key architectural points: **`self._listen(arguments)` is called
directly, unmodified** (Owner Decision D3) — EP-049 does not
re-implement capture, transcription, confidence-gating, or dispatch;
it calls the exact existing method `voice listen` already calls,
achieving Goal 2 (reuse `CommandRouter.dispatch()`) by construction
rather than by a new, parallel code path. And **the function returns
exactly once, after exactly one cycle** (Owner Decision D2) — there
is no loop construct anywhere in `_wake_assist()`.

## 11. STT Integration

* **Language selection:** identical to `_listen()` today — an
  optional language argument, defaulting to the engine's configured
  `voice.default_language`. EP-049 introduces no wake-word-specific
  language selection; `voice wake assist [language]` would accept
  the same optional argument `voice listen [language]` already does.
* **Timeout handling:** unchanged — `voice.timeout_seconds`,
  enforced inside `VoskSpeechToTextEngine._recognize()`'s existing
  worker-thread mechanism (Section 5.3/8).
* **Empty transcription handling:** unchanged — `TranscriptionResult
  (success=False, error="no speech detected")`, reported and the
  cycle returns to wake listening (no dispatch attempted).
* **Confidence handling:** unchanged — `_below_confidence_threshold()`
  and `voice.min_confidence`, exactly as `_listen()` already applies
  them (Owner Decision 9, EP-046).
* **Result object crossing the boundary:** `TranscriptionResult` is
  never itself passed outside `_listen()`/`_wake_assist()` — only the
  resulting `CommandResult` (from `_listen()`) crosses back to
  whatever reports `voice wake assist`'s outcome, exactly as today.
* **Existing vs. minimal extension:** EP-049 requires **no** change
  to `SpeechToTextEngine`'s Protocol or `VoskSpeechToTextEngine`'s
  implementation — it consumes `VoiceModule._listen()`, which already
  wraps everything STT-related. This is a direct, load-bearing
  consequence of Section 10's reuse of `_listen()` rather than
  reaching into `self._engine`/`self._audio_capture` directly a
  second time.

## 12. CommandRouter Integration

EP-049 introduces **zero** lines of change to
`src/core/command_router.py`. `CommandRouter.dispatch()` is called
exactly once per successful, sufficiently-confident transcription,
with exactly the same signature (`dispatch(text: str) -> CommandResult`)
and via exactly the same call site (`VoiceModule._listen()`, Section
5.2/10) every other voice interaction already uses. `voice wake
assist` never calls `dispatch()` itself, directly or a second time —
it delegates that responsibility entirely to `_listen()`, preserving
"one dispatch mechanism" as a structural invariant rather than a
convention EP-049 has to separately uphold.

## 13. TTS Integration Decision

Per this task's explicit framing ("A) only dispatch and report the
result, or B) optionally speak the result through existing TTS"):
**Owner Decision D6 (Section 23a) approves (B), strictly optional and
off by default**, reusing `Pyttsx3TextToSpeechEngine.synthesize()`
exactly as `_speak()` already calls it (Section 5.2/8's **SPEAKING**
state).

TTS-on-result:

* Is gated by its own new, minimal config flag (Section 14) —
  distinct from `voice.tts.enabled` itself, so an operator can have
  TTS available for `voice speak` without it automatically narrating
  every wake-triggered command result.
* Never blocks or fails the overall interaction — a synthesis
  failure is logged/reported but the cycle still returns to wake
  listening (Section 8, **SPEAKING** row).
* Is skipped entirely (no error) when `tts_engine is None`, mirroring
  every other optional-collaborator check already in `skill.py`.

## 14. Configuration

Per this task's instruction to design "only the minimum additional
configuration required," and to avoid duplicating `voice.*`/
`voice.tts.*`/`voice.wake.*` settings that already exist:

```yaml
voice:
  # ... existing voice.* (EP-046), unchanged ...
  # ... existing voice.tts.* (EP-047), unchanged ...
  # ... existing voice.wake.* (EP-048), unchanged ...

  wake:
    # ... existing voice.wake.* keys, unchanged ...

    # EP-049 additions, nested under the existing voice.wake block
    # (the wake-triggered assistant is conceptually part of "wake",
    # not a fourth top-level voice.* subsystem). Owner Decision D2:
    # EP-049 v1 is strictly one-shot -- there is no configuration key
    # for repeating/looping/continuous behavior; that is deferred to
    # a future EP, not merely defaulted off.
    assist:
      enabled: false          # NEW. Independent master switch for the
                               # one-shot wake -> STT -> dispatch cycle
                               # (Owner Decision D2). Requires
                               # voice.wake.enabled AND voice.enabled
                               # (STT) to both also be true to actually
                               # run (Section 14.1) -- this flag alone
                               # does not imply either.
      speak_result: false     # NEW. Whether to speak the dispatched
                               # command's result via the existing TTS
                               # engine (Section 13, Owner Decision
                               # D6). Requires voice.tts.enabled to
                               # also be true; otherwise this flag is
                               # inert (no tts_engine is ever
                               # constructed to use) and the command
                               # still executes and reports normally.
```

No new top-level configuration section is introduced.
`voice.listen_duration_seconds`, `voice.timeout_seconds`,
`voice.min_confidence`, and every `voice.wake.*` key are reused
exactly as-is (Goal/Non-Goal: "Design only the minimum additional
configuration required"). Per Owner Decision D4, `VoiceModule` reads
`voice.wake.assist.*` directly from the existing `config` object it
already holds — no new constructor parameter is added to carry these
values.

### 14.1 Enable/disable semantics and interaction with existing flags

* `voice.wake.assist.enabled: false` (default) → `voice wake assist`
  behaves exactly like an unknown-but-gracefully-handled action:
  `CommandResult(success=False, message="...")`, mirroring every
  other "not enabled" message already in `skill.py`. **No behavior
  changes for any existing action.**
* `voice.wake.assist.enabled: true` but `voice.wake.enabled: false`
  → `wake_engine`/`wake_capture` are `None` (Bootstrap's existing
  gating, Section 5's Owner-Decision-D6 logic, unchanged) →
  `_wake_assist()` reports the existing "Wake Word detection is not
  enabled" message (Section 10's guard clause) — this flag never
  *implies* `voice.wake.enabled`; both must be true.
* `voice.wake.assist.enabled: true` but `voice.enabled: false` (STT
  off) → `engine`/`audio_capture` are `None` → `_wake_assist()`
  reports the existing "Speech-to-Text is not enabled" message. A
  detected wake word with no STT available is reported as a clear
  failure, never a silent no-op and never a crash.
* `voice.wake.assist.speak_result: true` but `voice.tts.enabled:
  false` → `tts_engine` is `None` → the **SPEAKING** state (Section
  8) is simply skipped; the dispatched result is still returned/
  reported normally.
* All three master flags (`voice.enabled`, `voice.tts.enabled`,
  `voice.wake.enabled`) keep exactly their EP-046/047/048 meaning
  and Bootstrap wiring (Section 5.1) — `voice.wake.assist.*` is
  purely an additional gate *on top of* those, never a replacement
  for any of them.

### 14.2 Backward compatibility

* `voice.wake.assist` defaults to `enabled: false` — a fully
  upgraded `config/config.yaml` with no changes at all preserves
  EP-046/047/048 behavior exactly, including `voice wake listen`
  itself, which is entirely untouched by this EP (Section 15,
  "unchanged files").
* No existing key's default value, meaning, or validation changes.
* **`VoiceModule`'s constructor signature does not change at all**
  (Owner Decision D4): no new parameter is added. `voice.wake.assist.*`
  settings are read directly from the existing `config` object
  already passed into `__init__` (the same object `_min_confidence`
  is already read from today), either inline inside `_wake_assist()`
  or cached once in `__init__` exactly as `_min_confidence` is —
  either way, every existing call site and every existing
  EP-046/047/048 test that constructs `VoiceModule` continues to
  compile and pass completely unmodified, with zero new arguments to
  account for.

## 15. Error Handling

Every failure mode this task enumerates, mapped to Section 8's state
machine and to an existing, already-established handling idiom:

| Failure | State it occurs in | Handling |
|---|---|---|
| Wake word detected | WAKE_LISTENING → WAKE_DETECTED | Normal transition (not a failure) — proceeds to COMMAND_LISTENING. |
| No speech follows wake word | COMMAND_LISTENING → TRANSCRIBING | `AudioCapture.capture()` still succeeds (it always records for the full configured duration) but yields silence; `transcribe_audio()` returns `success=False, error="no speech detected"` (existing `speech_to_text.py` behavior) → reported; `_wake_assist()` returns that failure and terminates (Owner Decision D2 — one-shot, no retry). |
| STT returns empty text | TRANSCRIBING | Same as above — `TranscriptionResult(success=False, error="no speech detected")`, existing behavior, no dispatch attempted, action terminates. |
| STT confidence too low | DISPATCHING (gate) | `_below_confidence_threshold()` (existing, unchanged) — reported with heard text + confidence, exactly as `_listen()` already reports it; no dispatch; action terminates (Owner Decision D7 — no special handling beyond the existing result mechanism). |
| Recording times out | TRANSCRIBING | `VoskSpeechToTextEngine._recognize()`'s existing worker-thread `TimeoutError` → `TranscriptionResult(success=False, error="recognition timed out after {N}s")` (existing behavior); action terminates. |
| Microphone becomes unavailable | COMMAND_LISTENING | `AudioCapture.capture()` returns `AudioCaptureResult(success=False, error="microphone unavailable: ...")` (existing behavior) → reported; `_wake_assist()` returns that failure immediately (Owner Decision D2/D7 — no retry, no re-arming of wake listening). |
| STT model is unavailable | TRANSCRIBING (or earlier, at Bootstrap construction) | If unavailable at construction time, `self._engine is None` and `_wake_assist()` never leaves the initial guard (Section 10) — same as `voice listen` today. If a *specific language's* model directory is missing, `transcribe_audio()` returns `success=False` with the existing per-language error (`speech_to_text.py` `_load_model`); action terminates. |
| CommandRouter rejects the command | DISPATCHING | `dispatch()` returns its own `CommandResult(success=False, message="Unknown module: ...")` (existing behavior, e.g. an unrecognized module name) — reported/optionally spoken exactly like any other dispatched result and returned as-is (Owner Decision D7 — no retry, no confirmation step); not a crash, not a special case EP-049 adds handling for. |
| Command execution fails | DISPATCHING | `dispatch()` already catches any module-internal exception and returns `CommandResult(success=False, message="Internal error while executing '...'.")` (existing `CommandRouter.dispatch()` behavior, `command_router.py` lines 138-145) — EP-049 relies on this existing guarantee rather than adding its own try/except around `dispatch()`, and returns that result as-is. |
| Wake-word detection fails (engine error) | WAKE_LISTENING | Already absorbed inside `process_frame()` itself — a scoring error yields `WakeWordDetectionResult(detected=False, score=0.0, ...)` (existing `wake_word.py` behavior, Section 5.2) — the frame-scanning loop simply continues; it never raises out to `_wake_assist()`. |
| User speaks the wake word repeatedly (before/during command capture) | (see Section 9's ownership guarantee) | Impossible by construction during COMMAND_LISTENING/TRANSCRIBING/DISPATCHING/SPEAKING — the wake stream is stopped for the entire duration of those states (Section 9) and, per Owner Decision D2, is never restarted within the same invocation. A repeated utterance of the wake word during those states scores nothing (no stream is open to score it) and has no effect; a *new* wake-word detection only becomes possible if the operator explicitly issues a fresh `voice wake assist`/`voice wake listen` invocation after this one has returned. |
| User says a command that is not recognized | DISPATCHING | Same as "CommandRouter rejects the command" above — `dispatch()`'s existing "Unknown module" `CommandResult`, reported and returned as-is (Owner Decision D7). |

No failure path above introduces a new exception type, a new retry
loop, or a new logging convention — each reuses the exact
`success=False`-typed result and `loguru` logging idiom
`AudioCaptureResult`/`TranscriptionResult`/`WakeWordDetectionResult`/
`CommandResult` already established.

## 16. Timeout / Recovery

* **Wake listening (WAKE_LISTENING):** no timeout — matches `voice
  wake listen`'s own existing, indefinite-until-detected-or-
  interrupted behavior. An operator running `voice wake assist`
  (always strictly one-shot in v1, Owner Decision D2) waits as long
  as it takes for the wake phrase; this is unchanged from today's
  `voice wake listen`.
* **Command recording (COMMAND_LISTENING):** bounded by the existing
  `voice.listen_duration_seconds` — no new timeout setting.
* **Transcription (TRANSCRIBING):** bounded by the existing
  `voice.timeout_seconds` — no new timeout setting.
* **Dispatch (DISPATCHING):** unbounded, exactly as every other
  dispatch path (shell, Telegram, REST API) already is — EP-049
  introduces no dispatch-level timeout that does not already exist
  project-wide.
* **Recovery after any failure:** the pipeline always reaches
  **RETURN_TO_WAKE_LISTENING** as a terminal cleanup step and
  `_wake_assist()` returns a `CommandResult` — it never restarts wake
  listening automatically (Owner Decision D2) and never leaves a
  stale state, a held microphone, or a hung thread. No new thread,
  process, or async task is introduced anywhere in this pipeline
  (Section 9) — there is nothing to "recover" beyond what a normal
  Python function return and `finally` block already guarantee.

## 17. Security / Command Execution Boundaries

* **Are all commands allowed?** Unchanged — `CommandRouter.dispatch()`
  remains the sole authority on which module/action combinations
  exist and execute; EP-049 adds no allow-list, deny-list, or new
  permission layer of its own. Whatever authorization/validation
  `CommandRouter` and individual `CommandModule`s already enforce
  today (per-module logic) applies identically whether the text
  originated from typing, `voice listen`, or `voice wake assist`.
* **Does EP-049 add a new permission boundary?** No — per this task's
  own instruction ("Do not invent a new security system unless
  required. Reuse existing project authorization/validation
  mechanisms"), and because no existing per-source authorization
  distinction (typed vs. spoken) exists in `CommandRouter` today to
  extend.
* **How are accidental wake-word detections handled?** Exactly as
  EP-048 already handles them: a false-positive detection is
  indistinguishable, at the `WakeWordDetectionResult` level, from a
  genuine one — `voice.wake.threshold` (existing, unchanged) is the
  sole existing control over false-positive rate. An accidental
  detection simply starts a COMMAND_LISTENING cycle that then, most
  likely, records silence or unrelated noise, which the existing
  "no speech detected"/confidence-gate paths (Section 15) already
  handle safely (reported, not dispatched).
* **How is low-confidence speech prevented from being blindly
  dispatched?** By the same, unmodified `_below_confidence_threshold()`
  / `voice.min_confidence` gate `_listen()` already enforces (Section
  11) — EP-049 does not weaken, bypass, or duplicate this gate; it is
  inherited for free by calling `_listen()` directly (Section 10).
* **Net new attack surface:** the practical, disclosed risk EP-049
  introduces is that *any* voice within range of the microphone,
  authorized or not, can trigger command dispatch once the wake word
  is spoken and a command is understood with sufficient confidence —
  this is an inherent property of a voice-activated assistant, not
  something EP-049's design can eliminate without speaker
  verification (explicitly out of scope, Section 4, EP-048's own
  Section 2 non-goals). This is recorded as a disclosed limitation
  (Section 21), not silently accepted.

## 18. Offline Requirements

Every component in Section 10's pipeline is already offline-only
(Vosk, `openWakeWord`, `pyttsx3`/SAPI5, and `CommandRouter` itself
make no network calls). EP-049 adds no network-dependent step
anywhere in the wake → STT → dispatch → (optional) TTS path,
preserving `voice.offline_only: true`'s existing meaning without
requiring any new configuration key to express it (Section 14 adds
no `offline_only` flag under `voice.wake.assist` because there is
nothing there that could ever be online — the same reasoning
`voice.wake.offline_only` already documents for `voice.wake.*`).

## 19. Backward Compatibility

Explicitly verified against each named EP:

* **EP-046 (`voice listen`/`voice transcribe`/`voice status`):**
  unchanged — `_listen()`/`_transcribe()`/`_status()` are called by
  EP-049's new code exactly as they exist today (`_listen()` is
  reused directly; `_transcribe()`/`_status()` are untouched and
  unrelated to this EP's new action). `speech_to_text.py` and
  `audio_capture.py` require zero changes.
* **EP-047 (`voice speak`):** unchanged — `_speak()` is untouched;
  `text_to_speech.py` requires zero changes. EP-049's optional
  TTS-on-result step (Section 13) calls
  `self._tts_engine.synthesize()` directly, the same public method
  `_speak()` already calls, not a wrapper around `_speak()` itself
  (which expects explicit user-supplied text, not a dispatched
  result — reusing `_speak()`'s *method*, not its *signature's
  meaning*, would be a subtle misuse).
* **EP-048 (`voice wake listen`/`voice wake status`):** unchanged —
  `_wake_listen()`/`_wake_status()` are untouched;
  `streaming_audio_capture.py` and `wake_word.py` require zero
  changes. EP-049 adds a *new*, separate action (`wake assist`)
  alongside them inside the existing `_wake()` sub-dispatcher (lines
  399-410) — `voice wake listen` remains available and behaves
  identically for an operator who wants detection-only behavior
  without the full loop.
* **`CommandRouter`:** zero changes (Section 12).
* **`Bootstrap`:** **no change at all** to how `VoiceModule` is
  constructed (Owner Decision D4) — the same `config`,
  `command_router`, `engine`, `audio_capture`, `tts_engine`,
  `wake_engine`, `wake_capture` arguments already passed today
  continue to be passed unchanged; `voice.wake.assist.*` is read by
  `VoiceModule` directly from the `config` object it already holds.
  No new construction logic, no new `try`/`except` block, and no
  change to the existing independent-enable/disable gating (Section
  14.1).
* **Every existing `voice.*`/`voice.tts.*`/`voice.wake.*` config
  key:** unchanged default, meaning, and validation (Section 14.2).

## 20. Testing Strategy

Following `tests/EP046/test_voice.py`/`tests/EP047/test_voice_tts.py`/
`tests/EP048/test_wake_word.py`'s established, project-wide
convention (single combined `TestRegistry` suite, `NAME = "EP049"`,
in `tests/EP049/test_voice_assistant.py`, imported by
`src/modules/test_module.py` — created in STEP 2, not STEP 1):

Fakes for `WakeWordEngine`, `StreamingAudioCapture`, `SpeechToTextEngine`,
`AudioCapture`, and `CommandRouter`/a fake `CommandModule` (following
`_FakeWakeWordEngine`/`_FakeStreamingAudioCapture`'s existing pattern
from `tests/EP048/test_wake_word.py`) make every scenario below
deterministic and require no physical microphone, no real model
files, and no network access:

1. Disabled configuration (`voice.wake.assist.enabled: false`, or
   default) — `voice wake assist` reports "not enabled," never
   attempts any collaborator call.
2. Wake detection (fake engine/capture) transitions into
   COMMAND_LISTENING.
3. Wake detection followed by command listening — full happy path,
   fake collaborators, asserting the exact call order: `wake_capture
   .stop()` before `audio_capture.capture()`, before
   `engine.transcribe_audio()`, before `command_router.dispatch()`.
4. Successful STT → successful dispatch → correct `CommandResult`
   returned (message, success, should_exit forwarded correctly).
5. Empty STT result — no dispatch attempted; correct failure message.
6. Low-confidence STT — no dispatch attempted; correct failure
   message including heard text + confidence (mirrors existing
   `_listen()` test coverage in `tests/EP046/test_voice.py`).
7. STT timeout (fake engine raising/returning the existing timeout
   `TranscriptionResult`) — no dispatch attempted.
8. Microphone unavailable (fake `AudioCapture.capture()` returning
   `success=False`) — no transcription/dispatch attempted; the
   action returns that failure immediately and terminates (Owner
   Decision D2 — strictly one-shot, no retry, no resumed wake
   listening).
9. Wake engine unavailable (`wake_engine=None`) — action reports
   failure immediately, never touches STT/dispatch.
10. STT model unavailable (`engine=None`, or a fake engine reporting
    a per-language missing-model error) — action reports failure,
    never dispatches.
11. `CommandRouter.dispatch()` called exactly once with the exact
    transcribed text, using a fake/spy `CommandModule` registered on
    a real `CommandRouter` (mirrors `tests/EP046/test_voice.py`'s own
    dispatch-integration pattern).
12. `CommandRouter` dispatch failure (fake module raising, or
    returning `success=False`) — reported/optionally spoken as-is,
    no special-cased handling, no retry.
13. Correct terminal cleanup after every outcome (success and every
    failure in Section 15) — asserted via the fake
    `StreamingAudioCapture`'s `start()`/`stop()` call counts: `start()`
    called exactly **once** and `stop()` called exactly **once** per
    `_wake_assist()` invocation, with no second `start()` call under
    any circumstance (Owner Decision D2 — strictly one-shot; no
    automatic re-arming of wake listening).
14. Cleanup after every failure path — fake `StreamingAudioCapture
    .stop()` is asserted called even when a later step (STT,
    dispatch) fails, confirming no leaked "running" state.
15. No duplicate command dispatch — fake `CommandRouter`/module call
    count asserted `== 1` per cycle, across every branch (success,
    low confidence, empty transcription, etc. — most of which must
    assert `== 0`).
16. No simultaneous microphone ownership — fake capture/audio-capture
    objects assert `wake_capture.is_running is False` at the exact
    moment `audio_capture.capture()` is invoked (achievable by having
    the fake `AudioCapture.capture()` itself assert this inside its
    own call, following the existing fakes' pattern of asserting
    invariants from inside the fake).
17. Existing EP-046 behavior remains intact — re-run/re-assert
    `voice listen`/`voice transcribe`/`voice status` scenarios
    against a `VoiceModule` constructed with the new EP-049
    parameter(s) present (defaulted), confirming zero behavior
    change (mirrors EP-047/EP-048's own "regression compatibility"
    test items).
18. Existing EP-047 behavior remains intact — same, for `voice speak`.
19. Existing EP-048 behavior remains intact — same, for `voice wake
    listen`/`voice wake status`.
20. `Bootstrap` wiring: `voice.wake.assist.enabled` true/false/absent
    all degrade safely; true with `voice.wake.enabled: false` or
    `voice.enabled: false` degrades to the correct existing "not
    enabled" messages (Section 14.1), never a crash.
21. `voice help` includes the new action; unknown `wake` sub-action
    (e.g. `voice wake bogus`) still reports the existing usage
    message unchanged (mirrors EP-048's own test item 17).
22. `voice.wake.assist.speak_result: true` with a real/fake
    `tts_engine` present — `synthesize()` called exactly once, with
    the dispatched result's message, after dispatch, never before.
23. `voice.wake.assist.speak_result: true` but `tts_engine is None`
    (TTS disabled) — SPEAKING is skipped without error.
24. One scenario mirroring `tests/EP048/test_wake_word.py`'s own
    precedent — an actual wake phrase → real command, end-to-end
    through the *real* `OpenWakeWordEngine`/`VoskSpeechToTextEngine`
    — is not exercised in the automated suite (no model files, no
    physical microphone in this environment) and is reported via
    `self.skip()`, not silently omitted, exactly as EP-046/047/048's
    own hardware-dependent scenarios already are.

Real hardware verification (an actual "hey jarvis" → actual spoken
command → actual dispatched result, on the real Windows target
machine) is described as a **separate, manual STEP 2/3 verification
item**, not part of the automated suite — following EP-048's own
real-hardware verification precedent exactly (`EP048_AUDIT.md`
Section 17).

## 21. Acceptance Criteria

For STEP 2 (not yet started), EP-049 is acceptable when:

1. `voice wake assist` exists as a new action under the existing
   `voice` `CommandModule`, reachable only when
   `voice.wake.assist.enabled` (and `voice.wake.enabled` and
   `voice.enabled`) are all true.
2. A detected wake word reliably transitions into exactly one
   command-capture cycle, with the wake stream fully stopped for its
   entire duration (Section 9), verified by tests item 16.
3. A sufficiently confident transcript is dispatched through the
   existing, unmodified `CommandRouter.dispatch()` and no other path
   (tests items 11, 15).
4. Every failure mode in Section 15 is handled without a crash and
   without leaking microphone ownership (tests items 5-10, 14).
5. `voice listen`, `voice transcribe`, `voice status`, `voice speak`,
   `voice wake listen`, `voice wake status` are all confirmed
   unchanged in behavior (tests items 17-19; `speech_to_text.py`,
   `audio_capture.py`, `text_to_speech.py`,
   `streaming_audio_capture.py`, `wake_word.py`, and
   `command_router.py` confirmed byte-identical to their pre-EP-049
   state, mirroring EP-047/048's own "confirmed byte-identical"
   verification idiom).
6. No new dependency is added to `requirements.txt` (every component
   EP-049 uses already ships from EP-046/047/048).
7. `Bootstrap.initialize()` never makes a network call for any voice
   subsystem, unchanged (Section 18).
8. All Section 23 Owner Decisions are resolved by the project owner
   before STEP 2 implementation begins — **satisfied**, see Section
   23a.

## 22. Risks and Open Questions

* **Risk — false-positive wake detections during ambient noise/TV/
  conversation:** unchanged from EP-048's own existing, disclosed
  risk (`voice.wake.threshold` is the only existing mitigation);
  EP-049 makes this risk *user-visible* for the first time (a false
  detection now attempts to record and possibly dispatch a command,
  where before it only printed a log line), which is a materially
  different real-world impact even though no new detection logic is
  introduced. Recommend documenting this explicitly in
  `config/config.yaml`'s `voice.wake.assist` comments (Section 14).
* **Risk — multi-interface microphone contention:** unchanged from
  EP-048 Section 15's own already-disclosed, not-solved-by-that-EP
  risk ("does not attempt to solve concurrent multi-interface
  microphone access") — if an operator's single, one-shot `voice
  wake assist` invocation (Owner Decision D2) is in progress (holding
  either `StreamingAudioCapture` during its wake-listening phase or
  `AudioCapture` during its command-capture phase) at the same moment
  another interface separately issues its own `voice listen`/`voice
  speak` command (e.g. via Telegram or the REST API), that second
  command's own capture call will contend for the same input device.
  EP-049 does not add new locking to prevent this — it is the exact
  same class of risk EP-048 already carries forward for a single
  `voice wake listen` invocation, now simply also possible during
  `voice wake assist`'s additional STT phase. Because v1 is strictly
  one-shot (no loop, no background listener), this window is bounded
  to one invocation's duration, not indefinite.

**Resolved (no longer open):** whether EP-049 v1 supports a loop/
repeat mode. Owner Decision D2 (Section 23a) confirms v1 is strictly
one-shot; no loop mode, and no configuration to enable one, exists
in this design.

## 23. Owner Decisions / Decision Log

Per this task's explicit instruction ("Do NOT silently make
architectural decisions where the existing project does not provide
an answer... Identify decisions that require confirmation"), STEP 1
originally identified the following seven questions as unresolved by
the existing project and repository, requiring owner confirmation
before STEP 2 could begin — mirroring EP-046/047/048's own Section 9
→ 9a pattern exactly. **All seven have since been resolved by the
owner; see Section 23a immediately below the table for the
resolution.**

| ID | Question | Options | Recommended | Reason | Impact |
|---|---|---|---|---|---|
| D1 | Should `voice wake assist` remain a foreground, operator-initiated command (like `voice wake listen` today), or should EP-049 also introduce a `Bootstrap`-managed background/always-on variant? | (a) Foreground only — operator runs `voice wake assist` explicitly, exactly like `voice wake listen`; (b) also add an opt-in, `Bootstrap`-managed background thread that runs this loop automatically when a new flag is true | **(a)** | EP-048 Owner Decision D5 explicitly reserved "the full wake → listen → dispatch loop" for EP-049 as its *content*, not as license to also introduce this project's first-ever background thread — that is a separate, larger architectural commitment (thread lifecycle, shutdown ordering, interaction with (b) risk in Section 21) that deserves its own dedicated design pass. This task's own scope boundaries list "a new hidden background daemon" as explicitly disallowed. | Determines whether `Bootstrap.py` gains any new threading logic at all in EP-049 (recommended: no). |
| D2 | Is EP-049 v1 strictly one-shot (one detection → one command → return), or does it also support a bounded/toggle-able loop (repeat until interrupted)? | (a) One-shot only, `voice wake assist` returns a single `CommandResult` after one cycle, with no loop/repeat configuration of any kind; (b) support both, via a configurable toggle, defaulting to one-shot | **(a)** | This task's scope boundary explicitly disallows "continuous conversation" — a repeating single-command loop is arguably different from multi-turn *conversation* (no context carries between commands), but this line is exactly the kind of judgment call this task instructs not to make silently. (a) is the unambiguously safe reading of the stated non-goals. | Determines whether `voice wake assist` has any loop option in v1 at all, and whether any loop-related configuration key exists. |
| D3 | Should the shared "capture → transcribe → confidence-gate → dispatch" logic be factored into a new private helper both `_listen()` and `_wake_assist()` call, or should `_wake_assist()` simply call `self._listen(arguments)` directly, unmodified, as Section 10 currently proposes? | (a) `_wake_assist()` calls `self._listen(arguments)` directly, zero changes to `_listen()`; (b) extract a shared `_capture_transcribe_dispatch()` private helper, have both `_listen()` and `_wake_assist()` call it | **(a)** | (a) is strictly zero-risk to EP-046's existing, already-verified `_listen()` behavior — the literal reuse this task repeatedly asks for ("EP-049 should consume that capability," "do not duplicate"). (b) is marginally cleaner but touches an already-COMPLETE EP's method, which `AI_GENERATION_STANDARD.md`'s "avoid unnecessary changes to already-shipped code" principle (as applied by EP-048 Owner Decision D4's own reasoning) weighs against absent a concrete need. | Determines whether `skill.py`'s existing `_listen()` method body changes at all in EP-049 (recommended: no). |
| D4 | Does `VoiceModule.__init__` need any new parameter beyond the six it already has (`config`, `command_router`, `engine`, `audio_capture`, `tts_engine`, `wake_engine`, `wake_capture`)? | (a) No new parameter — `voice.wake.assist.*` settings are read directly from `config` inside `_wake_assist()`, exactly how `_min_confidence`/`voice.min_confidence` is already read in `__init__` today; (b) add an explicit `wake_assist_enabled: bool`/`speak_on_result: bool` constructor parameter, computed once at `Bootstrap` wiring time | **(a)** | Consistent with how every existing per-action config value (`voice.min_confidence`, thresholds, durations) is already read — either once in `__init__` (mirroring `_min_confidence`) or per-call from the engine/capture objects themselves — rather than added as a growing list of individual boolean constructor flags, which would make `VoiceModule.__init__`'s signature progressively harder to read as more EPs land. | Determines the exact diff to `VoiceModule.__init__`'s signature (recommended: none, or at most reading two new config keys into two new `self._...` attributes, exactly as `_min_confidence` already does). |
| D5 | Exact action name: `voice wake assist`, or an alternative? | (a) `voice wake assist` (one new sub-action under the existing `wake` dispatcher, alongside `listen`/`status`); (b) `voice wake auto`; (c) `voice assist` (a new top-level action, not nested under `wake`) | **(a)** | Reads naturally alongside the existing `wake listen`/`wake status` pair (EP-048 Owner Decision D7's own naming precedent) and correctly signals this is a variant/extension of wake-word handling, not an unrelated new capability. (c) would suggest a broader "assistant" concept not actually being introduced. | Cosmetic but flagged for the same reason EP-046/047/048's own naming decisions were each flagged — cheaper to confirm before STEP 2 than rename after. |
| D6 | Should TTS-on-result be included in EP-049 v1 at all, and if so, on by default or off by default? | (a) Included, off by default (`voice.wake.assist.speak_result: false`, Section 14); (b) included, on by default whenever `voice.tts.enabled` is also true; (c) not included in v1 at all — `voice wake assist` only ever returns/reports text, never speaks, deferring TTS integration entirely to a future EP | **(a)** | This task explicitly allows either (A) report-only or (B) optional-speak, and explicitly forbids making TTS mandatory. (a) delivers the "optionally speak the result" capability this task frames as desirable, while keeping today's default, silent, text-only behavior for any operator who has already enabled `voice.tts.enabled` for unrelated (`voice speak`) reasons but doesn't necessarily want every wake-triggered command narrated aloud. | Determines whether Section 14's `speak_result` key exists in v1, and its default. |
| D7 | Should a wake-triggered command that fails (dispatch `success=False`) or is not understood still resume wake listening automatically (loop mode) / return a failure result (one-shot mode), or should it require explicit operator re-confirmation before listening again? | (a) Always resume/return automatically — a failed command is reported like any other, no special "are you sure" step; (b) after N consecutive failed/misunderstood cycles (loop mode only), stop looping and report, rather than continuing indefinitely | **(a)**, with **(b)** as a possible future refinement, not v1 | (a) matches every existing voice action's existing "report the failure, don't retry automatically" idiom (`_listen()` itself never retries on a failed dispatch). (b) adds new state (a failure counter) this task does not ask for and that isn't needed for one-shot mode (Owner Decision D2) at all. | Determines whether `_wake_assist()` needs any counter/consecutive-failure state (recommended: no, for v1). |

None of these seven items was silently decided by this document.

## 23a. Owner Decisions (received prior to STEP 2) — Resolution of Section 23

The project owner reviewed and approved EP-049 STEP 1 with the
following decisions. STEP 2 has **not** started; these decisions
govern it once it does, mirroring EP-046's Owner Decision set /
EP-047 Owner Decisions D1-D8 / EP-048 Owner Decisions D1-D7's own
resolution precedent.

| # | Question | Owner Decision |
|---|---|---|
| D1 | Foreground vs. background | **(a) Foreground only**, confirming Section 23's recommendation. EP-049 must **not** introduce any `Bootstrap`-managed background thread, daemon, always-on listener, or automatic startup behavior. `voice wake assist` is invoked exactly as `voice wake listen` is today — explicitly, by the operator. |
| D2 | One-shot vs. loop | **(a) One-shot only.** EP-049 v1 performs exactly one cycle: wake detection → one command capture → STT → dispatch → optional TTS → return a `CommandResult` and terminate. Loop mode is **not** implemented. No `voice.wake.assist.one_shot` key, and no repeat/continuous-listening configuration of any kind, is added. Continuous/repeating behavior is deferred to a possible future EP. |
| D3 | Shared helper vs. direct reuse | **(a) Direct reuse of `self._listen(arguments)`.** No new shared helper is extracted. `_listen()`'s existing implementation is **not** modified. `_wake_assist()` calls the existing `_listen(arguments)` directly, after the wake stream has been stopped. |
| D4 | New constructor parameter(s) | **(a) No new `VoiceModule` constructor parameters.** EP-049 configuration (`voice.wake.assist.*`) is read directly from the existing `config` object already held by `VoiceModule`, wherever it is needed. No wake-assist-specific constructor flags are added. |
| D5 | Action name | **(a) `voice wake assist`**, confirming Section 23's recommendation. Implemented as a new sub-action under the existing `wake` dispatcher (`_wake()`, alongside `listen`/`status`) — not `voice assist`, not `voice wake auto`. |
| D6 | TTS-on-result | **(a) Included, off by default.** `voice.wake.assist.enabled: false` and `voice.wake.assist.speak_result: false` are added (Section 14). TTS is never mandatory. When `speak_result: true` and a TTS engine is available, the dispatched `CommandResult.message` is spoken via the existing TTS engine (Section 13, **SPEAKING** state). When TTS is unavailable (`tts_engine is None`), speaking is skipped gracefully — the command's own execution and result are never affected by TTS availability. |
| D7 | Retry / reconfirmation on failure | **(a) No special retry/reconfirmation logic.** A failed, rejected, misunderstood, or low-confidence command is handled entirely through the existing `CommandResult`/`TranscriptionResult` error mechanisms (Section 15). EP-049 introduces no failure counters, no retry loops, no confirmation dialogs, and no additional state to support this. |

All seven Section 23 questions are now resolved; none remains open
from the original list.

**Confirmed non-goals (restated, not new — consistent with Section
4):** no loop/repeat mode, no `one_shot` (or any other loop-related)
configuration key, no Bootstrap-managed background thread or daemon,
no automatic startup behavior, no new `VoiceModule` constructor
parameters, no modification of `_listen()`'s existing implementation,
no shared helper extraction, no mandatory TTS, and no
retry/reconfirmation/failure-counter state of any kind.

**STEP 1 boundary maintained while resolving these decisions:** no
file under `src/`, `tests/`, or `config/` was modified, and
`requirements.txt` was not modified, to produce this resolution.
STEP 2 has not started and begins only on the owner's explicit
instruction.

---

STEP 2 must not begin until the owner has resolved Section 23 —
resolved above in Section 23a.

---

## STEP 1 Boundary Statement

This update performed only editing of `EP049_DESIGN.md` itself, to
record the owner's approved resolution of Section 23 (Section 23a).
It did **not**:

* Create or modify any file under `src/`.
* Create or modify any file under `tests/`.
* Modify `config/config.yaml`.
* Modify `requirements.txt`.
* Modify `src/skills/voice/skill.py`, `audio_capture.py`,
  `streaming_audio_capture.py`, `speech_to_text.py`,
  `text_to_speech.py`, or `wake_word.py`.
* Modify `src/core/command_router.py`.
* Modify `src/bootstrap.py`.
* Modify any EP-046/047/048 design or audit document.
* Modify `docs/architecture/JARVIS_ROADMAP.md` or `docs/BACKLOG.md`.
* Commit or push anything.
* Start STEP 2.

All seven Section 23 Owner Decisions are now resolved (Section 23a).
STEP 2 (implementation) has still not begun and begins only on the
owner's explicit, separate instruction to proceed.
