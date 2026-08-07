"""Catalog registry for EP-033 Workflow Engine.

WorkflowDefinitionRegistry stores `WorkflowDefinition` catalog entries
and performs no execution of its own -- that responsibility belongs to
`WorkflowEngine`/`WorkflowRunProvider`. This mirrors `ToolRegistry`'s
role for the Tool catalog (`src/core/tool/tool_registry.py`),
`PluginRegistry`'s role for the Plugin catalog, and `ProcessRegistry`'s
role for the Process Catalog. Deliberately named apart from EP-007's
`WorkflowRegistry` (`src/core/workflows/workflow_registry.py`) -- see
`src/core/workflow_engine/__init__.py` for the disambiguation note.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.workflow_engine.workflow_definition import WorkflowDefinition
from src.core.workflow_engine.workflow_run_provider import WorkflowEngineError

__all__ = [
    "WorkflowDefinitionRegistry",
    "WorkflowDefinitionRegistryError",
    "WorkflowDefinitionNotFoundError",
]


class WorkflowDefinitionRegistryError(WorkflowEngineError):
    """Raised for invalid catalog operations (e.g. duplicate definition id)."""


class WorkflowDefinitionNotFoundError(WorkflowEngineError):
    """Raised when an operation references a definition id not in the catalog."""


class WorkflowDefinitionRegistry:
    """Thread-safe catalog of workflow definitions known to Workflow Engine.

    Responsibilities:
        - Register a definition in the catalog.
        - Unregister a definition from the catalog.
        - Return a single registered definition, raising if unknown.
        - List all registered definitions.
    """

    def __init__(self) -> None:
        """Initialize an empty WorkflowDefinitionRegistry."""
        self._definitions: dict[str, WorkflowDefinition] = {}
        self._lock = Lock()

    def register(self, definition: WorkflowDefinition) -> None:
        """Register a workflow definition in the catalog.

        Args:
            definition: The WorkflowDefinition to add.

        Raises:
            WorkflowDefinitionRegistryError: If a definition with the
                same id is already registered.
        """
        with self._lock:
            if definition.id in self._definitions:
                raise WorkflowDefinitionRegistryError(
                    f"Workflow definition already registered: '{definition.id}'."
                )
            self._definitions[definition.id] = definition
        logger.info(f"Workflow definition registered: '{definition.id}'.")

    def unregister(self, definition_id: str) -> None:
        """Remove a workflow definition from the catalog.

        Args:
            definition_id: The id of the definition to remove.

        Raises:
            WorkflowDefinitionNotFoundError: If `definition_id` is not registered.
        """
        with self._lock:
            if definition_id not in self._definitions:
                raise WorkflowDefinitionNotFoundError(
                    f"Unknown workflow definition: '{definition_id}'."
                )
            del self._definitions[definition_id]
        logger.info(f"Workflow definition unregistered: '{definition_id}'.")

    def get(self, definition_id: str) -> WorkflowDefinition:
        """Return a single registered workflow definition.

        Args:
            definition_id: The id of the definition to look up.

        Returns:
            The matching WorkflowDefinition.

        Raises:
            WorkflowDefinitionNotFoundError: If `definition_id` is not registered.
        """
        with self._lock:
            definition = self._definitions.get(definition_id)
        if definition is None:
            raise WorkflowDefinitionNotFoundError(f"Unknown workflow definition: '{definition_id}'.")
        return definition

    def list(self) -> list[WorkflowDefinition]:
        """Return every registered workflow definition, ordered by id.

        Returns:
            A list of WorkflowDefinition entries sorted by id.
        """
        with self._lock:
            return sorted(self._definitions.values(), key=lambda definition: definition.id)

    def is_registered(self, definition_id: str) -> bool:
        """Return whether a workflow definition id is currently registered.

        Args:
            definition_id: The id to check.

        Returns:
            True if a definition with this id exists in the catalog.
        """
        with self._lock:
            return definition_id in self._definitions
