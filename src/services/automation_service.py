"""Business logic that coordinates EP-035 Automation Engine.

AutomationService implements no rule-evaluation or dispatch logic of
its own; it depends only on `AutomationEngine`, matching EP-035's
architecture:

    AutomationModule -> AutomationService -> AutomationEngine -> AutomationRuleRegistry -> WorkflowEngine

Unlike EP-034's `WorkflowSchedulerService`, AutomationService owns no
background thread: EP-035 is purely reactive (rules only fire in
response to `AutomationEngine.notify_run()`, driven by another EP's
own execution path), so there is no tick loop to start, stop, or
track here. This service only owns 'automation.enabled' and adapts
`AutomationEngine`'s return values to `CommandResult`/status
dataclasses for `AutomationModule`.
"""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.automation_engine.automation_engine import AutomationEngine, AutomationError
from src.core.automation_engine.automation_rule import AutomationRule
from src.core.command_router import CommandResult
from src.core.config import Config


@dataclass(frozen=True)
class AutomationStatus:
    """Result of `automate status`.

    Attributes:
        enabled: Whether the Automation Engine subsystem is currently enabled.
        rules_registered: Number of automation rules currently registered.
        rules_enabled: Number of registered rules currently enabled.
    """

    enabled: bool
    rules_registered: int
    rules_enabled: int


class AutomationService:
    """Coordinates AutomationEngine as a CLI-friendly API.

    Depends only on AutomationEngine (rule storage and dispatch) and
    Config (its own 'automation.*' settings). Implements no business
    logic of its own.
    """

    def __init__(self, config: Config, engine: AutomationEngine) -> None:
        """Initialize the AutomationService.

        Args:
            config: Loaded application configuration, used to resolve
                'automation.enabled'.
            engine: The AutomationEngine used to register, inspect,
                enable, and disable automation rules.
        """
        self._config = config
        self._engine = engine

    # ---------- Public API ----------

    def register(self, rule: AutomationRule) -> CommandResult:
        """Register a new automation rule."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            self._engine.register_rule(rule)
        except AutomationError as exc:
            logger.error(f"Automation rule registration failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Automation rule '{rule.id}' registered.")

    def unregister(self, rule_id: str) -> CommandResult:
        """Remove a registered automation rule."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        try:
            self._engine.remove_rule(rule_id)
        except AutomationError as exc:
            logger.error(f"Automation rule removal failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Automation rule '{rule_id}' removed.")

    def enable(self, rule_id: str) -> CommandResult:
        """Enable a registered automation rule."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        rule = self._engine.get_rule(rule_id)
        if rule is None:
            message = f"Unknown automation rule: '{rule_id}'."
            logger.error(f"Automation rule enable failed: {message}")
            return CommandResult(success=False, message=message)

        if rule.enabled:
            return CommandResult(success=True, message="Automation rule already enabled.")

        try:
            self._engine.enable_rule(rule_id)
        except AutomationError as exc:
            logger.error(f"Automation rule enable failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Automation rule '{rule_id}' enabled.")

    def disable(self, rule_id: str) -> CommandResult:
        """Disable a registered automation rule."""
        disabled = self._ensure_enabled()
        if disabled is not None:
            return disabled

        rule = self._engine.get_rule(rule_id)
        if rule is None:
            message = f"Unknown automation rule: '{rule_id}'."
            logger.error(f"Automation rule disable failed: {message}")
            return CommandResult(success=False, message=message)

        if not rule.enabled:
            return CommandResult(success=True, message="Automation rule already disabled.")

        try:
            self._engine.disable_rule(rule_id)
        except AutomationError as exc:
            logger.error(f"Automation rule disable failed: {exc}")
            return CommandResult(success=False, message=str(exc))
        return CommandResult(success=True, message=f"Automation rule '{rule_id}' disabled.")

    def list_rules(self) -> list[AutomationRule]:
        """Return all registered automation rules."""
        return self._engine.list_rules()

    def get_rule(self, rule_id: str) -> AutomationRule | None:
        """Return the automation rule registered under `rule_id`, or None."""
        return self._engine.get_rule(rule_id)

    def status(self) -> AutomationStatus:
        """Return the `automate status` snapshot."""
        rules = self._engine.list_rules()
        return AutomationStatus(
            enabled=bool(self._config.get("automation.enabled", True)),
            rules_registered=len(rules),
            rules_enabled=sum(1 for rule in rules if rule.enabled),
        )

    # ---------- Internal helpers ----------

    def _ensure_enabled(self) -> CommandResult | None:
        """Return an "Automation Engine stopped" failure if automation is disabled.

        Returns:
            A failing CommandResult if 'automation.enabled' is False,
            otherwise None (meaning the caller may proceed).
        """
        if bool(self._config.get("automation.enabled", True)):
            return None
        logger.error("Automation Engine operation rejected: Automation Engine stopped.")
        return CommandResult(success=False, message="Automation Engine stopped.")
