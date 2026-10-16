import os
from typing import Callable, Optional, Dict, List, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QDoubleSpinBox, QGroupBox,
    QProgressBar, QSplitter, QWidget, QFileDialog, QMessageBox, QAbstractItemView,
    QComboBox, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont

import geopandas as gpd
from shapely.geometry import Point

from core.topology_engine import (
    TopologyEngine, TopologyReport, TopologyError, TopologyRuleInfo,
    ConfiguredRule, TopologyRuleCode
)
from core.workers import TopologyWorker
from ui.toast import ToastNotification


def get_layer_crs_unit_info(gdf: gpd.GeoDataFrame) -> Tuple[str, str, str, bool]:
    """
    Determines CRS description, linear distance unit, area unit, and degree flag.
    Returns: (crs_name, linear_unit, area_unit, is_degree)
    """
    crs = gdf.crs
    crs_name = str(crs) if crs else "EPSG:4326"
    is_degree = False
    if crs is not None:
        if hasattr(crs, "is_geographic") and crs.is_geographic:
            is_degree = True
        elif any(k in str(crs).upper() for k in ["4326", "WGS 84", "WGS84", "CRS84", "GEOGRAPHIC"]):
            is_degree = True
    else:
        # Check coordinate magnitudes to infer geographic vs projected
        b = gdf.total_bounds
        if abs(b[0]) <= 180.0 and abs(b[2]) <= 180.0 and abs(b[1]) <= 90.0 and abs(b[3]) <= 90.0:
            is_degree = True
            crs_name = "EPSG:4326 (Inferred)"

    if is_degree:
        return crs_name, "degrees (°)", "square degrees (°²)", True
    else:
        return crs_name, "meters (m)", "square meters (m²)", False


