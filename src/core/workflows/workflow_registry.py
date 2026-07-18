"""In-memory registry of Workflow objects.

WorkflowRegistry only stores and retrieves Workflow objects; it
performs no execution and no business validation beyond rejecting
duplicate ids. This mirrors ProcessRegistry's role for ExecutionEngine
(see src/core/execution/process_registry.py): a plain storage
component with a single responsibility.
"""

from __future__ import annotations

from src.core.workflows.workflow import Workflow


class WorkflowRegistry:
    """Stores registered Workflow objects, keyed by workflow id."""

    def __init__(self) -> None:
        """Initialize an empty WorkflowRegistry."""
        self._workflows: dict[str, Workflow] = {}

    def register(self, workflow: Workflow) -> None:
        """Register a workflow.

        Args:
            workflow: The Workflow to register.

        Raises:
            ValueError: If a workflow with the same id is already
                registered.
        """
        if workflow.id in self._workflows:
            raise ValueError(f"Workflow already registered: {workflow.id}")
        self._workflows[workflow.id] = workflow

    def unregister(self, workflow_id: str) -> None:
        """Remove a registered workflow.

        Args:
            workflow_id: The id of the workflow to remove.

        Raises:
            KeyError: If no workflow with that id is registered.
        """
        del self._workflows[workflow_id]

    def get(self, workflow_id: str) -> Workflow | None:
        """Return the workflow registered under `workflow_id`.

        Args:
            workflow_id: The id to look up.

        Returns:
            The registered Workflow, or None if no such id is registered.
        """
        return self._workflows.get(workflow_id)

    def list(self) -> list[Workflow]:
        """Return all registered workflows.

        Returns:
            A list of every currently registered Workflow.
        """
        return list(self._workflows.values())
