import os
import subprocess
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTreeView, QTreeWidget, QTreeWidgetItem, QStackedWidget,
    QFileDialog, QHeaderView, QMenu, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QDir
from PyQt6.QtGui import QFileSystemModel, QIcon, QAction


class ActivityBar(QWidget):
    """
    Vertical icon bar on the left edge (similar to modern VS Code Activity Bar).
    Houses Explorer and GIS Layers navigation.
    """
    view_toggled = pyqtSignal(str)  # 'explorer', 'layers', 'toggle'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(46)
        self.setObjectName("activityBar")
        self._current_view = "explorer"
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(4)

        self.btn_explorer = QPushButton("📁")
        self.btn_explorer.setObjectName("activityBtn")
        self.btn_explorer.setToolTip("Dosya Gezgini (Ctrl+Shift+E)")
        self.btn_explorer.setCheckable(True)
        self.btn_explorer.setChecked(True)
        self.btn_explorer.clicked.connect(lambda: self._on_btn_clicked("explorer"))

        self.btn_layers = QPushButton("🗺️")
        self.btn_layers.setObjectName("activityBtn")
        self.btn_layers.setToolTip("Mekansal Katmanlar & OGC Servisleri (WMS/WFS)")
        self.btn_layers.setCheckable(True)
        self.btn_layers.clicked.connect(lambda: self._on_btn_clicked("layers"))

        layout.addWidget(self.btn_explorer)
        layout.addWidget(self.btn_layers)
        layout.addStretch()

    def _on_btn_clicked(self, view_name: str):
        if self._current_view == view_name:
            self.view_toggled.emit("toggle")
        else:
            self._current_view = view_name
            self.btn_explorer.setChecked(view_name == "explorer")
            self.btn_layers.setChecked(view_name == "layers")
            self.view_toggled.emit(view_name)

    def set_active_view(self, view_name: str):
        self._current_view = view_name
        self.btn_explorer.setChecked(view_name == "explorer")
        self.btn_layers.setChecked(view_name == "layers")


