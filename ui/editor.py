import json
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

    def __init__(self, parent=None, lazy: bool = True):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setAcceptDrops(True)

        self.bridge = EditorBridge()
        self.bridge.textChanged.connect(self._internal_text_changed)
        self.bridge.cursorPositionChanged.connect(self.cursorPositionChanged.emit)
        self.bridge.editorReady.connect(self._on_editor_ready)

        self._current_text = ""
        self._is_initialized = False
        self._is_ready = False
        self._pending_text = None
        self._pending_language = None
        self._pending_theme = None
        self.web_view = None

        if not lazy:
            self.ensure_initialized()

    def showEvent(self, event):
        self.ensure_initialized()
        super().showEvent(event)

    def ensure_initialized(self):
        if not self._is_initialized:
            self._is_initialized = True
            self.web_view = QWebEngineView()
            self.web_view.setAcceptDrops(False)
            self.layout.addWidget(self.web_view)

            self.channel = QWebChannel()
            self.channel.registerObject("bridge", self.bridge)
            self.web_view.page().setWebChannel(self.channel)
            self._init_editor()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if file_path:
                self.file_dropped.emit(file_path)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def _init_editor(self):
        theme = "vs-dark" if ThemeManager.is_dark() else "vs"
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8"/>
            <style>
                body, html, #container {{ margin: 0; padding: 0; width: 100vw; height: 100vh; overflow: hidden; }}
            </style>
            <script>
                window._editorReady = false;
                window._cmdQueue = [];

                window.safeSetValue = function(val) {{
                    if (window._editorReady && window.editor) {{
                        window.editor.setValue(val);
                    }} else {{
                        window._cmdQueue.push(function() {{ window.editor.setValue(val); }});
                    }}
                }};

                window.safeSetLanguage = function(lang) {{
                    if (window._editorReady && window.editor && typeof monaco !== 'undefined') {{
                        monaco.editor.setModelLanguage(window.editor.getModel(), lang);
                    }} else {{
                        window._cmdQueue.push(function() {{
                            monaco.editor.setModelLanguage(window.editor.getModel(), lang);
                        }});
                    }}
                }};

                window.safeSetTheme = function(theme) {{
                    if (window._editorReady && typeof monaco !== 'undefined') {{
                        monaco.editor.setTheme(theme);
                    }} else {{
                        window._cmdQueue.push(function() {{ monaco.editor.setTheme(theme); }});
                    }}
                }};

                window.safeFindAndReplace = function(findText, replaceText) {{
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
                }};

                window.safeTriggerFind = function() {{
                    if (window._editorReady && window.editor) {{
                        window.editor.focus();
                        var act = window.editor.getAction('actions.find');
                        if (act) {{
                            act.run();
                        }} else {{
                            window.editor.trigger('keyboard', 'actions.find', null);
                        }}
                    }} else {{
                        window._cmdQueue.push(function() {{
                            window.safeTriggerFind();
                        }});
                    }}
                }};

                window.safeTriggerReplace = function() {{
                    if (window._editorReady && window.editor) {{
                        window.editor.focus();
                        var act = window.editor.getAction('editor.action.startFindReplaceAction');
                        if (act) {{
                            act.run();
                        }} else {{
                            var findAct = window.editor.getAction('actions.find');
                            if (findAct) findAct.run();
                        }}
                    }} else {{
                        window._cmdQueue.push(function() {{
                            window.safeTriggerReplace();
                        }});
                    }}
                }};
            </script>
            <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/require.js/2.3.6/require.min.js"></script>
            <script>
                function initBridge() {{
                    if (typeof QWebChannel !== 'undefined' && typeof qt !== 'undefined' && qt.webChannelTransport) {{
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
                    }} else {{
                        setTimeout(initBridge, 20);
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
                        fontSize: 13,
                        find: {{
                            addExtraSpaceOnTop: true,
                            autoFindInSelection: 'multiline',
                            seedSearchStringFromSelection: 'always'
                        }}
                    }});

                    window._editorReady = true;

                    while (window._cmdQueue.length > 0) {{
                        var fn = window._cmdQueue.shift();
                        try {{ fn(); }} catch(err) {{ console.error('Queue execution error:', err); }}
                    }}

                    initBridge();
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
        if self._pending_theme is not None:
            self.setTheme(self._pending_theme)
            self._pending_theme = None
        if self._pending_language is not None:
            self.setLanguage(self._pending_language)
            self._pending_language = None
        if self._pending_text is not None:
            self.setPlainText(self._pending_text)
            self._pending_text = None
        elif self._current_text:
            self.setPlainText(self._current_text)

    def _internal_text_changed(self, text):
        self._current_text = text
        self.textChanged.emit()

    def toPlainText(self):
        return self._current_text

    def setPlainText(self, text):
        self._current_text = text
        if not self._is_initialized or not self._is_ready:
            self._pending_text = text
            return
        escaped = json.dumps(text)
        self.web_view.page().runJavaScript(f"safeSetValue({escaped});")

    def setLanguage(self, language: str):
        if not self._is_initialized or not self._is_ready:
            self._pending_language = language
            return
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
        if not self._is_initialized or not self._is_ready:
            self._pending_theme = theme
            return
        monaco_theme = "vs-dark" if ThemeManager.is_dark(theme) else "vs"
        escaped = json.dumps(monaco_theme)
        self.web_view.page().runJavaScript(f"safeSetTheme({escaped});")

    def find_and_replace(self, find_text: str, replace_text: str):
        self.ensure_initialized()
        if not self._is_ready:
            return
        escaped_find = json.dumps(find_text)
        escaped_replace = json.dumps(replace_text)
        self.web_view.page().runJavaScript(f"safeFindAndReplace({escaped_find}, {escaped_replace});")

    def trigger_find(self):
        self.ensure_initialized()
        if self._is_ready:
            self.web_view.page().runJavaScript("safeTriggerFind();")

    def trigger_replace(self):
        self.ensure_initialized()
        if self._is_ready:
            self.web_view.page().runJavaScript("safeTriggerReplace();")