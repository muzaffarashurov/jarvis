"""Gemini Provider (EP-015.1 / EP-015.2): real Google Gemini API integration.

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

EP-015.2 scope note: `ai use <provider>` runs entirely through
ProviderManager.set_current(), which only checks the name is
registered and never calls back into the provider. This task forbids
modifying ProviderManager/AIService, so `ai use gemini` cannot itself
trigger a live check here. `validate_configured_model()` implements
that check, self-contained and ready to wire in -- see its TODO.
Until wired, the same diagnostic surfaces on the next
`ask()`/`ping()`/`ai test` against an invalid model.
"""

from __future__ import annotations

import difflib
import time
from dataclasses import dataclass
from typing import Any

import requests
from loguru import logger

from src.core.ai.provider import (
    AIProvider,
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
)

__all__ = ["GeminiProvider", "ModelValidationResult"]

_API_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/models"
_PROVIDER_NAME: str = "gemini"
_GENERATE_CONTENT_METHOD: str = "generateContent"
_MODEL_NAME_PREFIX: str = "models/"


@dataclass(frozen=True)
class ModelValidationResult:
    """Result of `GeminiProvider.validate_configured_model()` (EP-015.2).

    Attributes:
        valid: Whether 'providers.gemini.model' is in the live
            ListModels result for this API key.
        configured_model: The model set in 'providers.gemini.model'.
        available_models: Every model this key can call
            `generateContent` on, per ModelService.ListModels.
        suggested_model: Closest available match by name (or None).
        message: Human-readable summary.
    """

    valid: bool
    configured_model: str
    available_models: tuple[str, ...]
    suggested_model: str | None
    message: str


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
        """
        self._enabled = enabled
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._temperature = temperature

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

    def ask(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        """Send `prompt` to the Google Gemini API and return its reply.

        Args:
            prompt: The user prompt to send.
            max_tokens: Optional override for the reply's maximum
                token count. None uses 'providers.gemini.max_tokens'.

        Returns:
            The provider's reply. Errors are mapped to ProviderError
            subtypes by `_send_request()`, `_raise_for_transport_status()`
            and `_build_model_not_found_error()`.
        """
        if not self._enabled:
            raise ProviderConfigurationError("Provider 'gemini' is disabled.")
        if not self._api_key.strip():
            raise ProviderConfigurationError("Provider 'gemini' is missing 'api_key'.")

        url = f"{_API_BASE_URL}/{self._model}:generateContent"
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens if max_tokens is not None else self._max_tokens,
                "temperature": self._temperature,
            },
        }
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

    def ping(self) -> PingResult:
        """Check reachability, latency, model and authentication for this provider."""
        if not self.is_available():
            return PingResult(
                reachable=False,
                latency_ms=0.0,
                model=self._model,
                authenticated=False,
                message=self.health().message,
            )

        started = time.monotonic()
        try:
            response = self.ask("ping", max_tokens=1)
        except ProviderAuthenticationError as exc:
            return self._ping_result(started, reachable=True, authenticated=False, message=str(exc))
        except ProviderRateLimitError as exc:
            return self._ping_result(started, reachable=True, authenticated=True, message=str(exc))
        except ProviderError as exc:
            return self._ping_result(started, reachable=False, authenticated=False, message=str(exc))

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

        The model-existence check requested for `ai use gemini`,
        implemented self-contained so it is ready to be wired in.

        TODO: ProviderManager.set_current() only checks the name is
        registered and never calls back into the provider; wiring
        this into `ai use gemini` needs one call in
        AIService.use_provider() after set_current() succeeds -- out
        of this task's allowed scope, so not yet called automatically.
        Until then, the same diagnostic surfaces on the next
        `ask()`/`ping()`/`ai test` via `_build_model_not_found_error()`.

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
