import os
import geopandas as gpd
from PyQt6.QtWidgets import QWidget, QSplitter, QStackedWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from ui.editor import MonacoEditor
from ui.preview_panels import MapPreviewPanel, MarkdownPreviewPanel
from ui.attribute_table import AttributeTableWidget
from core.spatial_ops import SpatialOps


class EditorTab(QWidget):
    state_changed = pyqtSignal()
    spatial_data_ready = pyqtSignal(object)
    load_sample_requested = pyqtSignal()

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

        # Splitter Layout (direct workspace, no intermediate toolbar)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(2)

        # Left Container: Monaco Editor (0) or Attribute Table (1)
        self.left_stack = QStackedWidget()
        self.text_editor = MonacoEditor()
        self.table_panel = AttributeTableWidget()

        self.left_stack.addWidget(self.text_editor)
        self.left_stack.addWidget(self.table_panel)

        # Right Container: Map (0) or Markdown (1)
        self.right_stack = QStackedWidget()
        self.map_panel = MapPreviewPanel()
        self.markdown_panel = MarkdownPreviewPanel()

        self.right_stack.addWidget(self.map_panel)
        self.right_stack.addWidget(self.markdown_panel)

        self.splitter.addWidget(self.left_stack)
        self.splitter.addWidget(self.right_stack)
        self.splitter.setSizes([500, 650])

        self.layout.addWidget(self.splitter)

        # Default mode for new/unopened tab: Pure code view (map hidden)
        self.set_view_mode("code")

        # Bi-directional sync
        self.table_panel.feature_selected.connect(self.map_panel.highlight_feature)
        self.map_panel.feature_clicked.connect(self.table_panel.select_feature)
        self.map_panel.table_toggle_requested.connect(self.toggle_table)
        self.table_panel.data_modified.connect(self._on_table_data_modified)
        self.map_panel.feature_deleted.connect(self._on_feature_deleted)
        self.map_panel.feature_added.connect(self._on_feature_added)

        # Auto-refresh timer for code edits
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(600)
        self.preview_timer.timeout.connect(self._refresh_preview)
        self.text_editor.textChanged.connect(self._on_text_changed)

    def set_spatial_data(self, gdf: gpd.GeoDataFrame, raw_geojson: str = None):
        self.is_spatial = True
        self.file_type = "GeoJSON"
        self._current_gdf = gdf

        if raw_geojson is None and gdf is not None and not gdf.empty:
            raw_geojson = SpatialOps.to_geojson_str(gdf)

        self._is_loading = True

        # 1. Load Virtual Attribute Table immediately (Instant 0ms overhead)
        if gdf is not None and not gdf.empty:
            self.table_panel.load_data(gdf)

        # 2. Render Map via Leaflet
        if raw_geojson:
            self.map_panel.render_content(raw_geojson)

        # 3. Monaco Editor: Avoid freezing WebEngine by buffering large text
        if raw_geojson:
            if len(raw_geojson) < 500_000:
                self.text_editor.setPlainText(raw_geojson)
            else:
                count = len(gdf) if gdf is not None else 0
                size_mb = len(raw_geojson) / (1024 * 1024)
                preview = (
                    f"// Mekansal Veri: {count:,} adet geometrik özellik yüklendi ({size_mb:.1f} MB).\n"
                    f"// Tablo ve Harita görünümünde maksimum hız ve performans devrededir.\n\n"
                    f"{raw_geojson[:1200]}\n\n... [Büyük veri performansı için metin editöründe sınırlandırıldı] ..."
                )
                self.text_editor.setPlainText(preview)
            self.text_editor.setLanguage("GeoJSON")

        self._is_loading = False

        # Open directly in full map view (user can open attribute table on demand)
        self.set_view_mode("map")
        self.spatial_data_ready.emit(gdf)

    def update_spatial_gdf(self, gdf: gpd.GeoDataFrame):
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

    def _on_feature_deleted(self, index: int):
        if self._current_gdf is None or self._current_gdf.empty:
            return
        if index < 0 or index >= len(self._current_gdf):
            return
        try:
            new_gdf = self._current_gdf.drop(self._current_gdf.index[index]).reset_index(drop=True)
            self.update_spatial_gdf(new_gdf)
            from ui.toast import ToastNotification
            ToastNotification.show_toast(self.window(), f"🗑️ Geometri silindi. (Kalan: {len(new_gdf)})", "info")
        except Exception as e:
            print(f"Error deleting feature: {e}")

    def _on_feature_added(self, feature_json_str: str):
        try:
            import json
            import pandas as pd
            from shapely.geometry import shape
            from ui.toast import ToastNotification

            feat_data = json.loads(feature_json_str)
            geom_data = feat_data.get("geometry", feat_data)
            shapely_geom = shape(geom_data)

            if not shapely_geom.is_valid:
                from shapely.validation import make_valid
                shapely_geom = make_valid(shapely_geom)

            if self._current_gdf is None or self._current_gdf.empty:
                new_gdf = gpd.GeoDataFrame([{"geometry": shapely_geom}], crs="EPSG:4326")
            else:
                target_crs = self._current_gdf.crs or "EPSG:4326"
                new_row = {col: None for col in self._current_gdf.columns if col != "geometry"}
                new_row["geometry"] = shapely_geom

                for id_name in ["id", "ID", "fid", "FID", "gid", "objectid"]:
                    if id_name in new_row:
                        new_row[id_name] = len(self._current_gdf) + 1

                row_gdf = gpd.GeoDataFrame([new_row], crs="EPSG:4326")
                if target_crs != "EPSG:4326" and target_crs is not None:
                    try:
                        row_gdf = row_gdf.to_crs(target_crs)
                    except Exception:
                        pass
                new_gdf = pd.concat([self._current_gdf, row_gdf], ignore_index=True)

            self.update_spatial_gdf(new_gdf)
            geom_name = "Nokta" if shapely_geom.geom_type == "Point" else ("Çokgen" if "Polygon" in shapely_geom.geom_type else shapely_geom.geom_type)
            ToastNotification.show_toast(self.window(), f"➕ Yeni {geom_name} eklendi! (Toplam: {len(new_gdf)})", "success")
        except Exception as e:
            print(f"Error adding feature: {e}")
            from ui.toast import ToastNotification
            ToastNotification.show_toast(self.window(), f"Geometri ekleme hatası: {e}", "error")

    def _on_quick_fit(self):
        if self.map_panel:
            self.map_panel.fit_bounds()

    def set_view_mode(self, mode: str):
        if mode == "code":
            self.left_stack.setCurrentIndex(0)
            self.left_stack.show()
            self.right_stack.hide()

        elif mode == "code_map":
            self.left_stack.setCurrentIndex(0)
            self.right_stack.setCurrentIndex(0)
            self.left_stack.show()
            self.right_stack.show()
            self.splitter.setSizes([500, 650])

        elif mode == "table_map":
            self.left_stack.setCurrentIndex(1)
            self.right_stack.setCurrentIndex(0)
            self.left_stack.show()
            self.right_stack.show()
            self.splitter.setSizes([500, 650])

        elif mode == "map":
            self.right_stack.setCurrentIndex(0)
            self.left_stack.hide()
            self.right_stack.show()

        elif mode == "table":
            self.left_stack.setCurrentIndex(1)
            self.left_stack.show()
            self.right_stack.hide()

        elif mode == "markdown":
            self.left_stack.setCurrentIndex(0)
            self.right_stack.setCurrentIndex(1)
            self.left_stack.show()
            self.right_stack.show()
            self.splitter.setSizes([500, 500])

    def toggle_table(self):
        """Toggles between full Map view and Table+Map split view."""
        if not self.is_spatial:
            return
        if self.left_stack.isVisible() and self.left_stack.currentIndex() == 1:
            self.set_view_mode("map")
        else:
            self.set_view_mode("table_map")
        self.state_changed.emit()

    def toggle_spatial_left_view(self):
        """Toggles between Code (0) and Attribute Table (1) on the left side of split view."""
        if not self.is_spatial:
            return
        curr = self.left_stack.currentIndex()
        if curr == 1:
            self.set_view_mode("code_map")
        else:
            self.set_view_mode("table_map")
        self.state_changed.emit()

    def configure_for_file_type(self, file_type: str, is_spatial: bool, content: str = "", gdf: object = None):
        self.file_type = file_type
        self.is_spatial = is_spatial

        if is_spatial:
            if gdf is None and content.strip():
                try:
                    gdf = SpatialOps.parse_geojson_str(content)
                except Exception:
                    gdf = None
            self.set_spatial_data(gdf, content)
        elif file_type == "Markdown":
            self.set_view_mode("markdown")
            self.markdown_panel.render_content(content)
        else:
            self.set_view_mode("code")
            self.text_editor.setPlainText(content)
            self.text_editor.setLanguage(file_type)

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