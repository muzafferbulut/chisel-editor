import os
import json
import markdown
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QApplication, QFileDialog
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import pyqtSignal, QObject, pyqtSlot, QUrl, QTimer
from core.theme import ThemeManager


class MapBridge(QObject):
    featureSelected = pyqtSignal(int)
    featureDeleted = pyqtSignal(int)
    featureAdded = pyqtSignal(str)
    tableToggleRequested = pyqtSignal()
    wmsDeleted = pyqtSignal(str)
    serviceAddRequested = pyqtSignal()
    activeLayerRequested = pyqtSignal(str)
    viewportChanged = pyqtSignal(float, float, float, float, int)
    selectionChanged = pyqtSignal(str)
    selectionDeleted = pyqtSignal(str)
    layerRemoved = pyqtSignal(str)
    featureUpdated = pyqtSignal(int, str)
    captureSnapshotRequested = pyqtSignal()

    @pyqtSlot(int)
    def onFeatureClicked(self, index):
        self.featureSelected.emit(index)

    @pyqtSlot(int)
    def onFeatureDeleted(self, index):
        self.featureDeleted.emit(index)

    @pyqtSlot(int, str)
    def onFeatureUpdated(self, index, featureJson):
        self.featureUpdated.emit(index, featureJson)

    @pyqtSlot(str)
    def onFeatureAdded(self, featureJson):
        self.featureAdded.emit(featureJson)

    @pyqtSlot()
    def toggleTable(self):
        self.tableToggleRequested.emit()

    @pyqtSlot(str)
    def onWmsDeleted(self, layerId):
        self.wmsDeleted.emit(layerId)

    @pyqtSlot()
    def requestAddService(self):
        self.serviceAddRequested.emit()

    @pyqtSlot(str)
    def onActiveLayerRequested(self, layerId):
        self.activeLayerRequested.emit(layerId)

    @pyqtSlot(str)
    def onLayerRemoved(self, layerId):
        self.layerRemoved.emit(layerId)

    @pyqtSlot(float, float, float, float, int)
    def onViewportChanged(self, minx, miny, maxx, maxy, zoom):
        self.viewportChanged.emit(minx, miny, maxx, maxy, zoom)

    @pyqtSlot(str)
    def onSelectionChanged(self, indicesJson):
        self.selectionChanged.emit(indicesJson)

    @pyqtSlot(str)
    def onSelectionDeleted(self, indicesJson):
        self.selectionDeleted.emit(indicesJson)

    @pyqtSlot()
    def requestCaptureSnapshot(self):
        self.captureSnapshotRequested.emit()


class AbstractPreviewPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.web_view = QWebEngineView()
        self.layout.addWidget(self.web_view)

    def render_content(self, content: str):
        pass


