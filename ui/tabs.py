import os
import geopandas as gpd
from PyQt6.QtWidgets import (
    QWidget, QSplitter, QStackedWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QButtonGroup, QLabel
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from ui.editor import MonacoEditor
from ui.preview_panels import MapPreviewPanel, MarkdownPreviewPanel
from ui.attribute_table import AttributeTableWidget
from core.spatial_ops import SpatialOps


class EditorTab(QWidget):
    state_changed = pyqtSignal()
    spatial_data_ready = pyqtSignal(object)  # Emits GeoDataFrame when spatial data is loaded

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.is_dirty = False
        self.file_type = "Plain Text"
        self._is_loading = False
        self.is_spatial = False
        self._current_gdf = None

        self._init_ui()

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Top Control Bar (View Switcher + Quick Actions)
        self.control_bar = QWidget()
        self.control_bar.setObjectName("tabToolbar")
        bar_layout = QHBoxLayout(self.control_bar)
        bar_layout.setContentsMargins(8, 4, 8, 4)
        bar_layout.setSpacing(6)

        self.view_btn_group = QButtonGroup(self)
        self.view_btn_group.setExclusive(True)

        self.btn_mode_code = QPushButton("📝 Code")
        self.btn_mode_code.setCheckable(True)
        self.btn_mode_code.clicked.connect(lambda: self.set_view_mode("code"))
        self.view_btn_group.addButton(self.btn_mode_code)
        bar_layout.addWidget(self.btn_mode_code)

        self.btn_mode_code_map = QPushButton("⚡ Code + Map")
        self.btn_mode_code_map.setCheckable(True)
        self.btn_mode_code_map.clicked.connect(lambda: self.set_view_mode("code_map"))
        self.view_btn_group.addButton(self.btn_mode_code_map)
        bar_layout.addWidget(self.btn_mode_code_map)

        self.btn_mode_table_map = QPushButton("📊 Table + Map")
        self.btn_mode_table_map.setCheckable(True)
        self.btn_mode_table_map.clicked.connect(lambda: self.set_view_mode("table_map"))
        self.view_btn_group.addButton(self.btn_mode_table_map)
        bar_layout.addWidget(self.btn_mode_table_map)

        self.btn_mode_map = QPushButton("🗺️ Map")
        self.btn_mode_map.setCheckable(True)
        self.btn_mode_map.clicked.connect(lambda: self.set_view_mode("map"))
        self.view_btn_group.addButton(self.btn_mode_map)
        bar_layout.addWidget(self.btn_mode_map)

        self.btn_mode_table = QPushButton("📋 Table")
        self.btn_mode_table.setCheckable(True)
        self.btn_mode_table.clicked.connect(lambda: self.set_view_mode("table"))
        self.view_btn_group.addButton(self.btn_mode_table)
        bar_layout.addWidget(self.btn_mode_table)

        bar_layout.addStretch()

        # Quick action buttons
        self.btn_quick_fit = QPushButton("🎯 Fit Bounds")
        self.btn_quick_fit.clicked.connect(self._on_quick_fit)
        bar_layout.addWidget(self.btn_quick_fit)

        self.layout.addWidget(self.control_bar)
        self.control_bar.hide()  # Initially hidden until file loaded

        # Main Splitter Layout
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Container (holds Editor or Attribute Table)
        self.left_stack = QStackedWidget()
        self.text_editor = MonacoEditor()
        self.table_panel = AttributeTableWidget()

        self.left_stack.addWidget(self.text_editor)   # Index 0
        self.left_stack.addWidget(self.table_panel)   # Index 1

        # Right Container (holds Map Preview or Markdown Preview)
        self.right_stack = QStackedWidget()
        self.map_panel = MapPreviewPanel()
        self.markdown_panel = MarkdownPreviewPanel()

        self.right_stack.addWidget(self.map_panel)       # Index 0
        self.right_stack.addWidget(self.markdown_panel)  # Index 1
        self.right_stack.hide()

        self.splitter.addWidget(self.left_stack)
        self.splitter.addWidget(self.right_stack)
        self.splitter.setSizes([500, 600])

        self.layout.addWidget(self.splitter)

        # Bi-directional Map <-> Table synchronization
        self.table_panel.feature_selected.connect(self.map_panel.highlight_feature)
        self.map_panel.feature_clicked.connect(self.table_panel.select_feature)
        self.table_panel.data_modified.connect(self._on_table_data_modified)

        # Auto-refresh timer for code edits
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(600)
        self.preview_timer.timeout.connect(self._refresh_preview)
        self.text_editor.textChanged.connect(self._on_text_changed)

    def set_spatial_data(self, gdf: gpd.GeoDataFrame, raw_geojson: str = None):
        """
        Initializes spatial data across editor, table, and map panels.
        """
        self.is_spatial = True
        self.file_type = "GeoJSON"
        self._current_gdf = gdf

        if raw_geojson is None and gdf is not None and not gdf.empty:
            raw_geojson = SpatialOps.to_geojson_str(gdf, indent=2)

        self._is_loading = True
        if raw_geojson:
            self.text_editor.setPlainText(raw_geojson)
            self.text_editor.setLanguage("GeoJSON")
            self.map_panel.render_content(raw_geojson)

        if gdf is not None and not gdf.empty:
            self.table_panel.load_data(gdf)
        self._is_loading = False

        self.control_bar.show()
        self.btn_mode_table_map.setChecked(True)
        self.set_view_mode("table_map")
        self.spatial_data_ready.emit(gdf)

    def update_spatial_gdf(self, gdf: gpd.GeoDataFrame):
        """
        Updates the active spatial GeoDataFrame and synchronizes UI panels.
        """
        self._current_gdf = gdf
        geojson_str = SpatialOps.to_geojson_str(gdf, indent=2)
        self._is_loading = True
        self.text_editor.setPlainText(geojson_str)
        self.table_panel.load_data(gdf)
        self.map_panel.render_content(geojson_str)
        self._is_loading = False
        self.is_dirty = True
        self.state_changed.emit()

    def _on_table_data_modified(self, new_gdf):
        self.update_spatial_gdf(new_gdf)

    def _on_quick_fit(self):
        if self.is_spatial and self.map_panel:
            self.map_panel.fit_bounds()

    def set_view_mode(self, mode: str):
        """
        Switches layout between:
        - 'code': Editor only
        - 'code_map': Split Editor + Map
        - 'table_map': Split Virtual Table + Map (Default GIS mode)
        - 'map': Fullscreen Map
        - 'table': Fullscreen Virtual Table
        - 'markdown': Split Editor + Markdown
        """
        if mode == "code":
            self.left_stack.setCurrentIndex(0)
            self.left_stack.show()
            self.right_stack.hide()
            self.btn_mode_code.setChecked(True)

        elif mode == "code_map":
            self.left_stack.setCurrentIndex(0)
            self.right_stack.setCurrentIndex(0)
            self.left_stack.show()
            self.right_stack.show()
            self.splitter.setSizes([450, 650])
            self.btn_mode_code_map.setChecked(True)

        elif mode == "table_map":
            self.left_stack.setCurrentIndex(1)
            self.right_stack.setCurrentIndex(0)
            self.left_stack.show()
            self.right_stack.show()
            self.splitter.setSizes([450, 650])
            self.btn_mode_table_map.setChecked(True)

        elif mode == "map":
            self.right_stack.setCurrentIndex(0)
            self.left_stack.hide()
            self.right_stack.show()
            self.btn_mode_map.setChecked(True)

        elif mode == "table":
            self.left_stack.setCurrentIndex(1)
            self.left_stack.show()
            self.right_stack.hide()
            self.btn_mode_table.setChecked(True)

        elif mode == "markdown":
            self.left_stack.setCurrentIndex(0)
            self.right_stack.setCurrentIndex(1)
            self.left_stack.show()
            self.right_stack.show()
            self.splitter.setSizes([500, 500])

    def configure_for_file_type(self, file_type: str, is_spatial: bool, content: str = ""):
        self.file_type = file_type
        self.is_spatial = is_spatial

        if is_spatial:
            try:
                gdf = SpatialOps.parse_geojson_str(content) if content.strip() else None
            except Exception:
                gdf = None
            self.set_spatial_data(gdf, content)
        elif file_type == "Markdown":
            self.control_bar.hide()
            self.right_stack.setCurrentIndex(1)
            self.left_stack.setCurrentIndex(0)
            self.left_stack.show()
            self.right_stack.show()
            self.markdown_panel.render_content(content)
        else:
            self.control_bar.hide()
            self.left_stack.setCurrentIndex(0)
            self.left_stack.show()
            self.right_stack.hide()

    def _on_text_changed(self):
        if self._is_loading:
            return

        self.preview_timer.start()
        if not self.is_dirty:
            self.is_dirty = True
            self.state_changed.emit()

    def _refresh_preview(self):
        content = self.text_editor.toPlainText()
        if self.is_spatial:
            if SpatialOps.is_valid_geojson_content(content):
                self.map_panel.render_content(content)
                try:
                    gdf = SpatialOps.parse_geojson_str(content)
                    self._current_gdf = gdf
                    self.table_panel.load_data(gdf)
                except Exception:
                    pass
        elif self.file_type == "Markdown" and self.right_stack.isVisible():
            self.markdown_panel.render_content(content)

    def get_title(self):
        title = os.path.basename(self.current_file) if self.current_file else "Untitled"
        if self.is_dirty:
            title += " *"
        return title