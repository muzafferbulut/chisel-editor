import os
import io
import geopandas as gpd
from PyQt6.QtWidgets import (
    QMainWindow, QMenuBar, QMenu, QFileDialog, QMessageBox,
    QLabel, QApplication, QTabWidget, QProgressBar, QPushButton
)
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent, QKeySequence
from PyQt6.QtCore import Qt

from handlers.factory import HandlerFactory
from ui.dialogs import (
    CRSDialog, LayerSelectionDialog, SimplifyDialog,
    ExportSpatialDialog, SpatialInfoDialog, BufferDialog, DissolveDialog
)
from ui.toast import ToastNotification
from core.workers import FileLoadWorker, SpatialOpWorker
from core.theme import ThemeManager
from core.spatial_ops import SpatialOps
from ui.tabs import EditorTab


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self._is_loading = False
        self.spatial_worker = None
        self._init_ui()
        self._create_menus()

    def _init_ui(self):
        self.setWindowTitle("Chisel Editor - Modern GIS & Code Editor")
        self.resize(1150, 720)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.tabCloseRequested.connect(self._close_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        self.setCentralWidget(self.tab_widget)

        self.status_bar = self.statusBar()
        self.cursor_label = QLabel("Ln 1, Col 1")
        self.type_label = QLabel("Plain Text")

        self.btn_status_table = QPushButton("📊 Öznitelik Tablosu (F6)")
        self.btn_status_table.setStyleSheet("padding: 2px 8px; font-size: 11px;")
        self.btn_status_table.clicked.connect(self._toggle_attribute_table)
        self.btn_status_table.hide()

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(0)
        self.progress_bar.setMinimum(0)
        self.progress_bar.setFixedWidth(140)
        self.progress_bar.hide()

        self.status_bar.addPermanentWidget(self.btn_status_table)
        self.status_bar.addPermanentWidget(self.cursor_label)
        self.status_bar.addPermanentWidget(self.type_label)
        self.status_bar.addPermanentWidget(self.progress_bar)

        self.setAcceptDrops(True)
        self._add_new_tab()

    def _create_menus(self):
        menu_bar: QMenuBar = self.menuBar()

        # --- File Menu ---
        file_menu: QMenu = menu_bar.addMenu("File")

        new_action = QAction("New File", self)
        new_action.setShortcut(QKeySequence("Ctrl+N"))
        new_action.triggered.connect(self._add_new_tab)

        open_action = QAction("Open...", self)
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self._open_file)

        save_action = QAction("Save", self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self._save_file)

        save_as_action = QAction("Save As...", self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self._save_file_as)

        sample_action = QAction("🧪 Örnek Mekansal Veri Yükle", self)
        sample_action.setToolTip("Türkiye illeri ve bölgelerini içeren örnek GIS verisi yükler")
        sample_action.triggered.connect(self._load_sample_spatial_data)

        export_action = QAction("Export Spatial Data...", self)
        export_action.triggered.connect(self._export_spatial_data)

        close_tab_action = QAction("Close Tab", self)
        close_tab_action.setShortcut(QKeySequence("Ctrl+W"))
        close_tab_action.triggered.connect(lambda: self._close_tab(self.tab_widget.currentIndex()))

        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        exit_action.triggered.connect(self.close)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(sample_action)
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        file_menu.addAction(close_tab_action)
        file_menu.addAction(exit_action)

        # --- Edit Menu ---
        edit_menu: QMenu = menu_bar.addMenu("Edit")
        find_action = QAction("Find & Replace", self)
        find_action.setShortcut(QKeySequence("Ctrl+F"))
        find_action.triggered.connect(self._show_find_replace)
        edit_menu.addAction(find_action)

        # --- View Menu ---
        view_menu: QMenu = menu_bar.addMenu("View")

        theme_menu: QMenu = view_menu.addMenu("Theme")
        light_theme_action = QAction("Light", self)
        dark_theme_action = QAction("Dark", self)
        light_theme_action.triggered.connect(lambda: self._change_theme("light"))
        dark_theme_action.triggered.connect(lambda: self._change_theme("dark"))
        theme_menu.addAction(light_theme_action)
        theme_menu.addAction(dark_theme_action)

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

        # --- Spatial (CBS) Menu ---
        spatial_menu: QMenu = menu_bar.addMenu("Spatial")

        act_attr_table = QAction("📊 Attribute Table", self)
        act_attr_table.setShortcut(QKeySequence("F6"))
        act_attr_table.triggered.connect(self._toggle_attribute_table)

        act_fit_bounds = QAction("🎯 Fit Layer Bounds", self)
        act_fit_bounds.triggered.connect(self._fit_bounds)

        act_layer_info = QAction("ℹ️ Layer Info & Statistics...", self)
        act_layer_info.triggered.connect(self._show_layer_info)

        spatial_menu.addAction(act_attr_table)
        spatial_menu.addAction(act_fit_bounds)
        spatial_menu.addAction(act_layer_info)
        spatial_menu.addSeparator()

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

        act_bbox = QAction("📦 Generate Bounding Boxes", self)
        act_bbox.triggered.connect(self._calculate_bounding_boxes)

        act_centroids = QAction("📍 Generate Centroids", self)
        act_centroids.triggered.connect(self._calculate_centroids)

        act_hull = QAction("🔷 Calculate Convex Hull", self)
        act_hull.triggered.connect(self._calculate_convex_hull)

        spatial_menu.addAction(act_buffer)
        spatial_menu.addAction(act_dissolve)
        spatial_menu.addAction(act_calc_geom)
        spatial_menu.addAction(act_simplify)
        spatial_menu.addAction(act_validate)
        spatial_menu.addAction(act_bbox)
        spatial_menu.addAction(act_centroids)
        spatial_menu.addAction(act_hull)
        spatial_menu.addSeparator()

        act_set_crs = QAction("🌐 Set CRS...", self)
        act_set_crs.triggered.connect(self._set_crs)

        act_reproject = QAction("🔄 Reproject CRS...", self)
        act_reproject.triggered.connect(self._reproject_crs)

        spatial_menu.addAction(act_set_crs)
        spatial_menu.addAction(act_reproject)
        spatial_menu.addAction(export_action)

    def _get_current_tab(self) -> EditorTab:
        return self.tab_widget.currentWidget()

    def _add_new_tab(self) -> EditorTab:
        tab = EditorTab()
        tab.text_editor.cursorPositionChanged.connect(self._update_cursor_info)
        tab.text_editor.file_dropped.connect(self._handle_file_drop)
        tab.state_changed.connect(lambda: self._update_tab_title(tab))

        idx = self.tab_widget.addTab(tab, tab.get_title())
        self.tab_widget.setCurrentIndex(idx)
        return tab

    def _close_tab(self, index: int):
        if self.tab_widget.count() <= 1:
            self._add_new_tab()
        self.tab_widget.removeTab(index)

    def _update_tab_title(self, tab: EditorTab):
        idx = self.tab_widget.indexOf(tab)
        if idx != -1:
            self.tab_widget.setTabText(idx, tab.get_title())

    def _on_tab_changed(self, index: int):
        tab = self.tab_widget.widget(index)
        if tab:
            self.type_label.setText(tab.file_type)
            if tab.is_spatial:
                self.btn_status_table.show()
            else:
                self.btn_status_table.hide()

    def _update_cursor_info(self, line: int, col: int):
        self.cursor_label.setText(f"Ln {line}, Col {col}")

    def _set_current_view_mode(self, mode: str):
        tab = self._get_current_tab()
        if tab:
            tab.set_view_mode(mode)

    def _toggle_attribute_table(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial:
            ToastNotification.show_toast(self, "Öznitelik tablosu sadece mekansal verilerde kullanılabilir", "warning")
            return

        # If already in table_map or table, toggle back or switch
        curr_left = tab.left_stack.currentIndex()
        if curr_left == 1 and tab.splitter.sizes()[0] > 0:
            tab.set_view_mode("code_map")
        else:
            tab.set_view_mode("table_map")

    def _fit_bounds(self):
        tab = self._get_current_tab()
        if tab and tab.is_spatial:
            tab.map_panel.fit_bounds()

    def _load_sample_spatial_data(self):
        """
        Generates realistic Turkish spatial sample data for instant testing.
        """
        sample_gdf = SpatialOps.create_sample_spatial_data()
        tab = self._add_new_tab()
        tab.current_file = "turkey_sample_zones.geojson"
        tab.set_spatial_data(sample_gdf)
        self._update_tab_title(tab)
        self._on_tab_changed(self.tab_widget.currentIndex())
        ToastNotification.show_toast(self, "🧪 Örnek Mekansal Veri Başarıyla Yüklendi!", "info")

    def _open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open File", "",
            "All Supported Files (*.geojson *.json *.shp *.kml *.gpkg *.fgb *.csv *.txt *.md *.py);;All Files (*)"
        )
        if file_path:
            self._load_file(file_path)

    def _load_file(self, file_path: str, **kwargs):
        self.progress_bar.show()
        self._is_loading = True

        self.worker = FileLoadWorker(file_path, **kwargs)
        self.worker.finished.connect(self._on_file_loaded)
        self.worker.multiple_layers_detected.connect(self._on_multiple_layers)
        self.worker.start()

    def _on_file_loaded(self, file_path: str, content: str, is_spatial: bool, error: str):
        self.progress_bar.hide()
        self._is_loading = False

        if error:
            ToastNotification.show_toast(self, f"Error: {error}", "error")
            return

        tab = self._get_current_tab()
        if tab.current_file is not None or tab.is_dirty:
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

        tab.configure_for_file_type(file_type, is_spatial, content)
        self._update_tab_title(tab)
        self._on_tab_changed(self.tab_widget.currentIndex())

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
        filt = "GeoJSON (*.geojson);;All Files (*)" if tab.is_spatial else "All Files (*)"
        file_path, _ = QFileDialog.getSaveFileName(self, "Save File As", tab.current_file or "", filt)
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
            msg = f"Geometriler kontrol edildi. {fixed_count} geçersiz geometri onarıldı." if fixed_count > 0 else "Tüm geometriler geçerli!"
            ToastNotification.show_toast(self, msg, "info")

        elif op_name == "simplify":
            simplified_gdf, orig_v, simp_v = result
            tab.update_spatial_gdf(simplified_gdf)
            pct = ((orig_v - simp_v) / orig_v * 100) if orig_v > 0 else 0
            ToastNotification.show_toast(self, f"Basitleştirildi: {orig_v:,} -> {simp_v:,} köşe noktası (%{pct:.1f} azalma)", "info")

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
            self._run_spatial_worker(
                "simplify", tab._current_gdf,
                tolerance=dlg.tolerance,
                preserve_topology=dlg.preserve_topology
            )

    def _validate_repair_geometries(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            return
        self._run_spatial_worker("validate_repair", tab._current_gdf)

    def _calculate_bounding_boxes(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            return
        self._run_spatial_worker("bounding_boxes", tab._current_gdf)

    def _calculate_centroids(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            return
        self._run_spatial_worker("centroids", tab._current_gdf)

    def _calculate_convex_hull(self):
        tab = self._get_current_tab()
        if not tab or not tab.is_spatial or tab._current_gdf is None or tab._current_gdf.empty:
            return
        self._run_spatial_worker("convex_hull", tab._current_gdf, per_feature=False)

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
