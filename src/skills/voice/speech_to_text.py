"""EP-046 Speech-to-Text engine.

Converts audio (raw PCM bytes) into text, entirely offline, using
Vosk (see `docs/architecture/designs/EP046_DESIGN.md`, Section 8/9a
Decision 1). This module owns exactly one responsibility: audio in,
text out. It has no knowledge of the microphone (`audio_capture.py`),
of `CommandRouter`, or of Jarvis commands -- that separation is a
STEP 1 design requirement (Section 5.2), confirmed unchanged by the
owner's STEP 2 approval.

Supported languages are configured, not hard-coded (owner Decision
2): `voice.languages` in `config/config.yaml` lists the enabled
language codes, each requiring its own Vosk model directory under
`voice.model_dir` (owner Decision 10 -- manual model setup, no
downloader). The command-routing layer never needs to change to
support a different or additional language or model (owner
Decision 3) -- only this file and `config/config.yaml` do.

Confidence: Vosk's default recognizer result JSON exposes only a
final `text` field, with no single utterance-level confidence score.
To honor owner Decision 9 (low-confidence transcripts must not be
auto-executed), this engine enables Vosk's per-word confidence
output (`KaldiRecognizer.SetWords(True)`) and normalizes an overall
utterance confidence as the arithmetic mean of each recognized
word's `conf` value (range 0.0-1.0, as Vosk reports it). This is a
documented approximation, not a property Vosk computes natively for
a whole utterance -- see `VoskSpeechToTextEngine._normalize_confidence`
and the corresponding test in `tests/EP046/test_speech_to_text.py`.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from loguru import logger

from src.core.config import Config

if TYPE_CHECKING:
    import vosk

DEFAULT_MODEL_DIR = "data/models/voice"
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_TIMEOUT_SECONDS = 10.0


class SpeechToTextEngineError(Exception):
    """Raised when the STT engine cannot be constructed or loaded.

    Reserved for construction-time failures only (missing model
    directory, unimportable dependency, invalid configuration) --
    never raised by `transcribe_audio()` itself, which always returns
    a `TranscriptionResult` instead (see EP046_DESIGN.md Section 5.4).
    """


@dataclass(frozen=True)
class TranscriptionResult:
    """Outcome of a single transcription attempt.

    Mirrors `CommandResult`'s own shape (`src/core/command_router.py`)
    -- the project's established idiom for "this can fail in
    expected, non-exceptional ways": a caller checks `success`
    instead of catching an exception.

    Attributes:
        success: Whether usable text was recognized. False for
            silence, an empty/corrupt input, an unsupported language,
            or a timeout -- never raised as an exception.
        text: The recognized text. Empty when `success` is False.
        confidence: Normalized utterance confidence in [0.0, 1.0], or
            None if the engine/model does not expose one. See this
            module's docstring for how Vosk's per-word confidence is
            normalized into a single value.
        language: The language code actually used for recognition.
        error: A short, human-readable failure reason. None on
            success.
    """

    success: bool
    text: str
    confidence: float | None
    language: str | None
    error: str | None = None


class SpeechToTextEngine(Protocol):
    """Interface every STT engine implementation must satisfy.

    Only `VoskSpeechToTextEngine` implements this today (owner
    Decision 1). The interface exists so a future engine could be
    substituted -- per `voice.engine` in configuration -- without any
    change to `VoiceModule` (`skill.py`) or `CommandRouter`.
    """

    @property
    def supported_languages(self) -> list[str]:
        """Return the language codes this engine is configured for."""
        ...

    def transcribe_audio(
        self, pcm_data: bytes, sample_rate: int, language: str | None = None
    ) -> TranscriptionResult:
        """Transcribe raw 16-bit mono PCM audio into text.

        Args:
            pcm_data: Raw, little-endian, 16-bit signed mono PCM
                samples (no WAV/container header).
            sample_rate: Sample rate of `pcm_data`, in Hz.
            language: Language code to recognize in. None uses the
                engine's configured default language.

        Returns:
            A TranscriptionResult. Never raises for an expected
            failure (empty audio, unsupported language, timeout,
            engine error) -- those are reported via `success=False`.
        """
        ...


class VoskSpeechToTextEngine:
    """Offline STT engine backed by Vosk (owner Decision 1).

    Loads one Vosk model per configured language, lazily on first
    use, and caches it for the lifetime of this instance. Model
    files are never bundled with Jarvis or downloaded automatically
    (owner Decision 10) -- each language's model must already exist,
    extracted, under `<voice.model_dir>/<language>/`.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the engine from `voice.*` configuration.

        Args:
            config: The application Config.

        Raises:
            SpeechToTextEngineError: If the `vosk` package is not
                importable, if no language is configured, or if the
                configured model directory does not exist at all.
                Individual missing per-language model directories are
                *not* raised here -- they are only detected, and
                reported per-language, on first use of that language
                (see `_load_model`), so one missing language does not
                prevent the others from working.
        """
        try:
            import vosk  # noqa: F401 -- import-availability check only
        except ImportError as exc:
            raise SpeechToTextEngineError(
                "The 'vosk' package is not installed. Add it to the "
                "environment (see requirements.txt) before enabling "
                "'voice.enabled'."
            ) from exc

        self._vosk = vosk
        self._vosk.SetLogLevel(-1)  # suppress Vosk's own stderr logging; Jarvis logs via loguru instead

        languages = config.get("voice.languages", [])
        if not isinstance(languages, list) or not languages:
            raise SpeechToTextEngineError(
                "'voice.languages' must be a non-empty list of language "
                "codes (e.g. ['ru', 'uz', 'en'])."
            )
        self._languages: list[str] = [str(language) for language in languages]

        default_language = str(config.get("voice.default_language", self._languages[0]))
        if default_language not in self._languages:
            raise SpeechToTextEngineError(
                f"'voice.default_language' ('{default_language}') must be one "
                f"of 'voice.languages' ({self._languages})."
            )
        self._default_language = default_language

        self._model_dir = Path(str(config.get("voice.model_dir", DEFAULT_MODEL_DIR)))
        if not self._model_dir.exists():
            raise SpeechToTextEngineError(
                f"Configured 'voice.model_dir' ('{self._model_dir}') does not "
                "exist. Create it and place each configured language's "
                "extracted Vosk model under "
                f"'{self._model_dir}/<language>/' (see EP046_DESIGN.md "
                "Section 6, owner Decision 10 -- manual model setup)."
            )

        self._timeout_seconds = float(
            config.get("voice.timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
        )
        min_confidence = config.get("voice.min_confidence", None)
        self._min_confidence: float | None = (
            float(min_confidence) if min_confidence is not None else None
        )

        self._models: dict[str, "vosk.Model"] = {}
        self._models_lock = threading.Lock()

    @property
    def supported_languages(self) -> list[str]:
        """Return the configured language codes ('voice.languages')."""
        return list(self._languages)

    @property
    def default_language(self) -> str:
        """Return the configured default language ('voice.default_language')."""
        return self._default_language

    @property
    def min_confidence(self) -> float | None:
        """Return the configured minimum acceptable confidence, if any."""
        return self._min_confidence

    def model_available(self, language: str) -> bool:
        """Return whether a model directory exists for `language`.

        Does not load the model -- a cheap existence check only, used
        by `VoiceModule._status()` to report per-language readiness
        without paying the cost of loading every configured model.
        """
        return (self._model_dir / language).is_dir()

    def transcribe_audio(
        self, pcm_data: bytes, sample_rate: int, language: str | None = None
    ) -> TranscriptionResult:
        """Transcribe raw 16-bit mono PCM audio using Vosk.

        See `SpeechToTextEngine.transcribe_audio` for the contract.
        """
        resolved_language = language or self._default_language

        if resolved_language not in self._languages:
            return TranscriptionResult(
                success=False,
                text="",
                confidence=None,
                language=resolved_language,
                error=f"unsupported language: {resolved_language}",
            )

        if not pcm_data:
            return TranscriptionResult(
                success=False,
                text="",
                confidence=None,
                language=resolved_language,
                error="no speech detected",
            )

        try:
            model = self._load_model(resolved_language)
        except SpeechToTextEngineError as exc:
            logger.error(f"Voice: model unavailable for '{resolved_language}': {exc}")
            return TranscriptionResult(
                success=False,
                text="",
                confidence=None,
                language=resolved_language,
                error=str(exc),
            )

        try:
            text, confidence = self._recognize(model, pcm_data, sample_rate)
        except TimeoutError:
            return TranscriptionResult(
                success=False,
                text="",
                confidence=None,
                language=resolved_language,
                error=f"recognition timed out after {self._timeout_seconds}s",
            )
        except Exception as exc:  # noqa: BLE001 - engine errors must never propagate (Section 5.4)
            logger.error(f"Voice: recognition error ({resolved_language}): {exc}")
            return TranscriptionResult(
                success=False,
                text="",
                confidence=None,
                language=resolved_language,
                error=f"recognition error: {exc}",
            )

        if not text.strip():
            return TranscriptionResult(
                success=False,
                text="",
                confidence=confidence,
                language=resolved_language,
                error="no speech detected",
            )

        return TranscriptionResult(
            success=True,
            text=text.strip(),
            confidence=confidence,
            language=resolved_language,
            error=None,
        )

    def _load_model(self, language: str) -> vosk.Model:
        """Load (or return the cached) Vosk model for `language`.

        Raises:
            SpeechToTextEngineError: If the language's model directory
                does not exist, or Vosk fails to load it.
        """
        with self._models_lock:
            cached = self._models.get(language)
            if cached is not None:
                return cached

            model_path = self._model_dir / language
            if not model_path.is_dir():
                raise SpeechToTextEngineError(
                    f"No Vosk model found for language '{language}' at "
                    f"'{model_path}'. Download and extract the model there "
                    "(see EP046_DESIGN.md Section 6/9a for the recommended "
                    "small-model names per language)."
                )

            try:
                model = self._vosk.Model(str(model_path))
            except Exception as exc:  # noqa: BLE001 - Vosk raises plain Exception on load failure
                raise SpeechToTextEngineError(
                    f"Failed to load Vosk model for '{language}' from "
                    f"'{model_path}': {exc}"
                ) from exc

            self._models[language] = model
            logger.info(f"Voice: loaded Vosk model for '{language}' from '{model_path}'")
            return model

    def _recognize(
        self, model: vosk.Model, pcm_data: bytes, sample_rate: int
    ) -> tuple[str, float | None]:
        """Run recognition on `pcm_data` and return (text, confidence).

        Runs on a worker thread so `self._timeout_seconds` can be
        enforced (Vosk's Python API has no native timeout parameter).

        Raises:
            TimeoutError: If recognition exceeds `self._timeout_seconds`.
        """
        recognizer = self._vosk.KaldiRecognizer(model, sample_rate)
        recognizer.SetWords(True)  # required for per-word confidence, see module docstring

        outcome: dict[str, str] = {}

        def _run() -> None:
            recognizer.AcceptWaveform(pcm_data)
            outcome["result_json"] = recognizer.FinalResult()

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        worker.join(timeout=self._timeout_seconds)
        if worker.is_alive():
            raise TimeoutError

        result = json.loads(outcome.get("result_json", "{}"))
        text = str(result.get("text", ""))
        confidence = self._normalize_confidence(result)
        return text, confidence

    @staticmethod
    def _normalize_confidence(result: dict) -> float | None:
        """Approximate one utterance confidence from Vosk's per-word data.

        Vosk's `FinalResult()` JSON, with `SetWords(True)`, includes a
        `result` list of per-word dicts, each with a `conf` field
        (0.0-1.0). This method returns the arithmetic mean of those
        values. Returns None if no per-word data is present (e.g. an
        empty/silent utterance), rather than an artificial 0.0 or 1.0,
        so callers can distinguish "no confidence available" from
        "zero confidence".
        """
        words = result.get("result")
        if not isinstance(words, list) or not words:
            return None

        confidences = [
            float(word["conf"]) for word in words if isinstance(word, dict) and "conf" in word
        ]
        if not confidences:
            return None

        return sum(confidences) / len(confidences)
