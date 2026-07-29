from PyQt6.QtWidgets import (
    QMainWindow,
    QMenuBar,
    QMenu,
    QFileDialog,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QLabel,
)
from handlers.factory import HandlerFactory
from ui.highlighter import JsonHighlighter, MarkdownHighlighter
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent
from .editor import ChiselCodeEditor
from handlers.spatial import MultipleLayersError
from ui.dialogs import LayerSelectionDialog
from ui.preview_panels import MapPreviewPanel, MarkdownPreviewPanel
from PyQt6.QtCore import Qt, QTimer
import os

class MainWindow(QMainWindow):
    
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.is_dirty = False
        self.highlighter = None
        
        self._init_ui()
        self._create_menus()

    def _init_ui(self):
            self.setWindowTitle("Chisel Editor - Untitled")
            self.resize(800, 500)
            self.splitter = QSplitter(Qt.Orientation.Horizontal)
            self.text_editor = ChiselCodeEditor()
        
            self.preview_stack = QStackedWidget()
            self.map_panel = MapPreviewPanel()
            self.markdown_panel = MarkdownPreviewPanel()
    
            self.preview_stack.addWidget(self.map_panel)
            self.preview_stack.addWidget(self.markdown_panel)
            self.preview_stack.hide()
    
            self.preview_timer = QTimer()
            self.preview_timer.setSingleShot(True)
            self.preview_timer.setInterval(800)
            self.preview_timer.timeout.connect(self._refresh_preview)
    
            self.splitter.addWidget(self.text_editor)
            self.splitter.addWidget(self.preview_stack)
            self.splitter.setSizes([480, 720])
            self.setCentralWidget(self.splitter)
    
            self.setAcceptDrops(True)
            self.text_editor.file_dropped.connect(self._load_file)

            self.status_bar = self.statusBar()
            self.cursor_label = QLabel("Ln 1, Col 1")
            self.type_label = QLabel("Plain Text")
            
            self.status_bar.addPermanentWidget(self.cursor_label)
            self.status_bar.addPermanentWidget(self.type_label)
            self.text_editor.cursorPositionChanged.connect(self._update_cursor_pos)
            self.text_editor.textChanged.connect(self._on_text_changed)

    def _update_cursor_pos(self):
        cursor = self.text_editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.cursor_label.setText(f"Ln {line}, Col {col}")

    def _on_text_changed(self):
        if self.current_file:
            self.preview_timer.start()

        if not self.is_dirty:
            self.is_dirty = True
            self._update_title()

    def _update_title(self):
        title = "Chisel Editor - "
        if self.current_file:
            import os
            title += os.path.basename(self.current_file)
        else:
            title += "Untitled"

        if self.is_dirty:
            title += " *"
            
        self.setWindowTitle(title)
        
    def closeEvent(self, event):
        if self.is_dirty:
            reply = QMessageBox.warning(
                self, 
                "Unsaved Changes",
                "You have unsaved changes. Are you sure you want to exit without saving?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def _create_menus(self):
        menu_bar: QMenuBar = self.menuBar()

        file_menu: QMenu = menu_bar.addMenu("File")
        
        open_action = QAction("Open...", self)
        save_action = QAction("Save", self)
        save_as_action = QAction("Save As...", self)
        exit_action = QAction("Exit", self)
        
        open_action.triggered.connect(self._open_file)
        save_action.triggered.connect(self._save_file)
        save_as_action.triggered.connect(self._save_file_as)
        exit_action.triggered.connect(self.close)
        
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

    def _open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            "",
            "All Supported Files (*.txt *.md *.geojson *.kml *.shp);;Text Files (*.txt *.md);;Spatial Files (*.geojson *.kml *.shp);;All Files (*)"
        )
        
        if file_path:
            self._load_file(file_path)

    def _load_file(self, file_path: str, **kwargs):
        try:
            handler = HandlerFactory.get_handler(file_path)
            content = handler.read(file_path, **kwargs)

            self.text_editor.blockSignals(True)
            try:
                self.text_editor.setPlainText(content)
            finally:
                self.text_editor.blockSignals(False)
            
            self.current_file = file_path
            self.is_dirty = False 
            self._update_title()

            if self.highlighter:
                self.highlighter.setDocument(None)
                self.highlighter = None

            if handler.is_spatial:
                self.highlighter = JsonHighlighter(self.text_editor.document())
                self.preview_stack.setCurrentWidget(self.map_panel)
                self.preview_stack.show()
                self.map_panel.render_content(content)
                self.type_label.setText("Spatial")
                
            elif file_path.lower().endswith('.md'):
                self.highlighter = MarkdownHighlighter(self.text_editor.document())
                self.preview_stack.setCurrentWidget(self.markdown_panel)
                self.preview_stack.show()
                self.markdown_panel.render_content(content)
                self.type_label.setText("Markdown")
                
            else:
                self.preview_stack.hide()
                self.type_label.setText("Plain Text")
                    
        except MultipleLayersError as e:
            dialog = LayerSelectionDialog(os.path.basename(file_path), e.layers, self)
            if dialog.exec():
                if dialog.merge_all:
                    self._load_file(file_path, merge_all=True)
                elif dialog.selected_layer:
                    self._load_file(file_path, layer_name=dialog.selected_layer)
                    
        except ValueError as e:
            QMessageBox.warning(self, "Unsupported File", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not read file:\n{str(e)}")

    def _save_file(self):
        if not self.current_file:
            self._save_file_as()
            return
            
        try:
            handler = HandlerFactory.get_handler(self.current_file)
            content = self.text_editor.toPlainText()
            handler.write(self.current_file, content)
            self.statusBar().showMessage("File saved successfully.", 3000)
            
            self.is_dirty = False
            self._update_title()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{str(e)}")

    def _save_file_as(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save File As",
            "",
            "All Supported Files (*.txt *.md *.geojson *.kml *.shp);;Text Files (*.txt *.md);;Spatial Files (*.geojson *.kml *.shp);;All Files (*)"
        )
        
        if file_path:
            self.current_file = file_path
            self.setWindowTitle(f"Chisel Editor - {os.path.basename(file_path)}")
            self._save_file()

    def _update_map_preview(self):
        content = self.text_editor.toPlainText()
        if content.strip():
            self.map_panel.render_geojson(content)
            self.statusBar().showMessage("Map updated.", 3000)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            file_path = urls[0].toLocalFile()
            if os.path.isfile(file_path):
                self._load_file(file_path)

    def _refresh_preview(self):
        if not self.current_file:
            return
            
        content = self.text_editor.toPlainText()
        active_panel = self.preview_stack.currentWidget()
        
        if active_panel and self.preview_stack.isVisible():
            active_panel.render_content(content)