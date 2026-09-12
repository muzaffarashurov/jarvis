"""Real engineering tests for EP-069.4 STEP 2 - Unified Capability Abstraction.

New, distinct test suite (`NAME = "EP069_4"`) under `tests/EP069_4/`,
following `tests/EP069_3/test_cost_aware_provider_selection.py`'s own
precedent of a self-contained package per sub-EP. This repository's
`TestRegistry.register()` keys suites by `NAME.upper()`
(`src/testing/registry.py`), so a distinct name is required. Does not
import `src.bootstrap` -- `EP069_4_DESIGN.md` Section 8 (Non-Goals)
explicitly excludes bootstrap/CLI wiring from this EP's scope, so
nothing under `src/core/capability/` depends on it.

Per `EP069_4_DESIGN.md` Section 19/Acceptance Criteria, covers:
    - `Capability.create()` success for the worked `memory_recall`
      example (Section 15.1).
    - `Capability.create()` validation failures: blank id/name/
      description, a duplicate `required_permissions` tag, a
      duplicate field name in `input_schema`/`output_schema`.
    - `CapabilityRegistry` register/get/find/list/unregister
      round-trip; duplicate-id rejection; unknown-id lookup raises;
      `list()` sorted by id; `is_registered()`.
    - `CapabilityBackend` cannot be instantiated directly; a minimal
      concrete subclass inherits a working default `is_available()`.
    - Boundary cases: an empty `CapabilitySchema` (zero fields) and an
      empty `required_permissions` tuple.
    - `CapabilityResult`/`CapabilityStatus` construction.

STEP 3.1 addition (`EP069_4_ARCHITECTURE_AUDIT.md` AUDIT-001
resolution): every capability-specific exception
(`CapabilityValidationError`, `CapabilityRegistryError`,
`CapabilityNotFoundError`, `CapabilityBackendError`) is verified to be
catchable as the shared `CapabilityError` root, while remaining
distinguishable from one another.
"""

from __future__ import annotations

from src.core.capability import (
    Capability,
    CapabilityBackend,
    CapabilityBackendError,
    CapabilityError,
    CapabilityFieldKind,
    CapabilityNotFoundError,
    CapabilityRegistry,
    CapabilityRegistryError,
    CapabilityResult,
    CapabilitySchema,
    CapabilitySchemaField,
    CapabilitySourceKind,
    CapabilityStatus,
    CapabilityTrustLevel,
    CapabilityValidationError,
)
from src.testing.base_test import BaseTest
from src.testing.registry import TestRegistry


class _FakeCapabilityBackend(CapabilityBackend):
    """Minimal, deterministic, test-only concrete `CapabilityBackend`.

    Implements only the two abstract methods, to verify `is_available()`
    inherits a working default without being overridden.
    """

    def __init__(self, kind: CapabilitySourceKind) -> None:
        self._kind = kind
        self.invoke_calls: list[tuple[str, dict]] = []

    def backend_kind(self) -> CapabilitySourceKind:
        return self._kind

    def invoke(self, capability: Capability, arguments: dict) -> CapabilityResult:
        self.invoke_calls.append((capability.id, arguments))
        return CapabilityResult(
            capability_id=capability.id,
            status=CapabilityStatus.COMPLETED,
            message=f"Capability '{capability.id}' invoked successfully.",
            data=None,
        )


def _make_memory_recall_capability() -> Capability:
    """Build the `EP069_4_DESIGN.md` Section 15.1 worked example."""
    return Capability.create(
        id="memory_recall",
        name="Memory Recall",
        description="Retrieve relevant entries from the Memory Manager (EP-023).",
        source_kind=CapabilitySourceKind.INTERNAL,
        input_schema=CapabilitySchema(fields=()),
        output_schema=CapabilitySchema(fields=()),
        required_permissions=(),
        trust_level=CapabilityTrustLevel.TRUSTED_INTERNAL,
        source="internal:tool_engine",
        version="1.0.0",
    )


