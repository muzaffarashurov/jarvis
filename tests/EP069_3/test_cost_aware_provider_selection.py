"""Real engineering tests for EP-069.3 STEP 2 - Cost-Aware AI Provider Selection.

New, distinct test suite (`NAME = "EP069_3"`) rather than extending
`tests/EP069/test_ai_provider_fallback.py` -- resolving STEP 1's D7 in
favor of a separate package. This repository's `TestRegistry.register()`
keys suites by `NAME.upper()` (`src/testing/registry.py`), so reusing
`NAME = "EP069"` would silently overwrite EP-069.1's own registration
instead of adding to it; a distinct name is required, not merely
stylistic. Self-contained -- no import from `tests/EP069/`, matching
`tests/EP069/test_ai_provider_fallback.py`'s own precedent of not
importing from other `tests/EP0NN/` packages.

Per `EP069_3_DESIGN.md` Section 20 (and, now that EP-069.2 is
implemented, its actual composition per Section 14.1), covers:
    - `ai.cost_aware_enabled` absent/false -> existing alphabetical
      `list_fallback_candidates()` ordering is completely unchanged,
      regardless of any configured `relative_cost`.
    - `ai.cost_aware_enabled` true, every eligible candidate priced ->
      ascending `relative_cost` order; a lower-cost provider is always
      ordered before a higher-cost one, which remains fully eligible.
    - Equal `relative_cost` -> alphabetical tie-break.
    - Unknown-cost provider(s) -> ordered after every known-cost
      provider; multiple unknown-cost providers -> alphabetical among
      themselves.
    - Every invalid `relative_cost` case from EP069_3_DESIGN.md Section
      15/Constraint 2 (missing, bool, string, None/null, list, dict,
      negative, NaN, +/-Infinity) is treated as unknown cost, never
      excludes the provider, and never crashes -- validated via
      `bootstrap.py`'s real `_parse_relative_cost()`/
      `_parse_provider_relative_costs()`.
    - Invalid `ai.cost_aware_enabled` type -> treated as False, one
      WARNING, no crash -- validated via `bootstrap.py`'s real
      `_parse_cost_aware_enabled()`.
    - Availability filtering and the `exclude` set are unaffected by
      cost-aware ordering (eligibility is unchanged; only order is).
    - The primary/current provider (`get_current()`/`set_current()`)
      is never influenced by `cost_aware_enabled`/`relative_cost`.
    - Deterministic, repeated-call-stable ordering.
    - A cost-aware-selected fallback candidate that itself fails ->
      the existing, unmodified EP-069.1 `AIService.ask()` loop
      continues to the next candidate exactly as before.
    - Bootstrap wiring: `ai.cost_aware_enabled` and every
      `providers.<name>.relative_cost` are correctly parsed and
      threaded into `ProviderManager`'s constructor.
    - EP-069.2 (`fallback_order`) composition (EP069_3_DESIGN.md
      Section 14.1, now implemented rather than merely forward-
      declared): an explicit `fallback_order` always takes priority,
      in its own configured sequence, for the names it lists; cost
      only orders whichever eligible candidates `fallback_order`
      leaves unresolved; `ai.fallback_order` itself is never
      reimplemented or duplicated here -- this suite only exercises
      the single, shared `list_fallback_candidates()` implementation
      in `src/core/ai/provider_manager.py`.
    - Backward compatibility: `AIProvider`, `ProviderResponse`,
      `AIService`, `ProviderRegistry`, and every concrete provider
      remain unaffected.
"""

from __future__ import annotations

import math

from loguru import logger

