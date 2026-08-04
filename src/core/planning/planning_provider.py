"""PlanningProvider domain model for EP-029 Planning Engine.

Defines the abstraction every planning strategy must implement so the
rest of Jarvis never needs to know which decomposition strategy is
currently active, matching the pattern already used by the Semantic
Search Provider Framework (`src/core/semantic/semantic_provider.py`),
the Context Compression Provider Framework
(`src/core/context_compression/compression_provider.py`), and the
Agent Framework (`src/core/agent/agent_provider.py`).

A future AI-/LLM-backed planning strategy (e.g. one that reasons about
a request using an AI provider) is an obvious, natural extension point
for this abstraction -- but implementing it is explicitly out of scope
here: EP-029 must not call an AI provider, an LLM, or perform any
reasoning beyond deterministic, rule-based keyword matching. This
module resolves that the same way EP-026/EP-027/EP-028 resolved the
analogous conflict: it implements exactly one concrete, built-in
provider -- `DefaultPlanningProvider`, registered under the stable name
"planning" (matching 'planning.default_provider' in config/config.yaml)
-- so the subsystem is actually usable today, while implementing no
AI-backed decomposition strategy at all.

This module performs no AI reasoning, no task execution, and no tool
calling: it only maps a request's text to an ordered sequence of
`PlanStep` instances via fixed, deterministic keyword rules -- it never
queries a live subsystem registry itself (that is `PlanningEngine`'s
job, using EP-028's public `AgentEngine.list_subsystems()`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from src.core.planning.planning_result import Plan, PlanStep

__all__ = [
    "PlanningProviderStatus",
    "PlanningProviderHealth",
    "PlanningError",
    "PlanningConfigurationError",
    "PlanningProviderError",
    "PlanningProviderConfigurationError",
    "PlanningProviderUnavailableError",
    "PlanningProvider",
    "DefaultPlanningProvider",
]

#: Deterministic keyword -> (subsystem, action, description) rules,
#: applied in this fixed order. Each rule contributes at most one step
#: per subsystem (the first matching keyword for a subsystem wins;
#: later keywords for an already-matched subsystem are skipped).
#: Matching is a case-insensitive substring check against the request
#: text -- never an AI classification, never a network call.
_KEYWORD_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("remember", "memory", "retrieve_from_memory", "Retrieve relevant entries from the Memory Manager."),
    ("recall", "memory", "retrieve_from_memory", "Retrieve relevant entries from the Memory Manager."),
    ("knowledge", "knowledge", "query_knowledge_base", "Query the Knowledge Base for relevant records."),
    ("document", "knowledge", "query_knowledge_base", "Query the Knowledge Base for relevant records."),
    (
        "long-term",
        "long_term_memory",
        "query_long_term_memory",
        "Query Long-Term Memory for persisted records.",
    ),
    (
        "long term",
        "long_term_memory",
        "query_long_term_memory",
        "Query Long-Term Memory for persisted records.",
    ),
    ("embed", "embedding", "generate_embedding", "Generate an embedding vector via the Embedding Engine."),
    ("vector", "embedding", "generate_embedding", "Generate an embedding vector via the Embedding Engine."),
    ("retrieve", "rag", "retrieve_context", "Retrieve context via the RAG Engine."),
    ("rag", "rag", "retrieve_context", "Retrieve context via the RAG Engine."),
    ("search", "semantic", "semantic_search", "Run a meaning-based search via Semantic Search."),
    ("find", "semantic", "semantic_search", "Run a meaning-based search via Semantic Search."),
    (
        "compress",
        "compression",
        "compress_context",
        "Compress and deduplicate context via Context Compression.",
    ),
    (
        "summarize",
        "compression",
        "compress_context",
        "Compress and deduplicate context via Context Compression.",
    ),
    (
        "shrink",
        "compression",
        "compress_context",
        "Compress and deduplicate context via Context Compression.",
    ),
    ("coordinate", "agent", "coordinate_subsystems", "Coordinate subsystems via the Agent Framework."),
    ("orchestrate", "agent", "coordinate_subsystems", "Coordinate subsystems via the Agent Framework."),
)

#: The fallback action/description produced when no keyword rule matches the request.
_FALLBACK_ACTION = "acknowledge_request"
_FALLBACK_DESCRIPTION = (
    "No matching subsystem keyword found in the request; the request is "
    "acknowledged without further decomposition."
)


class PlanningProviderStatus(str, Enum):
    """Lifecycle status a registered planning provider can report.

    Attributes:
        DISABLED: The provider is turned off in configuration.
        NOT_CONFIGURED: The provider is enabled but is missing
            configuration it needs to be usable.
        AVAILABLE: The provider is enabled and fully configured.
    """

    DISABLED = "DISABLED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    AVAILABLE = "AVAILABLE"


@dataclass(frozen=True)
class PlanningProviderHealth:
    """Result of a provider's own `health()` check.

    This is a configuration-derived readiness check only -- no
    provider performs a network request or builds a real plan as part
    of `health()`.

    Attributes:
        available: Whether the provider reports itself ready for use.
        message: Human-readable explanation of the health result.
    """

    available: bool
    message: str


class PlanningError(Exception):
    """Common root for every exception raised by the Planning Engine (EP-029).

    Downstream packages (e.g. a future Execution Engine) can catch
    this single type to handle "anything planning-related" without
    needing to know about every specific failure mode (provider-level,
    engine-level, manager-level, or configuration-level).
    """


class PlanningConfigurationError(PlanningError):
    """Raised when 'planning.*' configuration itself is invalid.

    This is distinct from a provider-level error: it means the
    configuration value itself is malformed (wrong type, empty, or
    references a provider that does not exist) -- restarting with
    corrected configuration is required to resolve it.
    """


class PlanningProviderError(PlanningError):
    """Base class for errors raised while using a planning provider."""


class PlanningProviderConfigurationError(PlanningProviderError):
    """Raised when a provider is disabled or missing required configuration."""


class PlanningProviderUnavailableError(PlanningProviderError):
    """Raised when a provider cannot currently serve planning requests."""


class PlanningProvider(ABC):
    """Structural contract every planning strategy must implement.

    A provider maps a request's text to an ordered `Plan` -- it never
    performs AI reasoning, never calls an AI provider, never executes
    a step, and never queries a live subsystem registry itself (steps
    are always produced with `available=True`; `PlanningEngine` is
    responsible for reconciling that against EP-028's Agent Framework,
    if one was supplied). Identity and status reporting must never
    perform network requests or expensive work, matching
    `CompressionProvider`'s convention.
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return this provider's stable identifier (e.g. "planning")."""
        raise NotImplementedError

    @abstractmethod
    def plan(self, request: str, max_steps: int) -> Plan:
        """Decompose `request` into an ordered `Plan`.

        Args:
            request: The request text to decompose. Never parsed with
                AI, never sent anywhere -- only matched against fixed,
                deterministic rules.
            max_steps: Maximum number of steps the returned plan may
                contain. Must be a positive integer.

        Returns:
            The resulting Plan. Never has an empty `steps` list -- a
            request matching no rule still yields one fallback step.

        Raises:
            PlanningProviderError: If this provider cannot currently
                plan (e.g. disabled, not configured), or if
                `max_steps` is not a positive integer.
        """
        raise NotImplementedError

    # ---------- Lifecycle / diagnostics extension points ----------

    def status(self) -> PlanningProviderStatus:
        """Return this provider's current PlanningProviderStatus.

        Base implementation always reports AVAILABLE. Providers with
        an enabled/configured distinction should override this method.
        """
        return PlanningProviderStatus.AVAILABLE

    def is_available(self) -> bool:
        """Return whether this provider is enabled and fully configured."""
        return self.status() == PlanningProviderStatus.AVAILABLE

    def health(self) -> PlanningProviderHealth:
        """Return a configuration-derived readiness check (no network access, no planning)."""
        if self.is_available():
            return PlanningProviderHealth(
                available=True, message=f"Provider '{self.provider_name()}' is configured."
            )
        return PlanningProviderHealth(
            available=False, message=f"Provider '{self.provider_name()}' is not available."
        )


