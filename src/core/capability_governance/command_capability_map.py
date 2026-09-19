"""CommandCapabilityMap for EP-069.8 Capability Governance Integration (Wiring).

`CommandCapabilityMap` is the sole source of truth for the
`(module_name, action) -> capability_id` relationship the STEP 1.1
architecture-resolution report (`docs/architecture/designs/
EP069.8_STEP1_1_RESOLUTION.md`, Decision, Section 4) requires. Neither
`CommandRouter` (`src/core/command_router.py`) nor `Capability`/
`CapabilityRegistry` (EP-069.4, `src/core/capability/`) gains any
awareness of the other's identifiers -- this module is the only place
that relationship is declared.

Entries are hand-authored (never derived reflectively from
`CommandModule` structure -- no such structure exists to derive from,
per the STEP 1.1 report Section 2/3) and populated only by
`src/bootstrap.py`, the project's existing composition root, mirroring
every other cross-cutting wiring decision already made there.

This module performs no invocation, no discovery/ranking, and no
security/policy/lifecycle evaluation of any kind -- resolution only.
It never queries `CapabilityRegistry` for normal `resolve()` lookups;
`validate_against_registry()` is the one, explicit, opt-in exception,
used only at startup (STEP 1.1 report Section 4) to catch a mapping
that references a capability id `CapabilityRegistry` does not have --
never to silently repair or ignore it.
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.capability.capability_registry import CapabilityRegistry

__all__ = [
    "CapabilityGovernanceError",
    "CommandCapabilityMapError",
    "CommandCapabilityMapValidationError",
    "CommandCapabilityMap",
]


class CapabilityGovernanceError(Exception):
    """Common root for every exception raised by the Capability Governance package (EP-069.8).

    Downstream packages can catch this single type to handle "anything
    capability-governance-related," mirroring `CapabilityError`'s
    (EP-069.4), `CapabilityDiscoveryError`'s (EP-069.5),
    `CapabilitySecurityError`'s (EP-069.6), `CapabilityPolicyError`'s
    (EP-070), and `CapabilityLifecycleError`'s (EP-069.7) identical
    role. Defined here, not in `capability_governance_coordinator.py`,
    so this module has no dependency on the coordinator module (the
    coordinator imports this root instead, avoiding a circular
    import).
    """


class CommandCapabilityMapError(CapabilityGovernanceError):
    """Raised for an invalid `CommandCapabilityMap` registration.

    Covers a blank `module_name`/`action`/`capability_id`, and a
    duplicate `(module_name, action)` registration -- an existing
    mapping is never silently overwritten.
    """


class CommandCapabilityMapValidationError(CapabilityGovernanceError):
    """Raised by `validate_against_registry()` when one or more mapped
    `capability_id`s are not present in the supplied `CapabilityRegistry`.

    A mapping that references a nonexistent capability must never
    silently become an ungoverned command (STEP 1.1 report, Governance
    Semantics) -- this exception is how that requirement is enforced
    at startup, before any command can be dispatched.
    """


class CommandCapabilityMap:
    """Thread-safe, in-memory map of `(module_name, action) -> capability_id`.

    Deliberately as small as `CapabilityRegistry`'s own catalog
    (EP-069.4, `capability_registry.py`) -- same structural shape
    (register/resolve/list, duplicate-registration raises, lookup
    never raises), applied to a different key. No fuzzy matching, no
    capability discovery, no guessing: `resolve()` is an exact,
    case-insensitive dictionary lookup only.

    An empty `CommandCapabilityMap` is a fully valid, safe, real
    production state (STEP 1.1 report Section 7 / EP069.8_DESIGN.md
    Section 13) -- it means every dispatched command is ungoverned,
    identical to today's behavior before this Engineering Package
    existed.
    """

    def __init__(self) -> None:
        """Initialize an empty CommandCapabilityMap."""
        self._mappings: dict[tuple[str, str], str] = {}
        self._lock = Lock()

    @staticmethod
    def _normalize_key(module_name: str, action: str) -> tuple[str, str]:
        """Return the case-insensitive, whitespace-trimmed lookup key.

        Mirrors `CommandRouter.dispatch()`'s own normalization
        (`module_name.lower()` / `action.lower()`) exactly, so a
        mapping registered here always matches what `dispatch()`
        actually resolves at runtime.
        """
        return (module_name.strip().lower(), action.strip().lower())

    def register(self, module_name: str, action: str, capability_id: str) -> None:
        """Register a `(module_name, action) -> capability_id` relationship.

        Args:
            module_name: The `CommandModule` namespace (e.g. "system"),
                matching `CommandModule.name` / the token
                `CommandRouter.dispatch()` parses as `module_name`.
            action: The action identifier (e.g. "status"), matching
                the token `CommandRouter.dispatch()` parses as
                `action`. An empty string is a valid action (a module
                invoked with no action, per `CommandRouter.dispatch()`'s
                own `action = rest[0].lower() if rest else ""`).
            capability_id: The id of the `Capability` this command
                maps to. Not validated against a `CapabilityRegistry`
                here -- see `validate_against_registry()` for the
                explicit, separate startup check.

        Raises:
            CommandCapabilityMapError: If `module_name` or
                `capability_id` is blank, or if a mapping already
                exists for this `(module_name, action)` pair.
        """
        if not isinstance(module_name, str) or not module_name.strip():
            raise CommandCapabilityMapError("'module_name' must be non-blank.")
        if not isinstance(action, str):
            raise CommandCapabilityMapError("'action' must be a string.")
        if not isinstance(capability_id, str) or not capability_id.strip():
            raise CommandCapabilityMapError("'capability_id' must be non-blank.")

        key = self._normalize_key(module_name, action)
        with self._lock:
            if key in self._mappings:
                raise CommandCapabilityMapError(
                    f"A capability mapping already exists for '{module_name} {action}'."
                )
            self._mappings[key] = capability_id

        logger.info(
            f"Command capability mapping registered: '{module_name} {action}' -> '{capability_id}'."
        )

    def resolve(self, module_name: str, action: str) -> str | None:
        """Return the `capability_id` mapped to `(module_name, action)`, if any.

        Never raises for an unmapped pair -- mirrors
        `CapabilityRegistry.find()` / `ToolRegistry.find_for_step()`'s
        own "return `None`, don't raise" convention for the common,
        negative case.

        Args:
            module_name: The module namespace to resolve.
            action: The action identifier to resolve.

        Returns:
            The mapped `capability_id`, or `None` if this
            `(module_name, action)` pair has no registered
            relationship (the ungoverned case).
        """
        if not isinstance(module_name, str) or not isinstance(action, str):
            return None
        key = self._normalize_key(module_name, action)
        with self._lock:
            return self._mappings.get(key)

    def is_empty(self) -> bool:
        """Return whether this map currently has zero registered mappings."""
        with self._lock:
            return not self._mappings

    def entries(self) -> list[tuple[str, str, str]]:
        """Return every registered mapping.

        Returns:
            A list of `(module_name, action, capability_id)` tuples,
            exactly as registered (not re-normalized), sorted for
            deterministic iteration order.
        """
        with self._lock:
            items = list(self._mappings.items())
        return sorted(
            (
                (mapping_key[0], mapping_key[1], capability_id)
                for mapping_key, capability_id in items
            )
        )

    def validate_against_registry(self, registry: CapabilityRegistry) -> None:
        """Validate that every mapped `capability_id` exists in `registry`.

        Intended to be called exactly once, at bootstrap/composition-root
        time (STEP 1.1 report Section 4), immediately after both this
        map and `registry` have been populated -- never during normal
        `dispatch()`-time resolution.

        Args:
            registry: The `CapabilityRegistry` every mapped
                `capability_id` must be present in.

        Raises:
            CommandCapabilityMapValidationError: If one or more mapped
                `capability_id`s are not registered in `registry`. The
                caller (bootstrap) must let this propagate -- it must
                never be caught and suppressed, and the mapping must
                never be silently repaired or downgraded to
                ungoverned.
        """
        missing = [
            (module_name, action, capability_id)
            for module_name, action, capability_id in self.entries()
            if not registry.is_registered(capability_id)
        ]
        if missing:
            details = "; ".join(
                f"'{module_name} {action}' -> '{capability_id}'"
                for module_name, action, capability_id in missing
            )
            raise CommandCapabilityMapValidationError(
                f"CommandCapabilityMap references {len(missing)} capability id(s) not "
                f"present in CapabilityRegistry: {details}."
            )
