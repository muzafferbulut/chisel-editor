from PyQt6.QtWidgets import QApplication
from typing import Dict, Optional, List, Tuple
import os

from core.themes import THEMES, BaseTheme, DarkTheme, LightTheme


class ThemeManager:
    _current_theme: str = "dark"
    _current_theme_instance: BaseTheme = THEMES["dark"]

    @classmethod
    def get_theme(cls, theme_key: str) -> BaseTheme:
        return THEMES.get(theme_key, THEMES["dark"])

    @classmethod
    def current_theme(cls) -> BaseTheme:
        return cls._current_theme_instance

    @classmethod
    def get_available_themes(cls) -> Dict[str, str]:
        """Returns dict of {theme_key: display_name}."""
        return {k: theme.name for k, theme in THEMES.items()}

    @classmethod
    def is_dark(cls) -> bool:
        if cls._current_theme_instance:
            return cls._current_theme_instance.is_dark
        return cls._current_theme in ("dark", "high_contrast", "oceanic", "forest", "midnight", "solar")

    @classmethod
    def apply_theme(cls, app: QApplication, theme_name: str = "dark"):
        if theme_name in THEMES:
            cls._current_theme = theme_name
            cls._current_theme_instance = THEMES[theme_name]
        else:
            # Check by display name
            matched = False
            for k, t in THEMES.items():
                if t.name.lower() == theme_name.lower():
                    cls._current_theme = k
                    cls._current_theme_instance = t
                    matched = True
                    break
            if not matched:
                cls._current_theme = "dark"
                cls._current_theme_instance = THEMES["dark"]

        # Generate cohesive QSS from theme instance
        qss_content = cls._current_theme_instance.generate_qss()
        if app:
            app.setStyleSheet(qss_content)

        # Also write/cache qss file in resources/styles for persistence
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        styles_dir = os.path.join(base_dir, "resources", "styles")
        os.makedirs(styles_dir, exist_ok=True)
        qss_file = os.path.join(styles_dir, f"{cls._current_theme}.qss")
        try:
            with open(qss_file, "w", encoding="utf-8") as f:
                f.write(qss_content)
        except Exception:
            pass

    @classmethod
    def get_color(cls, key: str, default: str = "#000000") -> str:
        return cls._current_theme_instance.get_color(key, default)

    @classmethod
    def get_map_tiles(cls) -> str:
        return cls._current_theme_instance.map_style