import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox,
    QPushButton, QColorDialog, QInputDialog, QLabel, QFrame,
    QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import (
    QFont, QTextCharFormat, QTextCursor,
    QTextBlockFormat, QTextTableFormat, QTextListFormat, QIcon
)
from handlers.docx import DocxHandler
from core.theme import ThemeManager


class WordDocumentEditorWidget(QWidget):
    """
    Rich Text / WYSIWYG document editor for Microsoft Word (.docx) files.
    Features Word-style formatting toolbar, dark/light paper toggle,
    A4 page layout, real-time statistics, and .docx export support.
    """
    content_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_file = None
        self._is_loading = False
        self._is_dirty = False
        self._dark_paper_mode = False
        self._current_theme = "light"
        self._init_ui()
        self.apply_theme()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Word Formatting Toolbar
        self.toolbar_container = QWidget()
        self.toolbar_container.setObjectName("WordToolbar")
        toolbar_layout = QHBoxLayout(self.toolbar_container)
        toolbar_layout.setContentsMargins(6, 4, 6, 4)
        toolbar_layout.setSpacing(4)

        # Undo / Redo
        self.btn_undo = self._create_tool_btn("undo", "↶", "Undo (Ctrl+Z)", lambda: self.editor.undo())
        toolbar_layout.addWidget(self.btn_undo)

        self.btn_redo = self._create_tool_btn("redo", "↷", "Redo (Ctrl+Y)", lambda: self.editor.redo())
        toolbar_layout.addWidget(self.btn_redo)

        toolbar_layout.addWidget(self._create_sep())

        # Heading / Style Selector
        self.style_combo = QComboBox()
        self.style_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.style_combo.setMinimumContentsLength(8)
        self.style_combo.addItems(["Normal Text", "Heading 1", "Heading 2", "Heading 3", "Heading 4"])
        self.style_combo.setToolTip("Style / Heading Level")
        self.style_combo.activated.connect(self._apply_heading_style)
        toolbar_layout.addWidget(self.style_combo)

        # Font Family
        self.font_combo = QComboBox()
        self.font_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.font_combo.setMinimumContentsLength(10)
        self.font_combo.addItems(["Calibri", "Segoe UI", "Arial", "Times New Roman", "Verdana", "Courier New"])
        self.font_combo.setToolTip("Font Family")
        self.font_combo.currentTextChanged.connect(self._apply_font_family)
        toolbar_layout.addWidget(self.font_combo)

        # Font Size
        self.size_combo = QComboBox()
        self.size_combo.addItems(["9", "10", "11", "12", "14", "16", "18", "20", "24", "28", "32", "48"])
        self.size_combo.setCurrentText("11")
        self.size_combo.setToolTip("Font Size")
        self.size_combo.currentTextChanged.connect(self._apply_font_size)
        toolbar_layout.addWidget(self.size_combo)

        toolbar_layout.addWidget(self._create_sep())

        # Bold, Italic, Underline, Strikethrough
        self.btn_bold = self._create_tool_btn("bold", "B", "Bold (Ctrl+B)", self._toggle_bold, checkable=True)
        toolbar_layout.addWidget(self.btn_bold)

        self.btn_italic = self._create_tool_btn("italic", "I", "Italic (Ctrl+I)", self._toggle_italic, checkable=True)
        toolbar_layout.addWidget(self.btn_italic)

        self.btn_underline = self._create_tool_btn("underline", "U", "Underline (Ctrl+U)", self._toggle_underline, checkable=True)
        toolbar_layout.addWidget(self.btn_underline)

        self.btn_strike = self._create_tool_btn("strike", "S", "Strikethrough", self._toggle_strike, checkable=True)
        toolbar_layout.addWidget(self.btn_strike)

        toolbar_layout.addWidget(self._create_sep())

        # Colors
        self.btn_text_color = self._create_tool_btn("text_color", "A", "Text Color", self._pick_text_color)
        toolbar_layout.addWidget(self.btn_text_color)

        self.btn_bg_color = self._create_tool_btn("bg_color", "🖍", "Highlight Color", self._pick_bg_color)
        toolbar_layout.addWidget(self.btn_bg_color)

        toolbar_layout.addWidget(self._create_sep())

        # Alignment
        self.btn_align_left = self._create_tool_btn("align_left", "⇤", "Align Left", lambda: self._set_alignment(Qt.AlignmentFlag.AlignLeft))
        toolbar_layout.addWidget(self.btn_align_left)

        self.btn_align_center = self._create_tool_btn("align_center", "⬌", "Align Center", lambda: self._set_alignment(Qt.AlignmentFlag.AlignCenter))
        toolbar_layout.addWidget(self.btn_align_center)

        self.btn_align_right = self._create_tool_btn("align_right", "⇥", "Align Right", lambda: self._set_alignment(Qt.AlignmentFlag.AlignRight))
        toolbar_layout.addWidget(self.btn_align_right)

        self.btn_align_justify = self._create_tool_btn("align_justify", "☰", "Justify", lambda: self._set_alignment(Qt.AlignmentFlag.AlignJustify))
        toolbar_layout.addWidget(self.btn_align_justify)

        toolbar_layout.addWidget(self._create_sep())

        # Lists & Tables
        self.btn_bullet_list = self._create_tool_btn("list_bullet", "•=", "Bullet List", self._insert_bullet_list)
        toolbar_layout.addWidget(self.btn_bullet_list)

        self.btn_num_list = self._create_tool_btn("list_num", "1=", "Numbered List", self._insert_numbered_list)
        toolbar_layout.addWidget(self.btn_num_list)

        self.btn_table = self._create_tool_btn("table", "▦", "Insert Table", self._insert_table)
        toolbar_layout.addWidget(self.btn_table)

        toolbar_layout.addWidget(self._create_sep())

        # Paper Mode Toggle (Dark Paper / White Paper)
        self.btn_paper_mode = self._create_tool_btn("paper_mode", "◐", "Page View Mode (Dark Paper / White Paper)", self._toggle_paper_mode, checkable=True)
        toolbar_layout.addWidget(self.btn_paper_mode)

        toolbar_layout.addStretch()

        # Word count & statistics
        self.lbl_stats = QLabel("0 words | 0 characters")
        self.lbl_stats.setStyleSheet("color: #858585; font-size: 11px; padding: 0 8px;")
        toolbar_layout.addWidget(self.lbl_stats)

        self.toolbar_scroll = QScrollArea()
        self.toolbar_scroll.setObjectName("WordToolbarScroll")
        self.toolbar_scroll.setWidgetResizable(True)
        self.toolbar_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.toolbar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.toolbar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.toolbar_scroll.setFixedHeight(38)
        self.toolbar_scroll.setWidget(self.toolbar_container)
        main_layout.addWidget(self.toolbar_scroll)

        # 2. Document Canvas Container (A4 Paper Look)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.canvas_widget = QWidget()
        canvas_layout = QVBoxLayout(self.canvas_widget)
        canvas_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        canvas_layout.setContentsMargins(20, 20, 20, 20)

        self.editor = QTextEdit()
        self.editor.setMinimumWidth(320)
        self.editor.setMaximumWidth(850)
        self.editor.setMinimumHeight(450)
        self.editor.cursorPositionChanged.connect(self._on_cursor_changed)
        self.editor.textChanged.connect(self._on_text_changed)

        canvas_layout.addWidget(self.editor)
        self.scroll_area.setWidget(self.canvas_widget)
        main_layout.addWidget(self.scroll_area)

    def _create_sep(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("background-color: rgba(128, 128, 128, 0.25); width: 1px; margin: 2px 3px; border: none;")
        return sep

    def _get_icon(self, icon_name: str) -> QIcon:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "resources", "icons", f"{icon_name}.png")
        if os.path.isfile(icon_path):
            return QIcon(icon_path)
        return QIcon()

    def _create_tool_btn(self, icon_name: str, fallback_text: str, tooltip: str, callback=None, checkable: bool = False) -> QPushButton:
        btn = QPushButton()
        icon = self._get_icon(icon_name)
        if not icon.isNull():
            btn.setIcon(icon)
            btn.setIconSize(QSize(16, 16))
        else:
            btn.setText(fallback_text)

        btn.setToolTip(tooltip)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if checkable:
            btn.setCheckable(True)
        if callback:
            btn.clicked.connect(callback)
        return btn

    def _toggle_paper_mode(self):
        self._dark_paper_mode = self.btn_paper_mode.isChecked()
        self.apply_theme(self._current_theme)

    def apply_theme(self, theme_name: str = None):
        """Applies dynamic theme styling to toolbar, canvas, and A4 document page."""
        if theme_name:
            self._current_theme = theme_name
        tokens = ThemeManager.get_tokens(self._current_theme)
        toolbar_bg = tokens.get("toolbar_bg", "#f8fafc")
        panel_bg = tokens.get("panel_bg", "#ffffff")
        text = tokens.get("text", "#1e293b")
        text_muted = tokens.get("text_muted", "#64748b")
        border = tokens.get("border", "#e2e8f0")
        hover = tokens.get("hover", "rgba(128,128,128,0.18)")
        active = tokens.get("active", "rgba(128,128,128,0.30)")
        accent = tokens.get("accent", "#0284c7")
        is_dark = ThemeManager.is_dark(self._current_theme)

        # Toolbar styling
        tb_qss = f"""
            #WordToolbar {{
                background-color: {toolbar_bg};
                border-bottom: 1px solid {border};
            }}
            #WordToolbar QPushButton {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
                color: {text};
            }}
            #WordToolbar QPushButton:hover {{
                background-color: {hover};
                border: 1px solid {border};
            }}
            #WordToolbar QPushButton:pressed {{
                background-color: {active};
            }}
            #WordToolbar QPushButton:checked {{
                background-color: {active};
                border: 1px solid {accent};
            }}
            #WordToolbar QComboBox {{
                background-color: {panel_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 11px;
            }}
        """
        self.toolbar_container.setStyleSheet(tb_qss)

        # Canvas container background
        canvas_bg = panel_bg if is_dark else "#f1f5f9"
        self.scroll_area.setStyleSheet(f"QScrollArea {{ border: none; background-color: {canvas_bg}; }}")
        self.canvas_widget.setStyleSheet(f"background-color: {canvas_bg};")

        # Document Page Styling (Adaptive Paper Mode)
        if is_dark and self._dark_paper_mode:
            paper_bg = tokens.get("paper_bg", "#252526")
            paper_color = tokens.get("paper_text", "#e0e0e0")
            paper_border = border
        else:
            paper_bg = "#ffffff"
            paper_color = "#1e293b"
            paper_border = "#cbd5e1"

        page_qss = f"""
            QTextEdit {{
                background-color: {paper_bg};
                color: {paper_color};
                border: 1px solid {paper_border};
                border-radius: 4px;
                padding: 40px;
                font-family: 'Calibri', 'Segoe UI', sans-serif;
                font-size: 11pt;
                line-height: 1.5;
            }}
        """
        self.editor.setStyleSheet(page_qss)
        self.lbl_stats.setStyleSheet(f"color: {text_muted}; font-size: 11px; padding: 0 8px;")

    def load_data(self, data: dict, file_path: str = None):
        """Loads structured Word document data into the rich text editor."""
        if file_path:
            self.current_file = file_path
        self._is_loading = True
        try:
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

            self._update_stats()
            self._is_dirty = False
        finally:
            self._is_loading = False

    def load_file(self, file_path: str):
        self.current_file = file_path
        handler = DocxHandler()
        data = handler.read(file_path)
        self.load_data(data, file_path)

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

    def _update_stats(self):
        text = self.editor.toPlainText()
        words = len(text.split()) if text.strip() else 0
        chars = len(text)
        self.lbl_stats.setText(f"{words:,} words | {chars:,} characters")

    def _on_text_changed(self):
        if self._is_loading:
            return
        self._update_stats()
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
        col = QColorDialog.getColor(Qt.GlobalColor.black, self, "Select Text Color")
        if col.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(col)
            self._merge_format(fmt)

    def _pick_bg_color(self):
        col = QColorDialog.getColor(Qt.GlobalColor.yellow, self, "Select Highlight Color")
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
        rows, ok1 = QInputDialog.getInt(self, "Insert Table", "Number of Rows:", value=3, min=1, max=50)
        if not ok1:
            return
        cols, ok2 = QInputDialog.getInt(self, "Insert Table", "Number of Columns:", value=3, min=1, max=20)
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
