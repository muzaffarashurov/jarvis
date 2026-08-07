"""EP-034 Workflow Scheduler.

Gives an EP-033 `WorkflowDefinition` a time trigger: runs it
automatically on a schedule (interval/daily/weekly/once/manual --
cron is an interface only, not yet implemented), by calling EP-033's
already-existing `WorkflowEngine.run(workflow_id)` exclusively. This
package performs no AI reasoning, no planning, and no direct
subsystem/tool invocation of its own -- it only decides *when* an
already-completed EP's public API should be called again, exactly the
way EP-032/EP-033 only sequenced or broadcast calls to already
completed EPs' public APIs.

NAMING COLLISION NOTE (read before touching this package): a
completed, **actively wired** component already owns the name
"Scheduler". EP-011 ("Logging Improvements" era) shipped
`src/core/scheduler/` (`Job`, `Schedule`, `ScheduleType`, `JobStatus`,
`JobRegistry`, `Scheduler`), `src/services/scheduler_service.py`
(`SchedulerService`, which owns a live background tick thread
auto-started at Bootstrap), and `src/modules/scheduler_module.py`
(`SchedulerModule`, CLI namespace "scheduler", config key
`scheduler.*`). Unlike EP-007's dormant `WorkflowService`,
`src/bootstrap.py` actively constructs and registers all of this
today, including default jobs. Per this project's own Notes
("Completed EPs should not be redesigned unless an explicit
architectural decision requires it"), EP-034 does not touch, fix, or
repurpose any of it -- it remains exactly as EP-011 left it, and any
naming collision here would crash Bootstrap immediately
(`CommandRouter.register()` raises on a duplicate namespace), not just
create future confusion.

To avoid any collision, EP-034 is namespaced apart from EP-011 at
every layer:
    - Package: `src/core/workflow_scheduler/` (not `scheduler`)
    - Domain type: `ScheduledWorkflow` (not `Job`) -- carries a
      `workflow_id` reference to an EP-033 `WorkflowDefinition`, not a
      raw `ExecutionEngine` target string
    - Registry: `ScheduledWorkflowRegistry` (not `JobRegistry`)
    - Engine: `WorkflowSchedulerEngine` (not `Scheduler`)
    - CLI namespace: "autoflow" (not "scheduler", and deliberately not
      "schedule" either, to avoid the same near-miss confusion EP-033
      avoided by rejecting "workflows" for its own CLI namespace)
    - Config key: `workflow_scheduler.*` (not `scheduler.*`)

`Schedule`, `ScheduleType`, and `JobStatus` ARE reused unchanged from
EP-011 (`src/core/scheduler/job.py`, imported, never redefined) --
these are pure, stateless value types with zero coupling to
`ExecutionEngine`, so reusing them is genuine reuse, not a collision
risk. `WorkflowSchedulerEngine.calculate_next_run` deliberately
reimplements (rather than calls) EP-011's
`Scheduler.calculate_next_run`, since that method is typed to and
reads fields from `Job` specifically -- see
`workflow_scheduler_engine.py`'s own docstring for the full rationale.

`ScheduledWorkflow` (`scheduled_workflow.py`) is the plain domain type
a scheduled entry is built from. `ScheduledWorkflowRegistry`
(`scheduled_workflow_registry.py`) is the in-memory, thread-safe
catalog of registered entries. `WorkflowSchedulerEngine`
(`workflow_scheduler_engine.py`) is the engine that decides when an
entry is due and dispatches it through EP-033's `WorkflowEngine`, its
only cross-EP dependency, reached through `run()` only.

No separate Provider/Manager layer exists in this package: there is
exactly one way to compute a next-run time and exactly one way to
dispatch a due entry, so a swappable provider abstraction with only
one implementation would be speculative rather than justified by an
actual second strategy -- consistent with this project's Unknown API
Policy, and matching EP-011's own Scheduler, which likewise has no
Provider layer.

Public API:
    ScheduledWorkflow -- A single schedulable reference to a workflow definition.
    ScheduledWorkflowRegistry -- In-memory, thread-safe catalog of scheduled entries.
    WorkflowSchedulerEngine -- Decides when an entry is due and runs it.
    WorkflowSchedulerError -- Raised for invalid workflow-scheduler operations.
"""

from __future__ import annotations

from src.core.workflow_scheduler.scheduled_workflow import ScheduledWorkflow
from src.core.workflow_scheduler.scheduled_workflow_registry import ScheduledWorkflowRegistry
from src.core.workflow_scheduler.workflow_scheduler_engine import (
    WorkflowSchedulerEngine,
    WorkflowSchedulerError,
)

__all__ = [
    "ScheduledWorkflow",
    "ScheduledWorkflowRegistry",
    "WorkflowSchedulerEngine",
    "WorkflowSchedulerError",
]
