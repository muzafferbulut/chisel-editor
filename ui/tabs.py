import os
import uuid
from typing import Optional
import geopandas as gpd
from PyQt6.QtWidgets import QWidget, QSplitter, QStackedWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from ui.editor import MonacoEditor
from ui.preview_panels import MapPreviewPanel, MarkdownPreviewPanel
from ui.attribute_table import AttributeTableWidget
from ui.spreadsheet_editor import SpreadsheetEditorWidget
from ui.document_editor import WordDocumentEditorWidget
from ui.pdf_viewer import PdfViewerWidget
from core.spatial_ops import SpatialOps


class EditorTab(QWidget):
    state_changed = pyqtSignal()
    spatial_data_ready = pyqtSignal(object)
    load_sample_requested = pyqtSignal()
    service_add_requested = pyqtSignal()
    wms_deleted = pyqtSignal(str)

    def __init__(self, parent=None, map_panel: MapPreviewPanel = None):
        super().__init__(parent)
        self._default_layer_id = f"layer_{id(self)}"
        self._current_file = None
        self.is_dirty = False
        self.file_type = "Plain Text"
        self._is_loading = False
        self.is_spatial = False
        self._is_large_dataset = False
        self._fallback_gdf = None
        self.spatial_layers = {}
        self.active_layer_id = None
        self._custom_map_panel = map_panel

        self._init_ui()

    @property
    def layer_id(self) -> str:
        return self.active_layer_id or getattr(self, "_default_layer_id", f"layer_{id(self)}")

    @layer_id.setter
    def layer_id(self, val: str):
        self._default_layer_id = val

    @property
    def _current_gdf(self) -> Optional[gpd.GeoDataFrame]:
        if self.active_layer_id and self.active_layer_id in self.spatial_layers:
            return self.spatial_layers[self.active_layer_id].get("gdf")
        return getattr(self, "_fallback_gdf", None)

    @_current_gdf.setter
    def _current_gdf(self, val):
        if self.active_layer_id and self.active_layer_id in self.spatial_layers:
            self.spatial_layers[self.active_layer_id]["gdf"] = val
        self._fallback_gdf = val

    @property
    def current_file(self) -> Optional[str]:
        if self.is_spatial:
            if self.active_layer_id and self.active_layer_id in self.spatial_layers:
                return self.spatial_layers[self.active_layer_id].get("file_path")
            return getattr(self, "_current_file", None)
        return getattr(self, "_current_file", None)

    @current_file.setter
    def current_file(self, val: Optional[str]):
        self._current_file = val
        if self.is_spatial and self.active_layer_id and self.active_layer_id in self.spatial_layers:
            self.spatial_layers[self.active_layer_id]["file_path"] = val
            self.spatial_layers[self.active_layer_id]["name"] = os.path.basename(val) if val else "Katman"

    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Root Stack for switching between document paradigms:
        # Index 0: Code / Markdown Splitter
        # Index 1: Pure Spatial GIS Splitter (Map + Attribute Table)
        # Index 2: Spreadsheet Editor (.xlsx, .xls)
        # Index 3: Word Document Editor (.docx)
        # Index 4: PDF Viewer (.pdf)
        self.main_stack = QStackedWidget()

        # 0. Code Editor & Markdown Container
        self.code_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.code_splitter.setHandleWidth(2)
        self.text_editor = MonacoEditor()
        self.code_splitter.addWidget(self.text_editor)

        self.right_stack = QStackedWidget()
        self.markdown_panel = MarkdownPreviewPanel()
        self.right_stack.addWidget(self.markdown_panel)
        self.code_splitter.addWidget(self.right_stack)
        self.right_stack.hide()

        # Backward compatibility alias
        self.splitter = self.code_splitter

        # 1. Spatial GIS View (Vertical Splitter: Map top, Attribute Table bottom)
        self.spatial_splitter = QSplitter(Qt.Orientation.Vertical)
        self.spatial_splitter.setHandleWidth(3)

        self.map_panel = self._custom_map_panel if self._custom_map_panel is not None else MapPreviewPanel()
        self.table_panel = AttributeTableWidget()

        self.spatial_splitter.addWidget(self.map_panel)
        self.spatial_splitter.addWidget(self.table_panel)
        self.table_panel.hide()

        # 2. Native Interactive Spreadsheet Editor
        self.spreadsheet_editor = SpreadsheetEditorWidget()
        self.spreadsheet_editor.content_changed.connect(self._mark_dirty)

        # 3. Native Rich Text Word Document Editor
        self.document_editor = WordDocumentEditorWidget()
        self.document_editor.content_changed.connect(self._mark_dirty)

        # 4. Native High-Performance PDF Reader
        self.pdf_viewer = PdfViewerWidget()

        # Add all document environments to main stack
        self.main_stack.addWidget(self.code_splitter)       # 0
        self.main_stack.addWidget(self.spatial_splitter)    # 1
        self.main_stack.addWidget(self.spreadsheet_editor)  # 2
        self.main_stack.addWidget(self.document_editor)     # 3
        self.main_stack.addWidget(self.pdf_viewer)          # 4

        self.layout.addWidget(self.main_stack)

        # Default mode for initial blank tab: Code view
        self.set_view_mode("code")

        # Bi-directional sync & interactions for spatial GIS
        self.table_panel.features_selected.connect(self._on_table_features_selected)
        self.table_panel.delete_requested.connect(self._on_features_deleted)
        self.table_panel.close_requested.connect(self.toggle_table)
        self.table_panel.data_modified.connect(self._on_table_data_modified)
        self.table_panel.zoom_to_selected_requested.connect(self._on_table_zoom_to_selected)
        self.table_panel.layer_changed.connect(self.set_active_layer)

        if self._custom_map_panel is None:
            self.map_panel.feature_clicked.connect(self.table_panel.select_feature)
            self.map_panel.selection_changed.connect(self.table_panel.select_features)
            self.map_panel.selection_deleted.connect(self._on_features_deleted)
            self.map_panel.table_toggle_requested.connect(self.toggle_table)
            self.map_panel.feature_deleted.connect(self._on_feature_deleted)
            self.map_panel.feature_added.connect(self._on_feature_added)
            self.map_panel.feature_updated.connect(lambda idx, geom: self._on_feature_updated(idx, geom, from_map=True))
            self.map_panel.service_add_requested.connect(self.service_add_requested.emit)
            self.map_panel.wms_deleted.connect(self.wms_deleted.emit)

        # Auto-refresh timer for code edits (Markdown, etc.)
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

    def _mark_dirty(self):
        if not self.is_dirty:
            self.is_dirty = True
            self.state_changed.emit()

    def has_file(self, file_path: str) -> bool:
        if not file_path:
            return False
        norm = os.path.abspath(file_path).lower()
        if self.is_spatial:
            for info in self.spatial_layers.values():
                if info.get("file_path") and os.path.abspath(info["file_path"]).lower() == norm:
                    return True
            return False
        return bool(self.current_file and os.path.abspath(self.current_file).lower() == norm)

    def set_active_layer_by_file(self, file_path: str) -> bool:
        if not file_path:
            return False
        norm = os.path.abspath(file_path).lower()
        for lid, info in self.spatial_layers.items():
            if info.get("file_path") and os.path.abspath(info["file_path"]).lower() == norm:
                self.set_active_layer(lid)
                return True
        return False

    def add_spatial_layer(self, file_path: str, gdf: gpd.GeoDataFrame, raw_geojson: str = None, custom_name: str = None, is_wfs: bool = False) -> str:
        self.is_spatial = True
        self.file_type = "Mekansal Katman"

        if file_path:
            norm = os.path.abspath(file_path).lower()
            for lid, info in self.spatial_layers.items():
                if info.get("file_path") and os.path.abspath(info["file_path"]).lower() == norm:
                    self.set_active_layer(lid)
                    return lid

        layer_name = custom_name or (os.path.basename(file_path) if file_path else f"Katman {len(self.spatial_layers) + 1}")
        layer_id = f"layer_{uuid.uuid4().hex[:8]}"

        feat_count = len(gdf) if gdf is not None else 0
        is_large = (feat_count > 3000)
        geom_type = SpatialOps.get_layer_geometry_type(gdf)

        self.spatial_layers[layer_id] = {
            "id": layer_id,
            "name": layer_name,
            "file_path": file_path,
            "gdf": gdf,
            "geom_type": geom_type,
            "is_large": is_large,
            "is_dirty": False,
            "is_wfs": is_wfs,
        }

        self._is_loading = True
        if is_large:
            init_gdf = SpatialOps.get_overview_lod(gdf, max_features=3000)
            render_geojson = SpatialOps.to_geojson_str(init_gdf)
        else:
            if raw_geojson is None and gdf is not None and not gdf.empty:
                raw_geojson = SpatialOps.to_geojson_str(gdf)
            render_geojson = raw_geojson

        if render_geojson and self.map_panel:
            self.map_panel.set_vector_layer(
                layer_id=layer_id,
                name=layer_name,
                geojson_str=render_geojson,
                is_active=True,
                geom_type=geom_type,
                fit_bounds=True,
                is_wfs=is_wfs
            )

        self._is_loading = False
        self.set_active_layer(layer_id)
        self.set_view_mode("map")
        self.spatial_data_ready.emit(gdf)
        return layer_id

    def set_active_layer(self, layer_id: str):
        if layer_id not in self.spatial_layers:
            return
        self.active_layer_id = layer_id
        info = self.spatial_layers[layer_id]
        self._current_file = info.get("file_path")
        self._is_large_dataset = info.get("is_large", False)

        if info.get("gdf") is not None and not info["gdf"].empty:
            self.table_panel.load_data(info["gdf"], layer_name=info["name"], layer_id=layer_id)
        else:
            self.table_panel.load_data(None)

        self._sync_table_layers()

        if self.map_panel:
            self.map_panel.set_active_vector_layer(layer_id, info.get("geom_type", "any"))

        self.state_changed.emit()

    def remove_spatial_layer(self, layer_id: str):
        if layer_id in self.spatial_layers:
            del self.spatial_layers[layer_id]
            if self.map_panel:
                self.map_panel.remove_vector_layer(layer_id)

            if self.active_layer_id == layer_id:
                if self.spatial_layers:
                    first_id = next(iter(self.spatial_layers))
                    self.set_active_layer(first_id)
                else:
                    self.active_layer_id = None
                    self._current_file = None
                    self.table_panel.load_data(None)

            self._sync_table_layers()
            self.state_changed.emit()

    def _sync_table_layers(self):
        layers = [(info["id"], info["name"], info["geom_type"]) for info in self.spatial_layers.values()]
        self.table_panel.update_layer_list(layers, self.active_layer_id)

    def set_spatial_data(self, gdf: gpd.GeoDataFrame, raw_geojson: str = None):
        self.add_spatial_layer(self.current_file, gdf, raw_geojson=raw_geojson)

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
        if self.active_layer_id and self.active_layer_id in self.spatial_layers:
            self.spatial_layers[self.active_layer_id]["gdf"] = gdf
            self.spatial_layers[self.active_layer_id]["is_dirty"] = True
            layer_name = self.spatial_layers[self.active_layer_id]["name"]
        else:
            self._fallback_gdf = gdf
            layer_name = os.path.basename(self.current_file) if self.current_file else "Mekansal Katman"

        self._is_large_dataset = (len(gdf) > 3000) if gdf is not None else False
        self._is_loading = True
        self.table_panel.load_data(gdf, layer_name=layer_name, layer_id=self.layer_id)

        geom_type = SpatialOps.get_layer_geometry_type(gdf)
        if self.map_panel:
            if self._is_large_dataset:
                init_gdf = SpatialOps.get_overview_lod(gdf, max_features=3000)
                render_str = SpatialOps.to_geojson_str(init_gdf)
            else:
                render_str = SpatialOps.to_geojson_str(gdf, indent=0)
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
        self._on_features_deleted([index])

    def _on_features_deleted(self, indices: list):
        if self._current_gdf is None or self._current_gdf.empty or not indices:
            return
        try:
            valid_indices = [i for i in indices if 0 <= i < len(self._current_gdf)]
            if not valid_indices:
                return

            if len(valid_indices) > 10:
                from PyQt6.QtWidgets import QMessageBox
                reply = QMessageBox.question(
                    self, "Geometrileri Sil",
                    f"{len(valid_indices):,} adet seçili geometriyi silmek istediğinize emin misiniz?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return

            drop_indices = [self._current_gdf.index[i] for i in valid_indices]
            new_gdf = self._current_gdf.drop(index=drop_indices).reset_index(drop=True)
            self.update_spatial_gdf(new_gdf)
            if self.map_panel:
                self.map_panel.clear_selection(self.layer_id)
            from ui.toast import ToastNotification
            count = len(drop_indices)
            msg = f"🗑️ {count:,} adet geometri silindi. (Kalan: {len(new_gdf):,})" if count > 1 else f"🗑️ Geometri silindi. (Kalan: {len(new_gdf):,})"
            ToastNotification.show_toast(self.window(), msg, "info")
        except Exception as e:
            print(f"Error deleting features: {e}")

    def _on_table_features_selected(self, indices: list):
        if self.map_panel:
            self.map_panel.set_selected_features(indices, self.layer_id)

    def _on_table_zoom_to_selected(self):
        if self.map_panel and self.layer_id:
            self.map_panel.zoom_to_selected(self.layer_id)

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

    def _on_feature_updated(self, index: int, geometry_json_str: str, from_map: bool = False):
        if self._current_gdf is None or self._current_gdf.empty:
            return
        if not (0 <= index < len(self._current_gdf)):
            return

        try:
            import json
            from shapely.geometry import shape
            from ui.toast import ToastNotification

            data = json.loads(geometry_json_str)
            geom_data = data.get("geometry", data) if isinstance(data, dict) else data
            shapely_geom = shape(geom_data)
            if not shapely_geom.is_valid:
                from shapely.validation import make_valid
                shapely_geom = make_valid(shapely_geom)

            target_crs = self._current_gdf.crs
            if target_crs is not None:
                crs_str = str(target_crs).upper()
                if crs_str not in ("EPSG:4326", "WGS 84", "OGC:CRS84", "4326"):
                    try:
                        import pyproj
                        from shapely.ops import transform
                        project = pyproj.Transformer.from_crs("EPSG:4326", target_crs, always_xy=True).transform
                        shapely_geom = transform(project, shapely_geom)
                    except Exception as ex:
                        print(f"Reprojection error in feature update: {ex}")

            geom_col = getattr(self._current_gdf, 'geometry', None).name if hasattr(self._current_gdf, 'geometry') else 'geometry'
            self._current_gdf.at[self._current_gdf.index[index], geom_col] = shapely_geom
            if self.active_layer_id and self.active_layer_id in self.spatial_layers:
                self.spatial_layers[self.active_layer_id]["is_dirty"] = True

            self.is_dirty = True
            self.state_changed.emit()

            self.table_panel.source_model.set_data(self._current_gdf)
            self.table_panel._update_stats_label()

            if not from_map and self.map_panel:
                render_str = SpatialOps.to_geojson_str(self._current_gdf, indent=0)
                self.map_panel.update_vector_layer_data(
                    layer_id=self.layer_id,
                    name=self.spatial_layers.get(self.active_layer_id, {}).get("name", "Mekansal Katman"),
                    geojson_str=render_str,
                    geom_type=SpatialOps.get_layer_geometry_type(self._current_gdf)
                )

            ToastNotification.show_toast(self.window(), f"✏️ Geometri güncellendi (Kayıt #{index + 1})", "info")
        except Exception as e:
            print(f"Error in _on_feature_updated: {e}")
            from ui.toast import ToastNotification
            ToastNotification.show_toast(self.window(), f"Geometri güncelleme hatası: {e}", "error")

    def _on_quick_fit(self):
        if self.map_panel:
            self.map_panel.fit_bounds()

    def is_table_visible(self) -> bool:
        return (
            self.is_spatial
            and self.main_stack.currentWidget() == self.spatial_splitter
            and self.table_panel.isVisible()
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
            if self.is_spatial:
                self.set_view_mode("map")
                return
            self.main_stack.setCurrentIndex(0)
            self.text_editor.show()
            self.right_stack.hide()

        elif mode == "code_map":
            if self.is_spatial:
                self.set_view_mode("map")
                return
            self.main_stack.setCurrentIndex(0)
            self.text_editor.show()
            self.right_stack.setCurrentIndex(0)
            self.right_stack.show()
            self.code_splitter.setSizes([500, 650])

        elif mode == "table_map":
            self.main_stack.setCurrentIndex(1)
            self.map_panel.show()
            self.table_panel.show()
            self.map_panel.set_table_active(True)
            self._adjust_spatial_splitter_sizes()

        elif mode == "map":
            self.main_stack.setCurrentIndex(1)
            self.map_panel.show()
            self.table_panel.hide()
            self.map_panel.set_table_active(False)

        elif mode == "table":
            self.main_stack.setCurrentIndex(1)
            self.map_panel.hide()
            self.table_panel.show()
            self.map_panel.set_table_active(True)

        elif mode == "markdown":
            self.main_stack.setCurrentIndex(0)
            self.text_editor.show()
            self.right_stack.setCurrentIndex(0)
            self.right_stack.show()
            self.code_splitter.setSizes([500, 500])

        elif mode == "spreadsheet":
            self.main_stack.setCurrentIndex(2)

        elif mode == "word":
            self.main_stack.setCurrentIndex(3)

        elif mode == "pdf":
            self.main_stack.setCurrentIndex(4)

    def toggle_table(self):
        """Toggles bottom attribute table under the map in spatial view."""
        if not self.is_spatial:
            return

        if self.main_stack.currentWidget() != self.spatial_splitter:
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

    def configure_for_file_type(self, file_type: str, is_spatial: bool, content: object = "", gdf: object = None):
        self.file_type = file_type
        self.is_spatial = is_spatial

        if file_type == "Spreadsheet":
            self.set_view_mode("spreadsheet")
            if isinstance(content, dict) and content:
                self.spreadsheet_editor.load_data(content, self.current_file)
            elif self.current_file and os.path.exists(self.current_file):
                self.spreadsheet_editor.load_file(self.current_file)
        elif file_type == "Word":
            self.set_view_mode("word")
            if isinstance(content, dict) and content:
                self.document_editor.load_data(content, self.current_file)
            elif self.current_file and os.path.exists(self.current_file):
                self.document_editor.load_file(self.current_file)
        elif file_type == "PDF":
            self.set_view_mode("pdf")
            if self.current_file and os.path.exists(self.current_file):
                self.pdf_viewer.load_file(self.current_file)
        elif is_spatial:
            if gdf is None and isinstance(content, str) and content.strip():
                try:
                    gdf = SpatialOps.parse_geojson_str(content)
                except Exception:
                    gdf = None
            self.set_spatial_data(gdf)
        elif file_type == "Markdown":
            self.set_view_mode("markdown")
            text = content if isinstance(content, str) else ""
            self.markdown_panel.render_content(text)
            self.text_editor.setPlainText(text)
        else:
            self.set_view_mode("code")
            text = content if isinstance(content, str) else ""
            self.text_editor.setPlainText(text)
            self.text_editor.setLanguage(file_type)

    def _on_text_changed(self):
        if self._is_loading:
            return

        self.preview_timer.start()
        if not self.is_dirty:
            self.is_dirty = True
            self.state_changed.emit()

    def _refresh_preview(self):
        if self.file_type == "Markdown" and self.right_stack.isVisible():
            content = self.text_editor.toPlainText()
            self.markdown_panel.render_content(content)

    def apply_theme(self, theme_name: str = None):
        """Propagates theme change to all embedded document and code editors."""
        if hasattr(self, "text_editor") and self.text_editor:
            self.text_editor.setTheme(theme_name)
        if hasattr(self, "spreadsheet_editor") and self.spreadsheet_editor:
            self.spreadsheet_editor.apply_theme(theme_name)
        if hasattr(self, "document_editor") and self.document_editor:
            self.document_editor.apply_theme(theme_name)
        if hasattr(self, "pdf_viewer") and self.pdf_viewer:
            self.pdf_viewer.apply_theme(theme_name)
        if hasattr(self, "table_panel") and self.table_panel:
            self.table_panel.apply_theme(theme_name)
        if hasattr(self, "map_panel") and self.map_panel:
            self.map_panel.set_theme_tiles(theme_name)

    def get_format_badge(self) -> str:
        """Returns clean indicator for tab file type."""
        if self.is_spatial:
            return "🗺️ GIS"
        elif self.file_type == "Spreadsheet":
            return "📊 Tablo"
        elif self.file_type == "Word":
            return "📄 Word"
        elif self.file_type == "PDF":
            return "📑 PDF"
        elif self.file_type == "Markdown":
            return "📖 Markdown"
        return "📝 Kod"

    def get_title(self):
        if self.is_spatial:
            count = len(self.spatial_layers)
            if count == 0:
                title = "🗺️ Harita"
            elif count == 1:
                single = next(iter(self.spatial_layers.values()))
                title = f"🗺️ {single['name']}"
            else:
                title = f"🗺️ Harita ({count} Katman)"
            if any(l.get("is_dirty", False) for l in self.spatial_layers.values()) or self.is_dirty:
                title += " *"
            return title

        title = os.path.basename(self.current_file) if self.current_file else "Untitled"
        if self.is_dirty:
            title += " *"
        return title