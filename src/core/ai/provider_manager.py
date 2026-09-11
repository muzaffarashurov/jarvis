"""Provider selection for EP-014 AI Provider Manager.

ProviderManager is the single place that knows which AI provider is
currently active, keeping that choice entirely in memory so `ai use
<provider>` takes effect immediately -- no restart required, and no
write back to config/config.yaml (Config exposes no write path; see
src/core/config.py). Provider construction is delegated to
ProviderFactory and catalog storage to ProviderRegistry, so this class
owns current-provider/enabled-state selection only, per this project's
One Responsibility Per Component rule.

The rest of Jarvis is expected to depend only on ProviderManager (via
AIService), never on ProviderRegistry or a concrete AIProvider
directly, so the active provider can change without any other
component needing to know which one is active.

EP-069.1 (Automatic AI Provider Fallback on Request Failure)
additively adds `list_fallback_candidates()`: a read-only query over
the existing registry, used by AIService to find another available
provider when the current one fails. It introduces no new state, no
ordered preference list, and no change to `set_current()`/
`get_current()` -- fallback never changes which provider is
"current" for the next fresh request (`EP069_DESIGN.md` Section 14,
Owner Decision D1).

EP-069.2 (Configured AI Provider Fallback Ordering) additively adds an
optional, immutable-after-construction `fallback_order` preference,
consulted only inside `list_fallback_candidates()`. It changes nothing
about *which* providers are eligible (still `is_available()` and not
excluded, exactly as EP-069.1 left it) -- only the *order* in which an
already-computed eligible set is returned. Absent or empty
`fallback_order` reproduces EP-069.1's original alphabetical order
exactly, byte-for-byte (`EP069_2_DESIGN.md` Section 11/12, Owner
Decision D7). `set_current()`/`get_current()` and
`ProviderRegistry.list()`'s own general-purpose alphabetical
guarantee are both untouched by this addition.

EP-069.3 (Cost-Aware AI Provider Selection) additively extends
`list_fallback_candidates()` with an optional, operator-configured
`relative_cost` ordering, composed with EP-069.2's `fallback_order`
exactly as `EP069_3_DESIGN.md` Section 14.1 specifies: `fallback_order`
(an explicit, named operator preference) always takes priority for the
names it lists, in its own configured sequence, unchanged from
EP-069.2 above; `relative_cost` -- when `cost_aware_enabled` is True
-- governs the order only of whatever eligible candidates
`fallback_order` leaves unresolved (every eligible candidate, when
`fallback_order` is absent/empty, exactly as it did before EP-069.2
existed). `relative_cost` is a static, operator-declared relative
weight, never a measured or calculated cost (`EP069_3_DESIGN.md`
Section 9). Neither EP-069.3 addition changes *which* providers are
eligible, and neither ever touches `set_current()`/`get_current()`:
cost-aware ordering, like `fallback_order`, affects only which
provider is tried next *after* the current one has already failed,
never the primary/current provider selection (`EP069_3_DESIGN.md`
Section 14, Owner Decision D3).
"""

from __future__ import annotations

import math
from threading import Lock
from typing import Iterable

from loguru import logger

from src.core.ai.provider import AIProvider
from src.core.ai.provider_registry import ProviderRegistry

# Sort key used when cost-aware ordering is enabled: providers with a
# known `relative_cost` sort first (group 0), ascending by cost, tied
# by name; providers with no known cost (None) sort after every known-
# cost provider (group 1), tied by name. See EP069_3_DESIGN.md Section
# 14 -- this is a pure re-sort of whichever candidates `fallback_order`
# (EP-069.2) left unresolved, never a change to eligibility itself.
_UNKNOWN_COST_SORT_GROUP: int = 1
_KNOWN_COST_SORT_GROUP: int = 0


