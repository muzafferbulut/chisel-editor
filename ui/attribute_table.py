import csv
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView,
    QLineEdit, QPushButton, QLabel, QHeaderView, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QItemSelectionModel, QItemSelection
import geopandas as gpd
import pandas as pd
from core.spatial_ops import SpatialOps


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
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_gdf = None
        self._block_selection_signals = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Hızlı filtreleme...")
        self.search_input.textChanged.connect(self._filter_table)
        toolbar.addWidget(self.search_input, stretch=2)

        self.stats_label = QLabel("0 özellik")
        self.stats_label.setStyleSheet("color: #858585; font-size: 11px; padding: 0 4px;")
        toolbar.addWidget(self.stats_label)

        self.btn_stats = QPushButton("Σ İstatistik")
        self.btn_stats.setToolTip("Sütun İstatistikleri (Toplam, Ortalama, Min, Max)")
        self.btn_stats.clicked.connect(self._show_column_statistics)
        toolbar.addWidget(self.btn_stats)

        self.btn_calc_geom = QPushButton("📐 Geometri")
        self.btn_calc_geom.setToolTip("Alan (km²), Uzunluk (km) ve Koordinatları hesapla")
        self.btn_calc_geom.clicked.connect(self._calculate_geometry)
        toolbar.addWidget(self.btn_calc_geom)

        self.btn_del_selected = QPushButton("🗑️ Sil")
        self.btn_del_selected.setToolTip("Seçili kayıtları sil (Del)")
        self.btn_del_selected.setEnabled(False)
        self.btn_del_selected.clicked.connect(self._delete_selected_rows)
        toolbar.addWidget(self.btn_del_selected)

        self.btn_export_csv = QPushButton("CSV")
        self.btn_export_csv.setToolTip("Öznitelik tablosunu CSV olarak kaydet")
        self.btn_export_csv.clicked.connect(self._export_csv)
        toolbar.addWidget(self.btn_export_csv)

        self.btn_close = QPushButton("✕")
        self.btn_close.setToolTip("Öznitelik Tablosunu Kapat (F6)")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet(
            "QPushButton { border: 1px solid transparent; font-weight: bold; font-size: 13px; border-radius: 4px; padding: 0px; } "
            "QPushButton:hover { background-color: rgba(239, 68, 68, 0.2); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.4); }"
        )
        self.btn_close.clicked.connect(self.close_requested.emit)
        toolbar.addWidget(self.btn_close)

        layout.addLayout(toolbar)

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
        self.proxy_model = QSortFilterProxyModel(self)
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
        self.source_model.set_data(gdf)

        count = len(gdf) if gdf is not None and not gdf.empty else 0
        self.stats_label.setText(f"{count:,} özellik")
        self.btn_del_selected.setEnabled(False)
        self.btn_del_selected.setText("🗑️ Sil")
        header = self.table_view.horizontalHeader()
        header.setDefaultSectionSize(120)
        for col in range(min(5, self.source_model.columnCount())):
            header.resizeSection(col, 130)

    def _filter_table(self, text: str):
        self.proxy_model.setFilterFixedString(text)
        visible = self.proxy_model.rowCount()
        total = self.source_model.rowCount()
        if text.strip():
            self.stats_label.setText(f"{visible:,} / {total:,} özellik")
        else:
            self.stats_label.setText(f"{total:,} özellik")

    def _on_selection_changed(self, selected, deselected):
        indexes = self.table_view.selectionModel().selectedRows()
        count = len(indexes)
        if count > 0:
            self.btn_del_selected.setEnabled(True)
            self.btn_del_selected.setText(f"🗑️ Sil ({count})")
        else:
            self.btn_del_selected.setEnabled(False)
            self.btn_del_selected.setText("🗑️ Sil")

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
                self.btn_del_selected.setText("🗑️ Sil")
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
            self.btn_del_selected.setText(f"🗑️ Sil ({count})" if count > 0 else "🗑️ Sil")
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

        from ui.dialogs import ColumnStatisticsDialog
        dlg = ColumnStatisticsDialog(self._current_gdf, cols, parent=self)
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
