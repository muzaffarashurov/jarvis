"""Domain model for EP-070 Policy, Permissions & Human Approval Engine
(capability policy-decision slice).

Defines the plain, read-only data types `PolicyProvider`/
`DefaultPolicyProvider` (`capability_policy_provider.py`) and
`PolicyEngine` (`capability_policy_engine.py`) use to represent a
policy decision: `PolicyLevel` (one of the five BACKLOG-named
graduated levels) and `PolicyDecision` (the outcome of one
`evaluate()` call).

**`PolicyLevel` is deliberately an unordered enum** (Owner Decision
OD6, `docs/architecture/designs/EP070_DESIGN.md`) -- no `__lt__`/
`__le__`/`__gt__`/`__ge__`, no numeric severity, and no public
"restrictiveness" ranking. `REQUIRE_APPROVAL` is not assumed greater
or less than `EXECUTE`.

**Mandatory semantic clarification (Owner-issued, `EP070_DESIGN.md`
Section 7/12 OD4/OD5): `OBSERVE` is a restrictive policy decision, not
execution authorization.** A `PolicyDecision` with `level ==
PolicyLevel.OBSERVE` (produced when a capability's lifecycle status is
`REVOKED` or `DISABLED`) does **not** mean that capability is
executable -- it means the opposite. This module makes no enforcement
decision of any kind; it only represents the *result* of one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

__all__ = [
    "PolicyLevel",
    "PolicyDecision",
]


class PolicyLevel(Enum):
    """One of the five graduated policy levels named by `docs/BACKLOG.md`'s
    EP-070 bullet.

    Deliberately a plain `Enum` (not `str, Enum`, unlike every sibling
    enum in this capability architecture) -- Owner Decision OD6
    requires that no comparison operator, numeric severity, or public
    ordering contract exist between any two members. A `str, Enum`
    mixin would silently inherit `str`'s own `__lt__`/`__le__`/
    `__gt__`/`__ge__`, making e.g. `PolicyLevel.OBSERVE <
    PolicyLevel.EXECUTE` technically callable (a meaningless,
    alphabetical string comparison) instead of raising -- exactly the
    implicit ordering OD6 forbids. A plain `Enum` has no such
    inherited comparison, so any ordering attempt correctly raises
    `TypeError`. Equality (`==`), hashing, and `.value` access all
    still work identically to a `str, Enum`.

    `OBSERVE` is a restrictive decision, never execution authorization
    (Owner Decision OD4/OD5's mandatory clarification) -- see this
    module's own docstring.
    """

    OBSERVE = "OBSERVE"
    ANALYZE = "ANALYZE"
    PREPARE = "PREPARE"
    EXECUTE = "EXECUTE"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


@dataclass(frozen=True)
class PolicyDecision:
    """The outcome of one `PolicyEngine.evaluate()`/`PolicyProvider.evaluate()` call.

    A `PolicyDecision` is a decision, never an enforcement action --
    this package performs no enforcement of any kind
    (`EP070_DESIGN.md` Section 17). In particular, a `level` of
    `PolicyLevel.OBSERVE` is a restrictive result and must never be
    interpreted as execution authorization by any consumer of this
    type.

    Attributes:
        capability_id: The id of the `Capability` this decision
            concerns.
        level: The computed `PolicyLevel`.
        reasons: A non-empty, ordered tuple of human-readable strings
            explaining which rule(s) produced `level`. Always
            deterministic for identical inputs.
    """

    capability_id: str
    level: PolicyLevel
    reasons: tuple[str, ...]
