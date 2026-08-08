"""EP-035 Automation Engine.

Chains one EP-033 `WorkflowDefinition`'s completion (whether started
on-demand through `WorkflowEngineService.run()`, or automatically
through EP-034's `WorkflowSchedulerEngine.run_now()`/`tick()`) into a
run of a second `WorkflowDefinition`, based on the first run's
outcome (`ON_SUCCESS` / `ON_FAILURE` / `ON_ANY`), by calling EP-033's
already-existing `WorkflowEngine.run(workflow_id)` exclusively. This
package performs no AI reasoning, no scheduling of its own, and no
direct subsystem/tool invocation -- it only reacts, synchronously and
single-hop, to an already-completed EP's public API result, exactly
the way EP-034 only decided *when* to call an already-completed EP's
public API again.

This package is intentionally reactive, not proactive: it never polls,
never owns a background thread, and never decides that a workflow
should run -- it is only ever told, after the fact, that one already
did (via `AutomationEngine.notify_run()`, wired as an optional hook
into `WorkflowEngineService`/`WorkflowSchedulerEngine`, both of which
remain unaware this package exists -- see those modules' own
docstrings for the hook contract).

SINGLE-HOP ONLY (read before touching this package): `notify_run()`
dispatches a matched rule's action workflow by calling
`WorkflowEngine.run()` directly, bypassing the automation hook
entirely. An action workflow's own completion therefore never
re-enters `notify_run()` -- there is no A -> B -> C chaining and no
cycle detection, because recursive chaining is explicitly out of
EP-035's scope. Do not wire the hook into `AutomationEngine` itself.

NAMING NOTE: `AutomationRule`/`AutomationRuleRegistry`/`AutomationEngine`
deliberately do not reuse EP-034's `ScheduledWorkflow`/
`ScheduledWorkflowRegistry`/`WorkflowSchedulerEngine` types --  an
automation rule is not a schedulable entry (it carries no `Schedule`,
`next_run`, or tick participation) and a `ScheduledWorkflow` is not an
automation rule (it carries no trigger condition or action workflow).
Mirroring EP-034's own precedent, this is a new, independent set of
types one layer up, not a reuse of EP-034's.

`AutomationRule`/`AutomationTriggerCondition` (`automation_rule.py`)
are the plain domain types a rule is built from.
`AutomationRuleRegistry` (`automation_rule_registry.py`) is the
in-memory, thread-safe catalog of registered rules. `AutomationEngine`
(`automation_engine.py`) is the engine that matches a just-completed
run against registered rules and dispatches each match's action
workflow through EP-033's `WorkflowEngine`, its only cross-EP
dependency, reached through `run()` only.

No separate Provider/Manager layer exists in this package: there is
exactly one way to evaluate a rule and exactly one way to dispatch a
matched rule, so a swappable provider abstraction with only one
implementation would be speculative rather than justified by an
actual second strategy -- consistent with this project's Unknown API
Policy, and matching EP-034's own `WorkflowSchedulerEngine`, which
likewise has no Provider layer.

Public API:
    AutomationTriggerCondition -- Which outcome of the trigger workflow fires a rule.
    AutomationRule -- A single rule chaining one workflow's completion into another's run.
    AutomationRuleRegistry -- In-memory, thread-safe catalog of automation rules.
    AutomationEngine -- Matches a completed run against rules and dispatches action workflows.
    AutomationError -- Raised for invalid automation-engine operations.
"""

from __future__ import annotations

from src.core.automation_engine.automation_engine import AutomationEngine, AutomationError
from src.core.automation_engine.automation_rule import AutomationRule, AutomationTriggerCondition
from src.core.automation_engine.automation_rule_registry import AutomationRuleRegistry

__all__ = [
    "AutomationTriggerCondition",
    "AutomationRule",
    "AutomationRuleRegistry",
    "AutomationEngine",
    "AutomationError",
]
