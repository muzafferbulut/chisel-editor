import os
import geopandas as gpd
from PyQt6.QtWidgets import (
    QMainWindow, QMenuBar, QMenu, QFileDialog, QMessageBox,
    QLabel, QApplication, QTabWidget, QProgressBar, QPushButton,
    QWidget, QHBoxLayout, QSplitter
)
from PyQt6.QtGui import QAction, QActionGroup, QDragEnterEvent, QDropEvent, QKeySequence, QCursor, QShortcut
from PyQt6.QtCore import Qt, QSettings, QTimer

from handlers.factory import HandlerFactory
from ui.dialogs import (
    CRSDialog, LayerSelectionDialog, SimplifyDialog,
    ExportSpatialDialog, SpatialInfoDialog, BufferDialog, DissolveDialog
)
from ui.ogc_dialogs import WMSDialog, WFSDialog
from ui.sidebar import ExplorerPanel
from ui.toast import ToastNotification
from core.workers import FileLoadWorker, SpatialOpWorker, WFSWorker
from core.theme import ThemeManager
from core.spatial_ops import SpatialOps
from ui.tabs import EditorTab
from ui.preview_panels import MapPreviewPanel


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._is_loading = False
        self._active_workers = set()
        self.spatial_worker = None
        self.wfs_worker = None
        self._wms_counter = 1

        # Central Unified Map Preview Panel shared across all spatial tabs
        self.shared_map_panel = MapPreviewPanel()
        self.shared_map_panel.feature_added.connect(self._on_map_feature_added)
        self.shared_map_panel.feature_deleted.connect(self._on_map_feature_deleted)
        self.shared_map_panel.feature_updated.connect(self._on_map_feature_updated)
        self.shared_map_panel.feature_clicked.connect(self._on_map_feature_clicked)
        self.shared_map_panel.selection_changed.connect(self._on_map_selection_changed)
        self.shared_map_panel.selection_deleted.connect(self._on_map_selection_deleted)
        self.shared_map_panel.table_toggle_requested.connect(self._on_map_table_toggle_requested)
        self.shared_map_panel.service_add_requested.connect(self._show_service_menu)
        self.shared_map_panel.wms_deleted.connect(self._on_wms_remove_requested)
        self.shared_map_panel.active_layer_requested.connect(self._on_active_layer_requested)
        self.shared_map_panel.layer_removed.connect(self._on_map_layer_removed)
        self.shared_map_panel.viewport_changed.connect(self._on_map_viewport_changed)

        # Restore last opened folder
        settings = QSettings("ChiselEditor", "ChiselEditor")
        saved_folder = settings.value("last_folder", "")
        if saved_folder and os.path.isdir(str(saved_folder)):
            self._current_folder = str(saved_folder)
        else:
            self._current_folder = os.getcwd()

        self.topology_dialog = None

        self._init_ui()
        self._create_menus()
        self._restore_session_files()

    def _init_ui(self):
        self.setWindowTitle("Chisel Editor")
        self.setMinimumSize(720, 480)
        self._center_on_screen()

        # Main Central Container
        central_container = QWidget()
        central_layout = QHBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Main Horizontal Splitter (SideBar + Work Area)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setHandleWidth(2)
        self.main_splitter.setChildrenCollapsible(True)

        # Left: Explorer SideBar
        self.side_bar = ExplorerPanel(self._current_folder, self)
        self.side_bar.file_open_requested.connect(self._load_file)
        self.side_bar.folder_change_requested.connect(self._open_folder)
        self.side_bar.file_convert_requested.connect(self._convert_file)

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
        self.btn_status_crs.setToolTip("Click for Coordinate Reference System (CRS) Options")
        self.btn_status_crs.clicked.connect(self._show_crs_menu)
        self.btn_status_crs.hide()
        self.status_bar.addPermanentWidget(self.btn_status_crs)

        self.setAcceptDrops(True)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            w = min(1200, max(720, int(avail.width() * 0.88)))
            h = min(750, max(480, int(avail.height() * 0.82)))
            w = min(w, avail.width())
            h = min(h, avail.height())
            self.resize(w, h)
            self.move(avail.x() + (avail.width() - w) // 2, avail.y() + (avail.height() - h) // 2)
        else:
            self.resize(1150, 720)

    def _restore_session_files(self):
        settings = QSettings("ChiselEditor", "ChiselEditor")
        saved_files = settings.value("open_files", [])
        if isinstance(saved_files, str):
            saved_files = [saved_files] if saved_files else []

        spatial_exts = {".geojson", ".shp", ".kml", ".gpkg", ".fgb"}
        valid_files = [
            f for f in saved_files
            if f and os.path.isfile(str(f)) and os.path.splitext(str(f))[1].lower() not in spatial_exts
        ]
        active_file = settings.value("active_file", "")

        if valid_files:
            for f in valid_files:
                self._load_file(str(f))
            if active_file and os.path.splitext(str(active_file))[1].lower() not in spatial_exts:
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
        spatial_exts = {".geojson", ".shp", ".kml", ".gpkg", ".fgb"}

        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab and tab.current_file and os.path.exists(tab.current_file):
                ext = os.path.splitext(tab.current_file)[1].lower()
                # Do NOT save spatial files to restore upon restart
                if tab.is_spatial or ext in spatial_exts:
                    continue
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
        file_menu.addAction(act_exit)

        # --- Edit Menu ---
        edit_menu: QMenu = menu_bar.addMenu("Edit")
        act_find = QAction("Find", self)
        act_find.setShortcut(QKeySequence("Ctrl+F"))
        act_find.triggered.connect(self._show_find)
        edit_menu.addAction(act_find)

        act_replace = QAction("Replace", self)
        act_replace.setShortcut(QKeySequence("Ctrl+H"))
        act_replace.triggered.connect(self._show_replace)
        edit_menu.addAction(act_replace)

        # --- View Menu ---
        view_menu: QMenu = menu_bar.addMenu("View")

        act_toggle_sidebar = QAction("Toggle Side Bar", self)
        act_toggle_sidebar.setShortcut(QKeySequence("Ctrl+B"))
        act_toggle_sidebar.triggered.connect(self._toggle_side_bar)
        view_menu.addAction(act_toggle_sidebar)

        view_menu.addSeparator()
        theme_menu: QMenu = view_menu.addMenu("Theme")
        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.setExclusive(True)

        for theme_key, theme_label in ThemeManager.AVAILABLE_THEMES.items():
            act = QAction(theme_label, self)
            act.setCheckable(True)
            if theme_key == ThemeManager._current_theme:
                act.setChecked(True)
            act.triggered.connect(lambda checked, tk=theme_key: self._change_theme(tk))
            self.theme_action_group.addAction(act)
            theme_menu.addAction(act)

        # --- GIS / Spatial Menu ---
        gis_menu: QMenu = menu_bar.addMenu("GIS")

        act_export = QAction("💾 Export...", self)
        act_export.triggered.connect(self._export_spatial_data)

        # Global shortcuts for spatial tools
        QShortcut(QKeySequence("F6"), self, self._toggle_attribute_table)
        QShortcut(QKeySequence("Ctrl+Shift+F"), self, self._zoom_full_extent)
        QShortcut(QKeySequence("F5"), self, self._refresh_map)

        # Services & Basemaps Submenu
        service_menu = gis_menu.addMenu("🌐 Services & Basemaps")
        
        basemap_submenu = service_menu.addMenu("🗺️ Add Basemap Service")
        act_b_osm = basemap_submenu.addAction("🗺️ OpenStreetMap (Default)")
        act_b_osm.triggered.connect(lambda: self._add_preset_service("osm"))
        act_b_sat = basemap_submenu.addAction("🛰️ Esri World Imagery (Satellite)")
        act_b_sat.triggered.connect(lambda: self._add_preset_service("sat"))
        act_b_topo = basemap_submenu.addAction("🏔️ OpenTopoMap (Topographic)")
        act_b_topo.triggered.connect(lambda: self._add_preset_service("topo"))
        act_b_dark = basemap_submenu.addAction("🌙 CartoDB (Dark Mode)")
        act_b_dark.triggered.connect(lambda: self._add_preset_service("dark"))
        act_b_none = basemap_submenu.addAction("🚫 No Basemap (Blank Canvas)")
        act_b_none.triggered.connect(self._clear_all_basemaps)

        service_menu.addSeparator()
        act_wms = QAction("🌐 Add WMS Layer...", self)
        act_wms.triggered.connect(self._show_wms_dialog)
        act_wfs = QAction("📡 Download WFS Layer...", self)
        act_wfs.triggered.connect(self._show_wfs_dialog)
        service_menu.addAction(act_wms)
        service_menu.addAction(act_wfs)

        gis_menu.addSeparator()

        # Geoprocessing Tools
        act_buffer = QAction("⭕ Buffer...", self)
        act_buffer.triggered.connect(self._buffer_geometries)

        act_dissolve = QAction("🔗 Dissolve...", self)
        act_dissolve.triggered.connect(self._dissolve_geometries)

        act_simplify = QAction("✂️ Simplify...", self)
        act_simplify.triggered.connect(self._simplify_geometries)

        act_topology = QAction("📐 Topology Checker...", self)
        act_topology.triggered.connect(self._show_topology_checker)

        act_validate = QAction("🛡️ Validate Geometries", self)
        act_validate.triggered.connect(self._validate_geometries)

        act_repair = QAction("🔧 Repair Geometries", self)
        act_repair.triggered.connect(self._repair_geometries)

        gis_menu.addAction(act_buffer)
        gis_menu.addAction(act_dissolve)
        gis_menu.addAction(act_simplify)
        gis_menu.addSeparator()
        gis_menu.addAction(act_topology)
        gis_menu.addAction(act_validate)
        gis_menu.addAction(act_repair)
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

        act_sample = QAction("🧪 Load Sample GIS Data (Turkey)", self)
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
        tab = EditorTab(map_panel=self.shared_map_panel)
        tab.text_editor.cursorPositionChanged.connect(self._update_cursor_info)
        tab.text_editor.file_dropped.connect(self._handle_file_drop)
        tab.state_changed.connect(lambda: self._on_tab_state_changed(tab))
        tab.service_add_requested.connect(self._show_service_menu)
        tab.wms_deleted.connect(self._on_wms_remove_requested)

        idx = self.tab_widget.addTab(tab, tab.get_title())
        self.tab_widget.setCurrentIndex(idx)
        return tab

    def _find_spatial_tab(self):
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab and getattr(tab, "is_spatial", False):
                return tab
        return None

    def _close_tab(self, index: int):
        tab = self.tab_widget.widget(index)
        if tab:
            if hasattr(tab, "cleanup"):
                tab.cleanup()
            if tab.is_spatial:
                self.shared_map_panel.clear_all_vector_layers()
        self.tab_widget.removeTab(index)
        if self.tab_widget.count() == 0:
            self._add_new_tab()
        self._save_session_state()

    def _update_tab_title(self, tab: EditorTab):
        idx = self.tab_widget.indexOf(tab)
        if idx != -1:
            self.tab_widget.setTabText(idx, tab.get_title())
            if tab.is_spatial:
                layer_name = os.path.basename(tab.current_file) if tab.current_file else "Spatial Layer"
                self.shared_map_panel.update_layer_name(tab.layer_id, layer_name)

    def _on_tab_state_changed(self, tab: EditorTab):
        self._update_tab_title(tab)
        if tab == self._get_current_tab():
            self._update_table_button_state(tab)

    def _update_table_button_state(self, tab: EditorTab = None):
        pass

    def _on_tab_changed(self, index: int):
        tab = self.tab_widget.widget(index)
        if tab:
            badge = tab.get_format_badge() if hasattr(tab, "get_format_badge") else tab.file_type
            self.type_label.setText(badge)
            if hasattr(tab, "apply_theme"):
                tab.apply_theme(ThemeManager._current_theme)

            if tab.is_spatial:
                tab.attach_map_panel(self.shared_map_panel)
                tab._adjust_spatial_splitter_sizes()

                crs_label = str(tab._current_gdf.crs) if tab._current_gdf is not None and tab._current_gdf.crs else "EPSG:4326"
                self.btn_status_crs.setText(f"🌐 {crs_label}")
                self.btn_status_crs.show()

                geom_type = SpatialOps.get_layer_geometry_type(tab._current_gdf)
                self.shared_map_panel.set_active_vector_layer(tab.layer_id, geom_type)
            else:
                self.btn_status_crs.hide()
        self._save_session_state()

    def _on_map_feature_added(self, feature_json_str: str):
        tab = self._get_current_tab()
        if tab and tab.is_spatial:
            tab._on_feature_added(feature_json_str)

    def _on_map_feature_updated(self, index: int, feature_json_str: str):
        tab = self._get_current_tab()
        if tab and tab.is_spatial:
            tab._on_feature_updated(index, feature_json_str, from_map=True)

    def _on_map_feature_deleted(self, index: int):
        tab = self._get_current_tab()
        if tab and tab.is_spatial:
            tab._on_features_deleted([index])

    def _on_map_selection_deleted(self, indices: list):
        tab = self._get_current_tab()
        if tab and tab.is_spatial:
            tab._on_features_deleted(indices)

    def _on_map_feature_clicked(self, index: int):
        tab = self._get_current_tab()
        if not (tab and tab.is_spatial):
            tab = self._find_spatial_tab()
        if tab and tab.is_spatial:
            tab.table_panel.select_feature(index)

    def _on_map_selection_changed(self, indices: list):
        tab = self._get_current_tab()
        if not (tab and tab.is_spatial):
            tab = self._find_spatial_tab()
        if tab and tab.is_spatial:
            tab.table_panel.select_features(indices)

    def _on_map_table_toggle_requested(self):
        tab = self._get_current_tab()
        if tab and tab.is_spatial:
            tab.toggle_table()

    def _on_active_layer_requested(self, layer_id: str):
        spatial_tab = self._find_spatial_tab()
        if spatial_tab:
            spatial_tab.set_active_layer(layer_id)
            self._update_tab_title(spatial_tab)
            idx = self.tab_widget.indexOf(spatial_tab)
            if idx != -1:
                self.tab_widget.setCurrentIndex(idx)
                self._on_tab_changed(idx)

    def _on_map_layer_removed(self, layer_id: str):
        spatial_tab = self._find_spatial_tab()
        if spatial_tab:
            spatial_tab.remove_spatial_layer(layer_id)
            self._update_tab_title(spatial_tab)
            idx = self.tab_widget.indexOf(spatial_tab)
            if idx != -1:
                self._on_tab_changed(idx)
            ToastNotification.show_toast(self, "Layer removed from map", "info")

    def _on_map_viewport_changed(self, minx: float, miny: float, maxx: float, maxy: float, zoom: int):
        tab = self._get_current_tab()
        if tab and tab.is_spatial and getattr(tab, "_is_large_dataset", False):
            tab._update_viewport_data(minx, miny, maxx, maxy, zoom)

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
            self.shared_map_panel.fit_layer_bounds(tab.layer_id)

    def _zoom_full_extent(self):
        tab = self._get_current_tab()
        if tab and tab.is_spatial:
            self.shared_map_panel.zoom_full_extent()

    def _refresh_map(self):
        tab = self._get_current_tab()
        if tab and tab.is_spatial:
            self.shared_map_panel.refresh_map()

    def _capture_map_snapshot(self):
        tab = self._get_current_tab()
        if tab and tab.is_spatial:
            self.shared_map_panel.capture_snapshot()

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", self._current_folder)
        if folder:
            self._current_folder = folder
            self.side_bar.set_root_path(folder)
            self._save_session_state()
            ToastNotification.show_toast(self, f"Opened: {os.path.basename(folder)}", "info")

    def _open_file(self):
        filter_str = (
            "All Supported Files (*.geojson *.shp *.dbf *.kml *.kmz *.gpkg *.fgb *.xlsx *.xls *.docx *.pdf *.csv *.txt *.md *.py *.json);;"
            "Spatial Layers (*.geojson *.shp *.dbf *.kml *.kmz *.gpkg *.fgb);;"
            "Spreadsheets (*.xlsx *.xls *.csv);;"
            "Word Documents (*.docx);;"
            "PDF Documents (*.pdf);;"
            "Code & Text (*.txt *.md *.py *.json *.js *.html *.css);;"
            "All Files (*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open File", self._current_folder, filter_str
        )
        if file_path:
            self._load_file(file_path)

    def _load_file(self, file_path: str, **kwargs):
        # Auto-redirect shapefile sidecar files (.shx, .dbf, .prj, .cpg) to .shp if present
        ext = os.path.splitext(file_path)[1].lower()
        if ext in ('.shx', '.dbf', '.prj', '.cpg', '.qix', '.qmd'):
            candidate_shp = os.path.splitext(file_path)[0] + '.shp'
            if os.path.exists(candidate_shp):
                file_path = candidate_shp

        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab and hasattr(tab, "has_file") and tab.has_file(file_path):
                self.tab_widget.setCurrentIndex(i)
                if tab.is_spatial:
                    tab.set_active_layer_by_file(file_path)
                    self._on_tab_changed(i)
                ToastNotification.show_toast(self, f"Already open: {os.path.basename(file_path)}", "info")
                return
            elif tab and tab.current_file == file_path:
                self.tab_widget.setCurrentIndex(i)
                ToastNotification.show_toast(self, f"Already open: {os.path.basename(file_path)}", "info")
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
            ToastNotification.show_toast(self, f"Error: {error}", "error")
            return

        if is_spatial:
            spatial_tab = self._ensure_spatial_tab()
            spatial_tab.add_spatial_layer(file_path, gdf)
            idx = self.tab_widget.indexOf(spatial_tab)
            self.tab_widget.setCurrentIndex(idx)
            self._update_tab_title(spatial_tab)
            self._on_tab_changed(idx)
            self._save_session_state()
            QTimer.singleShot(150, lambda: self.shared_map_panel.fit_layer_bounds(spatial_tab.layer_id))
            ToastNotification.show_toast(self, f"Opened: {os.path.basename(file_path)}", "info")
            return

        # Non-spatial documents / code
        tab = self._get_current_tab()
        if tab is None or tab.current_file is not None or tab.is_dirty or tab.is_spatial:
            tab = self._add_new_tab()

        tab.current_file = file_path
        tab.is_dirty = False

        ext = os.path.splitext(file_path)[1].lower()
        if ext in {".xlsx", ".xls", ".csv"}:
            file_type = "Spreadsheet"
        elif ext in {".docx", ".doc"}:
            file_type = "Word"
        elif ext == ".pdf":
            file_type = "PDF"
        else:
            type_names = {
                ".md": "Markdown", ".json": "JSON", ".py": "Python"
            }
            file_type = type_names.get(ext, "Plain Text")

        tab.configure_for_file_type(file_type, is_spatial, content, gdf=gdf)
        self._update_tab_title(tab)
        self._on_tab_changed(self.tab_widget.currentIndex())
        self._save_session_state()

        ToastNotification.show_toast(self, f"Opened: {os.path.basename(file_path)}", "info")

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
        if tab.file_type == "Spreadsheet":
            filt = (
                "Excel Workbook (*.xlsx);;"
                "CSV File (*.csv);;"
                "JSON Data (*.json);;"
                "HTML Table (*.html);;"
                "All Files (*)"
            )
        elif tab.file_type == "Word":
            filt = (
                "Word Document (*.docx);;"
                "HTML Document (*.html);;"
                "Markdown Document (*.md);;"
                "Plain Text (*.txt);;"
                "All Files (*)"
            )
        elif tab.is_spatial:
            filt = (
                "GeoJSON (*.geojson);;"
                "ESRI Shapefile (*.shp);;"
                "GeoPackage (*.gpkg);;"
                "Google KML (*.kml);;"
                "Google KMZ (*.kmz);;"
                "AutoCAD DXF (*.dxf);;"
                "FlatGeobuf (*.fgb);;"
                "CSV with WKT (*.csv);;"
                "All Files (*)"
            )
        else:
            filt = "All Files (*)"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save As", tab.current_file or self._current_folder, filt)
        if file_path:
            self._write_file(file_path)

    def _write_file(self, file_path: str):
        tab = self._get_current_tab()
        if not tab:
            return
        try:
            ext = os.path.splitext(file_path)[1].lower()
            if tab.file_type == "Spreadsheet":
                if ext in ('.json', '.html'):
                    from core.converter import FileConverter
                    df = tab.spreadsheet_editor.to_dataframe()
                    FileConverter._export_tabular(df, file_path, ext)
                else:
                    tab.spreadsheet_editor.save_to_file(file_path)
            elif tab.file_type == "Word":
                if ext in ('.html', '.md', '.txt'):
                    content = tab.document_editor.to_html()
                    if ext in ('.md', '.txt'):
                        import re
                        clean_text = re.sub(r'<[^>]+>', '\n', content)
                        clean_text = re.sub(r'\n+', '\n', clean_text).strip()
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(clean_text)
                    else:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                else:
                    tab.document_editor.save_to_file(file_path)
            elif tab.file_type == "PDF":
                ToastNotification.show_toast(self, "PDF files are read-only.", "info")
                return
            elif tab.is_spatial:
                SpatialOps.export_file(tab._current_gdf, file_path)
            else:
                handler = HandlerFactory.get_handler(file_path)
                content = tab.text_editor.toPlainText()
                handler.write(file_path, content)

            tab.current_file = file_path
            tab.is_dirty = False
            self._update_tab_title(tab)
            ToastNotification.show_toast(self, f"Saved: {os.path.basename(file_path)}", "info")
        except Exception as e:
            ToastNotification.show_toast(self, f"Save error: {str(e)}", "error")

    def _convert_file(self, source_path: str, target_ext: str):
        from core.workers import ConvertWorker
        ToastNotification.show_toast(self, f"Converting {os.path.basename(source_path)}...", "info")
        worker = ConvertWorker(source_path, target_ext)
        self._active_workers.add(worker)
        self.progress_bar.show()

        def _on_finished(src, target, err):
            self._active_workers.discard(worker)
            if not self._active_workers:
                self.progress_bar.hide()
            if err:
                ToastNotification.show_toast(self, f"Conversion failed: {err}", "error")
            else:
                ToastNotification.show_toast(
                    self, f"Successfully converted: {os.path.basename(src)} ➔ {os.path.basename(target)}", "success"
                )
                self.side_bar._refresh_tree()

        worker.finished.connect(_on_finished)
        worker.start()

    # --- WMS, WFS & Basemap Service Integrations ---
    PRESET_BASEMAP_URLS = {
        "sat": ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", "esri_satellite", "🛰️ Esri World Imagery (Satellite)"),
        "topo": ("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", "opentopomap", "🏔️ OpenTopoMap (Topographic)"),
        "dark": ("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", "cartodb_dark", "🌙 CartoDB (Dark Mode)"),
        "osm": ("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", "osm", "🗺️ OpenStreetMap (Default)"),
    }

    def _ensure_spatial_tab(self):
        spatial_tab = self._find_spatial_tab()
        if spatial_tab is not None:
            self.tab_widget.setCurrentWidget(spatial_tab)
            if not spatial_tab.is_spatial:
                spatial_tab.is_spatial = True
            spatial_tab.attach_map_panel(self.shared_map_panel)
            spatial_tab.set_view_mode("map")
            return spatial_tab

        curr = self._get_current_tab()
        if curr and curr.current_file is None and not curr.is_dirty and not curr.is_spatial:
            tab = curr
        else:
            tab = self._add_new_tab()

        tab.is_spatial = True
        tab.file_type = "Spatial Layer"
        tab.attach_map_panel(self.shared_map_panel)
        tab.set_view_mode("map")
        self._update_tab_title(tab)
        self.tab_widget.setCurrentWidget(tab)
        return tab

    def _add_preset_service(self, key: str):
        if key not in self.PRESET_BASEMAP_URLS:
            return
        url, layer_name, title = self.PRESET_BASEMAP_URLS[key]
        layer_id = f"service_{key}"
        self._ensure_spatial_tab()
        self.shared_map_panel.add_wms_layer(layer_id, url, layer_name, title=title)
        ToastNotification.show_toast(self, f"Service Added: {title}", "info")

    def _clear_all_basemaps(self):
        for key in self.PRESET_BASEMAP_URLS:
            self.shared_map_panel.remove_wms_layer(f"service_{key}")
        self.shared_map_panel.set_basemap("none")
        ToastNotification.show_toast(self, "Basemaps cleared", "info")

    def _show_service_menu(self):
        self._ensure_spatial_tab()
        menu = QMenu(self)

        # Basemap & Map Services Options
        menu.addSection("🗺️ Basemap & Map Services")
        act_osm = menu.addAction("🗺️ OpenStreetMap (Default)")
        act_osm.triggered.connect(lambda: self._add_preset_service("osm"))

        act_sat = menu.addAction("🛰️ Esri World Imagery (Satellite)")
        act_sat.triggered.connect(lambda: self._add_preset_service("sat"))

        act_topo = menu.addAction("🏔️ OpenTopoMap (Topographic)")
        act_topo.triggered.connect(lambda: self._add_preset_service("topo"))

        act_dark = menu.addAction("🌙 CartoDB (Dark Mode)")
        act_dark.triggered.connect(lambda: self._add_preset_service("dark"))

        menu.addSeparator()
        menu.addSection("🌐 Web Services (OGC)")
        act_wms = menu.addAction("🗺️ Add Custom WMS Layer...")
        act_wms.triggered.connect(self._show_wms_dialog)

        act_wfs = menu.addAction("📡 Download WFS Vector Layer...")
        act_wfs.triggered.connect(self._show_wfs_dialog)

        menu.addSeparator()
        act_none = menu.addAction("🚫 Remove Basemap (Blank Canvas)")
        act_none.triggered.connect(self._clear_all_basemaps)

        menu.exec(QCursor.pos())

    def _show_wms_dialog(self):
        self._ensure_spatial_tab()
        dlg = WMSDialog(self)
        if dlg.exec():
            layer_id = f"wms_{self._wms_counter}"
            self._wms_counter += 1
            self.shared_map_panel.add_wms_layer(layer_id, dlg.wms_url, dlg.layer_name, dlg.format, dlg.transparent, title=dlg.title)
            ToastNotification.show_toast(self, f"WMS Layer Added: {dlg.title}", "info")

    def _show_wfs_dialog(self):
        self._ensure_spatial_tab()
        dlg = WFSDialog(self)
        if dlg.exec():
            self.progress_bar.show()
            self.wfs_worker = WFSWorker(dlg.wfs_url, dlg.type_name, dlg.limit)
            self.wfs_worker.finished.connect(self._on_wfs_download_finished)
            self.wfs_worker.start()

    def _on_wfs_download_finished(self, layer_name: str, gdf: object, error: str):
        self.progress_bar.hide()
        if error:
            ToastNotification.show_toast(self, f"WFS Error: {error}", "error")
            return

        if gdf is not None and not gdf.empty:
            spatial_tab = self._ensure_spatial_tab()
            wfs_title = f"{layer_name} (WFS)"
            spatial_tab.add_spatial_layer(file_path=None, gdf=gdf, custom_name=wfs_title, is_wfs=True)
            self._update_tab_title(spatial_tab)
            QTimer.singleShot(150, lambda: self.shared_map_panel.fit_layer_bounds(spatial_tab.layer_id))
            ToastNotification.show_toast(self, f"WFS Layer Added: {wfs_title} ({len(gdf):,} features)", "info")

    def _on_wms_remove_requested(self, layer_id: str):
        self.shared_map_panel.remove_wms_layer(layer_id)
        ToastNotification.show_toast(self, "WMS Layer Removed", "info")

    # --- Geoprocessing Operations via Background Worker ---
    def _run_spatial_worker(self, op_name: str, gdf: gpd.GeoDataFrame, **params):
        if gdf is None or gdf.empty:
            ToastNotification.show_toast(self, "No spatial data found to process", "warning")
            return

        self.progress_bar.show()
        self.spatial_worker = SpatialOpWorker(op_name, gdf, **params)
        self.spatial_worker.finished.connect(self._on_spatial_op_finished)
        self.spatial_worker.start()

    def _on_spatial_op_finished(self, op_name: str, result: object, error: str):
        self.progress_bar.hide()
        if error:
            ToastNotification.show_toast(self, f"Processing error: {error}", "error")
            return

        tab = self._get_current_tab()
        if not tab:
            return

        if op_name in ("buffer", "dissolve", "calc_geometry", "reproject", "set_crs", "centroids", "bounding_boxes", "convex_hull"):
            if op_name == "reproject":
                as_new_layer = getattr(self.spatial_worker, "params", {}).get("as_new_layer", False)
                target_crs = getattr(self.spatial_worker, "params", {}).get("target_crs", "")
                new_crs = str(result.crs) if result is not None and result.crs else target_crs or "EPSG:4326"

                if as_new_layer:
                    orig_name = tab.get_active_layer_name() if hasattr(tab, "get_active_layer_name") else "Layer"
                    new_name = f"{orig_name} [{new_crs}]"
                    new_id = tab.add_spatial_layer(file_path=None, gdf=result, custom_name=new_name)
                    self._update_tab_title(tab)
                    self.shared_map_panel.fit_layer_bounds(new_id)
                else:
                    orig_name = tab.get_active_layer_name() if hasattr(tab, "get_active_layer_name") else ""
                    import re
                    clean_orig = re.sub(r'\s*\[EPSG:[0-9]+\]', '', orig_name)
                    updated_name = f"{clean_orig} [{new_crs}]"
                    tab.update_spatial_gdf(result, fit_bounds=True, new_name=updated_name)
                    self._update_tab_title(tab)

                self.btn_status_crs.setText(f"🌐 {new_crs}")
                self.btn_status_crs.show()
                ToastNotification.show_toast(self, f"✅ Reprojected to {new_crs} successfully!", "info")

            elif op_name == "set_crs":
                new_crs = str(result.crs) if result is not None and result.crs else "EPSG:4326"
                tab.update_spatial_gdf(result, fit_bounds=True)
                self.btn_status_crs.setText(f"🌐 {new_crs}")
                self.btn_status_crs.show()
                ToastNotification.show_toast(self, f"✅ CRS set to {new_crs}!", "info")

            else:
                tab.update_spatial_gdf(result)
                ToastNotification.show_toast(self, f"✅ {op_name.title()} operation completed!", "info")

        elif op_name == "validate":
            val_info = result
            invalid_cnt = val_info.get("invalid_count", 0)
            total_cnt = val_info.get("total_features", 0)
            empty_cnt = val_info.get("empty_count", 0)
            if invalid_cnt == 0:
                msg = f"All {total_cnt:,} geometries are valid!"
                if empty_cnt > 0:
                    msg += f" ({empty_cnt} empty/null features)"
                ToastNotification.show_toast(self, f"✅ {msg}", "success")
                QMessageBox.information(self, "Geometry Validation", msg)
            else:
                reasons = val_info.get("reasons", [])
                reasons_preview = "\n".join(f"• {r}" for r in reasons[:8])
                if len(reasons) > 8:
                    reasons_preview += f"\n...and {len(reasons) - 8} more."
                ToastNotification.show_toast(self, f"⚠️ Found {invalid_cnt:,} invalid geometries!", "warning")
                QMessageBox.warning(
                    self,
                    "Geometry Validation",
                    f"Validation Result:\n\n"
                    f"• Total Features: {total_cnt:,}\n"
                    f"• Valid Geometries: {val_info.get('valid_count', 0):,}\n"
                    f"• Invalid Geometries: {invalid_cnt:,}\n"
                    f"• Empty/Null Geometries: {empty_cnt:,}\n\n"
                    f"Sample Issues:\n{reasons_preview}\n\n"
                    f"You can use 'GIS ➔ Repair Geometries' to automatically fix invalid geometries."
                )

        elif op_name in ("repair", "validate_repair"):
            repaired_gdf, fixed_count = result
            tab.update_spatial_gdf(repaired_gdf)
            if fixed_count > 0:
                ToastNotification.show_toast(self, f"🔧 {fixed_count:,} invalid geometries repaired!", "success")
                QMessageBox.information(self, "Geometry Repair", f"Successfully repaired {fixed_count:,} invalid geometries using MakeValid.")
            else:
                ToastNotification.show_toast(self, "All geometries are already valid. No repairs needed.", "info")

        elif op_name == "simplify":
            simplified_gdf, orig_v, simp_v = result
            tab.update_spatial_gdf(simplified_gdf)
            pct = ((orig_v - simp_v) / orig_v * 100) if orig_v > 0 else 0
            ToastNotification.show_toast(self, f"Simplified: {orig_v:,} -> {simp_v:,} vertices ({pct:.1f}%)", "info")

        elif op_name == "export":
            ToastNotification.show_toast(self, "Data exported successfully!", "info")

    def _buffer_geometries(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "No active spatial layer", "warning")
            return
        crs_str = str(tab._current_gdf.crs) if tab._current_gdf.crs else None
        dlg = BufferDialog(crs=crs_str, parent=self)
        if dlg.exec():
            self._run_spatial_worker("buffer", tab._current_gdf, distance=dlg.distance, unit=dlg.unit)

    def _dissolve_geometries(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "No active spatial layer", "warning")
            return
        cols = [c for c in tab._current_gdf.columns if c != tab._current_gdf.geometry.name]
        dlg = DissolveDialog(cols, parent=self)
        if dlg.exec():
            self._run_spatial_worker("dissolve", tab._current_gdf, by_column=dlg.by_column)

    def _calc_geometry_attributes(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "No active spatial layer", "warning")
            return
        self._run_spatial_worker("calc_geometry", tab._current_gdf)

    def _simplify_geometries(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "No active spatial layer", "warning")
            return
        v_count = SpatialOps.count_vertices(tab._current_gdf)
        crs_str = str(tab._current_gdf.crs) if tab._current_gdf.crs else None
        dlg = SimplifyDialog(crs_str, v_count, parent=self)
        if dlg.exec():
            self._run_spatial_worker("simplify", tab._current_gdf, tolerance=dlg.tolerance, preserve_topology=dlg.preserve_topology)

    def _show_topology_checker(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "No active spatial layer for topology check", "warning")
            return

        from ui.topology_dialog import TopologyCheckerDialog
        layer_name = os.path.basename(tab.current_file) if tab.current_file else "Spatial Layer"

        def _on_topology_layer_updated(new_gdf):
            tab.update_spatial_gdf(new_gdf)

        # If already open, update to active layer and bring to focus without blocking main window
        if hasattr(self, "topology_dialog") and self.topology_dialog is not None and self.topology_dialog.isVisible():
            self.topology_dialog.update_layer(tab._current_gdf, layer_name, _on_topology_layer_updated, layer_id=tab.layer_id)
            self.topology_dialog.raise_()
            self.topology_dialog.activateWindow()
            return

        self.topology_dialog = TopologyCheckerDialog(
            gdf=tab._current_gdf,
            layer_name=layer_name,
            map_panel=self.shared_map_panel,
            on_layer_updated=_on_topology_layer_updated,
            layer_id=tab.layer_id,
            parent=self
        )
        self.topology_dialog.show()
        self.topology_dialog.raise_()
        self.topology_dialog.activateWindow()

    def _validate_geometries(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "No active spatial layer", "warning")
            return
        self._run_spatial_worker("validate", tab._current_gdf)

    def _repair_geometries(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "No active spatial layer", "warning")
            return
        self._run_spatial_worker("repair", tab._current_gdf)

    def _validate_repair_geometries(self):
        self._repair_geometries()

    def _show_crs_menu(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None:
            ToastNotification.show_toast(self, "No active spatial layer", "warning")
            return
        curr_crs = str(tab._current_gdf.crs) if tab._current_gdf.crs else "Undefined"
        menu = QMenu(self)
        menu.addSection(f"🌐 Layer CRS: {curr_crs}")
        act_reproj = menu.addAction("🔄 Reproject Layer (Transform Coordinates)...")
        act_reproj.triggered.connect(self._reproject_crs)
        act_set = menu.addAction("⚙️ Set Layer CRS (Override Definition Only)...")
        act_set.triggered.connect(self._set_crs)
        menu.addSeparator()
        act_info = menu.addAction("ℹ️ Layer CRS & Extent Information...")
        act_info.triggered.connect(self._show_layer_info)
        menu.exec(QCursor.pos())

    def _set_crs(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "No active spatial layer to set CRS", "warning")
            return
        curr_crs = str(tab._current_gdf.crs) if tab._current_gdf.crs else "None"
        dlg = CRSDialog("Set Layer CRS (Override Definition)", curr_crs, self, is_reproject=False)
        if dlg.exec() and dlg.selected_epsg:
            self._run_spatial_worker("set_crs", tab._current_gdf, new_crs=dlg.selected_epsg)

    def _reproject_crs(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "No active spatial layer to reproject", "warning")
            return
        curr_crs = str(tab._current_gdf.crs) if tab._current_gdf.crs else "None"
        dlg = CRSDialog("Reproject Layer (Transform Coordinates)", curr_crs, self, is_reproject=True)
        if dlg.exec() and dlg.selected_epsg:
            self._run_spatial_worker("reproject", tab._current_gdf, target_crs=dlg.selected_epsg, as_new_layer=dlg.as_new_layer)

    def _export_spatial_data(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "No spatial data to export", "warning")
            return
        dlg = ExportSpatialDialog(tab.current_file, self)
        if dlg.exec() and dlg.target_path:
            self._run_spatial_worker("export", tab._current_gdf, target_path=dlg.target_path)

    def _show_layer_info(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            ToastNotification.show_toast(self, "No spatial layer found", "warning")
            return
        summary = SpatialOps.get_summary(tab._current_gdf)
        dlg = SpatialInfoDialog(summary, tab.current_file, self)
        dlg.exec()

    def _load_sample_spatial_data(self):
        sample_gdf = SpatialOps.create_sample_spatial_data()
        self._on_file_loaded("turkey_sample_zones.geojson", "", True, sample_gdf, None)
        ToastNotification.show_toast(self, "🧪 Sample Spatial Data Loaded!", "info")

    def _show_find(self):
        tab = self._get_current_tab()
        if not tab or tab.is_spatial or tab.file_type in ("Spreadsheet", "Word", "PDF"):
            return
        if hasattr(tab, "text_editor"):
            if tab.text_editor.isHidden():
                tab.set_view_mode("code")
            tab.text_editor.trigger_find()

    def _show_replace(self):
        tab = self._get_current_tab()
        if not tab or tab.is_spatial or tab.file_type in ("Spreadsheet", "Word", "PDF"):
            return
        if hasattr(tab, "text_editor"):
            if tab.text_editor.isHidden():
                tab.set_view_mode("code")
            tab.text_editor.trigger_replace()

    def _change_theme(self, theme_name: str):
        ThemeManager.apply_theme(QApplication.instance(), theme_name)
        if hasattr(self, "shared_map_panel") and self.shared_map_panel:
            self.shared_map_panel.set_theme_tiles(theme_name)
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if tab:
                if hasattr(tab, "apply_theme"):
                    tab.apply_theme(theme_name)
                else:
                    if hasattr(tab, "text_editor") and tab.text_editor:
                        tab.text_editor.setTheme(theme_name)
                    if hasattr(tab, "map_panel") and tab.map_panel:
                        tab.map_panel.set_theme_tiles(theme_name)
        settings = QSettings("ChiselEditor", "ChiselEditor")
        settings.setValue("current_theme", theme_name)

    def _show_shortcuts(self):
        QMessageBox.information(
            self, "Keyboard Shortcuts",
            "<b>Keyboard Shortcuts:</b><br><br>"
            "• <b>Ctrl+N</b>: New File<br>"
            "• <b>Ctrl+O</b>: Open File<br>"
            "• <b>Ctrl+K, Ctrl+O</b>: Open Folder (Workspace)<br>"
            "• <b>Ctrl+S</b>: Save<br>"
            "• <b>Ctrl+B</b>: Toggle Side Bar<br>"
            "• <b>F6</b>: Toggle Attribute Table<br>"
            "• <b>Ctrl+F</b>: Find (Monaco Find)<br>"
            "• <b>Ctrl+H</b>: Replace (Monaco Replace)"
        )

    def _show_about(self):
        QMessageBox.about(
            self, "About Chisel Editor",
            "<b>Chisel Editor</b><br>"
            "Modern, fast, and lightweight GIS-enabled code editor.<br><br>"
            "Quickly view, edit, and analyze vector GIS files (GeoJSON, SHP, GPKG, KML, CSV), WMS map services, "
            "and WFS features with built-in geoprocessing tools."
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
        for w in list(self._active_workers):
            if hasattr(w, "cancel"):
                w.cancel()
            w.wait(200)
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if hasattr(tab, "cleanup"):
                tab.cleanup()
        super().closeEvent(event)
