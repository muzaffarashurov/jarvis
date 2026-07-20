"""Job domain model for EP-011 Task Scheduler.

Job and Schedule are the Scheduler's only data model. A Job bundles
both its static definition (id, name, description, command, schedule)
and the minimal runtime state the Scheduler itself owns (last_run,
next_run, status). No other existing component tracks a job's own
execution history, so this is not a duplication of state owned
elsewhere (see AI_GENERATION_STANDARD.md's Single Source Of Truth
rule).

A Job's `command` is always a raw target string, handed unchanged to
ExecutionEngine.run() by the Scheduler. Job and Schedule carry no
knowledge of Telegram, Voice, AI, Browser, CALYPSO, Invoice, or Fast
Response Board -- per EP-011's Important Design Rules, the Scheduler
executes commands only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ScheduleType(str, Enum):
    """Supported job schedule types (see EP-011's "Supported Schedules")."""

    MANUAL = "manual"
    ONCE = "once"
    INTERVAL = "interval"
    DAILY = "daily"
    WEEKLY = "weekly"
    CRON = "cron"


class JobStatus(str, Enum):
    """Lifecycle states a Job can report."""

    IDLE = "IDLE"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class Schedule:
    """Describes when a Job should run.

    Only the fields relevant to `type` need to be set; Scheduler
    validates required fields when computing a job's next run (see
    Scheduler.calculate_next_run).

    Attributes:
        type: The ScheduleType governing how next_run is computed.
        interval_seconds: Required for INTERVAL: seconds between runs.
        time_of_day: Required for DAILY/WEEKLY: "HH:MM" (24h, UTC).
        day_of_week: Required for WEEKLY: 0=Monday .. 6=Sunday
            (matching datetime.weekday()).
        run_at: Required for ONCE: the single UTC datetime to run at.
        cron_expression: Reserved for CRON. Not yet interpreted --
            EP-011 prepares only the interface, not the implementation
            (see Scheduler.calculate_next_run's TODO).
    """

    type: ScheduleType
    interval_seconds: int | None = None
    time_of_day: str | None = None
    day_of_week: int | None = None
    run_at: datetime | None = None
    cron_expression: str | None = None


@dataclass
class Job:
    """A single schedulable unit of work.

    Attributes:
        id: Unique, stable identifier for the job.
        name: Human-readable display name.
        description: Short description shown by `scheduler info`.
        command: Raw target string passed unchanged to
            ExecutionEngine.run() -- never interpreted by the
            Scheduler itself.
        schedule: The Schedule describing when this job should run.
        enabled: Whether the job currently participates in automatic
            scheduled execution (toggled by Scheduler.start_job /
            Scheduler.stop_job).
        last_run: UTC timestamp of the job's most recent execution, or
            None if it has never run.
        next_run: UTC timestamp of the job's next scheduled execution,
            or None if it is disabled, manual, or has no further runs
            (see Scheduler.calculate_next_run).
        status: The job's most recently observed JobStatus.
    """

    id: str
    name: str
    description: str
    command: str
    schedule: Schedule
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None
    status: JobStatus = JobStatus.IDLE
