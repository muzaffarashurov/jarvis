"""Real engineering tests for EP-048 STEP 2 - Wake Word.

Single combined test suite (NAME = "EP048"), following the same
precedent EP-043/EP-045/EP-046/EP-047 already established: this
sidesteps the pre-existing `TestRegistry` NAME-collision technical
debt (docs/BACKLOG.md) entirely rather than triggering it.

Deterministic: no physical microphone, no real audio, no network
access, and no automatic model download are required or exercised.
`WakeWordEngine`/`StreamingAudioCapture` are exercised through fakes
(`_FakeWakeWordEngine`/`_FakeStreamingAudioCapture` below) for every
`VoiceModule` integration scenario; the *real* `OpenWakeWordEngine`/
`StreamingAudioCapture` classes are exercised directly wherever their
behavior does not require a loaded model
(construction validation, missing-model-directory/missing-model-file
handling). `StreamingAudioCapture.start()`'s real, physical-device
behavior is exercised environment-independently: this suite makes no
assumption about whether a microphone is present in the environment
it runs in (a device-less CI sandbox and a real workstation with a
working microphone are both valid, and both are asserted against
correctly -- see `_test_streaming_audio_capture_reports_no_device_gracefully`).

One scenario (an actual wake phrase detected from real audio through
a real, loaded openWakeWord model) is not exercised here: no
openWakeWord model files exist in this environment (owner Decision
D3 -- manual model setup only, no automatic downloader, and none was
placed here). That case is reported via `self.skip()`, matching
`tests/EP046/test_voice.py`'s own "skipped, not failed, when the
model directory/files are absent" precedent for Vosk -- not silently
omitted.

Covers (EP-048 STEP 2 instructions, items 1-25):
    1.  WakeWordEngine interface / WakeWordDetectionResult shape.
    2.  OpenWakeWordEngine construction (real class: missing model
        dir, missing model files; real model load not available in
        this environment -- skipped).
    3.  Invalid configuration (empty wake_word, out-of-range
        threshold).
    4.  Missing model handling (missing model_dir, missing model
        files under an existing model_dir).
    5.  Model availability reporting.
    6.  Supported wake word/model reporting.
    7.  StreamingCaptureStartResult / audio streaming interface
        shape.
    8.  StreamingAudioCapture construction (real class, real
        `sounddevice`).
    9.  StreamingAudioCapture: `start()`'s graceful contract, real
        class, environment-independent (accepts either a real
        device's successful start or a real "no input device"
        failure -- never a raised exception either way).
    10. Audio chunks processing (fake capture -> fake engine, one
        `process_frame()` call per yielded frame).
    11. Wake detection (a later frame's score meets the threshold).
    12. No detection (no frame's score meets the threshold).
    13. WakeWordDetectionResult shape (detected/score/wake_word).
    14. `voice wake listen` end to end (detected, not detected,
        microphone failure, disabled).
    15. `voice wake status` end to end (enabled, disabled).
    16. Disabled configuration (`wake_engine=None`/
        `wake_capture=None`) reports a clear failure, never a crash.
    17. VoiceModule integration: unknown `wake` sub-action, `voice
        help` lists the new actions, existing actions/namespace
        unaffected.
    18. Bootstrap wiring: `voice.wake.enabled` false/absent/invalid
        `model_dir` all degrade safely with no crash.
    19. Independent Wake-Word/STT/TTS enable/disable (owner Decision
        D6): each of the three flags, alone, registers the "voice"
        namespace; all three false does not.
    20. STT regression compatibility ('voice listen'/'voice
        transcribe'/'voice status' unaffected by the new, defaulted
        wake_engine/wake_capture parameters).
    21. TTS regression compatibility ('voice speak' unaffected by
        the same).
    22. No auto-dispatch after detection.
    23. No automatic STT after detection.
    24. No automatic TTS after detection.
    25. No audio files written to disk by StreamingAudioCapture.

Post-STEP-3 bugfix coverage (real Windows verification found
`OpenWakeWordEngine` only looked for the bare `<wake_word>.onnx`
filename, never openWakeWord's own official versioned release naming
e.g. `hey_jarvis_v0.1.onnx` -- see `wake_word.py`'s module docstring
and `resolve_wakeword_model_path()`):
    26. Exact `<wake_word>.onnx` resolution (still preferred over any
        versioned candidate, if both are present).
    27. Official versioned `<wake_word>_v0.1.onnx` resolution (the
        exact real-world scenario reported).
    28. Missing model (zero candidates of either naming convention).
    29. Multiple versioned candidates / ambiguity (never silently
        picks a version).
    30. Successful real `OpenWakeWordEngine` construction resolving a
        versioned-only model directory end to end (shared model files
        + a `hey_jarvis_v0.1.onnx`-only wake-word file), confirmed via
        the real `resolve_wakeword_model_path()` call `__init__` makes
        -- real `openwakeword.model.Model()` construction itself still
        requires genuine model bytes this environment does not have,
        so that specific step is disclosed via `self.skip()`
        (Section 2), not claimed.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from src.bootstrap import Bootstrap
from src.core.command_router import CommandRouter
from src.skills.voice.audio_capture import AudioCaptureResult
from src.skills.voice.skill import VoiceModule
from src.skills.voice.speech_to_text import TranscriptionResult
from src.skills.voice.streaming_audio_capture import (
    StreamingAudioCapture,
    StreamingCaptureStartResult,
)
from src.skills.voice.text_to_speech import SynthesisResult
from src.skills.voice.wake_word import (
    OpenWakeWordEngine,
    WakeWordDetectionResult,
    WakeWordEngineError,
    resolve_wakeword_model_path,
)
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry
from tests.EP045.test_web_dashboard import _ChdirGuard
from tests.EP046.test_voice import (
    _FakeAudioCapture,
    _FakeSpeechToTextEngine,
    _RecordingModule,
    _config_with,
    _write_voice_bootstrap_config,
)
from tests.EP047.test_voice_tts import _FakeTextToSpeechEngine


@dataclass
class _FakeWakeWordEngine:
    """Fake WakeWordEngine: returns pre-canned per-frame results in order.

    Records every `process_frame()` call (`self.calls`) so tests can
    assert exactly how many frames were scored before `voice wake
    listen` returned -- e.g. that it stops at the first detection
    (item 11) or scores every frame when none detects (item 12).
    """

    canned_results: list[WakeWordDetectionResult]
    wake_word_value: str = "hey_jarvis"
    threshold_value: float = 0.5
    model_dir_value: str = "data/models/wake"
    frame_length_value: int = 1280
    sample_rate_value: int = 16000
    model_available_value: bool = True

    def __post_init__(self) -> None:
        self.calls: list[bytes] = []
        self._index = 0

    @property
    def frame_length(self) -> int:
        return self.frame_length_value

    @property
    def sample_rate(self) -> int:
        return self.sample_rate_value

    @property
    def wake_word(self) -> str:
        return self.wake_word_value

    @property
    def threshold(self) -> float:
        return self.threshold_value

    @property
    def model_dir(self) -> str:
        return self.model_dir_value

    def model_available(self) -> bool:
        return self.model_available_value

    def process_frame(self, pcm_frame: bytes) -> WakeWordDetectionResult:
        self.calls.append(pcm_frame)
        if self._index < len(self.canned_results):
            result = self.canned_results[self._index]
        else:
            result = WakeWordDetectionResult(
                detected=False, score=0.0, wake_word=self.wake_word_value
            )
        self._index += 1
        return result


@dataclass
class _FakeStreamingAudioCapture:
    """Fake StreamingAudioCapture: yields a pre-canned list of frames, never touches sounddevice."""

    frames_to_yield: list[bytes]
    start_result: StreamingCaptureStartResult = field(
        default_factory=lambda: StreamingCaptureStartResult(success=True)
    )

    def __post_init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> StreamingCaptureStartResult:
        self.start_calls += 1
        return self.start_result

    def frames(self, timeout_seconds: float = 1.0) -> Iterator[bytes]:
        for frame in self.frames_to_yield:
            yield frame

    def stop(self) -> None:
        self.stop_calls += 1


@dataclass
class _CountingAudioCapture:
    """Fake AudioCapture that also counts `capture()` calls.

    Used only to prove `voice wake listen` never triggers EP-046's
    STT capture path (item 23) -- `tests/EP046/test_voice.py`'s own
    `_FakeAudioCapture` does not track call counts, and adding that
    there would be an unrelated change to an already-shipped EP-046
    test file, so this local, EP-048-only counting variant is used
    instead.
    """

    canned_result: AudioCaptureResult

    def __post_init__(self) -> None:
        self.call_count = 0

    def capture(self) -> AudioCaptureResult:
        self.call_count += 1
        return self.canned_result


def _write_voice_wake_bootstrap_config(directory: Path, voice_section: str) -> None:
    """Write a minimal bootstrap config.yaml (EP-045's fixture) plus a 'voice:' block."""
    _write_voice_bootstrap_config(directory, voice_section=voice_section)


@TestRegistry.register
class WakeWordTest(BaseTest):
    NAME = "EP048"

    def run(self):
        self._test_wake_word_detection_result_shape()

        self._test_open_wake_word_engine_rejects_missing_model_dir()
        self._test_open_wake_word_engine_rejects_empty_wake_word()
        self._test_open_wake_word_engine_rejects_invalid_threshold()
        self._test_open_wake_word_engine_rejects_missing_model_files()
        self._test_real_wake_word_detection_with_loaded_model_not_available_in_this_environment()

        self._test_resolve_wakeword_model_path_exact_match()
        self._test_resolve_wakeword_model_path_exact_match_preferred_over_versioned()
        self._test_resolve_wakeword_model_path_versioned_match()
        self._test_resolve_wakeword_model_path_missing_raises()
        self._test_resolve_wakeword_model_path_ambiguous_raises()
        self._test_open_wake_word_engine_resolves_versioned_model_construction()

        self._test_streaming_capture_start_result_shape()
        self._test_streaming_audio_capture_constructs_with_real_sounddevice()
        self._test_streaming_audio_capture_reports_no_device_gracefully()
        self._test_streaming_audio_capture_writes_no_files_to_disk()

        self._test_fake_capture_yields_frames_and_engine_processes_each()
        self._test_fake_engine_stops_scoring_at_first_detection()

        self._test_voice_module_wake_listen_detects_and_reports()
        self._test_voice_module_wake_listen_no_detection_reports_ended()
        self._test_voice_module_wake_listen_microphone_failure_returns_failure()
        self._test_voice_module_wake_listen_disabled_when_engine_none()
        self._test_voice_module_wake_listen_disabled_when_capture_none()

        self._test_voice_module_wake_status_reports_details()
        self._test_voice_module_wake_status_disabled_when_engine_none()

        self._test_voice_module_wake_unknown_subaction_returns_usage()
        self._test_voice_module_wake_no_subaction_returns_usage()
        self._test_voice_module_help_lists_wake_actions()

        self._test_voice_module_wake_listen_never_dispatches()
        self._test_voice_module_wake_listen_never_triggers_stt()
        self._test_voice_module_wake_listen_never_triggers_tts()

        self._test_voice_module_listen_unaffected_by_missing_wake_params()
        self._test_voice_module_transcribe_unaffected_by_missing_wake_params()
        self._test_voice_module_status_unaffected_by_missing_wake_params()
        self._test_voice_module_speak_unaffected_by_missing_wake_params()

        self._test_voice_module_listen_reports_disabled_when_engine_none()
        self._test_voice_module_status_reports_disabled_when_engine_none()

        self._test_bootstrap_config_defaults_wake_disabled()
        self._test_bootstrap_skips_voice_when_all_three_disabled()
        self._test_bootstrap_starts_voice_when_only_wake_enabled()
        self._test_bootstrap_starts_voice_when_only_tts_enabled()
        self._test_bootstrap_starts_voice_when_only_stt_enabled_regression()
        self._test_bootstrap_disables_wake_on_missing_model_files_but_keeps_stt_tts()

        return self.result

    # ---------- WakeWordDetectionResult / WakeWordEngine interface ----------

    def _test_wake_word_detection_result_shape(self) -> None:
        result = WakeWordDetectionResult(detected=True, score=0.87, wake_word="hey_jarvis")
        self.assert_true(result.detected)
        self.assert_equal(result.score, 0.87)
        self.assert_equal(result.wake_word, "hey_jarvis")

    # ---------- OpenWakeWordEngine construction ----------

    def _test_open_wake_word_engine_rejects_missing_model_dir(self) -> None:
        config = _config_with({"voice": {"wake": {"model_dir": "/nonexistent/EP048/model/dir"}}})
        raised = False
        try:
            OpenWakeWordEngine(config=config)
        except WakeWordEngineError as exc:
            raised = True
            self.assert_true("model_dir" in str(exc))
        self.assert_true(raised, "Expected WakeWordEngineError for missing 'voice.wake.model_dir'")

    def _test_open_wake_word_engine_rejects_empty_wake_word(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _config_with({"voice": {"wake": {"model_dir": tmp_dir, "wake_word": "   "}}})
            raised = False
            try:
                OpenWakeWordEngine(config=config)
            except WakeWordEngineError:
                raised = True
            self.assert_true(raised, "Expected WakeWordEngineError for empty 'voice.wake.wake_word'")

    def _test_open_wake_word_engine_rejects_invalid_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _config_with({"voice": {"wake": {"model_dir": tmp_dir, "threshold": 2.0}}})
            raised = False
            try:
                OpenWakeWordEngine(config=config)
            except WakeWordEngineError:
                raised = True
            self.assert_true(raised, "Expected WakeWordEngineError for out-of-range threshold")

            config = _config_with({"voice": {"wake": {"model_dir": tmp_dir, "threshold": "not-a-number"}}})
            raised = False
            try:
                OpenWakeWordEngine(config=config)
            except WakeWordEngineError:
                raised = True
            self.assert_true(raised, "Expected WakeWordEngineError for a non-numeric threshold")

    def _test_open_wake_word_engine_rejects_missing_model_files(self) -> None:
        # An existing, but empty, model_dir -- the directory itself is
        # valid, but none of the three required openWakeWord model
        # files (melspectrogram.onnx / embedding_model.onnx /
        # <wake_word>.onnx) have been manually placed there (owner
        # Decision D3: no automatic download to fill this gap).
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = _config_with({"voice": {"wake": {"model_dir": tmp_dir}}})
            raised = False
            try:
                OpenWakeWordEngine(config=config)
            except WakeWordEngineError as exc:
                raised = True
                self.assert_true("melspectrogram.onnx" in str(exc) or "Missing required" in str(exc))
            self.assert_true(raised, "Expected WakeWordEngineError for missing model files")

    def _test_real_wake_word_detection_with_loaded_model_not_available_in_this_environment(self) -> None:
        # No openWakeWord model files exist in this environment (owner
        # Decision D3: manual setup only). This is the one scenario
        # this suite allows to be skipped rather than failed, mirroring
        # tests/EP046/test_voice.py's identical precedent for Vosk.
        self.skip()

    # ---------- Post-STEP-3 bugfix: wake-word model filename resolution ----------

    def _test_resolve_wakeword_model_path_exact_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_dir = Path(tmp_dir)
            exact = model_dir / "hey_jarvis.onnx"
            exact.write_bytes(b"fake-model-bytes")

            resolved = resolve_wakeword_model_path(model_dir, "hey_jarvis")
            self.assert_equal(resolved, exact)

    def _test_resolve_wakeword_model_path_exact_match_preferred_over_versioned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_dir = Path(tmp_dir)
            exact = model_dir / "hey_jarvis.onnx"
            exact.write_bytes(b"fake-model-bytes")
            (model_dir / "hey_jarvis_v0.1.onnx").write_bytes(b"fake-model-bytes")

            resolved = resolve_wakeword_model_path(model_dir, "hey_jarvis")
            self.assert_equal(
                resolved, exact, "An exact '<wake_word>.onnx' match must win over any versioned candidate"
            )

    def _test_resolve_wakeword_model_path_versioned_match(self) -> None:
        # The exact real-world scenario reported: only the official
        # openWakeWord versioned filename is present, no bare
        # '<wake_word>.onnx'.
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_dir = Path(tmp_dir)
            versioned = model_dir / "hey_jarvis_v0.1.onnx"
            versioned.write_bytes(b"fake-model-bytes")
            # Unrelated files that happen to live alongside it (as in
            # the real report's directory listing) must not confuse
            # resolution.
            (model_dir / "silero_vad.onnx").write_bytes(b"fake-model-bytes")
            (model_dir / "melspectrogram.onnx").write_bytes(b"fake-model-bytes")
            (model_dir / "embedding_model.onnx").write_bytes(b"fake-model-bytes")

            resolved = resolve_wakeword_model_path(model_dir, "hey_jarvis")
            self.assert_equal(resolved, versioned)

    def _test_resolve_wakeword_model_path_missing_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_dir = Path(tmp_dir)
            raised = False
            try:
                resolve_wakeword_model_path(model_dir, "hey_jarvis")
            except WakeWordEngineError as exc:
                raised = True
                self.assert_true("hey_jarvis" in str(exc))
            self.assert_true(raised, "Expected WakeWordEngineError when no candidate model file exists")

    def _test_resolve_wakeword_model_path_ambiguous_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_dir = Path(tmp_dir)
            (model_dir / "hey_jarvis_v0.1.onnx").write_bytes(b"fake-model-bytes")
            (model_dir / "hey_jarvis_v0.2.onnx").write_bytes(b"fake-model-bytes")

            raised = False
            try:
                resolve_wakeword_model_path(model_dir, "hey_jarvis")
            except WakeWordEngineError as exc:
                raised = True
                self.assert_true("hey_jarvis_v0.1.onnx" in str(exc))
                self.assert_true("hey_jarvis_v0.2.onnx" in str(exc))
            self.assert_true(
                raised, "Expected WakeWordEngineError for multiple versioned candidates -- must never silently pick one"
            )

    def _test_open_wake_word_engine_resolves_versioned_model_construction(self) -> None:
        # Reproduces the reported bug's exact directory layout end to
        # end through OpenWakeWordEngine.__init__ itself (not just the
        # standalone resolver): shared model files present, plus only
        # the official versioned wake-word filename -- construction
        # must reach openwakeword.model.Model(...) (i.e. resolution
        # must succeed) rather than failing at the
        # "missing model file(s)" check. Real Model() construction
        # itself requires genuine ONNX model bytes this environment
        # does not have (Section 2's disclosed real-model-load gap),
        # so a failure originating from openwakeword/onnxruntime
        # itself (invalid model bytes) is accepted here as proof
        # resolution succeeded; a WakeWordEngineError whose message
        # still describes a *missing/ambiguous file* would mean the
        # bugfix regressed and must fail this test.
        with tempfile.TemporaryDirectory() as tmp_dir:
            model_dir = Path(tmp_dir)
            (model_dir / "melspectrogram.onnx").write_bytes(b"fake-model-bytes")
            (model_dir / "embedding_model.onnx").write_bytes(b"fake-model-bytes")
            (model_dir / "hey_jarvis_v0.1.onnx").write_bytes(b"fake-model-bytes")
            (model_dir / "silero_vad.onnx").write_bytes(b"fake-model-bytes")

            config = _config_with({"voice": {"wake": {"model_dir": str(model_dir)}}})
            try:
                engine = OpenWakeWordEngine(config=config)
            except WakeWordEngineError as exc:
                message = str(exc)
                self.assert_false(
                    "Missing required" in message or "No openWakeWord model file found" in message,
                    f"Resolution must have found 'hey_jarvis_v0.1.onnx' -- got: {message}",
                )
                # A failure here is openwakeword/onnxruntime rejecting
                # the fake (non-real) model bytes -- expected in this
                # environment (Section 2), not a resolution failure.
                return
            # If real openwakeword+onnxruntime happens to accept the
            # placeholder bytes in some future version, construction
            # succeeding is an even stronger confirmation of the fix.
            self.assert_equal(engine.wake_word, "hey_jarvis")
            self.assert_equal(engine.model_key, "hey_jarvis_v0.1")

    # ---------- StreamingAudioCapture ----------

    def _test_streaming_capture_start_result_shape(self) -> None:
        ok = StreamingCaptureStartResult(success=True)
        self.assert_true(ok.success)
        self.assert_equal(ok.error, None)

        failed = StreamingCaptureStartResult(success=False, error="no input device")
        self.assert_false(failed.success)
        self.assert_equal(failed.error, "no input device")

    def _test_streaming_audio_capture_constructs_with_real_sounddevice(self) -> None:
        config = _config_with({"voice": {"wake": {"sample_rate": 16000, "frame_length": 1280}}})
        capture = StreamingAudioCapture(config=config)
        self.assert_equal(capture.sample_rate, 16000)
        self.assert_equal(capture.frame_length, 1280)
        self.assert_false(capture.is_running)

    def _test_streaming_audio_capture_reports_no_device_gracefully(self) -> None:
        # Environment-independent: this suite makes no assumption
        # about whether a microphone is physically present. Real
        # hardware verification (EP-048 bug-fix report, Windows/
        # Realtek microphone) confirmed a genuine input device makes
        # start() succeed (result.success=True, result.error=None);
        # a device-less sandbox makes it fail gracefully instead
        # (result.success=False, result.error is not None). Both are
        # the same underlying contract (EP048_DESIGN.md Section 5.5:
        # never raise) -- this test asserts whichever real outcome
        # this environment's real sounddevice/PortAudio call actually
        # produces, rather than assuming one.
        config = _config_with({"voice": {"wake": {"sample_rate": 16000, "device": None}}})
        capture = StreamingAudioCapture(config=config)
        result = capture.start()

        if result.success:
            # A real input device is available in this environment.
            self.assert_true(result.success)
            self.assert_equal(result.error, None)
            self.assert_true(capture.is_running)
        else:
            # No input device is available in this environment.
            self.assert_false(result.success)
            self.assert_not_none(result.error)
            self.assert_false(capture.is_running)

        # stop() must remain safe to call in either case.
        capture.stop()
        self.assert_false(capture.is_running)

    def _test_streaming_audio_capture_writes_no_files_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            with _ChdirGuard(directory):
                config = _config_with({"voice": {"wake": {"sample_rate": 16000, "device": None}}})
                capture = StreamingAudioCapture(config=config)
                # Environment-independent: start() may succeed (real
                # device present) or fail gracefully (no device) --
                # either way, no file may ever be written to disk.
                capture.start()
                capture.stop()
                self.assert_equal(
                    os.listdir(directory),
                    [],
                    "StreamingAudioCapture must never write any file (wav/mp3/temp) to disk",
                )

    # ---------- fake capture -> fake engine wiring ----------

    def _test_fake_capture_yields_frames_and_engine_processes_each(self) -> None:
        engine = _FakeWakeWordEngine(
            canned_results=[
                WakeWordDetectionResult(detected=False, score=0.1, wake_word="hey_jarvis"),
                WakeWordDetectionResult(detected=False, score=0.2, wake_word="hey_jarvis"),
                WakeWordDetectionResult(detected=False, score=0.3, wake_word="hey_jarvis"),
            ]
        )
        capture = _FakeStreamingAudioCapture(frames_to_yield=[b"\x00" * 2560, b"\x01" * 2560, b"\x02" * 2560])
        module = self._build_voice_module(wake_engine=engine, wake_capture=capture)

        result = module.execute("wake", ["listen"])
        self.assert_false(result.success)
        self.assert_equal(len(engine.calls), 3, "Every yielded frame must be scored")
        self.assert_equal(capture.start_calls, 1)
        self.assert_equal(capture.stop_calls, 1, "stop() must be called even without a detection")

    def _test_fake_engine_stops_scoring_at_first_detection(self) -> None:
        engine = _FakeWakeWordEngine(
            canned_results=[
                WakeWordDetectionResult(detected=False, score=0.1, wake_word="hey_jarvis"),
                WakeWordDetectionResult(detected=True, score=0.91, wake_word="hey_jarvis"),
                WakeWordDetectionResult(detected=True, score=0.95, wake_word="hey_jarvis"),
            ]
        )
        capture = _FakeStreamingAudioCapture(
            frames_to_yield=[b"\x00" * 2560, b"\x01" * 2560, b"\x02" * 2560]
        )
        module = self._build_voice_module(wake_engine=engine, wake_capture=capture)

        result = module.execute("wake", ["listen"])
        self.assert_true(result.success)
        self.assert_equal(len(engine.calls), 2, "Scoring must stop at the first detection")
        self.assert_equal(capture.stop_calls, 1)

    # ---------- VoiceModule: voice wake listen ----------

    def _test_voice_module_wake_listen_detects_and_reports(self) -> None:
        engine = _FakeWakeWordEngine(
            canned_results=[
                WakeWordDetectionResult(detected=False, score=0.1, wake_word="hey_jarvis"),
                WakeWordDetectionResult(detected=True, score=0.83, wake_word="hey_jarvis"),
            ]
        )
        capture = _FakeStreamingAudioCapture(frames_to_yield=[b"\x00" * 2560, b"\x01" * 2560])
        module = self._build_voice_module(wake_engine=engine, wake_capture=capture)

        result = module.execute("wake", ["listen"])
        self.assert_true(result.success)
        self.assert_true("hey_jarvis" in result.message)
        self.assert_true("0.83" in result.message)

    def _test_voice_module_wake_listen_no_detection_reports_ended(self) -> None:
        engine = _FakeWakeWordEngine(
            canned_results=[
                WakeWordDetectionResult(detected=False, score=0.1, wake_word="hey_jarvis"),
            ]
        )
        capture = _FakeStreamingAudioCapture(frames_to_yield=[b"\x00" * 2560])
        module = self._build_voice_module(wake_engine=engine, wake_capture=capture)

        result = module.execute("wake", ["listen"])
        self.assert_false(result.success)
        self.assert_true("ended without a detection" in result.message)

    def _test_voice_module_wake_listen_microphone_failure_returns_failure(self) -> None:
        engine = _FakeWakeWordEngine(canned_results=[])
        capture = _FakeStreamingAudioCapture(
            frames_to_yield=[],
            start_result=StreamingCaptureStartResult(success=False, error="microphone unavailable: no device"),
        )
        module = self._build_voice_module(wake_engine=engine, wake_capture=capture)

        result = module.execute("wake", ["listen"])
        self.assert_false(result.success)
        self.assert_true("Microphone error" in result.message)
        self.assert_equal(capture.stop_calls, 0, "stop() must not be called when start() itself failed")

    def _test_voice_module_wake_listen_disabled_when_engine_none(self) -> None:
        module = self._build_voice_module(wake_engine=None, wake_capture=_FakeStreamingAudioCapture(frames_to_yield=[]))
        result = module.execute("wake", ["listen"])
        self.assert_false(result.success)
        self.assert_true("not enabled" in result.message.lower())

    def _test_voice_module_wake_listen_disabled_when_capture_none(self) -> None:
        module = self._build_voice_module(wake_engine=_FakeWakeWordEngine(canned_results=[]), wake_capture=None)
        result = module.execute("wake", ["listen"])
        self.assert_false(result.success)
        self.assert_true("not enabled" in result.message.lower())

    # ---------- VoiceModule: voice wake status ----------

    def _test_voice_module_wake_status_reports_details(self) -> None:
        engine = _FakeWakeWordEngine(canned_results=[], wake_word_value="hey_jarvis", threshold_value=0.6)
        module = self._build_voice_module(
            wake_engine=engine, wake_capture=_FakeStreamingAudioCapture(frames_to_yield=[])
        )
        result = module.execute("wake", ["status"])
        self.assert_true(result.success)
        self.assert_true("hey_jarvis" in result.message)
        self.assert_true("0.60" in result.message)
        self.assert_true("available" in result.message)
        self.assert_true("Russian" in result.message and "Uzbek" in result.message)

    def _test_voice_module_wake_status_disabled_when_engine_none(self) -> None:
        module = self._build_voice_module(wake_engine=None, wake_capture=None)
        result = module.execute("wake", ["status"])
        self.assert_true(result.success)
        self.assert_true("Enabled : No" in result.message)

    # ---------- VoiceModule integration ----------

    def _test_voice_module_wake_unknown_subaction_returns_usage(self) -> None:
        module = self._build_voice_module(wake_engine=None, wake_capture=None)
        result = module.execute("wake", ["dance"])
        self.assert_false(result.success)
        self.assert_true("Usage:" in result.message)

    def _test_voice_module_wake_no_subaction_returns_usage(self) -> None:
        module = self._build_voice_module(wake_engine=None, wake_capture=None)
        result = module.execute("wake", [])
        self.assert_false(result.success)
        self.assert_true("Usage:" in result.message)

    def _test_voice_module_help_lists_wake_actions(self) -> None:
        module = self._build_voice_module(wake_engine=None, wake_capture=None)
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("voice wake listen" in result.message)
        self.assert_true("voice wake status" in result.message)
        # EP-046/EP-047 actions must still be listed too (regression check).
        self.assert_true("voice listen" in result.message)
        self.assert_true("voice transcribe" in result.message)
        self.assert_true("voice status" in result.message)
        self.assert_true("voice speak" in result.message)

    # ---------- Architectural boundary: detection-only (owner Decision D5) ----------

    def _test_voice_module_wake_listen_never_dispatches(self) -> None:
        router = CommandRouter()
        echo = _RecordingModule("echo")
        router.register(echo)

        engine = _FakeWakeWordEngine(
            canned_results=[WakeWordDetectionResult(detected=True, score=0.9, wake_word="hey_jarvis")]
        )
        capture = _FakeStreamingAudioCapture(frames_to_yield=[b"\x00" * 2560])
        module = self._build_voice_module(wake_engine=engine, wake_capture=capture, command_router=router)

        result = module.execute("wake", ["listen"])
        self.assert_true(result.success)
        self.assert_equal(echo.call_count, 0, "'voice wake listen' must never call CommandRouter.dispatch()")

    def _test_voice_module_wake_listen_never_triggers_stt(self) -> None:
        stt_engine = _FakeSpeechToTextEngine(
            canned_result=TranscriptionResult(success=True, text="", confidence=None, language="en"),
            languages=["en"],
        )
        stt_audio_capture = _CountingAudioCapture(
            canned_result=AudioCaptureResult(success=True, pcm_data=b"", sample_rate=16000)
        )
        wake_engine = _FakeWakeWordEngine(
            canned_results=[WakeWordDetectionResult(detected=True, score=0.9, wake_word="hey_jarvis")]
        )
        wake_capture = _FakeStreamingAudioCapture(frames_to_yield=[b"\x00" * 2560])
        module = VoiceModule(
            config=_config_with({}),
            command_router=CommandRouter(),
            engine=stt_engine,
            audio_capture=stt_audio_capture,
            wake_engine=wake_engine,
            wake_capture=wake_capture,
        )

        result = module.execute("wake", ["listen"])
        self.assert_true(result.success)
        self.assert_equal(
            stt_audio_capture.call_count, 0, "'voice wake listen' must never trigger AudioCapture.capture()"
        )

    def _test_voice_module_wake_listen_never_triggers_tts(self) -> None:
        tts_engine = _FakeTextToSpeechEngine(
            canned_result=SynthesisResult(success=True, language="en"), languages=["en"]
        )
        wake_engine = _FakeWakeWordEngine(
            canned_results=[WakeWordDetectionResult(detected=True, score=0.9, wake_word="hey_jarvis")]
        )
        wake_capture = _FakeStreamingAudioCapture(frames_to_yield=[b"\x00" * 2560])
        module = self._build_voice_module(
            wake_engine=wake_engine, wake_capture=wake_capture, tts_engine=tts_engine
        )

        result = module.execute("wake", ["listen"])
        self.assert_true(result.success)
        self.assert_equal(tts_engine.calls, [], "'voice wake listen' must never call TextToSpeechEngine.synthesize()")

    # ---------- EP-046/EP-047 regression checks (unaffected by the additive change) ----------

    def _test_voice_module_listen_unaffected_by_missing_wake_params(self) -> None:
        engine = _FakeSpeechToTextEngine(
            canned_result=TranscriptionResult(
                success=True, text="echo say hello", confidence=0.95, language="en"
            ),
            languages=["en"],
        )
        audio_capture = _FakeAudioCapture(
            canned_result=AudioCaptureResult(success=True, pcm_data=b"\x00\x00" * 100, sample_rate=16000)
        )
        router = CommandRouter()
        router.register(_RecordingModule("echo"))
        module = VoiceModule(
            config=_config_with({}),
            command_router=router,
            engine=engine,
            audio_capture=audio_capture,
            # wake_engine/wake_capture intentionally omitted -- must
            # default to None and must not affect 'voice listen'.
        )
        result = module.execute("listen", [])
        self.assert_true(result.success)

    def _test_voice_module_transcribe_unaffected_by_missing_wake_params(self) -> None:
        module = self._build_voice_module(wake_engine=None, wake_capture=None)
        result = module.execute("transcribe", [])
        self.assert_true(result.success)
        self.assert_true("Confidence" in result.message)

    def _test_voice_module_status_unaffected_by_missing_wake_params(self) -> None:
        module = self._build_voice_module(
            wake_engine=None, wake_capture=None, languages=["ru", "uz", "en"]
        )
        result = module.execute("status", [])
        self.assert_true(result.success)
        self.assert_true("ru" in result.message)
        self.assert_true("uz" in result.message)
        self.assert_true("en" in result.message)

    def _test_voice_module_speak_unaffected_by_missing_wake_params(self) -> None:
        tts_engine = _FakeTextToSpeechEngine(
            canned_result=SynthesisResult(success=True, language="en"), languages=["en"]
        )
        module = self._build_voice_module(wake_engine=None, wake_capture=None, tts_engine=tts_engine)
        result = module.execute("speak", ["hello", "there"])
        self.assert_true(result.success)
        self.assert_true("hello there" in result.message)

    def _test_voice_module_listen_reports_disabled_when_engine_none(self) -> None:
        # EP-048/owner Decision D6: STT may now be None (Wake-Word-only
        # or TTS-only operation) -- 'voice listen' must report a clear
        # failure, never a crash/AttributeError.
        module = VoiceModule(
            config=_config_with({}),
            command_router=CommandRouter(),
            engine=None,
            audio_capture=None,
        )
        result = module.execute("listen", [])
        self.assert_false(result.success)
        self.assert_true("not enabled" in result.message.lower())

    def _test_voice_module_status_reports_disabled_when_engine_none(self) -> None:
        module = VoiceModule(
            config=_config_with({}),
            command_router=CommandRouter(),
            engine=None,
            audio_capture=None,
        )
        result = module.execute("status", [])
        self.assert_true(result.success)
        self.assert_true("Enabled : No" in result.message)

    # ---------- Configuration defaults ----------

    def _test_bootstrap_config_defaults_wake_disabled(self) -> None:
        config = _config_with({"voice": {"enabled": True, "languages": ["en"]}})
        self.assert_false(
            bool(config.get("voice.wake.enabled", False)),
            "'voice.wake.enabled' must default to false when entirely absent from config",
        )

    # ---------- Bootstrap wiring: independent STT/TTS/Wake enablement (owner Decision D6) ----------

    def _test_bootstrap_skips_voice_when_all_three_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            _write_voice_wake_bootstrap_config(directory, voice_section="")
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.voice_engine is None)
                    self.assert_true(bootstrap.voice_tts_engine is None)
                    self.assert_true(bootstrap.voice_wake_engine is None)
                    self.assert_true(bootstrap.voice_wake_capture is None)
                    result = bootstrap._command_router.dispatch("voice status")
                    self.assert_false(result.success, "'voice' must not be a registered namespace")
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_starts_voice_when_only_wake_enabled(self) -> None:
        # STT and TTS both left disabled -- only 'voice.wake.enabled'
        # is true. No real openWakeWord model files exist in this
        # environment, so wake construction itself is expected to
        # fail gracefully (voice_wake_engine stays None) -- but per
        # owner Decision D6 the "voice" namespace must still be
        # registered purely because the flag is true, independent of
        # whether construction actually succeeded.
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            voice_section = "voice:\n  wake:\n    enabled: true\n"
            _write_voice_wake_bootstrap_config(directory, voice_section=voice_section)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.voice_engine is None, "STT must remain disabled")
                    self.assert_true(bootstrap.voice_tts_engine is None, "TTS must remain disabled")
                    result = bootstrap._command_router.dispatch("voice wake status")
                    self.assert_true(result.success, "'voice' namespace must be registered when only Wake Word is enabled")
                    listen_result = bootstrap._command_router.dispatch("voice listen")
                    self.assert_false(listen_result.success)
                    self.assert_true("not enabled" in listen_result.message.lower())
                    other = bootstrap._command_router.dispatch("system version")
                    self.assert_true(other.success, "Other modules must be unaffected")
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_starts_voice_when_only_tts_enabled(self) -> None:
        # This is the exact scenario EP-047's own as-built limitation
        # disclosed as unsupported ("TTS-only operation is not
        # supported") -- owner Decision D6 authorizes EP-048 to fix
        # it. STT and Wake Word both left disabled.
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            voice_section = "voice:\n  tts:\n    enabled: true\n"
            _write_voice_wake_bootstrap_config(directory, voice_section=voice_section)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.voice_engine is None, "STT must remain disabled")
                    self.assert_true(bootstrap.voice_wake_engine is None, "Wake Word must remain disabled")
                    result = bootstrap._command_router.dispatch("voice status")
                    self.assert_true(
                        result.success,
                        "'voice' namespace must be registered when only TTS is enabled (D6 fix)",
                    )
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_starts_voice_when_only_stt_enabled_regression(self) -> None:
        # EP-046's own original scenario -- must remain unchanged.
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            model_dir = directory / "data" / "models" / "voice"
            model_dir.mkdir(parents=True, exist_ok=True)
            voice_section = (
                "voice:\n"
                "  enabled: true\n"
                '  languages: ["en"]\n'
                '  default_language: "en"\n'
                f'  model_dir: "{model_dir.as_posix()}"\n'
            )
            _write_voice_wake_bootstrap_config(directory, voice_section=voice_section)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.voice_engine is not None)
                    self.assert_true(bootstrap.voice_tts_engine is None)
                    self.assert_true(bootstrap.voice_wake_engine is None)
                    result = bootstrap._command_router.dispatch("voice status")
                    self.assert_true(result.success)
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_disables_wake_on_missing_model_files_but_keeps_stt_tts(self) -> None:
        """An empty (model-file-less) 'voice.wake.model_dir' must disable only Wake Word.

        Mirrors tests/EP047/test_voice_tts.py's own
        `_test_bootstrap_disables_tts_on_construction_failure_but_keeps_stt`
        precedent, extended to all three subsystems: STT and TTS must
        both remain fully intact, and Bootstrap must never crash.
        """
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            stt_model_dir = directory / "data" / "models" / "voice"
            stt_model_dir.mkdir(parents=True, exist_ok=True)
            wake_model_dir = directory / "data" / "models" / "wake"
            wake_model_dir.mkdir(parents=True, exist_ok=True)  # exists, but deliberately empty
            voice_section = (
                "voice:\n"
                "  enabled: true\n"
                '  languages: ["en"]\n'
                '  default_language: "en"\n'
                f'  model_dir: "{stt_model_dir.as_posix()}"\n'
                "  tts:\n"
                "    enabled: true\n"
                "  wake:\n"
                "    enabled: true\n"
                f'    model_dir: "{wake_model_dir.as_posix()}"\n'
            )
            _write_voice_wake_bootstrap_config(directory, voice_section=voice_section)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(
                        bootstrap.voice_engine is not None, "STT must remain available even if Wake Word construction fails"
                    )
                    self.assert_true(
                        bootstrap.voice_wake_engine is None,
                        "Wake Word must not be available when model files are missing",
                    )
                    self.assert_true(bootstrap.voice_wake_capture is None)
                    result = bootstrap._command_router.dispatch("voice wake status")
                    self.assert_true(result.success, "'voice' namespace must still be registered")
                    self.assert_true("Enabled : No" in result.message)
                    other = bootstrap._command_router.dispatch("system version")
                    self.assert_true(other.success, "Other modules must be unaffected")
                finally:
                    bootstrap.shutdown()

    # ---------- Helpers ----------

    def _build_voice_module(
        self,
        wake_engine,
        wake_capture,
        languages: list[str] | None = None,
        command_router: CommandRouter | None = None,
        tts_engine=None,
    ) -> VoiceModule:
        stt_engine = _FakeSpeechToTextEngine(
            canned_result=TranscriptionResult(success=True, text="", confidence=None, language="en"),
            languages=languages or ["en"],
        )
        audio_capture = _FakeAudioCapture(
            canned_result=AudioCaptureResult(success=True, pcm_data=b"", sample_rate=16000)
        )
        return VoiceModule(
            config=_config_with({}),
            command_router=command_router or CommandRouter(),
            engine=stt_engine,
            audio_capture=audio_capture,
            tts_engine=tts_engine,
            wake_engine=wake_engine,
            wake_capture=wake_capture,
        )
