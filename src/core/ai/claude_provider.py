"""Claude Provider (EP-015): real Anthropic Claude API integration.

ClaudeProvider is the first concrete AIProvider (EP-014) that talks to
a real AI API over HTTPS. It reuses the existing `requests` dependency
(see requirements.txt) exactly like TelegramClient reuses
`python-telegram-bot` (see src/core/telegram/telegram_client.py) --
no new third-party dependency is introduced.

Responsibilities:
    - Report identity/status/configuration/health from
      'providers.claude.*' configuration only (no network access),
      per EP-014's contract.
    - Implement `ask()`, `ping()` and `list_models()` (EP-015's
      extension points on AIProvider) by calling the official
      Anthropic Messages API (https://api.anthropic.com/v1/messages).
    - Translate every failure mode (timeout, authentication, network,
      rate limit, invalid configuration, provider unavailable) into
      the shared ProviderError hierarchy defined in
      src/core/ai/provider.py.
    - Never log or return the raw API key.

This class owns no provider selection, no CLI formatting, and no
conversation history (EP-015: "each request is independent" -- memory
integration is left to a future EP).
"""

from __future__ import annotations

import time
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

__all__ = ["ClaudeProvider"]

_API_URL: str = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_VERSION: str = "2023-06-01"
_PROVIDER_NAME: str = "claude"


