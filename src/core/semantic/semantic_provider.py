"""SemanticProvider domain model for EP-026 Semantic Search.

Defines the abstraction every semantic search provider must implement
so the rest of Jarvis never needs to know which similarity-search
strategy is currently active, matching the pattern already used by
the Embedding Provider Framework (see `src/core/embedding/provider.py`)
and the AI Provider Framework (see `src/core/ai/provider.py`).

The task brief for EP-026 names four *future* provider strategies --
`CosineSimilarityProvider`, `HybridSearchProvider`, `ANNProvider`,
`VectorDatabaseProvider` -- and is explicit that none of them is to be
implemented yet, "only create abstraction". Taken literally that would
leave Semantic Search without any working provider at all, which
conflicts with this EP's own goal ("Semantic Search must: perform
semantic similarity search, use embeddings, calculate similarity,
rank results"). This module resolves that by implementing exactly one
concrete, built-in provider -- `DefaultSemanticProvider`, registered
under the stable name "semantic" (matching
'semantic.default_provider' in config/config.yaml) -- so the
subsystem is actually usable today, while still not implementing any
of the four named *future* provider classes. `CosineSimilarityProvider`,
`HybridSearchProvider`, `ANNProvider` and `VectorDatabaseProvider`
remain unimplemented extension points for a future EP.

This module owns no embedding logic and no Knowledge Base / Long-Term
Memory access: it only scores and ranks `SemanticCandidate` instances
it is handed, exactly like `EmbeddingProvider.embed()` only transforms
the text it is handed.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from src.core.semantic.semantic_result import SemanticCandidate, SemanticResult

__all__ = [
    "SemanticProviderStatus",
    "SemanticProviderHealth",
    "SemanticError",
    "SemanticConfigurationError",
    "SemanticProviderError",
    "SemanticProviderConfigurationError",
    "SemanticProviderUnavailableError",
    "SemanticProvider",
    "DefaultSemanticProvider",
]


class SemanticProviderStatus(str, Enum):
    """Lifecycle status a registered semantic provider can report.

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
class SemanticProviderHealth:
    """Result of a provider's own `health()` check.

    This is a configuration-derived readiness check only -- no
    provider performs a network request or a real search as part of
    `health()`.

    Attributes:
        available: Whether the provider reports itself ready for use.
        message: Human-readable explanation of the health result.
    """

    available: bool
    message: str


class SemanticError(Exception):
    """Common root for every exception raised by Semantic Search (EP-026).

    Downstream packages (e.g. a future Agent Framework) can catch this
    single type to handle "anything semantic-search-related" without
    needing to know about every specific failure mode (provider-level,
    engine-level, manager-level, or configuration-level).
    """


class SemanticConfigurationError(SemanticError):
    """Raised when 'semantic.*' configuration itself is invalid.

    This is distinct from `SemanticProviderConfigurationError`, which
    is a *runtime* condition (a provider is currently disabled or
    unconfigured, and may become available later without restarting).
    `SemanticConfigurationError` means the configuration value itself
    is malformed (wrong type, empty, or references a provider that
    does not exist) -- restarting with corrected configuration is
    required to resolve it.
    """


class SemanticProviderError(SemanticError):
    """Base class for errors raised while using a semantic provider."""


class SemanticProviderConfigurationError(SemanticProviderError):
    """Raised when a provider is disabled or missing required configuration."""


class SemanticProviderUnavailableError(SemanticProviderError):
    """Raised when a provider cannot currently serve search requests."""


