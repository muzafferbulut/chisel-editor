import csv
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLineEdit, QPushButton, QLabel, QHeaderView, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
import geopandas as gpd
import pandas as pd


class AttributeTableWidget(QWidget):
    feature_selected = pyqtSignal(int)  # Emits original row/feature index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_gdf = None
        self._row_indices = []  # Maps visible table row to original feature index
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 Filter features across all attributes...")
        self.search_input.textChanged.connect(self._filter_table)
        toolbar.addWidget(self.search_input, stretch=2)

        self.stats_label = QLabel("0 features")
        self.stats_label.setStyleSheet("color: #858585; font-size: 12px;")
        toolbar.addWidget(self.stats_label)

        self.btn_export_csv = QPushButton("Export CSV")
        self.btn_export_csv.setToolTip("Export attribute table to CSV")
        self.btn_export_csv.clicked.connect(self._export_csv)
        toolbar.addWidget(self.btn_export_csv)

        layout.addLayout(toolbar)

        # Table Widget
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        layout.addWidget(self.table)

    def load_data(self, gdf: gpd.GeoDataFrame):
        self._current_gdf = gdf
        self.table.clear()
        self.search_input.clear()

        if gdf is None or len(gdf) == 0:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.stats_label.setText("0 features")
            return

        # Prepare columns: # (Index), Geometry, then attribute columns
        geom_col = gdf.geometry.name if hasattr(gdf, 'geometry') else None
        attr_cols = [c for c in gdf.columns if c != geom_col]
        all_cols = ["#", "Geometry"] + attr_cols

        self.table.setColumnCount(len(all_cols))
        self.table.setHorizontalHeaderLabels(all_cols)
        self.table.setRowCount(len(gdf))

        self._row_indices = list(range(len(gdf)))

        for i in range(len(gdf)):
            # Row index
            item_idx = QTableWidgetItem(str(i))
            item_idx.setFlags(item_idx.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_idx.setForeground(QColor("#858585"))
            self.table.setItem(i, 0, item_idx)

            # Geometry type
            geom = gdf.geometry.iloc[i] if geom_col else None
            g_type = geom.geom_type if geom is not None and not geom.is_empty else "None"
            item_geom = QTableWidgetItem(g_type)
            item_geom.setFlags(item_geom.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item_geom.setForeground(QColor("#00a2ff"))
            self.table.setItem(i, 1, item_geom)

            # Attribute columns
            for col_idx, col_name in enumerate(attr_cols):
                val = gdf[col_name].iloc[i]
                val_str = "" if pd.isna(val) or val is None else str(val)
                item = QTableWidgetItem(val_str)
                self.table.setItem(i, 2 + col_idx, item)

        self.table.resizeColumnsToContents()
        self.stats_label.setText(f"{len(gdf)} features, {len(attr_cols)} attributes")

    def _filter_table(self, query: str):
        query = query.strip().lower()
        if not query:
            for r in range(self.table.rowCount()):
                self.table.setRowHidden(r, False)
            visible_count = self.table.rowCount()
        else:
            visible_count = 0
            for r in range(self.table.rowCount()):
                match = False
                for c in range(self.table.columnCount()):
                    item = self.table.item(r, c)
                    if item and query in item.text().lower():
                        match = True
                        break
                self.table.setRowHidden(r, not match)
                if match:
                    visible_count += 1

        total = self.table.rowCount()
        self.stats_label.setText(f"Showing {visible_count} of {total} features")

    def _on_selection_changed(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            row = selected_rows[0].row()
            # Extract original feature index from column 0
            idx_item = self.table.item(row, 0)
            if idx_item:
                try:
                    feat_idx = int(idx_item.text())
                    self.feature_selected.emit(feat_idx)
                except ValueError:
                    pass

    def select_row_by_feature_index(self, feature_idx: int):
        """
        Called when a feature is clicked on the Leaflet map.
        Selects and scrolls to the corresponding row in the table.
        """
        for r in range(self.table.rowCount()):
            idx_item = self.table.item(r, 0)
            if idx_item and idx_item.text() == str(feature_idx):
                self.table.blockSignals(True)
                self.table.selectRow(r)
                self.table.scrollToItem(idx_item)
                self.table.blockSignals(False)
                break

    def _export_csv(self):
        if self._current_gdf is None or len(self._current_gdf) == 0:
            QMessageBox.information(self, "No Data", "No attributes to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Attribute Table", "attributes.csv", "CSV Files (*.csv)"
        )
        if file_path:
            try:
                # Export without geometry or with WKT geometry
                df = self._current_gdf.copy()
                if hasattr(df, 'geometry'):
                    df['wkt_geometry'] = df.geometry.apply(lambda g: g.wkt if g is not None else "")
                    df = df.drop(columns=[df.geometry.name])
                df.to_csv(file_path, index=False, encoding='utf-8')
                QMessageBox.information(self, "Export Successful", f"Attributes exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n{str(e)}")
