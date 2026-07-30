import json
import markdown
import folium
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

    def render_content(self, content: str):
        try:
            json.loads(content)
            tiles = ThemeManager.get_map_tiles()
            m = folium.Map(tiles=tiles)
            gj = folium.GeoJson(content)
            gj.add_to(m)
            
            bounds = gj.get_bounds()
            if bounds:
                m.fit_bounds(bounds)
            
            self.web_view.setHtml(m.get_root().render())
        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(f"Map rendering error: {e}")


class MarkdownPreviewPanel(AbstractPreviewPanel):

    def render_content(self, content: str):
        try:
            raw_html = markdown.markdown(content, extensions=['extra'])
            
            bg_color = "#1e1e1e" if ThemeManager._current_theme == "dark" else "#ffffff"
            text_color = "#cccccc" if ThemeManager._current_theme == "dark" else "#24292e"
            
            styled_html = f"""
            <html>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                         color: {text_color}; background-color: {bg_color}; padding: 20px; font-size: 14px; 
                         line-height: 1.6;">
                {raw_html}
            </body>
            </html>
            """
            self.web_view.setHtml(styled_html)
        except Exception as e:
            print(f"Markdown rendering error: {e}")