class SemanticProvider(ABC):
    """Structural contract every semantic search provider must implement.

    A provider scores and orders `SemanticCandidate` instances against
    an already-computed query vector -- it never calls the Embedding
    Engine, never reads Knowledge Base or Long-Term Memory records
    directly, and never performs AI reasoning. Identity and status
    reporting must never perform network requests or expensive work,
    matching `EmbeddingProvider`'s convention
    (`src/core/embedding/provider.py`).
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return this provider's stable identifier (e.g. "semantic")."""
        raise NotImplementedError

    @abstractmethod
    def search(
        self,
        query_vector: list[float],
        candidates: list[SemanticCandidate],
        top_k: int,
        threshold: float,
    ) -> list[SemanticResult]:
        """Score `candidates` against `query_vector` and return the top matches.

        Args:
            query_vector: The embedding vector of the search query.
            candidates: The candidates to score, already embedded.
            top_k: Maximum number of results to return.
            threshold: Minimum similarity score a candidate must reach
                to be included in the result.

        Returns:
            The matching candidates as `SemanticResult` instances,
            ranked (see `rank()`) and limited to at most `top_k`
            entries, in descending order of score.

        Raises:
            SemanticProviderError: If this provider cannot currently
                perform a search (e.g. disabled, not configured).
        """
        raise NotImplementedError

    @abstractmethod
    def rank(self, results: list[SemanticResult]) -> list[SemanticResult]:
        """Order `results` from most to least relevant.

        Args:
            results: The results to order. Not mutated.

        Returns:
            A new list containing every entry of `results`, ordered
            from most to least relevant.
        """
        raise NotImplementedError

    # ---------- Lifecycle / diagnostics extension points ----------

    def status(self) -> SemanticProviderStatus:
        """Return this provider's current SemanticProviderStatus.

        Base implementation always reports AVAILABLE. Providers with
        an enabled/configured distinction should override this method.
        """
        return SemanticProviderStatus.AVAILABLE

    def is_available(self) -> bool:
        """Return whether this provider is enabled and fully configured."""
        return self.status() == SemanticProviderStatus.AVAILABLE

    def health(self) -> SemanticProviderHealth:
        """Return a configuration-derived readiness check (no network access, no search)."""
        if self.is_available():
            return SemanticProviderHealth(
                available=True, message=f"Provider '{self.provider_name()}' is configured."
            )
        return SemanticProviderHealth(
            available=False,
            message=f"Provider '{self.provider_name()}' is not available.",
        )


class DefaultSemanticProvider(SemanticProvider):
    """Built-in semantic search provider, using cosine similarity.

    Registered by `SemanticManager` under the name "semantic" (see
    'semantic.default_provider' in config/config.yaml). Performs a
    brute-force cosine-similarity comparison between the query vector
    and every candidate vector -- no external index, no network
    access, no AI reasoning.
    """

    _NAME: str = "semantic"

    def provider_name(self) -> str:
        """Return this provider's stable identifier: "semantic"."""
        return self._NAME

    def search(
        self,
        query_vector: list[float],
        candidates: list[SemanticCandidate],
        top_k: int,
        threshold: float,
    ) -> list[SemanticResult]:
        """Score `candidates` by cosine similarity against `query_vector`.

        Args:
            query_vector: The embedding vector of the search query.
            candidates: The candidates to score, already embedded.
            top_k: Maximum number of results to return. Must be positive.
            threshold: Minimum cosine-similarity score (inclusive) a
                candidate must reach to be included.

        Returns:
            Candidates scoring at or above `threshold`, ranked (see
            `rank()`) and limited to at most `top_k` entries.

        Raises:
            SemanticProviderError: If `top_k` is not a positive integer.
        """
        if top_k <= 0:
            raise SemanticProviderError("'top_k' must be a positive integer.")

        scored: list[SemanticResult] = []
        for candidate in candidates:
            score = self._cosine_similarity(query_vector, candidate.vector)
            if score >= threshold:
                scored.append(
                    SemanticResult(
                        source=candidate.source,
                        identifier=candidate.identifier,
                        text=candidate.text,
                        score=score,
                        metadata=candidate.metadata,
                    )
                )

        return self.rank(scored)[:top_k]

    def rank(self, results: list[SemanticResult]) -> list[SemanticResult]:
        """Order `results` by descending score, breaking ties by identifier.

        Args:
            results: The results to order. Not mutated.

        Returns:
            A new list, ordered from highest to lowest score; entries
            with an equal score are ordered by `(source, identifier)`
            for a deterministic, reproducible result.
        """
        return sorted(
            results,
            key=lambda result: (-result.score, result.source, result.identifier),
        )

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        """Compute the cosine similarity between two equal-length vectors.

        Args:
            left: The first vector.
            right: The second vector.

        Returns:
            The cosine similarity in [-1.0, 1.0], or 0.0 if either
            vector has zero magnitude or the vectors have different
            lengths (treated as no similarity, never an error, since a
            malformed candidate must not abort an entire search).
        """
        if len(left) != len(right) or not left:
            return 0.0

        dot_product = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0

        return dot_product / (left_norm * right_norm)
