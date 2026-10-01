from PyQt6.QtWidgets import (
    QMainWindow,QMenuBar,QMenu,QFileDialog,QMessageBox,
    QLabel,QApplication,QTabWidget
)
from handlers.factory import HandlerFactory
from ui.dialogs import CRSDialog, CommandPaletteDialog
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent, QKeySequence, QShortcut
from core.workers import FileLoadWorker
from core.theme import ThemeManager
from ui.tabs import EditorTab
import geopandas as gpd
import json
import io
import os


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._is_loading = False
        self._init_ui()
        self._create_menus()

    def _init_ui(self):
        self.setWindowTitle("Chisel Editor")
        self.resize(1000, 600)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setDocumentMode(True) 
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        
        self.setCentralWidget(self.tab_widget)
        
        self.status_bar = self.statusBar()
        self.cursor_label = QLabel("Ln 1, Col 1")
        self.type_label = QLabel("Plain Text")
        
        self.status_bar.addPermanentWidget(self.cursor_label)
        self.status_bar.addPermanentWidget(self.type_label)
        
        self.setAcceptDrops(True)

        self._add_new_tab()

        self.cmd_shortcut = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        self.cmd_shortcut.activated.connect(self._show_command_palette)

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
        
    def closeEvent(self, event):
        has_unsaved_changes = False
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if hasattr(tab, 'is_dirty') and tab.is_dirty:
                has_unsaved_changes = True
                break

        if has_unsaved_changes:
            reply = QMessageBox.warning(
                self, 
                "Unsaved Changes",
                "You have unsaved changes in one or more tabs. Are you sure you want to exit without saving?",
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
        tab = self._get_current_tab()
        if not tab: return
        
        if not tab.current_file:
            self._save_file_as()
            return
            
        try:
            handler = HandlerFactory.get_handler(tab.current_file)
            handler.write(tab.current_file, tab.text_editor.toPlainText())
            self.statusBar().showMessage("File saved successfully.", 3000)
            tab.is_dirty = False
            self._update_tab_title(tab)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save file:\n{str(e)}")

    def _save_file_as(self):
        tab = self._get_current_tab()
        if not tab: return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save File As", "", "All Supported Files (*.txt *.md *.geojson *.kml *.shp);;All Files (*)")
        if file_path:
            tab.current_file = file_path
            self._save_file()
            self._on_tab_changed(self.tab_widget.indexOf(tab))

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

    def _load_file(self, file_path: str, **kwargs):
        if self._is_loading: return
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

        current_tab = self._get_current_tab()
        if current_tab and current_tab.current_file is None and not current_tab.is_dirty and not current_tab.text_editor.toPlainText():
            tab = current_tab
        else:
            tab = self._add_new_tab()

        tab.text_editor.blockSignals(True)
        try:
            tab.text_editor.setPlainText(content)
            tab.current_file = file_path
            
            if is_spatial:
                tab.text_editor.set_language("json")
                tab.preview_stack.setCurrentWidget(tab.get_map_panel())
                tab.preview_stack.show()
                tab.get_map_panel().render_content(content)
                tab.file_type = "Spatial"
                
            elif file_path.lower().endswith('.md'):
                tab.text_editor.set_language("markdown")
                tab.preview_stack.setCurrentWidget(tab.get_markdown_panel())
                tab.preview_stack.show()
                tab.get_markdown_panel().render_content(content)
                tab.file_type = "Markdown"
            else:
                tab.preview_stack.hide()
                tab.file_type = "Plain Text"

        finally:
            tab.text_editor.blockSignals(False)
            
        tab.is_dirty = False
        self._update_tab_title(tab)
        self._on_tab_changed(self.tab_widget.indexOf(tab))
        
        if is_spatial:
            self._set_crs(initial_check=True)

    def _show_find_replace(self):
        tab = self._get_current_tab()
        if tab:
            tab.text_editor.web_view.page().runJavaScript("editor.getAction('actions.find').run();")

    def _change_theme(self, theme_name: str):
        ThemeManager.apply_theme(QApplication.instance(), theme_name)
        monaco_theme = "vs-dark" if theme_name == "dark" else "vs"
        
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            
            if hasattr(tab.text_editor, 'web_view') and getattr(tab.text_editor, '_is_loaded', False):
                tab.text_editor.web_view.page().runJavaScript(f"monaco.editor.setTheme('{monaco_theme}');")
            
            if hasattr(tab, '_refresh_preview'):
                tab._refresh_preview()

    def _get_gdf_from_editor(self):
        tab = self._get_current_tab()
        if not tab: 
            return None
            
        content = tab.text_editor.toPlainText()
        if not content.strip():
            return None
            
        try:
            return gpd.read_file(io.StringIO(content))
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not parse spatial data:\n{str(e)}")
            return None

    def _update_editor_with_gdf(self, gdf):
        tab = self._get_current_tab()
        if not tab: 
            return
            
        tab.text_editor.blockSignals(True)
        tab.text_editor.setPlainText(gdf.to_json())
        tab.text_editor.blockSignals(False)
        
        tab.is_dirty = True
        self._update_tab_title(tab)
        tab.preview_timer.start()

    def _set_crs(self, initial_check=False):
        tab = self._get_current_tab()
        if not tab: return
        
        if tab.file_type != "Spatial":
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
        tab = self._get_current_tab()
        if not tab: return
        
        if tab.file_type != "Spatial":
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

    def _get_current_tab(self) -> EditorTab:
        return self.tab_widget.currentWidget()

    def _add_new_tab(self, file_path=None):
        tab = EditorTab(self)
        tab.current_file = file_path

        tab.state_changed.connect(lambda: self._update_tab_title(tab))
        tab.text_editor.file_dropped.connect(self._load_file)
        
        index = self.tab_widget.addTab(tab, tab.get_title())
        self.tab_widget.setCurrentIndex(index)
        return tab

    def _update_tab_title(self, tab):
        index = self.tab_widget.indexOf(tab)
        if index != -1:
            self.tab_widget.setTabText(index, tab.get_title())

    def _on_tab_changed(self, index):
        if index == -1:
            self.cursor_label.clear()
            self.type_label.clear()
            self.setWindowTitle("Chisel Editor")
            return
            
        tab = self.tab_widget.widget(index)
        self.cursor_label.setText("") 
        self.type_label.setText(tab.file_type)
        title = f"Chisel Editor - {os.path.basename(tab.current_file) if tab.current_file else 'Untitled'}"
    
        if getattr(tab, 'is_dirty', False):
            title += " *"
            
        self.setWindowTitle(title)

    def _close_tab(self, index):
        tab = self.tab_widget.widget(index)
        
        if getattr(tab, 'is_dirty', False):
            reply = QMessageBox.warning(
                self, 
                "Unsaved Changes",
                f"Save changes to {tab.get_title().replace('*', '').strip()}?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                self.tab_widget.setCurrentIndex(index)
                self._save_file()
            elif reply == QMessageBox.StandardButton.Cancel:
                return
                
        if getattr(tab, 'map_panel', None):
            tab.map_panel.web_view.setPage(None)
            
        if getattr(tab, 'markdown_panel', None):
            tab.markdown_panel.web_view.setPage(None)
            
        if hasattr(tab, 'text_editor') and hasattr(tab.text_editor, 'web_view'):
            tab.text_editor.web_view.setPage(None)
            
        self.tab_widget.removeTab(index)
        tab.deleteLater()
        
        if self.tab_widget.count() == 0:
            self._add_new_tab()

    def _show_command_palette(self):
        commands = {
            "Format GeoJSON": self._format_geojson,
            "Spatial: Set CRS": self._set_crs,
            "Spatial: Reproject CRS": self._reproject_crs,
            "Theme: Switch to Dark": lambda: self._change_theme("dark"),
            "Theme: Switch to Light": lambda: self._change_theme("light"),
            "File: Save": self._save_file,
            "File: Save As...": self._save_file_as,
            "File: Open...": self._open_file,
            "Edit: Find & Replace": self._show_find_replace
        }
        
        dialog = CommandPaletteDialog(commands, self)
        if dialog.exec():
            cmd_name = dialog.selected_command
            if cmd_name and cmd_name in commands:
                commands[cmd_name]()

    def _format_geojson(self):
        tab = self._get_current_tab()
        if not tab or tab.file_type != "Spatial":
            self.statusBar().showMessage("Current file is not Spatial/GeoJSON.", 3000)
            return
            
        try:
            content = tab.text_editor.toPlainText()
            parsed = json.loads(content)
            formatted = json.dumps(parsed, indent=4, ensure_ascii=False)
            
            tab.text_editor.blockSignals(True)
            cursor = tab.text_editor.textCursor()
            cursor.select(cursor.SelectionType.Document)
            cursor.insertText(formatted)
            tab.text_editor.blockSignals(False)
            
            self.statusBar().showMessage("GeoJSON formatted successfully.", 3000)
            tab.is_dirty = True
            self._update_tab_title(tab)
        except Exception as e:
            self.statusBar().showMessage(f"Format error: Invalid JSON.", 3000)