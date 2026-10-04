from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QMessageBox, QDoubleSpinBox, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox
)
from PyQt6.QtCore import Qt
from core.spatial_ops import SpatialOps


class LayerSelectionDialog(QDialog):

    def __init__(self, file_name: str, layers: list, parent=None):
        super().__init__(parent)
        self.selected_layer = None
        self.merge_all = False
        self.layers = layers

        self.setWindowTitle("Select Layer")
        self.resize(460, 360)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._setup_ui(file_name)

    def _setup_ui(self, file_name):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl_title = QLabel(
            f"<b>{file_name}</b> contains <b>{len(self.layers)}</b> layers.<br>"
            "Please select a layer to import, or merge all layers:"
        )
        lbl_title.setWordWrap(True)
        layout.addWidget(lbl_title)

        self.list_widget = QListWidget()
        self.list_widget.addItems(self.layers)
        self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_merge = QPushButton("Merge All Layers")
        self.btn_merge.clicked.connect(self._on_merge)

        self.btn_load = QPushButton("Load Selected Layer")
        self.btn_load.clicked.connect(self._on_load)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_merge)
        btn_layout.addWidget(self.btn_load)

        layout.addLayout(btn_layout)

    def _on_merge(self):
        self.merge_all = True
        self.accept()

    def _on_load(self):
        item = self.list_widget.currentItem()
        if item:
            self.selected_layer = item.text()
        self.accept()


class CRSDialog(QDialog):
    COMMON_CRS = [
        ("EPSG:4326", "EPSG:4326 - WGS 84 (GPS & GeoJSON Default)"),
        ("EPSG:3857", "EPSG:3857 - WGS 84 / Pseudo-Mercator (Web Maps)"),
        ("EPSG:5254", "EPSG:5254 - TUREF / TM30 (Turkey Central 3° Zone)"),
        ("EPSG:5255", "EPSG:5255 - TUREF / TM33 (Turkey 3° Zone)"),
        ("EPSG:5256", "EPSG:5256 - TUREF / TM36 (Turkey 3° Zone)"),
        ("EPSG:5257", "EPSG:5257 - TUREF / TM39 (Turkey 3° Zone)"),
        ("EPSG:32635", "EPSG:32635 - WGS 84 / UTM Zone 35N"),
        ("EPSG:32636", "EPSG:32636 - WGS 84 / UTM Zone 36N"),
        ("EPSG:32637", "EPSG:32637 - WGS 84 / UTM Zone 37N"),
        ("EPSG:25832", "EPSG:25832 - ETRS89 / UTM Zone 32N (Europe)"),
        ("EPSG:2154", "EPSG:2154 - RGF93 / Lambert-93 (France)"),
        ("EPSG:27700", "EPSG:27700 - British National Grid (UK)")
    ]

    def __init__(self, title: str, current_crs: str = None, parent=None):
        super().__init__(parent)
        self.selected_epsg = None
        self.setWindowTitle(title)
        self.resize(460, 240)
        self.setModal(True)
        self._setup_ui(current_crs)

    def _setup_ui(self, current_crs):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        if current_crs:
            lbl_current = QLabel(f"<b>Current CRS:</b> <code style='color:#00a2ff'>{current_crs}</code>")
            layout.addWidget(lbl_current)

        layout.addWidget(QLabel("<b>Quick Preset:</b>"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("-- Select Common CRS Preset --", "")
        for epsg_code, label in self.COMMON_CRS:
            self.preset_combo.addItem(label, epsg_code)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        layout.addWidget(self.preset_combo)

        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("<b>Target EPSG Code:</b>"))
        self.epsg_input = QLineEdit()
        self.epsg_input.setPlaceholderText("e.g. 4326 or EPSG:3857")
        input_layout.addWidget(self.epsg_input)
        layout.addLayout(input_layout)

        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_apply = QPushButton("Apply")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(self._on_apply)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_apply)

        layout.addLayout(btn_layout)

    def _on_preset_changed(self, index):
        val = self.preset_combo.currentData()
        if val:
            self.epsg_input.setText(val)

    def _on_apply(self):
        text = self.epsg_input.text().strip()
        if text.isdigit():
            self.selected_epsg = f"EPSG:{text}"
            self.accept()
        elif text.lower().startswith("epsg:") and text.split(":")[-1].isdigit():
            self.selected_epsg = text.upper()
            self.accept()
        else:
            QMessageBox.warning(self, "Invalid Input", "Please enter or select a valid EPSG code (e.g. 4326).")


