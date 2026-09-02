"""AIPlanningProvider for EP-058 Autonomous Planning.

Implements `EP058_DESIGN.md`'s approved Candidate A (Owner Decision
D1): a second, AI-/LLM-backed `PlanningProvider` implementation,
registered alongside -- never replacing -- `DefaultPlanningProvider`
(EP-029, `planning_provider.py`, completely unmodified by this
module). `AIPlanningProvider` reasons about a request's *meaning*
using an AI provider, rather than `DefaultPlanningProvider`'s fixed
substring rules, but chooses only from that exact same, already-real
`(subsystem, action)` vocabulary -- it never invents a subsystem or
action name Tool Engine (EP-031) does not already recognize.

Reuses the existing AI Provider Manager (EP-014/015) directly, via
`ProviderManager.get_current()` -> `AIProvider.ask()`, following the
same deliberate bypass of `AIService`'s Conversation/Context/Prompt
Engine pipeline that `PromptOptimizerModule` (EP-055,
`src/skills/prompt_optimizer/skill.py`) already established: going
through `AIService.ask()` would incorrectly append this call as a new
conversation turn. No second AI-client mechanism is introduced -- the
exact same `ProviderManager`/`AIProvider` public API every other
AI-calling component in this repository already uses.

This module performs no task execution and no tool calling: like
`DefaultPlanningProvider`, it only ever produces a `Plan` --
`PlanningEngine`'s existing, unmodified EP-028 Agent Framework
reconciliation logic and EP-030's Plan Execution Engine remain the
only components that ever act on that `Plan`, unaffected by which
provider produced it.

`_MENU` is derived programmatically, once, from
`planning_provider._KEYWORD_RULES` -- the exact same table
`DefaultPlanningProvider` already uses (deduplicated to one entry per
distinct `(subsystem, action)` pair) -- so both providers remain
genuine, interchangeable substitutes for each other over the
identical action space, and `_MENU` can never drift out of sync with
`DefaultPlanningProvider`'s own recognized vocabulary. `_FALLBACK_ACTION`/
`_FALLBACK_DESCRIPTION` are imported, not duplicated, for the same
reason.
"""

from __future__ import annotations

from src.core.ai.provider import ProviderError
from src.core.ai.provider_manager import ProviderManager
from src.core.planning.planning_provider import (
    _FALLBACK_ACTION,
    _FALLBACK_DESCRIPTION,
    _KEYWORD_RULES,
    PlanningProvider,
    PlanningProviderConfigurationError,
    PlanningProviderError,
    PlanningProviderHealth,
    PlanningProviderStatus,
)
from src.core.planning.planning_result import Plan, PlanStep

__all__ = ["AIPlanningProvider"]


def _build_menu() -> tuple[tuple[str, str, str], ...]:
    """Derive the deduplicated `(subsystem, action, description)` menu from `_KEYWORD_RULES`.

    Returns:
        One entry per distinct `(subsystem, action)` pair, in the
        same order `_KEYWORD_RULES` first introduces each pair --
        matching `DefaultPlanningProvider.plan()`'s own
        "first matching keyword for a subsystem wins" rule order.
    """
    seen: set[tuple[str, str]] = set()
    menu: list[tuple[str, str, str]] = []
    for _keyword, subsystem, action, description in _KEYWORD_RULES:
        pair = (subsystem, action)
        if pair in seen:
            continue
        seen.add(pair)
        menu.append((subsystem, action, description))
    return tuple(menu)


#: The exact, fixed `(subsystem, action, description)` menu this provider may choose
#: from -- derived once, above, from `DefaultPlanningProvider`'s own `_KEYWORD_RULES`.
#: Never modified at runtime; never extended with an AI-invented entry.
_MENU: tuple[tuple[str, str, str], ...] = _build_menu()

#: Fast (subsystem, action) -> description lookup for reply parsing.
_MENU_LOOKUP: dict[tuple[str, str], str] = {(subsystem, action): description for subsystem, action, description in _MENU}

