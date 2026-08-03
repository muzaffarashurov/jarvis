"""EP-027 Context Compression.

Shrinks already-assembled context (raw text, or the results of EP-026
Semantic Search) to fit within a configured character/chunk budget:
removes duplicated chunks and duplicated paragraphs, preserves chunk
ordering and metadata, and enforces a maximum context size -- using
only deterministic, arithmetic operations. This package must NOT
summarize using AI, NOT rewrite text, NOT call an LLM, and NOT change
semantic meaning. It has no dependency on any AI Provider, the Prompt
Engine, the RAG Engine (EP-022), Conversation Engine, Planner,
Reflection, Browser Automation, Tool Calling, or any future Agent
Framework component. It may use only the public APIs of Semantic
Search (EP-026), Knowledge Base (EP-024), and Long-Term Memory
(EP-025).

`ContextChunk` / `CompressionResult` (`compression_result.py`) are the
plain data types shared by the rest of this package. `CompressionProvider`
(`compression_provider.py`) is the structural contract every
compression provider must implement; `DefaultCompressionProvider` is
the built-in, deduplication-and-limit-enforcement provider registered
under the name "compression". `CompressionManager`
(`compression_manager.py`) owns provider registration, active-provider
selection, and the default `max_context_characters` / `max_chunks` /
`deduplicate` limits, mirroring EP-026's `SemanticManager`.
`CompressionEngine` (`compression_engine.py`) is the provider-independent
pipeline that turns raw text (or EP-026 `SemanticResult` instances)
into chunks and delegates deduplication, ordering and limit enforcement
to the active `CompressionProvider`.

Public API:
    ContextChunk -- A single unit of input context.
    CompressionResult -- The outcome of compressing an ordered chunk sequence.
    CompressionProvider -- Structural contract every compression
        provider must implement.
    DefaultCompressionProvider -- The built-in dedup + limit-enforcement provider.
    CompressionProviderStatus -- Lifecycle status a provider reports.
    CompressionProviderHealth -- Configuration-derived readiness result.
    ContextCompressionError -- Base class for every Context Compression exception.
    CompressionConfigurationError -- Invalid 'context_compression.*' configuration.
    CompressionProviderError -- Base class for provider-level errors.
    CompressionProviderConfigurationError -- Disabled/unconfigured provider.
    CompressionProviderUnavailableError -- Provider cannot currently serve requests.
    CompressionManager -- Owns provider selection, configuration loading,
        and provider lifecycle.
    CompressionProviderRegistryError -- Duplicate provider registration.
    CompressionProviderNotFoundError -- Unknown provider name.
    CompressionEngine -- The context -> chunks -> compressed-result pipeline.
    CompressionEngineError -- Base class for engine-level errors.
    NoCompressionProviderSelectedError -- No provider is currently selected.
    EmptyContextError -- Empty/whitespace-only context was submitted.
    SemanticSearchUnavailableError -- compress_query() used without a SemanticEngine.
"""

from __future__ import annotations

from src.core.context_compression.compression_engine import (
    CompressionEngine,
    CompressionEngineError,
    EmptyContextError,
    NoCompressionProviderSelectedError,
    SemanticSearchUnavailableError,
)
from src.core.context_compression.compression_manager import (
    CompressionManager,
    CompressionProviderNotFoundError,
    CompressionProviderRegistryError,
)
from src.core.context_compression.compression_provider import (
    CompressionConfigurationError,
    CompressionProvider,
    CompressionProviderConfigurationError,
    CompressionProviderError,
    CompressionProviderHealth,
    CompressionProviderStatus,
    CompressionProviderUnavailableError,
    ContextCompressionError,
    DefaultCompressionProvider,
)
from src.core.context_compression.compression_result import CompressionResult, ContextChunk

__all__ = [
    "ContextChunk",
    "CompressionResult",
    "CompressionProvider",
    "DefaultCompressionProvider",
    "CompressionProviderStatus",
    "CompressionProviderHealth",
    "ContextCompressionError",
    "CompressionConfigurationError",
    "CompressionProviderError",
    "CompressionProviderConfigurationError",
    "CompressionProviderUnavailableError",
    "CompressionManager",
    "CompressionProviderRegistryError",
    "CompressionProviderNotFoundError",
    "CompressionEngine",
    "CompressionEngineError",
    "NoCompressionProviderSelectedError",
    "EmptyContextError",
    "SemanticSearchUnavailableError",
]
