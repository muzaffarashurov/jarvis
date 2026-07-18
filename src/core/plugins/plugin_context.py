"""Shared-service context handed to plugin instances at initialization.

PluginContext is the only object a plugin ever receives (see EP-009's
"Important Design Rules": "Plugins receive only PluginContext.").
It exposes references to already-existing, shared infrastructure
components. It implements no business logic of its own and performs
no execution, per EP-009's "Plugin Context" requirements ("Do NOT
expose business logic.").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.core.config import Config
from src.core.execution.engine import ExecutionEngine

if TYPE_CHECKING:
    from src.services.process_service import ProcessService
    from src.services.workflow_service import WorkflowService


@dataclass
class PluginContext:
    """Shared services made available to every loaded plugin.

    Attributes:
        config: The loaded application configuration.
        logger: The application-wide Loguru logger (the same object
            imported elsewhere in this project via
            `from loguru import logger`). Typed as `Any` here since
            Loguru's `Logger` class is not part of its public
            re-exported API surface.
        execution_engine: Shared ExecutionEngine for launching raw
            OS-level targets (files, URLs, processes).
        workflow_service: The existing WorkflowService, if wired into
            the running application, or None.

            TODO:
            No component currently instantiates WorkflowService in
            src/bootstrap.py -- see that module's own docstring for
            the documented architecture gap (ExecutionEngine cannot
            dispatch named module actions, and WorkflowService must
            not call modules directly). Per the Unknown API Policy,
            this context does not fabricate a WorkflowService here;
            it is passed through as None until bootstrap.py is
            explicitly asked to wire one in.
        process_service: The existing ProcessService coordinating the
            Process Catalog (EP-008), or None if unavailable.
        shared_resources: A plain, plugin-owned key/value store for
            cross-plugin state. Jarvis places nothing here itself.
    """

    config: Config
    logger: Any
    execution_engine: ExecutionEngine
    workflow_service: "WorkflowService | None" = None
    process_service: "ProcessService | None" = None
    shared_resources: dict[str, Any] = field(default_factory=dict)

    def get_shared_resource(self, key: str) -> Any | None:
        """Return a value from `shared_resources`, or None if absent.

        Args:
            key: The shared resource key.

        Returns:
            The stored value, or None if `key` has not been set.
        """
        return self.shared_resources.get(key)

    def set_shared_resource(self, key: str, value: Any) -> None:
        """Store a value in `shared_resources` for other plugins to read.

        Args:
            key: The shared resource key.
            value: The value to store.
        """
        self.shared_resources[key] = value
