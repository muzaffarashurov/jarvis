"""Gemini Provider (EP-015.1 / EP-015.2 / EP-015.3): real Google Gemini API integration.

GeminiProvider is the second concrete AIProvider (EP-014), talking to
a real AI API over HTTPS via the existing `requests` dependency, the
same way ClaudeProvider does (src/core/ai/claude_provider.py) -- no
new dependency, no unofficial SDK. Each request is independent (no
conversation history), matching ClaudeProvider's EP-015 contract.

Responsibilities:
    - identity/status/configuration/health from 'providers.gemini.*'
      only (no network access).
    - `ask()`/`ping()` via generateContent
      (https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent).
    - `list_models()` (EP-015.2) via ModelService.ListModels
      (GET '.../v1beta/models'), so Jarvis sees the real models this
      API key has -- never a hardcoded or config-echoed guess.
    - On HTTP 404 from generateContent (EP-015.2), auto-call
      ListModels and fold the available models plus a closest-match
      suggestion into the raised ProviderError -- self-diagnosing
      instead of a bare 404.
    - Every failure maps into the shared ProviderError hierarchy
      (src/core/ai/provider.py); never logs/returns the raw API key.

EP-015.3 note: `validate_configured_model()` is now called by
AIService.use_provider() right after `ai use gemini` selects this
provider, so an invalid 'providers.gemini.model' is reported
immediately instead of only surfacing on the next
`ask()`/`ping()`/`ai test`. `ping()` also reuses this same check (via
`validate_configured_model()`) to decide `authenticated` from
ListModels rather than from a generateContent call alone, so an
invalid model no longer masquerades as a failed authentication.

EP-084 note: `generate_speech()` uses this same `generateContent`
endpoint with a TTS-capable model (`providers.gemini.audio_model`) and
wraps Gemini's raw PCM response into a valid WAV container
(`_pcm_to_wav()`, using only the standard-library `wave` module)
before returning it, per Owner Decision D2
(`EP084_DESIGN.md` Section 9/25).
"""

from __future__ import annotations

import difflib
import re
import time
import wave
from base64 import b64decode, b64encode
from io import BytesIO
from typing import Any

import requests
from loguru import logger

from src.core.ai.provider import (
    AIProvider,
    GeneratedAudio,
    GeneratedImage,
    ImageGenerationRequest,
    ImageGenerationResult,
    ModelValidationResult,
    PingResult,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderError,
    ProviderHealth,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponse,
    ProviderStatus,
    ProviderTimeoutError,
    ProviderUnavailableError,
    SpeechGenerationRequest,
    SpeechGenerationResult,
    validate_temperature,
)

__all__ = ["GeminiProvider"]

_API_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/models"
_PROVIDER_NAME: str = "gemini"
_GENERATE_CONTENT_METHOD: str = "generateContent"
_MODEL_NAME_PREFIX: str = "models/"

# EP-084: Gemini's TTS `generateContent` response returns raw,
# headerless 16-bit linear PCM audio (mimeType e.g.
# "audio/L16;codec=pcm;rate=24000") -- always mono, always 16-bit,
# per Google's current, documented TTS output format (verified during
# EP-084 STEP 1; `EP084_DESIGN.md` Section 9). Only the sample rate
# varies and is carried in the mimeType string itself; these two are
# therefore fixed constants, not configuration.
_PCM_SAMPLE_WIDTH_BYTES: int = 2  # 16-bit
_PCM_CHANNELS: int = 1  # mono
# Gemini's own current default TTS sample rate, used only as a
# fallback if a future response's mimeType cannot be parsed for its
# own rate (`EP084_DESIGN.md` Section 15) -- never used to override a
# rate that WAS successfully parsed.
_PCM_DEFAULT_SAMPLE_RATE_HZ: int = 24000
_PCM_RATE_PATTERN = re.compile(r"rate=(\d+)")


