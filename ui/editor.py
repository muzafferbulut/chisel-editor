import json
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import pyqtSignal, QObject, QUrl, pyqtSlot
from core.theme import ThemeManager


class EditorBridge(QObject):
    textChanged = pyqtSignal(str)

    @pyqtSlot(str)
    def onTextChanged(self, text):
        self.textChanged.emit(text)


class MonacoEditor(QWidget):
    textChanged = pyqtSignal()
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.web_view = QWebEngineView()
        self.web_view.setAcceptDrops(False) 
        self.setAcceptDrops(True)
        self.layout.addWidget(self.web_view)
        
        self.bridge = EditorBridge()
        self.bridge.textChanged.connect(self._internal_text_changed)
        
        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        
        self._current_text = ""
        self._is_loaded = False
        self._pending_text = ""
        
        self.web_view.loadFinished.connect(self._on_load_finished)
        self._init_editor()

    def _init_editor(self):
        theme = "vs-dark" if ThemeManager._current_theme == "dark" else "vs"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style> body, html, #container {{ margin: 0; padding: 0; height: 100vh; overflow: hidden; }} </style>
            <!-- PyQt WebChannel Script'i otomatik yükler -->
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/require.js/2.3.6/require.min.js"></script>
            <script>
                require.config({{ paths: {{ 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs' }}}});
                require(['vs/editor/editor.main'], function() {{
                    window.editor = monaco.editor.create(document.getElementById('container'), {{
                        value: "",
                        language: 'plaintext',
                        theme: '{theme}',
                        automaticLayout: true,
                        minimap: {{ enabled: true }},
                        wordWrap: 'on'
                    }});
                    
                    new QWebChannel(qt.webChannelTransport, function(channel) {{
                        window.bridge = channel.objects.bridge;
                        editor.onDidChangeModelContent(function(e) {{
                            bridge.onTextChanged(editor.getValue());
                        }});
                    }});
                }});
            </script>
        </head>
        <body>
            <div id="container"></div>
        </body>
        </html>
        """
        self.web_view.setHtml(html_content, QUrl("qrc:/"))

    def _on_load_finished(self, ok):
        if ok:
            self._is_loaded = True
            if self._pending_text:
                self.setPlainText(self._pending_text)
                self._pending_text = ""

    def _internal_text_changed(self, text):
        self._current_text = text
        self.textChanged.emit()

    def toPlainText(self):
        return self._current_text

    def setPlainText(self, text):
        self._current_text = text
        if self._is_loaded:
            escaped = json.dumps(text)
            self.web_view.page().runJavaScript(f"editor.setValue({escaped});")
        else:
            self._pending_text = text

    def set_language(self, language: str):
        if self._is_loaded:
            self.web_view.page().runJavaScript(f"monaco.editor.setModelLanguage(editor.getModel(), '{language}');")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if os.path.isfile(file_path):
                    self.file_dropped.emit(file_path)