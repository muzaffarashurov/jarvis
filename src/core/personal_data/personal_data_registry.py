"""Source registry for EP-092 Personal Data Collection Framework.

`PersonalDataRegistry` is pure registration bookkeeping for
`PersonalDataSource` instances -- no storage, no scheduling -- mirroring
`KnowledgeManager`'s "pure orchestration layer" framing
(`src/core/knowledge/knowledge_manager.py`) scoped down to sources
instead of storage providers.
"""

from __future__ import annotations

from src.core.personal_data.personal_data_source import PersonalDataSource


class PersonalDataRegistryError(Exception):
    """Raised for invalid Personal Data Collection registry operations (EP-092)."""


class PersonalDataRegistry:
    """Registers and looks up `PersonalDataSource` instances by `source_id`."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._sources: dict[str, PersonalDataSource] = {}

    def register(self, source: PersonalDataSource) -> None:
        """Register `source` under its own `source_id`.

        Args:
            source: The `PersonalDataSource` instance to register.

        Raises:
            PersonalDataRegistryError: If a source is already
                registered under the same `source_id` (Single Source
                Of Truth -- duplicate registration is rejected rather
                than silently overwriting the existing source).
        """
        source_id = source.source_id
        if source_id in self._sources:
            raise PersonalDataRegistryError(
                f"A personal data source is already registered under '{source_id}'."
            )
        self._sources[source_id] = source

    def unregister(self, source_id: str) -> bool:
        """Remove a registered source.

        Args:
            source_id: The source's registration id.

        Returns:
            True if a source was removed, False if `source_id` was
            unknown.
        """
        if source_id not in self._sources:
            return False
        del self._sources[source_id]
        return True

    def get(self, source_id: str) -> PersonalDataSource | None:
        """Return the source registered under `source_id`, or None."""
        return self._sources.get(source_id)

    def is_registered(self, source_id: str) -> bool:
        """Return whether a source is registered under `source_id`."""
        return source_id in self._sources

    def source_ids(self) -> list[str]:
        """Return every registered source's id, sorted."""
        return sorted(self._sources)