class AddRuleDialog(QDialog):
    """
    Modal dialog allowing the user to select and configure a topology rule
    with parameters explicitly formatted in the layer's native coordinate system unit.
    """

    def __init__(
        self,
        geom_type: str,
        crs_str: str,
        linear_unit: str,
        area_unit: str,
        is_degree: bool,
        parent=None
    ):
        super().__init__(parent)
        self.geom_type = geom_type
        self.crs_str = crs_str
        self.linear_unit = linear_unit
        self.area_unit = area_unit
        self.is_degree = is_degree

        self.setWindowTitle("➕ Add Topology Validation Rule")
        self.setModal(True)
        self.resize(540, 420)

        self._setup_ui()
        self._on_rule_selected(0)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # Header Info Banner
        info_banner = QFrame()
        info_banner.setStyleSheet(
            "background-color: rgba(0, 162, 255, 0.08); "
            "border: 1px solid rgba(0, 162, 255, 0.3); "
            "border-radius: 6px; padding: 6px;"
        )
        info_layout = QVBoxLayout(info_banner)
        info_layout.setContentsMargins(8, 6, 8, 6)
        info_layout.setSpacing(4)

        lbl_layer_crs = QLabel(
            f"<b>Active CRS:</b> <code>{self.crs_str}</code> &nbsp;|&nbsp; "
            f"<b>Target Geometry:</b> <b>{self.geom_type.upper()}</b>"
        )
        lbl_units = QLabel(
            f"<b>Input Distance Unit:</b> <span style='color:#00a2ff;'><b>{self.linear_unit}</b></span> &nbsp;|&nbsp; "
            f"<b>Area Unit:</b> <span style='color:#00a2ff;'><b>{self.area_unit}</b></span>"
        )
        info_layout.addWidget(lbl_layer_crs)
        info_layout.addWidget(lbl_units)
        layout.addWidget(info_banner)

        # Rule Selection Section
        grp_rule = QGroupBox("Select Topology Rule")
        rule_layout = QVBoxLayout(grp_rule)
        rule_layout.setSpacing(8)

        self.cmb_rules = QComboBox()
        self.cmb_rules.setStyleSheet("font-weight: bold; padding: 5px;")

        self.applicable_rules = TopologyEngine.get_applicable_rules(self.geom_type)
        for rule in self.applicable_rules:
            self.cmb_rules.addItem(rule.name, rule.code)

        self.cmb_rules.currentIndexChanged.connect(self._on_rule_selected)
        rule_layout.addWidget(self.cmb_rules)

        self.lbl_rule_desc = QLabel()
        self.lbl_rule_desc.setWordWrap(True)
        self.lbl_rule_desc.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        rule_layout.addWidget(self.lbl_rule_desc)
        layout.addWidget(grp_rule)

        # Dynamic Parameters Section
        self.grp_params = QGroupBox(f"Rule Parameters (Specified in {self.linear_unit})")
        self.params_layout = QVBoxLayout(self.grp_params)
        self.params_layout.setSpacing(10)

        # 1. Tolerance input (for Point Duplicates, Line Dangles)
        self.wgt_tolerance = QWidget()
        tol_layout = QHBoxLayout(self.wgt_tolerance)
        tol_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_tol = QLabel(f"Tolerance ({self.linear_unit}):")
        self.lbl_tol.setMinimumWidth(180)
        self.spin_tol = QDoubleSpinBox()
        if self.is_degree:
            self.spin_tol.setDecimals(6)
            self.spin_tol.setRange(0.000001, 10.0)
            self.spin_tol.setValue(0.0001)
            self.spin_tol.setSingleStep(0.00005)
        else:
            self.spin_tol.setDecimals(3)
            self.spin_tol.setRange(0.001, 1000.0)
            self.spin_tol.setValue(0.05)
            self.spin_tol.setSingleStep(0.01)
        tol_layout.addWidget(self.lbl_tol)
        tol_layout.addWidget(self.spin_tol)
        tol_layout.addStretch()
        self.params_layout.addWidget(self.wgt_tolerance)

        # 2. Min length input (for Line Short Segments)
        self.wgt_length = QWidget()
        len_layout = QHBoxLayout(self.wgt_length)
        len_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_len = QLabel(f"Min Segment Length ({self.linear_unit}):")
        self.lbl_len.setMinimumWidth(180)
        self.spin_len = QDoubleSpinBox()
        if self.is_degree:
            self.spin_len.setDecimals(6)
            self.spin_len.setRange(0.000001, 10.0)
            self.spin_len.setValue(0.0001)
            self.spin_len.setSingleStep(0.00005)
        else:
            self.spin_len.setDecimals(3)
            self.spin_len.setRange(0.001, 5000.0)
            self.spin_len.setValue(0.10)
            self.spin_len.setSingleStep(0.05)
        len_layout.addWidget(self.lbl_len)
        len_layout.addWidget(self.spin_len)
        len_layout.addStretch()
        self.params_layout.addWidget(self.wgt_length)

        # 3. Area input (for Polygon Overlaps, Slivers, Gaps)
        self.wgt_area = QWidget()
        area_layout = QHBoxLayout(self.wgt_area)
        area_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_area = QLabel(f"Area Threshold ({self.area_unit}):")
        self.lbl_area.setMinimumWidth(180)
        self.spin_area = QDoubleSpinBox()
        if self.is_degree:
            self.spin_area.setDecimals(8)
            self.spin_area.setRange(1e-9, 100.0)
            self.spin_area.setValue(1e-7)
            self.spin_area.setSingleStep(1e-7)
        else:
            self.spin_area.setDecimals(2)
            self.spin_area.setRange(0.01, 1000000.0)
            self.spin_area.setValue(1.0)
            self.spin_area.setSingleStep(0.5)
        area_layout.addWidget(self.lbl_area)
        area_layout.addWidget(self.spin_area)
        area_layout.addStretch()
        self.params_layout.addWidget(self.wgt_area)

        # 4. Thinness ratio (for Polygon Slivers)
        self.wgt_thinness = QWidget()
        thin_layout = QHBoxLayout(self.wgt_thinness)
        thin_layout.setContentsMargins(0, 0, 0, 0)
        lbl_thin = QLabel("Thinness Ratio Threshold:")
        lbl_thin.setMinimumWidth(180)
        self.spin_thinness = QDoubleSpinBox()
        self.spin_thinness.setDecimals(3)
        self.spin_thinness.setRange(0.001, 1.0)
        self.spin_thinness.setValue(0.030)
        self.spin_thinness.setSingleStep(0.005)
        thin_layout.addWidget(lbl_thin)
        thin_layout.addWidget(self.spin_thinness)
        thin_layout.addStretch()
        self.params_layout.addWidget(self.wgt_thinness)

        # 5. Label for rules that do not require numeric thresholds
        self.lbl_no_param = QLabel("ℹ️ This is a topological rule based on OGC geometry definitions and requires no threshold.")
        self.lbl_no_param.setStyleSheet("color: #27ae60; font-style: italic; padding: 4px;")
        self.lbl_no_param.setWordWrap(True)
        self.params_layout.addWidget(self.lbl_no_param)

        layout.addWidget(self.grp_params)
        layout.addStretch()

        # Dialog Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_add = QPushButton("➕ Add Rule")
        self.btn_add.setStyleSheet("font-weight: bold; padding: 6px 18px;")
        self.btn_add.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_add)

        layout.addLayout(btn_layout)

    def _on_rule_selected(self, index: int):
        if index < 0 or index >= len(self.applicable_rules):
            return
        rule = self.applicable_rules[index]
        self.lbl_rule_desc.setText(rule.description)

        code = rule.code
        # Hide all controls by default
        self.wgt_tolerance.hide()
        self.wgt_length.hide()
        self.wgt_area.hide()
        self.wgt_thinness.hide()
        self.lbl_no_param.hide()

        if code == TopologyRuleCode.POINT_DUPLICATES:
            self.lbl_tol.setText(f"Snap Tolerance ({self.linear_unit}):")
            self.wgt_tolerance.show()
        elif code == TopologyRuleCode.LINE_DANGLES:
            self.lbl_tol.setText(f"Undershoot Tolerance ({self.linear_unit}):")
            self.wgt_tolerance.show()
        elif code == TopologyRuleCode.LINE_SHORT_SEGMENTS:
            self.wgt_length.show()
        elif code == TopologyRuleCode.POLYGON_OVERLAPS:
            self.lbl_area.setText(f"Min Overlap Area ({self.area_unit}):")
            self.wgt_area.show()
        elif code == TopologyRuleCode.POLYGON_SLIVERS:
            self.lbl_area.setText(f"Max Sliver Area ({self.area_unit}):")
            self.wgt_area.show()
            self.wgt_thinness.show()
        elif code == TopologyRuleCode.POLYGON_GAPS:
            self.lbl_area.setText(f"Max Gap Area ({self.area_unit}):")
            self.wgt_area.show()
        else:
            self.lbl_no_param.show()

    def get_configured_rule(self) -> ConfiguredRule:
        idx = self.cmb_rules.currentIndex()
        rule = self.applicable_rules[idx]
        code = rule.code
        params = {}

        if code in (TopologyRuleCode.POINT_DUPLICATES, TopologyRuleCode.LINE_DANGLES):
            params["tolerance"] = self.spin_tol.value()
        elif code == TopologyRuleCode.LINE_SHORT_SEGMENTS:
            params["min_length"] = self.spin_len.value()
        elif code == TopologyRuleCode.POLYGON_OVERLAPS:
            params["min_area"] = self.spin_area.value()
        elif code == TopologyRuleCode.POLYGON_SLIVERS:
            params["min_area"] = self.spin_area.value()
            params["thinness"] = self.spin_thinness.value()
        elif code == TopologyRuleCode.POLYGON_GAPS:
            params["max_gap_area"] = self.spin_area.value()

        return ConfiguredRule(
            code=code,
            name=rule.name,
            params=params,
            description=rule.description
        )


