from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseTheme(ABC):
    name: str = "Base Theme"

    @property
    @abstractmethod
    def palette(self) -> Dict[str, str]:
        """Return the dictionary of palette colors."""
        pass

    @property
    def three_d_background(self) -> Dict[str, str]:
        return {'top': '#1e1e1e', 'bottom': '#000000'}

    @property
    def map_style(self) -> str:
        return 'carto_dark'

    @property
    def is_dark(self) -> bool:
        bg = self.palette.get('background', '#ffffff').lstrip('#')
        if len(bg) == 6:
            try:
                r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
                lum = 0.299 * r + 0.587 * g + 0.114 * b
                return lum < 128
            except ValueError:
                return True
        return True

    def get_color(self, key: str, default: str = "#000000") -> str:
        return self.palette.get(key, default)

    def generate_qss(self) -> str:
        p = self.palette
        bg = p.get('background', '#2b2b2b')
        bg_alt = p.get('background_alt', '#3c3f41')
        text = p.get('text', '#e0e0e0')
        primary = p.get('primary', '#4cc2ff')
        border = p.get('border', '#555555')
        input_bg = p.get('input_bg', '#3c3f41')
        btn_bg = p.get('button_bg', '#3c3f41')
        btn_hover = p.get('button_hover', '#4e5254')
        btn_pressed = p.get('button_pressed', '#5a5e61')
        hdr_bg = p.get('header_bg', '#323232')
        hdr_text = p.get('header_text', '#ffffff')
        sel_bg = p.get('selection_bg', '#094771')
        sel_text = p.get('selection_text', '#ffffff')

        return f"""
QWidget {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 13px;
    background-color: {bg};
    color: {text};
}}

QMainWindow {{
    background-color: {bg};
}}

QSplitter::handle {{
    background-color: {border};
    width: 2px;
}}

QSplitter::handle:hover {{
    background-color: {primary};
}}

QMenuBar {{
    background-color: {hdr_bg};
    color: {hdr_text};
    border-bottom: 1px solid {border};
    font-size: 12px;
}}

QMenuBar::item {{
    background-color: transparent;
    padding: 4px 10px;
}}

QMenuBar::item:selected {{
    background-color: {btn_hover};
    color: {hdr_text};
    border-radius: 4px;
}}

QMenu {{
    background-color: {bg_alt};
    border: 1px solid {border};
    padding: 3px 0px;
    font-size: 12px;
}}

QMenu::item {{
    padding: 4px 20px 4px 20px;
    color: {text};
}}

QMenu::item:selected {{
    background-color: {sel_bg};
    color: {sel_text};
}}

QPlainTextEdit, QTextEdit {{
    background-color: {input_bg};
    color: {text};
    border: 1px solid {border};
    selection-background-color: {sel_bg};
    selection-color: {sel_text};
}}

QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 10px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: {border};
    min-height: 20px;
    border-radius: 5px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background: {primary};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0px;
}}

QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 10px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background: {border};
    min-width: 20px;
    border-radius: 5px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {primary};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
    width: 0px;
}}

QTabWidget::pane {{
    border: none;
    background-color: {bg};
}}

QTabBar::tab {{
    background-color: {bg_alt};
    color: {text};
    padding: 6px 14px;
    border: none;
    border-right: 1px solid {border};
    border-bottom: 1px solid {border};
    font-size: 12px;
}}

QTabBar::tab:selected {{
    background-color: {bg};
    color: {primary};
    border-bottom: 2px solid {primary};
    font-weight: 600;
}}

QTabBar::tab:hover:!selected {{
    background-color: {btn_hover};
}}

QStatusBar {{
    background-color: {hdr_bg};
    color: {text};
    border-top: 1px solid {border};
    font-size: 11px;
}}

QStatusBar QLabel {{
    background-color: transparent;
    color: {text};
    padding: 0 4px;
}}

QLineEdit {{
    background-color: {input_bg};
    color: {text};
    border: 1px solid {border};
    padding: 4px 8px;
    border-radius: 3px;
}}

QLineEdit:focus {{
    border: 1px solid {primary};
}}

QDialog, QMessageBox {{
    background-color: {bg};
    color: {text};
}}

QMessageBox QLabel {{
    color: {text};
    font-size: 13px;
}}

QPushButton {{
    background-color: {btn_bg};
    color: {text};
    border: 1px solid {border};
    padding: 5px 12px;
    border-radius: 3px;
    min-height: 20px;
}}

QPushButton:hover {{
    background-color: {btn_hover};
    border-color: {primary};
    color: {hdr_text};
}}

QPushButton:pressed {{
    background-color: {btn_pressed};
}}

/* --- Activity Bar & Side Bar --- */
QWidget#activityBar {{
    background-color: {hdr_bg};
    border-right: 1px solid {border};
}}

QWidget#activityBar QPushButton#activityBtn {{
    background: transparent;
    border: none;
    font-size: 14px;
    width: 30px;
    height: 30px;
    min-width: 30px;
    max-width: 30px;
    min-height: 30px;
    max-height: 30px;
    padding: 0px;
    margin: 0px;
    border-radius: 4px;
    color: {text};
}}

QWidget#activityBar QPushButton#activityBtn:hover {{
    color: {hdr_text};
    background-color: {btn_hover};
}}

QWidget#activityBar QPushButton#activityBtn:checked {{
    color: {primary};
    background-color: {bg_alt};
    border-left: 2px solid {primary};
    border-radius: 0px;
}}

QWidget#sideBar {{
    background-color: {bg_alt};
    border-right: 1px solid {border};
}}

QWidget#sideBar QPushButton {{
    min-width: 0px;
    min-height: 0px;
}}

QWidget#sideBar QPushButton#sidebarHeaderBtn {{
    border: none;
    background: transparent;
    border-radius: 3px;
    width: 20px;
    height: 20px;
    min-width: 20px;
    max-width: 20px;
    min-height: 20px;
    max-height: 20px;
    padding: 0px;
    font-size: 11px;
    color: {text};
}}

QWidget#sideBar QPushButton#sidebarHeaderBtn:hover {{
    background-color: {btn_hover};
    color: {hdr_text};
}}

QWidget#sideBar QPushButton#sidebarPillBtn {{
    border: 1px solid {border};
    background-color: {btn_bg};
    border-radius: 2px;
    min-width: 40px;
    max-width: 46px;
    height: 18px;
    min-height: 18px;
    max-height: 18px;
    padding: 0px 4px;
    font-size: 9px;
    font-weight: 600;
    color: {text};
}}

QWidget#sideBar QPushButton#sidebarPillBtn:hover {{
    background-color: {btn_hover};
    border-color: {primary};
    color: {hdr_text};
}}

QWidget#sideBar QPushButton#sidebarActionBtn {{
    border: 1px solid {border};
    background-color: {btn_bg};
    border-radius: 3px;
    min-width: 48px;
    height: 22px;
    min-height: 22px;
    max-height: 22px;
    padding: 1px 6px;
    font-size: 10px;
    color: {text};
}}

QWidget#sideBar QPushButton#sidebarActionBtn:hover {{
    background-color: {btn_hover};
    border-color: {primary};
    color: {hdr_text};
}}

QTreeView, QTreeWidget {{
    background-color: {bg_alt};
    color: {text};
    border: none;
    font-size: 12px;
    outline: none;
}}

QTreeView::item, QTreeWidget::item {{
    padding: 3px 6px;
    border-radius: 3px;
}}

QTreeView::item:hover, QTreeWidget::item:hover {{
    background-color: {btn_hover};
}}

QTreeView::item:selected, QTreeWidget::item:selected {{
    background-color: {sel_bg};
    color: {sel_text};
}}

/* --- Attributes Table --- */
QTableView, QTableWidget {{
    background-color: {bg};
    alternate-background-color: {bg_alt};
    gridline-color: {border};
    border: 1px solid {border};
    color: {text};
    selection-background-color: {sel_bg};
    selection-color: {sel_text};
}}

QHeaderView::section {{
    background-color: {hdr_bg};
    color: {hdr_text};
    padding: 4px 8px;
    border: 1px solid {border};
    font-weight: bold;
    font-size: 11px;
}}

QComboBox, QDoubleSpinBox, QSpinBox {{
    background-color: {input_bg};
    border: 1px solid {border};
    color: {text};
    padding: 4px 8px;
    border-radius: 3px;
}}

QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border: 1px solid {primary};
}}

QProgressBar {{
    border: 1px solid {border};
    border-radius: 3px;
    background-color: {bg_alt};
    text-align: center;
    color: {text};
}}

QProgressBar::chunk {{
    background-color: {primary};
    border-radius: 2px;
}}
"""
