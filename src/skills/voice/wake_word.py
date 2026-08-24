"""EP-048 Wake Word detection engine.

Detects a configured wake phrase from a continuous stream of audio
frames, entirely offline, using `openWakeWord` (owner Decision D1,
`docs/architecture/designs/EP048_DESIGN.md` Section 9a). This module
owns exactly one responsibility: audio frames in, a per-frame
detection score out. It has no knowledge of the microphone
(`streaming_audio_capture.py`), of `CommandRouter`, or of Jarvis
commands -- the same separation `speech_to_text.py`/
`text_to_speech.py` already established for their own engines
(EP046_DESIGN.md Section 5.2, EP047_DESIGN.md Section 5.2).

`VoiceModule` (`skill.py`) never imports `openwakeword` directly and
never depends on its API -- only on the `WakeWordEngine` Protocol
below (owner Decision D1: "Use it behind the WakeWordEngine
abstraction... Do not couple VoiceModule directly to openWakeWord").
This is the seam through which a future engine could be substituted
-- per `voice.wake.engine` in configuration -- with no change to
`VoiceModule` or `CommandRouter`, and is also the seam a future EP
could use to add Russian/Uzbek wake-word support (owner Decision D2)
without touching `VoiceModule`.

Per owner Decision D2 (EP048_DESIGN.md Section 9a): only an
English-language "Hey Jarvis" wake phrase is in scope for EP-048 v1.
Russian and Uzbek wake-word detection are explicitly out of scope --
no translation layer, cloud fallback, hidden multilingual
workaround, or custom model training is implemented here. This is a
disclosed limitation, not an oversight, exactly as EP-047 disclosed
its own Uzbek text-to-speech gap.

Per owner Decision D3: model files are never downloaded
automatically. `openwakeword.utils.download_models()` (or any
network-dependent acquisition) is never called by this module.
Model files (the shared feature-extraction models and the wake-word
classifier head) must already exist on disk, under
`voice.wake.model_dir`, placed there manually by the operator --
mirroring `speech_to_text.py`'s own "no automatic downloader" Vosk
precedent (EP046_DESIGN.md, owner Decision 10).

Bugfix (post-STEP-3, real Windows verification): openWakeWord's own
official pretrained models are published with a version suffix in
the filename (e.g. `hey_jarvis_v0.1.onnx`, as downloaded by
`openwakeword.utils.download_models(['hey_jarvis'], ...)` on the real
target machine) -- not the bare `<wake_word>.onnx` this module
originally assumed. `resolve_wakeword_model_path()` below resolves
the configured logical `voice.wake.wake_word` (e.g. `"hey_jarvis"`)
to whichever of those two on-disk naming conventions is actually
present, without ever requiring the operator to rename an official
model file and without ever downloading or guessing among multiple
candidates (owner Decision D3 remains fully honored: this only
*discovers* files already placed in `voice.wake.model_dir`). The
`openwakeword.Model` class itself keys its `predict()` output by the
loaded file's own stem (confirmed by direct inspection of
`openwakeword/model.py`) -- so once a versioned file is resolved,
`process_frame()` must look up that same resolved stem in
`predict()`'s result, not the shorter logical `wake_word` configured
by the operator. Both fixes are applied together below.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from loguru import logger

from src.core.config import Config

DEFAULT_MODEL_DIR = "data/models/wake"
DEFAULT_WAKEWORD = "hey_jarvis"
DEFAULT_LANGUAGE = "en"
DEFAULT_THRESHOLD = 0.5
DEFAULT_FRAME_LENGTH = 1280  # ~80ms at 16kHz, openWakeWord's native frame size
DEFAULT_SAMPLE_RATE = 16000

# Shared feature-extraction model files openWakeWord's `Model` class
# expects to find under `voice.wake.model_dir` alongside the
# wake-word classifier head itself. Names match openWakeWord's own
# upstream release asset names (confirmed against its documented
# manual-installation layout) -- recorded here as constants so a
# missing-file check can name exactly what is missing, rather than a
# bare import/construction failure.
MELSPEC_MODEL_FILENAME = "melspectrogram.onnx"
EMBEDDING_MODEL_FILENAME = "embedding_model.onnx"


class WakeWordEngineError(Exception):
    """Raised when the wake-word engine cannot be constructed.

    Reserved for construction-time failures only (the `openwakeword`
    package not importable, missing/invalid `voice.wake.model_dir`,
    a missing/ambiguous required model file, or invalid
    `voice.wake.*` configuration) -- never raised by `process_frame()`
    itself, which always returns a plain result object instead
    (mirroring `SpeechToTextEngineError`/`AudioCaptureError`/
    `TextToSpeechEngineError`'s established idiom).
    """


def resolve_wakeword_model_path(model_dir: Path, wake_word: str) -> Path:
    """Resolve a configured logical wake word to an on-disk model file.

    Tries, in order, without ever downloading, renaming, or creating
    anything (owner Decision D3 -- this only discovers files already
    present in `model_dir`):

    1. An exact match: `<model_dir>/<wake_word>.onnx`.
    2. Exactly one file matching openWakeWord's own official
       versioned release naming pattern:
       `<model_dir>/<wake_word>_v*.onnx` (e.g. `hey_jarvis_v0.1.onnx`,
       as produced by `openwakeword.utils.download_models()` on a
       real installation -- never called by this project itself, but
       its output naming convention must still be recognized here).

    Args:
        model_dir: The configured `voice.wake.model_dir`, already
            confirmed to exist by the caller.
        wake_word: The configured `voice.wake.wake_word` (e.g.
            `"hey_jarvis"`).

    Returns:
        The resolved model file `Path`.

    Raises:
        WakeWordEngineError: If zero candidate files are found (with
            a message naming both naming conventions this method
            checked), or if more than one versioned candidate is
            found (with a message listing every candidate and asking
            the operator to resolve the ambiguity). Never silently
            picks an arbitrary version.
    """
    exact_path = model_dir / f"{wake_word}.onnx"
    if exact_path.is_file():
        return exact_path

    versioned_candidates = sorted(model_dir.glob(f"{wake_word}_v*.onnx"))
    if len(versioned_candidates) == 1:
        return versioned_candidates[0]

    if len(versioned_candidates) > 1:
        names = ", ".join(path.name for path in versioned_candidates)
        raise WakeWordEngineError(
            f"Multiple candidate model files found for wake word "
            f"'{wake_word}' under '{model_dir}': {names}. This project "
            "never silently picks a version -- remove all but one "
            f"candidate, or rename the intended file to "
            f"'{wake_word}.onnx', to resolve the ambiguity."
        )

    raise WakeWordEngineError(
        f"No openWakeWord model file found for wake word '{wake_word}' "
        f"under '{model_dir}'. Expected either '{wake_word}.onnx' or "
        f"exactly one '{wake_word}_v*.onnx' (openWakeWord's own official "
        f"versioned naming pattern, e.g. '{wake_word}_v0.1.onnx' as "
        "produced by 'openwakeword.utils.download_models()'). Model "
        "files must be placed manually -- see EP048_DESIGN.md Section "
        "9a, owner Decision D3."
    )


@dataclass(frozen=True)
class WakeWordDetectionResult:
    """Outcome of scoring a single audio frame for the wake phrase.

    Mirrors `TranscriptionResult`/`SynthesisResult`'s own shape
    (`speech_to_text.py`/`text_to_speech.py`) -- a caller checks
    fields on this result instead of catching an exception for an
    expected, non-exceptional outcome.

    Attributes:
        detected: Whether this frame's score met or exceeded the
            configured detection threshold.
        score: The raw 0.0-1.0 detection score openWakeWord reported
            for this frame, for the configured wake word.
        wake_word: The wake-word/model name this score belongs to.
    """

    detected: bool
    score: float
    wake_word: str


class WakeWordEngine(Protocol):
    """Interface every wake-word engine implementation must satisfy.

    Only `OpenWakeWordEngine` implements this today (owner Decision
    D1). `VoiceModule` depends only on this Protocol -- never on
    `openwakeword` directly -- so a future engine (or a future
    Russian/Uzbek-capable engine, per Decision D2's "must remain
    replaceable" framing) could be substituted with no change to
    `VoiceModule` or `CommandRouter`.
    """

    @property
    def frame_length(self) -> int:
        """Return the number of PCM samples `process_frame` expects per call."""
        ...

    @property
    def sample_rate(self) -> int:
        """Return the sample rate this engine's models were trained for."""
        ...

    @property
    def wake_word(self) -> str:
        """Return the configured wake-word/model name (e.g. 'hey_jarvis')."""
        ...

    def process_frame(self, pcm_frame: bytes) -> WakeWordDetectionResult:
        """Score one audio frame for the configured wake phrase.

        Args:
            pcm_frame: Little-endian, 16-bit signed mono PCM samples,
                exactly `frame_length` samples long.

        Returns:
            A WakeWordDetectionResult. Never raises for an expected
            failure (a malformed frame is scored as 0.0/not
            detected, never an exception) -- only construction-time
            failures raise `WakeWordEngineError`.
        """
        ...


class OpenWakeWordEngine:
    """Offline wake-word detection via `openWakeWord` (owner Decision D1).

    Wraps `openwakeword.Model`, loading model files strictly from a
    local directory (`voice.wake.model_dir`) with no network access
    at construction or detection time (owner Decision D3). Holds no
    reference to any microphone/capture component or to
    `CommandRouter` -- `VoiceModule` (`skill.py`) is the only
    component that connects this class's output to user-facing
    behavior, and even then only ever to report a detection, never
    to dispatch one (owner Decision D5).
    """

    def __init__(self, config: Config) -> None:
        """Initialize the wake-word engine from `voice.wake.*` configuration.

        Args:
            config: The application Config.

        Raises:
            WakeWordEngineError: If the `openwakeword` package is not
                importable, `voice.wake.model_dir` does not exist or
                is missing a required model file, or `voice.wake.*`
                configuration is invalid (e.g. an out-of-range
                `voice.wake.threshold`).
        """
        try:
            from openwakeword.model import Model
        except ImportError as exc:
            raise WakeWordEngineError(
                "The 'openwakeword' package is not usable (missing package, "
                "or its underlying 'onnxruntime' dependency is not usable). "
                "Add/install it before enabling 'voice.wake.enabled' -- see "
                "requirements.txt."
            ) from exc

        wake_word = str(config.get("voice.wake.wake_word", DEFAULT_WAKEWORD))
        if not wake_word.strip():
            raise WakeWordEngineError(
                "'voice.wake.wake_word' must not be empty."
            )

        threshold = config.get("voice.wake.threshold", DEFAULT_THRESHOLD)
        try:
            threshold = float(threshold)
        except (TypeError, ValueError) as exc:
            raise WakeWordEngineError(
                f"'voice.wake.threshold' ({threshold!r}) must be a number."
            ) from exc
        if not 0.0 <= threshold <= 1.0:
            raise WakeWordEngineError(
                f"'voice.wake.threshold' ({threshold!r}) must be between 0.0 and 1.0."
            )

        model_dir = Path(str(config.get("voice.wake.model_dir", DEFAULT_MODEL_DIR)))
        if not model_dir.is_dir():
            raise WakeWordEngineError(
                f"'voice.wake.model_dir' ({model_dir}) does not exist. Manually "
                "download the required openWakeWord model files (the shared "
                f"'{MELSPEC_MODEL_FILENAME}'/'{EMBEDDING_MODEL_FILENAME}' feature "
                f"extractors, plus a wake-word model matching '{wake_word}') and "
                "place them there -- openWakeWord's models are never downloaded "
                "automatically by this project (owner Decision D3)."
            )

        melspec_path = model_dir / MELSPEC_MODEL_FILENAME
        embedding_path = model_dir / EMBEDDING_MODEL_FILENAME
        missing_shared = [
            str(path) for path in (melspec_path, embedding_path) if not path.is_file()
        ]
        if missing_shared:
            raise WakeWordEngineError(
                "Missing required openWakeWord model file(s) under "
                f"'voice.wake.model_dir' ({model_dir}): {', '.join(missing_shared)}. "
                "Model files must be placed manually -- see "
                "EP048_DESIGN.md Section 9a, owner Decision D3."
            )

        # Resolves both '<wake_word>.onnx' and openWakeWord's own
        # official versioned naming (e.g. '<wake_word>_v0.1.onnx') --
        # raises WakeWordEngineError itself on zero or multiple
        # candidates (post-STEP-3 bugfix; see module docstring).
        wakeword_model_path = resolve_wakeword_model_path(model_dir, wake_word)

        try:
            model = Model(
                wakeword_models=[str(wakeword_model_path)],
                melspec_model_path=str(melspec_path),
                embedding_model_path=str(embedding_path),
                inference_framework="onnx",
            )
        except Exception as exc:  # noqa: BLE001 - model/runtime errors must never crash Bootstrap
            raise WakeWordEngineError(
                f"openWakeWord could not load the configured model(s) from "
                f"'{model_dir}' ({exc})."
            ) from exc

        self._model = model
        self._wake_word = wake_word
        # openwakeword.Model keys its predict() output by the loaded
        # file's own stem (confirmed by direct inspection of
        # openwakeword/model.py) -- for a versioned file this differs
        # from the configured logical `wake_word` (e.g.
        # "hey_jarvis_v0.1" vs. "hey_jarvis"), so process_frame() must
        # look up this resolved key, not `self._wake_word`, in
        # predict()'s result (post-STEP-3 bugfix; see module
        # docstring).
        self._model_key = wakeword_model_path.stem
        self._threshold = threshold
        self._model_dir = model_dir
        self._sample_rate = int(config.get("voice.wake.sample_rate", DEFAULT_SAMPLE_RATE))
        self._frame_length = int(config.get("voice.wake.frame_length", DEFAULT_FRAME_LENGTH))

    @property
    def frame_length(self) -> int:
        """Return the configured number of PCM samples expected per frame."""
        return self._frame_length

    @property
    def sample_rate(self) -> int:
        """Return the configured sample rate ('voice.wake.sample_rate')."""
        return self._sample_rate

    @property
    def wake_word(self) -> str:
        """Return the configured wake-word/model name ('voice.wake.wake_word')."""
        return self._wake_word

    @property
    def threshold(self) -> float:
        """Return the configured detection threshold ('voice.wake.threshold')."""
        return self._threshold

    @property
    def model_dir(self) -> Path:
        """Return the configured model directory ('voice.wake.model_dir')."""
        return self._model_dir

    @property
    def model_key(self) -> str:
        """Return the resolved on-disk model file's stem (e.g. 'hey_jarvis_v0.1').

        May differ from `wake_word` (e.g. 'hey_jarvis') when the
        configured logical wake word resolved to an official
        versioned filename (post-STEP-3 bugfix; see module
        docstring, `resolve_wakeword_model_path()`).
        """
        return self._model_key

    def model_available(self) -> bool:
        """Return whether the configured wake-word model loaded successfully.

        Always True once construction succeeds -- construction
        itself raises `WakeWordEngineError` rather than leaving this
        engine in a half-initialized state. Mirrors
        `VoskSpeechToTextEngine.model_available()`/
        `Pyttsx3TextToSpeechEngine.voice_available()`'s role for
        `voice status`/`voice wake status`.
        """
        return True

    def process_frame(self, pcm_frame: bytes) -> WakeWordDetectionResult:
        """Score one audio frame. See `WakeWordEngine.process_frame`.

        Never raises: a malformed/short frame or an engine runtime
        error is reported as a zero, undetected score rather than
        propagated -- streaming detection must never crash mid-loop
        on one bad frame (EP048_DESIGN.md Section 5.5).
        """
        try:
            import numpy as np

            samples = np.frombuffer(pcm_frame, dtype=np.int16)
            predictions = self._model.predict(samples)
            # Keyed by the loaded model file's own stem (self._model_key,
            # e.g. "hey_jarvis_v0.1"), not the shorter configured
            # `wake_word` (e.g. "hey_jarvis") -- post-STEP-3 bugfix, see
            # module docstring.
            score = float(predictions.get(self._model_key, 0.0))
        except Exception as exc:  # noqa: BLE001 - a bad frame must never crash the detection loop
            logger.error(f"Wake Word: frame scoring failed: {exc}")
            return WakeWordDetectionResult(
                detected=False, score=0.0, wake_word=self._wake_word
            )

        return WakeWordDetectionResult(
            detected=score >= self._threshold,
            score=score,
            wake_word=self._wake_word,
        )
