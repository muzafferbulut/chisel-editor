import os
from typing import Optional, Callable
from PyQt6.QtWidgets import QFrame, QPushButton, QWidget
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from ui.icons import get_lucide_icon
from core.theme import ThemeManager


def create_vsep(parent=None) -> QFrame:
    """Creates a consistent vertical separator for application toolbars."""
    sep = QFrame(parent)
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    sep.setStyleSheet("background-color: rgba(128, 128, 128, 0.25); width: 1px; margin: 3px 2px; border: none;")
    return sep


def get_tool_icon(icon_name: str, theme_name: Optional[str] = None) -> QIcon:
    """
    Retrieves crisp, theme-aware vector Lucide QIcon with fallback to legacy PNG.
    """
    try:
        icon = get_lucide_icon(icon_name, theme_name=theme_name)
        if not icon.isNull():
            return icon
    except Exception:
        pass

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(base_dir, "resources", "icons", f"{icon_name}.png")
    if os.path.isfile(icon_path):
        return QIcon(icon_path)
    return QIcon()


def create_tool_button(
    icon_name: str,
    fallback_text: str = "",
    tooltip: str = "",
    callback: Optional[Callable] = None,
    checkable: bool = False,
    size: int = 28,
    icon_size: int = 16,
    obj_name: str = "",
    parent=None
) -> QPushButton:
    """
    Creates a standard, modern theme-adaptive toolbar button.
    """
    btn = QPushButton(parent)
    icon = get_tool_icon(icon_name)
    if not icon.isNull():
        btn.setIcon(icon)
        btn.setIconSize(QSize(icon_size, icon_size))
    elif fallback_text:
        btn.setText(fallback_text)

    if tooltip:
        btn.setToolTip(tooltip)
    btn.setFixedSize(size, size)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if obj_name:
        btn.setObjectName(obj_name)
    if checkable:
        btn.setCheckable(True)

    if callback:
        if checkable:
            btn.toggled.connect(callback)
        else:
            btn.clicked.connect(callback)
    return btn


def refresh_tool_buttons(button_map: dict, theme_name: Optional[str] = None):
    """
    Re-applies theme-adaptive vector icons to buttons when the application theme changes.
    button_map format: {QPushButton: icon_name_str}
    """
    for btn, icon_name in button_map.items():
        icon = get_tool_icon(icon_name, theme_name=theme_name)
        if not icon.isNull():
            btn.setIcon(icon)


def get_toolbar_button_qss(container_id: str, theme_name: Optional[str] = None) -> str:
    """
    Generates unified toolbar button styling adhering to active theme tokens.
    """
    tokens = ThemeManager.get_tokens(theme_name)
    text = tokens.get("text", "#1e293b")
    hover = tokens.get("hover", "rgba(128,128,128,0.18)")
    active = tokens.get("active", "rgba(128,128,128,0.30)")
    accent = tokens.get("accent", "#0284c7")
    border = tokens.get("border", "#e2e8f0")

    return f"""
        #{container_id} QPushButton {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 4px;
            min-width: 28px;
            max-width: 28px;
            min-height: 28px;
            max-height: 28px;
            padding: 0px;
            color: {text};
        }}
        #{container_id} QPushButton:hover {{
            background-color: {hover};
            border: 1px solid {border};
        }}
        #{container_id} QPushButton:pressed, #{container_id} QPushButton:checked {{
            background-color: {active};
            border: 1px solid {accent};
        }}
        #{container_id} QPushButton:disabled {{
            opacity: 0.35;
        }}
    """

