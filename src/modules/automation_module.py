"""Automation module: CLI command surface for EP-035 Automation Engine.

Exposes the "automate" command namespace (list, status, info, enable,
stop, help) as thin CommandModule handlers, following the same
pattern as WorkflowEngineModule/WorkflowSchedulerModule. All
orchestration logic lives in AutomationService; this module only
formats CommandResult objects for the shell.

No "register" or "run"/"trigger" command is exposed via CLI, matching
EP-033's WorkflowEngineModule and EP-034's WorkflowSchedulerModule
precedent for "register" -- rules are registered only through the
public `AutomationService.register()` API (e.g. at Bootstrap). There
is also deliberately no manual trigger command: a rule only ever
fires reactively, through `AutomationEngine.notify_run()`, when its
trigger workflow actually completes.
"""

from __future__ import annotations

from typing import Callable

from src.core.automation_engine.automation_rule import AutomationRule
from src.core.command_router import CommandResult
from src.services.automation_service import AutomationService, AutomationStatus

HELP_TEXT: str = (
    "Available commands\n\n"
    "automate list\n"
    "automate status\n"
    "automate info <id>\n"
    "automate enable <id>\n"
    "automate stop <id>\n"
    "automate help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class AutomationModule:
    """Built-in "automate" command namespace for Automation Engine."""

    def __init__(self, automation_service: AutomationService) -> None:
        """Initialize the AutomationModule.

        Args:
            automation_service: The service used to list, inspect,
                enable, and disable automation rules.
        """
        self._service = automation_service
        self._actions: dict[str, ActionHandler] = {
            "list": self._list,
            "status": self._status,
            "info": self._info,
            "enable": self._enable,
            "stop": self._stop,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "automate"."""
        return "automate"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute an "automate" action.

        Args:
            action: The requested action (e.g. "list").
            arguments: Additional arguments (e.g. an automation rule id).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "automate help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available automate commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _list(self, arguments: list[str]) -> CommandResult:
        """List all registered automation rules."""
        rules: list[AutomationRule] = self._service.list_rules()
        if not rules:
            return CommandResult(success=True, message="Automation Rules\n\n(none registered)")

        lines = ["Automation Rules"]
        for rule in rules:
            state = "enabled" if rule.enabled else "disabled"
            lines.append(
                f"{rule.id} : {rule.name} -> {rule.trigger_workflow_id} "
                f"({rule.trigger_condition.value}) => {rule.action_workflow_id} ({state})"
            )
        return CommandResult(success=True, message="\n\n".join(lines))

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the automation engine's overall status."""
        status: AutomationStatus = self._service.status()
        lines = [
            "Automation Engine Status",
            f"Enabled : {'YES' if status.enabled else 'NO'}",
            f"Rules registered : {status.rules_registered}",
            f"Rules enabled : {status.rules_enabled}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    def _enable(self, arguments: list[str]) -> CommandResult:
        """Enable a registered automation rule."""
        rule_id = self._require_rule_id(arguments)
        if rule_id is None:
            return CommandResult(success=False, message="Usage: automate enable <id>")
        return self._service.enable(rule_id)

    def _stop(self, arguments: list[str]) -> CommandResult:
        """Disable a registered automation rule."""
        rule_id = self._require_rule_id(arguments)
        if rule_id is None:
            return CommandResult(success=False, message="Usage: automate stop <id>")
        return self._service.disable(rule_id)

    def _info(self, arguments: list[str]) -> CommandResult:
        """Display name, status, trigger, action, and last-run outcome."""
        rule_id = self._require_rule_id(arguments)
        if rule_id is None:
            return CommandResult(success=False, message="Usage: automate info <id>")

        rule = self._service.get_rule(rule_id)
        if rule is None:
            return CommandResult(success=False, message=f"Automation rule not found: {rule_id}")

        if rule.last_action_success is None:
            last_action = "never triggered"
        elif rule.last_action_success:
            last_action = "succeeded"
        else:
            last_action = "failed"

        pairs = (
            ("Name", rule.name),
            ("Trigger Workflow", rule.trigger_workflow_id),
            ("Condition", rule.trigger_condition.value),
            ("Action Workflow", rule.action_workflow_id),
            ("Enabled", "yes" if rule.enabled else "no"),
            ("Last Triggered", rule.last_triggered.isoformat() if rule.last_triggered else "never"),
            ("Last Action Result", last_action),
            ("Description", rule.description),
        )
        message = "\n\n".join(f"{label}\n\n{value}" for label, value in pairs)
        return CommandResult(success=True, message=message)

    @staticmethod
    def _require_rule_id(arguments: list[str]) -> str | None:
        """Return the automation rule id from arguments, or None if missing."""
        if not arguments:
            return None
        return arguments[0]
