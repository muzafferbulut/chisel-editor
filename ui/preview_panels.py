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
    wmsDeleted = pyqtSignal(str)
    serviceAddRequested = pyqtSignal()
    activeLayerRequested = pyqtSignal(str)
    viewportChanged = pyqtSignal(float, float, float, float, int)
    selectionChanged = pyqtSignal(str)
    selectionDeleted = pyqtSignal(str)

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

    @pyqtSlot(str)
    def onWmsDeleted(self, layerId):
        self.wmsDeleted.emit(layerId)

    @pyqtSlot()
    def requestAddService(self):
        self.serviceAddRequested.emit()

    @pyqtSlot(str)
    def onActiveLayerRequested(self, layerId):
        self.activeLayerRequested.emit(layerId)

    @pyqtSlot(float, float, float, float, int)
    def onViewportChanged(self, minx, miny, maxx, maxy, zoom):
        self.viewportChanged.emit(minx, miny, maxx, maxy, zoom)

    @pyqtSlot(str)
    def onSelectionChanged(self, indicesJson):
        self.selectionChanged.emit(indicesJson)

    @pyqtSlot(str)
    def onSelectionDeleted(self, indicesJson):
        self.selectionDeleted.emit(indicesJson)


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
    wms_deleted = pyqtSignal(str)
    service_add_requested = pyqtSignal()
    active_layer_requested = pyqtSignal(str)
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
        self.bridge.featureAdded.connect(self.feature_added.emit)
        self.bridge.tableToggleRequested.connect(self.table_toggle_requested.emit)
        self.bridge.wmsDeleted.connect(self.wms_deleted.emit)
        self.bridge.serviceAddRequested.connect(self.service_add_requested.emit)
        self.bridge.activeLayerRequested.connect(self.active_layer_requested.emit)
        self.bridge.viewportChanged.connect(self.viewport_changed.emit)
        self.bridge.selectionChanged.connect(self._on_bridge_selection_changed)
        self.bridge.selectionDeleted.connect(self._on_bridge_selection_deleted)

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
                .hud-vbtn.disabled {{
                    opacity: 0.28 !important;
                    cursor: not-allowed !important;
                    background: rgba(255, 255, 255, 0.03) !important;
                    border-color: rgba(255, 255, 255, 0.08) !important;
                }}
                .hud-vbtn.disabled:hover {{
                    background: rgba(255, 255, 255, 0.05) !important;
                    border-color: rgba(231, 76, 60, 0.4) !important;
                    color: #888888 !important;
                }}
                .hud-banner.hud-banner-warn {{
                    background: rgba(192, 57, 43, 0.95) !important;
                    box-shadow: 0 4px 16px rgba(192, 57, 43, 0.4) !important;
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
                .hud-layers-flyout {{
                    position: absolute;
                    right: 38px;
                    top: 0;
                    display: none;
                    flex-direction: column;
                    background: rgba(24, 28, 34, 0.96);
                    backdrop-filter: blur(12px);
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 8px;
                    padding: 8px 10px;
                    gap: 6px;
                    box-shadow: 0 8px 24px rgba(0,0,0,0.5);
                    z-index: 1002;
                    min-width: 230px;
                    max-width: 280px;
                    color: #e0e0e0;
                    user-select: none;
                }}
                .hud-layers-flyout.open {{
                    display: flex;
                }}
                .hud-layers-header {{
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    font-size: 11px;
                    font-weight: 700;
                    color: #9cdcfe;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.12);
                    padding-bottom: 5px;
                    letter-spacing: 0.5px;
                }}
                .hud-layers-section-title {{
                    font-size: 10px;
                    font-weight: 600;
                    color: #858585;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    margin-top: 3px;
                }}
                .hud-layer-item {{
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    background: rgba(255, 255, 255, 0.05);
                    border: 1px solid rgba(255, 255, 255, 0.08);
                    border-radius: 4px;
                    padding: 4px 6px;
                    font-size: 11px;
                    gap: 6px;
                }}
                .hud-layer-item:hover {{
                    background: rgba(255, 255, 255, 0.1);
                }}
                .hud-layer-item.active-layer {{
                    background: rgba(0, 120, 212, 0.2) !important;
                    border-color: rgba(76, 194, 255, 0.45) !important;
                }}
                .hud-layer-color-dot {{
                    width: 9px;
                    height: 9px;
                    border-radius: 50%;
                    flex-shrink: 0;
                    display: inline-block;
                    box-shadow: 0 0 4px rgba(0,0,0,0.4);
                }}
                .hud-layer-active-badge {{
                    font-size: 10px;
                    background: rgba(0, 120, 212, 0.35);
                    color: #4cc2ff;
                    border: 1px solid #0078d4;
                    border-radius: 3px;
                    padding: 1px 5px;
                    font-weight: 600;
                    white-space: nowrap;
                    flex-shrink: 0;
                }}
                .hud-layer-switch-btn {{
                    background: rgba(255, 255, 255, 0.08);
                    border: 1px solid rgba(255, 255, 255, 0.15);
                    color: #bbb;
                    font-size: 10px;
                    padding: 1px 6px;
                    border-radius: 3px;
                    cursor: pointer;
                    transition: all 0.15s ease;
                    white-space: nowrap;
                    flex-shrink: 0;
                }}
                .hud-layer-switch-btn:hover {{
                    background: #0078d4;
                    border-color: #4cc2ff;
                    color: #ffffff;
                }}
                .hud-popup-switch-btn {{
                    background: #0078d4;
                    color: #fff;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: background 0.15s ease;
                }}
                .hud-popup-switch-btn:hover {{
                    background: #0086ea;
                }}
                .hud-layer-label {{
                    display: flex;
                    align-items: center;
                    gap: 6px;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                    flex: 1;
                    cursor: pointer;
                }}
                .hud-layer-btn-del {{
                    background: transparent;
                    border: none;
                    color: #ff6b6b;
                    cursor: pointer;
                    padding: 0 2px;
                    font-size: 12px;
                    border-radius: 3px;
                }}
                .hud-layer-btn-del:hover {{
                    background: rgba(231, 76, 60, 0.25);
                }}
                .hud-layers-add-btn {{
                    background: #0078d4;
                    border: 1px solid #4cc2ff;
                    color: #ffffff;
                    font-size: 10px;
                    font-weight: 600;
                    padding: 2px 7px;
                    border-radius: 3px;
                    cursor: pointer;
                    transition: all 0.15s ease;
                }}
                .hud-layers-add-btn:hover {{
                    background: #0086ea;
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
                .measure-tooltip {{
                    background: rgba(0,0,0,0.85);
                    color: #fff;
                    padding: 3px 6px;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: bold;
                    border: 1px solid #00a2ff;
                }}
                .hud-selection {{
                    background: rgba(30, 30, 30, 0.94);
                    border: 1px solid rgba(245, 158, 11, 0.7);
                    color: #fbbf24;
                    display: none;
                    align-items: center;
                    gap: 6px;
                    padding: 4px 8px;
                    font-weight: 600;
                    border-radius: 6px;
                    box-shadow: 0 4px 12px rgba(245, 158, 11, 0.2);
                }}
                .hud-selection-btn {{
                    background: rgba(255, 255, 255, 0.12);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    color: #f1f5f9;
                    border-radius: 3px;
                    padding: 2px 6px;
                    font-size: 10px;
                    cursor: pointer;
                    transition: all 0.15s ease;
                }}
                .hud-selection-btn:hover {{
                    background: #0078d4;
                    border-color: #4cc2ff;
                    color: #ffffff;
                }}
            </style>
        </head>
        <body>
            <div id="map"></div>

            <div style="position: absolute; top: 12px; left: 54px; display: flex; gap: 8px; z-index: 1000; align-items: center;">
                <div class="hud-panel hud-stats" id="statsPill" style="position: static;">Mekansal Katman</div>
                <div class="hud-panel hud-selection" id="selectionPill" style="position: static;">
                    <span id="selectionPillText">0 seçili</span>
                    <button class="hud-selection-btn" onclick="zoomToSelected()" title="Seçilenlere Yakınlaş">🔍 Odaklan</button>
                    <button class="hud-selection-btn" onclick="clearSelection()" title="Seçimi Temizle">✕ Temizle</button>
                </div>
            </div>

            <div class="hud-banner" id="drawBanner">
                <span id="drawBannerText">Haritaya tıklayarak nokta ekleyin</span>
                <button class="hud-banner-cancel" onclick="cancelBanner()">İptal (Esc)</button>
            </div>

            <!-- Vertical Action Toolbar on the Far Right -->
            <div class="hud-toolbar-v">
                <button class="hud-vbtn" id="btnTable" onclick="toggleTableHud()" data-tip="Öznitelik Tablosu (F6)" title="Öznitelik Tablosu (F6)">📊</button>
                <button class="hud-vbtn" id="btnFit" onclick="fitLayerBounds()" data-tip="Katman Sınırlarına Odaklan" title="Katman Sınırlarına Odaklan">🎯</button>
                
                <div class="hud-vdivider"></div>
                
                <button class="hud-vbtn active" id="btnSelectClick" onclick="setSelectTool('click')" data-tip="Nesne Seç (Tıkla / Ctrl+Çoklu)" title="Nesne Seç">👆</button>
                <button class="hud-vbtn" id="btnSelectBox" onclick="setSelectTool('box')" data-tip="Kutu ile Seç (Kare Çizerek Seç)" title="Kutu ile Seç">⬚</button>
                <button class="hud-vbtn disabled" id="btnZoomSel" onclick="zoomToSelected()" data-tip="Seçilenlere Yakınlaş" title="Seçilenlere Yakınlaş">🔍</button>
                <button class="hud-vbtn disabled" id="btnClearSel" onclick="clearSelection()" data-tip="Seçimi Temizle (Esc)" title="Seçimi Temizle">✖</button>
                
                <div class="hud-vdivider"></div>
                
                <button class="hud-vbtn" id="btnAddPoint" onclick="toggleDrawMode('point')" data-tip="Nokta Ekle (Haritaya Tıkla)" title="Nokta Ekle">📍+</button>
                <button class="hud-vbtn" id="btnAddLine" onclick="toggleDrawMode('line')" data-tip="Çizgi Ekle (Çiz & Çift Tıkla)" title="Çizgi Ekle">〰️+</button>
                <button class="hud-vbtn" id="btnAddPolygon" onclick="toggleDrawMode('polygon')" data-tip="Çokgen Ekle (Çiz & Çift Tıkla)" title="Çokgen Ekle">📐+</button>
                <button class="hud-vbtn hud-vbtn-del" id="btnDelete" onclick="deleteSelectedFeatures()" data-tip="Seçili Geometrileri Sil (Del)" title="Seçili Geometrileri Sil">🗑️</button>
                
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
                
                <div style="position: relative;">
                    <button class="hud-vbtn" id="btnLayers" onclick="toggleLayersFlyout()" data-tip="Katmanlar & Servisler" title="Katmanlar">🥞</button>
                    <div class="hud-layers-flyout" id="layersFlyout">
                        <div class="hud-layers-header">
                            <span>📑 KATMANLAR & SERVİSLER</span>
                            <button class="hud-layers-add-btn" onclick="requestAddService()" title="WMS Web Servisi Ekle">+ Servis</button>
                        </div>
                        <div class="hud-layers-section-title">Vektör Katman</div>
                        <div id="vectorLayerContainer">
                            <div style="color: #858585; font-style: italic; font-size: 11px; padding: 2px 0;">(Aktif vektör yok)</div>
                        </div>
                        <div class="hud-layers-section-title">Web Servisleri (WMS)</div>
                        <div id="wmsLayersContainer" style="display: flex; flex-direction: column; gap: 4px; max-height: 160px; overflow-y: auto;">
                            <div style="color: #858585; font-style: italic; font-size: 11px; padding: 2px 0;">Eklenmiş servis yok</div>
                        </div>
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
                var sharedCanvas = L.canvas({{ padding: 0.5 }});

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

                // --- Layer Panel & Flyout Controls ---
                var vectorLayers = {{}}; // layerId -> {{ id, name, count, geomType, color, visible, isActive, leafletLayer, indexMap, geojsonData }}
                var activeLayerId = null;
                var selectedFeatureLayerId = null;
                var wmsRegistry = {{}}; // layerId -> {{ id, title, url, layerName, visible }}

                // --- QGIS Selection State ---
                var selectMode = 'click'; // 'click' | 'box'
                var selectedIndices = new Set();
                var isBoxSelecting = false;
                var boxStartLatLng = null;
                var boxRectLayer = null;

                var LAYER_PALETTE = [
                    '#0078d4', // Blue
                    '#e67e22', // Amber
                    '#2ecc71', // Emerald
                    '#9b59b6', // Purple
                    '#e74c3c', // Red
                    '#1abc9c', // Teal
                    '#f39c12', // Orange
                    '#e84393', // Pink
                    '#00cec9', // Cyan
                    '#6c5ce7'  // Violet
                ];

                function toggleLayersFlyout() {{
                    var lFlyout = document.getElementById('layersFlyout');
                    var bFlyout = document.getElementById('basemapFlyout');
                    var oFlyout = document.getElementById('opacityFlyout');
                    if (bFlyout) bFlyout.classList.remove('open');
                    if (oFlyout) oFlyout.classList.remove('open');
                    var isOpen = false;
                    if (lFlyout) {{
                        isOpen = lFlyout.classList.toggle('open');
                        var btn = document.getElementById('btnLayers');
                        if (btn) btn.classList.toggle('active', isOpen);
                    }}
                    if (isOpen) renderLayersPanel();
                }}

                function toggleBasemapFlyout() {{
                    var bFlyout = document.getElementById('basemapFlyout');
                    var oFlyout = document.getElementById('opacityFlyout');
                    var lFlyout = document.getElementById('layersFlyout');
                    if (oFlyout) oFlyout.classList.remove('open');
                    if (lFlyout) lFlyout.classList.remove('open');
                    var btnL = document.getElementById('btnLayers');
                    if (btnL) btnL.classList.remove('active');
                    if (bFlyout) bFlyout.classList.toggle('open');
                }}

                function toggleOpacityFlyout() {{
                    var bFlyout = document.getElementById('basemapFlyout');
                    var oFlyout = document.getElementById('opacityFlyout');
                    var lFlyout = document.getElementById('layersFlyout');
                    if (bFlyout) bFlyout.classList.remove('open');
                    if (lFlyout) lFlyout.classList.remove('open');
                    var btnL = document.getElementById('btnLayers');
                    if (btnL) btnL.classList.remove('active');
                    if (oFlyout) oFlyout.classList.toggle('open');
                }}

                function closeAllFlyouts() {{
                    var bFlyout = document.getElementById('basemapFlyout');
                    var oFlyout = document.getElementById('opacityFlyout');
                    var lFlyout = document.getElementById('layersFlyout');
                    if (bFlyout) bFlyout.classList.remove('open');
                    if (oFlyout) oFlyout.classList.remove('open');
                    if (lFlyout) lFlyout.classList.remove('open');
                    var btnL = document.getElementById('btnLayers');
                    if (btnL) btnL.classList.remove('active');
                }}

                function setActiveVectorInfo(name, count) {{
                    if (activeLayerId && vectorLayers[activeLayerId]) {{
                        vectorLayers[activeLayerId].name = name;
                        vectorLayers[activeLayerId].count = count;
                    }}
                    renderLayersPanel();
                }}

                function toggleVectorVisibility(visible) {{
                    if (activeLayerId) {{
                        setVectorLayerVisibility(activeLayerId, visible);
                    }}
                }}

                function requestAddService() {{
                    if (pyBridge && pyBridge.requestAddService) {{
                        pyBridge.requestAddService();
                    }}
                }}

                function removeWms(layerId) {{
                    removeWmsLayer(layerId);
                    if (pyBridge && pyBridge.onWmsDeleted) {{
                        pyBridge.onWmsDeleted(layerId);
                    }}
                }}

                function toggleWmsVisibility(layerId, visible) {{
                    setWmsVisibility(layerId, visible);
                }}

                function renderLayersPanel() {{
                    var vContainer = document.getElementById('vectorLayerContainer');
                    if (vContainer) {{
                        var keys = Object.keys(vectorLayers);
                        if (keys.length === 0) {{
                            vContainer.innerHTML = '<div style="color: #858585; font-style: italic; font-size: 11px; padding: 2px 0;">(Açık katman yok)</div>';
                        }} else {{
                            var html = '';
                            keys.forEach(function(k) {{
                                var l = vectorLayers[k];
                                var chk = l.visible ? 'checked' : '';
                                var geomIcon = l.geomType === 'point' ? '📍' : (l.geomType === 'line' ? '〰️' : (l.geomType === 'polygon' ? '📐' : '🔶'));
                                var activeBadge = l.isActive 
                                    ? '<span class="hud-layer-active-badge" title="Aktif Düzenleme Katmanı">✏️ Aktif</span>'
                                    : '<button class="hud-layer-switch-btn" onclick="requestSetActiveLayer(\\x27' + l.id + '\\x27)" title="Aktif Düzenleme Katmanı Yap">Seç</button>';

                                html += 
                                    '<div class="hud-layer-item' + (l.isActive ? ' active-layer' : '') + '">' +
                                    '<label class="hud-layer-label" style="display:flex; align-items:center; gap:6px; flex:1; min-width:0;">' +
                                    '<input type="checkbox" ' + chk + ' onchange="setVectorLayerVisibility(\\x27' + l.id + '\\x27, this.checked)" title="Görünürlüğü Aç/Kapat"/>' +
                                    '<span class="hud-layer-color-dot" style="background:' + l.color + ';"></span>' +
                                    '<span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:11px; ' + (l.isActive ? 'font-weight:600; color:#4cc2ff;' : '') + '" title="' + l.name + '">' + geomIcon + ' ' + l.name + ' (' + l.count.toLocaleString() + ')</span>' +
                                    '</label>' +
                                    activeBadge +
                                    '</div>';
                            }});
                            vContainer.innerHTML = html;
                        }}
                    }}

                    var wContainer = document.getElementById('wmsLayersContainer');
                    if (wContainer) {{
                        var wkeys = Object.keys(wmsRegistry);
                        if (wkeys.length === 0) {{
                            wContainer.innerHTML = '<div style="color: #858585; font-style: italic; font-size: 11px; padding: 2px 0;">Eklenmiş servis yok</div>';
                        }} else {{
                            var whtml = '';
                            wkeys.forEach(function(k) {{
                                var layer = wmsRegistry[k];
                                var chk = layer.visible ? 'checked' : '';
                                var title = layer.title || layer.layerName;
                                whtml += 
                                    '<div class="hud-layer-item">' +
                                    '<label class="hud-layer-label">' +
                                    '<input type="checkbox" ' + chk + ' onchange="toggleWmsVisibility(\\x27' + layer.id + '\\x27, this.checked)"/>' +
                                    '<span title="' + title + '">🌐 ' + title + '</span>' +
                                    '</label>' +
                                    '<button class="hud-layer-btn-del" onclick="removeWms(\\x27' + layer.id + '\\x27)" title="Servisi Kaldır">🗑️</button>' +
                                    '</div>';
                            }});
                            wContainer.innerHTML = whtml;
                        }}
                    }}
                }}

                // --- WMS Layer Management ---
                function addWmsLayer(layerId, url, layers, format, transparent, title) {{
                    if (wmsLayers[layerId]) map.removeLayer(wmsLayers[layerId]);
                    wmsLayers[layerId] = L.tileLayer.wms(url, {{
                        layers: layers,
                        format: format || 'image/png',
                        transparent: transparent !== false,
                        maxZoom: 20
                    }}).addTo(map);
                    wmsRegistry[layerId] = {{
                        id: layerId,
                        title: title || layers,
                        url: url,
                        layerName: layers,
                        visible: true
                    }};
                    bringVectorsToFront();
                    renderLayersPanel();

                    var lFlyout = document.getElementById('layersFlyout');
                    var btnL = document.getElementById('btnLayers');
                    if (lFlyout && !lFlyout.classList.contains('open')) {{
                        lFlyout.classList.add('open');
                        if (btnL) btnL.classList.add('active');
                    }}
                }}

                function removeWmsLayer(layerId) {{
                    if (wmsLayers[layerId]) {{
                        map.removeLayer(wmsLayers[layerId]);
                        delete wmsLayers[layerId];
                    }}
                    if (wmsRegistry[layerId]) {{
                        delete wmsRegistry[layerId];
                    }}
                    renderLayersPanel();
                }}

                function setWmsVisibility(layerId, visible) {{
                    if (wmsRegistry[layerId]) {{
                        wmsRegistry[layerId].visible = visible;
                    }}
                    if (wmsLayers[layerId]) {{
                        if (visible) map.addLayer(wmsLayers[layerId]);
                        else map.removeLayer(wmsLayers[layerId]);
                        bringVectorsToFront();
                    }}
                    renderLayersPanel();
                }}

                function bringVectorsToFront() {{
                    if (clusterGroup) clusterGroup.bringToFront();
                    Object.keys(vectorLayers).forEach(function(k) {{
                        var vl = vectorLayers[k];
                        if (vl.leafletLayer && vl.visible) {{
                            vl.leafletLayer.bringToFront();
                        }}
                    }});
                }}

                // --- Map Mouse Move & Coordinate Tracking ---
                map.on('mousemove', function(e) {{
                    document.getElementById('coordsPill').innerHTML = 
                        '<span>Lat: ' + e.latlng.lat.toFixed(4) + '°</span>' +
                        '<span>Lng: ' + e.latlng.lng.toFixed(4) + '°</span>' +
                        '<span>Zoom: ' + map.getZoom() + '</span>';

                    if (isBoxSelecting && boxRectLayer && boxStartLatLng) {{
                        boxRectLayer.setBounds(L.latLngBounds(boxStartLatLng, e.latlng));
                    }}
                }});

                var viewportDebounceTimer = null;
                map.on('moveend', function() {{
                    if (viewportDebounceTimer) clearTimeout(viewportDebounceTimer);
                    viewportDebounceTimer = setTimeout(function() {{
                        if (pyBridge && pyBridge.onViewportChanged) {{
                            var b = map.getBounds();
                            var z = map.getZoom();
                            pyBridge.onViewportChanged(b.getWest(), b.getSouth(), b.getEast(), b.getNorth(), z);
                        }}
                    }}, 120);
                }});

                document.getElementById('opacitySlider').oninput = function(e) {{
                    currentOpacity = e.target.value / 100.0;
                    document.getElementById('opacityVal').textContent = e.target.value + '%';
                    Object.keys(vectorLayers).forEach(function(k) {{
                        var vl = vectorLayers[k];
                        if (vl.leafletLayer) {{
                            vl.leafletLayer.setStyle(function(feature) {{
                                var gtype = (feature.geometry && feature.geometry.type) || 'Polygon';
                                var isLine = gtype.indexOf('Line') !== -1;
                                return {{
                                    fillOpacity: isLine ? 0 : currentOpacity * 0.35,
                                    opacity: currentOpacity
                                }};
                            }});
                        }}
                    }});
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
                var activeLayerGeomType = 'any'; // 'point' | 'line' | 'polygon' | 'mixed' | 'any'
                var drawMode = null; // null | 'point' | 'line' | 'polygon'
                var polyDrawPoints = [];
                var polyDrawMarkers = [];
                var polyDrawLine = null;
                var polyDrawPoly = null;
                var selectedFeatureIndex = -1;
                var warnBannerTimer = null;

                function setLayerGeometryType(geomType) {{
                    activeLayerGeomType = (geomType || 'any').toLowerCase();
                    updateDrawButtonsUI();
                    if (drawMode && !isDrawModeAllowed(drawMode)) {{
                        cancelDrawMode();
                    }}
                }}

                function isDrawModeAllowed(mode) {{
                    if (activeLayerGeomType === 'any' || activeLayerGeomType === 'mixed') return true;
                    if (mode === 'point') return activeLayerGeomType === 'point';
                    if (mode === 'line') return activeLayerGeomType === 'line';
                    if (mode === 'polygon') return activeLayerGeomType === 'polygon';
                    return true;
                }}

                function getLayerTypeNameTr(type) {{
                    if (type === 'point') return 'Nokta';
                    if (type === 'line') return 'Çizgi';
                    if (type === 'polygon') return 'Çokgen';
                    return 'Karma';
                }}

                function getDrawModeNameTr(mode) {{
                    if (mode === 'point') return 'Nokta';
                    if (mode === 'line') return 'Çizgi';
                    if (mode === 'polygon') return 'Çokgen';
                    return mode;
                }}

                function updateDrawButtonsUI() {{
                    var bPoint = document.getElementById('btnAddPoint');
                    var bLine = document.getElementById('btnAddLine');
                    var bPoly = document.getElementById('btnAddPolygon');
                    var layerTr = getLayerTypeNameTr(activeLayerGeomType);

                    if (bPoint) {{
                        if (isDrawModeAllowed('point')) {{
                            bPoint.classList.remove('disabled');
                            bPoint.setAttribute('data-tip', 'Nokta Ekle (Haritaya Tıkla)');
                        }} else {{
                            bPoint.classList.add('disabled');
                            bPoint.setAttribute('data-tip', '⚠️ Bu katman [' + layerTr + '] tipindedir. Nokta eklenemez!');
                        }}
                    }}

                    if (bLine) {{
                        if (isDrawModeAllowed('line')) {{
                            bLine.classList.remove('disabled');
                            bLine.setAttribute('data-tip', 'Çizgi Ekle (Çiz & Çift Tıkla)');
                        }} else {{
                            bLine.classList.add('disabled');
                            bLine.setAttribute('data-tip', '⚠️ Bu katman [' + layerTr + '] tipindedir. Çizgi eklenemez!');
                        }}
                    }}

                    if (bPoly) {{
                        if (isDrawModeAllowed('polygon')) {{
                            bPoly.classList.remove('disabled');
                            bPoly.setAttribute('data-tip', 'Çokgen Ekle (Çiz & Çift Tıkla)');
                        }} else {{
                            bPoly.classList.add('disabled');
                            bPoly.setAttribute('data-tip', '⚠️ Bu katman [' + layerTr + '] tipindedir. Çokgen eklenemez!');
                        }}
                    }}
                }}

                function showWarningBanner(msg, duration) {{
                    var banner = document.getElementById('drawBanner');
                    var bannerText = document.getElementById('drawBannerText');
                    if (!banner || !bannerText) return;
                    if (warnBannerTimer) clearTimeout(warnBannerTimer);

                    bannerText.textContent = msg;
                    banner.classList.add('active', 'hud-banner-warn');
                    warnBannerTimer = setTimeout(function() {{
                        banner.classList.remove('active', 'hud-banner-warn');
                    }}, duration || 3500);
                }}

                function toggleDrawMode(mode) {{
                    if (drawMode === mode) {{
                        cancelDrawMode();
                        return;
                    }}

                    if (!isDrawModeAllowed(mode)) {{
                        var layerName = getLayerTypeNameTr(activeLayerGeomType);
                        var targetName = getDrawModeNameTr(mode);
                        showWarningBanner('⚠️ Bu katman [' + layerName + '] tipindedir. ' + targetName + ' eklenemez!');
                        return;
                    }}

                    cancelDrawMode();
                    if (selectMode === 'box') setSelectTool('click');
                    if (measureActive) toggleMeasure();
                    closeAllFlyouts();
                    drawMode = mode;

                    var bPoint = document.getElementById('btnAddPoint');
                    var bLine = document.getElementById('btnAddLine');
                    var bPoly = document.getElementById('btnAddPolygon');
                    if (mode === 'point' && bPoint) bPoint.classList.add('active');
                    if (mode === 'line' && bLine) bLine.classList.add('active');
                    if (mode === 'polygon' && bPoly) bPoly.classList.add('active');

                    var banner = document.getElementById('drawBanner');
                    var bannerText = document.getElementById('drawBannerText');
                    if (banner) banner.classList.remove('hud-banner-warn');
                    if (mode === 'point') {{
                        bannerText.textContent = '📍 Haritaya tıklayarak yeni nokta ekleyin';
                        map.getContainer().style.cursor = 'crosshair';
                    }} else if (mode === 'line') {{
                        bannerText.textContent = '〰️ Noktaları tıklayın. Çizgiyi bitirmek için çift tıklayın';
                        map.getContainer().style.cursor = 'crosshair';
                        map.doubleClickZoom.disable();
                    }} else if (mode === 'polygon') {{
                        bannerText.textContent = '📐 Köşeleri tıklayın. Alanı bitirmek için çift tıklayın';
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
                    var bLine = document.getElementById('btnAddLine');
                    var bPoly = document.getElementById('btnAddPolygon');
                    if (bPoint) bPoint.classList.remove('active');
                    if (bLine) bLine.classList.remove('active');
                    if (bPoly) bPoly.classList.remove('active');

                    var banner = document.getElementById('drawBanner');
                    if (banner && selectMode !== 'box') banner.classList.remove('active', 'hud-banner-warn');

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

                // --- QGIS Selection State & Tools ---
                function setSelectTool(mode) {{
                    if (drawMode) cancelDrawMode();
                    if (measureActive) toggleMeasure();
                    closeAllFlyouts();

                    selectMode = mode;
                    var bClick = document.getElementById('btnSelectClick');
                    var bBox = document.getElementById('btnSelectBox');
                    if (bClick) bClick.classList.toggle('active', mode === 'click');
                    if (bBox) bBox.classList.toggle('active', mode === 'box');

                    var banner = document.getElementById('drawBanner');
                    var bannerText = document.getElementById('drawBannerText');

                    if (mode === 'box') {{
                        map.dragging.disable();
                        map.getContainer().style.cursor = 'crosshair';
                        if (banner && bannerText) {{
                            bannerText.textContent = '⬚ Kutu ile Seçim: Dikdörtgen çizerek nesneleri seçin (Ctrl/Shift: Mevcut seçime ekler)';
                            banner.classList.add('active');
                            banner.classList.remove('hud-banner-warn');
                        }}
                    }} else {{
                        map.dragging.enable();
                        map.getContainer().style.cursor = '';
                        if (banner && !drawMode) {{
                            banner.classList.remove('active');
                        }}
                    }}
                }}

                function cancelBanner() {{
                    if (drawMode) cancelDrawMode();
                    if (selectMode === 'box') setSelectTool('click');
                }}

                function updateSelectionUI() {{
                    var count = selectedIndices.size;
                    var pill = document.getElementById('selectionPill');
                    var pillText = document.getElementById('selectionPillText');
                    var btnZoom = document.getElementById('btnZoomSel');
                    var btnClear = document.getElementById('btnClearSel');
                    var btnDel = document.getElementById('btnDelete');

                    if (count > 0) {{
                        if (pill) {{
                            pill.style.display = 'flex';
                            if (pillText) pillText.textContent = count + ' seçili';
                        }}
                        if (btnZoom) btnZoom.classList.remove('disabled');
                        if (btnClear) btnClear.classList.remove('disabled');
                        if (btnDel) {{
                            btnDel.classList.add('has-selection');
                            btnDel.setAttribute('data-tip', 'Seçili ' + count + ' Geometriyi Sil (Del)');
                        }}
                    }} else {{
                        if (pill) pill.style.display = 'none';
                        if (btnZoom) btnZoom.classList.add('disabled');
                        if (btnClear) btnClear.classList.add('disabled');
                        if (btnDel) {{
                            btnDel.classList.remove('has-selection');
                            btnDel.setAttribute('data-tip', 'Seçili Geometrileri Sil (Önce Geometri Seçin)');
                        }}
                    }}
                }}

                function notifySelectionChanged() {{
                    updateSelectionUI();
                    if (pyBridge && pyBridge.onSelectionChanged) {{
                        pyBridge.onSelectionChanged(JSON.stringify(Array.from(selectedIndices)));
                    }}
                }}

                function applyStyleToLayerItem(l, idx, lObj) {{
                    var isSelected = selectedIndices.has(idx);
                    var baseColor = lObj.color;
                    if (l.setStyle) {{
                        var gtype = (l.feature && l.feature.geometry && l.feature.geometry.type) || 'Polygon';
                        var isLine = gtype.indexOf('Line') !== -1;
                        if (isSelected) {{
                            l.setStyle({{
                                color: isLine ? '#eab308' : '#b45309',
                                weight: isLine ? 4.5 : 3,
                                opacity: 1.0,
                                fillColor: '#ffff00',
                                fillOpacity: isLine ? 0 : 0.65
                            }});
                        }} else {{
                            l.setStyle({{
                                color: baseColor,
                                weight: isLine ? 2.5 : 2,
                                opacity: currentOpacity,
                                fillColor: baseColor,
                                fillOpacity: isLine ? 0 : currentOpacity * 0.35
                            }});
                        }}
                    }}
                    if (l.setRadius) {{
                        l.setRadius(isSelected ? 7.5 : 5);
                        l.setStyle({{
                            fillColor: isSelected ? '#ffff00' : baseColor,
                            color: isSelected ? '#b45309' : '#ffffff',
                            weight: isSelected ? 2.5 : 1.2,
                            opacity: 1.0,
                            fillOpacity: isSelected ? 0.95 : currentOpacity * 0.9
                        }});
                    }}
                }}

                function refreshLayerStyles(layerId) {{
                    var lId = layerId || activeLayerId;
                    if (!lId || !vectorLayers[lId]) return;
                    var lObj = vectorLayers[lId];
                    if (!lObj.leafletLayer) return;

                    lObj.leafletLayer.eachLayer(function(l) {{
                        var idx = l._featureIdx;
                        if (idx === undefined && l.eachLayer) {{
                            l.eachLayer(function(child) {{
                                if (child._featureIdx !== undefined) {{
                                    applyStyleToLayerItem(child, child._featureIdx, lObj);
                                }}
                            }});
                        }} else if (idx !== undefined) {{
                            applyStyleToLayerItem(l, idx, lObj);
                        }}
                    }});
                    updateSelectionUI();
                }}

                function setSelectedFeatures(indices, layerId) {{
                    var lId = layerId || activeLayerId;
                    if (!lId || !vectorLayers[lId]) return;
                    selectedIndices.clear();
                    if (Array.isArray(indices)) {{
                        indices.forEach(function(i) {{
                            selectedIndices.add(i);
                        }});
                    }}
                    selectedFeatureIndex = selectedIndices.size === 1 ? indices[0] : -1;
                    selectedFeatureLayerId = lId;
                    refreshLayerStyles(lId);
                }}

                function clearSelection() {{
                    if (selectedIndices.size === 0) return;
                    selectedIndices.clear();
                    selectedFeatureIndex = -1;
                    refreshLayerStyles(activeLayerId);
                    if (map.closePopup) map.closePopup();
                    notifySelectionChanged();
                }}

                function zoomToSelected() {{
                    if (selectedIndices.size === 0) return;
                    var lObj = vectorLayers[activeLayerId];
                    if (!lObj) return;

                    var b = L.latLngBounds();
                    var hasAny = false;
                    selectedIndices.forEach(function(idx) {{
                        var l = lObj.indexMap[idx];
                        if (l) {{
                            if (l.getBounds && l.getBounds().isValid()) {{
                                b.extend(l.getBounds());
                                hasAny = true;
                            }} else if (l.getLatLng) {{
                                b.extend(l.getLatLng());
                                hasAny = true;
                            }}
                        }}
                    }});

                    if (hasAny && b.isValid()) {{
                        map.fitBounds(b, {{ maxZoom: 16, padding: [40, 40] }});
                    }}
                }}

                function deleteSelectedFeatures() {{
                    if (selectedIndices.size === 0) {{
                        showWarningBanner("Silinecek seçili nesne yok!");
                        return;
                    }}
                    var arr = Array.from(selectedIndices);
                    if (map.closePopup) map.closePopup();
                    if (pyBridge && pyBridge.onSelectionDeleted) {{
                        pyBridge.onSelectionDeleted(JSON.stringify(arr));
                    }}
                    selectedIndices.clear();
                    selectedFeatureIndex = -1;
                    refreshLayerStyles(activeLayerId);
                }}

                function deleteFeature(idx) {{
                    selectedIndices.clear();
                    selectedIndices.add(idx);
                    deleteSelectedFeatures();
                }}

                function deleteSelectedFeature() {{
                    deleteSelectedFeatures();
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
                        if (selectMode === 'box') setSelectTool('click');
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

                // --- Box Drag Selection Mouse Handlers ---
                map.on('mousedown', function(e) {{
                    if (selectMode !== 'box' || drawMode || measureActive) return;
                    if (e.originalEvent.button !== 0) return;
                    isBoxSelecting = true;
                    boxStartLatLng = e.latlng;
                    if (boxRectLayer) {{
                        map.removeLayer(boxRectLayer);
                        boxRectLayer = null;
                    }}
                    boxRectLayer = L.rectangle([boxStartLatLng, boxStartLatLng], {{
                        color: '#f59e0b',
                        weight: 2,
                        dashArray: '5, 5',
                        fillColor: '#ffff00',
                        fillOpacity: 0.18
                    }}).addTo(map);
                }});

                map.on('mouseup', function(e) {{
                    if (!isBoxSelecting) return;
                    isBoxSelecting = false;
                    if (!boxRectLayer || !boxStartLatLng) return;

                    var boxBounds = boxRectLayer.getBounds();
                    map.removeLayer(boxRectLayer);
                    boxRectLayer = null;

                    var p1 = map.latLngToContainerPoint(boxStartLatLng);
                    var p2 = map.latLngToContainerPoint(e.latlng);
                    var dist = Math.hypot(p1.x - p2.x, p1.y - p2.y);
                    if (dist < 4) return;

                    var lObj = vectorLayers[activeLayerId];
                    if (!lObj || !lObj.leafletLayer) return;

                    var isMulti = e.originalEvent && (e.originalEvent.ctrlKey || e.originalEvent.shiftKey);
                    if (!isMulti) {{
                        selectedIndices.clear();
                    }}

                    lObj.leafletLayer.eachLayer(function(l) {{
                        var idx = l._featureIdx;
                        if (idx === undefined) return;
                        var hit = false;
                        if (l.getBounds && l.getBounds().isValid()) {{
                            hit = boxBounds.intersects(l.getBounds());
                        }} else if (l.getLatLng) {{
                            hit = boxBounds.contains(l.getLatLng());
                        }}
                        if (hit) {{
                            selectedIndices.add(idx);
                        }}
                    }});

                    refreshLayerStyles(activeLayerId);
                    notifySelectionChanged();
                }});

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

                    if (drawMode === 'line') {{
                        polyDrawPoints.push(e.latlng);
                        var lm = L.circleMarker(e.latlng, {{
                            radius: 4.5,
                            color: '#ff8800',
                            fillColor: '#ffffff',
                            fillOpacity: 1,
                            weight: 2
                        }}).addTo(map);
                        polyDrawMarkers.push(lm);

                        if (polyDrawPoints.length > 1) {{
                            if (polyDrawLine) map.removeLayer(polyDrawLine);
                            polyDrawLine = L.polyline(polyDrawPoints, {{
                                color: '#ff8800',
                                weight: 3
                            }}).addTo(map);
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

                    // Empty map click in click select mode -> clear selection
                    if (!e.originalEvent._layerClicked && selectMode === 'click') {{
                        if (selectedIndices.size > 0) {{
                            clearSelection();
                        }}
                    }}
                }});

                // --- Double Click Handler for Finish Drawing ---
                map.on('dblclick', function(e) {{
                    if (drawMode === 'line') {{
                        if (polyDrawPoints.length >= 2) {{
                            var lineCoords = polyDrawPoints.map(function(p) {{ return [p.lng, p.lat]; }});
                            var lineFeat = {{
                                type: "Feature",
                                geometry: {{
                                    type: "LineString",
                                    coordinates: lineCoords
                                }},
                                properties: {{}}
                            }};
                            cancelDrawMode();
                            if (pyBridge && pyBridge.onFeatureAdded) {{
                                pyBridge.onFeatureAdded(JSON.stringify(lineFeat));
                            }}
                        }} else {{
                            cancelDrawMode();
                        }}
                        return;
                    }}
                    if (drawMode === 'polygon') {{
                        if (polyDrawPoints.length >= 3) {{
                            var coords = polyDrawPoints.map(function(p) {{ return [p.lng, p.lat]; }});
                            coords.push([coords[0][0], coords[0][1]]);
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
                        return;
                    }}
                }});

                // --- Keyboard Handlers ---
                document.addEventListener('keydown', function(e) {{
                    if (e.key === 'Escape') {{
                        if (isBoxSelecting && boxRectLayer) {{
                            map.removeLayer(boxRectLayer);
                            boxRectLayer = null;
                            isBoxSelecting = false;
                        }}
                        if (selectMode === 'box') setSelectTool('click');
                        if (drawMode) cancelDrawMode();
                        if (measureActive) toggleMeasure();
                        closeAllFlyouts();
                    }} else if (e.key === 'Delete' || e.key === 'Backspace') {{
                        if (selectedIndices.size > 0 && !drawMode && !measureActive) {{
                            deleteSelectedFeatures();
                        }}
                    }}
                }});

                function handleFeatureClick(currentIdx, layerId, feature, layer, e) {{
                    if (drawMode || measureActive || selectMode === 'box') return;

                    var isMulti = e.originalEvent && (e.originalEvent.ctrlKey || e.originalEvent.shiftKey);

                    if (isMulti) {{
                        if (selectedIndices.has(currentIdx)) {{
                            selectedIndices.delete(currentIdx);
                        }} else {{
                            selectedIndices.add(currentIdx);
                        }}
                    }} else {{
                        selectedIndices.clear();
                        selectedIndices.add(currentIdx);
                    }}

                    selectedFeatureIndex = selectedIndices.size === 1 ? currentIdx : -1;
                    selectedFeatureLayerId = layerId;
                    refreshLayerStyles(layerId);
                    notifySelectionChanged();

                    if (pyBridge && layerId === activeLayerId && selectedIndices.size === 1) {{
                        pyBridge.onFeatureClicked(currentIdx);
                    }}
                }}

                var lastGeojsonData = null;
                var hasFittedInitially = false;

                function createLeafletLayer(layerId, name, geojsonData, color) {{
                    var featureIdx = 0;
                    var indexMap = {{}};

                    var lLayer = L.geoJSON(geojsonData, {{
                        renderer: sharedCanvas,
                        smoothFactor: 1.0,
                        pointToLayer: function(feature, latlng) {{
                            return L.circleMarker(latlng, {{
                                renderer: sharedCanvas,
                                radius: 5,
                                fillColor: color,
                                color: '#ffffff',
                                weight: 1.2,
                                opacity: currentOpacity,
                                fillOpacity: currentOpacity * 0.9
                            }});
                        }},
                        style: function(feature) {{
                            var gtype = (feature.geometry && feature.geometry.type) || 'Polygon';
                            var isLine = gtype.indexOf('Line') !== -1;
                            return {{
                                renderer: sharedCanvas,
                                color: color,
                                weight: isLine ? 2.5 : 2,
                                opacity: currentOpacity,
                                fillColor: color,
                                fillOpacity: isLine ? 0 : currentOpacity * 0.35
                            }};
                        }},
                        onEachFeature: function(feature, layer) {{
                            var currentIdx = featureIdx++;
                            indexMap[currentIdx] = layer;
                            layer._featureIdx = currentIdx;
                            layer._layerId = layerId;

                            if (layer.eachLayer) {{
                                layer.eachLayer(function(child) {{
                                    child._featureIdx = currentIdx;
                                    child._layerId = layerId;
                                    child.on('click', function(e) {{
                                        e.originalEvent._layerClicked = true;
                                        handleFeatureClick(currentIdx, layerId, feature, child, e);
                                    }});
                                }});
                            }}

                            layer.on('click', function(e) {{
                                e.originalEvent._layerClicked = true;
                                handleFeatureClick(currentIdx, layerId, feature, layer, e);
                            }});
                        }}
                    }});

                    return {{ leafletLayer: lLayer, indexMap: indexMap }};
                }}

                function setVectorLayer(layerId, name, geojsonData, isActive, geomType, color, fitBounds) {{
                    if (!layerId) layerId = 'default';
                    name = name || 'Mekansal Katman';

                    var prevVisible = true;
                    var assignedColor = color;
                    if (vectorLayers[layerId]) {{
                        prevVisible = vectorLayers[layerId].visible;
                        if (!assignedColor) assignedColor = vectorLayers[layerId].color;
                        if (vectorLayers[layerId].leafletLayer) {{
                            map.removeLayer(vectorLayers[layerId].leafletLayer);
                        }}
                    }} else {{
                        if (!assignedColor) {{
                            var cnt = Object.keys(vectorLayers).length;
                            assignedColor = LAYER_PALETTE[cnt % LAYER_PALETTE.length];
                        }}
                    }}

                    var featureCount = 0;
                    if (geojsonData && geojsonData.type === 'FeatureCollection' && geojsonData.features) {{
                        featureCount = geojsonData.features.length;
                    }} else if (geojsonData && geojsonData.type === 'Feature') {{
                        featureCount = 1;
                    }}

                    var detectedGeom = geomType;
                    if (!detectedGeom || detectedGeom === 'any') {{
                        if (geojsonData && geojsonData.features && geojsonData.features.length > 0) {{
                            var dt = {{}};
                            for (var di = 0; di < Math.min(geojsonData.features.length, 100); di++) {{
                                var fg = geojsonData.features[di].geometry;
                                if (fg && fg.type) {{
                                    var lt = fg.type.toLowerCase();
                                    if (lt.indexOf('point') !== -1) dt['point'] = true;
                                    else if (lt.indexOf('line') !== -1) dt['line'] = true;
                                    else if (lt.indexOf('poly') !== -1) dt['polygon'] = true;
                                }}
                            }}
                            var dkeys = Object.keys(dt);
                            detectedGeom = dkeys.length === 1 ? dkeys[0] : (dkeys.length > 1 ? 'mixed' : 'any');
                        }} else {{
                            detectedGeom = 'any';
                        }}
                    }}

                    var res = createLeafletLayer(layerId, name, geojsonData, assignedColor);
                    var lGeojson = res.leafletLayer;
                    var lIndexMap = res.indexMap;

                    if (prevVisible) {{
                        map.addLayer(lGeojson);
                    }}

                    vectorLayers[layerId] = {{
                        id: layerId,
                        name: name,
                        count: featureCount,
                        geomType: detectedGeom,
                        color: assignedColor,
                        visible: prevVisible,
                        isActive: !!isActive,
                        leafletLayer: lGeojson,
                        geojsonData: geojsonData,
                        indexMap: lIndexMap
                    }};

                    if (isActive) {{
                        setActiveVectorLayer(layerId, detectedGeom);
                    }} else {{
                        renderLayersPanel();
                    }}

                    if (fitBounds === true) {{
                        fitLayerBounds(layerId);
                    }}
                }}

                function updateVectorLayerData(layerId, name, geojsonData, geomType) {{
                    if (!layerId || !vectorLayers[layerId]) return;
                    var layerObj = vectorLayers[layerId];
                    if (layerObj.leafletLayer) {{
                        map.removeLayer(layerObj.leafletLayer);
                    }}
                    var res = createLeafletLayer(layerId, name || layerObj.name, geojsonData, layerObj.color);
                    layerObj.leafletLayer = res.leafletLayer;
                    layerObj.indexMap = res.indexMap;
                    layerObj.geojsonData = geojsonData;
                    if (geomType && geomType !== 'any') {{
                        layerObj.geomType = geomType;
                    }}
                    if (layerObj.visible) {{
                        map.addLayer(layerObj.leafletLayer);
                        if (layerObj.isActive) {{
                            layerObj.leafletLayer.bringToFront();
                        }}
                    }}
                }}

                function setActiveVectorLayer(layerId, geomType) {{
                    activeLayerId = layerId;
                    Object.keys(vectorLayers).forEach(function(k) {{
                        vectorLayers[k].isActive = (k === layerId);
                    }});

                    var activeObj = vectorLayers[layerId];
                    if (activeObj) {{
                        document.getElementById('statsPill').innerHTML = 
                            '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + activeObj.color + ';margin-right:5px;"></span>' +
                            activeObj.name + ' (' + activeObj.count.toLocaleString() + ')';
                        setLayerGeometryType(geomType || activeObj.geomType);
                        if (activeObj.leafletLayer && activeObj.visible) {{
                            activeObj.leafletLayer.bringToFront();
                        }}
                    }} else {{
                        document.getElementById('statsPill').textContent = 'Mekansal Katman';
                        setLayerGeometryType('any');
                    }}

                    selectedFeatureIndex = -1;
                    selectedIndices.clear();
                    updateSelectionUI();
                    renderLayersPanel();
                }}

                function setVectorLayerVisibility(layerId, visible) {{
                    if (vectorLayers[layerId]) {{
                        vectorLayers[layerId].visible = visible;
                        if (vectorLayers[layerId].leafletLayer) {{
                            if (visible) {{
                                map.addLayer(vectorLayers[layerId].leafletLayer);
                                vectorLayers[layerId].leafletLayer.bringToFront();
                            }} else {{
                                map.removeLayer(vectorLayers[layerId].leafletLayer);
                            }}
                        }}
                    }}
                    renderLayersPanel();
                }}

                function removeVectorLayer(layerId) {{
                    if (vectorLayers[layerId]) {{
                        if (vectorLayers[layerId].leafletLayer) {{
                            map.removeLayer(vectorLayers[layerId].leafletLayer);
                        }}
                        delete vectorLayers[layerId];
                    }}
                    if (activeLayerId === layerId) {{
                        var remaining = Object.keys(vectorLayers);
                        if (remaining.length > 0) {{
                            setActiveVectorLayer(remaining[0]);
                        }} else {{
                            activeLayerId = null;
                            document.getElementById('statsPill').textContent = 'Mekansal Katman';
                            setLayerGeometryType('any');
                        }}
                    }}
                    renderLayersPanel();
                }}

                function clearAllVectorLayers() {{
                    Object.keys(vectorLayers).forEach(function(k) {{
                        if (vectorLayers[k].leafletLayer) {{
                            map.removeLayer(vectorLayers[k].leafletLayer);
                        }}
                    }});
                    vectorLayers = {{}};
                    activeLayerId = null;
                    document.getElementById('statsPill').textContent = 'Mekansal Katman';
                    setLayerGeometryType('any');
                    renderLayersPanel();
                }}

                function updateLayerName(layerId, name) {{
                    if (vectorLayers[layerId]) {{
                        vectorLayers[layerId].name = name;
                        if (layerId === activeLayerId) {{
                            var l = vectorLayers[layerId];
                            document.getElementById('statsPill').innerHTML = 
                                '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + l.color + ';margin-right:5px;"></span>' +
                                name + ' (' + l.count.toLocaleString() + ')';
                        }}
                        renderLayersPanel();
                    }}
                }}

                function requestSetActiveLayer(layerId) {{
                    setActiveVectorLayer(layerId);
                    if (pyBridge && pyBridge.onActiveLayerRequested) {{
                        pyBridge.onActiveLayerRequested(layerId);
                    }}
                }}

                function updateMap(geojsonData, shouldFit) {{
                    if (!geojsonData) {{
                        if (activeLayerId) {{
                            removeVectorLayer(activeLayerId);
                        }} else {{
                            clearAllVectorLayers();
                        }}
                        return;
                    }}
                    var currentId = activeLayerId || 'default';
                    var currentName = (vectorLayers[currentId] && vectorLayers[currentId].name) || 'Mekansal Katman';
                    setVectorLayer(currentId, currentName, geojsonData, true, activeLayerGeomType, null, shouldFit);
                }}

                function fitLayerBounds(layerId) {{
                    var doFit = function() {{
                        if (map.invalidateSize) map.invalidateSize();
                        var targetLayer = (layerId && vectorLayers[layerId]) ? vectorLayers[layerId] : (activeLayerId && vectorLayers[activeLayerId] ? vectorLayers[activeLayerId] : null);
                        if (targetLayer && targetLayer.leafletLayer && targetLayer.leafletLayer.getBounds) {{
                            var b = targetLayer.leafletLayer.getBounds();
                            if (b && b.isValid()) {{
                                map.fitBounds(b, {{ padding: [40, 40], maxZoom: 16 }});
                                return;
                            }}
                        }}
                        var allBounds = L.latLngBounds();
                        var hasValid = false;
                        Object.keys(vectorLayers).forEach(function(k) {{
                            var l = vectorLayers[k];
                            if (l.visible && l.leafletLayer && l.leafletLayer.getBounds) {{
                                var lb = l.leafletLayer.getBounds();
                                if (lb && lb.isValid()) {{
                                    allBounds.extend(lb);
                                    hasValid = true;
                                }}
                            }}
                        }});
                        if (hasValid && allBounds.isValid()) {{
                            map.fitBounds(allBounds, {{ padding: [40, 40], maxZoom: 16 }});
                        }}
                    }};
                    doFit();
                    setTimeout(doFit, 80);
                    setTimeout(doFit, 250);
                }}

                function highlightFeature(idx, layerId) {{
                    var lId = layerId || activeLayerId;
                    if (!lId || !vectorLayers[lId]) return;
                    var layerObj = vectorLayers[lId];
                    selectedIndices.clear();
                    selectedIndices.add(idx);
                    selectedFeatureIndex = idx;
                    selectedFeatureLayerId = lId;
                    refreshLayerStyles(lId);
                    updateSelectionUI();
                    var l = layerObj.indexMap[idx];
                    if (l) {{
                        if (l.getBounds && l.getBounds().isValid()) {{
                            map.fitBounds(l.getBounds(), {{ maxZoom: 16, padding: [40, 40] }});
                        }} else if (l.getLatLng) {{
                            map.setView(l.getLatLng(), Math.max(map.getZoom(), 13));
                        }}
                        if (l.openPopup) l.openPopup();
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
                if isinstance(self._pending_content, tuple):
                    c, fb = self._pending_content
                    self.render_content(c, fit_bounds=fb)
                else:
                    self.render_content(self._pending_content, fit_bounds=True)
                self._pending_content = None
            if getattr(self, '_pending_vector_layers', None):
                last_fit_layer = None
                for lid, (lname, lgjson, lia, lgt, lcol, lfb) in list(self._pending_vector_layers.items()):
                    self.set_vector_layer(lid, lname, lgjson, lia, lgt, lcol, lfb)
                    if lfb:
                        last_fit_layer = lid
                self._pending_vector_layers.clear()
                if last_fit_layer:
                    self.fit_bounds(last_fit_layer)
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

    def set_vector_layer(self, layer_id: str, name: str, geojson_str: str, is_active: bool = True, geom_type: str = "any", color: str = None, fit_bounds: bool = False):
        if not geojson_str or not geojson_str.strip():
            return
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            esc_name = json.dumps(name)
            esc_type = json.dumps(geom_type)
            esc_color = json.dumps(color) if color else "null"
            act_str = "true" if is_active else "false"
            fit_str = "true" if fit_bounds else "false"
            js_code = f"setVectorLayer({esc_id}, {esc_name}, {geojson_str}, {act_str}, {esc_type}, {esc_color}, {fit_str});"
            self.web_view.page().runJavaScript(js_code)
        else:
            if not hasattr(self, '_pending_vector_layers'):
                self._pending_vector_layers = {}
            self._pending_vector_layers[layer_id] = (name, geojson_str, is_active, geom_type, color, fit_bounds)

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

    def fit_bounds(self, layer_id: str = None):
        if self._is_loaded:
            esc_id = json.dumps(layer_id) if layer_id else "null"
            self.web_view.page().runJavaScript(f"fitLayerBounds({esc_id});")

    def fit_layer_bounds(self, layer_id: str = None):
        self.fit_bounds(layer_id)

    def add_wms_layer(self, layer_id: str, url: str, layer_name: str, fmt: str = "image/png", transparent: bool = True, title: str = ""):
        if self._is_loaded:
            esc_id = json.dumps(layer_id)
            esc_url = json.dumps(url)
            esc_layer = json.dumps(layer_name)
            esc_fmt = json.dumps(fmt)
            esc_title = json.dumps(title or layer_name)
            trans_str = "true" if transparent else "false"
            self.web_view.page().runJavaScript(f"addWmsLayer({esc_id}, {esc_url}, {esc_layer}, {esc_fmt}, {trans_str}, {esc_title});")

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