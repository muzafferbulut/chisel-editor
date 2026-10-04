import json
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import pyqtSignal, QObject, QUrl, pyqtSlot
from core.theme import ThemeManager


class EditorBridge(QObject):
    textChanged = pyqtSignal(str)
    editorReady = pyqtSignal()
    cursorPositionChanged = pyqtSignal(int, int)

    @pyqtSlot(str)
    def onTextChanged(self, text):
        self.textChanged.emit(text)

    @pyqtSlot()
    def onEditorReady(self):
        self.editorReady.emit()

    @pyqtSlot(int, int)
    def onCursorPositionChanged(self, line, col):
        self.cursorPositionChanged.emit(line, col)


class MonacoEditor(QWidget):
    textChanged = pyqtSignal()
    cursorPositionChanged = pyqtSignal(int, int)
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
        self.bridge.cursorPositionChanged.connect(self.cursorPositionChanged.emit)
        self.bridge.editorReady.connect(self._on_editor_ready)

        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        self._current_text = ""
        self._is_ready = False
        self._pending_text = None
        self._pending_language = None

        self._init_editor()

    def _init_editor(self):
        theme = "vs-dark" if ThemeManager._current_theme == "dark" else "vs"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8"/>
            <style>
                body, html, #container {{ margin: 0; padding: 0; width: 100vw; height: 100vh; overflow: hidden; }}
            </style>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/require.js/2.3.6/require.min.js"></script>
            <script>
                window._editorReady = false;
                window._cmdQueue = [];

                function safeSetValue(val) {{
                    if (window._editorReady && window.editor) {{
                        window.editor.setValue(val);
                    }} else {{
                        window._cmdQueue.push(function() {{ window.editor.setValue(val); }});
                    }}
                }}

                function safeSetLanguage(lang) {{
                    if (window._editorReady && window.editor && typeof monaco !== 'undefined') {{
                        monaco.editor.setModelLanguage(window.editor.getModel(), lang);
                    }} else {{
                        window._cmdQueue.push(function() {{
                            monaco.editor.setModelLanguage(window.editor.getModel(), lang);
                        }});
                    }}
                }}

                function safeSetTheme(theme) {{
                    if (window._editorReady && typeof monaco !== 'undefined') {{
                        monaco.editor.setTheme(theme);
                    }} else {{
                        window._cmdQueue.push(function() {{ monaco.editor.setTheme(theme); }});
                    }}
                }}

                function safeFindAndReplace(findText, replaceText) {{
                    if (window._editorReady && window.editor) {{
                        var model = window.editor.getModel();
                        var matches = model.findMatches(findText, false, false, false, null, true);
                        if (matches && matches.length > 0) {{
                            var edits = matches.map(function(m) {{
                                return {{ range: m.range, text: replaceText }};
                            }});
                            window.editor.executeEdits('find-replace', edits);
                        }}
                    }}
                }}

                require.config({{ paths: {{ 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs' }}}});
                require(['vs/editor/editor.main'], function() {{
                    window.editor = monaco.editor.create(document.getElementById('container'), {{
                        value: "",
                        language: 'plaintext',
                        theme: '{theme}',
                        automaticLayout: true,
                        minimap: {{ enabled: true }},
                        wordWrap: 'on',
                        scrollBeyondLastLine: false,
                        fontSize: 13
                    }});

                    window._editorReady = true;

                    while (window._cmdQueue.length > 0) {{
                        var fn = window._cmdQueue.shift();
                        try {{ fn(); }} catch(err) {{ console.error('Queue execution error:', err); }}
                    }}

                    new QWebChannel(qt.webChannelTransport, function(channel) {{
                        window.bridge = channel.objects.bridge;
                        if (window.bridge) {{
                            window.bridge.onEditorReady();
                            window.editor.onDidChangeModelContent(function(e) {{
                                window.bridge.onTextChanged(window.editor.getValue());
                            }});
                            window.editor.onDidChangeCursorPosition(function(e) {{
                                window.bridge.onCursorPositionChanged(e.position.lineNumber, e.position.column);
                            }});
                        }}
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

    def _on_editor_ready(self):
        self._is_ready = True
        if self._pending_text is not None:
            self.setPlainText(self._pending_text)
            self._pending_text = None
        if self._pending_language is not None:
            self.setLanguage(self._pending_language)
            self._pending_language = None

    def _internal_text_changed(self, text):
        self._current_text = text
        self.textChanged.emit()

    def toPlainText(self):
        return self._current_text

    def setPlainText(self, text):
        self._current_text = text
        escaped = json.dumps(text)
        self.web_view.page().runJavaScript(f"safeSetValue({escaped});")

    def setLanguage(self, language: str):
        lang_map = {
            "JSON": "json",
            "GeoJSON": "json",
            "Python": "python",
            "Markdown": "markdown",
            "HTML": "html",
            "CSS": "css",
            "JavaScript": "javascript",
            "XML": "xml",
            "KML": "xml",
            "SQL": "sql",
            "CSV": "plaintext"
        }
        monaco_lang = lang_map.get(language, "plaintext")
        escaped = json.dumps(monaco_lang)
        self.web_view.page().runJavaScript(f"safeSetLanguage({escaped});")

    def setTheme(self, theme: str):
        monaco_theme = "vs-dark" if theme == "dark" else "vs"
        escaped = json.dumps(monaco_theme)
        self.web_view.page().runJavaScript(f"safeSetTheme({escaped});")

    def find_and_replace(self, find_text: str, replace_text: str):
        escaped_find = json.dumps(find_text)
        escaped_replace = json.dumps(replace_text)
        self.web_view.page().runJavaScript(f"safeFindAndReplace({escaped_find}, {escaped_replace});")