from PyQt6.QtWidgets import (
    QMainWindow,
    QMenuBar,
    QMenu,
    QFileDialog,
    QMessageBox,
    QSplitter,
    QStackedWidget,
    QLabel,
    QApplication
)
from handlers.factory import HandlerFactory
from ui.highlighter import JsonHighlighter, MarkdownHighlighter
from ui.dialogs import FindReplaceDialog, LayerSelectionDialog, CRSDialog
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent, QKeySequence
from core.workers import FileLoadWorker
from core.theme import ThemeManager
from ui.editor import ChiselCodeEditor
from PyQt6.QtCore import Qt, QTimer
import geopandas as gpd
import json
import io
import os


class MainWindow(QMainWindow):
    
    def __init__(self):
        super().__init__()
        self.current_file = None
        self.is_dirty = False
        self.highlighter = None
        self._is_loading = False
        
        self._init_ui()
        self._create_menus()

    def _init_ui(self):
            self.setWindowTitle("Chisel Editor - Untitled")
            self.resize(800, 500)
            self.splitter = QSplitter(Qt.Orientation.Horizontal)
            self.text_editor = ChiselCodeEditor()
        
            self.preview_stack = QStackedWidget()
            self.map_panel = None
            self.markdown_panel = None
    
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
    
            edit_menu: QMenu = menu_bar.addMenu("Edit")
            find_action = QAction("Find & Replace", self)
            find_action.setShortcut(QKeySequence("Ctrl+F"))
            find_action.triggered.connect(self._show_find_replace)
            edit_menu.addAction(find_action)
    
            view_menu: QMenu = menu_bar.addMenu("View")
            theme_menu: QMenu = view_menu.addMenu("Theme")
            
            light_theme_action = QAction("Light", self)
            dark_theme_action = QAction("Dark", self)
    
            light_theme_action.triggered.connect(lambda: self._change_theme("light"))
            dark_theme_action.triggered.connect(lambda: self._change_theme("dark"))
            
            theme_menu.addAction(light_theme_action)
            theme_menu.addAction(dark_theme_action)

            tools_menu: QMenu = menu_bar.addMenu("Tools")
        
            set_crs_action = QAction("Set CRS...", self)
            reproject_crs_action = QAction("Reproject CRS...", self)
            
            set_crs_action.triggered.connect(self._set_crs)
            reproject_crs_action.triggered.connect(self._reproject_crs)
            
            tools_menu.addAction(set_crs_action)
            tools_menu.addAction(reproject_crs_action)

    def _update_cursor_pos(self):
        cursor = self.text_editor.textCursor()
        line = cursor.blockNumber() + 1
        col = cursor.columnNumber() + 1
        self.cursor_label.setText(f"Ln {line}, Col {col}")

    def _on_text_changed(self):
        if self._is_loading:
            return

        if not self.text_editor.document().isModified():
            return

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

    def _open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open File",
            "",
            "All Supported Files (*.txt *.md *.geojson *.kml *.shp);;Text Files (*.txt *.md);;Spatial Files (*.geojson *.kml *.shp);;All Files (*)"
        )
        
        if file_path:
            self._load_file(file_path)

    def _save_file(self):
        if not self.current_file:
            self._save_file_as()
            return
            
        try:
            handler = HandlerFactory.get_handler(self.current_file)
            content = self.text_editor.toPlainText()
            handler.write(self.current_file, content)
            self.statusBar().showMessage("File saved successfully.", 3000)
            self.text_editor.document().setModified(False)
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
            panel = self._get_map_panel()
            panel.render_geojson(content)
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

    def _get_map_panel(self):
        if self.map_panel is None:
            from ui.preview_panels import MapPreviewPanel
            self.map_panel = MapPreviewPanel()
            self.preview_stack.addWidget(self.map_panel)
        return self.map_panel

    def _get_markdown_panel(self):
        if self.markdown_panel is None:
            from ui.preview_panels import MarkdownPreviewPanel
            self.markdown_panel = MarkdownPreviewPanel()
            self.preview_stack.addWidget(self.markdown_panel)
        return self.markdown_panel

    def _load_file(self, file_path: str, **kwargs):
        if self._is_loading:
            return
            
        self._is_loading = True
        self.statusBar().showMessage(f"Loading {os.path.basename(file_path)}...")
        
        self.worker = FileLoadWorker(file_path, **kwargs)
        self.worker.finished.connect(self._on_file_loaded)
        self.worker.start()

    def _on_file_loaded(self, file_path: str, content: str, is_spatial: bool, error_msg: str):
        self._is_loading = False
        self.statusBar().clearMessage()

        if error_msg:
            QMessageBox.critical(self, "Error", f"Could not read file:\n{error_msg}")
            return

        self.text_editor.blockSignals(True)
        try:
            self.text_editor.setPlainText(content)
            
            if self.highlighter:
                self.highlighter.setDocument(None)
                self.highlighter = None

            if is_spatial:
                self.highlighter = JsonHighlighter(self.text_editor.document())
                panel = self._get_map_panel()
                self.preview_stack.setCurrentWidget(panel)
                self.preview_stack.show()
                panel.render_content(content)
                self.type_label.setText("Spatial")
                self._set_crs(initial_check=True)
                
            elif file_path.lower().endswith('.md'):
                self.highlighter = MarkdownHighlighter(self.text_editor.document())
                panel = self._get_markdown_panel()
                self.preview_stack.setCurrentWidget(panel)
                self.preview_stack.show()
                panel.render_content(content)
                self.type_label.setText("Markdown")
                
            else:
                self.preview_stack.hide()
                self.type_label.setText("Plain Text")

        finally:
            self.text_editor.blockSignals(False)
            
        self.text_editor.document().setModified(False)
        self.current_file = file_path
        self.is_dirty = False
        self._update_title()

    def _show_find_replace(self):
        if not hasattr(self, 'find_dialog') or self.find_dialog is None:
            self.find_dialog = FindReplaceDialog(self.text_editor, self)
        
        self.find_dialog.show()
        self.find_dialog.raise_()
        self.find_dialog.activateWindow()
        self.find_dialog.find_input.setFocus()

    def _change_theme(self, theme_name: str):
        ThemeManager.apply_theme(QApplication.instance(), theme_name)
        
        if self.highlighter:
            self.highlighter.setDocument(None)
            self.highlighter = None
            
            if self.type_label.text() == "Spatial":
                self.highlighter = JsonHighlighter(self.text_editor.document())
            elif self.type_label.text() == "Markdown":
                self.highlighter = MarkdownHighlighter(self.text_editor.document())

        self.text_editor.highlight_current_line()
        self.text_editor.viewport().update()
        self.text_editor.line_number_area.update()
        self._refresh_preview()

    def _get_gdf_from_editor(self):
        content = self.text_editor.toPlainText()
        if not content.strip():
            return None
        try:
            return gpd.read_file(io.StringIO(content))
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not parse spatial data:\n{str(e)}")
            return None

    def _update_editor_with_gdf(self, gdf):
        raw_geojson = gdf.to_json()
        parsed_json = json.loads(raw_geojson)
        formatted_json = json.dumps(parsed_json, indent=4, ensure_ascii=False)
        
        self.text_editor.blockSignals(True)
        self.text_editor.setPlainText(formatted_json)
        self.text_editor.blockSignals(False)
        
        self.is_dirty = True
        self._update_title()
        
        self.preview_timer.start()

    def _set_crs(self, initial_check=False):
        if self.type_label.text() != "Spatial":
            if not initial_check:
                QMessageBox.information(self, "Not Spatial", "Current file is not recognized as spatial data.")
            return
            
        gdf = self._get_gdf_from_editor()
        if gdf is None: return
        
        current_crs = str(gdf.crs) if gdf.crs else "None"
        
        if initial_check and gdf.crs is not None:
            return
            
        dialog_title = "Set CRS (Missing!)" if initial_check else "Set CRS"
        dialog = CRSDialog(title=dialog_title, current_crs=current_crs, parent=self)
        
        if dialog.exec():
            new_crs = dialog.selected_epsg
            try:
                gdf.set_crs(new_crs, allow_override=True, inplace=True)
                self._update_editor_with_gdf(gdf)
                self.statusBar().showMessage(f"CRS successfully set to {new_crs}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "CRS Error", f"Failed to set CRS:\n{str(e)}")

    def _reproject_crs(self):
        if self.type_label.text() != "Spatial":
            QMessageBox.information(self, "Not Spatial", "Current file is not recognized as spatial data.")
            return
            
        gdf = self._get_gdf_from_editor()
        if gdf is None: return
        
        if gdf.crs is None:
            QMessageBox.warning(self, "Missing CRS", "The data has no CRS defined. Please use 'Set CRS' first before reprojecting.")
            return
            
        current_crs = str(gdf.crs)
        dialog = CRSDialog(title="Reproject CRS", current_crs=current_crs, parent=self)
        
        if dialog.exec():
            target_crs = dialog.selected_epsg
            if target_crs == current_crs:
                return
            try:
                gdf = gdf.to_crs(target_crs)
                self._update_editor_with_gdf(gdf)
                self.statusBar().showMessage(f"Successfully reprojected to {target_crs}", 4000)
            except Exception as e:
                QMessageBox.critical(self, "Reprojection Error", f"Failed to reproject CRS:\n{str(e)}")