class DefaultPlanningProvider(PlanningProvider):
    """Built-in planning provider: deterministic, keyword-rule decomposition only.

    Registered by `PlanningManager` under the name "planning" (see
    'planning.default_provider' in config/config.yaml). Performs a
    fixed, purely deterministic pipeline -- no AI reasoning, no
    network access:

        1. Scan the request (case-insensitive substring match) against
           a fixed, ordered table of keyword -> (subsystem, action,
           description) rules.
        2. Emit at most one step per distinct subsystem, in rule order
           (the first matching keyword for a subsystem wins).
        3. If no rule matched, emit a single fallback
           "acknowledge_request" step with no subsystem.
        4. Enforce `max_steps`, preserving order.

    Every step is returned with `available=True` -- this provider
    never queries a live subsystem registry; that reconciliation is
    `PlanningEngine`'s responsibility.
    """

    _NAME: str = "planning"

    def provider_name(self) -> str:
        """Return this provider's stable identifier: "planning"."""
        return self._NAME

    def plan(self, request: str, max_steps: int) -> Plan:
        """Decompose `request` into an ordered `Plan` using fixed keyword rules.

        Args:
            request: The request text to decompose.
            max_steps: Maximum number of steps the returned plan may
                contain. Must be a positive integer.

        Returns:
            The resulting Plan.

        Raises:
            PlanningProviderError: If `max_steps` is not a positive integer.
        """
        if max_steps <= 0:
            raise PlanningProviderError("'max_steps' must be a positive integer.")

        normalized_request = request.lower()
        matched_subsystems: set[str] = set()
        raw_steps: list[tuple[str | None, str, str]] = []

        for keyword, subsystem, action, description in _KEYWORD_RULES:
            if subsystem in matched_subsystems:
                continue
            if keyword in normalized_request:
                raw_steps.append((subsystem, action, description))
                matched_subsystems.add(subsystem)

        if not raw_steps:
            raw_steps.append((None, _FALLBACK_ACTION, _FALLBACK_DESCRIPTION))

        truncated = len(raw_steps) > max_steps
        limited_steps = raw_steps[:max_steps]

        steps = [
            PlanStep(
                order=index + 1,
                subsystem=subsystem,
                action=action,
                description=description,
                available=True,
            )
            for index, (subsystem, action, description) in enumerate(limited_steps)
        ]

        return Plan(request=request, steps=steps, step_count=len(steps), truncated=truncated)