class BufferDialog(QDialog):

    def __init__(self, crs: str = None, parent=None):
        super().__init__(parent)
        self.distance = 500.0
        self.unit = "meters"

        self.setWindowTitle("Buffer Geometries")
        self.resize(380, 220)
        self.setModal(True)
        self._setup_ui(crs)

    def _setup_ui(self, crs):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl_desc = QLabel("Creates a buffer zone around all geometries in the active layer.")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        dist_layout = QHBoxLayout()
        dist_layout.addWidget(QLabel("<b>Buffer Distance:</b>"))
        self.spin_dist = QDoubleSpinBox()
        self.spin_dist.setRange(0.0001, 1000000.0)
        self.spin_dist.setValue(500.0)
        self.spin_dist.setDecimals(2)
        dist_layout.addWidget(self.spin_dist)

        self.combo_unit = QComboBox()
        self.combo_unit.addItem("Meters (m)", "meters")
        self.combo_unit.addItem("Kilometers (km)", "kilometers")
        self.combo_unit.addItem("Degrees (°)", "degrees")
        dist_layout.addWidget(self.combo_unit)
        layout.addLayout(dist_layout)

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("Presets:"))
        for d, u, lbl in [(100, 0, "100m"), (500, 0, "500m"), (1, 1, "1km"), (5, 1, "5km")]:
            btn = QPushButton(lbl)
            btn.clicked.connect(lambda _, dist=d, unit_idx=u: self._set_preset(dist, unit_idx))
            preset_layout.addWidget(btn)
        layout.addLayout(preset_layout)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_apply = QPushButton("Apply Buffer")
        btn_cancel.clicked.connect(self.reject)
        btn_apply.clicked.connect(self._on_apply)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_apply)
        layout.addLayout(btn_layout)

    def _set_preset(self, dist, unit_idx):
        self.combo_unit.setCurrentIndex(unit_idx)
        self.spin_dist.setValue(dist)

    def _on_apply(self):
        val = self.spin_dist.value()
        unit_type = self.combo_unit.currentData()
        if unit_type == "kilometers":
            self.distance = val * 1000.0
            self.unit = "meters"
        else:
            self.distance = val
            self.unit = unit_type
        self.accept()


class DissolveDialog(QDialog):

    def __init__(self, columns: list, parent=None):
        super().__init__(parent)
        self.by_column = None

        self.setWindowTitle("Dissolve Geometries")
        self.resize(380, 180)
        self.setModal(True)
        self._setup_ui(columns)

    def _setup_ui(self, columns):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        lbl_desc = QLabel("Merges adjacent or selected features based on an attribute value, or merges all features into one.")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        col_layout = QHBoxLayout()
        col_layout.addWidget(QLabel("<b>Dissolve By Column:</b>"))
        self.col_combo = QComboBox()
        self.col_combo.addItem("-- Dissolve All Features (Single Layer) --", None)
        for col in columns:
            self.col_combo.addItem(col, col)
        col_layout.addWidget(self.col_combo)
        layout.addLayout(col_layout)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_apply = QPushButton("Dissolve")
        btn_cancel.clicked.connect(self.reject)
        btn_apply.clicked.connect(self._on_apply)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_apply)
        layout.addLayout(btn_layout)

    def _on_apply(self):
        self.by_column = self.col_combo.currentData()
        self.accept()


