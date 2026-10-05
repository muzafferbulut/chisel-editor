from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from core.theme import ThemeManager

class ToastNotification(QWidget):
    
    @classmethod
    def show_toast(cls, parent, message, notification_type="info", duration=3000):
        return cls(parent, message, notification_type, duration)

    def __init__(self, parent, message, notification_type="info", duration=3000):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        theme_obj = ThemeManager.current_theme()
        p = theme_obj.palette if theme_obj else {}
        bg_color = p.get('header_bg', '#333333' if ThemeManager.is_dark() else '#24292e')
        text_color = p.get('text', '#ffffff')
        border_color = {
            "info": p.get('primary', "#007fd4"),
            "success": "#4CAF50",
            "error": "#F44336"
        }.get(notification_type, p.get('primary', "#007fd4"))

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.label = QLabel(message)
        self.label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                padding: 12px 20px;
                border-radius: 6px;
                border-left: 4px solid {border_color};
                font-size: 13px;
                font-family: sans-serif;
            }}
        """)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.label)
        
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        
        self.adjustSize()
        self._position_toast(parent)
        
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(300)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._fade_out)
        self.timer.start(duration)
        
        self.show()
        self.animation.start()

    def _position_toast(self, parent):
        parent_rect = parent.geometry()
        x = parent_rect.x() + parent_rect.width() - self.width() - 20
        y = parent_rect.y() + parent_rect.height() - self.height() - 40
        self.move(x, y)

    def _fade_out(self):
        self.animation.setDirection(QPropertyAnimation.Direction.Backward)
        self.animation.finished.connect(self.close)
        self.animation.start()