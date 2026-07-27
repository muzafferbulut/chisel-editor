from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt6.QtCore import QRegularExpression
from core.theme import ThemeManager


class JsonHighlighter(QSyntaxHighlighter):

    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        key_fmt = QTextCharFormat()
        key_fmt.setForeground(QColor(ThemeManager.get_color("syntax_key")))
        key_fmt.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r'".*?"(?=\s*:)'), key_fmt))

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor(ThemeManager.get_color("syntax_str")))
        self.rules.append((QRegularExpression(r'".*?"'), str_fmt))

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor(ThemeManager.get_color("syntax_num")))
        self.rules.append((QRegularExpression(r'\b[-+]?\d*\.?\d+([eE][-+]?\d+)?\b'), num_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)


class MarkdownHighlighter(QSyntaxHighlighter):

    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        header_fmt = QTextCharFormat()
        header_fmt.setForeground(QColor("#005cc5"))
        header_fmt.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r'^#+ .*'), header_fmt))
        bold_fmt = QTextCharFormat()
        bold_fmt.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r'\*\*.*?\*\*'), bold_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self.rules:
            match_iterator = pattern.globalMatch(text)
            while match_iterator.hasNext():
                match = match_iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)