"""AutomationEngine: EP-035 outcome-triggered workflow chaining.

Architecture (mirroring EP-034's task brief for `WorkflowSchedulerEngine`,
one level up):

    AutomationService -> AutomationEngine -> AutomationRuleRegistry -> WorkflowEngine

AutomationEngine contains no business logic of its own beyond matching
an already-completed run against registered rules. It never decides
*when* the trigger workflow runs (that stays EP-033's `WorkflowEngine`
via `WorkflowEngineService`, or EP-034's `WorkflowSchedulerEngine` --
this engine is only ever notified *after* the fact, through
`notify_run()`). Dispatching a matched rule's action workflow always
delegates to the shared, unmodified EP-033 `WorkflowEngine`, through
its public `run(workflow_id)` method only -- never `PlanningEngine` or
`PlanExecutionEngine` directly.

`notify_run()` is deliberately single-hop: it calls
`self._workflow_engine.run(action_workflow_id)` directly, bypassing
the automation hook entirely, so an action workflow's own completion
never re-enters `notify_run()`. There is no recursive chaining and no
cycle detection, because recursive chaining itself is out of EP-035's
scope (A -> B is supported; A -> B -> C is not).

`notify_run()` must never propagate a failure -- neither an exception
raised while matching/dispatching, nor an action workflow's own
failed run -- back to its caller. Callers (`WorkflowEngineService.run()`,
`WorkflowSchedulerEngine.run_now()`) invoke this method, if wired at
all, strictly *after* they already have their own result to return;
an Automation Engine defect must never turn a successful triggering
run into a reported failure.
"""

from __future__ import annotations

from datetime import datetime, timezone

from loguru import logger

from src.core.automation_engine.automation_rule import AutomationRule, AutomationTriggerCondition
from src.core.automation_engine.automation_rule_registry import AutomationRuleRegistry
from src.core.workflow_engine.workflow_engine import WorkflowEngine
from src.core.workflow_engine.workflow_run_provider import WorkflowEngineError
from src.core.workflow_engine.workflow_run_result import WorkflowRunResult

__all__ = ["AutomationEngine", "AutomationError"]


class AutomationError(Exception):
    """Raised for invalid automation-engine operations.

    Covers the same cases as EP-034's `WorkflowSchedulerError`: unknown
    rule and duplicate rule. ("Automation Engine stopped" is reported
    by `AutomationService`, the layer that owns configuration; a failed
    action-workflow run is reported via `AutomationRule.last_action_success`
    rather than raised, matching `WorkflowSchedulerEngine.run_now()`'s
    convention.)
    """


