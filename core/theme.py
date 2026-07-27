from PyQt6.QtWidgets import QApplication
import os

class ThemeManager:
    
    _current_theme = "light"

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
            "highlight": "#264f78",
            "syntax_key": "#c678dd",
            "syntax_str": "#98c379",
            "syntax_num": "#d19a66",
            "map_tiles": "CartoDB dark_matter"
        }
    }

    @classmethod
    def apply_theme(cls, app: QApplication, theme_name: str = "light"):
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
        return cls.PALETTE[cls._current_theme].get(key, "#000000")
        
    @classmethod
    def get_map_tiles(cls) -> str:
        return cls.PALETTE[cls._current_theme].get("map_tiles", "OpenStreetMap")