"""EP-031 Tool Engine.

Turns an already-identified `(subsystem, action)` reference -- most
notably an EP-029 `PlanStep` dispatched by EP-030's Plan Execution
Engine -- into a real invocation of an already-implemented Engineering
Package's public API. This package must NOT call an AI provider,
build a prompt, plan a request, decompose it into steps, walk a Plan,
or decide dispatch order/failure policy -- those remain, respectively,
the Conversation/Prompt Engine's, EP-029 Planning Engine's, and EP-030
Plan Execution Engine's jobs. Tool Engine's entire responsibility is
narrower and more concrete than any of those: given a tool reference,
actually call the real subsystem method it wraps, and report whether
that call succeeded.

It may use only the public APIs of completed Engineering Packages --
each built-in `Tool`'s `handler` is a closure over one already-built
subsystem *Service* instance's public method (e.g.
`MemoryService.list_entries`, `KnowledgeService.list_records`,
`LongTermMemoryService.list_memories`, `AgentService.list_subsystems`)
-- never any subsystem's private internals. Tool Engine itself never
instantiates a subsystem service; every handler is bound once, at
composition-root time, in `src/bootstrap.py`.

NAMING / SCOPE NOTE: several of EP-029's recognized actions
(`generate_embedding`, `retrieve_context`, `semantic_search`,
`compress_context`) require a text parameter that neither `PlanStep`
nor `PlanExecutionProvider.execute_step()` currently carries. Per
this project's Unknown API Policy ("never invent APIs... leave a
TODO"), EP-031 does not invent a parameter source for these actions --
it registers real, built-in tools only for the parameter-free actions
(`retrieve_from_memory`, `query_knowledge_base`,
`query_long_term_memory`, `coordinate_subsystems`,
`acknowledge_request`) and leaves the remaining four genuinely
unregistered. Dispatching one of those four through Tool Engine
produces an honest `ToolStatus.FAILED` / `StepStatus.FAILED` -- "no
tool registered for this action" -- rather than a fabricated success.
Widening `PlanStep`'s schema to carry a parameter would be an EP-029/
EP-030 architecture change and is explicitly out of scope here.

`Tool` (`tool.py`) is the plain catalog-entry data type; `ToolStatus`/
`ToolResult` (`tool_result.py`) are the plain outcome data types
shared by the rest of this package, mirroring
`src/core/plan_execution/plan_execution_result.py`'s role relative to
`PlanExecutionProvider`/`PlanExecutionEngine`. `ToolRegistry`
(`tool_registry.py`) is the thread-safe tool catalog, mirroring
`PluginRegistry`/`ProcessRegistry`. `ToolProvider` (`tool_provider.py`)
is the structural contract every invocation strategy must implement;
`DefaultToolProvider` is the built-in, real-invocation provider,
registered under the name "tool_engine" (matching
'tool.default_provider' in config/config.yaml). `ToolManager`
(`tool_manager.py`) owns provider registration, active-provider
selection, and the tool catalog, mirroring EP-026 through EP-030's
*Manager classes. `ToolEngine` (`tool_engine.py`) is the
provider-independent pipeline that resolves a tool (by id or by
`(subsystem, action)`) and dispatches it to the active `ToolProvider`.
`ToolExecutionProvider` (`tool_execution_provider.py`) is the bridge
adapter implementing EP-030's `PlanExecutionProvider` ABC -- the
"Tool-Engine-backed provider" EP-030's own docstrings anticipated,
registered into `PlanExecutionManager` from `src/bootstrap.py` without
modifying any EP-030 file.

Public API:
    Tool -- A single catalog entry describing a real, invocable action.
    ToolStatus -- Outcome of invoking a single Tool.
    ToolResult -- The outcome of a single tool invocation.
    ToolProvider -- Structural contract every invocation strategy must implement.
    DefaultToolProvider -- The built-in, real-invocation provider.
    ToolError -- Base class for every Tool Engine exception.
    ToolConfigurationError -- Invalid 'tool.*' configuration.
    ToolProviderError -- Base class for provider-level errors.
    ToolRegistry -- Thread-safe catalog of registered tools.
    ToolRegistryError -- Duplicate tool registration.
    ToolNotFoundError -- Unknown tool id referenced.
    ToolManager -- Owns provider selection, configuration loading, and the tool catalog.
    ToolProviderRegistryError -- Duplicate provider registration.
    ToolProviderNotFoundError -- Unknown provider name.
    ToolEngine -- The tool-lookup -> real-invocation pipeline.
    ToolEngineError -- Base class for engine-level errors.
    NoToolProviderSelectedError -- No provider is currently selected.
    ToolNotRegisteredError -- invoke() referenced an unknown tool id.
    ToolExecutionProvider -- The EP-030 PlanExecutionProvider bridge.
"""

from __future__ import annotations

from src.core.tool.tool import Tool
from src.core.tool.tool_engine import (
    NoToolProviderSelectedError,
    ToolEngine,
    ToolEngineError,
    ToolNotRegisteredError,
)
from src.core.tool.tool_execution_provider import ToolExecutionProvider
from src.core.tool.tool_manager import (
    ToolManager,
    ToolProviderNotFoundError,
    ToolProviderRegistryError,
)
from src.core.tool.tool_provider import (
    DefaultToolProvider,
    ToolConfigurationError,
    ToolError,
    ToolProvider,
    ToolProviderError,
)
from src.core.tool.tool_registry import ToolNotFoundError, ToolRegistry, ToolRegistryError
from src.core.tool.tool_result import ToolResult, ToolStatus

__all__ = [
    "Tool",
    "ToolStatus",
    "ToolResult",
    "ToolProvider",
    "DefaultToolProvider",
    "ToolError",
    "ToolConfigurationError",
    "ToolProviderError",
    "ToolRegistry",
    "ToolRegistryError",
    "ToolNotFoundError",
    "ToolManager",
    "ToolProviderRegistryError",
    "ToolProviderNotFoundError",
    "ToolEngine",
    "ToolEngineError",
    "NoToolProviderSelectedError",
    "ToolNotRegisteredError",
    "ToolExecutionProvider",
]
