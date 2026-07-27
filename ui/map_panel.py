import io
import folium
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QVBoxLayout, QWidget
from PyQt6.QtCore import QTimer

class MapPanel(QWidget):
    
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.web_view = QWebEngineView()
        self.layout.addWidget(self.web_view)
        QTimer.singleShot(0, self.render_empty_map)

    def render_empty_map(self):
        m = folium.Map(location=[39.0, 35.0], zoom_start=5)
        self._set_map_html(m)

    def render_geojson(self, geojson_str: str):
        try:
            m = folium.Map()
            gj = folium.GeoJson(geojson_str)
            gj.add_to(m)
            
            bounds = gj.get_bounds()
            if bounds:
                m.fit_bounds(bounds)
            
            self._set_map_html(m)
        except Exception as e:
            print(f"Map rendering error: {e}")

    def _set_map_html(self, folium_map: folium.Map):
        data = io.BytesIO()
        folium_map.save(data, close_file=False)
        self.web_view.setHtml(data.getvalue().decode())