@TestRegistry.register
class UnifiedCapabilityAbstractionTest(BaseTest):
    NAME = "EP069_4"

    def run(self):
        # ---------- Capability.create() success ----------
        self._test_create_memory_recall_worked_example()
        self._test_create_with_schema_fields_succeeds()
        self._test_create_defaults_are_applied()

        # ---------- Capability.create() validation failures ----------
        self._test_create_blank_id_raises()
        self._test_create_blank_name_raises()
        self._test_create_blank_description_raises()
        self._test_create_duplicate_permission_tag_raises()
        self._test_create_duplicate_input_schema_field_raises()
        self._test_create_duplicate_output_schema_field_raises()

        # ---------- CapabilityRegistry round-trip ----------
        self._test_registry_register_and_get()
        self._test_registry_find_returns_none_for_unknown()
        self._test_registry_duplicate_register_raises()
        self._test_registry_unregister_removes_entry()
        self._test_registry_unregister_unknown_raises()
        self._test_registry_get_unknown_raises()
        self._test_registry_list_sorted_by_id()
        self._test_registry_is_registered_true_and_false()

        # ---------- CapabilityBackend contract ----------
        self._test_backend_cannot_be_instantiated_directly()
        self._test_backend_default_is_available_true()
        self._test_backend_invoke_returns_result()

        # ---------- Boundary conditions ----------
        self._test_empty_schema_is_valid()
        self._test_empty_required_permissions_is_valid()

        # ---------- Error hierarchy ----------
        self._test_capability_backend_error_is_catchable()

        # ---------- STEP 3.1 AUDIT-001 resolution: CapabilityError root ----------
        self._test_validation_error_is_a_capability_error()
        self._test_registry_error_is_a_capability_error()
        self._test_not_found_error_is_a_capability_error()
        self._test_backend_error_is_a_capability_error()
        self._test_specific_capability_errors_remain_distinguishable()

        return self.result

    # ---------- Capability.create() success ----------

    def _test_create_memory_recall_worked_example(self) -> None:
        capability = _make_memory_recall_capability()

        self.assert_equal(capability.id, "memory_recall", "id must round-trip unchanged.")
        self.assert_equal(
            capability.source_kind,
            CapabilitySourceKind.INTERNAL,
            "The worked example must classify as INTERNAL.",
        )
        self.assert_equal(
            capability.trust_level,
            CapabilityTrustLevel.TRUSTED_INTERNAL,
            "An internal tool wrapper must be TRUSTED_INTERNAL.",
        )
        self.assert_true(capability.enabled, "Capability.create() must default enabled=True.")

    def _test_create_with_schema_fields_succeeds(self) -> None:
        capability = Capability.create(
            id="rest_example",
            name="REST Example",
            description="An example REST-backed capability.",
            source_kind=CapabilitySourceKind.REST_API,
            input_schema=CapabilitySchema(
                fields=(
                    CapabilitySchemaField(name="query", kind=CapabilityFieldKind.STRING),
                    CapabilitySchemaField(
                        name="limit", kind=CapabilityFieldKind.INTEGER, required=False
                    ),
                )
            ),
            output_schema=CapabilitySchema(
                fields=(CapabilitySchemaField(name="results", kind=CapabilityFieldKind.LIST),)
            ),
            required_permissions=("network.external",),
            trust_level=CapabilityTrustLevel.TRUSTED_CONFIGURED,
            source="https://example.com/api",
            version="2.1.0",
        )

        self.assert_equal(len(capability.input_schema.fields), 2, "Two input fields must round-trip.")
        self.assert_equal(
            capability.required_permissions,
            ("network.external",),
            "required_permissions must round-trip unchanged.",
        )

    def _test_create_defaults_are_applied(self) -> None:
        capability = Capability.create(
            id="minimal",
            name="Minimal",
            description="A capability declared with only required arguments.",
            source_kind=CapabilitySourceKind.LOCAL_CLI,
        )

        self.assert_equal(
            capability.input_schema,
            CapabilitySchema(),
            "input_schema must default to an empty CapabilitySchema.",
        )
        self.assert_equal(
            capability.output_schema,
            CapabilitySchema(),
            "output_schema must default to an empty CapabilitySchema.",
        )
        self.assert_equal(
            capability.trust_level,
            CapabilityTrustLevel.UNVERIFIED,
            "trust_level must default to UNVERIFIED.",
        )
        self.assert_equal(
            capability.required_permissions,
            (),
            "required_permissions must default to an empty tuple.",
        )

    # ---------- Capability.create() validation failures ----------

    def _test_create_blank_id_raises(self) -> None:
        raised = False
        try:
            Capability.create(
                id="   ",
                name="Name",
                description="Description",
                source_kind=CapabilitySourceKind.INTERNAL,
            )
        except CapabilityValidationError:
            raised = True
        self.assert_true(raised, "A blank id must raise CapabilityValidationError.")

    def _test_create_blank_name_raises(self) -> None:
        raised = False
        try:
            Capability.create(
                id="id",
                name="",
                description="Description",
                source_kind=CapabilitySourceKind.INTERNAL,
            )
        except CapabilityValidationError:
            raised = True
        self.assert_true(raised, "A blank name must raise CapabilityValidationError.")

    def _test_create_blank_description_raises(self) -> None:
        raised = False
        try:
            Capability.create(
                id="id",
                name="Name",
                description="",
                source_kind=CapabilitySourceKind.INTERNAL,
            )
        except CapabilityValidationError:
            raised = True
        self.assert_true(raised, "A blank description must raise CapabilityValidationError.")

    def _test_create_duplicate_permission_tag_raises(self) -> None:
        raised = False
        try:
            Capability.create(
                id="id",
                name="Name",
                description="Description",
                source_kind=CapabilitySourceKind.INTERNAL,
                required_permissions=("filesystem.read", "filesystem.read"),
            )
        except CapabilityValidationError:
            raised = True
        self.assert_true(
            raised, "A duplicate required_permissions tag must raise CapabilityValidationError."
        )

    def _test_create_duplicate_input_schema_field_raises(self) -> None:
        raised = False
        try:
            Capability.create(
                id="id",
                name="Name",
                description="Description",
                source_kind=CapabilitySourceKind.INTERNAL,
                input_schema=CapabilitySchema(
                    fields=(
                        CapabilitySchemaField(name="query", kind=CapabilityFieldKind.STRING),
                        CapabilitySchemaField(name="query", kind=CapabilityFieldKind.INTEGER),
                    )
                ),
            )
        except CapabilityValidationError:
            raised = True
        self.assert_true(
            raised, "A duplicate input_schema field name must raise CapabilityValidationError."
        )

    def _test_create_duplicate_output_schema_field_raises(self) -> None:
        raised = False
        try:
            Capability.create(
                id="id",
                name="Name",
                description="Description",
                source_kind=CapabilitySourceKind.INTERNAL,
                output_schema=CapabilitySchema(
                    fields=(
                        CapabilitySchemaField(name="result", kind=CapabilityFieldKind.STRING),
                        CapabilitySchemaField(name="result", kind=CapabilityFieldKind.STRING),
                    )
                ),
            )
        except CapabilityValidationError:
            raised = True
        self.assert_true(
            raised, "A duplicate output_schema field name must raise CapabilityValidationError."
        )

    # ---------- CapabilityRegistry round-trip ----------

    def _test_registry_register_and_get(self) -> None:
        registry = CapabilityRegistry()
        capability = _make_memory_recall_capability()

        registry.register(capability)
        retrieved = registry.get("memory_recall")

        self.assert_equal(retrieved, capability, "get() must return the exact registered Capability.")

    def _test_registry_find_returns_none_for_unknown(self) -> None:
        registry = CapabilityRegistry()
        self.assert_true(
            registry.find("unknown") is None, "find() must return None for an unregistered id."
        )

    def _test_registry_duplicate_register_raises(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_make_memory_recall_capability())

        raised = False
        try:
            registry.register(_make_memory_recall_capability())
        except CapabilityRegistryError:
            raised = True
        self.assert_true(raised, "Registering a duplicate id must raise CapabilityRegistryError.")

    def _test_registry_unregister_removes_entry(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_make_memory_recall_capability())

        registry.unregister("memory_recall")

        self.assert_false(
            registry.is_registered("memory_recall"), "unregister() must remove the entry."
        )

    def _test_registry_unregister_unknown_raises(self) -> None:
        registry = CapabilityRegistry()

        raised = False
        try:
            registry.unregister("unknown")
        except CapabilityNotFoundError:
            raised = True
        self.assert_true(
            raised, "unregister() for an unknown id must raise CapabilityNotFoundError."
        )

    def _test_registry_get_unknown_raises(self) -> None:
        registry = CapabilityRegistry()

        raised = False
        try:
            registry.get("unknown")
        except CapabilityNotFoundError:
            raised = True
        self.assert_true(raised, "get() for an unknown id must raise CapabilityNotFoundError.")

    def _test_registry_list_sorted_by_id(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            Capability.create(
                id="zeta",
                name="Zeta",
                description="Zeta capability.",
                source_kind=CapabilitySourceKind.INTERNAL,
            )
        )
        registry.register(
            Capability.create(
                id="alpha",
                name="Alpha",
                description="Alpha capability.",
                source_kind=CapabilitySourceKind.INTERNAL,
            )
        )

        listed = registry.list()

        self.assert_equal(
            [capability.id for capability in listed],
            ["alpha", "zeta"],
            "list() must return entries sorted by id.",
        )

    def _test_registry_is_registered_true_and_false(self) -> None:
        registry = CapabilityRegistry()
        self.assert_false(
            registry.is_registered("memory_recall"),
            "is_registered() must be False before registration.",
        )

        registry.register(_make_memory_recall_capability())

        self.assert_true(
            registry.is_registered("memory_recall"),
            "is_registered() must be True after registration.",
        )

    # ---------- CapabilityBackend contract ----------

    def _test_backend_cannot_be_instantiated_directly(self) -> None:
        raised = False
        try:
            CapabilityBackend()  # type: ignore[abstract]
        except TypeError:
            raised = True
        self.assert_true(
            raised, "CapabilityBackend must not be directly instantiable (ABC enforcement)."
        )

    def _test_backend_default_is_available_true(self) -> None:
        backend = _FakeCapabilityBackend(kind=CapabilitySourceKind.INTERNAL)
        self.assert_true(
            backend.is_available(),
            "A subclass that does not override is_available() must inherit the default True.",
        )

    def _test_backend_invoke_returns_result(self) -> None:
        backend = _FakeCapabilityBackend(kind=CapabilitySourceKind.INTERNAL)
        capability = _make_memory_recall_capability()

        result = backend.invoke(capability, arguments={})

        self.assert_equal(
            result.status, CapabilityStatus.COMPLETED, "A successful invoke() must be COMPLETED."
        )
        self.assert_equal(
            result.capability_id, "memory_recall", "The result must carry the capability's id."
        )
        self.assert_equal(
            backend.backend_kind(),
            CapabilitySourceKind.INTERNAL,
            "backend_kind() must return the kind the backend was constructed with.",
        )

    # ---------- Boundary conditions ----------

    def _test_empty_schema_is_valid(self) -> None:
        schema = CapabilitySchema(fields=())
        try:
            schema.validate()
            valid = True
        except CapabilityValidationError:
            valid = False
        self.assert_true(valid, "An empty CapabilitySchema (zero fields) must be valid.")

    def _test_empty_required_permissions_is_valid(self) -> None:
        capability = Capability.create(
            id="no_permissions",
            name="No Permissions",
            description="A capability that declares no required permissions.",
            source_kind=CapabilitySourceKind.INTERNAL,
            required_permissions=(),
        )
        self.assert_equal(
            capability.required_permissions,
            (),
            "An empty required_permissions tuple must be accepted as-is.",
        )

    # ---------- Error hierarchy ----------

    def _test_capability_backend_error_is_catchable(self) -> None:
        """`CapabilityBackendError` is the base class a future concrete
        backend implementation would raise for its own invocation
        failures (`EP069_4_DESIGN.md` Section 13.3) -- no concrete
        backend ships in this EP, so this verifies only the error
        type itself is a well-formed, catchable `Exception` subclass.
        """
        raised = False
        try:
            raise CapabilityBackendError("example backend failure")
        except CapabilityBackendError:
            raised = True
        self.assert_true(raised, "CapabilityBackendError must be a catchable Exception subclass.")

    # ---------- STEP 3.1 AUDIT-001 resolution: CapabilityError root ----------
    #
    # Verifies the fix for EP069_4_ARCHITECTURE_AUDIT.md's AUDIT-001:
    # every capability-specific exception must also be catchable as the
    # shared `CapabilityError` root (mirroring `ToolError`'s identical
    # role in `src/core/tool/tool_provider.py`), while each specific
    # exception type must remain distinguishable from the others. These
    # are behavioral tests (an actual `raise`/`except CapabilityError`
    # round-trip for each concrete type), not mere `issubclass()`
    # existence checks, since the approved resolution's contractual
    # behavior is "can be caught as CapabilityError," not merely "is
    # related to it in the class graph."

    def _test_validation_error_is_a_capability_error(self) -> None:
        caught_as_root = False
        try:
            raise CapabilityValidationError("example validation failure")
        except CapabilityError:
            caught_as_root = True
        self.assert_true(
            caught_as_root,
            "A raised CapabilityValidationError must be catchable as CapabilityError.",
        )

    def _test_registry_error_is_a_capability_error(self) -> None:
        caught_as_root = False
        try:
            raise CapabilityRegistryError("example registry failure")
        except CapabilityError:
            caught_as_root = True
        self.assert_true(
            caught_as_root,
            "A raised CapabilityRegistryError must be catchable as CapabilityError.",
        )

    def _test_not_found_error_is_a_capability_error(self) -> None:
        caught_as_root = False
        try:
            raise CapabilityNotFoundError("example not-found failure")
        except CapabilityError:
            caught_as_root = True
        self.assert_true(
            caught_as_root,
            "A raised CapabilityNotFoundError must be catchable as CapabilityError.",
        )

    def _test_backend_error_is_a_capability_error(self) -> None:
        caught_as_root = False
        try:
            raise CapabilityBackendError("example backend failure")
        except CapabilityError:
            caught_as_root = True
        self.assert_true(
            caught_as_root,
            "A raised CapabilityBackendError must be catchable as CapabilityError.",
        )

    def _test_specific_capability_errors_remain_distinguishable(self) -> None:
        # Sharing a common root must not collapse the specific types
        # into being indistinguishable from one another -- a
        # CapabilityValidationError must not also be catchable as a
        # CapabilityRegistryError, and vice versa.
        validation_error = CapabilityValidationError("example validation failure")
        registry_error = CapabilityRegistryError("example registry failure")
        not_found_error = CapabilityNotFoundError("example not-found failure")
        backend_error = CapabilityBackendError("example backend failure")

        self.assert_false(
            isinstance(validation_error, CapabilityRegistryError),
            "CapabilityValidationError must remain distinct from CapabilityRegistryError.",
        )
        self.assert_false(
            isinstance(registry_error, CapabilityNotFoundError),
            "CapabilityRegistryError must remain distinct from CapabilityNotFoundError.",
        )
        self.assert_false(
            isinstance(not_found_error, CapabilityBackendError),
            "CapabilityNotFoundError must remain distinct from CapabilityBackendError.",
        )
        self.assert_false(
            isinstance(backend_error, CapabilityValidationError),
            "CapabilityBackendError must remain distinct from CapabilityValidationError.",
        )
