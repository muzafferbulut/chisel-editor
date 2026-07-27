import sys
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from core.theme import ThemeManager 

def main():
    app = QApplication(sys.argv)
    ThemeManager.apply_theme(app, "light")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()