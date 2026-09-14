"""EP-069.6 External Capability Security & Supply-Chain Trust (advisory assessment slice).

Given a `Capability` (EP-069.4, `src/core/capability/`), produces an
advisory `CapabilitySecurityAssessment` -- a risk classification plus
a list of specific findings -- by checking the capability's
already-declared metadata (`source`, `source_kind`, `trust_level`,
`required_permissions`) against three deterministic, non-AI rules.
See `docs/architecture/designs/EP069_6_DESIGN.md` for the full
architecture, scope boundary, and Owner Decisions (OD1-OD6).

**This package is advisory only.** It makes no binding approve/reject/
execution-authorization decision of any kind -- that remains a future
EP-070 (Policy, Permissions & Human Approval Engine, not yet
implemented in this repository) or other future policy consumer's own
responsibility. This package also does NOT: perform real dependency/
package inspection or supply-chain scanning (no tool integration of
any kind); implement any sandboxing/isolation mechanism; execute a
capability (no `CapabilityBackend.invoke()` call is ever made); handle
credentials or secrets; perform any capability lifecycle action;
mutate `CapabilityRegistry` or any `Capability`; or use semantic/
LLM-based reasoning. It is not wired into `src/bootstrap.py`,
`config/config.yaml`, or any CLI surface, and is not integrated with
Planning Engine, Agent Framework, Tool Engine, or Capability Discovery
Engine (EP-069.5) -- all of that remains deferred to a future
Engineering Package. Real dependency/package inspection and real
sandboxing/isolation policy -- named in this EP's parent `docs/
BACKLOG.md` bullet -- are both deferred until the infrastructure they
would act on (a local-CLI/GitHub-project `CapabilityBackend`
implementation, and an execution engine, respectively) actually
exists; building either speculatively today was explicitly rejected
(Owner Decision OD6).

`SecurityRiskLevel`/`SecurityFinding`/`CapabilitySecurityAssessment`
(`capability_security_result.py`) are the plain, read-only outcome
data types. `CapabilitySecurityProvider`/
`DefaultCapabilitySecurityProvider`
(`capability_security_provider.py`) are the structural contract and
its one concrete, deterministic implementation, alongside this
package's own `CapabilitySecurityError` hierarchy.
`CapabilitySecurityEngine` (`capability_security_engine.py`) is the
provider-independent orchestration layer -- there is no Manager in
this Engineering Package (Owner Decision OD4); the engine is
constructed directly with the provider it will use.

Public API:
    SecurityRiskLevel -- A coarse-grained, advisory risk classification.
    SecurityFinding -- A single, specific concern raised during assessment.
    CapabilitySecurityAssessment -- The advisory outcome of assessing one Capability.
    CapabilitySecurityError -- Common root for every exception raised by this package.
    CapabilitySecurityProviderError -- Invalid assess() input (a None capability).
    CapabilitySecurityProvider -- Structural contract every assessment strategy implements.
    DefaultCapabilitySecurityProvider -- Deterministic, non-AI default strategy.
    CapabilitySecurityEngine -- Provider-independent orchestration.
"""

from __future__ import annotations

from src.core.capability_security.capability_security_engine import (
    CapabilitySecurityEngine,
)
from src.core.capability_security.capability_security_provider import (
    CapabilitySecurityError,
    CapabilitySecurityProvider,
    CapabilitySecurityProviderError,
    DefaultCapabilitySecurityProvider,
)
from src.core.capability_security.capability_security_result import (
    CapabilitySecurityAssessment,
    SecurityFinding,
    SecurityRiskLevel,
)

__all__ = [
    "SecurityRiskLevel",
    "SecurityFinding",
    "CapabilitySecurityAssessment",
    "CapabilitySecurityError",
    "CapabilitySecurityProviderError",
    "CapabilitySecurityProvider",
    "DefaultCapabilitySecurityProvider",
    "CapabilitySecurityEngine",
]
