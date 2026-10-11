from PyQt6.QtWidgets import QApplication
import os


class ThemeManager:
    
    _current_theme = "light"

    AVAILABLE_THEMES = {
        "light": "Light",
        "dark": "Dark",
        "midnight": "Midnight",
        "forest": "Forest",
        "oceanic": "Oceanic",
        "solar": "Solarized",
        "high_contrast": "High Contrast",
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
            "map_tiles": "OpenStreetMap",
            "toolbar_bg": "#f8fafc",
            "panel_bg": "#ffffff",
            "text": "#1e293b",
            "text_muted": "#64748b",
            "border": "#e2e8f0",
            "hover": "#f1f5f9",
            "active": "#e2e8f0",
            "accent": "#0284c7",
            "grid_line": "#e2e8f0",
            "paper_bg": "#ffffff",
            "paper_text": "#1e293b",
        },
        "dark": {
            "line_bg": "#1e1e1e",
            "line_text": "#858585",
            "line_border": "#333333",
            "highlight": "#2a2d2e",
            "syntax_key": "#c678dd",
            "syntax_str": "#98c379",
            "syntax_num": "#d19a66",
            "map_tiles": "CartoDB dark_matter",
            "toolbar_bg": "#252526",
            "panel_bg": "#1e1e1e",
            "text": "#cccccc",
            "text_muted": "#858585",
            "border": "#3c3c3c",
            "hover": "#333333",
            "active": "#37373d",
            "accent": "#007acc",
            "grid_line": "#333333",
            "paper_bg": "#252526",
            "paper_text": "#e0e0e0",
        },
        "midnight": {
            "line_bg": "#0f172a",
            "line_text": "#94a3b8",
            "line_border": "#1e293b",
            "highlight": "#1e293b",
            "syntax_key": "#c678dd",
            "syntax_str": "#38bdf8",
            "syntax_num": "#f59e0b",
            "map_tiles": "CartoDB dark_matter",
            "toolbar_bg": "#1e1b4b",
            "panel_bg": "#0f0c29",
            "text": "#e0c3fc",
            "text_muted": "#9d8bb6",
            "border": "#3c096c",
            "hover": "#2d1654",
            "active": "#3c096c",
            "accent": "#9d4edd",
            "grid_line": "#24103f",
            "paper_bg": "#1a1638",
            "paper_text": "#e0c3fc",
        },
        "forest": {
            "line_bg": "#1a2421",
            "line_text": "#a7f3d0",
            "line_border": "#2e4c36",
            "highlight": "#23332a",
            "syntax_key": "#4ade80",
            "syntax_str": "#facc15",
            "syntax_num": "#38bdf8",
            "map_tiles": "CartoDB dark_matter",
            "toolbar_bg": "#16201b",
            "panel_bg": "#131a16",
            "text": "#d1fae5",
            "text_muted": "#6ee7b7",
            "border": "#263e2e",
            "hover": "#1d2e23",
            "active": "#2b4533",
            "accent": "#10b981",
            "grid_line": "#1c2c21",
            "paper_bg": "#18231c",
            "paper_text": "#d1fae5",
        },
        "oceanic": {
            "line_bg": "#0f1c24",
            "line_text": "#7dd3fc",
            "line_border": "#1e3a4b",
            "highlight": "#162a38",
            "syntax_key": "#38bdf8",
            "syntax_str": "#34d399",
            "syntax_num": "#fbbf24",
            "map_tiles": "CartoDB dark_matter",
            "toolbar_bg": "#0e202c",
            "panel_bg": "#0b1821",
            "text": "#e0f2fe",
            "text_muted": "#7dd3fc",
            "border": "#1e3a4b",
            "hover": "#152e3e",
            "active": "#1e445b",
            "accent": "#0ea5e9",
            "grid_line": "#132836",
            "paper_bg": "#0f222e",
            "paper_text": "#e0f2fe",
        },
        "solar": {
            "line_bg": "#002b36",
            "line_text": "#93a1a1",
            "line_border": "#073642",
            "highlight": "#073642",
            "syntax_key": "#268bd2",
            "syntax_str": "#2aa198",
            "syntax_num": "#b58900",
            "map_tiles": "CartoDB dark_matter",
            "toolbar_bg": "#073642",
            "panel_bg": "#002b36",
            "text": "#93a1a1",
            "text_muted": "#657b83",
            "border": "#094352",
            "hover": "#0a4c5c",
            "active": "#0e5a6c",
            "accent": "#268bd2",
            "grid_line": "#073642",
            "paper_bg": "#05303c",
            "paper_text": "#93a1a1",
        },
        "high_contrast": {
            "line_bg": "#000000",
            "line_text": "#ffffff",
            "line_border": "#666666",
            "highlight": "#222222",
            "syntax_key": "#ffff00",
            "syntax_str": "#00ff00",
            "syntax_num": "#00ffff",
            "map_tiles": "CartoDB dark_matter",
            "toolbar_bg": "#000000",
            "panel_bg": "#000000",
            "text": "#ffffff",
            "text_muted": "#ffffff",
            "border": "#ffffff",
            "hover": "#333333",
            "active": "#555555",
            "accent": "#ffff00",
            "grid_line": "#444444",
            "paper_bg": "#000000",
            "paper_text": "#ffffff",
        }
    }

    @classmethod
    def get_tokens(cls, theme_name: str = None) -> dict:
        t = theme_name if theme_name is not None else cls._current_theme
        return cls.PALETTE.get(t, cls.PALETTE["light"])

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