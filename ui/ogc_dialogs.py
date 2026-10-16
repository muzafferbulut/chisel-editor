from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QSpinBox, QCheckBox, QPushButton, QMessageBox
)


class WMSDialog(QDialog):
    """
    Dialog for connecting to WMS (Web Map Service) or XYZ Tile layers.
    Includes verified free public WMS server presets and XYZ raster layers.
    """
    PRESETS = [
        ("🗺️ Terrestris OpenStreetMap WMS (Free Global)", "https://ows.terrestris.de/osm/service", "OSM-WMS"),
        ("🏔️ Terrestris Topographic OSM WMS (Free)", "https://ows.terrestris.de/osm/service", "TOPO-WMS"),
        ("🌑 Terrestris Grayscale OSM WMS (Free)", "https://ows.terrestris.de/osm/service", "OSM-Overlay-WMS"),
        ("🌍 Mundialis Global Shaded Relief WMS (Free)", "https://ows.mundialis.de/services/service", "SRTM30-Colored"),
        ("🛰️ Esri World Imagery (XYZ Tiles)", "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", "esri_satellite"),
        ("🏔️ OpenTopoMap (XYZ Tiles)", "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", "opentopomap"),
        ("🌙 CartoDB Dark Matter (XYZ Tiles)", "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", "cartodb_dark"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wms_url = ""
        self.layer_name = ""
        self.title = ""
        self.format = "image/png"
        self.transparent = True

        self.setWindowTitle("Connect WMS / Raster Tile Service")
        self.resize(520, 290)
        self.setModal(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        lbl_desc = QLabel("Enter an OGC WMS URL with layer name, or an XYZ tile template URL (e.g. {z}/{y}/{x}):")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("<b>Free Presets:</b>"))
        self.combo_presets = QComboBox()
        self.combo_presets.addItem("-- Select Free WMS / Tile Preset --", "")
        for title, url, layer in self.PRESETS:
            self.combo_presets.addItem(title, (url, layer, title))
        self.combo_presets.currentIndexChanged.connect(self._on_preset_selected)
        preset_layout.addWidget(self.combo_presets)
        layout.addLayout(preset_layout)

        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("<b>Service URL:</b>"))
        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("https://example.com/geoserver/wms or https://.../{z}/{x}/{y}.png")
        self.input_url.textChanged.connect(self._on_url_changed)
        url_layout.addWidget(self.input_url)
        layout.addLayout(url_layout)

        layer_layout = QHBoxLayout()
        self.lbl_layer = QLabel("<b>Layer Name:</b>")
        layer_layout.addWidget(self.lbl_layer)
        self.input_layer = QLineEdit()
        self.input_layer.setPlaceholderText("e.g. workspace:layer_name (required for WMS)")
        layer_layout.addWidget(self.input_layer)
        layout.addLayout(layer_layout)

        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("<b>Layer Title:</b>"))
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Display name in layer list")
        title_layout.addWidget(self.input_title)
        layout.addLayout(title_layout)

        opts_layout = QHBoxLayout()
        self.chk_transparent = QCheckBox("Transparent PNG (for overlays)")
        self.chk_transparent.setChecked(True)
        opts_layout.addWidget(self.chk_transparent)
        opts_layout.addStretch()
        layout.addLayout(opts_layout)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_add = QPushButton("Add Layer")
        btn_cancel.clicked.connect(self.reject)
        btn_add.clicked.connect(self._on_add)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_add)
        layout.addLayout(btn_layout)

    def _on_url_changed(self, text):
        if "{z}" in text.lower():
            self.input_layer.setPlaceholderText("Optional for XYZ tiles")
        else:
            self.input_layer.setPlaceholderText("e.g. workspace:layer_name (required for WMS)")

    def _on_preset_selected(self, index):
        data = self.combo_presets.currentData()
        if data:
            url, layer, title = data
            self.input_url.setText(url)
            self.input_layer.setText(layer)
            clean_title = title.split("(")[0].strip()
            self.input_title.setText(clean_title)

    def _on_add(self):
        url = self.input_url.text().strip()
        layer = self.input_layer.text().strip()
        title = self.input_title.text().strip()

        if not url:
            QMessageBox.warning(self, "Missing URL", "Please specify a service URL.")
            return

        is_xyz = "{z}" in url.lower()
        if not layer:
            if is_xyz:
                layer = title or "tiles"
            else:
                QMessageBox.warning(self, "Missing Layer", "Please specify a Layer Name for WMS services.")
                return

        if not title:
            title = layer

        self.wms_url = url
        self.layer_name = layer
        self.title = title
        self.format = "image/png"
        self.transparent = self.chk_transparent.isChecked()
        self.accept()


class WFSDialog(QDialog):
    """
    Dialog for downloading vector features via WFS (Web Feature Service).
    Includes verified public WFS presets.
    """
    PRESETS = [
        ("USGS Earthquakes WFS (Recent)", "https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&limit=100", "earthquakes"),
        ("Terrestris OpenStreetMap Admin WFS", "https://ows.terrestris.de/osm/service?service=WFS&version=2.0.0&request=GetFeature&typeNames=osm:osm_admin_boundaries&outputFormat=application/json&count=100", "osm_admin")
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wfs_url = ""
        self.type_name = ""
        self.limit = 500

        self.setWindowTitle("Download WFS Vector Data (Web Feature Service)")
        self.resize(520, 260)
        self.setModal(True)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 18, 18, 18)

        lbl_desc = QLabel("Enter a WFS endpoint or GetFeature URL to load vector features into editor & map:")
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("<b>Free Presets:</b>"))
        self.combo_presets = QComboBox()
        self.combo_presets.addItem("-- Select Free WFS Preset --", "")
        for title, url, tname in self.PRESETS:
            self.combo_presets.addItem(title, (url, tname))
        self.combo_presets.currentIndexChanged.connect(self._on_preset_selected)
        preset_layout.addWidget(self.combo_presets)
        layout.addLayout(preset_layout)

        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("<b>WFS URL:</b>"))
        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("https://example.com/geoserver/wfs or full GetFeature URL")
        url_layout.addWidget(self.input_url)
        layout.addLayout(url_layout)

        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("<b>Feature Type (typename):</b>"))
        self.input_typename = QLineEdit()
        self.input_typename.setPlaceholderText("e.g. cities, roads, parcel (leave empty if full URL)")
        type_layout.addWidget(self.input_typename)
        layout.addLayout(type_layout)

        limit_layout = QHBoxLayout()
        limit_layout.addWidget(QLabel("<b>Max Features:</b>"))
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(1, 100000)
        self.spin_limit.setValue(500)
        limit_layout.addWidget(self.spin_limit)
        limit_layout.addStretch()
        layout.addLayout(limit_layout)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_fetch = QPushButton("Download Features")
        btn_cancel.clicked.connect(self.reject)
        btn_fetch.clicked.connect(self._on_fetch)

        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_fetch)
        layout.addLayout(btn_layout)

    def _on_preset_selected(self, index):
        data = self.combo_presets.currentData()
        if data:
            url, tname = data
            self.input_url.setText(url)
            self.input_typename.setText(tname)

    def _on_fetch(self):
        url = self.input_url.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Please enter a WFS URL.")
            return

        self.wfs_url = url
        self.type_name = self.input_typename.text().strip()
        self.limit = self.spin_limit.value()
        self.accept()
