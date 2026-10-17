from PyQt6.QtWidgets import QApplication
import os


class ThemeManager:
    
    _current_theme = "light"

    AVAILABLE_THEMES = {
        "dark": "Dark",
        "light": "Light",
    }

    PALETTE = {
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