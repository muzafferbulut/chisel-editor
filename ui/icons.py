"""
Lucide Vector Icons helper for PyQt6 in Chisel Editor.
Provides crisp, theme-adaptive vector icons directly from Lucide SVG definitions.
"""
from typing import Optional
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtSvg import QSvgRenderer

LUCIDE_SVGS: dict[str, str] = {
    # Navigation & Zoom
    "zoom-in": '<circle cx="11" cy="11" r="8"/><line x1="21" x2="16.65" y1="21" y2="16.65"/><line x1="11" x2="11" y1="8" y2="14"/><line x1="8" x2="14" y1="11" y2="11"/>',
    "zoom-out": '<circle cx="11" cy="11" r="8"/><line x1="21" x2="16.65" y1="21" y2="16.65"/><line x1="8" x2="14" y1="11" y2="11"/>',
    "focus": '<circle cx="12" cy="12" r="3"/><path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/>',
    "search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',

    # Selection Tools
    "box-select": '<path d="M5 3a2 2 0 0 0-2 2"/><path d="M19 3a2 2 0 0 1 2 2"/><path d="M21 19a2 2 0 0 1-2 2"/><path d="M5 21a2 2 0 0 1-2-2"/><path d="M9 3h1"/><path d="M9 21h1"/><path d="M14 3h1"/><path d="M14 21h1"/><path d="M3 9v1"/><path d="M21 9v1"/><path d="M3 14v1"/><path d="M21 14v1"/>',
    "square-check": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="m9 12 2 2 4-4"/>',
    "check-square": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="m9 12 2 2 4-4"/>',
    "square-x": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>',
    "refresh-cw": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "filter": '<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>',
    "list-filter": '<path d="M3 6h18"/><path d="M7 12h10"/><path d="M10 18h4"/>',

    # Table / Row / Field Data Operations
    "list-plus": '<path d="M11 12H3"/><path d="M16 6H3"/><path d="M16 18H3"/><path d="M18 9v6"/><path d="M21 12h-6"/>',
    "column-plus": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M10 3v18"/><path d="M16 8v6"/><path d="M19 11h-6"/>',
    "table": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M12 3v18"/>',
    "table-columns-split": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M12 3v18"/>',

    # Edit & Calculation Tools
    "pencil": '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>',
    "calculator": '<rect width="16" height="20" x="4" y="2" rx="2"/><line x1="8" x2="16" y1="6" y2="6"/><line x1="16" x2="16" y1="14" y2="18"/><path d="M16 10h.01"/><path d="M12 10h.01"/><path d="M8 10h.01"/><path d="M12 14h.01"/><path d="M8 14h.01"/><path d="M12 18h.01"/><path d="M8 18h.01"/>',
    "bar-chart-2": '<line x1="18" x2="18" y1="20" y2="10"/><line x1="12" x2="12" y1="20" y2="4"/><line x1="6" x2="6" y1="20" y2="14"/>',
    "trash-2": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>',

    # Export & Generic
    "file-down": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M12 18v-6"/><path d="m9 15 3 3 3-3"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "check": '<polyline points="20 6 9 17 4 12"/>',
    "plus": '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    "minus": '<line x1="5" y1="12" x2="19" y2="12"/>',
    "save": '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
    "eye": '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/>',
    "eye-off": '<path d="9.88 9.88a3 3 0 1 0 4.24 4.24"/><path d="10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/><path d="6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/><line x1="2" x2="22" y1="2" y2="22"/>',
    "rotate-ccw": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    "rotate-cw": '<path d="M21 12a9 9 0 1 1-9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/>',

    # Rich Text & Formatting Tools
    "bold": '<path d="M6 12h9a4 4 0 0 1 0 8H6v-8zm0 0h8a3.5 3.5 0 0 0 0-7H6v7z"/>',
    "italic": '<line x1="19" x2="10" y1="4" y2="4"/><line x1="14" x2="5" y1="20" y2="20"/><line x1="15" x2="9" y1="4" y2="20"/>',
    "underline": '<path d="M6 4v6a6 6 0 0 0 12 0V4"/><line x1="4" x2="20" y1="20" y2="20"/>',
    "strikethrough": '<path d="M16 4H9a3 3 0 0 0-2.83 4"/><path d="M14 12a4 4 0 0 1 0 8H6"/><line x1="4" x2="20" y1="12" y2="12"/>',
    "type": '<polyline points="4 7 4 4 20 4 20 7"/><line x1="9" x2="15" y1="20" y2="20"/><line x1="12" x2="12" y1="4" y2="20"/>',
    "highlighter": '<path d="m9 11-6 6v3h9l3-3"/><path d="m22 12-4.6 4.6a2 2 0 0 1-2.8 0l-5.2-5.2a2 2 0 0 1 0-2.8L14 4"/>',
    "align-left": '<line x1="21" x2="3" y1="6" y2="6"/><line x1="15" x2="3" y1="12" y2="12"/><line x1="17" x2="3" y1="18" y2="18"/>',
    "align-center": '<line x1="21" x2="3" y1="6" y2="6"/><line x1="19" x2="5" y1="12" y2="12"/><line x1="21" x2="3" y1="18" y2="18"/>',
    "align-right": '<line x1="21" x2="3" y1="6" y2="6"/><line x1="21" x2="9" y1="12" y2="12"/><line x1="21" x2="7" y1="18" y2="18"/>',
    "align-justify": '<line x1="21" x2="3" y1="6" y2="6"/><line x1="21" x2="3" y1="12" y2="12"/><line x1="21" x2="3" y1="18" y2="18"/>',
    "list": '<line x1="8" x2="21" y1="6" y2="6"/><line x1="8" x2="21" y1="12" y2="12"/><line x1="8" x2="21" y1="18" y2="18"/><line x1="3" x2="3.01" y1="6" y2="6"/><line x1="3" x2="3.01" y1="12" y2="12"/><line x1="3" x2="3.01" y1="18" y2="18"/>',
    "list-ordered": '<line x1="10" x2="21" y1="6" y2="6"/><line x1="10" x2="21" y1="12" y2="12"/><line x1="10" x2="21" y1="18" y2="18"/><path d="M4 6h1v4"/><path d="M4 10h2"/><path d="M6 18H4c0-1 2-2 2-3s-1-1.5-2-1"/>',
    "contrast": '<circle cx="12" cy="12" r="10"/><path d="M12 18a6 6 0 0 0 0-12v12z"/>',

    # Navigation & Paging
    "chevrons-left": '<polyline points="11 17 6 12 11 7"/><polyline points="18 17 13 12 18 7"/>',
    "chevron-left": '<polyline points="15 18 9 12 15 6"/>',
    "chevron-right": '<polyline points="9 18 15 12 9 6"/>',
    "chevrons-right": '<polyline points="13 17 18 12 13 7"/><polyline points="6 17 11 12 6 7"/>',
    "arrow-left-right": '<polyline points="8 3 4 7 8 11"/><polyline points="16 21 20 17 16 13"/><line x1="4" x2="20" y1="7" y2="7"/><line x1="20" x2="4" y1="17" y2="17"/>',
    "eraser": '<path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21"/><path d="M22 21H7"/><path d="m5 11 9 9"/>',
    "play": '<polygon points="6 3 20 12 6 21 6 3"/>',
    "wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    "zap": '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    "alert-triangle": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "check-circle-2": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
}

