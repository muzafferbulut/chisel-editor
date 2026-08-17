from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit
from PyQt6.QtGui import QPainter, QColor, QTextFormat, QPen, QTextCursor
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from core.theme import ThemeManager
import os

class LineNumberArea(QWidget):

    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return self.code_editor.line_number_area_size_hint()

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)

    def mousePressEvent(self, event):
        self.code_editor.line_number_area_mouse_press_event(event)


class ChiselCodeEditor(QPlainTextEdit):

    file_dropped = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        self.highlight_current_line()
        font = self.document().defaultFont()
        font.setFamily("Courier New")
        self.document().setDefaultFont(font)
        self.setAcceptDrops(True)
        self._current_font_size = 13
        self.folded_blocks = set()

    def line_number_area_width(self):
        digits = 1
        max_num = max(1, self.blockCount())
        while max_num >= 10:
            max_num //= 10
            digits += 1

        space = 20 + self.fontMetrics().horizontalAdvance('9') * digits
        return space
    
    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            
            line_color = QColor(ThemeManager.get_color("highlight")) 
            
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
            
        self.setExtraSelections(extra_selections)

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        bg_color = QColor(ThemeManager.get_color("line_bg"))
        painter.fillRect(event.rect(), bg_color)
        
        pen = QPen(QColor(ThemeManager.get_color("line_border")))
        painter.setPen(pen)
        painter.drawLine(
            self.line_number_area.width() - 1, event.rect().top(),
            self.line_number_area.width() - 1, event.rect().bottom()
        )

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor(ThemeManager.get_color("line_text")))
                painter.drawText(
                    0, top, self.line_number_area.width() - 15,
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, number
                )

                text = block.text()
                next_block = block.next()
                if next_block.isValid() and text.strip():
                    indent = len(text) - len(text.lstrip())
                    next_text = next_block.text()
                    
                    if next_text.strip():
                        next_indent = len(next_text) - len(next_text.lstrip())
                        if next_indent > indent:
                            is_folded = block_number in self.folded_blocks
                            sign = "+" if is_folded else "-"
                            
                            icon_rect = QRect(self.line_number_area.width() - 12, top + (self.fontMetrics().height() - 10) // 2, 10, 10)
                            painter.setPen(QColor(ThemeManager.get_color("line_border")))
                            painter.drawRect(icon_rect)
                            
                            painter.setPen(QColor(ThemeManager.get_color("line_text")))
                            painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, sign)

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if os.path.isfile(file_path):
                    self.file_dropped.emit(file_path)
        else:
            super().dropEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self._current_font_size += 1
            elif delta < 0:
                self._current_font_size -= 1
            self._current_font_size = max(8, min(self._current_font_size, 48))
            self.setStyleSheet(f"font-size: {self._current_font_size}px;")
            event.accept()
        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        
        char = event.text()
        match_dict = {'{': '}', '[': ']', '(': ')', '"': '"', "'": "'"}
        
        if char in match_dict:
            cursor = self.textCursor()
            cursor.insertText(match_dict[char])
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cursor)

    def line_number_area_mouse_press_event(self, event):
        cursor = self.cursorForPosition(event.pos())
        block = cursor.block()

        if event.pos().x() >= self.line_number_area.width() - 15:
            self.toggle_fold(block.blockNumber())

    def toggle_fold(self, block_number):
        block = self.document().findBlockByNumber(block_number)
        if not block.isValid() or not block.text().strip(): return
        
        indent = len(block.text()) - len(block.text().lstrip())
        is_folded = block_number in self.folded_blocks
        
        if is_folded:
            self.folded_blocks.remove(block_number)
        else:
            self.folded_blocks.add(block_number)
            
        next_block = block.next()
        while next_block.isValid():
            text = next_block.text()
            if text.strip():
                next_indent = len(text) - len(text.lstrip())
                if next_indent <= indent:
                    break
            
            next_block.setVisible(is_folded)
            next_block = next_block.next()

        self.document().markContentsDirty(block.position(), self.document().characterCount())
        self.viewport().update()
        self.update_line_number_area_width(0)