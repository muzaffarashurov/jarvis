"""AutomationRule domain model for EP-035 Automation Engine.

AutomationRule bundles a reference to a `trigger_workflow_id` (an
EP-033 `WorkflowDefinition` id) with an outcome condition
(`AutomationTriggerCondition`) and a reference to an
`action_workflow_id` (another EP-033 `WorkflowDefinition` id) to run
when that condition matches. It carries the minimal runtime state
needed to report on itself (`last_triggered`, `last_action_success`)
-- mirroring EP-034's `ScheduledWorkflow`'s shape and role exactly,
one level up (a *result* trigger instead of a *time* trigger).

Both `trigger_workflow_id` and `action_workflow_id` are opaque ids
handed unchanged to `WorkflowEngine.run()` -- this module never
inspects or decomposes the referenced `WorkflowDefinition` itself,
exactly like `ScheduledWorkflow.workflow_id`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = ["AutomationTriggerCondition", "AutomationRule"]


class AutomationTriggerCondition(str, Enum):
    """The outcome of the trigger workflow's run that fires an AutomationRule.

    Attributes:
        ON_SUCCESS: Fires only when the trigger workflow's
            `WorkflowRunResult.success` is True.
        ON_FAILURE: Fires only when the trigger workflow's
            `WorkflowRunResult.success` is False.
        ON_ANY: Fires regardless of the trigger workflow's outcome.
    """

    ON_SUCCESS = "ON_SUCCESS"
    ON_FAILURE = "ON_FAILURE"
    ON_ANY = "ON_ANY"


@dataclass
class AutomationRule:
    """A single rule chaining one workflow's completion into another workflow's run.

    Attributes:
        id: Unique, stable identifier for this rule.
        name: Human-readable display name.
        description: Short description shown by `automate info`.
        trigger_workflow_id: The id of the EP-033 `WorkflowDefinition`
            whose completion this rule watches for -- forwarded
            unchanged for comparison against
            `AutomationEngine.notify_run(definition_id, ...)`, never
            interpreted by this package.
        trigger_condition: Which outcome of the trigger workflow's run
            fires this rule.
        action_workflow_id: The id of the EP-033 `WorkflowDefinition`
            to run when this rule fires -- forwarded unchanged to
            `WorkflowEngine.run(action_workflow_id)`, never
            interpreted by this package.
        enabled: Whether this rule currently participates in automatic
            evaluation (toggled by
            `AutomationEngine.enable_rule`/`disable_rule`).
        last_triggered: UTC timestamp this rule last fired, or None if
            it has never fired.
        last_action_success: Whether the most recent action-workflow
            run this rule triggered succeeded, or None if it has never
            fired.
    """

    id: str
    name: str
    description: str
    trigger_workflow_id: str
    trigger_condition: AutomationTriggerCondition
    action_workflow_id: str
    enabled: bool = True
    last_triggered: datetime | None = None
    last_action_success: bool | None = None
