import os
import json
from typing import Callable, Optional, Dict, List, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QCheckBox, QDoubleSpinBox, QGroupBox,
    QProgressBar, QSplitter, QWidget, QFileDialog, QMessageBox, QAbstractItemView,
    QComboBox, QFrame, QLineEdit, QDockWidget, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
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
    All topology rules and defect measurements are standardized in metric units (m, m²).
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
        try:
            b = gdf.total_bounds
            if abs(b[0]) <= 180.0 and abs(b[2]) <= 180.0 and abs(b[1]) <= 90.0 and abs(b[3]) <= 90.0:
                is_degree = True
                crs_name = "EPSG:4326 (Inferred)"
        except Exception:
            pass

    return crs_name, "meters (m)", "square meters (m²)", is_degree


class AddRuleDialog(QDialog):
    """
    Modal dialog allowing the user to select and configure a topology rule
    with parameters explicitly formatted in metric units (m, m²).
    """

    def __init__(
        self,
        geom_type: str,
        crs_str: str,
        linear_unit: str = "meters (m)",
        area_unit: str = "square meters (m²)",
        is_degree: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.geom_type = geom_type
        self.crs_str = crs_str
        self.linear_unit = "meters (m)"
        self.area_unit = "square meters (m²)"
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
            f"<b>Distance Unit:</b> <span style='font-weight:600;'>meters (m)</span> &nbsp;|&nbsp; "
            f"<b>Area Unit:</b> <span style='font-weight:600;'>square meters (m²)</span> "
            f"<span style='color:#64748b;'>(Auto-scaled to layer CRS)</span>"
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
        self.grp_params = QGroupBox("Rule Parameters (Specified in Metric: m / m²)")
        self.params_layout = QVBoxLayout(self.grp_params)
        self.params_layout.setSpacing(10)

        # 1. Tolerance input (for Point Duplicates, Line Dangles, Line Duplicate Nodes)
        self.wgt_tolerance = QWidget()
        tol_layout = QHBoxLayout(self.wgt_tolerance)
        tol_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_tol = QLabel("Tolerance (m):")
        self.lbl_tol.setMinimumWidth(180)
        self.spin_tol = QDoubleSpinBox()
        self.spin_tol.setDecimals(3)
        self.spin_tol.setRange(0.0, 100000.0)
        self.spin_tol.setValue(0.05)
        self.spin_tol.setSingleStep(0.01)
        self.spin_tol.setSuffix(" m")
        tol_layout.addWidget(self.lbl_tol)
        tol_layout.addWidget(self.spin_tol)
        tol_layout.addStretch()
        self.params_layout.addWidget(self.wgt_tolerance)

        # 2. Min length input (for Line Short Segments)
        self.wgt_length = QWidget()
        len_layout = QHBoxLayout(self.wgt_length)
        len_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_len = QLabel("Min Segment Length (m):")
        self.lbl_len.setMinimumWidth(180)
        self.spin_len = QDoubleSpinBox()
        self.spin_len.setDecimals(2)
        self.spin_len.setRange(0.01, 100000.0)
        self.spin_len.setValue(0.50)
        self.spin_len.setSingleStep(0.10)
        self.spin_len.setSuffix(" m")
        len_layout.addWidget(self.lbl_len)
        len_layout.addWidget(self.spin_len)
        len_layout.addStretch()
        self.params_layout.addWidget(self.wgt_length)

        # 3. Area input (for Polygon Overlaps, Slivers, Gaps)
        self.wgt_area = QWidget()
        area_layout = QHBoxLayout(self.wgt_area)
        area_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_area = QLabel("Area Threshold (m²):")
        self.lbl_area.setMinimumWidth(180)
        self.spin_area = QDoubleSpinBox()
        self.spin_area.setDecimals(2)
        self.spin_area.setRange(0.01, 10000000.0)
        self.spin_area.setValue(1.0)
        self.spin_area.setSingleStep(0.50)
        self.spin_area.setSuffix(" m²")
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


class TopologyRuleRowWidget(QFrame):
    """
    Inline row representing a single configured topology rule.
    Includes:
      - QComboBox for selecting / switching the rule
      - Dynamic parameter controls for the selected rule (spinboxes with units)
      - Delete button on the far right
    """
    delete_requested = pyqtSignal(object)  # emits self
    changed = pyqtSignal()

    def __init__(
        self,
        applicable_rules: List[TopologyRuleInfo],
        initial_rule_code: str,
        initial_params: Optional[dict] = None,
        linear_unit: str = "meters (m)",
        area_unit: str = "square meters (m²)",
        is_degree: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.applicable_rules = applicable_rules
        self.linear_unit = linear_unit
        self.area_unit = area_unit
        self.is_degree = is_degree
        self._initial_rule_code = initial_rule_code
        self._initial_params = initial_params or {}

        self._setup_ui()
        self.apply_theme()

    def _setup_ui(self):
        self.setObjectName("TopologyRuleRowWidget")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(8)

        # 1. Kural Adı (ComboBox)
        self.combo_rule = QComboBox()
        self.combo_rule.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.combo_rule.setMinimumWidth(150)
        selected_idx = 0
        for idx, rule in enumerate(self.applicable_rules):
            self.combo_rule.addItem(rule.name, rule.code)
            if rule.code == self._initial_rule_code:
                selected_idx = idx

        self.combo_rule.setCurrentIndex(selected_idx)
        self.combo_rule.currentIndexChanged.connect(self._on_rule_changed)
        layout.addWidget(self.combo_rule)

        # 2. Parametreler (Kural Adı ile Silme Butonu Arasında)
        self.param_container = QWidget()
        self.param_layout = QHBoxLayout(self.param_container)
        self.param_layout.setContentsMargins(0, 0, 0, 0)
        self.param_layout.setSpacing(6)
        layout.addWidget(self.param_container, stretch=1)

        # 3. Silme Butonu (En Sağda)
        self.btn_delete = QPushButton()
        self.btn_delete.setObjectName("btn_rule_delete")
        self.btn_delete.setFixedSize(26, 26)
        self.btn_delete.setIconSize(QSize(16, 16))
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setToolTip("Remove rule")
        self.btn_delete.clicked.connect(lambda: self.delete_requested.emit(self))
        layout.addWidget(self.btn_delete)

        self._build_param_controls(self._initial_rule_code, self._initial_params)

    def _on_rule_changed(self, index: int):
        code = self.combo_rule.currentData()
        self._build_param_controls(code, {})
        self.changed.emit()

    def _build_param_controls(self, code: str, initial_params: dict):
        # Clear existing controls
        while self.param_layout.count():
            item = self.param_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for attr in ("spin_tol", "spin_angle", "spin_len", "spin_area", "spin_thin"):
            if hasattr(self, attr):
                delattr(self, attr)

        linear_suffix = " m"
        area_suffix = " m²"

        if code in (TopologyRuleCode.POINT_DUPLICATES, TopologyRuleCode.LINE_DANGLES, TopologyRuleCode.LINE_DUPLICATE_NODES):
            lbl_text = "Tol:"
            if code == TopologyRuleCode.LINE_DANGLES:
                lbl_text = "Snap:"
            lbl = QLabel(lbl_text)
            self.spin_tol = QDoubleSpinBox()
            self.spin_tol.setSuffix(linear_suffix)
            self.spin_tol.setMinimumWidth(75)
            self.spin_tol.setDecimals(3)
            self.spin_tol.setRange(0.0 if code == TopologyRuleCode.LINE_DUPLICATE_NODES else 0.001, 100000.0)
            def_val = 0.05 if code == TopologyRuleCode.POINT_DUPLICATES else (0.10 if code == TopologyRuleCode.LINE_DANGLES else 0.0)
            self.spin_tol.setValue(initial_params.get("tolerance", def_val))
            self.spin_tol.setSingleStep(0.01)
            self.param_layout.addWidget(lbl)
            self.param_layout.addWidget(self.spin_tol)
            self.param_layout.addStretch()

        elif code == TopologyRuleCode.LINE_SPIKES:
            lbl = QLabel("Angle:")
            self.spin_angle = QDoubleSpinBox()
            self.spin_angle.setDecimals(1)
            self.spin_angle.setRange(1.0, 90.0)
            self.spin_angle.setValue(initial_params.get("max_angle", 15.0))
            self.spin_angle.setSingleStep(1.0)
            self.spin_angle.setSuffix("°")
            self.spin_angle.setMinimumWidth(65)
            self.param_layout.addWidget(lbl)
            self.param_layout.addWidget(self.spin_angle)
            self.param_layout.addStretch()

        elif code == TopologyRuleCode.LINE_SHORT_SEGMENTS:
            lbl = QLabel("Min Len:")
            self.spin_len = QDoubleSpinBox()
            self.spin_len.setSuffix(linear_suffix)
            self.spin_len.setMinimumWidth(75)
            self.spin_len.setDecimals(2)
            self.spin_len.setRange(0.01, 100000.0)
            self.spin_len.setValue(initial_params.get("min_length", 0.50))
            self.spin_len.setSingleStep(0.10)
            self.param_layout.addWidget(lbl)
            self.param_layout.addWidget(self.spin_len)
            self.param_layout.addStretch()

        elif code == TopologyRuleCode.POLYGON_OVERLAPS:
            lbl = QLabel("Overlap:")
            self.spin_area = QDoubleSpinBox()
            self.spin_area.setSuffix(area_suffix)
            self.spin_area.setMinimumWidth(80)
            self.spin_area.setDecimals(2)
            self.spin_area.setRange(0.01, 10000000.0)
            self.spin_area.setValue(initial_params.get("min_area", 0.10))
            self.spin_area.setSingleStep(0.50)
            self.param_layout.addWidget(lbl)
            self.param_layout.addWidget(self.spin_area)
            self.param_layout.addStretch()

        elif code == TopologyRuleCode.POLYGON_SLIVERS:
            lbl1 = QLabel("Area:")
            self.spin_area = QDoubleSpinBox()
            self.spin_area.setSuffix(area_suffix)
            self.spin_area.setMinimumWidth(75)
            self.spin_area.setDecimals(2)
            self.spin_area.setRange(0.01, 10000000.0)
            self.spin_area.setValue(initial_params.get("min_area", 1.0))
            self.spin_area.setSingleStep(0.50)

            lbl2 = QLabel("Thin:")
            self.spin_thin = QDoubleSpinBox()
            self.spin_thin.setDecimals(3)
            self.spin_thin.setRange(0.001, 1.0)
            self.spin_thin.setValue(initial_params.get("thinness", 0.030))
            self.spin_thin.setSingleStep(0.005)
            self.spin_thin.setMinimumWidth(60)

            self.param_layout.addWidget(lbl1)
            self.param_layout.addWidget(self.spin_area)
            self.param_layout.addWidget(lbl2)
            self.param_layout.addWidget(self.spin_thin)
            self.param_layout.addStretch()

        elif code == TopologyRuleCode.POLYGON_GAPS:
            lbl = QLabel("Gap:")
            self.spin_area = QDoubleSpinBox()
            self.spin_area.setSuffix(area_suffix)
            self.spin_area.setMinimumWidth(80)
            self.spin_area.setDecimals(2)
            self.spin_area.setRange(0.01, 10000000.0)
            self.spin_area.setValue(initial_params.get("max_gap_area", 50.0))
            self.spin_area.setSingleStep(5.0)
            self.param_layout.addWidget(lbl)
            self.param_layout.addWidget(self.spin_area)
            self.param_layout.addStretch()

        else:
            lbl_no_param = QLabel("✓ OGC Standard")
            lbl_no_param.setStyleSheet(
                "background-color: rgba(16, 185, 129, 0.12); "
                "color: #10b981; "
                "border: 1px solid rgba(16, 185, 129, 0.28); "
                "border-radius: 9px; "
                "padding: 1px 7px; "
                "font-size: 10px; "
                "font-weight: 600;"
            )
            self.param_layout.addWidget(lbl_no_param)
            self.param_layout.addStretch()

    def get_configured_rule(self) -> ConfiguredRule:
        rule_code = self.combo_rule.currentData()
        info = TopologyEngine.RULES.get(rule_code)
        name = info.name if info else rule_code
        params = {}

        if rule_code in (TopologyRuleCode.POINT_DUPLICATES, TopologyRuleCode.LINE_DANGLES, TopologyRuleCode.LINE_DUPLICATE_NODES):
            if hasattr(self, "spin_tol"):
                params["tolerance"] = self.spin_tol.value()
        elif rule_code == TopologyRuleCode.LINE_SPIKES:
            if hasattr(self, "spin_angle"):
                params["max_angle"] = self.spin_angle.value()
        elif rule_code == TopologyRuleCode.LINE_SHORT_SEGMENTS:
            if hasattr(self, "spin_len"):
                params["min_length"] = self.spin_len.value()
        elif rule_code == TopologyRuleCode.POLYGON_OVERLAPS:
            if hasattr(self, "spin_area"):
                params["min_area"] = self.spin_area.value()
        elif rule_code == TopologyRuleCode.POLYGON_SLIVERS:
            if hasattr(self, "spin_area"):
                params["min_area"] = self.spin_area.value()
            if hasattr(self, "spin_thin"):
                params["thinness"] = self.spin_thin.value()
        elif rule_code == TopologyRuleCode.POLYGON_GAPS:
            if hasattr(self, "spin_area"):
                params["max_gap_area"] = self.spin_area.value()

        return ConfiguredRule(
            code=rule_code,
            name=name,
            params=params,
            description=info.description if info else ""
        )

    def apply_theme(self, theme_name: str = None):
        theme_name = theme_name or ThemeManager._current_theme or "light"
        tokens = ThemeManager.get_tokens(theme_name)
        is_dark = ThemeManager.is_dark(theme_name)
        card_bg = "#252526" if is_dark else "#f8fafc"
        input_bg = "#1e1e1e" if is_dark else "#ffffff"
        border = "#3c3c3c" if is_dark else "#e2e8f0"
        border_hover = "#505050" if is_dark else "#cbd5e1"
        text = tokens.get("text", "#1e293b")
        text_muted = tokens.get("text_muted", "#64748b")
        accent = tokens.get("accent", "#0284c7")

        del_bg = "rgba(239, 68, 68, 0.10)" if is_dark else "rgba(239, 68, 68, 0.06)"
        del_border = "rgba(239, 68, 68, 0.25)" if is_dark else "rgba(239, 68, 68, 0.18)"
        del_hover_bg = "rgba(239, 68, 68, 0.22)" if is_dark else "rgba(239, 68, 68, 0.16)"
        del_hover_border = "rgba(239, 68, 68, 0.45)" if is_dark else "rgba(239, 68, 68, 0.35)"

        self.setStyleSheet(f"""
            QFrame#TopologyRuleRowWidget {{
                background-color: {card_bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
            QFrame#TopologyRuleRowWidget:hover {{
                border-color: {border_hover};
            }}
            QLabel {{
                color: {text_muted};
                font-size: 11px;
                font-weight: 500;
            }}
            QComboBox, QDoubleSpinBox {{
                background-color: {input_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
                min-height: 24px;
            }}
            QComboBox:focus, QDoubleSpinBox:focus {{
                border-color: {accent};
            }}
            QPushButton#btn_rule_delete {{
                background-color: {del_bg};
                border: 1px solid {del_border};
                border-radius: 4px;
            }}
            QPushButton#btn_rule_delete:hover {{
                background-color: {del_hover_bg};
                border-color: {del_hover_border};
            }}
        """)
        self.btn_delete.setIcon(get_lucide_icon("trash-2", theme_name=theme_name, color="#ef4444", size=16))
        self.btn_delete.setIconSize(QSize(16, 16))


class TopologyCheckerWidget(QWidget):
    """
    Core Topology Inspection & Remediation Widget.
    Embeddable in a QDockWidget, QDialog, or standalone view.
    Fully integrated with Chisel Editor's design language, theme engine, and vector icons.
    """

    close_requested = pyqtSignal()
    ERROR_LAYER_ID = "topology_errors"

    def __init__(
        self,
        gdf: Optional[gpd.GeoDataFrame] = None,
        layer_name: str = "Spatial Layer",
        map_panel=None,
        on_layer_updated: Optional[Callable[[gpd.GeoDataFrame], None]] = None,
        layer_id: str = None,
        parent=None
    ):
        super().__init__(parent)
        self.gdf = gdf.copy() if (gdf is not None and not gdf.empty) else None
        self.layer_name = layer_name or "Spatial Layer"
        self.map_panel = map_panel
        self.on_layer_updated = on_layer_updated
        self.layer_id = layer_id

        self.report: Optional[TopologyReport] = None
        self.worker: Optional[TopologyWorker] = None
        self.configured_rules: List[ConfiguredRule] = []
        self.rule_rows: List[TopologyRuleRowWidget] = []
        self._current_theme_name: Optional[str] = None

        if self.gdf is not None:
            from core.spatial_ops import SpatialOps
            self.geom_type = SpatialOps.get_layer_geometry_type(self.gdf)
            self.crs_str, self.linear_unit, self.area_unit, self.is_degree = get_layer_crs_unit_info(self.gdf)
        else:
            self.geom_type = "Geometry"
            self.crs_str = "EPSG:4326"
            self.linear_unit = "meters (m)"
            self.area_unit = "square meters (m²)"
            self.is_degree = False

        self._setup_ui()
        self.apply_theme()
        if self.gdf is not None:
            self._populate_default_rules()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(6, 6, 6, 6)

        # =========================================================
        # Splitter: Top is Rules Pane, Bottom is Defects Pane
        # =========================================================
        self.splitter = QSplitter(Qt.Orientation.Vertical)

        # --- Top Section: Configured Rules Pane ---
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(2, 2, 2, 2)
        top_layout.setSpacing(6)

        # 1. Rules Section Header Bar
        rules_header = QHBoxLayout()
        rules_header.setContentsMargins(2, 0, 2, 2)
        rules_header.setSpacing(8)

        self.lbl_rules_header = QLabel("TOPOLOGY RULES")
        self.lbl_rules_header.setFont(QFont(self.font().family(), pointSize=9, weight=QFont.Weight.Bold))
        rules_header.addWidget(self.lbl_rules_header)

        self.lbl_rules_badge = QLabel("0 Active")
        rules_header.addWidget(self.lbl_rules_badge)

        rules_header.addStretch()

        self.btn_add_rule = QPushButton("+ Add Rule")
        self.btn_add_rule.setFixedHeight(24)
        self.btn_add_rule.setToolTip("Add a new topology validation rule")
        self.btn_add_rule.clicked.connect(self._on_add_new_rule_row)
        rules_header.addWidget(self.btn_add_rule)

        top_layout.addLayout(rules_header)

        # 2. Rules Scroll Area holding inline rule cards
        self.rules_scroll = QScrollArea()
        self.rules_scroll.setWidgetResizable(True)
        self.rules_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.rules_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.rules_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.rules_scroll.setMinimumHeight(110)

        self.rules_container = QWidget()
        self.rules_rows_layout = QVBoxLayout(self.rules_container)
        self.rules_rows_layout.setContentsMargins(4, 4, 4, 4)
        self.rules_rows_layout.setSpacing(6)

        self.lbl_no_rules = QLabel("No active rules.\nClick '+ Add Rule' above to configure validation rules.")
        self.lbl_no_rules.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_no_rules.hide()
        self.rules_rows_layout.addWidget(self.lbl_no_rules)

        self.rules_rows_layout.addStretch()
        self.rules_scroll.setWidget(self.rules_container)
        top_layout.addWidget(self.rules_scroll)

        # 3. Action Toolbar below Rules list: Run Check & Progress Bar
        rules_actions = QHBoxLayout()
        rules_actions.setContentsMargins(2, 4, 2, 2)
        rules_actions.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(16)
        self.progress_bar.setMinimumWidth(80)
        self.progress_bar.hide()
        rules_actions.addWidget(self.progress_bar)

        rules_actions.addStretch()

        self.btn_run = QPushButton("Run Topology Check")
        self.btn_run.setFixedHeight(30)
        self.btn_run.setToolTip("Execute configured topology rules against active layer")
        self.btn_run.clicked.connect(self._on_run_checks)
        rules_actions.addWidget(self.btn_run)

        top_layout.addLayout(rules_actions)
        top_layout.addSpacing(2)
        self.splitter.addWidget(top_widget)

        # --- Bottom Section: Defects Table & Remediation ---
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(2, 4, 2, 2)
        bottom_layout.setSpacing(6)

        # Defects Section Header Bar
        defects_header = QHBoxLayout()
        defects_header.setContentsMargins(2, 0, 2, 2)
        defects_header.setSpacing(8)

        self.lbl_defects_header = QLabel("DEFECTS & REMEDIATION")
        self.lbl_defects_header.setFont(QFont(self.font().family(), pointSize=9, weight=QFont.Weight.Bold))
        defects_header.addWidget(self.lbl_defects_header)

        self.lbl_defects_badge = QLabel("Ready to audit")
        defects_header.addWidget(self.lbl_defects_badge)
        defects_header.addStretch()

        bottom_layout.addLayout(defects_header)

        # Retain headless references for backward-compatibility & automated map updates
        self.lbl_status = QLabel("<b>Status:</b> Ready. Click 'Run Topology Check' to audit layer.")
        self.chk_show_map = QCheckBox("Map Overlay")
        self.chk_show_map.setChecked(True)
        self.filter_combo = QComboBox()
        self.search_input = QLineEdit()
        self.lbl_filter_count = QLabel("")

        # Errors Table (3 columns: Rule Violated, Feature ID(s), Description)
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["RULE VIOLATED", "FEATURE ID(S)", "DESCRIPTION"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.table.itemDoubleClicked.connect(self._on_zoom_to_selected)
        bottom_layout.addWidget(self.table)

        # Bottom Remediation Action Bar
        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 4, 0, 0)
        actions_row.setSpacing(6)

        self.btn_zoom = QPushButton("Zoom to Defect")
        self.btn_zoom.setFixedHeight(28)
        self.btn_zoom.setToolTip("Pan and zoom Leaflet map to selected error geometry")
        self.btn_zoom.clicked.connect(self._on_zoom_to_selected)
        self.btn_zoom.setEnabled(False)
        actions_row.addWidget(self.btn_zoom)

        self.btn_fix_single = QPushButton("Fix Selected")
        self.btn_fix_single.setFixedHeight(28)
        self.btn_fix_single.setToolTip("Auto-repair the selected topology defect")
        self.btn_fix_single.clicked.connect(self._on_fix_selected)
        self.btn_fix_single.setEnabled(False)
        actions_row.addWidget(self.btn_fix_single)

        self.btn_fix_all = QPushButton("Fix All")
        self.btn_fix_all.setFixedHeight(28)
        self.btn_fix_all.setToolTip("Batch repair all auto-fixable topology errors in the layer")
        self.btn_fix_all.clicked.connect(self._on_fix_all)
        self.btn_fix_all.setEnabled(False)
        actions_row.addWidget(self.btn_fix_all)

        self.btn_export = QPushButton("Export GeoJSON...")
        self.btn_export.setFixedHeight(28)
        self.btn_export.setToolTip("Export error geometries and attributes to a GeoJSON file")
        self.btn_export.clicked.connect(self._on_export_errors)
        self.btn_export.setEnabled(False)
        actions_row.addWidget(self.btn_export)

        actions_row.addStretch()
        bottom_layout.addLayout(actions_row)

        self.splitter.addWidget(bottom_widget)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 5)
        main_layout.addWidget(self.splitter)

    # -------------------------------------------------------------
    # Theme Engine Integration
    # -------------------------------------------------------------

    def apply_theme(self, theme_name: str = None):
        """Applies dynamic theme styling matching the active Chisel Editor theme palette."""
        theme_name = theme_name or ThemeManager._current_theme or "light"
        tokens = ThemeManager.get_tokens(theme_name)
        is_dark = ThemeManager.is_dark(theme_name)
        self._current_theme_name = theme_name

        bg = tokens.get("panel_bg", "#ffffff")
        toolbar_bg = tokens.get("toolbar_bg", "#f8fafc")
        text = tokens.get("text", "#1e293b")
        text_muted = tokens.get("text_muted", "#64748b")
        border = tokens.get("border", "#e2e8f0")
        hover = tokens.get("hover", "rgba(128,128,128,0.18)")
        active = tokens.get("active", "rgba(128,128,128,0.30)")
        accent = tokens.get("accent", "#0284c7")
        grid = tokens.get("grid_line", "#e2e8f0")
        alt_bg = tokens.get("hover", "#f8fafc") if not is_dark else tokens.get("active", "#252526")

        self.setStyleSheet(f"""
            QWidget {{ background-color: {bg}; color: {text}; }}
            QLabel {{ color: {text}; }}
            QSplitter::handle {{ background-color: {border}; }}
            QSplitter::handle:hover {{ background-color: {accent}; }}
        """)

        self.lbl_rules_header.setStyleSheet(f"color: {text_muted}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;")
        self.lbl_defects_header.setStyleSheet(f"color: {text_muted}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;")
        self.lbl_no_rules.setStyleSheet(f"color: {text_muted}; font-size: 11px; padding: 16px;")

        self.lbl_rules_badge.setStyleSheet(
            f"background-color: rgba(2, 132, 199, 0.12); "
            f"color: {accent}; "
            f"border: 1px solid rgba(2, 132, 199, 0.28); "
            f"border-radius: 9px; "
            f"padding: 1px 7px; "
            f"font-size: 10px; "
            f"font-weight: 600;"
        )

        self.btn_add_rule.setIcon(get_lucide_icon("plus", theme_name=theme_name, color=accent, size=13))
        self.btn_add_rule.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {accent};
                border: 1px solid {accent};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover:enabled {{
                background-color: {accent};
                color: #ffffff;
            }}
            QPushButton:pressed:enabled {{
                background-color: {active};
            }}
            QPushButton:disabled {{
                color: {text_muted};
                border-color: {border};
            }}
        """)

        table_style = f"""
            QTableWidget {{
                background-color: {bg};
                color: {text};
                gridline-color: {grid};
                border: 1px solid {border};
                border-radius: 6px;
                selection-background-color: {accent};
                selection-color: #ffffff;
                font-size: 12px;
            }}
            QTableWidget::item {{
                padding: 4px 6px;
                border: none;
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
                border: none;
                border-bottom: 1px solid {border};
                border-right: 1px solid {border};
                padding: 5px 8px;
                font-weight: 700;
                font-size: 11px;
                letter-spacing: 0.3px;
            }}
        """
        self.table.setStyleSheet(table_style)

        self.rules_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
            QScrollBar:vertical {{
                background: {toolbar_bg};
                width: 8px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {border};
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {accent};
            }}
        """)

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
                border-color: {border};
            }}
        """

        for btn in (self.btn_zoom, self.btn_fix_single, self.btn_export):
            btn.setStyleSheet(btn_neutral_style)

        self.btn_zoom.setIcon(get_lucide_icon("focus", theme_name=theme_name, size=14))
        self.btn_fix_single.setIcon(get_lucide_icon("wrench", theme_name=theme_name, size=14))
        self.btn_export.setIcon(get_lucide_icon("file-down", theme_name=theme_name, size=14))

        for row in self.rule_rows:
            row.apply_theme(theme_name)

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
                background-color: {toolbar_bg};
                color: {text_muted};
                border-color: {border};
            }}
        """)

        # Re-apply badge style based on current report
        if not self.report:
            self._update_defects_badge("ready")
        elif self.report.total_errors == 0:
            self._update_defects_badge("clean")
        else:
            fix_count = sum(1 for e in self.report.errors if e.can_fix)
            self._update_defects_badge("errors", count=self.report.total_errors, fix_count=fix_count)

    def _update_defects_badge(self, state: str, count: int = 0, fix_count: int = 0):
        """Updates the status pill badge in the Defects section."""
        if state == "ready":
            self.lbl_defects_badge.setText("Ready to audit")
            self.lbl_defects_badge.setStyleSheet(
                "background-color: rgba(100, 116, 139, 0.12); "
                "color: #64748b; "
                "border: 1px solid rgba(100, 116, 139, 0.28); "
                "border-radius: 9px; "
                "padding: 1px 8px; "
                "font-size: 10px; "
                "font-weight: 600;"
            )
        elif state == "running":
            self.lbl_defects_badge.setText("Auditing layer...")
            self.lbl_defects_badge.setStyleSheet(
                "background-color: rgba(2, 132, 199, 0.12); "
                "color: #0284c7; "
                "border: 1px solid rgba(2, 132, 199, 0.28); "
                "border-radius: 9px; "
                "padding: 1px 8px; "
                "font-size: 10px; "
                "font-weight: 600;"
            )
        elif state == "clean":
            self.lbl_defects_badge.setText("✓ Clean (0 Defects)")
            self.lbl_defects_badge.setStyleSheet(
                "background-color: rgba(16, 185, 129, 0.12); "
                "color: #10b981; "
                "border: 1px solid rgba(16, 185, 129, 0.28); "
                "border-radius: 9px; "
                "padding: 1px 8px; "
                "font-size: 10px; "
                "font-weight: 600;"
            )
        elif state == "errors":
            fix_str = f" ({fix_count} Fixable)" if fix_count > 0 else ""
            self.lbl_defects_badge.setText(f"⚠️ {count:,} Defects{fix_str}")
            self.lbl_defects_badge.setStyleSheet(
                "background-color: rgba(239, 68, 68, 0.12); "
                "color: #ef4444; "
                "border: 1px solid rgba(239, 68, 68, 0.28); "
                "border-radius: 9px; "
                "padding: 1px 8px; "
                "font-size: 10px; "
                "font-weight: 600;"
            )
        elif state == "failed":
            self.lbl_defects_badge.setText("Audit Error")
            self.lbl_defects_badge.setStyleSheet(
                "background-color: rgba(239, 68, 68, 0.12); "
                "color: #ef4444; "
                "border: 1px solid rgba(239, 68, 68, 0.28); "
                "border-radius: 9px; "
                "padding: 1px 8px; "
                "font-size: 10px; "
                "font-weight: 600;"
            )

    # -------------------------------------------------------------
    # Rule Configuration Handlers (Dynamic Inline Cards)
    # -------------------------------------------------------------

    def _populate_default_rules(self):
        """Populates the rules list with a single initial default rule for the layer."""
        while self.rule_rows:
            row = self.rule_rows.pop()
            self.rules_rows_layout.removeWidget(row)
            row.deleteLater()

        if self.gdf is None:
            self._update_rules_badge_and_button()
            return

        applicable = TopologyEngine.get_applicable_rules(self.geom_type)
        if not applicable:
            self._update_rules_badge_and_button()
            return

        default_rules = TopologyEngine.get_default_configured_rules(self.geom_type, self.is_degree)
        initial_rule = default_rules[0] if default_rules else ConfiguredRule(code=applicable[0].code, name=applicable[0].name)

        row_widget = TopologyRuleRowWidget(
            applicable_rules=applicable,
            initial_rule_code=initial_rule.code,
            initial_params=initial_rule.params,
            linear_unit=self.linear_unit,
            area_unit=self.area_unit,
            is_degree=self.is_degree,
            parent=self.rules_container
        )
        row_widget.delete_requested.connect(self._on_rule_row_deleted)
        row_widget.changed.connect(self._update_rules_badge_and_button)
        if self._current_theme_name:
            row_widget.apply_theme(self._current_theme_name)
        self.rule_rows.append(row_widget)
        stretch_idx = max(0, self.rules_rows_layout.count() - 1)
        self.rules_rows_layout.insertWidget(stretch_idx, row_widget)

        self._update_rules_badge_and_button()

    def _on_add_new_rule_row(self):
        """Adds a new rule row card with an unused or applicable rule."""
        if self.gdf is None:
            ToastNotification.show_toast(self, "Please select an active spatial layer first.", "warning")
            return

        applicable = TopologyEngine.get_applicable_rules(self.geom_type)
        if not applicable:
            ToastNotification.show_toast(self, f"No topology rules available for {self.geom_type}.", "warning")
            return

        used_codes = {row.combo_rule.currentData() for row in self.rule_rows}
        new_rule = next((r for r in applicable if r.code not in used_codes), None)
        if new_rule is None:
            new_rule = applicable[0]

        defaults = TopologyEngine.get_default_configured_rules(self.geom_type, self.is_degree)
        init_params = next((r.params for r in defaults if r.code == new_rule.code), {})

        row_widget = TopologyRuleRowWidget(
            applicable_rules=applicable,
            initial_rule_code=new_rule.code,
            initial_params=init_params,
            linear_unit=self.linear_unit,
            area_unit=self.area_unit,
            is_degree=self.is_degree,
            parent=self.rules_container
        )
        row_widget.delete_requested.connect(self._on_rule_row_deleted)
        row_widget.changed.connect(self._update_rules_badge_and_button)
        if self._current_theme_name:
            row_widget.apply_theme(self._current_theme_name)

        self.rule_rows.append(row_widget)
        stretch_idx = max(0, self.rules_rows_layout.count() - 1)
        self.rules_rows_layout.insertWidget(stretch_idx, row_widget)
        self._update_rules_badge_and_button()

    def _on_rule_row_deleted(self, row_widget: TopologyRuleRowWidget):
        """Removes a rule row card and updates UI counts."""
        if row_widget in self.rule_rows:
            self.rule_rows.remove(row_widget)
            self.rules_rows_layout.removeWidget(row_widget)
            row_widget.deleteLater()
            self._update_rules_badge_and_button()

    def _update_rules_badge_and_button(self):
        """Refreshes rule badge count and enables/disables Run button."""
        cnt = len(self.rule_rows)
        self.lbl_rules_badge.setText(f"{cnt} Active")
        btn_label = f"Run Topology Check ({cnt})" if cnt > 0 else "Run Topology Check"
        self.btn_run.setText(btn_label)
        self.btn_run.setEnabled(cnt > 0 and self.gdf is not None)

        if cnt == 0:
            self.lbl_no_rules.show()
        else:
            self.lbl_no_rules.hide()

    # -------------------------------------------------------------
    # Layer Refresh & Execution
    # -------------------------------------------------------------

    def update_layer(
        self,
        gdf: Optional[gpd.GeoDataFrame],
        layer_name: str,
        on_layer_updated: Optional[Callable[[gpd.GeoDataFrame], None]] = None,
        layer_id: str = None
    ):
        """Refreshes widget state when active layer or tab changes."""
        self.gdf = gdf.copy() if (gdf is not None and not gdf.empty) else None
        self.layer_name = layer_name or "Spatial Layer"
        if on_layer_updated:
            self.on_layer_updated = on_layer_updated
        if layer_id:
            self.layer_id = layer_id

        if self.gdf is not None:
            from core.spatial_ops import SpatialOps
            self.geom_type = SpatialOps.get_layer_geometry_type(self.gdf)
            self.crs_str, self.linear_unit, self.area_unit, self.is_degree = get_layer_crs_unit_info(self.gdf)
            self.lbl_status.setText("<b>Status:</b> Ready. Click 'Run Topology Check' to audit layer.")
        else:
            self.geom_type = "Geometry"
            self.crs_str = "EPSG:4326"
            self.linear_unit = "meters (m)"
            self.area_unit = "square meters (m²)"
            self.is_degree = False
            self.lbl_status.setText("<b>Status:</b> Select an active spatial layer to validate.")

        self.report = None
        self.table.setRowCount(0)
        self.btn_zoom.setEnabled(False)
        self.btn_fix_single.setEnabled(False)
        self.btn_fix_all.setEnabled(False)
        self.btn_export.setEnabled(False)
        self._update_defects_badge("ready")

        if self.map_panel:
            try:
                self.map_panel.remove_vector_layer(self.ERROR_LAYER_ID)
                self.map_panel.clear_topology_highlight()
            except Exception:
                pass

        self._populate_default_rules()

    def _on_run_checks(self):
        configured_rules = [row.get_configured_rule() for row in self.rule_rows]
        if not configured_rules:
            ToastNotification.show_toast(self, "Please configure at least one rule first.", "warning")
            return
        if self.gdf is None or self.gdf.empty:
            ToastNotification.show_toast(self, "No features in layer to check.", "warning")
            return

        self.btn_run.setEnabled(False)
        self.progress_bar.show()
        self._update_defects_badge("running")
        self.lbl_status.setText("<i>Auditing layer topology according to configured rules...</i>")

        self.worker = TopologyWorker(
            "check",
            self.gdf,
            configured_rules=configured_rules
        )
        self.worker.check_finished.connect(self._on_check_finished)
        self.worker.start()

    def _on_check_finished(self, report: Optional[TopologyReport], error_msg: str):
        self.progress_bar.hide()
        self.btn_run.setEnabled(True)

        if error_msg:
            self._update_defects_badge("failed")
            self.lbl_status.setText(f"<span style='color:#ef4444;'>Error: {error_msg}</span>")
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
                self.lbl_status.setText("✅ <b>No topology errors found! Layer satisfies all rules.</b>")
                self._update_defects_badge("clean")
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

            self._update_defects_badge("errors", count=report.total_errors, fix_count=fix_count)

            summary_str = f"⚠️ <b>Found {report.total_errors:,} issue(s)</b> ({err_count} errors, {warn_count} warnings)"
            self.lbl_status.setText(summary_str)

            self.btn_fix_all.setText(f"Fix All ({fix_count:,})" if fix_count > 0 else "Fix All")
            self.btn_fix_all.setEnabled(fix_count > 0)
            self.btn_fix_single.setEnabled(False)
            self.btn_export.setEnabled(True)
            self.btn_zoom.setEnabled(False)

            display_errors = report.errors[:2000]
            self.table.setRowCount(len(display_errors))
            for row_idx, err in enumerate(display_errors):
                item_rule = QTableWidgetItem(err.rule_name)
                item_rule.setData(Qt.ItemDataRole.UserRole, err.id)

                if err.severity == "error":
                    item_rule.setForeground(QBrush(QColor("#ef4444")))
                    item_rule.setFont(QFont(self.font().family(), weight=QFont.Weight.Bold))
                elif err.severity == "warning":
                    item_rule.setForeground(QBrush(QColor("#f59e0b")))
                    item_rule.setFont(QFont(self.font().family(), weight=QFont.Weight.Bold))
                else:
                    item_rule.setForeground(QBrush(QColor("#3b82f6")))

                item_feat = QTableWidgetItem(", ".join(map(str, err.feature_ids)) if err.feature_ids else "-")
                item_desc = QTableWidgetItem(err.description)

                for itm in (item_rule, item_feat, item_desc):
                    itm.setFlags(itm.flags() & ~Qt.ItemFlag.ItemIsEditable)

                self.table.setItem(row_idx, 0, item_rule)
                self.table.setItem(row_idx, 1, item_feat)
                self.table.setItem(row_idx, 2, item_desc)

            self.table.selectRow(0)
        finally:
            self.table.setUpdatesEnabled(True)

    def _apply_error_filter(self):
        pass

    def _get_selected_error(self) -> Optional[TopologyError]:
        if not self.report or not self.report.errors:
            return None
        selected_rows = self.table.selectedIndexes()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        item = self.table.item(row, 0)
        if not item:
            return None
        err_id = item.data(Qt.ItemDataRole.UserRole)
        if err_id is None:
            err_id = row
        if 0 <= err_id < len(self.report.errors):
            return self.report.errors[err_id]
        return None

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

    def on_close(self):
        """Cleans up map highlights and temporary vector layers."""
        if self.map_panel:
            try:
                self.map_panel.clear_topology_highlight()
                self.map_panel.remove_vector_layer(self.ERROR_LAYER_ID)
            except Exception as e:
                print(f"Failed to cleanup topology highlights: {e}")

    def _handle_close(self):
        self.on_close()
        self.close_requested.emit()

    def _on_table_selection_changed(self):
        err = self._get_selected_error()
        if err is not None:
            self.btn_fix_single.setEnabled(err.can_fix)
            self.btn_zoom.setEnabled(True)
            self._zoom_to_error_geometry(err.geometry, err.id, err=err)
        else:
            self.btn_fix_single.setEnabled(False)
            self.btn_zoom.setEnabled(False)

    def _on_zoom_to_selected(self):
        err = self._get_selected_error()
        if err is not None:
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
        err = self._get_selected_error()
        if err is None:
            return

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


