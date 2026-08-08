"""In-memory registry of AutomationRule objects, for EP-035 Automation Engine.

AutomationRuleRegistry only stores and retrieves AutomationRule
objects; it performs no rule-evaluation or dispatch logic. Mirrors
EP-034's `ScheduledWorkflowRegistry`'s storage-only role and
thread-safety pattern exactly, since AutomationRule objects are
mutated in place both by the CLI thread and by whichever thread is
running the triggering workflow at the moment `notify_run()` is
called.
"""

from __future__ import annotations

from threading import Lock

from src.core.automation_engine.automation_rule import AutomationRule

__all__ = ["AutomationRuleRegistry"]


class AutomationRuleRegistry:
    """Thread-safe, in-memory store of registered AutomationRule objects, keyed by id."""

    def __init__(self) -> None:
        """Initialize an empty AutomationRuleRegistry."""
        self._entries: dict[str, AutomationRule] = {}
        self._lock = Lock()

    def register(self, entry: AutomationRule) -> None:
        """Register an automation rule.

        Args:
            entry: The AutomationRule to register.

        Raises:
            ValueError: If an entry with the same id is already registered.
        """
        with self._lock:
            if entry.id in self._entries:
                raise ValueError(f"Automation rule already registered: {entry.id}")
            self._entries[entry.id] = entry

    def unregister(self, entry_id: str) -> None:
        """Remove a registered automation rule.

        Args:
            entry_id: The id of the entry to remove.

        Raises:
            KeyError: If no entry with that id is registered.
        """
        with self._lock:
            del self._entries[entry_id]

    def get(self, entry_id: str) -> AutomationRule | None:
        """Return the entry registered under `entry_id`.

        Args:
            entry_id: The id to look up.

        Returns:
            The registered AutomationRule, or None if no such id is registered.
        """
        with self._lock:
            return self._entries.get(entry_id)

    def list(self) -> list[AutomationRule]:
        """Return all registered automation rules.

        Returns:
            A list of every currently registered AutomationRule.
        """
        with self._lock:
            return list(self._entries.values())

    def list_by_trigger(self, trigger_workflow_id: str) -> list[AutomationRule]:
        """Return every registered rule whose `trigger_workflow_id` matches.

        Args:
            trigger_workflow_id: The trigger workflow id to match against.

        Returns:
            Every registered AutomationRule (enabled or not) whose
            `trigger_workflow_id` equals `trigger_workflow_id`. Filtering
            by `enabled` is left to the caller (`AutomationEngine`).
        """
        with self._lock:
            return [
                entry
                for entry in self._entries.values()
                if entry.trigger_workflow_id == trigger_workflow_id
            ]
