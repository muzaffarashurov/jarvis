"""Catalog registry for EP-031 Tool Engine.

ToolRegistry stores `Tool` catalog entries and performs no invocation
of its own -- that responsibility belongs to `ToolProvider`. This
mirrors `PluginRegistry`'s role for the Plugin catalog (see
`src/core/plugins/plugin_registry.py`) and `ProcessRegistry`'s role
for the Process Catalog (see `src/core/processes/process_registry.py`).
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.tool.tool import Tool


class ToolRegistryError(Exception):
    """Raised for invalid catalog operations (e.g. duplicate tool id)."""


class ToolNotFoundError(Exception):
    """Raised when an operation references a tool id not in the catalog."""


class ToolRegistry:
    """Thread-safe catalog of tools known to Tool Engine.

    Responsibilities:
        - Register a tool in the catalog.
        - Unregister a tool from the catalog.
        - Return a single registered tool, raising if unknown.
        - Find a single registered tool without raising.
        - Find a tool by its (subsystem, action) pair, without raising.
        - List all registered tools.
    """

    def __init__(self) -> None:
        """Initialize an empty ToolRegistry."""
        self._tools: dict[str, Tool] = {}
        self._lock = Lock()

    def register(self, tool: Tool) -> None:
        """Register a tool in the catalog.

        Args:
            tool: The Tool to add.

        Raises:
            ToolRegistryError: If a tool with the same id is already
                registered.
        """
        with self._lock:
            if tool.id in self._tools:
                raise ToolRegistryError(f"Tool already registered: '{tool.id}'.")
            self._tools[tool.id] = tool
        logger.info(f"Tool registered: '{tool.id}'.")

    def unregister(self, tool_id: str) -> None:
        """Remove a tool from the catalog.

        Args:
            tool_id: The id of the tool to remove.

        Raises:
            ToolNotFoundError: If `tool_id` is not registered.
        """
        with self._lock:
            if tool_id not in self._tools:
                raise ToolNotFoundError(f"Unknown tool: '{tool_id}'.")
            del self._tools[tool_id]
        logger.info(f"Tool unregistered: '{tool_id}'.")

    def get(self, tool_id: str) -> Tool:
        """Return a single registered tool.

        Args:
            tool_id: The id of the tool to look up.

        Returns:
            The matching Tool.

        Raises:
            ToolNotFoundError: If `tool_id` is not registered.
        """
        tool = self.find(tool_id)
        if tool is None:
            raise ToolNotFoundError(f"Unknown tool: '{tool_id}'.")
        return tool

    def find(self, tool_id: str) -> Tool | None:
        """Return the catalog entry for a tool id, if registered.

        Args:
            tool_id: The id of the tool to find.

        Returns:
            The Tool, or None if not registered.
        """
        with self._lock:
            return self._tools.get(tool_id)

    def find_for_step(self, subsystem: str | None, action: str) -> Tool | None:
        """Return the first registered, enabled tool matching a (subsystem, action) pair.

        Used exclusively by `ToolExecutionProvider` (the EP-030
        bridge) to resolve which tool -- if any -- satisfies a given
        `PlanStep`'s `subsystem`/`action` fields.

        Args:
            subsystem: The subsystem name to match (or None).
            action: The action identifier to match.

        Returns:
            The first matching, enabled Tool ordered by id, or None
            if no registered tool matches.
        """
        with self._lock:
            candidates = [
                tool
                for tool in self._tools.values()
                if tool.enabled and tool.subsystem == subsystem and tool.action == action
            ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda tool: tool.id)[0]

    def list(self) -> list[Tool]:
        """Return every registered tool, ordered by id.

        Returns:
            A list of Tool entries sorted by id.
        """
        with self._lock:
            return sorted(self._tools.values(), key=lambda tool: tool.id)

    def is_registered(self, tool_id: str) -> bool:
        """Return whether a tool id is currently registered.

        Args:
            tool_id: The id to check.

        Returns:
            True if a tool with this id exists in the catalog.
        """
        with self._lock:
            return tool_id in self._tools
