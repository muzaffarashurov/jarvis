"""Plugin manifest model for EP-010 Plugin Manifest & Auto Discovery.

PluginManifest is the strongly typed, validated representation of a
single plugin's on-disk manifest file (see plugin_discovery.py for the
manifest.yaml file format and lookup convention). It owns structural
manifest validation only.

Catalog-wide checks already have an owner elsewhere and are
deliberately NOT duplicated here, per this project's "never duplicate
existing functionality" rule:
    - Unique id across the whole catalog: PluginRegistry.register()
      already raises PluginRegistryError for a duplicate id.
    - Dependency existence across the whole catalog: PluginLoader.
      resolve_dependencies() already raises MissingDependencyError /
      DependencyCycleError.

This module performs no filesystem access and no dynamic imports --
those are PluginDiscovery's responsibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.core.plugins.plugin import Plugin, PluginInterface

_REQUIRED_STRING_FIELDS: tuple[str, ...] = ("id", "name", "version", "description", "author")


class ManifestValidationError(Exception):
    """Raised when a plugin manifest fails structural validation."""


@dataclass(frozen=True)
class PluginManifest:
    """Strongly typed, validated plugin manifest.

    Attributes:
        id: Unique, stable plugin identifier.
        name: Human-readable display name.
        version: Version string (e.g. "1.0.0").
        description: Short description shown by `plugin info`.
        author: Plugin author or owning team.
        enabled: Whether this plugin participates in auto-loading.
        dependencies: IDs of plugins that must load before this one.
        capabilities: Free-form capability tags this plugin provides.
        entry_point: Factory that creates the plugin's runtime
            instance, already resolved to a callable by
            PluginDiscovery, or None for a metadata-only plugin.
    """

    id: str
    name: str
    version: str
    description: str
    author: str
    enabled: bool = True
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    entry_point: Callable[[], PluginInterface] | None = None

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "PluginManifest":
        """Build and validate a PluginManifest from raw manifest data.

        Args:
            data: The parsed manifest file content. `entry_point`, if
                present, must already be resolved to a callable (or
                None) by the caller -- dynamic imports are a
                filesystem/module concern, not manifest validation.

        Returns:
            A validated PluginManifest.

        Raises:
            ManifestValidationError: If a required field is missing or
                blank, `dependencies`/`capabilities` are not lists of
                strings, `id` appears in its own `dependencies`,
                `capabilities` contains a duplicate, `enabled` is not
                a boolean, or `entry_point` is neither None nor
                callable.
        """
        for field_name in _REQUIRED_STRING_FIELDS:
            value = data.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise ManifestValidationError(f"Manifest missing required field '{field_name}'.")

        plugin_id = data["id"]
        dependencies = PluginManifest._as_string_tuple(data.get("dependencies", []), "dependencies")
        capabilities = PluginManifest._as_string_tuple(data.get("capabilities", []), "capabilities")

        if plugin_id in dependencies:
            raise ManifestValidationError(f"Plugin '{plugin_id}' cannot depend on itself.")
        if len(set(capabilities)) != len(capabilities):
            raise ManifestValidationError(f"Plugin '{plugin_id}' declares a duplicate capability.")

        enabled = data.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ManifestValidationError(f"Plugin '{plugin_id}' field 'enabled' must be a boolean.")

        entry_point = data.get("entry_point")
        if entry_point is not None and not callable(entry_point):
            raise ManifestValidationError(
                f"Plugin '{plugin_id}' field 'entry_point' must be a resolved callable or None."
            )

        return PluginManifest(
            id=plugin_id,
            name=data["name"],
            version=data["version"],
            description=data["description"],
            author=data["author"],
            enabled=enabled,
            dependencies=dependencies,
            capabilities=capabilities,
            entry_point=entry_point,
        )

    @staticmethod
    def _as_string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
        """Validate and coerce a manifest list field to a tuple of strings.

        Args:
            value: The raw field value from manifest data.
            field_name: The field's name, for error messages.

        Returns:
            `value` as a tuple of strings.

        Raises:
            ManifestValidationError: If `value` is not a list of strings.
        """
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ManifestValidationError(f"Manifest field '{field_name}' must be a list of strings.")
        return tuple(value)

    def to_plugin(self) -> Plugin:
        """Convert this manifest into a catalog-ready Plugin.

        Returns:
            A Plugin with the default `status=PluginStatus.REGISTERED`
            and no aliases (manifests do not declare aliases; aliases
            are an EP-009.1 CLI concern assigned separately, e.g. by
            PluginService.default_plugins()).
        """
        return Plugin(
            id=self.id,
            name=self.name,
            version=self.version,
            description=self.description,
            author=self.author,
            enabled=self.enabled,
            entry_point=self.entry_point,
            dependencies=self.dependencies,
            capabilities=self.capabilities,
        )