class ClaudeProvider(AIProvider):
    """AIProvider implementation backed by the official Anthropic Claude API."""

    def __init__(
        self,
        enabled: bool,
        api_key: str,
        model: str,
        timeout: int,
        max_tokens: int,
        temperature: float,
    ) -> None:
        """Initialize the ClaudeProvider.

        Args:
            enabled: Value of 'providers.claude.enabled'.
            api_key: Value of 'providers.claude.api_key'. Never logged
                or returned; used only as the outgoing 'x-api-key'
                header.
            model: Value of 'providers.claude.model' (e.g.
                "claude-sonnet-4").
            timeout: Value of 'providers.claude.timeout', in seconds.
            max_tokens: Value of 'providers.claude.max_tokens', the
                default reply size cap.
            temperature: Value of 'providers.claude.temperature'.
        """
        self._enabled = enabled
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._temperature = temperature

    # ---------- AIProvider: identity / configuration / health ----------

    def name(self) -> str:
        """Return this provider's stable identifier: "claude"."""
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
            return ProviderHealth(available=False, message="Provider 'claude' is disabled.")
        if not self._api_key.strip():
            return ProviderHealth(
                available=False, message="Provider 'claude' is missing 'api_key'."
            )
        return ProviderHealth(available=True, message="Provider 'claude' is configured.")

    # ---------- AIProvider: EP-015 real communication ----------

    def ask(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        """Send `prompt` to the Anthropic Messages API and return its reply.

        Args:
            prompt: The user prompt to send.
            max_tokens: Optional override for the reply's maximum
                token count. None uses 'providers.claude.max_tokens'.

        Returns:
            The provider's reply.

        Raises:
            ProviderConfigurationError: If this provider is disabled
                or missing its API key.
            ProviderAuthenticationError: If the API key is rejected.
            ProviderRateLimitError: If the API reports a rate limit.
            ProviderTimeoutError: If the request exceeds the
                configured timeout.
            ProviderNetworkError: If the request cannot reach the API.
            ProviderUnavailableError: If the API is unreachable or
                returns an unexpected error.
        """
        if not self._enabled:
            raise ProviderConfigurationError("Provider 'claude' is disabled.")
        if not self._api_key.strip():
            raise ProviderConfigurationError("Provider 'claude' is missing 'api_key'.")

        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens if max_tokens is not None else self._max_tokens,
            "temperature": self._temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        logger.info(f"AI request started (provider='claude', model='{self._model}').")
        started = time.monotonic()
        try:
            response = requests.post(
                _API_URL, headers=headers, json=payload, timeout=self._timeout
            )
        except requests.exceptions.Timeout as exc:
            logger.error(f"AI request timed out (provider='claude', timeout={self._timeout}s).")
            raise ProviderTimeoutError(
                f"Claude request timed out after {self._timeout}s."
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            logger.error(f"AI request network failure (provider='claude'): {exc}")
            raise ProviderNetworkError("Could not reach the Anthropic API.") from exc
        except requests.exceptions.RequestException as exc:
            logger.error(f"AI request failed (provider='claude'): {exc}")
            raise ProviderNetworkError(str(exc)) from exc

        latency_ms = (time.monotonic() - started) * 1000
        result = self._parse_response(response, latency_ms)
        logger.info(
            f"AI request finished (provider='claude', model='{result.model}', "
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
            return PingResult(
                reachable=True,
                latency_ms=(time.monotonic() - started) * 1000,
                model=self._model,
                authenticated=False,
                message=str(exc),
            )
        except ProviderRateLimitError as exc:
            return PingResult(
                reachable=True,
                latency_ms=(time.monotonic() - started) * 1000,
                model=self._model,
                authenticated=True,
                message=str(exc),
            )
        except ProviderError as exc:
            return PingResult(
                reachable=False,
                latency_ms=(time.monotonic() - started) * 1000,
                model=self._model,
                authenticated=False,
                message=str(exc),
            )

        return PingResult(
            reachable=True,
            latency_ms=response.latency_ms,
            model=response.model,
            authenticated=True,
            message="Provider reachable.",
        )

    def list_models(self) -> list[str]:
        """Return the Claude model configured in 'providers.claude.model'.

        Never performs online discovery (EP-015).
        """
        return [self._model]

    # ---------- Internal helpers ----------

    def _parse_response(self, response: requests.Response, latency_ms: float) -> ProviderResponse:
        """Translate a raw `requests.Response` into a ProviderResponse or error.

        Args:
            response: The raw HTTP response from the Messages API.
            latency_ms: Elapsed request time, in milliseconds.

        Returns:
            The parsed ProviderResponse, on success.

        Raises:
            ProviderAuthenticationError: On HTTP 401/403.
            ProviderRateLimitError: On HTTP 429.
            ProviderUnavailableError: On HTTP 5xx or an unexpected
                response body.
            ProviderError: On any other non-2xx status.
        """
        if response.status_code in (401, 403):
            raise ProviderAuthenticationError(
                "Claude rejected the configured API key. Check 'providers.claude.api_key'."
            )
        if response.status_code == 429:
            raise ProviderRateLimitError("Claude rate limit exceeded. Please retry later.")
        if response.status_code >= 500:
            raise ProviderUnavailableError(
                f"Claude API is currently unavailable (HTTP {response.status_code})."
            )
        if response.status_code != 200:
            message = self._extract_error_message(response)
            raise ProviderError(f"Claude request failed (HTTP {response.status_code}): {message}")

        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderUnavailableError("Claude returned an invalid response body.") from exc

        text = self._extract_text(data)
        model = str(data.get("model", self._model))
        return ProviderResponse(text=text, model=model, latency_ms=latency_ms)

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        """Extract and concatenate the text blocks of a Messages API response.

        Args:
            data: The parsed JSON body of a successful Messages API
                response.

        Returns:
            The concatenated text of every "text" content block.
        """
        blocks = data.get("content", [])
        if not isinstance(blocks, list):
            return ""
        parts = [
            str(block.get("text", ""))
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(parts).strip()

    @staticmethod
    def _extract_error_message(response: requests.Response) -> str:
        """Best-effort extraction of an Anthropic API error message.

        Args:
            response: The raw HTTP response.

        Returns:
            The API's own error message, or the raw response text if
            the body is not the expected JSON error shape.
        """
        try:
            data = response.json()
        except ValueError:
            return response.text
        error = data.get("error", {})
        if isinstance(error, dict) and "message" in error:
            return str(error["message"])
        return response.text
