"""EP-069.4 Unified Capability Abstraction.

Defines `Capability`, a single, shared, structurally validated
catalog-entry type that can describe an internal tool, a local
CLI/GitHub-project tool, a REST API, an external web service, or a
browser-executed service -- so a future Capability Discovery Engine
(EP-069.5) does not need to special-case `Tool`, `Plugin`, and three
more unrelated types to "find matching internal, local, or remote
capabilities and rank them." This package introduces no invocation, no
discovery/ranking, no security enforcement, and no lifecycle/
versioning workflow -- those remain, respectively, a future
`CapabilityBackend` implementation's, EP-069.5's, EP-069.6's, and
EP-069.7's jobs. See `docs/architecture/designs/EP069_4_DESIGN.md` for
the full architecture and rationale.

This package must NOT be confused with `src/skills/
capability_registry/skill.py`'s `CapabilityRegistryModule` (EP-056) --
that module is an unrelated, read-only prompt-context text composer
with no domain model of its own (`EP069_4_DESIGN.md` Section 11).

`Capability` (`capability.py`) is the plain, validated catalog-entry
data type, alongside its supporting `CapabilitySourceKind`,
`CapabilityTrustLevel`, and `CapabilitySchema` types.
`CapabilityRegistry` (`capability_registry.py`) is the thread-safe
capability catalog, mirroring `ToolRegistry`/`PluginRegistry`.
`CapabilityBackend` (`capability_backend.py`) is the structural
contract every future capability-invocation strategy will implement,
alongside its `CapabilityResult`/`CapabilityStatus` outcome types --
zero concrete backend is shipped by this package.

Public API:
    Capability -- A single catalog entry describing a real, invocable capability.
    CapabilitySourceKind -- Which of the four backend kinds a capability belongs to.
    CapabilityTrustLevel -- Coarse-grained trust classification.
    CapabilityFieldKind -- The primitive kind of a single schema field.
    CapabilitySchemaField -- A single named, primitively-typed schema field.
    CapabilitySchema -- A minimal input/output shape descriptor.
    CapabilityError -- Common root for every exception raised by this package.
    CapabilityValidationError -- Raised when a Capability/CapabilitySchema fails validation.
    CapabilityRegistry -- Thread-safe catalog of registered capabilities.
    CapabilityRegistryError -- Duplicate capability registration.
    CapabilityNotFoundError -- Unknown capability id referenced.
    CapabilityBackend -- Structural contract every invocation strategy must implement.
    CapabilityResult -- The outcome of a single capability invocation.
    CapabilityStatus -- Outcome of invoking a single Capability.
    CapabilityBackendError -- Base class for every CapabilityBackend exception.
"""

from __future__ import annotations

from src.core.capability.capability import (
    Capability,
    CapabilityError,
    CapabilityFieldKind,
    CapabilitySchema,
    CapabilitySchemaField,
    CapabilitySourceKind,
    CapabilityTrustLevel,
    CapabilityValidationError,
)
from src.core.capability.capability_backend import (
    CapabilityBackend,
    CapabilityBackendError,
    CapabilityResult,
    CapabilityStatus,
)
from src.core.capability.capability_registry import (
    CapabilityNotFoundError,
    CapabilityRegistry,
    CapabilityRegistryError,
)

__all__ = [
    "Capability",
    "CapabilitySourceKind",
    "CapabilityTrustLevel",
    "CapabilityFieldKind",
    "CapabilitySchemaField",
    "CapabilitySchema",
    "CapabilityError",
    "CapabilityValidationError",
    "CapabilityRegistry",
    "CapabilityRegistryError",
    "CapabilityNotFoundError",
    "CapabilityBackend",
    "CapabilityResult",
    "CapabilityStatus",
    "CapabilityBackendError",
]
