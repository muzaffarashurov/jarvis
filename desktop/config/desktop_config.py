"""Desktop UI configuration -- separate from the Jarvis server's
``config/config.yaml``.

The Desktop UI runs as an independent process from the Jarvis server
(EP044_DESIGN.md Section 5) and must not require direct access to
JARVIS's internal configuration files (Section 17 / Decision D6). This
module owns a small, separate configuration file for the values the
Desktop UI itself needs: the API base URL/host/port and the request
timeout.

Storage mechanism (STEP 1's Open Question 7, resolved here as the
smallest solution consistent with the existing architecture per the
STEP 2 governing instructions, Section 33, "choose the smallest
solution consistent with the existing architecture and document the
decision"): a small YAML file under a Desktop-owned directory, using
``PyYAML`` -- already a project dependency
(``requirements.txt``: ``PyYAML>=6.0.1``) and the same format
``config/config.yaml`` already uses, so no new dependency or new file
format is introduced. Default values mirror EP-043's own server
defaults (``127.0.0.1`` / ``8080``) purely as a sensible starting
point for the common same-machine case -- this file is never read
from or written to ``config/config.yaml`` itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from desktop.api.jarvis_api_client import DEFAULT_TIMEOUT_SECONDS

__all__ = ["DesktopConfig", "default_config_path", "load_config", "save_config"]

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8080


@dataclass(frozen=True)
class DesktopConfig:
    """Desktop UI connection configuration.

    Attributes:
        host: The Jarvis REST API host to connect to.
        port: The Jarvis REST API port to connect to.
        timeout_seconds: The request timeout applied by
            ``JarvisApiClient``.
    """

    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    @property
    def base_url(self) -> str:
        """Return the API base URL built from ``host``/``port``."""
        return f"http://{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        """Return the YAML-serializable representation of this config."""
        return {
            "host": self.host,
            "port": self.port,
            "timeout_seconds": self.timeout_seconds,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> DesktopConfig:
        """Build a DesktopConfig from a decoded YAML mapping.

        Missing keys fall back to defaults; this keeps a partial or
        pre-existing config file from breaking Desktop UI startup,
        mirroring EP-043's own tolerant ``Config.get(..., default)``
        convention on the server side (EP044_DESIGN.md Section 4).

        Args:
            data: The decoded YAML mapping. May be empty or partial.

        Returns:
            The resulting DesktopConfig.
        """
        return DesktopConfig(
            host=data.get("host", _DEFAULT_HOST),
            port=data.get("port", _DEFAULT_PORT),
            timeout_seconds=data.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        )


def default_config_path() -> Path:
    """Return the default Desktop UI configuration file path.

    Returns:
        A path under a Desktop-owned directory
        (``<home>/.jarvis-desktop/config.yaml``), independent of the
        Jarvis server's install directory or ``config/config.yaml``.
    """
    return Path.home() / ".jarvis-desktop" / "config.yaml"


def load_config(path: Path | None = None) -> DesktopConfig:
    """Load Desktop UI configuration from disk.

    Args:
        path: The configuration file path. Defaults to
            ``default_config_path()``.

    Returns:
        The loaded DesktopConfig, or the default DesktopConfig if the
        file does not exist. A malformed file also falls back to
        defaults rather than crashing the Desktop UI at startup.
    """
    target = path or default_config_path()

    if not target.exists():
        return DesktopConfig()

    try:
        with target.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except (yaml.YAMLError, OSError):
        return DesktopConfig()

    if not isinstance(data, dict):
        return DesktopConfig()

    return DesktopConfig.from_dict(data)


def save_config(config: DesktopConfig, path: Path | None = None) -> None:
    """Persist Desktop UI configuration to disk.

    Args:
        config: The configuration to save.
        path: The configuration file path. Defaults to
            ``default_config_path()``. Parent directories are created
            if they do not exist.
    """
    target = path or default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    with target.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config.to_dict(), handle, default_flow_style=False)
