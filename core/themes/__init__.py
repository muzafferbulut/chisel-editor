from core.themes.base import BaseTheme
from core.themes.definitions import (
    LightTheme,
    DarkTheme,
    HighContrastTheme,
    OceanicTheme,
    ForestTheme,
    MidnightTheme,
    SolarTheme
)

THEMES = {
    "light": LightTheme(),
    "dark": DarkTheme(),
    "high_contrast": HighContrastTheme(),
    "oceanic": OceanicTheme(),
    "forest": ForestTheme(),
    "midnight": MidnightTheme(),
    "solar": SolarTheme()
}

__all__ = [
    "BaseTheme",
    "LightTheme",
    "DarkTheme",
    "HighContrastTheme",
    "OceanicTheme",
    "ForestTheme",
    "MidnightTheme",
    "SolarTheme",
    "THEMES"
]