from src.bootstrap import (
    _parse_cost_aware_enabled,
    _parse_provider_relative_costs,
    _parse_relative_cost,
)
from src.core.ai.provider import (
    AIProvider,
    ProviderHealth,
    ProviderResponse,
    ProviderStatus,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from src.core.ai.provider_manager import ProviderManager, _is_valid_relative_cost
from src.core.ai.provider_registry import ProviderRegistry
from src.services.ai_service import AIService
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


# ---------- Fakes ----------


class _FakeAIProvider(AIProvider):
    """Deterministic, test-only concrete `AIProvider` (EP-069.3).

    Mirrors `tests/EP069/test_ai_provider_fallback.py`'s own
    `_FakeAIProvider` in shape, duplicated here rather than imported
    so this package stays self-contained.
    """

    def __init__(
        self,
        name: str,
        *,
        available: bool = True,
        response_text: str = "ok",
        raise_error: Exception | None = None,
    ) -> None:
        self._name = name
        self._available = available
        self._response_text = response_text
        self._raise_error = raise_error
        self.ask_calls: list[str] = []

    def name(self) -> str:
        return self._name

    def status(self) -> ProviderStatus:
        return ProviderStatus.AVAILABLE if self._available else ProviderStatus.NOT_CONFIGURED

    def is_available(self) -> bool:
        return self._available

    def configuration(self) -> dict:
        return {"enabled": self._available, "configured": self._available}

    def health(self) -> ProviderHealth:
        return ProviderHealth(available=self._available, message="")

    def ask(self, prompt: str, max_tokens: int | None = None) -> ProviderResponse:
        self.ask_calls.append(prompt)
        if self._raise_error is not None:
            raise self._raise_error
        return ProviderResponse(text=self._response_text, model=f"{self._name}-model", latency_ms=1.0)


class _FakeConfig:
    """Deterministic, test-only stand-in for `Config`.

    Only implements `.get()` -- the only method `bootstrap.py`'s
    `_parse_cost_aware_enabled()`/`_parse_relative_cost()`/
    `_parse_provider_relative_costs()` call.
    """

    def __init__(self, values: dict | None = None) -> None:
        self._values = values if values is not None else {}

    def get(self, key: str, default=None):
        return self._values.get(key, default)


class _FakeContext:
    rendered: str = ""


class _FakeContextManager:
    def create(self, conversation, query: str):
        return _FakeContext()


class _FakeBuiltPrompt:
    def __init__(self, rendered: str) -> None:
        self.rendered = rendered


class _FakePromptManager:
    def build(self, *, user_prompt: str, context, provider_name: str) -> _FakeBuiltPrompt:
        return _FakeBuiltPrompt(rendered=f"RENDERED::{user_prompt}")


class _FakeAppConfig:
    """Deterministic, test-only stand-in for `Config`, as used by `AIService`."""

    def __init__(self, values: dict | None = None) -> None:
        self._values = values if values is not None else {"conversation.enabled": False}

    def get(self, key: str, default=None):
        return self._values.get(key, default)


def _capture_logs():
    """Attach a fresh loguru sink capturing formatted messages.

    Mirrors `tests/EP069/test_ai_provider_fallback.py`'s own helper.
    """
    lines: list[str] = []
    sink_id = logger.add(lambda message: lines.append(message.record["message"]), level="DEBUG")
    return lines, sink_id


def _make_real_manager(
    *,
    providers: list[_FakeAIProvider],
    cost_aware_enabled: bool,
    relative_cost: dict[str, float] | None = None,
    fallback_order: list[str] | None = None,
    current: str | None = None,
) -> ProviderManager:
    registry = ProviderRegistry()
    for provider in providers:
        registry.register(provider)
    return ProviderManager(
        registry=registry,
        enabled=True,
        default_provider=current or "none",
        fallback_order=fallback_order,
        cost_aware_enabled=cost_aware_enabled,
        relative_cost=relative_cost,
    )


@TestRegistry.register
class CostAwareProviderSelectionTest(BaseTest):
    NAME = "EP069_3"

    def run(self):
        # ---------- ProviderManager.list_fallback_candidates() ordering ----------
        self._test_cost_aware_disabled_preserves_alphabetical_order()
        self._test_cost_aware_disabled_ignores_configured_relative_cost()
        self._test_cost_aware_enabled_orders_by_ascending_cost()
        self._test_lower_cost_provider_before_higher_cost_provider()
        self._test_higher_cost_provider_remains_eligible()
        self._test_equal_cost_tie_breaks_alphabetically()
        self._test_unknown_cost_provider_sorted_after_known_cost()
        self._test_multiple_unknown_cost_providers_alphabetical()
        self._test_missing_relative_cost_is_unknown_no_crash()

        # ---------- Availability / exclusion (unchanged eligibility) ----------
        self._test_availability_filtering_unchanged_under_cost_aware_ordering()
        self._test_excluded_providers_remain_excluded_under_cost_aware_ordering()

        # ---------- Primary/current provider isolation ----------
        self._test_primary_provider_unaffected_by_cost_configuration()

        # ---------- Determinism ----------
        self._test_repeated_calls_produce_identical_order()

        # ---------- EP-069.2 (fallback_order) composition ----------
        self._test_fallback_order_takes_priority_over_cost_for_listed_names()
        self._test_cost_orders_only_candidates_unlisted_by_fallback_order()
        self._test_fallback_order_present_but_cost_aware_disabled_unchanged_from_ep069_2()
        self._test_fallback_order_absent_cost_aware_enabled_orders_everyone_by_cost()
        self._test_unmatched_fallback_order_name_has_no_effect_alongside_cost()

        # ---------- AIService integration: fallback loop composition ----------
        self._test_fallback_loop_continues_after_cost_selected_candidate_fails()

        # ---------- bootstrap.py validation: ai.cost_aware_enabled ----------
        self._test_parse_cost_aware_enabled_absent_defaults_false_no_warning()
        self._test_parse_cost_aware_enabled_true()
        self._test_parse_cost_aware_enabled_invalid_type_warns_and_defaults_false()

        # ---------- bootstrap.py validation: providers.<name>.relative_cost ----------
        self._test_parse_relative_cost_missing_is_unknown_no_warning()
        self._test_parse_relative_cost_valid_int_and_float()
        self._test_parse_relative_cost_bool_is_invalid()
        self._test_parse_relative_cost_string_is_invalid()
        self._test_parse_relative_cost_none_is_invalid()
        self._test_parse_relative_cost_negative_is_invalid()
        self._test_parse_relative_cost_nan_is_invalid()
        self._test_parse_relative_cost_infinity_is_invalid()
        self._test_parse_relative_cost_warning_never_logs_raw_value()

        # ---------- bootstrap.py wiring ----------
        self._test_parse_provider_relative_costs_builds_expected_mapping()
        self._test_bootstrap_values_thread_into_provider_manager()

        # ---------- Backward compatibility ----------
        self._test_provider_manager_default_constructor_args_unchanged()

        # ---------- ProviderManager direct-construction sanitization (EP069.3-AUDIT-001 fix) ----------
        self._test_is_valid_relative_cost_predicate()
        self._test_provider_manager_sanitizes_bool_relative_cost_on_direct_construction()
        self._test_provider_manager_sanitizes_nan_and_infinity_on_direct_construction()
        self._test_provider_manager_sanitizes_negative_and_non_numeric_on_direct_construction()
        self._test_provider_manager_accepts_zero_and_positive_on_direct_construction()
        self._test_provider_manager_sanitization_does_not_affect_primary_provider()

        return self.result

    # ---------- ProviderManager.list_fallback_candidates() ordering ----------

    def _test_cost_aware_disabled_preserves_alphabetical_order(self) -> None:
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("openai"),
                _FakeAIProvider("claude"),
                _FakeAIProvider("gemini"),
            ],
            cost_aware_enabled=False,
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude", "gemini", "openai"],
            "cost_aware_enabled=False must preserve EP-069.1's alphabetical order.",
        )

    def _test_cost_aware_disabled_ignores_configured_relative_cost(self) -> None:
        manager = _make_real_manager(
            providers=[_FakeAIProvider("claude"), _FakeAIProvider("gemini")],
            cost_aware_enabled=False,
            relative_cost={"claude": 0.1, "gemini": 99.0},
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude", "gemini"],
            "A configured relative_cost must have zero effect while cost_aware_enabled is False.",
        )

    def _test_cost_aware_enabled_orders_by_ascending_cost(self) -> None:
        manager = _make_real_manager(
            providers=[_FakeAIProvider("claude"), _FakeAIProvider("gemini")],
            cost_aware_enabled=True,
            relative_cost={"claude": 3.0, "gemini": 0.5},
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["gemini", "claude"],
            "cost_aware_enabled=True must order candidates by ascending relative_cost.",
        )

    def _test_lower_cost_provider_before_higher_cost_provider(self) -> None:
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("claude"),
                _FakeAIProvider("gemini"),
                _FakeAIProvider("openai"),
            ],
            cost_aware_enabled=True,
            relative_cost={"claude": 3.0, "gemini": 0.5, "openai": 1.5},
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["gemini", "openai", "claude"],
            "Each provider must be ordered strictly by ascending configured relative_cost.",
        )

    def _test_higher_cost_provider_remains_eligible(self) -> None:
        manager = _make_real_manager(
            providers=[_FakeAIProvider("claude"), _FakeAIProvider("gemini")],
            cost_aware_enabled=True,
            relative_cost={"claude": 3.0, "gemini": 0.5},
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(len(candidates), 2, "A higher-cost provider must remain a candidate, never excluded.")
        self.assert_true(
            "claude" in [p.name() for p in candidates],
            "The higher-cost provider ('claude') must still be present in the result.",
        )

    def _test_equal_cost_tie_breaks_alphabetically(self) -> None:
        manager = _make_real_manager(
            providers=[_FakeAIProvider("gemini"), _FakeAIProvider("claude")],
            cost_aware_enabled=True,
            relative_cost={"claude": 1.0, "gemini": 1.0},
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude", "gemini"],
            "Equal relative_cost must tie-break alphabetically by name().",
        )

    def _test_unknown_cost_provider_sorted_after_known_cost(self) -> None:
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("claude"),
                _FakeAIProvider("gemini"),
                _FakeAIProvider("openai"),
            ],
            cost_aware_enabled=True,
            relative_cost={"claude": 3.0, "gemini": 0.5},  # "openai" intentionally unconfigured
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["gemini", "claude", "openai"],
            "An unpriced provider must be ordered after every priced provider, never excluded.",
        )

    def _test_multiple_unknown_cost_providers_alphabetical(self) -> None:
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("gemini"),
                _FakeAIProvider("claude"),
                _FakeAIProvider("openai"),
                _FakeAIProvider("ollama"),
            ],
            cost_aware_enabled=True,
            relative_cost={"gemini": 0.5},  # claude, openai, ollama all unpriced
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["gemini", "claude", "ollama", "openai"],
            "Multiple unpriced providers must be ordered alphabetically among themselves, after the priced one.",
        )

    def _test_missing_relative_cost_is_unknown_no_crash(self) -> None:
        manager = _make_real_manager(
            providers=[_FakeAIProvider("claude")],
            cost_aware_enabled=True,
            relative_cost=None,
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude"],
            "A completely absent relative_cost mapping must not crash and must not exclude any provider.",
        )

    # ---------- Availability / exclusion (unchanged eligibility) ----------

    def _test_availability_filtering_unchanged_under_cost_aware_ordering(self) -> None:
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("claude", available=True),
                _FakeAIProvider("gemini", available=False),
            ],
            cost_aware_enabled=True,
            relative_cost={"claude": 3.0, "gemini": 0.1},
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude"],
            "An unavailable provider must be excluded regardless of how favorable its configured cost is.",
        )

    def _test_excluded_providers_remain_excluded_under_cost_aware_ordering(self) -> None:
        manager = _make_real_manager(
            providers=[_FakeAIProvider("claude"), _FakeAIProvider("gemini")],
            cost_aware_enabled=True,
            relative_cost={"claude": 3.0, "gemini": 0.1},
        )

        candidates = manager.list_fallback_candidates(exclude=["gemini"])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude"],
            "An already-attempted (excluded) provider must remain excluded regardless of its cost.",
        )

    # ---------- Primary/current provider isolation ----------

    def _test_primary_provider_unaffected_by_cost_configuration(self) -> None:
        registry = ProviderRegistry()
        claude = _FakeAIProvider("claude")
        gemini = _FakeAIProvider("gemini")
        registry.register(claude)
        registry.register(gemini)
        manager = ProviderManager(
            registry=registry,
            enabled=True,
            default_provider="claude",
            cost_aware_enabled=True,
            relative_cost={"claude": 99.0, "gemini": 0.01},
        )

        current = manager.get_current()

        self.assert_true(current is not None, "The configured default_provider must still be selected.")
        self.assert_equal(
            current.name(),
            "claude",
            "The primary/current provider must be determined solely by default_provider/set_current(), "
            "never by relative_cost -- even when claude is configured as far more expensive than gemini.",
        )
        manager.set_current("gemini")
        self.assert_equal(
            manager.get_current().name(),
            "gemini",
            "set_current() must remain the only way to change the primary provider.",
        )

    # ---------- Determinism ----------

    def _test_repeated_calls_produce_identical_order(self) -> None:
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("claude"),
                _FakeAIProvider("gemini"),
                _FakeAIProvider("openai"),
            ],
            cost_aware_enabled=True,
            relative_cost={"claude": 3.0, "gemini": 0.5},
        )

        first = [p.name() for p in manager.list_fallback_candidates(exclude=[])]
        second = [p.name() for p in manager.list_fallback_candidates(exclude=[])]
        third = [p.name() for p in manager.list_fallback_candidates(exclude=[])]

        self.assert_equal(first, second, "Repeated calls with identical state must produce identical order.")
        self.assert_equal(second, third, "Repeated calls with identical state must produce identical order.")

    # ---------- EP-069.2 (fallback_order) composition ----------

    def _test_fallback_order_takes_priority_over_cost_for_listed_names(self) -> None:
        # openai is by far the cheapest, but fallback_order explicitly
        # names claude first -- the explicit operator preference must
        # win for claude's own position. gemini and openai are both
        # unlisted, so between themselves they are still cost-ordered
        # (openai is cheaper than gemini) -- this test isolates
        # "does fallback_order override cost for a name it lists",
        # not the unlisted-remainder ordering (covered separately
        # below).
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("claude"),
                _FakeAIProvider("gemini"),
                _FakeAIProvider("openai"),
            ],
            cost_aware_enabled=True,
            relative_cost={"claude": 3.0, "gemini": 2.0, "openai": 0.01},
            fallback_order=["claude"],
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude", "openai", "gemini"],
            "fallback_order must take priority over relative_cost for any name it explicitly lists; "
            "the unlisted remainder (openai, gemini) is still ordered by ascending relative_cost.",
        )

    def _test_cost_orders_only_candidates_unlisted_by_fallback_order(self) -> None:
        # claude is pinned first by fallback_order; gemini and openai
        # are NOT listed, so they must be ordered by relative_cost
        # between themselves, not alphabetically.
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("claude"),
                _FakeAIProvider("gemini"),
                _FakeAIProvider("openai"),
            ],
            cost_aware_enabled=True,
            relative_cost={"gemini": 5.0, "openai": 0.1},
            fallback_order=["claude"],
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude", "openai", "gemini"],
            "Candidates left unresolved by fallback_order must be ordered by ascending relative_cost.",
        )

    def _test_fallback_order_present_but_cost_aware_disabled_unchanged_from_ep069_2(self) -> None:
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("claude"),
                _FakeAIProvider("gemini"),
                _FakeAIProvider("openai"),
            ],
            cost_aware_enabled=False,
            relative_cost={"gemini": 0.01, "openai": 0.02},
            fallback_order=["openai"],
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["openai", "claude", "gemini"],
            "With cost_aware_enabled=False, behavior must be byte-for-byte identical to EP-069.2 alone: "
            "fallback_order first, then the remainder alphabetically -- relative_cost must have zero effect.",
        )

    def _test_fallback_order_absent_cost_aware_enabled_orders_everyone_by_cost(self) -> None:
        # No fallback_order configured (EP-069.2's own default, []) --
        # cost-aware ordering must apply to every eligible candidate,
        # exactly as it did before EP-069.2 was implemented.
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("claude"),
                _FakeAIProvider("gemini"),
                _FakeAIProvider("openai"),
            ],
            cost_aware_enabled=True,
            relative_cost={"claude": 3.0, "gemini": 0.5, "openai": 1.5},
            fallback_order=None,
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["gemini", "openai", "claude"],
            "With fallback_order absent, cost-aware ordering must apply to every eligible candidate.",
        )

    def _test_unmatched_fallback_order_name_has_no_effect_alongside_cost(self) -> None:
        # "azure" is not a registered provider; it must be silently
        # ignored (EP-069.2's own rule), and cost-aware ordering must
        # still apply normally to every real, eligible candidate.
        manager = _make_real_manager(
            providers=[_FakeAIProvider("claude"), _FakeAIProvider("gemini")],
            cost_aware_enabled=True,
            relative_cost={"claude": 3.0, "gemini": 0.5},
            fallback_order=["azure"],
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["gemini", "claude"],
            "An unmatched fallback_order name must be ignored, never fabricated, never an error, "
            "and must not disable cost-aware ordering for the real eligible candidates.",
        )

    # ---------- AIService integration: fallback loop composition ----------

    def _test_fallback_loop_continues_after_cost_selected_candidate_fails(self) -> None:
        # gemini is cheapest and tried first (cost-aware), but fails;
        # the existing, unmodified EP-069.1 loop must continue to the
        # next remaining candidate (openai) and succeed there.
        claude = _FakeAIProvider("claude", raise_error=ProviderUnavailableError("claude down"))
        gemini = _FakeAIProvider("gemini", raise_error=ProviderTimeoutError("gemini timed out"))
        openai = _FakeAIProvider("openai", response_text="cheapest-that-works")

        registry = ProviderRegistry()
        for provider in (claude, gemini, openai):
            registry.register(provider)
        provider_manager = ProviderManager(
            registry=registry,
            enabled=True,
            default_provider="claude",
            cost_aware_enabled=True,
            relative_cost={"gemini": 0.1, "openai": 0.2},  # claude unpriced -> tried last among fallbacks
        )
        service = AIService(
            config=_FakeAppConfig(),
            provider_manager=provider_manager,
            conversation_manager=None,
            prompt_manager=_FakePromptManager(),
            context_manager=_FakeContextManager(),
            fallback_enabled=True,
        )

        result = service.ask("hello")

        self.assert_true(
            result.success,
            "The fallback loop must continue past a failing, cost-preferred candidate to the next eligible one.",
        )
        self.assert_equal(result.provider, "openai", "AskResult must name whichever candidate actually succeeded.")
        self.assert_equal(len(claude.ask_calls), 1, "The primary (claude) must be attempted exactly once.")
        self.assert_equal(len(gemini.ask_calls), 1, "The cheapest fallback (gemini) must be attempted exactly once.")
        self.assert_equal(len(openai.ask_calls), 1, "The next candidate (openai) must be attempted exactly once.")

    # ---------- bootstrap.py validation: ai.cost_aware_enabled ----------

    def _test_parse_cost_aware_enabled_absent_defaults_false_no_warning(self) -> None:
        lines, sink_id = _capture_logs()
        try:
            value = _parse_cost_aware_enabled(_FakeConfig({}))
        finally:
            logger.remove(sink_id)

        self.assert_false(value, "Absent 'ai.cost_aware_enabled' must default to False.")
        self.assert_equal(len(lines), 0, "An absent 'ai.cost_aware_enabled' must never emit a warning.")

    def _test_parse_cost_aware_enabled_true(self) -> None:
        value = _parse_cost_aware_enabled(_FakeConfig({"ai.cost_aware_enabled": True}))
        self.assert_true(value, "An explicit True 'ai.cost_aware_enabled' must be honored.")

    def _test_parse_cost_aware_enabled_invalid_type_warns_and_defaults_false(self) -> None:
        lines, sink_id = _capture_logs()
        try:
            value = _parse_cost_aware_enabled(_FakeConfig({"ai.cost_aware_enabled": "yes"}))
        finally:
            logger.remove(sink_id)

        self.assert_false(value, "A non-boolean 'ai.cost_aware_enabled' must be treated as False.")
        matching = [line for line in lines if "ai.cost_aware_enabled" in line]
        self.assert_equal(len(matching), 1, "Exactly one WARNING must be emitted for an invalid type.")
        self.assert_true("str" in matching[0], "The warning must name the observed type.")
        self.assert_false("yes" in matching[0], "The warning must never echo the raw malformed value.")

    # ---------- bootstrap.py validation: providers.<name>.relative_cost ----------

    def _test_parse_relative_cost_missing_is_unknown_no_warning(self) -> None:
        lines, sink_id = _capture_logs()
        try:
            value = _parse_relative_cost(_FakeConfig({}), "claude")
        finally:
            logger.remove(sink_id)

        self.assert_true(value is None, "A missing relative_cost must resolve to None (unknown cost).")
        self.assert_equal(len(lines), 0, "A missing relative_cost must never emit a warning.")

    def _test_parse_relative_cost_valid_int_and_float(self) -> None:
        int_value = _parse_relative_cost(_FakeConfig({"providers.claude.relative_cost": 3}), "claude")
        float_value = _parse_relative_cost(_FakeConfig({"providers.claude.relative_cost": 0.5}), "claude")
        zero_value = _parse_relative_cost(_FakeConfig({"providers.claude.relative_cost": 0}), "claude")

        self.assert_equal(int_value, 3.0, "A valid int relative_cost must be accepted (as a float).")
        self.assert_equal(float_value, 0.5, "A valid float relative_cost must be accepted.")
        self.assert_equal(zero_value, 0.0, "Zero is a valid (>= 0) relative_cost.")

    def _test_parse_relative_cost_bool_is_invalid(self) -> None:
        lines, sink_id = _capture_logs()
        try:
            true_value = _parse_relative_cost(_FakeConfig({"providers.claude.relative_cost": True}), "claude")
        finally:
            logger.remove(sink_id)
        self.assert_true(true_value is None, "A bool (even though bool is a subclass of int) must be rejected.")
        self.assert_true(
            len([line for line in lines if "providers.claude.relative_cost" in line]) == 1,
            "A bool relative_cost must emit exactly one WARNING.",
        )

        false_value = _parse_relative_cost(_FakeConfig({"providers.claude.relative_cost": False}), "claude")
        self.assert_true(false_value is None, "False must also be rejected as a relative_cost, not treated as 0.")

    def _test_parse_relative_cost_string_is_invalid(self) -> None:
        lines, sink_id = _capture_logs()
        try:
            value = _parse_relative_cost(_FakeConfig({"providers.claude.relative_cost": "3.0"}), "claude")
        finally:
            logger.remove(sink_id)

        self.assert_true(value is None, "A string relative_cost must not be silently converted to a number.")
        matching = [line for line in lines if "providers.claude.relative_cost" in line]
        self.assert_equal(len(matching), 1, "A string relative_cost must emit exactly one WARNING.")
        self.assert_false("3.0" in matching[0], "The warning must never echo the raw malformed value.")

    def _test_parse_relative_cost_none_is_invalid(self) -> None:
        lines, sink_id = _capture_logs()
        try:
            value = _parse_relative_cost(_FakeConfig({"providers.claude.relative_cost": None}), "claude")
        finally:
            logger.remove(sink_id)

        self.assert_true(value is None, "An explicit null relative_cost must resolve to unknown cost.")
        self.assert_equal(
            len([line for line in lines if "providers.claude.relative_cost" in line]),
            1,
            "An explicit null (distinct from an absent key) must emit exactly one WARNING.",
        )

    def _test_parse_relative_cost_negative_is_invalid(self) -> None:
        lines, sink_id = _capture_logs()
        try:
            value = _parse_relative_cost(_FakeConfig({"providers.claude.relative_cost": -1.0}), "claude")
        finally:
            logger.remove(sink_id)

        self.assert_true(value is None, "A negative relative_cost must be rejected.")
        self.assert_equal(
            len([line for line in lines if "providers.claude.relative_cost" in line]),
            1,
            "A negative relative_cost must emit exactly one WARNING.",
        )

    def _test_parse_relative_cost_nan_is_invalid(self) -> None:
        lines, sink_id = _capture_logs()
        try:
            value = _parse_relative_cost(_FakeConfig({"providers.claude.relative_cost": math.nan}), "claude")
        finally:
            logger.remove(sink_id)

        self.assert_true(value is None, "NaN must be rejected as non-finite.")
        self.assert_equal(
            len([line for line in lines if "providers.claude.relative_cost" in line]),
            1,
            "NaN must emit exactly one WARNING.",
        )

    def _test_parse_relative_cost_infinity_is_invalid(self) -> None:
        lines, sink_id = _capture_logs()
        try:
            positive = _parse_relative_cost(_FakeConfig({"providers.claude.relative_cost": math.inf}), "claude")
            negative = _parse_relative_cost(_FakeConfig({"providers.claude.relative_cost": -math.inf}), "claude")
        finally:
            logger.remove(sink_id)

        self.assert_true(positive is None, "Positive Infinity must be rejected as non-finite.")
        self.assert_true(negative is None, "Negative Infinity must be rejected (also non-finite and negative).")

    def _test_parse_relative_cost_warning_never_logs_raw_value(self) -> None:
        secret_looking_value = "SECRET-LOOKING-VALUE-4f9c"
        lines, sink_id = _capture_logs()
        try:
            _parse_relative_cost(
                _FakeConfig({"providers.claude.relative_cost": secret_looking_value}), "claude"
            )
        finally:
            logger.remove(sink_id)

        for line in lines:
            self.assert_false(
                secret_looking_value in line,
                "A relative_cost validation warning must never echo the raw configured value.",
            )

    # ---------- bootstrap.py wiring ----------

    def _test_parse_provider_relative_costs_builds_expected_mapping(self) -> None:
        config = _FakeConfig(
            {
                "providers.claude.relative_cost": 3.0,
                "providers.gemini.relative_cost": 0.5,
                "providers.openai.relative_cost": "invalid",
                # ollama, lmstudio: absent entirely
            }
        )

        result = _parse_provider_relative_costs(config)

        self.assert_equal(
            result,
            {"claude": 3.0, "gemini": 0.5},
            "Only providers with a present and valid relative_cost must appear in the resulting mapping.",
        )

    def _test_bootstrap_values_thread_into_provider_manager(self) -> None:
        config = _FakeConfig(
            {
                "ai.cost_aware_enabled": True,
                "providers.claude.relative_cost": 3.0,
                "providers.gemini.relative_cost": 0.5,
            }
        )
        cost_aware_enabled = _parse_cost_aware_enabled(config)
        relative_cost = _parse_provider_relative_costs(config)

        registry = ProviderRegistry()
        registry.register(_FakeAIProvider("claude"))
        registry.register(_FakeAIProvider("gemini"))
        manager = ProviderManager(
            registry=registry,
            enabled=True,
            default_provider="none",
            cost_aware_enabled=cost_aware_enabled,
            relative_cost=relative_cost,
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["gemini", "claude"],
            "Values parsed by bootstrap.py's real validation helpers must be correctly threaded into "
            "ProviderManager and take effect in list_fallback_candidates().",
        )

    # ---------- Backward compatibility ----------

    def _test_provider_manager_default_constructor_args_unchanged(self) -> None:
        # A caller that constructs ProviderManager exactly as EP-069.1
        # always did -- with no cost-aware arguments at all -- must get
        # byte-for-byte the same behavior as before EP-069.3 existed.
        registry = ProviderRegistry()
        registry.register(_FakeAIProvider("openai"))
        registry.register(_FakeAIProvider("claude"))
        registry.register(_FakeAIProvider("gemini"))
        manager = ProviderManager(registry=registry, enabled=True, default_provider="none")

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude", "gemini", "openai"],
            "Constructing ProviderManager without cost-aware arguments must preserve EP-069.1's exact behavior.",
        )

    # ---------- ProviderManager direct-construction sanitization (EP069.3-AUDIT-001 fix) ----------

    def _test_is_valid_relative_cost_predicate(self) -> None:
        # Exercises the exact predicate ProviderManager.__init__ uses
        # to sanitize relative_cost, independent of bootstrap.py --
        # this is the fix for EP069_3_ARCHITECTURE_AUDIT.md Finding
        # EP069.3-AUDIT-001 (ProviderManager did not independently
        # enforce this invariant when constructed directly).
        self.assert_false(_is_valid_relative_cost(True), "True must be rejected (bool is a subclass of int).")
        self.assert_false(_is_valid_relative_cost(False), "False must be rejected.")
        self.assert_false(_is_valid_relative_cost(None), "None must be rejected.")
        self.assert_false(_is_valid_relative_cost("3.0"), "A string must be rejected, never coerced.")
        self.assert_false(_is_valid_relative_cost([1, 2]), "A list must be rejected.")
        self.assert_false(_is_valid_relative_cost({"a": 1}), "A dict must be rejected.")
        self.assert_false(_is_valid_relative_cost(-1.0), "A negative value must be rejected.")
        self.assert_false(_is_valid_relative_cost(math.nan), "NaN must be rejected.")
        self.assert_false(_is_valid_relative_cost(math.inf), "Positive Infinity must be rejected.")
        self.assert_false(_is_valid_relative_cost(-math.inf), "Negative Infinity must be rejected.")
        self.assert_true(_is_valid_relative_cost(0), "Integer zero must be valid.")
        self.assert_true(_is_valid_relative_cost(0.0), "Float zero must be valid.")
        self.assert_true(_is_valid_relative_cost(3), "A positive int must be valid.")
        self.assert_true(_is_valid_relative_cost(3.5), "A positive float must be valid.")

    def _test_provider_manager_sanitizes_bool_relative_cost_on_direct_construction(self) -> None:
        # Directly constructs ProviderManager -- bypassing bootstrap.py
        # entirely -- with a bool relative_cost, proving the invariant
        # now holds at the ProviderManager boundary itself, not only
        # at the composition root.
        manager = _make_real_manager(
            providers=[_FakeAIProvider("claude"), _FakeAIProvider("gemini")],
            cost_aware_enabled=True,
            relative_cost={"claude": True, "gemini": 1.0},
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["gemini", "claude"],
            "A bool relative_cost, even from direct construction bypassing bootstrap.py, must be "
            "treated as unknown cost -- never as a valid (or zero/one) known cost.",
        )

    def _test_provider_manager_sanitizes_nan_and_infinity_on_direct_construction(self) -> None:
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("claude"),
                _FakeAIProvider("gemini"),
                _FakeAIProvider("openai"),
            ],
            cost_aware_enabled=True,
            relative_cost={"claude": math.nan, "gemini": math.inf, "openai": 2.0},
        )

        first = [p.name() for p in manager.list_fallback_candidates(exclude=[])]
        second = [p.name() for p in manager.list_fallback_candidates(exclude=[])]
        third = [p.name() for p in manager.list_fallback_candidates(exclude=[])]

        self.assert_equal(
            first,
            ["openai", "claude", "gemini"],
            "NaN and Infinity must be sanitized to unknown cost (sorted after the one real known cost, "
            "openai) rather than treated as a valid known cost that could sort ahead of it.",
        )
        self.assert_equal(first, second, "Sanitized NaN/Infinity ordering must remain deterministic across calls.")
        self.assert_equal(second, third, "Sanitized NaN/Infinity ordering must remain deterministic across calls.")

    def _test_provider_manager_sanitizes_negative_and_non_numeric_on_direct_construction(self) -> None:
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("claude"),
                _FakeAIProvider("gemini"),
                _FakeAIProvider("openai"),
            ],
            cost_aware_enabled=True,
            relative_cost={"claude": -5.0, "gemini": "bad", "openai": [1, 2]},
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(len(candidates), 3, "No provider may be excluded due to an invalid relative_cost.")
        self.assert_equal(
            [p.name() for p in candidates],
            ["claude", "gemini", "openai"],
            "With every configured cost invalid, all three must fall into the unknown-cost group and "
            "sort alphabetically among themselves, exactly as if none had been configured at all.",
        )

    def _test_provider_manager_accepts_zero_and_positive_on_direct_construction(self) -> None:
        manager = _make_real_manager(
            providers=[
                _FakeAIProvider("claude"),
                _FakeAIProvider("gemini"),
                _FakeAIProvider("openai"),
            ],
            cost_aware_enabled=True,
            relative_cost={"claude": 0.0, "gemini": 5.0},  # openai unconfigured
        )

        candidates = manager.list_fallback_candidates(exclude=[])

        self.assert_equal(
            [p.name() for p in candidates],
            ["claude", "gemini", "openai"],
            "A valid 0.0 relative_cost must remain the cheapest known cost, sorted ahead of both a "
            "higher known cost and an unconfigured (unknown-cost) provider -- sanitization must not "
            "affect valid values.",
        )

    def _test_provider_manager_sanitization_does_not_affect_primary_provider(self) -> None:
        registry = ProviderRegistry()
        registry.register(_FakeAIProvider("claude"))
        registry.register(_FakeAIProvider("gemini"))
        manager = ProviderManager(
            registry=registry,
            enabled=True,
            default_provider="claude",
            cost_aware_enabled=True,
            relative_cost={"claude": math.nan, "gemini": 0.01},
        )

        current = manager.get_current()

        self.assert_true(current is not None, "The configured default_provider must still be selected.")
        self.assert_equal(
            current.name(),
            "claude",
            "Sanitizing an invalid relative_cost must have zero effect on the primary/current provider, "
            "which is governed solely by default_provider/set_current().",
        )
