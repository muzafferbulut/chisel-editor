import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QSpinBox, QComboBox, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView


class PdfViewerWidget(QWidget):
    """
    High-performance native PDF reader widget using QtPdf and QPdfView.
    Supports continuous multi-page scrolling, page jumping, zoom controls,
    and text selection.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.doc = QPdfDocument(self)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Navigation & Zoom Toolbar
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: rgba(128, 128, 128, 0.08); border-bottom: 1px solid rgba(128, 128, 128, 0.2);")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(6)

        # Previous Page
        self.btn_prev = QPushButton("◀ Önceki")
        self.btn_prev.setToolTip("Önceki Sayfa (Sol Ok)")
        self.btn_prev.clicked.connect(self._prev_page)
        toolbar_layout.addWidget(self.btn_prev)

        # Page Jumper
        toolbar_layout.addWidget(QLabel("Sayfa:"))
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.valueChanged.connect(self._on_page_spin_changed)
        toolbar_layout.addWidget(self.page_spin)

        self.lbl_page_count = QLabel("/ 1")
        toolbar_layout.addWidget(self.lbl_page_count)

        # Next Page
        self.btn_next = QPushButton("Sonraki ▶")
        self.btn_next.setToolTip("Sonraki Sayfa (Sağ Ok)")
        self.btn_next.clicked.connect(self._next_page)
        toolbar_layout.addWidget(self.btn_next)

        toolbar_layout.addWidget(self._create_sep())

        # Zoom Out
        self.btn_zoom_out = QPushButton("🔍 -")
        self.btn_zoom_out.setToolTip("Uzaklaştır (Ctrl+-)")
        self.btn_zoom_out.clicked.connect(self._zoom_out)
        toolbar_layout.addWidget(self.btn_zoom_out)

        # Zoom Mode / Percentage Combo
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["%50", "%75", "%100", "%125", "%150", "%200", "Genişliğe Sığdır", "Sayfaya Sığdır"])
        self.zoom_combo.setCurrentText("%100")
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_changed)
        toolbar_layout.addWidget(self.zoom_combo)

        # Zoom In
        self.btn_zoom_in = QPushButton("🔍 +")
        self.btn_zoom_in.setToolTip("Yakınlaştır (Ctrl++)")
        self.btn_zoom_in.clicked.connect(self._zoom_in)
        toolbar_layout.addWidget(self.btn_zoom_in)

        toolbar_layout.addStretch()

        self.lbl_doc_info = QLabel("")
        self.lbl_doc_info.setStyleSheet("color: #858585; font-size: 11px;")
        toolbar_layout.addWidget(self.lbl_doc_info)

        layout.addWidget(toolbar)

        # 2. Main QPdfView
        self.pdf_view = QPdfView(self)
        self.pdf_view.setDocument(self.doc)
        self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.pdf_view.setZoomFactor(1.0)
        self.pdf_view.pageNavigator().currentPageChanged.connect(self._on_page_navigated)

        layout.addWidget(self.pdf_view)

    def _create_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: rgba(128, 128, 128, 0.25); width: 1px; margin: 2px 4px; border: none;")
        return sep

    def load_file(self, file_path: str):
        self.current_file = file_path
        status = self.doc.load(file_path)
        if status != QPdfDocument.Error.None_:
            QMessageBox.critical(self, "Hata", f"PDF belgesi yüklenemedi: {os.path.basename(file_path)}")
            return

        page_count = self.doc.pageCount()
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(max(1, page_count))
        self.page_spin.setValue(1)
        self.page_spin.blockSignals(False)

        self.lbl_page_count.setText(f"/ {page_count}")
        size_kb = os.path.getsize(file_path) / 1024
        self.lbl_doc_info.setText(f"{os.path.basename(file_path)} ({size_kb:,.1f} KB)")

        self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.zoom_combo.setCurrentText("Genişliğe Sığdır")

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
        self.zoom_combo.setCurrentText(f"%{int(self.pdf_view.zoomFactor() * 100)}")

    def _zoom_out(self):
        factor = self.pdf_view.zoomFactor() / 1.2
        self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.pdf_view.setZoomFactor(max(0.2, factor))
        self.zoom_combo.setCurrentText(f"%{int(self.pdf_view.zoomFactor() * 100)}")

    def _on_zoom_changed(self, text: str):
        if text == "Genişliğe Sığdır":
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        elif text == "Sayfaya Sığdır":
            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitInView)
        else:
            try:
                pct = int(text.replace("%", "").strip())
                self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
                self.pdf_view.setZoomFactor(pct / 100.0)
            except ValueError:
                pass

