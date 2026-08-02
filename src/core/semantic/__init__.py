"""EP-026 Semantic Search.

Performs meaning-based similarity search over Knowledge Base (EP-024)
and Long-Term Memory (EP-025) records, using vectors produced by the
Embedding Engine (EP-021). This package must NOT generate answers,
NOT call an AI provider, NOT build prompts, NOT compress context, and
NOT reason. It has no dependency on the RAG Engine (EP-022), any AI
Provider, the Prompt Engine, Browser Automation, Tool Calling, the
Conversation Engine, or any future Agent Framework component.

`SemanticCandidate` / `SemanticResult` (`semantic_result.py`) are the
plain data types shared by the rest of this package. `SemanticProvider`
(`semantic_provider.py`) is the structural contract every semantic
search provider must implement; `DefaultSemanticProvider` is the
built-in, cosine-similarity-based provider registered under the name
"semantic". `SemanticManager` (`semantic_manager.py`) owns provider
registration, active-provider selection, and the default
`top_k` / `similarity_threshold` search parameters, mirroring EP-021's
`EmbeddingManager`. `SemanticEngine` (`semantic_engine.py`) is the
provider-independent pipeline that turns a query into a query vector,
gathers and embeds candidates from Knowledge Base and Long-Term
Memory, and delegates scoring and ranking to the active
`SemanticProvider`.

Public API:
    SOURCE_KNOWLEDGE / SOURCE_LONG_TERM_MEMORY -- Candidate/result
        source constants.
    SemanticCandidate -- A single record made searchable for one query.
    SemanticResult -- A single ranked match.
    SemanticProvider -- Structural contract every semantic provider
        must implement.
    DefaultSemanticProvider -- The built-in cosine-similarity provider.
    SemanticProviderStatus -- Lifecycle status a provider reports.
    SemanticProviderHealth -- Configuration-derived readiness result.
    SemanticError -- Base class for every Semantic Search exception.
    SemanticConfigurationError -- Invalid 'semantic.*' configuration.
    SemanticProviderError -- Base class for provider-level errors.
    SemanticProviderConfigurationError -- Disabled/unconfigured provider.
    SemanticProviderUnavailableError -- Provider cannot currently serve requests.
    SemanticManager -- Owns provider selection, configuration loading,
        and provider lifecycle.
    SemanticProviderRegistryError -- Duplicate provider registration.
    SemanticProviderNotFoundError -- Unknown provider name.
    SemanticEngine -- The query -> candidates -> ranked results pipeline.
    SemanticEngineError -- Base class for engine-level errors.
    NoSemanticProviderSelectedError -- No provider is currently selected.
    EmptySemanticQueryError -- An empty/whitespace-only query was searched.
"""

from __future__ import annotations

from src.core.semantic.semantic_engine import (
    EmptySemanticQueryError,
    NoSemanticProviderSelectedError,
    SemanticEngine,
    SemanticEngineError,
)
from src.core.semantic.semantic_manager import (
    SemanticManager,
    SemanticProviderNotFoundError,
    SemanticProviderRegistryError,
)
from src.core.semantic.semantic_provider import (
    DefaultSemanticProvider,
    SemanticConfigurationError,
    SemanticError,
    SemanticProvider,
    SemanticProviderConfigurationError,
    SemanticProviderError,
    SemanticProviderHealth,
    SemanticProviderStatus,
    SemanticProviderUnavailableError,
)
from src.core.semantic.semantic_result import (
    SOURCE_KNOWLEDGE,
    SOURCE_LONG_TERM_MEMORY,
    SemanticCandidate,
    SemanticResult,
)

__all__ = [
    "SOURCE_KNOWLEDGE",
    "SOURCE_LONG_TERM_MEMORY",
    "SemanticCandidate",
    "SemanticResult",
    "SemanticProvider",
    "DefaultSemanticProvider",
    "SemanticProviderStatus",
    "SemanticProviderHealth",
    "SemanticError",
    "SemanticConfigurationError",
    "SemanticProviderError",
    "SemanticProviderConfigurationError",
    "SemanticProviderUnavailableError",
    "SemanticManager",
    "SemanticProviderRegistryError",
    "SemanticProviderNotFoundError",
    "SemanticEngine",
    "SemanticEngineError",
    "NoSemanticProviderSelectedError",
    "EmptySemanticQueryError",
]
