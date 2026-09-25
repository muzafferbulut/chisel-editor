import json
import markdown
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from core.theme import ThemeManager


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


    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_map()


    def _init_map(self):
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
            <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
            <style>
                body { margin: 0; padding: 0; }
                #map { width: 100vw; height: 100vh; background: #1e1e1e; }
            </style>
        </head>
        <body>
            <div id="map"></div>
            <script>
                var map = L.map('map').setView([0, 0], 2);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);
                var geojsonLayer = null;

                function updateMap(geojsonData) {
                    if (geojsonLayer) {
                        map.removeLayer(geojsonLayer);
                    }
                    geojsonLayer = L.geoJSON(geojsonData).addTo(map);
                    if (geojsonLayer.getBounds().isValid()) {
                        map.fitBounds(geojsonLayer.getBounds());
                    }
                }
            </script>
        </body>
        </html>
        """
        self.web_view.setHtml(html_content)


    def render_content(self, content: str):
        try:
            json.loads(content)
            js_code = f"updateMap({content});"
            self.web_view.page().runJavaScript(js_code)
        except Exception:
            pass


class MarkdownPreviewPanel(AbstractPreviewPanel):


    def render_content(self, content: str):
        try:
            raw_html = markdown.markdown(content, extensions=['extra'])
            bg_color = "#1e1e1e" if ThemeManager._current_theme == "dark" else "#ffffff"
            text_color = "#cccccc" if ThemeManager._current_theme == "dark" else "#24292e"
            styled_html = f"""
            <html>
            <body style="font-family: -apple-system, sans-serif; color: {text_color}; background-color: {bg_color}; padding: 20px; font-size: 14px; line-height: 1.6;">
                {raw_html}
            </body>
            </html>
            """
            self.web_view.setHtml(styled_html)
        except Exception as e:
            print(f"Markdown rendering error: {e}")