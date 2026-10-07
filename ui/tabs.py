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
    service_add_requested = pyqtSignal()
    wms_deleted = pyqtSignal(str)

    def __init__(self, parent=None, map_panel: MapPreviewPanel = None):
        super().__init__(parent)
        self.layer_id = f"layer_{id(self)}"
        self.current_file = None
        self.is_dirty = False
        self.file_type = "Plain Text"
        self._is_loading = False
        self.is_spatial = False
        self._is_large_dataset = False
        self._current_gdf = None
        self._custom_map_panel = map_panel

        self._init_ui()

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Main Splitter (Left: Code Editor, Right: Spatial / Markdown)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(2)

        # Code Editor on the left
        self.text_editor = MonacoEditor()
        self.splitter.addWidget(self.text_editor)

        # Right Container: Spatial (0) or Markdown (1)
        self.right_stack = QStackedWidget()

        # Spatial View: Vertical splitter with Map on top and Attribute Table docked at bottom
        self.spatial_splitter = QSplitter(Qt.Orientation.Vertical)
        self.spatial_splitter.setHandleWidth(3)

        self.map_panel = self._custom_map_panel if self._custom_map_panel is not None else MapPreviewPanel()
        self.table_panel = AttributeTableWidget()

        self.spatial_splitter.addWidget(self.map_panel)
        self.spatial_splitter.addWidget(self.table_panel)
        self.table_panel.hide()

        self.markdown_panel = MarkdownPreviewPanel()

        self.right_stack.addWidget(self.spatial_splitter)  # index 0: Spatial
        self.right_stack.addWidget(self.markdown_panel)    # index 1: Markdown

        self.splitter.addWidget(self.right_stack)
        self.splitter.setSizes([500, 650])

        self.layout.addWidget(self.splitter)

        # Default mode for new/unopened tab: Pure code view (preview hidden)
        self.set_view_mode("code")

        # Bi-directional sync & interactions
        self.table_panel.feature_selected.connect(lambda idx: self.map_panel.highlight_feature(idx, self.layer_id) if self.map_panel else None)
        self.table_panel.close_requested.connect(self.toggle_table)
        self.table_panel.data_modified.connect(self._on_table_data_modified)

        if self._custom_map_panel is None:
            self.map_panel.feature_clicked.connect(self.table_panel.select_feature)
            self.map_panel.table_toggle_requested.connect(self.toggle_table)
            self.map_panel.feature_deleted.connect(self._on_feature_deleted)
            self.map_panel.feature_added.connect(self._on_feature_added)
            self.map_panel.service_add_requested.connect(self.service_add_requested.emit)
            self.map_panel.wms_deleted.connect(self.wms_deleted.emit)

        # Auto-refresh timer for code edits
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(600)
        self.preview_timer.timeout.connect(self._refresh_preview)
        self.text_editor.textChanged.connect(self._on_text_changed)

    def attach_map_panel(self, panel: MapPreviewPanel):
        self.map_panel = panel
        if self.spatial_splitter.count() > 0:
            if self.spatial_splitter.widget(0) != panel:
                self.spatial_splitter.insertWidget(0, panel)
        else:
            self.spatial_splitter.addWidget(panel)
        panel.show()

    def set_spatial_data(self, gdf: gpd.GeoDataFrame, raw_geojson: str = None):
        self.is_spatial = True
        self.file_type = "GeoJSON"
        self._current_gdf = gdf
        feat_count = len(gdf) if gdf is not None else 0
        self._is_large_dataset = (feat_count > 3000)

        self._is_loading = True

        # 1. Load Virtual Attribute Table immediately (Instant 0ms overhead)
        if gdf is not None and not gdf.empty:
            self.table_panel.load_data(gdf)

        # 2. Render Map via Leaflet
        layer_name = os.path.basename(self.current_file) if self.current_file else "Mekansal Katman"
        geom_type = SpatialOps.get_layer_geometry_type(gdf)

        if self._is_large_dataset:
            # QGIS-style initial LOD overview: sample or simplified view for ultra-fast initial render
            init_gdf = SpatialOps.get_overview_lod(gdf, max_features=3000)
            render_geojson = SpatialOps.to_geojson_str(init_gdf)
        else:
            if raw_geojson is None and gdf is not None and not gdf.empty:
                raw_geojson = SpatialOps.to_geojson_str(gdf)
            render_geojson = raw_geojson

        if render_geojson and self.map_panel:
            self.map_panel.set_vector_layer(
                layer_id=self.layer_id,
                name=layer_name,
                geojson_str=render_geojson,
                is_active=True,
                geom_type=geom_type,
                fit_bounds=True
            )

        # 3. Monaco Editor: Avoid freezing WebEngine by buffering large text
        if raw_geojson is None and render_geojson:
            raw_geojson = render_geojson
        if raw_geojson:
            if len(raw_geojson) < 500_000 and not self._is_large_dataset:
                self.text_editor.setPlainText(raw_geojson)
            else:
                count = len(gdf) if gdf is not None else 0
                size_mb = (len(raw_geojson) if raw_geojson else 0) / (1024 * 1024)
                preview = (
                    f"// Mekansal Veri: {count:,} adet geometrik özellik yüklendi ({size_mb:.1f} MB).\n"
                    f"// QGIS Modu: R-Tree indeksleme ve dinamik LOD devrededir.\n\n"
                    f"{raw_geojson[:1200] if raw_geojson else ''}\n\n... [Büyük veri performansı için sınırlandırıldı] ..."
                )
                self.text_editor.setPlainText(preview)
            self.text_editor.setLanguage("GeoJSON")

        self._is_loading = False

        # Open directly in full map view (user can open attribute table on demand)
        self.set_view_mode("map")
        if self.map_panel:
            QTimer.singleShot(120, lambda: self.map_panel.fit_bounds(self.layer_id) if self.map_panel else None)
        self.spatial_data_ready.emit(gdf)

    def _update_viewport_data(self, minx: float, miny: float, maxx: float, maxy: float, zoom: int):
        if not self._is_large_dataset or self._current_gdf is None or self._current_gdf.empty:
            return

        if hasattr(self, "_viewport_worker") and self._viewport_worker is not None and self._viewport_worker.isRunning():
            try:
                self._viewport_worker.finished.disconnect()
            except Exception:
                pass

        layer_name = os.path.basename(self.current_file) if self.current_file else "Mekansal Katman"
        geom_type = SpatialOps.get_layer_geometry_type(self._current_gdf)

        from core.workers import ViewportQueryWorker
        self._viewport_worker = ViewportQueryWorker(
            self.layer_id, layer_name, self._current_gdf, geom_type,
            minx, miny, maxx, maxy, zoom
        )
        self._viewport_worker.finished.connect(self._on_viewport_query_finished)
        self._viewport_worker.start()

    def _on_viewport_query_finished(self, layer_id: str, layer_name: str, raw_geojson: str, geom_type: str):
        if self.map_panel and layer_id == self.layer_id:
            self.map_panel.update_vector_layer_data(
                layer_id=layer_id,
                name=layer_name,
                geojson_str=raw_geojson,
                geom_type=geom_type
            )

    def update_spatial_gdf(self, gdf: gpd.GeoDataFrame, fit_bounds: bool = False):
        self._current_gdf = gdf
        self._is_large_dataset = (len(gdf) > 3000) if gdf is not None else False
        geojson_str = SpatialOps.to_geojson_str(gdf, indent=2)
        self._is_loading = True
        if not self._is_large_dataset and len(geojson_str) < 500_000:
            self.text_editor.setPlainText(geojson_str)
        self.table_panel.load_data(gdf)
        layer_name = os.path.basename(self.current_file) if self.current_file else "Mekansal Katman"
        geom_type = SpatialOps.get_layer_geometry_type(gdf)
        if self.map_panel:
            if self._is_large_dataset:
                init_gdf = SpatialOps.get_overview_lod(gdf, max_features=3000)
                render_str = SpatialOps.to_geojson_str(init_gdf)
            else:
                render_str = geojson_str
            self.map_panel.set_vector_layer(
                layer_id=self.layer_id,
                name=layer_name,
                geojson_str=render_str,
                is_active=True,
                geom_type=geom_type,
                fit_bounds=fit_bounds
            )
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

            # Check geometry compatibility with existing layer
            if self._current_gdf is not None and not self._current_gdf.empty:
                layer_type = SpatialOps.get_layer_geometry_type(self._current_gdf)
                new_type = shapely_geom.geom_type.lower()
                is_compat = True
                if layer_type == "point" and "point" not in new_type:
                    is_compat = False
                elif layer_type == "line" and "line" not in new_type:
                    is_compat = False
                elif layer_type == "polygon" and "poly" not in new_type:
                    is_compat = False

                if not is_compat:
                    type_tr = {"point": "Nokta", "line": "Çizgi", "polygon": "Çokgen"}.get(layer_type, layer_type)
                    new_tr = "Nokta" if "point" in new_type else ("Çizgi" if "line" in new_type else ("Çokgen" if "poly" in new_type else shapely_geom.geom_type))
                    ToastNotification.show_toast(self.window(), f"⚠️ Uyumsuz geometri! Katman [{type_tr}] tipindedir, [{new_tr}] eklenemez.", "warning")
                    return

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
            geom_name = "Nokta" if "point" in shapely_geom.geom_type.lower() else ("Çizgi" if "line" in shapely_geom.geom_type.lower() else ("Çokgen" if "poly" in shapely_geom.geom_type.lower() else shapely_geom.geom_type))
            ToastNotification.show_toast(self.window(), f"➕ Yeni {geom_name} eklendi! (Toplam: {len(new_gdf)})", "success")
        except Exception as e:
            print(f"Error adding feature: {e}")
            from ui.toast import ToastNotification
            ToastNotification.show_toast(self.window(), f"Geometri ekleme hatası: {e}", "error")

    def _on_quick_fit(self):
        if self.map_panel:
            self.map_panel.fit_bounds()

    def is_table_visible(self) -> bool:
        return (
            self.is_spatial
            and self.table_panel.isVisible()
            and self.right_stack.isVisible()
            and self.right_stack.currentIndex() == 0
        )

    def _adjust_spatial_splitter_sizes(self):
        total_h = self.spatial_splitter.height()
        if total_h < 300:
            total_h = self.height() if self.height() > 300 else 700
        table_h = getattr(self, "_last_table_height", None) or max(220, int(total_h * 0.35))
        map_h = max(200, total_h - table_h)
        self.spatial_splitter.setSizes([map_h, table_h])

    def set_view_mode(self, mode: str):
        if mode == "code":
            self.text_editor.show()
            self.right_stack.hide()

        elif mode == "code_map":
            self.text_editor.show()
            self.right_stack.setCurrentIndex(0)
            self.right_stack.show()
            self.map_panel.show()
            self.table_panel.hide()
            self.map_panel.set_table_active(False)
            self.splitter.setSizes([500, 650])

        elif mode == "table_map":
            self.text_editor.hide()
            self.right_stack.setCurrentIndex(0)
            self.right_stack.show()
            self.map_panel.show()
            self.table_panel.show()
            self.map_panel.set_table_active(True)
            self._adjust_spatial_splitter_sizes()

        elif mode == "map":
            self.text_editor.hide()
            self.right_stack.setCurrentIndex(0)
            self.right_stack.show()
            self.map_panel.show()
            self.table_panel.hide()
            self.map_panel.set_table_active(False)

        elif mode == "table":
            self.text_editor.hide()
            self.right_stack.setCurrentIndex(0)
            self.right_stack.show()
            self.map_panel.hide()
            self.table_panel.show()
            self.map_panel.set_table_active(True)

        elif mode == "markdown":
            self.text_editor.show()
            self.right_stack.setCurrentIndex(1)
            self.right_stack.show()
            self.splitter.setSizes([500, 500])

    def toggle_table(self):
        """Toggles bottom attribute table under the map."""
        if not self.is_spatial:
            return

        # If spatial container is not visible, switch to spatial view with table
        if not self.right_stack.isVisible() or self.right_stack.currentIndex() != 0:
            self.set_view_mode("table_map")
            self.state_changed.emit()
            return

        if self.table_panel.isVisible():
            sizes = self.spatial_splitter.sizes()
            if len(sizes) > 1 and sizes[1] > 50:
                self._last_table_height = sizes[1]
            self.table_panel.hide()
            self.map_panel.show()
            self.map_panel.set_table_active(False)
        else:
            self.table_panel.show()
            self.map_panel.show()
            self.map_panel.set_table_active(True)
            self._adjust_spatial_splitter_sizes()

        self.state_changed.emit()

    def toggle_spatial_left_view(self):
        """Toggle bottom attribute table under the map."""
        self.toggle_table()

    @property
    def left_stack(self):
        """Compatibility property for legacy callers referencing left_stack."""
        class _CompatStack:
            def __init__(self, tab):
                self._tab = tab
            def isVisible(self):
                return self._tab.is_table_visible()
            def currentIndex(self):
                return 1 if self._tab.is_table_visible() else 0
        return _CompatStack(self)

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
                try:
                    gdf = SpatialOps.parse_geojson_str(content)
                    self._current_gdf = gdf
                    self.table_panel.load_data(gdf)
                    layer_name = os.path.basename(self.current_file) if self.current_file else "Mekansal Katman"
                    geom_type = SpatialOps.get_layer_geometry_type(gdf)
                    if self.map_panel:
                        self.map_panel.set_vector_layer(
                            layer_id=self.layer_id,
                            name=layer_name,
                            geojson_str=content,
                            is_active=True,
                            geom_type=geom_type,
                            fit_bounds=False
                        )
                except Exception:
                    pass
        elif self.file_type == "Markdown" and self.right_stack.isVisible():
            self.markdown_panel.render_content(content)

    def get_title(self):
        title = os.path.basename(self.current_file) if self.current_file else "Untitled"
        if self.is_dirty:
            title += " *"
        return title