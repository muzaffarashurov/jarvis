"""ToolProvider domain model for EP-031 Tool Engine.

Defines the abstraction every invocation strategy must implement so
the rest of Jarvis never needs to know which invocation strategy is
currently active, matching the pattern already used by the Semantic
Search Provider Framework (`src/core/semantic/semantic_provider.py`),
the Context Compression Provider Framework
(`src/core/context_compression/compression_provider.py`), the Agent
Framework (`src/core/agent/agent_provider.py`), the Planning Engine
(`src/core/planning/planning_provider.py`), and the Plan Execution
Engine (`src/core/plan_execution/plan_execution_provider.py`).

This module implements exactly one concrete, built-in provider --
`DefaultToolProvider`, registered under the stable name "tool_engine"
(matching 'tool.default_provider' in config/config.yaml) -- which
invokes a `Tool`'s pre-bound handler and translates the outcome (or
any raised exception) into a `ToolResult`. It performs the real
subsystem invocation itself -- unlike every provider abstraction that
came before it in this project, `DefaultToolProvider` is the first to
actually call out to a live subsystem service, which is precisely
EP-031's reason for existing (see `src/core/tool/__init__.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from loguru import logger

from src.core.tool.tool import Tool
from src.core.tool.tool_result import ToolResult, ToolStatus

__all__ = [
    "ToolError",
    "ToolConfigurationError",
    "ToolProviderError",
    "ToolProvider",
    "DefaultToolProvider",
]


class ToolError(Exception):
    """Common root for every exception raised by Tool Engine (EP-031).

    Downstream packages can catch this single type to handle "anything
    tool-related" without needing to know about every specific failure
    mode (provider-level, engine-level, manager-level, or
    configuration-level).
    """


class ToolConfigurationError(ToolError):
    """Raised when 'tool.*' configuration itself is invalid.

    This is distinct from a provider-level error: it means the
    configuration value itself is malformed (wrong type, empty, or
    references a provider that does not exist) -- restarting with
    corrected configuration is required to resolve it.
    """


class ToolProviderError(ToolError):
    """Base class for errors raised while using a tool provider."""


class ToolProvider(ABC):
    """Structural contract every tool-invocation strategy must implement.

    A provider invokes a single, already-resolved `Tool` -- it never
    decides which tool to invoke (that stays inside `ToolEngine`),
    and never performs AI reasoning or planning. `is_available()` must
    never perform network requests or expensive work, matching
    `CompressionProvider`'s convention.
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return this provider's stable identifier (e.g. "tool_engine")."""
        raise NotImplementedError

    @abstractmethod
    def invoke_tool(self, tool: Tool) -> ToolResult:
        """Invoke a single, already-resolved `Tool`.

        Args:
            tool: The tool to invoke. Callers only ever pass a tool
                that was found in the catalog -- resolution (by id or
                by subsystem/action) is `ToolEngine`'s concern, never
                this method's.

        Returns:
            The resulting ToolResult (`status` is always `COMPLETED`
            or `FAILED`).
        """
        raise NotImplementedError

    # ---------- Lifecycle / diagnostics extension point ----------

    def is_available(self) -> bool:
        """Return whether this provider is currently able to invoke tools.

        Base implementation always returns True. Providers with an
        enabled/configured distinction should override this method.
        """
        return True


class DefaultToolProvider(ToolProvider):
    """Built-in tool provider: invokes a `Tool`'s pre-bound handler.

    Registered by `ToolManager` under the name "tool_engine" (see
    'tool.default_provider' in config/config.yaml). Performs the real
    subsystem invocation: calls `tool.handler()` and reports:

        - `ToolStatus.COMPLETED` with the handler's return value as
          `data`, if the handler returns normally.
        - `ToolStatus.FAILED`, if the handler raises any exception --
          the exception is never allowed to propagate out of this
          provider (this project's Error Handling Policy: expected
          failure surfaces must be caught and translated, not
          swallowed silently -- the exception's message is preserved
          in `ToolResult.message` and the exception itself is logged).
    """

    _NAME: str = "tool_engine"

    def provider_name(self) -> str:
        """Return this provider's stable identifier: "tool_engine"."""
        return self._NAME

    def invoke_tool(self, tool: Tool) -> ToolResult:
        """Invoke `tool.handler()` and translate the outcome into a ToolResult.

        Args:
            tool: The tool to invoke.

        Returns:
            A ToolResult with `status=COMPLETED` and the handler's
            return value as `data` on success, or `status=FAILED`
            with the exception's message if the handler raised.
        """
        try:
            data = tool.handler()
        except Exception as exc:  # noqa: BLE001 - translated, never swallowed
            logger.error(f"Tool '{tool.id}' handler raised: {exc}")
            return ToolResult(
                tool_id=tool.id,
                status=ToolStatus.FAILED,
                message=f"Tool '{tool.id}' failed: {exc}",
            )

        return ToolResult(
            tool_id=tool.id,
            status=ToolStatus.COMPLETED,
            message=f"Tool '{tool.id}' invoked successfully.",
            data=data,
        )
