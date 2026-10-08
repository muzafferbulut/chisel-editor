import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox,
    QPushButton, QColorDialog, QInputDialog, QLabel, QFrame,
    QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (
    QFont, QTextCharFormat, QColor, QTextCursor,
    QTextBlockFormat, QTextTableFormat, QTextListFormat
)
from handlers.docx import DocxHandler


class WordDocumentEditorWidget(QWidget):
    """
    Rich Text / WYSIWYG document editor for Microsoft Word (.docx) files.
    Features Word-style formatting toolbar (Styles, Font, Size, Bold/Italic/Underline,
    Color, Alignment, Lists, Tables) with document canvas and .docx save support.
    """
    content_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self._is_loading = False
        self._is_dirty = False
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Word Formatting Toolbar
        toolbar_container = QWidget()
        toolbar_container.setStyleSheet("background-color: rgba(128, 128, 128, 0.08); border-bottom: 1px solid rgba(128, 128, 128, 0.2);")
        toolbar_layout = QHBoxLayout(toolbar_container)
        toolbar_layout.setContentsMargins(6, 4, 6, 4)
        toolbar_layout.setSpacing(4)

        # Heading / Style Selector
        self.style_combo = QComboBox()
        self.style_combo.addItems(["Normal Metin", "Başlık 1", "Başlık 2", "Başlık 3", "Başlık 4"])
        self.style_combo.setToolTip("Stil / Başlık Düzeyi")
        self.style_combo.activated.connect(self._apply_heading_style)
        toolbar_layout.addWidget(self.style_combo)

        # Font Family
        self.font_combo = QComboBox()
        self.font_combo.addItems(["Calibri", "Segoe UI", "Arial", "Times New Roman", "Verdana", "Courier New"])
        self.font_combo.setToolTip("Yazı Tipi (Font)")
        self.font_combo.currentTextChanged.connect(self._apply_font_family)
        toolbar_layout.addWidget(self.font_combo)

        # Font Size
        self.size_combo = QComboBox()
        self.size_combo.addItems(["9", "10", "11", "12", "14", "16", "18", "20", "24", "28", "32", "48"])
        self.size_combo.setCurrentText("11")
        self.size_combo.setToolTip("Yazı Boyutu")
        self.size_combo.currentTextChanged.connect(self._apply_font_size)
        toolbar_layout.addWidget(self.size_combo)

        toolbar_layout.addWidget(self._create_sep())

        # Bold, Italic, Underline, Strikethrough
        self.btn_bold = self._create_btn("<b>B</b>", "Kalın (Ctrl+B)", self._toggle_bold, checkable=True)
        toolbar_layout.addWidget(self.btn_bold)

        self.btn_italic = self._create_btn("<i>I</i>", "İtalik (Ctrl+I)", self._toggle_italic, checkable=True)
        toolbar_layout.addWidget(self.btn_italic)

        self.btn_underline = self._create_btn("<u>U</u>", "Altı Çizili (Ctrl+U)", self._toggle_underline, checkable=True)
        toolbar_layout.addWidget(self.btn_underline)

        self.btn_strike = self._create_btn("<s>S</s>", "Üstü Çizili", self._toggle_strike, checkable=True)
        toolbar_layout.addWidget(self.btn_strike)

        toolbar_layout.addWidget(self._create_sep())

        # Colors
        self.btn_text_color = self._create_btn("A", "Metin Rengi", self._pick_text_color)
        self.btn_text_color.setStyleSheet("font-weight: bold; border-bottom: 2px solid #ef4444;")
        toolbar_layout.addWidget(self.btn_text_color)

        self.btn_bg_color = self._create_btn("🖍️", "Vurgu Rengi (Arka Plan)", self._pick_bg_color)
        toolbar_layout.addWidget(self.btn_bg_color)

        toolbar_layout.addWidget(self._create_sep())

        # Alignment
        self.btn_align_left = self._create_btn("⬅", "Sola Hizala", lambda: self._set_alignment(Qt.AlignmentFlag.AlignLeft))
        toolbar_layout.addWidget(self.btn_align_left)

        self.btn_align_center = self._create_btn("⬌", "Ortala", lambda: self._set_alignment(Qt.AlignmentFlag.AlignCenter))
        toolbar_layout.addWidget(self.btn_align_center)

        self.btn_align_right = self._create_btn("➡", "Sağa Hizala", lambda: self._set_alignment(Qt.AlignmentFlag.AlignRight))
        toolbar_layout.addWidget(self.btn_align_right)

        self.btn_align_justify = self._create_btn("☰", "İki Yana Yasla", lambda: self._set_alignment(Qt.AlignmentFlag.AlignJustify))
        toolbar_layout.addWidget(self.btn_align_justify)

        toolbar_layout.addWidget(self._create_sep())

        # Lists & Tables
        self.btn_bullet_list = self._create_btn("• Liste", "Madde İşaretli Liste", self._insert_bullet_list)
        toolbar_layout.addWidget(self.btn_bullet_list)

        self.btn_num_list = self._create_btn("1. Liste", "Numaralı Liste", self._insert_numbered_list)
        toolbar_layout.addWidget(self.btn_num_list)

        self.btn_table = self._create_btn("▦ Tablo", "Tablo Ekle", self._insert_table)
        toolbar_layout.addWidget(self.btn_table)

        toolbar_layout.addStretch()
        main_layout.addWidget(toolbar_container)

        # 2. Document Canvas Container (A4 Paper Look)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        scroll_area.setStyleSheet("QScrollArea { border: none; background-color: rgba(128, 128, 128, 0.05); }")

        canvas_widget = QWidget()
        canvas_layout = QVBoxLayout(canvas_widget)
        canvas_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        canvas_layout.setContentsMargins(20, 20, 20, 20)

        self.editor = QTextEdit()
        self.editor.setMinimumWidth(720)
        self.editor.setMaximumWidth(850)
        self.editor.setMinimumHeight(900)
        self.editor.setStyleSheet(
            "QTextEdit { background-color: #ffffff; color: #222222; border: 1px solid #d0d0d0; "
            "border-radius: 4px; padding: 40px; font-family: 'Calibri', 'Segoe UI', sans-serif; font-size: 11pt; line-height: 1.4; }"
        )
        self.editor.cursorPositionChanged.connect(self._on_cursor_changed)
        self.editor.textChanged.connect(self._on_text_changed)

        canvas_layout.addWidget(self.editor)
        scroll_area.setWidget(canvas_widget)
        main_layout.addWidget(scroll_area)

    def _create_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: rgba(128, 128, 128, 0.25); width: 1px; margin: 2px 4px; border: none;")
        return sep

    def _create_btn(self, text: str, tooltip: str, callback=None, checkable: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(26)
        if checkable:
            btn.setCheckable(True)
        if callback:
            btn.clicked.connect(callback)
        btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid transparent; border-radius: 3px; padding: 0 6px; } "
            "QPushButton:hover { background-color: rgba(128, 128, 128, 0.2); } "
            "QPushButton:checked { background-color: rgba(0, 122, 204, 0.25); border: 1px solid #007acc; }"
        )
        return btn

    def load_file(self, file_path: str):
        self.current_file = file_path
        self._is_loading = True
        try:
            handler = DocxHandler()
            data = handler.read(file_path)
            self.editor.clear()
            cursor = self.editor.textCursor()

            paragraphs = data.get("paragraphs", [])
            for p_info in paragraphs:
                style_name = p_info.get("style", "Normal")
                align = p_info.get("alignment", "left")

                block_fmt = QTextBlockFormat()
                if align == "center":
                    block_fmt.setAlignment(Qt.AlignmentFlag.AlignCenter)
                elif align == "right":
                    block_fmt.setAlignment(Qt.AlignmentFlag.AlignRight)
                elif align == "justify":
                    block_fmt.setAlignment(Qt.AlignmentFlag.AlignJustify)
                else:
                    block_fmt.setAlignment(Qt.AlignmentFlag.AlignLeft)

                cursor.insertBlock(block_fmt)

                runs = p_info.get("runs", [])
                if runs:
                    for r in runs:
                        fmt = QTextCharFormat()
                        if r.get("bold"):
                            fmt.setFontWeight(QFont.Weight.Bold)
                        if r.get("italic"):
                            fmt.setFontItalic(True)
                        if r.get("underline"):
                            fmt.setFontUnderline(True)
                        if r.get("font_name"):
                            fmt.setFontFamily(r["font_name"])
                        if r.get("font_size"):
                            fmt.setFontPointSize(r["font_size"])
                        elif "heading 1" in style_name.lower():
                            fmt.setFontPointSize(18)
                            fmt.setFontWeight(QFont.Weight.Bold)
                        elif "heading 2" in style_name.lower():
                            fmt.setFontPointSize(14)
                            fmt.setFontWeight(QFont.Weight.Bold)
                        elif "heading 3" in style_name.lower():
                            fmt.setFontPointSize(12)
                            fmt.setFontWeight(QFont.Weight.Bold)

                        cursor.insertText(r.get("text", ""), fmt)
                else:
                    cursor.insertText(p_info.get("text", ""))

            # Tables
            tables = data.get("tables", [])
            for table_data in tables:
                if table_data:
                    rows = len(table_data)
                    cols = len(table_data[0]) if rows > 0 else 0
                    if rows > 0 and cols > 0:
                        cursor.insertBlock()
                        tbl_fmt = QTextTableFormat()
                        tbl_fmt.setBorder(1)
                        tbl_fmt.setCellPadding(4)
                        table = cursor.insertTable(rows, cols, tbl_fmt)
                        for r_idx, row in enumerate(table_data):
                            for c_idx, cell_txt in enumerate(row):
                                cell_cursor = table.cellAt(r_idx, c_idx).firstCursorPosition()
                                cell_cursor.insertText(cell_txt)
                        cursor.movePosition(QTextCursor.MoveOperation.End)

            self._is_dirty = False
        finally:
            self._is_loading = False

    def save_to_file(self, file_path: str = None):
        target = file_path or self.current_file
        if not target:
            return

        paragraphs_data = []
        doc = self.editor.document()
        block = doc.begin()

        while block.isValid():
            text = block.text()
            if text.strip() or block.next().isValid():
                runs_data = []
                it = block.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid():
                        fmt = frag.charFormat()
                        runs_data.append({
                            "text": frag.text(),
                            "bold": fmt.fontWeight() == QFont.Weight.Bold,
                            "italic": fmt.fontItalic(),
                            "underline": fmt.fontUnderline(),
                            "font_size": fmt.fontPointSize() if fmt.fontPointSize() > 0 else 11
                        })
                    it += 1

                align_flag = block.blockFormat().alignment()
                align_str = "left"
                if align_flag & Qt.AlignmentFlag.AlignCenter:
                    align_str = "center"
                elif align_flag & Qt.AlignmentFlag.AlignRight:
                    align_str = "right"
                elif align_flag & Qt.AlignmentFlag.AlignJustify:
                    align_str = "justify"

                paragraphs_data.append({
                    "style": "Normal",
                    "text": text,
                    "alignment": align_str,
                    "runs": runs_data
                })
            block = block.next()

        handler = DocxHandler()
        handler.write(target, {"paragraphs": paragraphs_data, "tables": []})
        self.current_file = target
        self._is_dirty = False

    def _on_text_changed(self):
        if self._is_loading:
            return
        self._is_dirty = True
        self.content_changed.emit()

    def _on_cursor_changed(self):
        fmt = self.editor.currentCharFormat()
        self.btn_bold.blockSignals(True)
        self.btn_bold.setChecked(fmt.fontWeight() == QFont.Weight.Bold)
        self.btn_bold.blockSignals(False)

        self.btn_italic.blockSignals(True)
        self.btn_italic.setChecked(fmt.fontItalic())
        self.btn_italic.blockSignals(False)

        self.btn_underline.blockSignals(True)
        self.btn_underline.setChecked(fmt.fontUnderline())
        self.btn_underline.blockSignals(False)

        self.btn_strike.blockSignals(True)
        self.btn_strike.setChecked(fmt.fontStrikeOut())
        self.btn_strike.blockSignals(False)

    def _toggle_bold(self):
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if self.btn_bold.isChecked() else QFont.Weight.Normal)
        self._merge_format(fmt)

    def _toggle_italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(self.btn_italic.isChecked())
        self._merge_format(fmt)

    def _toggle_underline(self):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(self.btn_underline.isChecked())
        self._merge_format(fmt)

    def _toggle_strike(self):
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(self.btn_strike.isChecked())
        self._merge_format(fmt)

    def _apply_font_family(self, family: str):
        fmt = QTextCharFormat()
        fmt.setFontFamily(family)
        self._merge_format(fmt)

    def _apply_font_size(self, size_str: str):
        try:
            sz = float(size_str)
            fmt = QTextCharFormat()
            fmt.setFontPointSize(sz)
            self._merge_format(fmt)
        except ValueError:
            pass

    def _apply_heading_style(self, index: int):
        sizes = [11, 18, 14, 12, 11]
        sz = sizes[index] if index < len(sizes) else 11
        fmt = QTextCharFormat()
        fmt.setFontPointSize(sz)
        fmt.setFontWeight(QFont.Weight.Bold if index > 0 else QFont.Weight.Normal)
        self._merge_format(fmt)

    def _pick_text_color(self):
        col = QColorDialog.getColor(Qt.GlobalColor.black, self, "Metin Rengi Seç")
        if col.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(col)
            self._merge_format(fmt)
            self.btn_text_color.setStyleSheet(f"font-weight: bold; border-bottom: 2px solid {col.name()};")

    def _pick_bg_color(self):
        col = QColorDialog.getColor(Qt.GlobalColor.yellow, self, "Vurgu Rengi Seç")
        if col.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(col)
            self._merge_format(fmt)

    def _set_alignment(self, align):
        self.editor.setAlignment(align)

    def _insert_bullet_list(self):
        cursor = self.editor.textCursor()
        cursor.insertList(QTextListFormat.Style.ListDisc)

    def _insert_numbered_list(self):
        cursor = self.editor.textCursor()
        cursor.insertList(QTextListFormat.Style.ListDecimal)

    def _insert_table(self):
        rows, ok1 = QInputDialog.getInt(self, "Tablo Ekle", "Satır Sayısı:", value=3, min=1, max=50)
        if not ok1:
            return
        cols, ok2 = QInputDialog.getInt(self, "Tablo Ekle", "Sütun Sayısı:", value=3, min=1, max=20)
        if not ok2:
            return

        cursor = self.editor.textCursor()
        tbl_fmt = QTextTableFormat()
        tbl_fmt.setBorder(1)
        tbl_fmt.setCellPadding(6)
        cursor.insertTable(rows, cols, tbl_fmt)

    def _merge_format(self, format: QTextCharFormat):
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        cursor.mergeCharFormat(format)
        self.editor.mergeCurrentCharFormat(format)
