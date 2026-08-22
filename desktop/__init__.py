"""Jarvis Desktop UI (EP-044).

A PySide6-based graphical client for the Jarvis REST API (EP-043).

This package is a pure external client: it communicates with Jarvis
exclusively over HTTP through ``desktop.api.jarvis_api_client``,
against the existing ``/health``, ``/api/v1/status``, and
``/api/v1/commands`` endpoints. It never imports ``src.core``,
``src.services``, ``src.modules``, or ``src.bootstrap`` -- see
``docs/architecture/designs/EP044_DESIGN.md``, Section 5.

Architecture (MVVM, see EP044_DESIGN.md Section 11):

    desktop.views        -- Qt widgets/windows. Bind to ViewModel
                             signals only; never call the API client
                             directly.
    desktop.viewmodels   -- Qt-signal-exposing state holders. Hold no
                             widget references; coordinate API calls
                             on a worker thread.
    desktop.api          -- REST API client + typed error hierarchy.
                             Transport only, no UI logic.
    desktop.models       -- Client-side DTOs mirroring
                             src/core/api/dto.py's external contract.
    desktop.state        -- ConnectionState / CommandState enums.
    desktop.config       -- Desktop-owned configuration (separate from
                             config/config.yaml -- EP044_DESIGN.md
                             Section 17 / Decision D6).
    desktop.app          -- Application entrypoint / composition root.
"""
