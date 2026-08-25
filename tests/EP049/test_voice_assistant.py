"""Real engineering tests for EP-049 STEP 2 - Voice Assistant.

Single combined test suite (NAME = "EP049"), following the same
precedent EP-043/EP-045/EP-046/EP-047/EP-048 already established:
this sidesteps the pre-existing `TestRegistry` NAME-collision
technical debt (docs/BACKLOG.md) entirely rather than triggering it.

Deterministic: no physical microphone, no real wake-word model, no
real STT model, and no network access are required or exercised.
`WakeWordEngine`/`StreamingAudioCapture`/`SpeechToTextEngine`/
`AudioCapture`/`TextToSpeechEngine` are exercised through the
existing fakes already established by
`tests/EP046/test_voice.py`/`tests/EP047/test_voice_tts.py`/
`tests/EP048/test_wake_word.py` (imported directly below, never
duplicated) for every `VoiceModule._wake_assist()` scenario.

EP-049 is strictly one-shot (EP049_DESIGN.md Owner Decision D2,
Section 23a): one wake detection leads to exactly one call to the
existing, unmodified `_listen()` (Owner Decision D3), then returns.
There is no loop, no background thread, and no automatic re-arming of
wake listening. This suite asserts that directly (items 24-26 below)
by counting `start()`/`stop()` calls on the fake wake capture.

One scenario (an actual wake phrase detected from real audio, through
a real, loaded openWakeWord model, followed by a real transcribed
command) is not exercised here for the same reason
`tests/EP048/test_wake_word.py` already discloses: no real
openWakeWord/Vosk model files exist in this environment. That case is
reported via `self.skip()`, matching EP-046/047/048's own precedent
-- not silently omitted.

Covers (EP-049 STEP 2 instructions, items 1-32):
    1.  Assist disabled (`voice.wake.assist.enabled` false/absent).
    2.  Wake engine unavailable.
    3.  Wake capture unavailable.
    4.  STT engine unavailable.
    5.  Wake capture start failure.
    6.  Wake word not detected.
    7.  Successful wake detection.
    8.  `wake_capture.stop()` occurs before `audio_capture.capture()`.
    9.  Full successful wake -> listen -> dispatch flow.
    10. Exact transcribed text reaches CommandRouter through the
        existing `_listen()`.
    11. Dispatch occurs exactly once.
    12. Empty transcription.
    13. Low-confidence transcription.
    14. STT timeout/failure.
    15. Audio capture failure.
    16. CommandRouter failure (unknown module).
    17. Command execution failure.
    18. TTS disabled (`speak_result` false).
    19. TTS enabled and engine available.
    20. TTS receives the dispatched result message exactly once.
    21. TTS unavailable while `speak_result=true`.
    22. TTS failure does not crash the action.
    23. Wake stream cleanup on failure (`stop()` always called).
    24. No automatic wake restart after successful command.
    25. No automatic wake restart after failed command.
    26. One-shot behavior (`start()` called exactly once).
    27. Existing EP-046 behavior remains intact.
    28. Existing EP-047 behavior remains intact.
    29. Existing EP-048 behavior remains intact.
    30. `voice help` includes `wake assist`.
    31. Existing unknown `wake` sub-action behavior remains unchanged.
    32. Bootstrap configuration combinations degrade safely.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from src.bootstrap import Bootstrap
from src.core.command_router import CommandResult, CommandRouter
from src.skills.voice.audio_capture import AudioCaptureResult
from src.skills.voice.skill import VoiceModule
from src.skills.voice.speech_to_text import TranscriptionResult
from src.skills.voice.streaming_audio_capture import StreamingCaptureStartResult
from src.skills.voice.text_to_speech import SynthesisResult
from src.skills.voice.wake_word import WakeWordDetectionResult
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry
from tests.EP045.test_web_dashboard import _ChdirGuard
from tests.EP046.test_voice import (
    _FakeAudioCapture,
    _FakeSpeechToTextEngine,
    _RecordingModule,
    _config_with,
)
from tests.EP047.test_voice_tts import _FakeTextToSpeechEngine
from tests.EP048.test_wake_word import (
    _FakeWakeWordEngine,
    _write_voice_wake_bootstrap_config,
)


@dataclass
class _OrderTrackingStreamingAudioCapture:
    """Fake StreamingAudioCapture that appends to a *shared* call_log.

    Sharing one list (passed in explicitly, never a per-instance
    default) between this fake and `_OrderTrackingAudioCapture` below
    is what lets tests assert the exact relative order of
    `wake_capture.stop()` vs. `audio_capture.capture()` (item 8) --
    call counts alone cannot prove ordering.
    """

    frames_to_yield: list[bytes]
    call_log: list[str]
    start_result: StreamingCaptureStartResult = field(
        default_factory=lambda: StreamingCaptureStartResult(success=True)
    )

    def __post_init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    def start(self) -> StreamingCaptureStartResult:
        self.start_calls += 1
        self.call_log.append("wake_start")
        return self.start_result

    def frames(self, timeout_seconds: float = 1.0) -> Iterator[bytes]:
        for frame in self.frames_to_yield:
            yield frame

    def stop(self) -> None:
        self.stop_calls += 1
        self.call_log.append("wake_stop")


@dataclass
class _OrderTrackingAudioCapture:
    """Fake AudioCapture that also appends to a *shared* call_log (see above)."""

    canned_result: AudioCaptureResult
    call_log: list[str]

    def __post_init__(self) -> None:
        self.call_count = 0

    def capture(self) -> AudioCaptureResult:
        self.call_count += 1
        self.call_log.append("audio_capture")
        return self.canned_result


class _Missing:
    """Sentinel distinguishing 'use the default fake' from 'pass None explicitly'."""


class _NoneSentinel:
    """Sentinel meaning 'construct VoiceModule with this collaborator as None'."""


_MISSING = _Missing()
_NONE = _NoneSentinel()


@TestRegistry.register
class VoiceAssistantTest(BaseTest):
    NAME = "EP049"

    def run(self):
        self._test_assist_disabled_by_default()
        self._test_assist_disabled_explicit_false()
        self._test_wake_engine_unavailable()
        self._test_wake_capture_unavailable()
        self._test_stt_engine_unavailable()
        self._test_audio_capture_unavailable()
        self._test_wake_capture_start_failure()
        self._test_wake_word_not_detected()
        self._test_wake_stream_stopped_before_audio_capture()
        self._test_full_successful_wake_listen_dispatch_flow()
        self._test_exact_transcribed_text_reaches_command_router()
        self._test_dispatch_occurs_exactly_once()
        self._test_empty_transcription()
        self._test_low_confidence_transcription()
        self._test_stt_timeout_failure()
        self._test_audio_capture_failure()
        self._test_command_router_failure_unknown_module()
        self._test_command_execution_failure()
        self._test_tts_disabled_by_default()
        self._test_tts_enabled_and_available()
        self._test_tts_receives_result_message_exactly_once()
        self._test_tts_unavailable_while_speak_result_true()
        self._test_tts_failure_does_not_crash_action()
        self._test_wake_stream_cleanup_on_every_failure_path()
        self._test_no_automatic_wake_restart_after_success()
        self._test_no_automatic_wake_restart_after_failure()
        self._test_one_shot_start_called_exactly_once()
        self._test_ep046_regression_listen_transcribe_status_unaffected()
        self._test_ep047_regression_speak_unaffected()
        self._test_ep048_regression_wake_listen_status_unaffected()
        self._test_voice_help_includes_wake_assist()
        self._test_unknown_wake_sub_action_unchanged()
        self._test_bootstrap_assist_disabled_by_default_no_crash()
        self._test_bootstrap_assist_enabled_but_wake_disabled_degrades_safely()
        self._test_bootstrap_assist_enabled_but_stt_disabled_degrades_safely()
        self._test_real_hardware_wake_to_dispatch_not_available_here()

        return self.result

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def _make_module(
        self,
        *,
        assist_enabled: bool = True,
        speak_result: bool = False,
        wake_engine=_MISSING,
        wake_capture=_MISSING,
        engine=_MISSING,
        audio_capture=_MISSING,
        tts_engine=None,
        command_router: CommandRouter | None = None,
        call_log: list[str] | None = None,
        wake_frames: list[bytes] | None = None,
        wake_detection_results: list[WakeWordDetectionResult] | None = None,
        wake_start_result: StreamingCaptureStartResult | None = None,
        stt_result: TranscriptionResult | None = None,
        audio_result: AudioCaptureResult | None = None,
    ) -> tuple[VoiceModule, dict]:
        """Build a `VoiceModule` wired with fakes, plus a handle to them.

        Every collaborator has an EP-049-appropriate default so each
        test only needs to override what it cares about. Defaults
        represent a "successful wake -> one detected frame -> silence
        capture -> successful transcription" configuration.
        """
        if call_log is None:
            call_log = []

        if wake_frames is None:
            wake_frames = [b"\x00\x01"]
        if wake_detection_results is None:
            wake_detection_results = [
                WakeWordDetectionResult(detected=True, score=0.9, wake_word="hey_jarvis")
            ]
        if wake_start_result is None:
            wake_start_result = StreamingCaptureStartResult(success=True)

        if wake_engine is _MISSING:
            wake_engine = _FakeWakeWordEngine(canned_results=wake_detection_results)
        if wake_capture is _MISSING:
            wake_capture = _OrderTrackingStreamingAudioCapture(
                frames_to_yield=wake_frames,
                call_log=call_log,
                start_result=wake_start_result,
            )

        if stt_result is None:
            stt_result = TranscriptionResult(
                success=True, text="system version", confidence=0.9, language="en"
            )
        if audio_result is None:
            audio_result = AudioCaptureResult(success=True, pcm_data=b"\x00\x00", sample_rate=16000)

        if engine is _MISSING:
            engine = _FakeSpeechToTextEngine(canned_result=stt_result, languages=["en"])
        if audio_capture is _MISSING:
            audio_capture = _OrderTrackingAudioCapture(canned_result=audio_result, call_log=call_log)

        if command_router is None:
            command_router = CommandRouter()
            command_router.register(_RecordingModule())
            command_router.register(_SystemVersionModule())

        config = _config_with(
            {
                "voice": {
                    "wake": {
                        "assist": {
                            "enabled": assist_enabled,
                            "speak_result": speak_result,
                        }
                    }
                }
            }
        )

        module = VoiceModule(
            config=config,
            command_router=command_router,
            engine=None if engine is _NONE else engine,
            audio_capture=None if audio_capture is _NONE else audio_capture,
            tts_engine=tts_engine,
            wake_engine=None if wake_engine is _NONE else wake_engine,
            wake_capture=None if wake_capture is _NONE else wake_capture,
        )
        handles = {
            "wake_engine": wake_engine,
            "wake_capture": wake_capture,
            "engine": engine,
            "audio_capture": audio_capture,
            "call_log": call_log,
            "command_router": command_router,
        }
        return module, handles

    # ------------------------------------------------------------------
    # 1-5: Disabled / unavailable guards
    # ------------------------------------------------------------------

    def _test_assist_disabled_by_default(self) -> None:
        config = _config_with({})  # no voice.wake.assist section at all
        module = VoiceModule(
            config=config,
            command_router=CommandRouter(),
            engine=_FakeSpeechToTextEngine(
                canned_result=TranscriptionResult(True, "x", 0.9, "en"), languages=["en"]
            ),
            audio_capture=_FakeAudioCapture(
                canned_result=AudioCaptureResult(True, b"\x00", 16000)
            ),
            wake_engine=_FakeWakeWordEngine(canned_results=[]),
            wake_capture=_OrderTrackingStreamingAudioCapture(frames_to_yield=[], call_log=[]),
        )
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("not enabled" in result.message.lower())

    def _test_assist_disabled_explicit_false(self) -> None:
        module, handles = self._make_module(assist_enabled=False)
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("not enabled" in result.message.lower())
        # Must never touch any collaborator when disabled up front.
        self.assert_equal(handles["wake_capture"].start_calls, 0)

    def _test_wake_engine_unavailable(self) -> None:
        module, handles = self._make_module(wake_engine=_NONE)
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("wake word detection is not enabled" in result.message.lower())

    def _test_wake_capture_unavailable(self) -> None:
        module, handles = self._make_module(wake_capture=_NONE)
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("wake word detection is not enabled" in result.message.lower())

    def _test_stt_engine_unavailable(self) -> None:
        module, handles = self._make_module(engine=_NONE)
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("speech-to-text is not enabled" in result.message.lower())
        # Guard must fire before ever starting the wake stream.
        self.assert_equal(handles["wake_capture"].start_calls, 0)

    def _test_audio_capture_unavailable(self) -> None:
        module, handles = self._make_module(audio_capture=_NONE)
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("speech-to-text is not enabled" in result.message.lower())
        self.assert_equal(handles["wake_capture"].start_calls, 0)

    # ------------------------------------------------------------------
    # 5-9: Wake listening phase
    # ------------------------------------------------------------------

    def _test_wake_capture_start_failure(self) -> None:
        module, handles = self._make_module(
            wake_start_result=StreamingCaptureStartResult(success=False, error="no input device")
        )
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("microphone error" in result.message.lower())
        self.assert_true("no input device" in result.message)
        # Never reaches STT/dispatch.
        self.assert_equal(handles["audio_capture"].call_count, 0)

    def _test_wake_word_not_detected(self) -> None:
        module, handles = self._make_module(
            wake_frames=[b"\x00", b"\x01"],
            wake_detection_results=[
                WakeWordDetectionResult(detected=False, score=0.1, wake_word="hey_jarvis"),
                WakeWordDetectionResult(detected=False, score=0.2, wake_word="hey_jarvis"),
            ],
        )
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("ended without a detection" in result.message.lower())
        self.assert_equal(handles["wake_capture"].start_calls, 1)
        self.assert_equal(handles["wake_capture"].stop_calls, 1)
        self.assert_equal(handles["audio_capture"].call_count, 0)

    def _test_wake_stream_stopped_before_audio_capture(self) -> None:
        module, handles = self._make_module()
        result = module.execute("wake", ["assist"])
        self.assert_true(result.success)
        call_log = handles["call_log"]
        self.assert_true("wake_stop" in call_log and "audio_capture" in call_log)
        self.assert_true(call_log.index("wake_stop") < call_log.index("audio_capture"))

    # ------------------------------------------------------------------
    # 9-11: Full happy path / dispatch integration
    # ------------------------------------------------------------------

    def _test_full_successful_wake_listen_dispatch_flow(self) -> None:
        module, handles = self._make_module(
            stt_result=TranscriptionResult(success=True, text="echo say hello there", confidence=0.9, language="en")
        )
        result = module.execute("wake", ["assist"])
        self.assert_true(result.success)
        self.assert_true("hello there" in result.message)
        recording_module = handles["command_router"]._modules["echo"]
        self.assert_equal(recording_module.call_count, 1)

    def _test_exact_transcribed_text_reaches_command_router(self) -> None:
        module, handles = self._make_module(
            stt_result=TranscriptionResult(success=True, text="echo say exact phrase check", confidence=0.9, language="en")
        )
        result = module.execute("wake", ["assist"])
        self.assert_true(result.success)
        # The dispatched module echoes back exactly what CommandRouter
        # parsed out of the transcribed text ("exact phrase check"),
        # proving _wake_assist() forwarded the transcript unmodified
        # through the existing _listen() -> dispatch() path.
        self.assert_true(result.message.endswith("exact phrase check"))

    def _test_dispatch_occurs_exactly_once(self) -> None:
        module, handles = self._make_module(
            stt_result=TranscriptionResult(success=True, text="echo say once", confidence=0.9, language="en")
        )
        module.execute("wake", ["assist"])
        recording_module = handles["command_router"]._modules["echo"]
        self.assert_equal(recording_module.call_count, 1)

    # ------------------------------------------------------------------
    # 12-17: STT / dispatch failure paths (delegated to existing _listen())
    # ------------------------------------------------------------------

    def _test_empty_transcription(self) -> None:
        module, handles = self._make_module(
            stt_result=TranscriptionResult(success=False, text="", confidence=None, language="en", error="no speech detected")
        )
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("no speech detected" in result.message.lower())
        recording_module = handles["command_router"]._modules["echo"]
        self.assert_equal(recording_module.call_count, 0)

    def _test_low_confidence_transcription(self) -> None:
        module, handles = self._make_module(
            stt_result=TranscriptionResult(success=True, text="echo say quiet", confidence=0.1, language="en")
        )
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("below the configured" in result.message.lower())
        recording_module = handles["command_router"]._modules["echo"]
        self.assert_equal(recording_module.call_count, 0)

    def _test_stt_timeout_failure(self) -> None:
        module, handles = self._make_module(
            stt_result=TranscriptionResult(success=False, text="", confidence=None, language="en", error="recognition timed out after 8s")
        )
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("timed out" in result.message.lower())

    def _test_audio_capture_failure(self) -> None:
        module, handles = self._make_module(
            audio_result=AudioCaptureResult(success=False, pcm_data=b"", sample_rate=16000, error="microphone unavailable")
        )
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("microphone error" in result.message.lower())

    def _test_command_router_failure_unknown_module(self) -> None:
        module, handles = self._make_module(
            stt_result=TranscriptionResult(success=True, text="nonexistent_module do_thing", confidence=0.9, language="en")
        )
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("unknown" in result.message.lower())

    def _test_command_execution_failure(self) -> None:
        command_router = CommandRouter()
        command_router.register(_FailingModule())
        module, handles = self._make_module(
            command_router=command_router,
            stt_result=TranscriptionResult(success=True, text="boom fail", confidence=0.9, language="en"),
        )
        result = module.execute("wake", ["assist"])
        self.assert_false(result.success)
        self.assert_true("internal error" in result.message.lower())

    # ------------------------------------------------------------------
    # 18-22: TTS-on-result (Owner Decision D6)
    # ------------------------------------------------------------------

    def _test_tts_disabled_by_default(self) -> None:
        tts = _FakeTextToSpeechEngine(canned_result=SynthesisResult(True, "en"), languages=["en"])
        module, handles = self._make_module(tts_engine=tts, speak_result=False)
        module.execute("wake", ["assist"])
        self.assert_equal(len(tts.calls), 0)

    def _test_tts_enabled_and_available(self) -> None:
        tts = _FakeTextToSpeechEngine(canned_result=SynthesisResult(True, "en"), languages=["en"])
        module, handles = self._make_module(
            tts_engine=tts,
            speak_result=True,
            stt_result=TranscriptionResult(success=True, text="echo say spoken result", confidence=0.9, language="en"),
        )
        result = module.execute("wake", ["assist"])
        self.assert_true(result.success)
        self.assert_equal(len(tts.calls), 1)

    def _test_tts_receives_result_message_exactly_once(self) -> None:
        tts = _FakeTextToSpeechEngine(canned_result=SynthesisResult(True, "en"), languages=["en"])
        module, handles = self._make_module(
            tts_engine=tts,
            speak_result=True,
            stt_result=TranscriptionResult(success=True, text="echo say spoken twice check", confidence=0.9, language="en"),
        )
        result = module.execute("wake", ["assist"])
        self.assert_equal(len(tts.calls), 1)
        spoken_text, _language = tts.calls[0]
        self.assert_equal(spoken_text, result.message)

    def _test_tts_unavailable_while_speak_result_true(self) -> None:
        module, handles = self._make_module(tts_engine=None, speak_result=True)
        result = module.execute("wake", ["assist"])
        # Command still executes/reports normally; TTS is simply skipped.
        self.assert_true(result.success)

    def _test_tts_failure_does_not_crash_action(self) -> None:
        tts = _FakeTextToSpeechEngine(
            canned_result=SynthesisResult(False, "en", error="no voice installed"), languages=["en"]
        )
        module, handles = self._make_module(
            tts_engine=tts,
            speak_result=True,
            stt_result=TranscriptionResult(success=True, text="echo say resilient", confidence=0.9, language="en"),
        )
        result = module.execute("wake", ["assist"])
        # The command's own outcome is unaffected by TTS failure.
        self.assert_true(result.success)
        self.assert_equal(len(tts.calls), 1)

    # ------------------------------------------------------------------
    # 23-26: Cleanup / one-shot invariants
    # ------------------------------------------------------------------

    def _test_wake_stream_cleanup_on_every_failure_path(self) -> None:
        for stt_result in (
            TranscriptionResult(success=False, text="", confidence=None, language="en", error="no speech detected"),
            TranscriptionResult(success=True, text="echo say low", confidence=0.05, language="en"),
        ):
            module, handles = self._make_module(stt_result=stt_result)
            module.execute("wake", ["assist"])
            self.assert_equal(handles["wake_capture"].stop_calls, 1)

        # And when the wake stream never detects anything at all.
        module, handles = self._make_module(
            wake_frames=[b"\x00"],
            wake_detection_results=[WakeWordDetectionResult(detected=False, score=0.0, wake_word="hey_jarvis")],
        )
        module.execute("wake", ["assist"])
        self.assert_equal(handles["wake_capture"].stop_calls, 1)

    def _test_no_automatic_wake_restart_after_success(self) -> None:
        module, handles = self._make_module(
            stt_result=TranscriptionResult(success=True, text="system version", confidence=0.9, language="en")
        )
        result = module.execute("wake", ["assist"])
        self.assert_true(result.success)
        self.assert_equal(handles["wake_capture"].start_calls, 1)

    def _test_no_automatic_wake_restart_after_failure(self) -> None:
        module, handles = self._make_module(
            stt_result=TranscriptionResult(success=False, text="", confidence=None, language="en", error="no speech detected")
        )
        module.execute("wake", ["assist"])
        self.assert_equal(handles["wake_capture"].start_calls, 1)

    def _test_one_shot_start_called_exactly_once(self) -> None:
        module, handles = self._make_module()
        module.execute("wake", ["assist"])
        self.assert_equal(handles["wake_capture"].start_calls, 1)
        self.assert_equal(handles["wake_capture"].stop_calls, 1)

    # ------------------------------------------------------------------
    # 27-29, 31: Regression compatibility
    # ------------------------------------------------------------------

    def _test_ep046_regression_listen_transcribe_status_unaffected(self) -> None:
        module, handles = self._make_module(
            stt_result=TranscriptionResult(success=True, text="system version", confidence=0.9, language="en")
        )
        listen_result = module.execute("listen", [])
        self.assert_true(listen_result.success)
        transcribe_result = module.execute("transcribe", [])
        self.assert_true(transcribe_result.success)
        status_result = module.execute("status", [])
        self.assert_true(status_result.success)

    def _test_ep047_regression_speak_unaffected(self) -> None:
        tts = _FakeTextToSpeechEngine(canned_result=SynthesisResult(True, "en"), languages=["en"])
        module, handles = self._make_module(tts_engine=tts)
        result = module.execute("speak", ["hello", "world"])
        self.assert_true(result.success)
        self.assert_equal(len(tts.calls), 1)
        self.assert_equal(tts.calls[0][0], "hello world")

    def _test_ep048_regression_wake_listen_status_unaffected(self) -> None:
        module, handles = self._make_module()
        listen_result = module.execute("wake", ["listen"])
        self.assert_true(listen_result.success)
        # 'wake listen' must never dispatch (EP-048 Owner Decision D5).
        recording_module = handles["command_router"]._modules["echo"]
        self.assert_equal(recording_module.call_count, 0)
        status_result = module.execute("wake", ["status"])
        self.assert_true(status_result.success)

    def _test_unknown_wake_sub_action_unchanged(self) -> None:
        module, handles = self._make_module()
        result = module.execute("wake", ["bogus"])
        self.assert_false(result.success)
        self.assert_true("usage" in result.message.lower())
        self.assert_true("voice wake assist" in result.message.lower())

    def _test_voice_help_includes_wake_assist(self) -> None:
        module, handles = self._make_module()
        result = module.execute("help", [])
        self.assert_true(result.success)
        self.assert_true("voice wake assist" in result.message.lower())

    # ------------------------------------------------------------------
    # 32: Bootstrap wiring
    # ------------------------------------------------------------------

    def _test_bootstrap_assist_disabled_by_default_no_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            voice_section = "voice:\n  wake:\n    enabled: true\n"
            _write_voice_wake_bootstrap_config(directory, voice_section=voice_section)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    result = bootstrap._command_router.dispatch("voice wake assist")
                    self.assert_false(result.success)
                    self.assert_true("not enabled" in result.message.lower())
                    other = bootstrap._command_router.dispatch("system version")
                    self.assert_true(other.success, "Other modules must be unaffected")
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_assist_enabled_but_wake_disabled_degrades_safely(self) -> None:
        # voice.enabled=true (with a valid, empty model_dir -- mirrors
        # tests/EP046/test_voice.py's own
        # `_test_vosk_engine_constructs_with_existing_empty_model_dir`
        # precedent) keeps the 'voice' namespace registered (Bootstrap's
        # existing, unmodified D6 gate) even though voice.wake.enabled
        # is false, so this test can isolate exactly the
        # wake_engine-unavailable guard inside `_wake_assist()` itself.
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
                "  wake:\n"
                "    enabled: false\n"
                "    assist:\n"
                "      enabled: true\n"
            )
            _write_voice_wake_bootstrap_config(directory, voice_section=voice_section)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.voice_engine is not None)
                    self.assert_true(bootstrap.voice_wake_engine is None)
                    result = bootstrap._command_router.dispatch("voice wake assist")
                    self.assert_false(result.success)
                    self.assert_true("wake word detection is not enabled" in result.message.lower())
                finally:
                    bootstrap.shutdown()

    def _test_bootstrap_assist_enabled_but_stt_disabled_degrades_safely(self) -> None:
        # voice.wake.enabled=true here also attempts *real*
        # OpenWakeWordEngine construction, which -- exactly as
        # tests/EP048/test_wake_word.py's own
        # `_test_bootstrap_starts_voice_when_only_wake_enabled` already
        # discloses -- fails gracefully in this environment because no
        # real openWakeWord model files are installed under
        # 'voice.wake.model_dir'. `bootstrap.voice_wake_engine` is
        # therefore expected to be None here too, so `_wake_assist()`'s
        # wake-engine guard (not its STT guard) is the one that fires
        # first -- both are existing, graceful, non-crashing "not
        # enabled/available" outcomes (never a hang or a crash), which
        # is what this test actually verifies.
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            voice_section = (
                "voice:\n"
                "  enabled: false\n"
                "  wake:\n"
                "    enabled: true\n"
                "    assist:\n"
                "      enabled: true\n"
            )
            _write_voice_wake_bootstrap_config(directory, voice_section=voice_section)
            with _ChdirGuard(directory):
                bootstrap = Bootstrap(project_root=directory)
                try:
                    bootstrap.initialize()
                    self.assert_true(bootstrap.voice_engine is None)
                    result = bootstrap._command_router.dispatch("voice wake assist")
                    self.assert_false(result.success)
                    self.assert_true(
                        "not enabled" in result.message.lower()
                        or "not available" in result.message.lower()
                    )
                finally:
                    bootstrap.shutdown()

    def _test_real_hardware_wake_to_dispatch_not_available_here(self) -> None:
        # No real openWakeWord model, no real Vosk model, and no
        # physical microphone exist in this environment (matches
        # tests/EP048/test_wake_word.py's own disclosed limitation).
        # Real end-to-end 'hey jarvis' -> real spoken command -> real
        # dispatch verification is a separate, manual STEP 2/3
        # activity (EP049_DESIGN.md Section 20), not part of this
        # automated suite.
        self.skip()


class _SystemVersionModule:
    """Minimal stand-in for the real 'system' module's 'version' action.

    Used only so `_make_module`'s default STT result ("system
    version") has somewhere valid to dispatch to without importing the
    real, unrelated 'system' CommandModule.
    """

    name = "system"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        if action != "version":
            return CommandResult(success=False, message=f"Unknown command: system {action}")
        return CommandResult(success=True, message="Jarvis 0.1.0-alpha")


class _FailingModule:
    """Minimal CommandModule stub whose action always raises.

    Used to prove `_wake_assist()` relies on `CommandRouter.dispatch()`'s
    own existing exception-catching (item 17: command execution
    failure) rather than adding a new try/except of its own.
    """

    name = "boom"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        raise RuntimeError("simulated command execution failure")
