"""Capability domain model for EP-069.4 Unified Capability Abstraction.

Defines the single, shared, structurally validated catalog-entry type
(`Capability`) that can describe an internal tool, a local CLI/
GitHub-project tool, a REST API, an external web service, or a
browser-executed service, per `EP069_4_DESIGN.md` Sections 6-7 and 14.

This module owns no invocation, no discovery/ranking, and no security
enforcement -- it is pure data plus hand-written structural validation,
matching the pattern already used by `src/core/tool/tool.py` and
`src/core/plugins/plugin_manifest.py`. Per `EP069_4_DESIGN.md` Section
13.2, no schema-validation dependency (e.g. `pydantic`, `jsonschema`)
is introduced -- `CapabilitySchema` is a minimal, hand-rolled
descriptor of named, primitively-typed fields only.

`Capability` is not related to, and does not modify, `src/core/tool/
tool.py`'s `Tool`, `src/core/plugins/plugin.py`'s `Plugin`, or
`src/skills/capability_registry/skill.py`'s `CapabilityRegistryModule`
(`EP069_4_DESIGN.md` Section 11) -- the latter is a read-only
prompt-context text composer with no domain model of its own, and is
unrelated to this module despite the shared word "capability".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "CapabilitySourceKind",
    "CapabilityTrustLevel",
    "CapabilityFieldKind",
    "CapabilitySchemaField",
    "CapabilitySchema",
    "CapabilityError",
    "CapabilityValidationError",
    "Capability",
]

class CapabilitySourceKind(str, Enum):
    """Which of the four backend kinds a `Capability` belongs to.

    Classification only (`EP069_4_DESIGN.md` Section 12.1) -- this
    module performs no dispatch based on this value. Matching
    `docs/BACKLOG.md`'s own four named backend kinds exactly (local
    GitHub projects/CLI tools are grouped under one kind, per the
    backlog's own "Local GitHub projects, CLI apps... become
    *backends*" wording).
    """

    INTERNAL = "INTERNAL"
    LOCAL_CLI = "LOCAL_CLI"
    REST_API = "REST_API"
    BROWSER_SERVICE = "BROWSER_SERVICE"


class CapabilityTrustLevel(str, Enum):
    """Coarse-grained trust classification for a `Capability`.

    Exactly three levels, deliberately not a numeric score
    (`EP069_4_DESIGN.md` Section 23, Owner Decision D6) -- a scoring
    algorithm is EP-069.6's (External Capability Security &
    Supply-Chain Trust) subject, not this EP's.

    Attributes:
        TRUSTED_INTERNAL: A capability built into this codebase.
        TRUSTED_CONFIGURED: A capability an operator explicitly
            registered/approved.
        UNVERIFIED: Default for anything not yet reviewed -- the safe
            default for any future automatically discovered capability.
    """

    TRUSTED_INTERNAL = "TRUSTED_INTERNAL"
    TRUSTED_CONFIGURED = "TRUSTED_CONFIGURED"
    UNVERIFIED = "UNVERIFIED"


class CapabilityFieldKind(str, Enum):
    """The primitive kind of a single `CapabilitySchemaField`.

    Deliberately limited to flat, primitive types
    (`EP069_4_DESIGN.md` Section 13.2/25) -- nested/recursive shapes
    are an explicitly deferred future extension, not solved
    speculatively here.
    """

    STRING = "str"
    INTEGER = "int"
    FLOAT = "float"
    BOOLEAN = "bool"
    LIST = "list"
    DICT = "dict"


class CapabilityError(Exception):
    """Common root for every exception raised by the Capability package (EP-069.4).

    Downstream packages can catch this single type to handle "anything
    capability-related" without needing to know about every specific
    failure mode (validation-level, registry-level, or
    backend-level), mirroring `src/core/tool/tool_provider.py`'s
    `ToolError`'s identical role for Tool Engine (EP-031)
    (`EP069_4_DESIGN.md` Section 12.1, STEP 3.1 AUDIT-001 resolution).

    Introduces no new behavior of its own -- a plain marker root.
    """


class CapabilityValidationError(CapabilityError):
    """Raised when a `Capability` or `CapabilitySchema` fails structural validation."""


@dataclass(frozen=True)
class CapabilitySchemaField:
    """A single named, primitively-typed field in a `CapabilitySchema`.

    Attributes:
        name: The field's name.
        kind: The field's primitive kind.
        required: Whether this field must be present.
    """

    name: str
    kind: CapabilityFieldKind
    required: bool = True


@dataclass(frozen=True)
class CapabilitySchema:
    """A minimal, hand-rolled input/output shape descriptor.

    Deliberately far short of full JSON Schema (`EP069_4_DESIGN.md`
    Section 13.2) -- declares field names/kinds/required-ness only.
    Actual argument validation against this shape is a future
    `CapabilityBackend.invoke()` implementation's responsibility, not
    this module's (`EP069_4_DESIGN.md` Section 8, Non-Goals).

    Attributes:
        fields: The schema's fields, in declaration order. Empty for a
            capability that takes/returns nothing (e.g. wrapping an
            existing zero-argument `Tool`, `EP069_4_DESIGN.md`
            Section 15.1).
    """

    fields: tuple[CapabilitySchemaField, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        """Validate this schema's structural shape.

        Raises:
            CapabilityValidationError: If `fields` contains a
                duplicate field name.
        """
        names = [schema_field.name for schema_field in self.fields]
        if len(set(names)) != len(names):
            raise CapabilityValidationError(
                f"CapabilitySchema declares a duplicate field name among: {names}."
            )


@dataclass(frozen=True)
class Capability:
    """A single catalog entry describing a real, invocable capability.

    Shared by internal tools, local CLI/GitHub-project tools, REST
    APIs, external web services, and browser-executed services
    (`EP069_4_DESIGN.md` Section 6-7) -- one model, not one type per
    backend kind. This class performs no invocation itself; a future
    `CapabilityBackend` implementation is responsible for actually
    invoking whatever this entry describes (`EP069_4_DESIGN.md`
    Section 8, Non-Goals).

    Attributes:
        id: Unique, stable identifier for the capability (used as the
            registry key), mirroring `Tool.id`/`Plugin.id`.
        name: Human-readable display name.
        description: Short description of what this capability does.
        source_kind: Which of the four backend kinds this capability
            belongs to. Classification only.
        input_schema: Declared parameter names/kinds/required-ness.
        output_schema: Declared result shape, same type as
            `input_schema`.
        required_permissions: Free-form permission tags (e.g.
            "filesystem.read", "network.external"), mirroring
            `Plugin.capabilities`'s own "free-form tags, validated for
            shape only" precedent. Inert until a future policy/
            security engine (EP-070/EP-069.6) consumes it
            (`EP069_4_DESIGN.md` Section 17).
        trust_level: Coarse-grained trust classification. Inert until
            a future discovery/security engine (EP-069.5/EP-069.6)
            consumes it.
        source: Free-text provenance (e.g. "internal", a GitHub URL,
            an API base URL). Structured provenance is a future
            EP-069.6/EP-069.7 concern.
        version: Version string, matching `Plugin.version`'s
            convention (e.g. "1.0.0").
        enabled: Whether this capability currently participates in the
            catalog, mirroring `Tool.enabled`/`Plugin.enabled`.
    """

    id: str
    name: str
    description: str
    source_kind: CapabilitySourceKind
    input_schema: CapabilitySchema
    output_schema: CapabilitySchema
    required_permissions: tuple[str, ...] = field(default_factory=tuple)
    trust_level: CapabilityTrustLevel = CapabilityTrustLevel.UNVERIFIED
    source: str = ""
    version: str = "0.0.0"
    enabled: bool = True

    @staticmethod
    def create(
        *,
        id: str,
        name: str,
        description: str,
        source_kind: CapabilitySourceKind,
        input_schema: CapabilitySchema | None = None,
        output_schema: CapabilitySchema | None = None,
        required_permissions: tuple[str, ...] = (),
        trust_level: CapabilityTrustLevel = CapabilityTrustLevel.UNVERIFIED,
        source: str = "",
        version: str = "0.0.0",
        enabled: bool = True,
    ) -> "Capability":
        """Build and validate a `Capability`.

        A separate validating constructor rather than a permissive raw
        one, mirroring `PluginManifest.from_dict()`'s pattern
        (`EP069_4_DESIGN.md` Section 14.3) -- `Capability` itself
        remains a plain frozen dataclass with no `__post_init__`
        validation ceremony.

        Args:
            id: Unique, stable identifier for the capability.
            name: Human-readable display name.
            description: Short description of what this capability
                does.
            source_kind: Which of the four backend kinds this
                capability belongs to.
            input_schema: Declared parameter shape. Defaults to an
                empty `CapabilitySchema` (no parameters).
            output_schema: Declared result shape. Defaults to an empty
                `CapabilitySchema` (no declared result fields).
            required_permissions: Free-form permission tags.
            trust_level: Coarse-grained trust classification.
            source: Free-text provenance.
            version: Version string.
            enabled: Whether this capability is enabled.

        Returns:
            A validated `Capability`.

        Raises:
            CapabilityValidationError: If `id`/`name`/`description` is
                blank, `required_permissions` contains a duplicate
                tag, or `input_schema`/`output_schema` contains a
                duplicate field name.
        """
        for field_name, value in (("id", id), ("name", name), ("description", description)):
            if not isinstance(value, str) or not value.strip():
                raise CapabilityValidationError(f"Capability field '{field_name}' must be non-blank.")

        if len(set(required_permissions)) != len(required_permissions):
            raise CapabilityValidationError(
                f"Capability '{id}' declares a duplicate required_permissions tag."
            )

        resolved_input_schema = input_schema if input_schema is not None else CapabilitySchema()
        resolved_output_schema = output_schema if output_schema is not None else CapabilitySchema()
        resolved_input_schema.validate()
        resolved_output_schema.validate()

        return Capability(
            id=id,
            name=name,
            description=description,
            source_kind=source_kind,
            input_schema=resolved_input_schema,
            output_schema=resolved_output_schema,
            required_permissions=tuple(required_permissions),
            trust_level=trust_level,
            source=source,
            version=version,
            enabled=enabled,
        )
