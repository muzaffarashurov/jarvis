"""Plugin manifest domain model for EP-010 Plugin Manifest & Auto Discovery.

PluginManifest is the strongly typed, validated representation of a
single plugin's on-disk manifest file (read by PluginDiscovery). It
owns manifest-shape validation only: required fields, field types, and
structural dependency checks (self-dependency, duplicates). It performs
no filesystem access, no entry-point resolution, and no registry
mutation -- those responsibilities belong to PluginDiscovery and
PluginLoader respectively, matching this project's Single Source of
Truth rule and the "one responsibility per component" rule in
AI_GENERATION_STANDARD.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

_REQUIRED_FIELDS: tuple[str, ...] = ("id", "name", "version", "entry_point")


class PluginManifestError(Exception):
    """Raised when a plugin manifest fails validation."""


@dataclass(frozen=True)
class PluginManifest:
    """A single plugin's validated, strongly typed manifest.

    Attributes:
        id: Unique, stable plugin identifier (e.g. "invoice_automation").
        name: Human-readable display name.
        version: Version string (e.g. "1.0.0").
        entry_point: Reference to the plugin's entry point, in the form
            "<relative_module_path>:<ClassName>" (e.g.
            "plugin.py:MyPlugin"), where the module path is relative to
            this plugin's own directory. Resolution into an importable
            class is performed by PluginLoader, not by this module.
        description: Short description of the plugin. Defaults to "".
        author: Plugin author or owning team. Defaults to "".
        dependencies: Ids of plugins that must be loaded first.
        capabilities: Free-form capability tags this plugin provides.
        enabled: Whether this plugin should be activated automatically
            once discovered. Defaults to True.
    """

    id: str
    name: str
    version: str
    entry_point: str
    description: str = ""
    author: str = ""
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    enabled: bool = True

    @staticmethod
    def from_dict(data: dict[str, Any], source: str) -> "PluginManifest":
        """Build and validate a PluginManifest from raw manifest data.

        Args:
            data: Parsed manifest mapping (e.g. from YAML).
            source: Path or identifier of the manifest, used only to
                make error messages actionable.

        Returns:
            The validated PluginManifest.

        Raises:
            PluginManifestError: If `data` is not a mapping, a required
                field is missing/blank, a field has the wrong type, an
                entry_point is malformed, dependencies/capabilities
                contain non-string or blank entries, dependencies
                contain duplicates, or the manifest declares a
                dependency on itself.
        """
        if not isinstance(data, dict):
            raise PluginManifestError(f"Manifest at '{source}' must be a mapping.")

        missing = [
            field_name
            for field_name in _REQUIRED_FIELDS
            if not str(data.get(field_name, "")).strip()
        ]
        if missing:
            raise PluginManifestError(
                f"Manifest at '{source}' is missing required field(s): "
                f"{', '.join(missing)}."
            )

        plugin_id = str(data["id"]).strip()
        entry_point = PluginManifest._validate_entry_point(str(data["entry_point"]).strip(), source)

        dependencies = PluginManifest._as_str_tuple(
            data.get("dependencies", ()), "dependencies", source
        )
        if plugin_id in dependencies:
            raise PluginManifestError(f"Manifest at '{source}' declares a dependency on itself.")
        if len(set(dependencies)) != len(dependencies):
            raise PluginManifestError(f"Manifest at '{source}' declares duplicate dependencies.")

        capabilities = PluginManifest._as_str_tuple(
            data.get("capabilities", ()), "capabilities", source
        )

        enabled = data.get("enabled", True)
        if not isinstance(enabled, bool):
            raise PluginManifestError(f"Manifest at '{source}' field 'enabled' must be a boolean.")

        return PluginManifest(
            id=plugin_id,
            name=str(data["name"]).strip(),
            version=str(data["version"]).strip(),
            entry_point=entry_point,
            description=str(data.get("description", "")).strip(),
            author=str(data.get("author", "")).strip(),
            dependencies=dependencies,
            capabilities=capabilities,
            enabled=enabled,
        )

    @staticmethod
    def _validate_entry_point(entry_point: str, source: str) -> str:
        """Validate `entry_point` matches "<module_path>:<ClassName>".

        Args:
            entry_point: The raw entry_point string to validate.
            source: Manifest path/identifier, used in error messages.

        Returns:
            The validated entry_point string, unchanged.

        Raises:
            PluginManifestError: If `entry_point` does not contain
                exactly one colon, or either side of it is blank.
        """
        if entry_point.count(":") != 1 or not all(
            part.strip() for part in entry_point.split(":")
        ):
            raise PluginManifestError(
                f"Manifest at '{source}' has invalid entry_point '{entry_point}'; "
                "expected format '<module_path>:<ClassName>'."
            )
        return entry_point

    @staticmethod
    def _as_str_tuple(value: Any, field_name: str, source: str) -> tuple[str, ...]:
        """Validate and normalize a list-of-strings manifest field.

        Args:
            value: The raw field value from manifest data.
            field_name: Name of the field, used in error messages.
            source: Manifest path/identifier, used in error messages.

        Returns:
            A tuple of stripped, non-empty strings. Empty if `value` is
            None or an empty string.

        Raises:
            PluginManifestError: If `value` is not a list/tuple, or
                contains a non-string or blank entry.
        """
        if value in (None, ""):
            return ()
        if not isinstance(value, (list, tuple)):
            raise PluginManifestError(f"Manifest at '{source}' field '{field_name}' must be a list.")

        result: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise PluginManifestError(
                    f"Manifest at '{source}' field '{field_name}' must contain non-empty strings."
                )
            result.append(item.strip())
        return tuple(result)


def validate_unique_ids(manifests: Sequence[PluginManifest]) -> None:
    """Validate that every manifest in `manifests` declares a unique id.

    Args:
        manifests: Manifests to check for id collisions.

    Raises:
        PluginManifestError: On the first duplicate id encountered.
    """
    seen: set[str] = set()
    for manifest in manifests:
        if manifest.id in seen:
            raise PluginManifestError(f"Duplicate plugin id discovered: '{manifest.id}'.")
        seen.add(manifest.id)
