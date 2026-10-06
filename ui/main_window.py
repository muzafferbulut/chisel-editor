import os
import io
import geopandas as gpd
from PyQt6.QtWidgets import (
    QMainWindow, QMenuBar, QMenu, QFileDialog, QMessageBox,
    QLabel, QApplication, QTabWidget, QProgressBar, QPushButton,
    QWidget, QHBoxLayout, QSplitter
)
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent, QKeySequence
from PyQt6.QtCore import Qt, QSettings

from handlers.factory import HandlerFactory
from ui.dialogs import (
    CRSDialog, LayerSelectionDialog, SimplifyDialog,
    ExportSpatialDialog, SpatialInfoDialog, BufferDialog, DissolveDialog
)
from ui.ogc_dialogs import WMSDialog, WFSDialog
from ui.sidebar import SideBar, ExplorerPanel
from ui.toast import ToastNotification
from core.workers import FileLoadWorker, SpatialOpWorker, WFSWorker
from core.theme import ThemeManager
from core.spatial_ops import SpatialOps
from ui.tabs import EditorTab


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._is_loading = False
        self._active_workers = set()
        self.spatial_worker = None
        self.wfs_worker = None
        self._wms_counter = 1

        # Restore last opened folder
        settings = QSettings("ChiselEditor", "ChiselEditor")
        saved_folder = settings.value("last_folder", "")
        if saved_folder and os.path.isdir(str(saved_folder)):
            self._current_folder = str(saved_folder)
        else:
            self._current_folder = os.getcwd()

        self._init_ui()
        self._create_menus()
        self._restore_session_files()

    def _init_ui(self):
        self.setWindowTitle("Chisel Editor")
        self._center_on_screen()

        # Main Central Container
        central_container = QWidget()
        central_layout = QHBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Main Horizontal Splitter (SideBar + Work Area)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(2)

        # Left: Explorer SideBar
        self.side_bar = ExplorerPanel(self._current_folder, self)
        self.side_bar.file_open_requested.connect(self._load_file)
        self.side_bar.folder_change_requested.connect(self._open_folder)

        self.main_splitter.addWidget(self.side_bar)

        # Right: Tab Widget Workspace
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        self.main_splitter.addWidget(self.tab_widget)
        self.main_splitter.setSizes([220, 980])

        central_layout.addWidget(self.main_splitter)
        self.setCentralWidget(central_container)

        # Modern Compact Status Bar
        self.status_bar = self.statusBar()
        self.status_bar.setFixedHeight(24)
        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.setContentsMargins(6, 0, 6, 0)

        self.cursor_label = QLabel("Ln 1, Col 1")
        self.cursor_label.setStyleSheet("font-size: 12px; padding: 0 6px;")
        self.type_label = QLabel("Plain Text")
        self.type_label.setStyleSheet("font-size: 12px; padding: 0 6px;")
        self.status_bar.addPermanentWidget(self.cursor_label)
        self.status_bar.addPermanentWidget(self.type_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(0)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setFixedWidth(90)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.hide()
        self.status_bar.addPermanentWidget(self.progress_bar)

        status_btn_style = (
            "QPushButton {"
            " background-color: transparent;"
            " border: 1px solid transparent;"
            " padding: 0px 6px 1px 6px;"
            " font-size: 12px;"
            " min-height: 0px;"
            " max-height: 18px;"
            " height: 18px;"
            " border-radius: 3px;"
            " margin: 0px 2px;"
            "}"
            "QPushButton:hover {"
            " background-color: rgba(128, 128, 128, 0.2);"
            " border: 1px solid rgba(128, 128, 128, 0.35);"
            "}"
            "QPushButton:pressed {"
            " background-color: rgba(128, 128, 128, 0.35);"
            "}"
        )

        self.btn_status_crs = QPushButton("🌐 EPSG:4326")
        self.btn_status_crs.setFixedHeight(18)
        self.btn_status_crs.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_status_crs.setStyleSheet(status_btn_style)
        self.btn_status_crs.setToolTip("Click to Set or Reproject CRS")
        self.btn_status_crs.clicked.connect(self._set_crs)
        self.btn_status_crs.hide()
        self.status_bar.addPermanentWidget(self.btn_status_crs)

        self.setAcceptDrops(True)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            w = min(1200, max(800, int(avail.width() * 0.88)))
            h = min(750, max(550, int(avail.height() * 0.82)))
            self.resize(w, h)
            self.move(avail.x() + (avail.width() - w) // 2, avail.y() + (avail.height() - h) // 2)
        else:
            self.resize(1150, 720)

    def _restore_session_files(self):
        settings = QSettings("ChiselEditor", "ChiselEditor")
        saved_files = settings.value("open_files", [])
        if isinstance(saved_files, str):
            saved_files = [saved_files] if saved_files else []

        valid_files = [f for f in saved_files if f and os.path.isfile(str(f))]
        active_file = settings.value("active_file", "")

        if valid_files:
            for f in valid_files:
                self._load_file(str(f))
            if active_file:
                for idx in range(self.tab_widget.count()):
                    tab = self.tab_widget.widget(idx)
                    if tab and tab.current_file == active_file:
                        self.tab_widget.setCurrentIndex(idx)
                        break
        else:
            self._add_new_tab()

    def _save_session_state(self):
        settings = QSettings("ChiselEditor", "ChiselEditor")
        settings.setValue("last_folder", self._current_folder)
        open_files = []
        active_file = ""
        curr_idx = self.tab_widget.currentIndex()
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab and tab.current_file and os.path.exists(tab.current_file):
                open_files.append(tab.current_file)
                if i == curr_idx:
                    active_file = tab.current_file
        settings.setValue("open_files", open_files)
        settings.setValue("active_file", active_file)

    def _create_menus(self):
        menu_bar: QMenuBar = self.menuBar()

        # --- File Menu ---
        file_menu: QMenu = menu_bar.addMenu("File")

        act_new = QAction("New File", self)
        act_new.setShortcut(QKeySequence("Ctrl+N"))
        act_new.triggered.connect(self._add_new_tab)

        act_open = QAction("Open File...", self)
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.triggered.connect(self._open_file)

        act_open_folder = QAction("Open Folder...", self)
        act_open_folder.setShortcut(QKeySequence("Ctrl+K, Ctrl+O"))
        act_open_folder.triggered.connect(self._open_folder)

        act_save = QAction("Save", self)
        act_save.setShortcut(QKeySequence("Ctrl+S"))
        act_save.triggered.connect(self._save_file)

        act_save_as = QAction("Save As...", self)
        act_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        act_save_as.triggered.connect(self._save_file_as)

        act_close = QAction("Close Tab", self)
        act_close.setShortcut(QKeySequence("Ctrl+W"))
        act_close.triggered.connect(lambda: self._close_tab(self.tab_widget.currentIndex()))

        act_export = QAction("Export GIS Data...", self)
        act_export.triggered.connect(self._export_spatial_data)

        act_exit = QAction("Exit", self)
        act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        act_exit.triggered.connect(self.close)

        file_menu.addAction(act_new)
        file_menu.addAction(act_open)
        file_menu.addAction(act_open_folder)
        file_menu.addSeparator()
        file_menu.addAction(act_save)
        file_menu.addAction(act_save_as)
        file_menu.addAction(act_close)
        file_menu.addSeparator()
        file_menu.addAction(act_export)
        file_menu.addSeparator()
        file_menu.addAction(act_exit)

        # --- Edit Menu ---
        edit_menu: QMenu = menu_bar.addMenu("Edit")
        act_find = QAction("Find & Replace", self)
        act_find.setShortcut(QKeySequence("Ctrl+F"))
        act_find.triggered.connect(self._show_find_replace)
        edit_menu.addAction(act_find)

        # --- View Menu ---
        view_menu: QMenu = menu_bar.addMenu("View")

        act_toggle_sidebar = QAction("Toggle Side Bar", self)
        act_toggle_sidebar.setShortcut(QKeySequence("Ctrl+B"))
        act_toggle_sidebar.triggered.connect(self._toggle_side_bar)
        view_menu.addAction(act_toggle_sidebar)

        act_attr_table = QAction("Attribute Table", self)
        act_attr_table.setShortcut(QKeySequence("F6"))
        act_attr_table.triggered.connect(self._toggle_attribute_table)
        view_menu.addAction(act_attr_table)

        view_menu.addSeparator()
        mode_code = QAction("📝 Code View", self)
        mode_code.setShortcut(QKeySequence("Alt+1"))
        mode_code.triggered.connect(lambda: self._set_current_view_mode("code"))

        mode_code_map = QAction("⚡ Code + Map View", self)
        mode_code_map.setShortcut(QKeySequence("Alt+2"))
        mode_code_map.triggered.connect(lambda: self._set_current_view_mode("code_map"))

        mode_table_map = QAction("📊 Table + Map View", self)
        mode_table_map.setShortcut(QKeySequence("Alt+3"))
        mode_table_map.triggered.connect(lambda: self._set_current_view_mode("table_map"))

        mode_map = QAction("🗺️ Full Map View", self)
        mode_map.setShortcut(QKeySequence("Alt+4"))
        mode_map.triggered.connect(lambda: self._set_current_view_mode("map"))

        mode_table = QAction("📋 Full Table View", self)
        mode_table.setShortcut(QKeySequence("Alt+5"))
        mode_table.triggered.connect(lambda: self._set_current_view_mode("table"))

        view_menu.addAction(mode_code)
        view_menu.addAction(mode_code_map)
        view_menu.addAction(mode_table_map)
        view_menu.addAction(mode_map)
        view_menu.addAction(mode_table)

        view_menu.addSeparator()
        theme_menu: QMenu = view_menu.addMenu("Theme")
        act_light = QAction("Light", self)
        act_dark = QAction("Dark", self)
        act_light.triggered.connect(lambda: self._change_theme("light"))
        act_dark.triggered.connect(lambda: self._change_theme("dark"))
        theme_menu.addAction(act_light)
        theme_menu.addAction(act_dark)

        # --- GIS / Spatial Menu ---
        gis_menu: QMenu = menu_bar.addMenu("GIS")

        # Servis Ekle Submenu
        service_menu = gis_menu.addMenu("🌐 Servis Ekle")
        act_wms = QAction("🗺️ WMS Katmanı Ekle...", self)
        act_wms.triggered.connect(self._show_wms_dialog)
        act_wfs = QAction("📡 WFS Katmanı Ekle...", self)
        act_wfs.triggered.connect(self._show_wfs_dialog)
        service_menu.addAction(act_wms)
        service_menu.addAction(act_wfs)

        act_fit = QAction("🎯 Fit Layer Bounds", self)
        act_fit.triggered.connect(self._fit_bounds)

        act_info = QAction("ℹ️ Layer Info & Statistics...", self)
        act_info.triggered.connect(self._show_layer_info)

        gis_menu.addAction(act_attr_table)
        gis_menu.addAction(act_fit)
        gis_menu.addAction(act_info)
        gis_menu.addSeparator()

        # Geoprocessing Tools
        act_buffer = QAction("⭕ Buffer Geometries...", self)
        act_buffer.triggered.connect(self._buffer_geometries)

        act_dissolve = QAction("🔗 Dissolve Geometries...", self)
        act_dissolve.triggered.connect(self._dissolve_geometries)

        act_calc_geom = QAction("📐 Calculate Geometry (Area / Length)...", self)
        act_calc_geom.triggered.connect(self._calc_geometry_attributes)

        act_simplify = QAction("✂️ Simplify Geometries (Douglas-Peucker)...", self)
        act_simplify.triggered.connect(self._simplify_geometries)

        act_validate = QAction("🛡️ Validate & Repair Geometries", self)
        act_validate.triggered.connect(self._validate_repair_geometries)

        gis_menu.addAction(act_buffer)
        gis_menu.addAction(act_dissolve)
        gis_menu.addAction(act_calc_geom)
        gis_menu.addAction(act_simplify)
        gis_menu.addAction(act_validate)
        gis_menu.addSeparator()

        act_set_crs = QAction("🌐 Set CRS...", self)
        act_set_crs.triggered.connect(self._set_crs)

        act_reproject = QAction("🔄 Reproject CRS...", self)
        act_reproject.triggered.connect(self._reproject_crs)

        gis_menu.addAction(act_set_crs)
        gis_menu.addAction(act_reproject)
        gis_menu.addAction(act_export)

        # --- Help Menu ---
        help_menu: QMenu = menu_bar.addMenu("Help")

        act_sample = QAction("🧪 Load Sample GIS Data (Türkiye)", self)
        act_sample.triggered.connect(self._load_sample_spatial_data)

        act_shortcuts = QAction("⌨️ Keyboard Shortcuts", self)
        act_shortcuts.triggered.connect(self._show_shortcuts)

        act_about = QAction("ℹ️ About Chisel Editor", self)
        act_about.triggered.connect(self._show_about)

        help_menu.addAction(act_sample)
        help_menu.addSeparator()
        help_menu.addAction(act_shortcuts)
        help_menu.addAction(act_about)

    def _toggle_side_bar(self):
        is_vis = self.side_bar.isVisible()
        self.side_bar.setVisible(not is_vis)

    def _get_current_tab(self) -> EditorTab:
        tab = self.tab_widget.currentWidget()
        if not tab and self.tab_widget.count() == 0:
            return self._add_new_tab()
        return tab

    def _add_new_tab(self) -> EditorTab:
        tab = EditorTab()
        tab.text_editor.cursorPositionChanged.connect(self._update_cursor_info)
        tab.text_editor.file_dropped.connect(self._handle_file_drop)
        tab.state_changed.connect(lambda: self._on_tab_state_changed(tab))
        tab.service_add_requested.connect(self._show_wms_dialog)
        tab.wms_deleted.connect(self._on_wms_remove_requested)

        idx = self.tab_widget.addTab(tab, tab.get_title())
        self.tab_widget.setCurrentIndex(idx)
        return tab

    def _close_tab(self, index: int):
        self.tab_widget.removeTab(index)
        if self.tab_widget.count() == 0:
            self._add_new_tab()
        self._save_session_state()

    def _update_tab_title(self, tab: EditorTab):
        idx = self.tab_widget.indexOf(tab)
        if idx != -1:
            self.tab_widget.setTabText(idx, tab.get_title())

    def _on_tab_state_changed(self, tab: EditorTab):
        self._update_tab_title(tab)
        if tab == self._get_current_tab():
            self._update_table_button_state(tab)

    def _update_table_button_state(self, tab: EditorTab = None):
        pass

    def _on_tab_changed(self, index: int):
        tab = self.tab_widget.widget(index)
        if tab:
            self.type_label.setText(tab.file_type)
            if tab.is_spatial:
                crs_label = str(tab._current_gdf.crs) if tab._current_gdf is not None and tab._current_gdf.crs else "EPSG:4326"
                self.btn_status_crs.setText(f"🌐 {crs_label}")
                self.btn_status_crs.show()
                feat_count = len(tab._current_gdf) if tab._current_gdf is not None and not tab._current_gdf.empty else 0
                layer_name = os.path.basename(tab.current_file) if tab.current_file else "Sample GIS Layer"
                tab.map_panel.set_active_vector_info(layer_name, feat_count)
            else:
                self.btn_status_crs.hide()
                if tab.map_panel:
                    tab.map_panel.set_active_vector_info("", 0)
        self._save_session_state()

    def _update_cursor_info(self, line: int, col: int):
        self.cursor_label.setText(f"Ln {line}, Col {col}")

    def _set_current_view_mode(self, mode: str):
        tab = self._get_current_tab()
        if tab:
            tab.set_view_mode(mode)
            self._update_table_button_state(tab)

    def _toggle_attribute_table(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial:
            return
        tab.toggle_table()
        self._update_table_button_state(tab)

    def _fit_bounds(self):
        tab = self._get_current_tab()
        if tab and tab.is_spatial:
            tab.map_panel.fit_bounds()

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Klasör Seç", self._current_folder)
        if folder:
            self._current_folder = folder
            self.side_bar.set_root_path(folder)
            self._save_session_state()
            ToastNotification.show_toast(self, f"Açıldı: {os.path.basename(folder)}", "info")

    def _open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open File", self._current_folder,
            "All Supported Files (*.geojson *.json *.shp *.kml *.gpkg *.fgb *.csv *.txt *.md *.py);;All Files (*)"
        )
        if file_path:
            self._load_file(file_path)

    def _load_file(self, file_path: str, **kwargs):
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab and tab.current_file == file_path:
                self.tab_widget.setCurrentIndex(i)
                return

        self.progress_bar.show()
        self._is_loading = True

        worker = FileLoadWorker(file_path, **kwargs)
        self._active_workers.add(worker)
        worker.finished.connect(lambda fp, c, sp, g, err, w=worker: self._handle_worker_finished(w, fp, c, sp, g, err))
        worker.multiple_layers_detected.connect(self._on_multiple_layers)
        worker.start()

    def _handle_worker_finished(self, worker, file_path: str, content: str, is_spatial: bool, gdf: object, error: str):
        self._active_workers.discard(worker)
        if not self._active_workers:
            self.progress_bar.hide()
            self._is_loading = False
        self._on_file_loaded(file_path, content, is_spatial, gdf, error)

    def _on_file_loaded(self, file_path: str, content: str, is_spatial: bool, gdf: object, error: str):
        if not self._active_workers:
            self.progress_bar.hide()
            self._is_loading = False

        if error:
            ToastNotification.show_toast(self, f"Hata: {error}", "error")
            return

        tab = self._get_current_tab()
        if tab is None or tab.current_file is not None or tab.is_dirty:
            tab = self._add_new_tab()

        tab.current_file = file_path
        tab.is_dirty = False

        ext = os.path.splitext(file_path)[1].lower()
        type_names = {
            ".geojson": "GeoJSON", ".shp": "ESRI Shapefile", ".kml": "KML",
            ".gpkg": "GeoPackage", ".fgb": "FlatGeobuf", ".md": "Markdown",
            ".json": "JSON", ".py": "Python", ".csv": "CSV"
        }
        file_type = type_names.get(ext, "Plain Text")

        tab.configure_for_file_type(file_type, is_spatial, content, gdf=gdf)
        self._update_tab_title(tab)
        self._on_tab_changed(self.tab_widget.currentIndex())
        self._save_session_state()

        ToastNotification.show_toast(self, f"Açıldı: {os.path.basename(file_path)}", "info")

    def _on_multiple_layers(self, file_path: str, layers: list):
        self.progress_bar.hide()
        dlg = LayerSelectionDialog(os.path.basename(file_path), layers, self)
        if dlg.exec():
            if dlg.merge_all:
                self._load_file(file_path, merge_all=True)
            elif dlg.selected_layer:
                self._load_file(file_path, layer_name=dlg.selected_layer)

    def _save_file(self):
        tab = self._get_current_tab()
        if not tab:
            return
        if tab.current_file:
            self._write_file(tab.current_file)
        else:
            self._save_file_as()

    def _save_file_as(self):
        tab = self._get_current_tab()
        if not tab:
            return
        filt = "GeoJSON (*.geojson);;All Files (*)" if tab.is_spatial else "All Files (*)"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save File As", tab.current_file or self._current_folder, filt)
        if file_path:
            self._write_file(file_path)

    def _write_file(self, file_path: str):
        tab = self._get_current_tab()
        if not tab:
            return
        try:
            handler = HandlerFactory.get_handler(file_path)
            content = tab.text_editor.toPlainText()
            handler.write(file_path, content)
            tab.current_file = file_path
            tab.is_dirty = False
            self._update_tab_title(tab)
            ToastNotification.show_toast(self, f"Saved: {os.path.basename(file_path)}", "info")
        except Exception as e:
            ToastNotification.show_toast(self, f"Save failed: {str(e)}", "error")

    # --- WMS & WFS Service Integrations ---
    def _show_wms_dialog(self):
        tab = self._get_current_tab()
        if not tab:
            tab = self._add_new_tab()

        dlg = WMSDialog(self)
        if dlg.exec():
            layer_id = f"wms_{self._wms_counter}"
            self._wms_counter += 1
            tab.map_panel.add_wms_layer(layer_id, dlg.wms_url, dlg.layer_name, dlg.format, dlg.transparent, title=dlg.title)
            # Ensure map is visible
            if not tab.is_spatial and not tab.right_stack.isVisible():
                tab.set_view_mode("code_map")
            ToastNotification.show_toast(self, f"WMS Katmanı Eklendi: {dlg.title}", "info")

    def _show_wfs_dialog(self):
        dlg = WFSDialog(self)
        if dlg.exec():
            self.progress_bar.show()
            self.wfs_worker = WFSWorker(dlg.wfs_url, dlg.type_name, dlg.limit)
            self.wfs_worker.finished.connect(self._on_wfs_download_finished)
            self.wfs_worker.start()

    def _on_wfs_download_finished(self, layer_name: str, gdf: object, error: str):
        self.progress_bar.hide()
        if error:
            ToastNotification.show_toast(self, f"WFS Hatası: {error}", "error")
            return

        if gdf is not None and not gdf.empty:
            tab = self._add_new_tab()
            tab.current_file = f"{layer_name}.geojson"
            tab.set_spatial_data(gdf)
            self._update_tab_title(tab)
            self._on_tab_changed(self.tab_widget.currentIndex())
            ToastNotification.show_toast(self, f"WFS Katmanı İndirildi: {len(gdf):,} özellik", "info")

    def _on_wms_visibility_changed(self, layer_id: str, visible: bool):
        tab = self._get_current_tab()
        if tab and tab.map_panel:
            tab.map_panel.set_wms_visibility(layer_id, visible)

    def _on_wms_remove_requested(self, layer_id: str):
        tab = self._get_current_tab()
        if tab and tab.map_panel:
            tab.map_panel.remove_wms_layer(layer_id)
        ToastNotification.show_toast(self, "WMS Katmanı Kaldırıldı", "info")

    # --- Geoprocessing Operations via Background Worker ---
    def _run_spatial_worker(self, op_name: str, gdf: gpd.GeoDataFrame, **params):
        if gdf is None or gdf.empty:
            ToastNotification.show_toast(self, "İşlem yapılacak mekansal veri bulunamadı", "warning")
            return

        self.progress_bar.show()
        self.spatial_worker = SpatialOpWorker(op_name, gdf, **params)
        self.spatial_worker.finished.connect(self._on_spatial_op_finished)
        self.spatial_worker.start()

    def _on_spatial_op_finished(self, op_name: str, result: object, error: str):
        self.progress_bar.hide()
        if error:
            ToastNotification.show_toast(self, f"İşlem hatası: {error}", "error")
            return

        tab = self._get_current_tab()
        if not tab:
            return

        if op_name in ("buffer", "dissolve", "calc_geometry", "reproject", "set_crs", "centroids", "bounding_boxes", "convex_hull"):
            tab.update_spatial_gdf(result)
            ToastNotification.show_toast(self, f"✅ {op_name.title()} işlemi tamamlandı!", "info")

        elif op_name == "validate_repair":
            repaired_gdf, fixed_count = result
            tab.update_spatial_gdf(repaired_gdf)
            msg = f"{fixed_count} geçersiz geometri onarıldı." if fixed_count > 0 else "Tüm geometriler geçerli!"
            ToastNotification.show_toast(self, msg, "info")

        elif op_name == "simplify":
            simplified_gdf, orig_v, simp_v = result
            tab.update_spatial_gdf(simplified_gdf)
            pct = ((orig_v - simp_v) / orig_v * 100) if orig_v > 0 else 0
            ToastNotification.show_toast(self, f"Basitleştirildi: {orig_v:,} -> {simp_v:,} köşe noktası (%{pct:.1f})", "info")

        elif op_name == "export":
            ToastNotification.show_toast(self, "Veri başarıyla dışa aktarıldı!", "info")

    def _buffer_geometries(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "Aktif mekansal katman yok", "warning")
            return
        crs_str = str(tab._current_gdf.crs) if tab._current_gdf.crs else None
        dlg = BufferDialog(crs=crs_str, parent=self)
        if dlg.exec():
            self._run_spatial_worker("buffer", tab._current_gdf, distance=dlg.distance, unit=dlg.unit)

    def _dissolve_geometries(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "Aktif mekansal katman yok", "warning")
            return
        cols = [c for c in tab._current_gdf.columns if c != tab._current_gdf.geometry.name]
        dlg = DissolveDialog(cols, parent=self)
        if dlg.exec():
            self._run_spatial_worker("dissolve", tab._current_gdf, by_column=dlg.by_column)

    def _calc_geometry_attributes(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "Aktif mekansal katman yok", "warning")
            return
        self._run_spatial_worker("calc_geometry", tab._current_gdf)

    def _simplify_geometries(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "Aktif mekansal katman yok", "warning")
            return
        v_count = SpatialOps.count_vertices(tab._current_gdf)
        crs_str = str(tab._current_gdf.crs) if tab._current_gdf.crs else None
        dlg = SimplifyDialog(crs_str, v_count, parent=self)
        if dlg.exec():
            self._run_spatial_worker("simplify", tab._current_gdf, tolerance=dlg.tolerance, preserve_topology=dlg.preserve_topology)

    def _validate_repair_geometries(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            return
        self._run_spatial_worker("validate_repair", tab._current_gdf)

    def _set_crs(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            return
        curr_crs = str(tab._current_gdf.crs) if tab._current_gdf.crs else "None"
        dlg = CRSDialog("Set Coordinate Reference System (CRS)", curr_crs, self)
        if dlg.exec() and dlg.selected_epsg:
            self._run_spatial_worker("set_crs", tab._current_gdf, new_crs=dlg.selected_epsg)

    def _reproject_crs(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            return
        curr_crs = str(tab._current_gdf.crs) if tab._current_gdf.crs else "None"
        dlg = CRSDialog("Reproject Coordinate Reference System", curr_crs, self)
        if dlg.exec() and dlg.selected_epsg:
            self._run_spatial_worker("reproject", tab._current_gdf, target_crs=dlg.selected_epsg)

    def _export_spatial_data(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "Dışa aktarılacak mekansal veri yok", "warning")
            return
        dlg = ExportSpatialDialog(tab.current_file, self)
        if dlg.exec() and dlg.target_path:
            self._run_spatial_worker("export", tab._current_gdf, target_path=dlg.target_path)

    def _show_layer_info(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "Mekansal katman bulunamadı", "warning")
            return
        summary = SpatialOps.get_summary(tab._current_gdf)
        dlg = SpatialInfoDialog(summary, tab.current_file, self)
        dlg.exec()

    def _load_sample_spatial_data(self):
        sample_gdf = SpatialOps.create_sample_spatial_data()
        tab = self._add_new_tab()
        tab.current_file = "turkey_sample_zones.geojson"
        tab.set_spatial_data(sample_gdf)
        self._update_tab_title(tab)
        self._on_tab_changed(self.tab_widget.currentIndex())
        ToastNotification.show_toast(self, "🧪 Örnek Mekansal Veri Yüklendi!", "info")

    def _show_find_replace(self):
        from PyQt6.QtWidgets import QInputDialog
        tab = self._get_current_tab()
        if not tab:
            return
        find_text, ok1 = QInputDialog.getText(self, "Find", "Enter text to find:")
        if ok1 and find_text:
            replace_text, ok2 = QInputDialog.getText(self, "Replace", f"Replace '{find_text}' with:")
            if ok2:
                tab.text_editor.find_and_replace(find_text, replace_text)

    def _change_theme(self, theme_name: str):
        ThemeManager.apply_theme(QApplication.instance(), theme_name)
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab:
                tab.text_editor.setTheme(theme_name)
                tab.map_panel.set_theme_tiles(theme_name)

    def _show_shortcuts(self):
        QMessageBox.information(
            self, "Klavye Kısayolları",
            "<b>Klavye Kısayolları:</b><br><br>"
            "• <b>Ctrl+N</b>: Yeni Dosya<br>"
            "• <b>Ctrl+O</b>: Dosya Aç<br>"
            "• <b>Ctrl+K, Ctrl+O</b>: Klasör Aç (Çalışma Alanı)<br>"
            "• <b>Ctrl+S</b>: Kaydet<br>"
            "• <b>Ctrl+B</b>: Yan Paneli Aç / Kapat<br>"
            "• <b>F6</b>: Öznitelik Tablosunu Aç / Kapat<br>"
            "• <b>Ctrl+F</b>: Bul & Değiştir<br>"
            "• <b>Alt+1...5</b>: Görünüm Modları (Kod, Kod+Harita, Tablo+Harita, Harita, Tablo)"
        )

    def _show_about(self):
        QMessageBox.about(
            self, "Chisel Editor Hakkında",
            "<b>Chisel Editor</b><br>"
            "Modern, Hızlı ve Hafif CBS (GIS) Destekli Kod Editörü.<br><br>"
            "Vektör CBS dosyalarını (GeoJSON, SHP, GPKG, KML, CSV), WMS harita servislerini "
            "ve WFS özelliklerini hızla görüntüleyin, düzenleyin ve jeo-işleme araçlarıyla analiz edin."
        )

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if os.path.exists(file_path):
                self._load_file(file_path)

    def _handle_file_drop(self, file_path: str):
        if os.path.exists(file_path):
            self._load_file(file_path)

    def closeEvent(self, event):
        self._save_session_state()
        super().closeEvent(event)