# Aliases mapping project/action names to canonical Lucide SVG names
ICON_ALIASES: dict[str, str] = {
    "play": "play",
    "wrench": "wrench",
    "zap": "zap",
    "alert": "alert-triangle",
    "info": "info",
    "check_circle": "check-circle-2",
    "zoom_to_selected": "zoom-in",
    "box_select": "box-select",
    "select_box": "box-select",
    "select_all": "square-check",
    "invert_selection": "refresh-cw",
    "clear_selection": "square-x",
    "show_selected": "filter",
    "add_row": "list-plus",
    "add_field": "column-plus",
    "add_col": "column-plus",
    "edit_geometry": "pencil",
    "calc_geom": "calculator",
    "statistics": "bar-chart-2",
    "delete_selected": "trash-2",
    "delete_row": "trash-2",
    "delete_col": "trash-2",
    "export_csv": "file-down",
    "close": "x",
    # Formatting & Document Tools
    "strike": "strikethrough",
    "text_color": "type",
    "bg_color": "highlighter",
    "align_left": "align-left",
    "align_center": "align-center",
    "align_right": "align-right",
    "align_justify": "align-justify",
    "list_bullet": "list",
    "list_num": "list-ordered",
    "paper_mode": "contrast",
    "undo": "rotate-ccw",
    "redo": "rotate-cw",
    "rotate": "rotate-cw",
    "page_first": "chevrons-left",
    "page_prev": "chevron-left",
    "page_next": "chevron-right",
    "page_last": "chevrons-right",
    "zoom_in": "zoom-in",
    "zoom_out": "zoom-out",
    "autofit": "arrow-left-right",
    "clear_cells": "eraser",
}


def _get_theme_colors(theme_name: Optional[str] = None) -> tuple[str, str]:
    """Retrieve text (normal) and text_muted (disabled) colors from ThemeManager."""
    try:
        from core.theme import ThemeManager
        tokens = ThemeManager.get_tokens(theme_name)
        color = tokens.get("text", "#cbd5e1")
        disabled_color = tokens.get("text_muted", "#64748b")
        return color, disabled_color
    except Exception:
        return "#cbd5e1", "#64748b"


def get_lucide_svg(
    name: str,
    color: str = "#cbd5e1",
    stroke_width: float = 2.0,
    size: int = 24
) -> str:
    """Returns a standalone SVG XML string for a Lucide icon."""
    canonical = ICON_ALIASES.get(name, name)
    body = LUCIDE_SVGS.get(canonical, "")
    if not body:
        return ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )


def render_svg_pixmap(svg_xml: str, size: int = 32) -> QPixmap:
    """Renders SVG XML string to an anti-aliased transparent QPixmap."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    if not svg_xml:
        return pixmap
    renderer = QSvgRenderer(QByteArray(svg_xml.encode("utf-8")))
    if renderer.isValid():
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
    return pixmap


def get_lucide_icon(
    name: str,
    color: Optional[str] = None,
    disabled_color: Optional[str] = None,
    theme_name: Optional[str] = None,
    size: int = 32,
    stroke_width: float = 2.0
) -> QIcon:
    """
    Creates a crisp, theme-aware vector QIcon from a Lucide definition.
    Includes both Normal and Disabled state pixmaps.
    """
    canonical = ICON_ALIASES.get(name, name)
    body = LUCIDE_SVGS.get(canonical, "")
    if not body:
        return QIcon()

    default_color, default_disabled = _get_theme_colors(theme_name)
    clr = color or default_color
    dis_clr = disabled_color or default_disabled

    svg_normal = get_lucide_svg(canonical, color=clr, stroke_width=stroke_width, size=24)
    svg_disabled = get_lucide_svg(canonical, color=dis_clr, stroke_width=stroke_width, size=24)

    pm_normal = render_svg_pixmap(svg_normal, size=size)
    pm_disabled = render_svg_pixmap(svg_disabled, size=size)

    icon = QIcon()
    icon.addPixmap(pm_normal, QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(pm_disabled, QIcon.Mode.Disabled, QIcon.State.Off)
    return icon

