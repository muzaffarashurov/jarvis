"""CapabilityBackend structural contract for EP-069.4 Unified Capability Abstraction.

Defines the extension seam a *future* Engineering Package implements
per backend kind (internal, local CLI/GitHub-project, REST API,
browser-executed service) to actually invoke a `Capability`. This
module ships zero concrete implementations (`EP069_4_DESIGN.md`
Section 8/23, Owner Decision D4) -- it defines the contract shape
only, modeled directly on `src/core/tool/tool_provider.py`'s
`ToolProvider`/`DefaultToolProvider` pattern, the same structural-
contract pattern already used by the Semantic Search Provider
Framework, the Context Compression Provider Framework, the Agent
Framework, the Planning Engine, and the Plan Execution Engine.

No security, policy, credential, or execution-safety enforcement is
performed here or implied by this contract -- that is EP-070
(Policy, Permissions & Human Approval Engine), EP-071 (Credential &
Secret Management), EP-072 (Autonomous Task Execution & Safety
Boundaries), and EP-069.6 (External Capability Security &
Supply-Chain Trust)'s future responsibility, none of which exist in
this repository yet (`EP069_4_DESIGN.md` Section 17).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum

from src.core.capability.capability import Capability, CapabilityError, CapabilitySourceKind

__all__ = [
    "CapabilityStatus",
    "CapabilityResult",
    "CapabilityBackendError",
    "CapabilityBackend",
]


class CapabilityStatus(str, Enum):
    """The outcome of invoking a single `Capability` through a `CapabilityBackend`.

    Mirrors `src/core/tool/tool_result.py`'s `ToolStatus` exactly.

    Attributes:
        COMPLETED: The backend performed the capability's action and
            returned normally.
        FAILED: The backend raised, or the capability could not be
            invoked.
    """

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class CapabilityResult:
    """The outcome of a single `CapabilityBackend.invoke()` call.

    Mirrors `src/core/tool/tool_result.py`'s `ToolResult` exactly.

    Attributes:
        capability_id: The id of the `Capability` that was invoked.
        status: The invocation's outcome.
        message: Human-readable explanation of the outcome.
        data: The backend's return value, forwarded unchanged. None on
            failure, or when the backend itself returns None.
    """

    capability_id: str
    status: CapabilityStatus
    message: str
    data: object | None = None


class CapabilityBackendError(CapabilityError):
    """Base class for every exception raised by a `CapabilityBackend`."""


class CapabilityBackend(ABC):
    """Structural contract every capability-invocation strategy must implement.

    A backend invokes a single, already-resolved `Capability` for one
    `CapabilitySourceKind` -- it never decides which capability to
    invoke (that is a future `CapabilityRegistry` consumer's/EP-069.5's
    concern), and never performs discovery, ranking, or security
    enforcement. `is_available()` must never perform network requests
    or expensive work, matching `ToolProvider.is_available()`'s own
    convention.

    Zero concrete subclasses are shipped by this Engineering Package
    (`EP069_4_DESIGN.md` Section 8/23, Owner Decision D4) -- this
    contract exists so a future EP (e.g. one wrapping the existing,
    unmodified `ToolEngine` for the `INTERNAL` case, per
    `EP069_4_DESIGN.md` Section 15.1's worked example) has a stable
    shape to implement against.
    """

    @abstractmethod
    def backend_kind(self) -> CapabilitySourceKind:
        """Return the `CapabilitySourceKind` this backend implements."""
        raise NotImplementedError

    @abstractmethod
    def invoke(self, capability: Capability, arguments: dict) -> CapabilityResult:
        """Invoke a single, already-resolved `Capability`.

        Args:
            capability: The capability to invoke. Callers only ever
                pass a capability that was found in a
                `CapabilityRegistry` catalog -- resolution is not this
                method's concern.
            arguments: The capability's input arguments. Validating
                `arguments` against `capability.input_schema` is this
                method's own implementation's responsibility, not
                enforced by this contract (`EP069_4_DESIGN.md` Section
                8, Non-Goals).

        Returns:
            The resulting CapabilityResult (`status` is always
            `COMPLETED` or `FAILED`).
        """
        raise NotImplementedError

    # ---------- Lifecycle / diagnostics extension point ----------

    def is_available(self) -> bool:
        """Return whether this backend is currently able to invoke capabilities.

        Base implementation always returns True. Backends with an
        enabled/configured distinction should override this method.
        """
        return True
