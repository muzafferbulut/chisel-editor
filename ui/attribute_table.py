import os
import csv
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView,
    QLineEdit, QPushButton, QLabel, QHeaderView, QFileDialog, QMessageBox,
    QDialog, QComboBox, QFrame
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QItemSelectionModel, QItemSelection, QSize
import geopandas as gpd
import pandas as pd
from core.spatial_ops import SpatialOps


class AttributeTableProxyModel(QSortFilterProxyModel):
    """
    High-performance proxy model that handles fast text search filtering
    and optional 'Show only selected features' mode like QGIS.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._only_selected = False
        self._selected_source_rows = set()

    def set_only_selected(self, enabled: bool, selected_rows: set):
        self._only_selected = enabled
        self._selected_source_rows = set(selected_rows)
        self.invalidateFilter()

    def is_only_selected(self) -> bool:
        return self._only_selected

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex):
        if self._only_selected and source_row not in self._selected_source_rows:
            return False
        return super().filterAcceptsRow(source_row, source_parent)


class AddFieldDialog(QDialog):
    """QGIS-style dialog for adding a new attribute field/column to the layer."""

    def __init__(self, existing_columns: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Yeni Alan / Sütun Ekle")
        self.setFixedSize(320, 220)
        self.existing_columns = [str(c).lower() for c in existing_columns]
        self.field_name = ""
        self.field_type = "str"
        self.default_val = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addWidget(QLabel("<b>Sütun Adı:</b>"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("örn: mahalle_adi, nufus, durum")
        layout.addWidget(self.name_edit)

        layout.addWidget(QLabel("<b>Veri Türü:</b>"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("Metin (String / Yazı)", "str")
        self.type_combo.addItem("Tamsayı (Integer)", "int")
        self.type_combo.addItem("Ondalık Sayı (Float / Double)", "float")
        layout.addWidget(self.type_combo)

        layout.addWidget(QLabel("<b>Varsayılan Değer (İsteğe bağlı):</b>"))
        self.default_edit = QLineEdit()
        self.default_edit.setPlaceholderText("Boş bırakılabilir")
        layout.addWidget(self.default_edit)

        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("İptal")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Ekle")
        btn_ok.setStyleSheet("background-color: #007acc; color: white; font-weight: bold; border-radius: 4px; padding: 4px 14px;")
        btn_ok.clicked.connect(self._on_accept)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def _on_accept(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Geçersiz Ad", "Lütfen bir sütun adı girin.")
            return
        if name.lower() in self.existing_columns:
            QMessageBox.warning(self, "Mevcut Sütun", f"'{name}' isimli bir sütun zaten mevcut.")
            return

        self.field_name = name
        self.field_type = self.type_combo.currentData()
        raw_val = self.default_edit.text().strip()

        if raw_val:
            try:
                if self.field_type == "int":
                    self.default_val = int(raw_val)
                elif self.field_type == "float":
                    self.default_val = float(raw_val.replace(",", "."))
                else:
                    self.default_val = raw_val
            except ValueError:
                QMessageBox.warning(self, "Tür Uyuşmazlığı", "Varsayılan değer seçilen türe dönüştürülemedi.")
                return
        else:
            if self.field_type == "int":
                self.default_val = 0
            elif self.field_type == "float":
                self.default_val = 0.0
            else:
                self.default_val = ""

        self.accept()


class GeoDataFrameTableModel(QAbstractTableModel):
    """
    High-performance virtual table model for GeoDataFrame / DataFrame.
    Renders 100,000+ rows instantly with 0ms overhead by referencing memory directly.
    """

    def __init__(self, gdf: gpd.GeoDataFrame = None):
        super().__init__()
        self._gdf = gdf if gdf is not None and not gdf.empty else gpd.GeoDataFrame()
        self._columns = []
        self._update_columns()

    def _update_columns(self):
        if self._gdf is not None and not self._gdf.empty:
            geom_name = getattr(self._gdf, 'geometry', None)
            geom_col = geom_name.name if geom_name is not None else None
            self._columns = [c for c in self._gdf.columns if c != geom_col]
            if geom_col and geom_col in self._gdf.columns:
                self._columns.append(geom_col)
        else:
            self._columns = []

    def set_data(self, gdf: gpd.GeoDataFrame):
        self.beginResetModel()
        self._gdf = gdf if gdf is not None and not gdf.empty else gpd.GeoDataFrame()
        self._update_columns()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return len(self._gdf) if self._gdf is not None and not self._gdf.empty else 0

    def columnCount(self, parent=QModelIndex()):
        return len(self._columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self._gdf is None or self._gdf.empty:
            return None

        row = index.row()
        col_idx = index.column()
        if row >= len(self._gdf) or col_idx >= len(self._columns):
            return None

        col_name = self._columns[col_idx]
        val = self._gdf[col_name].iat[row]

        if role == Qt.ItemDataRole.DisplayRole:
            if col_name == getattr(self._gdf, 'geometry', None).name if hasattr(self._gdf, 'geometry') else None:
                if val is not None and hasattr(val, 'geom_type'):
                    return f"<{val.geom_type}>"
                return "<Empty>"
            if pd.isna(val):
                return ""
            if isinstance(val, float):
                return f"{val:.4f}" if abs(val) < 10000 else f"{val:,.2f}"
            return str(val)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if isinstance(val, (int, float)) and not pd.isna(val):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            if section < len(self._columns):
                return str(self._columns[section])
        elif orientation == Qt.Orientation.Vertical:
            return str(section + 1)
        return None

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if self._gdf is None or self._gdf.empty or column >= len(self._columns):
            return
        self.layoutAboutToBeChanged.emit()
        col_name = self._columns[column]
        ascending = (order == Qt.SortOrder.AscendingOrder)
        try:
            self._gdf = self._gdf.sort_values(by=col_name, ascending=ascending).reset_index(drop=True)
        except Exception:
            pass
        self.layoutChanged.emit()


class AttributeTableWidget(QWidget):
    feature_selected = pyqtSignal(int)
    features_selected = pyqtSignal(list)
    delete_requested = pyqtSignal(list)
    data_modified = pyqtSignal(object)
    zoom_to_selected_requested = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_gdf = None
        self._block_selection_signals = False
        self._cached_selected_rows = set()
        self._init_ui()

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

    def _create_tool_btn(self, icon_name: str, fallback_text: str, tooltip: str, callback=None, checkable: bool = False, obj_name: str = "") -> QPushButton:
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

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Toolbar Container (Theme-adaptive styling)
        toolbar_container = QWidget()
        toolbar_container.setObjectName("AttributeTableToolbar")
        toolbar_container.setStyleSheet(
            "#AttributeTableToolbar QPushButton {"
            "  background-color: transparent;"
            "  border: 1px solid transparent;"
            "  border-radius: 4px;"
            "  padding: 0px;"
            "  min-width: 28px;"
            "  max-width: 28px;"
            "  min-height: 28px;"
            "  max-height: 28px;"
            "}"
            "#AttributeTableToolbar QPushButton:hover {"
            "  background-color: rgba(128, 128, 128, 0.2);"
            "  border: 1px solid rgba(128, 128, 128, 0.35);"
            "}"
            "#AttributeTableToolbar QPushButton:pressed {"
            "  background-color: rgba(128, 128, 128, 0.35);"
            "}"
            "#AttributeTableToolbar QPushButton:checked {"
            "  background-color: rgba(0, 122, 204, 0.25);"
            "  border: 1px solid #007acc;"
            "}"
            "#AttributeTableToolbar QPushButton:disabled {"
            "  background-color: transparent;"
            "  border: 1px solid transparent;"
            "}"
            "#AttributeTableToolbar QPushButton#btn_del:hover:enabled {"
            "  background-color: rgba(239, 68, 68, 0.2);"
            "  border: 1px solid rgba(239, 68, 68, 0.4);"
            "}"
            "#AttributeTableToolbar QPushButton#btn_close {"
            "  border: 1px solid transparent;"
            "  font-weight: bold;"
            "  font-size: 13px;"
            "}"
            "#AttributeTableToolbar QPushButton#btn_close:hover {"
            "  background-color: rgba(239, 68, 68, 0.2);"
            "  border: 1px solid rgba(239, 68, 68, 0.4);"
            "}"
        )
        toolbar = QHBoxLayout(toolbar_container)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(4)

        # Quick Search Box
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Filtrele...")
        self.search_input.setMaximumWidth(200)
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self._filter_table)
        toolbar.addWidget(self.search_input)

        self.stats_label = QLabel("0 özellik")
        self.stats_label.setStyleSheet("color: #858585; font-size: 11px; padding: 0 4px;")
        toolbar.addWidget(self.stats_label)

        toolbar.addWidget(self._create_vsep())

        # QGIS Selection Tools
        self.btn_zoom_selected = self._create_tool_btn("zoom_to_selected", "🔍", "Haritada Seçilenlere Yakınlaş", self._zoom_to_selected)
        self.btn_zoom_selected.setEnabled(False)
        toolbar.addWidget(self.btn_zoom_selected)

        self.btn_select_all = self._create_tool_btn("select_all", "🔲", "Tümünü Seç (Ctrl+A)", self._select_all)
        toolbar.addWidget(self.btn_select_all)

        self.btn_invert_sel = self._create_tool_btn("invert_selection", "🔄", "Seçimi Tersine Çevir", self._invert_selection)
        toolbar.addWidget(self.btn_invert_sel)

        self.btn_clear_sel = self._create_tool_btn("clear_selection", "✖", "Seçimi Temizle", self._clear_selection)
        toolbar.addWidget(self.btn_clear_sel)

        self.btn_show_selected = self._create_tool_btn("show_selected", "🎯", "Yalnızca Seçilenleri Göster / Tümünü Göster", self._toggle_show_selected, checkable=True)
        toolbar.addWidget(self.btn_show_selected)

        toolbar.addWidget(self._create_vsep())

        # QGIS Data / Calculation Tools
        self.btn_add_col = self._create_tool_btn("add_field", "➕", "Yeni Sütun / Alan Ekle", self._add_field)
        toolbar.addWidget(self.btn_add_col)

        self.btn_calc_geom = self._create_tool_btn("calc_geom", "📐", "Geometri Hesapla (Alan, Uzunluk, Koordinatlar)", self._calculate_geometry)
        toolbar.addWidget(self.btn_calc_geom)

        self.btn_stats = self._create_tool_btn("statistics", "📊", "Sütun İstatistikleri (Tüm katman için)", self._show_column_statistics)
        toolbar.addWidget(self.btn_stats)

        self.btn_del_selected = self._create_tool_btn("delete_selected", "🗑️", "Seçili Kayıtları Sil (Del)", self._delete_selected_rows, obj_name="btn_del")
        self.btn_del_selected.setEnabled(False)
        toolbar.addWidget(self.btn_del_selected)

        toolbar.addWidget(self._create_vsep())

        # Export & Close
        self.btn_export_csv = self._create_tool_btn("export_csv", "💾", "Öznitelik Tablosunu CSV Olarak Dışa Aktar", self._export_csv)
        toolbar.addWidget(self.btn_export_csv)

        toolbar.addStretch()

        self.btn_close = self._create_tool_btn("close", "✕", "Öznitelik Tablosunu Kapat (F6)", self.close_requested.emit, obj_name="btn_close")
        toolbar.addWidget(self.btn_close)

        layout.addWidget(toolbar_container)

        # Table View with Virtual Model
        self.table_view = QTableView()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setStretchLastSection(False)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.verticalHeader().setDefaultSectionSize(25)

        self.source_model = GeoDataFrameTableModel()
        self.proxy_model = AttributeTableProxyModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)

        self.table_view.setModel(self.proxy_model)
        self.table_view.selectionModel().selectionChanged.connect(self._on_selection_changed)

        layout.addWidget(self.table_view)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self.btn_del_selected.isEnabled():
                self._delete_selected_rows()
                return
        super().keyPressEvent(event)

    def load_data(self, gdf: gpd.GeoDataFrame):
        self._current_gdf = gdf
        self.btn_show_selected.blockSignals(True)
        self.btn_show_selected.setChecked(False)
        self.btn_show_selected.blockSignals(False)
        self.proxy_model.set_only_selected(False, set())

        self.source_model.set_data(gdf)

        count = len(gdf) if gdf is not None and not gdf.empty else 0
        self.stats_label.setText(f"{count:,} özellik")
        self.btn_del_selected.setEnabled(False)
        self.btn_del_selected.setToolTip("Seçili Kayıtları Sil (Del)")
        self.btn_zoom_selected.setEnabled(False)
        self.btn_zoom_selected.setToolTip("Haritada Seçilenlere Yakınlaş")
        self.btn_stats.setToolTip("Sütun İstatistikleri (Tüm katman için)")

        header = self.table_view.horizontalHeader()
        header.setDefaultSectionSize(120)
        for col in range(min(5, self.source_model.columnCount())):
            header.resizeSection(col, 130)

    def _filter_table(self, text: str):
        self.proxy_model.setFilterFixedString(text)
        self._update_stats_label()

    def _update_stats_label(self):
        visible = self.proxy_model.rowCount()
        total = self.source_model.rowCount()
        if self.proxy_model.is_only_selected() or bool(self.search_input.text().strip()):
            self.stats_label.setText(f"{visible:,} / {total:,} özellik")
        else:
            self.stats_label.setText(f"{total:,} özellik")

    def _zoom_to_selected(self):
        self.zoom_to_selected_requested.emit()

    def _select_all(self):
        self.table_view.selectAll()

    def _invert_selection(self):
        sel_model = self.table_view.selectionModel()
        total_rows = self.proxy_model.rowCount()
        col_count = self.proxy_model.columnCount()
        if total_rows == 0 or col_count == 0:
            return
        selection = QItemSelection(
            self.proxy_model.index(0, 0),
            self.proxy_model.index(total_rows - 1, col_count - 1)
        )
        sel_model.select(selection, QItemSelectionModel.SelectionFlag.Toggle | QItemSelectionModel.SelectionFlag.Rows)

    def _clear_selection(self):
        self.table_view.selectionModel().clearSelection()

    def _toggle_show_selected(self, checked: bool):
        if checked:
            indexes = self.table_view.selectionModel().selectedRows()
            src_rows = set()
            for p_idx in indexes:
                s_idx = self.proxy_model.mapToSource(p_idx)
                if s_idx.isValid():
                    src_rows.add(s_idx.row())
            if not src_rows:
                self.btn_show_selected.blockSignals(True)
                self.btn_show_selected.setChecked(False)
                self.btn_show_selected.blockSignals(False)
                QMessageBox.information(
                    self, "Seçim Yok",
                    "Yalnızca seçilenleri göstermek için önce tablodan veya haritadan en az bir özellik seçmelisiniz."
                )
                return
            self._cached_selected_rows = src_rows
            self.proxy_model.set_only_selected(True, src_rows)
            self.table_view.selectAll()
        else:
            self.proxy_model.set_only_selected(False, set())
            if self._cached_selected_rows:
                self.select_features(list(self._cached_selected_rows))
        self._update_stats_label()

    def _add_field(self):
        if self._current_gdf is None or self._current_gdf.empty:
            QMessageBox.information(self, "Veri Yok", "Yüklü mekansal katman bulunamadı.")
            return

        dlg = AddFieldDialog(list(self._current_gdf.columns), parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.field_name
            val = dlg.default_val
            try:
                self._current_gdf[name] = val
                self.load_data(self._current_gdf)
                self.data_modified.emit(self._current_gdf)
                QMessageBox.information(self, "Alan Eklendi", f"'{name}' sütunu başarıyla eklendi!")
            except Exception as e:
                QMessageBox.critical(self, "Hata", f"Sütun eklenirken hata oluştu: {e}")

    def _on_selection_changed(self, selected, deselected):
        indexes = self.table_view.selectionModel().selectedRows()
        count = len(indexes)
        has_sel = count > 0

        self.btn_del_selected.setEnabled(has_sel)
        self.btn_zoom_selected.setEnabled(has_sel)
        if has_sel:
            self.btn_del_selected.setToolTip(f"Seçili {count:,} Kaydı Sil (Del)")
            self.btn_zoom_selected.setToolTip(f"Haritada Seçili {count:,} Geometriye Yakınlaş")
            self.btn_stats.setToolTip(f"Sütun İstatistikleri (Seçili {count:,} kayıt için)")
        else:
            self.btn_del_selected.setToolTip("Seçili Kayıtları Sil (Del)")
            self.btn_zoom_selected.setToolTip("Haritada Seçilenlere Yakınlaş")
            self.btn_stats.setToolTip("Sütun İstatistikleri (Tüm katman için)")

        if self._block_selection_signals:
            return

        source_rows = []
        for proxy_idx in indexes:
            src_idx = self.proxy_model.mapToSource(proxy_idx)
            if src_idx.isValid():
                source_rows.append(src_idx.row())

        self.features_selected.emit(source_rows)
        if source_rows:
            self.feature_selected.emit(source_rows[0])

    def _delete_selected_rows(self):
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            return
        source_rows = []
        for proxy_idx in indexes:
            src_idx = self.proxy_model.mapToSource(proxy_idx)
            if src_idx.isValid():
                source_rows.append(src_idx.row())
        if not source_rows:
            return

        count = len(source_rows)
        if count > 10:
            reply = QMessageBox.question(
                self, "Satırları Sil",
                f"{count:,} adet seçili öznitelik kaydını ve geometrisini silmek istediğinize emin misiniz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.delete_requested.emit(source_rows)

    def select_features(self, indices: list):
        if self._block_selection_signals:
            return
        self._block_selection_signals = True
        try:
            sel_model = self.table_view.selectionModel()
            sel_model.clearSelection()
            if not indices or self.source_model.rowCount() == 0:
                self.btn_del_selected.setEnabled(False)
                self.btn_del_selected.setToolTip("Seçili Kayıtları Sil (Del)")
                self.btn_zoom_selected.setEnabled(False)
                self.btn_zoom_selected.setToolTip("Haritada Seçilenlere Yakınlaş")
                self.btn_stats.setToolTip("Sütun İstatistikleri (Tüm katman için)")
                return

            selection = QItemSelection()
            col_count = self.proxy_model.columnCount()
            first_valid_proxy = None

            for idx in indices:
                if 0 <= idx < self.source_model.rowCount():
                    src_idx = self.source_model.index(idx, 0)
                    proxy_idx = self.proxy_model.mapFromSource(src_idx)
                    if proxy_idx.isValid():
                        if first_valid_proxy is None:
                            first_valid_proxy = proxy_idx
                        tl = self.proxy_model.index(proxy_idx.row(), 0)
                        br = self.proxy_model.index(proxy_idx.row(), col_count - 1)
                        selection.select(tl, br)

            sel_model.select(selection, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
            if first_valid_proxy:
                self.table_view.scrollTo(first_valid_proxy, QTableView.ScrollHint.PositionAtCenter)

            count = len(indices)
            self.btn_del_selected.setEnabled(count > 0)
            self.btn_zoom_selected.setEnabled(count > 0)
            if count > 0:
                self.btn_del_selected.setToolTip(f"Seçili {count:,} Kaydı Sil (Del)")
                self.btn_zoom_selected.setToolTip(f"Haritada Seçili {count:,} Geometriye Yakınlaş")
                self.btn_stats.setToolTip(f"Sütun İstatistikleri (Seçili {count:,} kayıt için)")
            else:
                self.btn_del_selected.setToolTip("Seçili Kayıtları Sil (Del)")
                self.btn_zoom_selected.setToolTip("Haritada Seçilenlere Yakınlaş")
                self.btn_stats.setToolTip("Sütun İstatistikleri (Tüm katman için)")
        finally:
            self._block_selection_signals = False

    def select_feature(self, index: int):
        self.select_features([index])

    def _show_column_statistics(self):
        if self._current_gdf is None or self._current_gdf.empty:
            QMessageBox.information(self, "Veri Yok", "Yüklü mekansal katman bulunamadı.")
            return

        cols = [c for c in self._current_gdf.columns if c != getattr(self._current_gdf, 'geometry', None).name]
        if not cols:
            QMessageBox.information(self, "Öznitelik Yok", "İstatistik hesaplanacak öznitelik sütunu bulunamadı.")
            return

        # Check if there are selected rows in the table
        indexes = self.table_view.selectionModel().selectedRows()
        selected_source_rows = []
        for proxy_idx in indexes:
            src_idx = self.proxy_model.mapToSource(proxy_idx)
            if src_idx.isValid():
                selected_source_rows.append(src_idx.row())

        if selected_source_rows:
            target_gdf = self._current_gdf.iloc[selected_source_rows]
            scope_desc = f"Seçili {len(selected_source_rows):,} Kayıt"
        else:
            target_gdf = self._current_gdf
            scope_desc = f"Tüm Katman ({len(self._current_gdf):,} Kayıt)"

        from ui.dialogs import ColumnStatisticsDialog
        dlg = ColumnStatisticsDialog(target_gdf, cols, scope_desc=scope_desc, parent=self)
        dlg.exec()

    def _calculate_geometry(self):
        if self._current_gdf is None or self._current_gdf.empty:
            QMessageBox.information(self, "Veri Yok", "Yüklü mekansal katman bulunamadı.")
            return

        try:
            updated_gdf = SpatialOps.calculate_geometry_attributes(self._current_gdf)
            self.load_data(updated_gdf)
            self.data_modified.emit(updated_gdf)
            QMessageBox.information(self, "Geometri Hesaplandı", "Alan (km²), uzunluk (km) ve koordinat sütunları başarıyla eklendi!")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"Geometri hesaplanamadı: {e}")

    def _export_csv(self):
        if self._current_gdf is None or self._current_gdf.empty:
            QMessageBox.information(self, "Veri Yok", "Dışa aktarılacak veri yok.")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Öznitelik Tablosunu Dışa Aktar", "attributes.csv", "CSV Dosyaları (*.csv)")
        if not path:
            return

        try:
            clean_df = pd.DataFrame(self._current_gdf.drop(columns=[self._current_gdf.geometry.name], errors='ignore'))
            clean_df.to_csv(path, index=False, encoding='utf-8')
            QMessageBox.information(self, "Başarılı", f"Öznitelik tablosu kaydedildi:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"CSV kaydedilemedi: {str(e)}")

