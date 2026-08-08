"""Business logic for EP-033 Workflow Engine CLI integration.

WorkflowEngineService is a thin, CLI-facing wrapper around
WorkflowEngine and WorkflowEngineManager. It owns no dispatch logic,
no failure policy, and no catalog logic itself -- provider selection,
the stop-on-failure policy, and the definition catalog stay inside
WorkflowEngineManager; run orchestration stays inside
WorkflowEngine/WorkflowRunProvider; this service only forwards calls
to them and adapts the results to dataclasses/CommandResult for
WorkflowEngineModule, matching every other Service in this project
(see src/services/collaboration_service.py's
CollaborationService -> CollaborationEngine pattern):

    WorkflowEngineModule -> WorkflowEngineService -> WorkflowEngine -> WorkflowEngineManager

It implements no business logic belonging to any other module and
never imports from src.core.ai, src.core.planning, or
src.core.plan_execution directly (Workflow Engine must not plan or
dispatch a step itself).

EP-035 ADDITIVE HOOK NOTE: `run()` optionally invokes an
`automation_hook` callback after a run completes, so EP-035's
Automation Engine can react to on-demand runs (see
`src/core/automation_engine/__init__.py`). This class never imports
`AutomationEngine` or any EP-035 type -- the hook is a bare
`Callable[[str, WorkflowRunResult], None]`, wired in from outside
(Bootstrap) via `set_automation_hook()`. Default is None, which
reproduces this class's exact pre-EP-035 behavior. The hook is always
invoked inside a try/except that never propagates, so a defect in the
hook can never turn a successful `run()` call into a failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from loguru import logger

from src.core.workflow_engine.workflow_definition import WorkflowDefinition
from src.core.workflow_engine.workflow_engine import WorkflowEngine, WorkflowRunError
from src.core.workflow_engine.workflow_engine_manager import (
    WorkflowEngineManager,
    WorkflowRunProviderNotFoundError,
)
from src.core.workflow_engine.workflow_definition_registry import WorkflowDefinitionNotFoundError
from src.core.workflow_engine.workflow_run_provider import WorkflowRunProviderError
from src.core.workflow_engine.workflow_run_result import WorkflowRunResult
from src.core.command_router import CommandResult


@dataclass(frozen=True)
class WorkflowEngineStatus:
    """Result of `flow status`.

    Attributes:
        enabled: Whether the Workflow Engine subsystem is currently enabled.
        current_provider: The currently selected provider's name, or
            None if no provider is selected.
        stop_on_failure: Whether a run halts the remaining workflow
            after a step fails.
        registered_provider_count: Number of providers registered with
            the WorkflowEngineManager.
        registered_definition_count: Number of workflow definitions
            currently registered.
    """

    enabled: bool
    current_provider: str | None
    stop_on_failure: bool
    registered_provider_count: int
    registered_definition_count: int


@dataclass(frozen=True)
class ProviderSelectionResult:
    """Result of `flow use <provider>`.

    Attributes:
        success: Whether the provider was successfully selected.
        provider: The requested provider name.
        message: Human-readable outcome summary.
    """

    success: bool
    provider: str
    message: str


@dataclass(frozen=True)
class WorkflowRunOutcome:
    """Result of `flow run <id>`.

    Attributes:
        success: Whether the run completed without an
            infrastructure-level error (this is independent of whether
            every step itself succeeded -- see `WorkflowRunResult.success`
            for that).
        definition_id: The requested definition id.
        result: The resulting WorkflowRunResult, or None on
            infrastructure failure.
        error: Human-readable error message, or "" on success.
    """

    success: bool
    definition_id: str
    result: WorkflowRunResult | None
    error: str


class WorkflowEngineService:
    """Coordinates WorkflowEngine/WorkflowEngineManager as a CLI-friendly API.

    Depends only on WorkflowEngine and WorkflowEngineManager (EP-033).
    Implements no dispatch logic of its own -- every call is forwarded
    unchanged; this class only adapts return values to
    dataclasses/CommandResult for WorkflowEngineModule.
    """

    def __init__(self, manager: WorkflowEngineManager, engine: WorkflowEngine) -> None:
        """Initialize the WorkflowEngineService.

        Args:
            manager: The WorkflowEngineManager this service reports on
                and selects providers through.
            engine: The WorkflowEngine this service requests workflow
                runs through.
        """
        self._manager = manager
        self._engine = engine
        self._automation_hook: Callable[[str, WorkflowRunResult], None] | None = None

    def set_automation_hook(
        self, hook: Callable[[str, WorkflowRunResult], None] | None
    ) -> None:
        """Wire (or clear) the optional EP-035 automation hook.

        Args:
            hook: Called as `hook(definition_id, result)` immediately
                after `run()` produces a `WorkflowRunResult`, or None
                to remove any previously wired hook (this class's
                default, and its exact pre-EP-035 behavior). Never
                called for an infrastructure-level run failure (i.e.
                only when a `WorkflowRunResult` actually exists).
        """
        self._automation_hook = hook

    def status(self) -> WorkflowEngineStatus:
        """Return the Workflow Engine subsystem's overall status."""
        return WorkflowEngineStatus(
            enabled=self._manager.is_enabled(),
            current_provider=self._manager.current_provider_name(),
            stop_on_failure=self._manager.stop_on_failure(),
            registered_provider_count=len(self._manager.list_providers()),
            registered_definition_count=len(self._engine.list_definitions()),
        )

    def list_definitions(self) -> list[WorkflowDefinition]:
        """List every workflow definition currently registered."""
        return self._engine.list_definitions()

    def get_definition(self, definition_id: str) -> WorkflowDefinition | None:
        """Return a single registered workflow definition, or None if unknown.

        Args:
            definition_id: The id of the definition to look up.
        """
        try:
            return self._manager.registry.get(definition_id)
        except WorkflowDefinitionNotFoundError:
            return None

    def use_provider(self, name: str) -> ProviderSelectionResult:
        """Select a workflow-run provider as the currently active provider.

        Args:
            name: The registered provider name to activate.

        Returns:
            A ProviderSelectionResult reflecting whether `name` was selected.
        """
        try:
            self._manager.set_current(name)
        except WorkflowRunProviderNotFoundError as exc:
            return ProviderSelectionResult(success=False, provider=name, message=str(exc))

        return ProviderSelectionResult(
            success=True, provider=name, message=f"Workflow-run provider set to '{name}'."
        )

    def disable(self) -> CommandResult:
        """Disable the Workflow Engine subsystem."""
        self._manager.disable()
        return CommandResult(success=True, message="Workflow Engine subsystem disabled.")

    def run(self, definition_id: str) -> WorkflowRunOutcome:
        """Run an already-registered workflow definition by id.

        Args:
            definition_id: The id of the workflow definition to run.

        Returns:
            A WorkflowRunOutcome describing the outcome.
        """
        try:
            result = self._engine.run(definition_id)
        except (WorkflowRunError, WorkflowRunProviderError, WorkflowDefinitionNotFoundError) as exc:
            logger.error(f"Workflow Engine run failed: {exc}")
            return WorkflowRunOutcome(
                success=False, definition_id=definition_id, result=None, error=str(exc)
            )

        if self._automation_hook is not None:
            try:
                self._automation_hook(definition_id, result)
            except Exception as exc:  # noqa: BLE001 - a hook defect must never break this run's result
                logger.error(f"Automation hook failed for workflow '{definition_id}': {exc}")

        return WorkflowRunOutcome(success=True, definition_id=definition_id, result=result, error="")