class MapPreviewPanel(AbstractPreviewPanel):
    feature_clicked = pyqtSignal(int)
    feature_deleted = pyqtSignal(int)
    feature_updated = pyqtSignal(int, str)
    feature_added = pyqtSignal(str)
    table_toggle_requested = pyqtSignal()
    wms_deleted = pyqtSignal(str)
    service_add_requested = pyqtSignal()
    active_layer_requested = pyqtSignal(str)
    layer_removed = pyqtSignal(str)
    viewport_changed = pyqtSignal(float, float, float, float, int)
    selection_changed = pyqtSignal(list)
    selection_deleted = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_loaded = False
        self._pending_content = None
        self._pending_vector_info = None

        self.bridge = MapBridge()
        self.bridge.featureSelected.connect(self.feature_clicked.emit)
        self.bridge.featureDeleted.connect(self.feature_deleted.emit)
        self.bridge.featureUpdated.connect(self.feature_updated.emit)
        self.bridge.featureAdded.connect(self.feature_added.emit)
        self.bridge.tableToggleRequested.connect(self.table_toggle_requested.emit)
        self.bridge.wmsDeleted.connect(self.wms_deleted.emit)
        self.bridge.serviceAddRequested.connect(self.service_add_requested.emit)
        self.bridge.activeLayerRequested.connect(self.active_layer_requested.emit)
        self.bridge.layerRemoved.connect(self.layer_removed.emit)
        self.bridge.viewportChanged.connect(self.viewport_changed.emit)
        self.bridge.selectionChanged.connect(self._on_bridge_selection_changed)
        self.bridge.selectionDeleted.connect(self._on_bridge_selection_deleted)
        self.bridge.captureSnapshotRequested.connect(self.capture_snapshot)

        self.channel = QWebChannel()
        self.channel.registerObject("mapBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        self.web_view.loadFinished.connect(self._on_load_finished)
        self._init_map()

    def _init_map(self):
        map_html_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "resources", "map", "index.html"
        )
        try:
            with open(map_html_path, "r", encoding="utf-8") as f:
                html_content = f.read()
        except Exception as e:
            html_content = f"<html><body><h3>Failed to load map template: {e}</h3></body></html>"
        self.web_view.setHtml(html_content, QUrl("qrc:/"))

    def _on_load_finished(self, ok):
        if ok:
            self._is_loaded = True
            if self._pending_content:
                if isinstance(self._pending_content, tuple):
                    c, fb = self._pending_content
                    self.render_content(c, fit_bounds=fb)
                else:
                    self.render_content(self._pending_content, fit_bounds=True)
                self._pending_content = None
            if getattr(self, '_pending_vector_layers', None):
                last_fit_layer = None
                for lid, item in list(self._pending_vector_layers.items()):
                    lname, lgjson, lia, lgt, lcol, lfb = item[:6]
                    lwfs = item[6] if len(item) > 6 else False
                    self.set_vector_layer(lid, lname, lgjson, lia, lgt, lcol, lfb, lwfs)
                    if lfb:
                        last_fit_layer = lid
                self._pending_vector_layers.clear()
                if last_fit_layer:
                    self.fit_bounds(last_fit_layer)
            if getattr(self, '_pending_wms_layers', None):
                for wid, (wurl, wlayer, wfmt, wtrans, wtitle) in list(self._pending_wms_layers.items()):
                    self.add_wms_layer(wid, wurl, wlayer, wfmt, wtrans, wtitle)
                self._pending_wms_layers.clear()
            if getattr(self, '_pending_active_layer', None):
                lid, lgt = self._pending_active_layer
                self.set_active_vector_layer(lid, lgt)
                self._pending_active_layer = None
            if self._pending_vector_info:
                n, c = self._pending_vector_info
                self.set_active_vector_info(n, c)
                self._pending_vector_info = None
            if getattr(self, '_pending_geom_type', None):
                self.set_layer_geometry_type(self._pending_geom_type)
                self._pending_geom_type = None
            if getattr(self, '_pending_basemap', None):
                self.set_basemap(self._pending_basemap)
                self._pending_basemap = None

    def set_vector_layer(self, layer_id: str, name: str, geojson_str: str, is_active: bool = True, geom_type: str = "any", color: str = None, fit_bounds: bool = False, is_wfs: bool = False):
        if not geojson_str or not geojson_str.strip():
            return
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            esc_name = json.dumps(name)
            esc_type = json.dumps(geom_type)
            esc_color = json.dumps(color) if color else "null"
            act_str = "true" if is_active else "false"
            fit_str = "true" if fit_bounds else "false"
            wfs_str = "true" if is_wfs else "false"
            js_code = f"setVectorLayer({esc_id}, {esc_name}, {geojson_str}, {act_str}, {esc_type}, {esc_color}, {fit_str}, {wfs_str});"
            self.web_view.page().runJavaScript(js_code)
        else:
            if not hasattr(self, '_pending_vector_layers'):
                self._pending_vector_layers = {}
            self._pending_vector_layers[layer_id] = (name, geojson_str, is_active, geom_type, color, fit_bounds, is_wfs)

    def update_vector_layer_data(self, layer_id: str, geojson_str: str, name: str = None, geom_type: str = "any"):
        if not geojson_str or not geojson_str.strip():
            return
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            esc_name = json.dumps(name) if name else "null"
            esc_type = json.dumps(geom_type)
            js_code = f"updateVectorLayerData({esc_id}, {esc_name}, {geojson_str}, {esc_type});"
            self.web_view.page().runJavaScript(js_code)

    def set_active_vector_layer(self, layer_id: str, geom_type: str = "any"):
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            esc_type = json.dumps(geom_type)
            self.web_view.page().runJavaScript(f"setActiveVectorLayer({esc_id}, {esc_type});")
        else:
            self._pending_active_layer = (layer_id, geom_type)

    def set_vector_layer_visibility(self, layer_id: str, visible: bool):
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            vis_str = "true" if visible else "false"
            self.web_view.page().runJavaScript(f"setVectorLayerVisibility({esc_id}, {vis_str});")

    def remove_vector_layer(self, layer_id: str):
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            self.web_view.page().runJavaScript(f"removeVectorLayer({esc_id});")
        else:
            if hasattr(self, '_pending_vector_layers') and layer_id in self._pending_vector_layers:
                del self._pending_vector_layers[layer_id]

    def clear_all_vector_layers(self):
        if self._is_loaded:
            self.web_view.page().runJavaScript("clearAllVectorLayers();")
        else:
            if hasattr(self, '_pending_vector_layers'):
                self._pending_vector_layers.clear()

    def update_layer_name(self, layer_id: str, name: str):
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            esc_name = json.dumps(name)
            self.web_view.page().runJavaScript(f"updateLayerName({esc_id}, {esc_name});")

    def set_layer_geometry_type(self, geom_type: str):
        self._current_geom_type = geom_type
        if self._is_loaded:
            esc_type = json.dumps(geom_type)
            self.web_view.page().runJavaScript(f"setLayerGeometryType({esc_type});")
        else:
            self._pending_geom_type = geom_type

    def set_active_vector_info(self, name: str, count: int):
        if self._is_loaded:
            esc_name = json.dumps(name)
            self.web_view.page().runJavaScript(f"setActiveVectorInfo({esc_name}, {count});")
        else:
            self._pending_vector_info = (name, count)

    def render_content(self, content: str, fit_bounds: bool = False):
        if not self._is_loaded:
            self._pending_content = (content, fit_bounds)
            return

        if not content or not content.strip():
            self.web_view.page().runJavaScript("updateMap(null);")
            return

        try:
            fit_arg = "true" if fit_bounds else "false"
            js_code = f"updateMap({content}, {fit_arg});"
            self.web_view.page().runJavaScript(js_code)
        except Exception:
            pass

    def _on_bridge_selection_changed(self, indices_json: str):
        try:
            indices = json.loads(indices_json)
            if isinstance(indices, list):
                self.selection_changed.emit(indices)
        except Exception:
            pass

    def _on_bridge_selection_deleted(self, indices_json: str):
        try:
            indices = json.loads(indices_json)
            if isinstance(indices, list):
                self.selection_deleted.emit(indices)
        except Exception:
            pass

    def highlight_feature(self, index: int, layer_id: str = None):
        if self._is_loaded:
            esc_id = json.dumps(layer_id) if layer_id else "null"
            self.web_view.page().runJavaScript(f"highlightFeature({index}, {esc_id});")

    def set_selected_features(self, indices: list, layer_id: str = None):
        if self._is_loaded:
            esc_indices = json.dumps(indices)
            esc_id = json.dumps(layer_id) if layer_id else "null"
            self.web_view.page().runJavaScript(f"setSelectedFeatures({esc_indices}, {esc_id});")

    def clear_selection(self, layer_id: str = None):
        if self._is_loaded:
            esc_id = json.dumps(layer_id) if layer_id else "null"
            self.web_view.page().runJavaScript(f"clearSelection({esc_id});")

    def zoom_to_selected(self, layer_id: str = None):
        if self._is_loaded:
            esc_id = json.dumps(layer_id) if layer_id else "null"
            self.web_view.page().runJavaScript(f"zoomToSelected({esc_id});")

    def set_select_tool(self, mode: str = "click"):
        if self._is_loaded:
            esc_mode = json.dumps(mode)
            self.web_view.page().runJavaScript(f"setSelectTool({esc_mode});")

    def fit_bounds(self, layer_id: str = None):
        if self._is_loaded:
            esc_id = json.dumps(layer_id) if layer_id else "null"
            self.web_view.page().runJavaScript(f"fitLayerBounds({esc_id});")

    def fit_layer_bounds(self, layer_id: str = None):
        self.fit_bounds(layer_id)

    def zoom_full_extent(self):
        if self._is_loaded:
            self.web_view.page().runJavaScript("zoomFullExtent();")

    def refresh_map(self):
        if self._is_loaded:
            self.web_view.page().runJavaScript("refreshMap();")

    def zoom_to_extent(self, minx: float, miny: float, maxx: float, maxy: float, max_zoom: int = 17):
        if not self._is_loaded:
            return
        try:
            # If coordinates are in projected meters (abs > 180), convert to degrees using pyproj
            if abs(minx) > 180.0 or abs(maxx) > 180.0 or abs(miny) > 90.0 or abs(maxy) > 90.0:
                try:
                    import pyproj
                    transformer = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
                    minx, miny = transformer.transform(minx, miny)
                    maxx, maxy = transformer.transform(maxx, maxy)
                except Exception:
                    pass

            s = max(-85.05, min(85.05, float(miny)))
            n = max(-85.05, min(85.05, float(maxy)))
            w = max(-180.0, min(180.0, float(minx)))
            e = max(-180.0, min(180.0, float(maxx)))

            if s > n:
                s, n = n, s
            if w > e:
                w, e = e, w

            # Ensure minimal box dimensions so Leaflet fitBounds doesn't degenerate
            if abs(n - s) < 1e-5:
                s -= 0.001
                n += 0.001
            if abs(e - w) < 1e-5:
                w -= 0.001
                e += 0.001

            js_code = (
                f"if (typeof map !== 'undefined' && map) {{ "
                f"try {{ map.fitBounds([[{s:.6f}, {w:.6f}], [{n:.6f}, {e:.6f}]], {{ maxZoom: {max_zoom}, padding: [50, 50], animate: true }}); }} "
                f"catch(err) {{ console.error('fitBounds failed:', err); }} "
                f"}}"
            )
            self.web_view.page().runJavaScript(js_code)
        except Exception as ex:
            print(f"zoom_to_extent exception: {ex}")

    def capture_snapshot(self):
        if not self._is_loaded:
            return
        # Enter snapshot mode: hide toolbars & zoom buttons, show clean layer legend, update coords
        self.web_view.page().runJavaScript("prepareSnapshotMode();", self._on_snapshot_ready)

    def _on_snapshot_ready(self, _=None):
        # Allow WebEngine rendering pipeline to paint the frame with toolbar hidden
        QTimer.singleShot(75, self._perform_grab_and_prompt)

    def _perform_grab_and_prompt(self):
        try:
            pixmap = self.web_view.grab()
        finally:
            # Always restore normal toolbar and UI
            self.web_view.page().runJavaScript("restoreSnapshotMode();")

        try:
            QApplication.clipboard().setPixmap(pixmap)
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Map View", "map_view.png", "PNG Image (*.png);;JPEG Image (*.jpg)"
            )
            from ui.toast import ToastNotification
            if file_path:
                pixmap.save(file_path)
                ToastNotification.show_toast(self.window(), f"Map snapshot saved: {os.path.basename(file_path)}", "success")
            else:
                ToastNotification.show_toast(self.window(), "Map snapshot copied to clipboard", "info")
        except Exception as e:
            print(f"Error capturing snapshot: {e}")

    def add_wms_layer(self, layer_id: str, url: str, layer_name: str, fmt: str = "image/png", transparent: bool = True, title: str = ""):
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            esc_url = json.dumps(url)
            esc_layer = json.dumps(layer_name)
            esc_fmt = json.dumps(fmt)
            esc_title = json.dumps(title or layer_name)
            trans_str = "true" if transparent else "false"
            self.web_view.page().runJavaScript(f"addWmsLayer({esc_id}, {esc_url}, {esc_layer}, {esc_fmt}, {trans_str}, {esc_title});")
        else:
            if not hasattr(self, '_pending_wms_layers'):
                self._pending_wms_layers = {}
            self._pending_wms_layers[layer_id] = (url, layer_name, fmt, transparent, title)

    def remove_wms_layer(self, layer_id: str):
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            self.web_view.page().runJavaScript(f"removeWmsLayer({esc_id});")
        else:
            if hasattr(self, '_pending_wms_layers') and layer_id in self._pending_wms_layers:
                del self._pending_wms_layers[layer_id]

    def set_wms_visibility(self, layer_id: str, visible: bool):
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            vis_str = "true" if visible else "false"
            self.web_view.page().runJavaScript(f"setWmsVisibility({esc_id}, {vis_str});")

    def set_basemap(self, base_type: str):
        if self._is_loaded:
            esc_type = json.dumps(base_type)
            self.web_view.page().runJavaScript(f"setBaseMap({esc_type});")
        else:
            self._pending_basemap = base_type

    def set_theme_tiles(self, theme_name: str):
        if self._is_loaded:
            tile_key = 'dark' if ThemeManager.is_dark(theme_name) else 'osm'
            self.web_view.page().runJavaScript(f"setBaseMap('{tile_key}');")

    def set_table_active(self, active: bool):
        if self._is_loaded:
            act_str = "true" if active else "false"
            self.web_view.page().runJavaScript(f"setTableButtonActive({act_str});")