_PROMPT_TEMPLATE: str = (
    "You are choosing which of Jarvis's already-implemented subsystems, if any, "
    "are relevant to a request. Choose only from the fixed menu below -- never "
    "invent a subsystem or action that is not listed.\n\n"
    "Menu (one entry per line, format \"subsystem|action - description\"):\n"
    "{menu_lines}\n\n"
    'Request: "{request}"\n\n'
    "Reply with one line per relevant menu entry, most relevant first, each "
    'formatted exactly as "subsystem|action" (omit the description). Do not '
    "include any other text, explanation, numbering, or bullet characters. If "
    "none of the menu entries are relevant, reply with an empty response."
)


def _render_menu_lines() -> str:
    """Return `_MENU` rendered as one "subsystem|action - description" line per entry."""
    return "\n".join(f"{subsystem}|{action} - {description}" for subsystem, action, description in _MENU)


def _build_prompt(request: str) -> str:
    """Build the single prompt sent to the AI provider for `request`.

    Args:
        request: The request text to decompose.

    Returns:
        The fully composed prompt text.
    """
    return _PROMPT_TEMPLATE.format(menu_lines=_render_menu_lines(), request=request)


def _parse_line(line: str) -> tuple[str, str] | None:
    """Parse one reply line into a `(subsystem, action)` pair, or None if unparseable.

    Tolerant of common formatting an AI reply may add despite the
    prompt's instructions not to: a leading list marker ("-", "*",
    "1.", "1)"), surrounding whitespace, and a trailing
    " - <description>" the model appended anyway. Never raises.

    Args:
        line: One line of the AI provider's reply text.

    Returns:
        The parsed `(subsystem, action)` pair (not yet validated
        against the menu), or None if `line` contains no "|".
    """
    stripped = line.strip()
    # Strip one leading list marker if present: "-", "*", or a small
    # leading number followed by "." or ")" (e.g. "1.", "12)").
    if stripped[:1] in ("-", "*"):
        stripped = stripped[1:].strip()
    else:
        digits = 0
        while digits < len(stripped) and stripped[digits].isdigit():
            digits += 1
        if 0 < digits <= 3 and digits < len(stripped) and stripped[digits] in ".)":
            stripped = stripped[digits + 1 :].strip()
    if "|" not in stripped:
        return None
    subsystem_part, _, action_part = stripped.partition("|")
    # Tolerate a trailing " - <description>" the model appended anyway.
    action_part = action_part.split(" - ", 1)[0]
    subsystem = subsystem_part.strip().strip("-*").strip()
    action = action_part.strip().strip("-*").strip()
    if not subsystem or not action:
        return None
    return subsystem, action


