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


class FindReplaceDialog(QDialog):


    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Find & Replace")
        self.setModal(False) 
        self.resize(350, 150)
        self._setup_ui()


    def _setup_ui(self):
        layout = QVBoxLayout(self)

        find_layout = QHBoxLayout()
        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Find...")
        self.btn_find_prev = QPushButton("<")
        self.btn_find_next = QPushButton(">")
        self.btn_find_prev.setFixedWidth(30)
        self.btn_find_next.setFixedWidth(30)
        
        find_layout.addWidget(QLabel("Find:"))
        find_layout.addWidget(self.find_input)
        find_layout.addWidget(self.btn_find_prev)
        find_layout.addWidget(self.btn_find_next)

        replace_layout = QHBoxLayout()
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replace with...")
        self.btn_replace = QPushButton("Replace")
        self.btn_replace_all = QPushButton("Replace All")
        
        replace_layout.addWidget(QLabel("Replace:"))
        replace_layout.addWidget(self.replace_input)
        replace_layout.addWidget(self.btn_replace)
        replace_layout.addWidget(self.btn_replace_all)

        options_layout = QHBoxLayout()
        self.cb_match_case = QCheckBox("Match Case")
        self.cb_whole_word = QCheckBox("Whole Word")
        options_layout.addWidget(self.cb_match_case)
        options_layout.addWidget(self.cb_whole_word)
        options_layout.addStretch()

        layout.addLayout(find_layout)
        layout.addLayout(replace_layout)
        layout.addLayout(options_layout)

        self.btn_find_next.clicked.connect(self.find_next)
        self.btn_find_prev.clicked.connect(self.find_prev)
        self.btn_replace.clicked.connect(self.replace)
        self.btn_replace_all.clicked.connect(self.replace_all)


    def _get_find_flags(self, backward=False):
        flags = QTextDocument.FindFlag(0)
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        if self.cb_match_case.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.cb_whole_word.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        return flags


    def find_next(self):
        text = self.find_input.text()
        if not text: return
        
        found = self.editor.find(text, self._get_find_flags())
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            self.editor.setTextCursor(cursor)
            self.editor.find(text, self._get_find_flags())


    def find_prev(self):
        text = self.find_input.text()
        if not text: return
        
        found = self.editor.find(text, self._get_find_flags(backward=True))
        if not found:
            cursor = self.editor.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.editor.setTextCursor(cursor)
            self.editor.find(text, self._get_find_flags(backward=True))


    def replace(self):
        text = self.find_input.text()
        replace_text = self.replace_input.text()
        if not text: return
        
        cursor = self.editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == text:
            cursor.insertText(replace_text)
        
        self.find_next()


    def replace_all(self):
        text = self.find_input.text()
        replace_text = self.replace_input.text()
        if not text: return

        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        
        cursor.movePosition(cursor.MoveOperation.Start)
        self.editor.setTextCursor(cursor)
        
        count = 0
        while self.editor.find(text, self._get_find_flags()):
            self.editor.textCursor().insertText(replace_text)
            count += 1
            
        cursor.endEditBlock()
        
        if self.parent():
            self.parent().statusBar().showMessage(f"Replaced {count} occurrences.", 3000)


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