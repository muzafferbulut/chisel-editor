from PyQt6.QtWidgets import QWidget, QSplitter, QStackedWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from ui.editor import ChiselCodeEditor
from ui.preview_panels import MapPreviewPanel, MarkdownPreviewPanel
import os

class EditorTab(QWidget):
    
    state_changed = pyqtSignal()


    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self.is_dirty = False
        self.highlighter = None
        self.file_type = "Plain Text"
        self._is_loading = False

        self._init_ui()


    def _init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.text_editor = ChiselCodeEditor()
        
        self.preview_stack = QStackedWidget()
        
        self.map_panel = None
        self.markdown_panel = None
        self.preview_stack.hide()
        
        self.splitter.addWidget(self.text_editor)
        self.splitter.addWidget(self.preview_stack)
        self.splitter.setSizes([480, 720])
        
        self.layout.addWidget(self.splitter)
        
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(500)
        self.preview_timer.timeout.connect(self._refresh_preview)
        self.text_editor.textChanged.connect(self._on_text_changed)


    def get_map_panel(self):
        if self.map_panel is None:
            self.map_panel = MapPreviewPanel()
            self.preview_stack.addWidget(self.map_panel)
        return self.map_panel


    def get_markdown_panel(self):
        if self.markdown_panel is None:
            self.markdown_panel = MarkdownPreviewPanel()
            self.preview_stack.addWidget(self.markdown_panel)
        return self.markdown_panel


    def _on_text_changed(self):
        if self._is_loading or not self.text_editor.document().isModified(): 
            return
            
        self.preview_timer.start()
        if not self.is_dirty:
            self.is_dirty = True
            self.state_changed.emit()


    def _refresh_preview(self):
        content = self.text_editor.toPlainText()
        if self.preview_stack.isVisible():
            active_panel = self.preview_stack.currentWidget()
            active_panel.render_content(content)


    def get_title(self):
        title = os.path.basename(self.current_file) if self.current_file else "Untitled"
        if self.is_dirty:
            title += " *"
        return title