class SimplifyDialog(QDialog):

    def __init__(self, crs: str = None, vertex_count: int = 0, parent=None):
        super().__init__(parent)
        self.tolerance = 0.001
        self.preserve_topology = True

        self.setWindowTitle("Simplify Geometries (Douglas-Peucker)")
        self.resize(380, 220)
        self.setModal(True)
        self._setup_ui(crs, vertex_count)

    def _setup_ui(self, crs, vertex_count):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        info_text = f"Current vertices: <b>{vertex_count:,}</b>"
        is_degree = crs and ("4326" in crs or "WGS 84" in crs)
        if is_degree:
            info_text += "<br><small style='color:#858585'>Coordinate unit: <b>Degrees</b> (suggested: 0.0001 - 0.01)</small>"
        else:
            info_text += "<br><small style='color:#858585'>Coordinate unit: <b>Meters / Linear</b> (suggested: 1.0 - 50.0)</small>"

        lbl_info = QLabel(info_text)
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)

        spin_layout = QHBoxLayout()
        spin_layout.addWidget(QLabel("<b>Tolerance:</b>"))
        self.spin_tolerance = QDoubleSpinBox()
        self.spin_tolerance.setDecimals(6)
        self.spin_tolerance.setRange(0.000001, 10000.0)
        self.spin_tolerance.setValue(0.0005 if is_degree else 5.0)
        self.spin_tolerance.setSingleStep(0.0001 if is_degree else 1.0)
        spin_layout.addWidget(self.spin_tolerance)
        layout.addLayout(spin_layout)

        self.chk_topology = QCheckBox("Preserve Topology (Prevents invalid geometries)")
        self.chk_topology.setChecked(True)
        layout.addWidget(self.chk_topology)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_simplify = QPushButton("Simplify")
        btn_cancel.clicked.connect(self.reject)
        btn_simplify.clicked.connect(self._on_apply)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_simplify)
        layout.addLayout(btn_layout)

    def _on_apply(self):
        self.tolerance = self.spin_tolerance.value()
        self.preserve_topology = self.chk_topology.isChecked()
        self.accept()


class ExportSpatialDialog(QDialog):

    FORMATS = [
        ("GeoJSON (*.geojson)", ".geojson"),
        ("GeoPackage (*.gpkg)", ".gpkg"),
        ("ESRI Shapefile (*.shp)", ".shp"),
        ("Keyhole Markup Language (*.kml)", ".kml"),
        ("FlatGeobuf (*.fgb)", ".fgb"),
        ("CSV with WKT (*.csv)", ".csv")
    ]

    def __init__(self, current_file: str = None, parent=None):
        super().__init__(parent)
        self.target_path = None
        self.setWindowTitle("Export / Convert Spatial Data")
        self.resize(480, 200)
        self.setModal(True)
        self._setup_ui(current_file)

    def _setup_ui(self, current_file):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        combo_layout = QHBoxLayout()
        combo_layout.addWidget(QLabel("<b>Target Format:</b>"))
        self.format_combo = QComboBox()
        for label, ext in self.FORMATS:
            self.format_combo.addItem(label, ext)
        combo_layout.addWidget(self.format_combo)
        layout.addLayout(combo_layout)

        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("<b>Destination:</b>"))
        self.path_input = QLineEdit()
        if current_file:
            import os
            base, _ = os.path.splitext(current_file)
            self.path_input.setText(f"{base}_export.geojson")
        path_layout.addWidget(self.path_input)

        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._on_browse)
        path_layout.addWidget(btn_browse)
        layout.addLayout(path_layout)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_export = QPushButton("Export")
        btn_cancel.clicked.connect(self.reject)
        btn_export.clicked.connect(self._on_export)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_export)
        layout.addLayout(btn_layout)

    def _on_browse(self):
        ext = self.format_combo.currentData()
        filt = f"Selected Format (*{ext});;All Files (*)"
        chosen, _ = QFileDialog.getSaveFileName(self, "Export Spatial Data", self.path_input.text(), filt)
        if chosen:
            self.path_input.setText(chosen)

    def _on_export(self):
        path = self.path_input.text().strip()
        if not path:
            QMessageBox.warning(self, "Empty Path", "Please specify a destination file path.")
            return
        self.target_path = path
        self.accept()


