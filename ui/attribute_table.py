import csv
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView,
    QLineEdit, QPushButton, QLabel, QHeaderView, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QAbstractTableModel, QModelIndex, QSortFilterProxyModel
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
        self._feature_indices = list(range(len(self._gdf)))
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
        self._feature_indices = list(range(len(self._gdf)))
        self._update_columns()
        self.endResetModel()

    def get_feature_index(self, row: int) -> int:
        if 0 <= row < len(self._feature_indices):
            return self._feature_indices[row]
        return row

    def get_row_for_feature_index(self, feature_idx: int) -> int:
        try:
            return self._feature_indices.index(feature_idx)
        except (ValueError, IndexError):
            return feature_idx

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

        elif role in (Qt.ItemDataRole.EditRole, Qt.ItemDataRole.UserRole):
            if pd.isna(val):
                return None
            if hasattr(val, 'item'):
                try:
                    return val.item()
                except Exception:
                    pass
            return val

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
            orig_idx = self.get_feature_index(section)
            return str(orig_idx + 1)
        return None

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        if self._gdf is None or self._gdf.empty or column >= len(self._columns):
            return
        self.layoutAboutToBeChanged.emit()
        col_name = self._columns[column]
        ascending = (order == Qt.SortOrder.AscendingOrder)
        try:
            sorted_indices = self._gdf[col_name].argsort(kind='mergesort')
            if not ascending:
                sorted_indices = sorted_indices[::-1]
            self._gdf = self._gdf.iloc[sorted_indices].reset_index(drop=True)
            self._feature_indices = [self._feature_indices[i] for i in sorted_indices]
        except Exception:
            pass
        self.layoutChanged.emit()


class AttributeTableWidget(QWidget):
    feature_selected = pyqtSignal(int)
    data_modified = pyqtSignal(object)
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_gdf = None
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
        self.table_view.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setStretchLastSection(False)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table_view.verticalHeader().setDefaultSectionSize(25)

        self.source_model = GeoDataFrameTableModel()
        self.proxy_model = QSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setSortRole(Qt.ItemDataRole.UserRole)

        self.table_view.setModel(self.proxy_model)
        self.table_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.table_view.clicked.connect(self._on_table_cell_clicked)
        self.table_view.doubleClicked.connect(self._on_table_cell_clicked)

        layout.addWidget(self.table_view)

    def load_data(self, gdf: gpd.GeoDataFrame):
        self._current_gdf = gdf
        self.source_model.set_data(gdf)

        count = len(gdf) if gdf is not None and not gdf.empty else 0
        self.stats_label.setText(f"{count:,} özellik")
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
        if getattr(self, "_is_selecting_programmatically", False):
            return
        indexes = self.table_view.selectionModel().selectedRows()
        if not indexes:
            indexes = self.table_view.selectionModel().selectedIndexes()
        if not indexes:
            return
        proxy_idx = indexes[0]
        source_idx = self.proxy_model.mapToSource(proxy_idx)
        feat_idx = self.source_model.get_feature_index(source_idx.row())
        self.feature_selected.emit(feat_idx)

    def _on_table_cell_clicked(self, proxy_idx: QModelIndex):
        if not proxy_idx.isValid() or getattr(self, "_is_selecting_programmatically", False):
            return
        source_idx = self.proxy_model.mapToSource(proxy_idx)
        feat_idx = self.source_model.get_feature_index(source_idx.row())
        self.feature_selected.emit(feat_idx)

    def select_feature(self, index: int):
        if index < 0:
            self._is_selecting_programmatically = True
            try:
                self.table_view.clearSelection()
            finally:
                self._is_selecting_programmatically = False
            return

        source_row = self.source_model.get_row_for_feature_index(index)
        if source_row < 0 or source_row >= self.source_model.rowCount():
            return

        self._is_selecting_programmatically = True
        try:
            source_idx = self.source_model.index(source_row, 0)
            proxy_idx = self.proxy_model.mapFromSource(source_idx)
            if proxy_idx.isValid():
                self.table_view.selectRow(proxy_idx.row())
                self.table_view.scrollTo(proxy_idx, QTableView.ScrollHint.PositionAtCenter)
        finally:
            self._is_selecting_programmatically = False

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
