"""EP-046 microphone audio capture.

Captures raw PCM audio from an input device using `sounddevice`
(owner Decision 6). Kept entirely separate from speech recognition
(`speech_to_text.py`) -- this module knows nothing about Vosk,
transcription, or `CommandRouter`; it only turns "a microphone" into
"PCM bytes" (EP046_DESIGN.md Section 5.2/5.3).

`sounddevice` was selected over `pyaudio` because it ships prebuilt
wheels bundling PortAudio for Windows (no separate native build
toolchain required on the target workstation), matching the
project's existing preference for dependencies with clean prebuilt
Windows wheels (see EP046_DESIGN.md Section 3.7/9a Decision 6).

v1 uses fixed-duration capture (`voice.listen_duration_seconds`),
not silence-terminated (voice activity detection) capture -- the
simplest of the two options EP046_DESIGN.md Section 5.1 left open,
and sufficient for short, command-style utterances. Silence-based
capture is not excluded by the architecture and remains a candidate
for a future refinement.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.config import Config

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_LISTEN_DURATION_SECONDS = 5.0


class AudioCaptureError(Exception):
    """Raised when the audio capture layer cannot be constructed.

    Reserved for construction-time failures (the `sounddevice`
    package not importable). Per-capture failures (no device, device
    busy, permission denied) are never raised -- `capture()` always
    returns an `AudioCaptureResult` instead (EP046_DESIGN.md
    Section 5.4).
    """


@dataclass(frozen=True)
class AudioCaptureResult:
    """Outcome of a single microphone capture attempt.

    Attributes:
        success: Whether audio was captured.
        pcm_data: Raw, little-endian, 16-bit signed mono PCM samples.
            Empty when `success` is False.
        sample_rate: The sample rate `pcm_data` was captured at.
        error: A short, human-readable failure reason. None on
            success.
    """

    success: bool
    pcm_data: bytes
    sample_rate: int
    error: str | None = None


class AudioCapture:
    """Captures a fixed-duration recording from an input device.

    A thin wrapper around `sounddevice.rec()`. Holds no reference to
    any STT engine or to `CommandRouter` -- `VoiceModule` (`skill.py`)
    is the only component that connects this class's output to
    recognition and dispatch.
    """

    def __init__(self, config: Config) -> None:
        """Initialize audio capture from `voice.*` configuration.

        Args:
            config: The application Config.

        Raises:
            AudioCaptureError: If the `sounddevice` package is not
                importable.
        """
        try:
            import sounddevice
        except (ImportError, OSError) as exc:
            raise AudioCaptureError(
                "The 'sounddevice' package is not usable (missing package or "
                "missing PortAudio runtime library). Add/install it before "
                "enabling 'voice.enabled' -- see requirements.txt."
            ) from exc

        self._sounddevice = sounddevice
        self._sample_rate = int(config.get("voice.sample_rate", DEFAULT_SAMPLE_RATE))
        self._duration_seconds = float(
            config.get("voice.listen_duration_seconds", DEFAULT_LISTEN_DURATION_SECONDS)
        )

        device = config.get("voice.device", None)
        self._device: int | str | None = device if device not in (None, "") else None

    @property
    def sample_rate(self) -> int:
        """Return the configured capture sample rate ('voice.sample_rate')."""
        return self._sample_rate

    def capture(self) -> AudioCaptureResult:
        """Record `voice.listen_duration_seconds` of audio from the input device.

        Returns:
            An AudioCaptureResult. Never raises -- microphone-unavailable,
            permission, timeout, and interrupted-capture conditions are
            all reported via `success=False` (EP046_DESIGN.md Section 5.4).
        """
        frame_count = max(1, int(self._duration_seconds * self._sample_rate))

        try:
            recording = self._sounddevice.rec(
                frame_count,
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                device=self._device,
            )
            self._sounddevice.wait()
        except self._sounddevice.PortAudioError as exc:
            logger.error(f"Voice: microphone unavailable: {exc}")
            return AudioCaptureResult(
                success=False,
                pcm_data=b"",
                sample_rate=self._sample_rate,
                error=f"microphone unavailable: {exc}",
            )
        except KeyboardInterrupt:
            return AudioCaptureResult(
                success=False,
                pcm_data=b"",
                sample_rate=self._sample_rate,
                error="capture interrupted",
            )
        except Exception as exc:  # noqa: BLE001 - device/driver errors must never propagate (Section 5.4)
            logger.error(f"Voice: audio capture error: {exc}")
            return AudioCaptureResult(
                success=False,
                pcm_data=b"",
                sample_rate=self._sample_rate,
                error=f"audio capture error: {exc}",
            )

        pcm_data = recording.tobytes()
        if not pcm_data:
            return AudioCaptureResult(
                success=False,
                pcm_data=b"",
                sample_rate=self._sample_rate,
                error="no audio captured",
            )

        return AudioCaptureResult(
            success=True, pcm_data=pcm_data, sample_rate=self._sample_rate, error=None
        )
