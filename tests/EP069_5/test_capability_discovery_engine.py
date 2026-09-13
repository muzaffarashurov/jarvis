"""Real engineering tests for EP-069.5 STEP 2 - Capability Discovery Engine.

Self-contained test suite (`NAME = "EP069_5"`) under `tests/EP069_5/`,
following `tests/EP069_4/test_unified_capability_abstraction.py`'s own
precedent of a package per sub-EP. Does not import `src.bootstrap` --
`EP069_5_DESIGN.md` Owner Decision OD2 explicitly excludes bootstrap/
CLI/config wiring from this EP's scope, so nothing under
`src/core/capability_discovery/` depends on it.

Covers every behavioral area required by STEP 2's implementation
prompt:
    1. basic capability discovery
    2. fit ranking
    3. deterministic ordering
    4. trust ordering
    5. UNVERIFIED behavior (included, ranked lowest)
    6. disabled capability exclusion
    7. cost_hints ordering
    8. unknown cost_hints keys (error)
    9. empty registry
    10. zero matches
    11. max_results truncation
    12. invalid max_results (error)
    13. read-only / non-mutation guarantees
    14. provider/engine interaction (custom provider, default provider)
    15. public API / import behavior
    16. error hierarchy (CapabilityDiscoveryError root)
"""

from __future__ import annotations

from src.core.capability import Capability, CapabilitySourceKind, CapabilityTrustLevel
from src.core.capability.capability_registry import CapabilityRegistry
from src.core.capability_discovery import (
    CapabilityDiscoveryEngine,
    CapabilityDiscoveryError,
    CapabilityDiscoveryProvider,
    CapabilityDiscoveryProviderError,
    CapabilityDiscoveryResult,
    CapabilityMatch,
    DefaultCapabilityDiscoveryProvider,
)
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


def _make_capability(
    id: str,
    name: str,
    description: str,
    trust_level: CapabilityTrustLevel = CapabilityTrustLevel.UNVERIFIED,
    enabled: bool = True,
) -> Capability:
    """Build a test `Capability` via EP-069.4's own, unmodified `Capability.create()`."""
    return Capability.create(
        id=id,
        name=name,
        description=description,
        source_kind=CapabilitySourceKind.INTERNAL,
        trust_level=trust_level,
        enabled=enabled,
    )