class ExplorerPanel(QWidget):
    """
    Modern Project / Folder File Tree Explorer.
    Displays the active workspace folder name in the header.
    """
    file_open_requested = pyqtSignal(str)
    folder_change_requested = pyqtSignal()

    def __init__(self, root_path: str = None, parent=None):
        super().__init__(parent)
        self._root_path = root_path or os.getcwd()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Modern Header Bar
        header = QHBoxLayout()
        header.setContentsMargins(4, 4, 4, 2)
        header.setSpacing(6)

        folder_name = os.path.basename(self._root_path) or self._root_path or "PROJE"
        self.lbl_title = QLabel(f"📁 {folder_name.upper()}")
        self.lbl_title.setStyleSheet("font-weight: 700; font-size: 11px; letter-spacing: 0.5px; color: #858585;")
        self.lbl_title.setToolTip(self._root_path)
        header.addWidget(self.lbl_title)
        header.addStretch()

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setFixedSize(24, 24)
        self.btn_refresh.setToolTip("Gezgini Yenile")
        self.btn_refresh.setStyleSheet("QPushButton { border: none; background: transparent; border-radius: 3px; font-size: 11px; } QPushButton:hover { background: rgba(128, 128, 128, 0.2); }")
        self.btn_refresh.clicked.connect(self._refresh_tree)
        header.addWidget(self.btn_refresh)

        self.btn_open_folder = QPushButton("📂")
        self.btn_open_folder.setFixedSize(24, 24)
        self.btn_open_folder.setToolTip("Klasör Aç / Değiştir (Ctrl+K, Ctrl+O)")
        self.btn_open_folder.setStyleSheet("QPushButton { border: none; background: transparent; border-radius: 3px; font-size: 12px; } QPushButton:hover { background: rgba(128, 128, 128, 0.2); }")
        self.btn_open_folder.clicked.connect(self.folder_change_requested.emit)
        header.addWidget(self.btn_open_folder)

        layout.addLayout(header)

        # File Tree Model & View
        self.fs_model = QFileSystemModel()
        self.fs_model.setRootPath(self._root_path)

        self.tree = QTreeView()
        self.tree.setModel(self.fs_model)
        self.tree.setRootIndex(self.fs_model.index(self._root_path))
        self.tree.setAnimated(True)
        self.tree.setIndentation(16)
        self.tree.setSortingEnabled(True)
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree.setStyleSheet("QTreeView { border: none; } QTreeView::item { height: 25px; padding: 1px 4px; }")

        # Hide extra columns for clean VS Code appearance
        self.tree.hideColumn(1)
        self.tree.hideColumn(2)
        self.tree.hideColumn(3)
        self.tree.header().setVisible(False)

        self.tree.doubleClicked.connect(self._on_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

        layout.addWidget(self.tree)

    def set_root_path(self, path: str):
        if os.path.exists(path):
            self._root_path = path
            self.fs_model.setRootPath(path)
            self.tree.setRootIndex(self.fs_model.index(path))
            folder_name = os.path.basename(path) or path or "PROJE"
            self.lbl_title.setText(f"📁 {folder_name.upper()}")
            self.lbl_title.setToolTip(path)

    def _refresh_tree(self):
        root = self._root_path
        self.fs_model.setRootPath("")
        self.fs_model.setRootPath(root)
        self.tree.setRootIndex(self.fs_model.index(root))

    def _on_item_double_clicked(self, index):
        file_path = self.fs_model.filePath(index)
        if os.path.isfile(file_path):
            self.file_open_requested.emit(file_path)

    def _on_context_menu(self, pos):
        index = self.tree.indexAt(pos)
        if not index.isValid():
            return
        file_path = self.fs_model.filePath(index)
        menu = QMenu(self)

        if os.path.isfile(file_path):
            act_open = QAction("📄 Dosyayı Aç", self)
            act_open.triggered.connect(lambda: self.file_open_requested.emit(file_path))
            menu.addAction(act_open)

        act_copy_path = QAction("📋 Dosya Yolunu Kopyala", self)
        act_copy_path.triggered.connect(lambda: QApplication.clipboard().setText(file_path))
        menu.addAction(act_copy_path)

        act_reveal = QAction("📂 Dosya Gezgininde Göster", self)
        def _reveal():
            target = file_path if os.path.isdir(file_path) else os.path.dirname(file_path)
            if os.name == 'nt':
                subprocess.Popen(f'explorer /select,"{os.path.normpath(file_path)}"')
            else:
                subprocess.Popen(['xdg-open', target])
        act_reveal.triggered.connect(_reveal)
        menu.addAction(act_reveal)

        menu.exec(self.tree.viewport().mapToGlobal(pos))


class LayersPanel(QWidget):
    """
    GIS Layers & Services (WMS/WFS) management panel.
    """
    add_wms_requested = pyqtSignal()
    add_wfs_requested = pyqtSignal()
    fit_bounds_requested = pyqtSignal()
    table_requested = pyqtSignal()
    wms_visibility_changed = pyqtSignal(str, bool)
    wms_remove_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # Header Bar
        header = QHBoxLayout()
        header.setContentsMargins(4, 4, 4, 2)
        lbl_title = QLabel("KATMANLAR & OGC")
        lbl_title.setStyleSheet("font-weight: 700; font-size: 11px; letter-spacing: 0.5px; color: #858585;")
        header.addWidget(lbl_title)
        header.addStretch()

        btn_wms = QPushButton("+ WMS")
        btn_wms.setToolTip("WMS Web Harita Servisi Ekle")
        btn_wms.setStyleSheet("padding: 2px 7px; font-size: 10px; font-weight: 600; border-radius: 3px;")
        btn_wms.clicked.connect(self.add_wms_requested.emit)

        btn_wfs = QPushButton("+ WFS")
        btn_wfs.setToolTip("WFS Vektör Veri Servisi İndir")
        btn_wfs.setStyleSheet("padding: 2px 7px; font-size: 10px; font-weight: 600; border-radius: 3px;")
        btn_wfs.clicked.connect(self.add_wfs_requested.emit)

        header.addWidget(btn_wms)
        header.addWidget(btn_wfs)
        layout.addLayout(header)

        # Layer Tree
        self.layer_tree = QTreeWidget()
        self.layer_tree.setHeaderHidden(True)
        self.layer_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.layer_tree.customContextMenuRequested.connect(self._on_context_menu)
        self.layer_tree.itemChanged.connect(self._on_item_changed)
        self.layer_tree.setStyleSheet("QTreeWidget { border: none; } QTreeWidget::item { height: 26px; padding: 2px 4px; }")
        layout.addWidget(self.layer_tree)

        # Top-level Groups
        self.root_vectors = QTreeWidgetItem(["🗺️ Vektör Katmanlar"])
        self.root_vectors.setExpanded(True)
        self.layer_tree.addTopLevelItem(self.root_vectors)

        self.root_wms = QTreeWidgetItem(["🌐 WMS Servisleri"])
        self.root_wms.setExpanded(True)
        self.layer_tree.addTopLevelItem(self.root_wms)

        # Bottom Quick Action Toolbar
        action_bar = QHBoxLayout()
        action_bar.setSpacing(6)

        btn_zoom = QPushButton("🎯 Sığdır")
        btn_zoom.setToolTip("Katman sınırlarına odaklan")
        btn_zoom.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        btn_zoom.clicked.connect(self.fit_bounds_requested.emit)

        btn_table = QPushButton("📊 Tablo (F6)")
        btn_table.setToolTip("Öznitelik Tablosunu Aç / Kapat")
        btn_table.setStyleSheet("padding: 4px 8px; font-size: 11px; font-weight: 600;")
        btn_table.clicked.connect(self.table_requested.emit)

        action_bar.addWidget(btn_zoom)
        action_bar.addWidget(btn_table)
        layout.addLayout(action_bar)

    def set_active_vector_layer(self, name: str, feature_count: int = 0):
        self.root_vectors.takeChildren()
        if name:
            item = QTreeWidgetItem([f"📍 {name} ({feature_count:,} özellik)"])
            item.setCheckState(0, Qt.CheckState.Checked)
            self.root_vectors.addChild(item)
        else:
            item = QTreeWidgetItem(["(Aktif vektör yok)"])
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.root_vectors.addChild(item)

    def add_wms_layer_item(self, layer_id: str, title: str):
        item = QTreeWidgetItem([f"🌐 {title}"])
        item.setData(0, Qt.ItemRole.UserRole if hasattr(Qt, 'ItemRole') else Qt.ItemDataRole.UserRole, layer_id)
        item.setCheckState(0, Qt.CheckState.Checked)
        self.root_wms.addChild(item)

    def remove_wms_layer_item(self, layer_id: str):
        role = Qt.ItemRole.UserRole if hasattr(Qt, 'ItemRole') else Qt.ItemDataRole.UserRole
        for i in range(self.root_wms.childCount()):
            item = self.root_wms.child(i)
            if item.data(0, role) == layer_id:
                self.root_wms.removeChild(item)
                break

    def _on_item_changed(self, item: QTreeWidgetItem, column: int):
        role = Qt.ItemRole.UserRole if hasattr(Qt, 'ItemRole') else Qt.ItemDataRole.UserRole
        layer_id = item.data(0, role)
        if layer_id:
            is_visible = (item.checkState(0) == Qt.CheckState.Checked)
            self.wms_visibility_changed.emit(layer_id, is_visible)

    def _on_context_menu(self, pos):
        item = self.layer_tree.itemAt(pos)
        if not item:
            return
        role = Qt.ItemRole.UserRole if hasattr(Qt, 'ItemRole') else Qt.ItemDataRole.UserRole
        layer_id = item.data(0, role)
        if layer_id:
            menu = QMenu(self)
            act_remove = QAction("WMS Katmanını Kaldır", self)
            act_remove.triggered.connect(lambda: self.wms_remove_requested.emit(layer_id))
            menu.addAction(act_remove)
            menu.exec(self.layer_tree.viewport().mapToGlobal(pos))


class SideBar(QWidget):
    """
    Modern Collapsible Side Bar housing Explorer and GIS Layers panels.
    """
    file_open_requested = pyqtSignal(str)
    folder_change_requested = pyqtSignal()
    add_wms_requested = pyqtSignal()
    add_wfs_requested = pyqtSignal()
    fit_bounds_requested = pyqtSignal()
    table_requested = pyqtSignal()
    wms_visibility_changed = pyqtSignal(str, bool)
    wms_remove_requested = pyqtSignal(str)

    def __init__(self, root_path: str = None, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)
        self.setObjectName("sideBar")
        self._init_ui(root_path)

    def _init_ui(self, root_path: str = None):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.stack = QStackedWidget()

        self.explorer_panel = ExplorerPanel(root_path)
        self.explorer_panel.file_open_requested.connect(self.file_open_requested.emit)
        self.explorer_panel.folder_change_requested.connect(self.folder_change_requested.emit)

        self.layers_panel = LayersPanel()
        self.layers_panel.add_wms_requested.connect(self.add_wms_requested.emit)
        self.layers_panel.add_wfs_requested.connect(self.add_wfs_requested.emit)
        self.layers_panel.fit_bounds_requested.connect(self.fit_bounds_requested.emit)
        self.layers_panel.table_requested.connect(self.table_requested.emit)
        self.layers_panel.wms_visibility_changed.connect(self.wms_visibility_changed.emit)
        self.layers_panel.wms_remove_requested.connect(self.wms_remove_requested.emit)

        self.stack.addWidget(self.explorer_panel)  # 0
        self.stack.addWidget(self.layers_panel)    # 1

        layout.addWidget(self.stack)

    def show_view(self, view_name: str):
        if view_name == "explorer":
            self.stack.setCurrentIndex(0)
            self.show()
        elif view_name == "layers":
            self.stack.setCurrentIndex(1)
            self.show()
