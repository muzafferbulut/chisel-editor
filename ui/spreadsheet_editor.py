import os
import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QTabBar, QPushButton, QLineEdit, QLabel, QHeaderView, QMenu,
    QMessageBox, QInputDialog, QApplication, QFrame, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QKeySequence, QShortcut, QIcon
from handlers.excel import ExcelHandler
from core.theme import ThemeManager


class SpreadsheetEditorWidget(QWidget):
    """
    Interactive spreadsheet editor for Excel workbooks (.xlsx, .xls) and CSV tables (.csv).
    Features a modern theme-adaptive toolbar, multi-sheet navigation, formula/cell bar,
    in-cell editing, statistics, sorting, copy-paste, and direct export.
    """
    content_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self._sheets = {}  # {sheet_name: pd.DataFrame}
        self._current_sheet_name = None
        self._is_loading = False
        self._is_dirty = False
        self._init_ui()
        self.apply_theme()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 1. Top Action Toolbar (Theme-aware with icon buttons)
        self.toolbar_container = QWidget()
        self.toolbar_container.setObjectName("SpreadsheetToolbar")
        toolbar = QHBoxLayout(self.toolbar_container)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(4)

        # Row and Column Tools
        self.btn_add_row = self._create_tool_btn("add_row", "+R", "Satır Ekle (Seçili satırın altına yeni satır ekler)", self._add_row)
        toolbar.addWidget(self.btn_add_row)

        self.btn_del_row = self._create_tool_btn("delete_row", "-R", "Satır Sil (Seçili satırı siler)", self._del_row)
        toolbar.addWidget(self.btn_del_row)

        self.btn_add_col = self._create_tool_btn("add_col", "+C", "Sütun Ekle (Yeni sütun ekler)", self._add_column)
        toolbar.addWidget(self.btn_add_col)

        self.btn_del_col = self._create_tool_btn("delete_col", "-C", "Sütun Sil (Seçili sütunu siler)", self._del_column)
        toolbar.addWidget(self.btn_del_col)

        toolbar.addWidget(self._create_vsep())

        # Layout and Content Tools
        self.btn_autofit = self._create_tool_btn("autofit", "↔", "Sütun Genişliklerini Otomatik Sığdır", self._autofit_columns)
        toolbar.addWidget(self.btn_autofit)

        self.btn_clear = self._create_tool_btn("clear_cells", "✕", "Seçili Hücreleri Temizle (Delete)", self._clear_selected_cells)
        toolbar.addWidget(self.btn_clear)

        self.btn_stats = self._create_tool_btn("statistics", "📊", "Sütun İstatistikleri (Toplam, Ortalama, Min, Max)", self._show_column_stats)
        toolbar.addWidget(self.btn_stats)

        toolbar.addWidget(self._create_vsep())

        self.btn_export = self._create_tool_btn("export_csv", "💾", "Tabloyu CSV Olarak Dışa Aktar", self._export_to_csv)
        toolbar.addWidget(self.btn_export)

        toolbar.addStretch()

        # Search / Quick Filter Input
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Filtrele...")
        self.search_edit.setMaximumWidth(180)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._search_cells)
        toolbar.addWidget(self.search_edit)

        layout.addWidget(self.toolbar_container)

        # 2. Formula / Cell Coordinate Bar
        formula_bar = QHBoxLayout()
        formula_bar.setSpacing(6)

        self.lbl_cell_coord = QLabel("A1")
        self.lbl_cell_coord.setFixedWidth(54)
        self.lbl_cell_coord.setAlignment(Qt.AlignmentFlag.AlignCenter)
        formula_bar.addWidget(self.lbl_cell_coord)

        lbl_fx = QLabel("fx")
        lbl_fx.setStyleSheet("font-weight: bold; font-style: italic; color: #858585; padding: 0 2px;")
        formula_bar.addWidget(lbl_fx)

        self.cell_edit = QLineEdit()
        self.cell_edit.setPlaceholderText("Hücre değeri veya metin...")
        self.cell_edit.returnPressed.connect(self._apply_cell_edit)
        formula_bar.addWidget(self.cell_edit)

        layout.addLayout(formula_bar)

        # 3. Main Spreadsheet Table
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setDefaultSectionSize(110)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.currentCellChanged.connect(self._on_current_cell_changed)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table)

        # 4. Bottom Sheets Tab Bar
        sheet_bar_layout = QHBoxLayout()
        sheet_bar_layout.setSpacing(4)

        self.tab_bar = QTabBar()
        self.tab_bar.setShape(QTabBar.Shape.RoundedSouth)
        self.tab_bar.setMovable(False)
        self.tab_bar.currentChanged.connect(self._on_sheet_tab_changed)
        sheet_bar_layout.addWidget(self.tab_bar)

        self.btn_new_sheet = QPushButton("➕")
        self.btn_new_sheet.setFixedSize(26, 24)
        self.btn_new_sheet.setToolTip("Yeni Çalışma Sayfası Ekle")
        self.btn_new_sheet.clicked.connect(self._add_new_sheet)
        sheet_bar_layout.addWidget(self.btn_new_sheet)

        sheet_bar_layout.addStretch()

        self.lbl_status = QLabel("0 satır x 0 sütun")
        sheet_bar_layout.addWidget(self.lbl_status)

        layout.addLayout(sheet_bar_layout)

        # Keyboard shortcuts
        QShortcut(QKeySequence.StandardKey.Copy, self.table, self._copy_selection)
        QShortcut(QKeySequence.StandardKey.Paste, self.table, self._paste_selection)
        QShortcut(QKeySequence.StandardKey.Delete, self.table, self._clear_selected_cells)

    def _create_vsep(self) -> QFrame:
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
        """Applies dynamic theme styling to toolbar, table, formula bar, and headers."""
        tokens = ThemeManager.get_tokens(theme_name)
        bg = tokens.get("panel_bg", "#ffffff")
        toolbar_bg = tokens.get("toolbar_bg", "#f8fafc")
        text = tokens.get("text", "#1e293b")
        text_muted = tokens.get("text_muted", "#64748b")
        border = tokens.get("border", "#e2e8f0")
        hover = tokens.get("hover", "rgba(128,128,128,0.18)")
        active = tokens.get("active", "rgba(128,128,128,0.30)")
        accent = tokens.get("accent", "#0284c7")
        grid = tokens.get("grid_line", "#e2e8f0")
        is_dark = ThemeManager.is_dark(theme_name)
        alt_bg = tokens.get("hover", "#f8fafc") if not is_dark else tokens.get("active", "#252526")

        tb_qss = f"""
            #SpreadsheetToolbar QPushButton {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                color: {text};
            }}
            #SpreadsheetToolbar QPushButton:hover {{
                background-color: {hover};
                border: 1px solid {border};
            }}
            #SpreadsheetToolbar QPushButton:pressed {{
                background-color: {active};
            }}
            #SpreadsheetToolbar QPushButton:disabled {{
                background-color: transparent;
                border: 1px solid transparent;
                color: {text_muted};
            }}
        """
        self.toolbar_container.setStyleSheet(tb_qss)

        # Formula & search styling
        self.lbl_cell_coord.setStyleSheet(
            f"background-color: {toolbar_bg}; color: {accent}; border: 1px solid {border}; "
            f"border-radius: 4px; font-weight: bold; font-size: 11px;"
        )
        self.cell_edit.setStyleSheet(
            f"QLineEdit {{ background-color: {bg}; color: {text}; border: 1px solid {border}; "
            f"border-radius: 4px; padding: 3px 8px; font-size: 12px; }} "
            f"QLineEdit:focus {{ border: 1px solid {accent}; }}"
        )
        self.search_edit.setStyleSheet(
            f"QLineEdit {{ background-color: {bg}; color: {text}; border: 1px solid {border}; "
            f"border-radius: 4px; padding: 3px 8px; font-size: 12px; }} "
            f"QLineEdit:focus {{ border: 1px solid {accent}; }}"
        )
        self.lbl_status.setStyleSheet(f"color: {text_muted}; font-size: 11px; padding: 0 8px;")

        # Table & Headers styling
        table_qss = f"""
            QTableWidget {{
                background-color: {bg};
                color: {text};
                gridline-color: {grid};
                border: 1px solid {border};
                selection-background-color: {accent};
                selection-color: #ffffff;
                font-size: 12px;
            }}
            QTableWidget::item:alternate {{
                background-color: {alt_bg};
            }}
            QTableWidget::item:selected {{
                background-color: {accent};
                color: #ffffff;
            }}
            QHeaderView::section {{
                background-color: {toolbar_bg};
                color: {text_muted};
                border: 1px solid {border};
                padding: 4px 6px;
                font-weight: 600;
                font-size: 11px;
            }}
        """
        self.table.setStyleSheet(table_qss)

        # Sheet TabBar styling
        self.tab_bar.setStyleSheet(
            f"QTabBar::tab {{ background: {toolbar_bg}; color: {text_muted}; border: 1px solid {border}; "
            f"padding: 4px 12px; border-bottom-left-radius: 4px; border-bottom-right-radius: 4px; font-size: 11px; }} "
            f"QTabBar::tab:selected {{ background: {bg}; color: {accent}; font-weight: bold; border-top: 2px solid {accent}; }}"
        )

    @staticmethod
    def _col_idx_to_name(col_idx: int) -> str:
        """Converts 0 -> 'A', 25 -> 'Z', 26 -> 'AA'"""
        name = ""
        while col_idx >= 0:
            name = chr(col_idx % 26 + 65) + name
            col_idx = col_idx // 26 - 1
        return name

    def load_data(self, sheets: dict, file_path: str = None):
        """Populates spreadsheet from a dictionary of DataFrames."""
        if file_path:
            self.current_file = file_path
        self._is_loading = True
        try:
            self._sheets = sheets if sheets else {"Sayfa1": pd.DataFrame()}

            self.tab_bar.blockSignals(True)
            while self.tab_bar.count() > 0:
                self.tab_bar.removeTab(0)

            for sheet_name in self._sheets.keys():
                self.tab_bar.addTab(sheet_name)

            self.tab_bar.blockSignals(False)
            first_sheet = list(self._sheets.keys())[0]
            self._current_sheet_name = first_sheet
            self._load_sheet_data(first_sheet)
            self._is_dirty = False
        finally:
            self._is_loading = False

    def load_file(self, file_path: str):
        self.current_file = file_path
        handler = ExcelHandler()
        sheets = handler.read(file_path)
        self.load_data(sheets, file_path)

    def _load_sheet_data(self, sheet_name: str):
        df = self._sheets.get(sheet_name, pd.DataFrame())
        self._is_loading = True
        self.table.blockSignals(True)
        try:
            self.table.clear()
            rows, cols = df.shape

            self.table.setRowCount(rows)
            self.table.setColumnCount(cols)

            col_labels = [str(c) for c in df.columns]
            self.table.setHorizontalHeaderLabels(col_labels)

            for r in range(rows):
                for c in range(cols):
                    val = df.iat[r, c]
                    txt = "" if pd.isna(val) else str(val)
                    item = QTableWidgetItem(txt)
                    if isinstance(val, (int, float)) and not pd.isna(val):
                        item.setTextAlignment(int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter))
                    self.table.setItem(r, c, item)

            self.lbl_status.setText(f"{rows:,} satır x {cols} sütun")
        finally:
            self.table.blockSignals(False)
            self._is_loading = False

    def _sync_current_table_to_df(self):
        """Reads current table contents into self._sheets[self._current_sheet_name]"""
        if not self._current_sheet_name:
            return

        rows = self.table.rowCount()
        cols = self.table.columnCount()

        col_names = []
        for c in range(cols):
            header_item = self.table.horizontalHeaderItem(c)
            col_names.append(header_item.text() if header_item else self._col_idx_to_name(c))

        data = []
        for r in range(rows):
            row_vals = []
            for c in range(cols):
                item = self.table.item(r, c)
                row_vals.append(item.text() if item else "")
            data.append(row_vals)

        self._sheets[self._current_sheet_name] = pd.DataFrame(data, columns=col_names)

    def save_to_file(self, file_path: str = None):
        target = file_path or self.current_file
        if not target:
            return

        self._sync_current_table_to_df()
        handler = ExcelHandler()
        handler.write(target, self._sheets)
        self.current_file = target
        self._is_dirty = False

    def _on_sheet_tab_changed(self, index: int):
        if self._is_loading:
            return
        self._sync_current_table_to_df()
        sheet_name = self.tab_bar.tabText(index)
        self._current_sheet_name = sheet_name
        self._load_sheet_data(sheet_name)

    def _add_new_sheet(self):
        name, ok = QInputDialog.getText(self, "Yeni Çalışma Sayfası", "Sayfa Adı:", text=f"Sayfa{self.tab_bar.count() + 1}")
        if ok and name.strip():
            sheet_name = name.strip()
            if sheet_name in self._sheets:
                QMessageBox.warning(self, "Hata", "Bu isimde bir sayfa zaten mevcut.")
                return
            self._sync_current_table_to_df()
            self._sheets[sheet_name] = pd.DataFrame([[""] * 5] * 10)
            idx = self.tab_bar.addTab(sheet_name)
            self.tab_bar.setCurrentIndex(idx)
            self._is_dirty = True
            self.content_changed.emit()

    def _on_current_cell_changed(self, row: int, col: int):
        if row < 0 or col < 0:
            return
        col_letter = self._col_idx_to_name(col)
        self.lbl_cell_coord.setText(f"{col_letter}{row + 1}")
        item = self.table.item(row, col)
        self.cell_edit.blockSignals(True)
        self.cell_edit.setText(item.text() if item else "")
        self.cell_edit.blockSignals(False)

    def _apply_cell_edit(self):
        r = self.table.currentRow()
        c = self.table.currentColumn()
        if r >= 0 and c >= 0:
            text = self.cell_edit.text()
            item = self.table.item(r, c)
            if item is None:
                item = QTableWidgetItem(text)
                self.table.setItem(r, c, item)
            else:
                item.setText(text)
            self._on_item_changed(item)

    def _on_item_changed(self, item):
        if self._is_loading:
            return
        self._is_dirty = True
        self.content_changed.emit()
        r = self.table.currentRow()
        c = self.table.currentColumn()
        if item.row() == r and item.column() == c:
            self.cell_edit.blockSignals(True)
            self.cell_edit.setText(item.text())
            self.cell_edit.blockSignals(False)

    def _add_row(self):
        r = self.table.currentRow()
        idx = r + 1 if r >= 0 else self.table.rowCount()
        self.table.insertRow(idx)
        self._is_dirty = True
        self.content_changed.emit()
        self.lbl_status.setText(f"{self.table.rowCount():,} satır x {self.table.columnCount()} sütun")

    def _del_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            self._is_dirty = True
            self.content_changed.emit()
            self.lbl_status.setText(f"{self.table.rowCount():,} satır x {self.table.columnCount()} sütun")

    def _add_column(self):
        name, ok = QInputDialog.getText(self, "Sütun Ekle", "Sütun Adı:", text=f"Sütun{self.table.columnCount() + 1}")
        if ok and name.strip():
            col_idx = self.table.columnCount()
            self.table.insertColumn(col_idx)
            self.table.setHorizontalHeaderItem(col_idx, QTableWidgetItem(name.strip()))
            self._is_dirty = True
            self.content_changed.emit()
            self.lbl_status.setText(f"{self.table.rowCount():,} satır x {self.table.columnCount()} sütun")

    def _del_column(self):
        c = self.table.currentColumn()
        if c >= 0:
            self.table.removeColumn(c)
            self._is_dirty = True
            self.content_changed.emit()
            self.lbl_status.setText(f"{self.table.rowCount():,} satır x {self.table.columnCount()} sütun")

    def _autofit_columns(self):
        self.table.resizeColumnsToContents()

    def _clear_selected_cells(self):
        ranges = self.table.selectedRanges()
        if not ranges:
            return
        for r in ranges:
            for row in range(r.topRow(), r.bottomRow() + 1):
                for col in range(r.leftColumn(), r.rightColumn() + 1):
                    item = self.table.item(row, col)
                    if item:
                        item.setText("")
        self._is_dirty = True
        self.content_changed.emit()

    def _export_to_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "Tabloyu CSV Olarak Dışa Aktar", "tablo.csv", "CSV Dosyası (*.csv)")
        if path:
            self._sync_current_table_to_df()
            df = self._sheets.get(self._current_sheet_name, pd.DataFrame())
            df.to_csv(path, index=False, encoding="utf-8")
            from ui.toast import ToastNotification
            ToastNotification.show_toast(self.window(), f"CSV Dışa Aktarıldı: {os.path.basename(path)}", "info")

    def _search_cells(self, text: str):
        if not text.strip():
            for r in range(self.table.rowCount()):
                self.table.setRowHidden(r, False)
            return

        text = text.lower()
        for r in range(self.table.rowCount()):
            match = False
            for c in range(self.table.columnCount()):
                item = self.table.item(r, c)
                if item and text in item.text().lower():
                    match = True
                    break
            self.table.setRowHidden(r, not match)

    def _show_column_stats(self):
        c = self.table.currentColumn()
        if c < 0:
            QMessageBox.information(self, "Seçim Yok", "Lütfen istatistiğini görmek istediğiniz bir sütun seçin.")
            return

        header_item = self.table.horizontalHeaderItem(c)
        col_name = header_item.text() if header_item else self._col_idx_to_name(c)

        values = []
        for r in range(self.table.rowCount()):
            item = self.table.item(r, c)
            if item and item.text().strip():
                try:
                    values.append(float(item.text().strip().replace(",", ".")))
                except ValueError:
                    pass

        if not values:
            QMessageBox.information(self, "Veri Yok", f"'{col_name}' sütununda sayısal veri bulunamadı.")
            return

        s = pd.Series(values)
        info = (
            f"<b>Sütun:</b> {col_name}<br><br>"
            f"• <b>Toplam Değer Sayısı:</b> {len(s):,}<br>"
            f"• <b>Toplam (Sum):</b> {s.sum():,.2f}<br>"
            f"• <b>Ortalama (Mean):</b> {s.mean():,.2f}<br>"
            f"• <b>Minimum:</b> {s.min():,.2f}<br>"
            f"• <b>Maksimum:</b> {s.max():,.2f}<br>"
            f"• <b>Medyan:</b> {s.median():,.2f}"
        )
        QMessageBox.information(self, f"Sütun İstatistikleri: {col_name}", info)

    def _copy_selection(self):
        ranges = self.table.selectedRanges()
        if not ranges:
            return
        r = ranges[0]
        text_lines = []
        for row in range(r.topRow(), r.bottomRow() + 1):
            row_items = []
            for col in range(r.leftColumn(), r.rightColumn() + 1):
                item = self.table.item(row, col)
                row_items.append(item.text() if item else "")
            text_lines.append("\t".join(row_items))
        QApplication.clipboard().setText("\n".join(text_lines))

    def _paste_selection(self):
        clipboard_text = QApplication.clipboard().text()
        if not clipboard_text:
            return

        start_r = self.table.currentRow()
        start_c = self.table.currentColumn()
        if start_r < 0 or start_c < 0:
            return

        lines = clipboard_text.splitlines()
        for i, line in enumerate(lines):
            r = start_r + i
            if r >= self.table.rowCount():
                self.table.insertRow(r)
            cells = line.split("\t")
            for j, cell in enumerate(cells):
                c = start_c + j
                if c >= self.table.columnCount():
                    self.table.insertColumn(c)
                item = self.table.item(r, c)
                if not item:
                    item = QTableWidgetItem(cell)
                    self.table.setItem(r, c, item)
                else:
                    item.setText(cell)

        self._is_dirty = True
        self.content_changed.emit()

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Kopyala (Ctrl+C)", self._copy_selection)
        menu.addAction("Yapıştır (Ctrl+V)", self._paste_selection)
        menu.addAction("Hücreleri Temizle (Del)", self._clear_selected_cells)
        menu.addSeparator()
        menu.addAction("Satır Ekle", self._add_row)
        menu.addAction("Satır Sil", self._del_row)
        menu.addSeparator()
        menu.addAction("Sütun Ekle", self._add_column)
        menu.addAction("Sütun Sil", self._del_column)
        menu.addAction("Sütun Genişliklerini Sığdır", self._autofit_columns)
        menu.addSeparator()
        menu.addAction("Sütun İstatistikleri", self._show_column_stats)
        menu.exec(self.table.viewport().mapToGlobal(pos))
