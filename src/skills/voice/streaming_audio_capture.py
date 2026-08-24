"""EP-048 continuous/streaming microphone audio capture.

Captures raw PCM audio from an input device as a continuous stream
of fixed-size frames, using `sounddevice` (owner Decision D1's own
precedent of reusing the project's existing prebuilt-Windows-wheel
dependency, and EP-046's own choice of `sounddevice` over `pyaudio`
for the same reason -- EP046_DESIGN.md Section 3.7/9a Decision 6).

This is a **new, separate** component from `audio_capture.py`'s
existing `AudioCapture`, per owner Decision D4
(EP048_DESIGN.md Section 9a): `AudioCapture.capture()` is a single,
blocking, fixed-duration recording with a call-and-return lifecycle;
wake-word detection needs an indefinite, start/stop streaming
lifecycle instead. Rather than growing `AudioCapture` with a second,
materially different lifecycle, this module implements that
lifecycle on its own, leaving `audio_capture.py` completely
untouched -- confirmed byte-identical to its pre-EP-048 state.

Like `AudioCapture`, this module knows nothing about wake-word
detection, `WakeWordEngine`, or `CommandRouter` -- it only turns "a
microphone" into a stream of PCM frames (EP048_DESIGN.md
Section 5.3). No audio is ever written to disk: frames are handed to
the caller in memory and are not retained by this class once
yielded.
"""

from __future__ import annotations

import queue
from dataclasses import dataclass
from typing import Iterator

from loguru import logger

from src.core.config import Config

DEFAULT_SAMPLE_RATE = 16000
DEFAULT_FRAME_LENGTH = 1280  # ~80ms at 16kHz, matches OpenWakeWordEngine's default


class StreamingAudioCaptureError(Exception):
    """Raised when streaming audio capture cannot be constructed.

    Reserved for construction-time failures (the `sounddevice`
    package not importable). Per-frame/per-stream failures (no
    device, device busy, permission denied, stream interrupted) are
    never raised from `frames()` -- iteration simply ends, and
    `start()`/`stop()` report failure through their own return value
    instead (mirroring `AudioCaptureResult`'s established idiom).
    """


@dataclass(frozen=True)
class StreamingCaptureStartResult:
    """Outcome of attempting to start a streaming capture session.

    Attributes:
        success: Whether the input stream was opened successfully.
        error: A short, human-readable failure reason. None on
            success.
    """

    success: bool
    error: str | None = None


class StreamingAudioCapture:
    """Captures a continuous stream of fixed-size frames from an input device.

    A thin wrapper around `sounddevice.InputStream`. Holds no
    reference to any wake-word engine or to `CommandRouter` --
    `VoiceModule` (`skill.py`) is the only component that connects
    this class's output to detection and reporting.

    Usage:
        capture = StreamingAudioCapture(config)
        result = capture.start()
        if result.success:
            for frame in capture.frames():
                ...  # hand `frame` to a WakeWordEngine
                if should_stop:
                    capture.stop()
                    break

    Never writes audio to disk, never buffers more than a small,
    bounded number of frames in memory, and never requires a
    physical microphone to construct -- only to `start()`.
    """

    def __init__(self, config: Config) -> None:
        """Initialize streaming audio capture from `voice.wake.*` configuration.

        Args:
            config: The application Config.

        Raises:
            StreamingAudioCaptureError: If the `sounddevice` package
                is not importable.
        """
        try:
            import sounddevice
        except (ImportError, OSError) as exc:
            raise StreamingAudioCaptureError(
                "The 'sounddevice' package is not usable (missing package or "
                "missing PortAudio runtime library). Add/install it before "
                "enabling 'voice.wake.enabled' -- see requirements.txt."
            ) from exc

        self._sounddevice = sounddevice
        self._sample_rate = int(config.get("voice.wake.sample_rate", DEFAULT_SAMPLE_RATE))
        self._frame_length = int(config.get("voice.wake.frame_length", DEFAULT_FRAME_LENGTH))

        device = config.get("voice.device", None)
        self._device: int | str | None = device if device not in (None, "") else None

        self._stream = None
        self._frame_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=64)
        self._running = False

    @property
    def sample_rate(self) -> int:
        """Return the configured capture sample rate ('voice.wake.sample_rate')."""
        return self._sample_rate

    @property
    def frame_length(self) -> int:
        """Return the configured frame size in samples ('voice.wake.frame_length')."""
        return self._frame_length

    @property
    def is_running(self) -> bool:
        """Return whether a capture session is currently active."""
        return self._running

    def start(self) -> StreamingCaptureStartResult:
        """Open the input stream and begin buffering frames.

        Returns:
            A StreamingCaptureStartResult. Never raises --
            microphone-unavailable, permission, and device-busy
            conditions are all reported via `success=False`
            (EP048_DESIGN.md Section 5.5).
        """
        if self._running:
            return StreamingCaptureStartResult(success=False, error="capture already running")

        def _on_audio(indata, frames, time_info, status) -> None:  # noqa: ANN001 - sounddevice callback signature
            if status:
                logger.warning(f"Wake Word: audio stream status: {status}")
            try:
                self._frame_queue.put_nowait(bytes(indata))
            except queue.Full:
                # Drop the oldest-pending frame rather than block the
                # audio callback thread -- a dropped frame degrades
                # detection latency for one frame, never crashes
                # capture (EP048_DESIGN.md Section 5.5).
                try:
                    self._frame_queue.get_nowait()
                    self._frame_queue.put_nowait(bytes(indata))
                except queue.Empty:
                    pass

        try:
            stream = self._sounddevice.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self._frame_length,
                device=self._device,
                callback=_on_audio,
            )
            stream.start()
        except self._sounddevice.PortAudioError as exc:
            logger.error(f"Wake Word: microphone unavailable: {exc}")
            return StreamingCaptureStartResult(success=False, error=f"microphone unavailable: {exc}")
        except Exception as exc:  # noqa: BLE001 - device/driver errors must never propagate (Section 5.5)
            logger.error(f"Wake Word: audio stream error: {exc}")
            return StreamingCaptureStartResult(success=False, error=f"audio stream error: {exc}")

        self._stream = stream
        self._running = True
        return StreamingCaptureStartResult(success=True, error=None)

    def frames(self, timeout_seconds: float = 1.0) -> Iterator[bytes]:
        """Yield captured PCM frames until `stop()` is called.

        Args:
            timeout_seconds: How long to wait for the next frame
                before yielding control back to the caller (allowing
                the caller to check its own stop condition even when
                no audio has arrived). This method never yields a
                frame shorter than `frame_length` samples.

        Yields:
            Raw, little-endian, 16-bit signed mono PCM frames, each
            exactly `frame_length` samples (2 * frame_length bytes).

        Never raises: a queue-read timeout simply continues the
        loop; the loop itself ends cleanly once `stop()` has been
        called and no further frames remain buffered.
        """
        while self._running or not self._frame_queue.empty():
            try:
                yield self._frame_queue.get(timeout=timeout_seconds)
            except queue.Empty:
                continue

    def stop(self) -> None:
        """Stop capturing and release the input stream.

        Never raises: any error while closing the underlying stream
        is logged, not propagated -- `stop()` must always be safe to
        call, including after a failed `start()` or a stream that
        has already errored out on its own.
        """
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:  # noqa: BLE001 - must never crash the caller's shutdown path
                logger.warning(f"Wake Word: error while stopping audio stream: {exc}")
            finally:
                self._stream = None