def _parse_reply(reply_text: str, max_steps: int) -> tuple[list[PlanStep], bool]:
    """Parse an AI reply into an ordered list of `PlanStep`s.

    Per this project's Unknown API Policy, applied here to the AI
    provider's own output: a parsed pair is only ever accepted when it
    exactly matches an entry already in `_MENU` -- nothing the AI
    invents is ever turned into a step. A reply that yields zero valid
    steps (empty, malformed, or entirely off-menu) falls back to the
    identical "acknowledge_request" step `DefaultPlanningProvider`
    already produces in the analogous case, so `plan()` never returns
    a `Plan` with an empty `steps` list, matching `Plan`'s own
    existing invariant.

    Args:
        reply_text: The AI provider's raw reply text.
        max_steps: Maximum number of steps to keep, preserving order.

    Returns:
        A tuple of `(steps, truncated)`, ready to build a `Plan` from.
    """
    raw_steps: list[tuple[str | None, str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    for line in reply_text.splitlines():
        parsed = _parse_line(line)
        if parsed is None:
            continue
        subsystem, action = parsed
        pair = (subsystem, action)
        if pair not in _MENU_LOOKUP or pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        raw_steps.append((subsystem, action, _MENU_LOOKUP[pair]))

    if not raw_steps:
        raw_steps.append((None, _FALLBACK_ACTION, _FALLBACK_DESCRIPTION))

    truncated = len(raw_steps) > max_steps
    limited_steps = raw_steps[:max_steps]

    steps = [
        PlanStep(order=index + 1, subsystem=subsystem, action=action, description=description, available=True)
        for index, (subsystem, action, description) in enumerate(limited_steps)
    ]
    return steps, truncated


class AIPlanningProvider(PlanningProvider):
    """AI-/LLM-backed planning provider: chooses from a fixed menu using an AI provider.

    Registered by `Bootstrap` alongside -- never in place of --
    `DefaultPlanningProvider`, under the stable name "ai". Selected
    only when an operator explicitly runs 'planning use ai' (or sets
    'planning.default_provider: "ai"'); `DefaultPlanningProvider`
    remains the unaffected default either way (`EP058_DESIGN.md`
    Section 4/Owner Decision D1).

    Unlike `DefaultPlanningProvider`, `status()` is overridden: this
    provider reports `NOT_CONFIGURED` whenever no AI provider is
    currently selected (`ai.default_provider` is "none" by default),
    exactly the way `CompressionProvider`/`SemanticProvider` already
    report an unconfigured backing provider one layer up the stack.
    """

    _NAME: str = "ai"

    def __init__(self, provider_manager: ProviderManager) -> None:
        """Initialize the AIPlanningProvider.

        Args:
            provider_manager: The already-constructed `ProviderManager`
                (EP-014), used only via `get_current()` to reach the
                currently-selected raw `AIProvider` -- never
                constructed or owned by this class.
        """
        self._provider_manager = provider_manager

    def provider_name(self) -> str:
        """Return this provider's stable identifier: "ai"."""
        return self._NAME

    def status(self) -> PlanningProviderStatus:
        """Return NOT_CONFIGURED when no AI provider is currently selected, else AVAILABLE."""
        if self._provider_manager.get_current() is None:
            return PlanningProviderStatus.NOT_CONFIGURED
        return PlanningProviderStatus.AVAILABLE

    def health(self) -> PlanningProviderHealth:
        """Return a configuration-derived readiness check (no network access, no planning)."""
        if self.is_available():
            return PlanningProviderHealth(
                available=True,
                message=f"Provider '{self._NAME}' is configured (AI provider selected).",
            )
        return PlanningProviderHealth(
            available=False,
            message=f"Provider '{self._NAME}' is not available: no AI provider is currently selected.",
        )

    def plan(self, request: str, max_steps: int) -> Plan:
        """Decompose `request` into an ordered `Plan`, using the currently selected AI provider.

        Args:
            request: The request text to decompose. Sent to the AI
                provider verbatim, alongside the fixed menu (module
                docstring) -- never combined with conversation
                history, memory, or file content.
            max_steps: Maximum number of steps the returned plan may
                contain. Must be a positive integer.

        Returns:
            The resulting Plan. Never has an empty `steps` list -- a
            reply naming no valid menu entry still yields one
            fallback step, matching `DefaultPlanningProvider`'s own
            behavior in the analogous case.

        Raises:
            PlanningProviderError: If `max_steps` is not a positive
                integer.
            PlanningProviderConfigurationError: If no AI provider is
                currently selected.
            PlanningProviderError: If the currently selected AI
                provider's `ask()` call itself fails.
        """
        if max_steps <= 0:
            raise PlanningProviderError("'max_steps' must be a positive integer.")

        provider = self._provider_manager.get_current()
        if provider is None:
            raise PlanningProviderConfigurationError(
                "No AI provider is currently selected; the 'ai' planning provider "
                "cannot plan. Select one via the AI Provider Manager ('ai use "
                "<provider>'), or switch back to the deterministic provider via "
                "'planning use planning'."
            )

        prompt = _build_prompt(request)
        try:
            response = provider.ask(prompt)
        except ProviderError as exc:
            raise PlanningProviderError(f"AI planning provider failed: {exc}") from exc

        steps, truncated = _parse_reply(response.text, max_steps)
        return Plan(request=request, steps=steps, step_count=len(steps), truncated=truncated)
