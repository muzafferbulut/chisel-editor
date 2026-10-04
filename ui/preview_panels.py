import json
import markdown
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import pyqtSignal, QObject, pyqtSlot, QUrl
from core.theme import ThemeManager


class MapBridge(QObject):
    featureSelected = pyqtSignal(int)

    @pyqtSlot(int)
    def onFeatureClicked(self, index):
        self.featureSelected.emit(index)


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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_loaded = False
        self._pending_content = None

        self.bridge = MapBridge()
        self.bridge.featureSelected.connect(self.feature_clicked.emit)

        self.channel = QWebChannel()
        self.channel.registerObject("mapBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        self.web_view.loadFinished.connect(self._on_load_finished)
        self._init_map()

    def _init_map(self):
        theme = ThemeManager._current_theme
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
            <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
            <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <style>
                html, body, #map {{
                    margin: 0; padding: 0; width: 100vw; height: 100vh; overflow: hidden;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                }}
                .hud-panel {{
                    position: absolute;
                    background: rgba(30, 30, 30, 0.85);
                    color: #e0e0e0;
                    backdrop-filter: blur(8px);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 12px;
                    z-index: 1000;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                    user-select: none;
                }}
                .hud-coords {{
                    bottom: 12px;
                    right: 12px;
                    font-family: monospace;
                    display: flex;
                    gap: 12px;
                }}
                .hud-toolbar {{
                    top: 12px;
                    right: 12px;
                    display: flex;
                    gap: 6px;
                    align-items: center;
                    padding: 4px 8px;
                }}
                .hud-stats {{
                    top: 12px;
                    left: 54px;
                    font-weight: 500;
                }}
                .hud-btn {{
                    background: rgba(255, 255, 255, 0.12);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    color: #fff;
                    padding: 4px 8px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 11px;
                    transition: all 0.15s ease;
                }}
                .hud-btn:hover {{
                    background: #007fd4;
                    border-color: #007fd4;
                }}
                .hud-btn.active {{
                    background: #007fd4;
                    border-color: #007fd4;
                    font-weight: bold;
                }}
                .hud-slider {{
                    width: 70px;
                    cursor: pointer;
                    vertical-align: middle;
                }}
                .leaflet-popup-content-wrapper {{
                    background: #252526 !important;
                    color: #cccccc !important;
                    border-radius: 6px;
                    box-shadow: 0 6px 20px rgba(0,0,0,0.5);
                    border: 1px solid #3c3c3c;
                    padding: 4px;
                }}
                .leaflet-popup-tip {{
                    background: #252526 !important;
                }}
                .prop-table {{
                    width: 100%;
                    border-collapse: collapse;
                    font-size: 11px;
                    max-height: 240px;
                    overflow-y: auto;
                    display: block;
                }}
                .prop-table th, .prop-table td {{
                    padding: 4px 8px;
                    text-align: left;
                    border-bottom: 1px solid #333;
                }}
                .prop-table th {{
                    color: #858585;
                    font-weight: 600;
                }}
                .prop-table td {{
                    color: #e0e0e0;
                    word-break: break-all;
                }}
                .prop-title {{
                    font-weight: bold;
                    color: #00a2ff;
                    margin-bottom: 6px;
                    font-size: 12px;
                    display: flex;
                    justify-content: space-between;
                }}
                .measure-tooltip {{
                    background: rgba(0,0,0,0.8);
                    color: #fff;
                    padding: 3px 6px;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: bold;
                    border: 1px solid #00a2ff;
                }}
            </style>
        </head>
        <body>
            <div id="map"></div>

            <div class="hud-panel hud-stats" id="statsPill">No layer loaded</div>

            <div class="hud-panel hud-toolbar">
                <button class="hud-btn" id="btnFit" title="Zoom to layer bounds">🎯 Fit</button>
                <button class="hud-btn" id="btnMeasure" title="Measure Distance / Area">📏 Measure</button>
                <button class="hud-btn" id="btnCluster" title="Toggle Marker Clustering">📍 Cluster: Off</button>
                <span style="font-size:10px; color:#aaa; margin-left:4px;">Opacity:</span>
                <input type="range" class="hud-slider" id="opacitySlider" min="10" max="100" value="85" title="Layer Opacity"/>
                <span style="border-left: 1px solid #555; height: 16px; margin: 0 4px;"></span>
                <button class="hud-btn" id="btnDark" onclick="setBaseMap('dark')">Dark</button>
                <button class="hud-btn" id="btnLight" onclick="setBaseMap('light')">Light</button>
                <button class="hud-btn" id="btnOsm" onclick="setBaseMap('osm')">Street</button>
                <button class="hud-btn" id="btnSat" onclick="setBaseMap('sat')">Satellite</button>
            </div>

            <div class="hud-panel hud-coords" id="coordsPill">
                <span>Lat: 0.0000°</span><span>Lng: 0.0000°</span><span>Zoom: 2</span>
            </div>

            <script>
                var map = L.map('map', {{
                    preferCanvas: true,
                    zoomControl: true,
                    attributionControl: false
                }}).setView([39.0, 35.0], 5);

                L.control.scale({{ imperial: false, position: 'bottomleft' }}).addTo(map);

                var tiles = {{
                    dark: L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{ maxZoom: 19 }}),
                    light: L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{ maxZoom: 19 }}),
                    osm: L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 19 }}),
                    sat: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{ maxZoom: 18 }})
                }};

                var currentBase = '{theme}' === 'dark' ? 'dark' : 'light';
                tiles[currentBase].addTo(map);
                updateActiveBaseButton(currentBase);

                function setBaseMap(type) {{
                    if (tiles[currentBase]) map.removeLayer(tiles[currentBase]);
                    currentBase = type;
                    if (tiles[type]) tiles[type].addTo(map);
                    if (geojsonLayer) geojsonLayer.bringToFront();
                    updateActiveBaseButton(type);
                }}

                function updateActiveBaseButton(type) {{
                    ['btnDark', 'btnLight', 'btnOsm', 'btnSat'].forEach(id => {{
                        var btn = document.getElementById(id);
                        if (btn) btn.classList.remove('active');
                    }});
                    var mapBtn = {{ dark: 'btnDark', light: 'btnLight', osm: 'btnOsm', sat: 'btnSat' }}[type];
                    if (mapBtn && document.getElementById(mapBtn)) {{
                        document.getElementById(mapBtn).classList.add('active');
                    }}
                }}

                var geojsonLayer = null;
                var clusterGroup = null;
                var useClustering = false;
                var layerIndexMap = {{}};
                var currentOpacity = 0.85;
                var pyBridge = null;

                if (typeof QWebChannel !== 'undefined') {{
                    new QWebChannel(qt.webChannelTransport, function(channel) {{
                        pyBridge = channel.objects.mapBridge;
                    }});
                }}

                map.on('mousemove', function(e) {{
                    document.getElementById('coordsPill').innerHTML = 
                        '<span>Lat: ' + e.latlng.lat.toFixed(4) + '°</span>' +
                        '<span>Lng: ' + e.latlng.lng.toFixed(4) + '°</span>' +
                        '<span>Zoom: ' + map.getZoom() + '</span>';
                }});

                document.getElementById('btnFit').onclick = function() {{
                    fitLayerBounds();
                }};

                document.getElementById('opacitySlider').oninput = function(e) {{
                    currentOpacity = e.target.value / 100.0;
                    if (geojsonLayer) {{
                        geojsonLayer.setStyle(function(feature) {{
                            return {{
                                fillOpacity: currentOpacity * 0.4,
                                opacity: currentOpacity
                            }};
                        }});
                    }}
                }};

                document.getElementById('btnCluster').onclick = function() {{
                    useClustering = !useClustering;
                    this.textContent = useClustering ? '📍 Cluster: ON' : '📍 Cluster: Off';
                    this.classList.toggle('active', useClustering);
                    if (lastGeojsonData) {{
                        updateMap(lastGeojsonData);
                    }}
                }};

                // --- Measurement Ruler Tool ---
                var measureActive = false;
                var measurePoints = [];
                var measureMarkers = [];
                var measureLine = null;
                var measurePolygon = null;
                var measureTooltip = null;

                document.getElementById('btnMeasure').onclick = function() {{
                    measureActive = !measureActive;
                    this.classList.toggle('active', measureActive);
                    if (!measureActive) {{
                        clearMeasure();
                    }}
                }};

                map.on('click', function(e) {{
                    if (!measureActive) return;
                    measurePoints.push(e.latlng);

                    var m = L.circleMarker(e.latlng, {{ radius: 5, color: '#e74c3c', fillColor: '#fff', fillOpacity: 1 }}).addTo(map);
                    measureMarkers.push(m);

                    if (measurePoints.length > 1) {{
                        if (measureLine) map.removeLayer(measureLine);
                        measureLine = L.polyline(measurePoints, {{ color: '#e74c3c', weight: 3, dashArray: '6, 6' }}).addTo(map);

                        // Calculate Distance
                        var totalDist = 0;
                        for (var i = 1; i < measurePoints.length; i++) {{
                            totalDist += measurePoints[i - 1].distanceTo(measurePoints[i]);
                        }}
                        var distText = totalDist > 1000 ? (totalDist / 1000).toFixed(2) + ' km' : totalDist.toFixed(1) + ' m';

                        // Calculate Area if >= 3
                        var areaText = '';
                        if (measurePoints.length >= 3) {{
                            if (measurePolygon) map.removeLayer(measurePolygon);
                            measurePolygon = L.polygon(measurePoints, {{ color: '#e74c3c', fillOpacity: 0.15, weight: 1 }}).addTo(map);
                        }}

                        if (!measureTooltip) {{
                            measureTooltip = L.tooltip({{ permanent: true, className: 'measure-tooltip' }});
                        }}
                        measureTooltip.setLatLng(e.latlng).setContent('📏 ' + distText).addTo(map);
                    }}
                }});

                function clearMeasure() {{
                    measurePoints = [];
                    measureMarkers.forEach(m => map.removeLayer(m));
                    measureMarkers = [];
                    if (measureLine) map.removeLayer(measureLine);
                    if (measurePolygon) map.removeLayer(measurePolygon);
                    if (measureTooltip) map.removeLayer(measureTooltip);
                    measureLine = null;
                    measurePolygon = null;
                    measureTooltip = null;
                }}

                var lastGeojsonData = null;

                function updateMap(geojsonData) {{
                    lastGeojsonData = geojsonData;
                    if (geojsonLayer) {{
                        map.removeLayer(geojsonLayer);
                        geojsonLayer = null;
                    }}
                    if (clusterGroup) {{
                        map.removeLayer(clusterGroup);
                        clusterGroup = null;
                    }}
                    layerIndexMap = {{}};

                    if (!geojsonData) {{
                        document.getElementById('statsPill').textContent = 'No data';
                        return;
                    }}

                    var featureCount = 0;
                    if (geojsonData.type === 'FeatureCollection' && geojsonData.features) {{
                        featureCount = geojsonData.features.length;
                    }} else if (geojsonData.type === 'Feature') {{
                        featureCount = 1;
                    }}

                    document.getElementById('statsPill').textContent = '📍 ' + featureCount.toLocaleString() + ' Features';

                    var geomColors = {{
                        Point: '#00a2ff',
                        MultiPoint: '#00a2ff',
                        LineString: '#ff8800',
                        MultiLineString: '#ff8800',
                        Polygon: '#2ecc71',
                        MultiPolygon: '#2ecc71'
                    }};

                    if (useClustering && typeof L.markerClusterGroup === 'function') {{
                        clusterGroup = L.markerClusterGroup({{
                            maxClusterRadius: 50,
                            spiderfyOnMaxZoom: true,
                            showCoverageOnHover: false
                        }});
                    }}

                    var featureIdx = 0;
                    geojsonLayer = L.geoJSON(geojsonData, {{
                        pointToLayer: function(feature, latlng) {{
                            var marker = L.circleMarker(latlng, {{
                                radius: 7,
                                fillColor: '#00a2ff',
                                color: '#ffffff',
                                weight: 2,
                                opacity: currentOpacity,
                                fillOpacity: currentOpacity * 0.9
                            }});
                            if (clusterGroup) clusterGroup.addLayer(marker);
                            return marker;
                        }},
                        style: function(feature) {{
                            var gtype = feature.geometry ? feature.geometry.type : 'Polygon';
                            var color = geomColors[gtype] || '#3388ff';
                            return {{
                                color: color,
                                weight: 2,
                                opacity: currentOpacity,
                                fillColor: color,
                                fillOpacity: currentOpacity * 0.35
                            }};
                        }},
                        onEachFeature: function(feature, layer) {{
                            var currentIdx = featureIdx++;
                            layerIndexMap[currentIdx] = layer;

                            var title = (feature.properties && (feature.properties.city || feature.properties.name || feature.properties.NAME || feature.properties.title || feature.properties.id)) || ('Feature #' + currentIdx);
                            layer.bindTooltip(String(title), {{ sticky: true }});

                            layer.on('click', function(e) {{
                                var props = feature.properties || {{}};
                                var gType = feature.geometry ? feature.geometry.type : 'Unknown';
                                var html = '<div class="prop-title"><span>Feature #' + currentIdx + '</span><span>[' + gType + ']</span></div>';
                                html += '<table class="prop-table">';
                                var keys = Object.keys(props);
                                if (keys.length === 0) {{
                                    html += '<tr><td colspan="2"><i>No attributes</i></td></tr>';
                                }} else {{
                                    keys.forEach(function(k) {{
                                        var val = props[k];
                                        if (val === null || val === undefined) val = '<i>null</i>';
                                        html += '<tr><th>' + k + '</th><td>' + val + '</td></tr>';
                                    }});
                                }}
                                html += '</table>';
                                layer.bindPopup(html, {{ maxWidth: 350, maxHeight: 300 }}).openPopup();

                                if (pyBridge) {{
                                    pyBridge.onFeatureClicked(currentIdx);
                                }}
                            }});
                        }}
                    }});

                    if (clusterGroup) {{
                        map.addLayer(clusterGroup);
                    }} else {{
                        map.addLayer(geojsonLayer);
                    }}

                    fitLayerBounds();
                }}

                function highlightFeature(idx) {{
                    var layer = layerIndexMap[idx];
                    if (layer) {{
                        if (layer.getBounds && layer.getBounds().isValid()) {{
                            map.fitBounds(layer.getBounds(), {{ maxZoom: 16, padding: [40, 40] }});
                        }} else if (layer.getLatLng) {{
                            map.setView(layer.getLatLng(), Math.max(map.getZoom(), 14));
                        }}
                        if (layer.openPopup) layer.openPopup();
                    }}
                }}

                function fitLayerBounds() {{
                    if (geojsonLayer && geojsonLayer.getBounds().isValid()) {{
                        map.fitBounds(geojsonLayer.getBounds(), {{ padding: [30, 30] }});
                    }}
                }}
            </script>
        </body>
        </html>
        """
        self.web_view.setHtml(html_content, QUrl("qrc:/"))

    def _on_load_finished(self, ok):
        if ok:
            self._is_loaded = True
            if self._pending_content:
                self.render_content(self._pending_content)
                self._pending_content = None

    def render_content(self, content: str):
        if not self._is_loaded:
            self._pending_content = content
            return

        if not content or not content.strip():
            self.web_view.page().runJavaScript("updateMap(null);")
            return

        try:
            json.loads(content)
            js_code = f"updateMap({content});"
            self.web_view.page().runJavaScript(js_code)
        except Exception:
            pass

    def highlight_feature(self, index: int):
        if self._is_loaded:
            self.web_view.page().runJavaScript(f"highlightFeature({index});")

    def fit_bounds(self):
        if self._is_loaded:
            self.web_view.page().runJavaScript("fitLayerBounds();")

    def set_theme_tiles(self, theme_name: str):
        if self._is_loaded:
            tile_key = 'dark' if theme_name == 'dark' else 'light'
            self.web_view.page().runJavaScript(f"setBaseMap('{tile_key}');")


class MarkdownPreviewPanel(AbstractPreviewPanel):

    def render_content(self, content: str):
        try:
            raw_html = markdown.markdown(content, extensions=['extra', 'codehilite', 'tables'])
            is_dark = ThemeManager._current_theme == "dark"
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