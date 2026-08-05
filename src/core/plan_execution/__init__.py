"""EP-030 Plan Execution Engine.

Turns an EP-029 `Plan` into dispatched work: walks a plan's steps in
order, skips any step already reported unavailable, dispatches every
other step to a pluggable provider, and (by default) halts the
remaining plan after a step fails. This package must NOT call an AI
provider, build a prompt, invoke a real subsystem action, or
re-implement decomposition (`PlanningEngine`, EP-029, remains the only
place a `Plan` is built). It may use only the public APIs of completed
Engineering Packages -- specifically EP-029's Planning Engine, through
`PlanningEngine.plan()` only, and EP-029's `Plan`/`PlanStep` public
fields -- never any subsystem's internals. Turning a dispatched step
into a real external effect is explicitly out of scope and left to a
future Tool Engine.

NAMING DISAMBIGUATION: this package is named `plan_execution`, not
`execution`, and its classes are `PlanExecution*`-prefixed, not
`Execution*`-prefixed. This is deliberate: `src/core/execution/`
already exists as an entirely unrelated, pre-existing package from
EP-003 -- an OS-level target launcher (`ExecutionEngine.run(raw_target)`
opens processes, scripts, files, and URLs, and tracks process IDs via
`ProcessRegistry`) that is a load-bearing dependency of the Invoice,
Process, Scheduler, Workflow, and Plugin subsystems. The roadmap names
this Engineering Package "Execution Engine" too, but the two concepts
are unrelated (one launches OS-level targets; this one dispatches
`PlanStep` instances produced by Planning Engine) and must never be
confused or merged. The "execution" CLI namespace (see
`src/modules/plan_execution_module.py`) was unclaimed and is used
here; every command's help text is explicit that it operates on Plans,
not OS processes.

`StepStatus` / `StepResult` / `PlanExecutionResult`
(`plan_execution_result.py`) are the plain data types shared by the
rest of this package. `PlanExecutionProvider`
(`plan_execution_provider.py`) is the structural contract every
step-dispatch strategy must implement; `DefaultPlanExecutionProvider`
is the built-in, recognized-action provider, registered under the name
"plan_execution". `PlanExecutionManager` (`plan_execution_manager.py`)
owns provider registration, active-provider selection, and the default
`stop_on_failure` policy, mirroring EP-026 through EP-029's *Manager
classes. `PlanExecutionEngine` (`plan_execution_engine.py`) is the
provider-independent pipeline that walks a Plan's steps, applies the
availability/failure policy, and dispatches to the active
`PlanExecutionProvider`.

Public API:
    StepStatus -- Outcome of dispatching a single PlanStep.
    StepResult -- The outcome of attempting a single PlanStep.
    PlanExecutionResult -- The outcome of a single execute_plan() call.
    PlanExecutionProvider -- Structural contract every step-dispatch
        strategy must implement.
    DefaultPlanExecutionProvider -- The built-in, recognized-action provider.
    PlanExecutionError -- Base class for every Plan Execution Engine exception.
    PlanExecutionConfigurationError -- Invalid 'plan_execution.*' configuration.
    PlanExecutionProviderError -- Base class for provider-level errors.
    PlanExecutionManager -- Owns provider selection, configuration
        loading, and provider lifecycle.
    PlanExecutionProviderRegistryError -- Duplicate provider registration.
    PlanExecutionProviderNotFoundError -- Unknown provider name.
    PlanExecutionEngine -- The Plan -> dispatched-work pipeline.
    PlanExecutionEngineError -- Base class for engine-level errors.
    NoPlanExecutionProviderSelectedError -- No provider is currently selected.
    EmptyPlanError -- A plan with no steps was submitted.
    PlanningEngineUnavailableError -- execute_request() used without a PlanningEngine.
"""

from __future__ import annotations

from src.core.plan_execution.plan_execution_engine import (
    EmptyPlanError,
    NoPlanExecutionProviderSelectedError,
    PlanExecutionEngine,
    PlanExecutionEngineError,
    PlanningEngineUnavailableError,
)
from src.core.plan_execution.plan_execution_manager import (
    PlanExecutionManager,
    PlanExecutionProviderNotFoundError,
    PlanExecutionProviderRegistryError,
)
from src.core.plan_execution.plan_execution_provider import (
    DefaultPlanExecutionProvider,
    PlanExecutionConfigurationError,
    PlanExecutionError,
    PlanExecutionProvider,
    PlanExecutionProviderError,
)
from src.core.plan_execution.plan_execution_result import PlanExecutionResult, StepResult, StepStatus

__all__ = [
    "StepStatus",
    "StepResult",
    "PlanExecutionResult",
    "PlanExecutionProvider",
    "DefaultPlanExecutionProvider",
    "PlanExecutionError",
    "PlanExecutionConfigurationError",
    "PlanExecutionProviderError",
    "PlanExecutionManager",
    "PlanExecutionProviderRegistryError",
    "PlanExecutionProviderNotFoundError",
    "PlanExecutionEngine",
    "PlanExecutionEngineError",
    "NoPlanExecutionProviderSelectedError",
    "EmptyPlanError",
    "PlanningEngineUnavailableError",
]
