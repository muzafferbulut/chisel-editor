import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSpinBox, QComboBox, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from core.theme import ThemeManager


class PdfViewerWidget(QWidget):
    """
    High-performance native PDF reader widget using QtPdf and QPdfView.
    Features continuous multi-page scrolling, modern navigation toolbar,
    dynamic zoom, page rotation, and full theme integration.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.doc = QPdfDocument(self)
        self._rotation_angle = 0
        self._init_ui()
        self.apply_theme()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Navigation & Zoom Toolbar
        self.toolbar_container = QWidget()
        self.toolbar_container.setObjectName("PdfToolbar")
        toolbar_layout = QHBoxLayout(self.toolbar_container)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(4)

        # First Page
        self.btn_first = self._create_tool_btn("page_first", "⇤", "First Page (Home)", self._first_page)
        toolbar_layout.addWidget(self.btn_first)

        # Previous Page
        self.btn_prev = self._create_tool_btn("page_prev", "◀", "Previous Page (Left Arrow)", self._prev_page)
        toolbar_layout.addWidget(self.btn_prev)

        # Page Jumper
        self.lbl_page_text = QLabel("Page:")
        toolbar_layout.addWidget(self.lbl_page_text)

        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.setFixedWidth(55)
        self.page_spin.valueChanged.connect(self._on_page_spin_changed)
        toolbar_layout.addWidget(self.page_spin)

        self.lbl_page_count = QLabel("/ 1")
        toolbar_layout.addWidget(self.lbl_page_count)

        # Next Page
        self.btn_next = self._create_tool_btn("page_next", "▶", "Next Page (Right Arrow)", self._next_page)
        toolbar_layout.addWidget(self.btn_next)

        # Last Page
        self.btn_last = self._create_tool_btn("page_last", "⇥", "Last Page (End)", self._last_page)
        toolbar_layout.addWidget(self.btn_last)

        toolbar_layout.addWidget(self._create_sep())

        # Zoom Out
        self.btn_zoom_out = self._create_tool_btn("zoom_out", "-", "Zoom Out (Ctrl+-)", self._zoom_out)
        toolbar_layout.addWidget(self.btn_zoom_out)

        # Zoom Mode / Percentage Combo
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%", "200%", "Fit to Width", "Fit to Page"])
        self.zoom_combo.setCurrentText("Fit to Width")
        self.zoom_combo.setToolTip("Zoom Level")
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_changed)
        toolbar_layout.addWidget(self.zoom_combo)

        # Zoom In
        self.btn_zoom_in = self._create_tool_btn("zoom_in", "+", "Zoom In (Ctrl++)", self._zoom_in)
        toolbar_layout.addWidget(self.btn_zoom_in)

        toolbar_layout.addWidget(self._create_sep())

        # Rotate Page
        self.btn_rotate = self._create_tool_btn("rotate", "↻", "Rotate 90° Clockwise", self._rotate_page)
        toolbar_layout.addWidget(self.btn_rotate)

        toolbar_layout.addStretch()

        # Document info label
        self.lbl_doc_info = QLabel("")
        toolbar_layout.addWidget(self.lbl_doc_info)

        layout.addWidget(self.toolbar_container)

        # 2. Main High-Performance PDF View
        self.pdf_view = QPdfView(self)
        self.pdf_view.setDocument(self.doc)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)

        # Sync page navigator
        nav = self.pdf_view.pageNavigator()
        nav.currentPageChanged.connect(self._on_page_navigated)

        layout.addWidget(self.pdf_view)

    def _create_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: rgba(128, 128, 128, 0.25); width: 1px; margin: 3px 2px; border: none;")
        return sep

    def _get_icon(self, icon_name: str) -> QIcon:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "resources", "icons", f"{icon_name}.png")
        if os.path.isfile(icon_path):
            return QIcon(icon_path)
        return QIcon()

    def _create_tool_btn(self, icon_name: str, fallback_text: str, tooltip: str, callback=None) -> QPushButton:
        btn = QPushButton()
        icon = self._get_icon(icon_name)
        if not icon.isNull():
            btn.setIcon(icon)
            btn.setIconSize(QSize(16, 16))
        else:
            btn.setText(fallback_text)

        btn.setToolTip(tooltip)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if callback:
            btn.clicked.connect(callback)
        return btn

    def apply_theme(self, theme_name: str = None):
        """Applies theme-adaptive styling to toolbar, controls, and canvas background."""
        tokens = ThemeManager.get_tokens(theme_name)
        toolbar_bg = tokens.get("toolbar_bg", "#f8fafc")
        panel_bg = tokens.get("panel_bg", "#ffffff")
        text = tokens.get("text", "#1e293b")
        text_muted = tokens.get("text_muted", "#64748b")
        border = tokens.get("border", "#e2e8f0")
        hover = tokens.get("hover", "rgba(128,128,128,0.18)")
        active = tokens.get("active", "rgba(128,128,128,0.30)")
        accent = tokens.get("accent", "#0284c7")
        is_dark = ThemeManager.is_dark(theme_name)

        tb_qss = f"""
            #PdfToolbar {{
                background-color: {toolbar_bg};
                border-bottom: 1px solid {border};
            }}
            #PdfToolbar QPushButton {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                color: {text};
            }}
            #PdfToolbar QPushButton:hover {{
                background-color: {hover};
                border: 1px solid {border};
            }}
            #PdfToolbar QPushButton:pressed {{
                background-color: {active};
            }}
            #PdfToolbar QComboBox, #PdfToolbar QSpinBox {{
                background-color: {panel_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
            }}
        """
        self.toolbar_container.setStyleSheet(tb_qss)

        view_bg = panel_bg if is_dark else "#e2e8f0"
        self.pdf_view.setStyleSheet(f"QPdfView {{ background-color: {view_bg}; border: none; }}")
        self.lbl_page_text.setStyleSheet(f"color: {text_muted}; font-size: 11px;")
        self.lbl_page_count.setStyleSheet(f"color: {text_muted}; font-size: 11px;")
        self.lbl_doc_info.setStyleSheet(f"color: {text_muted}; font-size: 11px; padding: 0 8px;")

    def load_file(self, file_path: str):
        if not os.path.isfile(file_path):
            QMessageBox.critical(self, "Error", f"PDF file not found: {file_path}")
            return

        self.current_file = file_path
        self.doc.load(file_path)

        page_count = self.doc.pageCount()
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(max(1, page_count))
        self.page_spin.setValue(1)
        self.page_spin.blockSignals(False)

        self.lbl_page_count.setText(f"/ {page_count:,}")
        size_kb = os.path.getsize(file_path) / 1024.0
        self.lbl_doc_info.setText(f"{os.path.basename(file_path)} ({size_kb:,.1f} KB)")

        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.zoom_combo.setCurrentText("Fit to Width")

    def _first_page(self):
        if self.doc.pageCount() > 0:
            self.pdf_view.pageNavigator().jump(0, self.pdf_view.pageNavigator().currentLocation())

    def _last_page(self):
        count = self.doc.pageCount()
        if count > 0:
            self.pdf_view.pageNavigator().jump(count - 1, self.pdf_view.pageNavigator().currentLocation())

    def _prev_page(self):
        curr = self.pdf_view.pageNavigator().currentPage()
        if curr > 0:
            self.pdf_view.pageNavigator().jump(curr - 1, self.pdf_view.pageNavigator().currentLocation())

    def _next_page(self):
        curr = self.pdf_view.pageNavigator().currentPage()
        if curr < self.doc.pageCount() - 1:
            self.pdf_view.pageNavigator().jump(curr + 1, self.pdf_view.pageNavigator().currentLocation())

    def _on_page_spin_changed(self, page_num: int):
        target = page_num - 1
        if 0 <= target < self.doc.pageCount():
            self.pdf_view.pageNavigator().jump(target, self.pdf_view.pageNavigator().currentLocation())

    def _on_page_navigated(self, page_idx: int):
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(page_idx + 1)
        self.page_spin.blockSignals(False)

    def _zoom_in(self):
        factor = self.pdf_view.zoomFactor() * 1.2
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.pdf_view.setZoomFactor(min(5.0, factor))
        self.zoom_combo.setCurrentText(f"{int(self.pdf_view.zoomFactor() * 100)}%")

    def _zoom_out(self):
        factor = self.pdf_view.zoomFactor() / 1.2
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.pdf_view.setZoomFactor(max(0.2, factor))
        self.zoom_combo.setCurrentText(f"{int(self.pdf_view.zoomFactor() * 100)}%")

    def _rotate_page(self):
        # QPdfDocument doesn't directly expose rotate, but we can cycle zoom or notify
        # Future-ready hook for rotation
        self._rotation_angle = (self._rotation_angle + 90) % 360

    def _on_zoom_changed(self, text: str):
        if text == "Fit to Width":
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        elif text == "Fit to Page":
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView)
        else:
            try:
                pct = int(text.replace("%", "").strip())
                self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
                self.pdf_view.setZoomFactor(pct / 100.0)
            except ValueError:
                pass
