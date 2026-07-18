"""Plugin discovery for EP-010 Plugin Manifest & Auto Discovery.

PluginDiscovery scans a configured plugin directory for subdirectories
containing a manifest file, reads and validates each manifest, and
returns every successfully discovered plugin. It performs no
registration and no entry-point resolution -- those responsibilities
belong to PluginLoader (see plugin_loader.py's `load_discovered`),
matching this project's "one responsibility per component" rule.
Invalid or malformed manifests are skipped and logged rather than
raising, so a single bad plugin cannot abort discovery of the rest.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from loguru import logger

from src.core.plugins.plugin_manifest import PluginManifest, PluginManifestError

MANIFEST_FILENAMES: tuple[str, ...] = ("plugin.yaml", "plugin.yml")


class PluginDiscoveryError(Exception):
    """Raised when the configured plugin directory cannot be scanned."""


@dataclass(frozen=True)
class DiscoveredPlugin:
    """A single plugin found on disk with a validated manifest.

    Attributes:
        manifest: The validated PluginManifest.
        plugin_directory: Directory containing the plugin and its
            manifest file. Entry-point module paths in `manifest` are
            resolved relative to this directory.
        manifest_path: Full path of the manifest file that was read.
    """

    manifest: PluginManifest
    plugin_directory: Path
    manifest_path: Path


class PluginDiscovery:
    """Scans a directory for plugin manifests and returns validated plugins.

    Responsibilities:
        - Scan the configured plugin directory for subdirectories.
        - Find each subdirectory's manifest file, if any.
        - Read and validate manifests.
        - Ignore invalid plugins, logging why each was skipped.
        - Return every successfully discovered plugin.
    """

    def __init__(self, plugin_directory: Path) -> None:
        """Initialize the PluginDiscovery.

        Args:
            plugin_directory: Root directory to scan for plugin
                subdirectories (each expected to contain a manifest
                file named "plugin.yaml" or "plugin.yml").
        """
        self._plugin_directory = plugin_directory

    def discover(self) -> list[DiscoveredPlugin]:
        """Scan `plugin_directory` and return every validly-discovered plugin.

        A missing plugin directory is treated as "nothing to
        discover" rather than an error, since auto-discovery must not
        prevent Jarvis from starting when no plugin directory has been
        created yet.

        Returns:
            Discovered plugins, in directory-scan order. Empty if the
            plugin directory does not exist or contains no valid
            plugins.

        Raises:
            PluginDiscoveryError: If `plugin_directory` exists but is
                not a directory.
        """
        if not self._plugin_directory.exists():
            logger.info(
                f"Plugin directory not found, skipping discovery: "
                f"'{self._plugin_directory}'."
            )
            return []
        if not self._plugin_directory.is_dir():
            raise PluginDiscoveryError(
                f"Plugin directory is not a directory: '{self._plugin_directory}'."
            )

        discovered: list[DiscoveredPlugin] = []
        seen_ids: set[str] = set()

        for entry in sorted(self._plugin_directory.iterdir()):
            if not entry.is_dir():
                continue

            manifest_path = self._find_manifest(entry)
            if manifest_path is None:
                logger.debug(f"No manifest found, skipping: '{entry}'.")
                continue

            manifest = self._read_manifest(manifest_path)
            if manifest is None:
                continue
            logger.info(f"Manifest loaded: '{manifest_path}'.")

            if manifest.id in seen_ids:
                logger.error(
                    f"Manifest validation failed: duplicate plugin id "
                    f"'{manifest.id}' at '{manifest_path}'."
                )
                continue

            seen_ids.add(manifest.id)
            discovered.append(
                DiscoveredPlugin(
                    manifest=manifest, plugin_directory=entry, manifest_path=manifest_path
                )
            )
            logger.info(f"Plugin discovered: '{manifest.id}' at '{entry}'.")

        logger.info(f"Discovery completed: {len(discovered)} plugin(s) found.")
        return discovered

    @staticmethod
    def _find_manifest(plugin_directory: Path) -> Path | None:
        """Return the manifest file inside `plugin_directory`, if present.

        Args:
            plugin_directory: A candidate plugin subdirectory.

        Returns:
            The path to the first matching manifest filename found, or
            None if `plugin_directory` contains no manifest file.
        """
        for filename in MANIFEST_FILENAMES:
            candidate = plugin_directory / filename
            if candidate.is_file():
                return candidate
        return None

    @staticmethod
    def _read_manifest(manifest_path: Path) -> PluginManifest | None:
        """Read and validate a single manifest file.

        Args:
            manifest_path: Path to the manifest file to read.

        Returns:
            The validated PluginManifest, or None if the file could
            not be read, parsed as YAML, or validated. Each failure
            case is logged as "Manifest validation failed" rather than
            raised, so discovery of other plugins can continue.
        """
        try:
            with manifest_path.open("r", encoding="utf-8") as file:
                data = yaml.safe_load(file)
        except (OSError, yaml.YAMLError) as exc:
            logger.error(f"Manifest validation failed: '{manifest_path}': {exc}")
            return None

        try:
            return PluginManifest.from_dict(data or {}, source=str(manifest_path))
        except PluginManifestError as exc:
            logger.error(f"Manifest validation failed: '{manifest_path}': {exc}")
            return None