class MarkdownPreviewPanel(AbstractPreviewPanel):

    def render_content(self, content: str):
        try:
            raw_html = markdown.markdown(content, extensions=['extra', 'codehilite', 'tables'])
            is_dark = ThemeManager.is_dark()
            bg_color = "#1e1e1e" if is_dark else "#ffffff"
            text_color = "#cccccc" if is_dark else "#24292e"
            code_bg = "#2d2d2d" if is_dark else "#f6f8fa"
            border_col = "#3c3c3c" if is_dark else "#e1e4e8"

            styled_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8" />
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                        color: {text_color};
                        background-color: {bg_color};
                        padding: 24px;
                        font-size: 14px;
                        line-height: 1.6;
                        margin: 0;
                    }}
                    pre, code {{
                        background-color: {code_bg};
                        border-radius: 4px;
                        font-family: Consolas, Monaco, monospace;
                    }}
                    pre {{ padding: 12px; overflow-x: auto; }}
                    code {{ padding: 2px 5px; }}
                    table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
                    th, td {{ border: 1px solid {border_col}; padding: 8px 12px; }}
                    th {{ background-color: {code_bg}; }}
                    blockquote {{
                        border-left: 4px solid #007fd4;
                        margin: 0;
                        padding-left: 14px;
                        color: #858585;
                    }}
                </style>
            </head>
            <body>
                {raw_html}
            </body>
            </html>
            """
            self.web_view.setHtml(styled_html)
        except Exception as e:
            print(f"Markdown rendering error: {e}")