from PyQt6.QtWidgets import (
    QMainWindow,
    QMenuBar,
    QMenu,
    QFileDialog,
    QMessageBox,
    QSplitter,
)
from handlers.factory import HandlerFactory
from ui.highlighter import JsonHighlighter, MarkdownHighlighter
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent
from .editor import ChiselCodeEditor
from handlers.spatial import MultipleLayersError
from ui.dialogs import LayerSelectionDialog
from ui.map_panel import MapPanel
from PyQt6.QtCore import Qt
import os

class MainWindow(QMainWindow):
    
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.highlighter = None
        self._init_ui()
        self._create_menus()

    def _init_ui(self):
        self.setWindowTitle("Chisel Editor - Untitled")
        self.resize(1200, 800)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.text_editor = ChiselCodeEditor()
        self.map_panel = MapPanel()
        self.splitter.addWidget(self.text_editor)
        self.splitter.addWidget(self.map_panel)
        self.map_panel.hide()
        self.setAcceptDrops(True)
        self.splitter.setSizes([480, 720])
        self.setCentralWidget(self.splitter)
        self.text_editor.file_dropped.connect(self._load_file)

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

        view_menu: QMenu = menu_bar.addMenu("View")
        update_map_action = QAction("Update Map Preview", self)
        update_map_action.setShortcut("Ctrl+R")  # Kısa yol ekledik
        update_map_action.triggered.connect(self._update_map_preview)
        view_menu.addAction(update_map_action)

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
            self.text_editor.setPlainText(content)
            self.current_file = file_path
            self.setWindowTitle(f"Chisel Editor - {os.path.basename(file_path)}")
            
            if self.highlighter:
                self.highlighter.setDocument(None)
                self.highlighter = None

            if handler.is_spatial:
                self.highlighter = JsonHighlighter(self.text_editor.document())
                self.map_panel.show()
                self.map_panel.render_geojson(content)
            else:
                self.map_panel.hide()
                if file_path.lower().endswith('.md'):
                    self.highlighter = MarkdownHighlighter(self.text_editor.document())
                    
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