class AutomationEngine:
    """Matches a completed workflow run against registered rules and dispatches action workflows.

    Responsibilities (mirroring EP-034's `WorkflowSchedulerEngine`):
    register_rule, remove_rule, enable_rule, disable_rule, list_rules,
    get_rule, notify_run. `notify_run()` is the reactive entry point
    driven by `WorkflowEngineService`/`WorkflowSchedulerEngine`'s
    optional `automation_hook`.
    """

    def __init__(self, registry: AutomationRuleRegistry, workflow_engine: WorkflowEngine) -> None:
        """Initialize the AutomationEngine.

        Args:
            registry: Storage for all known AutomationRule objects.
            workflow_engine: The EP-033 WorkflowEngine used to actually
                run a matched rule's action workflow, through its
                public `run()` method only.
        """
        self._registry = registry
        self._workflow_engine = workflow_engine

    # ---------- Public API ----------

    def register_rule(self, rule: AutomationRule) -> None:
        """Register a new automation rule.

        Args:
            rule: The AutomationRule to register.

        Raises:
            AutomationError: If a rule with the same id is already registered.
        """
        try:
            self._registry.register(rule)
        except ValueError as exc:
            raise AutomationError(str(exc)) from exc
        logger.info(f"Automation rule registered: '{rule.id}'.")

    def remove_rule(self, rule_id: str) -> None:
        """Remove a registered automation rule.

        Args:
            rule_id: The id of the rule to remove.

        Raises:
            AutomationError: If no rule with that id is registered.
        """
        try:
            self._registry.unregister(rule_id)
        except KeyError as exc:
            raise AutomationError(f"Unknown automation rule: '{rule_id}'.") from exc
        logger.info(f"Automation rule removed: '{rule_id}'.")

    def enable_rule(self, rule_id: str) -> AutomationRule:
        """Enable a registered automation rule.

        Args:
            rule_id: The id of the rule to enable.

        Returns:
            The updated AutomationRule.

        Raises:
            AutomationError: If the rule is unknown.
        """
        rule = self._require_rule(rule_id)
        rule.enabled = True
        logger.info(f"Automation rule enabled: '{rule_id}'.")
        return rule

    def disable_rule(self, rule_id: str) -> AutomationRule:
        """Disable a registered automation rule.

        Args:
            rule_id: The id of the rule to disable.

        Returns:
            The updated AutomationRule.

        Raises:
            AutomationError: If the rule is unknown.
        """
        rule = self._require_rule(rule_id)
        rule.enabled = False
        logger.info(f"Automation rule disabled: '{rule_id}'.")
        return rule

    def list_rules(self) -> list[AutomationRule]:
        """Return all registered automation rules."""
        return self._registry.list()

    def get_rule(self, rule_id: str) -> AutomationRule | None:
        """Return the rule registered under `rule_id`, or None."""
        return self._registry.get(rule_id)

    def notify_run(self, definition_id: str, result: WorkflowRunResult) -> list[AutomationRule]:
        """Evaluate and dispatch every enabled rule matching a just-completed workflow run.

        This is the reactive hook entry point: it is intended to be
        called (via `WorkflowEngineService`/`WorkflowSchedulerEngine`'s
        optional `automation_hook`) once, synchronously, immediately
        after a workflow run has already produced its result. It never
        raises -- a defect here must never break the run that just
        completed.

        Single-hop only: this method calls `WorkflowEngine.run()`
        directly for each matched rule's `action_workflow_id`,
        bypassing the automation hook entirely, so the action
        workflow's own completion never re-enters this method. No
        rule triggered by an action-workflow's completion will ever
        fire as a result of this call.

        Args:
            definition_id: The id of the WorkflowDefinition that just
                finished running.
            result: The WorkflowRunResult that run produced.

        Returns:
            The AutomationRule objects that were triggered by this
            call (i.e. matched and had their action workflow
            dispatched), in registry order. Always returns normally,
            even if matching or dispatch raises internally.
        """
        triggered: list[AutomationRule] = []
        try:
            candidates = [
                rule
                for rule in self._registry.list_by_trigger(definition_id)
                if rule.enabled and self._condition_matches(rule.trigger_condition, result.success)
            ]
        except Exception as exc:  # noqa: BLE001 - notify_run must never propagate a failure
            logger.error(f"Automation Engine rule matching failed: {exc}")
            return triggered

        for rule in candidates:
            try:
                self._trigger(rule)
                triggered.append(rule)
            except Exception as exc:  # noqa: BLE001 - one rule's failure must not stop the others
                logger.error(f"Automation Engine rule dispatch failed for '{rule.id}': {exc}")

        return triggered

    # ---------- Internal helpers ----------

    def _require_rule(self, rule_id: str) -> AutomationRule:
        """Return the rule for `rule_id`, or raise AutomationError if unknown."""
        rule = self._registry.get(rule_id)
        if rule is None:
            raise AutomationError(f"Unknown automation rule: '{rule_id}'.")
        return rule

    @staticmethod
    def _condition_matches(condition: AutomationTriggerCondition, trigger_success: bool) -> bool:
        """Return whether `condition` matches the trigger workflow's outcome."""
        if condition == AutomationTriggerCondition.ON_ANY:
            return True
        if condition == AutomationTriggerCondition.ON_SUCCESS:
            return trigger_success
        if condition == AutomationTriggerCondition.ON_FAILURE:
            return not trigger_success
        return False

    def _trigger(self, rule: AutomationRule) -> None:
        """Run `rule`'s action workflow and record the outcome on the rule.

        Never raises: an `WorkflowEngineError` from the action
        workflow's run is caught and recorded as
        `last_action_success = False`, exactly like
        `WorkflowSchedulerEngine.run_now()`'s failure handling.
        """
        try:
            action_result = self._workflow_engine.run(rule.action_workflow_id)
            success = action_result.success
        except WorkflowEngineError as exc:
            success = False
            logger.error(
                f"Automation rule '{rule.id}' action workflow "
                f"'{rule.action_workflow_id}' failed: {exc}"
            )

        rule.last_triggered = datetime.now(timezone.utc)
        rule.last_action_success = success

        if success:
            logger.info(f"Automation rule triggered: '{rule.id}' -> '{rule.action_workflow_id}'.")
        else:
            logger.error(
                f"Automation rule '{rule.id}' triggered but action workflow "
                f"'{rule.action_workflow_id}' did not succeed."
            )
