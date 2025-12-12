"""Color palette for the Aloran Treasury Console."""

from __future__ import annotations

PALETTE = {
    "dark_blue": "#078D70",
    "teal": "#26CEAA",
    "light_teal": "#99E8C2",
    "white": "#FFFFFF",
    "light_green": "#7BADE2",
    "medium_blue": "#5049CC",
    "dark_purple": "#3D1A78",
}

BACKGROUND = PALETTE["dark_purple"]
SURFACE = "#0f1a2c"  # Slightly darker neutral for cards/panels.
SURFACE_ALT = "#142037"
TEXT_PRIMARY = PALETTE["white"]
TEXT_MUTED = "#C8D3E6"

FONT_FAMILY = "Segoe UI"
FONT_SIZE = 11

def muted(text: str) -> str:
    """Return inline HTML to render muted helper text."""

    return f"<span style='color: {TEXT_MUTED};'>{text}</span>"

__all__ = [
    "PALETTE",
    "BACKGROUND",
    "SURFACE",
    "TEXT_PRIMARY",
    "TEXT_MUTED",
    "FONT_FAMILY",
]
