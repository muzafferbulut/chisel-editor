import json
import markdown
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import pyqtSignal, QObject, pyqtSlot, QUrl
from core.theme import ThemeManager


class MapBridge(QObject):
    featureSelected = pyqtSignal(int)
    featureDeleted = pyqtSignal(int)
    featureAdded = pyqtSignal(str)
    tableToggleRequested = pyqtSignal()

    @pyqtSlot(int)
    def onFeatureClicked(self, index):
        self.featureSelected.emit(index)

    @pyqtSlot(int)
    def onFeatureDeleted(self, index):
        self.featureDeleted.emit(index)

    @pyqtSlot(str)
    def onFeatureAdded(self, featureJson):
        self.featureAdded.emit(featureJson)

    @pyqtSlot()
    def toggleTable(self):
        self.tableToggleRequested.emit()


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
    feature_added = pyqtSignal(str)
    table_toggle_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_loaded = False
        self._pending_content = None

        self.bridge = MapBridge()
        self.bridge.featureSelected.connect(self.feature_clicked.emit)
        self.bridge.featureDeleted.connect(self.feature_deleted.emit)
        self.bridge.featureAdded.connect(self.feature_added.emit)
        self.bridge.tableToggleRequested.connect(self.table_toggle_requested.emit)

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
                    background: rgba(30, 30, 30, 0.88);
                    color: #e0e0e0;
                    backdrop-filter: blur(8px);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    border-radius: 6px;
                    padding: 5px 10px;
                    font-size: 11px;
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
                .hud-toolbar-v {{
                    position: absolute;
                    top: 14px;
                    right: 14px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    gap: 5px;
                    background: rgba(24, 28, 34, 0.92);
                    backdrop-filter: blur(10px);
                    border: 1px solid rgba(255, 255, 255, 0.14);
                    border-radius: 8px;
                    padding: 6px 5px;
                    z-index: 1000;
                    box-shadow: 0 6px 20px rgba(0,0,0,0.35);
                    user-select: none;
                }}
                .hud-vbtn {{
                    position: relative;
                    width: 30px;
                    height: 30px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.14);
                    color: #e0e0e0;
                    border-radius: 5px;
                    cursor: pointer;
                    font-size: 13px;
                    transition: all 0.15s ease;
                    padding: 0;
                    margin: 0;
                    box-sizing: border-box;
                }}
                .hud-vbtn:hover {{
                    background: #0078d4;
                    border-color: #4cc2ff;
                    color: #ffffff;
                }}
                .hud-vbtn.active {{
                    background: #0078d4;
                    border-color: #4cc2ff;
                    color: #ffffff;
                    font-weight: bold;
                }}
                .hud-vbtn-del:hover {{
                    background: #d32f2f !important;
                    border-color: #f44336 !important;
                    color: #ffffff !important;
                }}
                .hud-vbtn-del.has-selection {{
                    background: rgba(231, 76, 60, 0.3);
                    border-color: #e74c3c;
                    color: #ff6b6b;
                }}
                .hud-vdivider {{
                    width: 20px;
                    height: 1px;
                    background: rgba(255, 255, 255, 0.15);
                    margin: 2px 0;
                }}
                .hud-vbtn[data-tip]::after {{
                    content: attr(data-tip);
                    position: absolute;
                    right: calc(100% + 9px);
                    top: 50%;
                    transform: translateY(-50%);
                    background: rgba(15, 23, 42, 0.95);
                    color: #ffffff;
                    font-size: 11px;
                    font-weight: 500;
                    padding: 4px 8px;
                    border-radius: 4px;
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    white-space: nowrap;
                    pointer-events: none;
                    opacity: 0;
                    visibility: hidden;
                    transition: opacity 0.15s ease, transform 0.15s ease;
                    box-shadow: 0 4px 14px rgba(0,0,0,0.4);
                    z-index: 2000;
                }}
                .hud-vbtn:hover[data-tip]::after {{
                    opacity: 1;
                    visibility: visible;
                    transform: translateY(-50%) translateX(-2px);
                }}
                .hud-flyout {{
                    position: absolute;
                    right: 38px;
                    top: 0;
                    display: none;
                    background: rgba(24, 28, 34, 0.95);
                    backdrop-filter: blur(10px);
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 6px;
                    padding: 4px;
                    gap: 4px;
                    box-shadow: 0 6px 18px rgba(0,0,0,0.4);
                    z-index: 1002;
                    white-space: nowrap;
                }}
                .hud-flyout.open {{
                    display: flex;
                }}
                .hud-flyout-btn {{
                    background: rgba(255, 255, 255, 0.1);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    color: #e0e0e0;
                    padding: 4px 8px;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 11px;
                    transition: all 0.15s ease;
                }}
                .hud-flyout-btn:hover {{
                    background: #0078d4;
                    border-color: #0078d4;
                    color: #fff;
                }}
                .hud-flyout-btn.active {{
                    background: #0078d4;
                    border-color: #0078d4;
                    color: #fff;
                    font-weight: bold;
                }}
                .hud-banner {{
                    position: absolute;
                    top: 14px;
                    left: 50%;
                    transform: translateX(-50%);
                    background: rgba(0, 120, 212, 0.94);
                    color: #fff;
                    padding: 6px 14px;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: 500;
                    display: none;
                    align-items: center;
                    gap: 12px;
                    z-index: 1005;
                    box-shadow: 0 4px 16px rgba(0,0,0,0.35);
                    backdrop-filter: blur(6px);
                }}
                .hud-banner.active {{
                    display: flex;
                }}
                .hud-banner-cancel {{
                    background: rgba(255, 255, 255, 0.2);
                    border: none;
                    color: #fff;
                    padding: 2px 8px;
                    border-radius: 10px;
                    font-size: 11px;
                    cursor: pointer;
                }}
                .hud-banner-cancel:hover {{
                    background: rgba(255, 255, 255, 0.35);
                }}
                .hud-popup-del-btn {{
                    background: #e74c3c;
                    color: #fff;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: background 0.15s ease;
                }}
                .hud-popup-del-btn:hover {{
                    background: #c0392b;
                }}
                .hud-stats {{
                    top: 12px;
                    left: 54px;
                    font-weight: 500;
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
                    max-height: 220px;
                    overflow-y: auto;
                    display: block;
                }}
                .prop-table th, .prop-table td {{
                    padding: 3px 6px;
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
                    background: rgba(0,0,0,0.85);
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

            <div class="hud-panel hud-stats" id="statsPill">Mekansal Katman</div>

            <div class="hud-banner" id="drawBanner">
                <span id="drawBannerText">Haritaya tıklayarak nokta ekleyin</span>
                <button class="hud-banner-cancel" onclick="cancelDrawMode()">İptal (Esc)</button>
            </div>

            <!-- Vertical Action Toolbar on the Far Right -->
            <div class="hud-toolbar-v">
                <button class="hud-vbtn" id="btnTable" onclick="toggleTableHud()" data-tip="Öznitelik Tablosu (F6)" title="Öznitelik Tablosu (F6)">📊</button>
                <button class="hud-vbtn" id="btnFit" onclick="fitLayerBounds()" data-tip="Katman Sınırlarına Odaklan" title="Katman Sınırlarına Odaklan">🎯</button>
                
                <div class="hud-vdivider"></div>
                
                <button class="hud-vbtn" id="btnAddPoint" onclick="toggleDrawMode('point')" data-tip="Nokta Ekle (Haritaya Tıkla)" title="Nokta Ekle">📍+</button>
                <button class="hud-vbtn" id="btnAddPolygon" onclick="toggleDrawMode('polygon')" data-tip="Çokgen Ekle (Çiz & Çift Tıkla)" title="Çokgen Ekle">📐+</button>
                <button class="hud-vbtn hud-vbtn-del" id="btnDelete" onclick="deleteSelectedFeature()" data-tip="Seçili Geometriyi Sil" title="Seçili Geometriyi Sil">🗑️</button>
                
                <div class="hud-vdivider"></div>
                
                <button class="hud-vbtn" id="btnMeasure" onclick="toggleMeasure()" data-tip="Mesafe / Alan Ölçümü" title="Ölçüm">📏</button>
                <button class="hud-vbtn" id="btnCluster" onclick="toggleCluster()" data-tip="Nokta Kümeleme (Cluster)" title="Cluster">📍</button>
                
                <div class="hud-vdivider"></div>
                
                <div style="position: relative;">
                    <button class="hud-vbtn" id="btnBasemap" onclick="toggleBasemapFlyout()" data-tip="Altlık Harita Değiştir" title="Altlık Harita">🗺️</button>
                    <div class="hud-flyout" id="basemapFlyout">
                        <button class="hud-flyout-btn active" id="btnOsm" onclick="setBaseMap('osm')" title="OpenStreetMap">OSM</button>
                        <button class="hud-flyout-btn" id="btnSat" onclick="setBaseMap('sat')" title="Esri Uydu">Uydu</button>
                        <button class="hud-flyout-btn" id="btnTopo" onclick="setBaseMap('topo')" title="OpenTopoMap">Topo</button>
                        <button class="hud-flyout-btn" id="btnDark" onclick="setBaseMap('dark')" title="Karanlık Mod">Koyu</button>
                        <button class="hud-flyout-btn" id="btnNone" onclick="setBaseMap('none')" title="Boş Zemin">Yok</button>
                    </div>
                </div>
                
                <div style="position: relative;">
                    <button class="hud-vbtn" id="btnOpacity" onclick="toggleOpacityFlyout()" data-tip="Katman Opaklığı" title="Opaklık">👁️</button>
                    <div class="hud-flyout" id="opacityFlyout" style="align-items: center;">
                        <span style="font-size:10px; color:#aaa; margin-right:4px;">Opaklık:</span>
                        <input type="range" class="hud-slider" id="opacitySlider" min="10" max="100" value="85"/>
                        <span id="opacityVal" style="font-size:10px; color:#fff; min-width: 28px; margin-left:4px;">85%</span>
                    </div>
                </div>
            </div>

            <div class="hud-panel hud-coords" id="coordsPill">
                <span>Lat: 39.0000°</span><span>Lng: 35.0000°</span><span>Zoom: 5</span>
            </div>

            <script>
                var map = L.map('map', {{
                    preferCanvas: true,
                    zoomControl: true,
                    attributionControl: false
                }}).setView([39.0, 35.0], 5);

                L.control.scale({{ imperial: false, position: 'bottomleft' }}).addTo(map);

                // STRICTLY FREE BASE TILES (No API key, no watermark)
                var freeTiles = {{
                    osm: L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 19 }}),
                    sat: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{ maxZoom: 18 }}),
                    topo: L.tileLayer('https://{{s}}.tile.opentopomap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 17 }}),
                    dark: L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 19 }}),
                    none: null
                }};

                function applyTileFilter(type) {{
                    var tilePane = map.getPane('tilePane');
                    if (!tilePane) return;
                    if (type === 'dark') {{
                        tilePane.style.filter = 'invert(100%) hue-rotate(180deg) brightness(85%) contrast(90%)';
                    }} else {{
                        tilePane.style.filter = '';
                    }}
                }}

                var currentBase = '{theme}' === 'dark' ? 'dark' : 'osm';
                if (freeTiles[currentBase]) freeTiles[currentBase].addTo(map);
                applyTileFilter(currentBase);
                updateActiveBaseButton(currentBase);

                function setBaseMap(type) {{
                    if (freeTiles[currentBase]) map.removeLayer(freeTiles[currentBase]);
                    currentBase = type;
                    if (freeTiles[type]) freeTiles[type].addTo(map);
                    applyTileFilter(type);
                    bringVectorsToFront();
                    updateActiveBaseButton(type);
                }}

                function updateActiveBaseButton(type) {{
                    ['btnOsm', 'btnSat', 'btnTopo', 'btnDark', 'btnNone'].forEach(id => {{
                        var btn = document.getElementById(id);
                        if (btn) btn.classList.remove('active');
                    }});
                    var mapBtn = {{ osm: 'btnOsm', sat: 'btnSat', topo: 'btnTopo', dark: 'btnDark', none: 'btnNone' }}[type];
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
                var wmsLayers = {{}};

                function setupBridge() {{
                    if (typeof QWebChannel !== 'undefined' && typeof qt !== 'undefined' && qt.webChannelTransport) {{
                        new QWebChannel(qt.webChannelTransport, function(channel) {{
                            pyBridge = channel.objects.mapBridge;
                        }});
                    }} else {{
                        setTimeout(setupBridge, 100);
                    }}
                }}
                setupBridge();

                function toggleTableHud() {{
                    if (pyBridge && pyBridge.toggleTable) {{
                        pyBridge.toggleTable();
                    }}
                }}

                function setTableButtonActive(active) {{
                    var btn = document.getElementById('btnTable');
                    if (btn) {{
                        if (active) btn.classList.add('active');
                        else btn.classList.remove('active');
                    }}
                }}

                // --- WMS Layer Management ---
                function addWmsLayer(layerId, url, layers, format, transparent) {{
                    if (wmsLayers[layerId]) map.removeLayer(wmsLayers[layerId]);
                    wmsLayers[layerId] = L.tileLayer.wms(url, {{
                        layers: layers,
                        format: format || 'image/png',
                        transparent: transparent !== false,
                        maxZoom: 20
                    }}).addTo(map);
                    bringVectorsToFront();
                }}

                function removeWmsLayer(layerId) {{
                    if (wmsLayers[layerId]) {{
                        map.removeLayer(wmsLayers[layerId]);
                        delete wmsLayers[layerId];
                    }}
                }}

                function setWmsVisibility(layerId, visible) {{
                    if (wmsLayers[layerId]) {{
                        if (visible) map.addLayer(wmsLayers[layerId]);
                        else map.removeLayer(wmsLayers[layerId]);
                        bringVectorsToFront();
                    }}
                }}

                function bringVectorsToFront() {{
                    if (clusterGroup) clusterGroup.bringToFront();
                    else if (geojsonLayer) geojsonLayer.bringToFront();
                }}

                // --- Map Mouse Move & Coordinate Tracking ---
                map.on('mousemove', function(e) {{
                    document.getElementById('coordsPill').innerHTML = 
                        '<span>Lat: ' + e.latlng.lat.toFixed(4) + '°</span>' +
                        '<span>Lng: ' + e.latlng.lng.toFixed(4) + '°</span>' +
                        '<span>Zoom: ' + map.getZoom() + '</span>';
                }});

                // --- Flyout Controls ---
                function toggleBasemapFlyout() {{
                    var bFlyout = document.getElementById('basemapFlyout');
                    var oFlyout = document.getElementById('opacityFlyout');
                    if (oFlyout) oFlyout.classList.remove('open');
                    if (bFlyout) bFlyout.classList.toggle('open');
                }}

                function toggleOpacityFlyout() {{
                    var bFlyout = document.getElementById('basemapFlyout');
                    var oFlyout = document.getElementById('opacityFlyout');
                    if (bFlyout) bFlyout.classList.remove('open');
                    if (oFlyout) oFlyout.classList.toggle('open');
                }}

                function closeAllFlyouts() {{
                    var bFlyout = document.getElementById('basemapFlyout');
                    var oFlyout = document.getElementById('opacityFlyout');
                    if (bFlyout) bFlyout.classList.remove('open');
                    if (oFlyout) oFlyout.classList.remove('open');
                }}

                document.getElementById('opacitySlider').oninput = function(e) {{
                    currentOpacity = e.target.value / 100.0;
                    document.getElementById('opacityVal').textContent = e.target.value + '%';
                    if (geojsonLayer) {{
                        geojsonLayer.setStyle(function(feature) {{
                            return {{
                                fillOpacity: currentOpacity * 0.4,
                                opacity: currentOpacity
                            }};
                        }});
                    }}
                }};

                function toggleCluster() {{
                    useClustering = !useClustering;
                    var btn = document.getElementById('btnCluster');
                    if (btn) btn.classList.toggle('active', useClustering);
                    if (lastGeojsonData) {{
                        updateMap(lastGeojsonData);
                    }}
                }}

                // --- Geometry Addition & Drawing Modes ---
                var drawMode = null; // null | 'point' | 'polygon'
                var polyDrawPoints = [];
                var polyDrawMarkers = [];
                var polyDrawLine = null;
                var polyDrawPoly = null;
                var selectedFeatureIndex = -1;

                function toggleDrawMode(mode) {{
                    if (drawMode === mode) {{
                        cancelDrawMode();
                        return;
                    }}
                    cancelDrawMode();
                    if (measureActive) toggleMeasure();
                    closeAllFlyouts();
                    drawMode = mode;

                    var bPoint = document.getElementById('btnAddPoint');
                    var bPoly = document.getElementById('btnAddPolygon');
                    if (mode === 'point' && bPoint) bPoint.classList.add('active');
                    if (mode === 'polygon' && bPoly) bPoly.classList.add('active');

                    var banner = document.getElementById('drawBanner');
                    var bannerText = document.getElementById('drawBannerText');
                    if (mode === 'point') {{
                        bannerText.textContent = '📍 Haritaya tıklayarak yeni nokta ekleyin';
                        map.getContainer().style.cursor = 'crosshair';
                    }} else if (mode === 'polygon') {{
                        bannerText.textContent = '📐 Köşeleri tıklayın. Bitirmek için çift tıklayın';
                        map.getContainer().style.cursor = 'crosshair';
                        map.doubleClickZoom.disable();
                    }}
                    if (banner) banner.classList.add('active');
                }}

                function cancelDrawMode() {{
                    drawMode = null;
                    map.getContainer().style.cursor = '';
                    map.doubleClickZoom.enable();

                    var bPoint = document.getElementById('btnAddPoint');
                    var bPoly = document.getElementById('btnAddPolygon');
                    if (bPoint) bPoint.classList.remove('active');
                    if (bPoly) bPoly.classList.remove('active');

                    var banner = document.getElementById('drawBanner');
                    if (banner) banner.classList.remove('active');

                    clearPolyDraw();
                }}

                function clearPolyDraw() {{
                    polyDrawPoints = [];
                    polyDrawMarkers.forEach(function(m) {{ map.removeLayer(m); }});
                    polyDrawMarkers = [];
                    if (polyDrawLine) map.removeLayer(polyDrawLine);
                    if (polyDrawPoly) map.removeLayer(polyDrawPoly);
                    polyDrawLine = null;
                    polyDrawPoly = null;
                }}

                // --- Geometry Deletion ---
                function deleteFeature(idx) {{
                    if (map.closePopup) map.closePopup();
                    selectedFeatureIndex = -1;
                    updateDeleteButtonState();
                    if (pyBridge && pyBridge.onFeatureDeleted) {{
                        pyBridge.onFeatureDeleted(idx);
                    }}
                }}

                function deleteSelectedFeature() {{
                    if (selectedFeatureIndex >= 0) {{
                        deleteFeature(selectedFeatureIndex);
                    }} else {{
                        alert("Lütfen önce haritadan silmek istediğiniz geometriyi seçin.");
                    }}
                }}

                function updateDeleteButtonState() {{
                    var btn = document.getElementById('btnDelete');
                    if (!btn) return;
                    if (selectedFeatureIndex >= 0) {{
                        btn.classList.add('has-selection');
                        btn.setAttribute('data-tip', 'Seçili Geometriyi Sil (#' + selectedFeatureIndex + ')');
                    }} else {{
                        btn.classList.remove('has-selection');
                        btn.setAttribute('data-tip', 'Seçili Geometriyi Sil (Önce Geometri Seçin)');
                    }}
                }}

                // --- Measurement Ruler Tool ---
                var measureActive = false;
                var measurePoints = [];
                var measureMarkers = [];
                var measureLine = null;
                var measurePolygon = null;
                var measureTooltip = null;

                function toggleMeasure() {{
                    measureActive = !measureActive;
                    var btn = document.getElementById('btnMeasure');
                    if (btn) btn.classList.toggle('active', measureActive);
                    if (!measureActive) {{
                        clearMeasure();
                    }} else {{
                        cancelDrawMode();
                        closeAllFlyouts();
                    }}
                }}

                function clearMeasure() {{
                    measurePoints = [];
                    measureMarkers.forEach(function(m) {{ map.removeLayer(m); }});
                    measureMarkers = [];
                    if (measureLine) map.removeLayer(measureLine);
                    if (measurePolygon) map.removeLayer(measurePolygon);
                    if (measureTooltip) map.removeLayer(measureTooltip);
                    measureLine = null;
                    measurePolygon = null;
                    measureTooltip = null;
                }}

                // --- Map Click Handler ---
                map.on('click', function(e) {{
                    closeAllFlyouts();

                    if (measureActive) {{
                        measurePoints.push(e.latlng);
                        var m = L.circleMarker(e.latlng, {{ radius: 4, color: '#e74c3c', fillColor: '#fff', fillOpacity: 1 }}).addTo(map);
                        measureMarkers.push(m);

                        if (measurePoints.length > 1) {{
                            if (measureLine) map.removeLayer(measureLine);
                            measureLine = L.polyline(measurePoints, {{ color: '#e74c3c', weight: 2.5, dashArray: '5, 5' }}).addTo(map);

                            var totalDist = 0;
                            for (var i = 1; i < measurePoints.length; i++) {{
                                totalDist += measurePoints[i - 1].distanceTo(measurePoints[i]);
                            }}
                            var distText = totalDist > 1000 ? (totalDist / 1000).toFixed(2) + ' km' : totalDist.toFixed(1) + ' m';

                            if (measurePoints.length >= 3) {{
                                if (measurePolygon) map.removeLayer(measurePolygon);
                                measurePolygon = L.polygon(measurePoints, {{ color: '#e74c3c', fillOpacity: 0.15, weight: 1 }}).addTo(map);
                            }}

                            if (!measureTooltip) {{
                                measureTooltip = L.tooltip({{ permanent: true, className: 'measure-tooltip' }});
                            }}
                            measureTooltip.setLatLng(e.latlng).setContent('📏 ' + distText).addTo(map);
                        }}
                        return;
                    }}

                    if (drawMode === 'point') {{
                        var feat = {{
                            type: "Feature",
                            geometry: {{
                                type: "Point",
                                coordinates: [e.latlng.lng, e.latlng.lat]
                            }},
                            properties: {{}}
                        }};
                        cancelDrawMode();
                        if (pyBridge && pyBridge.onFeatureAdded) {{
                            pyBridge.onFeatureAdded(JSON.stringify(feat));
                        }}
                        return;
                    }}

                    if (drawMode === 'polygon') {{
                        polyDrawPoints.push(e.latlng);
                        var pm = L.circleMarker(e.latlng, {{
                            radius: 5,
                            color: '#0078d4',
                            fillColor: '#ffffff',
                            fillOpacity: 1,
                            weight: 2
                        }}).addTo(map);
                        polyDrawMarkers.push(pm);

                        if (polyDrawPoints.length > 1) {{
                            if (polyDrawLine) map.removeLayer(polyDrawLine);
                            polyDrawLine = L.polyline(polyDrawPoints, {{
                                color: '#0078d4',
                                weight: 2.5,
                                dashArray: '4, 4'
                            }}).addTo(map);
                        }}
                        if (polyDrawPoints.length >= 3) {{
                            if (polyDrawPoly) map.removeLayer(polyDrawPoly);
                            polyDrawPoly = L.polygon(polyDrawPoints, {{
                                color: '#0078d4',
                                weight: 1,
                                fillOpacity: 0.2
                            }}).addTo(map);
                        }}
                        return;
                    }}
                }});

                // --- Double Click Handler for Polygon Finish ---
                map.on('dblclick', function(e) {{
                    if (drawMode === 'polygon') {{
                        if (polyDrawPoints.length >= 3) {{
                            var coords = polyDrawPoints.map(function(p) {{ return [p.lng, p.lat]; }});
                            coords.push([coords[0][0], coords[0][1]]); // close polygon ring
                            var feat = {{
                                type: "Feature",
                                geometry: {{
                                    type: "Polygon",
                                    coordinates: [coords]
                                }},
                                properties: {{}}
                            }};
                            cancelDrawMode();
                            if (pyBridge && pyBridge.onFeatureAdded) {{
                                pyBridge.onFeatureAdded(JSON.stringify(feat));
                            }}
                        }} else {{
                            cancelDrawMode();
                        }}
                    }}
                }});

                // --- Keyboard Handlers ---
                document.addEventListener('keydown', function(e) {{
                    if (e.key === 'Escape') {{
                        if (drawMode) cancelDrawMode();
                        if (measureActive) toggleMeasure();
                        closeAllFlyouts();
                    }} else if (e.key === 'Delete' || e.key === 'Backspace') {{
                        if (selectedFeatureIndex >= 0 && !drawMode && !measureActive) {{
                            deleteSelectedFeature();
                        }}
                    }}
                }});

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
                        document.getElementById('statsPill').textContent = 'Mekansal Katman';
                        return;
                    }}

                    var featureCount = 0;
                    if (geojsonData.type === 'FeatureCollection' && geojsonData.features) {{
                        featureCount = geojsonData.features.length;
                    }} else if (geojsonData.type === 'Feature') {{
                        featureCount = 1;
                    }}

                    document.getElementById('statsPill').textContent = '📍 ' + featureCount.toLocaleString() + ' Özellik';

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
                            maxClusterRadius: 45,
                            spiderfyOnMaxZoom: true,
                            showCoverageOnHover: false
                        }});
                    }}

                    var featureIdx = 0;
                    geojsonLayer = L.geoJSON(geojsonData, {{
                        pointToLayer: function(feature, latlng) {{
                            var marker = L.circleMarker(latlng, {{
                                radius: 6,
                                fillColor: '#00a2ff',
                                color: '#ffffff',
                                weight: 1.5,
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

                            var title = (feature.properties && (feature.properties.city || feature.properties.name || feature.properties.NAME || feature.properties.title || feature.properties.id)) || ('Özellik #' + currentIdx);
                            if (featureCount <= 1000) {{
                                layer.bindTooltip(String(title), {{ sticky: true }});
                            }}

                            layer.on('click', function(e) {{
                                if (drawMode || measureActive) {{
                                    return; // Allow map click handler to draw or measure
                                }}
                                selectedFeatureIndex = currentIdx;
                                updateDeleteButtonState();

                                var props = feature.properties || {{}};
                                var gType = feature.geometry ? feature.geometry.type : 'Unknown';
                                var html = '<div class="prop-title"><span>Özellik #' + currentIdx + '</span><span>[' + gType + ']</span></div>';
                                html += '<table class="prop-table">';
                                var keys = Object.keys(props);
                                if (keys.length === 0) {{
                                    html += '<tr><td colspan="2"><i>Öznitelik yok</i></td></tr>';
                                }} else {{
                                    keys.forEach(function(k) {{
                                        var val = props[k];
                                        if (val === null || val === undefined) val = '<i>null</i>';
                                        html += '<tr><th>' + k + '</th><td>' + val + '</td></tr>';
                                    }});
                                }}
                                html += '</table>';
                                html += '<div style="margin-top: 8px; text-align: right; border-top: 1px solid rgba(255,255,255,0.12); padding-top: 6px;">';
                                html += '<button class="hud-popup-del-btn" onclick="deleteFeature(' + currentIdx + ')">🗑️ Bu Geometriyi Sil</button>';
                                html += '</div>';
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
                    selectedFeatureIndex = idx;
                    updateDeleteButtonState();
                    var layer = layerIndexMap[idx];
                    if (layer) {{
                        if (layer.getBounds && layer.getBounds().isValid()) {{
                            map.fitBounds(layer.getBounds(), {{ maxZoom: 16, padding: [40, 40] }});
                        }} else if (layer.getLatLng) {{
                            map.setView(layer.getLatLng(), Math.max(map.getZoom(), 13));
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

    def add_wms_layer(self, layer_id: str, url: str, layer_name: str, fmt: str = "image/png", transparent: bool = True):
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            esc_url = json.dumps(url)
            esc_layer = json.dumps(layer_name)
            esc_fmt = json.dumps(fmt)
            trans_str = "true" if transparent else "false"
            self.web_view.page().runJavaScript(f"addWmsLayer({esc_id}, {esc_url}, {esc_layer}, {esc_fmt}, {trans_str});")

    def remove_wms_layer(self, layer_id: str):
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            self.web_view.page().runJavaScript(f"removeWmsLayer({esc_id});")

    def set_wms_visibility(self, layer_id: str, visible: bool):
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            vis_str = "true" if visible else "false"
            self.web_view.page().runJavaScript(f"setWmsVisibility({esc_id}, {vis_str});")

    def set_theme_tiles(self, theme_name: str):
        if self._is_loaded:
            tile_key = 'dark' if theme_name == 'dark' else 'light'
            self.web_view.page().runJavaScript(f"setBaseMap('{tile_key}');")

    def set_table_active(self, active: bool):
        if self._is_loaded:
            act_str = "true" if active else "false"
            self.web_view.page().runJavaScript(f"setTableButtonActive({act_str});")


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