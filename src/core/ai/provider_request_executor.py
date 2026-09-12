"""Shared provider-request execution for EP-082 Text Generation Provider Integration.

`ProviderRequestExecutor` extracts the fallback/retry loop that
`AIService.ask()` (EP-018) previously owned inline, so both `AIService`
and the new, standalone `TextGenerationService` (EP-082) can execute a
provider request with EP-069.1/.2/.3 fallback and cost-aware provider
ordering, without either component owning a second implementation of
that loop (`EP082_DESIGN.md` Section 6, 11.2 -- Rule 3/Rule 4: never
introduce a second implementation of existing functionality).

Responsibility boundaries (`EP082_DESIGN.md` Section 6, Owner Decision
1) are deliberately narrow and do not change `ProviderManager`:

    - `ProviderManager` remains the sole owner of provider
      registry/current-provider access, fallback candidate discovery,
      and cost-aware/fallback-order ordering (EP-069.1/.2/.3). Nothing
      in this module changes `ProviderManager`.
    - `ProviderRequestExecutor` (this module) owns only the mechanics
      of *executing* a request against a chosen provider and retrying
      eligible failures against `ProviderManager.list_fallback_
      candidates()`'s ordering -- it holds no provider state of its
      own and makes no selection decisions `ProviderManager` doesn't
      already make.
    - `AIService` continues to own conversation/context/prompt
      orchestration; it calls this executor instead of running its
      own inline loop, with its public method signature, `AskResult`
      contract, and all other observable behavior unchanged
      (`EP082_DESIGN.md` Section 19).
    - `TextGenerationService` (EP-082) calls this same executor
      directly, with no conversation/context/prompt involvement.

Fallback eligibility and ordering exactly reproduce EP-069.1/.2/.3's
existing, already-shipped semantics (`EP069_DESIGN.md`,
`EP069_2_DESIGN.md`, `EP069_3_DESIGN.md`): only
`ProviderUnavailableError`, `ProviderNetworkError`,
`ProviderTimeoutError`, and `ProviderRateLimitError` are fallback-
eligible; `ProviderConfigurationError`, `ProviderAuthenticationError`,
and the base `ProviderError` are not, and stop retrying immediately.
This set is intentionally closed here, exactly as it was in
`ai_service.py` before this extraction, and is not derived from
exception attributes or broadened.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.ai.provider import (
    AIProvider,
    ProviderError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderResponse,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from src.core.ai.provider_manager import ProviderManager

__all__ = ["ProviderRequestExecutor", "ProviderRequestOutcome"]

# Fallback-eligible ProviderError subtypes, unchanged from EP-069.1
# (`EP069_DESIGN.md` Section 15, Owner Decision D4) -- moved here
# verbatim as part of the EP-082 extraction. Only transient/
# provider-availability failures are eligible; a bad credential or
# missing configuration is an operator-visible defect, not a
# transient failure to silently route around.
_FALLBACK_ELIGIBLE_ERRORS: tuple[type[ProviderError], ...] = (
    ProviderUnavailableError,
    ProviderNetworkError,
    ProviderTimeoutError,
    ProviderRateLimitError,
)


@dataclass(frozen=True)
class ProviderRequestOutcome:
    """Result of `ProviderRequestExecutor.execute()` (EP-082).

    Deliberately provider-level only: no conversation, context, or
    prompt-related field is present, so both `AIService` (which adds
    its own conversation/context handling around this outcome) and
    `TextGenerationService` (which adds none) can build their own
    caller-specific result type from the same underlying execution.

    Attributes:
        success: Whether some provider in the attempt chain produced
            a response.
        initial_provider: Name of the provider `execute()` was asked
            to start with -- the explicitly selected/current provider
            for this request, regardless of whether fallback occurred.
        final_provider: Name of the provider that actually produced
            the response (may differ from `initial_provider` when
            fallback occurred), or "" on failure.
        response: The successful `ProviderResponse`, or None on
            failure.
        error: A user-friendly error message, or "" on success.
    """

    success: bool
    initial_provider: str
    final_provider: str
    response: ProviderResponse | None
    error: str


class ProviderRequestExecutor:
    """Executes a provider request with EP-069.1/.2/.3 fallback semantics.

    Holds no provider-selection state of its own: every call re-reads
    `ProviderManager.list_fallback_candidates()` fresh, exactly as
    `AIService.ask()` did before this extraction, so eligibility and
    ordering can never go stale relative to provider
    registration/removal.
    """

    def __init__(self, provider_manager: ProviderManager) -> None:
        """Initialize the ProviderRequestExecutor.

        Args:
            provider_manager: The ProviderManager used to discover
                fallback candidates when the initial provider fails.
                This executor never calls `get_current()` or
                `set_current()` on it -- the caller supplies the
                provider to start with (Section `execute()`), so a
                fallback occurring mid-request never changes which
                provider is "current" for the next fresh request
                (EP-069.1 Owner Decision D1, preserved unchanged).
        """
        self._provider_manager = provider_manager

    def execute(
        self,
        provider: AIProvider,
        prompt: str,
        *,
        fallback_enabled: bool,
        max_tokens: int | None = None,
        temperature: float | None = None,
        system_prompt: str | None = None,
    ) -> ProviderRequestOutcome:
        """Send `prompt` to `provider`, retrying eligible failures via fallback.

        Reproduces `AIService.ask()`'s pre-EP-082 retry loop exactly:
        attempt `provider`; on a fallback-eligible `ProviderError`,
        and only when `fallback_enabled` is True, retry the next
        candidate from `ProviderManager.list_fallback_candidates()`
        (excluding every provider already attempted) until one
        succeeds or every eligible candidate has been tried. A
        non-eligible failure, or `fallback_enabled=False`, fails
        immediately with zero fallback candidates queried -- byte-
        identical to pre-EP-069.1 behavior.

        `max_tokens`/`temperature`/`system_prompt` are only passed to
        `provider.ask()` when not None, so a caller that omits them
        (e.g. `AIService.ask()`, which has no per-request concept of
        either) calls `provider.ask(prompt)` exactly as before this
        extraction -- preserving compatibility with any `AIProvider`
        implementation (including test fakes) that does not yet
        accept the EP-082 `temperature`/`system_prompt` parameters.

        Args:
            provider: The provider to attempt first (the caller's
                "current"/explicitly selected provider for this
                request).
            prompt: The final, already-rendered prompt to send.
            fallback_enabled: Whether a fallback-eligible failure may
                be retried against another candidate. Independent per
                caller (`AIService` uses 'ai.fallback_enabled';
                `TextGenerationService` uses
                'content_generation.fallback_enabled').
            max_tokens: Optional override forwarded to `provider.ask()`
                only when not None.
            temperature: Optional override forwarded to
                `provider.ask()` only when not None (EP-082).
            system_prompt: Optional override forwarded to
                `provider.ask()` only when not None (EP-082).

        Returns:
            A ProviderRequestOutcome describing the final result.
        """
        candidate = provider
        initial_name = provider.name()
        attempted: list[str] = []
        failure_summary: list[str] = []

        extra_kwargs: dict[str, object] = {}
        if max_tokens is not None:
            extra_kwargs["max_tokens"] = max_tokens
        if temperature is not None:
            extra_kwargs["temperature"] = temperature
        if system_prompt is not None:
            extra_kwargs["system_prompt"] = system_prompt

        while True:
            candidate_name = candidate.name()
            attempted.append(candidate_name)
            try:
                response = candidate.ask(prompt, **extra_kwargs)
            except ProviderError as exc:
                # `exc` here is always a ProviderError instance whose
                # message is a static, code-authored string, never
                # user-supplied prompt content -- safe to log
                # verbatim, per EP069_DESIGN.md Section 9/11.
                logger.error(f"AI request failed (provider='{candidate_name}'): {exc}")
                failure_summary.append(f"{candidate_name}: {type(exc).__name__}")

                fallback_eligible = fallback_enabled and isinstance(
                    exc, _FALLBACK_ELIGIBLE_ERRORS
                )
                if not fallback_eligible:
                    return ProviderRequestOutcome(
                        success=False,
                        initial_provider=initial_name,
                        final_provider="",
                        response=None,
                        error=str(exc),
                    )

                remaining = self._provider_manager.list_fallback_candidates(exclude=attempted)
                if not remaining:
                    # Every eligible candidate has been tried (bounded
                    # by construction). Only provider names and
                    # exception class names are aggregated here, never
                    # `str(exc)`, per EP-068's log-redaction precedent.
                    logger.error(
                        "AI request failed on every eligible provider: "
                        f"{', '.join(failure_summary)}."
                    )
                    return ProviderRequestOutcome(
                        success=False,
                        initial_provider=initial_name,
                        final_provider="",
                        response=None,
                        error=f"All providers failed. {'; '.join(failure_summary)}.",
                    )

                next_candidate = remaining[0]
                logger.info(
                    f"AI request falling back from provider='{candidate_name}' "
                    f"to provider='{next_candidate.name()}'."
                )
                candidate = next_candidate
                continue

            return ProviderRequestOutcome(
                success=True,
                initial_provider=initial_name,
                final_provider=candidate.name(),
                response=response,
                error="",
            )
