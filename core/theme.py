from PyQt6.QtWidgets import QApplication
import os


class ThemeManager:
    
    _current_theme = "light"

    AVAILABLE_THEMES = {
        "light": "Açık (Light)",
        "dark": "Koyu (Dark)",
        "midnight": "Gece (Midnight)",
        "forest": "Orman (Forest)",
        "oceanic": "Okyanus (Oceanic)",
        "solar": "Solar (Solarized)",
        "high_contrast": "Yüksek Kontrast (High Contrast)",
    }

    PALETTE = {
        "light": {
            "line_bg": "#f0f0f0",
            "line_text": "#808080",
            "line_border": "#c0c0c0",
            "highlight": "#e8f2fe",
            "syntax_key": "#d73a49",
            "syntax_str": "#032f62",
            "syntax_num": "#005cc5",
            "map_tiles": "OpenStreetMap"
        },
        "dark": {
            "line_bg": "#1e1e1e",
            "line_text": "#858585",
            "line_border": "#333333",
            "highlight": "#2a2d2e",
            "syntax_key": "#c678dd",
            "syntax_str": "#98c379",
            "syntax_num": "#d19a66",
            "map_tiles": "CartoDB dark_matter"
        },
        "midnight": {
            "line_bg": "#0f172a",
            "line_text": "#94a3b8",
            "line_border": "#1e293b",
            "highlight": "#1e293b",
            "syntax_key": "#c678dd",
            "syntax_str": "#38bdf8",
            "syntax_num": "#f59e0b",
            "map_tiles": "CartoDB dark_matter"
        },
        "forest": {
            "line_bg": "#1a2421",
            "line_text": "#a7f3d0",
            "line_border": "#2e4c36",
            "highlight": "#23332a",
            "syntax_key": "#4ade80",
            "syntax_str": "#facc15",
            "syntax_num": "#38bdf8",
            "map_tiles": "CartoDB dark_matter"
        },
        "oceanic": {
            "line_bg": "#0f1c24",
            "line_text": "#7dd3fc",
            "line_border": "#1e3a4b",
            "highlight": "#162a38",
            "syntax_key": "#38bdf8",
            "syntax_str": "#34d399",
            "syntax_num": "#fbbf24",
            "map_tiles": "CartoDB dark_matter"
        },
        "solar": {
            "line_bg": "#002b36",
            "line_text": "#93a1a1",
            "line_border": "#073642",
            "highlight": "#073642",
            "syntax_key": "#268bd2",
            "syntax_str": "#2aa198",
            "syntax_num": "#b58900",
            "map_tiles": "CartoDB dark_matter"
        },
        "high_contrast": {
            "line_bg": "#000000",
            "line_text": "#ffffff",
            "line_border": "#666666",
            "highlight": "#222222",
            "syntax_key": "#ffff00",
            "syntax_str": "#00ff00",
            "syntax_num": "#00ffff",
            "map_tiles": "CartoDB dark_matter"
        }
    }

    @classmethod
    def is_dark(cls, theme_name: str = None) -> bool:
        t = theme_name if theme_name is not None else cls._current_theme
        return t != "light"

    @classmethod
    def apply_theme(cls, app: QApplication, theme_name: str = "light"):
        if theme_name not in cls.AVAILABLE_THEMES:
            theme_name = "light"
        cls._current_theme = theme_name
        
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        qss_path = os.path.join(base_dir, "resources", "styles", f"{theme_name}.qss")
        
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                app.setStyleSheet(f.read())
        else:
            print(f"Warning: Theme file not found at {qss_path}")

    @classmethod
    def get_color(cls, key: str) -> str:
        palette = cls.PALETTE.get(cls._current_theme, cls.PALETTE["light"])
        return palette.get(key, "#000000")
        
    @classmethod
    def get_map_tiles(cls) -> str:
        palette = cls.PALETTE.get(cls._current_theme, cls.PALETTE["light"])
        return palette.get("map_tiles", "OpenStreetMap")