class TopologyDockWidget(QDockWidget):
    """
    Native PyQt6 Dock Widget for the Topology Inspection & Remediation Engine.
    Can be docked to Right, Left, Bottom, or Top dock widget areas,
    floated as an independent window, or tabbed with other docks.
    """

    def __init__(self, parent=None, map_panel=None):
        super().__init__("Topology Engine", parent)
        self.setObjectName("TopologyDockWidget")
        self.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.setMinimumWidth(360)

        self.checker_widget = TopologyCheckerWidget(
            gdf=None,
            layer_name="No Layer Selected",
            map_panel=map_panel,
            parent=self
        )
        self.setWidget(self.checker_widget)
        self.checker_widget.close_requested.connect(self.close)

    def update_layer(
        self,
        gdf: Optional[gpd.GeoDataFrame],
        layer_name: str,
        on_layer_updated: Optional[Callable[[gpd.GeoDataFrame], None]] = None,
        layer_id: str = None
    ):
        clean_name = layer_name or "Spatial Layer"
        self.setWindowTitle(f"Topology Engine — {clean_name}")
        self.checker_widget.update_layer(gdf, layer_name, on_layer_updated, layer_id)

    def apply_theme(self, theme_name: str = None):
        tokens = ThemeManager.get_tokens(theme_name)
        bg = tokens.get("panel_bg", "#ffffff")
        toolbar_bg = tokens.get("toolbar_bg", "#f8fafc")
        text = tokens.get("text", "#1e293b")
        text_muted = tokens.get("text_muted", "#64748b")
        border = tokens.get("border", "#e2e8f0")
        accent = tokens.get("accent", "#0284c7")
        hover = tokens.get("hover", "rgba(128,128,128,0.18)")

        self.setStyleSheet(f"""
            QDockWidget {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
            }}
            QDockWidget::title {{
                background-color: {toolbar_bg};
                color: {text};
                font-weight: 600;
                font-size: 12px;
                padding: 6px 10px;
                border-bottom: 1px solid {border};
                text-align: left;
            }}
            QDockWidget::close-button, QDockWidget::float-button {{
                border: none;
                background: transparent;
                padding: 2px;
                border-radius: 3px;
                icon-size: 14px;
            }}
            QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
                background-color: {hover};
            }}
        """)
        self.checker_widget.apply_theme(theme_name)

    def closeEvent(self, event):
        if hasattr(self, "checker_widget") and self.checker_widget:
            self.checker_widget.on_close()
        super().closeEvent(event)


