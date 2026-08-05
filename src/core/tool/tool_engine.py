"""EP-031 Tool Engine.

A provider-independent engine that turns a resolved `Tool` reference
into a real invocation: looks a tool up in the `ToolManager`'s
catalog (by id, or by a `(subsystem, action)` pair), and dispatches it
to the currently selected `ToolProvider`. This is Tool Engine's entire
responsibility -- it must NOT call an AI provider, build a prompt,
plan a request, walk a Plan, or decide *which* subsystem action a
request maps to (that remains EP-029 Planning Engine's job); Tool
Engine only carries out an already-identified action (see
`src/core/tool/__init__.py`).

Depends only on public APIs:
    - `ToolManager` (this package) -- current provider and the tool
      catalog (`ToolManager.registry`), reached only through
      `ToolRegistry`'s public `get()`/`find_for_step()` methods.

No AI provider, no Planning Engine, no Plan Execution Engine, and no
private attribute of any subsystem is ever accessed here.
"""

from __future__ import annotations

from src.core.tool.tool import Tool
from src.core.tool.tool_manager import ToolManager
from src.core.tool.tool_provider import ToolError
from src.core.tool.tool_registry import ToolNotFoundError
from src.core.tool.tool_result import ToolResult, ToolStatus

__all__ = [
    "ToolEngine",
    "ToolEngineError",
    "NoToolProviderSelectedError",
    "ToolNotRegisteredError",
]


class ToolEngineError(ToolError):
    """Base class for errors raised by the ToolEngine itself.

    Inherits from `ToolError` (src/core/tool/tool_provider.py) so
    callers can catch every Tool-Engine-related failure -- provider,
    engine, or manager -- with a single exception type.
    """


class NoToolProviderSelectedError(ToolEngineError):
    """Raised when an invocation is requested but no provider is currently selected."""


class ToolNotRegisteredError(ToolEngineError):
    """Raised when `invoke()` references a tool id not in the catalog."""


class ToolEngine:
    """Provider-independent tool-lookup -> real-invocation pipeline.

    Never selects, constructs, or configures providers itself --
    provider selection and lifecycle are exclusively `ToolManager`'s
    concern. Never invokes a tool itself -- that stays inside the
    active `ToolProvider`. Never decides which tool a request maps to
    -- callers (in particular `ToolExecutionProvider`, the EP-030
    bridge) resolve that externally, by id or by `(subsystem,
    action)`.
    """

    def __init__(self, manager: ToolManager) -> None:
        """Initialize the ToolEngine.

        Args:
            manager: The ToolManager used to resolve the currently
                active provider and the registered tool catalog.
                Never mutated by this engine.
        """
        self._manager = manager

    def list_tools(self) -> list[Tool]:
        """Return every registered tool, ordered by id.

        Returns:
            The tools registered with this engine's ToolManager.
        """
        return self._manager.registry.list()

    def invoke(self, tool_id: str) -> ToolResult:
        """Invoke the tool registered under `tool_id`.

        Args:
            tool_id: The id of the tool to invoke.

        Returns:
            The resulting ToolResult.

        Raises:
            ToolNotRegisteredError: If `tool_id` is not registered.
            NoToolProviderSelectedError: If no tool provider is
                currently selected (or the subsystem is disabled).
        """
        try:
            tool = self._manager.registry.get(tool_id)
        except ToolNotFoundError as exc:
            raise ToolNotRegisteredError(str(exc)) from exc

        provider = self._require_current_provider()
        return provider.invoke_tool(tool)

    def invoke_for_step(self, subsystem: str | None, action: str) -> ToolResult:
        """Invoke whichever registered tool matches a `(subsystem, action)` pair.

        Used exclusively by `ToolExecutionProvider` (the EP-030
        bridge) to turn an already-dispatched `PlanStep` into a real
        invocation, without EP-030 ever needing to know a tool's id.

        Args:
            subsystem: The subsystem name to match (or None).
            action: The action identifier to match.

        Returns:
            A ToolResult with `status=FAILED` (never raised) if no
            registered tool matches `(subsystem, action)` -- this is a
            genuine, reachable outcome (e.g. an action EP-029's
            `DefaultPlanningProvider` can produce but for which no
            real tool has been wired yet), not an error condition the
            caller must handle specially.

        Raises:
            NoToolProviderSelectedError: If no tool provider is
                currently selected (or the subsystem is disabled).
        """
        tool = self._manager.registry.find_for_step(subsystem, action)
        if tool is None:
            subsystem_label = subsystem if subsystem is not None else "none"
            return ToolResult(
                tool_id=f"{subsystem_label}:{action}",
                status=ToolStatus.FAILED,
                message=f"No tool registered for subsystem '{subsystem_label}', action '{action}'.",
            )

        provider = self._require_current_provider()
        return provider.invoke_tool(tool)

    # ---------- Internal helpers ----------

    def _require_current_provider(self):
        """Return the currently selected provider, or raise if none is selected.

        Returns:
            The active ToolProvider.

        Raises:
            NoToolProviderSelectedError: If no tool provider is
                currently selected (or the subsystem is disabled).
        """
        provider = self._manager.get_current()
        if provider is None:
            raise NoToolProviderSelectedError(
                "No tool provider is currently selected. Use 'tool use <provider>'."
            )
        return provider
