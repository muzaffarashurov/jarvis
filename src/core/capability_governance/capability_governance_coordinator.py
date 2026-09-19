"""CapabilityGovernanceCoordinator for EP-069.8 Capability Governance Integration (Wiring).

`CapabilityGovernanceCoordinator` is the single, thin orchestration
seam `CommandRouter.dispatch()` depends on (STEP 1.1 report, Section
1/8; `EP069.8_DESIGN.md` Section 10) to turn an already-dispatched
`(module_name, action)` pair into an allow/deny outcome. It composes
five already-existing, already-audited, unmodified collaborators --
`CommandCapabilityMap` (this package), `CapabilityRegistry`
(EP-069.4), `CapabilitySecurityEngine` (EP-069.6), `PolicyEngine`
(EP-070), and `CapabilityLifecycleRegistry` (EP-069.7) -- and performs
no governance decision logic of its own: every decision-making rule
still lives inside `PolicyEngine`'s own, unmodified
`DefaultPolicyProvider`. This module only sequences calls and
translates the result into a `GovernanceDecision` `CommandRouter` can
act on without needing to know any of the five collaborators exist.

`CapabilityDiscoveryEngine` (EP-069.5) is deliberately never called
here -- `CommandRouter.dispatch()` already has an exact
`(module_name, action)` target; fuzzy, ranked task-text matching has
no role in resolving an already-known target (STEP 1.1 report,
Section 7).

Every collaborator is received through dependency injection at
construction time; this module never constructs any of them itself
(mirrors `PolicyEngine`'s/`CapabilitySecurityEngine`'s own "never
selects, constructs, or reconfigures a provider on its own behalf"
convention, applied one layer up).

Failure semantics (STEP 1.1 report, Error Semantics; `EP069.8_DESIGN.md`
Section 12):
    - No mapping for `(module_name, action)` -> `UNGOVERNED` (not a
      denial; identical to pre-EP-069.8 behavior).
    - Mapping exists, capability exists, `PolicyLevel.EXECUTE` ->
      `ALLOWED`.
    - Mapping exists, capability exists, any other `PolicyLevel` ->
      `DENIED`.
    - Mapping exists but the capability is missing from
      `CapabilityRegistry`, or any collaborator raises unexpectedly ->
      `ERROR` (fail closed -- never treated as `ALLOWED`/`UNGOVERNED`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from loguru import logger

from src.core.capability.capability_registry import CapabilityRegistry
from src.core.capability_governance.command_capability_map import CommandCapabilityMap
from src.core.capability_lifecycle.capability_lifecycle_registry import (
    CapabilityLifecycleRegistry,
)
from src.core.capability_policy.capability_policy_engine import PolicyEngine
from src.core.capability_policy.capability_policy_result import PolicyDecision, PolicyLevel
from src.core.capability_security.capability_security_engine import CapabilitySecurityEngine

__all__ = [
    "GovernanceOutcome",
    "GovernanceDecision",
    "CapabilityGovernanceCoordinator",
]


class GovernanceOutcome(str, Enum):
    """The high-level result of one `CapabilityGovernanceCoordinator.authorize_dispatch()` call.

    Deliberately only four values, matching the four categories
    `CommandRouter` must be able to distinguish (STEP 2 requirement,
    `EP069.8_DESIGN.md` Section 4): an outcome this coarse-grained is
    all `CommandRouter` needs to decide whether to call
    `module.execute()` -- it never needs to know *why* in order to
    make that decision (see `GovernanceDecision.may_execute`).
    """

    UNGOVERNED = "UNGOVERNED"
    ALLOWED = "ALLOWED"
    DENIED = "DENIED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class GovernanceDecision:
    """The outcome of one `CapabilityGovernanceCoordinator.authorize_dispatch()` call.

    Attributes:
        outcome: The high-level result.
        capability_id: The resolved capability id, if `(module_name,
            action)` mapped to one. `None` for `UNGOVERNED`.
        policy_decision: The underlying `PolicyEngine.evaluate()`
            result, preserved unchanged, when one was actually
            computed (i.e. `ALLOWED`/`DENIED` only -- never present
            for `UNGOVERNED`, and never present for an `ERROR` raised
            before policy evaluation was reached).
        reason: A short, human-readable explanation. Always populated
            for `DENIED`/`ERROR`; empty for `UNGOVERNED`/`ALLOWED`.
    """

    outcome: GovernanceOutcome
    capability_id: str | None = None
    policy_decision: PolicyDecision | None = None
    reason: str = ""

    @property
    def may_execute(self) -> bool:
        """Return whether `CommandRouter` may proceed to `module.execute()`.

        `True` for `UNGOVERNED` (nothing to authorize) and `ALLOWED`
        (`PolicyLevel.EXECUTE`) only. `False` for `DENIED` and
        `ERROR` -- both fail closed identically from
        `CommandRouter`'s point of view; `outcome`/`reason` remain
        available for logging/diagnostics.
        """
        return self.outcome in (GovernanceOutcome.UNGOVERNED, GovernanceOutcome.ALLOWED)


class CapabilityGovernanceCoordinator:
    """Central governance orchestration layer for EP-069.8.

    Receives every collaborator through dependency injection
    (constructed once, in `src/bootstrap.py`) and never constructs any
    of them itself. `CommandRouter` depends on this class only -- it
    never sees `CommandCapabilityMap`, `CapabilityRegistry`, or any of
    the four governance engines directly (STEP 1.1 report, Section 1).
    """

    def __init__(
        self,
        command_capability_map: CommandCapabilityMap,
        capability_registry: CapabilityRegistry,
        security_engine: CapabilitySecurityEngine,
        policy_engine: PolicyEngine,
        lifecycle_registry: CapabilityLifecycleRegistry,
    ) -> None:
        """Initialize the coordinator with its five collaborators.

        Args:
            command_capability_map: Resolves `(module_name, action)`
                to a `capability_id`. Never mutated by this class.
            capability_registry: EP-069.4 catalog; only `find()` is
                ever called.
            security_engine: EP-069.6 advisory risk assessment; only
                `assess()` is ever called.
            policy_engine: EP-070 policy-decision engine; only
                `evaluate()` is ever called.
            lifecycle_registry: EP-069.7 status/audit tracker; only
                `is_tracked()`/`status()` are ever called -- this
                class never calls `register()`/`disable()`/`enable()`/
                `revoke()`, and never records a successful execution
                as a lifecycle event (STEP 1.1 report, Section 7 --
                execution audit stays in this module's own logging,
                not in `CapabilityLifecycleRegistry`, to preserve
                EP-069.7's own, already-audited boundary unmodified).
        """
        self._command_capability_map = command_capability_map
        self._capability_registry = capability_registry
        self._security_engine = security_engine
        self._policy_engine = policy_engine
        self._lifecycle_registry = lifecycle_registry

    def authorize_dispatch(self, module_name: str, action: str) -> GovernanceDecision:
        """Authorize one `CommandRouter.dispatch()`-resolved `(module_name, action)` pair.

        Args:
            module_name: The dispatched module namespace.
            action: The dispatched action identifier.

        Returns:
            A `GovernanceDecision` describing whether `CommandRouter`
            may proceed to `module.execute()`. Never raises -- every
            collaborator failure is caught and translated into an
            `ERROR` decision (fail closed), matching
            `CommandRouter.dispatch()`'s own "a module must never
            crash the shell" convention, extended here to
            "governance must never crash the shell" either.
        """
        capability_id: str | None = None
        try:
            capability_id = self._command_capability_map.resolve(module_name, action)
            if capability_id is None:
                return GovernanceDecision(outcome=GovernanceOutcome.UNGOVERNED)

            capability = self._capability_registry.find(capability_id)
            if capability is None:
                logger.error(
                    f"Capability governance inconsistency: '{module_name} {action}' maps to "
                    f"capability id '{capability_id}', which is not registered in "
                    f"CapabilityRegistry. Denying (fail closed)."
                )
                return GovernanceDecision(
                    outcome=GovernanceOutcome.ERROR,
                    capability_id=capability_id,
                    reason=f"mapped capability '{capability_id}' is not registered",
                )

            lifecycle_status = None
            if self._lifecycle_registry.is_tracked(capability_id):
                lifecycle_status = self._lifecycle_registry.status(capability_id)

            security_assessment = self._security_engine.assess(capability)

            policy_decision = self._policy_engine.evaluate(
                capability,
                security_assessment=security_assessment,
                lifecycle_status=lifecycle_status,
            )
        except Exception as exc:  # noqa: BLE001 - governance failures must fail closed, never propagate
            logger.error(
                f"Capability governance internal error authorizing '{module_name} {action}' "
                f"(capability_id={capability_id!r}): {type(exc).__name__}: {exc}. Denying (fail closed)."
            )
            return GovernanceDecision(
                outcome=GovernanceOutcome.ERROR,
                capability_id=capability_id,
                reason=f"internal governance error: {type(exc).__name__}",
            )

        if policy_decision.level == PolicyLevel.EXECUTE:
            logger.info(
                f"Capability governance allowed '{module_name} {action}' "
                f"(capability_id='{capability_id}')."
            )
            return GovernanceDecision(
                outcome=GovernanceOutcome.ALLOWED,
                capability_id=capability_id,
                policy_decision=policy_decision,
            )

        logger.warning(
            f"Capability governance denied '{module_name} {action}' "
            f"(capability_id='{capability_id}'): level={policy_decision.level.value}, "
            f"reasons={list(policy_decision.reasons)}."
        )
        return GovernanceDecision(
            outcome=GovernanceOutcome.DENIED,
            capability_id=capability_id,
            policy_decision=policy_decision,
            reason=f"policy level {policy_decision.level.value}",
        )
