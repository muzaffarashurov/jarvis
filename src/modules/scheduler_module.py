"""Scheduler module: CLI command surface for EP-011 Task Scheduler.

Exposes the "scheduler" command namespace (list, status, doctor, run,
start, stop, info, help) as thin CommandModule handlers, following the
same pattern as WorkflowModule/ProcessModule. All orchestration logic
lives in SchedulerService; this module only formats CommandResult
objects for the shell.
"""

from __future__ import annotations

from typing import Callable

from src.core.command_router import CommandResult
from src.core.scheduler.job import Job
from src.services.scheduler_service import (
    SchedulerDoctorReport,
    SchedulerService,
    SchedulerStatus,
)

HELP_TEXT: str = (
    "Available commands\n\n"
    "scheduler list\n"
    "scheduler status\n"
    "scheduler doctor\n"
    "scheduler run <job>\n"
    "scheduler start <job>\n"
    "scheduler stop <job>\n"
    "scheduler info <job>\n"
    "scheduler help"
)

ActionHandler = Callable[[list[str]], CommandResult]


class SchedulerModule:
    """Built-in "scheduler" command namespace for the Task Scheduler."""

    def __init__(self, scheduler_service: SchedulerService) -> None:
        """Initialize the SchedulerModule.

        Args:
            scheduler_service: The service used to list, inspect, run,
                start, and stop scheduled jobs.
        """
        self._service = scheduler_service
        self._actions: dict[str, ActionHandler] = {
            "list": self._list,
            "status": self._status,
            "doctor": self._doctor,
            "run": self._run,
            "start": self._start,
            "stop": self._stop,
            "info": self._info,
            "help": self._help,
        }

    @property
    def name(self) -> str:
        """Return this module's command namespace: "scheduler"."""
        return "scheduler"

    def execute(self, action: str, arguments: list[str]) -> CommandResult:
        """Execute a "scheduler" action.

        Args:
            action: The requested action (e.g. "list").
            arguments: Additional arguments (e.g. a job id).

        Returns:
            A CommandResult describing the outcome.
        """
        handler = self._actions.get(action)
        if handler is None:
            command = f"{self.name} {action}".strip()
            message = f'Unknown command: {command}\nType "scheduler help" for available commands.'
            return CommandResult(success=False, message=message)

        return handler(arguments)

    def _help(self, arguments: list[str]) -> CommandResult:
        """Return the list of available scheduler commands."""
        return CommandResult(success=True, message=HELP_TEXT)

    def _list(self, arguments: list[str]) -> CommandResult:
        """List all registered jobs."""
        jobs: list[Job] = self._service.list_jobs()
        if not jobs:
            return CommandResult(success=True, message="Jobs\n\n(none registered)")

        lines = ["Jobs"]
        for job in jobs:
            state = "enabled" if job.enabled else "disabled"
            lines.append(f"{job.id} : {job.name} ({state}, {job.schedule.type.value})")
        return CommandResult(success=True, message="\n\n".join(lines))

    def _status(self, arguments: list[str]) -> CommandResult:
        """Display the scheduler's overall status."""
        status: SchedulerStatus = self._service.status()
        lines = [
            "Scheduler Status",
            f"Running : {'YES' if status.running else 'NO'}",
            f"Jobs registered : {status.jobs_registered}",
            f"Jobs enabled : {status.jobs_enabled}",
        ]
        return CommandResult(success=True, message="\n\n".join(lines))

    def _doctor(self, arguments: list[str]) -> CommandResult:
        """Run full scheduler diagnostics."""
        report: SchedulerDoctorReport = self._service.doctor()
        lines = [
            "Scheduler Doctor",
            f"Scheduler : {self._mark(report.scheduler_available)}",
            f"Registry : {self._mark(report.registry_available)}",
            f"Configuration : {self._mark(report.configuration_loaded)}",
            f"Execution Engine : {self._mark(report.execution_engine_available)}",
            f"Job State : {self._mark(report.job_state_valid)}",
            f"Next Run : {self._mark(report.next_run_calculable)}",
            f"Result : {'READY' if report.is_ready else 'FAILED'}",
        ]
        return CommandResult(success=report.is_ready, message="\n\n".join(lines))

    def _run(self, arguments: list[str]) -> CommandResult:
        """Run a job immediately."""
        job_id = self._require_job_id(arguments)
        if job_id is None:
            return CommandResult(success=False, message="Usage: scheduler run <job>")
        return self._service.run(job_id)

    def _start(self, arguments: list[str]) -> CommandResult:
        """Enable scheduled execution for a job."""
        job_id = self._require_job_id(arguments)
        if job_id is None:
            return CommandResult(success=False, message="Usage: scheduler start <job>")
        return self._service.start(job_id)

    def _stop(self, arguments: list[str]) -> CommandResult:
        """Disable scheduled execution for a job."""
        job_id = self._require_job_id(arguments)
        if job_id is None:
            return CommandResult(success=False, message="Usage: scheduler stop <job>")
        return self._service.stop(job_id)

    def _info(self, arguments: list[str]) -> CommandResult:
        """Display name, status, schedule, last/next run, and description."""
        job_id = self._require_job_id(arguments)
        if job_id is None:
            return CommandResult(success=False, message="Usage: scheduler info <job>")

        job = self._service.get_job(job_id)
        if job is None:
            return CommandResult(success=False, message=f"Job not found: {job_id}")

        pairs = (
            ("Name", job.name),
            ("Status", job.status.value),
            ("Schedule", job.schedule.type.value),
            ("Last Run", job.last_run.isoformat() if job.last_run else "never"),
            ("Next Run", job.next_run.isoformat() if job.next_run else "not scheduled"),
            ("Description", job.description),
        )
        message = "\n\n".join(f"{label}\n\n{value}" for label, value in pairs)
        return CommandResult(success=True, message=message)

    @staticmethod
    def _mark(value: bool) -> str:
        """Format a boolean diagnostic check as "OK" or "FAIL"."""
        return "OK" if value else "FAIL"

    @staticmethod
    def _require_job_id(arguments: list[str]) -> str | None:
        """Return the job id from arguments, or None if missing."""
        if not arguments:
            return None
        return arguments[0]
