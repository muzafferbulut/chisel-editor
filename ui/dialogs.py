from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QListWidget, QPushButton)
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