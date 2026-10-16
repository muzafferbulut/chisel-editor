import os
import json
from typing import Callable, Optional, Dict, List, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QDoubleSpinBox, QGroupBox,
    QProgressBar, QSplitter, QWidget, QFileDialog, QMessageBox, QAbstractItemView,
    QComboBox, QFrame, QLineEdit
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QBrush, QFont, QIcon

import geopandas as gpd
from shapely.geometry import Point

from core.topology_engine import (
    TopologyEngine, TopologyReport, TopologyError, TopologyRuleInfo,
    ConfiguredRule, TopologyRuleCode
)
from core.workers import TopologyWorker
from core.theme import ThemeManager
from ui.icons import get_lucide_icon
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

        self.setWindowTitle("Add Topology Validation Rule")
        self.setModal(True)
        self.resize(540, 440)

        self._setup_ui()
        self.apply_theme()
        self._on_rule_selected(0)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        # Header Info Banner
        self.info_banner = QFrame()
        info_layout = QVBoxLayout(self.info_banner)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(4)

        lbl_layer_crs = QLabel(f"<b>Target Layer Projection:</b> {self.crs_str}")
        lbl_units = QLabel(
            f"<b>Distance Unit:</b> <span style='font-weight:600;'>{self.linear_unit}</span> &nbsp;|&nbsp; "
            f"<b>Area Unit:</b> <span style='font-weight:600;'>{self.area_unit}</span>"
        )
        info_layout.addWidget(lbl_layer_crs)
        info_layout.addWidget(lbl_units)
        layout.addWidget(self.info_banner)

        # Rule Selection Section
        self.grp_rule = QGroupBox("Select Topology Rule")
        rule_layout = QVBoxLayout(self.grp_rule)
        rule_layout.setSpacing(8)

        self.cmb_rules = QComboBox()
        self.applicable_rules = TopologyEngine.get_applicable_rules(self.geom_type)
        for rule in self.applicable_rules:
            self.cmb_rules.addItem(rule.name, rule.code)

        self.cmb_rules.currentIndexChanged.connect(self._on_rule_selected)
        rule_layout.addWidget(self.cmb_rules)

        self.lbl_rule_desc = QLabel()
        self.lbl_rule_desc.setWordWrap(True)
        self.lbl_rule_desc.setStyleSheet("font-size: 11px;")
        rule_layout.addWidget(self.lbl_rule_desc)
        layout.addWidget(self.grp_rule)

        # Dynamic Parameters Section
        self.grp_params = QGroupBox(f"Rule Parameters (Specified in {self.linear_unit})")
        self.params_layout = QVBoxLayout(self.grp_params)
        self.params_layout.setSpacing(10)

        # 1. Tolerance input (for Point Duplicates, Line Dangles, Line Duplicate Nodes)
        self.wgt_tolerance = QWidget()
        tol_layout = QHBoxLayout(self.wgt_tolerance)
        tol_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_tol = QLabel(f"Tolerance ({self.linear_unit}):")
        self.lbl_tol.setMinimumWidth(180)
        self.spin_tol = QDoubleSpinBox()
        if self.is_degree:
            self.spin_tol.setDecimals(6)
            self.spin_tol.setRange(0.0, 10.0)
            self.spin_tol.setValue(0.0001)
            self.spin_tol.setSingleStep(0.00005)
        else:
            self.spin_tol.setDecimals(3)
            self.spin_tol.setRange(0.0, 1000.0)
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

        # 5. Angle threshold (for Line Spikes / Needle-like turns)
        self.wgt_angle = QWidget()
        angle_layout = QHBoxLayout(self.wgt_angle)
        angle_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_angle = QLabel("Max Spike Angle (°):")
        self.lbl_angle.setMinimumWidth(180)
        self.spin_angle = QDoubleSpinBox()
        self.spin_angle.setDecimals(1)
        self.spin_angle.setRange(1.0, 90.0)
        self.spin_angle.setValue(15.0)
        self.spin_angle.setSingleStep(1.0)
        angle_layout.addWidget(self.lbl_angle)
        angle_layout.addWidget(self.spin_angle)
        angle_layout.addStretch()
        self.params_layout.addWidget(self.wgt_angle)

        # 6. Label for rules that do not require numeric thresholds
        self.lbl_no_param = QLabel("ℹ️ This topological rule validates spatial topology definitions and requires no threshold.")
        self.lbl_no_param.setStyleSheet("color: #10b981; font-style: italic; padding: 4px;")
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

        self.btn_add = QPushButton("Add Rule")
        self.btn_add.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_add)

        layout.addLayout(btn_layout)

    def apply_theme(self, theme_name: str = None):
        tokens = ThemeManager.get_tokens(theme_name)
        bg = tokens.get("panel_bg", "#ffffff")
        toolbar_bg = tokens.get("toolbar_bg", "#f8fafc")
        text = tokens.get("text", "#1e293b")
        text_muted = tokens.get("text_muted", "#64748b")
        border = tokens.get("border", "#e2e8f0")
        accent = tokens.get("accent", "#0284c7")

        self.setStyleSheet(f"""
            QDialog {{ background-color: {bg}; color: {text}; }}
            QGroupBox {{ font-weight: 600; border: 1px solid {border}; border-radius: 6px; margin-top: 8px; padding-top: 12px; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; color: {text}; }}
            QComboBox, QDoubleSpinBox {{ background-color: {bg}; color: {text}; border: 1px solid {border}; border-radius: 4px; padding: 4px 8px; }}
            QComboBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {accent}; }}
            QLabel {{ color: {text}; }}
        """)

        self.info_banner.setStyleSheet(f"""
            QFrame {{
                background-color: {toolbar_bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
            QLabel {{ color: {text}; font-size: 12px; }}
        """)

        self.btn_cancel.setIcon(get_lucide_icon("close", theme_name=theme_name, size=16))
        self.btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: {toolbar_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                border-color: {text_muted};
            }}
        """)

        self.btn_add.setIcon(get_lucide_icon("plus", theme_name=theme_name, color="#ffffff", size=16))
        self.btn_add.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent};
                color: #ffffff;
                border: 1px solid {accent};
                border-radius: 4px;
                padding: 6px 18px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)

    def _on_rule_selected(self, index: int):
        if index < 0 or index >= len(self.applicable_rules):
            return
        rule = self.applicable_rules[index]
        self.lbl_rule_desc.setText(rule.description)

        code = rule.code
        self.wgt_tolerance.hide()
        self.wgt_length.hide()
        self.wgt_area.hide()
        self.wgt_thinness.hide()
        self.wgt_angle.hide()
        self.lbl_no_param.hide()

        if code == TopologyRuleCode.POINT_DUPLICATES:
            self.lbl_tol.setText(f"Snap Tolerance ({self.linear_unit}):")
            self.wgt_tolerance.show()
        elif code == TopologyRuleCode.LINE_DUPLICATE_NODES:
            self.lbl_tol.setText(f"Distance Tolerance ({self.linear_unit}, 0 = exact):")
            self.wgt_tolerance.show()
        elif code == TopologyRuleCode.LINE_SPIKES:
            self.wgt_angle.show()
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

        if code in (TopologyRuleCode.POINT_DUPLICATES, TopologyRuleCode.LINE_DANGLES, TopologyRuleCode.LINE_DUPLICATE_NODES):
            params["tolerance"] = self.spin_tol.value()
        elif code == TopologyRuleCode.LINE_SPIKES:
            params["max_angle"] = self.spin_angle.value()
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
    Fully integrated with Chisel Editor's design language, theme engine, and vector icons.
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

        self.setWindowTitle(f"Topology Checker & Validator — {self.layer_name}")
        self.resize(1060, 740)
        self.setMinimumSize(880, 580)

        # Modeless tool window
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        self._setup_ui()
        self.apply_theme()
        self._update_rules_table()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # =========================================================
        # 1. Header Card (Layer Identity & Health Dashboard)
        # =========================================================
        self.header_card = QFrame()
        header_layout = QHBoxLayout(self.header_card)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.setSpacing(12)

        # Left Info Stack
        left_info = QVBoxLayout()
        left_info.setSpacing(5)

        self.lbl_title = QLabel(f"🗺️ <b>{self.layer_name}</b>")
        self.lbl_title.setStyleSheet("font-size: 14px;")
        left_info.addWidget(self.lbl_title)

        # Badges Row
        badges_layout = QHBoxLayout()
        badges_layout.setSpacing(6)

        geom_symbol = "🔷" if "line" in self.geom_type.lower() else ("🔶" if "poly" in self.geom_type.lower() else "🟢")
        self.badge_geom = QLabel(f"{geom_symbol} {self.geom_type.upper()}")
        self.badge_features = QLabel(f"{len(self.gdf):,} features")
        self.badge_crs = QLabel(f"🌐 {self.crs_str}")
        self.badge_units = QLabel(f"📏 {self.linear_unit}")

        for b in (self.badge_geom, self.badge_features, self.badge_crs, self.badge_units):
            b.setStyleSheet("font-size: 11px; padding: 2px 7px; border-radius: 4px;")
            badges_layout.addWidget(b)

        badges_layout.addStretch()
        left_info.addLayout(badges_layout)
        header_layout.addLayout(left_info, stretch=1)

        # Right Summary Badges Stack
        right_stack = QVBoxLayout()
        right_stack.setSpacing(5)
        right_stack.setAlignment(Qt.AlignmentFlag.AlignRight)

        summary_row = QHBoxLayout()
        summary_row.setSpacing(6)

        self.badge_status = QLabel("⚪ Not Audited")
        self.badge_errors = QLabel("🔴 0 Errors")
        self.badge_warnings = QLabel("🟡 0 Warnings")
        self.badge_fixable = QLabel("⚡ 0 Fixable")

        for b in (self.badge_status, self.badge_errors, self.badge_warnings, self.badge_fixable):
            b.setStyleSheet("font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 4px;")
            summary_row.addWidget(b)

        right_stack.addLayout(summary_row)

        map_toggle_layout = QHBoxLayout()
        map_toggle_layout.addStretch()
        self.chk_show_map = QCheckBox("Show Errors on Map")
        self.chk_show_map.setChecked(True)
        self.chk_show_map.toggled.connect(self._toggle_map_error_layer)
        map_toggle_layout.addWidget(self.chk_show_map)
        right_stack.addLayout(map_toggle_layout)

        header_layout.addLayout(right_stack)
        main_layout.addWidget(self.header_card)

        # =========================================================
        # 2. Splitter: Top is Rules Pane, Bottom is Errors Pane
        # =========================================================
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # --- Top Section: Configured Rules Pane ---
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        # Rules Toolbar
        rules_tb_layout = QHBoxLayout()
        self.lbl_rules_heading = QLabel("<b>Validation Rules</b>")
        self.lbl_rules_heading.setStyleSheet("font-size: 12px;")
        rules_tb_layout.addWidget(self.lbl_rules_heading)

        self.btn_add_rule = QPushButton("Add Rule...")
        self.btn_add_rule.clicked.connect(self._on_add_rule_clicked)
        rules_tb_layout.addWidget(self.btn_add_rule)

        self.btn_add_defaults = QPushButton("Recommended Rules")
        self.btn_add_defaults.setToolTip("Quickly load recommended rules matching layer geometry and CRS")
        self.btn_add_defaults.clicked.connect(self._on_add_recommended_rules)
        rules_tb_layout.addWidget(self.btn_add_defaults)

        self.btn_remove_rule = QPushButton("Remove")
        self.btn_remove_rule.clicked.connect(self._on_remove_selected_rule)
        rules_tb_layout.addWidget(self.btn_remove_rule)

        self.btn_clear_rules = QPushButton("Clear All")
        self.btn_clear_rules.clicked.connect(self._on_clear_all_rules)
        rules_tb_layout.addWidget(self.btn_clear_rules)

        rules_tb_layout.addStretch()

        # Run Check Button
        self.btn_run = QPushButton("Run Topology Check")
        self.btn_run.setFixedHeight(30)
        self.btn_run.clicked.connect(self._on_run_checks)
        rules_tb_layout.addWidget(self.btn_run)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setFixedWidth(120)
        self.progress_bar.hide()
        rules_tb_layout.addWidget(self.progress_bar)

        top_layout.addLayout(rules_tb_layout)

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
        self.rules_table.verticalHeader().setDefaultSectionSize(26)
        self.rules_table.setFixedHeight(140)
        top_layout.addWidget(self.rules_table)

        self.splitter.addWidget(top_widget)

        # --- Bottom Section: Errors Table & Remediation ---
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(8)

        # Errors Toolbar
        table_tb_layout = QHBoxLayout()
        table_tb_layout.setSpacing(8)

        self.lbl_status = QLabel("<b>Status:</b> Ready. Click 'Run Topology Check' to audit layer.")
        self.lbl_status.setStyleSheet("font-size: 12px;")
        table_tb_layout.addWidget(self.lbl_status)
        table_tb_layout.addStretch()

        self.lbl_filter = QLabel("Filter:")
        table_tb_layout.addWidget(self.lbl_filter)

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("All Issues", "all")
        self.filter_combo.addItem("Errors Only", "error")
        self.filter_combo.addItem("Warnings Only", "warning")
        self.filter_combo.addItem("Auto-Repairable Only", "fixable")
        self.filter_combo.currentIndexChanged.connect(self._apply_error_filter)
        table_tb_layout.addWidget(self.filter_combo)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search errors (rule, feature, text)...")
        self.search_input.setFixedWidth(240)
        self.search_input.textChanged.connect(self._apply_error_filter)
        table_tb_layout.addWidget(self.search_input)

        self.lbl_filter_count = QLabel("")
        self.lbl_filter_count.setStyleSheet("font-size: 11px;")
        table_tb_layout.addWidget(self.lbl_filter_count)

        bottom_layout.addLayout(table_tb_layout)

        # Errors Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["#", "Severity", "Rule Violated", "Feature ID(s)", "Description", "Auto-Fix"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_zoom_to_selected)
        bottom_layout.addWidget(self.table)

        # Bottom Remediation Action Bar
        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        self.btn_zoom = QPushButton("Zoom to Defect")
        self.btn_zoom.clicked.connect(self._on_zoom_to_selected)
        self.btn_zoom.setEnabled(False)
        btn_box.addWidget(self.btn_zoom)

        self.btn_fix_single = QPushButton("Fix Selected")
        self.btn_fix_single.clicked.connect(self._on_fix_selected)
        self.btn_fix_single.setEnabled(False)
        btn_box.addWidget(self.btn_fix_single)

        self.btn_fix_all = QPushButton("Fix All Auto-repairable")
        self.btn_fix_all.clicked.connect(self._on_fix_all)
        self.btn_fix_all.setEnabled(False)
        btn_box.addWidget(self.btn_fix_all)

        self.btn_export = QPushButton("Export GeoJSON...")
        self.btn_export.clicked.connect(self._on_export_errors)
        self.btn_export.setEnabled(False)
        btn_box.addWidget(self.btn_export)

        btn_box.addStretch()

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)
        btn_box.addWidget(self.btn_close)

        bottom_layout.addLayout(btn_box)
        self.splitter.addWidget(bottom_widget)

        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 4)
        main_layout.addWidget(self.splitter)

    # -------------------------------------------------------------
    # Theme Engine Integration
    # -------------------------------------------------------------

    def apply_theme(self, theme_name: str = None):
        """Applies dynamic theme styling matching the active Chisel Editor theme palette."""
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

        # Global Dialog Style
        self.setStyleSheet(f"""
            QDialog {{ background-color: {bg}; color: {text}; }}
            QLabel {{ color: {text}; }}
            QSplitter::handle {{ background-color: {border}; }}
            QSplitter::handle:hover {{ background-color: {accent}; }}
        """)

        # Header Card Style
        self.header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {toolbar_bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
        """)

        # Metadata Badges Style
        badge_style = f"background-color: {bg}; color: {text_muted}; border: 1px solid {border}; border-radius: 4px; padding: 2px 7px;"
        self.badge_geom.setStyleSheet(f"background-color: {bg}; color: {accent}; border: 1px solid {border}; border-radius: 4px; padding: 2px 7px; font-weight: 600;")
        self.badge_features.setStyleSheet(badge_style)
        self.badge_crs.setStyleSheet(badge_style)
        self.badge_units.setStyleSheet(badge_style)

        # Status Badges
        self._update_status_badges_style(is_dark)

        # Tables Style (Both Rules Table & Errors Table)
        table_style = f"""
            QTableWidget {{
                background-color: {bg};
                color: {text};
                gridline-color: {grid};
                border: 1px solid {border};
                border-radius: 4px;
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
        self.rules_table.setStyleSheet(table_style)
        self.table.setStyleSheet(table_style)

        # Controls & Search Input
        ctrl_style = f"""
            QLineEdit, QComboBox {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            QLineEdit:focus, QComboBox:focus {{
                border-color: {accent};
            }}
        """
        self.search_input.setStyleSheet(ctrl_style)
        self.filter_combo.setStyleSheet(ctrl_style)

        # Buttons Styling & Lucide Icons
        btn_neutral_style = f"""
            QPushButton {{
                background-color: {toolbar_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover:enabled {{
                background-color: {hover};
                border-color: {accent};
            }}
            QPushButton:pressed:enabled {{
                background-color: {active};
            }}
            QPushButton:disabled {{
                color: {text_muted};
                opacity: 0.5;
            }}
        """

        for btn in (self.btn_add_rule, self.btn_add_defaults, self.btn_remove_rule, self.btn_clear_rules, self.btn_zoom, self.btn_fix_single, self.btn_export, self.btn_close):
            btn.setStyleSheet(btn_neutral_style)

        self.btn_add_rule.setIcon(get_lucide_icon("plus", theme_name=theme_name, size=14))
        self.btn_add_defaults.setIcon(get_lucide_icon("zap", theme_name=theme_name, size=14))
        self.btn_remove_rule.setIcon(get_lucide_icon("trash-2", theme_name=theme_name, size=14))
        self.btn_clear_rules.setIcon(get_lucide_icon("eraser", theme_name=theme_name, size=14))
        self.btn_zoom.setIcon(get_lucide_icon("focus", theme_name=theme_name, size=14))
        self.btn_fix_single.setIcon(get_lucide_icon("wrench", theme_name=theme_name, size=14))
        self.btn_export.setIcon(get_lucide_icon("file-down", theme_name=theme_name, size=14))
        self.btn_close.setIcon(get_lucide_icon("close", theme_name=theme_name, size=14))

        # Primary Run Button
        self.btn_run.setIcon(get_lucide_icon("play", color="#ffffff", size=14))
        self.btn_run.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent};
                color: #ffffff;
                border: 1px solid {accent};
                border-radius: 4px;
                padding: 5px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover:enabled {{
                opacity: 0.92;
            }}
            QPushButton:pressed:enabled {{
                background-color: {active};
            }}
            QPushButton:disabled {{
                background-color: {border};
                color: {text_muted};
                border-color: {border};
            }}
        """)

        # Prominent Fix All Button
        self.btn_fix_all.setIcon(get_lucide_icon("zap", color="#ffffff", size=14))
        self.btn_fix_all.setStyleSheet(f"""
            QPushButton {{
                background-color: #10b981;
                color: #ffffff;
                border: 1px solid #10b981;
                border-radius: 4px;
                padding: 4px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton:hover:enabled {{
                background-color: #059669;
            }}
            QPushButton:disabled {{
                background-color: {border};
                color: {text_muted};
                border-color: {border};
            }}
        """)

    def _update_status_badges_style(self, is_dark: bool = False):
        if not self.report or self.report.total_errors == 0:
            self.badge_status.setText("✅ Clean (0 Issues)" if self.report else "⚪ Not Audited")
            self.badge_status.setStyleSheet("background-color: rgba(16, 185, 129, 0.15); color: #10b981; font-weight: 600; padding: 3px 8px; border-radius: 4px;" if self.report else "background-color: rgba(100, 116, 139, 0.15); color: #64748b; font-weight: 600; padding: 3px 8px; border-radius: 4px;")
            self.badge_errors.hide()
            self.badge_warnings.hide()
            self.badge_fixable.hide()
        else:
            err_cnt = sum(1 for e in self.report.errors if e.severity == "error")
            warn_cnt = self.report.total_errors - err_cnt
            fix_cnt = sum(1 for e in self.report.errors if e.can_fix)

            self.badge_status.setText(f"● {self.report.total_errors:,} Issues")
            self.badge_status.setStyleSheet("background-color: rgba(239, 68, 68, 0.15); color: #ef4444; font-weight: 600; padding: 3px 8px; border-radius: 4px;")

            self.badge_errors.setText(f"🔴 {err_cnt:,} Errors")
            self.badge_errors.setStyleSheet("background-color: rgba(239, 68, 68, 0.12); color: #ef4444; font-weight: 600; padding: 3px 8px; border-radius: 4px;")
            self.badge_errors.setVisible(err_cnt > 0)

            self.badge_warnings.setText(f"🟡 {warn_cnt:,} Warnings")
            self.badge_warnings.setStyleSheet("background-color: rgba(245, 158, 11, 0.12); color: #f59e0b; font-weight: 600; padding: 3px 8px; border-radius: 4px;")
            self.badge_warnings.setVisible(warn_cnt > 0)

            self.badge_fixable.setText(f"⚡ {fix_cnt:,} Fixable")
            self.badge_fixable.setStyleSheet("background-color: rgba(16, 185, 129, 0.12); color: #10b981; font-weight: 600; padding: 3px 8px; border-radius: 4px;")
            self.badge_fixable.setVisible(fix_cnt > 0)

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
            item_fix = QTableWidgetItem("✅ Yes" if can_fix_str == "Yes" else "—")

            self.rules_table.setItem(idx, 0, item_id)
            self.rules_table.setItem(idx, 1, item_name)
            self.rules_table.setItem(idx, 2, item_geom)
            self.rules_table.setItem(idx, 3, item_param)
            self.rules_table.setItem(idx, 4, item_fix)

        cnt = len(self.configured_rules)
        self.lbl_rules_heading.setText(f"<b>Validation Rules ({cnt} active)</b>")
        btn_label = f"Run Topology Check ({cnt} rules)" if cnt > 0 else "Run Topology Check"
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
        """Refreshes dialog state when active layer or tab changes."""
        self.gdf = gdf.copy()
        self.layer_name = layer_name or "Spatial Layer"
        if on_layer_updated:
            self.on_layer_updated = on_layer_updated
        if layer_id:
            self.layer_id = layer_id

        from core.spatial_ops import SpatialOps
        self.geom_type = SpatialOps.get_layer_geometry_type(self.gdf)
        self.crs_str, self.linear_unit, self.area_unit, self.is_degree = get_layer_crs_unit_info(self.gdf)

        self.setWindowTitle(f"Topology Checker & Validator — {self.layer_name}")
        self.lbl_title.setText(f"🗺️ <b>{self.layer_name}</b>")
        geom_symbol = "🔷" if "line" in self.geom_type.lower() else ("🔶" if "poly" in self.geom_type.lower() else "🟢")
        self.badge_geom.setText(f"{geom_symbol} {self.geom_type.upper()}")
        self.badge_features.setText(f"{len(self.gdf):,} features")
        self.badge_crs.setText(f"🌐 {self.crs_str}")
        self.badge_units.setText(f"📏 {self.linear_unit}")

        self.report = None
        self.table.setRowCount(0)
        self.lbl_status.setText("<b>Status:</b> Ready. Click 'Run Topology Check' to audit layer.")
        self.btn_zoom.setEnabled(False)
        self.btn_fix_single.setEnabled(False)
        self.btn_fix_all.setEnabled(False)
        self.btn_export.setEnabled(False)
        self._update_status_badges_style()

        if self.map_panel:
            self.map_panel.remove_vector_layer(self.ERROR_LAYER_ID)

        self._update_rules_table()

    def _on_run_checks(self):
        if not self.configured_rules:
            ToastNotification.show_toast(self, "Please configure at least one rule first.", "warning")
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
            self.lbl_status.setText(f"<span style='color:#ef4444;'>Error: {error_msg}</span>")
            ToastNotification.show_toast(self, f"Topology check error: {error_msg}", "error")
            return

        self.report = report
        if self.chk_show_map.isChecked():
            self._update_map_error_layer()
        self._populate_table(report)
        self._update_status_badges_style()

    def _populate_table(self, report: TopologyReport):
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(0)
            if not report or report.total_errors == 0:
                self.lbl_status.setText("✅ <b>No topology errors found! Layer satisfies all rules.</b>")
                self.btn_fix_all.setEnabled(False)
                self.btn_fix_single.setEnabled(False)
                self.btn_export.setEnabled(False)
                self.btn_zoom.setEnabled(False)
                self.lbl_filter_count.setText("")
                ToastNotification.show_toast(self, "✅ Topologically clean! 0 errors found.", "success")
                return

            err_count = sum(1 for e in report.errors if e.severity == "error")
            warn_count = report.total_errors - err_count
            fix_count = sum(1 for e in report.errors if e.can_fix)

            summary_str = f"⚠️ <b>Found {report.total_errors:,} issue(s)</b> ({err_count} errors, {warn_count} warnings)"
            self.lbl_status.setText(summary_str)

            self.btn_fix_all.setText(f"Fix All Auto-repairable ({fix_count:,})")
            self.btn_fix_all.setEnabled(fix_count > 0)
            self.btn_fix_single.setEnabled(True)
            self.btn_export.setEnabled(True)
            self.btn_zoom.setEnabled(True)

            display_errors = report.errors[:2000]
            self.table.setRowCount(len(display_errors))
            for row_idx, err in enumerate(display_errors):
                item_id = QTableWidgetItem(str(err.id + 1))
                item_sev = QTableWidgetItem("🔴 Error" if err.severity == "error" else ("🟡 Warning" if err.severity == "warning" else "ℹ️ Info"))
                item_rule = QTableWidgetItem(err.rule_name)
                item_feat = QTableWidgetItem(", ".join(map(str, err.feature_ids)) if err.feature_ids else "-")
                item_desc = QTableWidgetItem(err.description)
                item_fix = QTableWidgetItem("⚡ Ready" if err.can_fix else "—")

                if err.severity == "error":
                    item_sev.setForeground(QBrush(QColor("#ef4444")))
                    item_sev.setFont(QFont(self.font().family(), weight=QFont.Weight.Bold))
                elif err.severity == "warning":
                    item_sev.setForeground(QBrush(QColor("#f59e0b")))
                    item_sev.setFont(QFont(self.font().family(), weight=QFont.Weight.Bold))
                else:
                    item_sev.setForeground(QBrush(QColor("#3b82f6")))

                if err.can_fix:
                    item_fix.setForeground(QBrush(QColor("#10b981")))
                    item_fix.setFont(QFont(self.font().family(), weight=QFont.Weight.Bold))

                self.table.setItem(row_idx, 0, item_id)
                self.table.setItem(row_idx, 1, item_sev)
                self.table.setItem(row_idx, 2, item_rule)
                self.table.setItem(row_idx, 3, item_feat)
                self.table.setItem(row_idx, 4, item_desc)
                self.table.setItem(row_idx, 5, item_fix)

            self._apply_error_filter()
            self.table.selectRow(0)
        finally:
            self.table.setUpdatesEnabled(True)

    def _apply_error_filter(self):
        query = self.search_input.text().strip().lower()
        filter_mode = self.filter_combo.currentData() or "all"

        if not self.report or not self.report.errors:
            self.lbl_filter_count.setText("")
            return

        visible_count = 0
        total_rows = self.table.rowCount()
        for row in range(total_rows):
            err_idx = int(self.table.item(row, 0).text()) - 1
            if not (0 <= err_idx < len(self.report.errors)):
                continue
            err = self.report.errors[err_idx]

            match_mode = True
            if filter_mode == "error" and err.severity != "error":
                match_mode = False
            elif filter_mode == "warning" and err.severity != "warning":
                match_mode = False
            elif filter_mode == "fixable" and not err.can_fix:
                match_mode = False

            match_query = True
            if query:
                searchable = f"{err.rule_name} {err.description} {' '.join(map(str, err.feature_ids))}".lower()
                if query not in searchable:
                    match_query = False

            should_hide = not (match_mode and match_query)
            self.table.setRowHidden(row, should_hide)
            if not should_hide:
                visible_count += 1

        self.lbl_filter_count.setText(f"Showing: {visible_count:,} / {total_rows:,}")

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
                is_active=False,
                geom_type="any",
                color="#ef4444",
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
        err_id_item = self.table.item(row, 0)
        if not err_id_item:
            return
        err_idx = int(err_id_item.text()) - 1
        if 0 <= err_idx < len(self.report.errors):
            err = self.report.errors[err_idx]
            self.btn_fix_single.setEnabled(err.can_fix)
            self._zoom_to_error_geometry(err.geometry, err.id, err=err)

    def _on_zoom_to_selected(self):
        selected_rows = self.table.selectedIndexes()
        if not selected_rows or not self.report:
            return
        row = selected_rows[0].row()
        err_id_item = self.table.item(row, 0)
        if not err_id_item:
            return
        err_idx = int(err_id_item.text()) - 1
        if 0 <= err_idx < len(self.report.errors):
            err = self.report.errors[err_idx]
            self._zoom_to_error_geometry(err.geometry, err.id, err=err)

    def _transform_geom_to_4326(self, geom):
        """Converts any Shapely error geometry to WGS 84 (EPSG:4326) coordinates for Leaflet."""
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
        """Focuses and highlights the defective error geometry piece on the Leaflet map."""
        if geom is None or not self.map_panel:
            return

        try:
            geom_4326 = self._transform_geom_to_4326(geom)
            if geom_4326 is None or (hasattr(geom_4326, "is_empty") and geom_4326.is_empty):
                return

            bounds = geom_4326.bounds
            minx, miny, maxx, maxy = bounds

            span_x = abs(maxx - minx)
            span_y = abs(maxy - miny)
            if span_x < 0.0008 or span_y < 0.0008:
                delta = 0.0006
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

            parent_ids = [int(x) for x in err.feature_ids] if err and err.feature_ids else []
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
        err_id_item = self.table.item(row, 0)
        if not err_id_item:
            return
        err_idx = int(err_id_item.text()) - 1
        if not (0 <= err_idx < len(self.report.errors)):
            return

        err = self.report.errors[err_idx]
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
            "This will make geometries OGC valid, node self-intersections, remove duplicate vertices, "
            "prune spikes, resolve line overlaps, snap undershoots, merge pseudo-nodes, "
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

        ToastNotification.show_toast(self, f"Successfully resolved {count:,} topology issues!", "success")
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
