"""EP-033 Workflow Engine.

Runs a named, ordered sequence of plain-text requests (a
`WorkflowDefinition`) as a single, repeatable unit: each
`WorkflowRequestStep` is planned and executed through EP-030's
**already-existing** `PlanExecutionEngine.execute_request()` (which
itself already optionally calls EP-029's `PlanningEngine.plan()`), in
order, halting the remaining workflow on failure per
'workflow_engine.stop_on_failure', with every step's outcome
aggregated into one `WorkflowRunResult`. This package performs no AI
reasoning, no new planning logic, and no direct real-subsystem/tool
invocation of its own -- it only sequences calls to an already
completed EP's public API, exactly the way EP-032 Multi-Agent
Collaboration only sequenced calls to EP-028's public API.

NAMING COLLISION NOTE (read before touching this package): a
completed, unrelated component already owns the name "Workflow".
EP-007 ("Core Improvements") shipped `src/core/workflows/` (`Workflow`,
`WorkflowStep`, `WorkflowRegistry`), `src/services/workflow_service.py`
(`WorkflowService`), and `src/modules/workflow_module.py`
(`WorkflowModule`, CLI namespace "workflow", config key `workflows.*`).
Its own docstring documents a known, deliberate architecture gap (it
can only call `ExecutionEngine.run(raw_target)`, EP-003's OS-level
target launcher, so domain-name steps genuinely fail) and explicitly
defers the fix. `src/bootstrap.py` never instantiates `WorkflowService`
or registers `WorkflowModule` -- that package is completed, honestly
documented, and currently dormant/unwired. Per this project's own
Notes ("Completed EPs should not be redesigned unless an explicit
architectural decision requires it"), EP-033 does not touch, fix, or
repurpose it -- it remains exactly as EP-007 left it.

To avoid any collision, present or future, EP-033 is namespaced apart
from it at every layer:
    - Package: `src/core/workflow_engine/` (not `workflows`)
    - Domain types: `WorkflowDefinition`, `WorkflowRequestStep`,
      `WorkflowRunResult`, `WorkflowStepOutcome` (not `Workflow`/
      `WorkflowStep`, to avoid same-name-different-module confusion on
      import)
    - Registry: `WorkflowDefinitionRegistry` (not `WorkflowRegistry`)
    - CLI namespace: "flow" (not "workflow" -- that token is reserved/
      dormant, and `CommandRouter.register()` raises on a duplicate
      namespace)
    - Config key: `workflow_engine.*` (not `workflows.*`)

A `WorkflowRequestStep` here is a single plain-text `request` meant for
EP-029's Planning Engine (via EP-030's Plan Execution Engine) -- not a
raw `(target, action)` pair meant for EP-003's `ExecutionEngine`, which
is EP-007's `WorkflowStep`'s shape. This is a deliberate, narrower
scope, not an attempt to fix EP-007's gap.

It may use only the public APIs of completed Engineering Packages --
specifically EP-030's Plan Execution Engine, through
`PlanExecutionEngine.execute_request()` only -- never any subsystem's
internals, and never a private attribute of `PlanExecutionEngine` or
`PlanningEngine`. `WorkflowEngine` never imports `PlanningEngine`
directly, exactly like `PlanExecutionEngine` never imports the Tool
Engine.

`WorkflowRequestStep` / `WorkflowDefinition`
(`workflow_definition.py`) are the plain, immutable domain types a
workflow is built from. `WorkflowStepOutcomeStatus` /
`WorkflowStepOutcome` / `WorkflowRunResult`
(`workflow_run_result.py`) are the plain data types describing the
outcome of running one. `WorkflowRunProvider`
(`workflow_run_provider.py`) is the structural contract every
workflow-step dispatch strategy must implement;
`DefaultWorkflowRunProvider` is the built-in, deterministic provider,
registered under the name "workflow_engine" (matching
'workflow_engine.default_provider' in config/config.yaml).
`WorkflowDefinitionRegistry` (`workflow_definition_registry.py`) is
the in-memory catalog of registered workflow definitions.
`WorkflowEngineManager` (`workflow_engine_manager.py`) owns provider
registration, active-provider selection, the stop-on-failure policy,
and the definition catalog, mirroring EP-029 through EP-032's own
*Manager classes. `WorkflowEngine` (`workflow_engine.py`) is the
provider-independent pipeline that walks a definition's steps in order
and dispatches each through the active `WorkflowRunProvider`.

Public API:
    WorkflowRequestStep -- A single step within a workflow definition.
    WorkflowDefinition -- A named, ordered sequence of steps.
    WorkflowStepOutcomeStatus -- Outcome of running a single step.
    WorkflowStepOutcome -- The outcome of attempting a single step.
    WorkflowRunResult -- The outcome of a single run() call.
    WorkflowRunProvider -- Structural contract every dispatch strategy
        must implement.
    DefaultWorkflowRunProvider -- The built-in, deterministic provider.
    WorkflowEngineError -- Base class for every Workflow Engine exception.
    WorkflowEngineConfigurationError -- Invalid 'workflow_engine.*' configuration.
    WorkflowRunProviderError -- Base class for provider-level errors.
    WorkflowDefinitionRegistry -- In-memory catalog of workflow definitions.
    WorkflowDefinitionRegistryError -- Duplicate definition registration.
    WorkflowDefinitionNotFoundError -- Unknown definition id.
    WorkflowEngineManager -- Owns provider selection, failure policy, and the catalog.
    WorkflowRunProviderRegistryError -- Duplicate provider registration.
    WorkflowRunProviderNotFoundError -- Unknown provider name.
    WorkflowEngine -- The definition -> multi-step-run pipeline.
    WorkflowRunError -- Base class for engine-level errors.
    NoWorkflowRunProviderSelectedError -- No provider is currently selected.
    EmptyWorkflowDefinitionError -- A definition with no steps was run.
    DisabledWorkflowDefinitionError -- A disabled definition was run.
"""

