from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QListWidget, QPushButton, QLineEdit, QCheckBox,
                             QMessageBox)
from PyQt6.QtGui import QTextDocument
from PyQt6.QtCore import Qt


class LayerSelectionDialog(QDialog):

    
    def __init__(self, file_name: str, layers: list, parent=None):
        super().__init__(parent)
        self.selected_layer = None
        self.merge_all = False
        self.layers = layers
        
        self.setWindowTitle("Layer Selection")
        self.resize(450, 350)
        
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        
        self._setup_ui(file_name)

        
    def _setup_ui(self, file_name):
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        lbl_title = QLabel(f"<b>{file_name}</b> contains multiple layers.<br>Please select a layer to import:")
        lbl_title.setWordWrap(True)
        layout.addWidget(lbl_title)
        self.list_widget = QListWidget()
        self.list_widget.addItems(self.layers)
        self.list_widget.setCurrentRow(0)
        layout.addWidget(self.list_widget)
        
        btn_layout = QHBoxLayout()
        
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_cancel")
        
        self.btn_merge = QPushButton("Merge All")
        self.btn_merge.setObjectName("btn_merge")
        
        self.btn_load = QPushButton("Load Selected")
        self.btn_load.setObjectName("btn_load")
        
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_merge.clicked.connect(self._on_merge)
        self.btn_load.clicked.connect(self._on_load)
        
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_merge)
        btn_layout.addWidget(self.btn_load)
        
        layout.addLayout(btn_layout)

        
    def _on_merge(self):
        self.merge_all = True
        self.accept()

        
    def _on_load(self):
        item = self.list_widget.currentItem()
        if item:
            self.selected_layer = item.text()
        self.accept()


class CRSDialog(QDialog):


    def __init__(self, title: str, current_crs: str = None, parent=None):
        super().__init__(parent)
        self.selected_epsg = None
        self.setWindowTitle(title)
        self.resize(300, 120)
        self.setModal(True)
        
        self._setup_ui(current_crs)


    def _setup_ui(self, current_crs):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 20, 20, 20)

        if current_crs:
            lbl_current = QLabel(f"<b>Current CRS:</b> {current_crs}")
            layout.addWidget(lbl_current)

        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("<b>Target EPSG:</b>"))
        
        self.epsg_input = QLineEdit()
        self.epsg_input.setPlaceholderText("e.g. 4326 or 32636")
        input_layout.addWidget(self.epsg_input)
        
        layout.addLayout(input_layout)
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_cancel")
        
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.setObjectName("btn_load")
        
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(self._on_apply)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_apply)
        
        layout.addLayout(btn_layout)


    def _on_apply(self):
        epsg_text = self.epsg_input.text().strip()
        
        if epsg_text.isdigit():
            self.selected_epsg = f"EPSG:{epsg_text}"
            self.accept()
        elif epsg_text.lower().startswith("epsg:") and epsg_text.split(":")[-1].isdigit():
            self.selected_epsg = epsg_text.upper()
            self.accept()
        else:
            QMessageBox.warning(self, "Invalid Input", "Please enter a valid EPSG code (e.g.,4326).")


class CommandPaletteDialog(QDialog):


    def __init__(self, commands: dict, parent=None):
        super().__init__(parent)
        self.commands = commands
        self.selected_command = None
        self.setWindowTitle("Command Palette")
        self.resize(400, 300)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        
        self._setup_ui()


    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type a command (e.g. format, crs...)")
        
        self.list_widget = QListWidget()
        self.list_widget.addItems(self.commands.keys())
        
        layout.addWidget(self.search_input)
        layout.addWidget(self.list_widget)
        
        self.search_input.textChanged.connect(self._filter)
        self.list_widget.itemActivated.connect(self._accept_command)
        self.search_input.returnPressed.connect(self._on_enter)


    def _filter(self, text):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setHidden(text.lower() not in item.text().lower())

        for i in range(self.list_widget.count()):
            if not self.list_widget.item(i).isHidden():
                self.list_widget.setCurrentRow(i)
                break


    def _on_enter(self):
        current_item = self.list_widget.currentItem()
        if current_item and not current_item.isHidden():
            self.selected_command = current_item.text()
            self.accept()


    def _accept_command(self, item):
        self.selected_command = item.text()
        self.accept()