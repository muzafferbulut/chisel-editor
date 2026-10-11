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
        theme = ThemeManager._current_theme
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <style>
                html, body, #map {{
                    margin: 0; padding: 0; width: 100vw; height: 100vh; overflow: hidden;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
                    border: 1px solid rgba(255, 255, 255, 0.16);
                    border-radius: 8px;
                    padding: 8px 10px;
                    gap: 6px;
                    box-shadow: 0 8px 24px rgba(0,0,0,0.5);
                    z-index: 1002;
                    min-width: 220px;
                    max-width: 290px;
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
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                    padding-bottom: 5px;
                    letter-spacing: 0.3px;
                }}
                .hud-layer-count-badge {{
                    background: rgba(255, 255, 255, 0.12);
                    color: #9cdcfe;
                    border-radius: 10px;
                    font-size: 10px;
                    padding: 0 5px;
                    font-weight: 600;
                }}
                .hud-layers-add-btn {{
                    background: rgba(0, 120, 212, 0.25);
                    border: 1px solid rgba(76, 194, 255, 0.4);
                    color: #4cc2ff;
                    font-size: 10px;
                    font-weight: 600;
                    padding: 2px 7px;
                    border-radius: 4px;
                    cursor: pointer;
                    transition: all 0.15s ease;
                }}
                .hud-layers-add-btn:hover {{
                    background: #0078d4;
                    color: #ffffff;
                }}
                .hud-layers-list {{
                    display: flex;
                    flex-direction: column;
                    gap: 3px;
                    max-height: 260px;
                    overflow-y: auto;
                    padding-right: 2px;
                }}
                .hud-layers-list::-webkit-scrollbar {{
                    width: 4px;
                }}
                .hud-layers-list::-webkit-scrollbar-thumb {{
                    background: rgba(255, 255, 255, 0.2);
                    border-radius: 2px;
                }}
                .hud-layer-item {{
                    display: flex;
                    align-items: center;
                    background: rgba(255, 255, 255, 0.04);
                    border: 1px solid rgba(255, 255, 255, 0.07);
                    border-left: 3px solid transparent;
                    border-radius: 4px;
                    padding: 4px 6px;
                    font-size: 11px;
                    gap: 6px;
                    cursor: pointer;
                    transition: background 0.12s ease, border-color 0.12s ease;
                }}
                .hud-layer-item:hover {{
                    background: rgba(255, 255, 255, 0.09);
                    border-color: rgba(255, 255, 255, 0.15);
                }}
                .hud-layer-item.active-layer {{
                    background: rgba(0, 120, 212, 0.22) !important;
                    border-color: rgba(76, 194, 255, 0.35) !important;
                    border-left: 3px solid #0078d4 !important;
                }}
                .hud-layer-symbology {{
                    display: inline-flex;
                    align-items: center;
                    justify-content: center;
                    width: 16px;
                    height: 16px;
                    flex-shrink: 0;
                }}
                .hud-layer-btn-del {{
                    background: transparent;
                    border: none;
                    color: #888888;
                    cursor: pointer;
                    padding: 2px 4px;
                    font-size: 11px;
                    border-radius: 3px;
                    opacity: 0.5;
                    transition: all 0.15s ease;
                    flex-shrink: 0;
                }}
                .hud-layer-item:hover .hud-layer-btn-del {{
                    opacity: 1;
                }}
                .hud-layer-btn-del:hover {{
                    color: #ff5252;
                    background: rgba(231, 76, 60, 0.2);
                }}
                .hud-layer-tag {{
                    font-size: 9px;
                    font-weight: 700;
                    padding: 1px 4px;
                    border-radius: 3px;
                    letter-spacing: 0.3px;
                    flex-shrink: 0;
                    line-height: 1.2;
                }}
                .hud-layer-tag.wfs-tag {{
                    background: rgba(46, 204, 113, 0.2);
                    color: #2ecc71;
                    border: 1px solid rgba(46, 204, 113, 0.4);
                }}
                .hud-layer-tag.wms-tag {{
                    background: rgba(56, 189, 248, 0.2);
                    color: #38bdf8;
                    border: 1px solid rgba(56, 189, 248, 0.4);
                }}
                .hud-layers-section-header {{
                    font-size: 10px;
                    font-weight: 700;
                    color: #858585;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    padding: 5px 2px 2px 2px;
                    display: flex;
                    align-items: center;
                    gap: 4px;
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
                .measure-tooltip {{
                    background: rgba(0,0,0,0.85);
                    color: #fff;
                    padding: 3px 6px;
                    border-radius: 3px;
                    font-size: 11px;
                    font-weight: bold;
                    border: 1px solid #00a2ff;
                }}
                .leaflet-bottom.leaflet-left {{
                    display: flex !important;
                    flex-direction: row !important;
                    align-items: flex-end !important;
                    gap: 6px !important;
                    margin-left: 10px !important;
                    margin-bottom: 8px !important;
                    pointer-events: none;
                }}
                .leaflet-bottom.leaflet-left .leaflet-control {{
                    margin: 0 !important;
                    pointer-events: auto;
                }}
                .leaflet-control-scale-line {{
                    background: rgba(24, 28, 34, 0.75) !important;
                    backdrop-filter: blur(4px);
                    border: 1px solid rgba(255, 255, 255, 0.28) !important;
                    border-top: none !important;
                    color: #d1d5db !important;
                    font-family: Consolas, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
                    font-size: 11px !important;
                    font-weight: 500 !important;
                    padding: 2px 6px 1px 6px !important;
                    box-sizing: border-box;
                    box-shadow: 0 1px 4px rgba(0,0,0,0.35);
                    text-shadow: none !important;
                    height: 20px;
                    display: flex;
                    align-items: center;
                    border-radius: 0 0 2px 2px;
                }}
                .hud-coords-control {{
                    background: rgba(24, 28, 34, 0.75);
                    backdrop-filter: blur(4px);
                    border: 1px solid rgba(255, 255, 255, 0.28);
                    border-radius: 2px;
                    padding: 2px 8px 1px 8px;
                    font-size: 11px;
                    font-family: Consolas, -apple-system, BlinkMacSystemFont, "Segoe UI", monospace;
                    font-weight: 500;
                    color: #d1d5db;
                    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
                    height: 20px;
                    box-sizing: border-box;
                    display: flex;
                    align-items: center;
                    cursor: pointer;
                    user-select: none;
                    transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
                    white-space: nowrap;
                }}
                .hud-coords-control:hover {{
                    background: rgba(0, 120, 212, 0.85);
                    border-color: #38bdf8;
                    color: #ffffff;
                }}
                .hud-coords-control.copied {{
                    background: rgba(46, 204, 113, 0.9) !important;
                    border-color: #2ecc71 !important;
                    color: #ffffff !important;
                }}
                .vertex-handle-icon {{
                    background: transparent;
                    border: none;
                }}
                .vertex-handle-inner {{
                    width: 11px;
                    height: 11px;
                    background: #ffffff;
                    border: 2px solid #0078d4;
                    border-radius: 50%;
                    box-shadow: 0 0 5px rgba(0,0,0,0.6);
                    cursor: grab;
                    transition: transform 0.12s ease;
                    box-sizing: border-box;
                }}
                .vertex-handle-inner:hover {{
                    transform: scale(1.35);
                    background: #ffb703;
                    border-color: #fb8500;
                }}
                .vertex-handle-inner:active {{
                    cursor: grabbing;
                }}
                .snapshot-legend {{
                    display: none;
                    position: absolute;
                    top: 14px;
                    right: 14px;
                    background: rgba(24, 28, 34, 0.90);
                    backdrop-filter: blur(10px);
                    border: 1px solid rgba(255, 255, 255, 0.18);
                    border-radius: 8px;
                    padding: 8px 12px;
                    color: #f1f5f9;
                    font-size: 11px;
                    z-index: 1000;
                    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45);
                    min-width: 140px;
                    max-width: 280px;
                    pointer-events: none;
                }}
                .snapshot-legend-title {{
                    font-size: 11px;
                    font-weight: 700;
                    color: #9cdcfe;
                    margin-bottom: 6px;
                    padding-bottom: 4px;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.12);
                    letter-spacing: 0.3px;
                }}
                .snapshot-legend-items {{
                    display: flex;
                    flex-direction: column;
                    gap: 5px;
                }}
                .snapshot-legend-item {{
                    display: flex;
                    align-items: center;
                    gap: 7px;
                    font-size: 11px;
                    line-height: 1.3;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                }}
                body.snapshot-mode .snapshot-legend {{
                    display: block !important;
                }}
                body.snapshot-mode .hud-toolbar-v {{
                    display: none !important;
                }}
                body.snapshot-mode .leaflet-control-zoom {{
                    display: none !important;
                }}
                body.snapshot-mode .vertex-handle-icon {{
                    display: none !important;
                }}
            </style>
        </head>
        <body>
            <div id="map"></div>

            <!-- Clean GIS Legend for Snapshot / Map Output -->
            <div id="snapshotLegend" class="snapshot-legend"></div>

            <!-- Vertical Action Toolbar on the Far Right -->
            <div class="hud-toolbar-v">
                <!-- 1. Katmanlar & Servisler (QGIS Mantığıyla En Üstte) -->
                <div style="position: relative;">
                    <button class="hud-vbtn" id="btnLayers" onclick="toggleLayersFlyout()" data-tip="Katmanlar & Servisler" title="Katmanlar">
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/></svg>
                    </button>
                    <div class="hud-layers-flyout" id="layersFlyout">
                        <div class="hud-layers-header">
                            <span style="display:flex; align-items:center; gap:6px;">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/></svg>
                                <span>Katmanlar</span>
                                <span id="layerTotalCountBadge" class="hud-layer-count-badge">0</span>
                            </span>
                            <button class="hud-layers-add-btn" onclick="requestAddService()" title="WMS / WFS Servisi ve Altlık Harita Ekle">+ WMS & WFS</button>
                        </div>
                        <div class="hud-layers-list" id="layersListContainer">
                            <div style="color: #858585; font-size: 11px; padding: 6px 2px; text-align: center;">(Katman yok)</div>
                        </div>
                    </div>
                </div>

                <div class="hud-vdivider"></div>

                <!-- 2. Navigasyon & Görünüm -->
                <button class="hud-vbtn" id="btnTable" onclick="toggleTableHud()" data-tip="Öznitelik Tablosu (F6)" title="Öznitelik Tablosu">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18"/><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/></svg>
                </button>
                <button class="hud-vbtn" id="btnFullExtent" onclick="zoomFullExtent()" data-tip="Tüm Haritaya Odaklan (Full Extent)" title="Tüm Haritaya Odaklan">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                </button>
                <button class="hud-vbtn" id="btnFit" onclick="fitLayerBounds()" data-tip="Seçili Katmana Odaklan" title="Seçili Katmana Odaklan">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="22" x2="18" y1="12" y2="12"/><line x1="6" x2="2" y1="12" y2="12"/><line x1="12" x2="12" y1="6" y2="2"/><line x1="12" x2="12" y1="22" y2="18"/></svg>
                </button>
                
                <div class="hud-vdivider"></div>
                
                <!-- 3. Akıllı Seçim Aracı -->
                <button class="hud-vbtn active" id="btnSelectClick" onclick="setSelectTool('click')" data-tip="Nesne Seç (Tıkla / Shift+Kutu)" title="Nesne Seç">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 3 7.07 16.97 2.51-7.39 7.39-2.51L3 3z"/><path d="m13 13 6 6"/></svg>
                </button>
                
                <div class="hud-vdivider"></div>
                
                <!-- 4. Vektör Çizim & Düzenleme -->
                <button class="hud-vbtn" id="btnAddPoint" onclick="toggleDrawMode('point')" data-tip="Nokta Ekle (Haritaya Tıkla)" title="Nokta Ekle">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19.914 11.105A7.298 7.298 0 0 0 20 10a8 8 0 0 0-16 0c0 4.993 5.539 10.193 7.399 11.799a1 1 0 0 0 1.202 0 32.4 32.4 0 0 0 .824-.738"/><circle cx="12" cy="10" r="3"/><line x1="19" x2="19" y1="16" y2="22"/><line x1="16" x2="22" y1="19" y2="19"/></svg>
                </button>
                <button class="hud-vbtn" id="btnAddLine" onclick="toggleDrawMode('line')" data-tip="Çizgi Ekle (Çiz & Çift Tıkla)" title="Çizgi Ekle">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="19" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><path d="M5 17A12 12 0 0 1 17 5"/></svg>
                </button>
                <button class="hud-vbtn" id="btnAddPolygon" onclick="toggleDrawMode('polygon')" data-tip="Çokgen Ekle (Çiz & Çift Tıkla)" title="Çokgen Ekle">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.83 2.38a2 2 0 0 1 2.34 0l8 5.74a2 2 0 0 1 .73 2.25l-3.04 9.26a2 2 0 0 1-1.9 1.37H7.04a2 2 0 0 1-1.9-1.37L2.1 10.37a2 2 0 0 1 .73-2.25z"/></svg>
                </button>
                <button class="hud-vbtn" id="btnEditGeom" onclick="toggleVertexEditMode()" data-tip="Düğümleri Düzenle (Düğüm Noktaları)" title="Düğüm Düzenle">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/></svg>
                </button>
                <button class="hud-vbtn hud-vbtn-del" id="btnDelete" onclick="deleteSelectedFeatures()" data-tip="Seçili Geometrileri Sil (Del)" title="Seçili Geometrileri Sil">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/></svg>
                </button>
                
                <div class="hud-vdivider"></div>
                
                <!-- 5. Ölçüm & Çıktı -->
                <button class="hud-vbtn" id="btnMeasure" onclick="toggleMeasure()" data-tip="Mesafe / Alan Ölçümü" title="Ölçüm">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.3 8.7 8.7 21.3c-1 1-2.5 1-3.4 0l-2.6-2.6c-1-1-1-2.5 0-3.4L15.3 2.7c1-1 2.5-1 3.4 0l2.6 2.6c1 1 1 2.5 0 3.4Z"/><path d="m14.5 3.5 2 2"/><path d="m11.5 6.5 2 2"/><path d="m8.5 9.5 2 2"/><path d="m5.5 12.5 2 2"/></svg>
                </button>
                <button class="hud-vbtn" id="btnSnapshot" onclick="captureMapSnapshot()" data-tip="Harita Görüntüsünü Kaydet (PNG)" title="Ekranı Yakala">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/></svg>
                </button>
            </div>

            <script>
                var map = L.map('map', {{
                    preferCanvas: true,
                    zoomControl: true,
                    attributionControl: false,
                    boxZoom: false
                }}).setView([39.0, 35.0], 5);

                L.control.scale({{ imperial: false, position: 'bottomleft' }}).addTo(map);

                var coordsControl = L.control({{ position: 'bottomleft' }});
                coordsControl.onAdd = function() {{
                    var div = L.DomUtil.create('div', 'hud-coords-control');
                    div.id = 'hudCoordinates';
                    div.title = 'Koordinatları kopyalamak için tıklayın';
                    div.innerText = '39.0000° K, 35.0000° D';
                    L.DomEvent.disableClickPropagation(div);
                    div.onclick = copyMapCoordinates;
                    return div;
                }};
                coordsControl.addTo(map);

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

                var currentBase = 'osm';
                if (freeTiles[currentBase]) freeTiles[currentBase].addTo(map);
                applyTileFilter(currentBase);

                function setBaseMap(type) {{
                    if (freeTiles[currentBase]) map.removeLayer(freeTiles[currentBase]);
                    currentBase = type;
                    if (freeTiles[type]) freeTiles[type].addTo(map);
                    applyTileFilter(type);
                    bringVectorsToFront();
                }}

                var geojsonLayer = null;
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
                    var isOpen = false;
                    if (lFlyout) {{
                        isOpen = lFlyout.classList.toggle('open');
                        var btn = document.getElementById('btnLayers');
                        if (btn) btn.classList.toggle('active', isOpen);
                    }}
                    if (isOpen) renderLayersPanel();
                }}

                function closeAllFlyouts() {{
                    var lFlyout = document.getElementById('layersFlyout');
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

                function getLayerSymbolHtml(geomType, color) {{
                    var c = color || '#0078d4';
                    var gt = (geomType || 'any').toLowerCase();
                    if (gt === 'point') {{
                        return '<span class="hud-layer-symbology" title="Nokta Katmanı">' +
                               '<svg width="15" height="15" viewBox="0 0 15 15">' +
                               '<circle cx="7.5" cy="7.5" r="4.5" fill="' + c + '" stroke="#ffffff" stroke-width="1.2"/>' +
                               '</svg></span>';
                    }} else if (gt === 'line') {{
                        return '<span class="hud-layer-symbology" title="Çizgi Katmanı">' +
                               '<svg width="15" height="15" viewBox="0 0 15 15">' +
                               '<path d="M 2 12 L 6.5 3.5 L 13 8" fill="none" stroke="' + c + '" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>' +
                               '</svg></span>';
                    }} else if (gt === 'polygon') {{
                        return '<span class="hud-layer-symbology" title="Çokgen Katmanı">' +
                               '<svg width="15" height="15" viewBox="0 0 15 15">' +
                               '<polygon points="2.5,4.5 9.5,2 13,8 5,12.5" fill="' + c + '" fill-opacity="0.45" stroke="' + c + '" stroke-width="1.8" stroke-linejoin="round"/>' +
                               '</svg></span>';
                    }} else {{
                        return '<span class="hud-layer-symbology" title="Karma Katman">' +
                               '<svg width="15" height="15" viewBox="0 0 15 15">' +
                               '<polygon points="1.5,5.5 7,2 11.5,6.5 6,12" fill="' + c + '" fill-opacity="0.35" stroke="' + c + '" stroke-width="1.4"/>' +
                               '<circle cx="10" cy="4" r="2.2" fill="' + c + '" stroke="#ffffff" stroke-width="0.8"/>' +
                               '</svg></span>';
                    }}
                }}

                function getWmsSymbolHtml() {{
                    return '<span class="hud-layer-symbology" title="WMS / Harita Servisi">' +
                           '<svg width="15" height="15" viewBox="0 0 15 15">' +
                           '<circle cx="7.5" cy="7.5" r="5.5" fill="none" stroke="#38bdf8" stroke-width="1.2"/>' +
                           '<ellipse cx="7.5" cy="7.5" rx="2.5" ry="5.5" fill="none" stroke="#38bdf8" stroke-width="1.0"/>' +
                           '<line x1="2" y1="7.5" x2="13" y2="7.5" stroke="#38bdf8" stroke-width="1.0"/>' +
                           '</svg></span>';
                }}

                function renderLayersPanel() {{
                    var container = document.getElementById('layersListContainer');
                    if (!container) return;

                    var vKeys = Object.keys(vectorLayers);
                    var wKeys = Object.keys(wmsRegistry);
                    var totalCount = vKeys.length + wKeys.length;

                    var badge = document.getElementById('layerTotalCountBadge');
                    if (badge) badge.innerText = totalCount;

                    if (totalCount === 0) {{
                        container.innerHTML = '<div style="color: #858585; font-size: 11px; padding: 8px 4px; text-align: center;">(Katman veya servis yok)</div>';
                        return;
                    }}

                    var html = '';

                    // 1. Vector & WFS Layers (QGIS Layer Tree format)
                    if (vKeys.length > 0) {{
                        html += '<div class="hud-layers-section-header">📁 Vektör & WFS (' + vKeys.length + ')</div>';
                        vKeys.forEach(function(k) {{
                            var l = vectorLayers[k];
                            var chk = l.visible ? 'checked' : '';
                            var symHtml = getLayerSymbolHtml(l.geomType, l.color);
                            var countStr = l.count > 0 ? ' <span style="color:#858585; font-size:10px;">(' + l.count.toLocaleString() + ')</span>' : '';
                            var isWfs = (l.isWfs || (l.name && (l.name.indexOf('(WFS)') !== -1 || l.name.indexOf('[WFS]') !== -1 || l.name.indexOf('WFS') !== -1)));
                            var tagHtml = isWfs ? '<span class="hud-layer-tag wfs-tag" title="WFS Servisi">WFS</span> ' : '';

                            html += 
                                '<div class="hud-layer-item' + (l.isActive ? ' active-layer' : '') + '" onclick="requestSetActiveLayer(\\x27' + l.id + '\\x27)" title="' + l.name + (l.isActive ? ' (Aktif)' : '') + '">' +
                                '<input type="checkbox" ' + chk + ' onclick="event.stopPropagation();" onchange="setVectorLayerVisibility(\\x27' + l.id + '\\x27, this.checked)" title="Görünürlük"/>' +
                                symHtml +
                                tagHtml +
                                '<span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; min-width:0; font-size:11px;' + (l.isActive ? ' font-weight:600; color:#4cc2ff;' : '') + '">' + l.name + countStr + '</span>' +
                                '<button class="hud-layer-btn-del" onclick="event.stopPropagation(); removeVectorLayerUi(\\x27' + l.id + '\\x27)" title="Katmanı Kaldır">✕</button>' +
                                '</div>';
                        }});
                    }}

                    // 2. Web Services (WMS & Altlık Servisleri)
                    if (wKeys.length > 0) {{
                        if (vKeys.length > 0) {{
                            html += '<div style="height:1px; background:rgba(255,255,255,0.08); margin:6px 0 4px 0;"></div>';
                        }}
                        html += '<div class="hud-layers-section-header">🌐 WMS & Servisler (' + wKeys.length + ')</div>';
                        wKeys.forEach(function(k) {{
                            var layer = wmsRegistry[k];
                            var chk = layer.visible ? 'checked' : '';
                            var title = layer.title || layer.layerName;
                            var wmsSym = getWmsSymbolHtml();
                            var tagHtml = '<span class="hud-layer-tag wms-tag" title="WMS / Harita Servisi">WMS</span> ';
                            html += 
                                '<div class="hud-layer-item" title="' + title + '">' +
                                '<input type="checkbox" ' + chk + ' onclick="event.stopPropagation();" onchange="toggleWmsVisibility(\\x27' + layer.id + '\\x27, this.checked)" title="Görünürlük"/>' +
                                wmsSym +
                                tagHtml +
                                '<span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; min-width:0; font-size:11px;">' + title + '</span>' +
                                '<button class="hud-layer-btn-del" onclick="event.stopPropagation(); removeWms(\\x27' + layer.id + '\\x27)" title="Servisi Kaldır">✕</button>' +
                                '</div>';
                        }});
                    }}

                    container.innerHTML = html;
                }}

                // --- WMS & XYZ Tile Layer Management ---
                function addWmsLayer(layerId, url, layers, format, transparent, title) {{
                    if (wmsLayers[layerId]) map.removeLayer(wmsLayers[layerId]);
                    if (url.indexOf('{{z}}') !== -1) {{
                        wmsLayers[layerId] = L.tileLayer(url, {{
                            maxZoom: 20
                        }}).addTo(map);
                    }} else {{
                        wmsLayers[layerId] = L.tileLayer.wms(url, {{
                            layers: layers,
                            format: format || 'image/png',
                            transparent: transparent !== false,
                            maxZoom: 20
                        }}).addTo(map);
                    }}
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
                    Object.keys(vectorLayers).forEach(function(k) {{
                        var vl = vectorLayers[k];
                        if (vl.leafletLayer && vl.visible) {{
                            vl.leafletLayer.bringToFront();
                        }}
                    }});
                }}

                // --- Map Mouse Move & Coordinate Tracking ---
                map.on('mousemove', function(e) {{
                    if (isBoxSelecting && boxRectLayer && boxStartLatLng) {{
                        boxRectLayer.setBounds(L.latLngBounds(boxStartLatLng, e.latlng));
                    }}
                    var coordsEl = document.getElementById('hudCoordinates');
                    if (coordsEl && !coordsEl.classList.contains('copied')) {{
                        var lat = e.latlng.lat;
                        var lng = e.latlng.lng;
                        var latH = lat >= 0 ? 'K' : 'G';
                        var lngH = lng >= 0 ? 'D' : 'B';
                        coordsEl.setAttribute('data-lat', lat.toFixed(5));
                        coordsEl.setAttribute('data-lng', lng.toFixed(5));
                        coordsEl.innerText = Math.abs(lat).toFixed(4) + '° ' + latH + ', ' + Math.abs(lng).toFixed(4) + '° ' + lngH;
                    }}
                }});

                map.on('zoomend', function() {{
                    var coordsEl = document.getElementById('hudCoordinates');
                    if (coordsEl && !coordsEl.classList.contains('copied')) {{
                        var c = map.getCenter();
                        var lat = coordsEl.getAttribute('data-lat') || c.lat.toFixed(5);
                        var lng = coordsEl.getAttribute('data-lng') || c.lng.toFixed(5);
                        var latNum = parseFloat(lat);
                        var lngNum = parseFloat(lng);
                        var latH = latNum >= 0 ? 'K' : 'G';
                        var lngH = lngNum >= 0 ? 'D' : 'B';
                        coordsEl.innerText = Math.abs(latNum).toFixed(4) + '° ' + latH + ', ' + Math.abs(lngNum).toFixed(4) + '° ' + lngH;
                    }}
                }});

                function updateCoordinatesToMapCenter() {{
                    var coordsEl = document.getElementById('hudCoordinates');
                    if (coordsEl && map) {{
                        var c = map.getCenter();
                        var lat = c.lat;
                        var lng = c.lng;
                        var latH = lat >= 0 ? 'K' : 'G';
                        var lngH = lng >= 0 ? 'D' : 'B';
                        coordsEl.setAttribute('data-lat', lat.toFixed(5));
                        coordsEl.setAttribute('data-lng', lng.toFixed(5));
                        coordsEl.innerText = Math.abs(lat).toFixed(4) + '° ' + latH + ', ' + Math.abs(lng).toFixed(4) + '° ' + lngH;
                    }}
                }}

                function copyMapCoordinates() {{
                    var coordsEl = document.getElementById('hudCoordinates');
                    if (!coordsEl) return;
                    var c = map.getCenter();
                    var lat = coordsEl.getAttribute('data-lat') || c.lat.toFixed(5);
                    var lng = coordsEl.getAttribute('data-lng') || c.lng.toFixed(5);
                    var text = lat + ', ' + lng;
                    if (navigator.clipboard && navigator.clipboard.writeText) {{
                        navigator.clipboard.writeText(text);
                    }} else {{
                        var ta = document.createElement('textarea');
                        ta.value = text;
                        document.body.appendChild(ta);
                        ta.select();
                        document.execCommand('copy');
                        document.body.removeChild(ta);
                    }}
                    var origText = coordsEl.innerText;
                    coordsEl.classList.add('copied');
                    coordsEl.innerText = text + ' (Kopyalandı)';
                    setTimeout(function() {{
                        coordsEl.classList.remove('copied');
                        coordsEl.innerText = origText;
                    }}, 1200);
                }}

                var viewportDebounceTimer = null;
                map.on('moveend', function() {{
                    if (selectedIndices.size > 0 && activeLayerId) {{
                        refreshLayerStyles(activeLayerId);
                    }}
                    if (viewportDebounceTimer) clearTimeout(viewportDebounceTimer);
                    viewportDebounceTimer = setTimeout(function() {{
                        if (pyBridge && pyBridge.onViewportChanged) {{
                            var b = map.getBounds();
                            var z = map.getZoom();
                            pyBridge.onViewportChanged(b.getWest(), b.getSouth(), b.getEast(), b.getNorth(), z);
                        }}
                    }}, 120);
                }});

                // --- Geometry Addition & Drawing Modes ---
                var activeLayerGeomType = 'any'; // 'point' | 'line' | 'polygon' | 'mixed' | 'any'
                var drawMode = null; // null | 'point' | 'line' | 'polygon'
                var polyDrawPoints = [];
                var polyDrawMarkers = [];
                var polyDrawLine = null;
                var polyDrawPoly = null;
                var selectedFeatureIndex = -1;

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
                    console.warn(msg);
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
                    if (typeof finishVertexEditMode === 'function') finishVertexEditMode();
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

                    if (mode === 'point') {{
                        map.getContainer().style.cursor = 'crosshair';
                    }} else if (mode === 'line') {{
                        map.getContainer().style.cursor = 'crosshair';
                        map.doubleClickZoom.disable();
                    }} else if (mode === 'polygon') {{
                        map.getContainer().style.cursor = 'crosshair';
                        map.doubleClickZoom.disable();
                    }}
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
                    if (mode === 'box' && typeof finishVertexEditMode === 'function') finishVertexEditMode();
                    closeAllFlyouts();

                    selectMode = mode;
                    var bClick = document.getElementById('btnSelectClick');
                    if (bClick) bClick.classList.toggle('active', mode === 'click');

                    if (mode === 'box') {{
                        map.dragging.disable();
                        map.getContainer().style.cursor = 'crosshair';
                    }} else {{
                        map.dragging.enable();
                        map.getContainer().style.cursor = '';
                    }}
                }}

                function cancelBanner() {{
                    if (drawMode) cancelDrawMode();
                    if (selectMode === 'box') setSelectTool('click');
                }}

                function updateSelectionUI() {{
                    var count = selectedIndices.size;
                    var btnDel = document.getElementById('btnDelete');
                    var btnEdit = document.getElementById('btnEditGeom');

                    if (count > 0) {{
                        if (btnDel) {{
                            btnDel.classList.add('has-selection');
                            btnDel.setAttribute('data-tip', 'Seçili ' + count + ' Geometriyi Sil (Del)');
                        }}
                    }} else {{
                        if (btnDel) {{
                            btnDel.classList.remove('has-selection');
                            btnDel.setAttribute('data-tip', 'Seçili Geometrileri Sil (Önce Geometri Seçin)');
                        }}
                    }}

                    if (btnEdit) {{
                        if (count === 1) {{
                            btnEdit.classList.remove('disabled');
                            btnEdit.setAttribute('data-tip', 'Düğümleri Düzenle (Köşe Noktaları ✏️)');
                        }} else if (count > 1) {{
                            btnEdit.classList.add('disabled');
                            btnEdit.setAttribute('data-tip', '⚠️ Düğüm düzenlemek için tek bir geometri seçiniz');
                        }} else {{
                            btnEdit.classList.remove('disabled');
                            btnEdit.setAttribute('data-tip', 'Düğümleri Düzenle (Düğüm Noktaları)');
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
                            if (l.bringToFront) l.bringToFront();
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
                        if (isSelected && l.bringToFront) l.bringToFront();
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
                    if (vertexEditActive) {{
                        if (selectedIndices.size === 1) {{
                            attachVertexHandles(lId, selectedFeatureIndex);
                        }} else {{
                            clearVertexHandles();
                        }}
                    }}
                }}

                function clearSelection() {{
                    if (vertexEditActive) finishVertexEditMode();
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
                    if (vertexEditActive) finishVertexEditMode();
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

                // --- Vertex Editing (Node Tool) ---
                var vertexEditActive = false;
                var vertexEditLayerId = null;
                var vertexEditFeatureIdx = -1;
                var vertexMarkers = [];

                function toggleVertexEditMode() {{
                    if (vertexEditActive) {{
                        finishVertexEditMode();
                    }} else {{
                        startVertexEditMode();
                    }}
                }}

                function startVertexEditMode() {{
                    if (!activeLayerId || !vectorLayers[activeLayerId]) {{
                        showWarningBanner("⚠️ Düğüm düzenlemek için önce bir katman açın!");
                        return;
                    }}

                    if (drawMode) cancelDrawMode();
                    if (measureActive) toggleMeasure();
                    if (selectMode === 'box') setSelectTool('click');

                    vertexEditActive = true;
                    var btnEdit = document.getElementById('btnEditGeom');
                    if (btnEdit) btnEdit.classList.add('active');

                    if (selectedIndices.size === 1) {{
                        var idx = Array.from(selectedIndices)[0];
                        attachVertexHandles(activeLayerId, idx);
                    }} else if (selectedIndices.size > 1) {{
                        showWarningBanner("⚠️ Düğüm düzenlemek için tek bir geometri seçiniz!");
                    }} else {{
                        showWarningBanner("✏️ Düğümlerini düzenlemek istediğiniz geometriye tıklayın.");
                    }}
                }}

                function finishVertexEditMode() {{
                    clearVertexHandles();
                    vertexEditActive = false;
                    vertexEditLayerId = null;
                    vertexEditFeatureIdx = -1;
                    var btnEdit = document.getElementById('btnEditGeom');
                    if (btnEdit) btnEdit.classList.remove('active');
                }}

                function clearVertexHandles() {{
                    vertexMarkers.forEach(function(m) {{
                        map.removeLayer(m);
                    }});
                    vertexMarkers = [];
                }}

                function notifyFeatureUpdated(featureIdx, geom) {{
                    if (pyBridge && pyBridge.onFeatureUpdated) {{
                        pyBridge.onFeatureUpdated(featureIdx, JSON.stringify(geom));
                    }}
                }}

                function attachVertexHandles(layerId, featureIdx) {{
                    clearVertexHandles();
                    var lObj = vectorLayers[layerId];
                    if (!lObj || !lObj.indexMap) return;
                    var target = lObj.indexMap[featureIdx];
                    if (!target) return;

                    vertexEditActive = true;
                    vertexEditLayerId = layerId;
                    vertexEditFeatureIdx = featureIdx;

                    var btnEdit = document.getElementById('btnEditGeom');
                    if (btnEdit) btnEdit.classList.add('active');

                    var shapes = [];
                    if (target.eachLayer && !(target instanceof L.Polyline)) {{
                        target.eachLayer(function(child) {{ shapes.push(child); }});
                    }} else {{
                        shapes.push(target);
                    }}

                    shapes.forEach(function(subLayer) {{
                        attachHandlesToSubLayer(subLayer, featureIdx);
                    }});
                }}

                function attachHandlesToSubLayer(subLayer, featureIdx) {{
                    // Point / CircleMarker
                    if (subLayer.getLatLng && !subLayer.getLatLngs) {{
                        var pt = subLayer.getLatLng();
                        var m = L.marker(pt, {{
                            draggable: true,
                            icon: L.divIcon({{
                                className: 'vertex-handle-icon',
                                html: '<div class="vertex-handle-inner"></div>',
                                iconSize: [12, 12],
                                iconAnchor: [6, 6]
                            }}),
                            zIndexOffset: 10000
                        }}).addTo(map);

                        m.on('drag', function() {{
                            subLayer.setLatLng(m.getLatLng());
                        }});

                        m.on('dragend', function() {{
                            var newPos = m.getLatLng();
                            subLayer.setLatLng(newPos);
                            var geom = {{
                                type: "Point",
                                coordinates: [newPos.lng, newPos.lat]
                            }};
                            notifyFeatureUpdated(featureIdx, geom);
                        }});

                        vertexMarkers.push(m);
                        return;
                    }}

                    // Polyline or Polygon
                    if (subLayer.getLatLngs) {{
                        var rawLatLngs = subLayer.getLatLngs();
                        var isPoly = (subLayer instanceof L.Polygon);

                        if (isPoly) {{
                            var rings = Array.isArray(rawLatLngs[0]) ? rawLatLngs : [rawLatLngs];
                            rings.forEach(function(ring, rIdx) {{
                                ring.forEach(function(pt, pIdx) {{
                                    var m = L.marker(pt, {{
                                        draggable: true,
                                        icon: L.divIcon({{
                                            className: 'vertex-handle-icon',
                                            html: '<div class="vertex-handle-inner"></div>',
                                            iconSize: [12, 12],
                                            iconAnchor: [6, 6]
                                        }}),
                                        zIndexOffset: 10000
                                    }}).addTo(map);

                                    m.on('drag', function() {{
                                        ring[pIdx] = m.getLatLng();
                                        subLayer.setLatLngs(rawLatLngs);
                                    }});

                                    m.on('dragend', function() {{
                                        ring[pIdx] = m.getLatLng();
                                        subLayer.setLatLngs(rawLatLngs);
                                        var polyCoords = rings.map(function(r) {{
                                            var pts = r.map(function(p) {{ return [p.lng, p.lat]; }});
                                            if (pts.length > 0) {{
                                                var first = pts[0];
                                                var last = pts[pts.length - 1];
                                                if (first[0] !== last[0] || first[1] !== last[1]) {{
                                                    pts.push([first[0], first[1]]);
                                                }}
                                            }}
                                            return pts;
                                        }});
                                        var geom = {{
                                            type: "Polygon",
                                            coordinates: polyCoords
                                        }};
                                        notifyFeatureUpdated(featureIdx, geom);
                                    }});

                                    vertexMarkers.push(m);
                                }});
                            }});
                        }} else {{
                            var isMultiLine = Array.isArray(rawLatLngs[0]);
                            var lineParts = isMultiLine ? rawLatLngs : [rawLatLngs];

                            lineParts.forEach(function(part, partIdx) {{
                                part.forEach(function(pt, pIdx) {{
                                    var m = L.marker(pt, {{
                                        draggable: true,
                                        icon: L.divIcon({{
                                            className: 'vertex-handle-icon',
                                            html: '<div class="vertex-handle-inner"></div>',
                                            iconSize: [12, 12],
                                            iconAnchor: [6, 6]
                                        }}),
                                        zIndexOffset: 10000
                                    }}).addTo(map);

                                    m.on('drag', function() {{
                                        part[pIdx] = m.getLatLng();
                                        subLayer.setLatLngs(rawLatLngs);
                                    }});

                                    m.on('dragend', function() {{
                                        part[pIdx] = m.getLatLng();
                                        subLayer.setLatLngs(rawLatLngs);
                                        var geom;
                                        if (isMultiLine) {{
                                            geom = {{
                                                type: "MultiLineString",
                                                coordinates: lineParts.map(function(lp) {{
                                                    return lp.map(function(p) {{ return [p.lng, p.lat]; }});
                                                }})
                                            }};
                                        }} else {{
                                            geom = {{
                                                type: "LineString",
                                                coordinates: part.map(function(p) {{ return [p.lng, p.lat]; }})
                                            }};
                                        }}
                                        notifyFeatureUpdated(featureIdx, geom);
                                    }});

                                    vertexMarkers.push(m);
                                }});
                            }});
                        }}
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
                    if (typeof finishVertexEditMode === 'function') finishVertexEditMode();
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
                var mapMouseDownPos = null;
                map.on('mousedown', function(e) {{
                    if (e.containerPoint) mapMouseDownPos = e.containerPoint;
                    if (drawMode || measureActive) return;
                    if (e.originalEvent.button !== 0) return;

                    var isShift = e.originalEvent && e.originalEvent.shiftKey;
                    if (selectMode === 'box' || isShift) {{
                        isBoxSelecting = true;
                        map.dragging.disable();
                        boxStartLatLng = e.latlng;
                        if (boxRectLayer) {{
                            map.removeLayer(boxRectLayer);
                            boxRectLayer = null;
                        }}
                        boxRectLayer = L.rectangle([boxStartLatLng, boxStartLatLng], {{
                            color: '#0078d4',
                            weight: 1.5,
                            dashArray: '4, 4',
                            fillColor: '#0078d4',
                            fillOpacity: 0.15
                        }}).addTo(map);
                    }}
                }});

                map.on('mouseup', function(e) {{
                    if (!isBoxSelecting) return;
                    isBoxSelecting = false;
                    map.dragging.enable();
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

                    var isMulti = e.originalEvent && (e.originalEvent.ctrlKey || e.originalEvent.metaKey);
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

                    // Empty map click in click select mode -> clear selection (only if not dragged/panned)
                    var wasDragged = false;
                    if (mapMouseDownPos && e.containerPoint) {{
                        var dist = Math.hypot(e.containerPoint.x - mapMouseDownPos.x, e.containerPoint.y - mapMouseDownPos.y);
                        if (dist > 4) wasDragged = true;
                    }}
                    mapMouseDownPos = null;

                    if (!wasDragged && !e.originalEvent._layerClicked && selectMode === 'click') {{
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
                        if (vertexEditActive) finishVertexEditMode();
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

                    if (vertexEditActive) {{
                        selectedIndices.clear();
                        selectedIndices.add(currentIdx);
                        selectedFeatureIndex = currentIdx;
                        selectedFeatureLayerId = layerId;
                        refreshLayerStyles(layerId);
                        notifySelectionChanged();
                        attachVertexHandles(layerId, currentIdx);
                        return;
                    }}

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

                    if (layerId !== activeLayerId) {{
                        requestSetActiveLayer(layerId);
                    }}

                    if (pyBridge && selectedIndices.size === 1) {{
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
                            var currentIdx = (feature && feature.id !== undefined && !isNaN(parseInt(feature.id, 10)))
                                ? parseInt(feature.id, 10)
                                : featureIdx++;
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

                function setVectorLayer(layerId, name, geojsonData, isActive, geomType, color, fitBounds, isWfs) {{
                    if (!layerId) layerId = 'default';
                    name = name || 'Mekansal Katman';
                    var isWfsLayer = !!isWfs || (name && (name.indexOf('(WFS)') !== -1 || name.indexOf('[WFS]') !== -1 || name.indexOf('WFS') !== -1));

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
                        indexMap: lIndexMap,
                        isWfs: isWfsLayer
                    }};

                    if (isActive) {{
                        setActiveVectorLayer(layerId, detectedGeom);
                    }} else {{
                        renderLayersPanel();
                    }}

                    var lFlyout = document.getElementById('layersFlyout');
                    var btnL = document.getElementById('btnLayers');
                    if (lFlyout && !lFlyout.classList.contains('open')) {{
                        lFlyout.classList.add('open');
                        if (btnL) btnL.classList.add('active');
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
                    refreshLayerStyles(layerId);
                }}

                function setActiveVectorLayer(layerId, geomType) {{
                    activeLayerId = layerId;
                    Object.keys(vectorLayers).forEach(function(k) {{
                        vectorLayers[k].isActive = (k === layerId);
                    }});

                    var activeObj = vectorLayers[layerId];
                    if (activeObj) {{
                        setLayerGeometryType(geomType || activeObj.geomType);
                        if (activeObj.leafletLayer && activeObj.visible) {{
                            activeObj.leafletLayer.bringToFront();
                        }}
                    }} else {{
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
                    setLayerGeometryType('any');
                    renderLayersPanel();
                }}

                function updateLayerName(layerId, name) {{
                    if (vectorLayers[layerId]) {{
                        vectorLayers[layerId].name = name;
                        renderLayersPanel();
                    }}
                }}

                function requestSetActiveLayer(layerId) {{
                    setActiveVectorLayer(layerId);
                    if (pyBridge && pyBridge.onActiveLayerRequested) {{
                        pyBridge.onActiveLayerRequested(layerId);
                    }}
                }}

                function removeVectorLayerUi(layerId) {{
                    removeVectorLayer(layerId);
                    if (pyBridge && pyBridge.onLayerRemoved) {{
                        pyBridge.onLayerRemoved(layerId);
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

                function zoomFullExtent() {{
                    if (map.invalidateSize) map.invalidateSize();
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
                    }} else {{
                        map.setView([39.0, 35.0], 6);
                    }}
                }}

                function refreshMap() {{
                    if (map) {{
                        map.invalidateSize();
                        Object.keys(vectorLayers).forEach(function(k) {{
                            refreshLayerStyles(k);
                        }});
                        bringVectorsToFront();
                    }}
                }}

                function renderSnapshotLegend() {{
                    var legendEl = document.getElementById('snapshotLegend');
                    if (!legendEl) return;

                    var vKeys = Object.keys(vectorLayers).filter(function(k) {{ return vectorLayers[k].visible; }});
                    var wKeys = Object.keys(wmsRegistry).filter(function(k) {{ return wmsRegistry[k].visible; }});

                    if (vKeys.length === 0 && wKeys.length === 0) {{
                        legendEl.style.display = 'none';
                        return;
                    }}

                    var html = '<div class="snapshot-legend-title">🗂️ Katmanlar</div>';
                    html += '<div class="snapshot-legend-items">';

                    vKeys.forEach(function(k) {{
                        var l = vectorLayers[k];
                        var sym = getLayerSymbolHtml(l.geomType, l.color);
                        var cnt = l.count > 0 ? ' <span style="opacity:0.6; font-size:10px;">(' + l.count.toLocaleString() + ')</span>' : '';
                        html += '<div class="snapshot-legend-item">' + sym + '<span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">' + l.name + cnt + '</span></div>';
                    }});

                    wKeys.forEach(function(k) {{
                        var w = wmsRegistry[k];
                        var sym = getWmsSymbolHtml();
                        var title = w.title || w.layerName;
                        html += '<div class="snapshot-legend-item">' + sym + '<span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">' + title + '</span></div>';
                    }});

                    html += '</div>';
                    legendEl.innerHTML = html;
                    legendEl.style.display = 'block';
                }}

                function prepareSnapshotMode() {{
                    closeAllFlyouts();
                    renderSnapshotLegend();
                    if (typeof updateCoordinatesToMapCenter === 'function') {{
                        updateCoordinatesToMapCenter();
                    }}
                    document.body.classList.add('snapshot-mode');
                    return true;
                }}

                function restoreSnapshotMode() {{
                    document.body.classList.remove('snapshot-mode');
                    return true;
                }}

                function captureMapSnapshot() {{
                    if (pyBridge && pyBridge.requestCaptureSnapshot) {{
                        pyBridge.requestCaptureSnapshot();
                    }}
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
                self, "Harita Görünümünü Kaydet", "harita_gorunumu.png", "PNG Resim (*.png);;JPEG Resim (*.jpg)"
            )
            from ui.toast import ToastNotification
            if file_path:
                pixmap.save(file_path)
                ToastNotification.show_toast(self.window(), f"Harita görüntüsü kaydedildi: {os.path.basename(file_path)}", "success")
            else:
                ToastNotification.show_toast(self.window(), "Harita görüntüsü panoya kopyalandı", "info")
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