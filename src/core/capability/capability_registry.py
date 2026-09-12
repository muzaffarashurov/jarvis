"""Catalog registry for EP-069.4 Unified Capability Abstraction.

CapabilityRegistry stores `Capability` catalog entries and performs no
invocation, discovery/ranking, or security enforcement of its own --
those responsibilities belong to future EP-069.5 (Capability
Discovery Engine) and EP-069.6 (External Capability Security &
Supply-Chain Trust) respectively. This mirrors `ToolRegistry`'s role
for the Tool catalog (`src/core/tool/tool_registry.py`) and
`PluginRegistry`'s role for the Plugin catalog
(`src/core/plugins/plugin_registry.py`) exactly
(`EP069_4_DESIGN.md` Section 13.3).
"""

from __future__ import annotations

from threading import Lock

from loguru import logger

from src.core.capability.capability import Capability, CapabilityError


class CapabilityRegistryError(CapabilityError):
    """Raised for invalid catalog operations (e.g. duplicate capability id)."""


class CapabilityNotFoundError(CapabilityError):
    """Raised when an operation references a capability id not in the catalog."""


class CapabilityRegistry:
    """Thread-safe catalog of capabilities known to Jarvis.

    Responsibilities:
        - Register a capability in the catalog.
        - Unregister a capability from the catalog.
        - Return a single registered capability, raising if unknown.
        - Find a single registered capability without raising.
        - List all registered capabilities.
        - Report whether a capability id is currently registered.

    Deliberately does not import `ToolRegistry`/`PluginRegistry`, and
    is not imported by either -- each catalog remains its own source
    of truth (`EP069_4_DESIGN.md` Section 13.3, "Interaction with
    existing components: none").
    """

    def __init__(self) -> None:
        """Initialize an empty CapabilityRegistry."""
        self._capabilities: dict[str, Capability] = {}
        self._lock = Lock()

    def register(self, capability: Capability) -> None:
        """Register a capability in the catalog.

        Args:
            capability: The Capability to add.

        Raises:
            CapabilityRegistryError: If a capability with the same id
                is already registered.
        """
        with self._lock:
            if capability.id in self._capabilities:
                raise CapabilityRegistryError(f"Capability already registered: '{capability.id}'.")
            self._capabilities[capability.id] = capability
        logger.info(f"Capability registered: '{capability.id}'.")

    def unregister(self, capability_id: str) -> None:
        """Remove a capability from the catalog.

        Args:
            capability_id: The id of the capability to remove.

        Raises:
            CapabilityNotFoundError: If `capability_id` is not
                registered.
        """
        with self._lock:
            if capability_id not in self._capabilities:
                raise CapabilityNotFoundError(f"Unknown capability: '{capability_id}'.")
            del self._capabilities[capability_id]
        logger.info(f"Capability unregistered: '{capability_id}'.")

    def get(self, capability_id: str) -> Capability:
        """Return a single registered capability.

        Args:
            capability_id: The id of the capability to look up.

        Returns:
            The matching Capability.

        Raises:
            CapabilityNotFoundError: If `capability_id` is not
                registered.
        """
        capability = self.find(capability_id)
        if capability is None:
            raise CapabilityNotFoundError(f"Unknown capability: '{capability_id}'.")
        return capability

    def find(self, capability_id: str) -> Capability | None:
        """Return the catalog entry for a capability id, if registered.

        Args:
            capability_id: The id of the capability to find.

        Returns:
            The Capability, or None if not registered.
        """
        with self._lock:
            return self._capabilities.get(capability_id)

    def list(self) -> list[Capability]:
        """Return every registered capability, ordered by id.

        Returns:
            A list of Capability entries sorted by id.
        """
        with self._lock:
            return sorted(self._capabilities.values(), key=lambda capability: capability.id)

    def is_registered(self, capability_id: str) -> bool:
        """Return whether a capability id is currently registered.

        Args:
            capability_id: The id to check.

        Returns:
            True if a capability with this id exists in the catalog.
        """
        with self._lock:
            return capability_id in self._capabilities