class ColumnStatisticsDialog(QDialog):

    def __init__(self, gdf, columns: list, parent=None):
        super().__init__(parent)
        self.gdf = gdf
        self.columns = columns
        self.setWindowTitle("Column Statistics")
        self.resize(420, 320)
        self.setModal(True)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        sel_layout = QHBoxLayout()
        sel_layout.addWidget(QLabel("<b>Select Column:</b>"))
        self.combo_cols = QComboBox()
        self.combo_cols.addItems(self.columns)
        self.combo_cols.currentTextChanged.connect(self._update_stats)
        sel_layout.addWidget(self.combo_cols)
        layout.addLayout(sel_layout)

        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

        if self.columns:
            self._update_stats(self.columns[0])

    def _update_stats(self, col_name):
        if not col_name or col_name not in self.gdf.columns:
            return
        try:
            stats = SpatialOps.get_column_statistics(self.gdf, col_name)
            self.table.setRowCount(0)
            items = [
                ("Column", stats.get("column")),
                ("Total Count", f"{stats.get('total_count', 0):,}"),
                ("Valid Count", f"{stats.get('valid_count', 0):,}"),
                ("Null Count", f"{stats.get('null_count', 0):,}")
            ]
            if stats.get("is_numeric"):
                items.extend([
                    ("Min", f"{stats.get('min'):,.4f}"),
                    ("Max", f"{stats.get('max'):,.4f}"),
                    ("Sum", f"{stats.get('sum'):,.4f}"),
                    ("Mean", f"{stats.get('mean'):,.4f}"),
                    ("Median", f"{stats.get('median'):,.4f}"),
                    ("Std Dev", f"{stats.get('std'):,.4f}")
                ])
            else:
                items.append(("Unique Values", f"{stats.get('unique_count', 0):,}"))
                top = stats.get("top_values", {})
                for val, cnt in top.items():
                    items.append((f"Top: {val}", str(cnt)))

            self.table.setRowCount(len(items))
            for row_idx, (m, v) in enumerate(items):
                self.table.setItem(row_idx, 0, QTableWidgetItem(str(m)))
                self.table.setItem(row_idx, 1, QTableWidgetItem(str(v)))
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to compute statistics: {e}")


class SpatialInfoDialog(QDialog):

    def __init__(self, summary: dict, file_path: str = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spatial Layer Information")
        self.resize(520, 460)
        self.setModal(True)
        self._setup_ui(summary, file_path)

    def _setup_ui(self, summary, file_path):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        grp_general = QGroupBox("General Metadata")
        gen_layout = QVBoxLayout(grp_general)
        if file_path:
            import os
            gen_layout.addWidget(QLabel(f"<b>File:</b> {os.path.basename(file_path)}"))
        gen_layout.addWidget(QLabel(f"<b>Feature Count:</b> {summary.get('feature_count', 0):,}"))
        gen_layout.addWidget(QLabel(f"<b>CRS:</b> <code style='color:#00a2ff'>{summary.get('crs', 'None')}</code>"))
        gen_layout.addWidget(QLabel(f"<b>Total Vertices:</b> {summary.get('vertex_count', 0):,}"))

        valid_str = "✅ All Valid" if summary.get('all_valid') else f"⚠️ {summary.get('feature_count', 0) - summary.get('valid_count', 0)} Invalid Geometries"
        gen_layout.addWidget(QLabel(f"<b>Geometry Validity:</b> {valid_str}"))

        b = summary.get('total_bounds', [0, 0, 0, 0])
        gen_layout.addWidget(QLabel(f"<b>Bounding Box:</b> MinX: {b[0]:.4f}, MinY: {b[1]:.4f}, MaxX: {b[2]:.4f}, MaxY: {b[3]:.4f}"))
        layout.addWidget(grp_general)

        grp_geoms = QGroupBox("Geometry Types")
        geom_layout = QVBoxLayout(grp_geoms)
        g_types = summary.get('geometry_types', {})
        for gtype, count in g_types.items():
            geom_layout.addWidget(QLabel(f"• <b>{gtype}:</b> {count}"))
        layout.addWidget(grp_geoms)

        cols = summary.get('columns', [])
        if cols:
            layout.addWidget(QLabel("<b>Attribute Columns:</b>"))
            table = QTableWidget()
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["Column Name", "Data Type", "Non-Null Count"])
            table.setRowCount(len(cols))
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            for idx, c in enumerate(cols):
                table.setItem(idx, 0, QTableWidgetItem(c.get("name", "")))
                table.setItem(idx, 1, QTableWidgetItem(c.get("dtype", "")))
                table.setItem(idx, 2, QTableWidgetItem(str(c.get("non_null", ""))))
            layout.addWidget(table)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)