class GeminiProvider(AIProvider):
    """AIProvider implementation backed by the official Google Gemini API."""

    def __init__(
        self,
        enabled: bool,
        api_key: str,
        model: str,
        timeout: int,
        max_tokens: int,
        temperature: float,
        image_model: str | None = None,
        audio_model: str | None = None,
    ) -> None:
        """Initialize the GeminiProvider.

        Args:
            enabled: Value of 'providers.gemini.enabled'.
            api_key: Value of 'providers.gemini.api_key'. Never logged
                or returned; used only as the 'x-goog-api-key' header.
            model: Value of 'providers.gemini.model'.
            timeout: Value of 'providers.gemini.timeout', in seconds.
            max_tokens: Value of 'providers.gemini.max_tokens'.
            temperature: Value of 'providers.gemini.temperature'.
            image_model: Value of 'providers.gemini.image_model'
                (EP-083). None or empty means this provider instance
                does not support image generation --
                `supports_image_generation()` returns False and
                `generate_image()` is never expected to be called.
                Distinct from `model` above, which remains the text
                model EP-082 already uses.
            audio_model: Value of 'providers.gemini.audio_model'
                (EP-084). None or empty means this provider instance
                does not support speech generation --
                `supports_speech_generation()` returns False and
                `generate_speech()` is never expected to be called.
                Distinct from `model`/`image_model` above.
        """
        self._enabled = enabled
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._image_model = image_model or None
        self._audio_model = audio_model or None

    # ---------- AIProvider: identity / configuration / health ----------

    def name(self) -> str:
        """Return this provider's stable identifier: "gemini"."""
        return _PROVIDER_NAME

    def status(self) -> ProviderStatus:
        """Return this provider's current ProviderStatus."""
        if not self._enabled:
            return ProviderStatus.DISABLED
        if not self._api_key.strip():
            return ProviderStatus.NOT_CONFIGURED
        return ProviderStatus.AVAILABLE

    def is_available(self) -> bool:
        """Return whether this provider is enabled and has an API key."""
        return self._enabled and bool(self._api_key.strip())

    def configuration(self) -> dict[str, Any]:
        """Return a non-secret snapshot of this provider's configuration.

        Never includes the raw API key.
        """
        return {
            "enabled": self._enabled,
            "configured": bool(self._api_key.strip()),
            "credential_key": "api_key",
            "model": self._model,
            "timeout": self._timeout,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
            "image_model": self._image_model,
            "audio_model": self._audio_model,
        }

    def health(self) -> ProviderHealth:
        """Return a configuration-derived readiness check (no network access)."""
        if not self._enabled:
            return ProviderHealth(available=False, message="Provider 'gemini' is disabled.")
        if not self._api_key.strip():
            return ProviderHealth(
                available=False, message="Provider 'gemini' is missing 'api_key'."
            )
        return ProviderHealth(available=True, message="Provider 'gemini' is configured.")

    # ---------- AIProvider: EP-015 real communication ----------

    def ask(
        self,
        prompt: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> ProviderResponse:
        """Send `prompt` to the Google Gemini API and return its reply.

        Args:
            prompt: The user prompt to send.
            max_tokens: Optional override for the reply's maximum
                token count. None uses 'providers.gemini.max_tokens'.
            temperature: Optional per-request override for
                'providers.gemini.temperature' (EP-082). None
                preserves the configured default unchanged.
            system_prompt: Optional per-request system instruction
                sent as the Generative Language API's top-level
                'systemInstruction' field (EP-082). None omits it,
                unchanged from pre-EP-082 behavior.

        Returns:
            The provider's reply. Errors are mapped to ProviderError
            subtypes by `_send_request()`, `_raise_for_transport_status()`
            and `_build_model_not_found_error()`.

        Raises:
            ProviderConfigurationError: If this provider is disabled,
                missing its API key, or `temperature` is outside the
                valid 0.0-1.0 range.
        """
        if not self._enabled:
            raise ProviderConfigurationError("Provider 'gemini' is disabled.")
        if not self._api_key.strip():
            raise ProviderConfigurationError("Provider 'gemini' is missing 'api_key'.")
        validate_temperature(temperature)

        url = f"{_API_BASE_URL}/{self._model}:generateContent"
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens if max_tokens is not None else self._max_tokens,
                "temperature": temperature if temperature is not None else self._temperature,
            },
        }
        if system_prompt is not None:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        headers = {
            "x-goog-api-key": self._api_key,
            "content-type": "application/json",
        }

        logger.info(f"AI request started (provider='gemini', model='{self._model}').")
        started = time.monotonic()
        response = self._send_request("POST", url, headers, "request", json=payload)

        latency_ms = (time.monotonic() - started) * 1000
        result = self._parse_response(response, latency_ms)
        logger.info(
            f"AI request finished (provider='gemini', model='{result.model}', "
            f"latency={latency_ms:.0f}ms)."
        )
        return result

    # ---------- AIProvider: EP-083 image generation ----------

    def supports_image_generation(self) -> bool:
        """Return whether this provider instance is configured for image generation.

        True only when 'providers.gemini.image_model' is set to a
        non-empty value (EP-083) -- independent of `is_available()`,
        which governs text generation via `enabled`/`api_key` only.
        A `True` result here does not by itself mean a request will
        succeed (the API key or model may still be invalid); it means
        this provider instance is *configured* to attempt one.
        """
        return self._image_model is not None

    def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """Generate image(s) via the Google Gemini API and return the result.

        Uses the same `generateContent` endpoint `ask()` already
        calls, per Google's documented image-generation support: an
        image-capable model (`providers.gemini.image_model`, distinct
        from the text `model`) is requested with
        `generationConfig.responseModalities: ["IMAGE"]`, and the
        response's candidate `parts` are expected to contain
        `inlineData` entries (`{mimeType, data}`, base64-encoded)
        instead of/alongside `text` (`EP083_DESIGN.md` Section 7,
        verified against Google's current API documentation during
        STEP 1/preflight, not assumed).

        Args:
            request: The provider-independent image-generation
                request.

        Returns:
            The provider's reply, containing one or more
            `GeneratedImage` entries.

        Raises:
            ProviderConfigurationError: If this provider is disabled,
                missing its API key, not configured with an
                'image_model', or `request.number_of_images` is not a
                positive integer.
            ProviderAuthenticationError: If the API key is rejected.
            ProviderRateLimitError: If the API reports a rate limit.
            ProviderTimeoutError: If the request exceeds the
                configured timeout.
            ProviderNetworkError: If the request cannot reach the API.
            ProviderUnavailableError: If the API is unreachable, the
                configured image model is not found, or the response
                contains no image data.
        """
        if not self._enabled:
            raise ProviderConfigurationError("Provider 'gemini' is disabled.")
        if not self._api_key.strip():
            raise ProviderConfigurationError("Provider 'gemini' is missing 'api_key'.")
        if not self.supports_image_generation():
            raise ProviderConfigurationError(
                "Provider 'gemini' is not configured for image generation "
                "(set 'providers.gemini.image_model')."
            )
        # `self._image_model` is `str | None`; `supports_image_generation()`
        # (line above) already guarantees it is not None here, but that
        # guarantee is not visible to a static type checker across a
        # method call. Narrow it explicitly into a local variable rather
        # than a bare `assert` (EP-082 STEP 3 hardening precedent:
        # `assert` is stripped under Python's `-O` mode and must never be
        # the sole runtime enforcement of an invariant). This replaces
        # STEP 2's original, functionally-redundant second `if ... is
        # None: raise` block, which duplicated this same check and error
        # message (EP-083 STEP 3 audit finding F1).
        image_model = self._image_model
        if image_model is None:
            raise ProviderConfigurationError(
                "Provider 'gemini' is not configured for image generation "
                "(set 'providers.gemini.image_model')."
            )
        if request.number_of_images < 1:
            raise ProviderConfigurationError(
                f"Invalid 'number_of_images': {request.number_of_images!r} "
                "must be a positive integer."
            )

        url = f"{_API_BASE_URL}/{image_model}:generateContent"
        user_parts: list[dict[str, Any]] = [{"text": request.prompt}]
        if request.negative_prompt:
            user_parts.append({"text": f"Avoid: {request.negative_prompt}"})
        generation_config: dict[str, Any] = {"responseModalities": ["IMAGE"]}
        if request.seed is not None:
            generation_config["seed"] = request.seed
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": user_parts}],
            "generationConfig": generation_config,
        }
        headers = {
            "x-goog-api-key": self._api_key,
            "content-type": "application/json",
        }

        logger.info(f"AI image request started (provider='gemini', model='{self._image_model}').")
        started = time.monotonic()
        response = self._send_request("POST", url, headers, "image request", json=payload)

        latency_ms = (time.monotonic() - started) * 1000
        result = self._parse_image_response(response, latency_ms)
        logger.info(
            f"AI image request finished (provider='gemini', model='{result.model}', "
            f"images={len(result.images)}, latency={latency_ms:.0f}ms)."
        )
        return result

    # ---------- AIProvider: EP-084 speech generation ----------

    def supports_speech_generation(self) -> bool:
        """Return whether this provider instance is configured for speech generation.

        True only when 'providers.gemini.audio_model' is set to a
        non-empty value (EP-084) -- independent of `is_available()`,
        which governs text generation via `enabled`/`api_key` only,
        and independent of `supports_image_generation()`. A `True`
        result here does not by itself mean a request will succeed
        (the API key or model may still be invalid); it means this
        provider instance is *configured* to attempt one.
        """
        return self._audio_model is not None

    def generate_speech(self, request: SpeechGenerationRequest) -> SpeechGenerationResult:
        """Generate spoken audio via the Google Gemini API and return the result.

        Uses the same `generateContent` endpoint `ask()`/
        `generate_image()` already call, per Google's documented
        text-to-speech support: a TTS-capable model
        (`providers.gemini.audio_model`, distinct from the text
        `model` and the image `image_model`) is requested with
        `generationConfig.responseModalities: ["AUDIO"]` and, when a
        voice is requested, `speechConfig.voiceConfig.
        prebuiltVoiceConfig.voiceName`. The response's candidate
        `parts` are expected to contain one `inlineData` entry holding
        raw, headerless 16-bit linear PCM audio (`EP084_DESIGN.md`
        Section 7/9/15, verified against Google's current API
        documentation during EP-084 STEP 1, not assumed).

        Per Owner Decision D2 (`EP084_DESIGN.md` Section 9/25), the
        raw PCM is wrapped into a valid, directly playable WAV
        container (`_pcm_to_wav()`) before being returned -- the
        result's `mime_type` is therefore always "audio/wav",
        regardless of the raw `mimeType` Gemini itself reported.

        `request.language` has no structured Gemini parameter to map
        to (`EP084_DESIGN.md` Section 10) -- when supplied, it is
        applied as a best-effort natural-language instruction
        prepended to `request.text`, exactly as Google's own TTS
        documentation demonstrates steering language/style through
        prompt content rather than a discrete config field.

        Args:
            request: The provider-independent speech-generation
                request.

        Returns:
            The provider's reply, containing one `GeneratedAudio`
            entry.

        Raises:
            ProviderConfigurationError: If this provider is disabled,
                missing its API key, not configured with an
                'audio_model', or `request.text` is empty.
            ProviderAuthenticationError: If the API key is rejected.
            ProviderRateLimitError: If the API reports a rate limit.
            ProviderTimeoutError: If the request exceeds the
                configured timeout.
            ProviderNetworkError: If the request cannot reach the API.
            ProviderUnavailableError: If the API is unreachable, the
                configured audio model is not found, or the response
                contains no audio data.
        """
        if not self._enabled:
            raise ProviderConfigurationError("Provider 'gemini' is disabled.")
        if not self._api_key.strip():
            raise ProviderConfigurationError("Provider 'gemini' is missing 'api_key'.")
        audio_model = self._audio_model
        if audio_model is None:
            raise ProviderConfigurationError(
                "Provider 'gemini' is not configured for speech generation "
                "(set 'providers.gemini.audio_model')."
            )
        if not request.text.strip():
            raise ProviderConfigurationError("'text' must not be empty.")

        text = request.text
        if request.language:
            text = f"Speak the following in {request.language}: {text}"

        url = f"{_API_BASE_URL}/{audio_model}:generateContent"
        generation_config: dict[str, Any] = {"responseModalities": ["AUDIO"]}
        if request.voice:
            generation_config["speechConfig"] = {
                "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": request.voice}}
            }
        if request.seed is not None:
            generation_config["seed"] = request.seed
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": generation_config,
        }
        headers = {
            "x-goog-api-key": self._api_key,
            "content-type": "application/json",
        }

        logger.info(f"AI speech request started (provider='gemini', model='{self._audio_model}').")
        started = time.monotonic()
        response = self._send_request("POST", url, headers, "speech request", json=payload)

        latency_ms = (time.monotonic() - started) * 1000
        result = self._parse_speech_response(response, latency_ms)
        logger.info(
            f"AI speech request finished (provider='gemini', model='{result.model}', "
            f"latency={latency_ms:.0f}ms)."
        )
        return result

    def ping(self) -> PingResult:
        """Check reachability, latency, model and authentication for this provider.

        `authenticated` reflects API authentication only (EP-015.3):
        it is derived from `validate_configured_model()`, which calls
        ModelService.ListModels -- if that call succeeds, the API key
        is valid, regardless of whether 'providers.gemini.model' is
        itself usable for `generateContent`. `reachable` reflects
        whether text generation is *currently* available: it is only
        True once an actual `generateContent` call (via `ask()`)
        succeeds. This avoids the EP-015.2 bug where an invalid
        configured model (a `generateContent` 404) was reported as a
        failed authentication.
        """
        if not self.is_available():
            return PingResult(
                reachable=False,
                latency_ms=0.0,
                model=self._model,
                authenticated=False,
                message=self.health().message,
            )

        started = time.monotonic()
        validation = self.validate_configured_model()

        # ListModels succeeded if either the model matched (valid) or it
        # returned a (possibly non-matching) model list -- both mean the
        # API key itself was accepted. An empty available_models with
        # valid=False means ListModels itself could not be completed
        # (e.g. bad credentials), which is a real authentication failure.
        listmodels_ok = validation.valid or bool(validation.available_models)
        if not listmodels_ok:
            return self._ping_result(started, reachable=False, authenticated=False, message=validation.message)

        if not validation.valid:
            # Authenticated, but the configured model can't currently
            # generate text -- text generation is not reachable.
            return self._ping_result(started, reachable=False, authenticated=True, message=validation.message)

        try:
            response = self.ask("ping", max_tokens=1)
        except ProviderRateLimitError as exc:
            return self._ping_result(started, reachable=True, authenticated=True, message=str(exc))
        except ProviderError as exc:
            return self._ping_result(started, reachable=False, authenticated=True, message=str(exc))

        return PingResult(
            reachable=True,
            latency_ms=response.latency_ms,
            model=response.model,
            authenticated=True,
            message="Provider reachable.",
        )

    def _ping_result(
        self, started: float, *, reachable: bool, authenticated: bool, message: str
    ) -> PingResult:
        """Build a PingResult for `ping()`'s exception branches using elapsed time since `started`."""
        return PingResult(
            reachable=reachable,
            latency_ms=(time.monotonic() - started) * 1000,
            model=self._model,
            authenticated=authenticated,
            message=message,
        )

    def list_models(self) -> list[str]:
        """Return the models this API key can call `generateContent` on (EP-015.2).

        Calls ModelService.ListModels (GET '.../v1beta/models'); never
        hardcodes model names. Never raises -- falls back to the
        single configured model (EP-015.1 behavior) if live discovery
        fails for any reason, matching AIService.models()'s
        no-exception-handling call site.

        Returns:
            Every model ListModels returns that supports
            'generateContent', sorted. Falls back to
            ['providers.gemini.model'] if discovery is not possible.
        """
        if not self.is_available():
            return [self._model]

        try:
            models = self._fetch_model_ids()
        except ProviderError as exc:
            logger.error(f"AI model discovery failed (provider='gemini'): {exc}")
            return [self._model]

        return models if models else [self._model]

    def validate_configured_model(self) -> ModelValidationResult:
        """Verify 'providers.gemini.model' against the live ListModels result (EP-015.2).

        Called by `AIService.use_provider()` right after `ai use
        gemini` selects this provider (EP-015.3), and reused by
        `ping()` to determine `authenticated` from ListModels rather
        than from a generateContent call alone.

        Returns:
            Whether the configured model exists for this API key,
            the live model list, and (if invalid) the closest match.
        """
        if not self.is_available():
            return ModelValidationResult(False, self._model, (), None, self.health().message)

        try:
            available = self._fetch_model_ids()
        except ProviderError as exc:
            return ModelValidationResult(
                False, self._model, (), None, f"Could not verify 'providers.gemini.model': {exc}"
            )

        if self._model in available:
            return ModelValidationResult(
                True,
                self._model,
                tuple(available),
                None,
                f"Configured model '{self._model}' is available for this API key.",
            )

        suggestion, detail = self._describe_mismatch(available)
        return ModelValidationResult(
            False,
            self._model,
            tuple(available),
            suggestion,
            f"Configured model '{self._model}' is not available for this API key.{detail}",
        )

    # ---------- Internal helpers ----------

    def _send_request(
        self, method: str, url: str, headers: dict[str, str], action: str, json: Any | None = None
    ) -> requests.Response:
        """Send an HTTP request, mapping transport failures to ProviderError subtypes.

        Shared by the generateContent and ListModels call sites (DRY).
        `action` (e.g. "request", "model discovery") names the call in
        log lines and error messages.
        """
        try:
            return requests.request(method, url, headers=headers, json=json, timeout=self._timeout)
        except requests.exceptions.Timeout as exc:
            logger.error(f"AI {action} timed out (provider='gemini', timeout={self._timeout}s).")
            raise ProviderTimeoutError(f"Gemini {action} timed out after {self._timeout}s.") from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error(f"AI {action} network failure (provider='gemini'): {exc}")
            raise ProviderNetworkError("Could not reach the Google Gemini API.") from exc
        except requests.exceptions.RequestException as exc:
            logger.error(f"AI {action} failed (provider='gemini'): {exc}")
            raise ProviderNetworkError(str(exc)) from exc

    def _fetch_model_ids(self) -> list[str]:
        """Call ModelService.ListModels and return the usable model IDs.

        Only models whose 'supportedGenerationMethods' includes
        'generateContent' are returned -- this is how we confirm the
        API key actually has generateContent access to each model,
        not merely that the model exists (EP-015.2 item 8). Never
        hardcodes model names; the list is entirely API-provided,
        stripped of the 'models/' resource prefix.

        Returns:
            Sorted list of model IDs usable with `generateContent`.
            Errors are mapped to ProviderError subtypes by
            `_send_request()` and `_raise_for_transport_status()`.
        """
        if not self._enabled:
            raise ProviderConfigurationError("Provider 'gemini' is disabled.")
        if not self._api_key.strip():
            raise ProviderConfigurationError("Provider 'gemini' is missing 'api_key'.")

        headers = {"x-goog-api-key": self._api_key}
        logger.info("AI model discovery started (provider='gemini').")
        response = self._send_request("GET", _API_BASE_URL, headers, "model discovery")
        self._raise_for_transport_status(response, "ListModels request")

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderUnavailableError(
                "Gemini ListModels returned an invalid response body."
            ) from exc

        models = data.get("models", [])
        if not isinstance(models, list):
            return []

        model_ids: list[str] = []
        for entry in models:
            if not isinstance(entry, dict):
                continue
            methods = entry.get("supportedGenerationMethods", [])
            if not isinstance(methods, list) or _GENERATE_CONTENT_METHOD not in methods:
                continue
            raw_name = entry.get("name", "")
            if not isinstance(raw_name, str) or not raw_name:
                continue
            model_id = (
                raw_name[len(_MODEL_NAME_PREFIX) :]
                if raw_name.startswith(_MODEL_NAME_PREFIX)
                else raw_name
            )
            model_ids.append(model_id)

        logger.info(f"AI model discovery finished (provider='gemini', count={len(model_ids)}).")
        return sorted(model_ids)

    def _build_model_not_found_error(self) -> ProviderError:
        """Build a self-diagnosing error for a 404 from generateContent (EP-015.2 item 7).

        Automatically calls ListModels so the raised error names the
        configured model, every model actually available, and the
        closest valid match -- instead of a bare, non-actionable 404.
        """
        try:
            available = self._fetch_model_ids()
        except ProviderError:
            return ProviderError(
                f"Gemini model '{self._model}' was not found for this API key (HTTP 404). "
                "The available-models lookup (ModelService.ListModels) also failed, so no "
                "suggestions could be retrieved. Check 'providers.gemini.api_key' and "
                "'providers.gemini.model' in config.yaml."
            )

        _, detail = self._describe_mismatch(available)
        return ProviderError(
            f"Gemini model '{self._model}' was not found for this API key (HTTP 404). This "
            f"means the API key is valid but does not have 'generateContent' access to "
            f"'{self._model}' -- the name may be misspelled/outdated, or not enabled for this "
            f"key's project/tier/region.{detail}"
        )

    def _describe_mismatch(self, available: list[str]) -> tuple[str | None, str]:
        """Return (closest available match to `self._model`, message fragment naming it + the list)."""
        suggestion = self._closest_match(self._model, available)
        suggestion_text = f" Closest match: '{suggestion}'." if suggestion else ""
        available_text = ", ".join(available) if available else "(none returned for this API key)"
        return suggestion, f"{suggestion_text} Available models: {available_text}."

    @staticmethod
    def _closest_match(target: str, candidates: list[str]) -> str | None:
        """Return the available model name with the highest string similarity to `target`."""
        if not candidates:
            return None
        matches = difflib.get_close_matches(target, candidates, n=1, cutoff=0.0)
        return matches[0] if matches else None

    @staticmethod
    def _raise_for_transport_status(response: requests.Response, action: str) -> None:
        """Raise the shared ProviderError subtype for a non-2xx status (401/403/429/5xx/other).

        Shared by both the generateContent and ListModels call sites
        (DRY). No-op on HTTP 200. `action` names the call in the
        resulting error message (e.g. "request", "ListModels request").
        """
        if response.status_code in (401, 403):
            raise ProviderAuthenticationError(
                "Gemini rejected the configured API key. Check 'providers.gemini.api_key'."
            )
        if response.status_code == 429:
            raise ProviderRateLimitError("Gemini rate limit exceeded. Please retry later.")
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"Gemini API is currently unavailable (HTTP {response.status_code})."
            )
        if response.status_code != 200:
            message = GeminiProvider._extract_error_message(response)
            raise ProviderError(
                f"Gemini {action} failed (HTTP {response.status_code}): {message}"
            )

    def _parse_response(self, response: requests.Response, latency_ms: float) -> ProviderResponse:
        """Translate a raw `requests.Response` into a ProviderResponse or error.

        HTTP 404 is routed through `_build_model_not_found_error()`;
        every other non-2xx status through `_raise_for_transport_status()`.
        """
        if response.status_code == 404:
            raise self._build_model_not_found_error()
        self._raise_for_transport_status(response, "request")

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderUnavailableError("Gemini returned an invalid response body.") from exc

        text = self._extract_text(data)
        return ProviderResponse(text=text, model=self._model, latency_ms=latency_ms)

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        """Concatenate the "text" parts of the first candidate in a generateContent response."""
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict)).strip()
        except (KeyError, IndexError, TypeError, AttributeError):
            return ""

    def _parse_image_response(
        self, response: requests.Response, latency_ms: float
    ) -> ImageGenerationResult:
        """Translate a raw `requests.Response` from an image `generateContent` call (EP-083).

        A 404 here means the configured 'image_model' was not found --
        reported directly (not via `_build_model_not_found_error()`,
        which is specific to the text `model` field) so the error
        names the correct configuration key. Every other non-2xx
        status is shared with `ask()` via `_raise_for_transport_status()`.
        """
        if response.status_code == 404:
            raise ProviderUnavailableError(
                f"Gemini image model '{self._image_model}' was not found for this API key "
                "(HTTP 404). Check 'providers.gemini.image_model' in config.yaml."
            )
        self._raise_for_transport_status(response, "image request")

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderUnavailableError("Gemini returned an invalid response body.") from exc

        images = self._extract_images(data)
        if not images:
            raise ProviderUnavailableError(
                "Gemini image request succeeded but the response contained no image data."
            )
        return ImageGenerationResult(
            images=tuple(images), model=str(self._image_model), latency_ms=latency_ms
        )

    @staticmethod
    def _extract_images(data: dict[str, Any]) -> list[GeneratedImage]:
        """Extract every `inlineData` image part of the first candidate in a generateContent response."""
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            return []
        images: list[GeneratedImage] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline_data = part.get("inlineData")
            if not isinstance(inline_data, dict):
                continue
            encoded = inline_data.get("data")
            mime_type = inline_data.get("mimeType")
            if isinstance(encoded, str) and isinstance(mime_type, str) and encoded:
                images.append(GeneratedImage(data_base64=encoded, mime_type=mime_type))
        return images

    def _parse_speech_response(
        self, response: requests.Response, latency_ms: float
    ) -> SpeechGenerationResult:
        """Translate a raw `requests.Response` from a speech `generateContent` call (EP-084).

        A 404 here means the configured 'audio_model' was not found --
        reported directly (mirroring `_parse_image_response()`'s own
        404 handling) so the error names the correct configuration
        key. Every other non-2xx status is shared with `ask()`/
        `generate_image()` via `_raise_for_transport_status()`.
        """
        if response.status_code == 404:
            raise ProviderUnavailableError(
                f"Gemini audio model '{self._audio_model}' was not found for this API key "
                "(HTTP 404). Check 'providers.gemini.audio_model' in config.yaml."
            )
        self._raise_for_transport_status(response, "speech request")

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderUnavailableError("Gemini returned an invalid response body.") from exc

        raw_audio = self._extract_audio(data)
        if raw_audio is None:
            raise ProviderUnavailableError(
                "Gemini speech request succeeded but the response contained no audio data."
            )
        raw_data_base64, raw_mime_type = raw_audio
        try:
            wav_data_base64 = self._pcm_to_wav(raw_data_base64, raw_mime_type)
        except (ValueError, wave.Error) as exc:
            # EP-084 STEP 3 audit (Audit 6/8): `_pcm_to_wav()` decodes
            # base64 and writes a WAV container -- either step can
            # fail on a malformed/corrupt response (invalid base64
            # padding raises `binascii.Error`, a `ValueError`
            # subclass; an internal `wave` failure raises
            # `wave.Error`, which is not). Both must be normalized
            # into a `ProviderError` here -- otherwise they propagate
            # past `ProviderRequestExecutor._run()`'s
            # `except ProviderError` clause uncaught, crashing the
            # whole request path instead of producing a clean failure
            # result, exactly the same normalization
            # `except ValueError` already gives `response.json()`
            # failures a few lines above.
            raise ProviderUnavailableError(
                "Gemini speech request succeeded but its audio data could not be decoded."
            ) from exc
        audio = GeneratedAudio(data_base64=wav_data_base64, mime_type="audio/wav")
        return SpeechGenerationResult(
            audio=audio, model=str(self._audio_model), latency_ms=latency_ms
        )

    @staticmethod
    def _extract_audio(data: dict[str, Any]) -> tuple[str, str] | None:
        """Extract the first `inlineData` audio part of a generateContent response.

        Returns (data_base64, mime_type), or None if no usable audio
        part is present. Mirrors `_extract_images()`'s structure,
        returning a single optional pair rather than a list -- the
        Gemini TTS response in scope for EP-084 carries exactly one
        audio part per candidate (`EP084_DESIGN.md` Section 11).
        """
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            return None
        for part in parts:
            if not isinstance(part, dict):
                continue
            inline_data = part.get("inlineData")
            if not isinstance(inline_data, dict):
                continue
            encoded = inline_data.get("data")
            mime_type = inline_data.get("mimeType")
            if isinstance(encoded, str) and isinstance(mime_type, str) and encoded:
                return encoded, mime_type
        return None

    @staticmethod
    def _pcm_to_wav(pcm_data_base64: str, source_mime_type: str) -> str:
        """Wrap base64-encoded raw PCM audio into a base64-encoded WAV container (EP-084).

        Implements Owner Decision D2 (`EP084_DESIGN.md` Section 9/25):
        Gemini's TTS response is raw, headerless 16-bit linear PCM
        (mono) -- not directly playable -- so it is wrapped into a
        valid WAV container here, using only Python's standard-library
        `wave` module (no new dependency), before ever reaching a
        caller. Sample rate is parsed from `source_mime_type` (e.g.
        "audio/L16;codec=pcm;rate=24000"); sample width (16-bit) and
        channel count (mono) are fixed constants, per Google's current,
        documented TTS output format -- never guessed from the mime
        type. If the rate cannot be parsed (an unexpected/future
        `mimeType` shape), `_PCM_DEFAULT_SAMPLE_RATE_HZ` (Gemini's own
        current default) is used rather than discarding an otherwise-
        successful response.

        Args:
            pcm_data_base64: The raw PCM audio, base64-encoded, exactly
                as Gemini returned it.
            source_mime_type: The raw `mimeType` Gemini reported for
                `pcm_data_base64` (used only to parse the sample rate).

        Returns:
            The resulting WAV file's bytes, base64-encoded.
        """
        pcm_bytes = b64decode(pcm_data_base64)
        rate_match = _PCM_RATE_PATTERN.search(source_mime_type)
        sample_rate = int(rate_match.group(1)) if rate_match else _PCM_DEFAULT_SAMPLE_RATE_HZ

        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(_PCM_CHANNELS)
            wav_file.setsampwidth(_PCM_SAMPLE_WIDTH_BYTES)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)

        return b64encode(buffer.getvalue()).decode("ascii")

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        """Best-effort extraction of a Gemini API error message, or the raw body text."""
        try:
            data = response.json()
        except ValueError:
            return response.text
        error = data.get("error", {})
        if isinstance(error, dict) and "message" in error:
            return str(error["message"])
        return response.text
