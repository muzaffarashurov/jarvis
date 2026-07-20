"""Plugin discovery for EP-010 Plugin Manifest & Auto Discovery.

PluginDiscovery scans a configured plugin directory for plugin
packages and returns a validated PluginManifest for every package
whose manifest is well-formed. It performs no registration and no
lifecycle activation -- those remain owned by PluginRegistry and
PluginLoader respectively, matching this project's Single Source of
Truth rule. A manifest that fails to parse or validate is logged and
skipped rather than raised, per EP-010's "Ignore invalid plugins".

Plugin package layout expected under the plugin directory::

    <plugin_directory>/<plugin_name>/manifest.yaml

`manifest.yaml` fields: id, name, version, description, author,
enabled, dependencies, capabilities, entry_point. `entry_point`, if
present, must be a "module.path:callable_name" string; PluginDiscovery
imports that module and resolves the callable so the resulting
PluginManifest.entry_point is ready for PluginLoader to invoke. A
manifest with no `entry_point` produces a metadata-only plugin (see
EP-009 "Default Plugins").
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Callable

import yaml
from loguru import logger

from src.core.plugins.plugin import PluginInterface
from src.core.plugins.plugin_manifest import ManifestValidationError, PluginManifest

_MANIFEST_FILENAME = "manifest.yaml"


class PluginDiscoveryError(Exception):
    """Raised when the plugin directory itself cannot be scanned."""


class PluginDiscovery:
    """Scans a plugin directory and returns validated plugin manifests.

    Responsibilities:
        - Scan the configured plugin directory for plugin packages.
        - Read each package's manifest.yaml.
        - Resolve a manifest's declared entry point to a callable.
        - Validate each manifest, skipping (and logging) invalid ones.
        - Return every successfully discovered PluginManifest.
    """

    def __init__(self, plugin_directory: Path) -> None:
        """Initialize the PluginDiscovery.

        Args:
            plugin_directory: Root directory containing plugin
                packages, one subdirectory per plugin.
        """
        self._plugin_directory = plugin_directory

    @property
    def plugin_directory(self) -> Path:
        """Return the directory this instance scans for plugin packages."""
        return self._plugin_directory

    def discover(self) -> list[PluginManifest]:
        """Scan `plugin_directory` and return every valid plugin manifest.

        Returns:
            Validated PluginManifest entries for every plugin package
            whose manifest parsed and validated successfully. Empty if
            the plugin directory does not exist -- auto-discovery is
            optional, so an absent directory is not an error.

        Raises:
            PluginDiscoveryError: If `plugin_directory` exists but
                cannot be listed (e.g. a permissions error).
        """
        if not self._plugin_directory.exists():
            logger.info(
                f"Plugin directory not found, skipping discovery: '{self._plugin_directory}'."
            )
            return []

        try:
            entries = sorted(self._plugin_directory.iterdir())
        except OSError as exc:
            raise PluginDiscoveryError(
                f"Unable to scan plugin directory '{self._plugin_directory}': {exc}"
            ) from exc

        manifests: list[PluginManifest] = []
        for entry in entries:
            if not entry.is_dir():
                continue
            manifest = self._load_manifest(entry)
            if manifest is not None:
                manifests.append(manifest)

        logger.info(f"Discovery completed: {len(manifests)} plugin(s) found.")
        return manifests

    # ---------- Internal helpers ----------

    def _load_manifest(self, plugin_dir: Path) -> PluginManifest | None:
        """Read, resolve, and validate a single plugin package's manifest.

        Args:
            plugin_dir: The plugin package's directory.

        Returns:
            A validated PluginManifest, or None if this package has no
            manifest file, invalid YAML, an unresolved entry point, or
            fails PluginManifest validation. Every skip is logged.
        """
        manifest_path = plugin_dir / _MANIFEST_FILENAME
        if not manifest_path.is_file():
            return None

        try:
            with manifest_path.open("r", encoding="utf-8") as file:
                raw = yaml.safe_load(file)
        except (yaml.YAMLError, OSError) as exc:
            logger.error(f"Manifest validation failed for '{plugin_dir.name}': {exc}")
            return None

        if not isinstance(raw, dict):
            logger.error(
                f"Manifest validation failed for '{plugin_dir.name}': "
                "manifest.yaml must contain a mapping."
            )
            return None

        logger.debug(f"Manifest loaded: '{plugin_dir.name}'.")

        try:
            entry_point = self._resolve_entry_point(raw.get("entry_point"), plugin_dir.name)
        except PluginDiscoveryError as exc:
            logger.error(f"Manifest validation failed for '{plugin_dir.name}': {exc}")
            return None

        payload = dict(raw)
        payload["entry_point"] = entry_point

        try:
            manifest = PluginManifest.from_dict(payload)
        except ManifestValidationError as exc:
            logger.error(f"Manifest validation failed for '{plugin_dir.name}': {exc}")
            return None

        logger.info(f"Plugin discovered: '{manifest.id}'.")
        return manifest

    @staticmethod
    def _resolve_entry_point(
        reference: object, plugin_name: str
    ) -> Callable[[], PluginInterface] | None:
        """Resolve a manifest's "module.path:callable" entry point string.

        Args:
            reference: The raw `entry_point` value from manifest.yaml,
                or None for a metadata-only plugin.
            plugin_name: The plugin package's directory name, for
                error messages.

        Returns:
            The imported callable, or None if `reference` is None.

        Raises:
            PluginDiscoveryError: If `reference` is not a
                "module.path:callable" string, the module cannot be
                imported, or the callable is not found on it.
        """
        if reference is None:
            return None

        if not isinstance(reference, str) or ":" not in reference:
            raise PluginDiscoveryError(
                f"Plugin '{plugin_name}' entry_point must be a 'module.path:callable' string."
            )

        module_path, _, attribute = reference.partition(":")
        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise PluginDiscoveryError(
                f"Plugin '{plugin_name}' entry_point module '{module_path}' "
                f"could not be imported: {exc}"
            ) from exc

        entry_point = getattr(module, attribute, None)
        if entry_point is None or not callable(entry_point):
            raise PluginDiscoveryError(
                f"Plugin '{plugin_name}' entry_point '{reference}' does not resolve to a callable."
            )
        return entry_point
