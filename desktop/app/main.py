"""Desktop UI application entrypoint.

A separate entrypoint from ``src/main.py`` (the CLI entrypoint) --
per EP-044 STEP 2's governing instructions, Section 23, the Desktop
event loop must not be merged with the existing CLI event loop, and
``src/main.py`` is not modified. The existing JARVIS CLI remains
independently usable; this module only starts the Desktop UI process.

Run as:

    python -m desktop.app.main

Composition root: constructs the ``JarvisApiClient``, the
``MainWindowViewModel``, and the ``MainWindow``, and wires them
together. No other module should construct these directly outside of
tests.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from desktop.api.jarvis_api_client import JarvisApiClient
from desktop.config.desktop_config import DesktopConfig, load_config, save_config
from desktop.viewmodels.main_window_viewmodel import MainWindowViewModel
from desktop.views.main_window import MainWindow

__all__ = ["main"]


def main() -> int:
    """Start the Jarvis Desktop UI application.

    Returns:
        The process exit code from ``QApplication.exec()``.
    """
    app = QApplication(sys.argv)

    config = load_config()
    api_client = JarvisApiClient(base_url=config.base_url, timeout_seconds=config.timeout_seconds)
    view_model = MainWindowViewModel(api_client)

    def on_settings_applied(new_config: DesktopConfig) -> None:
        save_config(new_config)
        api_client.reconfigure(base_url=new_config.base_url, timeout_seconds=new_config.timeout_seconds)
        view_model.check_health()

    window = MainWindow(view_model, initial_config=config, on_settings_applied=on_settings_applied)
    window.show()

    view_model.check_health()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