class _RecordingFakeProvider(CapabilityDiscoveryProvider):
    """Minimal, deterministic, test-only `CapabilityDiscoveryProvider`.

    Records exactly what it was called with, so tests can assert the
    Engine delegates correctly, without depending on
    `DefaultCapabilityDiscoveryProvider`'s own scoring behavior.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[Capability], int, dict[str, float] | None]] = []

    def provider_name(self) -> str:
        return "recording_fake"

    def discover(
        self,
        task: str,
        capabilities: list[Capability],
        max_results: int,
        cost_hints: dict[str, float] | None = None,
    ) -> CapabilityDiscoveryResult:
        self.calls.append((task, capabilities, max_results, cost_hints))
        matches = [
            CapabilityMatch(capability=capability, fit_score=1.0, rank=rank)
            for rank, capability in enumerate(capabilities[:max_results], start=1)
        ]
        return CapabilityDiscoveryResult(
            task=task,
            matches=matches,
            match_count=len(matches),
            truncated=len(capabilities) > max_results,
        )


@TestRegistry.register
class CapabilityDiscoveryEngineTest(BaseTest):
    NAME = "EP069_5"

    def run(self):
        # ---------- Public API / import behavior ----------
        self._test_public_api_exports()

        # ---------- Basic discovery / fit ranking ----------
        self._test_basic_discovery_returns_matching_capability()
        self._test_zero_fit_capability_is_excluded()
        self._test_fit_ranking_orders_stronger_match_first()
        self._test_deterministic_ordering_across_repeated_calls()

        # ---------- Trust ordering / UNVERIFIED behavior ----------
        self._test_trust_ordering_with_equal_fit()
        self._test_unverified_included_but_ranked_lowest()

        # ---------- Disabled capability exclusion ----------
        self._test_disabled_capability_excluded_even_with_high_fit()

        # ---------- Cost hints ----------
        self._test_cost_hints_break_ties_with_equal_fit_and_trust()
        self._test_unknown_cost_hints_key_raises()
        self._test_missing_cost_hint_defaults_to_zero()

        # ---------- Boundary cases ----------
        self._test_empty_registry_returns_empty_result()
        self._test_zero_matches_returns_empty_result_not_error()
        self._test_max_results_truncation()
        self._test_invalid_max_results_raises_via_engine()
        self._test_invalid_max_results_raises_via_provider_directly()

        # ---------- Read-only / non-mutation guarantees ----------
        self._test_discover_does_not_mutate_registry()
        self._test_discover_returns_same_capability_instances()

        # ---------- Provider/engine interaction ----------
        self._test_engine_defaults_to_default_provider()
        self._test_engine_delegates_to_custom_provider()
        self._test_engine_filters_disabled_before_delegating()

        # ---------- Error hierarchy ----------
        self._test_provider_error_is_a_discovery_error()

        return self.result

    # ---------- Public API / import behavior ----------

    def _test_public_api_exports(self) -> None:
        self.assert_true(
            issubclass(CapabilityDiscoveryProviderError, CapabilityDiscoveryError),
            "CapabilityDiscoveryProviderError must subclass CapabilityDiscoveryError.",
        )
        self.assert_true(
            issubclass(DefaultCapabilityDiscoveryProvider, CapabilityDiscoveryProvider),
            "DefaultCapabilityDiscoveryProvider must implement CapabilityDiscoveryProvider.",
        )
        engine = CapabilityDiscoveryEngine()
        self.assert_true(
            isinstance(engine, CapabilityDiscoveryEngine),
            "CapabilityDiscoveryEngine must be constructible with no arguments.",
        )

    # ---------- Basic discovery / fit ranking ----------

    def _test_basic_discovery_returns_matching_capability(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _make_capability("send_email", "Send Email", "Sends an email message to a recipient")
        )
        engine = CapabilityDiscoveryEngine()

        result = engine.discover("send email", registry)

        self.assert_equal(result.match_count, 1, "Exactly one capability should match.")
        self.assert_equal(
            result.matches[0].capability.id, "send_email", "The matching capability must be returned."
        )
        self.assert_equal(result.matches[0].rank, 1, "The sole match must have rank 1.")
        self.assert_equal(result.task, "send email", "The result must carry the original task text.")

    def _test_zero_fit_capability_is_excluded(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _make_capability(
                "convert_currency", "Convert Currency", "Converts an amount from one currency to another"
            )
        )
        engine = CapabilityDiscoveryEngine()

        result = engine.discover("send email", registry)

        self.assert_equal(
            result.match_count, 0, "A capability with zero fit must be excluded, not scored zero."
        )
        self.assert_false(result.truncated, "Zero matches must not be reported as truncated.")

    def _test_fit_ranking_orders_stronger_match_first(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _make_capability("full_match", "Send Email", "Sends an email message to a recipient")
        )
        registry.register(
            _make_capability("partial_match", "Draft Message", "Drafts an email message for review")
        )
        engine = CapabilityDiscoveryEngine()

        result = engine.discover("send email", registry)

        self.assert_equal(result.match_count, 2, "Both non-zero-fit capabilities must be returned.")
        self.assert_equal(
            result.matches[0].capability.id,
            "full_match",
            "The stronger textual match must rank first.",
        )
        self.assert_true(
            result.matches[0].fit_score > result.matches[1].fit_score,
            "The first-ranked match must have a strictly higher fit_score.",
        )

    def _test_deterministic_ordering_across_repeated_calls(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _make_capability("full_match", "Send Email", "Sends an email message to a recipient")
        )
        registry.register(
            _make_capability("partial_match", "Draft Message", "Drafts an email message for review")
        )
        engine = CapabilityDiscoveryEngine()

        first_ids = [m.capability.id for m in engine.discover("send email", registry).matches]
        second_ids = [m.capability.id for m in engine.discover("send email", registry).matches]

        self.assert_equal(
            first_ids, second_ids, "Repeated discover() calls with identical input must produce identical ordering."
        )

    # ---------- Trust ordering / UNVERIFIED behavior ----------

    def _test_trust_ordering_with_equal_fit(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _make_capability(
                "trusted_internal",
                "Send Email",
                "Sends an email message",
                trust_level=CapabilityTrustLevel.TRUSTED_INTERNAL,
            )
        )
        registry.register(
            _make_capability(
                "trusted_configured",
                "Send Email",
                "Sends an email message",
                trust_level=CapabilityTrustLevel.TRUSTED_CONFIGURED,
            )
        )
        registry.register(
            _make_capability(
                "unverified",
                "Send Email",
                "Sends an email message",
                trust_level=CapabilityTrustLevel.UNVERIFIED,
            )
        )
        engine = CapabilityDiscoveryEngine()

        result = engine.discover("send email", registry)

        ranked_ids = [m.capability.id for m in result.matches]
        self.assert_equal(
            ranked_ids,
            ["trusted_internal", "trusted_configured", "unverified"],
            "Equal-fit candidates must be ordered TRUSTED_INTERNAL > TRUSTED_CONFIGURED > UNVERIFIED.",
        )

    def _test_unverified_included_but_ranked_lowest(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _make_capability(
                "unverified",
                "Send Email",
                "Sends an email message",
                trust_level=CapabilityTrustLevel.UNVERIFIED,
            )
        )
        engine = CapabilityDiscoveryEngine()

        result = engine.discover("send email", registry)

        self.assert_equal(
            result.match_count,
            1,
            "An UNVERIFIED capability must still be included in results by default (Owner Decision OD6).",
        )

    # ---------- Disabled capability exclusion ----------

    def _test_disabled_capability_excluded_even_with_high_fit(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _make_capability(
                "disabled_high_fit",
                "Send Email",
                "Sends an email message to a recipient",
                enabled=False,
            )
        )
        engine = CapabilityDiscoveryEngine()

        result = engine.discover("send email", registry)

        self.assert_equal(
            result.match_count,
            0,
            "A disabled capability must never be returned, even with a strong textual fit.",
        )

    # ---------- Cost hints ----------

    def _test_cost_hints_break_ties_with_equal_fit_and_trust(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_make_capability("cheap", "Send Email", "Sends an email message"))
        registry.register(_make_capability("expensive", "Send Email", "Sends an email message"))
        engine = CapabilityDiscoveryEngine()

        result = engine.discover(
            "send email", registry, cost_hints={"cheap": 1.0, "expensive": 5.0}
        )

        ranked_ids = [m.capability.id for m in result.matches]
        self.assert_equal(
            ranked_ids, ["cheap", "expensive"], "Lower cost_hints value must rank first among equal fit/trust."
        )

    def _test_unknown_cost_hints_key_raises(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_make_capability("send_email", "Send Email", "Sends an email message"))
        engine = CapabilityDiscoveryEngine()

        raised = False
        try:
            engine.discover("send email", registry, cost_hints={"does_not_exist": 1.0})
        except CapabilityDiscoveryProviderError:
            raised = True
        self.assert_true(
            raised, "A cost_hints key with no matching candidate id must raise CapabilityDiscoveryProviderError."
        )

    def _test_missing_cost_hint_defaults_to_zero(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_make_capability("has_hint", "Send Email", "Sends an email message"))
        registry.register(_make_capability("no_hint", "Send Email", "Sends an email message"))
        engine = CapabilityDiscoveryEngine()

        # A positive cost on 'has_hint' vs. the implicit 0.0 default for
        # 'no_hint' must rank the unhinted (cost-neutral) capability first.
        result = engine.discover("send email", registry, cost_hints={"has_hint": 2.0})

        ranked_ids = [m.capability.id for m in result.matches]
        self.assert_equal(
            ranked_ids,
            ["no_hint", "has_hint"],
            "A capability with no cost_hints entry must be treated as cost 0.0 (cost-neutral).",
        )

    # ---------- Boundary cases ----------

    def _test_empty_registry_returns_empty_result(self) -> None:
        registry = CapabilityRegistry()
        engine = CapabilityDiscoveryEngine()

        result = engine.discover("send email", registry)

        self.assert_equal(result.match_count, 0, "An empty registry must yield zero matches, not an error.")
        self.assert_equal(result.matches, [], "matches must be an empty list for an empty registry.")

    def _test_zero_matches_returns_empty_result_not_error(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _make_capability(
                "convert_currency", "Convert Currency", "Converts an amount from one currency to another"
            )
        )
        engine = CapabilityDiscoveryEngine()

        result = engine.discover("send email", registry)

        self.assert_equal(
            result.match_count, 0, "Zero matching capabilities must yield an empty result, not raise."
        )

    def _test_max_results_truncation(self) -> None:
        registry = CapabilityRegistry()
        for index in range(5):
            registry.register(
                _make_capability(f"email_{index}", "Send Email", "Sends an email message")
            )
        engine = CapabilityDiscoveryEngine()

        result = engine.discover("send email", registry, max_results=2)

        self.assert_equal(result.match_count, 2, "max_results must cap the number of returned matches.")
        self.assert_true(result.truncated, "truncated must be True when more matches existed than max_results.")

    def _test_invalid_max_results_raises_via_engine(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_make_capability("send_email", "Send Email", "Sends an email message"))
        engine = CapabilityDiscoveryEngine()

        raised_zero = False
        try:
            engine.discover("send email", registry, max_results=0)
        except CapabilityDiscoveryProviderError:
            raised_zero = True
        self.assert_true(raised_zero, "max_results=0 must raise CapabilityDiscoveryProviderError via the engine.")

        raised_negative = False
        try:
            engine.discover("send email", registry, max_results=-1)
        except CapabilityDiscoveryProviderError:
            raised_negative = True
        self.assert_true(
            raised_negative, "A negative max_results must raise CapabilityDiscoveryProviderError via the engine."
        )

    def _test_invalid_max_results_raises_via_provider_directly(self) -> None:
        provider = DefaultCapabilityDiscoveryProvider()

        raised = False
        try:
            provider.discover("send email", [], max_results=0)
        except CapabilityDiscoveryProviderError:
            raised = True
        self.assert_true(
            raised, "The provider itself must reject a non-positive max_results, independent of the engine."
        )

    # ---------- Read-only / non-mutation guarantees ----------

    def _test_discover_does_not_mutate_registry(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_make_capability("send_email", "Send Email", "Sends an email message"))
        engine = CapabilityDiscoveryEngine()

        before = registry.list()
        engine.discover("send email", registry)
        after = registry.list()

        self.assert_equal(
            [c.id for c in before], [c.id for c in after], "discover() must never add, remove, or reorder registry entries."
        )

    def _test_discover_returns_same_capability_instances(self) -> None:
        registry = CapabilityRegistry()
        registered = _make_capability("send_email", "Send Email", "Sends an email message")
        registry.register(registered)
        engine = CapabilityDiscoveryEngine()

        result = engine.discover("send email", registry)

        self.assert_true(
            result.matches[0].capability is registered,
            "discover() must return the exact registered Capability instance, never a copy or mutation.",
        )

    # ---------- Provider/engine interaction ----------

    def _test_engine_defaults_to_default_provider(self) -> None:
        engine = CapabilityDiscoveryEngine()
        self.assert_true(
            isinstance(engine._provider, DefaultCapabilityDiscoveryProvider),
            "CapabilityDiscoveryEngine must default to DefaultCapabilityDiscoveryProvider when none is supplied.",
        )

    def _test_engine_delegates_to_custom_provider(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_make_capability("send_email", "Send Email", "Sends an email message"))
        fake_provider = _RecordingFakeProvider()
        engine = CapabilityDiscoveryEngine(provider=fake_provider)

        engine.discover("send email", registry, max_results=3, cost_hints={"send_email": 1.0})

        self.assert_equal(len(fake_provider.calls), 1, "The engine must delegate exactly once per discover() call.")
        recorded_task, recorded_capabilities, recorded_max_results, recorded_cost_hints = fake_provider.calls[0]
        self.assert_equal(recorded_task, "send email", "The task text must be forwarded unchanged.")
        self.assert_equal(recorded_max_results, 3, "max_results must be forwarded unchanged.")
        self.assert_equal(
            recorded_cost_hints, {"send_email": 1.0}, "cost_hints must be forwarded unchanged."
        )
        self.assert_equal(
            [c.id for c in recorded_capabilities],
            ["send_email"],
            "The engine must forward the enabled-filtered capability list to the provider.",
        )

    def _test_engine_filters_disabled_before_delegating(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_make_capability("enabled_one", "Send Email", "Sends an email message"))
        registry.register(
            _make_capability("disabled_one", "Send Email", "Sends an email message", enabled=False)
        )
        fake_provider = _RecordingFakeProvider()
        engine = CapabilityDiscoveryEngine(provider=fake_provider)

        engine.discover("send email", registry)

        recorded_capabilities = fake_provider.calls[0][1]
        self.assert_equal(
            [c.id for c in recorded_capabilities],
            ["enabled_one"],
            "The engine must filter out disabled capabilities before the provider ever sees them.",
        )

    # ---------- Error hierarchy ----------

    def _test_provider_error_is_a_discovery_error(self) -> None:
        caught_as_root = False
        try:
            raise CapabilityDiscoveryProviderError("example failure")
        except CapabilityDiscoveryError:
            caught_as_root = True
        self.assert_true(
            caught_as_root,
            "A raised CapabilityDiscoveryProviderError must be catchable as CapabilityDiscoveryError.",
        )
