import os
import subprocess
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTreeView, QMenu, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFileSystemModel, QAction


class ExplorerPanel(QWidget):
    """
    Modern Project / Folder File Tree Explorer.
    Displays the active workspace folder name in the header.
    """
    file_open_requested = pyqtSignal(str)
    file_convert_requested = pyqtSignal(str, str)
    folder_change_requested = pyqtSignal()

    def __init__(self, root_path: str = None, parent=None):
        super().__init__(parent)
        self.setObjectName("sideBar")
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

        folder_name = os.path.basename(self._root_path) or self._root_path or "PROJECT"
        self.lbl_title = QLabel(f"📁 {folder_name.upper()}")
        self.lbl_title.setStyleSheet("font-weight: 700; font-size: 11px; letter-spacing: 0.5px; color: #858585;")
        self.lbl_title.setToolTip(self._root_path)
        header.addWidget(self.lbl_title)
        header.addStretch()

        self.btn_open_folder = QPushButton("📂")
        self.btn_open_folder.setObjectName("sidebarHeaderBtn")
        self.btn_open_folder.setFixedSize(22, 22)
        self.btn_open_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_open_folder.setToolTip("Open / Change Folder (Ctrl+K, Ctrl+O)")
        self.btn_open_folder.setStyleSheet(
            "QPushButton#sidebarHeaderBtn {"
            " border: none;"
            " background: transparent;"
            " border-radius: 3px;"
            " font-size: 13px;"
            " padding: 0px;"
            " margin: 0px;"
            " text-align: center;"
            "}"
            "QPushButton#sidebarHeaderBtn:hover {"
            " background-color: rgba(128, 128, 128, 0.25);"
            "}"
            "QPushButton#sidebarHeaderBtn:pressed {"
            " background-color: rgba(128, 128, 128, 0.4);"
            "}"
        )
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

        # Hide extra columns for clean appearance
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
            folder_name = os.path.basename(path) or path or "PROJECT"
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
            act_open = QAction("📄 Open File", self)
            act_open.triggered.connect(lambda: self.file_open_requested.emit(file_path))
            menu.addAction(act_open)

            from core.converter import FileConverter
            targets = FileConverter.get_conversion_targets(file_path)
            if targets:
                menu.addSeparator()
                convert_menu = menu.addMenu("🔄 Convert to...")
                for t_ext, t_lbl in targets:
                    act_conv = QAction(t_lbl, self)
                    act_conv.triggered.connect(lambda checked, ext=t_ext, fp=file_path: self.file_convert_requested.emit(fp, ext))
                    convert_menu.addAction(act_conv)
                menu.addSeparator()

        act_copy_path = QAction("📋 Copy File Path", self)
        act_copy_path.triggered.connect(lambda: QApplication.clipboard().setText(file_path))
        menu.addAction(act_copy_path)

        act_reveal = QAction("📂 Reveal in File Explorer", self)
        def _reveal():
            target = file_path if os.path.isdir(file_path) else os.path.dirname(file_path)
            if os.name == 'nt':
                subprocess.Popen(f'explorer /select,"{os.path.normpath(file_path)}"')
            else:
                subprocess.Popen(['xdg-open', target])
        act_reveal.triggered.connect(_reveal)
        menu.addAction(act_reveal)

        menu.exec(self.tree.viewport().mapToGlobal(pos))


# SideBar is an alias to ExplorerPanel
SideBar = ExplorerPanel
