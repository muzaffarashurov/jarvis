"""Application-wide constants for Jarvis."""

from __future__ import annotations

from colorama import Fore

# --- Branding -----------------------------------------------------------

APP_NAME: str = "JARVIS"
APP_TAGLINE: str = "Modular AI Operating System"
APP_VERSION: str = "0.1.0-alpha"

# --- Startup banner -------------------------------------------------------

BANNER_FONT: str = "block"
"""Pyfiglet font used to render the ASCII logo."""

BANNER_PALETTE: tuple[str, ...] = (
    Fore.WHITE,
    Fore.LIGHTYELLOW_EX,
    Fore.LIGHTCYAN_EX,
    Fore.LIGHTMAGENTA_EX,
    Fore.LIGHTRED_EX,
    Fore.LIGHTBLUE_EX,
)
"""Colors cycled across letters of the ASCII logo, one per character."""

BANNER_WIDTH: int = 62
"""Target width used to center text under the ASCII logo."""