class TopologyCheckerDialog(QDialog):
    """
    QGIS Topology Checker-style Interactive Inspection & Remediation Dialog.
    Allows configuring rules with CRS-native parameter units, running audits on demand,
    visualizing defective geometry parts on the map, and zooming directly to error locations.
    """

    ERROR_LAYER_ID = "topology_errors"

    def __init__(
        self,
        gdf: gpd.GeoDataFrame,
        layer_name: str,
        map_panel,
        on_layer_updated: Optional[Callable[[gpd.GeoDataFrame], None]] = None,
        layer_id: str = None,
        parent=None
    ):
        super().__init__(parent)
        self.gdf = gdf.copy()
        self.layer_name = layer_name or "Spatial Layer"
        self.map_panel = map_panel
        self.on_layer_updated = on_layer_updated
        self.layer_id = layer_id

        self.report: Optional[TopologyReport] = None
        self.worker: Optional[TopologyWorker] = None
        self.configured_rules: List[ConfiguredRule] = []

        from core.spatial_ops import SpatialOps
        self.geom_type = SpatialOps.get_layer_geometry_type(self.gdf)
        self.crs_str, self.linear_unit, self.area_unit, self.is_degree = get_layer_crs_unit_info(self.gdf)

        self.setWindowTitle(f"📐 Topology Checker & Validator — {self.layer_name}")
        self.resize(980, 720)

        # Modeless tool window: does NOT block the main application window
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        self._setup_ui()
        self._update_rules_table()
        # NOTE: Do NOT auto-execute checks on dialog open. User configures rules first.

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # Header Info Banner
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)

        info_text = (
            f"<b>Layer:</b> {self.layer_name} &nbsp;|&nbsp; "
            f"<b>Type:</b> <span style='color:#00a2ff; font-weight:bold;'>{self.geom_type.upper()}</span> &nbsp;|&nbsp; "
            f"<b>Features:</b> {len(self.gdf):,} &nbsp;|&nbsp; "
            f"<b>CRS:</b> {self.crs_str} &nbsp;|&nbsp; "
            f"<b>Unit:</b> <span style='color:#00a2ff;'>{self.linear_unit}</span>"
        )
        self.lbl_info = QLabel(info_text)
        header_layout.addWidget(self.lbl_info)
        header_layout.addStretch()

        self.chk_show_map = QCheckBox("👁️ Show Errors on Map")
        self.chk_show_map.setChecked(True)
        self.chk_show_map.toggled.connect(self._toggle_map_error_layer)
        header_layout.addWidget(self.chk_show_map)

        main_layout.addWidget(header_widget)

        # Splitter: Top is Rules List, Bottom is Errors Table
        splitter = QSplitter(Qt.Orientation.Vertical)

        # --- Top Section: Configured Rules List ---
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        grp_rules = QGroupBox("Configured Topology Rules (Click '➕ Add Rule' to define rules)")
        rules_box_layout = QVBoxLayout(grp_rules)
        rules_box_layout.setSpacing(8)

        # Toolbar above rules table
        rules_tb_layout = QHBoxLayout()

        self.btn_add_rule = QPushButton("➕ Add Rule...")
        self.btn_add_rule.setStyleSheet("font-weight: bold; padding: 5px 12px;")
        self.btn_add_rule.clicked.connect(self._on_add_rule_clicked)
        rules_tb_layout.addWidget(self.btn_add_rule)

        self.btn_remove_rule = QPushButton("🗑️ Remove Rule")
        self.btn_remove_rule.clicked.connect(self._on_remove_selected_rule)
        rules_tb_layout.addWidget(self.btn_remove_rule)

        self.btn_clear_rules = QPushButton("🧹 Clear All")
        self.btn_clear_rules.clicked.connect(self._on_clear_all_rules)
        rules_tb_layout.addWidget(self.btn_clear_rules)

        self.btn_add_defaults = QPushButton("⚡ Add Recommended Rules")
        self.btn_add_defaults.setToolTip("Quickly add recommended rules matching this geometry type and coordinate units")
        self.btn_add_defaults.clicked.connect(self._on_add_recommended_rules)
        rules_tb_layout.addWidget(self.btn_add_defaults)

        rules_tb_layout.addStretch()
        rules_box_layout.addLayout(rules_tb_layout)

        # Rules Table
        self.rules_table = QTableWidget()
        self.rules_table.setColumnCount(5)
        self.rules_table.setHorizontalHeaderLabels([
            "#", "Rule Name", "Target Geometry", f"Parameters ({self.linear_unit})", "Auto-Repairable"
        ])
        self.rules_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.rules_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.rules_table.setAlternatingRowColors(True)
        self.rules_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.rules_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.rules_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.rules_table.setFixedHeight(150)
        rules_box_layout.addWidget(self.rules_table)

        # Run Check Action Bar
        action_bar = QHBoxLayout()
        self.btn_run = QPushButton("▶️ Run Topology Check")
        self.btn_run.setStyleSheet(
            "font-weight: bold; font-size: 13px; padding: 7px 18px; "
            "background-color: #27ae60; color: white; border-radius: 4px;"
        )
        self.btn_run.clicked.connect(self._on_run_checks)
        action_bar.addWidget(self.btn_run)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.hide()
        action_bar.addWidget(self.progress_bar)
        action_bar.addStretch()

        top_layout.addWidget(grp_rules)
        top_layout.addLayout(action_bar)
        splitter.addWidget(top_widget)

        # --- Bottom Section: Error Table & Remediation Actions ---
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)

        table_header = QHBoxLayout()
        self.lbl_status = QLabel("<b>Status:</b> Ready. Click '➕ Add Rule...' to configure rules, then click 'Run Topology Check'.")
        table_header.addWidget(self.lbl_status)
        table_header.addStretch()
        bottom_layout.addLayout(table_header)

        # Errors Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["#", "Rule Violated", "Feature ID(s)", "Severity", "Description"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_zoom_to_selected)
        bottom_layout.addWidget(self.table)

        # Bottom Action Buttons
        btn_box = QHBoxLayout()

        self.btn_zoom = QPushButton("🔍 Zoom to Error")
        self.btn_zoom.clicked.connect(self._on_zoom_to_selected)
        self.btn_zoom.setEnabled(False)
        btn_box.addWidget(self.btn_zoom)

        self.btn_fix_single = QPushButton("🔧 Fix Selected")
        self.btn_fix_single.clicked.connect(self._on_fix_selected)
        self.btn_fix_single.setEnabled(False)
        btn_box.addWidget(self.btn_fix_single)

        self.btn_fix_all = QPushButton("⚡ Fix All Auto-repairable")
        self.btn_fix_all.setStyleSheet("font-weight: bold;")
        self.btn_fix_all.clicked.connect(self._on_fix_all)
        self.btn_fix_all.setEnabled(False)
        btn_box.addWidget(self.btn_fix_all)

        self.btn_export = QPushButton("💾 Export Errors...")
        self.btn_export.clicked.connect(self._on_export_errors)
        self.btn_export.setEnabled(False)
        btn_box.addWidget(self.btn_export)

        btn_box.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)
        btn_box.addWidget(self.btn_close)

        bottom_layout.addLayout(btn_box)
        splitter.addWidget(bottom_widget)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        main_layout.addWidget(splitter)

    # -------------------------------------------------------------
    # Rule Configuration Handlers
    # -------------------------------------------------------------

    def _update_rules_table(self):
        self.rules_table.setRowCount(len(self.configured_rules))
        for idx, crule in enumerate(self.configured_rules):
            info = TopologyEngine.RULES.get(crule.code)
            geom_types_str = ", ".join(info.geom_types) if info else self.geom_type
            can_fix_str = "Yes" if info and info.supports_auto_fix else "No"

            item_id = QTableWidgetItem(str(idx + 1))
            item_name = QTableWidgetItem(crule.name)
            item_name.setFont(QFont(self.font().family(), weight=QFont.Weight.Bold))
            item_geom = QTableWidgetItem(geom_types_str)
            item_param = QTableWidgetItem(crule.get_param_summary(self.is_degree))
            item_fix = QTableWidgetItem("✅ " + can_fix_str if can_fix_str == "Yes" else "❌ No")

            self.rules_table.setItem(idx, 0, item_id)
            self.rules_table.setItem(idx, 1, item_name)
            self.rules_table.setItem(idx, 2, item_geom)
            self.rules_table.setItem(idx, 3, item_param)
            self.rules_table.setItem(idx, 4, item_fix)

        cnt = len(self.configured_rules)
        btn_label = f"▶️ Run Topology Check ({cnt} rules)" if cnt > 0 else "▶️ Run Topology Check"
        self.btn_run.setText(btn_label)

    def _on_add_rule_clicked(self):
        dlg = AddRuleDialog(
            geom_type=self.geom_type,
            crs_str=self.crs_str,
            linear_unit=self.linear_unit,
            area_unit=self.area_unit,
            is_degree=self.is_degree,
            parent=self
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            crule = dlg.get_configured_rule()
            self.configured_rules.append(crule)
            self._update_rules_table()
            ToastNotification.show_toast(self, f"Added rule: {crule.name}", "info")

    def _on_remove_selected_rule(self):
        selected_rows = self.rules_table.selectedIndexes()
        if not selected_rows:
            ToastNotification.show_toast(self, "Please select a rule to remove.", "warning")
            return
        row = selected_rows[0].row()
        if 0 <= row < len(self.configured_rules):
            removed = self.configured_rules.pop(row)
            self._update_rules_table()
            ToastNotification.show_toast(self, f"Removed rule: {removed.name}", "info")

    def _on_clear_all_rules(self):
        if not self.configured_rules:
            return
        self.configured_rules.clear()
        self._update_rules_table()
        ToastNotification.show_toast(self, "Cleared all rules.", "info")

    def _on_add_recommended_rules(self):
        recommended = TopologyEngine.get_default_configured_rules(self.geom_type, self.is_degree)
        self.configured_rules = recommended
        self._update_rules_table()
        ToastNotification.show_toast(self, f"Loaded {len(recommended)} recommended rules for {self.geom_type}.", "success")

    # -------------------------------------------------------------
    # Layer Refresh & Execution
    # -------------------------------------------------------------

    def update_layer(
        self,
        gdf: gpd.GeoDataFrame,
        layer_name: str,
        on_layer_updated: Optional[Callable[[gpd.GeoDataFrame], None]] = None,
        layer_id: str = None
    ):
        """
        Refreshes dialog state when user switches active layers or tabs.
        Does NOT automatically execute checks.
        """
        self.gdf = gdf.copy()
        self.layer_name = layer_name or "Spatial Layer"
        if on_layer_updated:
            self.on_layer_updated = on_layer_updated
        if layer_id:
            self.layer_id = layer_id

        from core.spatial_ops import SpatialOps
        self.geom_type = SpatialOps.get_layer_geometry_type(self.gdf)
        self.crs_str, self.linear_unit, self.area_unit, self.is_degree = get_layer_crs_unit_info(self.gdf)

        self.setWindowTitle(f"📐 Topology Checker & Validator — {self.layer_name}")
        info_text = (
            f"<b>Layer:</b> {self.layer_name} &nbsp;|&nbsp; "
            f"<b>Type:</b> <span style='color:#00a2ff; font-weight:bold;'>{self.geom_type.upper()}</span> &nbsp;|&nbsp; "
            f"<b>Features:</b> {len(self.gdf):,} &nbsp;|&nbsp; "
            f"<b>CRS:</b> {self.crs_str} &nbsp;|&nbsp; "
            f"<b>Unit:</b> <span style='color:#00a2ff;'>{self.linear_unit}</span>"
        )
        self.lbl_info.setText(info_text)

        # Clear previous error table and map overlay
        self.report = None
        self.table.setRowCount(0)
        self.lbl_status.setText("<b>Status:</b> Ready. Configure rules and click 'Run Topology Check'.")
        self.btn_zoom.setEnabled(False)
        self.btn_fix_single.setEnabled(False)
        self.btn_fix_all.setEnabled(False)
        self.btn_export.setEnabled(False)

        if self.map_panel:
            self.map_panel.remove_vector_layer(self.ERROR_LAYER_ID)

        self._update_rules_table()

    def _on_run_checks(self):
        if not self.configured_rules:
            ToastNotification.show_toast(self, "Please add at least one rule with '➕ Add Rule...' first.", "warning")
            return

        self.btn_run.setEnabled(False)
        self.progress_bar.show()
        self.lbl_status.setText("<i>Auditing layer topology according to configured rules...</i>")

        self.worker = TopologyWorker(
            "check",
            self.gdf,
            configured_rules=self.configured_rules
        )
        self.worker.check_finished.connect(self._on_check_finished)
        self.worker.start()

    def _on_check_finished(self, report: Optional[TopologyReport], error_msg: str):
        self.progress_bar.hide()
        self.btn_run.setEnabled(True)

        if error_msg:
            self.lbl_status.setText(f"<span style='color:#e74c3c;'>Error: {error_msg}</span>")
            ToastNotification.show_toast(self, f"Topology check error: {error_msg}", "error")
            return

        self.report = report
        if self.chk_show_map.isChecked():
            self._update_map_error_layer()
        self._populate_table(report)

    def _populate_table(self, report: TopologyReport):
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(0)
            if not report or report.total_errors == 0:
                self.lbl_status.setText("✅ <b>No topology errors found! Layer satisfies all configured rules.</b>")
                self.btn_fix_all.setEnabled(False)
                self.btn_fix_single.setEnabled(False)
                self.btn_export.setEnabled(False)
                self.btn_zoom.setEnabled(False)
                ToastNotification.show_toast(self, "✅ Topologically clean! 0 errors found.", "success")
                return

            err_count = sum(1 for e in report.errors if e.severity == "error")
            warn_count = report.total_errors - err_count

            summary_str = f"⚠️ <b>Found {report.total_errors:,} issue(s)</b> ({err_count} errors, {warn_count} warnings)"
            breakdown = ", ".join(f"{code}: {cnt}" for code, cnt in report.rule_counts.items())
            self.lbl_status.setText(f"{summary_str} &nbsp;|&nbsp; <small>{breakdown}</small>")

            self.btn_fix_all.setEnabled(True)
            self.btn_fix_single.setEnabled(True)
            self.btn_export.setEnabled(True)
            self.btn_zoom.setEnabled(True)

            display_errors = report.errors[:2000]
            self.table.setRowCount(len(display_errors))
            for row_idx, err in enumerate(display_errors):
                item_id = QTableWidgetItem(str(err.id + 1))
                item_rule = QTableWidgetItem(err.rule_name)
                item_feat = QTableWidgetItem(", ".join(map(str, err.feature_ids)) if err.feature_ids else "-")
                item_sev = QTableWidgetItem("⛔ Error" if err.severity == "error" else "⚠️ Warning")
                item_desc = QTableWidgetItem(err.description)

                if err.severity == "error":
                    item_sev.setForeground(QBrush(QColor("#e74c3c")))
                    item_sev.setFont(QFont(self.font().family(), weight=QFont.Weight.Bold))
                else:
                    item_sev.setForeground(QBrush(QColor("#f39c12")))

                self.table.setItem(row_idx, 0, item_id)
                self.table.setItem(row_idx, 1, item_rule)
                self.table.setItem(row_idx, 2, item_feat)
                self.table.setItem(row_idx, 3, item_sev)
                self.table.setItem(row_idx, 4, item_desc)

            self.table.selectRow(0)
        finally:
            self.table.setUpdatesEnabled(True)

    # -------------------------------------------------------------
    # Map Visualization & Zoom
    # -------------------------------------------------------------

    def _update_map_error_layer(self):
        if not self.map_panel or not self.report or self.report.errors_gdf is None or self.report.errors_gdf.empty:
            if self.map_panel:
                self.map_panel.remove_vector_layer(self.ERROR_LAYER_ID)
            return

        try:
            from core.spatial_ops import SpatialOps
            err_gdf = self.report.errors_gdf
            if len(err_gdf) > 1500:
                err_gdf = err_gdf.iloc[:1500]

            geojson_str = SpatialOps.to_geojson_str(err_gdf)
            self.map_panel.set_vector_layer(
                self.ERROR_LAYER_ID,
                "⚠️ Topology Errors",
                geojson_str,
                is_active=False,       # Crucial: do NOT hijack active editing layer
                geom_type="any",
                color="#e74c3c",
                fit_bounds=False
            )
        except Exception as e:
            print(f"Error updating map error layer: {e}")

    def _toggle_map_error_layer(self, checked: bool):
        if not self.map_panel:
            return
        if checked:
            self._update_map_error_layer()
        else:
            self.map_panel.remove_vector_layer(self.ERROR_LAYER_ID)

    def closeEvent(self, event):
        if self.map_panel:
            self.map_panel.clear_topology_highlight()
            self.map_panel.remove_vector_layer(self.ERROR_LAYER_ID)
        super().closeEvent(event)

    def _on_table_selection_changed(self):
        selected_rows = self.table.selectedIndexes()
        if not selected_rows or not self.report:
            return
        row = selected_rows[0].row()
        if 0 <= row < len(self.report.errors):
            err = self.report.errors[row]
            self._zoom_to_error_geometry(err.geometry, err.id, err=err)

    def _on_zoom_to_selected(self):
        selected_rows = self.table.selectedIndexes()
        if not selected_rows or not self.report:
            return
        row = selected_rows[0].row()
        if 0 <= row < len(self.report.errors):
            err = self.report.errors[row]
            self._zoom_to_error_geometry(err.geometry, err.id, err=err)

    def _transform_geom_to_4326(self, geom):
        """
        Converts any Shapely error geometry to WGS 84 (EPSG:4326) coordinates for Leaflet.
        """
        if geom is None or (hasattr(geom, "is_empty") and geom.is_empty):
            return None
        import shapely.ops
        import pyproj

        if self.gdf is not None and self.gdf.crs is not None:
            crs_str = str(self.gdf.crs).upper()
            if "4326" not in crs_str and "CRS84" not in crs_str:
                try:
                    project = pyproj.Transformer.from_crs(self.gdf.crs, "EPSG:4326", always_xy=True).transform
                    return shapely.ops.transform(project, geom)
                except Exception:
                    pass

        b = geom.bounds
        if abs(b[0]) > 180.0 or abs(b[2]) > 180.0 or abs(b[1]) > 90.0 or abs(b[3]) > 90.0:
            try:
                project = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform
                return shapely.ops.transform(project, geom)
            except Exception:
                pass
        return geom

    def _zoom_to_error_geometry(self, geom, err_id: int = None, err: TopologyError = None):
        """
        Extracts defective geometry piece, converts it to WGS84 GeoJSON,
        calculates padded extent, and triggers high-zoom QGIS-style error focus.
        """
        if geom is None or not self.map_panel:
            return

        try:
            # 1. Transform defective error geometry to EPSG:4326 for Leaflet
            geom_4326 = self._transform_geom_to_4326(geom)
            if geom_4326 is None or (hasattr(geom_4326, "is_empty") and geom_4326.is_empty):
                return

            bounds = geom_4326.bounds  # (minx, miny, maxx, maxy) in degrees (lon, lat)
            minx, miny, maxx, maxy = bounds

            span_x = abs(maxx - minx)
            span_y = abs(maxy - miny)
            if span_x < 0.0008 or span_y < 0.0008:
                delta = 0.0006  # ~65 meters comfortable zoom buffer around point/micro-defect
                south = max(-85.0, miny - delta)
                north = min(85.0, maxy + delta)
                west = max(-180.0, minx - delta)
                east = min(180.0, maxx + delta)
                max_zoom = 18
            else:
                pad_x = max(span_x * 0.25, 0.0003)
                pad_y = max(span_y * 0.25, 0.0003)
                south = max(-85.0, miny - pad_y)
                north = min(85.0, maxy + pad_y)
                west = max(-180.0, minx - pad_x)
                east = min(180.0, maxx + pad_x)
                max_zoom = 18

            bounds_obj = {
                "south": south,
                "north": north,
                "west": west,
                "east": east,
                "maxZoom": max_zoom
            }

            import shapely.geometry
            geojson_geom = shapely.geometry.mapping(geom_4326)

            parent_ids = err.feature_ids if err else []
            title = err.rule_name if err else "Topoloji Hatası"
            desc = err.description if err else ""

            self.map_panel.show_topology_error_focus(
                geojson_geom=geojson_geom,
                bounds_obj=bounds_obj,
                title=title,
                description=desc,
                parent_indices=parent_ids,
                parent_layer_id=getattr(self, "layer_id", None)
            )

        except Exception as e:
            print(f"Failed to focus on error geometry: {e}")

    # -------------------------------------------------------------
    # Remediation
    # -------------------------------------------------------------

    def _on_fix_selected(self):
        selected_rows = self.table.selectedIndexes()
        if not selected_rows or not self.report:
            return
        row = selected_rows[0].row()
        if not (0 <= row < len(self.report.errors)):
            return

        err = self.report.errors[row]
        if not err.can_fix:
            QMessageBox.information(
                self, "Manual Fix Required",
                f"The rule '{err.rule_name}' requires manual inspection or geometry editing."
            )
            return

        repaired_gdf, ok = TopologyEngine.fix_single_error(self.gdf, err)
        if ok:
            self.gdf = repaired_gdf
            if self.on_layer_updated:
                self.on_layer_updated(self.gdf)
            ToastNotification.show_toast(self, f"Fixed error #{err.id + 1} ({err.rule_name})", "success")
            self._on_run_checks()
        else:
            ToastNotification.show_toast(self, "Could not auto-repair this error automatically.", "warning")

    def _on_fix_all(self):
        if not self.report or self.report.total_errors == 0:
            return

        reply = QMessageBox.question(
            self,
            "Auto-Repair Topology",
            "Are you sure you want to attempt automatic fixes for all repairable issues?\n\n"
            "This will make geometries OGC valid, remove duplicate vertices/points, "
            "clip overlapping areas, and merge slivers.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.lbl_status.setText("<i>Executing automated repairs...</i>")
        self.progress_bar.show()

        self.worker = TopologyWorker("fix_all", self.gdf, report=self.report)
        self.worker.repair_finished.connect(self._on_fix_all_finished)
        self.worker.start()

    def _on_fix_all_finished(self, repaired_gdf: Optional[gpd.GeoDataFrame], count: int, error_msg: str):
        self.progress_bar.hide()
        if error_msg or repaired_gdf is None:
            QMessageBox.warning(self, "Repair Error", f"Failed to execute repairs: {error_msg}")
            return

        self.gdf = repaired_gdf
        if self.on_layer_updated:
            self.on_layer_updated(self.gdf)

        ToastNotification.show_toast(self, f"🔧 Successfully resolved {count:,} topology issues!", "success")
        # Re-run check on repaired dataset
        self._on_run_checks()

    def _on_export_errors(self):
        if not self.report or self.report.errors_gdf is None or self.report.errors_gdf.empty:
            ToastNotification.show_toast(self, "No errors to export.", "warning")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Topology Errors",
            f"{os.path.splitext(self.layer_name)[0]}_topology_errors.geojson",
            "GeoJSON (*.geojson);;All Files (*)"
        )
        if path:
            try:
                from core.spatial_ops import SpatialOps
                clean_gdf = SpatialOps.sanitize_gdf_for_json(self.report.errors_gdf)
                clean_gdf.to_file(path, driver="GeoJSON")
                ToastNotification.show_toast(self, f"Errors exported to {os.path.basename(path)}", "success")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Could not export error file: {e}")