from __future__ import annotations

from src.core.workflow_engine.workflow_definition import WorkflowDefinition, WorkflowRequestStep
from src.core.workflow_engine.workflow_definition_registry import (
    WorkflowDefinitionNotFoundError,
    WorkflowDefinitionRegistry,
    WorkflowDefinitionRegistryError,
)
from src.core.workflow_engine.workflow_engine import (
    DisabledWorkflowDefinitionError,
    EmptyWorkflowDefinitionError,
    NoWorkflowRunProviderSelectedError,
    WorkflowEngine,
    WorkflowRunError,
)
from src.core.workflow_engine.workflow_engine_manager import (
    WorkflowEngineManager,
    WorkflowRunProviderNotFoundError,
    WorkflowRunProviderRegistryError,
)
from src.core.workflow_engine.workflow_run_provider import (
    DefaultWorkflowRunProvider,
    WorkflowEngineConfigurationError,
    WorkflowEngineError,
    WorkflowRunProvider,
    WorkflowRunProviderError,
)
from src.core.workflow_engine.workflow_run_result import (
    WorkflowRunResult,
    WorkflowStepOutcome,
    WorkflowStepOutcomeStatus,
)

__all__ = [
    "WorkflowRequestStep",
    "WorkflowDefinition",
    "WorkflowStepOutcomeStatus",
    "WorkflowStepOutcome",
    "WorkflowRunResult",
    "WorkflowRunProvider",
    "DefaultWorkflowRunProvider",
    "WorkflowEngineError",
    "WorkflowEngineConfigurationError",
    "WorkflowRunProviderError",
    "WorkflowDefinitionRegistry",
    "WorkflowDefinitionRegistryError",
    "WorkflowDefinitionNotFoundError",
    "WorkflowEngineManager",
    "WorkflowRunProviderRegistryError",
    "WorkflowRunProviderNotFoundError",
    "WorkflowEngine",
    "WorkflowRunError",
    "NoWorkflowRunProviderSelectedError",
    "EmptyWorkflowDefinitionError",
    "DisabledWorkflowDefinitionError",
]
