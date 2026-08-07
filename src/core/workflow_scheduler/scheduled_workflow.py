"""ScheduledWorkflow domain model for EP-034 Workflow Scheduler.

ScheduledWorkflow bundles a reference to an EP-033 `WorkflowDefinition`
(by id, never the object itself -- the definition's own catalog stays
exclusively `WorkflowEngineManager`'s concern) with the minimal runtime
state a scheduler needs to track (last_run, next_run, status).

`Schedule`, `ScheduleType`, and `JobStatus` are reused UNCHANGED from
EP-011's Task Scheduler (`src/core/scheduler/job.py`) rather than
redefined here: they are pure, stateless value types with zero
coupling to `ExecutionEngine`, `Job`, or anything else EP-011-specific
-- reusing them is genuine reuse, not a naming-collision risk, and
avoids duplicating the same enum values under a different name for no
reason. See `src/core/workflow_scheduler/__init__.py` for the full
naming-collision note explaining why `ScheduledWorkflow` itself (and
every other new type in this package) is deliberately NOT named `Job`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.core.scheduler.job import JobStatus, Schedule

__all__ = ["ScheduledWorkflow"]


@dataclass
class ScheduledWorkflow:
    """A single schedulable reference to an EP-033 workflow definition.

    Attributes:
        id: Unique, stable identifier for this scheduled entry (distinct
            from `workflow_id` -- the same workflow definition could, in
            principle, be scheduled more than once with different
            schedules).
        name: Human-readable display name.
        description: Short description shown by `autoflow info`.
        workflow_id: The id of the EP-033 `WorkflowDefinition` to run --
            forwarded unchanged to `WorkflowEngine.run(workflow_id)`,
            never interpreted by this package.
        schedule: The (reused, EP-011) Schedule describing when this
            entry should run.
        enabled: Whether this entry currently participates in automatic
            scheduled execution (toggled by
            `WorkflowSchedulerEngine.start`/`stop`).
        last_run: UTC timestamp of the most recent run, or None if it
            has never run.
        next_run: UTC timestamp of the next scheduled run, or None if
            disabled, manual, or exhausted (see
            `WorkflowSchedulerEngine.calculate_next_run`).
        status: The most recently observed (reused, EP-011) JobStatus.
    """

    id: str
    name: str
    description: str
    workflow_id: str
    schedule: Schedule
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    status: JobStatus = JobStatus.IDLE