def _is_valid_relative_cost(value: object) -> bool:
    """Return whether `value` is a valid EP-069.3 `relative_cost`.

    A valid value is numeric (`int`/`float`), explicitly NOT `bool`
    (Python's `bool` is a subclass of `int`), finite (not NaN or
    +/-Infinity), and >= 0 -- the exact same rule `bootstrap.py`'s
    `_parse_relative_cost()` enforces at the composition root.

    This predicate exists so `ProviderManager` itself can never treat
    an invalid `relative_cost` as a known cost, even if constructed
    directly with an unvalidated mapping that bypasses
    `bootstrap.py` -- the sole production call site, which already
    validates every value before construction
    (`EP069_3_ARCHITECTURE_AUDIT.md` Finding EP069.3-AUDIT-001). It
    intentionally re-implements only this pure predicate, not
    `bootstrap.py`'s logging/warning responsibility: `ProviderManager`
    has no configuration key name to attribute a warning to (it only
    ever sees the already-keyed-by-provider-name mapping), and
    `bootstrap.py` already warns on every value it rejects in the real
    configuration path. Duplicating the predicate (not the warning,
    not a second configuration system) is the smallest change that
    closes the gap: an invalid value is silently treated as absent,
    exactly like every other "unknown cost" case
    (`EP069_3_DESIGN.md` Section 15).

    Args:
        value: The raw candidate `relative_cost` value.

    Returns:
        True if `value` may be used as a known cost; False if it must
        be treated as unknown.
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    numeric_value = float(value)
    if math.isnan(numeric_value) or math.isinf(numeric_value):
        return False
    return numeric_value >= 0


class ProviderManager:
    """Owns the currently active AI provider and the AI subsystem's enabled state.

    Responsibilities:
        - Register a provider with the underlying ProviderRegistry.
        - Return a single registered provider.
        - Select and report the currently active provider.
        - List every registered provider.
        - Disable the AI subsystem as a whole.
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        enabled: bool,
        default_provider: str | None,
        fallback_order: list[str] | None = None,
        cost_aware_enabled: bool = False,
        relative_cost: dict[str, float] | None = None,
    ) -> None:
        """Initialize the ProviderManager.

        Args:
            registry: Catalog of known AI providers.
            enabled: Initial value of 'ai.enabled' from configuration.
            default_provider: Initial value of 'ai.default_provider'
                from configuration. "none" (or None) means no provider
                is selected at startup.
            fallback_order: Initial value of 'ai.fallback_order' from
                configuration (EP-069.2) -- an operator-preferred
                provider-name order consulted only by
                `list_fallback_candidates()`. `None` or an empty list
                preserves EP-069.1's original alphabetical fallback
                order exactly. Read once here and never mutated
                afterward (`EP069_2_DESIGN.md` Section 17).
            cost_aware_enabled: Initial value of 'ai.cost_aware_enabled'
                (EP-069.3), already validated by the composition root
                (`bootstrap.py`) as a real `bool`. Defaults to False,
                matching 'ai.cost_aware_enabled's own default -- when
                False, `list_fallback_candidates()`'s ordering is
                completely unaffected by `relative_cost`
                (`EP069_3_DESIGN.md` Section 11).
            relative_cost: Mapping of provider name to its configured
                `providers.<name>.relative_cost` (EP-069.3). Every
                entry is independently re-validated here
                (`_is_valid_relative_cost()`) and any invalid entry
                (non-numeric, `bool`, negative, NaN, or infinite) is
                silently dropped -- treated exactly like an absent
                entry, i.e. "unknown cost" (`EP069_3_DESIGN.md` Section
                15) -- regardless of whether the caller already
                validated it. This makes the finite/non-negative/
                non-bool invariant a property of `ProviderManager`
                itself, not merely of `bootstrap.py`'s composition-root
                validation (`EP069_3_ARCHITECTURE_AUDIT.md` Finding
                EP069.3-AUDIT-001). A provider name absent from the
                sanitized mapping has "unknown cost" and is never
                excluded from candidacy. Read and sanitized once at
                construction and never mutated afterward -- like
                `fallback_order` above, this is startup configuration
                state, not a runtime-settable preference
                (`EP069_3_DESIGN.md` Section 17, Owner Decision D6).
        """
        self._registry = registry
        self._enabled = enabled
        self._current_name: str | None = (
            default_provider
            if default_provider and default_provider.lower() != "none"
            else None
        )
        self._fallback_order: list[str] = list(fallback_order) if fallback_order else []
        self._cost_aware_enabled = cost_aware_enabled
        self._relative_cost: dict[str, float] = {
            name: float(cost)
            for name, cost in (relative_cost or {}).items()
            if _is_valid_relative_cost(cost)
        }
        self._lock = Lock()

    # ---------- Required API ----------

    def register_provider(self, provider: AIProvider) -> None:
        """Register a provider so it can later be selected by `set_current()`.

        Args:
            provider: The AIProvider to register.

        Raises:
            ProviderRegistryError: If a provider with the same name is
                already registered.
        """
        self._registry.register(provider)

    def get_provider(self, name: str) -> AIProvider:
        """Return a single registered provider by name.

        Args:
            name: The provider's registered name.

        Returns:
            The matching AIProvider.

        Raises:
            ProviderNotFoundError: If `name` is not registered.
        """
        return self._registry.get(name)

    def set_current(self, name: str) -> None:
        """Select the currently active provider.

        Takes effect immediately in memory; no restart is required and
        no configuration file is written.

        Args:
            name: The registered provider name to activate.

        Raises:
            ProviderNotFoundError: If `name` is not registered.
        """
        self._registry.get(name)  # raises ProviderNotFoundError if unknown
        with self._lock:
            self._current_name = name
        logger.info(f"AI current provider set to '{name}'.")

    def get_current(self) -> AIProvider | None:
        """Return the currently active provider.

        Returns:
            The active AIProvider, or None if no provider is selected.
        """
        with self._lock:
            current_name = self._current_name
        if current_name is None:
            return None
        return self._registry.find(current_name)

    def list_providers(self) -> list[AIProvider]:
        """Return every registered provider."""
        return self._registry.list()

    def list_fallback_candidates(self, exclude: Iterable[str]) -> list[AIProvider]:
        """Return registered providers eligible as an AI Provider Fallback (EP-069.1) target.

        A candidate is eligible when it is registered, reports
        `is_available() == True`, and its name is not in `exclude`
        (typically every provider already attempted for the current
        request, per `EP069_DESIGN.md` Section 14). This eligibility
        rule is entirely unchanged by EP-069.2 -- `fallback_order`
        (below) only ever reorders an already-computed eligible set,
        never expands or shrinks it.

        Ordering (EP-069.2, `EP069_2_DESIGN.md` Section 11/12): when
        `fallback_order` was not provided (or was empty) at
        construction, ordering matches `ProviderRegistry.list()`'s
        existing deterministic, name-sorted order exactly -- byte-for-
        byte identical to EP-069.1's original behavior. When
        `fallback_order` is non-empty, eligible candidates whose name
        appears in it are returned first, in `fallback_order`'s own
        sequence; any remaining eligible candidate not named in
        `fallback_order` is appended afterward. A name in
        `fallback_order` that does not match any eligible candidate
        (unregistered, unavailable, or already excluded) is simply
        never matched and has no effect -- never an error, never a
        fabricated candidate.

        Ordering (EP-069.3, `EP069_3_DESIGN.md` Section 14/14.1):
        whichever eligible candidates `fallback_order` leaves
        unresolved above (every eligible candidate, when
        `fallback_order` is absent/empty) are, when `cost_aware_enabled`
        is True, ordered by ascending configured `relative_cost`
        instead of plain `name()` order -- a candidate with no
        configured cost is ordered after every candidate that has one;
        ties (equal cost, or multiple candidates with no configured
        cost) are broken alphabetically by `name()`. `fallback_order`
        always takes priority for the names it lists: cost never
        reorders a candidate `fallback_order` has already placed.
        When `cost_aware_enabled` is False -- the default -- this
        step is skipped entirely and the unresolved candidates keep
        their existing name-sorted order, reproducing EP-069.2's
        (and, transitively, EP-069.1's) exact behavior.

        This method performs no request-level orchestration and holds
        no state of its own beyond the immutable `fallback_order`/
        `cost_aware_enabled`/`relative_cost` configuration read once
        at construction: eligibility and the alphabetical base order
        are both derived fresh from the registry on every call, so
        they can never go stale relative to
        `register_provider()`/`remove()`.

        Args:
            exclude: Provider names to exclude from the result (e.g.
                every provider already attempted this request).

        Returns:
            Every eligible AIProvider, ordered per `fallback_order`
            (if configured) followed by any unlisted eligible
            candidates -- themselves ordered by `relative_cost`
            (EP-069.3, if `cost_aware_enabled`) or by `name()`
            (default) -- with no duplicates.
        """
        excluded = set(exclude)
        eligible = [
            provider
            for provider in self._registry.list()
            if provider.name() not in excluded and provider.is_available()
        ]
        ordered: list[AIProvider] = []
        if not self._fallback_order:
            unlisted = eligible
        else:
            eligible_by_name = {provider.name(): provider for provider in eligible}
            seen: set[str] = set()
            for name in self._fallback_order:
                # First occurrence wins; a repeated name in `fallback_order`
                # must never add the same candidate twice (Owner Decision,
                # `EP069_2_DESIGN.md` Section 12/14).
                if name in eligible_by_name and name not in seen:
                    ordered.append(eligible_by_name[name])
                    seen.add(name)
            unlisted = [provider for provider in eligible if provider.name() not in seen]

        if self._cost_aware_enabled:
            unlisted = sorted(unlisted, key=self._cost_sort_key)

        return ordered + unlisted

    def _cost_sort_key(self, provider: AIProvider) -> tuple[int, float, str]:
        """EP-069.3 sort key: known-cost ascending, then unknown-cost, both tied by name()."""
        cost = self._relative_cost.get(provider.name())
        if cost is None:
            return (_UNKNOWN_COST_SORT_GROUP, 0.0, provider.name())
        return (_KNOWN_COST_SORT_GROUP, cost, provider.name())

    # ---------- AI subsystem enable/disable ----------

    def is_enabled(self) -> bool:
        """Return whether the AI subsystem is currently enabled."""
        with self._lock:
            return self._enabled

    def disable(self) -> None:
        """Disable the AI subsystem and clear the current provider selection."""
        with self._lock:
            self._enabled = False
            self._current_name = None
        logger.info("AI subsystem disabled.")
