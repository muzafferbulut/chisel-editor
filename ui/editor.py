from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit
from PyQt6.QtGui import QPainter, QColor, QTextFormat, QPen
from PyQt6.QtCore import Qt, QRect, pyqtSignal
import os

class LineNumberArea(QWidget):

    def __init__(self, editor):
        super().__init__(editor)
        self.code_editor = editor

    def sizeHint(self):
        return self.code_editor.line_number_area_size_hint()

    def paintEvent(self, event):
        self.code_editor.line_number_area_paint_event(event)

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
            line_color = QColor("#e8f2fe") 
            
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
            
        self.setExtraSelections(extra_selections)

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        bg_color = QColor("#f0f0f0")
        painter.fillRect(event.rect(), bg_color)
        pen = QPen(QColor("#c0c0c0"))
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
                painter.setPen(QColor("#808080"))
                painter.drawText(
                    0, top, self.line_number_area.width() - 5, 
                    self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, number
                )

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