class TopologyCheckerDialog(QDialog):
    """
    Backwards-compatible dialog wrapper embedding TopologyCheckerWidget.
    Preserves existing code paths expecting a QDialog.
    """

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
        self.layer_name = layer_name or "Spatial Layer"
        self.setWindowTitle(f"Topology Checker & Validator — {self.layer_name}")
        self.resize(1060, 740)
        self.setMinimumSize(880, 580)
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowMinMaxButtonsHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.checker_widget = TopologyCheckerWidget(
            gdf=gdf,
            layer_name=self.layer_name,
            map_panel=map_panel,
            on_layer_updated=on_layer_updated,
            layer_id=layer_id,
            parent=self
        )
        layout.addWidget(self.checker_widget)
        self.checker_widget.close_requested.connect(self.close)

    def update_layer(self, gdf, layer_name, on_layer_updated=None, layer_id=None):
        self.setWindowTitle(f"Topology Checker & Validator — {layer_name or 'Spatial Layer'}")
        self.checker_widget.update_layer(gdf, layer_name, on_layer_updated, layer_id)

    def apply_theme(self, theme_name: str = None):
        tokens = ThemeManager.get_tokens(theme_name)
        bg = tokens.get("panel_bg", "#ffffff")
        text = tokens.get("text", "#1e293b")
        self.setStyleSheet(f"QDialog {{ background-color: {bg}; color: {text}; }}")
        self.checker_widget.apply_theme(theme_name)

    def closeEvent(self, event):
        if hasattr(self, "checker_widget") and self.checker_widget:
            self.checker_widget.on_close()
        super().closeEvent(event)
